# Implementation Plan

Three parallel-safe streams meet in the integration group:
- **geometry**: tasks 2.x;
- **basemap**: tasks 3.x;
- **asset writes**: task 4.

The foundation group (1.x) lands first, in order. Every task leaves the full
suite, ruff, ruff format and mypy green on its own.

- [x] 1. Foundation: the dependency, test inputs and shared render primitives

- [x] 1.1 Add the image library as a required dependency
  - Declare Pillow with a minimum of 13.0.0 and no upper bound, and lock it.
  - Update every pinned copy of the runtime dependency set:
    - the determinism dependency baseline;
    - the packaging dependency list, and the offline-install fixture's
      dependency count ("six" becomes "seven");
    - the preserved-guarantees head;
    - the site repo-wiring list;
    - the derived-index preserved list.
  - Record the dependency-baseline amendment in the docs-site (Req 8.1),
    distribution and plugin-api requirements. Use the next free amendment
    number in each, worded like the analytics-index precedent, so that those
    specs never disagree with the pins that move here.
  - Record the library in the tech steering's key libraries. Add to the
    structure steering the import rule that only the basemap module imports
    the image library.
  - Done when:
    - `PIL.features.check("webp")` is True in a fresh environment;
    - every dependency-pin test passes with the new entry;
    - the three specifications carry their dated amendment.
  - _Requirements: 8.1, 8.2, 8.3, 9.6_

- [x] 1.2 Build a synthetic tile factory for tests
  - Produce deterministic tiles at any pixel size in PNG, JPEG and WebP:
    - solid colours;
    - transparent tiles;
    - procedurally drawn map-like tiles (fills, road strokes, label-like
      glyph blocks) from a seed.
  - Provide a decodable drop-in fetch stub.
  - Produce the undecodable cases:
    - a PNG signature with no image;
    - TIFF and GIF images;
    - an EPS-signature blob;
    - random bytes.
  - The factory never reads files, and carries no real place or route.
  - Done when: the factory's own tests show the same seed gives identical
    bytes, each decodable kind opens as its declared format at its declared
    size, and each undecodable kind fails to open as PNG, JPEG or WebP.
  - _Requirements: 10.1, 10.2_

- [x] 1.3 Add the shared render primitives the streams build on
  - Give the shared number formatter an optional decimal-places setting
    whose default reproduces today's 2-decimal output exactly.
  - Define the basemap value type in the map module: MIME type, encoded
    bytes and placement, as specified in the design. Nothing consumes it
    yet.
  - Done when:
    - the existing formatter test corpus is byte-identical unchanged;
    - 1- and 4-place outputs round and trim as specified;
    - the value type constructs, is frozen and passes mypy;
    - every chart-kit, zones, calendar, hero and map golden passes without
      regeneration.
  - _Requirements: 1.4, 7.4_

- [x] 1.4 Create the budget fixtures and capture pre-change outputs
  - Build deterministic synthetic activities of 1 hour and 6 hours at one
    sample per second as `.fit` bytes, through the existing test FIT
    builder: smooth terrain with bounded noise, heart rate, power or pace,
    and two running-dynamics channels. The 1-hour activity also carries a
    GPS track, so that 7.2 can sync the same input.
  - Render their hero and running-dynamics charts with the current
    renderer, and record each size as a named baseline constant in the
    budget test module. Only a fixture smoke test is active at this stage.
  - Capture the pre-change hero, running-dynamics and map assets of the
    1-hour activity (map over factory tiles) as test fixture files, for the
    migration test in 7.2.
  - Done when: the budget module holds four recorded baseline sizes, the
    three pre-change asset fixtures are committed, and a smoke test proves
    the fixtures render.
  - _Requirements: 1.5, 7.3_
  - _Depends: 1.2_

