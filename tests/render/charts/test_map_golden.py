"""Golden coverage for the composed route-map SVG (Req 2.1-2.4, 2.6, 2.7, 4.1, 6.1).

The behavioral shape of ``compose_map`` is pinned structurally in
``test_map.py``; this module pins its *exact bytes* against committed golden
SVGs, one per reference scenario, exactly as ``test_hero.py`` /``test_zones.py``
do for the other charts. A golden regression here means the composed appearance
changed -- deliberately (regenerate) or by accident (a bug).

Two things are committed and read from disk, never fabricated at compare time:

* **A synthetic fixture tile PNG** (``golden/tiles/fixture_tile.png``) generated
  with the standard library alone (``zlib`` + ``struct`` -> a minimal valid
  ``IHDR``/``IDAT``/``IEND`` PNG). It is a solid-color raster: license-clean, no
  basemap-provider tile is ever downloaded or redistributed. Its committed bytes
  are the stable source every golden embeds as base64 (a tile's real pixels are
  irrelevant -- the SVG ``<image>`` sizes it to 256).
* **One golden ``.svg`` per scenario** composed via ``compose_map`` from that
  fixture: the ride tint, the run tint, the neutral tint, a gap-split route (a
  ``None`` gap yields >= 2 segments), a single-point route (the zoom-16 centered
  fallback rendered as a dot), and an attribution block whose text carries an
  ``&`` to prove XML escaping survives into the committed bytes.

The invariants under test:

* **Byte-for-byte match (4.1)** -- ``compose_map`` over each scenario equals its
  committed golden; a missing golden or fixture fails loudly.
* **Determinism (4.1)** -- each scenario composes byte-identically across calls.
* **Self-contained (6.1)** -- every golden references no external resource: the
  only absolute URL is the SVG namespace, and every ``href`` is a ``data:`` URI.
* **Fixture provenance** -- the committed fixture's base64 payload actually
  appears in every golden, so the goldens are pinned to the committed PNG bytes.

Regeneration (the "regenerate byte-identically" observable): run this module as
a script -- ``uv run python -m tests.render.charts.test_map_golden`` -- to
rewrite the fixture PNG and every golden from the *same* ``compose_case`` /
``_solid_png`` the tests compare against, so the committed files and the live
comparison can never drift. It is byte-deterministic in a fixed environment; no
personal data or provider tile enters the repo. Pytest does not run ``main``.
"""

from __future__ import annotations

import base64
import re
import struct
import zlib
from dataclasses import dataclass
from pathlib import Path

from fitdocs.render.charts.map import compose_map, plan_map
from fitdocs.render.charts.palette import (
    ROUTE_BIKE_TINT,
    ROUTE_NEUTRAL_TINT,
    ROUTE_RUN_TINT,
)
from fitdocs.render.charts.svg import SVG_NAMESPACE

GOLDEN_DIR = Path(__file__).parent / "golden"
TILES_DIR = GOLDEN_DIR / "tiles"
FIXTURE_TILE = TILES_DIR / "fixture_tile.png"

#: The solid fixture color (RGB). Arbitrary and fixed -- the pixels never show
#: through the route/markers/attribution the goldens are really pinning.
_FIXTURE_RGB = (46, 139, 120)
_FIXTURE_SIZE = 4  # a 4x4 raster; the SVG <image> sizes every tile to 256

_OSM_ATTRIBUTION = "© OpenStreetMap contributors"


# --- synthetic PNG (stdlib only, deterministic, license-clean) --------------
def _png_chunk(tag: bytes, data: bytes) -> bytes:
    """One PNG chunk: length + type + data + CRC32(type + data), all big-endian."""
    return (
        struct.pack(">I", len(data))
        + tag
        + data
        + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    )


