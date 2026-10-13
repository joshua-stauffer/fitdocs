"""The metric vocabulary, absent-value rule and local sleep-day boundary."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import StrEnum
from typing import Final


class Metric(StrEnum):
    """Canonical wellness measurements, with unit tokens in their names."""

    RESTING_HR_BPM = "resting_hr_bpm"
    MIN_HR_BPM = "min_hr_bpm"
    MAX_HR_BPM = "max_hr_bpm"
    HRV_SDNN_MS = "hrv_sdnn_ms"
    HRV_RMSSD_MS = "hrv_rmssd_ms"
    SLEEP_S = "sleep_s"
    SLEEP_DEEP_S = "sleep_deep_s"
    SLEEP_LIGHT_S = "sleep_light_s"
    SLEEP_REM_S = "sleep_rem_s"
    SLEEP_AWAKE_S = "sleep_awake_s"
    SLEEP_HR_BPM = "sleep_hr_bpm"
    RESPIRATION_BRPM = "respiration_brpm"
    SPO2_PCT = "spo2_pct"
    WEIGHT_KG = "weight_kg"
    VO2MAX_ML_PER_KG_MIN = "vo2max_ml_per_kg_min"
    VO2MAX_RUN_ML_PER_KG_MIN = "vo2max_run_ml_per_kg_min"
    VO2MAX_RIDE_ML_PER_KG_MIN = "vo2max_ride_ml_per_kg_min"
    STEPS = "steps"
    STRESS_LEVEL = "stress_level"
    BODY_BATTERY_HIGHEST = "body_battery_highest"
    BODY_BATTERY_LOWEST = "body_battery_lowest"
    FATIGUE_RATING = "fatigue_rating"
    MOOD_RATING = "mood_rating"
    MOTIVATION_RATING = "motivation_rating"
    SORENESS_RATING = "soreness_rating"
    STRESS_RATING = "stress_rating"
    INJURY_RATING = "injury_rating"
    HYDRATION_RATING = "hydration_rating"


@dataclass(frozen=True)
class MetricInfo:
    metric: Metric
    label: str
    unit: str | None
    minimum: float
    maximum: float
    description: str

    @property
    def zero_is_absent(self) -> bool:
        return self.minimum > 0


METRICS: Final[Mapping[Metric, MetricInfo]] = {
    Metric.RESTING_HR_BPM: MetricInfo(
        Metric.RESTING_HR_BPM,
        "Resting HR",
        "bpm",
        1,
        250,
        "The day's resting heart rate, as the source defines it",
    ),
    Metric.MIN_HR_BPM: MetricInfo(
        Metric.MIN_HR_BPM,
        "Lowest HR",
        "bpm",
        1,
        250,
        "Lowest heart rate recorded that day",
    ),
    Metric.MAX_HR_BPM: MetricInfo(
        Metric.MAX_HR_BPM,
        "Highest HR",
        "bpm",
        1,
        250,
        "Highest heart rate recorded that day, workouts included",
    ),
    Metric.HRV_SDNN_MS: MetricInfo(
        Metric.HRV_SDNN_MS,
        "HRV (SDNN)",
        "ms",
        1,
        1000,
        "Heart-rate variability as SDNN",
    ),
    Metric.HRV_RMSSD_MS: MetricInfo(
        Metric.HRV_RMSSD_MS,
        "HRV (rMSSD)",
        "ms",
        1,
        1000,
        "Heart-rate variability as rMSSD",
    ),
    Metric.SLEEP_S: MetricInfo(
        Metric.SLEEP_S,
        "Sleep",
        "s",
        1,
        86400,
        "Total sleep (excluding awake time) of the night ending on the day",
    ),
    Metric.SLEEP_DEEP_S: MetricInfo(
        Metric.SLEEP_DEEP_S, "Deep sleep", "s", 0, 86400, "Deep sleep of that night"
    ),
    Metric.SLEEP_LIGHT_S: MetricInfo(
        Metric.SLEEP_LIGHT_S, "Light sleep", "s", 0, 86400, "Light sleep of that night"
    ),
    Metric.SLEEP_REM_S: MetricInfo(
        Metric.SLEEP_REM_S, "REM sleep", "s", 0, 86400, "REM sleep of that night"
    ),
    Metric.SLEEP_AWAKE_S: MetricInfo(
        Metric.SLEEP_AWAKE_S,
        "Awake in sleep",
        "s",
        0,
        86400,
        "Awake time within that night's sleep",
    ),
    Metric.SLEEP_HR_BPM: MetricInfo(
        Metric.SLEEP_HR_BPM,
        "Sleeping HR",
        "bpm",
        1,
        250,
        "Average heart rate during that night's sleep",
    ),
    Metric.RESPIRATION_BRPM: MetricInfo(
        Metric.RESPIRATION_BRPM,
        "Respiration",
        "brpm",
        1,
        100,
        "Average respiration rate, as the source defines it",
    ),
    Metric.SPO2_PCT: MetricInfo(
        Metric.SPO2_PCT,
        "SpO2",
        "pct",
        1,
        100,
        "Average blood-oxygen saturation, as the source defines it",
    ),
    Metric.WEIGHT_KG: MetricInfo(
        Metric.WEIGHT_KG, "Weight", "kg", 1, 500, "Body weight"
    ),
    Metric.VO2MAX_ML_PER_KG_MIN: MetricInfo(
        Metric.VO2MAX_ML_PER_KG_MIN,
        "VO2max",
        "ml_per_kg_min",
        1,
        100,
        "VO2max estimate not tied to a sport by its source",
    ),
    Metric.VO2MAX_RUN_ML_PER_KG_MIN: MetricInfo(
        Metric.VO2MAX_RUN_ML_PER_KG_MIN,
        "VO2max (running)",
        "ml_per_kg_min",
        1,
        100,
        "Running VO2max estimate",
    ),
    Metric.VO2MAX_RIDE_ML_PER_KG_MIN: MetricInfo(
        Metric.VO2MAX_RIDE_ML_PER_KG_MIN,
        "VO2max (cycling)",
        "ml_per_kg_min",
        1,
        100,
        "Cycling VO2max estimate",
    ),
    Metric.STEPS: MetricInfo(Metric.STEPS, "Steps", None, 1, 1000000, "Steps that day"),
    Metric.STRESS_LEVEL: MetricInfo(
        Metric.STRESS_LEVEL,
        "Stress level",
        None,
        1,
        100,
        "Average all-day stress level (Garmin's 0–100 scale)",
    ),
    Metric.BODY_BATTERY_HIGHEST: MetricInfo(
        Metric.BODY_BATTERY_HIGHEST,
        "Body battery (highest)",
        None,
        1,
        100,
        "Highest body battery that day",
    ),
    Metric.BODY_BATTERY_LOWEST: MetricInfo(
        Metric.BODY_BATTERY_LOWEST,
        "Body battery (lowest)",
        None,
        1,
        100,
        "Lowest body battery that day",
    ),
    Metric.FATIGUE_RATING: MetricInfo(
        Metric.FATIGUE_RATING,
        "Fatigue (rating)",
        None,
        1,
        4,
        "The athlete's subjective rating, as recorded on the source's 1–4 scale",
    ),
    Metric.MOOD_RATING: MetricInfo(
        Metric.MOOD_RATING,
        "Mood (rating)",
        None,
        1,
        4,
        "The athlete's subjective rating, as recorded on the source's 1–4 scale",
    ),
    Metric.MOTIVATION_RATING: MetricInfo(
        Metric.MOTIVATION_RATING,
        "Motivation (rating)",
        None,
        1,
        4,
        "The athlete's subjective rating, as recorded on the source's 1–4 scale",
    ),
    Metric.SORENESS_RATING: MetricInfo(
        Metric.SORENESS_RATING,
        "Soreness (rating)",
        None,
        1,
        4,
        "The athlete's subjective rating, as recorded on the source's 1–4 scale",
    ),
    Metric.STRESS_RATING: MetricInfo(
        Metric.STRESS_RATING,
        "Stress (rating)",
        None,
        1,
        4,
        "The athlete's subjective rating, as recorded on the source's 1–4 scale",
    ),
    Metric.INJURY_RATING: MetricInfo(
        Metric.INJURY_RATING,
        "Injury (rating)",
        None,
        1,
        4,
        "The athlete's subjective rating, as recorded on the source's 1–4 scale",
    ),
    Metric.HYDRATION_RATING: MetricInfo(
        Metric.HYDRATION_RATING,
        "Hydration (rating)",
        None,
        1,
        4,
        "The athlete's subjective rating, as recorded on the source's 1–4 scale",
    ),
}


def accept_value(metric: Metric, value: float) -> float | None:
    """Keep finite values within the metric's inclusive recorded range."""
    info = METRICS[metric]
    if not math.isfinite(value):
        return None
    if not info.minimum <= value <= info.maximum:
        return None
    return float(value)


@dataclass(frozen=True)
class DaySnapshot:
    """One parsed record, before archive-level invariant validation."""

    day: date
    covers: frozenset[Metric]
    values: Mapping[Metric, float]
    origins: Mapping[Metric, str]
    revision: str | None
    ordinal: int


@dataclass(frozen=True, order=True)
class SeriesValue:
    """One source-attributed line of the daily series."""

    day: date
    metric: Metric
    source: str
    origin: str | None
    value: float
    canonical: bool


ORIGIN_PATTERN: Final[re.Pattern[str]] = re.compile(r"[a-z0-9]+(-[a-z0-9]+)*")


def is_origin(token: str) -> bool:
    """Whether a token follows the lowercase origin identifier grammar."""
    return ORIGIN_PATTERN.fullmatch(token) is not None


def wellness_day_of_sleep_end(end: datetime) -> date:
    """Assign an offset-aware sleep end to the day bounded by 18:00 local."""
    if end.utcoffset() is None:
        raise ValueError("sleep end must carry a recorded UTC offset")
    return (end + timedelta(hours=6)).date()
