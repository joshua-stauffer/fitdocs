"""The ``box`` kind: boxes, whiskers, refusals and goldens.

Regenerate the goldens with ``uv run python -m tests.render.charts.kit.test_box``.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from datetime import date, timedelta
from typing import NamedTuple

import pytest

from fitdocs.render.charts.kit.data import Column, Value, ValueKind
from fitdocs.render.charts.kit.kinds.box import KIND
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
from fitdocs.render.charts.palette import CATEGORICAL_RAMP
from tests.render.charts.kit._helpers import (
    Case,
    chart_data,
    chart_request,
    column,
    problems_of,
    render_case,
)
from tests.render.charts.kit.goldens import assert_golden, golden_path, write_golden

# Columns: an unused note, the block, then the five values in an order that is
# neither the channel order nor alphabetical, so a bind by position would fail.
NOTE = column("note", ValueKind.CATEGORY)
BLOCK = column("block", ValueKind.CATEGORY)
P95 = column("p95_w", unit="w")
P05 = column("p05_w", unit="w")
P25 = column("p25_w", unit="w")
P50 = column("p50_w", unit="w")
P75 = column("p75_w", unit="w")
COLUMNS = [NOTE, BLOCK, P95, P05, P25, P50, P75]
CHANNELS = {
    "x": "block",
    "low": "p05_w",
    "q1": "p25_w",
    "median": "p50_w",
    "q3": "p75_w",
    "high": "p95_w",
}

Row = tuple[Value, Value, Value, Value, Value, Value]  # x, low, q1, median, q3, high


def _data_row(row: Row) -> tuple[Value, ...]:
    x, low, q1, median, q3, high = row
    return ("n", x, high, low, q1, median, q3)


def _request(
    *, title: str = "Weekly power", y_zero: bool | None = None
) -> ChartRequest:
    options: dict[str, OptionValue] = {} if y_zero is None else {"y_zero": y_zero}
    return chart_request("box", title=title, channels=CHANNELS, options=options)


def _case(
    name: str,
    rows: Sequence[Row],
    *,
    title: str = "Weekly power",
    columns: Sequence[Column] = COLUMNS,
    y_zero: bool | None = None,
) -> Case:
    return Case(
        name,
        _request(title=title, y_zero=y_zero),
        chart_data(columns, [_data_row(r) for r in rows]),
    )


def _text(case: Case) -> str:
    return render_case(KIND, case.request, case.data).text


def _render(rows: Sequence[Row], *, y_zero: bool | None = None) -> str:
    return _text(_case("t", rows, y_zero=y_zero))


def _problems(
    rows: Sequence[Row], *, columns: Sequence[Column] = COLUMNS
) -> tuple[ChartProblem, ...]:
    case = _case("t", rows, columns=columns)
    return problems_of(KIND, case.request, case.data)


# Reading an SVG --------------------------------------------------------------


class Rect(NamedTuple):
    x: float
    y: float
    width: float
    height: float

    @property
    def bottom(self) -> float:
        return self.y + self.height

    @property
    def centre(self) -> float:
        return self.x + self.width / 2


class Line(NamedTuple):
    x1: float
    y1: float
    x2: float
    y2: float
    width: str


_RECT = re.compile(
    r'<rect x="([^"]+)" y="([^"]+)" width="([^"]+)" height="([^"]+)" '
    r'fill="([^"]+)" fill-opacity="([^"]+)" stroke="([^"]+)" '
    r'stroke-width="([^"]+)"/>'
)
_LINE = re.compile(
    r'<line x1="([^"]+)" y1="([^"]+)" x2="([^"]+)" y2="([^"]+)" '
    r'stroke="([^"]+)" stroke-width="([^"]+)"/>'
)


def _group(svg: str, name: str) -> str:
    found = re.search(rf'<g class="{name}">(.*?)</g>', svg, re.S)
    assert found, f"no {name} group"
    return found.group(1)


def _marks_group(svg: str) -> str:
    return _group(svg, "ck-marks")


def _boxes(svg: str) -> list[Rect]:
    return [
        Rect(float(m[0]), float(m[1]), float(m[2]), float(m[3]))
        for m in _RECT.findall(_marks_group(svg))
    ]


def _lines(svg: str) -> list[Line]:
    return [
        Line(float(m[0]), float(m[1]), float(m[2]), float(m[3]), m[5])
        for m in _LINE.findall(_marks_group(svg))
    ]


def _texts(group: str) -> list[str]:
    return re.findall(r"<text [^>]*>(.*?)</text>", group)


def _axes(svg: str) -> list[str]:
    return re.findall(r'<g class="ck-axis">(.*?)</g>', svg, re.S)


def _x_labels(svg: str) -> list[str]:
    return _texts(_axes(svg)[0])[:-1]


def _notes(svg: str) -> list[str]:
    return _texts(_group(svg, "ck-notes"))


def _description(svg: str) -> str:
    found = re.search(r"<desc>(.*?)</desc>", svg, re.S)
    assert found
    return found.group(1)


def _value_at(svg: str) -> Callable[[float], float]:
    """The data value at a pixel row, read back from the y axis's own ticks."""
    axis = _axes(svg)[1]
    labels = [float(t.replace(",", "")) for t in _texts(axis)[:-1]]
    ticks = [
        float(m[1])
        for m in re.findall(
            r'<line x1="([^"]+)" y1="([^"]+)" x2="([^"]+)" y2="([^"]+)"', axis
        )
        if m[1] == m[3]
    ]
    assert len(ticks) == len(labels) >= 2
    slope = (labels[-1] - labels[0]) / (ticks[-1] - ticks[0])
    return lambda y: labels[0] + (y - ticks[0]) * slope


