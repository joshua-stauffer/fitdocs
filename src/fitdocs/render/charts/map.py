"""Pure slippy-map geometry for the route map (Req 1.3, 2.4, 2.5, 2.6).

This module is the single pure home of the map computation. It projects a
workout's per-sample GPS channels through the Web-Mercator / EPSG:3857 slippy
scheme, chooses a whole-route framing, enumerates the covering basemap tiles,
and lays the gap-split route out in viewport pixels. The result -- a
:class:`MapPlan` -- is consumed by two callers that must never disagree: the
sync engine reads ``MapPlan.tiles`` to resolve exactly the tiles a map needs,
and :func:`compose_map` reads the same plan to draw the SVG.

Two halves live here. *Planning* -- :class:`TileRef`, :class:`MapPlan`,
:func:`plan_map` -- projects and frames the route and enumerates its covering
tiles. *Composition* -- :func:`compose_map` -- lays the resolved tiles down as
inline base64 ``data:`` images, draws the gap-split route with a per-segment
glow, marks the start and finish, and labels the tile attribution, emitting one
self-contained SVG that references no external resources (Req 2.1, 2.2, 2.7,
6.1).

The projection is the canonical slippy formula on 256-px tiles: at zoom ``z``
the world is ``256 * 2**z`` px wide, ``px = (lon + 180) / 360 * world`` and
``py = (1 - ln(tan(phi) + sec(phi)) / pi) / 2 * world`` (``phi`` the latitude in
radians); the tile a point falls in is ``(floor(px / 256), floor(py / 256))``.
Framing picks the *largest* integer zoom, clamped to ``[1, 17]``, at which the
route's projected bounding box fits inside the fixed 800x500 viewport with at
least 32 px of padding on every side, so a larger route selects a lower zoom
(Req 2.5); a negligible extent (a single point or a sub-pixel bounding box)
falls back to a fixed zoom 16 centered on the position rather than failing or
dividing by zero (Req 2.6). Positions are paired through
:func:`fitdocs.render.charts.series.paired_gap_segments` *before* projection, so
a gap in either channel breaks the route and is never interpolated across (Req
2.4); ``plan_map`` returns ``None`` exactly when no index carries both a
latitude and a longitude (absent data stays absent, Req 1.3).

Purity: standard-library ``math`` and ``base64`` plus the sibling
:mod:`fitdocs.render.charts` modules (``series``, ``svg``, ``palette``) only --
no I/O, no clock, no randomness, and never an import of :mod:`fitdocs.tiles`.
Determinism follows by construction: planning emits tiles in a fixed row-major
order (``y`` outer, ``x`` inner), and composition runs every coordinate through
:func:`~fitdocs.render.charts.svg.fmt_num`, builds every attribute mapping in a
fixed key order, and base64-encodes identical bytes identically -- so identical
inputs yield byte-identical SVG (Req 4.1).

Documented limitation: a route that crosses the antimeridian is not given
special handling -- it simply frames at a low (zoomed-out) valid plan.
"""

from __future__ import annotations

import base64
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from fitdocs.render.charts.palette import ROUTE_FINISH_COLOR, ROUTE_START_COLOR
from fitdocs.render.charts.series import paired_gap_segments
from fitdocs.render.charts.svg import el, fmt_num, svg_document, text

#: Slippy tile edge length in pixels (the EPSG:3857 web tiling convention).
TILE_SIZE = 256

#: Fixed map viewport in pixels. Width matches the hero chart (800); height 500.
VIEWPORT_WIDTH = 800
VIEWPORT_HEIGHT = 500

#: Minimum visible padding, in px, between the route and every viewport edge.
VIEWPORT_PADDING = 32

#: Supported integer zoom range. Framing is clamped into ``[MIN_ZOOM, MAX_ZOOM]``.
MIN_ZOOM = 1
MAX_ZOOM = 17

#: Fixed fallback zoom for a negligible-extent route (single point / sub-pixel).
DEGENERATE_ZOOM = 16

# --- composition style constants (reference visual style, Req 2.1, 2.2, 2.7) -
# Named for clarity and stability: the composed SVG's appearance is pinned by
# these values, and goldens change only when a value here deliberately changes.

