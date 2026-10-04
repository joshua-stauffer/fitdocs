# Research & Design Decisions: analytics-derived

## Summary
- **Feature**: `analytics-derived`
- **Discovery Scope**: Extension. Four producers registered through
  `analytics-index`'s producer seam, three of them thin adapters over existing
  engines (history, the athlete profile, the plan pass) and one new metric
  function in `fitdocs.metrics`. Light discovery: no new library, no external
  service.
- **How it was researched**: three read-only Explore subagents ran in parallel
  (the history series engine, the plan engine, the benchmark model and profile
  reader), with the worktree and probe rules passed verbatim. The metrics layer,
  the activity model, the provenance regime and the analytics-index contract
  were read in the main context. No DuckDB probe was needed or run: nothing in
  this spec issues SQL, and every table rule it relies on (types, comments,
  replace-whole) is `analytics-index`'s, already probed there. **No research
  downgrade.**
- **Key findings**:
  1. **Every engine this spec projects is already pure in its middle and
     impure only at the ends.** History (`history/engine.py:288-359`) reads
     settings and pages, computes, then renders and writes. The plan pass
     (`plans/engine.py:456-577`, `plans/reconcile.py:195-230`) discovers and
     parses, resolves, then renders and writes. The profile reader
     (`load/profile.py:448-466`) only reads. A behaviour-preserving extraction
     of each pure middle lets the index call exactly what the commands call.
  2. **The engines read more pages than the index holds.** History and the plan
     corpus read every `workouts/*.md` whose frontmatter declares a workout
     (`history/documents.py:178-221`, `plans/corpus.py:168-206`). The index's
     `CorpusSnapshot.pages` omits pages left out for no base reference or a
     shared base (`analytics-index/design.md:886-891, 1079-1083`). The derived
     tables must follow the engines' page set, not the snapshot's.
  3. **Only the plan pass depends on the date.** History's series ends at the
     last contributing day and reads no clock (`history/engine.py:87, 309-310`;
     load-history Req 1.8, 8.5). The profile's in-force rule takes an explicit
     date and never assumes today (`benchmarks.py:189-243`;
     `load/profile.py:153-168`). The plan pass splits not-logged from upcoming
     on `row.date < today` (`plans/matching.py:222-225`; plan-resolution Req
     2.6), and that is its only use of the date.
  4. **The profile's in-force rule is tiered, not "latest applies-from".**
     Tier 1 picks the latest `measured_on <= D`; only when none exists does
     tier 2 pick, among entries whose `applies_from <= D`, the one measured
     soonest (`benchmarks.py:189-243`; athlete-benchmarks Req 3.1-3.11). A SQL
     join on `applies_from <= date` alone would give a different answer, so
     the index must hold in-force periods computed by the profile's own rule.
  5. **No pause rule exists for a rolling window.** Normalized power carries
     the last recorded value across every gap, pauses included
     (`metrics/power.py:133-206`). The composition layer calls a step of more
     than one second a pause for alignment (`compose/stretches.py:17`).
     Time-weighted means and zone times credit each step to the earlier sample
     (`performance/models.py:86-111`, `metrics/zones.py:47-75`). Best efforts
     need their own stated rule.

## Research Log

### The upstream seam (analytics-index, base 266d362)
- **Sources**: `.kiro/specs/analytics-index/design.md:166-281` (seams 1-6),
  `:840-951` (ProducerSeam, Registry), `:1372-1411` (reconcile order),
  `:1698-1874` (schema 1); `tasks.md:109-165` (cross-spec shared files),
  `:530-559` (3.3 table-set pin), `:927-960` (6.2 corpus gating tests); the
  controller's wave-2 notes.
