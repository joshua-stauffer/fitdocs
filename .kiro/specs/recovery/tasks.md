# Implementation Plan

## Upstream Prerequisites

- **Base.** Planned at `cd77157` (chore/p12-spec-batch). Implementation
  starts only when `wellness-store` is on `main` (the `fitdocs.wellness`
  facade, `read_series`, the sanctioned series test builder
  `tests/wellness/builders_series.py`, `MetricInfo.label`, `wellness/`
  in `OWNED_PATHS`, the registered intervals.icu format). `chart-kit` and
  `chart-catalog` are on `main` (16 kinds). `dashboards` may be on `main`
  first: it takes a `CONTRACT_VERSION`, appends `dashboards/` to the owned
  and declared lists, adds the `dashboard` command (the command count and
  its spelled form move) and pins the `docs/dashboards.md` kinds block live
  against the registry. Every version constant and count in this plan is
  **main + 1 at landing**, re-derived in 6.2 after the final rebase; every
  list it touches is append-only and keeps both sides on rebase.
- **Verify before building on it** (1.2 records each outcome with file and
  line in Implementation Notes; stop and report on drift):
  - the wellness facade exports `Metric`, `METRICS`, `MetricInfo` (with
    `label`, controller ruling R1), `SeriesValue`, `WellnessSeries`
    (`values`, `is_empty`, `days`, `by_source`, `canonical`), `read_series`,
    `SeriesReadError`;
  - wellness-store's one sanctioned series test builder,
    `tests/wellness/builders_series.py::write_series(data_root, values:
    Iterable[SeriesValue], …)`, writing year files and the manifest through
    the real codec (controller ruling, 2026-10-12); recovery never imports
    `fitdocs.wellness.series` internals (1.2 records the builder's file,
    line and signature);
  - for 5.3 and 6.1: the intervals.icu delivery envelope (wellness-store
    design § Seams 2), its builder `tests/wellness/builders_intervals.py`
    (wellness-store task 2.1) and the format's registration (wellness-store
    task 3.1);
  - `fitdocs.history` exports `read_history_inputs`, `compute_history`,
    `HistoryComputation`, `day_rows`, `DayRow`,
    `MethodologyConfigurationError` (`history/__init__.py`);
  - the kit facade exports `ChartRequest`, `ChartData`, `Column`,
    `ValueKind`, `render_chart`, `describe_kinds` (whose `small-multiples`
    entry carries `bound["limit"]`), and `kit.format.format_value(value,
    column, *, with_unit)` exists.
- **Existing spec updates carried by this plan** (design § Existing Spec
  Amendments). Each is appended to the named spec's `requirements.md` as
  `## Amendment N (<date>): <title>, landed by recovery` by the task that
  makes the change, taking the next free number then: wiki-contract (1.6),
  chart-catalog (2.2, Amendment 1), connectors (5.3). `MetricInfo.label` is
  wellness-store's own (controller ruling R1); recovery only consumes it.
- **Citations need the network.** Task 1.1 is run by the session controller
  or the maintainer (who can open the works); implementer subagents have no
  web access and never run it. 1.2 waits for 1.1 whenever 1.1 can be done
  before implementation starts; otherwise 1.2 ships the design's
  `FitdocsChoice` fallbacks and 6.2 transcribes the late records. No value
  ever changes because of 1.1.

**Hard rules for every task**

- **Absent is `None`.** No recovery code substitutes zero, an empty string or
  a default for an absent value, a missing day, an absent rolling mean or an
  absent range; a chart row with an absent value draws nothing.
- **No clock, no machine timezone, no network** anywhere under
  `fitdocs.recovery` or in the new kind. No `date.today`, `datetime.now`,
  `time.*`, `astimezone()`, `urllib`, `socket`, `http`. 1.5 enforces it.
- **Imports follow design § Allowed Dependencies.** `constants` →
  `baselines` → package facade; `baselines` → `view` → `charts` → `page` →
  `engine`. The facade imports only `baselines` and `constants`; `view`
  imports `fitdocs.history` and nothing from the chart kit (the engine
  passes it the panel limit, controller ruling R2); only `fitdocs.cli`
  imports `fitdocs.recovery.engine`; no recovery module imports `duckdb`,
  `fitdocs.index`, `query`, `dashboards`, `sync`, `inbox`, `ingest`,
  `model`, `connectors`, `tiles`, `load`, `benchmarks`, `cli` or a
  `fitdocs.wellness` submodule.
- **Consume, never re-own.** Wellness values only through
  `fitdocs.wellness.read_series` and `WellnessSeries`; labels only through
  `METRICS[metric].label`; fitness, fatigue and form only through
  `read_history_inputs`, `compute_history` and `day_rows`; charts only
  through the kit facade. No second metric list, label table, unit list,
  precedence rule or day-boundary rule.
- **Synthetic data only.** A series written to a data root goes only
  through wellness-store's `write_series` — never a hand-written CSV, never
  `encode_year` or the manifest encoder directly. An in-memory series is
  `WellnessSeries(values=tuple(sorted(values)))` built from `SeriesValue`s
  (wellness-store's `(day, metric, source)` order, design.md:761, which
  `SeriesValue` sorts by). Workout pages are synthetic frontmatter
  documents. No maintainer value appears in the repository.
- **Writes only through `recovery.engine`**, atomically, never through a
  symlink, never outside `recovery/` and the declarations. No test writes
  outside its `tmp_path`.
- **Faking the date.** `date.today` cannot be monkeypatched; date and
  timezone changes in tests use the history precedent's in-process
  `time.time` fake and `TZ` switch (`tests/test_history_e2e.py:213`,
  `_fake_system_date`), copied locally.
- **Linux-CI portable.** `tmp_path` only; child processes get
  `{**os.environ, …}`; permission-based tests skip when running as root.
- **Mutations run through `uv run pytest` only** (`change-protocol.md` §
  Fixture Discrimination): each named mutation applied, observed red,
  reverted by restoring a `cp` taken before it, observed green, recorded in
  Implementation Notes; one that cannot be made red is reported UNPINNED.
  Before submitting, run the prose-claim grep over changed test files and
  re-run or delete every surviving claim.
- **Fixtures discriminate.** Pairwise-distinct values where a mapping is
  asserted; two sources whose values differ on every shared day; arithmetic
  and geometric means that differ; the interesting day not first; an
  asserted end state shown false beforehand; "nothing written" asserted on
  bytes *and* `st_mtime_ns`.
- **Parallel streams.** `(P)` tasks run in separate worktrees and touch only
  their `_Boundary_`. `tests/recovery/builders.py` is created by 1.3 and
  appended once by 3.1, then frozen.
- **Never run the CLI by hand while a full `uv run pytest` is in flight in
  the same worktree** (`tests/test_bytecode_hygiene.py`).
- **Shell safety.** Never `rm -rf`, `git init`, `git reset --hard`,
  `git clean` or `git checkout -- <path>`; never chain a destructive command
  after `cd`.
- **Types and lint.** Each task runs `uv run mypy`, `uv run ruff check` and
  `uv run ruff format --check`.
- **Stop and report** on any need for: a runtime dependency; an edit to a
  chart-kit or catalog shared layer (`schema`, `data`, `validate`, `frame`,
  `layout`, `scales`, `marks`, `cartesian`, `cells`, `theme`, `format`) or to
  another kind; an edit to `fitdocs.history`, `fitdocs.wellness`, `sync`,
  `index` or `dashboards`; any edit to `src/fitdocs/render/attribution.py`
  other than 3.3's append of the four settled wellness names; a write
  outside `recovery/` from a recovery path;
  changing a constant's value (1.1 changes records, never values).
- **User-approved exception (2026-10-16).** Task 2.3 may change only the
  three named chart kinds and their direct tests/affected goldens to repair
  present-x extent. All other shared-layer/kind boundaries remain in force.

## Shared source files

Each file below has more than one writer; its writers are sequential.

- `src/fitdocs/recovery/__init__.py`: 1.2 creates it docstring-only; 1.3
  adds the re-exports.
- `tests/recovery/builders.py`: 1.3 creates it (series builders); 3.1
  appends the workout-page builder; frozen afterwards.
- `tests/recovery/test_boundary.py`: 1.5 creates it (rank table over every
  design module, modules on disk checked). Tasks 3.1, 3.2, 3.3, 3.4 and 4.1
  re-pin only their own module's measured import-row literals when imports
  arrive, within design § Allowed Dependencies; the guard policies remain
  unchanged. 4.3 adds the literal module-set pin and switches the reverse
  check to equality.
- `src/fitdocs/recovery/constants.py`: 1.2; 6.2 only when 1.1's records
  arrive after 1.2.
- `src/fitdocs/render/charts/kit/registry.py`,
  `tests/render/charts/kit/test_boundary.py`: 2.1 only.
  `tests/render/charts/kit/test_catalog_budgets.py`,
  `tests/render/charts/kit/test_catalog_contract.py`: 2.2 only.
- `pyproject.toml`: 1.2 (`tests/recovery` mypy entry), 5.1
  (`[project.urls] Recovery`).
- `tests/test_confinement.py`: 1.6 (docstrings only, if any), then 6.1 (the
  `recovery` entry point and its registration tests).
- `tests/identity/test_contract_docs.py`: 1.6 (the literal history pin,
  numbers written as literals as `main` stands, and the head-paragraph
  re-pin), then 6.2 (the landed literals and every peer head-paragraph pin on `main`
  at landing).
- `CHANGELOG.md`: 5.2 only.

## Cross-spec shared files (append-only, keep both sides on rebase)

`OWNED_PATHS` / `DECLARED_DIRS`, `CONTRACT_VERSION` and every declaration
golden's version line, the kit `KINDS` registry, the `docs/dashboards.md`
kinds block, `WRITING_ENTRY_POINTS`, the CLI command count and its spelled
form (`tests/test_cli_skill.py:266, 268`, `tests/query/test_cli_query.py:811,
812`, `tests/index/test_cli_index.py:608`, the `src/fitdocs/cli.py:5`
docstring), the no-network command lists (`tech.md`, connectors Req 14.1,
`tests/connectors/test_e2e.py` parametrization), `[project.urls]`,
`[tool.mypy].files`, `CHANGELOG.md` Unreleased, `docs/index.md` rows and
`_REQUIRED_ENTRY_POINT_LINKS` (`tests/test_docs_guarantees.py:1111`),
`.kiro/steering/structure.md`, `tests/test_public_api.py`, the workouts skill
and `tests/test_agent_skill.py`, `src/fitdocs/render/attribution.py` and
`tests/render/test_attribution.py` (the four appended wellness names, 3.3;
`workout-wellness` consumes them and lands after recovery),
`tests/identity/test_contract_docs.py`'s version-history test (append-only
literal pins, one per lander) and every head-paragraph pin of
`docs/ownership-contract.md`.

## Test File Ownership

- `tests/recovery/__init__.py`, `test_constants.py`, `test_constant_guard.py`:
  **1.2**. `builders.py`, `test_baselines.py` (the `on()` half): **1.3**.
  `test_shown.py` (shown source, key, bound, timezone): **1.4**.
  `test_boundary.py` and the `_RECOVERY_SURFACE` / `_RECOVERY_SURFACE_OWNERS`
  pins in `tests/test_public_api.py`: **1.5** (4.3 closes the boundary
  guard).
- Import-row literals in `test_boundary.py`: the narrow companion re-pins
  described under Shared source files belong to the task creating or
  extending that row's module; no rank, forbidden-name, clock, network,
  reverse-import or facade policy changes accompany those re-pins.
- The literal history pin and the head-paragraph re-pins in
  `tests/identity/test_contract_docs.py`: **1.6**, finished by **6.2**.
- Golden `tests/declaration_golden/recovery.AGENTS.md` and the re-pins in
  `tests/test_layout.py`, `tests/test_declaration*.py`,
  `tests/test_ownership_contract.py`, `tests/identity/test_contract_docs.py`,
  `tests/index/test_contract_docs.py`, `tests/index/derived/test_preserved.py`,
  docstrings in `tests/test_confinement.py` and
  `tests/test_declaration_refresh.py` if any name the declared set: **1.6**.
- `tests/render/charts/kit/test_reference_band.py`, its goldens, the
  `test_boundary.py` re-pin, the registry line: **2.1**. Budget, listing and
  order pins: **2.2**.
- `tests/recovery/test_view.py`: **3.1**; `test_charts.py`: **3.2**;
  `test_page.py` and `golden/`: **3.3** (sections, the attribution line) and
  **3.4** (method, references, coverage, descriptive guard);
  `tests/render/test_attribution.py` (the appended wellness tests): **3.3**.
- `tests/recovery/test_engine.py`: **4.1**; `test_cli_recovery.py` and the
  command-count re-pins: **4.2**; the boundary guard's closing pins: **4.3**.
- `tests/recovery/test_docs_recovery.py`, the `_REQUIRED_ENTRY_POINT_LINKS`
  append: **5.1**; skill pins: **5.2**;
  `tests/connectors/test_network_statements.py`,
  `tests/connectors/test_e2e.py`: **5.3**.
- `tests/recovery/test_e2e_recovery.py`, the confinement entry point and its
  registration tests: **6.1**.

---

- [x] 1. Foundation: citations, constants, baselines, boundary, location

