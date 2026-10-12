"""The ``calendar-heatmap`` kind: grid geometry, cell classes, refusals, goldens.

Regenerate the goldens with
``uv run python -m tests.render.charts.kit.test_calendar_heatmap``.
"""

from __future__ import annotations

import math
import re
import xml.etree.ElementTree as ET
from collections.abc import Sequence
from datetime import date, timedelta
from typing import NamedTuple

import pytest

from fitdocs.render.charts.kit.data import Column, Value, ValueKind
from fitdocs.render.charts.kit.kinds.calendar_heatmap import KIND
from fitdocs.render.charts.kit.problems import ChartProblem, ProblemCode
from fitdocs.render.charts.kit.schema import ChannelSpec, MarkBound, Output, OverBound
from fitdocs.render.charts.kit.theme import STROKE, ink
from fitdocs.render.charts.palette import SEQUENTIAL_RAMP
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

DAY = column("day", ValueKind.DATE)
KM = column("distance_km", unit="km")
CHANNELS = {"date": "day", "value": "distance_km"}
TITLE = "Daily distance"

# Title baseline 21, legend top 29, 18 px per legend row; below the plot the
# tick labels (19), the x title (16), the bottom pad (8) and 15 px per note.
LEGEND_TOP = 29
LEGEND_ROW = 18
BELOW_PLOT = 19 + 16 + 8
NOTE_ROW = 15
CELL_GAP = 1.0  # a cell is inset by this on each side of its pitch box

THURSDAY = date(2025, 3, 6)
MONDAY = date(2025, 3, 3)


def _case(
    name: str,
    rows: Sequence[Sequence[Value]],
    *,
    columns: Sequence[Column] = (DAY, KM),
    title: str = TITLE,
    options: dict[str, int] | None = None,
) -> Case:
    request = chart_request(
        "calendar-heatmap",
        title=title,
        channels={"date": columns[0].name, "value": columns[1].name},
        options=options,
    )
    return Case(name, request, chart_data(columns, rows))


def _svg(
    rows: Sequence[Sequence[Value]],
    *,
    columns: Sequence[Column] = (DAY, KM),
    width: int | None = None,
    height: int | None = None,
) -> str:
    options: dict[str, int] = {}
    if width is not None:
        options["width"] = width
    if height is not None:
        options["height"] = height
    case = _case("t", rows, columns=columns, options=options)
    return render_case(KIND, case.request, case.data).text


def _problems(
    rows: Sequence[Sequence[Value]], *, columns: Sequence[Column] = (DAY, KM)
) -> tuple[ChartProblem, ...]:
    case = _case("t", rows, columns=columns)
    return problems_of(KIND, case.request, case.data)


# ---------------------------------------------------------------- svg readers


def _root(svg: str) -> ET.Element:
    return ET.fromstring(svg)


def _groups(svg: str, css_class: str) -> list[ET.Element]:
    return [g for g in _root(svg).iter(f"{SVG}g") if g.get("class") == css_class]


def _num(value: str | None) -> float:
    assert value is not None
    return float(value)


def _desc(svg: str) -> str:
    element = _root(svg).find(f"{SVG}desc")
    assert element is not None and element.text is not None
    return element.text


def _body_classes(svg: str) -> list[str]:
    """The class of each top-level body element; the title text has class ``ck-t``."""
    out: list[str] = []
    for child in _root(svg):
        tag = child.tag.removeprefix(SVG)
        if tag in ("title", "desc", "style"):
            continue
        out.append(child.get("class") or tag)
    return out


class Plot(NamedTuple):
    left: float
    right: float
    bottom: float


def _plot(svg: str) -> Plot:
    """The date axis baseline: the first line of the axis group that holds the
    middle-anchored tick labels."""
    for group in _groups(svg, "ck-axis"):
        if any(t.get("text-anchor") == "middle" for t in group.iter(f"{SVG}text")):
            line = next(iter(group.iter(f"{SVG}line")))
            return Plot(
                _num(line.get("x1")), _num(line.get("x2")), _num(line.get("y1"))
            )
    raise AssertionError("no date axis")


def _date_ticks(svg: str) -> list[tuple[float, str]]:
    """The date axis tick marks' x and their labels, left to right."""
    for group in _groups(svg, "ck-axis"):
        if any(t.get("text-anchor") == "middle" for t in group.iter(f"{SVG}text")):
            xs = [
                _num(line.get("x1"))
                for line in group.iter(f"{SVG}line")
                if line.get("y1") != line.get("y2")
            ]
            labels = [
                t.text or ""
                for t in group.iter(f"{SVG}text")
                if t.get("text-anchor") == "middle"
            ][: len(xs)]
            return list(zip(xs, labels, strict=True))
    raise AssertionError("no date axis")


