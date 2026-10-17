"""Chart-catalog 1.4: the binned value scale, the cell marks and the grid legend.

Requirements 2.2, 2.3 and 3.1-3.4, 3.6-3.8 (3.5, a missing row draws nothing,
belongs to the kinds: ``cells`` only ever sees the cells it is handed).
"""

from __future__ import annotations

import math
import re
from collections.abc import Mapping, Sequence
from datetime import timedelta

import pytest

from fitdocs.render.charts.kit.cells import (
    ABSENT_LABEL,
    CELL_GAP,
    MAX_BINS,
    MIN_MARK,
    BinnedScale,
    binned_scale,
    cell_marks,
    legend,
    legend_entries,
    negative_problem,
)
from fitdocs.render.charts.kit.data import Column, Value, ValueKind
from fitdocs.render.charts.kit.frame import legend as frame_legend
from fitdocs.render.charts.kit.layout import FramePlan, LegendEntry, Rect, plan_frame
from fitdocs.render.charts.kit.problems import ProblemCode
from fitdocs.render.charts.kit.schema import (
    BoundChart,
    ChannelSpec,
    KindSpec,
    MarkBound,
    Output,
    OverBound,
)
from fitdocs.render.charts.kit.theme import STROKE, TEXT, ink
from fitdocs.render.charts.palette import SEQUENTIAL_RAMP

from ._helpers import chart_request, column

LOAD = column("load")
DURATION = column("moving_time", ValueKind.DURATION)
SECONDS = column("elapsed_s", unit="s")
PACE = column("pace_s_per_km", unit="s_per_km")
PERCENT = column("share_pct", unit="pct")
KM = column("distance_km", unit="km")


def _scale(values: Sequence[float | None], col: Column = LOAD) -> BinnedScale:
    return binned_scale(values, col)


# --------------------------------------------------------------------- edges


def test_constants() -> None:
    assert (MAX_BINS, CELL_GAP, MIN_MARK, ABSENT_LABEL) == (5, 1.0, 2.0, "no value")


@pytest.mark.parametrize(
    ("values", "edges"),
    [
        # round values from zero up to at or above the largest present value
        ([12.5, 41.0, 3.5, None, 0.0], (0.0, 10.0, 20.0, 30.0, 40.0, 50.0)),
        # whole values, max 3: steps of 1 (the ladder gives 1 here either way)
        ([3.0, 1.0, 0.0, 2.0], (0.0, 1.0, 2.0, 3.0)),
        # whole values, max 2: steps of 1; without the whole-number rule, 0.5
        ([2.0, 1.0], (0.0, 1.0, 2.0)),
        ([7.0, 2.0, 0.0], (0.0, 2.0, 4.0, 6.0, 8.0)),
        # a non-whole value allows steps of 0.5
        ([2.5, 0.7, 1.3], (0.0, 0.5, 1.0, 1.5, 2.0, 2.5)),
        # a non-whole small value does not change a whole-step maximum
        ([3.0, 0.5, 2.0], (0.0, 1.0, 2.0, 3.0)),
    ],
)
def test_edges_for_numbers(
    values: list[float | None], edges: tuple[float, ...]
) -> None:
    scale = _scale(values)
    assert scale.edges == edges
    assert scale.bins == len(edges) - 1


def test_edges_for_a_non_whole_max_two_use_half_steps() -> None:
    # the same maximum as the whole-valued [2.0, 1.0] above, one value non-whole
    assert _scale([2.0, 1.5]).edges == (0.0, 0.5, 1.0, 1.5, 2.0)


def test_durations_up_to_5400_seconds_use_the_duration_ladder() -> None:
    scale = _scale([1200.0, 5400.0, 60.0, 0.0, None], DURATION)
    assert scale.edges == (0.0, 1800.0, 3600.0, 5400.0)
    assert scale.labels == ("0:30:00", "1:00:00", "1:30:00")
    assert scale.zero_label == "0:00:00"


def test_duration_edges_below_an_hour_use_the_short_form() -> None:
    scale = _scale([130.0, 600.0, 45.0], SECONDS)
    assert scale.edges == (0.0, 120.0, 240.0, 360.0, 480.0, 600.0)
    assert scale.labels == ("2:00", "4:00", "6:00", "8:00", "10:00")
    assert scale.zero_label == "0:00"


