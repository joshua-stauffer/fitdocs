"""The declared registry: order, name rules, listing, and the registry render path.

Requirements 3.3, 5.1, 5.2, 5.3, 5.4, 5.5, 5.6.

The kind-name pin is on the first eight names only; later entries are free.
"""

from __future__ import annotations

import importlib
import json
import re
from dataclasses import replace
from typing import Any

import pytest

from fitdocs.render.charts.kit import registry
from fitdocs.render.charts.kit.api import render_chart, validate_chart
from fitdocs.render.charts.kit.data import ValueKind
from fitdocs.render.charts.kit.problems import ChartError, ProblemCode
from fitdocs.render.charts.kit.registry import (
    CORE_KIND_NAMES,
    KINDS,
    describe_kinds,
    kind_named,
    kind_names,
)
from fitdocs.render.charts.kit.schema import (
    ChannelSpec,
    KindSpec,
    MarkBound,
    OptionSpec,
    OptionType,
    Output,
    OverBound,
)
from fitdocs.render.charts.kit.theme import MAX_SERIES
from fitdocs.render.charts.kit.validate import parse_option
from tests.render.charts.kit._helpers import (
    Case,
    chart_data,
    chart_request,
    column,
)
from tests.render.charts.kit.goldens import assert_golden, golden_path

KIND_NAME = re.compile(r"[a-z][a-z0-9]*(-[a-z0-9]+)*")
FIELD_NAME = re.compile(r"[a-z][a-z0-9]*(_[a-z0-9]+)*")


# --- the invariant check, applied to the registry and to local specs ----------


def _draw(_: object) -> str:
    return ""


def _violations(spec: KindSpec) -> list[str]:
    """Every registry invariant ``spec`` breaks, as short sentences."""
    found: list[str] = []
    if not KIND_NAME.fullmatch(spec.name):
        found.append(f"kind name {spec.name!r} is not lowercase hyphen-separated")
    channel_names = [c.name for c in spec.channels]
    option_names = [o.name for o in spec.options]
    for name in channel_names:
        if not FIELD_NAME.fullmatch(name):
            found.append(f"channel name {name!r} is not lowercase snake_case")
    for name in option_names:
        if not FIELD_NAME.fullmatch(name):
            found.append(f"option name {name!r} is not lowercase snake_case")
    if len(set(channel_names)) != len(channel_names):
        found.append("channel names repeat")
    if len(set(option_names)) != len(option_names):
        found.append("option names repeat")
    for name in sorted(set(channel_names) & set(option_names)):
        found.append(f"{name!r} names both a channel and an option")
    for option in spec.options:
        default = option.default
        if default is None:
            if option.type in (OptionType.BOOLEAN, OptionType.CHOICE):
                found.append(f"option {option.name!r} has no default")
        elif parse_option(option, default) != default or type(
            parse_option(option, default)
        ) is not type(default):
            found.append(f"option {option.name!r} default {default!r} is invalid")
    tail = option_names[-2:]
    if spec.output is Output.SVG:
        if tail != ["width", "height"]:
            found.append("an SVG kind's options must end with width, height")
    elif "width" in option_names or "height" in option_names:
        found.append("a markdown kind must have neither width nor height")
    if spec.max_series is not None and spec.max_series > MAX_SERIES:
        found.append(f"max_series {spec.max_series} exceeds {MAX_SERIES}")
    return found


def _local(
    *,
    name: str = "local",
    output: Output = Output.MARKDOWN,
    channels: tuple[ChannelSpec, ...] = (),
    options: tuple[OptionSpec, ...] = (),
    max_series: int | None = None,
) -> KindSpec:
    return KindSpec(
        name=name,
        description="A local kind.",
        output=output,
        channels=channels,
        options=options,
        bound=MarkBound(1, "rows", OverBound.REFUSE, "One row."),
        max_series=max_series,
        draw=_draw,
    )


def _channel(name: str) -> ChannelSpec:
    return ChannelSpec(name, (ValueKind.NUMBER,), True, "A channel.")


def _flag(name: str, default: bool | None = False) -> OptionSpec:
    return OptionSpec(name, OptionType.BOOLEAN, "A flag.", default)


def _width_height(width: int = 720) -> tuple[OptionSpec, ...]:
    return (
        OptionSpec("width", OptionType.INTEGER, "w", width, minimum=320, maximum=1600),
        OptionSpec("height", OptionType.INTEGER, "h", None, minimum=160, maximum=1200),
    )


