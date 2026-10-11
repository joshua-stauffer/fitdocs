# Requirements Document

## Project Description (Input)
**Who has the problem.** An athlete who keeps a markdown wiki, and the
athlete's LLM assistant, who answer training questions in SQL against the
analytics index (Phase 10) and want those answers to live on wiki pages as
charts beside the athlete's own reading of them.

**Current situation.** `fitdocs query` answers a question in a second or two,
but the answer ends up in a chat transcript. Nothing puts a chart on a wiki
page; nothing keeps a "last 12 weeks" chart current as workouts arrive; and
nothing holds a point-in-time finding still once a late import, a threshold
change or a methodology change moves the data under it. The index is, by a
pinned Phase 10 rule, never read back into a document.

**What should change.** A fitdocs-owned `dashboards/` location in the data
root holds athlete-written pages. Hidden chart directives in a page declare a
chart's kind, mode, SQL and encodings; fitdocs owns one region below each
directive and the chart files in `dashboards/assets/`, and never touches the
prose. Relative charts re-run their SQL through analytics-query's sandbox with
`$today` bound, after every successful index refresh and on demand; frozen
charts are snapshots drawn from stored rows and never re-queried. A new
`fitdocs dashboard` command checks, refreshes, freezes and lists kinds; failures
are isolated per chart; a fourth packaged skill and `docs/dashboards.md` teach
the surface. Charts draw only through chart-kit's registry.

Source: `.kiro/specs/dashboards/brief.md`; Phase 11 of
`.kiro/steering/roadmap.md`. Dependencies: `chart-kit`. Parallel sibling:
`chart-catalog`.

## Introduction

A dashboard is a markdown page in the athlete's wiki that the athlete, or the
athlete's assistant, writes, and on which fitdocs draws charts from the
analytics index. The athlete writes every word; fitdocs draws the charts and
writes nothing else on the page.

Terms used below:
- The **data root** is the athlete's configured output directory (the wiki,
  when fitdocs is installed in one).
- A **dashboard page** is a markdown file in the data root's `dashboards/`
  directory that meets the page rule of Requirement 1. Its **page name** is the
  file name without `.md`.
- A **chart directive** is a hidden HTML comment in a page that declares one
  chart: its id, kind, mode, SQL, channel bindings, options and title. The
  directive belongs to the athlete.
- A **chart region** is the span of lines between a begin marker and an end
  marker directly below a directive. fitdocs owns it and writes the chart
  there.
- A **chart asset** is the image file fitdocs writes for a chart in
  `dashboards/assets/`. A **snapshot** is the file in which fitdocs stores a
  frozen chart's result rows.
- A **relative** chart is redrawn from a fresh run of its SQL. A **frozen**
  chart is drawn from its snapshot, taken once, and never re-queried.
- **`$today`** is the one SQL parameter a chart may use. It is bound to the
  **run date**: the local calendar date of the command that renders the chart.
- A **run** is one execution of the dashboard work, either the **pass** that
  follows an index refresh inside another command, or one invocation of
  `fitdocs dashboard`.
- A **problem** is one structured finding that stops one chart, or one page,
  from being rendered. A **notice** is a finding that does not.
- The **chart kit** is the drawing layer specified by `chart-kit`: its
  **registry** of chart kinds, its validation and its unit vocabulary.

## Boundary Context

- **In scope**: the `dashboards/` location, its declaration file and its
  ownership-contract entry; the page rule; the directive and region grammar
  and its validation; region creation and in-place rewrite; chart asset naming
  and stale-asset removal; running each chart's SQL in the analytics query
  sandbox with `$today`; typed result columns and unit tokens; snapshots and
  the freeze and re-freeze lifecycle; the pass after an index refresh; the
  `fitdocs dashboard` command; per-chart failure isolation; idempotence; the
  `fitdocs-dashboards` skill and `docs/dashboards.md`; the published-rule
  changes this feature makes to the analytics index, the query layer, the
  ownership contract and the no-network command list; the steering records
  and the CHANGELOG entry.
- **Out of scope**: how any chart looks, which kinds exist and how an encoding
  is validated (`chart-kit`, `chart-catalog`); charts in workout, history or
  block documents; fitdocs writing prose or calling a language model; SQL that
  writes, user tables or saved views; a scheduler or background process; a
  generated index page listing the dashboards; building the index from a
  dashboard run; coordinating relative charts across machines; registering
  `dashboards/` in the pkm wiki's schema (the pkm repository's work).