def test_one_hour_edge_switches_every_label_to_the_long_form() -> None:
    scale = _scale([300.0, 3600.0], DURATION)
    assert scale.edges == (0.0, 900.0, 1800.0, 2700.0, 3600.0)
    assert scale.labels == ("0:15:00", "0:30:00", "0:45:00", "1:00:00")


def test_pace_edges_are_on_the_ladder_and_labelled_as_pace() -> None:
    scale = _scale([400.0, 250.0, 310.0], PACE)
    assert scale.edges == (0.0, 120.0, 240.0, 360.0, 480.0)
    assert scale.labels == ("2:00", "4:00", "6:00", "8:00")
    assert scale.zero_label == "0:00"


def test_percent_labels_carry_their_symbol() -> None:
    scale = _scale([41.0, 5.0], PERCENT)
    assert scale.edges == (0.0, 10.0, 20.0, 30.0, 40.0, 50.0)
    assert scale.labels == ("10%", "20%", "30%", "40%", "50%")
    assert scale.zero_label == "0%"


def test_number_labels_follow_the_step() -> None:
    assert _scale([41.0]).labels == ("10", "20", "30", "40", "50")
    assert _scale([41.0]).zero_label == "0"
    assert _scale([2.5, 1.3]).labels == ("0.5", "1.0", "1.5", "2.0", "2.5")
    assert _scale([2.5, 1.3]).zero_label == "0.0"


@pytest.mark.parametrize(
    "values", [[0.0, None, 0.0], [None], [], [0.0], [None, 0.0, None, 0.0]]
)
@pytest.mark.parametrize("col", [LOAD, DURATION, PACE, PERCENT])
def test_no_positive_value_gives_no_bins(
    values: list[float | None], col: Column
) -> None:
    scale = _scale(values, col)
    assert scale.edges == (0.0,)
    assert scale.bins == 0
    assert scale.labels == ()


def test_no_positive_value_still_formats_the_zero() -> None:
    assert _scale([0.0], LOAD).zero_label == "0"
    assert _scale([0.0], DURATION).zero_label == "0:00"
    assert _scale([None], PERCENT).zero_label == "0%"


def test_absent_values_do_not_enter_the_maximum() -> None:
    assert _scale([None, 3.0, None]).edges == (0.0, 1.0, 2.0, 3.0)


def test_a_bin_count_never_exceeds_the_maximum() -> None:
    for top in (1.0, 7.0, 13.0, 41.0, 99.0, 250.0, 1234.0, 0.37, 17.5):
        assert 1 <= _scale([top]).bins <= MAX_BINS


# ------------------------------------------------------------------ classify


def test_classify_puts_an_edge_value_in_the_lower_bin() -> None:
    scale = _scale([41.0, 12.5])  # edges 0, 10, 20, 30, 40, 50
    assert scale.bins == 5
    assert [scale.classify(v) for v in (10.0, 20.0, 30.0, 40.0, 50.0)] == [
        1,
        2,
        3,
        4,
        5,
    ]


def test_classify_puts_a_value_just_above_an_edge_in_the_next_bin() -> None:
    scale = _scale([41.0, 12.5])
    above = [10.0001, 20.0001, 30.0001, 40.0001]
    assert [scale.classify(v) for v in above] == [2, 3, 4, 5]
    assert scale.classify(0.0001) == 1
    assert scale.classify(9.9999) == 1


def test_classify_zero_is_class_zero_not_the_first_bin() -> None:
    scale = _scale([41.0])
    assert scale.classify(0.0) == 0
    assert scale.classify(0) == 0
    assert scale.classify(-0.0) == 0
    assert scale.classify(0.0) != scale.classify(0.5)


def test_classify_absent_is_none_not_zero() -> None:
    scale = _scale([41.0])
    assert scale.classify(None) is None
    assert scale.classify(None) != scale.classify(0.0)


def test_classify_with_no_bins_has_only_zero_and_absent() -> None:
    scale = _scale([0.0, None])
    assert scale.classify(0.0) == 0
    assert scale.classify(None) is None
    with pytest.raises(ValueError, match="no bins"):
        scale.classify(1.0)


