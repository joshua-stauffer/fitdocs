"""Synthetic checks for the per-source recovery computation."""

from dataclasses import astuple
from datetime import date, timedelta
from math import exp, log, sqrt
from pathlib import Path
from typing import Any

import pytest

from fitdocs.recovery.baselines import BaselineDay, Baselines
from fitdocs.recovery.constants import SLEEP_METRICS
from fitdocs.wellness import Metric, SeriesValue, read_series
from tests.recovery.builders import series_value, stage_series, wellness_series

D = date(2026, 4, 12)
HR = Metric.RESTING_HR_BPM


def item(
    offset: int,
    value: float,
    metric: Metric = HR,
    source: str = "device-a",
    *,
    canonical: bool = True,
    origin: str | None = "garmin",
) -> SeriesValue:
    return series_value(
        D + timedelta(days=offset),
        value,
        metric=metric,
        source=source,
        canonical=canonical,
        origin=origin,
    )


def compute(
    values: list[SeriesValue], metric: Metric = HR, source: str = "device-a"
) -> BaselineDay:
    return Baselines.of(wellness_series(values)).on(metric, source, D)


@pytest.mark.parametrize(
    "field, expected",
    [
        ("metric", HR),
        ("source", "device-a"),
        ("day", D),
        ("value", 77.0),
        ("origin", "garmin"),
    ],
)
def test_daily_identity(field: str, expected: object) -> None:
    assert getattr(compute([item(0, 77)]), field) == expected


@pytest.mark.parametrize(
    "field, expected",
    [
        ("value", None),
        ("origin", None),
        ("rolling_count", 0),
        ("baseline_count", 0),
        ("rolling_mean", None),
        ("baseline_mean", None),
        ("baseline_sd", None),
        ("range_low", None),
        ("range_high", None),
        ("position", None),
    ],
)
def test_absent_source(field: str, expected: object) -> None:
    assert getattr(compute([item(0, 77)], source="missing"), field) == expected


@pytest.mark.parametrize(
    "field, expected",
    [
        ("value", None),
        ("origin", None),
        ("rolling_count", 3),
        ("rolling_mean", 60.0),
    ],
)
def test_gap_has_mean_without_daily_value(field: str, expected: object) -> None:
    assert (
        getattr(compute([item(-6, 40), item(-4, 60), item(-1, 80)]), field) == expected
    )


@pytest.mark.parametrize("today, expected", [(20, 40.0), (80, 60.0)])
def test_rolling_includes_today_and_day_minus_six(
    today: float, expected: float
) -> None:
    assert (
        compute(
            [item(-7, 249), item(-6, 40), item(-2, 60), item(0, today)]
        ).rolling_mean
        == expected
    )


@pytest.mark.parametrize("count, expected", [(2, None), (3, 60.0)])
def test_rolling_minimum(count: int, expected: float | None) -> None:
    assert (
        compute([item(-offset, 60) for offset in range(count)]).rolling_mean == expected
    )


@pytest.mark.parametrize("count, expected", [(29, None), (30, 60.0)])
def test_baseline_minimum(count: int, expected: float | None) -> None:
    assert (
        compute([item(-offset, 60) for offset in range(1, count + 1)]).baseline_mean
        == expected
    )


@pytest.mark.parametrize("today", [25, 125])
@pytest.mark.parametrize(
    "field, expected",
    [
        ("baseline_count", 30),
        ("baseline_mean", 62.0),
        ("baseline_sd", sqrt(120.0)),
        ("range_low", 62 - 0.5 * sqrt(120.0)),
        ("range_high", 62 + 0.5 * sqrt(120.0)),
    ],
)
def test_baseline_reaches_sixty_excludes_sixty_one_and_today(
    today: float,
    field: str,
    expected: float,
) -> None:
    values = [item(-offset, 60) for offset in range(1, 30)]
    values += [item(-60, 120), item(-61, 249), item(0, today)]
    assert getattr(compute(values), field) == pytest.approx(expected)


