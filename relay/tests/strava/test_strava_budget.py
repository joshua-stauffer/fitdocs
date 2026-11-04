"""StravaBudget (task 3.3) on both backends, against the real budget tables."""

from __future__ import annotations

from collections.abc import Callable

import pytest
from tests.conformance.state_support import Target, raw

from fitdocs_relay.storage.interface import BudgetDecision, NewPrincipal, Storage
from fitdocs_relay.strava.budget import CallKind, StravaBudget
from fitdocs_relay.strava.config import Limits

MIDNIGHT = 1_700_006_400  # a UTC midnight: 19676 x 86400
NOW = MIDNIGHT + 3 * 900 + 100  # 100 s into the fourth quarter hour of the day
HUGE = 1_000_000
ALLOWED = BudgetDecision(True, None)
FIELDS = ("overall_15m", "overall_day", "read_15m", "read_day")


@pytest.fixture
def store(open_full_storage: Callable[[], Storage]) -> Storage:
    s = open_full_storage()
    for pid in ("p1", "p2", "p3", "p4"):
        s.create_principal(NewPrincipal(pid, None), now=1)
    return s


class Clock:
    def __init__(self, now: int = NOW) -> None:
        self.now = now

    def __call__(self) -> int:
        return self.now


def limits(**small: int) -> Limits:
    """Every limit huge except the ones named."""
    values = {name: HUGE for name in FIELDS} | small
    return Limits(**values)


def budget(
    store: Storage, lim: Limits, clock: Clock | None = None
) -> tuple[StravaBudget, Clock]:
    c = clock or Clock()
    return StravaBudget(store, lim, clock=c), c


def counts(target: Target) -> dict[str, int]:
    return {
        str(k): int(c)
        for k, c in raw(target, "SELECT key, count FROM budget_counts WHERE count > 0")
    }


def allowed_run(b: StravaBudget, principal: str, limit: int) -> int:
    """How many single reads `principal` gets before the first refusal."""
    n = 0
    while n <= limit and b.spend(principal).allowed:
        n += 1
    return n


# --- the counted windows ---------------------------------------------------


def test_a_read_counts_in_the_application_and_the_principals_four_windows(
    database_target: Target, store: Storage
) -> None:
    b, _ = budget(store, limits())
    assert counts(database_target) == {}
    assert b.spend("p1") == ALLOWED
    assert counts(database_target) == {
        "strava:all:900": 1,
        "strava:all:86400": 1,
        "strava:read:900": 1,
        "strava:read:86400": 1,
        "strava:p:p1:all:900": 1,
        "strava:p:p1:all:86400": 1,
        "strava:p:p1:read:900": 1,
        "strava:p:p1:read:86400": 1,
    }


def test_an_upload_counts_in_the_overall_windows_only(
    database_target: Target, store: Storage
) -> None:
    b, _ = budget(store, limits(read_15m=1, read_day=1))
    assert b.spend("p1", CallKind.UPLOAD, count=2) == ALLOWED
    assert counts(database_target) == {
        "strava:all:900": 2,
        "strava:all:86400": 2,
        "strava:p:p1:all:900": 2,
        "strava:p:p1:all:86400": 2,
    }
    # the read windows (limit 1) are untouched, so they still hold their one read
    assert b.spend("p2") == ALLOWED


def test_a_count_below_one_is_refused_and_counts_nothing(
    database_target: Target, store: Storage
) -> None:
    b, _ = budget(store, limits())
    with pytest.raises(ValueError):
        b.spend("p1", count=0)
    with pytest.raises(ValueError):
        b.reserve_upload("p1", reads=-1)
    assert counts(database_target) == {}


def test_a_spend_of_several_counts_each_in_every_window(
    database_target: Target, store: Storage
) -> None:
    b, _ = budget(store, limits())
    assert b.spend("p1", count=3) == ALLOWED
    assert set(counts(database_target).values()) == {3}
    assert len(counts(database_target)) == 8


# --- the principal's share -------------------------------------------------


