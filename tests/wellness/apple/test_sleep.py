"""Sleep sweep, stage totals and asleep unions."""

from __future__ import annotations

from dataclasses import MISSING, FrozenInstanceError, astuple, fields
from enum import IntEnum
from itertools import combinations

import pytest

from fitdocs.wellness.formats.apple import sleep


def test_stage_members() -> None:
    assert {name: member.value for name, member in sleep.Stage.__members__.items()} == {
        "UNSPECIFIED": 1,
        "AWAKE": 2,
        "CORE": 3,
        "REM": 4,
        "DEEP": 5,
    }


def test_stage_is_integer_enum() -> None:
    assert issubclass(sleep.Stage, IntEnum)


@pytest.mark.parametrize(
    "name, expected",
    [
        ("Segment", (("start", "int"), ("end", "int"), ("stage", "Stage"))),
        (
            "NightTotals",
            (
                ("deep", "int"),
                ("core", "int"),
                ("rem", "int"),
                ("awake", "int"),
                ("unspecified", "int"),
            ),
        ),
    ],
)
def test_carrier_fields(name: str, expected: tuple[tuple[str, str], ...]) -> None:
    cls = getattr(sleep, name)
    assert tuple((field.name, field.type) for field in fields(cls)) == expected


@pytest.mark.parametrize("name", ["Segment", "NightTotals"])
def test_carrier_constructor_contract(name: str) -> None:
    cls = getattr(sleep, name)
    assert tuple(
        (field.default, field.default_factory, field.kw_only) for field in fields(cls)
    ) == ((MISSING, MISSING, False),) * len(fields(cls))


@pytest.mark.parametrize(
    "name, arguments, missing",
    [
        *(
            pytest.param(
                "Segment",
                {"start": -109, "end": 233, "stage": sleep.Stage.REM},
                missing,
                id=f"Segment-{missing}",
            )
            for missing in ("start", "end", "stage")
        ),
        *(
            pytest.param(
                "NightTotals",
                {"deep": 11, "core": 17, "rem": 23, "awake": 31, "unspecified": 43},
                missing,
                id=f"NightTotals-{missing}",
            )
            for missing in ("deep", "core", "rem", "awake", "unspecified")
        ),
    ],
)
def test_carrier_argument_is_required(
    name: str, arguments: dict[str, object], missing: str
) -> None:
    supplied = {key: value for key, value in arguments.items() if key != missing}
    with pytest.raises(TypeError, match=f"'{missing}'"):
        getattr(sleep, name)(**supplied)


@pytest.mark.parametrize(
    "name, arguments",
    [
        ("Segment", {"start": -109, "end": 233, "stage": sleep.Stage.REM}),
        (
            "NightTotals",
            {"deep": 11, "core": 17, "rem": 23, "awake": 31, "unspecified": 43},
        ),
    ],
)
def test_carrier_is_frozen(name: str, arguments: dict[str, object]) -> None:
    instance = getattr(sleep, name)(**arguments)
    with pytest.raises(FrozenInstanceError):
        setattr(instance, next(iter(arguments)), 999)


@pytest.mark.parametrize(
    "name, arguments, expected",
    [
        (
            "Segment",
            {"start": -109, "end": 233, "stage": sleep.Stage.REM},
            (-109, 233, sleep.Stage.REM),
        ),
        (
            "NightTotals",
            {"deep": 11, "core": 17, "rem": 23, "awake": 31, "unspecified": 43},
            (11, 17, 23, 31, 43),
        ),
    ],
)
def test_carrier_stores_arguments(
    name: str, arguments: dict[str, object], expected: tuple[object, ...]
) -> None:
    assert astuple(getattr(sleep, name)(**arguments)) == expected


@pytest.mark.parametrize(
    "arguments, expected",
    [
        ((11, 17, 23, 31, 43), 94),
        ((0, 0, 0, 59, 0), 0),
    ],
)
def test_asleep_property(arguments: tuple[int, ...], expected: int) -> None:
    assert sleep.NightTotals(*arguments).asleep == expected


@pytest.mark.parametrize(
    "arguments, expected",
    [
        ((11, 0, 0, 0, 0), True),
        ((0, 17, 0, 0, 0), True),
        ((0, 0, 23, 0, 0), True),
        ((0, 0, 0, 31, 0), False),
        ((0, 0, 0, 0, 43), False),
        ((0, 0, 0, 0, 0), False),
    ],
    ids=["deep", "core", "rem", "awake", "unspecified", "empty"],
)
def test_staged_property(arguments: tuple[int, ...], expected: bool) -> None:
    assert sleep.NightTotals(*arguments).staged is expected


@pytest.mark.parametrize("stage", list(sleep.Stage), ids=lambda stage: stage.name)
def test_same_stage_overlap(stage: sleep.Stage) -> None:
    segments = [sleep.Segment(141, 198, stage), sleep.Segment(103, 167, stage)]
    expected = dict.fromkeys(sleep.Stage, 0)
    expected[stage] = 95
    assert astuple(sleep.night_totals(segments)) == (
        expected[sleep.Stage.DEEP],
        expected[sleep.Stage.CORE],
        expected[sleep.Stage.REM],
        expected[sleep.Stage.AWAKE],
        expected[sleep.Stage.UNSPECIFIED],
    )


