"""Synthetic Garmin format contracts."""

import io
import json
from datetime import date
from pathlib import Path
from typing import Literal

import pytest

from fitdocs.wellness.formats import garmin
from fitdocs.wellness.model import DaySnapshot, Metric
from fitdocs.wellness.probe import CandidateProbe
from fitdocs.wellness.spec import FormatSpec, WellnessFormatError
from tests.wellness.builders_garmin import (
    garmin_biometrics_record,
    garmin_file_bytes,
    garmin_file_name,
    garmin_maxmet_record,
    garmin_sleep_record,
    garmin_uds_record,
    hydration_decoy_bytes,
)

KINDS: tuple[Literal["uds", "sleep", "maxmet", "biometrics"], ...] = (
    "uds",
    "sleep",
    "maxmet",
    "biometrics",
)
DAY = "2000-01-02"
UDS = {
    "resting_hr_bpm": 51,
    "min_hr_bpm": 43,
    "max_hr_bpm": 189,
    "steps": 7654,
    "stress_level": 37,
    "spo2_pct": 97,
    "body_battery_highest": 88,
    "body_battery_lowest": 19,
}
SLEEP = {
    "sleep_s": 20006,
    "sleep_deep_s": 2001,
    "sleep_light_s": 13002,
    "sleep_rem_s": 5003,
    "sleep_awake_s": 604,
    "respiration_brpm": 15,
}
METRICS = {
    "uds": frozenset(UDS),
    "sleep": frozenset(SLEEP),
    "maxmet": frozenset({"vo2max_run_ml_per_kg_min", "vo2max_ride_ml_per_kg_min"}),
    "biometrics": frozenset({"weight_kg"}),
}


def form(kind: str) -> FormatSpec:
    return {
        "uds": garmin.UDS_FORMAT,
        "sleep": garmin.SLEEP_FORMAT,
        "maxmet": garmin.MAXMET_FORMAT,
        "biometrics": garmin.BIOMETRICS_FORMAT,
    }[kind]


def record(kind: str) -> dict[str, object]:
    if kind == "uds":
        return garmin_uds_record(
            DAY,
            currentDayRestingHeartRate=51,
            restingHeartRate=62,
            minHeartRate=43,
            maxHeartRate=189,
            totalSteps=7654,
            averageSpo2Value=97,
            allDayStress={
                "aggregatorList": [
                    {"type": "AWAKE", "averageStressLevel": 28},
                    {"type": "TOTAL", "averageStressLevel": 37},
                    {"type": "ASLEEP", "averageStressLevel": 16},
                ]
            },
            bodyBattery={
                "bodyBatteryStatList": [
                    {"bodyBatteryStatType": "MOSTRECENT", "statsValue": 71},
                    {"bodyBatteryStatType": "LOWEST", "statsValue": 19},
                    {"bodyBatteryStatType": "HIGHEST", "statsValue": 88},
                ]
            },
            trainingReadiness=99,
            respiration={"avgWakingRespirationValue": 18},
        )
    if kind == "sleep":
        return garmin_sleep_record(
            DAY, deep_s=2001, light_s=13002, rem_s=5003, awake_s=604, respiration=15
        )
    if kind == "maxmet":
        return garmin_maxmet_record(
            DAY, sport="RUNNING", vo2max=53, updated="2000-01-03T01:30:02.123+02:00"
        )
    return garmin_biometrics_record(
        DAY, weight_g=81234, measured_at="2000-01-03T01:30:02.123+02:00"
    )


def parsed(kind: str, records: list[dict[str, object]]) -> tuple[DaySnapshot, ...]:
    return tuple(form(kind).parse(io.BytesIO(garmin_file_bytes(records))))