- [x] 1.5 Move render, sync and CLI tests onto decodable tiles
  - Apply this rule to the map unit and contract tests, views, map section,
    golden documents, the tile-transport tests, sync, sync e2e, CLI, CLI
    sync-inbox, CLI check, identity e2e, confinement, portability, drain and
    declaration-refresh modules:
    - every fake tile, meaning PNG-signature bytes or a fetch stub returning
      undecodable bytes, becomes a decodable factory tile or the factory's
      fetch stub;
    - a module may keep a fake only if its tests never compose a map (for
      example, the tile cache stores bytes verbatim) or deliberately
      exercise an unavailable or undecodable map;
    - name each kept module in the task's implementation note.
  - Behaviour is unchanged: today's composer embeds the bytes verbatim.
    Regenerate any golden that embeds a changed fixture tile.
  - Done when: a grep of these modules for PNG-signature fakes and
    undecodable fetch stubs returns only the named exceptions, and the full
    suite passes.
  - _Requirements: 10.1, 10.2_

- [x] 1.6 Move the remaining end-to-end tests onto decodable tiles
  - Apply the 1.5 rule to every other test module that feeds tiles to a
    page render: route-maps, determinism, compose and compose passes, wiki
    contract, plugin regression, effort tags, inbox, reconcile, running
    dynamics, wellness drain, and the load, load QA, threshold and index
    end-to-end and CLI modules.
  - Done when: a repository-wide grep of `tests/` finds no tile fake other
    than the exceptions named in 1.5 and here, and the full suite passes. A
    tile fake is PNG-signature bytes, or a `_default_fetch` patch or
    `fetch=` stub returning anything but a factory tile.
    `_default_fetch` patches that install the factory's fetch stub are
    expected and do not count.
  - _Requirements: 10.1, 10.2_

- [x] 2. Geometry: lines at output resolution

- [x] 2.1 (P) Build the line simplifier
  - Implement the design's simplifier contract, which reduces one gap-free
    run:
    - windowed Ramer–Douglas–Peucker at 0.3 output units, with windows of
      at most 512 points sharing their boundary points;
    - rounding to 1 decimal, and removal of consecutive duplicates that
      rounding produces;
    - a points-attribute formatter using the 1-place setting.
  - No assumption that x is monotone; stdlib only.
  - Property tests over seeded runs check that every input point lies within
    0.5 output units of the output line. The runs cover:
    - a smooth curve, a noisy walk, steps and spikes;
    - a closed loop, a back-and-forth route, and non-monotone x.
  - The first and last points are kept; runs of 0–2 points are handled;
    two calls give identical output.
  - Linear bound: a 100,000-point convex arc completes under a generous
    ceiling, and an instrumented counter shows at most n × 512 distance
    evaluations.
  - Done when: the simplifier and its tests pass. Nothing calls it yet.
  - _Requirements: 1.1, 1.2, 1.6, 2.1, 2.2, 2.5, 5.1, 5.4_
  - _Boundary: polyline_
  - _Depends: 1.3_

- [x] 2.2 Draw hero and running-dynamics lines at output resolution
  - Thin every series line and every backdrop outline, per gap segment,
    through the simplifier. The backdrop's baseline closure uses the thinned
    first and last x. Axes, ticks, legend, smoothing, normalization and
    colours stay untouched.
  - Replace the "plotted points equal samples" assertion with the tolerance
    property against the full-resolution points. Add a test showing that,
    with point data removed, the thinned and unthinned renderings are
    identical.
  - Add a regeneration entry point for the hero goldens.
  - Regenerate:
    - the hero goldens;
    - the golden documents' hero and dynamics assets (their markdown must
      not change);
    - the website hero chart, through its script.
  - Done when: the hero, dynamics, golden-document and website-chart tests
    pass on the regenerated outputs, and no golden document's markdown
    changed.
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 5.3_
  - _Depends: 2.1, 1.4_

- [x] 2.3 (P) Draw the map route at output resolution
  - Thin each route segment once and reuse the points for the underlay and
    foreground strokes. Markers stay at the unthinned first and last track
    points. Separate segments are never joined. Widths, colours, opacity,
    size, zoom and framing are unchanged.
  - Regenerate the map goldens and the golden documents' map assets.
  - Can run beside 2.2. Both regenerate golden-document assets, but
    different files (map versus hero/dynamics). Whichever lands second
    re-runs the regenerator after rebasing.
  - Done when: map tests assert the route tolerance and endpoint properties,
    and the regenerated goldens pass.
  - _Requirements: 2.1, 2.2, 2.3, 2.4_
  - _Boundary: map (route functions only)_
  - _Depends: 2.1, 1.4_

