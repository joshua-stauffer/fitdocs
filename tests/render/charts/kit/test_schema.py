"""Tests for the kit's request, kind declaration and bound inputs.

Covers chart-kit Req 3.1 (request shape), 5.1 (kind declaration), 7.5
(default size and limits) and 11.1 (mark bound declaration).
"""

from __future__ import annotations

import dataclasses

import pytest

from fitdocs.render.charts.kit.data import Column, ValueKind
from fitdocs.render.charts.kit.problems import ChartProblem, ProblemCode
from fitdocs.render.charts.kit.schema import (
    BoundChart,
    BoundRequest,
    ChannelSpec,
    ChartRequest,
    KindSpec,
    MarkBound,
    OptionSpec,
    OptionType,
    Output,
    OverBound,
    no_problems,
    svg_options,
)


def _draw(chart: BoundChart) -> str:
    return "<svg/>"


X = Column("day", ValueKind.DATE)
Y = Column("distance_km", ValueKind.NUMBER, unit="km")
Z = Column("note", ValueKind.CATEGORY)

OWN = (
    OptionSpec("smooth", OptionType.BOOLEAN, "Smooth the line.", False),
    OptionSpec("bins", OptionType.INTEGER, "Bin count.", 10, minimum=1, maximum=100),
)


def _spec(options: tuple[OptionSpec, ...] = ()) -> KindSpec:
    return KindSpec(
        name="demo",
        description="A demo kind.",
        output=Output.SVG,
        channels=(
            ChannelSpec("x", (ValueKind.DATE,), True, "Horizontal."),
            ChannelSpec("y", (ValueKind.NUMBER,), True, "Vertical."),
        ),
        options=options,
        bound=MarkBound(10, "rows", OverBound.REFUSE, "Ten rows."),
        max_series=None,
        draw=_draw,
    )


def _bound_request(
    options: dict[str, bool | int | float | str | None] | None = None,
) -> BoundRequest:
    return BoundRequest(
        request=ChartRequest("chart-7", "ignored-kind", "Title"),
        spec=_spec(),
        columns={"x": X, "y": Y},
        all_columns=(X, Y),
        options=options or {},
    )


def _bound_chart(
    options: dict[str, bool | int | float | str | None] | None = None,
) -> BoundChart:
    # Column order is note, day, distance_km: channel y is bound to the THIRD
    # column, channel x to the SECOND, and the first column is bound to
    # nothing, so a lookup by channel position or by column position
    # returns other values.
    return BoundChart(
        request=ChartRequest("chart-7", "ignored-kind", "Title"),
        spec=_spec(),
        columns={"x": X, "y": Y},
        all_columns=(Z, X, Y),
        options=options or {},
        rows=(("a", 10, 1.5), ("b", 20, None), ("c", 30, 3.5)),
    )


def test_svg_options_order_and_limits() -> None:
    got = svg_options(*OWN, height=320)
    assert [o.name for o in got] == ["smooth", "bins", "width", "height"]
    assert got[:2] == OWN
    width, height = got[2], got[3]
    assert width == OptionSpec(
        "width",
        OptionType.INTEGER,
        width.description,
        720,
        minimum=320,
        maximum=1600,
    )
    assert height == OptionSpec(
        "height",
        OptionType.INTEGER,
        height.description,
        320,
        minimum=160,
        maximum=1200,
    )
    assert width.description and height.description


def test_svg_options_height_none_and_no_own() -> None:
    got = svg_options(height=None)
    assert [o.name for o in got] == ["width", "height"]
    assert got[1].default is None
    assert (got[1].minimum, got[1].maximum) == (160, 1200)
    assert got[0].default == 720


def test_svg_options_height_default_is_the_argument() -> None:
    assert svg_options(height=480)[-1].default == 480


def test_problem_fills_ref_and_kind_from_request_and_spec() -> None:
    bound = _bound_request()
    assert bound.request.kind != bound.spec.name
    p = bound.problem(ProblemCode.OPTION_VALUE, "Bad.", "Fix it.")
    assert p == ChartProblem(
        ref="chart-7",
        kind="demo",
        code=ProblemCode.OPTION_VALUE,
        message="Bad.",
        fix="Fix it.",
    )


def test_problem_passes_every_keyword_to_its_own_field() -> None:
    p = _bound_request().problem(
        ProblemCode.OVER_BOUND,
        "m",
        "f",
        channel="c-chan",
        column="c-col",
        option="c-opt",
        row=4,
        rows=9,
        accepted=("p", "q"),
    )
    assert (p.channel, p.column, p.option) == ("c-chan", "c-col", "c-opt")
    assert (p.row, p.rows, p.accepted) == (4, 9, ("p", "q"))
    assert (p.message, p.fix) == ("m", "f")


