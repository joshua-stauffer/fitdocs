"""The Garmin Personal API delivery: recognition, metric mapping, absence, merge."""

import io
import json
from collections.abc import Mapping
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from fitdocs.wellness.formats import garmin
from fitdocs.wellness.merge import merge
from fitdocs.wellness.model import METRICS, DaySnapshot, Metric
from fitdocs.wellness.probe import CandidateProbe
from fitdocs.wellness.spec import ParsedEntry, Supersession, WellnessFormatError
from tests.wellness.builders_garmin import (
    PERSONAL_FETCHED_AT,
    garmin_personal_bytes,
    garmin_personal_day,
    hydration_decoy_bytes,
)

DAY = "2000-01-02"
# Every value is distinct so that any swap of two fields changes the result.
DAILY = {
    "heartRate": {"restingValue": 51, "minValue": 43, "maxValue": 189},
    "movement": {"steps": {"value": 7654}},
    "stress": {"avgLevel": 37},
    "bodyBattery": {"maxValue": 88, "minValue": 19},
    "pulseOx": {"avgValue": 96},
    # in range and distinct from EXPECTED: read from the sleep summary instead
    "respiration": {"avgValue": 21},
}
SLEEP = {
    "deepSleepSeconds": 2001,
    "lightSleepSeconds": 13002,
    "remSleepSeconds": 5003,
    "awakeSleepSeconds": 604,
    "averageRespirationValue": 15,
    # in range and distinct from EXPECTED: SpO2 comes from the daily summary
    "averageSpO2Value": 91,
}
HRV = {"lastNightAvg": 42}
WEIGHT = {"latestWeight": {"weight": 81234}}
EXPECTED = {
    Metric.RESTING_HR_BPM: 51,
    Metric.MIN_HR_BPM: 43,
    Metric.MAX_HR_BPM: 189,
    Metric.STEPS: 7654,
    Metric.STRESS_LEVEL: 37,
    Metric.BODY_BATTERY_HIGHEST: 88,
    Metric.BODY_BATTERY_LOWEST: 19,
    Metric.SPO2_PCT: 96,
    Metric.RESPIRATION_BRPM: 15,
    Metric.SLEEP_S: 20006,
    Metric.SLEEP_DEEP_S: 2001,
    Metric.SLEEP_LIGHT_S: 13002,
    Metric.SLEEP_REM_S: 5003,
    Metric.SLEEP_AWAKE_S: 604,
    Metric.HRV_RMSSD_MS: 42,
    Metric.WEIGHT_KG: 81.234,
}


def day_record(**overrides: object) -> dict[str, object]:
    sections: dict[str, object] = {
        "daily": json.loads(json.dumps(DAILY)),
        "sleep": dict(SLEEP),
        "hrv": dict(HRV),
        "weight": json.loads(json.dumps(WEIGHT)),
    }
    sections.update(overrides)
    return garmin_personal_day(DAY, **sections)


def _without_fetched_at() -> dict[str, object]:
    record = garmin_personal_day(DAY)
    del record["fetched_at"]
    return record


def parse_bytes(payload: bytes) -> tuple[DaySnapshot, ...]:
    return tuple(garmin.PERSONAL_FORMAT.parse(io.BytesIO(payload)))


def values_of(**overrides: object) -> dict[Metric, float]:
    return dict(parse_bytes(garmin_personal_bytes([day_record(**overrides)]))[0].values)


def without(*metrics: Metric) -> dict[Metric, float]:
    return {m: v for m, v in EXPECTED.items() if m not in metrics}


def nested(path: tuple[str, ...], value: object) -> dict[str, object]:
    """The daily section with the value at ``path`` replaced."""
    daily: dict[str, Any] = json.loads(json.dumps(DAILY))
    node = daily
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value
    return daily


def approx(values: dict[Metric, float]) -> object:
    return pytest.approx(values)