def test_classify_refuses_what_the_kinds_refuse_first() -> None:
    scale = _scale([41.0])
    with pytest.raises(ValueError, match="negative"):
        scale.classify(-1.0)
    # a positive value above the last edge clamps to the last bin (below)
    assert scale.classify(50.5) == 5


@pytest.mark.parametrize("values", [[0.1 + 0.2], [40.00000000001, 3.0]])
def test_the_scale_classifies_its_own_maximum(values: list[float | None]) -> None:
    scale = _scale(values)
    top = max(v for v in values if v is not None)
    assert scale.bins > 0
    assert scale.classify(top) == scale.bins
    assert top <= scale.edges[-1]


# --------------------------------------------------------------- colour/size


def test_color_takes_the_top_n_ramp_entries() -> None:
    scale = _scale([3.0, 1.0, 2.0])
    assert scale.bins == 3
    assert [scale.color(i) for i in (1, 2, 3)] == [
        SEQUENTIAL_RAMP[2],
        SEQUENTIAL_RAMP[3],
        SEQUENTIAL_RAMP[4],
    ]


@pytest.mark.parametrize("top", [1.0, 2.0, 3.0, 4.0, 5.0])
def test_the_largest_bin_is_always_the_last_ramp_entry(top: float) -> None:
    scale = _scale([top])
    assert scale.bins == int(top)
    colors = [scale.color(i) for i in range(1, scale.bins + 1)]
    assert colors == list(SEQUENTIAL_RAMP[MAX_BINS - scale.bins :])
    assert colors[-1] == SEQUENTIAL_RAMP[-1]
    assert len(set(colors)) == scale.bins


def test_fraction_is_the_square_root_of_the_bin_share() -> None:
    scale = _scale([3.0])
    assert [scale.fraction(i) for i in (1, 2, 3)] == pytest.approx(
        [math.sqrt(1 / 3), math.sqrt(2 / 3), 1.0]
    )
    five = _scale([41.0])
    assert [five.fraction(i) for i in range(1, 6)] == pytest.approx(
        [math.sqrt(i / 5) for i in range(1, 6)]
    )
    # area (fraction squared) is proportional to the bin index, not the side
    assert five.fraction(4) ** 2 == pytest.approx(4 * five.fraction(1) ** 2)


@pytest.mark.parametrize("index", [0, 4, -1])
def test_a_bin_outside_the_scale_is_refused(index: int) -> None:
    scale = _scale([3.0])
    with pytest.raises(ValueError, match="bin"):
        scale.color(index)
    with pytest.raises(ValueError, match="bin"):
        scale.fraction(index)


# ---------------------------------------------------------------- cell marks

FOUR = _scale([4.0])  # edges 0, 1, 2, 3, 4: fractions 0.5, 0.7071, 0.866, 1
FIVE = _scale([41.0])
CROSS_ATTRS = " ".join(f'{k}="{v}"' for k, v in ink(STROKE).items())


def _path(d: str, fill: str) -> str:
    return f'<path d="{d}" fill="{fill}"/>'


def test_ink_of_the_absent_cross_is_the_stroke_role() -> None:
    assert CROSS_ATTRS == 'class="ck-s" stroke="#7f7f7f"'


def test_a_bin_square_is_centred_in_the_inset_cell() -> None:
    cell = Rect(100.0, 50.0, 12.0, 12.0)  # inner box 101, 51, 10 x 10
    assert cell_marks([(cell, 1)], FOUR) == [
        _path("M103.5 53.5H108.5V58.5H103.5Z", FOUR.color(1))
    ]
    assert cell_marks([(cell, 4)], FOUR) == [
        _path("M101 51H111V61H101Z", FOUR.color(4))
    ]
    assert cell_marks([(cell, 2)], FOUR) == [
        _path("M102.46 52.46H109.54V59.54H102.46Z", FOUR.color(2))
    ]


def test_a_non_square_cell_gets_a_rectangle_scaled_per_side() -> None:
    cell = Rect(0.0, 0.0, 22.0, 12.0)  # inner 1, 1, 20 x 10; side 0.5 -> 10 x 5
    assert cell_marks([(cell, 1)], FOUR) == [_path("M6 3.5H16V8.5H6Z", FOUR.color(1))]


