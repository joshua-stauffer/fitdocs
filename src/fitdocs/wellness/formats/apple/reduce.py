"""Writer classification and Apple Health daily value reduction."""

from __future__ import annotations

import math
from bisect import bisect_right
from collections.abc import Collection, Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from fractions import Fraction
from typing import Final

from fitdocs.wellness.formats.apple.records import AppleType, RawRecord, SleepState
from fitdocs.wellness.formats.apple.sleep import (
    Segment,
    Stage,
    asleep_intervals,
    night_totals,
)
from fitdocs.wellness.model import (
    DaySnapshot,
    Metric,
    accept_value,
    wellness_day_of_sleep_end,
)
from fitdocs.wellness.spec import WellnessFormatError


class Writer(StrEnum):
    WATCH = "watch"
    PHONE = "iphone"
    OTHER = "other"


class DayRule(StrEnum):
    WAKE_DATE = "wake-date"
    NIGHT_OF_READING = "night-of-reading"
    START_DATE = "start-date"


class DailyRule(StrEnum):
    SLEEP_NIGHT = "sleep-night"
    ASLEEP_MEAN = "asleep-mean"
    FINAL = "final"
    LARGEST_TOTAL = "largest-total"
    LATEST = "latest"


@dataclass(frozen=True)
class TypePolicy:
    apple_type: AppleType
    metrics: tuple[Metric, ...]
    writers: frozenset[Writer]
    units: Mapping[str, float]
    day_rule: DayRule
    daily_rule: DailyRule


POLICIES: Final[Mapping[AppleType, TypePolicy]] = {
    AppleType.SLEEP_ANALYSIS: TypePolicy(
        AppleType.SLEEP_ANALYSIS,
        (
            Metric.SLEEP_S,
            Metric.SLEEP_DEEP_S,
            Metric.SLEEP_LIGHT_S,
            Metric.SLEEP_REM_S,
            Metric.SLEEP_AWAKE_S,
        ),
        frozenset({Writer.WATCH, Writer.PHONE}),
        {},
        DayRule.WAKE_DATE,
        DailyRule.SLEEP_NIGHT,
    ),
    AppleType.HRV_SDNN: TypePolicy(
        AppleType.HRV_SDNN,
        (Metric.HRV_SDNN_MS,),
        frozenset({Writer.WATCH}),
        {"ms": 1},
        DayRule.NIGHT_OF_READING,
        DailyRule.ASLEEP_MEAN,
    ),
    AppleType.RESPIRATORY_RATE: TypePolicy(
        AppleType.RESPIRATORY_RATE,
        (Metric.RESPIRATION_BRPM,),
        frozenset({Writer.WATCH}),
        {"count/min": 1},
        DayRule.NIGHT_OF_READING,
        DailyRule.ASLEEP_MEAN,
    ),
    AppleType.OXYGEN_SATURATION: TypePolicy(
        AppleType.OXYGEN_SATURATION,
        (Metric.SPO2_PCT,),
        frozenset({Writer.WATCH}),
        {"%": 100},
        DayRule.NIGHT_OF_READING,
        DailyRule.ASLEEP_MEAN,
    ),
    AppleType.RESTING_HEART_RATE: TypePolicy(
        AppleType.RESTING_HEART_RATE,
        (Metric.RESTING_HR_BPM,),
        frozenset({Writer.WATCH}),
        {"count/min": 1},
        DayRule.START_DATE,
        DailyRule.FINAL,
    ),
    AppleType.VO2_MAX: TypePolicy(
        AppleType.VO2_MAX,
        (Metric.VO2MAX_ML_PER_KG_MIN,),
        frozenset({Writer.WATCH}),
        {
            "mL/min·kg": 1,
            "mL/kg·min": 1,
            "mL/(kg·min)": 1,
            "mL/kg/min": 1,
            "ml/(kg*min)": 1,
        },
        DayRule.START_DATE,
        DailyRule.FINAL,
    ),
    AppleType.STEP_COUNT: TypePolicy(
        AppleType.STEP_COUNT,
        (Metric.STEPS,),
        frozenset({Writer.WATCH, Writer.PHONE}),
        {"count": 1},
        DayRule.START_DATE,
        DailyRule.LARGEST_TOTAL,
    ),
    AppleType.BODY_MASS: TypePolicy(
        AppleType.BODY_MASS,
        (Metric.WEIGHT_KG,),
        frozenset(Writer),
        {"kg": 1, "lb": 0.45359237, "g": 0.001, "st": 6.35029318},
        DayRule.START_DATE,
        DailyRule.LATEST,
    ),
}
APPLE_ORIGIN: Final[str] = "apple"
_STAGES: Final[Mapping[SleepState, Stage | None]] = {
    SleepState.IN_BED: None,
    SleepState.ASLEEP_UNSPECIFIED: Stage.UNSPECIFIED,
    SleepState.ASLEEP: Stage.UNSPECIFIED,
    SleepState.AWAKE: Stage.AWAKE,
    SleepState.CORE: Stage.CORE,
    SleepState.DEEP: Stage.DEEP,
    SleepState.REM: Stage.REM,
}
_COVERS = frozenset(metric for policy in POLICIES.values() for metric in policy.metrics)


