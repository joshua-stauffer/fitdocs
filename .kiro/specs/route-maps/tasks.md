# Implementation Plan

> Sequencing precondition: this plan builds on the implemented workout-docs
> and fit-ingest specs — per-sample position channels in the activity model,
> the document views/sections/asset pipeline, the deterministic SVG writer,
> the data-root layout, and the sync/regen/CLI shell must be complete before
> these tasks start.

- [x] 1. Foundation: palette, segmentation, and cache-layout building blocks
- [x] 1.1 (P) Add the route color group to the chart palette
  - Sport tints for rides and runs carried verbatim from the reference product and documented as reference-sourced (exempt from the oklch pipeline); a low-chroma neutral tint and distinct start/finish marker colors derived through the standard oklch pipeline with provenance entries
  - A route-color provenance mapping mirroring the existing series mapping so the palette test enforces provenance
  - Observable: the palette exposes the route color group and the provenance test passes, with the reference-hex exemption documented
  - _Requirements: 2.2, 2.3_
  - _Boundary: RoutePalette_
- [x] 1.2 (P) Add two-channel gap-aware segmentation to the series utilities
  - A paired segmenter over two nullable channels: a point exists only at indices where both values are present; an absent value in either channel ends the current segment
  - Stated generally over any paired channels (the map planner later applies it to latitude/longitude)
  - Observable: unit tests cover both-present pairing, either-side absence breaking segments, and all-absent input yielding no segments
  - _Requirements: 2.4_
  - _Boundary: PairedGapSegments_
- [x] 1.3 (P) Add the tile cache location to the data-root layout
  - A cache-directory constant and a path helper mapping provider name plus tile coordinates to a per-provider z/x/y path under the data root's cache area; layout stays a leaf taking plain values
  - Observable: unit tests confirm provider-keyed z/x/y cache paths under the data root, never inside a repo or the package
  - _Requirements: 3.3_
  - _Boundary: DataRootLayout_

- [x] 2. Pure map geometry and composition
- [x] 2.1 Implement map planning from the position channels
  - Web-Mercator slippy projection, integer zoom selection clamped to the supported range, whole-route framing in the fixed viewport with visible padding on all sides, row-major covering-tile enumeration with the tile y-range clamped per zoom, and the gap-split route projected to viewport coordinates
  - No complete latitude/longitude pair anywhere → no plan (absent data stays absent); a negligible extent (single point or sub-pixel bounding box) → a valid fixed-zoom plan centered on the position
  - Observable: unit tests validate projection against published slippy-map reference values, padding and zoom selection (larger extent → lower zoom), the degenerate-extent fallback, and the no-position case
  - _Requirements: 1.3, 2.4, 2.5, 2.6_
- [x] 2.2 Implement map composition to a self-contained SVG
  - Tiles embedded bottom-layer as base64 data URIs at their viewport offsets; per-segment glow treatment (wide translucent underlay beneath a narrower opaque foreground, round caps and joins, single-point segments rendering as dots); visually distinct start and finish markers on the first and last recorded positions; legible attribution text over a translucent backing in the corner
  - Deterministic by construction: tiles iterated in plan order, coordinates through the shared number formatter, fixed attribute order — identical inputs produce byte-identical SVG referencing no external resources
  - The SVG writer's documented portable element subset gains the image element (docstring only)
  - Observable: unit tests confirm identical inputs produce identical output and the composed SVG contains no external references
  - _Requirements: 2.1, 2.2, 2.7, 4.1, 6.1_
- [x] 2.3 Golden map coverage with synthetic fixture tiles
  - Tiny generated fixture tile PNGs committed (license-clean, no provider tiles redistributed); goldens for the ride tint, run tint, neutral tint, gap-split route, single-point route, and attribution block
  - Observable: golden tests pass and regenerate byte-identically
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.6, 2.7, 4.1, 6.1_

- [x] 3. Tile settings and acquisition
- [x] 3.1 (P) Implement tile provider settings loading
  - Read-only parse of the tiles table in the user-owned settings file under the data root; absent file or table means the keyless OSM default provider; each key defaults independently; unknown keys and tables are ignored (future settings share the file)
  - Loud validation: the URL template must carry the tile-coordinate placeholders, the provider name must be a path-safe slug (rejects cache-path traversal via config), the opt-out flag must be boolean; violations raise the typed settings error
  - Observable: unit tests cover defaults, per-key overrides, each validation failure, and unknown-key tolerance
  - _Requirements: 5.1, 5.2, 5.3_
  - _Boundary: TileSettings_
- [x] 3.2 Implement the cache-first tile store with polite fetch
  - Resolution reads the per-provider cache first; on a miss with tiles enabled, fetch sequentially with the mandatory descriptive user agent and timeout, one attempt per tile per run, writing through to the cache atomically before returning; cached tiles are never re-requested
  - On a miss with the opt-out active, or on any fetch failure (offline, HTTP error, timeout), raise the tile-unavailable error naming the cause; opt-out with everything cached still serves from cache; the only entry point takes an explicit tile list — no prefetch surface exists
  - The store is the package's only network-touching code, behind the injectable source seam the engine depends on
  - Observable: fake-fetch unit tests cover cache-first order, no-refetch, the user-agent header on the real opener, the opt-out gate both ways, write atomicity, and a partial failure leaving already-fetched tiles cached
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 4.2, 5.4_
  - _Boundary: TileStore_
  - _Depends: 1.3, 2.1_

