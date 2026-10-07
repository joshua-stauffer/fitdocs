# Implementation Plan

## Upstream Prerequisites

- **`analytics-index` has merged to `main`**, and this plan starts from it. Every
  seam in `analytics-index` design.md § "Cross-spec seams" is on the branch:
  - `fitdocs.index.location`, `store` (the facade), `schema`, `bookkeeping`,
    `corpus`, `fingerprint`, `producer`, `registry` and `build`, with exactly
    the names Seam 5 lists for query (design.md § Allowed Dependencies);
  - the one corpus snapshot builder, `corpus.corpus_snapshot(data_root, scan,
    *, today, athlete_fingerprint, held)`, and
    `fingerprint.combined_corpus_fingerprint(producer, snapshot)`
    (`analytics-index` tasks 5.1 and 2.3), with `CorpusSnapshot.left_out`,
    `CorpusLeftOut` and `LeftOutPage.document_fingerprint`;
  - the `fitdocs index` command;
  - the autouse `FITDOCS_INDEX_DIR` isolation fixture in `tests/conftest.py`;
  - `tests/index/_helpers.py` (`hold_index`, `forge_storage_version`);
  - `_INDEX_IMPORTERS` in `tests/index/test_boundary.py`;
  - the CLI docstring at "Twelve".

  A task that finds one of those shapes different from design.md stops and
  reports rather than adapting silently.
- **Three upstream facts.** These were raised to the controller as upstream
  issues against `analytics-index` (design.md § Upstream Prerequisites), and
  `analytics-index`'s cross-spec round 1 resolved all three. Each is now
  provided by an `analytics-index` task. Task 1.1 confirms each on the branch,
  and **stops and reports** if one does not hold:
  - **U1** (`analytics-index` task 1.1): `pyproject.toml` pins
    `duckdb>=1.2,<2`. Every 1.1.x release writes into HOME before refusing
    `INSTALL` (research.md, Decision 1).
  - **U2** (`analytics-index` task 4.1): `IndexResult.fetchmany`/`fetchall`
    raise `IndexStatementError` or `IndexInterrupted`, chained, as `execute`
    does.
  - **U3** (`analytics-index` task 8.1): the ownership contract's
    analytics-index section names "`query-spill-<pid>/` (transient; created
    by `fitdocs query`, removed on close or by the next query)" and
    `writer-spill/`. This plan edits neither `docs/ownership-contract.md` nor
    `CONTRACT_VERSION`.
- **The sibling `analytics-derived`** may land before or after this plan. Its
  producers appear through `registered_tables()`, and this plan treats them
  generically. See "Cross-spec shared files" for what the second lander does.

**Hard rules for every task**

- **No test, probe or fixture executes `INSTALL`, `LOAD` or `ATTACH 'md:'`,
  or calls `start_ui`.**
  - `INSTALL`/`LOAD` refusal is pinned only at the statement gate, where the
    executing function is replaced by a non-forwarding recorder.
  - A statement naming an `http(s)` URL runs only on a sandboxed connection,
    with HOME pointed at a fresh temporary directory that is asserted to still
    be empty afterwards.
  - A mutation run that removes a sandbox setting deselects every URL case
    (`-k 'not url'`; every such case carries `url` in its id).
  - Ad-hoc DuckDB exploration happens only in a throwaway venv under the
    session scratchpad, network-blocked, never in the worktree's `.venv`.
- **Only `src/fitdocs/index/store.py` imports `duckdb`.** Tests reach DuckDB only
  through the store facade, `fitdocs.query`, or the CLI.
- **Every test or fixture that executes DuckDB points HOME at a fresh
  temporary directory**, and never reads or writes the real user's HOME,
  cache or configuration.
  - Function-scoped tests in `tests/query/` use the `home_dir` fixture
    (task 1.1).
  - Module-scoped builders set HOME and `FITDOCS_INDEX_DIR` themselves, with
    `pytest.MonkeyPatch.context()` over `tmp_path_factory` directories. The
    function-scoped autouse fixture and `home_dir` cannot reach them.
  - Tests outside `tests/query/` (task 5.4) set HOME themselves.
    `tests/connectors/conftest.py` already does this for the e2e module.
- **Fixture data roots disable tile requests** (`[tiles] enabled = false` in
  their `fitdocs.toml`), so a fixture sync opens no socket.
- **Absent is `None`, then `NULL`.** No task prints `0`, an empty string or a
  default for a NULL.
- **No fixture holds personal data.** Every `.fit` input comes from
  `tests/fixtures/builder.py`, `identity.py` or `merge.py`. No task reads the
  real data root except for task 8.3, which the maintainer explicitly authorized
  the agent to run on the separate HealthFit timing root described below.
- **No schema, document or contract change.**
  - `SCHEMA_VERSION`, every table, column and comment, `DOC_VERSION`,
    `MANAGED_KEYS`, `CONTRACT_VERSION`, `docs/ownership-contract.md` and the
    rendering goldens stay untouched.
  - A task that needs any of these stops and reports.
  - Temporary edits to `analytics-index` files made only as named mutations are
    the exception. They are restored from a `cp` backup.
- **Mutations** follow `change-protocol.md` § Fixture Discrimination, including
  its bytecode-cache step.
  - Each named mutation is applied, observed red with `uv run pytest`,
    reverted by restoring a `cp` of the file taken before it, and observed
    green.
  - The result is recorded in the task's Implementation Notes.
  - Never revert with `git checkout -- <path>`, `git stash` or
    `git reset --hard`.
  - A listed mutation that cannot be made red is reported as UNPINNED. The
    assertion's wording is never weakened instead.
  - A guard's helper functions are code, and get fixed-input tests in the task
    that adds them.
- **Shell safety.** Never `rm -rf`, `git init`, `git reset --hard` or
  `git checkout -- <path>`. Never chain a destructive command after `cd`.
- **Types and lint.**
  - Every task type-checks the modules it creates or changes with
    `uv run mypy <paths>`.
  - Every task runs `uv run ruff check` and `uv run ruff format --check` on
    the files it changed.
  - Task 8.2 registers the new test modules in `pyproject.toml`'s mypy `files`.
- **Stop and report** when a task finds it needs any of:
  - a runtime dependency;
  - a change to an `analytics-index` seam beyond the one facade method of
    task 1.2;
  - a write location other than the spill directory;
  - a network path;
  - a change to what any other command does.

## Shared source files

Each file below has more than one writer in this plan, and its writers are
sequential: never two of them `(P)` at once.

- **`src/fitdocs/index/store.py`**: 1.2 only, an append.
- **`src/fitdocs/query/sandbox.py`**: 2.2, then 2.3.
- **`src/fitdocs/query/statement.py`**: 3.1, then 3.2.
- **`src/fitdocs/query/schemaview.py`**: 4.2, then 5.1.
- **`src/fitdocs/cli.py`**: 5.3 only.
- **`pyproject.toml`**: 6.1 (`[project.urls]`), then 8.2 (the mypy `files`).
- **`src/fitdocs/skills/fitdocs-analytics/SKILL.md`**: 7.1 (the text), then
  7.3 (making the examples execute).
- **`tests/query/conftest.py`**:
  - 1.1: `home_dir`;
  - 1.3: the indexed fixtures;
  - 7.3: the derived inputs section, only if `analytics-derived` has landed.
- **`tests/query/_helpers.py`**: 1.3 only. Later tasks import it and never edit
  it; a missing helper is a stop-and-report.
- **`tests/query/test_fixtures.py`**: 1.1 (the `home_dir` section), then 1.3
  (the builders section).
- **`tests/query/test_store_facade.py`**: 1.1 (the U2 section), then 1.2 (the
  statement-types section).
- **`tests/query/test_boundary.py`**: 1.3 (importers), 2.1 (format purity) and
  5.4 (direction). Each adds its own headed section, and 2.1's `(P)` sibling
  2.2 does not touch it.
- **`tests/query/test_statement.py`**: 3.1 (execution section), then 3.2 (gate
  section).
- **`tests/test_agent_skill.py`**: 7.1 (the profile), then 7.2 (the
  teaching-order pin).

## Cross-spec shared files

Each file below is shared with `analytics-index` (landed) or `analytics-derived`
(the wave-2 sibling). Writers append an entry, a row, a field or a block, and
never rewrite or reorder another spec's. **On rebase, keep both.**

- **`src/fitdocs/cli.py`**, the docstring command count, and
  `tests/test_cli_skill.py:262-270`.
  - This plan moves the count from `main`'s value to that value plus one: from
    "Twelve" to "Thirteen", and from 12 to 13.
  - `analytics-derived` adds no command.
  - If another command lands first, re-pin from `main` plus one.
- **The no-network command list**:
  - `tests/connectors/test_e2e.py` (`analytics-index` appended `index`; this
    plan appends `query`, with an argument column);
  - `.kiro/steering/tech.md`, Network and Credentials;
  - the `connectors` amendment for Req 14.1. `analytics-index`'s Amendment 1
    adds `index`. This plan starts after `analytics-index` merges, so it
    records its own amendment, connectors Amendment 2 (the next free number
    at landing), and never edits Amendment 1.
- **`tests/test_confinement.py`**: this plan appends one standalone test for
  `query`.
- **`tests/index/test_boundary.py`, `_INDEX_IMPORTERS`**: this plan appends
  `fitdocs.query.sandbox`, `fitdocs.query.statement`,
  `fitdocs.query.freshness`, `fitdocs.query.schemaview` and
  `fitdocs.query.command`, the five names `analytics-index` design.md and its
  task 7.3 name. The guard is one-way (`analytics-index` task 7.3). The
  duckdb-importer set stays exactly `{store}`.
- **`src/fitdocs/index/store.py`**: this plan appends one facade method,
  `statement_types`. It never changes `MANDATORY_SETTINGS` or an existing
  method.
- **`PACKAGED_SKILLS`** (`src/fitdocs/agentskill.py`), with
  `tests/test_skill_locator.py:57-58` and the `tests/test_agent_skill.py`
  profiles: this plan appends `fitdocs-analytics` last.
- **The second lander's bounded read-side exception** (design.md § Out of
  Boundary). "`analytics-derived` touches neither the pass nor the read side"
  holds except here: whichever of `analytics-query` and `analytics-derived`
  lands second touches exactly these three read-side files.
  - **The generated schema-reference block in `docs/analytics.md`.** The block
    projects whatever schema is live on `main` when a spec lands. The second
    lander regenerates it with `uv run python -m
    tests.query.test_docs_analytics`, and re-pins it.
  - **The worked examples in `src/fitdocs/skills/fitdocs-analytics/SKILL.md`.**
    `tests/query/test_skill_examples.py` requires one `sql` example per
    non-core **producer**, keyed on `ResolvedTable.producer` and
    `TableScope`. That example must name one of the producer's tables and
    select rows from it. For `analytics-derived` that is four examples:
    `derived.mean_max`, `derived.load_series`, `derived.benchmarks` and
    `derived.blocks`. The second lander adds or keeps them; the test turns
    red until it does.
  - **The derived-inputs section of `tests/query/conftest.py`'s indexed
    fixture**: the plan sources, the benchmark entries, and whatever else
    each derived producer needs to yield rows on the fixture.
    - If `analytics-derived` landed first, task 7.3 extends it.
    - Otherwise, the second lander extends it.
    - The section is an append point: a function `derived_inputs()` that
      returns two outputs:
      - **extra files**, as data-root-relative path to text (for example plan
        sources);
      - **TOML text appended** to the fixture's `athlete.toml`, for example
        a `[benchmarks]` table.
    - The builder writes both **before `fitdocs sync`**, so every document and
      load is computed under the final inputs.
    - The base `athlete.toml` declares `profile_version = 2`
      (`src/fitdocs/athlete.py:40-44`), so an appended `[benchmarks]` table
      is valid. The append never replaces the base keys.
  - **Data-relative examples.** Every worked example, core or derived, takes
    its date window relative to the data: `max(date)`, or the table's own
    dates. None uses `current_date`, `now()` or "this year".
    - The fixture's activities sit at `FIT_TIMESTAMP_BASE`
      (`tests/fixtures/builder.py:100`), about September 2021.
    - The fixture's "today" is pinned (task 1.3).
    - The second lander proves its examples with
      `tests/query/test_skill_examples.py` on `indexed_root`, extending the
      `derived_inputs()` hook as needed.

  Every table, derived ones included, stays covered by the docs schema block
  and `--schema`, which need no per-table work.
