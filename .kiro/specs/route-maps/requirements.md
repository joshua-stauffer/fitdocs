# Requirements Document

## Project Description (Input)

Outdoor workout docs are missing the route map fitdocs.ai renders. For runs and rides, *where* the workout happened is a core part of the record; today the generated doc (produced by workout-docs) has charts and metrics but no spatial view of the activity, even though fit-ingest already delivers per-sample GPS coordinates (`Samples.latitude_deg` / `longitude_deg`).

This feature adds a map section to any activity doc with position samples: the route drawn as a glow polyline with start/finish markers and sport tint colors over real basemap tiles (fitdocs.ai visual style), produced as a static SVG asset alongside the existing charts. Tiles are fetched politely from a configurable provider with stdlib `urllib` and cached under the data root, so regenerating a doc from a warm tile cache is byte-identical and works offline. Activities without position data (indoor, strength, pool) omit the section cleanly; a tile cache miss while offline omits the map with a warning rather than failing the doc; an opt-out flag/config prevents any tile requests for users who don't want location-revealing traffic leaving their machine.

In scope: map SVG generation for activities with position samples; tile fetch, local cache, provider configuration and attribution; zoom/extent/padding selection; glow polyline and start/finish pins with sport tints; doc integration for run, bike, and generic outdoor layouts; omission rules and offline behavior; tile-request opt-out. Out of scope: GPX/TCX ingestion (measured on real exports: no gain over FIT channels), interactive maps, route-name overlays, privacy zones, and aggregate multi-activity maps.

Full discovery context: `brief.md` in this directory.

## Introduction

route-maps extends workout-docs: any run/ride or generic-layout activity whose
samples carry GPS positions gets a Map section in its document — the route
drawn over real basemap tiles in the fitdocs.ai visual style (glow polyline,
start/finish markers, sport tint), produced as a static image asset alongside
the existing charts. Basemap tiles are fetched from a configurable provider
and cached under the data root, making tile fetch the sole permitted network
access in an otherwise fully-offline tool and keeping regeneration
byte-identical once the cache is warm. Activities without position data omit
the section cleanly, a missing tile never fails a document, and a persistent
opt-out lets users prevent any location-revealing tile traffic from leaving
their machine.

## Boundary Context

- **In scope**: a Map section in the run/ride and generic document layouts for
  activities with position samples; route presentation (glow polyline,
  start/finish markers, sport tints, attribution text, framing/detail-level
  selection); basemap tile fetching, local caching under the data root,
  provider configuration, and polite fetch behavior; omission rules, offline
  behavior, and the tile-request opt-out; documentation of the
  location-privacy implication of tile requests.
- **Out of scope**: GPX/TCX ingestion (measured on real exports: the GPX
  sidecar re-encodes the identical track, so it adds nothing over FIT
  channels); interactive or pannable maps; route-name overlays (require
  reverse geocoding); privacy zones / home-location masking (likely future
  work); aggregate or multi-activity maps; any change to the weight-training
  document view; changes to the fit-ingest activity model (position channels
  already exist); changes to existing chart rendering.
- **Adjacent expectations**: fit-ingest supplies per-sample positions in
  decimal degrees with unrecorded samples preserved as absent values —
  route-maps consumes them as-is. workout-docs owns the document layouts,
  asset conventions, and the sync/regen write pipeline; route-maps inserts a
  Map section into its section order and narrows two of its guarantees:
  "byte-identical rendering" becomes "byte-identical given a warm tile cache"
  and "fully offline" becomes "offline except basemap tile fetch on cache
  miss" (Requirement 4 states the amended forms). training-load is
  unaffected.

## Requirements

### Requirement 1: Map Section in Workout Documents
**Objective:** As an athlete whose runs and rides happen outdoors, I want each workout document to show the route on a map, so that where the workout happened is part of the permanent record.

#### Acceptance Criteria
1. When rendering a run/ride or generic-layout document for an activity whose samples contain at least one position (a sample index where both latitude and longitude are present), the fitdocs CLI shall include a Map section showing the activity route over a basemap.
2. The fitdocs CLI shall place the Map section immediately after the hero summary section and before the telemetry section, mirroring the reference product's placement of the map within the activity hero.
3. When an activity has no position samples, the fitdocs CLI shall omit the Map section and its image asset entirely while rendering all other sections unchanged.
4. The fitdocs CLI shall generate the map as a static image asset placed and linked with the same document-relative conventions as existing chart assets.

### Requirement 2: Route Presentation and Visual Style
**Objective:** As a user of documents modeled on fitdocs.ai's activity pages, I want the route drawn in the same recognizable style, so that maps feel consistent with the rest of the document.