@pytest.mark.parametrize("metric", [Metric.HRV_SDNN_MS, Metric.HRV_RMSSD_MS])
@pytest.mark.parametrize(
    "field", ["rolling_mean", "baseline_mean", "baseline_sd", "range_low", "range_high"]
)
def test_hrv_uses_log_scale(metric: Metric, field: str) -> None:
    historical = [10.0] * 15 + [90.0] * 15
    values = [
        item(-offset, value, metric)
        for offset, value in zip(range(1, 31), historical, strict=True)
    ]
    values += [item(0, 250, metric)]
    mu = (log(10) + log(90)) / 2
    sd = sqrt(15 * ((log(10) - mu) ** 2 + (log(90) - mu) ** 2) / 29)
    expected = {
        "rolling_mean": exp((log(250) + 6 * log(10)) / 7),
        "baseline_mean": 30.0,
        "baseline_sd": sd,
        "range_low": exp(mu - 0.5 * sd),
        "range_high": exp(mu + 0.5 * sd),
    }
    assert getattr(compute(values, metric), field) == pytest.approx(expected[field])


@pytest.mark.parametrize(
    "today, expected",
    [
        (54, "below"),
        (57, "within"),
        (60, "within"),
        (63, "within"),
        (66, "above"),
    ],
)
def test_position_with_inclusive_exact_bounds(today: int, expected: str) -> None:
    historical = [60] + [62] * 14 + [58] * 14
    values = [
        item(-offset, value)
        for offset, value in zip(range(10, 39), historical, strict=True)
    ]
    values += [item(-2, 62), item(-1, 58), item(0, today)]
    assert compute(values).position == expected


@pytest.mark.parametrize(
    "values",
    [
        [item(-1, 60), item(0, 60)],
        [item(-offset, 60) for offset in range(10, 40)] + [item(-1, 60), item(0, 60)],
        [item(-2, 60), item(-1, 60), item(0, 60)],
    ],
)
def test_position_missing_rolling_or_range(values: list[SeriesValue]) -> None:
    assert compute(values).position is None


@pytest.mark.parametrize(
    "source, metric, expected",
    [
        ("device-a", HR, 41.0),
        ("device-b", HR, 71.0),
        ("device-a", Metric.HRV_SDNN_MS, 15.0),
        ("device-a", Metric.HRV_RMSSD_MS, 85.0),
    ],
)
@pytest.mark.parametrize("field", ["value", "rolling_mean", "baseline_mean"])
def test_source_and_metric_separation(
    source: str, metric: Metric, expected: float, field: str
) -> None:
    values = []
    for offset in range(61):
        values += [
            item(-offset, 41),
            item(-offset, 71, source="device-b", canonical=False),
            item(-offset, 15, Metric.HRV_SDNN_MS),
            item(-offset, 85, Metric.HRV_RMSSD_MS),
        ]
    assert getattr(compute(values, metric, source), field) == pytest.approx(expected)


@pytest.mark.parametrize("metric", SLEEP_METRICS)
@pytest.mark.parametrize("field", ["range_low", "range_high", "position"])
def test_sleep_has_no_range(metric: Metric, field: str) -> None:
    assert (
        getattr(
            compute([item(-offset, 60, metric) for offset in range(61)], metric),
            field,
        )
        is None
    )


def test_unsupported_metric() -> None:
    with pytest.raises(ValueError, match="unsupported"):
        compute([item(0, 100, Metric.STEPS)], Metric.STEPS)


def test_staged_builder_roundtrip(tmp_path: Path) -> None:
    values = [
        item(0, 77),
        item(-1, 58),
        item(-1, 81, source="device-b", canonical=False),
    ]
    series = wellness_series(values)
    stage_series(tmp_path, series)
    assert astuple(Baselines.of(read_series(tmp_path)).on(HR, "device-a", D)) == (
        HR,
        "device-a",
        D,
        77,
        "garmin",
        None,
        2,
        None,
        None,
        1,
        None,
        None,
        None,
    )


@pytest.mark.parametrize(
    "pair, today, expected",
    [
        ((100, 100), 100, "below"),
        ((100, 900), 300, "within"),
        ((900, 900), 900, "above"),
    ],
)
def test_hrv_position_compares_transformed_values(
    pair: tuple[int, int],
    today: float,
    expected: str,
) -> None:
    metric = Metric.HRV_RMSSD_MS
    historical = [100] * (15 - pair.count(100)) + [900] * (15 - pair.count(900))
    values = [
        item(-offset, value, metric)
        for offset, value in zip(range(10, 38), historical, strict=True)
    ]
    values += [
        item(-2, pair[0], metric),
        item(-1, pair[1], metric),
        item(0, today, metric),
    ]
    assert compute(values, metric).position == expected


@pytest.mark.parametrize("field, expected", [("value", 77), ("origin", None)])
def test_present_value_without_origin(field: str, expected: object) -> None:
    assert getattr(compute([item(0, 77, origin=None)]), field) == expected


