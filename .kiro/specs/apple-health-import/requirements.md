# Requirements Document

## Project Description (Input)
**Who has the problem.** An athlete who trains with an Apple Watch and keeps a
markdown wiki with fitdocs. For that athlete Apple Health is the canonical
wellness store and the only place that holds all of it: intervals.icu receives
a subset only from the day a bridge app's health sync was switched on, and
Apple Health alone carries sleep stages. For the maintainer, Apple Health
alone holds 2023-03 → 2025-06, about 27 months between the Garmin export and
the intervals.icu relay.

**Current situation.** Nothing in fitdocs reads Apple Health. Apple offers no
cloud API; the Health app's "Export All Health Data" writes `export.zip`,
holding `apple_health_export/export.xml` (one to more than five gigabytes of
XML) and more. `wellness-store` (this phase) provides the format registry,
the archive, the model, the merge and the series, but no Apple Health format.
Archiving the whole export was ruled out at viability: GitHub refuses files
over 100 MiB, every export is the whole history so content hashing never
de-duplicates exports, and an evicted iCloud file is not materialised on read.

**What should change.** The athlete drops `export.zip`, or a bare
`export.xml`, into the inbox. The drain streams it once and archives a small,
deterministic, compressed canonical extract in its place: only the wellness
record types, as raw records, carrying the original's SHA-256, byte size and
export date. The extract is parsed into per-day values attributed to Apple
Health, with Apple's per-record writing source used to de-duplicate the
iPhone, the Apple Watch and other apps, and each type reduced to one value
per day by a stated rule. A later export supersedes the earlier one. The
original export stays the athlete's to keep or delete; fitdocs never needs it
again.

Source: `.kiro/specs/apple-health-import/brief.md`; Phase 12 of
`.kiro/steering/roadmap.md`. Dependencies: `wellness-store`. Downstream:
`hr-derivation`, `recovery` and `workout-wellness`, all through the series.

## Introduction

This feature lets fitdocs import the athlete's Apple Health history from the
export the Health app writes, so that Apple's resting heart rate, heart-rate
variability, sleep, respiration, blood oxygen, VO2max, steps and weight join
the normalized wellness series every Phase 12 consumer reads.

Terms used below, in addition to those `wellness-store` defines (data root,
inbox, drain, wellness day, metric, value, origin, wellness archive, series,
canonical value, source precedence):
- An **export** is the file set the Health app's "Export All Health Data"
  writes: a zip file holding the **main export document** (`export.xml` in
  English) and, beside it, other files such as the clinical-document file,
  workout routes and electrocardiograms. An export may also be dropped as its
  bare main export document.
- The **export date** is the date and time the export states it was made.
- A **record** is one sample Apple Health holds: one record type (for example
  resting heart rate or sleep analysis), its value, its start and end times,
  and its **writing source**: the app or device that wrote it, as the export
  names it.
- The **extract** is the compact file fitdocs archives in place of an export.
- A **night** is the sleep that belongs to one wellness day under
  `wellness-store`'s day-boundary rule.

## Boundary Context

- **In scope**: recognizing an export (`.zip` or bare `.xml`) in the inbox;
  reading it as a stream with bounded memory; the three known export defects;
  all-or-nothing imports; the extract (content, determinism, provenance,
  compression, readability); supersession by a later export; the mapping of
  record types to metrics; source de-duplication; the per-type daily
  reduction, including sleep; day assignment through `wellness-store`'s rule;
  progress during an import; documented time and memory bounds; the
  documentation and release notes.
- **Out of scope**: the archive, merge, series files, reader, precedence and
  day-boundary rule themselves (`wellness-store`); any baseline, chart or page
  (`recovery`, `workout-wellness`); Apple workouts and routes (activities keep
  arriving as `.fit` files through HealthFit); heart rate, walking heart rate,
  wrist temperature, nutrition, clinical records, ECGs, audiograms and the iOS
  26 Sleep Score; Apple's rMSSD type introduced with iOS and watchOS 27 (a
  follow-on that will be a new metric, never a continuation of SDNN);
  third-party file exporters such as Health Auto Export; archiving the whole
  export; any network access.
