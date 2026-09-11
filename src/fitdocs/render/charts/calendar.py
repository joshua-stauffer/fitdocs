"""The calendar-axis, absolutely-scaled multi-series chart (Req 3.8, 5.2-5.5).

This module renders the training-history chart -- fitness, fatigue and form
drawn across the full span of the archive -- as hand-built, deterministic SVG
text, exactly as ``hero.py`` and ``zones.py`` render their own charts. It is a
new, independent module: ``charts/hero.py`` is neither imported, extended nor
changed.

Three rules distinguish this chart from the hero chart's per-series
normalization:

- **One shared, absolute value scale.** Every series is plotted against the
  same y-axis, computed from the finite values actually present across *all*
  series and padded (never shrunk) to include zero. No series is
  band-normalised against another or against itself -- a series twice the
  magnitude of another stays twice as far from the zero line in pixel space
  (Req 5.3).
- **A zero line, always drawn**, because form is routinely negative (Req 5.3).
- **A calendar x-axis**: one tick per January 1st that falls inside the span,
  plus the span's own two endpoints, each labelled with a bare year number.
  No ``strftime``, no month name, and no other locale-dependent formatting
  call appears in this module, so the bytes are identical on every machine
  (Req 5.2).

A missing value (``None``) breaks a series' polyline rather than being
interpolated across, via the shared
:func:`fitdocs.render.charts.series.gap_segments` helper (Req 3.8). A
suppressed span additionally receives a low-opacity backdrop band across the
whole plot height, plus exactly one legend entry regardless of how many
suppressed bands are supplied -- so a break reads as *suppressed*, not as *no
data* (Req 3.8).

Markers are numbered glyphs sitting on the calendar axis, carrying their
1-based number as their only text; the number's meaning (what race, what
result) lives in the markdown beside the chart, which is what keeps ~30
markers legible on one axis (Req 5.4, 5.5). A marker with no result to show is
rendered identically to one with a result -- this module carries no result
text at all, so "no fabricated result" (Req 5.5) holds by construction.

Determinism (load-history Req 8.5): no generated ids, no timestamps, no
randomness, fixed attribute order via :func:`~fitdocs.render.charts.svg.el`,
and every coordinate formatted through
:func:`~fitdocs.render.charts.svg.fmt_num`. This module imports the standard
library plus sibling ``render.charts`` modules only -- never
``fitdocs.history`` (its input is plain dates and optional floats, per the
design's Service contract) and never reads the wall clock: nothing in this
module's code consults the current date or time.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta

from fitdocs.render.charts.series import gap_segments
from fitdocs.render.charts.svg import el, fmt_num, svg_document, text

# --- public spec -------------------------------------------------------------


@dataclass(frozen=True)
class CalendarSeries:
    """One plotted series: a label, its color, and one value per day.

    ``values`` has exactly ``CalendarChartSpec.days`` entries; ``None`` marks a
    day the series has no value for (suppressed or simply absent) and breaks
    the drawn polyline rather than being interpolated across.
    """

    label: str
    color: str
    values: tuple[float | None, ...]


@dataclass(frozen=True)
class CalendarMarker:
    """One race marker: which day it falls on, and its 1-based ordinal.

    ``number`` is the only text this module ever draws for a marker -- the
    label, date and result live in the markdown beside the chart, keyed to
    this number.
    """

    day_index: int
    number: int


@dataclass(frozen=True)
class CalendarBand:
    """One suppressed span, as an inclusive day-index range."""

    start_index: int
    end_index: int  # inclusive


@dataclass(frozen=True)
class CalendarChartSpec:
    """Everything :func:`render_calendar_chart` needs, and nothing else.

    ``start`` is the calendar date of day index 0; ``days`` is the number of
    days the span covers (``days >= 1``); every ``CalendarSeries.values`` has
    exactly ``days`` entries. ``y_label`` names the shared value axis.
    """

    start: date
    days: int
    series: tuple[CalendarSeries, ...]
    markers: tuple[CalendarMarker, ...]
    suppressed: tuple[CalendarBand, ...]
    y_label: str


# --- layout constants (SVG user units; SVG y grows downward) ----------------

_WIDTH = 800
_HEIGHT = 420

_MARGIN_LEFT = 56.0
_MARGIN_RIGHT = 20.0
_MARGIN_TOP = 36.0
_MARGIN_BOTTOM = 90.0

_PLOT_LEFT = _MARGIN_LEFT
_PLOT_RIGHT = _WIDTH - _MARGIN_RIGHT
_PLOT_TOP = _MARGIN_TOP
_PLOT_BOTTOM = _HEIGHT - _MARGIN_BOTTOM
_PLOT_WIDTH = _PLOT_RIGHT - _PLOT_LEFT
_PLOT_HEIGHT = _PLOT_BOTTOM - _PLOT_TOP

_Y_PAD_FRACTION = 0.05  # fraction of the data span added on each side

_ZERO_LINE_COLOR = "#888888"
_AXIS_COLOR = "#444444"
_TICK_LABEL_COLOR = "#333333"
_TICK_LABEL_SIZE = "11"
_Y_LABEL_COLOR = "#333333"
_Y_LABEL_SIZE = "11"

_SUPPRESSED_FILL = "#9aa5b1"
_SUPPRESSED_OPACITY = "0.18"
_LEGEND_LABEL = "suppressed"

_MARKER_ROW_Y = _PLOT_BOTTOM + 16.0
_MARKER_RADIUS = 7.0
_MARKER_FILL = "#333333"
_MARKER_TEXT_COLOR = "#ffffff"
_MARKER_TEXT_SIZE = "9"

_TICK_LABEL_Y = _PLOT_BOTTOM + 38.0
_TICK_MARK_LEN = 6.0

_LEGEND_Y = _HEIGHT - 12.0
_LEGEND_SWATCH_SIZE = 10.0

_STROKE_WIDTH = "2"


# --- rendering ----------------------------------------------------------------


def render_calendar_chart(spec: CalendarChartSpec) -> str:
    """Render ``spec`` as one self-contained, deterministic ``<svg>`` string.

    Every series shares one absolute value scale, padded to include zero, with
    a zero line always drawn (Req 5.3). A ``None`` in a series' ``values``
    breaks its polyline rather than being bridged (Req 3.8). Suppressed spans
    draw a shared low-opacity backdrop with one legend entry (Req 3.8).
    Markers are numbered glyphs on the calendar axis (Req 5.4, 5.5). Identical
    ``spec`` values render byte-identical output.
    """
    vmin, vmax = _y_domain(spec.series)

    children: list[str] = []
    children.append(_render_suppressed_bands(spec.suppressed, spec.days))
    children.append(_render_zero_line(vmin, vmax))
    for series in spec.series:
        children.append(_render_series(series, spec.days, vmin, vmax))
    children.append(_render_axis(spec.start, spec.days))
    children.append(_render_markers(spec.markers, spec.days))
    children.append(_render_legend(spec.series, bool(spec.suppressed)))
    children.append(_render_y_label(spec.y_label))

    return svg_document(_WIDTH, _HEIGHT, children)


# --- scale --------------------------------------------------------------------


def _y_domain(series: Sequence[CalendarSeries]) -> tuple[float, float]:
    """The shared, zero-inclusive value domain across every series (Req 5.3).

    Computed once from the finite values actually present across *all*
    series -- never per series, which is what keeps every series on the same
    scale (the anti-band-normalisation property). The raw data extent is
    widened, never shrunk, to include zero, then padded by a fixed fraction of
    the span on each side so extreme points do not sit on the plot edge. A
    perfectly flat (or entirely absent) domain gets a fixed unit span so the
    scale never degenerates to a division by zero.
    """
    present = [v for one in series for v in one.values if v is not None]
    if not present:
        return (-1.0, 1.0)
    vmin = min(0.0, min(present))
    vmax = max(0.0, max(present))
    if vmin == vmax:
        vmin -= 1.0
        vmax += 1.0
    span = vmax - vmin
    pad = span * _Y_PAD_FRACTION
    return (vmin - pad, vmax + pad)


def _x_for_index(index: int, days: int) -> float:
    """Map a day index (``0 <= index < days``) onto the plot's x range."""
    denom = max(days - 1, 1)
    return _PLOT_LEFT + (index / denom) * _PLOT_WIDTH


