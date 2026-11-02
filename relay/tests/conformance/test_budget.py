"""The call budget on both backends: all-or-nothing spends, waits, deletion, exhaust."""

from __future__ import annotations

import threading
from collections.abc import Callable

import pytest
from tests.conformance.state_support import Target, raw
from tests.conformance.test_connections import principals

from fitdocs_relay.config import PostgresTarget
from fitdocs_relay.storage.interface import (
    BudgetCharge,
    BudgetDecision,
    Storage,
    StorageUnreachable,
    UnknownPrincipal,
)

START = 1_700_000_400  # a multiple of both windows used (100 and 400)
SHORT, LONG = 100, 400
ALLOWED = BudgetDecision(True, None)


@pytest.fixture
def store(open_full_storage: Callable[[], Storage]) -> Storage:
    return open_full_storage()


def charge(
    key: str,
    *,
    window_s: int = SHORT,
    ceiling: int = 10,
    amount: int = 1,
    principal_id: str | None = None,
) -> BudgetCharge:
    return BudgetCharge(key, window_s, ceiling, amount, principal_id)


def counts(target: Target) -> dict[tuple[str, int], int]:
    """Every row with a count above zero: (key, window_start) -> count."""
    return {
        (str(k), int(s)): int(c)
        for k, s, c in raw(
            target,
            "SELECT key, window_start, count FROM budget_counts WHERE count > 0",
        )
    }


def row_ends(target: Target) -> dict[tuple[str, int], int]:
    return {
        (str(k), int(s)): int(e)
        for k, s, e in raw(
            target, "SELECT key, window_start, window_end FROM budget_counts"
        )
    }


def test_the_fixture_start_is_a_boundary_of_every_window_used() -> None:
    assert START % SHORT == 0 and START % LONG == 0


@pytest.mark.covers("BudgetStore.spend_budget")
def test_a_spend_counts_in_fixed_windows_and_is_allowed_up_to_the_ceiling(
    database_target: Target, store: Storage
) -> None:
    assert counts(database_target) == {}
    assert store.spend_budget((charge("k", ceiling=5, amount=2),), now=START + 37) == (
        ALLOWED
    )
    assert counts(database_target) == {("k", START): 2}
    assert row_ends(database_target) == {("k", START): START + SHORT}
    # exactly at the ceiling is allowed (2 + 2 + 1 = 5)
    assert store.spend_budget((charge("k", ceiling=5, amount=2),), now=START + 38) == (
        ALLOWED
    )
    assert store.spend_budget((charge("k", ceiling=5, amount=1),), now=START + 99) == (
        ALLOWED
    )
    assert counts(database_target) == {("k", START): 5}
    # one more is over; the count stays
    refused = store.spend_budget((charge("k", ceiling=5),), now=START + 99)
    assert refused == BudgetDecision(False, 1)
    assert counts(database_target) == {("k", START): 5}


@pytest.mark.covers("BudgetStore.spend_budget")
def test_a_spend_that_would_pass_the_ceiling_by_its_amount_is_refused_whole(
    database_target: Target, store: Storage
) -> None:
    assert store.spend_budget((charge("k", ceiling=5, amount=3),), now=START) == (
        ALLOWED
    )
    # 3 + 3 = 6 > 5, though 3 + 1 would fit: the amount is added in full
    assert store.spend_budget((charge("k", ceiling=5, amount=3),), now=START + 10) == (
        BudgetDecision(False, SHORT - 10)
    )
    assert counts(database_target) == {("k", START): 3}


@pytest.mark.covers("BudgetStore.spend_budget")
def test_a_later_window_starts_a_new_count(
    database_target: Target, store: Storage
) -> None:
    store.spend_budget((charge("k", ceiling=1),), now=START + 50)
    assert store.spend_budget((charge("k", ceiling=1),), now=START + 60) == (
        BudgetDecision(False, 40)
    )
    # the window's first second belongs to the new window
    assert store.spend_budget((charge("k", ceiling=1),), now=START + SHORT) == ALLOWED
    assert counts(database_target) == {("k", START + SHORT): 1}


