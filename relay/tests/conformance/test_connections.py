"""Target connections on both backends: put, get, list, delete and cascades."""

from __future__ import annotations

from collections.abc import Callable

import pytest
from tests.conformance.state_support import Target, raw
from tests.conftest import BYTE_ORDER, TIED_IDS

from fitdocs_relay.storage.interface import (
    NewConnection,
    NewPrincipal,
    NewToken,
    SealedTokens,
    Storage,
    StorageUnreachable,
    StoredConnection,
    UnknownPrincipal,
)

T1, T2, T3, T4 = 1_700_000_001, 1_700_000_002, 1_700_000_003, 1_700_000_004
STRAVA = "strava"
OTHER = "othertarget"
UPPER = "Strava"


@pytest.fixture
def store(open_full_storage: Callable[[], Storage]) -> Storage:
    return open_full_storage()


def principals(store: Storage, *ids: str) -> None:
    for principal_id in ids:
        store.create_principal(NewPrincipal(principal_id, None), now=T1)


def connection(
    principal_id: str,
    account_key: str,
    *,
    target: str = STRAVA,
    access: str = "sealed-access",
    refresh: str | None = "sealed-refresh",
    expires: int | None = T4,
) -> NewConnection:
    return NewConnection(
        principal_id,
        target,
        account_key,
        SealedTokens(access=access, refresh=refresh, access_expires_at=expires),
    )


def mint(store: Storage, token_id: str, principal_id: str) -> None:
    store.mint_token(
        NewToken(token_id, f"verifier-{token_id}", None),
        principal_id=principal_id,
        new_principal=None,
        now=T1,
    )


def attach_token(
    target: Target, principal_id: str, token_id: str, *, on: str = STRAVA
) -> None:
    """Record `token_id` as the connection's token (issuance is a later operation)."""
    raw(
        target,
        "UPDATE target_connections SET token_id = ? "
        "WHERE principal_id = ? AND target = ?",
        (token_id, principal_id, on),
    )


def add_publication(
    target: Target, publication_id: str, principal_id: str, *, on: str = STRAVA
) -> None:
    raw(
        target,
        "INSERT INTO target_publications (target, publication_id, principal_id, "
        "sport, start_s, elapsed_s, distance_m, created_at, updated_at) "
        "VALUES (?, ?, ?, 'run', 1.0, NULL, NULL, 1, 1)",
        (on, publication_id, principal_id),
    )


def publications(target: Target) -> list[tuple[str, str, str]]:
    return [
        (str(t), str(p), str(o))
        for t, p, o in raw(
            target,
            "SELECT target, publication_id, principal_id FROM target_publications "
            "ORDER BY target, publication_id",
        )
    ]


def revoked_at(store: Storage, token_id: str) -> int | None:
    record = store.find_token(token_id)
    assert record is not None
    return record.revoked_at


def must_get(
    store: Storage, principal_id: str, target: str = STRAVA
) -> StoredConnection:
    found = store.get_connection(principal_id, target)
    assert found is not None
    return found


@pytest.mark.covers(
    "TargetConnectionStore.put_connection", "TargetConnectionStore.get_connection"
)
def test_a_connection_reads_back_with_its_tokens_generation_one_and_no_lease(
    store: Storage,
) -> None:
    principals(store, "ann")
    assert store.get_connection("ann", STRAVA) is None
    store.put_connection(
        connection("ann", "acct-1", access="A-sealed", refresh="R-sealed", expires=T4),
        now=T2,
    )
    assert store.get_connection("ann", STRAVA) == StoredConnection(
        principal_id="ann",
        target=STRAVA,
        account_key="acct-1",
        tokens=SealedTokens("A-sealed", "R-sealed", T4),
        generation=1,
        lease_id=None,
        lease_until=None,
        token_id=None,
        created_at=T2,
        updated_at=T2,
    )
    assert store.get_connection("ann", OTHER) is None
    assert store.get_connection("bea", STRAVA) is None


