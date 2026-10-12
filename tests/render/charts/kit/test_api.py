"""The chart kit's entry points, registry reads and facade (design § Api)."""

from __future__ import annotations

import json
from dataclasses import FrozenInstanceError, fields, replace

import pytest

import fitdocs.render.charts.kit as kit
from fitdocs.render.charts.kit import api, registry
from fitdocs.render.charts.kit.data import ChartData, Column, ValueKind
from fitdocs.render.charts.kit.problems import ChartError, ChartProblem, ProblemCode
from fitdocs.render.charts.kit.schema import (
    BoundChart,
    ChannelSpec,
    ChartRequest,
    KindSpec,
    MarkBound,
    OptionSpec,
    OptionType,
    Output,
    OverBound,
)
from tests.render.charts.kit._helpers import (
    chart_data,
    chart_request,
    column,
    problems_of,
    render_case,
)

EVENTS: list[str] = []
DRAWN: list[BoundChart] = []
CHECK_PROBLEMS: list[tuple[ChartProblem, ...]] = []


def _check(bound: BoundChart) -> tuple[ChartProblem, ...]:
    EVENTS.append("check")
    return CHECK_PROBLEMS[0] if CHECK_PROBLEMS else ()


def _draw(bound: BoundChart) -> str:
    EVENTS.append("draw")
    DRAWN.append(bound)
    return f"<drawn {bound.spec.name} rows={len(bound.rows)}>"


A_STUB = KindSpec(
    name="a-stub",
    description="Alpha stub.",
    output=Output.SVG,
    channels=(
        ChannelSpec(
            "x", (ValueKind.NUMBER, ValueKind.DURATION), True, "The x position."
        ),
        ChannelSpec(
            "color", (ValueKind.CATEGORY, ValueKind.BOOLEAN), False, "The series."
        ),
    ),
    options=(
        OptionSpec(
            "mode",
            OptionType.CHOICE,
            "Drawing mode.",
            "fast",
            choices=("fast", "slow"),
        ),
        OptionSpec(
            "offset",
            OptionType.NUMBER,
            "Shift.",
            0.0,
            minimum=0.0,
        ),
        OptionSpec(
            "bins",
            OptionType.INTEGER,
            "Bin count.",
            None,
            minimum=1,
            maximum=100,
        ),
        OptionSpec("flag", OptionType.BOOLEAN, "A switch.", False),
    ),
    bound=MarkBound(2000, "rows", OverBound.REFUSE, "At most 2000 rows."),
    max_series=8,
    draw=_draw,
    check=_check,
)

B_STUB = KindSpec(
    name="b-stub",
    description="Bravo stub.",
    output=Output.MARKDOWN,
    channels=(ChannelSpec("value", tuple(ValueKind), True, "The headline value."),),
    options=(),
    bound=MarkBound(1, "row", OverBound.REDUCE, "One row."),
    max_series=None,
    draw=_draw,
)

COLUMNS = (column("x"), column("color", ValueKind.CATEGORY))
GOOD_ROWS = ((1, "u"), (2.5, "v"))


@pytest.fixture(autouse=True)
def _reset() -> None:
    EVENTS.clear()
    DRAWN.clear()
    CHECK_PROBLEMS.clear()


@pytest.fixture
def stubbed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(registry, "KINDS", (B_STUB, A_STUB))


def _request(**kwargs: object) -> ChartRequest:
    base = chart_request("a-stub", channels={"x": "x", "color": "color"})
    return replace(base, **kwargs)  # type: ignore[arg-type]


def _codes(problems: tuple[ChartProblem, ...]) -> list[ProblemCode]:
    return [p.code for p in problems]


# --- render_spec: stages ---------------------------------------------------


def test_render_spec_runs_check_then_draw_and_returns_the_text() -> None:
    data = chart_data(COLUMNS, GOOD_ROWS)
    rendered = render_case(A_STUB, _request(), data)

    assert rendered == api.RenderedChart("a-stub", Output.SVG, "<drawn a-stub rows=2>")
    assert EVENTS == ["check", "draw"]
    assert len(DRAWN) == 1
    assert DRAWN[0].rows == GOOD_ROWS
    assert dict(DRAWN[0].columns) == {"x": COLUMNS[0], "color": COLUMNS[1]}
    assert dict(DRAWN[0].options) == {
        "mode": "fast",
        "offset": 0.0,
        "bins": None,
        "flag": False,
    }