class Drawn(NamedTuple):
    """One box read back from the marks: every value in data units."""

    centre: float
    q1: float
    q3: float
    median: float
    low: float | None
    high: float | None
    low_cap: Line | None
    high_cap: Line | None


def _drawn(svg: str) -> list[Drawn]:
    """Each box, left to right, with its whiskers read from the marks.

    A stem is a vertical width-1 line starting on a box edge; a cap is a
    horizontal width-1 line; the median is the one width-2.5 line.
    """
    value = _value_at(svg)
    lines = _lines(svg)
    out: list[Drawn] = []
    for box in sorted(_boxes(svg), key=lambda r: r.x):
        mine = [ln for ln in lines if abs((ln.x1 + ln.x2) / 2 - box.centre) < 0.02]
        median = [ln for ln in mine if ln.width == "2.5"]
        assert len(median) == 1
        caps = [ln for ln in mine if ln.width == "1" and ln.y1 == ln.y2]
        low_cap = next((c for c in caps if c.y1 >= box.bottom - 0.02), None)
        high_cap = next((c for c in caps if c.y1 <= box.y + 0.02), None)
        out.append(
            Drawn(
                box.centre,
                value(box.bottom),
                value(box.y),
                value(median[0].y1),
                None if low_cap is None else value(low_cap.y1),
                None if high_cap is None else value(high_cap.y1),
                low_cap,
                high_cap,
            )
        )
    return out


# Declaration -----------------------------------------------------------------


