"""Behavioral + golden tests for the calendar-axis multi-series chart.

Exercises :mod:`fitdocs.render.charts.calendar` (Req 3.8, 5.2, 5.3, 5.4, 5.5):
the training-history chart drawing fitness, fatigue and form across the whole
archive span on one shared, absolute value scale with a calendar x-axis.

The invariants under test:

* **One shared, absolute scale -- no band normalisation (5.3).** Two series
  with different magnitudes keep their ratio: a series twice the size of
  another stays twice as far from the zero line, exactly, because every
  series is mapped through the same value domain.
* **The zero line is always drawn, and the domain always includes zero
  (5.3).** Even when every plotted value is strictly positive, the zero line
  renders inside the plot area rather than off-chart.
* **A missing value breaks the polyline (3.8).** A run of ``None`` in a
  series' values yields two separate ``<polyline>`` elements, never one line
  bridging the gap.
* **A suppressed span gets one backdrop band and exactly one legend entry
  (3.8)**, however many separate spans are supplied.
* **Calendar ticks (5.2).** One tick per January 1st inside the span plus the
  span's own two endpoints; every label is a bare year, with no
  locale-dependent formatting call anywhere in the module.
* **Markers carry only their number (5.4, 5.5).** A marker never carries a
  result or label -- resultless and result-bearing races render identically,
  which is how "no fabricated result" holds by construction.
* **Determinism (load-history 8.5)** -- identical input renders byte-identical
  output, pinned against a committed golden SVG.
"""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

from fitdocs.render.charts.calendar import (
    CalendarBand,
    CalendarChartSpec,
    CalendarMarker,
    CalendarSeries,
    render_calendar_chart,
)
from fitdocs.render.charts.palette import FATIGUE_COLOR, FITNESS_COLOR, FORM_COLOR

GOLDEN_DIR = Path(__file__).parent / "golden"
GOLDEN_PATH = GOLDEN_DIR / "calendar_small_span.svg"

_MODULE_SOURCE = Path(
    Path(__file__).parents[3] / "src" / "fitdocs" / "render" / "charts" / "calendar.py"
).read_text()


# --- golden scenario ---------------------------------------------------------


def _small_span_spec() -> CalendarChartSpec:
    """8 days spanning the 2023/2024 year boundary, one series' gap run,
    one suppressed span, and two markers -- a small synthetic golden case."""
    fitness = CalendarSeries(
        "fitness",
        FITNESS_COLOR,
        (10.0, 12.0, None, None, 16.0, 18.0, 20.0, 22.0),
    )
    fatigue = CalendarSeries(
        "fatigue",
        FATIGUE_COLOR,
        (5.0, 6.0, 7.0, 8.0, 9.0, 10.0, 11.0, 12.0),
    )
    form = CalendarSeries(
        "form",
        FORM_COLOR,
        (-2.0, -1.0, 0.0, 1.0, 2.0, 3.0, 4.0, 5.0),
    )
    return CalendarChartSpec(
        start=date(2023, 12, 30),
        days=8,
        series=(fitness, fatigue, form),
        markers=(
            CalendarMarker(day_index=1, number=1),
            CalendarMarker(day_index=6, number=2),
        ),
        suppressed=(CalendarBand(start_index=2, end_index=3),),
        y_label="load",
    )


def test_matches_committed_golden() -> None:
    assert GOLDEN_PATH.exists(), f"missing golden: {GOLDEN_PATH}"
    assert render_calendar_chart(_small_span_spec()) == GOLDEN_PATH.read_text()


def test_render_is_byte_identical_across_calls() -> None:
    spec = _small_span_spec()
    assert render_calendar_chart(spec) == render_calendar_chart(spec)


# --- anti-band-normalisation: shared absolute scale (Req 5.3) ---------------


