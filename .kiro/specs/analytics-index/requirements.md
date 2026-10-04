# Requirements Document

## Project Description (Input)
Agents working in the athlete's PKM need statistical answers about training
("weekly running volume since March", "time above 170 bpm in September",
"best 20-minute power this year"). Today fitdocs computes rich per-activity
data (summaries, laps, strength sets, per-second channels including running
dynamics and donated channels, NP/IF/TSS/TRIMP, zone times, loads, quality
flags, effort tags) and then flattens it into markdown: frontmatter carries
only a thin summary, everything else sits in rendered tables and the load
region's JSON, and per-second data is in no document at all. An agent must
either read hundreds of pages and do the arithmetic, or re-parse the archived
`.fit` files and re-implement fitdocs's parsing, composition and metric rules.

This spec makes fitdocs keep a derived DuckDB index of every workout page,
written as activities are ingested and readable with standard SQL: one file
per data root in a per-user cache directory outside the data root, refreshed
by one reconciling pass at the end of every writing command (`sync`, the
inbox drain, `pull --sync`, `regen`, `load`), rebuildable on demand with
`fitdocs index [--rebuild]`. The documents and the archived `.fit` files stay
the truth; the index is a disposable cache with a schema version, and its
failures never cost the pipeline. It also settles the extension seam two
later specs build on: `analytics-query` (the sandboxed `fitdocs query`
command) and `analytics-derived` (mean-max curves, the daily load series, the
benchmark timeline and training blocks). Source:
`.kiro/specs/analytics-index/brief.md`; Phase 10 of
`.kiro/steering/roadmap.md`. Dependencies: none.

## Introduction

The index answers one need: let a reader ask fitdocs's numbers with SQL
instead of re-deriving them. Everything about it follows from one stance:
it is a projection of the data root, never a second source of truth. That
stance settles four things the athlete can observe.

- **Where it lives.** A large binary rewritten on every sync would risk
  conflict copies and eviction in a synced data root, so the index sits in a
  per-user cache directory, one per data root, and deleting it costs only
  rebuild time.
- **When it moves.** One refresh runs after every command that writes
  workout pages. It compares each page against what the index recorded and
  updates only what moved, so hand edits and the training-load pass's
  rewrites reach it as surely as fitdocs's own writes. Building it from
  nothing is never automatic; the athlete asks with `fitdocs index`.
- **What it agrees with.** The index agrees with the documents (Requirement
  5 states the one rule), including the case where `athlete.toml` changed and
  the documents have not been regenerated yet.
- **What it may cost.** Nothing. No index problem (a held lock, a full disk, a
  corrupt file) fails, rolls back or skips a document write, or changes a
  command's exit code. The next successful refresh makes good a skipped one.

The index is built by registered **producers**: the core tables are the first,
and `analytics-derived` registers four more through the same seam without
changing the refresh. Reading the index safely is `analytics-query`'s.

Terms used below:
- A **workout page** is a markdown file directly under the data root's
  `workouts/` directory whose frontmatter reads and declares the workout type,
  the set `fitdocs check` and `fitdocs history` consider. A page's **base** and
  **extras** are `activity-identity`'s roles; the base is the last file the
  page's `sources` lists.
- A **writing command** is any of: `fitdocs sync SOURCE`, `fitdocs sync` with no
  source (the inbox drain), `fitdocs pull --sync`, `fitdocs regen` and
  `fitdocs load`.
- A **refresh** is the reconciling pass that brings the index level with the
  data root; a **build** is a refresh into an empty index; a **rebuild** is a
  build that replaces an existing index file.
- A page's **document values** are what its file records: frontmatter values,
  the load region's result and the effort tag. Its **computed values** are what
  fitdocs computes from its archived files: per-second records, laps, strength
  sets, derived metrics, zone times and channel provenance.
- A page's **rendering** is the part of its file only fitdocs's rendering
  writes: its managed frontmatter values other than the three load keys, and
  its body outside the `notes`, `workout` and `load` regions.
- The **athlete inputs** are the values from `athlete.toml` that fitdocs's
  metric computation reads (FTP, resting and maximum heart rate, zone
  dividers).
- A **producer** is a registered unit that declares index tables and supplies
  their rows; a **per-page producer** supplies one page's rows, a
  **corpus-level producer** supplies rows computed from the whole data root.