- **Findings**:
  - `ComputedProducer.rows(PageComputed)` receives the composed activity,
    metrics, provenance and athlete inputs; it is called only when the page's
    computed values are due and composable. Per-page rows omit `page_key`.
  - `CorpusProducer.fingerprint(snapshot)` and `.rows(snapshot)`; the refresh
    replaces the producer's tables whole in one transaction when
    `corpus_fingerprint(fp, fitdocs_version, SCHEMA_VERSION)` moves.
  - `CorpusSnapshot(data_root, pages, today, athlete_fingerprint)`; pages are
    the held pages only, sorted by path. Corpus tables that refer to pages
    declare their own `page_key`.
  - `ColumnType` has no zone-aware type; a `TIMESTAMP` must end `_utc` or
    `_local`; a unit-suffixed column's description must name the unit word
    (`UNIT_SUFFIXES`); the `index_` prefix is reserved; names unique across
    producers.
  - `SCHEMA_VERSION = 1`, `_DIGESTS_BY_VERSION` append-only; each schema-changing
    lander advances by one from `main`.
  - Allowed dependencies: later producers may import the engine they project,
    and from `fitdocs.index` only `producer`, `schema` and `fingerprint`
    (`design.md:137-140`).
- **Implications**: mean-max is a `ComputedProducer` and inherits the
  stale-document rule; the three others are `CorpusProducer`s. Registration is
  an append to `registry.py`; nothing in the pass, store or read side changes.

### History (load-history)
- **Sources**: `history/engine.py:288-435`, `history/series.py:248-575`,
  `history/model.py:46-135`, `history/documents.py:113-221`,
  `history/page.py:359-430`, `history/__init__.py:1-68`,
  `history/sources.py:421-461`; `tests/test_public_api.py:911-933`;
  `tests/history/test_boundary.py:119-128, 265-300`;
  `tests/load/test_settings.py:1952-2017`;
  `.kiro/specs/load-history/requirements.md:98-202`.
- **Findings**:
  - `run_history`: settings (`fitdocs.toml` `[history]`, `[load]`), scan,
    empty-archive gate, `configured = history.methodology or
    load.default_calculator`, `select_methodology`, `partition_pages`,
    `build_daily_series`, `resolve_constants`, threshold, `run_model`,
    `suppressed_weeks`, `week_rows`, coverage, criterion; then render and write.
  - One methodology per run; `select_methodology(pages, requested=m, ...)`
    accepts any `m` a page records, which is what `--methodology m` does.
  - `DayLoad.recorded_load` is `0.0` on a day with no load (load-history Req
    1.7 keeps a rest day distinguishable through the page counts).
  - The page's chart withholds fitness, fatigue and form on every day of a
    suppressed week (`page.py:359-430`, load-history Req 3.8); weekly rows hold
    `None` there (`series.py:535-575`).
  - The page rounds to one decimal (`page.py:327-337`); the series is never
    rounded.
  - Not on the public surface: `DayLoad`, `DailySeries`, `WeekRow`,
    `build_daily_series`, `week_rows`, `scan_documents`. The surface is
    append-only and pinned (`_HISTORY_SURFACE`). History modules' import
    targets are pinned exactly (`tests/history/test_boundary.py:265-300`).
  - `load_load_settings` has exactly four sanctioned callers
    (`tests/load/test_settings.py:2008-2017`).
  - Defect noticed: a negative `load_value` passes `_read_load`
    (`documents.py:147-159`) and makes `run_model` raise `ValueError`
    (`model.py:67-80`), which `cli.py:717` does not catch.
- **Implications**: extract `read_history_inputs` and `compute_history` from
  `run_history` without changing it, add a public `day_rows` in `page.py`
  built on the chart's own `_suppressed_day_indices` (which stays, because
  `tests/history/test_page.py:981-1046` and `tests/test_history_e2e.py:18, 337`
  name it as the mutation site), and append those names to the surface.
  The producer reaches `load_load_settings` only through history's own reader,
  so the caller pin does not move.

