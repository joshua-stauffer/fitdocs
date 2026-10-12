"""The ``hbar`` kind: ranking, geometry, labels, height, refusals and goldens.

Regenerate the goldens with ``uv run python -m tests.render.charts.kit.test_hbar``.
"""

from __future__ import annotations

import dataclasses
import xml.etree.ElementTree as ET
from collections.abc import Sequence
from datetime import date, timedelta

import pytest

from fitdocs.render.charts.kit.data import ChartData, Column, Value, ValueKind
from fitdocs.render.charts.kit.kinds.hbar import KIND
from fitdocs.render.charts.kit.problems import ProblemCode
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

SVG = "{http://www.w3.org/2000/svg}"

X = column("distance_km", unit="km")
Y = column("sport", ValueKind.CATEGORY)
CHANNELS = {"y": "sport", "x": "distance_km"}

# title (21) .. y-axis title row (down to 48) above the plot, then below it the
# tick labels (19), the x-axis title (16) and the bottom pad (8): 91 px that
# are not rows.
FRAME = 91
ROW = 26
BAR = 16
GAP = 4  # value label after the bar end

# (x, y): not ranked; Zebra and Alpha tie (Zebra is first in the rows, Alpha
# first alphabetically); an absent x, a zero, and two rows whose y is absent
# (one of them with the second-largest x).
TYPICAL_ROWS: list[tuple[Value, Value]] = [
    (8.0, "Zebra"),
    (21.1, "Easy"),
    (None, "Pending"),
    (8.0, "Alpha"),
    (0.0, "Rest"),
    (14.2, None),
    (3.3, "Long"),
    (None, None),
]


def _request() -> ChartRequest:
    return chart_request("hbar", title="Title", channels=CHANNELS)


def _data(
    rows: Sequence[tuple[Value, Value]],
    *,
    x: Column = X,
    y: Column = Y,
) -> ChartData:
    return chart_data([x, y], rows)


def _svg(
    rows: Sequence[tuple[Value, Value]],
    *,
    sort: str | None = None,
    height: int | None = None,
    x: Column = X,
    y: Column = Y,
    title: str = "Title",
) -> str:
    request = chart_request(
        "hbar",
        title=title,
        channels={"y": y.name, "x": x.name},
        options=({} if sort is None else {"sort": sort})
        | ({} if height is None else {"height": height}),
    )
    return render_case(KIND, request, _data(rows, x=x, y=y)).text


def _root(svg: str) -> ET.Element:
    return ET.fromstring(svg)


def _groups(root: ET.Element, css_class: str) -> list[ET.Element]:
    return [g for g in root.iter(f"{SVG}g") if g.get("class") == css_class]


def _row_labels(svg: str) -> list[str]:
    """The left axis tick labels, top to bottom."""
    root = _root(svg)
    return [
        t.text or ""
        for g in _groups(root, "ck-axis")
        for t in g.iter(f"{SVG}text")
        if t.get("text-anchor") == "end"
    ]


def _value_labels(svg: str) -> list[str]:
    root = _root(svg)
    (group,) = _groups(root, "ck-values")
    return [t.text or "" for t in group.iter(f"{SVG}text")]


def _value_label_xs(svg: str) -> list[float]:
    root = _root(svg)
    (group,) = _groups(root, "ck-values")
    return [float(t.get("x") or "nan") for t in group.iter(f"{SVG}text")]


def _bars(svg: str) -> list[dict[str, float]]:
    root = _root(svg)
    (group,) = _groups(root, "ck-marks")
    return [
        {k: float(r.get(k) or "nan") for k in ("x", "y", "width", "height")}
        for r in group.iter(f"{SVG}rect")
    ]


def _plot_left(svg: str) -> float:
    root = _root(svg)
    for g in _groups(root, "ck-axis"):
        if any(t.get("text-anchor") == "end" for t in g.iter(f"{SVG}text")):
            line = next(iter(g.iter(f"{SVG}line")))
            return float(line.get("x1") or "nan")
    raise AssertionError("no left axis")


def _height(svg: str) -> int:
    return int(_root(svg).get("height") or "0")


def _desc(svg: str) -> str:
    desc = _root(svg).find(f"{SVG}desc")
    assert desc is not None
    return desc.text or ""


# Declaration --------------------------------------------------------------