def test_declaration() -> None:
    assert KIND.name == "box"
    assert KIND.description == "One box-and-whisker per category from given quartiles"
    assert KIND.output is Output.SVG
    assert KIND.channels == (
        ChannelSpec(
            "x",
            (ValueKind.CATEGORY, ValueKind.DATE, ValueKind.BOOLEAN),
            True,
            "The category or date each box stands at.",
        ),
        ChannelSpec(
            "low",
            (ValueKind.NUMBER, ValueKind.DURATION),
            True,
            "The lower whisker end.",
        ),
        ChannelSpec(
            "q1",
            (ValueKind.NUMBER, ValueKind.DURATION),
            True,
            "The bottom edge of the box.",
        ),
        ChannelSpec(
            "median",
            (ValueKind.NUMBER, ValueKind.DURATION),
            True,
            "The line across the box.",
        ),
        ChannelSpec(
            "q3",
            (ValueKind.NUMBER, ValueKind.DURATION),
            True,
            "The top edge of the box.",
        ),
        ChannelSpec(
            "high",
            (ValueKind.NUMBER, ValueKind.DURATION),
            True,
            "The upper whisker end.",
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
        60,
        "rows",
        OverBound.REFUSE,
        "A box chart draws at most 60 rows; more are refused.",
    )
    assert KIND.max_series is None
    assert KIND.uses_all_columns is False


# Goldens ---------------------------------------------------------------------

_LONG_A = "Long steady aerobic base block around the lake and back"
_LONG_B = "Tempo repeats block on the track with a long warm-up"
_LONG_C = "Recovery block"


def _at_bound_rows(count: int) -> list[Row]:
    rows: list[Row] = []
    for i in range(count):
        low = 100 + (i * 37) % 61
        q1 = low + 10 + i % 5
        median = q1 + (i * 7) % 9 + 1
        q3 = median + (i * 3) % 8 + 1
        high = q3 + (i * 5) % 11 + 2
        rows.append((f"b{i:02d}", low, q1, median, q3, high))
    return rows


CASES: tuple[Case, ...] = (
    _case(
        "typical",
        [
            ("Peak", 180, 210, 228, 250, 290),
            ("Base", 140, 160, 171, 195, 220),
            ("Taper", None, 190, 203, 230, 262),
            ("Build", 150, 175, None, 215, 245),
            ("Race", 200, 240, 262, 270, None),
            (None, 120, 150, 158, 190, 205),
        ],
    ),
    _case("empty", []),
    _case(
        "all_absent",
        [
            ("Base", 140, 160, None, 195, 220),
            ("Build", 150, None, 190, 215, 245),
            ("Peak", 180, 210, 228, None, 290),
        ],
    ),
    _case("single", [("Solo", 140, 165, 172, 205, 230)]),
    _case(
        "negative",
        [
            ("Mon", -30, -12, -8, 6, 14),
            ("Tue", -22, -4, 1.5, 9, 25),
            ("Wed", -41, -35, -20.5, -10, -2),
        ],
    ),
    _case(
        "zero_whisker",
        [
            ("Flat low", 160, 160, 172, 190, 215),
            ("Flat high", 140, 155, 170, 185, 185),
            ("Both", 150, 150, 160, 180, 180),
            ("Neither", 130, 150, 165, 190, 210),
        ],
    ),
    _case(
        "long_labels",
        [
            (_LONG_A, 140, 165, 172, 205, 230),
            (_LONG_B, 150, 170, 188, 210, 240),
            (_LONG_C, 120, 140, 150, 170, 185),
        ],
        title="A weekly power summary with a title far longer than any chart "
        "could hope to show in one line of text",
        columns=[
            NOTE,
            column("block", ValueKind.CATEGORY, label=_LONG_A + " block"),
            P95,
            P05,
            P25,
            column(
                "p50_w",
                unit="w",
                label="Median power sustained across the whole training block",
            ),
            P75,
        ],
    ),
    _case("at_bound", _at_bound_rows(60)),
)


def test_cases_are_the_designed_names() -> None:
    assert [case.name for case in CASES] == [
        "typical",
        "empty",
        "all_absent",
        "single",
        "negative",
        "zero_whisker",
        "long_labels",
        "at_bound",
    ]


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.name)
def test_golden(case: Case) -> None:
    rendered = render_case(KIND, case.request, case.data)
    assert rendered.kind == "box"
    assert rendered.output is Output.SVG
    assert_golden(golden_path("box", case.name, "svg"), rendered.text)


def test_no_stale_goldens() -> None:
    directory = golden_path("box", "x", "svg").parent
    on_disk = sorted(path.name for path in directory.iterdir())
    assert on_disk == sorted(f"{case.name}.svg" for case in CASES)


def main() -> None:
    for case in CASES:
        write_golden(golden_path("box", case.name, "svg"), _text(case))


def _case_named(name: str) -> Case:
    (case,) = [c for c in CASES if c.name == name]
    return case


def test_goldens_hold_their_precondition() -> None:
    long_labels = _text(_case_named("long_labels"))
    assert any(label.endswith("…") for label in _x_labels(long_labels))
    assert _LONG_A not in _x_labels(long_labels)
    typical = _text(_case_named("typical"))
    assert len(_boxes(typical)) == 5  # six rows, one without a median
    assert _notes(typical) == [
        "Not drawn: 1 row without median.",
        "No whisker: 1 row without low, 1 row without high.",
    ]
    assert len(_case_named("at_bound").data.rows) == KIND.bound.limit
    assert len(_boxes(_text(_case_named("at_bound")))) == 60
    assert len(_boxes(_text(_case_named("single")))) == 1
    zero = _drawn(_text(_case_named("zero_whisker")))
    assert [(d.low, d.q1) for d in zero][0] == pytest.approx((160.0, 160.0), abs=0.05)
    negative = _text(_case_named("negative"))
    assert any(d.low is not None and d.low < 0 for d in _drawn(negative))


def test_empty_and_all_absent_say_why() -> None:
    assert "No data: no rows." in _description(_text(_case_named("empty")))
    assert "No data: none of the 3 rows has a value to draw." in _description(
        _text(_case_named("all_absent"))
    )
    assert "ck-marks" not in _text(_case_named("all_absent"))


# The values drawn are the values given -------------------------------------------


