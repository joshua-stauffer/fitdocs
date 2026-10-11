# Research & Design Decisions: dashboards

## Summary
- **Feature**: `dashboards`
- **Discovery Scope**: Complex Integration (a new owned location, a new
  ownership shape, a new command, a chained pass, and amendments to four
  shipped specs), on top of a parallel-built upstream (`chart-kit`, designed
  but not yet implemented at base `560f909`).
- **Key Findings**:
  - The query layer has **no named-parameter path and no column types**
    today: `screen_statement` reads only statement types, `execute_statement`
    calls `conn.execute(sql)` bare, `ResultSet` drops type names, and the
    facade's `IndexConnection.execute(sql, params: Sequence)` — used with
    positional `$1` by the index writer and `freshness.athlete_drift` —
    routes params through `.sql(params=)`, which materialises the whole
    result. `$today` therefore needs a new streaming facade read and query
    amendments before dashboards can bind it; `execute` itself stays as it is.
  - DuckDB 1.5.6 reports `?` and `$1` as the named parameter `'1'`, so
    positional parameters are detectable from `Statement.named_parameters`
    alone; `'$today'` in a literal or comment is not reported (probe P1).
  - The analytics-index post-pass (`cli._run_index_pass`) discards its
    `IndexReport`, and its signature (return `None`) is test-pinned; the pass
    needs that outcome, so the pin moves in the analytics-index amendment.
  - No shared atomic-write or foreign-occupant helper exists (each engine
    keeps a private copy; queue item `2026-09-15-atomic-write-helper-copied-per-engine`).
    Dashboards keeps its own, in one module, and does not widen that debt
    beyond one more copy.
  - Today's declaration and foreign-occupant code assumes tool-owned files
    (`_WRITTEN_AND_OWNED`, `is_generated`). A dashboard page is the inverse
    shape, so it needs its own declaration text and must never be marked
    generated.

## Research Log

### Codebase surveys (four read-only Explore subagents, in parallel)
- **Context**: what the CLI, query layer, ownership surface and published
  docs look like at `560f909`, with exact pins.
- **Sources Consulted**: `src/fitdocs/{cli,layout,declaration,contract,docmerge,agentskill}.py`,
  `src/fitdocs/{query,index,load,history,plans}/`, `tests/**` guards,
  `docs/ownership-contract.md`, `.kiro/steering/*`, `.kiro/specs/{analytics-index,analytics-query,analytics-derived,wiki-contract,connectors,chart-kit,chart-catalog}/`,
  `.kiro/queue/*`.
