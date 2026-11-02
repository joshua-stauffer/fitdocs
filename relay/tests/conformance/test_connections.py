"""Target connections on both backends: put, get, list, delete and cascades."""

from __future__ import annotations

from collections.abc import Callable

import pytest
from tests.conformance.state_support import Target, raw
from tests.conftest import BYTE_ORDER, TIED_IDS

from fitdocs_relay.storage.interface import (
    DuplicateIdentifier,
    NewConnection,
    NewPrincipal,
    NewToken,
    RevokeResult,
    SealedTokens,
    Storage,
    StorageUnreachable,
    StoredConnection,
    TokenRecord,
    UnknownPrincipal,
)

T1, T2, T3, T4, T5, T6 = (1_700_000_000 + i for i in range(1, 7))
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
    "TargetConnectionStore.claim_refresh",
    "TargetConnectionStore.swap_tokens",
    "TargetConnectionStore.release_refresh",
    "TargetConnectionStore.issue_connection_token",
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
        store.claim_refresh(
            "ann", STRAVA, generation=1, lease_id="L", lease_until=T3, now=T2
        )
    with pytest.raises(StorageUnreachable):
        store.swap_tokens(
            "ann",
            STRAVA,
            generation=1,
            lease_id=None,
            tokens=SealedTokens("a", None, None),
            now=T2,
        )
    with pytest.raises(StorageUnreachable):
        store.release_refresh("ann", STRAVA, lease_id="L")
    with pytest.raises(StorageUnreachable):
        store.issue_connection_token("ann", STRAVA, NewToken("t", "v", None), now=T2)
    with pytest.raises(StorageUnreachable):
        store.delete_connection("ann", STRAVA, generation=None, now=T2)
    with pytest.raises(StorageUnreachable):
        store.delete_connection_by_account(STRAVA, "acct-X", now=T2)


def issue(
    store: Storage, principal_id: str, token_id: str, *, now: int, target: str = STRAVA
) -> TokenRecord | None:
    return store.issue_connection_token(
        principal_id,
        target,
        NewToken(token_id, f"verifier-{token_id}", "conn"),
        now=now,
    )


def token_count(target: Target) -> int:
    return int(raw(target, "SELECT count(*) FROM tokens")[0][0])


@pytest.mark.covers("TargetConnectionStore.issue_connection_token")
def test_issuing_without_a_connection_is_none_and_inserts_nothing(
    database_target: Target, store: Storage
) -> None:
    principals(store, "ann", "bea")
    store.put_connection(connection("bea", "acct-B"), now=T2)
    store.put_connection(connection("ann", "acct-A", target=OTHER), now=T2)
    assert token_count(database_target) == 0

    assert issue(store, "ann", "tok-1", now=T3) is None  # none on this target
    assert issue(store, "cat", "tok-2", now=T3) is None  # no such principal
    assert issue(store, "ann", "tok-3", now=T3, target=UPPER) is None  # case differs

    assert token_count(database_target) == 0
    assert must_get(store, "bea").token_id is None
    assert must_get(store, "ann", OTHER).token_id is None


@pytest.mark.covers(
    "TargetConnectionStore.issue_connection_token",
    "TargetConnectionStore.get_connection",
)
def test_the_first_issuance_inserts_the_token_for_the_principal_and_records_it(
    database_target: Target, store: Storage
) -> None:
    principals(store, "ann", "bea")
    store.put_connection(connection("ann", "acct-A"), now=T2)
    store.put_connection(connection("bea", "acct-B"), now=T2)
    assert token_count(database_target) == 0
    before = must_get(store, "ann")

    record = issue(store, "ann", "tok-1", now=T3)

    assert record is not None
    assert (record.token_id, record.principal_id) == ("tok-1", "ann")
    assert (record.verifier, record.label) == ("verifier-tok-1", "conn")
    assert (record.created_at, record.revoked_at) == (T3, None)
    assert store.find_token("tok-1") == record
    after = must_get(store, "ann")
    assert after.token_id == "tok-1"
    assert after == StoredConnection(
        before.principal_id,
        before.target,
        before.account_key,
        before.tokens,
        before.generation,
        before.lease_id,
        before.lease_until,
        "tok-1",
        before.created_at,
        before.updated_at,
    )
    assert must_get(store, "bea").token_id is None
    assert token_count(database_target) == 1