def test_rendered_chart_is_frozen_and_ordered() -> None:
    assert [f.name for f in fields(api.RenderedChart)] == ["kind", "output", "text"]
    rendered = api.RenderedChart("k", Output.MARKDOWN, "t")
    with pytest.raises(FrozenInstanceError):
        rendered.text = "other"  # type: ignore[misc]


def test_a_request_fault_and_a_data_fault_yield_only_the_request_problem() -> None:
    bad_rows = (("oops", "u"), (2.5, "v"))
    data = chart_data(COLUMNS, bad_rows)

    # The data fault is real on its own: stage 2 would report it.
    alone = problems_of(A_STUB, _request(), data)
    assert _codes(alone) == [ProblemCode.VALUE_TYPE]

    both = problems_of(A_STUB, _request(title="  "), data)
    assert _codes(both) == [ProblemCode.EMPTY_TITLE]
    assert EVENTS == []


def test_stage_one_reports_every_request_problem_together() -> None:
    request = _request(title="", channels={"color": "color"})
    problems = problems_of(A_STUB, request, chart_data(COLUMNS, GOOD_ROWS))
    assert _codes(problems) == [ProblemCode.EMPTY_TITLE, ProblemCode.MISSING_CHANNEL]
    assert EVENTS == []


def test_stage_two_reports_every_data_problem_and_stops_before_check() -> None:
    columns = (column("x"), column("color", ValueKind.CATEGORY))
    rows = (("oops", 7), (2.5, "v"))
    problems = problems_of(A_STUB, _request(), chart_data(columns, rows))
    assert [(p.code, p.column) for p in problems] == [
        (ProblemCode.VALUE_TYPE, "x"),
        (ProblemCode.VALUE_TYPE, "color"),
    ]
    assert EVENTS == []


def test_a_data_fault_prevents_the_kinds_check() -> None:
    CHECK_PROBLEMS.append(
        (ChartProblem("c1", "a-stub", ProblemCode.OVER_BOUND, "Too many.", "Fewer."),)
    )
    data = chart_data(COLUMNS, (("oops", "u"),))
    assert _codes(problems_of(A_STUB, _request(), data)) == [ProblemCode.VALUE_TYPE]
    assert EVENTS == []


def test_a_check_problem_prevents_draw() -> None:
    first = ChartProblem("c1", "a-stub", ProblemCode.OVER_BOUND, "One.", "Fix one.")
    second = ChartProblem("c1", "a-stub", ProblemCode.LOG_DOMAIN, "Two.", "Fix two.")
    CHECK_PROBLEMS.append((first, second))

    problems = problems_of(A_STUB, _request(), chart_data(COLUMNS, GOOD_ROWS))

    assert problems == (first, second)
    assert EVENTS == ["check"]
    assert DRAWN == []


def test_render_spec_raises_chart_error_carrying_the_problems() -> None:
    request = _request(title="")
    with pytest.raises(ChartError) as caught:
        api.render_spec(A_STUB, request, chart_data(COLUMNS, GOOD_ROWS))
    assert _codes(caught.value.problems) == [ProblemCode.EMPTY_TITLE]
    assert isinstance(caught.value.problems, tuple)


def test_render_spec_works_for_a_spec_outside_the_registry() -> None:
    assert registry.kind_named("a-stub") is None
    rendered = render_case(A_STUB, _request(), chart_data(COLUMNS, GOOD_ROWS))
    assert rendered.text == "<drawn a-stub rows=2>"


# --- render_chart / validate_chart over a monkeypatched registry -----------


def test_unknown_kind_lists_the_registered_kinds_in_registration_order(
    stubbed: None,
) -> None:
    request = chart_request("zz-stub", title="T")
    with pytest.raises(ChartError) as caught:
        api.render_chart(request, chart_data(COLUMNS, GOOD_ROWS))
    problems = caught.value.problems
    assert _codes(problems) == [ProblemCode.UNKNOWN_KIND]
    assert problems[0].accepted == ("b-stub", "a-stub")
    assert EVENTS == []


def test_unknown_kind_stage_reports_title_and_duplicate_column_problems(
    stubbed: None,
) -> None:
    columns = (column("x"), column("x"), column("color", ValueKind.CATEGORY))
    request = chart_request("zz-stub", title="  ")
    expected = [
        ProblemCode.UNKNOWN_KIND,
        ProblemCode.EMPTY_TITLE,
        ProblemCode.DUPLICATE_COLUMN,
    ]

    with pytest.raises(ChartError) as caught:
        api.render_chart(request, chart_data(columns, ((1, 2, "u"),)))
    assert _codes(caught.value.problems) == expected
    assert caught.value.problems[0].accepted == ("b-stub", "a-stub")
    assert EVENTS == []

    validated = api.validate_chart(request, columns)
    assert _codes(validated) == expected
    assert validated == caught.value.problems


