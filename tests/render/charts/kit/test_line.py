"""The ``line`` kind: declaration, refusals, ordering, gaps, scales and goldens.

Requirements 9.1, 9.3, 9.6, 9.7, 10.1, 11.1, 11.2, 12.1, 12.2, 12.3, 18.1, 18.3.

Run ``uv run python -m tests.render.charts.kit.test_line`` to (re)write the
goldens under ``golden/line/``; a pytest run never writes them.
"""

from __future__ import annotations

import dataclasses
import re
import xml.etree.ElementTree as ET
from collections.abc import Mapping, Sequence
from datetime import date, datetime, timedelta

import pytest

from fitdocs.render.charts.kit import render_chart
from fitdocs.render.charts.kit.data import Column, Value, ValueKind
from fitdocs.render.charts.kit.kinds.line import KIND
from fitdocs.render.charts.kit.layout import text_width
from fitdocs.render.charts.kit.problems import ChartError, ChartProblem, ProblemCode
from fitdocs.render.charts.kit.schema import (
    ChannelSpec,
    MarkBound,
    OptionSpec,
    OptionType,
    OptionValue,
    Output,
    OverBound,
)
from fitdocs.render.charts.kit.theme import series_style
from tests.render.charts.kit._helpers import (
    Case,
    chart_data,
    chart_request,
    column,
    problems_of,
    render_case,
)
from tests.render.charts.kit.goldens import assert_golden, golden_path, write_golden

DAY = column("day", ValueKind.DATE)
KM = column("distance_km", unit="km")
SPORT = column("sport", ValueKind.CATEGORY)
CHANNELS_ALL = {"x": "day", "y": "distance_km", "color": "sport"}
CHANNELS_XY = {"x": "day", "y": "distance_km"}

SVG = "{http://www.w3.org/2000/svg}"


def _render(
    columns: Sequence[Column],
    rows: Sequence[Sequence[Value]],
    channels: Mapping[str, str] = CHANNELS_ALL,
    options: Mapping[str, OptionValue] | None = None,
    *,
    title: str = "Weekly distance",
) -> str:
    request = chart_request(
        "line", ref="l1", title=title, channels=channels, options=options
    )
    return render_case(KIND, request, chart_data(columns, rows)).text


def _refusal(
    columns: Sequence[Column],
    rows: Sequence[Sequence[Value]],
    channels: Mapping[str, str] = CHANNELS_ALL,
    options: Mapping[str, OptionValue] | None = None,
) -> tuple[ChartProblem, ...]:
    request = chart_request("line", ref="l1", channels=channels, options=options)
    return problems_of(KIND, request, chart_data(columns, rows))


# --- the golden fixtures --------------------------------------------------------

D = date

# Rows are out of date order; the absent colour sits before the first Bike row
# (so "absent last" differs from "first appearance"); Run precedes Bike
# (alphabetical would put Bike first); row 4 and row 8 are absent y inside a
# series; row 9 has no x and the largest y; row 12 is absent y at the latest
# date; row 6 is a recorded zero.
TYPICAL_ROWS: tuple[tuple[Value, ...], ...] = (
    (D(2026, 3, 9), 8.4, "Run"),
    (D(2026, 3, 2), 5.2, "Run"),
    (D(2026, 3, 12), 3.3, None),
    (D(2026, 3, 23), 10.8, "Run"),
    (D(2026, 3, 16), None, "Run"),
    (D(2026, 3, 10), 21.5, "Bike"),
    (D(2026, 3, 3), 0.0, "Bike"),
    (D(2026, 3, 24), 33.1, "Bike"),
    (D(2026, 3, 17), None, "Bike"),
    (None, 50.5, "Run"),
    (D(2026, 3, 30), 12.6, "Run"),
    (D(2026, 3, 26), 4.9, None),
    (D(2026, 4, 14), None, None),
)
TYPICAL_DESCRIPTION = (
    "Line chart: Weekly distance. x: day; y: distance (km); color: sport."
    " 13 rows, 3 series. Not drawn: 1 row without x, 3 rows without y."
    " day from 2026-03-02 to 2026-04-14; distance (km) from 0.0 km to 33.1 km."
)

ABSENT_ROWS: tuple[tuple[Value, ...], ...] = (
    (D(2026, 5, 2), None, "Run"),
    (None, 4.5, "Bike"),
    (None, None, None),
)

# Daily series with a run of absent days (rows exist, the value is absent).
_GAP_VALUES: tuple[float | None, ...] = (
    41.5,
    43.25,
    47.0,
    None,
    None,
    None,
    None,
    None,
    None,
    None,
    52.75,
    55.5,
    51.0,
    None,
    58.25,
    60.0,
)
DATES_GAP_ROWS: tuple[tuple[Value, ...], ...] = tuple(
    (D(2026, 6, 1) + timedelta(days=i), v) for i, v in enumerate(_GAP_VALUES)
)