@pytest.mark.covers(
    "TargetConnectionStore.issue_connection_token",
    "TargetConnectionStore.get_connection",
)
def test_each_issuance_revokes_the_previous_connection_token_once_and_only_that(
    store: Storage,
) -> None:
    principals(store, "ann", "bea")
    mint(store, "tok-ann-free", "ann")  # the principal's own, not a connection token
    mint(store, "tok-bea", "bea")
    store.put_connection(connection("ann", "acct-A"), now=T2)
    store.put_connection(connection("ann", "acct-A", target=OTHER), now=T2)
    store.put_connection(connection("bea", "acct-B"), now=T2)
    assert issue(store, "ann", "other-1", now=T2, target=OTHER) is not None
    assert issue(store, "bea", "bea-1", now=T2) is not None
    assert issue(store, "ann", "tok-1", now=T3) is not None
    assert revoked_at(store, "tok-1") is None

    second = issue(store, "ann", "tok-2", now=T4)

    assert second is not None
    assert revoked_at(store, "tok-1") == T4
    assert revoked_at(store, "tok-2") is None
    assert must_get(store, "ann").token_id == "tok-2"

    assert issue(store, "ann", "tok-3", now=T5) is not None
    assert revoked_at(store, "tok-1") == T4  # not stamped again
    assert revoked_at(store, "tok-2") == T5
    assert revoked_at(store, "tok-3") is None
    assert must_get(store, "ann").token_id == "tok-3"
    # nothing else of the principal's or anyone else's was touched
    assert revoked_at(store, "tok-ann-free") is None
    assert revoked_at(store, "other-1") is None
    assert must_get(store, "ann", OTHER).token_id == "other-1"
    assert revoked_at(store, "bea-1") is None
    assert revoked_at(store, "tok-bea") is None


@pytest.mark.covers(
    "TargetConnectionStore.issue_connection_token",
    "TargetConnectionStore.put_connection",
)
def test_a_same_principal_put_keeps_the_token_so_the_next_issuance_revokes_it(
    store: Storage,
) -> None:
    principals(store, "ann")
    store.put_connection(connection("ann", "acct-A"), now=T2)
    assert issue(store, "ann", "tok-1", now=T3) is not None

    store.put_connection(connection("ann", "acct-A", access="re-put"), now=T4)
    assert must_get(store, "ann").token_id == "tok-1"
    assert revoked_at(store, "tok-1") is None

    assert issue(store, "ann", "tok-2", now=T5) is not None
    assert revoked_at(store, "tok-1") == T5
    assert revoked_at(store, "tok-2") is None
    assert must_get(store, "ann").token_id == "tok-2"


@pytest.mark.covers("TargetConnectionStore.issue_connection_token")
def test_a_token_id_already_in_use_is_refused_and_changes_nothing(
    database_target: Target, store: Storage
) -> None:
    principals(store, "ann", "bea")
    mint(store, "tok-bea", "bea")
    store.put_connection(connection("ann", "acct-A"), now=T2)
    assert issue(store, "ann", "tok-1", now=T3) is not None
    count = token_count(database_target)

    with pytest.raises(DuplicateIdentifier):
        issue(store, "ann", "tok-bea", now=T4)  # another principal's id
    with pytest.raises(DuplicateIdentifier):
        issue(store, "ann", "tok-1", now=T4)  # the connection's own current token

    assert token_count(database_target) == count
    assert revoked_at(store, "tok-1") is None
    assert revoked_at(store, "tok-bea") is None
    assert must_get(store, "ann").token_id == "tok-1"


@pytest.mark.covers("TargetConnectionStore.issue_connection_token")
def test_issuing_after_the_recorded_token_was_revoked_keeps_its_revocation_time(
    store: Storage,
) -> None:
    principals(store, "ann")
    store.put_connection(connection("ann", "acct-A"), now=T2)
    assert issue(store, "ann", "tok-1", now=T3) is not None
    assert store.revoke_token("tok-1", now=T4) is RevokeResult.REVOKED
    assert revoked_at(store, "tok-1") == T4

    assert issue(store, "ann", "tok-2", now=T6) is not None

    assert revoked_at(store, "tok-1") == T4
    assert revoked_at(store, "tok-2") is None
    assert must_get(store, "ann").token_id == "tok-2"