- **`CHANGELOG.md` `[Unreleased]`**: append under an existing category heading,
  and create it only if absent.
- **`pyproject.toml`**: `[project.urls]` and the mypy `files` list, append-only.
- **`.kiro/steering/structure.md`**: the dependency-direction line for `query`,
  appended.
- **`.kiro/steering/roadmap.md`**: the Phase 10 ticks for this spec and the
  connectors line.

## Test File Ownership

- **1.1**:
  - `tests/query/__init__.py`;
  - `tests/query/conftest.py` (`home_dir`);
  - `tests/query/test_fixtures.py` (`home_dir` section);
  - `tests/query/test_store_facade.py` (U2 section).
- **1.2**: `tests/query/test_store_facade.py` (statement-types section).
- **1.3**:
  - `tests/query/conftest.py` (the indexed fixtures);
  - `tests/query/_helpers.py`;
  - `tests/query/test_fixtures.py` (builders section);
  - `tests/query/test_boundary.py` (importers section);
  - `_INDEX_IMPORTERS` in `tests/index/test_boundary.py`.
- **2.1**: `tests/query/test_format.py`, and `tests/query/test_boundary.py`
  (format-purity section).
- **2.2**: `tests/query/test_sandbox.py`.
- **2.3**: `tests/query/test_spill.py`, plus only the exact opening-settings
  expectation in `test_non_locked_open_fault_is_not_retried` in
  `tests/query/test_sandbox.py`: add the required per-PID `temp_directory`
  while preserving the full resource/read-only/error assertion. This evolves
  the phase-2.2 expectation when task2.3 adds its specified setting.
- **3.1**: `tests/query/test_statement.py` (execution section). **3.2**: the same
  file (gate section).
- **4.1**: `tests/query/test_freshness.py`.
- **4.2**: `tests/query/test_schemaview.py` (catalog section). **5.1**: the same
  file (state section).
- **5.2**: `tests/query/test_command.py`.
- **5.3**: `tests/query/test_cli_query.py` and `tests/test_cli_skill.py:262-270`.
- **5.4**:
  - `tests/test_confinement.py` (an appended test);
  - `tests/connectors/test_e2e.py:203-246`;
  - `tests/query/test_crash_vectors.py`;
  - `tests/query/test_boundary.py` (direction section).
- **6.1**: `tests/query/test_docs_analytics.py` and
  `tests/test_docs_guarantees.py:1111-1123`.
- **7.1**:
  - `tests/test_agent_skill.py` (import, `_ANALYTICS_HEADINGS`, profile);
  - `tests/test_skill_locator.py:29-58`;
  - `tests/test_release_artifacts.py:978-983`;
  - `tests/test_releasing_docs.py:569-573`.
- **7.2**: `tests/test_agent_skill.py` (teaching-order pin).
- **7.3**: `tests/query/test_skill_examples.py`.
- **8.1**: `tests/query/test_changelog_entry.py`.

---

- [x] 1. Foundation: prerequisites, the test package, the facade method and the fixtures

- [x] 1.1 Confirm the upstream facts and create the isolated query test package
  - **Prerequisite confirmations.** Each is a landed `analytics-index` fact,
    recorded in Implementation Notes with file:line evidence and the
    `analytics-index` task that provides it:
    - **U1** (`analytics-index` task 1.1): the dependency literal in
      `pyproject.toml` is `duckdb>=1.2,<2`.
    - **U2** (`analytics-index` task 4.1): the fetch-wrapping pins in the
      policy section of `tests/index/test_store.py` exist and are green; this
      task's own U2 pins below confirm it on query's call path.
    - **U3** (`analytics-index` task 8.1): `docs/ownership-contract.md`'s
      analytics-index section contains "`query-spill-<pid>/` (transient;
      created by `fitdocs query`, removed on close or by the next query)" and
      names `writer-spill/`.
    - **The snapshot seam** (`analytics-index` tasks 2.2, 2.3 and 5.1):
      `corpus.corpus_snapshot` and `fingerprint.combined_corpus_fingerprint`
      exist with `analytics-index` design.md's signatures (`held` keyword-only
      with no default), `combined_corpus_fingerprint` takes no version
      argument, `CorpusSnapshot` has `left_out`, and `LeftOutPage`'s fields
      end with `document_fingerprint`.
    - **The test-only names in Seam 5.** `analytics-index` design.md Seam 5's
      test-only bullet lists every test-only name these tests read (design.md
      § Allowed Dependencies): `store.duckdb_version`,
      `core.documents.CORE_DOCUMENTS`, `core.computed.CORE_COMPUTED`,
      `schema.TableScope`, and monkeypatching `registry.DOCUMENT_PRODUCERS`
      and `registry.CORPUS_PRODUCERS`. Confirm each is listed there on the
      branch. If one is not, stop and report.
    - `tests/index/_helpers.py` exports `hold_index` and
      `forge_storage_version`.
    - **The importer guard is one-way** (`analytics-index` task 7.3, whose
      fixed-input test pins both directions): it fails on an importer missing
      from `_INDEX_IMPORTERS`, and does not fail on a listed name whose module
      does not exist. Task 1.3 relies on this to append names ahead of their
      modules.

    If any confirmation fails, stop and report. Do not work around it.
  - **The test package.** Create `tests/query/__init__.py` and
    `tests/query/conftest.py` with one fixture, `home_dir`.
    - It is function-scoped.
    - It monkeypatches HOME to a fresh `tmp_path` directory.
    - It offers `assert_untouched()`, which fails if anything exists inside
      that directory.
    - The conftest records `_REAL_HOME = Path.home()` at import, before any
      monkeypatch, for the fixture self-tests in 1.3.
  - **The `home_dir` self-tests** (`tests/query/test_fixtures.py`, its section):
    - inside a test, `Path.home()` is the temporary directory and not
      `_REAL_HOME`;
    - `assert_untouched()` passes on an empty directory, and fails once a file
      is written into it.
  - **The U2 pins** (`tests/query/test_store_facade.py`, U2 section). Each
    runs on a store connection opened read-only on a database created with
    `store.create_index`, with HOME at `home_dir`. These exercise
    `analytics-index`'s facade on query's own call path, a read-only
    connection, and they run again on `duckdb==1.2.0` in task 8.2:
    - `execute("SELECT now()")`, then `fetchmany(1)`, raises
      `IndexStatementError` whose `__cause__` is set. The same holds for
      `fetchall()`, separately. Each test first asserts that `pytz` is not
      importable, so the fetch-time failure is real.
    - Start a 0.5-second interrupt timer before
      `execute("SELECT count(*) FROM range(1000000000000)")`. Run execute
      and `fetchmany(1)` inside one exception boundary; require chained
      `IndexInterrupted` from either operation and record the observed phase.
      This case runs in a subprocess with a 60 s timeout, so a broken
      interrupt reds instead of hanging.
    - Separately, a non-forwarding synthetic backend relation raises its
      `InterruptException` during `fetchmany`. Require `IndexInterrupted`,
      original cause identity and matching message. This deterministic pin
      tests fetch interruption wrapping independently of the real aggregate's
      version-dependent interruption phase.

    If any fails on the unmodified branch, U2 does not hold: stop and
    report.
  - **Mutations:**
    - make `home_dir` return the real home (the `Path.home()` pin reds);
    - make `assert_untouched` ignore files (its fixed-input test reds);
    - for U2, in `store.py`, let `fetchmany` re-raise the raw DuckDB
      exception, in place with a `cp` backup (the `fetchmany` pin and the
      deterministic fetch-interruption pin red); separately, the same for
      `fetchall` (the `fetchall`
      pin reds).
  - **Observable:** `uv run pytest tests/query/test_fixtures.py
    tests/query/test_store_facade.py` is green, and each confirmation is
    recorded in Implementation Notes with its `analytics-index` task.
  - _Requirements: 4.2, 6.1_

- [x] 1.2 Append the statement-type facade method
  - **The method.** Append `IndexConnection.statement_types(sql)` to
    `store.py`, per design.md § StoreFacadeAddition:
    - it returns DuckDB's statement-type names, without the `StatementType.`
      prefix;
    - it returns `()` for empty or comment-only text;
    - a parse error raises `IndexStatementError`, chained.

    Nothing else in `store.py` changes.
  - **Tests** (`tests/query/test_store_facade.py`, statement-types section,
    with HOME at `home_dir`):
    - `SELECT`, `WITH`, `FROM`, `VALUES`, `DESCRIBE`, `SHOW`, `SUMMARIZE` and
      table-valued `PRAGMA` give `("SELECT",)`; `EXPLAIN ANALYZE` gives
      `("EXPLAIN",)`;
    - `INSTALL httpfs` and `LOAD httpfs` give `("LOAD",)`, parsed only, never
      executed;
    - `SET`, `RESET`, `USE` and `SET VARIABLE` give `("SET",)`;
    - `CALL` and `CHECKPOINT` give `("CALL",)`;
    - `CREATE TEMP TABLE` and `CREATE SECRET` give `("CREATE",)`;
    - `COPY`, `ATTACH`, `DETACH` and `EXPORT` each give their own type;
    - `"SELECT 1; SELECT 2"` gives two;
    - `""`, whitespace and `-- c` give `()`;
    - `SELEC 1` raises `IndexStatementError` whose `__cause__` is set;
    - a positive control: an `execute` spy shows that no call executed a
      statement.
  - **Mutations:**
    - return `str(statement.type)`, keeping the prefix (the type pins red);
    - return `()` on a parse error (the parse-error pin reds).
  - **Observable:** the statement-types section is green.
    `git diff --stat src/fitdocs/index/store.py` shows one appended method, and
    the `analytics-index` store and boundary suites stay green.
  - _Requirements: 1.5, 5.2_

