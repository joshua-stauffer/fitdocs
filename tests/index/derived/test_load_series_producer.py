"""The load-series tables are the history engine's own projections."""

from __future__ import annotations

import re
from dataclasses import FrozenInstanceError, fields, replace
from datetime import date
from pathlib import Path

import pytest

import fitdocs.index.derived.load_series as load_series_module
from fitdocs.athlete import load_athlete_inputs
from fitdocs.history import (
    MethodologyChoice,
    compute_history,
    day_rows,
    observed_methodologies,
    read_history_inputs,
    select_methodology,
)
from fitdocs.index.corpus import corpus_snapshot, scan_workout_pages
from fitdocs.index.derived.inputs import (
    digest,
    settings_digest,
    workouts_digest,
)
from fitdocs.index.derived.load_series import (
    DAILY_LOAD_TABLE,
    LOAD_SERIES_PRODUCER,
    LOAD_SERIES_TABLE,
    WEEKLY_LOAD_TABLE,
    LoadSeriesProducer,
)
from fitdocs.index.fingerprint import athlete_fingerprint
from fitdocs.index.producer import CorpusProducer
from fitdocs.index.schema import ColumnType, resolve_tables
from tests.index.derived.conftest import TODAY, build_fixture_root, snapshot_of


def _expected_rows(root: Path) -> dict[str, tuple[tuple[object, ...], ...]]:
    inputs = read_history_inputs(root)
    default = select_methodology(
        inputs.scan.pages, requested=None, configured=inputs.configured
    )
    series_rows: list[tuple[object, ...]] = []
    daily_rows: list[tuple[object, ...]] = []
    weekly_rows: list[tuple[object, ...]] = []
    for methodology in observed_methodologies(inputs):
        computation = compute_history(inputs, methodology=methodology)
        assert computation is not None
        if (
            isinstance(default, MethodologyChoice)
            and default.methodology == methodology
        ):
            default_selection = default.source
        else:
            default_selection = None
        is_default = default_selection is not None
        series_rows.append(
            (
                methodology,
                is_default,
                default_selection,
                computation.series.start,
                computation.series.end,
                computation.constants.tau_fitness_days,
                computation.constants.tau_fatigue_days,
                computation.constants.k_fitness,
                computation.constants.k_fatigue,
                computation.constants.provenance.value,
                computation.threshold,
            )
        )
        daily_rows.extend(
            (
                methodology,
                row.day,
                row.recorded_load,
                row.pages,
                row.pages_with_load,
                row.fitness,
                row.fatigue,
                row.form,
                row.suppressed,
            )
            for row in day_rows(
                computation.series, computation.model, computation.weeks
            )
        )
        weekly_rows.extend(
            (
                methodology,
                row.iso_year,
                row.iso_week,
                row.monday,
                row.days_in_span,
                row.total_load,
                row.sessions,
                row.pages,
                row.pages_with_load,
                row.fitness,
                row.fatigue,
                row.form,
                row.suppressed,
            )
            for row in computation.weeks
        )
    return {
        LOAD_SERIES_TABLE.name: tuple(series_rows),
        DAILY_LOAD_TABLE.name: tuple(daily_rows),
        WEEKLY_LOAD_TABLE.name: tuple(weekly_rows),
    }


def _schema_shape(table: object) -> tuple[tuple[str, ColumnType, str], ...]:
    return tuple(
        (column.name, column.type, column.description)
        for column in table.columns  # type: ignore[attr-defined]
    )


def _as_corpus_producer(
    producer: CorpusProducer = LOAD_SERIES_PRODUCER,
) -> CorpusProducer:
    return producer