def test_rendered_kind_comes_from_the_spec_not_the_request() -> None:
    request = chart_request("other-name", channels={"x": "x"})
    rendered = render_case(A_STUB, request, chart_data(COLUMNS, GOOD_ROWS))
    assert rendered.kind == "a-stub"


def test_render_chart_looks_the_kind_up_and_reaches_its_draw(stubbed: None) -> None:
    rendered = api.render_chart(_request(), chart_data(COLUMNS, GOOD_ROWS))
    assert rendered == api.RenderedChart("a-stub", Output.SVG, "<drawn a-stub rows=2>")
    assert [b.spec.name for b in DRAWN] == ["a-stub"]

    other = api.render_chart(
        chart_request("b-stub", channels={"value": "x"}),
        chart_data((column("x"),), ((4,),)),
    )
    assert other == api.RenderedChart(
        "b-stub", Output.MARKDOWN, "<drawn b-stub rows=1>"
    )


def test_render_chart_refuses_instead_of_returning_empty_text(stubbed: None) -> None:
    with pytest.raises(ChartError):
        api.render_chart(_request(title=""), chart_data(COLUMNS, GOOD_ROWS))
    assert DRAWN == []


def test_validate_chart_needs_no_rows(stubbed: None) -> None:
    assert api.validate_chart(_request(), COLUMNS) == ()
    assert EVENTS == []

    problems = api.validate_chart(_request(title="", channels={}), COLUMNS)
    assert isinstance(problems, tuple)
    assert _codes(problems) == [ProblemCode.EMPTY_TITLE, ProblemCode.MISSING_CHANNEL]

    unknown = api.validate_chart(chart_request("nope"), COLUMNS)
    assert _codes(unknown) == [ProblemCode.UNKNOWN_KIND]
    assert unknown[0].accepted == ("b-stub", "a-stub")


def test_validate_chart_reads_the_registry_at_call_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = _request()
    assert _codes(api.validate_chart(request, COLUMNS)) == [ProblemCode.UNKNOWN_KIND]
    monkeypatch.setattr(registry, "KINDS", (A_STUB,))
    assert api.validate_chart(request, COLUMNS) == ()


# --- registry reads --------------------------------------------------------


def test_core_kind_names_are_the_designed_eight() -> None:
    assert registry.CORE_KIND_NAMES == (
        "line",
        "area",
        "bar",
        "hbar",
        "scatter",
        "histogram",
        "stat",
        "table",
    )


def test_registry_functions_read_kinds_at_call_time(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    assert registry.kind_named("a-stub") is None

    monkeypatch.setattr(registry, "KINDS", (B_STUB, A_STUB))
    assert registry.kind_names() == ("b-stub", "a-stub")
    assert registry.kind_named("a-stub") is A_STUB
    assert registry.kind_named("b-stub") is B_STUB
    assert registry.kind_named("zz-stub") is None
    assert [d["name"] for d in registry.describe_kinds()] == ["b-stub", "a-stub"]

    monkeypatch.setattr(registry, "KINDS", (A_STUB,))
    assert registry.kind_names() == ("a-stub",)
    assert registry.kind_named("b-stub") is None
    assert [d["name"] for d in registry.describe_kinds()] == ["a-stub"]


# --- describe_kinds --------------------------------------------------------


def _assert_plain_json_types(value: object) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            assert type(key) is str
            _assert_plain_json_types(item)
    elif isinstance(value, list):
        for item in value:
            _assert_plain_json_types(item)
    else:
        assert type(value) in (str, int, float, bool, type(None)), repr(value)


B_LISTING = {
    "name": "b-stub",
    "description": "Bravo stub.",
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
        }
    ],
    "options": [],
    "bound": {"limit": 1, "counts": "row", "over": "reduce", "rule": "One row."},
    "max_series": None,
}

