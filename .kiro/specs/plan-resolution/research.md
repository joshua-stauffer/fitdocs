# Research & Design Decisions: plan-resolution

## Summary
- **Feature**: `plan-resolution`
- **Discovery Scope**: Extension (light discovery) -- every seam this feature
  plugs into is either shipped (`contract`, `docio`, `history`, `layout`,
  `cli`, the confinement guard) or fixed verbatim by the wave-1
  `training-blocks` design (`Block`, `Resolution`, `run_plan(resolve=)`,
  `blocks/` and the `plan` entry point). No external library, no new
  dependency, no network.
- **Key Findings**:
  - **The brief's "one contract reader per field, literals into
    `FORBIDDEN_LITERALS` in the same change" collides with two registered
    consumers.** `tests/test_contract_consumers.py`'s literal scan runs over
    every `CONVERTED_MODULES` entry, and two of them spell the very keys the
    new readers would guard: `src/fitdocs/render/frontmatter.py:124-131`
    writes `data["date"]`, `data["start_time"]`, `data["sport"]`,
    `data["modality"]`, `data["indoor"]` as bare literals (the emitter), and
    `training-blocks`' `plans/page.py` will spell `date`, `sport`,
    `modality`, `indoor` in `PLANNED_FRONTMATTER_KEYS`. Adding the literals
    to the pin reds both. Resolution: the change that adds the readers also
    adds the five key constants (`DATE_KEY`, `START_TIME_KEY`, `SPORT_KEY`,
    `MODALITY_KEY`, `INDOOR_KEY`) beside `UUID_KEY`/`SOURCES_KEY`, routes
    both spellers through them, and extends their `CONTRACT_BINDINGS`
    entries. `tests/test_contract.py:233-268`'s anti-drift test already
    resolves a bare `ast.Name` key through the frontmatter module's
    namespace, so the emitter edit is anticipated by that test's own design.
    This also absorbs queue item `2026-07-26-date-key-has-no-constant`.
  - **`history`'s published `select_methodology` / `partition_pages` are
    typed over the unpublished `PageRecord`** (`history/series.py:230,314`;
    `history/documents.py:82`), and `PageRecord` is not in
    `history.__init__.__all__`. Both functions read only `.methodology`
    (`_observed_counts`, `partition_pages`). Under `mypy --strict` the
    reconciler's own record cannot be passed without either publishing
    `PageRecord` and fabricating its `effort`/`tag_problem` fields, or
    widening the two signatures to a structural `Protocol`. Chosen: a
    `MethodologyRecord` Protocol (`methodology: str | None`) with a
    `TypeVar` so `partition_pages` returns the caller's own record type --
    the generalization lens: the interface widens, the implementation and
    every existing caller are untouched. `history/series.py` already
    imports `typing`, so `tests/history/test_boundary.py`'s equality pin on
    import targets does not move.
  - **`training-blocks`' package boundary forbids exactly what this feature
    needs.** Its `tests/plans/test_boundary.py` forbids any module under
    `fitdocs.plans` importing `fitdocs.history` and `fitdocs.load` (all of
    it). The reconciler needs `fitdocs.history`'s *root* (the four published
    methodology names and `load_history_settings`) and
    `fitdocs.load.settings` (`load_load_settings`, the same two readers
    `history/engine.py:316-326` composes to pick the configured
    methodology). Resolution: the forbidden prefixes stay; the boundary test
    gains an explicit (module, exact target) exemption map --
    `plans.reconcile` → `fitdocs.history`, `fitdocs.load.settings`;
    `plans.aggregate` → `fitdocs.history` -- so every `fitdocs.history.<sub>`
    deep import and every other `fitdocs.load.<sub>` stays forbidden.
  - **The `today` clock.** `training-blocks` 8.4 requires `fitdocs plan` to
    read no clock and to be byte-identical across calendar days, and its
    task 4.6 tests that under two fake system dates. Once the command passes
    a resolver, a row crossing `today` legitimately flips
    `upcoming` → `not logged`. Resolution: `today` is resolved once in
    `cli.py` (beside `_local_tz`, `cli.py:665-674`) and handed in; nothing
    under `fitdocs.plans` names a clock (the wave-1 clock scan keeps
    holding); the page never prints `today`; and this feature lands an
    amendment to `training-blocks`' requirements 8.4 and 8.8 the way
    `training-blocks` landed wiki-contract's Amendment 3, re-anchoring its
    two-dates e2e test to two dates on the same side of every row.
    *(Superseded 2026-09-16, cross-spec review round 1: `training-blocks`
    scoped 8.4 and 8.8 itself to admit the resolver and the chaining, so
    no criterion is amended; what remains is the re-anchoring of its two
    pins (task 3.2) and a record of it in its `spec.json` and
    `requirements.md` (task 3.4) -- design.md TrainingBlocksSpecUpdate.)*
  - **The `run_plan` AST pin moves.** `training-blocks` task 4.3 pins
    "`run_plan` loaded by name exactly once, inside `plan_command`"
    (`tests/test_cli_plan.py`, shape of `tests/test_cli_history.py:660`).
    After this feature `cli.py` names `run_plan` nowhere: the chaining sites
    and `plan_command` all call one helper `_run_plan_pass`, which calls the
    published `run_reconcile`. The pin is re-stated, not deleted (see
    design, CliChaining).