- [x] 1.3 Create the query package, the indexed fixtures and the importer guards
  - **The package.** `src/fitdocs/query/__init__.py` is a docstring only: the
    read side, never imports `duckdb`, imported only by `fitdocs.cli`.
  - **`_INDEX_IMPORTERS`**: append the five query modules design.md and
    `analytics-index` task 7.3 name (`fitdocs.query.sandbox`,
    `fitdocs.query.statement`, `fitdocs.query.freshness`,
    `fitdocs.query.schemaview`, `fitdocs.query.command`), with a comment
    naming the task that creates each. 1.1 confirmed the guard is a one-way
    allow-list (`analytics-index` task 7.3). Doing it here keeps the `(P)`
    tasks 4.1 and 4.2 from editing the same line.
  - **`tests/query/_helpers.py`**, the one owner of the shared non-fixture
    helpers. Callers set HOME.
    - **`plain_database(path, *statements) -> Path`**: creates a DuckDB file
      through `store.create_index` and facade `execute`, with no
      bookkeeping.
    - **`schema_only_index(path) -> Path`**: `store.create_index`, then
      `store.create_schema(registry.registered_tables())`, then close.
      Nothing else: no refresh and no `apply_descriptions`.
    - **`FIXTURE_TODAY`**: a fixed `date(2021, 10, 1)`, after every fixture
      activity.
    - **`DerivedInputs`** (`files: Mapping[str, str]`, `athlete_toml: str`)
      and **`write_fixture_inputs(root, base_athlete_toml, inputs)`**:
      - writes `athlete.toml` as the base text followed by
        `inputs.athlete_toml`;
      - writes every extra file;
      - refuses a path outside `root`.
    - **`copy_indexed_root(src_root, src_index_dir, dst) -> (root, index_dir)`**:
      - copies the data root to `dst/root`;
      - resolves `resolve_index_location(dst/root,
        environ={"FITDOCS_INDEX_DIR": str(dst/"index-cache")}, home=dst/"home")`;
      - creates that location's directory;
      - copies the source `index.duckdb`, and `index.duckdb.wal` if present,
        to it.

      The per-data-root key hashes the resolved path, so a data-root copy
      alone would be NOT_BUILT.
  - **`tests/query/conftest.py`** gains the indexed fixtures:
    - **`derived_inputs()`**: the cross-spec append point. At this task it
      returns `DerivedInputs(files={}, athlete_toml="")`.
    - **`indexed_root`** is module-scoped. Inside `pytest.MonkeyPatch.context()`,
      for its whole body:
      - HOME and `FITDOCS_INDEX_DIR` are set to `tmp_path_factory`
        directories;
      - `XDG_CACHE_HOME` is deleted;
      - `fitdocs.cli._today` is pinned to `FIXTURE_TODAY`.

      It builds a data root through the real CLI (`CliRunner`), in this
      order:
      1. `fitdocs.toml` with `[tiles] enabled = false`;
      2. `write_fixture_inputs`, with a base `athlete.toml` declaring
         `profile_version = 2`, `ftp_watts`, `resting_hr_bpm`, `max_hr_bpm`,
         `hr_zones`, `power_zones` and `pace_zones`, plus `derived_inputs()`;
      3. `fitdocs sync` over the builder's run and ride files
         (`--no-prompt`);
      4. one page hand-tagged with the `contract.EFFORT_KEYS` keys, with
         pairwise-distinct values;
      5. `fitdocs index`.

      It returns the data root and its index directory. At teardown it
      asserts its HOME directory is still empty.
    - **`use_indexed_root(monkeypatch)`** is function-scoped. It points
      `FITDOCS_INDEX_DIR` at the fixture's index directory and pins
      `fitdocs.cli._today` to `FIXTURE_TODAY`.
    - **`copy_indexed_root(tmp_path)`** is function-scoped and wraps the
      helper. Tests never write into `indexed_root`; a test that needs another
      state works on a copy.
  - **Fixture self-tests** (`tests/query/test_fixtures.py`, builders section),
    read through `store.open_index(read_only=True)` with HOME at `home_dir`:
    - the index holds two or more pages;
    - `zone_times` has rows for `heart_rate`;
    - `loads` has a selected row;
    - exactly one `pages` row has a non-NULL `effort`, with the tagged values;
    - the index directory is not under `_REAL_HOME`;
    - every `pages.date` is before `FIXTURE_TODAY`;
    - `write_fixture_inputs` with a non-empty append (a `[benchmarks]` table)
      leaves every base key readable through `load_athlete_inputs`, and the
      appended table present: a fixed-input test on a `tmp_path` root;
    - `write_fixture_inputs` refuses an extra file path outside the root;
    - `schema_only_index` gives a file whose catalog holds the registered
      tables and zero rows;
    - a `copy_indexed_root` copy opens with no NOT_BUILT, and its page drift is
      zero (asserted with `scan_workout_pages` against `read_bookkeeping`
      directly; `page_drift` arrives in 4.1).
  - **The importer guard** (`tests/query/test_boundary.py`, importers section).
    An AST walk of `src/fitdocs` covers `import X`, `from X import`, aliases,
    and string arguments to `importlib.import_module`/`__import__`. No module
    outside `fitdocs.query` imports `fitdocs.query`, except `fitdocs.cli`.
    Positive controls: `scanned > 100`, and a synthetic violating module is
    caught.
  - **Mutations:**
    - add `import fitdocs.query` to `src/fitdocs/history/engine.py`, in place,
      with a `cp` backup restored (the importer guard reds);
    - drop `hr_zones` from the fixture's `athlete.toml` (the zone self-test
      reds);
    - skip the effort edit (the effort self-test reds);
    - make `copy_indexed_root` copy only the data root (the copy self-test
      reds with NOT_BUILT);
    - make `indexed_root` leave `FITDOCS_INDEX_DIR` unset. The index then
      resolves under the fixture's temporary HOME, and the teardown "HOME
      still empty" assertion reds. `XDG_CACHE_HOME` is deleted inside the
      context, so a user-level XDG cache cannot catch the write;
    - make `write_fixture_inputs` write only `inputs.athlete_toml` (the
      base-keys-survive pin reds);
    - drop the `_today` pin (record whether any fixture value moves; with no
      derived producer registered it may be UNPINNED, and is noted as
      such).
  - **Observable:** `uv run pytest tests/query tests/index/test_boundary.py`
    is green, `uv run python -c "import fitdocs.query"` imports nothing from
    DuckDB, and the real `~/.cache/fitdocs` gains nothing (listed before and
    after).
  - _Requirements: 7.3, 11.4_

- [ ] 2. Core: output rendering and the sandboxed connection

- [x] 2.1 (P) Render results as a table, CSV or JSON
  - **`format.py`**, per design.md § Format:
    - `OutputFormat`, `ResultSet` and `default_format`;
    - `render_result`;
    - `text_value`, `table_cell`, `csv_field` and `json_value`;
    - a hand-written JSON writer that emits a `Decimal` as an exact number
      token.

    Every rule in the value-rules table, the table layout and footer, the CSV
    quoting with LF endings, and the JSON key order.
  - **Tests** (`tests/query/test_format.py`), on in-memory `ResultSet`s only:
    - one parametrized case per value-rules row;
    - NULL, `0`, `0.0`, `""`, `False` and `"NULL"` render pairwise-distinct in
      `csv` and `json`, and NULL renders `NULL` in `table`;
    - repeated column names survive in `json`;
    - `Decimal("1E+2")` renders `100`;
    - NaN, `inf` and `-inf` render as `NaN`/`Infinity`/`-Infinity` in all
      three formats;
    - `timedelta(days=1, seconds=3661.5)` renders `P1DT1H1M1.5S`, and zero
      renders `PT0S`;
    - `\n`, `\t` and `\x01` inside a value are escaped in `table`, and quoted
      in `csv`;
    - the truncated footer and the `truncated` flag;
    - zero rows in each format;
    - `default_format(True)` gives `table` and `default_format(False)` gives
      `csv`.
  - **The format-purity guard** (`tests/query/test_boundary.py`, a new
    section): `fitdocs/query/format.py` imports standard-library modules only.
    Positive control: a synthetic module importing `fitdocs.index` is
    flagged.
  - **Mutations:**
    - render NULL as `""` in `csv` (the NULL-versus-empty pin reds);
    - drop the empty-string quoting;
    - render NaN as `null`;
    - use `str(Decimal)` (the `1E+2` pin reds);
    - swap the two defaults;
    - add `import fitdocs.index.schema` to `format.py` (the purity guard
      reds).
  - **Observable:** `uv run pytest tests/query/test_format.py
    tests/query/test_boundary.py` is green, and mypy is clean on `format.py`.
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9, 2.10, 3.3_
  - _Boundary: Format_

- [x] 2.2 (P) Open the index read-only inside a verified, bounded sandbox
  - **`sandbox.py`**, per design.md § Sandbox, without spill handling (that is
    2.3):
    - `RESOURCE_SETTINGS`;
    - `REQUIRED_SANDBOX`, as a literal never derived from the store's map;
    - `SandboxUnverified`, `IndexBusy`, `verify_sandbox`;
    - `open_sandboxed`, with the lock-retry schedule, `LOCK_RETRY_WINDOW_S`,
      the injected `monotonic`/`sleep`/`on_wait`, and closing on a failed
      verification.
  - **Tests** (`tests/query/test_sandbox.py`, with HOME at `home_dir`, on
    `plain_database` files):
    - every key of `store.MANDATORY_SETTINGS` is in `REQUIRED_SANDBOX`;
    - on a real `open_sandboxed` connection, each `REQUIRED_SANDBOX` value
      reads back. `memory_limit` and `max_temp_directory_size` equal the
      strings the locked release reports, recorded in Implementation Notes
      (`953.6 MiB` was probed for `1GB`);
    - with `store.MANDATORY_SETTINGS` monkeypatched without
      `enable_external_access`, `open_sandboxed` raises `SandboxUnverified`
      naming it, and the connection is closed (a spy);
    - **retry**:
      - with a fake clock and a `hold_index(read_only=False)` holder, the
        sleeps equal the schedule capped at the 10.0 s window;
      - `on_wait` fires exactly once, with the holder's PID;
      - `IndexBusy.holder_pid` equals the holder's PID;
    - with a `hold_index(read_only=True)` holder, the open succeeds with no
      sleep (8.5);
    - a `CORRUPT` fault (a junk file) propagates as `IndexOpenError` without a
      retry.
  - **Mutations:**
    - compute the expected map from `store.MANDATORY_SETTINGS` inside
      `verify_sandbox` (the monkeypatched read-back pin reds);
    - drop `enable_external_access` from `store.MANDATORY_SETTINGS`, in place,
      with a `cp` backup (the real read-back pin reds);
    - drop the `LOCKED` retry (the schedule pin reds);
    - use `<` instead of `<=` for the window (the schedule pin reds);
    - open with `read_only=False` (the read-only-holder pin reds).
  - **Observable:** `uv run pytest tests/query/test_sandbox.py` is green, HOME
    stays empty, and no holder process survives.
  - _Requirements: 5.1, 5.4, 5.6, 5.8, 6.2, 8.3, 8.4, 8.5_
  - _Boundary: Sandbox_
  - _Depends: 1.3_

