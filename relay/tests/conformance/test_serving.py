"""The single-serving-instance claim on both backends."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
import uuid
from collections.abc import Callable, Iterator
from contextlib import contextmanager

import pytest
from tests.conformance.state_support import Target, raw
from tests.conftest import StateStore

from fitdocs_relay.config import PostgresTarget, SqliteTarget
from fitdocs_relay.storage.interface import ServingClaim, StorageUnreachable

Opener = Callable[[Target | None], StateStore]


def claim(store: StateStore) -> ServingClaim:
    held = store.claim_serving()
    assert held is not None, "the claim was refused"
    return held


@pytest.mark.covers("ServingStore.claim_serving")
def test_a_second_claim_on_the_same_object_is_refused_while_one_is_held(
    state_store: StateStore,
) -> None:
    held = claim(state_store)
    assert state_store.claim_serving() is None
    assert state_store.claim_serving() is None
    held.release()
    again = claim(state_store)
    again.release()


@pytest.mark.covers("ServingStore.claim_serving")
def test_a_separate_storage_object_on_the_same_database_is_refused(
    open_state_store: Opener,
) -> None:
    first = open_state_store(None)
    second = open_state_store(None)
    assert first is not second

    held = claim(first)

    assert second.claim_serving() is None
    held.release()


@pytest.mark.covers("ServingStore.claim_serving")
def test_release_then_reclaim_succeeds_from_another_object_and_then_refuses_the_first(
    open_state_store: Opener,
) -> None:
    first = open_state_store(None)
    second = open_state_store(None)

    claim(first).release()
    held = claim(second)  # the release freed it

    assert first.claim_serving() is None  # and second now holds it
    held.release()


@pytest.mark.covers("ServingStore.claim_serving")
def test_releasing_twice_does_not_free_a_later_holders_claim(
    open_state_store: Opener,
) -> None:
    first = open_state_store(None)
    second = open_state_store(None)
    third = open_state_store(None)

    stale = claim(first)
    stale.release()
    held = claim(second)

    stale.release()  # a no-op: it no longer holds anything

    assert third.claim_serving() is None
    held.release()


@pytest.mark.covers("ServingStore.claim_serving")
def test_a_claim_is_per_database(
    second_database_target: Target, open_state_store: Opener
) -> None:
    here = open_state_store(None)
    there = open_state_store(second_database_target)

    held_here = claim(here)
    held_there = claim(there)  # a different database: not refused

    held_here.release()
    held_there.release()


@pytest.mark.covers("ServingStore.claim_serving", "RecordStore.put_record")
def test_holding_the_claim_does_not_block_storage_operations(
    state_store: StateStore,
) -> None:
    held = claim(state_store)

    state_store.put_record(namespace="n", key="k", value=b"v", expires_at=10, now=1)
    assert state_store.get_record(namespace="n", key="k", now=2) == b"v"
    state_store.ping()

    held.release()


@pytest.mark.covers("ServingStore.claim_serving")
def test_claiming_on_a_closed_store_is_unreachable(state_store: StateStore) -> None:
    state_store.close()
    with pytest.raises(StorageUnreachable):
        state_store.claim_serving()


@pytest.mark.covers("ServingStore.claim_serving")
def test_sqlite_locks_a_sidecar_file_named_for_the_database(
    database_target: Target, state_store: StateStore
) -> None:
    if not isinstance(database_target, SqliteTarget):
        pytest.skip("the sidecar lock file is the SQLite backend's")
    sidecar = database_target.path.with_name(database_target.path.name + ".serve-lock")
    assert not sidecar.exists()

    held = claim(state_store)

    assert sidecar.is_file()
    assert sidecar.stat().st_mode & 0o777 == 0o600
    held.release()


def _lock_holder_sessions(database_target: PostgresTarget) -> list[int]:
    return [
        int(pid)
        for (pid,) in raw(
            database_target,
            # this database, this schema's key (design: hashtext of the prefix
            # and the schema); a bigint key is classid (high) and objid (low)
            "SELECT pid FROM pg_locks WHERE locktype = 'advisory' AND granted "
            "AND objsubid = 1 "
            "AND database = (SELECT oid FROM pg_database "
            "WHERE datname = current_database()) "
            "AND ((classid::bigint << 32) | objid::bigint) "
            "= hashtext('fitdocs-relay:' || current_schema())::bigint",
        )
    ]


def _session_ids(database_target: PostgresTarget) -> set[int]:
    return {
        int(pid)
        for (pid,) in raw(
            database_target,
            "SELECT pid FROM pg_stat_activity WHERE datname = current_database()",
        )
    }


@pytest.mark.covers("ServingStore.claim_serving")
def test_postgres_holds_one_advisory_lock_on_a_session_that_release_closes(
    database_target: Target, state_store: StateStore
) -> None:
    if not isinstance(database_target, PostgresTarget):
        pytest.skip("advisory locks are the PostgreSQL backend's")
    assert _lock_holder_sessions(database_target) == []

    held = claim(state_store)

    holders = _lock_holder_sessions(database_target)
    assert len(holders) == 1
    assert holders[0] in _session_ids(database_target)

    held.release()

    assert _lock_holder_sessions(database_target) == []
    # the lock's session is gone from the server, not left open
    assert holders[0] not in _session_ids(database_target)


CHILD = """
import json, sys
from fitdocs_relay.config import PostgresTarget, SqliteTarget