def test_declaration() -> None:
    assert KIND.name == "hbar"
    assert KIND.description == "Horizontal bars, one per row, ranked by value"
    assert KIND.output is Output.SVG
    assert KIND.channels == (
        ChannelSpec(
            "y",
            (ValueKind.CATEGORY, ValueKind.DATE, ValueKind.BOOLEAN),
            True,
            "The label of each bar.",
        ),
        ChannelSpec(
            "x",
            (ValueKind.NUMBER, ValueKind.DURATION),
            True,
            "The length of each bar.",
        ),
    )
    assert KIND.options == (
        OptionSpec(
            "sort",
            OptionType.CHOICE,
            "Rank the bars by value, or keep the row order.",
            "value",
            choices=("value", "rows"),
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
        50, "rows", OverBound.REFUSE, "At most 50 rows; more are refused."
    )
    assert KIND.max_series is None
    assert KIND.uses_all_columns is False
    assert [f.name for f in dataclasses.fields(KIND)][:3] == [
        "name",
        "description",
        "output",
    ]


# Ranking ------------------------------------------------------------------


def test_ranking_is_value_descending_ties_in_row_order_absent_last() -> None:
    svg = _svg(TYPICAL_ROWS)
    # Zebra precedes Alpha: the tie keeps row order, not label order.
    assert _row_labels(svg) == [
        "Easy",
        "Zebra",
        "Alpha",
        "Long",
        "Rest",
        "Pending",
        "—",
        "—",
    ]
    # The absent value (Pending) is last among the rows that have a y; the two
    # rows whose y is absent follow it, the 14.2 one first (rows order).
    assert _value_labels(svg) == [
        "21.1",
        "8.0",
        "8.0",
        "3.3",
        "0.0",
        "—",
        "14.2",
        "—",
    ]


def test_default_sort_is_value() -> None:
    assert _svg(TYPICAL_ROWS) == _svg(TYPICAL_ROWS, sort="value")
    assert _svg(TYPICAL_ROWS) != _svg(TYPICAL_ROWS, sort="rows")


def test_sort_rows_keeps_row_order_with_absent_y_last() -> None:
    svg = _svg(TYPICAL_ROWS, sort="rows")
    assert _row_labels(svg) == [
        "Zebra",
        "Easy",
        "Pending",
        "Alpha",
        "Rest",
        "Long",
        "—",
        "—",
    ]
    assert _value_labels(svg) == [
        "8.0",
        "21.1",
        "—",
        "8.0",
        "0.0",
        "3.3",
        "14.2",
        "—",
    ]


def test_dates_on_y_follow_the_ranking_not_the_calendar() -> None:
    rows: list[tuple[Value, Value]] = [
        (5.0, date(2026, 3, 9)),
        (9.0, date(2026, 3, 2)),
        (7.0, date(2026, 3, 16)),
    ]
    date_y = column("week", ValueKind.DATE)
    # 5.0 / 9.0 / 7.0 and 03-09 / 03-02 / 03-16 are in neither order.
    ranked = _svg(rows, y=date_y)
    assert _row_labels(ranked) == ["2026-03-02", "2026-03-16", "2026-03-09"]
    kept = _svg(rows, y=date_y, sort="rows")
    assert _row_labels(kept) == ["2026-03-09", "2026-03-02", "2026-03-16"]


def test_durations_rank_by_seconds_and_label_without_unit() -> None:
    rows: list[tuple[Value, Value]] = [
        (timedelta(seconds=605), "Short"),
        (timedelta(seconds=3725), "Long"),
    ]
    svg = _svg(rows, x=column("time", ValueKind.DURATION))
    assert _row_labels(svg) == ["Long", "Short"]
    assert _value_labels(svg) == ["1:02:05", "10:05"]


def test_every_row_is_labelled_even_where_rows_are_narrow() -> None:
    # 4-character labels are wider than a 26 px row less its margin, so a band
    # scale's own thinning would drop every other label.
    rows: list[tuple[Value, Value]] = [(float(i + 1), f"R{i:02d}x") for i in range(50)]
    svg = _svg(rows, sort="rows")
    assert _row_labels(svg) == [f"R{i:02d}x" for i in range(50)]


# Bars ---------------------------------------------------------------------


def test_bar_lengths_are_proportional_from_zero_and_rows_sit_26_px_apart() -> None:
    bars = _bars(_svg(TYPICAL_ROWS))
    # Easy, Zebra, Alpha, Long, Rest (zero stub), then the y-absent 14.2 row;
    # Pending (absent x) and the all-absent row draw no bar.
    assert len(bars) == 6
    zebra = bars[1]["width"]
    assert bars[0]["width"] / zebra == pytest.approx(21.1 / 8.0, rel=1e-3)
    assert bars[2]["width"] == zebra
    assert bars[3]["width"] / zebra == pytest.approx(3.3 / 8.0, rel=1e-3)
    assert bars[5]["width"] / zebra == pytest.approx(14.2 / 8.0, rel=1e-3)
    zero = bars[0]["x"]
    assert [b["x"] for b in bars[:4] + bars[5:]] == [zero] * 5
    assert [b["height"] for b in bars] == [BAR] * 6
    ys = [b["y"] for b in bars]
    assert [round(b - a, 6) for a, b in zip(ys, ys[1:], strict=False)] == [
        ROW,
        ROW,
        ROW,
        ROW,
        2 * ROW,
    ]


def test_x_includes_zero_even_when_every_value_is_large() -> None:
    rows: list[tuple[Value, Value]] = [(90.0, "A"), (45.0, "B")]
    svg = _svg(rows)
    first, second = _bars(svg)
    assert first["width"] / second["width"] == pytest.approx(2.0, rel=1e-3)
    # The zero line is the left end of the axis: the domain starts at 0, not at
    # the smallest value.
    assert first["x"] == _plot_left(svg)


def test_zero_is_a_two_pixel_stub_centred_on_the_zero_line_and_absent_is_nothing() -> (
    None
):
    bars = _bars(_svg(TYPICAL_ROWS))
    stub = bars[4]
    zero = bars[0]["x"]
    assert stub == {"x": zero - 1.0, "y": stub["y"], "width": 2.0, "height": BAR}
    # Rest is the fifth row and 0.0 its label; Pending (sixth row) has no bar.
    assert bars[5]["y"] - stub["y"] == 2 * ROW


def test_bars_are_the_first_series_colour() -> None:
    root = _root(_svg(TYPICAL_ROWS))
    (group,) = _groups(root, "ck-marks")
    fills = {r.get("fill") for r in group.iter(f"{SVG}rect")}
    assert fills == {series_style(0).color}


def test_negative_values_extend_left_of_zero() -> None:
    rows: list[tuple[Value, Value]] = [
        (-5.5, "Down"),
        (12.0, "Up"),
        (-2.5, "Mild"),
        (0.0, "Flat"),
    ]
    svg = _svg(rows)
    assert _row_labels(svg) == ["Up", "Flat", "Mild", "Down"]
    up, flat, mild, down = _bars(svg)
    zero = up["x"]
    assert flat["x"] == zero - 1.0
    assert mild["x"] + mild["width"] == pytest.approx(zero, abs=0.01)
    assert down["x"] + down["width"] == pytest.approx(zero, abs=0.01)
    assert down["x"] < mild["x"] < zero
    assert mild["width"] / up["width"] == pytest.approx(2.5 / 12.0, rel=1e-2)
    assert down["width"] / up["width"] == pytest.approx(5.5 / 12.0, rel=1e-2)
    assert _value_labels(svg) == ["12.0", "0.0", "-2.5", "-5.5"]


# Value labels ---------------------------------------------------------------


def test_value_labels_follow_the_bar_end_and_negatives_sit_beside_zero() -> None:
    svg = _svg([(-5.5, "Down"), (12.0, "Up"), (0.0, "Flat")])
    up, flat, down = _bars(svg)
    zero = up["x"]
    xs = _value_label_xs(svg)
    assert xs[0] == pytest.approx(zero + up["width"] + GAP, abs=0.01)
    assert xs[1] == pytest.approx(zero + GAP, abs=0.01)
    assert xs[2] == pytest.approx(zero + GAP, abs=0.01)
    assert down["x"] < zero


def test_value_labels_carry_no_unit() -> None:
    labels = _value_labels(_svg(TYPICAL_ROWS))
    assert not any("km" in label for label in labels)


def test_value_labels_stay_inside_the_chart() -> None:
    for rows in (
        TYPICAL_ROWS,
        [(-5.5, "Down"), (12.0, "Up"), (-2.5, "Mild")],
        [(-5.5, "Down"), (-2.5, "Mild")],
    ):
        svg = _svg(rows)
        for x, label in zip(_value_label_xs(svg), _value_labels(svg), strict=True):
            assert x + len(label) * 11 * 0.64 <= 720 - 8


# Height ---------------------------------------------------------------------


def test_auto_height_is_26_px_per_row_plus_the_frame() -> None:
    rows = [(float(i + 1), f"R{i}") for i in range(6)]
    assert _height(_svg(rows)) == 6 * ROW + FRAME
    assert _height(_svg(rows[:5])) == 5 * ROW + FRAME
    assert _height(_svg(rows[:3])) == 3 * ROW + FRAME
    root = _root(_svg(rows))
    assert root.get("viewBox") == f"0 0 720 {6 * ROW + FRAME}"
    ys = [b["y"] for b in _bars(_svg(rows))]
    assert [b - a for a, b in zip(ys, ys[1:], strict=False)] == [ROW] * 5


def test_auto_height_has_a_minimum_of_160() -> None:
    assert _height(_svg([(12.5, "Only")])) == 160
    assert _height(_svg([(1.0, "A"), (2.0, "B")])) == 160
    assert 2 * ROW + FRAME < 160 < 3 * ROW + FRAME


def test_a_roomy_row_still_draws_a_16_px_bar() -> None:
    (bar,) = _bars(_svg([(12.5, "Only")]))
    assert bar["height"] == BAR


def test_an_explicit_height_is_used_as_given() -> None:
    rows = [(1.0, "A"), (2.0, "B"), (3.0, "C"), (4.0, "D")]
    svg = _svg(rows, height=400)
    assert _height(svg) == 400
    bars = _bars(svg)
    assert [b["height"] for b in bars] == [BAR] * 4


def test_a_cramped_explicit_height_never_overlaps_bars() -> None:
    rows = [(float(i + 1), f"R{i:02d}") for i in range(50)]
    bars = _bars(_svg(rows, height=300))
    ys = sorted(b["y"] for b in bars)
    pitch = min(b - a for a, b in zip(ys, ys[1:], strict=False))
    assert bars[0]["height"] < BAR
    assert bars[0]["height"] <= pitch


# Left margin ----------------------------------------------------------------


def test_left_margin_fits_the_widest_label() -> None:
    # "Pending" is the widest label: 7 characters at 11 px * 0.64.
    expected = 8 + 7 * 11 * 0.64 + 3 + 5
    assert _plot_left(_svg(TYPICAL_ROWS)) == pytest.approx(expected, abs=0.01)


def test_left_margin_stops_at_40_percent_and_long_labels_are_shortened() -> None:
    long_label = "Sunday long run along the river path to the lighthouse and back"
    svg = _svg([(10.0, long_label), (5.0, "Short")])
    assert _plot_left(svg) == pytest.approx(0.4 * 720, abs=0.01)
    labels = _row_labels(svg)
    assert labels[0].endswith("…") and long_label.startswith(labels[0][:-1])
    assert labels[1] == "Short"


def test_left_margin_follows_the_chart_width() -> None:
    long_label = "Sunday long run along the river path to the lighthouse and back"
    request = chart_request(
        "hbar", channels=CHANNELS, options={"width": 400}, title="T"
    )
    svg = render_case(KIND, request, _data([(10.0, long_label)])).text
    assert _plot_left(svg) == pytest.approx(0.4 * 400, abs=0.01)


# Description and no data ---------------------------------------------------


def test_description_names_channels_rows_and_the_x_range() -> None:
    svg = _svg([(8.0, "Zebra"), (21.1, "Easy"), (3.3, "Long")])
    assert _desc(svg) == (
        "Hbar chart: Title. y: sport; x: distance (km). 3 rows. "
        "distance (km) from 3.3 km to 21.1 km."
    )


def test_no_rows_is_the_no_data_state_at_the_minimum_height() -> None:
    svg = _svg([])
    assert _height(svg) == 160
    assert _desc(svg) == "Hbar chart: Title. No data: no rows."
    assert _height(_svg([], height=300)) == 300


def test_rows_without_a_bar_length_are_the_no_data_state() -> None:
    rows: list[tuple[Value, Value]] = [(None, "A"), (None, "B"), (None, None)]
    svg = _svg(rows)
    assert _height(svg) == 160
    assert _desc(svg) == (
        "Hbar chart: Title. No data: none of the 3 rows has a value to draw."
    )
    assert _height(_svg(rows, height=300)) == 300


# Refusals -------------------------------------------------------------------


def test_duplicate_y_is_refused_whatever_the_bar_lengths() -> None:
    rows: list[tuple[Value, Value]] = [(1.0, "A"), (2.0, "B"), (3.0, "A")]
    (problem,) = problems_of(KIND, _request(), _data(rows))
    assert problem.code is ProblemCode.DUPLICATE_POSITION
    assert problem.row == 2
    assert problem.message == "Row 2 repeats row 0, which has the same sport (A)."


def test_rows_whose_y_is_absent_never_repeat_each_other() -> None:
    rows: list[tuple[Value, Value]] = [(1.0, None), (2.0, None), (3.0, "A")]
    svg = _svg(rows)
    assert _row_labels(svg) == ["A", "—", "—"]


def test_fifty_rows_render_and_fifty_one_refuse() -> None:
    rows = [(float(i + 1), f"r{i:02d}") for i in range(50)]
    assert len(_bars(_svg(rows))) == 50
    (problem,) = problems_of(
        KIND,
        _request(),
        _data([*rows, (51.0, "r50")]),
    )
    assert problem.code is ProblemCode.OVER_BOUND
    assert problem.rows == 51
    assert problem.message == "hbar draws at most 50 rows; this data has 51."


# Goldens --------------------------------------------------------------------

LONG_LABELS: list[tuple[Value, Value]] = [
    (14.0, "Sunday long run along the river path to the lighthouse and back"),
    (22.5, "Hill repeats on the steep road behind the old quarry, six by two minutes"),
    (6.0, "Easy"),
]


def _case(
    name: str,
    rows: Sequence[tuple[Value, Value]],
    *,
    sort: str | None = None,
) -> Case:
    options: dict[str, OptionValue] = {} if sort is None else {"sort": sort}
    return Case(
        name,
        chart_request(
            "hbar", title="Distance by run", channels=CHANNELS, options=options
        ),
        _data(rows),
    )


CASES: tuple[Case, ...] = (
    _case("typical", TYPICAL_ROWS),
    _case("empty", []),
    _case("all_absent", [(None, "Easy"), (None, "Tempo"), (None, None)]),
    _case("single", [(12.5, "Tempo")]),
    _case(
        "negative",
        [(-5.5, "Down"), (12.0, "Up"), (-2.5, "Mild"), (0.0, "Flat"), (3.5, "Lift")],
    ),
    _case("long_labels", LONG_LABELS),
    _case(
        "at_bound",
        [(float((i * 7) % 50 + 1), f"Run {i + 1:02d}") for i in range(50)],
    ),
    _case("rows", TYPICAL_ROWS, sort="rows"),
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
        "rows",
    ]


def test_golden_preconditions_hold() -> None:
    by_name = {case.name: case for case in CASES}
    assert (
        "…"
        in render_case(
            KIND, by_name["long_labels"].request, by_name["long_labels"].data
        ).text
    )
    at_bound = by_name["at_bound"]
    assert len(at_bound.data.rows) == KIND.bound.limit
    assert len({row[0] for row in at_bound.data.rows}) == KIND.bound.limit
    assert any(row[0] is None for row in by_name["typical"].data.rows)
    assert any(row[1] is None for row in by_name["typical"].data.rows)
    assert any(row[0] == 0.0 for row in by_name["typical"].data.rows)
    assert any(
        isinstance(row[0], float) and row[0] < 0
        for row in by_name["negative"].data.rows
    )


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.name)
def test_golden(case: Case) -> None:
    rendered = render_case(KIND, case.request, case.data)
    assert rendered.kind == "hbar"
    assert rendered.output is Output.SVG
    assert_golden(golden_path("hbar", case.name, "svg"), rendered.text)


