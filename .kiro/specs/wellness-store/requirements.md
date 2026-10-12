# Requirements Document

## Project Description (Input)
**Who has the problem.** An athlete who keeps a markdown wiki with fitdocs,
and every Phase 12 consumer that serves that athlete: the recovery page, the
morning-of block on workout pages, the resting- and max-HR derivation and the
analytics index. Each of them needs one answer to "what was this athlete's
resting HR, HRV and sleep on this day, and where did each number come from?".

**Current situation.** fitdocs sees only workouts. Daily wellness exists for
most athletes, but in different places and shapes: intervals.icu wellness
records (the aggregator for Garmin, COROS, Polar, Suunto, Oura, WHOOP, Zepp,
Huawei, and Apple Health through HealthFit), Garmin's "Export Your Data" JSON
files, and Apple Health's export. No wellness model, store or parser exists.
The inbox takes `.fit` files only; a `.json` or `.zip` dropped there is
silently ignored and stays forever. A Garmin monitoring or sleep `.fit`
dropped there becomes an `undated-` workout page. The analytics index has no
wellness table.

**What should change.** A wellness file the athlete drops into the inbox, or
that a connector delivers there, is recognized, its original bytes (or, for a
format that declares one, a canonical extract) are archived content-hashed in
a new fitdocs-owned `wellness-archive/`, it is parsed into per-day,
per-metric, source-attributed values, and every source's values are merged by
a configurable per-metric source precedence into one normalized daily series,
written as fitdocs-owned yearly files in a new `wellness/` location. The drain
reports what it added or changed. `regen` rebuilds the series from the archive
alone. A file fitdocs cannot use is reported and left alone, and a `.fit`
file whose header declares a type other than an activity gets no workout
page; a page that already lists one is kept and rebuilt by `fitdocs regen`.
`check` reports an
orphaned archive entry, a series out of date and a conflicting duplicate. A
`wellness_daily` table brings the series into the analytics index. This
feature ships the intervals.icu and Garmin-export formats and settles the
seams the other Phase 12 features plug into.

Source: `.kiro/specs/wellness-store/brief.md`; Phase 12 of
`.kiro/steering/roadmap.md`. Dependencies: none. Downstream: `wellness-pull`,
`apple-health-import`, `hr-derivation`, `recovery`, `workout-wellness`.

## Introduction

Wellness is what happens between workouts: resting heart rate, heart-rate
variability, sleep, weight and the like, one value per day. This feature
gives fitdocs one place to keep it and one way to read it.

Terms used below:
- The **data root** is the athlete's configured output directory. The
  **inbox** is the configured intake directory the drain (`fitdocs sync`
  without a source, and `fitdocs pull --sync`) reads.
