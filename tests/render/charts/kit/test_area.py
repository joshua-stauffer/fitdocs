"""The ``area`` kind: declaration, refusals, geometry and goldens.

Regenerate the goldens with ``uv run python -m tests.render.charts.kit.test_area``.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from collections.abc import Sequence
from datetime import date, datetime, timedelta

import pytest

from fitdocs.render.charts.kit.data import ChartData, Column, Value, ValueKind
from fitdocs.render.charts.kit.kinds.area import KIND
from fitdocs.render.charts.kit.layout import text_width
from fitdocs.render.charts.kit.problems import ChartProblem, ProblemCode
from fitdocs.render.charts.kit.schema import (
    ChannelSpec,
    ChartRequest,
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

NS = "{http://www.w3.org/2000/svg}"

DAY = column("day", ValueKind.DATE)
DISTANCE = column("distance_km", unit="km")
SPORT = column("sport", ValueKind.CATEGORY)
COLUMNS = [DAY, DISTANCE, SPORT]
CHANNELS = {"x": "day", "y": "distance_km", "color": "sport"}


def d(n: int) -> date:
    return date(2026, 3, 1) + timedelta(days=n)


def _request(
    *,
    stack: bool = False,
    channels: dict[str, str] | None = None,
    title: str = "Weekly distance",
) -> ChartRequest:
    options: dict[str, OptionValue] = {"stack": True} if stack else {}
    return chart_request(
        "area",
        title=title,
        channels=CHANNELS if channels is None else channels,
        options=options,
    )


def _svg(rows: Sequence[Sequence[Value]], *, stack: bool = False) -> str:
    return render_case(KIND, _request(stack=stack), chart_data(COLUMNS, rows)).text


def _refusal(
    rows: Sequence[Sequence[Value]], *, stack: bool = False
) -> tuple[ChartProblem, ...]:
    return problems_of(KIND, _request(stack=stack), chart_data(COLUMNS, rows))


# --- reading a rendered chart back -------------------------------------------


def _group(root: ET.Element, css: str) -> list[ET.Element]:
    return [g for g in root.iter(f"{NS}g") if g.get("class") == css]


def _numbers(text: str) -> list[tuple[float, float]]:
    return [
        (float(a), float(b)) for a, b in re.findall(r"(-?[\d.]+)[ ,](-?[\d.]+)", text)
    ]


class Chart:
    """A rendered area chart read back as geometry."""

    def __init__(self, text: str) -> None:
        self.root = ET.fromstring(text)
        marks = _group(self.root, "ck-marks")
        assert len(marks) == 1
        self.marks = list(marks[0])
        left = [
            t
            for axis in _group(self.root, "ck-axis")
            for t in axis.iter(f"{NS}text")
            if t.get("text-anchor") == "end"
        ]
        self.y_labels = [t.text or "" for t in left]
        grid = _group(self.root, "ck-grid")[0]
        self.grid_y = [float(line.get("y1") or "nan") for line in grid]
        assert len(self.grid_y) == len(self.y_labels)

    @property
    def zero_px(self) -> float:
        return self.grid_y[self.y_labels.index("0")]

    @property
    def pixels_per_unit(self) -> float:
        top = len(self.y_labels) - 1
        return (self.zero_px - self.grid_y[top]) / float(self.y_labels[top])

    def value_at(self, y_px: float) -> float:
        return (self.zero_px - y_px) / self.pixels_per_unit

    def fills(self) -> list[ET.Element]:
        return [m for m in self.marks if m.tag == f"{NS}path" and m.get("fill-opacity")]

    def polylines(self) -> list[ET.Element]:
        return [m for m in self.marks if m.tag == f"{NS}polyline"]

    def dots(self) -> list[ET.Element]:
        return [m for m in self.marks if m.get("stroke-width") == "5"]

    def bands(self) -> list[ET.Element]:
        return [
            m
            for m in self.marks
            if m.tag == f"{NS}path"
            and m.get("fill-opacity") is None
            and m.get("fill") != "none"
        ]

    def legend(self) -> list[str]:
        return [
            t.text or "" for t in _group(self.root, "ck-legend")[0].iter(f"{NS}text")
        ]

    def notes(self) -> list[str]:
        groups = _group(self.root, "ck-notes")
        return [t.text or "" for g in groups for t in g.iter(f"{NS}text")]

    def description(self) -> str:
        node = self.root.find(f"{NS}desc")
        assert node is not None
        return node.text or ""


def _series_values(chart: Chart) -> list[list[float]]:
    """Each outline's values, read back from pixels, in drawing order."""
    return [
        [chart.value_at(y) for _, y in _numbers(line.get("points") or "")]
        for line in chart.polylines()
    ]