#: Route glow (Req 2.1): a wide translucent underlay beneath a narrow opaque
#: foreground, both tinted by sport, with round caps/joins so a single-point
#: segment reads as a dot.
GLOW_UNDERLAY_WIDTH = 10.0
GLOW_UNDERLAY_OPACITY = 0.2
GLOW_FOREGROUND_WIDTH = 4.0
GLOW_FOREGROUND_OPACITY = 0.95

#: Start/finish markers (Req 2.2): a filled circle with a thin white outline.
MARKER_RADIUS = 5.0
MARKER_STROKE_WIDTH = 1.5
MARKER_STROKE_COLOR = "#ffffff"

#: Attribution (Req 2.7): legible sans-serif text over a translucent white
#: backing rect in the bottom-right corner. ``CHAR_WIDTH`` is a per-character
#: advance estimate at the font size, sizing the backing without measuring text.
ATTRIBUTION_FONT_SIZE = 10.0
ATTRIBUTION_PADDING = 4.0
ATTRIBUTION_CHAR_WIDTH = 6.0
ATTRIBUTION_TEXT_COLOR = "#333333"
ATTRIBUTION_BACKING_COLOR = "#ffffff"
ATTRIBUTION_BACKING_OPACITY = 0.8


@dataclass(frozen=True)
class TileRef:
    """One slippy-map tile coordinate ``(z, x, y)``.

    Frozen so it is a hashable value: equality and hash drive tile-cache lookups
    and ``dict`` keys downstream. ``x`` is left unclamped (the antimeridian is a
    documented limitation); ``y`` is always within ``[0, 2**z - 1]``.
    """

    z: int
    x: int
    y: int


@dataclass(frozen=True)
class MapPlan:
    """Everything a map render needs, and the exact tile set sync must resolve.

    ``origin_x`` / ``origin_y`` are the global Web-Mercator pixel coordinates, at
    ``zoom``, of the viewport's top-left corner (sub-pixel floats). A tile
    ``t`` is drawn at ``(t.x * 256 - origin_x, t.y * 256 - origin_y)`` and a
    route point at ``global_px - origin_x`` / ``global_py - origin_y``; the
    ``segments`` are already stored in those viewport pixel coordinates.
    """

    zoom: int
    width: int
    height: int
    origin_x: float
    origin_y: float
    tiles: tuple[TileRef, ...]
    segments: tuple[tuple[tuple[float, float], ...], ...]


def _world_size(zoom: int) -> int:
    """Global map edge length in pixels at ``zoom`` (``256 * 2**zoom``)."""
    return TILE_SIZE << zoom


def _project(lat: float, lon: float, zoom: int) -> tuple[float, float]:
    """Project ``(lat, lon)`` (decimal degrees) to global pixel coords at ``zoom``.

    The canonical slippy-map / Web-Mercator formula on 256-px tiles::

        world = 256 * 2**zoom
        px    = (lon + 180) / 360 * world
        py    = (1 - ln(tan(phi) + sec(phi)) / pi) / 2 * world

    with ``phi`` the latitude in radians and ``sec(phi) = 1 / cos(phi)``. ``px``
    grows eastward; ``py`` grows southward (north is a smaller ``py``).
    """
    world = _world_size(zoom)
    px = (lon + 180.0) / 360.0 * world
    lat_rad = math.radians(lat)
    merc = math.log(math.tan(lat_rad) + 1.0 / math.cos(lat_rad))
    py = (1.0 - merc / math.pi) / 2.0 * world
    return px, py


def _tile_of(px: float, py: float) -> tuple[int, int]:
    """Slippy tile ``(x, y)`` containing the global pixel point ``(px, py)``."""
    return math.floor(px / TILE_SIZE), math.floor(py / TILE_SIZE)