def _solid_png(size: int, rgb: tuple[int, int, int]) -> bytes:
    """A minimal valid solid-color ``size``x``size`` 8-bit truecolor PNG.

    Emitted by hand from ``zlib`` + ``struct`` -- signature, ``IHDR`` (color
    type 2 / RGB), a single zlib-compressed ``IDAT`` of filter-0 scanlines, and
    ``IEND``. Deterministic for identical inputs (fixed zlib level), so
    regeneration reproduces byte-identical committed fixture bytes.
    """
    signature = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)
    scanline = b"\x00" + bytes(rgb) * size  # filter byte 0 (None) + RGB pixels
    raw = scanline * size
    idat = zlib.compress(raw, 9)
    return (
        signature
        + _png_chunk(b"IHDR", ihdr)
        + _png_chunk(b"IDAT", idat)
        + _png_chunk(b"IEND", b"")
    )


# --- reference scenarios ----------------------------------------------------
@dataclass(frozen=True)
class _Scenario:
    """One golden case: the position channels, the sport tint, the attribution.

    ``segments`` is the number of gap-split segments ``plan_map`` must yield --
    an assertion guarding the scenario against silently degrading (e.g. the
    gap-split route collapsing to one segment).
    """

    lats: tuple[float | None, ...]
    lons: tuple[float | None, ...]
    tint: str
    attribution: str
    segments: int


# A short, stable curved route shared by the three tint scenarios: identical
# geometry, so their goldens differ only in the stroke tint (2.3).
_ROUTE_LATS: tuple[float | None, ...] = (45.0, 45.0008, 45.0016, 45.0022, 45.0030)
_ROUTE_LONS: tuple[float | None, ...] = (10.0, 10.0010, 10.0016, 10.0026, 10.0032)

GOLDEN_CASES: dict[str, _Scenario] = {
    # 1-3: sport tints over one shared route (2.1, 2.2, 2.3, 2.7).
    "map_ride_tint": _Scenario(
        _ROUTE_LATS, _ROUTE_LONS, ROUTE_BIKE_TINT, _OSM_ATTRIBUTION, segments=1
    ),
    "map_run_tint": _Scenario(
        _ROUTE_LATS, _ROUTE_LONS, ROUTE_RUN_TINT, _OSM_ATTRIBUTION, segments=1
    ),
    "map_neutral_tint": _Scenario(
        _ROUTE_LATS, _ROUTE_LONS, ROUTE_NEUTRAL_TINT, _OSM_ATTRIBUTION, segments=1
    ),
    # 4: a None gap breaks the route into two segments (2.4).
    "map_gap_split": _Scenario(
        (45.0, 45.001, 45.002, None, 45.004, 45.005),
        (10.0, 10.001, 10.002, None, 10.004, 10.005),
        ROUTE_RUN_TINT,
        _OSM_ATTRIBUTION,
        segments=2,
    ),
    # 5: a lone position -> zoom-16 centered fallback, rendered as a dot (2.6).
    "map_single_point": _Scenario(
        (45.0,), (10.0,), ROUTE_BIKE_TINT, _OSM_ATTRIBUTION, segments=1
    ),
    # 6: a distinctive attribution with & < > " proves XML escaping in the bytes.
    "map_attribution": _Scenario(
        (45.0, 45.0012),
        (10.0, 10.0014),
        ROUTE_NEUTRAL_TINT,
        'Map data © Example & Co <tiles> "v2"',
        segments=1,
    ),
}


def compose_case(name: str) -> str:
    """Compose one scenario's SVG from the *committed* fixture tile bytes.

    The single source of truth shared by the tests and :func:`main`: it plans the
    route, maps every tile the plan requires to the committed fixture PNG's bytes
    (read from disk -- the stable byte-source, one solid fixture for all tiles),
    and composes. Because the test compares this exact output to the committed
    golden and ``main`` writes the golden from this exact output, the two can
    never drift.
    """
    scenario = GOLDEN_CASES[name]
    plan = plan_map(scenario.lats, scenario.lons)
    assert plan is not None, f"scenario {name} produced no plan"
    assert len(plan.segments) == scenario.segments, (
        f"scenario {name}: expected {scenario.segments} segment(s), "
        f"got {len(plan.segments)}"
    )
    tile_bytes = FIXTURE_TILE.read_bytes()
    tiles = {ref: tile_bytes for ref in plan.tiles}
    return compose_map(
        plan, tiles, tint=scenario.tint, attribution=scenario.attribution
    )