def _series_offsets_from_zero(svg: str, label: str) -> list[float]:
    """Parse a labelled series' polyline y-coordinates and return each point's
    signed pixel offset from the drawn zero line (positive = above zero)."""
    zero_y_match = re.search(r'class="zero-line"[^/]*\sy1="(-?[\d.]+)"', svg)
    assert zero_y_match is not None, "no zero line found in svg"
    zero_y = float(zero_y_match.group(1))

    poly_match = re.search(
        rf'<polyline[^>]*data-label="{re.escape(label)}"[^>]*points="([^"]+)"', svg
    )
    assert poly_match is not None, f"no polyline found for label {label!r}"
    points = poly_match.group(1).split(" ")
    ys = [float(p.split(",")[1]) for p in points]
    return [zero_y - y for y in ys]


def test_two_series_of_different_magnitude_keep_their_ratio() -> None:
    """A series with values exactly double another's stays exactly twice as
    far from the zero line at every index -- the anti-normalisation pin."""
    small = CalendarSeries("small", FITNESS_COLOR, (10.0, 20.0, 30.0, -10.0))
    big = CalendarSeries("big", FATIGUE_COLOR, (20.0, 40.0, 60.0, -20.0))
    spec = CalendarChartSpec(
        start=date(2024, 1, 1),
        days=4,
        series=(small, big),
        markers=(),
        suppressed=(),
        y_label="load",
    )
    svg = render_calendar_chart(spec)
    small_offsets = _series_offsets_from_zero(svg, "small")
    big_offsets = _series_offsets_from_zero(svg, "big")
    for so, bo in zip(small_offsets, big_offsets, strict=True):
        assert abs(bo - 2 * so) < 0.05, (so, bo)
    # Falsity in the starting state: an un-doubled pair of raw values would
    # not itself be near a 2x ratio (sanity: input values differ by exactly
    # 2x, so this is not a coincidentally-passing pair).
    assert small.values[0] * 2 == big.values[0]


# --- zero line always present and inside the domain (Req 5.3) ---------------


def test_zero_line_is_drawn_exactly_once() -> None:
    svg = render_calendar_chart(_small_span_spec())
    assert svg.count('class="zero-line"') == 1


def _zero_y_and_plot_bounds(svg: str) -> tuple[float, float, float]:
    """Parse the zero line's y and the plot's real top/bottom bounds from
    rendered SVG: the plot top is the suppressed band's ``y`` (``_PLOT_TOP``)
    and the plot bottom is the calendar axis baseline (``_PLOT_BOTTOM``)."""
    zero_y_match = re.search(r'class="zero-line"[^/]*\sy1="(-?[\d.]+)"', svg)
    assert zero_y_match is not None
    zero_y = float(zero_y_match.group(1))
    top_match = re.search(r'class="suppressed-band"[^/]*\sy="(-?[\d.]+)"', svg)
    assert top_match is not None
    plot_top = float(top_match.group(1))
    # The plot's bottom axis line is the calendar-axis element.
    axis_match = re.search(r'class="calendar-axis"[^/]*\sy1="(-?[\d.]+)"', svg)
    assert axis_match is not None
    plot_bottom = float(axis_match.group(1))
    return zero_y, plot_top, plot_bottom


def test_value_domain_includes_zero_even_when_all_values_are_positive() -> None:
    """All-positive data must still place the zero line inside the plot area
    (between the real plot top and bottom bounds), never off-chart below it."""
    series = CalendarSeries("fitness", FITNESS_COLOR, (100.0, 110.0, 120.0, 130.0))
    spec = CalendarChartSpec(
        start=date(2024, 1, 1),
        days=4,
        series=(series,),
        markers=(),
        # A suppressed band across the whole span exposes the plot-top
        # boundary (the "suppressed-band" element) for this assertion.
        suppressed=(CalendarBand(start_index=0, end_index=3),),
        y_label="load",
    )
    svg = render_calendar_chart(spec)
    zero_y, plot_top, plot_bottom = _zero_y_and_plot_bounds(svg)
    assert plot_top <= zero_y <= plot_bottom, (
        f"zero line at y={zero_y} is off the visible plot "
        f"(top={plot_top}, bottom={plot_bottom})"
    )


