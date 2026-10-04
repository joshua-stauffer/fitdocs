# Requirements Document

## Project Description (Input)
Agents working in the athlete's PKM answer statistical questions ("weekly
running volume since March", "average HR at 4:30/km pace this block versus
last") by reading hundreds of workout documents and doing the arithmetic in
context. That is slow, costs a lot of tokens, and is often wrong: frontmatter
carries only a thin summary, and everything else sits in rendered markdown
tables. `analytics-index` puts the data in a DuckDB file in a per-user cache
directory, kept current by a reconciling pass, with a schema version and a
description of every table and column. But agents still need a safe,
documented way to ask it.

This spec adds that read surface:
- `fitdocs query`, a read-only command that runs one SQL statement against the
  index inside a sandbox the statement cannot talk its way out of, and prints
  the result as a table, CSV or JSON;
- schema introspection, honest freshness reporting and lock handling;
- a packaged agent skill that teaches agents to use it;
- `docs/analytics.md`, whose schema reference is held to the live schema.

Source: `.kiro/specs/analytics-query/brief.md`; Phase 10 of
`.kiro/steering/roadmap.md`. Dependencies: `analytics-index`.

## Introduction

`fitdocs query` is the one way fitdocs lets an agent ask the index. One stance
governs everything an athlete or agent can observe about it: the command reads
and never changes anything, and the statement it runs gets no more power than
reading the index needs.

- **The statement is untrusted.** An agent may write SQL by mistake that reads
  the wrong file, or it may be handed injected SQL by a document it read. So
  every statement runs read-only, can touch no file but the index, can reach
  no network, and cannot change the settings that enforce this. A refusal
  says which limit it met.
- **The command writes nothing.** It never builds or refreshes the index,
  never touches the data root, and leaves no file behind. The one exception
  is the database's own temporary spill files, kept in a directory of the
  query's own inside the index directory and removed when the query ends.
- **Answers are honest about their source.** When the index is missing,
  incompatible or behind the data root, the command says so and names the
  command that fixes it. Absent values print as NULL, never as zero. A result
  is never cut short without a notice.
- **The agent-facing contract is text that cannot drift.** The packaged skill
  and the documentation page are what agents read. Both are held to the live
  index by tests: the skill's examples run, and the schema reference equals
  the stored descriptions.

Terms used below:
- The **index**, the **index file** and the **index directory** are
  `analytics-index`'s: one DuckDB file per data root in a per-user cache
  directory outside the data root.
- A **workout page**, a **refresh**, a **build** and a **rebuild** are as
  `analytics-index` defines them.
- A **statement** is the SQL text given to one `fitdocs query` invocation.
- The **sandbox** is the set of limits every statement runs under
  (Requirement 5).
- **Spill files** are the temporary files the database writes when a statement
  needs more memory than its bound.
- A table **built from the whole data root** is one whose rows a refresh
  recomputes from the data root as a whole rather than page by page.

## Boundary Context

- **In scope**:
  - the `fitdocs query` command: its input forms, formats, row limit, time
    limit, exit codes and messages;
  - the sandbox and its tests, each refused class pinned;
  - the database-library version floor at which the sandbox holds;
  - schema introspection and freshness reporting;
  - read-side lock handling;
  - the `fitdocs-analytics` packaged skill, with its registry, profile and
    locator pins, and a one-line pointer from `fitdocs-workouts`;
  - `docs/analytics.md` and its live-schema pin, with the documentation index
    entry;
  - joining the no-network command list (`tech.md`, the connectors e2e
    guard and the connectors amendment record);
  - the release notes.
- **Out of scope**:
  - building, refreshing or rebuilding the index, and the schema itself
    (`analytics-index`);
  - the derived tables (`analytics-derived`);
  - an MCP or HTTP server, and a natural-language "ask" wrapper;
  - write access, user tables, saved queries, and statements spanning several
    invocations;
  - charting query results;
  - any existing command reading the index, `fitdocs check` included;
  - the ownership contract's statements about the index directory
    (`analytics-index` owns them; this feature relies on them).
