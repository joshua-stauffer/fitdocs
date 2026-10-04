# Research & Design Decisions: analytics-index

## Summary
- **Feature**: `analytics-index`
- **Discovery Scope**: Complex Integration. A new package, a new runtime
  dependency, a post-pass wired into four CLI paths and fed by the sync engine,
  plus amendments to four existing specs.
- **Method**: The full discovery process. Five read-only research subagents
  (Explore) surveyed the codebase in parallel: the sync hand-over, the CLI and
  the load pass, the guards and test pins, the model, metrics and load types,
  and the corpus engines `analytics-derived` will call. Seven DuckDB probes ran
  in throwaway venvs under the session scratchpad (duckdb 1.5.6 and 1.1.3,
  Python 3.11, macOS arm64). One source check ran against DuckDB's GitHub
  source. No research step was downgraded.
- **Key Findings**:
  - **A crashed writer's WAL is silently replayed onto a swapped-in rebuild
    (P4).** After `os.replace` of a fresh file over an index whose `.wal` was
    left by a `kill -9`, opening the index showed the old WAL's rows and a table
    that existed only in the WAL. So a rebuild must remove `<index>.wal` before
    the swap, while holding a fitdocs-level writer lock (Decision 7).
  - **Fetching a `TIMESTAMPTZ` value into Python needs `pytz`**, which is not a
    dependency (P1: `InvalidInputException: Required module 'pytz' failed to
    import`). Every instant is therefore a naive `TIMESTAMP`, with UTC or local
    stated in its comment (Decision 9).
  - **The `>=1.1` floor runs the whole writer recipe** (P6, duckdb 1.1.3):
    - the locked config with `lock_configuration`;
    - `storage_compatibility_version='v1.0.0'`;
    - `COMMENT ON`;
    - JSON-columnar insert with NULLs, ISO timestamps, dates, booleans and lists.

    Both versions write storage version 64, which every 1.x client reads. The
    open-error message stems are identical across 1.1.3 and 1.5.6 (P2, P7).
  - **The per-page fingerprint has to come in two tiers** (Decision 3). A single
    page-bytes fingerprint would make `fitdocs load --recompute` recompute every
    page's per-second rows: about 20+ minutes on the real corpus. It would also
    make a hand-edited effort tag pull current-profile metrics into a page whose
    document predates the profile. Two tiers fix both:
    - document values, which follow every byte change;
    - computed values, which follow only the page's rendering.
  - **A page key that survives a rename** is the content hash of the page's base
    file, which is the last listed `sources` ref. `uuid` is absent on many pages
    and can appear later. Paths change on rename and settle moves. Membership is
    permanent (`docs/ownership-contract.md:538-539`).

## Research Log

### Sync hand-over (`sync.py`)
- **Context**: Requirement 7.5: pages a run wrote must not be parsed twice.
- **Sources**: `src/fitdocs/sync.py:1708-1720` (`_TaskResult`), `:1781-1793`
  (`_page_task`), `:1896-2045` (write), `:2119-2207` (settle pass),
  `:2211-2220` (`_render_activity`), `:2223-2255` (`_write_outputs`),
  `:378-439` (`SyncReport`), `:533`, `:719`, `:1055` (the `sync`/`drain`/`regen`
  entries); `src/fitdocs/compose/types.py:49-81`.
- **Findings**:
  - **What `_page_task` holds and returns.**
    - It holds `composition`, `metrics = compute_metrics(...)`, `roles:
      PageRoles` and `athlete` as locals, and `_TaskResult` drops them.
    - Page tasks run serially. No ProcessPool, ThreadPool or asyncio exists
      anywhere in `src/fitdocs`, so nothing crosses a process boundary.
      `Activity.developer_fields` is a `MappingProxyType`, which is not
      picklable.
  - **Two early returns write nothing.** The version gate, and the settle stem
    mismatch, which returns a non-`None` `doc_ref` without writing. So the
    hand-over must fire only after `_write_outputs` returns.
  - **The settle pass can render one page twice in a run**, and may move it
    afterwards (`moved`, sync.py:2200-2207). A hand-over keyed by path would go
    stale; the base content hash would not.
  - **The page's frontmatter `sources` is `roles.sources`**: ascending rank,
    base last.