def _y_for_value(value: float, vmin: float, vmax: float) -> float:
    """Map a data value onto the plot's y range (SVG y grows downward)."""
    span = vmax - vmin
    fraction = (value - vmin) / span
    return _PLOT_BOTTOM - fraction * _PLOT_HEIGHT


# --- series polylines -----------------------------------------------------


def _render_series(series: CalendarSeries, days: int, vmin: float, vmax: float) -> str:
    """One series as a group of gap-split polylines (Req 3.8, 5.3).

    :func:`~fitdocs.render.charts.series.gap_segments` splits the series at
    every run of ``None`` values, so a missing run yields two (or more)
    separate ``<polyline>`` elements rather than one line joining across the
    gap.
    """
    xs = [float(i) for i in range(days)]
    segments = gap_segments(xs, series.values)
    polylines: list[str] = []
    for segment in segments:
        point_parts = []
        for x, y in segment:
            px = fmt_num(_x_for_index(int(x), days))
            py = fmt_num(_y_for_value(y, vmin, vmax))
            point_parts.append(f"{px},{py}")
        points = " ".join(point_parts)
        polylines.append(
            el(
                "polyline",
                {
                    "class": "calendar-series",
                    "data-label": series.label,
                    "points": points,
                    "fill": "none",
                    "stroke": series.color,
                    "stroke-width": _STROKE_WIDTH,
                },
            )
        )
    return el("g", {"class": "series"}, polylines)