def test_fsum_retains_small_contributions() -> None:
    metric = Metric.SLEEP_S
    assert (
        compute(
            [item(-2, 86400, metric), item(-1, 1.1, metric), item(0, 1.1, metric)],
            metric,
        ).rolling_mean
        == 86402.2 / 3
    )


def test_indexes_only_supported_metrics_and_preserves_canonical() -> None:
    values = [
        item(0, 41),
        item(0, 71, source="device-b", canonical=False),
        item(0, 99, Metric.STEPS),
    ]
    engine = Baselines.of(wellness_series(values))
    assert (engine._values, engine._canonical) == (
        {(HR, "device-a"): {D: (41, "garmin")}, (HR, "device-b"): {D: (71, "garmin")}},
        {(HR, D): "device-a"},
    )


def test_on_uses_bounded_date_lookups() -> None:
    class CountingDays(dict[date, tuple[float, str | None]]):
        lookups = 0

        def get(self, key: date, default: Any = None) -> Any:
            self.lookups += 1
            return super().get(key, default)

    values = CountingDays(
        {D - timedelta(days=offset): (60, "garmin") for offset in range(1000)}
    )
    Baselines({(HR, "device-a"): values}, {}).on(HR, "device-a", D)
    assert values.lookups == 68


_VariedConfig = tuple[
    Metric, str, str, int, tuple[int, int], tuple[tuple[int, int], ...]
]
_VARIED_CONFIGS: tuple[_VariedConfig, ...] = (
    (
        Metric.RESTING_HR_BPM,
        "device-a",
        "garmin",
        30,
        (40, 60),
        ((0, 90), (-1, 88), (-2, 86)),
    ),
    (
        Metric.RESTING_HR_BPM,
        "device-b",
        "apple-health",
        31,
        (100, 130),
        ((0, 64), (-1, 62), (-3, 60), (-6, 58)),
    ),
    (
        Metric.HRV_SDNN_MS,
        "device-a",
        "intervals-icu",
        32,
        (80, 160),
        ((0, 14), (-1, 12), (-2, 16), (-4, 18), (-6, 20)),
    ),
    (
        Metric.HRV_SDNN_MS,
        "device-b",
        "polar",
        33,
        (15, 45),
        ((-1, 180), (-2, 200), (-3, 220), (-4, 240), (-5, 260), (-6, 280)),
    ),
    (
        Metric.HRV_RMSSD_MS,
        "device-a",
        "whoop",
        34,
        (120, 240),
        ((0, 500), (-1, 480), (-2, 520), (-3, 540), (-4, 560), (-5, 580), (-6, 600)),
    ),
    (
        Metric.HRV_RMSSD_MS,
        "device-b",
        "oura",
        35,
        (300, 600),
        ((0, 25), (-3, 22), (-5, 24)),
    ),
    (
        Metric.SLEEP_S,
        "device-a",
        "sleep-a-0",
        36,
        (10, 40),
        ((0, 30), (-1, 32), (-2, 34)),
    ),
    (
        Metric.SLEEP_S,
        "device-b",
        "sleep-b-0",
        42,
        (80, 160),
        ((0, 100), (-1, 103), (-2, 106), (-3, 109)),
    ),
    (
        Metric.SLEEP_DEEP_S,
        "device-a",
        "sleep-a-1",
        37,
        (11, 42),
        ((0, 33), (-1, 35), (-2, 37), (-3, 39)),
    ),
    (
        Metric.SLEEP_DEEP_S,
        "device-b",
        "sleep-b-1",
        43,
        (82, 163),
        ((0, 105), (-1, 108), (-2, 111), (-3, 114), (-4, 117)),
    ),
    (
        Metric.SLEEP_LIGHT_S,
        "device-a",
        "sleep-a-2",
        38,
        (12, 44),
        ((0, 36), (-1, 38), (-2, 40), (-3, 42), (-4, 44)),
    ),
    (
        Metric.SLEEP_LIGHT_S,
        "device-b",
        "sleep-b-2",
        44,
        (84, 166),
        ((0, 110), (-1, 113), (-2, 116), (-3, 119), (-4, 122), (-5, 125)),
    ),
    (
        Metric.SLEEP_REM_S,
        "device-a",
        "sleep-a-3",
        39,
        (13, 46),
        ((0, 39), (-1, 41), (-2, 43), (-3, 45), (-4, 47), (-5, 49)),
    ),
    (
        Metric.SLEEP_REM_S,
        "device-b",
        "sleep-b-3",
        45,
        (86, 169),
        ((0, 115), (-1, 118), (-2, 121), (-3, 124), (-4, 127), (-5, 130), (-6, 133)),
    ),
    (
        Metric.SLEEP_AWAKE_S,
        "device-a",
        "sleep-a-4",
        40,
        (14, 48),
        ((0, 42), (-1, 44), (-2, 46), (-3, 48), (-4, 50), (-5, 52), (-6, 54)),
    ),
    (
        Metric.SLEEP_AWAKE_S,
        "device-b",
        "sleep-b-4",
        46,
        (88, 172),
        ((-1, 123), (-2, 126), (-3, 129), (-4, 132)),
    ),
    (
        Metric.SLEEP_HR_BPM,
        "device-a",
        "sleep-a-5",
        41,
        (15, 50),
        ((0, 45), (-1, 47), (-2, 49)),
    ),
    (
        Metric.SLEEP_HR_BPM,
        "device-b",
        "sleep-b-5",
        47,
        (90, 175),
        ((0, 125), (-1, 128), (-2, 131), (-3, 134), (-4, 137)),
    ),
)

