# Brief: compact-chart-assets

## Problem

Long-term users sync their fitdocs root to phones and other machines with
Obsidian Sync, iCloud, Dropbox and similar tools. On the maintainer's real
archive (2,569 workouts, measured 2026-10-26 at fitdocs `4f1c1f46`) the
markdown is 15 MB and the chart assets are **1,218 MB** across 7,867 SVGs:

| Chart | Total | Files | Avg | Cause |
|---|---|---|---|---|
| `-map.svg` | 910 MB (75%) | 1,925 | 473 KB | ~12 base64 PNG tiles per map; about half of each tile's area lies outside the 800×500 viewBox; the same tiles repeat across workouts on the same routes |
| `-hero.svg` | 223 MB | 2,484 | 90 KB | a path point per source sample, about 5 per output pixel, including long runs of identical y values |
| `-dynamics.svg` | 81 MB | 971 | 84 KB | same oversampling as hero |
| `-zones.svg` | 3 MB | 2,479 | 1.2 KB | fine as is |

The pain, in the maintainer's words (2026-10-26):

- **Sync size and quota.** Obsidian Sync's cheaper plan holds 1 GB per
  vault. The charts alone decide whether the vault fits, and the maintainer
  is blocked from adopting Obsidian by the size of the files.
- **Viewer lag.** iA Writer, the current viewer, is slow and laggy on workout
  notes. Each map makes the viewer decode about 12 embedded PNGs (~500 KB),
  and each hero or dynamics chart carries about 5 points per output pixel.
- **Churn.** `fitdocs regen` on 2026-10-19 rewrote every asset, and every
  mtime moved. Each regen can add up to 1.2 GB of version history to Obsidian
  Sync, Time Machine or a PKM git repository.

Every long-term user hits this, and it grows with every workout. By year:
2024 273 MB, 2025 222 MB, 2026 151 MB.

## Current State

- **Maps.** `_render_tiles` (`src/fitdocs/render/charts/map.py:292-317`)
  emits one 256×256 `<image href="data:image/png;base64,…">` per covering
  tile. There are up to 15 tiles at fractional offsets, and the SVG's
  overflow clipping crops them at the viewport edge (route-maps
  `design.md:334`). Cached bytes are embedded verbatim
  (`design.md:397`, `:598`). The MIME type is hard-coded whatever the
  provider serves (`map.py:313`).
  - `_render_route` (`map.py:336-357`) writes each route segment twice: a
    10 px underlay and a 4 px foreground polyline. Both use `fmt_num`
    (2 decimals).
  - `map.py`'s docstring (`:34-41`) and route-maps `design.md:52`, `:120`
    and `:283` state that the module is stdlib-only, with zero new
    dependencies.
- **Hero and dynamics.**
  - `render_hero_chart` (`src/fitdocs/render/charts/hero.py`) writes one
    point per input sample after `boxcar_smooth` (`series.py:34-70`, an
    11-sample window). It draws one polyline per gap segment (`:250-280`) and
    one backdrop path (`:210-247`), and formats coordinates with `_coord` →
    `fmt_num` (`hero.py:206`, `svg.py:44-66`).
  - The dynamics chart reuses `render_hero_chart` (`dynamics.py:172-214`).
    One change therefore covers both.
  - Nothing in `src/` downsamples a chart. The fitdocs.ai reference says
    "no downsampling" (`docs/reference/fitdocs-ai-reference.md:123-124`).
    workout-docs Req 7.4 follows that reference "adapted only where static
    rendering demands".
- **Asset writes.** `_write_assets` (`src/fitdocs/sync.py:2570-2575`) calls a
  plain `write_text` with no compare and no atomic replace. `regen`
  (`sync.py:1211-1290`) re-renders every page and asset on every run. Other
  subsystems already compare before they write, and do it atomically:
  - morning: `morning/engine.py:82-84`;
  - dashboards: `dashboards/storage.py:262-287`;
  - recovery: `_write_if_changed`, `recovery/engine.py:100-114`.

  `docs/ownership-contract.md:424` says regeneration replaces "every chart
  asset".
- **Dependencies.** fitdocs has no image library today. The dependency set
  is pinned exactly by these tests:
  - `tests/test_determinism.py:671-714`;
  - `tests/test_packaging.py:503-514`;
  - the offline-install venv test (`tests/test_packaging.py:1036-1085`).

  `tech.md` keeps the footprint small, and its "No matplotlib dependency
  unless a spec proves we need it" line is the precedent for a spec
  justifying one.
- **Tests that move.**
  - Exact-byte SVG goldens: 4 hero and 6 map files in
    `tests/render/charts/golden/`, plus 9 hero, 3 dynamics and 3 map files in
    `tests/render/golden_docs/`.
  - Structural pins:
    - `test_hero.py:244-246` asserts plotted points == non-None samples;
    - `test_map.py:361`, `:375` and `:391` assert `data:image/png`, image
      order, and 256×256 tile elements;
    - `test_map_golden.py:195-233` asserts the fixture PNG's base64 appears
      in each golden;
    - `test_determinism.py:375-386` asserts the synthetic tile's data URI
      appears in the map asset.
  - Most fake tiles in tests are only the PNG signature. Seven sites say
    they "need not be a valid PNG"; the valid fixtures are 4×4.