def _weekday_labels(svg: str) -> list[tuple[str, float, float]]:
    """(text, x, y) of the end-anchored labels left of the grid."""
    return [
        (t.text or "", _num(t.get("x")), _num(t.get("y")))
        for group in _groups(svg, "ck-axis")
        for t in group.iter(f"{SVG}text")
        if t.get("text-anchor") == "end"
    ]


NUMBER = r"(-?[0-9.]+)"
BOX = re.compile(rf"M{NUMBER} {NUMBER}H{NUMBER}V{NUMBER}H{NUMBER}Z")
CROSS = re.compile(
    rf"M{NUMBER} {NUMBER}L{NUMBER} {NUMBER}M{NUMBER} {NUMBER}L{NUMBER} {NUMBER}"
)


class Mark(NamedTuple):
    kind: str  # "bin", "zero" or "absent"
    x: float  # centre
    y: float
    side: float
    fill: str | None


def _marks(svg: str) -> list[Mark]:
    """Every cell mark of the grid, in document order (back to front)."""
    (group,) = _groups(svg, "ck-marks")
    out: list[Mark] = []
    for path in group.iter(f"{SVG}path"):
        d = path.get("d") or ""
        if path.get("fill") != "none":
            for m in BOX.finditer(d):
                a, b, c, e, _ = (float(g) for g in m.groups())
                out.append(
                    Mark("bin", (a + c) / 2, (b + e) / 2, c - a, path.get("fill"))
                )
        elif path.get("stroke") == SEQUENTIAL_RAMP[0]:
            for m in BOX.finditer(d):
                a, b, c, e, _ = (float(g) for g in m.groups())
                out.append(Mark("zero", (a + c) / 2, (b + e) / 2, c - a, None))
        else:
            assert path.get("stroke") == "#7f7f7f"
            for m in CROSS.finditer(d):
                a, b, c, e, *_ = (float(g) for g in m.groups())
                out.append(Mark("absent", (a + c) / 2, (b + e) / 2, c - a, None))
    return out


def _columns(svg: str) -> set[int]:
    """The week column index of every cell (centres are rounded to 0.01 px)."""
    plot = _plot(svg)
    pitch = _pitch(svg)
    return {math.floor((m.x - plot.left) / pitch) for m in _marks(svg)}


def _texts(svg: str) -> list[str]:
    return [t.text or "" for t in _root(svg).iter(f"{SVG}text")]


def _legend_texts(svg: str) -> list[str]:
    (legend,) = _groups(svg, "ck-legend")
    return [t.text or "" for t in legend.iter(f"{SVG}text")]


def _legend_rows(svg: str) -> int:
    (legend,) = _groups(svg, "ck-legend")
    return len({t.get("y") for t in legend.iter(f"{SVG}text")})


def _note_lines(svg: str) -> list[str]:
    return [
        t.text or "" for g in _groups(svg, "ck-notes") for t in g.iter(f"{SVG}text")
    ]


def _pitch(svg: str) -> float:
    """The grid pitch, from the Monday and Sunday labels (six rows apart)."""
    labels = _weekday_labels(svg)
    return (labels[3][2] - labels[0][2]) / 6


# --------------------------------------------------------------------- data


def _typical_rows() -> list[tuple[Value, Value]]:
    """About six months from a Thursday: zeros, absent values, missing days, two
    rows without a date, and rows out of date order."""
    rows: list[tuple[Value, Value]] = []
    for i in range(180):
        if i % 11 == 5:
            continue  # no row on this day
        day = THURSDAY + timedelta(days=i)
        if i % 13 == 7:
            rows.append((day, None))
        elif i % 9 == 4:
            rows.append((day, 0.0))
        else:
            rows.append((day, round(1.5 + ((i * 7) % 23) * 0.75, 2)))
    shuffled = rows[1::2][::-1] + rows[0::2]
    shuffled.insert(3, (None, 4.0))
    shuffled.insert(40, (None, None))
    return shuffled


