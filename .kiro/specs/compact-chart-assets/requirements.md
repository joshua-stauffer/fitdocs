# Requirements Document

## Project Description (Input)
Make a long-term fitdocs archive small enough to sync and quick to view. On
the maintainer's archive of 2,569 workouts the chart assets weigh 1,218 MB:
maps 910 MB, hero charts 223 MB, dynamics charts 81 MB. The aim is about
250 MB, with the same filenames, links and look. There are three changes.

- **Thin line geometry to output resolution.** Use a shared, deterministic
  output-space polyline simplifier (Ramer–Douglas–Peucker at about 0.3 px,
  1-decimal coordinates). Apply it to the hero chart's series and backdrop,
  which covers the dynamics chart because it reuses `render_hero_chart`,
  and to the map's route polylines.
- **Flatten each map's basemap into one raster.** Composite the cached tiles
  onto one canvas cropped to the viewport, at the tiles' native pixel
  density, and encode it as WebP q75. Embed it as a single `data:image/webp`
  image under the unchanged vector route, markers and attribution.
  - Pillow (`>=13.0.0`) becomes a core dependency, imported by one render
    module only.
  - Tile bytes are decoded through an explicit format allow list.
  - WebP support is checked at runtime.
  - A tile that cannot be decoded ends as a warning with the map omitted.
- **Write workout chart assets only when their bytes change, and replace
  them atomically.**

The change carries amendments to route-maps (the basemap form, the
stdlib-only design statements, the determinism wording, a new cause of map
omission) and to workout-docs (Req 7.4's static adaptation, the 2-decimal
coordinate statement, the asset write semantics). It carries a wiki-contract
amendment only if the "regen replaces every chart asset" wording is a
published guarantee.

Out of scope:
- a route-only basemap setting;
- basemap quality and scale settings;
- per-year asset folders;
- chart-kit thinning;
- tile fetch, cache and provider settings;
- asset naming.

Discovery context, measurements and viability:
`.kiro/specs/compact-chart-assets/brief.md`; roadmap Phase 13.

## Requirements
<!-- Will be generated in /kiro-spec-requirements phase -->