- [x] 1.1 Verify the candidate citations against the works themselves (controller or maintainer)
  - For each of the six works in design § Constants and research.md
    (Plews et al. 2013 *Sports Med*; Plews et al. 2013 *IJSPP*; Plews et al.
    2014 *IJSPP*; Buchheit 2014 *Front Physiol*; Vesterinen et al. 2016
    *MSSE*; Altini & Plews 2021 *Sensors*), open the work and record one of:
    **verified** (full reference, the locator — page, section, figure or
    equation — and the sentence or value it states), **attested only**
    (bibliographic data confirmed from a secondary source, primary text not
    obtained), or **not verified**.
  - For each constant (`ROLLING_DAYS` 7, `MIN_ROLLING_VALUES` 3,
    `BASELINE_DAYS` 60, `MIN_BASELINE_VALUES` 30, `RANGE_SD_MULTIPLE` 0.5)
    and each rule of design § Constants, record the resulting governing
    record: a `Citation` (verified only), a `FitdocsChoice` with its
    justification and search basis, any `Corroboration` (attested works, as
    `SECONDARY_ATTESTATION` with a note), and any `Departure` (a work that
    states a different value or applies the method to another signal).
  - A work that contradicts a value is reported to the maintainer; the value
    is not changed by this task.
  - Run by the session controller or the maintainer with web access; never
    dispatched to an implementer subagent. Nothing under `src/` or `tests/`
    changes.
  - **Observable:** Implementation Notes hold a table with one row per work
    (state, locator, what it states) and one row per constant and rule (the
    governing record and its fields), ready for 1.2 (or 6.2) to transcribe.
  - _Requirements: 11.2, 11.3, 11.4_

- [x] 1.2 Create the recovery package's constants and methods
  - Verify the Upstream Prerequisites list and record each outcome with file
    and line in Implementation Notes (stop and report on drift).
  - `src/fitdocs/recovery/__init__.py` (docstring only) and `constants.py`
    per design § Constants: `Transform`, `BaselineMethod`, `MethodRule`; the
    five `CitedConstant`s with the governing records 1.1 recorded (with no
    1.1 outcome yet, each source is the design's `FitdocsChoice` fallback and
    the Implementation Notes say so, for 6.2 to pick up); `RULES`;
    `BASELINED_METRICS`, `SLEEP_METRICS`; `METHODS` (HRV LOG with range,
    resting HR LINEAR with range, the six sleep metrics LINEAR without);
    `lookback_days(methods)` and `LOOKBACK_DAYS = lookback_days(METHODS)`;
    `BASELINES_VERSION = 1`.
  - `pyproject.toml`: append `tests/recovery` to `[tool.mypy].files`.
  - **Tests** (`tests/recovery/test_constants.py`): `METHODS` rows equal a
    test-local literal of design § Data Models (metric, transform, windows,
    minimums, range multiple); the record check — every `Citation` governing
    a constant or rule has `PRIMARY_TEXT` and a non-`None` locator — runs
    over the real records and rejects a synthetic `Citation` without a
    locator (positive control); every `FitdocsChoice` has a non-empty
    justification and search basis; `LOOKBACK_DAYS == 60` and
    `lookback_days` of a synthetic table with `rolling_days=70` is 69;
    `CONSTANTS` and `RULES` keys unique.
  - **Tests** (`tests/recovery/test_constant_guard.py`, history's literal
    scan adapted): the guard names `constants.py` and `baselines.py` and
    scans whichever exist (`assert scanned`); no numeric literal outside
    `constants.py`'s `CitedConstant` constructors, other than the exempted
    identities; a synthetic module holding `0.5` is caught (positive
    control). `view.py`'s `WINDOW_DAYS` is a display choice and is not
    scanned (design § View).
  - **Mutations:** HRV to `LINEAR` in `METHODS` (literal pin reds);
    `range_multiple` on `sleep_s` (reds); a bare `0.5` in `METHODS` in place
    of `RANGE_SD_MULTIPLE.value` (the guard reds); drop `rolling_days − 1`
    from `lookback_days` (the synthetic-table pin reds); the record check
    skipping the locator test (the positive control reds).
  - **Observable:** `from fitdocs.recovery.constants import METHODS` lists
    nine metrics; `uv run pytest tests/recovery` green.
  - _Depends: 1.1 (records only; values never wait)_
  - _Requirements: 3.3, 3.4, 3.5, 3.6, 3.7, 11.1, 11.2, 11.3, 11.4_

- [x] 1.3 Compute one source's rolling mean, baseline, range and position, and publish the facade
  - `baselines.py` per design § Baselines: `RangePosition`, `BaselineDay`,
    `Baselines.of` and `Baselines.on`; `math.fsum` and `math.sqrt` only.
    The facade re-exports every design name (`shown_source` and `shown`
    arrive in 1.4, as methods of `Baselines`).
  - `tests/recovery/builders.py`: synthetic `SeriesValue` sets per
    (metric, source, day), each stating its canonical flag explicitly
    (exactly one canonical value per metric-day that has values); the
    in-memory `WellnessSeries` helper; and a data-root helper that only
    calls wellness-store's `write_series` (no recovery-side writer).
  - **Tests** (`tests/recovery/test_baselines.py`): the rolling window
    includes D (changing D's value changes the mean) and starts at D−6 (a
    value at D−7 does not); the baseline excludes D (changing D's value
    leaves mean, SD and range unchanged) and reaches D−60 but not D−61;
    minimums at 2 vs 3 and 29 vs 30 present days; the HRV mean is geometric
    (a fixture whose arithmetic and geometric means differ) and the range is
    asymmetric in ms; sample SD (n − 1) at n = 30; position below, within and
    above, and bounds inclusive with a resting-HR rolling mean exactly on a
    bound (linear scale, an exact float tie: 31 baseline values, one at μ,
    15 at μ+2 and 15 at μ−2, give a sample SD of exactly 2 and a lower bound
    of exactly μ−1; three integer rolling values averaging μ−1 tie exactly);
    position `None` when the
    rolling mean or the range is absent; two sources with pairwise-distinct
    values never mix; SDNN and rMSSD never mix; a gap day is never zero.
  - **Mutations:** rolling window `D−7…D−1`; baseline `D−59…D`; `>=` → `>` on
    each minimum; LOG → LINEAR; `n − 1` → `n`; `<` → `<=` on the lower bound;
    index the value map by metric only; fill a gap day with 0; a bare `0.5`
    in `baselines.py` in place of `METHODS[...].range_multiple` (1.2's
    constant guard reds).
  - **Observable:** `uv run pytest tests/recovery/test_baselines.py` green
    with every mutation recorded red.
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.8, 3.10, 4.4, 5.3, 15.1_

- [x] 1.4 Choose the shown source and bound what a late value can change
  - `baselines.py`: `Baselines.shown_source` and `Baselines.shown` per
    design § Baselines.
  - **Tests** (`tests/recovery/test_shown.py`): the shown source is the
    day's canonical source; it is carried across a 6-day gap and not a 7-day
    one; `shown` equals `on` for the shown source; a value at day X changes
    the result of day X + 60 and not X + 61; results are equal under two
    `TZ` values and two faked system dates (the history precedent's
    `time.time` fake, in-process).
  - **Mutations:** carry 7 days; pick the first rather than the latest
    canonical day in the carry window; shorten the dependency window so a
    value at X stops reaching X + 60.
  - **Observable:** `uv run pytest tests/recovery/test_shown.py` green; the
    facade lists every name of design § Facade.
  - _Requirements: 3.9, 3.10, 5.1, 5.2, 15.1, 15.2_

- [x] 1.5 Guard the recovery package's imports, clock, network and public surface
  - `tests/recovery/test_boundary.py` (the wellness-store 1.4 and history
    patterns): a rank table naming every design module (`constants`,
    `baselines`, the facade, `view`, `charts`, `page`, `engine`) with its
    allowed imports per design § Allowed Dependencies (`view`: `history`
    only, no kit; `engine`: the kit facade for `describe_kinds`); each module
    **on disk** checked by equality against its row; a module on disk the
    table does not name fails; positive control: the visited set equals a
    glob of `src/fitdocs/recovery/**/*.py` and is non-empty. A
    forbidden-name scan; a clock scan; a network scan; the reverse half at
    this stage is "importers of `fitdocs.recovery.engine` outside the
    package ⊆ {`fitdocs.cli`}" with `assert scanned` and a synthetic
    outside importer that must be caught (4.3 makes it equality).
  - The facade check, in a fresh interpreter: the modules `import
    fitdocs.recovery` loads, minus those `import fitdocs.wellness` loads, are
    a subset of {`fitdocs.recovery`, `fitdocs.recovery.constants`,
    `fitdocs.recovery.baselines`, `fitdocs.citation`}, and none is under
    `fitdocs.render`, `fitdocs.history` or is `fitdocs.recovery.engine`.
  - `tests/test_public_api.py`: `_RECOVERY_SURFACE` as a literal set and
    `_RECOVERY_SURFACE_OWNERS` naming the defining submodule of each name,
    with the identity check (the history precedent,
    `tests/test_public_api.py:912-960`).
  - **Mutations:** add `import fitdocs.history` to `baselines.py` (equality
    and facade checks red); `datetime.date.today()` in `baselines.py`
    (clock scan reds); drop a name from `__all__` (surface pin reds); re-bind a facade name to a copy (owners identity reds).
  - **Observable:** the guard and surface tests green, each layer with a
    positive control that fails on synthetic input.
  - _Requirements: 1.3, 15.1, 17.3, 17.4_

- [x] 1.6 (P) Declare `recovery/`, its AGENTS.md and the next contract version (wiki-contract amendment)
  - `layout.py`: `RECOVERY_DIR`, `RECOVERY_ASSETS_SUBDIR`,
    `RECOVERY_DOC_STEM`, `recovery_doc_path`, `recovery_asset_path`,
    `recovery_asset_rel_path`; `OWNED_PATHS` += `recovery/`,
    `recovery/assets/`; `DECLARED_DIRS` += `recovery/` (after main's
    entries).
  - `declaration.py`: `_RECOVERY_CONTENT`, `_RECOVERY_RERUNNABLE` (CLAIM
    ANCHOR comments) and the branch, heading "Generated Recovery Page";
    golden `tests/declaration_golden/recovery.AGENTS.md`.
  - `contract.py`: `CONTRACT_VERSION` main + 1 with the design's history
    paragraph. `docs/ownership-contract.md`: version, "What changed", owned
    bullets, declared-directory count, the "Recovery Page" section.
  - `tests/identity/test_contract_docs.py`: append to
    `test_the_version_history_records_the_amendment` a LITERAL pin
    `"Raised from ``N`` to ``N+1`` by recovery"` with the numbers written as
    literals (never derived from the live `CONTRACT_VERSION`; 6.2 rewrites
    them to the landed values); re-pin the head-paragraph test (`:177-187`)
    to recovery's "What changed" phrases, and re-pin every other
    head-paragraph pin on `main` (found by grepping the outgoing paragraph's
    phrases across `tests/`).
  - Re-pins named in Test File Ownership (append-only where a list); every
    existing declaration golden regenerated for the version line only;
    `tests/test_confinement.py` and `tests/test_declaration_refresh.py`
    docstrings only, if any name the declared set.
  - Append `## Amendment N` to `.kiro/specs/wiki-contract/requirements.md`, a
    dated paragraph to its `design.md`, a `spec.json` entry.
  - **Tests:** helpers return the design's paths; the owned and declared
    tuples end with the new entries; the golden equals
    `declaration_text("recovery/")`; `ensure_declarations` places
    `recovery/AGENTS.md`; `check` reports a missing one.
  - **Mutations:** drop `recovery/assets/` from `OWNED_PATHS`
    (`test_ownership_contract` reds); misspell the heading (golden reds);
    leave `CONTRACT_VERSION` unchanged (the preserved pin and the doc's
    version line red); change "by recovery" in the history paragraph (the
    literal history pin reds); keep the outgoing "What changed" paragraph
    (the head-paragraph pin reds).
  - **Observable:** `uv run pytest tests/test_layout.py tests/test_declaration*.py
    tests/test_ownership_contract.py tests/test_confinement.py
    tests/test_declaration_refresh.py tests/index tests/identity` green with
    the new version.
  - _Requirements: 12.1, 12.3, 13.1, 13.2, 13.3, 18.2_
  - _Boundary: OwnedLocation_

- [x] 2. The `reference-band` chart kind and chart-axis compatibility (chart-catalog Amendment 1)

- [x] 2.1 (P) Draw values as points against a segmented reference band, with flagged rows marked, and register the kind
  - `src/fitdocs/render/charts/kit/kinds/reference_band.py` per design §
    ReferenceBandKind and chart-catalog's Common rules: channels, options,
    bound (1000 rows), `max_series=8`, `_validate`, `_check`, `_draw`,
    legend, undrawn counts, description; built only from existing shared
    functions (`band_path`, `line_series`, `shape_path`, `gap_segments`,
    `numeric_scale`, `frame.*`).
  - `kit/registry.py`: append `reference_band.KIND` after the last
    registered kind (one line, controller ruling R3). When `dashboards` is on
    `main`, regenerate the `docs/dashboards.md` kinds block
    (`uv run python -m tests.dashboards.test_docs_dashboards`); otherwise
    record that its own landing regenerates it.
  - `tests/render/charts/kit/test_reference_band.py` with `CASES`
    (`typical` first: two segments, band, mid, flags; the standard classes
    `empty`, `all_absent`, `long_labels`, `single`, `negative`, `at_bound`;
    kind-local `no_band`, `absent_segment`, `segment_switch`, `lone_edges`)
    and goldens under `golden/reference-band/` written only by its `main()`.
    Problem tests written before the registry line call
    `validate.validate_request(request, columns, KIND, registry.kind_names())`
    (chart-catalog ruling (c)).
  - `tests/render/charts/kit/test_boundary.py`: the module tuple gains the
    kind module at the kinds rank.
  - **Tests:** problems for one bound edge, mixed units, low above high, a
    duplicate x and nine segments; a switch from segment A to B on adjacent
    rows draws two band paths and two centre-line paths (no path spans the
    switch); a flagged row draws one marker and an unflagged or absent-flag
    row none; the `—` segment orders last and draws no legend entry when it
    has no mark; absent values never drawn as zero; legend names points,
    band, centre line and flag with their own swatches.
  - **Mutations:** join runs across a segment change; draw the band through
    an absent low; treat an absent flag as true; order `—` first; drop the
    `missing_channel` check; `value_order` with `>=`.
  - **Observable:** `kind_names()` ends with `reference-band`; `uv run pytest
    tests/render/charts` (and `tests/dashboards` when present) green; every
    golden reddened by at least one named mutation.
  - _Requirements: 4.1, 5.4, 16.2, 16.3, 16.4, 18.5_
  - _Boundary: ReferenceBandKind_