def test_tables_have_exact_ordered_history_shapes_and_frozen_producer() -> None:
    assert LOAD_SERIES_PRODUCER.name == "derived.load_series"
    assert LOAD_SERIES_PRODUCER is not LoadSeriesProducer()
    assert LOAD_SERIES_PRODUCER.tables == (
        LOAD_SERIES_TABLE,
        DAILY_LOAD_TABLE,
        WEEKLY_LOAD_TABLE,
    )
    assert tuple(field.name for field in fields(LoadSeriesProducer)) == (
        "name",
        "tables",
    )
    with pytest.raises(FrozenInstanceError):
        LOAD_SERIES_PRODUCER.name = "changed"  # type: ignore[misc]
    assert _as_corpus_producer() is LOAD_SERIES_PRODUCER
    assert load_series_module.LOAD_SERIES_PRODUCER is LOAD_SERIES_PRODUCER
    assert load_series_module.__annotations__["LOAD_SERIES_PRODUCER"] == (
        "Final[LoadSeriesProducer]"
    )
    resolved = resolve_tables((), (), (LOAD_SERIES_PRODUCER,), ())
    assert tuple(table.name for table in resolved) == (
        "load_series",
        "daily_load",
        "weekly_load",
    )
    assert tuple(
        tuple(column.name for column in table.columns) for table in resolved
    ) == (
        tuple(column.name for column in LOAD_SERIES_TABLE.columns),
        tuple(column.name for column in DAILY_LOAD_TABLE.columns),
        tuple(column.name for column in WEEKLY_LOAD_TABLE.columns),
    )

    assert LOAD_SERIES_TABLE.description == (
        "One row per training-load methodology some workout page records a load "
        "under: the terms its fitness/fatigue/form series was computed with. "
        "Equals fitdocs history --methodology <methodology>'s computation for "
        "the inputs as of the last refresh."
    )
    assert DAILY_LOAD_TABLE.description == (
        "One row per day of each methodology's series, from its first to its "
        "last contributing day. Equals fitdocs history --methodology "
        "<methodology>'s computation for the inputs as of the last refresh."
    )
    assert WEEKLY_LOAD_TABLE.description == (
        "One row per ISO week of each methodology's series. Equals fitdocs "
        "history --methodology <methodology>'s weekly table, unrounded, for the "
        "inputs as of the last refresh."
    )
    assert _schema_shape(LOAD_SERIES_TABLE) == (
        ("methodology", ColumnType.VARCHAR, "Calculator id."),
        (
            "history_default",
            ColumnType.BOOLEAN,
            "TRUE for the methodology fitdocs history shows without --methodology; "
            "FALSE for every row when it would refuse to choose.",
        ),
        (
            "default_selection",
            ColumnType.VARCHAR,
            "configured or inferred for the default; NULL otherwise.",
        ),
        ("series_start", ColumnType.DATE, "First day of the series."),
        ("series_end", ColumnType.DATE, "Last day of the series."),
        ("tau_fitness_days", ColumnType.DOUBLE, "Fitness time constant in days."),
        ("tau_fatigue_days", ColumnType.DOUBLE, "Fatigue time constant in days."),
        ("k_fitness", ColumnType.DOUBLE, "Fitness weighting, dimensionless."),
        ("k_fatigue", ColumnType.DOUBLE, "Fatigue weighting, dimensionless."),
        (
            "constants_provenance",
            ColumnType.VARCHAR,
            "seeds for fitdocs's shipped starting values or configured.",
        ),
        (
            "coverage_threshold",
            ColumnType.DOUBLE,
            "Fraction from 0 to 1 below which a week is suppressed.",
        ),
    )
    assert _schema_shape(DAILY_LOAD_TABLE) == (
        ("methodology", ColumnType.VARCHAR, "Calculator id."),
        ("day", ColumnType.DATE, "Calendar day."),
        (
            "recorded_load",
            ColumnType.DOUBLE,
            "Sum of the day's recorded loads in dimensionless load points; 0 on a "
            "day with no load, as fitdocs history counts it.",
        ),
        ("pages", ColumnType.INTEGER, "Pages counted that day."),
        ("pages_with_load", ColumnType.INTEGER, "Pages carrying a load that day."),
        (
            "fitness",
            ColumnType.DOUBLE,
            "Fitness on the daily-average load scale; NULL on a suppressed day.",
        ),
        (
            "fatigue",
            ColumnType.DOUBLE,
            "Fatigue on the daily-average load scale; NULL on a suppressed day.",
        ),
        (
            "form",
            ColumnType.DOUBLE,
            "Fitness minus fatigue on the daily-average load scale; "
            "NULL on a suppressed day.",
        ),
        (
            "suppressed",
            ColumnType.BOOLEAN,
            "TRUE when the day's ISO week is suppressed for low coverage.",
        ),
    )
    assert _schema_shape(WEEKLY_LOAD_TABLE) == (
        ("methodology", ColumnType.VARCHAR, "Calculator id."),
        ("iso_year", ColumnType.INTEGER, "ISO week-numbering year."),
        ("iso_week", ColumnType.INTEGER, "ISO week number."),
        ("week_start", ColumnType.DATE, "Monday of the ISO week."),
        ("days_in_series", ColumnType.INTEGER, "Days of the week in the series."),
        (
            "total_load",
            ColumnType.DOUBLE,
            "Total dimensionless load points in the week.",
        ),
        ("sessions", ColumnType.INTEGER, "Pages carrying a load in the week."),
        ("pages", ColumnType.INTEGER, "Pages counted in the week."),
        ("pages_with_load", ColumnType.INTEGER, "Pages carrying a load in the week."),
        (
            "fitness",
            ColumnType.DOUBLE,
            "Fitness on the daily-average load scale at the week's last day; "
            "NULL when suppressed.",
        ),
        (
            "fatigue",
            ColumnType.DOUBLE,
            "Fatigue on the daily-average load scale at the week's last day; "
            "NULL when suppressed.",
        ),
        (
            "form",
            ColumnType.DOUBLE,
            "Form on the daily-average load scale at the week's last day; "
            "NULL when suppressed.",
        ),
        (
            "suppressed",
            ColumnType.BOOLEAN,
            "TRUE when the week is suppressed for low coverage.",
        ),
    )


