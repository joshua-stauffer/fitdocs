"""The histogram kind: binning rules, the count axis, refusals and goldens.

Requirements 6.5, 11.2, 14.4, 14.5, 18.1 and 18.3.

Run ``uv run python -m tests.render.charts.kit.test_histogram`` to (re)write the
goldens under ``golden/histogram/``; a pytest run never writes them.
"""

from __future__ import annotations

import math
import re
from collections.abc import Sequence
from datetime import timedelta
from fractions import Fraction
from xml.etree import ElementTree

import pytest

from fitdocs.render.charts.kit.data import ChartData, Value, ValueKind
from fitdocs.render.charts.kit.kinds.histogram import (
    KIND,
    _histogram,
    _shape,
    _sturges,
)
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
SPORT = column("sport", ValueKind.CATEGORY)
DISTANCE = column("distance_km", unit="km")
CHANNELS = {"x": "distance_km"}


def _data(values: Sequence[Value]) -> ChartData:
    """Columns ``sport, distance_km``: the bound column is not column 0."""
    return chart_data([SPORT, DISTANCE], [("run", v) for v in values])


def _request(
    options: dict[str, OptionValue] | None = None,
    *,
    title: str = "Distances",
    ref: str = "h1",
) -> ChartRequest:
    return chart_request(
        "histogram", ref=ref, title=title, channels=CHANNELS, options=options
    )


def _svg(values: Sequence[Value], options: dict[str, OptionValue] | None = None) -> str:
    request = chart_request(
        "histogram", title="Distances", channels=CHANNELS, options=options
    )
    return render_case(KIND, request, _data(values)).text


def _bins(
    values: list[float],
    *,
    bins: int | None = None,
    bin_width: float | None = None,
    duration: bool = False,
) -> tuple[tuple[float, ...], tuple[int, ...]]:
    result = _histogram(values, duration=duration, bins=bins, bin_width=bin_width)
    return result.edges, result.counts


# --- the declaration -------------------------------------------------------------


def test_kind_declaration() -> None:
    assert KIND.name == "histogram"
    assert KIND.description == "Counts of one numeric column in equal-width bins"
    assert KIND.output is Output.SVG
    assert KIND.channels == (
        ChannelSpec(
            "x",
            (ValueKind.NUMBER, ValueKind.DURATION),
            True,
            "The values to count.",
        ),
    )
    assert [
        (o.name, o.type, o.default, o.minimum, o.maximum) for o in KIND.options
    ] == [
        ("bins", OptionType.INTEGER, None, 1, 100),
        ("bin_width", OptionType.NUMBER, None, None, None),
        ("width", OptionType.INTEGER, 720, 320, 1600),
        ("height", OptionType.INTEGER, 280, 160, 1200),
    ]
    assert all(isinstance(o, OptionSpec) for o in KIND.options)
    assert KIND.bound == MarkBound(
        100,
        "bins",
        OverBound.REDUCE,
        "Any number of values is binned; a binning that yields more than 100 "
        "bins is refused.",
    )
    assert KIND.max_series is None
    assert KIND.uses_all_columns is False


# --- the three binning rules -------------------------------------------------------


def test_sturges_bin_count() -> None:
    assert [_sturges(n) for n in (1, 2, 7, 8, 9, 1000)] == [1, 2, 4, 4, 5, 11]


def test_sturges_is_clamped_at_50() -> None:
    assert _sturges(2**49) == 50
    assert _sturges(2**49 + 1) == 50
    assert _sturges(2**60) == 50


def test_inner_edge_value_is_in_the_upper_bin_and_the_maximum_in_the_last() -> None:
    values = [4.0, 0.0, 6.0, 2.0, 5.0, 3.0, 1.0]
    edges, counts = _bins(values)
    assert edges == (0.0, 2.0, 4.0, 6.0)
    assert counts == (2, 2, 3)


def test_default_bin_count_follows_sturges_over_the_range() -> None:
    values = [3.0, 0.0, 8.0, 1.5, 6.0, 4.5, 7.0]
    edges, counts = _bins(values)
    assert edges == (0.0, 2.0, 4.0, 6.0, 8.0)
    assert counts == (2, 1, 1, 3)