def test_the_drawn_values_are_exactly_the_given_ones() -> None:
    # In every row the median differs from the midpoint of q1 and q3, so a box
    # recomputed from the quartiles would move (asserted below).
    rows: list[Row] = [
        ("A", 112, 140, 148, 190, 230),
        ("B", 90, 131, 133, 176, 205),
        ("C", 150, 155, 190, 200, 260),
    ]
    drawn = _drawn(_render(rows))
    assert len(drawn) == 3
    for got, (_, low, q1, median, q3, high) in zip(drawn, rows, strict=True):
        assert (got.low, got.q1, got.median, got.q3, got.high) == pytest.approx(
            (low, q1, median, q3, high), abs=0.05
        )
        assert got.median != pytest.approx((got.q1 + got.q3) / 2, abs=1.0)


def test_negative_and_zero_values_are_drawn_where_they_are() -> None:
    rows: list[Row] = [("A", -30, -12, 0, 6, 14), ("B", 0, 2, 4, 8, 20)]
    first, second = _drawn(_render(rows))
    assert first.median == pytest.approx(0.0, abs=0.05)
    assert second.low == pytest.approx(0.0, abs=0.05)
    assert first.low == pytest.approx(-30.0, abs=0.05)


def test_the_box_is_the_series_colour_translucent_with_a_solid_outline() -> None:
    svg = _render([("A", 140, 165, 172, 205, 230)])
    (match,) = _RECT.findall(_marks_group(svg))
    colour = CATEGORICAL_RAMP[0]
    assert match[4:] == (colour, "0.2", colour, "1")
    strokes = set(re.findall(r'stroke="([^"]+)"', _marks_group(svg)))
    assert strokes == {colour}


def test_the_median_line_is_thicker_and_spans_the_box() -> None:
    svg = _render([("A", 140, 165, 172, 205, 230)])
    (box,) = _boxes(svg)
    (median,) = [ln for ln in _lines(svg) if ln.width == "2.5"]
    assert (median.x1, median.x2) == pytest.approx((box.x, box.x + box.width), abs=0.02)
    assert median.y1 == median.y2
    assert box.y < median.y1 < box.bottom


# Widths -------------------------------------------------------------------------


def test_a_lone_box_is_capped_at_40_px() -> None:
    (box,) = _boxes(_render([("Solo", 140, 165, 172, 205, 230)]))
    assert box.width == 40.0


def test_boxes_fill_60_percent_of_a_narrow_band() -> None:
    rows = [
        (f"c{i:02d}", 100 + i, 120 + i, 130 + i, 150 + i, 170 + i) for i in range(30)
    ]
    boxes = sorted(_boxes(_render(rows)), key=lambda r: r.x)
    spacing = boxes[1].x - boxes[0].x
    assert 0.6 * spacing < 40
    for box in boxes:
        assert box.width == pytest.approx(0.6 * spacing, abs=0.02)


def test_a_cap_is_half_the_box_wide_and_centred_on_the_whisker() -> None:
    svg = _render([("A", 140, 165, 172, 205, 230)])
    (box,) = _boxes(svg)
    (drawn,) = _drawn(svg)
    for cap in (drawn.low_cap, drawn.high_cap):
        assert cap is not None
        assert cap.x2 - cap.x1 == pytest.approx(box.width / 2, abs=0.02)
        assert (cap.x1 + cap.x2) / 2 == pytest.approx(box.centre, abs=0.02)
    stems = [ln for ln in _lines(svg) if ln.x1 == ln.x2]
    assert len(stems) == 2
    assert all(ln.x1 == pytest.approx(box.centre, abs=0.02) for ln in stems)


def test_stems_run_from_the_box_edge_to_the_cap() -> None:
    svg = _render([("A", 140, 165, 172, 205, 230)])
    (box,) = _boxes(svg)
    (drawn,) = _drawn(svg)
    assert drawn.low_cap is not None and drawn.high_cap is not None
    stems = sorted((ln for ln in _lines(svg) if ln.x1 == ln.x2), key=lambda ln: ln.y1)
    upper, lower = stems
    assert upper.y1 == pytest.approx(box.y, abs=0.02)
    assert upper.y2 == pytest.approx(drawn.high_cap.y1, abs=0.02)
    assert lower.y1 == pytest.approx(box.bottom, abs=0.02)
    assert lower.y2 == pytest.approx(drawn.low_cap.y1, abs=0.02)


# Absent values ----------------------------------------------------------------


