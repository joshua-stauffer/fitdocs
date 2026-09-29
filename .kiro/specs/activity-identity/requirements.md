# Requirements Document

## Project Description (Input)
One training session often exists as several `.fit` files: the device
original (a Garmin Edge ride, a Stryd run file), a phone-side re-export
(HealthFit's copy of what Apple Health received), a partner-API copy
(intervals.icu's file for a Garmin-synced ride), and a hand export from Garmin
Connect, whose bytes Connect re-encodes. fitdocs recognizes a file as belonging
to an existing page only by exact bytes or by HealthFit's session UUID, so any
other file of the same session becomes a second page. On 2026-09-12 this
blocked 761 Garmin originals from replacing their degraded HealthFit copies;
the only way through was a script that hand-edited the managed `sources` key,
then renamed 243 pages and deleted 287 orphaned chart assets by hand. Phase 8
of the roadmap makes a second file of a held session the common case:
connectors will deliver device originals and partner copies of activities the
athlete already has, and every one of them duplicates a page until the engine
knows it is the same activity.

This spec teaches the engine that knowledge. It reads the identity every file
declares (`file_id`: manufacturer, product, serial number, creation time);
classifies each file by what produced it; recognizes a file as the same
session as an existing page by a stated rule calibrated on measured pairs
(Stryd↔HealthFit: start identical to the second, distance equal to 0.01 m,
elapsed 8–9 s apart; Garmin↔HealthFit: start identical, distance within 5 m,
elapsed within about 1 s, timer time up to 400 s apart; 244 older HealthFit
re-exports shifted by whole hours; a 90 s / 300 m rule that matched two
different 10 k runs as the counter-example); refuses to guess when a file is
ambiguous; records each page's files with a role -- one base the page is
rendered from, and extras -- chosen by a configurable source precedence in
which a device original outranks a partner-API or phone-side copy; re-renders
and renames a page cleanly when its base changes, keeping its session UUID;
and reports ambiguous and orphaned sources through `fitdocs check`. It lands
the fit-ingest update for the `file_id` fields and the source-roles part of
the wiki-contract's Amendment 4, and closes the promoted queue item
`2026-09-12-adopting-a-higher-fidelity-re-export-needs-a-hand-edit`.
Source: `.kiro/specs/activity-identity/brief.md`; Phase 8 of
`.kiro/steering/roadmap.md`.

## Introduction

Until now a workout page's identity has been exact: the page is found by the
content hash of a file it already lists, or by the session UUID a HealthFit
export records. Both are certain, and both fail for the case Phase 8 exists to
serve -- a second, independently encoded file of a session the athlete already
has. `activity-identity` adds a third way to recognize a session, and it is
deliberately narrow. Two files are the same session only when they record the
same sport and agree on their start to the second, on their elapsed time and,
where both record one, on their distance, within tolerances derived from the
measured pairs and stated with their source; or when both carry the same
device identity and start in the same second; or, for a phone-side copy that
an older exporter shifted by whole hours, when the shift is a whole number of
hours and elapsed time and distance agree tightly. Timer time is never a key.

When the evidence is not unique, fitdocs does not choose. A file that matches
two pages, or two files that each match one page but not each other, are
archived, written into no page, reported by name on every run that meets them
and by `fitdocs check`, and left for the athlete to resolve. The assignment
of files to pages is a function of the files and the pages, never of the
order the files arrived in, and nothing already on a page is ever merged with
another page or taken back off it.

A page now records every file it holds, in one canonical order with its base
last, so that every existing reader of "the current source" keeps working
unchanged; it records the base file's own identity so that later files can be
matched without re-reading the archive; and it keeps the session UUID of a
phone-side copy even when a device original becomes its base. When a better
file arrives, the page is re-rendered from it with the athlete's regions
carried, renamed to the name the new base computes, and its previous chart
assets removed -- in an order a crash cannot turn into two pages or orphaned
files. Composing channels from the extras is not this spec's: until
`channel-merge` lands, a page renders from its base alone.

## Boundary Context

- **In scope**: the file-identity values decoded from `file_id` and the count
  of messages the FIT profile does not define; the closed vocabulary of source
  kinds and their derivation from a file's own bytes; the source-precedence
  setting, its default and its validation; the cross-source match rule, its
  tolerances, its evidence tiers and its handling of absent values; one-to-one
  assignment, grouping of a run's own files, and held (ambiguous) files; the
  roles a page records, the canonical order of its sources, the base file's
  identity on the page, and session-UUID retention; re-rendering, renaming and
  asset cleanup on a base change, including collision settling within a run;
  archive and regeneration semantics for every file of a page, including
  rebuilding roles from the archive; three new `fitdocs check` findings; the
  published ownership-contract and configuration documentation for all of the
  above; the fit-ingest, wiki-contract and workout-docs amendment records; and
  the closure of the promoted queue item.
- **Out of scope**: composing a page's channels from its extras, and recording
  which file each channel came from (`channel-merge`); fetching files from any
  service, the connector ledger and credentials (`connectors`,
  `intervals-connector`); resolving a numeric product code to a model name, and
  "Garmin <model>" attribution (`intervals-connector`); record-level developer
  fields and running-dynamics channels (`running-dynamics`); any network
  access; merging two sessions that are genuinely different recordings;
  merging two existing pages into one; an interactive "which page is this?"
  prompt; editing the athlete's plan sources or wiki links after a rename.
- **Adjacent expectations**: `fit-ingest` decodes the bytes and this spec
  extends its model; `wiki-contract` owns the published contract this spec
  amends; `inbox` drains candidates and disposes of a file only once its bytes
  are archived; the training-load pass, the performance pass and regeneration
  read "the current source" as the last entry of a page's source list and
  expect that to remain true; `plan-resolution` links logged pages by
  filename and is re-run after every `sync` and `regen`; `load-history` reads
  pages, not files; `channel-merge` consumes the roles this spec records and
  must not change a page's recorded base identity.

## Requirements

### Requirement 1: File identity at ingest
**Objective:** As the identity engine, I want every decoded activity to carry
the identity its own file declares, so that files of one recording can be
recognized and ranked without guessing.

#### Acceptance Criteria
1. When a `.fit` file carries a file-identity record, the fit-ingest library shall expose that record's manufacturer, product code, serial number and creation time on the decoded activity.
2. If a file carries no file-identity record, or its record omits a value, the fit-ingest library shall expose each missing value as absent, never as zero, an empty string or a default.
3. The fit-ingest library shall expose the manufacturer as the name the FIT profile gives it, or as the recorded number rendered as text when the profile names none, and shall expose the product as its recorded numeric code without resolving it to a model name.
4. The fit-ingest library shall expose the creation time as a timezone-aware UTC instant.
5. When a file carries more than one file-identity record, the fit-ingest library shall use the first.
6. The fit-ingest library shall expose, for every decoded file, the number of messages it carries whose message type the installed FIT profile does not define.
7. The fit-ingest library shall leave every activity value it exposed before this feature unchanged for the same input bytes.

### Requirement 2: Source kinds and source precedence
**Objective:** As an athlete with several files of one session, I want each
file classified by what produced it and ranked in an order I can configure, so
that each page renders from the best file I have.

#### Acceptance Criteria
1. The fitdocs CLI shall classify every file into exactly one source kind from the closed vocabulary `original`, `phone_copy`, `unknown`, derived from the file's own bytes and never from where or how the file arrived.
2. When a file's recorded manufacturer is `development` and its session records the `SESSION UUID` developer field HealthFit writes, the fitdocs CLI shall classify the file `phone_copy`.
3. When a file records a manufacturer other than `development`, the fitdocs CLI shall classify the file `original`.
4. When a file records no manufacturer, or records `development` without a recognized phone-side writer marker, the fitdocs CLI shall classify the file `unknown`.
5. Where the settings file configures no source precedence, the fitdocs CLI shall rank `original` above `phone_copy` above `unknown`.
6. Where the settings file configures a source precedence, the fitdocs CLI shall rank each file at the position of the first listed entry that names it -- an entry `original:<manufacturer>` naming the recorded manufacturer of an `original` file, otherwise the entry naming its kind -- and shall rank a file no listed entry names after every listed entry, in the default order of its kind.
7. If the source-precedence setting is not a list of strings, contains an entry that is neither a kind of the vocabulary nor `original:` followed by a non-empty manufacturer name other than `development`, or contains an entry twice, or if its table is not a table, the fitdocs CLI shall report a configuration error naming the settings file and the offending key and shall exit with the configuration-error status before writing anything.
8. The fitdocs CLI shall rank files of the same kind by the number of messages the FIT profile does not define, more first; then by creation time, later first, with an absent creation time last; then by content hash in ascending lexicographic order, so that the ranking of any set of files is a total order independent of arrival.

### Requirement 3: The cross-source match rule
**Objective:** As an athlete whose sessions arrive as several files, I want a
file recognized as the same session as an existing page by a stated,
calibrated rule, so that it joins that page instead of duplicating it.

#### Acceptance Criteria
1. The fitdocs CLI shall treat two files as possibly the same session only when both record the same sport.
2. When two files record the same sport, the same manufacturer, serial number and creation time, and session starts no more than 1 second apart, the fitdocs CLI shall treat them as the same session (device evidence).
3. When two files record the same sport, session starts no more than 1 second apart and elapsed times no more than 10 seconds apart, and, where both record a distance, distances no more than 5 metres apart, the fitdocs CLI shall treat them as the same session (strict evidence).
4. When at least one of two files is a `phone_copy`, both record the same sport, an elapsed time and a distance, their session starts are a whole number of hours apart between 1 and 36 hours inclusive to within 1 second, their elapsed times are no more than 5 seconds apart and their distances no more than 10 metres apart, the fitdocs CLI shall treat them as the same session (shifted evidence).
5. If two files' session starts are more than 1 second apart and are not a whole number of hours apart between 1 and 36 hours to within 1 second, the fitdocs CLI shall not treat them as the same session, however close their elapsed times and distances.
6. The fitdocs CLI shall never use a file's timer time as evidence of identity.
7. If a file records no session start, the fitdocs CLI shall recognize it as an existing page's only by exact content or by recorded session UUID.
8. If a file records no elapsed time, the fitdocs CLI shall recognize it as the same session as another file only by device evidence, besides exact content and recorded session UUID.
9. When an incoming file's content hash is among an existing page's sources, or its recorded session UUID equals the page's, the fitdocs CLI shall treat the file as that page's before any evidence of criteria 2–4 is considered, exactly as it does today.
10. The fitdocs CLI shall compare an incoming file against an existing page through the values the page records for its base file, its session UUID and its source list, without reading any archived file.
11. The fitdocs documentation shall state each tolerance of criteria 2–5 together with the measured pairs it was derived from.

### Requirement 4: One-to-one assignment and ambiguity
**Objective:** As an athlete, I want a file whose page is not certain reported
and left alone rather than merged by guesswork, so that no page ever holds a
file that is not the same session.

#### Acceptance Criteria
1. When Requirement 3 criterion 9 assigns a file to a page, the fitdocs CLI shall add the file to that page in every case, and criteria 2–6 below shall apply only to the run's other files.
2. The fitdocs CLI shall treat the run's other files that are the same session as each other, directly or through other such files, as one group, and shall say that a group matches a page when any file of the group is the same session as the page's base or as a file the run adds to that page under criterion 1.
3. When a group matches exactly one existing page and no other group of the same run matches that page, the fitdocs CLI shall add every file of the group to that page.
4. When a group matches no existing page, the fitdocs CLI shall render the group's files as one new page.
5. When a group matches two or more existing pages, the fitdocs CLI shall add none of its files to any page.
6. When two or more groups of one run each match the same existing page, the fitdocs CLI shall add none of those groups' files to that page.
7. While a file is held under criteria 5 or 6, the fitdocs CLI shall archive it, write no page for it, report a warning naming the archived file and every page it matched, and record the hold so the inspection command can report it without reading the file.
8. The fitdocs CLI shall assign a run's files to pages as a function of the set of files and the existing pages alone, so that the same inputs produce the same assignment whatever order the files are discovered or arrive in.
9. The fitdocs CLI shall never merge two existing pages, and shall never remove a file from a page it has already been added to.
10. When the regeneration command runs, the fitdocs CLI shall evaluate every held file and every archived file no page lists together, under criteria 1–7, against the regenerated pages, and shall keep the hold record equal to exactly the files that remain held.
11. When a file whose bytes are already archived is discovered again and forced re-processing is not requested, the fitdocs CLI shall skip it, whether it was added to a page or held.

### Requirement 5: Roles on the page
**Objective:** As an athlete or an agent reading a page, I want the page to
state which of its files it is rendered from and which it only holds, so that
provenance is visible and later files are matched against the right values.

#### Acceptance Criteria
1. The fitdocs CLI shall render every page from exactly one of its files, the base: the highest-ranked file of the page under Requirement 2.
2. The fitdocs CLI shall list every file of a page in the page's source list in ascending rank, so that the base is always the last entry and every other entry is an extra.
3. If an entry of a page's source list cannot be resolved to an archived file, the fitdocs CLI shall keep it in the list ahead of every resolved entry, in its existing relative order, and shall never choose it as the base.
4. The fitdocs CLI shall record on every page, as managed frontmatter keys, its base file's source kind, recorded elapsed time and recorded distance, and a digest of the base file's device identity that does not reveal its serial number, omitting each value the base does not record.
5. When a page's base records no session UUID and another file of the page does, the fitdocs CLI shall record the session UUID of the highest-ranked file of the page that carries one.
6. When a file joins a page and ranks below the page's base, the fitdocs CLI shall add it as an extra, keep the base, and keep the page's filename.
7. When the same set of files reaches a page in any order, across one run or several, the fitdocs CLI shall produce a byte-identical page under the same filename with the same chart assets, except where the filename computed for the page is held by a page of a different session, when the collision rule of Requirement 6 criterion 6 applies.
8. Until channel composition exists, the fitdocs CLI shall render a page from its base file's data alone and record its extras without drawing any value from them.

### Requirement 6: Base change, rename and asset cleanup
**Objective:** As an athlete, I want a page to follow its best file when a
better file arrives -- re-rendered, correctly named and without leftovers --
so that correcting a page never needs a hand edit.

#### Acceptance Criteria
1. When a file added to a page outranks the page's current base, the fitdocs CLI shall re-render the page from the new base, carrying every user-owned region and every user-owned frontmatter key verbatim.
2. When a page's base changes and the filename computed from the new base differs from the page's current filename, the fitdocs CLI shall rename the page to the computed filename.
3. When a page's base does not change, the fitdocs CLI shall keep the page's current filename, including a filename the user chose.
4. When the fitdocs CLI renames a page, it shall remove every chart asset the page's previous generated content linked that the new render does not write and no user-owned region of the page links, and shall remove no other file.
5. The fitdocs CLI shall report every rename as a warning naming the page's previous and new paths.
6. If the filename computed for a page is held by a different page, the fitdocs CLI shall apply the existing collision suffix; and after every file of a run has been processed, the fitdocs CLI shall rename each page the run wrote under a collision-suffixed filename to its unsuffixed filename when that filename is free, repeating until no such rename remains.
7. If a run is interrupted part-way through a rename, the fitdocs CLI shall leave the page at exactly one path, and the next run over the same inputs shall complete the rename and the asset cleanup.
8. When a matched page records a newer document-format version than the installed fitdocs produces, the fitdocs CLI shall leave it, its filename and its assets untouched, exactly as it does today.

### Requirement 7: Archive and regeneration semantics
**Objective:** As an athlete, I want every file of a session kept and every
page rebuildable from the archive alone, so that the role decisions are never
the only copy of anything.

#### Acceptance Criteria
1. The fitdocs CLI shall archive every file it processes, whether it becomes a page's base, an extra, or a held file, and shall write each archived copy after every other write for that file.
2. When the regeneration command runs, the fitdocs CLI shall rebuild each page's roles from the archived bytes of every file the page lists and the current source-precedence setting, and shall re-render, rename and clean up the page under Requirement 6 when its base changes.
3. When regeneration rebuilds a page from the same archived files, precedence setting, athlete profile and timezone, the fitdocs CLI shall produce the same page bytes, filename and assets as the run that last wrote it.
4. While a page lacks the base-identity keys this feature adds, the fitdocs CLI shall recognize it only by exact content or recorded session UUID, and shall report it as out of date through the existing document-format version, naming regeneration as the remedy.
5. The fitdocs CLI shall count a held file among the run's skipped files and shall never count it as a failure, so that the inbox disposes of it once its bytes are archived.
6. When none of a page's listed files resolves to an archived file, the fitdocs CLI shall report the page as a per-document failure during regeneration and leave it untouched, exactly as it does today for a page whose current source is missing.
7. When some but not all of a page's listed files resolve to archived files, the fitdocs CLI shall regenerate the page from the resolved files under Requirement 5 criterion 3.

### Requirement 8: Inspection findings
**Objective:** As a wiki maintainer or an automation acting for one, I want
`fitdocs check` to report every source whose page fitdocs could not decide and
every archived source no page holds, so that nothing is lost silently.

#### Acceptance Criteria
1. The inspection shall report each held file, naming its archived path, every page it matched and the evidence, with the action that resolves it.
2. The inspection shall report each archived source that no readable workout page lists and that is not held, as orphaned, naming regeneration as the action that renders it.
3. The inspection shall report each set of two or more workout pages that list a common archived source, record a common session UUID, or whose base-identity values match under Requirement 3, naming every page of the set and the evidence.
4. If the hold record cannot be read, the inspection shall report that as a finding naming the record and stating that regeneration rebuilds it, and shall continue.
5. The inspection shall report these findings without writing anything, without network access and without reading any `.fit` file.

### Requirement 9: The published contract and settings
**Objective:** As a person or agent maintaining a wiki fitdocs writes into, I
want the new guarantees and the new setting stated where the existing ones
are, so that I can rely on them instead of inferring them.

#### Acceptance Criteria
1. The ownership contract shall state that a page's source list names every archived file of the page, ranked with the base last, and shall define base and extra.
2. The ownership contract shall name the base-identity frontmatter keys among the managed keys, and the published managed-key set shall include them.
3. The ownership contract shall state that a base change may rename a page and remove the chart assets its previous render linked, that links to the previous filename are not updated by fitdocs, and that a page whose base does not change keeps its filename.
4. The ownership contract shall state that a page keeps a phone-side copy's session UUID when a file without one becomes its base.
5. The ownership contract shall state that an ambiguous file is archived and held rather than added to a page, where the hold is recorded, and how the athlete resolves it.
6. The published contract version and the document-format version shall each advance by one from the values current when this feature lands.
7. The configuration documentation shall document the source-precedence setting, its vocabulary, its default and its validation, and the compatibility statement shall list its settings table among the settings file's tables.
8. The documentation shall state that a data root holding pages written before this feature must be regenerated before files of already-held sessions are added from another source, so that those pages can be recognized.