@pytest.mark.covers(
    "TargetConnectionStore.put_connection", "TargetConnectionStore.get_connection"
)
def test_a_connection_with_no_access_expiry_and_no_refresh_reads_back_as_none(
    store: Storage,
) -> None:
    principals(store, "ann")
    store.put_connection(
        connection("ann", "acct-1", refresh=None, expires=None), now=T2
    )
    stored = must_get(store, "ann")
    assert stored.tokens.access_expires_at is None
    assert stored.tokens.refresh is None
    assert stored.tokens.access == "sealed-access"


@pytest.mark.covers(
    "TargetConnectionStore.put_connection", "TargetConnectionStore.get_connection"
)
def test_the_same_principal_putting_again_replaces_the_tokens_and_resets_the_state(
    database_target: Target, store: Storage
) -> None:
    principals(store, "ann")
    mint(store, "tok-ann", "ann")
    store.put_connection(connection("ann", "acct-1"), now=T2)
    raw(
        database_target,
        "UPDATE target_connections SET generation = 7, lease_id = 'lease-x', "
        "lease_until = 99, token_id = 'tok-ann'",
    )
    before = must_get(store, "ann")
    assert (before.generation, before.lease_id, before.token_id) == (
        7,
        "lease-x",
        "tok-ann",
    )

    store.put_connection(
        connection("ann", "acct-1", access="new-A", refresh=None, expires=None), now=T3
    )

    after = must_get(store, "ann")
    assert after.tokens == SealedTokens("new-A", None, None)
    assert (after.generation, after.lease_id, after.lease_until) == (1, None, None)
    assert after.token_id == "tok-ann"  # kept, so the next issuance revokes it
    assert (after.created_at, after.updated_at) == (T2, T3)
    assert revoked_at(store, "tok-ann") is None
    assert len(store.list_connections(None)) == 1


@pytest.mark.covers(
    "TargetConnectionStore.put_connection", "TargetConnectionStore.get_connection"
)
def test_targets_are_separate_even_for_one_account_key(store: Storage) -> None:
    principals(store, "ann", "bea")
    store.put_connection(connection("ann", "acct-1", access="s"), now=T2)
    store.put_connection(connection("ann", "acct-1", target=OTHER, access="o"), now=T2)
    store.put_connection(connection("bea", "acct-1", target=OTHER, access="b"), now=T3)
    # bea displaced ann on OTHER only
    assert must_get(store, "ann").tokens.access == "s"
    assert store.get_connection("ann", OTHER) is None
    assert must_get(store, "bea", OTHER).tokens.access == "b"


@pytest.mark.covers("TargetConnectionStore.put_connection")
def test_a_rival_is_sought_on_the_puts_target_only(
    database_target: Target, store: Storage
) -> None:
    # ann holds acct-1 on strava and a different account on OTHER; bea's put
    # of acct-1 on OTHER finds no rival there, so nothing of ann's goes.
    principals(store, "ann", "bea")
    mint(store, "tok-ann-other", "ann")
    store.put_connection(connection("ann", "acct-1"), now=T2)
    store.put_connection(connection("ann", "acct-2", target=OTHER), now=T2)
    attach_token(database_target, "ann", "tok-ann-other", on=OTHER)
    add_publication(database_target, "pub-ann-other", "ann", on=OTHER)

    store.put_connection(connection("bea", "acct-1", target=OTHER), now=T3)

    assert must_get(store, "ann").account_key == "acct-1"
    assert must_get(store, "ann", OTHER).account_key == "acct-2"
    assert must_get(store, "bea", OTHER).account_key == "acct-1"
    assert revoked_at(store, "tok-ann-other") is None
    assert publications(database_target) == [(OTHER, "pub-ann-other", "ann")]


@pytest.mark.covers("TargetConnectionStore.put_connection")
def test_a_put_for_an_unknown_principal_is_refused_and_stores_nothing(
    database_target: Target, store: Storage
) -> None:
    with pytest.raises(UnknownPrincipal):
        store.put_connection(connection("ghost", "acct-1"), now=T2)
    assert raw(database_target, "SELECT count(*) FROM target_connections") == [(0,)]


