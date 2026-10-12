"""The ``band`` kind: declaration, refusals, ordering, breaks, legend and goldens.

Requirements 2.2, 2.3, 2.4, 2.5, 2.6, 2.8, 2.9, 2.10, 7.1-7.7, 12.1, 12.3.

Run ``uv run python -m tests.render.charts.kit.test_band`` to (re)write the
goldens under ``golden/band/``; a pytest run never writes them.
"""

from __future__ import annotations

import dataclasses
import re
import xml.etree.ElementTree as ET
from collections.abc import Mapping, Sequence
from datetime import date, timedelta

import pytest

from fitdocs.render.charts.kit.data import ChartData, Column, Value, ValueKind
from fitdocs.render.charts.kit.kinds.band import KIND
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

SVG = "{http://www.w3.org/2000/svg}"
D = date

WEEK = column("week", ValueKind.DATE)
P10 = column("hr_p10_bpm", unit="bpm")
P50 = column("hr_p50_bpm", unit="bpm")
P90 = column("hr_p90_bpm", unit="bpm")
CHANNELS = {"x": "week", "low": "hr_p10_bpm", "high": "hr_p90_bpm", "mid": "hr_p50_bpm"}
CHANNELS_NO_MID = {"x": "week", "low": "hr_p10_bpm", "high": "hr_p90_bpm"}

X = column("x")
LOW = column("low_m", unit="m")
HIGH = column("high_m", unit="m")
MID = column("mid_m", unit="m")
NUM_CHANNELS = {"x": "x", "low": "low_m", "high": "high_m", "mid": "mid_m"}
NUM_COLUMNS = (X, LOW, HIGH, MID)


def _request(
    channels: Mapping[str, str] = CHANNELS,
    options: Mapping[str, OptionValue] | None = None,
    title: str = "Heart rate spread",
) -> ChartRequest:
    return chart_request(
        "band", ref="b1", title=title, channels=channels, options=options
    )


def _render(
    columns: Sequence[Column],
    rows: Sequence[Sequence[Value]],
    channels: Mapping[str, str] = NUM_CHANNELS,
    options: Mapping[str, OptionValue] | None = None,
) -> str:
    return render_case(
        KIND, _request(channels, options), chart_data(columns, rows)
    ).text


def _refusal(
    columns: Sequence[Column],
    rows: Sequence[Sequence[Value]],
    channels: Mapping[str, str] = NUM_CHANNELS,
) -> tuple[ChartProblem, ...]:
    return problems_of(KIND, _request(channels), chart_data(columns, rows))


# --- the golden fixtures ----------------------------------------------------------

# Weeks arrive out of date order. Row 3 (Mar 23) has no low but a median, so the
# band breaks and the centre line carries on; row 7 (Apr 6) has no median, so
# only the centre line breaks; row 5 has no week; row 8 (Apr 20) holds a low and
# nothing else, so it leaves no mark and counts under high and mid.
# Every value is distinct.
TYPICAL_ROWS: tuple[tuple[Value, ...], ...] = (
    (D(2026, 3, 16), 128.0, 141.5, 158.0),
    (D(2026, 3, 2), 131.0, 144.0, 161.5),
    (D(2026, 3, 30), 126.5, 139.0, 155.5),
    (D(2026, 3, 23), None, 143.5, 163.0),
    (D(2026, 3, 9), 129.5, 142.0, 159.5),
    (None, 127.0, 140.5, 157.0),
    (D(2026, 4, 13), 130.5, 146.5, 165.0),
    (D(2026, 4, 6), 124.5, None, 154.0),
    (D(2026, 4, 20), 133.0, None, None),
)
TYPICAL_COLUMNS = (WEEK, P10, P90, P50)


def _typical_data(
    rows: Sequence[Sequence[Value]] = TYPICAL_ROWS,
) -> ChartData:
    # Column order differs from the channel order on purpose.
    return chart_data(TYPICAL_COLUMNS, [(r[0], r[1], r[3], r[2]) for r in rows])


ABSENT_ROWS: tuple[tuple[Value, ...], ...] = (
    (D(2026, 5, 2), None, None, 140.0),
    (None, 124.0, 150.0, 137.0),
    (D(2026, 5, 9), 120.0, None, None),
    (D(2026, 5, 16), None, 151.0, None),
    (None, None, None, None),
)
# Row 0 has an x and a centre, so ABSENT_ROWS alone is not "all absent": the
# all-absent case drops the centre channel.

