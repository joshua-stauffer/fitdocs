# Gap Analysis: route-maps

**Date**: 2026-07-17
**Inputs**: `requirements.md` (phase: requirements-generated, not yet approved), `brief.md`, steering (`product.md`, `tech.md`, `structure.md`), full codebase investigation, external tile-provider research (web, current as of 2026-07-17).

---

## 1. Analysis Summary

- The feature is a clean brownfield extension: every consumption-side seam it needs (per-sport section assembly, chart asset conventions, deterministic SVG writer, position channels with `None` gaps, data-root resolution) exists and is well-documented in code. The production-side capabilities (tile fetch/cache, Web-Mercator math, raster embedding, provider config, warnings channel) are entirely greenfield — but all achievable with stdlib only, as the brief assumed.
- **Architectural tension to resolve in design**: `render_document` is a pure function of `DocContext` ("no I/O, no clock, no randomness", `src/fitdocs/render/__init__.py:80-93`) and `sync` is the only writer. Tile fetch + cache is I/O and fits neither seam as-is. Recommended shape: a new impure tile-acquisition module orchestrated by sync, a new pure map-composition module, and map inputs injected into the render path.
- **Requirements-level finding (AC 5.2 conflict)**: Esri World Topo — the fitdocs.ai reference basemap — is deprecated (mature support since 2021, retirement Dec 2029), and Esri has directed open-source users to an API-key service. No keyless provider both *matches the reference visual style* and *has terms permitting this use*. The OSM standard layer is the only provider whose published policy explicitly blesses fitdocs' exact access pattern; AC 5.2 should be revised to drop or soften the "matches the reference visual style" clause for the default.
- **Reporting gap**: Req 4.3/4.4 (map omission = warning, never a failure) has no home today — `SyncReport` knows only written/skipped/failures, and any failure drives exit code 1. A warnings channel is a small but cross-cutting addition.
- Effort **L**, risk **Medium**: new subsystem with network + politeness + config surface, but stdlib-only, strong prior art (py-staticmaps/go-staticmaps), and clear integration seams. Two empirical unknowns remain for design (GitHub rendering of data-URI SVGs, real tile sizes).

---

## 2. Current State — Codebase

### 2.1 Render pipeline & section assembly

- Dispatcher `render_document(ctx)` routes on modality: RUN/BIKE → `render_run_ride`, STRENGTH → `render_strength`, else `render_generic` (`src/fitdocs/render/__init__.py:80-101`).
- Sections are **imperative functions building a `blocks: list[str]`**, no registry or template objects (`src/fitdocs/render/views.py`): `_section(heading, body)` at `views.py:79-81`, `_assemble` at `views.py:124-134`. Assets travel as a `tuple[Asset, ...]`; today only `_telemetry_body` (`views.py:94-121`) produces assets (hero chart + zone strip).
- **Map insertion points** (after `## Summary`, before `## Telemetry`, per AC 1.2): `render_run_ride` between `views.py:148` and `views.py:151`; `render_generic` between `views.py:207` and `views.py:209`. Strength (`views.py:165-193`) is explicitly out of scope (`requirements.md:42`).
- Section-order contract lives in `.kiro/specs/workout-docs/design.md:587-599` — route-maps amends it.
- **Constraint**: rendering is a pure function of `DocContext` — "no I/O, no clock, no randomness" (`render/__init__.py:80-93`, `views.py:6-9`). Tile acquisition cannot happen inside a view.

### 2.2 Chart asset conventions

- Naming: `asset_rel_path(stem, chart)` → `assets/<stem>-<chart>.svg` (`src/fitdocs/layout.py:117-126`); a map asset is naturally `assets/<stem>-map.svg`. Note the helper **hardcodes `.svg`** — fine for the planned SVG-with-embedded-PNG asset; no non-SVG path exists.
- `Asset(rel_path, content)` is a frozen dataclass with **text** content (`render/__init__.py:34-45`); written by `sync._write_outputs` under `data_root/workouts/<rel_path>` (`src/fitdocs/sync.py:441-468`).
- Embedding: plain markdown image links, e.g. `hero_chart` → `f"![Telemetry hero chart]({rel_path})"` (`src/fitdocs/render/sections.py:265-279`). The map follows identically (AC 1.4, 6.2).

