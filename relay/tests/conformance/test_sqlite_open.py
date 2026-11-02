"""Opening the SQLite backend: file mode, WAL, pragmas, version and path checks."""

from __future__ import annotations

import os
import shutil
import sqlite3
import stat
from collections.abc import Iterator
from pathlib import Path

import pytest

from fitdocs_relay.config import SqliteTarget
from fitdocs_relay.storage.interface import (
    SchemaChange,
    StorageError,
    StorageUnreachable,
)
from fitdocs_relay.storage.sqlite import SqliteBackend, _statements


@pytest.fixture
def permissive_umask() -> Iterator[None]:
    """A umask that lets the default file mode through (0o666 -> 0o664)."""
    previous = os.umask(0o002)
    try:
        yield
    finally:
        os.umask(previous)


def mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def test_a_new_file_is_created_at_0600_even_under_a_permissive_umask(
    tmp_path: Path, permissive_umask: None
) -> None:
    control = tmp_path / "control"
    control.write_text("x")
    assert mode(control) == 0o664  # the umask does let group-write through
    path = tmp_path / "relay.db"
    assert not path.exists()

    backend = SqliteBackend(SqliteTarget(path=path))
    backend.ping()
    backend.close()

    assert mode(path) == 0o600


def test_an_existing_file_keeps_its_mode(tmp_path: Path) -> None:
    path = tmp_path / "relay.db"
    path.write_bytes(b"")
    path.chmod(0o640)

    SqliteBackend(SqliteTarget(path=path)).close()

    assert mode(path) == 0o640


def test_the_journal_mode_is_set_to_wal_when_the_store_is_opened(
    tmp_path: Path,
) -> None:
    path = tmp_path / "relay.db"
    plain = sqlite3.connect(path)
    assert plain.execute("PRAGMA journal_mode").fetchone() == ("delete",)
    plain.close()

    SqliteBackend(SqliteTarget(path=path)).close()

    check = sqlite3.connect(path)
    try:
        assert check.execute("PRAGMA journal_mode").fetchone() == ("wal",)
    finally:
        check.close()


def test_every_operation_connection_enforces_foreign_keys_and_waits_to_lock(
    tmp_path: Path,
) -> None:
    path = tmp_path / "relay.db"
    backend = SqliteBackend(SqliteTarget(path=path))
    plain = sqlite3.connect(path)
    assert plain.execute("PRAGMA foreign_keys").fetchone() == (0,)
    assert plain.execute("PRAGMA busy_timeout").fetchone() == (5000,)  # python's own
    plain.close()

    connection = backend._connect()
    try:
        assert connection.isolation_level is None
        assert connection.execute("PRAGMA foreign_keys").fetchone() == (1,)
        assert connection.execute("PRAGMA busy_timeout").fetchone() == (5000,)
    finally:
        connection.close()


@pytest.mark.parametrize(
    ("version", "accepted"),
    [((3, 34, 1), False), ((3, 35, 0), True), ((3, 45, 2), True), ((2, 99, 0), False)],
)
def test_the_sqlite_version_check(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    version: tuple[int, int, int],
    accepted: bool,
) -> None:
    text = ".".join(map(str, version))
    monkeypatch.setattr(
        "fitdocs_relay.storage.sqlite.sqlite3.sqlite_version_info", version
    )
    monkeypatch.setattr("fitdocs_relay.storage.sqlite.sqlite3.sqlite_version", text)
    path = tmp_path / "relay.db"

    if accepted:
        SqliteBackend(SqliteTarget(path=path)).close()
        assert path.exists()
        return
    with pytest.raises(StorageError) as refused:
        SqliteBackend(SqliteTarget(path=path))
    assert text in str(refused.value)
    assert not path.exists()  # refused before anything was created


def test_a_missing_parent_directory_is_a_storage_error(tmp_path: Path) -> None:
    with pytest.raises(StorageError) as refused:
        SqliteBackend(SqliteTarget(path=tmp_path / "absent" / "relay.db"))
    assert type(refused.value) is StorageError  # not the unreachable subclass
    assert not (tmp_path / "absent").exists()