# Each section's own fields at other values, to be planted in every other place.
FOREIGN: dict[str, dict[str, object]] = {
    "daily": {
        "heartRate": {"restingValue": 61, "minValue": 53, "maxValue": 179},
        "movement": {"steps": {"value": 6543}},
        "stress": {"avgLevel": 47},
        "bodyBattery": {"maxValue": 78, "minValue": 29},
        "pulseOx": {"avgValue": 92},
        "respiration": {"avgValue": 18},
    },
    "sleep": {
        "deepSleepSeconds": 3001,
        "lightSleepSeconds": 14002,
        "remSleepSeconds": 6003,
        "awakeSleepSeconds": 704,
        "averageRespirationValue": 17,
        "averageSpO2Value": 93,
    },
    "hrv": {"lastNightAvg": 77},
    "weight": {"latestWeight": {"weight": 70000}},
}


OWN: Mapping[str, Mapping[str, object]] = {
    "daily": DAILY,
    "sleep": SLEEP,
    "hrv": HRV,
    "weight": WEIGHT,
}


def planted() -> dict[str, dict[str, object]]:
    """Every section with its own fields and every other section's, foreign."""
    return {
        name: {
            **{
                k: v
                for other, fields in FOREIGN.items()
                if other != name
                for k, v in fields.items()
            },
            **OWN[name],
        }
        for name in FOREIGN
    }


def test_declarations() -> None:
    assert garmin.PERSONAL_SOURCE.id == "garmin-personal"
    assert garmin.PERSONAL_SOURCE.display_name == "Garmin Personal API"
    assert garmin.PERSONAL_SOURCE.kind.value == "device"
    spec = garmin.PERSONAL_FORMAT
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
        "garmin-personal",
        garmin.PERSONAL_SOURCE,
        frozenset({".json"}),
        "original",
        ".json",
        1,
        "none",
        None,
        None,
    )
    assert spec.metrics == frozenset(EXPECTED)


def test_full_day_maps_every_metric() -> None:
    (snapshot,) = parse_bytes(garmin_personal_bytes([day_record()]))
    assert len(set(EXPECTED.values())) == len(EXPECTED)
    assert snapshot.values == approx(EXPECTED)
    assert snapshot.day == date(2000, 1, 2)


@pytest.mark.parametrize("metric", list(EXPECTED))
def test_each_metric_is_mapped(metric: Metric) -> None:
    assert values_of()[metric] == pytest.approx(EXPECTED[metric])


def test_weight_converts_grams_to_kilograms() -> None:
    assert values_of(weight={"latestWeight": {"weight": 75500}})[
        Metric.WEIGHT_KG
    ] == pytest.approx(75.5)


def test_hrv_last_night_average_is_rmssd() -> None:
    values = values_of(hrv={"lastNightAvg": 61, "lastNight5MinHigh": 99})
    assert values[Metric.HRV_RMSSD_MS] == 61
    assert Metric.HRV_SDNN_MS not in values


def test_origin_covers_and_revision() -> None:
    (snapshot,) = parse_bytes(garmin_personal_bytes([day_record()]))
    assert snapshot.origins == {metric: "garmin" for metric in EXPECTED}
    assert snapshot.covers == frozenset(EXPECTED) == garmin.PERSONAL_FORMAT.metrics
    assert snapshot.revision == PERSONAL_FETCHED_AT


def test_covers_is_full_even_when_day_has_no_sections() -> None:
    (snapshot,) = parse_bytes(garmin_personal_bytes([garmin_personal_day(DAY)]))
    assert snapshot.values == {}
    assert snapshot.covers == frozenset(EXPECTED)
    assert snapshot.revision == PERSONAL_FETCHED_AT


def test_sections_are_independent_and_may_be_absent() -> None:
    (snapshot,) = parse_bytes(
        garmin_personal_bytes([garmin_personal_day(DAY, hrv=HRV)])
    )
    assert snapshot.values == {Metric.HRV_RMSSD_MS: 42}
    assert snapshot.origins == {Metric.HRV_RMSSD_MS: "garmin"}