### The athlete profile and benchmarks
- **Sources**: `benchmarks.py:34-638`, `load/profile.py:89-177, 319-466`,
  `athlete.py:39-183`, `performance/engine.py:300-526`,
  `load/threshold/anchors.py:91-168`;
  `.kiro/specs/athlete-benchmarks/requirements.md:111-371`,
  `.kiro/specs/performance-benchmarks/requirements.md:191-263`.
- **Findings**:
  - `load_profile(data_root)` reads `athlete.toml`, returns an empty profile when
    absent, and parses `[benchmarks]` eagerly, raising `ProfileError` (an
    `AthleteFileError`) on malformed entries.
  - `Benchmark(kind, discipline, value, measured_on, note, applies_from,
    source)`; `BenchmarkSource(kind, method, document, inputs, citation)`;
    `BenchmarkKind` values carry the unit in the key.
  - `BenchmarkSet.applicable(kind, *, discipline, on)` is the in-force rule
    (Finding 4). The natural key `(discipline, kind, measured_on)` is unique.
  - `load_athlete_inputs` never reads `[benchmarks]`, so the index's athlete
    fingerprint does not cover benchmarks.
  - The training-load calculator borrows across disciplines
    (`anchors.py:101-168`); the store does not.
- **Implications**: no engine change. The producer calls `load_profile` and
  `applicable`; it fingerprints `athlete.toml`'s bytes itself.

### The plan pass (training-blocks, plan-resolution)
- **Sources**: `plans/engine.py:121-194, 282-577`, `plans/reconcile.py:1-230`,
  `plans/matching.py:55-391`, `plans/aggregate.py:49-163`,
  `plans/corpus.py:97-206`, `plans/model.py:52-372`, `plans/__init__.py`,
  `cli.py:1538-1601`; `tests/test_public_api.py:1074-1110`,
  `tests/plans/test_boundary.py`; plan-resolution Req 1-8, training-blocks
  Req 1-8.
- **Findings**:
  - `run_plan` discovers, parses, renders and writes in one function; the
    discover-and-parse half (`engine.py:476-532`) is not reachable without the
    writes. `reconcile_block` is pure and public.
  - `Reconciler` scans the corpus and selects the methodology lazily, once per
    run, only when a valid block exists.
  - The corpus is built from frontmatter only and does not require `sources`.
  - Row states: matched, overridden, skipped, `not logged`, upcoming; matched
    rows carry exact, absorbed or ambiguous. `MesocycleLoad` holds the
    actual-load picture with `total`, `lower_bound`, `percent_of_target`.
  - Block identity is the source stem; planned-workout ids are unique and
    stable; logged paths are `workouts/<stem>.md`, the index's `pages.path`
    format.
  - The plan package's surface is append-only and pinned
    (`tests/test_public_api.py:1074-1110`); its modules are registered with
    exact import targets, and only `engine` may spell a write.
- **Implications**: extract `read_plan_sources` from `run_plan`, add
  `resolve_plans` to `reconcile.py` sharing `Reconciler`'s lazy scan, and
  append them to the surface. No new plans module, so the boundary registry
  does not move.

### Best efforts (mean-max)
- **Sources**: `model.py:106-173` (`Samples`), `metrics/power.py:133-243`,
  `compose/stretches.py:17-52`, `compose/alignment.py:55-62`,
  `performance/models.py:23-111`, `metrics/zones.py:13-75`,
  `metrics/sources.py:1-660`, `citation.py:86-199`,
  `tests/metrics/test_constant_guard.py:1-200`,
  `tests/metrics/test_sources.py:1239-1278, 312-332`,
  `.kiro/specs/fit-ingest/requirements.md:545-575`.