- **Adjacent expectations**: the chart kit validates a chart request against
  typed columns and draws it, or returns structured problems, and lists its
  registered kinds; kinds that `chart-catalog` registers become available on
  dashboard pages with no change here. The analytics query layer runs one
  read-only statement under its sandbox and time limit. The analytics index is
  refreshed by the writing commands, and its refresh outcome decides whether
  the pass runs. The athlete's assistant writes and edits pages; fitdocs only
  checks and renders them.

## Requirements

### Requirement 1: The Dashboards Location and Its Pages
**Objective:** As an athlete, I want one recognised place in my wiki for
dashboard pages, so that my assistant knows where charts live and which bytes
fitdocs may touch.

#### Acceptance Criteria
1. fitdocs shall treat `dashboards/` in the data root as an owned location, with `dashboards/assets/` as the location of the files it writes for charts, and shall list both in its published ownership contract.
2. fitdocs shall place a generated agent-instructions file, `AGENTS.md`, in `dashboards/`, refreshed by the same commands that refresh the other declared directories' files, stating that the pages belong to the athlete and that fitdocs owns only the chart regions in them and the files in `dashboards/assets/`.
3. fitdocs shall recognise as a dashboard page each regular file directly in `dashboards/` named `<page name>.md`, where a page name is one or more groups of lowercase ASCII letters and digits joined by single hyphens, and shall not read files in subdirectories of `dashboards/` as pages.
4. If a markdown file directly in `dashboards/`, other than the generated `AGENTS.md`, has a name that is not a valid page name, then fitdocs shall leave it unchanged and report it, naming the file and the page-name rule.
5. fitdocs shall recognise a dashboard page by its location and name alone, shall neither require nor write any frontmatter key on it, and shall document `dashboard` as the page type an athlete's wiki may record in the page's frontmatter.
6. fitdocs shall never write a generated-file banner or a generated-file provenance line into a dashboard page.
7. While dashboard pages exist, the workout, history and block commands shall continue to ignore them, whatever frontmatter they carry.

### Requirement 2: Who Owns Which Bytes
**Objective:** As an athlete, I want fitdocs to touch only the charts on my
page, so that my prose, headings, frontmatter and directives are never
rewritten.

#### Acceptance Criteria
1. fitdocs shall never create, rename or delete a dashboard page, and shall never change a byte of a dashboard page outside its chart regions, apart from inserting a missing region (Requirement 5.2).
2. fitdocs shall own the bytes between a chart region's begin and end markers and may replace them in full.
3. fitdocs shall own the chart assets and snapshots it writes in `dashboards/assets/`.
4. The published ownership contract shall describe a dashboard page as its own category, a page owned by the athlete that holds regions owned by fitdocs, distinct from the generated documents that hold user-owned regions.

### Requirement 3: The Chart Directive Form
**Objective:** As the athlete's assistant, I want a chart declaration that
stays hidden in every common markdown viewer and that fitdocs finds reliably,
so that a page reads as prose plus charts.

#### Acceptance Criteria
1. fitdocs shall recognise a chart directive as the lines from an opening line that is exactly `<!-- fitdocs:chart`, starting at column 0, through the next line that is exactly `-->`, starting at column 0; the lines between are the directive body.
2. fitdocs shall accept blank lines inside a directive body.
3. If a directive body contains `-->` or `--!>`, then fitdocs shall refuse the chart with a problem stating that the sequence ends the comment early and exposes the rest of the directive as visible text.
4. If a directive's opening line has no closing line before the end of the page, then fitdocs shall refuse the chart, naming the opening line.
5. If a line outside fenced code contains `<!-- fitdocs:chart` but is not a valid opening line (indented, or with other text on the line), then fitdocs shall report it as a malformed opening line, naming the line and the column-0 rule, and shall not treat it as a chart.
6. fitdocs shall ignore directive opening lines and region markers that appear inside fenced code blocks (backtick or tilde fences), so that examples quoted on a page are never treated as live charts or regions.

### Requirement 4: The Directive's Content
**Objective:** As the athlete's assistant, I want the directive body read
exactly as I wrote it, with every mistake named, so that a value is never
silently changed into something else.