@pytest.mark.covers("BudgetStore.spend_budget")
def test_a_refusal_leaves_every_window_of_the_spend_unchanged(
    database_target: Target, store: Storage
) -> None:
    store.spend_budget((charge("full", ceiling=2, amount=2),), now=START)
    store.spend_budget((charge("roomy", ceiling=50, amount=7),), now=START)
    before = counts(database_target)
    assert before == {("full", START): 2, ("roomy", START): 7}

    refused = store.spend_budget(
        (charge("roomy", ceiling=50, amount=4), charge("full", ceiling=2)),
        now=START + 1,
    )

    assert refused.allowed is False
    assert counts(database_target) == before


@pytest.mark.covers("BudgetStore.spend_budget")
def test_a_refusal_whose_first_charge_is_the_full_one_changes_nothing_either(
    database_target: Target, store: Storage
) -> None:
    store.spend_budget((charge("full", ceiling=1),), now=START)
    refused = store.spend_budget(
        (charge("full", ceiling=1), charge("roomy", ceiling=50, amount=4)),
        now=START + 1,
    )
    assert refused.allowed is False
    assert counts(database_target) == {("full", START): 1}


@pytest.mark.covers("BudgetStore.spend_budget")
def test_a_refusal_reports_the_longest_wait_among_the_windows_it_would_exceed(
    database_target: Target, store: Storage
) -> None:
    now = START + 130  # the short window ends at START + 200, the long at START + 400
    store.spend_budget(
        (
            charge("short", window_s=SHORT, ceiling=1),
            charge("long", window_s=LONG, ceiling=1),
            charge("roomy", window_s=LONG, ceiling=99),
        ),
        now=now,
    )
    refused = store.spend_budget(
        (
            charge("short", window_s=SHORT, ceiling=1),
            charge("long", window_s=LONG, ceiling=1),
            charge("roomy", window_s=LONG, ceiling=99),
        ),
        now=now,
    )
    # short waits 70, long waits 270 (to START + 400); roomy is no cause
    assert refused == BudgetDecision(False, 270)
    # the same, charges in the other order: the longest wait does not depend on order
    reversed_ = store.spend_budget(
        (
            charge("long", window_s=LONG, ceiling=1),
            charge("short", window_s=SHORT, ceiling=1),
        ),
        now=now,
    )
    assert reversed_ == BudgetDecision(False, 270)
    # only the short window is exceeded here: its own wait, not the long one's
    only_short = store.spend_budget(
        (
            charge("short", window_s=SHORT, ceiling=1),
            charge("roomy", window_s=LONG, ceiling=99),
        ),
        now=now,
    )
    assert only_short == BudgetDecision(False, 70)


@pytest.mark.covers("BudgetStore.spend_budget")
def test_a_spend_of_several_windows_raises_every_count_by_its_own_amount(
    database_target: Target, store: Storage
) -> None:
    decision = store.spend_budget(
        (
            charge("a", window_s=SHORT, amount=3),
            charge("a", window_s=LONG, amount=3),
            charge("b", window_s=SHORT, amount=5),
        ),
        now=START + 150,
    )
    assert decision == ALLOWED
    assert counts(database_target) == {
        ("a", START + SHORT): 3,
        ("a", START): 3,
        ("b", START + SHORT): 5,
    }


@pytest.mark.covers("BudgetStore.spend_budget")
def test_an_empty_spend_is_allowed_and_changes_nothing(
    database_target: Target, store: Storage
) -> None:
    assert store.spend_budget((), now=START) == ALLOWED
    assert counts(database_target) == {}