def test_maximum_on_an_edge_does_not_add_an_empty_bin() -> None:
    edges, counts = _bins([4.8, 5.4, 5.1])
    assert edges == (4.8, 5.0, 5.2, 5.4)
    assert counts == (1, 1, 1)


def test_bin_width_one_tenth_over_0_3_to_10_3_is_exactly_100_bins() -> None:
    values = [0.3, 10.3]
    assert _shape(values, duration=False, bins=None, bin_width=0.1).count == 100
    edges, counts = _bins(values, bin_width=0.1)
    assert len(counts) == 100 and edges[0] == 0.3 and edges[-1] == 10.3
    assert _bars(_svg(values, {"bin_width": 0.1}))


def test_negative_decimal_minimum_keeps_clean_edges() -> None:
    assert _bins([-2.7, -2.4], bin_width=0.1) == (
        (-2.7, -2.6, -2.5, -2.4),
        (1, 0, 1),
    )


_TENTHS = [round(i / 10, 1) for i in (-27, -3, 0, 3, 7, 13, 21, 38, 55)]
_WIDTHS = [0.05, 0.1, 0.2, 0.25, 0.3, 0.5, 2.5]


@pytest.mark.parametrize("width", _WIDTHS)
@pytest.mark.parametrize("rule", ["default", "bin_width"])
def test_extremes_sit_in_the_first_and_closed_last_bin(rule: str, width: float) -> None:
    checked = 0
    for low in _TENTHS:
        for span in (0.1, 0.4, 1.0, 2.3, 4.9):
            high = round(low + span, 1)
            edges, counts = _bins(
                [low, high], bin_width=width if rule == "bin_width" else None
            )
            assert edges[0] <= low < edges[1], (low, high, edges)
            assert edges[-2] < high <= edges[-1], (low, high, edges)
            assert counts[0] >= 1 and counts[-1] >= 1
            assert sum(counts) == 2
            checked += 1
    assert checked == len(_TENTHS) * 5


def test_default_first_edge_is_a_multiple_of_the_step() -> None:
    edges, counts = _bins([11.0, 13.0, 12.5, 17.5])
    assert edges == (10.0, 15.0, 20.0)
    assert counts == (3, 1)


def test_bins_option_splits_the_range_exactly() -> None:
    values = [10.0, 12.5, 11.0, 19.0, 14.5, 17.0, 10.5, 16.75]
    edges, counts = _bins(values, bins=4)
    assert edges == (10.0, 12.25, 14.5, 16.75, 19.0)
    assert counts == (3, 1, 1, 3)


def test_bin_width_option_starts_at_a_multiple_of_the_width() -> None:
    edges, counts = _bins([3.3, 0.7, 5.1, 2.0, 4.9, 6.0], bin_width=2.0)
    assert edges == (0.0, 2.0, 4.0, 6.0)
    assert counts == (1, 2, 3)


def test_bin_width_edges_are_decimal_clean() -> None:
    edges, counts = _bins([0.3, 0.45, 0.7], bin_width=0.1)
    assert edges == (0.3, 0.4, 0.5, 0.6, 0.7)
    assert counts == (1, 1, 0, 1)


def test_bin_width_value_just_below_an_edge_stays_below_it() -> None:
    # 0.8999999999999999 / 0.3 divides to 3.0, yet the value is below 0.9.
    value = 0.8999999999999999
    assert value / 0.3 == 3.0 and value < 0.9
    edges, counts = _bins([value, 1.4], bin_width=0.3)
    assert edges == (0.6, 0.9, 1.2, 1.5)
    assert counts == (1, 0, 1)


def test_bins_option_keeps_the_extremes_exactly() -> None:
    low = 0.1234567890123456
    edges, counts = _bins([low, 1.0], bins=2)
    assert edges[0] == low and edges[-1] == 1.0
    assert counts == (1, 1)


