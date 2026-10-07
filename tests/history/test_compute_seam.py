"""History's pure computation seam (analytics-derived task 2.2)."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from fitdocs.history import engine as history_engine
from fitdocs.history import page as history_page
from fitdocs.history.engine import MethodologyConfigurationError, run_history
from fitdocs.history.series import MethodologyProblem, select_methodology


def _write_page(
    root: Path,
    name: str,
    day: str,
    load: float | None,
    methodology: str | None,
) -> None:
    path = root / "workouts" / f"{name}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = ["---", "title: Seam fixture", "type: workout", f'date: "{day}"']
    if load is not None:
        lines.extend((f"load_value: {load}", f'load_methodology: "{methodology}"'))
    lines.extend(("---", "", "# Seam fixture", ""))
    path.write_text("\n".join(lines), encoding="utf-8")


def _archive(root: Path) -> None:
    # ISO week 1 in 2024 is deliberately low coverage; ISO week 1 in 2025 is
    # fully covered. Zeta recurs; alpha appears once.
    _write_page(root, "first", "2024-01-01", 10.0, "zeta")
    _write_page(root, "loadless", "2024-01-01", None, None)
    _write_page(root, "loadless-day", "2024-06-15", None, None)
    _write_page(root, "second", "2024-12-30", 30.0, "alpha")
    _write_page(root, "second-zeta", "2024-12-30", 20.0, "zeta")
    (root / "fitdocs.toml").write_text(
        '[history]\ncoverage_threshold = 0.8\n[load]\ndefault_calculator = "alpha"\n',
        encoding="utf-8",
    )


def _weekly_rows(markdown: str) -> list[str]:
    section = markdown.split("## Weekly Table\n", 1)[1].split("\n## ", 1)[0]
    return [line for line in section.splitlines() if line.startswith("| 20")]


def test_history_computation_seam_matches_written_weekly_table_for_both_choices(
    tmp_path: Path,
) -> None:
    _archive(tmp_path)
    inputs = history_engine.read_history_inputs(tmp_path)

    assert history_engine.observed_methodologies(inputs) == ("alpha", "zeta")
    for method in ("zeta", None):
        expected = history_engine.compute_history(inputs, methodology=method)
        assert expected is not None
        copy = tmp_path / f"copy-{method or 'configured'}"
        shutil.copytree(tmp_path / "workouts", copy / "workouts")
        (copy / "fitdocs.toml").write_bytes((tmp_path / "fitdocs.toml").read_bytes())
        report = run_history(copy, methodology=method)
        assert report.methodology == expected.choice.methodology
        written = (copy / "history" / "training-load-history.md").read_text(
            encoding="utf-8"
        )
        written_rows = _weekly_rows(written)
        assert [line.split("|")[1].strip() for line in written_rows] == sorted(
            line.split("|")[1].strip() for line in written_rows
        )
        assert written_rows == [
            line
            for line in history_page._render_weekly_table(expected.weeks).splitlines()
            if line.startswith("| 20")
        ]


def test_day_rows_suppression_is_iso_year_qualified_and_preserves_model_values(
    tmp_path: Path,
) -> None:
    _archive(tmp_path)
    computation = history_engine.compute_history(
        history_engine.read_history_inputs(tmp_path), methodology="zeta"
    )
    assert computation is not None
    week_one = [week for week in computation.weeks if week.iso_week == 1]
    assert [(week.iso_year, week.suppressed) for week in week_one] == [
        (2024, True),
        (2025, False),
    ]
    source_days = computation.series.days
    interior_zero_loads = [day for day in source_days[1:-1] if day.recorded_load == 0.0]
    assert interior_zero_loads
    assert any(
        day.pages > 0 and day.pages_with_load == 0 for day in interior_zero_loads
    )

    rows = history_page.day_rows(
        computation.series, computation.model, computation.weeks
    )
    assert tuple(row.day for row in rows) == tuple(day.day for day in source_days)
    by_day = {row.day: row for row in rows}
    assert by_day[week_one[0].monday].suppressed is True
    assert by_day[week_one[1].monday].suppressed is False
    assert (
        by_day[week_one[0].monday].recorded_load,
        by_day[week_one[0].monday].pages,
        by_day[week_one[0].monday].pages_with_load,
    ) == (10.0, 2, 1)
    suppressed_days = {
        day.day
        for week in computation.weeks
        if week.suppressed
        for day in source_days
        if day.day.isocalendar()[:2] == (week.iso_year, week.iso_week)
    }
    for day_load, row in zip(source_days, rows, strict=True):
        assert row.recorded_load == day_load.recorded_load
        assert row.pages == day_load.pages
        assert row.pages_with_load == day_load.pages_with_load
        assert row.suppressed is (day_load.day in suppressed_days)
        index = (day_load.day - computation.series.start).days
        if row.suppressed:
            assert (row.fitness, row.fatigue, row.form) == (None, None, None)
        else:
            assert (row.fitness, row.fatigue, row.form) == (
                computation.model.fitness[index],
                computation.model.fatigue[index],
                computation.model.form[index],
            )


def test_empty_archive_returns_none_before_methodology_selection(
    tmp_path: Path,
) -> None:
    _write_page(tmp_path, "empty", "2024-01-01", None, None)
    (tmp_path / "fitdocs.toml").write_text(
        '[load]\ndefault_calculator = "not-observed"\n', encoding="utf-8"
    )
    inputs = history_engine.read_history_inputs(tmp_path)
    assert history_engine.compute_history(inputs, methodology=None) is None


def test_methodology_configuration_error_matches_run_history(tmp_path: Path) -> None:
    _archive(tmp_path)
    (tmp_path / "fitdocs.toml").write_text("", encoding="utf-8")
    inputs = history_engine.read_history_inputs(tmp_path)
    with pytest.raises(MethodologyConfigurationError) as compute_error:
        history_engine.compute_history(inputs, methodology=None)
    with pytest.raises(MethodologyConfigurationError) as command_error:
        run_history(tmp_path)
    expected = select_methodology(inputs.scan.pages, requested=None, configured=None)
    assert isinstance(expected, MethodologyProblem)
    assert str(compute_error.value) == expected.detail
    assert str(compute_error.value) == str(command_error.value)
