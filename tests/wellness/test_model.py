"""The metric vocabulary and local sleep-day rule."""

from __future__ import annotations

import dataclasses
from datetime import date, datetime, timedelta, timezone

import pytest

from fitdocs.units import unit_named
from fitdocs.wellness.model import (
    METRICS,
    DaySnapshot,
    Metric,
    SeriesValue,
    accept_value,
    is_origin,
    wellness_day_of_sleep_end,
)

# name, label, unit, inclusive minimum, inclusive maximum.
DESIGN_TABLE: tuple[tuple[str, str, str | None, int, int], ...] = (
    ("resting_hr_bpm", "Resting HR", "bpm", 1, 250),
    ("min_hr_bpm", "Lowest HR", "bpm", 1, 250),
    ("max_hr_bpm", "Highest HR", "bpm", 1, 250),
    ("hrv_sdnn_ms", "HRV (SDNN)", "ms", 1, 1000),
    ("hrv_rmssd_ms", "HRV (rMSSD)", "ms", 1, 1000),
    ("sleep_s", "Sleep", "s", 1, 86400),
    ("sleep_deep_s", "Deep sleep", "s", 0, 86400),
    ("sleep_light_s", "Light sleep", "s", 0, 86400),
    ("sleep_rem_s", "REM sleep", "s", 0, 86400),
    ("sleep_awake_s", "Awake in sleep", "s", 0, 86400),
    ("sleep_hr_bpm", "Sleeping HR", "bpm", 1, 250),
    ("respiration_brpm", "Respiration", "brpm", 1, 100),
    ("spo2_pct", "SpO2", "pct", 1, 100),
    ("weight_kg", "Weight", "kg", 1, 500),
    ("vo2max_ml_per_kg_min", "VO2max", "ml_per_kg_min", 1, 100),
    ("vo2max_run_ml_per_kg_min", "VO2max (running)", "ml_per_kg_min", 1, 100),
    ("vo2max_ride_ml_per_kg_min", "VO2max (cycling)", "ml_per_kg_min", 1, 100),
    ("steps", "Steps", None, 1, 1000000),
    ("stress_level", "Stress level", None, 1, 100),
    ("body_battery_highest", "Body battery (highest)", None, 1, 100),
    ("body_battery_lowest", "Body battery (lowest)", None, 1, 100),
    ("fatigue_rating", "Fatigue (rating)", None, 1, 4),
    ("mood_rating", "Mood (rating)", None, 1, 4),
    ("motivation_rating", "Motivation (rating)", None, 1, 4),
    ("soreness_rating", "Soreness (rating)", None, 1, 4),
    ("stress_rating", "Stress (rating)", None, 1, 4),
    ("injury_rating", "Injury (rating)", None, 1, 4),
    ("hydration_rating", "Hydration (rating)", None, 1, 4),
)


def test_metric_table() -> None:
    assert tuple(metric.value for metric in Metric) == tuple(
        row[0] for row in DESIGN_TABLE
    )
    assert tuple(METRICS) == tuple(Metric)
    assert (
        tuple(
            (info.metric.value, info.label, info.unit, info.minimum, info.maximum)
            for info in METRICS.values()
        )
        == DESIGN_TABLE
    )


def test_labels_are_distinct_and_nonempty() -> None:
    assert len({info.label for info in METRICS.values()} - {""}) == 28


@pytest.mark.parametrize("metric", list(Metric))
def test_unit_and_zero_metadata(metric: Metric) -> None:
    info = METRICS[metric]
    if info.unit is not None:
        assert unit_named(info.unit) is not None
        assert metric.value.endswith("_" + info.unit)
    assert info.zero_is_absent == (info.minimum > 0)
    assert bool(info.description.strip())


@pytest.mark.parametrize(
    "metric,minimum,maximum",
    [
        (Metric.RESTING_HR_BPM, 1, 250),
        (Metric.SLEEP_REM_S, 0, 86400),
        (Metric.FATIGUE_RATING, 1, 4),
    ],
)
@pytest.mark.parametrize("endpoint", ["minimum", "maximum"])
def test_inclusive_bounds(
    metric: Metric, minimum: int, maximum: int, endpoint: str
) -> None:
    value = minimum if endpoint == "minimum" else maximum
    assert accept_value(metric, value) == float(value)


