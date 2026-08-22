"""The power-vs-HR hero graph as static, deterministic SVG (Req 7.1, 7.4, 7.5).

This module renders the reference "MultiChart" hero graph of
``docs/reference/fitdocs-ai-reference.md`` section 3 as hand-built SVG text --
no matplotlib, no template engine, no scripts -- so a workout document shows its
effort profile in any markdown renderer with zero plugins.

The renderer is a pure function of a fully-prepared :class:`HeroChartSpec`.
Series *selection* (default HR + power; documented fallbacks) and the x-axis
*choice* (cumulative distance km vs. elapsed minutes) live in ``sections.py`` (a
later task); this module only draws what it is handed. It imports the standard
library plus sibling ``render.charts`` modules only -- never fit-ingest, never
non-charts ``fitdocs``.

Fidelity to section 3 (Req 7.4), with static adaptations noted:

- Each series is null-skipping boxcar-smoothed (``k=5``) then *independently*
  min/max-normalized into the band ``[0.42, 0.92]``, and the smoothed/normalized
  series are overlaid on one hidden shared y-axis.
- The elevation backdrop, when present, is smoothed and normalized into
  ``[0, 0.32]`` and drawn as a faint filled area band (fill ``#888``, opacity
  ``0.18``) *behind* the series lines.
- Series lines are stroke width ``1.8`` with no dots or markers.
- Missing samples never bridge a gap (Req 7.5): each series polyline is split at
  runs of ``None`` via :func:`~fitdocs.render.charts.series.gap_segments`, so a
  sparse series renders as several separate polylines, never one interpolated
  line.
- X-axis ticks are labelled at 0.1 precision for ``km`` and whole units for
  ``min``. Y-axis ticks are shown ONLY when exactly one series is active -- three
  ticks at the band bottom/mid/top mapped back to that metric's own units; two
  overlaid metrics share a meaningless axis, so no y ticks are drawn.
- Static adaptation: an in-SVG legend (a color swatch + the series label) for
  each active series replaces the reference's hover identification. There is no
  cursor, no tooltip, and no script.

Determinism (Req 7.1, 4.1 by extension): identical ``spec`` -> byte-identical
SVG. Every coordinate is formatted through
:func:`~fitdocs.render.charts.svg.fmt_num`; nothing reads the clock or draws on
randomness, and no ids are generated.

Layout (all constants below, in SVG user units; SVG y grows downward):

- The plot rectangle is inset by fixed margins -- ``_MARGIN_LEFT`` leaves room
  for metric-unit y-tick labels, ``_MARGIN_TOP`` for the legend row, and
  ``_MARGIN_BOTTOM`` for x-axis labels.
- An x-value maps linearly across the plot width; a normalized band value ``n``
  in ``[0, 1]`` maps to ``plot_top + (1 - n) * plot_height`` -- so ``n = 0`` sits
  on the plot floor and larger values rise. Series (``[0.42, 0.92]``) sit in the
  upper-middle; the backdrop (``[0, 0.32]``) hugs the floor.
"""

from __future__ import annotations

from dataclasses import dataclass

from fitdocs.render.charts.series import (
    boxcar_smooth,
    gap_segments,
    normalize_band,
)
from fitdocs.render.charts.svg import el, fmt_num, svg_document, text

# --- public spec ------------------------------------------------------------


@dataclass(frozen=True)
class HeroSeries:
    """One plottable telemetry series for the hero chart.

    ``color`` is a caller-supplied hex string (the caller picks it from
    :mod:`fitdocs.render.charts.palette`); ``values`` is the raw per-sample
    series with absent samples as ``None`` (never a fabricated ``0``) and the
    same length as the spec's ``x``.
    """

    label: str
    unit: str
    color: str
    values: tuple[float | None, ...]