def test_value_domain_includes_zero_even_when_all_values_are_negative() -> None:
    """All-negative data must still place the zero line inside the plot area,
    never off-chart above it -- the padding clamp pins both sides of zero,
    not only the positive side."""
    series = CalendarSeries("fitness", FITNESS_COLOR, (-100.0, -110.0, -120.0, -130.0))
    spec = CalendarChartSpec(
        start=date(2024, 1, 1),
        days=4,
        series=(series,),
        markers=(),
        suppressed=(CalendarBand(start_index=0, end_index=3),),
        y_label="load",
    )
    svg = render_calendar_chart(spec)
    zero_y, plot_top, plot_bottom = _zero_y_and_plot_bounds(svg)
    assert plot_top <= zero_y <= plot_bottom, (
        f"zero line at y={zero_y} is off the visible plot "
        f"(top={plot_top}, bottom={plot_bottom})"
    )


# --- a run of missing values breaks the polyline (Req 3.8) ------------------


def test_missing_run_produces_two_polylines_not_one() -> None:
    series = CalendarSeries("fitness", FITNESS_COLOR, (1.0, 2.0, None, None, 5.0, 6.0))
    spec = CalendarChartSpec(
        start=date(2024, 1, 1),
        days=6,
        series=(series,),
        markers=(),
        suppressed=(),
        y_label="load",
    )
    svg = render_calendar_chart(spec)
    assert svg.count("<polyline") == 2


def test_isolated_single_none_also_breaks_the_polyline() -> None:
    """Sibling of the run-of-two gap test: a *single* interior ``None`` must
    also break the polyline into two segments, not be bridged across --
    proves the break is not conditional on the gap being two or more wide."""
    series = CalendarSeries("fitness", FITNESS_COLOR, (1.0, 2.0, None, 4.0, 5.0))
    spec = CalendarChartSpec(
        start=date(2024, 1, 1),
        days=5,
        series=(series,),
        markers=(),
        suppressed=(),
        y_label="load",
    )
    svg = render_calendar_chart(spec)
    assert svg.count("<polyline") == 2


def test_no_gap_produces_exactly_one_polyline() -> None:
    """Sibling of the gap test: no missing run yields exactly one polyline --
    proves the count is sensitive to the gap, not just always >= 1."""
    series = CalendarSeries("fitness", FITNESS_COLOR, (1.0, 2.0, 3.0, 4.0, 5.0, 6.0))
    spec = CalendarChartSpec(
        start=date(2024, 1, 1),
        days=6,
        series=(series,),
        markers=(),
        suppressed=(),
        y_label="load",
    )
    svg = render_calendar_chart(spec)
    assert svg.count("<polyline") == 1


# --- suppressed span: one backdrop, one legend entry, however many bands (3.8)


def test_two_suppressed_bands_yield_one_legend_entry() -> None:
    series = CalendarSeries("fitness", FITNESS_COLOR, (1.0,) * 10)
    spec = CalendarChartSpec(
        start=date(2024, 1, 1),
        days=10,
        series=(series,),
        markers=(),
        suppressed=(
            CalendarBand(start_index=1, end_index=2),
            CalendarBand(start_index=5, end_index=6),
        ),
        y_label="load",
    )
    svg = render_calendar_chart(spec)
    assert svg.count('class="suppressed-band"') == 2
    assert svg.count("suppressed</text>") == 1