- [ ] 2.3 Give every query process its own spill directory and remove stale ones
  - **`sandbox.py`** gains `SPILL_PREFIX`, `spill_directory`,
    `process_is_running`, the module-level hook `_SKIPS_SPILL_CLEANUP` and
    `remove_stale_spill`, per design.md. `open_sandboxed` sets
    `temp_directory` to `spill_directory(location, pid)`.
  - **Tests** (`tests/query/test_spill.py`):
    - **Setup.** A module-scoped `plain_database` holds a 3M-row table, built
      inside `pytest.MonkeyPatch.context()` with HOME at a `tmp_path_factory`
      directory that is asserted empty at teardown.
      `sandbox.RESOURCE_SETTINGS` is monkeypatched to `memory_limit='48MB'`.
    - A sorted group-by creates `query-spill-<pid>/`, observed by a watcher
      thread.
    - The directory is absent after close, and `index.duckdb.tmp` never
      exists.
    - **Concurrency.** Four subprocesses, each opening with `open_sandboxed`,
      run a spilling window query at the same time. Every one returns the
      reference result computed with a large memory limit.
    - **`remove_stale_spill`**, with directories planted in a `tmp_path` index
      directory:
      - it removes the directory of a dead PID (a reaped subprocess's PID);
      - it keeps a live sleeping subprocess's directory;
      - it keeps its own PID's directory, with `is_running` injected as
        always-false;
      - it does not follow a symlink with a dead-PID name pointing at a
        populated directory outside the index directory: the target and its
        contents survive, and the link is not in the returned tuple;
      - it keeps `index.duckdb`, and a populated `writer-spill/` directory
        (the writer's, `analytics-index`'s), named by its literal;
      - with `_SKIPS_SPILL_CLEANUP` patched true and a removable dead-PID
        directory present, it returns `()` and the directory survives. The
        hook is patched, never `os.name`, because a `Path` built while
        `os.name == "nt"` raises on 3.11.
    - `process_is_running` gives `True` for the current PID and `False` for a
      reaped PID.
  - **Mutations:**
    - drop the `temp_directory` setting (the concurrency pin reds; record the
      red rate over 5 runs);
    - drop the liveness check (the live-PID pin reds);
    - drop the own-PID check (the own-PID pin reds);
    - follow symlinks, `shutil.rmtree(path.resolve())` (the symlink-target pin
      reds);
    - ignore the hook (the hook pin reds);
    - match any directory whose name ends in `spill` and carries no live PID,
      instead of `^query-spill-(\d+)$` (the `writer-spill/` pin reds).
  - **Observable:** `uv run pytest tests/query/test_spill.py` is green, no
    `query-spill-*` directory or subprocess survives, and HOME stays empty.
    A `writer-spill/` left in the setup's own tmp directory does not count:
    `plain_database` builds through `store.create_index`, a writer connection
    whose `temp_directory` is `writer-spill/` (`analytics-index`'s
    `WRITER_SPILL_DIRNAME`), and DuckDB's removal of it on close is unprobed.
  - _Requirements: 6.3, 6.4, 7.3_

- [ ] 3. Core: one screened, timed statement

- [ ] 3.1 Execute a statement under the time limit and row cap, and classify its failures
  - **`statement.py`**, per design.md § Statement:
    - `Restriction`, `RESTRICTION_TEXT`;
    - `StatementRefused`, `StatementFailed`, `StatementTimedOut`;
    - `classify_statement_error`, `failure_hint`;
    - `execute_statement`, with the timer that records it fired before
      calling `interrupt`, the `fetchmany(max_rows + 1)` cap, and the timer
      cancelled in `finally`.
  - **Tests** (`tests/query/test_statement.py`, execution section, on a
    sandboxed `plain_database`, with HOME at `home_dir`):
    - **The configuration refusals** through `execute_statement`, each
      classified OUTSIDE_INDEX:
      - `read_csv('<tmp>/x.csv')`, `read_text('/etc/hosts')` and
        `glob('/etc/*')`;
      - `read_csv('https://example.invalid/x.csv')`, whose id carries `url`;
      - `COPY (SELECT 1) TO '<tmp>/out.csv'` and
        `EXPLAIN ANALYZE COPY (SELECT 1) TO '<tmp>/out2.csv'`, with both files
        absent afterwards;
      - `EXPORT DATABASE '<tmp>/exp'`, with no directory afterwards;
      - `ATTACH '<tmp>/other.duckdb' AS o`.
    - `SET threads = 8` and `SET autoinstall_known_extensions = true` are
      classified LOCKED_SETTING.
    - **The classifier**, fixed-input tests over exceptions captured from the
      facade:
      - a binder error gives `None`;
      - `ATTACH ':memory:'` gives READ_ONLY;
      - `CREATE SECRET s (TYPE S3, KEY_ID 'x', SECRET 'y')` gives EXTENSION,
        with a stable message and no URL;
      - a `SELECT now()` fetch gives `None`, with the TIMESTAMP hint;
      - a synthetic cause named `OutOfMemoryException` gives the memory hint.
    - **The time limit**: `SELECT count(*) FROM range(1000000000000)` with
      `timeout_s=0.5` raises `StatementTimedOut` within 3 s. The test arms its
      own 10 s safety interrupt, so a missing timer reds rather than hangs.
    - **The row cap**: `range(1001)` with `max_rows=1000` gives 1000 rows and
      `truncated=True`; `range(1000)` gives `truncated=False`.
    - The timer is cancelled after both success and failure (a timer spy).
  - **Mutations** (the first two run with `-k 'not url'`):
    - drop `enable_external_access` from both `store.MANDATORY_SETTINGS` and
      `REQUIRED_SANDBOX`, in place, with `cp` backups (DuckDB runs the `COPY`,
      the tmp file appears, and the OUTSIDE_INDEX pins red);
    - drop `lock_configuration` from both (the `SET` pins red);
    - classify by message stems only (the class-name pin reds);
    - never start the timer (the time-limit pin reds through the safety
      interrupt);
    - use `fetchmany(max_rows)` (the `truncated` pin reds).
  - **Observable:** the execution section is green, HOME stays empty, and no
    file appears under the test's tmp targets.
  - _Requirements: 3.1, 3.4, 4.2, 5.3, 5.5, 5.8, 6.1_
  - _Depends: 2.1, 2.3_

- [ ] 3.2 Refuse every statement that is not exactly one query or EXPLAIN
  - **`statement.py`** gains `ALLOWED_STATEMENT_TYPES`, `screen_statement` and
    `run_statement` (screen, then execute), per design.md. The
    STATEMENT_KIND text names LOAD as "INSTALL or LOAD" and SET as "SET, RESET
    or USE", and its CALL hint points at `SELECT * FROM <function>(…)`.
  - **Tests** (`tests/query/test_statement.py`, gate section). Each runs
    through `run_statement` on a real sandboxed connection, with
    `statement.execute_statement` monkeypatched to a non-forwarding recorder:
    - `INSTALL httpfs`, `LOAD httpfs`, `ATTACH ':memory:' AS m`,
      `COPY (SELECT 1) TO 'x.csv'`, `EXPORT DATABASE 'x'`, `SET threads = 1`,
      `RESET threads`, `USE system`, `SET VARIABLE v = 1`,
      `CREATE TEMP TABLE t AS SELECT 1`, `CALL pragma_version()` and
      `CHECKPOINT` each raise STATEMENT_KIND, and the recorder is never
      called;
    - `SELECT 1; SELECT 2` and `-- only a comment` raise ONE_STATEMENT, with
      no recorder call;
    - `SELECT 1`, `FROM t` (on a `plain_database` table), `DESCRIBE t`,
      `PRAGMA table_info('t')` and `EXPLAIN SELECT 1` each reach the recorder
      exactly once;
    - a parse error propagates as `IndexStatementError`, with no recorder
      call.
  - **Mutations:**
    - add `LOAD`, then `SET`, then `CALL`, then `CREATE`, then `COPY` to
      `ALLOWED_STATEMENT_TYPES`, each in turn (its pins red, and the recorder
      shows a call; nothing executes);
    - drop the statement-count check (the ONE_STATEMENT pins red);
    - call `execute_statement` before screening (every gate pin reds).
  - **Observable:** the gate section is green, and the recorder confirms that
    no refused statement reached execution.
  - _Requirements: 1.5, 5.2, 5.5, 5.8_

- [ ] 4. Core: freshness and the schema catalog

- [x] 4.1 (P) Measure how far the index is from the data root
  - **`freshness.py`**, per design.md § Freshness:
    - `PageDrift`/`page_drift`;
    - `CorpusDrift`/`corpus_fingerprints`/`corpus_drift`.
      `corpus_fingerprints(scan, held, *, data_root, today,
      athlete_fingerprint)` builds the snapshot once with
      `corpus.corpus_snapshot(data_root, scan, today=…, athlete_fingerprint=…,
      held=frozenset(held))`, where `held` is the bookkeeping's page mapping.
      It then calls `fingerprint.combined_corpus_fingerprint(producer,
      snapshot)` for each `registry.CORPUS_PRODUCERS` entry, read as a module
      attribute at call time. It assembles no `CorpusSnapshot`, composes no
      fingerprint by hand, and takes no version;
    - `AthleteDrift`/`current_athlete_fingerprint`/`athlete_drift`, including
      the unreadable-profile rule (corpus drift unassessed).
  - **Tests** (`tests/query/test_freshness.py`, on `copy_indexed_root` copies,
    with HOME at `home_dir`):
    - **Pages**, each change alone. Assert first that the counts are all 0,
      then each change gives its own count:
      - a new page gives `added == 1`;
      - a hand-edited `effort` gives `changed == 1`;
      - a deleted page gives `removed == 1`;
      - a rename gives `changed == 1` and `added == 0`;
      - a duplicate-base page gives `added == 0` and appears in
        `scan.left_out`.
    - After rebuilding the copy in-process with `build.run_index_command`, the
      counts return to 0.
    - **Corpus**, against fingerprints the refresh itself recorded. The setup,
      on one copy:
      - **The registry.** `registry.CORPUS_PRODUCERS` is monkeypatched to
        exactly `(fake,)`: `analytics-index`'s core-only corpus tier, `()`,
        plus the fake. It never appends to the landed tuple, so a producer
        `analytics-derived` registered never enters these exact assertions.
        (`analytics-index`'s `core_registry` fixture is in
        `tests/index/conftest.py`, which `tests/query/` cannot reach.)
      - **The fake** declares one table, and its `rows` returns one row. Its
        `fingerprint` hashes `today`, the `(path, document_fingerprint)` list
        of `snapshot.pages`, the same list of `snapshot.left_out` as a
        separate list, and the bytes of one test-controlled file in the data
        root.
      - **The version.** `fitdocs.version.tool_version` is monkeypatched to
        return a fixed string (`"0.0.0+query-test"`) for the whole test. The
        refresh's `combined_corpus_fingerprint` reads it at call time, so the
        recorded version is known whatever the install.
      - **The build.** The copy gains a duplicate-base page, made as the pages
        case makes one. Then its index is rebuilt in-process with
        `build.run_index_command(rebuild=True, today=FIXTURE_TODAY)` under the
        monkeypatches. The fixture's own index was built without the fake, so
        it has no state for it.
      - **Each assessment** calls `corpus_fingerprints` with `held` set to
        `read_bookkeeping(…).pages` of the copy's index and
        `today=FIXTURE_TODAY`.

      The assertions:
      - **Post-build.** After that build, `corpus_drift.behind == ()` and
        nothing is unassessed. Assert first that the scan's `left_out` holds
        the duplicate-base page.
      - **Page error.** Add a new page to the copy. Append a test-only
        document producer with no tables (`tables=()`) to
        `registry.DOCUMENT_PRODUCERS`, as a monkeypatch on the landed tuple,
        that raises on that page. Then run `build.run_index_command(
        rebuild=False, today=FIXTURE_TODAY)`, the incremental refresh
        (`analytics-index` design.md § Build, step 4). Assert first that the
        new page's key is in the scan and not in the bookkeeping's pages.
        Then, with the data root unchanged, `corpus_drift.behind == ()`: the
        refresh recorded that page in `left_out`, and so does the
        reproduction.
      - **Moved input.** Changing the fake's input file lists its table.
      - **Raising fingerprint.** A raising fingerprint becomes unassessed.
    - **Athlete**:
      - on the unmodified copy, the count is 0;
      - changing `ftp_watts` in `athlete.toml` counts every activity;
      - a malformed `athlete.toml` gives `skipped_reason` and runs no query
        (a facade spy).
    - The data root and the index directory are byte-identical before and
      after every assessment (9.5).
  - **Mutations:**
    - count `left_out` as added (the duplicate pin reds);
    - key by path instead of `page_key` (the rename pin reds);
    - compare against `index_meta.athlete_fingerprint` instead of
      `athlete.toml` (the athlete pin reds);
    - build the snapshot with `held=None` (the page-error pin reds: the failed
      page lands in `pages`, not `left_out`);
    - assemble `CorpusSnapshot(data_root, pages=<a CorpusPage per
      scan.pages>, left_out=(), today, athlete_fingerprint)` by hand instead
      of calling `corpus_snapshot` (the post-build pin reds: the refresh's
      `left_out` holds the duplicate-base page);
    - compose `corpus_fingerprint(producer.fingerprint(snapshot),
      fitdocs_version=None, schema_version=SCHEMA_VERSION)` by hand instead
      of calling `combined_corpus_fingerprint` (the post-build pin reds
      against the pinned `tool_version`);
    - bind `CORPUS_PRODUCERS` with `from fitdocs.index.registry import
      CORPUS_PRODUCERS` at import (the monkeypatched fake is never assessed;
      the moved-input pin reds).
  - **Observable:** `uv run pytest tests/query/test_freshness.py` is green, and
    mypy is clean.
  - _Requirements: 9.1, 9.3, 9.5, 10.3, 10.4_
  - _Boundary: Freshness_
  - _Depends: 1.3_

- [ ] 4.2 (P) Read the live catalog and render the schema reference
  - **`schemaview.py`**, catalog part, per design.md § SchemaView:
    - `CatalogColumn`/`CatalogTable`;
    - `read_catalog`, with the `current_database()`/`main`/not-temporary
      filters and the table order;
    - `row_counts`, with quoted identifiers;
    - `unit_of`, over `schema.UNIT_SUFFIXES`, longest first;
    - `undescribed`;
    - `render_reference`.
  - **Tests** (`tests/query/test_schemaview.py`, catalog section, with HOME at
    `home_dir`):
    - `read_catalog` on a sandboxed `schema_only_index` excludes system views
      and a temporary table created in the test (the positive control: the
      temp table exists before the read);
    - for every registered column, `unit_of` returns the suffix's unit word,
      and that word appears in the stored description;
    - a `plain_database` table created without comments is listed with `None`
      descriptions and named by `undescribed`, which also has a fixed-input
      test;
    - `render_reference` escapes `|`, and is identical across two calls;
    - **10.9**: a `schema_only_index` (`create_index` +
      `create_schema(registered_tables())`, no refresh) has
      `undescribed(read_catalog(…)) == ()`, with `len(tables) >= 13` asserted
      first.
  - **Mutations:**
    - drop the `database_name = current_database()` filter (system views
      appear and the exclusion pin reds);
    - match unit suffixes shortest-first (the `_s_per_km` and `_kn_m` pins
      red);
    - make `store.create_schema` skip `COMMENT ON COLUMN`, in place, with a
      `cp` backup (the 10.9 pin reds, since no `apply_descriptions` runs on
      this path);
    - let `undescribed` skip columns (its fixed-input test reds).
  - **Observable:** the catalog section is green, and mypy is clean.
  - _Requirements: 10.1, 10.5, 10.9, 12.5_
  - _Boundary: SchemaView_
  - _Depends: 2.2_

- [ ] 5. Integration: the state view, the command, the CLI and the guards

- [ ] 5.1 Render the index state and the full schema view
  - **`schemaview.py`** gains `IndexState`, `render_state_text`,
    `render_schema_text` and `render_schema_json`, per design.md:
    - the state lines;
    - `(N rows)` on each table heading;
    - the undescribed closing line;
    - the schema JSON keys, written through `format.json_value`.
  - **Tests** (`tests/query/test_schemaview.py`, state section, on
    hand-built `IndexState`s, whose `LeftOutPage`s carry all four fields,
    `document_fingerprint` included):
    - every state field appears in the text: the path, both schema versions,
      the fitdocs version, held against workout pages, each left-out page
      with its reason, the three drift counts, the without-computed counts by
      state, the athlete count or skip reason, the corpus tables behind, and
      the rebuild reason;
    - the JSON parses, and its keys equal design.md § Data Models, each
      `left_out` entry exactly `path`, `reason` and `collides_with` (the
      document fingerprint is not printed);
    - an undescribed column produces the defect line.
  - **Mutations:**
    - drop the left-out lines (their pin reds);
    - omit `reads_schema_version` from the JSON (the key-set pin reds).
  - **Observable:** the state section is green.
  - _Requirements: 10.2, 10.5, 10.6_
  - _Depends: 4.1, 4.2_

- [ ] 5.2 Orchestrate one invocation, from location to outcome
  - **`command.py`**, per design.md § Command:
    - `DEFAULT_MAX_ROWS`, `DEFAULT_TIMEOUT_S`;
    - `QueryRequest`, `QueryEnvironment`, `OutcomeKind`, `SchemaReport`,
      `QueryOutcome`;
    - `run_query`, in design.md's order: stale spill, the existence check, the
      scan (plus the athlete fingerprint for `--schema`), the sandboxed open,
      bookkeeping and version checks, the statement or schema path,
      `finally: close()`, then the page drift and, for `--schema`,
      `corpus_fingerprints(scan, bookkeeping.pages, …)` and the corpus drift.
      The corpus fingerprints come after close because `held` is the
      bookkeeping's.
  - **Tests** (`tests/query/test_command.py`, on copies, with HOME at
    `home_dir`). Each `OutcomeKind` comes from a real state:
    - **NOT_BUILT**:
      - there is no file, and nothing is created in the index directory;
      - **by race**: a `scan_workout_pages` spy deletes `index.duckdb` after
        the existence check. The read-only open's MISSING fault still gives
        NOT_BUILT.
    - **NEEDS_REBUILD**:
      - a junk file;
      - `forge_storage_version(…, 69)`;
      - a database without `index_meta` (`plain_database`);
      - `schema_version` 99, written on a copy through a read-write
        `store.open_index`;
    - **BUSY**: `hold_index` with a fake clock.
    - **UNVERIFIED**: a monkeypatched mandatory map.
    - **REFUSED, FAILED and TIMED_OUT**: FAILED is covered by both a binder
      error and a parse error.
    - **RESULT**: the rows equal a direct facade read.
    - **SCHEMA**: drift is reported on a behind copy.
    - **State assembly.** On a copy, delete one page's base archive file and
      add a duplicate-base page (a copied page file under a new name), then
      rebuild the copy with `fitdocs index`. The SCHEMA outcome's state has
      `without_computed == {"source_missing": 1}` and one left-out entry
      naming `duplicate_base` and the page it collides with.
    - **Stale spill.** Plant `query-spill-<reaped pid>/` and
      `query-spill-<live sleeping pid>/` in the copy's index directory. After
      `run_query`, the first is gone and the second is kept.
    - **Ordering**: a spy shows `scan_workout_pages` ran before `open_index`.
    - **Corpus inputs** (`--schema`): on a copy holding a page added after its
      build, so the scan's keys differ from the bookkeeping's (asserted
      first), a forwarding spy on the `corpus_fingerprints` that `run_query`
      calls records that it ran after `close()`, and that its `held` equals
      `read_bookkeeping(…).pages` of the copy.
    - **Close**: a connection spy shows `close()` on every outcome, and on a
      `KeyboardInterrupt` raised from a monkeypatched `execute_statement`,
      which propagates.
  - **Mutations:**
    - scan after opening (the ordering pin reds);
    - drop the `finally` (the `KeyboardInterrupt` close pin reds);
    - treat a schema-version mismatch as RESULT;
    - map `MISSING` to NEEDS_REBUILD (the race pin reds);
    - drop the `remove_stale_spill` call (the stale-spill pin reds);
    - leave `without_computed` empty (the state-assembly pin reds);
    - hand `corpus_fingerprints` a mapping keyed by the scan's page keys
      instead of the bookkeeping's (the corpus-inputs pin reds).
  - **Observable:** `uv run pytest tests/query/test_command.py` is green, and
    HOME stays empty.
  - _Requirements: 1.6, 4.3, 6.4, 6.6, 8.1, 8.2, 10.2, 10.4, 10.7, 10.8_

- [ ] 5.3 Add the `fitdocs query` command
  - **`cli.py`**, per design.md § CliWiring:
    - the option singletons (`--file`, `--schema`, `--format` as a
      case-insensitive `OutputFormat` choice, `--max-rows` with `min=1`,
      `--timeout`, `--out`);
    - `query_command`, `_read_statement` (strict UTF-8; `-` reads
      `sys.stdin.buffer`) and `_stdout_is_terminal`;
    - the validation order;
    - results to stdout via `typer.echo(text, nl=False)`;
    - every line in design.md's table to a stderr `Console` with
      `markup=False, highlight=False, soft_wrap=True`;
    - the exit mapping;
    - `render_state_text` on stderr for `--schema` failures that read a state;
    - the docstring's first paragraph, a plain sentence;
    - the module docstring count, "Twelve" becomes "Thirteen", with the
      `query` entry and its exit codes.

    `tests/test_cli_skill.py:262-270` goes from 12 to 13, and "Thirteen".
  - **Tests** (`tests/query/test_cli_query.py`, `use_indexed_root` and
    `home_dir`):
    - **Forms**:
      - the SQL argument;
      - `--file`, and `--file` holding undecodable bytes (exit 2);
      - `-` with CliRunner input;
      - none, two sources, and `--schema` with SQL (each exit 2, with
        `open_index` never called: a spy);
      - whitespace only (exit 2);
      - comment only (exit 1, the ONE_STATEMENT line).
    - **Options**:
      - piped output defaults to `csv`;
      - `_stdout_is_terminal` monkeypatched to `True` gives `table`;
      - `--max-rows 0`, `--timeout 0`, `--timeout nan` and
        `--schema --format csv` each exit 2.
    - **Streams**: stdout parses as exactly the CSV or JSON result. The
      truncated, behind and waiting lines appear only on stderr.
    - **Exit codes**: one case per row of design.md § Error Categories, each
      asserting the exact line.
    - **`--schema`**:
      - exit 0 on the fixture, behind or not;
      - exit 1 with the not-built line when absent;
      - on a `schema_version` 99 copy: exit 1, with stderr showing `99` and
        the rebuild line;
      - `--format json` parses.
  - **Mutations:**
    - swap the defaults (the TTY pin reds);
    - print the behind notice to stdout (the streams pin reds);
    - exit 0 on REFUSED;
    - accept `--timeout 0`;
    - drop the state print on `--schema` failures (the `99` pin reds);
    - leave the count at "Twelve" (`tests/test_cli_skill.py` reds).
  - **Observable:** the CLI tests and `tests/test_cli_skill.py` are green.
    `uv run fitdocs query --help` lists every option, and its first line is
    the plain sentence.
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 2.2, 2.3, 3.2, 3.5, 4.1, 4.4, 4.5, 6.5, 9.2, 9.4, 10.6, 10.7, 10.8_

- [ ] 5.4 Extend the confinement, network, boundary and crash-vector guards to `query`
  - **`tests/test_confinement.py`**: append a standalone
    `test_query_writes_nothing_outside_its_spill_directory`, modelled on
    `test_connect_writes_only_the_credentials_file`.
    - **The sandbox** holds the data root, `FITDOCS_INDEX_DIR` and HOME, all
      set by the test itself.
    - **The index** is built inside the sandbox with `fitdocs index`, and the
      snapshot is taken after that.
    - **The runs**: through `CliRunner`, a SELECT, `--schema`, a refused
      `COPY` targeting the sandbox, a `read_csv` of a sandbox file, an
      `ATTACH` of a sandbox file, a parse error, and a 0.5 s timeout.
    - **The checks**: every file's size, `mtime_ns` and sha256 are unchanged,
      and no path is added.
    - **Non-vacuity**: the SELECT printed rows, and each refusal printed its
      line.
  - **`tests/connectors/test_e2e.py:203-246`**: the parametrization gains an
    argument column, keeping every existing entry, `analytics-index`'s `index`
    included.
    - `query` runs with `SELECT count(*) AS n FROM pages`.
    - `fitdocs index` builds each root's index before the socket guard is
      installed.
    - Output is compared with the roots substituted.
    - For the `query` row it also asserts `bare_attempts == 0`.
  - **`tests/query/test_crash_vectors.py`** (subprocess, HOME and
    `FITDOCS_INDEX_DIR` temporary). Each subprocess is invoked as
    `[sys.executable, "-c", "from fitdocs.cli import app; app()", "query",
    …]`, so the interpreter's own DuckDB is the one exercised, the floor venv's
    in 8.2.
    - **Positive control**: a subprocess print of
      `fitdocs.index.store.duckdb_version()` equals the in-process value.
    - `"SELECT * FROM enable_logging(storage='file',
      storage_path='<tmp>/logs'); SELECT 42"` exits 1 with the ONE_STATEMENT
      line, and `<tmp>/logs` does not exist.
    - The single `SELECT * FROM enable_logging(…)` exits 0 or 1, never by a
      signal, and creates no `<tmp>/logs`.
  - **`tests/query/test_boundary.py`, direction section**:
    - each `fitdocs.query` module imports only modules to its left in
      `format → sandbox → statement → freshness → schemaview → command`;
    - no `fitdocs.query` module imports `fitdocs.cli`, `fitdocs.sync`,
      `fitdocs.render`, `fitdocs.connectors`, `fitdocs.tiles`,
      `fitdocs.plugins`, or `fitdocs.index.refresh`, `.build`, `.lock`,
      `.handoff` or `.derive` (7.4);
    - positive controls on synthetic violations.
  - **Mutations:**
    - write a marker file into the data root from `run_query` (the
      confinement pin reds);
    - add a swallowed socket attempt to `run_query`, `try:
      socket.socket(); except Exception: pass`. The existing equal-attempts
      check tolerates it, and `bare_attempts == 0` reds;
    - drop the statement-count check (the multi-statement pin reds on the exit
      code, by a signal abort or by exit 0; the −6 abort was probed for
      `CALL enable_logging(…); SELECT 42`, and this exact text is unprobed);
    - import `fitdocs.index.refresh` from `command.py`, then separately
      `fitdocs.sync` (the direction pin reds each time).
  - **Observable:** the confinement, connectors-e2e, crash-vector and
    boundary suites are green.
  - _Requirements: 1.5, 5.8, 7.1, 7.2, 7.3, 7.4, 7.5, 9.5_

- [ ] 6. The analytics documentation

- [ ] 6.1 Publish `docs/analytics.md` with its schema reference held to the live schema
  - **`docs/analytics.md`**: the seven sections of design.md § Docs and
    Records.
    - The schema reference sits between `<!-- schema-reference:start -->` and
      `<!-- schema-reference:end -->`.
    - The outside-client section gives a DuckDB CLI line (`-readonly` with
      auto-install and auto-load off, and its own `temp_directory`) and a
      Python `duckdb.connect(…, read_only=True, config={…})` snippet.
    - The location section names `FITDOCS_INDEX_DIR`,
      `$XDG_CACHE_HOME/fitdocs/index` and `~/.cache/fitdocs/index`.
  - **Wiring**:
    - a row in `docs/index.md`, before the Contributing row;
    - `"analytics.md"` appended to `_REQUIRED_ENTRY_POINT_LINKS`;
    - `Analytics = "https://github.com/joshua-stauffer/fitdocs/blob/main/docs/analytics.md"`
      appended to `[project.urls]`.
  - **Tests** (`tests/query/test_docs_analytics.py`):
    - the block equals `render_reference(read_catalog(…))` of a
      `schema_only_index` in `tmp_path`, with HOME at `home_dir`;
    - the module's `if __name__ == "__main__":` regeneration:
      - builds its `schema_only_index` inside a `TemporaryDirectory`, with HOME
        at another `TemporaryDirectory`;
      - never resolves an index location. This is pinned in-process: the
        regeneration function is called directly with
        `fitdocs.index.location.resolve_index_location` patched to raise, and
        the function completes;
      - rewrites only the marked block (asserted by running it as a
        subprocess against a temporary copy of the page, with the page path
        passed as an argument);
    - every `fitdocs` line in a `bash` fence names a registered command and
      only its options;
    - the stated defaults equal `DEFAULT_MAX_ROWS` and `DEFAULT_TIMEOUT_S`;
    - the page names `FITDOCS_INDEX_DIR`, `XDG_CACHE_HOME`, `read_only`,
      `-readonly`, `autoinstall_known_extensions`,
      `autoload_known_extensions` and `temp_directory`, case-sensitively,
      outside the generated block;
    - it states that outside clients bypass the sandbox and block refreshes
      (phrase pins).
  - **Mutations:**
    - edit one description string in `src/fitdocs/index/core/documents.py`, in
      place, with a `cp` backup (the block-equality pin reds);
    - state `500` as the default row limit (the defaults pin reds);
    - write `--rows` in a `bash` fence (the command-binding pin reds);
    - make the regeneration resolve the default index location (the
      in-process never-resolves pin, with `resolve_index_location` patched to
      raise, reds).
  - **Observable:**
    - `uv run pytest tests/query/test_docs_analytics.py
      tests/test_docs_guarantees.py tests/test_packaging.py` is green;
    - every anchor in the page resolves;
    - `uv run python -m tests.query.test_docs_analytics` leaves `git diff`
      empty, and the real `~/.cache/fitdocs` gains nothing.
  - _Requirements: 12.1, 12.2, 12.3, 12.4, 12.5, 12.6_
  - _Depends: 4.2, 5.3_

- [ ] 7. The packaged agent skill

- [ ] 7.1 Write and register the `fitdocs-analytics` skill
  - **`src/fitdocs/skills/fitdocs-analytics/SKILL.md`**, per design.md § Skill:
    - the five frontmatter keys;
    - `metadata.version` equal to `[project].version`;
    - the eight H2 headings in order;
    - one `bash` fence and inline `fitdocs query`/`fitdocs index` spans;
    - links only to `https://github.com/joshua-stauffer/fitdocs/…`, including
      the ownership-contract URL and the analytics page.

    The worked-examples section has its four H3s and one `sql` fence each,
    drafted here. Task 7.3 makes them execute.
  - **Spelling rules**:
    - no `OWNED_PATHS` substring anywhere, fences included: no `.cache/`, no
      `'workouts/…'` literal;
    - no `--word` on a `bash` line except registered options;
    - no backticked managed key or region inside `## Ownership`.
  - **Registration.** These land together, because the locator's directory
    check (`tests/test_skill_locator.py:186-194`) and the per-name docs pins
    (`tests/test_wiki_integration_docs.py:113-121, 218-224`) fail on a skill
    directory without its entry, and on an entry without its docs lines.
    - `ANALYTICS_SKILL_NAME = "fitdocs-analytics"`, appended to
      `PACKAGED_SKILLS`, with the agentskill docstring's "Two" becoming
      "Three";
    - `tests/test_skill_locator.py`: `_PUBLIC_NAMES` gains the constant, and
      the registry-order pin appends it;
    - `tests/test_agent_skill.py`: the import, `_ANALYTICS_HEADINGS`, and the
      `_SKILL_PROFILES` entry;
    - `docs/wiki-integration.md`: a listing line and a bullet;
    - `README.md` Agent skills: "Three packaged skills ship today", naming
      it;
    - `release/artifact-policy.toml` `[wheel] required` and the clean-wheel
      fixture `tests/test_release_artifacts.py:978-983`;
    - `docs/releasing.md`: "four tracked places", naming the third skill,
      with `tests/test_releasing_docs.py:569-573` gaining its path.
  - **Tests**: the parametrized skill, locator, wheel, packaging,
    version-identity, wiki-integration, release-artifact and releasing-docs
    suites cover the new skill.
  - **Mutations:**
    - spell `.cache/` in the skill body (the owned-path pin reds);
    - add `--rows` to the `bash` fence (the command-binding pin reds);
    - drop the registry entry (the locator's two-way pins red);
    - drop the README line (the README-section pin reds).
  - **Observable:**
    - `uv run fitdocs skill` lists three skills;
    - `uv run fitdocs skill fitdocs-analytics` prints its directory and the
      `cp -R` recipe;
    - `uv run pytest tests/test_agent_skill.py tests/test_skill_locator.py
      tests/test_skill_wheel.py tests/test_cli_skill.py
      tests/test_wiki_integration_docs.py tests/test_release_artifacts.py
      tests/test_releasing_docs.py tests/test_version_identity.py
      tests/test_packaging.py` is green.
  - _Requirements: 11.1, 11.6, 11.7_
  - _Depends: 6.1_

- [ ] 7.2 Pin the teaching order and point `fitdocs-workouts` at the new skill
  - **The teaching-order pin**, in `tests/test_agent_skill.py` beside the
    profile. The positions of four pinned phrases in the analytics skill
    ascend:
    1. `fitdocs query --schema`;
    2. the prefer-the-index sentence;
    3. the show-the-SQL sentence;
    4. the NULL-is-absent sentence.

    Each phrase is matched case-sensitively, outside fences, and its presence
    is asserted before the order.
  - **`fitdocs-workouts`**: one "Further reading" bullet linking the analytics
    page and naming `fitdocs-analytics`. Its headings are unchanged, and the
    existing inbox-skill pins stay green.
  - **The workouts link pin**, `test_inbox_further_reading_links_the_analytics_doc`
    in `tests/test_agent_skill.py`, modelled on
    `test_inbox_further_reading_links_the_connectors_doc` (`:706`). Within the
    inbox skill's "Further reading" section, a bullet links the exact
    hard-coded literal
    `https://github.com/joshua-stauffer/fitdocs/blob/main/docs/analytics.md`
    and names `fitdocs-analytics`.
  - **Mutations:**
    - move the NULL paragraph before the schema step (the order pin reds);
    - drop the workouts bullet (the workouts link pin reds).
  - **Observable:** `uv run pytest tests/test_agent_skill.py` is green.
  - _Requirements: 11.2, 11.8_

- [ ] 7.3 Make every worked example run against the live schema, one per producer
  - **The core examples**: weekly running volume, time in heart-rate zones,
    selected training load per week, and races, tests and hard efforts.
    - They use the values the index actually stores, checked here: the
      `Sport` values in `activities.sport`, the `zone_times.channel`
      vocabulary, and `loads.selected`.
    - Their date windows are relative to `max(date)`, so they hold on the
      fixture.
  - **Derived producers.** If `analytics-derived` has landed (its producers
    appear in `registered_tables()`), this task is the second lander. It takes
    the four example topics and the fixture inputs from
    `.kiro/specs/analytics-derived/design.md` § PublishedStatements and that
    spec's task 6.2, so both landing orders produce the same artifacts. Read
    both first; where this list and theirs differ, stop and report.
    - **Fixture inputs.** Extend `derived_inputs()` in
      `tests/query/conftest.py` (it returns `DerivedInputs(files=…,
      athlete_toml=…)` from `tests/query/_helpers.py`; `indexed_root` writes
      both before `fitdocs sync`, with `fitdocs.cli._today` pinned to
      `FIXTURE_TODAY`, 2021-10-01):
      - `files`: one valid plan source under the default plan directory
        `plans/` (`fitdocs.layout.DEFAULT_PLANS_DIR`), in the grammar of
        `tests/plans/fixtures/`, dated around `FIXTURE_TODAY`. Its mesocycle
        window covers the fixture's activities (`FIT_TIMESTAMP_BASE`,
        2021-09-08 UTC) and `FIXTURE_TODAY`. It has a planned workout dated
        before `FIXTURE_TODAY` on a day with no activity and no override (not
        logged), and one dated after it (upcoming). `derived_inputs()`
        writes no `fitdocs.toml`, so 1.3's `[tiles] enabled = false` stays;
      - `athlete_toml`: a `[benchmarks]` table appended to the base file,
        which declares `profile_version = 2`. It holds a Ride `ftp_watts`
        entry measured before the fixture's activities (for example
        2021-09-01), equal to the base file's flat `ftp_watts`, so the loads
        the fixture already computes stay put where the profile allows.
    - **Worked examples.** Four H3s under `Worked examples`, one per derived
      producer, each followed by one `sql` fence that selects rows from that
      producer's table. No example is a bare aggregate, and none uses an
      outer join that keeps rows once the producer's tables are emptied.
      Every window is relative to the data, `max(date)` or the table's own
      dates, worded "in the latest year of data": never "this year",
      `current_date`, `now()` or today. Each predicate is checked against
      what `indexed_root` holds before it is written.
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
         two, stop and report rather than drop the filter. `fitdocs.toml` is
         this spec's 1.3 fixture, but changing it here would make the two
         landing orders differ.
      3. **Thresholds in force** (`derived.benchmarks`): the FTP in force on
         each ride's date in the latest year of data (`benchmark_periods`
         joined to the ride pages on `starts_on` and `ends_before`, with
         `ends_before` NULL while in force).
      4. **Planned sessions not logged** (`derived.blocks`): the
         `planned_workouts` rows whose `state` is `not logged`, in the block
         with the latest `starts_on`.

    Otherwise, record in Implementation Notes that the second lander
    (`analytics-derived` task 6.2) does both (Cross-spec shared files).
  - **Tests** (`tests/query/test_skill_examples.py`, `use_indexed_root`, HOME
    at `home_dir`):
    - every `sql` fence of the skill runs through `fitdocs query --format
      json`, exits 0, and has `row_count >= 1`;
    - there are at least four fences, and the four core H3 topics exist;
    - **the generic 11.5 pin, keyed on the producer**:
      - group `registered_tables()` by `ResolvedTable.producer`;
      - exclude scope `TableScope.BOOKKEEPING`, and the core producers named
        by the imported `CORE_DOCUMENTS.name` and `CORE_COMPUTED.name`, never
        spelled out;
      - each remaining producer needs at least one `sql` fence that names one
        of its tables (whole word, case-sensitive) and selects rows from it:
        it returns at least one row on a `copy_indexed_root` copy, and zero
        rows on a second copy where every table of that producer was emptied
        through a read-write `store.open_index`.
    - **The helper's fixed-input tests**:
      - a monkeypatched extra producer, with a one-row table and no example,
        is reported missing;
      - an example `SELECT count(*) AS n FROM <that table>` is reported as
        not selecting rows (it returns one row on the emptied copy);
      - `SELECT * FROM <that table>` satisfies it.
  - **Mutations:**
    - misspell a column in one example (the execution pin reds);
    - filter the effort example to an impossible kind (`row_count >= 1`
      reds);
    - drop the emptied-copy condition (the bare-aggregate fixed-input test
      reds);
    - make the per-producer check accept any producer (the missing-producer
      control reds).
  - **Observable:** `uv run pytest tests/query/test_skill_examples.py` is
    green, with the number of examples and producers checked recorded.
  - _Requirements: 11.3, 11.4, 11.5_