def test_all_equal_values_make_one_bin_of_a_nice_width() -> None:
    assert _bins([42.0, 42.0, 42.0]) == ((40.0, 45.0), (3,))
    assert _bins([7.0]) == ((7.0, 8.0), (1,))
    assert _bins([0.0, 0.0]) == ((0.0, 1.0), (2,))
    assert _bins([-3.0]) == ((-3.0, -2.5), (1,))


def test_all_equal_values_ignore_the_bin_options() -> None:
    assert _bins([42.0, 42.0], bins=5) == ((40.0, 45.0), (2,))
    assert _bins([42.0, 42.0], bin_width=0.5) == ((40.0, 45.0), (2,))


def test_duration_values_bin_on_the_duration_ladder() -> None:
    values = [20.0, 95.0, 250.0, 61.0, 310.0, 130.0, 400.0, 15.0]
    edges, counts = _bins(values, duration=True)
    assert edges == (0.0, 120.0, 240.0, 360.0, 480.0)
    assert counts == (4, 1, 2, 1)
    plain, _ = _bins(values, duration=False)
    assert plain == (0.0, 100.0, 200.0, 300.0, 400.0)


def test_all_equal_duration_uses_the_duration_ladder() -> None:
    assert _bins([90.0], duration=True) == ((90.0, 100.0), (1,))
    assert _bins([90.0], duration=False) == ((90.0, 100.0), (1,))
    assert _bins([95.0], duration=True) == ((90.0, 100.0), (1,))


# --- the bound ---------------------------------------------------------------------


def test_bin_width_producing_100_bins_renders() -> None:
    result = _histogram([0.0, 100.0], duration=False, bins=None, bin_width=1.0)
    assert len(result.counts) == 100
    assert _shape([0.0, 100.0], duration=False, bins=None, bin_width=1.0).count == 100
    assert "<rect" in _svg([0.0, 100.0], {"bin_width": 1.0})


def test_bin_width_producing_101_bins_refuses() -> None:
    assert _shape([0.0, 101.0], duration=False, bins=None, bin_width=1.0).count == 101
    request = _request({"bin_width": 1})
    assert problems_of(KIND, request, _data([0.0, 101.0])) == (
        ChartProblem(
            ref="h1",
            kind="histogram",
            code=ProblemCode.OVER_BOUND,
            message="histogram draws at most 100 bins; this binning yields 101.",
            fix=(
                "Raise 'bin_width' so the binning yields at most 100 bins, or "
                "limit the range of the values."
            ),
            option="bin_width",
            rows=101,
        ),
    )


def test_bin_width_aligns_the_bin_count_to_the_first_edge() -> None:
    # 0.5 .. 100.5 spans 100 widths but starts inside the bin [0, 1): 101 bins.
    request = _request({"bin_width": 1})
    problems = problems_of(KIND, request, _data([0.5, 100.5]))
    assert [p.rows for p in problems] == [101]


def test_exact_count_is_taken_from_the_aligned_first_edge_when_huge() -> None:
    request = _request({"bin_width": 1})
    (problem,) = problems_of(KIND, request, _data([0.5, 10_000_000.5]))
    assert problem.rows == 10_000_001


def test_absurdly_small_bin_width_is_refused_with_the_exact_count() -> None:
    width = 1e-320
    expected = math.ceil(Fraction(1.0) / Fraction(width))
    assert expected > 10**300
    request = _request({"bin_width": width})
    (problem,) = problems_of(KIND, request, _data([0.0, 1.0]))
    assert problem.code is ProblemCode.OVER_BOUND
    assert problem.rows == expected


def test_bins_100_renders_and_default_never_exceeds_the_bound() -> None:
    assert _svg([0.0, 3.0, 99.0], {"bins": 100})
    assert _svg([float(i) for i in range(1000)])


# --- request-level refusals ----------------------------------------------------------


def test_bins_and_bin_width_together_are_refused() -> None:
    request = _request({"bins": 4, "bin_width": 2.0})
    problems = problems_of(KIND, request, _data([1.0, 2.0]))
    assert problems == (
        ChartProblem(
            ref="h1",
            kind="histogram",
            code=ProblemCode.OPTION_CONFLICT,
            message="Options 'bins' and 'bin_width' cannot both be set.",
            fix="Set either 'bins' or 'bin_width', not both.",
            option="bin_width",
            accepted=("bins", "bin_width"),
        ),
    )


