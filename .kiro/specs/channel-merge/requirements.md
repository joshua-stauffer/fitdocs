# Requirements Document

## Project Description (Input)
`activity-identity` gives each training session one page, rendered from one
base file, and records the session's other files as extras. The athlete brings
those extras in for the channels they carry and the base lacks. On a run, the
HealthFit copy is the base (it alone carries the session UUID, the full session
summaries and the heart-rate laps), and the Stryd file carries form power, air
power, leg spring stiffness, impact and the balance channels. On a ride, the
Garmin original is the base (power, altitude, temperature, GPS), and the
HealthFit copy carries the watch's heart rate when the ride was recorded without
a chest strap. Until a page is composed from all its files, those channels are
archived and read by nothing.

This spec composes one activity per page from its base and its extras: extras
donate only the channels the base lacks and the base wins every channel both
carry; an extra's samples are placed on the base's timeline by timestamp, with a
lag estimated per stretch between pauses (Stryd and HealthFit copies of the same
run drift between 0 and +1 s from one stretch to the next, measured on three
pairs on 2026-09-24); the page states which file each channel came from; and
summaries follow the composed channels. Source: `.kiro/specs/channel-merge/brief.md`;
Phase 8 of `.kiro/steering/roadmap.md`. Dependencies: `activity-identity`,
`running-dynamics`. It lands the channel part of wiki-contract Amendment 4.

## Introduction

A page's files are one session recorded or copied several times, and no single
file carries everything. The composition this spec adds is deliberately
conservative. It never averages, blends or corrects a value; it only decides,
channel by channel, which one file supplies that channel, and places that
file's values at the moments they were measured. The base always wins: a
channel the base records at even one sample is the base's, gaps included. An
extra supplies a channel only when the base records none of it, and then the
highest-ranked extra that records it supplies all of it.

Placing an extra's values needs care because the files' clocks do not agree
exactly. Every timestamp is a whole second and every Stryd timestamp exists in
the HealthFit copy, yet a plain timestamp join puts the Stryd values one second
early for 52–100% of samples: the content is shifted by a lag that changes at
each pause. The composition therefore splits the files at pauses, finds each
stretch's lag from a channel both files reproduce exactly (distance, else
power; never heart rate, which sits at a different lag again), and says so on
the page when no lag can be found.

Terms used below:
- **base** and **extra** are `activity-identity`'s roles; an extra's **rank** is
  its position in the page's source precedence, highest first.
- A **channel** is one per-sample series of the activity model (heart rate,
  power, cadence, speed, distance, altitude, temperature, each running-dynamics
  channel); **position** (latitude with longitude) is treated as one channel.
- A file **records** a channel when at least one of its samples holds a value
  for it.
- An **instant** is a sample's recorded time to the whole second. A **pause**
  is a gap of more than 1 second between consecutive samples of one file. A
  **stretch** is a run of an extra's samples uninterrupted by a pause of either
  file. A **lag** is the whole number of seconds by which a stretch's values
  are placed later on the base's timeline than their own instants.
- A channel is **donated** when the page takes it from an extra.

Two reconciliations with the discovery record are stated here because they
change what the athlete can observe. First, `activity-identity` hands this
spec every file of a page already decoded, so rendering a page reads no
archived file twice. Second, the training-load pass and the
benchmark-derivation pass do not read a page's body: each re-reads the page's
last listed archived file. For those passes to "read the composed page as they
read any page", as the discovery brief intends, they must compose the page's
files themselves by the same rule; Requirement 6 makes that so.

## Boundary Context

- **In scope**: composing a page's activity from its base and extras; splitting
  files at pauses, estimating each stretch's lag, the exact-timestamp fallback
  and the whole-hour shift; the donation rules, including the partial-coverage
  rule and the position unit; the Channel Sources section; summaries computed
  from the composed channels; the training-load and benchmark-derivation passes
  reading the composed activity; regeneration of composed pages; the
  document-format and contract version advances; the ownership-contract and
  release-note statements; the amendment records this changes in
  `wiki-contract`, `workout-docs`, `training-load` and `performance-benchmarks`;
  synthesized fixture pairs reproducing the measured shapes.