# --- declaration -------------------------------------------------------------


def test_kind_declaration() -> None:
    assert KIND.name == "area"
    assert (
        KIND.description == "Filled areas over a numeric or time x, optionally stacked"
    )
    assert KIND.output is Output.SVG
    assert [(c.name, c.accepts, c.required) for c in KIND.channels] == [
        (
            "x",
            (
                ValueKind.NUMBER,
                ValueKind.DURATION,
                ValueKind.DATE,
                ValueKind.DATETIME,
            ),
            True,
        ),
        ("y", (ValueKind.NUMBER, ValueKind.DURATION), True),
        ("color", (ValueKind.CATEGORY, ValueKind.BOOLEAN), False),
    ]
    assert all(isinstance(c, ChannelSpec) and c.description for c in KIND.channels)
    assert KIND.options == (
        OptionSpec(
            "stack",
            OptionType.BOOLEAN,
            "Stack the series in legend order instead of overlaying them.",
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
        1000,
        "rows",
        OverBound.REFUSE,
        "An area chart draws at most 1000 rows; more are refused.",
    )
    assert KIND.max_series == 8
    assert KIND.uses_all_columns is False


# --- refusals, each alone ----------------------------------------------------

_CLEAN = [
    (d(1), 4.0, "Run"),
    (d(0), 3.0, "Run"),
    (d(1), 2.0, "Bike"),
    (d(0), 6.0, "Bike"),
]


def test_clean_rows_render_stacked_and_unstacked() -> None:
    assert _svg(_CLEAN).startswith("<svg")
    assert _svg(_CLEAN, stack=True).startswith("<svg")


def test_stack_absent_alone() -> None:
    rows = [
        (d(1), 4.0, "Run"),
        (d(0), None, "Run"),
        (d(1), 2.0, "Bike"),
        (d(0), 6.0, "Bike"),
    ]
    assert _svg(rows).startswith("<svg")  # unstacked, the absent y is only a gap
    assert _refusal(rows, stack=True) == (
        ChartProblem(
            "c1",
            "area",
            ProblemCode.STACK_ABSENT,
            "Row 1 has no distance, which a stacked chart cannot draw.",
            "Unstack the chart or supply the missing value.",
            channel="y",
            column="distance_km",
            row=1,
        ),
    )


def test_stack_negative_alone() -> None:
    rows = [
        (d(1), 4.0, "Run"),
        (d(0), 3.0, "Run"),
        (d(1), -2.5, "Bike"),
        (d(0), 6.0, "Bike"),
    ]
    assert _svg(rows).startswith("<svg")
    assert _refusal(rows, stack=True) == (
        ChartProblem(
            "c1",
            "area",
            ProblemCode.STACK_NEGATIVE,
            "Row 2 holds the negative distance -2.5 km, "
            "which a stacked chart cannot add up.",
            "Unstack the chart or replace the negative values.",
            channel="y",
            column="distance_km",
            row=2,
        ),
    )


def test_stack_incomplete_alone() -> None:
    rows = [(d(1), 4.0, "Run"), (d(0), 3.0, "Run"), (d(0), 6.0, "Bike")]
    assert _svg(rows).startswith("<svg")  # unstacked, Bike simply stops
    assert _refusal(rows, stack=True) == (
        ChartProblem(
            "c1",
            "area",
            ProblemCode.STACK_INCOMPLETE,
            "Series Bike has no row at day 2026-03-02, which a stacked chart needs.",
            "Unstack the chart or supply a row for every series at every day.",
            channel="x",
            column="day",
        ),
    )


def test_stack_refusals_are_for_stacked_charts_only() -> None:
    # the same rows with all three faults draw when not stacked
    rows = [(d(1), -4.0, "Run"), (d(0), None, "Run"), (d(0), 6.0, "Bike")]
    assert _svg(rows).startswith("<svg")
    assert [p.code for p in _refusal(rows, stack=True)] == [
        ProblemCode.STACK_ABSENT,
        ProblemCode.STACK_NEGATIVE,
        ProblemCode.STACK_INCOMPLETE,
    ]


def test_duplicate_series_x_is_refused() -> None:
    rows = [
        (d(0), 3.0, "Run"),
        (d(1), 4.0, "Run"),
        (d(1), 5.0, "Bike"),  # same x, other series: fine
        (d(1), 6.0, "Run"),
    ]
    assert _refusal(rows) == (
        ChartProblem(
            "c1",
            "area",
            ProblemCode.DUPLICATE_POSITION,
            "Row 3 repeats row 1, which has the same sport (Run) and day (2026-03-02).",
            "Aggregate the rows that share this position, or bind a column to "
            "color or x that separates them.",
            row=3,
        ),
    )
    assert _svg(rows[:3]).startswith("<svg")


def test_rows_without_x_are_never_duplicates() -> None:
    rows = [(d(0), 3.0, "Run"), (None, 4.0, "Run"), (None, 5.0, "Run")]
    assert _svg(rows).startswith("<svg")


def test_nine_series_are_refused() -> None:
    rows = [(d(i), float(i + 1), f"S{i}") for i in range(9)]
    assert [p.code for p in _refusal(rows)] == [ProblemCode.TOO_MANY_SERIES]


def _numbered(count: int) -> ChartData:
    return chart_data(
        [column("n"), DISTANCE],
        [(i, float(i % 17) + 0.5) for i in range(count)],
    )


_NUMBERED = chart_request("area", channels={"x": "n", "y": "distance_km"})


def test_1000_rows_render_and_1001_refuse() -> None:
    drawn = Chart(render_case(KIND, _NUMBERED, _numbered(1000)).text)
    assert [len(_numbers(p.get("points") or "")) for p in drawn.polylines()] == [1000]
    assert problems_of(KIND, _NUMBERED, _numbered(1001)) == (
        ChartProblem(
            "c1",
            "area",
            ProblemCode.OVER_BOUND,
            "area draws at most 1000 rows; this data has 1001.",
            "Aggregate the rows (for example by day or week) or limit them to "
            "at most 1000.",
            rows=1001,
        ),
    )


# --- unstacked geometry ------------------------------------------------------

_GAPPED = [
    (d(4), 6.5, "Run"),
    (d(0), 3.5, "Run"),
    (d(3), 8.0, "Run"),
    (d(2), None, "Run"),
    (d(1), 5.25, "Run"),
]


def test_absent_y_breaks_both_fill_and_outline() -> None:
    chart = Chart(_svg(_GAPPED))
    assert len(chart.fills()) == 2
    outlines = chart.polylines()
    assert len(outlines) == 2
    first, second = (_numbers(o.get("points") or "") for o in outlines)
    assert [len(first), len(second)] == [2, 2]
    # in x order although the rows were not, and the values are the right ones
    assert [round(chart.value_at(y), 2) for _, y in first] == [3.5, 5.25]
    assert [round(chart.value_at(y), 2) for _, y in second] == [8.0, 6.5]
    step = first[1][0] - first[0][0]
    assert second[0][0] - first[1][0] == pytest.approx(2 * step, abs=0.02)
    # each fill covers exactly its own outline's x extent, down to the zero line
    for fill, outline in zip(chart.fills(), (first, second), strict=True):
        pts = _numbers(fill.get("d") or "")
        assert (pts[0][0], pts[1][0]) == (outline[0][0], outline[1][0])
        assert [y for _, y in pts[-2:]] == [chart.zero_px, chart.zero_px]
        assert fill.get("fill-opacity") == "0.2"
        assert fill.get("fill") == series_style(0).color


def test_absent_y_is_not_drawn_as_zero() -> None:
    chart = Chart(_svg(_GAPPED))
    values = [v for series in _series_values(chart) for v in series]
    assert sorted(round(v, 2) for v in values) == [3.5, 5.25, 6.5, 8.0]


def test_an_isolated_point_is_a_dot_without_fill() -> None:
    rows = [
        (d(0), 3.5, "Run"),
        (d(1), None, "Run"),
        (d(2), 5.0, "Run"),
        (d(3), 8.0, "Run"),
    ]
    chart = Chart(_svg(rows))
    assert len(chart.dots()) == 1
    assert len(chart.fills()) == 1
    assert len(chart.polylines()) == 1
    assert chart.dots()[0].get("d", "").startswith("M")


def test_unstacked_series_are_translucent_with_their_own_dash() -> None:
    chart = Chart(_svg(_CLEAN))
    assert [f.get("fill") for f in chart.fills()] == [
        series_style(0).color,
        series_style(1).color,
    ]
    assert {f.get("fill-opacity") for f in chart.fills()} == {"0.2"}
    assert [p.get("stroke-dasharray") for p in chart.polylines()] == [
        series_style(0).dash,
        series_style(1).dash,
    ]
    assert series_style(1).dash is not None
    assert chart.legend() == ["Run", "Bike"]


def test_zero_is_in_the_axis_even_when_every_value_is_positive() -> None:
    rows = [(d(2), 50.0, "Run"), (d(0), 30.0, "Run"), (d(1), 40.0, "Run")]
    chart = Chart(_svg(rows))
    assert "0" in chart.y_labels
    assert chart.zero_px == max(chart.grid_y)
    assert [y for _, y in _numbers(chart.fills()[0].get("d") or "")[-2:]] == [
        chart.zero_px,
        chart.zero_px,
    ]


def test_negative_values_hang_below_the_zero_line() -> None:
    rows = [(d(0), 3.0, "Run"), (d(1), -4.5, "Run")]
    chart = Chart(_svg(rows))
    low, high = (float(label) for label in (chart.y_labels[0], chart.y_labels[-1]))
    assert low < 0 < high or high < 0 < low
    assert [round(v, 2) for v in _series_values(chart)[0]] == [3.0, -4.5]


def test_colour_series_keep_first_appearance_with_absent_last() -> None:
    rows = [
        (d(0), 3.0, "Run"),
        (d(1), 4.0, "Bike"),
        (d(2), 5.0, None),
        (d(3), 6.0, "Run"),
    ]
    chart = Chart(_svg(rows))
    assert chart.legend() == ["Run", "Bike", "—"]
    assert [f.get("fill") for f in chart.fills()] == [series_style(0).color]
    assert [dot.get("stroke") for dot in chart.dots()] == [
        series_style(1).color,
        series_style(2).color,
    ]


def test_not_drawn_note_and_description_count_rows_by_first_missing_channel() -> None:
    rows = [
        (d(0), 3.0, "Run"),
        (None, 4.0, "Run"),
        (d(2), None, "Run"),
        (None, None, "Run"),
        (d(3), 5.5, "Run"),
        (d(4), None, "Run"),
    ]
    chart = Chart(_svg(rows))
    assert chart.notes() == ["Not drawn: 2 rows without x, 2 rows without y."]
    assert "Not drawn: 2 rows without x, 2 rows without y." in chart.description()


def test_no_note_when_every_row_is_drawn() -> None:
    chart = Chart(_svg(_CLEAN))
    assert chart.notes() == []
    assert "Not drawn" not in chart.description()


def test_description_of_a_gapped_chart() -> None:
    assert Chart(_svg(_GAPPED)).description() == (
        "Area chart: Weekly distance. x: day; y: distance (km); color: sport. "
        "5 rows, 1 series. Not drawn: 1 row without y. "
        "day from 2026-03-01 to 2026-03-05; distance (km) from 3.5 km to 8.0 km."
    )


# --- stacked geometry --------------------------------------------------------

_STACK_ROWS = [
    (d(3), 6.0, "Run"),
    (d(2), 7.0, "Swim"),
    (d(0), 5.0, "Bike"),
    (d(1), 4.5, "Run"),
    (d(0), 1.5, "Swim"),
    (d(2), 2.5, "Run"),
    (d(3), 0.0, "Swim"),
    (d(1), 0.75, "Bike"),
    (d(0), 3.0, "Run"),
    (d(3), 1.25, "Bike"),
    (d(1), 2.25, "Swim"),
    (d(2), 3.5, "Bike"),
]
_STACK_BY_SERIES = {
    "Run": [3.0, 4.5, 2.5, 6.0],
    "Swim": [1.5, 2.25, 7.0, 0.0],
    "Bike": [5.0, 0.75, 3.5, 1.25],
}


def test_stacked_bands_rise_in_legend_order_and_meet_edge_to_edge() -> None:
    chart = Chart(_svg(_STACK_ROWS, stack=True))
    assert chart.legend() == [
        "Run",
        "Swim",
        "Bike",
    ]  # first appearance, not alphabetical
    assert chart.fills() == []
    bands = chart.bands()
    assert [b.get("fill") for b in bands] == [series_style(i).color for i in range(3)]
    assert all(b.get("fill-opacity") is None for b in bands)
    edges = []
    for band in bands:
        points = _numbers(band.get("d") or "")
        assert len(points) == 8
        edges.append((points[:4], points[4:][::-1]))  # (upper, lower) by ascending x
    xs = [x for x, _ in edges[0][0]]
    assert xs == sorted(xs) and len(set(xs)) == 4
    assert all(
        [x for x, _ in upper] == xs == [x for x, _ in lower] for upper, lower in edges
    )
    assert [y for _, y in edges[0][1]] == [chart.zero_px] * 4
    for k in (1, 2):
        assert edges[k][1] == edges[k - 1][0]
    for (name, expected), (upper, lower) in zip(
        _STACK_BY_SERIES.items(), edges, strict=True
    ):
        thickness = [
            (lo - up) / chart.pixels_per_unit
            for (_, up), (_, lo) in zip(upper, lower, strict=True)
        ]
        assert [round(t, 2) for t in thickness] == expected, name


def test_each_stacked_band_is_topped_by_its_outline() -> None:
    chart = Chart(_svg(_STACK_ROWS, stack=True))
    tops = [_numbers(b.get("d") or "")[:4] for b in chart.bands()]
    outlines = [_numbers(o.get("points") or "") for o in chart.polylines()]
    assert outlines == tops
    assert [o.get("stroke") for o in chart.polylines()] == [
        series_style(i).color for i in range(3)
    ]


def test_stacked_legend_swatches_are_blocks() -> None:
    legend = _group(Chart(_svg(_STACK_ROWS, stack=True)).root, "ck-legend")[0]
    assert len(list(legend.iter(f"{NS}rect"))) == 3
    unstacked = _group(Chart(_svg(_CLEAN)).root, "ck-legend")[0]
    assert len(list(unstacked.iter(f"{NS}rect"))) == 0
    assert len(list(unstacked.iter(f"{NS}line"))) == 2


def test_stacked_axis_reaches_the_tallest_stack() -> None:
    chart = Chart(_svg(_STACK_ROWS, stack=True))
    assert float(chart.y_labels[-1]) >= 13.0  # d(2): 2.5 + 7.0 + 3.5


# --- goldens -----------------------------------------------------------------

_LONG_SERIES = ("Long steady-state aerobic base run", "Brick session bike then run")


def _long_rows() -> list[tuple[Value, ...]]:
    rows: list[tuple[Value, ...]] = []
    for i, value in enumerate([12.5, 18.25, 9.0, 21.5, 16.0]):
        rows.append((d(i * 7), value, _LONG_SERIES[0]))
    for i, value in enumerate([5.5, 7.75, 14.0, 3.25]):
        rows.append((d(i * 7 + 3), value, _LONG_SERIES[1]))
    return rows


_SPORT_LONG = Column("sport", ValueKind.CATEGORY, label="Training session category")

CASES: tuple[Case, ...] = (
    Case(
        "typical",
        _request(title="Weekly distance by sport"),
        chart_data(
            COLUMNS,
            [
                (d(3), 38.0, "Run"),
                (d(0), 23.5, "Run"),
                (d(1), 35.25, "Run"),
                (d(2), None, "Run"),
                (d(4), 36.5, "Run"),
                (d(5), None, "Run"),
                (d(6), 37.0, "Run"),
                (d(4), 22.0, "Bike"),
                (d(1), 49.0, "Bike"),
                (d(0), 44.75, "Bike"),
                (d(2), 47.5, "Bike"),
                (d(3), 21.25, "Bike"),
            ],
        ),
    ),
    Case("empty", _request(title="Weekly distance"), chart_data(COLUMNS, [])),
    Case(
        "all_absent",
        _request(title="Weekly distance"),
        chart_data(
            COLUMNS,
            [(d(0), None, "Run"), (d(1), None, "Bike"), (None, 6.0, "Run")],
        ),
    ),
    Case(
        "single",
        _request(title="Weekly distance"),
        chart_data(COLUMNS, [(d(2), 12.5, "Run")]),
    ),
    Case(
        "negative",
        _request(
            title="Weekly form",
            channels={"x": "day", "y": "distance_km"},
        ),
        chart_data(
            [DAY, DISTANCE],
            [
                (d(2), -1.0),
                (d(0), -4.5),
                (d(1), 2.0),
                (d(5), 3.25),
                (d(3), 6.5),
                (d(4), -8.0),
            ],
        ),
    ),
    Case(
        "long_labels",
        _request(
            title=(
                "Rolling twelve-week training distance split by session category, "
                "including warm-up, cool-down and recovery jogs"
            ),
        ),
        chart_data(
            [
                Column(
                    "day",
                    ValueKind.DATE,
                    label="Calendar date of the training session start",
                ),
                Column(
                    "distance_km",
                    ValueKind.NUMBER,
                    unit="km",
                    label="Distance covered including warm-up and cool-down",
                ),
                _SPORT_LONG,
            ],
            _long_rows(),
        ),
    ),
    Case(
        "at_bound",
        chart_request(
            "area",
            title="Distance per sample",
            channels={"x": "n", "y": "distance_km"},
        ),
        chart_data(
            [column("n"), DISTANCE],
            [(i, (i * 37 % 101) / 4) for i in range(1000)],
        ),
    ),
    Case(
        "narrow",
        chart_request(
            "area",
            title="Short week",
            channels={"x": "day", "y": "distance_km"},
            options={"width": 320},
        ),
        chart_data(
            [DAY, DISTANCE],
            [(d(2), 7.5), (d(0), 2.25), (d(1), 4.0), (d(3), 5.5)],
        ),
    ),
    Case(
        "stacked",
        _request(stack=True, title="Weekly distance by sport (stacked)"),
        chart_data(COLUMNS, _STACK_ROWS),
    ),
)


def test_cases_are_the_designed_names() -> None:
    assert [case.name for case in CASES] == [
        "typical",
        "empty",
        "all_absent",
        "single",
        "negative",
        "long_labels",
        "at_bound",
        "narrow",
        "stacked",
    ]


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.name)
def test_golden(case: Case) -> None:
    rendered = render_case(KIND, case.request, case.data)
    assert_golden(golden_path("area", case.name, "svg"), rendered.text)


