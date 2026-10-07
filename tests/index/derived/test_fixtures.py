"""Self-tests for the synthetic corpus consumed by derived producer tests."""

from __future__ import annotations

import shutil
import tomllib
from collections.abc import Callable
from datetime import date
from importlib import import_module
from pathlib import Path
from typing import Any

import pytest

from fitdocs import Sport, contract, docio, parse_fit
from fitdocs.athlete import ATHLETE_SCHEMA_VERSION, load_athlete_inputs
from fitdocs.benchmarks import BenchmarkKind
from fitdocs.history import MethodologyConfigurationError, run_history
from fitdocs.index import derive, registry
from fitdocs.index.bookkeeping import ComputedState
from fitdocs.index.corpus import scan_workout_pages
from fitdocs.index.derive import Derived
from fitdocs.index.fingerprint import athlete_fingerprint
from fitdocs.index.location import resolve_index_location
from fitdocs.index.producer import CorpusSnapshot, Rows
from fitdocs.index.refresh import Outcome
from fitdocs.index.schema import ColumnSpec, ColumnType, TableSpec
from fitdocs.index.store import open_index, read_bookkeeping
from fitdocs.load.profile import load_profile
from fitdocs.metrics.types import AthleteInputs
from fitdocs.plans.matching import Confidence, RowState
from fitdocs.plans.reconcile import run_reconcile
from tests.index.derived.conftest import (
    TODAY,
    _index_args,
    build_fixture_root,
    build_index,
    read_table,
    refresh,
    snapshot_of,
    sync_with_handoff,
)


def test_fixture_has_a_single_suppressed_week_and_can_refuse_methodology(
    tmp_path: Path,
) -> None:
    root = build_fixture_root(tmp_path / "configured")
    assert date(2026, 2, 24) == TODAY
    frontmatter = [
        docio.read_frontmatter(path) or {}
        for path in sorted((root / "workouts").glob("*.md"))
        if "left-out" not in path.name
    ]
    loaded = [
        page for page in frontmatter if isinstance(page.get("load_value"), (int, float))
    ]
    assert any("load_value" not in page for page in frontmatter)
    values = [page["load_value"] for page in loaded]
    assert len(values) == len(set(values))
    assert {page.get("load_methodology") for page in loaded} == {
        "threshold",
        "banister_1991",
    }
    assert sum(page.get("date") == "2026-02-03" for page in loaded) == 2
    history_root = shutil.copytree(root, tmp_path / "configured-history-copy")
    report = run_history(history_root, methodology="threshold")
    assert report.document is not None
    text = (history_root / report.document).read_text(encoding="utf-8")
    assert (
        sum(
            line.startswith("| 2026-") and "suppressed" in line
            for line in text.splitlines()
        )
        == 1
    )

    unconfigured = build_fixture_root(tmp_path / "unconfigured", methodology=False)
    with pytest.raises(MethodologyConfigurationError):
        run_history(shutil.copytree(unconfigured, tmp_path / "unconfigured-copy"))


def test_fixture_plan_reaches_each_resolution_state_and_confidence(
    tmp_path: Path,
) -> None:
    root = build_fixture_root(tmp_path / "plans")
    reconcile_root = shutil.copytree(root, tmp_path / "plans-copy")
    report = run_reconcile(reconcile_root, today=TODAY)
    assert report.blocks
    rows = tuple(row for block in report.blocks for row in block.rows)
    assert {row.state for row in rows} == set(RowState)
    assert {row.confidence for row in rows if row.confidence is not None} == set(
        Confidence
    )
    upcoming = next(row for row in rows if row.row_id == "upcoming")
    not_logged = next(row for row in rows if row.row_id == "not-logged")
    assert upcoming.state is RowState.UPCOMING
    assert not_logged.state is RowState.NOT_LOGGED
    assert report.failed
    (block,) = report.blocks
    assert len(block.problems) == 1
    assert "missing-override-stem" in block.problems[0].message
    (no_source_row,) = (row for row in block.rows if row.row_id == "no-sources-match")
    assert no_source_row.state is RowState.MATCHED
    (claimed_no_source,) = no_source_row.stems
    assert claimed_no_source == "2026-02-14-left-out"
    claimed_frontmatter = (
        docio.read_frontmatter(reconcile_root / "workouts" / f"{claimed_no_source}.md")
        or {}
    )
    assert "sources" not in claimed_frontmatter
    assert report.plan.blocks[1].status.value == "invalid"
    assert any(
        workout.stem == "2026-02-12-unplanned"
        for block in report.blocks
        for mesocycle in block.mesocycles
        for workout in mesocycle.unplanned
    )