@pytest.mark.covers("BudgetStore.spend_budget")
def test_ended_windows_are_deleted_by_a_spend_and_live_ones_are_kept(
    database_target: Target, store: Storage
) -> None:
    store.spend_budget((charge("old", window_s=SHORT),), now=START)  # ends START+100
    store.spend_budget((charge("edge", window_s=SHORT),), now=START + 50)  # same
    store.spend_budget((charge("kept", window_s=LONG),), now=START)  # ends START+400
    assert set(row_ends(database_target)) == {
        ("old", START),
        ("edge", START),
        ("kept", START),
    }

    # at the window's end it has ended (end <= now)
    store.spend_budget((charge("other", window_s=LONG),), now=START + SHORT)

    assert set(row_ends(database_target)) == {("kept", START), ("other", START)}


@pytest.mark.covers("BudgetStore.spend_budget")
def test_a_refused_spend_still_deletes_ended_windows(
    database_target: Target, store: Storage
) -> None:
    store.spend_budget((charge("old", window_s=SHORT),), now=START)
    store.spend_budget((charge("full", window_s=LONG, ceiling=1),), now=START)
    assert ("old", START) in row_ends(database_target)

    refused = store.spend_budget(
        (charge("full", window_s=LONG, ceiling=1),), now=START + SHORT + 1
    )

    assert refused.allowed is False
    assert set(row_ends(database_target)) == {("full", START)}


@pytest.mark.covers("BudgetStore.spend_budget", "PrincipalStore.delete_principal")
def test_rows_tagged_with_a_principal_go_with_it_and_untagged_rows_stay(
    database_target: Target, store: Storage
) -> None:
    principals(store, "ann", "bea")
    store.spend_budget(
        (
            charge("global"),
            charge("per-short", principal_id="ann"),
            charge("per-long", window_s=LONG, principal_id="ann"),
            charge("bea-key", principal_id="bea"),
        ),
        now=START,
    )
    assert {
        (str(k), str(p))
        for k, p in raw(database_target, "SELECT key, principal_id FROM budget_counts")
        if p is not None
    } == {
        ("per-short", "ann"),
        ("per-long", "ann"),
        ("bea-key", "bea"),
    }
    assert len(counts(database_target)) == 4

    assert store.delete_principal("ann") is True

    assert counts(database_target) == {("global", START): 1, ("bea-key", START): 1}


@pytest.mark.covers("BudgetStore.spend_budget")
def test_a_charge_for_an_unknown_principal_is_refused_and_stores_nothing(
    database_target: Target, store: Storage
) -> None:
    principals(store, "ann")
    with pytest.raises(UnknownPrincipal):
        store.spend_budget(
            (charge("fine", principal_id="ann"), charge("lost", principal_id="ghost")),
            now=START,
        )
    assert raw(database_target, "SELECT count(*) FROM budget_counts") == [(0,)]


@pytest.mark.covers("BudgetStore.spend_budget")
@pytest.mark.parametrize(
    "bad",
    [
        pytest.param(charge("k", window_s=0), id="window-zero"),
        pytest.param(charge("k", window_s=-5), id="window-negative"),
        pytest.param(charge("k", amount=0), id="amount-zero"),
        pytest.param(charge("k", amount=-1), id="amount-negative"),
        pytest.param(charge("k", ceiling=-1), id="ceiling-negative"),
    ],
)
def test_a_malformed_charge_is_a_value_error_and_stores_nothing(
    database_target: Target, store: Storage, bad: BudgetCharge
) -> None:
    with pytest.raises(ValueError):
        store.spend_budget((charge("fine"), bad), now=START)
    assert raw(database_target, "SELECT count(*) FROM budget_counts") == [(0,)]


@pytest.mark.covers("BudgetStore.spend_budget")
def test_a_zero_ceiling_refuses_every_spend(
    database_target: Target, store: Storage
) -> None:
    assert store.spend_budget((charge("k", ceiling=0),), now=START + 1) == (
        BudgetDecision(False, SHORT - 1)
    )
    assert counts(database_target) == {}