def test_a_mark_is_never_smaller_than_min_mark() -> None:
    tiny = Rect(0.0, 0.0, 4.0, 4.0)  # inner 2 x 2; 2 * 0.5 = 1 < MIN_MARK
    assert cell_marks([(tiny, 1)], FOUR) == [_path("M1 1H3V3H1Z", FOUR.color(1))]
    smaller = Rect(
        10.0, 20.0, 3.0, 3.0
    )  # inner 1 x 1: the MIN_MARK floor makes the mark overflow it
    assert cell_marks([(smaller, 1)], FOUR) == [
        _path("M10.5 20.5H12.5V22.5H10.5Z", FOUR.color(1))
    ]


def test_zero_cells_are_outlined_squares_with_no_fill() -> None:
    cell = Rect(100.0, 50.0, 12.0, 12.0)
    (mark,) = cell_marks([(cell, 0)], FOUR)
    assert mark == (
        '<path d="M101.5 51.5H110.5V60.5H101.5Z" fill="none" '
        f'stroke="{SEQUENTIAL_RAMP[0]}" stroke-width="1"/>'
    )


def test_absent_cells_are_two_diagonal_strokes_in_the_stroke_ink() -> None:
    cell = Rect(100.0, 50.0, 12.0, 12.0)
    (mark,) = cell_marks([(cell, None)], FOUR)
    assert mark == (
        '<path d="M103.5 53.5L108.5 58.5M103.5 58.5L108.5 53.5" '
        f'{CROSS_ATTRS} fill="none" stroke-width="1"/>'
    )


def test_zero_and_absent_and_the_smallest_bin_differ_in_shape() -> None:
    cell = Rect(0.0, 0.0, 12.0, 12.0)
    marks = {
        name: cell_marks([(cell, value_class)], FOUR)[0]
        for name, value_class in (("bin", 1), ("zero", 0), ("absent", None))
    }
    assert len(set(marks.values())) == 3
    assert "H" in marks["bin"] and 'fill="none"' not in marks["bin"]
    assert "H" in marks["zero"] and 'fill="none"' in marks["zero"]
    assert "L" in marks["absent"] and "H" not in marks["absent"]
    assert "L" not in marks["zero"] and "L" not in marks["bin"]
    # the absent cross is never the zero outline's ink
    assert SEQUENTIAL_RAMP[0] not in marks["absent"]
    assert "ck-s" not in marks["zero"]


def test_one_path_per_non_empty_class_in_the_stated_order() -> None:
    pitch = 12.0

    def rect(i: int) -> Rect:
        return Rect(i * pitch, 0.0, pitch, pitch)

    classes: list[int | None] = [None, 3, 0, 1, None, 3, 0, 5, 1, 3]
    cells = [(rect(i), c) for i, c in enumerate(classes)]
    marks = cell_marks(cells, FIVE)
    # bins 1, 3, 5 ascending, then zero, then absent: five elements, not ten
    assert len(marks) == 5
    assert [m.count("<path") for m in marks] == [1] * 5
    fills = [re.search(r'fill="([^"]+)"', m) for m in marks]
    assert [f.group(1) if f else None for f in fills] == [
        FIVE.color(1),
        FIVE.color(3),
        FIVE.color(5),
        "none",
        "none",
    ]
    assert marks[3].count("M") == 2 and "stroke" in marks[3] and "ck-s" not in marks[3]
    assert marks[4].count("M") == 4 and "ck-s" in marks[4]
    # subpaths keep the order the cells were given within a class
    d3 = re.search(r' d="([^"]+)"', marks[1])
    assert d3 is not None
    lefts = [float(m) for m in re.findall(r"M([\d.]+) ", d3.group(1))]
    assert len(lefts) == 3
    assert lefts == sorted(lefts)
    assert lefts[0] < 1 * pitch + pitch and lefts[2] > 9 * pitch


def test_cells_given_out_of_geometric_order_keep_the_given_order() -> None:
    near, far = Rect(0.0, 0.0, 12.0, 12.0), Rect(120.0, 0.0, 12.0, 12.0)
    (mark,) = cell_marks([(far, 4), (near, 4)], FOUR)
    assert mark == _path("M121 1H131V11H121ZM1 1H11V11H1Z", FOUR.color(4))