- [ ] 8. Records, the floor and validation

- [ ] 8.1 Publish the release notes, steering and amendment records
  - **`CHANGELOG.md` `[Unreleased]` `### Added`**: `fitdocs query` (forms,
    formats, sandbox, `--schema`), the `fitdocs-analytics` skill, and the
    analytics page, linked by its https URL.
  - **The entry pin** (`tests/query/test_changelog_entry.py`): the
    `[Unreleased]` section names `fitdocs query`, `fitdocs-analytics` and
    `https://github.com/joshua-stauffer/fitdocs/blob/main/docs/analytics.md`,
    and the `[0.1.0]` section names none of them.
  - **`tech.md` Network and Credentials**:
    - `query` joins the commands that make no connector request;
    - one clause on the read-only, locked DuckDB configuration with external
      access and extension loading off.
  - **`structure.md`**: the `query` dependency-direction sentence of
    design.md.
  - **The connectors amendment**: append connectors Amendment 2, the next free
    number at landing ("Amendment 2 (date): Req 14.1 gains `query`, landed by
    analytics-query"; if another spec has taken 2 by then, the next free
    number), naming `tests/connectors/test_e2e.py`. `analytics-index`'s
    Amendment 1, which adds `index`, has landed before this plan starts, and
    is not edited.
  - **Roadmap**:
    - Phase 10 Existing Spec Updates: the connectors line is ticked, since
      both parts have landed;
    - Specs: the analytics-query line is ticked at merge.
  - **Steering-class validation**: grep `.kiro/steering/` and `CLAUDE.md` for
    the no-network command list and "query", and reconcile every hit.
    `tests/connectors/test_network_statements.py` and
    `tests/connectors/test_docs.py` stay green.
  - **Mutations:**
    - move the entry under `[0.1.0]` (the entry pin reds; `test_changelog`
      checks structure only);
    - drop the analytics URL from the entry (the entry pin reds).
  - **Observable:**
    - the entry pin, the changelog, network-statement and connectors-docs
      tests are green;
    - the grep output, before and after, is recorded in Implementation Notes;
    - `/kiro-spec-status connectors` is clean.
  - _Requirements: 7.5, 12.6, 12.7_