@pytest.mark.parametrize(
    "section,metrics",
    [
        (
            "daily",
            [
                m
                for m in EXPECTED
                if m
                not in (Metric.RESPIRATION_BRPM, Metric.HRV_RMSSD_MS, Metric.WEIGHT_KG)
                and not m.value.startswith("sleep_")
            ],
        ),
        (
            "sleep",
            [m for m in EXPECTED if m.value.startswith("sleep_")]
            + [Metric.RESPIRATION_BRPM],
        ),
        ("hrv", [Metric.HRV_RMSSD_MS]),
        ("weight", [Metric.WEIGHT_KG]),
    ],
)
@pytest.mark.parametrize(
    "form", ["missing", "null", "string", "list", "wrapped", "number", "true"]
)
def test_bad_section_leaves_only_its_metrics_absent(
    section: str, metrics: list[Metric], form: str
) -> None:
    bad: dict[str, object] = {
        "null": None,
        "string": "x",
        "list": [1],
        "number": 7,
        "true": True,
        "wrapped": [OWN[section]],
    }
    overrides = {} if form == "missing" else {section: bad[form]}
    record = day_record(**overrides)
    if form == "missing":
        del record[section]
    (snapshot,) = parse_bytes(garmin_personal_bytes([record]))
    assert metrics
    assert snapshot.values == approx(without(*metrics))


@pytest.mark.parametrize(
    "metric,path,bad",
    [
        (Metric.RESTING_HR_BPM, ("heartRate", "restingValue"), None),
        (Metric.MIN_HR_BPM, ("heartRate", "minValue"), "43"),
        (Metric.MAX_HR_BPM, ("heartRate", "maxValue"), 251),
        (Metric.STEPS, ("movement", "steps", "value"), float("nan")),
        (Metric.STRESS_LEVEL, ("stress", "avgLevel"), -1),
        (Metric.BODY_BATTERY_HIGHEST, ("bodyBattery", "maxValue"), True),
        (Metric.BODY_BATTERY_LOWEST, ("bodyBattery", "minValue"), 101),
        (Metric.SPO2_PCT, ("pulseOx", "avgValue"), float("inf")),
        (Metric.SPO2_PCT, ("pulseOx", "avgValue"), False),
        (Metric.RESTING_HR_BPM, ("heartRate", "restingValue"), 0),
        (Metric.STEPS, ("movement", "steps"), 7654),
        (Metric.STEPS, ("movement", "steps"), None),
        (Metric.STEPS, ("movement",), "x"),
        (Metric.MAX_HR_BPM, ("heartRate",), [1]),
        (Metric.STEPS, ("movement", "steps", "value"), 10**400),
    ],
)
def test_bad_daily_value_leaves_only_that_metric_absent(
    metric: Metric, path: tuple[str, ...], bad: object
) -> None:
    daily = nested(path, bad)
    bad_metrics = {metric}
    if path == ("heartRate",):
        bad_metrics = {Metric.RESTING_HR_BPM, Metric.MIN_HR_BPM, Metric.MAX_HR_BPM}
    if path == ("movement",):
        bad_metrics = {Metric.STEPS}
    assert values_of(daily=daily) == approx(without(*bad_metrics))


def test_nan_and_infinity_pass_through_python_json() -> None:
    payload = (
        garmin_personal_bytes([day_record()])
        .replace(b'"restingValue": 51', b'"restingValue": NaN')
        .replace(b'"minValue": 43', b'"minValue": -Infinity')
    )
    assert b"NaN" in payload and b"-Infinity" in payload
    (snapshot,) = parse_bytes(payload)
    assert snapshot.values == approx(without(Metric.RESTING_HR_BPM, Metric.MIN_HR_BPM))


