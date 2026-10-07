# Implementation Plan

## Upstream Prerequisites

- **`analytics-index` is merged on `main`.** This plan registers producers
  through its seam and reads its public pieces:
  - `fitdocs.index.producer` (`PageComputed`, `CorpusSnapshot`, `CorpusPage`,
    `CorpusLeftOut`, `Rows`, the three protocols);
  - `fitdocs.index.schema` (`ColumnSpec`, `TableSpec`, `ColumnType`,
    `SCHEMA_VERSION`, `resolve_tables`);
  - `fitdocs.index.registry`, `fitdocs.index.corpus.scan_workout_pages` and
    `fitdocs.index.corpus.corpus_snapshot` (the one snapshot builder),
    `fitdocs.index.fingerprint.athlete_fingerprint`,
    `fitdocs.index.build.run_index_command`,
    `fitdocs.index.refresh.refresh_after_command`,
    `fitdocs.index.handoff.HandoffCollector`,
    `fitdocs.index.location.resolve_index_location`, the store's facade
    (`open_index`, `read_bookkeeping`), `fitdocs.sync.sync`'s `on_rendered`
    parameter, `tests/index/conftest.py` (its `core_registry` fixture
    included) and `tests/index/_helpers.py`.

  A task that finds any of those shaped differently from
  `analytics-index/design.md` stops and reports rather than adapting.
- **The sibling `analytics-query`** may land before or after this plan. It
  never changes the schema. Where its work and this plan's meet (the three
  bounded read-side files of Cross-spec shared files), task 6.2 decides by
  what is on `main` at the time, and task 4.1 knows which of its tests go
  red in between.
- `main` also carries what the seams extract from: `history/engine.py`
  `run_history` (`:288-462`), `plans/engine.py` `run_plan` (`:456-577`),
  `plans/reconcile.py` (`:113-228`). A task that finds them restructured stops
  and reports.

**Hard rules for every task**

- **One computation, two projections.** No producer computes a load series,
  a model value, an in-force benchmark, a match, a state or a mesocycle load
  itself. It calls the engine seam. A task that cannot get a value from an
  engine stops and reports.
- **Engines keep their behaviour.** `fitdocs history`, `fitdocs plan`, every
  chained plan pass and `fitdocs derive-benchmarks` write the same bytes and
  report the same outcomes. The history golden (`tests/history/golden/`), the
  plan goldens (`tests/plans/golden/`) and the rendering goldens
  (`tests/render/golden_docs/`) stay byte-identical: `git diff --stat` on them
  is empty at every task.
- **No producer writes, reads the clock, opens the network or imports
  `duckdb`.** Tests pass `today` explicitly, through 1.2's helpers; no test
  reads the clock. A test that must run a CLI command (5.4) monkeypatches
  `fitdocs.cli._today` to the fixture's `TODAY`, which is not the real date.
- **Absent is `None`, then `NULL`.** The one stated exception is the history
  engine's own `0.0` recorded load on a day without load (design § Data
  Models, `daily_load.recorded_load`), held as the engine holds it.
- **No personal data.** Fixtures are synthetic: hand-written frontmatter pages
  and plan sources, and `.fit` files from `tests/fixtures/builder.py` and
  `tests/fixtures/merge.py`. No task reads the real data root; 6.4 is the
  maintainer's alone.
- **No DuckDB outside the facade.** Tests reach the index only through
  `analytics-index`'s store facade. No test executes `INSTALL`, `LOAD` or
  `ATTACH`, or names a URL in SQL.
- **Engine references run on copies.** A test that runs `run_history`,
  `run_reconcile` or `run_plan` as the reference runs it on a
  `shutil.copytree` copy of the fixture root, because those commands write
  (pages, `AGENTS.md` declarations) and a write would move the inputs the
  producer under test reads.
- **Mutations run through `uv run pytest` only** (`change-protocol.md`,
  § Fixture Discrimination). Each named mutation is applied, observed red,
  reverted, observed green, and recorded in the task's Implementation Notes.
  Revert by restoring a `cp` of the file taken before the mutation, never
  with `git checkout -- <path>`, `git stash` or `git reset --hard`. A task that
  cannot make a listed mutation red stops and reports it UNPINNED rather than
  weakening the assertion. Before submitting, run the prose-claim grep of
  `change-protocol.md` over the changed test files and re-run or delete every
  surviving claim.
- **Shell safety.** Never `rm -rf`, `git init`, `git reset --hard` or
  `git checkout -- <path>`. Never chain a destructive command after `cd`.
- **Types and lint.** Every task type-checks the modules it creates or changes
  with `uv run mypy <paths>`, and runs `uv run ruff check` and
  `uv run ruff format --check` on its changed files. Task 6.3 registers the new
  test modules in `pyproject.toml`'s mypy `files` list, so parallel tasks never
  share `pyproject.toml`.
- **Stop and report** on any need for: a frontmatter key, a document change,
  a new write location, a runtime dependency, a change to `analytics-index`'s
  pass, store or seam, or a change to what an engine computes.

## Shared source files

Each file below has more than one writer in this plan. Its writers are
sequential: never two of them `(P)` at once.

- `tests/test_public_api.py`: 2.2 (the history surface pin), then 2.3 (the
  plans surface pin). That shared file is why 2.3 is not `(P)` with 2.2.
- `src/fitdocs/index/derived/__init__.py`, `tests/index/derived/__init__.py`,
  `tests/index/derived/conftest.py` and `tests/index/derived/test_fixtures.py`:
  1.2 only. Later tasks import the conftest's fixture builder and helpers and
  never edit them; a missing fixture or helper is a stop-and-report.
- `src/fitdocs/index/derived/inputs.py`: 1.3 only.
- `src/fitdocs/index/registry.py`, `src/fitdocs/index/schema.py`,
  `tests/index/test_schema.py` and `tests/index/test_schema_version.py`: 4.1
  only (and 6.3's re-pin after the final rebase, when a sibling advanced the
  version first).
- `tests/test_confinement.py`: 5.4 only.
- `pyproject.toml`: 6.3 only.
- `CHANGELOG.md`, `.kiro/steering/structure.md`,
  `.kiro/specs/fit-ingest/requirements.md`, `.kiro/specs/fit-ingest/spec.json`
  and `.kiro/steering/roadmap.md`: 6.1 only.

## Cross-spec shared files

Each file below is shared with `analytics-index` (already landed) or the
sibling `analytics-query`. Writers append an entry, a row or a block, and
never rewrite or reorder another spec's. **On rebase, keep both.**

- **`src/fitdocs/index/registry.py`**: the three producer tuples. This plan
  appends `MEAN_MAX_PRODUCER` to `COMPUTED_PRODUCERS` and its three corpus
  producers to `CORPUS_PRODUCERS`; the core producers stay first.
  **Append-only. Owner: analytics-index.**
- **`src/fitdocs/index/schema.py` `SCHEMA_VERSION`, with
  `tests/index/test_schema_version.py` `_DIGESTS_BY_VERSION`.** This plan
  advances the version to `main`'s value plus one and appends its digest.
  `analytics-query` never edits either. If another schema-changing lander
  reaches `main` first, this plan re-pins from `main + 1` (task 6.3).
  **Append-only map.**
- **`tests/index/test_schema.py`**, the exact registered-table-set pin (13
  names after analytics-index): this plan appends its eleven names.
  **Append-only. Owner: analytics-index.**
- **`tests/test_confinement.py`** (`WRITING_ENTRY_POINTS`): this plan appends
  `EntryPoint(id="index-derived", …)`. **Append-only. Siblings:
  analytics-index (the `index` and `sync-with-index` entries and the resolved
  index directory), analytics-query (one standalone test that `query` writes
  nothing outside its spill directory).**
- **`CHANGELOG.md` `[Unreleased]`**: append under the existing `### Added`
  heading; create it only if absent. **Siblings: both.**