@dataclass(frozen=True)
class HeroChartSpec:
    """A fully-prepared hero chart: axes, 1-2 series, and an optional backdrop.

    ``x`` is the non-decreasing axis (km or minutes) with the same length as
    each series' ``values``; ``x_unit`` is ``"km"`` or ``"min"``. ``series``
    holds one or two active series to overlay. ``backdrop`` holds altitude
    values (same length as ``x``, ``None`` for absent samples) or ``None`` when
    no elevation band should be drawn.
    """

    x: tuple[float, ...]
    x_unit: str
    series: tuple[HeroSeries, ...]
    backdrop: tuple[float | None, ...] | None
    width: int = 800
    height: int = 260


# --- layout + style constants ----------------------------------------------

_MARGIN_LEFT = 56.0
_MARGIN_RIGHT = 16.0
_MARGIN_TOP = 26.0
_MARGIN_BOTTOM = 26.0

_SMOOTH_K = 5
_SERIES_BAND = (0.42, 0.92)
_BACKDROP_BAND = (0.0, 0.32)
_Y_TICK_FRACTIONS = (0.42, 0.67, 0.92)
_N_X_TICKS = 6

_LINE_WIDTH = "1.8"
_BACKDROP_FILL = "#888"
_BACKDROP_OPACITY = "0.18"
_AXIS_COLOR = "#999"
_TICK_TEXT_COLOR = "#555"
_LEGEND_TEXT_COLOR = "#333"
_AXIS_FONT_SIZE = "10"
_LEGEND_FONT_SIZE = "11"

_LEGEND_Y = 8.0
_LEGEND_SWATCH = 10.0
_LEGEND_GAP = 4.0
_LEGEND_ITEM_GAP = 16.0
_LEGEND_CHAR_W = 7.0

_Point = tuple[float, float]


@dataclass(frozen=True)
class _Layout:
    """The resolved plot rectangle and the x-domain, for coordinate mapping."""

    plot_left: float
    plot_right: float
    plot_top: float
    plot_bottom: float
    xmin: float
    xspan: float

    @property
    def plot_width(self) -> float:
        return self.plot_right - self.plot_left

    @property
    def plot_height(self) -> float:
        return self.plot_bottom - self.plot_top

    def x_px(self, xv: float) -> float:
        if self.xspan == 0:
            return self.plot_left
        return self.plot_left + (xv - self.xmin) / self.xspan * self.plot_width

    def y_px(self, n: float) -> float:
        # SVG y grows downward: n=0 -> plot floor, n=1 -> plot ceiling.
        return self.plot_top + (1.0 - n) * self.plot_height


# --- rendering --------------------------------------------------------------


def render_hero_chart(spec: HeroChartSpec) -> str:
    """Render ``spec`` to a deterministic hero-chart SVG string (Req 7.1, 7.4).

    Draws, back to front: the faint elevation backdrop (when present), the
    x-axis ticks, the y-axis ticks (only when exactly one series is active), the
    band-normalized series lines, and the legend. Identical ``spec`` yields
    byte-identical output.
    """
    layout = _resolve_layout(spec)
    children: list[str] = []

    if spec.backdrop is not None:
        backdrop = _render_backdrop(layout, spec.x, spec.backdrop)
        if backdrop:
            children.append(backdrop)

    children.append(_render_x_axis(layout, spec.x_unit))

    if len(spec.series) == 1:
        y_axis = _render_y_axis(layout, spec.series[0])
        if y_axis:
            children.append(y_axis)

    children.append(_render_series(layout, spec.x, spec.series))
    children.append(_render_legend(layout, spec.series))

    return svg_document(spec.width, spec.height, children)


def _resolve_layout(spec: HeroChartSpec) -> _Layout:
    xmin = min(spec.x) if spec.x else 0.0
    xmax = max(spec.x) if spec.x else 0.0
    return _Layout(
        plot_left=_MARGIN_LEFT,
        plot_right=spec.width - _MARGIN_RIGHT,
        plot_top=_MARGIN_TOP,
        plot_bottom=spec.height - _MARGIN_BOTTOM,
        xmin=xmin,
        xspan=xmax - xmin,
    )