@pytest.mark.parametrize("channel", ["q1", "median", "q3"])
def test_a_row_missing_a_box_value_draws_no_box_but_keeps_its_band(
    channel: str,
) -> None:
    rows: list[Row] = [
        ("A", 140, 165, 172, 205, 230),
        ("B", 130, 150, 160, 180, 200),
        ("C", 120, 145, 155, 175, 195),
    ]
    index = {"q1": 2, "median": 3, "q3": 4}[channel]
    broken = list(rows[1])
    broken[index] = None
    rows[1] = (broken[0], *broken[1:])  # type: ignore[assignment]
    svg = _render(rows)
    assert len(_boxes(svg)) == 2
    assert _x_labels(svg) == ["A", "B", "C"]  # B keeps its band
    note = f"Not drawn: 1 row without {channel}."
    assert _notes(svg) == [note]
    assert note in _description(svg)
    band_b = _x_centres(svg)[1]
    # Nothing at B: no box, and no stem, cap or median line either.
    assert not [ln for ln in _lines(svg) if abs((ln.x1 + ln.x2) / 2 - band_b) < 0.02]
    assert not [r for r in _boxes(svg) if abs(r.centre - band_b) < 0.02]


def test_a_row_missing_several_box_values_counts_under_each_of_them() -> None:
    rows: list[Row] = [
        ("A", 140, 165, 172, 205, 230),
        ("B", 130, None, None, 180, 200),
        ("C", 120, 145, None, None, 195),
    ]
    svg = _render(rows)
    note = "Not drawn: 1 row without q1, 2 rows without median, 1 row without q3."
    assert _notes(svg) == [note]
    assert note in _description(svg)


def test_order_message_gives_exact_numbers_when_rounding_would_hide_them() -> None:
    km = [column(c.name, unit="m") for c in (P95, P05, P25, P50, P75)]
    rows: list[Row] = [("A", 1, 5.2, 5.1, 6, 7)]
    case = _case("t", rows, columns=[NOTE, BLOCK, *km])
    (problem,) = problems_of(KIND, case.request, case.data)
    assert problem.message == "Row 0 has q1 5.2 m above median 5.1 m."


def test_order_message_gives_exact_seconds_for_durations() -> None:
    kinds = [column(c.name, ValueKind.DURATION) for c in (P95, P05, P25, P50, P75)]
    one = timedelta(seconds=1)
    row: Row = ("A", one, timedelta(seconds=5.2), timedelta(seconds=5.1), one, one)
    case = _case("t", [row], columns=[NOTE, BLOCK, *kinds])
    (problem,) = problems_of(KIND, case.request, case.data)
    assert problem.message == "Row 0 has q1 5.2 s above median 5.1 s."


def test_order_message_keeps_the_rounded_form_when_it_tells_them_apart() -> None:
    (problem,) = _problems([("A", 140, 175, 160, 190, 210)])
    assert problem.message == "Row 0 has q1 175 W above median 160 W."


def _x_centres(svg: str) -> list[float]:
    found = re.findall(r'<text x="([^"]+)"', _axes(svg)[0])
    return [float(x) for x in found[:-1]]


def test_whisker_values_of_a_row_without_a_box_draw_nothing() -> None:
    rows: list[Row] = [
        ("A", 140, 165, 172, 205, 230),
        ("B", 100, 150, None, 180, 900),
        ("C", None, 150, None, 180, None),
    ]
    svg = _render(rows)
    assert len(_boxes(svg)) == 1
    assert len(_lines(svg)) == 5  # A: two stems, two caps, a median; nothing at B, C
    # No whisker line: C's missing ends belong to a box that is not drawn.
    assert _notes(svg) == ["Not drawn: 2 rows without median."]
    top = max(float(v) for v in re.findall(r">(\d+)</text>", _axes(svg)[1]))
    assert top < 900  # the axis does not stretch to a value nothing shows


def test_an_absent_low_draws_no_lower_whisker_or_cap() -> None:
    rows: list[Row] = [("A", None, 165, 172, 205, 230), ("B", 130, 150, 160, 180, 200)]
    svg = _render(rows)
    first, second = _drawn(svg)
    assert first.low is None and first.low_cap is None
    assert first.high == pytest.approx(230.0, abs=0.05)
    assert second.low == pytest.approx(130.0, abs=0.05)
    assert len(_lines(svg)) == 8  # A: stem, cap, median; B: two stems, two caps, median
    assert _notes(svg) == ["No whisker: 1 row without low."]


def test_an_absent_high_draws_no_upper_whisker_or_cap() -> None:
    svg = _render([("A", 140, 165, 172, 205, None)])
    (drawn,) = _drawn(svg)
    assert drawn.high is None and drawn.high_cap is None
    assert drawn.low == pytest.approx(140.0, abs=0.05)
    assert _notes(svg) == ["No whisker: 1 row without high."]