- **Adjacent expectations**:
  - `analytics-index` supplies the location, the read-only connection with its
    mandatory settings, the schema version, the stored descriptions, the
    bookkeeping this feature compares against, and the definition of a workout
    page.
  - `analytics-derived` adds tables through `analytics-index`'s producer seam.
    This feature shows them the same way as every other table and adds
    nothing for them except skill examples (Requirement 11.5).
  - An outside DuckDB client that opens the index file is outside every
    guarantee here. The documentation says so (Requirement 12.4).

## Requirements

### Requirement 1: Asking One Question
**Objective:** As an agent answering an athlete's question, I want to hand fitdocs one SQL statement and get its result, so that I never read hundreds of documents to compute an aggregate.

#### Acceptance Criteria
1. fitdocs shall provide a `fitdocs query` command that resolves the data root as other commands do, accepts `--out`, and runs one SQL statement against that data root's index.
2. fitdocs shall take the statement from exactly one of: a command-line argument, a file named with `--file`, or standard input when the argument is `-`.
3. If no statement source and no `--schema` is given, more than one statement source is given, or `--schema` is given together with a statement, then fitdocs shall print a message naming the accepted forms and exit 2 without opening the index.
4. If the file named with `--file` or standard input cannot be read as UTF-8 text, or the statement text is empty or only whitespace, then fitdocs shall say so and exit 2 without opening the index.
5. If the statement text holds no statement (only comments, say) or more than one statement, then fitdocs shall refuse it with a message saying that `fitdocs query` runs exactly one statement, run nothing, and exit 1.
6. fitdocs shall hold the index open only while it reads the index's records and runs the statement, and shall close it before printing the result.

### Requirement 2: Output Formats
**Objective:** As an agent or an athlete, I want the result in a form I can read or parse without ambiguity, so that an absent value is never mistaken for zero.

#### Acceptance Criteria
1. fitdocs shall print a statement's result in the format chosen with `--format`: `table` (aligned text for reading), `csv` (a header row, then one row per result row) or `json` (one JSON document).
2. When `--format` is not given and standard output is a terminal, fitdocs shall print `table`.
3. When `--format` is not given and standard output is not a terminal, fitdocs shall print `csv`.
4. fitdocs shall print SQL NULL distinguishably from zero, from an empty string and from false in every format: as `NULL` in `table`, as an empty unquoted field in `csv` (where an empty string prints as `""`), and as `null` in `json`.
5. fitdocs shall print every column of the result, in result order, under the name the result gives it, repeated names included.
6. fitdocs shall print a floating-point value that is not a number or is infinite as `NaN`, `Infinity` or `-Infinity` in every format, never as NULL, zero or an empty field.
7. fitdocs shall print an exact decimal with all its digits, a date, time or timestamp in ISO 8601 form, a duration as an ISO 8601 duration, and a list, structure or map as JSON text in `table` and `csv` and as a JSON array or object in `json`.
8. The `csv` format shall quote a field that contains a comma, a double quote or a line break, or that is an empty string, and shall double each double quote inside a quoted field.
9. The `json` format shall carry the column names, the rows as arrays in column order, the number of rows printed, whether the result was cut at the row limit, the row limit, and the index's freshness counts (Requirement 9.1).
10. The `table` format shall print a control character inside a value as an escape, so that each result row occupies one line.

### Requirement 3: The Row Limit
**Objective:** As an agent, I want large results capped with a clear notice, so that a careless query cannot flood my context and a cut result is never mistaken for a whole one.

#### Acceptance Criteria
1. fitdocs shall print at most a row limit of rows per statement: 1,000 unless `--max-rows` sets another positive whole number.
2. When a result has more rows than the row limit, fitdocs shall print the rows up to the limit and print a notice on the standard error stream. The notice shall say that the result was cut at that many rows, and that narrowing or aggregating the query, or raising `--max-rows`, shows more.
3. When a result has more rows than the row limit, fitdocs shall also mark the cut in the output itself: with a closing line in `table`, and with the cut flag in `json`.
4. fitdocs shall never leave out a result row without the notice of criterion 2, and shall exit 0 for a result cut at the row limit.
5. If `--max-rows` is not a positive whole number, then fitdocs shall say so and exit 2 without opening the index.