def test_daily_and_weekly_rows_equal_each_methodology_engine_projection(
    derived_root: Path,
) -> None:
    snapshot = snapshot_of(derived_root, today=TODAY)
    actual = LOAD_SERIES_PRODUCER.rows(snapshot)
    expected = _expected_rows(derived_root)
    assert len(expected["daily_load"]) > 10
    assert {row[0] for row in expected["load_series"]} == {
        "banister_1991",
        "threshold",
    }
    assert len(set(row[2] for row in expected["daily_load"])) > 1
    assert any(row[5] is not None and row[5] != 0 for row in expected["daily_load"])
    assert actual == expected

    series = {row[0]: row for row in actual["load_series"]}
    assert series["threshold"][1:3] == (True, "configured")
    assert series["banister_1991"][1:3] == (False, None)
    assert series["threshold"][3:5] == (date(2026, 2, 2), date(2026, 2, 15))
    assert any(
        row[1] == date(2026, 2, 15) and row[2:5] == (83.0, 1, 1)
        for row in actual["daily_load"]
        if row[0] == "threshold"
    )
    left_out_paths = {page.path for page in snapshot.left_out}
    assert "workouts/2026-02-14-left-out.md" in left_out_paths
    assert "workouts/2026-02-14-left-out.md" not in {
        page.path for page in snapshot.pages
    }
    rest_or_unscored = [
        row
        for row in actual["daily_load"]
        if row[0] == "threshold" and row[1] in {date(2026, 2, 13), date(2026, 2, 14)}
    ]
    assert [(row[2], row[3], row[4]) for row in rest_or_unscored] == [
        (0.0, 1, 0),
        (0.0, 1, 0),
    ]
    actual_zero_days = {
        (row[0], row[1], row[3], row[4])
        for row in actual["daily_load"]
        if row[2] == 0.0
    }
    expected_zero_days = {
        (row[0], row[1], row[3], row[4])
        for row in expected["daily_load"]
        if row[2] == 0.0
    }
    assert len(expected_zero_days) > 2
    assert actual_zero_days == expected_zero_days
    suppressed = [row for row in actual["daily_load"] if row[8]]
    assert suppressed
    assert all(row[5:8] == (None, None, None) for row in suppressed)
    suppressed_weeks = [row for row in actual["weekly_load"] if row[12]]
    assert suppressed_weeks
    assert all(row[9:12] == (None, None, None) for row in suppressed_weeks)
    daily_fitness = [
        row[5] for row in actual["daily_load"] if isinstance(row[5], float)
    ]
    assert any(value != round(value, 1) for value in daily_fitness)