NEGATIVE_X = column("offset_m", unit="m")
NEGATIVE_Y = column("delta_kg", unit="kg")
NEGATIVE_ROWS: tuple[tuple[Value, ...], ...] = (
    (4.0, -3.5, "Left"),
    (-6.0, 2.25, "Left"),
    (-1.0, -8.75, "Right"),
    (9.0, 6.5, "Right"),
    (0.0, 0.0, "Left"),
    (-3.0, -0.5, "Right"),
)

LONG_X = column(
    "elapsed_time", ValueKind.DURATION, label="Elapsed time since the start of the day"
)
LONG_Y = column(
    "power_w",
    unit="w",
    label="Average mechanical power sustained across the whole interval as measured"
    " at the crank spider by the strain gauges",
)
LONG_C = column("rider", ValueKind.CATEGORY)
LONG_ROWS: tuple[tuple[Value, ...], ...] = (
    (timedelta(minutes=50), 250.0, "A very long rider name that cannot fit its legend"),
    (timedelta(minutes=10), 180.0, "A very long rider name that cannot fit its legend"),
    (timedelta(minutes=30), 310.0, "Another extraordinarily long rider name indeed"),
    (timedelta(minutes=70), 205.0, "Another extraordinarily long rider name indeed"),
)
LONG_TITLE = (
    "A deliberately long chart title that cannot possibly fit within the width of"
    " the chart however small its type"
)

LOG_X = column("duration_s", unit="s")
LOG_Y = column("power_w", unit="w")
LOG_ROWS: tuple[tuple[Value, ...], ...] = (
    (300.0, 612.0, "Climb"),
    (5.0, 1450.0, "Climb"),
    (60.0, 905.0, "Climb"),
    (1800.0, 301.0, "Climb"),
    (20.0, 1130.0, "Sprint"),
    (3600.0, 255.0, "Sprint"),
    (1.0, 1710.0, "Sprint"),
    (600.0, 410.0, "Sprint"),
)

LIMIT = 2000


def _at_bound_rows(count: int) -> tuple[tuple[Value, ...], ...]:
    return tuple((float(i), float((i * 37) % 211) + i / 1000) for i in range(count))


N = column("n")
V = column("value")

CASES: tuple[Case, ...] = (
    Case(
        "typical",
        chart_request("line", ref="l1", title="Weekly distance", channels=CHANNELS_ALL),
        chart_data((DAY, KM, SPORT), TYPICAL_ROWS),
    ),
    Case(
        "empty",
        chart_request("line", ref="l1", title="Weekly distance", channels=CHANNELS_ALL),
        chart_data((DAY, KM, SPORT), []),
    ),
    Case(
        "all_absent",
        chart_request("line", ref="l1", title="Weekly distance", channels=CHANNELS_ALL),
        chart_data((DAY, KM, SPORT), ABSENT_ROWS),
    ),
    Case(
        "single",
        chart_request("line", ref="l1", title="Weekly distance", channels=CHANNELS_XY),
        chart_data((DAY, KM), [(D(2026, 3, 9), 8.4)]),
    ),
    Case(
        "negative",
        chart_request(
            "line",
            ref="l1",
            title="Net change",
            channels={"x": "offset_m", "y": "delta_kg", "color": "sport"},
        ),
        chart_data(
            (NEGATIVE_X, NEGATIVE_Y, column("sport", ValueKind.CATEGORY)), NEGATIVE_ROWS
        ),
    ),
    Case(
        "long_labels",
        chart_request(
            "line",
            ref="l1",
            title=LONG_TITLE,
            channels={"x": "elapsed_time", "y": "power_w", "color": "rider"},
        ),
        chart_data((LONG_X, LONG_Y, LONG_C), LONG_ROWS),
    ),
    Case(
        "at_bound",
        chart_request(
            "line", ref="l1", title="Every sample", channels={"x": "n", "y": "value"}
        ),
        chart_data((N, V), _at_bound_rows(LIMIT)),
    ),
    Case(
        "log",
        chart_request(
            "line",
            ref="l1",
            title="Power curve",
            channels={"x": "duration_s", "y": "power_w", "color": "sport"},
            options={"x_scale": "log", "y_scale": "log"},
        ),
        chart_data((LOG_X, LOG_Y, column("sport", ValueKind.CATEGORY)), LOG_ROWS),
    ),
    Case(
        "dates_gap",
        chart_request(
            "line",
            ref="l1",
            title="Resting heart rate",
            channels={"x": "day", "y": "rest_bpm"},
            options={"y_zero": True},
        ),
        chart_data((DAY, column("rest_bpm", unit="bpm")), DATES_GAP_ROWS),
    ),
)


def _case(name: str) -> Case:
    return next(case for case in CASES if case.name == name)


def _render_case(case: Case) -> str:
    return render_case(KIND, case.request, case.data).text


# --- parsing helpers -------------------------------------------------------------


def _root(text: str) -> ET.Element:
    return ET.fromstring(text)


def _group(text: str, css_class: str) -> list[ET.Element]:
    return [g for g in _root(text).iter(f"{SVG}g") if g.get("class") == css_class]