- [ ] 8.2 Register the test modules, verify the duckdb floor and validate the feature
  - **mypy registration**: append every new `tests/query/` module to
    `pyproject.toml`'s mypy `files`.
  - **The floor check**:
    - **The venv**: a throwaway venv under the session scratchpad, with the
      project's runtime and test dependencies and `duckdb==1.2.0`, running the
      worktree's `src` on `PYTHONPATH`. Never the worktree `.venv`.
    - **The run**: `tests/query/test_store_facade.py`, `test_sandbox.py`,
      `test_spill.py`, `test_statement.py`, `test_crash_vectors.py` and
      `test_command.py`, under `sandbox-exec -p '(version 1)(allow
      default)(deny network*)'`, with HOME at the run level pointed at an
      **existing** empty directory under the scratchpad. It is never a
      nonexistent path: that hid the 1.1.x HOME write from the index's probe
      P6 (research.md, Key Findings).
    - **Before the run**, verify that the sandbox blocks network with a
      `urlopen` probe.
    - **Confirm the floor is exercised**: the crash-vector positive control
      reports `1.2.0`.
    - **After the run**, assert HOME is still empty.
    - **Recording**: pass or fail per test, plus the `memory_limit` and
      `max_temp_directory_size` strings 1.2.0 reports. The `enable_logging`
      cases are expected to see the function absent.
    - If any test of the run fails on 1.2.0, or HOME is not empty, stop and
      report: the floor `analytics-index` task 1.1 set (U1, cross-spec ruling
      C1) is wrong, and changing it again is a roadmap decision.
  - **Full validation**, after the final rebase:
    - `uv run pytest && uv run ruff check . && uv run ruff format --check . &&
      uv run mypy`, plain, with `TZ=UTC`, and with `CI=true`;
    - the forbidden-strings gate, in the mode the other specs' validations
      recorded.
  - **Version checks**:
    - `SCHEMA_VERSION`, `CONTRACT_VERSION` and `DOC_VERSION` equal `main`'s;
    - the CLI count equals `main`'s plus one;
    - the docs reference block equals the live schema (regenerated if
      `analytics-derived` landed first);
    - the skill-examples test covers every non-core producer on `main`.
  - **Observable:** all green, with the floor table and the validation output
    recorded in Implementation Notes.
  - _Requirements: 5.7, 5.8_

