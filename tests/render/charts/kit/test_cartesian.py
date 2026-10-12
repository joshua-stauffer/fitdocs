"""Tests for the shared x/y layer: series, numbers, counts and the shared checks.

Covers chart-kit Req 6.6 (log domain), 6.7 (category and date order), 9.3
(undrawn rows counted), 9.4 (absent category last), 11.2 (bound), 11.3
(series limit), 12.2 and 13.3 (duplicate position) and the stacking checks
of 9.5 and 12.5.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping, Sequence
from datetime import date, datetime, timedelta

import pytest

from fitdocs.render.charts.kit.cartesian import (
    SeriesGroup,
    bound_problem,
    category_order,
    duplicate_problem,
    log_problem,
    numbers,
    series_groups,
    series_problem,
    stack_problems,
    undrawn,
)
from fitdocs.render.charts.kit.data import Column, Value, ValueKind
from fitdocs.render.charts.kit.schema import (
    BoundChart,
    ChannelSpec,
    KindSpec,
    MarkBound,
    Output,
    OverBound,
)
from fitdocs.render.charts.kit.theme import MAX_SERIES, series_style

from ._helpers import chart_request, column


def _draw(chart: BoundChart) -> str:
    return "<svg/>"


def _bound(
    columns: Sequence[Column],
    rows: Sequence[Sequence[Value]],
    channels: Mapping[str, str],
    *,
    kind: str = "line",
    limit: int = 2000,
    counts: str = "rows",
) -> BoundChart:
    """A bound chart whose ``channels`` map channel names to column names."""
    by_name = {c.name: c for c in columns}
    spec = KindSpec(
        name=kind,
        description="A test kind.",
        output=Output.SVG,
        channels=tuple(
            ChannelSpec(name, tuple(ValueKind), False, "A channel.")
            for name in channels
        ),
        options=(),
        bound=MarkBound(limit, counts, OverBound.REFUSE, "rule"),
        max_series=MAX_SERIES,
        draw=_draw,
    )
    return BoundChart(
        request=chart_request(kind, channels=channels),
        spec=spec,
        columns={ch: by_name[name] for ch, name in channels.items()},
        all_columns=tuple(columns),
        options={},
        rows=tuple(tuple(r) for r in rows),
    )


# NOTE is an unbound column placed ahead of the bound ones in most fixtures.
NOTE = column("note", ValueKind.CATEGORY)
DAY = column("day", ValueKind.DATE)
DIST = column("distance_km", ValueKind.NUMBER, unit="km")
SPORT = column("sport", ValueKind.CATEGORY)
FLAG = column("indoor", ValueKind.BOOLEAN)
CHANNELS = {"x": "day", "y": "distance_km", "color": "sport"}


def _sport_chart(sports: Sequence[str | None]) -> BoundChart:
    rows = [("n", date(2024, 1, 1 + i % 28), float(i), s) for i, s in enumerate(sports)]
    return _bound([NOTE, DAY, DIST, SPORT], rows, CHANNELS)


# ---------------------------------------------------------------- SeriesGroup


def test_series_group_shape() -> None:
    assert [f.name for f in dataclasses.fields(SeriesGroup)] == [
        "label",
        "rows",
        "style",
    ]
    group = SeriesGroup("Run", (0,), series_style(0))
    with pytest.raises(dataclasses.FrozenInstanceError):
        group.label = "Bike"  # type: ignore[misc]


# -------------------------------------------------------------- series_groups


def test_groups_follow_first_appearance_and_put_absent_last() -> None:
    chart = _sport_chart(["Run", "Bike", None, "Swim", "Bike", "Run", None])
    groups = series_groups(chart)
    assert [(g.label, g.rows) for g in groups] == [
        ("Run", (0, 5)),
        ("Bike", (1, 4)),
        ("Swim", (3,)),
        ("—", (2, 6)),
    ]
    assert [g.style for g in groups] == [series_style(i) for i in range(4)]
    assert len({g.style for g in groups}) == 4


def test_groups_without_an_absent_value_have_no_dash_group() -> None:
    groups = series_groups(_sport_chart(["Swim", "Run", "Swim"]))
    assert [(g.label, g.rows) for g in groups] == [("Swim", (0, 2)), ("Run", (1,))]


def test_boolean_groups_are_true_and_false_in_first_appearance() -> None:
    rows = [("n", True, 1.0), ("n", False, 2.0), ("n", None, 3.0), ("n", True, 4.0)]
    chart = _bound([NOTE, FLAG, DIST], rows, {"y": "distance_km", "color": "indoor"})
    assert [(g.label, g.rows) for g in series_groups(chart)] == [
        ("true", (0, 3)),
        ("false", (1,)),
        ("—", (2,)),
    ]


def test_a_channel_other_than_color_can_be_grouped() -> None:
    rows = [
        ("n", date(2024, 1, 1), 1.0, "Run", "b"),
        ("n", date(2024, 1, 2), 2.0, "Run", "a"),
    ]
    other = column("other", ValueKind.CATEGORY)
    chart = _bound(
        [NOTE, DAY, DIST, SPORT, other],
        rows,
        {**CHANNELS, "shade": "other"},
    )
    assert [(g.label, g.rows) for g in series_groups(chart, "shade")] == [
        ("b", (0,)),
        ("a", (1,)),
    ]


def test_without_a_colour_channel_one_group_is_named_by_the_y_label() -> None:
    rows = [("n", date(2024, 1, 1), None, "Run"), ("n", date(2024, 1, 2), 0.0, "Bike")]
    chart = _bound([NOTE, DAY, DIST, SPORT], rows, {"x": "day", "y": "distance_km"})
    groups = series_groups(chart)
    assert groups == (SeriesGroup("distance", (0, 1), series_style(0)),)


def test_the_y_label_prefers_an_explicit_label() -> None:
    labelled = column("distance_km", ValueKind.NUMBER, unit="km", label="Run distance")
    chart = _bound(
        [DAY, labelled], [(date(2024, 1, 1), 1.0)], {"x": "day", "y": "distance_km"}
    )
    assert [g.label for g in series_groups(chart)] == ["Run distance"]


def test_no_rows_with_a_colour_channel_gives_no_groups() -> None:
    assert series_groups(_sport_chart([])) == ()


def test_more_series_than_the_palette_holds_cannot_be_styled() -> None:
    chart = _sport_chart([f"s{i}" for i in range(MAX_SERIES + 1)])
    with pytest.raises(ValueError):
        series_groups(chart)


# ------------------------------------------------------------- category_order


def test_categories_keep_first_appearance_with_absent_last() -> None:
    chart = _sport_chart(["Run", None, "Bike", "Swim", "Bike"])
    assert category_order(chart, "color") == ("Run", "Bike", "Swim", "—")


def test_dates_ascend_whatever_the_row_order() -> None:
    days = [
        date(2024, 3, 5),
        date(2024, 1, 2),
        None,
        date(2024, 2, 10),
        date(2024, 1, 2),
    ]
    chart = _bound([DAY], [(d,) for d in days], {"x": "day"})
    assert category_order(chart, "x") == ("2024-01-02", "2024-02-10", "2024-03-05", "—")


def test_date_times_ascend_whatever_the_row_order() -> None:
    stamp = column("at", ValueKind.DATETIME)
    values = [
        datetime(2024, 1, 2, 9, 30),
        datetime(2024, 1, 2, 8, 15),
        datetime(2023, 12, 31, 23, 0),
    ]
    chart = _bound([stamp], [(v,) for v in values], {"x": "at"})
    assert category_order(chart, "x") == (
        "2023-12-31 23:00",
        "2024-01-02 08:15",
        "2024-01-02 09:30",
    )


def test_a_column_without_an_order_of_its_own_keeps_first_appearance() -> None:
    chart = _bound([DIST], [(10.0,), (2.0,), (33.0,), (None,)], {"x": "distance_km"})
    assert category_order(chart, "x") == ("10.0", "2.0", "33.0", "—")


def test_no_absent_value_means_no_dash_in_the_order() -> None:
    chart = _sport_chart(["B", "A"])
    assert category_order(chart, "color") == ("B", "A")


def test_boolean_order_is_first_appearance() -> None:
    chart = _bound([FLAG], [(True,), (False,), (True,)], {"x": "indoor"})
    assert category_order(chart, "x") == ("true", "false")


# -------------------------------------------------------------------- numbers


def test_numbers_are_the_numeric_view_with_absent_and_zero_kept_apart() -> None:
    chart = _bound(
        [NOTE, DIST],
        [("n", 0), ("n", None), ("n", 2.5), ("n", 0.0)],
        {"y": "distance_km"},
    )
    assert numbers(chart, "y") == (0.0, None, 2.5, 0.0)
    assert numbers(chart, "y")[1] is None


def test_numbers_of_dates_date_times_and_durations() -> None:
    stamp = column("at", ValueKind.DATETIME)
    span = column("moving", ValueKind.DURATION)
    chart = _bound(
        [DAY, stamp, span],
        [
            (
                date(2024, 1, 2),
                datetime(2024, 1, 2, 3, 4, 5, 500000),
                timedelta(seconds=90.5),
            ),
            (None, None, None),
        ],
        {"x": "day", "y": "moving", "color": "at"},
    )
    assert numbers(chart, "x") == (738887.0, None)
    assert numbers(chart, "color") == (63839847845.5, None)
    assert numbers(chart, "y") == (90.5, None)


# -------------------------------------------------------------------- undrawn


def _gaps() -> BoundChart:
    x = column("xs", ValueKind.NUMBER)
    y = column("ys", ValueKind.NUMBER)
    rows = [
        ("n", 1, 1),
        ("n", None, None),
        ("n", None, 2),
        ("n", 3, None),
        ("n", None, None),
        ("n", 0, 0),
        ("n", 4, 5),
    ]
    return _bound([NOTE, x, y], rows, {"x": "xs", "y": "ys"})


def test_a_row_absent_on_two_channels_is_counted_once_under_the_first() -> None:
    assert undrawn(_gaps(), ["x", "y"]) == (("x", 3), ("y", 1))


def test_the_channel_order_given_decides_where_a_row_is_counted() -> None:
    assert undrawn(_gaps(), ["y", "x"]) == (("y", 3), ("x", 1))


def test_channels_with_no_undrawn_rows_are_omitted() -> None:
    x = column("xs", ValueKind.NUMBER)
    y = column("ys", ValueKind.NUMBER)
    chart = _bound([x, y], [(0, 1), (None, 2), (3, 0)], {"x": "xs", "y": "ys"})
    assert undrawn(chart, ["x", "y"]) == (("x", 1),)
    assert undrawn(chart, ["y"]) == ()


def test_an_unbound_channel_is_skipped() -> None:
    assert undrawn(_gaps(), ["color", "x"]) == (("x", 3),)


# ---------------------------------------------------------------- bound_problem


def _sized(limit: int) -> BoundChart:
    return _bound(
        [DAY],
        [(date(2024, 1, 1),)],
        {"x": "day"},
        kind="area",
        limit=limit,
        counts="points",
    )


def test_the_bound_is_silent_at_the_limit() -> None:
    assert bound_problem(_sized(50), 50) == ()
    assert bound_problem(_sized(50), 49) == ()


def test_one_over_the_bound_is_refused_with_the_limit_and_the_count() -> None:
    (problem,) = bound_problem(_sized(50), 51)
    assert problem.as_dict() == {
        "ref": "c1",
        "kind": "area",
        "code": "over_bound",
        "message": "area draws at most 50 points; this data has 51.",
        "fix": (
            "Aggregate the rows (for example by day or week) "
            "or limit them to at most 50."
        ),
        "channel": None,
        "column": None,
        "option": None,
        "row": None,
        "rows": 51,
        "accepted": [],
    }


# -------------------------------------------------------------- series_problem


def test_eight_series_including_the_dash_group_are_silent() -> None:
    chart = _sport_chart([f"s{i}" for i in range(MAX_SERIES - 1)] + [None])
    assert len(series_groups(chart)) == MAX_SERIES
    assert series_problem(chart) == ()


def test_nine_series_counting_the_dash_group_are_refused() -> None:
    chart = _sport_chart([f"s{i}" for i in range(MAX_SERIES)] + [None, "s0"])
    (problem,) = series_problem(chart)
    assert problem.as_dict() == {
        "ref": "c1",
        "kind": "line",
        "code": "too_many_series",
        "message": "line draws at most 8 series; the colour channel yields 9.",
        "fix": (
            "Filter the rows or bind a colour column with at most 8 distinct values."
        ),
        "channel": "color",
        "column": "sport",
        "option": None,
        "row": None,
        "rows": None,
        "accepted": [],
    }


def test_nine_named_series_are_refused_without_a_dash_group() -> None:
    chart = _sport_chart([f"s{i}" for i in range(MAX_SERIES + 1)])
    (problem,) = series_problem(chart)
    assert (
        problem.message == "line draws at most 8 series; the colour channel yields 9."
    )


def test_no_colour_channel_is_one_series() -> None:
    chart = _bound(
        [DAY, DIST], [(date(2024, 1, 1), 1.0)], {"x": "day", "y": "distance_km"}
    )
    assert series_problem(chart) == ()


# ------------------------------------------------------------ duplicate_problem


def _positions(rows: Sequence[tuple[date | None, str | None]]) -> BoundChart:
    full = [("n", d, float(i), s) for i, (d, s) in enumerate(rows)]
    return _bound([NOTE, DAY, DIST, SPORT], full, CHANNELS)


D1, D2, D3 = date(2024, 1, 1), date(2024, 1, 2), date(2024, 1, 3)


def test_the_first_duplicate_row_is_named_not_row_zero() -> None:
    chart = _positions(
        [(D1, "Run"), (D1, "Bike"), (D2, "Run"), (D1, "Bike"), (D3, "Run"), (D1, "Run")]
    )
    (problem,) = duplicate_problem(chart, ["color", "x"])
    assert problem.as_dict() == {
        "ref": "c1",
        "kind": "line",
        "code": "duplicate_position",
        "message": (
            "Row 3 repeats row 1, which has the same sport (Bike) and day (2024-01-01)."
        ),
        "fix": (
            "Aggregate the rows that share this position, "
            "or bind a column to color or x that separates them."
        ),
        "channel": None,
        "column": None,
        "option": None,
        "row": 3,
        "rows": None,
        "accepted": [],
    }


def test_distinct_positions_are_silent() -> None:
    chart = _positions([(D1, "Run"), (D1, "Bike"), (D2, "Run"), (D2, "Bike")])
    assert duplicate_problem(chart, ["color", "x"]) == ()


def test_the_keys_decide_what_a_duplicate_is() -> None:
    chart = _positions([(D1, "Run"), (D2, "Run")])
    assert duplicate_problem(chart, ["color", "x"]) == ()
    (problem,) = duplicate_problem(chart, ["color"])
    assert problem.row == 1
    assert problem.message == "Row 1 repeats row 0, which has the same sport (Run)."


def test_two_rows_with_an_absent_colour_share_the_dash_series() -> None:
    chart = _positions([(D1, "Run"), (D1, None), (D2, None), (D1, None)])
    (problem,) = duplicate_problem(chart, ["color", "x"])
    assert problem.row == 3
    assert (
        problem.message
        == "Row 3 repeats row 1, which has the same sport (—) and day (2024-01-01)."
    )


def test_a_first_duplicate_of_a_later_original_is_still_the_first_duplicate() -> None:
    chart = _positions(
        [(D1, "Run"), (D2, "Run"), (D2, "Bike"), (D1, "Run"), (D2, "Run")]
    )
    (problem,) = duplicate_problem(chart, ["color", "x"])
    assert (problem.row, problem.message) == (
        3,
        "Row 3 repeats row 0, which has the same sport (Run) and day (2024-01-01).",
    )


# ------------------------------------------------------------------ log_problem


def _log(values: Sequence[Value], kind: ValueKind = ValueKind.NUMBER) -> BoundChart:
    col = column("distance_km", kind)
    return _bound(
        [NOTE, col], [("n", v) for v in values], {"y": "distance_km"}, kind="scatter"
    )


def _log_dict(message: str, row: int) -> dict[str, object]:
    return {
        "ref": "c1",
        "kind": "scatter",
        "code": "log_domain",
        "message": message,
        "fix": "Set y_scale to linear or remove the rows with values at or below zero.",
        "channel": "y",
        "column": "distance_km",
        "option": "y_scale",
        "row": row,
        "rows": None,
        "accepted": [],
    }


def test_a_zero_is_the_first_offender_before_a_later_negative() -> None:
    (problem,) = log_problem(_log([3.0, None, 0, -2.0]), "y")
    assert problem.as_dict() == _log_dict(
        "Column distance_km holds 0 in row 2, which a logarithmic scale cannot draw.", 2
    )


def test_a_negative_is_reported_with_its_value() -> None:
    (problem,) = log_problem(_log([3.0, None, -2.5, 0.0]), "y")
    assert problem.as_dict() == _log_dict(
        "Column distance_km holds -2.5 in row 2, "
        "which a logarithmic scale cannot draw.",
        2,
    )


def test_a_zero_duration_is_reported() -> None:
    (problem,) = log_problem(
        _log([timedelta(seconds=5), timedelta(0)], ValueKind.DURATION), "y"
    )
    assert problem.row == 1
    assert (
        problem.message == "Column distance_km holds 0:00 in row 1, "
        "which a logarithmic scale cannot draw."
    )


def test_absent_and_positive_values_are_silent() -> None:
    assert log_problem(_log([3.0, None, 0.001, None]), "y") == ()
    assert log_problem(_log([None, None]), "y") == ()
    assert log_problem(_log([]), "y") == ()


# --------------------------------------------------------------- stack_problems

XS = column("xs", ValueKind.NUMBER)
YS = column("ys", ValueKind.NUMBER)
TEAM = column("team", ValueKind.CATEGORY)


def _stack(rows: Sequence[tuple[float | None, float | None, str]]) -> BoundChart:
    return _bound(
        [NOTE, XS, YS, TEAM],
        [("n", x, y, t) for x, y, t in rows],
        {"x": "xs", "y": "ys", "color": "team"},
        kind="area",
    )


def _stack_dict(
    code: str, message: str, fix: str, *, channel: str, column: str, row: int | None
) -> dict[str, object]:
    return {
        "ref": "c1",
        "kind": "area",
        "code": code,
        "message": message,
        "fix": fix,
        "channel": channel,
        "column": column,
        "option": None,
        "row": row,
        "rows": None,
        "accepted": [],
    }


COMPLETE: list[tuple[float | None, float | None, str]] = [
    (1, 4.0, "A"),
    (2, 0.0, "A"),
    (3, 6.0, "A"),
    (1, 7.0, "B"),
    (2, 8.0, "B"),
    (3, 9.0, "B"),
]


def test_complete_non_negative_data_with_zero_is_silent() -> None:
    chart = _stack(COMPLETE)
    assert stack_problems(chart, x="x", y="y", complete=True) == ()


def test_an_absent_y_is_refused_alone() -> None:
    rows = list(COMPLETE)
    rows[4] = (2, None, "B")
    (problem,) = stack_problems(_stack(rows), x="x", y="y", complete=True)
    assert problem.as_dict() == _stack_dict(
        "stack_absent",
        "Row 4 has no ys, which a stacked chart cannot draw.",
        "Unstack the chart or supply the missing value.",
        channel="y",
        column="ys",
        row=4,
    )


def test_a_negative_y_is_refused_alone() -> None:
    rows = list(COMPLETE)
    rows[3] = (1, -7.5, "B")
    (problem,) = stack_problems(_stack(rows), x="x", y="y", complete=True)
    assert problem.as_dict() == _stack_dict(
        "stack_negative",
        "Row 3 holds the negative ys -7.5, which a stacked chart cannot add up.",
        "Unstack the chart or replace the negative values.",
        channel="y",
        column="ys",
        row=3,
    )


def test_a_missing_series_x_pair_is_refused_alone_when_complete() -> None:
    rows = COMPLETE[:4] + COMPLETE[5:]
    chart = _stack(rows)
    (problem,) = stack_problems(chart, x="x", y="y", complete=True)
    assert problem.as_dict() == _stack_dict(
        "stack_incomplete",
        "Series B has no row at xs 2, which a stacked chart needs.",
        "Unstack the chart or supply a row for every series at every xs.",
        channel="x",
        column="xs",
        row=None,
    )
    assert stack_problems(chart, x="x", y="y", complete=False) == ()


def test_each_check_reports_its_first_offender_in_design_order() -> None:
    rows = [
        (1, 4.0, "A"),
        (1, None, "B"),
        (3, -1.0, "A"),
        (2, None, "A"),
        (3, -2.0, "B"),
    ]
    problems = stack_problems(_stack(rows), x="x", y="y", complete=True)
    assert [(p.code.value, p.row, p.message) for p in problems] == [
        ("stack_absent", 1, "Row 1 has no ys, which a stacked chart cannot draw."),
        (
            "stack_negative",
            2,
            "Row 2 holds the negative ys -1, which a stacked chart cannot add up.",
        ),
        (
            "stack_incomplete",
            None,
            "Series B has no row at xs 2, which a stacked chart needs.",
        ),
    ]


def test_the_first_missing_pair_is_the_first_series_then_the_lowest_x() -> None:
    rows: list[tuple[float | None, float | None, str]] = [
        (4, 1.0, "A"),
        (1, 2.0, "A"),
        (3, 3.0, "B"),
        (4, 4.0, "B"),
        (1, 5.0, "B"),
        (2, 6.0, "B"),
    ]
    (problem,) = stack_problems(_stack(rows), x="x", y="y", complete=True)
    assert problem.message == (
        "Series A has no row at xs 2, which a stacked chart needs."
    )
    rows = [(4, 1.0, "Z"), (1, 2.0, "Z"), (3, 3.0, "A"), (4, 4.0, "A"), (2, 5.0, "A")]
    (problem,) = stack_problems(_stack(rows), x="x", y="y", complete=True)
    assert problem.message == (
        "Series Z has no row at xs 2, which a stacked chart needs."
    )


def test_nine_colours_are_refused_by_series_and_stacking_does_not_crash() -> None:
    rows: list[tuple[float | None, float | None, str]] = []
    for i in range(MAX_SERIES + 1):
        rows += [(1, 1.0 + i, f"s{i}"), (2, 2.0 + i, f"s{i}")]
    del rows[5]
    chart = _stack(rows)
    assert [p.code.value for p in series_problem(chart)] == ["too_many_series"]
    (problem,) = stack_problems(chart, x="x", y="y", complete=True)
    assert (
        problem.message == "Series s2 has no row at xs 2, which a stacked chart needs."
    )


def test_a_series_row_with_an_absent_x_is_not_a_missing_pair() -> None:
    rows = [*COMPLETE, (None, 5.0, "A")]
    assert stack_problems(_stack(rows), x="x", y="y", complete=True) == ()


def test_the_duplicate_message_carries_the_key_unit() -> None:
    km = column("distance_km", ValueKind.NUMBER, unit="km")
    rows = [("n", 5.0, "Run"), ("n", 7.5, "Run"), ("n", 7.5, "Run")]
    chart = _bound([NOTE, km, SPORT], rows, {"x": "distance_km", "color": "sport"})
    (problem,) = duplicate_problem(chart, ["color", "x"])
    assert problem.message == (
        "Row 2 repeats row 1, which has the same sport (Run) and distance (7.5 km)."
    )


def test_the_duplicate_fix_names_the_keys_passed() -> None:
    chart = _positions([(D1, "Run"), (D1, "Run")])
    (both,) = duplicate_problem(chart, ["color", "x"])
    assert both.fix == (
        "Aggregate the rows that share this position, "
        "or bind a column to color or x that separates them."
    )
    rows = [("n", D1, 4.5, "Run"), ("n", D2, 4.5, "Bike")]
    same_y = _bound([NOTE, DAY, DIST, SPORT], rows, CHANNELS)
    (only_y,) = duplicate_problem(same_y, ["y"])
    assert only_y.fix == (
        "Aggregate the rows that share this position, "
        "or bind a column to y that separates them."
    )


def _absent_x_line() -> BoundChart:
    rows = [
        ("n", None, 1.0, "Run"),
        ("n", D1, 2.0, "Run"),
        ("n", None, 3.0, "Run"),
        ("n", D1, 4.0, "Bike"),
    ]
    return _bound([NOTE, DAY, DIST, SPORT], rows, CHANNELS)


def test_skip_absent_exempts_rows_absent_on_a_named_channel() -> None:
    chart = _absent_x_line()
    assert duplicate_problem(chart, ["color", "x"], skip_absent=("x",)) == ()
    (problem,) = duplicate_problem(chart, ["color", "x"])
    assert problem.row == 2
    assert problem.message == (
        "Row 2 repeats row 0, which has the same sport (Run) and day (—)."
    )


def test_skip_absent_names_only_the_channels_it_lists() -> None:
    rows = [("n", D1, 1.0, None), ("n", D1, 2.0, None)]
    chart = _bound([NOTE, DAY, DIST, SPORT], rows, CHANNELS)
    (problem,) = duplicate_problem(chart, ["color", "x"], skip_absent=("x",))
    assert problem.row == 1


def test_an_unbound_key_channel_is_one_series() -> None:
    rows = [("n", D1, 1.0), ("n", D2, 2.0), ("n", D1, 3.0)]
    chart = _bound([NOTE, DAY, DIST], rows, {"x": "day", "y": "distance_km"})
    (problem,) = duplicate_problem(chart, ["color", "x"])
    assert problem.row == 2
    assert (
        problem.message == "Row 2 repeats row 0, which has the same day (2024-01-01)."
    )
    assert problem.fix == (
        "Aggregate the rows that share this position, "
        "or bind a column to color or x that separates them."
    )
    assert duplicate_problem(chart, ["color"]) == ()
    (kept,) = duplicate_problem(chart, ["color", "x"], skip_absent=("color",))
    assert kept.row == 2


def test_a_row_absent_on_one_of_several_skip_channels_is_exempt() -> None:
    rows = [("n", D1, 1.0, None), ("n", D1, 2.0, None)]
    chart = _bound([NOTE, DAY, DIST, SPORT], rows, CHANNELS)
    assert duplicate_problem(chart, ["color", "x"], skip_absent=("x", "color")) == ()
