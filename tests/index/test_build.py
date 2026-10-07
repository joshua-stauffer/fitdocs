"""Build and atomic replacement of the per-data-root index."""

from __future__ import annotations

import hashlib
import inspect
import os
import subprocess
import sys
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import cast, get_type_hints

import pytest

import fitdocs.index.build as build
from fitdocs import contract
from fitdocs.docio import read_frontmatter
from fitdocs.index import registry
from fitdocs.index.bookkeeping import Bookkeeping, ComputedState, IndexMeta
from fitdocs.index.corpus import LeftOutPage
from fitdocs.index.fingerprint import athlete_fingerprint
from fitdocs.index.location import (
    IndexLocation,
    IndexLocationError,
    resolve_index_location,
)
from fitdocs.index.lock import writer_lock
from fitdocs.index.producer import CorpusSnapshot, PageComputed, PageDocument, Rows
from fitdocs.index.refresh import (
    IndexReport,
    Outcome,
    ProgressCallback,
    RefreshInputs,
    RefreshResult,
)
from fitdocs.index.schema import SCHEMA_VERSION, ColumnSpec, ColumnType, TableSpec
from fitdocs.index.store import (
    IndexConnection,
    duckdb_version,
    open_index,
    read_bookkeeping,
    write_meta,
)
from fitdocs.metrics.types import AthleteInputs
from fitdocs.version import tool_version
from tests.index._helpers import forge_storage_version, hold_index

TODAY = date(2026, 10, 6)


@dataclass(frozen=True)
class _DocumentExtension:
    name: str
    tables: tuple[TableSpec, ...]

    def rows(self, page: PageDocument) -> Rows:
        return {
            table.name: ((f"document:{self.name}:{table.name}:{page.path}",),)
            for table in self.tables
        }


@dataclass(frozen=True)
class _ComputedExtension:
    name: str
    tables: tuple[TableSpec, ...]

    def rows(self, page: PageComputed) -> Rows:
        return {
            table.name: ((f"computed:{self.name}:{table.name}:{page.document.path}",),)
            for table in self.tables
        }


@dataclass(frozen=True)
class _CorpusExtension:
    name: str
    tables: tuple[TableSpec, ...]

    def fingerprint(self, corpus: CorpusSnapshot) -> str:
        return f"corpus-fingerprint:{corpus.data_root.name}"

    def rows(self, corpus: CorpusSnapshot) -> Rows:
        return {
            table.name: ((f"corpus:{self.name}:{table.name}:{corpus.data_root.name}",),)
            for table in self.tables
        }


def _extension_table(name: str) -> TableSpec:
    return TableSpec(
        name=name,
        description=f"Independent {name} table.",
        columns=(ColumnSpec("value", ColumnType.VARCHAR, f"Value in {name}."),),
    )


def test_run_index_command_has_the_declared_keyword_only_api() -> None:
    signature = inspect.signature(build.run_index_command)
    parameters = signature.parameters
    assert tuple(parameters) == (
        "data_root",
        "environ",
        "home",
        "athlete",
        "today",
        "rebuild",
        "progress",
    )
    assert parameters["data_root"].kind is inspect.Parameter.POSITIONAL_OR_KEYWORD
    assert all(
        parameters[name].kind is inspect.Parameter.KEYWORD_ONLY
        for name in ("environ", "home", "athlete", "today", "rebuild", "progress")
    )
    assert get_type_hints(build.run_index_command) == {
        "data_root": Path,
        "environ": Mapping[str, str],
        "home": Path,
        "athlete": AthleteInputs | None,
        "today": date,
        "rebuild": bool,
        "progress": ProgressCallback | None,
        "return": IndexReport,
    }


def _command(
    data_root: Path,
    base: Path,
    *,
    rebuild: bool = False,
    athlete: AthleteInputs | None = None,
    today: date = TODAY,
    progress: Callable[[int, int], None] | None = None,
) -> IndexReport:
    return build.run_index_command(
        data_root,
        environ={"FITDOCS_INDEX_DIR": str(base)},
        home=base.parent / "synthetic-home",
        athlete=athlete,
        today=today,
        rebuild=rebuild,
        progress=progress,
    )


def _page_count(path: Path) -> int:
    with open_index(path, read_only=True) as connection:
        return cast(
            int,
            connection.execute("SELECT count(*) FROM index_pages").fetchall()[0][0],
        )