- A **wellness file** is a file in a format fitdocs can read wellness from.
  A **wellness format** is one such file shape (for example "an intervals.icu
  wellness file" or "a Garmin export sleep file"). Each format belongs to one
  **source**: the service or export the values come from (`intervals-icu`,
  `garmin-export`).
- A **wellness day** is a local calendar date. A **metric** is one named
  wellness quantity with its unit in its name (for example `resting_hr_bpm`).
- A **value** is one number for one metric, one wellness day and one source.
  Its **origin** is the device platform that measured it, where the source
  says so (a relay such as intervals.icu may pass on Garmin's or Apple's
  measurements).
- The **wellness archive** is `wellness-archive/` in the data root: the kept
  form of every wellness file fitdocs has handled. An **archive entry** is one
  file in it.
- The **series** is the normalized daily wellness series: fitdocs-owned files
  in `wellness/` in the data root, one per calendar year, plus one file that
  records what the series was built from. Every value of every source is kept
  in it; for each day and metric, exactly one source's value is the day's
  **canonical value**.
- **Source precedence** is the ranked list of sources that decides which
  source's value is canonical when several sources have one.
- A **conflicting duplicate** is two archive entries of one source that give
  different values for the same day and metric, where nothing in them says
  which is newer.
- A **non-activity FIT file** is a `.fit` file whose own header declares a
  file type other than an activity (a monitoring, sleep or settings file, for
  example).

## Boundary Context

- **In scope**: recognition of wellness files in the inbox and the reported
  "unrecognized" channel; the wellness archive and its ownership-contract
  entry; the per-day, per-metric, source-attributed model, its metric
  vocabulary and the day-boundary rule for nights; per-metric source
  precedence and its configuration; the yearly series files and the way
  every consumer reads them; the rebuild on the drain and on `regen`; the
  `check` findings; the intervals.icu wellness format and the four Garmin
  export formats (daily summaries, sleep, VO2max, body metrics), each as an
  individual file; the rules that let a later format archive a canonical
  extract and supersede an earlier export; the non-activity-FIT guard; the
  `wellness_daily` analytics-index table; the documentation, the packaged
  skill's routine and the release notes; the published-rule changes this
  feature makes to the inbox, the ownership contract, fit-ingest's file
  identity and the analytics index.
- **Out of scope**: the Apple Health parser and its extract
  (`apple-health-import`); pulling wellness from intervals.icu
  (`wellness-pull`); parsing Garmin wellness FIT messages (monitoring, sleep,
  HRV status); importing a whole Garmin export zip; baselines, scores,
  verdicts and any page or chart of wellness (`recovery`,
  `workout-wellness`); deriving resting or max HR benchmarks
  (`hr-derivation`); a generic wellness CSV format; nutrition, blood
  pressure, glucose and menstrual data; intervals.icu's own computed fields
  (fitness, fatigue, ramp rate, eFTP); any network access.
- **Adjacent expectations**: `wellness-pull` delivers intervals.icu wellness
  as a file in the inbox in the shape this feature's intervals.icu format
  reads, and removes its own deliveries once they are archived.
  `apple-health-import` adds the Apple Health format through the same
  recognition, archive and merge rules this feature defines. `recovery`,
  `workout-wellness` and `hr-derivation` read the series through the reading
  interface this feature provides and never re-read the archive or
  re-implement the merge. The folder connector keeps listing `.fit` files
  only.

## Requirements

### Requirement 1: Recognizing Wellness Files in the Inbox
**Objective:** As an athlete, I want a wellness file I drop into the inbox to
be recognized by what it contains, so that I can hand fitdocs my exports
without renaming or sorting them.

#### Acceptance Criteria
1. When the inbox is drained, fitdocs shall consider as a wellness candidate every regular file in the inbox whose extension (compared case-insensitively) is one a supported wellness format reads, applying the same hidden-path, default-junk and configured ignore rules it applies to `.fit` files.
2. fitdocs shall apply the existing stability check to wellness candidates, together with the `.fit` candidates of the same drain and within the same single settle interval, and shall defer an unstable or unreadable wellness candidate exactly as it defers a `.fit` file.
3. fitdocs shall recognize a wellness candidate by its content, and, where a format defines a file-name pattern, by that pattern together with its content; it shall never recognize a candidate by its location in the inbox.
4. If no supported wellness format recognizes a wellness candidate, then fitdocs shall leave the file untouched in the inbox and report it in an "unrecognized" channel of the drain report, naming the file and the reason.
5. If more than one wellness format recognizes the same candidate, then fitdocs shall leave the file untouched, report it as unrecognized, and name every format that claimed it.
6. fitdocs shall continue to ignore, without reporting, an inbox file whose extension is neither `.fit` nor one a supported wellness format reads.
7. The drain shall report a wellness candidate in exactly one of: archived, already archived, failed, deferred, quarantined or unrecognized.
8. The folder connector shall continue to list only `.fit` files from its source directory.
9. fitdocs shall recognize wellness files only in the inbox drain; `fitdocs sync` given an explicit source directory shall continue to process `.fit` files only.

### Requirement 2: Archiving a Wellness File
**Objective:** As an athlete, I want every wellness file fitdocs handles kept
in my data root, so that the series can always be rebuilt and nothing depends
on the original staying in the inbox.

#### Acceptance Criteria
1. fitdocs shall treat `wellness-archive/` in the data root as an owned location and shall list it in its published ownership contract.
2. When a recognized wellness candidate is handled, fitdocs shall keep it as one archive entry named by the SHA-256 of the candidate's original bytes and grouped by its format, so that a file and a byte-identical copy of it are one entry.
3. Where a format keeps original bytes, fitdocs shall archive the candidate's bytes unchanged; where a format declares a canonical extract, fitdocs shall archive the extract in place of the original and the entry shall still be named by the original's SHA-256.
4. fitdocs shall never modify an archive entry once written, and shall write an entry only after the candidate has been read in full and parsed successfully, so that an entry's presence means it was handled.
5. When a recognized candidate's original SHA-256 already names an archive entry of its format, fitdocs shall report it as already archived and shall not read it further.
6. If a recognized candidate cannot be parsed, then fitdocs shall archive nothing for it, report it as failed with the reason, and record it in the inbox quarantine record so that later drains report it as quarantined without parsing it again, exactly as for a `.fit` file whose bytes cannot be decoded.
7. When the drain is run with `--retry-quarantined`, fitdocs shall re-attempt a quarantined wellness candidate exactly as it re-attempts a quarantined `.fit` file.
8. If a candidate's bytes change between being hashed and being archived, then fitdocs shall archive nothing for it and defer it with a reason that says it changed during the run, also when the change made its content unreadable or invalid, and shall not record it in the quarantine record.
9. Where the configured disposition moves processed files, fitdocs shall move a wellness candidate out of the inbox exactly when its archive entry exists and it did not fail in this drain, and shall otherwise leave it in place, as it does for `.fit` files.
10. fitdocs shall never delete a wellness file from the inbox.

### Requirement 3: Reading Large Wellness Files
**Objective:** As an athlete with a multi-gigabyte export, I want the drain to
handle it without loading it into memory, so that importing it does not
exhaust my machine.

#### Acceptance Criteria
1. fitdocs shall hash, recognize, copy and parse a wellness candidate by reading it in bounded chunks, never by reading the whole file into memory at once.
2. fitdocs shall decide recognition by reading a bounded part of the candidate (a prefix of its bytes, a zip file's member list, or, for a format that reads JSON, the parsed JSON of a file no larger than a stated size limit), never the whole of a larger file.
3. While a wellness candidate is being archived, fitdocs shall hold no more than a bounded amount of its content in memory, independent of the file's size, apart from what the format's own parsed result requires.
4. Where a format reports progress while it reads a large candidate, the drain shall show that progress to the athlete.

### Requirement 4: The Non-Activity FIT Guard
**Objective:** As an athlete, I want a Garmin monitoring or sleep `.fit` file
to stay out of my workouts, so that no meaningless `undated-` workout page
appears.

#### Acceptance Criteria
1. fitdocs shall read the file type a `.fit` file's own header declares, and shall record it as absent when the header does not declare one.
2. When a sync, drain or `regen` run would process a `.fit` file that declares a file type other than an activity (a new file, an archived file no workout page lists, or a file re-processed under `--force`), it shall write no workout page from it, shall not archive it when it is not already archived, and shall report it as skipped with a warning naming the file and its declared type.
3. When such a file sits in the inbox, the drain shall leave it untouched in the inbox under every disposition.
4. fitdocs shall continue to process as an activity a `.fit` file that declares the activity type or declares no file type.
5. fitdocs shall never delete or rename a workout page because a file it lists declares a non-activity type, and `fitdocs regen` shall continue to rebuild such a page from the files it lists.
6. The guard shall not count a non-activity FIT file as a failure and shall not record it in the quarantine record.

### Requirement 5: The Wellness Metrics
**Objective:** As a consumer of the series, I want one fixed vocabulary of
metrics with their units in their names, so that a value means the same thing
wherever I read it.

#### Acceptance Criteria
1. fitdocs shall name every metric in lowercase snake case ending in its unit token where the metric has a unit, and shall use the project's single unit vocabulary for those tokens.
2. fitdocs shall provide at least these metrics: resting heart rate, lowest and highest heart rate of the day, HRV as SDNN, HRV as rMSSD, total sleep, deep, light, REM and awake time in sleep, average heart rate in sleep, respiration rate, blood-oxygen saturation, body weight, VO2max (unspecified, running and cycling), steps, stress level, the day's highest and lowest body battery, and the subjective ratings for fatigue, mood, motivation, soreness, stress, injury and hydration.
3. fitdocs shall keep HRV measured as SDNN and HRV measured as rMSSD as two separate metrics, and shall never convert a value of one into the other or place it under the other's name.
4. fitdocs shall store a subjective rating as the number the source recorded, on the source's own scale, without reinterpreting it.
5. fitdocs shall give each metric one short display label, distinct from every other metric's, and shall document, for each metric, its label, its unit and each supported source's definition of it.
6. fitdocs shall never import a value another tool computed from its own training model, including intervals.icu's fitness, fatigue, ramp rate and estimated FTP fields.

### Requirement 6: Absent Values
**Objective:** As a consumer of the series, I want a missing measurement to be
missing, so that I never compute a baseline from a placeholder.

#### Acceptance Criteria
1. When a source does not record a metric for a day, the series shall hold no value for that source, metric and day, and the reading interface shall return no value (`None`) for it.
2. When a source records a value the format documents as a placeholder for "not measured" (for example Garmin's `-1` and `-2` stress values, or a zero resting heart rate), fitdocs shall treat it as absent.
3. fitdocs shall treat as absent a zero for every metric whose zero cannot be a real measurement, and shall document which metrics those are.
4. If a source records a value outside the metric's documented valid range, then fitdocs shall treat it as absent.
5. fitdocs shall never write a zero, a default or a carried-forward value into the series for a value no source recorded.

### Requirement 7: The Day-Boundary Rule
**Objective:** As a consumer that shows the night before a workout, I want one
rule for which date a night belongs to, so that every page, baseline and query
agrees.

#### Acceptance Criteria
1. fitdocs shall assign every value to exactly one wellness day, a local calendar date.
2. fitdocs shall assign sleep and every value measured over a night to the local date on which that sleep ended (the wake date).
3. Where a format reports a sleep period by its local end time rather than by a date, fitdocs shall assign it to day D when its end falls at or after 18:00 local time on the day before D and before 18:00 local time on D.
4. Where a source already reports a value under a calendar date, fitdocs shall keep the source's date, and shall document for each supported source that its dates for nights are wake dates.
5. fitdocs shall determine local time from the UTC offset recorded with the source's timestamp and shall never use the timezone of the machine fitdocs runs on to assign a wellness day.
6. fitdocs shall publish the rule in one place in its documentation, stating that the night before a workout on date D is the sleep of wellness day D.

### Requirement 8: Source Attribution
**Objective:** As an athlete, I want to know where every number came from, so
that I can compare like with like and credit the platform that measured it.

#### Acceptance Criteria
1. The series shall record, with every value, the source it came from and, where the source says so, the origin that measured it.
2. fitdocs shall keep every source's value for a day and metric in the series, including values that are not canonical, so that a consumer can follow one source alone.
3. When the intervals.icu wellness file names the upstream platform for a field, fitdocs shall record that platform as the origin of the field's values; otherwise the origin of an intervals.icu value shall be absent.
4. fitdocs shall record `garmin` as the origin of every value from a Garmin export file.

### Requirement 9: Overlapping Values Within One Source
**Objective:** As an athlete who exports or pulls more than once, I want a
newer record of a day to replace an older one from the same source, so that
corrections and late arrivals win without double counting.

#### Acceptance Criteria
1. When two archive entries of one source both describe the same day and metric, fitdocs shall keep the value from the record the source marks as most recently updated, where the format provides such a mark.
2. When the most recent record of a day from a source covers a metric but holds no value for it, fitdocs shall treat that source's value for the metric and day as absent, even if an older record held one.
3. Where a format declares that a later file of it replaces earlier ones as a whole, fitdocs shall build that format's values from its latest archive entry alone, by the order the format defines.
4. If two records of one source give different values for the same day and metric and nothing marks one as newer, then fitdocs shall keep one of them by a fixed rule that depends only on the archive's contents, record the conflicting duplicate, and report it through `check`.
5. When two records of one source give the same value for the same day and metric, fitdocs shall keep that value and record no conflict.

### Requirement 10: Source Precedence
**Objective:** As an athlete with overlapping sources, I want a predictable
choice of which source's number is the day's number, and I want to change it,
so that the series reflects the device I trust.

#### Acceptance Criteria
1. For each day and metric that at least one source has a value for, the series shall mark exactly one source's value as canonical: the value of the highest-ranked source that has one.
2. By default, fitdocs shall rank a device platform's own export above a phone health store, and a phone health store above a third-party aggregator that relays other platforms, and shall order sources of the same kind by their identifier.
3. Where the `[wellness]` table of `fitdocs.toml` sets `precedence` to a list of source identifiers, fitdocs shall rank those sources first, in that order, for every metric, followed by every other source in the default order.
4. Where the `[wellness.metric_precedence]` table sets a list of source identifiers for a metric, fitdocs shall use that list in place of `precedence` for that metric, followed by every other source in the default order.
5. If the `[wellness]` table names an unknown source or metric, repeats a source in one list, or has a value of the wrong type, then fitdocs shall refuse to run the drain or `regen`, writing nothing, with a configuration error that names the settings file and the offending key.
6. When the configured precedence changes, the next drain or `regen` shall rebuild the series under the new precedence.

### Requirement 11: The Series Files
**Objective:** As an athlete and as every consumer, I want the series as plain
files in my wiki that any tool can read, so that wellness outlives fitdocs and
diffs cleanly in git.

#### Acceptance Criteria
1. fitdocs shall treat `wellness/` in the data root as an owned location, list it in its published ownership contract, and keep in it one series file per calendar year that has at least one value, plus one file recording what the series was built from.
2. fitdocs shall write the series in a plain-text tabular format that common spreadsheet and data tools read without fitdocs, with one line per value giving the wellness day, metric, source, origin, value and whether it is canonical.
3. fitdocs shall order the lines of a series file by day, then metric, then source, and shall format every value deterministically, so that the same archive and settings always produce byte-identical files.
4. The series files shall contain no run date, run time, tool version or machine-specific path.
5. fitdocs shall write each series file atomically, shall leave a file whose content would not change untouched, and shall remove a year's file only when that year no longer has any value.
6. If a series location is occupied by a symlink, a directory, or a file fitdocs did not write, then fitdocs shall leave it untouched, write no part of the series in that run, and report the occupied path.
7. fitdocs shall place a generated `AGENTS.md` in `wellness/` and in `wellness-archive/` stating who owns their contents, that the series is rebuilt from the archive, that hand edits to the series are overwritten, and that archive entries are never modified by fitdocs.
8. fitdocs shall provide one reading interface for the series that returns, for a day, a metric and a source, the value, its origin and whether it is canonical, and that returns no value where none is held; every fitdocs feature that uses wellness shall read the series through it.

### Requirement 12: Rebuilding the Series
**Objective:** As an athlete, I want the series to follow the archive and my
settings automatically, and never to be left half-written, so that I can trust
what I read.

#### Acceptance Criteria
1. The series shall be a function of the wellness archive, the supported formats' parsing rules and the `[wellness]` settings alone.
2. When the drain archives a new wellness entry, or finds that the series does not reflect the current archive and settings, it shall rebuild the series before it renders workout pages.
3. When `fitdocs regen` runs, it shall rebuild the series from the wellness archive before it regenerates workout documents.
4. If an archive entry cannot be read during a rebuild (for example a cloud-evicted file), then fitdocs shall leave the existing series untouched, name every entry it could not read, and report the rebuild as deferred without failing the run.
5. If an archive entry cannot be parsed during a rebuild, then fitdocs shall leave the existing series untouched, name the entry and the reason, and fail the run.
6. If an existing series file cannot be read, then fitdocs shall leave the series untouched and report the rebuild as deferred.
7. The series' record of what it was built from shall list every archive entry the series reflects and every entry it left out because a later entry of the same format superseded it.
8. When `fitdocs sync` is given an explicit source directory, it shall neither archive wellness nor rebuild the series.

### Requirement 13: Reporting Wellness in the Drain and in `regen`
**Objective:** As an athlete or agent reading the drain report, I want to see
what wellness arrived and what changed, so that I know the drop worked.

#### Acceptance Criteria
1. The drain report shall show, in rows that are always present, the counts of unrecognized files, wellness files archived, wellness files already archived and wellness files that failed, and shall list each unrecognized or failed file with its reason.
2. When the series is rebuilt, the drain and `regen` reports shall state the series files written and removed and the number of values added, changed and removed, and the number of days whose canonical value changed.
3. When a rebuild is deferred, blocked by an occupied location, or fails, the drain and `regen` reports shall say so and name the entries or paths involved.
4. When nothing about wellness changed in a run, the reports shall not print a series summary.
5. A wellness file that failed to parse, or an archive entry that failed to parse during a rebuild, shall make the run exit with the failure status; an unrecognized, deferred, already archived or quarantined wellness file, a deferred or blocked rebuild, and a conflicting duplicate shall not.
6. A second drain with no new or changed inbox file and unchanged settings shall archive nothing, rewrite no series file and report no series change.

### Requirement 14: `check` Findings
**Objective:** As an athlete or agent, I want `fitdocs check` to tell me when
the wellness archive or series needs attention, so that problems surface
without running a drain.

#### Acceptance Criteria
1. `fitdocs check` shall report an orphaned archive entry for each file in `wellness-archive/` that no supported format reads, naming it and stating that fitdocs never reads it.
2. `fitdocs check` shall report the series as out of date when it does not reflect the current wellness archive and `[wellness]` settings, when a series file it recorded is missing or differs from what fitdocs wrote, or when wellness archive entries exist and no series has been written, with the remedy to run `fitdocs sync` or `fitdocs regen`.
3. `fitdocs check` shall report each conflicting duplicate recorded at the last rebuild, naming the day, the metric, the source, the archive entries involved and the value kept, with the remedy to remove the wrong entry from the archive and from the inbox and run `fitdocs regen`.
4. `fitdocs check` shall report a series location occupied by something fitdocs did not write.
5. `fitdocs check` shall remain read-only and offline: it shall list the wellness archive, read the series files and settings, and open no archive entry.
6. `fitdocs check` shall report the missing, stale or foreign `AGENTS.md` of `wellness/` and `wellness-archive/` as it does for the other declared directories.

### Requirement 15: The intervals.icu Wellness Format
**Objective:** As an athlete whose wellness reaches intervals.icu, I want the
records it returns, whether pulled by fitdocs or saved by hand, read into the
series, so that months of wellness arrive with one file.

#### Acceptance Criteria
1. fitdocs shall recognize as an intervals.icu wellness file a JSON file holding the list of day records the intervals.icu wellness endpoint returns.
2. fitdocs shall recognize as an intervals.icu wellness file a JSON file in the fitdocs delivery form: an object that names the fitdocs intervals.icu wellness format and its version, holds the day records under a records key, and may map intervals.icu field names to the platform that supplies them.
3. If a file in the fitdocs delivery form names a version this fitdocs does not read, then fitdocs shall report it as unrecognized, stating that a newer fitdocs wrote it.
4. fitdocs shall read each record's date from its `id` and its update time from its `updated` field, and shall map resting HR, HRV as rMSSD, HRV as SDNN, sleep time, average sleeping HR, respiration, SpO2, steps, VO2max, weight and the seven subjective ratings onto their metrics, converting no unit.
5. fitdocs shall ignore every other field of an intervals.icu record, including its fitness, fatigue, ramp-rate, load and sport-information fields.
6. fitdocs shall archive an intervals.icu wellness file as its original bytes.
7. fitdocs shall document the delivery form precisely enough that the intervals.icu wellness pull can produce a file this format reads.

### Requirement 16: The Garmin Export Formats
**Objective:** As an athlete with years of Garmin history, I want the wellness
files from Garmin's "Export Your Data" read into the series, so that the
history I already own fills the series without any login.

#### Acceptance Criteria
1. fitdocs shall recognize, each as an individual JSON file, a Garmin export daily-summary file, sleep file, VO2max file and body-metrics file, by their content, and, for a file that holds no records, by Garmin's file name for that kind.
2. When fitdocs parses a daily-summary file, it shall read the day's own resting heart rate, its lowest and highest heart rate, its total steps, its average all-day stress level, its average SpO2 and its highest and lowest body battery, and shall not read Garmin's seven-day average resting heart rate as the day's resting heart rate.
3. When fitdocs parses a sleep file, it shall read each night's deep, light, REM and awake time, its total sleep as the sum of deep, light and REM time, and its average respiration, under the night's calendar date.
4. When fitdocs parses a VO2max file, it shall read running VO2max and cycling VO2max as separate metrics, keep the most recently updated record of a day and sport, and import no VO2max for any other sport.
5. When fitdocs parses a body-metrics file, it shall read each recorded body weight, converted from grams to kilograms, keeping the most recent measurement of a day.
6. fitdocs shall treat Garmin's negative stress values, a zero stress average, a zero step count, a zero heart rate and a night whose sleep stages sum to zero as absent.
7. fitdocs shall archive a Garmin export file as its original bytes.
8. fitdocs shall not import a whole Garmin export zip and shall not read wellness messages from Garmin `.fit` files.

### Requirement 17: Formats Added Later
**Objective:** As the maintainer adding the Apple Health import and future
formats, I want one set of rules every format follows, so that a new format
plugs in without changing how the archive, merge or series work.

#### Acceptance Criteria
1. Where a format is added, fitdocs shall recognize, archive, parse, merge and report its files through the same rules as the formats this feature ships, with no change to the archive layout, the series files or the reading interface.
2. Where a format declares a canonical extract, fitdocs shall build the extract by streaming the original, confirm afterwards that the original still hashes to the SHA-256 that names the entry, and archive the extract only after it parses successfully.
3. Where a format declares that its latest entry supersedes earlier ones, fitdocs shall order its entries by the format's own rule, using the entry's name only to break a tie, and shall read a superseded entry only as far as needed to order it, so that damage beyond that point in a superseded entry never fails a rebuild.
4. Where a format's parsing rules change in a way that changes the values it produces, the next drain shall treat the series as out of date and rebuild it.
5. When a format adds a metric to the vocabulary, the series files and the analytics-index table shall accept it without a change to their structure.

### Requirement 18: The Analytics-Index Table
**Objective:** As an athlete or agent asking statistical questions, I want the
series in the analytics index, so that wellness can be queried beside
training.

#### Acceptance Criteria
1. The analytics index shall provide a `wellness_daily` table with one row per series value: its wellness day, metric, source, origin, value, unit token and whether it is canonical.
2. The `wellness_daily` table shall equal the series files as of the last index refresh, and shall be refreshed when a series file changes.
3. If the series cannot be read during an index refresh, then the index shall keep the table's previous rows and report the problem without failing the command.
4. The index schema version shall advance by one from its value at landing, and the published schema reference in `docs/analytics.md` shall list the new table.
5. Workout, history and block documents shall continue never to read the analytics index.

### Requirement 19: Ownership Contract and Documentation
**Objective:** As an athlete and as the agent maintaining my wiki, I want the
new locations and behavior written down where I already look, so that nothing
about wellness is a surprise.

#### Acceptance Criteria
1. The published ownership contract shall describe `wellness-archive/` and `wellness/`, what fitdocs writes there and what it never does, and its version shall advance by one from its value at landing, with a statement of what changed.
2. fitdocs shall provide a wellness documentation page covering how to get wellness files into the inbox, the supported formats and what each imports, the metrics and their per-source definitions, the day-boundary rule, absent values, source precedence and its settings, the series files and how to read them, the archive, the `check` findings and the analytics table, and shall link it from the documentation index and the package metadata.
3. The inbox documentation shall describe wellness candidates, the unrecognized channel and the non-activity-FIT guard.
4. The configuration documentation shall describe the `[wellness]` table.
5. The packaged workouts skill shall describe the new drain report rows and `check` findings and tell the agent which of them need the athlete.
6. The release notes shall describe the new capability, the new owned locations and the ownership-contract and index schema version changes.

### Requirement 20: Offline, Deterministic and Dependency-Free
**Objective:** As an athlete, I want wellness handling to behave like the rest
of fitdocs, so that it is safe to run unattended.

#### Acceptance Criteria
1. Recognizing, archiving, parsing, merging, rebuilding, checking and indexing wellness shall make no network request.
2. Wellness handling shall add no runtime dependency beyond the standard library and the packages fitdocs already requires.
3. The same wellness archive and `[wellness]` settings shall always produce byte-identical series files, on any machine and in any timezone.
4. Every write wellness handling makes shall be confined to `wellness-archive/`, `wellness/`, the inbox quarantine record and, under the move disposition, the processed-files destination.
5. No personal wellness data shall be committed to the fitdocs repository; tests shall use synthetic files shaped like the real formats.
