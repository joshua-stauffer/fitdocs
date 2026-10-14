"""Verbatim Apple Health record texts and reader exchange items."""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Final


class AppleType(StrEnum):
    RESTING_HEART_RATE = "HKQuantityTypeIdentifierRestingHeartRate"
    HRV_SDNN = "HKQuantityTypeIdentifierHeartRateVariabilitySDNN"
    RESPIRATORY_RATE = "HKQuantityTypeIdentifierRespiratoryRate"
    OXYGEN_SATURATION = "HKQuantityTypeIdentifierOxygenSaturation"
    VO2_MAX = "HKQuantityTypeIdentifierVO2Max"
    STEP_COUNT = "HKQuantityTypeIdentifierStepCount"
    BODY_MASS = "HKQuantityTypeIdentifierBodyMass"
    SLEEP_ANALYSIS = "HKCategoryTypeIdentifierSleepAnalysis"


class SleepState(StrEnum):
    IN_BED = "HKCategoryValueSleepAnalysisInBed"
    ASLEEP_UNSPECIFIED = "HKCategoryValueSleepAnalysisAsleepUnspecified"
    ASLEEP = "HKCategoryValueSleepAnalysisAsleep"
    AWAKE = "HKCategoryValueSleepAnalysisAwake"
    CORE = "HKCategoryValueSleepAnalysisAsleepCore"
    DEEP = "HKCategoryValueSleepAnalysisAsleepDeep"
    REM = "HKCategoryValueSleepAnalysisAsleepREM"


RECORD_ATTRIBUTES: Final = (
    "type",
    "sourceName",
    "sourceVersion",
    "device",
    "unit",
    "creationDate",
    "startDate",
    "endDate",
    "value",
)


@dataclass(frozen=True)
class RawRecord:
    type: str
    source_name: str | None
    source_version: str | None
    device: str | None
    unit: str | None
    creation_date: str | None
    start_date: str | None
    end_date: str | None
    value: str | None
    metadata: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class ExportDate:
    text: str


@dataclass(frozen=True)
class Corrections:
    doctype_removed: int
    control_characters_removed: int
    duplicate_attributes_removed: int


ExportItem = ExportDate | RawRecord | Corrections


def normalize_device(text: str) -> str:
    match = re.fullmatch(r"(?s)<<HKDevice: 0x[0-9a-fA-F]+>, (.*)>", text)
    return match.group(1) if match else text
