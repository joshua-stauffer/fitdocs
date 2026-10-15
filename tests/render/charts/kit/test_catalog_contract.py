"""Contract pins for the chart-catalog spec's appended values (tasks 1.1, 3.1).

Task 1.1: the four appended `ProblemCode` members are pinned by value, by
relative order and by their position after chart-kit's 23 codes; those
positions are compared by index rather than by slice.

Task 3.1: the eight catalog kinds are pinned as a prefix of the registry after
the eight core kinds (no total count), with two listing literals and the
`validate_chart` pins that need the kinds registered.
"""

from __future__ import annotations

from fitdocs.render.charts.kit.api import validate_chart
from fitdocs.render.charts.kit.problems import ProblemCode
from fitdocs.render.charts.kit.registry import (
    CORE_KIND_NAMES,
    describe_kinds,
    kind_names,
)
from tests.render.charts.kit._helpers import chart_request, column

_CATALOG_CODES: tuple[tuple[str, str], ...] = (
    ("NEGATIVE_VALUE", "negative_value"),
    ("VALUE_ORDER", "value_order"),
    ("SHARED_UNIT", "shared_unit"),
    ("CHANNEL_UNIT", "channel_unit"),
)

_CORE_CODE_COUNT = 23


def _index(name: str) -> int:
    return list(ProblemCode).index(ProblemCode[name])


def test_the_four_codes_are_members_with_their_stable_values() -> None:
    for name, value in _CATALOG_CODES:
        assert ProblemCode[name].value == value
        assert ProblemCode(value) is ProblemCode[name]


def test_the_four_codes_keep_their_relative_order() -> None:
    indexes = [_index(name) for name, _ in _CATALOG_CODES]
    assert indexes == sorted(indexes)
    assert len(set(indexes)) == 4


def test_the_four_codes_all_come_after_chart_kits_twenty_three() -> None:
    last_core = _index("STACK_INCOMPLETE")
    assert last_core == _CORE_CODE_COUNT - 1
    for name, _ in _CATALOG_CODES:
        assert _index(name) > last_core, name


def test_nothing_was_inserted_in_front_of_the_first_catalog_code() -> None:
    # Exactly 23 members precede it, so nothing sits between chart-kit's codes
    # and the catalog's first.
    first = _index("NEGATIVE_VALUE")
    assert first == _CORE_CODE_COUNT


# --- registration (task 3.1) -------------------------------------------------

CATALOG_KIND_NAMES = (
    "calendar-heatmap",
    "heatmap",
    "dual-axis",
    "band",
    "box",
    "mean-max",
    "small-multiples",
    "stacked-100",
)


def test_the_catalog_kinds_follow_the_core_kinds_in_requirement_order() -> None:
    assert kind_names()[:16] == (*CORE_KIND_NAMES, *CATALOG_KIND_NAMES)
    assert len(CORE_KIND_NAMES) == 8


def test_no_pie_donut_or_map_kind_is_registered() -> None:
    for name in ("pie", "donut", "map"):
        assert name not in kind_names()


def test_an_unknown_kind_lists_the_core_then_the_catalog_names() -> None:
    problems = validate_chart(chart_request("zz-not-a-kind", title="T"), [column("v")])
    assert [p.code for p in problems] == [ProblemCode.UNKNOWN_KIND]
    assert problems[0].accepted[:16] == (*CORE_KIND_NAMES, *CATALOG_KIND_NAMES)


def _listing(name: str) -> dict[str, object]:
    (found,) = (d for d in describe_kinds() if d["name"] == name)
    return dict(found)


def _width() -> dict[str, object]:
    return {
        "name": "width",
        "type": "integer",
        "default": 720,
        "choices": [],
        "minimum": 320,
        "maximum": 1600,
        "description": "Chart width in pixels.",
    }


def _bool_option(name: str, description: str) -> dict[str, object]:
    return {
        "name": name,
        "type": "boolean",
        "default": False,
        "choices": [],
        "minimum": None,
        "maximum": None,
        "description": description,
    }


def test_the_calendar_heatmap_listing_is_this_literal() -> None:
    assert _listing("calendar-heatmap") == {
        "name": "calendar-heatmap",
        "description": (
            "One cell per day in Monday-start week columns, sized and shaded by "
            "a value of zero or more (negative values are refused); a day with "
            "no row draws nothing, so return a zero row to show a rest day"
        ),
        "output": "svg",
        "channels": [
            {
                "name": "date",
                "required": True,
                "accepts": ["date"],
                "description": "The day of each row; one row per day.",
            },
            {
                "name": "value",
                "required": True,
                "accepts": ["number", "duration"],
                "description": "The amount shown for the day, zero or more.",
            },
        ],
        "options": [
            _width(),
            {
                "name": "height",
                "type": "integer",
                "default": None,
                "choices": [],
                "minimum": 160,
                "maximum": 1200,
                "description": "Chart height in pixels.",
            },
        ],
        "bound": {
            "limit": 54,
            "counts": "weeks",
            "over": "refuse",
            "rule": (
                "At most 54 Monday-start week columns: any 366 consecutive days fit."
            ),
        },
        "max_series": None,
    }