def _marks(text: str) -> list[tuple[str, str, list[tuple[float, float]]]]:
    """``(kind, stroke, points)`` per mark: a polyline or a one-point dot."""
    (marks,) = _group(text, "ck-marks")
    out: list[tuple[str, str, list[tuple[float, float]]]] = []
    for child in marks:
        stroke = child.get("stroke") or ""
        if child.tag == f"{SVG}polyline":
            points = [
                (float(a), float(b))
                for a, b in (p.split(",") for p in (child.get("points") or "").split())
            ]
            out.append(("line", stroke, points))
        else:
            assert child.tag == f"{SVG}path" and child.get("stroke-width") == "5"
            match = re.fullmatch(r"M(\S+) (\S+)h0", child.get("d") or "")
            assert match is not None
            out.append(("dot", stroke, [(float(match[1]), float(match[2]))]))
    return out


def _texts(element: ET.Element) -> list[ET.Element]:
    return list(element.iter(f"{SVG}text"))


def _legend_labels(text: str) -> list[str]:
    return [t.text or "" for g in _group(text, "ck-legend") for t in _texts(g)]


def _note_lines(text: str) -> list[str]:
    return [t.text or "" for g in _group(text, "ck-notes") for t in _texts(g)]


def _y_tick_labels(text: str) -> list[str]:
    return [
        t.text or ""
        for g in _group(text, "ck-axis")
        for t in _texts(g)
        if t.get("text-anchor") == "end"
    ]


def _desc(text: str) -> str:
    element = _root(text).find(f"{SVG}desc")
    assert element is not None
    return element.text or ""


# --- declaration -------------------------------------------------------------


def test_declaration() -> None:
    assert KIND.name == "line"
    assert KIND.description == "Lines over a numeric or time x, one per colour value"
    assert KIND.output is Output.SVG
    assert KIND.channels == (
        ChannelSpec(
            "x",
            (
                ValueKind.NUMBER,
                ValueKind.DURATION,
                ValueKind.DATE,
                ValueKind.DATETIME,
            ),
            True,
            "The horizontal position: a number, duration, date or date-time.",
        ),
        ChannelSpec(
            "y",
            (ValueKind.NUMBER, ValueKind.DURATION),
            True,
            "The vertical value: a number or duration.",
        ),
        ChannelSpec(
            "color",
            (ValueKind.CATEGORY, ValueKind.BOOLEAN),
            False,
            "One line per value of this column.",
        ),
    )
    assert KIND.options == (
        OptionSpec(
            "x_scale",
            OptionType.CHOICE,
            "The x axis scale; log needs a number or duration x.",
            "linear",
            choices=("linear", "log"),
        ),
        OptionSpec(
            "y_scale",
            OptionType.CHOICE,
            "The y axis scale; log needs values above zero.",
            "linear",
            choices=("linear", "log"),
        ),
        OptionSpec(
            "y_zero",
            OptionType.BOOLEAN,
            "Extend the y axis to include zero.",
            False,
        ),
        OptionSpec(
            "width",
            OptionType.INTEGER,
            "Chart width in pixels.",
            720,
            minimum=320,
            maximum=1600,
        ),
        OptionSpec(
            "height",
            OptionType.INTEGER,
            "Chart height in pixels.",
            320,
            minimum=160,
            maximum=1200,
        ),
    )
    assert KIND.bound == MarkBound(
        2000,
        "rows",
        OverBound.REFUSE,
        "At most 2000 rows; more are refused.",
    )
    assert KIND.max_series == 8
    assert KIND.uses_all_columns is False
    assert [f.name for f in dataclasses.fields(KIND)][:3] == [
        "name",
        "description",
        "output",
    ]


# --- each refusal alone ----------------------------------------------------------


def test_nine_series_refuse_alone() -> None:
    rows = [(float(i), float(i + 1), f"s{9 - i}") for i in range(9)]
    problems = _refusal(
        (column("n"), column("v"), SPORT),
        rows,
        {"x": "n", "y": "v", "color": "sport"},
    )
    assert problems == (
        ChartProblem(
            ref="l1",
            kind="line",
            code=ProblemCode.TOO_MANY_SERIES,
            message="line draws at most 8 series; the colour channel yields 9.",
            fix="Filter the rows or bind a colour column with at most 8 distinct "
            "values.",
            channel="color",
            column="sport",
        ),
    )


def test_eight_series_render() -> None:
    rows = [(float(i), float(i + 1), f"s{9 - i}") for i in range(8)]
    text = _render(
        (column("n"), column("v"), SPORT),
        rows,
        {"x": "n", "y": "v", "color": "sport"},
    )
    assert _legend_labels(text) == [f"s{9 - i}" for i in range(8)]


def test_2001_rows_refuse_alone_and_2000_render() -> None:
    columns = (N, V)
    channels = {"x": "n", "y": "value"}
    assert _refusal(columns, _at_bound_rows(2001), channels) == (
        ChartProblem(
            ref="l1",
            kind="line",
            code=ProblemCode.OVER_BOUND,
            message="line draws at most 2000 rows; this data has 2001.",
            fix="Aggregate the rows (for example by day or week) or limit them to "
            "at most 2000.",
            rows=2001,
        ),
    )
    text = _render(columns, _at_bound_rows(2000), channels)
    (mark,) = _marks(text)
    assert len(mark[2]) == 2000