- **Findings** (the ones that shaped the design):
  - CLI: one flat Typer app, 13 `@app.command`s, no `add_typer` anywhere.
    Count pins: `tests/query/test_cli_query.py:803-812`,
    `tests/test_cli_skill.py:261-269`, `tests/index/test_cli_index.py:604-614`
    (`len == 13`, "Thirteen" in the docstring's first 400 characters, the
    docstring command list ends before "Two further commands").
    `tests/query/test_docs_analytics.py:268-305` requires every
    `fitdocs <cmd> --opt` in a docs bash block to be a root command option.
  - `_run_index_pass(data_root, *, handoff) -> None` (cli.py:503-519) catches
    `Exception`, never `BaseException`; call sites: sync 725, drain 811
    (`pull --sync` goes through drain), regen 909, load 944 (handoff `None`).
    Pins: `tests/index/test_cli_post_pass.py:533-543` (signature, return
    `type(None)`, `returned is None`), `:585-601` (KeyboardInterrupt
    propagates), `:765-832` (exit-code invariance per entry point),
    `:174-212` (output order).
  - Index refresh outcomes (`index/refresh.py:64-72`): REFRESHED, UNCHANGED,
    BUILT, NOT_BUILT, NEEDS_REBUILD, BUSY, STAGED, FAILED. `fitdocs index`
    treats {BUILT, REFRESHED, UNCHANGED} as current (cli.py:474-476).
  - Query: `DEFAULT_MAX_ROWS = 1000`, `DEFAULT_TIMEOUT_S = 30.0`;
    `run_query` opens, checks bookkeeping and schema version, runs one
    statement, `interrupt_quietly` + `close` in `finally`; outcome kinds
    NOT_BUILT / NEEDS_REBUILD / BUSY / UNVERIFIED with fixed messages
    (cli.py:1990-2036); exit 1 for those, 2 for config, 130 for Ctrl-C.
    `is_user_interrupt` and `interrupt_quietly` already exist in
    `query/statement.py`.
  - Boundary guards: `_QUERY_IMPORTERS = {"fitdocs.cli"}`
    (`tests/query/test_boundary.py:15`); `_INDEX_IMPORTERS` = cli plus five
    query modules (`tests/index/test_boundary.py:36-46`); `import fitdocs.cli`
    must not load duckdb (`:625-660`).
  - Ownership: `OWNED_PATHS` (layout.py:133-142) is pinned exactly
    (`tests/test_layout.py:649`), feeds the confinement guard
    (`tests/test_confinement.py:205`) and the contract doc's set-equality
    test; `plans/settings.py:163` refuses a plans path inside any owned
    top-level name. `DECLARED_DIRS` (layout.py:161-166) drives
    `ensure_declarations`, run by sync/drain/regen (`sync.refresh_declarations`),
    `fitdocs history` and `fitdocs plan`, never by `load`
    (`tests/test_declaration_refresh.py:330,456`). Goldens per directory in
    `tests/declaration_golden/`, keyed by `_GOLDEN_NAMES`.
  - `CONTRACT_VERSION = "9"` (contract.py:328), hard-coded `"9"` in
    `tests/index/test_contract_docs.py:140` and
    `tests/index/derived/test_preserved.py:246`; head-paragraph phrases
    pinned in `tests/identity/test_contract_docs.py:177-186`.
  - "Never read back into a document" copies and pins: `tech.md:12-17`
    (pin `tests/connectors/test_network_statements.py:640-644`),
    `docs/ownership-contract.md:10-11` (pin `tests/identity/test_contract_docs.py:183`)
    and `:191-193` (pin `tests/index/test_contract_docs.py:56`),
    analytics-index Req 5.6, and the `contract.py:400` docstring (unpinned).
  - No-network list in `tech.md:45-48`, tail-pinned by
    `tests/connectors/test_network_statements.py:666-669` and
    `tests/query/test_changelog_entry.py:143-146`; the socket-guarded command
    parametrization is `tests/connectors/test_e2e.py:321-332`.
  - `WRITING_ENTRY_POINTS` (`tests/test_confinement.py:1208-1298`), 13
    entries; index ids special-cased at :1344 and :1371 to permit the
    external index directory; `index-derived` requires zero data-root change.
  - Skills: `PACKAGED_SKILLS` (agentskill.py:49-53), pinned by
    `tests/test_skill_locator.py:60,65,205,208`, `tests/test_agent_skill.py`
    (per-skill heading profiles; `_ANALYTICS_HEADINGS` at :91),
    `tests/test_release_artifacts.py:143-152` with
    `release/artifact-policy.toml:58-61`, `tests/test_skill_wheel.py`,
    `tests/test_cli_skill.py:67`, `tests/test_packaging.py:883`,
    `tests/test_releasing_docs.py:573`.
  - Docs: `docs/*.md` are not in the site nav (the site links them by URL);
    `docs/index.md` is the docs table, and
    `tests/test_docs_guarantees.py:1110-1123` lists required entry links.
    The live-pinned block precedent is `tests/query/test_docs_analytics.py`
    (`<!-- schema-reference:start/end -->`, a `regenerate_*` function and a
    module `__main__`).
  - Asset queue items: workout chart assets named by a *computed* stem
    collide across pages after a rename, and a rename cleanup that protects
    only the renaming page's own links can delete an asset another page links
    (`2026-10-01-chart-assets-named-by-computed-stem-collide-across-pages`);
    a timezone change re-stems assets and orphans the old ones
    (`2026-09-29-timezone-change-orphans-chart-assets`).
  - Interrupt queue item `2026-10-08-store-facade-user-interrupt-unwrapped`
    is **open** and the code is unfixed (store.py unchanged since b7e9e95):
    SIGINT surfaces as `RuntimeError('Query interrupted')` with a
    `KeyboardInterrupt` cause, unwrapped by the facade, and `close()` hangs
    unless `interrupt()` runs first. The query layer works around it locally
    (`is_user_interrupt`, `interrupt_quietly`).
