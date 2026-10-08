# Research & Design Decisions: analytics-query

## Summary
- **Feature**: `analytics-query`
- **Discovery Scope**: Complex Integration. A new read-only command runs untrusted
  SQL against the `analytics-index` file. It also adds a third packaged agent
  skill, a docs page held to the live schema, and entries in five shared
  registries (CLI command count, no-network list, confinement, packaged skills,
  index importers).
- **Method**: The full discovery process.
  - Three read-only research subagents (Explore) surveyed the codebase in
    parallel:
    - the packaged-skill machinery and its pins;
    - the CLI conventions and the guard lists;
    - the docs tree and its "doc held to code" patterns.
  - About fifteen DuckDB probes ran in throwaway venvs under the session
    scratchpad, on Python 3.11, macOS arm64, across twelve releases (1.1.0,
    1.1.1, 1.1.2, 1.1.3, 1.2.0, 1.2.1, 1.2.2, 1.3.2, 1.4.0, 1.4.5, 1.5.0,
    1.5.6).
  - Every probe that could reach the network ran under `sandbox-exec -p
    '(version 1)(allow default)(deny network*)'`, with HOME pointed at a fresh
    scratch directory. The sandbox was first verified to block: `urlopen` of
    `https://example.com` succeeds unsandboxed and fails sandboxed.
  - No probe attached `md:` or called `start_ui`. `start_ui`'s absence was
    checked through `duckdb_functions()` only.
  - One WebFetch read DuckDB's "Securing DuckDB" page.
  - No research step was downgraded.
- **Key Findings**:
  - **The floor is 1.2.0.** On every 1.1.x release, `INSTALL httpfs` under the
    locked configuration is refused by configuration only after DuckDB has
    created `~/.duckdb/extensions/v1.1.x/<platform>` in HOME. That is a write
    outside the index, on the query path. From 1.2.0 on, every statement in the
    escape set is refused and nothing is created anywhere.
    - The wave-1 probe P6 ran with HOME pointing at a nonexistent directory. On
      1.1.3 that made `INSTALL` fail on the missing home before the
      configuration check, which hid both the refusal and the directory
      creation.
  - **A multi-statement string can abort the process on 1.4 and later.**
    `CALL enable_logging(storage='file', storage_path=…); SELECT 42` on one
    connection ends in `libc++abi: terminating due to uncaught exception of type
    duckdb::PermissionException` (exit 134). The same `enable_logging` call as
    the only statement on its connection is harmless: no file and no crash.
    `query` therefore runs exactly one statement per connection.
  - **`enable_logging` slips past `lock_configuration` on 1.4 and later.** It
    changes the logging configuration through a function call. File storage
    is still refused by `enable_external_access`.
  - **Concurrent read-only spills collide.** Four read-only processes spilling
    into the default `<db>.tmp` all failed on 1.2.0 and 1.5.6. The errors were
    `Cannot open file …duckdb_temp_block…`, `Corrupt temporary file` and
    `Could not read enough bytes`, and one process aborted with -6. Each process
    given its own `temp_directory`, set at connect, returned the correct result.
    Each directory was removed on close.
  - **Execution streams.** `execute` returns at once, and the work and its
    errors happen during `fetchmany`. This holds for interrupts, permission
    errors and `pytz`. A row cap of `fetchmany(cap + 1)` is therefore cheap.
    Every DuckDB error, the interrupt included, can surface at fetch.

## Research Log

### The escape matrix: which release refuses what
- **Context**:
  - Requirement 5.
  - The controller's floor question: wave-1's P6 reported that 1.1.3 did not
    refuse `INSTALL httpfs` by configuration.
- **Method**:
  - `probe_escape.py` opens a fixture database read-only with the brief's locked
    configuration. It runs 62 statements, each on a fresh connection.
  - It records the outcome, plus every file created in the work directory or
    in HOME.
  - It ran on twelve releases with an existing, empty HOME. On 1.2.0 and 1.5.6
    it also ran once per dropped setting, with HOME missing (the mutation
    matrix below).
