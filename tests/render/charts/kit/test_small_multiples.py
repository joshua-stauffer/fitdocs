"""The ``small-multiples`` kind: declaration, refusals, panel order and grid, shared
and independent scales, label placement, empty panels, texts and goldens.

Requirements 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9, 2.10, 10.1, 10.2, 10.3, 10.4,
10.5, 10.6, 10.7, 12.1, 12.3.

Run ``uv run python -m tests.render.charts.kit.test_small_multiples`` to
(re)write the goldens under ``golden/small-multiples/``; a pytest run never
writes them.
"""

from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from collections.abc import Mapping, Sequence
from datetime import date, timedelta

import pytest

from fitdocs.render.charts.kit.data import Column, Value, ValueKind
from fitdocs.render.charts.kit.kinds.small_multiples import KIND
from fitdocs.render.charts.kit.layout import plan_frame, text_width
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
SHOE = column("shoe", ValueKind.CATEGORY)
CHANNELS = {"x": "day", "y": "distance_km", "facet": "shoe"}

D = date


def _render(
    columns: Sequence[Column],
    rows: Sequence[Sequence[Value]],
    channels: Mapping[str, str] = CHANNELS,
    options: Mapping[str, OptionValue] | None = None,
    *,
    title: str = "Shoe mileage",
) -> str:
    request = chart_request(
        "small-multiples", ref="s1", title=title, channels=channels, options=options
    )
    return render_case(KIND, request, chart_data(columns, rows)).text


def _refusal(
    columns: Sequence[Column],
    rows: Sequence[Sequence[Value]],
    channels: Mapping[str, str] = CHANNELS,
    options: Mapping[str, OptionValue] | None = None,
) -> tuple[ChartProblem, ...]:
    request = chart_request(
        "small-multiples", ref="s1", channels=channels, options=options
    )
    return problems_of(KIND, request, chart_data(columns, rows))


# --- the golden fixtures --------------------------------------------------------

# Shoes in first-appearance order Pegasus, Alphafly, Zoom Fly, Clifton, which is
# not alphabetical (Alphafly, Clifton, Pegasus, Zoom Fly). Dates are out of order
# inside each shoe. Alphafly has an absent y inside its line and the largest
# values (so a shared y scale differs from a per-panel one); Zoom Fly holds a
# recorded zero; one Clifton row has no day.
TYPICAL_ROWS: tuple[tuple[Value, ...], ...] = (
    (D(2026, 3, 9), 8.4, "Pegasus"),
    (D(2026, 3, 2), 5.2, "Pegasus"),
    (D(2026, 3, 23), 11.8, "Pegasus"),
    (D(2026, 3, 16), 9.1, "Pegasus"),
    (D(2026, 3, 10), 21.5, "Alphafly"),
    (D(2026, 3, 3), 16.0, "Alphafly"),
    (D(2026, 3, 24), 19.2, "Alphafly"),
    (D(2026, 3, 17), None, "Alphafly"),
    (D(2026, 3, 31), 24.0, "Alphafly"),
    (D(2026, 3, 11), 6.5, "Zoom Fly"),
    (D(2026, 3, 4), 0.0, "Zoom Fly"),
    (D(2026, 3, 25), 7.3, "Zoom Fly"),
    (D(2026, 3, 18), 10.4, "Zoom Fly"),
    (D(2026, 3, 12), 3.3, "Clifton"),
    (None, 15.5, "Clifton"),
    (D(2026, 3, 5), 4.1, "Clifton"),
    (D(2026, 3, 26), 8.9, "Clifton"),
)

# One shoe whose every y is absent, one shoe with values, and the absent facet.
EMPTY_PANEL_ROWS: tuple[tuple[Value, ...], ...] = (
    (D(2026, 3, 2), 6.0, "Pegasus"),
    (D(2026, 3, 9), 7.5, "Pegasus"),
    (D(2026, 3, 16), 5.5, "Pegasus"),
    (D(2026, 3, 3), None, "Retired"),
    (D(2026, 3, 10), None, "Retired"),
    (D(2026, 3, 4), 4.0, "Zoom Fly"),
    (D(2026, 3, 11), 9.5, "Zoom Fly"),
    (D(2026, 3, 5), 12.0, None),
    (D(2026, 3, 12), 10.0, None),
)

WEEK = column("week")
LOAD = column("load_w", unit="w")
SPORT = column("sport", ValueKind.CATEGORY)
INDEPENDENT_ROWS: tuple[tuple[Value, ...], ...] = (
    (1.0, 4.0, "Easy"),
    (2.0, 9.0, "Easy"),
    (3.0, 6.0, "Easy"),
    (4.0, 10.0, "Easy"),
    (1.0, 120.0, "Tempo"),
    (2.0, 180.0, "Tempo"),
    (3.0, 150.0, "Tempo"),
    (4.0, 200.0, "Tempo"),
    (1.0, 5200.0, "Long"),
    (2.0, 7400.0, "Long"),
    (3.0, 6100.0, "Long"),
    (4.0, 9000.0, "Long"),
)