- [x] 3. Basemap: one composed raster per map

- [x] 3.1 (P) Compose the viewport-cropped basemap canvas
  - Decode each tile only as PNG, JPEG or WebP. Any other content, or a
    decode failure, including a decompression-bomb refusal, raises the
    basemap error naming the tile as z/x/y and the cause.
  - Density is the highest tile density, never below one pixel per output
    unit. Tiles of another size are LANCZOS-resized to their slot.
    Transparent tiles are composited onto white.
  - Composite onto the integer-aligned canvas covering the viewport, and
    return the fractional placement, as specified in the design.
  - Tests use lossless canvas output to check:
    - exact pixel placement against a reference mosaic, for positive,
      negative and zero fractional origins;
    - an overhang under one pixel per edge;
    - densities 1 for 256 px tiles, 2 for 512 px, 1 for 4 px, and the
      maximum for mixed sizes;
    - every undecodable kind from the factory.
  - Done when: canvas composition and its tests pass, and the image library
    is imported only inside this module's functions.
  - _Requirements: 3.1, 3.2, 3.3, 4.1, 4.2, 10.2_
  - _Boundary: basemap_
  - _Depends: 1.1, 1.2, 1.3_

- [x] 3.2 Encode the basemap and check the encoder
  - Encode the canvas once as WebP at quality 75, method 4, from a fresh
    canvas with no metadata. Return the basemap value with its MIME type and
    placement.
  - Add the encoder-availability check and the "require encoder" call. The
    latter raises the encoder error, which is distinct from the basemap
    error.
  - Tests:
    - encoding twice gives identical bytes, and their SHA-256 matches a
      pinned golden for a fixed synthetic canvas, which proves macOS (dev)
      and Linux (CI) agreement;
    - a stubbed missing WebP raises the encoder error;
    - composing 15 map-like 512 px tiles stays under a generous time
      ceiling;
    - an AST guard confines every image-library import in `src/` to this
      module, inside functions or under a type-checking guard.
  - Done when: the full compose-and-encode path returns a basemap value, and
    the guard, determinism and encoder tests pass.
  - _Requirements: 3.4, 3.7, 4.4, 5.1, 5.2, 5.4_
  - _Boundary: basemap_
  - _Depends: 3.1_

- [x] 4. (P) Asset persistence: write only what changed
  - Add the compare-then-atomic-replace helper to the shared document I/O
    module, with this behaviour:
    - identical bytes in a regular file leave content and modification
      time untouched;
    - otherwise it writes a hidden temp file in the same directory,
      flushes, syncs and replaces;
    - the temp file is removed on any failure;
    - a symlink at the path is replaced, never read or written through.
  - Tests cover:
    - unchanged leaves the nanosecond mtime identical;
    - changed replaces the content;
    - a forced replace failure leaves the old content and no temp file;
    - a symlink is replaced while its target is untouched.
  - Done when: the helper and its tests pass. Sync does not use it yet.
  - _Requirements: 6.1, 6.2_
  - _Boundary: docio_

- [x] 5. Integration

