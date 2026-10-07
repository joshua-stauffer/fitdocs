from __future__ import annotations

import hashlib
import inspect
import multiprocessing
import shutil
from collections.abc import Callable, Iterator, Mapping
from contextlib import AbstractContextManager, contextmanager
from dataclasses import FrozenInstanceError, fields
from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import Any, cast, get_type_hints

import pytest

from fitdocs.athlete import AthleteFileError, load_athlete_inputs
from fitdocs.index import refresh
from fitdocs.index.bookkeeping import Bookkeeping, ComputedState, IndexMeta
from fitdocs.index.corpus import LeftOutPage
from fitdocs.index.handoff import HandoffCollector
from fitdocs.index.location import IndexLocation, resolve_index_location
from fitdocs.index.refresh import (
    IndexReport,
    Outcome,
    RefreshResult,
    refresh_after_command,
)
from fitdocs.index.schema import SCHEMA_VERSION, TableScope
from fitdocs.index.store import (
    FaultKind,
    IndexConnection,
    IndexFault,
    IndexOpenError,
    open_index,
    read_bookkeeping,
    write_meta,
    write_producer_state,
)
from fitdocs.metrics.types import AthleteInputs
from tests.index._helpers import forge_storage_version, hold_index
from tests.index.conftest import BuiltIndex

_OPEN_INDEX_ATTRIBUTE = "open_index"
_WRITER_LOCK_ATTRIBUTE = "writer_lock"
_LOAD_ATHLETE_ATTRIBUTE = "load_athlete_inputs"
_READ_BOOKKEEPING_ATTRIBUTE = "read_bookkeeping"


def _environment(tmp_path: Path) -> dict[str, str]:
    return {"FITDOCS_INDEX_DIR": str(tmp_path / "index-cache")}


def _location(
    data_root: Path, tmp_path: Path
) -> tuple[IndexLocation, dict[str, str], Path]:
    environ = _environment(tmp_path)
    home = tmp_path / "home-not-created"
    return resolve_index_location(data_root, environ, home), environ, home


def _copy_built_index(
    built_index: BuiltIndex, tmp_path: Path
) -> tuple[IndexLocation, dict[str, str], Path]:
    location, environ, home = _location(built_index.data_root, tmp_path)
    location.directory.mkdir(parents=True)
    shutil.copy2(built_index.database, location.database)
    return location, environ, home


def _refresh(
    data_root: Path,
    environ: Mapping[str, str],
    home: Path,
    *,
    today: date = date(2037, 4, 19),
    progress: refresh.ProgressCallback | None = None,
) -> IndexReport:
    return refresh_after_command(
        data_root,
        environ=environ,
        home=home,
        handoff=None,
        today=today,
        progress=progress,
    )


def _hold_writer_lock_process(path: str, ready: Any, release: Any) -> None:
    from fitdocs.index.lock import writer_lock

    with writer_lock(Path(path)):
        ready.set()
        release.wait(15)


def test_report_contract_and_outcome_vocabulary() -> None:
    assert [field.name for field in fields(IndexReport)] == [
        "outcome",
        "location",
        "detail",
        "holder_pid",
        "result",
    ]
    assert [item.value for item in Outcome] == [
        "refreshed",
        "unchanged",
        "built",
        "not_built",
        "needs_rebuild",
        "busy",
        "staged",
        "failed",
    ]
    assert dict(Outcome.__members__) == {
        "REFRESHED": "refreshed",
        "UNCHANGED": "unchanged",
        "BUILT": "built",
        "NOT_BUILT": "not_built",
        "NEEDS_REBUILD": "needs_rebuild",
        "BUSY": "busy",
        "STAGED": "staged",
        "FAILED": "failed",
    }
    assert issubclass(Outcome, StrEnum)
    assert all(type(item.value) is str for item in Outcome)
    report = IndexReport(Outcome.NOT_BUILT, None, None, None, None)
    with pytest.raises(FrozenInstanceError):
        cast(object, report).detail = "changed"  # type: ignore[attr-defined]
    assert get_type_hints(IndexReport) == {
        "outcome": Outcome,
        "location": IndexLocation | None,
        "detail": str | None,
        "holder_pid": int | None,
        "result": refresh.RefreshResult | None,
    }
    expected_hints = {
        "data_root": Path,
        "environ": Mapping[str, str],
        "home": Path,
        "handoff": HandoffCollector | None,
        "today": date,
        "progress": Callable[[int, int], None] | None,
        "return": IndexReport,
    }
    assert get_type_hints(refresh_after_command) == expected_hints
    signature = inspect.signature(refresh_after_command)
    assert tuple(signature.parameters) == (
        "data_root",
        "environ",
        "home",
        "handoff",
        "today",
        "progress",
    )
    assert all(
        signature.parameters[name].kind is inspect.Parameter.KEYWORD_ONLY
        for name in ("environ", "home", "handoff", "today", "progress")
    )
    assert (
        signature.parameters["data_root"].kind
        is inspect.Parameter.POSITIONAL_OR_KEYWORD
    )


