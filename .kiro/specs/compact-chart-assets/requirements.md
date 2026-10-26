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

## Introduction

This feature makes a workout's chart files small and stable without
changing what the athlete sees.

On the maintainer's archive of 2,569 workouts, the chart files weigh
1,218 MB. That is more than one sync plan holds, and it makes the athlete's
markdown viewer lag. Every regeneration then rewrites all of it, so sync
services and backups keep another full copy each time. The measured
projection after this feature is about 250 MB. The page links, the file
names and the look of every chart stay the same.

Three changes do it:
- line charts carry only the points their image can show;
- each map carries one image of exactly the area it shows, instead of a
  dozen whole map tiles;
- chart files are rewritten only when their content changes.

Terms used below:
- **Output units** are a chart's own coordinate units. The hero and dynamics
  charts are 800 units wide and the map is 800 by 500 units.
- The **line charts** are a workout page's hero chart and its
  running-dynamics chart. Both are drawn by the hero renderer.
- A line chart's **lines** are its series lines and its elevation
  backdrop's outline. A map's **route line** is the drawn path of the
  route.
- A line's **full-resolution form** is the line through every plotted point:
  every sample after smoothing and normalization for a chart, every
  projected track point for a route. It is the line fitdocs draws before
  this feature.
- A **gap-free segment** is a run of a line between two gaps. A line chart
  breaks a line where samples are missing; a route breaks where the track
  has separate segments.
- The **basemap** is the map imagery under a route. The **tiles** are the
  map-tile images the tile cache holds. A tile's **pixel density** is its
  pixel width divided by the 256 output units it covers on the map.
- The **supported tile formats** are PNG, JPEG and WebP images.
- A **workout chart asset** is any image file fitdocs writes under
  `workouts/assets/` for a workout page.
- The **image library** is the third-party package fitdocs uses to decode
  tiles and encode the basemap. Discovery chose Pillow, a decision of
  2026-10-26 recorded in `brief.md`.

## Boundary Context

- **In scope**:
  - drawing the line charts' lines and the map's route line at output
    resolution, in bounded time;
  - one basemap image per map, its pixel density and its fixed encoding;
  - maps whose tiles cannot be decoded;
  - an installation that cannot encode the basemap;
  - the determinism statement for maps;
  - writing workout chart assets only when their content changes, and
    atomically;
  - the image library as a required dependency;
  - byte budgets for the line charts and the map;
  - the documentation, the published ownership contract and the release
    notes;
  - the published-rule changes this feature makes to `route-maps`,
    `workout-docs` and `wiki-contract`.
- **Out of scope**:
  - a route-only map setting, and basemap quality or scale settings;
  - per-year asset folders;
  - thinning any chart other than the line charts and the route line: zones,
    calendar, and every chart-kit kind on the dashboard, recovery, history,
    block and catalogue pages;
  - writing the markdown pages only when they change;
  - how tiles are fetched, cached, configured or chosen, and the map's zoom,
    framing and size;
  - asset file names, locations and links;
  - removing orphaned assets
    (`.kiro/queue/2026-09-29-timezone-change-orphans-chart-assets.md`);
  - sharing imagery between map files. This is infeasible: an image shown in
    a markdown viewer loads no file it references, as verified at discovery.
- **Adjacent expectations**:
  - The tile cache (`route-maps`) supplies each tile's bytes exactly as
    today. Missing tiles, disabled tile requests and the map opt-out behave
    as today.
  - The hero chart follows `docs/reference/fitdocs-ai-reference.md` §3,
    adapted only where static rendering demands (`workout-docs` Req 7.4).
    This feature adds one such adaptation.
  - The running-dynamics chart (`running-dynamics`) keeps its requirements
    and changes only through the shared hero renderer.
  - The chart kit shares the coordinate formatting and series helpers with
    these charts, and its output does not change.

## Requirements

### Requirement 1: Line Charts at Output Resolution
**Objective:** As an athlete whose archive syncs to a phone, I want each line
chart to carry only the points its image can show, so that a chart weighs
kilobytes rather than a hundred and opens quickly, with no visible change.

#### Acceptance Criteria
1. When fitdocs draws a line of a line chart, every point of the line's full-resolution form shall lie within 0.5 output units of the drawn line.
2. When fitdocs draws a line of a line chart, the first and last plotted points of every gap-free segment shall be points of the drawn line.
3. fitdocs shall continue to leave a gap wherever a line chart's full-resolution form has one, and shall never draw a line across a gap.
4. Apart from the number and precision of the points on each line, the line charts shall be drawn as before this feature: the dimensions, axes, ticks, legend, smoothing, band normalization, colours and series precedence all stay the same.
5. fitdocs shall state a byte budget for a hero chart and for a running-dynamics chart drawn from a typical one-hour activity and from a typical six-hour activity, each recorded at one sample per second. The fitdocs test suite shall fail if any of those charts exceeds its budget.
6. The work fitdocs does to reduce a line to its drawn points shall grow no faster than in proportion to the number of plotted points times the chart's width in output units, whatever the line's shape. A line of any shape therefore cannot stall rendering.