@pytest.mark.parametrize(
    "weight",
    [
        {},
        {"latestWeight": None},
        {"latestWeight": "81234"},
        {"latestWeight": [81234]},
        {"latestWeight": [{"weight": 81234}]},
        {"latestWeight": {}},
        {"latestWeight": {"weight": None}},
        {"latestWeight": {"weight": "81234"}},
        {"latestWeight": {"weight": True}},
        {"latestWeight": {"weight": float("nan")}},
        {"latestWeight": {"weight": 0}},
        {"latestWeight": {"weight": 500001}},
        {"latestWeight": {"weight": 10**400}},
        {"weight": 81234},
    ],
)
def test_bad_weight_is_absent(weight: object) -> None:
    assert values_of(weight=weight) == approx(without(Metric.WEIGHT_KG))


@pytest.mark.parametrize("bad", [None, "42", True, 0, 1001, float("nan"), [42], {}])
def test_bad_hrv_is_absent(bad: object) -> None:
    assert values_of(hrv={"lastNightAvg": bad}) == approx(without(Metric.HRV_RMSSD_MS))


def test_hrv_other_fields_are_not_read() -> None:
    assert values_of(hrv={"weeklyAvg": 55, "lastNight5MinHigh": 99}) == approx(
        without(Metric.HRV_RMSSD_MS)
    )


@pytest.mark.parametrize("bad", [None, "15", True, 0, 101, float("inf"), [15]])
def test_bad_respiration_is_absent_and_sleep_stays(bad: object) -> None:
    sleep = {**SLEEP, "averageRespirationValue": bad}
    assert values_of(sleep=sleep) == approx(without(Metric.RESPIRATION_BRPM))


def test_export_respiration_field_name_is_not_read() -> None:
    sleep = {k: v for k, v in SLEEP.items() if k != "averageRespirationValue"}
    sleep["averageRespiration"] = 15
    assert values_of(sleep=sleep) == approx(without(Metric.RESPIRATION_BRPM))


@pytest.mark.parametrize(
    "stage,metric",
    [
        ("deepSleepSeconds", Metric.SLEEP_DEEP_S),
        ("lightSleepSeconds", Metric.SLEEP_LIGHT_S),
        ("remSleepSeconds", Metric.SLEEP_REM_S),
    ],
)
@pytest.mark.parametrize("bad", ["2001", True, float("nan"), None, 10**400])
def test_one_bad_stage_leaves_only_that_stage_absent(
    stage: str, metric: Metric, bad: object
) -> None:
    sleep = {**SLEEP, stage: bad}
    expected = without(metric)
    expected[Metric.SLEEP_S] = 20006 - EXPECTED[metric]
    assert values_of(sleep=sleep) == approx(expected)


@pytest.mark.parametrize(
    "stage,metric",
    [
        ("deepSleepSeconds", Metric.SLEEP_DEEP_S),
        ("lightSleepSeconds", Metric.SLEEP_LIGHT_S),
        ("remSleepSeconds", Metric.SLEEP_REM_S),
    ],
)
def test_negative_stage_is_absent_but_counts_in_the_shared_total(
    stage: str, metric: Metric
) -> None:
    expected = without(metric)
    expected[Metric.SLEEP_S] = 20006 - EXPECTED[metric] - 1
    assert values_of(sleep={**SLEEP, stage: -1}) == approx(expected)


@pytest.mark.parametrize(
    "stage,metric",
    [
        ("deepSleepSeconds", Metric.SLEEP_DEEP_S),
        ("lightSleepSeconds", Metric.SLEEP_LIGHT_S),
        ("remSleepSeconds", Metric.SLEEP_REM_S),
    ],
)
def test_oversized_stage_takes_the_total_with_it(stage: str, metric: Metric) -> None:
    expected = without(metric, Metric.SLEEP_S)
    assert values_of(sleep={**SLEEP, stage: 90000}) == approx(expected)


def test_zero_stage_and_zero_awake_are_values() -> None:
    sleep = {**SLEEP, "deepSleepSeconds": 0, "awakeSleepSeconds": 0}
    expected = {
        **EXPECTED,
        Metric.SLEEP_DEEP_S: 0,
        Metric.SLEEP_S: 20006 - 2001,
        Metric.SLEEP_AWAKE_S: 0,
    }
    assert values_of(sleep=sleep) == approx(expected)


