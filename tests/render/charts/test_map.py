"""Hand-computed tests for the pure map-planning geometry (Req 1.3, 2.4-2.6).

These exercise both halves of :mod:`fitdocs.render.charts.map`: the *planning*
half -- the Web-Mercator / EPSG:3857 slippy projection, integer zoom selection,
whole-route viewport framing with padding, row-major covering-tile enumeration,
and the gap-split route projected into viewport pixels -- and the *composition*
half (``compose_map``): tiles embedded as ``data:`` URIs, the per-segment glow
treatment, start/finish markers, and legible attribution, composed into a
single self-contained SVG that is byte-identical for identical inputs.

The invariants under test:

* **Projection matches published slippy-map references** -- known (lat, lon,
  zoom) map to the canonical tile x/y and global pixel coords. Expected values
  are hand-computed / hard-coded (the well-known London tile, the analytic
  origin points) and independently re-derived from the ``asinh`` formulation --
  never by calling ``plan_map`` itself (Req 2.5 projection basis).
* **Framing selects the largest fitting zoom with >= 32 px padding** -- a route
  is framed at the largest integer zoom (clamped to [1, 17]) whose projected
  bounding box fits inside the fixed 800x500 viewport with at least 32 px of
  padding on every side; a larger extent selects a lower zoom (Req 2.5).
* **Degenerate extent still yields a valid plan** -- a single point or a
  sub-pixel bounding box yields a fixed zoom-16 plan centered on the position,
  with a non-empty covering tile set, rather than failing (Req 2.6).
* **No complete lat/lon pair yields no plan** -- absent data stays absent:
  ``plan_map`` returns ``None`` iff no index has *both* latitude and longitude
  present (Req 1.3).
* **Gaps break the route** -- a ``None`` in either channel splits the projected
  route into multiple segments; a run of incomplete pairs is never bridged
  across (Req 2.4).
"""

from __future__ import annotations

import base64
import math
import re
from collections.abc import Sequence
from dataclasses import FrozenInstanceError

import pytest

from fitdocs.render.charts.map import (
    MapPlan,
    TileRef,
    _project,
    _tile_of,
    compose_map,
    plan_map,
)
from fitdocs.render.charts.palette import ROUTE_FINISH_COLOR, ROUTE_START_COLOR
from fitdocs.render.charts.svg import SVG_NAMESPACE, fmt_num

# --- viewport constants mirrored from the module contract -------------------
VIEWPORT_WIDTH = 800
VIEWPORT_HEIGHT = 500
PADDING = 32
AVAIL_W = VIEWPORT_WIDTH - 2 * PADDING  # 736
AVAIL_H = VIEWPORT_HEIGHT - 2 * PADDING  # 436
TILE_SIZE = 256