def _select_zoom(width0: float, height0: float) -> int:
    """Choose the integer framing zoom for a bounding box measured at zoom 0.

    ``width0`` / ``height0`` are the projected bounding-box dimensions in pixels
    at zoom 0; projection is linear in the world size, so the dimensions at zoom
    ``z`` are simply ``dimension0 * 2**z``. Returns the *largest* zoom in
    ``[MIN_ZOOM, MAX_ZOOM]`` at which both dimensions fit inside the padded
    viewport, clamped to ``MIN_ZOOM`` when even that overflows. A negligible
    extent -- sub-pixel in both dimensions even at the finest supported zoom --
    returns :data:`DEGENERATE_ZOOM` instead of framing (Req 2.6), so a single
    point never selects a spurious maximum zoom or divides by zero.
    """
    if max(width0, height0) * (1 << MAX_ZOOM) < 1.0:
        return DEGENERATE_ZOOM
    avail_w = VIEWPORT_WIDTH - 2 * VIEWPORT_PADDING
    avail_h = VIEWPORT_HEIGHT - 2 * VIEWPORT_PADDING
    zoom = MIN_ZOOM
    for candidate in range(MIN_ZOOM, MAX_ZOOM + 1):
        scale = 1 << candidate
        if width0 * scale <= avail_w and height0 * scale <= avail_h:
            zoom = candidate
        else:
            # Dimensions grow monotonically with zoom: once it stops fitting it
            # never fits again, so the last fitting zoom is the largest.
            break
    return zoom


def _enumerate_tiles(
    zoom: int,
    origin_x: float,
    origin_y: float,
) -> tuple[TileRef, ...]:
    """Row-major covering tile set for the viewport at ``(origin_x, origin_y)``.

    Emits every tile the fixed 800x500 viewport overlaps, iterating ``y`` outer
    then ``x`` inner (deterministic order, Req 4.1). The tile ``y`` range is
    clamped to the valid ``[0, 2**z - 1]`` band; ``x`` is left as-is (the
    antimeridian is a documented limitation).
    """
    x_min = math.floor(origin_x / TILE_SIZE)
    x_max = math.floor((origin_x + VIEWPORT_WIDTH) / TILE_SIZE)
    y_min = math.floor(origin_y / TILE_SIZE)
    y_max = math.floor((origin_y + VIEWPORT_HEIGHT) / TILE_SIZE)
    max_index = (1 << zoom) - 1
    y_min = min(max(y_min, 0), max_index)
    y_max = min(max(y_max, 0), max_index)
    return tuple(
        TileRef(zoom, x, y)
        for y in range(y_min, y_max + 1)
        for x in range(x_min, x_max + 1)
    )


def plan_map(
    latitudes: Sequence[float | None],
    longitudes: Sequence[float | None],
) -> MapPlan | None:
    """Plan the route map from the position channels, or ``None`` if none exist.

    ``latitudes`` and ``longitudes`` are the same-length, decimal-degree
    channels from fit-ingest, with unrecorded samples held as ``None``. A route
    point exists only where *both* channels are present at an index; a gap in
    either channel breaks the route (via :func:`paired_gap_segments`) and is
    never bridged (Req 2.4).

    Returns ``None`` iff no index carries a complete pair -- absent data stays
    absent (Req 1.3). Otherwise the returned :class:`MapPlan` frames the whole
    route inside the fixed 800x500 viewport at the largest integer zoom (clamped
    to ``[1, 17]``) that leaves at least 32 px of padding on every side, centered
    on the route (Req 2.5); a negligible extent (single point / sub-pixel
    bounding box) yields a fixed zoom-16 plan centered on the position (Req 2.6).
    ``segments`` are the gap-split route projected into viewport pixel coords.
    """
    segments_ll = paired_gap_segments(latitudes, longitudes)
    if not segments_ll:
        return None

    points = [point for segment in segments_ll for point in segment]

    # Bounding box at zoom 0; projection is linear in the world size, so this
    # scales to any zoom by multiplying pixel extents by ``2**zoom``.
    proj0 = [_project(lat, lon, 0) for lat, lon in points]
    px0 = [p[0] for p in proj0]
    py0 = [p[1] for p in proj0]
    width0 = max(px0) - min(px0)
    height0 = max(py0) - min(py0)

    zoom = _select_zoom(width0, height0)

    # Reproject at the chosen zoom to center the viewport and lay out the route.
    projected = [_project(lat, lon, zoom) for lat, lon in points]
    pxs = [p[0] for p in projected]
    pys = [p[1] for p in projected]
    center_px = (min(pxs) + max(pxs)) / 2.0
    center_py = (min(pys) + max(pys)) / 2.0
    origin_x = center_px - VIEWPORT_WIDTH / 2.0
    origin_y = center_py - VIEWPORT_HEIGHT / 2.0

    tiles = _enumerate_tiles(zoom, origin_x, origin_y)

    segments = tuple(
        tuple(
            (px - origin_x, py - origin_y)
            for px, py in (_project(lat, lon, zoom) for lat, lon in segment)
        )
        for segment in segments_ll
    )

    return MapPlan(
        zoom=zoom,
        width=VIEWPORT_WIDTH,
        height=VIEWPORT_HEIGHT,
        origin_x=origin_x,
        origin_y=origin_y,
        tiles=tiles,
        segments=segments,
    )


