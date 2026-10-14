"""Daily reduction of directly constructed synthetic records."""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from datetime import date
from enum import StrEnum
from itertools import permutations

import pytest

from fitdocs.wellness.formats.apple import reduce as reduction
from fitdocs.wellness.formats.apple.records import AppleType, RawRecord
from fitdocs.wellness.formats.apple.reduce import (
    POLICIES,
    DailyRule,
    DayReducer,
    DayRule,
    TypePolicy,
    Writer,
    device_maker_model,
    reduce_records,
    writer_of,
)
from fitdocs.wellness.model import DaySnapshot, Metric, accept_value
from fitdocs.wellness.spec import WellnessFormatError


def record(
    kind: str = AppleType.RESTING_HEART_RATE,
    /,
    *,
    source_name: str | None = "Example Watch",
    source_version: str | None = "10.2",
    device: str | None = "manufacturer:Apple Inc., model:Watch",
    unit: str | None = "count/min",
    creation_date: str | None = None,
    start_date: str | None = "2024-01-10 07:00:00 -0800",
    end_date: str | None = "2024-01-10 07:01:00 -0800",
    value: str | None = "57",
) -> RawRecord:
    return RawRecord(
        kind,
        source_name,
        source_version,
        device,
        unit,
        creation_date,
        start_date,
        end_date,
        value,
    )


def test_flag_daily_value() -> None:
    assert tuple((s.day, dict(s.values)) for s in reduce_records([record()])) == (
        (date(2024, 1, 10), {Metric.RESTING_HR_BPM: 57.0}),
    )


PolicyRow = tuple[str, tuple[str, ...], set[str], dict[str, float], str, str]
POLICY_ROWS: tuple[PolicyRow, ...] = (
    (
        "HKCategoryTypeIdentifierSleepAnalysis",
        ("sleep_s", "sleep_deep_s", "sleep_light_s", "sleep_rem_s", "sleep_awake_s"),
        {"watch", "iphone"},
        {},
        "wake-date",
        "sleep-night",
    ),
    (
        "HKQuantityTypeIdentifierHeartRateVariabilitySDNN",
        ("hrv_sdnn_ms",),
        {"watch"},
        {"ms": 1},
        "night-of-reading",
        "asleep-mean",
    ),
    (
        "HKQuantityTypeIdentifierRespiratoryRate",
        ("respiration_brpm",),
        {"watch"},
        {"count/min": 1},
        "night-of-reading",
        "asleep-mean",
    ),
    (
        "HKQuantityTypeIdentifierOxygenSaturation",
        ("spo2_pct",),
        {"watch"},
        {"%": 100},
        "night-of-reading",
        "asleep-mean",
    ),
    (
        "HKQuantityTypeIdentifierRestingHeartRate",
        ("resting_hr_bpm",),
        {"watch"},
        {"count/min": 1},
        "start-date",
        "final",
    ),
    (
        "HKQuantityTypeIdentifierVO2Max",
        ("vo2max_ml_per_kg_min",),
        {"watch"},
        {
            "mL/min·kg": 1,
            "mL/kg·min": 1,
            "mL/(kg·min)": 1,
            "mL/kg/min": 1,
            "ml/(kg*min)": 1,
        },
        "start-date",
        "final",
    ),
    (
        "HKQuantityTypeIdentifierStepCount",
        ("steps",),
        {"watch", "iphone"},
        {"count": 1},
        "start-date",
        "largest-total",
    ),
    (
        "HKQuantityTypeIdentifierBodyMass",
        ("weight_kg",),
        {"watch", "iphone", "other"},
        {"kg": 1, "lb": 0.45359237, "g": 0.001, "st": 6.35029318},
        "start-date",
        "latest",
    ),
)


@pytest.mark.parametrize("row", POLICY_ROWS, ids=range(8))
@pytest.mark.parametrize(
    "field", ("apple_type", "metrics", "writers", "units", "day_rule", "daily_rule")
)
def test_policy_fields(row: PolicyRow, field: str) -> None:
    expected_type: dict[str, type] = {
        "apple_type": AppleType,
        "metrics": tuple,
        "writers": frozenset,
        "units": Mapping,
        "day_rule": DayRule,
        "daily_rule": DailyRule,
    }
    actual = getattr(POLICIES[AppleType(row[0])], field)
    assert (isinstance(actual, expected_type[field]), actual) == (
        True,
        row[
            (
                "apple_type",
                "metrics",
                "writers",
                "units",
                "day_rule",
                "daily_rule",
            ).index(field)
        ],
    )


def test_policy_inventory() -> None:
    assert set(POLICIES) == {row[0] for row in POLICY_ROWS}