- **Findings**: these are the escape-set rows.
  - `PERM` is `PermissionException`.
  - `LOCK` is `InvalidInputException: … the configuration has been locked`.
  - `+HOME` means a directory was created under HOME.

  | Statement | 1.1.0–1.1.3 | 1.2.0–1.3.2 | 1.4.0–1.5.6 |
  |---|---|---|---|
  | `read_csv('/etc/passwd')`, `read_text`, `read_blob`, `read_json_objects`, `glob`, `sniff_csv`, `read_parquet`, relative `read_csv` | PERM | PERM | PERM |
  | `FROM '/etc/hosts'` (path as table) | Catalog error, no read | same | same |
  | `COPY (…) TO file`, `COPY … TO '/dev/stdout'`, `EXPORT DATABASE`, `IMPORT DATABASE`, `COPY … FROM` | PERM | PERM | PERM |
  | `EXPLAIN ANALYZE COPY … TO` | n/a | PERM, no file (1.2.0) | PERM, no file |
  | `ATTACH '<local file>'`, `ATTACH … (TYPE SQLITE)` | PERM | PERM | PERM |
  | `ATTACH ':memory:'` | refused: read-only | same | same |
  | `ATTACH 'https://…'` | "requires extension httpfs" | same, or PERM | same |
  | `INSTALL httpfs`, `FORCE INSTALL … FROM 'http://…'`, `INSTALL '<local path>'` | **PERM +HOME** | PERM | PERM |
  | `LOAD httpfs`, `LOAD '<local path>'` | PERM | PERM | PERM |
  | `SET`/`RESET`/`SET GLOBAL`/`PRAGMA threads=` of any option, including `temp_directory`, `log_query_path`, `profiling_output`, `disabled_filesystems` | LOCK | LOCK | LOCK |
  | `CREATE SECRET (TYPE S3 …)` | refused: type needs httpfs | same | same |
  | `getenv('HOME')` | function absent | same | same |
  | `read_csv('https://example.invalid/…')` | PERM | PERM | PERM |
  | `CREATE TABLE` / `CREATE VIEW` | refused: read-only | same | same |
  | `CREATE TEMP TABLE`, `TEMP MACRO`, `SET VARIABLE`, `SET search_path`, `USE` | allowed | allowed | allowed |
  | `CALL enable_logging(storage='file', …)` | function absent | absent | **allowed: lock bypass; a later statement aborts** |
  | `duckdb_extensions()` | readable | PERM | PERM |
  | `start_ui` in `duckdb_functions()` | absent | absent | absent |
  | Python replacement scan of an outside relation | Catalog error | same | same |
  | `SELECT now()` fetch | fetch error: `Required module 'pytz'` | same | same |

- **Implications**:
  - The configuration alone refuses the whole escape set from 1.2.0 on. Below
    1.2.0 it refuses, but only after writing into HOME.
  - On top of the configuration, `query` refuses every statement that is not
    a query or `EXPLAIN` before it runs (Decision 2). That keeps
    `CREATE TEMP`, `SET VARIABLE`, `USE` and `CALL enable_logging` out too.

### The mutation matrix: which setting does each refusal
- **Context**: Every pin must die on a named mutation that drops the setting
  (brief, Constraints).
- **Findings** (1.2.0 and 1.5.6, HOME missing, network blocked; each setting
  dropped in turn):
  - **`enable_external_access`** refuses every file and address class. With it
    dropped:
    - every read function succeeds;
    - `COPY TO` and `EXPORT` create their files;
    - `ATTACH` of a local file succeeds;
    - `INSTALL`/`LOAD` fail only on the missing HOME.
  - **`lock_configuration`** refuses `SET`/`RESET`/`PRAGMA` of a setting. With
    it dropped:
    - `SET autoinstall_known_extensions = true`, `SET memory_limit`,
      `RESET threads`, `SET disabled_filesystems` and `PRAGMA profiling_output`
      all succeed;
    - `SET enable_external_access = true` is still refused, because DuckDB
      forbids changing that setting on a running database.
  - **`autoinstall`, `autoload`, `allow_community_extensions`,
    `allow_persistent_secrets` and `python_enable_replacements`**: dropping one
    alone changes no escape-class outcome. `enable_external_access` masks each
    of them; the one exception is `CREATE SECRET` with autoload dropped, which
    then tries to autoload httpfs and is refused by external access.