# x = 1..9, out of order. Positions 1-3 and 8-9 are band runs; 5 is a band
# position between two breaks (a vertical line, no centre); 4 and 6 hold one
# edge and no centre, so they mark nothing; 7 holds a centre value alone (a dot).
ISOLATED_ROWS: tuple[tuple[Value, ...], ...] = (
    (8.0, 4.5, 8.5, None),
    (3.0, 2.5, 7.0, 5.0),
    (5.0, 3.0, 9.0, None),
    (1.0, 2.0, 6.5, 4.25),
    (4.0, None, 7.5, None),
    (9.0, 5.5, 10.0, None),
    (6.0, 3.5, None, None),
    (2.0, 1.5, 7.25, 4.0),
    (7.0, None, None, 6.75),
)

NEGATIVE_ROWS: tuple[tuple[Value, ...], ...] = (
    (3.0, -4.5, 2.0, -1.25),
    (1.0, -6.0, 1.5, -2.5),
    (4.0, -3.0, 4.75, 0.5),
    (2.0, -5.25, 0.25, -2.0),
    (5.0, -2.5, 5.0, 1.75),
)

LONG_X = column(
    "elapsed_time", ValueKind.DURATION, label="Elapsed time since the start of the day"
)
LONG_LOW = column(
    "pace_p10_s",
    ValueKind.DURATION,
    label="Fastest tenth of every kilometre split recorded during the entire year",
)
LONG_HIGH = column(
    "pace_p90_s",
    ValueKind.DURATION,
    label="Slowest tenth of every kilometre split recorded during the entire year",
)
LONG_MID = column(
    "pace_p50_s",
    ValueKind.DURATION,
    label="Typical middle split recorded across all of the long training runs",
)
LONG_ROWS: tuple[tuple[Value, ...], ...] = (
    (
        timedelta(minutes=50),
        timedelta(seconds=250),
        timedelta(seconds=330),
        timedelta(seconds=290),
    ),
    (
        timedelta(minutes=10),
        timedelta(seconds=240),
        timedelta(seconds=345),
        timedelta(seconds=300),
    ),
    (
        timedelta(minutes=30),
        timedelta(seconds=255),
        timedelta(seconds=335),
        timedelta(seconds=285),
    ),
    (
        timedelta(minutes=70),
        timedelta(seconds=262),
        timedelta(seconds=318),
        timedelta(seconds=280),
    ),
)
LONG_TITLE = (
    "A deliberately long chart title that cannot possibly fit within the width of"
    " the chart however small its type"
)

LIMIT = 1000


def _at_bound_rows(count: int) -> tuple[tuple[Value, ...], ...]:
    rows: list[tuple[Value, ...]] = []
    for i in range(count):
        base = float((i * 37) % 211) + i / 1000
        rows.append((float(i), base, base + 20.0 + (i % 7), base + 9.0))
    return tuple(rows)


CASES: tuple[Case, ...] = (
    Case("typical", _request(), _typical_data()),
    Case("empty", _request(), chart_data(TYPICAL_COLUMNS, [])),
    Case(
        "all_absent",
        _request(CHANNELS_NO_MID),
        chart_data(
            (WEEK, P10, P90),
            [(r[0], r[1], r[2]) for r in ABSENT_ROWS],
        ),
    ),
    Case(
        "single",
        _request(NUM_CHANNELS),
        chart_data(NUM_COLUMNS, [(4.0, 7.5, 7.5, 7.5)]),
    ),
    Case("negative", _request(NUM_CHANNELS), chart_data(NUM_COLUMNS, NEGATIVE_ROWS)),
    Case(
        "no_mid",
        _request(CHANNELS_NO_MID),
        chart_data((WEEK, P10, P90), [(r[0], r[1], r[3]) for r in TYPICAL_ROWS]),
    ),
    Case("isolated", _request(NUM_CHANNELS), chart_data(NUM_COLUMNS, ISOLATED_ROWS)),
    Case(
        "long_labels",
        _request(
            {
                "x": "elapsed_time",
                "low": "pace_p10_s",
                "high": "pace_p90_s",
                "mid": "pace_p50_s",
            },
            title=LONG_TITLE,
        ),
        chart_data((LONG_X, LONG_LOW, LONG_HIGH, LONG_MID), LONG_ROWS),
    ),
    Case(
        "at_bound",
        _request(NUM_CHANNELS, title="Every sample"),
        chart_data(NUM_COLUMNS, _at_bound_rows(LIMIT)),
    ),
)


def _case(name: str) -> Case:
    return next(case for case in CASES if case.name == name)


def _render_case(case: Case) -> str:
    return render_case(KIND, case.request, case.data).text


# --- parsing helpers --------------------------------------------------------------


def _root(text: str) -> ET.Element:
    return ET.fromstring(text)