def test_configured_constants_threshold_and_fractional_loads_are_projected(
    tmp_path: Path,
) -> None:
    root = build_fixture_root(tmp_path / "configured-fractional")
    settings = root / "fitdocs.toml"
    settings_text = settings.read_text(encoding="utf-8")
    settings.write_text(
        settings_text.replace(
            "coverage_threshold = 0.7",
            "tau_fitness_days = 37.0\n"
            "tau_fatigue_days = 9.0\n"
            "k_fitness = 1.3\n"
            "k_fatigue = 2.7\n"
            "coverage_threshold = 0.83",
        ),
        encoding="utf-8",
    )
    fractional_loads = {
        "2026-02-02-run-a": ("11", "11.1234567"),
        "2026-02-03-ride-a": ("23", "23.7654321"),
        "2026-02-03-ride-b": ("31", "31.2468135"),
        "2026-02-04-run-a": ("43", "43.9876543"),
    }
    for stem, (integer_value, fractional_value) in fractional_loads.items():
        page = root / f"workouts/{stem}.md"
        page_text = page.read_text(encoding="utf-8")
        assert f"load_value: {integer_value}\n" in page_text
        page.write_text(
            page_text.replace(
                f"load_value: {integer_value}\n",
                f"load_value: {fractional_value}\n",
            ),
            encoding="utf-8",
        )

    inputs = read_history_inputs(root)
    computations = {
        method: compute_history(inputs, methodology=method)
        for method in observed_methodologies(inputs)
    }
    assert computations.keys() == {"banister_1991", "threshold"}
    assert all(computation is not None for computation in computations.values())
    for computation in computations.values():
        assert computation is not None
        assert (
            computation.constants.tau_fitness_days,
            computation.constants.tau_fatigue_days,
            computation.constants.k_fitness,
            computation.constants.k_fatigue,
        ) == (37.0, 9.0, 1.3, 2.7)
        assert computation.constants.provenance.value == "configured"
        assert computation.constants.origin == (
            "the athlete's own configured constants (tau_fitness_days=37.0, "
            "tau_fatigue_days=9.0, k_fitness=1.3, k_fatigue=2.7)."
        )
        assert computation.threshold == 0.83

    expected = _expected_rows(root)
    fractional_daily = [
        row[2]
        for row in expected["daily_load"]
        if isinstance(row[2], float) and row[2] != 0.0 and row[0] == "threshold"
    ]
    assert any(value != round(value, 1) for value in fractional_daily)
    fractional_weekly = [
        row[5]
        for row in expected["weekly_load"]
        if isinstance(row[5], float) and row[5] != 0.0 and row[0] == "threshold"
    ]
    assert any(value != round(value, 1) for value in fractional_weekly)
    assert LOAD_SERIES_PRODUCER.rows(snapshot_of(root, today=TODAY)) == expected


def test_ambiguous_default_marks_no_methodology_and_inferred_default_is_marked(
    tmp_path: Path,
) -> None:
    unconfigured = build_fixture_root(tmp_path / "ambiguous", methodology=False)
    ambiguous_rows = LOAD_SERIES_PRODUCER.rows(snapshot_of(unconfigured, today=TODAY))
    assert len(ambiguous_rows["load_series"]) == 2
    assert all(row[1:3] == (False, None) for row in ambiguous_rows["load_series"])

    inferred = build_fixture_root(tmp_path / "inferred", methodology=False)
    for path in (inferred / "workouts").glob("*.md"):
        text = path.read_text(encoding="utf-8")
        if "load_value:" in text:
            text = re.sub(
                r"(?m)^load_methodology:.*\n", "load_methodology: threshold\n", text
            )
            path.write_text(text, encoding="utf-8")
    inferred_rows = LOAD_SERIES_PRODUCER.rows(snapshot_of(inferred, today=TODAY))
    assert len(inferred_rows["load_series"]) == 1
    assert inferred_rows["load_series"][0][1:3] == (True, "inferred")