#### Acceptance Criteria
1. fitdocs shall read the directive body as a YAML mapping in which every scalar is the text exactly as written, with no conversion of any value to a boolean, number, date or null.
2. If the directive body does not parse, is not a mapping, repeats a key, or uses an explicit type tag, an anchor or an alias, then fitdocs shall refuse the chart with a problem naming the page line.
3. fitdocs shall require the keys `id`, `kind`, `mode`, `title` and `sql`, and shall accept the optional keys `channels`, `options`, `window` and `show_rows`; if a required key is missing or any other key appears, then fitdocs shall refuse the chart, naming the key and listing the accepted keys.
4. If `id` is not a chart id (one or more groups of lowercase ASCII letters and digits joined by single hyphens, at most 64 characters long), then fitdocs shall refuse the chart, stating the rule.
5. If two directives on one page have the same `id`, then fitdocs shall refuse both charts and leave both of their regions unchanged.
6. If `mode` is neither `relative` nor `frozen`, then fitdocs shall refuse the chart, listing both values.
7. If `sql` is not written as a literal block scalar (`sql: |`), then fitdocs shall refuse the chart with a problem stating that other scalar styles can fold or cut SQL text.
8. fitdocs shall pass `kind`, `title`, the `channels` mapping (channel name to result column name) and the `options` mapping (option name to value) to the chart kit unchanged, and shall report the chart kit's problems for any of them, including an unregistered kind with the list of registered kinds.
9. If `channels` or `options` is not a mapping of names to single-line scalar values, if `title` or `window` is not single-line text, or if `show_rows` is neither `true` nor `false`, then fitdocs shall refuse the chart, naming the key.
10. fitdocs shall never infer a kind, a channel binding or an option value from the SQL, the result or the page.

### Requirement 5: Chart Regions
**Objective:** As an athlete, I want each chart to appear right below its
directive in a region that fitdocs alone rewrites, so that charts stay current
without disturbing anything around them.

#### Acceptance Criteria
1. fitdocs shall delimit each chart's region by the whole lines `<!-- fitdocs:begin:chart:<id> -->` and `<!-- fitdocs:end:chart:<id> -->`, starting at column 0, placed directly below the chart's directive with nothing but blank lines between the directive's closing line and the begin marker.
2. When a valid directive has no region directly below it, fitdocs shall insert the region on the line after the directive's closing line.
3. When fitdocs writes a chart, it shall replace only the bytes between that chart's begin and end markers.
4. A region holding an image chart shall contain one standard markdown image link whose text is the chart's title and whose target is the chart asset's path relative to the page; a region holding a markdown chart shall contain the markdown the chart kit returned.
5. A rendered chart's region shall contain a caption that states, in this order and only where it applies: the date a frozen chart's snapshot was taken; the directive's `window` text; and the latest date present in the result's date or date-time columns, or that the result had no rows.
6. Where a directive sets `show_rows: true`, the chart's region shall also contain the result rows as a markdown table drawn by the chart kit's table kind.
7. If a region for a chart id is anywhere other than directly below the directive with that id, if a region's end marker is missing, or if a region contains a directive opening line or another region marker, then fitdocs shall refuse that chart, leave its region unchanged and report the region's line.
8. If a region's id matches no directive on the page, then fitdocs shall leave the region unchanged and report it as orphaned.

### Requirement 6: Chart Assets
**Objective:** As an athlete, I want every chart image to have a path no other
chart can take and to be cleaned up only when nothing links it, so that one
page can never overwrite or lose another page's chart.

#### Acceptance Criteria
1. fitdocs shall write an image chart to `dashboards/assets/<page name>/<chart id>.svg`.
2. fitdocs shall derive an asset's path from the page name and the chart id only, never from the result, a date or any other computed value.
3. fitdocs shall write a mark into every chart image it writes, and shall never overwrite or delete a file in `dashboards/assets/` that does not carry the mark.
4. When the pass, or a `refresh` or `freeze` run, has finished its pages, fitdocs shall delete a marked chart image in `dashboards/assets/` only if no dashboard page's text contains that image's path relative to `dashboards/`, whichever pages the run targeted.
5. fitdocs shall never delete a snapshot.
6. When a chart image's bytes would be unchanged, fitdocs shall not rewrite it.

