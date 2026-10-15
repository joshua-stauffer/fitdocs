"""Sleep nights and readings from synthetic Apple records."""

from __future__ import annotations

import re
from collections.abc import Callable, Collection, Iterable, Mapping
from datetime import date
from itertools import permutations
from typing import Any, Final, get_type_hints

import pytest

from fitdocs.wellness.formats.apple import reduce as reduction
from fitdocs.wellness.formats.apple.records import AppleType, RawRecord, SleepState
from fitdocs.wellness.formats.apple.reduce import DayReducer, Writer, reduce_records
from fitdocs.wellness.model import DaySnapshot, Metric, accept_value
from fitdocs.wellness.spec import WellnessFormatError

WATCH = "manufacturer:Apple Inc., model:Watch"
PHONE = "manufacturer:Apple Inc., model:iPhone"
OTHER = "manufacturer:Other Ltd., model:Watch"
START = "2024-01-10T22:00:00-08:00"
END = "2024-01-11T02:00:00-08:00"
D = date(2024, 1, 11)
READINGS = (
    (AppleType.HRV_SDNN, "ms", "hrv_sdnn_ms", 63.2),
    (AppleType.RESPIRATORY_RATE, "count/min", "respiration_brpm", 14.3),
    (AppleType.OXYGEN_SATURATION, "%", "spo2_pct", 0.97),
)


def raw(
    kind: AppleType,
    value: str | float,
    start: str = START,
    end: str = END,
    *,
    source: str = "Synthetic Watch",
    device: str | None = WATCH,
    version: str = "10.0",
    unit: str | None = None,
) -> RawRecord:
    return RawRecord(kind, source, version, device, unit, None, start, end, str(value))


def sleep(
    state: SleepState = SleepState.ASLEEP_UNSPECIFIED,
    start: str = START,
    end: str = END,
    *,
    source: str = "Synthetic Watch",
    device: str | None = WATCH,
    version: str = "10.0",
    unit: str | None = None,
) -> RawRecord:
    return raw(
        AppleType.SLEEP_ANALYSIS,
        state,
        start,
        end,
        source=source,
        device=device,
        version=version,
        unit=unit,
    )


def values(
    records: Iterable[RawRecord],
) -> tuple[tuple[date, dict[str, float]], ...] | str:
    try:
        return tuple(
            (s.day, {metric.value: value for metric, value in s.values.items()})
            for s in reduce_records(records)
        )
    except (WellnessFormatError, OverflowError) as exc:
        return str(exc)


def test_flag_sleep_night() -> None:
    assert values([sleep()]) == ((D, {"sleep_s": 14400}),)


@pytest.mark.parametrize(
    "state,expected",
    (
        (SleepState.IN_BED, {}),
        (SleepState.ASLEEP_UNSPECIFIED, {"sleep_s": 14400}),
        (SleepState.ASLEEP, {"sleep_s": 14400}),
        (SleepState.AWAKE, {}),
        (
            SleepState.CORE,
            {
                "sleep_s": 14400,
                "sleep_deep_s": 0,
                "sleep_light_s": 14400,
                "sleep_rem_s": 0,
                "sleep_awake_s": 0,
            },
        ),
        (
            SleepState.DEEP,
            {
                "sleep_s": 14400,
                "sleep_deep_s": 14400,
                "sleep_light_s": 0,
                "sleep_rem_s": 0,
                "sleep_awake_s": 0,
            },
        ),
        (
            SleepState.REM,
            {
                "sleep_s": 14400,
                "sleep_deep_s": 0,
                "sleep_light_s": 0,
                "sleep_rem_s": 14400,
                "sleep_awake_s": 0,
            },
        ),
    ),
    ids=("in-bed", "unspecified", "deprecated", "awake", "core", "deep", "rem"),
)
def test_state_mapping(state: SleepState, expected: dict[str, float]) -> None:
    assert values([sleep(state)]) == (((D, expected),) if expected else ())


@pytest.mark.parametrize("writer", ("watch", "phone", "other"))
def test_sleep_writer_admission(writer: str) -> None:
    item = sleep(device={"watch": WATCH, "phone": PHONE, "other": OTHER}[writer])
    assert values([item]) == (((D, {"sleep_s": 14400}),) if writer != "other" else ())


NIGHT_CASES = (
    (
        "watch-over-phone",
        [
            sleep(end="2024-01-10T23:00:00-08:00"),
            sleep(
                start="2024-01-10T20:00:00-08:00",
                source="Synthetic Phone",
                device=PHONE,
            ),
        ],
        ((D, {"sleep_s": 3600}),),
    ),
    (
        "watch-awake-phone-asleep",
        [
            sleep(SleepState.AWAKE),
            sleep(
                end="2024-01-10T23:00:00-08:00", source="Synthetic Phone", device=PHONE
            ),
        ],
        ((D, {"sleep_s": 3600}),),
    ),
    (
        "watch-in-bed-phone-asleep",
        [
            sleep(SleepState.IN_BED),
            sleep(
                end="2024-01-10T23:00:00-08:00", source="Synthetic Phone", device=PHONE
            ),
        ],
        ((D, {"sleep_s": 3600}),),
    ),
    (
        "sleep-app-longer",
        [
            sleep(end="2024-01-10T23:00:00-08:00"),
            sleep(
                start="2024-01-10T19:00:00-08:00",
                source="Synthetic Sleep App",
                device=OTHER,
            ),
        ],
        ((D, {"sleep_s": 3600}),),
    ),
    (
        "phone-in-bed-watch-stages",
        [
            sleep(SleepState.CORE),
            sleep(
                SleepState.IN_BED,
                start="2024-01-10T19:00:00-08:00",
                source="Synthetic Phone",
                device=PHONE,
            ),
        ],
        (
            (
                D,
                {
                    "sleep_s": 14400,
                    "sleep_deep_s": 0,
                    "sleep_light_s": 14400,
                    "sleep_rem_s": 0,
                    "sleep_awake_s": 0,
                },
            ),
        ),
    ),
    (
        "unstaged-with-awake",
        [
            sleep(end="2024-01-10T23:00:00-08:00"),
            sleep(SleepState.AWAKE, start="2024-01-10T23:00:00-08:00"),
        ],
        ((D, {"sleep_s": 3600}),),
    ),
    (
        "awake-and-in-bed",
        [
            sleep(SleepState.AWAKE),
            sleep(SleepState.IN_BED, start="2024-01-10T19:00:00-08:00"),
        ],
        (),
    ),
    ("zero-asleep", [sleep(start=END)], ()),
    (
        "zero-asleep-selects-watch",
        [sleep(start=END), sleep(source="Synthetic Phone", device=PHONE)],
        (),
    ),
    (
        "nap",
        [sleep(start="2024-01-11T14:00:00+09:00", end="2024-01-11T15:00:00+09:00")],
        ((D, {"sleep_s": 3600}),),
    ),
    (
        "stages-distinct",
        [
            sleep(SleepState.CORE, end="2024-01-10T23:00:00-08:00"),
            sleep(
                SleepState.DEEP,
                start="2024-01-10T23:00:00-08:00",
                end="2024-01-11T00:30:00-08:00",
            ),
            sleep(
                SleepState.REM,
                start="2024-01-11T00:30:00-08:00",
                end="2024-01-11T01:15:00-08:00",
            ),
            sleep(
                SleepState.AWAKE,
                start="2024-01-11T01:15:00-08:00",
                end="2024-01-11T02:05:00-08:00",
            ),
        ],
        (
            (
                D,
                {
                    "sleep_s": 11700,
                    "sleep_deep_s": 5400,
                    "sleep_light_s": 3600,
                    "sleep_rem_s": 2700,
                    "sleep_awake_s": 3000,
                },
            ),
        ),
    ),
    (
        "overlap-union",
        [
            sleep(SleepState.CORE),
            sleep(
                SleepState.DEEP,
                start="2024-01-10T23:00:00-08:00",
                end="2024-01-11T01:00:00-08:00",
            ),
            sleep(SleepState.CORE),
        ],
        (
            (
                D,
                {
                    "sleep_s": 14400,
                    "sleep_deep_s": 7200,
                    "sleep_light_s": 7200,
                    "sleep_rem_s": 0,
                    "sleep_awake_s": 0,
                },
            ),
        ),
    ),
    (
        "ignored-sleep-unit",
        [sleep(unit="unexpected category unit")],
        ((D, {"sleep_s": 14400}),),
    ),
)


