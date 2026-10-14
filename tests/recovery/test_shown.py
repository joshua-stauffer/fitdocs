"""Synthetic shown-source and explicit as-of checks."""

import os
import time
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, timedelta
from math import sqrt

import pytest

from fitdocs.recovery import METHODS, Baselines
from fitdocs.wellness import Metric, SeriesValue
from tests.recovery.builders import series_value, wellness_series

D = date(2026, 4, 12)
HR = Metric.RESTING_HR_BPM


def item(
    offset: int,
    value: float,
    source: str = "selected",
    *,
    metric: Metric = HR,
    canonical: bool = True,
) -> SeriesValue:
    return series_value(
        D + timedelta(days=offset),
        value,
        metric=metric,
        source=source,
        canonical=canonical,
        origin=f"origin-{source}",
    )


@contextmanager
def _fake_system_date(fixed_timestamp: float, *, tz: str) -> Iterator[None]:
    original_time = time.time
    original_tz = os.environ.get("TZ")
    original_epoch = os.environ.get("SOURCE_DATE_EPOCH")
    time.time = lambda: fixed_timestamp
    os.environ["TZ"] = tz
    os.environ["SOURCE_DATE_EPOCH"] = str(int(fixed_timestamp))
    if hasattr(time, "tzset"):
        time.tzset()
    try:
        yield
    finally:
        time.time = original_time
        if original_tz is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = original_tz
        if original_epoch is None:
            os.environ.pop("SOURCE_DATE_EPOCH", None)
        else:
            os.environ["SOURCE_DATE_EPOCH"] = original_epoch
        if hasattr(time, "tzset"):
            time.tzset()


@pytest.mark.parametrize("metric", METHODS)
def test_today_canonical_wins(metric: Metric) -> None:
    engine = Baselines.of(
        wellness_series(
            [
                item(-1, 130, "older", metric=metric),
                item(0, 40, metric=metric),
                item(0, 90, "zz-decoy", metric=metric, canonical=False),
            ]
        )
    )
    assert engine.shown_source(metric, D) == "selected"


@pytest.mark.parametrize("metric", METHODS)
def test_latest_canonical_wins(metric: Metric) -> None:
    engine = Baselines.of(
        wellness_series(
            [
                item(-5, 130, "earlier", metric=metric),
                item(-2, 40, metric=metric),
                item(-2, 90, "zz-decoy", metric=metric, canonical=False),
            ]
        )
    )
    assert engine.shown_source(metric, D) == "selected"


@pytest.mark.parametrize("metric", METHODS)
@pytest.mark.parametrize("offset, expected", [(-6, "selected"), (-7, None)])
def test_carry_boundary(metric: Metric, offset: int, expected: str | None) -> None:
    engine = Baselines.of(wellness_series([item(offset, 65, metric=metric)]))
    assert engine.shown_source(metric, D) == expected


@pytest.mark.parametrize(
    "values",
    [[], [item(0, 500, metric=Metric.SLEEP_S)], [item(-7, 65)]],
    ids=["empty", "other-metric", "expired"],
)
@pytest.mark.parametrize("method", ["shown_source", "shown"])
def test_absent_canonical(values: list[SeriesValue], method: str) -> None:
    engine = Baselines.of(wellness_series(values))
    assert getattr(engine, method)(HR, D) is None


def rich_engine() -> Baselines:
    values = [
        item(-offset, 50 + offset, canonical=offset != 2) for offset in range(1, 61)
    ]
    values.append(item(-2, 130, "other"))
    return Baselines.of(wellness_series(values))


_EXPECTED: tuple[tuple[str, object], ...] = (
    ("metric", HR),
    ("source", "selected"),
    ("day", D),
    ("value", None),
    ("origin", None),
    ("rolling_mean", 53.5),
    ("rolling_count", 6),
    ("baseline_mean", 80.5),
    ("baseline_sd", sqrt(305)),
    ("baseline_count", 60),
    ("range_low", 80.5 - 0.5 * sqrt(305)),
    ("range_high", 80.5 + 0.5 * sqrt(305)),
    ("position", "below"),
)


@pytest.mark.parametrize("field, expected", _EXPECTED)
def test_shown_matches_real_on(field: str, expected: object) -> None:
    engine = rich_engine()
    observed = (
        getattr(engine.shown(HR, D), field),
        getattr(engine.on(HR, "selected", D), field),
    )
    target = (expected, expected)
    assert observed == (
        pytest.approx(target) if isinstance(expected, float) else target
    )


@pytest.mark.parametrize("tz", ["Antarctica/Troll", "Pacific/Honolulu"])
@pytest.mark.parametrize("timestamp", [0.0, 4070908800.0])
@pytest.mark.parametrize("field, expected", _EXPECTED)
def test_timezone_and_fake_date(
    tz: str, timestamp: float, field: str, expected: object
) -> None:
    with _fake_system_date(timestamp, tz=tz):
        engine = rich_engine()
        observed = (
            getattr(engine.shown(HR, D), field),
            getattr(engine.on(HR, "selected", D), field),
        )
    target = (expected, expected)
    assert observed == (
        pytest.approx(target) if isinstance(expected, float) else target
    )


_LATE_EXPECTED: tuple[tuple[int, str, object, object], ...] = (
    (60, "baseline_count", 59, 60),
    (60, "baseline_mean", 80.0, 81.0),
    (60, "baseline_sd", sqrt(295), sqrt(350)),
    (60, "range_low", 80 - 0.5 * sqrt(295), 81 - 0.5 * sqrt(350)),
    (60, "range_high", 80 + 0.5 * sqrt(295), 81 + 0.5 * sqrt(350)),
    (61, "baseline_count", 60, 60),
    (61, "baseline_mean", 80.5, 80.5),
    (61, "baseline_sd", sqrt(305), sqrt(305)),
    (61, "range_low", 80.5 - 0.5 * sqrt(305), 80.5 - 0.5 * sqrt(305)),
    (61, "range_high", 80.5 + 0.5 * sqrt(305), 80.5 + 0.5 * sqrt(305)),
)