@pytest.mark.parametrize(
    ("name", "limit", "share"),
    [
        ("overall_15m", 11, 5),
        ("overall_day", 23, 11),
        ("read_15m", 15, 7),
        ("read_day", 27, 13),
    ],
)
def test_a_principal_may_use_the_floor_of_half_of_each_window(
    store: Storage, name: str, limit: int, share: int
) -> None:
    b, _ = budget(store, limits(**{name: limit}))
    assert allowed_run(b, "p1", limit) == share
    # another principal is still allowed
    assert b.spend("p2") == ALLOWED


def test_a_share_that_floors_to_zero_is_one_call(store: Storage) -> None:
    b, _ = budget(store, limits(read_15m=1))
    assert b.spend("p1") == ALLOWED
    assert b.spend("p1").allowed is False


@pytest.mark.parametrize("name", FIELDS)
def test_the_application_window_is_the_whole_limit_shared_by_principals(
    store: Storage, name: str
) -> None:
    b, _ = budget(store, limits(**{name: 7}))  # a share of 3 each
    assert [allowed_run(b, p, 7) for p in ("p1", "p2")] == [3, 3]
    # p3 is under its own share: only the application's last call is left
    assert b.spend("p3") == ALLOWED
    refused = b.spend("p4")
    assert refused.allowed is False
    assert refused.retry_after_s is not None and refused.retry_after_s > 0


# --- the upload reservation ------------------------------------------------


def test_a_reservation_counts_the_upload_and_its_reads_together(
    database_target: Target, store: Storage
) -> None:
    b, _ = budget(store, limits())
    assert b.reserve_upload("p1", reads=3) == ALLOWED
    assert counts(database_target) == {
        "strava:all:900": 4,
        "strava:all:86400": 4,
        "strava:read:900": 3,
        "strava:read:86400": 3,
        "strava:p:p1:all:900": 4,
        "strava:p:p1:all:86400": 4,
        "strava:p:p1:read:900": 3,
        "strava:p:p1:read:86400": 3,
    }


def test_a_reservation_without_reads_counts_the_upload_alone(
    database_target: Target, store: Storage
) -> None:
    b, _ = budget(store, limits())
    assert b.reserve_upload("p1", reads=0) == ALLOWED
    assert set(counts(database_target)) == {
        "strava:all:900",
        "strava:all:86400",
        "strava:p:p1:all:900",
        "strava:p:p1:all:86400",
    }
    assert set(counts(database_target).values()) == {1}


def test_a_reservation_the_read_windows_cannot_hold_counts_nothing(
    database_target: Target, store: Storage
) -> None:
    b, _ = budget(store, limits(read_15m=20))  # a share of 10
    for _ in range(8):
        assert b.spend("p1") == ALLOWED
    before = counts(database_target)
    assert before["strava:read:900"] == 8
    refused = b.reserve_upload("p1", reads=3)  # 8 + 3 > 10; the overall has room
    assert refused.allowed is False
    assert counts(database_target) == before
    assert b.reserve_upload("p1", reads=2) == ALLOWED


def test_a_reservation_the_overall_windows_cannot_hold_counts_nothing(
    database_target: Target, store: Storage
) -> None:
    b, _ = budget(store, limits(overall_15m=20))  # a share of 10
    assert b.spend("p1", count=6) == ALLOWED
    before = counts(database_target)
    refused = b.reserve_upload("p1", reads=4)  # 6 + 5 > 10; the read windows have room
    assert refused.allowed is False
    assert counts(database_target) == before
    assert b.reserve_upload("p1", reads=3) == ALLOWED


def test_a_reservation_larger_than_any_window_names_no_wait(
    database_target: Target, store: Storage
) -> None:
    b, _ = budget(store, limits(read_15m=20))
    assert b.reserve_upload("p1", reads=11) == BudgetDecision(False, None)
    assert counts(database_target) == {}


# --- windows spent by Strava's answer --------------------------------------