def test_single_day_suppressed_band_renders_with_positive_width() -> None:
    """A one-day suppressed span (``start_index == end_index``) is a
    contract-valid inclusive range and must still render a visible rect, not
    a zero-width sliver -- a band covers the day cell it names, not merely
    the point-to-point distance between two identical indices."""
    series = CalendarSeries("fitness", FITNESS_COLOR, (1.0,) * 10)
    spec = CalendarChartSpec(
        start=date(2024, 1, 1),
        days=10,
        series=(series,),
        markers=(),
        suppressed=(CalendarBand(start_index=4, end_index=4),),
        y_label="load",
    )
    svg = render_calendar_chart(spec)
    width_match = re.search(r'class="suppressed-band"[^/]*\swidth="([\d.]+)"', svg)
    assert width_match is not None
    assert float(width_match.group(1)) > 0.0


def test_no_suppressed_bands_yield_no_legend_entry() -> None:
    series = CalendarSeries("fitness", FITNESS_COLOR, (1.0,) * 4)
    spec = CalendarChartSpec(
        start=date(2024, 1, 1),
        days=4,
        series=(series,),
        markers=(),
        suppressed=(),
        y_label="load",
    )
    svg = render_calendar_chart(spec)
    assert svg.count('class="suppressed-band"') == 0
    assert svg.count("suppressed</text>") == 0


# --- calendar ticks: Jan 1sts + endpoints, bare year labels (Req 5.2) -------


def test_ticks_are_every_january_first_plus_the_endpoints() -> None:
    # 2023-12-30 .. 2024-01-06 (8 days): endpoints at 2023-12-30 (year 2023)
    # and 2024-01-06 (year 2024), plus Jan-1-2024 in between -- three ticks.
    svg = render_calendar_chart(_small_span_spec())
    labels = re.findall(r'class="calendar-tick-label"[^>]*>(\d{4})</text>', svg)
    assert labels == ["2023", "2024", "2024"]


def test_ticks_do_not_duplicate_an_endpoint_on_january_first() -> None:
    # A span that starts exactly on Jan 1st must not double that tick.
    series = CalendarSeries("fitness", FITNESS_COLOR, (1.0, 2.0, 3.0))
    spec = CalendarChartSpec(
        start=date(2024, 1, 1),
        days=3,
        series=(series,),
        markers=(),
        suppressed=(),
        y_label="load",
    )
    svg = render_calendar_chart(spec)
    labels = re.findall(r'class="calendar-tick-label"[^>]*>(\d{4})</text>', svg)
    # Only the two endpoints (both year 2024) -- Jan-1 coincides with the
    # start and must not add a third tick.
    assert labels == ["2024", "2024"]
    assert svg.count('class="calendar-tick"') == 2


def test_no_locale_dependent_formatting_call_in_module() -> None:
    """No ``strftime``, no ``locale`` call anywhere in the module's source --
    axis labels are bare integer years, formatted with no locale dependence."""
    assert ".strftime(" not in _MODULE_SOURCE
    assert "locale." not in _MODULE_SOURCE
    assert re.search(r"['\"]%[aAbB]['\"]", _MODULE_SOURCE) is None


# --- markers: numbered glyphs only, no result text (Req 5.4, 5.5) -----------


def test_markers_render_only_their_number() -> None:
    svg = render_calendar_chart(_small_span_spec())
    labels = re.findall(r'class="calendar-marker-label"[^>]*>(\d+)</text>', svg)
    assert labels == ["1", "2"]


def test_marker_count_matches_input_regardless_of_any_result() -> None:
    """A marker carries no result field at all, so a marker for a resultless
    race and one for a race with a result are indistinguishable inputs to
    this module -- both render as the same numbered glyph. This asserts the
    marker count is driven by the input list, not hardcoded."""
    series = CalendarSeries("fitness", FITNESS_COLOR, (1.0,) * 5)
    spec = CalendarChartSpec(
        start=date(2024, 1, 1),
        days=5,
        series=(series,),
        markers=(
            CalendarMarker(day_index=0, number=1),
            CalendarMarker(day_index=2, number=2),
            CalendarMarker(day_index=4, number=3),
        ),
        suppressed=(),
        y_label="load",
    )
    svg = render_calendar_chart(spec)
    assert svg.count('class="calendar-marker-label"') == 3


