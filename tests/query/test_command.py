"""Behavioral contract for one read-only query invocation."""

from __future__ import annotations

import os
import shutil
import stat
from collections.abc import Callable, Iterator, Mapping
from dataclasses import FrozenInstanceError, fields
from datetime import date, timedelta
from enum import StrEnum
from pathlib import Path
from threading import Timer
from types import SimpleNamespace
from typing import Any, cast, get_type_hints

import pytest

from fitdocs.athlete import load_athlete_inputs
from fitdocs.index import build, fingerprint, registry
from fitdocs.index.location import (
    IndexLocation,
    IndexLocationError,
    resolve_index_location,
)
from fitdocs.index.store import (
    FaultKind,
    IndexFault,
    IndexInterrupted,
    IndexOpenError,
    IndexStatementError,
    open_index,
    read_bookkeeping,
)
from fitdocs.layout import archive_path
from fitdocs.query import command as command_module
from fitdocs.query import sandbox as sandbox_module_import
from fitdocs.query import statement as statement_module
from fitdocs.query.format import ResultSet
from fitdocs.query.freshness import PageDrift
from fitdocs.query.sandbox import IndexBusy, SandboxUnverified
from fitdocs.query.schemaview import CatalogTable, IndexState
from fitdocs.query.statement import Restriction
from tests.index._helpers import forge_storage_version, hold_index
from tests.query._helpers import FIXTURE_TODAY, copy_indexed_root
from tests.query.conftest import HomeDirectory

command: Any = cast(Any, command_module)
sandbox_module: Any = cast(Any, sandbox_module_import)


@pytest.fixture(autouse=True)
def _active_empty_home(
    home_dir: HomeDirectory, capsys: pytest.CaptureFixture[str]
) -> Iterator[None]:
    assert Path(os.environ["HOME"]) == home_dir.path
    home_dir.assert_untouched()
    yield
    assert capsys.readouterr() == ("", "")
    home_dir.assert_untouched()


def _env(home: Path, index_base: Path, *, pid: int = 74123) -> command.QueryEnvironment:
    return command.QueryEnvironment(
        environ={"FITDOCS_INDEX_DIR": str(index_base)},
        home=home,
        pid=pid,
        monotonic=lambda: 0.0,
        sleep=lambda _delay: None,
        on_wait=lambda _pid: None,
        is_running=lambda _pid: False,
        timer=Timer,
    )


def _request(
    root: Path, *, sql: str | None = "SELECT 7 AS answer", schema: bool = False
) -> command.QueryRequest:
    return command.QueryRequest(root, sql, schema, 1, 4.25, FIXTURE_TODAY)


def _copy(indexed_root: tuple[Path, Path], dst: Path) -> tuple[Path, Path, Path]:
    source_root, source_index = indexed_root
    copy_root = dst / "copied-fixture"
    copy_root.mkdir()
    root, index_dir = copy_indexed_root(source_root, source_index, copy_root)
    home = Path(os.environ["HOME"])
    assert tuple(home.iterdir()) == ()
    assert (
        (root / "fitdocs.toml")
        .read_text(encoding="utf-8")
        .startswith("[tiles]\nenabled = false\n")
    )
    return root, index_dir, home