@pytest.mark.parametrize(
    "name,records,expected", NIGHT_CASES, ids=[c[0] for c in NIGHT_CASES]
)
def test_night_cases(name: str, records: list[RawRecord], expected: object) -> None:
    assert values(records) == expected


@pytest.mark.parametrize(
    "end,expected",
    (
        ("2024-01-10T17:59:00+09:00", date(2024, 1, 10)),
        ("2024-01-10T18:00:00+09:00", date(2024, 1, 11)),
        ("2024-01-12T17:59:00-08:00", date(2024, 1, 12)),
        ("2024-01-12T18:00:00-08:00", date(2024, 1, 13)),
    ),
    ids=(
        "positive-before",
        "positive-boundary",
        "negative-before",
        "negative-boundary",
    ),
)
def test_wake_boundary(end: str, expected: date) -> None:
    start = end.replace("17:59", "16:59").replace("18:00", "17:00")
    assert values([sleep(start=start, end=end)]) == ((expected, {"sleep_s": 3600}),)


BASE_SLEEP = (
    sleep(end="2024-01-10T23:00:00-08:00"),
    sleep(
        SleepState.AWAKE,
        start="2024-01-10T23:00:00-08:00",
        end="2024-01-11T01:00:00-08:00",
    ),
    sleep(start="2024-01-11T01:00:00-08:00"),
)
LOCATIONS = (
    ("at-start", "2024-01-10T22:00:00-08:00", True),
    ("inside", "2024-01-10T22:30:00-08:00", True),
    ("at-end", "2024-01-10T23:00:00-08:00", False),
    ("before", "2024-01-10T21:59:00-08:00", False),
    ("awake-gap", "2024-01-11T00:00:00-08:00", False),
    ("after", "2024-01-11T02:01:00-08:00", False),
    ("own-offset-instant", "2024-01-11T15:30:00+09:00", True),
)


@pytest.mark.parametrize(
    "kind,unit,metric,value", READINGS, ids=("hrv", "respiration", "oxygen")
)
@pytest.mark.parametrize("name,end,included", LOCATIONS, ids=[c[0] for c in LOCATIONS])
def test_reading_location(
    kind: AppleType,
    unit: str,
    metric: str,
    value: float,
    name: str,
    end: str,
    included: bool,
) -> None:
    expected = {"sleep_s": 7200.0}
    if included:
        expected[metric] = round(
            value * (100 if kind == AppleType.OXYGEN_SATURATION else 1), 1
        )
    reading = raw(kind, value, "2024-01-10T21:00:00-08:00", end, unit=unit)
    assert values([*BASE_SLEEP, reading]) == ((D, expected),)


@pytest.mark.parametrize(
    "kind,unit,metric,value", READINGS, ids=("hrv", "respiration", "oxygen")
)
@pytest.mark.parametrize("writer", ("watch", "phone", "other"))
def test_reading_writer_admission(
    kind: AppleType, unit: str, metric: str, value: float, writer: str
) -> None:
    reading = raw(
        kind,
        value,
        end="2024-01-10T22:30:00-08:00",
        source=f"Synthetic Reading {writer}",
        device={"watch": WATCH, "phone": PHONE, "other": OTHER}[writer],
        unit=unit,
    )
    expected = {"sleep_s": 14400.0}
    if writer == "watch":
        expected[metric] = round(
            value * (100 if kind == AppleType.OXYGEN_SATURATION else 1), 1
        )
    assert values([sleep(), reading]) == ((D, expected),)


@pytest.mark.parametrize(
    "kind,unit,metric,value", READINGS, ids=("hrv", "respiration", "oxygen")
)
@pytest.mark.parametrize("state", ("no-sleep", "phone", "in-bed", "awake", "zero"))
def test_no_watch_sleep(
    kind: AppleType, unit: str, metric: str, value: float, state: str
) -> None:
    nights = {
        "no-sleep": [],
        "phone": [sleep(source="Synthetic Phone", device=PHONE)],
        "in-bed": [sleep(SleepState.IN_BED)],
        "awake": [sleep(SleepState.AWAKE)],
        "zero": [sleep(start=END)],
    }[state]
    reading = raw(kind, value, end="2024-01-10T22:30:00-08:00", unit=unit)
    assert values([*nights, reading]) == (
        ((D, {"sleep_s": 14400}),) if state == "phone" else ()
    )


@pytest.mark.parametrize(
    "kind,unit,metric,numbers,expected",
    (
        (AppleType.HRV_SDNN, "ms", "hrv_sdnn_ms", (63.24, 64.35), 63.8),
        (
            AppleType.RESPIRATORY_RATE,
            "count/min",
            "respiration_brpm",
            (13.14, 17.37),
            15.3,
        ),
        (AppleType.OXYGEN_SATURATION, "%", "spo2_pct", (0.97, 0.95), 96.0),
        (AppleType.HRV_SDNN, "ms", "hrv_sdnn_ms", (1e16, 61, -1e16), 20.3),
        (AppleType.OXYGEN_SATURATION, "%", "spo2_pct", (0.9724, 0.9518), 96.2),
    ),
    ids=(
        "hrv-round",
        "respiration-round",
        "oxygen-percent",
        "fsum-cancellation",
        "oxygen-round",
    ),
)
def test_asleep_mean(
    kind: AppleType, unit: str, metric: str, numbers: tuple[float, ...], expected: float
) -> None:
    readings = [
        raw(kind, n, end="2024-01-10T22:30:00-08:00", unit=unit) for n in numbers
    ]
    assert values([sleep(), *readings]) == ((D, {"sleep_s": 14400, metric: expected}),)