_VARIED_EXPECTED: tuple[tuple[Metric, str, dict[str, object]], ...] = (
    (
        Metric.RESTING_HR_BPM,
        "device-a",
        {
            "metric": Metric.RESTING_HR_BPM,
            "source": "device-a",
            "day": D,
            "origin": "garmin",
            "value": 90,
            "rolling_mean": 88.0,
            "rolling_count": 3,
            "baseline_mean": 52.46666666666667,
            "baseline_sd": 13.591917814828689,
            "baseline_count": 30,
            "range_low": 45.67070775925232,
            "range_high": 59.262625574081014,
            "position": "above",
        },
    ),
    (
        Metric.RESTING_HR_BPM,
        "device-b",
        {
            "metric": Metric.RESTING_HR_BPM,
            "source": "device-b",
            "day": D,
            "origin": "apple-health",
            "value": 64,
            "rolling_mean": 61.0,
            "rolling_count": 4,
            "baseline_mean": 109.6774193548387,
            "baseline_sd": 21.988462272707466,
            "baseline_count": 31,
            "range_low": 98.68318821848497,
            "range_high": 120.67165049119244,
            "position": "below",
        },
    ),
    (
        Metric.HRV_SDNN_MS,
        "device-a",
        {
            "metric": Metric.HRV_SDNN_MS,
            "source": "device-a",
            "day": D,
            "origin": "intervals-icu",
            "value": 14,
            "rolling_mean": 15.745133708141406,
            "rolling_count": 5,
            "baseline_mean": 88.7446085868695,
            "baseline_sd": 0.7343679709126656,
            "baseline_count": 32,
            "range_low": 61.471809815197965,
            "range_high": 128.1173529283263,
            "position": "below",
        },
    ),
    (
        Metric.HRV_SDNN_MS,
        "device-b",
        {
            "metric": Metric.HRV_SDNN_MS,
            "source": "device-b",
            "day": D,
            "origin": None,
            "value": None,
            "rolling_mean": 227.42836739579326,
            "rolling_count": 6,
            "baseline_mean": 37.90797178807299,
            "baseline_sd": 0.9970707501362333,
            "baseline_count": 33,
            "range_low": 23.026046974634166,
            "range_high": 62.40820782952341,
            "position": "above",
        },
    ),
    (
        Metric.HRV_RMSSD_MS,
        "device-a",
        {
            "metric": Metric.HRV_RMSSD_MS,
            "source": "device-a",
            "day": D,
            "origin": "whoop",
            "value": 500,
            "rolling_mean": 538.5134026447004,
            "rolling_count": 7,
            "baseline_mean": 208.51827840871317,
            "baseline_sd": 0.5539417316237866,
            "baseline_count": 34,
            "range_low": 158.07282393376755,
            "range_high": 275.0622867897373,
            "position": "above",
        },
    ),
    (
        Metric.HRV_RMSSD_MS,
        "device-b",
        {
            "metric": Metric.HRV_RMSSD_MS,
            "source": "device-b",
            "day": D,
            "origin": "oura",
            "value": 25,
            "rolling_mean": 23.633315009350024,
            "rolling_count": 3,
            "baseline_mean": 355.6106194812811,
            "baseline_sd": 0.7646764484690388,
            "baseline_count": 35,
            "range_low": 242.620414680322,
            "range_high": 521.2212371101725,
            "position": "below",
        },
    ),
    (
        Metric.SLEEP_S,
        "device-a",
        {
            "metric": Metric.SLEEP_S,
            "source": "device-a",
            "day": D,
            "origin": "sleep-a-0",
            "value": 30,
            "rolling_mean": 32.0,
            "rolling_count": 3,
            "baseline_mean": 25.444444444444443,
            "baseline_sd": 14.902434018727936,
            "baseline_count": 36,
            "range_low": None,
            "range_high": None,
            "position": None,
        },
    ),
    (
        Metric.SLEEP_S,
        "device-b",
        {
            "metric": Metric.SLEEP_S,
            "source": "device-b",
            "day": D,
            "origin": "sleep-b-0",
            "value": 100,
            "rolling_mean": 104.5,
            "rolling_count": 4,
            "baseline_mean": 118.04761904761905,
            "baseline_sd": 39.151333890588084,
            "baseline_count": 42,
            "range_low": None,
            "range_high": None,
            "position": None,
        },
    ),
    (
        Metric.SLEEP_DEEP_S,
        "device-a",
        {
            "metric": Metric.SLEEP_DEEP_S,
            "source": "device-a",
            "day": D,
            "origin": "sleep-a-1",
            "value": 33,
            "rolling_mean": 36.0,
            "rolling_count": 4,
            "baseline_mean": 27.35135135135135,
            "baseline_sd": 15.348210565651215,
            "baseline_count": 37,
            "range_low": None,
            "range_high": None,
            "position": None,
        },
    ),
    (
        Metric.SLEEP_DEEP_S,
        "device-b",
        {
            "metric": Metric.SLEEP_DEEP_S,
            "source": "device-b",
            "day": D,
            "origin": "sleep-b-1",
            "value": 105,
            "rolling_mean": 111.0,
            "rolling_count": 5,
            "baseline_mean": 120.62790697674419,
            "baseline_sd": 39.116445972441696,
            "baseline_count": 43,
            "range_low": None,
            "range_high": None,
            "position": None,
        },
    ),
    (
        Metric.SLEEP_LIGHT_S,
        "device-a",
        {
            "metric": Metric.SLEEP_LIGHT_S,
            "source": "device-a",
            "day": D,
            "origin": "sleep-a-2",
            "value": 36,
            "rolling_mean": 40.0,
            "rolling_count": 5,
            "baseline_mean": 29.36842105263158,
            "baseline_sd": 15.8786292767926,
            "baseline_count": 38,
            "range_low": None,
            "range_high": None,
            "position": None,
        },
    ),
    (
        Metric.SLEEP_LIGHT_S,
        "device-b",
        {
            "metric": Metric.SLEEP_LIGHT_S,
            "source": "device-b",
            "day": D,
            "origin": "sleep-b-2",
            "value": 110,
            "rolling_mean": 117.5,
            "rolling_count": 6,
            "baseline_mean": 123.38636363636364,
            "baseline_sd": 39.09274357758525,
            "baseline_count": 44,
            "range_low": None,
            "range_high": None,
            "position": None,
        },
    ),
    (
        Metric.SLEEP_REM_S,
        "device-a",
        {
            "metric": Metric.SLEEP_REM_S,
            "source": "device-a",
            "day": D,
            "origin": "sleep-a-3",
            "value": 39,
            "rolling_mean": 44.0,
            "rolling_count": 6,
            "baseline_mean": 31.487179487179485,
            "baseline_sd": 16.498599294408688,
            "baseline_count": 39,
            "range_low": None,
            "range_high": None,
            "position": None,
        },
    ),
    (
        Metric.SLEEP_REM_S,
        "device-b",
        {
            "metric": Metric.SLEEP_REM_S,
            "source": "device-b",
            "day": D,
            "origin": "sleep-b-3",
            "value": 115,
            "rolling_mean": 124.0,
            "rolling_count": 7,
            "baseline_mean": 126.31111111111112,
            "baseline_sd": 39.10523228315096,
            "baseline_count": 45,
            "range_low": None,
            "range_high": None,
            "position": None,
        },
    ),
    (
        Metric.SLEEP_AWAKE_S,
        "device-a",
        {
            "metric": Metric.SLEEP_AWAKE_S,
            "source": "device-a",
            "day": D,
            "origin": "sleep-a-4",
            "value": 42,
            "rolling_mean": 48.0,
            "rolling_count": 7,
            "baseline_mean": 33.7,
            "baseline_sd": 17.207929001272074,
            "baseline_count": 40,
            "range_low": None,
            "range_high": None,
            "position": None,
        },
    ),
    (
        Metric.SLEEP_AWAKE_S,
        "device-b",
        {
            "metric": Metric.SLEEP_AWAKE_S,
            "source": "device-b",
            "day": D,
            "origin": None,
            "value": None,
            "rolling_mean": 127.5,
            "rolling_count": 4,
            "baseline_mean": 129.7826086956522,
            "baseline_sd": 40.59442383353669,
            "baseline_count": 46,
            "range_low": None,
            "range_high": None,
            "position": None,
        },
    ),
    (
        Metric.SLEEP_HR_BPM,
        "device-a",
        {
            "metric": Metric.SLEEP_HR_BPM,
            "source": "device-a",
            "day": D,
            "origin": "sleep-a-5",
            "value": 45,
            "rolling_mean": 47.0,
            "rolling_count": 3,
            "baseline_mean": 32.829268292682926,
            "baseline_sd": 17.62229048538298,
            "baseline_count": 41,
            "range_low": None,
            "range_high": None,
            "position": None,
        },
    ),
    (
        Metric.SLEEP_HR_BPM,
        "device-b",
        {
            "metric": Metric.SLEEP_HR_BPM,
            "source": "device-b",
            "day": D,
            "origin": "sleep-b-5",
            "value": 125,
            "rolling_mean": 131.0,
            "rolling_count": 5,
            "baseline_mean": 131.59574468085106,
            "baseline_sd": 41.092504116226486,
            "baseline_count": 47,
            "range_low": None,
            "range_high": None,
            "position": None,
        },
    ),
)