def _group(text: str, css_class: str) -> list[ET.Element]:
    return [g for g in _root(text).iter(f"{SVG}g") if g.get("class") == css_class]


def _marks(text: str) -> list[ET.Element]:
    (marks,) = _group(text, "ck-marks")
    return list(marks)


def _bands(text: str) -> list[ET.Element]:
    return [m for m in _marks(text) if m.tag == f"{SVG}path" and m.get("fill-opacity")]


def _verticals(text: str) -> list[ET.Element]:
    return [m for m in _marks(text) if m.tag == f"{SVG}line"]


def _centre_lines(text: str) -> list[ET.Element]:
    return [m for m in _marks(text) if m.tag == f"{SVG}polyline"]


def _dots(text: str) -> list[ET.Element]:
    return [m for m in _marks(text) if (m.get("d") or "").endswith("h0")]


def _band_points(path: ET.Element) -> list[tuple[float, float]]:
    d = path.get("d") or ""
    assert d.startswith("M") and d.endswith("Z")
    return [(float(a), float(b)) for a, b in (p.split(" ") for p in d[1:-1].split("L"))]


def _texts(element: ET.Element) -> list[ET.Element]:
    return list(element.iter(f"{SVG}text"))


def _legend(text: str) -> ET.Element:
    (legend,) = _group(text, "ck-legend")
    return legend


def _legend_labels(text: str) -> list[str]:
    return [t.text or "" for t in _texts(_legend(text))]


def _note_lines(text: str) -> list[str]:
    return [t.text or "" for g in _group(text, "ck-notes") for t in _texts(g)]


def _x_tick(text: str, label: str) -> float:
    """The x position of the bottom-axis tick labelled ``label``."""
    bottom = _group(text, "ck-axis")[0]
    (tick,) = [t for t in _texts(bottom) if t.text == label]
    return float(tick.get("x") or "nan")


def _y_title(text: str) -> str:
    left = _group(text, "ck-axis")[1]
    (title,) = [t for t in _texts(left) if t.get("text-anchor") == "start"]
    return title.text or ""


def _desc(text: str) -> str:
    element = _root(text).find(f"{SVG}desc")
    assert element is not None
    return element.text or ""


# --- declaration ------------------------------------------------------------------


def test_declaration() -> None:
    assert KIND.name == "band"
    assert KIND.description == (
        "A band from low to high over a numeric or time x, with an optional centre line"
    )
    assert KIND.output is Output.SVG
    value_kinds = (ValueKind.NUMBER, ValueKind.DURATION)
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
            "low",
            value_kinds,
            True,
            "The lower edge of the band: a number or duration.",
        ),
        ChannelSpec(
            "high",
            value_kinds,
            True,
            "The upper edge of the band, in the kind and unit of low.",
        ),
        ChannelSpec(
            "mid",
            value_kinds,
            False,
            "The centre line (for example a median), in the kind and unit of low.",
        ),
    )
    assert KIND.options == (
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
        1000, "rows", OverBound.REFUSE, "At most 1000 rows; more are refused."
    )
    assert KIND.max_series is None
    assert KIND.uses_all_columns is False
    assert [f.name for f in dataclasses.fields(KIND)][:3] == [
        "name",
        "description",
        "output",
    ]


# --- each refusal alone -----------------------------------------------------------


def test_a_high_in_another_unit_is_unit_mismatch_alone() -> None:
    columns = (X, LOW, column("high_s", unit="s"), MID)
    channels = {**NUM_CHANNELS, "high": "high_s"}
    (problem,) = _refusal(columns, [(1.0, 2.0, 3.0, 2.5)], channels)
    assert problem.code is ProblemCode.UNIT_MISMATCH
    assert (problem.channel, problem.column) == ("high", "high_s")
    assert "'low_m'" in problem.message and "unit 'm'" in problem.message
    assert "'high_s'" in problem.message and "unit 's'" in problem.message


def test_a_mid_with_no_unit_is_unit_mismatch_naming_both_units() -> None:
    columns = (X, LOW, HIGH, column("mid_plain"))
    channels = {**NUM_CHANNELS, "mid": "mid_plain"}
    (problem,) = _refusal(columns, [(1.0, 2.0, 3.0, 2.5)], channels)
    assert problem.code is ProblemCode.UNIT_MISMATCH
    assert problem.channel == "mid"
    assert "unit 'm'" in problem.message and "no unit" in problem.message


