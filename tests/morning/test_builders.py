"""Synthetic series builders for morning-of tests."""

from datetime import date
from pathlib import Path

import pytest

from fitdocs.wellness import Metric, SeriesValue, read_series
from tests.morning.builders import series_value, stage_series, wellness_series


@pytest.mark.parametrize(
    "expected",
    [
        SeriesValue(
            date(2001, 2, 3), Metric.HRV_SDNN_MS, "source-b", "apple", 43.25, False
        ),
        SeriesValue(
            date(2002, 4, 5), Metric.RESTING_HR_BPM, "source-a", None, 57.75, True
        ),
    ],
)
def test_series_value_keeps_each_field(expected: SeriesValue) -> None:
    item = series_value(
        expected.day,
        expected.value,
        metric=expected.metric,
        source=expected.source,
        origin=expected.origin,
        canonical=expected.canonical,
    )
    assert item == expected


def test_series_sorts_distinct_source_day_metric_patterns() -> None:
    earlier = date(2001, 2, 3)
    later = date(2001, 2, 4)
    items = (
        SeriesValue(later, Metric.HRV_SDNN_MS, "source-b", "garmin", 71, True),
        SeriesValue(earlier, Metric.HRV_SDNN_MS, "source-a", "apple", 31, True),
        SeriesValue(later, Metric.HRV_SDNN_MS, "source-a", None, 59, False),
        SeriesValue(earlier, Metric.HRV_RMSSD_MS, "source-a", None, 83, True),
        SeriesValue(earlier, Metric.HRV_SDNN_MS, "source-b", "garmin", 43, False),
    )
    assert wellness_series(iter(items)).values == (
        items[3],
        items[1],
        items[4],
        items[2],
        items[0],
    )


def test_series_rejects_duplicate_source_day_metric() -> None:
    item = SeriesValue(
        date(2001, 2, 3), Metric.HRV_SDNN_MS, "source-a", "apple", 31, True
    )
    with pytest.raises(ValueError, match="duplicate day, metric and source"):
        wellness_series((item, item))


@pytest.mark.parametrize("flags", [(False, False), (True, True)])
def test_series_requires_one_canonical_per_day_and_metric(
    flags: tuple[bool, bool],
) -> None:
    values = (
        SeriesValue(
            date(2001, 2, 3), Metric.HRV_SDNN_MS, "source-a", "apple", 31, flags[0]
        ),
        SeriesValue(
            date(2001, 2, 3), Metric.HRV_SDNN_MS, "source-b", "garmin", 43, flags[1]
        ),
    )
    with pytest.raises(ValueError, match="exactly one canonical"):
        wellness_series(values)


def test_stage_series_uses_sanctioned_writer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    series = wellness_series(
        (
            SeriesValue(
                date(2001, 2, 3), Metric.HRV_SDNN_MS, "source-a", "apple", 31, True
            ),
        )
    )
    recorded: list[tuple[Path, tuple[SeriesValue, ...]]] = []
    result = (tmp_path / "sentinel",)

    def write(root: Path, values: tuple[SeriesValue, ...]) -> tuple[Path, ...]:
        recorded.append((root, values))
        return result

    monkeypatch.setattr("tests.morning.builders.write_series", write)
    assert stage_series(tmp_path, series) == result
    assert recorded == [(tmp_path, series.values)]


def test_staged_series_round_trips(tmp_path: Path) -> None:
    values = (
        SeriesValue(
            date(2001, 2, 3), Metric.HRV_SDNN_MS, "source-a", "apple", 31, True
        ),
        SeriesValue(
            date(2001, 2, 3), Metric.HRV_SDNN_MS, "source-b", "garmin", 43, False
        ),
        SeriesValue(date(2002, 2, 4), Metric.HRV_RMSSD_MS, "source-b", None, 59, True),
    )
    stage_series(tmp_path, wellness_series(values))
    assert read_series(tmp_path).values == values