def test_history_suppression_is_confined_to_the_weekly_row(tmp_path: Path) -> None:
    root = build_fixture_root(tmp_path / "one-suppressed-week")
    history_root = shutil.copytree(root, tmp_path / "history-copy")
    report = run_history(history_root, methodology="threshold")
    assert report.document is not None
    weekly = [
        line
        for line in (history_root / report.document)
        .read_text(encoding="utf-8")
        .splitlines()
        if line.startswith("| 2026-")
    ]
    assert len(weekly) == 2
    assert sum("suppressed" in line for line in weekly) == 1


def test_snapshot_distinguishes_no_sources_workout(tmp_path: Path) -> None:
    root = build_fixture_root(tmp_path / "snapshot")
    scan = scan_workout_pages(root)
    no_sources = next(
        item for item in scan.left_out if item.path.endswith("left-out.md")
    )
    left_out_frontmatter = docio.read_frontmatter(root / no_sources.path) or {}
    assert "sources" not in left_out_frontmatter
    assert left_out_frontmatter["load_value"] == 83
    snapshot = snapshot_of(root, today=TODAY)
    assert any(
        item.path == no_sources.path
        and item.document_fingerprint == no_sources.document_fingerprint
        for item in snapshot.left_out
    )
    assert {page.path for page in snapshot.pages} == {page.path for page in scan.pages}
    assert no_sources.path not in {page.path for page in snapshot.pages}


def test_profile_keeps_ftp_disciplines_separate_and_flat_value_distinct(
    tmp_path: Path,
) -> None:
    root = build_fixture_root(tmp_path / "profile")
    profile = load_profile(root)
    ride = profile.benchmark(
        BenchmarkKind.FTP_WATTS, discipline=Sport.RIDE, on=date(2026, 2, 11)
    )
    run = profile.benchmark(
        BenchmarkKind.FTP_WATTS, discipline=Sport.RUN, on=date(2026, 2, 11)
    )
    assert ride is not None and run is not None
    assert ride.value != run.value
    athlete_data = tomllib.loads((root / "athlete.toml").read_text(encoding="utf-8"))
    assert athlete_data["profile_version"] == ATHLETE_SCHEMA_VERSION
    run_entry = next(
        entry
        for entry in profile.benchmarks.entries
        if entry.kind is BenchmarkKind.FTP_WATTS and entry.discipline is Sport.RUN
    )
    ride_measured_dates = {
        entry.measured_on
        for entry in profile.benchmarks.entries
        if entry.kind is BenchmarkKind.FTP_WATTS and entry.discipline is Sport.RIDE
    }
    assert run_entry.measured_on not in ride_measured_dates
    assert min(ride_measured_dates) < run_entry.measured_on < max(ride_measured_dates)
    assert any(
        entry.kind is BenchmarkKind.LTHR_BPM
        and entry.discipline is Sport.RUN
        and entry.value == 172
        for entry in profile.benchmarks.entries
    )
    ride_entries = [
        entry
        for entry in profile.benchmarks.entries
        if entry.kind is BenchmarkKind.FTP_WATTS and entry.discipline is Sport.RIDE
    ]
    earlier_measured = next(entry for entry in ride_entries if entry.value == 271)
    assert earlier_measured.applies_from == date(2026, 2, 1)
    day = date(2026, 2, 11)
    naive = max(
        (
            entry
            for entry in ride_entries
            if entry.applies_from is not None and entry.applies_from <= day
        ),
        key=lambda entry: entry.applies_from or entry.measured_on,
    )
    assert ride.value == 260
    assert naive.value == 271
    assert ride.value != naive.value
    assert profile.get_number("ftp_watts") == 999
    assert profile.get_number("ftp_watts") not in {
        item.value for item in profile.benchmarks.entries
    }
    assert len(ride_entries) == 2
    assert all(entry.source is None for entry in ride_entries)
    assert any(
        entry.source is not None
        and entry.source.kind == "derived"
        and entry.source.method == "synthetic-method"
        and entry.source.document == "workouts/derived.md"
        and entry.source.inputs == "synthetic-inputs"
        and entry.source.citation == "synthetic-citation"
        for entry in profile.benchmarks.entries
    )
    assert any(
        entry.discipline is None and entry.kind.value == "max_hr_bpm"
        for entry in profile.benchmarks.entries
    )