def test_an_empty_class_emits_no_element() -> None:
    cell = Rect(0.0, 0.0, 12.0, 12.0)
    assert cell_marks([], FIVE) == []
    only_zero = cell_marks([(cell, 0), (cell, 0)], FIVE)
    assert len(only_zero) == 1 and 'fill="none"' in only_zero[0]
    only_absent = cell_marks([(cell, None)], FIVE)
    assert len(only_absent) == 1 and "ck-s" in only_absent[0]
    bins = cell_marks([(cell, 2)], FIVE)
    assert len(bins) == 1 and 'fill="none"' not in bins[0]


def test_a_scale_without_bins_draws_zero_and_absent_only() -> None:
    none = _scale([0.0, None])
    cell = Rect(0.0, 0.0, 12.0, 12.0)
    marks = cell_marks([(cell, 0), (cell, None)], none)
    assert len(marks) == 2
    assert 'stroke-width="1"' in marks[0] and SEQUENTIAL_RAMP[0] in marks[0]
    assert "ck-s" in marks[1]


def test_a_class_outside_the_scale_is_refused() -> None:
    cell = Rect(0.0, 0.0, 12.0, 12.0)
    with pytest.raises(ValueError, match="class"):
        cell_marks([(cell, 5)], FOUR)
    with pytest.raises(ValueError, match="class"):
        cell_marks([(cell, -1)], FOUR)


# -------------------------------------------------------------------- legend


def _labels(entries: Sequence[LegendEntry]) -> list[str]:
    return [e.label for e in entries]


def test_legend_entries_run_lead_zero_bins_absent() -> None:
    scale = _scale([30.0, 4.0, 11.0], KM)  # edges 0, 10, 20, 30; zero "0"
    entries = legend_entries(scale, has_zero=True, has_absent=True)
    assert _labels(entries) == [
        "distance (km)",
        "0",
        "≤ 10",
        "≤ 20",
        "≤ 30",
        ABSENT_LABEL,
    ]
    assert {e.swatch for e in entries} == {"block"}


@pytest.mark.parametrize(
    ("has_zero", "has_absent", "labels"),
    [
        (False, False, ["load", "≤ 1", "≤ 2", "≤ 3"]),
        (True, False, ["load", "0", "≤ 1", "≤ 2", "≤ 3"]),
        (False, True, ["load", "≤ 1", "≤ 2", "≤ 3", ABSENT_LABEL]),
    ],
)
def test_zero_and_absent_entries_appear_only_when_asked_for(
    has_zero: bool, has_absent: bool, labels: list[str]
) -> None:
    scale = _scale([3.0, 1.0, 2.0])
    entries = legend_entries(scale, has_zero=has_zero, has_absent=has_absent)
    assert _labels(entries) == labels


def test_bin_entries_carry_the_bin_colour() -> None:
    scale = _scale([3.0, 1.0, 2.0])
    entries = legend_entries(scale, has_zero=True, has_absent=True)
    bins = [e for e in entries if e.label.startswith("≤")]
    assert [e.style.color for e in bins] == [scale.color(i) for i in (1, 2, 3)]


def test_a_scale_without_bins_has_lead_and_the_asked_for_entries_only() -> None:
    scale = _scale([0.0, None])
    assert _labels(legend_entries(scale, has_zero=True, has_absent=False)) == [
        "load",
        "0",
    ]
    assert _labels(legend_entries(scale, has_zero=True, has_absent=True)) == [
        "load",
        "0",
        ABSENT_LABEL,
    ]
    assert _labels(legend_entries(scale, has_zero=False, has_absent=True)) == [
        "load",
        ABSENT_LABEL,
    ]


def test_duration_edges_are_one_form_in_the_entries() -> None:
    scale = _scale([1200.0, 5400.0], DURATION)
    entries = legend_entries(scale, has_zero=True, has_absent=False)
    assert _labels(entries) == [
        "moving time (h:mm:ss)",
        "0:00:00",
        "≤ 0:30:00",
        "≤ 1:00:00",
        "≤ 1:30:00",
    ]


def test_a_duration_lead_at_exactly_one_hour_names_the_long_form() -> None:
    scale = _scale([300.0, 3600.0], DURATION)
    entries = legend_entries(scale, has_zero=False, has_absent=False)
    assert entries[0].label == "moving time (h:mm:ss)"
    just_below = _scale([300.0, 3000.0], DURATION)
    assert legend_entries(just_below, has_zero=False, has_absent=False)[0].label == (
        "moving time (m:ss)"
    )