OFFSET = column("offset_m", unit="m")
DELTA = column("delta_kg", unit="kg")
SIDE = column("side", ValueKind.CATEGORY)
NEGATIVE_ROWS: tuple[tuple[Value, ...], ...] = (
    (4.0, -3.5, "Left"),
    (-6.0, 2.25, "Left"),
    (0.0, 0.0, "Left"),
    (-1.0, -8.75, "Right"),
    (9.0, 6.5, "Right"),
    (-3.0, -0.5, "Right"),
    (2.0, -12.0, "Centre"),
    (5.0, -4.0, "Centre"),
    (-7.0, -9.5, "Centre"),
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
LONG_F = column("rider", ValueKind.CATEGORY)
LONG_ROWS: tuple[tuple[Value, ...], ...] = (
    (timedelta(minutes=50), 250.0, "A very long rider name that cannot fit its panel"),
    (timedelta(minutes=10), 180.0, "A very long rider name that cannot fit its panel"),
    (timedelta(minutes=30), 310.0, "Another extraordinarily long rider name indeed"),
    (timedelta(minutes=70), 205.0, "Another extraordinarily long rider name indeed"),
    (timedelta(minutes=20), 190.0, "Short"),
    (timedelta(minutes=45), 240.0, "Short"),
)
LONG_TITLE = (
    "A deliberately long chart title that cannot possibly fit within the width of"
    " the chart however small its type"
)

PANEL_LIMIT = 12
ROW_LIMIT = 2000


def _grid_rows(panels: int, per_panel: int) -> tuple[tuple[Value, ...], ...]:
    return tuple(
        (float(j), float((p * 31 + j * 17) % 53) + j / 10, f"P{p:02d}")
        for p in range(panels)
        for j in range(per_panel)
    )


def _many_rows(count: int) -> tuple[tuple[Value, ...], ...]:
    """``count`` rows over four facets, every (facet, x) distinct."""
    return tuple(
        (float(i // 4), float((i * 37) % 211) + i / 1000, f"F{i % 4}")
        for i in range(count)
    )


N = column("n")
V = column("value")
P = column("panel", ValueKind.CATEGORY)
GRID_CHANNELS = {"x": "n", "y": "value", "facet": "panel"}

CASES: tuple[Case, ...] = (
    Case(
        "typical",
        chart_request(
            "small-multiples", ref="s1", title="Shoe mileage", channels=CHANNELS
        ),
        chart_data((DAY, KM, SHOE), TYPICAL_ROWS),
    ),
    Case(
        "empty",
        chart_request(
            "small-multiples", ref="s1", title="Shoe mileage", channels=CHANNELS
        ),
        chart_data((DAY, KM, SHOE), []),
    ),
    Case(
        "all_absent",
        chart_request(
            "small-multiples", ref="s1", title="Shoe mileage", channels=CHANNELS
        ),
        chart_data(
            (DAY, KM, SHOE),
            [(D(2026, 5, 2), None, "Pegasus"), (None, 4.5, "Zoom Fly")],
        ),
    ),
    Case(
        "single",
        chart_request(
            "small-multiples", ref="s1", title="Shoe mileage", channels=CHANNELS
        ),
        chart_data((DAY, KM, SHOE), [(D(2026, 3, 9), 8.4, "Pegasus")]),
    ),
    Case(
        "negative",
        chart_request(
            "small-multiples",
            ref="s1",
            title="Net change",
            channels={"x": "offset_m", "y": "delta_kg", "facet": "side"},
        ),
        chart_data((OFFSET, DELTA, SIDE), NEGATIVE_ROWS),
    ),
    Case(
        "independent",
        chart_request(
            "small-multiples",
            ref="s1",
            title="Training load by session type",
            channels={"x": "week", "y": "load_w", "facet": "sport"},
            options={"y_axes": "independent", "columns": 2},
        ),
        chart_data((WEEK, LOAD, SPORT), INDEPENDENT_ROWS),
    ),
    Case(
        "empty_panel",
        chart_request(
            "small-multiples", ref="s1", title="Shoe mileage", channels=CHANNELS
        ),
        chart_data((DAY, KM, SHOE), EMPTY_PANEL_ROWS),
    ),
    Case(
        "long_labels",
        chart_request(
            "small-multiples",
            ref="s1",
            title=LONG_TITLE,
            channels={"x": "elapsed_time", "y": "power_w", "facet": "rider"},
        ),
        chart_data((LONG_X, LONG_Y, LONG_F), LONG_ROWS),
    ),
    Case(
        "at_bound",
        chart_request(
            "small-multiples", ref="s1", title="Twelve panels", channels=GRID_CHANNELS
        ),
        chart_data((N, V, P), _grid_rows(PANEL_LIMIT, 4)),
    ),
)


def _case(name: str) -> Case:
    return next(case for case in CASES if case.name == name)


def _render_case(case: Case) -> str:
    return render_case(KIND, case.request, case.data).text


# --- parsing helpers -------------------------------------------------------------


def _root(text: str) -> ET.Element:
    return ET.fromstring(text)


def _translate(element: ET.Element) -> tuple[float, float] | None:
    match = re.fullmatch(
        r"translate\(([^,]+),([^)]+)\)", element.get("transform") or ""
    )
    return None if match is None else (float(match[1]), float(match[2]))


def _panels(text: str) -> list[ET.Element]:
    """The panel groups, in document order."""
    return [g for g in _root(text) if g.tag == f"{SVG}g" and _translate(g) is not None]


def _origin(panel: ET.Element) -> tuple[float, float]:
    origin = _translate(panel)
    assert origin is not None
    return origin


def _texts(element: ET.Element) -> list[ET.Element]:
    return list(element.iter(f"{SVG}text"))


def _panel_title(panel: ET.Element) -> str:
    (title,) = [t for t in _texts(panel) if t.get("text-anchor") is None]
    return title.text or ""


def _titles(text: str) -> list[str]:
    return [_panel_title(p) for p in _panels(text)]


def _y_labels(panel: ET.Element) -> list[str]:
    return [t.text or "" for t in _texts(panel) if t.get("text-anchor") == "end"]


def _x_labels(panel: ET.Element) -> list[str]:
    return [
        t.text or ""
        for t in _texts(panel)
        if t.get("text-anchor") == "middle" and t.text != "No values"
    ]


def _grid_ys(panel: ET.Element) -> list[float]:
    (grid,) = [g for g in panel if g.get("class") == "ck-grid"]
    return [float(line.get("y1") or "nan") for line in grid]


def _mark_children(panel: ET.Element) -> list[ET.Element]:
    return [c for g in panel if g.get("class") == "ck-marks" for c in g]


def _outer_plot_width(text: str) -> float:
    plan = plan_frame(
        int(_root(text).get("width") or "0"),
        500,
        legend=(),
        y_label_width=0.0,
        x_label_overhang=0.0,
        has_x_title=True,
        has_y_title=True,
        notes=0,
    )
    return plan.plot.width


def _stride(text: str) -> float:
    """The panels' x-stride: the layout's cell width (0 when one column)."""
    origins = [_origin(p) for p in _panels(text)]
    return origins[1][0] - origins[0][0] if len(origins) > 1 else 0.0


def _columns(text: str) -> int:
    """The layout's column count: the outer plot width over the cell width."""
    stride = _stride(text)
    return 1 if stride <= 0 else round(_outer_plot_width(text) / stride)


def _desc(text: str) -> str:
    element = _root(text).find(f"{SVG}desc")
    assert element is not None
    return element.text or ""


def _outer_notes(text: str) -> list[str]:
    return [
        t.text or ""
        for g in _root(text)
        if g.get("class") == "ck-notes"
        for t in _texts(g)
    ]


def _height(text: str) -> int:
    return int(_root(text).get("height") or "0")


def _plain(facets: int, **options: OptionValue) -> str:
    return _render((N, V, P), _grid_rows(facets, 4), GRID_CHANNELS, options or None)


# --- declaration -----------------------------------------------------------------


def test_declaration() -> None:
    assert KIND.name == "small-multiples"
    assert KIND.description == "A grid of small line charts, one per facet value"
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
            "The horizontal position in every panel: a number, duration, date "
            "or date-time.",
        ),
        ChannelSpec(
            "y",
            (ValueKind.NUMBER, ValueKind.DURATION),
            True,
            "The vertical value: a number or duration.",
        ),
        ChannelSpec(
            "facet",
            (ValueKind.CATEGORY, ValueKind.BOOLEAN, ValueKind.DATE),
            True,
            "One panel per value of this column, titled with the value.",
        ),
    )
    assert KIND.options == (
        OptionSpec(
            "y_axes",
            OptionType.CHOICE,
            "Whether every panel shares one y scale or has its own.",
            "shared",
            choices=("shared", "independent"),
        ),
        OptionSpec(
            "columns",
            OptionType.INTEGER,
            "The number of panel columns; unset, it follows the chart width.",
            None,
            minimum=1,
            maximum=6,
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
            None,
            minimum=160,
            maximum=1200,
        ),
    )
    assert KIND.bound == MarkBound(
        12, "panels", OverBound.REFUSE, "At most 12 panels and 2000 rows."
    )
    assert KIND.max_series is None
    assert KIND.uses_all_columns is False


def test_columns_option_is_one_to_six() -> None:
    for bad in (0, 7):
        request = chart_request(
            "small-multiples", channels=GRID_CHANNELS, options={"columns": bad}
        )
        problems = problems_of(KIND, request, chart_data((N, V, P), _grid_rows(2, 2)))
        assert [p.code for p in problems] == [ProblemCode.OPTION_VALUE]
    for good in (1, 6):
        _plain(2, columns=good)


# --- panel order -----------------------------------------------------------------


def test_panels_are_in_first_appearance_not_alphabetical() -> None:
    assert _titles(_render_case(_case("typical"))) == [
        "Pegasus",
        "Alphafly",
        "Zoom Fly",
        "Clifton",
    ]


def test_date_facets_ascend_and_the_absent_facet_is_last() -> None:
    rows: list[tuple[Value, ...]] = [
        (1.0, 1.0, D(2026, 3, 9)),
        (1.0, 2.0, None),
        (1.0, 3.0, D(2026, 1, 5)),
        (1.0, 4.0, D(2026, 2, 1)),
    ]
    text = _render(
        (N, V, column("month", ValueKind.DATE)),
        rows,
        {"x": "n", "y": "value", "facet": "month"},
    )
    assert _titles(text) == ["2026-01-05", "2026-02-01", "2026-03-09", "—"]


def test_a_boolean_facet_is_in_first_appearance() -> None:
    rows: list[tuple[Value, ...]] = [
        (1.0, 1.0, True),
        (1.0, 2.0, False),
        (2.0, 3.0, True),
    ]
    text = _render(
        (N, V, column("indoor", ValueKind.BOOLEAN)),
        rows,
        {"x": "n", "y": "value", "facet": "indoor"},
    )
    assert _titles(text) == ["true", "false"]


def test_panels_run_left_to_right_then_top_to_bottom() -> None:
    panels = _panels(_plain(5, columns=2))
    origins = [_origin(p) for p in panels]
    xs = sorted({o[0] for o in origins})
    ys = sorted({o[1] for o in origins})
    assert len(xs) == 2 and len(ys) == 3
    assert origins == [(xs[i % 2], ys[i // 2]) for i in range(5)]


def test_every_panel_has_identical_geometry() -> None:
    text = _render_case(_case("typical"))
    baselines = []
    for panel in _panels(text):
        axes = [g for g in panel if g.get("class") == "ck-axis"]
        lines = [
            tuple(g.find(f"{SVG}line").get(k) for k in ("x1", "y1", "x2", "y2"))  # type: ignore[union-attr]
            for g in axes
        ]
        baselines.append(tuple(lines))
    assert len(set(baselines)) == 1


# --- columns ---------------------------------------------------------------------


def test_outer_plot_width_is_688_at_720() -> None:
    plan = plan_frame(
        720,
        500,
        legend=(),
        y_label_width=0.0,
        x_label_overhang=0.0,
        has_x_title=True,
        has_y_title=True,
        notes=0,
    )
    assert plan.plot.width == 688.0  # floor(688 / 180) == 3


def test_auto_columns_by_width() -> None:
    typical = _render_case(_case("typical"))
    assert _root(typical).get("width") == "720"
    assert _columns(typical) == 3
    rows = _grid_rows(8, 3)
    wide = _render((N, V, P), rows, GRID_CHANNELS, {"width": 1600})
    assert _columns(wide) == 6  # floor(1568 / 180) = 8, capped at 6
    narrow = _render((N, V, P), rows, GRID_CHANNELS, {"width": 320})
    assert _columns(narrow) == 1  # floor(288 / 180) = 1
    fewer = _render((N, V, P), _grid_rows(4, 3), GRID_CHANNELS, {"width": 1600})
    assert _columns(fewer) == 4  # n when fewer than six
    one = _render((N, V, P), _grid_rows(1, 3), GRID_CHANNELS)
    (panel,) = _panels(one)
    baseline = panel.find(f"{SVG}g/{SVG}line")
    assert baseline is not None
    # one panel takes the whole outer plot (688 px), not a third of it
    assert float(baseline.get("x2") or "0") > 600


def test_columns_option_is_honoured() -> None:
    assert _columns(_plain(8, columns=2)) == 2
    assert _columns(_plain(8, columns=4)) == 4
    assert _columns(_plain(8, columns=1)) == 1
    assert _columns(_plain(8, columns=6)) == 6


def test_explicit_columns_divide_the_plot_even_with_fewer_panels() -> None:
    text = _plain(2, columns=6)
    assert _stride(text) == 114  # floor(688 / 6), not 688 / 2
    assert _columns(text) == 6


def test_auto_height_holds_the_rows_of_panels() -> None:
    three = _height(_plain(3))  # one row of panels
    six = _height(_plain(6))  # two rows
    nine = _height(_plain(9))  # three rows
    assert six - three == nine - six == 140
    assert _height(_plain(4, columns=1)) - three == 3 * 140


def test_a_requested_height_below_the_auto_height_squeezes_the_panels() -> None:
    auto = _height(_plain(6))
    assert auto > 300
    text = _plain(6, height=300)
    assert _height(text) == 300
    found = _absolute_texts(_root(text))
    assert len(found) == text.count("<text")
    assert max(y for _, _, y in found) <= 300 - 8 + 1e-6
    # the second row of panels starts above the auto layout's second row
    assert _origin(_panels(text)[3])[1] < _origin(_panels(_plain(6))[3])[1]


# --- shared and independent scales -------------------------------------------------


def test_shared_y_has_equal_ticks_in_every_panel_and_labels_in_the_first_column() -> (
    None
):
    text = _render_case(_case("typical"))
    panels = _panels(text)
    assert _columns(text) == 3
    grids = [_grid_ys(p) for p in panels]
    assert grids[0] and all(g == grids[0] for g in grids)
    labelled = [bool(_y_labels(p)) for p in panels]
    assert labelled == [True, False, False, True]
    assert _y_labels(panels[0]) == _y_labels(panels[3])
    assert len(_y_labels(panels[0])) == len(grids[0])


def test_shared_y_labels_on_every_first_column_panel_of_a_taller_grid() -> None:
    panels = _panels(_plain(7, columns=2))
    assert [bool(_y_labels(p)) for p in panels] == [i % 2 == 0 for i in range(7)]


def test_shared_y_marks_use_one_scale() -> None:
    # Two panels with the same y values at the same x draw the same polyline.
    rows: list[tuple[Value, ...]] = [
        (1.0, 10.0, "A"),
        (2.0, 30.0, "A"),
        (1.0, 10.0, "B"),
        (2.0, 30.0, "B"),
        (1.0, 100.0, "C"),
        (2.0, 300.0, "C"),
    ]
    text = _render((N, V, P), rows, GRID_CHANNELS)
    lines = [[c.get("points") for c in _mark_children(p)] for p in _panels(text)]
    assert lines[0] == lines[1] != lines[2]
    # C reaches higher (a smaller y pixel) than the others on the shared scale.
    first = [float(pt.split(",")[1]) for pt in (lines[0][0] or "").split()]
    third = [float(pt.split(",")[1]) for pt in (lines[2][0] or "").split()]
    assert min(third) < min(first)


def test_independent_y_has_its_own_domain_and_labels_in_every_panel() -> None:
    text = _render_case(_case("independent"))
    panels = _panels(text)
    labels = [_y_labels(p) for p in panels]
    assert all(labels)
    assert len({tuple(label) for label in labels}) == 3
    # each line spans most of the plot height in its own domain
    for p in panels:
        ys = [
            float(pt.split(",")[1])
            for c in _mark_children(p)
            for pt in (c.get("points") or "").split()
        ]
        assert max(ys) - min(ys) > 45


def test_shared_scale_would_flatten_the_small_panels() -> None:
    shared = _render(
        (WEEK, LOAD, SPORT),
        INDEPENDENT_ROWS,
        {"x": "week", "y": "load_w", "facet": "sport"},
        {"columns": 2},
    )
    ys = [
        float(pt.split(",")[1])
        for c in _mark_children(_panels(shared)[0])
        for pt in (c.get("points") or "").split()
    ]
    assert max(ys) - min(ys) < 15  # Easy spans 4..10 on a 0..10000 axis


def test_independent_duration_axes_agree_on_one_form() -> None:
    sec = column("moving", ValueKind.DURATION)
    rows: list[tuple[Value, ...]] = [
        (1.0, timedelta(minutes=1), "Short"),
        (2.0, timedelta(minutes=8), "Short"),
        (1.0, timedelta(hours=2), "Long"),
        (2.0, timedelta(hours=5), "Long"),
    ]
    text = _render(
        (N, sec, P),
        rows,
        {"x": "n", "y": "moving", "facet": "panel"},
        {"y_axes": "independent"},
    )
    labels = [label for p in _panels(text) for label in _y_labels(p)]
    assert labels and all(label.count(":") == 2 for label in labels)
    assert "moving (h:mm:ss)" in _desc(text)


def test_independent_sub_hour_duration_axes_use_the_short_form() -> None:
    sec = column("moving", ValueKind.DURATION)
    rows: list[tuple[Value, ...]] = [
        (1.0, timedelta(minutes=1), "Short"),
        (2.0, timedelta(minutes=8), "Short"),
        (1.0, timedelta(minutes=3), "Other"),
        (2.0, timedelta(minutes=9), "Other"),
    ]
    text = _render(
        (N, sec, P),
        rows,
        {"x": "n", "y": "moving", "facet": "panel"},
        {"y_axes": "independent"},
    )
    labels = [label for p in _panels(text) for label in _y_labels(p)]
    assert labels and all(label.count(":") == 1 for label in labels)
    assert "moving (m:ss)" in _desc(text)


# --- x labels --------------------------------------------------------------------


def test_x_labels_only_on_panels_with_no_panel_below() -> None:
    panels = _panels(_plain(5, columns=4))
    assert [bool(_x_labels(p)) for p in panels] == [False, True, True, True, True]


def test_x_labels_on_the_last_row_of_a_typical_chart() -> None:
    panels = _panels(_render_case(_case("typical")))
    # three columns, four panels: panel 0 has panel 3 below it
    assert [bool(_x_labels(p)) for p in panels] == [False, True, True, True]


def test_every_x_axis_is_shared() -> None:
    panels = _panels(_render_case(_case("typical")))
    labelled = [_x_labels(p) for p in panels if _x_labels(p)]
    assert all(label == labelled[0] for label in labelled)


# --- empty panels ----------------------------------------------------------------


def test_a_facet_with_no_values_draws_no_values() -> None:
    text = _render_case(_case("empty_panel"))
    panels = _panels(text)
    assert _titles(text) == ["Pegasus", "Retired", "Zoom Fly", "—"]
    messages = [[t.text for t in _texts(p) if t.text == "No values"] for p in panels]
    assert messages == [[], ["No values"], [], []]
    retired = panels[1]
    assert not _mark_children(retired)
    assert retired.findall(f"{SVG}g")  # its axes
    assert [g.get("class") for g in retired if g.tag == f"{SVG}g"] == [
        "ck-grid",
        "ck-axis",
        "ck-axis",
    ]


def test_the_message_is_centred_in_the_panel_plot() -> None:
    text = _render_case(_case("empty_panel"))
    retired = _panels(text)[1]
    (message,) = [t for t in _texts(retired) if t.text == "No values"]
    assert message.get("text-anchor") == "middle"
    axis = [g for g in retired if g.get("class") == "ck-axis"][0]
    baseline = axis.find(f"{SVG}line")
    assert baseline is not None
    # the bottom axis baseline runs along the plot's bottom edge
    left = float(baseline.get("x1") or "nan")
    right = float(baseline.get("x2") or "nan")
    assert float(message.get("x") or "nan") == pytest.approx((left + right) / 2)


def test_a_panel_with_a_point_but_no_value_in_the_other_channel_is_empty() -> None:
    # Panel B's only row has no x; panel C's only row has no y.
    rows: list[tuple[Value, ...]] = [
        (1.0, 1.0, "A"),
        (2.0, 2.0, "A"),
        (None, 5.0, "B"),
        (1.0, None, "C"),
    ]
    text = _render((N, V, P), rows, GRID_CHANNELS)
    assert [bool(_mark_children(p)) for p in _panels(text)] == [True, False, False]
    assert text.count(">No values<") == 2


# --- marks -----------------------------------------------------------------------


def test_no_line_carries_a_dash_and_every_panel_has_one_style() -> None:
    for case in CASES:
        text = _render_case(case)
        assert "stroke-dasharray" not in text
        strokes = {
            c.get("stroke")
            for p in _panels(text)
            for c in _mark_children(p)
            if c.get("stroke")
        }
        assert len(strokes) <= 1


def test_an_absent_y_splits_the_line_and_is_not_zero() -> None:
    text = _render_case(_case("typical"))
    alphafly = _panels(text)[1]
    marks = _mark_children(alphafly)
    # the absent 3-17 splits 3-03..3-10 from 3-24..3-31
    assert [c.tag.removeprefix(SVG) for c in marks] == ["polyline", "polyline"]
    ys = [
        float(pt.split(",")[1]) for c in marks for pt in (c.get("points") or "").split()
    ]
    assert len(ys) == 4
    # the shared axis reaches zero (Zoom Fly holds a recorded 0.0); an absent y
    # drawn as zero would pull the line down to the lowest gridline
    gridlines = _grid_ys(alphafly)
    assert gridlines and max(gridlines) > max(ys)


def test_a_recorded_zero_is_drawn_not_a_gap() -> None:
    text = _render_case(_case("typical"))
    zoom = _panels(text)[2]
    (line,) = _mark_children(zoom)
    assert len((line.get("points") or "").split()) == 4


def test_rows_out_of_x_order_are_joined_in_x_order() -> None:
    text = _render_case(_case("typical"))
    (line,) = _mark_children(_panels(text)[0])
    xs = [float(pt.split(",")[0]) for pt in (line.get("points") or "").split()]
    assert xs == sorted(xs) and len(xs) == 4


# --- notes and description -------------------------------------------------------


def test_rows_without_x_or_y_are_counted_in_the_note_and_the_description() -> None:
    text = _render_case(_case("typical"))
    assert _outer_notes(text) == ["Not drawn: 1 row without x, 1 row without y."]
    assert "Not drawn: 1 row without x, 1 row without y." in _desc(text)


def test_a_row_absent_on_both_channels_counts_under_x_only() -> None:
    rows: list[tuple[Value, ...]] = [
        (1.0, 1.0, "A"),
        (None, None, "A"),
        (None, 2.0, "A"),
        (3.0, None, "A"),
    ]
    text = _render((N, V, P), rows, GRID_CHANNELS)
    note = "Not drawn: 2 rows without x, 1 row without y."
    assert _outer_notes(text) == [note]
    assert note in _desc(text)


def test_a_complete_chart_has_no_note() -> None:
    text = _plain(3)
    assert _outer_notes(text) == []
    assert "Not drawn" not in _desc(text)


def test_the_description_names_the_kind_channels_rows_and_ranges() -> None:
    desc = _desc(_render_case(_case("typical")))
    assert desc == (
        "Small-multiples chart: Shoe mileage. x: day; y: distance (km); "
        "facet: shoe. 17 rows. Not drawn: 1 row without x, 1 row without y. "
        "day from 2026-03-02 to 2026-03-31; distance (km) from 0.0 km to 24.0 km."
    )


def test_the_axis_titles_are_the_chart_level_titles() -> None:
    text = _render_case(_case("typical"))
    chart_titles = [
        t.text for g in _root(text) if g.get("class") == "ck-axis" for t in _texts(g)
    ]
    assert chart_titles == ["day", "distance (km)"]
    for panel in _panels(text):
        assert "distance (km)" not in [t.text for t in _texts(panel)]


def test_an_hours_duration_x_range_is_in_its_axis_form() -> None:
    rows: list[tuple[Value, ...]] = [
        (timedelta(minutes=5), 1.0, "A"),
        (timedelta(hours=2), 2.0, "A"),
    ]
    text = _render(
        (column("elapsed", ValueKind.DURATION), V, P),
        rows,
        {"x": "elapsed", "y": "value", "facet": "panel"},
    )
    assert "elapsed (h:mm:ss) from 0:05:00 to 2:00:00" in _desc(text)


# --- refusals --------------------------------------------------------------------


def test_twelve_panels_render_and_thirteen_refuse_alone() -> None:
    assert _titles(_plain(12)) == [f"P{i:02d}" for i in range(12)]
    assert _refusal((N, V, P), _grid_rows(13, 2), GRID_CHANNELS) == (
        ChartProblem(
            ref="s1",
            kind="small-multiples",
            code=ProblemCode.OVER_BOUND,
            message="small-multiples draws at most 12 panels; this data has 13.",
            fix="Filter the facet column to at most 12 values.",
            channel="facet",
            column="panel",
            rows=13,
        ),
    )


def test_the_absent_facet_counts_as_a_panel() -> None:
    rows = [*_grid_rows(12, 1), (1.0, 1.0, None)]
    (problem,) = _refusal((N, V, P), rows, GRID_CHANNELS)
    assert problem.rows == 13 and problem.channel == "facet"


def test_2001_rows_refuse_alone_and_2000_render() -> None:
    assert _refusal((N, V, P), _many_rows(2001), GRID_CHANNELS) == (
        ChartProblem(
            ref="s1",
            kind="small-multiples",
            code=ProblemCode.OVER_BOUND,
            message="small-multiples draws at most 2000 rows; this data has 2001.",
            fix="Aggregate the rows (for example by day or week) or limit them to "
            "at most 2000.",
            rows=2001,
        ),
    )
    text = _render((N, V, P), _many_rows(2000), GRID_CHANNELS)
    assert sum(len(_mark_children(p)) for p in _panels(text)) == 4
    points = sum(
        len((c.get("points") or "").split())
        for p in _panels(text)
        for c in _mark_children(p)
    )
    assert points == 2000


def test_both_limits_exceeded_report_both() -> None:
    rows = tuple((float(i // 14), float(i % 7), f"P{i % 14:02d}") for i in range(2002))
    problems = _refusal((N, V, P), rows, GRID_CHANNELS)
    assert [(p.channel, p.rows) for p in problems] == [("facet", 14), (None, 2002)]


def test_a_duplicate_facet_and_x_refuses_alone_naming_both_and_the_row() -> None:
    rows: list[tuple[Value, ...]] = [
        (D(2026, 3, 2), 1.0, "Pegasus"),
        (D(2026, 3, 9), 2.0, "Pegasus"),
        (D(2026, 3, 2), 3.0, "Zoom Fly"),
        (D(2026, 3, 9), 4.0, "Pegasus"),
    ]
    (problem,) = _refusal((DAY, KM, SHOE), rows)
    assert problem.code is ProblemCode.DUPLICATE_POSITION
    assert problem.row == 3
    assert "Row 3 repeats row 1" in problem.message
    assert "shoe (Pegasus)" in problem.message
    assert "day (2026-03-09)" in problem.message
    assert problem.kind == "small-multiples"


def test_the_same_x_in_two_facets_is_not_a_duplicate() -> None:
    rows: list[tuple[Value, ...]] = [
        (1.0, 1.0, "A"),
        (1.0, 2.0, "B"),
    ]
    _render((N, V, P), rows, GRID_CHANNELS)


def test_rows_without_x_in_one_facet_are_not_duplicates_of_each_other() -> None:
    rows: list[tuple[Value, ...]] = [
        (None, 1.0, "A"),
        (None, 2.0, "A"),
        (1.0, 3.0, "A"),
    ]
    text = _render((N, V, P), rows, GRID_CHANNELS)
    assert _outer_notes(text) == ["Not drawn: 2 rows without x."]


def test_the_absent_facet_duplicates_too() -> None:
    rows: list[tuple[Value, ...]] = [(1.0, 1.0, None), (1.0, 2.0, None)]
    (problem,) = _refusal((N, V, P), rows, GRID_CHANNELS)
    assert problem.code is ProblemCode.DUPLICATE_POSITION and problem.row == 1


# --- no-data states ----------------------------------------------------------------


def test_no_rows_is_the_no_data_state_at_one_row_of_panels() -> None:
    text = _render_case(_case("empty"))
    assert ">No data<" in text
    assert "No data: no rows." in _desc(text)
    assert _height(text) == _height(_plain(3))
    sized = _render((DAY, KM, SHOE), [], CHANNELS, {"height": 300})
    assert _height(sized) == 300


def test_rows_without_a_drawable_value_are_the_no_data_state() -> None:
    text = _render_case(_case("all_absent"))
    assert ">No data<" in text
    assert "None of the 2 rows has a value to draw." in text
    assert "none of the 2 rows has a value to draw" in _desc(text)


# --- text bounds -----------------------------------------------------------------


def _absolute_texts(
    element: ET.Element, dx: float = 0.0, dy: float = 0.0
) -> list[tuple[ET.Element, float, float]]:
    """Every text with its absolute x and y, through the panels' translations."""
    found: list[tuple[ET.Element, float, float]] = []
    for child in element:
        origin = _translate(child)
        ox, oy = (dx + origin[0], dy + origin[1]) if origin else (dx, dy)
        if child.tag == f"{SVG}text":
            found.append(
                (
                    child,
                    dx + float(child.get("x") or "nan"),
                    dy + float(child.get("y") or "nan"),
                )
            )
        else:
            found.extend(_absolute_texts(child, ox, oy))
    return found


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.name)
def test_every_text_stays_inside_the_chart(case: Case) -> None:
    text = _render_case(case)
    root = _root(text)
    width = float(root.get("width") or "nan")
    found = _absolute_texts(root)
    assert len(found) == text.count("<text") > 0  # no text escaped the walk
    for element, x, _ in found:
        reach = text_width(element.text or "", float(element.get("font-size") or "nan"))
        anchor = element.get("text-anchor")
        left = (
            x - reach / 2 if anchor == "middle" else x - reach if anchor == "end" else x
        )
        assert left >= 8.0 - 1e-6, element.text
        assert left + reach <= width - 4.0 + 1e-6, element.text


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.name)
def test_every_panel_text_stays_inside_its_panel(case: Case) -> None:
    """Panel-local text keeps 8 px on the left and 4 px on the right of its cell."""
    text = _render_case(case)
    cell = _stride(text) or _outer_plot_width(text)
    for panel in _panels(text):
        for element in _texts(panel):
            x = float(element.get("x") or "nan")
            reach = text_width(
                element.text or "", float(element.get("font-size") or "nan")
            )
            anchor = element.get("text-anchor")
            left = (
                x - reach / 2
                if anchor == "middle"
                else x - reach
                if anchor == "end"
                else x
            )
            assert left >= 8.0 - 1e-6, element.text
            assert left + reach <= cell - 4.0 + 1e-6, element.text


# --- fixtures and goldens ----------------------------------------------------------


def test_typical_fixture_has_the_distinguishing_values() -> None:
    first = [str(s) for s in dict.fromkeys(r[2] for r in TYPICAL_ROWS)]
    assert first != sorted(first)
    for shoe in first:
        days = [r[0] for r in TYPICAL_ROWS if r[2] == shoe and r[0] is not None]
        assert days != sorted(days, key=str) or shoe == "Alphafly"
    assert any(r[1] is None for r in TYPICAL_ROWS)
    assert any(r[1] == 0.0 for r in TYPICAL_ROWS)
    assert any(r[0] is None for r in TYPICAL_ROWS)
    per_panel_max = {
        shoe: max(
            (r[1] for r in TYPICAL_ROWS if r[2] == shoe and isinstance(r[1], float)),
            default=0.0,
        )
        for shoe in first
    }
    assert len(set(per_panel_max.values())) == 4


def test_cases_are_the_designed_names() -> None:
    assert [case.name for case in CASES] == [
        "typical",
        "empty",
        "all_absent",
        "single",
        "negative",
        "independent",
        "empty_panel",
        "long_labels",
        "at_bound",
    ]
    assert CASES[0].name == "typical"


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.name)
def test_golden(case: Case) -> None:
    rendered = render_case(KIND, case.request, case.data)
    assert rendered.kind == "small-multiples"
    assert rendered.output is Output.SVG
    assert_golden(golden_path("small-multiples", case.name, "svg"), rendered.text)


def test_no_stale_goldens() -> None:
    directory = golden_path("small-multiples", "x", "svg").parent
    on_disk = sorted(path.name for path in directory.iterdir())
    assert on_disk == sorted(f"{case.name}.svg" for case in CASES)


def test_typical_is_four_facets_in_three_columns_and_two_rows() -> None:
    case = _case("typical")
    assert case.request.options == {}
    text = _render_case(case)
    assert _root(text).get("width") == "720"
    origins = [_origin(p) for p in _panels(text)]
    assert len({o[0] for o in origins}) == 3
    assert len({o[1] for o in origins}) == 2


def test_long_labels_golden_is_shortened() -> None:
    text = _render_case(_case("long_labels"))
    assert text.count("…") >= 3
    assert any("…" in title for title in _titles(text))


def test_at_bound_golden_is_at_the_bound() -> None:
    case = _case("at_bound")
    assert len(_panels(_render_case(case))) == PANEL_LIMIT == KIND.bound.limit


def test_single_golden_is_one_dot() -> None:
    text = _render_case(_case("single"))
    (panel,) = _panels(text)
    (mark,) = _mark_children(panel)
    assert mark.tag == f"{SVG}path" and mark.get("stroke-width") == "5"


def test_negative_golden_reaches_below_zero() -> None:
    text = _render_case(_case("negative"))
    assert any(label.startswith("-") for p in _panels(text) for label in _y_labels(p))


def test_empty_panel_golden_has_one_empty_panel() -> None:
    assert _render_case(_case("empty_panel")).count(">No values<") == 1


def main() -> None:
    for case in CASES:
        write_golden(
            golden_path("small-multiples", case.name, "svg"), _render_case(case)
        )


if __name__ == "__main__":
    main()
