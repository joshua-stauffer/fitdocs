# Brief: dashboards

## Problem

The analytics index (Phase 10) answers the athlete's training questions in
SQL in a second or two. The first real session, on 2026-10-11 against 2,562
workouts, asked "how do cadence, HR and pace relate?" and got answers. But
those answers end up in a chat transcript:

- **Nothing puts them on a wiki page.** There is no way to keep a chart of a
  learning beside the athlete's own reading of it, in the PKM the athlete
  already uses.
- **Nothing keeps a chart current.** A "last 12 weeks of weekly volume"
  chart is stale the day it's drawn unless someone re-runs the query and
  redraws it.
- **Nothing holds a finding still.** "This is what my cadence looked like
  before the hill block" is a point-in-time record. Re-running its query
  later can change it: a late import, a threshold change or a methodology
  change all move the data underneath it.

## Current State

- `fitdocs query` (`src/fitdocs/query/`) runs one SELECT in a locked,
  read-only DuckDB sandbox:
  - the connection factory is `open_sandboxed` (`sandbox.py:123-165`);
  - screening and execution are `run_statement` (`statement.py:221-233`), with
    a timer interrupt and a `max_rows+1` truncation check.
  - `ResultSet` keeps column names but **drops their types**
    (`statement.py:200-205`), although the store facade exposes
    `ResultColumn(name, type_name)` (`index/store.py:99-120`).
  - Units are inferred only from column-name suffixes (`index/schema.py:77-97`,
    `query/schemaview.py:86-90`).
- Only `fitdocs.cli` may import `fitdocs.query` (`tests/query/test_boundary.py:15`,
  `:230-240`), and the index importer allow-list is `cli` plus five query
  modules (`tests/index/test_boundary.py:36-46`).
- **The index is never read back into a document.** This is stated in
  `tech.md:12-17`, `docs/ownership-contract.md:10-11` and `:191-193`, and
  analytics-index Req 5.6 (`requirements.md:186`). It is pinned by
  `tests/index/test_contract_docs.py:56`,
  `tests/identity/test_contract_docs.py:183` and
  `tests/connectors/test_network_statements.py:640-644`. analytics-query
  ruled saved queries and charting out of scope (`requirements.md:85-88`).
  This spec makes the one named exception.
- **Post-pass wiring is hand-written.** `cli._run_index_pass` (`cli.py:503-519`)
  runs at the end of `sync SOURCE` (`:725`), drain (`:811`), `pull --sync`
  (through drain), `regen` (`:909`) and `load` (`:944`). It catches
  everything, never changes the exit code, and **discards the
  `IndexReport`**, so nothing after it knows whether the refresh succeeded.
  It closes its lock before returning.
- **Region editing inside a page the user otherwise owns** already exists:
  - `load/docedit.py` (`classify_load_region` :156, `replace_load_region`
    :208) rewrites only the bytes between the `load` markers and classifies
    anything else there as the user's.
  - `docmerge.py` holds the generic marker grammar
    (`<!-- fitdocs:begin:<id> -->`, column 0, no nesting).
- **Ownership:**
  - `layout.OWNED_PATHS` (`layout.py:133-159`) is the single source for the
    published contract and the write-confinement guard
    (`tests/test_confinement.py:205`).
  - `DECLARED_DIRS` (`layout.py:161-176`) get a generated `AGENTS.md`, whose
    text comes from `declaration.py` with one golden per directory.
  - `CONTRACT_VERSION` is `"9"` (`contract.py:328`), and each new owned
    location has been a wiki-contract amendment.
- The single clock read is `cli._today()` (`cli.py:2063-2075`).
- Skills are declared in `PACKAGED_SKILLS` (`agentskill.py:46-54`), three
  today.
- There are 13 CLI commands, guarded in several places
  (`tests/query/test_cli_query.py:803-812`, `tests/test_cli_skill.py:261-269`,
  `tests/index/test_cli_index.py:604-614`).

## Desired Outcome

1. **A `dashboards/` directory in the data root** that fitdocs owns as a
   location: declared with its own `AGENTS.md`, listed in the ownership
   contract, and with `dashboards/assets/` for chart files. The pages in it
   are co-owned:
   - **the athlete owns** creating and deleting pages, every byte of prose,
     the frontmatter (the design states any key fitdocs manages), and every
     directive;
   - **fitdocs owns** the chart regions and the files in `dashboards/assets/`.