- [x] 5.1 Put the composed basemap into the map pipeline
  - The map composer embeds exactly one image (a data URI with the
    basemap's MIME type, placement at 4 decimals) before the route, markers
    and attribution, and replaces the per-tile images. Its purity statement
    is updated: still stdlib-only, no image library.
  - The render inputs' map data carries the basemap instead of tiles, and
    is re-exported. The map section passes it through.
  - The sync page task composes the basemap after resolving tiles, passing
    the resolved tiles as (tile, bytes) pairs in the plan's tile order. A
    basemap error becomes a document warning with the map omitted; the
    encoder error is not caught.
  - Update the tile module's "embedded verbatim" docstring. Update the
    structural map assertions: one WebP image, no per-tile PNG images.
  - Regenerate the map goldens (render-level goldens use a fixed fake
    basemap value) and the golden documents' map assets.
  - Done when:
    - rendered maps hold one `data:image/webp` image and no PNG tile
      images;
    - a page with an undecodable tile is written without its Map section,
      with a warning naming the document and cause, and exit 0;
    - the full suite passes.
  - _Requirements: 3.1, 3.5, 3.6, 4.1, 4.3_
  - _Depends: 1.3, 1.5, 1.6, 2.3, 3.2_

- [x] 5.2 Write workout chart assets through the change-aware helper
  - Lands after 5.1, because both edit the sync module (the page task and
    the asset writer).
  - The sync asset writer keeps its name and loop, and writes every asset
    through the helper. Stale-asset removal and the output write order are
    unchanged.
  - Done when:
    - a second regen of a synthetic archive leaves every workout asset's
      nanosecond mtime unchanged;
    - after one activity's input changes, only that page's assets move;
    - the identity end-to-end fault-injection test passes with its named
      steps.
  - _Requirements: 6.1, 6.2, 6.3, 6.4_
  - _Depends: 4, 5.1_

- [x] 5.3 (P) Fail before writing when the WebP encoder is missing
  - Add the CLI preflight that requires the encoder and routes the encoder
    error to the configuration-error exit, code 2, with the remedy message.
  - Call it before the first write of:
    - sync with a source, after the tile store;
    - the inbox drain, before the inbox preflight;
    - regen, before the wellness series rebuild;
    - pull with sync, in its preflight block.
  - Touches only the CLI module, so it can run beside 5.1 and 5.2.
  - Done when: with the encoder stubbed out, each of the four paths exits 2
    with the remedy message and creates or changes no page, asset, inbox
    directory, declaration or wellness series; and with the encoder present,
    every path behaves as before.
  - _Requirements: 4.4_
  - _Boundary: cli_
  - _Depends: 3.2_

- [ ] 6. Contract, documentation and specification amendments

- [ ] 6.1 Advance the ownership contract
  - Raise the contract version by one from its value at landing: 16 → 17
    unless a peer landed first. Append its history paragraph.
  - In the published ownership contract:
    - update the version head and the "what changed" paragraph;
    - add to "What Regeneration Replaces and Preserves" that an asset whose
      regenerated content is identical is left untouched, and that a changed
      one is replaced without ever exposing partial content.
  - Regenerate the eight declaration goldens, and move every literal
    version pin with its pinned paragraph. That covers the retimed-rename
    docs test, the index contract-docs test (including its current-version
    and release-notes assertion) and the derived-index preserved test.
  - Done when: the contract docs tests, declaration goldens and every
    version pin pass at the new value.
  - _Requirements: 9.1, 9.2_
  - _Depends: 5.2_

- [ ] 6.2 Document the change for users
  - Route-map documentation (the README route maps and the configuration
    tile-cache section) covers:
    - one basemap image cropped to the map at the tiles' pixel density;
    - tiles still cached and reused while rendering;
    - the undecodable-tile warning;
    - the encoder installation error.
  - The install documentation gets a Pillow paragraph beside the DuckDB
    note, which stays: approximate size, and that a platform without a
    prebuilt package builds from source and may lack WebP.
  - The compatibility documentation gets a map-images section:
    - the viewers and the iOS 14 / macOS 11 floor;
    - the route over a blank basemap below that floor;
    - the one-time rewrite when the image library changes.
  - The fitdocs.ai reference §3 records output-resolution drawing, within
    0.5 output units, as a static adaptation.
  - The changelog's Unreleased entry describes the smaller assets, the new
    dependency, the viewer floor, the contract version change and the
    `fitdocs regen` action. The contract and action are named inline, per
    the changelog convention. Keep every phrase the existing changelog and
    install-note tests pin.
  - Check whether the fitdocs.ai website guides' Map section and
    privacy/network page describe per-tile embedding. If they do, record a
    queue item for the site copy rather than editing it.
  - Done when:
    - the changelog structure tests, the release-notes assertions and the
      DuckDB install-note test pass;
    - a new docs test pins the viewer floor, the regen action and the
      Pillow install sentence;
    - the website-copy outcome (a queue item, or "not applicable" with the
      reason) is recorded in the implementation notes.
  - _Requirements: 3.7, 8.4, 8.5, 9.3, 9.4, 9.5_
  - _Depends: 6.1_

- [x] 6.3 Record the amendments in the affected specifications
  - **route-maps**: the next free requirements amendment covers:
    - the Req 4.1 determinism wording amended in place, to "same installed
      dependency versions";
    - undecodable tiles added to Req 4.3's causes;
    - the basemap form.

    Its design gets a dated note reversing "stdlib-only (zero new
    dependencies)" and "embedded verbatim".
  - **workout-docs**: the next free amendment states Req 7.4's static
    adaptation and the asset write semantics. The design's "fixed 2-decimal"
    statement is scoped to non-line geometry.
  - **wiki-contract**: the next free amendment states the asset-write
    guarantee and the contract version change.
  - No existing criterion is renumbered.
  - Done when: each of the three specifications carries its dated amendment
    naming this feature, and their spec status checks are clean.
  - _Requirements: 9.4, 9.6_

