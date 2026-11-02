"""Link records on both backends: put for the owner only, get, and their removal."""

from __future__ import annotations

from collections.abc import Callable

import pytest
from tests.conformance.state_support import Target, raw
from tests.conformance.test_connections import (
    OTHER,
    STRAVA,
    T1,
    T2,
    T3,
    T4,
    attach_token,
    connection,
    mint,
    principals,
    revoked_at,
)

from fitdocs_relay.storage.interface import Publication, Storage, UnknownPrincipal


@pytest.fixture
def store(open_full_storage: Callable[[], Storage]) -> Storage:
    return open_full_storage()


def publication(
    publication_id: str,
    principal_id: str,
    *,
    target: str = STRAVA,
    sport: str = "run",
    start_s: float = 1_700_000_000.25,
    elapsed_s: float | None = 1800.5,
    distance_m: float | None = 5000.75,
) -> Publication:
    return Publication(
        target, publication_id, principal_id, sport, start_s, elapsed_s, distance_m
    )


def stored_ids(target: Target) -> list[tuple[str, str, str]]:
    return [
        (str(t), str(p), str(o))
        for t, p, o in raw(
            target,
            "SELECT target, publication_id, principal_id FROM target_publications "
            "ORDER BY target, publication_id",
        )
    ]


def stamps(target: Target, publication_id: str) -> tuple[int, int]:
    rows = raw(
        target,
        "SELECT created_at, updated_at FROM target_publications "
        "WHERE publication_id = ?",
        (publication_id,),
    )
    assert len(rows) == 1
    return int(rows[0][0]), int(rows[0][1])


def put_all(store: Storage, *records: Publication, now: int = T2) -> None:
    for record in records:
        assert store.put_publication(record, now=now) is True


@pytest.mark.covers(
    "PublicationStore.put_publication", "PublicationStore.get_publication"
)
def test_a_record_reads_back_whole_by_target_and_id(store: Storage) -> None:
    principals(store, "ann", "bea")
    full = publication("pub-1", "ann")
    bare = publication(
        "pub-2",
        "ann",
        sport="ride",
        start_s=1_600_000_000.5,
        elapsed_s=None,
        distance_m=None,
    )
    assert store.get_publication(STRAVA, "pub-1") is None
    put_all(store, full, bare)
    assert store.get_publication(STRAVA, "pub-1") == full
    assert store.get_publication(STRAVA, "pub-2") == bare
    assert store.get_publication(STRAVA, "pub-3") is None


@pytest.mark.covers(
    "PublicationStore.put_publication", "PublicationStore.get_publication"
)
def test_the_target_is_part_of_the_key_in_a_put_and_in_a_get(
    database_target: Target, store: Storage
) -> None:
    principals(store, "ann", "bea")
    on_strava = publication("pub-1", "ann", sport="run", distance_m=111.5)
    on_other = publication(
        "pub-1", "bea", target=OTHER, sport="ride", distance_m=222.5, elapsed_s=None
    )
    put_all(store, on_strava, on_other)  # same id, two targets, two owners

    assert stored_ids(database_target) == [
        (OTHER, "pub-1", "bea"),
        (STRAVA, "pub-1", "ann"),
    ]
    assert store.get_publication(STRAVA, "pub-1") == on_strava
    assert store.get_publication(OTHER, "pub-1") == on_other
    assert store.get_publication("nothing", "pub-1") is None


@pytest.mark.covers("PublicationStore.put_publication")
def test_another_principals_put_of_the_id_is_refused_and_changes_nothing(
    database_target: Target, store: Storage
) -> None:
    principals(store, "ann", "bea")
    owned = publication("pub-1", "ann")
    put_all(store, owned, now=T2)
    before = stamps(database_target, "pub-1")
    assert before == (T2, T2)

    thief = publication(
        "pub-1", "bea", sport="swim", start_s=1.5, elapsed_s=9.5, distance_m=8.5
    )
    assert store.put_publication(thief, now=T4) is False

    assert store.get_publication(STRAVA, "pub-1") == owned
    assert stamps(database_target, "pub-1") == before
    assert stored_ids(database_target) == [(STRAVA, "pub-1", "ann")]


@pytest.mark.covers(
    "PublicationStore.put_publication", "PublicationStore.get_publication"
)
def test_the_owners_put_updates_every_field_and_keeps_the_creation_time(
    database_target: Target, store: Storage
) -> None:
    principals(store, "ann")
    put_all(store, publication("pub-1", "ann"), now=T2)
    assert stamps(database_target, "pub-1") == (T2, T2)

    changed = publication(
        "pub-1",
        "ann",
        sport="ride",
        start_s=1_650_000_000.5,
        elapsed_s=None,
        distance_m=None,
    )
    assert store.put_publication(changed, now=T4) is True

    assert store.get_publication(STRAVA, "pub-1") == changed
    assert stamps(database_target, "pub-1") == (T2, T4)
    assert raw(database_target, "SELECT count(*) FROM target_publications") == [(1,)]