# --- fixture provenance -----------------------------------------------------
def test_fixture_tile_is_committed_and_is_a_valid_png() -> None:
    assert FIXTURE_TILE.exists(), f"missing fixture tile: {FIXTURE_TILE}"
    data = FIXTURE_TILE.read_bytes()
    # A real PNG signature + the trailing IEND chunk: a minimal valid raster,
    # not an empty or truncated file.
    assert data.startswith(b"\x89PNG\r\n\x1a\n")
    assert data.endswith(b"IEND\xaeB`\x82")
    # License-clean: regenerating from stdlib reproduces the committed bytes,
    # so no provider tile was ever substituted.
    assert data == _solid_png(_FIXTURE_SIZE, _FIXTURE_RGB)


def test_goldens_embed_the_committed_fixture_bytes() -> None:
    payload = base64.b64encode(FIXTURE_TILE.read_bytes()).decode("ascii")
    for name in GOLDEN_CASES:
        golden = GOLDEN_DIR / f"{name}.svg"
        assert golden.exists(), f"missing golden: {golden}"
        # The committed PNG is the byte-source the golden embeds as base64.
        assert payload in golden.read_text(), f"golden {name} lacks fixture payload"


# --- byte-for-byte match against committed goldens (4.1) --------------------
def test_matches_committed_goldens() -> None:
    for name in GOLDEN_CASES:
        golden = GOLDEN_DIR / f"{name}.svg"
        assert golden.exists(), f"missing golden: {golden}"
        assert compose_case(name) == golden.read_text(), f"golden mismatch for {name}"


# --- determinism (4.1) ------------------------------------------------------
def test_render_is_byte_identical_across_calls() -> None:
    for name in GOLDEN_CASES:
        assert compose_case(name) == compose_case(name), (
            f"non-deterministic composition for {name}"
        )


# --- self-contained: no external references (6.1) --------------------------
def test_goldens_are_self_contained() -> None:
    for name in GOLDEN_CASES:
        svg = (GOLDEN_DIR / f"{name}.svg").read_text()
        assert svg.startswith("<svg")
        assert svg.endswith("</svg>")
        assert "<script" not in svg
        assert "xlink" not in svg
        # Every tile reference is an inline data: URI -- no remote tiles.
        hrefs = re.findall(r'href="([^"]*)"', svg)
        assert hrefs, f"golden {name} embeds no tiles"
        assert all(h.startswith("data:image/png;base64,") for h in hrefs)
        # The only absolute URL anywhere is the SVG namespace literal.
        urls = re.findall(r'https?://[^\s"\'<>]+', svg)
        assert set(urls) == {SVG_NAMESPACE}, f"golden {name} has external URLs"


# --- attribution escaping is preserved in the committed bytes (2.7) ---------
def test_attribution_golden_preserves_xml_escaping() -> None:
    svg = (GOLDEN_DIR / "map_attribution.svg").read_text()
    raw = GOLDEN_CASES["map_attribution"].attribution
    # The escaped form is present; the raw ampersand/brackets/quotes are not.
    assert "Map data © Example &amp; Co &lt;tiles&gt; &quot;v2&quot;" in svg
    assert raw not in svg


# --- regeneration writer (developer utility; pytest does not run this) ------
def main() -> None:
    """Rewrite the fixture tile and every golden from the shared code above.

    Writes ``golden/tiles/fixture_tile.png`` (deterministic stdlib PNG) then
    ``golden/<name>.svg`` for every scenario via :func:`compose_case` -- the same
    function the tests compare against. Byte-deterministic, so re-running leaves
    the working tree unchanged when nothing intentional has changed.
    """
    TILES_DIR.mkdir(parents=True, exist_ok=True)
    FIXTURE_TILE.write_bytes(_solid_png(_FIXTURE_SIZE, _FIXTURE_RGB))
    print(f"wrote {FIXTURE_TILE}")
    for name in GOLDEN_CASES:
        path = GOLDEN_DIR / f"{name}.svg"
        path.write_text(compose_case(name), encoding="utf-8")
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