def test_duplicate_series_and_x_refuse_alone() -> None:
    rows = [
        (D(2026, 3, 9), 1.0, "Run"),
        (D(2026, 3, 10), 2.0, "Run"),
        (D(2026, 3, 9), 3.0, "Bike"),
        (D(2026, 3, 10), 4.0, "Run"),
    ]
    assert _refusal((DAY, KM, SPORT), rows) == (
        ChartProblem(
            ref="l1",
            kind="line",
            code=ProblemCode.DUPLICATE_POSITION,
            message="Row 3 repeats row 1, which has the same sport (Run) and day "
            "(2026-03-10).",
            fix="Aggregate the rows that share this position, or bind a column to "
            "color or x that separates them.",
            row=3,
        ),
    )


def test_duplicate_is_per_series_and_absent_colour_is_a_series() -> None:
    same_x_other_series = [
        (D(2026, 3, 9), 1.0, "Run"),
        (D(2026, 3, 9), 3.0, "Bike"),
        (D(2026, 3, 9), 5.0, None),
    ]
    text = _render((DAY, KM, SPORT), same_x_other_series)
    assert [m[0] for m in _marks(text)] == ["dot", "dot", "dot"]
    twice_absent = [
        (D(2026, 3, 9), 1.0, None),
        (D(2026, 3, 10), 3.0, "Bike"),
        (D(2026, 3, 9), 5.0, None),
    ]
    (problem,) = _refusal((DAY, KM, SPORT), twice_absent)
    assert problem.code is ProblemCode.DUPLICATE_POSITION
    assert problem.row == 2
    assert problem.message == (
        "Row 2 repeats row 0, which has the same sport (—) and day (2026-03-09)."
    )


def test_rows_without_x_are_not_duplicates_of_each_other() -> None:
    rows = [
        (None, 1.0, "Run"),
        (D(2026, 3, 9), 2.0, "Run"),
        (None, 3.0, "Run"),
    ]
    text = _render((DAY, KM, SPORT), rows)
    assert _note_lines(text) == ["Not drawn: 2 rows without x."]


def test_log_y_with_a_non_positive_value_refuses_alone() -> None:
    rows = [
        (D(2026, 3, 1), 5.0),
        (D(2026, 3, 2), 3.0),
        (D(2026, 3, 3), 0.0),
        (D(2026, 3, 4), -2.0),
    ]
    assert _refusal((DAY, KM), rows, CHANNELS_XY, {"y_scale": "log"}) == (
        ChartProblem(
            ref="l1",
            kind="line",
            code=ProblemCode.LOG_DOMAIN,
            message="Column distance_km holds 0.0 km in row 2, which a logarithmic "
            "scale cannot draw.",
            fix="Set y_scale to linear or remove the rows with values at or below "
            "zero.",
            channel="y",
            column="distance_km",
            option="y_scale",
            row=2,
        ),
    )
    assert len(_marks(_render((DAY, KM), rows, CHANNELS_XY))) == 1


def test_log_x_with_a_non_positive_value_refuses_alone() -> None:
    rows = [(4.0, 1.0), (2.0, 2.0), (-3.0, 3.0), (0.0, 4.0)]
    problems = _refusal(
        (column("t"), column("v")), rows, {"x": "t", "y": "v"}, {"x_scale": "log"}
    )
    assert problems == (
        ChartProblem(
            ref="l1",
            kind="line",
            code=ProblemCode.LOG_DOMAIN,
            message="Column t holds -3 in row 2, which a logarithmic scale cannot "
            "draw.",
            fix="Set x_scale to linear or remove the rows with values at or below "
            "zero.",
            channel="x",
            column="t",
            option="x_scale",
            row=2,
        ),
    )


@pytest.mark.parametrize(
    ("kind", "value"),
    [
        (ValueKind.DATE, D(2026, 3, 9)),
        (ValueKind.DATETIME, datetime(2026, 3, 9, 6, 30)),
    ],
)
def test_log_x_on_a_time_column_conflicts_alone(kind: ValueKind, value: Value) -> None:
    when = column("when", kind)
    assert _refusal(
        (when, KM),
        [(value, 1.5)],
        {"x": "when", "y": "distance_km"},
        {"x_scale": "log"},
    ) == (
        ChartProblem(
            ref="l1",
            kind="line",
            code=ProblemCode.OPTION_CONFLICT,
            message=f"Option x_scale cannot be log for column 'when': it is a "
            f"{kind.value} column, and a logarithmic scale applies to number and "
            "duration columns only.",
            fix="Set x_scale to linear.",
            channel="x",
            column="when",
            option="x_scale",
        ),
    )
    text = _render((when, KM), [(value, 1.5)], {"x": "when", "y": "distance_km"}, None)
    assert text.startswith("<svg")


# --- ordering, gaps, dots, notes -------------------------------------------------