def test_the_dual_axis_listing_is_this_literal() -> None:
    assert _listing("dual-axis") == {
        "name": "dual-axis",
        "description": (
            "Two series over one x, each on its own y axis with its own unit; "
            "unless the two are a deliberate pair, prefer small-multiples or "
            "one line with a colour column"
        ),
        "output": "svg",
        "channels": [
            {
                "name": "x",
                "required": True,
                "accepts": ["number", "duration", "date", "datetime"],
                "description": (
                    "The horizontal position: a number, duration, date or date-time."
                ),
            },
            {
                "name": "y",
                "required": True,
                "accepts": ["number", "duration"],
                "description": (
                    "The value drawn solid against the left axis: a number or duration."
                ),
            },
            {
                "name": "y2",
                "required": True,
                "accepts": ["number", "duration"],
                "description": (
                    "The value drawn dashed against the right axis, in another "
                    "unit than y: a number or duration."
                ),
            },
        ],
        "options": [
            _bool_option("y_zero", "Extend the left axis to include zero."),
            _bool_option("y2_zero", "Extend the right axis to include zero."),
            _width(),
            {
                "name": "height",
                "type": "integer",
                "default": 320,
                "choices": [],
                "minimum": 160,
                "maximum": 1200,
                "description": "Chart height in pixels.",
            },
        ],
        "bound": {
            "limit": 2000,
            "counts": "rows",
            "over": "refuse",
            "rule": "At most 2000 rows; more are refused.",
        },
        "max_series": None,
    }


def test_validate_chart_reports_dual_axis_shared_unit_without_rows() -> None:
    columns = (
        column("n"),
        column("a_bpm", unit="bpm"),
        column("max_bpm", unit="bpm"),
    )
    request = chart_request(
        "dual-axis",
        ref="d1",
        channels={"x": "n", "y": "a_bpm", "y2": "max_bpm"},
    )
    (problem,) = validate_chart(request, columns)
    assert problem.code is ProblemCode.SHARED_UNIT
    assert problem.kind == "dual-axis"
    assert problem.channel == "y2" and problem.column == "max_bpm"
    ok = chart_request(
        "dual-axis", ref="d1", channels={"x": "n", "y": "a_bpm", "y2": "n"}
    )
    assert validate_chart(ok, columns) == ()


def test_validate_chart_reports_mean_max_channel_unit_without_rows() -> None:
    columns = (
        column("distance_m", unit="m"),
        column("power_w", unit="w"),
        column("elapsed_s", unit="s"),
    )
    request = chart_request(
        "mean-max", ref="m1", channels={"x": "distance_m", "y": "power_w"}
    )
    (problem,) = validate_chart(request, columns)
    assert problem.code is ProblemCode.CHANNEL_UNIT
    assert problem.kind == "mean-max"
    assert problem.channel == "x" and problem.column == "distance_m"
    assert problem.accepted == ("elapsed_s",)
    ok = chart_request(
        "mean-max", ref="m1", channels={"x": "elapsed_s", "y": "power_w"}
    )
    assert validate_chart(ok, columns) == ()


# --- reference-band (recovery task 2.2) ---------------------------------------


def test_reference_band_follows_the_existing_registry_prefix() -> None:
    assert kind_names()[15:17] == ("stacked-100", "reference-band")


def test_the_reference_band_listing_is_this_literal_json() -> None:
    import json

    expected = {
        "name": "reference-band",
        "description": (
            "Values as points against a segmented reference band, "
            "with optional centre line and flags."
        ),
        "output": "svg",
        "channels": [
            {
                "name": "x",
                "required": True,
                "accepts": ["number", "duration", "date", "datetime"],
                "description": "Horizontal position.",
            },
            {
                "name": "y",
                "required": True,
                "accepts": ["number", "duration"],
                "description": "Values as points.",
            },
            {
                "name": "low",
                "required": False,
                "accepts": ["number", "duration"],
                "description": "Lower band edge.",
            },
            {
                "name": "high",
                "required": False,
                "accepts": ["number", "duration"],
                "description": "Upper band edge.",
            },
            {
                "name": "mid",
                "required": False,
                "accepts": ["number", "duration"],
                "description": "Centre line.",
            },
            {
                "name": "segment",
                "required": False,
                "accepts": ["category"],
                "description": "Separate source segments.",
            },
            {
                "name": "flag",
                "required": False,
                "accepts": ["boolean"],
                "description": "Rows marked along the bottom axis.",
            },
        ],
        "options": [
            {
                "name": "y_zero",
                "type": "boolean",
                "default": False,
                "choices": [],
                "minimum": None,
                "maximum": None,
                "description": "Extend the y axis to include zero.",
            },
            {
                "name": "width",
                "type": "integer",
                "default": 720,
                "choices": [],
                "minimum": 320,
                "maximum": 1600,
                "description": "Chart width in pixels.",
            },
            {
                "name": "height",
                "type": "integer",
                "default": 320,
                "choices": [],
                "minimum": 160,
                "maximum": 1200,
                "description": "Chart height in pixels.",
            },
        ],
        "bound": {
            "limit": 1000,
            "counts": "rows",
            "over": "refuse",
            "rule": "At most 1000 rows; more are refused.",
        },
        "max_series": 8,
    }
    assert json.dumps(describe_kinds()[16], sort_keys=True) == json.dumps(
        expected, sort_keys=True
    )