def test_accessors_return_typed_option_values() -> None:
    bound = _bound_request(
        {
            "smooth": True,
            "off": False,
            "bins": 12,
            "ratio": 2.5,
            "whole": 3,
            "mode": "step",
            "unset_int": None,
            "unset_num": None,
        }
    )
    assert bound.flag("smooth") is True
    assert bound.flag("off") is False
    assert bound.integer("bins") == 12
    assert type(bound.integer("bins")) is int
    assert bound.number("ratio") == 2.5
    whole = bound.number("whole")
    assert whole == 3.0
    assert type(whole) is float
    assert bound.choice("mode") == "step"
    assert bound.integer("unset_int") is None
    assert bound.number("unset_num") is None


def test_column_accessor_returns_bound_column_or_none() -> None:
    bound = _bound_request()
    assert bound.column("x") is X
    assert bound.column("y") is Y
    assert bound.column("z") is None


def test_values_follow_the_bound_column_in_row_order() -> None:
    chart = _bound_chart()
    assert chart.values("y") == (1.5, None, 3.5)
    assert chart.values("x") == (10, 20, 30)
    # Channel position (y is the second channel) and column position
    # (all_columns[1] is day) would both give other columns than y's.
    assert chart.values("y") != tuple(r[1] for r in chart.rows)
    assert chart.values("y") != tuple(r[0] for r in chart.rows)


def test_width_and_height_read_the_options() -> None:
    chart = _bound_chart({"width": 640, "height": 200})
    assert chart.width == 640
    assert chart.height == 200


def test_height_none_is_preserved() -> None:
    chart = _bound_chart({"width": 900, "height": None})
    assert chart.width == 900
    assert chart.height is None


def test_two_requests_do_not_share_a_default_mapping() -> None:
    a = ChartRequest("a", "line", "A")
    b = ChartRequest("b", "line", "B")
    assert a.channels == {} and a.options == {}
    assert a.channels is not b.channels
    assert a.options is not b.options
    assert a.channels is not a.options


def test_kind_spec_field_order_and_defaults() -> None:
    fields = dataclasses.fields(KindSpec)
    assert [f.name for f in fields] == [
        "name",
        "description",
        "output",
        "channels",
        "options",
        "bound",
        "max_series",
        "draw",
        "validate",
        "check",
        "uses_all_columns",
    ]
    spec = _spec()
    assert spec.validate is no_problems
    assert spec.check is no_problems
    assert spec.uses_all_columns is False
    assert no_problems(object()) == ()


def test_enum_member_names_and_values() -> None:
    assert [(m.name, m.value) for m in Output] == [
        ("SVG", "svg"),
        ("MARKDOWN", "markdown"),
    ]
    assert [(m.name, m.value) for m in OptionType] == [
        ("BOOLEAN", "boolean"),
        ("INTEGER", "integer"),
        ("NUMBER", "number"),
        ("CHOICE", "choice"),
    ]
    assert [(m.name, m.value) for m in OverBound] == [
        ("REFUSE", "refuse"),
        ("REDUCE", "reduce"),
    ]


def test_channel_spec_field_order() -> None:
    assert [f.name for f in dataclasses.fields(ChannelSpec)] == [
        "name",
        "accepts",
        "required",
        "description",
    ]


def test_zero_option_values_are_not_absent() -> None:
    bound = _bound_request({"zero_int": 0, "zero_num": 0.0})
    assert bound.integer("zero_int") == 0
    assert bound.integer("zero_int") is not None
    zero = bound.number("zero_num")
    assert zero == 0.0
    assert zero is not None
    int_zero = _bound_request({"zi": 0}).number("zi")
    assert int_zero is not None
    assert type(int_zero) is float


def test_declarations_are_frozen() -> None:
    chart = _bound_chart()
    spec = chart.spec
    targets: list[tuple[object, str]] = [
        (chart.request, "title"),
        (spec, "name"),
        (OWN[0], "name"),
        (spec.channels[0], "name"),
        (spec.bound, "limit"),
        (chart, "rows"),
    ]
    for obj, attr in targets:
        with pytest.raises(dataclasses.FrozenInstanceError):
            setattr(obj, attr, None)


def test_option_spec_and_mark_bound_defaults() -> None:
    o = OptionSpec("k", OptionType.CHOICE, "d", "a")
    assert (o.choices, o.minimum, o.maximum) == ((), None, None)
    assert [f.name for f in dataclasses.fields(OptionSpec)] == [
        "name",
        "type",
        "description",
        "default",
        "choices",
        "minimum",
        "maximum",
    ]
    assert [f.name for f in dataclasses.fields(MarkBound)] == [
        "limit",
        "counts",
        "over",
        "rule",
    ]
    assert [f.name for f in dataclasses.fields(ChartRequest)] == [
        "ref",
        "kind",
        "title",
        "channels",
        "options",
    ]