def test_a_duration_mid_over_a_number_low_is_channel_kind_alone() -> None:
    mid = column("mid_t", ValueKind.DURATION)
    columns = (X, LOW, HIGH, mid)
    channels = {**NUM_CHANNELS, "mid": "mid_t"}
    (problem,) = _refusal(columns, [(1.0, 2.0, 3.0, timedelta(seconds=5))], channels)
    assert problem.code is ProblemCode.CHANNEL_KIND
    assert (problem.channel, problem.column) == ("mid", "mid_t")
    assert "'low_m' is number" in problem.message
    assert "'mid_t' is duration" in problem.message
    assert problem.accepted == ("x", "high_m")


def test_channel_kind_accepted_lists_the_columns_of_lows_kind() -> None:
    spare = column("spare")
    mid = column("mid_t", ValueKind.DURATION)
    columns = (X, LOW, HIGH, mid, spare)
    channels = {**NUM_CHANNELS, "mid": "mid_t"}
    (problem,) = _refusal(
        columns, [(1.0, 2.0, 3.0, timedelta(seconds=5), 1.0)], channels
    )
    assert problem.accepted == ("x", "high_m", "spare")


def test_a_kind_mismatch_is_not_also_a_unit_mismatch() -> None:
    mid = column("mid_t", ValueKind.DURATION)
    channels = {**NUM_CHANNELS, "mid": "mid_t"}
    problems = _refusal(
        (X, LOW, HIGH, mid), [(1.0, 2.0, 3.0, timedelta(seconds=5))], channels
    )
    assert [p.code for p in problems] == [ProblemCode.CHANNEL_KIND]


def test_low_above_high_names_the_first_row_and_counts_the_rows() -> None:
    rows = [
        (0.0, 1.0, 5.0, 3.0),
        (1.0, 2.0, 6.0, 4.0),
        (2.0, 3.0, 7.0, 5.0),
        (3.0, 9.5, 4.0, 6.0),
        (4.0, 5.0, 9.0, 7.0),
        (5.0, 8.0, 2.5, 6.0),
    ]
    (problem,) = _refusal(NUM_COLUMNS, rows)
    assert problem.code is ProblemCode.VALUE_ORDER
    assert problem.row == 3
    assert problem.rows == 2
    assert (problem.channel, problem.column) == ("low", "low_m")
    assert problem.message == "Row 3 has low 10 m above high 4 m."
    assert problem.fix == (
        "Swap the low and high bindings, or correct the query so that low is at "
        "most high."
    )


def test_one_offending_row_counts_one() -> None:
    rows = [(0.0, 1.0, 5.0, 3.0), (1.0, 7.0, 6.0, 4.0)]
    (problem,) = _refusal(NUM_COLUMNS, rows)
    assert problem.message == "Row 1 has low 7 m above high 6 m."
    assert problem.rows == 1


def test_low_equal_to_high_is_drawn() -> None:
    rows = [(0.0, 5.0, 5.0, 5.0), (1.0, 2.0, 6.0, 4.0), (2.0, 3.0, 3.0, 3.0)]
    text = _render(NUM_COLUMNS, rows)
    assert len(_bands(text)) == 1


def test_a_low_above_an_absent_high_is_not_out_of_order() -> None:
    rows = [(0.0, 9.0, None, 3.0), (1.0, 2.0, 6.0, 4.0)]
    _render(NUM_COLUMNS, rows)


def test_a_duplicate_x_refuses_alone_naming_the_first_duplicate_row() -> None:
    rows = [
        (3.0, 1.0, 5.0, 3.0),
        (1.0, 2.0, 6.0, 4.0),
        (2.0, 3.0, 7.0, 5.0),
        (1.0, 4.0, 8.0, 6.0),
        (3.0, 5.0, 9.0, 7.0),
    ]
    (problem,) = _refusal(NUM_COLUMNS, rows)
    assert problem.code is ProblemCode.DUPLICATE_POSITION
    assert problem.row == 3
    assert "Row 3 repeats row 1" in problem.message
    assert "x (1)" in problem.message


def test_rows_without_x_are_not_duplicates_of_each_other() -> None:
    rows = [(None, 1.0, 5.0, 3.0), (None, 2.0, 6.0, 4.0), (1.0, 2.0, 6.0, 4.0)]
    _render(NUM_COLUMNS, rows)


def _bound_rows(count: int) -> list[tuple[Value, ...]]:
    return [(float(i), 1.0, 2.0, 1.5) for i in range(count)]


def test_1001_rows_refuse_alone_and_1000_render() -> None:
    (problem,) = _refusal(NUM_COLUMNS, _bound_rows(LIMIT + 1))
    assert problem.code is ProblemCode.OVER_BOUND
    assert problem.rows == LIMIT + 1
    assert "at most 1000 rows" in problem.message
    assert "1001" in problem.message
    _render(NUM_COLUMNS, _bound_rows(LIMIT))