- **`.kiro/steering/structure.md`**, the `index` dependency-direction sentence:
  this plan appends its derived-producers clause. **Siblings: analytics-index
  (the sentence), analytics-query (its package's line).**
- **`pyproject.toml`'s mypy `files` list.** **Append-only. Siblings: both.**
- **The second lander's three bounded read-side files** (owner:
  analytics-query; its design § Out of Boundary and its Cross-spec shared
  files state the same rule). Whichever of `analytics-query` and
  `analytics-derived` lands second touches exactly these three, and nothing
  else on the read side. Here that is task 6.2, and only when
  `analytics-query` is on `main` when 6.2 runs; otherwise `analytics-query`'s
  task 7.3 does it at its landing.
  - **The generated schema-reference block in `docs/analytics.md`**, between
    `<!-- schema-reference:start -->` and `<!-- schema-reference:end -->`,
    regenerated with `uv run python -m tests.query.test_docs_analytics`.
  - **The worked examples in `src/fitdocs/skills/fitdocs-analytics/SKILL.md`**:
    four H3s under `Worked examples`, each with one `sql` fence, one per
    derived producer (`derived.mean_max`, `derived.load_series`,
    `derived.benchmarks`, `derived.blocks`). The core examples are not
    edited.
  - **`derived_inputs()` in `tests/query/conftest.py`**, the append point
    analytics-query's task 1.3 creates: it returns `DerivedInputs(files=…,
    athlete_toml=…)` (`tests/query/_helpers.py`), which `indexed_root` writes
    before `fitdocs sync`. This plan fills it with plan sources and a
    `[benchmarks]` table.
- **`tests/query/test_docs_analytics.py` and
  `tests/query/test_skill_examples.py`** (owner: analytics-query; this plan
  never edits either). If `analytics-query` is on `main` when this plan is
  implemented, registering the derived producers (task 4.1) turns these two
  red: the docs block no longer equals the live schema, and four non-core
  producers have no worked example. **They are the only tests expected red,
  from 4.1 until task 6.2 turns them green.** Any other red test is a
  stop-and-report (task 4.1). If `analytics-query` is not on `main`, nothing
  here applies.
- **`.kiro/steering/roadmap.md`**, the Phase 10 Specs and Existing Spec Updates
  ticks (task 6.1).

Not touched by this plan, though shared among the siblings: `src/fitdocs/cli.py`
and its command count, the no-network command list, `_INDEX_IMPORTERS`
(the derived package lives inside `fitdocs.index`, which needs no entry),
`PACKAGED_SKILLS`, the store facade, `docs/ownership-contract.md` and
`CONTRACT_VERSION` (no new write location), and `tests/conftest.py`'s
index-isolation fixture (used as is). `tests/index/conftest.py`, its
`core_registry` fixture included, is analytics-index's and is only imported
from here.

## Test File Ownership

- `tests/metrics/test_mean_max_sources.py`: **1.1**.
- `tests/index/derived/__init__.py`, `tests/index/derived/conftest.py`
  (the fixture root and the shared index helpers) and
  `tests/index/derived/test_fixtures.py`: **1.2**.
- `tests/index/derived/test_inputs.py`: **1.3**.
- `tests/metrics/test_mean_max.py`: **2.1**.
- `tests/history/test_compute_seam.py` and the `_HISTORY_SURFACE` section of
  `tests/test_public_api.py`: **2.2**.
- `tests/plans/test_resolve_seam.py` and the plans surface section of
  `tests/test_public_api.py`: **2.3**.
- `tests/index/derived/test_mean_max_producer.py`: **3.1**.
- `tests/index/derived/test_load_series_producer.py`: **3.2**.
- `tests/index/derived/test_benchmark_producer.py`: **3.3**.
- `tests/index/derived/test_block_producer.py`: **3.4**.
- `tests/index/derived/test_registration.py`, the table-set pin in
  `tests/index/test_schema.py` and `tests/index/test_schema_version.py`:
  **4.1**.
- `tests/index/derived/test_boundary.py`: **4.2**.
- `tests/index/derived/test_refresh.py`: **5.1**.
- `tests/index/derived/test_determinism.py`: **5.2**.
- `tests/index/derived/test_composed_and_upgrade.py`: **5.3**.
- `tests/test_confinement.py` (the `index-derived` entry) and
  `tests/index/derived/test_preserved.py`: **5.4**.
- `tests/index/derived/test_published.py`: **6.1**.
- The `derived_inputs()` section of `tests/query/conftest.py`
  (analytics-query's file): **6.2**, and only when `analytics-query` is on
  `main` (Cross-spec shared files).

---

- [x] 1. Foundation: the best-effort records, the derived package, its fixtures and its input digests

- [x] 1.1 Record the duration set and the maximum step as fitdocs's own choices
  - **The records module**, per design.md § MeanMaxRecords: two `FitdocsChoice`
    records (durations, maximum step), the 28 duration `CitedConstant`s in
    ascending order each sourced by the durations choice, the maximum step at
    5.0 seconds sourced by its choice, and the collection of all 29. It holds
    no arithmetic and imports only `fitdocs.citation`.
  - **The search basis is a search actually run.** Before writing
    `search_basis`, search for a published work that defines a standard
    best-effort duration set or a rule for pauses in a mean-maximal curve. When
    a live search tool is available, record the queries run and what each
    source found; when none is, say so plainly, as `NP_MIN_SPAN_CHOICE` does.
    If a published work turns out to define either value, stop and report:
    Req 15.1, not 15.8, would then govern it.
  - **Justifications** state the design's reasons in full sentences (the
    ladder, the durations fitdocs's own threshold derivations name, why the
    step differs from `compose/stretches.py`'s one second). `measurement` stays
    `None`.
  - **Tests** (`tests/metrics/test_mean_max_sources.py`):
    - exactly 28 durations, strictly ascending, first 1 and last 21600, each
      value pinned by literal;
    - every duration's source is the durations choice by identity, and the
      step's is the step choice by identity;
    - the collection equals the module-level `CitedConstant`s by identity, with
      unique names;
    - both choices carry a non-empty justification and search basis, and the
      module holds no `Citation`;
    - `metrics/sources.py`'s `CONSTANT_SOURCES` and its pinned counts are
      untouched (its own suite stays green unchanged);
    - `docs/reference` appears nowhere in the module.
  - **Mutations:** drop one duration (the count pin reds); swap two durations
    (the ascending pin reds); source one duration from the step choice (the
    identity pin reds); blank the step's justification; add a stray
    module-level `CitedConstant` outside the collection.
  - **Observable:** `uv run pytest tests/metrics/test_mean_max_sources.py
    tests/metrics/test_sources.py` is green and mypy is clean on the module.
  - _Requirements: 2.1, 2.2, 2.7_

- [x] 1.2 Create the derived package, the derived fixture root and the shared index helpers
  - **Markers.** Create `fitdocs.index.derived` (its docstring states the four
    producers and the imports they may use, design.md § Allowed Dependencies;
    it imports nothing) and the `tests/index/derived` test package, so the
    parallel tasks of group 3 only add modules.
  - **The derived fixture root** (`tests/index/derived/conftest.py`), one
    builder with keyword switches, written from synthetic text only, with a
    fixed `TODAY` that is not the real date:
    - `fitdocs.toml`, with a switch for `[history].methodology` (configured
      or not) and a coverage threshold that suppresses exactly one week;
    - frontmatter-only workout pages, each with `type`, `date`, `sport` and a
      `sources` list naming an archive reference whose file is absent (so the
      index holds the page without computed values): loads under two
      methodologies with pairwise-distinct values; two loaded pages on one
      day; a page without a load; a page with no `sources` at all, carrying a
      load (left out by the index, counted by history);
    - `athlete.toml` at the current profile version with tiered benchmarks:
      a Ride FTP whose `applies_from` precedes an earlier-measured entry's (so
      "latest `applies_from` on or before the day" and the profile's rule
      disagree on a stated day); a Run FTP whose dates interleave with the
      Ride FTP's (so grouping by kind alone merges two disciplines that the
      profile keeps apart); a Run LTHR; an athlete-wide maximum heart rate; one
      derived entry with a full `source` table; and a flat top-level
      `ftp_watts` whose value equals no benchmark value;
    - a valid plan source (copying the grammar of `tests/plans/fixtures/`)
      whose rows reach matched (exact, absorbed and ambiguous), overridden
      with one missing stem, skipped, not logged and upcoming relative to
      `TODAY`, with an unplanned page in a mesocycle window and a matched page
      that has no `sources`; and an invalid second source;
    - a switch adding real composed pages: the builder's run with power, heart
      rate and speed, and the `merge.py` ride pair, as source files for
      `sync_with_handoff` below.
  - **Shared helpers**, in the same conftest, each taking `today` explicitly
    and reaching DuckDB only through `analytics-index`'s public functions:
    - `snapshot_of(root, *, today)`: `corpus_snapshot(root,
      scan_workout_pages(root), today=today,
      athlete_fingerprint=athlete_fingerprint(<the root's athlete inputs>),
      held=…)`, analytics-index's one snapshot builder; the helper never
      assembles a `CorpusSnapshot` by hand. `held` is `None` while the test's
      isolated index directory holds no `index.duckdb`, and
      `frozenset(bookkeeping.pages)` from `read_bookkeeping` on a read-only
      `open_index` facade connection once `build_index` has built one, so it
      reproduces the snapshot the refresh passes to the producers;
    - `build_index(root, *, today, rebuild=False)`: `run_index_command` with
      `environ` naming the test's isolated `FITDOCS_INDEX_DIR`, a nonexistent
      `home`, the root's athlete inputs and `progress=None`;
    - `refresh(root, *, today, handoff=None)`: `refresh_after_command` with the
      same location;
    - `read_table(root, name)`: every row of a table, `ORDER BY ALL`, through a
      read-only `open_index` facade connection;
    - `sync_with_handoff(root, source_dir, *, today)`: the engine's
      `fitdocs.sync.sync(..., on_rendered=collector.add)` with a fresh
      `HandoffCollector`, a fixed time zone and an offline tile source (as
      `tests/test_identity_e2e.py:63-77` builds them), then `refresh(root,
      today=today, handoff=collector)`. It asserts the refresh outcome is
      REFRESHED and that every page the sync wrote is among the pages added
      or updated, so a call over a root with no index fails loudly instead of
      returning NOT_BUILT.
  - **Self-tests** (`tests/index/derived/test_fixtures.py`), proving each
    property later tasks rely on is present rather than assumed, using public
    commands on copies:
    - `run_history` over the root with a methodology requested writes a page
      whose weekly table shows exactly one suppressed week; with none
      configured it raises `MethodologyConfigurationError` (two
      methodologies);
    - `run_reconcile(copy, today=TODAY)` reaches all five row states and all
      three confidences, reports one missing override stem and at least one
      unplanned page;
    - `scan_workout_pages` leaves out the no-`sources` page, and with no
      index `snapshot_of` lists it in `left_out` with its document
      fingerprint and every other workout page in `pages`;
    - on the stated day, the profile's `applicable` and the naive "latest
      `applies_from`" rule give different Ride FTP entries, and
      `applicable(FTP, Ride, d)` and `applicable(FTP, Run, d)` give different
      values;
    - the composed switch's ride-pair base file alone records no heart rate;
    - `build_index` writes `index.duckdb` inside the isolated directory and
      nothing under the real HOME; `read_table(root, "pages")` returns the
      held pages;
    - a test-local corpus producer, monkeypatched into the registry tuple,
      records the `today` that `refresh` and `build_index` pass, and it equals
      `TODAY`; the whole snapshot it records during a `refresh` equals
      `snapshot_of(root, today=TODAY)` taken right after it;
    - with `build_index` run first, `sync_with_handoff` reports REFRESHED with
      the synced pages added, and a spy on `derive_page` shows no
      re-derivation for them; over a root with no index it raises on the
      NOT_BUILT outcome.
  - **Mutations** (each reds its self-test): remove the no-`sources` page;
    move the retroactive Ride FTP so the two rules agree; give the Run FTP the
    Ride FTP's dates and values; date the upcoming row before `TODAY`; make
    `refresh` pass `date.today()` instead of `today`; drop `on_rendered` from
    `sync_with_handoff`; make `snapshot_of` pass `athlete_fingerprint(None)`
    (the snapshot-equality self-test reds).
  - **Observable:** `uv run pytest tests/index/derived/test_fixtures.py` is
    green; the root's pages and benchmark entries are listed in Implementation
    Notes with their roles; nothing outside `tests/index/derived/` and the
    package marker changed.
  - _Requirements: 7.1, 7.5_

- [x] 1.3 Digest exactly the files a corpus producer reads
  - **The inputs module**, per design.md § DerivedInputs: file digests with
    markers for absent, directory, symlink and unreadable entries; the
    workouts digest over the snapshot's `pages` and `left_out` together, by
    `(path, document_fingerprint)`, reading no file and globbing nothing; the
    settings digest; the canonical-JSON digest; the path-to-page-key map.
  - **Why the snapshot is enough**, stated in the module docstring with these
    citations: history's `scan_documents`
    (`src/fitdocs/history/documents.py:197-200`) and the plan corpus's
    `scan_corpus` (`src/fitdocs/plans/corpus.py:184-187`) read
    `sorted(workouts/*.md)` through `docio.read_frontmatter` and keep a file
    only when `is_workout_document` holds. analytics-index's
    `scan_workout_pages` reads the same glob through `docio.read_document`,
    to which `read_frontmatter` delegates, keeps the same set, and
    `corpus_snapshot` lists each such page exactly once in `pages` or
    `left_out`. A file in neither (`AGENTS.md`, a non-workout page, a
    symlink, an unreadable or fence-less file) is read by neither engine, and
    a file entering or leaving the set adds or drops an entry.
  - **Tests** (`tests/index/derived/test_inputs.py`), each digest computed
    from `snapshot_of` on a root with no index, before and after a single
    change, with the starting digests asserted equal on an unchanged repeat
    first:
    - a one-byte change to a held page, to the left-out no-`sources` page
      (asserted in `left_out` first), to `fitdocs.toml` and to `athlete.toml`
      each moves exactly the digests that cover it; adding and removing a
      workout page each move the workouts digest;
    - a one-byte change to `workouts/AGENTS.md` and to a non-workout `.md`
      page in `workouts/` (a `type` other than the workout type), each
      asserted present on disk and absent from the snapshot first, a file
      outside `workouts/` and a non-`.md` file in it move nothing;
    - two snapshots of one scan, built with `corpus_snapshot` and `held=None`
      and with a `held` set lacking one scanned key (that page asserted in
      `left_out` first), give equal workouts digests and different
      `page_keys`;
    - `file_digest` of an absent path, a symlink, a directory and an
      unreadable file (`chmod 000`, skipped as root) gives four distinct
      markers and never raises;
    - `page_keys` maps every path of `snapshot.pages` and omits every path of
      `snapshot.left_out`.
  - **Mutations:** digest `pages` only, dropping `left_out` (the left-out
    change reds); glob `workouts/*.md` again and fold each file not in
    `pages` in by `file_digest` (the `AGENTS.md` pin reds); digest `pages` and
    `left_out` as two separate lists (the held-only difference pin reds); let
    an unreadable file raise (the never-raise pin reds); fold `fitdocs.toml`
    into the workouts digest (the separation pin reds); digest `pages` entries
    by `page_key` instead of `document_fingerprint` (the one-byte held-page
    change reds).
  - **Observable:** the inputs tests are green and the module imports only
    `fitdocs.index.producer`, `fitdocs.layout` and the standard library.
  - _Requirements: 7.1, 8.1, 8.2, 8.3, 8.6_
  - _Depends: 1.2_

- [x] 2. The best-effort computation and the engine seams

- [x] 2.1 (P) Compute best efforts under the stated continuity rule
  - **The rule module**, per design.md § MeanMaxRule: the three channels, the
    point type, the duration accessor and the curve function; recorded finite
    values only; stretches cut at a step greater than the maximum step; the
    one-second grid per stretch holding the latest recorded value; windows
    inside one stretch; the highest mean with the earliest window on a tie;
    the duration set and step read from the records at call time.
  - **Tests** (`tests/metrics/test_mean_max.py`), against a naive reference
    written in the test (every window enumerated, explicit hold), on
    hand-built `Samples` with pairwise-distinct values:
    - a pause longer than the step, where a window spanning it would score
      higher than any inside a stretch;
    - a step exactly equal to the step continues and one second more breaks;
    - a heart-rate dropout longer than the step splits heart rate only, with
      power continuous across it;
    - recorded zeros lower a mean; `None` is never zero; NaN speed is
      unrecorded;
    - two equal best windows give the earlier start;
    - irregular 3-second steps hold the earlier value;
    - a 1 Hz recording of N samples supports N seconds and not N + 1;
    - one point per duration, ascending, `None` past the longest stretch;
    - **the records drive the result**: patching the step record smaller splits
      a fixture's stretch, and patching the durations record changes the
      returned durations;
    - **literal scan** of the rule module: only `0` and `1` occur, with a
      positive control that the walk read the module.
  - **Mutations:** drop the stretch cut; `>` to `>=` at the step; stretch on
    all-channel steps; map `None` to 0; drop the finite check; take the last
    maximal window; take the next sample on the grid; build the grid without
    `+ 1`; inline `5.0` for the step (the scan and the patch test both red);
    bind the durations at import (the patch test reds).
  - **Observable:** `uv run pytest tests/metrics/test_mean_max.py` is green;
    the module imports only `fitdocs.model`, the records module and the
    standard library.
  - _Requirements: 1.3, 1.6, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8_
  - _Boundary: MeanMaxRule_
  - _Depends: 1.1_

- [x] 2.2 (P) Expose history's computation without its writes
  - **The history seam**, per design.md § HistorySeam: the inputs and
    computation types, `read_history_inputs`, `observed_methodologies` and
    `compute_history` in `engine.py`, which `run_history` composes; `DayRow`
    and `day_rows` in `page.py`, deciding suppression by calling the existing
    `_suppressed_day_indices`. That helper and `_build_chart` keep their names,
    signatures and bodies. The seven names are appended to
    `fitdocs.history.__all__` and `_HISTORY_SURFACE` with their defining
    submodules.
  - **Tests** (`tests/history/test_compute_seam.py`), on a local fixture with
    two methodologies, one suppressed week and a load-less day:
    - the weekly table parsed from the page `run_history` writes (on a copy)
      equals `compute_history`'s weekly rows formatted as the page formats
      them, for a requested methodology and for the configured default;
    - `day_rows` returns `None` fitness, fatigue and form exactly on the days
      of suppressed weeks, with one suppressed and one unsuppressed day
      asserted first, and its values elsewhere equal the model's;
    - `compute_history` returns `None` for an archive with no load, and raises
      `MethodologyConfigurationError` exactly where `run_history` does;
    - `observed_methodologies` is sorted and distinct.
  - **Preservation:** the history golden, `tests/history/` and
    `tests/test_history_e2e.py` pass with no file of theirs edited, docstrings
    included (`tests/history/test_page.py:981-1046` and
    `tests/test_history_e2e.py:18, 337` name `_suppressed_day_indices`, which
    stays); the module import targets pinned in
    `tests/history/test_boundary.py` are unchanged;
    `tests/load/test_settings.py::test_load_load_settings_is_called_from_exactly_the_licensed_modules`
    passes unchanged.
  - **Cross-year fixture.** The seam fixture's series spans an ISO-year
    boundary with week 1 of one year suppressed and week 1 of the other not
    (as `tests/test_history_e2e.py:328-390` builds it), asserted before the
    `day_rows` checks.
  - **Mutations:** `day_rows` ignores `_suppressed_day_indices` (the seam
    test reds); key `_suppressed_day_indices` by ISO week alone (the seam
    test's cross-year case and
    `tests/test_history_e2e.py::test_suppressed_band_keys_by_iso_year_not_week_number_alone`
    red together); move the empty-archive check
    after methodology selection (the empty-archive pin reds); omit one
    appended name from `__all__` (the surface pin reds).
  - **Observable:** the seam tests, the history suites and
    `tests/test_public_api.py` are green; `git diff --stat
    tests/history tests/test_history_e2e.py` shows only the new seam test.
  - _Requirements: 3.2, 3.3, 3.4, 4.1, 4.2, 7.3_
  - _Boundary: HistorySeam_

- [x] 2.3 Expose the plan pass's resolution without its writes
  - **The plans seam**, per design.md § PlanSeam: `ParsedSource`,
    `PlanSources`, `read_plan_sources` (the settings, directory, discovery and
    parse half of `run_plan`, which now calls it), `Reconciler.reconcile`
    (which `__call__` uses), `PlanResolution` and `resolve_plans`. The five
    names are appended to `fitdocs.plans.__all__` and the plans surface pin.
    Not `(P)` with 2.2: both edit `tests/test_public_api.py`.
  - **Tests** (`tests/plans/test_resolve_seam.py`), on the reconcile fixtures
    of `tests/plans/`:
    - `resolve_plans(root, today=d).blocks` equals `run_reconcile(copy,
      today=d).blocks` for two dates that flip a row between not logged and
      upcoming;
    - `read_plan_sources` gives the same valid and invalid split, problems and
      report paths as `run_plan`'s outcomes;
    - an absent, unconfigured plan directory gives `present` false and no
      sources; a configured, absent one raises `PlanSettingsError` as
      `run_plan` does;
    - `resolve_plans` writes nothing: every file's bytes and `mtime_ns` under
      the root, `blocks/` and every `AGENTS.md` included, are unchanged, with
      `run_plan` on a copy asserted first to write there;
    - a root with no valid block never scans the corpus (a spy on
      `scan_corpus`).
  - **Preservation:** the plan goldens, `tests/plans/`,
    `tests/test_plan_e2e.py` and `tests/test_cli_reconcile.py` pass unchanged;
    the plans boundary registry and the write-shaped-name guard are unchanged.
    The shared `[history]`/`[load]` reading helper stays in
    `plans/reconcile.py`, so
    `tests/load/test_settings.py::test_load_load_settings_is_called_from_exactly_the_licensed_modules`
    passes unchanged.
  - **Mutations:** call `run_plan` inside `resolve_plans` (the no-write pin
    reds); scan the corpus eagerly (the spy reds); give `resolve_plans` its own
    `today + 1 day` (the date-flip pin reds); omit an appended name from
    `__all__`.
  - **Observable:** the seam tests, the plan suites and
    `tests/test_public_api.py` are green; `git diff --stat tests/plans/golden`
    is empty.
  - _Requirements: 6.1, 6.6, 6.7, 7.3_
  - _Depends: 2.2_

- [x] 3. The four producers

- [x] 3.1 (P) Project each page's best efforts
  - **The mean-max producer**, per design.md § MeanMaxProducer and the
    `mean_max` table of § Data Models: every column and description, rows from
    the composed activity's three curves, a row only where some channel has a
    value.
  - **Tests** (`tests/index/derived/test_mean_max_producer.py`), with
    `PageComputed` built from hand-made activities:
    - rows equal `mean_max_curve` of `page.activity.samples` per channel, on
      samples whose three channels have pairwise-distinct values;
    - a heart-rate-only activity gives NULL power and speed columns and no row
      past its longest stretch;
    - the declared table resolves through `resolve_tables` (descriptions,
      unit words, no declared `page_key`).
  - **Mutations:** swap the speed and heart-rate columns; emit a row when every
    value is `None`. (The producer receives only the composed activity, so
    "use the base file" is not a producer mutation; 5.3 pins composition end
    to end.)
  - **Observable:** the producer tests are green and mypy is clean.
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 9.1, 9.4_
  - _Boundary: MeanMaxProducer_
  - _Depends: 1.2, 2.1_

- [x] 3.2 (P) Project history's series for every methodology
  - **The load-series producer**, per design.md § LoadSeriesProducer and the
    `load_series`, `daily_load` and `weekly_load` tables: the fingerprint
    (workouts and settings digests, no date) and rows from
    `read_history_inputs`, `compute_history` per observed methodology,
    `day_rows`, and the default from `select_methodology`.
  - **Tests** (`tests/index/derived/test_load_series_producer.py`), on the
    derived root, against `compute_history` called in the test:
    - every `daily_load` and `weekly_load` value, for each methodology, equals
      the engine's, and the load-series row equals its constants and threshold;
    - the no-`sources` page's load is in its day's `recorded_load` while
      `snapshot.pages` lacks it;
    - with the methodology configured exactly one row is `history_default` with
      selection `configured`; without it none is;
    - suppressed days hold NULL model values and `suppressed` TRUE;
    - an archive with no load gives three empty tables;
    - the fingerprint moves on a workout or settings change and not on a
      different `today`, nor between two `corpus_snapshot`s of one scan that
      differ only in `held` (history reads every workout page, held or not);
    - each of the three tables' descriptions contains "as of the last
      refresh" and `fitdocs history --methodology` (Req 9.3).
  - **Mutations** (each a re-implementation the fixture defeats): replace the
    engine's model values with a recursion re-implemented with `1/tau` in
    place of `1 - exp(-1/tau)`; recount `pages` as `pages_with_load`; build the
    series from `snapshot.pages`; read the model values without `day_rows`'
    mask; add `today` to the fingerprint; add the path-to-page-key map to the
    fingerprint (the `held` pin reds); drop the agreement sentence from
    `weekly_load`'s description.
  - **Observable:** the producer tests are green and mypy is clean.
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 4.1, 4.2, 4.3, 4.4, 7.1, 7.5, 8.1, 9.1, 9.3, 9.4_
  - _Boundary: LoadSeriesProducer_
  - _Depends: 1.3, 2.2_

- [x] 3.3 (P) Project the benchmark timeline by the profile's own rule
  - **The benchmark producer**, per design.md § BenchmarkProducer and the
    `benchmarks` and `benchmark_periods` tables, descriptions included: the
    unit tokens for every kind, `in_force_periods` evaluated at each group's
    dates through `BenchmarkSet.applicable`, the fingerprint over
    `athlete.toml`'s digest.
  - **Tests** (`tests/index/derived/test_benchmark_producer.py`):
    - for every day from three days before the earliest date to three after
      the latest, for every kind and discipline in the fixture (Ride FTP and
      Run FTP among them), the period covering the day names the entry
      `applicable` returns, and no period covers a day where it returns
      `None`;
    - on the stated day the Ride FTP period names the profile's entry, which
      differs from the naive rule's, and the Ride and Run FTP periods carry
      different values;
    - `retroactive` flips exactly at `measured_on`;
    - every entry appears in `benchmarks` with its source columns; the
      athlete-wide entry has a NULL discipline; notes and inputs text appear
      nowhere (a distinctive marker string in each, absent from every row);
    - the flat top-level `ftp_watts` value appears in no row (Req 5.7);
    - every `BenchmarkKind` has a unit token;
    - an absent profile gives two empty tables;
    - the fingerprint moves on an `athlete.toml` change only;
    - both descriptions contain "as of the last refresh" and "the athlete
      profile's own" (Req 9.3).
  - **Mutations:** replace `applicable` with "latest `applies_from` on or
    before the day"; drop the retroactive split; group by kind alone, merging
    the Ride and Run FTP entries; remove a kind's token; drop the agreement
    sentence from `benchmark_periods`.
  - **Observable:** the producer tests are green and mypy is clean.
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 7.5, 8.2, 9.1, 9.3, 9.4_
  - _Boundary: BenchmarkProducer_
  - _Depends: 1.3_

- [x] 3.4 (P) Project blocks, mesocycles and planned workouts as the plan pass resolves them
  - **The block producer**, per design.md § BlockProducer and the five block
    tables: the fingerprint (workouts, the path-to-page-key map, settings,
    plan sources, and `today` only while a source exists, never raising) and
    rows from `resolve_plans`.
  - **Tests** (`tests/index/derived/test_block_producer.py`), on the derived
    root with `today=TODAY`, against `run_reconcile(copy, today=TODAY)`:
    - every planned workout's state, confidence and override date, every
      claimed and missing stem, every mesocycle's load picture and every
      unplanned page equal the engine's;
    - the matched page with no `sources` has its path and a NULL `page_key`;
    - a row dated `TODAY` is upcoming and one dated the day before is not
      logged; `resolved_on` is `TODAY` on every block row;
    - the invalid source has one `blocks` row with `valid` FALSE and no other
      rows; a root without plan sources gives five empty tables;
    - prescriptions and override reasons appear nowhere (a distinctive marker
      string in each, absent from every row);
    - the fingerprint folds a malformed `fitdocs.toml` into a marker without
      raising, and includes `today` only while a source exists;
    - the fingerprint moves between two `corpus_snapshot`s of one scan that
      differ only in `held` (a claimed page moved to `left_out`, asserted
      first), because the page's `page_key` column turns NULL;
    - all five descriptions contain "as of the last refresh" and `fitdocs
      plan` (Req 9.3).
  - **Mutations:** build the corpus from `snapshot.pages`; pass `today + 1
    day`; treat an invalid source as absent, emitting no `blocks` row for it;
    raise from the fingerprint on a settings error; include `today` with no
    source; drop the path-to-page-key map from the fingerprint (the `held`
    pin reds); drop the agreement sentence from `unplanned_pages`.
  - **Observable:** the producer tests are green and mypy is clean.
  - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8, 6.9, 7.1, 7.5, 8.3, 9.1, 9.3, 9.4_
  - _Boundary: BlockProducer_
  - _Depends: 1.3, 2.3_

- [ ] 4. Registration, the schema version and the boundary

- [x] 4.1 Register the four producers and advance the schema version
  - **Registration**: append the computed producer and the three corpus
    producers to the registry tuples, core producers first.
  - **The schema version**: set `SCHEMA_VERSION` to `main`'s value plus one,
    reading `main` at this task (not a value copied from this plan), and append
    `schema_digest(registered_tables())` under it in `_DIGESTS_BY_VERSION`.
  - **The table-set pin** in `tests/index/test_schema.py` gains the eleven
    names.
  - **Tests** (`tests/index/derived/test_registration.py`):
    - the registry holds the four producers after the core ones, in the stated
      order;
    - every derived table and column has a description, every unit-suffixed
      column names its unit word, and no `TIMESTAMP` column exists;
    - each corpus table's description contains "as of the last refresh" and
      exactly one of the accepted command phrases, by producer:
      `fitdocs history --methodology` (load series), "the athlete profile's
      own" (benchmarks), `fitdocs plan` (blocks);
    - the eleven names are the design's, and `registered_tables()` returns 24.
  - **Mutations:** register a producer twice (`resolve_tables` reds); blank a
    column description; drop the agreement sentence from one corpus table;
    leave `SCHEMA_VERSION` at `main`'s value (the digest pin reds); bump it
    without a digest entry (the `max` pin reds).
  - **Observable:** the full suite (`uv run pytest`) is green, not only
    `tests/index/`, with one stated exception. Registration reaches every test
    that builds an index (`tests/test_confinement.py`'s `index` and
    `sync-with-index` entries, `tests/test_inbox_e2e.py`,
    `tests/connectors/test_e2e.py`, `tests/test_determinism.py`,
    analytics-index's refresh and build tests). analytics-index keeps its own
    tests independent of these producers: every refresh test that asserts an
    exact write set or a no-op runs under its `core_registry` fixture (its
    tasks 6.1 and 6.2), its determinism and non-empty assertions are scoped to
    the core producers' tables (its 6.5), and `fitdocs index`'s schema line is
    pinned as `f"Schema version: {SCHEMA_VERSION}"` (its 7.1).
    - **The exception.** If `analytics-query` is on `main`,
      `tests/query/test_docs_analytics.py` and
      `tests/query/test_skill_examples.py` are expected red, and only those
      two, from this task until 6.2 turns them green (Cross-spec shared
      files). Record their red output in Implementation Notes.
    - **Any other red test**, one not on this plan's Cross-spec shared files
      list, is a stop-and-report; never re-pin it silently.
  - _Requirements: 1.5, 8.4, 9.2, 9.3, 9.5, 10.1_
  - _Depends: 3.1, 3.2, 3.3, 3.4_

- [ ] 4.2 Guard the derived package's boundary
  - **The boundary test** (`tests/index/derived/test_boundary.py`), an AST
    walk per design.md § DerivedGuards: the derived modules' allowed imports;
    the rule and records modules' allowed imports; no clock spelling and no
    write-shaped call in either set; only `registry.py` imports the derived
    package.
  - **Positive controls**, at this task: the walk read every derived module
    and both metrics modules (counted against the file list on disk), and
    synthetic modules containing `import duckdb`, `date.today()`,
    `Path.write_text(...)` and `from fitdocs.index import store` are each
    flagged.
  - **Mutations**, each in place with a `cp` backup restored afterwards:
    import `fitdocs.index.store` in `blocks.py`; call `date.today()` in
    `load_series.py`; import `fitdocs.history.engine` (a submodule) in
    `load_series.py`; import `fitdocs.index.derived` from
    `src/fitdocs/history/engine.py`.
  - **Observable:** the boundary test is green and every listed mutation reds
    it at this task.
  - _Requirements: 2.8, 10.7_

- [ ] 5. End to end through the real refresh

- [ ] 5.1 Prove when each derived table moves and what a failure keeps
  - **Tests** (`tests/index/derived/test_refresh.py`), building and refreshing
    the derived root with 1.2's `build_index` and `refresh` at `TODAY` (or a
    stated later date), with a spy counting each producer's `rows` calls, each
    change made alone from a starting state whose stored fingerprints are
    current:
    - an `athlete.toml` benchmark edit recomputes benchmarks only, and the new
      entry is in `benchmark_periods` without a `regen`;
    - a new page recomputes the load series and blocks, not benchmarks;
    - a later `today` recomputes blocks when a plan source exists and nothing
      when none does;
    - a `notes` edit recomputes the load series and not that page's
      `mean_max` rows;
    - a second refresh with nothing changed leaves every file in the index
      directory byte-identical (size, `mtime_ns`, sha256).
  - **Failures** (8.5), one per input class. Each refresh also carries a
    change that moves an unaffected producer, so "the other tables refresh" is
    observed, not assumed:
    - a malformed `[history]` table plus a benchmark edit: the load-series and
      block rows are unchanged, the benchmark rows change, and both failures
      are reported as the index's could-not-refresh lines;
    - a malformed `[benchmarks]` entry in a valid-TOML `athlete.toml` (so
      `load_profile` raises while analytics-index's own athlete-input load
      succeeds) plus a new page: the benchmark rows are unchanged and the load
      series changes;
    - a configured plan directory that does not exist plus a benchmark edit:
      the block rows are unchanged and the benchmark rows change;
    - after each, the next good refresh repairs the failed tables.

    Implementation Notes record the upstream limit (design.md § Error
    Handling): an `athlete.toml` that is not valid TOML fails the whole
    refresh before any producer runs, so it is not a case of this test.
  - **Mutations:** add the profile digest to the load-series fingerprint; add
    the workouts digest to the benchmark fingerprint; add `today` to the
    load-series fingerprint; drop the "only with a source" condition; let the
    load-series producer swallow the engine's settings error and return empty
    tables (the keeps-previous-rows pin reds); let the benchmark producer
    swallow `ProfileError` the same way.
  - **Observable:** the refresh tests are green.
  - _Requirements: 1.5, 7.4, 8.1, 8.2, 8.3, 8.4, 8.5, 8.6_
  - _Depends: 4.1_

- [ ] 5.2 (P) Prove the derived rows are deterministic
  - **Tests** (`tests/index/derived/test_determinism.py`), all at `TODAY`
    through 1.2's helpers: the derived root with composed pages, indexed five
    ways: incrementally, with one refresh after each page is added in path
    order; after creating the pages in reverse order; from the hand-over
    (`sync_with_handoff`); by re-derivation with no hand-over; and by
    `build_index(rebuild=True)`. For each of the eleven tables, `read_table`
    is equal across all five, each asserted non-empty first.
  - **The hand-over versus re-derivation leg** is a regression check of
    `analytics-index`'s contract (its Req 4.5) over this spec's tables: a
    producer receives no signal of which path supplied the activity, so no
    production mutation of this spec's can make the two differ. Recorded as
    PRESERVED-ONLY in Implementation Notes.
  - **Ordering precondition for the incremental leg**, asserted before
    comparing: the workout pages are added in path order, so the first page
    by path never changes after the first refresh, and the last page added is
    a held page with a load. Otherwise a late change to the first page would
    move the digest under the mutation below, recompute over every page and
    heal the stale state.
  - **Mutation:** let the workouts digest cover only the first workout page
    by path, of `pages` and `left_out` together (the incremental path then
    keeps a stale load series, and the incremental-versus-rebuild comparison
    reds).
  - **Observable:** the determinism tests are green.
  - _Requirements: 1.6, 8.7_
  - _Boundary: DerivedRefreshTests_
  - _Depends: 4.1_

- [ ] 5.3 (P) Prove composed best efforts and the rebuild on the version advance
  - **Tests** (`tests/index/derived/test_composed_and_upgrade.py`), at
    `TODAY` through 1.2's helpers:
    - **Composed**: the ride pair, synced with `sync_with_handoff`, has
      heart-rate best efforts equal to `mean_max_curve` of the composed
      samples, with the base file alone asserted first to record no heart
      rate.
    - **Upgrade**, by analytics-index's recorded-version recipe (its task 6.3
      uses a recorded schema version of 99): build the index with the derived
      producers monkeypatched out of the registry tuples, then set
      `index_meta.schema_version` to `SCHEMA_VERSION - 1` through a writable
      store facade connection. A `refresh` then reports NEEDS_REBUILD naming
      both versions, and `build_index` (not `rebuild=True`: the version
      mismatch alone must trigger it) rebuilds it with every derived table
      non-empty.
  - **Mutations:** drop heart rate from the mean-max producer's channels (the
    composed pin reds); remove `BLOCK_PRODUCER` from the registry append (the
    rebuilt index lacks the block tables, and the non-empty pin reds).
  - **Observable:** both tests are green.
  - _Requirements: 1.2, 10.2_
  - _Boundary: DerivedRefreshTests_
  - _Depends: 4.1_

- [ ] 5.4 (P) Confine the derived producers and prove the data root unchanged
  - **`tests/test_confinement.py`**: append `EntryPoint(id="index-derived",
    …)`, running `fitdocs index` over the derived root with composed pages,
    `FITDOCS_INDEX_DIR` sandboxed and `fitdocs.cli._today` monkeypatched to
    `TODAY`. It is non-vacuous only when each of the eleven derived tables has
    at least one row, read through the store's read-only facade. Add its
    membership pin.
  - **Data-root bytes** (`tests/index/derived/test_preserved.py`): `fitdocs
    sync`, `regen` and `load` over the derived root through the CLI, with
    `fitdocs.cli._today` monkeypatched, leave byte-identical data roots with
    and without a prebuilt index.
  - **Version pins**: `DOC_VERSION`, `MANAGED_KEYS` and `CONTRACT_VERSION`
    equal `main`'s values, and the runtime dependency list is unchanged.
  - **Not here**: Req 7.3 (command output unchanged) is pinned by 2.2's and
    2.3's seam-equality tests, the history and plan goldens and their
    unchanged suites. `fitdocs history` and `fitdocs plan` never reach the
    registry (analytics-index's untouched-commands check), so comparing their
    output with and without these producers could not go red.
  - **Mutations:** write a scratch file into the data root from the block
    producer's `rows` (the confinement guard and the byte comparison red);
    leave one derived table empty (the non-vacuity check reds); advance
    `CONTRACT_VERSION` (the pin reds).
  - **Observable:** the confinement suite and the preservation tests are
    green.
  - _Requirements: 7.2, 10.7, 10.8_
  - _Boundary: DerivedGuards_
  - _Depends: 4.1_

- [ ] 6. Published statements, records and final validation

- [x] 6.1 Publish the derived tables and record the amendment
  - **`CHANGELOG.md` `[Unreleased]` `### Added`**: the four derived tables and
    "run `fitdocs index` once after upgrading", per design.md
    § PublishedStatements.
  - **`.kiro/steering/structure.md`**: the derived-producers clause appended to
    the `index` sentence. Validation by the steering class: read the document
    end to end, and grep `.kiro/steering/` and `CLAUDE.md` for "derived",
    "index", "re-derivable" and "dependencies point"; reconcile every hit.
  - **fit-ingest amendment**: the next free amendment number at landing (6
    today), "landed by analytics-derived", adding a requirement numbered the
    next free requirement number at landing (19 today; 18 already exists).
    It states best efforts at library level and classifies the two choices
    under Req 15.8 in their own record module, outside Req 15.6's enumeration.
    No existing criterion is renumbered or reworded. `spec.json`'s amendments
    array names `tests/metrics/test_mean_max.py` and
    `tests/metrics/test_mean_max_sources.py`.
  - **Roadmap**: tick the analytics-derived Specs line at merge; add or tick a
    fit-ingest line in Phase 10's Existing Spec Updates (idempotent with the
    controller's batch finalize).
  - **Pins** (`tests/index/derived/test_published.py`):
    - the CHANGELOG entry is inside `[Unreleased]` and names `fitdocs index`;
    - `structure.md` names `index.derived`;
    - in `.kiro/specs/fit-ingest/requirements.md`, every `### Requirement N`
      number occurs once, the amendment headings' numbers are consecutive, and
      the last amendment heading contains "landed by analytics-derived";
    - `.kiro/specs/fit-ingest/spec.json` parses, and its amendments array has
      an entry naming both test modules.
  - **Mutations:** move the CHANGELOG entry under a released version; drop the
    `structure.md` clause; number the new requirement 18 (the uniqueness pin
    reds); drop one test path from the `spec.json` entry.
  - **Observable:** the published pins and `tests/test_changelog.py` are
    green; the steering grep before and after is recorded in Implementation
    Notes.
  - _Requirements: 10.3, 10.5, 10.6_

- [x] 6.2 Complete the analytics documentation if this plan lands second
  - **The rule** (stated identically in `analytics-query`'s plan, Cross-spec
    shared files): the second of `analytics-query` and `analytics-derived` to
    land touches exactly the three bounded read-side files. It regenerates the
    `docs/analytics.md` schema-reference block, adds one worked example per
    derived producer to `src/fitdocs/skills/fitdocs-analytics/SKILL.md`, and
    extends `derived_inputs()` in `tests/query/conftest.py` so that every
    derived producer yields rows on `indexed_root`.
    `tests/query/test_docs_analytics.py` and
    `tests/query/test_skill_examples.py` enforce it.
  - **If `analytics-query` is not on `main` when this task runs**: change none
    of the three files. `analytics-query`'s task 7.3 does this work at its
    landing, when these producers are already registered. Record that in
    Implementation Notes; no queue item is needed, because query's plan
    tracks it.
  - **If it is**, do all three:
    - **Fixture inputs.** Extend `derived_inputs()` (it returns
      `DerivedInputs(files=…, athlete_toml=…)` from `tests/query/_helpers.py`;
      `indexed_root` writes both before `fitdocs sync`, with
      `fitdocs.cli._today` pinned to `FIXTURE_TODAY`, 2021-10-01):
      - `files`: one valid plan source under the default plan directory
        `plans/` (`fitdocs.layout.DEFAULT_PLANS_DIR`), in the grammar of
        `tests/plans/fixtures/`, dated around `FIXTURE_TODAY`. Its mesocycle
        window covers the fixture's activities (`FIT_TIMESTAMP_BASE`,
        2021-09-08 UTC) and `FIXTURE_TODAY`. It has a planned workout dated
        before `FIXTURE_TODAY` on a day with no activity and no override (not
        logged), and one dated after it (upcoming). `fitdocs.toml` is not
        written, so its `[tiles] enabled = false` stays;
      - `athlete_toml`: a `[benchmarks]` table appended to the base file,
        which declares `profile_version = 2`. It holds a Ride `ftp_watts`
        entry measured before the fixture's activities (for example
        2021-09-01), equal to the base file's flat `ftp_watts`, so the loads
        the fixture already computes stay put where the profile allows.
    - **Worked examples.** Four H3s under `Worked examples`, one per derived
      producer, each followed by one `sql` fence that selects rows from that
      producer's table. No example is a bare aggregate, which returns a row
      when the table is empty, and none uses an outer join that keeps rows
      once the producer's tables are emptied. Every window is relative to the
      data, `max(date)` or the table's own dates, worded "in the latest year
      of data": never "this year", `current_date`, `now()` or today. Each
      predicate is checked against what `indexed_root` holds before it is
      written.
      1. **Best efforts** (`derived.mean_max`): the best power at each
         duration in the latest year of data, with the page it came from
         (`mean_max` joined to `pages`, one row per `duration_s` with a
         power). Not a fixed 20-minute filter: the builder's ride records 10
         seconds (`tests/fixtures/builder.py:298`), so the fixture holds only
         the 1-, 5- and 10-second durations. The prose may name
         `duration_s = 1200` as the 20-minute filter.
      2. **Fitness, fatigue and form** (`derived.load_series`): the last four
         weeks of the series `fitdocs history` shows by default (`daily_load`
         joined to `load_series` where `history_default`, the window taken
         from `load_series.series_end`). A default exists only when one
         methodology is observed or one is configured; if the fixture records
         two, stop and report rather than drop the filter (`fitdocs.toml` is
         not this plan's to change).
      3. **Thresholds in force** (`derived.benchmarks`): the FTP in force on
         each ride's date in the latest year of data (`benchmark_periods`
         joined to the ride pages on `starts_on` and `ends_before`, with
         `ends_before` NULL while in force).
      4. **Planned sessions not logged** (`derived.blocks`): the
         `planned_workouts` rows whose `state` is `not logged`, in the block
         with the latest `starts_on`.
    - **The schema block.** Regenerate it with `uv run python -m
      tests.query.test_docs_analytics`; a second run leaves `git diff`
      empty.
  - **Tests**: none of this plan's own. The proof is analytics-query's
    `tests/query/test_skill_examples.py` on `indexed_root` (every `sql` fence
    runs and returns rows, and each derived producer has an example that
    returns no rows once that producer's tables are emptied) and
    `tests/query/test_docs_analytics.py` (the block equals the live schema).
    Both have been red since 4.1 and turn green here. Any other query test
    that reds after the fixture extension is a stop-and-report.
  - **Mutations** (second branch only): misspell a column in one derived
    example (the execution pin reds); replace the best-efforts example with
    `SELECT max(power_w) AS best FROM mean_max` (the emptied-copy pin reds);
    take the best-efforts window from `current_date` (the fixture's data is
    from 2021, so `row_count >= 1` reds); drop the `[benchmarks]` append (the
    thresholds example returns no rows, and `row_count >= 1` reds); leave the schema block stale (the
    block-equality pin reds).
  - **Observable:** in the second branch, `uv run pytest tests/query
    tests/index/derived` is green, with the four examples and the fixture
    inputs recorded in Implementation Notes; in the first, the Implementation
    Notes entry names `analytics-query`'s task 7.3.
  - _Requirements: 10.4_
  - _Depends: 6.1_

- [ ] 6.3 Register test modules, re-pin after rebase and validate the feature
  - **mypy registration**: append every new test module to `pyproject.toml`'s
    mypy `files` list.
  - **After the final rebase onto `main`**: `SCHEMA_VERSION == main's value +
    1`, re-pinning the version and its digest entry if a sibling advanced it
    first; the table-set pin holds every registered table; `CONTRACT_VERSION`
    and `DOC_VERSION` equal `main`'s.
  - **Full validation**: `uv run pytest && uv run ruff check . && uv run ruff
    format --check . && uv run mypy`, plain, with `TZ=UTC`, and with
    `CI=true`; the forbidden-strings gate in the mode earlier specs' notes
    record.
  - **Observable:** all green after the rebase, with the commands' output
    recorded in Implementation Notes.
  - _Requirements: 10.1, 10.7_

- [x] 6.4 (Maintainer-only) Measure the derived tables on the real data root
  - **Who runs it**: the maintainer, on their machine. No agent reads the real
    data root.
  - **What to measure**: `fitdocs index --rebuild` time with and without the
    derived producers; one recompute of each corpus producer; the share of
    rebuild time spent in best efforts; the distribution of steps between
    consecutive recorded samples per source (HealthFit, Garmin, Stryd); the
    fraction of pages with each channel that lose their 20- and 60-minute
    points to steps between 5 and 10 seconds.
  - **Where results go**: `research.md`, as numbers only.
  - **Observable**: the measurements are recorded; if the 5-to-10-second loss
    exceeds 5 % of the pages carrying a channel, a follow-up is queued to
    revisit the maximum step (a `SCHEMA_VERSION` advance).
  - _Requirements: 2.2, 8.1, 8.3_


## Implementation Notes

- 2026-10-07 task 1.1 candidate is locally verified but NOT accepted: records-only source and tests remain untracked in `/private/tmp/fitdocs-analytics-derived`; exact candidate is persisted in `pending-task-1.1.patch`. Scoped tests 113 passed, mypy and Ruff passed. Independent review confirmed 19 claimed and two own mutation failures/restored passes. Initial identifier gaps were repaired by literal pins for both choice keys and all 29 constant names. No task checkbox was completed.
- Environment debug resolved a separate Homebrew interpreter mismatch: unchanged tooling tests 17 passed/one failed under Homebrew 3.11.15 versus 18 passed under pyenv 3.11.15; a fake interpreter symlink resolves differently. The worktree now uses canonical `/Users/josh/.pyenv/versions/3.11.15/bin/python3.11` and the default warm uv cache with `--group docs`. Existing queue `2026-10-05-site-fixture-homebrew-interpreter-path` tracks the issue.
- Final task 1.1 canonical gate FAILED: 9,393 passed, one failed, two expected actionlint skips in 300.41 seconds. Unchanged `tests/sitebuild/test_preview.py` controlled live case failed at line 1157 waiting 20 seconds for the added page, before deletion. Native mechanism UNKNOWN; no failure-time state captured. Independent review REJECTED; debug round 2 returned STOP_FOR_HUMAN. Existing queue `2026-10-06-preview-delete-readiness-race` receives this evidence. No downstream patch, weakened deadline, or additional unchanged retry was made; the reviewer's already-started standalone pass does not supersede this gate.
- User explicitly authorizes agent-run task 6.4 measurements, overriding its maintainer-only restriction, using the peer-created HealthFit root at `/private/tmp/fitdocs-analytics-query-timings/data` once positively READY. The user confirms this root is equivalent to their actual fitdocs install. Use a private complete copy for writer measurements; never mutate the shared root/index concurrently. Only aggregate counts/timings enter research; personal FITs, pages and source paths remain outside Git. No measurements have run. The earlier 39-file private copy is not the final timing dataset.

- 2026-10-07 resumed task 1.1 accepted after owning polling-watcher repair `0b92561`: fresh independent review APPROVED; canonical 9,395 passed/two optional actionlint skips (262.54s), scoped 113 passed, static checks clean, all 19 claimed plus two new own mutations intended RED/restored GREEN. Parent fresh scoped verification 113 passed. Earlier failed runs retained; no preview deadline or assertion changed. User requests parallel independent tasks in isolated worktrees and a fresh Sol instance for every dispatch; Luna remains the implementer for each task.

- 2026-10-07 task 2.1 accepted after fresh Luna remediation and fresh independent Sol approval: canonical 9,409 passed/two optional actionlint skips; all 23 claimed mutation entries and six new independent variants RED/restored GREEN, including separate power/HR integer exactness. Parent fresh metrics regression 308 passed. Prior invalid flag chronology retained; separately evidenced API-only OFF shell, new test, OFF RED, ON implementation/GREEN, then flag removal satisfies the repair. Producer integration remains later-owned; plain imports are covered by the existing global boundary guard.

- 2026-10-07 task 2.2 accepted after complete-date and per-field projection assertions closed the omission survivor: fresh independent canonical 9,392 passed/two optional skips, preservation 475 passed, 17 distinct claimed and three new own mutants RED/restored GREEN; parent fresh seam/API 52 passed. History reports and bytes equal original engine over seven copied scenarios; chart helpers, imports and goldens preserved. The history public surface includes defining-owner entries. Task 2.3 now owns the next plans-only public surface append.

- 2026-10-07 task 1.2 accepted: corrected canonical 9,398 passed/two optional skips; parent fresh fixture 10 passed; all retained 59 executions, seven latest exact-row claims and three new own valid controls RED/restored GREEN. Earlier reviewer cold-cache/restricted gate failed (15 failed, 31 errors) from uncached PyPI DNS and localhost PermissionError; corrected default warm cache plus authorized socket access passed unchanged code. Do not set UV_CACHE_DIR.
- Fixture roles: threshold loads 11/23/31/59/71 plus left-out 83; banister_1991 loads 17/43; two Ride pages on February 3; two loadless pages February 13/14; no-source page dated February 15 has stem 2026-02-14-left-out and is matched by no-sources-match. Synthetic plan supplies exact/absorbed/ambiguous, missing-stem override, skipped/not-logged/upcoming, unplanned, and invalid source. Ride FTP 260 measured February 10 applies January 1 versus 271 measured February 5 applies February 1, profile versus naive differs on February 11; Run FTP 283 measured February 7, Run LTHR 172 with full derived provenance, athlete max HR 203, flat FTP 999. Composed switch supplies actual builder run and merge ride pair; all helpers require explicit TODAY 2026-02-24, public store facade and isolated index. Producer parity remains later-owned.

- 2026-10-07 task 3.1 accepted: fresh independent canonical 9,428 passed/two optional actionlint skips, explicit scoped mypy/Ruff clean, all 33 claimed and 15 own mutations RED/restored GREEN; parent fresh producer/rule 19 passed. Exact frozen seven-column mean_max schema and pure composed-activity engine projection verified. Registry integration and real composition/handoff remain tasks 4.1 and 5.3; no producer re-computation or base-file read.

- 1.3 accepted: immutable snapshot/file/layout/held-key digests; fresh independent canonical suite 9439 passed/2 optional skips, all 32 mutation executions RED/restored GREEN, explicit two-file mypy and scoped Ruff clean. Parent fresh derived scope 26 passed. Typing-only repair preserves every assertion AST and production bytes; always explicitly type-check newly added test paths until 6.3 registration. Evidence: /private/tmp/analytics-derived-evidence/resume/1.3/review-remediation1/report.md.

- 6.1 accepted: derived release notes, structure dependency clause, fit-ingest Requirement 19 and actual Amendment 6 with both test paths. Canonical fresh independent suite 9415 passed/2 optional skips; 21 claimed plus seven own mutations RED/restored GREEN, explicit mypy/Ruff clean, parent fresh 75 publication/changelog checks passed. Derived roadmap tick remains deferred until feature merge; final rebase must preserve analytics-index main 63d79a3 peer completion and registrations. Evidence: /private/tmp/analytics-derived-evidence/resume/6.1/review-remediation1/report.md.

- 2.3 accepted: pure read_plan_sources/resolve_plans and frozen ParsedSource/PlanSources/PlanResolution; original plan writes/bytes and lazy scanning preserved. Fresh independent canonical 9422 passed/2 optional skips, preservation 640, all 31 claimed plus six own mutations RED/restored GREEN; explicit five-file mypy/Ruff clean. Parent fresh post-review restoration engine/API scope 61 passed. Earlier overlapping controller check excluded from acceptance evidence; final verification serialized after reviewer restoration. Invalid-only corpus and methodology are explicitly None; complete sources and ordered block payloads pinned. Evidence: /private/tmp/analytics-derived-evidence/resume/2.3/review-remediation2/report.md.

- 3.2 accepted: frozen load-series producer delegates every methodology, day mask, weekly row, constants and selection to the history seam; fingerprint includes workouts/settings only. Fresh independent restored canonical 9452 passed/2 optional skips, 30 claimed and 15 own mutations assertion-RED/restored GREEN, all 15 task projection sections pinned; explicit two-file mypy/Ruff clean. Parent fresh producer/history 310 passed. Configured nonseed constants/threshold and fractional loads close prior default-only and integer-only blind spots; NULL-preserving rounding replaces prior unrelated TypeError evidence. Genuine original API/OFF RED chronology verified; later final OFF is supplementary. Parent accepted-eight integration also passed 9459/2 optional before this addition. Evidence: /private/tmp/analytics-derived-evidence/resume/3.2/review-remediation1/report.md.

- 6.2 accepted ownership decision: main 63d79a364fa5fef71875888f474c8cd0982e2fe4 does not contain analytics-query branch f7dfd762d1349a0dd5b13a605e0a7b4f01df723c (merge-base ancestor check exit 1; main...query counts 0 8). First-lander path makes no change to docs/analytics.md, src/fitdocs/skills/fitdocs-analytics/SKILL.md, or tests/query/conftest.py. Analytics-query task 7.3 owns the generated schema reference, four derived worked examples, and derived_inputs fixtures at its landing. No queue item is needed. Recheck main at final rebase: if query lands first, perform the bounded second-lander path before feature GO. Fresh independent review APPROVED with canonical 9467 passed/2 optional skips and all three bounded paths unchanged. Parent fresh ancestry recheck also confirms current query 63014ff6663a606451c4ef4f31663ad7d9674f75 is absent from main (ancestor exit 1; divergence 0 9); paths remain absent and diff check clean. Evidence: /private/tmp/analytics-derived-evidence/resume/6.2/review/report.md.

- 3.3 accepted: frozen benchmark producer uses the profile's own applicable rule with exact maximal periods, all five kinds and profile-only fingerprints. Fresh independent canonical 9452 passed/2 optional skips, final scope 168, all 27 original plus six repair claims and 25 own mutation variants assertion-RED/restored GREEN; all 12 task requirements pinned with existing-owner qualifications. Source byte-identical to initial final implementation; test repair adds independent literal nine-row periods and fractional pace. Genuine initial OFF RED is qualified: CorpusProducer identity test repair preceded computation, BenchmarkProducer identity repair followed ON; no corrected-OFF claim. Parent fresh scope 168 and integrated derived/benchmark scope 213 passed, explicit two-file mypy/Ruff clean. Evidence: /private/tmp/analytics-derived-evidence/resume/3.3/review-remediation1/report.md.

- 3.4 accepted: frozen five-table block producer delegates the complete plan resolution and keeps left-out page matches/loads with NULL held keys. Fresh independent canonical 9465 passed/2 optional skips, 81 original variants, eight prior independent faults, eight repair recipes, both sole held-only controls, five new filesystem faults and three inventory diagnostic faults all RED/restored GREEN; all 15 listed clauses pinned. Production unchanged; test repair pins physical row multiplicities, distinct unplanned left-out load97/NULLkey, complete entry/type/byte inventory before reference copying, and exact owning SettingsError marker. Explicit both-file mypy/Ruff clean; parent fresh scope565 and integrated derived/plans618 passed. Genuine original API-only OFF checkpoint precedes GO_IMPLEMENT. Evidence: /private/tmp/analytics-derived-evidence/resume/3.4/review-remediation1/report.md. All four producers now accepted; registration remains4.1.

- 6.4 accepted: user-authorized equivalent shared HealthFit root, private writer copy; all 2,517 source FITs and 2,502 composed pages measured without parse/composition errors or input changes. Fresh independent pyenv canonical 9,475 passed/two optional skips; all 112 numeric/dash cells, formulas and inventories independently checked and freshly verified by parent. Core rebuild287.473370624939s, derived285.86776125011966s, mean-max8.511576691875234s/2.977452460764906%,30,802 rows. Single-run times imply no causal speedup. All six channel/duration loss rates below5%; no exact union loss inferred. Ten other derived tables and core loads are zero; athlete profile/plan sources absent, so corpus timings cover empty outputs. Previous Homebrew-environment review9474/1fail/2skip retained, canonical environment corrected without source changes. Final accepted runtime must match all11 measurement-source-hashes.json entries before reuse under4.1/6.3; affected runtime changes require affected measurement reruns. Evidence: /private/tmp/analytics-derived-evidence/resume/6.4/review-pyenv/verdict.md.

- 4.1 accepted: core-first registration of four accepted producers,24tables/eleven derived names, currentmain995db58 schema1 advancedto2 withappend-onlydigest. Fresh independent canonical9486/2optional315.32s, all15claimed+2own mutants sole-target RED/restored211GREEN, explicitfive-filemypy/Ruff clean; parentfresh211passed. Allfour metadata/version requirementsPINNED,two existing refresh clausesPRESERVED-ONLY. Earlier9479/2skip/7failuregate retained and resolvedby separatelylanded analytics-index owner correction main995db58. Query63014ffstillnotonmain, so no temporaryqueryexception. All11 measuredruntimehashes matchfinalacceptedregistration bytes; task6.4 measurementreusegate satisfied withoriginalempty-output/single-runlimits. Evidence: /private/tmp/analytics-derived-evidence/resume/4.1/review-ownerlanded/verdict.md.