@pytest.mark.parametrize(
    "enum, expected",
    (
        (Writer, {"WATCH": "watch", "PHONE": "iphone", "OTHER": "other"}),
        (
            DayRule,
            {
                "WAKE_DATE": "wake-date",
                "NIGHT_OF_READING": "night-of-reading",
                "START_DATE": "start-date",
            },
        ),
        (
            DailyRule,
            {
                "SLEEP_NIGHT": "sleep-night",
                "ASLEEP_MEAN": "asleep-mean",
                "FINAL": "final",
                "LARGEST_TOTAL": "largest-total",
                "LATEST": "latest",
            },
        ),
    ),
    ids=("writer", "day", "daily"),
)
def test_enums(enum: type[StrEnum], expected: dict[str, str]) -> None:
    assert {name: value.value for name, value in enum.__members__.items()} == expected


def test_policy_frozen() -> None:
    policy = TypePolicy(
        AppleType.BODY_MASS,
        (Metric.WEIGHT_KG,),
        frozenset({Writer.OTHER}),
        {"kg": 1},
        DayRule.START_DATE,
        DailyRule.LATEST,
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        policy.daily_rule = DailyRule.FINAL  # type: ignore[misc]


@pytest.mark.parametrize(
    "device, expected",
    (
        ("manufacturer:Apple Inc., model:Watch", ("Apple Inc.", "Watch")),
        (" model : iPhone , manufacturer : Apple Inc. ", ("Apple Inc.", "iPhone")),
        (
            "name:Example, software:10.2, manufacturer:Other Ltd., "
            "model:Watch, hardware:Watch6,1",
            ("Other Ltd.", "Watch"),
        ),
        ("manufacturer:apple inc., model:watch", ("apple inc.", "watch")),
        ("manufacturer:, model:", ("", "")),
        ("manufacturer:Apple Inc.", None),
        ("model:Watch", None),
        ("", None),
        ("manufacturer Apple Inc., model Watch", None),
        ("manufacturer:Apple Inc., Model:Watch", None),
    ),
    ids=(
        "watch",
        "padded-phone",
        "other",
        "lowercase",
        "empty-fields",
        "no-model",
        "no-maker",
        "empty",
        "no-colons",
        "field-case",
    ),
)
def test_device_fields(device: str, expected: tuple[str, str] | None) -> None:
    assert device_maker_model(device) == expected


@pytest.mark.parametrize(
    "evidence, expected",
    (
        ([("Apple Inc.", "Watch")], Writer.WATCH),
        ([("Apple Inc.", "iPhone")], Writer.PHONE),
        ([("Apple Inc.", "iPhone"), ("Apple Inc.", "Watch")], Writer.WATCH),
        ([("Other Ltd.", "Watch")], Writer.OTHER),
        ([("Apple Inc.", "Other")], Writer.OTHER),
        ([("apple inc.", "Watch")], Writer.OTHER),
        ([("Apple Inc.", "watch")], Writer.OTHER),
        ([], Writer.OTHER),
    ),
    ids=(
        "watch",
        "phone",
        "mixed",
        "other-maker",
        "other-model",
        "maker-case",
        "model-case",
        "empty",
    ),
)
def test_writer(evidence: list[tuple[str, str]], expected: Writer) -> None:
    assert writer_of(evidence) == expected


WATCH = "manufacturer:Apple Inc., model:Watch"
PHONE = "manufacturer:Apple Inc., model:iPhone"
RHR = AppleType.RESTING_HEART_RATE
VO2 = AppleType.VO2_MAX
STEPS = AppleType.STEP_COUNT
WEIGHT = AppleType.BODY_MASS


def t(hour: str, day: int = 10, offset: str = "-0800") -> str:
    return f"2024-01-{day:02} {hour}:00:00 {offset}"


def quantity(
    kind: AppleType, value: str | int | float, **changes: str | None
) -> RawRecord:
    defaults = {RHR: "count/min", VO2: "mL/min·kg", STEPS: "count", WEIGHT: "kg"}
    return record(kind, value=str(value), **{"unit": defaults[kind], **changes})


DAILY_CASES: tuple[tuple[str, list[RawRecord], dict[str, float]], ...] = (
    (
        "evidence-deviceless-version",
        [
            quantity(RHR, 93, device=None, source_version="11.4", end_date=t("09")),
            quantity(VO2, 41, source_version="10.2"),
        ],
        {"resting_hr_bpm": 93, "vo2max_ml_per_kg_min": 41},
    ),
    (
        "evidence-mixed-phone-watch",
        [
            quantity(RHR, 82, device=PHONE, end_date=t("09")),
            quantity(VO2, 37, device=WATCH),
        ],
        {"resting_hr_bpm": 82, "vo2max_ml_per_kg_min": 37},
    ),
    ("no-evidence", [quantity(RHR, 76, device=None)], {}),
    ("phone-rhr-excluded", [quantity(RHR, 73, device=PHONE)], {}),
    (
        "other-rhr-excluded",
        [
            quantity(
                RHR,
                91,
                source_name="Example Sleep App",
                device="manufacturer:Other Ltd., model:Watch",
            )
        ],
        {},
    ),
    (
        "source-case-distinct",
        [
            quantity(
                RHR, 92, source_name="example watch", device=None, end_date=t("09")
            ),
            quantity(RHR, 61, source_name="Example Watch"),
        ],
        {"resting_hr_bpm": 61},
    ),
    (
        "source-padding-distinct",
        [
            quantity(
                RHR, 94, source_name=" Example Watch ", device=None, end_date=t("09")
            ),
            quantity(RHR, 63),
        ],
        {"resting_hr_bpm": 63},
    ),
    (
        "source-whitespace-preserved",
        [
            quantity(RHR, 67, source_name=" ", device=None, end_date=t("09")),
            quantity(VO2, 39, source_name=" "),
        ],
        {"resting_hr_bpm": 67, "vo2max_ml_per_kg_min": 39},
    ),
    (
        "final-end-rhr",
        [
            quantity(RHR, 98, start_date=t("08"), end_date=t("09")),
            quantity(RHR, 54, start_date=t("07"), end_date=t("10")),
        ],
        {"resting_hr_bpm": 54},
    ),
    (
        "final-end-vo2",
        [
            quantity(VO2, 69, start_date=t("08"), end_date=t("09")),
            quantity(VO2, 43, start_date=t("07"), end_date=t("10")),
        ],
        {"vo2max_ml_per_kg_min": 43},
    ),
    (
        "final-creation-rhr",
        [
            quantity(
                RHR, 96, start_date=t("08"), end_date=t("10"), creation_date=t("11")
            ),
            quantity(
                RHR, 52, start_date=t("07"), end_date=t("10"), creation_date=t("12")
            ),
        ],
        {"resting_hr_bpm": 52},
    ),
    (
        "final-creation-vo2",
        [
            quantity(
                VO2, 68, start_date=t("08"), end_date=t("10"), creation_date=t("11")
            ),
            quantity(
                VO2, 44, start_date=t("07"), end_date=t("10"), creation_date=t("12")
            ),
        ],
        {"vo2max_ml_per_kg_min": 44},
    ),
    (
        "final-present-before-missing",
        [
            quantity(RHR, 99, start_date=t("08"), end_date=t("10")),
            quantity(
                RHR,
                53,
                start_date=t("07"),
                end_date=t("10"),
                creation_date="0001-01-01T00:00:00+00:00",
            ),
        ],
        {"resting_hr_bpm": 53},
    ),
    (
        "final-value-tie",
        [
            quantity(RHR, 51, start_date=t("08"), end_date=t("10")),
            quantity(RHR, 86, start_date=t("07"), end_date=t("10")),
        ],
        {"resting_hr_bpm": 86},
    ),
    (
        "final-aware-instants",
        [
            quantity(
                RHR,
                97,
                end_date=t("11", offset="+0200"),
                start_date=t("07", offset="+0200"),
            ),
            quantity(RHR, 58, end_date=t("10", offset="-0800")),
        ],
        {"resting_hr_bpm": 58},
    ),
    (
        "final-aware-creation",
        [
            quantity(RHR, 95, end_date=t("10"), creation_date=t("23", offset="+0500")),
            quantity(RHR, 56, end_date=t("10"), creation_date=t("20", offset="-0800")),
        ],
        {"resting_hr_bpm": 56},
    ),
    (
        "final-across-writers",
        [
            quantity(RHR, 97, source_name="Example Watch A", end_date=t("09")),
            quantity(RHR, 55, source_name="Example Watch B", end_date=t("10")),
        ],
        {"resting_hr_bpm": 55},
    ),
    (
        "steps-largest",
        [
            quantity(STEPS, 300),
            quantity(STEPS, 410),
            quantity(STEPS, 900, source_name="Example iPhone", device=PHONE),
            quantity(STEPS, 1800, source_name="Example Sleep App", device=None),
        ],
        {"steps": 900},
    ),
    (
        "steps-same-source-version",
        [
            quantity(STEPS, 320, source_version="10.2"),
            quantity(STEPS, 470, source_version="11.4", device=None),
            quantity(STEPS, 610, source_name="Example iPhone", device=PHONE),
        ],
        {"steps": 790},
    ),
    (
        "steps-sum-not-max-record",
        [
            quantity(STEPS, 370),
            quantity(STEPS, 430),
            quantity(STEPS, 650, source_name="Example iPhone", device=PHONE),
        ],
        {"steps": 800},
    ),
    (
        "steps-other-only",
        [quantity(STEPS, 1000, source_name="Example Sleep App", device=None)],
        {},
    ),
    (
        "steps-fractional",
        [quantity(STEPS, "100.25"), quantity(STEPS, "0.125"), quantity(STEPS, "200")],
        {"steps": 300.375},
    ),
    (
        "steps-fsum",
        [
            quantity(STEPS, "1e16"),
            quantity(STEPS, "-1e16"),
            quantity(STEPS, "0.5"),
            quantity(STEPS, "0.0000000000000001"),
            quantity(STEPS, "0.4999999999999999"),
        ],
        {"steps": 1},
    ),
    (
        "steps-fsum-fractional",
        [
            quantity(STEPS, "10000000000000000.5"),
            quantity(STEPS, "0.5"),
            quantity(STEPS, "-10000000000000000.25"),
            quantity(STEPS, "2.25"),
        ],
        {"steps": 2.75},
    ),
    (
        "latest-start",
        [
            quantity(
                WEIGHT,
                96,
                source_name="Example iPhone",
                device=PHONE,
                start_date=t("08"),
                end_date=t("12"),
            ),
            quantity(
                WEIGHT,
                71,
                source_name="Example Scale",
                device=None,
                start_date=t("10"),
                end_date=t("11"),
            ),
        ],
        {"weight_kg": 71},
    ),
    (
        "latest-creation",
        [
            quantity(
                WEIGHT, 95, start_date=t("08"), end_date=t("12"), creation_date=t("13")
            ),
            quantity(
                WEIGHT,
                72,
                source_name="Example Scale",
                device=None,
                start_date=t("08"),
                end_date=t("11"),
                creation_date=t("14"),
            ),
        ],
        {"weight_kg": 72},
    ),
    (
        "latest-missing-creation",
        [
            quantity(WEIGHT, 99, start_date=t("08"), end_date=t("12")),
            quantity(
                WEIGHT,
                73,
                source_name="Example Scale",
                device=None,
                start_date=t("08"),
                end_date=t("11"),
                creation_date="0001-01-01T00:00:00+00:00",
            ),
        ],
        {"weight_kg": 73},
    ),
    (
        "latest-converted-tie",
        [quantity(WEIGHT, 80000, unit="g"), quantity(WEIGHT, 190, unit="lb")],
        {"weight_kg": 86.18},
    ),
    (
        "latest-aware-instants",
        [
            quantity(
                WEIGHT,
                97,
                start_date=t("11", offset="+0200"),
                end_date=t("12", offset="+0200"),
            ),
            quantity(WEIGHT, 74, start_date=t("10"), end_date=t("11")),
        ],
        {"weight_kg": 74},
    ),
    (
        "latest-aware-creation",
        [
            quantity(WEIGHT, 95, creation_date=t("23", offset="+0500")),
            quantity(WEIGHT, 76, creation_date=t("20", offset="-0800")),
        ],
        {"weight_kg": 76},
    ),
    ("zero-rhr", [quantity(RHR, 0)], {}),
    ("range-rhr", [quantity(RHR, 251)], {}),
    ("range-vo2", [quantity(VO2, 101)], {}),
    ("range-steps", [quantity(STEPS, 1000001)], {}),
    ("range-weight", [quantity(WEIGHT, 501)], {}),
    (
        "boundary-valid",
        [
            quantity(RHR, 250),
            quantity(VO2, 100),
            quantity(STEPS, 1000000),
            quantity(WEIGHT, 500),
        ],
        {
            "resting_hr_bpm": 250,
            "vo2max_ml_per_kg_min": 100,
            "steps": 1000000,
            "weight_kg": 500,
        },
    ),
    (
        "equal-start-end",
        [quantity(RHR, " 6.2e1 ", start_date=t("08"), end_date=t("08"))],
        {"resting_hr_bpm": 62},
    ),
)


@pytest.mark.parametrize(
    "name, records, expected", DAILY_CASES, ids=[case[0] for case in DAILY_CASES]
)
def test_daily_cases(
    name: str, records: list[RawRecord], expected: dict[str, float]
) -> None:
    result: object
    try:
        result = tuple(
            dict(snapshot.values) for snapshot in reduce_records(iter(records))
        )
    except WellnessFormatError as exc:
        result = str(exc)
    assert result == ((expected,) if expected else ())


@pytest.mark.parametrize(
    "unit,value,expected",
    (
        ("kg", "73.456", 73.46),
        ("lb", "170", 77.11),
        ("g", "81234", 81.23),
        ("st", "12", 76.2),
        ("kg", "64.321", 64.32),
        ("lb", "155", 70.31),
        ("g", "67234", 67.23),
        ("st", "11.5", 73.03),
    ),
    ids=("kg", "lb", "g", "st", "kg-second", "lb-second", "g-second", "st-second"),
)
def test_weight_units(unit: str, value: str, expected: float) -> None:
    assert tuple(
        dict(s.values)
        for s in reduce_records([quantity(WEIGHT, value, unit=unit, device=None)])
    ) == ({"weight_kg": expected},)


@pytest.mark.parametrize(
    "unit,value",
    tuple(
        (unit, value)
        for value in (47.25, 39.75)
        for unit in (
            "mL/min·kg",
            "mL/kg·min",
            "mL/(kg·min)",
            "mL/kg/min",
            "ml/(kg*min)",
        )
    ),
    ids=range(10),
)
def test_vo2_units(unit: str, value: float) -> None:
    assert tuple(
        dict(s.values) for s in reduce_records([quantity(VO2, value, unit=unit)])
    ) == ({"vo2max_ml_per_kg_min": value},)


@pytest.mark.parametrize(
    "field", ("day", "covers", "origins", "revision", "ordinal", "values")
)
def test_snapshot_fields(field: str) -> None:
    records = [
        quantity(WEIGHT, 78.5, start_date=t("23", day=11), end_date=t("23", day=11)),
        quantity(
            RHR,
            59,
            start_date="2024-01-10T23:30:00-08:00",
            end_date="2024-01-11T00:15:00-08:00",
        ),
        quantity(VO2, 42),
        quantity(STEPS, 123),
    ]
    expected: dict[str, object] = {
        "day": (date(2024, 1, 10), date(2024, 1, 11)),
        "covers": (
            frozenset(
                {
                    "sleep_s",
                    "sleep_deep_s",
                    "sleep_light_s",
                    "sleep_rem_s",
                    "sleep_awake_s",
                    "hrv_sdnn_ms",
                    "respiration_brpm",
                    "spo2_pct",
                    "resting_hr_bpm",
                    "vo2max_ml_per_kg_min",
                    "steps",
                    "weight_kg",
                }
            ),
        )
        * 2,
        "origins": (
            {
                "resting_hr_bpm": "apple",
                "vo2max_ml_per_kg_min": "apple",
                "steps": "apple",
            },
            {},
        ),
        "revision": (None, None),
        "ordinal": (0, 1),
        "values": (
            {"resting_hr_bpm": 59, "vo2max_ml_per_kg_min": 42, "steps": 123},
            {"weight_kg": 78.5},
        ),
    }
    assert tuple(getattr(s, field) for s in reduce_records(records)) == expected[field]


@pytest.mark.parametrize("order", tuple(permutations(range(3))), ids=range(6))
def test_order_independent(order: tuple[int, ...]) -> None:
    records = [
        quantity(RHR, 97, device=None, end_date=t("09")),
        quantity(RHR, 58, device=None, end_date=t("10")),
        quantity(VO2, 44, source_version="11.4"),
    ]
    assert tuple(
        dict(s.values) for s in reduce_records(records[index] for index in order)
    ) == ({"resting_hr_bpm": 58, "vo2max_ml_per_kg_min": 44},)


def test_incremental_reclassification() -> None:
    reducer = DayReducer()
    reducer.add(quantity(RHR, 63, device=None))
    before = reducer.snapshots()
    reducer.add(quantity(VO2, 46, source_version="11.4"))
    assert (before, tuple(dict(s.values) for s in reducer.snapshots())) == (
        (),
        ({"resting_hr_bpm": 63, "vo2max_ml_per_kg_min": 46},),
    )


def test_unknown_type_ignored() -> None:
    unknown = record(
        "HKQuantityTypeIdentifierHeartRate",
        source_name=None,
        start_date=None,
        end_date=None,
        unit="invalid",
        value="nan",
    )
    error = None
    snapshots: tuple[DaySnapshot, ...] = ()
    try:
        snapshots = reduce_records([unknown])
    except WellnessFormatError as exc:
        error = str(exc)
    assert (snapshots, error) == ((), None)


def test_empty_stream() -> None:
    assert reduce_records(iter(())) == ()


def test_exact_integer_steps(monkeypatch: pytest.MonkeyPatch) -> None:
    observed: list[tuple[Metric, float | int, type]] = []
    original = accept_value

    def capture(metric: Metric, value: float | int) -> float | None:
        observed.append((metric, value, type(value)))
        return original(metric, value)

    monkeypatch.setattr(reduction, "accept_value", capture)
    snapshots = reduce_records(
        [quantity(STEPS, "9007199254740993"), quantity(STEPS, "2")]
    )
    assert (observed, snapshots) == ([(Metric.STEPS, 9007199254740995, int)], ())


INVALID_CASES = (
    ("source-none", {"source_name": None}, "missing sourceName"),
    ("source-empty", {"source_name": ""}, "missing sourceName"),
    ("start-none", {"start_date": None}, "missing startDate"),
    ("start-empty", {"start_date": ""}, "missing startDate"),
    ("end-none", {"end_date": None}, "missing endDate"),
    ("end-empty", {"end_date": ""}, "missing endDate"),
    ("value-none", {"value": None}, "missing value"),
    ("value-empty", {"value": ""}, "missing value"),
    ("unknown-unit", {"unit": "beats/hour"}, "unknown unit 'beats/hour'"),
    ("unit-none", {"unit": None}, "unknown unit None"),
    ("unit-empty", {"unit": ""}, "unknown unit ''"),
    ("unit-case", {"unit": "Count/min"}, "unknown unit 'Count/min'"),
    ("nonnumeric", {"value": "forty"}, "non-numeric value 'forty'"),
    ("value-spaces", {"value": " "}, "non-numeric value ' '"),
    ("nan", {"value": "nan"}, "non-finite value 'nan'"),
    ("inf", {"value": "inf"}, "non-finite value 'inf'"),
    ("negative-inf", {"value": "-inf"}, "non-finite value '-inf'"),
    ("overflow", {"value": "1e309"}, "non-finite value '1e309'"),
    (
        "start-no-offset",
        {"start_date": "2024-01-10T07:00:00"},
        "startDate lacks UTC offset",
    ),
    ("end-no-offset", {"end_date": "2024-01-10T07:01:00"}, "endDate lacks UTC offset"),
    (
        "creation-no-offset",
        {"creation_date": "2024-01-10T08:00:00"},
        "creationDate lacks UTC offset",
    ),
    ("start-unreadable", {"start_date": "bad-start"}, "invalid startDate"),
    ("end-unreadable", {"end_date": "bad-end"}, "invalid endDate"),
    ("creation-unreadable", {"creation_date": "bad-creation"}, "invalid creationDate"),
    ("creation-empty", {"creation_date": ""}, "invalid creationDate"),
    (
        "end-before-start",
        {"end_date": "2024-01-10T06:59:59-08:00"},
        "endDate before startDate",
    ),
)


@pytest.mark.parametrize(
    "name,changes,problem", INVALID_CASES, ids=[c[0] for c in INVALID_CASES]
)
def test_invalid_records(
    name: str, changes: dict[str, str | None], problem: str
) -> None:
    invalid = (
        record(**changes, device=None, source_name="Example Sleep App")
        if "source_name" not in changes
        else record(**changes, device=None)
    )
    import re

    expected = (
        rf"{re.escape(invalid.type)}: {re.escape(problem)}"
        rf".*startDate={re.escape(repr(invalid.start_date))}"
    )
    with pytest.raises(WellnessFormatError, match=expected):
        reduce_records([invalid])


@pytest.mark.parametrize(
    "enum", (Writer, DayRule, DailyRule), ids=("writer", "day", "daily")
)
def test_enum_base(enum: type[StrEnum]) -> None:
    assert issubclass(enum, StrEnum)


def test_policy_carrier_fields() -> None:
    assert tuple(
        (field.name, field.type) for field in dataclasses.fields(TypePolicy)
    ) == (
        ("apple_type", "AppleType"),
        ("metrics", "tuple[Metric, ...]"),
        ("writers", "frozenset[Writer]"),
        ("units", "Mapping[str, float]"),
        ("day_rule", "DayRule"),
        ("daily_rule", "DailyRule"),
    )


def test_policy_carrier_defaults() -> None:
    assert (
        tuple(
            (field.default, field.default_factory, field.kw_only)
            for field in dataclasses.fields(TypePolicy)
        )
        == ((dataclasses.MISSING, dataclasses.MISSING, False),) * 6
    )


@pytest.mark.parametrize(
    "missing", ("apple_type", "metrics", "writers", "units", "day_rule", "daily_rule")
)
def test_policy_required(missing: str) -> None:
    fields = dict(
        apple_type=AppleType.BODY_MASS,
        metrics=(Metric.WEIGHT_KG,),
        writers=frozenset({Writer.OTHER}),
        units={"kg": 1},
        day_rule=DayRule.START_DATE,
        daily_rule=DailyRule.LATEST,
    )
    supplied = {key: value for key, value in fields.items() if key != missing}
    constructor = getattr(reduction, TypePolicy.__name__)
    with pytest.raises(TypeError, match=f"'{missing}'"):
        constructor(**supplied)


LARGE_FINITE = str(10**308)


@pytest.mark.parametrize(
    "name,values,expected",
    (
        ("large-integrals", [LARGE_FINITE, LARGE_FINITE], ()),
        ("large-fractions", [LARGE_FINITE + ".5", LARGE_FINITE + ".5"], ()),
        (
            "cancel-positive-first",
            [
                LARGE_FINITE + ".5",
                LARGE_FINITE + ".5",
                "-" + LARGE_FINITE + ".5",
                "-" + LARGE_FINITE + ".5",
                "2.5",
            ],
            ({"steps": 2.5},),
        ),
        (
            "cancel-negative-first",
            [
                "-" + LARGE_FINITE + ".5",
                "-" + LARGE_FINITE + ".5",
                LARGE_FINITE + ".5",
                LARGE_FINITE + ".5",
                "2.5",
            ],
            ({"steps": 2.5},),
        ),
        (
            "cancel-alternating",
            [
                "2.5",
                LARGE_FINITE + ".5",
                "-" + LARGE_FINITE + ".5",
                LARGE_FINITE + ".5",
                "-" + LARGE_FINITE + ".5",
            ],
            ({"steps": 2.5},),
        ),
    ),
    ids=(
        "large-integrals",
        "large-fractions",
        "cancel-positive-first",
        "cancel-negative-first",
        "cancel-alternating",
    ),
)
def test_large_finite_steps(
    name: str, values: list[str], expected: tuple[dict[str, float], ...]
) -> None:
    result: object
    try:
        result = tuple(
            dict(s.values)
            for s in reduce_records(quantity(STEPS, value) for value in values)
        )
    except OverflowError as exc:
        result = type(exc).__name__
    assert result == expected


@pytest.mark.parametrize(
    "kind,value",
    ((RHR, 64), (VO2, 45), (STEPS, 270), (WEIGHT, 81.23)),
    ids=("rhr", "vo2", "steps", "weight"),
)
@pytest.mark.parametrize(
    "start,end",
    (
        ("2024-01-10T23:30:00-08:00", "2024-01-11T00:15:00-08:00"),
        ("2024-01-10T00:30:00+05:30", "2024-01-10T00:31:00+05:30"),
    ),
    ids=("negative", "positive"),
)
def test_own_offset_day(kind: AppleType, value: float, start: str, end: str) -> None:
    assert tuple(
        s.day
        for s in reduce_records([quantity(kind, value, start_date=start, end_date=end)])
    ) == (date(2024, 1, 10),)


@pytest.mark.parametrize(
    "kind,unit",
    (
        (RHR, "bad-resting"),
        (VO2, "bad-vo2"),
        (STEPS, "bad-steps"),
        (WEIGHT, "bad-weight"),
    ),
    ids=("rhr", "vo2", "steps", "weight"),
)
def test_error_context_by_type(kind: AppleType, unit: str) -> None:
    import re

    invalid = quantity(
        kind,
        57,
        source_name="Example Sleep App",
        device=None,
        unit=unit,
        start_date="2024-01-12T06:00:00+05:30",
        end_date="2024-01-12T06:01:00+05:30",
    )
    expected = re.escape(
        f"{kind}: unknown unit {unit!r}; startDate='2024-01-12T06:00:00+05:30'"
    )
    with pytest.raises(WellnessFormatError, match=expected):
        reduce_records([invalid])


@pytest.mark.parametrize(
    "kind,unit",
    ((RHR, " count/min "), (VO2, " mL/min·kg "), (STEPS, " count "), (WEIGHT, " lb ")),
    ids=("rhr", "vo2", "steps", "weight"),
)
def test_padded_unit_is_unknown(kind: AppleType, unit: str) -> None:
    import re

    with pytest.raises(
        WellnessFormatError, match=re.escape(f"{kind}: unknown unit {unit!r}")
    ):
        reduce_records(
            [
                quantity(
                    kind, 57, unit=unit, device=None, source_name="Example Sleep App"
                )
            ]
        )


@pytest.mark.parametrize("field", ("start_date", "end_date", "creation_date"))
def test_padded_timestamp_unreadable(field: str) -> None:
    changed = {field: " 2024-01-10T07:00:00-08:00 "}
    name = {
        "start_date": "startDate",
        "end_date": "endDate",
        "creation_date": "creationDate",
    }[field]
    with pytest.raises(WellnessFormatError, match=f"invalid {name}"):
        reduce_records(
            [record(device=None, source_name="Example Sleep App", **changed)]
        )


def test_equal_step_source_totals() -> None:
    records = [
        quantity(STEPS, 500),
        quantity(STEPS, 300),
        quantity(STEPS, 800, source_name="Example iPhone", device=PHONE),
    ]
    assert tuple(dict(s.values) for s in reduce_records(records)) == ({"steps": 800},)


@pytest.mark.parametrize(
    "kind,writer,value,expected",
    (
        (
            RHR,
            Writer.WATCH,
            "61",
            (({"resting_hr_bpm": 61}, {"resting_hr_bpm": "apple"}),),
        ),
        (RHR, Writer.PHONE, "72", ()),
        (RHR, Writer.OTHER, "83", ()),
        (
            VO2,
            Writer.WATCH,
            "43",
            (({"vo2max_ml_per_kg_min": 43}, {"vo2max_ml_per_kg_min": "apple"}),),
        ),
        (VO2, Writer.PHONE, "54", ()),
        (VO2, Writer.OTHER, "65", ()),
        (STEPS, Writer.WATCH, "260", (({"steps": 260}, {"steps": "apple"}),)),
        (STEPS, Writer.PHONE, "370", (({"steps": 370}, {"steps": "apple"}),)),
        (STEPS, Writer.OTHER, "480", ()),
        (WEIGHT, Writer.WATCH, "72.34", (({"weight_kg": 72.34}, {}),)),
        (WEIGHT, Writer.PHONE, "83.45", (({"weight_kg": 83.45}, {}),)),
        (WEIGHT, Writer.OTHER, "94.56", (({"weight_kg": 94.56}, {}),)),
    ),
    ids=(
        "rhr-watch",
        "rhr-phone",
        "rhr-other",
        "vo2-watch",
        "vo2-phone",
        "vo2-other",
        "steps-watch",
        "steps-phone",
        "steps-other",
        "weight-watch",
        "weight-phone",
        "weight-other",
    ),
)
def test_current_type_writer_admission(
    kind: AppleType,
    writer: Writer,
    value: str,
    expected: tuple[tuple[dict[str, float], dict[str, str]], ...],
) -> None:
    device = {Writer.WATCH: WATCH, Writer.PHONE: PHONE, Writer.OTHER: None}[writer]
    item = quantity(
        kind, value, source_name=f"Example {writer.value} writer", device=device
    )
    assert (
        tuple((dict(s.values), dict(s.origins)) for s in reduce_records([item]))
        == expected
    )


@pytest.mark.parametrize(
    "writer,value", ((Writer.PHONE, 85), (Writer.OTHER, 79)), ids=("phone", "other")
)
def test_excluded_vo2_cannot_replace_watch(writer: Writer, value: float) -> None:
    device = PHONE if writer == Writer.PHONE else None
    records = [
        quantity(
            VO2,
            value,
            source_name=f"Example {writer.value} VO2 writer",
            device=device,
            start_date=t("11"),
            end_date=t("12"),
        ),
        quantity(
            VO2,
            44,
            source_name="Example Eligible Watch",
            device=WATCH,
            start_date=t("08"),
            end_date=t("09"),
        ),
    ]
    assert tuple(
        (dict(s.values), dict(s.origins)) for s in reduce_records(records)
    ) == (({"vo2max_ml_per_kg_min": 44}, {"vo2max_ml_per_kg_min": "apple"}),)


@pytest.mark.parametrize(
    "name,records,expected",
    (
        (
            "late-phone",
            [
                quantity(
                    VO2,
                    67,
                    source_name="Example Later Phone",
                    source_version="1.0",
                    device=None,
                    end_date=t("12"),
                ),
                quantity(
                    STEPS,
                    130,
                    source_name="Example Later Phone",
                    source_version="1.0",
                    device=None,
                ),
                quantity(
                    STEPS,
                    7,
                    source_name="Example Later Phone",
                    source_version="2.0",
                    device=PHONE,
                ),
            ],
            (({"steps": 137}, {"steps": "apple"}),),
        ),
        (
            "late-watch",
            [
                quantity(
                    VO2,
                    58,
                    source_name="Example Later Watch",
                    source_version="1.0",
                    device=None,
                    end_date=t("12"),
                ),
                quantity(
                    STEPS,
                    11,
                    source_name="Example Later Watch",
                    source_version="2.0",
                    device=WATCH,
                ),
            ],
            (
                (
                    {"vo2max_ml_per_kg_min": 58, "steps": 11},
                    {"vo2max_ml_per_kg_min": "apple", "steps": "apple"},
                ),
            ),
        ),
        (
            "mixed-phone-watch",
            [
                quantity(
                    VO2,
                    59,
                    source_name="Example Mixed Writer",
                    source_version="1.0",
                    device=None,
                    end_date=t("12"),
                ),
                quantity(
                    STEPS,
                    9,
                    source_name="Example Mixed Writer",
                    source_version="2.0",
                    device=PHONE,
                ),
                quantity(
                    STEPS,
                    13,
                    source_name="Example Mixed Writer",
                    source_version="3.0",
                    device=WATCH,
                ),
            ],
            (
                (
                    {"vo2max_ml_per_kg_min": 59, "steps": 22},
                    {"vo2max_ml_per_kg_min": "apple", "steps": "apple"},
                ),
            ),
        ),
    ),
    ids=("late-phone", "late-watch", "mixed-phone-watch"),
)
def test_vo2_writer_evidence(
    name: str,
    records: list[RawRecord],
    expected: tuple[tuple[dict[str, float], dict[str, str]], ...],
) -> None:
    assert (
        tuple((dict(s.values), dict(s.origins)) for s in reduce_records(records))
        == expected
    )


def test_phone_weight_wins_with_no_origin() -> None:
    records = [
        quantity(
            WEIGHT,
            97,
            source_name="Example Earlier Scale",
            device=None,
            start_date=t("08"),
            end_date=t("12"),
        ),
        quantity(
            WEIGHT,
            91.23,
            source_name="Example Earlier Watch",
            device=WATCH,
            start_date=t("09"),
            end_date=t("13"),
        ),
        quantity(
            WEIGHT,
            74.32,
            source_name="Example Winning iPhone",
            device=PHONE,
            start_date=t("10"),
            end_date=t("11"),
        ),
    ]
    assert tuple(
        (dict(s.values), dict(s.origins)) for s in reduce_records(records)
    ) == (({"weight_kg": 74.32}, {}),)


def test_deviceless_weight_uses_late_phone_evidence() -> None:
    records = [
        quantity(
            WEIGHT,
            83.21,
            source_name="Example Computed Phone",
            source_version="1.0",
            device=None,
            start_date=t("10"),
            end_date=t("11"),
        ),
        quantity(
            STEPS,
            17,
            source_name="Example Computed Phone",
            source_version="2.0",
            device=PHONE,
        ),
    ]
    assert tuple(
        (dict(s.values), dict(s.origins)) for s in reduce_records(records)
    ) == (({"weight_kg": 83.21, "steps": 17}, {"steps": "apple"}),)
