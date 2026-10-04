# Requirements Document

## Project Description (Input)
Agents querying the athlete's analytics index (`analytics-index`) get the raw
facts as SQL tables, but four kinds of question are still expensive or wrong to
answer from those tables alone: best efforts over a duration (a rolling window
over about 9 million per-second rows that must handle pauses correctly);
fitness, fatigue and form (an exponentially weighted series a hand-rolled query
would compute differently from the history page); the thresholds in force on a
date (held only in `athlete.toml`); and plan compliance (blocks, mesocycles,
planned workouts and their reconciliation, held only as rendered `blocks/`
pages). This spec registers four producers through `analytics-index`'s producer
seam: per-page mean-max curves from a new pure function in `fitdocs.metrics`,
and three corpus-level tables (the daily load series, the benchmark timeline
and training blocks) that call the owning engines' existing code so the index
never disagrees with the history page, the athlete profile or the block page.
Source: `.kiro/specs/analytics-derived/brief.md`; Phase 10 of
`.kiro/steering/roadmap.md`. Dependencies: analytics-index.

## Introduction

The analytics index holds what fitdocs knows about each workout page. This
feature adds four answers that are expensive or easy to get wrong from those
rows alone:

- **Best efforts.** Each page's best average power, speed and heart rate over a
  fixed set of durations, under one stated rule for pauses and dropouts.
- **Fitness, fatigue and form.** The daily and weekly series `fitdocs history`
  computes, for every methodology the pages record a load under.
- **The benchmark timeline.** Every benchmark in `athlete.toml`, and the period
  each one is in force, so a workout can be joined to the thresholds of its day.
- **Training blocks.** Blocks, mesocycles and planned workouts, with each
  planned workout's resolution as the plan pass decides it.

One stance governs all four: **one computation, two projections.** Best efforts
are the one new computation. Everything else is the owning command's own
computation, landing in one more place, so the index can never disagree with the
history page, the athlete profile or a block page for the same inputs.

Terms used below:
- A **workout page**, a page's **key**, its **composed activity**, its
  **rendering**, **computed values**, a **refresh** and a **build** are
  `analytics-index`'s terms.
- A **channel** here is one of power, speed and heart rate.
- A **best effort** of a channel over a duration is the highest average value of
  that channel over any window of that duration that the rule of Requirement 2
  allows.
- A **methodology** is a training-load calculator id as a workout page records
  it beside its load.
- A **plan source** is an athlete-owned block definition the plan pass reads; the
  **current date** is the date the command that runs the refresh takes as today.
- The **corpus-level tables** are the load-series, benchmark and block tables:
  each is computed from the whole data root, not from one page.

## Boundary Context

- **In scope**: the best-effort rows of every workout page and the rule that
  decides them, as a computation of the activity alone with its recorded
  choices; the daily and weekly load series and the series' terms per
  methodology; the benchmark entries and their in-force periods; blocks,
  mesocycles, planned workouts, their resolution, claimed pages and unplanned
  pages; when each of these tables is recomputed; their descriptions and units;
  the schema-version advance; the release notes; the steering and amendment
  records this feature needs.
- **Out of scope**: the index store, location, refresh and producer mechanism
  and the `fitdocs index` command (`analytics-index`); `fitdocs query`, its
  sandbox and the agent skill's mechanics (`analytics-query`); a best-effort
  section in workout documents (a follow-on); best efforts by distance (fastest
  5 km) or for any channel other than power, speed and heart rate; new load or
  fitness methodologies; forecasting form from a plan; the cross-discipline
  threshold borrowing the training-load calculator applies; free-text values
  (benchmark notes, planned-workout prescriptions, override reasons,
  explanatory text); a plan's amendment trail and original rows.
- **Adjacent expectations**: `analytics-index` refreshes these tables with its
  own pass, holds per-page rows under its stale-document rule and replaces a
  corpus-level table whole when its inputs move. `load-history`, the athlete
  profile (`athlete-benchmarks`, `performance-benchmarks`) and the plan pass
  (`training-blocks`, `plan-resolution`) keep computing exactly what they
  compute today; this feature calls their computations and changes none of
  their outputs. `analytics-query` projects these tables' descriptions in its
  schema view and documentation.

## Requirements

### Requirement 1: Best Efforts for Every Workout Page
**Objective:** As an agent asked for the athlete's best 20-minute power this
year, I want each workout page's best efforts held in the index, so that I can
answer with a simple query instead of a rolling window over millions of samples
that I would likely get wrong at pauses.