def _extents(svg: str) -> list[tuple[str, float, float]]:
    out: list[tuple[str, float, float]] = []
    for t in _root(svg).iter(f"{SVG}text"):
        content = t.text or ""
        size = float(t.get("font-size") or "nan")
        w = len(content) * size * 0.64
        x = float(t.get("x") or "nan")
        anchor = t.get("text-anchor")
        left = x - w if anchor == "end" else x - w / 2 if anchor == "middle" else x
        out.append((content, left, left + w))
    return out


HOURS_CASE = Case(
    "hours",
    chart_request(
        "hbar", title="T", channels={"y": "s", "x": "t"}, options={"width": 320}
    ),
    chart_data(
        [column("t", ValueKind.DURATION), column("s", ValueKind.CATEGORY)],
        [(timedelta(seconds=14400), "A"), (timedelta(seconds=7200), "B")],
    ),
)


@pytest.mark.parametrize("case", (*CASES, HOURS_CASE), ids=lambda case: case.name)
def test_every_text_stays_inside_the_chart(case: Case) -> None:
    svg = render_case(KIND, case.request, case.data).text
    width = float(_root(svg).get("width") or "nan")
    texts = _extents(svg)
    assert texts
    for content, left, right in texts:
        assert left >= 8.0 - 1e-6, content
        assert right <= width - 4.0, content