### Requirement 7: Running a Chart's Query
**Objective:** As the athlete's assistant, I want a chart's SQL to run under
exactly the rules `fitdocs query` runs under, with one date parameter, so that
what I tested with `fitdocs query` is what the chart shows.

#### Acceptance Criteria
1. fitdocs shall run a chart's SQL only through the analytics query sandbox: read-only, under the locked configuration, with extension loading, external file access and network access disabled.
2. If a chart's SQL is not exactly one SELECT statement, then fitdocs shall refuse the chart, naming the restriction.
3. When a chart's SQL uses the parameter `$today`, fitdocs shall bind it to the run date as a date value; when the SQL does not use it, fitdocs shall bind no parameter.
4. If a chart's SQL uses any parameter other than `$today`, including a positional parameter, then fitdocs shall refuse the chart before running it, naming the parameter.
5. fitdocs shall decide which parameters a chart's SQL uses from the parsed statement and never from the text of a database error, so that `$today` inside a string literal or a comment is not a use.
6. fitdocs shall run each chart's statement under the default time limit of `fitdocs query`; if a statement runs longer, then fitdocs shall stop it and refuse the chart with a timeout problem.
7. If a chart's result has more than 10,000 rows, then fitdocs shall refuse the chart with a problem naming the cap and suggesting aggregation in SQL, without reading the remaining rows.
8. fitdocs shall open at most one read-only index connection per run, share it among every chart the run queries, and close it before the run ends.
9. If a chart's statement fails, then fitdocs shall refuse the chart with the database's message and any hint `fitdocs query` would give for the same failure.
10. When the user interrupts a run while a statement is running, fitdocs shall stop the statement, close the connection without waiting for the statement to finish, and leave every page, asset and snapshot it had not finished writing unchanged.

### Requirement 8: Typed Result Columns and Units
**Objective:** As the athlete's assistant, I want result columns to reach the
chart with their real value kinds and units, so that dates plot as dates and a
`_km` column is labelled in kilometres.

#### Acceptance Criteria
1. fitdocs shall give each result column a value kind from its database type, whichever spelling the supported database engine version reports: integer, floating-point and decimal numbers as number; DATE as date; TIMESTAMP as date-time; INTERVAL as duration; text and enumerations as category; BOOLEAN as boolean.
2. If a result column has a type with no chart value kind (time of day, timestamp with time zone, list, structure, map, binary, UUID, or a type fitdocs does not recognise), then fitdocs shall refuse the chart with a problem naming the column and its type and suggesting a cast or removing the column.
3. fitdocs shall give each result column the unit token of the most specific unit suffix its name ends with, taken from the single unit vocabulary the analytics index documents, and no unit when no suffix matches.
4. fitdocs shall pass each result value to the chart kit as the value the database returned, with SQL NULL as absent, and shall never substitute zero, an empty string or any default for an absent value.
5. fitdocs shall not convert any value from one unit to another.
6. If a returned value does not match its column's value kind, then fitdocs shall refuse the chart with a problem naming the column, the first offending row and the number of offending rows.

### Requirement 9: Relative Charts
**Objective:** As an athlete, I want a "last 12 weeks" chart that is current
after every sync, and that stays byte-for-byte still on a day with no new data.

#### Acceptance Criteria
1. When fitdocs renders a relative chart, it shall run the chart's SQL in that run and draw the chart from the rows returned.
2. fitdocs shall write a relative chart's region and asset only when their bytes differ from those on disk.
3. fitdocs shall never write the run date, a time of day, or any other value that changes when only the date changes into a relative chart's region or asset, so that a relative chart's bytes change only when its rows, its directive or the chart kit change.
4. When a relative chart's result has no rows, fitdocs shall render the chart kit's no-data state and a caption stating that the result had no rows, and shall not treat the chart as failed.

### Requirement 10: Frozen Charts and Snapshots
**Objective:** As an athlete, I want a frozen chart to show the same thing
forever, so that "my cadence before the hill block" stays a record even after
the data underneath it moves or the index is gone.