- [x] 2.2 Pin the kind's listing, order and budget and record chart-catalog Amendment 1
  - `test_catalog_contract.py`: a literal listing pin for `reference-band`
    (as `dual-axis`'s) and the registered order's tail.
  - `test_catalog_budgets.py`: a 90-row fixture (band, mid, two segments,
    flags), budget measured + 25 %; the `at_bound` golden under chart-kit's
    80,000-byte ceiling (exceeding it is a stop-and-report).
  - Append `## Amendment 1` (design's ten criteria) to
    `.kiro/specs/chart-catalog/requirements.md`, a dated paragraph to its
    `design.md` § Kinds, a `spec.json` entry.
  - **Mutations:** register before `table` (the order pin reds); drop the
    `flag` channel (the listing pin reds); one `<circle>` per point instead
    of a shared path (the budget reds).
  - **Observable:** `uv run pytest tests/render/charts` green with the new
    pins.
  - _Depends: 2.1_
  - _Requirements: 16.3, 16.4_

- [x] 2.3 Preserve the present-x extent when endpoint values are absent (user-approved prerequisite)
  - User approved the fresh-debug proposal on 2026-10-16: "yes, please fix
    it and continue". This prerequisite resolves the task 3.2 scope conflict.
  - For line, small-multiples and reference-band, when a genuine mark is
    drawable, use every received present x position for the x domain and
    accessible x extrema, including rows with no drawable value. Keep
    drawable-only y inputs, all original values/None, marks, source legends,
    gaps, counts, bounds, validation and all-markless no-data behavior.
    Small-multiples keeps one global x scale across all panels.
  - Reference-band's flags-only path separates true flag entries from
    domain-only positions; expanding the domain must not fabricate flags.
  - Public-render tests check independently specified x extrema AND mark
    geometry for missing first/last/both endpoints, unsorted rows, all four
    allowed x kinds (including zero/negative linear x), x-absent decoys,
    separate y ranges/notes/marks, both small-multiples y modes and an empty
    panel anchoring the global domain, reference-band value/band/mid/flag
    modes, and original no-data/gap/validation behavior. Apply independent
    domain-only, description-only, truthiness, per-panel-domain, false-flag
    and no-data mutations; every new/changed assertion needs direct evidence.
  - _Boundary:_ only `src/fitdocs/render/charts/kit/kinds/line.py`,
    `small_multiples.py`, `reference_band.py`; their corresponding existing
    three `tests/render/charts/kit/test_*.py` modules; directly affected
    goldens regenerated solely by sanctioned writers (line typical expected).
    No shared kit layer/schema/options/registry/budget/other kind edits.
    Preserve all prior test cases; change only assertions genuinely made
    obsolete by the approved wider x extent. The three task 3.2 draft paths
    are frozen during this prerequisite; actual recovery-axis tests belong
    to the resumed 3.2. Parent owns this plan/design/spec metadata.
  - **Observable:** targeted kind tests and full chart/recovery scope pass;
    original draft values remain unchanged; fresh independent review and
    completion gate precede acceptance.
  - _Depends: 2.1, 2.2_
  - _Requirements: 2.2_

- [x] 3. The page model and its rendering

- [x] 3.1 Build the page model from the series, the baselines and the history computation
  - `view.py` per design § View: `WINDOW_DAYS`, `OTHER_SIGNALS`, the view
    types and `build_view(series, baselines, load, *, panel_limit)`;
    nothing from `fitdocs.render` (controller ruling R2); `RecoveryView.origins`
    collected per design § View "Origins" (the page, not the view, decides
    the attribution).
  - `tests/recovery/builders.py` (append, then frozen): synthetic workout
    pages with date, load and methodology frontmatter under a data root, so a
    test obtains a real `HistoryComputation` through `read_history_inputs`
    and `compute_history`.
  - **Tests** (`tests/recovery/test_view.py`): as-of is the series' last day
    (equal views under two faked system dates, the `time.time` precedent);
    window 90 days; a signal section only with a value in the window and
    `absent` otherwise; runs split by direction and by source; source changes
    and source notes with origins; `latest`; sleep rows only for stages the
    source records that night; other-signal panels in metric then source-id
    order, each holding only its own source's values; with 13 qualifying
    pairs and `panel_limit=12` the thirteenth is overflow, and with
    `panel_limit=3` the fourth is (the argument, not a literal, cuts);
    coverage counts; load rows mapped onto the window with days past the
    series end `None`, a suppressed week counted in `unavailable_days`, and
    `note` set when no page records a load; `origins` (design § View
    "Origins", only windows whose figure formed) includes a `garmin` value
    read only by the range (day D − 60 of a shown day D whose baseline
    formed) and excludes one at D − 61; with an unformed baseline (29 of 60
    days) the same D − 60 value is excluded, and with an unformed rolling
    mean (2 of 7 days) a value at D − 3 is excluded while D's own shown value
    is still included; `None` is included for an unrecorded origin; a
    charted panel's origins are included and an overflow pair's are not.
  - **Mutations:** as-of from the first day; origins over D − 59 … D only;
    count the baseline window when the baseline did not form (the
    unformed-baseline case reds); count the rolling window when the rolling
    mean did not form (the unformed-rolling case reds); origins dropping
    `None`; origins including overflow pairs; runs ignoring the source;
    panels holding the canonical value instead of the source's own; the cut
    at `panel_limit + 1`; load rows not offset by the window start; add a
    `fitdocs.render.charts.kit` import to `view.py` (1.5's rank row for
    `view` reds).
  - **Observable:** `uv run pytest tests/recovery/test_view.py` green.
  - _Depends: 1.4_
  - Companion boundary pin: re-pin only `view`'s measured import row in
    `tests/recovery/test_boundary.py` if its imports differ from the
    anticipated row, preserving design § Allowed Dependencies and all guard
    policies. This keeps every module on disk checked by exact equality.
  - _Requirements: 2.1, 2.2, 4.2, 4.3, 5.5, 5.6, 6.1, 6.3, 7.2, 7.3, 8.1, 8.2, 8.3, 8.4, 9.1, 9.5, 9.6, 12.5, 12.7, 12.8_

- [x] 3.2 Draw every section's chart through the kit
  - `charts.py` per design § Charts: `CHART_NAMES`, one request and one row
    per window day per chart, `render_charts(view)` in `CHART_NAMES` order;
    column labels from `METRICS[metric].label`.
  - **Tests** (`tests/recovery/test_charts.py`): each chart's kind, channels,
    options and column units equal the design table; every chart has the
    window's first and last day as rows; `outside` true exactly on `ABOVE`
    and `BELOW`; segment values are the shown sources; no chart for a missing
    section; SDNN and rMSSD never share a chart; every SVG comes from
    `render_chart` (the kit's theme style element present, no colour literal
    in `charts.py`).
  - **Mutations:** flag `WITHIN` days; drop the segment channel (a source
    switch draws one joined band); omit absent-value rows (the x extent
    shrinks).
  - **Observable:** `uv run pytest tests/recovery/test_charts.py` green.
  - _Depends: 2.1, 2.3_
  - Companion boundary pin: re-pin only `charts`'s measured import row in
    `tests/recovery/test_boundary.py` if its imports differ from the
    anticipated row, preserving design § Allowed Dependencies and all guard
    policies. This keeps every module on disk checked by exact equality.
  - _Requirements: 2.2, 4.1, 5.4, 6.2, 6.4, 7.1, 8.1, 9.1, 12.6, 16.1_

- [x] 3.3 Write the page's frontmatter, its attribution line and its signal, sleep, other-signal and load sections
  - `src/fitdocs/render/attribution.py` (append-only, after the existing
    workout-page names; nothing existing changes): `GARMIN_ORIGIN`,
    `WellnessAttribution`, `wellness_attribution`,
    `wellness_attribution_line` exactly as design § AttributionNames (the
    names settled at the Phase 12 cross-spec review), importing only the
    standard library. Tests appended to `tests/render/test_attribution.py`:
    `{"garmin"}` → SOLE; `{"garmin", "apple"}` and `{"garmin", None}` →
    CONTRIBUTING; `{"apple"}`, `{None}` and an empty iterable → NONE; the
    exact lines "Data source: Garmin" and "Data sources: Garmin and other
    sources", and `None` for NONE; the existing workout-page tests
    unchanged.
  - `page.py` per design § Page: `RECOVERY_TYPE`, `RECOVERY_TITLE`,
    `RECOVERY_VERSION`, `RECOVERY_FRONTMATTER_KEYS`, the plain-line
    frontmatter, `DOC_BANNER`, the title, the opening paragraph and the
    load, signal, sleep and other-signal sections with their fixed sentences;
    every number through `kit.format.format_value` on the chart's column;
    headings and rows from `METRICS[metric].label`; chart links through
    `layout.recovery_asset_rel_path`; the attribution line
    `wellness_attribution_line(wellness_attribution(view.origins))` directly
    beneath `# Recovery` when not `None`; no stamp in any chart image (an
    Open Question for the maintainer, design § Open Questions).
  - **Tests** (`tests/recovery/test_page.py`, part 1): section order; each
    fixed sentence and each "not shown" form with its counts; runs and
    source changes worded as designed; frontmatter keys in order,
    `methodology` omitted without load; `RECOVERY_TYPE` differs from the
    workout and history types; each number equals `format_value` of the
    chart column; relative chart links; the attribution line is the line
    right after `# Recovery` for SOLE and CONTRIBUTING views and absent for a
    NONE view (asserted false on that fixture first); a byte golden for one
    synthetic view with a Garmin origin (written only by the module's
    `main()`).
  - **Mutations:** print the arithmetic HRV mean; drop the "not shown"
    branch; swap `above` and `below`; emit `methodology` when no load; in
    `wellness_attribution`, ignore `None` origins (the `{"garmin", None}`
    case reds), return SOLE whenever `garmin` is present (the CONTRIBUTING
    case reds), return CONTRIBUTING for an origin set without `garmin` (the
    NONE case reds); change the CONTRIBUTING text (the exact-line pin reds);
    print the line after the opening paragraph (the position pin reds).
  - **Observable:** `uv run pytest tests/recovery/test_page.py` green.
  - _Depends: 1.6, 3.2_
  - Companion boundary pin: re-pin only `page`'s measured import row in
    `tests/recovery/test_boundary.py` if its imports differ from the
    anticipated row, preserving design § Allowed Dependencies and all guard
    policies. This keeps every module on disk checked by exact equality.
  - _Requirements: 2.3, 4.2, 4.3, 5.5, 5.6, 6.1, 6.3, 7.2, 8.3, 8.4, 9.5, 9.6, 9.7, 12.1, 12.2, 12.3, 12.4, 12.7, 12.8_

- [x] 3.4 Write the coverage, method and references sections and keep the page descriptive
  - `page.py`: the coverage table and the "No value in this window" line;
    the method section generated from `CONSTANTS` and `RULES` (citation,
    choice, corroborator and departure wording); the references list;
    `_FORBIDDEN_PHRASE_PATTERN`.
  - **Tests** (`tests/recovery/test_page.py`, part 2): the method section
    names every constant with its value and every rule; a `Citation`, a
    `FitdocsChoice`, a corroborator and a departure each render as designed
    (with synthetic records); references list each citation once in key
    order; the coverage rows equal the view; the forbidden pattern matches
    each forbidden word in a synthetic string (positive control) and never
    matches a rendered page over three fixtures (with load, without load,
    with a source change); no two signals are combined into one value (each
    number on the page traces to one `BaselineDay` field).
  - **Mutations:** omit one rule from the method section; list a citation
    twice; render a `FitdocsChoice` as a citation; add "recommended" to a
    fixed sentence (the guard reds).
  - **Observable:** `uv run pytest tests/recovery/test_page.py` green and the
    golden regenerated by its `main()`.
  - Companion boundary pin: re-pin only `page`'s measured import row in
    `tests/recovery/test_boundary.py` if its imports differ from the
    anticipated row, preserving design § Allowed Dependencies and all guard
    policies. This keeps every module on disk checked by exact equality.
  - _Requirements: 10.1, 10.2, 10.3, 11.1, 11.2, 11.3, 11.4, 11.5, 12.5_

- [x] 4. The run, the command and the closed boundary

- [x] 4.1 Read, compute, write and report a recovery run
  - `engine.py` per design § Engine: `FileOutcome`, `FileResult`,
    `RecoveryReport`, `run_recovery`; the series read first; history settings
    and methodology errors raised before any write; the panel limit read
    from `describe_kinds()`'s `small-multiples` entry and passed to
    `build_view`; the location check; the declaration refresh; charts then
    page, each only when the bytes differ; the generated SVG marker line;
    stale-chart removal limited to `CHART_NAMES`; a module-local atomic
    write (`.recovery-*.tmp`).
  - **Tests** (`tests/recovery/test_engine.py`): a staged root writes the page
    and the charts of its sections and places `recovery/AGENTS.md`; a second
    run reports every file `UNCHANGED` with bytes and `st_mtime_ns`
    unchanged; adding one wellness day rewrites only changed files; a section
    disappearing removes its chart; a foreign page, a foreign chart and a
    symlinked `recovery/` are `FOREIGN` and untouched; a read-only `assets/`
    fails the chart and skips the page (`failed` true); an unreadable series
    (made unreadable after `write_series` by corrupting one listed year
    file) fails with the remedy and writes nothing; an empty series writes nothing
    and leaves an existing page byte-identical; a malformed `[history]` and
    an unresolvable methodology raise `SettingsError` with nothing written;
    the load rows equal `day_rows(compute_history(...))` for the window, with
    and without an explicit methodology; a 13-pair other-signal fixture names
    the thirteenth in the overflow sentence, and with `describe_kinds`
    monkeypatched in the engine module to report a `small-multiples` limit
    of 3, a 4-pair fixture names the fourth (the listing's limit, not a
    literal, reaches the view); nothing outside `recovery/` and the declarations changes (a
    snapshot of the root).
  - **Mutations:** always write (the second-run pin reds); skip the foreign
    check on charts; remove every `*.svg` in `assets/`; read history before
    the series (the empty-series test sees a settings error); write the page
    after a failed chart; pass a literal 13 as the panel limit; hard-code 12
    as the panel limit (the monkeypatched-listing test reds).
  - **Observable:** `uv run pytest tests/recovery/test_engine.py` green.
  - _Depends: 3.4, 1.6_
  - Companion boundary pin: re-pin only `engine`'s measured import row in
    `tests/recovery/test_boundary.py` if its imports differ from the
    anticipated row, preserving design § Allowed Dependencies and all guard
    policies. This keeps every module on disk checked by exact equality.
  - _Requirements: 1.1, 1.3, 1.4, 1.5, 1.6, 1.7, 9.2, 9.3, 9.4, 13.4, 13.5, 13.6, 14.1, 14.3_

- [x] 4.2 Add the `fitdocs recovery` command
  - `cli.py`: `recovery_command` (`--out`, `--methodology`), the
    configuration exit on `SettingsError`, `_report_recovery`,
    `_finish(failed=report.failed)`; the module docstring's command list,
    exit codes and spelled command count (`cli.py:5`, main + 1, for example
    "Fifteen" when dashboards landed first); the summary line a plain
    sentence.
  - Command-count pins re-derived as main + 1: `tests/test_cli_skill.py:266`
    and `:268`, `tests/query/test_cli_query.py:811` and `:812`,
    `tests/index/test_cli_index.py:608`.
  - **Tests** (`tests/recovery/test_cli_recovery.py`): exit 0 with report rows
    on a staged root; exit 1 on an unreadable series; exit 2 on an
    unresolvable data root and on an ambiguous methodology (nothing written);
    `--methodology` reaches the engine; `run_recovery` is referenced only in
    `recovery_command` (an AST pin over `cli.py`, with a positive control);
    `fitdocs sync`, `regen`, `load` and `history` on a staged root write no
    `recovery/recovery.md`.
  - **Mutations:** map `SettingsError` to exit 1; call `run_recovery` from
    `history_command`; drop `--methodology` forwarding; leave the spelled
    count unchanged (the three spelled pins red).
  - **Observable:** `uv run fitdocs recovery --out <tmp root>` prints the
    report and exits 0 on a staged root.
  - _Requirements: 1.2, 1.6, 1.7, 1.8, 9.3, 9.4_

- [x] 4.3 Close the boundary guard now that every module exists
  - `tests/recovery/test_boundary.py`: a literal pin of the package's module
    set (every design module present, nothing else), and the reverse check
    switched to equality: the importers of `fitdocs.recovery.engine` outside
    the package are exactly {`fitdocs.cli`}.
  - **Mutations:** import `fitdocs.recovery.engine` from `src/fitdocs/sync.py`
    (the equality check reds); remove the import from `cli.py` (equality reds
    the other way); add an empty `recovery/extra.py` (the module-set pin
    reds).
  - **Observable:** `uv run pytest tests/recovery/test_boundary.py` green with
    both new pins shown red by their mutations.
  - _Depends: 4.2_
  - _Requirements: 1.3, 1.8, 15.1_

- [x] 5. Documentation, the skill, and the network statements

- [x] 5.1 (P) Write the recovery guide and link it
  - `docs/recovery.md` per design § Docs; `docs/index.md` row and
    `recovery.md` appended to `_REQUIRED_ENTRY_POINT_LINKS`
    (`tests/test_docs_guarantees.py:1111`, as dashboards 7.2 does);
    `[project.urls] Recovery`; README ownership summary gains `recovery/`
    and `recovery/assets/`, and one sentence on `fitdocs recovery` under
    "Show training history".
  - **Tests** (`tests/recovery/test_docs_recovery.py`): the guide names the
    command, each page section, each constant with the value `METHODS`
    holds (read live), the shown-source rule, the Garmin attribution line
    beneath the title (and that chart images carry none) and the
    `reference-band` kind; the index row and the URL resolve to the file.
  - **Mutations:** change a constant's value in the guide (the live pin
    reds); drop the index row (the entry-point pin reds).
  - **Observable:** the docs tests, `tests/test_docs_guarantees.py` and
    `tests/test_packaging.py` green.
  - _Depends: 4.2_
  - _Requirements: 12.7, 18.1_
  - _Boundary: Docs_

- [x] 5.2 Teach the workouts skill when to run recovery and record the release
  - The workouts skill: after the `fitdocs regen` block in "Commands to
    run", the design's paragraph and a fence holding exactly `fitdocs
    recovery`; it may link `docs/recovery.md` by its documentation URL
    (5.1 declared it in `[project.urls]`); `tests/test_agent_skill.py` pins
    re-derived (the routine fence unchanged, the new fence's command bound
    to the CLI).
  - `.kiro/steering/structure.md`: the `recovery` dependency sentence of
    design § NoNetworkLists and ConfinementEntry (it names `wellness`,
    `history`, `citation`, `contract`, `layout`, `declaration`, `units`, the
    chart kit facade and the render layer's attribution helpers).
  - `CHANGELOG.md` `[Unreleased]`: Added (the command and page; the
    `reference-band` kind), Changed (the ownership contract version and the
    new owned location, with the action).
  - **Mutations:** put `fitdocs recovery` in the routine fence (the routine
    pin reds); name a nonexistent option in the new fence (the binding pin
    reds).
  - **Observable:** `uv run pytest tests/test_agent_skill.py
    tests/test_packaging.py` green.
  - _Depends: 4.2, 5.1_
  - _Requirements: 18.3, 18.4_

- [x] 5.3 (P) Name `recovery` among the commands that make no connector request (connectors amendment)
  - `.kiro/steering/tech.md`: `recovery` before `check`, giving the final
    order with dashboards "`sync`, `regen`, `load`, `dashboard`, `recovery`,
    `check`, `query`, `history`, `plan`, `derive-benchmarks`, `index`" (the
    tail pins `tests/connectors/test_network_statements.py:667-670` and
    `tests/query/test_changelog_entry.py:143-146` stay green unedited);
    `tests/connectors/test_network_statements.py`: a new pin covering
    `recovery`, and, when dashboards is on `main`, its pin of "`load`,
    `dashboard`, `check`" re-pinned to "`load`, `dashboard`, `recovery`,
    `check`, `query`, `history`".
  - `tests/connectors/test_e2e.py`: the parametrization ends `…,
    ("query", …), ("dashboard", ["refresh"]), ("recovery", [])` (without
    the dashboard row while dashboards is not on `main`), and the module
    docstring's command list names `recovery`. Only this case stages wellness: the shared staging
    helper `_fresh_synced_root` (`:288-316`, which runs `sync <source>` and
    so never drains the inbox, `cli.py:682-685`) gains a keyword, off by
    default, that afterwards writes a synthetic intervals.icu delivery
    (wellness-store design § Seams 2, built with
    `tests/wellness/builders_intervals.py`; the format is registered by
    wellness-store 3.1) into `<root>/inbox/` and runs `fitdocs sync --out
    <root>` with no source, for both roots (with and without connectors), so
    the existing comparison still holds and the other cases are
    unchanged; the case asserts `read_series(root).values` is non-empty
    before the run and that the page was written under the socket guard.
  - Append `## Amendment N` (Req 14.1 adds `recovery`) to
    `.kiro/specs/connectors/requirements.md` and a `spec.json` entry.
  - If recovery lands BEFORE dashboards, the landing session logs a
    `TOUCHING` line in the agent log telling impl-dashboards to insert
    `dashboard` before `recovery` (in `tech.md` and in its own pin) and to
    keep the `("recovery", [])` row last.
  - **Mutations:** drop `recovery` from `tech.md` (the new pin reds); stage
    an empty series for the recovery case (the non-empty precondition reds).
  - **Observable:** `uv run pytest tests/connectors/test_network_statements.py
    tests/connectors/test_e2e.py` green.
  - _Depends: 4.2_
  - _Requirements: 17.1, 17.2_
  - _Boundary: NoNetworkLists_

- [ ] 6. Validation

- [x] 6.1 End-to-end, determinism, offline and confinement
  - `tests/recovery/test_e2e_recovery.py`: `fitdocs sync` (drain) on a staged
    inbox with a synthetic intervals.icu delivery (17 metrics: no sleep
    stages, no body battery, so the sleep section shows total sleep only)
    and synthetic workout `.fit` files, then `fitdocs recovery`: exit 0, page
    and charts written; a second run all `UNCHANGED`; `fitdocs check` clean;
    the page and charts byte-identical under `TZ=UTC` and
    `TZ=Pacific/Kiritimati` and under two faked system dates, in-process
    with the history precedent's `time.time` fake and `TZ` switch
    (`tests/test_history_e2e.py:213`).
  - `tests/test_confinement.py`: `EntryPoint(id="recovery", …)` with its own
    `non_vacuous` (the recovery page exists); a test that `recovery` is a
    registered writing entry point, and a test that its `non_vacuous`
    predicate tells a real recovery write from an empty run (the
    `tests/test_confinement.py:1658-1721` precedent).
  - **Mutations:** write the run date into the frontmatter (determinism
    reds); write a file beside `recovery/` (confinement reds); make
    `non_vacuous` always true (the discrimination test reds).
  - **Observable:** the e2e and confinement tests green.
  - _Requirements: 2.1, 13.2, 13.4, 14.1, 14.2, 14.3, 17.1, 17.5_

- [x] 6.2 Rebase, transcribe late citations, re-derive the version constants and validate the whole
  - When 1.1's records arrived after 1.2: transcribe them into
    `constants.py`, regenerate the page golden through `test_page`'s
    `main()`, and rerun `tests/recovery/test_constants.py`, `test_page.py`
    and `test_docs_recovery.py`; record the transcription in Implementation
    Notes.
  - Rebase onto `main`; re-derive `CONTRACT_VERSION` (main + 1), the command
    count and its spelled form, and every appended list, keeping both sides;
    regenerate the declaration goldens and, when `dashboards` is on `main`,
    the kinds block; write the landed numbers as literals into the history
    pin ("Raised from ``N`` to ``N+1`` by recovery"), keeping every peer's
    literal pin, and re-pin every head-paragraph pin on `main` to
    recovery's "What changed" paragraph (grep the outgoing paragraph's
    phrases across `tests/`); re-check the no-network order and the
    `test_e2e.py` rows against dashboards' landing state.
  - Run `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .`
    and `uv run mypy`; check branch CI before merging.
  - **Observable:** the full validation green after the rebase; Implementation
    Notes record the final version numbers and which records are citations.
  - _Requirements: 11.2, 11.3, 13.3_