#### Acceptance Criteria
1. The fitdocs CLI shall draw the route as a polyline with a glow treatment: a wide translucent underlay beneath a narrower opaque foreground line.
2. The fitdocs CLI shall mark the first and last recorded positions of the route with visually distinct start and finish markers.
3. The fitdocs CLI shall tint the route by sport, using the reference cycling tint for rides, the reference running tint for runs, and a neutral tint for other activities.
4. If the position channels contain a gap (one or more samples without a position) between recorded positions, the fitdocs CLI shall break the polyline at the gap rather than drawing a segment across it.
5. The fitdocs CLI shall frame the map so the entire route fits within the image with visible padding on all sides, at a basemap detail level appropriate to the route's extent.
6. If the recorded positions span a negligible extent (for example, a single point), the fitdocs CLI shall still produce a valid map centered on the recorded position rather than failing.
7. The fitdocs CLI shall render the tile provider's attribution text legibly on the map image.

### Requirement 3: Basemap Tile Acquisition and Caching
**Objective:** As a user regenerating documents repeatedly, I want basemap tiles fetched once and reused from a local cache, so that re-renders are fast and offline-capable and traffic to the tile provider stays minimal.

#### Acceptance Criteria
1. When a map render requires a basemap tile that is not in the local tile cache, the fitdocs CLI shall fetch that tile from the configured tile provider and store it in the cache.
2. When every tile a map requires is already cached, the fitdocs CLI shall complete the render without any network access.
3. The fitdocs CLI shall store cached tiles under the data root, never inside a code repository or the package installation.
4. When fetching tiles, the fitdocs CLI shall identify itself to the provider (a descriptive user agent) and shall keep request volume polite: bounded concurrency and no re-fetching of already-cached tiles.
5. The fitdocs CLI shall request tiles only as needed to render the maps of activities currently being processed, never for prefetching or any other purpose.

### Requirement 4: Determinism and Offline Behavior
**Objective:** As a user who relies on the data root being fully re-derivable, I want regeneration to remain reproducible and offline-tolerant, so that adding maps never compromises the existing regeneration guarantees.

#### Acceptance Criteria
1. While the local tile cache already holds every tile a document's map requires, when rendering the same activity with the same inputs repeatedly, the fitdocs CLI shall produce byte-identical document and asset output on every invocation. (This refines the workout-docs byte-identical guarantee to "byte-identical given a warm tile cache".)
2. The fitdocs CLI shall perform network access only to fetch missing basemap tiles; every other operation shall continue to work fully offline. (This amends the workout-docs fully-offline guarantee.)
3. If a required tile is neither cached nor fetchable (offline, provider error, or tile requests disabled), the fitdocs CLI shall omit the Map section, emit a warning naming the affected document, and render the remainder of the document normally.
4. The fitdocs CLI shall never report a document or a run as failed solely because a map could not be rendered; map omission is reported as a warning, not an error.

### Requirement 5: Tile Provider Configuration and Privacy Opt-Out
**Objective:** As a privacy-conscious user, I want to choose the tile provider or turn tile fetching off entirely, because tile requests reveal approximate activity locations to an external service.

#### Acceptance Criteria
1. The fitdocs CLI shall let the user configure which tile provider is used, including the provider's tile address pattern and its attribution text, without code changes.
2. Where no provider is configured, the fitdocs CLI shall use a default provider whose published usage terms permit fitdocs' keyless, cached, low-volume access pattern (the OpenStreetMap standard tile layer); the reference visual style is carried by the route treatment (glow polyline, markers, sport tints), not by the basemap skin.
3. The fitdocs CLI shall offer a persistent opt-out that disables all tile requests.
4. While tile requests are disabled, the fitdocs CLI shall render maps from already-cached tiles only and shall apply the standard omission behavior (warning and skip) when required tiles are absent.
5. The fitdocs user documentation shall disclose that map rendering sends approximate activity-location information (at basemap-tile granularity) to the configured tile provider, and shall describe the opt-out.

### Requirement 6: Portable, Self-Contained Map Asset
**Objective:** As a PKM user, I want the map to display anywhere my markdown renders, so that documents remain useful without fitdocs installed, without plugins, and without network access at view time.

#### Acceptance Criteria
1. The fitdocs CLI shall produce each map as a single self-contained image file that references no external resources when displayed.
2. The generated document shall embed the map via a standard image link, consistent with existing chart embedding, so that it displays in common markdown renderers (including Obsidian and GitHub) without plugins, scripts, or network access at view time.