def test_missing_whisker_ends_are_counted_by_end_with_plurals() -> None:
    rows: list[Row] = [
        ("A", None, 165, 172, 205, None),
        ("B", 130, 150, 160, 180, None),
        ("C", 120, 145, 155, 175, 195),
    ]
    assert _notes(_render(rows)) == [
        "No whisker: 1 row without low, 2 rows without high."
    ]


def test_a_complete_chart_has_no_notes() -> None:
    svg = _render([("A", 140, 165, 172, 205, 230)])
    assert "ck-notes" not in svg
    assert "Not drawn" not in _description(svg)


def test_a_whisker_of_zero_length_still_has_its_cap() -> None:
    svg = _render([("A", 165, 165, 172, 205, 205), ("B", 140, 150, 160, 190, 230)])
    flat, normal = _drawn(svg)
    assert flat.low_cap is not None and flat.high_cap is not None
    box = sorted(_boxes(svg), key=lambda r: r.x)[0]
    assert flat.low_cap.y1 == pytest.approx(box.bottom, abs=0.02)  # on the box edge
    assert flat.high_cap.y1 == pytest.approx(box.y, abs=0.02)
    assert flat.low == pytest.approx(165.0, abs=0.05)
    stems_of_flat = [
        ln for ln in _lines(svg) if ln.x1 == ln.x2 and abs(ln.x1 - flat.centre) < 0.02
    ]
    assert stems_of_flat == []  # no stem of zero length, only the cap
    assert normal.low_cap is not None
    assert "ck-notes" not in svg


# Categories ---------------------------------------------------------------------


def test_categories_keep_first_appearance_with_absent_last() -> None:
    rows: list[Row] = [
        ("Wed", 100, 120, 130, 150, 170),
        (None, 110, 130, 140, 160, 180),
        ("Mon", 120, 140, 150, 170, 190),
        ("Fri", 130, 150, 160, 180, 200),
    ]
    svg = _render(rows)
    assert _x_labels(svg) == ["Wed", "Mon", "Fri", "—"]
    # Boxes follow the same left-to-right order: medians by position.
    assert [round(d.median) for d in _drawn(svg)] == [130, 150, 160, 140]


def test_dates_ascend_from_unsorted_rows() -> None:
    week = column("block", ValueKind.DATE)
    cols = [NOTE, week, P95, P05, P25, P50, P75]
    dates = [date(2026, 3, 9), date(2026, 3, 2), date(2026, 3, 23), date(2026, 3, 16)]
    rows: list[Row] = [
        (d, 100 + i, 120 + i, 125 + 5 * i, 150 + i, 170 + i)
        for i, d in enumerate(dates)
    ]
    case = _case("t", rows, columns=cols)
    svg = _text(case)
    assert _x_labels(svg) == ["2026-03-02", "2026-03-09", "2026-03-16", "2026-03-23"]
    assert [round(d.median) for d in _drawn(svg)] == [130, 125, 140, 135]


def test_boolean_x_is_accepted() -> None:
    flag = column("block", ValueKind.BOOLEAN)
    cols = [NOTE, flag, P95, P05, P25, P50, P75]
    rows: list[Row] = [(True, 100, 120, 130, 150, 170), (False, 90, 110, 125, 140, 160)]
    svg = _text(_case("t", rows, columns=cols))
    assert len(_boxes(svg)) == 2
    assert len(_x_labels(svg)) == 2


# The value axis -------------------------------------------------------------------


def test_the_axis_starts_at_zero_only_when_asked() -> None:
    rows: list[Row] = [("A", 140, 165, 172, 205, 230), ("B", 150, 170, 180, 210, 240)]
    off = _texts(_axes(_render(rows))[1])[:-1]
    assert "0" not in off
    default = _texts(_axes(_render(rows, y_zero=False))[1])[:-1]
    assert default == off
    on = _texts(_axes(_render(rows, y_zero=True))[1])[:-1]
    assert on[0] == "0"


def test_the_axis_title_is_the_median_columns() -> None:
    svg = _render([("A", 140, 165, 172, 205, 230)])
    assert _texts(_axes(svg)[1])[-1] == "p50 (W)"
    assert _texts(_axes(svg)[0])[-1] == "block"


# Refusals -----------------------------------------------------------------------


def _with_column(position: int, replacement: Column) -> list[Column]:
    cols = list(COLUMNS)
    cols[position] = replacement
    return cols


_POSITION = {"high": 2, "low": 3, "q1": 4, "median": 5, "q3": 6}
_ROW: Row = ("A", 140, 165, 172, 205, 230)