def test_conflict_and_non_positive_width_are_both_reported() -> None:
    request = _request({"bins": 4, "bin_width": 0})
    problems = problems_of(KIND, request, _data([1.0, 2.0]))
    assert [(p.code, p.option) for p in problems] == [
        (ProblemCode.OPTION_CONFLICT, "bin_width"),
        (ProblemCode.OPTION_VALUE, "bin_width"),
    ]


def test_either_option_alone_is_accepted() -> None:
    assert _svg([1.0, 5.0], {"bins": 4})
    assert _svg([1.0, 5.0], {"bin_width": 2.0})


@pytest.mark.parametrize("width", [0, 0.0, -1.5])
def test_bin_width_must_be_positive(width: float) -> None:
    request = _request({"bin_width": width})
    assert problems_of(KIND, request, _data([1.0, 2.0])) == (
        ChartProblem(
            ref="h1",
            kind="histogram",
            code=ProblemCode.OPTION_VALUE,
            message=(
                "Option 'bin_width' does not accept this value; it takes a "
                "number greater than zero."
            ),
            fix="Set 'bin_width' to a number greater than zero.",
            option="bin_width",
        ),
    )


def test_a_tiny_positive_bin_width_is_not_mistaken_for_zero() -> None:
    request = _request({"bin_width": 5e-324})
    (problem,) = problems_of(KIND, request, _data([0.0, 1.0]))
    assert problem.code is ProblemCode.OVER_BOUND


def test_x_must_be_a_number_or_duration() -> None:
    request = chart_request("histogram", channels={"x": "sport"})
    (problem,) = problems_of(KIND, request, _data([1.0]))
    assert problem.code is ProblemCode.CHANNEL_KIND
    assert problem.accepted == ("distance_km",)


# --- what is drawn -------------------------------------------------------------------


def _root(svg: str) -> ElementTree.Element:
    return ElementTree.fromstring(svg)


def _bars(svg: str) -> list[tuple[float, float, float, float]]:
    """``(x, y, width, height)`` of every rect in the marks group."""
    (marks,) = [g for g in _root(svg).iter(f"{SVG}g") if g.get("class") == "ck-marks"]
    return [
        (
            float(r.get("x", "nan")),
            float(r.get("y", "nan")),
            float(r.get("width", "nan")),
            float(r.get("height", "nan")),
        )
        for r in marks.iter(f"{SVG}rect")
    ]


def _axis_labels(svg: str) -> list[list[str]]:
    groups = [g for g in _root(svg).iter(f"{SVG}g") if g.get("class") == "ck-axis"]
    return [["".join(t.itertext()) for t in g.iter(f"{SVG}text")] for g in groups]


def test_bar_heights_follow_the_counts_and_zero_counts_draw_nothing() -> None:
    # bins=3 over 0..9 gives edges 0, 3, 6, 9 and counts 3, 0, 2.
    bars = _bars(_svg([0.0, 1.0, 2.0, 9.0, 8.0], {"bins": 3}))
    assert len(bars) == 2
    assert bars[0][3] / bars[1][3] == pytest.approx(1.5)
    assert bars[0][0] < bars[1][0]
    assert bars[0][1] + bars[0][3] == pytest.approx(bars[1][1] + bars[1][3])
    assert bars[1][0] - (bars[0][0] + bars[0][2]) > bars[0][2]


def test_contiguous_bins_are_one_pixel_apart() -> None:
    bars = _bars(_svg([0.0, 1.0, 3.5, 5.0, 4.0, 2.5], {"bins": 3}))
    assert len(bars) == 3
    assert len({round(b[2], 6) for b in bars}) == 1
    for left, right in zip(bars, bars[1:], strict=False):
        assert right[0] - (left[0] + left[2]) == pytest.approx(1.0, abs=0.02)


