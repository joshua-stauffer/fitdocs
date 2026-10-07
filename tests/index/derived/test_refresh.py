"""End-to-end refresh gating and failure isolation for derived tables."""

from __future__ import annotations

import hashlib
import os
import shutil
import stat
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path
from typing import Any, cast

import pytest

from fitdocs import cli as cli_module
from fitdocs.index import registry
from fitdocs.index.corpus import scan_workout_pages
from fitdocs.index.producer import (
    ComputedProducer,
    CorpusProducer,
    CorpusSnapshot,
    Rows,
)
from fitdocs.index.refresh import IndexReport, Outcome
from fitdocs.index.schema import TableSpec
from tests.index.derived.conftest import (
    TODAY,
    build_fixture_root,
    build_index,
    read_table,
    refresh,
    sync_with_handoff,
)


@dataclass
class _ProducerSpy:
    producer: CorpusProducer | ComputedProducer
    calls: int = 0

    @property
    def name(self) -> str:
        return self.producer.name

    @property
    def tables(self) -> tuple[TableSpec, ...]:
        return self.producer.tables

    def fingerprint(self, corpus: Any) -> str:
        return cast(CorpusProducer, self.producer).fingerprint(
            cast(CorpusSnapshot, corpus)
        )

    def rows(self, value: Any) -> Rows:
        self.calls += 1
        return self.producer.rows(cast(Any, value))


def _install_spies(monkeypatch: pytest.MonkeyPatch) -> dict[str, _ProducerSpy]:
    producers: tuple[CorpusProducer | ComputedProducer, ...] = (
        *registry.COMPUTED_PRODUCERS,
        *registry.CORPUS_PRODUCERS,
    )
    spies = {producer.name: _ProducerSpy(producer) for producer in producers}
    monkeypatch.setattr(
        registry,
        "COMPUTED_PRODUCERS",
        tuple(spies[producer.name] for producer in registry.COMPUTED_PRODUCERS),
    )
    monkeypatch.setattr(
        registry,
        "CORPUS_PRODUCERS",
        tuple(spies[producer.name] for producer in registry.CORPUS_PRODUCERS),
    )
    return spies


def _reset(spies: dict[str, _ProducerSpy]) -> None:
    for spy in spies.values():
        spy.calls = 0


def _calls(spies: dict[str, _ProducerSpy]) -> dict[str, int]:
    return {name: spy.calls for name, spy in spies.items()}


def _built(root: Path, spies: dict[str, _ProducerSpy]) -> None:
    report = build_index(root, today=TODAY)
    assert report.outcome is Outcome.BUILT
    _reset(spies)


def _write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def _append_page(root: Path, stem: str = "2026-02-16-new-page") -> Path:
    path = root / "workouts" / f"{stem}.md"
    _write(
        path,
        "---\n"
        "type: workout\n"
        'date: "2026-02-16"\n'
        "sport: Run\n"
        "sources:\n"
        f"  - archive/{'a' * 64}.fit\n"
        "load_value: 97\n"
        'load_methodology: "threshold"\n'
        "---\n\n"
        "<!-- fitdocs:begin:load -->\n"
        "_Training load not computed._\n"
        "<!-- fitdocs:end:load -->\n",
    )
    return path


def _edit_benchmark(root: Path, *, add: bool = False) -> str:
    path = root / "athlete.toml"
    original = path.read_text(encoding="utf-8")
    if add:
        target = (
            "  { value = 271, measured_on = 2026-02-05, applies_from = 2026-02-01 },\n]"
        )
        replacement = (
            "  { value = 271, measured_on = 2026-02-05, applies_from = 2026-02-01 },\n"
            "  { value = 295, measured_on = 2026-02-15, applies_from = 2026-02-14 },\n]"
        )
    else:
        target = "value = 283, measured_on = 2026-02-07"
        replacement = "value = 299, measured_on = 2026-02-07"
    assert target in original
    _write(path, original.replace(target, replacement, 1))
    return original


def _assert_nontrivial(
    rows: tuple[tuple[object, ...], ...], *, minimum: int = 1
) -> None:
    assert len(rows) >= minimum
    assert len(set(rows)) == len(rows)