def _watch_close(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    actual_open = command.open_sandboxed
    events: list[str] = []

    class ConnectionCloseSpy:
        def __init__(self, conn: Any) -> None:
            self.conn = conn

        def close(self) -> None:
            events.append("close")
            self.conn.close()

        def __getattr__(self, name: Any) -> Any:
            return getattr(self.conn, name)

    monkeypatch.setattr(
        command,
        "open_sandboxed",
        lambda *args, **kwargs: ConnectionCloseSpy(actual_open(*args, **kwargs)),
    )
    return events


def _filesystem_inventory(
    root: Path, index_dir: Path
) -> tuple[tuple[str, str, int, bytes | str | None], ...]:
    entries: list[tuple[str, str, int, bytes | str | None]] = []
    for base in (root, index_dir):
        for path in (base, *base.rglob("*")):
            mode = path.lstat().st_mode
            if path.is_symlink():
                payload: bytes | str | None = os.readlink(os.fsencode(path))
                kind = "symlink"
            elif path.is_dir():
                payload = None
                kind = "directory"
            elif path.is_file():
                payload = path.read_bytes()
                kind = "file"
            else:
                payload = None
                kind = "other"
            entries.append((path.as_posix(), kind, mode, payload))
    return tuple(sorted(entries))


def test_filesystem_inventory_captures_fixed_bytes_modes_and_unfollowed_links(
    tmp_path: Path,
) -> None:
    root = tmp_path / "inventory-root"
    index_dir = tmp_path / "inventory-index"
    outside = tmp_path / "dir-target"
    root.mkdir()
    index_dir.mkdir()
    outside.mkdir()
    nested_empty = root / "nested-empty"
    nested_empty.mkdir()
    os.chmod(nested_empty, 0o750)
    (root / "known.bin").write_bytes(b"fixed file bytes")
    os.chmod(root / "known.bin", 0o640)
    (root / "empty.bin").write_bytes(b"")
    (outside / "hidden.bin").write_bytes(b"must not be traversed")
    (root / "file-link").symlink_to(Path("known.bin"))
    (root / "directory-link").symlink_to(
        Path("../dir-target"), target_is_directory=True
    )
    (root / "dangling-link").symlink_to(Path("missing-target"))

    initial = _filesystem_inventory(root, index_dir)
    by_path = {entry[0]: entry[1:] for entry in initial}
    known = by_path[(root / "known.bin").as_posix()]
    empty = by_path[(root / "empty.bin").as_posix()]
    assert known[0] == "file" and known[2] == b"fixed file bytes"
    assert known[1] == stat.S_IFREG | 0o640
    assert empty[0] == "file" and empty[2] == b""
    assert stat.S_IFMT(empty[1]) == stat.S_IFREG
    directory = by_path[nested_empty.as_posix()]
    assert directory == ("directory", stat.S_IFDIR | 0o750, None)
    file_link = by_path[(root / "file-link").as_posix()]
    assert file_link[0] == "symlink" and file_link[2] == b"known.bin"
    assert stat.S_IFMT(file_link[1]) == stat.S_IFLNK
    directory_link = by_path[(root / "directory-link").as_posix()]
    assert directory_link[0::2] == ("symlink", b"../dir-target")
    assert stat.S_IFMT(directory_link[1]) == stat.S_IFLNK
    dangling_link = by_path[(root / "dangling-link").as_posix()]
    assert dangling_link[0::2] == ("symlink", b"missing-target")
    assert stat.S_IFMT(dangling_link[1]) == stat.S_IFLNK
    assert (root / "directory-link" / "hidden.bin").as_posix() not in by_path
    assert (outside / "hidden.bin").as_posix() not in by_path

    (root / "created.bin").write_bytes(b"created")
    created = _filesystem_inventory(root, index_dir)
    assert created != initial
    assert {entry[0]: entry[3] for entry in created}[
        (root / "created.bin").as_posix()
    ] == b"created"
    os.chmod(root / "known.bin", 0o600)
    chmodded = _filesystem_inventory(root, index_dir)
    assert chmodded != created
    assert {entry[0]: entry[2] for entry in chmodded}[
        (root / "known.bin").as_posix()
    ] == stat.S_IFREG | 0o600
    (root / "known.bin").write_bytes(b"changed bytes")
    changed = _filesystem_inventory(root, index_dir)
    assert changed != chmodded
    assert {entry[0]: entry[3] for entry in changed}[
        (root / "known.bin").as_posix()
    ] == b"changed bytes"
    (root / "known.bin").unlink()
    removed = _filesystem_inventory(root, index_dir)
    assert removed != changed
    assert (root / "known.bin").as_posix() not in {entry[0] for entry in removed}


def test_public_api_is_exact_frozen_and_import_safe() -> None:
    assert issubclass(command.OutcomeKind, StrEnum)
    assert command.DEFAULT_MAX_ROWS == 1000
    assert command.DEFAULT_TIMEOUT_S == 30.0
    assert tuple(command.OutcomeKind.__members__) == (
        "RESULT",
        "SCHEMA",
        "NOT_BUILT",
        "NEEDS_REBUILD",
        "BUSY",
        "REFUSED",
        "FAILED",
        "TIMED_OUT",
        "UNVERIFIED",
    )
    assert tuple(item.value for item in command.OutcomeKind) == (
        "result",
        "schema",
        "not_built",
        "needs_rebuild",
        "busy",
        "refused",
        "failed",
        "timed_out",
        "unverified",
    )
    assert all(type(item.value) is str for item in command.OutcomeKind)
    assert tuple(field.name for field in fields(command.QueryRequest)) == (
        "data_root",
        "sql",
        "schema",
        "max_rows",
        "timeout_s",
        "today",
    )
    assert tuple(field.name for field in fields(command.QueryEnvironment)) == (
        "environ",
        "home",
        "pid",
        "monotonic",
        "sleep",
        "on_wait",
        "is_running",
        "timer",
    )
    assert tuple(field.name for field in fields(command.SchemaReport)) == (
        "state",
        "tables",
        "counts",
    )
    assert tuple(field.name for field in fields(command.QueryOutcome)) == (
        "kind",
        "location",
        "result",
        "drift",
        "schema",
        "state",
        "restriction",
        "message",
        "hint",
        "holder_pid",
    )
    assert type(command.DEFAULT_MAX_ROWS) is int
    assert type(command.DEFAULT_TIMEOUT_S) is float
    assert (
        get_type_hints(command.QueryEnvironment)["timer"]
        == statement_module.TimerFactory
    )
    assert get_type_hints(command.QueryRequest) == {
        "data_root": Path,
        "sql": str | None,
        "schema": bool,
        "max_rows": int,
        "timeout_s": float,
        "today": date,
    }
    assert get_type_hints(command.QueryEnvironment) == {
        "environ": Mapping[str, str],
        "home": Path,
        "pid": int,
        "monotonic": Callable[[], float],
        "sleep": Callable[[float], None],
        "on_wait": Callable[[int | None], None],
        "is_running": Callable[[int], bool],
        "timer": statement_module.TimerFactory,
    }
    assert get_type_hints(command.SchemaReport) == {
        "state": IndexState,
        "tables": tuple[CatalogTable, ...],
        "counts": Mapping[str, int],
    }
    assert get_type_hints(command.QueryOutcome) == {
        "kind": command.OutcomeKind,
        "location": IndexLocation,
        "result": ResultSet | None,
        "drift": PageDrift | None,
        "schema": command.SchemaReport | None,
        "state": IndexState | None,
        "restriction": Restriction | None,
        "message": str | None,
        "hint": str | None,
        "holder_pid": int | None,
    }
    request = _request(Path("/private/fixture"))
    environment = _env(Path("/private/home"), Path("/private/cache"))
    state = command.IndexState(
        Path("/private/index.duckdb"), None, 2, None, None, (), {}, None, None, None
    )
    location = resolve_index_location(
        Path("/private/data"),
        {"FITDOCS_INDEX_DIR": "/private/cache"},
        Path("/private/home"),
    )
    values = (
        (request, "schema"),
        (environment, "pid"),
        (command.SchemaReport(state, (), {}), "tables"),
        (command.QueryOutcome(command.OutcomeKind.NOT_BUILT, location), "kind"),
    )
    for value, field_name in values:
        with pytest.raises(FrozenInstanceError):
            setattr(value, field_name, getattr(value, field_name))
    signature = __import__("inspect").signature(command.QueryOutcome)
    assert (
        tuple(
            signature.parameters[name].default
            for name in (
                "result",
                "drift",
                "schema",
                "state",
                "restriction",
                "message",
                "hint",
                "holder_pid",
            )
        )
        == (None,) * 8
    )


def test_result_is_a_direct_read_oracle_and_emits_nothing(
    indexed_root: tuple[Path, Path],
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, index_dir, home = _copy(indexed_root, tmp_path)
    close_events = _watch_close(monkeypatch)
    with open_index(index_dir / "index.duckdb", read_only=True) as conn:
        oracle = conn.execute(
            "SELECT 7 AS answer UNION ALL SELECT 9 AS answer ORDER BY answer"
        ).fetchall()
    assert oracle == [(7,), (9,)]
    inventory_before = _filesystem_inventory(root, index_dir)
    actual_runner = command.run_statement
    forwarded: list[str] = []

    def run_spy(conn: Any, sql: Any, **kwargs: Any) -> Any:
        forwarded.append(sql)
        return actual_runner(conn, sql, **kwargs)

    monkeypatch.setattr(command, "run_statement", run_spy)
    sql = "SELECT 7 AS answer UNION ALL SELECT 9 AS answer ORDER BY answer"
    output = command.run_query(
        _request(root, sql=sql),
        _env(home, index_dir.parent),
    )
    assert (
        output.kind,
        output.location.database,
        output.result,
        output.drift,
        output.schema,
        output.state,
        output.restriction,
        output.message,
        output.hint,
        output.holder_pid,
    ) == (
        command.OutcomeKind.RESULT,
        index_dir / "index.duckdb",
        ResultSet(("answer",), ((7,),), True, 1),
        PageDrift(2, 2, 0, 0, 0),
        None,
        None,
        None,
        None,
        None,
        None,
    )
    assert forwarded == [sql]
    assert close_events == ["close"]
    assert capsys.readouterr() == ("", "")
    assert tuple(home.iterdir()) == ()
    assert _filesystem_inventory(root, index_dir) == inventory_before


def test_result_object_and_all_request_execution_values_are_forwarded_unchanged(
    indexed_root: tuple[Path, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, index_dir, home = _copy(indexed_root, tmp_path)
    close_events = _watch_close(monkeypatch)
    timer = Timer
    result = ResultSet(("literal",), ((73,),), False, 17)
    forwarded: list[tuple[object, ...]] = []

    def statement(
        conn: Any, sql: Any, *, max_rows: Any, timeout_s: Any, timer: Any
    ) -> Any:
        forwarded.append((sql, max_rows, timeout_s, timer))
        return result

    monkeypatch.setattr(command, "run_statement", statement)
    request = command.QueryRequest(
        root, "SELECT 73 AS literal", False, 17, 2.5, date(2021, 10, 1)
    )
    env = command.QueryEnvironment(
        {"FITDOCS_INDEX_DIR": str(index_dir.parent)},
        home,
        74123,
        lambda: 0.0,
        lambda _delay: None,
        lambda _pid: None,
        lambda _pid: False,
        timer,
    )
    outcome = command.run_query(request, env)
    assert outcome.kind is command.OutcomeKind.RESULT
    assert outcome.result is result
    assert forwarded == [("SELECT 73 AS literal", 17, 2.5, timer)]
    assert close_events == ["close"]


def test_absent_index_is_not_built_without_creating_cache(
    tmp_path: Path, home_dir: HomeDirectory, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "data"
    root.mkdir()
    home = home_dir.path
    env = _env(home, tmp_path / "cache")
    expected_location = resolve_index_location(root, env.environ, home)
    observed: list[str] = []
    monkeypatch.setattr(
        command, "scan_workout_pages", lambda *_: observed.append("scan")
    )
    monkeypatch.setattr(
        command, "open_sandboxed", lambda *_a, **_kw: pytest.fail("opened absent index")
    )
    monkeypatch.setattr(
        command,
        "run_statement",
        lambda *_a, **_kw: pytest.fail("executed absent index"),
    )
    outcome = command.run_query(_request(root), env)
    assert (
        outcome.kind,
        outcome.location,
        outcome.result,
        outcome.drift,
        outcome.schema,
        outcome.state,
        outcome.restriction,
        outcome.message,
        outcome.hint,
        outcome.holder_pid,
    ) == (
        command.OutcomeKind.NOT_BUILT,
        expected_location,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
    )
    assert not expected_location.directory.exists()
    assert observed == []

    resolver_home = tmp_path / "resolver-home"
    default_env = command.QueryEnvironment(
        {},
        resolver_home,
        74123,
        lambda: 0.0,
        lambda _delay: None,
        lambda _pid: None,
        lambda _pid: False,
        Timer,
    )
    default_location = resolve_index_location(root, {}, resolver_home)
    default_outcome = command.run_query(_request(root), default_env)
    assert (
        default_outcome.kind,
        default_outcome.location,
        default_outcome.result,
        default_outcome.drift,
        default_outcome.schema,
        default_outcome.state,
        default_outcome.restriction,
        default_outcome.message,
        default_outcome.hint,
        default_outcome.holder_pid,
    ) == (
        command.OutcomeKind.NOT_BUILT,
        default_location,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
    )
    assert not default_location.directory.exists()
    assert observed == []
    assert tuple(home.iterdir()) == ()
    assert not resolver_home.exists()


@pytest.mark.parametrize("file_kind", ["junk", "storage", "plain"])
def test_real_invalid_index_files_need_rebuild(
    indexed_root: tuple[Path, Path],
    tmp_path: Path,
    file_kind: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, index_dir, home = _copy(indexed_root, tmp_path)
    close_events = _watch_close(monkeypatch)
    monkeypatch.setattr(
        command,
        "run_statement",
        lambda *_a, **_kw: pytest.fail("statement on invalid index"),
    )
    monkeypatch.setattr(
        command,
        "read_catalog",
        lambda *_a, **_kw: pytest.fail("catalog on invalid index"),
    )
    database = index_dir / "index.duckdb"
    if file_kind == "junk":
        database.write_bytes(b"not a DuckDB index")
    elif file_kind == "storage":
        forge_storage_version(database, 69)
    else:
        from tests.query._helpers import plain_database

        database.unlink()
        plain_database(database)
    if file_kind == "plain":
        with open_index(database, read_only=True) as conn:
            assert read_bookkeeping(conn) is None
    else:
        with pytest.raises(IndexOpenError) as direct:
            open_index(database, read_only=True)
    outcome = command.run_query(_request(root), _env(home, index_dir.parent))
    expected_message = (
        "not a complete fitdocs index"
        if file_kind == "plain"
        else direct.value.fault.message
    )
    assert (
        outcome.kind,
        outcome.location.database,
        outcome.message,
        outcome.result,
        outcome.schema,
        outcome.state,
        outcome.restriction,
        outcome.hint,
        outcome.holder_pid,
    ) == (
        command.OutcomeKind.NEEDS_REBUILD,
        database,
        expected_message,
        None,
        None,
        None,
        None,
        None,
        None,
    )
    assert close_events == (["close"] if file_kind == "plain" else [])


@pytest.mark.parametrize(
    "malformed", [False, True], ids=["missing-meta", "null-schema-version"]
)
def test_schema_rebuild_failure_keeps_only_obtainable_partial_state(
    indexed_root: tuple[Path, Path],
    tmp_path: Path,
    malformed: bool,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, index_dir, home = _copy(indexed_root, tmp_path)
    database = index_dir / "index.duckdb"
    if malformed:
        with open_index(database, read_only=False) as conn:
            conn.execute("UPDATE index_meta SET schema_version = NULL")
        with (
            open_index(database, read_only=True) as conn,
            pytest.raises(TypeError) as direct,
        ):
            read_bookkeeping(conn)
        expected_reason = f"not a complete fitdocs index: {direct.value}"
    else:
        from tests.query._helpers import plain_database

        database.unlink()
        plain_database(database)
        with open_index(database, read_only=True) as conn:
            assert read_bookkeeping(conn) is None
        expected_reason = "not a complete fitdocs index"

    close_events = _watch_close(monkeypatch)
    monkeypatch.setattr(
        command,
        "read_catalog",
        lambda *_a, **_kw: pytest.fail("catalog on incomplete index"),
    )
    monkeypatch.setattr(
        command,
        "run_statement",
        lambda *_a, **_kw: pytest.fail("SQL on incomplete index"),
    )
    outcome = command.run_query(
        _request(root, sql=None, schema=True), _env(home, index_dir.parent)
    )

    assert outcome == command.QueryOutcome(
        command.OutcomeKind.NEEDS_REBUILD,
        resolve_index_location(
            root, {"FITDOCS_INDEX_DIR": str(index_dir.parent)}, home
        ),
        state=IndexState(
            database=database,
            recorded_schema_version=None,
            reads_schema_version=2,
            fitdocs_version=None,
            drift=None,
            left_out=(),
            without_computed={},
            athlete=None,
            corpus=None,
            rebuild_reason=expected_reason,
        ),
        message=expected_reason,
    )
    assert close_events == ["close"]


def test_real_schema_version_99_has_independent_literal_mismatch_reason(
    indexed_root: tuple[Path, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, index_dir, home = _copy(indexed_root, tmp_path)
    database = index_dir / "index.duckdb"
    with open_index(database, read_only=False) as conn:
        conn.execute(
            "UPDATE index_meta SET schema_version = 99, "
            "fitdocs_version = 'writer-version-99'"
        )
    close_events = _watch_close(monkeypatch)
    monkeypatch.setattr(
        command,
        "run_statement",
        lambda *_args, **_kwargs: pytest.fail(
            "statement was executed for schema-version mismatch"
        ),
    )
    monkeypatch.setattr(
        command,
        "read_catalog",
        lambda *_args, **_kwargs: pytest.fail(
            "catalog was read for schema-version mismatch"
        ),
    )
    outcome = command.run_query(
        _request(root, sql=None, schema=True), _env(home, index_dir.parent)
    )
    expected_reason = "index schema version 99 differs from readable schema version 2"
    assert outcome == command.QueryOutcome(
        command.OutcomeKind.NEEDS_REBUILD,
        resolve_index_location(
            root, {"FITDOCS_INDEX_DIR": str(index_dir.parent)}, home
        ),
        drift=PageDrift(2, 2, 0, 0, 0),
        state=IndexState(
            database=database,
            recorded_schema_version=99,
            reads_schema_version=2,
            fitdocs_version="writer-version-99",
            drift=PageDrift(2, 2, 0, 0, 0),
            left_out=(),
            without_computed={},
            athlete=None,
            corpus=None,
            rebuild_reason=expected_reason,
        ),
        message=expected_reason,
    )
    assert close_events == ["close"]


def test_real_writer_lock_reaches_busy_after_bounded_fake_clock(
    indexed_root: tuple[Path, Path], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root, index_dir, home = _copy(indexed_root, tmp_path)
    now = [0.0]
    sleeps: list[float] = []
    waits: list[int | None] = []

    def sleep(delay: float) -> None:
        sleeps.append(delay)
        now[0] += delay

    env = command.QueryEnvironment(
        environ={"FITDOCS_INDEX_DIR": str(index_dir.parent)},
        home=home,
        pid=74123,
        monotonic=lambda: now[0],
        sleep=sleep,
        on_wait=waits.append,
        is_running=lambda _pid: False,
        timer=Timer,
    )
    with hold_index(index_dir / "index.duckdb", read_only=False) as holder:
        outcome = command.run_query(_request(root), env)
    assert outcome.kind is command.OutcomeKind.BUSY
    assert outcome.holder_pid == holder
    assert waits == [holder]
    assert sum(sleeps) == pytest.approx(10.0)
    assert len(sleeps) < 20
    assert outcome.state is None and outcome.message is None
    assert capsys.readouterr() == ("", "")


def test_missing_open_race_deletes_real_copied_database_after_scan(
    indexed_root: tuple[Path, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, index_dir, home = _copy(indexed_root, tmp_path)
    database = index_dir / "index.duckdb"
    assert database.is_file()
    actual_scan = command.scan_workout_pages
    actual_open = command.open_sandboxed
    events: list[str] = []

    def delete_after_scan(data_root: Path) -> Any:
        scan = actual_scan(data_root)
        events.append("scan")
        database.unlink()
        assert not database.exists()
        return scan

    def verify_missing_open(*args: Any, **kwargs: Any) -> Any:
        events.append("open")
        try:
            return actual_open(*args, **kwargs)
        except IndexOpenError as error:
            assert error.fault.kind is FaultKind.MISSING
            events.append("actual-missing-fault")
            raise

    monkeypatch.setattr(command, "scan_workout_pages", delete_after_scan)
    monkeypatch.setattr(command, "open_sandboxed", verify_missing_open)
    monkeypatch.setattr(
        command,
        "run_statement",
        lambda *_a, **_kw: pytest.fail("executed missing race"),
    )
    outcome = command.run_query(_request(root), _env(home, index_dir.parent))
    assert events == ["scan", "open", "actual-missing-fault"]
    assert (
        outcome.kind,
        outcome.location.database,
        outcome.result,
        outcome.drift,
        outcome.schema,
        outcome.state,
        outcome.restriction,
        outcome.message,
        outcome.hint,
        outcome.holder_pid,
    ) == (
        command.OutcomeKind.NOT_BUILT,
        database,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
    )


def test_dead_spill_is_pruned_and_live_or_unrelated_entries_are_kept(
    indexed_root: tuple[Path, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, index_dir, home = _copy(indexed_root, tmp_path)
    close_events = _watch_close(monkeypatch)
    dead = index_dir / "query-spill-991001"
    live = index_dir / "query-spill-991002"
    unrelated = index_dir / "keep-this-entry"
    dead.mkdir()
    live.mkdir()
    unrelated.mkdir()
    (dead / "spill.bin").write_bytes(b"dead")
    (live / "spill.bin").write_bytes(b"live")
    (unrelated / "sentinel").write_bytes(b"keep")
    env = command.QueryEnvironment(
        environ={"FITDOCS_INDEX_DIR": str(index_dir.parent)},
        home=home,
        pid=74123,
        monotonic=lambda: 0.0,
        sleep=lambda _delay: None,
        on_wait=lambda _pid: None,
        is_running=lambda pid: pid == 991002,
        timer=Timer,
    )
    command.run_query(_request(root), env)
    assert not dead.exists()
    assert (live / "spill.bin").read_bytes() == b"live"
    assert (unrelated / "sentinel").read_bytes() == b"keep"
    assert close_events == ["close"]


def test_each_invocation_scans_new_page_state_without_reusing_snapshot(
    indexed_root: tuple[Path, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, index_dir, home = _copy(indexed_root, tmp_path)
    close_events = _watch_close(monkeypatch)
    real_scan = command.scan_workout_pages
    observed: list[tuple[str, ...]] = []

    def scan(data_root: Path) -> Any:
        result = real_scan(data_root)
        observed.append(tuple(page.path for page in result.pages))
        return result

    monkeypatch.setattr(command, "scan_workout_pages", scan)
    first = command.run_query(_request(root), _env(home, index_dir.parent))
    assert first.kind is command.OutcomeKind.RESULT
    assert len(observed) == 1
    original = sorted((root / "workouts").glob("*.md"))[0]
    _page_copy_with_key(root, original, "fresh-invocation.md", "9" * 64)
    second = command.run_query(_request(root), _env(home, index_dir.parent))
    assert (
        first.kind,
        second.kind,
        second.drift,
    ) == (
        command.OutcomeKind.RESULT,
        command.OutcomeKind.RESULT,
        PageDrift(3, 2, 1, 0, 0),
    )
    assert len(observed) == 2
    assert observed[0] != observed[1]
    assert close_events == ["close", "close"]


def test_schema_corpus_receives_bookkeeping_held_keys_after_connection_close(
    indexed_root: tuple[Path, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, index_dir, home = _copy(indexed_root, tmp_path)
    source = sorted((root / "workouts").glob("*.md"))[0]
    _page_copy_with_key(root, source, "added-after-index.md", "8" * 64)
    with open_index(index_dir / "index.duckdb", read_only=True) as conn:
        book = read_bookkeeping(conn)
    assert book is not None
    held_oracle = dict(book.pages)
    recorded_athlete_fingerprint = book.meta.athlete_fingerprint
    request_today = FIXTURE_TODAY + timedelta(days=1)
    assert request_today != FIXTURE_TODAY
    (root / "athlete.toml").write_text(
        "profile_version = 2\nftp_watts = 251\nresting_hr_bpm = 45\n"
        "max_hr_bpm = 190\nhr_zones = [100, 120, 140, 160]\n"
        "power_zones = [100, 150, 200, 250]\npace_zones = [240, 300, 360, 420]\n",
        encoding="utf-8",
    )
    current_inputs = load_athlete_inputs(root)
    assert current_inputs is not None
    current_fingerprint = fingerprint.athlete_fingerprint(current_inputs)
    assert current_fingerprint != recorded_athlete_fingerprint
    scan_oracle = command.scan_workout_pages(root)
    assert {page.page_key for page in scan_oracle.pages} != set(held_oracle)

    closed = [False]
    actual_open = command.open_sandboxed
    actual_corpus = command.corpus_fingerprints
    observed: dict[str, object] = {}

    class CloseSpy:
        def __init__(self, conn: Any) -> None:
            self.conn = conn

        def close(self) -> None:
            self.conn.close()
            closed[0] = True

        def __getattr__(self, name: Any) -> Any:
            return getattr(self.conn, name)

    def open_spy(*args: Any, **kwargs: Any) -> Any:
        return CloseSpy(actual_open(*args, **kwargs))

    def corpus_spy(scan: Any, held: Any, **kwargs: Any) -> Any:
        observed["held"] = dict(held)
        observed["after_close"] = closed[0]
        observed["today"] = kwargs["today"]
        observed["athlete_fingerprint"] = kwargs["athlete_fingerprint"]
        return actual_corpus(scan, held, **kwargs)

    monkeypatch.setattr(command, "open_sandboxed", open_spy)
    monkeypatch.setattr(command, "corpus_fingerprints", corpus_spy)
    request = command.QueryRequest(root, None, True, 1, 4.25, request_today)
    outcome = command.run_query(request, _env(home, index_dir.parent))
    assert outcome.kind is command.OutcomeKind.SCHEMA
    assert observed["held"] == held_oracle
    assert observed["after_close"] is True
    assert observed["today"] == request_today
    assert observed["athlete_fingerprint"] == current_fingerprint


def test_schema_drift_maps_current_registry_tables_not_stored_producer_tables(
    indexed_root: tuple[Path, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, index_dir, home = _copy(indexed_root, tmp_path)
    close_events = _watch_close(monkeypatch)
    current = SimpleNamespace(
        name="late.registration",
        tables=(
            SimpleNamespace(name="current_table"),
            SimpleNamespace(name="current_detail"),
        ),
    )
    monkeypatch.setattr(registry, "CORPUS_PRODUCERS", (current,))
    monkeypatch.setattr(
        command,
        "corpus_fingerprints",
        lambda *_args, **_kwargs: {"late.registration": "new"},
    )
    outcome = command.run_query(
        _request(root, sql=None, schema=True), _env(home, index_dir.parent)
    )
    assert outcome.kind is command.OutcomeKind.SCHEMA
    assert outcome.schema is not None
    assert outcome.schema.state.corpus is not None
    assert (
        outcome.schema.state.corpus.behind,
        outcome.schema.state.corpus.unassessed,
    ) == (("current_detail", "current_table"), ())
    assert close_events == ["close"]


def test_malformed_athlete_skips_all_corpus_work_and_reports_every_producer(
    indexed_root: tuple[Path, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, index_dir, home = _copy(indexed_root, tmp_path)
    close_events = _watch_close(monkeypatch)
    (root / "athlete.toml").write_text(
        'profile_version = 2\nftp_watts = "not-a-number"\n', encoding="utf-8"
    )
    monkeypatch.setattr(
        command,
        "corpus_fingerprints",
        lambda *_args, **_kwargs: pytest.fail("corpus scan after athlete file error"),
    )
    outcome = command.run_query(
        _request(root, sql=None, schema=True), _env(home, index_dir.parent)
    )
    assert outcome.kind is command.OutcomeKind.SCHEMA
    assert outcome.schema is not None
    athlete = outcome.schema.state.athlete
    assert athlete is not None
    expected_reason = (
        f"{root}/athlete.toml: ftp_watts must be a number, got 'not-a-number' (str)"
    )
    corpus = outcome.schema.state.corpus
    assert corpus is not None
    assert (
        athlete.activities_other_inputs,
        athlete.skipped_reason,
        corpus.behind,
        {name for name, _reason in corpus.unassessed},
        {reason for _name, reason in corpus.unassessed},
    ) == (
        None,
        expected_reason,
        (),
        {producer.name for producer in registry.CORPUS_PRODUCERS},
        {f"AthleteFileError: {expected_reason}"},
    )
    assert close_events == ["close"]


def test_statement_path_order_is_scan_open_bookkeeping_execute_close_drift(
    indexed_root: tuple[Path, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, index_dir, home = _copy(indexed_root, tmp_path)
    events: list[str] = []
    originals = {
        "resolve_index_location": command.resolve_index_location,
        "scan_workout_pages": command.scan_workout_pages,
        "open_sandboxed": command.open_sandboxed,
        "remove_stale_spill": command.remove_stale_spill,
        "read_bookkeeping": command.read_bookkeeping,
        "run_statement": command.run_statement,
        "page_drift": command.page_drift,
    }
    env = _env(home, index_dir.parent)
    expected_environ = {"FITDOCS_INDEX_DIR": str(index_dir.parent)}
    expected_location = resolve_index_location(root, expected_environ, home)
    resolver_arguments: list[tuple[Any, ...]] = []
    open_arguments: list[tuple[Any, ...]] = []
    spill_arguments: list[tuple[Any, ...]] = []

    def resolve_spy(data_root: Any, environ: Any, resolved_home: Any) -> Any:
        resolver_arguments.append((data_root, environ, resolved_home))
        return originals["resolve_index_location"](data_root, environ, resolved_home)

    def scan(*args: Any, **kwargs: Any) -> Any:
        events.append("scan")
        return originals["scan_workout_pages"](*args, **kwargs)

    class CloseSpy:
        def __init__(self, conn: Any) -> None:
            self.conn = conn

        def close(self) -> None:
            events.append("close")
            self.conn.close()

        def __getattr__(self, name: Any) -> Any:
            return getattr(self.conn, name)

    def open_spy(
        location: Any,
        *,
        pid: Any,
        monotonic: Any,
        sleep: Any,
        on_wait: Any,
    ) -> Any:
        events.append("open")
        open_arguments.append((location, pid, monotonic, sleep, on_wait))
        return CloseSpy(
            originals["open_sandboxed"](
                location,
                pid=pid,
                monotonic=monotonic,
                sleep=sleep,
                on_wait=on_wait,
            )
        )

    def spill_cleanup(location: Any, *, own_pid: Any, is_running: Any) -> Any:
        events.append("spill-cleanup")
        spill_arguments.append((location, own_pid, is_running))
        return originals["remove_stale_spill"](
            location, own_pid=own_pid, is_running=is_running
        )

    def bookkeeping(*args: Any, **kwargs: Any) -> Any:
        events.append("bookkeeping")
        return originals["read_bookkeeping"](*args, **kwargs)

    def statement(*args: Any, **kwargs: Any) -> Any:
        events.append("statement")
        return originals["run_statement"](*args, **kwargs)

    def drift(*args: Any, **kwargs: Any) -> Any:
        events.append("drift")
        return originals["page_drift"](*args, **kwargs)

    monkeypatch.setattr(command, "resolve_index_location", resolve_spy)
    monkeypatch.setattr(command, "scan_workout_pages", scan)
    monkeypatch.setattr(command, "open_sandboxed", open_spy)
    monkeypatch.setattr(command, "remove_stale_spill", spill_cleanup)
    monkeypatch.setattr(command, "read_bookkeeping", bookkeeping)
    monkeypatch.setattr(command, "run_statement", statement)
    monkeypatch.setattr(command, "page_drift", drift)
    outcome = command.run_query(_request(root), env)
    assert (outcome.kind, outcome.result is not None) == (
        command.OutcomeKind.RESULT,
        True,
    )
    assert events == [
        "spill-cleanup",
        "scan",
        "open",
        "bookkeeping",
        "statement",
        "close",
        "drift",
    ]
    assert spill_arguments == [(expected_location, 74123, env.is_running)]
    assert open_arguments == [
        (expected_location, 74123, env.monotonic, env.sleep, env.on_wait)
    ]
    assert resolver_arguments == [(root, expected_environ, home)]


@pytest.mark.parametrize(
    ("kind", "expected"),
    [
        (FaultKind.INCOMPATIBLE, command.OutcomeKind.NEEDS_REBUILD),
        (FaultKind.CORRUPT, command.OutcomeKind.NEEDS_REBUILD),
        (FaultKind.OTHER, command.OutcomeKind.NEEDS_REBUILD),
        (FaultKind.MISSING, command.OutcomeKind.NOT_BUILT),
    ],
)
def test_typed_open_errors_map_only_their_fault_kind(
    indexed_root: tuple[Path, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    kind: FaultKind,
    expected: command.OutcomeKind,
) -> None:
    root, index_dir, home = _copy(indexed_root, tmp_path)
    monkeypatch.setattr(
        command,
        "run_statement",
        lambda *_a, **_kw: pytest.fail("statement after open fault"),
    )
    monkeypatch.setattr(
        command,
        "read_catalog",
        lambda *_a, **_kw: pytest.fail("catalog after open fault"),
    )
    fault = IndexFault(kind, "literal open diagnostic", 8821)
    monkeypatch.setattr(
        command,
        "open_sandboxed",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(IndexOpenError(fault)),
    )
    outcome = command.run_query(_request(root), _env(home, index_dir.parent))
    assert (
        outcome.kind,
        outcome.location.database,
        outcome.message,
        outcome.holder_pid,
        outcome.result,
        outcome.drift,
        outcome.schema,
        outcome.state,
        outcome.restriction,
        outcome.hint,
    ) == (
        expected,
        index_dir / "index.duckdb",
        None if kind is FaultKind.MISSING else "literal open diagnostic",
        None,
        None,
        None,
        None,
        None,
        None,
        None,
    )


def test_busy_preserves_holder_and_unverified_null_is_literal_null(
    indexed_root: tuple[Path, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, index_dir, home = _copy(indexed_root, tmp_path)
    monkeypatch.setattr(
        command,
        "run_statement",
        lambda *_a, **_kw: pytest.fail("statement before verified open"),
    )
    monkeypatch.setattr(
        command,
        "read_catalog",
        lambda *_a, **_kw: pytest.fail("catalog before verified open"),
    )
    monkeypatch.setattr(
        command,
        "open_sandboxed",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(IndexBusy(7721)),
    )
    busy = command.run_query(_request(root), _env(home, index_dir.parent))
    assert (
        busy.kind,
        busy.holder_pid,
        busy.state,
        busy.message,
        busy.result,
        busy.drift,
        busy.schema,
        busy.restriction,
        busy.hint,
    ) == (command.OutcomeKind.BUSY, 7721, None, None, None, None, None, None, None)

    monkeypatch.setattr(
        command,
        "open_sandboxed",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            SandboxUnverified("threads", "2", None)
        ),
    )
    unverified = command.run_query(_request(root), _env(home, index_dir.parent))
    assert (
        unverified.kind,
        unverified.message,
        unverified.state,
        unverified.result,
        unverified.drift,
        unverified.schema,
        unverified.restriction,
        unverified.hint,
        unverified.holder_pid,
    ) == (
        command.OutcomeKind.UNVERIFIED,
        "the sandbox setting threads is NULL, not 2",
        None,
        None,
        None,
        None,
        None,
        None,
        None,
    )

    monkeypatch.setattr(
        command,
        "open_sandboxed",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            SandboxUnverified("threads", "2", "1")
        ),
    )
    mismatched = command.run_query(_request(root), _env(home, index_dir.parent))
    assert (
        mismatched.kind,
        mismatched.message,
        mismatched.state,
        mismatched.result,
        mismatched.drift,
        mismatched.schema,
        mismatched.restriction,
        mismatched.hint,
        mismatched.holder_pid,
    ) == (
        command.OutcomeKind.UNVERIFIED,
        "the sandbox setting threads is 1, not 2",
        None,
        None,
        None,
        None,
        None,
        None,
        None,
    )


def test_sandbox_mismatch_closes_once_before_command_returns_unverified(
    indexed_root: tuple[Path, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, index_dir, home = _copy(indexed_root, tmp_path)
    original_open = sandbox_module.store.open_index
    close_calls = [0]

    class CloseSpy:
        def __init__(self, conn: Any) -> None:
            self.conn = conn

        def close(self) -> None:
            close_calls[0] += 1
            self.conn.close()

        def __getattr__(self, name: Any) -> Any:
            return getattr(self.conn, name)

    monkeypatch.setattr(
        sandbox_module.store,
        "open_index",
        lambda *args, **kwargs: CloseSpy(original_open(*args, **kwargs)),
    )
    monkeypatch.setattr(sandbox_module, "REQUIRED_SANDBOX", {"threads": "wrong"})
    outcome = command.run_query(_request(root), _env(home, index_dir.parent))
    assert (
        outcome.kind,
        outcome.message,
        outcome.result,
        outcome.drift,
        outcome.schema,
        outcome.state,
        outcome.restriction,
        outcome.hint,
        outcome.holder_pid,
    ) == (
        command.OutcomeKind.UNVERIFIED,
        "the sandbox setting threads is 2, not wrong",
        None,
        None,
        None,
        None,
        None,
        None,
        None,
    )
    assert close_calls == [1]


@pytest.mark.parametrize(
    "error",
    [
        IndexStatementError("malformed index metadata"),
        ValueError("bad conversion"),
        TypeError("bad metadata type"),
    ],
)
def test_bookkeeping_conversion_errors_are_needs_rebuild(
    indexed_root: tuple[Path, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    error: Exception,
) -> None:
    root, index_dir, home = _copy(indexed_root, tmp_path)
    close_events = _watch_close(monkeypatch)
    monkeypatch.setattr(
        command, "read_bookkeeping", lambda _conn: (_ for _ in ()).throw(error)
    )
    outcome = command.run_query(_request(root), _env(home, index_dir.parent))
    assert (
        outcome.kind,
        outcome.message,
        outcome.result,
        outcome.schema,
        outcome.state,
        outcome.drift,
        outcome.restriction,
        outcome.hint,
        outcome.holder_pid,
    ) == (
        command.OutcomeKind.NEEDS_REBUILD,
        f"not a complete fitdocs index: {error}",
        None,
        None,
        None,
        None,
        None,
        None,
        None,
    )
    assert close_events == ["close"]


def test_incomplete_bookkeeping_and_unrelated_errors_are_distinct(
    indexed_root: tuple[Path, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, index_dir, home = _copy(indexed_root, tmp_path)
    close_events = _watch_close(monkeypatch)
    monkeypatch.setattr(command, "read_bookkeeping", lambda _conn: None)
    incomplete = command.run_query(_request(root), _env(home, index_dir.parent))
    assert (
        incomplete.kind,
        incomplete.message,
        incomplete.result,
        incomplete.drift,
        incomplete.schema,
        incomplete.state,
        incomplete.restriction,
        incomplete.hint,
        incomplete.holder_pid,
    ) == (
        command.OutcomeKind.NEEDS_REBUILD,
        "not a complete fitdocs index",
        None,
        None,
        None,
        None,
        None,
        None,
        None,
    )
    assert close_events == ["close"]
    marker = RuntimeError("unapproved bookkeeping failure")
    monkeypatch.setattr(
        command, "read_bookkeeping", lambda _conn: (_ for _ in ()).throw(marker)
    )
    with pytest.raises(RuntimeError) as raised:
        command.run_query(_request(root), _env(home, index_dir.parent))
    assert raised.value is marker
    assert close_events == ["close", "close"]


@pytest.mark.parametrize("broken_part", ["missing-table", "unknown-computed-state"])
def test_real_malformed_bookkeeping_is_needs_rebuild(
    indexed_root: tuple[Path, Path],
    tmp_path: Path,
    broken_part: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, index_dir, home = _copy(indexed_root, tmp_path)
    close_events = _watch_close(monkeypatch)
    database = index_dir / "index.duckdb"
    with open_index(database, read_only=False) as conn:
        if broken_part == "missing-table":
            conn.execute("DROP TABLE index_pages")
        else:
            conn.execute("UPDATE index_pages SET computed_state = 'unknown-state'")
    with (
        open_index(database, read_only=True) as conn,
        pytest.raises((IndexStatementError, ValueError, TypeError)) as direct,
    ):
        read_bookkeeping(conn)
    outcome = command.run_query(_request(root), _env(home, index_dir.parent))
    assert (
        outcome.kind,
        outcome.message,
        outcome.result,
        outcome.drift,
        outcome.schema,
        outcome.state,
        outcome.restriction,
        outcome.hint,
        outcome.holder_pid,
    ) == (
        command.OutcomeKind.NEEDS_REBUILD,
        f"not a complete fitdocs index: {direct.value}",
        None,
        None,
        None,
        None,
        None,
        None,
        None,
    )
    assert close_events == ["close"]


@pytest.mark.parametrize(
    ("kind", "expected_restriction", "detail"),
    [
        (Restriction.ONE_STATEMENT, Restriction.ONE_STATEMENT, "SELECT 1; SELECT 2"),
        (Restriction.STATEMENT_KIND, Restriction.STATEMENT_KIND, "CREATE"),
        (Restriction.OUTSIDE_INDEX, Restriction.OUTSIDE_INDEX, "PermissionException"),
        (
            Restriction.LOCKED_SETTING,
            Restriction.LOCKED_SETTING,
            "configuration locked",
        ),
        (Restriction.READ_ONLY, Restriction.READ_ONLY, "read-only mode"),
        (Restriction.EXTENSION, Restriction.EXTENSION, "requires extension"),
    ],
)
def test_refusal_keeps_enum_and_full_detail(
    indexed_root: tuple[Path, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    kind: Restriction,
    expected_restriction: Restriction,
    detail: str,
) -> None:
    root, index_dir, home = _copy(indexed_root, tmp_path)
    close_events = _watch_close(monkeypatch)
    from fitdocs.query.statement import StatementRefused

    refusal = StatementRefused(kind, detail)
    monkeypatch.setattr(
        command,
        "run_statement",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(refusal),
    )
    outcome = command.run_query(_request(root), _env(home, index_dir.parent))
    assert (
        outcome.kind,
        outcome.restriction,
        outcome.message,
        outcome.result,
        outcome.schema,
        outcome.state,
        outcome.hint,
        outcome.holder_pid,
    ) == (
        command.OutcomeKind.REFUSED,
        expected_restriction,
        detail,
        None,
        None,
        None,
        None,
        None,
    )
    assert close_events == ["close"]


def test_real_copy_refusal_is_screened_before_database_execute(
    indexed_root: tuple[Path, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, index_dir, home = _copy(indexed_root, tmp_path)
    target = tmp_path / "must-not-be-created.csv"
    sql = f"COPY (SELECT 7 AS answer) TO '{target}' (HEADER, DELIMITER ',')"
    actual_open = command.open_sandboxed
    actual_runner = command.run_statement
    forwarded: list[str] = []
    executed: list[str] = []
    fetched: list[str] = []
    closed: list[bool] = []

    class ResultFetchSpy:
        def __init__(self, result: Any, statement: str) -> None:
            self.result = result
            self.statement = statement

        def fetchmany(self, size: int) -> Any:
            fetched.append(self.statement)
            return self.result.fetchmany(size)

        def __getattr__(self, name: Any) -> Any:
            return getattr(self.result, name)

    class ExecuteSpy:
        def __init__(self, conn: Any) -> None:
            self.conn = conn

        def execute(self, statement: Any, *args: Any, **kwargs: Any) -> Any:
            executed.append(statement)
            result = self.conn.execute(statement, *args, **kwargs)
            if statement == "SELECT 23 AS safe":
                return ResultFetchSpy(result, statement)
            return result

        def close(self) -> None:
            closed.append(True)
            self.conn.close()

        def __getattr__(self, name: Any) -> Any:
            return getattr(self.conn, name)

    def open_spy(*args: Any, **kwargs: Any) -> Any:
        return ExecuteSpy(actual_open(*args, **kwargs))

    def runner(conn: Any, statement: Any, **kwargs: Any) -> Any:
        forwarded.append(statement)
        return actual_runner(conn, statement, **kwargs)

    monkeypatch.setattr(command, "open_sandboxed", open_spy)
    monkeypatch.setattr(command, "run_statement", runner)
    outcome = command.run_query(_request(root, sql=sql), _env(home, index_dir.parent))
    assert (
        outcome.kind,
        outcome.restriction,
        outcome.message,
        outcome.result,
        outcome.schema,
        outcome.state,
        outcome.hint,
        outcome.holder_pid,
        outcome.drift,
    ) == (
        command.OutcomeKind.REFUSED,
        Restriction.STATEMENT_KIND,
        "COPY",
        None,
        None,
        None,
        None,
        None,
        PageDrift(2, 2, 0, 0, 0),
    )
    assert forwarded == [sql]
    assert sql not in executed
    assert (
        "SELECT table_name FROM duckdb_tables() WHERE table_name = 'index_meta'"
        in executed
    )
    assert not target.exists()

    allowed = command.run_query(
        _request(root, sql="SELECT 23 AS safe"), _env(home, index_dir.parent)
    )
    assert (
        allowed.kind,
        None if allowed.result is None else allowed.result.rows,
        None if allowed.result is None else allowed.result.columns,
        None if allowed.result is None else allowed.result.truncated,
        None if allowed.result is None else allowed.result.max_rows,
    ) == (command.OutcomeKind.RESULT, ((23,),), ("safe",), False, 1)
    assert "SELECT 23 AS safe" in executed
    assert fetched == ["SELECT 23 AS safe"]
    assert closed == [True, True]


def test_real_multiple_statement_refusal_preserves_gate_detail_without_execute(
    indexed_root: tuple[Path, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, index_dir, home = _copy(indexed_root, tmp_path)
    actual_open = command.open_sandboxed
    executed: list[str] = []

    class ExecuteSpy:
        def __init__(self, conn: Any) -> None:
            self.conn = conn

        def execute(self, sql: Any, *args: Any, **kwargs: Any) -> Any:
            executed.append(sql)
            return self.conn.execute(sql, *args, **kwargs)

        def __getattr__(self, name: Any) -> Any:
            return getattr(self.conn, name)

    monkeypatch.setattr(
        command, "open_sandboxed", lambda *a, **kw: ExecuteSpy(actual_open(*a, **kw))
    )
    outcome = command.run_query(
        _request(root, sql="SELECT 1; SELECT 2"), _env(home, index_dir.parent)
    )
    assert (
        outcome.kind,
        outcome.restriction,
        outcome.message,
        outcome.result,
        outcome.schema,
        outcome.state,
        outcome.hint,
        outcome.holder_pid,
        outcome.drift,
    ) == (
        command.OutcomeKind.REFUSED,
        Restriction.ONE_STATEMENT,
        "SELECT, SELECT",
        None,
        None,
        None,
        None,
        None,
        PageDrift(2, 2, 0, 0, 0),
    )
    assert "SELECT 1; SELECT 2" not in executed


def test_real_outside_index_refusal_preserves_backend_detail(
    indexed_root: tuple[Path, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, index_dir, home = _copy(indexed_root, tmp_path)
    csv = tmp_path / "private-outside-index.csv"
    csv.write_text("answer\n7\n", encoding="utf-8")
    sql = f"SELECT * FROM read_csv_auto('{csv}')"
    location = resolve_index_location(
        root, {"FITDOCS_INDEX_DIR": str(index_dir.parent)}, home
    )
    with (
        sandbox_module.open_sandboxed(
            location,
            pid=74123,
            monotonic=lambda: 0.0,
            sleep=lambda _delay: None,
            on_wait=lambda _pid: None,
        ) as conn,
        pytest.raises(IndexStatementError) as direct,
    ):
        conn.execute(sql)
    actual_open = command.open_sandboxed
    actual_runner = command.run_statement
    backend_sql: list[str] = []
    closed: list[bool] = []

    class BackendSpy:
        def __init__(self, conn: Any) -> None:
            self.conn = conn

        def execute(self, statement: Any, *args: Any, **kwargs: Any) -> Any:
            backend_sql.append(statement)
            return self.conn.execute(statement, *args, **kwargs)

        def close(self) -> None:
            closed.append(True)
            self.conn.close()

        def __getattr__(self, name: Any) -> Any:
            return getattr(self.conn, name)

    monkeypatch.setattr(
        command, "open_sandboxed", lambda *a, **kw: BackendSpy(actual_open(*a, **kw))
    )
    monkeypatch.setattr(command, "run_statement", actual_runner)
    outcome = command.run_query(_request(root, sql=sql), _env(home, index_dir.parent))
    assert (
        outcome.kind,
        outcome.restriction,
        outcome.message,
        outcome.result,
        outcome.schema,
        outcome.state,
        outcome.hint,
        outcome.holder_pid,
        outcome.drift,
    ) == (
        command.OutcomeKind.REFUSED,
        Restriction.OUTSIDE_INDEX,
        str(direct.value),
        None,
        None,
        None,
        None,
        None,
        PageDrift(2, 2, 0, 0, 0),
    )
    assert sql in backend_sql
    assert closed == [True]


def test_deterministic_timeout_has_no_invented_hint_and_cancels_before_close(
    indexed_root: tuple[Path, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, index_dir, home = _copy(indexed_root, tmp_path)
    events: list[str] = []
    actual_open = command.open_sandboxed

    class FiredTimer:
        def __init__(self, _timeout: float, callback: Any) -> None:
            self.callback = callback

        def start(self) -> None:
            events.append("timer-start")
            self.callback()

        def cancel(self) -> None:
            events.append("timer-cancel")

    class ConnectionSpy:
        def __init__(self, conn: Any) -> None:
            self.conn = conn
            self.interrupted = False
            self.query_phase = False

        def statement_types(self, sql: Any) -> Any:
            events.append("screen")
            self.query_phase = True
            return self.conn.statement_types(sql)

        def interrupt(self) -> None:
            events.append("interrupt")
            self.interrupted = True

        def execute(self, sql: Any, *args: Any, **kwargs: Any) -> Any:
            if not self.query_phase:
                return self.conn.execute(sql, *args, **kwargs)
            events.append("execute")
            assert self.interrupted is True
            raise IndexInterrupted("literal stopped execution")

        def close(self) -> None:
            events.append("close")
            self.conn.close()

        def __getattr__(self, name: Any) -> Any:
            return getattr(self.conn, name)

    actual_executor = statement_module.execute_statement

    def execute_statement_spy(*args: Any, **kwargs: Any) -> Any:
        events.append("execute_statement")
        return actual_executor(*args, **kwargs)

    monkeypatch.setattr(statement_module, "execute_statement", execute_statement_spy)
    monkeypatch.setattr(
        command,
        "open_sandboxed",
        lambda *args, **kwargs: ConnectionSpy(actual_open(*args, **kwargs)),
    )
    env = command.QueryEnvironment(
        {"FITDOCS_INDEX_DIR": str(index_dir.parent)},
        home,
        74123,
        lambda: 0.0,
        lambda _delay: None,
        lambda _pid: None,
        lambda _pid: False,
        FiredTimer,
    )
    outcome = command.run_query(_request(root), env)
    assert (
        outcome.kind,
        outcome.message,
        outcome.hint,
        outcome.drift,
        outcome.result,
        outcome.schema,
        outcome.state,
        outcome.restriction,
        outcome.holder_pid,
    ) == (
        command.OutcomeKind.TIMED_OUT,
        "statement ran longer than 4.25 seconds and was stopped",
        None,
        PageDrift(2, 2, 0, 0, 0),
        None,
        None,
        None,
        None,
        None,
    )
    assert events == [
        "screen",
        "execute_statement",
        "timer-start",
        "interrupt",
        "execute",
        "timer-cancel",
        "close",
    ]


@pytest.mark.parametrize("phase", ["execute", "fetch", "interrupt"])
def test_real_statement_timer_is_cancelled_before_connection_close_on_failures(
    indexed_root: tuple[Path, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    phase: str,
) -> None:
    root, index_dir, home = _copy(indexed_root, tmp_path)
    events: list[str] = []
    actual_open = command.open_sandboxed
    failure = IndexStatementError(f"literal {phase} failure")

    class FakeTimer:
        def __init__(self, _timeout: float, _callback: Any) -> None:
            pass

        def start(self) -> None:
            events.append("timer-start")

        def cancel(self) -> None:
            events.append("timer-cancel")

    class ResultFetchSpy:
        def __init__(self, result: Any) -> None:
            self.result = result
            self.columns = result.columns

        def fetchmany(self, size: int) -> Any:
            events.append("fetchmany")
            raise failure

    class ConnectionSpy:
        def __init__(self, conn: Any) -> None:
            self.conn = conn
            self.query_phase = False

        def statement_types(self, sql: Any) -> Any:
            events.append("screen")
            self.query_phase = True
            return self.conn.statement_types(sql)

        def execute(self, sql: Any, *args: Any, **kwargs: Any) -> Any:
            if not self.query_phase:
                return self.conn.execute(sql, *args, **kwargs)
            events.append("execute")
            if phase == "execute":
                raise failure
            if phase == "interrupt":
                raise KeyboardInterrupt()
            return ResultFetchSpy(self.conn.execute(sql, *args, **kwargs))

        def close(self) -> None:
            events.append("close")
            self.conn.close()

        def __getattr__(self, name: Any) -> Any:
            return getattr(self.conn, name)

    actual_executor = statement_module.execute_statement

    def execute_statement_spy(*args: Any, **kwargs: Any) -> Any:
        events.append("execute_statement")
        return actual_executor(*args, **kwargs)

    monkeypatch.setattr(statement_module, "execute_statement", execute_statement_spy)
    monkeypatch.setattr(
        command,
        "open_sandboxed",
        lambda *args, **kwargs: ConnectionSpy(actual_open(*args, **kwargs)),
    )
    env = command.QueryEnvironment(
        {"FITDOCS_INDEX_DIR": str(index_dir.parent)},
        home,
        74123,
        lambda: 0.0,
        lambda _delay: None,
        lambda _pid: None,
        lambda _pid: False,
        FakeTimer,
    )
    if phase == "interrupt":
        with pytest.raises(KeyboardInterrupt):
            command.run_query(_request(root), env)
        assert events == [
            "screen",
            "execute_statement",
            "timer-start",
            "execute",
            "timer-cancel",
            "close",
        ]
    else:
        outcome = command.run_query(_request(root), env)
        assert outcome.kind is command.OutcomeKind.FAILED
        assert outcome.message == f"literal {phase} failure"
        assert events[-2:] == ["timer-cancel", "close"]
        if phase == "fetch":
            assert events == [
                "screen",
                "execute_statement",
                "timer-start",
                "execute",
                "fetchmany",
                "timer-cancel",
                "close",
            ]
        else:
            assert events == [
                "screen",
                "execute_statement",
                "timer-start",
                "execute",
                "timer-cancel",
                "close",
            ]
    assert not (index_dir / "query-spill-74123").exists()


@pytest.mark.parametrize("sql", ["SELECT missing_column", "SELECT FROM"])
def test_binder_and_parse_failures_keep_facade_message_and_no_hint(
    indexed_root: tuple[Path, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    sql: str,
) -> None:
    root, index_dir, home = _copy(indexed_root, tmp_path)
    with (
        open_index(index_dir / "index.duckdb", read_only=True) as conn,
        pytest.raises(IndexStatementError) as direct,
    ):
        conn.execute(sql)
    close_events = _watch_close(monkeypatch)
    outcome = command.run_query(_request(root, sql=sql), _env(home, index_dir.parent))
    assert (
        outcome.kind,
        outcome.message,
        outcome.hint,
        outcome.restriction,
        outcome.result,
        outcome.drift,
        outcome.schema,
        outcome.state,
        outcome.holder_pid,
    ) == (
        command.OutcomeKind.FAILED,
        str(direct.value),
        None,
        None,
        None,
        PageDrift(2, 2, 0, 0, 0),
        None,
        None,
        None,
    )
    assert close_events == ["close"]


@pytest.mark.parametrize(
    ("hint", "expected_hint"),
    [("literal failure hint", "literal failure hint"), (None, None)],
    ids=["hint-present", "hint-absent"],
)
def test_statement_failed_preserves_literal_message_and_optional_hint(
    indexed_root: tuple[Path, Path],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    hint: str | None,
    expected_hint: str | None,
) -> None:
    from fitdocs.query.statement import StatementFailed

    root, index_dir, home = _copy(indexed_root, tmp_path)
    close_events = _watch_close(monkeypatch)
    failure = StatementFailed("literal runtime failure detail", hint)
    monkeypatch.setattr(
        command,
        "run_statement",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(failure),
    )
    outcome = command.run_query(
        _request(root, sql="SELECT 73"), _env(home, index_dir.parent)
    )
    assert (
        outcome.kind,
        outcome.message,
        outcome.hint,
        outcome.restriction,
        outcome.result,
        outcome.drift,
        outcome.schema,
        outcome.state,
        outcome.holder_pid,
    ) == (
        command.OutcomeKind.FAILED,
        "literal runtime failure detail",
        expected_hint,
        None,
        None,
        PageDrift(2, 2, 0, 0, 0),
        None,
        None,
        None,
    )
    assert close_events == ["close"]


def test_schema_uses_live_catalog_and_reports_complete_typed_state(
    indexed_root: tuple[Path, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, index_dir, home = _copy(indexed_root, tmp_path)
    with open_index(index_dir / "index.duckdb", read_only=False) as conn:
        conn.execute("UPDATE index_meta SET fitdocs_version = 'fixture-writer-9.9'")
    with open_index(index_dir / "index.duckdb", read_only=True) as conn:
        oracle_bookkeeping = read_bookkeeping(conn)
        assert oracle_bookkeeping is not None
        table_rows = conn.execute(
            "SELECT table_name FROM duckdb_tables() "
            "WHERE database_name = current_database() AND schema_name = 'main' "
            "AND NOT temporary"
        ).fetchall()
        direct_names = tuple(
            sorted(
                (str(row[0]) for row in table_rows),
                key=lambda name: (name.startswith("index_"), name),
            )
        )
        direct_counts = {
            name: int(
                cast(
                    int | str,
                    conn.execute(f'SELECT count(*) FROM "{name}"').fetchall()[0][0],
                )
            )
            for name in direct_names
        }
        pages_comment = conn.execute(
            "SELECT comment FROM duckdb_tables() WHERE table_name = 'pages' "
            "AND schema_name = 'main'"
        ).fetchall()[0][0]
        page_columns = conn.execute(
            "SELECT column_name, data_type, comment FROM duckdb_columns() "
            "WHERE table_name = 'pages' AND schema_name = 'main' "
            "ORDER BY column_index LIMIT 3"
        ).fetchall()
    events: list[str] = []
    originals = {
        name: getattr(command, name)
        for name in (
            "scan_workout_pages",
            "current_athlete_fingerprint",
            "open_sandboxed",
            "read_bookkeeping",
            "read_catalog",
            "row_counts",
            "athlete_drift",
            "page_drift",
            "corpus_fingerprints",
            "corpus_drift",
        )
    }

    class CloseSpy:
        def __init__(self, conn: Any) -> None:
            self.conn = conn

        def close(self) -> None:
            events.append("close")
            self.conn.close()

        def __getattr__(self, name: Any) -> Any:
            return getattr(self.conn, name)

    for name in (
        "scan_workout_pages",
        "current_athlete_fingerprint",
        "read_bookkeeping",
        "read_catalog",
        "row_counts",
        "athlete_drift",
        "page_drift",
        "corpus_fingerprints",
        "corpus_drift",
    ):
        original = originals[name]

        def forwarding(
            *args: Any,
            _name: str = name,
            _original: Any = original,
            **kwargs: Any,
        ) -> Any:
            events.append(_name)
            return _original(*args, **kwargs)

        monkeypatch.setattr(command, name, forwarding)

    def open_spy(*args: Any, **kwargs: Any) -> Any:
        events.append("open_sandboxed")
        return CloseSpy(originals["open_sandboxed"](*args, **kwargs))

    monkeypatch.setattr(command, "open_sandboxed", open_spy)
    monkeypatch.setattr(
        command,
        "run_statement",
        lambda *_args, **_kwargs: pytest.fail(
            "statement was executed for schema request"
        ),
    )
    assert direct_names == (
        "activities",
        "benchmark_periods",
        "benchmarks",
        "blocks",
        "channel_sources",
        "daily_load",
        "laps",
        "load_series",
        "loads",
        "mean_max",
        "mesocycles",
        "page_sources",
        "pages",
        "planned_workout_pages",
        "planned_workouts",
        "quality_flags",
        "records",
        "strength_sets",
        "unplanned_pages",
        "weekly_load",
        "zone_times",
        "index_meta",
        "index_pages",
        "index_producers",
    )
    assert direct_counts["pages"] == 2
    assert direct_counts["index_meta"] == 1
    assert direct_counts["index_pages"] == 2
    assert direct_counts["index_producers"] == 6
    assert (
        pages_comment == "one row per workout page; the page's frontmatter as recorded."
    )
    assert page_columns == [
        (
            "page_key",
            "VARCHAR",
            "Key of the workout page: the SHA-256 (64 hex) of the page's base file, "
            "the last file its sources list.",
        ),
        ("path", "VARCHAR", "data-root-relative POSIX path"),
        ("title", "VARCHAR", "Workout page title"),
    ]
    with open_index(index_dir / "index.duckdb", read_only=False) as conn:
        conn.execute(
            "UPDATE activities SET athlete_fingerprint = "
            "'fixture-stale-athlete-fingerprint'"
        )
        stale_activities = cast(
            int, conn.execute("SELECT count(*) FROM activities").fetchall()[0][0]
        )
    assert stale_activities > 0
    inventory_before = _filesystem_inventory(root, index_dir)
    outcome = command.run_query(
        _request(root, sql=None, schema=True), _env(home, index_dir.parent)
    )
    assert outcome.kind is command.OutcomeKind.SCHEMA
    assert outcome.schema is not None
    assert (
        outcome.schema.state.database,
        outcome.schema.state.recorded_schema_version,
        outcome.schema.state.reads_schema_version,
        outcome.schema.state.fitdocs_version,
        tuple(table.name for table in outcome.schema.tables),
        outcome.schema.counts,
    ) == (
        index_dir / "index.duckdb",
        2,
        2,
        "fixture-writer-9.9",
        direct_names,
        direct_counts,
    )
    pages_table = next(
        table for table in outcome.schema.tables if table.name == "pages"
    )
    assert (
        pages_table.description,
        tuple(
            (column.name, column.type_name, column.description)
            for column in pages_table.columns[:3]
        ),
    ) == (
        "one row per workout page; the page's frontmatter as recorded.",
        tuple(
            (name, type_name, description)
            for name, type_name, description in page_columns
        ),
    )
    assert outcome.schema.state.athlete is not None
    assert outcome.schema.state.corpus is not None
    assert (
        outcome.schema.state.drift,
        outcome.schema.state.left_out,
        outcome.schema.state.without_computed,
        outcome.schema.state.athlete.activities_other_inputs,
        outcome.schema.state.athlete.skipped_reason,
        outcome.schema.state.corpus.behind,
        outcome.schema.state.corpus.unassessed,
        outcome.schema.state.rebuild_reason,
    ) == (
        PageDrift(2, 2, 0, 0, 0),
        (),
        {},
        stale_activities,
        None,
        (),
        (),
        None,
    )
    assert events == [
        "scan_workout_pages",
        "current_athlete_fingerprint",
        "open_sandboxed",
        "read_bookkeeping",
        "read_catalog",
        "row_counts",
        "athlete_drift",
        "close",
        "page_drift",
        "corpus_fingerprints",
        "corpus_drift",
    ]
    assert _filesystem_inventory(root, index_dir) == inventory_before
    assert outcome.result is None and outcome.drift is None and outcome.state is None
    assert oracle_bookkeeping.meta.schema_version == 2


def _page_copy_with_key(root: Path, source: Path, target_name: str, key: str) -> Path:
    target = source.with_name(target_name)
    shutil.copy2(source, target)
    lines = target.read_text(encoding="utf-8").splitlines()
    source_lines = [
        index
        for index, line in enumerate(lines)
        if line.strip().startswith("-") and ".fit" in line
    ]
    assert source_lines
    index = source_lines[-1]
    prefix, _, suffix = lines[index].rpartition("/")
    basename = suffix.strip().strip("\"'")
    assert basename.endswith(".fit")
    lines[index] = f"{prefix}/{key}.fit"
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return target


def test_schema_pins_all_noncomputed_state_counts_and_duplicate_base(
    indexed_root: tuple[Path, Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root, index_dir, home = _copy(indexed_root, tmp_path)
    database = index_dir / "index.duckdb"
    close_events = _watch_close(monkeypatch)
    monkeypatch.setattr(
        command,
        "run_statement",
        lambda *_args, **_kwargs: pytest.fail(
            "statement was executed for schema request"
        ),
    )
    source = sorted((root / "workouts").glob("*.md"))[0]
    lines = source.read_text(encoding="utf-8").splitlines()
    source_lines = [
        line for line in lines if line.strip().startswith("-") and ".fit" in line
    ]
    assert source_lines
    existing_key = Path(source_lines[-1].strip().strip("\"'").rsplit("/", 1)[-1]).stem
    assert len(existing_key) == 64 and all(
        char in "0123456789abcdef" for char in existing_key
    )
    existing_archive = archive_path(root, existing_key)
    assert existing_archive.is_file()
    existing_archive.unlink()
    duplicate = _page_copy_with_key(root, source, "00-duplicate.md", existing_key)

    unreadable_keys = ("b" * 64, "c" * 64)
    undecodable_keys = ("d" * 64, "e" * 64, "f" * 64)
    unreadable_archives: set[Path] = set()
    for index, key in enumerate(unreadable_keys):
        _page_copy_with_key(root, source, f"10-unreadable-{index}.md", key)
        archive = archive_path(root, key)
        archive.parent.mkdir(parents=True, exist_ok=True)
        archive.write_bytes(b"intentionally unreadable test archive")
        unreadable_archives.add(archive)
    for index, key in enumerate(undecodable_keys):
        _page_copy_with_key(root, source, f"20-undecodable-{index}.md", key)
        archive = archive_path(root, key)
        archive.parent.mkdir(parents=True, exist_ok=True)
        archive.write_bytes(b"not a FIT archive")

    original_read_bytes = Path.read_bytes

    def deny_unreadable(candidate: Path) -> bytes:
        if candidate in unreadable_archives:
            raise PermissionError("literal private test archive denial")
        return original_read_bytes(candidate)

    with monkeypatch.context() as scoped:
        scoped.setattr(Path, "read_bytes", deny_unreadable)
        report = build.run_index_command(
            root,
            environ={"FITDOCS_INDEX_DIR": str(index_dir.parent)},
            home=home,
            athlete=load_athlete_inputs(root),
            today=FIXTURE_TODAY,
            rebuild=True,
            progress=None,
        )
    assert report.outcome.value in {"built", "refreshed", "unchanged"}
    with open_index(index_dir / "index.duckdb", read_only=True) as conn:
        held = read_bookkeeping(conn)
    assert held is not None
    assert (
        sum(
            state.computed_state.value == "source_missing"
            for state in held.pages.values()
        )
        == 1
    )
    assert (
        sum(
            state.computed_state.value == "source_unreadable"
            for state in held.pages.values()
        )
        == 2
    )
    assert (
        sum(
            state.computed_state.value == "source_undecodable"
            for state in held.pages.values()
        )
        == 3
    )
    assert (
        sum(state.computed_state.value == "computed" for state in held.pages.values())
        >= 1
    )

    inventory_before = _filesystem_inventory(root, index_dir)
    outcome = command.run_query(
        _request(root, sql=None, schema=True), _env(home, index_dir.parent)
    )
    assert outcome.kind is command.OutcomeKind.SCHEMA
    assert outcome.schema is not None
    assert (
        outcome.schema.state.without_computed,
        tuple(
            (page.path, page.reason, page.collides_with)
            for page in outcome.schema.state.left_out
        ),
        "computed" in outcome.schema.state.without_computed,
    ) == (
        {
            "source_missing": 1,
            "source_unreadable": 2,
            "source_undecodable": 3,
        },
        (
            (
                source.relative_to(root).as_posix(),
                "duplicate_base",
                duplicate.relative_to(root).as_posix(),
            ),
        ),
        False,
    )
    assert close_events == ["close"]
    assert _filesystem_inventory(root, index_dir) == inventory_before

    # A readable but incompatible index still reports observations available
    # before it was rejected: the scan's duplicate-base finding and the
    # bookkeeping's non-computed producer states.
    with open_index(index_dir / "index.duckdb", read_only=False) as conn:
        conn.execute("UPDATE index_meta SET schema_version = 99")
    rejected = command.run_query(
        _request(root, sql=None, schema=True), _env(home, index_dir.parent)
    )
    assert rejected.state is not None
    mismatch_reason = "index schema version 99 differs from readable schema version 2"
    assert (
        rejected.kind,
        rejected.message,
        rejected.result,
        rejected.drift,
        rejected.schema,
        rejected.state.database,
        rejected.state.recorded_schema_version,
        rejected.state.reads_schema_version,
        tuple(
            (page.path, page.reason, page.collides_with)
            for page in rejected.state.left_out
        ),
        rejected.state.without_computed,
        rejected.state.athlete,
        rejected.state.corpus,
        rejected.state.rebuild_reason,
        rejected.restriction,
        rejected.hint,
        rejected.holder_pid,
    ) == (
        command.OutcomeKind.NEEDS_REBUILD,
        mismatch_reason,
        None,
        PageDrift(7, 7, 0, 0, 0),
        None,
        database,
        99,
        2,
        (
            (
                source.relative_to(root).as_posix(),
                "duplicate_base",
                duplicate.relative_to(root).as_posix(),
            ),
        ),
        {
            "source_missing": 1,
            "source_unreadable": 2,
            "source_undecodable": 3,
        },
        None,
        None,
        mismatch_reason,
        None,
        None,
        None,
    )
    assert close_events == ["close", "close"]


def test_location_error_propagates_before_any_owned_operation(
    tmp_path: Path, home_dir: HomeDirectory, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "data"
    root.mkdir()
    home = home_dir.path
    env = _env(home, root / "inside-cache")
    marker = IndexLocationError("literal invalid index location")
    monkeypatch.setattr(
        command,
        "resolve_index_location",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(marker),
    )
    monkeypatch.setattr(
        command,
        "remove_stale_spill",
        lambda *_args, **_kwargs: pytest.fail("spill cleanup after location error"),
    )
    with pytest.raises(IndexLocationError) as raised:
        command.run_query(_request(root), env)
    assert raised.value is marker
    assert tuple(home.iterdir()) == ()