- **Implications**:
  - The file, address and `COPY`/`EXPORT`/`ATTACH` pins die on dropping
    `enable_external_access`. The `SET` pin dies on dropping
    `lock_configuration`, and must use an option other than
    `enable_external_access`.
  - The five masked settings cannot be pinned through statement outcomes
    without enabling a network path. They are pinned by reading the
    configuration back (Decision 3).

### Runtime behaviour on the floor (1.2.0) and on the locked release (1.5.6)
- **Read-back.** `duckdb_settings()` values are identical on both releases:
  - booleans are `'false'`/`'true'`;
  - `threads` is `'2'`;
  - `memory_limit='1GB'` reads back as `'953.6 MiB'`;
  - `max_temp_directory_size='8MB'` reads back as `'7.6 MiB'`;
  - `temp_directory` defaults to `<db>.tmp`.
- **Statement extraction.** `extract_statements` exists from 1.1.3 on.
  - `''`, whitespace and comment-only text give 0 statements.
  - `SELECT 1;;` gives 1, and `SELECT 1; SELECT 2` gives 2.
  - A syntax error raises `ParserException`.
  - Statement types:
    - SELECT: `SELECT`, `WITH`, `FROM`, `VALUES`, `DESCRIBE`, `SHOW`,
      `SUMMARIZE`, `PRAGMA table_info(…)` and `PRAGMA version`;
    - EXPLAIN: `EXPLAIN …` and `EXPLAIN ANALYZE …`;
    - LOAD: `INSTALL` and `LOAD`;
    - SET: `SET`, `RESET`, `USE`, `SET VARIABLE` and `PRAGMA threads=…`;
    - CALL: `CALL …` and `CHECKPOINT`;
    - CREATE (`CREATE SECRET` included), ATTACH, DETACH, COPY, EXPORT and
      UPDATE are each their own type.
- **Interrupt.** `threading.Timer(1.0, con.interrupt)` stops
  `SELECT count(*) FROM range(10^12)` after 1.01 s with `InterruptException`.
  The connection stays usable afterwards.
- **Streaming.**
  - `execute('SELECT * FROM range(200000000)')` returns in under a
    millisecond.
  - `fetchmany(1001)` also takes under a millisecond.
- **Spill.**
  - With `memory_limit='64MB'`, a sorted group-by spills into `<db>.tmp/`
    (block files on 1.2.0, `duckdb_temp_storage_*.tmp` on 1.5.6). The
    directory is removed on `close()`.
  - After a `kill -9` mid-spill, the directory and its files remain. Neither a
    later read-only open nor a later read-write open removes them.
- **Spill-size cap.** `max_temp_directory_size` is accepted at connect, and is
  refused by `SET` under the lock on both releases.
  - Its enforcement could not be triggered at the probe's sizes: the queries
    finished, or hit `OutOfMemoryException` first on 1.5.6.
  - It is adopted on DuckDB's documentation ("Securing DuckDB": limit temporary
    storage). Its effect is not measured here.
- **Locks.**
  - Read-only open while another process holds the file read-write fails in
    2–3 ms with `IOException: Could not set lock on file "…": Conflicting lock
    is held in <exe> (PID n)`.
  - Read-only alongside read-only opens.
  - Read-write while a reader is open fails the same way.
- **Python types fetched.** The types are the same on both releases:
  - INTEGER and HUGEINT give `int`; DOUBLE gives `float`, including `nan` and
    `inf`; DECIMAL gives `Decimal`;
  - DATE, TIMESTAMP and TIME give `date`, naive `datetime` and `time`;
  - INTERVAL gives `timedelta`; BLOB gives `bytes`; UUID gives `uuid.UUID`;
  - LIST gives `list`; STRUCT and MAP give `dict`;
  - `1/0` gives `inf`.
  - `cursor.description` type codes are coarse on 1.2.0 (`NUMBER`, `STRING`,
    `DATETIME`) and full on 1.5.6 (`DECIMAL(10,2)`). So `query`'s output
    carries no per-column types (Decision 6).