@pytest.mark.parametrize("channel", ["q1", "median", "q3", "high"])
def test_a_value_column_of_another_unit_is_unit_mismatch(channel: str) -> None:
    name = CHANNELS[channel]
    odd = column(name, unit="bpm")
    (problem,) = _problems([_ROW], columns=_with_column(_POSITION[channel], odd))
    assert problem.code is ProblemCode.UNIT_MISMATCH
    assert problem.channel == channel
    assert problem.column == name
    assert "unit 'bpm'" in problem.message
    assert "unit 'w'" in problem.message
    assert "'p05_w'" in problem.message
    every = ("p95_w", "p05_w", "p25_w", "p50_w", "p75_w")
    assert problem.accepted == tuple(n for n in every if n != name)


def test_a_missing_unit_on_one_value_is_unit_mismatch() -> None:
    bare = column("p75_w")
    (problem,) = _problems([_ROW], columns=_with_column(6, bare))
    assert problem.code is ProblemCode.UNIT_MISMATCH
    assert problem.channel == "q3"
    assert "has no unit" in problem.message


def test_the_low_column_is_the_one_the_others_are_compared_to() -> None:
    odd = column("p05_w", unit="bpm")
    found = _problems([_ROW], columns=_with_column(3, odd))
    assert [(p.code, p.channel) for p in found] == [
        (ProblemCode.UNIT_MISMATCH, ch) for ch in ("q1", "median", "q3", "high")
    ]


def test_a_duration_among_numbers_is_channel_kind_not_unit_mismatch() -> None:
    odd = column("p50_w", ValueKind.DURATION)
    case = _case(
        "t",
        [("A", 140, 165, timedelta(seconds=172), 205, 230)],
        columns=_with_column(5, odd),
    )
    (problem,) = problems_of(KIND, case.request, case.data)
    assert problem.code is ProblemCode.CHANNEL_KIND
    assert problem.channel == "median"
    assert problem.column == "p50_w"
    assert problem.accepted == ("p95_w", "p05_w", "p25_w", "p75_w")


def test_matching_columns_of_one_unit_are_accepted() -> None:
    assert _render([_ROW])


def test_q1_above_the_median_is_value_order_naming_both() -> None:
    rows: list[Row] = [
        ("A", 140, 165, 172, 205, 230),
        ("B", 130, 150, 160, 180, 200),
        ("C", 120, 175, 160, 190, 210),
        ("D", 130, 150, 160, 180, 200),
    ]
    (problem,) = _problems(rows)
    assert problem.code is ProblemCode.VALUE_ORDER
    assert problem.row == 2
    assert problem.rows == 1
    assert problem.message == "Row 2 has q1 175 W above median 160 W."
    assert problem.fix == (
        "Bind each channel to its own column, or correct the query so that "
        "low ≤ q1 ≤ median ≤ q3 ≤ high."
    )
    assert problem.channel == "median"
    assert problem.column == "p50_w"


def test_q3_above_high_is_value_order_naming_both() -> None:
    rows: list[Row] = [
        ("A", 140, 165, 172, 205, 230),
        ("B", 130, 150, 160, 180, 200),
        ("C", 120, 145, 155, 235, 210),
    ]
    (problem,) = _problems(rows)
    assert problem.code is ProblemCode.VALUE_ORDER
    assert problem.row == 2
    assert problem.message == "Row 2 has q3 235 W above high 210 W."


def test_value_order_names_the_first_pair_of_the_first_row() -> None:
    rows: list[Row] = [
        ("A", 140, 165, 172, 205, 230),
        ("B", 200, 150, 160, 100, 90),
        ("C", 300, 150, 160, 100, 90),
    ]
    (problem,) = _problems(rows)
    assert problem.row == 1
    assert problem.rows == 2
    assert problem.message.startswith("Row 1 has low 200 W above q1 150 W.")


def test_value_order_compares_the_present_neighbours_across_an_absent_one() -> None:
    rows: list[Row] = [("A", 140, 200, None, 150, 230)]
    (problem,) = _problems(rows)
    assert problem.message == "Row 0 has q1 200 W above q3 150 W."


def test_value_order_is_checked_for_a_row_that_draws_no_box() -> None:
    (problem,) = _problems([("A", 300, None, None, None, 230)])
    assert problem.code is ProblemCode.VALUE_ORDER
    assert problem.message == "Row 0 has low 300 W above high 230 W."


def test_equal_neighbours_are_in_order() -> None:
    rows: list[Row] = [
        ("A", 150, 150, 150, 150, 150),
        ("B", 130, 130, 160, 160, 200),
    ]
    svg = _render(rows)
    assert len(_boxes(svg)) == 2