### Requirement 4: Exit Codes and Error Messages
**Objective:** As an agent driving fitdocs from a shell, I want exit codes and messages I can act on, so that a failed query is never mistaken for an empty answer.

#### Acceptance Criteria
1. When the statement runs and its result is printed, fitdocs shall exit 0.
2. If the statement fails (a syntax error, an unknown table or column, a type error, or an error the statement raises while running), then fitdocs shall print the database's own error message on the standard error stream, print no result, and exit 1.
3. If the sandbox refuses the statement (Requirement 5), the time limit stops it (Requirement 6), or the index cannot be read (Requirement 8), then fitdocs shall say so on the standard error stream, print no result, and exit 1.
4. If the data root cannot be resolved, the index location is refused, or an option's value is invalid, then fitdocs shall print the reason on the standard error stream and exit 2 without opening the index.
5. fitdocs shall print results only on the standard output stream, and every notice, warning and error only on the standard error stream.

### Requirement 5: The Sandbox
**Objective:** As an athlete whose agent runs SQL it wrote or was handed by a document, I want every statement confined to reading the index, so that no statement, accidental or injected, reads my other files, writes anything, reaches the network or loosens these limits.

#### Acceptance Criteria
1. fitdocs shall open the index read-only for every statement, so that no statement can change the index.
2. fitdocs shall run only statements that read: queries (including those that start with `WITH`, `FROM`, `VALUES`, `DESCRIBE`, `SHOW`, `SUMMARIZE` or a table-valued `PRAGMA`) and `EXPLAIN`. It shall refuse every other kind of statement before it runs, including `INSTALL`, `LOAD`, `ATTACH`, `DETACH`, `COPY`, `EXPORT`, `IMPORT`, `SET`, `RESET`, `USE`, `CREATE`, `CALL`, and any statement that changes data.
3. fitdocs shall refuse every attempt by a statement to read, list or write a file or address other than the index. That includes file-reading functions, table references that name a path, `COPY … TO` inside `EXPLAIN ANALYZE`, attaching another database, and installing or loading an extension.
4. fitdocs shall run every statement with extension auto-install, extension auto-load, community extensions, persistent secrets and external access turned off, and with the configuration locked so that no statement can change a setting.
5. When fitdocs refuses a statement, it shall print a message naming the restriction met, followed by the database's own message, and exit 1. The restriction is one of: a statement kind that is not allowed, a file or address outside the index, a locked setting, the read-only index, or an extension that is unavailable.
6. Before running a statement, fitdocs shall confirm that every sandbox setting is in force on the opened index; if any is not, fitdocs shall run nothing, name the setting, and exit 1.
7. fitdocs's dependency declaration shall admit no release of its database library on which a refusal of this requirement fails, or on which a refused statement leaves a file or directory behind.
8. If any sandbox setting is removed from the configuration fitdocs opens the index with, or any refused statement kind of criterion 2 is allowed to run, then the fitdocs test suite shall fail.

### Requirement 6: Bounded Execution
**Objective:** As an athlete, I want a runaway query stopped and contained, so that it can hang neither my agent nor my machine.

#### Acceptance Criteria
1. If a statement has not finished within its time limit (30 seconds unless `--timeout` sets another positive number of seconds), then fitdocs shall stop it, say that it ran longer than the limit and was stopped, and exit 1.
2. fitdocs shall run every statement within at most 1 GB of database memory and at most 2 threads.
3. Where a statement needs more memory than its bound, fitdocs shall let the database spill only into a directory inside the index directory that belongs to that one `fitdocs query` process, and shall have that directory removed when the statement ends.
4. When `fitdocs query` starts, fitdocs shall remove any spill directory a `fitdocs query` process left in the index directory if that process is no longer running. It shall leave every other file untouched, spill directories of running processes included.
5. If `--timeout` is not a positive number, then fitdocs shall say so and exit 2 without opening the index.
6. If the user interrupts `fitdocs query`, then fitdocs shall stop the statement and close the index before exiting.