def _coord(px: float, py: float) -> str:
    return f"{fmt_num(px)},{fmt_num(py)}"


def _render_backdrop(
    layout: _Layout,
    x: tuple[float, ...],
    backdrop: tuple[float | None, ...],
) -> str:
    """The elevation backdrop as a faint filled area band behind the series.

    Smoothed then normalized into ``[0, 0.32]``; each gap-free run becomes a
    filled area path closed down to the plot floor (``n = 0``). Runs shorter
    than two points cannot form an area and are dropped. Returns ``""`` when no
    fillable area exists.
    """
    smoothed = boxcar_smooth(backdrop, _SMOOTH_K)
    norm = normalize_band(smoothed, *_BACKDROP_BAND)
    baseline = layout.y_px(0.0)
    paths: list[str] = []
    for segment in gap_segments(x, norm):
        if len(segment) < 2:
            continue
        points: list[_Point] = [(layout.x_px(xv), layout.y_px(n)) for xv, n in segment]
        commands = [f"M{_coord(*points[0])}"]
        commands += [f"L{_coord(px, py)}" for px, py in points[1:]]
        commands.append(f"L{_coord(points[-1][0], baseline)}")
        commands.append(f"L{_coord(points[0][0], baseline)}")
        commands.append("Z")
        paths.append(
            el(
                "path",
                {
                    "d": " ".join(commands),
                    "fill": _BACKDROP_FILL,
                    "opacity": _BACKDROP_OPACITY,
                },
            )
        )
    if not paths:
        return ""
    return el("g", {"class": "backdrop"}, paths)


def _render_series(
    layout: _Layout,
    x: tuple[float, ...],
    series: tuple[HeroSeries, ...],
) -> str:
    """The overlaid, band-normalized series lines (Req 7.4, 7.5).

    Each series is smoothed (``k=5``), independently normalized into
    ``[0.42, 0.92]``, and split at ``None`` runs so gaps render as separate
    polylines -- a sparse series yields several polylines, never one bridged
    line. Lines are width ``1.8`` with no markers.
    """
    lines: list[str] = []
    for s in series:
        norm = normalize_band(boxcar_smooth(s.values, _SMOOTH_K), *_SERIES_BAND)
        for segment in gap_segments(x, norm):
            points = " ".join(
                _coord(layout.x_px(xv), layout.y_px(n)) for xv, n in segment
            )
            lines.append(
                el(
                    "polyline",
                    {
                        "points": points,
                        "fill": "none",
                        "stroke": s.color,
                        "stroke-width": _LINE_WIDTH,
                    },
                )
            )
    return el("g", {"class": "series"}, lines)


def _render_x_axis(layout: _Layout, x_unit: str) -> str:
    """X-axis ticks evenly spaced across the domain, labelled per unit.

    ``_N_X_TICKS`` ticks span ``[xmin, xmax]`` inclusive (one tick if the domain
    is degenerate); labels round to 0.1 for ``km`` and to whole units for
    ``min``.
    """
    positions: list[float]
    if layout.xspan == 0:
        positions = [layout.xmin]
    else:
        positions = [
            layout.xmin + layout.xspan * i / (_N_X_TICKS - 1) for i in range(_N_X_TICKS)
        ]
    y_bottom = layout.plot_bottom
    ticks: list[str] = []
    for xv in positions:
        px = layout.x_px(xv)
        tick_line = el(
            "line",
            {
                "x1": fmt_num(px),
                "y1": fmt_num(y_bottom),
                "x2": fmt_num(px),
                "y2": fmt_num(y_bottom + 4),
                "stroke": _AXIS_COLOR,
                "stroke-width": "1",
            },
        )
        label = el(
            "text",
            {
                "x": fmt_num(px),
                "y": fmt_num(y_bottom + 16),
                "text-anchor": "middle",
                "font-size": _AXIS_FONT_SIZE,
                "fill": _TICK_TEXT_COLOR,
            },
            [text(_format_x(xv, x_unit))],
        )
        ticks.append(el("g", {"class": "x-tick"}, [tick_line, label]))
    return el("g", {"class": "x-axis"}, ticks)