@pytest.mark.parametrize(
    "kind,unit,metric,value", READINGS, ids=("hrv", "respiration", "oxygen")
)
def test_earliest_overlapping_night(
    kind: AppleType, unit: str, metric: str, value: float
) -> None:
    records = [
        sleep(start="2024-01-11T16:00:00+14:00", end="2024-01-11T17:59:00+14:00"),
        sleep(start="2024-01-10T13:00:00-12:00", end="2024-01-10T17:59:00-12:00"),
        raw(
            kind,
            value,
            start="2024-01-10T22:00:00Z",
            end="2024-01-11T03:00:00Z",
            unit=unit,
        ),
    ]
    assert values(records) == (
        (
            date(2024, 1, 10),
            {
                "sleep_s": 17940,
                metric: round(
                    value * (100 if kind == AppleType.OXYGEN_SATURATION else 1), 1
                ),
            },
        ),
        (D, {"sleep_s": 7140}),
    )


def test_unknown_sleep_state() -> None:
    item = sleep(start="2024-01-12T06:00:00+05:30", end="2024-01-12T07:00:00+05:30")
    item = RawRecord(
        item.type,
        item.source_name,
        item.source_version,
        item.device,
        item.unit,
        item.creation_date,
        item.start_date,
        item.end_date,
        "HKCategoryValueSleepAnalysisFuture",
    )
    with pytest.raises(
        WellnessFormatError,
        match=re.escape(
            f"{item.type}: unknown sleep state {item.value!r}; "
            f"startDate={item.start_date!r}"
        ),
    ):
        reduce_records([item])


@pytest.mark.parametrize(
    "kind,unit,metric,value", READINGS, ids=("hrv", "respiration", "oxygen")
)
def test_reading_validation(
    kind: AppleType, unit: str, metric: str, value: float
) -> None:
    item = raw(kind, value, unit="invalid spot unit")
    with pytest.raises(
        WellnessFormatError,
        match=re.escape(
            f"{kind}: unknown unit 'invalid spot unit'; startDate={START!r}"
        ),
    ):
        reduce_records([sleep(), item])


@pytest.mark.parametrize(
    "kind,unit,metric,value", READINGS, ids=("hrv", "respiration", "oxygen")
)
def test_out_of_range_reading_absent(
    kind: AppleType, unit: str, metric: str, value: float
) -> None:
    item = raw(kind, -1, end="2024-01-10T22:30:00-08:00", unit=unit)
    assert values([sleep(), item]) == ((D, {"sleep_s": 14400}),)


@pytest.mark.parametrize("order", tuple(permutations(range(4))), ids=range(24))
def test_night_order_independent(order: tuple[int, ...]) -> None:
    records = [
        sleep(device=None, version="9.0"),
        raw(
            AppleType.HRV_SDNN,
            64.4,
            end="2024-01-10T23:00:00-08:00",
            device=None,
            version="9.0",
            unit="ms",
        ),
        sleep(
            SleepState.AWAKE,
            start="2024-01-11T02:00:00-08:00",
            end="2024-01-11T03:00:00-08:00",
            device=PHONE,
            version="10.0",
        ),
        raw(
            AppleType.HRV_SDNN,
            61.2,
            end="2024-01-11T01:00:00-08:00",
            device=WATCH,
            version="11.0",
            unit="ms",
        ),
    ]
    assert values(records[i] for i in order) == (
        (D, {"sleep_s": 14400, "hrv_sdnn_ms": 62.8}),
    )


def test_incremental_night_reclassification() -> None:
    reducer = DayReducer()
    reducer.add(sleep(device=None, version="9.0"))
    before = reducer.snapshots()
    reducer.add(
        raw(
            AppleType.HRV_SDNN,
            67.3,
            end="2024-01-10T23:00:00-08:00",
            unit="ms",
            version="11.0",
        )
    )
    assert (before, tuple((s.day, dict(s.values)) for s in reducer.snapshots())) == (
        (),
        ((D, {"sleep_s": 14400, "hrv_sdnn_ms": 67.3}),),
    )


@pytest.mark.parametrize(
    "constant,expected",
    (
        ("APPLE_ORIGIN", Final[str]),
        ("POLICIES", Final[Mapping[AppleType, reduction.TypePolicy]]),
    ),
)
def test_declared_constant_types(constant: str, expected: object) -> None:
    assert get_type_hints(reduction).get(constant) == expected


@pytest.mark.parametrize(
    "target,expected",
    (
        (
            reduction.device_maker_model,
            {"device": str, "return": tuple[str, str] | None},
        ),
        (
            reduction.writer_of,
            {"evidence": Collection[tuple[str, str]], "return": Writer},
        ),
        (DayReducer.add, {"record": RawRecord, "return": type(None)}),
        (DayReducer.snapshots, {"return": tuple[DaySnapshot, ...]}),
        (
            reduce_records,
            {"records": Iterable[RawRecord], "return": tuple[DaySnapshot, ...]},
        ),
    ),
    ids=("device", "writer", "add", "snapshots", "reduce-records"),
)
def test_public_annotations(target: object, expected: dict[str, object]) -> None:
    assert get_type_hints(target) == expected


SHARED_INVALID = (
    ("source-none", "source_name", None, "missing sourceName"),
    ("source-empty", "source_name", "", "missing sourceName"),
    ("start-none", "start_date", None, "missing startDate"),
    ("start-empty", "start_date", "", "missing startDate"),
    ("end-none", "end_date", None, "missing endDate"),
    ("end-empty", "end_date", "", "missing endDate"),
    ("value-none", "value", None, "missing value"),
    ("value-empty", "value", "", "missing value"),
    ("start-invalid", "start_date", "bad-start", "invalid startDate: 'bad-start'"),
    ("end-invalid", "end_date", "bad-end", "invalid endDate: 'bad-end'"),
    (
        "creation-invalid",
        "creation_date",
        "bad-creation",
        "invalid creationDate: 'bad-creation'",
    ),
    ("creation-empty", "creation_date", "", "invalid creationDate: ''"),
    (
        "start-offset",
        "start_date",
        "2024-01-10T22:00:00",
        "startDate lacks UTC offset: '2024-01-10T22:00:00'",
    ),
    (
        "end-offset",
        "end_date",
        "2024-01-11T02:00:00",
        "endDate lacks UTC offset: '2024-01-11T02:00:00'",
    ),
    (
        "creation-offset",
        "creation_date",
        "2024-01-10T23:00:00",
        "creationDate lacks UTC offset: '2024-01-10T23:00:00'",
    ),
    ("backwards", "end_date", "2024-01-10T21:59:59-08:00", "endDate before startDate"),
    (
        "start-padded",
        "start_date",
        " 2024-01-10T22:00:00-08:00 ",
        "invalid startDate: ' 2024-01-10T22:00:00-08:00 '",
    ),
    (
        "end-padded",
        "end_date",
        " 2024-01-11T02:00:00-08:00 ",
        "invalid endDate: ' 2024-01-11T02:00:00-08:00 '",
    ),
    (
        "creation-padded",
        "creation_date",
        " 2024-01-10T23:00:00-08:00 ",
        "invalid creationDate: ' 2024-01-10T23:00:00-08:00 '",
    ),
)
NEW_TYPES = (
    (AppleType.SLEEP_ANALYSIS, None, SleepState.ASLEEP_UNSPECIFIED),
    *[(kind, unit, str(value)) for kind, unit, metric, value in READINGS],
)