def _render_zero_line(vmin: float, vmax: float) -> str:
    """The always-drawn horizontal line at value 0 (Req 5.3)."""
    y = fmt_num(_y_for_value(0.0, vmin, vmax))
    return el(
        "line",
        {
            "class": "zero-line",
            "x1": fmt_num(_PLOT_LEFT),
            "y1": y,
            "x2": fmt_num(_PLOT_RIGHT),
            "y2": y,
            "stroke": _ZERO_LINE_COLOR,
            "stroke-width": "1",
        },
    )


# --- suppressed spans -----------------------------------------------------


def _render_suppressed_bands(bands: Sequence[CalendarBand], days: int) -> str:
    """One low-opacity backdrop rect per suppressed span (Req 3.8).

    Spans the full plot height, so a break in every series across the span
    reads as *suppressed* rather than as *no data*. A band covers the day
    cells it names, not merely the point-to-point distance between them: it
    extends half a day-step past ``start_index`` and past ``end_index``
    (clamped to the plot's left/right edges), so a single-day band
    (``start_index == end_index``) still renders with positive width. An
    empty ``bands`` yields an empty group.
    """
    step = _PLOT_WIDTH / max(days - 1, 1)
    rects: list[str] = []
    for band in bands:
        left = max(_PLOT_LEFT, _x_for_index(band.start_index, days) - step / 2)
        right = min(_PLOT_RIGHT, _x_for_index(band.end_index, days) + step / 2)
        rects.append(
            el(
                "rect",
                {
                    "class": "suppressed-band",
                    "x": fmt_num(left),
                    "y": fmt_num(_PLOT_TOP),
                    "width": fmt_num(right - left),
                    "height": fmt_num(_PLOT_HEIGHT),
                    "fill": _SUPPRESSED_FILL,
                    "fill-opacity": _SUPPRESSED_OPACITY,
                },
            )
        )
    return el("g", {"class": "suppressed"}, rects)


# --- calendar axis --------------------------------------------------------


def _calendar_ticks(start: date, days: int) -> tuple[tuple[int, int], ...]:
    """Tick positions and their year label: every January 1st inside the span,
    plus the span's own two endpoints (Req 5.2).

    Returns ``(day_index, year)`` pairs in ascending index order with no
    duplicate index -- an endpoint that already falls on January 1st is not
    doubled. Every label is a bare integer year: no ``strftime``, no month
    name, no locale call of any kind, so the bytes never vary by machine.
    """
    end = start + timedelta(days=days - 1)
    ticks: dict[int, int] = {0: start.year, days - 1: end.year}
    for year in range(start.year, end.year + 1):
        jan_first = date(year, 1, 1)
        if start <= jan_first <= end:
            index = (jan_first - start).days
            ticks[index] = year
    return tuple(sorted(ticks.items()))


