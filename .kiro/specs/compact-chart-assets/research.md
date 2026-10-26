# Research & Design Decisions

## Summary
- **Feature**: `compact-chart-assets`
- **Discovery Scope**: Extension. Light discovery: it touches the hero
  renderer, the map composer, the sync asset writer and packaging. It adds
  one new third-party dependency, which was viability-checked at discovery.
- **Key Findings**:
  - **Where the bytes are.** On the maintainer's archive, maps are 75% of
    asset bytes. Each embeds about 12 base64 PNG tiles, and about half of
    each tile's area lies outside the viewport. Hero and dynamics charts
    carry about 5 points per output pixel.
  - **Sharing tiles between map files is impossible.** An SVG shown as an
    image loads no external resource. Verified in headless Chrome: a
    relative-href tile renders blank and a data URI renders.
  - **Pillow 13 and WebP q75 are deterministic.** Byte-identical output on
    macOS/Linux, arm64/x86-64, glibc/musl, spawn/fork, and Pillow 9.5–13.0.
    About 22 ms per map.
  - **The basemap's position can be preserved exactly.** Every tile of a map
    shares one fractional offset, because the plan places tiles at
    `tile*256 - origin`. Composing on an integer-aligned canvas and
    positioning the single `<image>` at the fractional offset therefore keeps
    every basemap pixel where it was, with no resampling.

## Research Log

### Asset size measurements (discovery, 2026-10-26)
- **Context**: The maintainer cannot adopt Obsidian Sync (1 GB plan) because
  of 1,218 MB of chart assets, and iA Writer lags on workout notes.
- **Sources Consulted**:
  - the maintainer's `artifacts/2026-10-26-chart-asset-size/` (git-excluded,
    holds a real route), with `svgexp.py` and `svgexp2.py`;
  - a 40-file random sample per chart kind, seed 7;
  - a re-run of the map variants on that sample during discovery.
- **Findings**:
  - **Hero:** 100.6 → 10.7 KB (−89%) with RDP 0.3 px and 1-decimal
    coordinates. Integer coordinates give −92%; gzip alone gives −66%.
  - **Dynamics:** 85.8 → 16.6 KB (−81%) with the same thinning.
  - **Map, today:** 507 KB on average.

  | Map variant | Size | Change |
  |---|---|---|
  | route thinned only | 450 KB | −11% |
  | lossless per-tile crop, own palettes + RDP (stdlib only) | 236 KB | −53% |
  | flattened WebP q75 + RDP | 114 KB | −78% |
  | WebP q60 at 0.75× | 57 KB | −89% |
  | route only | 5.6 KB | −99% |
  - A single cropped PNG needs RGB, because the composite carries 2,343
    distinct colours (each tile has its own palette). That is 755 KB,
    against the original 562 KB.
- **Implications**: The archive projects to about 250 MB of charts with the
  chosen approach. Thinning alone gives most of the line-chart win and needs
  no dependency.

### Pillow / WebP viability (discovery, 2026-10-26)
- **Context**: Pillow becomes the first image dependency.
- **Sources Consulted**:
  - empirical encodes across platforms (Docker amd64/arm64 glibc/musl, macOS
    arm64 and Rosetta x86-64);
  - Pillow 13.0.0 release notes and building-from-source docs;
  - OSV for advisories;
  - camo sources;
  - a WKWebView snapshot, headless Chrome, QuickLook and librsvg renders.
- **Findings**:
  - **Version and license.** Pillow 13.0.0 (2026-10-16) requires Python ≥3.11
    and has no runtime dependencies. MIT-CMU license; the bundled libraries
    are permissive.
  - **Wheels.** cp311–cp315; macOS arm64/x86-64; manylinux 2.27+ and
    musllinux x86-64/aarch64; Windows.
  - **Source builds** happen on glibc 2.26 and cp313t, and can lack libwebp.
  - **Advisories on this path:**
    - CVE-2026-59199, heap OOB write in `paste()`/`crop()`, fixed in 12.3.0;
    - CVE-2026-96643, quadratic PNG eXIf parsing, fixed in 13.0.0;
    - an APNG bomb bypass, fixed in 13.0.0;
    - roughly 40 decoder CVEs in 13.0.0, among them Ghostscript argument
      injection via EPS.

    Pass `formats=` to `Image.open` so autodetection never reaches them.
  - **Determinism.**
    - WebP lossy bytes were identical across every platform tested, for the
      same Pillow version.
    - They were also identical across Pillow 9.5–13.0 (libwebp 1.3.0–1.6.0),
      but libwebp promises no cross-version stability.
    - Pillow never sets `thread_level`, so encoding is single-threaded.
    - A fresh `Image.new` canvas encodes as bare RIFF/VP8, with no metadata.
  - **Rendering.** WebP in an SVG `<image>` data URI rendered in Chrome,
    WKWebView, QuickLook and librsvg, and under GitHub raw-content headers
    as an `<img>`.
    - WebKit needs iOS 14 / macOS 11.
    - Opening the SVG directly on GitHub blocks every `data:` image through
      CSP, PNG included, so this is not a regression.
  - **Cost.**
    - Composite of 12 palette tiles: 2.8 ms; 8.4 ms with 512 px tiles
      downscaled.
    - WebP q75 encode: 19.5 ms at method 4, 39.5 ms at method 6 (about 6%
      smaller).
    - Warm import about 10 ms; installed size about 12 MB on macOS and about
      22 MB on Linux.
  - **Sharpness.** At 2× device-pixel ratio, an 800×500 raster is as soft as
    today's 256 px tiles. Providers serving 512 px `@2x` tiles keep 2×
    today, so the canvas must follow tile density. WebP lossy uses 4:2:0
    chroma, which softens thin coloured lines slightly.