#### Acceptance Criteria
1. When fitdocs renders a frozen chart for which no snapshot can be found, it shall run the chart's SQL once with `$today` bound to the run date and, only if the chart then renders without problems, store a snapshot of the result's columns and rows together with that date, the SQL text and a digest of it, before drawing the chart from the snapshot.
2. When a frozen chart has a snapshot, fitdocs shall draw it from the stored rows and shall not run its SQL, including when no index exists, after an index rebuild or schema change, and on a machine that has never built an index.
3. fitdocs shall record in a frozen chart's region which snapshot the chart was drawn from.
4. fitdocs shall find a frozen chart's snapshot first from its region's record and, when the region records none, from the most recent snapshot stored for that page name and chart id.
5. If the snapshot a frozen chart's region records is missing or cannot be read, then fitdocs shall leave the chart's region and asset unchanged, shall not run the chart's SQL, and shall report the missing snapshot and how to take a new one.
6. If a frozen chart's SQL differs from the SQL its snapshot was taken with, then fitdocs shall keep drawing the chart from the snapshot and shall report a notice that the SQL changed after the snapshot was taken and how to take a new one.
7. When a frozen chart's kind, title, channels, options, `window` or `show_rows` change, fitdocs shall redraw the chart from its stored rows.
8. fitdocs shall never modify or delete a stored snapshot; `fitdocs regen`, `fitdocs index --rebuild`, a chart-kit upgrade and stale-asset removal shall leave every snapshot unchanged.
9. fitdocs shall store snapshot values so that drawing a chart from a snapshot produces exactly the bytes drawn from the rows the query returned when the snapshot was taken.

### Requirement 11: Freezing on Request
**Objective:** As an athlete, I want to retake a frozen chart's snapshot
deliberately, so that re-snapshotting is always my decision.

#### Acceptance Criteria
1. When asked to freeze a frozen chart, fitdocs shall run its SQL with `$today` bound to the run date, store the result as a new snapshot without altering any earlier snapshot, and point the chart's region at the new snapshot.
2. If asked to freeze a relative chart, then fitdocs shall refuse it, naming the chart's mode and how to change it.
3. If a freeze's query fails or its chart does not render, then fitdocs shall leave the chart's region, asset and existing snapshots unchanged and report the problem.
4. If the index cannot be opened when a freeze is requested, then fitdocs shall refuse the freeze and state the index's state and the command that fixes it.

### Requirement 12: Failure Isolation Per Chart
**Objective:** As an athlete, I want one broken chart to cost only that chart,
so that a typo in one directive never blanks my other charts.

#### Acceptance Criteria
1. If a chart fails (a directive or region problem, refused or failed SQL, a timeout, the row cap, an unsupported column, a chart-kit refusal, a missing snapshot, or an unwritable asset), then fitdocs shall continue with every other chart on the page and every other page.
2. If a chart that has been rendered before fails, then fitdocs shall leave its region and asset exactly as they were.
3. If a chart that has never been rendered fails, then fitdocs shall write its region with a short visible note that begins `Not rendered:` and states the first problem's message, and with no image link.
4. fitdocs shall report every failed chart with its page name, chart id, the page line of its directive and every problem found for it.
5. If a page cannot be read or written safely (Requirement 16), then fitdocs shall leave it unchanged, report it and continue with the other pages.

### Requirement 13: The Pass After an Index Refresh
**Objective:** As an athlete, I want relative charts brought up to date by the
commands I already run, without those commands ever failing because of a
chart.

#### Acceptance Criteria
1. When `fitdocs sync` (with or without a source), `fitdocs pull --sync`, `fitdocs regen` or `fitdocs load` has refreshed the analytics index successfully, fitdocs shall then run the dashboard pass over every dashboard page.
2. If that command's index refresh did not succeed (the index is not built, is busy, needs a rebuild, or the refresh failed or raised an error), then fitdocs shall change no dashboard page, asset or snapshot and, when at least one dashboard page exists, shall print one line stating that the dashboards were not refreshed and why.
3. The dashboard pass shall never build or rebuild the analytics index.
4. The dashboard pass shall never cause its command to fail and shall never change its command's exit code; an unexpected error in the pass shall be reported in one line.
5. Commands that do not refresh the analytics index after writing, and `fitdocs index` itself, shall not run the dashboard pass.
6. When no dashboard page exists, the dashboard pass shall print nothing; otherwise it shall print the number of charts it wrote and every problem and notice, and nothing when it wrote nothing and found nothing to report.
7. If the user interrupts the dashboard pass, then fitdocs shall let the interrupt end the command exactly as an interrupt during the index refresh does.