- **Queue.**
  `.kiro/queue/closed/2026-08-23-map-svgs-inline-the-basemap-per-document.md`
  (725 MB of assets from a 40 MB tile cache) is promoted to this spec by
  this discovery.

## Desired Outcome

- The charts for the measured archive shrink from **~1,218 MB to ~250 MB**.
  The projection uses the experiments below.
  - Map average: 507 → ~114 KB.
  - Hero: 100.6 → ~10.7 KB.
  - Dynamics: 85.8 → ~16.6 KB.
- Line charts look the same. The basemap is at most very slightly softer.
  Labels, route, markers and attribution stay intact.
- A regen that changes nothing writes no asset. A changed asset is replaced
  atomically.
- Asset filenames, markdown links and the `assets/` layout do not change.
  One `fitdocs regen` migrates an existing archive in place.
- Maps still display, with no plugins, scripts or network access at view
  time (route-maps Req 6.1/6.2), in:
  - Obsidian desktop and mobile;
  - iA Writer;
  - GitHub;
  - Safari.

## Approach

**Chosen (maintainer, 2026-10-26): render at output resolution, flatten the
basemap into one WebP raster through Pillow as a core dependency, and write
assets only when their bytes change.**

1. **Thin line geometry in output space.** Ramer–Douglas–Peucker at about
   0.3 px in output coordinates, coordinates rounded to 1 decimal, endpoints
   and gap-segment boundaries kept. Applies to the hero series and backdrop
   (and so to dynamics) and to the map route polyline pair. Measured on 40
   random files per kind: hero −89%, dynamics −81%, with no visible
   difference side by side. Integer coordinates would reach −92% / −85%.
2. **Flatten the basemap.**
   - Decode the cached tiles with Pillow and composite them onto one canvas
     cropped to the 800×500 viewport.
   - Encode the canvas once as WebP q75 and embed it as a single
     `data:image/webp` `<image>` under the unchanged vector route, markers
     and attribution.
   - Measured: −66% alone, −78% with item 1.
   - Pillow is imported by one render module only, the way `duckdb` is
     confined to `fitdocs.index.store`.
3. **Write-if-changed, atomic asset writes** for workout chart assets, on the
   pattern recovery and dashboards already use.

Experiments: `artifacts/2026-10-26-chart-asset-size/` in the maintainer's
checkout. It is git-excluded and holds a real route, so it is never
committed. Rejected alternatives:

- **Shared tile files referenced from each map SVG** (the promoted queue
  item's option; the maintainer asked about tile reuse 2026-10-26). This is
  infeasible: an SVG shown as an image loads no external resource.
  - Verified 2026-10-26 in headless Chrome, Obsidian desktop's engine, even
    with file access allowed. An SVG that references a sibling `tile.png`
    rendered blank where the tile should be. The same SVG with a data URI
    rendered, and `tile.png` alone rendered.
  - So every map file must carry its own pixels. Tiles are already reused at
    render time: the cache holds about 40 MB of distinct tiles.
- **Lossless per-tile crop, stdlib only** (no Pillow).
  - How it works: crop each tile to its visible part and keep its own
    palette. A stdlib decode of 12 tiles took 0.04 s.
  - Measured on the same 40-map sample: 507 → 236 KB (−53%) with the route
    thinned, about 470 MB for the archive.
  - The maintainer chose the WebP path for the further halving. This remains
    the fallback if Pillow ever has to go.
- **One cropped PNG without Pillow.** The composite carries 2,343 distinct
  colours, because each tile has its own palette.
  - As RGB PNG it is 755 KB against the original 562 KB.
  - A 256-colour quantization (243 KB) needs a quantizer.
- **gzip / `.svgz`.** Measured only as a reference (−63% to −66% on lines).
  It changes filenames and links, and viewer support was not established.
- **Route-only maps** (about 5 KB). This drops the basemap, so it is deferred
  as an opt-in setting (see Out).

## Scope

- **In**:
  - A shared, deterministic output-space polyline simplifier in
    `render/charts`. `series.py` and `svg.py` are already on the chart-kit
    import allow-list. Its call sites are the hero series and backdrop (and
    so dynamics) and the map route.
  - 1-decimal coordinates for those geometries only.
  - The flattened-WebP basemap:
    - decode, composite and crop, including 512 px `@2x` tiles and
      fractional offsets;
    - WebP q75 at 1×, with the attribution kept as vector text.
  - A tile that cannot be decoded ends as a warning with the map omitted,
    never a failed document (route-maps Req 4.3/4.4 semantics).
  - Pillow as a core runtime dependency: `pyproject.toml`, `uv.lock`, the
    pinned dependency-set tests, `tech.md` Key Libraries, and the route-maps
    stdlib-only statements.
  - The determinism contract re-stated for an encoded raster (see
    Constraints), with a golden strategy to match.
  - Compare-before-write and atomic replace for workout chart assets.
  - Docs:
    - the ownership-contract regen statement;
    - CHANGELOG with a migration note (`fitdocs regen` once);
    - the fitdocs.ai-reference "static adaptation" note for thinning;
    - the route-maps user docs.
  - An optional maintainer-only task: measure the real archive before and
    after.
- **Out** (maintainer, 2026-10-26: no extras this round; recorded as
  follow-on candidates):
  - a route-only basemap setting (`[tiles] basemap = "none"`, about 5 KB
    maps; amends route-maps Req 1.1/5.4);
  - user-tunable basemap quality and scale settings;
  - per-year asset subfolders (they change every chart link);
  - thinning the chart-kit kinds: dashboards, recovery, history and the
    catalogue. Row caps of 1,000–2,000 already bound them, and they appear on
    few pages.
  - Also unchanged:
    - zones charts;
    - tile fetch, cache, provider settings and zoom/framing;
    - asset naming;
    - orphaned-asset cleanup (`.kiro/queue/2026-09-29-timezone-change-orphans-chart-assets.md`).

## Boundary Candidates

- **Geometry.** The simplifier and its three call sites. Pure, no
  dependency, reviewable on its own.
- **Basemap raster.** One module that is the only Pillow importer. It takes
  the plan and the cached tile bytes and returns one encoded raster or a
  typed failure. `compose_map` embeds the raster.
- **Asset persistence.** `sync._write_assets` compare and atomic replace,
  plus the ownership-contract wording. It is independent of the other two,
  so it can land first.

## Out of Boundary

- How tiles are fetched, cached or configured (`tiles.py`, the `[tiles]`
  table).
- chart-kit rendering, `svg.fmt_num`'s shared 2-decimal default (changing it
  moves all 168 SVG goldens), and the kit's byte budgets.
