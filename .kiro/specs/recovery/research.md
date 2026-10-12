# Research & Design Decisions — recovery

## Summary
- **Feature**: `recovery`
- **Discovery Scope**: New feature on an existing system (a new package, a
  new command, a new owned location, one new chart kind), with four
  amendments to shipped or specified features. Codebase-first discovery; no
  network was used (Phase 12 spec-batch rule), so every published-work
  citation below is from knowledge and is marked for verification.
- **Key Findings**:
  - The history computation is already consumed outside `history/` by the
    index producer `index/derived/load_series.py:186-235`
    (`read_history_inputs` → `compute_history` → `day_rows`); recovery
    follows exactly that path, so fitness, fatigue and form can never be
    computed a second way.
  - No registered chart kind draws daily points, a rolling-mean line and a
    normal-range band per source segment without joining two sources: `band`
    (`kit/kinds/band.py:407-460`) has one band and one centre line and joins
    consecutive rows of any provenance; `line` (`kinds/line.py:259-319`) has
    no band and at most 8 series. One new catalog kind (`reference-band`) is
    the smallest honest fix.
  - The history command is deliberately standalone (load-history Req 8.7,
    `cli.py:979-1006` "never chained onto sync, regen or load"). The brief
    says "mirror history", so recovery is a command, not a drain pass.
  - wellness-store's reader already exposes everything the baselines need:
    `WellnessSeries.by_source`, `.canonical`, `.values` (design.md § Seams 6).
    Only display labels for metrics are missing; one additive field
    (`MetricInfo.label`) avoids a second metric table in recovery. The
    controller folded that field into wellness-store's own spec (ruling R1,
    Step 3.5 round 1); recovery consumes it.

## Research Log