- **Implications**: see Design Decisions below; every pin above is named in
  the task that moves it.

### Probe P1: parameters and column types (duckdb 1.5.6, network-blocked)
- **Context**: what screening can see, and what each execution path reports
  as a column type.
- **Sources Consulted**: scratch probe under `sandbox-exec` with
  `(deny network*)` (verified: a socket connect failed with EPERM) and a
  fresh empty HOME, against a synthetic DuckDB file in the scratch dir.
- **Findings**:
  - `duckdb.extract_statements(sql)[i].named_parameters`: `$today` →
    `{'today'}`; `?` → `{'1'}`; `$1` → `{'1'}`; `'$today'` in a literal and
    `-- $today` in a comment → `{}`; `$today … $min` → `{'min','today'}`.
  - Binding `{'today': date}` to SQL that does not use it raises
    "Parameter argument/count mismatch, identifiers of the excess parameters:
    today"; a missing value raises "Values were not provided for the
    following prepared statement parameters: today".
  - `connection.execute(sql, params).description` on 1.5.6 yields
    `DuckDBPyType` objects whose `str()` is the SQL type name (`DATE`,
    `DOUBLE`, `BIGINT`, `VARCHAR`, `BOOLEAN`, `INTERVAL`, `TIMESTAMP`,
    `DECIMAL(5,2)`, `TIME`, `BIGINT[]`, `TIMESTAMP WITH TIME ZONE`);
    `relation.types` gives the same strings. `SELECT NULL` is `INTEGER`.
  - Fetched values: `date`, `float`, `int`, `str`, `bool`, `timedelta`,
    naive `datetime`, `Decimal`, `time`, `list`. Fetching a
    `TIMESTAMP WITH TIME ZONE` value fails without `pytz` (InvalidInputException,
    which `fitdocs query` already hints as "cast … to TIMESTAMP").
  - `$today - 84` is DATE; `$today - INTERVAL 12 WEEK` is TIMESTAMP (matches
    the discovery viability); `DATE + BIGINT` has no overload, so a window
    written `$today - n` needs an INTEGER literal.
- **Implications**: parameter screening uses `named_parameters` (positional
  = an all-digit name); type mapping keys on the type name with the
  parameters stripped (`DECIMAL(5,2)` → `DECIMAL`). duckdb 1.2.0 could not be
  probed (no network to install it); its description vocabulary (`NUMBER`,
  `STRING`, `Date`, `DATETIME`, `TIMEDELTA`, `bool`, `Time`, `list`, `dict`,
  `BINARY`, `UUID`) is taken from the discovery viability record and the
  1.2.0 Python client's `description` mapping, and the implementation task
  verifies it on the floor version as analytics-query did.

### Probe P2: strict YAML (PyYAML 6.0.3)
- **Context**: how to read a directive body without silent coercion.
- **Findings**: a `SafeLoader` subclass with `yaml_implicit_resolvers = {}`
  composes every plain scalar as `str` (`mode: no` → `'no'`,
  `id: 2026-10-11` → `'2026-10-11'`, `012` → `'012'`). Duplicate keys
  compose as two pairs (detectable on the node). Explicit tags keep their tag
  (`!!int 5` → tag `int`). The composed scalar's `style` is `'|'` for
  `|`, `|-`, `|+`, and `'>'` for folded; a folded `sql: >` turns
  `SELECT a\n-- c\nFROM t` into `SELECT a -- c FROM t` (the comment
  swallows `FROM t`); a plain `sql: SELECT 1 # x` loses ` # x`. Aliases
  compose to the same node object, so they are refused at the event level
  (`AliasEvent`, or any event with an anchor). Tabs in indentation are a
  scanner error.
- **Implications**: the directive parser walks `yaml.parse` events for
  anchors and aliases, composes with the resolver-free loader, and checks
  tags, duplicate keys and the `sql` node's style itself.

### Hidden-directive and marker behaviour (discovery viability, re-read)
- Python-Markdown (Zensical extensions), cmark-gfm, markdown-it, GitHub's
  `/markdown` API and Obsidian's reading view hide the directive with blank
  lines, `--` comments, `<`, `<>`, `>=` and `$today` inside; Live Preview
  shows it dimmed. A body containing `-->`/`--!>`, or a comment starting
  `<!-->`/`<!--->`, ends early; four-space indentation makes a code block.