### 2.3 SVG writer (`src/fitdocs/render/charts/svg.py`)

- Deterministic by construction: `fmt_num` two-decimal / trailing-zero-stripped / negative-zero-normalized (`svg.py:40-62`); `el(tag, attrs, children)` emits attributes in mapping order, XML-escapes values (`svg.py:90-112`); `svg_document` emits root `xmlns`/`width`/`height`/`viewBox` (`svg.py:115-128`).
- `el` is generic ("The tag whitelist … is a caller discipline", `svg.py:104-106`) — it can emit `<image>`. The escaper leaves `+ / =` untouched, so base64 payloads pass through unharmed.
- **Missing**: no `<image>` usage, no base64 helper, no data-URI convention anywhere; the module docstring currently asserts an element subset without `image` (`svg.py:24-27`) and would need updating. SVG2 `href` (no `xmlns:xlink`) is the right target since the root sets only `xmlns`.

### 2.4 Palette

- `src/fitdocs/render/charts/palette.py` holds series and zone colors with oklch-provenance comments (`palette.py:35-62`). **Missing**: the sport tints bike `#1f4d8a` / run `#b22d4a` and any neutral tint — they exist only in `docs/reference/fitdocs-ai-reference.md:101` and `brief.md`. A palette test reconverts constants from provenance, so new tints need matching provenance or a separate constant group.

### 2.5 Activity model & gap handling

- `Samples.latitude_deg` / `longitude_deg`: `tuple[float | None, ...]` (`src/fitdocs/model.py:113-114`); `None` = not recorded; semicircle→degrees done in ingest. GPS presence is already keyed off `latitude_deg` in the coverage table (`sections.py:88`).
- `gap_segments(x, y)` splits polylines on `None` runs (`src/fitdocs/render/charts/series.py:94-120`) — **but it is 1-D** (all-present `x` vs one nullable `y`). A route needs a 2-channel variant: a point exists only when *both* lat and lon are present (AC 2.4).

### 2.6 Config, athlete profile, data root

- `src/fitdocs/config.py` is **only** the data-root resolver: `--out` > `FITDOCS_DATA` > `.fitdocs/data-root` pointer, loud failure (`config.py:47-93`). No general settings store exists.
- `athlete.toml` under the data root has two accessors — read-only `athlete.py:51-82` and read/write `load/profile.py:144-191` (atomic `tomli_w` + `os.replace`); both **ignore/preserve unknown keys and tables** (`athlete.py:56-57`, `profile.py:6-8`), so a new `[tiles]` table would survive round-trips — but the file is semantically athlete-scoped.
- **Missing**: any home for tile-provider URL template, attribution text, and the persistent opt-out (AC 5.1, 5.3). No relevant env var (only `FITDOCS_DATA`) or CLI flag exists; existing boolean-flag pattern is `_NO_PROMPT_OPTION` (`cli.py:134-138`).
- **Missing**: any cache-directory convention. The brief proposes `<data-root>/.cache/tiles/<provider>/<z>/<x>/<y>.png`; `layout.py` (constants `WORKOUTS_DIR`, `ASSETS_SUBDIR`, `ARCHIVE_DIR` at `layout.py:35-41`) is the natural home for the new constant + helper.

### 2.7 Sync engine, warnings, exit codes

- Pipeline: `sync` → `_process_isolated` → `_process_file` (hash→dedup→parse→identity→render→merge→write→archive, `sync.py:367-438`); `regen` reuses it (`sync.py:218-311`).
- **Missing — warnings channel**: `SyncReport` has only `written`/`skipped`/`failures` (`sync.py:153-166`); failure isolation (`_process_isolated`, `sync.py:314-350`) drives **exit code 1**. Req 4.3/4.4 requires warn-and-continue that leaves exit code 0 — no such path exists. Reporting is `rich` Console/Table (`cli.py:59-60, 300-330`), no `logging` anywhere.
- Exit-code contract (verbatim `cli.py:33-41`): 0 success, 1 per-file/per-document failures, 2 configuration error.