@pytest.mark.covers("TargetConnectionStore.put_connection")
def test_another_principals_connection_to_the_account_is_displaced_with_its_records(
    database_target: Target, store: Storage
) -> None:
    principals(store, "ann", "bea", "cy")
    for token_id, owner in (("tok-ann", "ann"), ("tok-ann2", "ann"), ("tok-cy", "cy")):
        mint(store, token_id, owner)
    store.put_connection(connection("ann", "acct-X"), now=T2)
    store.put_connection(connection("ann", "acct-X", target=OTHER), now=T2)
    store.put_connection(connection("cy", "acct-Y"), now=T2)
    attach_token(database_target, "ann", "tok-ann")
    attach_token(database_target, "ann", "tok-ann2", on=OTHER)
    attach_token(database_target, "cy", "tok-cy")
    add_publication(database_target, "pub-a", "ann")
    add_publication(database_target, "pub-a-other", "ann", on=OTHER)
    add_publication(database_target, "pub-c", "cy")
    assert must_get(store, "ann").account_key == "acct-X"  # the rival is present

    store.put_connection(connection("bea", "acct-X", access="bea-A"), now=T3)

    assert store.get_connection("ann", STRAVA) is None
    assert must_get(store, "bea").tokens.access == "bea-A"
    assert [c.principal_id for c in store.list_connections(STRAVA)] == ["bea", "cy"]
    assert must_get(store, "ann", OTHER).account_key == "acct-X"
    assert publications(database_target) == [
        (OTHER, "pub-a-other", "ann"),
        (STRAVA, "pub-c", "cy"),
    ]
    assert revoked_at(store, "tok-ann") == T3
    assert revoked_at(store, "tok-ann2") is None
    assert revoked_at(store, "tok-cy") is None


@pytest.mark.covers("TargetConnectionStore.put_connection")
def test_displacing_a_connection_does_not_restamp_an_already_revoked_token(
    database_target: Target, store: Storage
) -> None:
    principals(store, "ann", "bea")
    mint(store, "tok-ann", "ann")
    store.put_connection(connection("ann", "acct-X"), now=T2)
    attach_token(database_target, "ann", "tok-ann")
    store.revoke_token("tok-ann", now=T2)

    store.put_connection(connection("bea", "acct-X"), now=T4)

    assert revoked_at(store, "tok-ann") == T2


@pytest.mark.covers("TargetConnectionStore.put_connection")
def test_a_changed_account_drops_own_publications_and_the_same_account_keeps_them(
    database_target: Target, store: Storage
) -> None:
    principals(store, "ann", "bea")
    mint(store, "tok-ann", "ann")
    store.put_connection(connection("ann", "acct-X"), now=T2)
    store.put_connection(connection("ann", "acct-X", target=OTHER), now=T2)
    store.put_connection(connection("bea", "acct-B"), now=T2)
    attach_token(database_target, "ann", "tok-ann")
    for publication_id, owner, on in (
        ("pub-a", "ann", STRAVA),
        ("pub-a-other", "ann", OTHER),
        ("pub-b", "bea", STRAVA),
    ):
        add_publication(database_target, publication_id, owner, on=on)

    store.put_connection(connection("ann", "acct-X", access="again"), now=T3)
    assert len(publications(database_target)) == 3  # the same account: all kept

    store.put_connection(connection("ann", "acct-Z"), now=T4)

    assert publications(database_target) == [
        (OTHER, "pub-a-other", "ann"),
        (STRAVA, "pub-b", "bea"),
    ]
    assert must_get(store, "ann").account_key == "acct-Z"
    assert must_get(store, "ann").token_id == "tok-ann"
    assert revoked_at(store, "tok-ann") is None
    assert must_get(store, "bea").account_key == "acct-B"


