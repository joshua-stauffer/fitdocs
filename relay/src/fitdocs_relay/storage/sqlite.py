"""The SQLite backend (the only module that imports `sqlite3`)."""

from __future__ import annotations

import fcntl
import os
import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager, suppress
from typing import Any, Literal

from fitdocs_relay.config import SqliteTarget
from fitdocs_relay.storage.interface import (
    BudgetCharge,
    BudgetDecision,
    DuplicateIdentifier,
    NewConnection,
    NewPrincipal,
    NewToken,
    Principal,
    Publication,
    RateDecision,
    RevokeResult,
    SchemaChange,
    SchemaState,
    SealedTokens,
    ServingClaim,
    StorageError,
    StorageUnreachable,
    StoredConnection,
    TokenRecord,
    TokenSummary,
    UnknownPrincipal,
)
from fitdocs_relay.storage.migrate import schema_changes

MINIMUM_SQLITE_VERSION = (3, 35, 0)  # RETURNING
BUSY_TIMEOUT_MS = 5000
FILE_MODE = 0o600
SERVE_LOCK_SUFFIX = ".serve-lock"  # <database>.serve-lock

# Fixed texts: the driver's own message is never carried (it can name values).
_UNREACHABLE = "the SQLite database cannot be reached"
_FAILED = "the SQLite database reported an error"


def _statements(sql: str) -> Iterator[str]:
    """Split a change into statements, keeping triggers and comments whole.

    `executescript` commits any open transaction first, so a change cannot use
    it and stay in the same transaction as its version row.
    """
    parts = sql.split(";")
    buffer = ""
    for index, part in enumerate(parts):
        buffer += part
        if index < len(parts) - 1:
            buffer += ";"
            if sqlite3.complete_statement(buffer):
                yield buffer
                buffer = ""
    if buffer.strip():
        yield buffer


class _SqliteClaim:
    """The serving claim: an exclusive `flock` on the sidecar file's descriptor.

    The lock belongs to the open file description, so closing the descriptor
    (or the process dying) frees it, and a second `release` finds nothing to
    close.
    """

    def __init__(self, descriptor: int) -> None:
        self._descriptor: int | None = descriptor

    def release(self) -> None:
        descriptor, self._descriptor = self._descriptor, None
        if descriptor is not None:
            os.close(descriptor)


_CONNECTION_COLUMNS = (
    "principal_id, target, account_key, access_sealed, refresh_sealed, "
    "access_expires_at, generation, lease_id, lease_until, token_id, "
    "created_at, updated_at"
)


def _connection_from_row(row: tuple[Any, ...]) -> StoredConnection:
    return StoredConnection(
        principal_id=row[0],
        target=row[1],
        account_key=row[2],
        tokens=SealedTokens(access=row[3], refresh=row[4], access_expires_at=row[5]),
        generation=row[6],
        lease_id=row[7],
        lease_until=row[8],
        token_id=row[9],
        created_at=row[10],
        updated_at=row[11],
    )


def _publication_from_row(row: tuple[Any, ...]) -> Publication:
    return Publication(
        target=row[0],
        publication_id=row[1],
        principal_id=row[2],
        sport=row[3],
        start_s=row[4],
        elapsed_s=row[5],
        distance_m=row[6],
    )


def _check_charges(charges: tuple[BudgetCharge, ...], now: int) -> None:
    """Refuse a malformed spend before it touches anything."""
    windows: set[tuple[str, int]] = set()
    for charge in charges:
        if charge.window_s < 1 or charge.amount < 1 or charge.ceiling < 0:
            raise ValueError(
                "a charge needs a window of a second or more, an amount of one "
                "or more and a ceiling of zero or more"
            )
        window = (charge.key, now - now % charge.window_s)
        if window in windows:
            raise ValueError("a window is charged once in a spend")
        windows.add(window)


def _lease_live(lease_until: int | None, now: int) -> bool:
    """A lease is live while its end is after `now`; an absent end is no lease."""
    return lease_until is not None and lease_until > now


