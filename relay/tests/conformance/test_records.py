"""Namespaced records with an expiry on both backends."""

from __future__ import annotations

import pytest
from tests.conformance.state_support import Target, raw
from tests.conftest import StateStore

from fitdocs_relay.storage.interface import StorageUnreachable

NOW = 1_700_000_000
EXPIRY = NOW + 100


def stored(target: Target) -> list[tuple[str, str, bytes, int]]:
    return [
        (str(n), str(k), bytes(v), int(e))
        for n, k, v, e in raw(
            target,
            "SELECT namespace, key, value, expires_at FROM records "
            "ORDER BY namespace, key",
        )
    ]


def put(
    store: StateStore,
    key: str,
    value: bytes,
    *,
    namespace: str = "wrap",
    expires_at: int = EXPIRY,
    now: int = NOW,
) -> None:
    store.put_record(
        namespace=namespace, key=key, value=value, expires_at=expires_at, now=now
    )


@pytest.mark.covers("RecordStore.put_record", "RecordStore.get_record")
def test_a_record_reads_back_byte_for_byte_and_reading_does_not_consume_it(
    state_store: StateStore,
) -> None:
    value = bytes(range(256)) + b"\x00tail"
    put(state_store, "k", value)
    assert state_store.get_record(namespace="wrap", key="k", now=NOW + 1) == value
    assert state_store.get_record(namespace="wrap", key="k", now=NOW + 2) == value
    assert state_store.get_record(namespace="wrap", key="missing", now=NOW) is None


@pytest.mark.covers("RecordStore.put_record", "RecordStore.get_record")
def test_an_empty_value_is_a_record_and_not_absent(state_store: StateStore) -> None:
    put(state_store, "k", b"")
    value = state_store.get_record(namespace="wrap", key="k", now=NOW)
    assert value == b""
    assert value is not None


@pytest.mark.covers("RecordStore.put_record", "RecordStore.get_record")
def test_namespaces_and_keys_are_separate_and_case_is_significant(
    state_store: StateStore,
) -> None:
    put(state_store, "k", b"one", namespace="alpha")
    put(state_store, "k", b"two", namespace="beta")
    put(state_store, "K", b"three", namespace="alpha")
    get = state_store.get_record
    assert get(namespace="alpha", key="k", now=NOW) == b"one"
    assert get(namespace="beta", key="k", now=NOW) == b"two"
    assert get(namespace="alpha", key="K", now=NOW) == b"three"
    assert get(namespace="beta", key="K", now=NOW) is None
    assert get(namespace="gamma", key="k", now=NOW) is None


@pytest.mark.covers("RecordStore.put_record", "RecordStore.get_record")
def test_putting_an_existing_key_replaces_its_value_and_its_expiry(
    database_target: Target, state_store: StateStore
) -> None:
    put(state_store, "k", b"old", expires_at=NOW + 10)
    put(state_store, "k", b"new", expires_at=NOW + 500, now=NOW + 5)
    assert stored(database_target) == [("wrap", "k", b"new", NOW + 500)]
    # past the old expiry, inside the new one
    assert state_store.get_record(namespace="wrap", key="k", now=NOW + 50) == b"new"


@pytest.mark.covers("RecordStore.get_record")
def test_a_record_is_visible_until_the_instant_it_expires(
    state_store: StateStore,
) -> None:
    put(state_store, "k", b"v")
    get = state_store.get_record
    assert get(namespace="wrap", key="k", now=EXPIRY - 1) == b"v"
    assert get(namespace="wrap", key="k", now=EXPIRY) is None  # now == expires_at
    assert get(namespace="wrap", key="k", now=EXPIRY + 1) is None


@pytest.mark.covers("RecordStore.put_record", "RecordStore.get_record")
def test_put_purges_expired_records_of_every_namespace_and_keeps_live_ones(
    database_target: Target, state_store: StateStore
) -> None:
    later = NOW + 1000
    put(state_store, "gone", b"1", namespace="alpha", expires_at=later - 1)
    put(state_store, "edge", b"2", namespace="beta", expires_at=later)
    put(state_store, "kept", b"3", namespace="beta", expires_at=later + 1)
    # invisible at `later`, yet still stored: the purge has not run
    assert state_store.get_record(namespace="alpha", key="gone", now=later) is None
    assert len(stored(database_target)) == 3

    put(state_store, "fresh", b"4", namespace="gamma", expires_at=later + 50, now=later)

    # an expired record (and one expiring this very second) is removed from storage
    assert stored(database_target) == [
        ("beta", "kept", b"3", later + 1),
        ("gamma", "fresh", b"4", later + 50),
    ]