- [ ]* 6.3 Maintainer-run look at the page on the maintainer's own data (no data enters the repository)
  - Run `fitdocs recovery` on the maintainer's data root; read the page in
    light and dark viewers; confirm the source switches (Garmin export →
    Apple Health → intervals.icu) are drawn and stated; report anything odd
    as a queue item. Nothing is committed from the data root.
  - _Requirements: 5.4, 5.5, 12.6_

## Implementation Notes

- Planning record (2026-10-12): Step 3.5 task-graph review ran twice, as an
  independent reviewer the batch controller dispatched. Round 1 returned
  NEEDS_FIXES with 16 findings (1 critical, 7 important, 8 minor) and three
  controller rulings: R1, `MetricInfo.label` is folded into wellness-store;
  R2, the engine passes the panel limit to `build_view`; R3, the registry
  append moves into 2.1. All of them were applied. Round 2 verified every
  finding resolved and added one ruling, that series fixtures on disk go
  only through wellness-store's `tests/wellness/builders_series.py::write_series`,
  plus four minor fixes. Those were applied without a further review, as
  the controller directed.
- Cross-spec review round 1 (2026-10-13, controller fix plan): I-1, Garmin
  attribution for wellness values. recovery appends the settled names to
  `render/attribution.py` in 3.3, `view` collects `origins`, and `page`
  prints the line beneath the title. Chart images carry no stamp; that is a
  maintainer Open Question. I-3, the final no-network order with dashboards.
  M-1, `baseline_key` dropped. I-2/M-2, the literal history pin and the
  peer head-paragraph re-pins (1.6, 6.2). M-8, the forbidden-phrase pattern
  is named as consumed by workout-wellness. M-12, a stale `MetricInfo`
  re-pin line removed from the design. Requirements gained 12.7 and 12.8.
- Outcomes of 1.1 (the citation verification) and of 1.2's upstream checks
  are recorded below when those tasks run.

### Task 1.1 — primary-text verification (2026-10-14)

All approved values remain unchanged. The table records paraphrases, not
verbatim extracts. Primary texts were opened through the browser research tool;
a publisher or repository URL alone does not establish verification.