def _capture_nontrivial_tables(
    root: Path, names: tuple[str, ...]
) -> dict[str, tuple[tuple[object, ...], ...]]:
    captured = {name: read_table(root, name) for name in names}
    for rows in captured.values():
        _assert_nontrivial(rows, minimum=1)
    return captured


def _assert_tables_match(
    root: Path, expected: dict[str, tuple[tuple[object, ...], ...]]
) -> None:
    for name, rows in expected.items():
        assert read_table(root, name) == rows


def _index_directory(root: Path) -> Path:
    database = next(
        (root.parent / "fitdocs-derived-index" / root.name).rglob("index.duckdb")
    )
    return database.parent


def _file_inventory(
    directory: Path,
) -> tuple[tuple[str, str, int, int, str | None, str | None], ...]:
    entries: list[tuple[str, str, int, int, str | None, str | None]] = []
    pending = [directory]
    while pending:
        parent = pending.pop()
        for path in sorted(parent.iterdir(), reverse=True):
            metadata = path.lstat()
            relative = path.relative_to(directory).as_posix()
            if stat.S_ISLNK(metadata.st_mode):
                entries.append(
                    (
                        relative,
                        "symlink",
                        metadata.st_size,
                        metadata.st_mtime_ns,
                        None,
                        os.readlink(path),
                    )
                )
            elif stat.S_ISDIR(metadata.st_mode):
                entries.append(
                    (
                        relative,
                        "directory",
                        metadata.st_size,
                        metadata.st_mtime_ns,
                        None,
                        None,
                    )
                )
                pending.append(path)
            elif stat.S_ISREG(metadata.st_mode):
                entries.append(
                    (
                        relative,
                        "file",
                        metadata.st_size,
                        metadata.st_mtime_ns,
                        hashlib.sha256(path.read_bytes()).hexdigest(),
                        None,
                    )
                )
            else:
                entries.append(
                    (
                        relative,
                        "other",
                        metadata.st_size,
                        metadata.st_mtime_ns,
                        None,
                        None,
                    )
                )
    return tuple(sorted(entries))


def _producer_errors(report: IndexReport) -> dict[str, str]:
    result = report.result
    assert result is not None
    return dict(result.producer_errors)


def _assert_rendered_errors(
    report: IndexReport,
    capsys: pytest.CaptureFixture[str],
    expected_errors: dict[str, str],
) -> None:
    cli_module._report_index_pass(report)
    captured = capsys.readouterr()
    rendered = captured.out + captured.err
    for producer, error in expected_errors.items():
        assert rendered.count(f"could not refresh {producer}:") == 1
        assert error in rendered


