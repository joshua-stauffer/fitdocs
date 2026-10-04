# Brief: analytics-index

## Problem

fitdocs computes rich per-activity data: summaries, laps, strength sets,
per-second channels including running dynamics, NP/IF/TSS/TRIMP, zone
times, loads per channel, QA flags and effort tags. It then flattens all of
it into markdown. Agents in the athlete's PKM who need a statistical answer
have only two options, both bad:

- **Read documents.** Frontmatter carries only distance, moving time,
  average HR and power, elevation gain, calories and the selected load
  (`src/fitdocs/render/frontmatter.py:90`). Everything else is in rendered
  tables and the load region's JSON (`load/render.py:63`). Answering "time
  above 170 bpm in September" means reading every September page and
  parsing tables, and the per-second data isn't in any document at all.
- **Re-parse `.fit` files themselves**, re-implementing fitdocs's parsing,
  composition and metric rules, and getting them subtly wrong.

The maintainer wants fitdocs to ship an analytics engine: a DuckDB database
written as activities are ingested and read with standard SQL.

## Current State

- `.kiro/steering/tech.md:12-16` says "No server, no database … Everything
  is re-derivable from the `.fit` + profile."
  `.kiro/specs/training-load/research.md:79` rejected a separate load
  database because it "duplicates truth". Phase 10 reconciles this: the
  index is a derived, disposable projection, never state (see Approach).
  This spec amends `tech.md`.
- There's no single write seam:
  - documents are written by `sync.py:_page_task` → `_write_outputs`
    (`sync.py:2223`), which covers sync, drain, pull --sync, regen and the
    settle pass;
  - load values are written separately by `load/engine.py` at :379
    (restore), :526 (compute) and :594 (unsupported);
  - the CLI chains passes, then calls `_run_load_pass` (`cli.py:1498`) at
    `cli.py:451`, `:534`, `:628`, plus `load` alone (`cli.py:638`).
- At `_page_task`'s write (`sync.py:1979-2045`) the composed `Activity`,
  its `DerivedMetrics`, the `Composition`, the page identity and roles are
  in memory. The `LoadResult` isn't; the load region is carried verbatim
  and can be re-read with `load/render.py`'s `parse_payload`.
- Every corpus pass reads frontmatter through `docio.read_frontmatter`
  (about 1.4 s at 2,500 pages, `activity-identity/design.md:1440`). A full
  real drain took 27:58 for 2,478 files, about 1.5 documents per second
  (queue `2026-08-23-sync-emits-nothing-until-the-run-ends`).
- Nothing caches or indexes today. No sqlite, duckdb or parquet anywhere in
  `src/`.
- The runtime dependency set is frozen by plugin-api's Req 7.2 guard
  (`tests/test_determinism.py:672-713`, which also forbids any
  `optional-dependencies`) and by `tests/test_packaging.py:501-516`.
- Writes are confined to `OWNED_PATHS` ∪ `athlete.toml` ∪ configured
  locations (`tests/test_confinement.py:1026`, `WRITING_ENTRY_POINTS`). The
  one existing per-user location outside the data root is the connector
  credentials directory (`connectors/credentials.py:87`):
  `FITDOCS_CREDENTIALS_DIR` (absolute) > `$XDG_CONFIG_HOME/fitdocs/…` >
  `~/.config/fitdocs/…`, refused inside the data root.
- The real data root is in iCloud Drive and its git repository ignores
  `.cache/` and `.fitdocs/`. A large, frequently rewritten binary there
  risks conflict copies and eviction. That's why the maintainer put the
  index outside the data root.

The viability check (2026-10-04) used duckdb 1.5.6 on macOS arm64 with
Python 3.11. What it measured:

- **Size and speed.** 9.0M records rows over 2,502 synthetic activities
  take a 224 MB file. Open takes 4 ms, a group-by 11–14 ms, and a rolling
  60 s max over every row 150–180 ms. Peak memory is about 480 MB.
  Rewriting 100 activities takes 0.2–0.3 s. Repeated rewrites grow the file
  (224 → 254 MB over six rounds), and a rebuild compacts it.
- **Insert route.** Without numpy, pandas or pyarrow, the fast route is one
  JSON-columnar string parameter per activity,
  `INSERT … SELECT unnest(j.c1), … FROM (SELECT from_json($1, '<types>') j)`.
  It runs at about 186k rows/s, needs no file access and round-trips values
  exactly. The obvious routes are 100× slower or need missing packages:
  - `executemany`, `con.values` and list parameters: about 1.4k rows/s;
  - `con.append`: needs pandas;
  - `read_csv` from a file-like object: needs fsspec.
  A full rebuild spends about 48 s inserting, plus parsing.