@pytest.mark.parametrize("bad", ["604", True, float("inf"), None, -1, 86401, 10**400])
def test_bad_awake_leaves_only_awake_absent(bad: object) -> None:
    assert values_of(sleep={**SLEEP, "awakeSleepSeconds": bad}) == approx(
        without(Metric.SLEEP_AWAKE_S)
    )


@pytest.mark.parametrize(
    "stages",
    [
        (0, 0, 0),
        (-1, 0, 0),
        (100, -200, 0),
        (100, -100, 0),
        (None, None, None),
        ("1", "2", "3"),
        (True, True, True),
        (float("nan"), float("nan"), float("nan")),
    ],
)
def test_no_positive_stage_total_reads_no_sleep_metric(
    stages: tuple[object, object, object],
) -> None:
    sleep = {
        **SLEEP,
        "deepSleepSeconds": stages[0],
        "lightSleepSeconds": stages[1],
        "remSleepSeconds": stages[2],
    }
    assert values_of(sleep=sleep) == approx(
        {
            metric: value
            for metric, value in EXPECTED.items()
            if not metric.value.startswith("sleep_")
            and metric is not Metric.RESPIRATION_BRPM
        }
        | {Metric.RESPIRATION_BRPM: 15}
    )


HYDRATION_DICT = {"value": 3, "valueInML": 2, "goalInML": 4, "rating": 1}


def with_top_level(record: dict[str, object], **extra: object) -> bytes:
    return garmin_personal_bytes([{**record, **extra}])


@pytest.mark.parametrize("hydration", [HYDRATION_DICT, 3], ids=["object", "flat"])
def test_hydration_is_not_read(hydration: object) -> None:
    record = day_record(
        daily={**DAILY, "hydration": hydration},
        sleep={**SLEEP, "hydration": hydration},
        hrv={**HRV, "hydration": hydration},
        weight={**WEIGHT, "hydration": hydration},
    )
    (snapshot,) = parse_bytes(with_top_level(record, hydration=hydration))
    assert snapshot.values == approx(EXPECTED)
    assert Metric.HYDRATION_RATING not in snapshot.values
    assert Metric.HYDRATION_RATING not in snapshot.covers


@pytest.mark.parametrize("top", [52, {"vO2MaxValue": 52}], ids=["flat", "object"])
def test_vo2max_is_not_read(top: object) -> None:
    vo2 = {"vO2MaxValue": 52, "vo2MaxValue": 52, "vo2Max": 52, "vo2max": 52}
    record = day_record(
        daily={**DAILY, **vo2},
        sleep={**SLEEP, **vo2},
        hrv={**HRV, **vo2},
        weight={**WEIGHT, **vo2},
    )
    (snapshot,) = parse_bytes(with_top_level(record, **{**vo2, "vo2max": top}))
    assert snapshot.values == approx(EXPECTED)
    assert not any(m.value.startswith("vo2max") for m in snapshot.values)
    assert not any(m.value.startswith("vo2max") for m in snapshot.covers)


def test_fields_are_read_only_from_their_own_section() -> None:
    sections = planted()
    record = day_record(**sections)
    flat = {k: v for fields in FOREIGN.values() for k, v in fields.items()}
    (snapshot,) = parse_bytes(with_top_level(record, **flat))
    assert snapshot.values == approx(EXPECTED)


@pytest.mark.parametrize(
    "dropped", [(), ("daily",), ("sleep",), ("hrv",), ("weight",), tuple(FOREIGN)]
)
def test_foreign_fields_do_not_stand_in_for_an_absent_own_field(
    dropped: tuple[str, ...],
) -> None:
    sections = {
        name: {
            k: v
            for other, fields in FOREIGN.items()
            if other != name
            for k, v in fields.items()
        }
        for name in FOREIGN
        if name not in dropped
    }
    flat = {k: v for fields in FOREIGN.values() for k, v in fields.items()}
    record = garmin_personal_day(DAY, **sections)
    (snapshot,) = parse_bytes(with_top_level(record, **flat))
    assert snapshot.values == {}