UNSORTED = [(5.0, 50.0), (1.0, 40.0), (9.0, 30.0), (3.0, 10.0), (7.0, 20.0)]
N_COL = column("n")
V_COL = column("v")
XY = {"x": "n", "y": "v"}


def test_rows_out_of_x_order_are_joined_in_x_order() -> None:
    assert sorted(UNSORTED) != UNSORTED
    text = _render((N_COL, V_COL), UNSORTED, XY)
    ((kind, _, points),) = _marks(text)
    assert kind == "line"
    xs = [p[0] for p in points]
    assert xs == sorted(xs) and len(set(xs)) == 5
    values = [v for _, v in sorted(UNSORTED)]
    assert values == [40.0, 10.0, 50.0, 20.0, 30.0]
    ys = [p[1] for p in points]
    # a larger value sits higher, that is at a smaller pixel y
    for i in range(5):
        for j in range(i + 1, 5):
            assert (ys[i] < ys[j]) == (values[i] > values[j])
    again = _render((N_COL, V_COL), sorted(UNSORTED), XY)
    assert again == text


def test_an_absent_y_splits_the_line_and_an_isolated_point_is_a_dot() -> None:
    rows = [
        (1.0, 10.0),
        (2.0, 20.0),
        (3.0, None),
        (4.0, 30.0),
        (5.0, 25.0),
        (6.0, 12.0),
        (7.0, None),
        (8.0, 18.0),
        (9.0, None),
        (10.0, 22.0),
        (11.0, 16.0),
    ]
    text = _render((N_COL, V_COL), rows, XY)
    marks = _marks(text)
    assert [(kind, len(points)) for kind, _, points in marks] == [
        ("line", 2),
        ("line", 3),
        ("dot", 1),
        ("line", 2),
    ]
    xs = [p[0] for _, _, points in marks for p in points]
    assert xs == sorted(xs) and len(xs) == 8


def test_a_recorded_zero_is_drawn_not_a_gap() -> None:
    rows = [(1.0, 3.0), (2.0, 0.0), (3.0, 5.0), (4.0, 1.0)]
    text = _render((N_COL, V_COL), rows, XY, {"y_zero": False})
    ((kind, _, points),) = _marks(text)
    assert kind == "line" and len(points) == 4
    assert points[1][1] > points[0][1] and points[1][1] > points[3][1]


def test_rows_without_x_or_y_are_counted_in_the_note_and_the_description() -> None:
    text = _render_case(_case("typical"))
    assert _note_lines(text) == ["Not drawn: 1 row without x, 3 rows without y."]
    assert _desc(text) == TYPICAL_DESCRIPTION


def test_a_complete_chart_has_no_note() -> None:
    text = _render((N_COL, V_COL), [(1.0, 2.0), (2.0, 3.0)], XY)
    assert _group(text, "ck-notes") == []
    assert "Not drawn" not in _desc(text)


# --- series ----------------------------------------------------------------------


def test_series_are_in_first_appearance_order_and_the_absent_colour_is_last() -> None:
    text = _render_case(_case("typical"))
    assert _legend_labels(text) == ["Run", "Bike", "—"]
    strokes = [stroke for _, stroke, _ in _marks(text)]
    assert strokes == [
        series_style(0).color,
        series_style(0).color,
        series_style(1).color,
        series_style(1).color,
        series_style(2).color,
    ]
    assert [kind for kind, _, _ in _marks(text)] == [
        "line",
        "line",
        "line",
        "dot",
        "line",
    ]


def test_without_a_colour_channel_there_is_no_legend() -> None:
    text = _render((N_COL, V_COL), [(1.0, 2.0), (2.0, 3.0)], XY)
    assert _group(text, "ck-legend") == []
    ((_, stroke, _),) = _marks(text)
    assert stroke == series_style(0).color


def test_a_boolean_colour_channel_makes_series() -> None:
    flag = column("flag", ValueKind.BOOLEAN)
    rows = [(1.0, 2.0, True), (2.0, 3.0, False), (3.0, 4.0, True), (4.0, 5.0, False)]
    text = _render((N_COL, V_COL, flag), rows, {"x": "n", "y": "v", "color": "flag"})
    assert _legend_labels(text) == ["true", "false"]


# --- scales ----------------------------------------------------------------------


def test_y_zero_includes_zero() -> None:
    rows = [(1.0, 62.0), (2.0, 71.0), (3.0, 88.0)]
    without = _y_tick_labels(_render((N_COL, V_COL), rows, XY))
    with_zero = _y_tick_labels(_render((N_COL, V_COL), rows, XY, {"y_zero": True}))
    assert float(without[0]) > 0
    assert float(with_zero[0]) == 0.0


def test_log_axes_accept_positive_data() -> None:
    text = _render_case(_case("log"))
    assert _y_tick_labels(text) == ["200", "500", "1000", "2000"]