@pytest.mark.parametrize(
    "metric,value",
    [
        (Metric.RESTING_HR_BPM, 0),
        (Metric.RESTING_HR_BPM, 251),
        (Metric.SLEEP_REM_S, -1),
        (Metric.SLEEP_REM_S, 86401),
        (Metric.FATIGUE_RATING, 0),
        (Metric.FATIGUE_RATING, 5),
        (Metric.STRESS_LEVEL, -1),
    ],
)
def test_outside_bounds_is_absent(metric: Metric, value: float) -> None:
    assert accept_value(metric, value) is None


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_nonfinite_is_absent(value: float) -> None:
    assert accept_value(Metric.RESTING_HR_BPM, value) is None


def test_zero_sleep_stage_is_present() -> None:
    assert accept_value(Metric.SLEEP_REM_S, 0) == 0.0


def test_values_stay_on_recorded_scale() -> None:
    value = accept_value(Metric.MOOD_RATING, 2.75)
    assert value == 2.75
    assert type(accept_value(Metric.STEPS, 357)) is float


@pytest.mark.parametrize(
    "offset,year,month,day,hour,minute,expected",
    [
        (9, 2024, 3, 10, 17, 59, date(2024, 3, 10)),
        (9, 2024, 3, 10, 18, 0, date(2024, 3, 11)),
        (-8, 2024, 7, 20, 17, 59, date(2024, 7, 20)),
        (-8, 2024, 7, 20, 18, 0, date(2024, 7, 21)),
    ],
)
def test_sleep_day_uses_recorded_offset(
    offset: int, year: int, month: int, day: int, hour: int, minute: int, expected: date
) -> None:
    end = datetime(
        year, month, day, hour, minute, tzinfo=timezone(timedelta(hours=offset))
    )
    assert wellness_day_of_sleep_end(end) == expected


def test_naive_sleep_end_rejected() -> None:
    with pytest.raises(ValueError):
        wellness_day_of_sleep_end(datetime(2024, 5, 4, 18))


@pytest.mark.parametrize("origin", ["garmin", "oura", "zepp-life"])
def test_valid_origins(origin: str) -> None:
    assert is_origin(origin)


@pytest.mark.parametrize("origin", ["Garmin", "garmin_", "-x", "", "garmin\n"])
def test_invalid_origins(origin: str) -> None:
    assert not is_origin(origin)


def test_snapshot_and_series_records() -> None:
    snapshot = DaySnapshot(
        date(2024, 4, 3),
        frozenset({Metric.SLEEP_REM_S}),
        {Metric.SLEEP_REM_S: 93.0},
        {Metric.SLEEP_REM_S: "oura"},
        None,
        7,
    )
    assert dataclasses.asdict(snapshot) == {
        "day": date(2024, 4, 3),
        "covers": frozenset({Metric.SLEEP_REM_S}),
        "values": {Metric.SLEEP_REM_S: 93.0},
        "origins": {Metric.SLEEP_REM_S: "oura"},
        "revision": None,
        "ordinal": 7,
    }
    with pytest.raises(dataclasses.FrozenInstanceError):
        snapshot.ordinal = 9  # type: ignore[misc]
    value = SeriesValue(
        date(2024, 4, 3), Metric.WEIGHT_KG, "synthetic", None, 65.2, True
    )
    assert dataclasses.asdict(value) == {
        "day": date(2024, 4, 3),
        "metric": Metric.WEIGHT_KG,
        "source": "synthetic",
        "origin": None,
        "value": 65.2,
        "canonical": True,
    }
    with pytest.raises(dataclasses.FrozenInstanceError):
        value.value = 70.1  # type: ignore[misc]
    later = dataclasses.replace(value, day=date(2024, 4, 4))
    assert value < later