# --- order and names (5.2, 5.3, 5.4) ------------------------------------------


def test_core_kinds_are_registered_in_the_designed_order() -> None:
    assert kind_names()[:8] == CORE_KIND_NAMES
    assert kind_names()[:8] == (
        "line",
        "area",
        "bar",
        "hbar",
        "scatter",
        "histogram",
        "stat",
        "table",
    )
    assert len(KINDS) >= 8


def test_kinds_are_the_declared_kind_modules_objects() -> None:
    for position, name in enumerate(CORE_KIND_NAMES):
        module = importlib.import_module(f"fitdocs.render.charts.kit.kinds.{name}")
        assert KINDS[position] is module.KIND
        assert kind_named(name) is module.KIND


def test_registered_names_are_unique() -> None:
    assert len(set(kind_names())) == len(KINDS) >= 8


def test_every_registered_kind_obeys_the_invariants() -> None:
    assert len(KINDS) >= 8
    for spec in KINDS:
        assert _violations(spec) == [], spec.name


def test_output_split_over_the_core_kinds() -> None:
    outputs = {spec.name: spec.output for spec in KINDS[:8]}
    assert outputs == {
        "line": Output.SVG,
        "area": Output.SVG,
        "bar": Output.SVG,
        "hbar": Output.SVG,
        "scatter": Output.SVG,
        "histogram": Output.SVG,
        "stat": Output.MARKDOWN,
        "table": Output.MARKDOWN,
    }


def test_only_the_table_kind_takes_every_column() -> None:
    assert {spec.name: spec.uses_all_columns for spec in KINDS[:8]} == {
        "line": False,
        "area": False,
        "bar": False,
        "hbar": False,
        "scatter": False,
        "histogram": False,
        "stat": False,
        "table": True,
    }


# --- the invariant check can fail (controls) ----------------------------------


def test_a_clean_local_spec_has_no_violations() -> None:
    clean = _local(
        output=Output.SVG,
        channels=(_channel("x"), _channel("y_value")),
        options=(_flag("y_zero"), *_width_height()),
        max_series=MAX_SERIES,
    )
    assert _violations(clean) == []
    assert (
        _violations(_local(channels=(_channel("value"),), options=(_flag("d"),))) == []
    )


@pytest.mark.parametrize(
    ("spec", "expected"),
    [
        (
            _local(name="Bad_Name"),
            ["kind name 'Bad_Name' is not lowercase hyphen-separated"],
        ),
        (
            _local(channels=(_channel("x"), _channel("x"))),
            ["channel names repeat"],
        ),
        (
            _local(options=(_flag("a"), _flag("a"))),
            ["option names repeat"],
        ),
        (
            _local(channels=(_channel("rows"),), options=(_flag("rows"),)),
            ["'rows' names both a channel and an option"],
        ),
        (
            _local(channels=(_channel("Rows-1"),)),
            ["channel name 'Rows-1' is not lowercase snake_case"],
        ),
        (
            _local(options=(_flag("Is-On"),)),
            ["option name 'Is-On' is not lowercase snake_case"],
        ),
        (
            _local(
                options=(
                    OptionSpec(
                        "limit",
                        OptionType.INTEGER,
                        "n",
                        5000,
                        minimum=1,
                        maximum=100,
                    ),
                )
            ),
            ["option 'limit' default 5000 is invalid"],
        ),
        (
            _local(
                options=(
                    OptionSpec(
                        "mode",
                        OptionType.CHOICE,
                        "m",
                        "c",
                        choices=("a", "b"),
                    ),
                )
            ),
            ["option 'mode' default 'c' is invalid"],
        ),
        (
            _local(options=(_flag("on", None),)),
            ["option 'on' has no default"],
        ),
        (
            _local(
                output=Output.SVG,
                options=(*_width_height()[::-1],),
            ),
            ["an SVG kind's options must end with width, height"],
        ),
        (
            _local(output=Output.SVG, options=_width_height()[:1]),
            ["an SVG kind's options must end with width, height"],
        ),
        (
            _local(options=_width_height()),
            ["a markdown kind must have neither width nor height"],
        ),
        (
            _local(max_series=MAX_SERIES + 1),
            [f"max_series {MAX_SERIES + 1} exceeds {MAX_SERIES}"],
        ),
    ],
)
def test_the_invariant_check_reports_each_violation(
    spec: KindSpec, expected: list[str]
) -> None:
    assert _violations(spec) == expected


