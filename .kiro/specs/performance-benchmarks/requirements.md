# Requirements Document

## Project Description (Input)
An athlete with nine years of `.fit` files runs `fitdocs load` and gets *not
computed* on every page, because every load fitdocs computes is anchored on a
dated benchmark and the archive holds none for the past: a benchmark answered
at the prompt is dated today, and the store never applies a future-dated
benchmark to a past activity (queue item
`2026-08-27-prompt-date-strands-historical-documents`, critical). Wave 0 of
Phase 6 fixes the prompt's dating, but even a correctly dated prompt answer is
one number for one date; it cannot describe what the athlete's threshold was
in 2019, 2021 and 2024. The races can. A race is a dated maximal performance
with a certified distance and an official time, and the literature has been
converting such results into threshold estimates for forty years. This spec
adds a pass that reads every page the athlete tagged as a race, test or hard
effort (`effort-tags`), re-parses that page's archived source, derives
threshold pace, lactate-threshold heart rate and functional threshold power
through cited models, and writes them into `athlete.toml` as ordinary dated
entries carrying a provenance record -- so the shipped calculator scores the
whole archive against the threshold that was true at the time, with no change
to the calculator's own code. Nothing in the store records today *how* a
benchmark was obtained; this spec adds that field and the rule that the pass
never touches an entry it did not write. Source:
`.kiro/specs/performance-benchmarks/brief.md`; Phase 6 of
`.kiro/steering/roadmap.md`.

## Introduction

performance-benchmarks is the pass that turns the athlete's own history into
the anchors the load calculator has been missing. It reads tags, not files
directly: `effort-tags` says which pages are dated maximal performances, and
this spec decides what such a performance implies about a threshold on that
date. It writes to one place -- the `[benchmarks]` region of `athlete.toml`
that `athlete-benchmarks` already owns -- and it writes ordinary dated entries
there, so every consumer downstream (the threshold calculator first among
them) reads a derived benchmark exactly as it reads a typed one, with no code
change anywhere.

Four principles govern every requirement below.

**Derived is not measured.** Every entry this pass writes carries a provenance
record naming the method, the page it came from, the inputs it used and the
citation that governs it. An entry without that record was written by someone
else -- the athlete, or the prompt -- and this pass never edits, replaces or
shadows it. Provenance is what makes the store honest about the difference,
and it is mandatory, not optional.

**A refusal is an outcome, not a gap.** A race outside the model's validity
window, an effort with no heart-rate stream, a cycling file with no power, a
sport the pass does not cover: each is declined by name, with the observed
value and the rule that refused it, and nothing is written. Absent data is
`None`, never a fabricated value, and a validity window is a refusal, never a
clamp.

**Citation discipline is the gate on every number.** No numeric literal in
this feature's arithmetic stands without a citation record naming the work,
the locator and how well it was verified; and where the literature does not
state a step fitdocs needs, that step is recorded as fitdocs' own choice with
its justification, never dressed up as a source's. Where a locator is not yet
verified, the constant that depends on it does not ship -- and the method that
needed it declines by name until it does, rather than blocking every other
derivation.

**Official beats recorded, and the fallback is named.** A certified course
distance and a chip time carried on the tag take precedence over GPS distance
and recorded elapsed time. Whichever anchored the number is written into the
entry's provenance, so a later reader knows which one it was.

## Boundary Context

- **In scope**: a pass over every tagged workout page and its archived source
  that derives threshold pace (running, from a race), lactate-threshold heart
  rate (running or cycling, from a sustained maximal effort) and functional
  threshold power (cycling, from a test or time trial); the provenance field
  on a benchmark entry and its parsing, serialization and write path (an
  `athlete-benchmarks` amendment landed here); the rule that the pass never
  overwrites or shadows an entry it did not write; reconciliation of derived
  entries against the current tag set and byte-level idempotence of repeated
  runs; a command that runs the pass and a per-run report naming what was
  derived and what was declined, with reasons; the citation records for every
  constant and formula and the fitdocs-choice records for every step the
  literature does not state; and the amendment to `athlete-benchmarks`'
  boundary line that excluded estimation.