def test_value_order_is_checked_after_the_bound_and_duplicates() -> None:
    rows = _bound_rows(LIMIT + 1)
    rows[5] = (0.0, 9.0, 1.0, 5.0)
    codes = [p.code for p in _refusal(NUM_COLUMNS, rows)]
    assert codes == [
        ProblemCode.OVER_BOUND,
        ProblemCode.DUPLICATE_POSITION,
        ProblemCode.VALUE_ORDER,
    ]


# --- ordering, breaks and marks ---------------------------------------------------


def test_rows_out_of_x_order_are_joined_in_x_order() -> None:
    shuffled = [
        (3.0, 3.0, 7.0, 5.0),
        (1.0, 1.0, 5.0, 3.0),
        (4.0, 4.0, 9.0, 6.5),
        (2.0, 2.0, 6.0, 4.5),
    ]
    text = _render(NUM_COLUMNS, shuffled)
    assert text == _render(NUM_COLUMNS, sorted(shuffled))
    (band,) = _bands(text)
    points = _band_points(band)
    forward = [x for x, _ in points[:4]]
    assert forward == sorted(forward) and len(set(forward)) == 4
    # the lower edge returns in the opposite order
    assert [x for x, _ in points[4:]] == forward[::-1]
    (centre,) = _centre_lines(text)
    centre_xs = [float(p.split(",")[0]) for p in (centre.get("points") or "").split()]
    assert centre_xs == forward


def test_the_band_is_a_translucent_fill_with_a_stroked_outline() -> None:
    text = _render(NUM_COLUMNS, [(1.0, 1.0, 5.0, 3.0), (2.0, 2.0, 6.0, 4.0)])
    (band,) = _bands(text)
    colour = series_style(0).color
    assert band.get("fill") == colour
    assert band.get("fill-opacity") == "0.2"
    assert band.get("stroke") == colour
    assert band.get("stroke-width") == "1"


def test_the_band_closes_upper_edge_forward_and_lower_edge_back() -> None:
    text = _render(NUM_COLUMNS, [(1.0, 1.0, 5.0, 3.0), (2.0, 2.0, 6.0, 4.0)])
    (band,) = _bands(text)
    (x0, high0), (x1, high1), (x1b, low1), (x0b, low0) = _band_points(band)
    assert (x0, x1) == (x0b, x1b)
    # pixel y grows downward: the upper edge sits above the lower
    assert high0 < low0 and high1 < low1
    assert low1 < low0 and high1 < high0  # both edges rise with the values


def test_an_absent_low_splits_the_band_into_two_paths() -> None:
    rows = [
        (1.0, 1.0, 5.0, 3.0),
        (2.0, 2.0, 6.0, 4.0),
        (3.0, None, 7.0, 5.0),
        (4.0, 4.0, 8.0, 6.0),
        (5.0, 5.0, 9.0, 7.0),
        (6.0, 6.0, 10.0, 8.0),
    ]
    text = _render(NUM_COLUMNS, rows)
    bands = _bands(text)
    assert [len(_band_points(b)) for b in bands] == [4, 6]
    assert _verticals(text) == []
    # the centre line is unbroken: mid is present at the broken position
    (centre,) = _centre_lines(text)
    assert len((centre.get("points") or "").split()) == 6


def test_an_absent_high_splits_the_band_too() -> None:
    rows = [
        (1.0, 1.0, 5.0, 3.0),
        (2.0, 2.0, None, 4.0),
        (3.0, 3.0, 7.0, 5.0),
        (4.0, 4.0, 8.0, 6.0),
    ]
    text = _render(NUM_COLUMNS, rows)
    assert len(_bands(text)) == 1
    assert len(_verticals(text)) == 1


def test_a_row_holding_one_edge_and_no_centre_breaks_the_band_and_the_line() -> None:
    rows = [
        (1.0, 1.0, 5.0, 3.0),
        (2.0, 2.0, 6.0, 4.0),
        (3.0, 3.0, None, None),
        (4.0, 4.0, 8.0, 6.0),
        (5.0, 5.0, 9.0, 7.0),
    ]
    text = _render(NUM_COLUMNS, rows)
    assert [len(_band_points(b)) for b in _bands(text)] == [4, 4]
    assert len(_centre_lines(text)) == 2


def test_a_band_point_between_two_gaps_is_one_vertical_line() -> None:
    text = _render(NUM_COLUMNS, ISOLATED_ROWS)
    (vertical,) = _verticals(text)
    assert vertical.get("x1") == vertical.get("x2")
    assert float(vertical.get("y1") or "nan") > float(vertical.get("y2") or "nan")
    assert vertical.get("stroke-width") == "1.8"
    assert vertical.get("stroke-linecap") == "round"
    assert vertical.get("stroke") == series_style(0).color
    bands = _bands(text)
    assert [len(_band_points(b)) for b in bands] == [6, 4]
    # the vertical line sits at x = 5, between the band runs at 1-3 and 8-9
    assert float(vertical.get("x1") or "nan") == _x_tick(text, "5")