def _run(
    connection: sqlite3.Connection, sql: str, params: tuple[object, ...] = ()
) -> list[tuple[Any, ...]]:
    """Execute and fetch; any driver error becomes the fixed-text `StorageError`."""
    failed = False
    try:
        return connection.execute(sql, params).fetchall()
    except sqlite3.Error:
        failed = True
    assert failed
    raise StorageError(_FAILED)


class SqliteBackend:
    """Storage on one SQLite file: a new connection per operation, WAL mode."""

    def __init__(self, target: SqliteTarget) -> None:
        self._path = target.path
        self._closed = False
        if sqlite3.sqlite_version_info < MINIMUM_SQLITE_VERSION:
            raise StorageError(
                f"SQLite {sqlite3.sqlite_version} is too old; "
                "version 3.35 or newer is required"
            )
        if not self._path.parent.is_dir():
            raise StorageError("the database's parent directory does not exist")
        self._create_file()
        with closing(self._connect()) as connection:
            _run(connection, "PRAGMA journal_mode=WAL")

    # --- StorageBase ---------------------------------------------------------

    @property
    def backend(self) -> Literal["sqlite"]:
        return "sqlite"

    def ping(self) -> None:
        self._check_open()
        with closing(self._connect()) as connection:
            _run(connection, "SELECT 1")

    def close(self) -> None:
        self._closed = True

    # --- PrincipalStore ------------------------------------------------------

    def create_principal(self, principal: NewPrincipal, *, now: int) -> Principal:
        with self._write() as connection:
            self._insert_principal(connection, principal, now)
        return Principal(principal.principal_id, principal.label, now)

    def get_principal(self, principal_id: str) -> Principal | None:
        with self._read() as connection:
            rows = _run(
                connection,
                "SELECT principal_id, label, created_at FROM principals "
                "WHERE principal_id = ?",
                (principal_id,),
            )
        return Principal(*rows[0]) if rows else None

    def list_principals(self) -> tuple[Principal, ...]:
        with self._read() as connection:
            rows = _run(
                connection,
                "SELECT principal_id, label, created_at FROM principals "
                "ORDER BY created_at, principal_id",
            )
        return tuple(Principal(*row) for row in rows)

    def delete_principal(self, principal_id: str) -> bool:
        # The tokens go with it: ON DELETE CASCADE, in this one transaction.
        with self._write() as connection:
            deleted = _run(
                connection,
                "DELETE FROM principals WHERE principal_id = ? RETURNING principal_id",
                (principal_id,),
            )
        return bool(deleted)

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
        with self._write() as connection:
            if new_principal is not None:
                self._insert_principal(connection, new_principal, now)
                owner = new_principal.principal_id
            else:
                assert principal_id is not None
                if not _run(
                    connection,
                    "SELECT 1 FROM principals WHERE principal_id = ?",
                    (principal_id,),
                ):
                    raise UnknownPrincipal("the principal does not exist")
                owner = principal_id
            if _run(
                connection,
                "SELECT 1 FROM tokens WHERE token_id = ?",
                (token.token_id,),
            ):
                raise DuplicateIdentifier("the token identifier already exists")
            _run(
                connection,
                "INSERT INTO tokens (token_id, principal_id, verifier, label, "
                "created_at, revoked_at) VALUES (?, ?, ?, ?, ?, NULL)",
                (token.token_id, owner, token.verifier, token.label, now),
            )
        return TokenRecord(
            token_id=token.token_id,
            principal_id=owner,
            verifier=token.verifier,
            label=token.label,
            created_at=now,
            revoked_at=None,
        )

    def find_token(self, token_id: str) -> TokenRecord | None:
        with self._read() as connection:
            rows = _run(
                connection,
                "SELECT token_id, principal_id, verifier, label, created_at, "
                "revoked_at FROM tokens WHERE token_id = ?",
                (token_id,),
            )
        return TokenRecord(*rows[0]) if rows else None

    def list_tokens(self, principal_id: str | None) -> tuple[TokenSummary, ...]:
        sql = "SELECT token_id, principal_id, label, created_at, revoked_at FROM tokens"
        params: tuple[object, ...] = ()
        if principal_id is not None:
            sql += " WHERE principal_id = ?"
            params = (principal_id,)
        with self._read() as connection:
            rows = _run(connection, sql + " ORDER BY created_at, token_id", params)
        return tuple(TokenSummary(*row) for row in rows)

    def revoke_token(self, token_id: str, *, now: int) -> RevokeResult:
        with self._write() as connection:
            rows = _run(
                connection,
                "SELECT revoked_at FROM tokens WHERE token_id = ?",
                (token_id,),
            )
            if not rows:
                return RevokeResult.UNKNOWN
            if rows[0][0] is not None:
                return RevokeResult.ALREADY_REVOKED
            _run(
                connection,
                "UPDATE tokens SET revoked_at = ? WHERE token_id = ?",
                (now, token_id),
            )
        return RevokeResult.REVOKED

    # --- RateLimitStore ------------------------------------------------------

    def count_request(
        self, *, key: str, window_s: int, limit: int, now: int
    ) -> RateDecision:
        window_start = now - now % window_s
        window_end = window_start + window_s
        with self._write() as connection:
            # A window that has ended (window_end <= now) is deleted; the
            # current one, and every other key's current one, is kept.
            _run(connection, "DELETE FROM rate_counts WHERE window_end <= ?", (now,))
            rows = _run(
                connection,
                "INSERT INTO rate_counts (key, window_start, count, window_end) "
                "VALUES (?, ?, 1, ?) "
                "ON CONFLICT (key, window_start) DO UPDATE SET count = count + 1 "
                "RETURNING count",
                (key, window_start, window_end),
            )
        count = int(rows[0][0])
        if count <= limit:
            return RateDecision(allowed=True, count=count, retry_after_s=None)
        return RateDecision(allowed=False, count=count, retry_after_s=window_end - now)

    # --- RecordStore ---------------------------------------------------------

    def put_record(
        self, *, namespace: str, key: str, value: bytes, expires_at: int, now: int
    ) -> None:
        with self._write() as connection:
            _run(connection, "DELETE FROM records WHERE expires_at <= ?", (now,))
            _run(
                connection,
                "INSERT INTO records (namespace, key, value, expires_at) "
                "VALUES (?, ?, ?, ?) ON CONFLICT (namespace, key) DO UPDATE "
                "SET value = excluded.value, expires_at = excluded.expires_at",
                (namespace, key, value, expires_at),
            )

    def get_record(self, *, namespace: str, key: str, now: int) -> bytes | None:
        with self._read() as connection:
            rows = _run(
                connection,
                "SELECT value FROM records "
                "WHERE namespace = ? AND key = ? AND expires_at > ?",
                (namespace, key, now),
            )
        return bytes(rows[0][0]) if rows else None

    def take_record(self, *, namespace: str, key: str, now: int) -> bytes | None:
        with self._write() as connection:
            rows = _run(
                connection,
                "DELETE FROM records "
                "WHERE namespace = ? AND key = ? AND expires_at > ? RETURNING value",
                (namespace, key, now),
            )
        return bytes(rows[0][0]) if rows else None

    def delete_record(self, *, namespace: str, key: str) -> bool:
        with self._write() as connection:
            rows = _run(
                connection,
                "DELETE FROM records WHERE namespace = ? AND key = ? RETURNING key",
                (namespace, key),
            )
        return bool(rows)

    # --- TargetConnectionStore -----------------------------------------------

    def put_connection(self, connection: NewConnection, *, now: int) -> None:
        owner, target, account = (
            connection.principal_id,
            connection.target,
            connection.account_key,
        )
        with self._write() as db:
            if not _run(
                db, "SELECT 1 FROM principals WHERE principal_id = ?", (owner,)
            ):
                raise UnknownPrincipal("the principal does not exist")
            rival = _run(
                db,
                "SELECT principal_id FROM target_connections "
                "WHERE target = ? AND account_key = ? AND principal_id <> ?",
                (target, account, owner),
            )
            if rival:
                self._remove_connection(db, str(rival[0][0]), target, now)
            own = _run(
                db,
                "SELECT account_key FROM target_connections "
                "WHERE principal_id = ? AND target = ?",
                (owner, target),
            )
            if own and own[0][0] != account:
                _run(
                    db,
                    "DELETE FROM target_publications "
                    "WHERE principal_id = ? AND target = ?",
                    (owner, target),
                )
            tokens = connection.tokens
            _run(
                db,
                "INSERT INTO target_connections (principal_id, target, account_key, "
                "access_sealed, refresh_sealed, access_expires_at, generation, "
                "lease_id, lease_until, token_id, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, 1, NULL, NULL, NULL, ?, ?) "
                "ON CONFLICT (principal_id, target) DO UPDATE SET "
                "account_key = excluded.account_key, "
                "access_sealed = excluded.access_sealed, "
                "refresh_sealed = excluded.refresh_sealed, "
                "access_expires_at = excluded.access_expires_at, "
                "generation = 1, lease_id = NULL, lease_until = NULL, "
                "updated_at = excluded.updated_at",
                (
                    owner,
                    target,
                    account,
                    tokens.access,
                    tokens.refresh,
                    tokens.access_expires_at,
                    now,
                    now,
                ),
            )

    def get_connection(self, principal_id: str, target: str) -> StoredConnection | None:
        with self._read() as db:
            rows = _run(
                db,
                f"SELECT {_CONNECTION_COLUMNS} FROM target_connections "
                "WHERE principal_id = ? AND target = ?",
                (principal_id, target),
            )
        return _connection_from_row(rows[0]) if rows else None

    def list_connections(self, target: str | None) -> tuple[StoredConnection, ...]:
        sql = f"SELECT {_CONNECTION_COLUMNS} FROM target_connections"
        params: tuple[object, ...] = ()
        if target is not None:
            sql += " WHERE target = ?"
            params = (target,)
        with self._read() as db:
            rows = _run(db, sql + " ORDER BY target, principal_id", params)
        return tuple(_connection_from_row(row) for row in rows)

    def claim_refresh(
        self,
        principal_id: str,
        target: str,
        *,
        generation: int,
        lease_id: str,
        lease_until: int,
        now: int,
    ) -> bool:
        with self._write() as db:
            rows = _run(
                db,
                "SELECT generation, lease_until FROM target_connections "
                "WHERE principal_id = ? AND target = ?",
                (principal_id, target),
            )
            if not rows or rows[0][0] != generation or _lease_live(rows[0][1], now):
                return False
            _run(
                db,
                "UPDATE target_connections SET lease_id = ?, lease_until = ? "
                "WHERE principal_id = ? AND target = ?",
                (lease_id, lease_until, principal_id, target),
            )
            return True

    def swap_tokens(
        self,
        principal_id: str,
        target: str,
        *,
        generation: int,
        lease_id: str | None,
        tokens: SealedTokens,
        now: int,
    ) -> bool:
        with self._write() as db:
            rows = _run(
                db,
                "SELECT generation, lease_id, lease_until FROM target_connections "
                "WHERE principal_id = ? AND target = ?",
                (principal_id, target),
            )
            if not rows or rows[0][0] != generation:
                return False
            if lease_id is None:
                if _lease_live(rows[0][2], now):
                    return False
            elif rows[0][1] != lease_id:
                return False
            _run(
                db,
                "UPDATE target_connections SET access_sealed = ?, refresh_sealed = ?, "
                "access_expires_at = ?, generation = generation + 1, "
                "lease_id = NULL, lease_until = NULL, updated_at = ? "
                "WHERE principal_id = ? AND target = ?",
                (
                    tokens.access,
                    tokens.refresh,
                    tokens.access_expires_at,
                    now,
                    principal_id,
                    target,
                ),
            )
            return True

    def release_refresh(self, principal_id: str, target: str, *, lease_id: str) -> None:
        with self._write() as db:
            _run(
                db,
                "UPDATE target_connections SET lease_id = NULL, lease_until = NULL "
                "WHERE principal_id = ? AND target = ? AND lease_id = ?",
                (principal_id, target, lease_id),
            )

    def issue_connection_token(
        self, principal_id: str, target: str, token: NewToken, *, now: int
    ) -> TokenRecord | None:
        with self._write() as db:
            rows = _run(
                db,
                "SELECT token_id FROM target_connections "
                "WHERE principal_id = ? AND target = ?",
                (principal_id, target),
            )
            if not rows:
                return None
            if _run(db, "SELECT 1 FROM tokens WHERE token_id = ?", (token.token_id,)):
                raise DuplicateIdentifier("the token identifier already exists")
            _run(
                db,
                "INSERT INTO tokens (token_id, principal_id, verifier, label, "
                "created_at, revoked_at) VALUES (?, ?, ?, ?, ?, NULL)",
                (token.token_id, principal_id, token.verifier, token.label, now),
            )
            if rows[0][0] is not None:
                _run(
                    db,
                    "UPDATE tokens SET revoked_at = ? "
                    "WHERE token_id = ? AND revoked_at IS NULL",
                    (now, rows[0][0]),
                )
            _run(
                db,
                "UPDATE target_connections SET token_id = ? "
                "WHERE principal_id = ? AND target = ?",
                (token.token_id, principal_id, target),
            )
        return TokenRecord(
            token_id=token.token_id,
            principal_id=principal_id,
            verifier=token.verifier,
            label=token.label,
            created_at=now,
            revoked_at=None,
        )

    def delete_connection(
        self, principal_id: str, target: str, *, generation: int | None, now: int
    ) -> bool:
        with self._write() as db:
            if generation is not None and not _run(
                db,
                "SELECT 1 FROM target_connections "
                "WHERE principal_id = ? AND target = ? AND generation = ?",
                (principal_id, target, generation),
            ):
                return False
            return self._remove_connection(db, principal_id, target, now)

    def delete_connection_by_account(
        self, target: str, account_key: str, *, now: int
    ) -> bool:
        with self._write() as db:
            rows = _run(
                db,
                "SELECT principal_id FROM target_connections "
                "WHERE target = ? AND account_key = ?",
                (target, account_key),
            )
            if not rows:
                return False
            return self._remove_connection(db, str(rows[0][0]), target, now)

    @staticmethod
    def _remove_connection(
        db: sqlite3.Connection, principal_id: str, target: str, now: int
    ) -> bool:
        """Delete a connection, its publications; revoke its token. Inside a write."""
        rows = _run(
            db,
            "DELETE FROM target_connections WHERE principal_id = ? AND target = ? "
            "RETURNING token_id",
            (principal_id, target),
        )
        if not rows:
            return False
        _run(
            db,
            "DELETE FROM target_publications WHERE principal_id = ? AND target = ?",
            (principal_id, target),
        )
        if rows[0][0] is not None:
            _run(
                db,
                "UPDATE tokens SET revoked_at = ? "
                "WHERE token_id = ? AND revoked_at IS NULL",
                (now, rows[0][0]),
            )
        return True

    # --- PublicationStore ----------------------------------------------------

    def put_publication(self, publication: Publication, *, now: int) -> bool:
        with self._write() as db:
            if not _run(
                db,
                "SELECT 1 FROM principals WHERE principal_id = ?",
                (publication.principal_id,),
            ):
                raise UnknownPrincipal("the principal does not exist")
            rows = _run(
                db,
                "INSERT INTO target_publications (target, publication_id, "
                "principal_id, sport, start_s, elapsed_s, distance_m, created_at, "
                "updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT (target, publication_id) DO UPDATE SET "
                "sport = excluded.sport, start_s = excluded.start_s, "
                "elapsed_s = excluded.elapsed_s, distance_m = excluded.distance_m, "
                "updated_at = excluded.updated_at "
                "WHERE target_publications.principal_id = excluded.principal_id "
                "RETURNING 1",
                (
                    publication.target,
                    publication.publication_id,
                    publication.principal_id,
                    publication.sport,
                    publication.start_s,
                    publication.elapsed_s,
                    publication.distance_m,
                    now,
                    now,
                ),
            )
            return bool(rows)

    def get_publication(self, target: str, publication_id: str) -> Publication | None:
        with self._read() as db:
            rows = _run(
                db,
                "SELECT target, publication_id, principal_id, sport, start_s, "
                "elapsed_s, distance_m FROM target_publications "
                "WHERE target = ? AND publication_id = ?",
                (target, publication_id),
            )
        return _publication_from_row(rows[0]) if rows else None

    # --- BudgetStore ---------------------------------------------------------

    def spend_budget(
        self, charges: tuple[BudgetCharge, ...], *, now: int
    ) -> BudgetDecision:
        _check_charges(charges, now)
        with self._write() as db:
            for principal_id in sorted(
                {c.principal_id for c in charges if c.principal_id is not None}
            ):
                if not _run(
                    db,
                    "SELECT 1 FROM principals WHERE principal_id = ?",
                    (principal_id,),
                ):
                    raise UnknownPrincipal("the principal does not exist")
            # A window that has ended (window_end <= now) is deleted.
            _run(db, "DELETE FROM budget_counts WHERE window_end <= ?", (now,))
            waits: list[int] = []
            for charge in charges:
                start = now - now % charge.window_s
                rows = _run(
                    db,
                    "SELECT count FROM budget_counts "
                    "WHERE key = ? AND window_start = ?",
                    (charge.key, start),
                )
                used = int(rows[0][0]) if rows else 0
                if used + charge.amount > charge.ceiling:
                    waits.append(start + charge.window_s - now)
            if waits:
                return BudgetDecision(allowed=False, retry_after_s=max(waits))
            for charge in charges:
                start = now - now % charge.window_s
                _run(
                    db,
                    "INSERT INTO budget_counts "
                    "(key, window_start, count, window_end, principal_id) "
                    "VALUES (?, ?, ?, ?, ?) "
                    "ON CONFLICT (key, window_start) "
                    "DO UPDATE SET count = count + excluded.count",
                    (
                        charge.key,
                        start,
                        charge.amount,
                        start + charge.window_s,
                        charge.principal_id,
                    ),
                )
        return BudgetDecision(allowed=True, retry_after_s=None)

    def exhaust_budget(self, *, key: str, window_s: int, count: int, now: int) -> None:
        if window_s < 1:
            raise ValueError("a window is a second or more")
        if count < 0:
            raise ValueError("a count is zero or more")
        start = now - now % window_s
        with self._write() as db:
            _run(
                db,
                "INSERT INTO budget_counts (key, window_start, count, window_end) "
                "VALUES (?, ?, ?, ?) "
                "ON CONFLICT (key, window_start) DO UPDATE SET "
                "count = max(count, excluded.count)",
                (key, start, count, start + window_s),
            )

    # --- ServingStore --------------------------------------------------------

    def claim_serving(self) -> ServingClaim | None:
        self._check_open()
        lock_path = self._path.with_name(self._path.name + SERVE_LOCK_SUFFIX)
        failed = False
        try:
            descriptor = os.open(lock_path, os.O_RDWR | os.O_CREAT, FILE_MODE)
        except OSError:
            failed = True
        if failed:
            raise StorageUnreachable(_UNREACHABLE)
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(descriptor)
            return None
        except OSError:
            failed = True
        if failed:
            os.close(descriptor)
            raise StorageError(_FAILED)
        return _SqliteClaim(descriptor)

    # --- SchemaStore ---------------------------------------------------------

    def schema_state(self) -> SchemaState:
        self._check_open()
        with closing(self._connect()) as connection:
            current = self._current_version(connection)
        return SchemaState(current=current, expected=len(schema_changes(self.backend)))

    def apply_schema_change(self, change: SchemaChange, *, now: int) -> bool:
        self._check_open()
        with closing(self._connect()) as connection:
            _run(connection, "BEGIN IMMEDIATE")  # the writer lock
            try:
                current = self._current_version(connection)  # re-read under the lock
                if change.version <= current:
                    applied = False
                elif change.version != current + 1:
                    raise StorageError("schema change applied out of order")
                else:
                    for statement in _statements(change.sql):
                        _run(connection, statement)
                    _run(
                        connection,
                        "INSERT INTO relay_schema (version, name, applied_at) "
                        "VALUES (?, ?, ?)",
                        (change.version, change.name, now),
                    )
                    applied = True
                _run(connection, "COMMIT")
            except BaseException:
                with suppress(sqlite3.Error):
                    connection.execute("ROLLBACK")
                raise
        return applied

    # --- internals -----------------------------------------------------------

    @contextmanager
    def _read(self) -> Iterator[sqlite3.Connection]:
        self._check_open()
        with closing(self._connect()) as connection:
            yield connection

    @contextmanager
    def _write(self) -> Iterator[sqlite3.Connection]:
        """One transaction under the writer lock: commit, or roll back on error."""
        self._check_open()
        with closing(self._connect()) as connection:
            _run(connection, "BEGIN IMMEDIATE")
            try:
                yield connection
                _run(connection, "COMMIT")
            except BaseException:
                with suppress(sqlite3.Error):
                    connection.execute("ROLLBACK")
                raise

    @staticmethod
    def _insert_principal(
        connection: sqlite3.Connection, principal: NewPrincipal, now: int
    ) -> None:
        if _run(
            connection,
            "SELECT 1 FROM principals WHERE principal_id = ?",
            (principal.principal_id,),
        ):
            raise DuplicateIdentifier("the principal identifier already exists")
        _run(
            connection,
            "INSERT INTO principals (principal_id, label, created_at) VALUES (?, ?, ?)",
            (principal.principal_id, principal.label, now),
        )

    def _check_open(self) -> None:
        if self._closed:
            raise StorageUnreachable(_UNREACHABLE)

    def _create_file(self) -> None:
        """Create the file at mode 0600 when absent; never change an existing one."""
        failed = False
        try:
            os.close(os.open(self._path, os.O_RDWR | os.O_CREAT, FILE_MODE))
        except OSError:
            failed = True
        if failed:
            raise StorageUnreachable(_UNREACHABLE)

    def _connect(self) -> sqlite3.Connection:
        failed = False
        try:
            # mode=rw: a file that has gone away is unreachable, not recreated
            # (at the default mode, with schema version 0).
            connection = sqlite3.connect(
                f"{self._path.absolute().as_uri()}?mode=rw",
                uri=True,
                isolation_level=None,
            )
            connection.execute(f"PRAGMA busy_timeout={BUSY_TIMEOUT_MS}")
            connection.execute("PRAGMA foreign_keys=ON")
            return connection
        except sqlite3.Error:
            failed = True
        assert failed
        raise StorageUnreachable(_UNREACHABLE)

    @staticmethod
    def _current_version(connection: sqlite3.Connection) -> int:
        table = _run(
            connection,
            "SELECT 1 FROM sqlite_master "
            "WHERE type = 'table' AND name = 'relay_schema'",
        )
        if not table:
            return 0
        rows = _run(connection, "SELECT COALESCE(MAX(version), 0) FROM relay_schema")
        return int(rows[0][0])
