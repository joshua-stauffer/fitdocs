"""The SQLite backend (the only module that imports `sqlite3`)."""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Iterator
from contextlib import closing, suppress
from typing import Any, Literal

from fitdocs_relay.config import SqliteTarget
from fitdocs_relay.storage.interface import (
    SchemaChange,
    SchemaState,
    StorageError,
    StorageUnreachable,
)
from fitdocs_relay.storage.migrate import schema_changes

MINIMUM_SQLITE_VERSION = (3, 35, 0)  # RETURNING
BUSY_TIMEOUT_MS = 5000
FILE_MODE = 0o600

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
