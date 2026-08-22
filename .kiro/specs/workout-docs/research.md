# Research & Design Decisions — workout-docs

## Summary
- **Feature**: `workout-docs`
- **Discovery Scope**: New Feature (greenfield user-visible layer; document-driven
  discovery — the chart/view spec and the upstream contract are already pinned
  in-repo, so external web research was limited to confirming mainstream
  library floors)
- **Key Findings**:
  - The fit-ingest design (approved) fixes everything this layer consumes:
    `parse_fit` / `compute_metrics`, the frozen `Activity` model
    (`SCHEMA_VERSION "1.0"`), `DerivedMetrics`, `AthleteInputs`/`ZoneSpec`,
    and the error taxonomy (`NotFitFileError`, `FitIntegrityError`,
    `FitDecodeError`). fit-ingest explicitly defers the console entry point
    and packaging polish to this spec, and ships no serialization — rendering
    owns presentation formats.
  - `docs/reference/fitdocs-ai-reference.md` §3 fully specifies the hero
    chart (distance x-axis, band normalization [0.42, 0.92], elevation
    backdrop [0, 0.32] at `#888`/0.18, null-skipping boxcar k=5, line width
    1.8, oklch palette) and the activity view section order; §4 gives the
    strength display model (`set | reps | load | rest`) with no reference
    implementation to copy.
  - The reference's HR-zone strip uses hard-coded fallback zone bands; the
    reference doc itself flags this as a defect to diverge from — zone data
    must come from the athlete's real zones or the strip must be omitted.
  - Python 3.11 stdlib `tomllib` provides read-only TOML parsing — a perfect
    match for the read-only athlete-inputs contract (no new dependency, and
    the API is physically incapable of writing, which enforces the boundary
    with training-load).

## Research Log

### Upstream contract audit (fit-ingest design/tasks)
- **Context**: This layer renders exclusively from fit-ingest outputs; any
  interface mismatch would ripple through every template.
- **Sources Consulted**: `.kiro/specs/fit-ingest/design.md`,
  `requirements.md`, `tasks.md` (`_Boundary:_` lines).
- **Findings**:
  - Public API: `parse_fit(source) -> Activity`,
    `compute_metrics(activity, athlete: AthleteInputs | None) -> DerivedMetrics`.
  - `Activity` carries `sport: Sport`, `modality: Modality`, `is_indoor`,
    `start_time: datetime | None` (tz-aware UTC), `summary`, `laps` (with
    inclusive `start_index`/`end_index` into `samples`), `samples` (parallel
    tuples with `None` holes), `sets: tuple[StrengthSet, ...]`, `devices`,
    `provenance` (sha256, source path, `decode_errors`).
  - `DerivedMetrics` is flat and fully `None`-able; time-in-zone fields are
    `tuple[float, ...] | None` sized `len(dividers) + 1`.
  - fit-ingest owns `pyproject.toml` creation but explicitly excludes the
    console script ("no console script (workout-docs owns CLI)") — so this
    spec **modifies** `pyproject.toml` rather than creating it.
  - fit-ingest's `tests/fixtures/builder.py` builds synthetic `.fit` bytes
    (run/ride/strength/minimal/corrupt) — reusable for this spec's
    end-to-end and golden tests without adding personal data.
- **Implications**: Renderers take `(Activity, DerivedMetrics, AthleteInputs | None)`
  and never touch FIT messages; sha256 comes from `provenance` (no second
  hashing pass needed after parse, though sync hashes bytes first for dedup
  before parsing); decode errors surface in the data-quality section.

### Chart reproduction in static SVG
- **Context**: The hero graph is the doc's centerpiece and must render in
  Obsidian, GitHub, and plain viewers with zero plugins.
- **Sources Consulted**: `docs/reference/fitdocs-ai-reference.md` §3
  (MultiChart spec), steering `tech.md` (hand-generated SVG, no matplotlib).