- **Out of scope**: deriving maximum or resting heart rate (a race maximum is
  a lower bound and wrist-optical spikes are common -- a listed candidate, not
  a deliverable); any change to channel arithmetic, channel selection, or the
  threshold calculator (`threshold-load` Requirement 11 stands untouched);
  automatic detection or suggestion of races and best efforts, and locating an
  effort inside a longer file; prompting the athlete for anything;
  aggregation of load over time or any longitudinal page (`load-history`);
  fitting model constants to results (`performance-model-fit`); the effort-tag
  vocabulary and its validation (`effort-tags`); staleness of a benchmark
  (`athlete-benchmarks` / `activity-qa-flags`); rendering a derived benchmark
  into any document; sports other than running and cycling, which the pass
  declines by name; and any new configuration table or key.
- **Adjacent expectations**: `effort-tags` publishes the one reader for a
  page's tag, its closed kind vocabulary and its optional official distance,
  time and event fields; this pass reads tags only through that reader,
  treats a malformed tag as a reportable condition on that page and never as
  untagged, and defines no second spelling of an effort key.
  `athlete-benchmarks` owns the benchmark vocabulary, the entry shape, the
  parser, the serializer and dated selection; this spec extends the entry with
  provenance and changes no existing guarantee, including the rule that a
  benchmark dated after an activity never applies to it. `training-load` owns
  the profile write path and the prompt; the wave-0 prompt-date fix is
  complementary, not a dependency, because derived entries carry their own
  dates. `fit-ingest` supplies the archived source parse and the sample
  streams. `load-channels` owns the data-sufficiency rule this pass applies to
  a stream; its package may not import anything this spec adds.
  `threshold-load` consumes a derived entry as an ordinary dated entry with no
  code change, and its boundary test pins the calculator's allowed imports --
  nothing this spec adds may become reachable from it. `load-history` adds its
  own command and its own owned path; this spec adds neither.
- **Downstream contract**: `performance-model-fit` reuses the race-equivalence
  model recorded here for its criterion scale and reads derived entries'
  provenance to tell a derived criterion from a measured one.

## Requirements

### Requirement 1: The Derivation Pass and Its Command
**Objective:** As an athlete with a tagged archive, I want one command that turns my tagged efforts into dated benchmarks, so that the load pass can score the years before I first answered a prompt.

#### Acceptance Criteria
1. The fitdocs CLI shall provide a command that runs the benchmark-derivation pass over the resolved data root, distinct in name from every existing command and from the command `load-history` adds.
2. When the derivation command runs, the fitdocs CLI shall consider every generated workout document under the data root, read each one's effort tag through the document contract's single published reader, and process only those documents that carry a tag.
3. While a document carries no effort tag, the fitdocs CLI shall not open, re-parse, or otherwise read that document's archived source.
4. When a tagged document is processed, the fitdocs CLI shall resolve that document's archived source by the same rule the training-load pass resolves it, re-parse it, and derive from the parsed activity and the tag.
5. If a tagged document's archived source cannot be resolved or cannot be parsed, the fitdocs CLI shall record that document as a failure naming the document and the reason, shall write no benchmark from it, and shall continue processing the remaining tagged documents.
6. If a tagged document's tag is malformed, the fitdocs CLI shall record that document as a failure naming the document and each offending key with the expectation it failed, shall derive nothing from it, and shall never treat it as untagged.
7. When every tagged document has been processed, the fitdocs CLI shall write all accepted derived benchmarks to the athlete profile in a single write, and shall leave the profile untouched when no benchmark was accepted.
8. Where the derivation command is invoked in a preview mode, the fitdocs CLI shall produce the same report it would otherwise produce and shall create, modify, or delete no file.
9. The fitdocs CLI shall complete the run with a non-zero exit status when at least one document was recorded as a failure, and with a success status when the run produced only derivations and declines.
10. The fitdocs CLI shall derive benchmarks only within this command; no other command shall derive, write, or reconcile a derived benchmark.

