# Implementation Plan

## Upstream Prerequisites

- **`chart-kit` is on `main`** with every task checked. This plan consumes
  its facade by exact name (design § Allowed Dependencies):
  `fitdocs.units.unit_for_column`; `fitdocs.render.charts.kit.{validate_chart,
  render_chart, describe_kinds, kind_names, ChartRequest, ChartData, Column,
  ValueKind, ChartProblem, ProblemCode, ChartError, RenderedChart}`;
  `fitdocs.render.charts.kit.format.{escape_markdown, clean_text}` (research.md
  gap G1); the core `table` kind; and chart-kit's kind test-module convention
  (`tests/render/charts/kit/test_<name with - as _>.py` exposing `CASES`;
  chart-kit design § Settled Seams). Task 1.1 confirms each name and
  signature in the tree; a missing or different one is a stop-and-report,
  never an adaptation, and never an edit to chart-kit.
- **`chart-catalog` runs in parallel.** It appends kinds to `KINDS` and may
  append shared-layer functions. Task 7.3 carries the second-lander rule.
- **Open queue item `2026-10-08-store-facade-user-interrupt-unwrapped`.**
  Task 1.1 records whether it is still open. While it is, every dashboards
  path to DuckDB goes through the query session (task 2.2), which calls
  `interrupt_quietly` before `close` and converts the user interrupt; no
  dashboards module copies that workaround. If it has been fixed upstream,
  the session keeps its calls (they are harmless) and 6.3 still runs.
- **Existing spec updates carried by this plan** (design § Existing Spec
  Updates). Amendment numbers are the next free ones at `560f909`; the task
  that writes each record re-checks and takes the next free number if another
  spec took it first.
  - **analytics-index Amendment 1**: two new facade methods,
    `execute_named` (a streaming named-parameter read) and
    `statement_parameters` (2.1) — `IndexConnection.execute`, its `Sequence`
    signature, its callers and its tests stay byte-for-byte unchanged, and
    the positional materialisation hazard is recorded as out of scope;
    `_run_index_pass` returns its report (6.2); the named exception in every
    copy of "never read back into a document" (8.1 for
    `docs/ownership-contract.md`, 8.2 for `tech.md` and the record).
  - **analytics-query Amendment 1**: column types, the `params` path through
    `execute_named`, the session and the superseded out-of-scope line (2.2);
    the `_QUERY_IMPORTERS` entry (4.3); the `fitdocs-analytics` pointer (7.1).
  - **wiki-contract Amendment 5**: the location, declaration and
    `CONTRACT_VERSION` (1.2); the narrative sections of the ownership contract
    (8.1).
  - **connectors Amendment 3**: `dashboard` in the no-network list (6.5).

**Hard rules for every task**

- **Absent is `None`.** No dashboards code substitutes zero, an empty string
  or a default for an absent value or a missing key.
- **No clock in `fitdocs.dashboards`.** The run date arrives in the request
  from `cli._today()`; tests inject dates. No `date.today`, `datetime.now`,
  `time.*` call in the package.
- **Imports follow the rank order** (design § Architecture):
  `problems → grammar → directive → snapshot → region → source → storage →
  kinds → engine → report → binding`. `yaml` only in `directive`;
  `fitdocs.query.*` and `fitdocs.units` only in `binding`;
  `kit.format` only in `region`; `fitdocs.layout` and `fitdocs.contract`
  only in `storage` and `engine`; never `duckdb` or `fitdocs.index`. The
  engine never imports `binding`. No dashboards module imports `uuid` or
  binds a name `uuid` (`tests/test_contract_consumers.py:597-624`). Task 8.4
  enforces the rest; earlier tasks obey it.
- **No registry enumeration or kind-count pin.** No dashboards code or test
  holds a list of kinds or asserts how many are registered; tests that cover
  "every kind" iterate `kind_names()` / `describe_kinds()` at run time.
  Naming one specific core kind in a fixture (`bar`, `stat`, `table`) is
  allowed.
- **Writes only through `storage`**, atomically, never following a symlink.
  No dashboards test writes outside its `tmp_path`.
- **Linux-CI portable.** Temp directories come from `tmp_path` /
  `tmp_path_factory`, never `tempfile.gettempdir()` (the runner has no
  TMPDIR); HOME-purity assertions name fitdocs paths only (Rosetta writes
  `HOME/.cache/rosetta`). Child processes get `{**os.environ, …}` so the root
  conftest's `PYTHONDONTWRITEBYTECODE=1` holds.
- **Never run the CLI by hand while a full `uv run pytest` is in flight in
  the same worktree**: the CLI writes `src/**/__pycache__` and
  `tests/test_bytecode_hygiene.py` then fails spuriously.
- **Mutations run through `uv run pytest` only** (`change-protocol.md` §
  Fixture Discrimination). Each named mutation is applied, observed red,
  reverted, observed green, and recorded in the task's Implementation Notes.
  Revert by restoring a `cp` of the file taken before the mutation, never
  `git checkout -- <path>`, `git stash` or `git reset --hard`. A listed
  mutation that cannot be made red is reported UNPINNED, never hidden by
  weakening the assertion. Before submitting, run the prose-claim grep of
  `change-protocol.md` over the changed test files and re-run or delete
  every surviving claim.
- **Parallel streams.** `(P)` tasks run in separate worktrees, one per
  stream (repo practice). A `(P)` task mutates only modules inside its own
  `_Boundary_`, runs its mutations and `uv run mypy`/`ruff` scoped to its own
  files, and never edits a shared helper (`tests/dashboards/_helpers.py`,
  `tests/dashboards/conftest.py`): a missing helper is a stop-and-report.
  The whole suite runs at each group's integration point and in 8.5.
  **Stream order**: the group-3 streams (3.1–3.4) merge, with a full-suite
  run, before the group-4 streams 4.1 and 4.2 branch from that merged state
  (they consume 3.1 and 3.3). 4.3 needs only 2.2, so it may branch as soon as
  2.2 lands and run alongside group 3; it merges with 4.1 and 4.2 at 5.1,
  the integration point of group 4. 7.1 and 7.2 branch after 6.5 and merge
  at 7.3. Mutations of shared modules
  (`cli.py`, `store.py`, `query/*`, `layout.py`, `declaration.py`,
  `contract.py`, `engine.py`) happen only in the sequential tasks that own
  them.
- **Fixtures discriminate.** Pages put the interesting chart second, not
  first; offending rows sit at indices other than 0; dates are not pre-sorted;
  values are pairwise distinct where a mapping is asserted; an asserted end
  state is shown false beforehand; "nothing written" is asserted on bytes
  *and* on `st_mtime_ns`.
- **Version constants advance by one at land time.** `CONTRACT_VERSION`
  becomes main's value + 1 (`"10"` at `560f909`); if `main` moved it before
  the merge, task 8.5 re-derives it after the final rebase.
- **Shell safety.** Never `rm -rf`, `git init`, `git reset --hard`,
  `git clean` or `git checkout -- <path>`; never chain a destructive command
  after `cd`; scratch files under the task's own `tmp_path` only.
- **Types and lint.** Each task runs `uv run mypy` (config-driven), and
  `uv run ruff check` and `uv run ruff format --check` on its changed files.
- **Stop and report** on any need for: a runtime dependency; an edit to
  chart-kit or chart-catalog files; a kind list or count; a change to
  `IndexConnection.execute` or any of its callers; an edit to another spec's
  files beyond those this plan names; a write outside `dashboards/` from a
  dashboards path.

## Shared source files

Each file below has more than one writer in this plan; its writers are
sequential, never two `(P)` tasks at once.

- `src/fitdocs/cli.py`: 6.1 (`dashboard` command, `_query_environment`,
  docstring), then 6.2 (`_run_index_pass` return, `_run_dashboard_pass`).
- `src/fitdocs/dashboards/engine.py`: 5.1 creates it; 5.2, then 5.3,
  extend it; 5.4 imports it after 5.3.