def test_a_vertical_line_runs_from_the_low_edge_to_the_high_edge() -> None:
    rows = [(1.0, 2.0, 6.0, 4.0), (2.0, None, 7.0, 5.0), (3.0, 3.0, 8.0, 6.0)]
    # three positions, the band at each end is alone: two verticals
    text = _render(NUM_COLUMNS, rows)
    first, second = sorted(_verticals(text), key=lambda v: float(v.get("x1") or "0"))
    low_px = float(first.get("y1") or "nan")
    high_px = float(first.get("y2") or "nan")
    assert high_px < low_px
    assert (float(second.get("y1") or "nan") - float(second.get("y2") or "nan")) > 0
    # row 0 spans 2..6 and row 2 spans 3..8: the line lengths follow the data
    assert (low_px - high_px) < (
        float(second.get("y1") or "nan") - float(second.get("y2") or "nan")
    )


def test_an_absent_mid_splits_only_the_centre_line() -> None:
    rows = [
        (1.0, 1.0, 5.0, 3.0),
        (2.0, 2.0, 6.0, 4.0),
        (3.0, 3.0, 7.0, None),
        (4.0, 4.0, 8.0, 6.0),
        (5.0, 5.0, 9.0, 7.0),
    ]
    text = _render(NUM_COLUMNS, rows)
    assert [len(_band_points(b)) for b in _bands(text)] == [10]
    assert [len((c.get("points") or "").split()) for c in _centre_lines(text)] == [
        2,
        2,
    ]
    assert _dots(text) == []
    assert _verticals(text) == []


def test_a_centre_point_with_no_neighbour_is_a_dot() -> None:
    text = _render(NUM_COLUMNS, ISOLATED_ROWS)
    dots = _dots(text)
    assert len(dots) == 1
    # x = 7 holds only a centre value, and its neighbours have none
    match = re.fullmatch(r"M(\S+) (\S+)h0", dots[0].get("d") or "")
    assert match is not None
    assert float(match[1]) == _x_tick(text, "7")
    assert dots[0].get("stroke-width") == "5"
    assert dots[0].get("stroke-linecap") == "round"


def test_a_recorded_zero_is_drawn_as_zero_not_a_gap() -> None:
    rows = [(1.0, 0.0, 5.0, 3.0), (2.0, -1.0, 0.0, 0.0), (3.0, 1.0, 6.0, 4.0)]
    text = _render(NUM_COLUMNS, rows)
    assert len(_bands(text)) == 1
    (centre,) = _centre_lines(text)
    assert len((centre.get("points") or "").split()) == 3
    assert "Not drawn" not in _desc(text)


def test_y_zero_includes_zero() -> None:
    rows = [(1.0, 60.0, 80.0, 70.0), (2.0, 62.0, 84.0, 72.0)]
    without = _render(NUM_COLUMNS, rows)
    with_zero = _render(NUM_COLUMNS, rows, options={"y_zero": True})
    assert "mid (m) from 60 m to 84 m" in _desc(without)
    left_labels = [
        t.text
        for t in _texts(_group(with_zero, "ck-axis")[1])
        if t.get("text-anchor") == "end"
    ]
    assert "0" in left_labels
    left_without = [
        t.text
        for t in _texts(_group(without, "ck-axis")[1])
        if t.get("text-anchor") == "end"
    ]
    assert "0" not in left_without


# --- legend and axis title --------------------------------------------------------


def test_the_legend_names_the_band_and_the_centre_each_with_its_own_swatch() -> None:
    text = _render_case(_case("typical"))
    legend = _legend(text)
    assert _legend_labels(text) == ["hr p10 to hr p90", "hr p50"]
    swatches = [c for c in legend if c.tag != f"{SVG}text"]
    assert [s.tag for s in swatches] == [f"{SVG}rect", f"{SVG}line"]
    assert swatches[0].get("width") == swatches[0].get("height")
    colour = series_style(0).color
    assert swatches[0].get("fill") == colour
    assert swatches[1].get("stroke") == colour


def test_with_mid_unbound_the_legend_has_the_band_entry_only() -> None:
    text = _render_case(_case("no_mid"))
    assert _legend_labels(text) == ["hr p10 to hr p90"]
    swatches = [c for c in _legend(text) if c.tag != f"{SVG}text"]
    assert [s.tag for s in swatches] == [f"{SVG}rect"]
    assert _centre_lines(text) == [] and _dots(text) == []