@pytest.mark.parametrize(
    "lower, higher, geometry",
    [
        (lower, higher, geometry)
        for lower, higher in combinations(sleep.Stage, 2)
        for geometry in ("nested", "partial")
    ],
    ids=[
        f"{lower.name}-{higher.name}-{geometry}"
        for lower, higher in combinations(sleep.Stage, 2)
        for geometry in ("nested", "partial")
    ],
)
def test_stage_priority(lower: sleep.Stage, higher: sleep.Stage, geometry: str) -> None:
    expected = dict.fromkeys(sleep.Stage, 0)
    if geometry == "nested":
        segments = [sleep.Segment(101, 190, lower), sleep.Segment(112, 149, higher)]
        expected[lower] = 52
        expected[higher] = 37
    else:
        segments = [sleep.Segment(149, 211, lower), sleep.Segment(101, 190, higher)]
        expected[lower] = 21
        expected[higher] = 89
    assert astuple(sleep.night_totals(segments)) == (
        expected[sleep.Stage.DEEP],
        expected[sleep.Stage.CORE],
        expected[sleep.Stage.REM],
        expected[sleep.Stage.AWAKE],
        expected[sleep.Stage.UNSPECIFIED],
    )


def test_deep_inside_core() -> None:
    assert sleep.night_totals(
        [
            sleep.Segment(101, 190, sleep.Stage.CORE),
            sleep.Segment(112, 149, sleep.Stage.DEEP),
        ]
    ) == sleep.NightTotals(37, 52, 0, 0, 0)


def test_disjoint_stage_mapping() -> None:
    assert sleep.night_totals(
        [
            sleep.Segment(400, 431, sleep.Stage.AWAKE),
            sleep.Segment(-100, -83, sleep.Stage.CORE),
            sleep.Segment(200, 243, sleep.Stage.UNSPECIFIED),
            sleep.Segment(500, 511, sleep.Stage.DEEP),
            sleep.Segment(50, 73, sleep.Stage.REM),
        ]
    ) == sleep.NightTotals(11, 17, 23, 31, 43)


@pytest.mark.parametrize("order", [(4, 1, 3, 0, 2), (2, 0, 4, 3, 1), (1, 3, 2, 4, 0)])
def test_shuffled_boundary_sweep(order: tuple[int, ...]) -> None:
    segments = (
        sleep.Segment(0, 200, sleep.Stage.UNSPECIFIED),
        sleep.Segment(11, 160, sleep.Stage.AWAKE),
        sleep.Segment(29, 140, sleep.Stage.CORE),
        sleep.Segment(47, 119, sleep.Stage.REM),
        sleep.Segment(61, 104, sleep.Stage.DEEP),
    )
    assert sleep.night_totals(segments[index] for index in order) == sleep.NightTotals(
        43, 39, 29, 38, 51
    )


def test_totals_touching_half_open_boundaries() -> None:
    assert sleep.night_totals(
        [
            sleep.Segment(11, 28, sleep.Stage.CORE),
            sleep.Segment(0, 11, sleep.Stage.DEEP),
            sleep.Segment(28, 51, sleep.Stage.REM),
        ]
    ) == sleep.NightTotals(11, 17, 23, 0, 0)


@pytest.mark.parametrize("stage", list(sleep.Stage), ids=lambda stage: stage.name)
def test_zero_length_totals(stage: sleep.Stage) -> None:
    assert sleep.night_totals(
        [sleep.Segment(31, 31, stage), sleep.Segment(10, 27, sleep.Stage.CORE)]
    ) == sleep.NightTotals(0, 17, 0, 0, 0)


def test_empty_totals() -> None:
    assert sleep.night_totals(iter(())) == sleep.NightTotals(0, 0, 0, 0, 0)


@pytest.mark.parametrize(
    "stage",
    [sleep.Stage.DEEP, sleep.Stage.REM, sleep.Stage.CORE, sleep.Stage.UNSPECIFIED],
    ids=lambda stage: stage.name,
)
def test_asleep_stage_is_in_union(stage: sleep.Stage) -> None:
    assert sleep.asleep_intervals([sleep.Segment(-109, -66, stage)]) == ((-109, -66),)


def test_awake_is_excluded_from_union() -> None:
    assert sleep.asleep_intervals(
        [
            sleep.Segment(101, 144, sleep.Stage.AWAKE),
            sleep.Segment(5, 22, sleep.Stage.REM),
        ]
    ) == ((5, 22),)


def test_asleep_union_sorted_merged_and_half_open() -> None:
    segments = [
        sleep.Segment(151, 182, sleep.Stage.REM),
        sleep.Segment(41, 73, sleep.Stage.UNSPECIFIED),
        sleep.Segment(29, 41, sleep.Stage.DEEP),
        sleep.Segment(97, 120, sleep.Stage.CORE),
        sleep.Segment(11, 35, sleep.Stage.CORE),
        sleep.Segment(13, 19, sleep.Stage.REM),
        sleep.Segment(120, 137, sleep.Stage.DEEP),
    ]
    assert sleep.asleep_intervals(segment for segment in segments) == (
        (11, 73),
        (97, 137),
        (151, 182),
    )


@pytest.mark.parametrize("stage", list(sleep.Stage), ids=lambda stage: stage.name)
def test_zero_length_union(stage: sleep.Stage) -> None:
    assert sleep.asleep_intervals(
        [sleep.Segment(73, 73, stage), sleep.Segment(11, 28, sleep.Stage.REM)]
    ) == ((11, 28),)


def test_empty_union() -> None:
    assert sleep.asleep_intervals(iter(())) == ()