def _year_rows() -> list[tuple[Value, Value]]:
    """366 consecutive days from a Sunday: 54 Monday-start week columns."""
    start = date(2023, 1, 1)
    rows: list[tuple[Value, Value]] = []
    for i in range(366):
        day = start + timedelta(days=i)
        if i % 17 == 3:
            rows.append((day, None))
        elif i % 7 == 2:
            rows.append((day, 0.0))
        else:
            rows.append((day, round(1.0 + ((i * 5) % 19) * 0.5, 1)))
    return rows[1::2][::-1] + rows[0::2]


LONG_COLUMN = column(
    "load",
    label="Total training load accumulated over the whole of the calendar day",
    unit="km",
)
SECONDS = column("moving_time", ValueKind.DURATION)


def _secs(*values: float | None) -> list[Value]:
    return [None if v is None else timedelta(seconds=v) for v in values]


DURATION_DAYS = [
    date(2025, 5, 14),
    date(2025, 5, 1),
    date(2025, 5, 22),
    date(2025, 5, 9),
    date(2025, 5, 17),
    date(2025, 5, 5),
    date(2025, 5, 12),
]
DURATION_VALUES = _secs(5400, 600, 7200, 0, None, 2400, 3600)

CASES: tuple[Case, ...] = (
    _case("typical", _typical_rows()),
    _case("empty", []),
    _case(
        "all_absent",
        [(date(2025, 4, 9), None), (date(2025, 4, 2), None), (date(2025, 4, 15), None)],
    ),
    _case(
        "absent_dates",
        [(None, 3.0), (None, None), (None, 0.0)],
    ),
    _case("single", [(date(2025, 6, 12), 4.5)]),
    _case(
        "constant",
        [(date(2025, 2, 12) - timedelta(days=d), 5.0) for d in (0, 9, 3, 6, 1, 8, 4)],
    ),
    _case(
        "all_zero",
        [(date(2025, 2, 12) - timedelta(days=d), 0.0) for d in (4, 0, 9, 2, 7)],
    ),
    _case(
        "durations",
        list(zip(DURATION_DAYS, DURATION_VALUES, strict=True)),
        columns=(DAY, SECONDS),
    ),
    _case(
        "long_labels",
        [(date(2025, 8, 20), 6.0), (date(2025, 8, 4), 2.5), (date(2025, 8, 11), 4.0)],
        columns=(DAY, LONG_COLUMN),
        title="A calendar chart title long enough that it cannot fit the width of the "
        "chart and must be cut with an ellipsis before it reaches the edge",
    ),
    _case("at_bound", _year_rows()),
)


# ------------------------------------------------------------ the declaration


def test_description_travels_with_the_registry_guidance() -> None:
    assert "negative values are refused" in KIND.description
    assert "a day with no row draws nothing" in KIND.description


def test_declaration() -> None:
    assert KIND.name == "calendar-heatmap"
    assert KIND.output is Output.SVG
    assert [c.name for c in KIND.channels] == ["date", "value"]
    assert all(isinstance(c, ChannelSpec) and c.required for c in KIND.channels)
    assert KIND.channels[0].accepts == (ValueKind.DATE,)
    assert KIND.channels[1].accepts == (ValueKind.NUMBER, ValueKind.DURATION)
    assert isinstance(KIND.bound, MarkBound)
    assert (KIND.bound.limit, KIND.bound.counts, KIND.bound.over) == (
        54,
        "weeks",
        OverBound.REFUSE,
    )
    height = next(o for o in KIND.options if o.name == "height")
    assert height.default is None


# ------------------------------------------------------------------ geometry


def test_a_sunday_lands_in_row_six_of_the_previous_mondays_column() -> None:
    # Rows out of order: Monday (3.0), Sunday (1.0), Thursday (2.0).
    svg = _svg([(date(2025, 3, 10), 3.0), (date(2025, 3, 9), 1.0), (THURSDAY, 2.0)])
    sunday, thursday, monday = _marks(svg)  # bins 1, 2, 3 are drawn in that order
    assert [m.kind for m in (sunday, thursday, monday)] == ["bin"] * 3
    pitch = _pitch(svg)
    assert pitch == 20.0
    # Thursday is row 3 of column 0; Sunday is row 6 of the same column; the
    # Monday after is row 0 of the next column.
    assert sunday.x == thursday.x
    assert sunday.y - thursday.y == pytest.approx(3 * pitch)
    assert monday.x - thursday.x == pytest.approx(pitch)
    assert thursday.y - monday.y == pytest.approx(3 * pitch)