#### Acceptance Criteria
1. fitdocs shall hold, for each workout page with computed values, one best-effort row per duration of the duration set (Requirement 2) that at least one channel supports, carrying the page's key, the duration in seconds, and for each channel its best effort and the number of seconds after the activity's start at which that best window begins.
2. fitdocs shall compute a page's best efforts from its composed activity, so that a channel an extra donates yields best efforts as the base's own channels do.
3. If a page's activity cannot support a channel's best effort for a duration, because the channel was never recorded or no continuous stretch of it lasts that long, then fitdocs shall hold that channel's best effort and window start for that duration as NULL, never zero.
4. fitdocs shall hold no best-effort row for a duration that no channel of the page supports, and none for a page without computed values.
5. fitdocs shall bring a page's best efforts level by the rule the index applies to computed values: recomputed when the page is new, when its rendering changed, or when an earlier attempt left it without computed values, and not for a change confined to its effort tag, its load, its `notes` or `workout` regions or its file name.
6. fitdocs shall hold the same best-effort rows for a page whether the command that wrote it handed its activity over or the refresh re-derived it from the archived files, and whether the index was refreshed incrementally or built from empty.

### Requirement 2: One Stated Rule for a Best Effort
**Objective:** As an athlete comparing best efforts across devices and years, I
want one rule for what counts as a best effort, decided once and stated where I
can read it, so that a number means the same thing on every page.

#### Acceptance Criteria
1. fitdocs shall compute best efforts over one fixed duration set, running from 1 second to 6 hours, that is the same for every page and every channel.
2. fitdocs shall take a best effort only over a window of continuous recording, and shall treat as a break in continuity every step between two consecutive recorded values of the channel that is longer than a stated maximum step, whether the step comes from a pause in recording or from a dropout of that channel alone.
3. Within a stretch of continuous recording, fitdocs shall credit each second of a window with the value the channel most recently recorded at or before that second, and shall never credit a second with a value from another stretch or with a value the channel did not record.
4. fitdocs shall count a recorded zero (power while coasting, speed while stopped without a pause) as a real value, and shall never count an unrecorded value as zero.
5. When two or more windows of one duration share the best average, fitdocs shall report the earliest.
6. fitdocs shall hold every best effort unrounded.
7. fitdocs shall record the duration set and the maximum step as fitdocs's own choices, each with the justification for its value and the basis for concluding that no published work defines it, and the fitdocs test suite shall fail if the computation uses a duration or a maximum step that is not read from those records.
8. fitdocs shall make the best-effort computation depend on the activity alone, independent of the index, so that a later workout-document section can show the same numbers.

### Requirement 3: Fitness, Fatigue and Form by Day
**Objective:** As an agent asked what the athlete's form was before a race, I
want the daily series `fitdocs history` computes held in the index for every
methodology the pages record, so that I never re-implement the exponentially
weighted model and never disagree with the history page.

#### Acceptance Criteria
1. fitdocs shall hold, for each methodology that at least one workout page records a load under, one daily row per day of that methodology's series, carrying the methodology, the date, the recorded load, the number of pages counted that day and the number of them carrying a load, fitness, fatigue, form, and whether the day is suppressed.
2. fitdocs shall hold, for each methodology, exactly the days, recorded loads, page counts, fitness, fatigue and form that `fitdocs history --methodology <that methodology>` computes for the same data root and settings, including where the series starts and ends and how a day whose pages carry no load is counted.
3. While a day falls in a week the history computation suppresses for low coverage, fitdocs shall hold that day's fitness, fatigue and form as NULL and mark the day suppressed, as the history page withholds them.
4. fitdocs shall hold no daily row for a day after the last day that contributes a load to a methodology's series, and no daily row at all when no workout page records a load.
5. fitdocs shall mark, among the methodologies it holds, the one `fitdocs history` shows when run without `--methodology`, and shall mark none when that command would refuse to choose one.

### Requirement 4: Weekly Rows and the Series' Terms
**Objective:** As an agent asked for weekly volume and how fitness is defined, I
want the weekly table and the model's terms held as the history computation has
them, so that a weekly total or a fitness value is queryable with its meaning.

#### Acceptance Criteria
1. fitdocs shall hold, for each methodology, one weekly row per ISO week of its series, carrying the week's Monday, its ISO year and week number, its number of days within the series, its total load, sessions, pages and pages carrying a load, its fitness, fatigue and form at its last day within the series, and whether it is suppressed, exactly as `fitdocs history --methodology <that methodology>` computes them.
2. While a week is suppressed, fitdocs shall hold its fitness, fatigue and form as NULL.
3. fitdocs shall hold, for each methodology, one series row carrying the series' first and last day, the two time constants and two weightings the model ran with, whether those are fitdocs's shipped starting values or the athlete's configured ones, and the coverage threshold below which a week is suppressed.
4. fitdocs shall hold every load, fitness, fatigue and form value unrounded, where the history page shows them to one decimal place.