- `src/fitdocs/dashboards/problems.py`, `source.py`: 1.1 only.
- `tests/dashboards/_helpers.py` and `tests/dashboards/conftest.py`: 1.1
  creates both with every shared helper and fixture the plan uses; only the
  sequential tasks 5.1–5.3 and 6.1–6.2 may append to `_helpers.py` (each
  addition named in that task's notes); no `(P)` task edits either.
- `tests/query/test_boundary.py`: 2.2 (query's forbidden targets), then 4.3
  (the `_QUERY_IMPORTERS` entry; no other `(P)` task touches the file).
- `tests/test_confinement.py`: 1.2 (the AGENTS.md expectations of the
  history and plan negative halves), then 6.4 (the dashboards entries).
- `docs/ownership-contract.md`: 1.2 (version, head paragraph, owned paths,
  "five owned directories"), then 8.1 (the narrative sections).
- `README.md`: 1.2 (the owned-locations sentence), then 7.1 (the packaged
  skills sentence).
- `.kiro/steering/tech.md`: 6.5 (the no-network list), then 8.2 (the
  architecture paragraph and the sandbox sentence).
- `pyproject.toml` `[tool.mypy].files`: 1.1 only (the `tests/dashboards`
  directory entry covers every later dashboards test module).
- `src/fitdocs/index/store.py`: 2.1 only. `src/fitdocs/query/{format,statement,command}.py`:
  2.2 only.
- `src/fitdocs/skills/fitdocs-analytics/SKILL.md`, `src/fitdocs/agentskill.py`:
  7.1 only.

## Cross-spec shared files

- **With `chart-catalog`** (parallel), and only these two:
  - the kinds block in `docs/dashboards.md` (7.2 creates it; 7.3 and
    chart-catalog's second-lander task regenerate it);
  - `CHANGELOG.md` Unreleased (8.2 adds one bullet; chart-catalog may add
    its own): append-only, keep both sides on rebase.
- **With `chart-kit`** (lands first, so these are sequential, not
  contended): `pyproject.toml` `[tool.mypy].files` (chart-kit's 1.1/1.2
  added its entries; 1.1 here appends `tests/dashboards`) and
  `.kiro/steering/structure.md` (chart-kit's 7.1 edited the `index` bullet
  and added the `units`/kit paragraph; 8.2 here edits the `query` bullet and
  adds a `dashboards` bullet) and `tests/connectors/test_network_statements.py`
  (chart-kit's 7.1 re-pinned the `index`-bullet phrase first; 6.5 here adds
  the `load`, `dashboard`, `check` pin and 8.2 moves the tech.md
  Architecture pin, in separate hunks). chart-catalog edits none of these.
- **Append-only, keep both sides on rebase**: the `cli.py` command count
  and docstring list (13 → 14), the no-network command list,
  `WRITING_ENTRY_POINTS`, `OWNED_PATHS` / `DECLARED_DIRS`,
  `PACKAGED_SKILLS`, `release/artifact-policy.toml`.

## Test File Ownership

- `tests/dashboards/__init__.py`, `_helpers.py`, `conftest.py`,
  `test_problems.py`: **1.1**.
- `tests/declaration_golden/dashboards.AGENTS.md` and the edits to
  `tests/test_layout.py`, `tests/test_declaration*.py`,
  `tests/test_ownership_contract.py`, `tests/identity/test_contract_docs.py`,
  `tests/index/test_contract_docs.py:140`,
  `tests/index/derived/test_preserved.py:246`, the history/plan negative
  halves of `tests/test_confinement.py`, and plans-settings tests: **1.2**.
- Additions to `tests/index/test_store.py`, `tests/query/test_store_facade.py`
  and the child-process latency test: **2.1**.
- Additions to `tests/query/test_statement.py`, `tests/query/test_command.py`,
  `tests/query/test_format.py`; the forbidden-target edit to
  `tests/query/test_boundary.py`: **2.2** (its `_QUERY_IMPORTERS` entry:
  **4.3**).
- `test_grammar.py`: **3.1**. `test_directive.py`: **3.2**.
  `test_snapshot.py`: **3.3**. `test_kinds.py`: **3.4**.
- `test_region.py`: **4.1**. `test_storage.py`: **4.2**. `test_binding.py`:
  **4.3**.
- `test_engine.py`: **5.1** creates, **5.2** and **5.3** extend.
  `test_report.py`: **5.4**.
- `test_cli_dashboard.py` and the count pins in
  `tests/query/test_cli_query.py:803-812`, `tests/test_cli_skill.py:261-269`,
  `tests/index/test_cli_index.py:604-608`: **6.1**.
- `test_pass.py` and the pin in `tests/index/test_cli_post_pass.py:533-543`:
  **6.2**. `test_interrupt.py`: **6.3**. Dashboards entries in
  `tests/test_confinement.py`: **6.4**. `tests/connectors/test_e2e.py` and
  the new tech.md pin in `tests/connectors/test_network_statements.py`: **6.5**.
- Skill pins (`tests/test_skill_locator.py`, `tests/test_agent_skill.py`,
  `tests/test_release_artifacts.py`, `tests/test_skill_wheel.py`,
  `tests/test_cli_skill.py:67`, `tests/test_packaging.py:883`,
  `tests/test_releasing_docs.py:573`, `tests/test_wiki_integration_docs.py`):
  **7.1**.
- `test_docs_dashboards.py`, `tests/test_docs_guarantees.py` required links:
  **7.2**.
- `tests/index/test_contract_docs.py:56` and the ownership-contract phrase
  pins: **8.1**. `tests/connectors/test_network_statements.py:640-644` and
  `test_published.py`: **8.2**. `test_e2e.py`, `test_determinism.py`,
  `golden/`: **8.3**. `test_boundary.py`: **8.4**.

---

- [ ] 1. Foundation: the package, the problem record, and the dashboards location

- [x] 1.1 Create the dashboards package, its problem record, the shared test helpers and fixture, and confirm the upstream seams
  - **Confirm upstream** (record in Implementation Notes): each chart-kit
    name listed in Upstream Prerequisites exists with the design's signature
    (`git grep` plus an import in a scratch test); `describe_kinds()` returns
    JSON-ready listings; the `table` kind is registered; the kind test-module
    convention resolves for every `kind_names()` entry; `escape_markdown`
    escapes `[`, `]`, `*`, `_`, `\` and `clean_text` replaces control
    characters. Record the queue item's status, `CONTRACT_VERSION` on `main`,
    the next free amendment numbers of analytics-index (1), analytics-query
    (1), wiki-contract (5) and connectors (3), and whether
    the `structure.md` `index`-bullet phrase pin in
    `tests/connectors/test_network_statements.py` (the phrase chart-kit's
    7.1 re-pinned to include `units`; cite it by content, its line numbers
    move) is green on `main` after chart-kit's 7.1 (a check, not a claim: if
    it is red, stop and report).
  - **Package**: `src/fitdocs/dashboards/__init__.py` (docstring only:
    dashboard pages, imported only by the CLI); `problems.py` per design §
    Problems (`Source`, `Severity`, `DashboardCode` with the 38 values in
    design order, `NOTICE_CODES`, `Problem`, `ProblemDict`, `as_dict`,
    `severity`, `dashboard_problem`, `from_chart_problem`); `source.py` per
    design § Source (`Fetched`, `SourceUnavailable`, `ChartSource`,
    `SourceOpener`).
  - **Shared test helpers** (`tests/dashboards/_helpers.py`), complete for
    every later task: a page-text builder (frontmatter, prose, directive
    blocks with chosen keys and line endings, regions with chosen bodies);
    typed `ChartData` builders; `FakeSource` (queued data or problems per
    SQL, a record of every `fetch` with its `today`, and a `must_not_open`
    opener that raises `AssertionError`); a data-root factory under
    `tmp_path`; `snapshot_of(path)` returning bytes and `st_mtime_ns` for
    every file under a directory, and `assert_untouched(before, after)`.
  - **Shared fixture** (`tests/dashboards/conftest.py`):
    `indexed_dashboard_root`, a real index built the way
    `tests/query/conftest.py`'s `indexed_root` builds one (reusing
    `tests/query/_helpers.py` builders; `FITDOCS_INDEX_DIR`, `HOME` and
    `XDG_CACHE_HOME` isolated under `tmp_path_factory`), yielding the data
    root and environment.
  - **`pyproject.toml`**: append `tests/dashboards` (a directory entry) to
    `[tool.mypy].files`.
  - **Tests** (`test_problems.py`): `tuple(DashboardCode)[:38]` equals a
    test-local literal in design order (a prefix pin); `as_dict()` keys in
    field order with `accepted` a list and the whole dict `json.dumps`-able;
    `from_chart_problem` copies every field of a `ChartProblem` whose fields
    are all distinct non-default values, and the `option` override; severity
    is NOTICE exactly for the two notice codes from the dashboard source and
    PROBLEM for a chart-source problem whose code string equals
    `"sql_changed"`; a smoke test that `indexed_dashboard_root` answers
    `SELECT count(*) FROM activities` with a positive count through
    `fitdocs.query.command.run_query` (the fixture is live).
  - **Mutations:** reorder two `DashboardCode` members; drop `channel` from
    the copy in `from_chart_problem`; make `severity` ignore `source`.
  - **Observable:** `uv run pytest tests/dashboards` is green; `uv run mypy`
    covers `tests/dashboards`; Implementation Notes list the confirmed
    upstream names, the queue item's status, the four amendment numbers and
    the structure.md pin check.
  - _Requirements: 4.8, 15.1, 15.2, 15.3, 15.6_

- [x] 1.2 Declare the dashboards location, its AGENTS.md and the next contract version (wiki-contract Amendment 5, part 1)
  - **`src/fitdocs/layout.py`**: `DASHBOARDS_DIR = "dashboards"`;
    `OWNED_PATHS` appends `f"{DASHBOARDS_DIR}/"` and
    `f"{DASHBOARDS_DIR}/{ASSETS_SUBDIR}/"`; `DECLARED_DIRS` appends
    `f"{DASHBOARDS_DIR}/"`; both docstrings name the co-owned shape.
  - **`src/fitdocs/declaration.py`**: the dashboards fragments (each with a
    CLAIM ANCHOR comment) and the `dashboards/` branch per design §
    Declaration, including its Owner line; the no-fall-through `else` stays.
  - **`src/fitdocs/contract.py`**: `CONTRACT_VERSION` = main + 1 (`"10"` at
    `560f909`) with a history entry "Raised from ``9`` to ``10`` by
    dashboards: …" in the existing docstring style.
  - **`docs/ownership-contract.md`**: the version line; a new "What changed
    at this version" paragraph (a fitdocs-owned `dashboards/` location whose
    pages belong to the athlete while fitdocs owns their chart regions and
    `dashboards/assets/`; dashboard chart regions and assets are the only
    document content produced from the analytics index — workout, history
    and block documents never read it; run `sync` or `regen` once to place
    `dashboards/AGENTS.md`; nothing is needed for existing documents);
    "five owned directories" with `dashboards/AGENTS.md`; two Owned Paths
    bullets.
  - **Stale prose naming the owned locations**: `docs/install.md:111-113`,
    `README.md:209-211`, `docs/upgrading.md:149-150` ("writes only into …
    `workouts/`, `history/`, `blocks/`, `fit-archive/`, `.cache/`,
    `.fitdocs/`") gain `dashboards/`.
  - **Goldens**: create `tests/declaration_golden/dashboards.AGENTS.md`;
    regenerate the four existing declaration goldens (their Ownership block
    carries the version) with `uv run python -m tests.test_declaration_goldens`;
    add `dashboards/` to `_GOLDEN_NAMES` and a `dashboards-old/` lookalike to
    `_OUTSIDE_DECLARED_SET`.
  - **Pins that move** (owned edits):
    - `tests/test_layout.py`: the exact tuple at `:649`, `:863-872`
      (`OWNED_PATHS` literal and `len(OWNED_PATHS) == 8` → 10), `:885`
      (`DECLARED_DIRS` literal), and `:907-916` (`allowed_nestings` gains the
      `dashboards/` → `dashboards/assets/` pair; the test's name and
      docstring say three pairs);
    - the hard-coded `"9"` in `tests/index/test_contract_docs.py:140`,
      `tests/index/derived/test_preserved.py:246` and `tests/test_declaration.py:98`
      (if it is one);
    - `tests/identity/test_contract_docs.py:177-186` (the head phrases now
      pin the version-10 paragraph's phrases, including the named exception);
    - the AGENTS.md sets in the history and plan negative halves of
      `tests/test_confinement.py` (~:1861, ~:1943) and any
      `tests/test_declaration_refresh.py` set of created declarations;
    - any plans-settings test enumerating refused owned names
      (`plans/settings.py:163` now refuses `dashboards`).
    `DECLARED_DIRS` changes what sync, drain, regen, history and plan write
    and what `fitdocs check` audits, so pins a grep cannot find (counts,
    exact file sets) surface only in the full suite.
  - **Tests**: `tests/test_declaration_goldens.py` covers the new golden;
    a `tests/test_declaration.py` case asserts the dashboards text never
    claims the pages are tool-owned (the `_WRITTEN_AND_OWNED` sentence is
    absent) and names `fitdocs dashboard check`; the contract conformance
    tests (`tests/test_ownership_contract.py`) pass with the new bullets.
  - **Mutations:** drop `dashboards/assets/` from `OWNED_PATHS` (layout
    pins and contract set-equality red); route `dashboards/` through the
    `_WRITTEN_AND_OWNED` fragment (new declaration test reds); leave
    `CONTRACT_VERSION` at main's value (version pins red).
  - **Observable:** the full `uv run pytest` is green, and a sync in a
    scratch data root (an existing test's harness) creates
    `dashboards/AGENTS.md` equal to the golden.
  - _Requirements: 1.1, 1.2, 19.2_

- [ ] 2. Upstream amendments: parameters, typed columns and a multi-statement session

- [x] 2.1 Add a streaming named-parameter read and parameter screening to the index facade (analytics-index Amendment 1, facade)
  - **`src/fitdocs/index/store.py`** per design § Upstream amendments, two
    new methods and nothing else changed:
    - `execute_named(sql, params: Mapping[str, object]) -> IndexResult`:
      `self._connection.execute(sql, dict(params))` for a non-empty mapping,
      `self._connection.execute(sql)` for an empty one (nothing bound);
      the result is built by a new classmethod `IndexResult.from_cursor(cursor,
      errors)` whose `columns` come from `description` (`str(name)`,
      `str(type)`) and whose `fetchmany`/`fetchall` stream from the cursor,
      errors wrapped exactly as the relation form wraps them. The positional
      constructor `IndexResult(relation, errors)` is unchanged, so
      `tests/query/test_store_facade.py:119` keeps working unedited;
    - `statement_parameters(sql) -> tuple[frozenset[str], ...]`, parse
      errors wrapped as `IndexStatementError`.
  - **Unchanged**: `IndexConnection.execute(sql, params: Sequence[object] = ())`,
    its `.sql(sql, params=params)` routing, every caller (`store.py:400`,
    `:426`, `:486`, `:500`, `:513`, `:523-524`, `query/freshness.py:119`) and
    every test that monkeypatches it (`tests/index/test_store.py:1172-1179`,
    `:1510-1517`, `:1541-1546`, `tests/query/test_store_facade.py:264`).
  - **Tests** (additions to `tests/index/test_store.py` and
    `tests/query/test_store_facade.py`):
    - `execute_named` returns rows and `ResultColumn`s typed from
      `description`; an extra key and a missing value each raise
      `IndexStatementError`;
    - **binds nothing for an empty mapping**: a recording proxy around the
      facade's DuckDB connection shows `execute` called with exactly
      `(sql,)` for `{}` and `(sql, {"lo": 0})` for `{"lo": 0}` (on 1.5.6
      `execute(sql, {})` and `execute(sql)` behave identically — probe in
      research.md — so only the call shape can pin this clause);
    - `statement_parameters` gives `{"today"}` for `$today`, `{"1"}` for `?`
      and for `$1`, `set()` for `'$today'` in a literal and in a `--`
      comment, one set per statement for two statements;
    - a timer interrupt on `execute_named` surfaces as `IndexInterrupted`;
    - **streaming pin**: a child process (`{**os.environ, …}`, repository
      root as cwd) receives a path under the test's `tmp_path`, opens it with
      the facade's `create_index(<tmp_path>/stream.duckdb)` (no new open
      helper), reads `ru_maxrss` once connected (the baseline), reads the
      first `fetchmany(10)` of
      `SELECT range AS n FROM range(5000000) WHERE range >= $lo` via
      `execute_named`, reads `ru_maxrss` again (the peak), and prints both,
      normalised to bytes (`ru_maxrss` is bytes on macOS and KiB on Linux).
      The test asserts the growth (peak − baseline) stays under 100 MB and
      records both absolute values. Probe P3 (research.md, macOS, 1.5.6)
      measured ~0 MB of growth streaming against ~255 MB materialised at this
      size, so the mutation costs ~300 MB; do not raise the size. Elapsed time
      is recorded, not asserted.
    - **Floor version**: where the environment provides duckdb 1.2.0 (as
      4.3 and 6.3 do), run the streaming pin on it and record the baseline,
      peak and growth. If 1.2.0 materialises (growth above the bound), mark
      the test to skip on versions below the first one that streams, record
      the evidence in Implementation Notes and report it at the end of the
      task: on the floor the cost is memory, not correctness, and the
      controller queues it.
    - Every pre-existing store, facade and freshness test passes unedited.
  - **Mutations:** route `execute_named` through
    `self._connection.sql(sql, params=dict(params))` (the streaming pin
    reds); pass `dict(params)` even when empty (the call-shape case reds);
    return statement types from `statement_parameters`.
  - **Observable:** `uv run pytest tests/index tests/query` is green and
    `git diff main -- src/fitdocs/index/store.py` shows only added lines
    (the two methods and `IndexResult.from_cursor`); `git diff --stat` on the
    two test files shows additions only; the amendment record is written by
    8.2.
  - _Requirements: 7.3, 7.5_

- [x] 2.2 Keep column types, add the named-parameter path and a sandboxed session to the query layer (analytics-query Amendment 1)
  - **`src/fitdocs/query/format.py`**: `ResultSet.column_types: tuple[str, ...] = ()`
    (a defaulted trailing field; every positional construction keeps working).
  - **`src/fitdocs/query/statement.py`**: `execute_statement` and
    `run_statement` take `params: Mapping[str, object] | None = None`;
    `None` keeps today's `conn.execute(sql)` call byte-for-byte; a mapping
    (even empty) calls `conn.execute_named(sql, params)`; both fill
    `column_types` from `result.columns`; `statement_parameters(conn, sql)`.
  - **`src/fitdocs/query/command.py`** per design § Upstream amendments:
    `ScreenedStatement`, `SessionUnavailable`, `QuerySession` (`screen`,
    `run` — always passing a mapping —, idempotent `close` with
    `interrupt_quietly` first, context manager), `open_session(data_root,
    env)`; `run_query`'s open-and-check sequence moves into one private
    helper used by both, behaviour unchanged. `QuerySession.run`/`screen`
    raise only `StatementRefused`, `StatementFailed` (parse failures
    converted), `StatementTimedOut` and `KeyboardInterrupt`.
  - **`tests/query/test_boundary.py`**: query's forbidden targets gain
    `fitdocs.dashboards` (query never imports dashboards). The importer
    allow-list entry for `fitdocs.dashboards.binding` is added by 4.3, when
    the module exists.
  - **Records**: `.kiro/specs/analytics-query/requirements.md` marks the two
    out-of-scope lines (saved queries; charting query results, `:85-88`) as
    superseded by Phase 11 `dashboards` and gains `## Amendment 1
    (2026-10-xx): parameters, typed columns and a session, landed by
    dashboards` in the fit-ingest/connectors style; `spec.json` gains an
    `amendments` entry naming the tests below and tasks 4.3 (the importer
    allow-list) and 7.1 (the `fitdocs-analytics` pointer).
  - **Tests** (`tests/query/test_statement.py`, `test_command.py`,
    `test_format.py`): `column_types` filled on both paths (a no-params
    statement and a `$today` statement over DATE, DOUBLE, VARCHAR columns);
    `run_statement(params=None)` still calls `execute` (a recording
    connection) while `params={}` calls `execute_named`;
    `run_statement(params=…)` binds; `open_session` returns
    `SessionUnavailable` with NOT_BUILT (no file), NEEDS_REBUILD (wrong
    schema version), BUSY (held lock, injected sleep/monotonic) exactly as
    `run_query` classifies them; a session runs two statements on one
    connection (one open recorded); `session.run(sql, params={})` reaches
    `execute_named` on a recording connection (the session never turns an
    empty mapping into `None`); `run` converts a syntax error to
    `StatementFailed` and a refused statement to `StatementRefused`; `close`
    after an interrupted statement returns (interrupt called first, observed
    through a recording connection); every existing query test passes
    unedited.
  - **Mutations:** drop `column_types` filling; route `params=None` through
    `execute_named` (the recording-connection case reds); pass
    `params or None` from `QuerySession.run` (the session-level `{}` case
    reds); have `close` skip
    `interrupt_quietly`; let `IndexStatementError` escape `screen`; open a
    new connection per `run` (the one-open assertion reds).
  - **Observable:** `uv run pytest tests/query tests/index` is green with
    the pre-existing tests unedited; the analytics-query amendment record is
    committed.
  - _Requirements: 7.1, 7.2, 7.6, 7.8, 7.10, 19.6_

- [ ] 3. The pure core

- [x] 3.1 (P) Scan pages: lines, fences, directives, regions and near misses
  - **`src/fitdocs/dashboards/grammar.py`** per design § Grammar: `SLUG`,
    `PAGE_NAME_RE`, `CHART_ID_RE`, `OPENER`, `CLOSER`, `begin_marker`,
    `end_marker`, `REFERENCE_RE`, `Line`, `DirectiveBlock`, `RegionBlock`,
    `PageScan`, `split_lines`, `scan_page`, `following_region`.
  - **Tests** (`test_grammar.py`), each fixture with the case under test as
    the second chart on the page:
    - exact opener and closer; `<!-- fitdocs:chart -->`, a trailing space,
      four-space and one-space indentation → `opener_malformed` with the line;
    - blank lines and `--` SQL comments inside a body; `-->` and `--!>`
      mid-body set `terminator_line`; an unclosed directive and the scan
      resuming after it;
    - backtick and tilde fences; a closing fence longer than the opener; a
      tilde line not closing a backtick fence; a four-space-indented
      backtick line that is not a fence; an unclosed fence hiding a later
      directive; markers inside fences ignored;
    - regions: closed; unclosed (an opener after it); an intruding
      `begin:chart:` line; a reference line allowed; an end marker with no
      open region and a marker with an invalid id → `marker_malformed`;
    - `following_region` across blank lines, and `None` when prose
      intervenes;
    - `split_lines` round trip for LF, CRLF, mixed, a missing final newline
      and a leading U+FEFF.
  - **Mutations:** drop the fence state (fenced example parsed live);
    `startswith(OPENER)` instead of equality; skip the `--!>` check; let
    `following_region` skip prose; strip line endings in `split_lines`.
  - **Observable:** `uv run pytest tests/dashboards/test_grammar.py` green
    with every mutation recorded red.
  - _Requirements: 1.3, 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 5.1, 5.7, 16.5_
  - _Boundary: Grammar_

- [x] 3.2 (P) Parse directives strictly
  - **`src/fitdocs/dashboards/directive.py`** per design § Directive:
    `Mode`, `REQUIRED_KEYS`, `OPTIONAL_KEYS`, `MAX_ID_LENGTH`, `Directive`
    (with `sql_sha256`), `parse_directive(body, *, open_line, page)`; the
    resolver-free loader, the event walk for anchors and aliases, tag and
    duplicate-key checks, the `sql` style check.
  - **Tests** (`test_directive.py`): `mode: no`, `id: 2026-10-11`, `id: 012`
    reach validation as the strings written (`mode_value`; the two ids
    valid); duplicate key; `!!int`, `!!str` on a key; an anchor and an alias;
    `sql: >`, `sql: |-`, `sql: |+`, plain `sql:`, quoted `sql:`; missing and
    unknown keys in order with `accepted`; ids of 64 and 65 characters and
    with an uppercase letter; multi-line `title`; `show_rows: yes`;
    `channels` as a list; a nested option value; a YAML syntax error on body
    line 3 reported at `open_line + 3`; a valid directive's fields, including
    an empty `title` passed through; `sql_sha256` of a known string.
  - **Mutations:** load with `yaml.safe_load` (the `mode: no` and id cases
    red); skip the style check (`sql: >` passes); drop the alias walk;
    accept `yes`; off-by-one in the error line.
  - **Observable:** `uv run pytest tests/dashboards/test_directive.py` green
    with every mutation recorded red.
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.6, 4.7, 4.9, 4.10_
  - _Boundary: Directive_

- [x] 3.3 (P) Encode and decode snapshots, and name their files
  - **`src/fitdocs/dashboards/snapshot.py`** per design § SnapshotCodec:
    `SNAPSHOT_FORMAT`, `SNAPSHOT_VERSION`, `SNAPSHOT_NAME_RE`, `Snapshot`,
    `snapshot_rel_path`, `encode`, `decode`, `SnapshotFormatError`.
  - **Tests** (`test_snapshot.py`):
    - round trip per value kind with `Decimal("1.50")`, `-0.0`, `1e-7`, a
      large `int`, microsecond date-times, negative and multi-day durations,
      absent values in every kind (decoded values equal and of the same
      Python type);
    - the exact encoded bytes of one small snapshot (key order, separators,
      trailing newline);
    - strict decoding refusals, one fixture per rule;
    - **every registered kind** (10.9): for each name in `kind_names()`,
      import `tests.render.charts.kit.test_<name with - as _>` and, for each
      of its `CASES`, render `case.request` with the case's columns and the
      rows decoded from `encode(Snapshot(…, data=case.data))`, and assert the
      bytes equal `render_chart(case.request, case.data)`; the loop asserts it
      visited at least one case per kind (no literal kind list or count, so
      appended kinds are covered unedited);
    - name grammar accepts `pace.snapshot-12.json` and refuses
      `pace.snapshot-0.json`, `pace.snapshot-01.json`,
      `Pace.snapshot-1.json`.
  - **Mutations:** encode `Decimal` as a float (round trip reds); drop
    microseconds; accept `version: 2`; serialise with `sort_keys=True`
    (exact-bytes pin reds).
  - **Observable:** `uv run pytest tests/dashboards/test_snapshot.py` green
    with every mutation recorded red.
  - _Requirements: 10.1, 10.9_
  - _Boundary: SnapshotCodec_

- [x] 3.4 (P) List the registered kinds as text and markdown
  - **`src/fitdocs/dashboards/kinds.py`** per design § Kinds: `kinds_text`,
    `kinds_markdown` over a sequence of `KindListing`.
  - **Tests** (`test_kinds.py`): output for two stub listings (built as
    dicts in the test, one SVG with required and optional channels and a
    choice option, one markdown with none) pinned exactly; a description
    containing `|` and a newline escaped in the markdown table; the live
    registry's listing has one H3 per `kind_names()` entry, in order (no
    literal count); no output line starts with `<!-- fitdocs:`.
  - **Mutations:** drop the `*` for required channels; iterate listings
    sorted by name; skip the `|` escape.
  - **Observable:** `uv run pytest tests/dashboards/test_kinds.py` green
    with every mutation recorded red.
  - _Requirements: 14.5, 18.7, 20.1_
  - _Boundary: Kinds_

- [ ] 4. Regions, files and query binding

- [x] 4.1 (P) Compose, classify and splice chart regions
  - **`src/fitdocs/dashboards/region.py`** per design § Region:
    `BodyState`, `ChartBody`, `chart_body`, `caption`, `note_body`,
    `classify_body`, `recorded_snapshot`, `RegionEdit`, `apply_edits`;
    escaping through `kit.format.escape_markdown(clean_text(…))`.
  - **Tests** (`test_region.py`): body lines exactly for an SVG chart, a
    markdown kind (the kit's `stat` output), a frozen chart with its
    reference line, a rows table, and no caption; caption parts and their
    order; `through` is the latest date across two date columns where the
    later date sits in the second column and an earlier row; `no rows`;
    escaping of `]`, `*`, `_`, `\` and a control character in title and
    window (pins gap G1's dependency); note body and `NOTE_RE`;
    `classify_body` for empty, note, rendered and a note-like line with
    extra text; `apply_edits` inserting after a closer with CRLF endings and
    after a final closer without a newline, replacing two regions in one
    page, and leaving every byte outside the regions identical; no emitted
    line starts with `<!-- fitdocs:generated`.
  - **Mutations:** `min` instead of `max` for `through`; drop the window
    escape; insert before the closer; use `\n` regardless of the closer's
    ending; omit the blank line before the end marker.
  - **Observable:** `uv run pytest tests/dashboards/test_region.py` green
    with every mutation recorded red.
  - _Requirements: 1.6, 2.1, 2.2, 5.2, 5.3, 5.4, 5.5, 5.6, 9.3, 9.4, 10.3, 12.3, 16.5_
  - _Boundary: Region_
  - _Depends: 3.1_

- [x] 4.2 (P) Read and write dashboard files safely
  - **`src/fitdocs/dashboards/storage.py`** per design § Storage:
    `ASSET_MARK`, `asset_rel_path`, `PageFile`, `Refusal`,
    `dashboards_root`, `location_refusal`, `list_markdown`, `read_page`,
    `replace_page`, `write_asset`, `create_snapshot`, `read_snapshot`,
    `latest_snapshot`, `remove_stale_images`; the private atomic writer.
  - **Tests** (`test_storage.py`): symlinked `dashboards/`, `assets/`,
    `assets/<page>/`, page and image each refused and never followed (the
    link target's bytes and mtime unchanged); a page that is a directory;
    non-UTF-8 page; `replace_page` returns `changed` when bytes moved under
    it and writes nothing; no `.dashboards-*.tmp` left after a write or a
    simulated failure; `write_asset` writes once and reports `unchanged`
    the second time (mtime unchanged); an unmarked image reported `foreign`
    and left byte-identical; `create_snapshot` with generations 1 and 9
    present creates 10 and never replaces an existing file (a pre-created
    target name is skipped); `latest_snapshot` picks 10 over 9;
    `remove_stale_images` keeps an image referenced by another page and one
    referenced only from a nested non-page `.md`, removes an unreferenced
    marked image and its emptied directory, never removes a
    `*.snapshot-*.json` or an unmarked file, and removes nothing when one
    markdown file is not UTF-8.
  - **Mutations:** `os.replace` instead of the no-replace link for
    snapshots; scan only one page's text for references; lexical `max` for
    generations; skip the mark check in `write_asset`.
  - **Observable:** `uv run pytest tests/dashboards/test_storage.py` green
    with every mutation recorded red; no test path outside `tmp_path` is
    touched.
  - _Requirements: 2.3, 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 10.4, 10.8, 16.1, 16.2, 16.3, 16.4, 16.6_
  - _Boundary: Storage_
  - _Depends: 3.1, 3.3_

- [x] 4.3 (P) Bind chart SQL to the query session with typed columns
  - **`src/fitdocs/dashboards/binding.py`** per design § Binding:
    `ROW_CAP`, `TODAY`, `TYPE_KINDS`, `column_kind`, `QueryChartSource`,
    `source_opener`. UUID is refused by type name only: no `uuid` import and
    no name `uuid` (`tests/test_contract_consumers.py:597-624`).
  - **`tests/query/test_boundary.py`**: `_QUERY_IMPORTERS` gains
    `"fitdocs.dashboards.binding"` (analytics-query Amendment 1; the only
    edit to that file outside 2.2, which precedes this task).
  - **Tests** (`test_binding.py`; the real index from 1.1's
    `indexed_dashboard_root`; a test-local recording session for
    call-shape cases):
    - `column_kind` for every spelling in the design table, both
      vocabularies, with `DECIMAL(18,3)` and `TIMESTAMP_NS`; `None` for
      `TIME`, `Time`, `TIMESTAMP WITH TIME ZONE`, `BIGINT[]`, `list`,
      `STRUCT(a INTEGER)`, `MAP(VARCHAR, INTEGER)`, `BLOB`, `UUID`, `JSON`;
    - against the real index: `$today` used → bound (a `$today - 84` filter
      returns the expected rows for an injected date); not used → the
      session receives an empty mapping; `'$today'` in a literal → not bound;
      `$min`, `?` and `$1` → `sql_parameter` before execution (the recording
      session shows `run` never called); `EXPLAIN …` and two statements →
      `sql_refused`; a syntax error → `sql_failed`; a `TIMESTAMPTZ` column
      refused with a fix naming a cast (either `sql_failed` with the query
      hint or `column_type`, per design § Binding);
    - **hint carried** (7.9): a recording session raising
      `StatementFailed("boom", "a distinctive hint.")` → the problem's `fix`
      equals the hint;
    - **time limit** (7.6): with the binding module's `DEFAULT_TIMEOUT_S`
      monkeypatched to `7.5` (a value no literal would match), the recording
      session sees `timeout_s == 7.5`, and `max_rows == ROW_CAP`;
    - row cap: 10,000 rows pass and 10,001 → `row_cap`; a timeout through
      the recording session raising `StatementTimedOut` → `sql_timeout`;
    - `value_kind` with offenders at rows 2 and 5 of a recorded `ResultSet`;
      a `TIME` column → `column_type` naming it;
    - units: `distance_km`, `avg_pace_s_per_km` (not `_km`), `week` (none);
    - `source_opener` maps each `SessionUnavailable` kind to the design's
      message and fix and opens at most once.
  - **Floor version**: where the environment provides duckdb 1.2.0 (as
    analytics-query's validation did), run this module on it and record the
    result and the `description` spellings observed; otherwise record that it
    could not be run.
  - **Mutations** (in `binding.py` only): always bind `today`; classify
    parameters by matching the error text; `max_rows=ROW_CAP + 1`; drop the
    parenthesis strip; accept `EXPLAIN`; replace the hint with a fixed fix;
    pass a literal `30.0` instead of `DEFAULT_TIMEOUT_S`.
  - **Observable:** `uv run pytest tests/dashboards/test_binding.py
    tests/query/test_boundary.py` green with every mutation recorded red.
  - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 7.7, 7.9, 8.1, 8.2, 8.3, 8.4, 8.5, 8.6, 13.3_
  - _Boundary: Binding_
  - _Depends: 2.2_

- [ ] 5. The engine and the report

- [x] 5.1 Discover pages, resolve targets and plan charts
  - **`src/fitdocs/dashboards/engine.py`** (created here) per design §
    Engine: `Action`, `Outcome`, `Target`, `TargetError`, `RunRequest`,
    `ChartResult`, `PageResult`, `RunReport` (with `failed`),
    `has_dashboards`, `resolve_targets`, and the discovery and planning half
    of `run_dashboards`: location refusal, page listing and `page_name`,
    page reads and their refusals, `scan_page`, `parse_directive`, duplicate
    ids, region association (`region_mismatch`, `region_misplaced`,
    `region_unclosed`, `region_contents`), orphan notices, chart targets, and
    each chart's data need (fetch, recorded snapshot, latest generation). In
    this task no chart is rendered: a run returns the planning problems with
    every planned chart's outcome FAILED or, for a chart with no planning
    problem, CHECKED.
  - **Tests** (`test_engine.py`, created here, `FakeSource` that must not
    open): discovery (`AGENTS.md` skipped, `Running.md` → `page_name`, nested
    `sub/x.md` not read, a symlinked `dashboards/` → one `location_foreign`,
    a symlinked page and a non-UTF-8 page reported while the next page is
    planned); a page without frontmatter and one with `type: workout` are
    both pages (1.5); duplicate ids (both failed, `duplicate_id` on each);
    a region under another directive; a misplaced region; an unclosed region
    followed by a valid directive that is still planned; an orphan region
    (notice only); `page:chart` targets (other charts unreported); unknown
    page and unknown chart raise `TargetError` listing names; pages in
    sorted order from a directory whose listing order differs (17.3);
    `has_dashboards` for no directory, an empty one, one with only
    `AGENTS.md`, and a symlink.
  - **Mutations:** report `region_orphaned` as a problem; mark only the
    second duplicate; plan pages in listing order; read nested files as
    pages.
  - **Observable:** `uv run pytest tests/dashboards/test_engine.py` green
    with every mutation recorded red, and — this being the integration point
    of the group 3–4 parallel streams — the full `uv run pytest`, `uv run
    mypy` and `uv run ruff check .` green on the merged streams.
  - _Requirements: 1.3, 1.4, 1.5, 4.5, 4.10, 5.7, 5.8, 12.5, 14.6, 15.5, 17.3_
  - _Depends: 3.2, 4.1, 4.2_

- [x] 5.2 Render relative charts and write pages, with isolation and idempotence
  - **`engine.py`**: the rendering and writing half per design § Engine —
    the single source open after planning and its close in `finally`,
    relative fetches, `ChartRequest` construction, the `show_rows` table
    request, `from_chart_problem` for kit problems, success bodies, failure
    bodies (kept when RENDERED, note otherwise), per-page ordered writes
    (assets, then one `replace_page`), `asset_foreign`, `page_changed`,
    `write_failed`, and CHECK rendering in memory without writes.
  - **Tests** (extend `test_engine.py`):
    - a relative SVG chart second on its page: region inserted, image
      written with the mark, bytes outside the region identical; a second run
      writes nothing (bytes and `st_mtime_ns` of page and image unchanged)
      (17.1, 9.2);
    - **run date never in bytes** (9.3): the same relative chart run with
      `today` D1, then with `today` D2 (a different day) over identical
      `FakeSource` rows — the second run changes no byte and no
      `st_mtime_ns` of the page or the image, and `FakeSource` recorded both
      `today` values (the run did reach the source);
    - isolation: a kit refusal, an `sql_failed` from the source and a
      `region_contents` problem on three charts of one page; a healthy chart
      on that page and on another page still rendered; a previously rendered
      failing chart kept byte-identical; a never-rendered failing chart
      written as the note; a note replaced once the chart renders (12.1–12.4);
    - `show_rows: true` adds the kit table; a result over the table bound
      fails the chart with a kit problem carrying `option: show_rows` (5.6);
    - an unregistered `kind` is reported with the registered kinds as
      `accepted` (4.8);
    - kit order kept (15.5): a request the kit refuses with two stage-1
      problems in a known kit order (for example `empty_title` before a
      `missing_channel`) reports both, in that order, after the dashboards
      problems of earlier lines;
    - the source opens once for relative charts on two pages, and not at all
      for a page whose only chart has a planning problem (7.8);
      `SourceUnavailable` gives `index_unavailable` on each relative chart,
      `RunReport.index` set, other charts still rendered (14.7);
    - CHECK renders in memory and creates or changes no file (14.2); a page
      changed between read and replace → `page_changed`, page not written
      (12.5); an unmarked image at the asset path → `asset_foreign`, the
      chart's region not edited.
  - **Mutations:** write the page when no edit changed it; put the run date
    in the caption (the D1/D2 case reds); replace a rendered region with the
    note on failure; open the source per chart; let CHECK write assets; drop
    the `option="show_rows"` override; sort a chart's problems by code.
  - **Observable:** `uv run pytest tests/dashboards/test_engine.py` green
    with every mutation recorded red.
  - _Requirements: 4.8, 5.6, 7.8, 9.1, 9.2, 9.3, 12.1, 12.2, 12.3, 12.4, 12.5, 14.2, 14.3, 14.7, 15.5, 17.1, 20.1_

- [x] 5.3 Freeze, re-freeze and clean up
  - **`engine.py`**: the frozen paths per design § Engine and § Chart
    decision — recorded snapshot, latest generation, first freeze (encode,
    decode, render, create), `sql_changed` notice, `snapshot_missing` /
    `snapshot_unreadable`, `Action.FREEZE` (new generation, repoint, refuse
    relative), and `remove_stale_images` after REFRESH and FREEZE.
  - **Tests** (extend `test_engine.py`):
    - first freeze stores generation 1 with the run date and SQL digest, the
      region records it; the next run, with a `FakeSource` that must not
      open, renders unchanged (10.1–10.3);
    - a changed title and kind redraw from rows without opening the source
      (10.7); a changed SQL keeps the snapshot and reports `sql_changed`,
      `failed` false (10.6);
    - recorded snapshot deleted → `snapshot_missing`, region and image
      byte-identical, source not opened (10.5); corrupt file →
      `snapshot_unreadable`;
    - region deleted by hand → the highest generation adopted, no fetch
      (10.4); page renamed → the recorded path under the old page directory
      still used, the image now under the new page's directory, the old image
      removed by cleanup once nothing references it;
    - a copied page sharing a snapshot: FREEZE of one page's chart creates
      generation 2 under that page and repoints only that region; the other
      page renders unchanged (11.1);
    - FREEZE of a relative chart → `freeze_relative` (11.2); a failing
      freeze leaves region, image and snapshots unchanged (11.3);
      `SourceUnavailable` → `index_unavailable` (11.4);
    - a first freeze whose render fails creates no snapshot (10.1); CHECK of
      a never-frozen frozen chart fetches but creates no snapshot;
    - cleanup removes the image of a chart deleted from its page and keeps
      every snapshot (6.4, 10.8); it does not run on CHECK;
    - **no asset collisions** (6.1, 6.2): pages `a-b` (chart `c`) and `a`
      (chart `b-c`), plus two pages sharing the chart id `pace`, render four
      distinct image files with four distinct contents, and cleanup keeps all
      four.
  - **Mutations:** re-query when a snapshot exists; overwrite the existing
    generation on FREEZE; create the snapshot before the render succeeds;
    skip the `sql_sha256` comparison; run cleanup on CHECK; name assets
    `assets/<page>-<id>.svg` in `storage.asset_rel_path` (the collision case
    reds; this is a shared-module mutation, run here because 5.3 is
    sequential).
  - **Observable:** `uv run pytest tests/dashboards/test_engine.py` green
    with every mutation recorded red.
  - _Requirements: 6.1, 6.2, 6.4, 10.1, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7, 10.8, 11.1, 11.2, 11.3, 11.4, 14.4_

- [x] 5.4 Render the run report as text and JSON
  - **`src/fitdocs/dashboards/report.py`** per design § Report:
    `render_json`, `render_text(…, chained=…)`.
  - **Tests** (`test_report.py`, `RunReport` values built directly): JSON
    key order at every level and the summary counts; problems via
    `as_dict`; text lists failed and rendered charts with their problems and
    notices and omits UNCHANGED and CHECKED charts without findings; chained
    text is `""` for a run with only unchanged charts and no findings;
    `failed` is false for a run whose only findings are notices; lines
    ordered by page then line.
  - **Mutations:** sort JSON keys; print unchanged charts in chained mode;
    count notices in `failed`.
  - **Observable:** `uv run pytest tests/dashboards/test_report.py` green
    with every mutation recorded red.
  - _Requirements: 12.4, 13.6, 14.8, 14.9, 15.4, 15.5, 15.6_

- [ ] 6. Command, pass and integration wiring

- [x] 6.1 Add the `fitdocs dashboard` command
  - **`src/fitdocs/cli.py`** per design § CliCommand: `_DashboardForm`,
    `_DashboardFormat`, option singletons at module scope (B008),
    `dashboard_command`, `_query_environment()` extracted from
    `query_command` (which then uses it, behaviour unchanged); lazy imports
    of `fitdocs.dashboards.*` inside the command so `import fitdocs.cli`
    still loads no duckdb; docstring "Fourteen commands are registered" and
    the command-list bullet after `query`, before "Two further commands".
  - **Pins that move** (owned edits): `tests/query/test_cli_query.py:803-812`
    and `tests/test_cli_skill.py:261-269` (`len == 14`, "Fourteen");
    `tests/index/test_cli_index.py:604-608` ("Thirteen" → "Fourteen"; its
    command-list and exit-code phrases at `:609-614` stay as they are).
    `tests/test_packaging.py` `_EXPECTED_COMMANDS` and
    `tests/test_agent_skill.py` `_COMMAND_MAP` derive from the app and must
    pass unedited.
  - **Tests** (`test_cli_dashboard.py`, `CliRunner`, `FakeSource` or the
    real index fixture): `kinds` without any data root configured exits 0;
    `kinds --format json` equals `json.dumps(describe_kinds())` parsed;
    `kinds x` and `freeze` without targets exit 2; an unknown target exits 2
    listing page names; `check` on a page with one bad directive exits 1 and
    writes nothing; `refresh` of a healthy page exits 0 and writes; a notice
    alone exits 0; `--format json` output parses and carries the problems;
    an index-location configuration error exits 2 before any write.
  - **Mutations:** exit 1 on notices; resolve the data root for `kinds`;
    import `fitdocs.dashboards.binding` at module top (the existing
    `tests/index/test_boundary.py:625-660` duckdb-not-loaded check reds).
  - **Observable:** `uv run pytest tests/dashboards/test_cli_dashboard.py
    tests/query/test_cli_query.py tests/test_cli_skill.py
    tests/index/test_cli_index.py tests/index/test_boundary.py` green.
  - _Requirements: 14.1, 14.5, 14.6, 14.8, 14.9_
  - _Depends: 4.3, 5.3, 5.4_

- [x] 6.2 Return the index outcome and chain the dashboard pass (analytics-index Amendment 1, post-pass)
  - **`src/fitdocs/cli.py`** per design § CliPass: `_run_index_pass` returns
    `IndexReport | None` (unchanged output); `_run_dashboard_pass(data_root,
    index_report)`; called immediately after `_run_index_pass` in sync
    SOURCE (~:725), `_run_drain_passes` (~:811; drain and `pull --sync`),
    regen (~:909) and load (~:944); exit codes still computed by the
    existing `_finish` calls.
  - **Pin that moves**: `tests/index/test_cli_post_pass.py:533-543` (return
    `IndexReport | None`) and its `returned is None` assertion (now the
    report); the ordering test `:174-212` and exit-code invariance
    `:765-832` stay green unedited.
  - **Tests** (`test_pass.py`), reusing the entry-point harness of
    `tests/index/test_cli_post_pass.py:765-832` (import its helpers; do not
    edit them), per entry point (sync SOURCE, drain, `pull --sync`, regen,
    load) with the index outcome monkeypatched:
    the outcome classification is an **exhaustive partition**: the test
    holds a table mapping every `index.refresh.Outcome` member to
    "runs" (REFRESHED, UNCHANGED, BUILT) or "does not run" (NOT_BUILT,
    NEEDS_REBUILD, BUSY, STAGED, FAILED), asserts the table's keys equal
    `set(Outcome)` (a new member reds until classified), and is parametrized
    over it: "runs" → a staged page's relative chart is written; "does not
    run", and a raising refresh (`None`) → one `Dashboards: not refreshed; …`
    line and the page byte-identical; no
    `dashboards/` → no output; a raising pass → one line and the command's
    exit code equal to a run without the pass; `KeyboardInterrupt` from the
    pass propagates (identity preserved); `history`, `plan`, `check`,
    `query` and `index` never call `_run_dashboard_pass` (spy).
  - **Mutations:** run the pass for NOT_BUILT; drop BUILT from the success
    set; catch `BaseException` in the pass; call the pass before
    `_run_index_pass`; drop the drain call site (`pull --sync` case reds).
  - **Observable:** the full `uv run pytest` is green (this task rewires
    every writing command), with every mutation recorded red through the two
    focused modules.
  - _Requirements: 13.1, 13.2, 13.3, 13.4, 13.5, 13.6, 13.7_

- [x] 6.3 Prove a real interrupt ends a run cleanly
  - **Tests** (`test_interrupt.py`, harness after
    `tests/query/test_interrupt.py`): a child `fitdocs dashboard refresh`
    against the real index fixture with one relative chart whose SQL runs
    for many seconds, a marker file written when the session executes (the
    store-execute hook pattern of the query harness), SIGINT once the marker
    exists: the child exits 130 within a stated bound (record the measured
    time), stderr ends `Dashboard run interrupted.`, the page and
    `dashboards/assets/` are byte-identical to before, and no
    `.dashboards-*.tmp` remains. Run on duckdb 1.5.6, and on 1.2.0 where
    available (record).
  - **Mutations:** make `QuerySession.close` skip `interrupt_quietly` (the
    child hangs past the bound, as the open queue item describes); catch
    `KeyboardInterrupt` in the engine and continue.
  - **Observable:** `uv run pytest tests/dashboards/test_interrupt.py` green
    twice in a row with both mutations recorded red.
  - _Requirements: 7.10, 13.7, 14.8_

- [x] 6.4 Register the dashboard writers with the confinement guard
  - **`tests/test_confinement.py`**: `WRITING_ENTRY_POINTS` appends
    `dashboard` (refresh of a page with one relative and one frozen chart:
    a first freeze), `dashboard-freeze` (freeze of that frozen chart) and
    `sync-with-dashboards` (sync with an index and a staged page), each with
    a non-vacuous predicate (a region rewritten, an image and, where frozen,
    a snapshot written); their ids join the set that permits the external
    index directory (~:1344, ~:1371).
  - **Tests**: the parametrized confinement test covers the three entries;
    a membership test like `test_plan_is_a_registered_writing_entry_point`.
  - **Preconditions asserted**: each predicate is shown false for a run of
    the same entry over a page whose only directive is invalid (nothing
    written), so it cannot pass vacuously.
  - **Mutations:** make `storage.write_asset` also write a stray file at the
    data root (the confinement assertion reds for all three entries); drop
    the image check from a predicate (its precondition case stops failing).
  - **Observable:** `uv run pytest tests/test_confinement.py` green with the
    three entries listed in the parametrize ids.
  - _Requirements: 2.1, 16.6_

- [x] 6.5 Add `dashboard` to the no-network list (connectors Amendment 3)
  - **`.kiro/steering/tech.md`**: the list becomes "`sync`, `regen`,
    `load`, `dashboard`, `check`, `query`, …" (inserted before `check`, so
    the tail pins in `tests/connectors/test_network_statements.py:666-669`
    and `tests/query/test_changelog_entry.py:143-146` stay green unedited).
  - **`tests/connectors/test_network_statements.py`**: a new pin of the
    phrase "`load`, `dashboard`, `check`".
  - **`tests/connectors/test_e2e.py:321-332`**: the parametrization gains
    `("dashboard", ["refresh"])`; like the `query` case (`:352-369`) it sets
    `FITDOCS_INDEX_DIR` for each root and builds the index, and it stages a
    dashboard page with one relative chart in both the bare and the wired
    root, so the command really opens the index and renders under the socket
    guard (a page-less run would be vacuous).
  - **Records**: `.kiro/specs/connectors/requirements.md` `## Amendment 3
    (2026-10-xx): dashboard joins Req 14.1, landed by dashboards` and Req
    14.1's list; `spec.json` `amendments` entry naming the two tests.
  - **Preconditions asserted**: the staged chart's region is written in
    both roots (the run reached the index).
  - **Mutations:** remove `dashboard` from tech.md (new pin reds); open a
    socket from the engine during a run (the e2e socket guard reds).
  - **Observable:** `uv run pytest tests/connectors tests/query/test_changelog_entry.py`
    green.
  - _Requirements: 14.10, 19.3, 19.6_

- [ ] 7. The agent surface

- [x] 7.1 (P) Ship the `fitdocs-dashboards` skill and point the analytics skill at it
  - **`src/fitdocs/skills/fitdocs-dashboards/SKILL.md`** per design § Skill
    and Docs: frontmatter like `fitdocs-analytics`; the ten headings; the
    directive and its keys with one complete example in a fenced block;
    relative vs frozen and `fitdocs dashboard freeze`; `$today - 84` and the
    INTERVAL-is-a-timestamp warning; alias suffixes; pace from speed
    (`1000.0 / NULLIF(speed_mps, 0) AS pace_s_per_km`) and that a non-finite
    result is refused, not hidden; that a missing row is not an absent value
    (a gap needs a row with a NULL value; a stacked week with no activity
    needs `COALESCE(…, 0)`), in "Columns, units and pace"; the running-cadence
    strides warning (one foot, FIT convention; doubling loses the suffix);
    the check loop with `fitdocs dashboard check --format json`; the traps
    (column 0, no indentation, no `-->`/`--!>`, `sql: |`) and Obsidian Live
    Preview; ownership; `fitdocs dashboard kinds` instead of a kinds list.
    It names locations as "the dashboards directory" and "its assets
    directory", never with a trailing slash (see the guards below), and it
    carries `CONTRACT_DOCUMENTATION_URL`.
  - **`src/fitdocs/agentskill.py`**: `DASHBOARDS_SKILL_NAME`,
    `PACKAGED_SKILLS` appended; docstring "Four skills".
  - **`release/artifact-policy.toml`**: the new SKILL.md in `wheel_required`.
  - **`src/fitdocs/skills/fitdocs-analytics/SKILL.md`**: one sentence under
    "Further reading" pointing at `fitdocs-dashboards` for charting an
    answer on a wiki page (no heading change; no `dashboards/` spelling).
  - **Stale prose**: `docs/wiki-integration.md` "The packaged skills"
    (`:10-19`, the `fitdocs skill` listing) gains the fourth skill;
    `README.md:113` "Three packaged skills ship today" → four.
  - **Existing per-skill guards the new skill must satisfy**
    (`tests/test_agent_skill.py`, parametrized over `PACKAGED_SKILLS`):
    `:437-477` frontmatter keys exactly `name`, `description`, `license`,
    `compatibility`, `metadata`, with "when" in the description; `:1494-1500`
    no `](./` and no `src/fitdocs`; `:1527` the contract URL present;
    `:1533-1545` no `OWNED_PATHS` entry as a substring of the body (after 1.2
    that bans `dashboards/` and `dashboards/assets/`, in this skill and in
    the analytics pointer); `:1551-1554` exactly one heading containing
    "Ownership"; `:1077-1094` a `bash` fence and an inline
    `` `fitdocs <command>` `` span; `:1146-1167` every bound command is
    registered (`dashboard`, after 6.1).
  - **Pins that move**: `tests/test_skill_locator.py:60,65,205,208`,
    `tests/test_release_artifacts.py:143-152`, `tests/test_skill_wheel.py`,
    `tests/test_cli_skill.py:67`, `tests/test_packaging.py:883`,
    `tests/test_releasing_docs.py:573` with `docs/releasing.md` if it lists
    skills; `tests/test_agent_skill.py` gains a `_DASHBOARDS_HEADINGS`
    profile and any per-skill phrase pins it applies to every skill.
  - **Tests**: the skill profile (headings in order); phrase pins for the
    cadence warning ("strides per minute", "steps"), the pace expression,
    the non-finite note ("non-finite"), the missing-row note ("missing row",
    "NULL", "COALESCE") found inside the "Columns, units and pace" section,
    `$today - 84`, `fitdocs dashboard kinds`, `fitdocs dashboard check`;
    every `kind:` value in the skill's example directives is in
    `kind_names()` (read live; no literal list) and the skill holds no
    channel or option table; the analytics pointer present; a precondition
    that `"dashboards/"` is in `OWNED_PATHS` and that the skill body mentions
    "dashboards directory", so the substring guard at `:1533-1545` is live
    for this skill rather than passing vacuously.
  - **Mutations:** drop the cadence paragraph; drop the missing-row
    paragraph (its section-scoped pin reds); paste a kinds table into the
    skill (guard reds); write "the `dashboards/` directory" in the skill (the
    owned-path guard reds); use a kind name absent from the registry in an
    example; remove the policy entry (release-artifact test reds).
  - **Observable:** `uv run pytest tests/test_skill_locator.py
    tests/test_agent_skill.py tests/test_release_artifacts.py
    tests/test_skill_wheel.py tests/test_cli_skill.py
    tests/test_wiki_integration_docs.py tests/test_packaging.py
    tests/test_releasing_docs.py` green and `fitdocs skill` lists four
    skills.
  - _Requirements: 18.1, 18.2, 18.3, 18.4, 18.5, 18.6, 18.8_
  - _Boundary: AgentSkill_
  - _Depends: 1.2, 6.1_

- [x] 7.2 (P) Publish `docs/dashboards.md` with its live kinds block
  - **`docs/dashboards.md`** per design § Skill and Docs: the H2s; the
    directive reference; regions and assets; relative vs frozen and the
    snapshot files (`*.snapshot-<n>.json`, never deleted; do not
    git-ignore them even if images are ignored); writing the SQL (windows,
    suffixes, pace, non-finite results refused, and the missing-row note: a
    gap needs a row with a NULL value, a stacked empty week needs
    `COALESCE(…, 0)`); the check loop; the command's forms, targets, formats
    and exit codes; ownership; the traps and Live Preview; links from
    outside `dashboards/` are not protected from image cleanup; the kinds
    block between `<!-- dashboard-kinds:start -->` and
    `<!-- dashboard-kinds:end -->` generated from the registry.
  - **`docs/index.md`**: a Dashboards row after Analytics;
    `tests/test_docs_guarantees.py` `_REQUIRED_ENTRY_POINT_LINKS` gains
    `dashboards.md`.
  - **Tests** (`test_docs_dashboards.py`, after `tests/query/test_docs_analytics.py`):
    the block equals `kinds_markdown(describe_kinds())`; `regenerate_kinds_block`
    and a module `__main__` (`uv run python -m tests.dashboards.test_docs_dashboards`),
    failing on duplicate or reversed markers; the H2 list; phrase pins for
    18.2–18.4, including the missing-row note ("missing row", "NULL",
    "COALESCE") and the non-finite note inside "Writing the SQL"; every
    `fitdocs …` line in a bash block names a registered
    command and option; directive examples sit inside fences (scanning the
    doc with `scan_page` finds no live directive).
  - **Mutations:** drop the missing-row paragraph from "Writing the SQL"
    (its section-scoped pin reds); leave one kind's line stale in the block;
    move an example
    directive out of its fence (the live-directive check reds); misspell an
    option in a bash example.
  - **Observable:** `uv run pytest tests/dashboards/test_docs_dashboards.py
    tests/test_docs_guarantees.py tests/connectors/test_network_statements.py`
    green (the last globs `docs/*.md` for retired phrases).
  - _Requirements: 18.2, 18.3, 18.4, 18.7, 18.8_
  - _Boundary: Docs_
  - _Depends: 3.1, 3.4, 6.1_

- [ ] 7.3 Reconcile the kinds listing with `chart-catalog`, whichever lands second
  - **The rule** (roadmap Phase 11 › Boundary Strategy, stated identically
    in `chart-catalog`'s brief "Second-lander duty"): whichever of
    `dashboards` and `chart-catalog` lands second regenerates the kinds block
    in `docs/dashboards.md` and re-pins any registered-kind count. dashboards
    pins no count (its tests read `kind_names()` / `describe_kinds()` live),
    so the block is this side's only artifact.
  - **If `chart-catalog` is not on `main` when this task runs** (no name
    beyond the eight core kinds in `kind_names()`): change nothing. Record
    in Implementation Notes that `chart-catalog`'s second-lander task
    regenerates the block at its landing with
    `uv run python -m tests.dashboards.test_docs_dashboards`, and that its
    kinds then appear in `fitdocs dashboard kinds` with no dashboards change.
  - **If it is**: regenerate the block (a second run leaves `git diff`
    empty); run chart-catalog's registry and kind tests and
    `grep -rn "kind_names()\|describe_kinds()\|len(KINDS)" tests/` and
    re-pin any registered-kind count this landing makes stale (expected:
    none outside chart-catalog's own prefix pins). A dashboards test that
    pins a count is a defect here: replace it with a live read and report.
    7.1's live check (every example `kind:` is in `kind_names()`) covers the
    skill; run it.
  - **Re-evaluated at the final rebase** (task 8.5): `chart-catalog` may
    land between this task and the merge; 8.5 re-runs this decision.
  - **Tests**: none of its own; the block pin from 7.2 is the proof.
  - **Mutations** (second branch only): leave the block stale (the 7.2 pin
    reds).
  - **Observable:** the full `uv run pytest` is green on the merged 7.1 and
    7.2 streams (their integration point); in the second branch the
    regenerated block is committed, in the first the Implementation Notes
    entry names chart-catalog's task.
  - _Requirements: 18.7, 20.1_

- [ ] 8. Records, steering and validation

- [x] 8.1 Publish the dashboards category in the ownership contract (wiki-contract Amendment 5, part 2; analytics-index Amendment 1, contract copies)
  - **`docs/ownership-contract.md`**: a new section "Dashboard Pages:
    Athlete Pages with fitdocs Regions" (page rule; `type: dashboard`
    documented, never required or written; directive is the athlete's;
    region and image and snapshot ownership; snapshots never modified or
    deleted; image cleanup by reference scan; links from outside
    `dashboards/` not protected; never a generated document, never a
    banner); the analytics-index section's sentence at `:191-193` gains the
    named exception; "User-Owned and Tool-Filled Regions" names chart
    regions as tool-owned regions in an athlete page; "Overwrite Semantics"
    gains a `fitdocs dashboard` bullet and the pass in the sync, regen,
    load, drain and `pull --sync` bullets.
  - **Pins that move**: `tests/index/test_contract_docs.py:56` (the
    exception wording replaces "never reads the index back into a
    document"); new phrase pins for the section's guarantees.
  - **Records**: `.kiro/specs/wiki-contract/requirements.md` `## Amendment 5
    (2026-10-xx): the dashboards location and athlete pages with fitdocs
    regions, landed by dashboards` with appended criteria in the
    `_(added by Amendment 5)_` style; `design.md` dated paragraph;
    `spec.json` `amendments` entry naming the tests of 1.2 and this task.
  - **Mutations:** drop the snapshot-never-deleted sentence (its pin reds);
    restore the old index sentence (the moved pin reds).
  - **Observable:** `uv run pytest tests/test_ownership_contract.py
    tests/index/test_contract_docs.py tests/identity tests/compose/test_contract_docs.py
    tests/test_docs_guarantees.py` green; the doc reads end to end with no
    sentence contradicting the dashboards section (grep "never read",
    "tool-owned", "four owned").
  - _Requirements: 2.4, 19.1, 19.2, 19.6_

- [x] 8.2 Record the steering, the CHANGELOG and the analytics-index amendment
  - **`.kiro/steering/tech.md`**: the Architecture paragraph states the
    named exception ("…never read back into a document, except the chart
    regions and assets of dashboard pages under `dashboards/`; workout,
    history and block documents never read it"); the Network paragraph's
    `fitdocs query` sentence gains that `fitdocs dashboard` and the
    dashboard pass run chart SQL through the same sandbox.
  - **`.kiro/steering/structure.md`**: the `query` bullet reads "only `cli`
    and `dashboards` import it"; a new `dashboards` bullet: imports `query`
    (in `dashboards.binding` only), the chart kit facade (and `kit.format`
    in `dashboards.region`), `units`, `layout`, `contract` and `yaml`; only
    `cli` imports it; it never imports `duckdb`, `index` or a clock. Do not
    amend chart-kit's `units` paragraph: check that it names no exhaustive
    list of `units`' importers (chart-kit words it that way), so
    `dashboards.binding` importing `units` contradicts nothing; if it does
    carry an exhaustive list, stop and report rather than editing it. Leave
    the `index` bullet unchanged, and check before and after the edit that
    its pins (the `index`-bullet phrase chart-kit's 7.1 re-pinned with
    `units` in `tests/connectors/test_network_statements.py`, and
    `tests/index/derived/test_published.py:28-33`) are green; if either is
    red before this task's edit, stop and report (a cross-spec issue for the
    controller, not this task's to fix).
  - **`CHANGELOG.md`** Unreleased › Added: one bullet starting
    "- `fitdocs dashboard`" naming the forms, the pass after the index
    refresh, the `fitdocs-dashboards` skill, `docs/dashboards.md`, the
    ownership contract version (main+1), the user action (run `sync` or
    `regen` once to place `dashboards/AGENTS.md`) and that `[plans] path`
    may no longer be `dashboards`.
  - **Records**: `.kiro/specs/analytics-index/requirements.md` Req 5.6 gains
    the named exception and `## Amendment 1 (2026-10-xx): the dashboards
    exception, a named-parameter read and the post-pass outcome, landed by
    dashboards` (naming 2.1, 6.2, 8.1, 8.2). The amendment states that
    `IndexConnection.execute` and its positional callers are unchanged, that
    positional `execute` with params still goes through `.sql(params=)` and
    so materialises its whole result (a known hazard for any future large
    positional read), and that this is outside the amendment's scope;
    `spec.json` entry.
  - **Pins that move**: `tests/connectors/test_network_statements.py:640-644`
    (the Architecture sentence now carries the exception).
  - **Tests** (`tests/dashboards/test_published.py`, created here, after
    `tests/query/test_changelog_entry.py`): exactly one Unreleased › Added
    bullet starting "- `fitdocs dashboard`", absent from released sections;
    the tech.md exception and sandbox sentences; the structure.md
    `dashboards` bullet and the `query` bullet's importer phrase.
  - **Validation (steering class)**: read `tech.md` and `structure.md` end
    to end and grep `.kiro/steering/` and `CLAUDE.md` for "never read back",
    "only `cli` imports", "Thirteen", "three skills".
  - **Mutations:** drop the exception from tech.md (moved pin reds); add a
    second `fitdocs dashboard` bullet (CHANGELOG pin reds).
  - **Observable:** `uv run pytest tests/dashboards/test_published.py
    tests/connectors/test_network_statements.py tests/query/test_changelog_entry.py
    tests/index/derived/test_published.py tests/test_changelog.py` green; the
    greps find no contradicted statement.
  - _Requirements: 19.1, 19.4, 19.5, 19.6_

- [x] 8.3 Prove the whole feature end to end, deterministically
  - **Tests** (`test_e2e.py`, real index fixture): a staged page with a
    relative bar of weekly distance (`$today - 84` window) and a frozen
    scatter: `fitdocs sync` renders both; a second `sync` changes no byte
    or mtime under `dashboards/`; `fitdocs regen` and `fitdocs index
    --rebuild` leave the snapshot byte-identical; with the index directory
    removed, `fitdocs dashboard refresh` re-renders the frozen chart and
    reports `index_unavailable` for the relative one (exit 1), its region
    byte-identical; a dashboard page carrying `type: workout` frontmatter is
    untouched by `sync`, `history` and `plan` outside its regions (1.7); no
    line starting `<!-- fitdocs:generated` is ever written into a page (1.6).
  - **Page goldens** (`golden/*.md`, compared as bytes; regenerated only by
    the module's `main()`): a relative SVG chart, a frozen chart with its
    reference line, a `stat` chart, a chart with `show_rows`, a never-rendered
    note. Images are compared with the kit's live `render_chart` output,
    never a stored copy. Each golden is shown able to fail by: swapping two
    caption parts; dropping the reference line; dropping the blank line
    before the end marker.
  - **Determinism** (`test_determinism.py`): two child processes with `TZ`
    UTC/Pacific/Auckland, `LC_ALL` C/C.UTF-8 and `PYTHONHASHSEED` 0/1 run
    the engine with a fake source and a fixed date over the same pages (one
    relative chart whose latest value is a DATETIME at 05:00, one frozen
    chart); SHA-256 of every page, image and snapshot equal.
  - **Mutations:** append `hash(page) % 97` to the asset mark (the
    cross-process run reds, since its two children use different hash
    seeds); take the
    caption's `through` date from `value.astimezone(timezone.utc).date()`,
    with the fixture's latest value a DATETIME at 05:00 (only the
    `TZ=Pacific/Auckland` child differs). The run-date trap is pinned in 5.2
    (D1 then D2), not here: both syncs here read the same day.
  - **Observable:** `uv run pytest tests/dashboards/test_e2e.py
    tests/dashboards/test_determinism.py` green with every mutation recorded
    red.
  - _Requirements: 1.6, 1.7, 2.1, 9.2, 9.3, 10.2, 10.8, 17.1, 17.2_

- [x] 8.4 Guard the dashboards boundary
  - **Tests** (`test_boundary.py`, after `tests/query/test_boundary.py` and
    `tests/compose/test_boundary.py`): the package's module tuple equals
    `rglob` both ways with a positive control (the walk saw ≥ 11 modules);
    the rank matrix of design § Architecture (every intra-package import
    points to a strictly lower rank; `engine` never imports `binding`);
    allowed imports per module (`yaml` only in `directive`; `fitdocs.query`
    only in `binding`; `kit.format` only in `region`; `units` only in
    `binding`; no other `fitdocs.render` module; no `duckdb`, `fitdocs.index`,
    `sync`, `history`, `plans`, `load`, `model`, `ingest`, `connectors`,
    `tiles`, `plugins`, `cli`) by dotted descent, including `importlib`
    forms; clock spellings and names as the compose guard; network modules
    (`socket`, `urllib`, `http`, `ssl`); only `fitdocs.cli` imports
    `fitdocs.dashboards` (scan of every `src/fitdocs` module outside the
    package, > 100 files); each rule with a synthetic violating source the
    same check rejects.
  - **Mutations:** add `from datetime import date; date.today()` to
    `engine.py`; import `fitdocs.query.command` in `engine.py`; import
    `fitdocs.dashboards.report` from `fitdocs.sync` (each reds its rule).
  - **Observable:** `uv run pytest tests/dashboards/test_boundary.py` green
    with every mutation recorded red.
  - _Requirements: 14.10, 20.2, 20.3, 20.4_

- [ ] 8.5 Validate the feature after the final rebase
  - Rebase onto current `main`; re-derive `CONTRACT_VERSION` as main + 1 and
    the four amendment numbers if `main` moved them; re-run task 7.3's
    decision; keep both sides of every append-only seam (command count, the
    no-network list, `WRITING_ENTRY_POINTS`, `OWNED_PATHS`/`DECLARED_DIRS`,
    `PACKAGED_SKILLS`, mypy files, CHANGELOG).
  - Run `uv run pytest && uv run ruff check . && uv run ruff format --check .
    && uv run mypy`, plus `gh run list --branch <branch>` green on the Linux
    runner before the merge (memory: check CI before merge).
  - Smoke, between suite runs: in a scratch data root, `fitdocs dashboard
    kinds`, a page written from the skill's example, `fitdocs dashboard
    check --format json`, `refresh`, a second `refresh` writing nothing,
    `freeze`.
  - **Observable:** the full suite, lint, format and mypy are green after
    the rebase; CI is green on the branch; `/kiro-spec-status dashboards` is
    clean; Implementation Notes record the final contract version, amendment
    numbers and the 7.3 branch taken.
  - _Requirements: 14.1, 17.1, 17.2, 19.2, 19.6, 20.1_

## Implementation Notes

- **1.1 (upstream confirmed on main 5231337):** every chart-kit name in
  Upstream Prerequisites imports with the design's shape
  (`validate_chart(request, columns) -> tuple[ChartProblem, ...]`,
  `render_chart(request, data) -> RenderedChart(kind, output, text)`,
  `ChartProblem` carries a `ref` that `from_chart_problem` drops,
  `Column(name, kind, unit=None, label=None)`); `table` registered; every
  `kind_names()` entry has `tests/render/charts/kit/test_<name>.py` with
  `CASES`; `escape_markdown` / `clean_text` behave as stated. Queue item
  `2026-10-08-store-facade-user-interrupt-unwrapped` still **open**.
  `CONTRACT_VERSION` on main `"9"` (1.2 sets `"10"`). Next free amendment
  numbers: analytics-index 1, analytics-query 1, wiki-contract 5,
  connectors 3. structure.md `index`-bullet pin green (47 passed).
- **1.1 deviation:** `dashboard_problem(..., **fields: Any)` instead of
  design's `object` — `object` does not type-check when forwarded into
  `Problem(...)` under mypy strict; callers pass only real `Problem` fields.
  `Problem.code` is a plain `str` (`from_chart_problem` stores `.value`).
- **1.1 shared helpers (later tasks consume, (P) tasks never edit):**
  `_helpers.py`: `directive_block(keys, ending=)` (ending applied inside
  multi-line values too), `region_block`, `page_text`, column/data builders,
  `FakeSource` (`queue`, `.calls` with `today`, `.opened`, `.misused`,
  `.closed`, `.opener()`), `MustNotOpen` (`attempts`), `must_not_open`,
  `unavailable_opener`, `make_data_root`, `write_page`, `snapshot_of`,
  `assert_untouched`, `query_environment`. `conftest.py`:
  module-scoped `indexed_dashboard_root` (frozen `IndexedDashboardRoot(root,
  index_dir, home, environ, today)`; two synthetic .fit files, no plans,
  races or derived inputs) and `copy_dashboard_root(fixture, tmp_path)` —
  use the copy for any test that writes pages or rebuilds/removes the index,
  and apply its `environ` via monkeypatch (the module fixture leaves the
  shared `FITDOCS_INDEX_DIR` in `os.environ`). Teardown HOME-purity names
  fitdocs paths only.
- **3.4 (3 review rounds, test-side only):** formats are the implementer's
  reading of a loose design. Text: `name (output) — desc`, `  channels:` with
  `    x* number|date`, options `    name type [default=X] [choices=a|b]
  [range=lo..hi]` (open ends empty), `  bound: …`; empty sections omitted.
  Markdown: H3 per kind, channels/options tables omitted when empty (design
  lists channels unconditionally — accepted deviation), values `a, b` /
  `lo to hi` / `lo and up` / `up to hi` / `-`. All free text collapsed to one
  line (no output line can start `<!-- fitdocs:`). Design § Testing's
  monkeypatched-`KINDS` test realised as dict stubs per task text; a CLI-level
  "registry read at call time" test is not carried by any task (queued).
- **1.2:** `CONTRACT_VERSION` "9" → "10". Declaration wording deviates from
  design § Declaration item 2: "declares a chart" / "after a successful index
  refresh" (design: "each") because `test_no_declaration_quantifies_over_documents`
  bans "each"; `...` for `…` (goldens are ASCII). 8.1 amends the design text.
  `_OWNER_BLOCK` format key renamed `{generator}` → `{owner}`. `DECLARED_DIRS`
  order: workouts, history, blocks, fit-archive, dashboards. Carried forward:
  5.1 discovery and `has_dashboards` must skip the generated
  `dashboards/AGENTS.md` (it contains literal directive/marker text); 8.1 owns
  the contract's narrative sections (index "never read back", the "those four
  files" example, unpinned "five owned"); 6.4 refreshes stale counts in
  `tests/test_confinement.py` and `tests/test_declaration_refresh.py` prose.
- **3.3 (4 review rounds):** units and labels are not stored (decoded
  columns carry `unit=None`; the engine re-derives units from names).
  `encode` raises `ValueError` on any non-storable cell (non-finite number,
  aware datetime, wrong kind, wrong row width). `decode` refuses: other than
  the exact keys, format, version 1, known kinds, row widths, per-kind JSON
  type/shape (Decimal strings `-?[0-9]+(\.[0-9]+)?`, dates
  `YYYY-MM-DD`, datetimes with exactly 0 or 6 fraction digits), finite
  numbers, slug page/chart; byte layout beyond UTF-8 + one trailing newline
  is not enforced; `sql_sha256` is not checked against `sql`.
  `SNAPSHOT_NAME_RE` = `(?P<id>SLUG)\.snapshot-(?P<generation>[1-9][0-9]*)\.json`
  (fullmatch). **5.3 must handle** `encode`'s `ValueError` on a first freeze:
  a NaN in an UNUSED number column renders fine (kit validates used columns
  only) but cannot be stored. The local `_SLUG` copy is reconciled with
  `grammar.SLUG` at the group-3 merge.
- **3.2 (2 review rounds):** folded plain / `>-` titles and windows are
  accepted as one line (`"a b"`), per design's "no `\n`" (pinned;
  requirement wording queued). `Problem.option` carries the directive key on
  `missing_key`, `unknown_key`, `field_value`, `mode_value`, `sql_style`,
  `id_grammar` — report (5.4) and skill/docs (7.1/7.2) must say so.
  `Problem.chart` is the valid id on key/field problems, `None` on
  `id_grammar`, `yaml_syntax`, `yaml_shape`, `duplicate_key` — 5.x engine
  decides attribution (15.1). Order: structural problems return alone;
  otherwise missing (REQUIRED_KEYS order), unknown (code-point sorted),
  `id_grammar`, then fields `kind, mode, title, sql, channels, options,
  window, show_rows`; the report must still sort by page line (15.5).
  Page lines = `open_line + 1 + body[:index].count("\n")` (`mark.index` and
  `ReaderError.position` are character offsets into the body), so U+2028 /
  U+0085 / lone `\r` do not shift lines. `directive._ID_RE` duplicates
  `grammar.SLUG` until the group-3 reconciliation.
- **2.1 (4 review rounds):** `store.py` additions only:
  `IndexResult.from_cursor` (returns private `_CursorResult`),
  `IndexConnection.execute_named`, `statement_parameters`. On duckdb 1.2.0
  `cursor.description` types are DB-API names (`NUMBER`, `STRING`,
  `DATETIME`), on 1.5.6 SQL names (`BIGINT`, `VARCHAR`, …) — 4.3's
  two-vocabulary `TYPE_KINDS` must map both. Streaming verified on both
  (growth ~2.8 MB; `.sql(params=)` mutant ~270 MB). **DuckDB race (controller
  ruling):** under CPU load, streamed results misreport an interrupt during
  fetch as `InvalidInputException("…INTERRUPT Error…")` → `IndexStatementError`,
  and a mid-stream SQL error as `InterruptException` → `IndexInterrupted`
  (plain duckdb, both versions, ~3–7%). The facade wraps by class unchanged;
  **2.2 must classify any failure after the statement timer fired as
  `StatementTimedOut`** and decide a no-timer `IndexInterrupted`. Tests: exact
  wrapping pinned with fake cursors; real-DuckDB tests are tuple-accepting
  smoke tests (interrupt one in a bounded subprocess). A cursor-backed result
  is the connection: the next statement on that connection replaces an
  unfinished result (2.2's session must finish one result before the next).
- **3.1 (3 review rounds; controller rulings):** (R1) fence state is also
  tracked inside a region body — a fence-opening line in the body opens a
  fence, a column-0 `<!-- fitdocs:` line inside it neither closes nor cuts the
  region, a fence open at end of page runs the region to the end unclosed
  (`end_line`/`intruder_line` None); fences stay untracked inside directive
  bodies. Reason: the fence-blind region scan let a fenced example after an
  unclosed region go live and let a fenced end marker "close" a region over
  user prose (Req 3.6 / 2.1). (R2) `DirectiveBlock.body: str | None`, None
  when unclosed (absent is None). Both deviate from design § Grammar; the
  design is amended at validation. BOM is kept in `Line.text` (exact round
  trip) and ignored only on line 1 for opener, fence and marker comparisons.
  `split_lines` splits on `\n` only (lone `\r` is text). `following_region`
  returns unclosed regions; None after an unclosed directive. An intruder
  always has `end_line` None, so **5.1 tells `region_contents`
  (`intruder_line` set) from `region_unclosed` (both None) by
  `intruder_line`.** Orphan end-marker message contains "no open region".
- **2.2 (2 review rounds; implements the 2.1 R-timeout ruling):**
  `ResultSet.column_types` is `field(default=(), compare=False)` so the
  unedited `test_result_is_a_direct_read_oracle_and_emits_nothing` passes —
  `==` ignores types, so **4.3 and 8.3 assert `column_types` explicitly**,
  and binding treats `len(column_types) != len(columns)` as a defect.
  `_column_types()` returns `()` for name-only fake columns (existing test
  fake). duckdb 1.2.0 cursor type names are `Date`/`NUMBER`/`STRING`/
  `DATETIME` (1.5.6: SQL names) — 4.3 looks them up case-sensitively per
  design `TYPE_KINDS`. R-timeout applies on the named path only
  (`params is not None`): any `IndexInterrupted`/`IndexStatementError` after
  the timer fired is `StatementTimedOut`; a no-timer `IndexInterrupted` is
  `StatementFailed(str, None)`; the positional path is unchanged (pinned).
  `QuerySession(connection, timer)`; `screen_statement` returns the kind
  str; query-level `statement_parameters` unions all statements' names
  (binding screens single-statement first). `execute_statement` materialises
  a tuple `ResultSet`, so no cursor result outlives its statement. A SIGINT
  during a streaming non-aggregating statement is not honoured for ≥20 s
  (both duckdb versions) — **6.3 uses an aggregating statement**
  (`_JOIN_STATEMENT` in `tests/query/test_interrupt.py`); the `fitdocs query`
  hazard is queued.
- **4.1 (2 review rounds):** body layout per design — every part (incl. the
  frozen reference line) is followed by exactly one blank line.
  `recorded_snapshot` returns the first full `REFERENCE_RE` line anywhere in
  the body, as path text (5.3 resolves it via `SNAPSHOT_NAME_RE` /
  `read_snapshot`; whether a reference naming another page/chart is honoured
  is the engine's call). A window that is `None`, empty or whitespace-only
  states nothing (controller ruling); `caption()` returns None when no part
  applies and `chart_body` omits it. `ValueError` guards (programmer errors;
  5.2 decides whether a hostile kit line is a chart failure under 12.1):
  `chart_body` refuses a snapshot path `REFERENCE_RE` would not read back, a
  non-markdown rows table, a kit line starting `<!-- fitdocs:` at column 0;
  `apply_edits` refuses an off-page `after_line`, replacing an unclosed
  region, a chart-id mismatch, overlapping/duplicate edits. Inserted and
  replaced lines take the ending of the line at `after_line` (the directive
  closer), adding `\n` when it has none — **5.x passes `after_line` for
  replace edits too**. Edits are position-sorted internally. `NOTE_RE` is
  used with `fullmatch` (5.1 too).
- **4.3 (2 review rounds; controller rulings R3, R4 — design § Binding
  amended at validation):** (R3) a query hint becomes the fix via
  `_sentence(error.hint)` (adds the stop, does not capitalise), so
  `Problem.fix` stays a sentence. (R4) screen-stage refusals (ONE_STATEMENT,
  STATEMENT_KIND) use binding's chart message ("a chart runs exactly one
  SELECT statement; this is <kind>"), because the query layer's
  `RESTRICTION_TEXT` ("runs only queries and EXPLAIN", "fitdocs query runs
  exactly one statement") misleads chart authors; run-stage refusals keep
  `RESTRICTION_TEXT`. `sql_refused` fix is per restriction (one SELECT /
  read only the index's tables / remove the setting / remove the write /
  remove the extension). Parenthesis strip is a fullmatch on `name(...)`, so
  `DECIMAL(18,3)[]` stays unsupported. A `column_types`/`columns` length
  mismatch raises `RuntimeError` ("fitdocs defect") — the engine lets it
  propagate. `row_cap` precedes type checks; no `rows` on `row_cap`.
  TIMESTAMPTZ: refused with a cast fix on both versions (1.5.6 `sql_failed`
  with the cast hint; 1.2.0 reports `DATETIME` and, only if pytz is
  importable — it is not in the lock — would give `value_kind`).
  `source_opener` memoises its first result incl. `SourceUnavailable`.
  `__all__` re-exports `DEFAULT_TIMEOUT_S` (monkeypatched by tests).
  duckdb 1.2.0: test_binding 133 passed.
- **4.2 (2 review rounds, test-side only):** `list_markdown` returns page
  stems for every direct `*.md` entry (incl. misnamed, directories, links)
  and skips `AGENTS.md` by exact name; `()` for a missing/linked/non-dir
  `dashboards/` — 5.1 adds `page_name` for stems failing `PAGE_NAME_RE` and
  `has_dashboards` must still use `location_refusal` for a linked
  `dashboards/`. `read_page` refusals: link → `SYMLINK`, dir/fifo →
  `NOT_REGULAR`, missing/OSError → `UNREADABLE`, non-UTF-8 → `NOT_UTF8`
  (BOM stays in `text`); engine maps the first three to `page_unreadable`,
  the last to `page_encoding`. Non-slug page/chart raise `ValueError`;
  `read_snapshot` returns None for any rel path that is not exactly
  `assets/<slug>/<SNAPSHOT_NAME_RE>`. `write_asset`/`create_snapshot` raise
  `FileNotFoundError` when `dashboards/` is absent (never created);
  `replace_page` raises `FileNotFoundError` on a vanished page (5.2 reports
  `write_failed`) and `OSError` on a link/dir — 5.3 catches `OSError` from
  `replace_page`, `write_asset`, `create_snapshot`. `latest_snapshot` skips
  non-regular entries; `create_snapshot` counts every occupant for `1+max`,
  retries on `FileExistsError`, and may call `encode_for` more than once.
  `remove_stale_images` returns None (skipped) on a linked/non-dir location
  or any unreadable/non-UTF-8 markdown, `()` when nothing exists; scans
  every regular `.md` under `dashboards/` except top-level `assets/`,
  never follows links, removes only marked (UTF-8, `is_generated`)
  unreferenced `.svg` and directories it emptied. Old-format marked assets
  are rewritten (`written`). No fsync (repo convention). `test_storage.py`
  has a module-local autouse 10 s SIGALRM guard raising `StorageHung`
  (`BaseException`, so storage's OSError catches cannot absorb it).
  Case-insensitive macOS folds case-only decoys; pair case rejections with
  real paths (`.`, `..`, `Bad_Dir`).
- **5.1 (4 review rounds; final F2 assertion added and mutation-verified by
  the controller — a downgrade from a 5th reviewer round):** extra planning
  API (design amended at validation): `plan_run(request) -> RunPlan(
  location_problems, pages)`, `PlannedPage(name, file, scan, problems,
  notices, charts)`, `PlannedChart(chart, line, close_line, directive,
  region, need, snapshot, problems)`, `DataNeed` {FETCH, RECORDED, LATEST};
  `run_dashboards` ignores `open_source` until 5.2; `RunReport.index` is
  `"not_needed"` until 5.2. **Trusted-id rule:** a chart's identity is the
  parsed `chart_id`, else the first non-None `chart` among its parse
  problems; targeting, the chart filter, `resolve_targets` listings,
  duplicate detection and region association all use it. Directives with no
  trusted id (yaml_syntax, yaml_shape, duplicate_key, id_grammar, unclosed)
  are untargetable, outside duplicate detection, keep `chart` None, and claim
  the region directly below them (no orphan). `duplicate_id` is added to
  every directive sharing a trusted id, incl. ones with parse problems; a
  chart with problems is targetable. A recorded reference is honoured as
  written whatever page/chart it names (controller ruling revised to follow
  the design). `region_contents` → `Problem.line` = intruder line, message
  names the begin line; `region_unclosed` → begin line. `has_dashboards` is
  true for any unusable location or any listed markdown. `page_name` is
  reported on whole runs only. Chart problems are stable-sorted by line;
  pages in name order. A terminator directive is still parsed.
- **5.4 (3 review rounds; rulings R5, R6 — design § Report amended at
  validation):** the report sorts on its own, stably, in both forms: pages
  by name, charts by line, problems/notices by line (no line first,
  same-line kit order kept), location problems by page (None first),
  `removed` by code point. Text collapses every whitespace run in message,
  fix and accepted values to one space (a multi-line database error cannot
  break a line); JSON stays raw, `indent=2`, `ensure_ascii=False`, no
  trailing newline (6.1 echoes it with one). Text layout: location then
  index problems at column 0 (`<code>: <message> <fix>`), a bare `<page>`
  header for page-level findings, chart headers `<page>:<line> <id>
  <outcome>` (`-` for no trusted id), problems before notices, notice label
  from `severity`; `option` not rendered in text. (R5) summary
  `Dashboards: <r> rendered, <u> unchanged, <f> failed[, <n> checked][, <k>
  images removed].` — `checked` only when n > 0; JSON summary keys unchanged
  (`charts`, `rendered`, `unchanged`, `failed`). (R6) text appends
  ` Accepted: a, b, c.` when `accepted` is non-empty. Chained text is `""`
  unless a chart is RENDERED or FAILED, any problem/notice exists, a page was
  written, or images were removed (extends the design's wording).
- **5.2 (2 review rounds):** only relative charts with `need FETCH` are
  queried/drawn/written; the source opens once after planning, only if such a
  chart exists, and closes in `finally`. An opener exception propagates
  before any write; a `RuntimeError` from the source propagates (source still
  closed). `SourceUnavailable` → `RunReport.index` = its state,
  `index_problem` a page-less `index_unavailable`, and each relative chart
  gets `index_unavailable` ("The chart was not queried: …"). **Ruling:** a
  `ValueError` from `chart_body`/`apply_edits` is a fitdocs defect and
  propagates (nothing written). Show-rows: `ChartRequest(ref, "table",
  title)` attempted even when the chart is refused; chart problems first,
  table problems with `option="show_rows"`, kit order, no re-sort.
  `ChartRequest.ref` = `<page>:<id>`. Failure bodies: a RENDERED region is
  kept byte-identical; otherwise the note states `problems[0].message` and is
  rewritten when that message changes; a planning-problem chart is never
  edited. Edits use `after_line = close_line` for insert and replace. Write
  order per page: assets, then one `replace_page`; `"foreign"` →
  `asset_foreign`, OSError → `write_failed` (both drop that chart's edit);
  page OSError (incl. vanished) → `write_failed` on edited charts only;
  `"changed"` → `page_changed` on edited charts only. A written asset stays
  when the page then fails (design order; Req 12.2 wording conflict
  recorded for validation). Outcomes: RENDERED = an asset written or an edit
  applied to a written page; `PageResult.written` only on "written".
  **Interim until 5.3:** frozen charts pass through as planned (CHECKED or
  FAILED); FREEZE renders relative charts; `ChartResult.notices` is `()`;
  no cleanup. **5.3 carry-forwards:** pin 14.7's "still render charts that
  need no query" (frozen chart with a snapshot renders while the opener
  returns `SourceUnavailable`); replace the interim FREEZE/CHECKED
  behaviour; cleanup removes a new image left unreferenced by
  `page_changed`/`write_failed` in the same run.
- **5.3 (2 review rounds; the round-2 one-test close-out — O38 — was
  verified by the controller's own mutation run, a downgrade from a 3rd
  review; rulings R7–R12):** `_settle` serves both modes: a FETCH chart
  fetches (a frozen one is encoded, decoded and drawn from the decoded rows,
  units re-derived by name); RECORDED/LATEST read + decode. Per page: snapshots,
  then assets, then one `replace_page`; a fresh region records the path
  `create_snapshot` returns. `ChartResult.snapshot` = created path, else
  planned, else None. `sql_changed` is a chart notice on both the recorded and
  adopted-latest paths. Cleanup runs once after all pages for REFRESH and
  FREEZE, never CHECK (outcome-equivalent to "after every page"); it also
  removes images left unreferenced by `page_changed`/`write_failed`.
  **R7** unstorable cell on a first freeze → `write_failed` with `column`,
  fix "Exclude or cast the non-finite values in the SQL."; no snapshot; under
  REFRESH a never-rendered chart gets the 12.3 note, under FREEZE nothing.
  **R8** `Directive.sql_sha256` hashes `sql.rstrip("\r\n")`. **R9** a FREEZE
  page target leaves relative charts untouched (CHECKED, no problem);
  `freeze_relative` only for an explicit chart target. **R10** a failing
  explicit FREEZE writes no note. **R11** engine imports
  `fitdocs.units.unit_for_column` (design § Allowed Dependencies amended at
  validation; **8.4 must allow `engine`**). **R12** a cleanup OSError is
  unhandled (queued). A failed re-freeze can leave an unused extra
  generation; a failed first freeze's snapshot is adopted next run (10.4).
  Equivalent mutants: F8 (draw from fetched vs decoded rows — round-trip is
  the identity, probed), O26 (CR half of the digest strip unreachable).
- **6.1 (1 review round):** `fitdocs dashboard {check|refresh|freeze|kinds}`
  — kinds resolves no data root, refuses targets (exit 2), reads
  `describe_kinds()` at call time (pinned; closes the 3.4 "registry read at
  call time" gap), text via `kinds_text` with `nl=False`, JSON
  `indent=2, ensure_ascii=False` + newline (controller decision, same style
  as the run report). freeze without targets exits 2 before the data root is
  resolved. check/refresh/freeze: `_resolved_data_root` → `resolve_targets`
  → `run_dashboards(RunRequest(Action(form), root, targets, _today()),
  source_opener(root, _query_environment()))`; `TargetError` and
  `IndexLocationError` exit 2 (before any write); `KeyboardInterrupt` →
  stderr `Dashboard run interrupted.`, exit 130; exit 1 iff `report.failed`;
  output = `render_json` or `render_text(chained=False)` + one newline.
  `_query_environment()` is a module function (tests monkeypatch it) with a
  stderr wait line; `query_command` behaviour unchanged.
  `_config_error` now prints with `emoji=False` (Rich turned `p:a:b` into an
  emoji; strictly a fix for all 45 callers). **Task text correction:** the
  task-named "import binding at module top" mutation does not red
  `tests/index/test_boundary.py` (binding loads no duckdb); the pin is the
  new subprocess test `test_importing_the_cli_loads_no_dashboards_module`.
  `kinds` JSON `ensure_ascii=False` is an equivalent mutant today (ASCII
  registry).
- **6.5 (1 review round):** tech.md no-network list is "`sync`, `regen`,
  `load`, `dashboard`, `check`, `query`, `history`, …"; pinned by
  "`load`, `dashboard`, `check`, `query`, `history`" in
  `tests/connectors/test_network_statements.py`. `test_e2e.py` gains
  `("dashboard", ["refresh"])` with a staged one-chart page in both roots,
  per-root `FITDOCS_INDEX_DIR` and index build, and asserts the region and
  image written in both (non-vacuous) and `Dashboards: 1 rendered,`. It
  imports `tests.dashboards._helpers.write_page` (first sibling-subpackage
  test import). connectors Amendment 3 dated 2026-10-13 (controller set the
  placeholder dates); next free connectors amendment is 4.
- **6.3 (2 review rounds):** `tests/dashboards/test_interrupt.py` runs 14
  trials (fresh child, per-trial marker) of a real `dashboard refresh` over a
  `copy_dashboard_root` copy; the store hook wraps `execute` and
  `execute_named` (only `execute_named` fires for a bound chart); the chart is
  an aggregating cross join (a SIGINT during a streaming non-aggregating
  statement is not honoured for >20 s — queued). Each trial: exit 130, empty
  stdout, stderr ends `Dashboard run interrupted.`, no traceback, page and
  `dashboards/` bytes+mtime untouched, no svg, no `.dashboards-*.tmp`.
  Measured exit after SIGINT ≈0.05–0.07 s unloaded (both duckdb versions),
  ≤0.19 s under load. **Controller ruling (amended in review):** task-named
  mutation 1 (`QuerySession.close` skips `interrupt_quietly`) is masked on
  this path by the `interrupt_quietly` in `execute_statement` and
  `QuerySession.run`; it is pinned in-process by
  `tests/query/test_command.py` (`test_close_after_an_interrupted_statement_
  interrupts_first_and_is_idempotent`, `test_session_context_manager_closes_
  once_on_exit`). The real-process substitute — all three calls removed —
  hangs intermittently (7/16 on 1.5.6, 2/6 on 1.2.0), hence 14 trials; it
  reds (1.5.6 at trials 0/2/9, 1.2.0 at trial 3).
- **6.2 (2 review rounds):** `_run_index_pass` returns `IndexReport | None`;
  `_run_dashboard_pass(data_root, index_report)` is called right after it at 4
  sites (sync SOURCE, `_run_drain_passes` = drain + `pull --sync`, regen,
  load). Silent when `has_dashboards` is false (checked first, inside the
  `try`); runs `Action.REFRESH` over every page only for REFRESHED,
  UNCHANGED, BUILT (exhaustive partition test over `set(Outcome)`); otherwise
  one line `Dashboards: not refreshed; <fixed reason per Outcome.value>.`
  (`report.detail` is not repeated — the index line printed it). Catches
  `Exception` only (one whitespace-collapsed line, exit code unchanged);
  `KeyboardInterrupt`/`SystemExit` propagate with identity. Chained text via
  `render_text(chained=True)` printed with the default newline. All the
  pass's Consoles use `emoji=False` (`:a:` in a key printed as 🅰 before).
  13.3 pinned by an absent `index-cache` before and after refusing runs. The
  post_pass harness is inline (not importable), so `test_pass.py` duplicates
  its five arg lists. "Untouched" checks exclude `dashboards/AGENTS.md`
  (sync, drain, pull --sync, regen write it themselves; load does not).
- **7.2 (2 review rounds):** `docs/dashboards.md` with the live
  `<!-- dashboard-kinds:start/end -->` block = start marker, newline,
  `kinds_markdown(describe_kinds())`, end marker (byte-exact; regenerate with
  `uv run python -m tests.dashboards.test_docs_dashboards`). Registered via a
  `docs/index.md` row + `_REQUIRED_ENTRY_POINT_LINKS`; no `[project.urls]`
  entry yet (7.3 adds it with the skill link). The whole page is scanned with
  `scan_page` and must yield no directive/region/problem — never quote the
  opener inline, even in backticks. Corrected in review to the landed
  behaviour: Not-rendered note only when a valid chart's query/draw/write
  fails under refresh or the pass (directive/region problems → untouched;
  failing freeze → nothing); TIMESTAMPTZ → `sql_failed` with a cast hint
  (other unsupported types → `column_type` naming column and type); problem
  fields conditional (page/chart/line may be null); `option` names the
  directive key, `accepted` (when non-empty) → text ` Accepted: …`;
  `, <n> checked` whenever charts were only checked.
- **6.4 (3 review rounds; the round-3 close-out was verified by the
  controller's own mutation run — a downgrade from a 4th review):**
  `WRITING_ENTRY_POINTS` gains `dashboard` (refresh = first freeze: page,
  `load.svg`, `peak.svg`, `peak.snapshot-1.json`), `dashboard-freeze`
  (`freeze board:peak` after a refresh whose frozen SQL was swapped so the
  re-freeze rewrites the image; page, `peak.svg`, `peak.snapshot-2.json`) and
  `sync-with-dashboards`. Preconditions: each predicate is False over a page
  whose only directive is invalid (`dashboard-freeze` uses the page target
  `freeze board`, since `board:peak` would stop at target resolution).
  **Task-text correction:** task-named mutation 2 (drop the image check) is
  killed by the synthetic predicate test, not the precondition case (`pull`
  precedent). **Controller ruling R2:** `dashboard`/`dashboard-freeze` stay in
  `_EXTERNAL_INDEX_ENTRY_IDS` because the query sandbox legitimately creates
  `query-spill-<pid>` under the index location; they are held tighter by
  `_assert_index_directory_unchanged_but_for_spill`, which exempts only real
  `query-spill-\d+` directories (reusing `_query_spill_exemptions`) — a stray
  file, `query-spill-evil.tmp` or a `query-spill-1` file all go red. Stale
  counts fixed in `tests/test_confinement.py` and
  `tests/test_declaration_refresh.py` (five declarations, three assets dirs).
- **8.4 (4 review rounds; the final prose-only edit — the reviewer's exact
  "known limits" text — applied by the controller):**
  `tests/dashboards/test_boundary.py` encodes the LANDED graph: strict
  lower-rank intra-package imports (`problems → grammar → directive →
  snapshot → region → source → storage → kinds → engine → report →
  binding`), `engine` never imports `binding`, the `__init__` marker imports
  nothing and is imported by nothing; per-module allowlists — `yaml` only in
  directive, `fitdocs.query` only in binding, `kit.format` only in region,
  `fitdocs.units` in binding AND engine (R11), `layout`/`contract` allowed in
  storage and engine per design (only storage uses them today); forbidden
  roots (duckdb, index, time, network, other render, …) pinned literally;
  dynamic imports forbidden outright (`importlib`, `builtins`, `pkgutil`,
  `runpy`, `zipimport`, `__import__`, `import_module`, `__builtins__`, bare
  `exec`/`eval`/`compile`); `.today` legal only on `request`/`stored`/
  `snapshot` and an import alias may not borrow those names; only
  `fitdocs.cli` imports the package (function-level imports scanned). Known
  static-scan limits are documented as illustrative (`code` and similar
  source-running modules, `operator.attrgetter("today")`, local rebinding).
- **8.1 (3 review rounds; the round-3 one-sentence close-out — the
  reviewer's code-verified text — was confirmed by the controller's own
  pin mutation rather than a 4th review):** the wiki-contract Amendment 5
  record did not exist, so 8.1 wrote it whole (criteria 2.17, 3.11, design
  paragraph, spec.json entry, 2026-10-13); dashboards design § Declaration
  amended to the shipped wording ("a", "after a successful index refresh",
  `...`). New contract section "Dashboard Pages: Athlete Pages with fitdocs
  Regions"; index sentence carries the named exception ("…except the chart
  regions and chart assets of dashboard pages under `dashboards/`; workout,
  history and block documents never read it"), guarded sentence-by-sentence
  by `test_every_never_read_back_sentence_carries_the_named_exception`.
  Corrected to the code in review: pages hold "at most a few" user regions
  (none on history/planned pages); the Not-rendered note only when a valid
  chart's query or drawing fails or its first frozen result cannot be
  stored (write failures leave the region as it was; a failing freeze writes
  nothing); a frozen chart with no snapshot runs its SQL once; deletions are
  marked images and the `assets/<page>/` folders cleanup emptied; snapshots
  are created atomically and never replace a file; `load` and the
  `dashboard` command do not write `dashboards/AGENTS.md`; the pass is
  silent only when `dashboards/` holds no markdown file besides `AGENTS.md`.
  Safety-relevant sentences are phrase-pinned (bullet-scoped) in
  `test_safety_relevant_dashboard_sentences_are_pinned`.
- **7.1 (4 review rounds; the reviewer's closed final list of three test
  pins was applied and mutation-verified by the controller, a downgrade from
  a 5th review):** packaged skill `fitdocs-dashboards` (fourth in
  `PACKAGED_SKILLS`, wheel policy, analytics-skill pointer, README /
  wiki-integration / releasing "five tracked places"). Every sentence was
  probed against the code: Not-rendered note only when a never-rendered
  chart's query or drawing fails or its first frozen result cannot be stored,
  under a refresh (command or the pass after sync, pull --sync, regen, load);
  directive/region problems never edited; image/page write failure → no
  region; failing freeze → no note. JSON report shape: `location_problems`,
  `index{state,problem}`, `pages[].problems/notices/charts[]`; page/chart/line
  null where they do not apply; an unclosed or id-less directive is a chart
  entry with `id` null. `CAST($today - INTERVAL 12 WEEK AS DATE)`. Each kind
  has its own size limit (rows, bins, panels, cells or weeks). Guards on skill
  prose: no kinds/channels/options listing (table check over fences too; a
  kind code span with "channel"/"option", ≥3 code spans, or ≥2 commas after
  it), cadence "not steps per minute", section-scoped phrase pins for each
  corrected sentence. The skill does not link `docs/dashboards.md` yet: a
  packaged-skill docs link needs a `[project.urls]` entry (8.2 adds it; 7.3
  adds the link).
- **8.3 (3 review rounds; the final one-sentence prose fix — the reviewer's
  verified wording — applied by the controller):** `tests/dashboards/test_e2e.py`
  runs the real CLI on `copy_dashboard_root` copies: `sync` renders the
  relative bar and the frozen scatter; a second `sync` prints no `Dashboards:`
  line and changes no byte or mtime under `dashboards/`; `regen` and
  `index --rebuild` leave the snapshot byte-identical; with the index dir
  renamed aside, `dashboard refresh` exits 1 (`index.state == "not_built"`),
  the relative chart gets `index_unavailable` and stays byte-identical, the
  frozen chart re-renders. Req 1.7 is pinned by comparing a root holding a
  dated `type: workout` dashboard page against a copy without `dashboards/`
  (history and plan stdout plus the whole tree outside `dashboards/`).
  Goldens (`relative`, `frozen`, `stat`, `rows`, `note`) and images are
  compared as raw bytes; regenerate only via
  `uv run python -m tests.dashboards.test_e2e`. `test_determinism.py` runs
  three children (UTC/C/seed 0, America/Los_Angeles/C.UTF-8/seed 1,
  Pacific/Auckland/C/seed 1) with `cwd` = repo root, asserts the probes
  (UTC offset, hash) really differ, then compares SHA-256 of every file.
  Task-text corrections: the second sync prints nothing; the JSON chart key
  is `id`.
- **8.2 (2 review rounds; the reviewer's non-blocking wording nit — "run the
  dashboard pass" for "run the same pass" — applied by the controller in a
  resumed session, pins re-run green):** tech.md states the dashboards
  exception to "the index is never read back into a document" and the shared
  query sandbox; structure.md gains the dashboards package bullet with the
  design's `layout`/`contract` rule (in `dashboards.storage` and
  `dashboards.engine`) and the query bullet's new importer; the CHANGELOG
  Unreleased Added bullet names the four forms truthfully (`check`/`refresh`/
  `freeze` run SQL, `kinds` lists kinds), the exact pass callers (`sync` with
  or without a source, `pull --sync`, `regen`, `load`), CONTRACT_VERSION 10
  with its action, and the `[plans] path` refusal (exit 2); analytics-index
  Req 5.6 carries Amendment 1. Controller ruling (a): 8.2 adds `Dashboards` to
  `[project.urls]` after `Analytics` (test_packaging requires a URL for every
  linked docs page); 7.3 adds only the skill link. Pins:
  `tests/dashboards/test_published.py`.