def _by_name(name: str) -> Case:
    return next(case for case in CASES if case.name == name)


def test_case_preconditions() -> None:
    typical = _rows_of("typical")
    days = [row[0] for row in typical if isinstance(row[0], date)]
    assert any(row[1] is None for row in typical)  # an absent y to break on
    present = [row[1] for row in typical if isinstance(row[1], float)]
    assert min(present) > 20.0  # zero is not in the data, so only the kind adds it
    assert len(days) == len(typical) and days != sorted(days)
    assert len(_rows_of("at_bound")) == KIND.bound.limit
    assert any(isinstance(row[1], float) and row[1] < 0 for row in _rows_of("negative"))
    assert all(row[1] is None or row[0] is None for row in _rows_of("all_absent"))
    assert len(_rows_of("single")) == 1
    assert _rows_of("empty") == ()


def _rows_of(name: str) -> tuple[tuple[Value, ...], ...]:
    return _by_name(name).data.rows


def test_long_labels_golden_is_shortened_with_an_ellipsis() -> None:
    case = _by_name("long_labels")
    text = render_case(KIND, case.request, case.data).text
    chart = Chart(text)
    assert chart.legend()[0].endswith("…")
    assert chart.legend()[1] == _LONG_SERIES[1]
    assert text.count("…") == 2  # the legend entry and the title, nothing else
    assert _LONG_SERIES[0] not in text