@pytest.mark.covers("RecordStore.put_record", "RecordStore.get_record")
def test_putting_over_an_expired_record_of_the_same_key_stores_the_new_one(
    database_target: Target, state_store: StateStore
) -> None:
    put(state_store, "k", b"old", expires_at=NOW + 10)
    put(state_store, "k", b"new", expires_at=NOW + 900, now=NOW + 20)
    assert stored(database_target) == [("wrap", "k", b"new", NOW + 900)]
    assert state_store.get_record(namespace="wrap", key="k", now=NOW + 21) == b"new"


@pytest.mark.covers("RecordStore.take_record", "RecordStore.put_record")
def test_take_returns_the_value_once_and_deletes_the_row(
    database_target: Target, state_store: StateStore
) -> None:
    put(state_store, "k", b"secret")
    put(state_store, "other", b"stays")
    assert len(stored(database_target)) == 2

    first = state_store.take_record(namespace="wrap", key="k", now=NOW + 1)
    second = state_store.take_record(namespace="wrap", key="k", now=NOW + 1)

    assert first == b"secret"
    assert second is None
    assert state_store.get_record(namespace="wrap", key="k", now=NOW + 1) is None
    assert stored(database_target) == [("wrap", "other", b"stays", EXPIRY)]


@pytest.mark.covers("RecordStore.take_record")
def test_take_of_a_missing_key_or_namespace_is_none(state_store: StateStore) -> None:
    put(state_store, "k", b"v", namespace="alpha")
    assert state_store.take_record(namespace="alpha", key="nope", now=NOW) is None
    assert state_store.take_record(namespace="beta", key="k", now=NOW) is None
    assert state_store.get_record(namespace="alpha", key="k", now=NOW) == b"v"


@pytest.mark.covers("RecordStore.take_record", "RecordStore.put_record")
def test_take_answers_none_for_an_expired_record_from_the_instant_it_expires(
    state_store: StateStore,
) -> None:
    put(state_store, "live", b"v")
    put(state_store, "dead", b"v")
    take = state_store.take_record
    assert take(namespace="wrap", key="live", now=EXPIRY - 1) == b"v"
    assert take(namespace="wrap", key="dead", now=EXPIRY) is None


@pytest.mark.covers("RecordStore.delete_record", "RecordStore.put_record")
def test_delete_removes_one_record_and_says_whether_there_was_one(
    database_target: Target, state_store: StateStore
) -> None:
    put(state_store, "k", b"1", namespace="alpha")
    put(state_store, "k", b"2", namespace="beta")
    put(state_store, "j", b"3", namespace="alpha")

    assert state_store.delete_record(namespace="alpha", key="k") is True
    assert state_store.delete_record(namespace="alpha", key="k") is False
    assert state_store.delete_record(namespace="gamma", key="k") is False

    assert stored(database_target) == [
        ("alpha", "j", b"3", EXPIRY),
        ("beta", "k", b"2", EXPIRY),
    ]
    assert state_store.get_record(namespace="alpha", key="k", now=NOW) is None


@pytest.mark.covers(
    "RecordStore.put_record",
    "RecordStore.get_record",
    "RecordStore.take_record",
    "RecordStore.delete_record",
)
def test_every_record_operation_on_a_closed_store_is_unreachable(
    state_store: StateStore,
) -> None:
    state_store.close()
    with pytest.raises(StorageUnreachable):
        put(state_store, "k", b"v")
    with pytest.raises(StorageUnreachable):
        state_store.get_record(namespace="wrap", key="k", now=NOW)
    with pytest.raises(StorageUnreachable):
        state_store.take_record(namespace="wrap", key="k", now=NOW)
    with pytest.raises(StorageUnreachable):
        state_store.delete_record(namespace="wrap", key="k")
