"""The ``dual-axis`` kind: declaration, unit refusal, two scales, gaps and goldens.

Requirements 2.2, 2.3, 2.4, 2.5, 2.6, 2.8, 2.9, 2.10, 6.1, 6.2, 6.3, 6.4, 6.5,
6.6, 6.7, 12.1, 12.3.

Run ``uv run python -m tests.render.charts.kit.test_dual_axis`` to (re)write the
goldens under ``golden/dual-axis/``; a pytest run never writes them.
"""

from __future__ import annotations

import dataclasses
import re
import xml.etree.ElementTree as ET
from collections.abc import Mapping, Sequence
from datetime import date, timedelta

import pytest

from fitdocs.render.charts.kit import registry
from fitdocs.render.charts.kit.data import Column, Value, ValueKind
from fitdocs.render.charts.kit.kinds.dual_axis import KIND
from fitdocs.render.charts.kit.layout import PAD, text_width
from fitdocs.render.charts.kit.problems import ChartProblem, ProblemCode
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
from fitdocs.render.charts.kit.validate import validate_request
from tests.render.charts.kit._helpers import (
    Case,
    chart_data,
    chart_request,
    column,
    problems_of,
    render_case,
)
from tests.render.charts.kit.goldens import assert_golden, golden_path, write_golden

SVG = "{http://www.w3.org/2000/svg}"
D = date

DAY = column("day", ValueKind.DATE)
PACE = column("pace_s_per_km", unit="s_per_km")
HR = column("heart_rate_bpm", unit="bpm")
CHANNELS = {"x": "day", "y": "pace_s_per_km", "y2": "heart_rate_bpm"}
N = column("n")
A = column("a_bpm", unit="bpm")
B = column("b_w", unit="w")
NAB = {"x": "n", "y": "a_bpm", "y2": "b_w"}


def _render(
    columns: Sequence[Column],
    rows: Sequence[Sequence[Value]],
    channels: Mapping[str, str] = CHANNELS,
    options: Mapping[str, OptionValue] | None = None,
    *,
    title: str = "Pace and heart rate",
) -> str:
    request = chart_request(
        "dual-axis", ref="d1", title=title, channels=channels, options=options
    )
    return render_case(KIND, request, chart_data(columns, rows)).text


def _refusal(
    columns: Sequence[Column],
    rows: Sequence[Sequence[Value]],
    channels: Mapping[str, str] = CHANNELS,
    options: Mapping[str, OptionValue] | None = None,
) -> tuple[ChartProblem, ...]:
    request = chart_request("dual-axis", ref="d1", channels=channels, options=options)
    return problems_of(KIND, request, chart_data(columns, rows))


def _stage1(
    columns: Sequence[Column], channels: Mapping[str, str]
) -> tuple[ChartProblem, ...]:
    request = chart_request("dual-axis", ref="d1", channels=channels)
    return validate_request(request, columns, KIND, registry.kind_names())


# --- the golden fixtures --------------------------------------------------------

# Rows are out of date order. Row 2 has no heart rate and row 3 no pace (each
# series breaks alone), row 7
# has no date but both values, and row 8 has neither value (counted under both
# y and y2, though it is one row) and breaks both lines. Pace is a line and two
# dots; heart rate is a line and a dot.
TYPICAL_ROWS: tuple[tuple[Value, ...], ...] = (
    (D(2026, 3, 9), 345.0, 152.0),
    (D(2026, 3, 2), 360.0, 148.0),
    (D(2026, 3, 23), 332.0, None),
    (D(2026, 3, 16), None, 158.0),
    (D(2026, 3, 12), 351.0, 155.0),
    (D(2026, 3, 30), 338.0, 161.0),
    (D(2026, 3, 5), 357.0, 150.0),
    (None, 340.0, 150.0),
    (D(2026, 3, 26), None, None),
)
TYPICAL_DESCRIPTION = (
    "Dual-axis chart: Pace and heart rate. x: day; y: pace (min/km);"
    " y2: heart rate (bpm). 9 rows."
    " Not drawn: 1 row without x, 2 rows without y, 2 rows without y2."
    " day from 2026-03-02 to 2026-03-30; pace (min/km) from 5:32 /km to"
    " 6:00 /km; heart rate (bpm) from 148 bpm to 161 bpm."
)