def test_absent_x_rows_are_noted_and_zero_is_a_value() -> None:
    svg = _svg([3.0, None, 0.0, 1.0, 9.0, 2.0, 8.0, None, 0.5])
    assert "Not drawn: 2 rows without x." in svg
    assert svg.count("Not drawn: 2 rows without x.") == 2  # the note and the <desc>
    bars = _bars(svg)
    # seven present values: Sturges k = 4, step 5 -> bins [0, 5) and [5, 10].
    assert len(bars) == 2
    assert bars[0][3] / bars[1][3] == pytest.approx(5 / 2)


def test_one_absent_row_uses_the_singular_note() -> None:
    assert "Not drawn: 1 row without x." in _svg([1.0, None, 2.0])


def test_no_note_when_every_row_is_drawn() -> None:
    assert "Not drawn" not in _svg([1.0, 2.0, 3.0])


def test_count_axis_includes_zero_and_has_whole_number_ticks() -> None:
    # the smallest count is 1, so zero is on the axis only because it is included.
    for height in (280, 1200):
        svg = _svg(
            [4.4, 0.0, 9.6, 2.8, 7.1, 5.2, 1.3, 3.7, 6.0, 4.9],
            {"height": height},
        )
        _, y_labels = _axis_labels(svg)
        counts = y_labels[:-1]
        assert counts[0] == "0"
        assert all(re.fullmatch(r"\d+", label) for label in counts), counts
        assert y_labels[-1] == "Count"


def test_x_axis_is_titled_with_the_columns_unit() -> None:
    x_labels, _ = _axis_labels(_svg([1.0, 5.0, 3.0]))
    assert x_labels[-1] == "distance (km)"


def test_duration_column_is_titled_in_clock_form_and_binned_in_seconds() -> None:
    seconds = [20, 95, 250, 61, 310, 130, 400, 15]
    data = chart_data(
        [SPORT, column("elapsed", ValueKind.DURATION)],
        [("run", timedelta(seconds=s)) for s in seconds],
    )
    request = chart_request("histogram", channels={"x": "elapsed"})
    svg = render_case(KIND, request, data).text
    x_labels, _ = _axis_labels(svg)
    assert x_labels[-1] == "elapsed (m:ss)"
    assert "0:00" in x_labels
    # edges 0, 120, 240, 360, 480 s: four bars with counts 4, 1, 2, 1.
    heights = [b[3] for b in _bars(svg)]
    assert [round(h / heights[1]) for h in heights] == [4, 1, 2, 1]


def test_description_names_the_ranges_and_the_row_counts() -> None:
    svg = _svg([4.5, None, 0.0, 9.5, 2.0])
    desc = _root(svg).find(f"{SVG}desc")
    assert desc is not None
    assert desc.text == (
        "Histogram chart: Distances. x: distance (km). 5 rows. "
        "Not drawn: 1 row without x. "
        "distance (km) from 0.0 km to 9.5 km; Count from 1 to 3."
    )


def _duration_desc(seconds: list[int]) -> str:
    data = chart_data(
        [SPORT, column("elapsed", ValueKind.DURATION)],
        [("run", timedelta(seconds=s)) for s in seconds],
    )
    request = chart_request("histogram", channels={"x": "elapsed"})
    desc = _root(render_case(KIND, request, data).text).find(f"{SVG}desc")
    assert desc is not None and desc.text is not None
    return desc.text


def test_duration_description_uses_the_axis_form() -> None:
    short = _duration_desc([1500, 2700, 1800, 2100])
    assert "elapsed (m:ss) from 25:00 to 45:00;" in short
    long = _duration_desc([1500, 5400, 1800, 2100])
    assert "elapsed (h:mm:ss) from 0:25:00 to 1:30:00;" in long


def test_count_range_follows_the_smallest_and_largest_count() -> None:
    with_empty = _root(_svg([0.0, 1.0, 2.0, 9.0, 8.0], {"bins": 3}))
    desc = with_empty.find(f"{SVG}desc")
    assert desc is not None and desc.text is not None
    assert desc.text.endswith("Count from 0 to 3.")
    no_empty = _root(_svg([0.0, 1.0, 2.0, 9.0, 8.0, 5.0], {"bins": 3}))
    desc = no_empty.find(f"{SVG}desc")
    assert desc is not None and desc.text is not None
    assert desc.text.endswith("Count from 1 to 3.")


