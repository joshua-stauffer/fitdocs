"""The PostgreSQL backend (the only module that imports the PostgreSQL driver)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Literal, TypeVar

import psycopg
import psycopg_pool

from fitdocs_relay.config import PostgresTarget
from fitdocs_relay.storage.interface import (
    SchemaChange,
    SchemaState,
    StorageError,
    StorageUnreachable,
)
from fitdocs_relay.storage.migrate import schema_changes

POOL_MIN = 1
POOL_MAX = 8
POOL_TIMEOUT_S = 10.0

# Taken with `pg_advisory_xact_lock` while a schema change is applied: the
# transaction-scoped writer lock, released at commit or rollback.
SCHEMA_LOCK_KEY = 0x6669_7472_656C_6179  # b"fitrelay"

# Fixed texts: the driver's own message is never carried (it can name hosts,
# users, and the values in a statement).
_UNREACHABLE = "the PostgreSQL database cannot be reached"
_FAILED = "the PostgreSQL database reported an error"

_T = TypeVar("_T")


# SQLSTATEs that mean the server could not be reached or refused the session:
# class 08 (connection exception), class 28 (authorization, at connect),
# 57P01-57P03 (admin shutdown, crash shutdown, cannot connect now) and 53300
# (too many connections). A driver error without a SQLSTATE came from the
# client library: resolution, refusal, timeout, or a connection lost
# mid-statement.
_CONNECTION_STATES = frozenset({"57P01", "57P02", "57P03", "53300"})
_CONNECTION_CLASSES = ("08", "28")


def is_connection_failure(error: psycopg.Error) -> bool:
    """Whether `error` is a genuine connection failure, not a failed statement.

    Deadlocks, serialization failures, cancelled statements, lock timeouts,
    a full disk and out-of-memory are `OperationalError` subclasses too, but
    they are statement failures and stay `StorageError`. The pool's closed and
    timed-out errors are `OperationalError`s without a SQLSTATE, so they count
    as connection failures through the first rule.
    """
    if not isinstance(error, psycopg.OperationalError):
        return False
    state = error.sqlstate
    return (
        state is None
        or state in _CONNECTION_STATES
        or state.startswith(_CONNECTION_CLASSES)
    )


def _guarded(work: Callable[[], _T]) -> _T:
    """Run driver work; translate its errors outside the `except`, so none chains."""
    failure: type[StorageError] | None = None
    try:
        return work()
    except psycopg.Error as error:
        failure = StorageUnreachable if is_connection_failure(error) else StorageError
    assert failure is not None
    raise failure(_UNREACHABLE if failure is StorageUnreachable else _FAILED)


class PostgresBackend:
    """Storage on PostgreSQL: a capped connection pool."""

    def __init__(self, target: PostgresTarget) -> None:
        kwargs: dict[str, object] = {}
        if target.password is not None:
            kwargs["password"] = target.password
        self._closed = False
        # A single connection first: an unreachable server fails here, once,
        # instead of the pool retrying (and logging) in the background.
        _guarded(lambda: psycopg.connect(target.conninfo, **kwargs).close())  # type: ignore[arg-type]
        self._pool = psycopg_pool.ConnectionPool(
            target.conninfo,
            min_size=POOL_MIN,
            max_size=POOL_MAX,
            kwargs=kwargs,
            timeout=POOL_TIMEOUT_S,
            open=False,
        )
        try:
            _guarded(lambda: self._pool.open(wait=True, timeout=POOL_TIMEOUT_S))
        except StorageError:
            self._pool.close()
            raise

    # --- StorageBase ---------------------------------------------------------

    @property
    def backend(self) -> Literal["postgres"]:
        return "postgres"

    def ping(self) -> None:
        self._check_open()

        def work() -> None:
            with self._pool.connection() as connection:
                connection.execute("SELECT 1")

        _guarded(work)

    def close(self) -> None:
        self._closed = True
        _guarded(self._pool.close)

    # --- SchemaStore ---------------------------------------------------------

    def schema_state(self) -> SchemaState:
        self._check_open()

        def work() -> int:
            with self._pool.connection() as connection:
                return self._current_version(connection)

        current = _guarded(work)
        return SchemaState(current=current, expected=len(schema_changes(self.backend)))

    def apply_schema_change(self, change: SchemaChange, *, now: int) -> bool:
        self._check_open()

        def work() -> bool | None:
            # One transaction: the lock, the re-read, the change and its
            # version row commit together or not at all.
            with self._pool.connection() as connection:
                connection.execute(
                    "SELECT pg_advisory_xact_lock(%s)", (SCHEMA_LOCK_KEY,)
                )
                current = self._current_version(connection)
                if change.version <= current:
                    return False
                if change.version != current + 1:
                    return None
                connection.execute(change.sql)
                connection.execute(
                    "INSERT INTO relay_schema (version, name, applied_at) "
                    "VALUES (%s, %s, %s)",
                    (change.version, change.name, now),
                )
                return True

        applied = _guarded(work)
        if applied is None:
            raise StorageError("schema change applied out of order")
        return applied

    # --- internals -----------------------------------------------------------

    def _check_open(self) -> None:
        if self._closed:
            raise StorageUnreachable(_UNREACHABLE)

    @staticmethod
    def _current_version(connection: psycopg.Connection[tuple[object, ...]]) -> int:
        # Not `to_regclass`: after waiting on the advisory lock, a transaction
        # that began before the winner committed still answers "no such table"
        # from its catalog cache (the lock is not a relation lock, so pending
        # invalidations are not processed). A scan of `pg_tables` reads the
        # committed catalog rows.
        row = connection.execute(
            "SELECT EXISTS (SELECT 1 FROM pg_catalog.pg_tables "
            "WHERE schemaname = current_schema() AND tablename = 'relay_schema')"
        ).fetchone()
        if row is None or not row[0]:
            return 0
        row = connection.execute(
            "SELECT COALESCE(MAX(version), 0) FROM relay_schema"
        ).fetchone()
        assert row is not None
        version: int = row[0]  # type: ignore[assignment]
        return version