- **Findings**:
  - The model has no timer or pause events; a pause shows only as a step in
    `time_s`. Power and heart rate are integers, speed a float; `None` is "not
    recorded" and a recorded `0` is real.
  - fit-ingest Req 15 and 16 require every constant a reported metric is
    computed from to carry a machine-readable record: a `Citation`, or a
    `FitdocsChoice` with justification and search basis. `CitedConstant`'s
    value is `int` or `float` only.
  - `metrics/sources.py`'s registry is pinned at exactly ten constants and
    three choices (`tests/metrics/test_sources.py:312, 332, 1245, 1267`), and
    the literal guard scans only `aggregates`, `power` and `stress`. Adding
    records there would break fit-ingest's own pins.
  - `history/sources.py` and `performance/sources.py` each keep their own
    records and their own literal guard: the precedent for a separate records
    module.
- **Implications**: `fitdocs.metrics.mean_max` holds the computation and
  `fitdocs.metrics.mean_max_sources` its records, guarded by their own tests;
  a fit-ingest amendment states that the library gains the function and that
  its constants are classified under Req 15.8.

### Fixtures and test infrastructure
- **Sources**: `tests/fixtures/builder.py`, `merge.py`, `identity.py`;
  `tests/history/test_engine.py:37-98` (hand-written workout pages and
  settings); `tests/plans/test_reconcile.py:40-210`, `tests/plans/fixtures/`;
  analytics-index tasks 4.2 (`tests/index/_helpers.py`) and 5.1/6.1
  (`tests/index/conftest.py`).
- **Findings**: history and plan tests write frontmatter-only workout pages by
  hand; that is enough for the load-series and block producers, which read
  frontmatter only. Mean-max needs `Samples`, built directly for unit tests and
  through the real sync with `merge.py` files for composed activities.
- **Implications**: one new fixture module, `tests/index/derived/conftest.py`,
  owned by one task created before first use, builds a "derived" data root:
  frontmatter pages carrying loads under two methodologies, a page with no
  sources, `athlete.toml` with tiered benchmarks, a plan source, and
  `fitdocs.toml`.

## Architecture Pattern Evaluation

| Option | Description | Strengths | Risks / Limitations | Notes |
|---|---|---|---|---|
| Thin adapters over extracted engine seams | Each producer calls a public, behaviour-preserving function the owning engine's command also calls | One computation by construction; tests compare against the engine | Small refactors in three engine packages; public-surface pins move | **Selected** |
| Re-derive from the snapshot's frontmatter | Producers rebuild series, resolution and in-force rules from `CorpusSnapshot.pages` | No engine change | A second implementation; disagrees on left-out pages; violates the roadmap decision | Rejected |
| Read the rendered pages back | Parse `history/` and `blocks/` pages | No engine change | Parses generated markdown; rounded values; stale until the next `history`/`plan` run | Rejected |
| Mean-max in SQL at query time | A view over `records` | No new table | Pause rule left to every query; ~9M-row windows per question | Rejected by the brief |

## Design Decisions

### Decision: Windows never span a break in continuity; one maximum step covers pauses and dropouts
- **Context**: Requirement 2. The model has no pause events; devices record at
  1 Hz or at irregular "smart" intervals; channels drop out independently;
  composed channels are absent where the donor did not record.
- **Alternatives Considered**:
  1. Carry the last value across every gap, as normalized power does.
  2. Count unrecorded time as zero.
  3. Join the stretches, ignoring wall-clock time between them.
  4. Cut a channel's recording into stretches wherever two consecutive
     recorded values of that channel are more than a maximum step apart; hold
     each value within a stretch; windows stay inside one stretch.
- **Selected Approach**: Option 4, on a one-second grid anchored at each
  stretch's first recorded instant; a window of `d` seconds is `d` consecutive
  grid seconds; the earliest best window wins a tie.
- **Rationale**: Options 1 and 3 fabricate continuous effort across a café
  stop or a ten-minute strap dropout; option 2 fabricates zeros (CLAUDE.md
  hard rule). Option 4 bounds the held time by the maximum step and handles
  pauses, dropouts, donated channels and irregular recording with one rule and
  one constant. The grid convention matches the NP resample (`range(int(span) +
  1)`), so a 1 Hz recording of N samples supports a window of N seconds.