def test_the_hours_case_needs_the_left_overhang_reserve() -> None:
    svg = render_case(KIND, HOURS_CASE.request, HOURS_CASE.data).text
    assert any(c == "0:00:00" for c, _, _ in _extents(svg))
    # One-character row labels alone would put the plot edge at 8 + 7 + 8.
    assert _plot_left(svg) > 8 + 11 * 0.64 + 8


def test_the_hours_case_needs_the_right_overhang_reserve() -> None:
    svg = render_case(KIND, HOURS_CASE.request, HOURS_CASE.data).text
    root = _root(svg)
    baseline = next(
        next(iter(g.iter(f"{SVG}line")))
        for g in _groups(root, "ck-axis")
        if any(t.get("text-anchor") == "middle" for t in g.iter(f"{SVG}text"))
    )
    # width 320 less the margin: half of the 7-character last tick label (24.64)
    # plus 4, then the widest value label (49.28) plus its 4 px gap.
    assert float(baseline.get("x2") or "nan") == pytest.approx(238.08, abs=0.01)


def test_the_title_is_drawn_last() -> None:
    root = _root(render_case(KIND, CASES[0].request, CASES[0].data).text)
    last = list(root)[-1]
    assert last.tag == f"{SVG}text" and last.text == "Distance by run"