def test_two_rows_at_one_x_are_refused_alone() -> None:
    rows: list[Row] = [
        ("A", 140, 165, 172, 205, 230),
        ("B", 130, 150, 160, 180, 200),
        ("A", 120, 145, 155, 175, 195),
    ]
    (problem,) = _problems(rows)
    assert problem.code is ProblemCode.DUPLICATE_POSITION
    assert problem.row == 2
    assert "row 0" in problem.message
    assert "A" in problem.message


def test_two_rows_with_absent_x_collide_because_absent_is_a_category() -> None:
    rows: list[Row] = [
        (None, 140, 165, 172, 205, 230),
        ("B", 130, 150, 160, 180, 200),
        (None, 120, 145, 155, 175, 195),
    ]
    (problem,) = _problems(rows)
    assert problem.code is ProblemCode.DUPLICATE_POSITION
    assert problem.row == 2


def test_60_rows_render_and_61_are_refused_alone() -> None:
    assert _render(_at_bound_rows(60))
    (problem,) = _problems(_at_bound_rows(61))
    assert problem.code is ProblemCode.OVER_BOUND
    assert problem.rows == 61


def test_problems_come_in_the_kit_order() -> None:
    rows = _at_bound_rows(61)
    rows[5] = ("b00", 100, 150, 140, 200, 250)  # duplicate x and q1 above median
    codes = [p.code for p in _problems(rows)]
    assert codes == [
        ProblemCode.OVER_BOUND,
        ProblemCode.DUPLICATE_POSITION,
        ProblemCode.VALUE_ORDER,
    ]


# Description, order and containment ----------------------------------------------


def test_description_summarises_the_chart() -> None:
    rows: list[Row] = [
        ("A", 140, 165, 172, 205, 230),
        ("B", 130, 150, None, 180, 260),
        ("C", None, 160, 165, 190, 200),
    ]
    assert _description(_render(rows)) == (
        "Box chart: Weekly power. x: block; low: p05 (W); q1: p25 (W); "
        "median: p50 (W); q3: p75 (W); high: p95 (W). 3 rows. "
        "Not drawn: 1 row without median. block from A to C; "
        "p50 (W) from 140 W to 230 W."
    )


def test_duration_ranges_use_the_axis_form() -> None:
    kinds = [column(c.name, ValueKind.DURATION) for c in (P95, P05, P25, P50, P75)]
    cols = [NOTE, BLOCK, *kinds]

    def minutes(*values: int) -> Row:
        a, b, c, d, e = (timedelta(minutes=v) for v in values)
        return ("A", a, b, c, d, e)

    short = _text(_case("t", [minutes(20, 25, 30, 35, 45)], columns=cols))
    assert "p50 w (m:ss) from 20:00 to 45:00." in _description(short)
    assert "low: p05 w (m:ss)" in _description(short)
    long = _text(_case("t", [minutes(20, 25, 30, 35, 90)], columns=cols))
    assert "p50 w (h:mm:ss) from 0:20:00 to 1:30:00." in _description(long)
    assert "low: p05 w (h:mm:ss)" in _description(long)
    assert _texts(_axes(long)[1])[-1] == "p50 w (h:mm:ss)"


def test_the_body_is_drawn_in_the_documented_order() -> None:
    svg = _text(_case_named("typical"))
    order = [
        svg.index('<g class="ck-grid">'),
        svg.index('<g class="ck-marks">'),
        svg.index('<g class="ck-axis">'),
        svg.index('<text x="8" y="21"'),
        svg.index('<g class="ck-notes">'),
    ]
    assert order == sorted(order)


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.name)
def test_every_text_stays_inside_the_chart(case: Case) -> None:
    svg = _text(case)
    width = float(re.search(r'<svg [^>]*width="([^"]+)"', svg).group(1))  # type: ignore[union-attr]
    found = re.findall(
        r'<text x="([^"]+)" y="[^"]+"(?: text-anchor="([^"]+)")? '
        r'font-size="([^"]+)"[^>]*>(.*?)</text>',
        svg,
    )
    assert found
    assert len(found) == svg.count("<text ")
    for x, anchor, size, content in found:
        reach = text_width(content, float(size))
        left = (
            float(x) - reach / 2
            if anchor == "middle"
            else float(x) - reach
            if anchor == "end"
            else float(x)
        )
        assert left >= 8.0 - 1e-6, content
        assert left + reach <= width - 4.0 + 1e-6, content


if __name__ == "__main__":
    main()