- **Trade-offs**: A sub-second recording contributes only the value held at
  each whole second. A pause shorter than the maximum step is held through.
- **Follow-up**: the maintainer measures the step distribution and curve-point
  loss on the real archive (tasks, maintainer-only).

### Decision: The maximum step is 5 seconds, not the composition layer's 1 second
- **Context**: `compose/stretches.py:17` cuts at more than 1 s, justified by
  "Recording is 1 Hz" for alignment, where a cut costs nothing.
- **Alternatives Considered**: 1 s (reuse); 5 s; 10 s; 30 s.
- **Selected Approach**: 5.0 s, recorded as a `FitdocsChoice`.
- **Rationale**: for best efforts a cut loses data. 1 s would break a
  smart-recording file at every multi-second step and erase its long-window
  points. 5 s bridges brief Bluetooth dropouts and irregular steps while
  holding at most 4 s of value per step (0.3 % of a 20-minute window), and
  still breaks at a stop long enough to trigger auto-pause. 10 s and 30 s
  would hold through real stops and inflate short-window peaks.
- **Trade-offs**: an assumption about the archive (the real step distribution
  is personal data). It is stated as such and measured by the maintainer.
- **Follow-up**: changing the value later changes existing rows, which the
  computed tier does not recompute on an upgrade, so it advances
  `SCHEMA_VERSION` (design, Revalidation Triggers).

### Decision: A fixed duration set of 28 durations, 1 s to 6 h
- **Selected**: 1, 5, 10, 15, 20, 30, 45 s; 1, 2, 3, 4, 5, 6, 8, 10, 12, 15,
  20, 30, 40, 45 min; 1, 1.5, 2, 3, 4, 5, 6 h.
- **Rationale**: a near-logarithmic ladder from sprint to long endurance,
  dense where threshold tests live. It contains the durations fitdocs's own
  threshold derivations name: 15 min (`ftp_short_protocol_floor_s`), 20 min
  (`twenty_minute_power_factor`), 60 min (the FTP definition and Riegel solve
  target). Every page and channel uses the same set, so curves compare.
- **Trade-offs**: a query for an unlisted duration (7 min) must use `records`.
- **Follow-up**: the implementing task performs and records the literature
  search Req 15.9 asks for. No search was run at design time; the design
  states the value and its justification only.

### Decision: Best efforts are a wide row per duration, with window starts
- **Alternatives**: a long table `(channel, duration, value)` with a unitless
  value column; a wide row per duration.
- **Selected**: one row per duration, with `power_w`, `speed_mps`,
  `heart_rate_bpm` and a `*_start_s` per channel; a row only when at least one
  channel supports the duration.
- **Rationale**: unit suffixes stay meaningful (the long form would need a
  unit column and a generic `value`); the window start lets a reader find the
  effort in `records` and lets tests check a value independently.

### Decision: Corpus tables follow the engines' page sets, fingerprinted without a seam change
- **Context**: Finding 2.
- **Alternatives**:
  1. Feed `CorpusSnapshot.pages` to the engines (disagrees on left-out pages).
  2. Ask `analytics-index` to add left-out pages to the snapshot (a seam
     change, a revalidation trigger for the sibling).
  3. Call the engines' own readers in `rows`, and fingerprint the held pages
     from the snapshot plus every other `workouts/*.md` read directly.
- **Selected**: Option 3. Left-out pages are few (usually none plus
  `AGENTS.md`), so the extra reads per refresh are negligible.
- **Trade-offs**: any byte change to any markdown file in `workouts/`
  recomputes the load-series and block tables (about one corpus scan, 1-2 s at
  2,500 pages). Over-inclusive, never stale.
- **Follow-up**: recorded as an optional upstream improvement (Upstream
  issues).

### Decision: Fingerprints never raise for an input fault
- **Context**: `analytics-index` states that an error in a producer's
  replacement rolls back and is reported, but not what happens when
  `fingerprint()` raises (`design.md:1399-1402`).
