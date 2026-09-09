# Research & Design Decisions: load-history

## Summary
- **Feature**: `load-history`
- **Discovery Scope**: Extension (a new package on top of an existing document
  contract, chart layer, settings reader and ownership guard) with one genuinely
  new element -- the first data-root location that is not a per-activity output.
- **Key Findings**:
  - The whole input already exists in the documents. `contract.LOAD_KEYS`
    (`src/fitdocs/contract.py:269-289`) puts `load_value` /
    `load_methodology` / `load_basis` in the frontmatter of every scored page,
    `contract.document_date` (`contract.py:536`) reads the page's local date,
    and `docio.read_frontmatter` (`docio.py:74`) is the one shared reader. No
    `.fit`, no payload comment and no `athlete.toml` read is needed.
  - A page that was *not computed* has **no** `load_value` key at all:
    `load/docedit.py:314` (`strip_frontmatter_load`) removes the three lines and
    `load/engine.py:406` calls it before writing a `NotComputed` outcome, while
    `apply_frontmatter_load` (`docedit.py:264`) writes them only from a real
    `LoadResult`. So "absent key" is an exact, already-guaranteed marker for
    missing data -- there is nothing to disambiguate and no zero to mistake.
  - Morton et al.'s illustrative figures are an *exact* regression vector. The
    recursion at `T = 100`, `i = 1`, `tau1 = 45`, `tau2 = 15`, `k1 = 1`,
    `k2 = 2` yields `k1*g(60) = 3350.8`, `k2*h(60) = 3044.3`, difference
    `306.5`, and asymptote `1449.07` -- against the paper's published `3,351`,
    `3,044`, `~307` and `1,449`. Reproduced numerically during this discovery.
    Note that the published pair is the **weighted** quantities, which is what
    fixes `k2 = 2` as the figures' own weighting and rules out reading `3,044`
    as a raw fatigue accumulator.
  - `layout.py` has no home for a non-activity page. `doc_path` is
    `workouts/<stem>.md` unconditionally (`layout.py:199`), `OWNED_PATHS`
    (`layout.py:92`) and `DECLARED_DIRS` (`layout.py:117`) enumerate five and
    two directory prefixes respectively, and three separate guards read them:
    `tests/test_confinement.py::permitted_locations` (line 150),
    `tests/test_layout.py:473` (an exact tuple pin), and
    `tests/test_ownership_contract.py` (a conformance test over
    `docs/ownership-contract.md`'s own list). `declaration.py:257`
    (`declaration_text`) is a two-branch `if/else` that must become a real
    dispatch before a third directory exists.
  - The chart layer's reusable half is exactly what this page needs and its
    per-activity half is exactly what it cannot use.
    `render/charts/svg.py` (`el`, `svg_document`, `fmt_num`, `text`) and
    `render/charts/series.py` (`gap_segments`, `paired_gap_segments`) are
    generic; `charts/hero.py` is km/min-axis, band-normalised and single-series
    on the y axis by construction. `gap_segments` already implements exactly the
    suppression rendering this spec needs -- a `None` breaks the polyline and is
    never interpolated across.

## Research Log

### How a load reaches a page's frontmatter, and what "not computed" looks like
- **Context**: The series' entire input is one number per page. Whether an
  absent load is distinguishable from a zero decides whether Requirement 3 is
  implementable at all.
- **Sources Consulted**: `src/fitdocs/contract.py:269-289`;
  `src/fitdocs/load/docedit.py:264-345`; `src/fitdocs/load/engine.py:369, 402-412,
  512, 522`; `src/fitdocs/load/render.py:56-186`; `src/fitdocs/load/types.py:171-245`.
- **Findings**:
  - `apply_frontmatter_load(markdown, result)` is the only writer of the three
    load keys and takes a `LoadResult`, so the keys exist only where a value does.
  - `strip_frontmatter_load` runs on the `NotComputed` and `Unsupported` paths,
    so a page that once scored and later did not carries no stale value.
  - `load_value` is emitted as a numeric scalar; `load_methodology` carries
    `LoadResult.calculator_id`, which is the registered id (or a plugin's id).
  - The `<!-- fitdocs-load:v2 ... -->` payload carries the non-selected channel
    values, flags, inputs and notes. None of them is on this page.
- **Implications**: read frontmatter only. The payload parser
  (`load/render.py:162`) stays unimported, which keeps this package off
  `fitdocs.load` entirely except for the settings read described below.

### The wave-0 prompt-date defect, and this spec's independence from it
- **Context**: `.kiro/queue/2026-08-27-prompt-date-strands-historical-documents.md`
  (critical, maintainer-accepted 2026-08-29) means most of the athlete's 2,478
  pages currently carry no computed load, and the roadmap lands the fix as wave 0
  before this spec's tasks run. The design must be correct either way.
- **Sources Consulted**: the queue item; `load/engine.py:504`;
  `load/prompts.py:110-124`; `benchmarks.py:126-152`.
- **Findings**: the four candidate fixes differ only in *which* pages end up
  carrying a `load_value`. None changes the key names, the value's meaning, or
  the absent-key marker.
- **Implications**: this spec's contract with wave 0 is exactly one sentence --
  *a page with no `load_value` is a counted gap, never a zero* -- and it holds
  under every candidate. No requirement, component or test here references the
  prompt-date semantic, and no task waits on it. The visible consequence is only
  that the coverage statement is honest about how much of the archive is
  currently unscored, which is the intended behaviour on today's archive.

### The fitness-fatigue model in the primary texts
- **Context**: Requirement 2 demands the recursion be the published one, its
  constants cited, and the seeds labelled as seeds.
- **Sources Consulted**: `docs/reference/banister-trimp-primary-sources.md`
  sections 3, D5, D6; `src/fitdocs/metrics/sources.py:149-190` (the existing
  `BANISTER_1991` and `MORTON_1990` `Citation` records);
  `src/fitdocs/citation.py` (the vocabulary).
- **Findings**:
  - M90 eq. (4)/(5), p. 1173: `g(t) = g(t-i)*e^(-i/tau1) + w(t)`,
    `h(t) = h(t-i)*e^(-i/tau2) + w(t)`; eq. (8) combines them as
    `p(t) = k1*g(t) - k2*h(t)`, with `k1`/`k2` applied once, at the combination.
  - B91 pp. 413-414 gives the average time constants 45 d and 15 d and the
    initial weightings K1 = 1, K2 = 2.
  - D5 is explicit that 45/15 are illustrative starting values and that M90's
    own fits landed at tau1 = 50/40, tau2 = 11 for its two subjects.
  - D6 records that the source's own fitted model predicted peaking imperfectly.
  - The existing `MORTON_1990` and `BANISTER_1991` records carry locators for
    the *training-impulse weighting* (`Eq. 2, p. 1172` and `p. 408`), not for the
    recursion.
- **Implications**: the recursion's constants need their own `Citation`
  records at their own locators. They name the same works, so a test pins their
  bibliographic fields equal to the metrics records' field for field, with only
  `key`, `locator` and `note` differing.

### The 42/7 pair, and why it does not ship
- **Context**: the brief and the roadmap both flag Coggan's Performance
  Management Chart constants as the interop default with no peer-reviewed origin
  and an unverified book locator.
- **Sources Consulted**: roadmap Phase 6 Constraints and Direct Implementation
  Candidates; the brief's Constraints section; `fitdocs.citation`'s
  `VerificationStatus` and `FitdocsChoice`.
- **Findings**: the trail runs to a 2006 conference presentation, a
  TrainingPeaks article that calls the values "nominal values based on the
  scientific literature" while dropping k1/k2 from the model, and Allen & Coggan
  (2010) ch. 8 **by reviewer account with the page unverified**. The roadmap's
  own Direct Implementation Candidate says verify from a physical copy *before
  either `CitedConstant` is written*.
- **Implications**: the 42/7 preset is designed and named but not shipped. The
  blocked-citation mechanism withholds exactly one constant record, and nothing
  else: the curve, the page, the command and the 45/15 seeds are all
  independent of it. The athlete can still type 42 and 7 into the settings; the
  page then reports the constants as the athlete's own, uncited, which is the
  honest description of what they are.

### The recursion form: exact decay against the vendor approximation
- **Context**: the brief requires fitdocs to pick one and justify it.
- **Sources Consulted**: M90 eq. (4)/(5); TrainingPeaks help text as summarised
  in the brief; numeric comparison run during this discovery.
- **Findings**: the vendor form's per-step weight `1/tau` exceeds the exact
  `1 - e^(-1/tau)` by 1.20% at tau = 42 and 1.12% at tau = 45.
- **Implications**: fitdocs uses the exact form, because it is what the primary
  text prints and because a 1% systematic bias in a nine-year integration is not
  worth inheriting from a help page. Recorded as a `FitdocsChoice`, not as
  anything a source instructed.

### Where a non-activity page can live, and everything that moves with it
- **Context**: constraint from the roadmap: "the data root has no home for a
  non-activity page today; `load-history` adds one, and every guard moves in the
  same change".
- **Sources Consulted**: `src/fitdocs/layout.py:43-127, 199-230`;
  `src/fitdocs/declaration.py:152-325, 374-440`; `tests/test_confinement.py:1-233`;
  `tests/test_layout.py:449-490`; `tests/test_declaration_goldens.py`;
  `docs/ownership-contract.md:26-44`; `src/fitdocs/contract.py:233` (`CONTRACT_VERSION`).
- **Findings**: five sites read the owned set and three of them pin it exactly.
  `declaration_text`'s `else` branch is currently the workouts branch, so a third
  directory silently inherits workout prose unless the function is restructured.
  `DECLARED_DIRS` drives a parameterized golden test, so a new declared directory
  adds one golden file generated by `tests/test_declaration_goldens.py`'s own
  generator, never hand-written.
- **Implications**: one task lands the layout constants, the ownership document,
  the declaration branch, the goldens and the confinement registration together;
  splitting them reds the tree in between.

### The chart primitives, and what the hero chart cannot be asked to do
- **Context**: Requirement 5 needs a calendar axis, an absolute shared scale,
  three series, a zero line, race markers and visible suppression.
- **Sources Consulted**: `src/fitdocs/render/charts/svg.py:39-128`;
  `series.py:34-160`; `hero.py:67-130, 164-330`; `palette.py:41-120`.
- **Findings**: `hero.py`'s x axis formats km and minutes only
  (`_format_x`, line 411), its series are band-normalised into `(0.42, 0.92)`
  (`_SERIES_BAND`), and its y ticks are drawn for one nominated series
  (`_render_y_axis`). None of that is parameterizable into a calendar chart.
  `svg.el` / `svg_document` / `fmt_num` and `series.gap_segments` are fully
  generic and already deterministic (no timestamps, no generated ids).
- **Implications**: a new sibling module under `render/charts/` built on the same
  primitives, with no change to `hero.py`. `palette.py` gains the three series
  colours, because it is the one home for colour in the render layer.

### The settings choke point
- **Context**: the brief and steering both flag `src/fitdocs/load/settings.py` as
  the repository's most-cited module (nine specs) and ask that it not be extended
  without a stated reason.
- **Sources Consulted**: `src/fitdocs/load/settings.py:1-160`;
  `src/fitdocs/settings.py:38-60`; `src/fitdocs/inbox.py`, `tiles.py`,
  `plugins.py` (three existing per-table readers).
- **Findings**: `settings.load_settings_document(data_root)` parses the shared
  file once and every table has its own reader that receives the mapping and
  validates only its own table. `[load]`'s reader is one such peer, not a
  gateway. `LoadSettings.default_calculator` is a plain field on the returned
  dataclass.
- **Implications**: this spec adds a fourth peer reader for a `[history]` table
  and **does not touch `load/settings.py`**. It *calls* `load_load_settings` once
  to read `default_calculator`, which is a read of a published field, not an
  extension of the choke point.

### The effort tag as a marker source
- **Context**: race markers must come from `effort-tags`' one reader.
- **Sources Consulted**: `.kiro/specs/effort-tags/design.md:410-600, 126-160`;
  `.kiro/specs/effort-tags/requirements.md:99-135`;
  `tests/test_contract_consumers.py:1-120`.
- **Findings**: the contract publishes `EffortKind`, `EffortTag`,
  `InvalidEffortTag`, `EffortTagProblem`, `EFFORT_KEYS`, `USER_KEYS` and exactly
  one reader `effort_tag(frontmatter)` that never raises; `None` means untagged
  and `InvalidEffortTag` must be reported by page and skipped, never read as
  untagged. Consumers register in `tests/test_contract_consumers.py::CONTRACT_BINDINGS`
  and are then structurally forbidden from spelling an effort key or importing YAML.
- **Implications**: one module in this package does all document reading and is
  the one registered consumer. Nothing else in the package sees a frontmatter
  mapping.

## Architecture Pattern Evaluation

| Option | Description | Strengths | Risks / Limitations | Notes |
|--------|-------------|-----------|---------------------|-------|
| New top-level package with a pure core and one I/O shell | `fitdocs/history/` : one reader module does all filesystem work; series, model and page rendering are pure | Matches `load/` and `metrics/`; the model is testable against published figures with no fixtures; determinism is provable at the pure boundary | One more top-level package | **Selected** |
| Extend `fitdocs.render` with a history view | Reuse the existing view assembly | No new package | `render/views.py` is `DocContext`-shaped (one `Activity`), and every view there is per-activity; the seam would have to be widened for a document with no activity at all | Rejected |
| A subcommand inside the load pass | Append the history write to `apply_load` | One command for the athlete | Widens the load pass's write surface into a second owned directory, couples `training-load` to this spec, and makes the history page's determinism depend on a pass that prompts | Rejected -- see decision below |
| Aggregate into a cache/index file first | Persist a derived daily series under `.cache/` | Faster repeat runs | A second source of truth that can go stale; 2,478 frontmatter reads is already fast; the brief's determinism guarantee is easier without it | Rejected |

## Design Decisions

### Decision: A new top-level owned directory `history/`, with `history/assets/`
- **Context**: Req 7.1-7.3. The data root has no home for a non-activity page.
- **Alternatives Considered**:
  1. The page inside `workouts/` -- rejected: everything under `workouts/` that
     is not `type: workout` is skipped by the engine's scan
     (`load/engine.py:590-611`) and by the audit (`audit.py:433`), so the page
     would be invisible to the tools that police that directory while still
     sitting in it; and the directory's own `AGENTS.md` says it holds generated
     *workout* documents.
  2. A single file at the data root -- rejected: an owned *file* at the root
     contradicts the contract's "owned means a directory prefix" shape
     (`layout.OWNED_PATHS` is a tuple of prefixes) and leaves the chart image
     homeless.
  3. `history/` with `history/assets/` -- selected.
- **Selected Approach**: two new prefixes in `OWNED_PATHS`; `history/` alone in
  `DECLARED_DIRS` (mirroring `workouts/assets/`'s exclusion, which is excluded
  because the parent's declaration already covers it).
- **Rationale**: mirrors the established `workouts/` + `workouts/assets/` shape
  exactly, so `asset_rel_path`'s doc-relative link idiom carries over unchanged.
- **Trade-offs**: a third declared directory forces `declaration_text` from an
  `if/else` into a dispatch, and adds one golden file.
- **Follow-up**: `CONTRACT_VERSION` advances (see below).

### Decision: The page is typed, and its type constant lives in this package
- **Context**: the roadmap's wiki-contract update asks for "the history page's
  owned location and, if typed, its document type".
- **Alternatives Considered**:
  1. Untyped -- rejected: a wiki page with no `type` is a second-class citizen
     in the reference PKM and gives no reader a way to recognise the page.
  2. `type: workout` -- rejected outright: it would make the page answer true to
     `contract.is_workout_document`.
  3. A new type value published from `fitdocs.contract` -- rejected for this
     spec: `src/fitdocs/contract.py` is `effort-tags`' file in this batch and is
     the repository's most heavily pinned leaf; a second spec editing it in the
     same wave is the merge conflict the boundary rules exist to prevent.
  4. A new type value published from this package -- selected.
- **Selected Approach**: `type: training-history`, defined once in
  `fitdocs/history/page.py`, re-exported from `fitdocs.history.__all__` and
  pinned in `tests/test_public_api.py`. A test asserts it is not equal to
  `contract.WORKOUT_TYPE`.
- **Rationale**: the value is this page's vocabulary, not the workout document
  contract's. The shared vocabulary the page *does* use -- the frontmatter
  fence, `type`/`generator` key names, the generator name and the generated
  banner prefix -- is imported from `contract`, never re-spelled.
- **Trade-offs**: document types are now named in two modules. Recorded as a
  revalidation trigger: if `wiki-contract` ever centralises a type registry,
  this constant moves there and the pin moves with it.
- **Follow-up**: the roadmap's Existing Spec Update for `wiki-contract` is
  landed by this spec's task 4.3, as an amendment block, exactly the way
  `effort-tags` landed the user-owned-keys half.

### Decision: `history_version`, not `doc_version`
- **Context**: the page needs a format version for the same reason workout
  documents have one.
- **Selected Approach**: the page carries `history_version: 1`, owned here.
  `contract.DOC_VERSION` (currently 5) is not used and not bumped.
- **Rationale**: `DOC_VERSION` versions the *workout* document format and gates
  regeneration of workout documents (`wiki-contract` Req 5). Reusing it would
  mean every change to this page's layout forces a workout-wide version gate
  event, and would make the two formats inseparable forever.
- **Trade-offs**: two version numbers in the data root. Both are namespaced by
  the page's `type`, so neither is ambiguous.

### Decision: exact `e^(-1/tau)` decay, rescaled to a daily average
- **Context**: Req 2.1-2.3, 2.6. The brief demands the daily-average form every
  platform draws *and* the primary text's recursion.
- **Alternatives Considered**:
  1. Vendor form `CTL += (TSS - CTL)/tau` -- rejected: 1.2% per-step bias against
     the printed equation, and its only attestation is a help page.
  2. Raw M90 accumulators as reported values -- rejected: they read ~45x a
     typical day's load, which no athlete can interpret and which does not
     compare with any platform.
  3. Exact recursion, reported after a constant rescaling -- selected.
- **Selected Approach**: run `g(t) = g(t-1)*e^(-1/tau1) + w(t)` exactly; report
  `fitness = k1 * g(t) * (1 - e^(-1/tau1))` and the fatigue analogue. The
  rescaling is a single positive constant per series, so it is an exact linear
  change of units: shape, ratios, zero crossings and the fitted-constant seam are
  all identical, and M90's own figures are recovered by dividing back.
  Equivalently the reported series is the exponential moving average
  `G(t) = G(t-1)*e^(-1/tau1) + w(t)*(1 - e^(-1/tau1))`, which converges to the
  mean daily load.
- **Rationale**: keeps the model literally the published one while putting the
  numbers on the scale the athlete's other tools use.
- **Trade-offs**: the page must state the scale, or a reader comparing against
  M90's figures is confused. It does.
- **Follow-up**: the worked-example test asserts the **unscaled** accumulators
  against the published figures and, separately, that the scaled series equals
  the unscaled one times the constant.

### Decision: shipped weightings are k1 = k2 = 1; M90's k2 = 2 is a test vector, not a default
- **Context**: Req 2.3 fixes form as fitness minus fatigue.
- **Findings that forced the decision**: M90's published day-60 figures are the
  *weighted* quantities: `k1*g(60) = 3350.8` and `k2*h(60) = 3044.3` with
  `k2 = 2`. Shipping `k2 = 2` would make form (`fitness - fatigue`) negative
  through any normal training block, which is not the quantity the brief names.
- **Selected Approach**: seeds `k1 = k2 = 1`, recorded as a `FitdocsChoice` with
  an explicit `Departure` from M90 eq. (8)'s illustrative weighting. The model
  accepts any `k1`/`k2`, and the worked-example test drives it with M90's own
  `(1, 2)`.
- **Rationale**: fitting `k1`/`k2` is `performance-model-fit`'s gated job; until
  then, an unfitted `k2 = 2` is no more defensible than 1 and is far more
  confusing. The interop definition (form = fitness - fatigue) is what the page
  claims and all it claims.
- **Trade-offs**: the shipped curve is not M90's `p(t)`. The page says so.

### Decision: the coverage threshold is a measured fitdocs choice at 0.80
- **Context**: Req 3.4 -- "cited or measured, never assumed".
- **Findings**: no source in the fitness-fatigue literature states a
  minimum-coverage rule; the question does not arise in prospectively collected
  study data. So there is nothing to cite and the value must be measured.
- **Selected Approach**: `FitdocsChoice` whose `search_basis` records the
  fruitless search and whose `measurement` records the sensitivity the shipped
  recursion actually has: one uncomputed daily page understates daily-average
  fitness by `1 - e^(-1/tau1)` of that page's load (2.198% at tau1 = 45 d) and
  fatigue by `1 - e^(-1/tau2)` (6.449% at tau2 = 15 d). A threshold of 0.80
  admits at most one uncomputed page in five, bounding a single admitted week's
  understatement at ~2.2% of fitness and ~6.4% of fatigue. A committed test
  reproduces both figures numerically from the shipped model.
- **Trade-offs**: the bound is per admitted week and compounds across
  consecutive admitted weeks; the page's "values following a suppressed period
  understate" sentence is what covers that, and it is a requirement (3.7), not a
  footnote.

### Decision: no clock is read at all
- **Context**: Req 8.5. The brief allows "the pass's single resolved `today`,
  and only for an 'as of' line if the design keeps one".
- **Selected Approach**: the page keeps no "as of" line and the pass takes no
  `today`. The chart's span is the archive's span.
- **Rationale**: byte-identical output on different calendar days is then true by
  construction rather than by discipline, and there is no `date.today()` in the
  package for a later change to start depending on. A test asserts the package's
  source names no clock function.
- **Trade-offs**: a reader cannot tell from the page when it was generated. The
  provenance banner deliberately carries no timestamp either
  (`contract.DOC_BANNER`, Req 4.5), so this is the established convention.

### Decision: `fitdocs history` is standalone and is not chained onto the load pass
- **Context**: the brief invited chaining "if the design finds it cheap".
- **Selected Approach**: it is not chained.
- **Rationale**: chaining would extend `apply_load`'s write surface into a second
  owned directory, put a deterministic pass downstream of an interactive one, and
  make `training-load` depend on this spec. It also makes every load run pay for
  a full archive re-read. The command is cheap to type and cheap to run.
- **Trade-offs**: the page can be stale after a load pass. The page's own
  coverage statement is what makes a stale page visibly stale, and the run report
  names the file it wrote.

### Decision: methodology resolution, and what happens when it is ambiguous
- **Context**: Req 4.2-4.5. Loads on different scales do not add.
- **Selected Approach**: explicit `--methodology` beats `[load].default_calculator`
  beats a unique methodology inferred from the archive. More than one methodology
  present with nothing configured is a configuration error (exit 2) naming each
  methodology and its page count. A configured methodology no page records is
  also a configuration error.
- **Rationale**: guessing the most common methodology would silently drop the
  athlete's other pages and produce a curve nobody asked for; refusing with the
  counts in hand is one command away from correct.

### Decision: the seam `performance-model-fit` plugs into
- **Context**: the roadmap requires a clean seam for a fitted constant set, with
  no fitting implemented here.
- **Selected Approach**: `ModelConstants(tau_fitness_days, tau_fatigue_days,
  k_fitness, k_fatigue, provenance, origin)` is the model's only constant input.
  `provenance` is a closed `ConstantProvenance` enumeration whose members are
  `SEEDS`, `CONFIGURED` and `FITTED`; this spec produces the first two and never
  the third, and the page's wording table already has a row for `FITTED`.
  `performance-model-fit` constructs a `ModelConstants` and calls the same
  `run_model` entry point.
- **Rationale**: one frozen value object and one enumeration member is the whole
  seam. Nothing about fitting -- no optimiser hook, no callback, no registry --
  is designed here, which is the point of the gate.
- **Follow-up**: recorded as a revalidation trigger; a change to
  `ModelConstants`' field set is a downstream break.

## Risks & Mitigations
- **The weekly table is long.** A nine-year archive is ~490 rows. Mitigation:
  it is a plain markdown table that renders and searches fine; the coverage
  statement summarises by calendar year so a reader has a short path. Recorded
  rather than solved, because truncating a table on a page whose whole purpose
  is honesty about coverage would be the wrong trade.
- **Race-marker labels collide.** ~30 races over nine years cannot all carry
  legible in-chart text. Mitigation: the SVG carries a numbered marker glyph
  only; the results are a numbered list in the markdown, keyed to the glyphs.
- **The recursion starts from zero.** The first weeks of the archive understate
  fitness because no history precedes the first page. Mitigation: the page states
  it, in the same paragraph as the suppression caveat. No warm-up period is
  fabricated.
- **A plugin calculator id could be an awkward frontmatter scalar.** Mitigation:
  the frontmatter emitter quotes any id that is not a plain token and fails
  loudly on a control character, rather than emitting a block that will not parse.
- **`contract.CONTRACT_VERSION` is edited by two specs in one wave.**
  `effort-tags` sets it to `"2"`; this spec sets it to `"3"`. Mitigation: the
  roadmap already orders them (`load-history` depends on `effort-tags`), the
  edit is a single string literal, and it is called out in this spec's
  `tasks.md` under "Shared source file" rather than hidden in a boundary line.
- **The Allen & Coggan locator may never be verified.** Mitigation: nothing in
  this spec waits on it. The 42/7 preset simply does not exist until it is.

## References
- `docs/reference/banister-trimp-primary-sources.md` sections 3, D5, D6 -- the
  extracted equations, the illustrative figures, and the ruling that 45/15 are
  seeds.
- Morton, R.H., Fitz-Clarke, J.R., Banister, E.W. (1990). Modeling human
  performance in running. *Journal of Applied Physiology* 69(3):1171-1177 --
  eq. (4), (5), (6), (8), (11) and the Fig. 3-4 illustrative figures.
- Banister, E.W. (1991). Modeling Elite Athletic Performance, in *Physiological
  Testing of the High-Performance Athlete* (2nd ed.), pp. 403-424 -- the two
  time constants and the initial weightings, pp. 413-414.
- `.kiro/queue/2026-08-27-prompt-date-strands-historical-documents.md` -- wave 0.
- `.kiro/specs/effort-tags/design.md` -- the tag contract this spec consumes.
- `.kiro/steering/roadmap.md` Phase 6 -- scope, constraints, boundary strategy,
  and the Direct Implementation Candidate that blocks the 42/7 citation.
