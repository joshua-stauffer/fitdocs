"""Wellness projection, exact inputs and the public index/query path."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import replace
from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import cast

import pytest
from typer.testing import CliRunner

import fitdocs.index.derived.wellness as wellness_module
from fitdocs.cli import app
from fitdocs.index.derived.wellness import WELLNESS_PRODUCER
from fitdocs.index.producer import CorpusSnapshot
from fitdocs.index.schema import ColumnType
from fitdocs.wellness import (
    DEFAULT_WELLNESS_SETTINGS,
    METRICS,
    Metric,
    SeriesReadError,
    SeriesValue,
    WellnessSeries,
    series_files,
)
from fitdocs.wellness.archive import commit_original
from fitdocs.wellness.engine import rebuild_series
from fitdocs.wellness.formats.intervals import FORMAT
from tests.wellness.builders_intervals import intervals_list_bytes, intervals_record
from tests.wellness.builders_series import write_series


def _snapshot(root: Path) -> CorpusSnapshot:
    return CorpusSnapshot(root, (), (), date(2032, 9, 6), "unused-athlete")


def _values() -> tuple[SeriesValue, ...]:
    return (
        SeriesValue(
            date(2031, 4, 8),
            Metric.RESTING_HR_BPM,
            "garmin-export",
            "garmin",
            57.25,
            False,
        ),
        SeriesValue(
            date(2031, 4, 8),
            Metric.RESTING_HR_BPM,
            "intervals-icu",
            "polar",
            63.5,
            True,
        ),
        SeriesValue(
            date(2028, 12, 3),
            Metric.VO2MAX_ML_PER_KG_MIN,
            "intervals-icu",
            None,
            41.75,
            True,
        ),
        SeriesValue(
            date(2031, 7, 2), Metric.MOOD_RATING, "intervals-icu", "coros", 4.0, True
        ),
    )


def test_exact_table_shape_and_producer_name() -> None:
    assert WELLNESS_PRODUCER.name == "derived.wellness"
    assert tuple(
        (table.name, tuple((column.name, column.type) for column in table.columns))
        for table in WELLNESS_PRODUCER.tables
    ) == (
        (
            "wellness_daily",
            (
                ("day", ColumnType.DATE),
                ("metric", ColumnType.VARCHAR),
                ("source", ColumnType.VARCHAR),
                ("origin", ColumnType.VARCHAR),
                ("value", ColumnType.DOUBLE),
                ("unit", ColumnType.VARCHAR),
                ("canonical", ColumnType.BOOLEAN),
            ),
        ),
    )


def test_rows_equal_reader_with_distinct_fields_and_registry_units(
    tmp_path: Path,
) -> None:
    write_series(tmp_path, _values())
    expected = (
        (
            date(2028, 12, 3),
            "vo2max_ml_per_kg_min",
            "intervals-icu",
            None,
            41.75,
            "ml_per_kg_min",
            True,
        ),
        (
            date(2031, 4, 8),
            "resting_hr_bpm",
            "garmin-export",
            "garmin",
            57.25,
            "bpm",
            False,
        ),
        (
            date(2031, 4, 8),
            "resting_hr_bpm",
            "intervals-icu",
            "polar",
            63.5,
            "bpm",
            True,
        ),
        (date(2031, 7, 2), "mood_rating", "intervals-icu", "coros", 4.0, None, True),
    )
    assert WELLNESS_PRODUCER.rows(_snapshot(tmp_path)) == {"wellness_daily": expected}


def test_future_registry_unit_is_used_without_schema_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_series(tmp_path, _values())
    monkeypatch.setitem(
        METRICS,
        Metric.VO2MAX_ML_PER_KG_MIN,
        replace(METRICS[Metric.VO2MAX_ML_PER_KG_MIN], unit="future_unit"),
    )
    assert (
        WELLNESS_PRODUCER.rows(_snapshot(tmp_path))["wellness_daily"][0][5]
        == "future_unit"
    )


def test_added_metric_uses_the_existing_row_structure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class AddedMetric(StrEnum):
        BALANCE = "future_balance"

    metric = cast(Metric, AddedMetric.BALANCE)
    monkeypatch.setitem(
        METRICS, metric, replace(METRICS[Metric.MOOD_RATING], metric=metric)
    )
    monkeypatch.setattr(
        wellness_module,
        "read_series",
        lambda root: WellnessSeries(
            (SeriesValue(date(2035, 2, 7), metric, "future-source", None, 2.75, True),)
        ),
    )
    assert WELLNESS_PRODUCER.rows(_snapshot(tmp_path)) == {
        "wellness_daily": (
            (
                date(2035, 2, 7),
                "future_balance",
                "future-source",
                None,
                2.75,
                None,
                True,
            ),
        )
    }


def _exact_fingerprint(root: Path) -> str:
    parts = {
        "series": [
            [
                path.relative_to(root).as_posix(),
                "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest(),
            ]
            for path in series_files(root)
        ]
    }
    return hashlib.sha256(
        json.dumps(parts, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def test_fingerprint_has_exact_ordered_relative_names_and_byte_digests(
    tmp_path: Path,
) -> None:
    write_series(tmp_path, _values())
    assert WELLNESS_PRODUCER.fingerprint(_snapshot(tmp_path)) == _exact_fingerprint(
        tmp_path
    )


def test_fingerprint_uses_filenames_even_with_equal_file_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = tmp_path / "first.csv"
    second = tmp_path / "second.csv"
    first.write_bytes(b"same bytes")
    second.write_bytes(b"same bytes")
    monkeypatch.setattr(wellness_module, "series_files", lambda root: (first,))
    before = WELLNESS_PRODUCER.fingerprint(_snapshot(tmp_path))
    monkeypatch.setattr(wellness_module, "series_files", lambda root: (second,))
    assert WELLNESS_PRODUCER.fingerprint(_snapshot(tmp_path)) != before


def test_fingerprint_keeps_series_files_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_series(tmp_path, _values())
    paths = series_files(tmp_path)
    before = WELLNESS_PRODUCER.fingerprint(_snapshot(tmp_path))
    monkeypatch.setattr(
        wellness_module, "series_files", lambda root: tuple(reversed(paths))
    )
    assert WELLNESS_PRODUCER.fingerprint(_snapshot(tmp_path)) != before


@pytest.mark.parametrize("change", ["year", "manifest", "rename", "missing"])
def test_fingerprint_changes_for_each_relevant_input(
    tmp_path: Path, change: str
) -> None:
    write_series(tmp_path, _values())
    snapshot = _snapshot(tmp_path)
    before = WELLNESS_PRODUCER.fingerprint(snapshot)
    year = tmp_path / "wellness/2028.csv"
    manifest = tmp_path / "wellness/manifest.toml"
    if change == "year":
        year.write_bytes(year.read_bytes().replace(b"41.75", b"42.75"))
    elif change == "manifest":
        manifest.write_bytes(manifest.read_bytes() + b"\n# manifest-only change\n")
    elif change == "rename":
        year.rename(year.with_name("2029.csv"))
        manifest.write_text(manifest.read_text().replace("2028.csv", "2029.csv"))
    else:
        year.unlink()
    assert WELLNESS_PRODUCER.fingerprint(snapshot) != before


@pytest.mark.parametrize("change", ["mtime", "unrelated"])
def test_fingerprint_ignores_noninputs(tmp_path: Path, change: str) -> None:
    paths = write_series(tmp_path, _values())
    before = WELLNESS_PRODUCER.fingerprint(_snapshot(tmp_path))
    if change == "mtime":
        for path in paths:
            os.utime(path, ns=(1_000_000_000, 2_000_000_000))
    else:
        (tmp_path / "wellness/1999.csv").write_bytes(b"unlisted")
        (tmp_path / "athlete.toml").write_text("unrelated")
    assert WELLNESS_PRODUCER.fingerprint(_snapshot(tmp_path)) == before


def test_absent_series_projects_no_rows(tmp_path: Path) -> None:
    assert WELLNESS_PRODUCER.rows(_snapshot(tmp_path)) == {"wellness_daily": ()}


def test_bad_series_error_propagates(tmp_path: Path) -> None:
    write_series(tmp_path, _values())
    (tmp_path / "wellness/2031.csv").write_bytes(b"broken")
    with pytest.raises(SeriesReadError):
        WELLNESS_PRODUCER.rows(_snapshot(tmp_path))


def _commit_and_rebuild(
    root: Path, candidate: Path, value: float, revision: str
) -> None:
    data = intervals_list_bytes(
        [intervals_record("2031-04-08", updated=revision, restingHR=value, mood=3)]
    )
    candidate.write_bytes(data)
    commit_original(root, FORMAT, candidate, hashlib.sha256(data).hexdigest())
    rebuild_series(root, settings=DEFAULT_WELLNESS_SETTINGS, force=False)


def _query(root: Path) -> object:
    result = CliRunner().invoke(
        app,
        [
            "query",
            "SELECT day, metric, source, origin, value, unit, canonical "
            "FROM wellness_daily ORDER BY metric",
            "--out",
            str(root),
            "--format",
            "json",
        ],
    )
    if result.exit_code:
        pytest.fail(f"query failed: {result.output} {result.exception}")
    return json.loads(result.stdout)["rows"]


def test_cli_build_refresh_and_unreadable_series_retains_previous_rows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "data"
    root.mkdir()
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    monkeypatch.setenv("FITDOCS_INDEX_DIR", str(tmp_path / "index"))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    candidate = tmp_path / "delivery.json"
    _commit_and_rebuild(root, candidate, 67.25, "2031-04-09T10:00:00Z")
    first = CliRunner().invoke(app, ["index", "--out", str(root)])
    assert first.exit_code == 0, first.output
    expected = [
        ["2031-04-08", "mood_rating", "intervals-icu", None, 3.0, None, True],
        ["2031-04-08", "resting_hr_bpm", "intervals-icu", None, 67.25, "bpm", True],
    ]
    assert _query(root) == expected
    _commit_and_rebuild(root, candidate, 71.5, "2031-04-10T10:00:00Z")
    second = CliRunner().invoke(app, ["index", "--out", str(root)])
    assert second.exit_code == 0, second.output
    expected[1][4] = 71.5
    assert _query(root) == expected
    (root / "wellness/2031.csv").write_bytes(b"broken")
    failed = CliRunner().invoke(app, ["index", "--out", str(root)])
    assert failed.exit_code == 0, failed.output
    assert "Could not refresh derived.wellness: SeriesReadError:" in failed.stdout
    assert _query(root) == expected