- **Implications**:
  - `pillow>=13.0.0`, with no upper cap (Req 8.3).
  - An explicit format allow list for tile decoding.
  - A runtime `features.check("webp")` (Req 4.4).
  - A canvas at the tiles' density (Req 3.3).
  - Goldens may pin exact bytes against the `uv.lock` Pillow.

### SVG-as-image cannot reference shared tiles (discovery, 2026-10-26)
- **Context**: The maintainer asked whether tiles could be reused across
  maps. The open queue item proposed a shared `assets/tiles/` directory.
- **Findings**: A headless Chrome render of `<img src="ref.svg">`, where
  `ref.svg` holds `<image href="tile.png">`, showed no tile. The same SVG
  with a data URI showed it, and `tile.png` displayed directly showed it.
  SVG documents loaded as images are restricted from fetching external
  resources.
- **Implications**: Every map file carries its own pixels. The queue item
  was promoted to this spec with that resolution.

## Architecture Pattern Evaluation

| Option | Description | Strengths | Risks / Limitations | Notes |
|--------|-------------|-----------|---------------------|-------|
| Compose in the render layer | `compose_map` decodes and composites tiles itself, importing Pillow | One call site | The render layer gains a third-party import and a failure mode inside a pure function; warnings must travel out of render | Rejected |
| Compose at tile resolution | The sync step that already resolves tiles composes the basemap and hands the render layer an encoded raster; decode failure joins the existing "map unavailable" path | Render stays stdlib-only and pure; one failure path; Pillow confined to one module | The `MapData` shape changes, so test constructors move | **Selected** |
| Shared tile files | The map references `assets/tiles/z/x/y.png` | Deduplicates bytes | Does not render: SVG-as-image loads no external resource | Infeasible |

## Design Decisions

### Decision: Windowed Ramer–Douglas–Peucker at 0.3 output units
- **Context**: Req 1.1/2.1 require every point within 0.5 output units of
  the drawn line. Req 1.6/2.5 require work linear in the point count for any
  shape.
- **Alternatives Considered**:
  1. Plain RDP. Its tolerance guarantee holds, but the worst case is
     O(n²), for example a long convex arc.
  2. M4 (first/last/min/max per pixel column). Linear and exact per
     column, but it keeps up to 4 points per column. On a 1-hour run that
     is barely fewer than the 3,600 samples.
  3. Sleeve-fitting (Zhao–Saalfeld). Linear, but intricate to implement
     correctly, and its endpoint semantics need care.
  4. Visvalingam–Whyatt. It has no distance guarantee and is O(n log n).
- **Selected Approach**:
  - Split each gap-free run into consecutive index windows of at most 512
    points that share their boundary points.
  - Run iterative RDP with ε = 0.3 in each window.
  - Concatenate, round to 1 decimal, and drop consecutive duplicates
    produced by rounding.
  - Each window costs at most O(K²), so the total is O(n·K) with K = 512
    fixed, which is linear in n.
- **Rationale**: The maximum error is 0.3 for RDP plus √2·0.05 ≈ 0.071 for
  rounding, about 0.371 < 0.5. The window boundaries add about n/512
  vertices, which is negligible.
- **Trade-offs**: Slightly more vertices than unwindowed RDP, in exchange
  for a hard time bound.
- **Follow-up**: Test the tolerance with a property test over synthetic
  lines. Test the time bound with a 100,000-point convex arc against a
  generous ceiling, plus a window-size assertion.

### Decision: Integer-aligned canvas, fractional `<image>` placement
- **Context**: Req 3.2 requires the same imagery at the same position.
  Tiles sit at fractional SVG offsets today.
- **Selected Approach**:
  - Let `d` be the canvas density in pixels per unit and `(ox, oy)` the
    shared tile-grid offset in units.
  - The canvas origin is `floor(ox·d)` in the tile-grid pixel space, and
    every tile pastes at an integer pixel position.
  - The `<image>` is placed at `x = (floor(ox·d) − ox·d)/d`, in (−1/d, 0],
    with `width = canvas_px/d`.
  - The canvas is the smallest integer-pixel rectangle covering the
    viewport, so it overhangs by less than one pixel per edge (Req 3.1).