def device_maker_model(device: str) -> tuple[str, str] | None:
    fields = {}
    for field in device.split(","):
        key, separator, value = field.partition(":")
        if separator:
            fields[key.strip()] = value.strip()
    maker, model = fields.get("manufacturer"), fields.get("model")
    if maker is None or model is None:
        return None
    return maker, model


def writer_of(evidence: Collection[tuple[str, str]]) -> Writer:
    if ("Apple Inc.", "Watch") in evidence:
        return Writer.WATCH
    if ("Apple Inc.", "iPhone") in evidence:
        return Writer.PHONE
    return Writer.OTHER


@dataclass(frozen=True)
class _Sample:
    start: datetime
    end: datetime
    creation: datetime | None
    value: float | int

    def key(
        self, rule: DailyRule
    ) -> tuple[datetime, tuple[datetime, ...], float | int]:
        instant = self.start if rule == DailyRule.LATEST else self.end
        return (
            instant,
            (self.creation,) if self.creation is not None else (),
            self.value,
        )


def _error(record: RawRecord, problem: str) -> WellnessFormatError:
    return WellnessFormatError(
        f"{record.type}: {problem}; startDate={record.start_date!r}"
    )


def _timestamp(record: RawRecord, text: str, field: str) -> datetime:
    try:
        result = datetime.fromisoformat(text)
    except ValueError as exc:
        raise _error(record, f"invalid {field}: {text!r}") from exc
    if result.utcoffset() is None:
        raise _error(record, f"{field} lacks UTC offset: {text!r}")
    return result


def _step_total(integral: int, remainder: list[float]) -> int | float:
    if not remainder:
        return integral
    try:
        return integral + math.fsum(remainder)
    except OverflowError:
        exact = Fraction(integral) + sum(
            (Fraction(value) for value in remainder), Fraction()
        )
        try:
            return float(exact)
        except OverflowError:
            return math.inf if exact > 0 else -math.inf