@pytest.mark.parametrize("kind", KINDS)
def test_declarations(kind: str) -> None:
    spec = form(kind)
    assert (garmin.SOURCE.id, garmin.SOURCE.display_name, garmin.SOURCE.kind.value) == (
        "garmin-export",
        "Garmin export",
        "device",
    )
    assert (
        spec.id,
        spec.source,
        spec.suffixes,
        spec.archive_form.value,
        spec.archived_suffix,
        spec.rules_version,
        spec.supersession.value,
        spec.extract,
        spec.entry_order,
    ) == (
        f"garmin-{kind}",
        garmin.SOURCE,
        frozenset({".json"}),
        "original",
        ".json",
        1,
        "none",
        None,
        None,
    )
    assert {metric.value for metric in spec.metrics} == METRICS[kind]


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize(
    "mode",
    [
        "content",
        "empty",
        "empty_upper",
        "unrelated",
        "decoy",
        "wrong_kind",
        "mixed",
        "missing_date",
        "object",
        "scalar",
        "date_only",
    ],
)
def test_recognition(
    tmp_path: Path, kind: Literal["uds", "sleep", "maxmet", "biometrics"], mode: str
) -> None:
    name = "synthetic.json"
    payload = garmin_file_bytes([record(kind)])
    expected = mode in {"content", "empty", "empty_upper"}
    if mode in {"empty", "empty_upper"}:
        name = garmin_file_name(kind, DAY, "2000-04-10")
        if mode == "empty_upper":
            name = name.upper()
        payload = b"[]"
    elif mode == "unrelated":
        payload = b"[]"
    elif mode == "decoy":
        payload = hydration_decoy_bytes()
    elif mode == "wrong_kind":
        payload = garmin_file_bytes([record(KINDS[(KINDS.index(kind) + 1) % 4])])
    elif mode == "mixed":
        payload = json.dumps([record(kind), 1]).encode()
    elif mode == "missing_date":
        payload = json.dumps([record(kind), {}]).encode()
    elif mode == "object":
        payload = json.dumps(record(kind)).encode()
    elif mode == "scalar":
        payload = b"1"
    elif mode == "date_only":
        payload = b'[{"calendarDate":"2000-01-02"}]'
    path = tmp_path / name
    path.write_bytes(payload)
    assert form(kind).recognize(CandidateProbe.open(path)) is expected


@pytest.mark.parametrize("kind", KINDS)
def test_signature_can_be_in_later_record(tmp_path: Path, kind: str) -> None:
    first: dict[str, object] = (
        {"calendarDate": DAY}
        if kind != "biometrics"
        else {"metaData": {"calendarDate": DAY}}
    )
    path = tmp_path / "synthetic.json"
    path.write_bytes(garmin_file_bytes([first, record(kind)]))
    assert form(kind).recognize(CandidateProbe.open(path)) is True


@pytest.mark.parametrize("metric", UDS)
def test_uds_mapping(metric: str) -> None:
    assert parsed("uds", [record("uds")])[0].values[Metric(metric)] == UDS[metric]


@pytest.mark.parametrize("metric", SLEEP)
def test_sleep_mapping(metric: str) -> None:
    assert parsed("sleep", [record("sleep")])[0].values[Metric(metric)] == SLEEP[metric]


@pytest.mark.parametrize("kind", KINDS)
def test_snapshot(kind: str) -> None:
    first, second = parsed(kind, [record(kind), record(kind)])
    assert (first.day, second.day) == (date(2000, 1, 2), date(2000, 1, 2))
    assert (first.ordinal, second.ordinal) == (0, 1)
    expected_covers = (
        METRICS[kind] if kind != "maxmet" else {"vo2max_run_ml_per_kg_min"}
    )
    assert {metric.value for metric in first.covers} == expected_covers
    expected_values = (
        UDS
        if kind == "uds"
        else SLEEP
        if kind == "sleep"
        else {"vo2max_run_ml_per_kg_min": 53}
        if kind == "maxmet"
        else {"weight_kg": 81.234}
    )
    assert {
        metric.value: value for metric, value in first.values.items()
    } == expected_values
    assert first.origins == {Metric(metric): "garmin" for metric in expected_values}
    assert first.revision == (
        "2000-01-02T23:30:02.123000Z" if kind in {"maxmet", "biometrics"} else None
    )


@pytest.mark.parametrize("stress", [-2, -1, 0, None])
def test_stress_absent(stress: object) -> None:
    snapshot = parsed(
        "uds",
        [
            garmin_uds_record(
                DAY,
                allDayStress={
                    "aggregatorList": [{"type": "TOTAL", "averageStressLevel": stress}]
                },
            )
        ],
    )[0]
    assert snapshot.values == {}


@pytest.mark.parametrize(
    "field",
    ["currentDayRestingHeartRate", "minHeartRate", "maxHeartRate", "totalSteps"],
)
def test_uds_zero_absent(field: str) -> None:
    assert parsed("uds", [garmin_uds_record(DAY, **{field: 0})])[0].values == {}


@pytest.mark.parametrize("stages", [(None, None, None), (0, 0, 0)])
def test_no_sleep(stages: tuple[object, object, object]) -> None:
    snapshot = parsed(
        "sleep",
        [
            garmin_sleep_record(
                DAY,
                deep_s=stages[0],
                light_s=stages[1],
                rem_s=stages[2],
                awake_s=123,
                respiration=17,
            )
        ],
    )[0]
    assert snapshot.values == {Metric.RESPIRATION_BRPM: 17}