def test_the_y_title_is_mids_when_bound_and_lows_otherwise() -> None:
    columns = (
        X,
        column("floor_w", unit="w"),
        column("ceiling_w", unit="w"),
        column("median_w", unit="w"),
    )
    rows = [(1.0, 100.0, 200.0, 150.0), (2.0, 110.0, 210.0, 160.0)]
    channels = {"x": "x", "low": "floor_w", "high": "ceiling_w"}
    with_mid = _render(columns, rows, {**channels, "mid": "median_w"})
    assert _y_title(with_mid) == "median (W)"
    assert "median (W) from 100 W to 210 W" in _desc(with_mid)
    no_mid = _render(columns, rows, channels)
    assert _y_title(no_mid) == "floor (W)"
    assert "floor (W) from 100 W to 210 W" in _desc(no_mid)


def test_the_description_names_each_y_channel_by_its_own_column() -> None:
    desc = _desc(_render_case(_case("typical")))
    assert "low: hr p10 (bpm); high: hr p90 (bpm); mid: hr p50 (bpm)." in desc


def test_a_value_order_message_survives_rounding() -> None:
    rows = [(0.0, 1.0, 5.0, 3.0), (1.0, 5.2, 5.1, 5.15)]
    (problem,) = _refusal(NUM_COLUMNS, rows)
    assert problem.message == "Row 1 has low 5.2 m above high 5.1 m."


def test_a_duration_value_order_message_survives_rounding_in_seconds() -> None:
    columns = (
        X,
        column("lo_t", ValueKind.DURATION),
        column("hi_t", ValueKind.DURATION),
    )
    channels = {"x": "x", "low": "lo_t", "high": "hi_t"}
    rows = [(0.0, timedelta(seconds=300.2), timedelta(seconds=300.1))]
    (problem,) = _refusal(columns, rows, channels)
    assert problem.message == "Row 0 has low 300.2 s above high 300.1 s."


def test_a_duration_axis_title_and_ranges_use_the_axis_form() -> None:
    text = _render_case(_case("long_labels"))
    desc = _desc(text)
    assert "(m:ss)" in _y_title(text)
    assert "from 0:04:00" not in desc
    assert "from 4:00 to 5:45" in desc
    assert "(h:mm:ss) from 0:10:00 to 1:10:00" in desc


# --- not drawn and no data --------------------------------------------------------


def test_undrawn_counts_are_stated_per_channel_in_the_note_and_the_description() -> (
    None
):
    text = _render_case(_case("typical"))
    expected = (
        "Not drawn: 1 row without x, 1 row without low, 1 row without high,"
        " 2 rows without mid."
    )
    assert _note_lines(text) == [expected]
    assert expected in _desc(text)


def test_a_row_absent_on_two_channels_counts_under_both() -> None:
    rows = [
        (1.0, 1.0, 5.0, 3.0),
        (2.0, 2.0, None, None),
        (3.0, None, 7.0, None),
        (4.0, None, None, None),
        (5.0, 4.0, 8.0, 6.0),
    ]
    text = _render(NUM_COLUMNS, rows)
    assert _note_lines(text) == [
        "Not drawn: 2 rows without low, 2 rows without high, 3 rows without mid."
    ]


def test_a_centre_only_row_counts_under_both_low_and_high() -> None:
    rows = [(1.0, None, None, 3.0), (2.0, 2.0, 6.0, 4.0), (3.0, 3.0, 7.0, 5.0)]
    text = _render(NUM_COLUMNS, rows)
    assert _note_lines(text) == ["Not drawn: 1 row without low, 1 row without high."]
    assert "Not drawn: 1 row without low, 1 row without high." in _desc(text)


def test_a_full_band_without_a_centre_value_counts_under_mid_only() -> None:
    rows = [(1.0, 1.0, 5.0, 3.0), (2.0, 2.0, 6.0, None), (3.0, 3.0, 7.0, 5.0)]
    text = _render(NUM_COLUMNS, rows)
    assert _note_lines(text) == ["Not drawn: 1 row without mid."]


def test_an_unbound_mid_never_appears_in_the_counts() -> None:
    rows = [(1.0, 1.0, 5.0, 3.0), (2.0, 2.0, None, 4.0), (None, 3.0, 7.0, 5.0)]
    channels = {"x": "x", "low": "low_m", "high": "high_m"}
    text = _render(NUM_COLUMNS, rows, channels)
    assert _note_lines(text) == ["Not drawn: 1 row without x, 1 row without high."]
    assert "mid" not in _desc(text)