## Boundary Context

- **In scope**: the per-user index location and its refusal inside the data
  root; DuckDB as a required runtime dependency and the reworded dependency
  guards; the connection policy every fitdocs connection follows; the core
  tables with comments, and the schema version; the producer seam (per-page
  and corpus-level); fingerprints and the reconciling refresh after every
  writing command, with the in-memory hand-over from the sync engine;
  `fitdocs index [--rebuild]` with progress; failure isolation and write-side
  locking; the confinement, no-network and boundary guards for the new
  location and library; steering updates (`tech.md`'s database rule, Key
  Libraries, Network and Credentials; `structure.md`'s dependency direction);
  the ownership-contract statement and version advance; the install
  documentation's footprint note; the release notes; the amendment records in
  `plugin-api`, `distribution`, `workout-docs` and `connectors`.
- **Out of scope**: `fitdocs query`, its sandbox, statement timeout, formats,
  freshness reporting, read-side lock retry, the agent skill and
  `docs/analytics.md` (`analytics-query`); mean-max curves, the daily load
  series, the benchmark timeline and training blocks (`analytics-derived`);
  any existing pass (history, plan, derive-benchmarks, check) reading the
  index; any change to what a document shows or when it is written; free-text
  columns (the `notes` and `workout` regions, generated explanatory text);
  record-level developer fields beyond the activity model's channels;
  cross-machine sync of the index; an MCP or HTTP server.
- **Adjacent expectations**: `analytics-query` opens the index through this
  spec's location function, connection module and schema version, and owns
  everything a reader sees; `analytics-derived` adds tables only by
  registering producers and advancing the schema version; the sync engine
  (`workout-docs`, `activity-identity`, `channel-merge`) hands over what it
  rendered and otherwise renders exactly as before; the training-load pass's
  payload and the effort-tag and quality-flag vocabularies are read as their
  owning specs define them, never redefined here.

## Requirements

### Requirement 1: The Index Location
**Objective:** As an athlete whose data root lives in a synced folder, I want
the index kept in a per-user cache directory outside the data root, one per
data root, so that a large, frequently rewritten binary never sits in my
synced, versioned files and deleting it loses nothing.

#### Acceptance Criteria
1. fitdocs shall keep at most one index file per data root, in a per-data-root directory beneath an index base directory resolved in this order: the `FITDOCS_INDEX_DIR` environment variable when it is set to a non-empty value; otherwise `fitdocs/index` under `XDG_CACHE_HOME` when that variable is set to an absolute path; otherwise `.cache/fitdocs/index` under the user's home directory.
2. fitdocs shall name the per-data-root directory from the data root's fully resolved absolute path, so that two different data roots never share an index and one data root reached through different spellings (a relative path, a symbolic link) always resolves to the same index.
3. If `FITDOCS_INDEX_DIR` is set to a non-empty relative path, then fitdocs shall refuse it with a message naming the variable and its value, and shall write no index file.
4. If the per-data-root index directory resolves to the data root itself or to a path inside it, then fitdocs shall refuse it with a message naming both resolved paths, and shall write nothing there.
5. fitdocs shall write index files only inside the resolved per-data-root index directory.
6. When fitdocs creates the index base directory or a per-data-root directory, fitdocs shall create it readable, writable and searchable by the current user only.
7. fitdocs shall hold nothing in the index that a build cannot reproduce from the data root's workout pages, archived files, athlete profile, settings file and plan sources, so that deleting the index directory costs only the time of `fitdocs index`.

### Requirement 2: Document Values in the Index
**Objective:** As an agent answering an athlete's questions, I want every
workout page's recorded identity, effort tag, sources, loads and quality flags
queryable, so that I never parse frontmatter or the load region myself.

#### Acceptance Criteria
1. fitdocs shall hold one page row per workout page, carrying the page's key (Requirement 6), its data-root-relative path and the values its frontmatter records for title, document-format version, session UUID, date, local start time, sport, modality, indoor flag, the four base-identity keys, and the selected load's value, methodology and basis.
2. fitdocs shall hold a page's effort tag (kind, distance, time and event) when the tag is valid by the rule `fitdocs check` applies, and when the tag is present but invalid shall hold no effort value for it and record on the page row that the tag is invalid.
3. fitdocs shall hold one source row per file a page's `sources` lists, carrying its position in the list, its archive reference, the content hash the reference names, and its role (base for the last listed file, extra for every other).
4. While a page's load region holds a computed result, fitdocs shall hold one load row per channel the result reports (the selected channel and each non-selected channel), carrying the calculator, the channel, whether it is the selected one, and its load value, absent where the result records the channel as not computable and never zero in its place.
5. While a page's load region holds a computed result, fitdocs shall hold one quality-flag row per flag the result records, carrying the flag's key and its verdict.
6. fitdocs shall record on each page row whether its load region holds a computed result, an unsupported result, or neither.
7. fitdocs shall not hold the content of a page's `notes` or `workout` regions, the explanatory text of a load or flag result, or any record-level developer field outside the activity model's channels.

### Requirement 3: Computed Values in the Index
**Objective:** As an agent, I want every page's per-second samples, laps,
strength sets, derived metrics, zone times and channel provenance queryable as
fitdocs computes them, so that I can answer questions nobody planned for
without re-implementing fitdocs's rules.

#### Acceptance Criteria
1. fitdocs shall hold one activity row per workout page whose files compose, carrying its start instant, its sport, sub-sport, modality and indoor flag as fitdocs determines them, every derived metric fitdocs computes for the page (time, distance, speed, pace, heart rate, power, cadence, normalized power, intensity factor, variability index, efficiency factor, decoupling, elevation, altitude, temperature, TRIMP and its weighting, power-based TSS and calories), its sample count, and the fingerprint of the athlete inputs the metrics were computed under.
2. fitdocs shall hold one record row per sample of the page's composed activity, in recorded order, carrying the sample's position, its instant, its seconds since the activity's start and its value for every per-sample channel of the activity model, the running-dynamics channels and channels donated by an extra included, placed as the composed activity places them.
3. fitdocs shall hold one lap row per lap of the page's base, in recorded order, carrying every value the lap records and the range of samples it spans.
4. fitdocs shall hold one strength-set row per set of the page's base, in recorded order, carrying its type, start, duration, repetitions, weight, category and exercise name, a recorded weight of zero kept as zero.
5. fitdocs shall hold one zone-time row per channel (heart rate, power, pace) and zone for which fitdocs computes zone times for the page, carrying the zone's number, its lower and upper bound in the channel's unit from the athlete inputs, and the seconds credited to it.
6. fitdocs shall hold one channel-source row per per-sample channel for which the page holds at least one value, naming the file that supplied it and that file's role.
7. If a page's base archived file cannot be found, read or decoded, then fitdocs shall hold the page's document values, hold no computed value for it, and record on the page's index bookkeeping which of the three applied.
8. If the activity model gains a per-sample channel that the record rows do not hold, then the fitdocs test suite shall fail.

### Requirement 4: Values, Units and Meaning
**Objective:** As an agent writing SQL against the index, I want absent values
absent, units in the column names and every column described in the database
itself, so that I can trust a value without reading fitdocs's source.

#### Acceptance Criteria
1. fitdocs shall hold a value the page or its files do not record, or that fitdocs cannot compute, as SQL NULL, and shall never hold zero, a default, NaN or an infinity in its place.
2. fitdocs shall name every column that carries a unit with that unit's suffix in the style the frontmatter uses (for example `_m`, `_s`, `_bpm`, `_w`, `_mps`, `_rpm`, `_c`, `_pct`).
3. fitdocs shall give every table and every column of the index a non-empty description in the database's own table and column comments, stating the value's meaning and, for a column with a unit, the unit in words; and shall reapply every description whenever it creates the schema.
4. fitdocs shall store every instant in a type any DuckDB client reads without a time-zone extension or library, and shall state in each such column's description whether it holds UTC or local wall-clock time.
5. fitdocs shall hold the same rows, compared as sets, for the same data root, athlete profile, settings and fitdocs version, whichever order pages were indexed in, whether a page's computed values were handed over by the command that wrote it or computed by the refresh, and whether the index was refreshed incrementally or built from empty.
6. If a table or column of the index lacks a description, or a column named with a unit suffix has a description that does not name that unit, then the fitdocs test suite shall fail.

### Requirement 5: Agreement with the Documents
**Objective:** As an athlete, I want one stated rule for how the index relates to
my documents, including after I change `athlete.toml` without regenerating, so
that I know what an answer from the index means.

#### Acceptance Criteria
1. When a workout page's file changes in any way, or the page's file is renamed, fitdocs shall bring that page's document values in the index level with the file at the next refresh.
2. fitdocs shall recompute a page's computed values only when the page's rendering changed since they were last computed, when the page has none in the index, or when an earlier attempt left it without them; and shall not recompute them for a change that is confined to the page's effort tag, its load keys or load region, its `notes` or `workout` regions, or its file name.
3. When a refresh computes values for a page that the same command wrote, fitdocs shall take them from the composed activity, derived metrics and athlete inputs the command rendered that page from.
4. When a refresh computes values for a page that the same command did not write, fitdocs shall compose the page's activity from its listed archived files by the rule the training-load pass applies, and compute its metrics under the athlete inputs current when the refresh runs.
5. fitdocs shall change no row of the index for a change to the athlete inputs alone, and shall record the fingerprint of the athlete inputs current at the last refresh in the index's metadata, so that every activity row computed under other inputs can be found by comparing the two fingerprints.
6. fitdocs shall never read the index to produce a document, a document value, or the output of any command other than `fitdocs index` and the analytics commands built on it.
7. The published ownership contract shall state this agreement rule: document values follow every change of a page; computed values follow the page's rendering; `fitdocs regen` brings documents and index forward together after the athlete inputs change; and a build computes every page under the athlete inputs current at that build.

### Requirement 6: Page Keys and Page-Level Consistency
**Objective:** As an agent joining the index's tables, I want each page held
under one key that survives a rename and never held twice, so that joins and
counts are exact.

#### Acceptance Criteria
1. fitdocs shall key every page's rows by the content hash of the page's base file, so that renaming the page's file keeps its key and moves none of its computed values.
2. If two workout pages list the same base file, then fitdocs shall index the one whose data-root-relative path sorts first, hold no row for the other, and report the page left out and the page it collides with.
3. fitdocs shall replace a page's rows in every table as one unit, so that a reader never sees a page with some old and some new rows, or the same page twice.
4. When a page's base changes (a higher-ranked file joins it), fitdocs shall remove every row held under the page's former key and hold the page under its new key.
5. When the same page is indexed again into an index that already holds it, fitdocs shall hold exactly one set of that page's rows afterwards, enforced by the refresh's replace-as-a-unit step rather than by any database key or constraint.

### Requirement 7: The Refresh After Every Writing Command
**Objective:** As an athlete, I want the index kept current as a side effect of
the commands I already run, so that an agent can count on it without my asking.

#### Acceptance Criteria
1. When a writing command finishes its own passes, fitdocs shall run one refresh, after every document write of the command, the training-load and plan passes included.
2. The refresh shall add rows for every workout page the index does not hold, update the rows of every page that moved (Requirement 5), and remove every row of every page no longer in the data root.
3. When the effort tag is edited by hand, or the training-load pass rewrites a page's load region, fitdocs shall bring that page's document values level at the next writing command's refresh.
4. When a refresh finds no page added, moved or removed and no producer input changed, fitdocs shall leave every file in the index directory byte-identical.
5. When the refresh computes values for a page the same command wrote, fitdocs shall not read the page's archived files again, for every page up to a bound on retained samples that the design states; beyond that bound fitdocs shall compute them by Requirement 5.4.
6. When a refresh changed the index, the command shall print one line counting the pages added, updated and removed; and when a refresh changed nothing and met no problem, the command shall print nothing about the index.
7. When a refresh or build has more than 100 pages whose computed values must be computed, fitdocs shall report progress on the standard error stream, as pages done out of pages to do, at least once every 100 such pages.
8. fitdocs shall not open, create or refresh the index during `check`, `history`, `plan`, `derive-benchmarks`, `connect`, `pull` without `--sync`, `plugins`, `skill` or `--version`.

### Requirement 8: Never an Automatic Build
**Objective:** As an athlete with years of workouts, I want a routine sync never
to turn into a long backfill I did not ask for, so that the index costs nothing
until I choose to build it.

#### Acceptance Criteria
1. If the index file does not exist when a writing command's refresh would run, then fitdocs shall not create it, and shall print one line saying the index is not built and that `fitdocs index` builds it.
2. If the index file exists but cannot be opened because it is corrupt, unreadable or in a storage format the installed DuckDB cannot read, or it records a schema version other than fitdocs's, then fitdocs shall leave it unchanged during a writing command and print one line naming the reason and saying that `fitdocs index` rebuilds it.
3. fitdocs shall build or rebuild the index only when the athlete runs `fitdocs index`.

### Requirement 9: The Pipeline Never Pays for the Index
**Objective:** As an athlete, I want index trouble reported but never allowed to
fail, roll back or skip a document write, so that my workout pages are exactly
what they would be without the index.

#### Acceptance Criteria
1. fitdocs shall complete every document write of a writing command before its refresh begins.
2. If a writing command's refresh fails for any reason (another program holding the index, a full disk, a corrupt file, a refused index location, an error computing a page's values), then fitdocs shall print what failed and the command shall exit with the code it would have exited with had the refresh not run.
3. If another program holds the index open when a refresh needs it, then fitdocs shall say so without waiting, naming the holding process's id when the database reports one, and saying that closing that program lets the next refresh proceed.
4. If computing one page's rows raises an unexpected error, then fitdocs shall keep that page's previous rows, report the page and the error, continue with the other pages, and retry that page at the next refresh.
5. fitdocs shall carry no state between refreshes other than the index itself, so that a refresh that was skipped, failed or was interrupted is made good by the next successful one.
6. If a refresh is interrupted, then the index shall hold each page's rows as they were either before or after that page's update, never a mixture.
7. fitdocs shall leave every workout page, archived file and other data-root file byte-identical to what the same command writes when the index is absent.