2. **A chart directive.** A hidden, multi-line HTML comment
   (`<!-- fitdocs:chart … -->`) whose body is YAML: `id` (unique on the
   page), `kind` (from the chart-kit registry), `mode` (`relative` or
   `frozen`), `sql` (one SELECT), the kind's encodings, a title and options.
   Directly below it sits the fitdocs-owned region
   `<!-- fitdocs:begin:chart:<id> -->` … `<!-- fitdocs:end:chart:<id> -->`,
   which holds:
   - the image link (`![<title>](assets/<page>/<id>.svg)`; the naming rule
     is in Constraints) or, for markdown kinds, the markdown itself;
   - a caption stating the window and the latest date present in the
     result (never the run date; see Constraints);
   - optionally, the plotted rows as a small markdown table, so an agent
     reading the wiki can see the numbers.

   fitdocs creates the region when it's missing, and rewrites only the bytes
   between its markers.
3. **Relative charts.** The SQL runs with `$today` bound to the run's local
   date, through analytics-query's sandbox (one read-only connection per
   pass, the same timeout, a per-chart row cap). The rows go through
   chart-kit, and the region and asset are written **only if a byte
   changed**.
4. **Frozen charts are snapshots.**
   - On the first render, the SQL runs once, with `$today` bound to that day
     and recorded. fitdocs stores the result rows together with the
     directive's digest and the date.
   - Every later render draws from the stored rows and never re-queries.
     Those renders need no index, so they work after index deletion, after a
     schema bump and on a machine without one. A chart-kit upgrade can
     restyle them.
   - Re-snapshotting is explicit.
   - A directive edited after its snapshot is reported, never silently
     re-queried.
5. **Refresh cadence.** A dashboard pass runs after the index pass at the
   end of `sync SOURCE`, drain, `pull --sync`, `regen` and `load`, and only
   when that refresh succeeded. `_run_index_pass` returns its outcome so the
   pass can know.
   - Otherwise (not built, busy, needs rebuild, failed), relative charts are
     left as they were and the report says why. No pass ever starts an index
     build.
   - The pass never fails the command and never changes its exit code.
   - Commands that don't refresh the index (`history`, `plan`, `check`, …)
     don't run it.
6. **One new command, `fitdocs dashboard`.** It has forms for:
   - checking pages without writing: directive syntax, kinds, encodings
     against the actual result columns, SQL screening;
   - refreshing all pages or named ones;
   - freezing or re-freezing a chart;
   - listing the chart kinds from the registry with their channels.

   Its errors are structured enough for an agent to iterate in a loop
   without reading the source. The design decides the exact forms; there is
   no subcommand-group precedent (`cli.py:294-300`).
7. **Failure isolation per chart.** A bad directive, an SQL error, a timeout,
   an encoding mismatch or an over-bound result affects only that chart:
   - an already-rendered chart is left as it was;
   - a never-rendered chart gets a short visible "not rendered: <reason>"
     note in its region.

   The pass report names every failure, and other charts and pages
   proceed.
8. **A fourth packaged skill, `fitdocs-dashboards`**, plus
   `docs/dashboards.md`. Together they teach:
   - the directive;
   - relative versus frozen;
   - `$today` windows;
   - keeping unit suffixes on aliases (`AS distance_km`);
   - the check loop;
   - who owns which bytes.

   The skill points at `fitdocs dashboard`'s kinds listing rather than
   copying the catalogue, so `chart-catalog` landing later doesn't make it
   stale. `fitdocs-analytics` gains a pointer to it.

## Approach

**Hidden directives in athlete-owned pages, with fitdocs-owned regions**
(maintainer, 2026-10-11). This keeps one file per dashboard, and prose can
go anywhere. It is the `load/docedit.py` polarity: fitdocs owns regions
inside a page whose other bytes it doesn't own. SQL runs only through
analytics-query's sandbox. The MERGED log line for analytics-query says to
consume `src/fitdocs/query` and not add a second SQL surface. Charts render
only through chart-kit's registry.

## Scope

