# Requirements Document

## Project Description (Input)
**Who has the problem.** An athlete who keeps a markdown wiki with fitdocs,
and the agent that maintains it. Reading a workout, the question after "how
did it go?" is "what state was I in?": a short night, a resting heart rate
6 bpm up, an HRV below its usual range. That answer decides whether a bad
session was the legs or the day.

**Current situation.** A workout page knows nothing about the day around the
workout; the answer sits in another app. Phase 12's `wellness-store` brings
daily wellness into fitdocs as one source-attributed series, and `recovery`
computes each signal's per-source baseline and normal range. Workout pages
are rendered by `fitdocs sync`, the inbox drain and `fitdocs regen` from
archived `.fit` files, and a page is re-rendered only when its own files
change. Wellness for the morning of a workout often arrives after the
workout's file (HealthFit sends the previous night's HRV the next morning),
and an intervals.icu pull or a Garmin or Apple export can bring years of
backfill at once, touching about 2,500 of the maintainer's pages.

**What should change.** Each workout page carries a small, fitdocs-owned,
descriptive morning-of block for the workout's local date: that morning's
resting heart rate and HRV, each against the athlete's own baseline and
normal range for its source, and the previous night's sleep with its stages
where recorded. The block reads only the wellness series and the shared
baselines, never the analytics index or the recovery page, and never shows a
zero for something not recorded. When wellness for a page's day arrives or
changes, the page's block is refreshed in the same run without a full
`fitdocs regen`, and only the pages whose block changed are rewritten.

Source: `.kiro/specs/workout-wellness/brief.md`; Phase 12 of
`.kiro/steering/roadmap.md`. Dependencies: `wellness-store`, `recovery`.
Downstream: none.

## Introduction

This feature puts the day around a workout onto the workout's own page and
keeps it current as wellness arrives.

Terms used below:
- The **wellness series**, a **source**, a **metric**, a **wellness day**, a
  value's **origin** and the **day-boundary rule** are as `wellness-store`
  defines them. Under that rule, the night before a workout on date D is the
  sleep of wellness day D, and that morning's resting heart rate and HRV are
  wellness day D's values.
- A workout page's **date** is the local date the page records for the
  workout (its `date` frontmatter value).
- The **baselined signals** are resting heart rate, HRV measured as SDNN and
  HRV measured as rMSSD. The **sleep signals** are total sleep, deep, light
  and REM sleep, awake time in sleep, and average heart rate in sleep.
- For a signal and a day D, the **shown source**, the **day value**, the
  **7-day mean** (the seven days ending on D), the **normal range** and the
  **60-day mean** (both from the 60 days before D) and the **position** (the
  7-day mean below, within or above the normal range) are exactly the figures
  `recovery`'s baseline computation gives, the same figures the recovery page
  shows.
- The **morning-of block** is the part of a workout page this feature writes.
  Its **location** is a fitdocs-owned place on every workout page, delimited
  by machine-recognizable markers that are invisible in rendered markdown.
- The **wellness fingerprint** is the record, inside the block, of the facts
  the block shows.
- The **morning-of pass** is the step that brings every page's block up to
  date with the current wellness series.
- The **absence marker** is the en dash workout pages print in a table cell
  that has no value.

## Boundary Context

- **In scope**: the block's content, wording, placement and absence rules;
  Garmin attribution inside the block; the wellness fingerprint; the
  morning-of pass, the runs that carry it out and its report; the page-format
  version advance; the ownership-contract statements for the block location
  and the pass; how the analytics index treats a change confined to the
  block; the documentation, the packaged workouts skill and the release
  notes; the published-rule changes this feature makes to `workout-docs`,
  `wiki-contract` and `analytics-index`.
- **Out of scope**: computing baselines, normal ranges, 7-day means or the
  shown source (`recovery`); parsing, merging, precedence, the day-boundary
  rule and the series files (`wellness-store`); a readiness verdict, score,
  status label, recommendation or advice; charts in the block; any wellness
  signal other than the baselined and sleep signals on a workout page
  (weight, SpO2, respiration, steps, stress, body battery and subjective
  ratings stay on the recovery page); wellness on the history, block,
  planned-workout or dashboard pages; wellness in the analytics index's
  activity tables; a new command or setting; any change to training load,
  zones or benchmarks.