- Because the opening line is fixed as exactly `<!-- fitdocs:chart`, the
  comment text after `<!--` always begins with a space, so the "starts with
  `>` or `->`" trap cannot occur on a recognised directive; only a malformed
  opener can hit it, and malformed openers are reported, never processed.
- `docmerge._MARKER_RE` ids are `[A-Za-z0-9_-]+`, so `begin:chart:<id>`
  (with a colon) is invisible to docmerge; dashboard regions never collide
  with workout-document regions, and docmerge is not reused (it is not
  fence-aware and its id grammar differs).

## Architecture Pattern Evaluation

| Option | Description | Strengths | Risks / Limitations | Notes |
|---|---|---|---|---|
| Pure core + thin I/O shell (selected) | String-level page grammar, directive parser, region composer and snapshot codec are pure; one storage module does file I/O; one binding module touches the query layer; one engine orchestrates | Grammar and codec testable on strings; query reach confined to one module; engine testable with a fake source | More modules than a single file | Mirrors `load/docedit` (pure region edit) + history/plans engines (I/O shell) |
| Reuse `docmerge` regions | Treat chart regions as docmerge regions | No new marker parser | Not fence-aware; id grammar excludes `:`; `merge_regions` semantics (fresh doc vs existing) do not fit an athlete-owned page | Rejected |
| Subcommand group (`fitdocs dashboard check …` as Typer sub-app) | Per-form `--help` | Idiomatic | No precedent; several tests iterate root commands' params; docs-command guard assumes root options | Rejected for one command with a form argument |

## Design Decisions

### Decision: one command with a form argument, not a Typer group
- **Context**: Req 14.1; the brief notes there is no subcommand-group precedent.
- **Alternatives Considered**: 1. Typer sub-app; 2. four separate commands
  (`dashboard-check`, …); 3. one command whose first argument is the form.
- **Selected Approach**: 3: `fitdocs dashboard FORM [TARGET...] [--format text|json] [--out PATH]`,
  FORM ∈ {check, refresh, freeze, kinds} (a `StrEnum` argument).
- **Rationale**: adds exactly one root command (13 → 14) and keeps every
  option a root-command option, so existing command-introspection guards hold.
- **Trade-offs**: per-form help lives in one help text; form-specific option
  misuse (targets with `kinds`, no targets with `freeze`) is checked by hand
  (exit 2).

### Decision: snapshots are immutable files in the page's asset directory, recorded by the region
- **Context**: Req 10; the brief asks the design to weigh in-page storage
  against an orphaned sidecar.
- **Alternatives Considered**:
  1. In the page (a hidden JSON comment in the region): rename-safe, but a
     2,000-row scatter is ~60–100 KB of hidden text in a page an agent reads
     whole; JSON strings could contain `-->`; an agent rewriting a page can
     drop it.
  2. A sidecar named by page and chart (`assets/<page>/<id>.json`), rewritten
     on re-freeze: re-freeze would change every other page that links it; a
     rename silently re-freezes.
  3. A content-addressed store (`assets/snapshots/<hash>.json`): rename-safe
     via a region record, but a dropped region loses the link and a reserved
     directory collides with a page named `snapshots`.
  4. **Selected**: immutable generation files
     `dashboards/assets/<page>/<id>.snapshot-<n>.json`, created no-replace;
     the region records the path it was drawn from
     (`<!-- fitdocs:snapshot assets/<page>/<id>.snapshot-<n>.json -->`);
     lookup is the region's record first, then the highest generation for
     the current page and id.
- **Rationale**: a rename keeps the record (the old file is still there and
  never deleted); a dropped region falls back to the latest generation for
  that page and chart; a copied page shares a file nobody can change;
  re-freeze writes generation n+1 and repoints only its own region.
- **Trade-offs**: rename *and* dropped region together lose the link (the
  next render takes a new snapshot); documented. Snapshot files accumulate
  (never auto-deleted, by requirement).
- **Follow-up**: the pkm `.gitignore` decision for `dashboards/assets/`
  (roadmap Direct Implementation Candidate) must not ignore `*.snapshot-*.json`;
  `docs/dashboards.md` says so. Considered and rejected: a separate owned
  `dashboards/snapshots/` directory (a cleaner ignore rule, but a third owned
  path the brief and roadmap do not list).