def test_a_short_duration_lead_names_the_m_ss_form() -> None:
    scale = _scale([130.0, 600.0], SECONDS)
    entries = legend_entries(scale, has_zero=False, has_absent=False)
    assert entries[0].label == "elapsed (m:ss)"
    assert entries[1].label == "≤ 2:00"


def test_a_duration_lead_with_no_bins_uses_the_short_form() -> None:
    entries = legend_entries(_scale([0.0], DURATION), has_zero=True, has_absent=False)
    assert _labels(entries) == ["moving time (m:ss)", "0:00"]


def test_non_duration_leads_are_the_plain_axis_title() -> None:
    assert (
        legend_entries(_scale([40.0], PERCENT), has_zero=False, has_absent=False)[
            0
        ].label
        == "share (%)"
    )
    assert (
        legend_entries(_scale([400.0], PACE), has_zero=False, has_absent=False)[0].label
        == "pace (min/km)"
    )
    assert (
        legend_entries(_scale([2.0]), has_zero=False, has_absent=False)[0].label
        == "load"
    )


def _frame(entries: Sequence[LegendEntry], width: int) -> FramePlan:
    return plan_frame(
        width,
        200,
        legend=entries,
        y_label_width=20.0,
        x_label_overhang=10.0,
        has_x_title=False,
        has_y_title=False,
        notes=0,
    )


def _drawn(svg: str) -> tuple[list[str], list[tuple[str, str, str]]]:
    paths = re.findall(r"<path [^>]*/>", svg)
    texts = re.findall(r'<text x="([^"]+)" y="([^"]+)"[^>]*>([^<]*)</text>', svg)
    return paths, texts


@pytest.mark.parametrize("width", [720, 200])
def test_legend_swatches_equal_the_cell_marks_of_a_10px_cell(width: int) -> None:
    scale = _scale([30.0, 4.0, 11.0], KM)
    entries = legend_entries(scale, has_zero=True, has_absent=True)
    plan = _frame(entries, width)
    svg = legend(plan, scale, entries)
    paths, texts = _drawn(svg)
    expected_paths: list[str] = []
    expected_texts: list[tuple[str, str, str]] = []
    classes: list[int | None] = [-1, 0, 1, 2, 3, None]  # -1: the lead, no swatch
    flat = [pair for row in plan.legend_rows for pair in row]
    assert len(flat) == len(entries)
    position = 0
    for r, row in enumerate(plan.legend_rows):
        top = plan.legend_top + 18.0 * r
        for entry, x in row:
            cls = classes[position]
            position += 1
            if cls == -1:
                label_x = x
            else:
                swatch = Rect(x + 5.0, top + 7.0 - 5.0, 10.0, 10.0)
                expected_paths.extend(cell_marks([(swatch, cls)], scale))
                label_x = x + 24.0
            expected_texts.append((f"{label_x:g}", f"{top + 11.0:g}", entry.label))
    assert paths == expected_paths
    assert len(paths) == 5  # the lead has no swatch
    assert [(a, b, c) for a, b, c in texts] == expected_texts
    if width == 200:
        assert len(plan.legend_rows) > 1
    assert svg.startswith('<g class="ck-legend">') and svg.endswith("</g>")


def test_legend_swatches_are_drawn_per_class_with_the_right_marks() -> None:
    scale = _scale([30.0, 4.0, 11.0], KM)
    entries = legend_entries(scale, has_zero=True, has_absent=True)
    plan = _frame(entries, 720)
    paths, _ = _drawn(legend(plan, scale, entries))
    assert 'fill="none"' in paths[0] and SEQUENTIAL_RAMP[0] in paths[0]  # zero
    assert [re.search(r'fill="(#[0-9a-f]+)"', p) is not None for p in paths[1:4]] == [
        True
    ] * 3
    assert [re.search(r'fill="([^"]+)"', p).group(1) for p in paths[1:4]] == [  # type: ignore[union-attr]
        scale.color(1),
        scale.color(2),
        scale.color(3),
    ]
    assert "ck-s" in paths[4] and "L" in paths[4]  # absent cross
    # the bin swatches grow in size: widths strictly increase along the bins
    widths = []
    for p in paths[1:4]:
        d = re.search(r' d="([^"]+)"', p)
        assert d is not None
        left, _top, right = (
            float(n)
            for n in re.match(r"M([\d.]+) ([\d.]+)H([\d.]+)", d.group(1)).groups()  # type: ignore[union-attr]
        )
        widths.append(right - left)
    assert widths == sorted(widths) and len(set(widths)) == 3