- [ ] 8.3 Measure `fitdocs query` on the authorized HealthFit timing data root
  - **Who runs it**: the agent under the maintainer's explicit 2026-10-07
    authorization. Create a separate data root from copies of iCloud
    HealthFit `.fit` files; preserve originals and keep all personal inputs,
    generated documents, SQL output and index files outside the repository.
    Record only dataset counts and timings in the spec.
  - **What to run**:
    - `time fitdocs query "SELECT count(*) FROM pages"` (the freshness scan
      dominates);
    - `time fitdocs query --schema`;
    - one aggregate over `records`.
  - **Where results go**: `research.md`, as numbers only, with no personal
    values.
  - **Observable:** the three timings are recorded. If the plain query exceeds
    3 s, a follow-up is queued.
  - _Requirements: 9.1_


## Implementation Notes

- 2026-10-07 resumed task 1.3 accepted after rebase onto owning polling-watcher fix 0b92561: fresh independent Sol review APPROVED, canonical 9,477 passed/two optional actionlint skips in 281.27 s, all 31 preview tests passed; scoped/canonical Ruff and mypy clean. Fresh replay 79 observations: 78 red, one explicitly permitted module-date pin green; four new reviewer mutants and five fixture probes discriminate. Parent completion: 107 fixture/boundary tests, strict mypy six files, Ruff and diff checks passed. Statement creator annotation names 3.1. The old preview failures remain historical records; 1.3 prerequisites are now accepted. Task 2.1 subsequently received REJECTED; see the resumed review note below.

- Historical pre-preview-repair state, 2026-10-07: task 2.1 remained unchecked and blocked after its independent review and fresh debug: locally correct formatter candidate, initial review demonstrated twelve test/guard mutation survivors. Fresh Luna remediation corrected bounded Decimal/duration/order/alignment fixtures and literal import purity classification; implementer reports thirteen focused mutants red/restored green, 187 scoped tests and clean statics. These corrections remain unaccepted candidates pending fresh independent review and the causal owning preview repair/canonical gate. Debug confirms all other query tasks depend on unaccepted core tasks or the same mandatory gate. Preserve pending-task-1.3.patch and pending-task-2.1.patch; do not mark the feature GO or run query timings before the command exists.

- 2026-10-07 task 1.3 remains blocked after independent review round 3 and fresh debug1: 138 scoped tests and all meaningful claimed/reviewer mutations pass, but canonical 9,474 passed/two failed/two optional skips at distinct preview initial-edit and deleted-route stages. A focused diagnostic localized reproduced stale HTML after successful validation/sync; native cause and retained deletion mechanism are unknown. Route repair to docs-site owning queue; do not retry unchanged or weaken assertions. The creating-task annotation was corrected to 3.1 by Luna (focused test passed), without task acceptance. Candidate recovery patch and blocker evidence accompany this handoff. Module-date pin remains explicitly permitted UNPINNED; function-date pin is PINNED. Independent tasks may proceed, dependent tasks wait.

- 2026-10-07 task 1.1: Luna implementer BLOCKED before edits; independent debug confirmed SPEC_CONFLICT / STOP_FOR_HUMAN. Fresh read-only aggregate probes interrupted during execute on DuckDB 1.2.0 and fetchmany on 1.5.6. A temporary raw-fetchmany mutation survived the floor aggregate assertion and failed the current-version assertion; a deterministic synthetic fetch interruption pin failed on the floor. Source restored; no query implementation or task completed. Proposed correction and evidence: `implementation-blocker.md`; existing queue item `2026-10-06-query-interruption-phase-statements`. Upstream facade remains sound; preserve floor and timer-before-execute ordering.
- 2026-10-07 maintainer explicitly approved the bounded interruption testing correction: real aggregate cancellation may occur during execute or fetch, timer starts before either, and a separate deterministic fetch-interruption pin owns the raw-fetchmany mutation obligation. The prior blocker is cleared; runtime facade and dependency floor remain unchanged.
- 2026-10-07 maintainer authorized the agent to run task 8.3 on a new data root populated from iCloud HealthFit FIT copies, overriding the maintainer-only restriction for that measurement. Located 2,517 local FIT files (171,192,835 bytes), no cloud placeholders; isolated timing workspace `/private/tmp/fitdocs-analytics-query-timings`, with copied sources and tiles disabled. Original files untouched.
- 2026-10-07 task 1.1 review round 1 found one real fixture gap: directory contents were not tested; Luna added file/directory fixed-input cases and observed the directory-blind mutation fail. Initial full regression also failed under a cold UV cache and Homebrew's existing fake-interpreter fixture issue. Validation environment now matches main's pyenv 3.11.15, with locked all-groups tooling and warmed scratch cache `/private/tmp/analytics-query-uv-cache`; preserved previous environment outside the tree. Existing upstream queue item `2026-10-05-site-fixture-homebrew-interpreter-path` updated; no upstream production/test patch.