def test_partial_sleep() -> None:
    assert parsed(
        "sleep", [garmin_sleep_record(DAY, light_s=12003, deep_s=0, awake_s=0)]
    )[0].values == {
        Metric.SLEEP_S: 12003,
        Metric.SLEEP_LIGHT_S: 12003,
        Metric.SLEEP_DEEP_S: 0,
        Metric.SLEEP_AWAKE_S: 0,
    }


@pytest.mark.parametrize(
    "sport,expected",
    [
        ("RUNNING", {Metric.VO2MAX_RUN_ML_PER_KG_MIN: 53}),
        ("CYCLING", {Metric.VO2MAX_RIDE_ML_PER_KG_MIN: 53}),
        ("WALKING", {}),
        (None, {}),
    ],
)
def test_sports(sport: object, expected: dict[Metric, float]) -> None:
    snapshots = parsed(
        "maxmet", [garmin_maxmet_record(DAY, sport=sport, vo2max=53, updated=None)]
    )
    assert [dict(snapshot.values) for snapshot in snapshots] == (
        [expected] if expected else []
    )


@pytest.mark.parametrize("kind", ["maxmet", "biometrics"])
@pytest.mark.parametrize(
    "updated,expected",
    [
        (None, None),
        ("bad", None),
        (1, None),
        ("2000-01-02T10:20:30.4", "2000-01-02T10:20:30.400000"),
        ("2000-01-02T10:20:30Z", "2000-01-02T10:20:30.000000Z"),
    ],
)
def test_revisions(kind: str, updated: object, expected: str | None) -> None:
    item = (
        garmin_maxmet_record(DAY, sport="RUNNING", vo2max=53, updated=updated)
        if kind == "maxmet"
        else garmin_biometrics_record(DAY, weight_g=81234, measured_at=updated)
    )
    assert parsed(kind, [item])[0].revision == expected


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("bad_day", [None, "20000102", "2000-02-30", 1, "bad"])
def test_bad_date(kind: str, bad_day: object) -> None:
    item = record(kind)
    if kind == "biometrics":
        item["metaData"] = {"calendarDate": bad_day}
    else:
        item["calendarDate"] = bad_day
    with pytest.raises(WellnessFormatError):
        parsed(kind, [item])


BIOMETRICS_STAMPS = [
    "2000-01-02",
    "2000-01-02T00:00:00",
    "2000-01-02T06:30:15.1",
    "2000-01-02T06:30:15.12",
    "2000-01-02T06:30:15.123",
    "2000-01-02T23:59:59.123456",
]


@pytest.mark.parametrize("stamp", BIOMETRICS_STAMPS)
def test_biometrics_calendar_date_may_carry_a_local_time(stamp: str) -> None:
    item = record("biometrics")
    item["metaData"] = {"calendarDate": stamp}
    # local wall-clock time: the date part is the day, never shifted
    assert parsed("biometrics", [item])[0].day == date(2000, 1, 2)


@pytest.mark.parametrize(
    "stamp",
    [
        "2000-01-02T",
        "2000-01-02T06:30",
        "2000-01-02T06:30:15.",
        "2000-01-02T06:30:15.1234567",
        "2000-01-02T24:00:00",
        "2000-01-02T06:60:00",
        "2000-01-02T06:30:60",
        "2000-01-02T06:30:15Z",
        "2000-01-02T06:30:15.1Z",
        "2000-01-02T06:30:15+02:00",
        "2000-01-02T06:30:15.1-05:00",
        "2000-01-02 06:30:15",
        "2000-01-02t06:30:15",
        "2000-01-02T06:30:15\n",
        "2000-01-02\n",
        "2000-02-30T06:30:15.1",
        "x2000-01-02T06:30:15.1",
        "2000-01-02T0६:30:15",
        "2000-01-02T06:3६:15",
        "2000-01-02T06:30:15.1६",
        "2000-01-02T06:30:15,1",
    ],
)
def test_biometrics_calendar_date_rejects_other_shapes(stamp: str) -> None:
    item = record("biometrics")
    item["metaData"] = {"calendarDate": stamp}
    with pytest.raises(WellnessFormatError, match="invalid Garmin calendar date"):
        parsed("biometrics", [item])


@pytest.mark.parametrize("kind", ["uds", "sleep", "maxmet"])
@pytest.mark.parametrize("stamp", ["2000-01-02T06:30:15.1", "2000-01-02T00:00:00"])
def test_other_kinds_still_require_a_bare_date(kind: str, stamp: str) -> None:
    item = record(kind)
    item["calendarDate"] = stamp
    with pytest.raises(WellnessFormatError, match="invalid Garmin calendar date"):
        parsed(kind, [item])