def _seed(data_root: Path, base: Path) -> IndexReport:
    result = _command(data_root, base)
    assert result.outcome is Outcome.BUILT
    assert result.location is not None
    return result


def test_absent_index_builds_every_page_outside_data_root_with_owner_only_mode(
    synced_corpus: Path, synced_workout_pages: tuple[Path, ...], tmp_path: Path
) -> None:
    base = tmp_path / "cache"
    athlete = AthleteInputs(
        ftp_watts=203.5,
        resting_hr_bpm=47,
        max_hr_bpm=192,
    )
    before = {
        p.relative_to(synced_corpus): p.read_bytes()
        for p in synced_corpus.rglob("*")
        if p.is_file()
    }

    report = _command(synced_corpus, base, athlete=athlete)

    assert report.outcome is Outcome.BUILT
    assert report.location is not None
    assert report.detail == "index does not exist"
    expected = tuple(
        sorted(p.relative_to(synced_corpus).as_posix() for p in synced_workout_pages)
    )
    assert report.result is not None
    assert report.result.added == expected
    assert report.result.pages_held == 2
    assert report.location.database.is_file()
    assert report.location.database.is_relative_to(report.location.directory)
    assert report.location.directory.stat().st_mode & 0o777 == 0o700
    assert report.location.base_dir.stat().st_mode & 0o777 == 0o700
    with open_index(report.location.database, read_only=True) as connection:
        state = read_bookkeeping(connection)
    assert state is not None
    assert state.meta.data_root == str(synced_corpus.resolve())
    assert state.meta.schema_version == SCHEMA_VERSION
    assert state.meta.fitdocs_version == tool_version()
    assert state.meta.athlete_fingerprint == athlete_fingerprint(athlete)
    assert {value.path for value in state.pages.values()} == set(expected)
    assert not report.location.building.exists()
    after = {
        p.relative_to(synced_corpus): p.read_bytes()
        for p in synced_corpus.rglob("*")
        if p.is_file()
    }
    assert after == before