@pytest.mark.covers("PublicationStore.put_publication")
def test_a_put_for_an_unknown_principal_is_refused_and_stores_nothing(
    database_target: Target, store: Storage
) -> None:
    principals(store, "ann")  # a principal exists, so "ghost" is not the only absence
    with pytest.raises(UnknownPrincipal):
        store.put_publication(publication("pub-1", "ghost"), now=T2)
    assert raw(database_target, "SELECT count(*) FROM target_publications") == [(0,)]


@pytest.mark.covers(
    "PublicationStore.put_publication",
    "PrincipalStore.delete_principal",
)
def test_deleting_a_principal_removes_its_link_records_and_only_those(
    database_target: Target, store: Storage
) -> None:
    principals(store, "ann", "bea")
    put_all(
        store,
        publication("pub-a", "ann"),
        publication("pub-a2", "ann", target=OTHER),
        publication("pub-b", "bea"),
    )
    assert len(stored_ids(database_target)) == 3

    assert store.delete_principal("ann") is True

    assert stored_ids(database_target) == [(STRAVA, "pub-b", "bea")]


def seed_two_owners(database_target: Target, store: Storage) -> None:
    principals(store, "ann", "bea")
    mint(store, "tok-ann", "ann")
    store.put_connection(connection("ann", "acct-X"), now=T1)
    store.put_connection(connection("ann", "acct-X", target=OTHER), now=T1)
    store.put_connection(connection("bea", "acct-B"), now=T1)
    attach_token(database_target, "ann", "tok-ann")
    put_all(
        store,
        publication("pub-a", "ann"),
        publication("pub-a2", "ann", target=OTHER),
        publication("pub-b", "bea"),
    )
    assert len(stored_ids(database_target)) == 3  # the records are present


@pytest.mark.covers(
    "PublicationStore.put_publication", "TargetConnectionStore.delete_connection"
)
def test_deleting_a_connection_removes_its_link_records_only(
    database_target: Target, store: Storage
) -> None:
    seed_two_owners(database_target, store)

    assert store.delete_connection("ann", STRAVA, generation=None, now=T3) is True

    assert stored_ids(database_target) == [
        (OTHER, "pub-a2", "ann"),
        (STRAVA, "pub-b", "bea"),
    ]
    assert revoked_at(store, "tok-ann") == T3


@pytest.mark.covers(
    "PublicationStore.put_publication",
    "TargetConnectionStore.delete_connection_by_account",
)
def test_deleting_a_connection_by_account_removes_its_link_records_only(
    database_target: Target, store: Storage
) -> None:
    seed_two_owners(database_target, store)

    assert store.delete_connection_by_account(STRAVA, "acct-X", now=T3) is True

    assert stored_ids(database_target) == [
        (OTHER, "pub-a2", "ann"),
        (STRAVA, "pub-b", "bea"),
    ]


@pytest.mark.covers(
    "PublicationStore.put_publication", "TargetConnectionStore.put_connection"
)
def test_a_displacing_put_of_the_same_account_removes_the_displaced_link_records(
    database_target: Target, store: Storage
) -> None:
    seed_two_owners(database_target, store)
    principals(store, "cy")

    store.put_connection(connection("cy", "acct-X"), now=T3)  # ann's account

    assert store.get_connection("ann", STRAVA) is None
    assert stored_ids(database_target) == [
        (OTHER, "pub-a2", "ann"),
        (STRAVA, "pub-b", "bea"),
    ]


@pytest.mark.covers(
    "PublicationStore.put_publication", "TargetConnectionStore.put_connection"
)
def test_a_changed_account_removes_the_principals_link_records_for_the_target(
    database_target: Target, store: Storage
) -> None:
    seed_two_owners(database_target, store)

    store.put_connection(connection("ann", "acct-X", access="again"), now=T3)
    assert len(stored_ids(database_target)) == 3  # the same account keeps all

    store.put_connection(connection("ann", "acct-Z"), now=T4)

    assert stored_ids(database_target) == [
        (OTHER, "pub-a2", "ann"),
        (STRAVA, "pub-b", "bea"),
    ]
    assert store.get_publication(STRAVA, "pub-a") is None
    assert store.get_publication(OTHER, "pub-a2") is not None