def test_legend_labels_use_the_text_ink_and_the_swatch_text_gap() -> None:
    scale = _scale([2.0])
    entries = legend_entries(scale, has_zero=False, has_absent=False)
    plan = _frame(entries, 720)
    svg = legend(plan, scale, entries)
    for el_text in re.findall(r"<text [^>]*>", svg):
        assert 'class="ck-t"' in el_text and 'fill="#7f7f7f"' in el_text
        assert 'font-size="11"' in el_text
    assert ink(TEXT) == {"class": "ck-t", "fill": "#7f7f7f"}


def test_a_plan_without_legend_rows_draws_nothing() -> None:
    scale = _scale([2.0])
    plan = _frame([], 720)
    assert legend(plan, scale, ()) == ""


def test_a_legend_that_does_not_match_its_plan_is_refused() -> None:
    scale = _scale([2.0])
    entries = legend_entries(scale, has_zero=False, has_absent=False)
    plan = _frame(entries, 720)
    with pytest.raises(ValueError, match="entries"):
        legend(plan, scale, entries[:-1])


@pytest.mark.parametrize(
    ("built_for", "drawn_with", "zero_and_absent"),
    [([2.0], [4.0], False), ([4.0], [2.0], True)],
    ids=["fewer entries than the scale has bins", "more entries than it has"],
)
def test_a_legend_whose_entries_belong_to_another_scale_is_refused(
    built_for: list[float], drawn_with: list[float], zero_and_absent: bool
) -> None:
    entries = legend_entries(
        _scale(built_for), has_zero=zero_and_absent, has_absent=zero_and_absent
    )
    plan = _frame(entries, 720)
    assert _scale(built_for).bins != _scale(drawn_with).bins  # precondition
    with pytest.raises(ValueError, match="not those of legend_entries"):
        legend(plan, _scale(drawn_with), entries)


def test_legend_entry_labels_are_cleaned_and_escaped() -> None:
    col = column("odd", label="a<b & c\x01")
    scale = _scale([2.0], col)
    entries = legend_entries(scale, has_zero=False, has_absent=False)
    plan = _frame(entries, 720)
    svg = legend(plan, scale, entries)
    assert "a&lt;b &amp; c�" in svg
    assert "\x01" not in svg


# ----------------------------------------------------------- negative_problem


def _bound(
    columns: Sequence[Column],
    rows: Sequence[Sequence[Value]],
    channels: Mapping[str, str],
) -> BoundChart:
    by_name = {c.name: c for c in columns}
    spec = KindSpec(
        name="heatmap",
        description="A test kind.",
        output=Output.SVG,
        channels=tuple(
            ChannelSpec(name, tuple(ValueKind), False, "A channel.")
            for name in channels
        ),
        options=(),
        bound=MarkBound(2000, "rows", OverBound.REFUSE, "rule"),
        max_series=8,
        draw=lambda chart: "<svg/>",
    )
    return BoundChart(
        request=chart_request("heatmap", channels=channels),
        spec=spec,
        columns={ch: by_name[name] for ch, name in channels.items()},
        all_columns=tuple(columns),
        options={},
        rows=tuple(tuple(r) for r in rows),
    )


NOTE = column("note", ValueKind.CATEGORY)


def test_negative_problem_names_the_first_row_and_the_count() -> None:
    rows = [("a", None), ("b", 4.0), ("c", -1.5), ("d", 0.0), ("e", -7.0), ("f", 2.0)]
    chart = _bound([NOTE, column("load")], rows, {"value": "load"})
    (problem,) = negative_problem(chart, "value")
    assert problem.as_dict() == {
        "ref": "c1",
        "kind": "heatmap",
        "code": "negative_value",
        "message": (
            "load has a negative value at row 2; heatmap shades values from zero up."
        ),
        "fix": (
            "Use a line or bar chart for signed values, "
            "or select a value that cannot be negative."
        ),
        "channel": "value",
        "column": "load",
        "option": None,
        "row": 2,
        "rows": 2,
        "accepted": [],
    }
    assert problem.code is ProblemCode.NEGATIVE_VALUE