def test_the_grid_starts_on_the_monday_before_a_thursday_first_date() -> None:
    svg = _svg([(date(2025, 3, 10), 3.0), (THURSDAY, 2.0)])
    plot = _plot(svg)
    pitch = _pitch(svg)
    thursday = min(_marks(svg), key=lambda m: m.x)
    # Column 0 is the week of Monday 3 March: the Thursday sits half a pitch
    # right of the plot edge, the grid's left edge.
    assert thursday.x == pytest.approx(plot.left + pitch / 2)
    ticks = dict((label, x) for x, label in _date_ticks(svg))
    assert ticks["2025-03-03"] == pytest.approx(plot.left)
    assert ticks["2025-03-17"] == pytest.approx(plot.left + 2 * pitch)


def test_weekday_labels_name_rows_zero_two_four_and_six() -> None:
    # One full week, seven distinct values, rows out of order.
    order = (4, 1, 6, 0, 3, 5, 2)
    svg = _svg([(MONDAY + timedelta(days=d), float(d + 1)) for d in order])
    labels = _weekday_labels(svg)
    assert [name for name, _, _ in labels] == ["Mon", "Wed", "Fri", "Sun"]
    assert {x for _, x, _ in labels} == {_plot(svg).left - 8.0}  # tick length + gap
    centres = sorted(m.y for m in _marks(svg))
    assert len(centres) == 7
    # The label baseline sits 4 px under the centre of its row.
    assert [y - 4 for _, _, y in labels] == pytest.approx(
        [centres[0], centres[2], centres[4], centres[6]]
    )
    grid = _groups(svg, "ck-axis")[1]
    assert all(t.get("text-anchor") == "end" for t in grid.iter(f"{SVG}text"))


def test_54_week_columns_render_and_55_refuse() -> None:
    first = date(2025, 1, 6)  # a Monday
    last_of_54 = first + timedelta(days=54 * 7 - 1)  # the Sunday of column 53
    ok = _svg([(first, 1.0), (last_of_54, 2.0), (first + timedelta(days=100), 3.0)])
    assert len(_marks(ok)) == 3
    over = [(first, 1.0), (last_of_54 + timedelta(days=1), 2.0)]
    (problem,) = _problems(over)
    assert problem.code is ProblemCode.OVER_BOUND
    assert problem.message == (
        "calendar-heatmap draws at most 54 weeks; these dates span 55."
    )
    assert problem.fix == (
        "Limit the rows to at most 54 weeks of dates, for example the last 365 days."
    )
    assert (problem.channel, problem.column, problem.rows) == ("date", "day", 55)


def test_any_366_consecutive_days_fit_54_columns() -> None:
    sunday = date(2023, 1, 1)
    rows = [(sunday + timedelta(days=i), 1.0 + (i % 5)) for i in range(366)]
    svg = _svg(rows)
    assert len(_marks(svg)) == 366
    assert len(_columns(svg)) == 54


def test_the_week_count_runs_from_the_mondays_before_the_first_date() -> None:
    sunday = date(2023, 1, 1)  # column 0 holds the Sunday of the week of 26 Dec
    ok = _svg([(sunday, 1.0), (sunday + timedelta(days=7 * 53), 2.0)])
    assert _columns(ok) == {0, 53}
    # The Monday 372 days on is column 54: 55 columns, though only 53 weeks and a
    # day after the first date.
    (problem,) = _problems([(sunday, 1.0), (sunday + timedelta(days=7 * 53 + 1), 2.0)])
    assert "span 55" in problem.message


def test_cells_are_20_px_for_a_three_week_span_and_on_a_wide_chart() -> None:
    top_bin = [(MONDAY, 5.0), (MONDAY + timedelta(days=14), 5.0)]  # 3 columns
    svg = _svg(top_bin)
    marks = _marks(svg)
    assert _pitch(svg) == 20.0
    assert {m.side for m in marks} == {20.0 - 2 * CELL_GAP}
    assert marks[1].x - marks[0].x == pytest.approx(2 * 20.0)
    # A wide chart with 41 week columns still draws 20 px cells.
    wide = _svg(
        [(MONDAY, 5.0), (MONDAY + timedelta(days=7 * 40), 5.0)], width=1600, height=400
    )
    assert _pitch(wide) == 20.0


def test_the_pitch_is_the_plot_width_over_the_week_columns_when_below_20_px() -> None:
    svg = _svg(_year_rows())
    plot = _plot(svg)
    assert _pitch(svg) == pytest.approx((plot.right - plot.left) / 54, abs=0.01)
    assert _pitch(svg) < 20.0


