"""Synthetic Garmin JSON records for downstream integration tests."""

import json
from datetime import date
from typing import Literal


def _day(day: str | date) -> str:
    return day.isoformat() if isinstance(day, date) else day


def garmin_uds_record(day: str | date, **fields: object) -> dict[str, object]:
    return {"calendarDate": _day(day), "includesWellnessData": True, **fields}


def garmin_sleep_record(
    day: str | date,
    *,
    deep_s: object = None,
    light_s: object = None,
    rem_s: object = None,
    awake_s: object = None,
    respiration: object = None,
) -> dict[str, object]:
    return {
        "calendarDate": _day(day),
        "sleepStartTimestampGMT": "2000-01-01T22:00:00Z",
        "deepSleepSeconds": deep_s,
        "lightSleepSeconds": light_s,
        "remSleepSeconds": rem_s,
        "awakeSleepSeconds": awake_s,
        "averageRespiration": respiration,
    }


def garmin_maxmet_record(
    day: str | date,
    *,
    sport: object,
    vo2max: object,
    updated: object,
) -> dict[str, object]:
    record = {
        "calendarDate": _day(day),
        "vo2MaxValue": vo2max,
        "updateTimestamp": updated,
    }
    if sport is not None:
        record["sport"] = sport
    return record


def garmin_biometrics_record(
    day: str | date,
    *,
    weight_g: object,
    measured_at: object,
) -> dict[str, object]:
    return {
        "metaData": {"calendarDate": _day(day)},
        "weight": {"weight": weight_g, "timestampGMT": measured_at},
    }


def garmin_file_bytes(records: list[dict[str, object]]) -> bytes:
    return json.dumps(records, ensure_ascii=False).encode()


def garmin_file_name(
    kind: Literal["uds", "sleep", "maxmet", "biometrics"],
    first: str | date,
    last: str | date,
) -> str:
    names = {
        "uds": f"UDSFile_{_day(first)}_{_day(last)}.json",
        "sleep": f"{_day(first)}_{_day(last)}_1_sleepData.json",
        "maxmet": f"MetricsMaxMetData_{_day(first)}_{_day(last)}.json",
        "biometrics": f"{_day(first)}_{_day(last)}_1_userBioMetrics.json",
    }
    return names[kind]


def hydration_decoy_bytes() -> bytes:
    return garmin_file_bytes([{"calendarDate": "2000-01-02", "valueInML": 1234}])