def test_no_data_goldens_say_why() -> None:
    empty = render_case(KIND, _by_name("empty").request, _by_name("empty").data).text
    absent = render_case(
        KIND, _by_name("all_absent").request, _by_name("all_absent").data
    ).text
    assert "No data: no rows." in empty
    assert "None of the 3 rows has a value to draw." in absent
    assert "None of the" not in empty


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.name)
def test_every_text_stays_inside_the_chart(case: Case) -> None:
    svg = render_case(KIND, case.request, case.data).text
    root = ET.fromstring(svg)
    width = float(root.get("width") or "nan")
    texts = list(root.iter(f"{NS}text"))
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


def test_narrow_case_has_one_digit_y_labels_and_date_x() -> None:
    case = _by_name("narrow")
    chart = Chart(render_case(KIND, case.request, case.data).text)
    assert {len(label) for label in chart.y_labels} == {1}
    assert case.data.columns[0].kind is ValueKind.DATE


def _duration_description(minutes: Sequence[int]) -> str:
    columns = [column("elapsed", ValueKind.DURATION), column("pace_s_per_km")]
    rows = [(timedelta(minutes=m), float(m)) for m in minutes]
    request = chart_request(
        "area", channels={"x": "elapsed", "y": "pace_s_per_km"}, title="Pace"
    )
    return Chart(
        render_case(KIND, request, chart_data(columns, rows)).text
    ).description()


