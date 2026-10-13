"""intervals.icu wellness day records and delivery envelopes."""

from __future__ import annotations

import json
import re
from collections.abc import Iterator, Mapping
from datetime import UTC, date, datetime
from typing import BinaryIO, Final

from fitdocs.wellness.model import DaySnapshot, Metric, accept_value, is_origin
from fitdocs.wellness.probe import CandidateProbe
from fitdocs.wellness.spec import (
    ArchiveForm,
    FormatSpec,
    SourceKind,
    SourceSpec,
    Supersession,
    WellnessFormatError,
)

DELIVERY_FORMAT: Final[str] = "fitdocs.intervals-icu-wellness"
DELIVERY_VERSION: Final[int] = 1
FIELD_METRICS: Final[Mapping[str, Metric]] = {
    "restingHR": Metric.RESTING_HR_BPM,
    "hrv": Metric.HRV_RMSSD_MS,
    "hrvSDNN": Metric.HRV_SDNN_MS,
    "sleepSecs": Metric.SLEEP_S,
    "avgSleepingHR": Metric.SLEEP_HR_BPM,
    "respiration": Metric.RESPIRATION_BRPM,
    "spO2": Metric.SPO2_PCT,
    "steps": Metric.STEPS,
    "vo2max": Metric.VO2MAX_ML_PER_KG_MIN,
    "weight": Metric.WEIGHT_KG,
    "fatigue": Metric.FATIGUE_RATING,
    "mood": Metric.MOOD_RATING,
    "motivation": Metric.MOTIVATION_RATING,
    "soreness": Metric.SORENESS_RATING,
    "stress": Metric.STRESS_RATING,
    "injury": Metric.INJURY_RATING,
    "hydration": Metric.HYDRATION_RATING,
}
SOURCE: Final[SourceSpec] = SourceSpec(
    "intervals-icu", "intervals.icu", SourceKind.RELAY
)


def _date_id(value: object) -> bool:
    return (
        isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value) is not None
    )


def recognize(probe: CandidateProbe) -> bool:
    value = probe.json()
    if isinstance(value, dict):
        return (
            value.get("format") == DELIVERY_FORMAT
            and value.get("version") == DELIVERY_VERSION
        )
    return (
        isinstance(value, list)
        and bool(value)
        and all(
            isinstance(record, dict) and _date_id(record.get("id")) for record in value
        )
        and any(
            "updated" in record or FIELD_METRICS.keys() & record.keys()
            for record in value
        )
    )


def _revision(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        instant = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if instant.utcoffset() is None:
            return None
        return instant.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    except (ValueError, OverflowError):
        return None


def parse(stream: BinaryIO) -> Iterator[DaySnapshot]:
    try:
        payload = json.load(stream)
    except (ValueError, UnicodeError) as error:
        raise WellnessFormatError("invalid intervals JSON") from error
    origins: dict[str, str] = {}
    if isinstance(payload, dict):
        if (
            payload.get("format") != DELIVERY_FORMAT
            or payload.get("version") != DELIVERY_VERSION
        ):
            raise WellnessFormatError("invalid intervals delivery header")
        raw_origins = payload.get("origins", {})
        if not isinstance(raw_origins, dict):
            raise WellnessFormatError("invalid intervals origins")
        for field, token in raw_origins.items():
            if not isinstance(token, str) or not is_origin(token):
                raise WellnessFormatError("invalid intervals origin token")
            origins[field] = token
        records = payload.get("records")
    else:
        records = payload
    if not isinstance(records, list):
        raise WellnessFormatError("intervals records must be a list")
    seen: set[date] = set()
    for ordinal, record in enumerate(records):
        if not isinstance(record, dict) or not _date_id(record.get("id")):
            raise WellnessFormatError("invalid intervals date id")
        try:
            day = date.fromisoformat(record["id"])
        except ValueError as error:
            raise WellnessFormatError("invalid intervals date id") from error
        if day in seen:
            raise WellnessFormatError("duplicate intervals date id")
        seen.add(day)
        values: dict[Metric, float] = {}
        value_origins: dict[Metric, str] = {}
        for field, metric in FIELD_METRICS.items():
            raw = record.get(field)
            if raw is None:
                continue
            if isinstance(raw, bool) or not isinstance(raw, (int, float)):
                raise WellnessFormatError(f"invalid intervals number for {field}")
            try:
                accepted = accept_value(metric, raw)
            except OverflowError:
                accepted = None
            if accepted is not None:
                values[metric] = accepted
                if field in origins:
                    value_origins[metric] = origins[field]
        yield DaySnapshot(
            day,
            frozenset(FIELD_METRICS.values()),
            values,
            value_origins,
            _revision(record.get("updated")),
            ordinal,
        )


FORMAT: Final[FormatSpec] = FormatSpec(
    "intervals-icu",
    "intervals.icu",
    SOURCE,
    frozenset({".json"}),
    ArchiveForm.ORIGINAL,
    ".json",
    1,
    frozenset(FIELD_METRICS.values()),
    recognize,
    parse,
    supersession=Supersession.NONE,
    extract=None,
    entry_order=None,
)