## Research Log

### The chaining sites and the load pass's shape
- **Context**: the brief names `cli.py:279-284, 306-309, 385-386` as the
  three sites and `_run_load_pass` as the pattern.
- **Sources Consulted**: `src/fitdocs/cli.py:225-390` (`sync_command` both
  branches, `regen_command`), `:625-662` (`_run_load_pass`), `:665-674`
  (`_local_tz`), `:451-478` (`history_command`), `:1178` (`_finish`).
- **Findings**: the anchors are exact at HEAD e40e361 -- re-created as b381f0d after the 2026-09-16 .git loss, identical tree -- (`load_report =
  _run_load_pass(` at 280, 309, 385). Each site is followed by
  `_report_plugin_errors` and `_finish(failed=...)`. `_run_load_pass` maps
  `SettingsError` to `_config_error` (exit 2) and returns the report whose
  `.failures` the call site folds into `_finish`. `fitdocs load` (`:414`) is
  a fourth load-pass site the brief deliberately does not name.
- **Implications**: `_run_plan_pass(data_root, *, today)` follows
  `_run_load_pass`'s shape exactly (catch `SettingsError` → exit 2; print;
  return) and is inserted after the load pass at the three sites; each
  `_finish` gains `or plan_report.failed`. `fitdocs load`, `history`, `check`
  stay unchanged (Req 8.3).

### What the corpus scan can read
- **Context**: which fields the frontmatter carries, and how each is typed
  after PyYAML.
- **Sources Consulted**: `src/fitdocs/render/frontmatter.py:109-151`;
  `src/fitdocs/contract.py:306-360` (`LOAD_KEYS`, `MANAGED_KEYS`),
  `:869-907` (`document_date`); `src/fitdocs/history/documents.py:130-160`
  (`_read_load`); `src/fitdocs/docio.py`.
- **Findings**: `date` is emitted quoted (reads back `str`; hand-edited
  unquoted reads back `datetime.date`); `start_time` is
  `local.isoformat()` of a tz-aware datetime, which PyYAML quotes on dump
  (reads back `str`; unquoted reads back `datetime`); `sport` and `modality`
  are the enum `.value` strings, always emitted; `indoor` is emitted only
  when `True`; `sub_sport` is never emitted (`model.py:127`, ingest only);
  the three load keys are written by the load pass. `_read_load` rejects
  `bool`, non-finite and overflowing values and drops a load whose
  methodology is absent -- the rule `document_load` adopts verbatim.