### Requirement 10: The `fitdocs index` Command
**Objective:** As an athlete or an agent, I want one command that brings the
index current from any state, so that building, backfilling and recovering are
one thing to remember.

#### Acceptance Criteria
1. fitdocs shall provide a `fitdocs index` command that resolves the data root as other commands do, accepts `--out`, and runs the same refresh as a writing command.
2. When the index file does not exist, `fitdocs index` shall build it from every workout page.
3. Where `--rebuild` is given, `fitdocs index` shall build a new index from empty by the same refresh, whatever state the existing index is in.
4. If the existing index cannot be opened because it is corrupt, unreadable or in a storage format the installed DuckDB cannot read, or records another schema version, then `fitdocs index` shall rebuild it, saying why.
5. fitdocs shall write every build to a separate file and put it in place of the index only once it is complete, so that a reader opening the index during a build sees either the whole former index or the whole new one.
6. fitdocs shall ensure that no recovery data of a replaced index file is ever applied to the index that replaces it.
7. If the operating system refuses to replace the index file with a completed build because another program holds it open, then fitdocs shall keep the completed build beside the index, say so, and put it in place at the start of the next `fitdocs index` run.
8. When `fitdocs index` finishes, it shall print the index file's absolute path, its schema version, the number of workout pages it holds, the pages added, updated and removed, and the pages without computed values with the reason for each.
9. `fitdocs index` shall exit 0 when the index is current at exit (pages without computed values included); 1 when the index could not be brought current (another process writing or holding it, a write error, an unexpected error computing a page); and 2 when the data root, the index location, the settings or the athlete profile is invalid.
10. `fitdocs index` shall make no network request and write nothing inside the data root.

