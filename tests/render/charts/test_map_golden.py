"""Golden coverage for the composed route-map SVG (Req 2.1-2.4, 2.6, 2.7, 4.1, 6.1).

The behavioral shape of ``compose_map`` is pinned structurally in
``test_map.py``; this module pins its *exact bytes* against committed golden
SVGs, one per reference scenario, exactly as ``test_hero.py`` /``test_zones.py``
do for the other charts. A golden regression here means the composed appearance
changed -- deliberately (regenerate) or by accident (a bug).

Each golden is composed from a **fixed fake basemap value**: a ``Basemap`` whose
bytes are a short literal, not an image. ``compose_map`` embeds a basemap without
decoding it, so no image library and no tile enters these goldens, and nothing
here depends on a platform's encoder. The placement (-1/3, -2/3) is chosen so it
cannot be written exactly with two decimals. One golden ``.svg`` per scenario:
the ride tint, the run tint, the neutral tint, a gap-split route (a ``None`` gap
yields >= 2 segments), a single-point route (the zoom-16 centered fallback
rendered as a dot), and an attribution block whose text carries an ``&`` to prove
XML escaping survives into the committed bytes.

The invariants under test:

* **Byte-for-byte match (4.1)** -- ``compose_map`` over each scenario equals its
  committed golden; a missing golden or fixture fails loudly.
* **Determinism (4.1)** -- each scenario composes byte-identically across calls.
* **Self-contained (6.1)** -- every golden references no external resource: the
  only absolute URL is the SVG namespace, and every ``href`` is a ``data:`` URI.
* **Fixture provenance** -- the fake basemap's base64 payload appears exactly
  once in every golden, in a single ``data:image/webp`` image.

Regeneration (the "regenerate byte-identically" observable): run this module as
a script -- ``uv run python -m tests.render.charts.test_map_golden`` -- to
rewrite every golden from the *same* ``compose_case`` the tests compare against,
so the committed files and the live comparison can never drift. It is
byte-deterministic in a fixed environment; no personal data or provider tile
enters the repo. Pytest does not run ``main``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from fitdocs.render.charts.map import compose_map, plan_map
from fitdocs.render.charts.palette import (
    ROUTE_BIKE_TINT,
    ROUTE_NEUTRAL_TINT,
    ROUTE_RUN_TINT,
)
from fitdocs.render.charts.svg import SVG_NAMESPACE
from tests.support.basemap import FAKE_BASEMAP, FAKE_PAYLOAD, FAKE_PLACEMENT

GOLDEN_DIR = Path(__file__).parent / "golden"

_OSM_ATTRIBUTION = "© OpenStreetMap contributors"


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
    """Compose one scenario's SVG over the fixed fake basemap.

    The single source of truth shared by the tests and :func:`main`: it plans the
    route and composes it over :data:`FAKE_BASEMAP`. Because the test compares this
    exact output to the committed golden and ``main`` writes the golden from this
    exact output, the two can never drift.
    """
    scenario = GOLDEN_CASES[name]
    plan = plan_map(scenario.lats, scenario.lons)
    assert plan is not None, f"scenario {name} produced no plan"
    assert len(plan.segments) == scenario.segments, (
        f"scenario {name}: expected {scenario.segments} segment(s), "
        f"got {len(plan.segments)}"
    )
    return compose_map(
        plan, FAKE_BASEMAP, tint=scenario.tint, attribution=scenario.attribution
    )


# --- fixture provenance ------------------------------------------------------
def test_goldens_embed_the_fake_basemap_once() -> None:
    for name in GOLDEN_CASES:
        golden = GOLDEN_DIR / f"{name}.svg"
        assert golden.exists(), f"missing golden: {golden}"
        svg = golden.read_text()
        assert svg.count("<image") == 1, f"golden {name} is not one image"
        assert svg.count(f"data:image/webp;base64,{FAKE_PAYLOAD}") == 1
        assert FAKE_PLACEMENT in svg


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
        # The basemap reference is an inline data: URI -- no remote tiles.
        hrefs = re.findall(r'href="([^"]*)"', svg)
        assert hrefs, f"golden {name} embeds no basemap"
        assert all(h.startswith("data:image/webp;base64,") for h in hrefs)
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
    """Rewrite every golden from the shared code above.

    Writes ``golden/<name>.svg`` for every scenario via :func:`compose_case` --
    the same function the tests compare against. Byte-deterministic, so
    re-running leaves the working tree unchanged when nothing intentional has
    changed.
    """
    GOLDEN_DIR.mkdir(parents=True, exist_ok=True)
    for name in GOLDEN_CASES:
        path = GOLDEN_DIR / f"{name}.svg"
        path.write_text(compose_case(name), encoding="utf-8")
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