def test_spo2_is_absent_when_the_daily_pulse_ox_is_absent() -> None:
    daily = {k: v for k, v in DAILY.items() if k != "pulseOx"}
    assert values_of(daily=daily) == approx(without(Metric.SPO2_PCT))
    assert values_of(daily={**daily, "pulseOx": None}) == approx(
        without(Metric.SPO2_PCT)
    )


def test_respiration_is_absent_when_the_sleep_summary_has_none() -> None:
    sleep = {k: v for k, v in SLEEP.items() if k != "averageRespirationValue"}
    assert values_of(sleep=sleep) == approx(without(Metric.RESPIRATION_BRPM))


_DAILY_METRIC_PATHS = {
    Metric.RESTING_HR_BPM: ("heartRate", "restingValue"),
    Metric.MIN_HR_BPM: ("heartRate", "minValue"),
    Metric.MAX_HR_BPM: ("heartRate", "maxValue"),
    Metric.STEPS: ("movement", "steps", "value"),
    Metric.STRESS_LEVEL: ("stress", "avgLevel"),
    Metric.BODY_BATTERY_HIGHEST: ("bodyBattery", "maxValue"),
    Metric.BODY_BATTERY_LOWEST: ("bodyBattery", "minValue"),
    Metric.SPO2_PCT: ("pulseOx", "avgValue"),
}


@pytest.mark.parametrize("metric", list(_DAILY_METRIC_PATHS))
def test_daily_value_range_edges(metric: Metric) -> None:
    info = METRICS[metric]
    path = _DAILY_METRIC_PATHS[metric]
    for edge in (info.minimum, info.maximum):
        got = values_of(daily=nested(path, edge))
        assert got[metric] == edge
    for outside in (info.minimum - 1, info.maximum + 1):
        assert values_of(daily=nested(path, outside)) == approx(without(metric))


def test_stress_zero_is_absent_and_one_is_kept() -> None:
    path = ("stress", "avgLevel")
    assert values_of(daily=nested(path, 0)) == approx(without(Metric.STRESS_LEVEL))
    assert values_of(daily=nested(path, 1))[Metric.STRESS_LEVEL] == 1


@pytest.mark.parametrize("grams,kept", [(1000, 1.0), (500000, 500.0)])
def test_weight_range_edges_after_conversion(grams: int, kept: float) -> None:
    got = values_of(weight={"latestWeight": {"weight": grams}})
    assert got[Metric.WEIGHT_KG] == pytest.approx(kept)


@pytest.mark.parametrize("grams", [999, 500001])
def test_weight_outside_range_after_conversion(grams: int) -> None:
    got = values_of(weight={"latestWeight": {"weight": grams}})
    assert got == approx(without(Metric.WEIGHT_KG))


def test_days_keep_order_and_ordinal() -> None:
    days = [
        garmin_personal_day("2000-01-02", hrv={"lastNightAvg": 30}),
        garmin_personal_day("2000-01-03", hrv={"lastNightAvg": 31}),
    ]
    snapshots = parse_bytes(garmin_personal_bytes(days))
    assert [(s.day, s.ordinal, s.values[Metric.HRV_RMSSD_MS]) for s in snapshots] == [
        (date(2000, 1, 2), 0, 30),
        (date(2000, 1, 3), 1, 31),
    ]


def test_empty_day_list_yields_nothing() -> None:
    assert parse_bytes(garmin_personal_bytes([])) == ()


def entry(ref: str, payload: bytes) -> ParsedEntry:
    return ParsedEntry(
        ref,
        garmin.PERSONAL_FORMAT.id,
        garmin.PERSONAL_SOURCE.id,
        Supersession.NONE,
        parse_bytes(payload),
    )