def test_a_default_of_the_wrong_type_is_a_violation() -> None:
    spec = _local(
        options=(OptionSpec("limit", OptionType.INTEGER, "n", True, minimum=0),)
    )
    assert _violations(spec) == ["option 'limit' default True is invalid"]


# --- the machine-readable listing (5.5) ---------------------------------------


LINE_LISTING: dict[str, Any] = {
    "name": "line",
    "description": "Lines over a numeric or time x, one per colour value",
    "output": "svg",
    "channels": [
        {
            "name": "x",
            "required": True,
            "accepts": ["number", "duration", "date", "datetime"],
            "description": "The horizontal position: a number, duration, date or "
            "date-time.",
        },
        {
            "name": "y",
            "required": True,
            "accepts": ["number", "duration"],
            "description": "The vertical value: a number or duration.",
        },
        {
            "name": "color",
            "required": False,
            "accepts": ["category", "boolean"],
            "description": "One line per value of this column.",
        },
    ],
    "options": [
        {
            "name": "x_scale",
            "type": "choice",
            "default": "linear",
            "choices": ["linear", "log"],
            "minimum": None,
            "maximum": None,
            "description": "The x axis scale; log needs a number or duration x.",
        },
        {
            "name": "y_scale",
            "type": "choice",
            "default": "linear",
            "choices": ["linear", "log"],
            "minimum": None,
            "maximum": None,
            "description": "The y axis scale; log needs values above zero.",
        },
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
        "limit": 2000,
        "counts": "rows",
        "over": "refuse",
        "rule": "At most 2000 rows; more are refused.",
    },
    "max_series": 8,
}

STAT_LISTING: dict[str, Any] = {
    "name": "stat",
    "description": "One headline value with its unit and an optional change",
    "output": "markdown",
    "channels": [
        {
            "name": "value",
            "required": True,
            "accepts": [
                "number",
                "date",
                "datetime",
                "duration",
                "category",
                "boolean",
            ],
            "description": "The headline value.",
        },
        {
            "name": "compare",
            "required": False,
            "accepts": ["number", "duration"],
            "description": "The value to compare against, of the same kind and unit.",
        },
    ],
    "options": [
        {
            "name": "delta",
            "type": "choice",
            "default": "absolute",
            "choices": ["absolute", "percent", "both"],
            "minimum": None,
            "maximum": None,
            "description": "How the change from the comparison is shown.",
        }
    ],
    "bound": {
        "limit": 1,
        "counts": "rows",
        "over": "refuse",
        "rule": "A stat shows one row; more are refused.",
    },
    "max_series": None,
}


def test_describe_kinds_is_in_registration_order() -> None:
    listings = describe_kinds()
    assert [entry["name"] for entry in listings] == list(kind_names())
    assert [entry["name"] for entry in listings[:8]] == list(CORE_KIND_NAMES)


def test_line_listing_field_by_field() -> None:
    listing = describe_kinds()[0]
    assert dict(listing) == LINE_LISTING
    assert list(listing) == list(LINE_LISTING)
    assert [list(c) for c in listing["channels"]] == [
        ["name", "required", "accepts", "description"]
    ] * 3
    assert [list(o) for o in listing["options"]] == [
        ["name", "type", "default", "choices", "minimum", "maximum", "description"]
    ] * 5
    assert list(listing["bound"]) == ["limit", "counts", "over", "rule"]


def test_stat_listing_field_by_field() -> None:
    listing = describe_kinds()[6]
    assert dict(listing) == STAT_LISTING
    assert list(listing) == list(STAT_LISTING)


def test_listing_uses_plain_lists_and_strings() -> None:
    for listing in describe_kinds():
        assert type(listing["output"]) is str
        assert type(listing["channels"]) is list
        assert type(listing["options"]) is list
        for channel in listing["channels"]:
            assert type(channel["accepts"]) is list
            assert all(type(item) is str for item in channel["accepts"])
        for option in listing["options"]:
            assert type(option["choices"]) is list
            assert type(option["type"]) is str


def test_listing_round_trips_through_json_unchanged() -> None:
    listings = describe_kinds()
    assert len(listings) >= 8
    decoded = json.loads(json.dumps(listings))
    assert decoded[0] == LINE_LISTING
    assert decoded[6] == STAT_LISTING
    assert [entry["name"] for entry in decoded] == list(kind_names())