- **Adjacent expectations**: `wellness-store` rebuilds the series before
  pages are written in the inbox drain and first in `fitdocs regen`, and
  gives the one reader of the series; `recovery` gives the one baseline
  computation and shown-source rule, which this feature consumes unchanged so
  that the block and the recovery page never disagree; the analytics index's
  existing refresh picks up rewritten pages; the recovery command stays
  standalone and is not run by this feature.

## Requirements

### Requirement 1: The Morning-Of Block on Workout Pages
**Objective:** As an athlete reading a workout, I want the day's wellness on the workout's own page, in the same place on every page, so that I see what state I was in without opening another app.

#### Acceptance Criteria
1. fitdocs shall give every workout page, whatever its sport, one morning-of block location, placed immediately before the Training Load section and outside every user-owned region.
2. When the wellness series holds a figure the block shows for the page's date, fitdocs shall show the block at its location under a "Morning Of" heading.
3. If the wellness series holds no figure the block shows for the page's date, or the page records no date, then fitdocs shall show nothing at the block location: no heading, no sentence, no table and no zero.
4. fitdocs shall show in a page's block the wellness day equal to the page's date, so that the block of a workout on date D shows that morning's values and the night that ended on D.
5. The block shall state, in one sentence, the wellness day it shows, the days its 7-day means cover, and the days its normal ranges and 60-day means cover.
6. fitdocs shall render the block as plain markdown readable in any markdown renderer, with no chart, no image and no plugin syntax.
7. The block shall add no frontmatter key to the page.

### Requirement 2: Resting Heart Rate and HRV Against Baseline
**Objective:** As an athlete, I want that morning's resting heart rate and HRV each against my own normal range for the source that measured it, so that I can tell an ordinary morning from an unusual one.

#### Acceptance Criteria
1. When a baselined signal has a day value, a 7-day mean or a normal range to show for the page's date, the block shall show one row for it, named by the signal's wellness display label, in the order the recovery page lists the baselined signals.
2. Each baselined row shall show the shown source's day value, its 7-day mean, its normal range and the position of the 7-day mean against that range.
3. fitdocs shall take every figure and the shown source of the block from the same baseline computation the recovery page uses, so that the block and the recovery page show the same numbers for the same signal and day.
4. fitdocs shall show HRV measured as SDNN and HRV measured as rMSSD in separate rows and shall never combine, convert or compare one with the other.
5. fitdocs shall format every figure in the block with the unit symbol and precision the recovery page uses for that signal.
6. If a figure of a row is absent (no value that day, too few days for a 7-day mean, or too few days for a normal range), then fitdocs shall print the absence marker in that cell and never a zero.
7. When the shown source has no value on the page's date but supplies the row's other figures, the row shall show those figures, name that source, and print the absence marker for the day value.

### Requirement 3: The Previous Night's Sleep
**Objective:** As an athlete, I want the night before the workout beside its usual length, with its stages where my device recorded them, so that I can see whether I came in short on sleep.

#### Acceptance Criteria
1. When total sleep has a day value, a 7-day mean or a 60-day mean to show for the page's date, the block shall show a sleep table for the night that ended on the page's date, with a total-sleep row giving the shown source's value for that night, its 7-day mean and its 60-day mean, and no normal range.
2. Where the shown source of total sleep records deep, light or REM sleep, awake time in sleep, or average heart rate in sleep for that night, the sleep table shall add one row for each, in that order, with the same three figures from that same source.
3. fitdocs shall never place in the sleep table a stage or sleeping heart rate from a source other than the shown source of total sleep for that night.
4. If the shown source records no stage for that night, then the sleep table shall show the total-sleep row alone and shall show no stage as zero.
5. fitdocs shall show sleep durations as hours, minutes and seconds in the form the recovery page uses.

### Requirement 4: Sources and Garmin Attribution
**Objective:** As an athlete, I want every number in the block to name where it came from, and Garmin credited wherever Garmin data is shown, so that I compare like with like and honour the platforms' terms.