### Requirement 2: Threshold Pace From a Tagged Race
**Objective:** As a runner, I want each of my races converted into the pace I could have held for an hour on that date, so that my old running pages score against the threshold I actually had.

#### Acceptance Criteria
1. Where a tagged document's activity is a running activity and its tag names the race kind, the fitdocs CLI shall derive a threshold pace for the running discipline from the race's distance and time through the published race-equivalence model.
2. Where the tag carries both an official course distance and an official time, the fitdocs CLI shall use those two values as the model's inputs.
3. While the tag carries no official course distance and time, the fitdocs CLI shall use the activity's recorded total distance and recorded elapsed time as the model's inputs.
4. The fitdocs CLI shall record which of the two input pairs anchored the derived value in the entry's provenance, so that a later reader can tell an official result from a recorded one without re-deriving it.
5. If the effort's duration falls outside the race-equivalence model's published validity window, the fitdocs CLI shall decline the derivation with a reason naming the observed duration and both bounds of the window, and shall neither clamp the duration nor extrapolate beyond the window.
6. If the inputs needed by the model are absent, non-positive, or non-finite -- an unrecorded distance, a zero elapsed time -- the fitdocs CLI shall decline the derivation naming the missing or invalid input and shall write nothing.
7. The fitdocs CLI shall express the derived value as a threshold pace in seconds per kilometre, recorded under the running discipline and dated at the tagged page's own calendar date.
8. While a tagged document's activity is a running activity and its tag names the test or hard kind rather than the race kind, the fitdocs CLI shall derive no threshold pace from it and shall state that reason in the report.
9. The fitdocs CLI shall solve the model for the one-hour distance as an explicit, recorded step of its own, distinct from the model the literature states, and shall record that step as fitdocs' own choice with its justification.

### Requirement 3: Lactate-Threshold Heart Rate From a Sustained Maximal Effort
**Objective:** As an athlete who races and tests, I want the heart rate I sustained through a maximal effort recorded as my threshold heart rate on that date, so that heart-rate-anchored load works across my archive.

#### Acceptance Criteria
1. Where a tagged document's activity is a running or cycling activity and its tag names any of the three effort kinds, the fitdocs CLI shall derive a lactate-threshold heart rate for that activity's discipline from the effort's heart-rate stream.
2. The fitdocs CLI shall compute the derived value as the time-weighted average heart rate over the whole recorded effort, never over a selected portion of it, and never by discarding a leading or trailing segment.
3. If the effort's recorded duration falls outside the published validity window for a sustained maximal effort, the fitdocs CLI shall decline the derivation with a reason naming the observed duration and both bounds of the window.
4. If the heart-rate stream's time-weighted coverage over the effort falls below the configured minimum for the heart-rate channel, the fitdocs CLI shall decline the derivation with a reason naming the observed coverage and the minimum required.
5. If the activity records no heart rate anywhere, the fitdocs CLI shall decline the derivation with a reason distinguishing an absent stream from an insufficiently covered one.
6. Where the tag carries an official time and the activity's recorded span differs from it by more than the published tolerance, the fitdocs CLI shall decline the derivation naming both durations, because the pass cannot locate the effort inside a longer recording and locating it is out of scope.
7. The fitdocs CLI shall express the derived value as a whole number of beats per minute by a stated rounding rule recorded as fitdocs' own choice, and shall never store a fractional value the store would reject.
8. The fitdocs CLI shall record the derived value under the activity's own discipline and shall never record it under the whole-athlete scope or borrow it across disciplines.
9. The fitdocs CLI shall record in the entry's provenance that the value is the whole-effort average of a sustained maximal effort, with the citation that governs that method.

### Requirement 4: Functional Threshold Power From a Cycling Effort
**Objective:** As a cyclist, I want my time trials and power tests turned into dated FTP entries, so that power-anchored load applies to my older rides.