- **Implications**: five new readers (`document_sport`, `document_modality`,
  `document_indoor`, `document_start_time`, `document_load`) and one value
  type (`LoadReading`) in `contract.py`; the readers return raw `str` for
  sport and modality because the contract may not import `fitdocs.model`
  (`tests/test_contract.py:974-1000`), and the scan maps them onto `Sport`
  / `Modality` -- an unknown spelling is `None`. `document_start_time`
  accepts only a tz-aware value (a naive one cannot be placed on a
  timeline and is `None`).

### How `history` picks and applies the one methodology
- **Context**: Req 6.2 requires the same rule the history page uses.
- **Sources Consulted**: `src/fitdocs/history/engine.py:288-345`;
  `src/fitdocs/history/series.py:230-336`; `src/fitdocs/history/__init__.py`.
- **Findings**: `configured = history_settings.methodology or
  load_settings.default_calculator`; `select_methodology(pages,
  requested=None, configured=configured)` returns a `MethodologyChoice`
  (`methodology`, `source` ∈ requested/configured/inferred, `excluded`
  counts) or a `MethodologyProblem(detail)`; `partition_pages` includes
  pages with `methodology is None` (unscored) and excludes pages under
  another methodology. History raises `MethodologyConfigurationError`
  (exit 2) on a problem, but it gates the empty archive first.
- **Implications**: the reconciler composes the same two settings readers
  and the same selection over the *whole* corpus (so the block page and the
  history page agree), but degrades on a problem instead of raising (Req
  6.6): matching still runs, every sum reads "not computed", the detail is
  stated once. The empty-corpus case is one `MethodologyProblem` branch and
  needs no separate gate here.

### The plans boundary, the confinement guard and the other pins
- **Sources Consulted**: `.kiro/specs/training-blocks/design.md`
  (PackageBoundary, ConfinementRegistration, PlanEngine);
  `tests/test_confinement.py:540-611`; `tests/test_public_api.py:835-935`;
  `tests/test_contract_consumers.py:65-250`; `tests/test_layout.py:734-790`;
  `tests/load/threshold/test_boundary.py:255-300`; `pyproject.toml:60-92`.
- **Findings**: the confinement `EntryPoint` takes `prepare`, `run`,
  `non_vacuous(touched)`; `_wrote_the_history_document` is the template for
  a pass that writes no workout document. The layout form pin requires a
  literal `f"{PREFIX}/` token per rel-link helper. The threshold boundary
  test is an *allowlist over the threshold package's own imports*
  (`fitdocs.model`, `fitdocs.benchmarks`, `fitdocs.metrics.types`,
  `fitdocs.load.channels`, `fitdocs.load.types`); nothing this feature
  touches is on that list and the contract edit adds no import, so the
  reconciler cannot become reachable from it. `tests/test_public_api.py`
  pins `contract.__all__`, `history.__all__` and (after wave 1)
  `plans.__all__` by exact set with owners.
- **Implications**: every pin that moves is named in the File Structure
  Plan and owned by exactly one task; the threshold boundary test is
  preserved-only and stated as such.

### Where the reconciler's own report goes
- **Context**: `run_plan` returns `PlanReport`, whose `BlockOutcome.problems`
  exists only for `invalid` blocks; the resolver hook returns only a
  `Resolution`.
- **Findings**: the hook is called once per valid block, in order, after
  validation and before rendering. A callable object can record the
  per-block reconciliation it computed alongside the `Resolution` it
  returns.
- **Implications**: `run_reconcile` wraps `run_plan` with a `Reconciler`
  callable that records `BlockReconciliation`s keyed by block id, and
  returns `ReconcileReport(plan=..., blocks=..., methodology=...)`. The
  seam is consumed verbatim; nothing upstream is widened.

## Architecture Pattern Evaluation