def _render_x(
    name: str,
    unit: str | None,
    seconds: list[float],
    options: dict[str, OptionValue] | None = None,
) -> str:
    data = chart_data([SPORT, column(name, unit=unit)], [("run", v) for v in seconds])
    request = chart_request(
        "histogram", title="Distances", channels={"x": name}, options=options
    )
    return render_case(KIND, request, data).text


def _heights(svg: str) -> list[float]:
    bars = _bars(svg)
    return [round(b[3] / min(x[3] for x in bars), 2) for b in bars]


def test_number_column_in_seconds_describes_in_the_axis_clock_form() -> None:
    svg = _render_x("elapsed_s", "s", [1500, 3500])
    desc = _root(svg).find(f"{SVG}desc")
    assert desc is not None
    assert desc.text == (
        "Histogram chart: Distances. x: elapsed (h:mm:ss). 2 rows. "
        "elapsed (h:mm:ss) from 0:25:00 to 0:58:20; Count from 1 to 1."
    )


def test_number_column_in_seconds_bins_on_the_duration_ladder() -> None:
    # duration ladder: step 600, edges 1200..3000, counts 1, 2, 1;
    # the decimal ladder would give step 500 and counts 2, 1, 1.
    svg = _render_x("elapsed_s", "s", [1500, 2700, 1800, 2100])
    assert _heights(svg) == [1.0, 2.0, 1.0]


def test_pace_column_bins_on_the_duration_ladder() -> None:
    # step 30, edges 240..330, counts 2, 2, 3; the decimal ladder gives five bins.
    svg = _render_x("pace", "s_per_km", [250, 290, 305, 330, 271, 262, 318])
    assert _heights(svg) == [1.0, 1.0, 1.5]


def test_bars_narrower_than_three_pixels_touch() -> None:
    svg = _render_x(
        "distance_km",
        "km",
        [0.0, 100.0, 5.0, 50.0, 1.0, 2.0],
        {"bin_width": 1, "width": 320},
    )
    bars = _bars(svg)
    first, second, third = bars[:3]
    assert first[2] < 3.0
    assert second[0] - (first[0] + first[2]) == pytest.approx(0.0, abs=0.02)
    assert third[0] - (second[0] + second[2]) == pytest.approx(0.0, abs=0.02)


def test_chart_is_the_requested_size() -> None:
    svg = _svg([1.0, 2.0], {"width": 480, "height": 300})
    root = _root(svg)
    assert (root.get("width"), root.get("height")) == ("480", "300")
    assert _root(_svg([1.0, 2.0])).get("height") == "280"


def test_no_data_forms() -> None:
    empty = _svg([])
    assert "No data" in empty and "None of the" not in empty
    assert _root(empty).get("height") == "280"
    absent = _svg([None, None, None], {"height": 300})
    assert "None of the 3 rows has a value to draw." in absent
    assert _root(absent).get("height") == "300"


def test_100000_values_are_binned_not_refused() -> None:
    values: list[Value] = [float((i * 7919) % 10007) / 10.0 for i in range(100_000)]
    svg = _svg(values)
    bars = _bars(svg)
    assert 0 < len(bars) <= 50
    assert len(svg) < 20_000
    assert "100000 rows" in svg


def test_counts_sum_to_the_number_of_present_values() -> None:
    values = [float((i * 31) % 97) for i in range(500)]
    result = _histogram(values, duration=False, bins=None, bin_width=None)
    assert sum(result.counts) == 500
    assert len(result.edges) == len(result.counts) + 1


# --- goldens ------------------------------------------------------------------

TYPICAL = [4.4, 0.0, None, 9.6, 2.8, 7.1, 5.2, 1.3, 3.7, None, 6.0, 4.9]
LONG_LABEL = column(
    "distance_of_the_longest_steady_aerobic_efforts_of_the_whole_block_km",
    unit="km",
)


def _case(
    name: str,
    values: Sequence[Value],
    *,
    options: dict[str, OptionValue] | None = None,
    title: str = "Run distances",
) -> Case:
    return Case(
        name,
        chart_request(
            "histogram", ref=name, title=title, channels=CHANNELS, options=options
        ),
        _data(values),
    )