@pytest.mark.covers(
    "TargetConnectionStore.issue_connection_token",
    "TargetConnectionStore.delete_connection",
    "TargetConnectionStore.delete_connection_by_account",
)
def test_deleting_a_connection_revokes_the_token_issuance_recorded(
    store: Storage,
) -> None:
    principals(store, "ann", "bea")
    store.put_connection(connection("ann", "acct-A"), now=T2)
    store.put_connection(connection("bea", "acct-B"), now=T2)
    assert issue(store, "ann", "ann-1", now=T3) is not None
    assert issue(store, "ann", "ann-2", now=T4) is not None
    assert issue(store, "bea", "bea-1", now=T3) is not None

    assert store.delete_connection("ann", STRAVA, generation=None, now=T5)
    assert revoked_at(store, "ann-1") == T4  # not stamped again
    assert revoked_at(store, "ann-2") == T5
    assert revoked_at(store, "bea-1") is None

    assert store.delete_connection_by_account(STRAVA, "acct-B", now=T6)
    assert revoked_at(store, "bea-1") == T6
    assert issue(store, "ann", "ann-3", now=T6) is None  # the connection is gone


def claim(
    store: Storage,
    principal_id: str,
    lease_id: str,
    *,
    generation: int = 1,
    until: int,
    now: int,
    target: str = STRAVA,
) -> bool:
    return store.claim_refresh(
        principal_id,
        target,
        generation=generation,
        lease_id=lease_id,
        lease_until=until,
        now=now,
    )


NEW_TOKENS = SealedTokens(access="new-access", refresh=None, access_expires_at=None)


def swap(
    store: Storage,
    principal_id: str,
    *,
    generation: int = 1,
    lease: str | None,
    now: int,
    tokens: SealedTokens = NEW_TOKENS,
    target: str = STRAVA,
) -> bool:
    return store.swap_tokens(
        principal_id,
        target,
        generation=generation,
        lease_id=lease,
        tokens=tokens,
        now=now,
    )


def lease_of(store: Storage, principal_id: str) -> tuple[str | None, int | None]:
    found = must_get(store, principal_id)
    return found.lease_id, found.lease_until


@pytest.mark.covers("TargetConnectionStore.claim_refresh")
def test_a_claim_needs_the_generation_and_names_the_holder_and_the_lease_end(
    store: Storage,
) -> None:
    principals(store, "ann", "bea")
    store.put_connection(connection("ann", "acct-A"), now=T1)
    store.put_connection(connection("bea", "acct-B"), now=T1)
    before = must_get(store, "ann")
    assert lease_of(store, "ann") == (None, None)

    for wrong in (0, 2):
        assert (
            claim(store, "ann", "L-wrong", generation=wrong, until=T5, now=T2) is False
        )
    assert claim(store, "cat", "L-nobody", until=T5, now=T2) is False
    assert claim(store, "ann", "L-other", until=T5, now=T2, target=OTHER) is False
    assert lease_of(store, "ann") == (None, None)

    assert claim(store, "ann", "L-1", until=T5, now=T2) is True
    after = must_get(store, "ann")
    assert (after.lease_id, after.lease_until) == ("L-1", T5)
    assert after.generation == 1
    assert after.tokens == before.tokens
    assert after.updated_at == before.updated_at
    assert lease_of(store, "bea") == (None, None)


@pytest.mark.covers("TargetConnectionStore.claim_refresh")
def test_a_live_lease_refuses_every_claim_and_the_end_second_frees_it(
    store: Storage,
) -> None:
    principals(store, "ann")
    store.put_connection(connection("ann", "acct-A"), now=T1)
    assert claim(store, "ann", "L-1", until=T4, now=T2)

    assert claim(store, "ann", "L-2", until=T6, now=T2) is False
    assert claim(store, "ann", "L-1", until=T6, now=T3) is False  # not even its holder
    assert claim(store, "ann", "L-2", until=T6, now=T4 - 1) is False
    assert lease_of(store, "ann") == ("L-1", T4)

    # `lease_until <= now` frees the lease: at the end second, not a second later.
    assert claim(store, "ann", "L-2", until=T6, now=T4) is True
    assert lease_of(store, "ann") == ("L-2", T6)
    assert claim(store, "ann", "L-3", until=T6 + 9, now=T6 + 1) is True  # long past
    assert lease_of(store, "ann") == ("L-3", T6 + 9)