def _render_axis(start: date, days: int) -> str:
    """The calendar horizontal axis: a baseline, tick marks and year labels."""
    children: list[str] = [
        el(
            "line",
            {
                "class": "calendar-axis",
                "x1": fmt_num(_PLOT_LEFT),
                "y1": fmt_num(_PLOT_BOTTOM),
                "x2": fmt_num(_PLOT_RIGHT),
                "y2": fmt_num(_PLOT_BOTTOM),
                "stroke": _AXIS_COLOR,
                "stroke-width": "1",
            },
        )
    ]
    for index, year in _calendar_ticks(start, days):
        x = _x_for_index(index, days)
        children.append(
            el(
                "line",
                {
                    "class": "calendar-tick",
                    "x1": fmt_num(x),
                    "y1": fmt_num(_PLOT_BOTTOM),
                    "x2": fmt_num(x),
                    "y2": fmt_num(_PLOT_BOTTOM + _TICK_MARK_LEN),
                    "stroke": _AXIS_COLOR,
                    "stroke-width": "1",
                },
            )
        )
        children.append(
            el(
                "text",
                {
                    "class": "calendar-tick-label",
                    "x": fmt_num(x),
                    "y": fmt_num(_TICK_LABEL_Y),
                    "font-size": _TICK_LABEL_SIZE,
                    "fill": _TICK_LABEL_COLOR,
                    "text-anchor": "middle",
                },
                [text(str(year))],
            )
        )
    return el("g", {"class": "axis"}, children)


# --- markers ----------------------------------------------------------------


def _render_markers(markers: Sequence[CalendarMarker], days: int) -> str:
    """Numbered glyphs on the calendar axis, one per race marker (Req 5.4, 5.5).

    Each marker carries only its 1-based number as text -- no result, no date,
    no label -- which holds "no fabricated result" (Req 5.5) by construction:
    a resultless race is rendered identically to one with a result, because
    this module never carries a result at all.
    """
    items: list[str] = []
    for marker in markers:
        x = _x_for_index(marker.day_index, days)
        circle = el(
            "circle",
            {
                "class": "calendar-marker",
                "cx": fmt_num(x),
                "cy": fmt_num(_MARKER_ROW_Y),
                "r": fmt_num(_MARKER_RADIUS),
                "fill": _MARKER_FILL,
            },
        )
        label = el(
            "text",
            {
                "class": "calendar-marker-label",
                "x": fmt_num(x),
                "y": fmt_num(_MARKER_ROW_Y + 3.0),
                "font-size": _MARKER_TEXT_SIZE,
                "fill": _MARKER_TEXT_COLOR,
                "text-anchor": "middle",
            },
            [text(str(marker.number))],
        )
        items.append(el("g", {"class": "marker"}, [circle, label]))
    return el("g", {"class": "markers"}, items)


# --- legend -----------------------------------------------------------------


def _render_legend(series: Sequence[CalendarSeries], has_suppressed: bool) -> str:
    """One swatch + label per series, plus exactly one entry for suppression.

    A suppressed span always gets exactly one legend entry regardless of how
    many separate :class:`CalendarBand` spans are supplied (Req 3.8).
    """
    entries: list[tuple[str, str]] = [(s.color, s.label) for s in series]
    if has_suppressed:
        entries.append((_SUPPRESSED_FILL, _LEGEND_LABEL))

    column_width = _WIDTH / max(len(entries), 1)
    items: list[str] = []
    for index, (color, label) in enumerate(entries):
        column_left = index * column_width
        swatch = el(
            "rect",
            {
                "class": "legend-swatch",
                "x": fmt_num(column_left),
                "y": fmt_num(_LEGEND_Y - _LEGEND_SWATCH_SIZE),
                "width": fmt_num(_LEGEND_SWATCH_SIZE),
                "height": fmt_num(_LEGEND_SWATCH_SIZE),
                "fill": color,
            },
        )
        caption = el(
            "text",
            {
                "x": fmt_num(column_left + _LEGEND_SWATCH_SIZE + 4.0),
                "y": fmt_num(_LEGEND_Y),
                "font-size": _TICK_LABEL_SIZE,
                "fill": _TICK_LABEL_COLOR,
            },
            [text(label)],
        )
        items.append(el("g", {"class": "legend-entry"}, [swatch, caption]))
    return el("g", {"class": "legend"}, items)


def _render_y_label(y_label: str) -> str:
    """The shared value axis's name, once, near the plot's top-left corner."""
    return el(
        "text",
        {
            "class": "calendar-y-label",
            "x": fmt_num(_PLOT_LEFT),
            "y": fmt_num(_PLOT_TOP - 12.0),
            "font-size": _Y_LABEL_SIZE,
            "fill": _Y_LABEL_COLOR,
        },
        [text(y_label)],
    )