- [ ] 7. Validation

- [x] 7.1 Enforce the chart byte budgets
  - Activate the budgets for:
    - the 1-hour and 6-hour hero and running-dynamics charts;
    - a map over map-like synthetic tiles.

    Each is the size measured now, rounded up, with 10–40% headroom.
  - Assert the 1-hour hero is at least 75% smaller than its recorded
    pre-change baseline.
  - Done when: the budget test passes, and each budget's headroom sits
    within 10–40% of the measured size.
  - _Requirements: 1.5, 3.8_
  - _Depends: 1.4, 2.2, 5.1_

- [ ] 7.2 Prove the end-to-end guarantees
  - Extend the existing end-to-end modules rather than repeating the
    undecodable-tile test from 5.1 or the regen-twice test from 5.2.
  - With synthetic decodable tiles, two independent runs give byte-identical
    map, hero and dynamics assets.
  - Migration: sync the 1-hour activity, overwrite its three assets with
    the pre-change fixtures captured in 1.4, then run one regen. Each asset
    must be replaced by the new form: the map holds exactly one
    `data:image/webp` image and no PNG, and the hero and dynamics lines
    carry fewer points than the fixtures. Every link and file name is
    unchanged.
  - Golden documents' markdown is unchanged, and the page-format version is
    unchanged.
  - Zones, calendar and every chart-kit golden pass without regeneration.
  - The settings tables and keys are unchanged.
  - Done when: these tests pass in the full suite on macOS and on CI
    (Linux).
  - _Requirements: 3.1, 5.1, 5.2, 6.3, 6.4, 7.1, 7.2, 7.3, 7.4, 7.5_

- [ ]* 7.3 Maintainer-only: measure the real archive and check viewers
  - On a copy of the maintainer's archive, run one regen and record
    before/after totals per chart kind, as aggregates only, in the
    implementation notes. The target is ≤300 MB of charts.
  - Open a generated map in Obsidian desktop, iA Writer, Safari and a GitHub
    image.
  - Done when: the aggregate numbers and the viewer outcomes are recorded,
    with no route, tile or page content committed.
  - _Requirements: 3.7, 10.3_

## Implementation Notes