def test_a_single_date_draws_one_normal_cell() -> None:
    svg = _svg([(date(2025, 6, 12), 4.5)])
    (mark,) = _marks(svg)
    assert _pitch(svg) == 20.0
    assert mark.side == 18.0
    assert _legend_texts(svg)[-1] == "≤ 5"  # the bins enclose the value 4.5


def test_equal_values_fill_the_top_bin_with_edges_enclosing_the_value() -> None:
    svg = _svg([(MONDAY + timedelta(days=d), 5.0) for d in (3, 0, 5)])
    marks = _marks(svg)
    assert {m.fill for m in marks} == {SEQUENTIAL_RAMP[-1]}
    assert _legend_texts(svg)[-1] == "≤ 5"
    assert {m.side for m in marks} == {18.0}


def test_an_explicit_height_is_honoured_and_the_rows_fit_inside_it() -> None:
    rows = [(MONDAY, 5.0), (MONDAY + timedelta(days=6), 5.0)]
    for height in (160, 400):
        svg = _svg(rows, height=height)
        assert _root(svg).get("height") == str(height)
        bottom = max(m.y + m.side / 2 for m in _marks(svg))
        assert bottom <= _plot(svg).bottom
        assert len(_marks(svg)) == 2
    assert _pitch(_svg(rows, height=160)) < 20.0
    assert _pitch(_svg(rows, height=400)) == 20.0


def test_auto_height_is_the_seven_rows_plus_the_frame() -> None:
    def expected(svg: str, pitch: float, notes: int) -> int:
        top = LEGEND_TOP + LEGEND_ROW * _legend_rows(svg)
        return math.ceil(top + 7 * pitch + BELOW_PLOT + NOTE_ROW * notes)

    svg = _svg([(MONDAY, 5.0), (MONDAY + timedelta(days=14), 0.0)])
    assert _pitch(svg) == 20.0
    assert _num(_root(svg).get("height")) == expected(svg, 20.0, 0) == 230
    noted = _svg([(MONDAY, 5.0), (None, 1.0), (MONDAY + timedelta(days=14), 0.0)])
    assert _num(_root(noted).get("height")) == expected(noted, 20.0, 1) == 245
    wide = _svg([(MONDAY + timedelta(days=7 * 40), 5.0), (MONDAY, 2.0)])
    pitch = _pitch(wide)
    assert pitch < 20.0
    assert _num(_root(wide).get("height")) == expected(wide, pitch, 0)


def test_auto_height_has_a_floor_of_160() -> None:
    svg = _svg([(MONDAY, 1.0), (MONDAY + timedelta(days=7 * 50), 2.0)], width=320)
    assert _pitch(svg) < 6.0
    assert _root(svg).get("height") == "160"


# ----------------------------------------------------------- refusals


def test_a_duplicate_date_refuses_naming_the_row_and_the_date() -> None:
    rows: list[tuple[Value, Value]] = [
        (date(2025, 3, 8), 1.0),
        (date(2025, 3, 5), 2.0),
        (date(2025, 3, 9), 3.0),
        (date(2025, 3, 5), 4.0),
        (date(2025, 3, 7), 5.0),
    ]
    (problem,) = _problems(rows)
    assert problem.code is ProblemCode.DUPLICATE_POSITION
    assert problem.row == 3
    assert problem.message == (
        "Row 3 repeats row 1, which has the same day (2025-03-05)."
    )


def test_rows_without_a_date_are_not_duplicates_of_each_other() -> None:
    svg = _svg([(MONDAY, 2.0), (None, 1.0), (None, 1.0)])
    assert len(_marks(svg)) == 1


def test_a_negative_value_refuses_naming_the_first_row_and_the_count() -> None:
    rows: list[tuple[Value, Value]] = [
        (date(2025, 3, 8), 1.0),
        (date(2025, 3, 5), 2.0),
        (date(2025, 3, 9), -3.0),
        (date(2025, 3, 6), 4.0),
        (date(2025, 3, 7), -0.5),
    ]
    (problem,) = _problems(rows)
    assert problem.code is ProblemCode.NEGATIVE_VALUE
    assert (problem.row, problem.rows, problem.channel) == (2, 2, "value")
    assert "distance has a negative value at row 2" in problem.message
    assert "calendar-heatmap shades values from zero up" in problem.message