# --- independent reference implementations ----------------------------------
def _ref_project(lat: float, lon: float, zoom: int) -> tuple[float, float]:
    """Independent slippy projection using ``asinh`` instead of ``ln(tan+sec)``.

    Algebraically identical to the module's formula (``asinh(tan phi) ==
    ln(tan phi + sec phi)``) but written with different primitives, so a formula
    transcription bug in the module would surface as a mismatch here.
    """
    n = 256 * 2**zoom
    x = (lon + 180.0) / 360.0 * n
    lat_rad = math.radians(lat)
    y = (1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n
    return x, y


def _route_span(
    lats: Sequence[float],
    lons: Sequence[float],
    zoom: int,
) -> tuple[float, float]:
    """Projected bounding-box width/height (global px) of a route at ``zoom``."""
    pxs = [_project(lat, lon, zoom)[0] for lat, lon in zip(lats, lons, strict=True)]
    pys = [_project(lat, lon, zoom)[1] for lat, lon in zip(lats, lons, strict=True)]
    return max(pxs) - min(pxs), max(pys) - min(pys)


# --- projection against published reference values --------------------------
def test_projection_analytic_reference_points() -> None:
    # Prime meridian / equator: exact, sign-free.
    assert _project(0.0, 0.0, 0) == (128.0, 128.0)
    assert _project(0.0, 0.0, 1) == (256.0, 256.0)
    # At zoom 1 the equator/prime-meridian corner is the shared corner of the
    # four tiles: floor(256/256) == 1 on both axes.
    assert _tile_of(*_project(0.0, 0.0, 1)) == (1, 1)
    assert _tile_of(*_project(0.0, 0.0, 0)) == (0, 0)


def test_projection_matches_well_known_london_tile() -> None:
    # Published slippy-map reference: (lat 51.5, lon -0.1) at zoom 10 lands in
    # tile x=511, y=340 (the standard OSM tilename worked example).
    px, py = _project(51.5, -0.1, 10)
    assert _tile_of(px, py) == (511, 340)


def test_projection_matches_independent_asinh_derivation() -> None:
    for lat in (-60.0, -12.3, 0.0, 12.3, 48.8583, 60.0):
        for lon in (-179.0, -73.0, 0.0, 8.53, 151.2):
            for z in (1, 5, 10, 14, 17):
                ex, ey = _ref_project(lat, lon, z)
                px, py = _project(lat, lon, z)
                assert px == pytest.approx(ex, abs=1e-4)
                assert py == pytest.approx(ey, abs=1e-4)


# --- framing: zoom selection and padding ------------------------------------
def test_zoom_leaves_padding_and_is_maximal() -> None:
    # A ~0.5-degree bounding box near lat 37.
    lats = [37.0, 37.0, 37.5, 37.5]
    lons = [-122.5, -122.0, -122.0, -122.5]
    plan = plan_map(lats, lons)
    assert plan is not None
    assert 1 <= plan.zoom <= 17
    assert plan.width == VIEWPORT_WIDTH
    assert plan.height == VIEWPORT_HEIGHT

    # The route fits inside the viewport with >= 32 px padding on all sides.
    span_w, span_h = _route_span(lats, lons, plan.zoom)
    assert span_w <= AVAIL_W
    assert span_h <= AVAIL_H

    # Maximal: one zoom deeper would overflow the padded area (unless clamped).
    if plan.zoom < 17:
        span_w2, span_h2 = _route_span(lats, lons, plan.zoom + 1)
        assert span_w2 > AVAIL_W or span_h2 > AVAIL_H


def test_larger_extent_selects_lower_zoom() -> None:
    small = plan_map([0.0, 0.001], [0.0, 0.001])
    large = plan_map([0.0, 2.0], [0.0, 2.0])
    assert small is not None
    assert large is not None
    assert small.zoom > large.zoom


def test_route_is_centered_in_viewport() -> None:
    lats = [10.0, 10.4]
    lons = [20.0, 20.4]
    plan = plan_map(lats, lons)
    assert plan is not None
    # Reproject the bbox at the plan zoom; the viewport-relative bbox center
    # must sit at the viewport center.
    proj = [_project(lat, lon, plan.zoom) for lat, lon in zip(lats, lons, strict=True)]
    pxs = [px for px, _ in proj]
    pys = [py for _, py in proj]
    cx = (min(pxs) + max(pxs)) / 2 - plan.origin_x
    cy = (min(pys) + max(pys)) / 2 - plan.origin_y
    assert cx == pytest.approx(VIEWPORT_WIDTH / 2)
    assert cy == pytest.approx(VIEWPORT_HEIGHT / 2)


# --- degenerate extent ------------------------------------------------------
def test_single_point_yields_fixed_zoom_16_centered() -> None:
    plan = plan_map([45.0], [10.0])
    assert plan is not None
    assert plan.zoom == 16
    assert plan.tiles  # non-empty covering set
    assert len(plan.segments) == 1
    assert len(plan.segments[0]) == 1
    x, y = plan.segments[0][0]
    assert x == pytest.approx(VIEWPORT_WIDTH / 2)
    assert y == pytest.approx(VIEWPORT_HEIGHT / 2)


def test_subpixel_bounding_box_is_degenerate() -> None:
    # Two points a ten-millionth of a degree apart: sub-pixel even at zoom 17.
    plan = plan_map([45.0, 45.0000001], [10.0, 10.0000001])
    assert plan is not None
    assert plan.zoom == 16
    assert plan.tiles


# --- absent data ------------------------------------------------------------
def test_no_position_returns_none() -> None:
    assert plan_map([], []) is None
    assert plan_map([None, None], [None, None]) is None
    # Latitude present but longitude absent at every index -> no complete pair.
    assert plan_map([1.0, 2.0], [None, None]) is None
    # Present values never coincide at the same index -> no complete pair.
    assert plan_map([1.0, None], [None, 2.0]) is None


def test_zero_is_a_real_position_not_absent() -> None:
    # A recorded 0.0 is an ordinary coordinate (presence via ``is not None``).
    plan = plan_map([0.0], [0.0])
    assert plan is not None
    assert len(plan.segments) == 1


# --- gap handling -----------------------------------------------------------
def test_gap_splits_route_into_multiple_segments() -> None:
    lats = [0.0, 0.001, None, 0.003, 0.004]
    lons = [0.0, 0.001, None, 0.003, 0.004]
    plan = plan_map(lats, lons)
    assert plan is not None
    assert len(plan.segments) == 2
    assert len(plan.segments[0]) == 2
    assert len(plan.segments[1]) == 2


def test_gap_in_either_channel_breaks_segment() -> None:
    # A hole in longitude alone splits the route exactly as a latitude hole.
    lats = [0.0, 0.001, 0.002, 0.003]
    lons = [0.0, 0.001, None, 0.003]
    plan = plan_map(lats, lons)
    assert plan is not None
    assert len(plan.segments) == 2


# --- tile enumeration -------------------------------------------------------
def test_tiles_are_row_major_and_y_clamped() -> None:
    plan = plan_map([45.0], [10.0])
    assert plan is not None
    # Every tile is at the plan zoom.
    assert {t.z for t in plan.tiles} == {plan.zoom}
    # Tile y range is clamped to the valid [0, 2**z - 1] band.
    max_index = 2**plan.zoom - 1
    assert all(0 <= t.y <= max_index for t in plan.tiles)
    # Row-major order: y outer, x inner.
    assert list(plan.tiles) == sorted(plan.tiles, key=lambda t: (t.y, t.x))
    # No duplicates.
    assert len(set(plan.tiles)) == len(plan.tiles)


def test_out_of_band_viewport_y_is_clamped_per_zoom() -> None:
    # An almost-global route frames at zoom 1, where the raw viewport y-range
    # escapes the valid [0, 2**z - 1] band: a near-north-pole route pushes the
    # top edge above the world (raw y_min == -1), a near-south-pole route pushes
    # the bottom edge below it (raw y_max == 2**z). The per-zoom clamp must keep
    # every emitted tile y in band -- dropping it would surface negative or
    # over-max tile rows here, which the mid-latitude clamp test cannot see.
    north = plan_map([60.0, 84.0], [-170.0, 170.0])
    assert north is not None
    assert north.zoom == 1
    north_max = 2**north.zoom - 1
    # Precondition: the raw (unclamped) viewport top escapes below row 0, so the
    # clamp genuinely fires here rather than the assertion passing vacuously.
    assert math.floor(north.origin_y / TILE_SIZE) < 0
    assert all(0 <= t.y <= north_max for t in north.tiles)

    # The far-south twin exercises the raw y_max > max_index side of the clamp.
    south = plan_map([-84.0, -60.0], [-170.0, 170.0])
    assert south is not None
    assert south.zoom == 1
    south_max = 2**south.zoom - 1
    assert math.floor((south.origin_y + VIEWPORT_HEIGHT) / TILE_SIZE) > south_max
    assert all(0 <= t.y <= south_max for t in south.tiles)


def test_tiles_cover_the_viewport() -> None:
    plan = plan_map([45.0], [10.0])
    assert plan is not None
    # The covering set spans at least the tiles the 800x500 viewport overlaps.
    xs = {t.x for t in plan.tiles}
    ys = {t.y for t in plan.tiles}
    # 800 px over 256-px tiles -> at least 4 columns; 500 px -> at least 2 rows.
    assert len(xs) >= 4
    assert len(ys) >= 2


# --- contract shape ---------------------------------------------------------
def test_plan_is_frozen_value_object() -> None:
    plan = plan_map([45.0], [10.0])
    assert isinstance(plan, MapPlan)
    ref = plan.tiles[0]
    assert isinstance(ref, TileRef)
    with pytest.raises(FrozenInstanceError):
        ref.x = 999  # type: ignore[misc]
    with pytest.raises(FrozenInstanceError):
        plan.zoom = 3  # type: ignore[misc]


# ============================================================================
# compose_map -- self-contained SVG composition (Req 2.1, 2.2, 2.7, 4.1, 6.1)
# ============================================================================

_TINT = "#123456"
_ATTRIBUTION = "© OpenStreetMap contributors"


def _tile_bytes(ref: TileRef) -> bytes:
    """Distinct per-tile pseudo-PNG bytes.

    ``compose_map`` only base64-encodes whatever bytes it is handed, so these
    need not be a valid PNG. Making each tile's bytes unique lets a test assert
    the emitted ``<image>`` order matches ``plan.tiles`` order by locating each
    tile's (necessarily distinct) base64 payload in the document.
    """
    return b"\x89PNG\r\n\x1a\n" + bytes((ref.z & 0xFF, ref.x & 0xFF, ref.y & 0xFF))


def _tiles_for(plan: MapPlan) -> dict[TileRef, bytes]:
    return {ref: _tile_bytes(ref) for ref in plan.tiles}


def _multi_segment_plan() -> MapPlan:
    """A realistic plan: a two-segment gap-split route covering several tiles."""
    lats = [45.0, 45.001, 45.002, None, 45.004, 45.005]
    lons = [10.0, 10.001, 10.002, None, 10.004, 10.005]
    plan = plan_map(lats, lons)
    assert plan is not None
    assert len(plan.segments) == 2
    return plan


def _hand_plan(
    segments: tuple[tuple[tuple[float, float], ...], ...],
) -> MapPlan:
    """A minimal single-tile plan with caller-chosen viewport-pixel segments."""
    return MapPlan(
        zoom=16,
        width=800,
        height=500,
        origin_x=100 * 256 - 10.0,
        origin_y=200 * 256 - 20.0,
        tiles=(TileRef(16, 100, 200),),
        segments=segments,
    )


# --- determinism (4.1) ------------------------------------------------------
def test_compose_is_byte_identical_for_identical_inputs() -> None:
    plan = _multi_segment_plan()
    tiles = _tiles_for(plan)
    first = compose_map(plan, tiles, tint=_TINT, attribution=_ATTRIBUTION)
    second = compose_map(plan, tiles, tint=_TINT, attribution=_ATTRIBUTION)
    assert first == second
    # A freshly-built (equal) tiles mapping yields the same bytes, too: base64
    # of identical bytes is identical regardless of dict identity.
    third = compose_map(plan, _tiles_for(plan), tint=_TINT, attribution=_ATTRIBUTION)
    assert first == third


# --- self-contained: no external references (6.1) --------------------------
def test_compose_references_no_external_resources() -> None:
    plan = _multi_segment_plan()
    svg = compose_map(plan, _tiles_for(plan), tint=_TINT, attribution=_ATTRIBUTION)

    # A complete SVG document rooted at <svg> with the namespace.
    assert svg.startswith("<svg")
    assert SVG_NAMESPACE in svg

    # No scripts, no legacy xlink href.
    assert "<script" not in svg
    assert "xlink" not in svg

    # Every href is a self-contained data: URI -- no remote tile references.
    hrefs = re.findall(r'href="([^"]*)"', svg)
    assert hrefs  # tiles are present
    assert all(h.startswith("data:image/png;base64,") for h in hrefs)

    # The only absolute URL anywhere is the SVG namespace literal in xmlns.
    urls = re.findall(r'https?://[^\s"\'<>]+', svg)
    assert set(urls) == {SVG_NAMESPACE}


# --- tiles are the bottom layer, in plan order (4.1) -----------------------
def test_tiles_are_bottom_layer_in_plan_order() -> None:
    plan = _multi_segment_plan()
    tiles = _tiles_for(plan)
    svg = compose_map(plan, tiles, tint=_TINT, attribution=_ATTRIBUTION)

    # Tiles (images) precede the route (polylines) and the markers (circles).
    assert svg.index("<image") < svg.index("<polyline")
    assert svg.index("<polyline") < svg.index("<circle")

    # Images appear in exactly plan.tiles order (distinct payloads per tile).
    payloads = [base64.b64encode(tiles[ref]).decode("ascii") for ref in plan.tiles]
    positions = [svg.index(p) for p in payloads]
    assert positions == sorted(positions)
    assert len(set(positions)) == len(positions)


def test_tile_image_is_placed_at_its_viewport_offset() -> None:
    plan = _hand_plan(segments=(((10.0, 20.0),),))
    ref = plan.tiles[0]
    svg = compose_map(plan, _tiles_for(plan), tint=_TINT, attribution=_ATTRIBUTION)
    exp_x = fmt_num(ref.x * 256 - plan.origin_x)
    exp_y = fmt_num(ref.y * 256 - plan.origin_y)
    assert f'<image x="{exp_x}" y="{exp_y}" width="256" height="256"' in svg


def test_missing_tile_bytes_raise_keyerror() -> None:
    # compose requires full coverage of plan.tiles; sync guarantees it.
    plan = _hand_plan(segments=(((10.0, 20.0),),))
    with pytest.raises(KeyError):
        compose_map(plan, {}, tint=_TINT, attribution=_ATTRIBUTION)


# --- route glow: wide translucent underlay + narrow opaque foreground (2.1) -
def test_each_segment_yields_underlay_and_foreground() -> None:
    plan = _multi_segment_plan()
    n = len(plan.segments)
    svg = compose_map(plan, _tiles_for(plan), tint=_TINT, attribution=_ATTRIBUTION)

    # Two polylines per segment: one wide translucent, one narrow opaque.
    assert svg.count("<polyline") == 2 * n
    assert svg.count('stroke-width="10"') == n
    assert svg.count('stroke-opacity="0.2"') == n
    assert svg.count('stroke-width="4"') == n
    assert svg.count('stroke-opacity="0.95"') == n

    # The wide translucent underlay is drawn beneath (before) the foreground.
    assert svg.index('stroke-width="10"') < svg.index('stroke-width="4"')

    # Both layers wear the tint, round caps and joins, and no fill.
    assert f'stroke="{_TINT}"' in svg
    assert svg.count('stroke-linecap="round"') == 2 * n
    assert svg.count('stroke-linejoin="round"') == 2 * n
    assert svg.count('fill="none"') == 2 * n


# --- single-point segment renders as a dot (2.1) ---------------------------
def test_single_point_segment_renders_as_dot() -> None:
    pt = (400.0, 250.0)
    plan = _hand_plan(segments=((pt,),))
    svg = compose_map(plan, _tiles_for(plan), tint=_TINT, attribution=_ATTRIBUTION)
    coord = f"{fmt_num(pt[0])},{fmt_num(pt[1])}"
    # A zero-length round-cap stroke: the point duplicated so the cap shows.
    assert f'points="{coord} {coord}"' in svg
    # Still both glow layers (underlay + foreground) so the dot glows too.
    assert svg.count("<polyline") == 2


# --- start / finish markers at the route endpoints (2.2) -------------------
def test_start_and_finish_markers_at_route_endpoints() -> None:
    plan = _multi_segment_plan()
    svg = compose_map(plan, _tiles_for(plan), tint=_TINT, attribution=_ATTRIBUTION)

    start = plan.segments[0][0]  # first point of the first segment
    finish = plan.segments[-1][-1]  # last point of the last segment

    circles = re.findall(r"<circle[^>]*/>", svg)
    assert len(circles) == 2

    start_circles = [c for c in circles if f'fill="{ROUTE_START_COLOR}"' in c]
    finish_circles = [c for c in circles if f'fill="{ROUTE_FINISH_COLOR}"' in c]
    assert len(start_circles) == 1
    assert len(finish_circles) == 1

    assert f'cx="{fmt_num(start[0])}"' in start_circles[0]
    assert f'cy="{fmt_num(start[1])}"' in start_circles[0]
    assert f'cx="{fmt_num(finish[0])}"' in finish_circles[0]
    assert f'cy="{fmt_num(finish[1])}"' in finish_circles[0]

    # Each marker is r=5 with a 1.5 px white stroke.
    for circle in (start_circles[0], finish_circles[0]):
        assert 'r="5"' in circle
        assert 'stroke-width="1.5"' in circle


# --- attribution: legible text over a translucent backing (2.7) ------------
def test_attribution_text_over_backing_rect_is_escaped() -> None:
    attribution = 'Tiles & data <src> "prov"'
    plan = _hand_plan(segments=(((10.0, 20.0),),))
    svg = compose_map(plan, _tiles_for(plan), tint=_TINT, attribution=attribution)

    # Attribution text is XML-escaped -- the raw form never reaches the markup.
    assert "Tiles &amp; data &lt;src&gt; &quot;prov&quot;" in svg
    assert attribution not in svg

    # A translucent white backing rect sits behind the 10 px text.
    rects = re.findall(r"<rect[^>]*/>", svg)
    backings = [r for r in rects if 'fill="#ffffff"' in r and 'fill-opacity="0.8"' in r]
    assert len(backings) == 1
    assert 'font-size="10"' in svg

    # The backing rect precedes (sits beneath) the attribution text.
    assert svg.rindex("<rect") < svg.rindex("<text")