- **Findings**:
  - All normalization/smoothing constants are documented and portable to
    static SVG. Interactive-only affordances (tooltips, cursor, metric
    toggling) have no static equivalent and are dropped; averages move into
    a "chips" line above the chart, and a small in-SVG legend replaces
    hover identification.
  - `oklch()` color syntax is CSS Color 4 — fine in Chromium-based renderers
    (Obsidian, GitHub web) but not guaranteed in older SVG rasterizers or
    plain viewers. The brief allows adaptation "where print/static form
    demands".
  - GitHub serves user-content SVG sanitized but supports inline `<style>`
    and presentation attributes; the safe subset is plain shapes, paths,
    text, and presentation attributes — no scripts, no external refs
    (which the CSP-free markdown constraint requires anyway).
- **Implications**: Precompute sRGB hex equivalents of the documented oklch
  palette at development time and ship them as constants documented next to
  their oklch sources (`render/charts/palette.py`); use only presentation
  attributes; fixed float precision for deterministic output.

### Editable-region preservation mechanics
- **Context**: Regeneration must never destroy user-authored content
  (strength workout section, notes) or the training-load section another
  tool fills.
- **Sources Consulted**: Common merge-marker practice (HTML comment markers
  in generated markdown, e.g. doc generators and README injectors); Obsidian
  and GitHub renderer behavior for HTML comments.
- **Findings**: HTML comments (`<!-- ... -->`) are invisible in GitHub and
  Obsidian preview, survive plain-text editing, and are trivially parseable.
  Line-based markers with explicit ids are robust against content edits
  inside the region; damage detection (unbalanced or missing markers) is
  decidable with a linear scan.
- **Implications**: Region contract
  `<!-- fitdocs:begin:<id> -->` / `<!-- fitdocs:end:<id> -->` with region ids
  `notes`, `workout`, `load`; non-nesting; conflict = refuse to overwrite
  that document. The `load` region is machine-filled (by training-load) but
  preserved by the same mechanism.

### Data-root state without a database
- **Context**: tech.md mandates "state = the user's files"; sync needs a
  processed-marker and regen needs a sha→document lookup.