def test_problems_come_in_the_stage_three_order() -> None:
    first = date(2025, 1, 6)
    rows: list[tuple[Value, Value]] = [
        (first, 1.0),
        (first, -1.0),
        (first + timedelta(days=7 * 55), 2.0),
    ]
    assert [p.code for p in _problems(rows)] == [
        ProblemCode.OVER_BOUND,
        ProblemCode.DUPLICATE_POSITION,
        ProblemCode.NEGATIVE_VALUE,
    ]


# ------------------------------------------------------------ cell classes


def test_absent_date_is_counted_in_the_note_and_the_description() -> None:
    svg = _svg(
        [(MONDAY, 2.0), (None, 1.0), (MONDAY + timedelta(days=2), 3.0), (None, None)]
    )
    assert _note_lines(svg) == ["Not drawn: 2 rows without date."]
    assert "Not drawn: 2 rows without date." in _desc(svg)
    assert len(_marks(svg)) == 2
    one = _svg([(MONDAY, 2.0), (None, 1.0)])
    assert _note_lines(one) == ["Not drawn: 1 row without date."]


def test_rows_without_a_date_do_not_shape_the_scale_or_the_legend() -> None:
    # The unplaced rows hold the largest value, a zero and an absent value.
    svg = _svg(
        [(None, 100.0), (MONDAY + timedelta(days=2), 2.0), (None, 0.0), (None, None)]
    )
    assert _legend_texts(svg) == ["distance (km)", "≤ 1", "≤ 2"]
    assert _desc(svg).endswith(
        "day from 2025-03-05 to 2025-03-05; distance (km) from 2.0 km to 2.0 km."
    )


def test_an_absent_value_is_drawn_as_a_cross_and_is_not_counted() -> None:
    svg = _svg([(MONDAY, 2.0), (MONDAY + timedelta(days=1), None)])
    assert [m.kind for m in _marks(svg)] == ["bin", "absent"]
    assert _note_lines(svg) == []
    assert "Not drawn" not in _desc(svg)


def test_one_absent_value_one_zero_and_one_missing_day() -> None:
    # Mon bin, Tue absent, (Wed has no row), Thu zero, Fri bin; out of order.
    svg = _svg(
        [
            (MONDAY + timedelta(days=4), 2.0),
            (MONDAY + timedelta(days=3), 0.0),
            (MONDAY, 4.0),
            (MONDAY + timedelta(days=1), None),
        ]
    )
    marks = _marks(svg)
    by_kind = sorted(marks, key=lambda m: m.kind)
    assert [m.kind for m in by_kind] == ["absent", "bin", "bin", "zero"]
    pitch = _pitch(svg)
    rows = sorted((m.y, m.kind) for m in marks)
    top = rows[0][0]
    assert [(round((y - top) / pitch), kind) for y, kind in rows] == [
        (0, "bin"),
        (1, "absent"),
        (3, "zero"),
        (4, "bin"),
    ]
    paths = list(_groups(svg, "ck-marks")[0].iter(f"{SVG}path"))
    outline = [p for p in paths if p.get("stroke") == SEQUENTIAL_RAMP[0]]
    cross = [p for p in paths if p.get("fill") == "none" and p not in outline]
    assert len(outline) == len(cross) == 1
    assert (outline[0].get("d") or "").count("M") == 1
    assert (cross[0].get("d") or "").count("M") == 2


def test_the_cross_uses_the_theme_stroke_class() -> None:
    svg = _svg([(MONDAY, None), (MONDAY + timedelta(days=1), 1.0)])
    cross = next(
        p
        for p in _groups(svg, "ck-marks")[0].iter(f"{SVG}path")
        if p.get("fill") == "none"
    )
    assert cross.get("class") == ink(STROKE)["class"]


def test_dates_with_every_value_absent_draw_crosses_not_the_no_data_state() -> None:
    svg = _svg([(MONDAY + timedelta(days=d), None) for d in (4, 1, 2)])
    assert [m.kind for m in _marks(svg)] == ["absent"] * 3
    assert _legend_texts(svg) == ["distance (km)", "no value"]
    assert "No data" not in _texts(svg)
    assert "No data" not in _desc(svg)
    assert "3 rows" in _desc(svg)
    assert _desc(svg).endswith("day from 2025-03-04 to 2025-03-07.")


def test_every_date_absent_draws_the_no_data_state_with_its_second_line() -> None:
    svg = _svg([(None, 1.0), (None, None), (None, 0.0)])
    assert "No data" in _texts(svg)
    assert "None of the 3 rows has a value to draw." in _texts(svg)
    assert _groups(svg, "ck-marks") == []
    assert _desc(svg).endswith("No data: none of the 3 rows has a value to draw.")