def _render_y_axis(layout: _Layout, series: HeroSeries) -> str:
    """Three y-axis ticks mapped back to the single metric's own units (7.4).

    The band bottom / mid / top (``0.42 / 0.67 / 0.92``) map back to the
    series' pre-normalization min / mid / max (of the smoothed values, which are
    what normalization consumes). Returns ``""`` when the series has no data.
    """
    smoothed = boxcar_smooth(series.values, _SMOOTH_K)
    present = [v for v in smoothed if v is not None]
    if not present:
        return ""
    vmin = min(present)
    vmax = max(present)
    values = (vmin, (vmin + vmax) / 2, vmax)
    ticks: list[str] = []
    for frac, value in zip(_Y_TICK_FRACTIONS, values, strict=True):
        py = layout.y_px(frac)
        tick_line = el(
            "line",
            {
                "x1": fmt_num(layout.plot_left - 4),
                "y1": fmt_num(py),
                "x2": fmt_num(layout.plot_left),
                "y2": fmt_num(py),
                "stroke": _AXIS_COLOR,
                "stroke-width": "1",
            },
        )
        unit = f" {series.unit}" if series.unit else ""
        label = el(
            "text",
            {
                "x": fmt_num(layout.plot_left - 6),
                "y": fmt_num(py + 3),
                "text-anchor": "end",
                "font-size": _AXIS_FONT_SIZE,
                "fill": _TICK_TEXT_COLOR,
            },
            [text(f"{fmt_num(value)}{unit}")],
        )
        ticks.append(el("g", {"class": "y-tick"}, [tick_line, label]))
    return el("g", {"class": "y-axis"}, ticks)


def _render_legend(layout: _Layout, series: tuple[HeroSeries, ...]) -> str:
    """An in-SVG legend (swatch + label per series) replacing hover ID (7.4).

    Entries flow left to right from the plot's left edge in the top margin;
    entry advance uses a fixed per-character width estimate so layout is
    deterministic without measuring text.
    """
    cursor = layout.plot_left
    items: list[str] = []
    for s in series:
        swatch = el(
            "rect",
            {
                "x": fmt_num(cursor),
                "y": fmt_num(_LEGEND_Y),
                "width": fmt_num(_LEGEND_SWATCH),
                "height": fmt_num(_LEGEND_SWATCH),
                "fill": s.color,
            },
        )
        label = el(
            "text",
            {
                "x": fmt_num(cursor + _LEGEND_SWATCH + _LEGEND_GAP),
                "y": fmt_num(_LEGEND_Y + _LEGEND_SWATCH - 1),
                "font-size": _LEGEND_FONT_SIZE,
                "fill": _LEGEND_TEXT_COLOR,
            },
            [text(s.label)],
        )
        items.append(el("g", {"class": "legend-item"}, [swatch, label]))
        cursor += (
            _LEGEND_SWATCH
            + _LEGEND_GAP
            + len(s.label) * _LEGEND_CHAR_W
            + _LEGEND_ITEM_GAP
        )
    return el("g", {"class": "legend"}, items)


def _format_x(value: float, x_unit: str) -> str:
    """Format an x-axis tick label: 0.1 precision for km, whole units for min.

    Negative zero is normalized to ``"0"`` / ``"0.0"`` so a tick never renders a
    stray ``-0`` between runs.
    """
    if x_unit == "km":
        # ``or 0.0`` collapses a falsy -0.0 to +0.0 while keeping real negatives.
        rounded = round(value, 1) or 0.0
        return f"{rounded:.1f}"
    return str(int(round(value)))