- **Catalog.**
  - `duckdb_tables()` and `duckdb_columns()` read comments on a locked
    read-only connection on both releases.
  - `duckdb_columns()` filtered on `schema_name = 'main'` alone also returns
    system views, so the filter must add `database_name = current_database()`.
  - Temporary tables carry `database_name = 'temp'`.
  - A table or column with no comment gives `NULL`.

### Codebase: the CLI, the guards, the skill machinery and the docs (subagent summaries)
- **CLI** (`src/fitdocs/cli.py`):
  - The docstring opens with "Eleven commands are registered" (`:4-7`), and
    `analytics-index` makes it "Twelve".
  - The exit constants are `_EXIT_SUCCESS`/`_EXIT_FILE_FAILURES`/`_EXIT_CONFIG_ERROR`
    (`:244-249`).
  - `_config_error` is the only stderr console (`:1723-1733`).
  - Option singletons follow flake8 B008 (`:285-300`).
  - No command reads stdin as data, offers `--format`, or writes JSON.
  - `_stdin_is_interactive` (`:764-766`) is the TTY-detection precedent.
  - The connectors package's no-clock rule (`connectors/__init__.py:17-19`)
    injects `now`/`sleep`, and query follows it for its retry loop.
- **No-network list.** `tests/connectors/test_e2e.py:203-246` runs `[command,
  "--out", root]` per command, compares output with the roots substituted, and
  counts Python socket attempts. `query` needs a SQL argument, so the
  parametrization gains an argument column. A Python socket guard does not see
  DuckDB's native connections, so the no-network claim rests on the settings
  (pinned by read-back) and on httpfs never being installed.
- **Confinement.** `tests/test_confinement.py` has `EntryPoint` writers and no
  read-only registry. `test_connect_writes_only_the_credentials_file`
  (`:1738-1801`) is the standalone precedent for "this command writes exactly
  X".
- **Skills.**
  - `PACKAGED_SKILLS` is a tuple of names (`agentskill.py:43-47`).
  - `tests/test_agent_skill.py` has a profile per skill (`:174-199`), with
    two-way registry checks (`:224`, `:228`). Parametrized pins cover:
    - frontmatter keys exactly `{name, description, license, compatibility,
      metadata}`, with `metadata.version == project.version` (`:422-462`);
    - command binding of inline spans and `bash`/`sh` fences, but not `sql`
      fences (`:804-858`);
    - published GitHub URLs only, plus the contract URL (`:1194-1218`);
    - every `OWNED_PATHS` entry (`workouts/`, `history/`, `blocks/`,
      `fit-archive/`, `.cache/`, `.fitdocs/`…) absent from the whole raw
      body, fences included;
    - no `MANAGED_KEYS`/`PRESERVED_REGIONS` backticked inside the single
      Ownership section (`:1224-1258`).
  - The locator pins the registry order and the set of installed skill
    directories (`tests/test_skill_locator.py:57-58`, `:186-194`).
  - Further hard-coded lists name the skills:
    - `release/artifact-policy.toml:55-61`;
    - `tests/test_release_artifacts.py:978-983`;
    - `docs/releasing.md:75-83` with `tests/test_releasing_docs.py:569-573`;
    - `docs/wiki-integration.md:10-28` and `README.md:93-121`, each pinned
      per registered name.
  - Any `blob/main/docs/*.md` URL in a SKILL.md or the CHANGELOG must be a
    `[project.urls]` value (`tests/test_packaging.py:231-285`).
- **Docs.**
  - The docs index is the table at `docs/index.md:8-21`.
    `_REQUIRED_ENTRY_POINT_LINKS` (`tests/test_docs_guarantees.py:1111-1123`) is
    a subset list.
  - No `docs/` page has a generated section. Goldens regenerate through `uv run
    python -m <test module>` (`tests/test_declaration_goldens.py:20-23`).
  - Docs-held-to-code tests compare parsed sections with code constants as sets
    (`tests/test_ownership_contract.py:131-134`,
    `tests/identity/test_contract_docs.py`).
  - The network statements ("every network request fitdocs ever makes") are
    pinned by `tests/connectors/test_network_statements.py`. `query` keeps them
    true by adding no network path.