def test_no_rows_draws_the_no_data_state_without_a_second_line() -> None:
    svg = _svg([])
    assert "No data" in _texts(svg)
    assert not any(t.startswith("None of the") for t in _texts(svg))
    assert _desc(svg).endswith("No data: no rows.")
    assert _root(svg).get("height") == "160"
    assert _root(_svg([], height=300)).get("height") == "300"
    assert _root(_svg([(None, 1.0)], height=300)).get("height") == "300"


def test_all_zero_draws_outlines_and_a_legend_without_bins() -> None:
    svg = _svg([(MONDAY + timedelta(days=d), 0.0) for d in (2, 0, 5)])
    assert [m.kind for m in _marks(svg)] == ["zero"] * 3
    assert _legend_texts(svg) == ["distance (km)", "0"]


def test_a_zero_with_an_absent_value_lists_both_entries() -> None:
    svg = _svg([(MONDAY, 0.0), (MONDAY + timedelta(days=1), None)])
    assert _legend_texts(svg) == ["distance (km)", "0", "no value"]


# ----------------------------------------------------------- durations, text


def test_a_duration_chart_titles_and_ranges_in_the_form_of_its_edges() -> None:
    days = [date(2025, 5, 14), date(2025, 5, 1), date(2025, 5, 22)]
    long = _svg(
        list(zip(days, _secs(5400, 600, 7200), strict=True)), columns=(DAY, SECONDS)
    )
    assert _legend_texts(long)[0] == "moving time (h:mm:ss)"
    assert _legend_texts(long)[1:] == [
        "≤ 0:30:00",
        "≤ 1:00:00",
        "≤ 1:30:00",
        "≤ 2:00:00",
    ]
    assert _desc(long).endswith("moving time (h:mm:ss) from 0:10:00 to 2:00:00.")
    short = _svg(
        list(zip(days, _secs(900, 300, 2700), strict=True)), columns=(DAY, SECONDS)
    )
    assert _legend_texts(short)[0] == "moving time (m:ss)"
    assert all(":" in t and t.count(":") == 1 for t in _legend_texts(short)[1:])
    assert _desc(short).endswith("moving time (m:ss) from 5:00 to 45:00.")
    assert "value: moving time (m:ss)" in _desc(short)


def test_the_range_form_follows_the_edges_not_the_values() -> None:
    # The largest value is under an hour but the last edge reaches it.
    svg = _svg(
        list(zip([date(2025, 5, 14), date(2025, 5, 1)], _secs(3500, 300), strict=True)),
        columns=(DAY, SECONDS),
    )
    assert _legend_texts(svg)[0] == "moving time (h:mm:ss)"
    assert _desc(svg).endswith("moving time (h:mm:ss) from 0:05:00 to 0:58:20.")


def test_the_description_names_each_drawn_title_and_range() -> None:
    svg = _svg(
        [
            (date(2025, 3, 20), 9.5),
            (date(2025, 3, 6), 1.5),
            (None, 2.0),
            (date(2025, 3, 11), None),
        ]
    )
    assert _desc(svg) == (
        "Calendar-heatmap chart: Daily distance. date: day; value: distance (km). "
        "4 rows. Not drawn: 1 row without date. "
        "day from 2025-03-06 to 2025-03-20; distance (km) from 1.5 km to 9.5 km."
    )


def test_a_pace_value_range_carries_its_unit() -> None:
    pace = column("pace_s_per_km", unit="s_per_km")
    svg = _svg(
        [(MONDAY + timedelta(days=1), 330.0), (MONDAY, 245.0)], columns=(DAY, pace)
    )
    assert _desc(svg).endswith("pace (min/km) from 4:05 /km to 5:30 /km.")


def test_long_labels_are_cut_with_an_ellipsis() -> None:
    case = next(c for c in CASES if c.name == "long_labels")
    text = render_case(KIND, case.request, case.data).text
    assert "…" in text
    assert any("…" in t for t in _legend_texts(text))
    assert any(t.endswith("…") for t in _texts(text) if t.startswith("A calendar"))


def _extents(svg: str) -> list[tuple[str, float, float]]:
    out: list[tuple[str, float, float]] = []
    for t in _root(svg).iter(f"{SVG}text"):
        content = t.text or ""
        size = _num(t.get("font-size"))
        w = len(content) * size * 0.64
        x = _num(t.get("x"))
        anchor = t.get("text-anchor")
        left = x - w if anchor == "end" else x - w / 2 if anchor == "middle" else x
        out.append((content, left, left + w))
    return out