class DayReducer:
    def __init__(self) -> None:
        self._evidence: dict[str, set[tuple[str, str]]] = {}
        self._best: dict[tuple[AppleType, str, date], _Sample] = {}
        self._steps: dict[tuple[str, date], tuple[int, list[float]]] = {}
        self._sleep: dict[tuple[str, date], list[Segment]] = {}
        self._readings: dict[
            tuple[AppleType, str], list[tuple[float, float | int | Fraction]]
        ] = {}

    def add(self, record: RawRecord) -> None:
        if record.type not in POLICIES:
            return
        kind = AppleType(record.type)
        policy = POLICIES[kind]
        for field, text in (
            ("sourceName", record.source_name),
            ("startDate", record.start_date),
            ("endDate", record.end_date),
            ("value", record.value),
        ):
            if text is None or text == "":
                raise _error(record, f"missing {field}")
        assert record.source_name is not None
        assert record.start_date is not None
        assert record.end_date is not None
        assert record.value is not None
        start = _timestamp(record, record.start_date, "startDate")
        end = _timestamp(record, record.end_date, "endDate")
        creation = (
            _timestamp(record, record.creation_date, "creationDate")
            if record.creation_date is not None
            else None
        )
        if end < start:
            raise _error(record, "endDate before startDate")
        if kind == AppleType.SLEEP_ANALYSIS:
            try:
                state = SleepState(record.value)
            except ValueError as exc:
                raise _error(record, f"unknown sleep state {record.value!r}") from exc
            value: float | int = 0
        else:
            try:
                quantity = float(record.value)
            except ValueError as exc:
                raise _error(record, f"non-numeric value {record.value!r}") from exc
            if not math.isfinite(quantity):
                raise _error(record, f"non-finite value {record.value!r}")
            if record.unit is None or record.unit not in policy.units:
                raise _error(record, f"unknown unit {record.unit!r}")
            value = quantity * policy.units[record.unit]
            if (
                kind == AppleType.STEP_COUNT
                and Decimal(record.value) == Decimal(record.value).to_integral_value()
            ):
                value = int(Decimal(record.value))
        evidence = self._evidence.setdefault(record.source_name, set())
        if record.device is not None:
            device = device_maker_model(record.device)
            if device is not None:
                evidence.add(device)
        if policy.daily_rule == DailyRule.SLEEP_NIGHT:
            stage = _STAGES[state]
            if stage is not None:
                day = wellness_day_of_sleep_end(end)
                segment = Segment(int(start.timestamp()), int(end.timestamp()), stage)
                self._sleep.setdefault((record.source_name, day), []).append(segment)
        elif policy.daily_rule == DailyRule.ASLEEP_MEAN:
            reading: float | int | Fraction = value
            if not math.isfinite(value):
                reading = Fraction(quantity) * Fraction(policy.units[record.unit or ""])
            self._readings.setdefault((kind, record.source_name), []).append(
                (end.timestamp(), reading)
            )
        if policy.day_rule != DayRule.START_DATE:
            return
        day = start.date()
        if policy.daily_rule == DailyRule.LARGEST_TOTAL:
            key = record.source_name, day
            integral, remainder = self._steps.setdefault(key, (0, []))
            if isinstance(value, int):
                integral += value
            else:
                remainder.append(value)
            self._steps[key] = integral, remainder
        else:
            best_key = kind, record.source_name, day
            sample = _Sample(start, end, creation, value)
            previous = self._best.get(best_key)
            if previous is None or sample.key(policy.daily_rule) > previous.key(
                policy.daily_rule
            ):
                self._best[best_key] = sample

    def _night_values(
        self, writers: Mapping[str, Writer]
    ) -> dict[tuple[date, Metric], float | int]:
        nights: dict[date, dict[Writer, list[Segment]]] = {}
        policy = POLICIES[AppleType.SLEEP_ANALYSIS]
        for (source, day), segments in self._sleep.items():
            writer = writers[source]
            if writer in policy.writers:
                nights.setdefault(day, {}).setdefault(writer, []).extend(segments)
        raw: dict[tuple[date, Metric], float | int] = {}
        watch_intervals: dict[date, tuple[tuple[int, int], ...]] = {}
        for day, kinds in sorted(nights.items()):
            watch = kinds.get(Writer.WATCH, [])
            phone = kinds.get(Writer.PHONE, [])
            if any(segment.stage != Stage.AWAKE for segment in watch):
                selected = watch
            elif any(segment.stage != Stage.AWAKE for segment in phone):
                selected = phone
            else:
                continue
            totals = night_totals(selected)
            if totals.asleep > 0:
                raw[day, Metric.SLEEP_S] = totals.asleep
            if totals.staged:
                raw[day, Metric.SLEEP_DEEP_S] = totals.deep
                raw[day, Metric.SLEEP_LIGHT_S] = totals.core
                raw[day, Metric.SLEEP_REM_S] = totals.rem
                raw[day, Metric.SLEEP_AWAKE_S] = totals.awake
            watch_intervals[day] = asleep_intervals(watch)
        means: dict[tuple[date, Metric], list[float | int | Fraction]] = {}
        for (kind, source), readings in self._readings.items():
            policy = POLICIES[kind]
            if writers[source] not in policy.writers:
                continue
            for instant, value in readings:
                for day, intervals in watch_intervals.items():
                    index = bisect_right(intervals, (instant, math.inf)) - 1
                    if index >= 0 and instant < intervals[index][1]:
                        means.setdefault((day, policy.metrics[0]), []).append(value)
                        break
        for key, samples in means.items():
            try:
                raw[key] = round(math.fsum(samples) / len(samples), 1)
            except OverflowError:
                exact_mean = sum(
                    (Fraction(value) for value in samples), Fraction()
                ) / len(samples)
                try:
                    raw[key] = round(float(exact_mean), 1)
                except OverflowError:
                    raw[key] = math.inf if exact_mean > 0 else -math.inf
        return raw

    def snapshots(self) -> tuple[DaySnapshot, ...]:
        writers = {
            name: writer_of(evidence) for name, evidence in self._evidence.items()
        }
        chosen: dict[
            tuple[date, Metric], tuple[datetime, tuple[datetime, ...], float | int]
        ] = {}
        totals: dict[date, tuple[float | int, str]] = {}
        for (kind, source, day), sample in self._best.items():
            policy = POLICIES[kind]
            if writers[source] not in policy.writers:
                continue
            key = day, policy.metrics[0]
            sample_key = sample.key(policy.daily_rule)
            if key not in chosen or sample_key > chosen[key]:
                chosen[key] = sample_key
        for (source, day), (integral, remainder) in self._steps.items():
            if writers[source] not in POLICIES[AppleType.STEP_COUNT].writers:
                continue
            total = _step_total(integral, remainder)
            candidate = total, source
            if day not in totals or candidate > totals[day]:
                totals[day] = candidate
        raw = {key: sample_key[-1] for key, sample_key in chosen.items()}
        raw.update({(day, Metric.STEPS): total for day, (total, _) in totals.items()})
        raw.update(self._night_values(writers))
        days: dict[date, dict[Metric, float]] = {}
        for (day, metric), value in raw.items():
            if metric == Metric.WEIGHT_KG:
                value = round(value, 2)
            try:
                accepted = accept_value(metric, value)
            except OverflowError:
                accepted = accept_value(metric, math.inf)
            if accepted is not None:
                days.setdefault(day, {})[metric] = accepted
        return tuple(
            DaySnapshot(
                day,
                _COVERS,
                values,
                {
                    metric: APPLE_ORIGIN
                    for metric in values
                    if metric != Metric.WEIGHT_KG
                },
                None,
                ordinal,
            )
            for ordinal, (day, values) in enumerate(sorted(days.items()))
        )


def reduce_records(records: Iterable[RawRecord]) -> tuple[DaySnapshot, ...]:
    reducer = DayReducer()
    for record in records:
        reducer.add(record)
    return reducer.snapshots()
