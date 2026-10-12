"""Tests for stage 1 and 2 validation, option parsing and binding.

Covers chart-kit Req 1.3, 1.4, 1.5, 3.2-3.11, 4.2, 4.3 and 16.2.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Callable, Iterable, Sequence
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any, cast

import pytest

from fitdocs.render.charts.kit.data import Column, ValueKind
from fitdocs.render.charts.kit.problems import ChartProblem, ProblemCode, ProblemDict
from fitdocs.render.charts.kit.schema import (
    BoundChart,
    BoundRequest,
    ChannelSpec,
    ChartRequest,
    KindSpec,
    MarkBound,
    OptionSpec,
    OptionType,
    OptionValue,
    Output,
    OverBound,
)
from fitdocs.render.charts.kit.validate import (
    bind_chart,
    bind_request,
    check_data,
    parse_option,
    validate_request,
)

N = ValueKind.NUMBER
D = ValueKind.DATE

DAY = Column("day", D)
STAMP = Column("stamp", ValueKind.DATETIME)
DIST = Column("dist_km", N, unit="km")
LOAD = Column("load", N)
NOTE = Column("note", ValueKind.CATEGORY)
FLAG = Column("ok", ValueKind.BOOLEAN)
SPAN = Column("span", ValueKind.DURATION)
COLS = (DAY, DIST, LOAD, NOTE, FLAG, SPAN)

OPT_FLAG = OptionSpec("flag", OptionType.BOOLEAN, "A flag.", True)
OPT_INT = OptionSpec("count", OptionType.INTEGER, "A count.", 7, minimum=2, maximum=50)
OPT_NUM = OptionSpec(
    "ratio", OptionType.NUMBER, "A ratio.", None, minimum=-5, maximum=9.5
)
OPT_CHOICE = OptionSpec(
    "mode", OptionType.CHOICE, "A mode.", "alpha", choices=("alpha", "beta", "gamma")
)
OPTIONS = (OPT_FLAG, OPT_INT, OPT_NUM, OPT_CHOICE)

CH_X = ChannelSpec("x", (N, D), True, "Horizontal.")
CH_Y = ChannelSpec("y", (N,), False, "Vertical.")


def _draw(chart: BoundChart) -> str:
    return "<svg/>"


def _spec(
    *,
    validate: Callable[[BoundRequest], tuple[ChartProblem, ...]] | None = None,
    uses_all_columns: bool = False,
    channels: tuple[ChannelSpec, ...] = (CH_X, CH_Y),
) -> KindSpec:
    kwargs: dict[str, Any] = {} if validate is None else {"validate": validate}
    return KindSpec(
        name="demo",
        description="A demo kind.",
        output=Output.SVG,
        channels=channels,
        options=OPTIONS,
        bound=MarkBound(10, "rows", OverBound.REFUSE, "Ten rows."),
        max_series=None,
        draw=_draw,
        uses_all_columns=uses_all_columns,
        **kwargs,
    )


def _req(
    channels: dict[str, str] | None = None,
    options: dict[str, Any] | None = None,
    *,
    title: str = "Title",
    kind: str = "demo",
) -> ChartRequest:
    return ChartRequest(
        "r9",
        kind,
        title,
        {"x": "day", "y": "dist_km"} if channels is None else channels,
        {} if options is None else options,
    )


def _validate(
    request: ChartRequest,
    columns: Sequence[Column] = COLS,
    spec: KindSpec | None = None,
    registered: Sequence[str] = ("demo", "other"),
) -> tuple[ChartProblem, ...]:
    return validate_request(request, columns, spec or _spec(), registered)


def _dicts(problems: Iterable[ChartProblem]) -> list[ProblemDict]:
    return [p.as_dict() for p in problems]


def _expected(code: str, message: str, fix: str, **kw: Any) -> ProblemDict:
    base: dict[str, Any] = {
        "ref": "r9",
        "kind": "demo",
        "code": code,
        "message": message,
        "fix": fix,
        "channel": None,
        "column": None,
        "option": None,
        "row": None,
        "rows": None,
        "accepted": [],
    }
    base.update(kw)
    return cast(ProblemDict, base)


# --- stage 1: one fixture per code --------------------------------------


def test_clean_request_has_no_problems() -> None:
    assert _validate(_req()) == ()


def test_unknown_kind_lists_registered_and_stops_channel_checks() -> None:
    # channels also unknown and options unknown: they are not reported.
    request = _req({"zz": "day"}, {"qq": 1}, kind="nope")
    got = validate_request(request, COLS, None, ("line", "bar", "area"))
    assert _dicts(got) == [
        _expected(
            "unknown_kind",
            "Kind 'nope' is not registered.",
            "Use one of the registered kinds.",
            kind=None,
            accepted=["line", "bar", "area"],
        )
    ]


def test_unknown_kind_still_reports_title_and_duplicate_columns() -> None:
    request = _req(kind="nope", title="")
    cols = (DAY, LOAD, Column("load", N))
    got = validate_request(request, cols, None, ("line",))
    assert [(p.code, p.kind) for p in got] == [
        (ProblemCode.UNKNOWN_KIND, None),
        (ProblemCode.EMPTY_TITLE, None),
        (ProblemCode.DUPLICATE_COLUMN, None),
    ]


def test_empty_title() -> None:
    assert _dicts(_validate(_req(title=""))) == [
        _expected(
            "empty_title", "The title is empty.", "Give the chart a non-empty title."
        )
    ]


def test_whitespace_title_is_empty() -> None:
    got = _validate(_req(title=" \t\n"))
    assert [p.code for p in got] == [ProblemCode.EMPTY_TITLE]


def test_duplicate_column_once_per_name_in_first_occurrence_order() -> None:
    cols = (
        DAY,
        DIST,
        LOAD,
        Column("load", N),
        Column("dist_km", N, unit="km"),
        Column("load", N),
    )
    got = _validate(_req(), cols)
    assert _dicts(got) == [
        _expected(
            "duplicate_column",
            "Column 'load' appears more than once.",
            "Give every column a unique name, for example with an alias in the query.",
            column="load",
        ),
        _expected(
            "duplicate_column",
            "Column 'dist_km' appears more than once.",
            "Give every column a unique name, for example with an alias in the query.",
            column="dist_km",
        ),
    ]


def test_missing_channel_accepted_is_fitting_columns_in_column_order() -> None:
    got = _validate(_req({"y": "dist_km"}))
    assert _dicts(got) == [
        _expected(
            "missing_channel",
            "Required channel 'x' is not bound.",
            "Bind 'x' to a column of kind number or date.",
            channel="x",
            accepted=["day", "dist_km", "load"],
        )
    ]


def test_optional_channel_unbound_is_fine() -> None:
    assert _validate(_req({"x": "day"})) == ()


def test_unknown_column() -> None:
    got = _validate(_req({"x": "day", "y": "ghost"}))
    assert _dicts(got) == [
        _expected(
            "unknown_column",
            "Channel 'y' is bound to column 'ghost', which is not among the columns.",
            "Bind 'y' to a column of kind number.",
            channel="y",
            column="ghost",
            accepted=["dist_km", "load"],
        )
    ]


def test_channel_kind() -> None:
    got = _validate(_req({"x": "day", "y": "note"}))
    assert _dicts(got) == [
        _expected(
            "channel_kind",
            "Channel 'y' accepts number columns, but column 'note' is category.",
            "Bind 'y' to a column of kind number.",
            channel="y",
            column="note",
            accepted=["dist_km", "load"],
        )
    ]


def test_unknown_unit() -> None:
    cols = (DAY, Column("dist_km", N, unit="furlong"), LOAD)
    got = _validate(_req(), cols)
    assert _dicts(got) == [
        _expected(
            "unknown_unit",
            "Column 'dist_km' (kind number) has unit 'furlong', "
            "which is not in the unit vocabulary.",
            "Use a unit token from the unit vocabulary, or give the column no unit.",
            channel="y",
            column="dist_km",
        )
    ]


def test_unit_kind_on_category_column() -> None:
    cols = (DAY, Column("tag", ValueKind.CATEGORY, unit="km"))
    spec = _spec(
        channels=(CH_X, ChannelSpec("y", (ValueKind.CATEGORY,), False, "Tag."))
    )
    got = _validate(_req({"x": "day", "y": "tag"}), cols, spec)
    assert _dicts(got) == [
        _expected(
            "unit_kind",
            "Column 'tag' (kind category) cannot carry unit 'km'.",
            "Alias the column in the query to a name without a unit suffix, "
            "or with one that fits its value kind.",
            channel="y",
            column="tag",
        )
    ]


def test_channel_kind_and_unit_kind_are_both_reported_for_one_column() -> None:
    cols = (DAY, Column("tag", ValueKind.CATEGORY, unit="km"))
    got = _validate(_req({"x": "day", "y": "tag"}), cols)
    assert [(p.code.value, p.channel, p.column) for p in got] == [
        ("channel_kind", "y", "tag"),
        ("unit_kind", "y", "tag"),
    ]


def test_unit_kind_for_seconds_on_a_date_column() -> None:
    cols = (Column("day_s", D, unit="s"), LOAD)
    got = _validate(_req({"x": "day_s"}), cols)
    assert _dicts(got) == [
        _expected(
            "unit_kind",
            "Column 'day_s' (kind date) cannot carry unit 's'.",
            "Alias the column in the query to a name without a unit suffix, "
            "or with one that fits its value kind.",
            channel="x",
            column="day_s",
        )
    ]


def test_unit_kind_for_clock_unit_on_a_number_column() -> None:
    cols = (Column("t_utc", N, unit="utc"),)
    got = _validate(_req({"x": "t_utc"}), cols)
    assert [(p.code, p.column) for p in got] == [(ProblemCode.UNIT_KIND, "t_utc")]


def test_unit_kind_for_unit_on_duration_and_boolean_columns() -> None:
    cols = (
        Column("a", ValueKind.DURATION, unit="s"),
        Column("b", ValueKind.BOOLEAN, unit="pct"),
    )
    spec = _spec(
        channels=(
            ChannelSpec("x", (ValueKind.DURATION,), True, "a"),
            ChannelSpec("y", (ValueKind.BOOLEAN,), True, "b"),
        )
    )
    got = _validate(_req({"x": "a", "y": "b"}), cols, spec)
    assert [(p.code, p.column) for p in got] == [
        (ProblemCode.UNIT_KIND, "a"),
        (ProblemCode.UNIT_KIND, "b"),
    ]


def test_valid_units_pass() -> None:
    cols = (
        Column("a_utc", D, unit="utc"),
        Column("b_local", ValueKind.DATETIME, unit="local"),
        Column("c_s", N, unit="s"),
        Column("d_pct", N, unit="pct"),
        Column("e_s_per_km", N, unit="s_per_km"),
    )
    spec = _spec(uses_all_columns=True, channels=())
    assert validate_request(_req({}), cols, spec, ("demo",)) == ()


def test_uses_all_columns_checks_unit_of_every_column_in_column_order() -> None:
    cols = (
        Column("z", ValueKind.CATEGORY, unit="km"),
        Column("a", N, unit="furlong"),
        Column("m", N),
        Column("q", D, unit="s"),
    )
    spec = _spec(uses_all_columns=True, channels=())
    got = validate_request(_req({}), cols, spec, ("demo",))
    assert [(p.code, p.column, p.channel) for p in got] == [
        (ProblemCode.UNIT_KIND, "z", None),
        (ProblemCode.UNKNOWN_UNIT, "a", None),
        (ProblemCode.UNIT_KIND, "q", None),
    ]


def test_uses_all_columns_reports_units_by_column_not_by_channel() -> None:
    cols = (Column("z", D, unit="s"), Column("b", N, unit="furlong"))
    spec = _spec(uses_all_columns=True, channels=(CH_X,))
    got = validate_request(_req({"x": "b"}), cols, spec, ("demo",))
    assert [(p.code.value, p.column, p.channel) for p in got] == [
        ("unit_kind", "z", None),
        ("unknown_unit", "b", None),
    ]


def test_unit_of_unbound_column_is_not_checked_without_uses_all_columns() -> None:
    cols = (DAY, DIST, Column("stray", ValueKind.CATEGORY, unit="km"))
    assert _validate(_req(), cols) == ()


def test_unknown_channel_lists_declared_channels_in_spec_order() -> None:
    spec = _spec(channels=(CH_Y, CH_X))
    got = _validate(_req({"x": "day", "bogus": "day"}), spec=spec)
    assert _dicts(got) == [
        _expected(
            "unknown_channel",
            "Channel 'bogus' is not declared by kind 'demo'.",
            "Bind only the channels the kind declares.",
            channel="bogus",
            accepted=["y", "x"],
        )
    ]


def test_option_value_for_choice_lists_choices() -> None:
    got = _validate(_req(options={"mode": "delta"}))
    assert _dicts(got) == [
        _expected(
            "option_value",
            "Option 'mode' does not accept this value; "
            "it takes one of alpha, beta, gamma.",
            "Set 'mode' to one of alpha, beta, gamma.",
            option="mode",
            accepted=["alpha", "beta", "gamma"],
        )
    ]


def test_option_value_messages_by_type() -> None:
    def msg(name: str, value: object) -> tuple[str, tuple[str, ...]]:
        (p,) = _validate(_req(options={name: value}))
        return p.message, p.accepted

    assert msg("flag", "yes") == (
        "Option 'flag' does not accept this value; it takes true or false.",
        (),
    )
    assert msg("count", 99) == (
        "Option 'count' does not accept this value; it takes an integer from 2 to 50.",
        (),
    )
    assert msg("ratio", 10) == (
        "Option 'ratio' does not accept this value; "
        "it takes a finite number from -5 to 9.5.",
        (),
    )


def test_option_value_messages_for_one_sided_and_large_bounds() -> None:
    def text(spec: OptionSpec, value: object) -> str:
        request = _req(options={spec.name: value})
        kind = dataclasses.replace(_spec(), options=(spec,))
        (p,) = validate_request(request, COLS, kind, ("demo",))
        return p.message

    lo = OptionSpec("o", OptionType.NUMBER, "x", None, minimum=1.5)
    hi = OptionSpec("o", OptionType.INTEGER, "x", None, maximum=12345678)
    free = OptionSpec("o", OptionType.NUMBER, "x", None)
    big = OptionSpec("o", OptionType.INTEGER, "x", None, minimum=0, maximum=12345678)
    fine = OptionSpec("o", OptionType.NUMBER, "x", None, minimum=0.1234567, maximum=2)
    pre = "Option 'o' does not accept this value; it takes "
    assert text(lo, "0") == pre + "a finite number of at least 1.5."
    assert text(hi, "12345679") == pre + "an integer of at most 12345678."
    assert text(free, "nan") == pre + "a finite number."
    assert text(big, "-1") == pre + "an integer from 0 to 12345678."
    assert text(fine, "9") == pre + "a finite number from 0.1234567 to 2."


def test_huge_integer_text_is_an_option_value_problem_not_a_crash() -> None:
    got = _validate(_req(options={"count": "9" * 5000}))
    assert _dicts(got) == [
        _expected(
            "option_value",
            "Option 'count' does not accept this value; "
            "it takes an integer from 2 to 50.",
            "Set 'count' to an integer from 2 to 50.",
            option="count",
        )
    ]
    assert parse_option(OPT_INT, "9" * 5000) is None
    assert parse_option(OPT_INT, "-" + "9" * 5000) is None


def test_unknown_option_lists_declared_options() -> None:
    got = _validate(_req(options={"nope": 1}))
    assert _dicts(got) == [
        _expected(
            "unknown_option",
            "Option 'nope' is not declared by kind 'demo'.",
            "Set only the options the kind declares.",
            option="nope",
            accepted=["flag", "count", "ratio", "mode"],
        )
    ]


def test_valid_options_in_every_form_pass() -> None:
    options = {"flag": "false", "count": "20", "ratio": "2.5", "mode": "gamma"}
    assert _validate(_req(options=options)) == ()
    assert _validate(_req(options={"flag": False, "count": 20, "ratio": 2.5})) == ()


# --- the validate hook gate ---------------------------------------------


def test_hook_runs_when_clean_and_its_problems_are_appended() -> None:
    seen: list[BoundRequest] = []

    def hook(bound: BoundRequest) -> tuple[ChartProblem, ...]:
        seen.append(bound)
        return (
            bound.problem(
                ProblemCode.OPTION_CONFLICT, "Hooked.", "Unhook.", option="mode"
            ),
        )

    got = _validate(_req(options={"count": "3"}), spec=_spec(validate=hook))
    assert len(seen) == 1
    assert seen[0].options["count"] == 3
    assert _dicts(got) == [
        _expected("option_conflict", "Hooked.", "Unhook.", option="mode")
    ]


@pytest.mark.parametrize(
    "request_",
    [
        _req(title=""),
        _req({"y": "dist_km"}),
        _req({"x": "day", "y": "ghost"}),
        _req({"x": "day", "y": "note"}),
        _req({"x": "day", "zz": "day"}),
        _req(options={"mode": "delta"}),
        _req(options={"nope": 1}),
    ],
)
def test_hook_does_not_run_when_anything_else_failed(request_: ChartRequest) -> None:
    calls: list[int] = []

    def hook(bound: BoundRequest) -> tuple[ChartProblem, ...]:
        calls.append(1)
        return ()

    got = _validate(request_, spec=_spec(validate=hook))
    assert got
    assert calls == []


def test_hook_does_not_run_after_duplicate_column_or_unit_problem() -> None:
    calls: list[int] = []

    def hook(bound: BoundRequest) -> tuple[ChartProblem, ...]:
        calls.append(1)
        return ()

    spec = _spec(validate=hook)
    _validate(_req(), (DAY, DIST, Column("dist_km", N, unit="km")), spec)
    _validate(_req(), (DAY, Column("dist_km", N, unit="furlong")), spec)
    assert calls == []


# --- order (16.2, 4.2) -----------------------------------------------------


def test_problems_follow_spec_order_not_request_order() -> None:
    # Request lists y before x, and options in reverse spec order.
    request = ChartRequest(
        "r9",
        "demo",
        "Title",
        {"y": "ghost2", "x": "ghost1"},
        {"mode": "delta", "count": 1, "flag": "maybe"},
    )
    got = _validate(request)
    assert [(p.code.value, p.channel, p.option) for p in got] == [
        ("unknown_column", "x", None),
        ("unknown_column", "y", None),
        ("option_value", None, "flag"),
        ("option_value", None, "count"),
        ("option_value", None, "mode"),
    ]


def test_unknown_names_are_sorted_and_come_after_declared_ones() -> None:
    request = ChartRequest(
        "r9",
        "demo",
        "Title",
        {"zeta": "day", "x": "ghost", "alpha": "day", "mid": "day"},
        {"yy": 1, "mode": "no", "aa": 1, "mm": 1},
    )
    got = _validate(request)
    assert [(p.code.value, p.channel or p.option) for p in got] == [
        ("unknown_column", "x"),
        ("unknown_channel", "alpha"),
        ("unknown_channel", "mid"),
        ("unknown_channel", "zeta"),
        ("option_value", "mode"),
        ("unknown_option", "aa"),
        ("unknown_option", "mm"),
        ("unknown_option", "yy"),
    ]


def test_stage_order_title_duplicates_channels_units_options() -> None:
    cols = (DAY, Column("dist_km", N, unit="furlong"), DAY)
    request = _req({"x": "ghost", "y": "dist_km"}, {"mode": "no"}, title="")
    got = _validate(request, cols)
    assert [p.code.value for p in got] == [
        "empty_title",
        "duplicate_column",
        "unknown_column",
        "unknown_unit",
        "option_value",
    ]


def test_independent_faults_are_all_reported() -> None:
    request = _req({"x": "day", "y": "note"}, {"count": 0, "wat": 1})
    got = _validate(request)
    assert [p.code.value for p in got] == [
        "channel_kind",
        "option_value",
        "unknown_option",
    ]


def test_request_mapping_order_does_not_change_the_result() -> None:
    a = ChartRequest(
        "r9", "demo", "T", {"x": "g1", "y": "g2"}, {"mode": "q", "flag": "q"}
    )
    b = ChartRequest(
        "r9", "demo", "T", {"y": "g2", "x": "g1"}, {"flag": "q", "mode": "q"}
    )
    assert _validate(a) == _validate(b)


# --- parse_option ---------------------------------------------------------


@pytest.mark.parametrize(
    ("spec", "raw", "expected"),
    [
        (OPT_FLAG, "true", True),
        (OPT_FLAG, "false", False),
        (OPT_FLAG, True, True),
        (OPT_FLAG, False, False),
        (OPT_INT, "20", 20),
        (OPT_INT, 20, 20),
        (OPT_INT, "2", 2),
        (OPT_INT, "50", 50),
        (OPT_NUM, "-3", -3.0),
        (OPT_NUM, "2.5", 2.5),
        (OPT_NUM, "9.5", 9.5),
        (OPT_NUM, "-5", -5.0),
        (OPT_NUM, 0, 0),
        (OPT_NUM, 0.0, 0.0),
        (OPT_NUM, 4.25, 4.25),
        (OPT_CHOICE, "beta", "beta"),
    ],
)
def test_parse_option_accepts(
    spec: OptionSpec, raw: OptionValue, expected: object
) -> None:
    got = parse_option(spec, raw)
    assert got == expected
    assert type(got) is type(expected)


def test_parse_option_negative_integer_text() -> None:
    spec = OptionSpec("o", OptionType.INTEGER, "x", None, minimum=-10, maximum=10)
    assert parse_option(spec, "-3") == -3
    assert parse_option(spec, "-10") == -10
    assert parse_option(spec, "-11") is None


def test_parse_option_unbounded() -> None:
    spec = OptionSpec("o", OptionType.NUMBER, "x", None)
    assert parse_option(spec, "-123456.5") == -123456.5
    assert parse_option(spec, "9" * 400) is None
    ispec = OptionSpec("o", OptionType.INTEGER, "x", None)
    assert (
        parse_option(ispec, "123456789012345678901234567890")
        == 123456789012345678901234567890
    )


@pytest.mark.parametrize(
    ("spec", "raw"),
    [
        (OPT_FLAG, "True"),
        (OPT_FLAG, "FALSE"),
        (OPT_FLAG, "yes"),
        (OPT_FLAG, "1"),
        (OPT_FLAG, 1),
        (OPT_FLAG, 0),
        (OPT_INT, "1.0"),
        (OPT_INT, " 20"),
        (OPT_INT, "20 "),
        (OPT_INT, "20\n"),
        (OPT_INT, "+20"),
        (OPT_INT, "nan"),
        (OPT_INT, "1"),
        (OPT_INT, "51"),
        (OPT_INT, 1),
        (OPT_INT, 51),
        (OPT_INT, True),
        (OPT_INT, 20.0),
        (OPT_INT, "٣"),
        (OPT_NUM, "nan"),
        (OPT_NUM, "inf"),
        (OPT_NUM, float("nan")),
        (OPT_NUM, float("inf")),
        (OPT_NUM, "9.51"),
        (OPT_NUM, "-5.01"),
        (OPT_NUM, 10),
        (OPT_NUM, -6.0),
        (OPT_NUM, True),
        (OPT_NUM, "1e3"),
        (OPT_NUM, "+5"),
        (OPT_NUM, "-"),
        (OPT_NUM, "--5"),
        (OPT_NUM, ".5"),
        (OPT_NUM, "5."),
        (OPT_NUM, " 5"),
        (OPT_NUM, "5\n"),
        (OPT_CHOICE, "Beta"),
        (OPT_CHOICE, " beta"),
        (OPT_CHOICE, "delta"),
        (OPT_CHOICE, ""),
        (OPT_CHOICE, 1),
        (OPT_CHOICE, True),
    ],
)
def test_parse_option_refuses(spec: OptionSpec, raw: OptionValue) -> None:
    assert parse_option(spec, raw) is None


def test_parse_option_false_and_zero_are_not_invalid() -> None:
    spec = OptionSpec("o", OptionType.INTEGER, "x", None, minimum=0, maximum=3)
    assert parse_option(spec, 0) == 0
    assert parse_option(spec, "0") == 0
    assert parse_option(OPT_FLAG, False) is False


# --- bind_request ---------------------------------------------------------


def test_bind_request_applies_defaults_and_parses_given_options() -> None:
    bound = bind_request(_req(options={"count": "20", "ratio": "2.5"}), COLS, _spec())
    assert dict(bound.options) == {
        "flag": True,
        "count": 20,
        "ratio": 2.5,
        "mode": "alpha",
    }
    assert list(bound.options) == ["flag", "count", "ratio", "mode"]
    assert bound.options["ratio"] == 2.5
    assert bound.integer("count") == 20


def test_bind_request_default_none_stays_none() -> None:
    bound = bind_request(_req(), COLS, _spec())
    assert bound.options["ratio"] is None
    assert bound.options["flag"] is True
    assert bound.options["count"] == 7


def test_bind_request_false_and_zero_options_are_kept_not_defaulted() -> None:
    spec = dataclasses.replace(
        _spec(),
        options=(
            OptionSpec("flag", OptionType.BOOLEAN, "f", True),
            OptionSpec("n", OptionType.INTEGER, "n", 5, minimum=0, maximum=9),
        ),
    )
    bound = bind_request(_req(options={"flag": False, "n": 0}), COLS, spec)
    assert dict(bound.options) == {"flag": False, "n": 0}


def test_bind_request_columns_in_spec_order_and_unbound_absent() -> None:
    request = ChartRequest("r9", "demo", "T", {"y": "load", "x": "day"})
    bound = bind_request(request, COLS, _spec())
    assert list(bound.columns) == ["x", "y"]
    assert dict(bound.columns) == {"x": DAY, "y": LOAD}
    assert bound.all_columns == COLS
    assert bound.request is request
    only_x = bind_request(ChartRequest("r9", "demo", "T", {"x": "day"}), COLS, _spec())
    assert dict(only_x.columns) == {"x": DAY}
    assert only_x.column("y") is None


def test_no_binding_is_inferred_from_a_column_named_like_a_channel() -> None:
    cols = (Column("x", N), Column("y", N), LOAD)
    request = ChartRequest("r9", "demo", "T", {"x": "load"})
    bound = bind_request(request, cols, _spec())
    assert dict(bound.columns) == {"x": LOAD}
    got = validate_request(ChartRequest("r9", "demo", "T"), cols, _spec(), ("demo",))
    assert [p.code.value for p in got] == ["missing_channel"]
    assert got[0].accepted == ("x", "y", "load")


def test_bind_request_refuses_an_unvalidated_request() -> None:
    with pytest.raises(ValueError):
        bind_request(_req({"x": "ghost"}), COLS, _spec())
    with pytest.raises(ValueError):
        bind_request(_req(options={"count": 0}), COLS, _spec())


# --- stage 2 --------------------------------------------------------------


def _bound(
    columns: Sequence[Column] = COLS,
    channels: dict[str, str] | None = None,
    spec: KindSpec | None = None,
) -> BoundRequest:
    spec = spec or _spec()
    request = _req(channels if channels is not None else {"x": "day", "y": "dist_km"})
    return bind_request(request, columns, spec)


def test_row_width_at_row_three_stops_the_stage() -> None:
    cols = (DAY, DIST)
    rows: list[tuple[Any, ...]] = [
        (date(2025, 1, 1), 1.0),
        (date(2025, 1, 2), 2.0),
        (date(2025, 1, 3), 3.0),
        (date(2025, 1, 4),),
        ("bad", float("nan")),
        (date(2025, 1, 6), 1.0, 2.0),
    ]
    got = check_data(_bound(cols), rows)
    assert _dicts(got) == [
        _expected(
            "row_width",
            "Row 3 holds 1 values but there are 2 columns.",
            "Give every row exactly one value per column.",
            row=3,
        )
    ]


def test_row_width_too_long() -> None:
    got = check_data(
        _bound((DAY, DIST)), [(date(2025, 1, 1), 1.0), (date(2025, 1, 2), 1.0, 5)]
    )
    assert [(p.code.value, p.row) for p in got] == [("row_width", 1)]


def test_value_type_names_first_offender_and_count() -> None:
    d = date(2025, 1, 1)
    rows: list[tuple[Any, ...]] = [
        (d, 1.0),
        (d, "x"),
        (d, 3.0),
        (d, None),
        (d, True),
        (d, 6.0),
    ]
    got = check_data(_bound((DAY, DIST)), rows)
    assert _dicts(got) == [
        _expected(
            "value_type",
            "Column 'dist_km' holds values that are not of kind number "
            "(first at row 1, rows affected: 2).",
            "Give column 'dist_km' only number values or absent ones.",
            column="dist_km",
            row=1,
            rows=2,
        )
    ]


def test_value_type_rows_counts_all_offenders_not_from_first_only() -> None:
    d = date(2025, 1, 1)
    rows: list[tuple[Any, ...]] = [
        (d, 1.0),
        (d, "a"),
        (d, 2.0),
        (d, 3.0),
        (d, "b"),
        (d, "c"),
        (d, "d"),
    ]
    (p,) = check_data(_bound((DAY, DIST)), rows)
    assert (p.row, p.rows) == (1, 4)


def test_non_finite_names_first_offender_and_count() -> None:
    d = date(2025, 1, 1)
    rows: list[tuple[Any, ...]] = [
        (d, 1.0),
        (d, 0.0),
        (d, float("nan")),
        (d, 4),
        (d, float("inf")),
        (d, float("-inf")),
        (d, Decimal("NaN")),
        (d, Decimal("7.5")),
    ]
    got = check_data(_bound((DAY, DIST)), rows)
    assert _dicts(got) == [
        _expected(
            "non_finite",
            "Column 'dist_km' holds NaN or infinite numbers "
            "(first at row 2, rows affected: 4).",
            "Replace them in column 'dist_km' with finite numbers or absent values.",
            column="dist_km",
            row=2,
            rows=4,
        )
    ]


def test_offenders_at_rows_two_and_five() -> None:
    d = date(2025, 1, 1)
    rows: list[tuple[Any, ...]] = [
        (d, 1.0),
        (d, 2.0),
        (d, "x"),
        (d, 4.0),
        (d, 5.0),
        (d, "y"),
    ]
    (p,) = check_data(_bound((DAY, DIST)), rows)
    assert (p.code, p.row, p.rows) == (ProblemCode.VALUE_TYPE, 2, 2)
    rows = [
        (d, 1.0),
        (d, 2.0),
        (d, float("nan")),
        (d, 4.0),
        (d, 5.0),
        (d, float("inf")),
    ]
    (p,) = check_data(_bound((DAY, DIST)), rows)
    assert (p.code, p.row, p.rows) == (ProblemCode.NON_FINITE, 2, 2)


def test_value_type_then_non_finite_per_column_in_channel_order() -> None:
    d = date(2025, 1, 1)
    # Column order: dist_km, day. Channel order: x (day), y (dist_km).
    cols = (DIST, DAY)
    rows: list[tuple[Any, ...]] = [
        (1.0, d),
        (float("nan"), d),
        (2.0, "bad"),
        ("worse", d),
        (3.0, datetime(2025, 1, 1, 12, 0)),
    ]
    got = check_data(_bound(cols), rows)
    assert [(p.code.value, p.column, p.row, p.rows) for p in got] == [
        ("value_type", "day", 2, 2),
        ("value_type", "dist_km", 3, 1),
        ("non_finite", "dist_km", 1, 1),
    ]


def test_value_type_one_problem_per_column_and_code() -> None:
    d = date(2025, 1, 1)
    rows: list[tuple[Any, ...]] = [
        (d, 1.0),
        (d, "a"),
        (d, "b"),
        (d, float("nan")),
        (d, float("nan")),
    ]
    got = check_data(_bound((DAY, DIST)), rows)
    assert [(p.code.value, p.rows) for p in got] == [
        ("value_type", 2),
        ("non_finite", 2),
    ]


def test_column_bound_to_two_channels_is_reported_once() -> None:
    d = date(2025, 1, 1)
    rows: list[tuple[Any, ...]] = [(d, 1.0), (d, "a")]
    bound = _bound((DAY, DIST), {"x": "dist_km", "y": "dist_km"})
    got = check_data(bound, rows)
    assert [(p.code.value, p.column) for p in got] == [("value_type", "dist_km")]


def test_unbound_columns_are_not_checked() -> None:
    d = date(2025, 1, 1)
    rows: list[tuple[Any, ...]] = [
        (d, 1.0, "oops", 5, float("nan")),
        (d, 2.0, 3, "x", 7),
    ]
    cols = (DAY, DIST, NOTE, FLAG, LOAD)
    assert check_data(_bound(cols), rows) == ()


def test_uses_all_columns_checks_every_column_in_column_order() -> None:
    d = date(2025, 1, 1)
    spec = _spec(uses_all_columns=True, channels=())
    cols = (NOTE, DIST, DAY)
    rows: list[tuple[Any, ...]] = [("a", 1.0, d), (4, float("nan"), "x"), ("c", 2.0, d)]
    bound = bind_request(_req({}), cols, spec)
    got = check_data(bound, rows)
    assert [(p.code.value, p.column, p.row) for p in got] == [
        ("value_type", "note", 1),
        ("non_finite", "dist_km", 1),
        ("value_type", "day", 1),
    ]


def test_kind_specific_value_rules_reach_check_data() -> None:
    cols = (DAY, STAMP, DIST)
    spec = _spec(channels=(CH_X, ChannelSpec("y", (N, ValueKind.DATETIME), False, "y")))
    bound = bind_request(_req({"x": "day", "y": "stamp"}), cols, spec)
    d = date(2025, 1, 1)
    rows: list[tuple[Any, ...]] = [
        (d, datetime(2025, 1, 1), 1.0),
        (datetime(2025, 1, 1), datetime(2025, 1, 1, tzinfo=UTC), 2.0),
    ]
    got = check_data(bound, rows)
    assert [(p.code.value, p.column, p.row, p.rows) for p in got] == [
        ("value_type", "day", 1, 1),
        ("value_type", "stamp", 1, 1),
    ]


def test_duration_column_with_values_and_absent_is_clean() -> None:
    from datetime import timedelta

    spec = _spec(channels=(ChannelSpec("x", (ValueKind.DURATION,), True, "d"),))
    bound = bind_request(_req({"x": "span"}), (SPAN,), spec)
    rows: list[tuple[Any, ...]] = [
        (timedelta(seconds=90),),
        (None,),
        (timedelta(0),),
    ]
    assert check_data(bound, rows) == ()


def test_absent_values_are_clean() -> None:
    d = date(2025, 1, 1)
    assert check_data(_bound((DAY, DIST)), [(None, None), (d, 0), (d, 0.0)]) == ()


def test_no_rows_is_clean() -> None:
    assert check_data(_bound((DAY, DIST)), []) == ()


# --- bind_chart -----------------------------------------------------------


def test_bind_chart_freezes_rows_and_keeps_the_bound_request() -> None:
    bound = _bound((DAY, DIST))
    rows: list[list[Any]] = [[date(2025, 1, 1), 1.5], [date(2025, 1, 2), None]]
    chart = bind_chart(bound, rows)
    assert isinstance(chart, BoundChart)
    assert chart.rows == ((date(2025, 1, 1), 1.5), (date(2025, 1, 2), None))
    assert all(isinstance(r, tuple) for r in chart.rows)
    assert isinstance(chart.rows, tuple)
    assert chart.request is bound.request
    assert chart.spec is bound.spec
    assert chart.columns == bound.columns
    assert chart.all_columns == bound.all_columns
    assert dict(chart.options) == dict(bound.options)
    assert chart.values("y") == (1.5, None)