### Requirement 7: Nothing Written, Nothing Reached
**Objective:** As an athlete, I want the query command to leave no trace and make no request, so that fitdocs's promises about my files and the network still hold.

#### Acceptance Criteria
1. fitdocs shall make no network request while running `fitdocs query`, including when the statement contains a web address.
2. fitdocs shall create, change or delete nothing in the data root while running `fitdocs query`.
3. fitdocs shall create, change or delete nothing outside the index directory while running `fitdocs query`, the user's home directory included. Inside the index directory it shall touch nothing other than spill directories (Requirement 6.3 and 6.4).
4. fitdocs shall never build, refresh or rebuild the index during `fitdocs query`.
5. The published list of commands that make no network request shall include `fitdocs query`.

### Requirement 8: An Index That Is Absent, Incompatible or Busy
**Objective:** As an agent, I want to know at once why the index cannot answer and what fixes it, so that I neither wait nor guess.

#### Acceptance Criteria
1. If the index file does not exist, then fitdocs shall say that the index is not built and that `fitdocs index` builds it, create nothing, and exit 1.
2. If the index file is corrupt or unreadable, is in a storage format the installed database library cannot read, does not hold a complete fitdocs index, or records a schema version other than the one this fitdocs reads, then fitdocs shall name the reason, say that `fitdocs index` rebuilds it, run no statement, and exit 1.
3. While another process holds the index open for writing, fitdocs shall retry opening it, waiting longer between attempts, for at most 10 seconds in total, and shall say once on the standard error stream that it is waiting.
4. If the index is still held for writing after 10 seconds, then fitdocs shall say that the index is being refreshed or is open for writing in another program, name the holding process's id when the database reports one, say that the query can be run again once that finishes, and exit 1.
5. While other processes hold the index open only for reading, fitdocs shall open it without waiting.

### Requirement 9: Honest Freshness
**Objective:** As an agent, I want to know when the index is behind the athlete's documents, so that I never present a stale answer as current.

#### Acceptance Criteria
1. Each time `fitdocs query` runs a statement, fitdocs shall compare the data root's workout pages with the pages the index records. It shall count the pages the index lacks, the pages whose files changed since the index recorded them, and the pages the index holds that are no longer in the data root.
2. When any count of criterion 1 is not zero, fitdocs shall print a notice on the standard error stream giving the three counts and saying that `fitdocs index` brings the index level, and shall still run the statement.
3. fitdocs shall count as workout pages exactly the pages the index's refresh considers, so that the notice disappears once a refresh has run and a page the refresh leaves out (for example, one that lists the same base file as another page) is never counted as missing from the index.
4. When the index is level with the data root, fitdocs shall print no freshness notice.
5. fitdocs shall assess freshness by reading alone, changing neither the index nor the data root.

### Requirement 10: Schema Introspection
**Objective:** As an agent about to write SQL, I want one view of every table and column with its meaning and unit, and of the index's state, so that I write correct SQL without reading fitdocs's source.

#### Acceptance Criteria
1. Where `--schema` is given, fitdocs shall print every table of the index with its name, description and row count. For every column, in table order, it shall print the column's name, its type, its unit when the name carries a unit suffix, and its description. Every description shall come from the descriptions stored in the index itself.
2. Where `--schema` is given, fitdocs shall also print the index's state:
   - the index file's absolute path;
   - the schema version it records, and the one this fitdocs reads;
   - the fitdocs version that last wrote it;
   - the number of pages it holds, against the number of workout pages in the data root;
   - the pages left out, with their reasons;
   - the counts of Requirement 9.1;
   - the number of pages without computed values, by reason;
   - whether a rebuild is needed.