@pytest.mark.covers(
    "TargetConnectionStore.list_connections", "TargetConnectionStore.put_connection"
)
@pytest.mark.usefixtures("ids_sort_by_locale_here")
def test_list_orders_by_target_then_principal_in_byte_order_and_filters_by_target(
    store: Storage,
) -> None:
    assert store.list_connections(None) == ()
    assert store.list_connections(STRAVA) == ()
    principals(store, *TIED_IDS)
    # put in an order that is neither the byte order nor the reverse of it
    for index, principal_id in enumerate(TIED_IDS):
        store.put_connection(connection(principal_id, f"a{index}"), now=T2)
    store.put_connection(connection("ab", "a-upper", target=UPPER), now=T2)
    store.put_connection(connection("Z", "a-other", target=OTHER), now=T2)

    # byte order: "Strava" < "othertarget" < "strava"
    assert [(c.target, c.principal_id) for c in store.list_connections(None)] == [
        (UPPER, "ab"),
        (OTHER, "Z"),
        *[(STRAVA, principal_id) for principal_id in BYTE_ORDER],
    ]
    assert [c.principal_id for c in store.list_connections(STRAVA)] == BYTE_ORDER
    assert [c.principal_id for c in store.list_connections(OTHER)] == ["Z"]
    assert store.list_connections("nothing") == ()


@pytest.mark.covers(
    "TargetConnectionStore.delete_connection", "TargetConnectionStore.put_connection"
)
def test_delete_removes_the_connection_its_publications_and_revokes_its_token(
    database_target: Target, store: Storage
) -> None:
    principals(store, "ann", "bea")
    mint(store, "tok-ann", "ann")
    mint(store, "tok-bea", "bea")
    store.put_connection(connection("ann", "acct-X"), now=T2)
    store.put_connection(connection("ann", "acct-X", target=OTHER), now=T2)
    store.put_connection(connection("bea", "acct-B"), now=T2)
    attach_token(database_target, "ann", "tok-ann")
    attach_token(database_target, "bea", "tok-bea")
    add_publication(database_target, "pub-a", "ann")
    add_publication(database_target, "pub-a-other", "ann", on=OTHER)
    add_publication(database_target, "pub-b", "bea")

    assert store.delete_connection("ann", STRAVA, generation=None, now=T3) is True

    assert store.get_connection("ann", STRAVA) is None
    assert store.delete_connection("ann", STRAVA, generation=None, now=T3) is False
    assert must_get(store, "ann", OTHER).account_key == "acct-X"
    assert must_get(store, "bea").account_key == "acct-B"
    assert publications(database_target) == [
        (OTHER, "pub-a-other", "ann"),
        (STRAVA, "pub-b", "bea"),
    ]
    assert revoked_at(store, "tok-ann") == T3
    assert revoked_at(store, "tok-bea") is None


@pytest.mark.covers("TargetConnectionStore.delete_connection")
def test_delete_with_a_generation_deletes_only_on_a_match(
    database_target: Target, store: Storage
) -> None:
    principals(store, "ann")
    mint(store, "tok-ann", "ann")
    store.put_connection(connection("ann", "acct-X"), now=T2)
    attach_token(database_target, "ann", "tok-ann")
    add_publication(database_target, "pub-a", "ann")
    raw(database_target, "UPDATE target_connections SET generation = 4")

    for wrong in (3, 5, 1):
        assert store.delete_connection("ann", STRAVA, generation=wrong, now=T3) is False
    assert must_get(store, "ann").generation == 4
    assert publications(database_target) == [(STRAVA, "pub-a", "ann")]
    assert revoked_at(store, "tok-ann") is None

    assert store.delete_connection("ann", STRAVA, generation=4, now=T3) is True
    assert store.get_connection("ann", STRAVA) is None
    assert publications(database_target) == []
    assert revoked_at(store, "tok-ann") == T3


@pytest.mark.covers("TargetConnectionStore.delete_connection")
def test_delete_of_a_missing_connection_is_false(store: Storage) -> None:
    principals(store, "ann")
    store.put_connection(connection("ann", "acct-X"), now=T2)
    assert store.delete_connection("ann", OTHER, generation=None, now=T3) is False
    assert store.delete_connection("bea", STRAVA, generation=None, now=T3) is False
    assert store.get_connection("ann", STRAVA) is not None