### Task 1.1 upstream confirmations

- U1, analytics-index 1.1: `pyproject.toml:31` pins `duckdb>=1.2,<2`.
- U2, analytics-index 4.1: `src/fitdocs/index/store.py:122` and `:132` wrap fetchmany/fetchall; `tests/index/test_store.py:245` pins original exceptions for every operation, `:562` pins conversion errors, and `:577` pins bounded real interruption. Query's own read-only conversion/interruption pins and the deterministic fetch interruption pin exercise this contract.
- U3, analytics-index 8.1: `docs/ownership-contract.md:218` names `writer-spill/` and `:220` names `query-spill-<pid>/` as transient.
- Snapshot seam, analytics-index 2.2, 2.3 and 5.1: `src/fitdocs/index/producer.py:80` defines CorpusSnapshot with left_out at `:83`; `src/fitdocs/index/corpus.py:37` defines LeftOutPage ending in document_fingerprint at `:41`; `:91` defines corpus_snapshot with keyword-only held and no default; `src/fitdocs/index/fingerprint.py:102` defines combined_corpus_fingerprint(producer, snapshot) without a version argument.
- Test-only Seam 5 names, analytics-index design.md:316-321 / tasks 2.2, 4.1, 5.1 and 6.2: create_index, create_schema, run_index_command, duckdb_version, CORE_DOCUMENTS, CORE_COMPUTED, TableScope and both monkeypatched producer registries are listed explicitly.
- Helpers, analytics-index 4.2: `tests/index/_helpers.py:49` exports hold_index and `:82` exports forge_storage_version.
- One-way importer guard, analytics-index 7.3: `tests/index/test_boundary.py:456` pins unlisted importers failing and absent listed modules remaining allowed. The initial independent task review ran this fixed-input guard successfully.
- 2026-10-07 shared timing data preparation complete: copied 2,517 HealthFit FIT files outside Git; stable main sync exited 0 in 532.870 s and index rebuild exited 0 in 269.507 s. Read-only facade verified 2,502 pages/activities and 5,636,964 records. Shared root `/private/tmp/fitdocs-analytics-query-timings/data`, cache base `.../index`; readiness and private preparation evidence published to both peer sessions under explicit user authorization. Query timings remain pending task 8.3; these are preparation timings, not query performance claims.
- 2026-10-07 task 1.1 review round 2 found a substring-only synthetic interruption message assertion; the second Luna remediation added exact equality and fixed-input symlink cases, including dangling links. Round 3 independently observed all 24 claimed mutation runs and three reviewer mutations go red, restored source, and observed current query 10/floor store 4 tests pass. Acceptance remains pending the canonical regression gate.
- 2026-10-07 validation environment: default sandbox denies local preview socket binds (errno 1), independently resolved by an escalated loopback control. The first round-3 full run failed 15 tests with 30 errors because of socket permission and missing hatchling/PyYAML resolver metadata; tracked forbidden-content check passed, artifact checks failed to build rather than finding forbidden content. Warmed scratch build/docs tool metadata from stable main, leaving the locked worktree environment unchanged. Canonical rerun uses the required socket permissions; the earlier run remains failed.

- 2026-10-07 task 1.1 accepted after round-3 APPROVED: escalated canonical suite 9,397 passed, two optional actionlint skips, exit 0 in 263.98 s; all 24 claimed mutation observations and three reviewer mutations red with no survivors. Fresh parent completion check: query 10 passed in 4.92 s, scoped mypy four files and Ruff check/format clean, diff check clean. No production source changes. Restricted earlier runs remain failed environment evidence.

- 2026-10-07 task 1.2 accepted and independently APPROVED after one test-only remediation: append-only seven-line statement_types facade using extract_statements/type.name; all 14 claimed entries, five reviewer mutations and 30 literal-row mutations observed sole red, no survivors. Direct PRAGMA syntax, exact parser message/original cause and non-forwarding facade/backend execution recorders close the first-review gaps. Canonical 9,430 passed/two optional skips; floor 33 passed; fresh parent store/query/boundary 177 passed in 11.96 s, mypy/Ruff/diff clean. Full command-level 1.5/5.2 behavior remains owned by later tasks.

- 2026-10-07 resumed task 2.1 review REJECTED: 86/187 scoped tests and scoped/canonical statics pass; canonical 9,525 passed, one failed, two optional skips, with all preview tests passing. Of 90 mutation trials, 88 red and two survivors: JSON column deduplication and removal of DEL escaping. Distinct-name correction had displaced the repeated-name pin. The sole canonical failure is the existing session-UUID guard's any-uuid-import proxy, triggered by generic formatter UUID handling. Fresh Sol debug is required; launching it after reviewer completion still fails with `agent thread limit reached`. No candidate correction or task acceptance bypass was made. Evidence: `/private/tmp/analytics-query-resume-review2-1/verdict.md` and `canonical-pytest.log`.

- 2026-10-07 resumed task 2.2 independent review REJECTED solely for verifier discrimination: canonical 9,486 passed/two optional skips and full/scoped statics passed. All32 production and seven HOME claims independently red/restored green, but defaulting absent settings to expected and checking only the first key survive all147 task-relevant tests. Independent fixed-input controls detect eight absent-row and21 later-key violations. Fresh Luna correction must add per-key absent/wrong/NULL cases and exact fields while preserving correct production and existing pins. Evidence `/private/tmp/analytics-query-review2-2/verdict.md`; initial un-escalated environment failure retained in pytest.log, corrected canonical in pytest-escalated.log.

- 2026-10-07 fresh formatter debug returned RETRY_TASK/HIGH: explicit UUID branches duplicate the existing str/JSON-string fallbacks, so removing branches and unused import preserves behavior and avoids changing the session guard. Read-only diagnostics preserved six scalar/nested UUID outputs; branch/source/test bytes unchanged by debugger. Fresh Luna correction dispatched with duplicate-name/order/DEL controls and exhaustive replay, evidence `/private/tmp/analytics-query-resume-debug2-1/report.md`. Capacity permits one fresh subagent launch after the preceding agent completes; concurrent launches still hit the thread limit. No completed Sol agent reused.

- 2026-10-07 fresh task2.1 correction review REJECTED for converging incomplete whitespace coverage: canonical9,529 passed/two optional skips and full/scoped statics passed, exactsessionUUIDguard clean, scoped191. Historical82 meaningful variants independently red/restored green; distinct-order/duplicate/DEL/UUID corrections retained all predecessor bytes. Table-cell and CSV-field stripping survive existing fixtures; fresh exact-whitespace witnesses prove incorrect output. New Luna TEST-ONLY correction must preserve correct production and every existing pin, exhaustively cover design whitespace/header edge values, then obtain fresh Sol review. Evidence `/private/tmp/analytics-query-review-format-final/verdict.md`. Original Luna handoff metadata corrections are preserved in `/private/tmp/analytics-query-resume-remediation2-1/parent-evidence-erratum.md`; repeated-name reversal passes as expected and distinct-name catches order, initial canonical reservation was already explicit. Incomplete mistaken implementer gates are not acceptance evidence.

- 2026-10-07 task2.1 accepted after fresh independent APPROVED: canonical9,535 passed/two optional actionlint skips in293.24s; full/scoped statics pass, 107 meaningful mutation trials and12 isolated controls RED/restored GREEN/no survivors. All52 clauses PINNED, 75 assertions inventoried (74PINNED/one preserved structural source-path precondition), all prior65 retained. Exact whitespace/header fixtures close final gaps; canonical UUID outputs use equivalent generic fallback, owning guard unchanged. Fresh parent after integration on verified-index9e9b2da lineage: query/index-boundary/exactUUIDguard197passed8.82s, fullRuff/checkformat534/mypy342 and strictthreeownedfiles pass, diffcheck clean. Evidence `/private/tmp/analytics-query-review-format-whitespace/verdict.md` and `/private/tmp/analytics-query-parent-format-completion/verification.md`. Historical pending-task-2.1.patch is superseded by accepted live files; keep original failed/incomplete evidence as history.

- 2026-10-07 task2.2 accepted after fresh independent APPROVED: canonical9,510 passed/two optional skips, full/scoped statics and45 meaningful mutation observations RED/restoredGREEN, eight clause groups PINNED/no survivors. Per-key missing/wrong/NULL readbacks close both original gaps without changing correct production. Parent byte-equal integration on91b0e74 passed230 query/index-boundary/exactUUIDguard tests8.46s, fullRuff/checkformat536/mypy343 and stricttwoownedfiles, diffcheck clean. Evidence `/private/tmp/analytics-query-review-sandbox-correction/verdict.md` and `/private/tmp/analytics-query-parent-sandbox-completion/verification.md`. Older pending-task-2.2.patch is superseded by accepted live files. Spill configuration and cleanup remain task2.3.

- 2026-10-07 task4.1 first independent review REJECTED despite canonical9540 passed/two optional skips and full/scoped statics: saved pre-flag backup equals complete production source, so retrospective flag capture does not prove tests-first. All25 claimed mutations RED, but three reviewer variants survive whole task tests: workout_pages uses held length, pages_held uses scan length, IS DISTINCT FROM becomes NULL-insensitive <>. Three fixed-input controls GREEN originally and soleRED under respective variants. Candidate restored/hashes preserved; evidence `/private/tmp/analytics-query-review4-1/verdict.md`. Fresh Luna remediation in cleanf7dfd76 tree copies tests only, requires parent-inspected API-shell/OFFRED checkpoint BEFORE implementation, preserves prior pins and adds exact differing page totals/NULL athlete controls. No4.1 acceptance.

- 2026-10-07 task4.1 first remediation review REJECTED only for9.5 directory purity: genuine forward parent-inspected OFFcheckpoint/ONGREEN/removedGREEN verified; canonical9573 passed/two optional skips, exactUUIDscope235 and full/strictstatics green, all33claims+2own variants RED. Parent-suggested emptydirectory creation under data_root survives full5tests because _tree_bytes records files only. Source restored01e740ec..., test7cd9db57..., no acceptance. Fresh Luna secondbounded TEST-ONLY repair preserves production/phasehistory/allpriorpins, adds treeentries/types+filebytes fixedcontrols; parent independently observed2intended oldhelperRED failures (bothroots) BEFORE GO_FIX_GUARD, proof `/private/tmp/analytics-query-task4-1-purity/evidence/parent-guard-checkpoint.json`. Review `/private/tmp/analytics-query-review4-1-repair/verdict.md`; laterfreshreview must replay all35 and newguard/directory controls.

- 2026-10-07 task4.1 accepted after fresh independent APPROVED: correctedrestoredcanonical9579passed/twooptional skips/exactexit0, all41claimed+2newown mutations RED/restoredGREEN, allfive requirement groups PINNED/no survivors. Production01e740ec... remains unchanged through test-only purity correction; test57e3ea62... pins directory/filebytes/live-and-broken-symlink entries and bothroot mkdir writes. Genuine parent-inspected preimplementation OFF/ON/remove chronology and tests-first guardRED verified; original retrospective/failedwrapper evidence preserved as history. Parent byte-equal integration onf7dfd76 passed241 query/indexboundary/exactUUIDguard13.75s, fullRuff/checkformat538/mypy344 andstrict2 plusdiffcheck. Evidence `/private/tmp/analytics-query-review4-1-purity/verdict.md` and `/private/tmp/analytics-query-parent-freshness-completion/verification.md`. Six/21leavesaccepted; freshLuna2.3 spill running isolatedf7dfd76 with earlycheckpoint, catalog4.2 queued. Bounded2.3 testownership clarification permits only its required perPID opening-settings expectation evolution, without changing requirements/runtime behavior of2.2.