def test_description_ranges_are_named_by_axis_title() -> None:
    svg = _svg(
        [(timedelta(seconds=605), "Short"), (timedelta(seconds=3725), "Long")],
        x=column("time", ValueKind.DURATION),
    )
    assert _desc(svg).endswith("time (h:mm:ss) from 0:10:05 to 1:02:05.")
    short = _svg(
        [(timedelta(seconds=2700), "A"), (timedelta(seconds=1500), "B")],
        x=column("time", ValueKind.DURATION),
    )
    assert _desc(short).endswith("time (m:ss) from 25:00 to 45:00.")
    mixed = _svg(
        [(timedelta(seconds=300), "A"), (timedelta(seconds=3500), "B")],
        x=column("time", ValueKind.DURATION),
    )
    assert _desc(mixed).endswith("time (h:mm:ss) from 0:05:00 to 0:58:20.")
    numeric = _svg([(100, "A"), (4000, "B")], x=column("t_s", unit="s"))
    assert _desc(numeric).endswith("t (h:mm:ss) from 0:01:40 to 1:06:40.")
    numeric_short = _svg([(1500, "A"), (2700, "B")], x=column("t_s", unit="s"))
    assert _desc(numeric_short).endswith("t (m:ss) from 25:00 to 45:00.")
    pace = _svg([(245.0, "A"), (330.0, "B")], x=column("p_s_per_km", unit="s_per_km"))
    assert _desc(pace).endswith("p (min/km) from 4:05 /km to 5:30 /km.")


def test_no_stale_goldens() -> None:
    directory = golden_path("hbar", "x", "svg").parent
    on_disk = sorted(path.name for path in directory.iterdir())
    assert on_disk == sorted(f"{case.name}.svg" for case in CASES)


def main() -> None:
    for case in CASES:
        text = render_case(KIND, case.request, case.data).text
        write_golden(golden_path("hbar", case.name, "svg"), text)


if __name__ == "__main__":
    main()