- **Out of scope**: deciding which files form a page and which is its base
  (`activity-identity`); channel definitions, decoding, and the placeholder and
  gate rules that make a file's values final (`running-dynamics`,
  `fit-ingest`); averaging, blending or correcting two values of one channel;
  composing files of different sessions; merging or re-deriving laps;
  showing an extra's devices, decode errors, session values or generic
  developer fields; any frontmatter key for channel provenance; rescoring a
  page whose load was already computed without the athlete asking; any network
  access.
- **Adjacent expectations**:
  - `activity-identity` supplies each page's roles (the base and its extras in
    rank order) and every file of the page decoded, and computes the page's
    filename, session identity and base-identity values from the base alone,
    before composition.
  - `running-dynamics` supplies the per-sample channel set; its values arrive
    final, with the placeholder-zero and gate rules already applied per file.
  - The training-load calculators, the data-quality flags and the
    benchmark-derivation rules receive the composed activity and are
    otherwise unchanged; `load-history` and plan reconciliation read pages,
    not files, and are unchanged.
  - The route map is planned from the composed position channel.

## Requirements

### Requirement 1: One Composed Activity per Page
**Objective:** As an athlete whose workout page holds more than one file, I want
the page built from all of them, so that channels only an extra carries reach
my page.

#### Acceptance Criteria
1. When a page has at least one extra, fitdocs shall render the page's body, derived values and charts from one activity composed of the base and the page's extras.
2. When a page has no extra, fitdocs shall render it from the base alone, byte-identically to how it renders that file as a page's only file.
3. fitdocs shall compose a page's activity as a function of the base and of the extras in rank order alone, so that the same set of files produces byte-identical page content and chart images whatever order the files arrived in, in one run or across several.
4. fitdocs shall give the composed activity exactly the base's samples: the same number, at the same instants, in the same order, never adding, removing or reordering a sample.
5. fitdocs shall take the composed activity's laps, strength sets, devices, session-level recorded values, session developer values, record-level developer fields, decode errors, sport and start time from the base, and shall take none of them from an extra.
6. fitdocs shall determine a page's filename, session identity and recorded base identity from the base alone, exactly as for a page with no extra.

### Requirement 2: Donation, Never Override
**Objective:** As an athlete, I want an extra to add only what the base lacks, so
that the file I rank highest is never overridden.

#### Acceptance Criteria
1. When the base records a channel, fitdocs shall take that channel from the base in full and shall take no value of it from any extra.
2. While the base records a channel at some samples and not at others, fitdocs shall leave every sample the base does not record absent, and shall never fill it from an extra.
3. When the base does not record a channel and at least one extra records it at an instant of the base's samples after alignment (Requirement 3), fitdocs shall take that channel from the highest-ranked such extra alone.
4. fitdocs shall take position from an extra only when the base records neither latitude nor longitude, and then shall take both from the one highest-ranked extra that records both at instants of the base's samples after alignment.
5. fitdocs shall take each running-dynamics channel, each balance channel and air power included, independently of the channel that gates its placeholder rule, and shall keep every donated value exactly as the extra's own decoding produced it, never re-filtering it against the base's channels.
6. fitdocs shall hold a donated channel absent at every base sample at which no value of it is placed, and shall never interpolate, carry forward, zero-fill or otherwise invent a value there.
7. fitdocs shall never combine values of one channel from two files into one value or one channel.
8. fitdocs shall apply criteria 1-7 to every per-sample channel of the activity model, including channels added to the model after this feature, without a per-channel exception.

### Requirement 3: Alignment on the Base's Timeline
**Objective:** As an athlete, I want an extra's values placed at the moment they
were measured, so that a donated channel lines up with the base's own channels
although the files' clocks drift apart between pauses.

