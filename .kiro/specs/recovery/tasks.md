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

## Shared source files

Each file below has more than one writer; its writers are sequential.

- `src/fitdocs/recovery/__init__.py`: 1.2 creates it docstring-only; 1.3
  adds the re-exports.
- `tests/recovery/builders.py`: 1.3 creates it (series builders); 3.1
  appends the workout-page builder; frozen afterwards.
- `tests/recovery/test_boundary.py`: 1.5 creates it (rank table over every
  design module, modules on disk checked); 4.3 adds the literal module-set
  pin and switches the reverse check to equality.
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

- [ ] 1. Foundation: citations, constants, baselines, boundary, location

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

- [ ] 1.3 Compute one source's rolling mean, baseline, range and position, and publish the facade
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

- [ ] 1.4 Choose the shown source and bound what a late value can change
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

- [ ] 1.5 Guard the recovery package's imports, clock, network and public surface
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

- [ ] 1.6 (P) Declare `recovery/`, its AGENTS.md and the next contract version (wiki-contract amendment)
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

- [ ] 2. The `reference-band` chart kind (chart-catalog Amendment 1)

- [ ] 2.1 (P) Draw values as points against a segmented reference band, with flagged rows marked, and register the kind
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

- [ ] 2.2 Pin the kind's listing, order and budget and record chart-catalog Amendment 1
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

- [ ] 3. The page model and its rendering

- [ ] 3.1 Build the page model from the series, the baselines and the history computation
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
  - _Requirements: 2.1, 2.2, 4.2, 4.3, 5.5, 5.6, 6.1, 6.3, 7.2, 7.3, 8.1, 8.2, 8.3, 8.4, 9.1, 9.5, 9.6, 12.5, 12.7, 12.8_

- [ ] 3.2 Draw every section's chart through the kit
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
  - _Depends: 2.1_
  - _Requirements: 2.2, 4.1, 5.4, 6.2, 6.4, 7.1, 8.1, 9.1, 12.6, 16.1_

- [ ] 3.3 Write the page's frontmatter, its attribution line and its signal, sleep, other-signal and load sections
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
  - _Requirements: 2.3, 4.2, 4.3, 5.5, 5.6, 6.1, 6.3, 7.2, 8.3, 8.4, 9.5, 9.6, 9.7, 12.1, 12.2, 12.3, 12.4, 12.7, 12.8_

- [ ] 3.4 Write the coverage, method and references sections and keep the page descriptive
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
  - _Requirements: 10.1, 10.2, 10.3, 11.1, 11.2, 11.3, 11.4, 11.5, 12.5_

- [ ] 4. The run, the command and the closed boundary

- [ ] 4.1 Read, compute, write and report a recovery run
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
  - _Requirements: 1.1, 1.3, 1.4, 1.5, 1.6, 1.7, 9.2, 9.3, 9.4, 13.4, 13.5, 13.6, 14.1, 14.3_

- [ ] 4.2 Add the `fitdocs recovery` command
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

- [ ] 4.3 Close the boundary guard now that every module exists
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

- [ ] 5. Documentation, the skill, and the network statements

- [ ] 5.1 (P) Write the recovery guide and link it
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

- [ ] 5.2 Teach the workouts skill when to run recovery and record the release
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

- [ ] 5.3 (P) Name `recovery` among the commands that make no connector request (connectors amendment)
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

- [ ] 6.1 End-to-end, determinism, offline and confinement
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

- [ ] 6.2 Rebase, transcribe late citations, re-derive the version constants and validate the whole
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