- **Rationale**: No resampling, no position error, and fully deterministic.

### Decision: Basemap composed where tiles are resolved, not in render
- **Context**: Pillow must be confined to one module, and an undecodable
  tile must end as "map omitted + warning" (Req 4.1).
- **Selected Approach**:
  - A new `fitdocs.basemap` module turns `(MapPlan, tile bytes)` into an
    encoded `Basemap` or a typed failure.
  - Sync calls it where tiles are resolved today.
  - The render layer receives the `Basemap` value, embeds it, and never
    imports Pillow.
- **Rationale**: The render layer stays stdlib-only (route-maps purity), and
  the omission path is the existing one.

### Decision: WebP q75, method 4, canvas at the highest tile density
- **Context**: Req 3.3/3.4. Method 6 saves about 6% for twice the time.
- **Selected Approach**: `quality=75`, `method=4`. Tiles of lower density are
  LANCZOS-resized to their slot, and transparent tiles are composited onto
  white.
- **Rationale**: Matches the measured 114 KB per map; deterministic; about
  20 ms.

### Decision: Fail before writing when WebP encoding is unavailable
- **Context**: Req 4.4. Omitting maps would strip them from an archive on
  `regen`.
- **Selected Approach**:
  - A `require_basemap_encoder()` preflight runs in the sync and regen
    entry points before any write.
  - It raises a typed error that the CLI turns into a non-zero exit with
    the remedy: reinstall Pillow from an official wheel, or build it with
    libwebp.

### Decision: Contract 16 → 17, page format unchanged
- **Context**: Req 6, 7.2 and 9.1/9.2.
- **Selected Approach**: The ownership contract gains the "unchanged assets
  are left untouched; changed ones are replaced atomically" guarantee, so
  `CONTRACT_VERSION` goes to main + 1. `DOC_VERSION` is unchanged, because
  the page markdown does not change.

### Decision: `pillow>=13.0.0`, no upper bound
- **Context**: Req 8.2/8.3; the brief's cross-machine question.
- **Rationale**: A cap would block security releases until fitdocs ships.
  Cross-version byte drift is documented as a one-time rewrite (Req 8.5),
  and was not observed for Pillow 9.5–13.0.

### Decision: One spec with three parallel-safe seams
- **Context**: The design review gate asks for a split when independent
  seams could move separately. The three seams are:
  - geometry (`polyline` + hero/route);
  - the basemap (`fitdocs.basemap` + `MapData`);
  - asset writes (`docio`).
- **Selected Approach**: Keep one spec, as the maintainer chose at
  discovery on 2026-10-26. The seams become parallel-safe task streams that
  meet only in `map.py`: the route thinning and `_render_basemap` are
  separate functions. They also share one corpus-level acceptance check.

## Risks & Mitigations
- **libwebp changes output in a future Pillow.** Goldens pin bytes against
  `uv.lock`. A Pillow bump in the lock regenerates the map goldens and
  records it in the CHANGELOG. Users see a one-time rewrite (Req 8.5).
- **Test fakes are not decodable PNGs.** Seven sites fake tiles with only the
  PNG signature. A shared synthetic-tile fixture produces real 256 and 512 px
  PNG, JPEG and WebP tiles. Tests that only need an unavailable map keep the
  undecodable fake deliberately, as the Req 4.1 case.
- **Pillow import cost.** Pages render sequentially and in-process; there
  is no process pool (`sync._run_planned`, `regen`). `fitdocs.basemap`
  imports Pillow lazily, inside its functions, so a run pays about 10 ms
  once. Any other importer of `fitdocs.render` (morning, recovery,
  dashboards) pays nothing, because `render/__init__.py` imports
  `charts.map` eagerly and `charts.map` never imports Pillow.
- **The website hero chart.** It is generated by
  `scripts/make_hero_chart.py`, and `tests/sitebuild/test_hero_chart.py`
  pins it byte-for-byte. Thinning changes its bytes, so it is regenerated in
  the same change. The docs workflow watches that script, so pushing to
  `main` redeploys the site with a visually identical chart.
- **Hero `x` is not guaranteed monotone.** `chart_axis` passes distance or
  time through unsorted. The simplifier is a 2-D algorithm and assumes no
  ordering.
- **The byte-budget fixtures must resemble real imagery.** Synthetic
  solid-colour tiles compress to almost nothing. The map budget fixture uses
  procedurally drawn map-like tiles (roads, labels, fills), as the viability
  check did.

## References
- `.kiro/specs/compact-chart-assets/brief.md`: problem, measurements,
  rejected alternatives, viability.
- `.kiro/steering/roadmap.md` § Phase 13.
- `.kiro/queue/closed/2026-08-23-map-svgs-inline-the-basemap-per-document.md`.
- Pillow 13.0.0 release notes; the Pillow "Building from source" guide
  (libwebp optional).
- Jugel et al., "M4: A Visualization-Oriented Time Series Data Aggregation"
  (VLDB 2014), as the rejected alternative.