@pytest.mark.covers("BudgetStore.spend_budget")
def test_one_window_charged_twice_in_a_spend_is_a_value_error(
    database_target: Target, store: Storage
) -> None:
    with pytest.raises(ValueError):
        store.spend_budget((charge("k"), charge("k", amount=2)), now=START)
    assert raw(database_target, "SELECT count(*) FROM budget_counts") == [(0,)]


@pytest.mark.covers("BudgetStore.exhaust_budget", "BudgetStore.spend_budget")
def test_exhaust_raises_the_current_windows_count_and_the_next_spend_is_refused(
    database_target: Target, store: Storage
) -> None:
    store.spend_budget((charge("k", ceiling=10, amount=2),), now=START + 5)
    assert counts(database_target) == {("k", START): 2}

    store.exhaust_budget(key="k", window_s=SHORT, count=10, now=START + 40)

    assert counts(database_target) == {("k", START): 10}
    assert store.spend_budget((charge("k", ceiling=10),), now=START + 41) == (
        BudgetDecision(False, SHORT - 41)
    )


@pytest.mark.covers("BudgetStore.exhaust_budget")
def test_exhaust_creates_the_window_never_lowers_a_count_and_touches_only_its_window(
    database_target: Target, store: Storage
) -> None:
    store.exhaust_budget(key="fresh", window_s=SHORT, count=7, now=START + 3)
    assert counts(database_target) == {("fresh", START): 7}
    assert row_ends(database_target) == {("fresh", START): START + SHORT}

    store.exhaust_budget(key="fresh", window_s=SHORT, count=4, now=START + 4)
    assert counts(database_target) == {("fresh", START): 7}  # not lowered

    store.exhaust_budget(key="fresh", window_s=SHORT, count=7, now=START + 5)
    assert counts(database_target) == {("fresh", START): 7}  # equal: unchanged

    store.exhaust_budget(key="fresh", window_s=SHORT, count=9, now=START + SHORT)
    assert counts(database_target) == {
        ("fresh", START): 7,
        ("fresh", START + SHORT): 9,
    }
    store.exhaust_budget(key="other", window_s=LONG, count=1, now=START + SHORT)
    assert counts(database_target)[("fresh", START + SHORT)] == 9
    assert counts(database_target)[("other", START)] == 1


@pytest.mark.covers("BudgetStore.exhaust_budget")
def test_exhaust_with_a_window_shorter_than_a_second_is_a_value_error(
    database_target: Target, store: Storage
) -> None:
    with pytest.raises(ValueError):
        store.exhaust_budget(key="k", window_s=0, count=1, now=START)
    assert raw(database_target, "SELECT count(*) FROM budget_counts") == [(0,)]


@pytest.mark.covers("BudgetStore.spend_budget", "BudgetStore.exhaust_budget")
def test_every_budget_operation_on_a_closed_store_is_unreachable(
    store: Storage,
) -> None:
    store.close()
    with pytest.raises(StorageUnreachable):
        store.spend_budget((charge("k"),), now=START)
    with pytest.raises(StorageUnreachable):
        store.exhaust_budget(key="k", window_s=SHORT, count=1, now=START)


@pytest.mark.covers("BudgetStore.exhaust_budget")
def test_exhaust_with_a_negative_count_is_a_value_error(
    database_target: Target, store: Storage
) -> None:
    with pytest.raises(ValueError):
        store.exhaust_budget(key="k", window_s=SHORT, count=-1, now=START)
    assert raw(database_target, "SELECT count(*) FROM budget_counts") == [(0,)]


def _spend_in_a_thread(
    store: Storage, charges: tuple[BudgetCharge, ...], now: int
) -> tuple[threading.Thread, list[object]]:
    outcome: list[object] = []

    def run() -> None:
        try:
            outcome.append(store.spend_budget(charges, now=now))
        except BaseException as error:  # noqa: BLE001 - reported to the test
            outcome.append(error)

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    return thread, outcome


