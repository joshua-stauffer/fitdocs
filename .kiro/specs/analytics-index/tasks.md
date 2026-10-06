# Implementation Plan

## Upstream Prerequisites

- **No upstream spec is in flight.** `main` at or after `ef7660e` carries
  everything this plan reads:
  - the Phase 8 composition (`fitdocs.compose`, `compose_listed`);
  - `activity-identity`'s roles and `sources` ordering;
  - the load payload v2 (`load/render.py:63`, `:162`);
  - the effort-tag and quality-flag vocabularies;
  - `DOC_VERSION` 9 and `CONTRACT_VERSION` "8".

  A task that finds one of those shapes different from design.md stops and
  reports rather than adapting silently.
- **Downstream siblings** are `analytics-query` and `analytics-derived`. Their
  specs are written on top of this one, and both are implemented **after**
  this plan merges. They consume the seams in design.md § "Cross-spec seams"
  exactly as stated. A task here that needs to change one of those seams stops
  and reports, because a seam change is a revalidation trigger for both
  siblings.

**Hard rules for every task**

- **Only `src/fitdocs/index/store.py` imports `duckdb`**, lazily, inside its
  connect function, and under `TYPE_CHECKING`. From task 4.1 on, a guard
  enforces it. No other module, test helper included, imports `duckdb`: tests
  reach DuckDB through the store's facade.
- **No test, probe or fixture executes `INSTALL`, `LOAD` or `ATTACH`, calls
  `start_ui`, or names an `http(s)` URL in SQL**, except the store test's
  refused `read_csv('https://…')`. That test runs only on a store connection,
  with HOME pointed at a nonexistent path (design.md, Testing Strategy).
  Ad-hoc DuckDB exploration happens only in a throwaway venv under the session
  scratchpad, never in the worktree's `.venv`.
- **No test reads or writes the real user's HOME, cache or config.** Task 1.2's
  autouse fixture lands before any code that resolves the index location. A
  test that needs its own location sets `FITDOCS_INDEX_DIR` inside its
  `tmp_path`.
- **Absent is `None`, then `NULL`.** No task writes `0`, a default, NaN or an
  infinity for a value nothing recorded or nothing could compute.
- **No fixture holds personal data.** Every `.fit` input is synthesized through
  `tests/fixtures/builder.py`, `tests/fixtures/identity.py` or
  `tests/fixtures/merge.py`. No task reads the real data root; task 8.5 is the
  maintainer's alone.
- **No document byte changes.**
  - The rendering goldens (`tests/render/golden_docs/`), `DOC_VERSION` and
    `MANAGED_KEYS` stay untouched.
  - A task whose change alters a rendered page stops and reports.
  - `CONTRACT_VERSION` advances once (task 8.1), by one from the value on the
    branch when the task runs. After the final rebase, the implementer checks
    it equals `main`'s value plus one, and re-pins if a sibling landed a bump
    first.
  - `SCHEMA_VERSION` is introduced at `1`. This plan is the first Phase 10
    lander.
- **Mutations run through `uv run pytest` only** (`change-protocol.md`,
  § Fixture Discrimination).
  - Each named mutation is applied, observed red, reverted, observed green, and
    recorded in the task's Implementation Notes.
  - Revert by restoring a `cp` of the file taken before the mutation, never
    with `git checkout -- <path>`, `git stash` or `git reset --hard`.
  - A task that cannot make a listed mutation red stops and reports it as
    UNPINNED, rather than weakening the assertion's wording.
- **Shell safety.** Never `rm -rf`, `git init`, `git reset --hard` or
  `git checkout -- <path>`. Never chain a destructive command after `cd`.
- **Types.** Every task that creates a typed source, test or fixture module
  type-checks it clean with `uv run mypy <its paths>`. Task 8.4 registers the
  new test modules in `pyproject.toml`'s curated mypy `files` list, so
  parallel tasks never share `pyproject.toml`.