- **In**:
  - the `dashboards/` owned location, its declaration, its contract entry,
    and the page type and recognition rule;
  - the directive grammar, its parser and validation;
  - region creation and surgical rewrite;
  - asset naming and stale-asset cleanup (frozen snapshots excepted);
  - query execution with `$today`, typed result columns and the unit
    mapping;
  - snapshot storage, the freeze and re-freeze lifecycle, and digest-change
    reporting;
  - the chained pass, with `_run_index_pass` returning its outcome;
  - `fitdocs dashboard`;
  - per-chart failure isolation;
  - idempotence;
  - the skill and the docs page;
  - the existing-spec updates listed below;
  - steering text (`tech.md`'s database and network paragraphs,
    `structure.md`'s import direction);
  - the CHANGELOG entry.
- **Out**:
  - chart rendering itself (`chart-kit`, `chart-catalog`);
  - charts in workout, history or block documents;
  - fitdocs writing prose or calling an LLM (the athlete's assistant writes,
    fitdocs renders);
  - write SQL, user tables, persisted views;
  - a scheduler or daemon (the cadence is the writing commands);
  - an auto-generated index page of dashboards (follow-on);
  - building the index from the dashboard pass;
  - cross-machine coordination of relative renders.

## Boundary Candidates

- **Page model**: recognition, the directive grammar and the region grammar.
  Pure, testable on strings.
- **Data binding**: the sandboxed execution, typed columns, unit tokens and
  `$today`. This is the only place that touches `fitdocs.query`.
- **Snapshot store**: format, location and lifecycle.
- **Pass and CLI wiring**: chaining after the index pass, the report, the
  command.
- **Agent surface**: the skill, the docs and the kinds listing.

## Out of Boundary

- How any chart looks: chart-kit owns layout, theme, units, kinds and
  validation of encodings.
- Index schema and producers: the dashboards pass never writes the index.
- Workout, history and block documents: they keep never reading the index.

## Upstream / Downstream

- **Upstream**:
  - `chart-kit` (data contract, registry, validation, rendering);
  - `analytics-query` (sandbox, statement screening and execution);
  - `analytics-index` (location, refresh outcome);
  - `wiki-contract` (ownership contract);
  - `docmerge` and `load/docedit` patterns.
- **Downstream**:
  - `chart-catalog` kinds appear in dashboards automatically through the
    registry;
  - pkm's `wiki-schema.md` section for `dashboards/` (pkm repo);
  - follow-ons such as charts inside block notes, a dashboards index page,
    an MCP tool.

## Existing Spec Touchpoints

- **Extends** (carried out inside this spec):
  - `analytics-index`: Req 5.6 gains the named exception. Dashboard chart
    regions and assets are the only document content produced from the
    index; workout, history and block documents still never read it.
    `_run_index_pass` returns its outcome. The text pins move in the same
    change.
  - `analytics-query`:
    - result columns keep their type names;
    - `fitdocs.dashboards` joins the importer allow-list;
    - the "saved queries, charting" out-of-scope line is marked superseded
      by Phase 11.
  - `wiki-contract`: a new owned location and declared directory, the
    chart-region policy (tool-owned regions inside an athlete-owned page),
    the page type, and `CONTRACT_VERSION` `"9"` → `"10"`.
  - `connectors`: `dashboard` joins the no-network command list (`tech.md`,
    `tests/connectors/test_e2e.py:205`).
- **Adjacent**:
  - `chart-catalog` (parallel; append-only on the registry);
  - `docs-site` (a new docs page in the nav);
  - `analytics-derived` (its tables are what most dashboards query).

## Constraints

- **Idempotent, with no churn from the clock alone.** A second identical
  run writes nothing. This is the "a second sync changes nothing" property
  Phase 8 established.
  - **The run date never enters rendered bytes** (taken at discovery).
    Captions state the window as the directive wrote it and the latest date
    present in the result, never the run date.
  - A relative chart's bytes therefore change when its rows change, and a
    day with no new data rewrites nothing in an iCloud- and git-backed wiki.
  - Rows still change as old days fall out of a moving window, which is
    inherent in a relative chart.
- **Query execution** (viability, 2026-10-11; duckdb 1.2.0 and 1.5.6):
  - **Not `.sql(params=…)`.** `IndexConnection.execute` uses
    `.sql(sql, params=…)`. With non-empty params that call materialises the
    whole result before `fetchmany` caps it: 60M rows reached 7 GB on 1.5.6,
    and a 2 s interrupt took 21 s to land.
  - **Use `execute` + `fetchmany`.** Parameterised statements run through
    `connection.execute(sql, params)` + `fetchmany`, which is flat in memory
    and interrupts promptly.
  - **Widen the params type.** The facade's params type goes from `Sequence`
    to `Mapping`.
- **Binding `$today`:**
  - **Bind only when used.** Bind `today` only when screening reports it in
    `Statement.named_parameters`. DuckDB errors on an excess parameter, so
    "always bind" is not an option.
  - **Refuse every other parameter**, including positional `?`/`$1`.
  - **Classify by screening, not by message text.** Parameter errors are
    classified by screening before execution. DuckDB's messages differ by
    version.
- **Date arithmetic.** `$today - INTERVAL 12 WEEK` is a TIMESTAMP, while
  `$today - 84` stays a DATE. The skill teaches the DATE form, or a cast, so
  that comparisons against DATE columns don't surprise anyone.
- **Column types.** They come from a mapping that covers both
  `cursor.description` vocabularies (1.2.0 reports `Date`/`NUMBER`, 1.5.6
  reports `DATE`/`DOUBLE`/`BIGINT`), or from the returned Python values.
  They never come from one version's spelling.
- **Snapshots are the one tool-written artifact in the data root that can't
  be re-derived.** They are never deleted automatically, and they survive
  `regen`, `index --rebuild` and chart-kit upgrades. The design picks the
  storage: in the page, or a sidecar in `dashboards/assets/`. It weighs page
  weight against the risk of an orphaned sidecar when a page is renamed.
- **No network.** The pass and `fitdocs dashboard` make no request, and
  there is no map kind.
- **One clock read.** `$today` comes from `cli._today()`. The dashboards
  package reads no clock, enforced by a boundary guard.
- **Absent data is never drawn as zero.** NULL passes through as `None`, and
  an empty result shows an explicit no-data state.
- **Write confinement.** Writes go only to `dashboards/` and its `assets/`.
  A `WRITING_ENTRY_POINTS` entry covers the pass and the command.
- **Symlinks and foreign occupants are refused the way history and plans
  refuse them.** Writes are atomic.
- **The directive must stay a comment** (viability, probed against
  Python-Markdown with Zensical's extensions, cmark-gfm, markdown-it,
  GitHub's `/markdown` API, and Obsidian's bundled remark tokenizer):
  - The directive and markers start at column 0. Four spaces of indent turn
    the directive into a visible code block.
  - The parser refuses a body that contains `-->` or `--!>`, or that starts
    with `>` or `->`. Any of these ends the comment early and leaks the rest
    of the SQL as visible text, GitHub included.
  - Blank lines inside the comment are safe: a CommonMark type-2 HTML block
    ends only at `-->`.
  - Obsidian's Reading view hides the directive. **Live Preview**, the
    default editing mode, shows it as dimmed source. The docs and skill say
    so.
- **Strict YAML.** PyYAML's `safe_load` silently changes values:
  - `mode: no` becomes `False`;
  - `id: 2026-10-11` becomes a date, and `012` becomes 10;
  - duplicate keys pass, and the last one wins;
  - a plain `sql: SELECT 1 # x` loses its tail;
  - and a folded `sql: >` merges a `--` comment line into the next line,
    swallowing `FROM t`.

  So:
  - the parser uses a loader with no implicit type resolvers that rejects
    duplicate keys;
  - it requires `sql` to be a literal `|` block scalar, checked on the
    composed node's style;
  - it validates `id` against a slug grammar and `mode`/`kind` against their
    enums.
- **Fence-aware markers.** `docmerge._MARKER_RE` matches column-0 markers
  across the raw text. A directive or marker quoted inside a fenced code
  example (the docs and skill will have them) must be skipped or refused,
  never treated as live.
- **Asset names that can't collide.** `assets/<page>-<id>.svg` collides
  (page `a-b` with id `c`, against page `a` with id `b-c`). Use a
  per-page directory (`assets/<page>/<id>.svg`) or a separator ids can't
  contain. This is the same family as the open queue item
  `2026-10-01-chart-assets-named-by-computed-stem-collide-across-pages`.
- **A new ownership shape.** Workout documents are fitdocs pages with user
  regions. A dashboard is the inverse: an athlete page with fitdocs regions.
  The ownership contract (`docs/ownership-contract.md`) gains this as a
  new category. pkm's rule "never add a region marker to a document that
  lacks one" has to be reconciled in pkm's `wiki-schema.md`, which is pkm's
  work.
  - A dashboard page is **not a generated document**. fitdocs never writes
    `contract.DOC_BANNER` or a `GENERATED_PREFIX` line into one: the banner
    claims everything outside the regions is replaced
    (`contract.py:810-813`), and `contract.is_generated` (`:989`) would
    then misclassify the page.
  - `is_workout_document` scans must keep skipping dashboard pages.
- The CLI command count goes from 13 to 14. `PACKAGED_SKILLS` goes from 3
  to 4. Both are append-only with their guards.