- **Locking.** One read-write process or many read-only ones. Every conflict
  fails at once with `duckdb.IOException` ("Could not set lock on file …
  (PID n)"); nothing waits. A lock conflict, a version mismatch and a
  missing file are told apart only by message text, which isn't a stable
  API.
- **Crash recovery.** After `kill -9`, a reopen replays the WAL to exactly
  the committed rows.
- **Rebuild swap.** A rebuild written to a temp file and `os.replace`d into
  place works on macOS even while a reader is open. Windows is untested.
- **Open corruption bugs** are tied to primary-key/ART indexes and
  checkpoints: duckdb/duckdb #22823, #25928, #23046.
- **Storage format.** Files written by 1.0–1.5 are mutually readable. 2.0
  pre-releases (on PyPI) write a format 1.x refuses.
- **Writer config.** The writer works under the strict configuration that
  `analytics-query` uses, external access off included.
- **Footprint.** About 44 MB installed (wheels 13–21 MB). There are no
  musllinux wheels since 1.4.0 and no free-threaded 3.14t wheels.

## Desired Outcome

- **One DuckDB file per data root**, in a per-user cache directory outside
  the data root:
  - resolved like the credentials directory: a dedicated absolute env
    override, then `$XDG_CACHE_HOME/fitdocs/…`, then `~/.cache/fitdocs/…`;
  - keyed by the resolved data root, so two data roots never share an index;
  - refused if it resolves inside the data root.
  Deleting it loses nothing but rebuild time.
- **Core tables** (names provisional), each carrying units and meaning in
  table and column comments:
  - activities: one row per workout page, with identity, date and start,
    sport and modality, summary scalars, `DerivedMetrics` scalars, the
    selected load and basis, effort tag, QA flags;
  - page sources and roles (base and extras);
  - laps;
  - strength sets;
  - records: per-second samples of every channel, including running
    dynamics and donated channels, aligned as composed;
  - zone times per channel and zone;
  - per-channel loads;
  - index metadata: schema version, fitdocs version, data-root key.
- **A producer seam.** A per-page producer gets the page and its composed
  activity, metrics and load result, and writes that page's rows. A
  corpus-level producer gets a corpus snapshot and declares an input
  fingerprint. The core tables are the first producers; `analytics-derived`
  registers four more without touching the pass.
- **A reconciling pass** at the end of every writing command (`sync`,
  drain, `pull --sync`, `regen`, `load`):
  - it fingerprints each workout page against the index and upserts only
    pages whose fingerprint moved, one transaction per page;
  - it removes rows for pages that are gone;
  - when the run already holds a page's composed activity and metrics, they
    are handed over, so nothing is parsed twice;
  - effort-tag edits by hand and the load pass's rewrites reach the index
    on the next writing command;
  - a run that changes nothing writes nothing to the index.
- **`fitdocs index`** runs the same pass on demand. `--rebuild` starts from
  an empty database, so backfill and intake are one code path.
- **No automatic pass ever starts a full rebuild.** When the index is
  absent, unreadable, or carries another schema version, a writing command
  reports that the index needs `fitdocs index` and leaves it alone. A
  routine `sync` never turns into a 25-minute backfill without being asked.
  The rebuild reports progress.
- **The pipeline never pays for the index's failures.** An index error
  (lock held, disk full, corrupt file) is reported in the command's output
  and never fails, rolls back or skips a document write. Because the pass
  reconciles against disk state rather than replaying events, a skipped
  refresh heals itself at the next successful one. A held lock, say an
  agent's DuckDB CLI left open on the file, needs no stale marker; it only
  needs reporting.
- **`fitdocs index` recovers anything.** A version-mismatch or
  corruption-class error there leads to a rebuild into a temp file that
  replaces the old one. Whether `os.replace` over a file a Windows reader
  holds open works is verified in the design, which supplies a fallback if
  it doesn't.

## Approach

**Reconciling projection** (maintainer choice, 2026-10-04, over inline
write hooks and refresh-on-query):

- The documents and the archived `.fit` files stay the truth. The index is
  a cache with a schema version.
- It's written by one post-pass, keyed by fingerprints, rather than hooks at
  each of the five write sites owned by four specs.
- Being a post-pass, it can see every change: documents, load regions,
  user frontmatter, `athlete.toml`. The stale-document rule (Constraints)
  decides which of them move rows.
- DuckDB is a **core** runtime dependency (maintainer, 2026-10-04,
  confirmed after the viability check reported the footprint and the
  musl gap), so the index always exists on intake and agents can count
  on it.

## Scope

- **In**:
  - location resolution and refusal;
  - the DuckDB dependency and the reworded dependency guards;
  - the connection policy for the writer;
  - the core schema with comments and a schema-version constant;
  - the producer seam;
  - fingerprints and the reconciling pass, wired after each writing
    command's passes;
  - the in-memory handoff from sync;
  - `fitdocs index [--rebuild]` with progress;
  - failure isolation, and locking on the write side;
  - the confinement entry for the new location;
  - steering updates: `tech.md` no-database rule, Key Libraries and
    Network notes;
  - the ownership contract and compatibility statements, if the design
    finds that a stated guarantee changes;
  - the CHANGELOG entry.
- **Out**:
  - mean-max curves, daily load series, the benchmark timeline and training
    blocks (`analytics-derived`);
  - `fitdocs query`, the read sandbox, the agent skill and the query docs
    page (`analytics-query`);
  - any existing pass reading the index;
  - cross-machine sync of the index;
  - free-text columns.

## Boundary Candidates

- Row extraction: pure functions from (page, activity, metrics, load
  result) to rows. No DuckDB import.
- Store: location, connection, schema DDL and version, transactions. The
  only module that imports `duckdb`.
- Reconcile: fingerprints, the change set, producer dispatch, reporting.
- CLI wiring: the post-pass call sites and the `index` command.

## Out of Boundary

- Changing what any document shows or when it's written.
- Read-side concerns: the sandbox, formats and freshness reporting belong to
  `analytics-query`, which consumes this spec's location and version API.

## Upstream / Downstream

- **Upstream**:
  - `fit-ingest` (model);
  - `workout-docs`, `activity-identity`, `channel-merge` (`_page_task`,
    identity, composition);
  - `training-load` (load region payload);
  - `effort-tags`, `activity-qa-flags`, `running-dynamics` (columns).
- **Downstream**: `analytics-derived` (producer seam, schema version) and
  `analytics-query` (location, version, comments, locking).

## Existing Spec Touchpoints

- **Extends** (carried out inside this spec, recorded as amendments):
  - `plugin-api`: Req 7.2's guard is reworded. Plugin discovery still adds
    no dependency and never imports `duckdb`, but the baseline set gains
    `duckdb` for this spec.
  - `distribution`: the exact dependency list in
    `tests/test_packaging.py:501-516`.
  - `workout-docs`: the in-memory handoff out of `_page_task` (append-only;
    nothing it renders changes).
- **Adjacent**:
  - `load-history`, `plan-resolution`, `performance-benchmarks`: their scans
    stay independent;
  - `connectors`: the network boundary guard
    (`tests/connectors/test_boundary.py`) and the no-network command list.
    `index` joins the list, and DuckDB must never fetch an extension.

## Constraints

- Absent data is NULL, never 0 or a default (CLAUDE.md hard rule). Column
  names carry units the way frontmatter does (`_m`, `_s`, `_bpm`, `_w`).
- No network. Under default settings, one SQL string mentioning `https://`
  auto-installs httpfs from `http://extensions.duckdb.org` (measured). So
  every connection fitdocs opens, the writer's included, sets:
  - `autoinstall_known_extensions` and `autoload_known_extensions` off;
  - `allow_community_extensions` and `allow_persistent_secrets` off;
  - `enable_external_access` off.
  Only the store module imports `duckdb`, and a boundary test pins both
  facts. Tech.md's network allow-list gains a sentence: it binds fitdocs's
  connections, not an outside DuckDB client that opens the file.
- **Dependency pin: `duckdb>=1.1,<2`** (viability, 2026-10-04). *Superseded:
  the floor is now `duckdb>=1.2,<2`, by the Phase 10 cross-spec review,
  round 1, ruling C1 (every 1.1.x release writes into HOME on `INSTALL`; see
  research.md, Risks).* Moving to 2.x
  is a deliberate change, because a 2.x-written file can't be read by an
  agent's 1.x client. A version-mismatch error means rebuild, never data
  loss.
- **No `PRIMARY KEY`, `UNIQUE` or index in the schema**, given the open
  corruption bugs. Page uniqueness is enforced by delete-then-insert per
  page inside one transaction, and pinned by a test.
- **Insert through the JSON-columnar route** (or a faster one the design
  measures). NaN and infinity become `None` before serialising, because the
  JSON route stores real NaN.
- `CREATE OR REPLACE TABLE` drops comments, so every schema creation
  re-applies them. Don't set `disabled_filesystems`: it breaks spilling.
  Spilling goes to `<db>.tmp` beside the file, which is fine in a cache
  directory.
- Classifying DuckDB errors (lock, version, missing, corrupt) by message
  text lives in one function, pinned by tests against the real messages
  of the locked version range.
- The documentation states the install footprint and the platform gap: no
  musllinux and no free-threaded wheels.
- Determinism means the same rows for the same inputs. File bytes aren't
  compared.
- A stable page key is needed. Frontmatter `uuid` is written only when
  present, so the design has to give pages without one a stable key that
  survives a rename.
- **The index's relation to stale documents needs one stated rule.**
  `athlete.toml` changes alter IF, TSS, TRIMP and zone times, but
  documents only change on `regen`. The recommended rule: the index agrees
  with the documents. In-run metrics are handed over; a page is re-indexed
  when its bytes or sources change; a rebuild records the athlete-input
  fingerprint it computed with, so any disagreement with a stale page is
  detectable. The design either adopts this or states a better one.
- Python 3.11 floor, `mypy --strict`. `duckdb` ships `py.typed` plus
  stubs, and a sample module passed `mypy --strict` in the viability check.
- The schema version advances by one per lander across Phase 10's specs.