def test_ping_is_unreachable_when_the_database_directory_goes_away(
    tmp_path: Path,
) -> None:
    folder = tmp_path / "data"
    folder.mkdir()
    backend = SqliteBackend(SqliteTarget(path=folder / "relay.db"))
    backend.ping()
    shutil.rmtree(folder)

    with pytest.raises(StorageUnreachable) as raised:
        backend.ping()
    assert_fixed_unreachable(raised.value)


def test_a_deleted_database_file_is_unreachable_and_is_not_recreated(
    tmp_path: Path, permissive_umask: None
) -> None:
    path = tmp_path / "relay.db"
    backend = SqliteBackend(SqliteTarget(path=path))
    backend.ping()
    path.unlink()
    assert not path.exists()

    with pytest.raises(StorageUnreachable) as pinged:
        backend.ping()
    with pytest.raises(StorageUnreachable):
        backend.schema_state()

    assert_fixed_unreachable(pinged.value)
    assert not path.exists()  # no empty, default-mode database left behind
    assert sorted(p.name for p in tmp_path.iterdir()) == []


def test_a_file_that_cannot_be_created_is_the_fixed_unreachable_error(
    tmp_path: Path,
) -> None:
    folder = tmp_path / "locked"
    folder.mkdir()
    folder.chmod(0o500)
    try:
        if os.access(folder, os.W_OK):
            pytest.skip("the directory is writable despite its mode (running as root)")
        with pytest.raises(StorageUnreachable) as raised:
            SqliteBackend(SqliteTarget(path=folder / "relay.db"))
    finally:
        folder.chmod(0o700)
    assert_fixed_unreachable(raised.value)


def assert_fixed_unreachable(error: BaseException) -> None:
    assert str(error) == "the SQLite database cannot be reached"
    assert error.args == ("the SQLite database cannot be reached",)
    assert error.__cause__ is None
    assert error.__context__ is None


def test_the_statement_splitter_keeps_triggers_and_comments_whole() -> None:
    sql = (
        "-- a comment; with a semicolon\n"
        "CREATE TABLE a (x integer); CREATE TABLE b (y integer);\n"
        "CREATE TRIGGER t AFTER INSERT ON a BEGIN\n"
        "  INSERT INTO b VALUES (new.x); INSERT INTO b VALUES (0);\n"
        "END;\n"
        "INSERT INTO a VALUES (1)\n"
    )
    statements = [s.strip() for s in _statements(sql)]
    assert len(statements) == 4
    assert statements[0].endswith("CREATE TABLE a (x integer);")
    assert statements[1] == "CREATE TABLE b (y integer);"
    assert statements[2].startswith("CREATE TRIGGER t") and statements[2].endswith(
        "END;"
    )
    assert statements[3] == "INSERT INTO a VALUES (1)"


def test_a_change_with_a_trigger_applies_in_one_transaction(tmp_path: Path) -> None:
    backend = SqliteBackend(SqliteTarget(path=tmp_path / "relay.db"))
    base = SchemaChange(
        version=1,
        name="0001_trigger",
        sql=(
            "CREATE TABLE relay_schema (version INTEGER PRIMARY KEY, "
            "name TEXT, applied_at INTEGER);\n"
            "CREATE TABLE a (x integer); CREATE TABLE b (y integer);\n"
            "CREATE TRIGGER t AFTER INSERT ON a BEGIN\n"
            "  INSERT INTO b VALUES (new.x); INSERT INTO b VALUES (0);\n"
            "END;\n"
        ),
    )
    assert backend.apply_schema_change(base, now=5) is True
    connection = backend._connect()
    try:
        connection.execute("INSERT INTO a VALUES (7)")
        assert connection.execute("SELECT y FROM b ORDER BY y").fetchall() == [
            (0,),
            (7,),
        ]
    finally:
        connection.close()
    backend.close()