### Requirement 11: One Writer at a Time
**Objective:** As an athlete running fitdocs from several terminals or agents, I
want concurrent writers refused rather than interleaved, so that the index is
never written by two processes at once.

#### Acceptance Criteria
1. fitdocs shall let at most one fitdocs process write a data root's index at a time.
2. If a refresh or `fitdocs index` finds another fitdocs process writing the same index, then fitdocs shall report it at once, without waiting, and leave the index to that process.
3. fitdocs shall hold no lock or marker file whose presence alone blocks a later writer after the process that held it has ended.
4. fitdocs shall write the index in a storage format every DuckDB 1.x release from 1.0 on can open, so that an athlete's or agent's own 1.x client reads it.

### Requirement 12: No Network, and the Runtime Dependency
**Objective:** As an athlete, I want the index to add a library but no network
path, so that fitdocs's network promises still hold.

#### Acceptance Criteria
1. fitdocs shall configure every database connection it opens so that the database library cannot install or load an extension, read or write any file other than the index and its own working files, or keep a secret, and so that no statement on the connection can re-enable any of these.
2. fitdocs shall make no network request while opening, refreshing, building or rebuilding the index, including when a value or statement it handles contains a web address.
3. fitdocs shall declare DuckDB as a required runtime dependency in the version range from 1.1 up to but excluding 2, and shall declare no optional dependency group.
4. fitdocs shall not load the DuckDB library during plugin discovery, or during any command or import that does not open the index.
5. The published list of commands that make no network request shall include `fitdocs index`, and the network statement shall say that it binds the connections fitdocs opens, not another program that opens the index file.
6. The installation documentation shall state DuckDB's installed size and the platforms for which no prebuilt package exists (musl-based Linux, free-threaded Python builds).