- **Implications**:
  - The hand-over is a keyword-only callback, `on_rendered`, threaded from
    `sync`, `drain` and `regen` to `_page_task`. It fires after
    `_write_outputs`. It carries the composed activity, metrics, provenance,
    `sources` and athlete inputs.
  - The consumer bounds retained samples (Decision 5).

### Re-deriving a page not written in this run
- **Sources**: `load/engine.py:458-477` (the load pass recipe), `:628-660`
  (`_resolve_archive`: the last ref must resolve to an existing archive file);
  `compose/archive.py:20-40` (`compose_listed`: extras = `refs[:-1]` reversed;
  it skips non-archive refs, duplicate shas and missing extras, and propagates
  read and decode errors); `ingest/__init__.py:42` (`parse_fit`, raising
  `FitDecodeError`); `metrics/__init__.py:64` (`compute_metrics`);
  `athlete.py:94` (`load_athlete_inputs`).
- **Findings**:
  - There is no public "re-derive a page" helper; the recipe is spelled out in
    the load pass.
  - Regen picks the base differently (the last *resolvable* ref,
    sync.py:2351-2378).
  - `compose_listed` ranks by the recorded order. Sync ranks by the current
    precedence and writes that order, so the two agree for pages written by this
    fitdocs.
- **Implications**: The index re-derives exactly as the load pass does
  (Requirement 5.4). Failures classify as source missing (the last ref does not
  resolve), unreadable (`OSError`) or undecodable (`FitDecodeError`).

### Page identity and keys
- **Sources**:
  - `render/frontmatter.py:90-165`, which emits the keys in order;
  - `contract.py:485-509` (`MANAGED_KEYS`), `:463-467` (`LOAD_KEYS`), `:524-553`
    (the user-owned effort keys), `:1245-1280` (`source_refs`, `sha_of_ref`),
    `:961` (`is_workout_document`), `:815-830` (the region ids: `notes`,
    `workout`, `load`);
  - `identity/roles.py:134-176`;
  - `docs/ownership-contract.md:480-483`, `:538-539`, `:710-723`.
- **Findings**:
  - `uuid` is written only when a file recorded one, and a page can gain one
    later.
  - The base sha changes when a higher-ranked file joins.
  - The filename changes on base change, on settle moves and on user renames.
  - Every listed ref belongs to exactly one page, forever.
  - `_stranded_pages` already uses "uuid else the base sha" as a run-local uid
    (sync.py:2094-2096).
- **Implications**: The key is the base sha (Decision 4). Changing the base
  re-keys the page; that is a re-render anyway.

### The load region and quality flags
- **Sources**:
  - `load/render.py:63` (`LOAD_PAYLOAD_VERSION = 2`), `:81-94` (`LoadPayload`),
    `:112-145` (`encode_payload`), `:162` (`parse_payload`; the brief's `:63`
    is the version constant);
  - `load/docedit.py:104-139`, `:156` (`classify_load_region`);
  - `load/types.py:130-202`;
  - `load/qa/types.py:41-66`;
  - `threshold/selection.py:78-140`.
- **Findings**:
  - Persisted per-channel loads are the result's `value`/`basis` plus
    `non_selected` (`key` = channel id, `value` or `None`). `ChannelLoad`
    detail (intensity, coverage) survives only as display strings in
    `inputs_used`.
  - Quality flags exist only inside a computed payload: four flags, each with a
    verdict.
  - Region states are PLACEHOLDER, COMPUTED, UNSUPPORTED, SUPERSEDED and
    FOREIGN.
- **Implications**:
  - `loads` holds one row for `basis` plus one per `non_selected` entry.
  - `quality_flags` holds one row per flag.
  - `pages.load_status` maps the region states to computed, unsupported,
    not_computed and unreadable.

### The CLI and passes
- **Sources**:
  - `cli.py:377-546` (sync and drain), `:594-667` (regen and load),
    `:1498-1574` (the load and plan passes), `:1589-1601` (`_today`),
    `:1604-1626` (data root, athlete), `:1723-1733` (`_config_error`),
    `:2343-2350` (`_finish`), `:244-249` (exit codes);
  - `tests/test_cli_skill.py:262-270` (pins 11 commands plus "Eleven" in the
    docstring);
  - `tests/test_cli_reconcile.py:196, 238, 286` (output byte-identity between
    two runs).