- **Sources Consulted**: steering `tech.md`, `structure.md`, pkm data-root
  contract description; brief ("sha256-keyed archive … for provenance and
  dedup").
- **Findings**: Archive presence (`fit-archive/<sha256>.fit`) is a
  sufficient processed-marker; the document's frontmatter `sources` entry
  (data-root-relative archive path) is a sufficient reverse index for
  regeneration. No index file needed; both survive user renames of the doc
  only partially — regen matches on `sources`, so user renames are safe;
  frontmatter edits that remove `sources` orphan the doc (documented
  limitation, surfaces as "no document found; rendering fresh").
- **Implications**: Write order per file: render → write assets → write doc
  → archive last (archive presence is the commit marker, so a crash mid-file
  causes reprocessing, which is idempotent).

### Real-data verification (user's actual `.fit` corpus)
- **Context**: Mid-design verification against 16 real HealthFit exports
  (Apple Watch + Stryd, decoded with `garmin-fit-sdk` 21.208.0, zero decoder
  errors) — ground truth for what documents must handle.
- **Sources Consulted**: Coordinator-supplied decode results over the user's
  files (personal data stays outside the repo; findings only).
- **Findings**:
  - **Strength files carry no `set_mesgs` at all** (sport `training` /
    sub_sport `strength_training`): records hold only timestamp + heart
    rate; session holds duration, avg/max HR, calories, num_laps — no
    distance, no power. The real strength doc is HR summary + HR-over-time
    chart + duration/calories + the manual workout section.
  - **Running power is native and near-universal** (Apple Watch running
    power and Stryd, ~99% record coverage, session avg_power); NP/IF/TSS
    are *not* in the files — they come from fit-ingest derived metrics.
    The power-vs-HR hero chart is well supported for running.
  - **HR streams can be very sparse** (62% and 72% coverage in two real
    files) — gap tolerance in charts is a real-data requirement, not an
    edge case.
  - One real outdoor run has **no GPS/altitude fields whatsoever**; the
    cycling file has **no power**. Elevation backdrop, climb stats, and
    power series must all degrade to absent.
  - **HealthFit session-scoped developer fields** exist: `SESSION UUID`
    (16-byte array), `SESSION INDOOR`, `SESSION ACTIVITY TYPE`,
    `SESSION WEATHER HUMIDITY`, `WORKOUT RPE ESTIMATED`, `AVG METs`.
    fit-ingest is being amended (additively) to expose session developer
    fields as a generic optional name→value mapping.
  - **Device naming quirk**: manufacturer decodes as the literal string
    `development` with `product_name` like `Watch7,5` — product name is the
    meaningful display field.
  - `avg_temperature` present only in older Apple Watch files — strictly
    optional.
- **Implications**: Strength view gains a telemetry section and never
  scaffolds an empty sets table; hero chart/summary logic treats every
  channel as independently absent; SESSION UUID becomes the preferred
  stable activity identity (re-export dedup, frontmatter, regeneration
  lookup) with sha256 fallback; device display prefers `product_name`.

## Architecture Pattern Evaluation

| Option | Description | Strengths | Risks / Limitations | Notes |
|--------|-------------|-----------|---------------------|-------|
| Layered pipeline continuation (chosen) | `cli → sync → render → (fit-ingest model/metrics)`; config/athlete/docmerge/layout as leaf services | Extends the steering dependency direction; render is pure (strings/bytes out), sync owns all I/O; charts take plain series | Requires discipline that render performs no file I/O | Direct fit with brief's three seams (template/render, charts, CLI/config) |
| Template engine (Jinja2) for docs | Markdown via template files | Familiar templating | New dependency; logic-in-template drift; determinism and `None`-handling harder to type-check; golden tests already pin output | Rejected (build-vs-adopt: string assembly in typed Python is smaller and `mypy --strict`-checkable) |
| matplotlib for charts | Library-rendered SVG | Battle-tested plotting | Heavy dependency for an installable tool; output SVG nondeterministic across versions; steering explicitly discourages | Rejected (steering-pinned hand SVG) |
| Watch-directory daemon | Background sync service | Zero-step ingest | Steering: no background jobs; out of scope (automated acquisition deferred) | Rejected |

## Design Decisions

### Decision: Hand-assembled markdown and SVG, no template/plot dependency
- **Context**: Docs and charts must be byte-deterministic (golden files,
  idempotent re-runs) and pass `mypy --strict`.
- **Alternatives Considered**:
  1. Jinja2 templates — dependency, logic drift into templates.
  2. matplotlib SVG — heavy, version-dependent output.
- **Selected Approach**: Typed Python builders: section renderers return
  markdown strings; a minimal SVG element builder emits fixed-precision,
  attribute-ordered SVG.
- **Rationale**: Smallest dependency footprint (steering), full type
  checking, deterministic output under version pinning.
- **Trade-offs**: More rendering code to own; mitigated by golden tests.

### Decision: Archive presence is the dedup/commit marker; frontmatter `sources` is the reverse index
- **Context**: Requirements 3.2, 4.2–4.4 need "already processed" and
  "which doc belongs to this archive" without a database.
- **Alternatives Considered**: 1. `index.json` in the data root — second
  source of truth that can desync. 2. Doc-name convention lookup — breaks on
  user renames.
- **Selected Approach**: `fit-archive/<sha256>.fit` present ⇒ processed;
  regeneration scans `workouts/*.md` frontmatter for the matching
  data-root-relative `sources` entry; archive written last per file.
- **Rationale**: State stays in user-visible files (tech.md); crash-safe
  (reprocessing is idempotent); user renames of docs survive regen.
- **Trade-offs**: Regen is O(docs) per lookup — trivial at personal scale;
  removing the `sources` frontmatter orphans a doc (regen renders fresh
  alongside; documented).

### Decision: Activity identity = SESSION UUID when present, content hash otherwise
- **Context**: Real HealthFit exports carry a `SESSION UUID` developer
  field; re-exporting the same activity produces different bytes (sha256
  changes), so byte-hash dedup alone would duplicate documents on
  re-export. Requirement 3.6 was added for this.
- **Alternatives Considered**: 1. sha256-only identity — duplicates on
  re-export. 2. start_time+sport heuristic identity — collides for
  back-to-back activities and fabricates identity the file doesn't assert.
- **Selected Approach**: `activity_uid` = canonical UUID string from the
  session developer field when present and well-formed; else the source
  sha256. Frontmatter carries `uuid` (when recorded) plus `sources` (all
  archived refs, last = current). Sync resolves the target document by
  `uuid` first, then by `sources` match; same uid + new bytes ⇒ in-place
  update (regions preserved) + archive append. Regen renders each doc from
  its last `sources` entry; unreferenced archives render fresh.
- **Rationale**: Uses only identity the file itself records; degrades to
  content-hash identity without fabrication; makes re-exports converge on
  one document.
- **Trade-offs**: Depends on the additive fit-ingest amendment exposing
  session developer fields (tracked as an allowed dependency and
  revalidation trigger); UUID-less devices fall back to per-byte identity
  (re-exports of identical bytes still dedup via the archive).

### Decision: HTML-comment region markers with conflict-on-damage
- **Context**: Requirement 10 (preserve user content), Requirement 11
  (stable load placeholder another spec fills).
- **Alternatives Considered**: 1. Heading-based sections (fragile — users
  legitimately edit headings). 2. Separate sidecar file for user content
  (splits the document, violates "one doc per workout"). 3. Diff3-style
  merge (overkill, nondeterministic).
- **Selected Approach**: `<!-- fitdocs:begin:<id> -->` /
  `<!-- fitdocs:end:<id> -->` around `notes` (all docs), `workout`
  (strength), `load` (all docs). On regeneration all three regions'
  inner content carries over verbatim; unbalanced/missing/unknown markers ⇒
  per-document conflict error, file left untouched.
- **Rationale**: Invisible in rendered views, robust to in-region editing,
  linear-scan verifiable, and the same mechanism serves both user content
  and the training-load fill contract.
- **Trade-offs**: Users who delete markers lose regen for that doc until
  they restore them — loud failure is the project's stated preference.

### Decision: Local-timezone presentation with timezone as an explicit render input
- **Context**: The model stores tz-aware UTC; docs are a personal training
  log where "morning run" must land on the athlete's calendar date (doc
  name, frontmatter `date`, displayed times).