def test_log_scale_is_not_linear() -> None:
    rows = [(1.0, 1.0), (10.0, 10.0), (100.0, 100.0), (1000.0, 1000.0)]
    text = _render((N_COL, V_COL), rows, XY, {"x_scale": "log", "y_scale": "log"})
    ((_, _, points),) = _marks(text)
    x_steps = [b[0] - a[0] for a, b in zip(points, points[1:], strict=False)]
    y_steps = [a[1] - b[1] for a, b in zip(points, points[1:], strict=False)]
    assert len(x_steps) == len(y_steps) == 3
    assert max(x_steps) - min(x_steps) < 0.5 and max(y_steps) - min(y_steps) < 0.5
    assert min(x_steps) > 50 and min(y_steps) > 50


DECADES = [(1.0, 1.0), (10.0, 10.0), (100.0, 100.0), (1000.0, 1000.0)]


def _steps(points: list[tuple[float, float]], axis: int) -> list[float]:
    return [abs(b[axis] - a[axis]) for a, b in zip(points, points[1:], strict=False)]


def _x_tick_labels(text: str) -> list[str]:
    (axis, *_) = _group(text, "ck-axis")
    labels = [t.text or "" for t in _texts(axis)]
    return labels[:-1]  # the last text is the axis title


def test_only_y_log_leaves_x_linear() -> None:
    text = _render((N_COL, V_COL), DECADES, XY, {"y_scale": "log"})
    assert _y_tick_labels(text) == ["1", "10", "100", "1000"]
    assert _x_tick_labels(text) == [f"{v}" for v in range(100, 1001, 100)]
    ((_, _, points),) = _marks(text)
    y_steps, x_steps = _steps(points, 1), _steps(points, 0)
    assert max(y_steps) - min(y_steps) < 0.5 and min(y_steps) > 50
    assert x_steps[0] < 10 < 100 < x_steps[2]


def test_only_x_log_leaves_y_linear() -> None:
    text = _render((N_COL, V_COL), DECADES, XY, {"x_scale": "log"})
    assert _x_tick_labels(text) == ["1", "10", "100", "1000"]
    assert _y_tick_labels(text) == ["0", "200", "400", "600", "800", "1000"]
    ((_, _, points),) = _marks(text)
    x_steps, y_steps = _steps(points, 0), _steps(points, 1)
    assert max(x_steps) - min(x_steps) < 0.5 and min(x_steps) > 50
    assert y_steps[0] < 10 < 100 < y_steps[2]


def test_a_row_absent_on_both_channels_is_counted_once_under_x() -> None:
    rows = [(1.0, 2.0), (None, None), (None, 3.0), (2.0, None), (3.0, 4.0)]
    text = _render((N_COL, V_COL), rows, XY)
    assert [m[0] for m in _marks(text)] == ["dot", "dot"]
    assert _note_lines(text) == ["Not drawn: 2 rows without x, 1 row without y."]
    assert "Not drawn: 2 rows without x, 1 row without y." in _desc(text)


def test_a_colour_with_one_value_still_has_a_legend() -> None:
    rows = [(D(2026, 3, 1), 1.0, "Run"), (D(2026, 3, 2), 2.0, "Run")]
    text = _render((DAY, KM, SPORT), rows)
    assert _legend_labels(text) == ["Run"]
    assert "2 rows, 1 series." in _desc(text)


def test_a_sub_hour_duration_axis_is_described_in_its_own_form() -> None:
    moving = column("moving_s", unit="s")
    rows = [(1.0, 1500.0), (2.0, 2700.0), (3.0, 2000.0)]
    text = _render((N_COL, moving), rows, {"x": "n", "y": "moving_s"})
    assert _y_tick_labels(text)[0] == "25:00"
    assert _desc(text).endswith("n from 1 to 3; moving (m:ss) from 25:00 to 45:00.")


def test_an_hours_duration_axis_is_described_in_hours_form() -> None:
    text = _render_case(_case("log"))
    assert _desc(text).endswith(
        "duration (h:mm:ss) from 0:00:01 to 1:00:00; power (W) from 255 W to 1710 W."
    )


def test_a_same_day_clock_axis_is_described_with_its_date() -> None:
    when = column("t", ValueKind.DATETIME)
    rows = [(datetime(2026, 3, 9, 9, 30), 2.0), (datetime(2026, 3, 9, 6, 0), 1.0)]
    text = _render((when, V_COL), rows, {"x": "t", "y": "v"})
    assert "t (2026-03-09) from 2026-03-09 06:00 to 2026-03-09 09:30;" in _desc(text)


SUB_HOUR = (300, 2700, 1200)
OVER_HOUR = (300, 4500, 1200)
MOVING = column("moving_s", unit="s")
ELAPSED = column("elapsed", ValueKind.DURATION)


@pytest.mark.parametrize(
    ("col", "seconds", "expected"),
    [
        (MOVING, SUB_HOUR, "moving (m:ss) from 5:00 to 45:00;"),
        (ELAPSED, SUB_HOUR, "elapsed (m:ss) from 5:00 to 45:00;"),
        (MOVING, OVER_HOUR, "moving (h:mm:ss) from 0:05:00 to 1:15:00;"),
        (ELAPSED, OVER_HOUR, "elapsed (h:mm:ss) from 0:05:00 to 1:15:00;"),
    ],
    ids=["number-sub-hour", "duration-sub-hour", "number-hours", "duration-hours"],
)
def test_a_duration_x_axis_is_described_in_its_own_form(
    col: Column, seconds: tuple[int, ...], expected: str
) -> None:
    values: list[Value] = [
        float(v) if col.kind is ValueKind.NUMBER else timedelta(seconds=v)
        for v in seconds
    ]
    rows = [(v, float(i + 1)) for i, v in enumerate(values)]
    text = _render((col, V_COL), rows, {"x": col.name, "y": "v"})
    assert expected in _desc(text)


