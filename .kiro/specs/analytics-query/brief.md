# Brief: analytics-query

## Problem

Agents working in the athlete's PKM answer statistical questions ("weekly
running volume since March", "average HR at 4:30/km pace this block versus
last") by reading hundreds of workout documents and doing the arithmetic in
context. It's slow, it costs a lot of tokens, and it's often wrong:
frontmatter carries only a thin summary (distance, moving time, average HR
and power, elevation, calories, load), and everything else sits in rendered
markdown tables. `analytics-index` puts the data in a DuckDB file, but
agents still need a safe, documented way to ask it.

## Current State

- After `analytics-index`, an index file exists in a per-user cache
  directory outside the data root, kept current by a reconciling pass, with
  a schema version and table and column comments.
- There's no read surface yet. `fitdocs check` is the closest precedent: a
  read-only command that resolves the data root and reports. Its read-only
  contract is in its docstring (`src/fitdocs/cli.py:676`).
- Packaged agent skills: `fitdocs-workouts` (pull, drain, check) and
  `build-training-block`. They're registered in `PACKAGED_SKILLS`
  (`src/fitdocs/agentskill.py:44-47`) and installed by `fitdocs skill
  [NAME]`, which prints a `cp -R` recipe. Neither teaches reading workout
  content.
- These guards list every CLI command or every skill:
  - `tests/connectors/test_e2e.py:205` (no-network command list; `tech.md`
    says the same in prose);
  - `tests/test_agent_skill.py` (a profile per skill, command binding at
    :838, no owned path or managed key spelled out at :1225);
  - `tests/test_skill_locator.py:48-57` (registry order).

## Desired Outcome

- **`fitdocs query`** runs one SQL statement, given as an argument or read
  from a file or stdin, against the index and prints the result:
  - output formats: at least a human table, CSV and JSON. The default on a
    TTY and the default when piped are decided and stated;
  - a row cap with an explicit truncation notice, never silent truncation;
  - non-zero exit with a clear message on SQL errors.
- **A sandbox the agent can't talk its way out of:**
  - a read-only connection;
  - no network, including DuckDB extension auto-install and auto-load;
  - no file access beyond the index: no `read_csv` of arbitrary paths, no
    `COPY … TO`, no `ATTACH`, no `INSTALL` or `LOAD`;
  - configuration locked so a statement can't re-enable any of it.
  Statements the sandbox refuses fail with a message that names the
  restriction.

  `read_only=True` alone is **not** this. In the viability check it still
  allowed `read_csv('/etc/passwd')`, `COPY TO`, `EXPORT DATABASE`,
  `INSTALL`/`LOAD httpfs`, `ATTACH 'md:'` (which opened a browser
  login) and `CALL start_ui()` (which started an HTTP server). The
  configuration measured to refuse every one of those (duckdb 1.5.6):
  ```python
  {"enable_external_access": False, "autoinstall_known_extensions": False,
   "autoload_known_extensions": False, "allow_community_extensions": False,
   "allow_persistent_secrets": False, "python_enable_replacements": False,
   "memory_limit": "1GB", "threads": 2, "lock_configuration": True}
  ```
  Under it, aggregates, window functions with `QUALIFY`, CTEs, joins,
  `information_schema`, `CREATE TEMP TABLE` and `TEMP MACRO` all work, and
  spilling goes to `<db>.tmp`. Every `SET`/`RESET`, `CREATE SECRET` and
  `getenv` is refused. One setting stays out: `disabled_filesystems` can't
  be set at connect and breaks spilling when set later. DuckDB's own docs call
  these settings "not a substitute for proper sandboxing". The sandbox
  guards against accidental or prompt-injected SQL; it isn't a boundary
  against a local user, who can always open the file with their own client.
- **Bounded execution.** DuckDB has no statement timeout. A timer that calls
  `connection.interrupt()` (measured: stops within 1.00 s, raising
  `duckdb.InterruptException`) plus the config's `memory_limit` and
  `threads` keep a runaway query from hanging the agent or the machine.
- **Introspection.** A schema view (e.g. `fitdocs query --schema`) lists
  tables, columns, types, units and meanings from the schema comments,
  plus row counts and the index's state:
  - schema version;
  - pages indexed against workout pages in the corpus;
  - whether a rebuild is needed.