- **Lint.** Every task's observable includes `uv run ruff check <files it
  changed>` and `uv run ruff format --check <files it changed>`, both clean.
- **Stop and report** when a task finds it needs any of: a runtime dependency
  other than `duckdb`, a frontmatter key, a document change, an owned path
  inside the data root, a new write location, or a change to a seam in
  design.md § "Cross-spec seams".

## Shared source files

Each file below has more than one writer in this plan. Its writers are
sequential: never two of them `(P)` at once.

- `pyproject.toml`: 1.1 (the dependency) and 8.4 (the mypy `files`).
  `uv.lock`: 1.1 only.
- `tests/conftest.py`: 1.2 only.
- `src/fitdocs/index/__init__.py` and `src/fitdocs/index/core/__init__.py`:
  1.3 only, so the parallel 3.1 and 3.2 never both create `core/__init__.py`.
- `src/fitdocs/index/schema.py` and `src/fitdocs/index/bookkeeping.py`: 2.1
  only. Later tasks import them, and a missing field is a stop-and-report.
- `src/fitdocs/index/producer.py`: 2.2 only.
- `src/fitdocs/index/registry.py`: 3.3 only.
- `src/fitdocs/index/store.py`: 4.1 (policy, facade), 4.2 (classification) and
  4.3 (DDL, insert, transactions, bookkeeping I/O), in that order.
- `tests/index/test_boundary.py`: 4.1 (the duckdb importer and the
  plugin-discovery no-import), then 7.3 (index importers, untouched commands).
- `tests/index/_helpers.py`: 4.2 only (the lock-holding subprocess and the
  storage-version forger, with their self-tests). Later tasks import it and
  never edit it; a missing helper is a stop-and-report.
- `tests/index/conftest.py`: 5.1 (created, with page-building fixtures), then
  6.1 (appends the `core_registry` fixture and the built-index fixture).
- `src/fitdocs/index/refresh.py`: 6.1, then 6.2, then 6.3.
- `src/fitdocs/cli.py`: 7.1 (the `index` command and docstring), then 7.2
  (the post-pass wiring).
- `src/fitdocs/sync.py`: 5.3 only. `src/fitdocs/docio.py`: 5.1 only.
- `src/fitdocs/contract.py`: 2.5 (approved additive recorded-basis reader)
  and 8.1 (publication/version history), sequentially. `tests/test_contract.py`:
  2.5 only; `tests/test_public_api.py`'s literal contract export set also
  belongs to 2.5. Existing load/history/plan behavior stays unchanged.
- `docs/ownership-contract.md`, `tests/declaration_golden/*`, `CHANGELOG.md`
  and `docs/install.md`: 8.1 only.
- `.kiro/steering/tech.md` and `.kiro/steering/structure.md`: 8.2 only.
- Existing tests whose full stdout of `sync`/`regen`/`load` gains the index
  line: 7.2 only, each listed in its Implementation Notes.

## Cross-spec shared files

Each file below is shared with a sibling Phase 10 spec. Writers append an
entry, a row, a field or a block, and never rewrite or reorder a sibling's.
**On rebase, keep both.**

- **`src/fitdocs/cli.py`.** Command registration and the module docstring's
  command count: "Twelve" after this plan, "Thirteen" after `analytics-query`
  adds `query`. With it goes `tests/test_cli_skill.py:262-270`, where the
  count is 12 after this plan. **Append-only. Sibling: analytics-query.**
  Whoever lands second re-pins the count from `main`'s value plus one.
- **The no-network command list.** This is
  `tests/connectors/test_e2e.py:203-207`, the list of commands making no
  connector request in `.kiro/steering/tech.md` (Network and Credentials),
  and connectors Requirement 14.1, through its amendment. This plan appends
  `index`. **Append-only. Sibling: analytics-query, which appends `query`.**
- **The confinement entry list and permitted locations**
  (`tests/test_confinement.py`: `WRITING_ENTRY_POINTS`, `permitted_locations`).
  This plan appends the `index` and `sync-with-index` entries and the
  resolved index directory. **Append-only. Siblings:**
  - `analytics-query` appends one standalone test that `query` writes nothing
    outside its spill directory;
  - `analytics-derived` appends `EntryPoint(id="index-derived", …)`, running
    `fitdocs index` over its derived fixture root.
- **`PACKAGED_SKILLS`**: `src/fitdocs/agentskill.py:44-47`,
  `tests/test_skill_locator.py:57-58` and `tests/test_agent_skill.py:191-199`.
  This plan adds nothing. **Append-only. Sibling: analytics-query, which
  appends its skill.** It is listed so both landers keep the registry order.
- **`src/fitdocs/index/registry.py`**: the three producer tuples. **Append-only,
  core producers first. Sibling: analytics-derived, which appends its four.**
- **`src/fitdocs/index/schema.py`, `SCHEMA_VERSION`, with
  `tests/index/test_schema_version.py` `_DIGESTS_BY_VERSION`.**
  **Append-only map; the version advances by exactly one per lander that
  changes the schema or a producer's row rule (design.md, Seam 2). Sibling:
  analytics-derived, which advances to `main`'s value plus one and appends its
  digest. analytics-query never edits either.**
- **`tests/index/test_schema.py`, the exact registered-table-set pin** (the 13
  names of design.md, Seam 3, after this plan). **Append-only. Sibling:
  analytics-derived, which appends its eleven table names.**
- **`tests/index/test_boundary.py`, `_INDEX_IMPORTERS`.** The set is
  `{"fitdocs.cli"}` after this plan. **Append-only. Sibling: analytics-query,
  which appends its five modules: `fitdocs.query.sandbox`,
  `fitdocs.query.statement`, `fitdocs.query.freshness`,
  `fitdocs.query.schemaview` and `fitdocs.query.command`.** analytics-derived
  appends nothing: its producers live inside `fitdocs.index`. The
  duckdb-importer set stays exactly `{store}`. No sibling adds to it: query
  goes through the facade.
- **`src/fitdocs/index/store.py`, the connection facade.** **Append-only for
  `analytics-query`**, which adds the facade method it needs
  (`statement_types`). Never change `MANDATORY_SETTINGS`, the writer
  settings or the exception mapping, and never remove a method.
- **`tests/conftest.py`, the index-isolation fixture.** Owned by this plan.
  **Neither sibling edits it**: analytics-query isolates HOME in
  `tests/query/conftest.py`, and analytics-derived uses the fixture as is.
- **`CHANGELOG.md` `[Unreleased]`.** Append under an existing category
  heading; create it only if absent. **Siblings: both.**
- **`docs/ownership-contract.md`, the analytics-index section.** Owned by this
  plan. **Neither sibling edits it**: this plan's section already names
  `query-spill-<pid>/` (task 8.1), and analytics-derived adds no write
  location.
- **`pyproject.toml`'s mypy `files` list.** **Append-only. Siblings: both.**
- **`.kiro/steering/structure.md`**, the dependency-direction sentence for
  `index`. **analytics-query appends its package's line; analytics-derived
  appends its derived-producers clause to the `index` sentence.**
- **`.kiro/steering/roadmap.md`**, the Phase 10 Existing Spec Updates and Specs
  ticks. The connectors line is ticked only when both its parts land: this
  plan annotates it "(analytics-index part landed)".
- **`.kiro/specs/connectors/requirements.md`**, the amendment adding `index` to
  Requirement 14.1. analytics-query starts after this plan merges, so it
  records its own amendment, numbered the next free at its landing.

## Test File Ownership

- `tests/test_determinism.py:666-715`, `tests/test_packaging.py:503-519` and
  `:1036-1090`, `tests/test_preserved_guarantees.py:93-108`, and
  `tests/sitebuild/test_repo_wiring.py:18-24, 64-72`: **1.1**.
- `tests/conftest.py`, `tests/index/__init__.py` and
  `tests/index/test_isolation.py`: **1.2**.
- `tests/index/test_location.py`: **1.3**.
- `tests/index/test_schema.py` (synthetic specs section): **2.1**.
- `tests/index/test_producer.py`: **2.2**.
- `tests/index/test_fingerprint.py`: **2.3**.
- `tests/index/test_lock.py`: **2.4**.
- `tests/index/test_core_documents.py`: **3.1**.
- `tests/index/test_core_computed.py`: **3.2**.
- `tests/index/test_schema.py` (registered-tables section) and
  `tests/index/test_schema_version.py`: **3.3**.
- `tests/index/test_store.py`: **4.1** (policy section), **4.2**
  (classification section) and **4.3** (DDL, insert, transaction sections).
  Each adds its own headed section.
- `tests/index/_helpers.py` and `tests/index/test_helpers.py`: **4.2**.
- `tests/index/test_boundary.py`: **4.1**, then **7.3**.
- `tests/index/conftest.py` and `tests/index/test_corpus.py`: **5.1**
  (6.1 appends `core_registry` and the built-index fixture to the conftest).
- `tests/index/test_derive.py`: **5.2**.
- `tests/test_sync_handoff.py`: **5.3**.
- `tests/index/test_handoff.py`: **5.4**.
- `tests/index/test_refresh.py`: **6.1** (pages section) and **6.2** (corpus,
  meta and progress section).
- `tests/index/test_post_pass.py`: **6.3**.
- `tests/index/test_build.py`: **6.4**.
- `tests/index/test_interruption.py` and `tests/index/test_determinism.py`:
  **6.5**.
- `tests/index/test_cli_index.py` and `tests/test_cli_skill.py:262-270`:
  **7.1**.
- `tests/index/test_cli_post_pass.py`, and the pre-existing full-stdout pins:
  **7.2**.
- `tests/test_confinement.py`, `tests/connectors/test_e2e.py:203-244` and
  `tests/test_inbox_e2e.py:100-175`: **7.3**.
- `tests/test_ownership_contract.py`, the phrase pins in
  `tests/identity/test_contract_docs.py:155-165`, the new
  `tests/index/test_contract_docs.py` and `tests/declaration_golden/*`
  (regenerated): **8.1**.

---

- [x] 1. Foundation: the dependency, test isolation and the index location

- [x] 1.1 Add DuckDB as a core runtime dependency and reword the four dependency pins
  - **Dependency and lock.** Append `duckdb>=1.2,<2` to `[project].dependencies`
    and regenerate `uv.lock` with `uv lock`. No `[project.optional-dependencies]`
    appears. The floor is 1.2, not the brief's 1.1: every 1.1.x release writes
    into HOME on `INSTALL` under the locked configuration (design.md, Security
    Considerations).
  - **Reword `tests/test_determinism.py:666-715`; do not delete it.**
    - The baseline set becomes the five plus `"duckdb>=1.2,<2"`.
    - The docstring states that analytics-index added `duckdb` for the index,
      that plugin discovery adds no dependency, and that discovery never loads
      `duckdb`. The last is pinned by 4.1's subprocess check.
    - The `optional-dependencies == {}` assertion stays.
  - **Reword `tests/test_packaging.py:503-519`.** The exact ordered list gains
    `"duckdb>=1.2,<2"` last. The scratch-venv docstring at `:1036-1090` says
    "six".
  - **Reword `tests/test_preserved_guarantees.py:93-108`.** It asserts `head ==
    list(pre_distribution.DEPENDENCIES) + ["duckdb>=1.2,<2"]` and names
    analytics-index as the deliberate delta. The vendored snapshot
    `tests/fixtures/pre_distribution_e74af37.py` is not edited (its own
    rule, lines 19-23).
  - **Reword `tests/sitebuild/test_repo_wiring.py:18-24, 64-72`** (docs-site
    Req 8.1). `test_runtime_dependencies_are_the_pre_spec_literals` asserts
    `PRE_SPEC_DEPENDENCIES + ["duckdb>=1.2,<2"]`, and keeps `PRE_SPEC_DEPENDENCIES`
    itself as the five literals. Its docstring names analytics-index as the
    deliberate delta, and keeps a `Dies on:` line (the module's own
    `_DIES_ON` rule requires one) that names adding any other entry.
  - **Offline install.** The packaging tests that install `--offline` still
    pass. Warm the uv cache with the duckdb wheel the way those tests already
    warm it, and run them in CI mode locally (`CI=true uv run pytest
    tests/test_packaging.py tests/test_preserved_guarantees.py`). Record any
    CI-runner-only step this needs in Implementation Notes.
  - **Mutations.**
    - Remove `duckdb` from `pyproject.toml`: the determinism, packaging,
      preserved-guarantees and docs-site repo-wiring pins each red.
    - Write the superseded floor, `duckdb>=1.1,<2`, in `pyproject.toml`: the
      same four pins each red on the literal.
    - Add an `[project.optional-dependencies]` table: the optional-dependency
      assertions red.
  - **Observable:** `uv sync` installs `duckdb` 1.5.x. The four pin modules
    the packaging suite and `tests/sitebuild/` are green, plain and in CI
    mode. `uv.lock` lists `duckdb`. `git diff --stat` touches only
    `pyproject.toml`, `uv.lock` and the four test files.
  - _Requirements: 12.3_

- [x] 1.2 Isolate every test from the real index location
  - **The fixture.** Add an autouse fixture to `tests/conftest.py` that sets
    `FITDOCS_INDEX_DIR` to a fresh directory from `tmp_path_factory` for every
    test, using `monkeypatch`, so it is restored afterwards.
  - **Its pins** go in a new `tests/index/test_isolation.py`. This task
    creates `tests/index/__init__.py`, because every test subdirectory here is
    a package:
    - inside a test, `os.environ["FITDOCS_INDEX_DIR"]` is absolute;
    - it is not under `Path.home()`;
    - it differs between two tests: write a marker in one, and assert it is
      absent in the other.
  - **Mutations:**
    - Drop `autouse=True`: the absolute and not-under-HOME pins red.
    - Return a session-scoped directory: the per-test pin reds.
  - **Observable:** `uv run pytest tests/index/test_isolation.py` is green,
    and the full suite stays green. No production code changes.
  - _Requirements: 14.6_

- [x] 1.3 Create the index package and resolve the index location
  - **The package.** Create `fitdocs.index` as a marker package. Its docstring
    says the index is a disposable projection and that the package never
    imports `duckdb` at import time. Also create the empty
    `fitdocs.index.core` subpackage marker, so the parallel 3.1 and 3.2 only
    add modules to it.
  - **The location module**, exactly as design.md § Location states:
    - **Resolution:** `FITDOCS_INDEX_DIR` when non-empty and absolute, refused
      when relative; then `XDG_CACHE_HOME/fitdocs/index` when absolute, a
      relative value skipped; then `~/.cache/fitdocs/index`.
    - **The per-data-root key:** a slug plus 16 hex characters of the SHA-256
      of the resolved path.
    - **`IndexLocation`'s file names.**
    - **The refusal:** an `IndexLocationError` subclassing `SettingsError`,
      for a directory equal to or inside the resolved data root.
    - **`ensure_directory`:** mode `0o700` for directories it creates; existing
      directories are never re-moded.
  - **Tests**, mirroring `tests/connectors/test_credentials.py:115-260`:
    - all six env combinations;
    - empty-string handling;
    - a relative `FITDOCS_INDEX_DIR` raises, naming the variable and value;
    - refusal when equal, inside, or inside through a symlink, with the message
      naming both resolved paths (as
      `tests/connectors/test_credentials.py:214` does);
    - a sibling with a shared prefix is accepted;
    - one key for a relative spelling and a symlinked spelling of one root,
      and different keys for two roots;
    - created directories have mode `0o700`, and an existing directory's mode
      is unchanged;
    - every `IndexLocation` path is inside `directory`.
  - **Mutations:**
    - swap the XDG and home steps;
    - drop `.resolve()` in the key;
    - make the refusal an equality test (the inside-root case reds);
    - drop the `mode` argument;
    - accept a relative `FITDOCS_INDEX_DIR`.
  - **Observable:** `uv run pytest tests/index/test_location.py` is green, and
    mypy is clean on the package and its tests. Nothing imports `fitdocs.index`
    yet.
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.6_

- [x] 2. The schema contract and the producer seam

- [x] 2.1 Define the schema contract and the bookkeeping tables
  - **The schema module**, per design.md § Schema:
    - `SCHEMA_VERSION = 1`;
    - the `ColumnType` enum: no zone-aware timestamp type;
    - `ColumnSpec`, `TableSpec`, `TableScope`, `ResolvedTable`;
    - `PAGE_KEY_COLUMN`, with its description;
    - the reserved `index_` prefix;
    - `UNIT_SUFFIXES`, longest first, exactly as design.md § Data Models
      tabulates them;
    - `resolve_tables`, which raises `SchemaError` on every rule listed there;
    - `schema_manifest` and `schema_digest`.
  - **The bookkeeping module:**
    - `ComputedState`, `IndexMeta`, `PageState` and `Bookkeeping`;
    - the three bookkeeping `TableSpec`s (`index_meta`, `index_pages`,
      `index_producers`), with the columns and descriptions of design.md
      § Data Models.
  - **Tests, on synthetic specs only.** Registered tables come in 3.3. For each
    `resolve_tables` rule there is a failing spec:
    - a duplicate table;
    - a non-snake name;
    - the reserved prefix on a producer table;
    - a declared `page_key`;
    - an empty description;
    - `_bpm` without "beats per minute";
    - `_s_per_km` matched before `_km` and `_s`;
    - a `TIMESTAMP` column without `_utc` or `_local`.

    Also:
    - `page_key` is prepended for document and computed scopes only;
    - the manifest excludes descriptions, so a description change leaves the
      digest equal;
    - a column type change moves the digest.
  - **Mutations:**
    - delete each validation branch in turn (each rule's test reds);
    - match suffixes shortest-first (the `_s_per_km` test reds);
    - include descriptions in the manifest.
  - **Observable:** `uv run pytest tests/index/test_schema.py` is green, mypy
    is clean, and both modules import no other `fitdocs.index` module except
    each other.
  - _Requirements: 3.7, 4.2, 4.3, 4.4, 4.6, 13.5, 13.6_

- [x] 2.2 Define the producer seam
  - **The producer module**, per design.md § ProducerSeam:
    - `SqlValue`, `Row`, `Rows`, `LoadStatus`, `LoadRegionReading`. The
      name differs from `fitdocs.contract.LoadReading` (the frontmatter load
      reading, `contract.py:1150`) so the two never clash in one module;
    - `PageDocument`, `PageComputed`, `CorpusPage`, `CorpusLeftOut` and
      `CorpusSnapshot` (`data_root`, `pages`, `left_out`, `today`,
      `athlete_fingerprint`, in that order);
    - the `DocumentProducer`, `ComputedProducer` and `CorpusProducer` protocols.

    The module docstring states every producer obligation:
    - no writes, network, clock or `duckdb`;
    - deterministic;
    - naive datetimes;
    - every declared table keyed, possibly empty;
    - per-page rows exclude `page_key`;
    - corpus fingerprints cover every input read, `today` included when used,
      and a producer reading the workout pages fingerprints the snapshot's
      `pages` and `left_out` rather than globbing `workouts/`;
    - a snapshot is built only by `corpus.corpus_snapshot` (task 5.1);
    - an exception, from `rows` or `fingerprint`, rolls back or skips that
      unit and is retried.
  - **Typing tests.** A test module defines one minimal frozen-dataclass
    producer per protocol, passes each where the protocol is expected, and
    `uv run mypy` accepts them. A deliberately wrong one, with `rows` taking
    the wrong input type, is rejected: the test runs mypy on a snippet through
    the API that existing typing tests use, or records the reject in
    Implementation Notes if no such pattern exists.
  - **Dataclass test.** `dataclasses.fields` of each input type (`PageDocument`,
    `PageComputed`, `CorpusPage`, `CorpusLeftOut`, `CorpusSnapshot`) equals the
    design's field list, in order, including `CorpusSnapshot.left_out` and
    `CorpusLeftOut`'s `path` and `document_fingerprint`. This is a seam pin
    for the siblings.
  - **Mutations:**
    - drop `today` from `CorpusSnapshot`;
    - drop `left_out` from `CorpusSnapshot`;
    - reorder `PageComputed` fields.

    The field-list pins red.
  - **Observable:** the tests are green, mypy is clean, and the module imports
    only `fitdocs.model`, `fitdocs.metrics.types`, `fitdocs.compose.types`,
    `fitdocs.load.render` and `fitdocs.index.schema`.
  - _Requirements: 13.1, 13.2, 13.3_

- [x] 2.3 (P) Define the document, render, athlete and corpus fingerprints
  - **The fingerprint module**, per design.md § Fingerprint. The render
    fingerprint excises the `notes`, `workout` and `load` region contents
    using `fitdocs.docmerge`'s grammar, keeping the markers. It keeps managed
    frontmatter minus `LOAD_KEYS`.
  - **`combined_corpus_fingerprint(producer, snapshot)`**, the one composition
    of a corpus producer's stored fingerprint:
    `corpus_fingerprint(producer.fingerprint(snapshot),
    fitdocs_version=version.tool_version(), schema_version=SCHEMA_VERSION)`.
    It calls `fitdocs.version.tool_version` through the module attribute at
    call time, and lets an exception from `producer.fingerprint` propagate
    unchanged.
  - **Tests**, starting from a real page made by the existing fixture builders.
    Each fixture edit is verified to change the page bytes before the
    fingerprint is asserted.
    - The document fingerprint moves on a one-byte edit and on a rename.
    - The render fingerprint stays equal under:
      - an effort-key edit;
      - each load key;
      - load-region content;
      - `notes` content;
      - `workout` content;
      - a rename;
      - an unmanaged key.
    - The render fingerprint moves under:
      - `title`;
      - a body line outside the regions;
      - `sources`;
      - `doc_version`.
    - The athlete fingerprint is equal for equal inputs, moves on one changed
      divider and on `ftp_watts`, is stable and representable for NaN, and
      `None` differs from all-`None` inputs.
    - Two athlete inputs differing only in the twelfth significant digit of
      `ftp_watts` give different fingerprints.
    - The corpus fingerprint moves on each of its three arguments.
    - `combined_corpus_fingerprint`, with a minimal test corpus producer and a
      snapshot built by hand in the test (the builder arrives in 5.1):
      - it equals `corpus_fingerprint(<the producer's fingerprint>,
        fitdocs_version=tool_version(), schema_version=SCHEMA_VERSION)`;
      - it moves when `fitdocs.version.tool_version` is monkeypatched to
        another version, and when the producer's fingerprint changes;
      - a producer whose `fingerprint` raises makes it raise the same
        exception object.
  - **Mutations:**
    - include `LOAD_KEYS` in managed;
    - stop excising the `notes` region (and, separately, the `load` region);
    - drop `path` from the document fingerprint;
    - render floats rounded to six significant digits (the twelfth-digit test
      reds);
    - drop `schema_version` from the corpus fingerprint;
    - bind `tool_version` with `from fitdocs.version import tool_version` (the
      monkeypatched-version test reds);
    - catch the producer's exception and return a constant (the propagation
      test reds).
  - **Observable:** `uv run pytest tests/index/test_fingerprint.py` is green
    and mypy is clean. The module imports only `fitdocs.contract`,
    `fitdocs.docmerge`, `fitdocs.metrics.types`, `fitdocs.version`,
    `fitdocs.index.producer`, `fitdocs.index.schema` and stdlib.
  - _Requirements: 5.1, 5.2, 5.5, 7.3, 13.3_
  - _Boundary: Fingerprint_
  - _Depends: 2.1, 2.2_

- [x] 2.4 (P) Guarantee one fitdocs writer with an OS advisory lock
  - **The lock module**, per design.md § Lock: `writer_lock(path)` uses a
    non-blocking `fcntl.flock`, with `msvcrt.locking` where `fcntl` is absent.
    `WriterBusy` is raised on contention. The file is opened `O_RDWR|O_CREAT`
    with mode `0o600` and never written.
  - **Tests:**
    - a subprocess holding the lock makes acquisition raise `WriterBusy`;
    - after the subprocess is killed (`SIGKILL`), acquisition succeeds while
      the file still exists;
    - acquiring an existing lock file leaves its mtime and size unchanged;
    - the lock is released on exit from the `with` block, including on an
      exception.
  - **Mutations:**
    - drop `LOCK_NB` (the busy test hangs; guard it with a subprocess timeout
      so it reds instead);
    - truncate the file on open (the mtime test reds);
    - release before the body runs.
  - **Observable:** `uv run pytest tests/index/test_lock.py` is green, mypy is
    clean, and no test leaves a process behind.
  - _Requirements: 11.1, 11.2, 11.3_
  - _Boundary: Lock_

- [x] 2.5 Add the approved recorded-load-basis reader prerequisite
  - Add `contract.document_load_basis(frontmatter: Mapping[str, object] | None) -> str | None`
    and export it in `contract.__all__`. Read the third `LOAD_KEYS` entry.
  - Return `None` for absent frontmatter, a missing key, non-string values,
    or strings empty after stripping whitespace. Return a valid recorded
    string verbatim, preserving whitespace and arbitrary nonblank labels.
  - Read basis independently of load value/methodology validity. Preserve
    `LoadReading`, `document_load`, history/plan behavior and document bytes.
  - Tests in `tests/test_contract.py` pin every input shape, verbatim string
    preservation, independence from other load keys and the public export.
    Append the approved reader to `tests/test_public_api.py`'s literal
    `_CONTRACT_SURFACE`; keep the exact public-export assertion intact.
    Mutate the key, type/blank guards, normalization, load-validity gating and
    export; each named assertion must fail and pass after restoration.
  - Observable: contract tests, history document tests and plan corpus tests
    pass; scoped mypy/Ruff and canonical regression pass.
  - _Requirements: 2.1; plan-resolution Amendment 1_
  - _Boundary: ContractReaders (approved additive prerequisite)_

- [x] 3. Core producers

- [x] 3.1 (P) Project document values: pages, sources, loads and quality flags
  - **The core documents producer**, per design.md § CoreDocuments and § Data
    Models: tables `pages`, `page_sources`, `loads` and `quality_flags`, with
    every column and description. Values come only through the contract
    readers and `PageDocument.load`.
  - **Tests**, on `PageDocument`s built from fixture pages. Each
    `LoadRegionReading` is constructed directly with the status under test.
    Mapping region states to statuses is 5.1's, not this producer's. Load
    payloads are produced by the real load pass on synthetic activities, or
    encoded with `load/render.py`'s encoder, with pairwise-distinct values
    throughout.
    - A computed payload gives one selected row plus one row per non-selected
      entry, and a non-selected `None` stays `None`.
    - Each status, `unsupported`, `not_computed` and `unreadable`, is written
      as itself to `pages.load_status`, with no `loads` or `quality_flags`
      rows.
    - A valid effort tag gives exact values.
    - An invalid tag gives `effort_invalid` True and every effort column
      `None`.
    - No tag gives `effort_invalid` False and the effort columns `None`.
    - `indoor` is `None` when the key is absent and True when present.
    - `uuid` is `None` when absent.
    - `page_sources` positions and roles are correct, with base last.
    - A non-archive ref gives `sha256` `None`.
    - No row holds `notes` or `workout` region text. This is asserted with a
      distinctive marker string in those regions, absent from every row.
  - **Mutations:**
    - swap `selected` on the basis row;
    - map a non-selected `None` to `0.0`;
    - emit `loads` rows for an unsupported payload;
    - write `not_computed` as `unreadable`;
    - drop the invalid-tag branch;
    - set the base role on the first source.
  - `core/documents.py` imports `fitdocs.index.producer.LoadRegionReading` and
    reads the frontmatter load through `fitdocs.contract.document_load`. The
    two types have different names, so no alias is needed.
  - **Observable:** `uv run pytest tests/index/test_core_documents.py` is
    green, and mypy is clean. Rows match the declared column counts, which
    `resolve_tables` accepts.
  - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 4.1_
  - _Boundary: CoreDocuments_
  - _Depends: 2.1, 2.2, 2.5_

- [x] 3.2 (P) Project computed values: activities, records, laps, sets, zone times and channel sources
  - **The core computed producer**, per design.md § CoreComputed and § Data
    Models, covering six tables.
    - The `activities` metric columns are generated from `DerivedMetrics`'
      scalar fields in declared order, and the `records` channel columns from
      `fields(Samples)` minus `time_s`, so their order cannot drift.
    - Descriptions and units come from a static table in the module, which
      3.3's pins check.
  - **Tests.**
    - **Records**: a composed run from `tests/fixtures/merge.py` gives records
      equal, column by column, to the composed activity's samples, a donated
      dynamics channel included.
    - **Time**: `time_utc` equals start plus `time_s`, with distinct
      fractional `time_s` values. A `None` start gives `None` times.
    - **Strength**: a strength fixture keeps a zero `weight_kg` as 0.
    - **Zones**: bounds come from distinct dividers (zone 1 lower `None`, last
      zone upper `None`), and there are no zone rows when no `ZoneSpec` is
      present.
    - **Provenance**: `channel_sources` roles follow the provenance.
    - **Activities**: `athlete_fingerprint` equals `fingerprint.athlete_fingerprint`
      of the inputs, and metric values equal `compute_metrics` exactly.
  - **Mutations:**
    - off-by-one zone bound index;
    - use the base instead of the composed activity for records;
    - drop the donated-channel column;
    - replace a `None` weight with 0 (with a separate zero-versus-`None`
      fixture);
    - mark every source `base`.
  - **Observable:** `uv run pytest tests/index/test_core_computed.py` is
    green, and mypy is clean.
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 4.1, 4.4_
  - _Boundary: CoreComputed_
  - _Depends: 2.1, 2.2, 2.3_

- [x] 3.3 Register the core producers and pin the schema
  - **The registry module**: `DOCUMENT_PRODUCERS = (CORE_DOCUMENTS,)`,
    `COMPUTED_PRODUCERS = (CORE_COMPUTED,)`, `CORPUS_PRODUCERS = ()` and
    `registered_tables()`.
  - **Pins over the registered tables**, added to `tests/index/test_schema.py`:
    - every table and column has a non-empty description;
    - every unit-suffixed column's description names its unit word;
    - **3.8**: `records` channel columns equal `fields(Samples)` minus `time_s`,
      in order;
    - `activities` metric columns equal `DerivedMetrics`' scalar fields;
    - `laps` matches `fields(Lap)` as renamed in design.md;
    - `strength_sets` matches `fields(StrengthSet)` minus `message_index`;
    - the table set is exactly the 13 names of design.md, Seam 3.
  - **`tests/index/test_schema_version.py`**:
    `_DIGESTS_BY_VERSION = {1: "<digest>"}`, with the digest computed once and
    pasted. It asserts `schema_digest(registered_tables()) ==
    _DIGESTS_BY_VERSION[SCHEMA_VERSION]` and `SCHEMA_VERSION ==
    max(_DIGESTS_BY_VERSION)`. Its docstring states the binding rule of
    design.md, Seam 2, including that the version advances for every change
    to how any producer derives rows from unchanged inputs, because the
    per-page tiers do not recompute on an upgrade, and that such a version's
    digest may equal the previous one (Requirement 13.6).
  - **Mutations:**
    - add a channel to `Samples` in a test-local subclass passed to the pin
      helper, or the generated column list hard-coded minus one field (3.8
      reds);
    - rename one column (the digest reds);
    - bump `SCHEMA_VERSION` to 2 (the `max` pin reds);
    - blank one description.
  - **Observable:** the schema and schema-version tests are green, and
    `registered_tables()` returns 13 tables, bookkeeping first.
  - _Requirements: 3.8, 4.6, 13.1, 13.4, 13.6, 13.7_
  - _Depends: 3.1, 3.2_

- [x] 4. The store: the only DuckDB importer

- [x] 4.1 Open every connection under the fitdocs connection policy
  - **The store's policy and facade**, per design.md § Store:
    - `MANDATORY_SETTINGS` and `WRITER_SETTINGS`;
    - `open_index` and `create_index`, with `ValueError` on a mandatory
      override;
    - `IndexConnection` (`execute`, `interrupt`, `close`, the context manager);
    - `IndexResult` (`columns`, `fetchmany`, `fetchall`);
    - `IndexStatementError` and `IndexInterrupted`, raised by `execute`,
      `IndexResult.fetchmany` and `IndexResult.fetchall` alike, with the
      original DuckDB exception chained (`raise … from exc`), so 4.2 can
      classify a statement failure through `__cause__`:
      `duckdb.InterruptException` becomes `IndexInterrupted`, and every other
      `duckdb.Error` becomes `IndexStatementError`. DuckDB streams execution,
      so errors and interrupts surface at fetch;
    - the writer's `temp_directory`: every writer connection (`create_index`,
      `open_index(read_only=False)`) sets it to `path.parent /
      WRITER_SPILL_DIRNAME` (`"writer-spill"`), per design.md § Store;
    - `duckdb_version()`.

    `import duckdb` appears only inside the private connect function and under
    `TYPE_CHECKING`. Open errors become `IndexOpenError` carrying a fault whose
    kind is `OTHER` for now; 4.2 classifies.
  - **Policy tests**, in the `tests/index/test_store.py` policy section:
    - `current_setting` equals each mandatory value on a created, a read-write
      and a read-only connection;
    - `current_setting('storage_compatibility_version')` is `v1.0.0` on
      writers;
    - `current_setting('temp_directory')` on a created and on a read-write
      connection names `<the database's directory>/writer-spill` (compared
      after resolving both paths), and is not that path on a read-only
      connection;
    - a mandatory override raises before any file is created;
    - `SET enable_external_access=true`, `SET
      autoinstall_known_extensions=true`, `read_csv('/etc/hosts')` and
      `read_csv('https://example.invalid/x.csv')` are each refused with the
      configuration refusal, with `HOME` monkeypatched to a nonexistent path,
      and that path still does not exist afterwards;
    - an `https://` string used as a parameter value round-trips as text;
    - the file header storage version (bytes 12-20) is 64. This is a
      regression check of Requirement 11.4's outcome. It does not
      discriminate on 1.5.6, which writes 64 either way (research.md P6);
    - `interrupt()` on an idle connection is harmless;
    - **fetch errors are wrapped** (analytics-query relies on this):
      - `execute("SELECT now()")`, then `fetchmany(1)`, raises
        `IndexStatementError` whose `__cause__` is set; the test first
        asserts that `pytz` is not importable, so the fetch-time failure is
        real;
      - separately, the same with `fetchall()`, with the same `pytz`
        precondition;
      - `execute("SELECT count(*) FROM range(1000000000000)")`, then
        `fetchmany(1)`, raises `IndexInterrupted` when a timer calls
        `interrupt()` after 0.5 s. It runs in a subprocess with a 60 s
        timeout, so a broken interrupt reds instead of hanging.

    No test executes `INSTALL` or `LOAD`.
  - **The boundary guard**, `tests/index/test_boundary.py`. An AST walk of
    `src/fitdocs` covers `import X`, `from X import`, aliases, and string
    arguments to `importlib.import_module` and `__import__`. Only
    `fitdocs/index/store.py` imports `duckdb`. Positive controls:
    `scanned > 100`, the store is found, and a synthetic `import duckdb` /
    `from duckdb import x` / `importlib.import_module("duckdb")` in a temp
    file is caught.
  - **The store-SQL guard**, the only pin of "fitdocs never issues
    `INSTALL`/`LOAD`" (Requirement 12.1). An AST pass over `store.py` collects
    every string constant that is not a docstring, and asserts two things,
    per design.md § Guards:
    - none contains, case-sensitively, any of `INSTALL `, `LOAD `, `ATTACH`,
      `COPY `, `EXPORT `, `http://`, `https://`, `PRAGMA`;
    - none matches the statement-leading pattern `^\s*SET\b`. This catches a
      configuration statement, and allows the bookkeeping writes' ordinary
      `UPDATE … SET` in 4.3.

    Checks on the guard itself:
    - **Reachability, at this task.** The walk scanned the
      `autoinstall_known_extensions` setting-name constant, and does not flag
      it. SQL constants arrive in 4.3, which tightens this.
    - **Positive controls.** Synthetic modules whose constant is `"INSTALL
      httpfs"`, `"https://x"` or `"SET autoinstall_known_extensions = true"`
      are each flagged.
    - **Negative control.** A synthetic constant `"UPDATE index_meta SET
      athlete_fingerprint = $1"` is not flagged.
  - **The subprocess no-import check.** In a subprocess: `import fitdocs.cli`;
    import every module that exists under `fitdocs.index` at this point,
    enumerated with `pkgutil.walk_packages` (so `fitdocs.index.store` is
    among them, asserted); run `fitdocs.plugins.discover(tmp_root,
    DEFAULT_PLUGIN_SETTINGS)`; then assert `"duckdb" not in sys.modules`.
    This is the plugin-api Req 7.2 half that 1.1's docstring cites. Importing
    the store directly makes a top-level `import duckdb` detectable now,
    before the CLI imports the index in 7.1.
  - **Mutations:**
    - drop each mandatory key in turn (its `current_setting` pin reds, and for
      `enable_external_access` the refusal-message pin reds too);
    - drop `lock_configuration` (the `SET` refusal pins red);
    - drop `WRITER_SETTINGS` (the `current_setting('storage_compatibility_version')`
      pin reds);
    - drop the writer `temp_directory` (the `writer-spill` pin reds);
    - let `fetchmany` re-raise the raw DuckDB exception (the `fetchmany`
      wrapping pin and the interrupt pin red);
    - let `fetchall` re-raise the raw DuckDB exception (the `fetchall`
      wrapping pin reds);
    - move `import duckdb` to `store.py`'s top level (the subprocess check
      reds, because it imports the store);
    - add `import duckdb` to `src/fitdocs/index/location.py` in place, with a
      `cp` backup restored afterwards (the AST guard reds);
    - add the constant `"INSTALL httpfs"` to `store.py`, then separately
      `"https://x"`, then separately `"SET autoinstall_known_extensions =
      true"` (the store-SQL guard reds each time; the last proves the
      anchored `SET` pattern is live).
  - **Observable:** the policy and boundary tests are green, and `uv run
    python -c "import fitdocs.cli, sys; print('duckdb' in sys.modules)"`
    prints `False`.
  - _Requirements: 1.5, 11.4, 12.1, 12.2, 12.4, 14.7_

- [x] 4.2 Classify DuckDB failures from their real messages
  - **`classify_error`**, with the stems and PID extraction of design.md
    § Store. It matches only `duckdb.Error` subclasses by message stem, never
    module paths. `open_index` and `create_index` now raise `IndexOpenError`
    with the classified fault.
  - **Shared test helpers**, in a new `tests/index/_helpers.py`. They reach
    DuckDB only through the store's facade, honouring the hard rule:
    - `hold_index(path, *, read_only)`: a context manager that starts a
      subprocess, which opens the index through `fitdocs.index.store.open_index`
      and holds it. It yields the subprocess's PID once the subprocess
      reports it is holding, and kills and reaps it on exit, with a timeout;
    - `forge_storage_version(path, version)`: the research.md P3 recipe,
      rewriting header bytes 12-20 and recomputing the block checksum over
      bytes 8-4096.

    Self-tests in `tests/index/test_helpers.py`:
    - forging version 64 onto a fresh index reproduces its original header
      bytes exactly;
    - while `hold_index` is active, a read-write open fails, and after it
      exits, a read-write open succeeds;
    - no subprocess survives.

    4.2, 6.3, 6.4, 7.1 and 7.2 use these helpers.
  - **Tests**, in the `tests/index/test_store.py` classification section. Each
    produces the real message in-test:
    - **LOCKED, read-write held**: a subprocess holds the file read-write, and
      the PID is parsed and equals the subprocess's.
    - **LOCKED, read-only held**: a subprocess holds the file read-only and a
      read-write open is attempted.
    - **MISSING**: a read-only open of an absent file, and a read-write open
      in a missing directory.
    - **CORRUPT**:
      - a junk file;
      - an empty file;
      - a truncated file;
      - a data block with flipped bytes.
    - **INCOMPATIBLE**: a header storage version forged to 69 with
      `forge_storage_version`.
    - **OTHER**: a statement failure through the facade (`execute("SELECT *
      FROM no_such_table")`, which raises `IndexStatementError`).
      `classify_error(exc.__cause__)` is OTHER.
    - **Not DuckDB's**: a non-DuckDB exception whose message contains a stem
      (`OSError("Could not set lock on file x")`) classifies as OTHER, never
      LOCKED.
  - **Mutations:**
    - drop each stem in turn (its case reds as OTHER);
    - break the PID regex;
    - classify by exception class only (all IOException kinds collapse);
    - drop the `duckdb.Error` subclass check (the not-DuckDB case reds as
      LOCKED).
  - **Observable:** the classification tests are green on the locked duckdb.
    Each fixture's raw message is asserted to contain its stem before
    classification (a reachability check).
  - _Requirements: 8.2, 9.3, 10.4_

- [x] 4.3 Create the schema, insert rows and keep bookkeeping in transactions
  - **The store's write side**, per design.md § Store:
    - `create_schema`: plain `CREATE TABLE` plus `COMMENT ON` for every table
      and column, with quotes doubled; never `CREATE OR REPLACE`; no
      constraint or index;
    - `apply_descriptions`;
    - `transaction`;
    - `delete_page_rows`;
    - `insert_rows`: the JSON-columnar route, non-finite to `None`, `date`
      and naive `datetime` as ISO, aware `datetime` raises `RowShapeError`,
      type and arity checks per design.md § ProducerSeam, and
      `allow_nan=False`;
    - `replace_table_rows`;
    - `read_bookkeeping`: `None` when `index_meta` is absent, empty or has
      more than one row;
    - `write_page_state`, `delete_page_state`, `write_producer_state`,
      `write_meta`, `checkpoint`.
  - **Tests**, in the `tests/index/test_store.py` DDL, insert and transaction
    sections:
    - round-trip of every `ColumnType`, including `None`, an empty
      `VARCHAR[]`, microsecond timestamps, a `DATE`, and booleans;
    - NaN, inf and -inf become `NULL`;
    - an aware datetime, a wrong arity and a `bool` in a `DOUBLE` column each
      raise `RowShapeError`;
    - comments on the registered tables are readable from `duckdb_columns()`
      on a read-only connection, and a description containing `'` survives;
    - `duckdb_constraints()` and `duckdb_indexes()` are empty after
      `create_schema`;
    - **6.5**: inserting a page's rows twice with delete-then-insert in one
      transaction leaves exactly one set;
    - an exception inside `transaction` leaves no rows;
    - `read_bookkeeping` round-trips `IndexMeta`, `PageState` and producer
      fingerprints.
  - **Mutations:**
    - skip the non-finite mapping (NaN is stored, and the `NULL` pin reds);
    - drop `delete_page_rows` from the replace path (two sets);
    - use `CREATE OR REPLACE` plus re-create without comments (the comment pin
      reds);
    - add `PRIMARY KEY (page_key)` (the constraints pin reds);
    - swallow the exception in `transaction` (the rollback pin reds).
  - **Tightening the 4.1 guard.** Its reachability check now also requires at
    least one `CREATE TABLE` constant and at least one `INSERT INTO` constant
    found in `store.py`. Bookkeeping updates may use `UPDATE … SET`, which
    the anchored pattern allows.
  - **Observable:** the store tests are green, mypy is clean, and the 4.1
    guard is still green, now finding at least one `CREATE TABLE` and one
    `INSERT INTO` constant in `store.py`.
  - _Requirements: 4.1, 4.3, 6.3, 6.5, 9.6, 13.5_

- [ ] 5. Reading the corpus and the hand-over

- [ ] 5.1 (P) Scan the workout pages once per refresh
  - **`docio.read_document`.** Append it to `docio`: bytes, text and
    frontmatter, the same symlink refusal, never raising. `read_frontmatter`
    delegates to it. The existing docio and scanner tests stay green
    unchanged.
  - **The corpus module**, per design.md § Corpus:
    - `ScannedPage`, `LeftOutPage` (`path`, `reason`, `collides_with`,
      `document_fingerprint`, in that order), `CorpusScan` and
      `scan_workout_pages`; every left-out page carries the
      `document_fingerprint` of the bytes the scan read;
    - `corpus_snapshot(data_root, scan, *, today, athlete_fingerprint, held)`,
      the one builder of a `CorpusSnapshot`: `pages` holds every scanned page
      whose key is in `held` (every scanned page when `held` is `None`);
      `left_out` holds a `CorpusLeftOut` for each of `scan.left_out` and for
      each scanned page not held; both sorted by path. It is pure: it reads no
      file;
    - the `LoadRegionReading` mapping from `classify_load_region` states:
      - COMPUTED becomes `computed`;
      - UNSUPPORTED becomes `unsupported`;
      - PLACEHOLDER becomes `not_computed`;
      - SUPERSEDED and FOREIGN become `unreadable`.
  - **`tests/index/conftest.py`.** Create it, with fixtures that build a data
    root of synthetic pages by running the real `sync` over
    `tests/fixtures/builder.py` and `merge.py` files.
  - **Tests:**
    - the key is the base sha;
    - non-workout `type` values and `AGENTS.md` are skipped;
    - a symlinked page is skipped;
    - a page whose last ref is not an archive ref is left out as
      `no_base_reference`;
    - two pages with the same base keep the first by path and leave the second
      out as `duplicate_base` naming the first;
    - pages are sorted by path;
    - each load state maps as above;
    - **`LeftOutPage`'s fields** are `path`, `reason`, `collides_with`,
      `document_fingerprint`, in order (a seam pin for analytics-query), and a
      left-out page's `document_fingerprint` equals
      `fingerprint.document_fingerprint(path, <its bytes>)`;
    - **`corpus_snapshot`**, on a scan with one `no_base_reference` page and
      one `duplicate_base` page:
      - with `held=None`, `pages` is every scanned page and `left_out` is the
        two left-out pages, with their fingerprints;
      - with a `held` set missing one scanned key, that page appears in
        `left_out` with its document fingerprint, not in `pages`;
      - with a `held` set holding a key no scanned page has, nothing extra
        appears;
      - in every case, the paths of `pages` and `left_out` together are every
        scanned workout page exactly once, each tuple is sorted by path, and
        `data_root`, `today` and `athlete_fingerprint` are passed through
        unchanged (asserted with values that differ from any default).
  - **Mutations:**
    - key by `sources[0]` (red with a multi-file page);
    - keep the last colliding page;
    - drop the symlink refusal in `read_document` (the docio symlink tests and
      the corpus test red);
    - map SUPERSEDED to `computed`;
    - leave `scan.left_out` out of the snapshot's `left_out` (the `held=None`
      pin reds);
    - drop not-held pages instead of moving them to `left_out` (the
      missing-key pin reds);
    - ignore `held` (the missing-key pin reds).
  - **Observable:** the corpus and docio tests are green, and
    `read_frontmatter`'s callers are unchanged.
  - _Requirements: 2.6, 6.1, 6.2, 7.2, 13.3_
  - _Boundary: Corpus, docio_
  - _Depends: 2.2, 2.3_

- [ ] 5.2 (P) Re-derive a page that was not written in this run
  - **The derive module**, per design.md § Derive: `base_archive` and
    `derive_page`, mirroring the load pass's rule.
  - **Tests:**
    - **Missing**: a missing base archive gives `SOURCE_MISSING`.
    - **Unreadable**: an unreadable base (`chmod 000`, skipped when running as
      root) gives `SOURCE_UNREADABLE`.
    - **Undecodable**: an extra with corrupted bytes gives
      `SOURCE_UNDECODABLE`.
    - **Success**: equals what the load pass composes for the same page, with
      the same composed samples and the same `compute_metrics` result. The page
      is built inline in this test module, with the real `sync` over
      `merge.py` files, because 5.1's conftest fixtures may not exist yet while
      the two run in parallel.
    - **Ranking**: a three-file page ranks extras by recorded order. Use the
      run trio from `merge.py`.
  - **Mutations:**
    - take `sources[0]` as the base;
    - catch `FitDecodeError` as unreadable;
    - drop the extras from `compose_listed`'s refs.
  - **Observable:** `uv run pytest tests/index/test_derive.py` is green, and
    mypy is clean.
  - _Requirements: 3.7, 5.4_
  - _Boundary: Derive_
  - _Depends: 2.1_

- [ ] 5.3 (P) Hand each rendered page out of the sync engine
  - **`sync.py`** (workout-docs Amendment 4). Append the frozen `RenderedPage`
    and the keyword-only `on_rendered=None` parameter on `sync`, `drain` and
    `regen`.
    - The parameter is threaded through `_run_planned`, `_group_task`,
      `_process_isolated` and `_settle_pass` to `_page_task`.
    - `_page_task` calls it once, immediately after `_write_outputs` returns.
    - It is never called on the version-gate return
      (`sync.py:1842-1846`) or the settle stem-mismatch return (`:1947-1948`).
  - **Tests**, in `tests/test_sync_handoff.py`:
    - one call per written page, with `sources` equal to the written
      frontmatter, `composition.activity` equal to what was rendered (the
      composed run of `merge.py`), and `athlete` equal to the inputs passed;
    - no call for a version-gated page;
    - no call when `_write_outputs` raises: a monkeypatched write failure, with
      the callback asserted never called;
    - no call for a settle stem mismatch;
    - a page re-rendered by the settle pass is called again;
    - with `on_rendered=None`, every golden document and every existing sync
      test is byte-identical;
    - **9.7**: the same `sync` run with and without a callback writes
      byte-identical data roots.
  - **Mutations:**
    - call before `_write_outputs` (a test injecting a write failure reds);
    - call in the version-gate branch;
    - pass the base activity instead of the composition.
  - **Observable:** the hand-over tests and the full sync and render suites
    are green, and the golden docs are unchanged (`git diff --stat
    tests/render/golden_docs` is empty).
  - _Requirements: 7.5, 9.7, 14.3_
  - _Boundary: SyncHandoff_

- [ ] 5.4 Collect hand-overs within a memory bound
  - **The handoff module**, per design.md § Handoff:
    `HANDOFF_SAMPLE_BUDGET = 250_000` and `HandoffCollector`. It keys by the
    base sha, uses budget admission, replaces on a repeated key, and checks
    `sources` equality in `take`.
  - **Tests:**
    - the exact budget boundary: an entry that fills it exactly is admitted,
      and one sample more is dropped;
    - a repeated key replaces the entry and adjusts the count;
    - a `sources` mismatch returns `None`;
    - a page moved by the settle pass is still found by key;
    - `take` of an unknown key returns `None`.
  - **Mutations:**
    - change `<=` to `<` (the boundary test reds);
    - key by `doc_ref` (the moved-page test reds);
    - drop the `sources` check.
  - **Observable:** `uv run pytest tests/index/test_handoff.py` is green, and
    mypy is clean.
  - _Requirements: 5.3, 7.5_
  - _Depends: 5.3_

- [ ] 6. The refresh and the build

- [ ] 6.1 Reconcile pages: plan, document tier, computed tier, removals
  - **`refresh.py`'s `reconcile` page path**, per design.md § Refresh, steps
    1-4:
    - scan;
    - plan the document-due and computed-due pages, with the
      missing-base retry rule;
    - per-page transactions;
    - no write when the outcome equals the stored state;
    - per-page error rollback with the stored state untouched;
    - one transaction per removal.

    Also define `RefreshInputs`, `RefreshResult` and `PROGRESS_EVERY`.
    `reconcile` reads the producer tuples as `registry.<NAME>` at call time
    (design.md § Registry).
  - **`tests/index/conftest.py` gains two fixtures:**
    - **`core_registry`**: monkeypatches the registry to its core-only values,
      `registry.DOCUMENT_PRODUCERS = (CORE_DOCUMENTS,)`,
      `registry.COMPUTED_PRODUCERS = (CORE_COMPUTED,)` and
      `registry.CORPUS_PRODUCERS = ()`;
    - **the built-index fixture**: schema created, reconcile from empty. It
      requests `core_registry`, so the index is built under the same registry
      its refresh then uses. A test that registers a fake producer patches
      the tuple on top of `core_registry` and builds its own index after the
      patch.
  - **Tests** (`tests/index/test_refresh.py`, pages section). Each starts by
    asserting its postcondition is false. Every test that asserts an exact
    write set or a no-op runs under `core_registry`: the effort edit, the load
    rewrite, the rename, the render change, the removal, the base change, the
    missing base's no-write retry and the no-op. So a later spec's registered
    producers never change what they assert.
    - **New pages**: added with both tiers.
    - **Effort edit**: a hand-edited `effort` gives a document-only update,
      and a spy confirms `derive_page` is not called.
    - **Load rewrite**: a rewrite by the real `load` pass gives a
      document-only update.
    - **Rename**: same key, the path updated, no derivation.
    - **Render change**: a body change outside regions gives a computed
      recompute.
    - **Removal**: a deleted page has every row removed from every per-page
      table and `index_pages`.
    - **Base change**: the identity fixtures' higher-ranked file joining
      removes the old key and adds the new one.
    - **Hand-over**: with a hand-over present, no derivation happens for that
      page.
    - **Hand-over inputs** (5.3): a hand-over whose `athlete` differs from
      `RefreshInputs.athlete` (a different FTP) records the hand-over's
      `athlete_fingerprint` in `activities`, and the hand-over's metric values.
      Assert first that the two fingerprints differ.
    - **Missing base**: recorded `source_missing`, no computed rows; nothing
      written on the next refresh while still missing; computed rows
      appear when the archive appears.
    - **Page error**: a test-registry producer raising on one page leaves that
      page's previous rows, commits the others, records the error, and
      retries next time.
    - **No-op**: a second refresh leaves size, mtime_ns and sha256 of every
      file in the index directory identical.
  - **Mutations:**
    - treat every document-due page as computed-due (the effort and rename
      spies red);
    - use `inputs.athlete` for handed-over pages (the hand-over-inputs pin
      reds);
    - omit the path from the plan's comparison;
    - skip removals;
    - write `PageState` even when nothing changed (the no-op pin reds);
    - commit before the producer runs (the page-error pin reds).
  - **Observable:** the pages section is green, and mypy is clean.
  - _Requirements: 1.7, 3.7, 5.1, 5.2, 5.3, 5.4, 6.3, 6.4, 7.2, 7.3, 7.4, 9.4, 9.5_

- [ ] 6.2 Refresh corpus producers, metadata and progress
  - **`reconcile` steps 5-6**, per design.md § Refresh:
    - the snapshot from `corpus.corpus_snapshot(data_root, scan, today=…,
      athlete_fingerprint=…, held=…)`, where `held` is the keys
      `index_pages` holds after steps 3 and 4 (a page whose transaction
      rolled back keeps its previous membership);
    - corpus fingerprint gating on
      `fingerprint.combined_corpus_fingerprint(producer, snapshot)`, with
      whole-table replacement in one transaction per producer. Neither the
      snapshot nor the three-part fingerprint is assembled in `refresh.py`;
    - producer error rollback;
    - **a raising `fingerprint()` is that producer's error**: no transaction
      runs, its previous rows and stored fingerprint are kept, the error is
      appended to `producer_errors`, the other producers and the meta step
      proceed, and the producer is retried at the next refresh;
    - the meta update, reading the version through
      `fitdocs.version.tool_version()` as a module attribute at call time,
      like `combined_corpus_fingerprint` (2.3), so one monkeypatch moves both;
    - `apply_descriptions` when the fitdocs version differs.

    Plus the progress callback: it fires when the total exceeds
    `PROGRESS_EVERY`, every `PROGRESS_EVERY` pages and at the end.
  - **Tests**, in the corpus, meta and progress section. Fake corpus producers
    are registered by monkeypatching `registry.CORPUS_PRODUCERS` in the test,
    on top of `core_registry` (6.1), never editing the registry. Every test
    here that asserts an exact write set or a no-op runs under
    `core_registry`, the 5.5 test included.
    - Rows are replaced only when the producer's fingerprint moves.
    - A fitdocs-version change, monkeypatched on `fitdocs.version.tool_version`,
      recomputes them and reapplies every description.
    - An exception from `rows` keeps the previous rows and stored
      fingerprint, and records the error.
    - **A raising `fingerprint()`**: two fake producers, one whose
      `fingerprint` raises and one whose fingerprint moved since the last
      refresh, with the athlete inputs also changed. After the refresh, the
      raising producer's rows and stored `index_producers.fingerprint` are
      unchanged and its error is in `producer_errors`; the other producer's
      rows are replaced; `index_meta` carries the new athlete fingerprint.
      Assert first that the moved producer's stored fingerprint differs from
      its new one.
    - **The snapshot.** A fake producer records the snapshot it is handed, on
      a refresh that adds one new page and removes one held page. It
      holds every held page, sorted, with `today` exactly as passed, and it
      equals `corpus_snapshot(data_root, scan_workout_pages(data_root),
      today=…, athlete_fingerprint=…, held=frozenset(<read_bookkeeping(conn)
      .pages after the refresh>))`: the snapshot a reader rebuilds.
    - **The snapshot after a page error.** A test-only document producer
      with no tables (`tables=()`, so the built index needs none, as in 6.5)
      is appended to `registry.DOCUMENT_PRODUCERS` on top of `core_registry`.
      It raises on one new page and on one page held before (whose file was
      edited so it is document-due). The recorded snapshot has the new page
      in `left_out`, not `pages`, and the previously held page still in
      `pages`, with its new document fingerprint. On the next refresh, with
      the raising producer removed, the new page moves to `pages` and the fake
      producer's fingerprint moves (the fake fingerprints the paths of `pages`
      and of `left_out` as two separate lists).
    - **5.5**: an athlete-inputs change alone writes only `index_meta`
      (`activities` rows unchanged), and the old athlete fingerprint is still
      on the rows.
    - The progress callback's exact call list is `[(100, 101), (101, 101)]`
      for 101 due pages, and `[]` for 100. The pages are cheap missing-source
      pages, as in 7.1.
  - **Mutations:**
    - always recompute corpus producers;
    - skip `apply_descriptions` (a changed description is not visible);
    - update `activities.athlete_fingerprint` on a meta change;
    - change `>` to `>=` in the progress threshold;
    - let an exception from `fingerprint()` propagate out of `reconcile` (the
      raising-fingerprint test reds);
    - build the snapshot with `held=None` (the page-error snapshot pin reds:
      the failed new page lands in `pages`);
    - build `held` from the bookkeeping read before the pages step, ignoring
      commits (the new page never moves to `pages`, and the snapshot-equality
      pin reds);
    - make the built-index fixture skip `core_registry` while a test-only
      corpus producer whose fingerprint covers `snapshot.athlete_fingerprint`
      is appended to `registry.CORPUS_PRODUCERS` in `registry.py`, both in
      place with `cp` backups restored afterwards (the 5.5
      writes-only-`index_meta` pin reds: the isolation is what keeps it green
      once a later spec registers producers).
  - **Observable:** the section is green, and mypy is clean.
  - _Requirements: 1.7, 5.5, 7.7, 13.2, 13.3, 13.8_

- [ ] 6.3 Run the refresh after a command, never raising
  - **`refresh_after_command`** and `IndexReport`/`Outcome`, per design.md
    § Refresh: the ordered outcome checks, and the catch-all to FAILED, with
    `KeyboardInterrupt` propagating.
  - **Tests**, in `tests/index/test_post_pass.py`:
    - **NOT_BUILT**: an absent index gives NOT_BUILT, and no directory is
      created.
    - **BUSY**: a subprocess holding the writer lock gives BUSY. A subprocess
      holding DuckDB's read-write lock (`hold_index` from 4.2's helpers) gives
      BUSY with the holder's PID.
    - **NEEDS_REBUILD**: a junk file, a forged-version file
      (`forge_storage_version`), an index with no
      `index_meta`, and an index recording schema version 99 each give
      NEEDS_REBUILD with the matching reason. The file is byte-identical
      afterwards.
    - **FAILED**:
      - a refused location (a relative `FITDOCS_INDEX_DIR`);
      - a malformed `athlete.toml`;
      - an exception raised inside `reconcile` (monkeypatched).
    - **REFRESHED and UNCHANGED**: on a healthy index.
  - **Mutations:**
    - create the directory on NOT_BUILT;
    - remove the catch-all (the FAILED test raises);
    - treat a schema-version mismatch as REFRESHED;
    - drop the PID from BUSY.
  - **Observable:** `uv run pytest tests/index/test_post_pass.py` is green.
  - _Requirements: 1.3, 1.4, 8.1, 8.2, 8.3, 9.2, 9.3_

- [ ] 6.4 Build, rebuild and swap the index safely
  - **`build.py`**, per design.md § Build: `run_index_command`, with
    - `_build` into `index.duckdb.building` (the leftover removed first,
      schema, meta, producer rows, reconcile from empty, checkpoint, close);
    - `_swap`: remove `index.duckdb.wal`, `os.replace`, and fall back to
      `index.duckdb.rebuilt` on `PermissionError`;
    - completing a staged swap first on the next run;
    - errors: `IndexLocationError` propagates, everything else becomes FAILED.
  - **Tests** (`tests/index/test_build.py`):
    - a build when absent creates the directory with mode `0o700`;
    - `--rebuild` over a current index gives BUILT with no rows lost;
    - a rebuild over a junk file, over a forged-version file and over a
      schema-99 index each gives BUILT with the reason;
    - **10.6**, the P4 scenario: a subprocess writes a committed row and
      exits with `os._exit` while `checkpoint_threshold` is high, leaving a
      WAL beside the old file. The rebuild then contains no foreign row or
      table. Assert first that the WAL exists;
    - `os.replace` monkeypatched to raise `PermissionError` gives STAGED,
      leaves `index.duckdb` unchanged and `index.duckdb.rebuilt` complete,
      and the next run swaps it and refreshes;
    - a read-only reader subprocess holding the old file during a rebuild reads
      the old row count whole, and a new reader reads the new count. The
      reader is a local subprocess in `tests/index/test_build.py` that opens
      the index read-only through the store facade and reports a row count;
      `_helpers.py` stays 4.2's;
    - LOCKED on an incremental run gives BUSY;
    - a failing build leaves `index.duckdb` unchanged;
    - a junk leftover `index.duckdb.building`, with a junk `.wal` beside it, is
      removed and the build succeeds.
  - **Mutations:**
    - skip the WAL unlink (the P4 test shows the foreign row);
    - build in place on `index.duckdb`;
    - skip the staged completion;
    - leave the leftover `.building` (a partial-file test reds).
  - **Observable:** `uv run pytest tests/index/test_build.py` is green on
    macOS and Linux. The Windows replace behaviour is recorded as untested in
    Implementation Notes (research.md).
  - _Requirements: 1.6, 1.7, 10.2, 10.3, 10.4, 10.5, 10.6, 10.7, 10.9_

- [ ] 6.5 Prove interruption safety and determinism end to end
  - **Interruption** (`tests/index/test_interruption.py`):
    - **The setup.** A subprocess refreshes an index whose five pages are all
      due for computed values. A test-only computed producer is registered by
      monkeypatching in the subprocess. It writes the page's key to a pipe
      when called, and on the fourth page blocks until killed.
    - **The producer declares no tables.** It has `tables=()` and returns `{}`.
      The index was built without it, so any table it declared would not
      exist there, and every page would fail rather than commit.
    - **The kill point.** The parent reads four keys from the pipe, then
      `SIGKILL`s the subprocess. The kill therefore lands inside page 4's
      producer call, after pages 1-3 have committed.
    - **The assertions:**
      - reopening shows pages 1-3 fully new (new fingerprint and rows);
      - pages 4 and 5 are fully old: their old `index_pages` fingerprint and
        their old rows, with none of page 4's new rows;
      - the next refresh completes pages 4 and 5.
  - **Determinism** (`tests/index/test_determinism.py`). The same synthetic
    corpus is indexed:
    1. incrementally in path order;
    2. after creating pages in reverse order;
    3. from the hand-over;
    4. by re-derivation, with the hand-over disabled;
    5. by `run_index_command(rebuild=True)`.

    For every table of the core producers (`CORE_DOCUMENTS.tables` and
    `CORE_COMPUTED.tables`, read from the producers, not a hard-coded list),
    `SELECT * … ORDER BY ALL` (through the facade) is equal across all five,
    and non-empty. The rows are asserted non-trivial before comparing. Both
    assertions are scoped to the core producers' tables, so they stay green
    when a later spec registers producers whose tables may be empty on this
    fixture; those producers prove their own determinism. All five runs pass
    the same `today`.
  - **Mutations:**
    - write and commit `PageState` before computing and inserting the page's
      rows. The kill then falls after a page's new fingerprint is recorded
      without its rows, and the reopened index shows the mixed page;
    - make the hand-over path round a metric (the hand-over versus
      re-derivation comparison reds).
  - **Observable:** both modules are green, and the kill test leaves no
    process behind.
  - _Requirements: 4.5, 6.5, 9.6_

- [ ] 7. CLI integration and guards

- [ ] 7.1 Add the `fitdocs index` command
  - **`cli.py`:**
    - `index_command`, with `--out` and `--rebuild`, per design.md
      § CliWiring;
    - `_report_index_command`;
    - `_index_progress` to stderr;
    - the exit mapping;
    - the module docstring: "Twelve" commands, an `index` entry, and the
      exit behaviour;
    - `tests/test_cli_skill.py:262-270`: 11 becomes 12.
  - **Tests** (`tests/index/test_cli_index.py`):
    - **The first run**: on fixture pages it prints the table counts, `Index
      file: <abs path inside FITDOCS_INDEX_DIR>` and
      `f"Schema version: {SCHEMA_VERSION}"`, and exits 0. The schema line is
      pinned from the constant, never the literal `1`, so a later spec's
      version advance keeps it green.
    - **A second run** gives UNCHANGED, exit 0, with identical counts.
    - **Detail lines**: a missing-source page is listed with its reason, exit
      0. A duplicate-base page is listed as left out, naming the other page.
    - **Exit 1**: a page-producer error, a held DuckDB lock (`hold_index`),
      and STAGED.
    - **Exit 2**: a relative `FITDOCS_INDEX_DIR`, a malformed `athlete.toml`,
      and an unresolvable data root.
    - **Progress**: `Indexing: 100/101 pages` and `101/101` on stderr for 101
      missing-source pages, and none for 100. Stdout carries no progress
      line.
  - **Mutations:**
    - exit 0 on STAGED;
    - print progress to stdout;
    - omit the left-out lines;
    - map `IndexLocationError` to exit 1;
    - print `Schema version: 1` as a literal and set `SCHEMA_VERSION` to 2 in
      `schema.py`, both in place with `cp` backups (the schema-line pin
      reds).
  - **Observable:** the command tests and `tests/test_cli_skill.py` are green,
    and `uv run fitdocs index --help` lists `--rebuild`.
  - _Requirements: 6.2, 7.7, 10.1, 10.8, 10.9_

- [ ] 7.2 Refresh the index after every writing command
  - **`cli.py`:**
    - `_run_index_pass` at the four call sites of design.md § CliWiring:
      after the plan pass for `sync SOURCE`, `_run_drain_passes` (the drain
      and `pull --sync`) and `regen`, and after the load pass for `load`;
      always before `_report_plugin_errors`;
    - a `HandoffCollector` created before `sync()`, `drain()` and `regen()`
      and passed as `on_rendered`;
    - `_report_index_pass`, with the exact lines of design.md.

    The `failed` flag passed to `_finish` is untouched.
  - **Tests** (`tests/index/test_cli_post_pass.py`):
    - **The refresh runs.** Each of `sync SOURCE`, the drain, `pull --sync`
      (folder connector) and `regen` refreshes a prebuilt index. The pages
      appear, and the line `Index: N added, …` comes after the `fitdocs load`
      table and any `reconciled` lines, and before `Plugin errors:`.
    - **`load` alone** refreshes the document tier with no derivation (a spy).
    - **No re-read.** A sync's refresh reads no archived file for the pages it
      wrote: spy on `derive_page`.
    - **Exit codes unchanged**, against the same command with the index
      directory absent, under each of these failures:
      - a held DuckDB lock (`hold_index`);
      - a junk index;
      - a refused location;
      - a raising producer;
      - a sync with a file failure, which stays exit 1.
    - **Silence.** No index line when nothing changed.
    - **The not-built line** prints when the index is absent.
  - **Pre-existing tests.** Update every test that pins the full stdout of
    `sync`, `regen` or `load`, which now prints `Index: not built; …` under
    isolation. List each in Implementation Notes. The comparison-based pins
    (`tests/test_cli_reconcile.py:196, 238, 286`) must stay green without
    edits.
  - **Mutations:**
    - call `_run_index_pass` before the load pass (the ordering pin and the
      load-region document-tier pin red);
    - let a refresh failure set `failed` (the exit pins red);
    - drop `on_rendered` (the no-re-read spy reds);
    - print the summary line on UNCHANGED.
  - **Observable:** the post-pass tests and the full CLI suite are green, and
    no golden document changes.
  - _Requirements: 7.1, 7.5, 7.6, 8.1, 8.2, 9.1, 9.2_

- [ ] 7.3 Extend the confinement, network and boundary guards to the index
  - **`tests/test_confinement.py`:**
    - append `EntryPoint(id="index", …)`, running `fitdocs index` with
      `FITDOCS_INDEX_DIR=<sandbox>/index-cache`, non-vacuous only if
      `index.duckdb` was written;
    - extend `permitted_locations` with the resolved index directory;
    - **the post-pass entry**, `EntryPoint(id="sync-with-index", …)`. The
      existing `sync`, `regen` and `load` entries call the engine functions
      directly (`tests/test_confinement.py:310-328, 447`), never the CLI, so
      they never reach the post-pass, and running them with the sandboxed
      variable would prove nothing new. The new entry:
      - prepares a prebuilt index under `<sandbox>/index-cache`;
      - runs `fitdocs sync SOURCE --out <data_root>` through `CliRunner`;
      - its non-vacuity check requires a workout document written **and** a
        file in the index directory changed;
    - add membership pins for both new entries.
  - **`tests/connectors/test_e2e.py:203-207`**: append `index` to the offline
    list. The comparison also substitutes each run's index location, which
    differs per data root.
  - **`tests/test_inbox_e2e.py`**: with an index prebuilt, the second drain
    leaves every file in the index directory byte-identical (7.4).
  - **`tests/index/test_boundary.py`:**
    - `_INDEX_IMPORTERS = {"fitdocs.cli"}`: no module outside `fitdocs.index`
      except those imports `fitdocs.index`, with a positive control. The set
      is append-only: analytics-query appends `fitdocs.query.sandbox`,
      `fitdocs.query.statement`, `fitdocs.query.freshness`,
      `fitdocs.query.schemaview` and `fitdocs.query.command`. The check is
      one-way: it fails on an importer missing from the set, and never on a
      listed name whose module does not exist, so query can append its names
      ahead of its modules. A fixed-input test pins both directions: a
      synthetic importer not in the set is flagged, and a listed name with no
      module is not;
    - **the untouched-commands check** (7.8, 12.4). The parent first builds
      an index for a fixture data root with `fitdocs index`, then hand-edits
      one page's `effort` tag so the index is behind the corpus, then
      snapshots every file in the index directory (size, `mtime_ns`,
      sha256). A
      subprocess then runs, through `CliRunner`, against that data root and
      index: `check`, `history`, `plan`, `derive-benchmarks`, `plugins`,
      `skill`, `--version`, and `connect` and `pull` without `--sync` against a
      folder-connector instance. It asserts:
      - `"duckdb" not in sys.modules` afterwards;
      - no output line starts with `Index:`.

      The parent then asserts the index directory's snapshot is unchanged.
      Preconditions, asserted first:
      - the index exists and holds at least one page;
      - the edited page's bytes differ from those recorded at the build.

      So a refresh, if wrongly run, would write the edit and print an
      `Index:` line.
  - **9.7**: the same `sync` and `load` with and without a prebuilt index leave
    byte-identical data roots.
  - **Mutations:**
    - write a scratch file inside the data root from the post-pass (the
      confinement guard reds);
    - import `fitdocs.index.refresh` from `src/fitdocs/history/engine.py`, in
      place with a `cp` backup restored afterwards (the importer guard reds);
    - make the importer guard also require every listed name to resolve to a
      module (the listed-name-with-no-module fixed-input test reds);
    - run `_run_index_pass` at the end of `check` (the untouched-commands
      check reds three ways: `duckdb` is imported, an `Index: 0 added, 1
      updated` line prints, and the snapshot changes);
    - make the post-pass re-write `index_meta` every run (the inbox pin
      reds).
  - **Observable:** the confinement, connectors-e2e, inbox-e2e and boundary
    suites are green.
  - _Requirements: 1.5, 5.6, 7.4, 7.8, 9.7, 10.10, 12.4, 12.5, 14.7_

- [ ] 8. Published contract, steering, records and final validation

- [ ] 8.1 Publish the index in the ownership contract and the release notes
  - **The ownership contract.** `docs/ownership-contract.md` gains the
    analytics-index section, per design.md § ContractDocs:
    - location and order;
    - the key;
    - refusal;
    - `0o700`;
    - the disposable cache, never read back into a document;
    - the agreement rule of 5.7, in those words;
    - the file names: `index.duckdb`, `.wal`, `index.lock`, `.building`,
      `.rebuilt`, `writer-spill/` (transient; DuckDB's spill space for
      fitdocs's own index writes, set by the store) and
      "`query-spill-<pid>/` (transient; created by `fitdocs query`, removed on
      close or by the next query)". DuckDB's default `.tmp/` is not listed:
      no fitdocs connection uses it.

    It also gains:
    - the overwrite-semantics bullets for the refresh and for `fitdocs
      index`;
    - the write-set sentence (lines 182-191) and the outside-the-data-root
      count (642-646) updated.
  - **`CONTRACT_VERSION`** advances by one from the branch's value:
    - the history paragraph in `contract.py`;
    - `docs/ownership-contract.md:3`, with its "What changed at this version"
      paragraph rewritten for this feature;
    - the phrase pins of the replaced paragraph
      (`tests/identity/test_contract_docs.py:155-165`) moved to pins on the
      history docstring, as `tests/compose/test_contract_docs.py:143-158`
      did;
    - `tests/declaration_golden/*` regenerated.
  - **`CHANGELOG.md` `[Unreleased]`**: `### Added` and `### Changed` entries
    per design.md, naming the contract and the action.
  - **`docs/install.md`**: the footprint and platform note under "Install the
    tool". The install-writes-nothing guarantee and its pin
    (`tests/test_packaging.py:952-1030`) stay true.
  - **Pins** (`tests/index/test_contract_docs.py`):
    - the contract section names `FITDOCS_INDEX_DIR`, both fallbacks and the
      refusal;
    - the agreement-rule sentences;
    - **the spill directories**: the section contains the phrase
      "`query-spill-<pid>/` (transient; created by `fitdocs query`, removed on
      close or by the next query)" and names `writer-spill/`, and the name
      equals `store.WRITER_SPILL_DIRNAME` (read from the constant);
    - the `CHANGELOG` entry is inside `[Unreleased]`;
    - `docs/install.md` names the size and both platform gaps;
    - `DOC_VERSION == 9`, the value on `main` when this plan was written. If
      a sibling lands a document-format advance first, re-pin it to `main`'s
      value: this plan never changes it.
  - **Mutations:**
    - drop the refusal sentence;
    - drop the `query-spill-<pid>/` phrase (the spill-directory pin reds);
    - change `WRITER_SPILL_DIRNAME`'s value in `store.py` without touching
      the contract (the spill-directory pin reds);
    - move the CHANGELOG entry under `[0.1.0]`;
    - leave `CONTRACT_VERSION` unchanged (the version pins and the golden
      red).
  - **Observable:**
    - the contract, declaration, docs and packaging tests are green;
    - the docs-site suite that builds `docs/` is green (find it with `grep -rl
      "ownership-contract" tests/`);
    - `git diff tests/render/golden_docs` is empty.
  - _Requirements: 5.7, 12.6, 14.1, 14.2, 14.3, 14.4_

- [ ] 8.2 Update steering for the index
  - **`tech.md`**, per design.md § Steering:
    - the "No server, no database" paragraph is rewritten and the Phase 10
      forward note removed;
    - Key Libraries gains `duckdb`;
    - Network and Credentials adds `index` to the no-connector-request list
      and gains the DuckDB-connections sentence;
    - "the frozen runtime dependency list is unchanged" becomes "connectors
      add no runtime dependency".
  - **`structure.md`**: the `index` dependency-direction sentence.
  - **Validation by the steering class.** Read both documents end to end. Grep
    `.kiro/steering/` and `CLAUDE.md` for "no database", "frozen", "runtime
    dependency" and "re-derivable", and reconcile every hit.
    `tests/connectors/test_network_statements.py` and
    `tests/connectors/test_docs.py` stay green.
  - **Observable:** the grep output, before and after, is recorded in
    Implementation Notes, and the network-statement tests are green.
  - _Requirements: 12.5, 14.5_

- [ ] 8.3 Record the amendments in the upstream specs and the roadmap
  - **Append an amendment section to each spec**, numbered from that spec's
    last, in the existing "Amendment N (date): …, landed by analytics-index"
    form:
    - **plugin-api Amendment 1**: Req 7.2 amended, naming the tests (1.1, 4.1).
    - **distribution Amendment 4**: the dependency list, the pre-feature
      snapshot delta and the install footprint, naming the tests.
    - **docs-site Amendment 1**: Req 8.1 amended. The runtime dependency list
      is the pre-docs-site list plus `duckdb>=1.2,<2`, added by
      analytics-index. The site tooling still adds none, and the optional
      dependencies stay empty. It names
      `tests/sitebuild/test_repo_wiring.py::test_runtime_dependencies_are_the_pre_spec_literals`.
    - **workout-docs Amendment 4**: one appended criterion for the hand-over,
      naming `tests/test_sync_handoff.py`.
    - **connectors Amendment 1**: `index` in Req 14.1, and Req 14.5 reworded.

    No existing criterion is renumbered.
  - **Roadmap ticks**, in the Phase 10 Existing Spec Updates:
    - add the docs-site line to Phase 10's Existing Spec Updates if it is
      missing. The controller also adds it at batch finalize; the two are
      idempotent;
    - plugin-api, distribution, docs-site and workout-docs ticked;
    - connectors annotated "(analytics-index part landed)";
    - the analytics-index Specs line ticked at merge.
  - **Observable:** `/kiro-spec-status` is clean for the five specs, and each
    amendment names its pinning tests by path.
  - _Requirements: 14.8_

- [ ] 8.4 Register test modules, verify the duckdb floor and validate the feature
  - **mypy registration.** Append every new test module to `pyproject.toml`'s
    mypy `files` list.
  - **The floor check.** Run `tests/index/test_store.py`'s policy and
    classification sections against `duckdb==1.2.0`, the floor of
    `duckdb>=1.2,<2`, in a throwaway venv under the session scratchpad, with
    no network calls. Never the worktree `.venv`, and never with `INSTALL`.
    - **HOME.** At the venv/run level, point `HOME` at an **existing** empty
      directory under the scratchpad, and assert after the run that it is
      still empty. The policy tests themselves still monkeypatch HOME to a
      nonexistent path (task 4.1) and are not changed for this run; the
      run-level directory catches anything else the run writes into HOME,
      which a nonexistent HOME would hide (research.md, the P6 disclosure).
    - Installing the 1.2.0 wheel may fetch it from PyPI. Only the test run is
      network-free.
    - Record pass or fail per test, and the HOME listing after the run.
    - **If any fails, or HOME is not empty, stop and report.** The floor is
      1.2.0 by cross-spec ruling C1 (every 1.1.x release writes into HOME on
      `INSTALL`); changing it again is a roadmap decision (research.md,
      Risks).
  - **Full validation**, after the final rebase: `uv run pytest && uv run ruff
    check . && uv run ruff format --check . && uv run mypy`, plain, with
    `TZ=UTC`, and with `CI=true`. Also run the forbidden-strings gate
    (`tests/test_forbidden_strings.py`, with its data from
    `tests/_forbidden_strings.py`) in the mode the repo's other spec
    validations used, which is recorded in their Implementation Notes.
  - **Version checks.**
    - `CONTRACT_VERSION` equals `main`'s value plus one.
    - `SCHEMA_VERSION == 1`. This plan lands first by construction: both
      siblings start after it merges.
  - **Observable:** all green, with the floor-check table and the validation
    commands' output recorded in Implementation Notes.
  - _Requirements: 11.4, 12.1, 12.3_

- [ ] 8.5 (Maintainer-only) Measure the index on the real data root
  - **Who runs it.** The maintainer, on their machine. No agent reads the real
    data root.
  - **What to run:**
    - `fitdocs index --rebuild`: wall time and file size;
    - a no-change `fitdocs sync`: the index pass time;
    - a 5-file sync: the index pass time.
  - **Where results go:** `research.md`, Implementation Notes, as numbers only,
    with no personal values.
  - **Observable:** the three measurements are recorded, and the no-op pass is
    within the frontmatter-scan order of magnitude (about 1.5 s at 2,500
    pages), or a follow-up is queued.
  - _Requirements: 7.4, 7.5_


## Implementation Notes

- 1.1: DuckDB `>=1.2,<2` added and locked at 1.5.6; four dependency pins retained their names. Tests-first RED: all four dependency pins failed before adding the dependency. Required mutations (remove DuckDB, restore floor 1.1, add optional-dependencies) each failed their targeted guards; independent review repeated them and added extra dependency, ordered-list swap and omitted upper bound, with no survivors. Restored guards: 5 passed. Reviewer full suite: 8696 passed / 8 skipped; CI boundary and sitebuild: 807 passed; source-enabled forbidden-string gate: 44 passed; canonical mypy: 296 files clean; ruff check/format clean. Offline packaging CI checks passed using the existing cache-warming fixtures; no new CI-runner step required.
- Worktree setup: use `/Users/josh/.pyenv/versions/3.11.15/bin/python3.11`, matching main. Homebrew Python's executable resolution broke the docs-site fake-interpreter fixture; recreating only the worktree venv with pyenv resolved it. Real-data-root setup is unnecessary: all index tests use synthetic inputs.
- Validation: `FITDOCS_FORBIDDEN_STRINGS=/Users/josh/.fitdocs-purge/forbidden-strings.tsv` enables the existing real-tree gate. Never print its contents. Use `uv run --group docs` for required site tooling; a plain `uv run` can remove the docs group. Scoped mypy on the three pre-existing unregistered dependency test modules reports 11 baseline errors, independently reproduced on main; canonical mypy is clean.

- 1.2: per-test autouse index-directory fixture; absolute/outside-home and marker isolation pins, plus actual pytest lifecycle pins for both existing and absent environment values. Tests-first RED 3 failures before fixture. Mutations: drop autouse with relative/home original values, share one session directory, direct environment assignment; each targeted assertion failed. Independent review added missing directory, deletion of existing env at teardown, absent env restored as empty string; all caught. First review rejected an unpinned cleanup behavior; remediation supplied the lifecycle pins. Final independent review APPROVED: full suite 8707 passed / 2 actionlint skips, canonical mypy 296 files clean, scoped ruff/type checks clean. Fresh completion gate 5 passed.
- Full regression must use the normal warmed uv cache with sandbox escalation, rather than a fresh synthetic UV_CACHE_DIR: packaging builds/offline fixtures need cached hatchling and dependency wheels. A cold-cache review run failed setup; the canonical warmed-cache rerun passed. Task-local synthetic uv caches are not interchangeable with the canonical regression environment.

- 1.3: exact Location API, lightweight index/core packages, resolved slug+16-hex key, env precedence/refusals and private creation of missing cache ancestors with existing modes retained. Flag OFF RED 10 failures; ON and removed GREEN. Final tests 11 passed. Independent review3 APPROVED: 44 claimed mutations and 3 reviewer mutations caught; full source-enabled suite 8718 passed / 2 actionlint skips; canonical mypy 299 files clean, scoped source/test mypy and ruff clean; fresh completion gate 11 passed.
- 1.3 discrimination repairs: a root-path substring can match the child path, so refusal diagnostics now assert both labeled paths; equality must make the final per-root directory resolve to the root itself, with that precondition asserted (base_dir==root only tests a descendant); expected filenames and environment keys use literals, because deriving expectations from exported production constants makes constant-value changes invisible. Missing cache-base parents must be exercised; ordinary mkdir(parents=True) leaves intermediate modes dependent on umask.
- Host allocation limit encountered at 1.3 remediation: new agent creation and resurrection of retired threads were refused. Remaining dispatch reuses an available Luna implementer thread and a separate available reviewer thread. This is a downgrade from fresh-per-task contexts; reviewer code/mutation checks remain independent from implementation, with actual current diff/spec as input.
- 2.1: schema version 1, schema enums/carriers/validator/manifest/digest and typed bookkeeping declarations. Initial tests-first import RED and feature-off RED recorded; final schema tests 203 passed. Unit descriptions now match complete words/phrases, so milliseconds cannot satisfy seconds, millimetres cannot satisfy metres, and locale cannot satisfy local. Final independent review APPROVED: 125 distinct mutations each produced named assertion failures and restored passes; full source-enabled/docs regression 8921 passed / 2 actionlint skips; canonical mypy 301 files clean, scoped mypy and repository Ruff clean. Fresh completion verification: 203 passed.
- 2.1 review/debug learnings: exercise validation in every applicable scope, including bookkeeping, and global collision rules within/across registries. Use otherwise-valid fixtures and specific diagnostics so another guard cannot intercept. Complete resolver outputs need independent literal expectations for every field, varied column types/descriptions and multiple nonalphabetical table declarations. Debug rounds 1 and 2 repaired test structure only: partial comparisons missed metadata/order; eager parameter tuples then caused enum mutations to abort collection. Callable factories preserve literal expectations while allowing named enum contract assertions to execute. All source mutations restored before approval; no seam changes.
- 2.2: exact producer aliases, six frozen input carriers and three readonly structural protocols, with all producer obligations documented. Tests-first RED: three assertions failed before the module existed. Required snapshot field deletion and computed-field reorder mutations failed named field pins; alias, authoritative types, frozen state and protocol signatures also discriminate. Final review APPROVED: 18 claimed mutation observations plus two new reviewer probes red/restored green; earlier exhaustive carrier/protocol sweep confirmed 93 additional probes. Full docs/source-enabled suite 8925 passed / 2 actionlint skips; canonical mypy 302 files and scoped mypy/Ruff clean. Fresh completion gate: four producer tests plus the ordered nesting regression, 5 passed.
- 2.2 typing-test learnings: pin every generic alias argument independently, including Rows' str key, and import expected external types from their authoritative owner rather than the production module under test. In-process mypy.api.run raises Python's global recursion limit to 16384: restore the caller's limit in finally. Without cleanup, the later docs-site absurd-nesting test failed; the ordered pair reproduced RED before the fix and GREEN afterwards. Independent review verified exception-path cleanup. No production seam changes were needed.
- 2.3: five pure fingerprint APIs with exact SHA-256/canonical JSON recipes, all athlete fields, dynamic tool version and unchanged producer exceptions. Tests-first/flag OFF RED 31 failed / 1 passed, flag ON and removed GREEN; EOF regression RED before grammar-aware fix. Final review APPROVED: 39 distinct recipe/target observations named RED/restored GREEN; full source-enabled/docs suite 8963 passed / 2 actionlint skips, canonical mypy 303 files and scoped mypy/Ruff clean. Fresh completion gate 38 passed.
- 2.3 learnings: reconstructing a region_block and replacing its string misses valid end markers at EOF without a final newline; public docmerge.merge_regions splices grammar-valid content while retaining markers and unknown regions. Pin every effort exclusion and eligible managed field with complete literal payloads. All three zone precision fixtures use 1.12345678901/1.12345678902 (twelfth significant digit), not eight-digit substitutes; ten-decimal rounding collides before exact hashes differ. Expected-fingerprint setup must not populate the snapshot spy before the forwarding assertion: verify it is unset immediately before composition. Rename coverage physically writes, renames and rereads synthetic bytes, verifies the document hash moves, then checks render invariance.
- 2.4: nonblocking advisory writer lock, fcntl with msvcrt fallback, mode 0600 creation and unchanged existing file bytes/mtime/size. Tests-first and flag-OFF RED 5 failures; ON and removed GREEN. Real subprocess contention, timeout-safe blocking mutation, SIGKILL release and normal/exception release are pinned. Final review APPROVED: 21 claimed mutations plus 2 new reviewer probes named RED/restored GREEN, full docs/source-enabled suite 8980 passed / 2 actionlint skips; canonical mypy 304 files and scoped mypy/Ruff clean. Fresh completion gate 17 passed. Windows backend tested synthetically on POSIX; native Windows execution unavailable.
- 2.4 cleanup learnings: closing a descriptor itself releases flock, so an OS-level release check cannot pin an explicit unlock call. Independent event expectations pin unlock-before-close and exact flags/descriptors/byte counts across both backends' normal exit, body exception, contention, unexpected acquisition error and unlock error paths. Recording stubs do not reject arguments before assertions. Only contention errors map to WriterBusy; unrelated errors propagate.
- 3.1 BLOCKED: tests-first RED 7 missing-module failures; partial documents producer and tests preserved uncommitted. contract.LoadReading contains only value/methodology, and no public reader exposes recorded load_basis. The halted payload-basis fallback would violate frontmatter provenance. Debug1 returned STOP_FOR_HUMAN (task decomposition): approve an additive document_load_basis reader prerequisite in contract.py/tests/test_contract.py, explicitly define absent/wrong-type/empty-string behavior, amend CoreDocuments and task ownership/dependency, and revalidate plan-resolution/history consumers. Preserve LoadReading/document_load and document bytes; use distinct recorded-vs-payload basis and a noncomputed recorded-basis fixture. Debug plan: /private/tmp/analytics-index-evidence/3.1/debug1/REPORT.md. No task3.1 completion or feature GO claimed; branch parked pending plan approval.
- Approval resumed: maintainer approved document_load_basis and the proposed missing/non-string/blank semantics. Added prerequisite 2.5 and amended reader ownership, CoreDocuments and the upstream plan-resolution contract. Task3.1 now waits on 2.5; its partial source/tests are preserved under /private/tmp/analytics-index-evidence/3.1/parked/ until prerequisite verification finishes.
- 2.5 public guard alignment: the approved new export also requires its literal entry in tests/test_public_api.py's existing exact export-set pin. Added that test file to prerequisite ownership after canonical regression exposed the omitted expectation; this is required by the existing approval of the public reader and changes no additional API semantics.
- 2.5: approved additive document_load_basis reader exported publicly, None for missing/non-string/blank (Unicode whitespace included), nonblank recorded strings preserved verbatim for any Mapping and read without mutation or load-validity gating. Tests-first RED 11 failures; flag OFF 2 intended failures, ON/removed GREEN. Final independent review APPROVED: 12 claimed observations plus 2 new reviewer probes named RED/restored GREEN; full docs/source-enabled suite 8994 passed / 2 expected actionlint skips; canonical/source mypy and repository Ruff clean; scoped mypy retains six unchanged baseline test errors already queued. Fresh completion gate 282 API/contract/history/plan tests passed. Whole-module AST comparison proves all old definitions unchanged; public API expectation gained only the new literal.
- 2.5 review learnings: mixed-case and Unicode-only whitespace fixtures are needed to pin verbatim/blank behavior; general Mapping and input-preservation pins prevent dict-only or destructive readers. Narrow mutation replacements to the target function and compare the entire restored source against HEAD: a generic blank-guard edit accidentally drifted document_date and was restored before acceptance. A new approved export requires updating the existing exact public API set pin; preserve the guard rather than weakening it. Prerequisite now clears task3.1's recorded-basis blocker.

- 3.1: pure core.documents producer and four exact document-tier schemas; approved recorded-basis reader consumed independently of payload basis. Original missing-module/flag RED and restored GREEN retained. Independent review round2 APPROVED: 60 claimed observations plus two own probes produced named assertion failures and restored passes; full source-enabled/docs suite 9011 passed / two expected actionlint skips; canonical/scoped mypy and repository Ruff clean. Parent fresh completion gate 17 passed.
- 3.1 fixture learnings: preserve real zeros separately from None in selected, nonselected and frontmatter loads; cross archive/nonarchive reference kinds with base/extra roles. Nullable fields require both populated and genuinely absent inputs, including bare valid effort optional fields and computed payload/result absence. Recorded basis must survive invalid/missing old load pairs. Schema descriptions with prescribed literals must match exactly.

- 3.2: pure core.computed producer and six exact computed-tier schemas with metric/sample columns generated from authoritative dataclass field order. Reported tests-first missing-module and OFF/ON/removal lifecycle retained; raw initial outputs were not saved and were not reconstructed. Independent review round2 APPROVED: 46 distinct claimed mutations plus two own probes produced named assertion failures and restored passes; full source-enabled/docs suite 9020 passed / two expected actionlint skips; canonical/scoped mypy and repository Ruff clean. Parent fresh completion gate nine passed.
- 3.2 fixture learnings: retain real composition/compute regressions but also supply independent distinct scalar metrics, all-None/real-zero rows, contrasting headers and empty fingerprint to defeat recomputation and tied-value swaps. Athlete=None shadows per-channel missing times/spec branches; exercise each independently with other channels populated and distinct zone time tuples. Multiple extras pin provenance cardinality. String enums need exact stored-string type assertions. A datetime.min sentinel with negative offsets overflows before assertions; use a safe timestamp and report actual failure types.

- 3.3: typed append-only core registries, call-time resolver forwarding and literal schema version 1 digest/model/comment pins. Raw missing-registry RED and flag OFF/ON/removed lifecycle saved. Independent review round2 APPROVED: 53 claimed observations plus two own probes produced named assertion failures and restored passes; full source-enabled/docs suite 9023 passed / two expected actionlint skips; canonical/scoped mypy and repository Ruff clean. Parent fresh completion gate 206 passed.
- 3.3 fidelity learnings: dynamic registry fixtures require multiple distinguishable producers, multiple nonalphabetically ordered tables per producer and complete independent ResolvedTable expectations across bookkeeping/document/computed/corpus scopes. Partial name/scope comparisons miss table/column descriptions and corpus types/order; the digest deliberately excludes comments and default corpus is empty. Distinct metadata and exact injected-key literals pin forwarding; retain core model/version pins.

- 4.1: lazy-only DuckDB store facade, mandatory seven-setting policy, writer compatibility/spill configuration and AST/subprocess/SQL guards. Raw missing-module and OFF/ON/removed RED/GREEN saved. Independent review round2 APPROVED: 65 claimed observations plus two own probes confirmed; full source-enabled/docs suite 9107 passed / two expected actionlint skips; canonical/scoped mypy and repository Ruff clean. Parent fresh completion gate 84 passed. Header version 64 remains PRESERVED-ONLY on DuckDB 1.5.6; captured configuration pins writer policy independently. Classification remains OTHER for task4.2.
- 4.1 execution learning: raw DB-API execute blocks the aggregate COUNT before fetch; instrumented subprocess stopped at before-execute. The facade uses lazy connection.sql with parameters, preserving fetch-time error/interrupt behavior and immediate nonquery effects. Real bounded fetchmany interruption passes; preserve this strategy for query siblings. Official relational API documentation supports lazy evaluation.
- 4.1 fixture/guard learnings: verify raw driver forwarding with live read-only/caller-setting checks plus a synthetic backend, nonquery effects and multi-parameter/batch cursor state. Compare original exception object identity across ordinary/interrupt execute/fetchmany/fetchall/open cases. AST imports need positional and literal keyword name forms plus aliases/submodules. SQL token controls must include every forbidden token, genuine docstrings versus branch/list strings, case sensitivity, SET whitespace/word boundary/anchor. Dangling symlinks are existing paths despite Path.exists returning False.

- 4.2: real DuckDB error-subclass classification with all prescribed stems, exact original messages/causes and optional lock-holder PID. Shared facade-only hold_index and storage-version forger helpers are available for later tasks; consume them unchanged. Tests-first and OFF/ON/removed outputs retained. Independent review round2 APPROVED: 22 claimed observations plus two new reviewer mutations produced named assertion failures and restored passes; full docs/source-enabled suite 9127 passed / two expected actionlint skips; canonical/scoped mypy and repository Ruff clean. Parent fresh completion gate 104 passed.
- 4.2 helper learnings: a failed startup may exit naturally, so no-live-child alone cannot pin explicit cleanup. Record cleanup calls on the exact captured Popen object, force-reap it before assertions, and inspect literal timeout arguments without waiting for hangs. Exercise both reap waits by making the first raise TimeoutExpired. Preserve None for a lock message without PID. The Corrupt database file stem is reached by the flipped-block fixture, not the junk fixture.

- 4.3: store write-side schema/comments, typed JSON-columnar insert, scoped deletes/replacement, transactions, bookkeeping I/O and checkpoint APIs available. Tests-first missing-API and OFF13/ON75/removed75 outputs saved. Independent review round2 APPROVED: 60 distinct claimed observations plus two new reviewer probes confirmed, equivalent variants excluded; full docs/source-enabled suite 9157 passed / two expected actionlint skips, canonical/scoped mypy and repository Ruff clean. Parent fresh completion gate 134 passed. Final source unchanged by test remediation; CREATE/INSERT constant reachability added to boundary guard.
- 4.3 fixture learnings: aware timestamps require valid scope/key preconditions; distinguish NULL array/empty tuple, False/True and numeric zero/None across scopes. Pin actual SQL types and complete comments through a fresh read-only connection, with multiple tables. Observe every computed state before overwrite, vary metadata versions and nullable fields, and assert complete producer registration rows. Keep matching corpus/bookkeeping rows present before per-page deletion. Record one multi-row INSERT with independent JSON arrays/parameters. Transaction tests cover BaseException and rollback errors preserving original identity. DuckDB from_json structure uses arrays of type strings for column arrays, nested for VARCHAR[]; max_depth=1 preserves list values.