ABSENT_ROWS: tuple[tuple[Value, ...], ...] = (
    (D(2026, 5, 2), None, None),
    (None, 340.0, 150.0),
    (None, None, None),
)

NEGATIVE_Y = column("delta_kg", unit="kg")
NEGATIVE_Y2 = column("temp_c", unit="c")
NEGATIVE_ROWS: tuple[tuple[Value, ...], ...] = (
    (4.0, -3.5, -12.5),
    (-6.0, 2.25, 4.0),
    (-1.0, -8.75, -0.5),
    (9.0, 6.5, 9.25),
    (0.0, 0.0, 0.0),
    (-3.0, -0.5, -7.75),
)

ZERO_COLUMNS = (column("day", ValueKind.DATE), A, B)
ZERO_ROWS: tuple[tuple[Value, ...], ...] = (
    (D(2026, 6, 1), 121.0, 212.0),
    (D(2026, 6, 2), 134.0, 248.0),
    (D(2026, 6, 3), 128.0, 231.0),
    (D(2026, 6, 4), 143.0, 276.0),
    (D(2026, 6, 5), 139.0, 262.0),
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
LONG_Y2 = column(
    "cadence_rpm",
    unit="rpm",
    label="Pedalling cadence averaged over every complete revolution of the cranks"
    " within the interval",
)
LONG_ROWS: tuple[tuple[Value, ...], ...] = (
    (timedelta(minutes=50), 250.0, 88.0),
    (timedelta(minutes=10), 180.0, 76.0),
    (timedelta(minutes=30), 310.0, 94.0),
    (timedelta(minutes=70), 205.0, 81.0),
)
LONG_CHANNELS = {"x": "elapsed_time", "y": "power_w", "y2": "cadence_rpm"}
LONG_TITLE = (
    "A deliberately long chart title that cannot possibly fit within the width of"
    " the chart however small its type"
)

LIMIT = 2000


def _at_bound_rows(count: int) -> tuple[tuple[Value, ...], ...]:
    return tuple(
        (float(i), float((i * 37) % 211) + i / 1000, float((i * 53) % 97) + i / 1000)
        for i in range(count)
    )


CASES: tuple[Case, ...] = (
    Case(
        "typical",
        chart_request(
            "dual-axis", ref="d1", title="Pace and heart rate", channels=CHANNELS
        ),
        chart_data((DAY, PACE, HR), TYPICAL_ROWS),
    ),
    Case(
        "empty",
        chart_request(
            "dual-axis", ref="d1", title="Pace and heart rate", channels=CHANNELS
        ),
        chart_data((DAY, PACE, HR), []),
    ),
    Case(
        "all_absent",
        chart_request(
            "dual-axis", ref="d1", title="Pace and heart rate", channels=CHANNELS
        ),
        chart_data((DAY, PACE, HR), ABSENT_ROWS),
    ),
    Case(
        "single",
        chart_request(
            "dual-axis", ref="d1", title="Pace and heart rate", channels=CHANNELS
        ),
        chart_data((DAY, PACE, HR), [(D(2026, 3, 9), 345.0, 152.0)]),
    ),
    Case(
        "negative",
        chart_request(
            "dual-axis",
            ref="d1",
            title="Net change and temperature",
            channels={"x": "n", "y": "delta_kg", "y2": "temp_c"},
        ),
        chart_data((N, NEGATIVE_Y, NEGATIVE_Y2), NEGATIVE_ROWS),
    ),
    Case(
        "zero",
        chart_request(
            "dual-axis",
            ref="d1",
            title="Heart rate and power",
            channels={"x": "day", "y": "a_bpm", "y2": "b_w"},
            options={"y_zero": True, "y2_zero": True},
        ),
        chart_data(ZERO_COLUMNS, ZERO_ROWS),
    ),
    Case(
        "long_labels",
        chart_request("dual-axis", ref="d1", title=LONG_TITLE, channels=LONG_CHANNELS),
        chart_data((LONG_X, LONG_Y, LONG_Y2), LONG_ROWS),
    ),
    Case(
        "at_bound",
        chart_request("dual-axis", ref="d1", title="Every sample", channels=NAB),
        chart_data((N, A, B), _at_bound_rows(LIMIT)),
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


def _marks(text: str) -> list[tuple[str, str, str | None, list[tuple[float, float]]]]:
    """``(kind, stroke, dash, points)`` per mark: a polyline or a one-point dot."""
    (marks,) = _group(text, "ck-marks")
    out: list[tuple[str, str, str | None, list[tuple[float, float]]]] = []
    for child in marks:
        stroke = child.get("stroke") or ""
        if child.tag == f"{SVG}polyline":
            points = [
                (float(a), float(b))
                for a, b in (p.split(",") for p in (child.get("points") or "").split())
            ]
            out.append(("line", stroke, child.get("stroke-dasharray"), points))
        else:
            assert child.tag == f"{SVG}path" and child.get("stroke-width") == "5"
            match = re.fullmatch(r"M(\S+) (\S+)h0", child.get("d") or "")
            assert match is not None
            point = (float(match[1]), float(match[2]))
            out.append(("dot", stroke, child.get("stroke-dasharray"), [point]))
    return out


def _series(
    text: str, index: int
) -> list[tuple[str, str, str | None, list[tuple[float, float]]]]:
    colour = series_style(index).color
    return [m for m in _marks(text) if m[1] == colour]


def _texts(element: ET.Element) -> list[ET.Element]:
    return list(element.iter(f"{SVG}text"))


def _legend_labels(text: str) -> list[str]:
    return [t.text or "" for g in _group(text, "ck-legend") for t in _texts(g)]


def _note_lines(text: str) -> list[str]:
    return [t.text or "" for g in _group(text, "ck-notes") for t in _texts(g)]


def _desc(text: str) -> str:
    element = _root(text).find(f"{SVG}desc")
    assert element is not None
    return element.text or ""


def _axes(text: str) -> tuple[ET.Element, ET.Element, ET.Element]:
    """The bottom, left and right axis groups, in drawn order."""
    bottom, left, right = _group(text, "ck-axis")
    return bottom, left, right


def _tick_texts(axis: ET.Element, anchor: str) -> list[ET.Element]:
    """The tick labels of a side axis: the anchored texts below the title row."""
    texts = _texts(axis)
    title_y = min(float(t.get("y") or "nan") for t in texts)
    return [
        t
        for t in texts
        if t.get("text-anchor") == anchor and float(t.get("y") or "nan") > title_y
    ]


def _tick_labels(text: str) -> tuple[list[str], list[str]]:
    _, left, right = _axes(text)
    return (
        [t.text or "" for t in _tick_texts(left, "end")],
        [t.text or "" for t in _tick_texts(right, "start")],
    )


def _tick_ys(axis: ET.Element) -> list[float]:
    return [
        float(line.get("y1") or "nan")
        for line in axis.iter(f"{SVG}line")
        if line.get("y1") == line.get("y2")
    ]


def _grid_ys(text: str) -> list[float]:
    (grid,) = _group(text, "ck-grid")
    return [float(line.get("y1") or "nan") for line in grid.iter(f"{SVG}line")]


def _title_texts(text: str) -> tuple[ET.Element, ET.Element]:
    """The left (start-anchored) and right (end-anchored) y titles."""
    _, left, right = _axes(text)
    title_y = min(float(t.get("y") or "nan") for t in _texts(left) + _texts(right))
    (left_title,) = [t for t in _texts(left) if float(t.get("y") or "nan") == title_y]
    (right_title,) = [t for t in _texts(right) if float(t.get("y") or "nan") == title_y]
    return left_title, right_title


# --- declaration -----------------------------------------------------------------


def test_declaration() -> None:
    assert KIND.name == "dual-axis"
    assert KIND.output is Output.SVG
    assert KIND.description == (
        "Two series over one x, each on its own y axis with its own unit; "
        "unless the two are a deliberate pair, prefer small-multiples or one "
        "line with a colour column"
    )
    assert [(c.name, c.required, c.accepts) for c in KIND.channels] == [
        (
            "x",
            True,
            (
                ValueKind.NUMBER,
                ValueKind.DURATION,
                ValueKind.DATE,
                ValueKind.DATETIME,
            ),
        ),
        ("y", True, (ValueKind.NUMBER, ValueKind.DURATION)),
        ("y2", True, (ValueKind.NUMBER, ValueKind.DURATION)),
    ]
    assert all(isinstance(c, ChannelSpec) for c in KIND.channels)
    assert KIND.options == (
        OptionSpec(
            "y_zero",
            OptionType.BOOLEAN,
            "Extend the left axis to include zero.",
            False,
        ),
        OptionSpec(
            "y2_zero",
            OptionType.BOOLEAN,
            "Extend the right axis to include zero.",
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
        2000, "rows", OverBound.REFUSE, "At most 2000 rows; more are refused."
    )
    assert KIND.max_series is None
    assert [f.name for f in dataclasses.fields(KIND)][:3] == [
        "name",
        "description",
        "output",
    ]


def test_description_steers_towards_small_multiples_or_a_coloured_line() -> None:
    assert "prefer small-multiples or one line with a colour column" in KIND.description


# --- shared_unit -----------------------------------------------------------------

SHARED_FIX = (
    "Draw both columns on one axis with the line kind and a colour column, or "
    "bind y2 to a column in another unit."
)


def _shared(message: str, y2: str) -> ChartProblem:
    return ChartProblem(
        ref="d1",
        kind="dual-axis",
        code=ProblemCode.SHARED_UNIT,
        message=message,
        fix=SHARED_FIX,
        channel="y2",
        column=y2,
    )


def test_one_column_on_both_channels_is_refused_alone() -> None:
    channels = {"x": "n", "y": "a_bpm", "y2": "a_bpm"}
    expected = (
        _shared("y and y2 both show bpm; one unit belongs on one axis.", "a_bpm"),
    )
    assert _stage1((N, A), channels) == expected
    assert _refusal((N, A), [(1.0, 2.0)], channels) == expected


def test_one_unitless_column_on_both_channels_is_refused_by_its_label() -> None:
    plain = column("score")
    channels = {"x": "n", "y": "score", "y2": "score"}
    assert _stage1((N, plain), channels) == (
        _shared("y and y2 both show score; one unit belongs on one axis.", "score"),
    )


def test_two_columns_in_the_same_unit_are_refused() -> None:
    other = column("max_bpm", unit="bpm")
    channels = {"x": "n", "y": "a_bpm", "y2": "max_bpm"}
    assert _stage1((N, A, other), channels) == (
        _shared("y and y2 both show bpm; one unit belongs on one axis.", "max_bpm"),
    )


def test_two_duration_columns_are_refused() -> None:
    moving = column("moving_time", ValueKind.DURATION)
    elapsed = column("elapsed_time", ValueKind.DURATION)
    channels = {"x": "n", "y": "moving_time", "y2": "elapsed_time"}
    assert _stage1((N, moving, elapsed), channels) == (
        _shared(
            "y and y2 both show duration; one unit belongs on one axis.",
            "elapsed_time",
        ),
    )


@pytest.mark.parametrize("swap", [False, True])
def test_a_duration_column_and_a_seconds_column_are_refused(swap: bool) -> None:
    moving = column("moving_time", ValueKind.DURATION)
    seconds = column("rest_s", unit="s")
    y, y2 = ("rest_s", "moving_time") if swap else ("moving_time", "rest_s")
    assert _stage1((N, moving, seconds), {"x": "n", "y": y, "y2": y2}) == (
        _shared("y and y2 both show duration; one unit belongs on one axis.", y2),
    )


def test_pace_against_heart_rate_has_no_problem() -> None:
    assert _stage1((DAY, PACE, HR), CHANNELS) == ()


def test_a_duration_against_a_quantity_has_no_problem() -> None:
    moving = column("moving_time", ValueKind.DURATION)
    assert _stage1((N, moving, A), {"x": "n", "y": "moving_time", "y2": "a_bpm"}) == ()


def test_two_unitless_numbers_have_no_problem() -> None:
    assert (
        _stage1(
            (N, column("alpha"), column("beta")),
            {"x": "n", "y": "alpha", "y2": "beta"},
        )
        == ()
    )


def test_shared_unit_is_reported_without_rows() -> None:
    channels = {"x": "n", "y": "a_bpm", "y2": "a_bpm"}
    request = chart_request("dual-axis", ref="d1", channels=channels)
    problems = validate_request(request, (N, A), KIND, registry.kind_names())
    assert [p.code for p in problems] == [ProblemCode.SHARED_UNIT]


# --- limits and duplicates --------------------------------------------------------


def test_2001_rows_refuse_alone_and_2000_render() -> None:
    assert _refusal((N, A, B), _at_bound_rows(2001), NAB) == (
        ChartProblem(
            ref="d1",
            kind="dual-axis",
            code=ProblemCode.OVER_BOUND,
            message="dual-axis draws at most 2000 rows; this data has 2001.",
            fix="Aggregate the rows (for example by day or week) or limit them to "
            "at most 2000.",
            rows=2001,
        ),
    )
    text = _render((N, A, B), _at_bound_rows(2000), NAB)
    assert [len(m[3]) for m in _series(text, 0)] == [2000]
    assert [len(m[3]) for m in _series(text, 1)] == [2000]


def test_a_duplicate_x_refuses_alone() -> None:
    rows = [
        (D(2026, 3, 2), 360.0, 148.0),
        (D(2026, 3, 9), 345.0, 152.0),
        (D(2026, 3, 2), 351.0, 155.0),
        (D(2026, 3, 2), 340.0, 150.0),
    ]
    assert _refusal((DAY, PACE, HR), rows) == (
        ChartProblem(
            ref="d1",
            kind="dual-axis",
            code=ProblemCode.DUPLICATE_POSITION,
            message="Row 2 repeats row 0, which has the same day (2026-03-02).",
            fix="Aggregate the rows that share this position, or bind a column "
            "to x that separates them.",
            row=2,
        ),
    )


def test_rows_without_x_are_not_duplicates_of_each_other() -> None:
    rows = [(None, 360.0, 148.0), (None, 345.0, 152.0), (D(2026, 3, 9), 340.0, 150.0)]
    text = _render((DAY, PACE, HR), rows)
    assert _note_lines(text) == ["Not drawn: 2 rows without x."]


# --- two series, gaps, dots ---------------------------------------------------------


def test_an_absent_y_splits_only_the_y_line() -> None:
    rows = [
        (1.0, 10.0, 100.0),
        (2.0, 20.0, 110.0),
        (3.0, None, 120.0),
        (4.0, 30.0, 130.0),
        (5.0, 25.0, 140.0),
    ]
    text = _render((N, A, B), rows, NAB)
    y_marks, y2_marks = _series(text, 0), _series(text, 1)
    assert [(k, len(p)) for k, _, _, p in y_marks] == [("line", 2), ("line", 2)]
    assert [(k, len(p)) for k, _, _, p in y2_marks] == [("line", 5)]


def test_an_absent_y2_splits_only_the_y2_line() -> None:
    rows = [
        (1.0, 10.0, 100.0),
        (2.0, 20.0, None),
        (3.0, 15.0, 120.0),
        (4.0, 30.0, 130.0),
    ]
    text = _render((N, A, B), rows, NAB)
    assert [(k, len(p)) for k, _, _, p in _series(text, 0)] == [("line", 4)]
    assert [(k, len(p)) for k, _, _, p in _series(text, 1)] == [
        ("dot", 1),
        ("line", 2),
    ]


def test_an_isolated_point_is_a_dot() -> None:
    rows = [
        (1.0, 10.0, 100.0),
        (2.0, None, 110.0),
        (3.0, 15.0, 120.0),
        (4.0, None, 130.0),
    ]
    text = _render((N, A, B), rows, NAB)
    assert [(k, len(p)) for k, _, _, p in _series(text, 0)] == [
        ("dot", 1),
        ("dot", 1),
    ]


def test_the_series_are_joined_in_ascending_x_order() -> None:
    rows = [(5.0, 50.0, 5.0), (1.0, 40.0, 1.0), (9.0, 30.0, 9.0), (3.0, 10.0, 3.0)]
    text = _render((N, A, B), rows, NAB)
    for index in (0, 1):
        ((_, _, _, points),) = _series(text, index)
        xs = [p[0] for p in points]
        assert xs == sorted(xs) and len(set(xs)) == 4
    ((_, _, _, points),) = _series(text, 0)
    values = [v for _, v, _ in sorted(rows)]
    ys = [p[1] for p in points]
    for i in range(4):
        for j in range(i + 1, 4):
            assert (ys[i] < ys[j]) == (values[i] > values[j])


def test_a_recorded_zero_is_drawn_not_a_gap() -> None:
    rows = [(1.0, 3.0, 9.0), (2.0, 0.0, 0.0), (3.0, 5.0, 4.0), (4.0, 1.0, 8.0)]
    text = _render((N, A, B), rows, NAB)
    for index in (0, 1):
        ((kind, _, _, points),) = _series(text, index)
        assert kind == "line" and len(points) == 4
        assert points[1][1] > points[0][1] and points[1][1] > points[3][1]


def test_each_series_is_drawn_against_its_own_scale() -> None:
    # y spans 0-1000 and y2 spans 0-4 over the same rows: on one shared scale one
    # of them would be flat; on their own both climb the whole plot.
    rows = [(1.0, 0.0, 0.0), (2.0, 1000.0, 4.0)]
    text = _render((N, A, B), rows, NAB, {"y_zero": True, "y2_zero": True})
    ((_, _, _, y_points),) = _series(text, 0)
    ((_, _, _, y2_points),) = _series(text, 1)
    assert y_points == y2_points
    left, right = _tick_labels(text)
    assert left[0] == "0" and left[-1] == "1000"
    assert right[0] == "0" and right[-1] == "4"


def test_y_is_solid_and_y2_is_dashed_in_two_colours() -> None:
    text = _render_case(_case("typical"))
    y_marks, y2_marks = _series(text, 0), _series(text, 1)
    assert [m[0] for m in y_marks] == ["line", "dot", "dot"]
    assert [m[0] for m in y2_marks] == ["line", "dot"]
    assert {m[2] for m in y_marks if m[0] == "line"} == {None}
    assert {m[2] for m in y2_marks if m[0] == "line"} == {series_style(1).dash}
    assert series_style(1).dash is not None
    assert series_style(0).color != series_style(1).color
    assert len(_marks(text)) == len(y_marks) + len(y2_marks)


def test_the_legend_names_each_side() -> None:
    text = _render_case(_case("typical"))
    assert _legend_labels(text) == ["pace (left axis)", "heart rate (right axis)"]
    assert all(
        label.endswith(("(left axis)", "(right axis)"))
        for label in _legend_labels(text)
    )


def test_gridlines_number_the_left_axiss_ticks() -> None:
    rows = [(1.0, 0.0, 0.0), (2.0, 970.0, 3.2), (3.0, 400.0, 1.1)]
    text = _render((N, A, B), rows, NAB, {"y_zero": True, "y2_zero": True})
    _, left, right = _axes(text)
    left_ys, right_ys = _tick_ys(left), _tick_ys(right)
    assert len(left_ys) != len(right_ys)
    assert _grid_ys(text) == left_ys
    assert len(_grid_ys(text)) == len(_tick_labels(text)[0])


def test_the_typical_gridlines_follow_the_left_scale() -> None:
    text = _render_case(_case("typical"))
    _, left, right = _axes(text)
    assert _grid_ys(text) == _tick_ys(left)
    assert _grid_ys(text) != _tick_ys(right)


@pytest.mark.parametrize(
    ("y_zero", "y2_zero"), [(False, False), (True, False), (False, True), (True, True)]
)
def test_zero_is_included_in_the_axis_that_asks_for_it_only(
    y_zero: bool, y2_zero: bool
) -> None:
    text = _render(
        ZERO_COLUMNS,
        ZERO_ROWS,
        {"x": "day", "y": "a_bpm", "y2": "b_w"},
        {"y_zero": y_zero, "y2_zero": y2_zero},
    )
    left, right = _tick_labels(text)
    assert ("0" in left) is y_zero
    assert ("0" in right) is y2_zero


def test_each_axis_title_carries_its_own_column_and_unit() -> None:
    text = _render_case(_case("typical"))
    left_title, right_title = _title_texts(text)
    assert left_title.text == "pace (min/km)"
    assert right_title.text == "heart rate (bpm)"
    assert left_title.get("text-anchor") == "start"
    assert right_title.get("text-anchor") == "end"


def test_a_series_with_no_present_value_draws_an_empty_axis_not_zeros() -> None:
    rows = [(1.0, 10.0, None), (2.0, 20.0, None)]
    text = _render((N, A, B), rows, NAB)
    assert _series(text, 1) == []
    left, right = _tick_labels(text)
    assert left and right == []
    assert _legend_labels(text) == ["a (left axis)", "b (right axis)"]
    assert "Not drawn: 2 rows without y2." in _desc(text)
    assert "b (W) from" not in _desc(text)


# --- notes and description --------------------------------------------------------


def test_each_series_counts_its_own_absent_values() -> None:
    text = _render_case(_case("typical"))
    expected = "Not drawn: 1 row without x, 2 rows without y, 2 rows without y2."
    assert _note_lines(text) == [expected]
    assert _desc(text) == TYPICAL_DESCRIPTION


def test_a_row_with_neither_value_breaks_both_lines() -> None:
    rows = [(1.0, 2.0, 3.0), (2.0, None, None), (3.0, 4.0, 5.0)]
    text = _render((N, A, B), rows, NAB)
    for index in (0, 1):
        assert [(k, len(p)) for k, _, _, p in _series(text, index)] == [
            ("dot", 1),
            ("dot", 1),
        ]


def test_an_empty_left_series_draws_no_ticks_grid_or_range() -> None:
    rows = [(1.0, None, 5.0), (2.0, None, 7.0)]
    text = _render((N, A, B), rows, NAB)
    left, right = _tick_labels(text)
    assert left == [] and right
    assert _group(text, "ck-grid")[0].findall(f"{SVG}line") == []
    assert _series(text, 0) == []
    assert "a (bpm) from" not in _desc(text)
    assert "b (W) from 5 W to 7 W" in _desc(text)
    assert "Not drawn: 2 rows without y." in _desc(text)


def test_a_row_absent_on_both_values_is_counted_under_both() -> None:
    rows = [(1.0, 2.0, 3.0), (2.0, None, None), (3.0, 4.0, 5.0)]
    text = _render((N, A, B), rows, NAB)
    assert _note_lines(text) == ["Not drawn: 1 row without y, 1 row without y2."]


def test_a_row_without_x_is_counted_under_x_alone() -> None:
    rows = [(1.0, 2.0, 3.0), (None, None, 1.0), (3.0, 4.0, 5.0)]
    text = _render((N, A, B), rows, NAB)
    assert _note_lines(text) == ["Not drawn: 1 row without x."]


def test_a_complete_chart_has_no_note() -> None:
    text = _render((N, A, B), [(1.0, 2.0, 3.0), (2.0, 3.0, 4.0)], NAB)
    assert _group(text, "ck-notes") == []
    assert "Not drawn" not in _desc(text)


def test_no_rows_is_the_no_data_state() -> None:
    text = _render_case(_case("empty"))
    assert "No data: no rows." in _desc(text)


def test_rows_without_a_drawable_value_are_the_no_data_state() -> None:
    text = _render_case(_case("all_absent"))
    assert "None of the 3 rows has a value to draw." in text


def test_a_duration_axis_is_titled_and_described_in_its_own_form() -> None:
    moving = column("moving_s", unit="s")
    rows = [(1.0, 1500.0, 100.0), (2.0, 2700.0, 120.0), (3.0, 2000.0, 110.0)]
    text = _render((N, moving, B), rows, {"x": "n", "y": "moving_s", "y2": "b_w"})
    left_title, _ = _title_texts(text)
    assert left_title.text == "moving (m:ss)"
    assert left_title.text is not None and "moving (m:ss) from 25:00 to 45:00" in _desc(
        text
    )
    assert _tick_labels(text)[0][0] == "25:00"


def test_an_hours_duration_axis_is_titled_and_described_in_hours_form() -> None:
    moving = column("moving_s", unit="s")
    rows = [(1.0, 1500.0, 100.0), (2.0, 7200.0, 120.0)]
    text = _render((N, moving, B), rows, {"x": "n", "y": "moving_s", "y2": "b_w"})
    left_title, _ = _title_texts(text)
    assert left_title.text == "moving (h:mm:ss)"
    assert "moving (h:mm:ss) from 0:25:00 to 2:00:00" in _desc(text)


# --- the two y titles share one row without overlapping -------------------------


@pytest.mark.parametrize("width", [720, 320])
def test_two_long_titles_do_not_overlap(width: int) -> None:
    request = chart_request(
        "dual-axis",
        ref="d1",
        title="Power and cadence",
        channels=LONG_CHANNELS,
        options={"width": width},
    )
    text = render_case(
        KIND, request, chart_data((LONG_X, LONG_Y, LONG_Y2), LONG_ROWS)
    ).text
    left, right = _title_texts(text)
    assert (left.text or "").endswith("…") and (right.text or "").endswith("…")
    left_end = float(left.get("x") or "nan") + text_width(
        left.text or "", float(left.get("font-size") or "nan")
    )
    right_start = float(right.get("x") or "nan") - text_width(
        right.text or "", float(right.get("font-size") or "nan")
    )
    assert left_end <= right_start - PAD + 1e-6
    # the fitted pair fills the shared row: neither collapsed to a stub
    assert len(left.text or "") > 10 and len(right.text or "") > 10


# --- goldens -------------------------------------------------------------------


def test_cases_are_the_designed_names() -> None:
    assert [case.name for case in CASES] == [
        "typical",
        "empty",
        "all_absent",
        "single",
        "negative",
        "zero",
        "long_labels",
        "at_bound",
    ]


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.name)
def test_golden(case: Case) -> None:
    rendered = render_case(KIND, case.request, case.data)
    assert rendered.kind == "dual-axis"
    assert rendered.output is Output.SVG
    assert_golden(golden_path("dual-axis", case.name, "svg"), rendered.text)


def test_no_stale_goldens() -> None:
    directory = golden_path("dual-axis", "x", "svg").parent
    on_disk = sorted(path.name for path in directory.iterdir())
    assert on_disk == sorted(f"{case.name}.svg" for case in CASES)


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.name)
def test_every_text_stays_inside_the_chart(case: Case) -> None:
    svg = _render_case(case)
    root = _root(svg)
    width = float(root.get("width") or "nan")
    texts = _texts(root)
    assert len(texts) == svg.count("<text ")
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


@pytest.mark.parametrize("width", [320, 720])
def test_long_labels_stay_inside_the_chart_at_both_widths(width: int) -> None:
    request = chart_request(
        "dual-axis",
        ref="d1",
        title=LONG_TITLE,
        channels=LONG_CHANNELS,
        options={"width": width},
    )
    root = _root(
        render_case(
            KIND, request, chart_data((LONG_X, LONG_Y, LONG_Y2), LONG_ROWS)
        ).text
    )
    texts = _texts(root)
    assert len(texts) > 8
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
    assert any(r[1] is None and r[2] is not None for r in TYPICAL_ROWS)
    assert any(r[2] is None and r[1] is not None for r in TYPICAL_ROWS)
    assert any(r[0] is None for r in TYPICAL_ROWS)
    assert any(r[1] is None and r[2] is None and r[0] is not None for r in TYPICAL_ROWS)


def test_long_labels_golden_is_shortened() -> None:
    text = _render_case(_case("long_labels"))
    assert text.count("…") >= 4


def test_at_bound_golden_is_at_the_bound() -> None:
    case = _case("at_bound")
    assert len(case.data.rows) == LIMIT == KIND.bound.limit


def test_zero_golden_data_sits_away_from_zero() -> None:
    assert min(r[1] for r in ZERO_ROWS if isinstance(r[1], float)) > 100
    assert min(r[2] for r in ZERO_ROWS if isinstance(r[2], float)) > 200


def main() -> None:
    for case in CASES:
        write_golden(golden_path("dual-axis", case.name, "svg"), _render_case(case))


if __name__ == "__main__":
    main()
