"""Synthetic, source-attributed wellness inputs for morning-of tests."""

from collections import Counter
from collections.abc import Iterable
from datetime import date
from pathlib import Path

from fitdocs.wellness import Metric, SeriesValue, WellnessSeries
from tests.wellness.builders_series import write_series


def series_value(
    day: date,
    value: float,
    *,
    metric: Metric,
    source: str,
    canonical: bool,
    origin: str | None = None,
) -> SeriesValue:
    return SeriesValue(day, metric, source, origin, value, canonical)


def wellness_series(values: Iterable[SeriesValue]) -> WellnessSeries:
    items = tuple(values)
    keys = {(item.day, item.metric, item.source) for item in items}
    if len(keys) != len(items):
        raise ValueError("duplicate day, metric and source")
    groups = {(item.day, item.metric) for item in items}
    canonicals = Counter((item.day, item.metric) for item in items if item.canonical)
    if any(canonicals[group] != 1 for group in groups):
        raise ValueError("exactly one canonical value required per day and metric")
    return WellnessSeries(values=tuple(sorted(items)))


def stage_series(data_root: Path, series: WellnessSeries) -> tuple[Path, ...]:
    return write_series(data_root, series.values)
