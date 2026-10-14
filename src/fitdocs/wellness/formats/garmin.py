"""Garmin export wellness records, recognized by structure or empty-file name."""

from __future__ import annotations

import json
import re
from collections.abc import Iterator, Mapping
from datetime import UTC, date, datetime
from functools import partial
from typing import BinaryIO, Final

from fitdocs.wellness.model import DaySnapshot, Metric, accept_value
from fitdocs.wellness.probe import CandidateProbe
from fitdocs.wellness.spec import (
    ArchiveForm,
    FormatSpec,
    SourceKind,
    SourceSpec,
    Supersession,
    WellnessFormatError,
)

SOURCE: Final[SourceSpec] = SourceSpec(
    "garmin-export", "Garmin export", SourceKind.DEVICE
)
_UDS_FIELDS: Final[Mapping[str, Metric]] = {
    "currentDayRestingHeartRate": Metric.RESTING_HR_BPM,
    "minHeartRate": Metric.MIN_HR_BPM,
    "maxHeartRate": Metric.MAX_HR_BPM,
    "totalSteps": Metric.STEPS,
    "averageSpo2Value": Metric.SPO2_PCT,
}
_STAGE_FIELDS: Final[Mapping[str, Metric]] = {
    "deepSleepSeconds": Metric.SLEEP_DEEP_S,
    "lightSleepSeconds": Metric.SLEEP_LIGHT_S,
    "remSleepSeconds": Metric.SLEEP_REM_S,
}
_UDS_METRICS = frozenset(_UDS_FIELDS.values()) | {
    Metric.STRESS_LEVEL,
    Metric.BODY_BATTERY_HIGHEST,
    Metric.BODY_BATTERY_LOWEST,
}
_SLEEP_METRICS = frozenset(_STAGE_FIELDS.values()) | {
    Metric.SLEEP_S,
    Metric.SLEEP_AWAKE_S,
    Metric.RESPIRATION_BRPM,
}
_SPORTS: Final[Mapping[str, Metric]] = {
    "RUNNING": Metric.VO2MAX_RUN_ML_PER_KG_MIN,
    "CYCLING": Metric.VO2MAX_RIDE_ML_PER_KG_MIN,
}
_SIGNATURES = {
    "uds": "includesWellnessData",
    "sleep": "sleepStartTimestampGMT",
    "maxmet": "vo2MaxValue",
    "biometrics": "metaData",
}
_NAMES = {
    "uds": r"UDSFile_.*\.json",
    "sleep": r".*_sleepData\.json",
    "maxmet": r"MetricsMaxMetData_.*\.json",
    "biometrics": r".*_userBioMetrics\.json",
}


def _date_value(record: dict[str, object], kind: str) -> object:
    if kind == "biometrics":
        metadata = record.get("metaData")
        return metadata.get("calendarDate") if isinstance(metadata, dict) else None
    return record.get("calendarDate")


def _recognize(kind: str, probe: CandidateProbe) -> bool:
    payload = probe.json()
    if not isinstance(payload, list):
        return False
    if not payload:
        return re.fullmatch(_NAMES[kind], probe.name, re.IGNORECASE) is not None
    return all(
        isinstance(record, dict)
        and (
            isinstance(record.get("metaData"), dict)
            and "calendarDate" in record["metaData"]
            if kind == "biometrics"
            else "calendarDate" in record
        )
        for record in payload
    ) and any(_SIGNATURES[kind] in record for record in payload)


def _day(record: dict[str, object], kind: str) -> date:
    raw = _date_value(record, kind)
    if not isinstance(raw, str) or re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw) is None:
        raise WellnessFormatError("invalid Garmin calendar date")
    try:
        return date.fromisoformat(raw)
    except ValueError as error:
        raise WellnessFormatError("invalid Garmin calendar date") from error


def _number(raw: object) -> int | float | None:
    if raw is None:
        return None
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        raise WellnessFormatError("invalid Garmin measurement number")
    return raw


def _put(values: dict[Metric, float], metric: Metric, raw: object) -> None:
    number = _number(raw)
    if number is None:
        return
    try:
        accepted = accept_value(metric, number)
    except OverflowError:
        accepted = None
    if accepted is not None:
        values[metric] = accepted


def _object(raw: object) -> dict[str, object]:
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise WellnessFormatError("invalid Garmin measurement object")
    return raw


def _entries(raw: object) -> list[dict[str, object]]:
    if raw is None:
        return []
    if not isinstance(raw, list) or any(not isinstance(item, dict) for item in raw):
        raise WellnessFormatError("invalid Garmin measurement entries")
    return raw