- **Honest freshness.** `query` never writes. When the index is absent,
  built by an incompatible schema version, or behind the corpus, it says so
  and names the command that fixes it (`fitdocs index`). DuckDB never waits
  on a lock: opening read-only while the writer holds the file fails at once
  with "Could not set lock on file … (PID n)". So `query` retries with
  backoff for a bounded time (the viability check suggested about 10 s; a
  refresh normally takes seconds), then fails with a message saying the
  index is being refreshed.
- **A packaged agent skill** (provisional name `fitdocs-analytics`) that
  teaches:
  - check freshness, then read the schema, then write SQL;
  - prefer the index over reading documents for anything aggregate;
  - show the query alongside the answer;
  - absent values are NULL, not zero.
  Its examples cover volume, zones, loads and effort tags, and gain
  mean-max, fitness and form, benchmarks and blocks once `analytics-derived`
  has landed.
- **A docs page** (`docs/analytics.md`) covering:
  - the command and the sandbox;
  - the location and how to open the file from another DuckDB client:
    - open it read-only, with extension auto-install off. Outside clients
      bypass the sandbox and aren't bound by fitdocs's network allow-list;
    - an outside client left open blocks every refresh until it's closed;
  - the schema reference, held to the live schema by a test so it can't
    drift.

## Approach

A thin read-only command over `analytics-index`'s location and version API.
It opens a sandboxed DuckDB connection, executes, formats and exits. The
skill and the docs page are the agent-facing contract. The schema comments
are the single source of column meaning, and the schema view and the docs
reference both project them.

## Scope

- **In**:
  - the `query` command and its formats, row cap, input modes and exit
    codes;
  - the sandbox configuration and its tests (each refused statement class
    pinned);
  - schema introspection and freshness reporting;
  - lock-contention handling on the read side;
  - the packaged skill and its registry, profile and locator pins;
  - `docs/analytics.md`;
  - joining the no-network command list (`tech.md`,
    `tests/connectors/test_e2e.py:205`);
  - the CHANGELOG entry.
- **Out**:
  - building or refreshing the index (`analytics-index`);
  - the derived tables (`analytics-derived`);
  - an MCP or HTTP server, and a natural-language "ask" wrapper (follow-ons);
  - write access, user tables, saved queries;
  - charting query results.

## Boundary Candidates

- The sandboxed connection factory: one function, the only place that opens
  the index for reading.
- Result formatting: pure functions from rows to text.
- Freshness assessment: compares the index's recorded state with a
  frontmatter-level corpus scan, and never writes.
- The skill and docs, as contract text with live-schema pins.

## Out of Boundary

- Deciding the schema. This spec reads it; `analytics-index` and
  `analytics-derived` own it.
- Making existing commands read the index (discovery decision, 2026-10-04).

## Upstream / Downstream

- **Upstream**: `analytics-index` (location, version, schema comments, the
  writer's locking behavior); `distribution` (the packaged-skill machinery
  and wheel contents).
- **Downstream**: the PKM's agents; a possible MCP server follow-on that
  would wrap the same sandboxed connection factory.

## Existing Spec Touchpoints

- **Extends**:
  - `connectors`, by joining the no-network command list in `tech.md` and
    `tests/connectors/test_e2e.py:205`. Carried out inside this spec.
  - The packaged-skill registry (`agentskill.py`, distribution's), by adding
    one entry. Carried out inside this spec.
- **Adjacent**: `fitdocs-workouts` skill (may gain a one-line pointer to the
  new skill, and must not duplicate it); `fitdocs check` (doesn't report
  index freshness unless the design chooses to).

## Constraints

- `query` makes no network request and writes nothing: no data-root writes
  and no index writes. The only exception is DuckDB's transient spill files
  for a query too big for memory, in `<db>.tmp` beside the index. The
  design states how they're cleaned up.
- The sandbox has to hold even if a statement tries to change configuration.
  Tests pin each refused statement class (external file read, `COPY TO`,
  `ATTACH`, `INSTALL`/`LOAD`, `SET` of a locked option), and each pin dies on
  a named mutation that drops the setting.
- NULL is printed distinguishably from zero in every format.
- The skill follows the existing skill pins: frontmatter keys,
  `metadata.version` equal to the project version, command binding,
  published URLs only, and no owned path or managed key spelled out.