### Requirement 5: The Benchmark Timeline
**Objective:** As an agent asked what the athlete's FTP was on the day of a ride,
I want every benchmark and the period each one is in force held in the index,
so that a query can join a workout to the thresholds in force on its date.

#### Acceptance Criteria
1. fitdocs shall hold one benchmark row per benchmark entry the athlete profile records, carrying its kind, its discipline or none for an athlete-wide kind, its value, its kind's unit, the date it was measured, the date it applies from when one is recorded, and its source when one is recorded: whether it was derived or measured and, for a derived entry, the derivation method, the page it was derived from and the citation key.
2. fitdocs shall hold, for each kind and discipline the profile records, one in-force row per period during which a single entry is the one in force, carrying the kind, the discipline, the period's first day, the first day after it (none while it is still in force), the entry's value and measured date, and whether the period precedes that measured date because the entry applies retroactively.
3. fitdocs shall make the in-force entry for every kind, discipline and date exactly the entry the athlete profile's own in-force rule selects for them, and shall hold no in-force row covering a date for which that rule selects none.
4. fitdocs shall hold each benchmark value in the unit its kind names (watts, beats per minute, or seconds per kilometre), never converted.
5. fitdocs shall hold in-force periods per discipline as the profile records them, without the cross-discipline borrowing the training-load calculator applies (a walk borrowing a run's threshold).
6. If the athlete profile does not exist or records no benchmark, then fitdocs shall hold no benchmark row and no in-force row.
7. fitdocs shall not hold a benchmark's note, a derived benchmark's explanatory inputs text, or a threshold recorded outside the benchmark entries (the profile's flat FTP, heart-rate and zone values).

### Requirement 6: Training Blocks and Their Resolution
**Objective:** As an agent asked which planned sessions the athlete missed this
block, I want blocks, mesocycles and planned workouts held in the index with
each planned workout's resolution as the plan pass decides it, so that plan
compliance is a query instead of a read of rendered block pages.

#### Acceptance Criteria
1. fitdocs shall hold one block row per plan source the plan pass discovers, carrying the block's identity, its source file's data-root-relative path, whether the source is valid, the number of problems the plan pass reports for it, and, for a valid source, its title, goal, first and last day and mesocycle length.
2. fitdocs shall hold, for each mesocycle of a valid block, one row carrying its number, first and last day, nominal and actual length in days, its target load and focus when stated, and the actual-load picture the plan pass computes for it: the methodology its load is summed under, its total load, whether that total is a lower bound, its percent of target, and how many pages in its window are counted, scored, unscored, excluded and unplanned.
3. fitdocs shall hold, for each planned workout in a valid block's current plan, one row carrying its identity, its block and mesocycle, its date, sport, modality and indoor flag when stated, its title and summary, its resolution state (matched, overridden, skipped, not logged or upcoming), its match confidence when matched, and the date of the override that decided it when one did.
4. fitdocs shall hold one row per workout page a planned workout claims, by match or by override, carrying the page's data-root-relative path and the page's index key when the index holds that page, and one row per page an override names that does not exist, marked as not found.
5. fitdocs shall hold, for each mesocycle, one row per unplanned workout page in its window, carrying the page's data-root-relative path and the page's index key when the index holds that page.
6. fitdocs shall decide every resolution state, confidence, claimed page, unplanned page and mesocycle load exactly as the plan pass decides them for the same plan sources, workout pages, settings and current date.
7. fitdocs shall hold a planned workout that has no logged candidate and no override as not logged when its date is before the current date and as upcoming otherwise, taking the current date from the command that runs the refresh, and shall record that date on every block row.
8. fitdocs shall hold no mesocycle, planned-workout or page row for an invalid plan source, and no block-table row of any kind when the plan pass discovers no plan source.
9. fitdocs shall not hold a planned workout's prescription, an override's reason, a block's amendment trail or the rows of its plan before amendment.

### Requirement 7: One Computation, Two Projections
**Objective:** As an athlete, I want each derived table to equal what the owning
command shows for the same inputs, so that the index can never disagree with my
history page, my profile or my block pages.

#### Acceptance Criteria
1. fitdocs shall compute the load-series and block tables over every workout page the owning command reads, including pages the index holds no rows for (a page without an archived base reference, a page listing another page's base file).
2. fitdocs shall leave every workout page, history page, block page, the athlete profile and every other data-root file byte-identical to what the same commands write without this feature.
3. fitdocs shall leave the output and exit code of `fitdocs history`, `fitdocs plan`, `fitdocs derive-benchmarks` and every writing command unchanged, apart from what the index already reports.
4. fitdocs shall hold each corpus-level table as its inputs stood at the last refresh, so that a change to the athlete profile, a plan source, the settings or a workout page reaches it at the next refresh without a `fitdocs regen`.
5. The fitdocs test suite shall check each derived table against the owning computation's own output for the same fixture, on fixtures where a different computation would produce different values, and never against the index's own earlier output.

### Requirement 8: When the Derived Tables Move
**Objective:** As an athlete who syncs often, I want each derived table
recomputed only when what it is computed from changed, so that a routine sync
costs no more than it must and an unchanged index stays byte-identical.

#### Acceptance Criteria
1. fitdocs shall recompute the load-series tables when, and only when, a markdown file directly in the data root's workouts folder or the settings file changed since they were last computed, or the fitdocs version or schema version changed.
2. fitdocs shall recompute the benchmark tables when, and only when, the athlete profile file changed since they were last computed, or the fitdocs version or schema version changed.
3. fitdocs shall recompute the block tables when, and only when, a plan source, a markdown file directly in the data root's workouts folder or the settings file changed since they were last computed, the fitdocs version or schema version changed, or, while at least one plan source exists, the current date changed.
4. When fitdocs recomputes a corpus-level table, fitdocs shall replace it whole, so that a reader never sees part of the old table beside part of the new one.
5. If computing a corpus-level table fails (a malformed settings file, a malformed benchmark entry in the athlete profile, a plan source directory the settings name that does not exist), then fitdocs shall keep that table's previous rows, report the failure as the index reports any table it could not refresh, retry at the next refresh, and refresh every other table as usual.
6. When a refresh finds no workout page added, moved or removed and none of the inputs of criteria 1 to 3 changed, fitdocs shall leave every file in the index directory byte-identical.
7. fitdocs shall hold the same derived rows, compared as sets, for the same data root, athlete profile, settings, plan sources, current date and fitdocs version, whatever order pages were indexed in and whether the index was refreshed incrementally or built from empty.

### Requirement 9: Values, Units and Descriptions
**Objective:** As an agent writing SQL against the derived tables, I want absent
values absent, units in the column names and every table and column described
in the database itself, so that I can use a value without reading fitdocs's
source.

#### Acceptance Criteria
1. fitdocs shall hold a value that is not recorded, not applicable or not computable as NULL, and never as zero, a default, NaN or an infinity, except where the owning computation itself holds a zero (a day with no load in the history series), which fitdocs shall hold as that computation holds it.
2. fitdocs shall name every column that carries a unit with that unit's suffix in the style the index uses, and shall describe the unit in words.
3. fitdocs shall give every table and column it adds a non-empty description stating its meaning, and shall state in each corpus-level table's description which command's computation it equals and that it reflects its inputs as of the last refresh.
4. fitdocs shall hold every date as a calendar date and every window start as seconds since the activity's start.
5. If a table or column this feature adds lacks a description, or a unit-suffixed column's description does not name its unit, then the fitdocs test suite shall fail.

### Requirement 10: Schema Version, Published Statements and Records
**Objective:** As a person or agent relying on fitdocs's stated guarantees, I
want the new tables versioned, announced and recorded where the other
guarantees are, so that an index built before this feature is rebuilt rather
than silently missing tables.

#### Acceptance Criteria
1. fitdocs's index schema version shall advance by exactly one from the value current when this feature lands, and the fitdocs test suite shall fail if the tables, columns, types or column order fitdocs creates differ from those recorded for that version.
2. When a writing command meets an index built under the earlier schema version, fitdocs shall report that it needs a rebuild, and `fitdocs index` shall rebuild it with the derived tables filled.
3. The release notes shall state, under the unreleased entry, the derived tables and that `fitdocs index` must be run once after upgrading to build them.
4. When the later of this feature and `analytics-query` lands, the published analytics documentation's schema reference shall list the derived tables, and the agent skill's worked examples shall include at least one query over each of best efforts, the load series, the benchmark timeline and the block tables.
5. The steering documents shall state which engines the index's derived tables may call.
6. The `fit-ingest` amendment record shall name the best-effort computation and its recorded choices.
7. fitdocs shall add no write location, network request, clock read or runtime dependency, and shall leave the document-format version, the managed frontmatter keys and the ownership contract version unchanged.
8. If building the index over a data root that carries loads, benchmarks and plan sources writes anywhere outside the index directory, or leaves any derived table empty, then the fitdocs test suite shall fail.