- **Selected**: each derived fingerprint folds an unreadable file or an
  unresolvable plan directory into its digest as a marker; `rows()` then calls
  the engine, which raises its own error, reported as that producer's failure.
- **Rationale**: keeps a malformed `fitdocs.toml` from aborting the other
  producers' refresh, whatever the upstream does with a raising fingerprint.

### Decision: The block table records the date it was resolved under
- **Context**: not-logged versus upcoming depends on the current date.
- **Selected**: `blocks.resolved_on`, the snapshot's `today`; the block
  producer fingerprints `today` only while at least one plan source exists.
- **Rationale**: a reader of "upcoming" needs the date it was upcoming as of;
  a data root without plans never rewrites the index because a day passed.

### Decision: In-force periods are evaluated at breakpoints by the profile's own rule
- **Context**: Finding 4.
- **Selected**: for each `(kind, discipline)` group, evaluate
  `BenchmarkSet.applicable` at every distinct `measured_on` and `applies_from`
  date of the group, in order; merge consecutive dates with the same winner
  and the same retroactive flag into one period; the last period is open.
- **Rationale**: any rule that decides by comparing the date with the
  entries' own dates is constant between those dates, so evaluating at them
  reproduces the rule for every day without restating it. The test checks
  every day of a window against `applicable` directly.

### Decision: History's suppressed-day rule gets a second reader, not a new home
- **Context**: the chart withholds daily values in suppressed weeks through a
  private helper (`page.py:359-374`). Existing tests and docstrings name that
  helper as their mutation site (`tests/history/test_page.py:981-1046`,
  `tests/test_history_e2e.py:18, 337`), and one calls `_build_chart`
  directly.
- **Selected**: `fitdocs.history.day_rows(series, model, weeks)`, defined in
  `page.py`, returns each day's values with suppression decided by the same
  `_suppressed_day_indices` the chart calls. Neither the helper nor
  `_build_chart` changes, so no existing test or docstring is edited.
- **Rationale**: one rule with two readers; moving it would have made those
  docstrings' mutation instructions stale (Step 3.5 round 1, S2).

### Decision: No ownership-contract change
- **Context**: the contract states what fitdocs writes and where; the index
  section (`analytics-index`) covers the index directory.
- **Selected**: no new write location, no document change, so no contract
  text and no `CONTRACT_VERSION` advance. Each corpus table states its
  agreement rule ("as of the last refresh") in its description, which
  `analytics-query`'s schema view and `docs/analytics.md` project.

### Decision: Free text stays out
- **Selected**: benchmark notes, derived inputs text, planned-workout
  prescriptions and override reasons are not held; titles, goals, foci and
  one-line summaries are, as `pages.title` is.
- **Rationale**: the roadmap's Phase 10 exclusion of free-text columns.

## Synthesis

- **Generalization**: the three corpus producers share one input concern
  (digests of files they read) and one page-key concern (path to key from the
  snapshot). One helper module serves both; each producer stays a thin
  adapter. The four producers do not share a base class: three tiny protocols
  already exist upstream.
- **Build vs adopt**: every corpus computation is adopted from its engine; the
  only build is mean-max. No library offers a pause-aware rolling maximum over
  the activity model; DuckDB window functions are the read side's, and the
  write side must not depend on SQL for a metric (one computation in
  `fitdocs.metrics`).
- **Simplification**: no per-methodology producer, no table per channel, no
  separate plan-sources table (a `valid` flag on `blocks`), no amendment-trail
  tables, no "current threshold" view (a query joins `benchmark_periods`).

## Risks & Mitigations
- **The real archive's recording steps are unknown** (personal data). The
  5-second maximum step may erase long-window points on sparse files.
  Mitigation: maintainer-only measurement with a stated threshold that queues a
  follow-up.
- **Per-page computed rows are not recomputed on a fitdocs upgrade.** A later
  change to the mean-max rule would leave old rows. Mitigation: a rule change
  advances `SCHEMA_VERSION` (forcing a rebuild); the constants are pinned by
  value in tests so a change is deliberate.