def test_a_duration_range_is_written_in_the_form_of_the_niced_axis() -> None:
    elapsed = column("elapsed", ValueKind.DURATION)
    rows = [(1.0, timedelta(seconds=1500)), (2.0, timedelta(seconds=3300))]
    text = _render((N_COL, elapsed), rows, {"x": "n", "y": "elapsed"})
    assert _y_tick_labels(text)[-1] == "1:00:00"
    assert max(timedelta(seconds=1500), timedelta(seconds=3300)).seconds < 3600
    assert "elapsed (h:mm:ss) from 0:25:00 to 0:55:00." in _desc(text)


# --- no data ----------------------------------------------------------------------


def test_no_rows_is_the_no_data_state() -> None:
    text = _render_case(_case("empty"))
    assert _group(text, "ck-marks") == []
    assert _desc(text) == "Line chart: Weekly distance. No data: no rows."
    assert ">No data<" in text and "None of the" not in text
    assert 'height="320"' in text.split(">")[0]


def test_rows_without_a_drawable_value_are_the_no_data_state() -> None:
    text = _render_case(_case("all_absent"))
    assert _group(text, "ck-marks") == []
    assert _desc(text) == (
        "Line chart: Weekly distance. No data: none of the 3 rows has a value to draw."
    )
    assert "None of the 3 rows has a value to draw." in text


# --- goldens -------------------------------------------------------------------


def test_cases_are_the_designed_names() -> None:
    assert [case.name for case in CASES] == [
        "typical",
        "empty",
        "all_absent",
        "single",
        "negative",
        "long_labels",
        "at_bound",
        "log",
        "dates_gap",
    ]


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.name)
def test_golden(case: Case) -> None:
    rendered = render_case(KIND, case.request, case.data)
    assert rendered.kind == "line"
    assert rendered.output is Output.SVG
    assert_golden(golden_path("line", case.name, "svg"), rendered.text)


def test_no_stale_goldens() -> None:
    directory = golden_path("line", "x", "svg").parent
    on_disk = sorted(path.name for path in directory.iterdir())
    assert on_disk == sorted(f"{case.name}.svg" for case in CASES)


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.name)
def test_every_text_stays_inside_the_chart(case: Case) -> None:
    root = _root(_render_case(case))
    width = float(root.get("width") or "nan")
    texts = _texts(root)
    assert texts
    for element in texts:
        x = float(element.get("x") or "nan")
        reach = text_width(element.text or "", float(element.get("font-size") or "nan"))
        anchor = element.get("text-anchor")
        left = (
            x - reach / 2 if anchor == "middle" else x - reach if anchor == "end" else x
        )
        assert left >= 8.0 - 1e-6, element.text
        assert left + reach <= width - 4.0 + 1e-6, element.text


def test_typical_fixture_has_the_distinguishing_values() -> None:
    xs = [r[0] for r in TYPICAL_ROWS if r[0] is not None]
    assert xs != sorted(xs)
    first_colours = list(dict.fromkeys(r[2] for r in TYPICAL_ROWS))
    assert first_colours == ["Run", None, "Bike"]
    assert any(r[1] == 0.0 for r in TYPICAL_ROWS)


def test_long_labels_golden_is_shortened() -> None:
    text = _render_case(_case("long_labels"))
    assert text.count("…") >= 3


def test_at_bound_golden_is_at_the_bound() -> None:
    case = _case("at_bound")
    assert len(case.data.rows) == LIMIT == KIND.bound.limit


def test_dates_gap_has_a_run_of_absent_days() -> None:
    marks = _marks(_render_case(_case("dates_gap")))
    assert [(k, len(p)) for k, _, p in marks] == [
        ("line", 3),
        ("line", 3),
        ("line", 2),
    ]
    assert sum(1 for v in _GAP_VALUES[3:10] if v is None) == 7


def main() -> None:
    for case in CASES:
        write_golden(golden_path("line", case.name, "svg"), _render_case(case))


if __name__ == "__main__":
    main()