- 1.1: Pillow is last in the dependency list (after duckdb); the packaging, preserved-guarantees and sitebuild pins are order-sensitive. Amendments taken: docs-site 2, distribution 5, plugin-api 2. Plugin-api Amendment 2 claims discovering plugins does not import Pillow — 3.2 should also pin it at runtime by adding `assert 'PIL' not in sys.modules` beside the duckdb check in `tests/index/test_boundary.py:644`'s subprocess (reviewer follow-up).
- 1.3: `Basemap(mime: str, data: bytes, x, y, width, height: float)` is frozen in `render/charts/map.py`; `fmt_num(value, places=2)`. Review rounds 2–3 were prose only: a module docstring (in src AND in the test module) still claimed the old 2-decimal contract — after changing a contract, grep both src and test docstrings for the old wording.
- 4: `docio.write_bytes_if_changed` is exported (in `docio.__all__` and the `_DOCIO_SURFACE` pin). It compares only when `lstat` says S_ISREG; a symlink or FIFO is replaced, never read. Cleanup is on BaseException. The mode follows the umask (`os.open(..., 0o666)`), so a mkstemp refactor would silently make assets 0600; the umask-0o002 test pins it. Three rounds: failure paths, fsync and mode were unpinned. When pinning a mode, pick a umask where umask-following and the hard-coded default differ.
- 1.2: The factory is `tests/support/tiles.py`. Import it as `from tests.support import tiles as tile_factory`, because `tiles` clashes with `fitdocs.tiles`. Its API: `solid`, `transparent`, `map_like(seed=...)`, `fetch_stub`/`FetchStub` (records `.urls`, crc32-seeded per URL, matches the `fetch: Callable[[str], bytes]` seam), and `UNDECODABLE` (5 kinds). `DEFAULT_SIZE` is 8x8. PNG is written with `compress_level=0`, because Pillow's compressed PNG differs between macOS (zlib-ng) and Linux CI. Stored PNG, JPEG and lossless WebP were byte-identical on macOS and on linux amd64/arm64. Any golden or fixture embedding Pillow-encoded bytes must keep this property.
- 1.5: The only kept fake is `tests/test_tiles.py`: the tile cache stores bytes verbatim and never composes a map. These are not fakes: `test_sync._UnavailableTiles`, which raises `TileUnavailableError`, and `test_identity_e2e._NoTiles`, which returns `{}`. The remaining `_default_fetch` mentions in test_cli*, test_identity_e2e and test_confinement are patch targets that install `tile_factory.fetch_stub()`. Hand-rolled stdlib PNG builders in test_golden_docs, test_map_section and test_map_golden were replaced with `tile_factory.solid`. The map goldens, `fixture_tile.png` and `golden_docs/map_*-map.svg` were regenerated through each module's own `main()`. `test_map._tile_bytes` is `map_like`, seeded per z/x/y. Out of scope here and left for 1.6: test_cli_identity, test_cli_reconcile, test_cli_unconstructible_frontmatter.
- 2.1: Controller ruling: the design's normative `[0..K],[K..2K]` partition governs, so a window spans K = `THIN_WINDOW` intervals, which is at most K+1 points. The "max 512 points" wording in the design and in this task is superseded. Cut-point vertices are always kept, and adjacent points that round to the same 1-decimal pair are deduplicated. Not pinned, and equivalent at the requirement level: the order is RDP first, then rounding (rounding first also meets every postcondition). The tolerance is pinned behaviourally to (0.28, 0.32). `polyline` imports `svg.fmt_num`, which the design's "stdlib only" line misses (queued).
- 1.4: `tests/fixtures/budget_activities.py` is the generator: `activity_fit_bytes(duration_s, *, gps, seed=20260101)`, `render_assets`, `write_fixtures`, regenerated with `uv run python -m tests.fixtures.budget_activities <dir>`. Baselines at f28316d7: 1h hero 149_489, 1h dynamics 96_588, 6h hero 887_112, 6h dynamics 571_079. 2.2 must retire two kinds of check in `test_activity_renders_hero_and_dynamics_charts`, both pre-thinning: the size-parity asserts against the baselines and the `[samples, samples]` polyline-count asserts. 7.1 moves them to the budget comparison. The generator pin hashes the decoded record values, not the `.fit` bytes, because a garmin-fit-sdk bump re-encodes identical records to different bytes. That was shown with 21.218.0 against the locked 21.208.0. Round 3 was a controller fix. Nothing ties the committed `1h-map.svg` route geometry to the generator; 7.2 asserts only on the pre-change form.
- 3.1: `fitdocs.basemap` is now the only module that imports PIL. It exposes `compose_canvas(plan, tiles) -> Canvas`, `BasemapError`, `TILE_FORMATS`, `TILE_UNITS` and `MAX_TILE_PX`. Controller rulings, which amend the design (record them there):
  - (a) A tile must be square, with an edge of at most `MAX_TILE_PX` = 1024 (density ≤ 4). This is checked from the header before `load()`, and anything else is a `BasemapError` naming z/x/y.
  - (b) Error text is deterministic: `tile z/x/y cannot be decoded: Cause: msg`, with ` at 0x…` addresses stripped.
  - (c) Failures in `resize`/`alpha_composite` become `BasemapError` ("cannot be composed"). This is reachable with real Pillow through the partial-crop bomb check; Pillow skips that check when a tile exactly covers the canvas.
  - Placement is pixel-granular at fractional density (`floor(d·o)`, not `floor(o)·d`).
  - Round 3 was a controller fix (a header-only fixture pinning ruling (a)'s ordering).
- 1.6: The exceptions to "no tile fake in `tests/`":
  - **Kept fake:** `tests/test_tiles.py`; it never composes a map.
  - **Not tiles:** `sitebuild/test_check_site.py` and `dashboards/test_storage.py` hold site-asset bytes.
  - **Not fakes:**
    - `_FailingTiles` and `_UnavailableTiles` raise.
    - `_NoTiles` returns `{}` (in test_identity_e2e and test_retimed_rename).
    - The real `TileStore`s in the reconcile tests are served by the patched `fetch_stub()`.
    - The morning and apple-import `TileStore`s are disabled.
  - Beyond the task list, the change also covered `test_sync_handoff`, `index/conftest` and `index/derived/conftest`.
  - An instrument the reviewer wrote around both `compose_map` bindings, in `render/charts/map.py` and `render/sections.py`, found 0 undecodable tiles out of 7703 across 640 suite-wide composes.
  - Until stream 5 decodes tiles, a reintroduced fake on a composing path still passes the plain suite.
  - Round 2 was a controller prose fix.
- 2.3: `_render_route` thins each segment once, and both strokes reuse the result. Markers stay at the raw `plan.segments` endpoints. A segment that thins to a single point is drawn as a duplicated-point dot. `_point()` was removed. The map tests use Req 2.1's 0.5-unit bound; the tighter ≈0.371 postcondition is pinned in test_polyline. Whichever of 2.2/2.3 lands second must re-run `python -m tests.render.test_golden_docs` after rebasing; only map assets changed here. Round 2 was a controller prose fix.
- 6.3: route-maps Amendment 2, workout-docs Amendment 7 (criteria 2.11 and 7.9) and wiki-contract Amendment 13 (2.22) are in place, with the stale route-maps design statements tagged inline. The 3.1 and 2.1 controller rulings are now in this spec's design.md. wiki-contract 1.5 is deliberately left unamended (controller ruling): it is that feature's own landing guarantee. Some amendment sentences run ahead of the code (places=4 placement, WebP q75, MapData.basemap, CONTRACT_VERSION 17, reference §3); 7.x validation re-checks them. Three review rounds, all prose; the last fix was a controller edit.
- 2.2: `hero._render_series` and `_render_backdrop` thin each gap segment; the backdrop closure uses the thinned end x. The dynamics chart renders through `render_hero_chart` with `backdrop=None`, so it is covered by the same path. The size-parity and `[samples, samples]` checks are retired, replaced by `0 < count < samples`. The `BASELINE_*` constants stay. `_BASELINES` in test_chart_asset_budgets has no reader now, so 7.1 can reuse it or delete it. The `_points_tokens` helper in test_hero is dead. The `scripts/make_hero_chart.py` docstring ("two-decimal formatting", "only IEEE-754 basic operations") is stale after thinning, so 6.2 should fix it. The regenerated goldens are macOS-only until branch CI runs (Req 5.2).
- 3.2:
  - **Added:** `encode_canvas`, `encoder_available`, `require_encoder`, `compose_basemap` and `BasemapEncoderError`, plus the `BASEMAP_FORMAT`/`BASEMAP_MIME`/`BASEMAP_QUALITY`/`BASEMAP_METHOD` constants. `BasemapEncoderError` is NOT a `BasemapError`, so 5.1 must not catch it as a per-map warning; 5.3 turns it into a pre-write failure.
  - **Departures from the design wording:**
    - `compose_basemap` calls `require_encoder()` before decoding any tile.
    - `encode_canvas` builds the fresh image with `Image.frombytes`.
    - Both are ruled acceptable (queued for the design).
  - **Golden SHA `fa6c615d…`:** verified with `uv sync --frozen` on macOS arm64 and on linux arm64/amd64 (amd64 emulated) for py3.11–3.13. Real x86-64 is covered only by branch CI.
  - **Remedy text:** the error message contains "install a Pillow wheel that includes libwebp".
  - **Guards:**
    - The AST guard confines PIL to function bodies or `TYPE_CHECKING`; decorators and default arguments count as module scope.
    - `tests/index/test_boundary.py` asserts `'PIL' not in sys.modules` after plugin discovery.
    - basemap.py has an import allow list and banned I/O builtins. File access via `io.open` or a PIL path is not pinned (declared).
  - **Review:** four rounds. Rounds 3–4 were controller test and comment fixes. The round-4 confirmation went to the same reviewer instead of a debug subagent, because the fix was already agreed.
- 5.3: `cli._basemap_preflight()` maps `BasemapEncoderError` to `_config_error` (exit 2) using the design's exact message (controller ruling: the design text governs over the module error's phrase). It is called on four paths: sync SOURCE after `_tile_store`, `_run_drain_passes` before `_inbox_preflight`, regen before `rebuild_series`, and the end of pull's `if sync_after:` block. `load` and plain `pull` do not call it. Tests snapshot the whole data root (paths, bytes, mtime_ns, dirs). Round 2 was a controller docstring fix. Known gap, queued: plugin discovery can write `__pycache__` into a data-root plugins dir before any preflight.
- 5.1: `compose_map(plan, basemap, *, tint, attribution)` draws one `<image>` (4-place placement) as the first element. `MapData` is now `(plan, basemap, attribution)`, and both `MapData` and `Basemap` are in `fitdocs.render.__all__` (design § Modified Files). `sync._page_task` passes `(ref, bytes)` pairs in `plan.tiles` order. A `BasemapError` becomes a `DocWarning` (unless `quiet`) and the map is omitted. `BasemapEncoderError` propagates: it is a per-file failure in the engine, and the CLI preflight (5.3) stops before any write. The render-level map goldens use `tests/support/basemap.py` `FAKE_BASEMAP`. `fixture_tile.png` and its provenance tests are deleted. A new `test_identity_e2e::test_a_ledger_settle_does_not_repeat_the_pages_map_warning` pins the `quiet` gates on both map-warning branches, and a sync test pins attribution. 2 rounds.
- 5.2: `sync._write_assets` writes every asset through `docio.write_bytes_if_changed`. The write order, assets → stale removal → move → document → archive, is unchanged. `tests/test_chart_asset_writes.py` covers all four asset kinds (hero, dynamics, map, zones), and needs an athlete with HR zones so zones render. It also checks first-write and replace atomicity, and pins the order. The identity fault-injection test wraps the `_write_assets` step, so it needed no change. Two rounds. Queued follow-up: a SIGKILL during the helper leaves an orphan `.tmp` in `workouts/assets/`.
- 7.1: `BUDGET_BYTES` vs `MEASURED_BYTES` (macOS arm64), in bytes:

  | Chart | Budget | Measured |
  |---|---|---|
  | 1h hero | 30_000 | 24_514 |
  | 1h dynamics | 32_000 | 26_272 |
  | 6h hero | 58_000 | 47_218 |
  | 6h dynamics | 64_000 | 51_951 |
  | 1h map | 61_000 | 49_571 |

  - Headroom is 22–23%; the 10–40% band is pinned on the constants, plus a live check that the budget is no more than 1.40× the current size.
  - The 1h hero is 83.6% below its baseline.
  - The map is measured over 8 z15 map-like tiles at 256 px, with `_TILE_SIZE` monkeypatched inside the fixture context.
  - The map-like thresholds are ≥5 colours and a dominant colour under 90%; two real tiles are at 76% and 79%.
  - If the renderer shrinks more than about 18%, the live looseness check fails and the budgets must be lowered.
  - Two rounds.