@pytest.mark.parametrize(
    "kind,unit,value", NEW_TYPES, ids=("sleep", "hrv", "respiration", "oxygen")
)
@pytest.mark.parametrize(
    "name,field,text,problem", SHARED_INVALID, ids=[c[0] for c in SHARED_INVALID]
)
def test_new_type_invalid_fields(
    kind: AppleType,
    unit: str | None,
    value: str,
    name: str,
    field: str,
    text: str | None,
    problem: str,
) -> None:
    import dataclasses

    changes: dict[str, Any] = {field: text}
    item = dataclasses.replace(raw(kind, value, unit=unit), **changes)
    with pytest.raises(
        WellnessFormatError,
        match=re.escape(f"{kind}: {problem}; startDate={item.start_date!r}"),
    ):
        reduce_records([item])


@pytest.mark.parametrize(
    "kind,unit,metric,value", READINGS, ids=("hrv", "respiration", "oxygen")
)
@pytest.mark.parametrize(
    "text,problem",
    (
        ("forty", "non-numeric value 'forty'"),
        (" ", "non-numeric value ' '"),
        ("nan", "non-finite value 'nan'"),
        ("inf", "non-finite value 'inf'"),
        ("-inf", "non-finite value '-inf'"),
        ("1e309", "non-finite value '1e309'"),
    ),
    ids=("text", "spaces", "nan", "infinity", "negative-infinity", "overflow"),
)
def test_invalid_reading_values(
    kind: AppleType, unit: str, metric: str, value: float, text: str, problem: str
) -> None:
    with pytest.raises(
        WellnessFormatError, match=re.escape(f"{kind}: {problem}; startDate={START!r}")
    ):
        reduce_records([raw(kind, text, unit=unit)])


@pytest.mark.parametrize(
    "kind,unit,metric,value", READINGS, ids=("hrv", "respiration", "oxygen")
)
@pytest.mark.parametrize("bad", (None, "", "padded", "case"))
def test_invalid_reading_units(
    kind: AppleType, unit: str, metric: str, value: float, bad: str | None
) -> None:
    changed = (
        f" {unit} "
        if bad == "padded"
        else unit.upper()
        if bad == "case" and unit != "%"
        else "Percent"
        if bad == "case"
        else bad
    )
    with pytest.raises(
        WellnessFormatError,
        match=re.escape(f"{kind}: unknown unit {changed!r}; startDate={START!r}"),
    ):
        reduce_records([raw(kind, value, unit=changed)])


@pytest.mark.parametrize(
    "target,names",
    (
        (reduction.device_maker_model, ("device",)),
        (reduction.writer_of, ("evidence",)),
        (DayReducer.add, ("self", "record")),
        (DayReducer.snapshots, ("self",)),
        (reduce_records, ("records",)),
    ),
    ids=("device", "writer", "add", "snapshots", "reduce-records"),
)
def test_public_parameters(
    target: Callable[..., object], names: tuple[str, ...]
) -> None:
    import inspect

    assert tuple(
        (p.name, p.kind, p.default)
        for p in inspect.signature(target).parameters.values()
    ) == tuple(
        (name, inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.empty)
        for name in names
    )


def test_zero_sleep_not_submitted(monkeypatch: pytest.MonkeyPatch) -> None:
    submitted: list[float | int] = []
    original = accept_value

    def capture(metric: Metric, value: float | int) -> float | None:
        if metric == Metric.SLEEP_S:
            submitted.append(value)
        return original(metric, value)

    monkeypatch.setattr(reduction, "accept_value", capture)
    result = values([sleep(start=END)])
    assert (submitted, result) == ([], ())


def test_sleep_out_of_range_absent() -> None:
    assert values([sleep(start="2024-01-09T20:00:00-08:00")]) == ()


@pytest.mark.parametrize("tz", ("Pacific/Auckland", "America/Los_Angeles"))
def test_timezone_independent_nights(tz: str, monkeypatch: pytest.MonkeyPatch) -> None:
    import time

    try:
        with monkeypatch.context() as context:
            context.setenv("TZ", tz)
            time.tzset()
            records = [
                sleep(
                    start="2024-01-10T17:00:00+09:00", end="2024-01-10T18:00:00+09:00"
                ),
                raw(
                    AppleType.HRV_SDNN,
                    61.7,
                    start="2024-01-10T07:00:00Z",
                    end="2024-01-10T08:30:00Z",
                    unit="ms",
                ),
            ]
            assert values(records) == ((D, {"sleep_s": 3600, "hrv_sdnn_ms": 61.7}),)
    finally:
        time.tzset()


@pytest.mark.parametrize(
    "kind,unit,metric",
    (
        (AppleType.HRV_SDNN, "ms", "hrv_sdnn_ms"),
        (AppleType.RESPIRATORY_RATE, "count/min", "respiration_brpm"),
    ),
    ids=("hrv", "respiration"),
)
@pytest.mark.parametrize(
    "numbers,expected",
    (((1e308, 1e308), None), ((1e308, 1e308, -1e308, -1e308, 61), 12.2)),
    ids=("large-positive", "large-cancellation"),
)
def test_large_finite_asleep_mean(
    kind: AppleType,
    unit: str,
    metric: str,
    numbers: tuple[float, ...],
    expected: float | None,
) -> None:
    records = [
        sleep(),
        *[
            raw(kind, value, end="2024-01-10T23:00:00-08:00", unit=unit)
            for value in numbers
        ],
    ]
    result = {"sleep_s": 14400.0}
    if expected is not None:
        result[metric] = expected
    assert values(records) == ((D, result),)


SLEEP_VALUES: tuple[tuple[SleepState, dict[str, float]], ...] = (
    (SleepState.IN_BED, {}),
    (SleepState.AWAKE, {}),
    (SleepState.ASLEEP_UNSPECIFIED, {"sleep_s": 14400}),
    (SleepState.ASLEEP, {"sleep_s": 14400}),
    (
        SleepState.CORE,
        {
            "sleep_s": 14400,
            "sleep_deep_s": 0,
            "sleep_light_s": 14400,
            "sleep_rem_s": 0,
            "sleep_awake_s": 0,
        },
    ),
    (
        SleepState.DEEP,
        {
            "sleep_s": 14400,
            "sleep_deep_s": 14400,
            "sleep_light_s": 0,
            "sleep_rem_s": 0,
            "sleep_awake_s": 0,
        },
    ),
    (
        SleepState.REM,
        {
            "sleep_s": 14400,
            "sleep_deep_s": 0,
            "sleep_light_s": 0,
            "sleep_rem_s": 14400,
            "sleep_awake_s": 0,
        },
    ),
)


@pytest.mark.parametrize(
    "state,expected",
    SLEEP_VALUES,
    ids=("in-bed", "awake", "unspecified", "deprecated", "core", "deep", "rem"),
)
def test_phone_sleep_states(state: SleepState, expected: dict[str, float]) -> None:
    assert values([sleep(state, device=PHONE)]) == (
        ((D, expected),) if expected else ()
    )


@pytest.mark.parametrize(
    "state",
    tuple(state for state, expected in SLEEP_VALUES if expected),
    ids=("unspecified", "deprecated", "core", "deep", "rem"),
)
def test_other_asleep_states_excluded(state: SleepState) -> None:
    assert values([sleep(state, device=OTHER)]) == ()