@pytest.mark.parametrize("kind", KINDS)
def test_missing_date(kind: str) -> None:
    item = record(kind)
    item["metaData"] = {} if kind == "biometrics" else item.get("metaData")
    item.pop("calendarDate", None)
    with pytest.raises(WellnessFormatError):
        parsed(kind, [item])


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize(
    "payload", [b"broken", b"{}", b"1", b"[1]", b"[null]", b"\xff"]
)
def test_invalid_json(kind: str, payload: bytes) -> None:
    with pytest.raises(WellnessFormatError):
        tuple(form(kind).parse(io.BytesIO(payload)))


@pytest.mark.parametrize(
    "kind,field",
    [
        ("uds", "currentDayRestingHeartRate"),
        ("uds", "stress"),
        ("uds", "battery"),
        ("sleep", "deepSleepSeconds"),
        ("sleep", "awakeSleepSeconds"),
        ("sleep", "averageRespiration"),
        ("maxmet", "vo2MaxValue"),
        ("biometrics", "weight"),
    ],
)
@pytest.mark.parametrize("bad", [True, False, "53", [], {}])
def test_invalid_number(kind: str, field: str, bad: object) -> None:
    item = record(kind)
    if field == "stress":
        item["allDayStress"] = {
            "aggregatorList": [{"type": "TOTAL", "averageStressLevel": bad}]
        }
    elif field == "battery":
        item["bodyBattery"] = {
            "bodyBatteryStatList": [
                {"bodyBatteryStatType": "HIGHEST", "statsValue": bad}
            ]
        }
    elif kind == "biometrics":
        item["weight"] = {"weight": bad}
    else:
        item[field] = bad
    with pytest.raises(WellnessFormatError):
        parsed(kind, [item])


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("value", [float("inf"), float("nan"), -10, 10**400])
def test_outside_range(kind: str, value: object) -> None:
    item = (
        garmin_uds_record(DAY, currentDayRestingHeartRate=value)
        if kind == "uds"
        else garmin_sleep_record(DAY, respiration=value)
        if kind == "sleep"
        else garmin_maxmet_record(DAY, sport="RUNNING", vo2max=value, updated=None)
        if kind == "maxmet"
        else garmin_biometrics_record(DAY, weight_g=value, measured_at=None)
    )
    assert parsed(kind, [item])[0].values == {}


@pytest.mark.parametrize("weight", [None, {}, {"weight": None}])
def test_missing_weight(weight: object) -> None:
    assert (
        parsed("biometrics", [{"metaData": {"calendarDate": DAY}, "weight": weight}])[
            0
        ].values
        == {}
    )


def test_missing_weight_still_validates_date() -> None:
    with pytest.raises(WellnessFormatError):
        parsed("biometrics", [{"metaData": {}}])


def test_unmapped_data() -> None:
    assert (
        parsed(
            "uds",
            [
                garmin_uds_record(
                    DAY, restingHeartRate=62, sleepScore=91, trainingReadiness=99
                )
            ],
        )[0].values
        == {}
    )


@pytest.mark.parametrize("kind", KINDS)
def test_empty_file(kind: str) -> None:
    assert parsed(kind, []) == ()


@pytest.mark.parametrize("kind", KINDS)
def test_recognition_defers_date_validation(tmp_path: Path, kind: str) -> None:
    item = record(kind)
    if kind == "biometrics":
        item["metaData"] = {"calendarDate": None}
    else:
        item["calendarDate"] = None
    path = tmp_path / "synthetic.json"
    path.write_bytes(garmin_file_bytes([item]))
    assert form(kind).recognize(CandidateProbe.open(path)) is True


@pytest.mark.parametrize("kind", ["maxmet", "biometrics"])
def test_preserves_revision_candidates(kind: str) -> None:
    if kind == "maxmet":
        records = [
            garmin_maxmet_record(
                DAY, sport="RUNNING", vo2max=62, updated="2000-01-02T10:20:30.2"
            ),
            garmin_maxmet_record(
                DAY, sport="RUNNING", vo2max=51, updated="2000-01-02T10:20:30.9"
            ),
        ]
    else:
        records = [
            garmin_biometrics_record(
                DAY, weight_g=82000, measured_at="2000-01-02T10:20:30.2Z"
            ),
            garmin_biometrics_record(
                DAY, weight_g=71000, measured_at="2000-01-02T10:20:30.9Z"
            ),
        ]
    snapshots = parsed(kind, records)
    assert [list(item.values.values()) for item in snapshots] == (
        [[62], [51]] if kind == "maxmet" else [[82], [71]]
    )
    assert [item.revision for item in snapshots] == (
        ["2000-01-02T10:20:30.200000", "2000-01-02T10:20:30.900000"]
        if kind == "maxmet"
        else ["2000-01-02T10:20:30.200000Z", "2000-01-02T10:20:30.900000Z"]
    )