### The history computation and its consumers
- **Context**: Requirement 9 (fitness, fatigue and form through
  load-history's functions).
- **Sources Consulted**: `src/fitdocs/history/engine.py:203-271`
  (`read_history_inputs`, `compute_history`), `history/page.py:377-411`
  (`DayRow`, `day_rows`), `history/__init__.py` (`__all__` includes all
  three), `index/derived/load_series.py:186-235`, `cli.py:979-1006`.
- **Findings**:
  - `read_history_inputs(data_root)` reads `fitdocs.toml` once, projects
    `[history]` and `[load]`, and scans `workouts/*.md`; it raises
    `HistorySettingsError` / `LoadSettingsError` (both `SettingsError`).
  - `compute_history(inputs, methodology=)` returns `None` when no page
    records a load, raises `MethodologyConfigurationError` (a
    `SettingsError`, `engine.py:168`) when the methodology cannot be
    resolved, and otherwise returns `HistoryComputation(series, model,
    weeks, ...)`.
  - `day_rows(series, model, weeks)` yields one `DayRow` per span day with
    fitness, fatigue and form `None` on suppressed days — the same values
    the history chart and the `daily_load` index table carry.
  - The only importers of `fitdocs.history` outside the package are
    `cli.py:216`, `plans/{aggregate,placement,reconcile}.py` and
    `index/derived/load_series.py:8` (grep). The history boundary guard's
    reverse layer forbids only `load/`, `ingest/`, `render/views.py` and
    `sync.py` from importing it (`tests/history/test_boundary.py:588-640`),
    so a new importer under `recovery/` needs no history re-pin.
- **Implications**: recovery calls the same three functions, passes the
  athlete's `--methodology` through, maps `SettingsError` to the
  configuration exit exactly as `history_command` does, and never reads the
  history page.

### Chart kit and catalog capabilities
- **Context**: Requirements 4.1, 5.4, 6.2, 7.1, 8.1, 9.1, 16.
- **Sources Consulted**: `kit/__init__.py:12-46` (facade),
  `kit/schema.py` (`ChartRequest`, `KindSpec`, `MarkBound`),
  `kit/data.py` (`Column`, `ValueKind`), `kinds/{band,line,dual_axis,
  small_multiples,stacked_100,bar,calendar_heatmap}.py`, `kit/marks.py:59,
  88, 136` (`line_series`, `band_path`, `points`), `kit/theme.py:58-95`
  (`Shape`, `SeriesStyle`, `series_style`, `MAX_SERIES = 8`),
  `kit/layout.py:69-73` (`LegendEntry`), `kit/format.py:116`
  (`format_value`), chart-kit and chart-catalog `tasks.md` Implementation
  Notes.
- **Findings**:
  - Row bounds: `line` 2000 (`line.py:58`), `band` 1000 (`band.py:62`),
    `small-multiples` 12 panels / 2000 rows (`small_multiples.py:66-67`),
    `stacked-100` 400, `bar` 200.
  - `band` draws one band in `series_style(0)` and joins every placed row
    whose low and high are present (`band.py:330-366`): two sources on
    consecutive days would be joined — a silent splice (brief, Constraints).
  - `line` splits a series only where its y is absent; one colour per
    series, `max_series=8` — four quantities × two sources already fills it.
  - `small-multiples` draws one line per panel, one style, one shared or
    independent y scale; one y column (one unit) for all panels.
  - The x axis of the cartesian kinds keeps the exact data extent, so a
    chart spans the window only when it carries a row for the window's first
    and last day; a row with an x and an absent value is counted in the
    "Not drawn" note (`frame.not_drawn_note`, chart-catalog Notes A2).
  - The catalog's shared guarantees (chart-catalog Requirement 2) and its
    testing conventions (`CASES` with `typical` first, standard golden
    classes, `test_boundary.py` module tuple and rank matrix, budgets,
    `test_size_budget.py`'s 80,000-byte at-bound ceiling) are what a new
    kind must meet; the catalog contract test pins only a 16-name prefix
    (`tests/render/charts/kit/test_catalog_contract.py:90`), so appending a
    kind keeps it green.
  - `kit.format.format_value(value, column, *, with_unit=)` is the one
    formatter the charts use; the page reuses it so page text and chart
    labels agree (Requirement 12.4).
- **Implications**: one appended catalog kind, `reference-band`, built from
  existing marks (`band_path`, `line_series`, `points`, `shape_path`),
  with a `segment` channel that breaks and colours per source and a `flag`
  channel for marked days. Fitness, fatigue and form use `line`; other
  signals use `small-multiples` with one panel per (metric, source).

### Owned locations, declarations, confinement and the command lists
- **Context**: Requirements 13, 17, 18.
- **Sources Consulted**: `layout.py:104-166, 263-293`, `contract.py:328,
  799-822, 989-1002`, `declaration.py:278-310, 371-487, 538`,
  `history/engine.py:308-357` (foreign-occupant and atomic-write idioms),
  dashboards `design.md` § Storage (`ASSET_MARK`, write-if-different,
  stale-image removal), `tests/test_confinement.py:1209-1290`,
  `tests/connectors/test_e2e.py:320-332`,
  `tests/connectors/test_network_statements.py:667-670`, connectors
  `requirements.md:289` and its two amendments, `tech.md:44-48`,
  `tests/test_cli_skill.py:266`, `tests/query/test_cli_query.py:811`,
  `tests/test_layout.py:649, 863, 885`,
  `tests/index/derived/test_preserved.py:246`.
- **Findings**:
  - Owned paths and declared directories are append-only tuples; history's
    pair (`history/`, `history/assets/`) and its declaration branch are the
    exact precedent for a one-page generated location.
  - History writes its chart, then its page, with a module-local
    `GENERATED_PREFIX` marker line on the SVG and a foreign-occupant check
    per path; it always rewrites (mtime churn). Dashboards writes an asset
    only when its bytes differ — the churn rule Requirement 14.3 needs.
  - `ensure_declarations` iterates every declared directory, so a recovery
    run (like a history run) may refresh every `AGENTS.md`.
  - Two tests pin the CLI command count at 13 (dashboards takes it to 14);
    the no-network command list is pinned in `tech.md` by a tail phrase that
    dashboards keeps green by inserting before `check`.
- **Implications**: `recovery/` + `recovery/assets/` appended, a recovery
  declaration branch, `CONTRACT_VERSION` main + 1; the engine refuses a
  symlinked or non-directory location before refreshing declarations; files
  are written only when their bytes differ; `recovery` is inserted before
  `check` in the no-network lists.

### Baseline methods and citations
- **Context**: Requirements 3, 4, 11; brief: "The design picks and cites the
  exact windows and range multipliers. The research flagged the commonly
  quoted ±0.75 SD and 0.5 × SD as unverified."
- **Sources Consulted** (from knowledge; **none verified in this run**):
  - Plews DJ, Laursen PB, Stanley J, Kilding AE, Buchheit M. Training
    adaptation and heart rate variability in elite endurance athletes:
    opening the door to effective monitoring. *Sports Med.*
    2013;43(9):773-781. Confident of the work; it advocates the 7-day
    rolling average of the natural log of rMSSD and judging changes against
    a smallest worthwhile change. Locators unknown.
  - Plews DJ, Laursen PB, Kilding AE, Buchheit M. Evaluating training
    adaptation with heart-rate measures: a methodological comparison.
    *Int J Sports Physiol Perform.* 2013;8(6):688-691. Fairly confident;
    compares single-day and weekly-averaged ln rMSSD.
  - Plews DJ, Laursen PB, Le Meur Y, Hausswirth C, Kilding AE, Buchheit M.
    Monitoring training with heart-rate variability: how much compliance is
    needed for valid assessment? *Int J Sports Physiol Perform.*
    2014;9(5):783-790. Fairly confident of the work; its minimum number of
    recordings per week (recalled as three) is **unverified**.
  - Buchheit M. Monitoring training status with HR measures: do all roads
    lead to Rome? *Front Physiol.* 2014;5:73. Confident of the work; it
    discusses resting HR and HRV, weekly averaging and the smallest
    worthwhile change. Locators unknown.
  - Vesterinen V, et al. Individual endurance training prescription with
    heart rate variability. *Med Sci Sports Exerc.* 2016;48(7):1347-1354.
    Moderately confident; recalled as defining the individual normal range
    of the 7-day rolling RMSSD as the baseline mean ± 0.5 SD. **Unverified.**
  - Altini M, Plews DJ. What is behind changes in resting heart rate and
    heart rate variability? A large-scale analysis of longitudinal
    measurements acquired in free-living. *Sensors.* 2021;21(23):7932.
    Moderately confident of the work; whether it states HRV4Training's
    60-day normal-values window is **unverified**.
- **Findings**:
  - The maintainer's decisions fix the shape: a 7-day ln mean against a
    60-day normal range for HRV; resting HR and sleep against rolling
    baselines; days outside marked (roadmap Phase 12, Decisions).
  - The two multipliers the brief names (±0.75 SD, 0.5 × SD) cannot be
    settled without the primary texts. 0.5 × SD of the baseline is the
    smallest-worthwhile-change convention the Plews/Buchheit line of work
    is recalled as using, and under stationary daily values about one 7-day
    mean in five falls outside it (the 7-day mean's SD is about 0.38 of a
    day's), which marks notable weeks without marking most of them.
  - The project's citation discipline (load-history Req 2.4, 2.8;
    `fitdocs/citation.py`) already distinguishes a verified `Citation`
    from a `FitdocsChoice` and records `Departure`s, so an unverified
    source can be stated honestly without blocking the feature.
- **Implications**: every value is fixed by this design; task 1.1 (run by
  the controller or the maintainer, who have web access; implementers do
  not) verifies each candidate work at its primary text. A verified work
  becomes the constant's `Citation`; an unverified one is named in a
  `FitdocsChoice`'s `search_basis`; a contradiction becomes a `Departure`
  reported to the maintainer, never a silent change of value.

### wellness-store's seams
- **Context**: everything recovery reads.
- **Sources Consulted**: `.kiro/specs/wellness-store/design.md` § Seams for
  downstream specs (normative), § Model, § Series, § Facade.
- **Findings**: the facade exports `Metric`, `METRICS`, `MetricInfo`,
  `SeriesValue`, `WellnessSeries`, `read_series`, `SeriesReadError`;
  `WellnessSeries.values` is sorted by (day, metric, source) and carries
  `canonical`; an absent value has no line; the day-boundary rule makes the
  sleep of day D the night before a workout on D. `MetricInfo` has `unit`,
  `minimum`, `maximum`, `description` but no short label; source display
  names live only in the registry, which the facade does not export.
- **Implications**: no re-parse, no re-merge, no precedence of its own;
  sources are named by id (`garmin-export`, `apple-health`,
  `intervals-icu`) and origin token; one additive field,
  `MetricInfo.label`, owned by wellness-store, gives every consumer the
  same short labels.

## Architecture Pattern Evaluation

| Option | Description | Strengths | Risks / Limitations | Notes |
|--------|-------------|-----------|---------------------|-------|
| Command only (selected) | `fitdocs recovery`, like `fitdocs history` | Mirrors load-history Req 8.7; no new failure mode in the drain; churn only when asked | Page goes stale until the athlete or agent runs it | Skill tells the agent when to run it |
| Drain pass | Run after the drain and `regen` when the series changed | Always current | Contradicts "mirror history"; methodology errors would need a non-fatal path inside sync | Rejected |
| Both | Command plus a chained pass | Current and on demand | Two triggers, two report surfaces | Rejected (simplification) |
| Baselines in `fitdocs.recovery` (selected) | Pure module re-exported by a light package facade | One computation; importing it pulls in no render or history code | `fitdocs.recovery/__init__` must stay light (guarded) | workout-wellness imports it |
| Baselines as index table | Precompute in DuckDB | Queryable | Documents never read the index (Phase 10 rule); not needed by the page | Deferred (follow-up) |
| New catalog kind (selected) | `reference-band` | Honest per-source segments; reusable in dashboards | A kind's full test discipline | chart-catalog Amendment |
| Private renderer | SVG built inside recovery | Fast | Forbidden by the controller and Phase 11 | Rejected |

## Design Decisions

### Decision: compare the 7-day mean for both HRV and resting HR
- **Context**: the brief puts resting HR's "daily value against a rolling
  baseline and range" and HRV's "7-day ln mean against a 60-day normal
  range".
- **Alternatives Considered**: (1) mark a resting-HR day by its daily value;
  (2) mark both signals by their 7-day mean.
- **Selected Approach**: (2). The daily value is still drawn against the
  rolling mean and the range; the marked day is the one whose 7-day mean
  leaves the range.
- **Rationale**: a ±0.5 SD range would mark about 60 % of stationary daily
  values; one rule for both signals is easier to read; the weekly-averaging
  argument (Plews 2013 IJSPP; Buchheit 2014) applies to both — to verify.
- **Trade-offs**: a single very high resting-HR morning is drawn but not
  marked unless it moves the week.

### Decision: the baseline excludes day D; the rolling mean includes it
- **Context**: workout-wellness needs "the baseline as of the morning of D".
- **Selected Approach**: the baseline (mean, SD, range) of D is computed
  from D−60…D−1; the rolling mean from D−6…D. A value on day X can change
  only days X…X+60.
- **Rationale**: the range a day is judged against never contains the day
  itself; the block for a workout on D is final once D's own morning values
  are in, apart from late arrivals for the 60 days before D.

### Decision: shown source per day, carried across short gaps
- **Selected Approach**: the canonical source of the day; on a day with no
  value from any source, the source shown on the latest of the six days
  before it that had a canonical value (the rolling window), else none.
- **Rationale**: a single missing morning does not break the band; a week
  without data does; no value is ever carried, only which source's own
  rolling mean and range are drawn.

### Decision: metric labels live in wellness-store
- **Selected Approach**: `MetricInfo.label`, one short label per metric,
  used by the recovery page and by workout-wellness. First drafted as a
  recovery-carried amendment; the controller ruled (R1, Step 3.5 round 1)
  that wellness-store's own spec carries it, because wellness-store 1.1
  pins `METRICS` against a literal of its table and a later field would
  break pins that cannot be listed in advance.
- **Rationale**: a label table in recovery would be the "second metric
  list" the batch rules forbid.

## Synthesis

- **Generalization**: one `BaselineMethod` record parameterises every
  per-source computation (transform, windows, minimum counts, optional range
  multiple); HRV, resting HR and the six sleep signals are rows of one
  mapping, and the page, the morning-of block and the tests read the same
  mapping. One chart kind serves the three baselined signals and sleep.
- **Build vs adopt**: the statistics are a few lines of `math.fsum`/`sqrt`
  (stdlib; no `statistics` module, whose `stdev` is exact but slower and
  adds nothing); the history computation, the chart kit, the declaration and
  confinement machinery are adopted unchanged.
- **Simplification**: no settings table, no index table, no benchmark
  values, no long-term view, no source display-name amendment (ids are
  readable), a fixed chart-file set with removal of stale ones only.

## Risks & Mitigations
- Citations unverified in this run — task 1.1 verifies; unverified ones
  ship as `FitdocsChoice`; values never change silently.
- `math.log`/`math.exp` may differ in the last bit across C libraries —
  values are rounded for display and charts; goldens use fixtures away from
  rounding boundaries (the history model has the same exposure through
  `math.exp`).
- The new kind's at-bound golden may approach chart-kit's 80,000-byte
  ceiling — the bound is 1000 rows (the `band` precedent) and is measured at
  implementation; exceeding it is a stop-and-report.
- The recovery page goes stale until the command runs — the workouts skill
  tells the agent when to run it; `docs/recovery.md` says so.

## References
- `.kiro/specs/wellness-store/design.md` § Seams for downstream specs.
- `.kiro/specs/load-history/requirements.md` Req 2.4, 2.8, 2.11, 8.7.
- `.kiro/specs/chart-catalog/design.md` § Kinds, § Band; `tasks.md`
  Implementation Notes.
- `.kiro/specs/dashboards/design.md` § Storage (asset mark, write-if-
  different, stale-image removal).
- The six published works listed under "Baseline methods and citations",
  all to be verified by task 1.1.