A_LISTING = {
    "name": "a-stub",
    "description": "Alpha stub.",
    "output": "svg",
    "channels": [
        {
            "name": "x",
            "required": True,
            "accepts": ["number", "duration"],
            "description": "The x position.",
        },
        {
            "name": "color",
            "required": False,
            "accepts": ["category", "boolean"],
            "description": "The series.",
        },
    ],
    "options": [
        {
            "name": "mode",
            "type": "choice",
            "default": "fast",
            "choices": ["fast", "slow"],
            "minimum": None,
            "maximum": None,
            "description": "Drawing mode.",
        },
        {
            "name": "offset",
            "type": "number",
            "default": 0.0,
            "choices": [],
            "minimum": 0.0,
            "maximum": None,
            "description": "Shift.",
        },
        {
            "name": "bins",
            "type": "integer",
            "default": None,
            "choices": [],
            "minimum": 1,
            "maximum": 100,
            "description": "Bin count.",
        },
        {
            "name": "flag",
            "type": "boolean",
            "default": False,
            "choices": [],
            "minimum": None,
            "maximum": None,
            "description": "A switch.",
        },
    ],
    "bound": {
        "limit": 2000,
        "counts": "rows",
        "over": "refuse",
        "rule": "At most 2000 rows.",
    },
    "max_series": 8,
}


def test_describe_kinds_gives_full_listings_in_registration_order(
    stubbed: None,
) -> None:
    listings = registry.describe_kinds()

    assert isinstance(listings, tuple)
    assert list(listings) == [B_LISTING, A_LISTING]
    for listing in listings:
        _assert_plain_json_types(listing)
    # Key order is the contract too, and dict equality ignores it.
    assert [list(listing) for listing in listings] == [
        list(B_LISTING),
        list(A_LISTING),
    ]
    assert [list(c) for c in listings[1]["channels"]] == [
        ["name", "required", "accepts", "description"]
    ] * 2
    assert [list(o) for o in listings[1]["options"]] == [
        [
            "name",
            "type",
            "default",
            "choices",
            "minimum",
            "maximum",
            "description",
        ]
    ] * 4
    assert list(listings[1]["bound"]) == ["limit", "counts", "over", "rule"]


def test_describe_kinds_is_json_serialisable_unchanged(stubbed: None) -> None:
    text = json.dumps(registry.describe_kinds())
    assert json.loads(text) == [B_LISTING, A_LISTING]


def test_listing_typed_dict_key_orders() -> None:
    assert tuple(registry.KindListing.__annotations__) == (
        "name",
        "description",
        "output",
        "channels",
        "options",
        "bound",
        "max_series",
    )
    assert tuple(registry.ChannelListing.__annotations__) == (
        "name",
        "required",
        "accepts",
        "description",
    )
    assert tuple(registry.OptionListing.__annotations__) == (
        "name",
        "type",
        "default",
        "choices",
        "minimum",
        "maximum",
        "description",
    )
    assert tuple(registry.BoundListing.__annotations__) == (
        "limit",
        "counts",
        "over",
        "rule",
    )


# --- facade ----------------------------------------------------------------

FACADE = (
    "ValueKind",
    "Value",
    "Column",
    "ChartData",
    "ChartRequest",
    "OptionValue",
    "Output",
    "ProblemCode",
    "ChartProblem",
    "ProblemDict",
    "ChartError",
    "RenderedChart",
    "validate_chart",
    "render_chart",
    "describe_kinds",
    "kind_names",
    "KindListing",
)


def test_facade_all_is_the_seventeen_names_in_order() -> None:
    assert kit.__all__ == FACADE
    assert len(FACADE) == 17
    for name in FACADE:
        assert hasattr(kit, name), name


def test_facade_names_are_the_defining_objects() -> None:
    assert kit.ChartError is ChartError
    assert kit.ChartProblem is ChartProblem
    assert kit.ChartRequest is ChartRequest
    assert kit.ChartData is ChartData
    assert kit.Column is Column
    assert kit.ValueKind is ValueKind
    assert kit.Output is Output
    assert kit.ProblemCode is ProblemCode
    assert kit.RenderedChart is api.RenderedChart
    assert kit.validate_chart is api.validate_chart
    assert kit.render_chart is api.render_chart
    assert kit.describe_kinds is registry.describe_kinds
    assert kit.kind_names is registry.kind_names
    assert kit.KindListing is registry.KindListing


def test_facade_keeps_render_spec_and_format_helpers_out() -> None:
    assert not hasattr(kit, "render_spec")
    assert not hasattr(kit, "escape_markdown")
    assert not hasattr(kit, "clean_text")
    assert kit.__doc__ is not None
    assert kit.__doc__.startswith("The chart kit:")