def test_builders() -> None:
    day = date(2000, 1, 2)
    assert garmin_uds_record(day, currentDayRestingHeartRate=51, extra="é") == {
        "calendarDate": DAY,
        "includesWellnessData": True,
        "currentDayRestingHeartRate": 51,
        "extra": "é",
    }
    assert garmin_sleep_record(
        day, deep_s=101, light_s=202, rem_s=303, awake_s=404, respiration=15
    ) == {
        "calendarDate": DAY,
        "sleepStartTimestampGMT": "2000-01-01T22:00:00Z",
        "deepSleepSeconds": 101,
        "lightSleepSeconds": 202,
        "remSleepSeconds": 303,
        "awakeSleepSeconds": 404,
        "averageRespiration": 15,
    }
    assert garmin_maxmet_record(day, sport="CYCLING", vo2max=54, updated="stamp") == {
        "calendarDate": DAY,
        "sport": "CYCLING",
        "vo2MaxValue": 54,
        "updateTimestamp": "stamp",
    }
    assert garmin_maxmet_record(DAY, sport=None, vo2max=54, updated=None) == {
        "calendarDate": DAY,
        "vo2MaxValue": 54,
        "updateTimestamp": None,
    }
    assert garmin_biometrics_record(day, weight_g=81234, measured_at="stamp") == {
        "metaData": {"calendarDate": f"{DAY}T06:30:15.1"},
        "weight": {"weight": 81234, "timestampGMT": "stamp"},
    }
    assert garmin_biometrics_record(
        day, weight_g=81234, measured_at="stamp", calendar_time=None
    ) == {
        "metaData": {"calendarDate": DAY},
        "weight": {"weight": 81234, "timestampGMT": "stamp"},
    }
    assert (
        garmin_file_bytes(
            [{"calendarDate": "2000-01-03", "note": "é"}, {"calendarDate": DAY}]
        )
        == (
            '[{"calendarDate": "2000-01-03", "note": "é"}, '
            '{"calendarDate": "2000-01-02"}]'
        ).encode()
    )
    assert [garmin_file_name(kind, day, date(2000, 4, 10)) for kind in KINDS] == [
        "UDSFile_2000-01-02_2000-04-10.json",
        "2000-01-02_2000-04-10_1_sleepData.json",
        "MetricsMaxMetData_2000-01-02_2000-04-10.json",
        "2000-01-02_2000-04-10_1_userBioMetrics.json",
    ]
    assert (
        hydration_decoy_bytes()
        == b'[{"calendarDate": "2000-01-02", "valueInML": 1234}]'
    )


@pytest.mark.parametrize("kind", KINDS)
def test_absent_snapshot_covers_and_origins(kind: str) -> None:
    items: dict[str, list[dict[str, object]]] = {
        "uds": [garmin_uds_record(DAY)],
        "sleep": [garmin_sleep_record(DAY)],
        "maxmet": [
            garmin_maxmet_record(DAY, sport="RUNNING", vo2max=None, updated=None)
        ],
        "biometrics": [{"metaData": {"calendarDate": DAY}}],
    }
    snapshot = parsed(kind, items[kind])[0]
    assert {metric.value for metric in snapshot.covers} == (
        METRICS[kind] if kind != "maxmet" else {"vo2max_run_ml_per_kg_min"}
    )
    assert snapshot.values == {}
    assert snapshot.origins == {}


@pytest.mark.parametrize("kind", KINDS)
def test_empty_name_is_whole_name(
    tmp_path: Path, kind: Literal["uds", "sleep", "maxmet", "biometrics"]
) -> None:
    path = tmp_path / (garmin_file_name(kind, DAY, DAY) + ".bak")
    path.write_bytes(b"[]")
    assert form(kind).recognize(CandidateProbe.open(path)) is False


@pytest.mark.parametrize(
    "field,value",
    [
        ("allDayStress", []),
        ("bodyBattery", 1),
        ("allDayStress", {"aggregatorList": {}}),
        ("bodyBattery", {"bodyBatteryStatList": [1]}),
    ],
)
def test_invalid_nested_container(field: str, value: object) -> None:
    with pytest.raises(WellnessFormatError):
        parsed("uds", [garmin_uds_record(DAY, **{field: value})])