| Option | Description | Strengths | Risks / Limitations | Notes |
|--------|-------------|-----------|---------------------|-------|
| Pure core, one I/O edge, one wrapper (chosen) | `corpus` reads; `matching`, `aggregate`, `placement` are pure; `reconcile` wires and wraps `run_plan` | Every rule mutation-testable without a filesystem; mirrors `training-blocks`' own shape | Five modules for one pass | The rules are the thing a reviewer must mutate row by row (roadmap, Boundary Strategy) |
| One `resolve.py` module | Scan + rules + text in one file | Fewer files | Rules and wording entangled; a wording golden reds on a rule change and vice versa | Rejected |
| Eager corpus scan before `run_plan` | Scan once, then run | Simplest control flow | Scans 2,478 pages on every `sync` even for an athlete with no plan directory | Rejected for the chained case; the scan is deferred to the first resolver call, which `run_plan` never makes when there is no source directory |
| Reconciler raises on a methodology problem (history's shape) | `MethodologyConfigurationError` → exit 2 | Consistent with `fitdocs history` | Would abort matching at the end of every `sync` for a config the athlete may not care about yet | Rejected: sums degrade to "not computed" with the reason (Req 6.6) |

## Design Decisions

### Decision: Add key constants and readers to the contract, and route every speller through them
- **Context**: the brief's "one reader per matched field" and the
  `FORBIDDEN_LITERALS` extension collide with two registered spellers.
- **Alternatives Considered**:
  1. Add only the readers, leave the literals out of the pin -- an inline
     `frontmatter.get("sport")` elsewhere stays uncaught (the exact gap the
     brief names).
  2. Exempt the emitter and `plans.page` from the literal scan -- a waiver
     that widens with every new speller.
  3. Constants + readers + route both spellers (chosen).
- **Selected Approach**: `DATE_KEY`, `START_TIME_KEY`, `SPORT_KEY`,
  `MODALITY_KEY`, `INDOOR_KEY` in `contract.py`; `MANAGED_KEYS` and
  `document_date` use them; `render/frontmatter.py` and `plans/page.py`
  import them; `FORBIDDEN_LITERALS` gains the five values;
  `CONTRACT_BINDINGS` gains the names for both modules.
- **Rationale**: the same pattern `UUID_KEY` and `SOURCES_KEY` already
  follow; the anti-drift test resolves names by design; the queue already
  asked for `DATE_KEY`.
- **Trade-offs**: touches one `workout-docs` module and one
  `training-blocks` module mechanically; no byte of any rendered page
  changes (pinned by the existing goldens).
- **Follow-up**: `history/documents.py`'s private `_read_load` is now a
  duplicate of `contract.document_load`; adopting the reader there is
  queued, not done here (the history package is out of boundary).

### Decision: Match on `(date, sport, modality?, indoor?)` and nothing else; three labels; connected competition groups
- **Context**: Req 2.7, 3.1-3.9; the roadmap's "no classifier".
- **Alternatives Considered**:
  1. Group competing rows by an exact type key -- misses partial overlaps
     (a `Workout` row and a `Workout (strength)` row both wanting one
     strength page).
  2. Rank candidates by duration/distance similarity -- a classifier.
  3. Competition groups as connected components of the row↔candidate graph
     per day; greedy assignment in (source order × start-time order) inside
     a group with more than one row (chosen).
- **Selected Approach**: per day, build each row's candidate set (after
  override stems are removed); rows whose candidate sets intersect,
  transitively, form a group; a one-row group is `exact` (one candidate) or
  `absorbed` (several); a multi-row group is assigned greedily and labelled
  `ambiguous` on every row that received a candidate; a row that received
  none is `not logged`/`upcoming` with the competition noted; leftover
  candidates are unplanned.
- **Rationale**: deterministic, needs no measure beyond date and type,
  degrades to a labelled proposal exactly where the athlete's word is
  needed.
- **Trade-offs**: the greedy proposal can pair the less specific row with
  the more specific page; that is the ambiguous case by construction and
  the page says so.