- The workout document's markdown format. Bump `DOC_VERSION` only if the
  design shows a reader-visible need; see Constraints.

## Upstream / Downstream

- **Upstream**:
  - route-maps (`map.py`, the tile cache, Req 4.1/6.1);
  - workout-docs (the hero chart, Req 7.4; `sync` asset writes);
  - running-dynamics (`render_hero_chart` reuse, Req 8.4);
  - wiki-contract (ownership of `workouts/assets/`).
- **Downstream**:
  - the follow-on candidates above;
  - the maintainer's PKM, where Obsidian adoption is unblocked;
  - any later chart family that adopts the simplifier.

## Existing Spec Touchpoints

- **Extends** (amendments carried by this spec; numbers are the next free
  number at landing):
  - **route-maps**:
    - the basemap becomes one encoded raster;
    - the stdlib-only design statements are reversed;
    - the Req 4.1 determinism wording gains its environment qualifier;
    - an undecodable tile becomes a new map-omission cause (Req 4.3);
    - Req 6.1 still holds, because a data URI references no external
      resource.
  - **workout-docs**:
    - Req 7.4 names output-resolution thinning as a static adaptation;
    - the design's "fixed 2-decimal" SvgBuilder statement is scoped;
    - the asset write semantics change.
  - **running-dynamics**: no requirement change expected. Req 8.4
    (byte-identical, script-free) still holds, but the goldens move. Record
    it as a touchpoint, not an amendment, unless the design finds a
    requirement change.
  - **wiki-contract**: if "regen replaces every chart asset" is a published
    guarantee, its change is an ownership-contract change and takes
    `CONTRACT_VERSION` main + 1 under the binding version rules. Settle this
    at requirements.
- **Adjacent**:
  - chart-kit and chart-catalog: shared `svg.fmt_num` and `series.py`; kit
    output must not change.
  - recovery and dashboards: their write-if-changed helpers are reuse
    candidates.

## Constraints

- **Determinism.** "Byte-identical given a warm tile cache" (route-maps
  Req 4.1, running-dynamics Req 8.4) must still hold for repeated renders in
  one installation, because write-if-changed depends on it. Whether WebP
  bytes also match across platforms and Pillow versions decides how goldens
  pin the raster (see Viability).
- **Degradation.** A map problem is a warning, never a failure (route-maps
  Req 4.3/4.4). A decode or encode error joins "tile missing" as a cause of
  omission.
- **Test fixtures.** Fake tiles in seven test sites are not decodable. The
  spec must say what a non-decodable tile does, and re-fixture with
  decodable synthetic tiles, including a 512 px one.
- **Confinement.** Pillow is imported by one module, lazily, so commands
  that never render a map do not pay its import. Rendering runs in a process
  pool.
- **Personal data.** Tests use synthetic tiles only. The real-archive
  measurement stays in the maintainer's git-excluded `artifacts/` and in an
  optional maintainer-only task.
- **Migration.** Links are unchanged; one `fitdocs regen` rewrites the
  assets. After that, write-if-changed keeps later regens from churning sync
  history.
- **Compatibility.** Adding a core dependency counts as a packaging change
  for the CHANGELOG and `docs/install.md`. The Python 3.11 floor stays.

## Viability (2026-10-26)

_Pending: the Pillow/WebP viability check dispatched at discovery._