def test_duration_ranges_use_the_axis_clock_form() -> None:
    sub_hour = _duration_description([45, 25, 35])
    assert "elapsed (m:ss) from 25:00 to 45:00;" in sub_hour
    over_hour = _duration_description([95, 25, 35])
    assert "elapsed (h:mm:ss) from 0:25:00 to 1:35:00;" in over_hour


def _description_of(
    columns: Sequence[Column], rows: Sequence[Sequence[Value]], x: str, y: str
) -> str:
    request = chart_request("area", channels={"x": x, "y": y}, title="t")
    return Chart(
        render_case(KIND, request, chart_data(columns, rows)).text
    ).description()


def test_same_day_datetime_axis_names_its_date_in_the_range_title() -> None:
    columns = [column("t", ValueKind.DATETIME), column("load")]
    rows = [
        (datetime(2026, 3, 1, 7, 0), 3.0),
        (datetime(2026, 3, 1, 6, 0), 5.0),
    ]
    text = _description_of(columns, rows, "t", "load")
    assert "t (2026-03-01) from 2026-03-01 06:00 to 2026-03-01 07:00;" in text


def test_a_number_column_with_a_duration_unit_reads_as_a_clock() -> None:
    columns = [column("elapsed_s", unit="s"), column("load")]
    rows = [(5700, 3.0), (1500, 5.0), (2100, 4.0)]
    text = _description_of(columns, rows, "elapsed_s", "load")
    assert "elapsed (h:mm:ss) from 0:25:00 to 1:35:00;" in text


def test_the_high_bound_follows_an_axis_that_reaches_an_hour() -> None:
    columns = [column("x"), column("elapsed", ValueKind.DURATION)]
    rows = [(1, timedelta(minutes=55)), (2, timedelta(minutes=20))]
    text = _description_of(columns, rows, "x", "elapsed")
    assert "elapsed (h:mm:ss) from 0:20:00 to 0:55:00" in text


def test_a_stack_with_one_x_draws_no_band() -> None:
    rows = [(d(0), 3.0, "Run"), (d(0), 1.5, "Bike")]
    chart = Chart(_svg(rows, stack=True))
    assert chart.bands() == []
    assert len(chart.dots()) == 2


def test_no_stale_goldens() -> None:
    directory = golden_path("area", "x", "svg").parent
    on_disk = sorted(path.name for path in directory.iterdir())
    assert on_disk == sorted(f"{case.name}.svg" for case in CASES)


def main() -> None:
    for case in CASES:
        rendered = render_case(KIND, case.request, case.data)
        write_golden(golden_path("area", case.name, "svg"), rendered.text)


if __name__ == "__main__":
    main()