### Requirement 13: Extending the Index
**Objective:** As the maintainer of a later feature, I want to add index tables
by registering a producer, so that they are refreshed and rebuilt by the same
pass and described by the same comments, without changing the pass.

#### Acceptance Criteria
1. fitdocs shall build every index table other than its own bookkeeping from registered producers, each declaring its tables, their columns in order, each column's type and every description.
2. fitdocs shall replace a per-page producer's rows for a page in the same unit as the page's other rows, refreshing them by the document-values rule or the computed-values rule of Requirement 5 as the producer declares.
3. fitdocs shall hand a corpus-level producer the data root as the refresh leaves it, have it declare a fingerprint of its inputs, and replace its tables whole when, and only when, that fingerprint, the fitdocs version or the schema version differs from the one recorded for it.
4. fitdocs shall let a later feature register a producer without changing the refresh, the build, the `index` command or the database connection code.
5. fitdocs shall record in the index its schema version, the fitdocs version that last wrote it, the DuckDB version, the data root, the athlete-input fingerprint, each page's fingerprints and computed-values state, and each producer's fingerprint.
6. fitdocs's schema version shall be 1 when this feature lands, and every later feature that adds, removes or renames a table or column, or changes a column's type or order, shall advance it by exactly one from the value current when that feature lands.
7. If the tables, columns, types or column order fitdocs creates differ from those recorded for the current schema version, then the fitdocs test suite shall fail.
8. When the fitdocs version recorded in the index differs from the running one, the refresh shall reapply every table and column description and record the running version.