def _point(px: float, py: float) -> str:
    """Format one ``x,y`` coordinate through the shared deterministic writer."""
    return f"{fmt_num(px)},{fmt_num(py)}"


def _render_tiles(plan: MapPlan, tiles: Mapping[TileRef, bytes]) -> list[str]:
    """The basemap tiles as inline ``data:`` ``<image>`` elements (bottom layer).

    One ``<image>`` per tile in ``plan.tiles`` order (deterministic, Req 4.1),
    positioned at its viewport offset ``(x*256 - origin_x, y*256 - origin_y)``,
    each carrying a base64 PNG payload via the SVG2 ``href`` attribute (no
    ``xlink``) so the map is self-contained (Req 6.1). ``tiles`` must cover every
    ref: a missing key is a programming error (sync guarantees coverage) and
    surfaces as :class:`KeyError` rather than a silently dropped tile.
    """
    images: list[str] = []
    for ref in plan.tiles:
        encoded = base64.b64encode(tiles[ref]).decode("ascii")
        images.append(
            el(
                "image",
                {
                    "x": fmt_num(ref.x * TILE_SIZE - plan.origin_x),
                    "y": fmt_num(ref.y * TILE_SIZE - plan.origin_y),
                    "width": str(TILE_SIZE),
                    "height": str(TILE_SIZE),
                    "href": f"data:image/png;base64,{encoded}",
                },
            )
        )
    return images


def _polyline(points: str, tint: str, width: float, opacity: float) -> str:
    """One tinted, round-capped/joined polyline layer with no fill."""
    return el(
        "polyline",
        {
            "points": points,
            "fill": "none",
            "stroke": tint,
            "stroke-width": fmt_num(width),
            "stroke-opacity": fmt_num(opacity),
            "stroke-linecap": "round",
            "stroke-linejoin": "round",
        },
    )


def _render_route(plan: MapPlan, tint: str) -> list[str]:
    """The gap-split route with a per-segment glow treatment (Req 2.1).

    Each segment draws a wide translucent underlay beneath a narrow opaque
    foreground -- both tinted, round caps and joins -- so the route reads with a
    glow. A single-point segment duplicates its point, rendering the zero-length
    round-cap stroke as a dot.
    """
    elements: list[str] = []
    for segment in plan.segments:
        coords = [_point(px, py) for px, py in segment]
        if len(coords) == 1:
            # A zero-length stroke: the round cap shows the lone point as a dot.
            coords = coords * 2
        points = " ".join(coords)
        elements.append(
            _polyline(points, tint, GLOW_UNDERLAY_WIDTH, GLOW_UNDERLAY_OPACITY)
        )
        elements.append(
            _polyline(points, tint, GLOW_FOREGROUND_WIDTH, GLOW_FOREGROUND_OPACITY)
        )
    return elements