def test_profile_edit_refreshes_only_benchmarks_without_regen(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = build_fixture_root(tmp_path / "profile-edit")
    spies = _install_spies(monkeypatch)
    _built(root, spies)
    old_benchmarks = read_table(root, "benchmarks")
    old_periods = read_table(root, "benchmark_periods")
    _assert_nontrivial(old_benchmarks, minimum=5)
    _assert_nontrivial(old_periods, minimum=6)
    original = _edit_benchmark(root, add=True)

    report = refresh(root, today=TODAY)
    assert report.outcome is Outcome.REFRESHED
    assert _calls(spies)["derived.benchmarks"] == 1
    assert _calls(spies)["derived.load_series"] == 0
    assert _calls(spies)["derived.blocks"] == 0
    new_benchmarks = read_table(root, "benchmarks")
    new_periods = read_table(root, "benchmark_periods")
    assert len(new_benchmarks) == len(old_benchmarks) + 1
    assert new_benchmarks != old_benchmarks
    assert any(row[2] == 295.0 for row in new_benchmarks)
    assert any(row[4] == 295.0 for row in new_periods)
    assert any(row[2] == date(2026, 2, 15) for row in new_periods if row[4] == 295.0)
    assert (root / "athlete.toml").read_text(encoding="utf-8") != original


def test_new_page_refreshes_load_and_blocks_but_not_benchmarks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = build_fixture_root(tmp_path / "new-page")
    spies = _install_spies(monkeypatch)
    _built(root, spies)
    old_load = read_table(root, "daily_load")
    old_blocks = read_table(root, "mesocycles")
    old_benchmarks = read_table(root, "benchmarks")
    old_unplanned = read_table(root, "unplanned_pages")
    _assert_nontrivial(old_load, minimum=10)
    _assert_nontrivial(old_blocks, minimum=1)
    new_page = _append_page(root)

    report = refresh(root, today=TODAY)
    assert report.outcome is Outcome.REFRESHED
    assert _calls(spies)["derived.load_series"] == 1
    assert _calls(spies)["derived.blocks"] == 1
    assert _calls(spies)["derived.benchmarks"] == 0
    new_load = read_table(root, "daily_load")
    new_blocks = read_table(root, "mesocycles")
    assert new_load != old_load
    assert new_blocks != old_blocks
    added_load = tuple(
        row for row in new_load if row[0] == "threshold" and row[1] == date(2026, 2, 16)
    )
    assert len(added_load) == 1
    assert added_load[0][:5] == ("threshold", date(2026, 2, 16), 97.0, 1, 1)
    new_unplanned = read_table(root, "unplanned_pages")
    assert len(new_unplanned) == len(old_unplanned) + 1
    assert any(
        row[2] == new_page.stem and row[3] == "workouts/2026-02-16-new-page.md"
        for row in new_unplanned
    )
    assert read_table(root, "benchmarks") == old_benchmarks


def test_later_date_refreshes_blocks_only_when_a_plan_source_exists(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    with_source = build_fixture_root(tmp_path / "with-plan")
    with_spies = _install_spies(monkeypatch)
    _built(with_source, with_spies)
    old_blocks = read_table(with_source, "blocks")
    _assert_nontrivial(old_blocks, minimum=1)
    later = TODAY + timedelta(days=1)

    report = refresh(with_source, today=later)
    assert report.outcome is Outcome.REFRESHED
    with_calls = _calls(with_spies)
    assert with_calls["derived.blocks"] == 1
    assert all(
        count == 0 for name, count in with_calls.items() if name != "derived.blocks"
    )
    new_blocks = read_table(with_source, "blocks")
    assert new_blocks != old_blocks
    assert all(row[-1] == later for row in new_blocks)

    no_source = build_fixture_root(tmp_path / "no-plan")
    for source in (no_source / "plans").glob("*.toml"):
        source.unlink()
    _built(no_source, with_spies)
    assert read_table(no_source, "blocks") == ()
    _reset(with_spies)
    no_source_report = refresh(no_source, today=later)
    assert no_source_report.outcome is Outcome.UNCHANGED
    assert _calls(with_spies) == {name: 0 for name in with_spies}


def test_notes_edit_refreshes_load_series_without_recomputing_mean_max(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, composed_source: Path
) -> None:
    root = build_fixture_root(tmp_path / "notes", composed=True)
    spies = _install_spies(monkeypatch)
    assert build_index(root, today=TODAY).outcome is Outcome.BUILT
    sync_with_handoff(root, composed_source, today=TODAY)
    _reset(spies)
    mean_rows = read_table(root, "mean_max")
    _assert_nontrivial(mean_rows, minimum=1)
    page_key = mean_rows[0][0]
    page_mean_rows = tuple(row for row in mean_rows if row[0] == page_key)
    _assert_nontrivial(page_mean_rows, minimum=1)
    page = next(
        root / item.path
        for item in scan_workout_pages(root).pages
        if item.page_key == page_key
    )
    before = page.read_text(encoding="utf-8")
    begin = "<!-- fitdocs:begin:notes -->"
    end = "<!-- fitdocs:end:notes -->"
    assert begin in before and end in before
    start = before.index(begin) + len(begin)
    finish = before.index(end, start)
    old_note = before[start:finish]
    assert "refresh-note-marker" not in old_note
    _write(page, before[:start] + "\nrefresh-note-marker\n" + before[finish:])

    report = refresh(root, today=TODAY)
    assert report.outcome is Outcome.REFRESHED
    assert _calls(spies)["derived.load_series"] == 1
    assert _calls(spies)["derived.blocks"] == 1
    assert _calls(spies)["derived.benchmarks"] == 0
    assert _calls(spies)["derived.mean_max"] == 0
    refreshed_mean_rows = read_table(root, "mean_max")
    assert (
        tuple(row for row in refreshed_mean_rows if row[0] == page_key)
        == page_mean_rows
    )
    assert refreshed_mean_rows == mean_rows


def test_noop_refresh_keeps_every_index_file_byte_and_metadata_identical(
    tmp_path: Path,
) -> None:
    root = build_fixture_root(tmp_path / "noop")
    assert build_index(root, today=TODAY).outcome is Outcome.BUILT
    directory = _index_directory(root)
    nested = directory / "nested-probe"
    nested.mkdir()
    sentinel = nested / "sentinel.txt"
    sentinel.write_text("inventory-positive-control\n", encoding="utf-8")
    link = nested / "sentinel-link"
    link.symlink_to(sentinel.name)
    before = _file_inventory(directory)
    assert any(entry[0] == "nested-probe/sentinel.txt" for entry in before)
    assert any(
        entry[0] == "nested-probe/sentinel-link"
        and entry[1] == "symlink"
        and entry[5] == sentinel.name
        for entry in before
    )
    report = refresh(root, today=TODAY)
    after = _file_inventory(directory)
    assert after == before
    assert report.outcome is Outcome.UNCHANGED


def test_bad_history_settings_keep_load_and_block_rows_while_benchmarks_refresh(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = build_fixture_root(tmp_path / "bad-history")
    spies = _install_spies(monkeypatch)
    _built(root, spies)
    old_load = _capture_nontrivial_tables(
        root, ("load_series", "daily_load", "weekly_load")
    )
    old_blocks = _capture_nontrivial_tables(
        root,
        (
            "blocks",
            "mesocycles",
            "planned_workouts",
            "planned_workout_pages",
            "unplanned_pages",
        ),
    )
    old_benchmarks = read_table(root, "benchmarks")
    _assert_nontrivial(old_load["daily_load"], minimum=10)
    _assert_nontrivial(old_blocks["blocks"], minimum=1)
    _assert_nontrivial(old_benchmarks, minimum=5)
    settings_path = root / "fitdocs.toml"
    good_settings = settings_path.read_text(encoding="utf-8")
    _write(
        settings_path,
        '[history]\nmethodology = "threshold"\ncoverage_threshold = 2.0\n'
        '\n[plans]\npath = "plans"\n',
    )
    _edit_benchmark(root)

    report = refresh(root, today=TODAY)
    errors = _producer_errors(report)
    _assert_tables_match(root, old_load)
    _assert_tables_match(root, old_blocks)
    assert set(errors) == {"derived.load_series", "derived.blocks"}
    assert "SettingsError" in errors["derived.load_series"]
    assert "SettingsError" in errors["derived.blocks"]
    _assert_rendered_errors(
        report,
        capsys,
        errors,
    )
    new_benchmarks = read_table(root, "benchmarks")
    assert len(new_benchmarks) == len(old_benchmarks)
    assert new_benchmarks != old_benchmarks
    assert any(row[2] == 299.0 for row in new_benchmarks)
    assert not any(row[2] == 283.0 for row in new_benchmarks)

    repaired_settings = good_settings.replace(
        "coverage_threshold = 0.7", "coverage_threshold = 0.8", 1
    )
    assert repaired_settings != good_settings
    _write(settings_path, repaired_settings)
    repaired = refresh(root, today=TODAY)
    assert _producer_errors(repaired) == {}
    assert _calls(spies)["derived.load_series"] == 2
    assert _calls(spies)["derived.blocks"] == 2
    repaired_load = _capture_nontrivial_tables(
        root, ("load_series", "daily_load", "weekly_load")
    )
    assert repaired_load["load_series"] != old_load["load_series"]
    assert all(row[10] == 0.8 for row in repaired_load["load_series"])
    _assert_tables_match(root, old_blocks)


def test_bad_benchmark_entry_keeps_rows_while_new_page_refreshes_load_series(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = build_fixture_root(tmp_path / "bad-benchmark")
    spies = _install_spies(monkeypatch)
    _built(root, spies)
    old_benchmarks = _capture_nontrivial_tables(
        root, ("benchmarks", "benchmark_periods")
    )
    old_load = read_table(root, "daily_load")
    _assert_nontrivial(old_load, minimum=10)
    profile_path = root / "athlete.toml"
    good_profile = profile_path.read_text(encoding="utf-8")
    invalid_profile = good_profile.replace(
        "value = 283, measured_on = 2026-02-07",
        'value = "not-a-number", measured_on = 2026-02-07',
        1,
    )
    assert invalid_profile != good_profile
    _write(profile_path, invalid_profile)
    _append_page(root)

    report = refresh(root, today=TODAY)
    errors = _producer_errors(report)
    _assert_tables_match(root, old_benchmarks)
    assert set(errors) == {"derived.benchmarks"}
    assert "ProfileError" in errors["derived.benchmarks"]
    _assert_rendered_errors(
        report,
        capsys,
        errors,
    )
    new_load = read_table(root, "daily_load")
    assert new_load != old_load
    assert _calls(spies)["derived.benchmarks"] == 1
    assert _calls(spies)["derived.load_series"] == 1

    repaired_profile = good_profile.replace(
        "value = 283, measured_on = 2026-02-07",
        "value = 307, measured_on = 2026-02-07",
        1,
    )
    _write(profile_path, repaired_profile)
    repaired = refresh(root, today=TODAY)
    assert _producer_errors(repaired) == {}
    assert _calls(spies)["derived.benchmarks"] == 2
    repaired_benchmarks = _capture_nontrivial_tables(
        root, ("benchmarks", "benchmark_periods")
    )
    assert repaired_benchmarks["benchmarks"] != old_benchmarks["benchmarks"]
    assert any(row[2] == 307.0 for row in repaired_benchmarks["benchmarks"])
    repaired_periods = repaired_benchmarks["benchmark_periods"]
    assert any(row[4] == 307.0 for row in repaired_periods)


def test_missing_plans_directory_keeps_block_rows_while_benchmarks_refresh(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    root = build_fixture_root(tmp_path / "missing-plans")
    spies = _install_spies(monkeypatch)
    _built(root, spies)
    old_blocks = _capture_nontrivial_tables(
        root,
        (
            "blocks",
            "mesocycles",
            "planned_workouts",
            "planned_workout_pages",
            "unplanned_pages",
        ),
    )
    old_benchmarks = read_table(root, "benchmarks")
    _assert_nontrivial(old_benchmarks, minimum=5)
    settings_path = root / "fitdocs.toml"
    good_settings = settings_path.read_text(encoding="utf-8")
    alternate_plans = root / "alternate-plans"
    alternate_plans.mkdir()
    for source in (root / "plans").glob("*.toml"):
        shutil.copyfile(source, alternate_plans / source.name)
    bad_settings = good_settings.replace('path = "plans"', 'path = "missing-plans"')
    assert bad_settings != good_settings
    _write(settings_path, bad_settings)
    _edit_benchmark(root)

    report = refresh(root, today=TODAY)
    errors = _producer_errors(report)
    _assert_tables_match(root, old_blocks)
    assert set(errors) == {"derived.blocks"}
    assert "PlanSettingsError" in errors["derived.blocks"]
    _assert_rendered_errors(
        report,
        capsys,
        errors,
    )
    new_benchmarks = read_table(root, "benchmarks")
    assert len(new_benchmarks) == len(old_benchmarks)
    assert new_benchmarks != old_benchmarks
    assert any(row[2] == 299.0 for row in new_benchmarks)
    assert not any(row[2] == 283.0 for row in new_benchmarks)
    assert _calls(spies)["derived.blocks"] == 1
    assert _calls(spies)["derived.benchmarks"] == 1

    repaired_settings = good_settings.replace(
        'path = "plans"', 'path = "alternate-plans"'
    )
    _write(settings_path, repaired_settings)
    repaired = refresh(root, today=TODAY)
    assert _producer_errors(repaired) == {}
    assert _calls(spies)["derived.blocks"] == 2
    repaired_blocks = read_table(root, "blocks")
    assert repaired_blocks != old_blocks["blocks"]
    assert any(row[1] == "alternate-plans/derived.toml" for row in repaired_blocks)
    repaired_other_blocks = _capture_nontrivial_tables(
        root,
        (
            "mesocycles",
            "planned_workouts",
            "planned_workout_pages",
            "unplanned_pages",
        ),
    )
    assert set(repaired_other_blocks) == set(old_blocks) - {"blocks"}