def test_table_listing_has_no_channels_options_or_series() -> None:
    table = describe_kinds()[7]
    assert table["channels"] == []
    assert table["options"] == []
    assert table["max_series"] is None
    assert table["bound"] == {
        "limit": 100,
        "counts": "rows",
        "over": "refuse",
        "rule": "At most 100 rows and 12 columns.",
    }


def test_the_listing_reads_the_registry_at_call_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stub = _local(name="zz-stub", channels=(_channel("x"),))
    monkeypatch.setattr(registry, "KINDS", (*KINDS, stub))
    assert kind_names()[-1] == "zz-stub"
    assert kind_names()[:8] == CORE_KIND_NAMES
    assert describe_kinds()[-1]["name"] == "zz-stub"
    assert kind_named("zz-stub") is stub


# --- the registry path equals the spec path (3.3, 5.6) ------------------------


def _cases_of(name: str) -> tuple[Case, ...]:
    module = importlib.import_module(
        f"tests.render.charts.kit.test_{name.replace('-', '_')}"
    )
    cases: tuple[Case, ...] = module.CASES
    return cases


def test_render_chart_equals_the_first_case_golden_of_every_registered_kind() -> None:
    checked = 0
    for spec in KINDS:
        case = _cases_of(spec.name)[0]
        rendered = render_chart(case.request, case.data)
        assert rendered.kind == spec.name
        assert rendered.output is spec.output
        assert rendered.text != ""
        suffix = "svg" if spec.output is Output.SVG else "md"
        assert_golden(golden_path(spec.name, case.name, suffix), rendered.text)
        checked += 1
    assert checked == len(KINDS) >= 8


def test_cases_are_found_for_the_core_kinds_by_convention() -> None:
    assert _cases_of("line")[0].name == "typical"
    assert _cases_of("stat")[0].name == "value"
    for name in CORE_KIND_NAMES:
        assert _cases_of(name)[0].request.kind == name


def test_render_chart_runs_the_kinds_check_before_drawing() -> None:
    stat = chart_request("stat", title="T", channels={"value": "v"})
    two_rows = chart_data([column("v")], [(1.5,), (2.5,)])
    with pytest.raises(ChartError) as caught:
        render_chart(stat, two_rows)
    assert [p.code for p in caught.value.problems] == [ProblemCode.OVER_BOUND]
    assert caught.value.problems[0].rows == 2
    one_row = chart_data([column("v")], [(1.5,)])
    assert render_chart(stat, one_row).text == "**T:** 1.5"


def test_render_chart_refuses_an_svg_kind_over_its_bound() -> None:
    line = chart_request("line", title="T", channels={"x": "n", "y": "v"})
    rows = [(float(i), float(i + 1)) for i in range(2001)]
    with pytest.raises(ChartError) as caught:
        render_chart(line, chart_data([column("n"), column("v")], rows))
    assert [p.code for p in caught.value.problems] == [ProblemCode.OVER_BOUND]
    assert caught.value.problems[0].rows == 2001


# --- unknown kind lists the registry (3.3) ------------------------------------


def test_an_unknown_kind_lists_the_registered_names() -> None:
    request = chart_request("zz-not-a-kind", title="T")
    problems = validate_chart(request, [column("v")])
    assert [p.code for p in problems] == [ProblemCode.UNKNOWN_KIND]
    assert problems[0].accepted == kind_names()
    assert problems[0].accepted[:8] == CORE_KIND_NAMES
    assert kind_named("zz-not-a-kind") is None


def test_render_chart_on_an_unknown_kind_lists_the_same_names() -> None:
    request = chart_request("zz-not-a-kind", title="T")
    with pytest.raises(ChartError) as caught:
        render_chart(request, chart_data([column("v")], [(1.0,)]))
    (problem,) = caught.value.problems
    assert problem.code is ProblemCode.UNKNOWN_KIND
    assert problem.accepted == kind_names()


def test_a_replaced_registry_changes_what_unknown_kind_lists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stub = replace(KINDS[0], name="aa-stub")
    monkeypatch.setattr(registry, "KINDS", (stub, *KINDS))
    problems = validate_chart(chart_request("zz", title="T"), [column("v")])
    assert problems[0].accepted[0] == "aa-stub"
    assert problems[0].accepted[1:9] == CORE_KIND_NAMES