#### Acceptance Criteria
1. Where a tagged document's activity is a cycling activity carrying a power stream and its tag names the race or test kind, the fitdocs CLI shall derive a functional threshold power for the cycling discipline from that stream.
2. Where the effort's duration falls inside the window the definition itself states for a threshold effort, the fitdocs CLI shall derive the value as the time-weighted average power over the whole effort, with no scaling factor applied.
3. Where the effort's duration matches the shorter test protocol instead, the fitdocs CLI shall derive the value by applying the published factor to the effort's average power, and shall do so only while the citation record for that factor is present and verified.
4. While the citation record for the shorter test protocol's factor is not verified, the fitdocs CLI shall decline every derivation that would need it with a reason naming the unverified locator and what must be read to resolve it, and shall continue to derive by every other method in this feature.
5. If the power stream's time-weighted coverage over the effort falls below the configured minimum for the power channel, the fitdocs CLI shall decline the derivation naming the observed coverage and the minimum required.
6. If the activity records no power anywhere, the fitdocs CLI shall decline the derivation with a reason stating that the file carries no power, and shall state that outcome in the run report rather than silently omitting the discipline.
7. If the effort's duration falls outside every window this feature covers, the fitdocs CLI shall decline the derivation naming the observed duration and the covered windows.
8. The fitdocs CLI shall record in the entry's provenance the measured limits of agreement published for the derivation method it used, so that a reader of the file sees the method's own uncertainty next to the number.
9. Where a tagged document's activity is a running activity, the fitdocs CLI shall derive no functional threshold power from it, even when the file carries running power.
10. The fitdocs CLI shall express the derived value in watts, recorded under the cycling discipline and dated at the tagged page's own calendar date.

### Requirement 5: Provenance on a Benchmark Entry
**Objective:** As an athlete reading my own `athlete.toml`, I want every entry to say where it came from, so that I can tell a number I measured from a number fitdocs worked out, and correct either one by hand.

#### Acceptance Criteria
1. The fitdocs CLI shall extend a benchmark entry with an optional provenance record, and shall treat an entry that carries none as an entry fitdocs did not derive.
2. The provenance record shall state which class of origin the entry has, drawn from a closed, published vocabulary, and shall state the derivation method, the document the derivation read, the inputs it used, and the key of the source record that governs the method whenever the origin is a derivation.
3. The fitdocs CLI shall write a provenance record on every benchmark it derives, without exception, and shall write no derived benchmark that lacks one.
4. When the fitdocs CLI reads a benchmark entry carrying a provenance record, it shall parse it into the same typed value the write path produces, so that a record written by one run is read identically by the next.
5. If a benchmark entry's provenance record is present but malformed -- not a table, an origin outside the published vocabulary, a missing required field, or a field of the wrong type -- the fitdocs CLI shall reject the profile with a message naming the file, the offending entry and what was expected, and shall neither drop, coerce, nor guess the record.
6. The fitdocs CLI shall ignore an unrecognized field inside a provenance record for forward compatibility, exactly as it already ignores an unrecognized field on a benchmark entry, and shall carry it through unchanged on a rewrite.
7. When the fitdocs CLI rewrites the profile, it shall preserve the provenance record of every entry it did not write, byte-equivalently in content, alongside every other field of that entry.
8. The fitdocs CLI shall keep `athlete.toml` plain, readable and editable without fitdocs installed: the provenance record shall be expressed in the file's own ordinary notation, with no encoded, packed, or generated identifier a person cannot read.
9. The fitdocs CLI shall accept a provenance record on the existing programmatic write path for a single dated benchmark, so that any future caller recording a benchmark can state its origin.
10. The fitdocs CLI shall validate a provenance record's shape and its origin class rather than the method name it carries, so that an entry naming a derivation method a future release adds stays readable, while the set of method names this feature writes remains closed and published.

