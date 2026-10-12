"""The ``heatmap`` kind: declaration, band order, limits, labelling, cells and goldens.

Requirements 2.4, 2.5, 2.7, 2.8, 2.9, 2.10, 3.5, 3.7, 5.1, 5.2, 5.3, 5.4, 5.5,
5.6, 12.1, 12.3.

Run ``uv run python -m tests.render.charts.kit.test_heatmap`` to (re)write the
goldens under ``golden/heatmap/``; a pytest run never writes them.
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
from fitdocs.render.charts.kit.kinds.heatmap import KIND
from fitdocs.render.charts.kit.layout import PAD, text_width
from fitdocs.render.charts.kit.problems import ChartProblem, ProblemCode
from fitdocs.render.charts.kit.scales import band_scale
from fitdocs.render.charts.kit.schema import (
    ChannelSpec,
    MarkBound,
    OptionSpec,
    OptionType,
    OptionValue,
    Output,
    OverBound,
)
from fitdocs.render.charts.kit.validate import validate_request
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
D = date

ZONE = column("zone")
WEEK = column("week", ValueKind.DATE)
TIME = column("time_s", unit="s")
CH = {"x": "week", "y": "zone", "value": "time_s"}
W = (D(2026, 3, 2), D(2026, 3, 9), D(2026, 3, 16), D(2026, 3, 23))


def _render(
    columns: Sequence[Column],
    rows: Sequence[Sequence[Value]],
    channels: Mapping[str, str] = CH,
    options: Mapping[str, OptionValue] | None = None,
    *,
    title: str = "Zone time",
) -> str:
    request = chart_request(
        "heatmap", ref="h1", title=title, channels=channels, options=options
    )
    return render_case(KIND, request, chart_data(columns, rows)).text


def _refusal(
    columns: Sequence[Column],
    rows: Sequence[Sequence[Value]],
    channels: Mapping[str, str] = CH,
) -> tuple[ChartProblem, ...]:
    request = chart_request("heatmap", ref="h1", channels=channels)
    return problems_of(KIND, request, chart_data(columns, rows))


# --- the golden fixtures --------------------------------------------------------

# Five zones by four weeks, one cell with no row (zone 4, third week), one zero
# (zone 5, first week) and one absent value (zone 2, third week). Rows arrive
# neither by zone nor by week; the values are pairwise distinct, run through all
# four 10-minute bins and sit on the bin edges 600 and 1200 and 2400.
TYPICAL_ROWS: tuple[tuple[Value, ...], ...] = (
    (3, W[2], 1260.0),
    (5, W[0], 0.0),
    (1, W[3], 480.0),
    (4, W[0], 1560.0),
    (2, W[1], 720.0),
    (5, W[3], 2400.0),
    (1, W[0], 150.0),
    (3, W[0], 960.0),
    (2, W[2], None),
    (4, W[3], 1920.0),
    (5, W[1], 2100.0),
    (1, W[2], 330.0),
    (3, W[3], 1380.0),
    (2, W[0], 600.0),
    (4, W[1], 1740.0),
    (5, W[2], 2250.0),
    (1, W[1], 240.0),
    (3, W[1], 1200.0),
    (2, W[3], 840.0),
)
TYPICAL_COLUMNS = (ZONE, WEEK, TIME)
TYPICAL_DESCRIPTION = (
    "Heatmap chart: Zone time. x: week; y: zone; value: time (m:ss). 19 rows."
    " week from 2026-03-02 to 2026-03-23; zone from 1 to 5;"
    " time (m:ss) from 0:00 to 40:00."
)

SPORT = column("sport", ValueKind.CATEGORY)
DAYNAME = column("weekday", ValueKind.CATEGORY)
LOAD = column("load")
CAT_CH = {"x": "weekday", "y": "sport", "value": "load"}
# y first appears as Run, Bike, Swim and x as Wed, Mon, Fri; neither is
# alphabetical. Swim on Mon and Run on Fri have no row.
CATEGORY_ROWS: tuple[tuple[Value, ...], ...] = (
    ("Run", "Wed", 45.0),
    ("Bike", "Mon", 80.0),
    ("Swim", "Fri", 25.0),
    ("Run", "Mon", 60.0),
    ("Bike", "Wed", 35.0),
    ("Swim", "Wed", 15.0),
    ("Bike", "Fri", 70.0),
)
CATEGORY_DESCRIPTION = (
    "Heatmap chart: Load by sport. x: weekday; y: sport; value: load."
    " 7 rows. weekday from Wed to Fri; sport from Run to Swim;"
    " load from 15 to 80."
)

BLOCK = column("block", ValueKind.CATEGORY)
# Both axes have an absent value, none at row 0. "Taper" appears before "Base".
ABSENT_AXIS_ROWS: tuple[tuple[Value, ...], ...] = (
    (2, "Taper", 30.0),
    (None, "Base", 50.0),
    (1, None, 20.0),
    (3, "Taper", 70.0),
    (None, None, 10.0),
    (1, "Base", 40.0),
    (2, None, 60.0),
)
ABSENT_AXIS_CH = {"x": "block", "y": "zone", "value": "load"}
ABSENT_AXIS_DESCRIPTION = (
    "Heatmap chart: Training blocks. x: block; y: zone; value: load."
    " 7 rows. block from Taper to —; zone from 1 to —; load from 10 to 70."
)

# Positions present, every value absent.
ALL_ABSENT_ROWS: tuple[tuple[Value, ...], ...] = (
    (2, W[1], None),
    (1, W[0], None),
    (2, W[0], None),
    (1, W[2], None),
    (2, W[2], None),
)

LONG_Y = column(
    "route",
    ValueKind.CATEGORY,
    label="Route taken on the day, from the first stretch to the last",
)
LONG_X = column("runner", ValueKind.CATEGORY)
LONG_VALUE = column(
    "pace_load",
    label="Training load accumulated over the whole of the effort as recorded",
)
LONG_A = "Alexandria Bartholomew Cornelius Dominic Eustace Fitzgerald"
LONG_B = "Bartholomew Cornelius Dominic Eustace Fitzgerald Alexandria"
LONG_ROWS: tuple[tuple[Value, ...], ...] = (
    ("Threshold intervals on the long hilly loop through the forest", LONG_A, 4.0),
    ("Easy recovery jog along the river path", LONG_B, 9.0),
    ("Hill sprints beside the reservoir wall", LONG_A, 2.0),
    ("Easy recovery jog along the river path", LONG_A, 6.0),
    ("Threshold intervals on the long hilly loop through the forest", LONG_B, 7.0),
)
LONG_CH = {"x": "runner", "y": "route", "value": "pace_load"}
LONG_TITLE = (
    "A deliberately long chart title that cannot possibly fit within the width of"
    " the chart however small its type"
)

AT_X, AT_Y = 60, 25
LIMIT = 1500


def _at_bound_rows(count: int) -> tuple[tuple[Value, ...], ...]:
    """Daily columns by zone rows, row-major, cut after ``count`` rows."""
    rows: list[tuple[Value, ...]] = []
    for zone in range(1, AT_Y + 1):
        for day in range(AT_X):
            number = (day * 37 + zone * 11) % 97
            value: Value = None if number == 5 else float(number)
            rows.append((zone, D(2026, 1, 1) + timedelta(days=day), value))
    return tuple(rows[:count])


CASES: tuple[Case, ...] = (
    Case(
        "typical",
        chart_request("heatmap", ref="h1", title="Zone time", channels=CH),
        chart_data(TYPICAL_COLUMNS, TYPICAL_ROWS),
    ),
    Case(
        "empty",
        chart_request("heatmap", ref="h1", title="Zone time", channels=CH),
        chart_data(TYPICAL_COLUMNS, []),
    ),
    Case(
        "all_absent",
        chart_request("heatmap", ref="h1", title="Zone time", channels=CH),
        chart_data(TYPICAL_COLUMNS, ALL_ABSENT_ROWS),
    ),
    Case(
        "single",
        chart_request("heatmap", ref="h1", title="Zone time", channels=CH),
        chart_data(TYPICAL_COLUMNS, [(2, W[1], 1500.0)]),
    ),
    Case(
        "categories",
        chart_request("heatmap", ref="h1", title="Load by sport", channels=CAT_CH),
        chart_data((SPORT, DAYNAME, LOAD), CATEGORY_ROWS),
    ),
    Case(
        "absent_axis",
        chart_request(
            "heatmap", ref="h1", title="Training blocks", channels=ABSENT_AXIS_CH
        ),
        chart_data((ZONE, BLOCK, LOAD), ABSENT_AXIS_ROWS),
    ),
    Case(
        "long_labels",
        chart_request("heatmap", ref="h1", title=LONG_TITLE, channels=LONG_CH),
        chart_data((LONG_Y, LONG_X, LONG_VALUE), LONG_ROWS),
    ),
    Case(
        "at_bound",
        chart_request("heatmap", ref="h1", title="Every day", channels=CH),
        chart_data((ZONE, WEEK, column("time_s", unit="s")), _at_bound_rows(LIMIT)),
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


def _texts(element: ET.Element) -> list[ET.Element]:
    return list(element.iter(f"{SVG}text"))


def _axes(text: str) -> tuple[ET.Element, ET.Element]:
    """The bottom (x) and left (y) axes, in draw order."""
    x_axis, y_axis = _group(text, "ck-axis")
    return x_axis, y_axis


def _x_labels(text: str) -> list[str]:
    """The drawn x tick labels (the last text of the bottom axis is its title)."""
    return [t.text or "" for t in _texts(_axes(text)[0])[:-1]]


def _x_title(text: str) -> str:
    return _texts(_axes(text)[0])[-1].text or ""


def _y_labels(text: str) -> list[str]:
    return [
        t.text or "" for t in _texts(_axes(text)[1]) if t.get("text-anchor") == "end"
    ]


def _y_title(text: str) -> str:
    (title,) = [t for t in _texts(_axes(text)[1]) if t.get("text-anchor") == "start"]
    return title.text or ""


def _plot(text: str) -> tuple[float, float, float, float]:
    """The plot rectangle as ``(left, top, right, bottom)``."""
    x_axis, y_axis = _axes(text)
    base = next(x_axis.iter(f"{SVG}line"))
    side = next(y_axis.iter(f"{SVG}line"))
    return (
        float(base.get("x1") or "nan"),
        float(side.get("y1") or "nan"),
        float(base.get("x2") or "nan"),
        float(side.get("y2") or "nan"),
    )


def _height(text: str) -> int:
    return int(_root(text).get("height") or "0")


def _row_pitch(text: str, rows: int) -> float:
    _, top, _, bottom = _plot(text)
    return (bottom - top) / rows


def _desc(text: str) -> str:
    (desc,) = _root(text).iter(f"{SVG}desc")
    return desc.text or ""


def _legend_labels(text: str) -> list[str]:
    (legend,) = _group(text, "ck-legend")
    return [t.text or "" for t in _texts(legend)]


BOX = re.compile(r"M(-?[\d.]+) (-?[\d.]+)H(-?[\d.]+)V(-?[\d.]+)H(-?[\d.]+)Z")
CROSS = re.compile(
    r"M(-?[\d.]+) (-?[\d.]+)L(-?[\d.]+) (-?[\d.]+)"
    r"M(-?[\d.]+) (-?[\d.]+)L(-?[\d.]+) (-?[\d.]+)"
)


def _cells(text: str) -> list[tuple[str, float, float]]:
    """Every drawn cell as ``(class, centre x, centre y)``: ``bin:<fill>``,
    ``zero`` or ``absent``, in element then subpath order."""
    (marks,) = _group(text, "ck-marks")
    found: list[tuple[str, float, float]] = []
    for path in marks.iter(f"{SVG}path"):
        d = path.get("d") or ""
        fill = path.get("fill")
        if fill != "none":
            label = f"bin:{fill}"
        elif path.get("stroke") == SEQUENTIAL_RAMP[0]:
            label = "zero"
        else:
            label = "absent"
        if label == "absent":
            for m in CROSS.finditer(d):
                left, top, right, bottom = (float(m.group(i)) for i in (1, 2, 3, 4))
                found.append((label, (left + right) / 2, (top + bottom) / 2))
            continue
        for m in BOX.finditer(d):
            left, top, right, bottom = (float(m.group(i)) for i in (1, 2, 3, 4))
            found.append((label, (left + right) / 2, (top + bottom) / 2))
    return found


def _placed(text: str, columns: int, rows: int) -> dict[tuple[int, int], str]:
    """The cell class at each ``(column, row)`` band, read from the pixel centres."""
    left, top, right, bottom = _plot(text)
    cell_w, cell_h = (right - left) / columns, (bottom - top) / rows
    out: dict[tuple[int, int], str] = {}
    cells = _cells(text)
    for label, cx, cy in cells:
        out[(int((cx - left) // cell_w), int((cy - top) // cell_h))] = label
    assert len(out) == len(cells), "two cells share a band"
    return out


def _bin_fill(bins: int, bin_index: int) -> str:
    """The fill of bin ``bin_index`` when the scale has ``bins`` bins: the top ones."""
    return f"bin:{SEQUENTIAL_RAMP[-bins:][bin_index - 1]}"


# --- declaration -----------------------------------------------------------------


def test_declaration() -> None:
    assert KIND.name == "heatmap"
    assert KIND.output is Output.SVG
    assert [(c.name, c.required, c.accepts) for c in KIND.channels] == [
        (
            "x",
            True,
            (
                ValueKind.CATEGORY,
                ValueKind.DATE,
                ValueKind.BOOLEAN,
                ValueKind.NUMBER,
            ),
        ),
        (
            "y",
            True,
            (
                ValueKind.CATEGORY,
                ValueKind.DATE,
                ValueKind.BOOLEAN,
                ValueKind.NUMBER,
            ),
        ),
        ("value", True, (ValueKind.NUMBER, ValueKind.DURATION)),
    ]
    assert all(isinstance(c, ChannelSpec) for c in KIND.channels)
    assert KIND.options == (
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
            None,
            minimum=160,
            maximum=1200,
        ),
    )
    assert KIND.bound == MarkBound(
        1500,
        "cells",
        OverBound.REFUSE,
        "At most 1500 cells, 60 x values and 40 y values.",
    )
    assert KIND.max_series is None
    assert [f.name for f in dataclasses.fields(KIND)][:3] == [
        "name",
        "description",
        "output",
    ]


def test_description_states_the_refusal_and_the_empty_position() -> None:
    assert "negative values are refused" in KIND.description
    assert "a position with no row draws nothing" in KIND.description
    assert KIND.description == (
        "A grid of cells over two category, date, boolean or number axes, "
        "sized and shaded by a value of zero or more (negative values are "
        "refused); a position with no row draws nothing"
    )


def test_a_datetime_axis_is_not_accepted() -> None:
    stamp = column("started", ValueKind.DATETIME)
    request = chart_request(
        "heatmap", ref="h1", channels={"x": "started", "y": "zone", "value": "time_s"}
    )
    problems = validate_request(
        request, (stamp, ZONE, TIME), KIND, registry.kind_names()
    )
    assert [(p.code, p.channel) for p in problems] == [(ProblemCode.CHANNEL_KIND, "x")]


# --- band order (5.2, 2.7) ------------------------------------------------------


def test_number_bands_ascend_from_rows_given_3_1_2() -> None:
    rows = [(3, W[0], 30.0), (1, W[0], 10.0), (2, W[0], 20.0)]
    text = _render(TYPICAL_COLUMNS, rows)
    assert _y_labels(text) == ["1", "2", "3"]
    # the value 10 sits in the top row, 30 in the bottom
    placed = _placed(text, 1, 3)
    assert [placed[(0, i)] for i in range(3)] == [
        _bin_fill(3, 1),
        _bin_fill(3, 2),
        _bin_fill(3, 3),
    ]


def test_typical_number_and_date_bands_ascend_and_hold_their_rows() -> None:
    text = _render(TYPICAL_COLUMNS, TYPICAL_ROWS)
    assert _y_labels(text) == ["1", "2", "3", "4", "5"]
    assert _x_labels(text) == ["2026-03-02", "2026-03-09", "2026-03-16", "2026-03-23"]
    assert [r[0] for r in TYPICAL_ROWS[:3]] != [1, 2, 3]  # zones arrive unsorted
    row_weeks = [r[1] for r in TYPICAL_ROWS if isinstance(r[1], date)]
    assert len(row_weeks) == 19 and row_weeks != sorted(row_weeks)
    edges = (600.0, 1200.0, 1800.0, 2400.0)
    expected: dict[tuple[int, int], str] = {}
    for zone, week, seconds in TYPICAL_ROWS:
        assert isinstance(zone, int) and isinstance(week, date)
        assert isinstance(seconds, float | None)
        if seconds is None:
            label = "absent"
        elif seconds == 0:
            label = "zero"
        else:
            label = _bin_fill(4, 1 + sum(seconds > e for e in edges[:-1]))
        expected[(W.index(week), zone - 1)] = label
    assert _placed(text, 4, 5) == expected
    assert len(expected) == 19
    assert (2, 3) not in expected  # the one position with no row


def test_categories_keep_first_appearance_not_alphabetical() -> None:
    text = _render((SPORT, DAYNAME, LOAD), CATEGORY_ROWS, CAT_CH)
    assert _y_labels(text) == ["Run", "Bike", "Swim"]
    assert _x_labels(text) == ["Wed", "Mon", "Fri"]
    assert _y_labels(text) != sorted(_y_labels(text))
    assert _x_labels(text) != sorted(_x_labels(text))
    # Run/Wed is 45, Bike/Mon 80, Swim/Fri 25: read each from its position
    placed = _placed(text, 3, 3)
    assert placed[(0, 0)] != placed[(1, 1)]  # 45 and 80 are in different bins
    assert placed[(1, 1)] == _bin_fill(3, 3)  # 80, the maximum
    assert placed[(2, 2)] == _bin_fill(3, 1)  # 25


def test_booleans_order_by_first_appearance() -> None:
    flag = column("race", ValueKind.BOOLEAN)
    rows = [(True, 1, 5.0), (False, 1, 6.0), (True, 2, 7.0)]
    text = _render(
        (flag, ZONE, LOAD), rows, {"x": "zone", "y": "race", "value": "load"}
    )
    assert _y_labels(text) == ["true", "false"]


def test_dates_ascend_from_unsorted_rows_on_either_axis() -> None:
    rows = [
        (D(2026, 3, 16), "a", 3.0),
        (D(2026, 3, 2), "a", 1.0),
        (D(2026, 3, 9), "a", 2.0),
    ]
    text = _render(
        (WEEK, SPORT, LOAD), rows, {"x": "sport", "y": "week", "value": "load"}
    )
    assert _y_labels(text) == ["2026-03-02", "2026-03-09", "2026-03-16"]


def test_an_absent_y_forms_the_last_em_dash_row() -> None:
    text = _render((ZONE, BLOCK, LOAD), ABSENT_AXIS_ROWS, ABSENT_AXIS_CH)
    assert _y_labels(text) == ["1", "2", "3", "—"]
    assert _x_labels(text) == ["Taper", "Base", "—"]
    placed = _placed(text, 3, 4)
    assert len(placed) == 7
    # (zone None, Base) is the fourth row of the second column
    assert (1, 3) in placed
    # (zone None, block None) is the bottom-right corner
    assert (2, 3) in placed
    # (zone 1, block None) is the first row of the last column
    assert (2, 0) in placed
    assert (0, 3) not in placed  # nothing at (Taper, —)


def test_an_absent_axis_value_is_not_counted_against_the_value_limit() -> None:
    rows = [(1, f"c{i}", 1.0) for i in range(60)] + [(1, None, 2.0)]
    text = _render((ZONE, BLOCK, LOAD), rows, ABSENT_AXIS_CH)
    assert len(_cells(text)) == 61


# --- refusals (5.3, 5.4, 3.7, 2.9) -----------------------------------------------


def test_a_duplicate_x_y_at_row_4_refuses_alone() -> None:
    rows = [
        (1, W[0], 10.0),
        (2, W[1], 20.0),
        (3, W[2], 30.0),
        (1, W[3], 40.0),
        (2, W[1], 50.0),
        (3, W[2], 60.0),
    ]
    assert _refusal(TYPICAL_COLUMNS, rows) == (
        ChartProblem(
            ref="h1",
            kind="heatmap",
            code=ProblemCode.DUPLICATE_POSITION,
            message="Row 4 repeats row 1, which has the same week (2026-03-09)"
            " and zone (2).",
            fix="Aggregate the rows that share this position, or bind a column "
            "to x or y that separates them.",
            row=4,
        ),
    )


def test_two_rows_in_the_same_absent_band_pair_are_a_duplicate() -> None:
    rows = [(1, "a", 1.0), (None, "b", 2.0), (3, "c", 3.0), (None, "b", 4.0)]
    (problem,) = _refusal((ZONE, BLOCK, LOAD), rows, ABSENT_AXIS_CH)
    assert problem.code is ProblemCode.DUPLICATE_POSITION
    assert problem.row == 3


def _grid(
    x_count: int, y_count: int, *, limit: int | None = None
) -> tuple[tuple[Value, ...], ...]:
    rows = [
        (y, f"c{x}", float(1 + (x * 7 + y * 3) % 20))
        for y in range(y_count)
        for x in range(x_count)
    ]
    return tuple(rows if limit is None else rows[:limit])


def test_1501_cells_refuse_alone_and_1500_render() -> None:
    assert _refusal((ZONE, BLOCK, LOAD), _grid(60, 26, limit=1501), ABSENT_AXIS_CH) == (
        ChartProblem(
            ref="h1",
            kind="heatmap",
            code=ProblemCode.OVER_BOUND,
            message="heatmap draws at most 1500 cells; this data has 1501.",
            fix="Aggregate the rows (for example by day or week) or limit them to "
            "at most 1500.",
            rows=1501,
        ),
    )
    text = _render((ZONE, BLOCK, LOAD), _grid(60, 25), ABSENT_AXIS_CH)
    assert len(_cells(text)) == 1500


def test_61_x_values_refuse_alone_and_60_render() -> None:
    assert _refusal((ZONE, BLOCK, LOAD), _grid(61, 2), ABSENT_AXIS_CH) == (
        ChartProblem(
            ref="h1",
            kind="heatmap",
            code=ProblemCode.OVER_BOUND,
            message="heatmap draws at most 60 x values; this data has 61.",
            fix="Filter or group the x column to at most 60 values.",
            channel="x",
            column="block",
        ),
    )
    text = _render((ZONE, BLOCK, LOAD), _grid(60, 2), ABSENT_AXIS_CH)
    assert len(_cells(text)) == 120


def test_41_y_values_refuse_alone_and_40_render() -> None:
    assert _refusal((ZONE, BLOCK, LOAD), _grid(3, 41), ABSENT_AXIS_CH) == (
        ChartProblem(
            ref="h1",
            kind="heatmap",
            code=ProblemCode.OVER_BOUND,
            message="heatmap draws at most 40 y values; this data has 41.",
            fix="Filter or group the y column to at most 40 values.",
            channel="y",
            column="zone",
        ),
    )
    text = _render((ZONE, BLOCK, LOAD), _grid(3, 40), ABSENT_AXIS_CH)
    assert len(_cells(text)) == 120
    assert _row_pitch(text, 40) > 13
    assert len(_y_labels(text)) == 40


def test_every_exceeded_limit_is_reported_in_order() -> None:
    problems = _refusal((ZONE, BLOCK, LOAD), _grid(61, 41), ABSENT_AXIS_CH)
    assert [(p.code, p.channel) for p in problems] == [
        (ProblemCode.OVER_BOUND, None),
        (ProblemCode.OVER_BOUND, "x"),
        (ProblemCode.OVER_BOUND, "y"),
    ]


def test_a_negative_value_refuses_naming_the_first_row_and_the_count() -> None:
    rows = [(1, W[0], 10.0), (2, W[1], 0.0), (3, W[2], 30.0), (4, W[3], -5.0)]
    rows += [(5, W[0], -1.0)]
    assert _refusal(TYPICAL_COLUMNS, rows) == (
        ChartProblem(
            ref="h1",
            kind="heatmap",
            code=ProblemCode.NEGATIVE_VALUE,
            message="time has a negative value at row 3; heatmap shades values"
            " from zero up.",
            fix="Use a line or bar chart for signed values, or select a value"
            " that cannot be negative.",
            channel="value",
            column="time_s",
            row=3,
            rows=2,
        ),
    )


def test_problems_follow_the_stage_three_order() -> None:
    rows = [(1, W[0], 10.0), (2, W[1], -2.0), (1, W[0], 30.0)]
    problems = _refusal(TYPICAL_COLUMNS, rows)
    assert [p.code for p in problems] == [
        ProblemCode.DUPLICATE_POSITION,
        ProblemCode.NEGATIVE_VALUE,
    ]


# --- labelling and height (5.5, 5.6) ---------------------------------------------


def _rows_chart(count: int, height: int | None) -> str:
    """``count`` y categories ``r<count-1>`` .. ``r0`` in that order, one x."""
    rows = [(f"r{count - 1 - i}", "a", float(i + 1)) for i in range(count)]
    options = {} if height is None else {"height": height}
    return _render((SPORT, DAYNAME, LOAD), rows, CAT_CH, options)


def _frame_px() -> int:
    """The pixels of a chart that are not plot, read from a render."""
    text = _rows_chart(10, 400)
    _, top, _, bottom = _plot(text)
    return round(400 - (bottom - top))


@pytest.mark.parametrize(
    ("count", "pitch", "every"),
    [(10, 9, 2), (10, 12, 2), (10, 13, 1), (10, 16, 1), (40, 5, 3)],
    ids=lambda v: str(v),
)
def test_y_rows_are_labelled_by_pitch(count: int, pitch: int, every: int) -> None:
    text = _rows_chart(count, _frame_px() + count * pitch)
    assert _row_pitch(text, count) == pytest.approx(pitch)
    expected = [f"r{count - 1 - i}" for i in range(0, count, every)]
    assert _y_labels(text) == expected
    assert len(expected) == -(-count // every)


def test_x_bands_are_labelled_by_the_band_scale_rule() -> None:
    text = _render_case(_case("at_bound"))
    left, _, right, _ = _plot(text)
    labels = [(D(2026, 1, 1) + timedelta(days=i)).isoformat() for i in range(AT_X)]
    expected = band_scale(labels, left, right, font_px=11)
    assert 1 < len(expected.labelled) < AT_X
    ticks = [
        float(line.get("x1") or "nan")
        for line in _axes(text)[0].iter(f"{SVG}line")
        if line.get("y2") != line.get("y1") and line.get("x1") == line.get("x2")
    ]
    assert ticks == [
        pytest.approx(expected.centre(i), abs=0.01) for i in expected.labelled
    ]
    assert len(_x_labels(text)) == len(expected.labelled)
    assert expected.labelled[0] == 0  # counted from the first


def test_auto_height_follows_the_rows_at_the_row_pitch() -> None:
    few = _render((ZONE, BLOCK, LOAD), _grid(3, 4), ABSENT_AXIS_CH)
    many = _render((ZONE, BLOCK, LOAD), _grid(3, 8), ABSENT_AXIS_CH)
    assert _row_pitch(few, 4) == pytest.approx(32)
    assert _row_pitch(many, 8) == pytest.approx(32)
    assert _height(many) - _height(few) == 4 * 32


def test_row_pitch_is_a_column_pitch_between_16_and_32() -> None:
    # 26 columns of about 26 px: the pitch follows the width
    wide = _render((ZONE, BLOCK, LOAD), _grid(26, 4), ABSENT_AXIS_CH)
    left, _, right, _ = _plot(wide)
    assert 16 < (right - left) / 26 < 32
    target = (right - left) / 26
    assert 0.2 < (4 * target) % 1 < 0.9  # four such rows do not fill whole pixels
    # the height is rounded up to a whole pixel, so a row is never under the pitch
    assert target - 0.01 <= _row_pitch(wide, 4) < target + 1 / 4
    # 60 columns of about 11 px: the floor
    narrow = _render((ZONE, BLOCK, LOAD), _grid(60, 4), ABSENT_AXIS_CH)
    assert _row_pitch(narrow, 4) == pytest.approx(16)
    # 3 columns of over 200 px: the ceiling
    tall = _render((ZONE, BLOCK, LOAD), _grid(3, 4), ABSENT_AXIS_CH)
    assert _row_pitch(tall, 4) == pytest.approx(32)


def test_auto_height_is_limited_to_160_and_1200() -> None:
    assert _height(_render_case(_case("single"))) == 160
    assert _height(_render((ZONE, BLOCK, LOAD), _grid(3, 40), ABSENT_AXIS_CH)) == 1200


def test_a_set_height_is_the_chart_height_and_the_rows_share_the_plot() -> None:
    text = _render((ZONE, BLOCK, LOAD), _grid(3, 4), ABSENT_AXIS_CH, {"height": 500})
    assert _height(text) == 500
    _, top, _, bottom = _plot(text)
    assert (bottom - top) / 4 > 32  # the rows took the whole plot, not 32 px each
    placed = _placed(text, 3, 4)
    assert len(placed) == 12


# --- cells and legend (3.5, 2.3) --------------------------------------------------


def test_a_missing_row_draws_no_mark() -> None:
    rows = [(1, "a", 1.0), (2, "b", 2.0), (1, "b", 3.0)]
    text = _render((ZONE, BLOCK, LOAD), rows, ABSENT_AXIS_CH)
    assert sorted(_placed(text, 2, 2)) == [(0, 0), (1, 0), (1, 1)]
    assert len(_cells(text)) == 3


def test_an_absent_value_is_a_cross_and_a_zero_an_outline() -> None:
    rows = [(1, "a", None), (2, "b", 0.0), (3, "c", 4.0)]
    text = _render((ZONE, BLOCK, LOAD), rows, ABSENT_AXIS_CH)
    classes = _placed(text, 3, 3)
    assert classes[(0, 0)] == "absent"
    assert classes[(1, 1)] == "zero"
    assert classes[(2, 2)].startswith("bin:")


def test_all_values_absent_draws_crosses_and_a_lead_and_absent_legend() -> None:
    text = _render_case(_case("all_absent"))
    assert "No data" not in text
    assert [c for c, _, _ in _cells(text)] == ["absent"] * 5
    assert _legend_labels(text) == ["time (m:ss)", "no value"]
    assert _y_labels(text) == ["1", "2"]
    assert _x_labels(text) == ["2026-03-02", "2026-03-09", "2026-03-16"]
    assert "none of the" not in _desc(text)
    assert _desc(text).startswith("Heatmap chart: Zone time. x: week; y: zone;")


def test_all_positions_absent_and_all_values_absent_still_draws_a_cross() -> None:
    rows = [(None, None, None)]
    text = _render((ZONE, BLOCK, LOAD), rows, ABSENT_AXIS_CH)
    assert "No data" not in text
    assert [c for c, _, _ in _cells(text)] == ["absent"]
    assert _y_labels(text) == ["—"]
    assert _x_labels(text) == ["—"]


def test_typical_legend_names_the_lead_zero_every_bin_and_absent() -> None:
    labels = _legend_labels(_render_case(_case("typical")))
    assert labels == [
        "time (m:ss)",
        "0:00",
        "≤ 10:00",
        "≤ 20:00",
        "≤ 30:00",
        "≤ 40:00",
        "no value",
    ]


def test_the_legend_lists_zero_and_absent_only_when_the_chart_holds_them() -> None:
    complete = _legend_labels(_render_case(_case("categories")))
    assert "no value" not in complete
    assert not any(label in complete for label in ("0", "0.0"))
    with_zero = _legend_labels(
        _render(
            (SPORT, DAYNAME, LOAD),
            [("a", "b", 0.0), ("c", "d", 7.0)],
            CAT_CH,
        )
    )
    assert "0" in with_zero and "no value" not in with_zero
    with_absent = _legend_labels(
        _render(
            (SPORT, DAYNAME, LOAD),
            [("a", "b", None), ("c", "d", 7.0)],
            CAT_CH,
        )
    )
    assert "no value" in with_absent and "0" not in with_absent


def test_a_grid_of_zeros_draws_outlines_and_a_legend_without_bins() -> None:
    rows = [("a", "b", 0.0), ("c", "d", 0.0), ("a", "d", None)]
    text = _render((SPORT, DAYNAME, LOAD), rows, CAT_CH)
    assert sorted(c for c, _, _ in _cells(text)) == ["absent", "zero", "zero"]
    assert _legend_labels(text) == ["load", "0", "no value"]


# --- the value column's wording (2.10) --------------------------------------------


def test_a_value_with_a_unit_is_described_with_it() -> None:
    bpm = column("heart_rate_bpm", unit="bpm")
    rows = [(1, "a", 152.0), (2, "b", 161.0), (3, "c", 148.0)]
    text = _render(
        (ZONE, BLOCK, bpm), rows, {"x": "block", "y": "zone", "value": "heart_rate_bpm"}
    )
    assert _desc(text) == (
        "Heatmap chart: Zone time. x: block; y: zone; value: heart rate (bpm)."
        " 3 rows. block from a to c; zone from 1 to 3;"
        " heart rate (bpm) from 148 bpm to 161 bpm."
    )


def test_a_short_duration_value_is_titled_and_described_in_minutes() -> None:
    elapsed = column("elapsed", ValueKind.DURATION)
    rows = [
        (1, "a", timedelta(minutes=5)),
        (2, "b", timedelta(minutes=40)),
        (3, "c", timedelta(minutes=20)),
    ]
    text = _render(
        (ZONE, BLOCK, elapsed), rows, {"x": "block", "y": "zone", "value": "elapsed"}
    )
    assert _legend_labels(text)[0] == "elapsed (m:ss)"
    assert "elapsed (m:ss) from 5:00 to 40:00." in _desc(text)


def test_a_long_duration_value_is_titled_and_described_in_hours() -> None:
    elapsed = column("elapsed", ValueKind.DURATION)
    rows = [
        (1, "a", timedelta(minutes=5)),
        (2, "b", timedelta(hours=2, minutes=10)),
        (3, "c", timedelta(minutes=45)),
    ]
    text = _render(
        (ZONE, BLOCK, elapsed), rows, {"x": "block", "y": "zone", "value": "elapsed"}
    )
    assert _legend_labels(text)[0] == "elapsed (h:mm:ss)"
    assert "elapsed (h:mm:ss) from 0:05:00 to 2:10:00." in _desc(text)


INTERVAL = column("interval_s", unit="s")


def _interval_chart(seconds: Sequence[float]) -> str:
    """A seconds-valued number x axis, rows out of order, one y category each."""
    rows = [(f"r{i}", v, float(i + 1)) for i, v in enumerate(seconds)]
    return _render(
        (BLOCK, INTERVAL, LOAD),
        rows,
        {"x": "interval_s", "y": "block", "value": "load"},
    )


def test_a_short_seconds_axis_is_labelled_titled_and_described_in_minutes() -> None:
    text = _interval_chart([900.0, 300.0, 600.0])
    assert _x_labels(text) == ["5:00", "10:00", "15:00"]
    assert _x_title(text) == "interval (m:ss)"
    assert "interval (m:ss) from 5:00 to 15:00" in _desc(text)
    assert "x: interval (m:ss);" in _desc(text)


def test_a_seconds_axis_with_an_hour_is_one_long_form() -> None:
    text = _interval_chart([3600.0, 300.0, 900.0])
    assert _x_labels(text) == ["0:05:00", "0:15:00", "1:00:00"]
    assert _x_title(text) == "interval (h:mm:ss)"
    assert "interval (h:mm:ss) from 0:05:00 to 1:00:00" in _desc(text)


def test_a_seconds_y_axis_keeps_its_absent_band_and_one_form() -> None:
    rows = [("a", 1800.0, 1.0), ("b", None, 2.0), ("c", 7200.0, 3.0)]
    text = _render(
        (BLOCK, INTERVAL, LOAD),
        rows,
        {"x": "block", "y": "interval_s", "value": "load"},
    )
    assert _y_labels(text) == ["0:30:00", "2:00:00", "—"]
    assert _y_title(text) == "interval (h:mm:ss)"


def test_a_short_seconds_y_axis_is_titled_in_minutes() -> None:
    # Every y under an hour, so the title's form differs from axis_title's default.
    rows = [("a", 2700.0, 1.0), ("b", None, 2.0), ("c", 1800.0, 3.0)]
    text = _render(
        (BLOCK, INTERVAL, LOAD),
        rows,
        {"x": "block", "y": "interval_s", "value": "load"},
    )
    assert _y_labels(text) == ["30:00", "45:00", "—"]
    assert _y_title(text) == "interval (m:ss)"


def test_nothing_is_counted_as_not_drawn() -> None:
    for name in ("typical", "all_absent", "absent_axis"):
        text = _render_case(_case(name))
        assert "Not drawn" not in text, name
    assert 'class="ck-notes"' not in _render_case(_case("absent_axis"))


def test_descriptions_name_the_channels_rows_and_ranges() -> None:
    assert _desc(_render_case(_case("typical"))) == TYPICAL_DESCRIPTION
    assert _desc(_render_case(_case("categories"))) == CATEGORY_DESCRIPTION
    assert _desc(_render_case(_case("absent_axis"))) == ABSENT_AXIS_DESCRIPTION


def test_axis_titles_are_the_columns_with_their_units() -> None:
    text = _render_case(_case("typical"))
    assert _x_title(text) == "week"
    assert _y_title(text) == "zone"


# --- no data (2.4, 2.5) -----------------------------------------------------------


def test_no_rows_is_the_no_data_state_at_the_default_size() -> None:
    text = _render_case(_case("empty"))
    assert "No data" in text
    assert _height(text) == 160
    assert "None of the" not in text
    assert 'class="ck-marks"' not in text
    assert _desc(text) == "Heatmap chart: Zone time. No data: no rows."


def test_no_rows_with_a_set_height_keeps_that_height() -> None:
    text = _render(TYPICAL_COLUMNS, [], CH, {"height": 300})
    assert _height(text) == 300
    assert "No data" in text


# --- long labels -------------------------------------------------------------------


@pytest.mark.parametrize("width", [320, 720])
def test_the_y_labels_leave_the_plot_at_least_60_percent_of_the_width(
    width: int,
) -> None:
    text = _render(
        (LONG_Y, LONG_X, LONG_VALUE),
        LONG_ROWS,
        LONG_CH,
        {"width": width},
        title=LONG_TITLE,
    )
    left, _, right, _ = _plot(text)
    assert left <= 0.4 * width + 1e-6
    assert left > 0.4 * width - 30  # the long labels fill the share
    assert _y_labels(text)[0].endswith("…")
    assert right > left


def test_short_labels_are_not_shortened() -> None:
    text = _render_case(_case("typical"))
    assert "…" not in text
    text = _render_case(_case("categories"))
    assert "…" not in text


def test_the_long_labels_golden_is_shortened() -> None:
    text = _render_case(_case("long_labels"))
    assert text.count("…") >= 4
    assert "…" in "".join(_y_labels(text))
    assert "…" in "".join(_legend_labels(text))


# --- goldens -----------------------------------------------------------------------


def test_cases_are_the_designed_names() -> None:
    assert [case.name for case in CASES] == [
        "typical",
        "empty",
        "all_absent",
        "single",
        "categories",
        "absent_axis",
        "long_labels",
        "at_bound",
    ]


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.name)
def test_golden(case: Case) -> None:
    rendered = render_case(KIND, case.request, case.data)
    assert rendered.kind == "heatmap"
    assert rendered.output is Output.SVG
    assert_golden(golden_path("heatmap", case.name, "svg"), rendered.text)


def test_no_stale_goldens() -> None:
    directory = golden_path("heatmap", "x", "svg").parent
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
        assert left >= PAD - 1e-6, element.text
        assert left + reach <= width - 4.0 + 1e-6, element.text


@pytest.mark.parametrize("width", [320, 720])
def test_long_labels_stay_inside_the_chart_at_both_widths(width: int) -> None:
    svg = _render(
        (LONG_Y, LONG_X, LONG_VALUE),
        LONG_ROWS,
        LONG_CH,
        {"width": width},
        title=LONG_TITLE,
    )
    texts = _texts(_root(svg))
    assert len(texts) > 10
    for element in texts:
        x = float(element.get("x") or "nan")
        reach = text_width(element.text or "", float(element.get("font-size") or "nan"))
        anchor = element.get("text-anchor")
        left = (
            x - reach / 2 if anchor == "middle" else x - reach if anchor == "end" else x
        )
        assert left >= PAD - 1e-6, element.text
        assert left + reach <= width - 4.0 + 1e-6, element.text


def test_typical_fixture_has_the_distinguishing_values() -> None:
    zones = [r[0] for r in TYPICAL_ROWS]
    weeks = [r[1] for r in TYPICAL_ROWS]
    values = [r[2] for r in TYPICAL_ROWS]
    assert zones != sorted(zones, key=lambda z: z if isinstance(z, int) else 0)
    assert weeks != sorted(weeks, key=lambda w: w if isinstance(w, date) else W[0])
    assert any(v == 0 for v in values)
    assert any(v is None for v in values)
    positive = [v for v in values if isinstance(v, float) and v > 0]
    assert len(set(positive)) == len(positive) == 17
    assert len(TYPICAL_ROWS) == 5 * 4 - 1
    assert (4, W[2]) not in {(r[0], r[1]) for r in TYPICAL_ROWS}


def test_categories_fixture_differs_from_alphabetical_on_both_axes() -> None:
    sports = list(dict.fromkeys(r[0] for r in CATEGORY_ROWS))
    days = list(dict.fromkeys(r[1] for r in CATEGORY_ROWS))
    assert sports != sorted(sports, key=str)
    assert days != sorted(days, key=str)
    assert CATEGORY_ROWS[0][0] != "Bike"


def test_absent_axis_fixture_has_its_absent_values_after_row_0() -> None:
    assert ABSENT_AXIS_ROWS[0][0] is not None and ABSENT_AXIS_ROWS[0][1] is not None
    assert any(r[0] is None for r in ABSENT_AXIS_ROWS[1:])
    assert any(r[1] is None for r in ABSENT_AXIS_ROWS[1:])
    blocks = list(dict.fromkeys(r[1] for r in ABSENT_AXIS_ROWS if r[1] is not None))
    assert blocks != sorted(blocks, key=str)


def test_all_absent_fixture_has_no_present_value() -> None:
    assert len(ALL_ABSENT_ROWS) == 5
    assert all(r[2] is None for r in ALL_ABSENT_ROWS)
    assert all(r[0] is not None and r[1] is not None for r in ALL_ABSENT_ROWS)


def test_at_bound_golden_is_at_the_bound() -> None:
    case = _case("at_bound")
    assert len(case.data.rows) == LIMIT == KIND.bound.limit
    assert len({r[1] for r in case.data.rows}) == AT_X == 60
    assert len({r[0] for r in case.data.rows}) == AT_Y == 25
    assert any(r[2] is None for r in case.data.rows)
    assert any(r[2] == 0 for r in case.data.rows)
    assert len(_cells(_render_case(case))) == LIMIT


def test_long_labels_fixture_labels_overflow_their_share() -> None:
    longest = max(len(str(r[0])) for r in LONG_ROWS)
    assert text_width("x" * longest, 11) > 0.4 * 320


def main() -> None:
    for case in CASES:
        write_golden(golden_path("heatmap", case.name, "svg"), _render_case(case))


if __name__ == "__main__":
    main()