@pytest.mark.parametrize("device", (WATCH, PHONE), ids=("watch", "phone"))
@pytest.mark.parametrize(
    "unit",
    (None, "", "unexpected category unit"),
    ids=("absent", "empty", "unexpected"),
)
def test_sleep_unit_ignored(device: str, unit: str | None) -> None:
    assert values([sleep(device=device, unit=unit)]) == ((D, {"sleep_s": 14400}),)


@pytest.mark.parametrize(
    "kind,unit,metric,value", READINGS, ids=("hrv", "respiration", "oxygen")
)
@pytest.mark.parametrize(
    "state,sleep_values",
    tuple((state, expected) for state, expected in SLEEP_VALUES if expected),
    ids=("unspecified", "deprecated", "core", "deep", "rem"),
)
def test_reading_asleep_stages(
    kind: AppleType,
    unit: str,
    metric: str,
    value: float,
    state: SleepState,
    sleep_values: dict[str, float],
) -> None:
    expected = {
        **sleep_values,
        metric: round(value * (100 if kind == AppleType.OXYGEN_SATURATION else 1), 1),
    }
    assert values(
        [sleep(state), raw(kind, value, end="2024-01-10T23:00:00-08:00", unit=unit)]
    ) == ((D, expected),)


def test_night_metric_origins() -> None:
    records = [
        *next(
            records
            for name, records, expected in NIGHT_CASES
            if name == "stages-distinct"
        ),
        *[
            raw(kind, value, end="2024-01-10T22:30:00-08:00", unit=unit)
            for kind, unit, metric, value in READINGS
        ],
    ]
    assert tuple(dict(s.origins) for s in reduce_records(records)) == (
        {
            "sleep_s": "apple",
            "sleep_deep_s": "apple",
            "sleep_light_s": "apple",
            "sleep_rem_s": "apple",
            "sleep_awake_s": "apple",
            "hrv_sdnn_ms": "apple",
            "respiration_brpm": "apple",
            "spo2_pct": "apple",
        },
    )


@pytest.mark.parametrize(
    "numbers,expected",
    (
        ((1e307, -1e307, 0.96), 32.0),
        ((-1e307, 0.96, 1e307), 32.0),
        ((1e307, 1e307, -1e307, -1e307, 0.96), 19.2),
        ((1e307, 1e307), None),
        ((-1e307, -1e307), None),
        ((0.97, 0.95), 96.0),
        ((0.9724, 0.9518), 96.2),
        ((1e14, 0.63, -1e14), 21.0),
    ),
    ids=(
        "scaled-cancellation",
        "reordered-cancellation",
        "repeated-cancellation",
        "positive-unrepresentable",
        "negative-unrepresentable",
        "normal-conversion",
        "normal-rounding",
        "normal-fsum",
    ),
)
def test_finite_oxygen_conversion_mean(
    numbers: tuple[float, ...], expected: float | None
) -> None:
    records = [
        sleep(),
        *[
            raw(
                AppleType.OXYGEN_SATURATION,
                number,
                end="2024-01-10T23:00:00-08:00",
                unit="%",
            )
            for number in numbers
        ],
    ]
    expected_values = {"sleep_s": 14400.0}
    if expected is not None:
        expected_values["spo2_pct"] = expected
    try:
        result, error = values(records), None
    except ValueError as exc:
        result, error = None, str(exc)
    assert (error, result) == (None, ((D, expected_values),))


def snapshot_values(
    snapshots: Iterable[DaySnapshot],
) -> tuple[tuple[date, dict[str, float]], ...]:
    return tuple(
        (
            snapshot.day,
            {metric.value: value for metric, value in snapshot.values.items()},
        )
        for snapshot in snapshots
    )


def test_reading_type_means_and_origins_are_separate() -> None:
    records = [
        sleep(),
        raw(AppleType.HRV_SDNN, 61.2, end="2024-01-10T23:00:00-08:00", unit="ms"),
        raw(
            AppleType.RESPIRATORY_RATE,
            14.4,
            end="2024-01-10T23:00:00-08:00",
            unit="count/min",
        ),
        raw(
            AppleType.OXYGEN_SATURATION,
            0.96,
            end="2024-01-10T23:00:00-08:00",
            unit="%",
        ),
    ]
    snapshots = reduce_records(records)
    assert (snapshot_values(snapshots), tuple(dict(s.origins) for s in snapshots)) == (
        (
            (
                D,
                {
                    "sleep_s": 14400,
                    "hrv_sdnn_ms": 61.2,
                    "respiration_brpm": 14.4,
                    "spo2_pct": 96.0,
                },
            ),
        ),
        (
            {
                "sleep_s": "apple",
                "hrv_sdnn_ms": "apple",
                "respiration_brpm": "apple",
                "spo2_pct": "apple",
            },
        ),
    )


@pytest.mark.parametrize("device", (WATCH, PHONE), ids=("watch", "phone"))
@pytest.mark.parametrize("reverse", (False, True), ids=("forward", "reverse"))
def test_all_selected_kind_sleep_sources(device: str, reverse: bool) -> None:
    records = [
        sleep(
            end="2024-01-10T23:00:00-08:00",
            source="First Sleep Source",
            device=device,
        ),
        sleep(
            start="2024-01-11T00:00:00-08:00",
            source="Second Sleep Source",
            device=device,
        ),
    ]
    assert values(reversed(records) if reverse else records) == (
        (D, {"sleep_s": 10800}),
    )


@pytest.mark.parametrize(
    "kind,unit,metric,first_value,second_value,mean",
    (
        (AppleType.HRV_SDNN, "ms", "hrv_sdnn_ms", 61.2, 65.4, 63.3),
        (AppleType.RESPIRATORY_RATE, "count/min", "respiration_brpm", 14.4, 18.6, 16.5),
        (AppleType.OXYGEN_SATURATION, "%", "spo2_pct", 0.94, 0.98, 96.0),
    ),
    ids=("hrv", "respiration", "oxygen"),
)
@pytest.mark.parametrize("reverse", (False, True), ids=("forward", "reverse"))
def test_mean_pools_distinct_watch_reading_sources(
    kind: AppleType,
    unit: str,
    metric: str,
    first_value: float,
    second_value: float,
    mean: float,
    reverse: bool,
) -> None:
    readings = [
        raw(
            kind,
            first_value,
            end="2024-01-10T23:00:00-08:00",
            source="First Reading Watch",
            unit=unit,
        ),
        raw(
            kind,
            second_value,
            end="2024-01-10T23:00:00-08:00",
            source="Second Reading Watch",
            unit=unit,
        ),
    ]
    assert values([sleep(), *(reversed(readings) if reverse else readings)]) == (
        (D, {"sleep_s": 14400, metric: mean}),
    )