### Decision: Overrides are applied first, latest per row wins, missing stems are problems that fail the run but never the render
- **Context**: Req 4.1-4.4; upstream validates override *form and
  reference* only.
- **Selected Approach**: effective override per row = latest by `(date,
  source position)`; its stems leave every other row's candidate set; a
  stem absent from the corpus is rendered as `not found`, reported with the
  override entry's index (`override[i] (id r)`), and sets
  `ReconcileReport.failed` (exit 1) while the block still renders.
- **Rationale**: upstream's own rule is "a source problem exits 1"; the
  brief's rule is "never dropped". Rendering with the problem stated
  satisfies both, and a curating LLM running `fitdocs plan` sees the exit
  code.
- **Trade-offs**: a dangling stem keeps `sync` at exit 1 until the source is
  fixed -- the same behaviour a per-document load failure already has.

### Decision: Sum under history's methodology rule; degrade, never abort
- See "How `history` picks and applies the one methodology" above. The
  reconciler reads `[history]` and `[load]` eagerly (a malformed table is a
  configuration error before anything is written, as everywhere else) and
  selects lazily with the corpus. A `MethodologyProblem` is stated once and
  every sum reads "not computed".

### Decision: `today` never appears on a page
- **Context**: Req 5.2, 5.3; `training-blocks` 8.4.
- **Selected Approach**: the page states `upcoming` and `not logged`, never
  the date they were judged against.
- **Rationale**: a page that changes bytes every day is diff noise in a
  version-controlled wiki (the reason 8.4 exists); only a row crossing
  `today` should change a byte.

### Decision: No back-link key into logged pages
- **Context**: the roadmap's `workout-docs` Existing Spec Update is
  conditional on this design writing one.
- **Selected Approach**: none is written. The relation "this logged page
  fulfilled that planned row" is fully expressed by the links on the block
  page and the planned page, is re-derived on every run, and would need a
  managed key, a `MANAGED_KEYS` pin move and a contract-version advance to
  live on the workout page.
- **Consequence**: the roadmap's `workout-docs` entry closes as "no change".

### Decision: Reuse `history`'s helpers by widening their record type to a Protocol
- See the Key Findings. `MethodologyRecord` is published from
  `fitdocs.history` (append-only `__all__`), the two signatures widen, no
  existing caller changes.

## Risks & Mitigations
- **The wave-1 implementation may spell the four planned-page keys somewhere
  other than `plans/page.py`** (a renderer building `(key, value)` pairs).
  The literal scan covers only registered modules, so an unregistered
  speller is neither caught nor broken; the task that adds the literals
  routes any spelling it finds under `src/fitdocs/plans/` through `page.py`
  constants and says what it found.
- **A `SettingsError` raised inside the resolver would escape `run_plan`
  mid-run.** Mitigated by reading both settings tables *before* `run_plan`
  is called; the resolver itself has no code path that raises for a valid
  block (the corpus scan never raises; `select_methodology` returns a
  value).
- **Two blocks with overlapping bounds** each reconcile independently; a
  logged workout can be matched in both. Stated on the page-level rules,
  not prevented -- the plan source decides what overlaps.
- **Determinism across time zones**: start-time ordering compares aware
  datetimes (instants); a naive value is `None` and sorts last; the page
  prints `HH:MM` from the recorded local wall clock, never re-zoned.

## References
- `.kiro/specs/training-blocks/design.md` -- the seams, verbatim.
- `.kiro/specs/plan-resolution/brief.md` -- the discovery brief.
- `.kiro/steering/roadmap.md` § Phase 7 -- decisions, constraints, boundary
  strategy.
- `.kiro/steering/change-protocol.md` § Fixture Discrimination -- the gate
  every rule's named mutation answers to.
- `.kiro/queue/2026-07-26-date-key-has-no-constant.md` -- absorbed by
  task 1.1.