def test_later_fetch_replaces_and_retracts() -> None:
    earlier = garmin_personal_bytes(
        [day_record(hrv={"lastNightAvg": 40}, weight=WEIGHT)]
    )
    later_record = day_record(hrv={"lastNightAvg": 47}, weight={})
    later_record["fetched_at"] = "2000-01-04T00:00:00.000000Z"
    later = garmin_personal_bytes([later_record])
    for entries in (
        [entry("a", earlier), entry("b", later)],
        [entry("b", later), entry("a", earlier)],
    ):
        result = merge(entries, order_for=lambda metric: ("garmin-personal",))
        got = {v.metric: v.value for v in result.values}
        assert got[Metric.HRV_RMSSD_MS] == 47
        assert Metric.WEIGHT_KG not in got
        assert {v.origin for v in result.values} == {"garmin"}
        assert len(got) == len(EXPECTED) - 1


def test_earlier_fetch_with_higher_ref_does_not_win() -> None:
    earlier_record = day_record(hrv={"lastNightAvg": 40})
    earlier_record["fetched_at"] = "1999-12-31T00:00:00.000000Z"
    later = garmin_personal_bytes([day_record(hrv={"lastNightAvg": 47})])
    result = merge(
        [
            entry("z", garmin_personal_bytes([earlier_record])),
            entry("a", later),
        ],
        order_for=lambda metric: ("garmin-personal",),
    )
    assert {v.metric: v.value for v in result.values}[Metric.HRV_RMSSD_MS] == 47


def test_revision_order_is_the_fixed_width_string_order() -> None:
    first = day_record(hrv={"lastNightAvg": 40})
    first["fetched_at"] = "2000-01-03T04:05:06.123456Z"
    second = day_record(hrv={"lastNightAvg": 47})
    second["fetched_at"] = "2000-01-03T04:05:06.123457Z"
    for refs in (("a", "z"), ("z", "a")):
        result = merge(
            [
                entry(refs[0], garmin_personal_bytes([first])),
                entry(refs[1], garmin_personal_bytes([second])),
            ],
            order_for=lambda metric: ("garmin-personal",),
        )
        assert {v.metric: v.value for v in result.values}[Metric.HRV_RMSSD_MS] == 47


def recognized(tmp_path: Path, payload: bytes, name: str = "delivery.json") -> bool:
    path = tmp_path / name
    path.write_bytes(payload)
    return garmin.PERSONAL_FORMAT.recognize(CandidateProbe.open(path))


def test_recognizes_the_envelope(tmp_path: Path) -> None:
    assert recognized(tmp_path, garmin_personal_bytes([day_record()])) is True
    assert recognized(tmp_path, garmin_personal_bytes([])) is True
    assert recognized(tmp_path, garmin_personal_bytes(None)) is True
    envelope = b'{"format": "fitdocs.garmin-personal-wellness", "version": 1}'
    assert recognized(tmp_path, envelope) is True


@pytest.mark.parametrize(
    "payload",
    [
        garmin_personal_bytes([day_record()], format_name="fitdocs.other"),
        garmin_personal_bytes([day_record()], format_name=None),
        garmin_personal_bytes([day_record()], version=2),
        garmin_personal_bytes([day_record()], version=True),
        garmin_personal_bytes([day_record()], version="1"),
        garmin_personal_bytes([day_record()], version=1.0),
        b'{"days": []}',
        b'{"format": "fitdocs.garmin-personal-wellness"}',
        b"[]",
        b'[{"calendarDate": "2000-01-02", "includesWellnessData": true}]',
        b"not json",
        hydration_decoy_bytes(),
    ],
)
def test_does_not_recognize_other_files(tmp_path: Path, payload: bytes) -> None:
    assert recognized(tmp_path, payload) is False


def test_export_formats_do_not_claim_the_delivery(tmp_path: Path) -> None:
    path = tmp_path / "UDSFile_2000-01-01_2000-01-02.json"
    path.write_bytes(garmin_personal_bytes([day_record()]))
    probe = CandidateProbe.open(path)
    for spec in (
        garmin.UDS_FORMAT,
        garmin.SLEEP_FORMAT,
        garmin.MAXMET_FORMAT,
        garmin.BIOMETRICS_FORMAT,
    ):
        assert spec.recognize(probe) is False