### External: DuckDB's own guidance
- "Securing DuckDB" (duckdb.org/docs/current/operations_manual/securing_duckdb)
  recommends:
  - extension auto-install and auto-load off, and community extensions off;
  - `enable_external_access = false`;
  - limits on threads, memory and `max_temp_directory_size`;
  - `lock_configuration = true`.
- It states that these settings "provide defense-in-depth … but they are not a
  substitute for proper sandboxing".
- `allowed_directories` and `allowed_paths` exist, but `query` needs none: the
  index is the only file, opened at connect.

### Task 8.3: query timing on the authorized copied-data root (2026-10-08)
- **Scope**: 2,517 FIT files (171,192,835 bytes); schema 2 index; 2,502 pages and 5,636,964 records. Python 3.11.15.
- **Preparation measurements (2026-10-07; not query timings)**: sync 532.870 s, exit 0; index rebuild 269.507 s, exit 0.
- **Query measurements (2026-10-08)**: `SELECT count(*) FROM pages`, 1.530 s, exit 0; `--schema`, 1.501 s, exit 0; `SELECT count(*), avg(heart_rate_bpm) FROM records`, 1.457 s, exit 0.

## Architecture Pattern Evaluation

| Option | Description | Strengths | Risks / Limitations | Verdict |
|---|---|---|---|---|
| Configuration only (the brief's measured settings) | One locked read-only connection; DuckDB refuses everything else | Smallest; DuckDB's own mechanism | 1.1.x writes into HOME before refusing `INSTALL`; on 1.4+ a multi-statement string can abort the process and `enable_logging` bypasses the lock; INSTALL/LOAD can only be pinned by executing them | Insufficient alone |
| Configuration plus a statement gate plus read-back (selected) | The configuration is the boundary. Before it, `query` parses the text, refuses anything but one query or `EXPLAIN`, and confirms the settings took effect | Clear refusal messages; INSTALL/LOAD never reach DuckDB in any test; fails closed if the shared store's mandatory settings drift; immune to the multi-statement abort | Three layers to pin; the gate depends on DuckDB's statement classification | Adopted |
| A separate subprocess per query (OS-level sandbox) | Run DuckDB in a child with seccomp, sandbox-exec or similar | A true sandbox | Platform-specific; not portable to Linux CI without new tooling; the brief scopes the sandbox to accidental or injected SQL, not a local adversary | Rejected (out of scope; recorded) |
| Wrap statements as `SELECT * FROM (<sql>)` | Coerce every statement into a query | No parser call | Breaks `DESCRIBE`, `SHOW`, `EXPLAIN` and `PRAGMA`; still runs `CALL`-like table functions | Rejected |

## Design Decisions

### Decision 1: Raise the dependency floor to `duckdb>=1.2,<2` (option b), rather than a runtime version gate (option a)
- **Context**: `query` runs arbitrary agent SQL, so its sandbox claim must hold
  on every release the pin admits. Every 1.1.x release creates
  `~/.duckdb/extensions/v1.1.x/<platform>` before refusing `INSTALL`.
  When this research ran, `analytics-index` task 1.1 pinned `duckdb>=1.1,<2`.
- **Alternatives**:
  1. A runtime gate: `query` refuses to run below 1.2 with a message, and the
     pin stays.
  2. Raise the floor in the pin to 1.2.
- **Selected**: Option 2, `duckdb>=1.2,<2`. The literal is `analytics-index`'s,
  so it was raised to the controller as upstream issue U1. Resolved:
  `analytics-index`'s cross-spec round 1 adopted it (ruling C1), and its task
  1.1 now pins `duckdb>=1.2,<2`. This spec's task 1.1 confirms the literal,
  and its task 8.2 verifies the floor on 1.2.0.
- **Rationale**:
  - The resolver enforces a floor statically, for every command. A runtime gate
    would leave installs that pip calls valid but on which one command refuses
    to run: two product behaviours on one install.
  - The roadmap's reason for `>=1.1` was that 1.x clients can read the file.
    That rests on the storage version the writer pins
    (`storage_compatibility_version='v1.0.0'`, header version 64), not on the
    library floor, so raising the floor costs that guarantee nothing.
  - 1.2.0 shipped on 2025-02-05, and the lock resolves 1.5.6.
  - Even with the statement gate (Decision 2), which keeps `INSTALL` from ever
    reaching DuckDB through `query`, the configuration claim itself must hold
    on the floor. The controller's criterion and Requirement 5.7 both ask for
    exactly that.
- **Trade-offs**: An environment that forces duckdb 1.1.x cannot install
  fitdocs. That is accepted.
- **Follow-up**: Task "floor verification" runs `query`'s sandbox tests on 1.2.0
  in a network-blocked scratch venv, and asserts HOME stays empty.

### Decision 2: Exactly one statement, of a read kind, screened before it runs
- **Context**:
  - The multi-statement abort and the `enable_logging` lock bypass, both on 1.4
    and later.
  - The brief's "runs one SQL statement" and "a message that names the
    restriction".
  - analytics-index's rule that no test executes `INSTALL`/`LOAD`.
- **Selected**:
  - A facade method `IndexConnection.statement_types(sql)` (an append to
    `store.py`, the only DuckDB importer) returns the parsed statement types.
  - `query` refuses zero statements, or two or more, and every type other than
    `SELECT` and `EXPLAIN`, before execution.
  - The configuration remains the boundary for what a query can reach:
    file-reading functions, `EXPLAIN ANALYZE COPY`, and
    `SELECT … FROM enable_logging(…)`.
- **Trade-offs**:
  - `CREATE TEMP TABLE`, `TEMP MACRO`, `SET VARIABLE` and `USE` are refused.
    With one statement per invocation they would serve nothing, and CTEs cover
    their use.
  - `CALL pragma_x()` is refused, while `SELECT * FROM pragma_x()` and
    table-valued `PRAGMA` (which parse as SELECT) work. The refusal message says
    so.

### Decision 3: Fail closed by reading the sandbox back
- **Context**:
  - `fitdocs.index.store.MANDATORY_SETTINGS` is shared and owned by
    `analytics-index`.
  - Five of the settings cannot be pinned through statement outcomes (the
    mutation matrix).
  - A future DuckDB might ignore or rename a setting.
- **Selected**:
  - `query` holds its own literal map `REQUIRED_SANDBOX` of the expected values
    of the seven mandatory keys, plus `threads`.
  - After opening, it reads `duckdb_settings()` and refuses to run on any
    missing or different value, naming the setting.
  - A test pins that every key of `store.MANDATORY_SETTINGS` is in
    `REQUIRED_SANDBOX`.
  - The literal is deliberately not derived from the store's map: a mutation
    that drops a key from the store must make `query` refuse.
- **Not read back**: `memory_limit` and `max_temp_directory_size`. They read
  back in a human-formatted size (`953.6 MiB`). They are resource bounds, not
  escape barriers, and tests pin them on the locked release.

### Decision 4: A spill directory per `query` process, and stale ones removed by the next `query`
- **Context**: Concurrent read-only spills into the shared default `<db>.tmp`
  fail or abort. A killed spill's files remain, and no reopen removes them.
- **Selected**:
  - `temp_directory = <index directory>/query-spill-<pid>`, set at connect.
    DuckDB creates the directory only when it spills, and removes it on close.
  - At start, `query` removes `query-spill-<n>` directories whose process `n` is
    no longer running: `os.kill(n, 0)` raises `ProcessLookupError`.
  - It never removes:
    - one whose process is alive, or that it cannot check (`PermissionError`);
    - its own;
    - a symlink;
    - anything else.
  - On Windows (`os.name == "nt"`) it skips the clean-up entirely, because
    `os.kill(pid, 0)` there sends a console control event. fitdocs claims no
    Windows support.
  - `max_temp_directory_size = '4GB'` bounds a runaway spill.
- **Alternatives**:
  - The brief's `<db>.tmp`: it collides under concurrency.
  - The OS temporary directory: health data would spill outside the `0o700`
    index directory.
  - Leaving leftovers: unbounded growth after crashes.
- **Trade-offs**:
  - The index directory gains a transient name, `query-spill-<pid>/`. The
    ownership contract's analytics-index section had to name it (upstream
    issue U3). Resolved: `analytics-index`'s cross-spec round 1 (ruling C3)
    names it in its task 8.1, beside the writer's own `writer-spill/`, and
    pins the phrase.
  - PID reuse by an unrelated live process only delays a removal.