- **Findings**:
  - No command has a "report and continue" post-pass: chained passes hard-exit
    2 on configuration errors.
  - No progress reporting exists. Reporters are per-type rich Consoles on
    stdout, and errors go to stderr.
  - `load` runs no plan pass.
  - `pull --sync` reuses `_run_drain_passes`.
- **Implications**:
  - The index pass is the first post-pass that never changes the exit code. It
    runs after the plan pass, and in `load` after the load pass, before plugin
    errors.
  - Progress goes to stderr.

### Guards and pins the dependency touches
- **Sources**:
  - `tests/test_determinism.py:666-715` (baseline five strings; `optional-dependencies == {}`);
  - `tests/test_packaging.py:503-519` (the exact ordered list; the roadmap's
    `501-516` is off by two), `:1036-1090` (offline scratch venv, "five runtime
    dependencies");
  - `tests/test_preserved_guarantees.py:93-108` together with
    `tests/fixtures/pre_distribution_e74af37.py:19-39`. **This third pin is
    missing from the roadmap and the brief**;
  - `pyproject.toml:25-31` and `:103-193` (the curated mypy `files`);
  - `uv.lock`.
- **Findings**: The vendored snapshot says "re-vendor explicitly, do not
  silently edit".
- **Implications**: The snapshot stays as the pre-feature truth. The pin
  asserts `snapshot + ["duckdb>=1.1,<2"]` and names the deliberate delta.

### Confinement, isolation and the network guards
- **Sources**:
  - `tests/test_confinement.py:155-200` (permitted = owned ∪ shared ∪
    configured, all under the data root), `:1002-1151` (`EntryPoint`,
    `WRITING_ENTRY_POINTS`, the guard snapshots only `tmp_path`), `:1738-1801`
    (`connect` writes outside the data root: the template);
  - `tests/test_inbox_e2e.py:60-137` (snapshots the data root only);
  - `conftest.py` and `tests/conftest.py`, which have no HOME or XDG isolation;
  - `tests/connectors/conftest.py:61-103` (isolates `XDG_CONFIG_HOME` and HOME,
    not `XDG_CACHE_HOME`);
  - `tests/connectors/test_e2e.py:203-244` (offline list; `--out`; output
    compared with roots substituted);
  - `tests/connectors/test_boundary.py:522-630` (the tree-wide AST allow-list
    template, with positive controls);
  - `tests/performance/test_single_writer.py:100-213`;
  - `tests/test_model.py:64-77` (the subprocess `sys.modules` pattern).
- **Findings**:
  - Every in-process CLI test outside `tests/connectors` runs against the real
    HOME. A post-pass with no isolation would write into a developer's real
    `~/.cache`.
- **Implications**:
  - A suite-wide autouse fixture points `FITDOCS_INDEX_DIR` at a per-test
    temporary directory.
  - The confinement guard gains the index directory inside its sandbox.
  - The offline e2e test must also substitute the index location in its output
    comparison.

### The credentials precedent for a per-user location
- **Sources**: `connectors/credentials.py:62-128` and its tests
  (`tests/connectors/test_credentials.py:115-260`).
- **Findings**:
  - Location order: a dedicated absolute env var (a relative value raises),
    then XDG (a relative XDG value is skipped), then the home default.
  - Refusal uses `resolve()` and `is_relative_to`. The error subclasses
    `SettingsError`, giving exit 2.
- **Implications**: `fitdocs.index.location` mirrors it, with a per-data-root
  subdirectory added.

### The corpus engines the derived producers will call
- **Sources**:
  - history: `history/engine.py:288-357` (`run_history`, which scans
    `workouts/*.md` itself via `history/documents.py:178`),
    `history/series.py:399` (`build_daily_series`, pure);
  - profile: `load/profile.py:448` (`load_profile`), `benchmarks.py:125-245`;
  - plans: `plans/reconcile.py:195` (`run_reconcile(data_root, *, today)`),
    `plans/matching.py:222-225` (NOT_LOGGED or UPCOMING depends on `today`),
    `plans/settings.py:133`;
  - shared scans: none. Each pass rescans; `docio.read_frontmatter` is the
    shared read.
- **Implications for the seam**:
  - The corpus snapshot carries `today`, supplied by the CLI's `_today()`, so a
    plan producer can fingerprint it.
  - It also carries the scanned frontmatter of every page, so fingerprints are
    cheap without a second scan.
  - Producers may read data-root files themselves, read-only, and must
    fingerprint everything they read.

### Model and metrics shapes
- **Sources**:
  - `model.py:67-330`: `Samples` is columnar tuples, with `time_s` as an offset
    from `start_time`; 12 dynamics channels, `DYNAMICS_CHANNELS` at :106-119;
    `Lap` with inclusive sample indices; `StrengthSet`;
  - `metrics/types.py:97-164` (`DerivedMetrics`, `AthleteInputs`, `ZoneSpec`);
  - `metrics/zones.py:47-75`.
- **Findings**:
  - No sample carries an absolute timestamp; it is `start_time + time_s`.
  - Zone bounds live in `AthleteInputs`, not in `DerivedMetrics`.
  - Non-finite values are possible: `ftp_watts = nan` in `athlete.toml` passes
    the `<= 0` guard (athlete.py:130-139), giving NaN IF and TSS. A `-inf`/`+inf`
    edge exists too.
- **Implications**:
  - Records compute `time_utc` from those two values.
  - Zone rows carry their bounds from the athlete inputs.
  - The store maps non-finite values to NULL.

## DuckDB probes (scratchpad, never in the worktree)

All connections used `enable_external_access=false`,
`autoinstall_known_extensions=false` and `autoload_known_extensions=false`. No
statement attached `md:`, called `start_ui`, or named a URL except one refused
`read_csv('https://example.invalid/…')`. **Disclosure:** P6 issued `INSTALL
httpfs` under the locked config:
- On 1.5.6 the configuration refused it (`PermissionException`).
- On 1.1.3 it was **not** refused by the configuration. It failed only because
  HOME pointed at a nonexistent directory (`Can't find the home directory`), so
  no download happened.

The writer never issues `INSTALL`. `analytics-query`, which runs arbitrary SQL,
must not rely on the configuration refusing `INSTALL` on the floor version (see
Risks).

| # | Probe | Result |
|---|---|---|
| P1 | Locked writer on 1.5.6: JSON-columnar insert, comments, settings, extensions | `core_functions`, `icu`, `json` and `parquet` are statically linked. Inserts round-trip NULLs and lists exactly. Comments are readable from `duckdb_columns()` on a read-only, `lock_configuration` connection. `SET enable_external_access=true` is refused even without `lock_configuration`, but `SET autoinstall_known_extensions=true` is allowed without it. `temp_directory` defaults to `<db>.tmp`. Fetching a `TIMESTAMPTZ` needs `pytz` and fails. `duckdb_extensions()` errors when external access is off. |
| P2 | Open-error texts on 1.5.6 | lock: `Could not set lock on file "…": Conflicting lock is held in <exe> (PID n) by user u…` (RW after RO adds `However, you would be able to open this database in read-only mode`). A missing file opened RO gives `Cannot open database "…" in read-only mode: database does not exist`; a missing directory gives `Cannot open file "…": No such file or directory`. Junk or empty files give `…exists, but it is not a valid DuckDB database file!`. A flipped block gives `Corrupt database file: computed checksum … does not match stored checksum … in block at location N`. A truncated file gives `Could not read enough bytes from file …`. All are `duckdb.IOException`. |
| P3 | A forged storage version (header bytes 12–20, the checksum recomputed over bytes 8–4096 with DuckDB's `5381 ^= x*0xbf58476d1ce4e5b9` per uint64) | 69 gives `Trying to read a database file with version number 69, but we can only read versions between 64 and 68. The database file was created with a newer version of DuckDB.` Patching without the checksum gives "Corrupt database file". The forged recipe lets tests produce a genuine version mismatch without a 2.x install. |
| P4 | A WAL from `kill -9`, then a rebuild file `os.replace`d over the index | **Foreign WAL replayed**: the new file showed the old WAL's row and its WAL-only table. |
| P5 | Opening RW, reading and closing, then RO the same, then an empty `DELETE` in a transaction | The file stays byte-identical: size, mtime_ns and sha256. So "a refresh that changes nothing writes nothing" holds with an RW open. |
| P6 | The writer recipe on 1.1.3 and on 1.5.6, under a fake HOME | Both accept `storage_compatibility_version='v1.0.0'` and `lock_configuration`. JSON insert with ISO `TIMESTAMP`, `DATE`, `BOOLEAN` and `VARCHAR[]` works. Header version is 64. `read_csv` of a local file or a URL is refused. Nothing is created under HOME. |
| P7 | P2 and P3 on 1.1.3 | The same stems. Version text: `…but we can only read version 64. The database file was created with an newer version…`. The exception module path differs (`duckdb.duckdb` against `_duckdb`), so the classifier matches class `duckdb.IOException` and message stems, never module paths. |

Source check (DuckDB `src/common/local_file_system.cpp`, main branch): on
Windows, DuckDB opens database files with `FILE_SHARE_DELETE` added to every
share mode, and locks through share modes rather than `LockFileEx`. Whether
`os.replace` over a file another process holds open succeeds then depends on
the Windows build and file system (POSIX rename semantics). It is not
verifiable here: CI is Ubuntu-only (`.github/workflows/ci.yml:41`) and fitdocs
claims no Windows support. Hence the staged-rebuild fallback (Requirement
10.7).

## Architecture Pattern Evaluation

| Option | Description | Strengths | Risks / Limitations | Verdict |
|---|---|---|---|---|
| Reconciling projection (chosen at discovery) | One post-pass diffs the corpus against recorded fingerprints | Sees hand edits and every writer; self-healing; one path for intake and backfill | A scan per writing command (~1.5 s at 2,500 pages) | Adopted (maintainer) |
| Inline write hooks | Rows inserted at each of the five write sites | No scan | Misses hand edits; five sites across four specs; needs a separate backfill | Rejected at discovery |
| Refresh on query | Index brought current lazily | Intake untouched | First query pays all; outside clients see stale data | Rejected at discovery |
| Ports and adapters inside the index | Pure row extraction, a single store adapter owning SQL and `duckdb`, an orchestrating pass | Store swappable in tests; the duckdb import confined by construction | One more interface layer | Adopted for the internal structure |

## Design Decisions

### Decision 1: One connection module is the only importer of `duckdb`, and it exposes a small typed facade
- **Context**: The roadmap constraint is that only the index store module
  imports `duckdb`, pinned by a boundary test. `analytics-query` must still open
  the index read-only, run arbitrary statements, interrupt them and tell lock
  errors apart.
- **Alternatives**:
  1. Allow-list a second importer (query's sandbox module).
  2. Have the store expose a facade, `IndexConnection` (execute, fetch,
     description, interrupt, close), plus classified fitdocs exceptions.
- **Selected**: Option 2. `fitdocs.index.store` imports `duckdb` lazily, inside
  its open function, and under `TYPE_CHECKING`. It applies the mandatory
  settings to every connection and refuses any caller setting that would
  override one. Query passes its additional sandbox settings (memory limit,
  threads) and owns timer, retry, formatting and freshness.
- **Trade-offs**: Query cannot reach DuckDB-specific APIs not on the facade.
  Anything it needs is a facade addition, an append to the store.
- **Follow-up**: Query's design names which facade methods it uses. A new one is
  an append-only store change made by query.

### Decision 2: Producers are the only way tables are made, and the core tables are producers
- **Context**: `analytics-derived` must add four producers without touching the
  pass.
- **Generalization**: The core tables and the derived tables are the same thing,
  so one seam carries both. The pass knows producer protocols and table specs,
  never table names.
- **Selected**:
  - Three protocols: `DocumentProducer` and `ComputedProducer` (per page, by
    tier) and `CorpusProducer`.
  - One registry module with append-only tuples.
  - Each producer declares `TableSpec`s: name, description, and ordered
    `ColumnSpec`s (name, type, description).
  - For per-page tables the store prepends `page_key`. Producers return rows as
    tuples in declared order, keyed by table name.
- **Trade-offs**: Rows are tuples, not mappings: cheaper and order-checked
  against the spec at insert. A wrong tuple length fails the page, not silently.

### Decision 3: Two fingerprints per page (document and rendering) and the stale-document rule
- **Context**: Requirement 5. `athlete.toml` changes alter IF, TSS, TRIMP and
  zone times; documents change only on `regen`. Effort tags and load regions
  change bytes without changing the rendering.
- **Alternatives**:
  1. One fingerprint (page bytes); every change recomputes everything.
  2. Two tiers: document values follow `document_fingerprint` (sha256 of the
     path and the bytes); computed values follow `render_fingerprint` (sha256 of
     managed frontmatter minus the load keys, plus the body with the `notes`,
     `workout` and `load` region contents excised).
- **Selected**: Option 2. A hand-edited tag, a load rewrite, a notes edit or a
  rename updates only document-tier tables. That is no parse, and no
  current-profile metric is pulled into a page whose document predates the
  profile. A regen whose output changed recomputes computed values, handed over
  from that regen.
- **Rule as stated** (Requirement 5):
  - The index agrees with the documents.
  - Computed rows record the athlete-input fingerprint they were computed under;
    `index_meta` records the current one.
  - An athlete-input change alone moves no row.
  - A build computes every page under the current inputs, and the contract says
    so.
  - `analytics-derived`'s mean-max is a computed-tier producer and inherits the
    rule unchanged.
- **Trade-offs**: A regen that renders byte-identically under changed inputs
  (inputs affecting no rendered value) does not recompute. The athlete-input
  fingerprint shows it.

### Decision 4: The page key is the base file's content hash
- **Alternatives**: the path (changes on rename); `uuid` (absent on many pages
  and can appear later); "uuid else base sha" (changes when a phone copy joins);
  the base sha.
- **Selected**: the base sha, the 64-hex sha256 named by the last listed
  `sources` ref.
  - A page whose last ref is not an archive ref has no key. It is left out and
    reported.
  - Two pages listing the same base: the first by path is indexed and the other
    is reported.
- **Trade-offs**: A base change re-keys the page (remove plus add). It
  coincides with a re-render, so no extra parse.

### Decision 5: The hand-over is a bounded callback, not a report field
- **Context**: A 2,478-file drain cannot retain every composed activity: Python
  tuples of floats cost about 350 bytes per sample.
- **Selected**: `on_rendered: Callable[[RenderedPage], None] | None`.
  - It is threaded through the sync engine and called after `_write_outputs`.
  - The index's `HandoffCollector` keeps entries until `HANDOFF_SAMPLE_BUDGET =
    250_000` samples (about 69 h at 1 Hz, roughly 90 MB worst case) and drops
    later ones, which are then re-derived.
  - A second render of a page (the settle pass) replaces its entry.
  - An entry is used only when its `sources` equal the page's recorded
    `sources`.
- **Trade-offs**: Big drains re-derive the overflow. Rows are identical either
  way (pinned by the determinism test).

### Decision 6: No automatic build
- **Context**: The roadmap's literal rule.
- **Considered**: Building an absent index automatically when every workout page
  is in this run's hand-over (a brand-new data root's first sync), at no
  backfill cost.
- **Rejected for this spec**: The roadmap says an absent index is reported, and
  the variant would be a second build path. It is noted as a follow-up
  candidate.

### Decision 7: A fitdocs writer lock plus WAL removal makes the rebuild swap safe
- **Context**: P4 (a foreign WAL replayed). DuckDB's own lock cannot be taken on
  a corrupt or version-mismatched file, and the brief rejects stale lock
  markers.
- **Selected**:
  - The lock is an OS advisory lock on `<index dir>/index.lock`:
    `fcntl.flock(LOCK_EX|LOCK_NB)`, or `msvcrt.locking(LK_NBLCK)` on Windows.
  - Every fitdocs index writer takes it: the refresh, the build and the swap.
    The OS releases it at process end, so the file's presence means nothing.
  - Under it, a build writes `index.duckdb.building`, checkpoints and closes it,
    removes `index.duckdb.wal` if present, then `os.replace`s it onto
    `index.duckdb`.
  - If the replace raises `PermissionError`, the build is renamed to
    `index.duckdb.rebuilt` and the next `fitdocs index` completes the swap
    first.
- **Trade-offs**: An outside client that opens the file read-write and crashes
  could leave a WAL that a later rebuild discards. That is acceptable: the
  documented access is read-only, and the rebuild recomputes everything anyway.

### Decision 8: The connection settings
- **Mandatory on every connection**, refused if a caller tries to override:
  - `autoinstall_known_extensions=false`, `autoload_known_extensions=false`;
  - `allow_community_extensions=false`, `allow_persistent_secrets=false`;
  - `enable_external_access=false`, `python_enable_replacements=false`;
  - `lock_configuration=true`.
- **Writer-only**: `storage_compatibility_version='v1.0.0'` (Requirement 11.4).
  P6 confirms the default today is 64, and the explicit setting keeps it 64 if a
  later 1.x changes its default.
- **Not set**: `disabled_filesystems` (it breaks spilling), and memory and
  thread limits for the writer (the default memory limit is 80% of RAM).

### Decision 9: Column types
- **Allowed**: `VARCHAR`, `BOOLEAN`, `INTEGER`, `BIGINT`, `DOUBLE`, `DATE`,
  `TIMESTAMP` (naive) and `VARCHAR[]`.
- **Not allowed**: `TIMESTAMPTZ`. Python fetch needs `pytz`, and its semantics
  depend on the session `TimeZone`.
- UTC columns are suffixed `_utc` and local columns `_local`, and each column's
  comment says which.

### Decision 10: The schema version and the digest
- `fitdocs.index.schema.SCHEMA_VERSION = 1`.
- A test holds an append-only map `{version: digest}` of the canonical schema
  manifest: table names, column names, types and order, excluding comments.
- Changing the schema without advancing the version fails, and so does
  advancing without a digest.
- A comment change is not a schema change: the pass reapplies comments when the
  recorded fitdocs version differs.

## Synthesis outcomes
- **Generalization**:
  - Core and derived tables share one producer seam (Decision 2).
  - The two-tier page producers (Decision 3) generalize three separate brief
    items: hand-edited effort tags, the load pass's rewrites, and the
    stale-document rule.
  - Error classification is one function for both write and read sides.
- **Build vs adopt**:
  - DuckDB (decided).
  - The JSON-columnar insert route (measured at about 186k rows/s, needs no
    numpy, pandas or pyarrow).
  - The stdlib `fcntl`/`msvcrt` advisory lock, rather than a lock-file
    protocol.
  - `hashlib` for fingerprints.
  - No new dependency beyond `duckdb`.
- **Simplification**:
  - No migrations: any schema version difference means rebuild.
  - No primary keys, unique constraints or ART indexes.
  - No clock values in rows.
  - The page is the unit of change, with no row-level diffing.
  - The CLI reporter lives in `cli.py` beside the others.
  - No separate "core" code path.
  - A missing-source page is a recorded state, not an error.

## Risks & Mitigations
- **The `duckdb>=1.1` floor and `INSTALL`.** The writer never issues
  `INSTALL`/`LOAD`, so the index is unaffected. For `analytics-query`, which
  runs arbitrary SQL, the floor (1.1.3) did not refuse `INSTALL httpfs` by
  configuration (P6 disclosure).
  - Mitigation inside this spec: the store's policy test pins `INSTALL`
    refusal on the locked version, and a floor-verification task runs the
    store's policy and classifier tests on 1.1.x in a scratch venv with no
    network and a nonexistent HOME.
  - Raised to the controller for `analytics-query`, which either verifies the
    floor or proposes raising it. The roadmap's stated reason for `>=1.1`,
    1.x-client readability, rests on the written storage version (64), not on
    the installed library's floor.
- **CI's offline install.** The scratch-venv test installs dependencies
  `--offline`, so the uv cache must hold the duckdb wheel. The distribution spec
  met three CI-runner-only failure classes. Mitigation: the dependency task runs
  the packaging tests in CI mode locally and warms the cache as the existing
  tests do.
- **A ~1.5 s scan per writing command** at 2,500 pages (the read and hash of
  every page). Accepted, and stated in the contract. The scan's frontmatter
  doubles as the corpus snapshot, so corpus producers can fingerprint without
  rescanning.
- **Swapping the index over an open file on Windows** is untested. It falls
  back to a staged rebuild, completed by the next `fitdocs index`
  (Requirement 10.7).
- **Output churn in existing tests.** Every sync prints "index not built" when
  isolated. The isolation fixture makes that deterministic, and the tasks name
  the output-pinning tests to update.

## References
- DuckDB concurrency: https://duckdb.org/docs/stable/connect/concurrency
- DuckDB storage versions: https://duckdb.org/internals/storage
- DuckDB `local_file_system.cpp` (Windows share modes): https://github.com/duckdb/duckdb/blob/main/src/common/local_file_system.cpp
- The roadmap's Phase 10 section: `.kiro/steering/roadmap.md:2030-2334`
- The sibling briefs: `.kiro/specs/analytics-query/brief.md`, `.kiro/specs/analytics-derived/brief.md`