#### Acceptance Criteria
1. The block shall name, in each row, the source its figures come from and every origin recorded for the values those figures are computed from.
2. Where any figure in the block is computed from a value whose origin is Garmin, the block shall show a Garmin attribution line directly beneath its heading.
3. Where every value the block's figures are computed from has Garmin as its origin, the attribution line shall name Garmin as the data source.
4. Where the block's figures are computed from Garmin-origin values together with values of another or of no recorded origin, the attribution line shall name Garmin as one of the data sources together with other sources, and shall never present Garmin as the source of the whole block.
5. Where no figure in the block is computed from a Garmin-origin value, the block shall show no Garmin attribution.
6. fitdocs shall decide sources, origins and attribution from the wellness series' recorded values alone, so that the same series gives the same block however its files arrived.

### Requirement 5: Descriptive Only
**Objective:** As an athlete, I want the block to show my numbers without telling me what to do, so that the page stays a record and the judgement stays mine.

#### Acceptance Criteria
1. The block shall describe each signal against its baseline and shall state no verdict, readiness, score, status label, recommendation, warning or advice.
2. The block shall word a position only as the 7-day mean lying below, within or above the normal range.
3. The block shall show no wellness signal other than the baselined signals and the sleep signals.

### Requirement 6: The Wellness Fingerprint
**Objective:** As the maintainer of a wiki under version control, I want each page to record exactly what its block shows, so that a page changes only when what it shows changes.

#### Acceptance Criteria
1. fitdocs shall record in every non-empty block a wellness fingerprint of the facts the block shows (the wellness day, and for each row its signal, source, origins and each figure as printed) together with the block's format version, in a form invisible in rendered markdown.
2. When two blocks show the same facts in the same format version, fitdocs shall give them the same fingerprint, and when the facts differ it shall give them different fingerprints.
3. The fingerprint shall contain no run date, run time, fitdocs release version or machine-specific value.
4. fitdocs shall change a page's block only when what the block shows changes, so that a wellness value that changes no printed figure (a digit below the shown precision, or a signal the block does not show) leaves the page unchanged.

### Requirement 7: Refreshing Blocks When Wellness Changes
**Objective:** As an athlete whose wellness arrives after the workout or in large backfills, I want the affected pages updated in the same run, without a full regeneration, so that my pages stay current at a bounded cost.

#### Acceptance Criteria
1. After `fitdocs sync` (with a source, or as the inbox drain), `fitdocs pull --sync` and `fitdocs regen` have written their workout pages, fitdocs shall run the morning-of pass once over the data root's workout pages, before the analytics index is refreshed in the same run.
2. During the morning-of pass, fitdocs shall rewrite a page only when its block differs from the block the current wellness series gives for the page's date.
3. When the morning-of pass rewrites a page, fitdocs shall change only the block, leaving every other byte of the page unchanged.
4. When the wellness series changes the values of a wellness day X, the morning-of pass shall leave unchanged every page dated before X or more than 60 days (the length of the normal-range window) after X.
5. However many wellness days changed in a run, fitdocs shall refresh all affected pages in that one morning-of pass, reading each workout page once and reading no `.fit` file.
6. When neither the wellness series nor any page's date or block changed since the previous run, the morning-of pass shall write nothing.
7. fitdocs shall write each page the morning-of pass rewrites atomically, so that a page holds either its previous bytes or its new bytes.
8. The morning-of pass shall never change a page's frontmatter, charts, training-load region, user-owned regions or any file other than the workout page itself.
9. `fitdocs load`, `fitdocs history`, `fitdocs plan`, `fitdocs recovery`, `fitdocs index`, `fitdocs check` and `fitdocs query` shall not run the morning-of pass, and fitdocs shall add no command for it.

### Requirement 8: Pages and Series the Pass Cannot Use
**Objective:** As an athlete or agent reading the run report, I want every page the pass could not bring up to date named with the reason, so that nothing is silently stale.