def test_index_build_is_isolated_and_reads_held_pages(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = build_fixture_root(tmp_path / "index")
    controlled_home = tmp_path / "controlled-home"
    controlled_home.mkdir()
    sentinel = controlled_home / "sentinel"
    sentinel.write_bytes(b"positive-control")

    def home_snapshot() -> dict[Path, tuple[bool, bytes | None]]:
        return {
            path.relative_to(controlled_home): (
                path.is_dir(),
                None if path.is_dir() else path.read_bytes(),
            )
            for path in controlled_home.rglob("*")
        }

    before_home = home_snapshot()
    monkeypatch.setenv("HOME", str(controlled_home))
    held_arguments: list[frozenset[str] | None] = []
    fixture_module: Any = import_module("tests.index.derived.conftest")
    real_corpus_snapshot: Callable[..., CorpusSnapshot] = fixture_module.corpus_snapshot

    def record_held(*args: Any, **kwargs: Any) -> CorpusSnapshot:
        held_arguments.append(kwargs["held"])
        return real_corpus_snapshot(*args, **kwargs)

    monkeypatch.setattr(fixture_module, "corpus_snapshot", record_held)
    snapshot_of(root, today=TODAY)
    assert held_arguments == [None]
    report = build_index(root, today=TODAY)
    assert report.result is not None
    environ, home = _index_args(root, TODAY)
    location = resolve_index_location(root, environ, home)
    assert location.database.is_file()
    assert not home.exists()
    after_home = home_snapshot()
    assert before_home == {Path("sentinel"): (False, b"positive-control")}
    assert after_home == before_home
    with open_index(location.database, read_only=True) as conn:
        bookkeeping = read_bookkeeping(conn)
        assert bookkeeping is not None
        assert bookkeeping.pages
        expected_held = frozenset(bookkeeping.pages)
    snapshot_of(root, today=TODAY)
    assert held_arguments[-1] == expected_held
    from fitdocs.index.corpus import scan_workout_pages

    read_only_values: list[bool] = []
    real_open_index = fixture_module.open_index

    def record_read_only(*args: Any, **kwargs: Any) -> Any:
        read_only_values.append(kwargs.get("read_only", False))
        return real_open_index(*args, **kwargs)

    monkeypatch.setattr(fixture_module, "open_index", record_read_only)
    actual_rows = read_table(root, "pages")
    expected_paths = tuple(sorted(page.path for page in scan_workout_pages(root).pages))
    with open_index(location.database, read_only=True) as conn:
        reference_rows = tuple(
            conn.execute('SELECT * FROM "pages" ORDER BY ALL').fetchall()
        )
    assert len({row[5] for row in reference_rows}) > 1
    assert len({row[7] for row in reference_rows}) > 1
    assert len(actual_rows) > 1
    assert {row[1] for row in actual_rows} == set(expected_paths)
    assert len({row[1] for row in actual_rows}) == len(expected_paths)
    assert tuple(sorted(actual_rows)) == actual_rows
    assert all(row[5] is not None and row[7] in {"Run", "Ride"} for row in actual_rows)
    assert actual_rows == reference_rows
    assert read_only_values == [True]


def test_snapshot_carries_explicit_today_and_athlete_fingerprint(
    tmp_path: Path,
) -> None:
    root = build_fixture_root(tmp_path / "snapshot-values")
    snapshot = snapshot_of(root, today=TODAY)
    assert snapshot.today == TODAY
    assert snapshot.athlete_fingerprint != ""
    assert len(snapshot.pages) > 1


def test_sync_handoff_refreshes_written_pages_and_not_built_fails(
    tmp_path: Path, composed_source: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = build_fixture_root(tmp_path / "sync")
    built = build_index(root, today=TODAY)
    assert built.outcome is Outcome.BUILT
    derived_calls: list[tuple[str, ...]] = []
    real_derive = derive.derive_page

    def track_derive(
        data_root: Path, sources: tuple[str, ...], athlete: AthleteInputs | None
    ) -> Derived | ComputedState:
        derived_calls.append(sources)
        return real_derive(data_root, sources, athlete)

    monkeypatch.setattr(derive, "derive_page", track_derive)
    report, refreshed, collector = sync_with_handoff(root, composed_source, today=TODAY)
    assert report.written
    assert refreshed.outcome is Outcome.REFRESHED
    assert collector.retained_samples > 0
    written_sources = {
        contract.source_refs(docio.read_frontmatter(root / relative) or {})
        for relative in report.written
    }
    assert written_sources
    assert all(sources not in derived_calls for sources in written_sources)
    base_activity = parse_fit((composed_source / "ride/garmin.fit").read_bytes())
    extra_activity = parse_fit((composed_source / "ride/healthfit.fit").read_bytes())
    assert base_activity.samples and extra_activity.samples
    assert all(value is None for value in base_activity.samples.heart_rate_bpm)
    assert any(value is not None for value in extra_activity.samples.heart_rate_bpm)
    run_activity = parse_fit((composed_source / "run/power.fit").read_bytes())
    assert run_activity.samples
    assert all(value is not None for value in run_activity.samples.power_w)
    assert any(value is not None for value in run_activity.samples.heart_rate_bpm)
    assert all(value is not None for value in run_activity.samples.speed_mps)

    empty = build_fixture_root(tmp_path / "not-built")
    with pytest.raises(AssertionError):
        # The helper's refresh assertion is the intended NOT_BUILT observable.
        sync_with_handoff(empty, composed_source, today=TODAY)


class _SnapshotRecorder:
    name = "fixture.snapshot_recorder"
    tables = (
        TableSpec(
            name="fixture_probe",
            description="Synthetic explicit-date observation.",
            columns=(
                ColumnSpec(
                    "observed_on", ColumnType.VARCHAR, "The supplied refresh date."
                ),
            ),
        ),
    )

    def __init__(self) -> None:
        self.snapshots: list[CorpusSnapshot] = []

    def fingerprint(self, corpus: CorpusSnapshot) -> str:
        return repr(
            (
                corpus.today,
                tuple((page.path, page.document_fingerprint) for page in corpus.pages),
                tuple(
                    (page.path, page.document_fingerprint) for page in corpus.left_out
                ),
            )
        )

    def rows(self, corpus: CorpusSnapshot) -> Rows:
        self.snapshots.append(corpus)
        return {"fixture_probe": ((corpus.today.isoformat(),),)}


def test_build_and_refresh_pass_explicit_today_and_the_whole_snapshot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = build_fixture_root(tmp_path / "recorder")
    recorder = _SnapshotRecorder()
    monkeypatch.setattr(registry, "CORPUS_PRODUCERS", (recorder,))
    built = build_index(root, today=TODAY)
    assert built.outcome is Outcome.BUILT
    assert recorder.snapshots[-1].today == TODAY

    left_out_page = root / "workouts/2026-02-14-left-out.md"
    left_out_page.write_text(
        left_out_page.read_text(encoding="utf-8") + "\nchange\n", encoding="utf-8"
    )
    before = len(recorder.snapshots)
    refreshed = refresh(root, today=TODAY)
    assert refreshed.outcome is Outcome.REFRESHED
    assert len(recorder.snapshots) > before
    observed = recorder.snapshots[-1]
    assert observed.today == TODAY
    assert observed.athlete_fingerprint == athlete_fingerprint(
        load_athlete_inputs(root)
    )
    assert observed == snapshot_of(root, today=TODAY)


def test_sync_handoff_without_an_index_fails_on_not_built(
    tmp_path: Path, composed_source: Path
) -> None:
    root = build_fixture_root(tmp_path / "unbuilt-sync")
    with pytest.raises(AssertionError, match="REFRESHED"):
        sync_with_handoff(root, composed_source, today=TODAY)