@pytest.mark.parametrize(
    "kind,unit,metric,first_value,second_value,first_mean,next_mean",
    (
        (AppleType.HRV_SDNN, "ms", "hrv_sdnn_ms", 61.2, 65.4, 61.2, 63.3),
        (
            AppleType.RESPIRATORY_RATE,
            "count/min",
            "respiration_brpm",
            14.4,
            18.6,
            14.4,
            16.5,
        ),
        (AppleType.OXYGEN_SATURATION, "%", "spo2_pct", 0.94, 0.98, 94.0, 96.0),
    ),
    ids=("hrv", "respiration", "oxygen"),
)
def test_populated_snapshots_retain_readings_and_detach_results(
    kind: AppleType,
    unit: str,
    metric: str,
    first_value: float,
    second_value: float,
    first_mean: float,
    next_mean: float,
) -> None:
    reducer = DayReducer()
    reducer.add(sleep())
    reducer.add(raw(kind, first_value, end="2024-01-10T23:00:00-08:00", unit=unit))
    first = reducer.snapshots()
    second = reducer.snapshots()
    reducer.add(raw(kind, second_value, end="2024-01-10T23:30:00-08:00", unit=unit))
    reducer.add(
        sleep(start="2024-01-11T12:00:00-08:00", end="2024-01-11T13:00:00-08:00")
    )
    third = reducer.snapshots()
    original = ((D, {"sleep_s": 14400, metric: first_mean}),)
    updated = ((D, {"sleep_s": 18000, metric: next_mean}),)
    assert tuple(
        snapshot_values(snapshots) for snapshots in (first, second, third)
    ) == (
        original,
        original,
        updated,
    )