### Requirement 14: The `fitdocs dashboard` Command
**Objective:** As the athlete's assistant, I want one command to check a page,
redraw it, retake a snapshot and list the chart kinds, so that I can iterate on
a dashboard in a loop without reading fitdocs's source.

#### Acceptance Criteria
1. fitdocs shall provide one command, `fitdocs dashboard`, whose first argument selects one of the forms `check`, `refresh`, `freeze` and `kinds`.
2. `fitdocs dashboard check [TARGET...]` shall check the targeted pages, or every page, without writing or deleting any file: the page's structure, each directive's syntax and content, the SQL's screening, the result's columns against the kind's channels, and a complete render in memory, reporting every problem and notice.
3. `fitdocs dashboard refresh [TARGET...]` shall render the targeted pages or charts, or every page, writing as the pass does, whether or not an index refresh has run.
4. `fitdocs dashboard freeze TARGET...` shall freeze the targeted frozen charts as Requirement 11 states; a page target freezes every frozen chart on that page.
5. `fitdocs dashboard kinds` shall list every registered chart kind with its description, output, channels (whether each is required and the value kinds it accepts), options (type, default, choices or range) and mark bound, read from the chart registry when the command runs.
6. A target shall be a page name, or a page name and a chart id joined by `:`; if a target names no existing page or chart, then fitdocs shall exit with an invalid-input error that lists the available page names or chart ids.
7. If the index cannot be opened during `check` or `refresh`, then fitdocs shall still check or render every chart that needs no query, and shall report for each chart that needs one that it was not queried, with the index's state and the command that fixes it.
8. The command shall exit 0 when every chart and page in scope checked or rendered without a problem (notices allowed), 1 when any problem was reported, 2 for invalid input or configuration, and 130 when interrupted.
9. Where `--format json` is given, the command shall print its report as one JSON document on standard output; the default output is text.
10. The command shall make no network request.

### Requirement 15: Problems an Agent Can Act On
**Objective:** As the athlete's assistant, I want every failure as structured
data with a stable code and a fix, so that I can correct a directive without
guessing.

#### Acceptance Criteria
1. Every problem shall carry the page name, the chart id when it concerns a chart, the 1-based page line it concerns, a stable code, a one-sentence message and a one-sentence fix.
2. A problem raised by the chart kit shall carry the chart kit's code, message, fix, channel, column, option, row, row count and accepted values unchanged, and shall state that it came from the chart kit.
3. fitdocs shall keep its own problem codes stable and append-only, distinct by source from the chart kit's codes.
4. The JSON report shall list, for each page in scope, its page-level problems and, for each chart, its id, kind, mode, outcome, problems and notices, together with the index's state and the paths of any assets removed.
5. fitdocs shall order the report by page name, then by page line, keeping the chart kit's own order among one chart's chart-kit problems, so that the same inputs give the same report.
6. A notice shall be reported apart from problems and shall not by itself make the command's exit code non-zero.

### Requirement 16: Safe Writes
**Objective:** As an athlete, I want fitdocs's writes into my wiki to be
atomic and to refuse anything unexpected, so that a crash, a symlink or my own
concurrent edit never costs me content.

#### Acceptance Criteria
1. fitdocs shall replace pages, chart assets and snapshots atomically, so that a reader never sees a partly written file, and shall create each snapshot as a new file that never replaces an existing one.
2. If `dashboards/`, `dashboards/assets/`, a page's asset directory, a page or an asset path is a symbolic link, or an asset path is occupied by anything fitdocs did not write, then fitdocs shall not follow, overwrite or delete it and shall report it.
3. If a page's bytes change between fitdocs reading the page and replacing it, then fitdocs shall not replace it and shall report that the page changed during the run.
4. If a page is not valid UTF-8, then fitdocs shall leave it unchanged and report it.
5. fitdocs shall keep a page's line endings and any leading byte-order mark, and lines it inserts shall end with the line ending of the directive's closing line.
6. A dashboard run shall write only chart regions inside existing dashboard pages and files inside `dashboards/assets/`, and shall delete only marked chart images inside `dashboards/assets/`.