### Requirement 6: Never Overwriting What the Athlete Recorded
**Objective:** As an athlete who typed a tested FTP into my profile, I want fitdocs never to replace or shadow it with something it worked out, so that the numbers I measured always win.

#### Acceptance Criteria
1. The fitdocs CLI shall never modify, replace, or delete a benchmark entry that carries no derivation provenance, including entries written by the athlete by hand and entries written by the training-load prompt.
2. If a derived benchmark would occupy the same discipline, quantity and date as an existing entry that fitdocs did not derive, the fitdocs CLI shall not write the derived benchmark, shall leave the existing entry untouched, and shall report the derivation as declined with a reason naming the existing entry.
3. When the derivation pass writes, it shall replace only those entries whose provenance records them as derived, and shall leave every other entry, table and key in the profile untouched.
4. When the derivation pass runs and a tag that produced a derived entry on an earlier run is no longer present, no longer valid, or no longer yields a derivation, the fitdocs CLI shall remove the derived entry that tag produced, so that the store reflects the current tag set rather than the union of every past run.
5. When the derivation pass runs twice over an unchanged tag set, an unchanged archive and an unchanged configuration, the second run shall leave the profile byte-identical to what the first run wrote.
6. When the derivation pass writes the profile, it shall preserve every non-benchmark key and table in the file, every benchmark entry of a quantity it does not derive, and every piece of content the benchmark parser deliberately ignores for forward compatibility.
7. If writing the profile would produce a document the profile reader would reject, the fitdocs CLI shall refuse the write with a message naming the target and the reason, and shall leave the existing file exactly as it was.
8. The fitdocs CLI shall write the profile atomically, leaving no partial or temporary file behind if the run is interrupted.

### Requirement 7: Declining Is an Outcome With a Reason
**Objective:** As an athlete running the pass, I want a report that says what it derived and exactly why it refused everything else, so that I can fix a tag, tag another page, or accept that a file simply lacks the data.

#### Acceptance Criteria
1. When the derivation pass completes, the fitdocs CLI shall report the number of documents considered, the number of tagged documents processed, the benchmarks derived, the derivations declined, and the documents that failed.
2. For every derived benchmark, the fitdocs CLI shall report the quantity, the discipline, the value with its unit, the date, the method, and the document it came from.
3. For every declined derivation, the fitdocs CLI shall report the document, the quantity it would have produced, and a reason drawn from a closed, published vocabulary, together with the observed value and the requirement that refused it where the reason has them.
4. The fitdocs CLI shall report a decline in the same vocabulary the training-load pass uses for the equivalent condition, so that "this stream is not good enough" reads identically in both reports.
5. Where a tagged document's sport is neither running nor cycling, the fitdocs CLI shall decline every derivation for it with a reason naming the sport, rather than omitting the document from the report.
6. Where the tagged page carries no parseable date, the fitdocs CLI shall decline every derivation from it with a reason naming that condition, and shall never date an entry from the wall clock, the file's timestamps, or the activity's own recorded start.
7. While no cycling file in the archive carries a power stream, the fitdocs CLI shall report that no functional threshold power was derived and why, rather than reporting a successful run that silently produced nothing for that quantity.
8. The fitdocs CLI shall distinguish a decline from a failure in the report and in the exit status: a decline is a method that does not apply and leaves the run successful, while a failure is a broken input the athlete should fix.
9. The fitdocs CLI shall report every decline and failure for a document, not only the first, so that one run tells the athlete everything wrong with a page.

### Requirement 8: Citation Discipline and the Blocked Constant
**Objective:** As a maintainer who has already shipped one refuted coefficient, I want every number in this feature bound to a source record with an honest verification status, so that no value can enter the athlete's file without a traceable origin.