_AT_BOUND = [float(v) for v in (0, 100, 37, 38, 38, 12, 90, 91, 91, 91, 55, 56, 8)]

CASES: tuple[Case, ...] = (
    _case("typical", TYPICAL),
    _case("empty", []),
    _case("all_absent", [None, None, None]),
    _case("single", [42.0]),
    _case(
        "negative",
        [-12.5, -3.0, 4.0, -7.5, 0.0, 9.0, -1.5, -8.0, 2.5, -4.0],
    ),
    Case(
        "long_labels",
        chart_request(
            "histogram",
            ref="long_labels",
            title="A very long chart title that keeps going well past the width "
            "of the chart so that it must be cut short with an ellipsis",
            channels={"x": LONG_LABEL.name},
        ),
        chart_data(
            [SPORT, LONG_LABEL],
            [("run", v) for v in (4.4, 0.0, 9.6, 2.8, 7.1, 5.2, 1.3, 3.7, 6.0)],
        ),
    ),
    _case("at_bound", list(_AT_BOUND), options={"bin_width": 1}),
    _case(
        "bins",
        [10.0, 12.5, 11.0, 19.0, 14.5, 17.0, 10.5, 16.75, 13.0],
        options={"bins": 4, "height": 480},
    ),
    _case(
        "bin_width",
        [3.3, 0.7, 5.1, 2.0, 4.9, 6.0, 2.4, 0.3, 3.9],
        options={"bin_width": 0.5},
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
        "bins",
        "bin_width",
    ]


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.name)
def test_golden(case: Case) -> None:
    rendered = render_case(KIND, case.request, case.data)
    assert rendered.kind == "histogram"
    assert rendered.output is Output.SVG
    assert_golden(golden_path("histogram", case.name, "svg"), rendered.text)


def test_long_labels_case_is_shortened_with_an_ellipsis() -> None:
    case = next(c for c in CASES if c.name == "long_labels")
    assert "…" in render_case(KIND, case.request, case.data).text


def test_at_bound_case_has_exactly_100_bins() -> None:
    assert _shape(_AT_BOUND, duration=False, bins=None, bin_width=1.0).count == 100


def test_typical_case_has_absent_zero_and_unsorted_values() -> None:
    values = [v for v in TYPICAL if v is not None]
    assert 0.0 in values and None in TYPICAL
    assert values != sorted(values)
    assert (
        max(_histogram(values, duration=False, bins=None, bin_width=None).counts) == 3
    )


def _assert_inside(svg: str) -> None:
    root = _root(svg)
    width = float(root.get("width", "nan"))
    texts = list(root.iter(f"{SVG}text"))
    assert texts
    for node in texts:
        content = "".join(node.itertext())
        x = float(node.get("x", "nan"))
        span = text_width(content, float(node.get("font-size", "nan")))
        anchor = node.get("text-anchor", "start")
        left = {"start": x, "middle": x - span / 2, "end": x - span}[anchor]
        assert left >= 8.0 - 1e-9, content
        assert left + span <= width - 4.0 + 1e-9, content


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.name)
def test_every_text_stays_inside_the_chart(case: Case) -> None:
    _assert_inside(render_case(KIND, case.request, case.data).text)


def test_wide_first_and_last_tick_labels_stay_inside_the_chart() -> None:
    svg = _svg([100000.0, 100300.0, 100050.0, 100220.0])
    labels = [t for g in _axis_labels(svg)[:1] for t in g]
    assert labels[0] == "100000"
    _assert_inside(svg)


def test_no_stale_goldens() -> None:
    directory = golden_path("histogram", "x", "svg").parent
    on_disk = sorted(path.name for path in directory.iterdir())
    assert on_disk == sorted(f"{case.name}.svg" for case in CASES)


def main() -> None:
    for case in CASES:
        text = render_case(KIND, case.request, case.data).text
        write_golden(golden_path("histogram", case.name, "svg"), text)


if __name__ == "__main__":
    main()