@pytest.mark.covers(
    "TargetConnectionStore.swap_tokens", "TargetConnectionStore.claim_refresh"
)
def test_a_swap_by_the_holder_writes_the_tokens_advances_and_clears_the_lease(
    store: Storage,
) -> None:
    principals(store, "ann", "bea")
    store.put_connection(connection("ann", "acct-A"), now=T1)
    store.put_connection(connection("bea", "acct-B"), now=T1)
    before = must_get(store, "ann")
    bea_before = must_get(store, "bea")
    assert before.tokens != NEW_TOKENS and before.tokens.refresh is not None
    assert claim(store, "ann", "L-1", until=T5, now=T2)

    assert swap(store, "ann", lease="L-1", now=T3) is True

    after = must_get(store, "ann")
    assert after.tokens == NEW_TOKENS  # a missing refresh token and expiry too
    assert after.generation == 2
    assert (after.lease_id, after.lease_until) == (None, None)
    assert after.updated_at == T3
    assert (after.account_key, after.created_at, after.token_id) == (
        before.account_key,
        before.created_at,
        before.token_id,
    )
    assert must_get(store, "bea") == bea_before
    # The generation moved, so the same claim cannot be made twice.
    assert claim(store, "ann", "L-2", generation=1, until=T6, now=T3) is False
    assert claim(store, "ann", "L-2", generation=2, until=T6, now=T3) is True


@pytest.mark.covers(
    "TargetConnectionStore.swap_tokens", "TargetConnectionStore.claim_refresh"
)
def test_a_stale_swap_is_refused_and_leaves_the_connection_unchanged(
    store: Storage,
) -> None:
    principals(store, "ann")
    store.put_connection(connection("ann", "acct-A"), now=T1)
    assert claim(store, "ann", "L-1", until=T4, now=T2)
    assert swap(store, "ann", lease="L-1", now=T2)  # generation 2
    assert claim(store, "ann", "L-2", generation=2, until=T6, now=T3)
    before = must_get(store, "ann")
    assert before.generation == 2 and before.lease_id == "L-2"
    other = SealedTokens("stale-access", "stale-refresh", T6)

    # The lease is held and named correctly; only the generation is stale.
    assert swap(store, "ann", generation=1, lease="L-2", now=T3, tokens=other) is False
    assert swap(store, "ann", generation=3, lease="L-2", now=T3, tokens=other) is False
    assert must_get(store, "ann") == before

    # Without a lease, a stale generation is refused as well.
    assert claim(store, "ann", "L-3", generation=2, until=T6, now=T6) is True
    assert (
        swap(store, "ann", generation=1, lease=None, now=T6 + 1, tokens=other) is False
    )
    assert must_get(store, "ann").tokens == before.tokens


@pytest.mark.covers(
    "TargetConnectionStore.swap_tokens", "TargetConnectionStore.claim_refresh"
)
def test_a_swap_names_the_holder_unless_it_names_none_while_no_lease_is_live(
    store: Storage,
) -> None:
    principals(store, "ann", "bea")
    store.put_connection(connection("ann", "acct-A"), now=T1)
    store.put_connection(connection("bea", "acct-B"), now=T1)
    assert claim(store, "ann", "L-1", until=T4, now=T2)
    held = must_get(store, "ann")

    # A live lease: another holder's id, no id, and the id of bea's lease fail.
    assert claim(store, "bea", "L-bea", until=T5, now=T2)
    assert swap(store, "ann", lease="L-bea", now=T3) is False
    assert swap(store, "ann", lease=None, now=T3) is False
    assert swap(store, "ann", lease=None, now=T4 - 1) is False
    assert must_get(store, "ann") == held

    # The lease's end frees a swap that names no holder, at the end second.
    assert swap(store, "ann", lease=None, now=T4) is True
    assert must_get(store, "ann").generation == 2
    assert must_get(store, "ann").lease_id is None

    # bea: a swap naming a lease nobody holds is refused; after the release a
    # swap naming the released id is refused, and one naming none works.
    assert swap(store, "bea", lease="L-ghost", generation=1, now=T3) is False
    release(store, "bea", "L-bea")
    assert swap(store, "bea", lease="L-bea", now=T3) is False  # released, so gone
    assert swap(store, "bea", lease=None, now=T3) is True
    assert must_get(store, "bea").generation == 2