def varied_values() -> list[SeriesValue]:
    rows: list[tuple[Metric, str, str, list[tuple[int, int]]]] = []
    for metric, source, origin, count, pair, rolling in _VARIED_CONFIGS:
        older_count = count - sum(offset < 0 for offset, _ in rolling)
        observations = [(-10 - i, pair[i % 2]) for i in range(older_count)]
        rows.append((metric, source, origin, observations + list(rolling)))
    primary_days = {
        (metric, offset)
        for metric, source, _, observations in rows
        if source == "device-a"
        for offset, _ in observations
    }
    return [
        item(
            offset,
            value,
            metric,
            source,
            canonical=source == "device-a" or (metric, offset) not in primary_days,
            origin=origin,
        )
        for metric, source, origin, observations in rows
        for offset, value in observations
    ]


@pytest.mark.parametrize("metric, source, expected", _VARIED_EXPECTED)
@pytest.mark.parametrize(
    "field",
    [
        "metric",
        "source",
        "day",
        "value",
        "origin",
        "rolling_mean",
        "rolling_count",
        "baseline_mean",
        "baseline_sd",
        "baseline_count",
        "range_low",
        "range_high",
        "position",
    ],
)
def test_varied_source_metric_outputs(
    metric: Metric,
    source: str,
    expected: dict[str, object],
    field: str,
) -> None:
    observed = getattr(compute(varied_values(), metric, source), field)
    target = expected[field]
    assert observed == (
        pytest.approx(target, rel=1e-12) if isinstance(target, float) else target
    )


def test_baseline_fsum_precision() -> None:
    metric = Metric.SLEEP_S
    values = [item(-60, 86400, metric)] + [
        item(-offset, 1.1, metric) for offset in range(1, 30)
    ]
    assert compute(values, metric).baseline_mean == 86431.9 / 30


def test_deviation_fsum_precision() -> None:
    metric = Metric.SLEEP_S
    observations = [
        13899.3344,
        18940.8212,
        54381.0304,
        55806.2002,
        74150.7929,
        77620.1812,
        71106.0688,
        85613.9077,
        29065.8526,
        65755.4537,
        24971.2583,
        72957.3986,
        48206.3603,
        14112.7063,
        21481.6189,
        1421.9695,
        82792.1274,
        30527.6311,
        67973.0867,
        72541.3353,
        27930.4475,
        8446.8823,
        55872.2127,
        57297.6752,
        29948.6669,
        77917.0306,
        13295.9747,
        61837.0985,
        44801.519,
        17990.4096,
    ]
    values = [
        item(-offset, value, metric)
        for offset, value in zip(range(30, 0, -1), observations, strict=True)
    ]
    assert compute(values, metric).baseline_sd == 25932.064269051254