- **Alternatives Considered**: 1. UTC everywhere — deterministic but wrong
  dates for evening workouts west of UTC. 2. Configurable `--tz` flag —
  scope creep for v1.
- **Selected Approach**: All date/time presentation converts through one
  `tzinfo` parameter threaded from the CLI (system local zone) into sync
  and render; tests pin a fixed zone. Regen finds existing docs via
  `sources`, so a later tz change cannot duplicate docs (names are looked
  up, not recomputed).
- **Rationale**: User-correct dates; determinism preserved because tz is an
  input, not ambient state.
- **Trade-offs**: Same archive rendered under different system zones yields
  different display strings — acceptable for a personal tool; golden tests
  fix the zone.

### Decision: oklch palette shipped as documented sRGB hex constants
- **Context**: Chart fidelity (brief pins the §3 palette) vs. portability of
  `oklch()` in static SVG viewers.
- **Selected Approach**: `palette.py` defines each series color as an sRGB
  hex constant with the source oklch value in an adjacent comment;
  conversion done once at development time with a color tool (verification
  step in the implementation task). Zone-strip colors: a documented 5-step
  cool→hot sequential ramp defined in the same module.
- **Rationale**: Identical appearance in modern renderers, graceful in older
  ones; keeps "documented palette" auditable.
- **Trade-offs**: Manual re-conversion if the reference palette changes.