### Decision: assets named by page and chart id in a per-page directory, cleaned by whole-directory reference scan
- **Context**: Req 6; the two asset queue items.
- **Selected Approach**: `dashboards/assets/<page>/<id>.svg`. Page names and
  chart ids share one slug grammar (`[a-z0-9]+(-[a-z0-9]+)*`), so `/` and
  `.` never occur inside either and no two charts share a path. A chart image
  is removed only if it carries the fitdocs mark and no markdown file under
  `dashboards/` (outside `assets/`) mentions its relative path; if any such
  file cannot be read, nothing is removed that run.
- **Rationale**: no computed value enters a name, so nothing re-stems; the
  reference scan covers every page, not the one being written.
- **Trade-offs**: links to a dashboard image from outside `dashboards/` are
  not protected (documented: embed the page instead).

### Decision: the query layer offers a multi-statement session; dashboards never imports the index
- **Context**: Req 7.8 (one connection per run), Req 20.2 (reach DuckDB
  only through `fitdocs.query`).
- **Selected Approach**: analytics-query Amendment 1 extracts `run_query`'s
  open-and-check sequence into `open_session(data_root, env)`, returning a
  `QuerySession` (screen, run with params, close-with-interrupt) or a
  `SessionUnavailable` with the same outcome kinds `fitdocs query` reports.
  Session methods raise only query-defined exceptions (parse failures become
  `StatementFailed`). Only `fitdocs.dashboards.binding` imports it; the index
  importer allow-list is unchanged.
- **Rationale**: one place opens, verifies and closes sandboxed connections;
  the interrupt workaround (`interrupt_quietly` before close) is reused, not
  copied.

### Decision: a new named-parameter read on the facade; `execute` untouched
- **Context**: viability (materialisation on `.sql(params=)`), Req 7.3.
- **Correction (Step 3.5 round 1)**: the first design widened
  `IndexConnection.execute`'s params to a `Mapping` and called
  `freshness.athlete_drift` "the one existing positional caller". That was
  false: the index writer binds positional `$1` through `execute` at
  `store.py:400`, `:426`, `:486`, `:500`, `:513`, `:523-524`, and tests
  monkeypatch `execute` with the `Sequence` signature
  (`tests/index/test_store.py:1172-1179`, `:1510-1517`, `:1541-1546`;
  `tests/query/test_store_facade.py:264`). Widening it would have broken
  every index write (`dict((page_key,))` raises) and mypy. The error came
  from generalising a subagent's "only query-side use of a parameter" to the
  whole facade.