#### Acceptance Criteria
1. fitdocs shall relate the samples of a page's files by their instants, to the whole second.
2. fitdocs shall split an extra's samples into stretches at every pause of the extra and at every pause of the base.
3. fitdocs shall establish as each stretch's lag the whole number of seconds between −2 and +2 inclusive at which the extra's distance values equal the base's distance values at the lagged instants, to the channel's recorded resolution, for at least 5 samples and for more than half of the samples compared at that lag, provided that no other lag in that range matches as many samples.
4. If distance establishes no lag for a stretch, fitdocs shall establish the stretch's lag from power by the rule of criterion 3.
5. fitdocs shall place each value of a stretch at the base sample whose instant equals the value's own instant plus the stretch's lag.
6. fitdocs shall never establish a lag from heart rate, cadence, step length or any channel other than distance and power.
7. If neither distance nor power establishes a lag for a stretch, fitdocs shall place that stretch's values at the base samples whose instants equal their own, and shall record that the stretch fell back to exact timestamps.
8. When an extra's recorded start differs from the base's by a whole number of hours between 1 and 36, to within 1 second, fitdocs shall move every instant of the extra by that whole number of hours toward the base's start before splitting it into stretches and establishing lags.
9. fitdocs shall place each value of an extra at no more than one base sample and no more than one value of a channel at any base sample, and shall discard every value whose placed instant is not an instant of a base sample.
10. fitdocs shall align each extra against the base alone, never against another extra or against values already composed.

### Requirement 4: Channel Provenance on the Page
**Objective:** As an athlete, or an agent reading my wiki, I want each page to
say which file every channel came from and how it was aligned, so that every
number on it can be traced and questioned.

#### Acceptance Criteria
1. When a page has at least one extra, fitdocs shall include a Channel Sources section listing every file the page is composed from, with its archive reference, its role (base or extra) and its source kind, naming the recorded manufacturer of an original.
2. The Channel Sources section shall list with each file the channels it supplies to the page, and shall list every channel for which the page holds at least one value with exactly one file.
3. The Channel Sources section shall name each channel by the label fitdocs gives it in the channel coverage table or the Running Dynamics section, in the activity model's channel order, and shall name position once, as GPS.
4. When an extra supplies at least one channel, the Channel Sources section shall state for that extra the number of stretches, how many were aligned by distance, how many by power and how many fell back to exact timestamps, and the whole-hour shift when one was applied.
5. When an extra supplies no channel, the Channel Sources section shall show the absence marker in place of that extra's channels and alignment.
6. When a page has no extra, fitdocs shall not include the Channel Sources section.
7. fitdocs shall place the Channel Sources section after the Device & Data Quality section.
8. fitdocs shall record channel provenance in the page body only, and shall write no frontmatter key for it.

### Requirement 5: Summaries Follow the Channels
**Objective:** As an athlete, I want every summary on a page computed from the
channels the page shows, so that a donated heart rate or form power appears
where it matters while nothing the base recorded is replaced.

#### Acceptance Criteria
1. When a donated channel feeds a value the page shows (a summary statistic, a telemetry chip, a frontmatter metric, a chart, a zone time, a 1 km split or a Running Dynamics row) and the base records no session-level value for it, fitdocs shall compute that value from the composed samples, for example the average heart rate of a ride whose base records no heart rate, or the average form power of a run whose base records none.
2. While the base records a session-level value, fitdocs shall show the base's value, even where a donated channel would compute a different one.
3. fitdocs shall compute every value that no donated channel feeds exactly as it computes it from the base alone.
4. fitdocs shall show only the base's recorded lap values in the lap table, and shall never fill a lap value the base's lap does not record from a donated channel.

### Requirement 6: Load and Benchmarks Read the Composed Activity
**Objective:** As an athlete, I want training load and derived benchmarks
computed from the same activity the page shows, so that a channel donated to
the page is a channel load can score.