| Key / full reference | State and primary-text locator | What the opened work states / scope |
|---|---|---|
| `PLEWS_2013_SPORTS_MED` — Plews DJ, Laursen PB, Stanley J, Kilding AE, Buchheit M. Training adaptation and heart rate variability in elite endurance athletes: opening the door to effective monitoring. Sports Med. 2013;43(9):773–781. doi:10.1007/s40279-013-0071-8. [Author full text](https://www.researchgate.net/publication/249321195_Training_Adaptation_and_Heart_Rate_Variability_in_Elite_Endurance_Athletes_Opening_the_Door_to_Effective_Monitoring) | **verified / PRIMARY_TEXT**; §3, pp.774–775; §5, pp.779–780; Fig.4, p.779 | Weekly and seven-day rolling ln rMSSD reduce daily noise. Individual worthwhile-change regions illustrate comparison of averaged HRV. This does not establish a 60-day baseline or the exact 0.5 multiplier. |
| `PLEWS_2013_IJSPP` — Plews DJ, Laursen PB, Kilding AE, Buchheit M. Evaluating training adaptation with heart-rate measures: a methodological comparison. Int J Sports Physiol Perform. 2013;8(6):688–691. doi:10.1123/ijspp.8.6.688. [Author full text](https://www.researchgate.net/publication/235906316_Evaluating_Training_Adaptation_With_Heart-Rate_Measures_A_Methodological_Comparison) | **verified / PRIMARY_TEXT**; Experimental Protocol, p.689; Discussion and Fig.1, p.690 | Weekly ln rMSSD and resting-HR averages are compared with isolated readings. Fig.1 instead uses 0.2 times a within-group SD; that is a different threshold population and cannot govern the individual 0.5 multiplier. |
| `PLEWS_2014_IJSPP` — Plews DJ, Laursen PB, Le Meur Y, Hausswirth C, Kilding AE, Buchheit M. Monitoring training with heart-rate variability: how much compliance is needed for valid assessment? Int J Sports Physiol Perform. 2014;9(5):783–790. doi:10.1123/IJSPP.2013-0455. [Primary PDF](https://padletuploads.blob.core.windows.net/prod/232663277/a484fe91e8f7d906336f166bfc592e5d/plews2014.pdf) | **verified / PRIMARY_TEXT**; abstract, p.783; Discussion, p.785; Practical Applications and Conclusions, p.789 | Three randomly selected valid weekly ln rMSSD recordings suffice in trained triathletes; recreational athletes may need approximately five. Generalizing three to every recovery metric/population is an explicit fitdocs departure. |
| `BUCHHEIT_2014` — Buchheit M. Monitoring training status with HR measures: do all roads lead to Rome? Front Physiol. 2014;5:73. doi:10.3389/fphys.2014.00073. [Primary text](https://www.frontiersin.org/journals/physiology/articles/10.3389/fphys.2014.00073/full) | **verified / PRIMARY_TEXT**; “Acknowledging the uncertainty of the measures”; “Determining the smallest worthwhile change” | Repeated HR/HRV measurements reduce noise. Describes 0.5 or 1 times within-athlete CV and warns that practical meaning of such cutoffs is unestablished. This is supporting context, not the governing 0.5 SD record. |
| `VESTERINEN_2016` — Vesterinen V, Nummela A, Heikura I, Laine T, Hynynen E, Botella J, Häkkinen K. Individual endurance training prescription with heart rate variability. Med Sci Sports Exerc. 2016;48(7):1347–1354. doi:10.1249/MSS.0000000000000910. [Accepted primary manuscript](https://jyx.jyu.fi/bitstream/handle/123456789/50625/vesterinenetalindividualendurancemsse.pdf) | **verified / PRIMARY_TEXT**; Methods, “HRV guided training”, paragraphs 1–3; Discussion, “Methodological issues to use HRV in training prescription” | Compares a seven-day RMSSD average with mean ±0.5 SD from four preparation weeks, updating after four intensive weeks. Uses untransformed RMSSD and guides training. Fitdocs uses log-HRV, preceding 60 days and descriptive marking only. |
| `ALTINI_PLEWS_2021` — Altini M, Plews DJ. What Is behind Changes in Resting Heart Rate and Heart Rate Variability? A Large-Scale Analysis of Longitudinal Measurements Acquired in Free-Living. Sensors. 2021;21(23):7932. doi:10.3390/s21237932. [Bibliographic record](https://pubmed.ncbi.nlm.nih.gov/34883936/) | **attested only / SECONDARY_ATTESTATION**, locator: PubMed bibliographic record PMID 34883936; no primary-text locator | Metadata confirmed. MDPI article, HTML and PDF failed to open; PMC returned a verification interstitial; Europe PMC failed. No claim about 60-day normal values was verified. Does not govern a constant. |

Governing records for transcription in task 1.2 (every `Citation` below has
`verification=PRIMARY_TEXT`, the authors/year/work above and the stated locator):

| Constant / rule | Governing source and required fields | Corroboration / departure |
|---|---|---|
| `ROLLING_DAYS = 7` | `Citation PLEWS_2013_SPORTS_MED`, locator: §3, pp.774–775; §5, pp.779–780 | `PLEWS_2013_IJSPP`, Statistical Analysis p.689, `AGREES`; rolling seven-day application to sleep/other metrics is fitdocs's method choice. |
| `MIN_ROLLING_VALUES = 3` | `Citation PLEWS_2014_IJSPP`, locator: abstract p.783; Practical Applications and Conclusions p.789 | `Departure`: source studies weekly ln rMSSD in trained triathletes, approximately five samples for recreational athletes; fitdocs applies a fixed three-value minimum to all nine methods for one explicit missingness rule. |
| `BASELINE_DAYS = 60` | `FitdocsChoice`, key `BASELINE_DAYS`; justification: maintainer's 2026-10-12 decision for a longer personal baseline; search_basis: six candidates above, Altini primary unavailable and no opened work specifies this 60-day method | `Departure`: Vesterinen Methods uses four weeks, periodically updated; fitdocs uses preceding 60 days, excluding D, to implement the approved as-of baseline. No Altini corroborator claims agreement with 60. |
| `MIN_BASELINE_VALUES = 30` | `FitdocsChoice`, key `MIN_BASELINE_VALUES`; justification: at least half the 60-day window before estimating variation; search_basis: no minimum of 30 found in the five opened works | No corroborator or departure. |
| `RANGE_SD_MULTIPLE = 0.5` | `Citation VESTERINEN_2016`, locator: Methods, “HRV guided training”, paragraph 2; Discussion, “Methodological issues to use HRV in training prescription” | `Departure`: source uses raw RMSSD and four weeks plus training decisions; fitdocs uses log HRV, 60 preceding days, descriptive marking and also resting HR. Plews 2013 IJSPP Fig.1 uses 0.2 between-athlete SD and does not corroborate this individual threshold. |
| `LOG_TRANSFORM` | `Citation PLEWS_2013_SPORTS_MED`, locator: §3, pp.774–775; §5, pp.779–780 | `PLEWS_2013_IJSPP`, Experimental Protocol p.689, `AGREES`; studies ln rMSSD; exponentiating for display preserves metric units. |
| `SDNN_APPLICATION` | `FitdocsChoice`, key `SDNN_APPLICATION`; justification: display each HRV definition separately with one transparent method; search_basis: opened works study rMSSD, no SDNN counterpart verified | `Departure`: source evidence concerns rMSSD; fitdocs applies log averaging and range to SDNN independently, without conversion or mixing. |
| `RESTING_HR_APPLICATION` | `FitdocsChoice`, key `RESTING_HR_APPLICATION`; justification: one descriptive rolling/baseline comparison on resting HR's own linear values; search_basis: Plews 2013 IJSPP and Buchheit discuss averaged HR, but no identical 60-day/0.5-SD resting-HR method verified | `PLEWS_2013_IJSPP`, Discussion p.690, `OMITS` with note: supports weekly HR averaging but not fitdocs's full range method; `Departure`: transfer of the HRV range to linear resting HR. |
| `COMPARED_QUANTITY` | `Citation PLEWS_2013_SPORTS_MED`, locator: Fig.4 p.779; §5 pp.779–780 | `VESTERINEN_2016`, Methods “HRV guided training”, paragraphs 1–3, `AGREES` with note: supports comparison of seven-day averages, not fitdocs's log/60-day descriptive method; `Departure`: descriptive marking uses the two bounds without training advice or confidence-interval inference. |
| `SAMPLE_SD` | `FitdocsChoice`, key `SAMPLE_SD`; justification: n−1 sample estimate of baseline-day variation; search_basis: no explicit denominator verified in the opened candidates | No corroborator or departure. |
| `SLEEP_METHOD` | `FitdocsChoice`, key `SLEEP_METHOD`; justification: descriptive recent and longer sleep averages, no unsupported normal range; search_basis: no matching sleep-range method verified in the opened HRV works | No corroborator or departure. |
| `PER_SOURCE` | `FitdocsChoice`, key `PER_SOURCE`; justification: maintainer's 2026-10-12 decision because platform definitions differ; search_basis: opened works do not establish comparability of export-source definitions | No corroborator or departure. |
| `SHOWN_SOURCE` | `FitdocsChoice`, key `SHOWN_SOURCE`; justification: use canonical source and bridge only gaps within the seven-day rolling window, carrying the source identifier, never the value; search_basis: no source-carry policy in the opened works | No corroborator or departure. |

Scope differences were reported to the maintainer during this run. They do
not alter a value or turn descriptive marking into an inference about health,
performance or training. Task 1.2 must transcribe departures rather than
present all choices as a single published method.

Departure field mappings (literal transcription brief; sources/locators are
the verified records above):

| subject | source_specifies | fitdocs_does | reason |
|---|---|---|---|
| `MIN_ROLLING_VALUES` | Plews 2014, Practical Applications and Conclusions p.789: three in trained triathletes, approximately five in recreational athletes | Require three present days for each of nine methods | One explicit missingness rule across metrics; no claim that three establishes validity for every population/signal |
| `BASELINE_DAYS` | Vesterinen 2016, Methods “HRV guided training”, paragraphs 2–3: four-week reference periodically updated | Use D−60 through D−1 | Approved personal as-of baseline excludes the judged day and implements the maintainer's longer-window decision |
| `RANGE_SD_MULTIPLE` | Vesterinen 2016, Methods “HRV guided training”, paragraphs 1–3: raw RMSSD, four weeks, training prescription | Use 0.5 SD for log HRV and linear resting HR over preceding 60 days; descriptive marking only | Preserve approved transparent windows and separate metrics while keeping the display descriptive |
| `SDNN_APPLICATION` | Plews 2013 Sports Med, §3 pp.774–775: preferred index is ln rMSSD | Apply log averaging/range independently to SDNN | Show each platform's HRV definition separately without unsupported SDNN/rMSSD conversion |
| `RESTING_HR_APPLICATION` | Vesterinen 2016, Methods “HRV guided training”: range applied to RMSSD; Plews 2013 IJSPP Discussion p.690 supports weekly HR averaging | Apply the approved windows/range to linear resting HR values | A single explicit descriptive comparison rule; no published claim of this exact resting-HR range |
| `COMPARED_QUANTITY` | Plews 2013 Sports Med, Fig.4 p.779: weekly ln rMSSD comparison with individual SWC and confidence intervals | Mark a seven-day mean outside either bound, without confidence intervals or training instructions | Describe the athlete's own figures rather than infer performance, health or training decisions |

Task 1.1 review remediation: corrected the weekly-averaging and Vesterinen
Discussion locators and supplied explicit four-field departure mappings.

- 1.1: READY_FOR_REVIEW → independently APPROVED round 2; fresh completion
  checklist VERIFIED. Baseline `uv run pytest`: 14733 passed, 44 skipped;
  ruff check/format and mypy clean (550 files); CLI help smoke exit 0.
  Only citation notes changed; all approved values preserved.

- 1.2 review remediation: controller reworded two 1.1 departure fields
  (range reason and compared-quantity behavior) to stay compatible with the
  approved page phrase pattern. Meaning, provenance and values unchanged.


### Task 1.2 — upstream outcomes and implementation notes (2026-10-14)

All upstream checks passed through executable introspection. Definition paths
below are relative to the repository; METRICS's binding is model.py:61 (the
introspection artifact also names its MetricInfo value type at line 48).

| Prerequisite | Verified file/line and public signature / outcome |
|---|---|
| Wellness facade | `src/fitdocs/wellness/__init__.py:26` exports Metric, METRICS, MetricInfo, SeriesValue, WellnessSeries, read_series and SeriesReadError |
| Metric labels | `src/fitdocs/wellness/model.py:48` MetricInfo includes label; `:61` METRICS is the shared vocabulary; no recovery-side labels or units added |
| Values and series | `src/fitdocs/wellness/model.py:285` SeriesValue(day, metric, source, origin, value, canonical); `src/fitdocs/wellness/series.py:267` WellnessSeries(values=()) exposes values, is_empty(), days(), by_source(metric, source), canonical(metric, day) |
| Series reader | `src/fitdocs/wellness/series.py:340` read_series(data_root: Path) -> WellnessSeries; `:28` SeriesReadError available |
| Sanctioned staging builder | `tests/wellness/builders_series.py:12` write_series(data_root: Path, values: Iterable[SeriesValue]) -> tuple[Path, ...]; writes through real year/manifest codec; recovery must consume this helper |
| Intervals delivery | `tests/wellness/builders_intervals.py:18` intervals_delivery_bytes(records: Sequence[Mapping[str, object]], *, origins: Mapping[str, str] \| None = None) -> bytes; `src/fitdocs/wellness/formats/intervals.py:22–23` delivery format/version; `src/fitdocs/wellness/registry.py:20` registered intervals-icu format |
| History facade | `src/fitdocs/history/__init__.py:53` exports all required names; `history/engine.py:203` read_history_inputs(data_root: Path) -> HistoryInputs; `:229` compute_history(inputs, *, methodology: str \| None) -> HistoryComputation \| None |
| History rows/errors | `src/fitdocs/history/page.py:390` day_rows(series, model, weeks) -> tuple[DayRow, ...]; DayRow at `:376`; HistoryComputation at `history/engine.py:189`; MethodologyConfigurationError at `:168` |
| Kit facade | `src/fitdocs/render/charts/kit/__init__.py:31` exports ChartRequest, ChartData, Column, ValueKind, render_chart and describe_kinds; `kit/registry.py:147` describe_kinds() lists 16 kinds, with small-multiples bound["limit"] == 12 |
| Unit formatter | `src/fitdocs/render/charts/kit/format.py:116` format_value(value, column, *, with_unit) -> str |
| Ownership prerequisite | `src/fitdocs/layout.py:153` OWNED_PATHS includes wellness/; current main CONTRACT_VERSION is 11; recovery's bump remains main + 1 at landing |

- 1.2: READY_FOR_REVIEW → independently APPROVED round 2 → fresh completion
  gate VERIFIED. Five constants, eight rules, nine methods; all approved
  values and provenance preserved. Tests-first RED and helper OFF/ON/removal
  evidence; 128 independent replayed mutations plus five reviewer probes,
  each RED/restored GREEN. Focused 83 passed; full 14816 passed / 44 existing
  skips; ruff check/format and mypy clean (555 files).
- Numeric guards count exact semantic sites; 1.3 may append only exact-site
  structural identity exemptions actually introduced in baselines.py, under
  the existing exempted-identities clause. Preserve guard logic and previous
  exemptions; no broad exemption or unknown-site preallocation.
- Review lessons: a duplicate-site fixture pins counting; both scanned files
  must coexist to pin the complete walk; bibliography checks need every
  corroborator Citation field; printed metadata must avoid the page pattern's
  forbidden tokens even in negated explanations.
- Mutation targeting: before snippets must occur exactly once in the restored
  snapshot, or be scoped to a verified named AST call/assignment; repeated
  digits/year lines cannot establish which field changed.
- Full pytest needs authorized execution for existing AF_UNIX socket and
  isolated build/install fixtures. Restricted DNS/cold-cache failures and
  socket EPERM are environment failures; no source patch or skipped test was
  used. Focused tests/mutations use the writable temporary uv cache.
- Task 1.3 review lesson: constant observations on identical dates pin means
  but leave source-specific SD, counts, ranges and positions indistinguishable.
  Use distinct variability, coverage and origins, and check all exposed fields.
  Sleep arithmetic needs varied positive observations for every metric; a
  no-range assertion alone does not protect rolling or baseline calculations.
- Task 1.3: APPROVED round 2 and VERIFIED. Per-source/date indexes,
  transformed sample statistics, explicit missingness and the exact ten-name
  facade are available. 116 claimed and four independent mutations were red
  and restored green; 329 assertion cases discriminate. Fresh full suite:
  15,145 passed / 44 expected skips; controller scoped 523 passed; Ruff and
  mypy clean. Baseline and deviation fsum each have an exact valid-domain
  precision pin. Runtime TZ/clock probes U01/U02 are explicitly allocated to
  1.4/1.5; shown-source and future consumer integration are not claimed here.
- Task 1.4 review lesson: varying metrics and source names in selector tests
  does not pin arguments forwarded by `shown()`. Exercise `shown()` itself
  across all METHODS metrics and multiple genuinely selected sources, with
  independent nontrivial expected observations; a constant selected name can
  leave hardcoded delegation green.
- Task 1.4's bounded forwarding audit includes both calls: arguments to
  `shown_source(metric, day)` as well as `on(metric, source, day)`. Distinct
  per-metric canonical source IDs and a real neighboring/future-day source
  flip are needed to distinguish selector arguments.
- Task 1.4: APPROVED round 3 and VERIFIED. `shown_source` selects the
  requested metric's canonical source on the requested day, carrying at
  most six days; `shown` delegates to the same source's `on`. All five
  forwarded arguments discriminate, including different per-metric IDs and
  an actual future canonical source. 51 claimed and two independent probes
  red/restored green; 171 assertion cases. Fresh full suite: 15,316 passed /
  44 expected skips; controller scoped 694 passed; Ruff/mypy clean. The
  known U01 timezone probe is now caught; unused-clock structural prevention
  and formal surface guards remain task 1.5, consumer integration later.
- Task 1.5 import-row clarification: exact rows for existing modules are
  measured; rows for absent modules are anticipated. Their actual standard
  library/import footprint is known when each module is implemented, so its
  task owns a narrow matching row re-pin, not a guard-policy change. This
  preserves per-module equality without inventing future imports or forcing
  unused dependencies. Existing packaging dependency declaration coverage is
  `tests/test_packaging.py::test_dependencies_declaration_is_unchanged`.

- **1.5 verified:** independent round-2 review replayed all78 claimed and12 own mutations RED/restoredGREEN, mapped all48 assertion sites, and passed155 additional finite-family/coexistence controls. Full15700passed/44expectedskips; controller fresh1079/statics clean. Exact current import rows, all-seven planned rows and reverse-import subset are guarded;4.3 closes module-set/reverse equality. Shared finite literal-target resolution covers imported/simple assigned aliases, known argument dictionaries/fromlists and relative anchors; actual tz slots reject missing/resolvedNone, with explicitUTC and lexical-scope positive controls. Arbitrary computed targets/call results/control flow remain explicit static-analysis limits, not a general IO gate. Runtime dependency declaration uses the existing packaging literal pin.

- **1.6 verified:** owned14/declared8 append-only recovery locations, exact path helpers/declaration and new golden, seven predecessor golden version lines only, contract11→12 with literal history/head/published rules, wiki-contract Amendment7/2.19/3.13. Independent round2 review replayed72claimed+11own RED/restoredGREEN, bounded all four root/chart argument slots with lexical/nested/mixed-case inputs and independent3×3 expectations; source helpers unchanged. Full15717passed/44expectedskips, scoped1531 and controller fresh210/statics clean. Declaration dispatch docstring counts/enumerates8. Final6.2 rederives main+1 version/amendment/peer head pins at landing; later Page/Engine/confinement tasks implement the published runtime behavior.


### Task 2.1 — blocked after two debug cycles (2026-10-15)

- Final implementer READY_FOR_REVIEW; final independent review REJECTED.
  All 675 claimed mutation pairs reproduced (670 direct and five explicitly
  historical regression-only); all 4177 assertion-parameter instances have
  direct evidence. The positioned-gap and eight-style repairs are correct.
- Remaining defect is native test coverage, not production: the 1000-row
  and eight-segment limits must count all received inputs, including a row
  whose x is None. Substituting positioned-only populations for either
  `_check` limit leaves 1466 task/boundary tests green; combining both
  substitutions leaves the full 17169-test suite green (44 expected skips).
  Independent public `render_chart` controls directly fail each faulty
  substitution and pass after restoration. Retain the existing at-bound
  and markless-present-x contrasts; add valid 1001-row and nine-segment
  cases with a present-value final row whose x is None, asserting exact
  `over_bound` / `too_many_series` metadata through the public pipeline.
- Both allowed debug cycles are exhausted. No third cycle or direct
  remediation was attempted. The 16 submitted draft files, eleven goldens
  and prior tests are preserved uncommitted. Task 2.2 and chart-dependent
  work await acceptance of 2.1; independent 3.1 remains actionable.
- Fresh restored original: 17169 passed / 44 expected skips; chart/dashboard
  4831 passed; inherited controls 1913 passed; Ruff check/format (747 files),
  mypy (562 files) and diff checks clean. Production source SHA256
  `9ae718abe04710a869ea05a97ba80496fb60137d66d216dca92bc6d1442a824a`;
  test SHA256 `0731b0b5dac9612e8caba1828af87efa64b79690095ea4084effbee248141019`.
- Evidence: `/private/tmp/recovery-review-2.1-debug2.md` and its linked
  `recovery-review-2.1-debug2-evidence/` package; own public controls
  `/private/tmp/recovery_review_debug2_own_controls.py`. No adjacent work
  was surfaced outside this leaf; the blocker is already tracked here.


### Task 3.1 accepted (2026-10-15)

- READY_FOR_REVIEW → independent APPROVED round 3 → fresh controller
  completion gate VERIFIED. `view.py` builds the typed 90-day model from
  the public series, Baselines and real history computation. The workout
  builder append is now frozen; only View's measured boundary import row
  changed. All twenty task-local View contributions are pinned.
- Two append-only test repairs preserve every earlier case. Complete daily
  and latest records are checked separately for resting HR, both HRV
  definitions and total sleep; sleep table rows are a separate observable.
  Independent arithmetic, two actually selected sources, absent/carried
  and unformed/formed records prevent the earlier forwarding collisions.
- Fresh independent replay: 311 source-plus-selection pairs, 304 direct
  and seven historical exception-only; all 272 parameter nodes and 37
  assertion sites directly covered somewhere. Four additional reviewer
  faults were caught and restored. Full restored original: 17440 passed,
  44 expected skips; final reviewer and fresh controller recovery/history:
  1537 passed, no skips. Ruff check/format (749 files), mypy (564 files),
  diff and prose checks clean. Exact old prefixes, sixteen chart draft
  hashes and eleven golden mtimes preserved.
- Scope limit: the local full suite includes the uncommitted 2.1 draft.
  This acceptance does not clear its blocker, establish feature GO, or
  claim remote CI. Exact schema/frozen metadata mutation tests and later
  chart/page/engine/attribution responsibilities remain separately scoped.
- Evidence: `/private/tmp/recovery-review-3.1-round3.md`, independent raw
  `recovery-review-round3-evidence/`, sealed 1577-entry implementer package
  `recovery-task-3.1-round3-final-evidence/`, and fresh controller
  `/private/tmp/recovery-task-3.1-verification.md`.


### Autonomous run parked after task 3.1 (2026-10-15)

- Accepted and pushed: 1.1–1.6 and 3.1 (7 of 20 mandatory leaves).
  Task 3.1 commit: `2c6ca52`. Task 2.1 remains the sole primary blocker;
  both allowed debug cycles were exhausted, as recorded above. No third
  debug cycle or parent bypass was attempted.
- No remaining mandatory leaf is actionable under the approved ordering:
  2.2 and 3.2 require 2.1; 3.3 requires 3.2; 3.4 extends 3.3's page;
  4.1 requires 3.4; 4.2 calls 4.1's engine; 4.3, 5.1 and 5.3 require
  4.2; 5.2 requires 4.2 and 5.1; 6.1 exercises 4.2's command; 6.2 is
  the final whole-feature integration and cannot run before those leaves.
  These twelve leaves remain unchecked, awaiting 2.1 acceptance. No
  placeholder prerequisites were fabricated. Optional 6.3 remains
  maintainer-only and was not run.
- Feature status: incomplete; feature-level GO, release build, installed
  wheel smoke, branch CI and main merge were not attempted. The current
  local full17440/44 result includes 2.1's preserved uncommitted draft and
  does not accept that leaf or establish a remotely tested feature.
- Preserve the worktree `/private/tmp/fitdocs-recovery`, `impl/recovery`
  and all sixteen uncommitted chart draft files/eleven golden mtimes for
  human review. The exact blocker, native public-pipeline controls needed
  and prior raw evidence are already tracked in task 2.1 above; no duplicate
  queue item was created. All reviewers reported no adjacent untracked
  follow-up work.


### Task 2.1 additional retry authorization (2026-10-15)

- User instruction: "take another 2 debug rounds to find a solution".
  This grants two additional debug cycles for the sole root blocker 2.1;
  the two previous cycles remain historical. Reclaimed the released spec
  after reading the whole shared log: no recovery claimant or main merge.
- Resume from pushed `2447864` and the exact sixteen-file chart draft.
  Accepted tasks 1.1–1.6 and 3.1 remain frozen. A fresh debug investigator,
  new implementer and independent reviewer handle each additional cycle.
  The current finding concerns native received-domain refusal coverage;
  production and goldens must remain unchanged unless new concrete
  evidence proves an in-boundary source defect.


### Task 2.1 accepted after additional debug round 1 (2026-10-15)

- The user's two-round extension superseded the earlier bounded stop.
  Additional round 1 returned RETRY_TASK, a new implementer returned
  READY_FOR_REVIEW, a fresh reviewer APPROVED, and the controller's fresh
  completion gate VERIFIED. The second additional round was not needed.
  The prior parked/blocker entries above are historical; 2.2 and the
  rendering dependency chain may now proceed after current-main rebase.
- The original reference-band source, registry tail, sanctioned dashboard
  block, boundary entry and eleven goldens are accepted. Test-only repair
  appends exactly 24 public and eight direct cases over received row and
  segment limits. Public outcomes distinguish normal return from an empty
  ChartError; refusal diagnostics compare all eleven literal fields.
- Independent replay: 708 source-plus-selection pairs, 703 direct and
  five historical exception-only; all 4209 assertion-parameter targets
  preserved/directly covered, including all 4177 old and 32 new targets.
  Three additional reviewer faults were caught/restored. All 43 criteria
  classified: 34 PINNED, nine PRESERVED-ONLY, zero UNPINNED. No unrelated
  future catalog listing/budget/amendment coverage is claimed.
- Stable-base full original: 17472 passed / 44 expected skips; final
  chart/dashboard: 4863 passed; fresh controller task/boundary: 1498
  passed. Ruff check/format (749 files), mypy (564 files), diff and scans
  clean. Exact 104123-byte prefix, nineteen other frozen paths and eleven
  golden mtimes preserved. Source SHA256 remains
  `9ae718abe04710a869ea05a97ba80496fb60137d66d216dca92bc6d1442a824a`;
  final test SHA256
  `bce8d2218ba13a58e751ebf29f0a524ef6dbf4259b97a78ebf332e707593b5ef`.
- Evidence: `/private/tmp/recovery-debug-2.1-extra1.md`, sealed implementer
  `recovery-task-2.1-extra1-final/`, independent
  `/private/tmp/recovery-review-2.1-extra1.md` and its raw package, and
  `/private/tmp/recovery-task-2.1-extra1-verification.md`. No adjacent
  follow-up was surfaced.
- Main advanced to wellness-pull `693fd445` during review (contract 12,
  wiki Amendment 7). This acceptance is on stable base `2447864`, not a
  post-rebase or feature GO claim. Commit/push this reviewed leaf, then
  rebase before the next leaf, preserve both histories, re-derive the
  recovery landing numbers and validate the combined tree.


### Post-rebase compatibility verified (2026-10-15)

- Rebased the accepted recovery work onto wellness-pull main `693fd445`;
  clean rewritten head `c23e2fc` was pushed with force-with-lease. Recovery
  now advances CONTRACT_VERSION 12→13, retaining wellness-pull's 11→12
  history and permanent pull guarantees. DOC_VERSION remains 9; runtime
  dependency declarations are unchanged. Recovery wiki amendment is 8;
  wellness-pull Amendment 7/Requirement 2.15 remain intact.
- Resolved only task 1.6's shared contract/current-head/history companion
  surfaces. Migrated the five current-head parameters from wellness-pull
  to recovery without changing the existing Markdown parser or other
  guards; updated literal index/version pins and regenerated eight
  declaration goldens through the sanctioned writer, version lines only.
  Accepted chart/View bytes and the exact automatic confinement merge are
  preserved. Original acceptance commit IDs above are historical pre-rebase
  records; current chart commit is `c23e2fc`, View `8d33f85`, location
  `0b03a49`.
- Fresh independent compatibility APPROVED and controller VERIFIED:
  full combined tree 21446 passed / 44 expected skips; final focused 71
  passed; Ruff check/format (761 files), mypy (576 files) and diff clean.
  Five targeted/own faults produced nineteen direct intended failures and
  restored GREEN. All 1958 tracked byte/size/mtime snapshots restored;
  both histories, metadata, goldens and peer implementation files preserved.
- Evidence: `/private/tmp/recovery-rebase-review.md` and its raw package,
  plus `/private/tmp/recovery-post-rebase-verification.md`. This verifies
  compatibility, not feature GO or task 6.2 completion. Eight mandatory
  leaves are accepted; continue with 2.2, then the remaining approved plan.


### Task 2.2 accepted (2026-10-15)

- READY_FOR_REVIEW → independent APPROVED → current-evidence VERIFIED.
  Five-file boundary: appended complete canonical-JSON listing/order pins,
  90-row typical budget and live at-bound ceiling; chart-catalog Amendment 1
  copies all ten normative clauses and explicitly applies Common rules and
  Requirements 2/12. Prior tests, metadata approvals and phase notes remain
  unchanged. The chart-kind group is complete; nine mandatory leaves are
  now accepted.
- Actual fixture: ninety rows, two forty-five-row segments, thirteen true
  flags, two band paths and two mid polylines. Original 9622 bytes ×1.25,
  rounded up to 100, yields budget 12100. Required circle expansion renders
  13059 bytes and live at-bound 100851 (>80000). Frozen at-bound golden
  remains 61014 bytes: observed/PRESERVED-ONLY, not claimed mutable through
  production. Existing golden comparisons preserve its live relationship.
- Independent 92/92 claimed pairs reproduced (93 intended failures), plus
  four own faults (five intended failures); sixteen explicit metadata type
  substitutions and all four new assertion sites directly sensitive, zero
  survivors. Full restored original 21450 passed / 44 expected skips;
  charts 3697, dashboard listing/docs 13; Ruff check/format (761 files),
  mypy (576 files), diff/scans clean. Exact old prefixes and accepted
  chart/View bytes preserved. Static-artifact limitation disclosed; no
  adjacent follow-up.
- Evidence: `/private/tmp/recovery-review-2.2.md`, independent raw
  `recovery-review-2.2-evidence/`, implementer 319-file sealed
  `recovery-task-2.2-evidence/` and archive, and
  `/private/tmp/recovery-task-2.2-verification.md`. Continue with 3.2;
  future chart construction/page/writer/CLI behavior remains unimplemented.


### Task 3.2 paused for a chart-axis prerequisite (2026-10-16)

- Task 2.2 is accepted and pushed at `a37d098`; nine of twenty mandatory
  leaves remain accepted. Task 3.2 is not accepted. Its draft adapter
  correctly forwards every window day with genuine missing values, through
  the real public kit, but that does not satisfy Requirement 2.2's actual
  90-day time-axis guarantee.
- Fresh `kiro-debug` round 1 returned SPEC_CONFLICT / STOP_FOR_HUMAN.
  Existing line, small-multiples and accepted reference-band kinds choose
  the x domain and accessible x extrema from drawable rows, discarding
  markless endpoint dates. No public domain option exists. A deterministic
  six-chart probe forwards February 1–May 1 2025; load/other show only
  March 16–17, the four reference charts March 16–20. The valid probe
  writes only under tmp_path and copies evidence after pytest exits.
- Proposed prerequisite: use every received present x for domain and x
  description while retaining drawable-only y inputs, marks, counts, gaps
  and no-data behavior. Reference-band's flags-only path must keep genuine
  flags separate from domain-only dates. Exact unapplied three-kind patch
  and test/golden/plan boundary are in
  `/private/tmp/recovery-debug-3.2-round1-proposal.md` and
  `/private/tmp/recovery-debug-3.2-round1-proposed.patch`; governing report
  `/private/tmp/recovery-debug-3.2-round1.md`. No shared kind was edited.
- Scope approval was requested. Dependent work remains paused until an
  answer; elapsed time does not grant approval. Preserve all three draft
  paths and evidence; do not mark 3.2 or feature GO. This concrete blocker
  already belongs to this leaf and is not a separate queue item.
- Implementer final exact BLOCKED/released: 159 task-local tests and
  canonical recovery/charts 5091 passed; Ruff check/format (763 files),
  mypy (578 files), diff clean. Only 149 of 343 planned fault replays
  completed RED/restored GREEN; 194 are explicitly pending after the
  controller hold. No independent acceptance review or full suite was run
  for this draft. Existing 977 frozen source/test hashes remain unchanged.
  Evidence: `/private/tmp/recovery-task-3.2-report.md` and its raw
  `recovery-task-3.2-evidence/` package.


### Chart-axis prerequisite approved (2026-10-16)

- User response: "yes, please fix it and continue" approves the concrete
  three-kind proposal following debug 3.2 round 1. The STOP_FOR_HUMAN entry
  above is historical; scope approval is no longer pending. Added mandatory
  prerequisite 2.3, restored group 2 to pending and made 3.2 depend on 2.3.
  The plan now has 21 mandatory leaves plus optional maintainer-only 6.3.
- Execute 2.3 with a fresh implementer/reviewer and independent acceptance
  before a fresh 3.2 retry. The existing three-file 3.2 draft and its 149
  completed/194 pending replays are preserved. Actual recovery-axis
  assertions and remaining discrimination are completed in resumed 3.2.
- The correction changes only kind-local domain/description populations;
  original values/missingness, drawable-only y/marks, true flags and
  no-data behavior remain. Parent controls metadata and selective commits.

- During 2.3, the approved wider line/typical extent moves tick positions
  when the frame replans; the same seven weekly tick values remain. The
  changed residual overhang makes its existing label-fit check fail by
  about 0.48 px at the right bound. A minimal conditional line-local
  overhang correction is part of this same approved axis fix; no shared
  layout change or other-kind expansion is needed. Independently review
  its geometry and direct mutation evidence. Only the line/typical golden
  is observed changed so far; old flags-only extent expectations may be
  updated where the wider x domain intentionally makes them obsolete.


### Task 2.3 accepted (2026-10-16)

- User-approved prerequisite READY_FOR_REVIEW → fresh independent APPROVED
  → current-evidence VERIFIED. Three kind-local x-domain/description fixes,
  separate genuine flags-only entries and a minimal conditional line-local
  overhang correction; three test modules and only line/typical.svg changed.
  No API, schema, option, registry, budget or shared-layer changes. Group 2
  is complete; ten of twenty-one mandatory leaves are accepted.
- Independent 45/45 valid source probes reproduced exact native failed
  nodes, then restored GREEN; six additional faults caught/restored. All
  194 new parameter nodes and changed assertions directly covered. Scoped
  chart-kit/recovery 5150 passed; targeted 1809; Ruff check/format 763 and
  mypy 578 clean. All 287 sealed artifacts and original 1960-path
  byte/mtime snapshot preserved. The three unaccepted 3.2 drafts remain
  unchanged. Tick-note wording above is corrected: same tick values,
  changed positions/residual overhang; the source correction is unchanged.
- Full combined draft tree: 21802 passed, 44 expected skips, one failure
  in load's existing settings guard, which mistakes frozen charts.py's
  `charts["load"]` Store for a settings read. This is not hidden or fixed
  by 2.3. Resumed 3.2 must remove the collision within its owned adapter
  (for example using the existing request.ref), without changing the guard.
- Fresh accepted-task validation used a detached a38dd24 checkout plus
  exactly the seven sealed submitted files, with independent import
  provenance and no unaccepted 3.2 source/test/import-row diff. Unmodified
  full pytest: 21644 passed / 44 expected skips, exit 0, 571.98 s. No test
  skip, patched fixture or guard change; both checkout preservation audits
  passed. This accepts 2.3 only, not the combined draft or feature GO.
- Evidence: `/private/tmp/recovery-review-2.3.md`, its raw package and
  isolated-scope manifest, sealed `recovery-task-2.3-evidence/`, and parent
  `/private/tmp/recovery-task-2.3-verification.md`/`.json`. No new unowned
  follow-up; 3.2 owns its existing collision and actual six-chart window
  assertions/remaining discrimination. Continue directly with fresh 3.2.


### Task 3.2 accepted (2026-10-16)

- Fresh retry READY_FOR_REVIEW → independent APPROVED → controller VERIFIED.
  The adapter constructs all six optional sections through the public kit in
  CHART_NAMES order, with exact typed requests, catalog labels/units, every
  window day and genuine missing values. Outside flags remain true for an
  above/below carried baseline day even when its daily measurement is absent.
- Owned adapter correction keys the load chart by the existing request.ref;
  the unchanged load-settings guard now passes. Only the charts import row
  changed in the companion boundary metadata; no guard policy changed.
- Independent replay: 453 named observations (299 unique transformations),
  all exact native RED/restored GREEN; six additional reviewer faults caught,
  zero survivors. All 21 assertion sites, 276 assertion-parameter roles and
  184 chart nodes covered. Full-window description, ticks and mark geometry
  independently distinguish all six charts' first/last/both endpoint loss.
  The original 159 cases remain, with 25 appended cases and all old function
  ASTs preserved. No new implementation history is claimed for already
  correct forwarding; original feature-flag and native guard RED remain.
- Full restored original canonical pytest: 21828 passed / 44 expected skips,
  exit 0 in 576.22 s. Scoped recovery/charts/load-settings: 5428 passed;
  Ruff check/format (763 files), mypy (578 files) and diff clean. All 1958
  tracked byte/mtime entries, seven accepted 2.3 hashes and 1930 prior sealed
  artifacts preserved. Parent also verified 953 sealed review artifacts.
- Evidence: `/private/tmp/recovery-task-3.2-retry1-report.md`, sealed
  `recovery-task-3.2-retry1-evidence/`, independent
  `/private/tmp/recovery-review-3.2-retry1.md` and its raw package, and
  `/private/tmp/recovery-task-3.2-verification.md`/`.json`. No follow-up.
  Eleven of twenty-one mandatory leaves are accepted. Page/Engine and
  feature GO remain pending; the approved all-markless no-data exception
  remains. Commit/push, synchronize current main, then continue with 3.3.


### Task 3.3 accepted (2026-10-16)

- READY_FOR_REVIEW → independent APPROVED after two bounded test-only
  remediations → fresh controller VERIFIED. Pure Page part 1 renders the
  ordered frontmatter, banner/title, exact signal/sleep/other/load prose,
  relative assets and title-adjacent Garmin attribution. Four settled
  wellness-attribution names append without changing prior workout code.
- Numeric call checks bind each semantic occurrence and returned result;
  equal int/float/Decimal quantities are permitted. Discrete count/version
  subjects remain integral even when display precision masks a fractional
  change. Negative valid RHR bounds and all sixteen formed-zero sleep
  cases are pinned. Dates require ISO output; uncharted/generic Column
  names/labels stay unspecified. All earlier positive fixtures/scenarios
  and forty-nine workout-attribution nodes remain intact.
- Independent final 615 observations all sole intended native RED/restored
  GREEN: 599 normative plus 16 fixture preconditions, 217 IDs / 202 source
  states / 58 sites / 224 roles / 206 nodes. Eight additional reviewer faults
  caught/restored; 17 allowed families GREEN. Thirty-five unsupported old
  observations remain excluded history, with no sensitivity credit.
- Full original 22,033 passed / 44 expected skips, exit0 in 545.94 s; scope 5,682,
  fresh trace 255 and support 196 passed. Ruff check/format 765, mypy 580 and
  diff clean. Current 2,548-file implementer and 1,332-file review seals plus
  32,849 prior artifacts verified; 1,962 other repository snapshots preserved.
- Nineteen task contributions: 18 PINNED and one PRESERVED-ONLY (8.4 actual source-scale) through accepted View/charts, zero UNPINNED. Coverage/Method/
  References remain 3.4; writing remains 4.1; no feature GO. Twelve of 21
  mandatory leaves accepted. No follow-up.
- Evidence: `/private/tmp/recovery-task-3.3-round3-report.md`, its sealed
  `recovery-task-3.3-round3-evidence/final/`, independent
  `/private/tmp/recovery-review-3.3-round3.md` and raw package, and
  `/private/tmp/recovery-task-3.3-verification.md`/`.json`.

### 3.4 — Coverage, method, references and descriptive guard

Accepted after one bounded test-only remediation; no debug cycle used. Page
appends Coverage, Method and References and exports the prescribed private
`_FORBIDDEN_PHRASE_PATTERN` for its consumer. Method preserves each occurrence's
Citation locator; References deduplicates by citation key, in key order. A
legitimate first or last representative for a duplicate key is an ordinary
choice; the golden preserves this implementation's first representative.
Coverage identity is `(metric, source)`, and distinct citation keys remain
separate even when their displayed metadata is identical. Two appended literal
fixtures close the independently demonstrated metric-only and author-only
identity gaps without changing existing tests or correct production behavior.

Fresh review `/private/tmp/recovery-review-3.4-round2.md` APPROVED and parent
`/private/tmp/recovery-task-3.4-verification.md` VERIFIED: 317 normative native
RED/restored-GREEN observations plus two independent controls, 72 failed nodes /
21 frames, all sixteen added assertions observed, nine requirement families
PINNED, fourteen permitted-variant observations GREEN. Page254, scope1853 and
full original22095 passed/44 expected skips (exit0); Ruff765/mypy580 and diff
checks clean. All four submitted and seven protected hashes/mtimes match; four
immutable packages total2510 artifacts and their reports verified unchanged.
The only companion boundary change adds `fitdocs.citation` to Page's measured
import row; the existing guarded golden main() regenerated its appended output.
The six original section headings and every other accepted3.3 function, fixture,
helper, decorator and numeric/date/zero/range assertion remain intact. No
follow-ups were identified. Feature GO and remaining mandatory tasks remain open.

- 4.1 accepted after independent review and fresh parent completion gate: public series/history pipeline, live panel limit, report records, recovery-only atomic writes, foreign regular/nonregular occupants and symlink referents, known-only stale cleanup and byte idempotency. Guard regular files before any read so FIFOs remain foreign without blocking. Final full original: 22,188 passed / 44 expected skips; engine93, assigned scope2329, Ruff767/mypy582 clean.
- 4.1 fixture lesson: inspect metadata on every report return branch and the runtime files tuple; single-chart failures and one stale chart cannot pin multi-chart continuation or multiple-removal order. Seven appended cases closed all four independent review findings while preserving every old test byte. Fresh review replayed192 valid faults and three allowed variants; all316 normative assertion roles pinned. Exception-only regression/guard/fixture/reference credit stays separate. Parent gate: /private/tmp/recovery-task-4.1-verification.json; reports and all6,341 task/review artifacts sealed. CLI remains the sole intended production engine caller and is added by4.2.

- Post-4.1 integration checkpoint: rebased20commits onto HR main700b32e and immediately lease-pushed f513a1c2. Preserved both public API surfaces, confinement registration, mypy directories and HR12→13 history. Recovery is now CONTRACT_VERSION14/DOC_VERSION9/wikiAm9; HRAm8 stays intact. Only16 licensed metadata/pin/golden paths changed; declaration goldens regenerated by their sanctioned manual main. No scientific/runtime/CLI change.
- Fresh independent compatibility review and parent FIX gate: full24,264 passed/44expected skips, focused499, compatibility3447, Ruff794/mypy609; claimed2+own2 source faults cover13native roles, all restoredGREEN. Protected265production paths and archived proofs preserved. Evidence /private/tmp/recovery-post-4.1-rebase-verification.json. This closes only the early rebase/version portion of6.2; its checkbox remains open for final validation/build/installed smoke/CI and any later main drift. Seven mandatory leaves remain; CLI4.2 is next.


- 4.2 accepted after one bounded append-only test repair: standalone `fitdocs recovery --out/--methodology`, direct public engine call, standard SettingsError exit2, report fields/outcomes/reasons and report.failed finish; actual command registry15/Fifteen. All66 predecessor CLI functions remain exact source/AST, and only five owned paths changed before this plan note. No sibling command chains recovery; each archive-backed runtime test proves direct recovery on the same post-command root creates its page.
- CLI fixture lesson: a date emitted twice can pre-satisfy a global token assertion. Six appended cases separately pin the as-of record and both window endpoints, and preserve literal bracket/emoji root data in real engine errors. Chosen labels, spacing, punctuation, class prefixes and record ordering remain unspecified; three permitted variants each138 distinct nodes GREEN. Preserve existing fixtures and exact old test prefix.
- Fresh independent4.2 review APPROVED and parent completion VERIFIED:107 applied control invocations/102 distinct source-path states/171 intended native observations (145 normative,26 support), all40 native sites+five companion count assertions, six requirement families PINNED. Full original24,299 passed/44expected skips, exit0 in620.94s; scope128, runtime2, Ruff795/mypy610 clean. Current5 hash/mtime,277protected artifacts,66oldCLI functions and four sealed packages totaling2218 artifacts verified. Evidence /private/tmp/recovery-task-4.2-verification.json and /private/tmp/recovery-review-4.2-round2.md. No follow-ups;15/21 mandatory leaves accepted. Continue4.3; whole6.2/featureGO/mainlanding remain.


- 4.3 accepted with no remediation/debug: independent literal seven-module set from a nonempty recursive qualified-name scan and exact reverse engine-importer equality `{fitdocs.cli}`. The obsolete math-only CLI acceptance now expects rejection, preserving its existing empty-walk and CLI-import controls. Only boundarytest.py changed; all other definitions, module assignments, resolver limits, import rows/ranks and clock/network/facade policies remain unchanged. Group4 is complete;16/21 mandatory leaves accepted.
- Fresh independent review replayed21claimed states (18nativeRED/3permitted) plusfive own production faults: same-cardinality relocated module, nested package marker, same-cardinality importer replacement, package-relative import and nested keyword-relative dynamic import. All23 intended native failures and26restoredGREEN observations cover four new/changed sites; the two guard-support controls receive no production credit. Full original24,300 passed/44expectedskips exit0 in613.16s; boundary382/Recovery1802/Ruff795/mypy610/diffclean. Parent completion VERIFIEDcurrentboundary/278protected/229golden-relatedfiles/226sealedtask-reviewartifacts/prior2218CLIartifacts/exactASTscope. Evidence /private/tmp/recovery-task-4.3-verification.json and /private/tmp/recovery-review-4.3.md. No findings/followups; continue5.1Docs. Static access pins do not claim whole-program runtime call-graph or arbitrary computed-target evaluation.


- 5.1 accepted without remediation/debug: Recovery guide, index row, project URL, required-entry link and licensed README ownership/history additions; exactly six paths, no production/scientific/dependency/validator-policy changes. Guide facts follow the live command/page/METHODS, independently bound to named rows and relevant subsections. Source isolation is explicitly for rolling means/baselines, and absent daily points/bounds/mid have separate chart effects. Preserve both owned locations and the README published documentation URL.
- Fresh independent5.1 APPROVED and parent completion VERIFIED:178claimed+4own=182native assertion RED/restoredGREEN invocations across179distinct path/source states;9newassertsites+2existingrequired-entryRecoveryroles, all48newnodes+originalguard. Full original24,348passed/44expectedskips exit0 in638.16s; scope90/20.19s,Ruff796/mypy611/diffclean. Current6hash/size/mtime,279protected,228trackedgolden-related files and635+531sealedtask/review artifacts verified. One editable-build DNS setup attempt was excluded, followed by the original command with authorized cache/build access; no fixture/dependency workaround.
- Source and synthetic CLI audit verifies all nine method records, source-specific geometric means/ranges and identifier-only carry, attribution, all five report outcomes, help/written6charts+page/unchanged/empty/invalid behavior. Runtime substrate remains preserved from accepted prior tasks; no new primary-text/science claim. Evidence /private/tmp/recovery-task-5.1-verification.json and /private/tmp/recovery-review-5.1.md. No follow-ups;17/21 mandatory accepted. Continue5.2, then5.3/6.1/6.2/featureGO/mainlanding.

- 5.2 accepted without remediation/debug: conditional standalone Recovery guidance and executable fence after regen, approved package dependency documentation and Unreleased command/chart-kind/ownership entries. The routine pull/check fence, all old skill tests and HR instructions remain exact; all four retained changes are insertion-only. The reference-band description follows its live points-against-band semantics, and the present-x statement applies to the approved three kinds when genuine marks exist.
- Fresh independent review and parent completion gate verified70claimed+5own=75distinct applied faults, each native assertion RED/restoredGREEN; four new assertion sites/six nodes plus preserved routine-isolation and actual CLI-option-binding roles. The new Recovery fence also accepts the existing supported sh label (117GREEN/restored117). Full original24,354passed/44expectedskips exit0 in617.73s; canonical scope133,Ruff796/mypy611/diffclean. Current4hash/size/mtime,284protected and228golden-related files preserved; immutable report/raw-evidence seals checked. Evidence /private/tmp/recovery-task-5.2-verification.json and /private/tmp/recovery-review-5.2.md. No follow-ups;18/21mandatoryaccepted. Continue5.3, then6.1/6.2/featureGO/mainlanding.


- 5.3 accepted without remediation/debug: Recovery joins the offline list before check, runs last after query/dashboard refresh in the socket-guarded native case, and receives identical synthetic intervals deliveries through the real inbox drain in both configured/unconfigured roots. The optional staging keyword remains off by default; all old command rows/arguments, assertions, query tail, approval fields and amendment history are preserved. Connectors Amendment5 is appended without backfilling unrelated historical metadata. Group5 is complete;19/21mandatoryleavesaccepted.
- Fresh independent review and parent completion VERIFIED:48uniquelyclaimedtransformations+6own=54distinctstates,83intendednativefailed-nodeobservations/allrestoredGREEN,25currentassertionsites/34node-site roles includingall15new/changedsites. Expanded default-True/always-stage and wired-only controls cover all10oldcommandnodes and both roots. Actual swallowed socket/scriptedconnector calls, forwarding/drain, supportedmetric/value, absent-before/written-after pages and output/exit/exception parity discriminate; fixture reachability remains separate from production credit. The old socket-parity expression is logically subsumed on Recovery by the new strict-zero assertions, with no independent new claim for it.
- Full original24,357passed/44expectedskipsexit0 in683.05s;scope73/13.52s,nativecase1/4.35s,Ruff796/mypy611/diffclean. Final2019trackedentries,5current/288protected/228golden-related files and209+187outsideproofartifacts preserved. Both roots contain matching17/18files exceptsettings,oneworkout,same delivery/archive,normalized47bpm and identical8944-byteRecoverypages/SVGs. Evidence /private/tmp/recovery-task-5.3-verification.json and /private/tmp/recovery-review-5.3.md. No findings/follow-ups; continue6.1, then6.2/featureGO/mainlanding. Historicalsetup/static/audit-classifier issues are excluded from feature failure claims.

- 6.1 accepted without remediation/debug: real synthetic intervals/FIT inbox lifecycle, seven nontrivial outputs, unchanged second run/check, independent date/TZ roots, input metadata and nonvacuous recovery confinement registration. Two test paths only; all125 predecessor definitions/20 registry entries and guard policies preserved. Independent review APPROVED and controller TASK VERIFIED:97claimed+8own distinct states/111 native RED/restored GREEN observations, all28 new assertion sites and38 node-site roles. Full original24,371passed/44expectedskips, exit0 in639.10s; scope88, Ruff797/mypy612/diff clean. Evidence /private/tmp/recovery-task-6.1-verification.json and /private/tmp/recovery-review-6.1.md;520+3+536 outside artifacts and526 handoff files preserved. Twenty of21 mandatory leaves accepted.
- Necessary upstream prerequisite before6.2/FEATURE_GO: constant SDNN73 produces unrounded geometric mean72.99999999999999 and exposes shared linear tick collapse. Existing chart-kit queue2026-10-12-chart-kit-tick-tolerance-magnitude owns it; read-only debug RETRY_TASK/HIGH /private/tmp/recovery-scale-precision-debug.md. This accepted varied fixture does not repair it. Implement/review bounded shared linear precision fix with a genuine constant-data Recovery regression; direct clock/workaround cleanup remains queued.

- Necessary chart-kit LINEAR precision prerequisite accepted after one bounded fixture remediation: exact decimal-ladder construction and represented enclosure/cardinality preserve valid unequal HRV inputs, with no Recovery rounding/formatter fallback/global clock or log changes. The accepted E2E prefix remains intact; one appended constant73 pipeline case and one new focused module retain the crash. Two old cells parameters no longer assert the repaired non-enclosure defect; all old classification/clamp coverage remains.
- Fresh independent APPROVED and parent FIX VERIFIED: original real constant pipeline produces page+six populated SVGs; full24391passed/44expectedskips exit0 in684.80s; assigned5714/Ruff798/mypy613/diff clean. Union39 recorded observations represents33 distinct transformations (original32 records31states plus two new); duplicate fault selectors merged, plus two reviewer faults,145native failures/restoredGREEN. All18assertion sites89roles pinned. The one review gap was niced/exact endpoint coincidence; appending one unaligned parameter killed the actual bypass while preserving all prior cases.
- Precision evidence /private/tmp/recovery-scale-precision-verification.json and /private/tmp/recovery-scale-precision-review-remediation1.md;578outside sealed artifacts/current4/protected293/goldens228 preserved. Existing queue2026-10-12-chart-kit-tick-tolerance-magnitude updated with repaired linear portion and remaining direct clock/workaround cleanup; no duplicate item, no broad closure claim. Continue final6.2, featureGO/build/installed smoke/CI/main landing;20/21mandatory leaves accepted.

- 6.2 final reconciliation accepted without repository source edits: current main700b32e already integrated; full2021tracked bytes/mtime/mode/link metadata preserved. FinalCONTRACT14=main13+1, DOC9, wikiAm9 afterHR8, CLI15/Fifteen, kinds17, owned14/declared8 and writing21 preserve all peer histories/current-head pins/old entries. Eight declaration goldens and dashboard kinds block already exact; no regeneration or stale outgoing head pin required.
- Citations were transcribed by1.2 before implementation: four retained works remain PRIMARY_TEXT, Altini stays secondary-attestation-only and absent from governing records, baseline60 remains FitdocsChoice, Buchheit verified but unused. All nine live METHODS retain approved values and scopes; no late transcription, source upgrade or scientific change.
- Fresh independent6.2 APPROVED and parent TASK VERIFIED: fulloriginal24391passed/44expectedskips exit0 in751.38s, focused1154 plus Recovery confinement4; Ruff798/mypy613/diff clean. Forty-five audit checks plus nine reviewer checks passed, frozen1036runtime/verification paths unchanged;78+149outside artifacts exact. Exact reviewedHEAD7f733b7CI success run38985418391. Initial isolated fixture selection errors retained/excluded, corrected selection green; no fixture workaround. Evidence /private/tmp/recovery-task-6.2-verification.json and /private/tmp/recovery-review-6.2.md.
- All21mandatory leaves are accepted; optional6.3maintainer-data visual check remains unrun. Feature-level coverage/design/integration, canonical build, isolated installed-wheel first-usable smoke, final-head CI and main merge/push/cleanup remain the final run gates; no FEATURE_GO is claimed by this task note.