def test_overflowing_oxygen_retains_exact_converted_samples(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import math
    from fractions import Fraction

    observed: list[tuple[tuple[type, float | int | Fraction], ...]] = []
    original = math.fsum

    def capture(samples: Iterable[float | int | Fraction]) -> float:
        supplied = tuple(samples)
        observed.append(tuple((type(sample), sample) for sample in supplied))
        return original(supplied)

    monkeypatch.setattr(math, "fsum", capture)
    records = [
        sleep(),
        *[
            raw(
                AppleType.OXYGEN_SATURATION,
                number,
                end="2024-01-10T23:00:00-08:00",
                unit="%",
            )
            for number in (1e307, -1e307, 0.96)
        ],
    ]
    result = values(records)
    assert (observed, result) == (
        [
            (
                (Fraction, Fraction(1e307) * 100),
                (Fraction, Fraction(-1e307) * 100),
                (float, 96.0),
            )
        ],
        ((D, {"sleep_s": 14400, "spo2_pct": 32.0}),),
    )


@pytest.mark.parametrize("device", (WATCH, PHONE), ids=("watch", "phone"))
@pytest.mark.parametrize(
    "unstaged",
    (SleepState.ASLEEP_UNSPECIFIED, SleepState.ASLEEP),
    ids=("unspecified", "deprecated"),
)
@pytest.mark.parametrize("reverse", (False, True), ids=("forward", "reverse"))
def test_stage_availability_isolated_between_nights(
    device: str, unstaged: SleepState, reverse: bool
) -> None:
    records = [
        sleep(
            SleepState.CORE,
            "2024-01-10T22:00:00Z",
            "2024-01-11T01:00:00Z",
            device=device,
        ),
        sleep(
            SleepState.AWAKE,
            "2024-01-11T01:00:00Z",
            "2024-01-11T01:30:00Z",
            device=device,
        ),
        sleep(
            unstaged,
            "2024-01-11T22:00:00Z",
            "2024-01-12T00:00:00Z",
            device=device,
        ),
        sleep(
            SleepState.AWAKE,
            "2024-01-12T00:00:00Z",
            "2024-01-12T01:15:00Z",
            device=device,
        ),
    ]
    assert values(reversed(records) if reverse else records) == (
        (
            date(2024, 1, 11),
            {
                "sleep_s": 10800,
                "sleep_deep_s": 0,
                "sleep_light_s": 10800,
                "sleep_rem_s": 0,
                "sleep_awake_s": 1800,
            },
        ),
        (date(2024, 1, 12), {"sleep_s": 7200}),
    )


DISJOINT_NIGHT_MEANS: tuple[
    tuple[AppleType, str, str, tuple[float, float], tuple[float, float], float, float],
    ...,
] = (
    (AppleType.HRV_SDNN, "ms", "hrv_sdnn_ms", (60.0, 62.4), (64.0, 66.8), 61.2, 65.4),
    (
        AppleType.RESPIRATORY_RATE,
        "count/min",
        "respiration_brpm",
        (11.0, 13.4),
        (17.0, 19.8),
        12.2,
        18.4,
    ),
    (
        AppleType.OXYGEN_SATURATION,
        "%",
        "spo2_pct",
        (0.946, 0.958),
        (0.978, 0.99),
        95.2,
        98.4,
    ),
)


@pytest.mark.parametrize(
    "kind,unit,metric,first_numbers,later_numbers,first_mean,later_mean",
    DISJOINT_NIGHT_MEANS,
    ids=("hrv", "respiration", "oxygen"),
)
@pytest.mark.parametrize("later_only", (False, True), ids=("both", "later-only"))
@pytest.mark.parametrize("offsets", (False, True), ids=("utc", "equivalent-offsets"))
@pytest.mark.parametrize("reverse", (False, True), ids=("forward", "reverse"))
def test_disjoint_nights_keep_separate_reading_means(
    kind: AppleType,
    unit: str,
    metric: str,
    first_numbers: tuple[float, float],
    later_numbers: tuple[float, float],
    first_mean: float,
    later_mean: float,
    later_only: bool,
    offsets: bool,
    reverse: bool,
) -> None:
    first_instants, later_instants = (
        (
            ("2024-01-11T07:15:00+09:00", "2024-01-11T08:00:00+09:00"),
            ("2024-01-11T14:15:00-08:00", "2024-01-11T15:00:00-08:00"),
        )
        if offsets
        else (
            ("2024-01-10T22:15:00Z", "2024-01-10T23:00:00Z"),
            ("2024-01-11T22:15:00Z", "2024-01-11T23:00:00Z"),
        )
    )
    records = [
        sleep(start="2024-01-10T22:00:00Z", end="2024-01-11T01:00:00Z"),
        sleep(start="2024-01-11T22:00:00Z", end="2024-01-12T02:00:00Z"),
    ]
    if not later_only:
        records.extend(
            raw(kind, number, instant, instant, unit=unit)
            for number, instant in zip(first_numbers, first_instants, strict=True)
        )
    records.extend(
        raw(kind, number, instant, instant, unit=unit)
        for number, instant in zip(later_numbers, later_instants, strict=True)
    )
    first_values = {"sleep_s": 10800.0}
    if not later_only:
        first_values[metric] = first_mean
    assert values(reversed(records) if reverse else records) == (
        (date(2024, 1, 11), first_values),
        (date(2024, 1, 12), {"sleep_s": 14400, metric: later_mean}),
    )


@pytest.mark.parametrize(
    "kind,unit,metric,first_value,shared_value,later_value,first_mean,later_mean",
    (
        (AppleType.HRV_SDNN, "ms", "hrv_sdnn_ms", 61.2, 65.4, 72.8, 63.3, 72.8),
        (
            AppleType.RESPIRATORY_RATE,
            "count/min",
            "respiration_brpm",
            14.4,
            18.6,
            22.8,
            16.5,
            22.8,
        ),
        (AppleType.OXYGEN_SATURATION, "%", "spo2_pct", 0.94, 0.98, 0.91, 96.0, 91.0),
    ),
    ids=("hrv", "respiration", "oxygen"),
)
@pytest.mark.parametrize("offsets", (False, True), ids=("utc", "equivalent-offsets"))
@pytest.mark.parametrize("reverse", (False, True), ids=("forward", "reverse"))
def test_overlapping_nights_keep_exclusive_and_shared_readings(
    kind: AppleType,
    unit: str,
    metric: str,
    first_value: float,
    shared_value: float,
    later_value: float,
    first_mean: float,
    later_mean: float,
    offsets: bool,
    reverse: bool,
) -> None:
    instants = (
        (
            "2024-01-11T10:30:00+09:00",
            "2024-01-10T18:30:00-08:00",
            "2024-01-11T09:00:00+05:30",
        )
        if offsets
        else (
            "2024-01-11T01:30:00Z",
            "2024-01-11T02:30:00Z",
            "2024-01-11T03:30:00Z",
        )
    )
    records = [
        sleep(start="2024-01-10T13:00:00-12:00", end="2024-01-10T15:00:00-12:00"),
        sleep(start="2024-01-11T16:00:00+14:00", end="2024-01-11T17:59:00+14:00"),
        *[
            raw(kind, number, instant, instant, unit=unit)
            for number, instant in zip(
                (first_value, shared_value, later_value), instants, strict=True
            )
        ],
    ]
    assert values(reversed(records) if reverse else records) == (
        (date(2024, 1, 10), {"sleep_s": 7200, metric: first_mean}),
        (date(2024, 1, 11), {"sleep_s": 7140, metric: later_mean}),
    )


@pytest.mark.parametrize(
    "phone_first", (False, True), ids=("watch-first", "phone-first")
)
@pytest.mark.parametrize("reverse", (False, True), ids=("forward", "reverse"))
@pytest.mark.parametrize(
    "phone_state",
    (SleepState.ASLEEP_UNSPECIFIED, SleepState.ASLEEP, SleepState.CORE),
    ids=("unspecified", "deprecated", "core"),
)
def test_mixed_device_nights_select_independently(
    phone_first: bool, reverse: bool, phone_state: SleepState
) -> None:
    records = [
        sleep(
            phone_state if phone_first else SleepState.ASLEEP_UNSPECIFIED,
            "2024-01-10T22:00:00Z",
            "2024-01-11T01:00:00Z",
            source="Mixed Phone" if phone_first else "Mixed Watch",
            device=PHONE if phone_first else WATCH,
        ),
        sleep(
            SleepState.ASLEEP_UNSPECIFIED if phone_first else phone_state,
            "2024-01-11T22:00:00Z",
            "2024-01-12T02:00:00Z",
            source="Mixed Watch" if phone_first else "Mixed Phone",
            device=WATCH if phone_first else PHONE,
        ),
    ]
    first_values = {"sleep_s": 10800}
    later_values = {"sleep_s": 14400}
    if phone_state == SleepState.CORE:
        phone_values = first_values if phone_first else later_values
        phone_values.update(
            sleep_deep_s=0,
            sleep_light_s=10800 if phone_first else 14400,
            sleep_rem_s=0,
            sleep_awake_s=0,
        )
    assert values(reversed(records) if reverse else records) == (
        (date(2024, 1, 11), first_values),
        (date(2024, 1, 12), later_values),
    )


@pytest.mark.parametrize(
    "kind,unit,metric,number,expected_value",
    (
        (AppleType.HRV_SDNN, "ms", "hrv_sdnn_ms", 61.2, 61.2),
        (AppleType.RESPIRATORY_RATE, "count/min", "respiration_brpm", 14.4, 14.4),
        (AppleType.OXYGEN_SATURATION, "%", "spo2_pct", 0.96, 96.0),
    ),
    ids=("hrv", "respiration", "oxygen"),
)
@pytest.mark.parametrize("included", (False, True), ids=("before-start", "before-end"))
@pytest.mark.parametrize("offsets", (False, True), ids=("utc", "equivalent-offsets"))
@pytest.mark.parametrize("reverse", (False, True), ids=("forward", "reverse"))
def test_fractional_reading_end_preserves_interval_membership(
    kind: AppleType,
    unit: str,
    metric: str,
    number: float,
    expected_value: float,
    included: bool,
    offsets: bool,
    reverse: bool,
) -> None:
    instant = (
        (
            "2024-01-11T07:59:59.900000+09:00"
            if included
            else "2024-01-11T06:59:59.900000+09:00"
        )
        if offsets
        else (
            "2024-01-10T22:59:59.900000Z" if included else "2024-01-10T21:59:59.900000Z"
        )
    )
    records = [
        sleep(start="2024-01-10T22:00:00Z", end="2024-01-10T23:00:00Z"),
        raw(kind, number, instant, instant, unit=unit),
    ]
    expected = {"sleep_s": 3600.0}
    if included:
        expected[metric] = expected_value
    assert values(reversed(records) if reverse else records) == (
        (date(2024, 1, 11), expected),
    )


@pytest.mark.parametrize(
    "state,sleep_values",
    (
        (
            SleepState.CORE,
            {
                "sleep_s": 3600,
                "sleep_deep_s": 0,
                "sleep_light_s": 3600,
                "sleep_rem_s": 0,
                "sleep_awake_s": 0,
            },
        ),
        (
            SleepState.DEEP,
            {
                "sleep_s": 3600,
                "sleep_deep_s": 3600,
                "sleep_light_s": 0,
                "sleep_rem_s": 0,
                "sleep_awake_s": 0,
            },
        ),
        (
            SleepState.REM,
            {
                "sleep_s": 3600,
                "sleep_deep_s": 0,
                "sleep_light_s": 0,
                "sleep_rem_s": 3600,
                "sleep_awake_s": 0,
            },
        ),
        (SleepState.ASLEEP_UNSPECIFIED, {"sleep_s": 1800}),
    ),
    ids=("core", "deep", "rem", "unspecified"),
)
@pytest.mark.parametrize(
    "kind,unit,metric,number,expected_value",
    (
        (AppleType.HRV_SDNN, "ms", "hrv_sdnn_ms", 60.0, 60.0),
        (AppleType.RESPIRATORY_RATE, "count/min", "respiration_brpm", 20.0, 20.0),
        (AppleType.OXYGEN_SATURATION, "%", "spo2_pct", 0.96, 96.0),
    ),
    ids=("hrv", "respiration", "oxygen"),
)
@pytest.mark.parametrize("reverse", (False, True), ids=("forward", "reverse"))
def test_reading_inside_awake_overlap_uses_raw_asleep_union(
    state: SleepState,
    sleep_values: dict[str, float],
    kind: AppleType,
    unit: str,
    metric: str,
    number: float,
    expected_value: float,
    reverse: bool,
) -> None:
    records = [
        sleep(state, "2024-01-10T22:00:00Z", "2024-01-10T23:00:00Z"),
        sleep(SleepState.AWAKE, "2024-01-10T22:15:00Z", "2024-01-10T22:45:00Z"),
        raw(kind, number, "2024-01-10T22:30:00Z", "2024-01-10T22:30:00Z", unit=unit),
    ]
    assert values(reversed(records) if reverse else records) == (
        (date(2024, 1, 11), {**sleep_values, metric: expected_value}),
    )


@pytest.mark.parametrize(
    "kind,unit,metric,positive,expected_mean",
    (
        (AppleType.HRV_SDNN, "ms", "hrv_sdnn_ms", 60.0, 30.0),
        (AppleType.RESPIRATORY_RATE, "count/min", "respiration_brpm", 20.0, 10.0),
        (AppleType.OXYGEN_SATURATION, "%", "spo2_pct", 0.96, 48.0),
    ),
    ids=("hrv", "respiration", "oxygen"),
)
@pytest.mark.parametrize("reverse", (False, True), ids=("forward", "reverse"))
def test_zero_readings_contribute_before_daily_acceptance(
    kind: AppleType,
    unit: str,
    metric: str,
    positive: float,
    expected_mean: float,
    reverse: bool,
) -> None:
    records = [
        sleep(start="2024-01-10T22:00:00Z", end="2024-01-10T23:00:00Z"),
        raw(kind, 0.0, "2024-01-10T22:15:00Z", "2024-01-10T22:15:00Z", unit=unit),
        raw(
            kind,
            positive,
            "2024-01-10T22:30:00Z",
            "2024-01-10T22:30:00Z",
            unit=unit,
        ),
    ]
    assert values(reversed(records) if reverse else records) == (
        (date(2024, 1, 11), {"sleep_s": 3600, metric: expected_mean}),
    )


@pytest.mark.parametrize(
    "kind,unit,metric,first_value,second_value,two_first_mean,two_second_mean",
    (
        (AppleType.HRV_SDNN, "ms", "hrv_sdnn_ms", 60.0, 90.0, 70.0, 80.0),
        (
            AppleType.RESPIRATORY_RATE,
            "count/min",
            "respiration_brpm",
            10.0,
            20.0,
            13.3,
            16.7,
        ),
        (AppleType.OXYGEN_SATURATION, "%", "spo2_pct", 0.90, 0.99, 93.0, 96.0),
    ),
    ids=("hrv", "respiration", "oxygen"),
)
@pytest.mark.parametrize("repeat_first", (True, False), ids=("two-first", "two-second"))
@pytest.mark.parametrize("reverse", (False, True), ids=("forward", "reverse"))
def test_individual_readings_have_equal_weight_across_watch_sources(
    kind: AppleType,
    unit: str,
    metric: str,
    first_value: float,
    second_value: float,
    two_first_mean: float,
    two_second_mean: float,
    repeat_first: bool,
    reverse: bool,
) -> None:
    records = [
        sleep(start="2024-01-10T22:00:00Z", end="2024-01-10T23:00:00Z"),
        raw(
            kind,
            first_value,
            "2024-01-10T22:15:00Z",
            "2024-01-10T22:15:00Z",
            source="First Reading Watch",
            unit=unit,
        ),
        raw(
            kind,
            second_value,
            "2024-01-10T22:30:00Z",
            "2024-01-10T22:30:00Z",
            source="Second Reading Watch",
            unit=unit,
        ),
        raw(
            kind,
            first_value if repeat_first else second_value,
            "2024-01-10T22:45:00Z",
            "2024-01-10T22:45:00Z",
            source="First Reading Watch" if repeat_first else "Second Reading Watch",
            unit=unit,
        ),
    ]
    expected = two_first_mean if repeat_first else two_second_mean
    assert values(reversed(records) if reverse else records) == (
        (date(2024, 1, 11), {"sleep_s": 3600, metric: expected}),
    )


@pytest.mark.parametrize(
    "kind,unit,number,expected",
    (
        (AppleType.HRV_SDNN, "ms", 60.0, {"sleep_s": 3600, "hrv_sdnn_ms": 60}),
        (
            AppleType.RESPIRATORY_RATE,
            "count/min",
            10.0,
            {"sleep_s": 3600, "respiration_brpm": 10},
        ),
        (AppleType.OXYGEN_SATURATION, "%", 0.90, {"sleep_s": 3600, "spo2_pct": 90}),
    ),
    ids=("hrv", "respiration", "oxygen"),
)
@pytest.mark.parametrize(
    "creation",
    ("2024-01-10T23:15:00Z", "2024-01-11T02:00:00Z"),
    ids=("written-same-day", "written-next-day"),
)
@pytest.mark.parametrize("reverse", (False, True), ids=("forward", "reverse"))
def test_reading_end_locates_reading_with_delayed_creation(
    kind: AppleType,
    unit: str,
    number: float,
    expected: dict[str, float],
    creation: str,
    reverse: bool,
) -> None:
    from dataclasses import replace

    reading = replace(
        raw(kind, number, "2024-01-10T22:15:00Z", "2024-01-10T22:30:00Z", unit=unit),
        creation_date=creation,
    )
    records = [
        sleep(start="2024-01-10T22:00:00Z", end="2024-01-10T23:00:00Z"),
        reading,
    ]
    assert values(reversed(records) if reverse else records) == (
        (date(2024, 1, 11), expected),
    )


@pytest.mark.parametrize(
    "kind,unit,first_value,second_value,two_first,two_second",
    (
        (
            AppleType.HRV_SDNN,
            "ms",
            60.0,
            90.0,
            {"sleep_s": 7200, "hrv_sdnn_ms": 70},
            {"sleep_s": 7200, "hrv_sdnn_ms": 80},
        ),
        (
            AppleType.RESPIRATORY_RATE,
            "count/min",
            10.0,
            20.0,
            {"sleep_s": 7200, "respiration_brpm": 13.3},
            {"sleep_s": 7200, "respiration_brpm": 16.7},
        ),
        (
            AppleType.OXYGEN_SATURATION,
            "%",
            0.90,
            0.99,
            {"sleep_s": 7200, "spo2_pct": 93},
            {"sleep_s": 7200, "spo2_pct": 96},
        ),
    ),
    ids=("hrv", "respiration", "oxygen"),
)
@pytest.mark.parametrize(
    "repeat_first", (True, False), ids=("two-first-bout", "two-last-bout")
)
@pytest.mark.parametrize("reverse", (False, True), ids=("forward", "reverse"))
def test_individual_readings_have_equal_weight_across_asleep_bouts(
    kind: AppleType,
    unit: str,
    first_value: float,
    second_value: float,
    two_first: dict[str, float],
    two_second: dict[str, float],
    repeat_first: bool,
    reverse: bool,
) -> None:
    repeated_end = "2024-01-10T22:30:00Z" if repeat_first else "2024-01-11T01:30:00Z"
    records = [
        sleep(start="2024-01-10T22:00:00Z", end="2024-01-10T23:00:00Z"),
        sleep(start="2024-01-11T01:00:00Z", end="2024-01-11T02:00:00Z"),
        raw(
            kind,
            first_value,
            "2024-01-10T22:15:00Z",
            "2024-01-10T22:15:00Z",
            unit=unit,
        ),
        raw(
            kind,
            second_value,
            "2024-01-11T01:15:00Z",
            "2024-01-11T01:15:00Z",
            unit=unit,
        ),
        raw(
            kind,
            first_value if repeat_first else second_value,
            repeated_end,
            repeated_end,
            unit=unit,
        ),
    ]
    assert values(reversed(records) if reverse else records) == (
        (date(2024, 1, 11), two_first if repeat_first else two_second),
    )