@pytest.mark.parametrize(
    "payload",
    [
        b"not json",
        b"[]",
        b"[1]",
        b"{}",
        garmin_personal_bytes([], format_name="fitdocs.other"),
        garmin_personal_bytes([], version=2),
        garmin_personal_bytes([], version=True),
        garmin_personal_bytes([], version=1.0),
        b"\xff\xfe",  # a UTF-16 BOM and nothing else: decodes as empty text
        b'{"format": "fitdocs.garmin-personal-wellness", "version": 1}',
        garmin_personal_bytes(None),
        garmin_personal_bytes({}),
        garmin_personal_bytes(["2000-01-02"]),
        garmin_personal_bytes([garmin_personal_day(None)]),
        garmin_personal_bytes([garmin_personal_day("2000-1-2")]),
        garmin_personal_bytes([garmin_personal_day("2000-02-30")]),
        garmin_personal_bytes([garmin_personal_day("2000-01-02T00:00:00")]),
        garmin_personal_bytes([garmin_personal_day(20000102)]),
        garmin_personal_bytes([garmin_personal_day("20000102")]),
        garmin_personal_bytes([garmin_personal_day("2000-W01-7")]),
        # invalid UTF-8 inside an otherwise well-formed envelope
        b'{"format": "fitdocs.garmin-personal-wellness", "version": 1, '
        b'"days": [], "x": "\xff"}',
        garmin_personal_bytes([garmin_personal_day(DAY, fetched_at=None)]),
        garmin_personal_bytes([garmin_personal_day(DAY, fetched_at=12345)]),
        garmin_personal_bytes([garmin_personal_day(DAY, fetched_at="soon")]),
        garmin_personal_bytes([_without_fetched_at()]),
        *[
            garmin_personal_bytes([garmin_personal_day(DAY, fetched_at=stamp)])
            for stamp in (
                "2000-01-03T04:05:06.123456",
                "2000-01-03T04:05:06.123456+00:00",
                "2000-01-03T06:05:06.123456+02:00",
                "2000-01-03T04:05:06Z",
                "2000-01-03T04:05:06.123Z",
                "2000-01-03T04:05:06.1234567Z",
                "2000-01-03 04:05:06.123456Z",
                "2000-01-03T04:05:06.123456z",
                "2000-01-03T24:00:00.000000Z",
                "2000-13-01T00:00:00.000000Z",
                "2000-02-30T00:00:00.000000Z",
                "2000-01-03T04:05:60.000000Z",
                " 2000-01-03T04:05:06.123456Z",
                "\u0662\u0660\u0660\u0660-01-03T04:05:06.123456Z",
            )
        ],
        garmin_personal_bytes([garmin_personal_day(DAY), garmin_personal_day(DAY)]),
        garmin_personal_bytes(
            [garmin_personal_day("2000-01-03"), garmin_personal_day("2000-01-02")]
        ),
        garmin_personal_bytes(
            [
                garmin_personal_day("2000-01-02"),
                garmin_personal_day("2000-01-04"),
                garmin_personal_day("2000-01-03"),
            ]
        ),
        garmin_personal_bytes(
            [
                garmin_personal_day("2000-01-02"),
                garmin_personal_day("2000-01-03"),
                garmin_personal_day("2000-01-03"),
            ]
        ),
    ],
)
def test_envelope_outside_the_form_is_refused(payload: bytes) -> None:
    with pytest.raises(WellnessFormatError):
        parse_bytes(payload)


def test_a_good_day_before_a_bad_one_does_not_hide_the_refusal() -> None:
    payload = garmin_personal_bytes(
        [day_record(), garmin_personal_day("2000-01-03", fetched_at=None)]
    )
    with pytest.raises(WellnessFormatError):
        parse_bytes(payload)