def test_build_forwards_all_caller_inputs_to_the_single_reconcile(
    synced_corpus: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = tmp_path / "cache"
    athlete = AthleteInputs(ftp_watts=201.25, resting_hr_bpm=48, max_hr_bpm=191)
    callback_calls: list[tuple[int, int]] = []

    def progress(done: int, total: int) -> None:
        callback_calls.append((done, total))

    original = build.reconcile
    observed: list[RefreshInputs] = []

    def observe(
        connection: IndexConnection,
        bookkeeping: Bookkeeping,
        inputs: RefreshInputs,
    ) -> RefreshResult:
        observed.append(inputs)
        return original(connection, bookkeeping, inputs)

    with monkeypatch.context() as scoped:
        scoped.setattr(build, "reconcile", observe)
        report = _command(synced_corpus, base, athlete=athlete, progress=progress)

    assert build.reconcile is original
    assert report.outcome is Outcome.BUILT
    assert len(observed) == 1
    assert observed[0].data_root == synced_corpus.resolve()
    assert observed[0].athlete is athlete
    assert observed[0].today == TODAY
    assert observed[0].progress is progress
    assert callback_calls == []


def test_built_report_relays_every_refresh_result_field(
    synced_corpus: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    core_registry: None,
) -> None:
    expected = RefreshResult(
        added=("workouts/added.md",),
        updated=("workouts/updated.md",),
        removed=("workouts/removed.md",),
        without_computed=(
            ("workouts/missing.fit.md", ComputedState.SOURCE_UNREADABLE),
        ),
        page_errors=(("workouts/page-error.md", "ValueError: page"),),
        producer_errors=(("test.producer", "RuntimeError: producer"),),
        left_out=(
            LeftOutPage(
                "workouts/left-out.md",
                "no_base_reference",
                None,
                "left-out-document-fp",
            ),
        ),
        corpus_refreshed=("test.corpus",),
        pages_held=17,
    )

    def return_expected(
        connection: IndexConnection,
        bookkeeping: Bookkeeping,
        inputs: RefreshInputs,
    ) -> RefreshResult:
        assert bookkeeping.pages == {}
        assert bookkeeping.producers == {
            "core.documents": None,
            "core.computed": None,
        }
        return expected

    original = build.reconcile
    with monkeypatch.context() as scoped:
        scoped.setattr(build, "reconcile", return_expected)
        report = _command(synced_corpus, tmp_path / "cache")

    assert build.reconcile is original
    location = resolve_index_location(
        synced_corpus,
        {"FITDOCS_INDEX_DIR": str(tmp_path / "cache")},
        tmp_path / "synthetic-home",
    )
    assert report == IndexReport(
        Outcome.BUILT, location, "index does not exist", None, expected
    )


def test_build_initializes_all_tiers_and_checkpoints_before_swap(
    synced_corpus: Path,
    synced_workout_pages: tuple[Path, ...],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    documents = (
        _DocumentExtension(
            "test.documents_z",
            (_extension_table("z_doc_beta"), _extension_table("a_doc_alpha")),
        ),
        _DocumentExtension(
            "test.documents_a",
            (_extension_table("z_doc_delta"), _extension_table("a_doc_gamma")),
        ),
    )
    computed = (
        _ComputedExtension(
            "test.computed_z",
            (_extension_table("z_computed_beta"), _extension_table("a_computed_alpha")),
        ),
        _ComputedExtension(
            "test.computed_a",
            (
                _extension_table("z_computed_delta"),
                _extension_table("a_computed_gamma"),
            ),
        ),
    )
    corpora = (
        _CorpusExtension(
            "test.corpus_z",
            (_extension_table("z_corpus_beta"), _extension_table("a_corpus_alpha")),
        ),
        _CorpusExtension(
            "test.corpus_a",
            (_extension_table("z_corpus_delta"), _extension_table("a_corpus_gamma")),
        ),
    )
    monkeypatch.setattr(registry, "DOCUMENT_PRODUCERS", documents)
    monkeypatch.setattr(registry, "COMPUTED_PRODUCERS", computed)
    monkeypatch.setattr(registry, "CORPUS_PRODUCERS", corpora)

    athlete = AthleteInputs(ftp_watts=218.75, resting_hr_bpm=44, max_hr_bpm=193)
    expected_meta = IndexMeta(
        schema_version=SCHEMA_VERSION,
        fitdocs_version=tool_version(),
        duckdb_version=duckdb_version(),
        data_root=str(synced_corpus.resolve()),
        athlete_fingerprint=athlete_fingerprint(athlete),
    )
    expected_initial = Bookkeeping(
        expected_meta,
        {},
        {
            "test.documents_z": None,
            "test.documents_a": None,
            "test.computed_z": None,
            "test.computed_a": None,
            "test.corpus_z": None,
            "test.corpus_a": None,
        },
    )
    expected_registration_rows = [
        ("test.computed_a", "computed", ["z_computed_delta", "a_computed_gamma"], None),
        ("test.computed_z", "computed", ["z_computed_beta", "a_computed_alpha"], None),
        ("test.corpus_a", "corpus", ["z_corpus_delta", "a_corpus_gamma"], None),
        ("test.corpus_z", "corpus", ["z_corpus_beta", "a_corpus_alpha"], None),
        ("test.documents_a", "document", ["z_doc_delta", "a_doc_gamma"], None),
        ("test.documents_z", "document", ["z_doc_beta", "a_doc_alpha"], None),
    ]
    expected_table_names = (
        "z_doc_beta",
        "a_doc_alpha",
        "z_doc_delta",
        "a_doc_gamma",
        "z_computed_beta",
        "a_computed_alpha",
        "z_computed_delta",
        "a_computed_gamma",
        "z_corpus_beta",
        "a_corpus_alpha",
        "z_corpus_delta",
        "a_corpus_gamma",
    )
    expected_paths = tuple(
        sorted(
            path.relative_to(synced_corpus).as_posix() for path in synced_workout_pages
        )
    )
    observed_initial: list[Bookkeeping | None] = []
    observed_passed: list[Bookkeeping] = []
    observed_rows: list[dict[str, list[tuple[object, ...]]]] = []
    observed_tables: list[list[tuple[object, ...]]] = []
    connections: list[IndexConnection] = []
    events: list[str] = []

    create_name = "create_index"
    checkpoint_name = "checkpoint"
    original_create = cast(
        Callable[[Path], IndexConnection], getattr(build, create_name)
    )
    original_reconcile = build.reconcile
    original_checkpoint = cast(
        Callable[[IndexConnection], None], getattr(build, checkpoint_name)
    )
    original_close = IndexConnection.close
    original_swap = build._swap

    def observe_create(path: Path) -> IndexConnection:
        connection = original_create(path)
        connections.append(connection)
        return connection

    def observe_reconcile(
        connection: IndexConnection,
        bookkeeping: Bookkeeping,
        inputs: RefreshInputs,
    ) -> RefreshResult:
        observed_passed.append(
            Bookkeeping(
                bookkeeping.meta,
                dict(bookkeeping.pages),
                dict(bookkeeping.producers),
            )
        )
        observed_initial.append(read_bookkeeping(connection))
        observed_tables.append(
            connection.execute(
                "SELECT producer, kind, tables, fingerprint FROM index_producers "
                "ORDER BY producer"
            ).fetchall()
        )
        result = original_reconcile(connection, bookkeeping, inputs)
        observed_rows.append(
            {
                table_name: connection.execute(
                    f'SELECT page_key, value FROM "{table_name}" ORDER BY value'
                ).fetchall()
                for table_name in expected_table_names[:8]
            }
            | {
                table_name: connection.execute(
                    f'SELECT value FROM "{table_name}" ORDER BY value'
                ).fetchall()
                for table_name in expected_table_names[8:]
            }
        )
        return result

    def observe_checkpoint(connection: IndexConnection) -> None:
        original_checkpoint(connection)
        events.append("checkpoint")

    def observe_close(connection: IndexConnection) -> None:
        original_close(connection)
        if connection in connections:
            events.append("close")

    def observe_swap(location: IndexLocation, source: Path) -> None:
        original_swap(location, source)
        events.append("swap")

    with monkeypatch.context() as scoped:
        scoped.setattr(build, create_name, observe_create)
        scoped.setattr(build, "reconcile", observe_reconcile)
        scoped.setattr(build, checkpoint_name, observe_checkpoint)
        scoped.setattr(IndexConnection, "close", observe_close)
        scoped.setattr(build, "_swap", observe_swap)
        report = _command(synced_corpus, tmp_path / "cache", athlete=athlete)

    assert getattr(build, create_name) is original_create
    assert build.reconcile is original_reconcile
    assert getattr(build, checkpoint_name) is original_checkpoint
    assert IndexConnection.close is original_close
    assert build._swap is original_swap
    assert len(connections) == 1
    assert events == ["checkpoint", "close", "swap"]
    assert observed_initial == [expected_initial]
    assert observed_passed == [expected_initial]
    assert observed_tables == [expected_registration_rows]
    expected_keys = {
        path.relative_to(synced_corpus).as_posix(): hashlib.sha256(
            (
                synced_corpus / contract.source_refs(read_frontmatter(path) or {})[-1]
            ).read_bytes()
        ).hexdigest()
        for path in synced_workout_pages
    }
    expected_rows = (
        {
            table_name: sorted(
                (
                    expected_keys[path],
                    f"document:{producer}:{table_name}:{path}",
                )
                for path in expected_paths
            )
            for producer, table_name in (
                ("test.documents_z", "z_doc_beta"),
                ("test.documents_z", "a_doc_alpha"),
                ("test.documents_a", "z_doc_delta"),
                ("test.documents_a", "a_doc_gamma"),
            )
        }
        | {
            table_name: sorted(
                (
                    expected_keys[path],
                    f"computed:{producer}:{table_name}:{path}",
                )
                for path in expected_paths
            )
            for producer, table_name in (
                ("test.computed_z", "z_computed_beta"),
                ("test.computed_z", "a_computed_alpha"),
                ("test.computed_a", "z_computed_delta"),
                ("test.computed_a", "a_computed_gamma"),
            )
        }
        | {
            table_name: [(f"corpus:{producer}:{table_name}:{synced_corpus.name}",)]
            for producer, table_name in (
                ("test.corpus_z", "z_corpus_beta"),
                ("test.corpus_z", "a_corpus_alpha"),
                ("test.corpus_a", "z_corpus_delta"),
                ("test.corpus_a", "a_corpus_gamma"),
            )
        }
    )
    assert observed_rows == [expected_rows]
    assert report == IndexReport(
        Outcome.BUILT,
        resolve_index_location(
            synced_corpus,
            {"FITDOCS_INDEX_DIR": str(tmp_path / "cache")},
            tmp_path / "synthetic-home",
        ),
        "index does not exist",
        None,
        RefreshResult(
            expected_paths,
            (),
            (),
            (),
            (),
            (),
            (),
            ("test.corpus_z", "test.corpus_a"),
            2,
        ),
    )


def test_forced_rebuild_is_from_empty_and_stale_building_pair_is_removed(
    synced_corpus: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    initial = _seed(synced_corpus, tmp_path / "cache")
    assert initial.location is not None
    location = initial.location
    with open_index(location.database, read_only=False) as connection:
        connection.execute("CREATE TABLE old_generation_marker (value INTEGER)")
        connection.execute("INSERT INTO old_generation_marker VALUES (73)")
    old_bytes = location.database.read_bytes()
    location.building.write_bytes(b"partial old build")
    building_wal = location.building.with_name(location.building.name + ".wal")
    building_wal.write_bytes(b"partial recovery")
    original_unlink = Path.unlink
    unlinked: list[Path] = []

    def record_unlink(path: Path, *, missing_ok: bool = False) -> None:
        if path in {location.building, building_wal}:
            unlinked.append(path)
        original_unlink(path, missing_ok=missing_ok)

    with monkeypatch.context() as scoped:
        scoped.setattr(Path, "unlink", record_unlink)
        report = _command(synced_corpus, tmp_path / "cache", rebuild=True)

    assert Path.unlink is original_unlink
    assert report.outcome is Outcome.BUILT
    assert report.detail == "rebuild requested"
    assert report.result is not None
    assert report.result.pages_held == 2
    assert len(report.result.added) == 2
    assert report.result.removed == ()
    assert location.database.read_bytes() != old_bytes
    assert _page_count(location.database) == 2
    with open_index(initial.location.database, read_only=True) as connection:
        marker = connection.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_name = 'old_generation_marker'"
        ).fetchall()
    assert marker == []
    assert not location.building.exists()
    assert not building_wal.exists()
    assert unlinked == [location.building, building_wal]


def test_build_error_preserves_old_index_and_location_error_propagates(
    synced_corpus: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = tmp_path / "cache"
    initial = _seed(synced_corpus, base)
    assert initial.location is not None
    previous = initial.location.database.read_bytes()
    original = build.reconcile

    def fail(
        conn: IndexConnection, bookkeeping: Bookkeeping, inputs: RefreshInputs
    ) -> RefreshResult:
        assert bookkeeping.pages == {}
        raise RuntimeError("injected build failure")

    monkeypatch.setattr(build, "reconcile", fail)
    report = _command(synced_corpus, base, rebuild=True)
    monkeypatch.setattr(build, "reconcile", original)
    assert report.outcome is Outcome.FAILED
    assert report.detail == "RuntimeError: injected build failure"
    assert report.location == initial.location
    assert report.holder_pid is None
    assert report.result is None
    assert initial.location.database.read_bytes() == previous

    unsafe = synced_corpus / "index-cache"
    with pytest.raises(IndexLocationError, match="index directory"):
        _command(synced_corpus, unsafe)
    assert not unsafe.exists()


def test_keyboard_interrupt_during_build_propagates_and_preserves_old_file(
    synced_corpus: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = tmp_path / "cache"
    initial = _seed(synced_corpus, base)
    assert initial.location is not None
    previous = initial.location.database.read_bytes()
    original = build.reconcile
    interrupted = KeyboardInterrupt("synthetic cancellation")

    def interrupt(
        conn: IndexConnection, bookkeeping: Bookkeeping, inputs: RefreshInputs
    ) -> RefreshResult:
        raise interrupted

    monkeypatch.setattr(build, "reconcile", interrupt)
    with pytest.raises(KeyboardInterrupt) as raised:
        _command(synced_corpus, base, rebuild=True)
    monkeypatch.setattr(build, "reconcile", original)
    assert raised.value is interrupted
    assert initial.location.database.read_bytes() == previous


def test_incremental_writer_contention_is_busy(
    synced_corpus: Path, tmp_path: Path
) -> None:
    base = tmp_path / "cache"
    initial = _seed(synced_corpus, base)
    assert initial.location is not None
    with writer_lock(initial.location.lock):
        report = _command(synced_corpus, base)
    assert report.outcome is Outcome.BUSY
    assert report.location == initial.location
    assert report.detail == f"writer lock is held for {initial.location.lock}"
    assert report.holder_pid is None
    assert report.result is None


def test_current_index_uses_refresh_for_changes_then_reports_unchanged(
    synced_corpus: Path,
    synced_workout_pages: tuple[Path, ...],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    core_registry: None,
) -> None:
    base = tmp_path / "cache"
    initial = _seed(synced_corpus, base)
    assert initial.location is not None
    athlete = AthleteInputs(ftp_watts=231.75, resting_hr_bpm=43, max_hr_bpm=194)
    caller_today = date(2026, 10, 19)
    with open_index(initial.location.database, read_only=True) as connection:
        before_changed = read_bookkeeping(connection)
    assert before_changed is not None and before_changed.pages
    assert before_changed.producers
    assert before_changed.meta.athlete_fingerprint != athlete_fingerprint(athlete)
    progress_calls: list[tuple[int, int]] = []

    def progress(done: int, total: int) -> None:
        progress_calls.append((done, total))

    expected_before_changed = Bookkeeping(
        before_changed.meta,
        dict(before_changed.pages),
        dict(before_changed.producers),
    )
    page = synced_workout_pages[0]
    relative = page.relative_to(synced_corpus).as_posix()
    lines = page.read_text().splitlines()
    title_index = next(
        index for index, line in enumerate(lines) if line.startswith("title:")
    )
    lines[title_index] = "title: Changed for incremental build test"
    page.write_text("\n".join(lines) + "\n")

    original_reconcile = build.reconcile
    observed: list[tuple[RefreshInputs, Bookkeeping]] = []

    def observe(
        connection: IndexConnection,
        bookkeeping: Bookkeeping,
        inputs: RefreshInputs,
    ) -> RefreshResult:
        observed.append(
            (
                inputs,
                Bookkeeping(
                    bookkeeping.meta,
                    dict(bookkeeping.pages),
                    dict(bookkeeping.producers),
                ),
            )
        )
        return original_reconcile(connection, bookkeeping, inputs)

    with monkeypatch.context() as scoped:
        scoped.setattr(build, "reconcile", observe)
        changed = _command(
            synced_corpus,
            base,
            athlete=athlete,
            today=caller_today,
            progress=progress,
        )
        with open_index(initial.location.database, read_only=True) as connection:
            after_changed = read_bookkeeping(connection)
        assert after_changed is not None and after_changed.pages
        expected_before_unchanged = Bookkeeping(
            after_changed.meta,
            dict(after_changed.pages),
            dict(after_changed.producers),
        )
        unchanged = _command(
            synced_corpus,
            base,
            athlete=athlete,
            today=caller_today,
            progress=progress,
        )

    assert build.reconcile is original_reconcile
    expected_inputs = RefreshInputs(
        synced_corpus.resolve(), athlete, None, caller_today, progress
    )
    assert observed == [
        (expected_inputs, expected_before_changed),
        (expected_inputs, expected_before_unchanged),
    ]
    assert progress_calls == []

    assert changed.outcome is Outcome.REFRESHED
    assert changed.result is not None
    assert changed.result.added == ()
    assert changed.result.updated == (relative,)
    assert changed.result.removed == ()
    assert changed.result.pages_held == 2
    assert changed.result.page_errors == ()
    assert changed.result.producer_errors == ()
    assert changed.result.without_computed == ()
    assert changed.result.left_out == ()
    assert changed.result.corpus_refreshed == ()
    assert changed.detail is None
    assert changed.holder_pid is None
    assert changed.location == initial.location
    with open_index(initial.location.database, read_only=True) as connection:
        row = connection.execute(
            "SELECT title FROM pages WHERE path = $1", (relative,)
        ).fetchall()
    assert row == [("Changed for incremental build test",)]

    assert unchanged.outcome is Outcome.UNCHANGED
    assert unchanged.location == initial.location
    assert unchanged.result is not None
    assert unchanged.result.changed is False
    assert unchanged.result.pages_held == 2
    assert unchanged.result.added == ()
    assert unchanged.result.updated == ()
    assert unchanged.result.removed == ()
    assert unchanged.result.without_computed == ()
    assert unchanged.result.page_errors == ()
    assert unchanged.result.producer_errors == ()
    assert unchanged.result.left_out == ()
    assert unchanged.result.corpus_refreshed == ()
    assert unchanged.detail is None
    assert unchanged.holder_pid is None


def test_staged_build_is_completed_before_next_refresh(
    synced_corpus: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base = tmp_path / "cache"
    initial = _seed(synced_corpus, base)
    assert initial.location is not None
    location = initial.location
    old_bytes = location.database.read_bytes()
    original = os.replace
    original_reconcile = build.reconcile
    calls: list[tuple[Path, Path]] = []
    reconcile_calls: list[Path] = []
    refuse_stage_retry = True

    def refuse_first_swap(
        source: str | os.PathLike[str], target: str | os.PathLike[str]
    ) -> None:
        source_path, target_path = Path(source), Path(target)
        calls.append((source_path, target_path))
        if source_path == location.building and target_path == location.database:
            raise PermissionError("synthetic reader")
        if (
            source_path == location.staged
            and target_path == location.database
            and refuse_stage_retry
        ):
            raise PermissionError("synthetic staged refusal")
        original(source, target)

    def observe_reconcile(
        connection: IndexConnection,
        bookkeeping: Bookkeeping,
        inputs: RefreshInputs,
    ) -> RefreshResult:
        reconcile_calls.append(location.building)
        return original_reconcile(connection, bookkeeping, inputs)

    with monkeypatch.context() as scoped:
        scoped.setattr(os, "replace", refuse_first_swap)
        scoped.setattr(build, "reconcile", observe_reconcile)
        report = _command(synced_corpus, base, rebuild=True)
        assert os.replace is refuse_first_swap
        assert build.reconcile is observe_reconcile
        assert report.outcome is Outcome.STAGED
        assert report.location == location
        assert report.detail == "synthetic reader"
        assert report.holder_pid is None
        assert report.result is None
        assert location.database.read_bytes() == old_bytes
        assert location.staged.is_file()
        staged_bytes = location.staged.read_bytes()
        assert _page_count(location.staged) == 2
        assert (location.building, location.staged) in calls
        assert reconcile_calls == [location.building]

        refused_retry = _command(synced_corpus, base)
        assert refused_retry == IndexReport(
            Outcome.STAGED,
            location,
            "synthetic staged refusal",
            None,
            None,
        )
        assert location.database.read_bytes() == old_bytes
        assert location.staged.exists()
        assert location.staged.read_bytes() == staged_bytes
        assert reconcile_calls == [location.building]

        refuse_stage_retry = False
        completed = _command(synced_corpus, base)

    assert os.replace is original
    assert build.reconcile is original_reconcile
    assert report.outcome is Outcome.STAGED
    assert report.location == location
    assert completed.outcome is Outcome.UNCHANGED
    assert completed.location == location
    assert completed.result is not None and completed.result.pages_held == 2
    assert not location.staged.exists()
    assert _page_count(location.database) == 2


def test_rebuild_unlinks_crashed_old_wal_before_swap(
    synced_corpus: Path, tmp_path: Path
) -> None:
    initial = _seed(synced_corpus, tmp_path / "cache")
    assert initial.location is not None
    location = initial.location
    code = """
import os
from pathlib import Path
from fitdocs.index.store import open_index
connection = open_index(
    Path(os.environ["INDEX_DB"]),
    read_only=False,
    settings={"checkpoint_threshold": "1GB"},
)
connection.execute("CREATE TABLE foreign_recovery_marker (value INTEGER)")
connection.execute("INSERT INTO foreign_recovery_marker VALUES (947)")
os._exit(0)
"""
    env = dict(os.environ)
    env["INDEX_DB"] = str(location.database)
    child = subprocess.run(
        [sys.executable, "-c", code],
        env=env,
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert child.returncode == 0, child.stderr
    assert location.wal.is_file(), "fixture did not leave the old database WAL"

    report = _command(synced_corpus, tmp_path / "cache", rebuild=True)

    assert report.outcome is Outcome.BUILT
    assert report.location == location
    with open_index(location.database, read_only=True) as connection:
        tables = connection.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema='main' AND table_name='foreign_recovery_marker'"
        ).fetchall()
    assert tables == []
    assert _page_count(location.database) == 2


def test_schema_mismatch_and_corrupt_index_rebuild_with_reason(
    synced_corpus: Path, tmp_path: Path
) -> None:
    base = tmp_path / "cache"
    initial = _seed(synced_corpus, base)
    assert initial.location is not None
    with open_index(initial.location.database, read_only=False) as connection:
        current = read_bookkeeping(connection)
        assert current is not None
        write_meta(
            connection,
            IndexMeta(
                99,
                current.meta.fitdocs_version,
                current.meta.duckdb_version,
                current.meta.data_root,
                current.meta.athlete_fingerprint,
            ),
        )
    mismatch = _command(synced_corpus, base)
    assert mismatch.outcome is Outcome.BUILT
    assert mismatch.detail == f"schema version 99; this fitdocs uses {SCHEMA_VERSION}"
    assert mismatch.result is not None and mismatch.result.pages_held == 2

    initial.location.database.write_bytes(b"not a DuckDB file")
    corrupt = _command(synced_corpus, base)
    assert corrupt.outcome is Outcome.BUILT
    assert corrupt.detail is not None
    assert "not a valid DuckDB database file" in corrupt.detail
    assert corrupt.result is not None and corrupt.result.pages_held == 2


def test_index_without_bookkeeping_is_rebuilt(
    synced_corpus: Path, synced_workout_pages: tuple[Path, ...], tmp_path: Path
) -> None:
    initial = _seed(synced_corpus, tmp_path / "cache")
    assert initial.location is not None
    with open_index(initial.location.database, read_only=False) as connection:
        connection.execute("DELETE FROM index_meta")

    report = _command(synced_corpus, tmp_path / "cache")

    assert report.outcome is Outcome.BUILT
    assert report.detail == "not a complete fitdocs index"
    assert report.result is not None
    assert report.result.added == tuple(
        sorted(
            page.relative_to(synced_corpus).as_posix() for page in synced_workout_pages
        )
    )


def test_incompatible_storage_and_schema_mismatch_both_rebuild(
    synced_corpus: Path, tmp_path: Path
) -> None:
    base = tmp_path / "cache"
    initial = _seed(synced_corpus, base)
    assert initial.location is not None
    forge_storage_version(initial.location.database, 69)

    incompatible = _command(synced_corpus, base)

    assert incompatible.outcome is Outcome.BUILT
    assert incompatible.detail is not None
    assert (
        "Trying to read a database file with version number 69" in incompatible.detail
    )
    assert incompatible.result is not None and incompatible.result.pages_held == 2


def test_duckdb_locked_incremental_run_is_busy(
    synced_corpus: Path, tmp_path: Path
) -> None:
    initial = _seed(synced_corpus, tmp_path / "cache")
    assert initial.location is not None
    with hold_index(initial.location.database, read_only=True) as holder_pid:
        report = _command(synced_corpus, tmp_path / "cache")
    assert holder_pid > 0
    assert report.outcome is Outcome.BUSY
    assert report.location == initial.location
    assert report.holder_pid == holder_pid
    assert report.detail is not None
    assert report.result is None


def test_readonly_holder_sees_complete_old_database_during_rebuild(
    synced_corpus: Path, tmp_path: Path
) -> None:
    initial = _seed(synced_corpus, tmp_path / "cache")
    assert initial.location is not None
    location = initial.location
    with open_index(location.database, read_only=False) as connection:
        state = read_bookkeeping(connection)
        assert state is not None
        key = sorted(state.pages)[-1]
        connection.execute("DELETE FROM index_pages WHERE page_key = $1", (key,))
    assert _page_count(location.database) == 1

    ready, release = tmp_path / "reader-ready", tmp_path / "reader-release"
    code = """
import os, time
from pathlib import Path
from fitdocs.index.store import open_index
ready, release = Path(os.environ["READY"]), Path(os.environ["RELEASE"])
with open_index(Path(os.environ["INDEX_DB"]), read_only=True) as connection:
    before = connection.execute("SELECT count(*) FROM index_pages").fetchall()[0][0]
    ready.write_text(str(before))
    deadline = time.monotonic() + 12
    while not release.exists() and time.monotonic() < deadline:
        time.sleep(.01)
    after = connection.execute("SELECT count(*) FROM index_pages").fetchall()[0][0]
    print(f"{before},{after}", flush=True)
"""
    env = dict(os.environ)
    env.update(
        {
            "INDEX_DB": str(location.database),
            "READY": str(ready),
            "RELEASE": str(release),
        }
    )
    reader = subprocess.Popen(
        [sys.executable, "-c", code],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        deadline = time.monotonic() + 10
        while not ready.exists() and time.monotonic() < deadline:
            time.sleep(0.01)
        assert ready.exists()
        assert ready.read_text() == "1"
        rebuilt = _command(synced_corpus, tmp_path / "cache", rebuild=True)
        assert rebuilt.outcome is Outcome.BUILT
        assert _page_count(location.database) == 2
        release.write_text("continue")
        stdout, stderr = reader.communicate(timeout=15)
        assert reader.returncode == 0, stderr
        assert stdout.strip() == "1,1"
        assert _page_count(location.database) == 2
    finally:
        if reader.poll() is None:
            reader.kill()
            reader.wait(timeout=5)