def test_missing_index_returns_not_built_without_creating_any_directory(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "data"
    data_root.mkdir()
    location, environ, home = _location(data_root, tmp_path)
    (data_root / "athlete.toml").write_text("ftp_watts = [\n")
    assert not location.directory.exists()
    report = _refresh(data_root, environ, home)
    assert report == IndexReport(Outcome.NOT_BUILT, location, None, None, None)
    assert not location.directory.exists()
    assert not location.base_dir.exists()
    assert not home.exists()


def test_relative_index_directory_is_reported_as_failed_without_writes(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "data"
    data_root.mkdir()
    environ = {"FITDOCS_INDEX_DIR": "relative-index"}
    report = _refresh(data_root, environ, tmp_path / "home")
    assert report.outcome is Outcome.FAILED
    assert report.location is None
    assert report.detail == (
        "IndexLocationError: FITDOCS_INDEX_DIR='relative-index' is not an absolute path"
    )
    assert report.holder_pid is None
    assert report.result is None
    assert tuple(data_root.iterdir()) == ()


def test_index_directory_inside_data_root_is_failed_without_writes(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "data"
    data_root.mkdir()
    cache_base = data_root / "cache"
    key = f"data-{hashlib.sha256(str(data_root.resolve()).encode()).hexdigest()[:16]}"
    expected_directory = cache_base / key
    environ = {"FITDOCS_INDEX_DIR": str(cache_base)}
    report = _refresh(data_root, environ, tmp_path / "home")
    assert report.outcome is Outcome.FAILED
    assert report.location is None
    assert report.detail == (
        f"IndexLocationError: index directory {expected_directory} is the data root "
        f"{data_root} or lies inside it"
    )
    assert tuple(data_root.iterdir()) == ()


def test_empty_environment_uses_the_supplied_home_without_creating_directories(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "home-fallback-data"
    home = tmp_path / "synthetic-home"
    data_root.mkdir()
    resolved_root = data_root.resolve()
    expected_base = (home / ".cache" / "fitdocs" / "index").resolve()
    digest = hashlib.sha256(str(resolved_root).encode("utf-8")).hexdigest()[:16]
    expected_directory = (expected_base / f"home-fallback-data-{digest}").resolve()
    expected_location = IndexLocation(
        data_root=resolved_root,
        base_dir=expected_base,
        directory=expected_directory,
        database=expected_directory / "index.duckdb",
        wal=expected_directory / "index.duckdb.wal",
        lock=expected_directory / "index.lock",
        building=expected_directory / "index.duckdb.building",
        staged=expected_directory / "index.duckdb.rebuilt",
    )

    report = _refresh(data_root, {}, home)

    assert report == IndexReport(Outcome.NOT_BUILT, expected_location, None, None, None)
    assert not home.exists()
    assert not expected_base.exists()


def test_writer_lock_returns_busy_without_waiting(
    built_index: BuiltIndex,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    location, environ, home = _copy_built_index(built_index, tmp_path)
    (built_index.data_root / "athlete.toml").write_text("ftp_watts = [\n")
    original_open = cast(
        Callable[..., IndexConnection], getattr(refresh, _OPEN_INDEX_ATTRIBUTE)
    )
    original_load_athlete = cast(
        Callable[[Path], AthleteInputs | None],
        getattr(refresh, _LOAD_ATHLETE_ATTRIBUTE),
    )
    original_reconcile = refresh.reconcile
    open_calls: list[Path] = []
    athlete_calls: list[Path] = []
    reconcile_calls: list[refresh.RefreshInputs] = []

    def observe_open(path: Path, **kwargs: object) -> IndexConnection:
        open_calls.append(path)
        return original_open(path, **kwargs)

    def observe_athlete(data_root: Path) -> AthleteInputs | None:
        athlete_calls.append(data_root)
        return original_load_athlete(data_root)

    def observe_reconcile(
        conn: IndexConnection,
        bookkeeping: Bookkeeping,
        inputs: refresh.RefreshInputs,
    ) -> RefreshResult:
        reconcile_calls.append(inputs)
        return original_reconcile(conn, bookkeeping, inputs)

    context = multiprocessing.get_context("spawn")
    ready = context.Event()
    release = context.Event()
    process = context.Process(
        target=_hold_writer_lock_process,
        args=(str(location.lock), ready, release),
    )
    with monkeypatch.context() as scoped:
        scoped.setattr(refresh, "open_index", observe_open)
        scoped.setattr(refresh, _LOAD_ATHLETE_ATTRIBUTE, observe_athlete)
        scoped.setattr(refresh, "reconcile", observe_reconcile)
        process.start()
        try:
            assert ready.wait(5), "writer-lock child did not acquire the advisory lock"
            report = _refresh(built_index.data_root, environ, home)
        finally:
            release.set()
            process.join(5)
            assert not process.is_alive(), "writer-lock child was not reaped"
            assert process.exitcode == 0
    assert getattr(refresh, _OPEN_INDEX_ATTRIBUTE) is original_open
    assert getattr(refresh, _LOAD_ATHLETE_ATTRIBUTE) is original_load_athlete
    assert refresh.reconcile is original_reconcile
    assert open_calls == []
    assert athlete_calls == []
    assert reconcile_calls == []
    assert report.outcome is Outcome.BUSY
    assert report.location == location
    assert report.detail == f"writer lock is held for {location.lock}"
    assert report.holder_pid is None
    assert report.result is None


def test_duckdb_lock_returns_busy_with_holder_pid(
    built_index: BuiltIndex, tmp_path: Path
) -> None:
    location, environ, home = _copy_built_index(built_index, tmp_path)
    with hold_index(location.database, read_only=False) as holder_pid:
        report = _refresh(built_index.data_root, environ, home)
        assert report.outcome is Outcome.BUSY
        assert report.location == location
        assert report.detail is not None
        assert "Could not set lock on file" in report.detail
        assert report.holder_pid == holder_pid
        assert report.result is None


@pytest.mark.parametrize(
    ("kind", "detail_fragment"),
    [
        ("junk", "not a valid DuckDB database file"),
        ("incompatible", "Trying to read a database file with version number"),
        ("missing_meta", "not a complete fitdocs index"),
        ("schema", f"schema version 99; this fitdocs uses {SCHEMA_VERSION}"),
    ],
)
def test_unusable_index_reports_rebuild_reason_and_preserves_bytes(
    built_index: BuiltIndex,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    kind: str,
    detail_fragment: str,
) -> None:
    location, environ, home = _copy_built_index(built_index, tmp_path)
    if kind == "junk":
        location.database.write_bytes(b"not a DuckDB index\x00")
    elif kind == "incompatible":
        forge_storage_version(location.database, 69)
    elif kind == "missing_meta":
        with open_index(location.database, read_only=False) as conn:
            conn.execute("DROP TABLE index_meta")
    elif kind == "schema":
        with open_index(location.database, read_only=False) as conn:
            current = read_bookkeeping(conn)
            assert current is not None
            write_meta(
                conn,
                IndexMeta(
                    schema_version=99,
                    fitdocs_version=current.meta.fitdocs_version,
                    duckdb_version=current.meta.duckdb_version,
                    data_root=current.meta.data_root,
                    athlete_fingerprint=current.meta.athlete_fingerprint,
                ),
            )
    else:  # pragma: no cover - parametrization is exhaustive.
        raise AssertionError(kind)
    before = location.database.read_bytes()
    if kind in {"missing_meta", "schema"}:
        (built_index.data_root / "athlete.toml").write_text("ftp_watts = [\n")
    if kind == "missing_meta":
        original_load_athlete = cast(
            Callable[[Path], AthleteInputs | None],
            getattr(refresh, _LOAD_ATHLETE_ATTRIBUTE),
        )
        original_reconcile = refresh.reconcile
        athlete_calls: list[Path] = []
        reconcile_calls: list[refresh.RefreshInputs] = []

        def observe_athlete(data_root: Path) -> AthleteInputs | None:
            athlete_calls.append(data_root)
            return original_load_athlete(data_root)

        def observe_reconcile(
            conn: IndexConnection,
            bookkeeping: Bookkeeping,
            inputs: refresh.RefreshInputs,
        ) -> RefreshResult:
            reconcile_calls.append(inputs)
            return original_reconcile(conn, bookkeeping, inputs)

        with monkeypatch.context() as scoped:
            scoped.setattr(refresh, _LOAD_ATHLETE_ATTRIBUTE, observe_athlete)
            scoped.setattr(refresh, "reconcile", observe_reconcile)
            report = _refresh(built_index.data_root, environ, home)
        assert getattr(refresh, _LOAD_ATHLETE_ATTRIBUTE) is original_load_athlete
        assert refresh.reconcile is original_reconcile
        assert athlete_calls == []
        assert reconcile_calls == []
    else:
        report = _refresh(built_index.data_root, environ, home)
    assert report.outcome is Outcome.NEEDS_REBUILD
    assert report.location == location
    assert report.detail is not None and detail_fragment in report.detail
    assert report.holder_pid is None
    assert report.result is None
    assert location.database.read_bytes() == before


@pytest.mark.parametrize(
    ("kind", "outcome", "message", "holder_pid"),
    [
        (FaultKind.MISSING, Outcome.NOT_BUILT, "Missing synthetic index", None),
        (
            FaultKind.INCOMPATIBLE,
            Outcome.NEEDS_REBUILD,
            "Trying to read a database file with version number 69",
            None,
        ),
        (
            FaultKind.CORRUPT,
            Outcome.NEEDS_REBUILD,
            "Corrupt database file: synthetic cause",
            None,
        ),
        (FaultKind.OTHER, Outcome.NEEDS_REBUILD, "unknown open error", None),
        (FaultKind.LOCKED, Outcome.BUSY, "lock held; no PID was reported", None),
        (FaultKind.LOCKED, Outcome.BUSY, "Could not set lock (PID 28173)", 28173),
    ],
)
def test_open_fault_kinds_map_to_report_outcomes(
    built_index: BuiltIndex,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    kind: FaultKind,
    outcome: Outcome,
    message: str,
    holder_pid: int | None,
) -> None:
    location, environ, home = _copy_built_index(built_index, tmp_path)
    before = location.database.read_bytes()
    original_open = cast(
        Callable[..., IndexConnection], getattr(refresh, _OPEN_INDEX_ATTRIBUTE)
    )
    fault = IndexFault(kind, message, holder_pid)

    def raise_fault(*_args: object, **_kwargs: object) -> IndexConnection:
        raise IndexOpenError(fault)

    with monkeypatch.context() as scoped:
        scoped.setattr(refresh, "open_index", raise_fault)
        report = _refresh(built_index.data_root, environ, home)
    assert getattr(refresh, _OPEN_INDEX_ATTRIBUTE) is original_open
    assert report == IndexReport(outcome, location, message, holder_pid, None)
    assert location.database.read_bytes() == before


@pytest.mark.parametrize(
    "exit_path",
    [
        "normal",
        "open_fault",
        "missing_meta",
        "schema",
        "athlete_error",
        "reconcile_error",
        "interrupt",
    ],
)
def test_connection_and_writer_lock_contexts_close_on_applicable_paths(
    built_index: BuiltIndex,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    exit_path: str,
) -> None:
    location, environ, home = _copy_built_index(built_index, tmp_path)
    sentinel: BaseException | None = None
    if exit_path == "missing_meta":
        with open_index(location.database, read_only=False) as conn:
            conn.execute("DROP TABLE index_meta")
        (built_index.data_root / "athlete.toml").write_text("ftp_watts = [\n")
    elif exit_path == "schema":
        with open_index(location.database, read_only=False) as conn:
            current = read_bookkeeping(conn)
            assert current is not None
            write_meta(
                conn,
                IndexMeta(
                    schema_version=99,
                    fitdocs_version=current.meta.fitdocs_version,
                    duckdb_version=current.meta.duckdb_version,
                    data_root=current.meta.data_root,
                    athlete_fingerprint=current.meta.athlete_fingerprint,
                ),
            )
        (built_index.data_root / "athlete.toml").write_text("ftp_watts = [\n")
    elif exit_path == "athlete_error":
        (built_index.data_root / "athlete.toml").write_text("ftp_watts = [\n")
    elif exit_path == "reconcile_error":
        sentinel = RuntimeError("cleanup path sentinel")
    elif exit_path == "interrupt":
        sentinel = KeyboardInterrupt("cleanup interrupt sentinel")
    elif exit_path == "open_fault":
        sentinel = IndexOpenError(
            IndexFault(FaultKind.OTHER, "cleanup synthetic open fault", None)
        )
    original_open = cast(
        Callable[..., IndexConnection], getattr(refresh, _OPEN_INDEX_ATTRIBUTE)
    )
    original_lock = cast(
        Callable[[Path], AbstractContextManager[None]],
        getattr(refresh, _WRITER_LOCK_ATTRIBUTE),
    )
    original_enter = IndexConnection.__enter__
    original_exit = IndexConnection.__exit__
    original_close = IndexConnection.close
    original_reconcile = refresh.reconcile
    opened: list[IndexConnection] = []
    connection_events: list[str] = []
    lock_events: list[str] = []

    def observe_open(path: Path, **kwargs: object) -> IndexConnection:
        if exit_path == "open_fault":
            assert isinstance(sentinel, IndexOpenError)
            raise sentinel
        connection = original_open(path, **kwargs)
        opened.append(connection)
        return connection

    def observe_enter(connection: IndexConnection) -> IndexConnection:
        connection_events.append("enter")
        return original_enter(connection)

    def observe_exit(connection: IndexConnection, *exc: object) -> None:
        connection_events.append("exit")
        original_exit(connection, *exc)

    def observe_close(connection: IndexConnection) -> None:
        connection_events.append("close")
        original_close(connection)

    @contextmanager
    def observe_lock(path: Path) -> Iterator[None]:
        lock_events.append("enter")
        try:
            with original_lock(path):
                yield
        finally:
            lock_events.append("exit")

    def raise_reconcile(*_args: object) -> RefreshResult:
        assert sentinel is not None
        raise sentinel

    interrupted: KeyboardInterrupt | None = None
    report: IndexReport | None = None
    try:
        with monkeypatch.context() as scoped:
            scoped.setattr(refresh, _OPEN_INDEX_ATTRIBUTE, observe_open)
            scoped.setattr(refresh, _WRITER_LOCK_ATTRIBUTE, observe_lock)
            scoped.setattr(IndexConnection, "__enter__", observe_enter)
            scoped.setattr(IndexConnection, "__exit__", observe_exit)
            scoped.setattr(IndexConnection, "close", observe_close)
            if exit_path in {"reconcile_error", "interrupt"}:
                scoped.setattr(refresh, "reconcile", raise_reconcile)
            if exit_path == "interrupt":
                with pytest.raises(KeyboardInterrupt) as captured:
                    _refresh(built_index.data_root, environ, home)
                interrupted = captured.value
            else:
                report = _refresh(built_index.data_root, environ, home)
        assert getattr(refresh, _OPEN_INDEX_ATTRIBUTE) is original_open
        assert getattr(refresh, _WRITER_LOCK_ATTRIBUTE) is original_lock
        assert IndexConnection.__enter__ is original_enter
        assert IndexConnection.__exit__ is original_exit
        assert IndexConnection.close is original_close
        assert refresh.reconcile is original_reconcile
        assert len(opened) == (0 if exit_path == "open_fault" else 1)
        if exit_path == "open_fault":
            assert connection_events == []
        else:
            assert connection_events == ["enter", "exit", "close"]
        assert lock_events == ["enter", "exit"]
        if exit_path == "interrupt":
            assert interrupted is sentinel
        else:
            assert report is not None
            if exit_path == "normal":
                assert report.outcome in {Outcome.REFRESHED, Outcome.UNCHANGED}
            elif exit_path in {"missing_meta", "schema"}:
                assert report.outcome is Outcome.NEEDS_REBUILD
            elif exit_path == "athlete_error":
                assert report.outcome is Outcome.FAILED
            elif exit_path == "open_fault":
                assert report == IndexReport(
                    Outcome.NEEDS_REBUILD,
                    location,
                    "cleanup synthetic open fault",
                    None,
                    None,
                )
            else:
                assert report == IndexReport(
                    Outcome.FAILED,
                    location,
                    "RuntimeError: cleanup path sentinel",
                    None,
                    None,
                )
    finally:
        if opened and "close" not in connection_events:
            original_close(opened[0])


def test_malformed_athlete_profile_returns_complete_failed_report(
    built_index: BuiltIndex,
    tmp_path: Path,
) -> None:
    location, environ, home = _copy_built_index(built_index, tmp_path)
    profile = built_index.data_root / "athlete.toml"
    profile.write_text("ftp_watts = [\n")
    before = location.database.read_bytes()
    with pytest.raises(AthleteFileError) as expected_error:
        load_athlete_inputs(built_index.data_root)
    assert type(expected_error.value) is AthleteFileError
    assert "athlete.toml" in str(expected_error.value)
    expected_detail = f"AthleteFileError: {expected_error.value}"

    report = _refresh(built_index.data_root, environ, home)

    assert report == IndexReport(
        Outcome.FAILED,
        location,
        expected_detail,
        None,
        None,
    )
    assert report.holder_pid is None
    assert report.result is None
    assert location.database.read_bytes() == before


def test_reconcile_exception_returns_failed_and_keyboard_interrupt_propagates(
    built_index: BuiltIndex,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    location, environ, home = _copy_built_index(built_index, tmp_path)
    original_reconcile = refresh.reconcile
    sentinel = RuntimeError("reconcile sentinel")
    with monkeypatch.context() as scoped:
        scoped.setattr(
            refresh, "reconcile", lambda *_args: (_ for _ in ()).throw(sentinel)
        )
        report = _refresh(built_index.data_root, environ, home)
    assert refresh.reconcile is original_reconcile
    assert report == IndexReport(
        Outcome.FAILED, location, "RuntimeError: reconcile sentinel", None, None
    )
    interrupted = KeyboardInterrupt("stop now")
    with monkeypatch.context() as scoped:
        scoped.setattr(
            refresh, "reconcile", lambda *_args: (_ for _ in ()).throw(interrupted)
        )
        with pytest.raises(KeyboardInterrupt) as captured:
            _refresh(built_index.data_root, environ, home)
    assert captured.value is interrupted
    assert refresh.reconcile is original_reconcile


def test_reconcile_receives_authoritative_populated_bookkeeping(
    built_index: BuiltIndex,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    location, environ, home = _copy_built_index(built_index, tmp_path)
    with open_index(location.database, read_only=False) as conn:
        write_producer_state(
            conn,
            "review.synthetic.computed",
            TableScope.COMPUTED,
            ("sentinel_z", "sentinel_a"),
            "fingerprint-review-synthetic-8261",
        )
        write_producer_state(
            conn,
            "review.synthetic.document",
            TableScope.DOCUMENT,
            ("document_z", "document_a"),
            "fingerprint-review-document-4197",
        )
        expected_bookkeeping = read_bookkeeping(conn)
    assert expected_bookkeeping is not None
    expected_producers = dict(expected_bookkeeping.producers)
    assert expected_producers == {
        "review.synthetic.computed": "fingerprint-review-synthetic-8261",
        "review.synthetic.document": "fingerprint-review-document-4197",
    }

    original_read = cast(
        Callable[[IndexConnection], Bookkeeping | None],
        getattr(refresh, _READ_BOOKKEEPING_ATTRIBUTE),
    )
    original_reconcile = refresh.reconcile
    read_results: list[tuple[IndexConnection, Bookkeeping | None]] = []
    reconcile_inputs: list[tuple[IndexConnection, Bookkeeping]] = []
    unchanged_result = RefreshResult((), (), (), (), (), (), (), (), 17)

    def observe_read(conn: IndexConnection) -> Bookkeeping | None:
        result = original_read(conn)
        read_results.append((conn, result))
        return result

    def capture_reconcile(
        conn: IndexConnection,
        bookkeeping: Bookkeeping,
        inputs: refresh.RefreshInputs,
    ) -> RefreshResult:
        del inputs
        reconcile_inputs.append((conn, bookkeeping))
        return unchanged_result

    with monkeypatch.context() as scoped:
        scoped.setattr(refresh, _READ_BOOKKEEPING_ATTRIBUTE, observe_read)
        scoped.setattr(refresh, "reconcile", capture_reconcile)
        report = _refresh(built_index.data_root, environ, home)
    assert getattr(refresh, _READ_BOOKKEEPING_ATTRIBUTE) is original_read
    assert refresh.reconcile is original_reconcile
    assert len(read_results) == len(reconcile_inputs) == 1
    read_connection, read_value = read_results[0]
    reconcile_connection, reconcile_value = reconcile_inputs[0]
    assert read_value is not None
    assert reconcile_connection is read_connection
    assert reconcile_value is read_value
    assert reconcile_value == expected_bookkeeping
    assert dict(reconcile_value.producers) == expected_producers
    assert report == IndexReport(
        Outcome.UNCHANGED, location, None, None, unchanged_result
    )
    assert report.result is unchanged_result


def test_healthy_refresh_reports_refresh_then_unchanged_and_forwards_inputs(
    built_index: BuiltIndex,
    synced_corpus: Path,
    synced_workout_pages: tuple[Path, ...],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    shutil.copytree(synced_corpus, built_index.data_root, dirs_exist_ok=True)
    location, environ, home = _copy_built_index(built_index, tmp_path)
    (built_index.data_root / "athlete.toml").write_text(
        "ftp_watts = 277.0\nresting_hr_bpm = 47\nmax_hr_bpm = 193\n"
    )
    handoff = HandoffCollector()
    today = date(2041, 9, 23)

    def progress(done: int, total: int) -> None:
        del done, total

    expected_profile = AthleteInputs(ftp_watts=277.0, resting_hr_bpm=47, max_hr_bpm=193)
    original_reconcile = refresh.reconcile
    seen_inputs: list[refresh.RefreshInputs] = []

    def capture(
        conn: IndexConnection,
        bookkeeping: Bookkeeping,
        inputs: refresh.RefreshInputs,
    ) -> RefreshResult:
        seen_inputs.append(inputs)
        return original_reconcile(conn, bookkeeping, inputs)

    with monkeypatch.context() as scoped:
        scoped.setattr(refresh, "reconcile", capture)
        report = refresh_after_command(
            built_index.data_root,
            environ=environ,
            home=home,
            handoff=handoff,
            today=today,
            progress=progress,
        )
    assert refresh.reconcile is original_reconcile
    assert len(seen_inputs) == 1
    assert seen_inputs[0].data_root == built_index.data_root
    assert seen_inputs[0].athlete == expected_profile
    assert seen_inputs[0].handoff is handoff
    assert seen_inputs[0].today is today
    assert seen_inputs[0].progress is progress
    assert report.outcome is Outcome.REFRESHED
    assert report.location == location
    assert report.detail is None
    assert report.holder_pid is None
    assert report.result is not None
    expected_added = tuple(
        path.relative_to(synced_corpus).as_posix() for path in synced_workout_pages
    )
    assert report.result == RefreshResult(
        added=expected_added,
        updated=(),
        removed=(),
        without_computed=(),
        page_errors=(),
        producer_errors=(),
        left_out=(),
        corpus_refreshed=(),
        pages_held=2,
    )
    assert report.result.changed

    second = _refresh(
        built_index.data_root,
        environ,
        home,
        today=today,
        progress=progress,
    )
    assert second.outcome is Outcome.UNCHANGED
    assert second.location == location
    assert second.detail is None
    assert second.holder_pid is None
    assert second.result is not None
    assert second.result == RefreshResult(
        added=(),
        updated=(),
        removed=(),
        without_computed=(),
        page_errors=(),
        producer_errors=(),
        left_out=(),
        corpus_refreshed=(),
        pages_held=2,
    )


def test_report_relays_complete_changed_and_unchanged_results(
    built_index: BuiltIndex,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    location, environ, home = _copy_built_index(built_index, tmp_path)
    changed_result = RefreshResult(
        added=("workouts/added.md",),
        updated=("workouts/updated.md",),
        removed=("workouts/removed.md",),
        without_computed=(("workouts/missing.fit.md", ComputedState.SOURCE_MISSING),),
        page_errors=(("workouts/bad.md", "ValueError: bad document"),),
        producer_errors=(("corpus.sentinel", "RuntimeError: sentinel"),),
        left_out=(
            LeftOutPage(
                "workouts/duplicate.md",
                "duplicate_base",
                "workouts/first.md",
                "document-fingerprint-dup-8137",
            ),
        ),
        corpus_refreshed=("corpus.sentinel",),
        pages_held=19,
    )
    changed_expected = RefreshResult(
        added=("workouts/added.md",),
        updated=("workouts/updated.md",),
        removed=("workouts/removed.md",),
        without_computed=(("workouts/missing.fit.md", ComputedState.SOURCE_MISSING),),
        page_errors=(("workouts/bad.md", "ValueError: bad document"),),
        producer_errors=(("corpus.sentinel", "RuntimeError: sentinel"),),
        left_out=(
            LeftOutPage(
                "workouts/duplicate.md",
                "duplicate_base",
                "workouts/first.md",
                "document-fingerprint-dup-8137",
            ),
        ),
        corpus_refreshed=("corpus.sentinel",),
        pages_held=19,
    )
    unchanged_result = RefreshResult(
        added=(),
        updated=(),
        removed=(),
        without_computed=(
            ("workouts/unreadable.fit.md", ComputedState.SOURCE_UNREADABLE),
        ),
        page_errors=(("workouts/retry.md", "OSError: read failure"),),
        producer_errors=(("corpus.second", "ValueError: producer"),),
        left_out=(
            LeftOutPage(
                "workouts/no-base.md",
                "no_base_reference",
                None,
                "document-fingerprint-no-base-5924",
            ),
        ),
        corpus_refreshed=(),
        pages_held=23,
    )
    unchanged_expected = RefreshResult(
        added=(),
        updated=(),
        removed=(),
        without_computed=(
            ("workouts/unreadable.fit.md", ComputedState.SOURCE_UNREADABLE),
        ),
        page_errors=(("workouts/retry.md", "OSError: read failure"),),
        producer_errors=(("corpus.second", "ValueError: producer"),),
        left_out=(
            LeftOutPage(
                "workouts/no-base.md",
                "no_base_reference",
                None,
                "document-fingerprint-no-base-5924",
            ),
        ),
        corpus_refreshed=(),
        pages_held=23,
    )
    assert changed_result is not changed_expected
    assert changed_result == changed_expected
    assert changed_result.changed
    assert unchanged_result is not unchanged_expected
    assert unchanged_result == unchanged_expected
    assert not unchanged_result.changed
    results = [changed_result, unchanged_result]
    original_reconcile = refresh.reconcile

    def return_results(
        _conn: IndexConnection,
        _bookkeeping: Bookkeeping,
        _inputs: refresh.RefreshInputs,
    ) -> RefreshResult:
        return results.pop(0)

    with monkeypatch.context() as scoped:
        scoped.setattr(refresh, "reconcile", return_results)
        changed_report = _refresh(built_index.data_root, environ, home)
        unchanged_report = _refresh(built_index.data_root, environ, home)
    assert refresh.reconcile is original_reconcile
    assert results == []
    assert changed_report == IndexReport(
        Outcome.REFRESHED, location, None, None, changed_expected
    )
    assert changed_report.result is changed_result
    assert unchanged_report == IndexReport(
        Outcome.UNCHANGED, location, None, None, unchanged_expected
    )
    assert unchanged_report.result is unchanged_result