3. Where `--schema` is given, fitdocs shall report how many activities' computed values were computed under athlete inputs other than the current athlete profile's, and say that `fitdocs regen` brings documents and index forward together. When the athlete profile cannot be read, it shall say that this comparison was skipped, and why.
4. Where `--schema` is given, fitdocs shall name every table built from the whole data root whose inputs have moved since the index last computed it, and say that `fitdocs index` brings it level.
5. If a table or column of the index has no stored description, then fitdocs shall list it as having no description, never omit it, and print a warning that names it as a fitdocs defect.
6. Where `--schema` is given, fitdocs shall print the view as text by default and as one JSON document with `--format json`, and shall refuse `--format csv` with exit 2.
7. Where `--schema` is given and the index is readable at the schema version this fitdocs reads, fitdocs shall exit 0, whether or not the index is behind the data root.
8. Where `--schema` is given and the index is absent, cannot be used (Requirement 8.2) or is still held for writing (Requirement 8.4), fitdocs shall print as much of the state as it can read, name the command that fixes it, and exit 1.
9. If any table or column of an index built by this fitdocs lacks a stored description, then the fitdocs test suite shall fail.

### Requirement 11: The Packaged Agent Skill
**Objective:** As an agent in the athlete's PKM, I want a packaged skill that teaches me to use the index well, so that I check freshness, read the schema, write correct SQL and report answers honestly.

#### Acceptance Criteria
1. fitdocs shall ship a packaged agent skill named `fitdocs-analytics`, listed by `fitdocs skill` and located by `fitdocs skill fitdocs-analytics` as the other packaged skills are.
2. The skill shall teach, in this order:
   - check the index's freshness and read its schema with `fitdocs query --schema`, then write SQL;
   - prefer the index over reading workout documents for any count, sum, average, distribution or trend;
   - show the SQL alongside every answer drawn from it;
   - read NULL as absent, never as zero.
3. The skill shall include worked SQL examples for training volume over time, time in heart-rate, power or pace zones, training loads, and effort tags.
4. If an SQL example in the skill fails to run, or returns no row, against an index built from the fitdocs test fixtures, then the fitdocs test suite shall fail.
5. Where `analytics-derived`'s tables (mean-max curves, the daily load series, the benchmark timeline, training blocks) are in the index when this feature lands, the skill shall include a worked example for each.
6. The skill shall teach the output formats, the row limit and `--max-rows`, the time limit and `--timeout`, and what the sandbox refuses.
7. The skill shall meet every pin the existing packaged skills meet:
   - its frontmatter keys;
   - a `metadata.version` equal to the project version;
   - every `fitdocs` command and option it shows registered in the CLI;
   - links only to published URLs, the ownership-contract link among them;
   - no owned path or managed key spelled out.
8. The `fitdocs-workouts` skill shall point to the new skill and its documentation in one line, and shall not restate it.

### Requirement 12: The Analytics Documentation and Published Statements
**Objective:** As an athlete or an agent, I want one documentation page for querying the index, and fitdocs's published statements updated, so that I can use the index safely, from fitdocs or from my own client.

#### Acceptance Criteria
1. The documentation shall include an analytics page describing `fitdocs query`: its input forms, the formats and their defaults, the row limit, the time limit, the exit codes, the freshness notice and `--schema`.
2. The analytics page shall describe the sandbox:
   - what runs and what is refused;
   - that opening the index read-only is not by itself the sandbox;
   - that the sandbox guards against accidental or injected SQL, and is no boundary against a local user who can open the file with another program.
3. The analytics page shall state the index's location, its resolution order, and how to print it.
4. The analytics page shall explain how to open the index from another DuckDB client: read-only, with extension auto-install and auto-load turned off. It shall also state:
   - that such a client bypasses the sandbox and is not bound by fitdocs's network statement;
   - that a client left open blocks every refresh until it is closed;
   - that concurrent clients should each spill into their own temporary directory.
5. The analytics page shall carry a schema reference listing every table and column with its type, unit and description, generated from the descriptions stored in an index built by this fitdocs. If the reference differs from them, then the fitdocs test suite shall fail.
6. The documentation index shall link the analytics page. The release notes shall state, under the unreleased entry, the `fitdocs query` command, the `fitdocs-analytics` skill and the analytics page.
7. The steering documents shall list `fitdocs query` among the commands that make no network request, and shall record the read side's place in the dependency direction. The `connectors` amendment record shall name `query` in its no-network command list.