### Decision 5: Freshness is the refresh's own scan, run before the index is opened
- **Context**: Requirement 9.3 requires exactly the pages the refresh
  considers.
- **Alternatives**:
  1. A fast path: hash only the files whose path and bytes the bookkeeping
     does not know, and parse the rest lazily. It must re-implement the
     duplicate-base rule (first by path wins) to be exact: two definitions.
  2. `corpus.scan_workout_pages`, `analytics-index`'s scan.
- **Selected**: Option 2.
  - Added = scanned keys the bookkeeping lacks; removed = held keys not
    scanned; changed = the same key with a different document fingerprint,
    renames included.
  - Left-out pages are reported, never counted as behind.
  - The scan runs before the index is opened, so the read lock is held only
    for the bookkeeping read and the statement.
- **Trade-offs**: It costs about the frontmatter scan's time per query (about
  1.5 s at 2,500 pages, per analytics-index's estimate). A maintainer-only task
  measures it on the real data root.
- **`--schema` only**:
  - Corpus-table staleness: each registered corpus producer's fingerprint
    against `index_producers`. It is computed exactly as the refresh computes
    it: `analytics-index`'s one builder, `corpus_snapshot`, with `held` set to
    the bookkeeping's page keys, and its one composition,
    `combined_corpus_fingerprint`, which supplies the fitdocs version and
    `SCHEMA_VERSION` itself (cross-spec ruling C5). `held` comes from the
    bookkeeping, so this runs after close, still outside the read lock.
  - Athlete-input drift: `activities.athlete_fingerprint` against the current
    `athlete.toml`'s fingerprint.

  Both cost more than pages and change rarely. The skill teaches `--schema`
  first.