#### Acceptance Criteria
1. When the training-load pass computes a page's load, fitdocs shall compute it from the activity composed of the page's listed archived files, taking the last listed file as the base and every other listed file as an extra, an extra listed nearer the end of the list ranking higher.
2. When the benchmark-derivation pass derives from a tagged page, fitdocs shall derive from the activity composed by the rule of criterion 1.
3. If a listed file other than the last cannot be resolved to an archived file, fitdocs shall compose from the listed files that resolve, as regeneration does.
4. If the last listed file cannot be resolved to an archived file, or any listed file that resolves cannot be read or decoded, fitdocs shall report the page exactly as each pass reports an unresolvable, unreadable or undecodable source, and shall not alter the page.
5. fitdocs shall apply the training-load data-sufficiency rules to a composed activity exactly as to any activity, a donated channel's recorded samples counting toward its coverage and its absent samples counting against it.
6. While a page's load region holds a computed result, fitdocs shall keep that result until the athlete requests recomputation, and the documentation shall state that recomputing load rescores a page whose composition changed after its load was computed.

### Requirement 7: Regeneration, Determinism and Dependencies
**Objective:** As an athlete, I want composed pages rebuilt exactly from the
archive, so that the composition is never the only copy of anything.

#### Acceptance Criteria
1. When the regeneration command rebuilds a composed page from its archived files, fitdocs shall produce the same page bytes and chart images as the run that last wrote the page from the same files, source precedence, athlete profile and timezone.
2. fitdocs shall compose without network access, without reading a clock, and without reading any file other than the page's listed archived files.
3. fitdocs shall add no runtime dependency.

### Requirement 8: The Published Contract and the Document Format
**Objective:** As a person or agent maintaining a wiki fitdocs writes into, I
want the composition stated where the other guarantees are, and old pages
brought current by the regeneration I already know, so that I can rely on it.

#### Acceptance Criteria
1. fitdocs shall advance the document-format version by exactly one from the value current when this feature lands, so that `fitdocs check` reports every page written before it as out of date and `fitdocs regen` brings it current.
2. fitdocs shall render every page that has no extra byte-identically to how it rendered immediately before this feature landed, apart from the recorded document-format version.
3. The published ownership contract shall state that a page takes each channel from exactly one of its files (the base when the base records it, otherwise the highest-ranked extra that records it), that its identity, laps and session values are the base's, that its Channel Sources section names the file each channel came from, and that the training-load and benchmark-derivation passes read the same composed activity.
4. The published contract version shall advance by one from the value current when this feature lands, and the contract's statement of what changed at that version shall name this feature's changes.
5. fitdocs shall leave the published set of managed frontmatter keys unchanged.
6. The release notes shall state, under the unreleased entry, that a page holding several files of one workout takes the channels its base lacks from the other files and names each channel's file, that `fitdocs regen` applies this to existing pages, and that recomputing load rescores a page whose load was computed before.

### Requirement 9: Measured Shapes and Evidence
**Objective:** As a fitdocs maintainer, I want this feature proven on synthesized
files with the measured shapes, by tests that can fail, so that the public
repository stays honest and holds no personal data.

#### Acceptance Criteria
1. The fitdocs test suite shall use only synthesized `.fit` pairs reproducing the measured shapes (a Stryd↔HealthFit run pair whose distance and power agree at a lag of +1 s in some stretches and 0 s in others, +1, +1, 0, +1, 0 across five stretches; whose heart rate agrees at a lag of −1 or 0 s; whose base carries 2 to 7 trailing samples the extra lacks; whose step length reads about 0.8% higher in the extra and whose cadence differs by ±1; and a Garmin↔HealthFit ride pair starting in the same second, with distances within 5 m and the copy's power covering about 99% of samples), and no personal file, name, date or value.
2. If lags are established once per file instead of once per stretch, or a channel the base records is taken from an extra, or heart rate establishes a lag, or an extra's laps reach the page, or a partially recorded base channel is filled from an extra, then the fitdocs test suite shall fail.
3. The fitdocs repository shall name no Stryd web or service address in this feature's code, tests, specification or documentation.