# --- band clamping and degenerate spans (module-guard sweep, round 3) -------


def _plot_bounds_from_axis(svg: str) -> tuple[float, float]:
    """Parse the plot's real left/right x-bounds from the calendar-axis
    line's ``x1``/``x2`` attributes (``_PLOT_LEFT``/``_PLOT_RIGHT``)."""
    axis_match = re.search(
        r'class="calendar-axis"[^/]*\sx1="(-?[\d.]+)"[^/]*\sx2="(-?[\d.]+)"', svg
    )
    assert axis_match is not None, "no calendar-axis line found in svg"
    return float(axis_match.group(1)), float(axis_match.group(2))


def _band_rects(svg: str) -> list[tuple[float, float]]:
    """Parse every ``suppressed-band`` rect's ``(x, x + width)`` pair, in the
    order the bands were rendered."""
    return [
        (float(x), float(x) + float(width))
        for x, width in re.findall(
            r'class="suppressed-band"[^/]*\sx="(-?[\d.]+)"[^/]*\swidth="([\d.]+)"', svg
        )
    ]


def test_band_at_either_end_is_clamped_to_the_plot() -> None:
    """A band touching either end of the span is clamped to the plot's real
    left/right edges -- its half-day-step extension must not push it past the
    axis. Mutation O1: drop the ``max(_PLOT_LEFT, ...)``/``min(_PLOT_RIGHT,
    ...)`` wrap at calendar.py ~298-299."""
    series = CalendarSeries("fitness", FITNESS_COLOR, (1.0,) * 10)
    spec = CalendarChartSpec(
        start=date(2024, 1, 1),
        days=10,
        series=(series,),
        markers=(),
        suppressed=(
            CalendarBand(start_index=0, end_index=0),
            CalendarBand(start_index=9, end_index=9),
        ),
        y_label="load",
    )
    svg = render_calendar_chart(spec)
    plot_left, plot_right = _plot_bounds_from_axis(svg)
    rects = _band_rects(svg)
    assert len(rects) == 2, rects

    first_left, first_right = rects[0]
    last_left, last_right = rects[1]

    # Falsity in the starting state: the unclamped half-step extension for an
    # end-touching band genuinely reaches past the plot edge for this fixture
    # (10 days -> step = _PLOT_WIDTH / 9, half-step > 0), so the clamp is the
    # only thing keeping the rendered edges on the plot -- this is not a
    # fixture where the raw geometry already sits inside the bounds.
    step = (plot_right - plot_left) / 9
    unclamped_first_left = plot_left - step / 2
    unclamped_last_right = plot_right + step / 2
    assert unclamped_first_left < plot_left
    assert unclamped_last_right > plot_right

    assert first_left == plot_left, (first_left, plot_left)
    assert last_right == plot_right, (last_right, plot_right)
    for left, right in rects:
        assert left >= plot_left, (left, plot_left)
        assert right <= plot_right, (right, plot_right)


def test_all_none_series_renders_with_a_zero_line_and_no_polyline() -> None:
    """Every value missing across every series must not crash the shared
    value-domain computation, must draw no polyline, and must still place the
    zero line inside the plot. Mutation O7: change the empty-domain fallback
    ``(-1.0, 1.0)`` to ``(0.0, 0.0)`` at calendar.py ~203 -- must red with a
    ``ZeroDivisionError`` (a zero-width domain divides by zero in
    ``_y_for_value``)."""
    series = CalendarSeries("fitness", FITNESS_COLOR, (None, None, None, None))
    # Falsity in the starting state: the fixture's finite-value list really is
    # empty (every entry is None), so the empty-domain fallback path is the
    # one actually reached, not bypassed by a stray finite value.
    assert all(v is None for v in series.values)
    spec = CalendarChartSpec(
        start=date(2024, 1, 1),
        days=4,
        series=(series,),
        markers=(),
        suppressed=(CalendarBand(start_index=0, end_index=3),),
        y_label="load",
    )
    svg = render_calendar_chart(spec)
    assert svg.count("<polyline") == 0
    zero_y, plot_top, plot_bottom = _zero_y_and_plot_bounds(svg)
    assert plot_top <= zero_y <= plot_bottom, (
        f"zero line at y={zero_y} is off the visible plot "
        f"(top={plot_top}, bottom={plot_bottom})"
    )