### Decision 6: Output formats, defaults and values
- **Defaults**: `table` on a TTY and `csv` when piped (agents run piped).
  - CSV is the conventional piped tabular form (`duckdb -csv`, `sqlite3 -csv`)
    and costs the fewest tokens.
  - NULL stays distinguishable: an empty unquoted field, with an empty string
    always quoted as `""`.
  - JSON is one flag away for nested values.
- **JSON shape**:
  - `{"columns": [...], "rows": [[...]], "row_count", "truncated", "max_rows",
    "freshness"}`, with rows as arrays, because result column names may repeat.
  - Column types are not included, because the cursor description is coarse on
    the 1.2 floor.
  - Decimals are emitted as exact number tokens. A small hand-written JSON
    writer is used, because `json.dumps` cannot emit a raw number.
  - Non-finite floats become `"NaN"`, `"Infinity"` and `"-Infinity"`, never
    `null`.
- **Times**: Timestamps print in ISO 8601 with a `T`, durations as ISO 8601
  durations, and BLOBs as lowercase hex.
- **`TIMESTAMP WITH TIME ZONE`**:
  - Without `pytz` (not a dependency) its fetch fails. The error is classified
    with a hint: cast to `TIMESTAMP`.
  - If `pytz` happens to be installed, the aware datetime prints with its
    offset.

### Decision 7: Comments are the single source of meaning, and one renderer serves both projections
- `schemaview.read_catalog` reads `duckdb_tables()`/`duckdb_columns()` from the
  live file, filtered to the current database's `main` schema.
- `render_reference(tables)` produces the markdown that is both
  `docs/analytics.md`'s generated block and the body of `--schema`'s text view.
- Units are derived from the column name with `analytics-index`'s
  `schema.UNIT_SUFFIXES` (longest first). A consistency test asserts that each
  derived unit's word appears in the column's stored description, which
  `analytics-index` guarantees.
- A missing comment shows as "(no description)" and raises a warning line. The
  test suite asserts there are none on a freshly built index.

## Synthesis outcomes
- **Generalization**:
  - The docs reference and `--schema` are one renderer over one catalog read.
  - The per-query freshness counts and `--schema`'s page counts are one
    function.
  - Every DuckDB refusal maps through one classifier (`statement.py`) to a
    named restriction.