@pytest.mark.covers("BudgetStore.spend_budget")
def test_postgres_a_spend_does_not_wait_for_an_ended_window_another_transaction_holds(
    database_target: Target, store: Storage
) -> None:
    if not isinstance(database_target, PostgresTarget):
        pytest.skip("row locks held across statements are the PostgreSQL backend's")
    import psycopg

    store.exhaust_budget(key="old", window_s=SHORT, count=3, now=START - SHORT)
    assert row_ends(database_target) == {("old", START - SHORT): START}
    holder = psycopg.connect(database_target.conninfo)
    try:
        holder.execute(
            "SELECT 1 FROM budget_counts WHERE key = 'old' FOR UPDATE"
        ).fetchall()
        thread, outcome = _spend_in_a_thread(store, (charge("new"),), START + 1)
        thread.join(timeout=10)
        assert not thread.is_alive(), "the spend waited for the held row"
        assert outcome == [ALLOWED]
        # the held row was skipped, not deleted
        assert ("old", START - SHORT) in row_ends(database_target)
    finally:
        holder.rollback()
        holder.close()
    # a later spend finds the row free and deletes it
    assert store.spend_budget((charge("new"),), now=START + 2) == ALLOWED
    assert ("old", START - SHORT) not in row_ends(database_target)


@pytest.mark.covers("BudgetStore.spend_budget")
def test_postgres_spends_straddling_a_window_boundary_do_not_deadlock(
    database_target: Target, store: Storage
) -> None:
    if not isinstance(database_target, PostgresTarget):
        pytest.skip("row locks held across statements are the PostgreSQL backend's")
    import psycopg

    quarter, day = 900, 86_400
    edge = START - START % quarter + quarter  # the first moment of a new quarter
    assert edge % day != 0  # the day window is the same row on both sides
    pair = (
        charge("all", window_s=quarter, ceiling=100),
        charge("read", window_s=day, ceiling=100),
    )
    store.spend_budget(
        pair, now=edge - 5
    )  # both rows exist, the quarter's is ended at `edge`
    assert store.spend_budget(pair, now=edge - 4) == ALLOWED
    # An earlier spend (T, now = edge - 1) that has locked only its first row.
    earlier = psycopg.connect(database_target.conninfo)
    try:
        earlier.execute(
            "SELECT 1 FROM budget_counts WHERE key = 'all' AND window_start = %s "
            "FOR UPDATE",
            (edge - quarter,),
        ).fetchall()
        # A later spend (U) locks the day row T wants next, then cleans up.
        thread, outcome = _spend_in_a_thread(store, pair, edge)
        thread.join(timeout=10)
        assert not thread.is_alive(), "the later spend waited on the earlier one"
        assert outcome == [ALLOWED]
        # T now takes the day row U held; U has committed, so this is not a wait cycle.
        earlier.execute(
            "SELECT 1 FROM budget_counts WHERE key = 'read' FOR UPDATE"
        ).fetchall()
        earlier.commit()
    finally:
        earlier.close()


@pytest.mark.covers("BudgetStore.spend_budget")
def test_postgres_a_principal_deleted_mid_spend_is_unknown_not_a_storage_error(
    database_target: Target, store: Storage
) -> None:
    if not isinstance(database_target, PostgresTarget):
        pytest.skip(
            "SQLite serialises every write, so a delete cannot be left open mid-spend"
        )
    import psycopg

    principals(store, "ann")
    deleter = psycopg.connect(database_target.conninfo)
    try:
        deleter.execute("DELETE FROM principals WHERE principal_id = 'ann'")
        thread, outcome = _spend_in_a_thread(
            store, (charge("k", principal_id="ann"),), START + 1
        )
        thread.join(timeout=1)
        assert thread.is_alive(), "the spend did not wait for the open delete"
        deleter.commit()
    finally:
        deleter.close()
    thread.join(timeout=10)
    assert not thread.is_alive()
    assert len(outcome) == 1 and isinstance(outcome[0], UnknownPrincipal), outcome
    assert raw(database_target, "SELECT count(*) FROM budget_counts") == [(0,)]