def test_flat_series_renders_with_zero_line_inside_the_plot() -> None:
    """A series flat at exactly zero must not crash the value-domain
    computation (``vmin == vmax == 0.0``), and the zero line must still land
    inside the plot. Mutation O6: delete the ``if vmin == vmax`` widening
    guard at calendar.py ~206-208 -- must red with a ``ZeroDivisionError``
    (an unwidened, zero-span domain divides by zero in ``_y_for_value``)."""
    series = CalendarSeries("fitness", FITNESS_COLOR, (0.0, 0.0, 0.0, 0.0))
    # Falsity in the starting state: the fixture's raw min/max really are
    # equal (both 0.0) before the guard runs -- the flatness the guard exists
    # to widen is genuinely present, not already avoided by varying values.
    assert min(series.values) == max(series.values) == 0.0
    spec = CalendarChartSpec(
        start=date(2024, 1, 1),
        days=4,
        series=(series,),
        markers=(),
        suppressed=(CalendarBand(start_index=0, end_index=3),),
        y_label="load",
    )
    svg = render_calendar_chart(spec)
    zero_y, plot_top, plot_bottom = _zero_y_and_plot_bounds(svg)
    assert plot_top <= zero_y <= plot_bottom, (
        f"zero line at y={zero_y} is off the visible plot "
        f"(top={plot_top}, bottom={plot_bottom})"
    )


def test_single_day_span_renders() -> None:
    """A one-day span (``days == 1``) exercises every ``days - 1``
    denominator in the module and must not crash. Mutation O12: change
    ``denom = max(days - 1, 1)`` to ``denom = days - 1`` at calendar.py ~216
    -- must red with a ``ZeroDivisionError`` in ``_x_for_index``. Mutation
    O13: change ``step = _PLOT_WIDTH / max(days - 1, 1)`` to
    ``step = _PLOT_WIDTH / (days - 1)`` at calendar.py ~295 -- must red with a
    ``ZeroDivisionError`` in ``_render_suppressed_bands``."""
    # Falsity in the starting state: with days == 1, the raw (unguarded)
    # denominator `days - 1` really is 0 -- both mutated lines would divide
    # by zero on this fixture, so the guard is genuinely reached.
    days = 1
    assert days - 1 == 0
    series = CalendarSeries("fitness", FITNESS_COLOR, (5.0,))
    spec = CalendarChartSpec(
        start=date(2024, 1, 1),
        days=days,
        series=(series,),
        markers=(CalendarMarker(day_index=0, number=1),),
        suppressed=(CalendarBand(start_index=0, end_index=0),),
        y_label="load",
    )
    svg = render_calendar_chart(spec)
    assert svg.count('class="calendar-tick"') == 1

    plot_left, plot_right = _plot_bounds_from_axis(svg)
    rects = _band_rects(svg)
    assert len(rects) == 1, rects
    left, right = rects[0]
    assert left >= plot_left, (left, plot_left)
    assert right <= plot_right, (right, plot_right)


# --- regeneration writer (developer utility; pytest does not run this) ------
def main() -> None:
    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    GOLDEN_PATH.write_text(render_calendar_chart(_small_span_spec()), encoding="utf-8")
    print(f"wrote {GOLDEN_PATH}")


if __name__ == "__main__":
    main()