### Requirement 14: The Published Contract, Steering and Evidence
**Objective:** As a person or agent relying on fitdocs's stated guarantees, I
want the new write location and the new dependency stated where the other
guarantees are, and proven by tests that can fail, so that the promises stay
true.

#### Acceptance Criteria
1. The published ownership contract shall state the index's location and resolution order, its refusal inside the data root, that it is a disposable cache, the overwrite semantics of the refresh and of `fitdocs index`, and that the refresh writes only inside the index directory.
2. The published contract version shall advance by one from the value current when this feature lands, and the contract's statement of what changed at that version shall name this feature's changes.
3. fitdocs shall leave the document-format version and every managed frontmatter key unchanged, and shall write every workout page byte-identically to how it wrote it before this feature landed.
4. The release notes shall state, under the unreleased entry, the new `fitdocs index` command, the refresh after every writing command, the index location and its environment variable, that `fitdocs index` must be run once to build the index, and the new runtime dependency with its installed size.
5. The steering documents shall state the index as a derived cache that is not state, DuckDB among the key libraries, the network statement of criterion 12.5, and the index package's place in the dependency direction.
6. The fitdocs test suite shall never read or write the real user's cache, configuration or home directory while exercising the index.
7. If any writing command or `fitdocs index` writes outside the data root's permitted locations and the resolved index directory, or if any module other than the one connection module imports the DuckDB library, then the fitdocs test suite shall fail.
8. The amendment records of `plugin-api` (its dependency baseline), `distribution` (its exact dependency list, its pre-feature dependency snapshot and the install footprint), `workout-docs` (the hand-over out of the sync engine) and `connectors` (the no-network command list) shall name this feature's change.