def _marker(px: float, py: float, fill: str) -> str:
    """One start/finish marker: a filled circle with a thin white outline (2.2)."""
    return el(
        "circle",
        {
            "cx": fmt_num(px),
            "cy": fmt_num(py),
            "r": fmt_num(MARKER_RADIUS),
            "fill": fill,
            "stroke": MARKER_STROKE_COLOR,
            "stroke-width": fmt_num(MARKER_STROKE_WIDTH),
        },
    )


def _render_markers(plan: MapPlan) -> list[str]:
    """Start and finish markers on the first and last recorded positions (2.2).

    The start sits on the first point of the first segment and the finish on the
    last point of the last segment; ``plan.segments`` is non-empty by
    construction (``plan_map`` returns ``None`` when no route exists).
    """
    start_x, start_y = plan.segments[0][0]
    finish_x, finish_y = plan.segments[-1][-1]
    return [
        _marker(start_x, start_y, ROUTE_START_COLOR),
        _marker(finish_x, finish_y, ROUTE_FINISH_COLOR),
    ]


def _render_attribution(plan: MapPlan, attribution: str) -> list[str]:
    """Legible attribution text over a translucent backing, bottom-right (2.7).

    A white ``fill-opacity`` 0.8 backing rect, sized from a per-character advance
    estimate with ``ATTRIBUTION_PADDING`` on each side, sits beneath the
    right-anchored 10 px text (drawn after, so it reads over the backing). The
    text passes through the writer's XML escaping so recorded data cannot break
    the markup.
    """
    text_width = max(len(attribution), 1) * ATTRIBUTION_CHAR_WIDTH
    rect_width = text_width + 2.0 * ATTRIBUTION_PADDING
    rect_height = ATTRIBUTION_FONT_SIZE + 2.0 * ATTRIBUTION_PADDING
    backing = el(
        "rect",
        {
            "x": fmt_num(plan.width - rect_width),
            "y": fmt_num(plan.height - rect_height),
            "width": fmt_num(rect_width),
            "height": fmt_num(rect_height),
            "fill": ATTRIBUTION_BACKING_COLOR,
            "fill-opacity": fmt_num(ATTRIBUTION_BACKING_OPACITY),
        },
    )
    label = el(
        "text",
        {
            "x": fmt_num(plan.width - ATTRIBUTION_PADDING),
            "y": fmt_num(plan.height - ATTRIBUTION_PADDING),
            "text-anchor": "end",
            "font-size": fmt_num(ATTRIBUTION_FONT_SIZE),
            "font-family": "sans-serif",
            "fill": ATTRIBUTION_TEXT_COLOR,
        },
        [text(attribution)],
    )
    return [backing, label]


def compose_map(
    plan: MapPlan,
    tiles: Mapping[TileRef, bytes],
    *,
    tint: str,
    attribution: str,
) -> str:
    """Compose ``plan`` and its resolved ``tiles`` into one self-contained SVG.

    Drawn bottom to top (document order): the basemap ``tiles`` as base64
    ``data:`` ``<image>`` elements at their viewport offsets; the gap-split
    route with a per-segment glow (a wide translucent underlay beneath a narrow
    opaque foreground, ``tint``-colored, round caps/joins, single-point segments
    as dots, Req 2.1); distinct start/finish markers on the first and last
    recorded positions (Req 2.2); and legible ``attribution`` over a translucent
    backing in the bottom-right corner (Req 2.7). The result is a complete SVG
    document string that references no external resources -- every tile is an
    inline ``data:`` URI, so it renders with no network access at view time (Req
    6.1).

    ``tiles`` must cover every :attr:`MapPlan.tiles` entry (sync guarantees this);
    a missing key raises :class:`KeyError` rather than silently dropping a tile.

    Deterministic by construction (Req 4.1): tiles are emitted in ``plan.tiles``
    order, every coordinate passes through
    :func:`~fitdocs.render.charts.svg.fmt_num`, each attribute mapping is built
    in a fixed key order, and ``base64`` of identical bytes is identical -- so
    identical inputs yield byte-identical SVG.
    """
    children: list[str] = []
    children += _render_tiles(plan, tiles)
    children += _render_route(plan, tint)
    children += _render_markers(plan)
    children += _render_attribution(plan, attribution)
    return svg_document(plan.width, plan.height, children)