@pytest.mark.covers(
    "TargetConnectionStore.delete_connection_by_account",
    "TargetConnectionStore.put_connection",
)
def test_delete_by_account_removes_that_accounts_connection_and_nothing_else(
    database_target: Target, store: Storage
) -> None:
    principals(store, "ann", "bea")
    mint(store, "tok-ann", "ann")
    mint(store, "tok-bea", "bea")
    # bea's connection to the same account on another target is stored first, so
    # a lookup that ignored the target would reach it before ann's
    store.put_connection(connection("bea", "acct-X", target=OTHER), now=T2)
    store.put_connection(connection("ann", "acct-X"), now=T2)
    store.put_connection(connection("bea", "acct-B"), now=T2)
    attach_token(database_target, "ann", "tok-ann")
    attach_token(database_target, "bea", "tok-bea")
    add_publication(database_target, "pub-a", "ann")
    add_publication(database_target, "pub-b", "bea")

    assert store.delete_connection_by_account(STRAVA, "acct-nope", now=T3) is False
    assert store.delete_connection_by_account("nothing", "acct-X", now=T3) is False
    assert len(store.list_connections(None)) == 3

    assert store.delete_connection_by_account(STRAVA, "acct-X", now=T3) is True

    assert store.get_connection("ann", STRAVA) is None
    assert must_get(store, "bea", OTHER).account_key == "acct-X"
    assert must_get(store, "bea").account_key == "acct-B"
    assert publications(database_target) == [(STRAVA, "pub-b", "bea")]
    assert revoked_at(store, "tok-ann") == T3
    assert revoked_at(store, "tok-bea") is None
    assert store.delete_connection_by_account(STRAVA, "acct-X", now=T3) is False


@pytest.mark.covers(
    "PrincipalStore.delete_principal", "TargetConnectionStore.put_connection"
)
def test_deleting_a_principal_removes_its_connections_and_only_its_own(
    database_target: Target, store: Storage
) -> None:
    principals(store, "ann", "bea")
    store.put_connection(connection("ann", "acct-X"), now=T2)
    store.put_connection(connection("ann", "acct-X", target=OTHER), now=T2)
    store.put_connection(connection("bea", "acct-B"), now=T2)
    add_publication(database_target, "pub-a", "ann")
    add_publication(database_target, "pub-b", "bea")
    assert len(store.list_connections(None)) == 3

    assert store.delete_principal("ann") is True

    assert [(c.principal_id, c.target) for c in store.list_connections(None)] == [
        ("bea", STRAVA)
    ]
    assert publications(database_target) == [(STRAVA, "pub-b", "bea")]


@pytest.mark.covers(
    "TargetConnectionStore.put_connection",
    "TargetConnectionStore.get_connection",
    "TargetConnectionStore.list_connections",
    "TargetConnectionStore.delete_connection",
    "TargetConnectionStore.delete_connection_by_account",
)
def test_every_connection_operation_on_a_closed_store_is_unreachable(
    store: Storage,
) -> None:
    store.close()
    with pytest.raises(StorageUnreachable):
        store.put_connection(connection("ann", "acct-X"), now=T2)
    with pytest.raises(StorageUnreachable):
        store.get_connection("ann", STRAVA)
    with pytest.raises(StorageUnreachable):
        store.list_connections(None)
    with pytest.raises(StorageUnreachable):
        store.delete_connection("ann", STRAVA, generation=None, now=T2)
    with pytest.raises(StorageUnreachable):
        store.delete_connection_by_account(STRAVA, "acct-X", now=T2)


def test_a_sealed_token_never_appears_in_a_repr() -> None:
    shown = repr(connection("ann", "acct-X", access="SECRET-A", refresh="SECRET-R"))
    assert "SECRET-A" not in shown
    assert "SECRET-R" not in shown