@pytest.mark.parametrize("offset, field, before, after", _LATE_EXPECTED)
def test_late_value_dependency_bound(
    offset: int, field: str, before: object, after: object
) -> None:
    values = [item(i, 50 + i) for i in range(1, 62)]
    day = D + timedelta(days=offset)
    original = Baselines.of(wellness_series(values))
    updated = Baselines.of(wellness_series([*values, item(0, 140)]))
    observed = (
        getattr(original.shown(HR, day), field),
        getattr(updated.shown(HR, day), field),
        getattr(original.on(HR, "selected", day), field),
        getattr(updated.on(HR, "selected", day), field),
    )
    target = (before, after, before, after)
    assert observed == (pytest.approx(target) if isinstance(before, float) else target)


_DISPATCH_CASES: tuple[tuple[Metric, int, float], ...] = (
    (Metric.RESTING_HR_BPM, 30, 70),
    (Metric.HRV_SDNN_MS, 10, 20),
    (Metric.HRV_RMSSD_MS, 20, 40),
    (Metric.SLEEP_S, 3000, 7000),
    (Metric.SLEEP_DEEP_S, 600, 1400),
    (Metric.SLEEP_LIGHT_S, 1800, 4200),
    (Metric.SLEEP_REM_S, 840, 1960),
    (Metric.SLEEP_AWAKE_S, 60, 140),
    (Metric.SLEEP_HR_BPM, 15, 35),
)
_DISPATCH_SOURCES: tuple[tuple[str, float], ...] = (
    ("device-east", 1.0),
    ("device-west", 1.5),
)


@pytest.mark.parametrize("metric, base, rolling", _DISPATCH_CASES)
@pytest.mark.parametrize("source, scale", _DISPATCH_SOURCES)
@pytest.mark.parametrize("offset", [0, 1], ids=["present", "carried"])
def test_shown_dispatches_every_metric_and_source(
    metric: Metric, base: int, rolling: float, source: str, scale: float, offset: int
) -> None:
    values = [
        item(
            observation,
            metric_base * source_scale * factor,
            name,
            metric=observed_metric,
            canonical=(name == source) == (observation != -2),
        )
        for observed_metric, metric_base, _ in _DISPATCH_CASES
        for name, source_scale in _DISPATCH_SOURCES
        for observation, factor in [(-2, 1), (-1, 2), (0, 4)]
    ]
    engine = Baselines.of(wellness_series(values))
    day = D + timedelta(days=offset)
    fields = (
        "metric",
        "source",
        "day",
        "value",
        "origin",
        "rolling_mean",
        "rolling_count",
    )
    target = (
        metric,
        source,
        day,
        base * scale * 4 if offset == 0 else None,
        f"origin-{source}" if offset == 0 else None,
        pytest.approx(rolling * scale),
        3,
    )
    observed = tuple(
        tuple(getattr(result, field) for field in fields)
        for result in (engine.shown(metric, day), engine.on(metric, source, day))
    )
    assert observed == (target, target)


_SELECTOR_CURRENT_MEANS: dict[Metric, float] = {
    Metric.RESTING_HR_BPM: 75,
    Metric.HRV_SDNN_MS: 10 * sqrt(sqrt(24)),
    Metric.HRV_RMSSD_MS: 20 * sqrt(sqrt(24)),
    Metric.SLEEP_S: 7500,
    Metric.SLEEP_DEEP_S: 1500,
    Metric.SLEEP_LIGHT_S: 4500,
    Metric.SLEEP_REM_S: 2100,
    Metric.SLEEP_AWAKE_S: 150,
    Metric.SLEEP_HR_BPM: 37.5,
}


def selector_source(metric: Metric, kind: str) -> str:
    return f"source-{metric.value.replace('_', '-')}-{kind}"


def selector_values() -> list[SeriesValue]:
    return [
        item(
            offset,
            base * scale * factor,
            selector_source(metric, kind),
            metric=metric,
            canonical=(kind == "future") == (offset in {-1, 1}),
        )
        for metric, base, _ in _DISPATCH_CASES
        for kind, scale in [("current", 1.0), ("future", 1.5)]
        for offset, factor in [(-3, 1), (-2, 2), (-1, 4), (0, 3), (1, 5)]
    ]


@pytest.mark.parametrize("metric, base, earlier_mean", _DISPATCH_CASES)
@pytest.mark.parametrize("offset", [-1, 0], ids=["previous", "current"])
def test_shown_selects_requested_metric_and_day(
    metric: Metric, base: int, earlier_mean: float, offset: int
) -> None:
    engine = Baselines.of(wellness_series(selector_values()))
    day = D + timedelta(days=offset)
    source = selector_source(metric, "future" if offset == -1 else "current")
    value = base * 1.5 * 4 if offset == -1 else base * 3
    mean = earlier_mean * 1.5 if offset == -1 else _SELECTOR_CURRENT_MEANS[metric]
    fields = (
        "metric",
        "source",
        "day",
        "value",
        "origin",
        "rolling_mean",
        "rolling_count",
    )
    target = (
        metric,
        source,
        day,
        value,
        f"origin-{source}",
        pytest.approx(mean),
        3 if offset == -1 else 4,
    )
    observed = tuple(
        tuple(getattr(result, field) for field in fields)
        for result in (engine.shown(metric, day), engine.on(metric, source, day))
    )
    assert observed == (target, target)