def test_a_quarter_hour_mark_blocks_the_rest_of_that_quarter_hour_only(
    database_target: Target, store: Storage
) -> None:
    lim = limits(overall_15m=30, read_15m=20)
    b, clock = budget(store, lim)
    b.mark_spent(daily=False)
    assert counts(database_target) == {"strava:all:900": 30, "strava:read:900": 20}
    # 800 s to the end of the quarter hour (NOW is 100 s into it)
    assert b.spend("p1") == BudgetDecision(False, 800)
    assert b.spend("p3", CallKind.UPLOAD) == BudgetDecision(False, 800)
    assert b.reserve_upload("p4", reads=0) == BudgetDecision(False, 800)
    clock.now = NOW + 800
    assert b.spend("p1") == ALLOWED


def test_a_daily_mark_blocks_the_rest_of_the_day(
    database_target: Target, store: Storage
) -> None:
    lim = limits(overall_15m=30, overall_day=300, read_15m=20, read_day=200)
    b, clock = budget(store, lim)
    b.mark_spent(daily=True)
    assert counts(database_target) == {
        "strava:all:900": 30,
        "strava:read:900": 20,
        "strava:all:86400": 300,
        "strava:read:86400": 200,
    }
    assert b.spend("p1") == BudgetDecision(False, 86400 - 2800)
    clock.now = NOW + 900  # the next quarter hour: the day still holds
    assert b.spend("p1") == BudgetDecision(False, 86400 - 3700)
    assert b.spend("p1", CallKind.UPLOAD) == BudgetDecision(False, 86400 - 3700)
    clock.now = MIDNIGHT + 86400
    assert b.spend("p1") == ALLOWED


def test_a_mark_does_not_touch_the_principals_windows(
    database_target: Target, store: Storage
) -> None:
    b, _ = budget(store, limits(overall_15m=30, read_15m=20))
    b.spend("p1")
    b.mark_spent(daily=True)
    assert {k for k in counts(database_target) if k.startswith("strava:p:")} == {
        "strava:p:p1:all:900",
        "strava:p:p1:all:86400",
        "strava:p:p1:read:900",
        "strava:p:p1:read:86400",
    }
    assert {
        counts(database_target)[k]
        for k in counts(database_target)
        if k.startswith("strava:p:")
    } == {1}


# --- the windows -----------------------------------------------------------


def test_the_quarter_hour_window_is_fifteen_minutes_and_the_day_window_a_day(
    store: Storage,
) -> None:
    b, clock = budget(store, limits(read_15m=2, read_day=HUGE))
    clock.now = MIDNIGHT + 899
    assert b.spend("p1") == ALLOWED
    assert b.spend("p1") == BudgetDecision(False, 1)  # share 1; ends at +900
    clock.now = MIDNIGHT + 900
    assert b.spend("p1") == ALLOWED

    # a later day, so the first half's day count is not in the way
    b2, clock2 = budget(store, limits(read_day=2))
    clock2.now = MIDNIGHT + 3 * 86400 - 1
    assert b2.spend("p2") == ALLOWED
    assert b2.spend("p2") == BudgetDecision(False, 1)
    clock2.now = MIDNIGHT + 3 * 86400
    assert b2.spend("p2") == ALLOWED


def test_a_day_window_holds_across_quarter_hours_and_half_a_day(store: Storage) -> None:
    b, clock = budget(store, limits(read_day=2))
    assert b.spend("p1") == ALLOWED
    for later in (900, 3600, 43200, 50000):
        clock.now = MIDNIGHT + later
        assert b.spend("p1").allowed is False


def test_a_principals_windows_go_with_the_principal(
    database_target: Target, store: Storage
) -> None:
    b, _ = budget(store, limits())
    b.spend("p1")
    assert len(counts(database_target)) == 8
    assert store.delete_principal("p1") is True
    assert set(counts(database_target)) == {
        "strava:all:900",
        "strava:all:86400",
        "strava:read:900",
        "strava:read:86400",
    }