### Requirement 2: The Route Line at Output Resolution
**Objective:** As an athlete, I want a map's route to carry only the points
the map can show, so that the route stops being a large share of the map's
weight.

#### Acceptance Criteria
1. When fitdocs draws a map's route line, every point of the route's full-resolution form shall lie within 0.5 output units of the drawn route line.
2. When fitdocs draws a map's route line, the first and last points of every gap-free segment shall be points of the drawn route line, and the start and finish markers shall stay at the route's first and last track points.
3. fitdocs shall never join two of a route's separate segments with a drawn line.
4. Apart from the number and precision of the route line's points, the route, markers and attribution shall be drawn as before this feature. That covers the stroke widths, colours and opacity, the map's size, its zoom and the framing of the route.
5. The bound of Requirement 1.6 shall apply to the route line, with the map's width in output units.

### Requirement 3: One Basemap Image per Map
**Objective:** As an athlete, I want each map to carry one compact image of
exactly the area it shows, so that a map weighs about a hundred kilobytes
instead of about five hundred and my viewer decodes one image instead of a
dozen.

#### Acceptance Criteria
1. When fitdocs renders a map, the map file shall contain exactly one basemap image. The image shall cover the map's whole visible area and contain no imagery from outside it.
2. The basemap image shall show the imagery of the tiles fitdocs would have placed under the route before this feature, at the same zoom and position, differing only by the loss of the fixed compression of Requirement 3.4. The route, markers and attribution therefore sit on the same streets as before.
3. The basemap image's pixel density shall equal the highest pixel density among the tiles it is composed from: one pixel per output unit for 256-pixel tiles, two for 512-pixel tiles.
4. fitdocs shall encode the basemap image in one fixed compressed format at one fixed quality. No setting shall change either.
5. The map shall remain a single self-contained file that references no external resource, displayed through a standard image link without plugins, scripts or network access (`route-maps` Req 6.1 and 6.2, unchanged).
6. The route, markers and attribution shall be drawn as vector shapes and text above the basemap image.
7. The basemap image's format shall be one that displays in Obsidian desktop and mobile, in iA Writer, on GitHub, and in Safari on iOS 14 or macOS 11 and later.
8. fitdocs shall state a byte budget for a map drawn over a typical set of tiles, and the fitdocs test suite shall fail if that map exceeds its budget.

### Requirement 4: Tiles and Installations That Cannot Produce a Basemap
**Objective:** As an athlete, I want a bad tile to cost me one map with a
clear warning, and a broken installation to stop before it touches my
archive, so that neither silently strips maps from my pages.

#### Acceptance Criteria
1. If a tile a map needs is not an image in one of the supported tile formats, or cannot be decoded, then fitdocs shall omit that document's Map section, emit a warning naming the document and the cause, and render the rest of the document normally.
2. fitdocs shall read tile content only as one of the supported tile formats, and shall treat content of any other kind as a tile that cannot be decoded.
3. fitdocs shall never report a document or a run as failed because a tile could not be decoded (`route-maps` Req 4.4, unchanged). Missing tiles, disabled tile requests and the map opt-out shall behave as before this feature.
4. If the installed image library cannot encode the basemap's format, then every fitdocs command that renders workout pages shall stop with an error before it writes any page or asset. The error shall name the missing capability and how to restore it.

### Requirement 5: Deterministic Output
**Objective:** As an athlete who regenerates often and syncs everywhere, I
want the same inputs to give the same bytes, so that unchanged charts never
look changed to my sync service.

#### Acceptance Criteria
1. Given the same activity, the same settings, a tile cache that already holds every tile the map needs, and the same installed versions of fitdocs and its dependencies, fitdocs shall write byte-identical line charts and map on every run.
2. For the same installed versions of fitdocs and its dependencies, the bytes of the line charts and the map shall be identical on macOS and Linux, on both arm64 and x86-64 processors.
3. The line charts' bytes shall not depend on the installed image library.
4. fitdocs shall read no clock and make no network request to draw the line charts or compose the basemap. Fetching missing tiles keeps its existing behaviour.

### Requirement 6: Writing Only What Changed
**Objective:** As an athlete whose sync service and backups keep every
version of every file, I want a regeneration that changes no chart to write
no chart, so that a regeneration does not add another gigabyte of history.