- **Adjacent expectations**: `wellness-store` recognizes candidates through
  its format registry, hashes and settles them, keeps the inbox quarantine
  record and the disposition, commits an extract only after it parses, merges
  every source's values under the configured precedence and writes the series.
  This feature relies on those rules unchanged except where its design names
  an amendment. Consumers read Apple Health's values only through the series.

## Requirements

### Requirement 1: Recognizing an Apple Health Export
**Objective:** As an athlete with an Apple Watch, I want to drop the export the
Health app writes into my inbox as it is, so that importing my Apple Health
history needs no unzipping, renaming or sorting.

#### Acceptance Criteria
1. When the inbox is drained, fitdocs shall recognize as an Apple Health export a zip file whose list of contents names exactly one main export document, whatever the name of the zip file itself.
2. When the inbox is drained, fitdocs shall recognize as an Apple Health export an XML file whose opening bytes identify it as the Health app's main export document, whatever the file's name.
3. fitdocs shall decide whether a candidate is an Apple Health export from its name, its opening bytes and, for a zip file, its list of contents alone, without reading the rest of the file.
4. If a zip or XML file in the inbox is not an Apple Health export (for example a Garmin export zip, the Health app's clinical-document file, or an unrelated XML file), then fitdocs shall report it as unrecognized and leave it in place, as for any other unrecognized wellness candidate.
5. If a zip file's list of contents names more than one possible main export document, then fitdocs shall report it as unrecognized and leave it in place.
6. fitdocs shall document that a `.zip` or `.xml` file kept in the inbox that is not an Apple Health export is now reported as unrecognized, and how to silence it with the inbox ignore setting.

### Requirement 2: Importing a Large Export
**Objective:** As an athlete with a multi-gigabyte export, I want the import to
finish without exhausting my machine and to show that it is working, so that a
long import is neither a crash nor a mystery.

#### Acceptance Criteria
1. fitdocs shall read an export, zipped or bare, once from start to end as a stream, holding no more than a bounded amount of it in memory whatever the export's size.
2. fitdocs shall import an export whose main export document is larger than 4 GB, including one inside a zip file that uses the zip format's large-file extensions.
3. fitdocs shall never unpack an export to disk; the only file it writes while importing is the extract it archives.
4. While an export is being imported, the drain shall report progress as the share of the main export document read so far, at most once per whole percent.
5. fitdocs shall document the expected import time per gigabyte of main export document and the memory an import uses.
6. When an export whose bytes are already archived is drained again, fitdocs shall report it as already archived without importing it again.

### Requirement 3: Tolerating Known Export Defects
**Objective:** As an athlete whose export was written by an iOS version with
known export bugs, I want the import to succeed anyway, so that a defect Apple
introduced does not block my history.

#### Acceptance Criteria
1. If the export's document-type declaration is malformed (as in exports written by iOS 16), then fitdocs shall import the export, ignoring the declaration.
2. If an attribute value in the export contains a control character that XML does not allow (for example a vertical tab), then fitdocs shall import the export with that character removed from the value.
3. If a workout-statistics element in the export carries the same attribute twice (as in exports written by iOS 16.0), then fitdocs shall import the export, keeping the attribute's first occurrence.
4. fitdocs shall record in the extract how many corrections of each kind it made to the export, and shall document that removing a control character changes the text it was in.
5. If an export is malformed in any other way, then fitdocs shall fail the import with a reason that names the line of the main export document at which reading stopped.
6. fitdocs shall never modify the export file.

### Requirement 4: All-or-Nothing Import
**Objective:** As an athlete, I want an import either to succeed whole or to
change nothing, so that a partly read export never leaves partial values in my
series.

#### Acceptance Criteria
1. If any part of an export cannot be read or does not satisfy this feature's rules, then fitdocs shall archive nothing for the export, leave the series unchanged, and report the export as failed with the reason.
2. When an import fails, fitdocs shall record the export in the inbox quarantine record exactly as for any wellness file that cannot be parsed, so that later drains report it as quarantined without importing it again until a retry is requested.
3. If an export's bytes change while it is being imported, then fitdocs shall archive nothing for it and defer it to a later drain with a reason saying it changed during the run.
4. If an import is interrupted, then fitdocs shall leave no archive entry and no partial file of it in the wellness archive.

### Requirement 5: The Canonical Extract
**Objective:** As an athlete who keeps the wiki in git and in iCloud, I want
fitdocs to keep a small, faithful extract of my export instead of the export,
so that my archive stays small enough to push and the series can always be
rebuilt without the original.

#### Acceptance Criteria
1. When an export is imported, fitdocs shall archive, in place of the export, an extract holding every record of the record types this feature reads, with each record's type, writing source, writing source's version, device, unit, creation, start and end times, value and metadata entries as the export states them, apart from the corrections of Requirement 3 and the removal of the device description's memory address.
2. The extract shall state the SHA-256 and the byte size of the original export and the export date the export states.
3. fitdocs shall write byte-identical extract content for byte-identical exports, on any machine, in any timezone and on any run date.
4. The extract shall contain no run date, no file name or path of the export, and no machine-specific value.
5. fitdocs shall store the extract compressed.
6. The extract shall never contain the export's personal profile (date of birth, biological sex, blood type, skin type), workouts, workout routes, clinical records, electrocardiograms, audiograms, or a record type this feature does not read.
7. The extract shall be readable without fitdocs as compressed UTF-8 text with one record per line.
8. fitdocs shall derive Apple Health's contribution to the series from the extract alone, so that the original export is never read again once its extract is archived.
9. Where a later version of fitdocs changes the extract's layout, that version shall continue to read every extract layout an earlier version wrote.
10. fitdocs shall treat the original export in the inbox exactly as it treats any other handled wellness file (left in place, or moved under the move disposition) and shall never delete it.

### Requirement 6: A Later Export Supersedes an Earlier One
**Objective:** As an athlete who exports again months later, I want the newer
export to replace the older one, so that nothing is counted twice and Apple's
revisions win.

#### Acceptance Criteria
1. When the wellness archive holds extracts of more than one export, fitdocs shall build Apple Health's values from the extract whose export date is latest, and the series' record of what it was built from shall list the others as superseded.
2. When an export whose export date is earlier than an already archived one is imported, fitdocs shall archive its extract and keep building from the later export's extract.
3. When the same export is imported both as its zip file and as its bare main export document, fitdocs shall build from exactly one of the two extracts, chosen by a fixed rule that depends only on the archive's contents.
4. fitdocs shall keep superseded extracts in the wellness archive unchanged.
5. When the series is rebuilt, fitdocs shall read no more of a superseded extract than it needs to learn its export date.
6. fitdocs shall document that a later export replaces an earlier one entirely, including any day the later export no longer holds, and that every Apple Health export in the archive is taken to be the same athlete's.

### Requirement 7: What Is Imported
**Objective:** As a consumer of the series, I want each Apple Health measurement
on the metric that means the same thing, in the metric's unit, so that Apple's
values compare with the other sources' where they should and never where they
should not.

#### Acceptance Criteria
1. fitdocs shall import Apple Health's resting heart rate as `resting_hr_bpm`, heart-rate variability (SDNN) as `hrv_sdnn_ms`, respiratory rate as `respiration_brpm`, blood-oxygen saturation as `spo2_pct`, VO2max as `vo2max_ml_per_kg_min`, step count as `steps`, body mass as `weight_kg`, and sleep analysis as `sleep_s`, `sleep_deep_s`, `sleep_light_s`, `sleep_rem_s` and `sleep_awake_s`.
2. fitdocs shall attribute every imported value to the source `apple-health`, which by default ranks below a device platform's own export and above a third-party aggregator.
3. fitdocs shall record `apple` as the origin of every value an Apple device measured, and no origin for body weight.
4. fitdocs shall convert each record from the unit the export states into its metric's unit, including blood-oxygen fractions into percent and pounds, grams and stones into kilograms.
5. If a record of a type this feature reads states a unit fitdocs does not convert for that type, then fitdocs shall fail the import with a reason naming the record type and the unit.
6. fitdocs shall never import an Apple Health value as `hrv_rmssd_ms` or into any metric other than the one this requirement names for its type.
7. fitdocs shall import no other Apple Health record type, including heart rate, walking heart rate, wrist temperature, workouts, nutrition and the rMSSD type introduced with iOS and watchOS 27.
8. If a record of a type this feature reads has a value or a timestamp fitdocs cannot read, ends before it starts, or is a sleep record stating a sleep state fitdocs does not know, then fitdocs shall fail the import with a reason naming the record type, the problem and the record's start time as the export states it.

### Requirement 8: Source De-duplication
**Objective:** As an athlete whose iPhone, Apple Watch and other apps all write
into Apple Health, I want each day's value taken from the right writer and
never counted twice, so that the series reflects one measurement per day.

#### Acceptance Criteria
1. fitdocs shall take resting heart rate, heart-rate variability, respiratory rate, blood-oxygen saturation and VO2max only from records written by an Apple Watch.
2. fitdocs shall take steps and sleep only from records written by an Apple Watch or an iPhone.
3. fitdocs shall take body weight from every writing source, including other apps and values typed into the Health app.
4. fitdocs shall treat a record as written by an Apple Watch, or by an iPhone, when its writing source is one the export shows writing records on a device it describes as an Apple-made watch, or as an Apple-made iPhone, including that writing source's records that name no device.
5. fitdocs shall never add together the values of one day and metric that come from two different writing sources.
6. fitdocs shall choose among writing sources by the export's content alone, never by the order of records in the export.
7. fitdocs shall document these rules, including that values other apps write into Apple Health (other than body weight) are not imported from the export and reach the series only through those platforms' own sources.

### Requirement 9: Daily Values
**Objective:** As a consumer of the series, I want one value per day and metric
by a stated rule, so that a baseline built on it measures the same thing every
day.

#### Acceptance Criteria
1. fitdocs shall take as a day's resting heart rate the Apple Watch's final estimate for that day: of the day's estimates, the one that ends last, and of those the one written last.
2. fitdocs shall take as a day's heart-rate variability, respiratory rate and blood-oxygen saturation the mean of the Apple Watch's readings of that type taken while the athlete was asleep in that day's night, rounded to one decimal place.
3. If the Apple Watch recorded no sleep in a day's night, or took no reading of a type while the athlete was asleep in it, then fitdocs shall hold no value of that type for that day.
4. fitdocs shall take as a day's VO2max the Apple Watch's estimate for that day that ends last, and of those the one written last.
5. fitdocs shall take as a day's steps the largest single-source day total among the writing sources Requirement 8 allows, each total being the sum of that source's step records for the day.
6. fitdocs shall take as a day's body weight the measurement of that day that starts last, and of those the one written last, in kilograms rounded to two decimal places.
7. Where two records tie on every timing rule above, fitdocs shall choose by a fixed rule that depends only on the records' contents.
8. fitdocs shall document each daily rule together with the reason for it.

### Requirement 10: Sleep
**Objective:** As an athlete who sleeps with an Apple Watch, I want each night's
sleep and stages counted once and correctly, so that the series holds the
night as Apple measured it.

#### Acceptance Criteria
1. fitdocs shall import Apple's core sleep as light sleep, deep sleep as deep sleep, REM sleep as REM sleep and awake time as awake time, and total sleep as the sum of core, deep, REM and unspecified asleep time, never counting in-bed time or awake time toward total sleep.
2. When sleep records of one stage overlap, fitdocs shall count the overlapping time once.
3. When sleep records of different stages overlap, fitdocs shall count the overlapping time once, under the most specific stage: deep, then REM, then core, then awake, then unspecified asleep.
4. fitdocs shall take a night's sleep from the Apple Watch's records when an Apple Watch recorded asleep time that night, otherwise from the iPhone's, and shall never combine the two within one night.
5. When a night's sleep holds no deep, core or REM time (as Apple Watch recorded before watchOS 9), fitdocs shall import its total sleep only, and no deep, light, REM or awake time.
6. fitdocs shall treat the deprecated "asleep" sleep state of older exports as unspecified asleep time.
7. If a night's total sleep is zero, then fitdocs shall import no sleep value for that night.
8. fitdocs shall count asleep time the writer recorded outside the main sleep, such as a nap, toward the night of the wellness day it belongs to, and shall document this.

### Requirement 11: Assigning Values to Days
**Objective:** As a consumer that shows the night before a workout, I want
Apple Health's values on the same days every other source uses, so that every
page, baseline and query agrees.

#### Acceptance Criteria
1. fitdocs shall assign every Apple Health value to a wellness day only by `wellness-store`'s day-boundary rule, using the UTC offset the export records with each timestamp, and never the timezone of the machine fitdocs runs on.
2. fitdocs shall assign each sleep record to the wake date its end time gives under that rule.
3. fitdocs shall assign a heart-rate-variability, respiratory-rate or blood-oxygen reading to the wellness day of the night during which it was taken.
4. fitdocs shall assign resting heart rate, VO2max, steps and body weight to the local calendar date on which each record starts, in the record's own recorded offset.
5. fitdocs shall produce the same daily values from the same export on any machine and in any timezone.

### Requirement 12: Absent Values
**Objective:** As a consumer of the series, I want a missing Apple Health
measurement to be missing, so that no baseline is built on a placeholder.

#### Acceptance Criteria
1. When the export holds no record that qualifies for a metric on a day, fitdocs shall hold no Apple Health value for that metric and day, never a zero, a default or a carried-forward value.
2. fitdocs shall pass every daily value through `wellness-store`'s absent-value rule, so that a zero or out-of-range value is absent.

### Requirement 13: Documentation and Release Notes
**Objective:** As an athlete and as the agent maintaining my wiki, I want the
Apple Health import written down where I already look, so that I know how to
export, what arrives and what to expect.

#### Acceptance Criteria
1. The wellness documentation shall describe how to export from the Health app on an iPhone and where to put the resulting file.
2. The wellness documentation shall list each Apple Health record type fitdocs reads with the metric it becomes, its writing-source rule, its daily rule and its day assignment, and that list shall match what fitdocs imports.
3. The wellness documentation shall describe the extract (what it holds and never holds), the defect corrections, supersession and its consequences, the import time and memory bounds, what happens to the original export, and that workouts keep arriving as `.fit` files.
4. The release notes shall describe the Apple Health import and the inbox change that makes a `.zip` or `.xml` file a wellness candidate, with the action an athlete takes to silence a file that is not an export.

### Requirement 14: Offline, Dependency-Free and Private
**Objective:** As an athlete, I want the Apple Health import to behave like the
rest of fitdocs, so that it is safe to run unattended on my private data.

#### Acceptance Criteria
1. Recognizing, importing and parsing an Apple Health export, and rebuilding from its extract, shall make no network request.
2. The Apple Health import shall add no runtime dependency beyond the standard library and the packages fitdocs already requires.
3. Every write the Apple Health import makes shall be confined to the wellness archive, the series, the inbox quarantine record and, under the move disposition, the processed-files destination.
4. No Apple Health export, and no extract made from a real export, shall be committed to the fitdocs repository; tests shall use synthetic exports shaped like the real format.