NARROW = _case(
    "narrow",
    [(date(2023, 2, 6), 1.0), (date(2023, 12, 31), 2.0), (date(2023, 6, 14), 3.0)],
    options={"width": 320},
)


WIDE_NARROW_DATA = _case(
    "narrow_1000",
    [(date(2023, 2, 6), 1.0), (date(2023, 12, 31), 2.0), (date(2023, 6, 14), 3.0)],
    options={"width": 1000},
)
WEEKS_40 = _case(
    "weeks_40_at_859",
    [(date(2023, 3, 27), 1.0), (date(2023, 3, 27) + timedelta(days=40 * 7 - 1), 2.0)],
    options={"width": 859},
)
# Overshoots by about 0.76 px when the reserve is measured against plot.right.
WEEKS_53 = _case(
    "weeks_53_at_1125",
    [(date(2023, 3, 27), 1.0), (date(2023, 3, 27) + timedelta(days=53 * 7 - 1), 2.0)],
    options={"width": 1125},
)


@pytest.mark.parametrize(
    "case",
    (*CASES, NARROW, WIDE_NARROW_DATA, WEEKS_40, WEEKS_53),
    ids=lambda case: case.name,
)
def test_every_text_stays_inside_the_chart(case: Case) -> None:
    svg = render_case(KIND, case.request, case.data).text
    width = _num(_root(svg).get("width"))
    texts = _extents(svg)
    assert len(texts) == len(list(_root(svg).iter(f"{SVG}text"))) > 0
    for content, left, right in texts:
        assert left >= 8.0 - 1e-6, content
        assert right <= width - 4.0 + 1e-6, content


# ---------------------------------------------------------------- structure


def test_body_order_is_marks_axes_legend_title_notes() -> None:
    svg = _svg([(MONDAY, 2.0), (None, 1.0), (MONDAY + timedelta(days=9), 0.0)])
    assert _body_classes(svg) == [
        "ck-marks",
        "ck-axis",
        "ck-axis",
        "ck-legend",
        "ck-t",
        "ck-notes",
    ]


def test_no_gridlines_are_drawn() -> None:
    svg = _svg(_year_rows())
    assert not [
        line
        for line in _root(svg).iter(f"{SVG}line")
        if line.get("stroke-opacity") is not None
    ]


# ----------------------------------------------------------------- goldens


def test_cases_are_the_designed_names() -> None:
    assert [case.name for case in CASES] == [
        "typical",
        "empty",
        "all_absent",
        "absent_dates",
        "single",
        "constant",
        "all_zero",
        "durations",
        "long_labels",
        "at_bound",
    ]


def test_golden_preconditions_hold() -> None:
    by_name = {case.name: case for case in CASES}
    typical = by_name["typical"].data.rows
    days = [d for d in (r[0] for r in typical) if isinstance(d, date)]
    assert days != sorted(days)
    assert any(r[0] is None for r in typical)
    assert any(r[1] is None and r[0] is not None for r in typical)
    assert any(r[1] == 0.0 for r in typical)
    assert min(days).weekday() == 3  # a Thursday
    assert len(set(days)) == len(days)
    span = (max(days) - min(days)).days + 1
    assert span > len(days)  # missing days
    at_bound = by_name["at_bound"].data.rows
    assert len(at_bound) == 366
    columns = {
        (d - timedelta(days=d.weekday()))
        for d in (r[0] for r in at_bound)
        if isinstance(d, date)
    }
    assert len(columns) == KIND.bound.limit
    svg = render_case(KIND, by_name["at_bound"].request, by_name["at_bound"].data).text
    assert len(svg.encode()) <= 80_000


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.name)
def test_golden(case: Case) -> None:
    rendered = render_case(KIND, case.request, case.data)
    assert rendered.kind == "calendar-heatmap"
    assert rendered.output is Output.SVG
    assert_golden(golden_path("calendar-heatmap", case.name, "svg"), rendered.text)


def test_no_stale_goldens() -> None:
    directory = golden_path("calendar-heatmap", "x", "svg").parent
    on_disk = sorted(path.name for path in directory.iterdir())
    assert on_disk == sorted(f"{case.name}.svg" for case in CASES)


def main() -> None:
    for case in CASES:
        text = render_case(KIND, case.request, case.data).text
        write_golden(golden_path("calendar-heatmap", case.name, "svg"), text)


if __name__ == "__main__":
    main()
