# Brief: route-maps

## Problem

Outdoor workout docs are missing the route map fitdocs.ai renders. For runs
and rides, *where* the workout happened is a core part of the record; today
the generated doc has charts and metrics but no spatial view of the activity.

## Current State

- fit-ingest already delivers per-sample GPS: `Samples.latitude_deg` /
  `longitude_deg` (semicircles converted to decimal degrees, `None` gaps
  preserved) — see `src/fitdocs/model.py:113`.
- workout-docs renders docs with static SVG chart assets from a hand-built
  SVG writer (`src/fitdocs/render/charts/`), placed relative to the doc and
  embedded as image links. Route maps were explicitly deferred from v1
  because of the tile dependency.
- fitdocs.ai reference look (`docs/reference/fitdocs-ai-reference.md`):
  non-interactive Leaflet on ESRI World Topo tiles; glow polyline;
  start/end pins; tint bike `#1f4d8a`, run `#b22d4a`.
- **Measured on real HealthFit/Stryd exports (3 FIT+GPX pairs, 2026-07-16)**:
  the GPX sidecar is the identical track re-encoded — 1:1 trackpoint match,
  median horizontal delta 3 mm / max 8 mm (pure FIT semicircle quantization,
  ~9 mm resolution), elevation delta ±0.1 m (FIT altitude scale rounding).
  Only additions are `hAcc`/`vAcc` accuracy estimates. GPX ingestion
  therefore gains nothing; the map renders from FIT channels alone.

## Desired Outcome

Any activity with position samples gets a map section in its doc: the route
drawn as a glow polyline with start/finish markers over real basemap tiles
(fitdocs.ai visual style), produced as a static SVG asset alongside the
charts. Activities without position data (indoor, strength, pool) omit the
section cleanly. Regenerating a doc from a warm tile cache is byte-identical
and works offline.

## Approach

SVG with embedded raster tiles, reusing the chart asset pipeline:

1. Compute the route bounding box → choose a slippy-map zoom level → fetch
   the covering tile set with stdlib `urllib` from a configurable tile
   provider (default matching the fitdocs.ai look, e.g. ESRI World Topo).
2. Cache tiles under the data root (e.g.
   `<data-root>/.cache/tiles/<provider>/<z>/<x>/<y>.png`). First render of a
   new area needs network; every re-render is offline and deterministic.
3. Author the map as SVG via the existing chart-writer pattern: tiles
   embedded as base64 data URIs, route projected (Web Mercator → pixel
   coords) and drawn as a vector glow polyline with start/finish pins,
   sport tint colors, and provider attribution text.
4. Graceful degradation: no position samples → no map section; tile cache
   miss while offline → omit the map with a warning, never fail the doc;
   `None` position gaps break the polyline rather than interpolating.

Why: zero new dependencies (no Pillow, no HTTP client), output is text we
fully control (robust byte-identical determinism), vector-crisp route, and
the asset/link conventions are identical to charts.

## Scope

- **In**: map SVG generation for any activity with position samples; tile
  fetch + local cache; tile-provider configuration and attribution; zoom /
  extent / padding selection; glow polyline + start/finish pins with sport
  tints; doc integration for run, bike, and generic outdoor layouts;
  omission rules and offline behavior; opt-out flag/config for users who
  don't want tile requests leaving their machine.
- **Out**: GPX/TCX ingestion (measured: no gain); interactive/pannable
  maps; route-name overlay (requires reverse geocoding service); privacy
  zones (home-location masking) — likely future work; aggregate/multi-
  activity maps.

## Boundary Candidates

- Tile acquisition (fetch, cache, provider config, politeness/attribution)
- Map composition (projection math, zoom selection, SVG authoring, styling)
- Doc integration (section placement per layout, omission rules)

## Out of Boundary

- fit-ingest model changes (lat/long channels already exist)
- Existing chart rendering
- The `enhanced_avg_speed` list-value lap-parsing bug found during
  discovery (direct fix, tracked separately)

## Upstream / Downstream

- **Upstream**: fit-ingest (`Samples` position channels), workout-docs
  (doc layout contract, asset placement, SVG writer + palette, config).
- **Downstream**: privacy zones, route-name overlays, plan-level or weekly
  aggregate maps.

## Existing Spec Touchpoints

- **Extends**: workout-docs — adds a Map section to the run/bike/generic
  section orders (small template-contract change) and carves out the
  byte-identical output requirement to "byte-identical given a warm tile
  cache; tile fetch is the only permitted network access".
- **Adjacent**: training-load (no interaction).

## Constraints

- Regeneration from a warm cache must be byte-identical and offline; tile
  fetch is the only network access, and only on cache miss.
- Tile provider terms: attribution rendered on the map; provider URL
  template configurable; polite fetching (identifying user-agent, modest
  concurrency). Verify chosen default provider's terms permit this use.
- Personal-data posture: tile requests reveal approximate activity
  location (at tile granularity) to the provider — document it and honor
  the opt-out. Cached tiles live under the data root, never the repo.
- Output stays plain markdown + image links; the SVG (with data-URI
  rasters) must render in Obsidian and GitHub.