@pytest.mark.covers("TargetConnectionStore.swap_tokens")
def test_a_swap_by_the_holder_of_an_expired_lease_still_lands(store: Storage) -> None:
    principals(store, "ann")
    store.put_connection(connection("ann", "acct-A"), now=T1)
    assert claim(store, "ann", "L-1", until=T3, now=T2)
    assert swap(store, "ann", lease="L-1", now=T5) is True
    assert must_get(store, "ann").generation == 2


@pytest.mark.covers("TargetConnectionStore.swap_tokens")
def test_a_swap_on_a_missing_connection_is_false(store: Storage) -> None:
    principals(store, "ann")
    store.put_connection(connection("ann", "acct-A"), now=T1)
    assert swap(store, "bea", lease=None, now=T2) is False
    assert swap(store, "ann", lease=None, now=T2, target=OTHER) is False
    assert must_get(store, "ann").generation == 1


def release(store: Storage, principal_id: str, lease_id: str) -> None:
    return store.release_refresh(principal_id, STRAVA, lease_id=lease_id)


@pytest.mark.covers(
    "TargetConnectionStore.release_refresh", "TargetConnectionStore.claim_refresh"
)
def test_a_release_clears_only_the_holders_lease_and_frees_the_generation(
    store: Storage,
) -> None:
    principals(store, "ann", "bea")
    store.put_connection(connection("ann", "acct-A"), now=T1)
    store.put_connection(connection("bea", "acct-B"), now=T1)
    assert claim(store, "ann", "L-1", until=T6, now=T2)
    assert claim(store, "bea", "L-1", until=T6, now=T2)  # the same id, another row
    held = must_get(store, "ann")

    release(store, "ann", "L-other")  # not the holder
    release(store, "cat", "L-1")  # no such connection
    assert must_get(store, "ann") == held

    release(store, "ann", "L-1")
    freed = must_get(store, "ann")
    assert (freed.lease_id, freed.lease_until) == (None, None)
    assert (freed.generation, freed.tokens, freed.updated_at) == (
        held.generation,
        held.tokens,
        held.updated_at,
    )
    assert lease_of(store, "bea") == ("L-1", T6)  # bea's lease stands
    assert claim(store, "ann", "L-2", until=T6, now=T3) is True  # before L-1's end


@pytest.mark.covers(
    "TargetConnectionStore.release_refresh", "TargetConnectionStore.claim_refresh"
)
def test_a_late_release_does_not_clear_a_newer_holders_lease(store: Storage) -> None:
    principals(store, "ann")
    store.put_connection(connection("ann", "acct-A"), now=T1)
    assert claim(store, "ann", "L-1", until=T3, now=T2)
    assert claim(store, "ann", "L-2", until=T6, now=T4)  # L-1 ran out
    release(store, "ann", "L-1")
    assert lease_of(store, "ann") == ("L-2", T6)


@pytest.mark.covers(
    "TargetConnectionStore.delete_connection",
    "TargetConnectionStore.swap_tokens",
    "TargetConnectionStore.claim_refresh",
)
def test_a_delete_with_a_generation_a_swap_has_passed_changes_nothing(
    database_target: Target, store: Storage
) -> None:
    principals(store, "ann")
    mint(store, "tok-ann", "ann")
    store.put_connection(connection("ann", "acct-A"), now=T1)
    attach_token(database_target, "ann", "tok-ann")
    add_publication(database_target, "pub-a", "ann")
    assert claim(store, "ann", "L-1", until=T5, now=T2)
    assert swap(store, "ann", lease="L-1", now=T3)  # generation 2
    assert claim(store, "ann", "L-2", generation=2, until=T6, now=T3)
    before = must_get(store, "ann")

    assert store.delete_connection("ann", STRAVA, generation=1, now=T4) is False

    assert must_get(store, "ann") == before
    assert publications(database_target) == [(STRAVA, "pub-a", "ann")]
    assert revoked_at(store, "tok-ann") is None
    assert store.delete_connection("ann", STRAVA, generation=2, now=T4) is True
    assert revoked_at(store, "tok-ann") == T4


def test_a_sealed_token_never_appears_in_a_repr() -> None:
    shown = repr(connection("ann", "acct-X", access="SECRET-A", refresh="SECRET-R"))
    assert "SECRET-A" not in shown
    assert "SECRET-R" not in shown