### 2.8 Network posture & determinism guarantees

- **Zero network code in the package today**; CLI docstring: "The tool is fully offline: nothing here (or anywhere it calls) performs network access (Req 8.7, 14.4)" (`cli.py:43-44`). No user-agent or politeness convention exists.
- Guarantees being amended (verbatim, `.kiro/specs/workout-docs/requirements.md`): Req 4.1 (`:112`) byte-identical output; Req 14.4 (`:233`) "shall operate fully offline". Route-maps Req 4 AC1/AC2 state the amended forms.
- Offline test guards: `tests/test_determinism.py:91-93, 192-207` patches `socket.socket` for parse/compute (would not trip on a sync-time fetch); `tests/load/test_feature_e2e.py:635-669` forbids network imports **in `fitdocs.load` only**. A package-wide guard, if added, must carve out the tile module.
- Golden tests: byte-identical doc + SVG goldens (`tests/render/test_golden_docs.py:176-202`, regenerate via `python -m tests.render.test_golden_docs`); chart goldens under `tests/render/charts/golden/`. Map goldens will need **committed tile fixtures** so byte-checks run offline.

### 2.9 Reference visual spec (`docs/reference/fitdocs-ai-reference.md:89-136`)

- Placement: map is the last element of the Hero, after KeyStats (= our `## Summary`) — matches AC 1.2.
- Style (verbatim `:99-102`): "non-interactive Leaflet on ESRI World Topo tiles; glow polyline (weight 10, opacity 0.2) under foreground polyline (weight 4, 0.95); start/end pins; tint bike `#1f4d8a`, run `#b22d4a`". Route-name pill and gain/loss overlays are out of scope per `requirements.md:42`.

### 2.10 Dependencies & tooling

- Runtime deps (`pyproject.toml:8-14`): `garmin-fit-sdk`, `typer`, `rich`, `pyyaml`, `tomli-w`. **No HTTP client, no Pillow.** Python ≥3.11, `mypy --strict` on `src`, ruff `E,F,I,UP,B,SIM`. Everything the feature needs (`urllib.request`, `base64`, `math`) is stdlib — **zero new dependencies**, as the brief assumed.

---

## 3. External Dependencies — Tile Providers & Rendering

### 3.1 Provider verdicts (researched 2026-07-17)

| Provider | Keyless access permitted? | Default candidate? | Attribution | Policy |
|---|---|---|---|---|
| **OSM standard** (`tile.openstreetmap.org`) | **Yes** — policy explicitly allows identified, cached, viewport-only, low-volume app use | **Yes — recommended** | `© OpenStreetMap contributors` | operations.osmfoundation.org/policies/tiles/ |
| **OpenTopoMap** | Yes (no key; "no mass downloads"; new server Jan 2026, no SLA) | Good built-in alternative style | `Map data: © OpenStreetMap contributors, SRTM \| Map style: © OpenTopoMap (CC-BY-SA)` | opentopomap.org/about |
| **Esri World Topo** (fitdocs.ai reference) | **Effectively no** — classic service deprecated (mature support 2021, retirement Dec 2029, tiles frozen); Esri directs OSS users to the API-key basemap service; "Powered by Esri" attribution mandatory | **No** | "Powered by Esri" + data credits | arcgis.com item 30e5fe31…; esri.com Master Agreement |
| **CARTO basemaps** | Ambiguous — free tier now reads as scoped to "CARTO grantees" | No (terms ambiguity) | `© OpenStreetMap contributors © CARTO` | carto.com/basemaps |
| **Stadia/Stamen** | No for desktop apps — API key explicitly required outside browser localhost | No (fine as opt-in with user key) | `© Stadia Maps © Stamen Design © OpenMapTiles © OSM contributors` | docs.stadiamaps.com/authentication/ |

**Consequence for AC 5.2** ("a default provider that matches the reference visual style and whose published usage terms permit this use"): the two clauses cannot both be satisfied keyless. Recommendation: default to **OSM standard**, treat "reference visual style" as governing the *route treatment* (glow polyline, pins, tints) rather than the basemap skin, and revise AC 5.2 accordingly. OpenTopoMap is the closest keyless topographic look if style fidelity matters more than service reliability.