- **Corpus-producer cost on every changed sync**: one history scan and one plan
  corpus scan (about 1-2 s each at 2,500 pages). Mitigation: measured by the
  maintainer; acceptable against a sync that already writes pages.
- **Engine refactors could change bytes.** Mitigation: the history golden, the
  plan goldens and the existing engine suites run unchanged; each seam task
  asserts its command's output is byte-identical.
- **Sibling ordering**: `SCHEMA_VERSION`, the table-set pin, `docs/analytics.md`
  and the skill examples depend on which Phase 10 spec lands first.
  Mitigation: tasks read `main`'s values at landing; cross-spec shared files
  are append-only.

## Upstream issues (for the controller)
1. **`CorpusSnapshot` holds only the indexed pages**
   (`.kiro/specs/analytics-index/design.md:886-891`, `:1079-1083`), while the
   history and plan engines read every workout page
   (`src/fitdocs/history/documents.py:178-221`,
   `src/fitdocs/plans/corpus.py:168-206`). Designed around with no seam change
   (the derived inputs helper reads the non-held `workouts/*.md` files). An
   optional improvement: carry the left-out pages' paths and document
   fingerprints in the snapshot.
2. **A raising `CorpusProducer.fingerprint()` is unspecified**
   (`design.md:1399-1402`; `tasks.md:939-945` tests only a raising
   replacement). Designed around (derived fingerprints never raise). Smallest
   change: one sentence and one test in analytics-index 6.2 treating a
   fingerprint exception as that producer's error.
3. **The derived producers' sibling imports.** `design.md:137-140` allows a
   later producer to import only `producer`, `schema` and `fingerprint` from
   `fitdocs.index`; the derived producers also import their own package's
   helper (`fitdocs.index.derived.inputs`). Smallest change: allow "and the
   producer package's own modules". Nothing upstream enforces the sentence, so
   this spec's own boundary guard states the rule it follows.
4. **The computed tier does not follow fitdocs upgrades.** `computed_due`
   (`design.md:1376-1381`) moves on the render fingerprint, never the fitdocs
   version, so a metric fix in a later release leaves existing `activities`
   and `mean_max` rows until a rebuild or regen. This spec mitigates for
   mean-max by advancing `SCHEMA_VERSION` on any rule change; the core tables
   have the same exposure.
5. **An `athlete.toml` the refresh cannot load stops every producer.**
   analytics-index's refresh loads the athlete inputs before reconciling
   (`.kiro/specs/analytics-index/design.md:1366-1367`, step 6:
   `load_athlete_inputs` raising `AthleteFileError` gives FAILED). That
   loader rejects invalid TOML, an unsupported profile version and malformed
   flat keys (`src/fitdocs/athlete.py:62-91, 115-118, 130-183`) but never reads
   `[benchmarks]`. So this spec's Req 8.5 holds for a malformed benchmark entry
   in a valid profile (the benchmark producer alone fails), while a profile
   the upstream loader rejects fails the whole refresh and every table keeps its
   rows. Requirement 8.5 was worded to say so. For the controller to queue: no
   change proposed here.

## References
- `.kiro/specs/analytics-index/{requirements,design,tasks,research}.md`: the
  producer seam and schema contract.
- `.kiro/specs/load-history/requirements.md`: the series, model and weekly
  semantics this spec projects.
- `.kiro/specs/athlete-benchmarks/requirements.md` (Req 1, 3; Amendments 1, 2)
  and `.kiro/specs/performance-benchmarks/requirements.md` (Req 5, 6, 10).
- `.kiro/specs/training-blocks/requirements.md` and
  `.kiro/specs/plan-resolution/requirements.md` (Req 2.6: the only use of the
  date).
- `.kiro/specs/fit-ingest/requirements.md` Req 15, 16: the provenance regime
  the mean-max constants follow.
