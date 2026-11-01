"""The PostgreSQL backend (the only module that imports the PostgreSQL driver)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Literal, TypeVar

import psycopg
import psycopg_pool

from fitdocs_relay.config import PostgresTarget
from fitdocs_relay.storage.interface import (
    DuplicateIdentifier,
    NewPrincipal,
    NewToken,
    Principal,
    RateDecision,
    RevokeResult,
    SchemaChange,
    SchemaState,
    ServingClaim,
    StorageError,
    StorageUnreachable,
    TokenRecord,
    TokenSummary,
    UnknownPrincipal,
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


class _PostgresClaim:
    """The serving claim: a session advisory lock on its own connection.

    The lock lives as long as the session, so closing the connection (or the
    process dying) frees it, and a second `release` finds nothing to close.
    """

    def __init__(self, connection: psycopg.Connection[tuple[object, ...]]) -> None:
        self._connection: psycopg.Connection[tuple[object, ...]] | None = connection

    def release(self) -> None:
        connection, self._connection = self._connection, None
        if connection is not None:
            _guarded(connection.close)


class PostgresBackend:
    """Storage on PostgreSQL: a capped connection pool."""

    def __init__(self, target: PostgresTarget) -> None:
        kwargs: dict[str, object] = {}
        if target.password is not None:
            kwargs["password"] = target.password
        self._closed = False
        self._conninfo = target.conninfo
        self._kwargs = kwargs
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

    # --- PrincipalStore ------------------------------------------------------

    def create_principal(self, principal: NewPrincipal, *, now: int) -> Principal:
        self._check_open()

        def work() -> None:
            with self._pool.connection() as connection:
                self._insert_principal(connection, principal, now)

        _guarded(work)
        return Principal(principal.principal_id, principal.label, now)

    def get_principal(self, principal_id: str) -> Principal | None:
        self._check_open()

        def work() -> tuple[object, ...] | None:
            with self._pool.connection() as connection:
                return connection.execute(
                    "SELECT principal_id, label, created_at FROM principals "
                    "WHERE principal_id = %s",
                    (principal_id,),
                ).fetchone()

        row = _guarded(work)
        return Principal(*row) if row else None  # type: ignore[arg-type]

    def list_principals(self) -> tuple[Principal, ...]:
        self._check_open()

        def work() -> list[tuple[object, ...]]:
            with self._pool.connection() as connection:
                return connection.execute(
                    "SELECT principal_id, label, created_at FROM principals "
                    # "C": byte order, as SQLite's BINARY; the database default
                    # collation would order ids by locale.
                    'ORDER BY created_at, principal_id COLLATE "C"'
                ).fetchall()

        return tuple(Principal(*row) for row in _guarded(work))  # type: ignore[arg-type]

    def delete_principal(self, principal_id: str) -> bool:
        self._check_open()

        def work() -> bool:
            # The tokens go with it: ON DELETE CASCADE, in this one transaction.
            with self._pool.connection() as connection:
                cursor = connection.execute(
                    "DELETE FROM principals WHERE principal_id = %s "
                    "RETURNING principal_id",
                    (principal_id,),
                )
                return cursor.fetchone() is not None

        return _guarded(work)

    # --- TokenStore ----------------------------------------------------------

    def mint_token(
        self,
        token: NewToken,
        *,
        principal_id: str | None,
        new_principal: NewPrincipal | None,
        now: int,
    ) -> TokenRecord:
        if (principal_id is None) == (new_principal is None):
            raise ValueError("exactly one of principal_id and new_principal is given")
        self._check_open()

        def work() -> str:
            with self._pool.connection() as connection:
                if new_principal is not None:
                    self._insert_principal(connection, new_principal, now)
                    owner = new_principal.principal_id
                else:
                    assert principal_id is not None
                    # FOR UPDATE: a concurrent delete waits for this mint.
                    row = connection.execute(
                        "SELECT principal_id FROM principals "
                        "WHERE principal_id = %s FOR UPDATE",
                        (principal_id,),
                    ).fetchone()
                    if row is None:
                        raise UnknownPrincipal("the principal does not exist")
                    owner = principal_id
                inserted = connection.execute(
                    "INSERT INTO tokens (token_id, principal_id, verifier, label, "
                    "created_at, revoked_at) VALUES (%s, %s, %s, %s, %s, NULL) "
                    "ON CONFLICT (token_id) DO NOTHING RETURNING token_id",
                    (token.token_id, owner, token.verifier, token.label, now),
                ).fetchone()
                if inserted is None:
                    raise DuplicateIdentifier("the token identifier already exists")
                return owner

        owner = _guarded(work)
        return TokenRecord(
            token_id=token.token_id,
            principal_id=owner,
            verifier=token.verifier,
            label=token.label,
            created_at=now,
            revoked_at=None,
        )

    def find_token(self, token_id: str) -> TokenRecord | None:
        self._check_open()

        def work() -> tuple[object, ...] | None:
            with self._pool.connection() as connection:
                return connection.execute(
                    "SELECT token_id, principal_id, verifier, label, created_at, "
                    "revoked_at FROM tokens WHERE token_id = %s",
                    (token_id,),
                ).fetchone()

        row = _guarded(work)
        return TokenRecord(*row) if row else None  # type: ignore[arg-type]

    def list_tokens(self, principal_id: str | None) -> tuple[TokenSummary, ...]:
        self._check_open()
        sql = "SELECT token_id, principal_id, label, created_at, revoked_at FROM tokens"
        params: tuple[object, ...] = ()
        if principal_id is not None:
            sql += " WHERE principal_id = %s"
            params = (principal_id,)
        sql += ' ORDER BY created_at, token_id COLLATE "C"'

        def work() -> list[tuple[object, ...]]:
            with self._pool.connection() as connection:
                return connection.execute(sql, params).fetchall()

        return tuple(TokenSummary(*row) for row in _guarded(work))  # type: ignore[arg-type]

    def revoke_token(self, token_id: str, *, now: int) -> RevokeResult:
        self._check_open()

        def work() -> RevokeResult:
            with self._pool.connection() as connection:
                row = connection.execute(
                    "SELECT revoked_at FROM tokens WHERE token_id = %s FOR UPDATE",
                    (token_id,),
                ).fetchone()
                if row is None:
                    return RevokeResult.UNKNOWN
                if row[0] is not None:
                    return RevokeResult.ALREADY_REVOKED
                connection.execute(
                    "UPDATE tokens SET revoked_at = %s WHERE token_id = %s",
                    (now, token_id),
                )
                return RevokeResult.REVOKED

        return _guarded(work)

    # --- RateLimitStore ------------------------------------------------------

    def count_request(
        self, *, key: str, window_s: int, limit: int, now: int
    ) -> RateDecision:
        self._check_open()
        window_start = now - now % window_s
        window_end = window_start + window_s

        def work() -> int:
            with self._pool.connection() as connection:
                # A window that has ended (window_end <= now) is deleted; the
                # current one, and every other key's current one, is kept.
                connection.execute(
                    "DELETE FROM rate_counts WHERE window_end <= %s", (now,)
                )
                row = connection.execute(
                    "INSERT INTO rate_counts (key, window_start, count, window_end) "
                    "VALUES (%s, %s, 1, %s) "
                    "ON CONFLICT (key, window_start) "
                    "DO UPDATE SET count = rate_counts.count + 1 RETURNING count",
                    (key, window_start, window_end),
                ).fetchone()
                assert row is not None
                count: int = row[0]
                return count

        count = _guarded(work)
        if count <= limit:
            return RateDecision(allowed=True, count=count, retry_after_s=None)
        return RateDecision(allowed=False, count=count, retry_after_s=window_end - now)

    # --- RecordStore ---------------------------------------------------------

    def put_record(
        self, *, namespace: str, key: str, value: bytes, expires_at: int, now: int
    ) -> None:
        self._check_open()

        def work() -> None:
            with self._pool.connection() as connection:
                connection.execute("DELETE FROM records WHERE expires_at <= %s", (now,))
                connection.execute(
                    "INSERT INTO records (namespace, key, value, expires_at) "
                    "VALUES (%s, %s, %s, %s) ON CONFLICT (namespace, key) DO UPDATE "
                    "SET value = excluded.value, expires_at = excluded.expires_at",
                    (namespace, key, value, expires_at),
                )

        _guarded(work)

    def get_record(self, *, namespace: str, key: str, now: int) -> bytes | None:
        self._check_open()

        def work() -> tuple[object, ...] | None:
            with self._pool.connection() as connection:
                return connection.execute(
                    "SELECT value FROM records "
                    "WHERE namespace = %s AND key = %s AND expires_at > %s",
                    (namespace, key, now),
                ).fetchone()

        row = _guarded(work)
        return bytes(row[0]) if row else None  # type: ignore[call-overload]

    def take_record(self, *, namespace: str, key: str, now: int) -> bytes | None:
        self._check_open()

        def work() -> tuple[object, ...] | None:
            with self._pool.connection() as connection:
                return connection.execute(
                    "DELETE FROM records WHERE namespace = %s AND key = %s "
                    "AND expires_at > %s RETURNING value",
                    (namespace, key, now),
                ).fetchone()

        row = _guarded(work)
        return bytes(row[0]) if row else None  # type: ignore[call-overload]

    def delete_record(self, *, namespace: str, key: str) -> bool:
        self._check_open()

        def work() -> bool:
            with self._pool.connection() as connection:
                return (
                    connection.execute(
                        "DELETE FROM records WHERE namespace = %s AND key = %s "
                        "RETURNING key",
                        (namespace, key),
                    ).fetchone()
                    is not None
                )

        return _guarded(work)

    # --- ServingStore --------------------------------------------------------

    def claim_serving(self) -> ServingClaim | None:
        self._check_open()

        def work() -> ServingClaim | None:
            # Its own connection, not the pool's: the session holds the lock.
            connection = psycopg.connect(
                self._conninfo,
                autocommit=True,
                **self._kwargs,  # type: ignore[arg-type]
            )
            try:
                row = connection.execute(
                    "SELECT pg_try_advisory_lock("
                    "hashtext('fitdocs-relay:' || current_schema()))"
                ).fetchone()
            except BaseException:
                connection.close()
                raise
            if row is not None and row[0]:
                return _PostgresClaim(connection)
            connection.close()
            return None

        return _guarded(work)

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
    def _insert_principal(
        connection: psycopg.Connection[tuple[object, ...]],
        principal: NewPrincipal,
        now: int,
    ) -> None:
        inserted = connection.execute(
            "INSERT INTO principals (principal_id, label, created_at) "
            "VALUES (%s, %s, %s) ON CONFLICT (principal_id) DO NOTHING "
            "RETURNING principal_id",
            (principal.principal_id, principal.label, now),
        ).fetchone()
        if inserted is None:
            raise DuplicateIdentifier("the principal identifier already exists")

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