def test_no_load_archive_returns_three_empty_tables(derived_root: Path) -> None:
    for path in (derived_root / "workouts").glob("*.md"):
        original = path.read_text(encoding="utf-8")
        without_loads = re.sub(r"(?m)^load_value:.*\n", "", original)
        without_methods = re.sub(r"(?m)^load_methodology:.*\n", "", without_loads)
        path.write_text(without_methods, encoding="utf-8")
    rows = LOAD_SERIES_PRODUCER.rows(snapshot_of(derived_root, today=TODAY))
    assert rows == {"load_series": (), "daily_load": (), "weekly_load": ()}


def test_fingerprint_tracks_workouts_and_settings_but_not_date_or_held_set(
    derived_root: Path,
) -> None:
    scan = scan_workout_pages(derived_root)
    snapshot = snapshot_of(derived_root, today=TODAY)
    original = LOAD_SERIES_PRODUCER.fingerprint(snapshot)
    assert original == LOAD_SERIES_PRODUCER.fingerprint(
        snapshot_of(derived_root, today=TODAY)
    )
    later = replace(snapshot, today=date(2027, 1, 1))
    assert original == LOAD_SERIES_PRODUCER.fingerprint(later)

    held = frozenset(page.page_key for page in snapshot.pages[:2])
    held_snapshot = corpus_snapshot(
        derived_root,
        scan,
        today=TODAY,
        athlete_fingerprint=athlete_fingerprint(load_athlete_inputs(derived_root)),
        held=held,
    )
    assert len(held) == 2
    assert len(held_snapshot.pages) == 2
    assert held_snapshot.pages != snapshot.pages
    assert held_snapshot.left_out != snapshot.left_out
    assert original == LOAD_SERIES_PRODUCER.fingerprint(held_snapshot)

    page = derived_root / "workouts/2026-02-02-run-a.md"
    before = page.read_bytes()
    page.write_bytes(before + b"\n")
    changed_workout = snapshot_of(derived_root, today=TODAY)
    assert original != LOAD_SERIES_PRODUCER.fingerprint(changed_workout)
    assert settings_digest(derived_root) == settings_digest(changed_workout.data_root)
    assert workouts_digest(changed_workout) != workouts_digest(snapshot)
    page.write_bytes(before)
    restored = snapshot_of(derived_root, today=TODAY)
    assert original == LOAD_SERIES_PRODUCER.fingerprint(restored)

    settings = derived_root / "fitdocs.toml"
    original_settings_digest = settings_digest(derived_root)
    before_settings = settings.read_bytes()
    settings.write_bytes(before_settings + b"\n# fingerprint input\n")
    changed_settings = snapshot_of(derived_root, today=TODAY)
    assert original != LOAD_SERIES_PRODUCER.fingerprint(changed_settings)
    assert settings_digest(derived_root) != original_settings_digest
    assert workouts_digest(changed_settings) == workouts_digest(restored)


def test_week_rows_keep_iso_year_across_calendar_year_boundary(tmp_path: Path) -> None:
    root = build_fixture_root(tmp_path / "cross-year")
    first = root / "workouts/2026-02-02-run-a.md"
    second = root / "workouts/2026-02-03-ride-a.md"
    first.write_text(
        first.read_text(encoding="utf-8").replace("2026-02-02", "2025-12-28"),
        encoding="utf-8",
    )
    second.write_text(
        second.read_text(encoding="utf-8").replace("2026-02-03", "2025-12-29"),
        encoding="utf-8",
    )
    rows = LOAD_SERIES_PRODUCER.rows(snapshot_of(root, today=TODAY))
    expected = _expected_rows(root)
    assert rows == expected
    threshold_weeks = [row for row in rows["weekly_load"] if row[0] == "threshold"]
    assert any(
        row[1] == 2026 and row[3] == date(2025, 12, 29) for row in threshold_weeks
    )
    assert {row[1] for row in threshold_weeks} >= {2025, 2026}


def test_fingerprint_is_exact_digest_of_two_declared_inputs(derived_root: Path) -> None:
    snapshot = snapshot_of(derived_root, today=TODAY)
    assert LOAD_SERIES_PRODUCER.fingerprint(snapshot) == digest(
        {
            "workouts": workouts_digest(snapshot),
            "settings": settings_digest(derived_root),
        }
    )