#### Acceptance Criteria
1. When `fitdocs sync` or `fitdocs regen` renders a workout chart asset whose bytes equal those of the existing file at its path, fitdocs shall leave that file untouched, both its content and its modification time.
2. When `fitdocs sync` or `fitdocs regen` renders a workout chart asset whose bytes differ from the existing file, or for which no file exists, fitdocs shall write it so that the path never holds partial content. A run interrupted at any point shall leave each asset with either its previous complete content or its new complete content.
3. Requirements 6.1 and 6.2 shall apply to every workout chart asset, not only to the line charts and the map.
4. fitdocs shall keep its existing ownership of `workouts/assets/` and its existing removal of assets that a rewritten page no longer links.

### Requirement 7: Compatibility and Migration
**Objective:** As an athlete with an existing archive, I want one command to
shrink it and nothing else to change, so that the upgrade breaks no link
and no note.

#### Acceptance Criteria
1. fitdocs shall keep every workout chart asset's file name and location, and every link to it, as before this feature.
2. This feature shall not change the markdown fitdocs writes for a workout page, except to omit a Map section under Requirement 4.1. It shall leave the workout page-format version unchanged.
3. When `fitdocs regen` completes on an archive written before this feature, every map, hero chart and running-dynamics chart that a page links shall be in the form this feature defines.
4. This feature shall leave every other chart's bytes unchanged: zones, calendar, and every chart-kit kind on the dashboard, recovery, history, block and catalogue pages.
5. This feature shall add no setting. It shall change no existing setting's meaning, and shall change neither tile fetching and caching nor fitdocs' network behaviour.

### Requirement 8: The Image Library Dependency
**Objective:** As an athlete installing fitdocs, I want the new dependency
to be safe, installable on my machine and honestly described, so that the
smaller archive does not cost me a fragile install.

#### Acceptance Criteria
1. fitdocs shall declare the image library as a required runtime dependency.
2. The image library's declared minimum version shall include the fixes for every advisory known at landing that affects decoding tile images or composing them.
3. fitdocs shall declare a minimum version only, with no upper bound, so that image-library security releases install without a fitdocs release.
4. The installation documentation shall name the dependency and its approximate installed size, and shall state that a platform without a prebuilt package builds it from source. Such a build may lack the basemap's format, which Requirement 4.4 reports.
5. The compatibility documentation shall state three things:
   - the viewers and minimum operating-system versions in which maps display (Requirement 3.7);
   - what a viewer below that floor shows: the route over a blank basemap;
   - that map bytes can change when the installed image library changes, in which case the next `fitdocs regen` rewrites the affected maps once.

### Requirement 9: Documentation, Contract and Release Notes
**Objective:** As an athlete and as the agent maintaining my wiki, I want
the new behaviour written down where I already look, so that nothing about
my chart files surprises me.

#### Acceptance Criteria
1. The published ownership contract shall state that regeneration leaves a chart asset untouched when its regenerated content is identical to the file on disk, and that it replaces a changed asset without ever exposing partial content.
2. The published ownership contract's version shall advance by one from its value at landing, with a statement of what changed.
3. The route-map documentation shall describe four things:
   - the basemap as one image cropped to the map at the tiles' pixel density;
   - that tiles are still cached and reused across maps when rendering;
   - the warning for a tile that cannot be decoded;
   - the installation error of Requirement 4.4.
4. `docs/reference/fitdocs-ai-reference.md` §3 and `workout-docs` Requirement 7.4 shall record drawing at output resolution, within 0.5 output units, as a static-rendering adaptation of the chart specification.
5. The release notes shall describe:
   - the smaller chart files and the new dependency;
   - the viewer floor;
   - the ownership-contract version change;
   - the action `fitdocs regen`, run once to convert an existing archive.
6. The `route-maps` requirements and design, the `workout-docs` requirements and design, and the `wiki-contract` requirements shall record the amendments this feature makes. Each amendment shall take the next free amendment number in its specification at landing.

### Requirement 10: Personal Data and Test Inputs
**Objective:** As the maintainer of a public repository, I want this
feature's tests and measurements to carry no personal data, so that the
repository stays clean.

#### Acceptance Criteria
1. No personal data shall be committed to the fitdocs repository: no `.fit` files, routes, tiles of the maintainer's areas, or rendered maps of the maintainer's activities. Tests shall use synthetic activities and synthetic tiles.
2. The fitdocs test suite shall cover tiles of 256 and 512 pixels, tiles in each supported tile format, and tile content that cannot be decoded.
3. Where the maintainer measures their own archive before and after this feature, only aggregate sizes and counts shall be recorded in the repository.