- **Alternatives Considered** (controller's options): (a) a new
  named-parameter method, `execute` unchanged; (b) accept both shapes in
  `execute`; (c) migrate every positional caller to named parameters.
- **Selected Approach** (controller ruling: option a):
  `IndexConnection.execute_named(sql, params: Mapping[str, object])` runs
  `connection.execute(sql, dict(params))`, or `connection.execute(sql)` for
  an empty mapping (nothing bound), and streams `fetchmany` from the cursor.
  `execute` keeps its signature, its `.sql(params=)` routing and all of its
  callers and tests. The query session always reads through `execute_named`;
  `fitdocs query` keeps the relation path.
- **Trade-offs**: positional `execute` keeps the materialisation hazard for
  any future large positional read; the amendment states it as out of scope
  and the controller queues the residual. The relation path (query) and the
  cursor path (dashboards) report type names in different vocabularies on
  1.2.0; the dashboards type map covers both.
- **Evidence for the latency pin** (probe P3, duckdb 1.5.6, network-blocked,
  2026-10-11): for `SELECT range AS n FROM range(N) WHERE range >= $lo`, the
  first `fetchmany(10)` took 0.006 s at 42 MB peak RSS through
  `execute` + `fetchmany` versus 0.879 s at ~297 MB through
  `.sql(params=)` at N = 5,000,000, and 0.000 s / 42 MB versus 3.5 s / ~930 MB
  at N = 20,000,000. Task 2.1 uses N = 5,000,000 in a child process and
  asserts the child's peak RSS, so observing the mutation costs ~300 MB, not
  gigabytes.
- **Empty mapping** (same probe set): `connection.execute("SELECT 1", {})`
  and `connection.execute("SELECT 1")` both return `[(1,)]`, and both raise
  the same "Values were not provided … today" error for `SELECT $today`, so
  "binds nothing for an empty mapping" is observable only as the call shape
  (task 2.1 pins it with a recording proxy).

### Decision: escaping caption and alt text with the kit's formatter
- **Context**: the image link's text is the athlete's title; captions carry
  the athlete's `window` text.
- **Selected Approach**: `fitdocs.render.charts.kit.format.escape_markdown`
  and `clean_text` (chart-kit design § Formatter). See the seam note below.

## Chart-kit seam review (consumer side)
- **Consumed by exact name**: `fitdocs.units.unit_for_column`;
  `fitdocs.render.charts.kit.{validate_chart, render_chart, describe_kinds, kind_names, ChartRequest, ChartData, Column, ValueKind, ChartProblem, ProblemCode, ChartError, RenderedChart}`.
- **Gap G1 (minor)**: the facade does not re-export `escape_markdown` or
  `clean_text`, and chart-kit's Revalidation Triggers do not list
  `kit.format`'s signatures. Dashboards needs both for text it writes
  outside the chart (image alt text, caption, the not-rendered note).
  **Accommodation**: import the two functions from
  `fitdocs.render.charts.kit.format` (a designed, public module) in one
  dashboards module (`region.py`), allow exactly that import in the
  dashboards boundary guard, and pin the behaviour relied on (`[`, `]`, `*`,
  `_`, `\` escaped; control characters replaced) with a dashboards test, so
  a kit change that breaks it reds a dashboards test. **Report**: chart-kit
  could re-export both from the facade or list them as a revalidation
  trigger; no chart-kit edit is made here.
- **Gap G2 (none, noted)**: `ProblemCode` is chart-kit's closed enum;
  dashboards' own codes are a separate `StrEnum` and every reported problem
  carries `source` (`chart` or `dashboard`), so a code chart-catalog appends
  can never be confused with a dashboards code.
- **Gap G3 (none, noted)**: `validate_chart` needs columns, which a
  dashboard has only after running the SQL; the check form therefore runs
  the query and calls `render_chart` in memory (stage 1 is included), and
  never validates a relative chart's encodings without the index.

## Risks & Mitigations
- A pass with many slow charts lengthens `sync` — each statement is bounded
  by the 30 s query time limit and charts run sequentially; the pass report
  names timeouts. No pass-level budget (out of scope; revisit if real use
  shows it).
- The open interrupt queue item — dashboards uses the query session, which
  interrupts before close; a real-process SIGINT test (precedent
  `tests/query/test_interrupt.py`) covers `fitdocs dashboard refresh`.
- 1.2.0 type and parameter vocabularies unverified locally — the binding
  type map is a two-vocabulary table plus value checks; task 4.3 runs the
  parameter and type tests on 1.2.0 where the environment allows, and an
  unrecognised spelling degrades to a `column_type` problem, never a wrong
  kind.
- An athlete's editor writing a page during a pass — re-read before replace;
  a changed page is skipped and reported.
- The CLI writes `src/__pycache__` when run; a full pytest in flight in the
  same worktree then fails `test_bytecode_hygiene` spuriously (peer WARN).
  Implementation tasks run CLI smokes only between suite runs.
- Linux CI has no TMPDIR and Rosetta containers write `HOME/.cache/rosetta`
  (peer MERGED line): every dashboards test uses `tmp_path`, never
  `tempfile.gettempdir()`, and HOME-purity assertions are scoped to fitdocs
  paths.

## References
- `.kiro/specs/chart-kit/design.md` § Settled Seams for Wave 2 (authoritative
  at 560f909).
- `.kiro/steering/roadmap.md` § Phase 11 (decisions, viability, boundary
  strategy, Existing Spec Updates).
- `.kiro/specs/dashboards/brief.md`.
- `.kiro/queue/2026-10-08-store-facade-user-interrupt-unwrapped.md`,
  `2026-10-01-chart-assets-named-by-computed-stem-collide-across-pages.md`,
  `2026-09-29-timezone-change-orphans-chart-assets.md`,
  `2026-09-15-atomic-write-helper-copied-per-engine.md`.
- CommonMark 0.31 §4.5 (fenced code), §4.6 (HTML blocks, type 2).