def test_negative_problem_reads_durations_in_seconds() -> None:
    rows = [("a", timedelta(seconds=5)), ("b", timedelta(seconds=-3))]
    chart = _bound([NOTE, DURATION], rows, {"value": "moving_time"})
    (problem,) = negative_problem(chart, "value")
    assert (problem.row, problem.rows, problem.column) == (1, 1, "moving_time")
    assert problem.message.startswith("moving time has a negative value at row 1;")


def test_negative_problem_is_empty_for_zero_absent_and_positive() -> None:
    rows = [("a", 0.0), ("b", None), ("c", 3.0), ("d", -0.0)]
    chart = _bound([NOTE, column("load")], rows, {"value": "load"})
    assert negative_problem(chart, "value") == ()


def test_negative_problem_ignores_an_unbound_channel() -> None:
    chart = _bound([NOTE, column("load")], [("a", -1.0)], {"x": "note"})
    assert negative_problem(chart, "value") == ()


@pytest.mark.parametrize("values", [[3.0, 1.0, 2.0, 0.0], [0.0, None]])
@pytest.mark.parametrize("has_zero", [False, True])
@pytest.mark.parametrize("has_absent", [False, True])
def test_legend_derives_each_swatch_class_from_the_entries(
    values: list[float | None], has_zero: bool, has_absent: bool
) -> None:
    scale = _scale(values)
    entries = legend_entries(scale, has_zero=has_zero, has_absent=has_absent)
    plan = _frame(entries, 720)
    paths, _ = _drawn(legend(plan, scale, entries))
    classes: list[int | None] = []
    if has_zero:
        classes.append(0)
    classes.extend(range(1, scale.bins + 1))
    if has_absent:
        classes.append(None)
    flat = [pair for row in plan.legend_rows for pair in row][1:]
    expected: list[str] = []
    for (_, x), cls in zip(flat, classes, strict=True):
        swatch = Rect(x + 5.0, plan.legend_top + 7.0 - 5.0, 10.0, 10.0)
        expected.extend(cell_marks([(swatch, cls)], scale))
    assert paths == expected


def test_the_absent_entry_colour_is_the_ink_its_swatch_draws() -> None:
    scale = _scale([2.0])
    absent = legend_entries(scale, has_zero=False, has_absent=True)[-1]
    assert absent.style.color == ink(STROKE)["stroke"] == "#7f7f7f"
    (cross,) = cell_marks([(Rect(0.0, 0.0, 12.0, 12.0), None)], scale)
    assert f'stroke="{absent.style.color}"' in cross


def test_legend_offsets_match_frame_legend() -> None:
    scale = _scale([1.0])  # one bin: its square fills the inset cell
    entries = legend_entries(scale, has_zero=False, has_absent=False)
    plan = _frame(entries, 720)
    theirs = frame_legend(plan)
    ours = legend(plan, scale, entries)
    text_re = r'<text x="([^"]+)" y="([^"]+)"'
    their_text = [(float(x), y) for x, y in re.findall(text_re, theirs)]
    our_text = [(float(x), y) for x, y in re.findall(text_re, ours)]
    assert [y for _, y in their_text] == [y for _, y in our_text]
    # frame.legend gives the lead a swatch slot; cells.legend draws it bare
    assert their_text[0][0] - our_text[0][0] == 24.0
    assert their_text[1:] == our_text[1:]
    # frame's block swatch of the bin entry and the cell swatch share a centre
    blocks = re.findall(r'<rect x="([^"]+)" y="([^"]+)" width="10" height="10"', theirs)
    block_x, block_y = (float(v) for v in blocks[1])
    path = re.search(r' d="M([\d.]+) ([\d.]+)H([\d.]+)V([\d.]+)', ours)
    assert path is not None
    left, top, right, bottom = (float(v) for v in path.groups())
    assert (left + right) / 2 == block_x + 5.0
    assert (top + bottom) / 2 == block_y + 5.0