### Decision: Athlete inputs read from `athlete.toml` via stdlib `tomllib`, strictly read-only
- **Context**: The HR-zone strip and threshold metrics (IF, TSS, TRIMP) need
  athlete data, but profile ownership (creation, prompting, persistence)
  belongs to training-load; hard-coded fallback zones are forbidden.
- **Alternatives Considered**: 1. Defer all zone displays until
  training-load lands — loses the strip for users willing to write a file
  by hand. 2. YAML profile — second config format for no gain, and pyyaml
  can write (tempting future violation).
- **Selected Approach**: Optional `<data-root>/athlete.toml`; this spec
  reads only the keys it consumes (`ftp_watts`, `resting_hr_bpm`,
  `max_hr_bpm`, `hr_zones`, `power_zones`, `pace_zones` — dividers as
  ascending arrays), maps them onto fit-ingest `AthleteInputs`, ignores
  unknown keys (forward-compatible with training-load's extensions).
  Absent file ⇒ `None`; malformed file ⇒ loud config error (never silently
  drop zones).
- **Rationale**: stdlib-only, read-only by construction; gives training-load
  a concrete file contract to own and extend.
- **Trade-offs**: A file schema is committed before its owning spec exists —
  mitigated by keeping it minimal and listing it as a revalidation trigger
  for training-load.

### Decision: Split re-slicing is presentation-level derivation owned here
- **Context**: The 1 km re-slice computes per-split aggregates from
  `Samples`, which superficially resembles fit-ingest's metric territory.
- **Selected Approach**: `render/splits.py` slices the sample stream
  (cumulative-distance boundaries) and computes per-slice display aggregates
  (time, pace/speed, avg/max HR, avg power, cadence) directly over sample
  windows; device-lap rows come straight from `Lap` summary fields.
- **Rationale**: The reference app does this client-side in the view layer;
  the aggregates are table cells, not contract metrics; fit-ingest's
  boundary ("metric formulas") stays intact.
- **Trade-offs**: Minor duplication of averaging logic — contained to one
  module, unit-tested against hand-computed slices.

### Decision: Two commands — `sync` and `regen` — instead of one overloaded verb
- **Context**: Requirement 4.3/4.4: regeneration from archive alone must be
  possible; Requirement 1: sync consumes a source directory.
- **Selected Approach**: `fitdocs sync SOURCE [--out] [--force]` (discover →
  dedup → process; `--force` reprocesses already-archived discoveries) and
  `fitdocs regen [--out]` (re-render every archived source; no SOURCE
  needed). Both share the same per-file pipeline and preservation rules.
- **Rationale**: Regen-without-source is observable proof of Requirement
  4.4; flags stay orthogonal.
- **Trade-offs**: Two entry points to document — both thin over one engine.

## Risks & Mitigations
- pyyaml emission style could shift across versions and break golden files —
  pin the dev lockfile; restrict frontmatter emission to one `safe_dump`
  call with fixed options; golden tests catch drift immediately.
- Hand-built SVG may render differently across viewers — stick to the plain
  shapes/paths/text subset with presentation attributes only; visual check
  in Obsidian + GitHub is an explicit validation task.
- Region markers deleted by users — loud per-document conflict (never
  overwrite); error message explains how to restore markers.
- `.fit` files that decode but contain almost nothing (minimal fixture) —
  generic fallback view plus missing-data honesty keeps output valid; e2e
  test covers the minimal fixture.
- Upstream schema drift — fit-ingest revalidation triggers (field renames,
  `SCHEMA_VERSION` bump, error taxonomy changes) require re-checking this
  spec; mirrored in this design's dependency notes.

## References
- `docs/reference/fitdocs-ai-reference.md` §3–§6 — chart spec, view
  structure, strength display model, divergence list
- `.kiro/specs/fit-ingest/design.md` — consumed contracts and boundary
- `.kiro/steering/tech.md`, `structure.md` — stack, layering, data-root and
  naming conventions
- `.kiro/specs/workout-docs/brief.md` — scope, seams, chart fidelity
  constraint
- Python 3.11 `tomllib` (stdlib) — read-only TOML parsing for athlete inputs