def _revision(raw: object) -> str | None:
    """Normalize opaque revision keys; naive times retain their wall-clock order."""
    if not isinstance(raw, str):
        return None
    try:
        instant = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if instant.utcoffset() is None:
            return instant.isoformat(timespec="microseconds")
        return instant.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    except (ValueError, OverflowError):
        return None


def _uds(record: dict[str, object]) -> dict[Metric, float]:
    values: dict[Metric, float] = {}
    for field, metric in _UDS_FIELDS.items():
        _put(values, metric, record.get(field))
    stress = _object(record.get("allDayStress"))
    for entry in _entries(stress.get("aggregatorList")):
        if entry.get("type") == "TOTAL":
            _put(values, Metric.STRESS_LEVEL, entry.get("averageStressLevel"))
    battery = _object(record.get("bodyBattery"))
    for entry in _entries(battery.get("bodyBatteryStatList")):
        if entry.get("bodyBatteryStatType") == "HIGHEST":
            _put(values, Metric.BODY_BATTERY_HIGHEST, entry.get("statsValue"))
        elif entry.get("bodyBatteryStatType") == "LOWEST":
            _put(values, Metric.BODY_BATTERY_LOWEST, entry.get("statsValue"))
    return values


def _sleep(record: dict[str, object]) -> dict[Metric, float]:
    values: dict[Metric, float] = {}
    stages = {field: _number(record.get(field)) for field in _STAGE_FIELDS}
    awake = _number(record.get("awakeSleepSeconds"))
    try:
        total = sum(value for value in stages.values() if value is not None)
        positive = total > 0
    except OverflowError:
        total = float("inf")
        positive = True
    if positive:
        _put(values, Metric.SLEEP_S, total)
        for field, metric in _STAGE_FIELDS.items():
            _put(values, metric, stages[field])
        _put(values, Metric.SLEEP_AWAKE_S, awake)
    _put(values, Metric.RESPIRATION_BRPM, record.get("averageRespiration"))
    return values


def _parse(kind: str, stream: BinaryIO) -> Iterator[DaySnapshot]:
    try:
        payload = json.load(stream)
    except (ValueError, UnicodeError) as error:
        raise WellnessFormatError("invalid Garmin JSON") from error
    if not isinstance(payload, list):
        raise WellnessFormatError("Garmin records must be a list")
    for ordinal, record in enumerate(payload):
        if not isinstance(record, dict):
            raise WellnessFormatError("invalid Garmin record")
        day = _day(record, kind)
        revision = None
        if kind == "uds":
            covers = _UDS_METRICS
            values = _uds(record)
        elif kind == "sleep":
            covers = _SLEEP_METRICS
            values = _sleep(record)
        elif kind == "maxmet":
            sport = record.get("sport")
            metric = _SPORTS.get(sport) if isinstance(sport, str) else None
            if metric is None:
                continue
            covers = frozenset({metric})
            values = {}
            _put(values, metric, record.get("vo2MaxValue"))
            revision = _revision(record.get("updateTimestamp"))
        else:
            covers = frozenset({Metric.WEIGHT_KG})
            values = {}
            weight = _object(record.get("weight"))
            number = _number(weight.get("weight"))
            if number is not None:
                try:
                    kilograms = number / 1000
                except OverflowError:
                    kilograms = float("inf")
                _put(values, Metric.WEIGHT_KG, kilograms)
            revision = _revision(weight.get("timestampGMT"))
        yield DaySnapshot(
            day,
            covers,
            values,
            {metric: "garmin" for metric in values},
            revision,
            ordinal,
        )


def _format(kind: str, label: str, metrics: frozenset[Metric]) -> FormatSpec:
    return FormatSpec(
        f"garmin-{kind}",
        label,
        SOURCE,
        frozenset({".json"}),
        ArchiveForm.ORIGINAL,
        ".json",
        1,
        metrics,
        partial(_recognize, kind),
        partial(_parse, kind),
        supersession=Supersession.NONE,
        extract=None,
        entry_order=None,
    )


UDS_FORMAT: Final[FormatSpec] = _format("uds", "Garmin daily summaries", _UDS_METRICS)
SLEEP_FORMAT: Final[FormatSpec] = _format("sleep", "Garmin sleep", _SLEEP_METRICS)
MAXMET_FORMAT: Final[FormatSpec] = _format(
    "maxmet", "Garmin VO2max", frozenset(_SPORTS.values())
)
BIOMETRICS_FORMAT: Final[FormatSpec] = _format(
    "biometrics", "Garmin body metrics", frozenset({Metric.WEIGHT_KG})
)