- [x] 4. Render contract and document integration
- [x] 4.1 Carry prepared map inputs across the purity boundary
  - A frozen map-data value (plan, resolved tile bytes ordered exactly as the plan, attribution) and a defaulted optional field on the document context so every existing constructor call and test stays valid; the planning and map types re-exported from the render package surface so the engine never imports chart internals
  - Observable: existing render tests pass unchanged and the new contract imports from the package render surface under strict typing
  - _Requirements: 1.1, 4.1_
- [x] 4.2 Emit the Map section in the run/ride and generic views
  - A map section following the existing section pattern: nothing when map data is absent; otherwise tint by modality (ride tint, run tint, neutral otherwise), compose the SVG, and return the standard markdown image link plus asset using the existing chart naming conventions
  - Inserted immediately after the Summary block and before Telemetry in both outdoor-capable views, with the map asset first in the assets tuple; the strength view untouched
  - Observable: document goldens show the Map section between Summary and Telemetry with its asset link for fixtures with map data, and full omission (no section, no asset) without
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 2.3, 6.2_

- [x] 5. Sync orchestration and warnings
- [x] 5.1 (P) Add the warn-and-continue channel to the sync report
  - A doc-scoped warning value (document reference plus human-readable reason) and a warnings tuple on the report; warnings never enter failures and never affect the written/skipped classification
  - Observable: unit tests confirm warnings are additive — every discovered file still lands in exactly one of written/skipped/failures with warnings alongside
  - _Requirements: 4.3, 4.4_
  - _Boundary: WarningsChannel_
- [x] 5.2 Orchestrate the map path in the sync engine
  - In per-file processing, after stem/match resolution and before context construction, and only for non-strength modalities (the exact set of views that render a map — tiles fetched means a map is rendered): plan from the position channels; on a plan, resolve the exact tile set through the injected source and inject complete map data; on tile unavailability, append a warning naming the target document and carry no map data
  - sync and regen gain the injected tile-source keyword as optional in this task (absent source → map path skipped entirely), so the existing CLI call sites and test suite stay green and offline; task 6.1 flips it to the design's always-supplied contract when the CLI wires the real store; tests here inject fakes
  - The module docstring is amended to the narrowed offline guarantee
  - Observable: integration tests with a fake source cover success (map data injected), unavailable (warning names the doc, document renders without a Map section, run reports success), opt-out-disabled, and strength (no tile resolution attempted); the pre-existing suite passes unchanged
  - _Requirements: 1.1, 3.5, 4.2, 4.3, 4.4, 5.4_
  - _Boundary: SyncMapOrchestration_
  - _Depends: 3.2, 4.1, 4.2_

- [x] 6. CLI wiring and user documentation
- [x] 6.1 Wire tile settings and the store through the CLI
  - sync/regen load the tile settings from the data root (a malformed tiles table routes through the existing config-error path: instructive stderr, exit 2, nothing written), construct the store once per command, and pass it to the engine; the engine's tile-source keyword becomes required (always supplied) per the design contract, updating the direct engine call sites in the existing test suites as part of the flip; the load command never constructs one
  - The report gains a warnings count row and a per-document detail listing mirroring failures; exit codes stay exactly 0/1/2 — warnings never alter the exit code; the CLI docstring is amended to the narrowed network posture
  - Test-infrastructure guard: existing and new CLI tests stay offline by design-native means (the test data root's settings file disables tile requests, or the fetch seam is patched) — no test in the suite performs real network access
  - Observable: CLI tests confirm the warnings presentation, exit 2 on malformed settings before any write, and exit 0 for runs whose only issues are map warnings, with the whole suite network-free
  - _Requirements: 4.2, 4.4, 5.1_
- [x] 6.2 (P) Document route maps, privacy, and configuration
  - A README route-maps section: what leaves the machine (approximate activity location at basemap-tile granularity plus the tool's user agent, only on cache miss during sync/regen), the persistent opt-out and its cached-tiles-only behavior, provider configuration with the documented alternative provider, attribution, and the cache location with the no-pruning policy
  - Observable: the README section discloses the location implication and describes the opt-out
  - _Requirements: 5.5_
  - _Boundary: UserDocs_

- [ ] 7. Feature-level validation
- [x] 7.1 End-to-end determinism, offline behavior, and coverage validation
  - Two sync/regen runs against a warm fake tile cache produce byte-identical documents and assets; the offline guard extends to render-plus-compose under a blocked socket with the tile module's carve-out documented
  - End-to-end fixtures: outdoor activity yields the Map section and asset; indoor/strength yields no section, no asset, and no tile resolution; a failing source yields a warning, intact remaining sections, and exit 0
  - Observable: the full test suite, strict type checking, and lint pass clean with the new coverage
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 3.2, 3.5, 4.1, 4.2, 4.3, 4.4_
- [ ]* 7.2 Confirm GitHub renders data-URI map SVGs
  - Push a sample composed map SVG to a scratch repository and confirm markdown embedding renders through GitHub's image proxy (empirical check for 6.1/6.2); a negative result is recorded as a documented GitHub-only limitation, not an architecture change
  - Observable: the outcome is recorded (works, or a documented limitation)
  - _Requirements: 6.1, 6.2_