#### Acceptance Criteria
1. The fitdocs CLI shall bind every constant this feature introduces -- each model's exponent, each validity-window bound, each scaling factor, each tolerance and each rounding rule -- to exactly one governing source record naming the work, its locator, and how well the value was verified.
2. Where no published work defines a value this feature needs, the fitdocs CLI shall record it as fitdocs' own choice with its justification and what was searched, and shall never present it as read from a published work's text.
3. The fitdocs CLI shall carry no bare numeric literal for any such constant in this feature's arithmetic; every value shall be reached through its bound record.
4. Where a constant's governing record is only attested by secondary sources because the primary text has not been obtained, the fitdocs CLI shall record that status explicitly and shall name the record in a published set of tracked exceptions stating what must be read to resolve it.
5. If a constant's locator has not been verified against the work itself, the fitdocs CLI shall not ship that constant at all, and the method that depends on it shall decline by name while every other method in this feature continues to work.
6. The fitdocs CLI shall record a further work that measures or corroborates a value as a corroborating record with its own locator and its own verification status, never as a second governing source.
7. The fitdocs CLI shall state in each derived entry's provenance the key of the governing record for the method that produced it, so that the athlete's file points back at the literature.
8. The fitdocs CLI shall keep this feature's source records consistent with the record of the same work already shipped elsewhere in the package, so that one work cannot be described two different ways.

### Requirement 9: Determinism, Offline Operation and the Data-Root Contract
**Objective:** As an athlete who re-runs the pass, I want the same inputs to produce the same bytes, so that the store is reproducible and the pass is safe to run at any time.

#### Acceptance Criteria
1. The fitdocs CLI shall produce identical profile bytes from identical tags, archived sources and configuration, independent of the order documents are discovered in, the machine, the locale, and the system time zone.
2. The fitdocs CLI shall open no network connection during the pass.
3. The fitdocs CLI shall consult no clock during the pass beyond the run's own notion of today, and shall date no entry from it.
4. The fitdocs CLI shall create, modify, or delete nothing under the data root during the pass except the athlete profile, which the ownership contract already names a shared file fitdocs writes its own keys into.
5. The fitdocs CLI shall write no workout document, asset, archived source, or cache entry during the pass.
6. The fitdocs CLI shall resolve the data root by the same precedence every other command uses, and shall fail loudly rather than write anywhere else when it cannot be resolved.
7. The fitdocs CLI shall require no new configuration key or table for this feature, and shall read the stream-sufficiency minima the training-load configuration already publishes.
8. The fitdocs CLI shall treat the validity windows, exponents and factors of a published method as constants rather than as configuration, so that no setting can move a number away from the source that governs it.

### Requirement 10: Feature Boundary and Permanent Exclusions
**Objective:** As the owner of the surrounding specs, I want this feature to stop exactly at writing dated entries, so that estimation stays out of the calculator and out of the store, and the rejected designs cannot return.

#### Acceptance Criteria
1. The fitdocs CLI shall make no change to the threshold calculator, to any channel's arithmetic, or to channel selection, and a derived benchmark shall reach the calculator as an ordinary dated entry indistinguishable in use from a typed one.
2. The fitdocs CLI shall keep this feature unreachable from the threshold calculator and from the channels package: no module of either shall import anything this feature adds.
3. The fitdocs CLI shall define no second reader of the effort tag, no second spelling of an effort key, and no parsing of document frontmatter of its own.
4. The fitdocs CLI shall derive no maximum heart rate and no resting heart rate.
5. The fitdocs CLI shall detect, suggest, or infer no effort: it shall act only on tags the athlete wrote, and shall never search a recording for a best effort or locate an effort inside a longer file.
6. The fitdocs CLI shall prompt for nothing during the pass and shall run identically with and without a terminal.
7. The fitdocs CLI shall aggregate nothing over time, shall fit no model constant, and shall render nothing into any document.
8. The fitdocs CLI shall claim no owned path and shall add no document type, leaving the data-root layout and its ownership declarations unchanged.
9. The fitdocs CLI shall keep the published boundary of the benchmark store consistent with this feature's existence, so that the store's stated exclusion of estimation names the pass that performs it rather than contradicting it.