_EXTENT_CASES = (
    (
        ValueKind.DATE,
        (
            date(2025, 2, 1),
            date(2025, 2, 3),
            date(2025, 2, 5),
            date(2025, 2, 7),
            date(2025, 2, 9),
        ),
        ("2025-02-01", "2025-02-09"),
    ),
    (
        ValueKind.DATETIME,
        (
            datetime(2025, 2, 1, 6),
            datetime(2025, 2, 3, 6),
            datetime(2025, 2, 5, 6),
            datetime(2025, 2, 7, 6),
            datetime(2025, 2, 9, 6),
        ),
        ("2025-02-01 06:00", "2025-02-09 06:00"),
    ),
    (ValueKind.NUMBER, (0.0, 2.0, 4.0, 6.0, 8.0), ("0", "8")),
    (ValueKind.NUMBER, (-4.0, -2.0, 0.0, 2.0, 4.0), ("-4", "4")),
    (
        ValueKind.DURATION,
        (
            timedelta(0),
            timedelta(seconds=120),
            timedelta(seconds=240),
            timedelta(seconds=360),
            timedelta(seconds=480),
        ),
        ("0:00", "8:00"),
    ),
)


def _extent_axis(element: ET.Element) -> tuple[float, float]:
    axis = next(g for g in element.iter(f"{SVG}g") if g.get("class") == "ck-axis")
    line = next(iter(axis))
    return float(line.attrib["x1"]), float(line.attrib["x2"])


def _extent_positions(element: ET.Element) -> list[float]:
    left, right = _extent_axis(element)
    values: list[float] = []
    for g in element.iter(f"{SVG}g"):
        if g.get("class") != "ck-marks":
            continue
        for mark in g:
            if mark.tag == f"{SVG}polyline":
                values.extend(
                    float(p.split(",")[0]) for p in mark.attrib["points"].split()
                )
            elif mark.tag == f"{SVG}line":
                values.append(float(mark.attrib["x1"]))
            else:
                values.extend(
                    float(x) for x in re.findall(r"M([-\d.]+) ", mark.attrib["d"])
                )
    return sorted((v - left) / (right - left) for v in values)


@pytest.mark.parametrize(
    "kind,xs,labels",
    _EXTENT_CASES,
    ids=["date", "datetime", "zero", "negative", "duration"],
)
@pytest.mark.parametrize("missing", ["first", "last", "both"])
@pytest.mark.parametrize("observation", ["geometry", "y_geometry", "description"])
def test_present_x_extent(
    kind: ValueKind,
    xs: tuple[Value, ...],
    labels: tuple[str, str],
    missing: str,
    observation: str,
) -> None:
    first = None if missing in ("first", "both") else 4.0
    last = None if missing in ("last", "both") else 12.0
    rows = [(xs[3], 8.0), (xs[0], first), (None, 999.0), (xs[4], last), (xs[1], 0.0)]
    text = render_chart(
        chart_request("line", title="Extent", channels={"x": "position", "y": "value"}),
        chart_data((column("position", kind), column("value")), rows),
    ).text
    if observation == "geometry":
        expected = (
            ([0.0] if first is not None else [])
            + [0.25, 0.75]
            + ([1.0] if last is not None else [])
        )
        assert _extent_positions(_root(text)) == pytest.approx(expected, abs=0.001)
    elif observation == "y_geometry":
        high = 8.0 if last is None else 15.0
        expected = sorted(
            ([4.0 / high] if first is not None else [])
            + [0.0, 8.0 / high]
            + ([12.0 / high] if last is not None else [])
        )
        assert _extent_heights(_root(text)) == pytest.approx(expected, abs=0.001)
    else:
        x_title = "position (m:ss)" if kind is ValueKind.DURATION else "position"
        absent = 2 if missing == "both" else 1
        y_high = "8" if last is None else "12"
        assert _desc(text) == (
            f"Line chart: Extent. "
            f"x: {x_title}; y: value. "
            f"5 rows. "
            f"Not drawn: 1 row without x, "
            f"{absent} row{'s' if absent > 1 else ''} without y. "
            f"{x_title} from {labels[0]} to {labels[1]}; value from 0 to {y_high}."
        )


def _extent_heights(element: ET.Element) -> list[float]:
    axes = [g for g in element.iter(f"{SVG}g") if g.get("class") == "ck-axis"]
    boundary = next(iter(axes[1]))
    top, bottom = sorted((float(boundary.attrib["y1"]), float(boundary.attrib["y2"])))
    values: list[float] = []
    for g in element.iter(f"{SVG}g"):
        if g.get("class") != "ck-marks":
            continue
        for mark in g:
            if mark.tag == f"{SVG}polyline":
                values.extend(
                    float(p.split(",")[1]) for p in mark.attrib["points"].split()
                )
            else:
                values.extend(
                    float(y)
                    for y in re.findall(r"M[-\d.]+ ([-\d.]+)", mark.attrib["d"])
                )
    return sorted((bottom - v) / (bottom - top) for v in values)


@pytest.mark.parametrize("invalid_x", [0.0, -3.0])
def test_missing_y_does_not_disable_log_x_validation(invalid_x: float) -> None:
    with pytest.raises(ChartError) as error:
        render_chart(
            chart_request(
                "line",
                channels={"x": "position", "y": "value"},
                options={"x_scale": "log"},
            ),
            chart_data(
                (column("position"), column("value")),
                [(2.0, 1.0), (invalid_x, None), (4.0, 3.0)],
            ),
        )
    assert [(p.code, p.channel, p.row) for p in error.value.problems] == [
        (ProblemCode.LOG_DOMAIN, "x", 1)
    ]