#### Acceptance Criteria
1. If the wellness series cannot be read, then the morning-of pass shall leave every page untouched, report that the blocks were not refreshed with the reason, and shall not change the run's exit status.
2. If a page records a page-format version newer than the installed fitdocs writes, then the morning-of pass shall leave that page untouched.
3. If a page has no block location (a page written by an older fitdocs, or one whose block markers were removed), then the morning-of pass shall leave it untouched; and when the wellness series holds any value, the report shall state how many such pages there are and that `fitdocs regen` adds the block.
4. If a page's region markers are damaged, then the morning-of pass shall leave that page untouched, report it as failed with the reason, and the run shall exit with the failure status.
5. If writing a page fails, then the morning-of pass shall report that page as failed with the reason, continue with the other pages, and the run shall exit with the failure status.
6. The morning-of pass shall never follow a symlinked workout page and shall never treat a page that is not a fitdocs workout document as one.
7. When the morning-of pass rewrites or fails any page, the run report shall state how many pages it updated, how many blocks it removed, and each failed page with its reason; when it has nothing to report, the run report shall print nothing for it.

### Requirement 9: Regeneration and the Page Format
**Objective:** As an athlete upgrading fitdocs, I want my existing pages to gain the block through the usual regeneration, and every page to stay re-derivable, so that the upgrade is one command.

#### Acceptance Criteria
1. fitdocs shall advance the workout page-format version by one from its value at landing, so that `fitdocs check` reports every page written before this feature as out of date with `fitdocs regen` as the remedy.
2. When `fitdocs regen` completes with a readable wellness series, every workout page it wrote shall carry the block the current series gives for its date.
3. fitdocs shall be able to rebuild every workout page's block by regeneration from the data root's archived wellness files and settings, in addition to the inputs regeneration already uses for the rest of the page.
4. Given the same workout pages and the same wellness series, the morning-of pass shall write byte-identical blocks on any machine, in any timezone and on any date.
5. fitdocs shall replace any content in the block location that differs from the block the current series gives the next time the morning-of pass runs, and shall never treat the block location as user-owned.

### Requirement 10: The Analytics Index
**Objective:** As an athlete whose index is refreshed after every writing command, I want a block-only change to cost the index almost nothing, so that a wellness backfill does not trigger a full recomputation.

#### Acceptance Criteria
1. When a page changes only in its block, the analytics index shall refresh the page's document values and shall not recompute its computed values.
2. The block shall read nothing from the analytics index, and the analytics index's tables and schema version shall not change because of this feature.

### Requirement 11: Ownership Contract and Documentation
**Objective:** As an athlete and as the agent maintaining my wiki, I want the block and its refreshing written down where I already look, so that nothing on my pages changes unexpectedly.

#### Acceptance Criteria
1. The published ownership contract shall describe the block location: that fitdocs owns it, fills it from the wellness series, replaces its content whenever it differs from what the series gives, carries no user content in it, and that hand edits there are replaced.
2. The published ownership contract shall describe the morning-of pass among the operations that overwrite existing content, and shall state that a workout page's block is re-derivable from the archived wellness files and the settings, alongside the inputs that already re-derive the rest of the page.
3. The published ownership contract's version shall advance by one from its value at landing, with a statement of what changed.
4. The wellness documentation shall describe the block: what it shows, which day it shows, the windows of its figures, sources and Garmin attribution, the absence marker, when pages are refreshed, and that it states no verdict.
5. The packaged workouts skill shall describe the morning-of pass's report lines and state which of them need the athlete.
6. The release notes shall describe the block, the page-format version change with the action `fitdocs regen`, and the ownership-contract version change.

### Requirement 12: Offline, Deterministic and Confined
**Objective:** As an athlete, I want the block and its refresh to behave like the rest of fitdocs, so that they are safe to run unattended.

#### Acceptance Criteria
1. Rendering the block and running the morning-of pass shall make no network request and add no runtime dependency.
2. The block and the morning-of pass shall read no clock, so that the run date never enters a page.
3. The morning-of pass shall write only existing workout pages under `workouts/`, and shall create, rename or delete no file.
4. No personal wellness data shall be committed to the fitdocs repository; tests shall use synthetic series and pages.