- **Build vs adopt**:
  - Adopted:
    - DuckDB's configuration as the boundary;
    - `extract_statements` for parsing;
    - `connection.interrupt` with a `threading.Timer` for the time limit;
    - `temp_directory` and `max_temp_directory_size` for spill;
    - analytics-index's location, store, scan, bookkeeping, fingerprints and
      schema vocabulary;
    - Click's option validation for `--format` choices and `--max-rows`.
  - Built:
    - the CSV quoting, because Python's `csv` cannot tell `""` from NULL;
    - a JSON writer, for exact decimals;
    - the stale-spill clean-up.

  No new dependency.
- **Simplification**:
  - No per-column types in the output.
  - No `--no-freshness` switch.
  - No user-tunable memory or threads.
  - No total row count for a cut result: it would mean full execution.
  - No `--schema` CSV.
  - No multi-statement scripts.
  - No contract-version bump: the contract's index section, `analytics-index`'s,
    names the spill directory (U3, its task 8.1).

## Risks & Mitigations
- **The floor.** Had the floor stayed `>=1.1`, Requirement 5.7 would have
  failed on 1.1.x (the `+HOME` row above). Resolved by `analytics-index`'s
  cross-spec round 1 (upstream issue U1, ruling C1): its task 1.1 pins
  `duckdb>=1.2,<2`. Task 1.1 here confirms the literal and stops and reports
  if `main` still admits 1.1; task 8.2 verifies the floor on 1.2.0.
- **Facade fetch errors.** Errors and interrupts surface at `fetchmany`
  (streaming). Had `IndexResult.fetchmany` let raw DuckDB exceptions escape,
  `query` could not have classified them without importing DuckDB. Resolved
  by `analytics-index`'s cross-spec round 1 (upstream issue U2, ruling C2):
  its task 4.1 makes `fetchmany`/`fetchall` raise
  `IndexStatementError`/`IndexInterrupted` chained, like `execute`, and pins
  it. Task 1.1 here confirms it and pins it again on query's read-only call
  path.
- **Reproducing the refresh's corpus fingerprints.** A reader that assembled
  its own `CorpusSnapshot`, or composed the three-part fingerprint itself,
  could drift from the refresh and report a corpus table behind right after a
  refresh, for example after a page error left a new page out of the index.
  Resolved by cross-spec ruling C5: `analytics-index` owns the one builder
  (`corpus_snapshot`, whose snapshot also carries the left-out pages) and the
  one composition (`combined_corpus_fingerprint`). `query` calls both, with
  `held` set to the bookkeeping's page keys, and its freshness tests compare
  against fingerprints a real refresh recorded.
- **A future DuckDB adds another lock-bypassing function**, as `enable_logging`
  did in 1.4. Mitigations:
  - one statement per connection, which removes the cross-statement effect;
  - the gate refuses `CALL`;
  - external access still refuses files;
  - the read-back fails closed on changed settings.
  - Residual: a `SELECT`-able table function that both changes an unlocked
    setting and acts within the same statement. None is known.
- **The Python socket guard cannot see DuckDB's native sockets.** The
  no-network claim rests on httpfs never being installed: auto-install is off,
  `INSTALL` is refused by the gate and by the configuration, and the settings
  are read back. The docs page says that outside clients are not bound.
- **Process abort from a DuckDB defect.** A crash ends `query` without a
  message. Its spill directory, if any, is removed by the next `query`.
  Subprocess tests pin the known abort vector without risking the test
  process.
- **Freshness scan cost.** It is about 1.5 s at 2,500 pages per query.
  Mitigation: a maintainer-only measurement. If it exceeds about 3 s, a
  follow-up is queued; caching is not allowed, because `query` writes nothing.
- **`max_temp_directory_size` is unmeasured.** It is recorded above. The time
  limit also bounds a spill.

## References
- DuckDB, Securing DuckDB: https://duckdb.org/docs/current/operations_manual/securing_duckdb/overview.html
- DuckDB concurrency: https://duckdb.org/docs/stable/connect/concurrency
- `analytics-index` design § Cross-spec seams (`.kiro/specs/analytics-index/design.md:178-337`
  at ee70095, after its cross-spec round 1) and research P6 with its
  disclosure (`.kiro/specs/analytics-index/research.md:277-316`)
- Probe scripts and raw outputs (session scratchpad, not in the repo):
  `p10/query/probe/*.py`, `p10/query/runs/*`