def test_a_lone_edge_does_not_stretch_the_y_axis() -> None:
    rows = [
        (1.0, 10.0, 20.0, 15.0),
        (2.0, 12.0, 22.0, 17.0),
        (3.0, 500.0, None, 16.0),
        (4.0, None, -400.0, 16.5),
    ]
    text = _render(NUM_COLUMNS, rows)
    desc = _desc(text)
    # Both lone-edge rows are drawn (by their centre), so the y scale code sees them.
    assert "Not drawn: 1 row without low, 1 row without high." in desc
    assert "mid (m) from 10 m to 22 m" in desc
    left_labels = re.findall(r'text-anchor="end"[^>]*>([^<]*)</text>', text)
    assert left_labels == ["10", "15", "20", "25"]


def test_a_complete_chart_has_no_note() -> None:
    rows = [(1.0, 1.0, 5.0, 3.0), (2.0, 2.0, 6.0, 4.0)]
    text = _render(NUM_COLUMNS, rows)
    assert _group(text, "ck-notes") == []


def test_the_description_names_the_kind_channels_rows_and_ranges() -> None:
    text = _render_case(_case("typical"))
    assert _desc(text) == (
        "Band chart: Heart rate spread. x: week; low: hr p10 (bpm);"
        " high: hr p90 (bpm); mid: hr p50 (bpm). 9 rows."
        " Not drawn: 1 row without x, 1 row without low, 1 row without high,"
        " 2 rows without mid."
        " week from 2026-03-02 to 2026-04-13;"
        " hr p50 (bpm) from 124 bpm to 165 bpm."
    )


def test_no_rows_is_the_no_data_state() -> None:
    text = _render_case(_case("empty"))
    assert _group(text, "ck-marks") == []
    assert _desc(text) == "Band chart: Heart rate spread. No data: no rows."
    assert 'height="320"' in text.split(">")[0]


def test_rows_that_leave_no_mark_are_the_no_data_state() -> None:
    text = _render_case(_case("all_absent"))
    assert _group(text, "ck-marks") == []
    assert _desc(text) == (
        "Band chart: Heart rate spread. No data: none of the 5 rows has a value"
        " to draw."
    )


# --- goldens ----------------------------------------------------------------------


def test_cases_are_the_designed_names() -> None:
    assert [case.name for case in CASES] == [
        "typical",
        "empty",
        "all_absent",
        "single",
        "negative",
        "no_mid",
        "isolated",
        "long_labels",
        "at_bound",
    ]


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.name)
def test_golden(case: Case) -> None:
    rendered = render_case(KIND, case.request, case.data)
    assert rendered.kind == "band"
    assert rendered.output is Output.SVG
    assert_golden(golden_path("band", case.name, "svg"), rendered.text)


def test_no_stale_goldens() -> None:
    directory = golden_path("band", "x", "svg").parent
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
    weeks = [r[0] for r in TYPICAL_ROWS if r[0] is not None]
    assert weeks != sorted(weeks)
    assert TYPICAL_ROWS[3][1] is None and TYPICAL_ROWS[3][2] is not None
    assert TYPICAL_ROWS[7][2] is None and TYPICAL_ROWS[7][1] is not None
    numbers = [v for r in TYPICAL_ROWS for v in r[1:] if v is not None]
    assert len(numbers) == len(set(numbers))
    text = _render_case(_case("typical"))
    assert [len(_band_points(b)) for b in _bands(text)] == [6, 6]
    assert [len((c.get("points") or "").split()) for c in _centre_lines(text)] == [5]
    assert len(_dots(text)) == 1


def test_long_labels_golden_is_shortened() -> None:
    assert _render_case(_case("long_labels")).count("…") >= 3


def test_at_bound_golden_is_at_the_bound() -> None:
    case = _case("at_bound")
    assert len(case.data.rows) == LIMIT == KIND.bound.limit


def test_single_golden_is_one_degenerate_band_position() -> None:
    text = _render_case(_case("single"))
    (vertical,) = _verticals(text)
    assert vertical.get("y1") == vertical.get("y2")
    assert len(_dots(text)) == 1
    assert _bands(text) == []
    assert "Not drawn" not in _desc(text)


def test_negative_golden_crosses_zero() -> None:
    text = _render_case(_case("negative"))
    desc = _desc(text)
    assert "mid (m) from -6 m to 5 m" in desc
    labels = [
        t.text or ""
        for t in _texts(_group(text, "ck-axis")[1])
        if t.get("text-anchor") == "end"
    ]
    assert "0" in labels and any(label.startswith("-") for label in labels)


def main() -> None:
    for case in CASES:
        write_golden(golden_path("band", case.name, "svg"), _render_case(case))


if __name__ == "__main__":
    main()