spec = json.loads(sys.argv[1])
if spec["kind"] == "sqlite":
    from pathlib import Path
    from fitdocs_relay.storage.sqlite import SqliteBackend
    store = SqliteBackend(SqliteTarget(path=Path(spec["path"])))
else:
    from fitdocs_relay.storage.postgres import PostgresBackend
    store = PostgresBackend(PostgresTarget(conninfo=spec["conninfo"], password=None))
held = store.claim_serving()
print("claimed" if held is not None else "refused", flush=True)
sys.stdin.readline()
"""


@contextmanager
def _holder_process(database_target: Target) -> Iterator[subprocess.Popen[str]]:
    if isinstance(database_target, SqliteTarget):
        spec = {"kind": "sqlite", "path": str(database_target.path)}
    else:
        spec = {"kind": "postgres", "conninfo": database_target.conninfo}
    env = {k: v for k, v in os.environ.items() if not k.startswith("FITDOCS_RELAY_")}
    child = subprocess.Popen(
        [sys.executable, "-I", "-B", "-c", CHILD, json.dumps(spec)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
        env=env,
    )
    try:
        assert child.stdout is not None
        timer = threading.Timer(30, child.kill)  # a hung child ends the read
        timer.start()
        try:
            first_line = child.stdout.readline().strip()
        finally:
            timer.cancel()
        assert first_line == "claimed"
        yield child
    finally:
        child.kill()
        child.wait()
        if child.stdin is not None:
            child.stdin.close()
        if child.stdout is not None:
            child.stdout.close()


@pytest.mark.covers("ServingStore.claim_serving")
def test_a_claim_held_by_another_process_is_refused_and_dies_with_that_process(
    database_target: Target, state_store: StateStore
) -> None:
    with _holder_process(database_target) as child:
        assert state_store.claim_serving() is None
        child.kill()
        child.wait()
        deadline = time.monotonic() + 10
        reclaimed = state_store.claim_serving()
        while reclaimed is None and time.monotonic() < deadline:
            time.sleep(0.05)
            reclaimed = state_store.claim_serving()
        assert reclaimed is not None, "a dead process's claim was never freed"
        reclaimed.release()


def _schema_named_with_key_sign(admin: object, negative: bool) -> str:
    """A fresh schema name whose claim key has the wanted sign on this server."""
    import psycopg

    assert isinstance(admin, psycopg.Connection)
    for _ in range(200):
        name = f"relay_key_{uuid.uuid4().hex[:12]}"
        row = admin.execute(
            "SELECT hashtext('fitdocs-relay:' || %s)", (name,)
        ).fetchone()
        assert row is not None
        if (row[0] < 0) == negative:
            admin.execute(
                psycopg.sql.SQL("CREATE SCHEMA {}").format(psycopg.sql.Identifier(name))
            )
            return name
    raise AssertionError("no schema name with the wanted key sign was found")


@pytest.mark.covers("ServingStore.claim_serving")
@pytest.mark.parametrize(
    "negative", [True, False], ids=["negative-key", "positive-key"]
)
def test_postgres_claim_key_is_found_for_negative_and_positive_hash_values(
    negative: bool,
    database_target: Target,
    postgres_test_url: str,
) -> None:
    if not isinstance(database_target, PostgresTarget):
        pytest.skip("advisory locks are the PostgreSQL backend's")
    import psycopg
    import psycopg.sql
    from psycopg.conninfo import make_conninfo

    from fitdocs_relay.storage.postgres import PostgresBackend

    with psycopg.connect(postgres_test_url, autocommit=True) as admin:
        name = _schema_named_with_key_sign(admin, negative)
        try:
            target = PostgresTarget(
                conninfo=make_conninfo(
                    postgres_test_url, options=f"-csearch_path={name}"
                ),
                password=None,
            )
            key = admin.execute(
                "SELECT hashtext('fitdocs-relay:' || %s)", (name,)
            ).fetchone()
            assert key is not None
            assert (key[0] < 0) is negative  # the precondition, on the live server
            store = PostgresBackend(target)
            try:
                held = claim(store)
                try:
                    assert len(_lock_holder_sessions(target)) == 1
                finally:
                    held.release()
                assert _lock_holder_sessions(target) == []
            finally:
                store.close()
        finally:
            admin.execute(
                psycopg.sql.SQL("DROP SCHEMA {} CASCADE").format(
                    psycopg.sql.Identifier(name)
                )
            )