### 3.2 Politeness requirements (OSM policy — load-bearing)

- **User-Agent is mandatory**: a unique, descriptive UA naming the app (e.g. `fitdocs/{version} (+repo URL)`); generic defaults like `Python-urllib/3.x` are **actively blocked**. This must override urllib's default.
- No prefetching or bulk download; fetch only tiles the current render needs (matches AC 3.5 exactly).
- Concurrency norm: ≤2 simultaneous connections per host (numeric cap now lives in the OSM *API* policy; 2 remains the community norm and a safe design target for AC 3.4).
- Cache and never re-fetch (fitdocs' cache-forever design exceeds the ≥7-day minimum). Referer not required for native apps.
- Precedent: folium, py-staticmaps/go-staticmaps (which added overridable UAs specifically for OSM compliance and cache tiles locally — essentially this architecture), komoot/staticmap, QGIS, JOSM all fetch OSM tiles directly from desktop tools.

### 3.3 SVG-with-embedded-raster viability (AC 6.1/6.2)

- Browsers render SVG-as-image (`<img>`/markdown) in secure static mode: external references are blocked but `data:` URIs are allowed. **All tiles must be base64-embedded; tile URLs in the SVG would render blank.** The brief's approach is correct.
- GitHub: repo-hosted `.svg` referenced via `![](…)` renders through the Camo proxy (default cap ~**5 MB**) — keep map SVGs under that. Whether GitHub further sanitizes data URIs *inside* repo-hosted SVGs is **unverified** — needs a one-time empirical check (Research Needed).
- Obsidian: renders vault SVGs as `<img>`; known quirks are sizing, not sanitization — root element needs explicit `width`, `height`, and `viewBox`, which `svg_document` already emits (`svg.py:115-128`).
- Size estimate: land tiles at z12–16 run ~15–60 KB typical (to ~250 KB dense-urban; OpenTopoMap heavier). 6–20 tiles × 1.33 base64 → **~0.25–2 MB per map SVG**, worst case ~4 MB. Under the Camo cap in the typical case, but design should bound tile count (e.g. prefer the lower of two candidate zooms). Ranges are estimates — verify with real tiles (Research Needed).

---

## 4. Requirement-to-Asset Map

Tags: **[Exists]** usable as-is · **[Missing]** must be built · **[Constraint]** existing rule shapes the design · **[Unknown]** research needed.

| Req | Need | Status |
|---|---|---|
| 1.1 | Position-presence detection | [Exists] `Samples.latitude_deg/longitude_deg` (`model.py:113-114`); presence pattern at `sections.py:88` |
| 1.2 | Section insertion after Summary | [Exists] seams at `views.py:148/151` and `views.py:207/209`; [Missing] the Map section function; [Constraint] pure render — no I/O in views |
| 1.3 | Clean omission (no section, no asset) | [Exists] conditional-block pattern; trivial once map data is optional in context |
| 1.4 | Asset placement/link conventions | [Exists] `asset_rel_path` (`layout.py:117-126`), `Asset`, `_write_outputs`; note `.svg` suffix hardcoded (fine for SVG map) |
| 2.1–2.3 | Glow polyline, pins, sport tints | [Exists] SVG primitives via generic `el`; [Missing] tints in `palette.py` (bike `#1f4d8a`, run `#b22d4a`, neutral); style params documented (glow w10/0.2, fg w4/0.95) |
| 2.4 | Break polyline at position gaps | [Missing] 2-channel variant of `gap_segments` (`series.py:94-120` is 1-D) |
| 2.5–2.6 | Extent → zoom/padding; degenerate extent | [Missing] Web-Mercator projection + zoom-selection math (greenfield, stdlib `math`) |
| 2.7 | Attribution text on image | [Exists] `text` primitive; string comes from provider config |
| 3.1–3.2 | Fetch on miss; fully-cached ⇒ no network | [Missing] tile-fetch module (stdlib `urllib`), cache-first logic — greenfield |
| 3.3 | Cache under data root | [Exists] data-root resolution (`config.py:47-93`); [Missing] cache-dir constant/helper (natural home `layout.py`) |
| 3.4 | Descriptive UA, bounded concurrency | [Missing] no convention exists; [Constraint] OSM blocks generic UAs — UA override is mandatory, ≤2 connections |
| 3.5 | No prefetching | [Constraint] design rule; matches OSM policy verbatim |
| 4.1 | Byte-identical given warm cache | [Exists] deterministic SVG writer (`fmt_num`, ordered attrs); [Missing] committed tile fixtures for goldens; deterministic base64 is inherent |
| 4.2 | Network only for tiles | [Constraint] amends workout-docs Req 14.4 (`requirements.md:233`); test guards at `test_determinism.py:192-207` and `test_feature_e2e.py:635-669` are scoped — a package-wide guard needs a tile-module carve-out |
| 4.3–4.4 | Omission = warning, never failure | [Missing] warnings channel in `SyncReport` (`sync.py:153-166`) + CLI report + exit-code-neutral path (`cli.py:33-41`) |
| 5.1 | Provider configurable without code changes | [Missing] no settings store; options: `[tiles]` table in `athlete.toml` (both accessors preserve unknown tables) vs. new config file — design decision |
| 5.2 | Default provider: reference style + permitted terms | [Constraint/**conflict**] Esri deprecated/keyed; OSM is the defensible default — **AC needs revision** (§3.1) |
| 5.3–5.4 | Persistent opt-out; cached-only mode | [Missing] config key + fetch-gate; cached-only rendering falls out of cache-first design |
| 5.5 | Privacy disclosure docs | [Missing] user-docs addition (location revealed at tile granularity; opt-out) |
| 6.1 | Self-contained image | [Exists in principle] SVG + data URIs; [Unknown] GitHub data-URI-in-SVG sanitization — empirical check; [Constraint] ~5 MB Camo cap → bound tile count |
| 6.2 | Standard image link, plugin-free | [Exists] identical to chart embedding; `svg_document` already emits width/height/viewBox (Obsidian sizing quirk covered) |

---

## 5. Implementation Approach Options

### Option A — Extend the render layer in place
Do tile fetch + map composition inside the view/chart functions where the section is emitted.

- ✅ Smallest diff; everything in one place; asset flow identical to charts.
- ❌ **Breaks the documented pure-render contract** (`render/__init__.py:80-93`: no I/O) — network, cache reads, and cache writes inside `render_document`.
- ❌ Untestable without network mocks threaded through the render path; contradicts the codebase's strongest architectural invariant.
- **Verdict**: rejected — violates the load-bearing invariant the determinism guarantees rest on.

### Option B — Separate map pass after doc write (load-pass precedent)
Model on the training-load pass: render docs without maps, then a second pass computes maps and splices a Map region into written docs.

- ✅ Precedent exists (sync/regen load pass); isolates all impurity in a pass.
- ❌ The Map section sits *between* Summary and Telemetry — splicing mid-document is far more invasive than the load pass' dedicated region, and AC 1.3 (omit entirely, no placeholder) means the renderer must know about positions anyway.
- ❌ Two-write churn per doc complicates the byte-identical story and `merge_regions` interplay.
- **Verdict**: workable but strained; the pass machinery buys nothing here because the map is derived purely from the `.fit` (no user input to wait for, unlike load).

### Option C — Hybrid: new acquisition + composition modules, sync-orchestrated, pure render preserved *(recommended)*
- **New impure module** (e.g. `fitdocs/tiles.py` or `tiles/`): provider config model, cache path + read/write, polite `urllib` fetch (UA, ≤2 concurrency, opt-out gate, warning on miss). The *only* network-touching code in the package.
- **New pure module** (e.g. `render/charts/map.py`): extent → zoom/tile-set math and `compose_map(points, tiles, tint, attribution) → str` — deterministic SVG via the existing writer, plus the base64 `<image>` capability and a 2-channel gap-segmenter.
- **Sync orchestration**: after parse, sync computes the needed tile set (via the pure math), resolves tiles through cache/fetch, and injects prepared map inputs (or `None`) into `DocContext`; views emit the `## Map` block + asset only when present.
- **Small extensions to existing seams**: `views.py` insertion (2 call sites), `palette.py` tints, `layout.py` cache + (reused) asset helpers, `SyncReport`/CLI warnings channel, config surface for provider/opt-out, `svg.py` docstring/element-subset note.
- ✅ Preserves pure render and the determinism/offline test posture; tile module is independently testable with a fake fetcher; composition is golden-testable with committed fixture tiles.
- ✅ Zero new dependencies; mirrors proven prior art (py-staticmaps' fetch/cache/compose split).
- ❌ Map math is consulted from sync (to know which tiles to fetch) *and* used in composition — the design must keep that in one shared pure module to avoid drift.
- ❌ More moving parts than A: config surface + warnings channel are cross-cutting touches.

---

## 6. Effort & Risk

- **Effort: L (1–2 weeks).** The composition math (Mercator, zoom selection, framing) and the fetch/cache/politeness module are each S–M alone, but the feature also carries a config surface, a new warnings channel, doc/user-docs updates, golden fixtures with committed tiles, and amendments to two workout-docs guarantees — together solidly L.
- **Risk: Medium.** No unknown technology (stdlib HTTP, well-known slippy-map math, existing SVG writer) and provider terms are now resolved; residual risk is concentrated in two empirical unknowns (GitHub data-URI-in-SVG rendering; real tile sizes vs. the 5 MB Camo cap) and one requirements decision (default provider / AC 5.2 revision).

---

## 7. Recommendations for Design Phase

1. **Adopt Option C** (impure tile acquisition + pure composition, sync-orchestrated). Keep all tile-need math in the pure module so sync and composition cannot disagree.
2. **Resolve AC 5.2 before design sign-off**: default to OSM standard tiles; re-scope "reference visual style" to the route treatment (glow/pins/tints), not the basemap skin. Ship OpenTopoMap as a documented alternative; Esri/Stadia only as user-keyed opt-ins.
3. **Decide the config home**: `[tiles]` table in `athlete.toml` (zero new files; both accessors already preserve unknown tables) vs. a dedicated settings file (cleaner scoping). Either way the persistent opt-out (AC 5.3) and provider URL/attribution (AC 5.1) live there; consider a CLI flag mirroring `--no-prompt` for one-shot opt-out.
4. **Design the warnings channel** as a first-class `SyncReport` addition (doc-scoped warning list, rendered by the CLI report, exit code untouched) — it is required by Req 4.3/4.4 and will be reusable beyond maps.
5. **Bound map size**: cap the tile count per map (prefer the lower candidate zoom when over the cap) to stay under GitHub's ~5 MB proxy limit.
6. **Test strategy**: commit a small set of fixture tiles (tiny, license-clean — consider hand-made synthetic PNGs to avoid redistributing provider tiles) for byte-identical map goldens; unit-test the fetch module against a fake opener; extend the offline-guard tests with an explicit tile-module carve-out.

### Research Needed (carry into design)

- **GitHub rendering check** (empirical): push a sample repo-hosted SVG containing `<image href="data:image/png;base64,…">` and confirm it renders via markdown embed (Camo). Community evidence is positive; no authoritative doc.
- **Real tile sizes**: download a handful of OSM/OpenTopoMap tiles at z12–16 over representative workout areas to validate the 0.25–2 MB SVG estimate and pick the tile-count cap.
- **Tile fixture licensing**: confirm whether committing a few real OSM tiles to the repo is acceptable (ODbL/attribution) or whether synthetic fixture tiles are the cleaner path.
- **Cache eviction stance**: cache-forever is policy-compliant; decide whether any pruning/size reporting is wanted (likely "document, don't build").
- **Concurrency mechanism**: whether ≤2 parallel fetches warrant `ThreadPoolExecutor(max_workers=2)` or simple sequential fetching suffices (a typical map is 6–20 tiles; sequential may be fine and simpler).

---

## 8. Design Phase Addendum (2026-07-18)

Recorded while producing `design.md`. Supersedes the matching open items above.

### 8.1 Empirical: real tile sizes (resolved)

Fetched 5 OSM standard tiles at z13–z16 over a dense urban area (NYC) with a
descriptive UA, sequentially: **30–37 KB each** (256×256, 8-bit colormap PNG).
At the fixed 800×500 viewport (≤15 covering tiles, §8.3) a map SVG lands at
**~0.5–0.75 MB** base64-embedded in the typical case — comfortably under
GitHub's ~5 MB Camo cap. The 250 KB dense-tile worst case from §3.3 was not
observed on the standard layer; treated as a documented bound, not a design
driver.

### 8.2 AC 5.2 conflict (resolved — requirements revised)

Applied the §3.1 recommendation to `requirements.md` AC 5.2 under the `-y`
fast-track: the default provider is the **OSM standard layer** (the only
keyless provider whose published policy blesses this access pattern), and the
"reference visual style" clause now explicitly governs the *route treatment*
(glow polyline, markers, sport tints), not the basemap skin. OpenTopoMap is a
documented alternative via the same config surface; keyed providers work via
the URL template but ship no key-management surface.

### 8.3 Synthesis outcomes

- **Simplification — fixed viewport bounds the tile set geometrically.** The
  map viewport is a fixed 800×500 px (800 matches the hero chart width). A
  fixed viewport can intersect at most 5×3 = 15 tiles at any zoom, so the
  §3.3/§7.5 "tile-count cap" knob is unnecessary: zoom selection is purely
  "largest integer zoom whose padded route bbox fits the viewport", and the
  size budget follows from geometry.
- **Simplification — sequential fetch.** ≤15 tiles per map; plain sequential
  fetching trivially satisfies the ≤2-connection politeness norm. No thread
  pool, no retry logic (one attempt per tile per run; failure → warning path).
- **Simplification — opt-out is a config key only** (`tiles.enabled = false`
  in `fitdocs.toml`); no extra CLI flag. Persistent per AC 5.3; documented.
- **Simplification — no cache eviction.** Cache-forever is policy-compliant;
  documented for the user, nothing built.
- **Generalization — warnings channel.** `SyncReport` gains a doc-scoped
  `warnings` tuple (warn-and-continue, exit code untouched) — required by
  4.3/4.4 and reusable for any future non-fatal doc condition.
- **Generalization — paired gap segmentation.** A 2-channel sibling of
  `gap_segments` (`series.py`): a point exists only where *both* channels are
  present. Stated generally (any paired nullable channels); used for lat/lon.
- **Generalization — settings file.** Provider config lives in a new
  `<data-root>/fitdocs.toml` under a `[tiles]` table. The file is the general
  tool-settings home (future tables join it); only the tiles loader is built
  now. `athlete.toml` rejected as semantically athlete-scoped.
- **Build vs adopt.** Reaffirmed stdlib-only (`urllib.request`, `tomllib`,
  `base64`, `math`): py-staticmaps would drag Pillow + an HTTP client for
  raster composition fitdocs does not need (SVG embeds tiles verbatim). The
  slippy-map math is ~40 lines of documented public formulas.

### 8.4 Architecture (final)

Option C confirmed, concrete shapes in `design.md`: pure planning/composition
in `render/charts/map.py` (`plan_map` / `compose_map`, one shared module so
sync and composition cannot disagree on the tile set); impure fetch/cache in
`fitdocs/tiles.py` (`TileStore`, settings loader, `TileSource` protocol);
`MapData` injected into `DocContext` by sync; cache-path helper in
`layout.py`; warnings channel in `sync.py`; CLI builds the store and reports
warnings. Provider `name` is validated as a path-safe slug at settings load
(rejects traversal via config).

### 8.5 Remaining open item (carried into implementation)

- **GitHub data-URI-in-SVG rendering**: still unverified authoritatively.
  Design carries it as a validation hook — during implementation, push a
  sample map SVG to a scratch GitHub repo and confirm it renders through
  Camo. Obsidian/local rendering is unaffected either way; a negative result
  degrades to a documented GitHub-only limitation, not an architecture change.
- **Tile fixture licensing (resolved by avoidance)**: goldens use tiny
  synthetic PNGs generated in-repo (license-clean); no provider tiles are
  committed.