### Requirement 17: Idempotence and Determinism
**Objective:** As an athlete whose wiki is synced through iCloud and git, I
want a run with nothing new to change nothing.

#### Acceptance Criteria
1. When a run follows an identical run (the same pages, query results, snapshots and chart kit), fitdocs shall write no file and delete no file.
2. fitdocs shall produce byte-identical regions, chart assets and snapshots for the same inputs, independent of the process, the host's timezone, locale and environment, and the order in which pages are found.
3. fitdocs shall process pages in page-name order and charts in page order.

### Requirement 18: The Skill and the Documentation
**Objective:** As the athlete's assistant, I want a packaged skill and a docs
page that teach the dashboard surface, so that I write correct directives the
first time and stay correct as kinds are added.

#### Acceptance Criteria
1. fitdocs shall ship a fourth packaged agent skill, `fitdocs-dashboards`, which `fitdocs skill` lists and locates like the other packaged skills.
2. The skill and `docs/dashboards.md` shall each teach: the directive and its keys; relative versus frozen charts and how to retake a snapshot; who owns which bytes of a page; and the check loop of writing a directive, running `fitdocs dashboard check`, and fixing what it reports.
3. The skill and `docs/dashboards.md` shall each teach that `$today` windows are written as date arithmetic (`$today - 84`) or with an explicit cast, because `$today - INTERVAL 12 WEEK` is a timestamp rather than a date; that an alias keeps its unit suffix (`AS distance_km`) to keep its unit; and that pace is computed in SQL from speed (`1000.0 / NULLIF(speed_mps, 0) AS pace_s_per_km`) because fitdocs converts no unit.
4. The skill and `docs/dashboards.md` shall each state the directive's traps: column 0 and no indentation; no `-->` or `--!>` in the body; `sql` as a literal block; and that Obsidian's reading view hides a directive while its Live Preview mode shows it as dimmed source.
5. The skill shall state that running cadence columns ending `_cadence_rpm` hold strides per minute (one foot, the FIT convention), not steps per minute, and that a query doubling them to steps loses the unit suffix.
6. The skill shall point to `fitdocs dashboard kinds` for the list of chart kinds and shall not list kinds' channels or options.
7. `docs/dashboards.md` shall contain a block listing every registered kind, generated from the chart registry, and the fitdocs test suite shall fail when that block differs from the registry.
8. The `fitdocs-analytics` skill shall point to the `fitdocs-dashboards` skill for putting a query's answer on a wiki page as a chart, and the documentation index shall link `docs/dashboards.md`.

### Requirement 19: Published Rules and Records
**Objective:** As a maintainer, I want every published statement this feature
changes to change with it, so that no contract, steering file or test pin
contradicts the shipped behavior.

#### Acceptance Criteria
1. Every published statement that the analytics index is never read back into a document shall state one named exception: dashboard chart regions and their assets are the only document content produced from the index, and workout, history and block documents never read it.
2. The ownership contract's version shall advance by one, and the contract shall describe the dashboards location, the dashboard page category, the chart region and asset policy, snapshots, and what the pass and `fitdocs dashboard` overwrite.
3. The published list of commands that make no connector request shall include `dashboard`.
4. The steering record of import directions shall state what the dashboards feature imports and that only the CLI imports it.
5. The CHANGELOG's unreleased section shall gain one entry naming `fitdocs dashboard`, the `fitdocs-dashboards` skill, the ownership-contract version and the action a user takes.
6. The specifications whose published rules this feature changes (analytics index, analytics query, wiki contract, connectors) shall each record the change as a dated amendment naming this feature.

### Requirement 20: Boundaries
**Objective:** As a maintainer, I want the dashboards feature to stay inside a
narrow boundary, so that rendering, data access and time stay owned where they
are owned today.

#### Acceptance Criteria
1. fitdocs shall draw every dashboard chart through the chart kit's registry and shall accept every registered kind, including kinds registered after this feature lands, without a change to the dashboards feature.
2. The dashboards feature shall reach the database only through the analytics query layer, shall read no clock (the run date comes from the CLI's one clock read), shall make no network request, and shall add no runtime dependency.
3. Only the CLI shall use the dashboards feature.
4. The fitdocs test suite shall fail if dashboards code imports outside its allowed dependencies, reads a clock or imports a network module, and each such guard shall carry a positive control showing that it detects a violation.
