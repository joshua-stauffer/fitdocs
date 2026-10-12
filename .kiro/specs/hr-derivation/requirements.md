# Requirements Document

## Project Description (Input)
**Who has the problem.** An athlete who keeps a markdown wiki with fitdocs
and wants heart-rate training load to be right without maintaining the
numbers it depends on. Heart-rate load needs a resting and a maximum heart
rate: TRIMP uses the heart-rate reserve `(hr - rest) / (max - rest)`, and the
threshold heart-rate channel needs the threshold, resting and maximum heart
rates to describe one athlete.

**Current situation.** Both values exist only if the athlete types them in,
as dated `max_hr_bpm` and `resting_hr_bpm` entries in `athlete.toml`, and
nothing keeps them current: a resting heart rate typed once in 2023 still
scores 2026 workouts. Entries are chosen for an activity by date alone. The
derivation command derives threshold pace, threshold heart rate and threshold
power from tagged efforts, but is forbidden to derive maximum or resting
heart rate, and its write replaces every derived entry, so a second
derivation would erase the first. A derived entry must name one page it was
derived from, which a value read from a daily series does not have. Yet
fitdocs now holds the evidence for both values: every workout's heart-rate
recording gives the observed maxima, and the wellness series gives a daily
resting heart rate per source.

**What should change.** `fitdocs derive-benchmarks` also derives dated
resting and maximum heart-rate entries into the benchmark timeline, with
their method, evidence and citation, and the training-load pass uses them by
date like any other entry, selected exactly as today. A value the athlete
recorded by hand is never replaced by agreeing evidence, under a precise rule
the maintainer chose on 2026-10-12: the derivation writes a new entry only
when evidence disagrees by more than a fixed step with the value in force on
its date, a hand-recorded value therefore stays in force until evidence dated
after it disagrees, and every takeover of a hand-recorded value is announced.
Re-running on unchanged inputs changes nothing, and the timeline stays sparse.

Source: `.kiro/specs/hr-derivation/brief.md`; Phase 12 of
`.kiro/steering/roadmap.md`; maintainer decisions of 2026-10-12 relayed by the
Phase 12 spec-batch controller. Dependencies: `wellness-store`. Downstream:
the training-load pass (threshold calculator, heart-rate channel), the
analytics index's benchmark tables, `recovery` (which may plot the values).

## Introduction

fitdocs scores heart-rate load against a resting and a maximum heart rate.
This feature derives both from evidence fitdocs already holds and writes them
into the athlete's benchmark timeline. It writes a value only where the
evidence disagrees with the value already in force, so a number the athlete
recorded stays in charge until the athlete's own recordings clearly contradict
it. Which entry applies to an activity is decided exactly as today.

Terms used below:
- The **benchmark timeline** is the dated benchmark entries in the athlete
  profile, `athlete.toml`. An entry has a **kind** (here `resting_hr_bpm` or
  `max_hr_bpm`, both athlete-wide and in whole beats per minute), a value, a
  measurement date and, optionally, an applies-from date and a provenance
  record.
- A **derived entry** is one whose provenance names a derivation as its
  origin. A **hand-recorded entry** is every other entry: typed by hand,
  answered at a load-pass prompt, or marked as measured.
- The **value in force** on a date is the entry fitdocs selects for an
  activity on that date, by the unchanged selection rule: the latest entry
  measured on or before the date, whoever recorded it; when there is none, an
  entry whose applies-from date reaches back to the date.
- A hand-recorded entry's **back-reach** is its applies-from date: the entry
  also covers the days from that date which no earlier-measured entry covers.
- **Evidence** is a candidate value of a kind for one calendar day, worked out
  from the wellness series (resting heart rate) or from workout recordings
  (maximum heart rate). An **evidence day** is a day that has evidence.
- A **source** is a wellness source as the wellness series names it (for
  example `garmin-export`, `apple-health`, `intervals-icu`). A source's
  **baseline** is the robust level of its own daily resting heart rate.
- A **sustained peak** is the highest mean heart rate a session held over a
  short continuous stretch.
- The **step** of a kind is the hysteresis threshold: evidence must differ
  from the value in force by more than the step before a new derived entry
  starts.
- A **takeover** is a derived entry for which the value in force on its
  date, leaving that entry itself aside, comes from a hand-recorded entry,
  whether that entry is measured on or before the date or reaches back to it.
- The derivation command has two **stages**: the **tagged-effort stage**
  (threshold pace, threshold heart rate and threshold power from tagged
  efforts, owned by `performance-benchmarks`) and the **heart-rate stage**
  this feature adds.

## Boundary Context

- **In scope**: the heart-rate stage of `fitdocs derive-benchmarks` and its
  report; derived resting heart rate from the wellness series, one baseline
  per source, with the source chosen by the wellness precedence; derived
  maximum heart rate from workout heart rate (sustained peaks, rejection of
  implausible samples and of cadence-locked stretches, a recency window);
  the step, confirmation and dating rules that keep the timeline sparse; the
  hand-recorded-wins rule as a rule of what the heart-rate stage writes;
  takeover announcements in the report, in the timeline and in
  `fitdocs check`; the one-time notice when derived entries narrow a hand
  entry's back-reach; the provenance of an entry derived from a series; the
  citation records behind every constant; partitioning the derived write so
  the two stages never erase each other; `check` findings for inconsistent
  heart-rate benchmarks; the heart-rate channel naming the dated entries it
  used; documentation, the packaged skill and the release notes; the
  published-rule changes this makes to `athlete-benchmarks` (provenance
  only), `performance-benchmarks`, `load-channels` and the ownership
  contract's version.
- **Out of scope**: heart-rate-variability thresholds; deriving threshold
  heart rate, threshold power or threshold pace (the tagged-effort stage);
  age-formula maxima (220 − age and similar) as values; heart-rate zones,
  which stay absolute dividers; the undated `max_hr_bpm` and `resting_hr_bpm`
  keys at the top of `athlete.toml`, which keep feeding zones and the page's
  own TRIMP figure exactly as today; telling a chest strap from a wrist
  sensor, because no activity fitdocs reads records the heart-rate sensor's
  type; rescoring already computed documents automatically; any page,
  chart or analytics-index table; any change to how an entry is selected
  for an activity, for any kind; any network access; any setting that turns
  derivation off or expires a hand-recorded value.
- **Adjacent expectations**: `wellness-store` provides the daily resting
  heart rate per source, the per-metric source precedence and the
  day-boundary rule, and this feature reads them only through the series it
  publishes. `recovery` owns the descriptive baselines and normal ranges
  shown on the recovery page; this feature's baseline is the level that
  becomes a benchmark value and is not shared with that page. The
  training-load pass selects entries by date and recomputes a document only
  when asked to. The analytics index exposes benchmark entries and their
  in-force periods through its existing tables.

## Maintainer Decisions (2026-10-12)

The brief left two questions for requirements approval. The maintainer
answered both on 2026-10-12, through the Phase 12 spec-batch controller, and
settled a third in a second round the same day; all three are binding here.

1. **Hand-recorded wins: "evidence must disagree", announced.** A
   hand-recorded entry stays in force until evidence dated after it differs
   from it by more than the kind's step; a derived entry then starts on the
   evidence date. Evidence that agrees with the hand value within the step
   never creates a derived entry. Every takeover is announced: the run
   prints it, `fitdocs check` lists it, and the timeline shows it. The
   athlete answers by recording a new hand value, which wins from its date
   under the same rule, or by leaving it. Rejected by the maintainer: a hand
   entry masking derivation until the next hand entry (derivation never
   resumes); a hand entry masking derivation for a fixed window (values
   later change with no notice); either of those with a switch to turn
   derivation off; "maximum heart rate only rises"; a hand entry that
   expires after a warned period. The three points the maintainer asked
   requirements to make precise are settled here: the step per kind
   (Requirement 4.1), how a hand entry's back-reach interacts with derived
   entries dated before its measurement date (decision 3; Requirements 5.5
   to 5.7), and how long `fitdocs check` lists a takeover (Requirements 6.3
   and 6.4).
2. **Resting heart rate across sources: precedence picks, segments
   allowed.** Each source keeps its own baseline, the wellness source
   precedence picks the source for each day, a change of source may start a
   new derived entry whose provenance names the source, and baselines are
   never spliced across sources (Requirement 2).
3. **Selection unchanged; the rule lives in the write** (second round). A
   first draft added a selection rule under which a derived entry never
   applied inside a hand entry's back-reach. It contradicted training-load
   Amendment 4 and athlete-benchmarks Amendment 1, and the maintainer chose
   consistency: selection stays exactly as it is today for every kind (the
   latest entry measured on or before the date wins, whoever wrote it;
   applies-from only fills the days no earlier-measured entry covers), and
   "evidence must disagree" is a rule of what the heart-rate stage writes.
   The stage writes an entry only where evidence disagrees by more than the
   step with the value in force on that date, hand-recorded or derived.
   Derived entries dated before a hand entry's measurement date apply on
   their own dates, so a hand entry's back-reach then covers only the days
   before the first derived entry. The maintainer accepted the consequence:
   on the first run, historic heart-rate load before a hand entry's date
   moves to the derived values where derived evidence exists, once load is
   recomputed. The run states it once (Requirement 5.7), and so do the
   release notes (Requirement 11.5).

## Requirements

### Requirement 1: The Heart-Rate Stage of `derive-benchmarks`
**Objective:** As an athlete, I want the command that already derives my
benchmarks to derive my resting and maximum heart rate too, so that one run
brings the whole timeline up to date.

#### Acceptance Criteria
1. When `fitdocs derive-benchmarks` runs, the fitdocs CLI shall run the heart-rate stage after the tagged-effort stage, over the same resolved data root, in the same invocation.
2. The heart-rate stage shall derive only `resting_hr_bpm` and `max_hr_bpm` entries, each in the athlete-wide scope.
3. When the heart-rate stage completes, the fitdocs CLI shall report the number of workout documents considered, the number that supplied maximum-heart-rate evidence, the number that supplied none for each reason, each document skipped because its archived source is missing or cannot be decoded, the wellness sources that supplied resting-heart-rate evidence, the entries derived and removed per kind, every takeover, every inconsistency (Requirement 9), every failure, and whether the profile was written.
4. Where the command runs in preview mode (`--dry-run`), the heart-rate stage shall produce the same report it would otherwise produce and shall create, modify or delete no file.
5. If the heart-rate stage records a failure, the fitdocs CLI shall complete the run with the failure exit status; a run whose stages only derived, kept, skipped or declined shall complete with the success status.
6. The fitdocs CLI shall derive, write or reconcile a heart-rate entry only within `derive-benchmarks`; `sync`, `regen`, `load`, `check`, `index` and every other command shall derive none.
7. The heart-rate stage shall prompt for nothing, shall run identically with and without a terminal, and shall open no network connection.
8. The heart-rate stage shall require no new configuration key or table; it shall read the wellness source precedence and the cadence-lock settings the athlete has already configured, and `derive-benchmarks` shall read the training-load configuration once per run, shared by both stages.
9. The heart-rate stage shall read neither the analytics index nor the wellness archive.
10. The heart-rate stage shall create, modify or delete nothing under the data root except the athlete profile, and shall write no workout document, asset, archived source, series file or cache entry.
11. If the athlete profile, the wellness configuration or the training-load configuration the heart-rate stage reads is malformed, the fitdocs CLI shall stop with the configuration-error status, naming the file and the problem, before either stage writes anything.

### Requirement 2: Resting Heart Rate From the Wellness Series
**Objective:** As an athlete whose watch reports a resting heart rate every
day, I want fitdocs to keep my resting heart rate current from that series,
so that heart-rate load follows my fitness without me retyping a number.
(Maintainer decision, 2026-10-12: the source precedence picks the source,
each source keeps its own baseline, and baselines are never spliced.)

#### Acceptance Criteria
1. The heart-rate stage shall read resting heart rate only from the normalized wellness series, one source at a time.
2. For each source and each calendar day, the heart-rate stage shall form that source's baseline as the median of the source's own daily resting-heart-rate values on the 28 days ending that day, and only when at least 14 of those 28 days carry a value.
3. The heart-rate stage shall never combine values of more than one source in one baseline, and shall never adjust one source's values to agree with another's.
4. For each calendar day, the heart-rate stage shall take that day's evidence from the first source, in the resting-heart-rate source precedence the wellness configuration sets, whose baseline is formed that day.
5. When no source's baseline is formed on a day, the heart-rate stage shall take no resting-heart-rate evidence from that day.
6. The heart-rate stage shall express a baseline as whole beats per minute, rounding a value exactly halfway between two whole numbers up.
7. When the source supplying the evidence changes from one day to the next, the heart-rate stage shall treat the new source's baseline like any other evidence: it shall start a new derived entry only under Requirements 4 and 5, and that entry shall name the new source.
8. If the wellness series holds no resting-heart-rate value, the heart-rate stage shall derive no resting-heart-rate entry.
9. If the wellness series cannot be read, the heart-rate stage shall record a failure naming the series and the reason, and shall leave every derived resting-heart-rate entry on file unchanged in that run.

### Requirement 3: Maximum Heart Rate From Workout Heart Rate
**Objective:** As an athlete who sometimes races or runs hard intervals, I
want fitdocs to work out my maximum heart rate from those sessions while
ignoring sensor glitches, so that heart-rate reserve uses a maximum I have
actually reached recently.

#### Acceptance Criteria
1. The heart-rate stage shall consider every generated workout document, of every sport, and shall read each one's heart rate from the activity composed of the files the page lists, by the same rule the training-load pass uses.
2. The heart-rate stage shall exclude from a session every heart-rate sample below 30 or above 230 beats per minute, and every sample that differs from the previous sample it kept by more than 10 beats per minute per second.
3. Where the cadence-lock check finds a session locked, the heart-rate stage shall take no evidence from that session; in every other session it shall exclude the samples inside any stretch that check measures as locked.
4. For each session, the heart-rate stage shall find the sustained peak: the highest time-weighted mean of the remaining samples over any 30 continuous seconds, where no two consecutive samples in the stretch are more than 10 seconds apart.
5. The heart-rate stage shall take maximum-heart-rate evidence from a session only when the session has a sustained peak and its document has a calendar date.
6. On each evidence day, the heart-rate stage shall take as evidence the median of the three highest sustained peaks among the sessions dated in the 365 calendar days ending on that day, expressed as whole beats per minute with a halfway value rounded up, and shall take none when fewer than three such sessions exist.
7. The heart-rate stage shall work out maximum-heart-rate evidence on every date of a session that supplies evidence and on every date on which such a session leaves that 365-day window.
8. The heart-rate stage shall never take a maximum from a session's recorded summary maximum, from the wellness series, from an age formula, or from any default.
9. If a workout document has no date, its archived source cannot be found, or its archived source cannot be decoded, the heart-rate stage shall take no evidence from it and shall report it with that reason, without recording a failure.
10. If an archived source that exists cannot be read, the heart-rate stage shall record a failure naming the document and the reason, and shall leave every derived maximum-heart-rate entry on file unchanged in that run.

### Requirement 4: A Sparse, Reproducible Timeline
**Objective:** As an athlete whose `athlete.toml` lives in a git-tracked
wiki, I want derived entries to change only when the evidence really moves,
so that the timeline stays short and readable and historic load does not
churn on noise.

#### Acceptance Criteria
1. The heart-rate stage shall use a step of 3 beats per minute for resting heart rate and of 2 beats per minute for maximum heart rate.
2. While no entry of a kind is in force on an evidence day, the heart-rate stage shall start a derived entry of that kind on that day carrying that day's evidence.
3. When maximum-heart-rate evidence differs from the value in force by more than the step, the heart-rate stage shall start a derived maximum-heart-rate entry on that evidence day carrying that day's evidence.
4. When resting-heart-rate evidence from one source differs from the value in force by more than the step on each of 14 consecutive calendar days, the heart-rate stage shall start a derived resting-heart-rate entry on the first of those days carrying that day's evidence; a day without evidence, a day within the step, or a change of source shall end the run of days.
5. The heart-rate stage shall write no applies-from date on a derived entry, so that a derived entry applies from its own date only.
6. When the heart-rate stage runs, it shall work out the whole timeline of each kind from all the evidence and the hand-recorded entries on file, and shall replace its earlier derived entries of that kind with the result, so that evidence that is gone takes its entries with it.
7. The heart-rate stage shall produce identical entries and identical profile bytes from an identical wellness series, identical workout documents and archived sources, an identical profile and identical configuration, independent of the order documents are found in, the machine, the locale and the system time zone.
8. The heart-rate stage shall consult no clock and shall date no entry from the run date, a file's timestamps, or anything but an evidence day.
9. When the heart-rate stage runs twice over unchanged inputs, the second run shall leave the profile byte-identical and untouched.
10. Where evidence for a kind is absent, the heart-rate stage shall derive no entry of that kind and shall never substitute a default, an earlier hand value or another kind's value.
11. The heart-rate stage shall work out the value in force on an evidence day from the hand-recorded entries and the derived entries it has already decided for earlier evidence days, by the selection rule the training-load pass uses, so that later evidence never changes the decision made for an earlier day.

### Requirement 5: Hand-Recorded Entries Win
**Objective:** As an athlete who measured a value myself, I want my number to
stay in charge until my own recordings clearly disagree with it, so that
derivation never silently overrides me and never stops working because I once
typed a value. (Maintainer decisions, 2026-10-12: "evidence must disagree",
and selection unchanged with the rule in the write.)

#### Acceptance Criteria
1. The heart-rate stage shall never modify, replace or delete a hand-recorded entry, and shall never write a derived entry on the measurement date of a hand-recorded entry of the same kind.
2. The heart-rate stage shall take no evidence from the measurement date of a hand-recorded entry of the kind, so that a hand-recorded value is challenged only by evidence dated after it.
3. The heart-rate stage shall start a derived entry only from evidence that differs by more than the step from the value in force on the evidence day, under Requirement 4, whether that value is hand-recorded or derived.
4. The heart-rate stage shall never start a derived entry from evidence that agrees with the value in force to within the step, so that a correct hand-recorded value is never replaced.
5. Where a hand-recorded entry declares an applies-from date, the heart-rate stage shall compare evidence dated before that entry's measurement date with the value in force on its day, which is the hand-recorded value only on days no earlier-measured entry covers, and a derived entry it starts there shall apply from its own date by the ordinary selection rule.
6. fitdocs shall select the entry for an activity exactly as before this feature, for every kind: the latest entry measured on or before the activity's date, whoever recorded it, and otherwise the entry whose applies-from date reaches back to that date.
7. When a run writes, or in preview mode would write, derived entries that change the days a hand-recorded entry's applies-from date covers, the fitdocs CLI shall report it once in that run, naming the hand-recorded entry, the days it covered before and covers now, and that activities on the other days are scored with the derived values once load is recomputed.
8. When the athlete records a new hand value of a kind, the next run of the heart-rate stage shall treat it under criteria 1 to 5, and shall remove the derived entries the new value makes unnecessary.
9. The fitdocs CLI shall offer no setting that turns heart-rate derivation off, that keeps a derived maximum from falling, or that expires a hand-recorded entry after a period.

### Requirement 6: Announcing a Takeover
**Objective:** As an athlete, I want to be told every time derivation takes
over from a value I recorded, so that a change to my load is never silent and
I can answer it with a value of my own or leave it.

#### Acceptance Criteria
1. When the heart-rate stage writes, or in preview mode would write, a takeover that the profile did not already hold, the fitdocs CLI shall report it, naming the kind, the derived value and its date, the superseded hand-recorded value and its measurement date, whether that value applied by measurement or by its applies-from date, and the evidence: the source and window for resting heart rate, or the session page and window for maximum heart rate.
2. The heart-rate stage shall record on every takeover entry, in the timeline itself, the superseded hand-recorded value and its measurement date.
3. While a takeover entry is the latest entry of its kind, `fitdocs check` shall list it with the facts criterion 1 names and the remedy: record your own value to override it, or leave it to accept it.
4. When a later entry of the same kind exists, whether recorded by hand or derived, `fitdocs check` shall no longer list that takeover; the takeover shall remain visible in the timeline.
5. When the athlete records a hand value dated after a takeover, that value shall apply from its own date by the ordinary selection rule, and the heart-rate stage shall treat it under Requirement 5.

### Requirement 7: Provenance and Citations
**Objective:** As an athlete reading my own `athlete.toml`, I want every
derived heart-rate entry to say how it was worked out and from what, so that
I can check it against my own recordings and correct it by hand.

#### Acceptance Criteria
1. The heart-rate stage shall write on every derived entry a provenance record naming a derived origin, the method from a closed, published vocabulary, the document it read, the inputs it used, and the key of the source record that governs the method.
2. For a derived maximum heart rate, the heart-rate stage shall name as the document the page of the session whose sustained peak is the median of the three highest, and shall name in the inputs the window, the number of sessions in it and the three peaks used.
3. For a derived resting heart rate, the heart-rate stage shall name as the document the wellness series file that holds the entry's date, shall name the source and the metric as a series reference, and shall name in the inputs the window, the number of daily values in the baseline and the confirmation days.
4. The fitdocs athlete store shall accept an optional series reference in a benchmark entry's provenance record, shall require it to be a non-empty string when present, shall carry it through every rewrite, and shall keep accepting a provenance record without one.
5. The fitdocs athlete store shall keep reading, unchanged, every entry an earlier release wrote, and an earlier release reading an entry this feature writes shall read it as a valid derived entry.
6. The fitdocs CLI shall bind every constant the heart-rate stage uses to exactly one governing source record that states how well the value was verified; a value no published work defines shall be recorded as fitdocs' own choice with its justification and what was measured, and a work whose text has not been read shall be recorded as such and named in a published set of tracked exceptions.
7. The fitdocs CLI shall carry no bare numeric literal for such a constant in the heart-rate stage's arithmetic, and shall treat every window, step and threshold as a constant rather than as configuration.

### Requirement 8: The Two Stages Never Erase Each Other
**Objective:** As an athlete with both tagged efforts and heart-rate
evidence, I want each stage of the command to manage only its own entries, so
that running either never removes what the other derived.

#### Acceptance Criteria
1. When the tagged-effort stage writes, it shall replace only derived entries of the kinds it derives (threshold pace, threshold heart rate and threshold power) and shall keep every derived resting- and maximum-heart-rate entry unchanged.
2. When the heart-rate stage writes, it shall replace only derived `resting_hr_bpm` and `max_hr_bpm` entries and shall keep every other derived entry unchanged.
3. Each stage shall write the athlete profile at most once per run, atomically, and only when its own derived entries change.
4. When a stage writes the profile, it shall preserve every hand-recorded entry, every key and table outside the benchmark entries, and every piece of content the benchmark reader ignores for forward compatibility.
5. If writing the profile would produce a document the profile reader would reject, the stage shall refuse the write with a message naming the target and the reason, and shall leave the file exactly as it was.
6. The tagged-effort stage shall continue to derive no resting or maximum heart rate.

### Requirement 9: Consistency Findings
**Objective:** As an athlete, I want to know when a derived resting or
maximum heart rate cannot describe me together with my other heart-rate
benchmarks, so that heart-rate load never silently stops for a reason I
cannot see.

#### Acceptance Criteria
1. `fitdocs check` shall report each period in which the maximum heart rate in force is not above the resting heart rate in force and at least one of the two is derived, naming the period, both values, their dates and which is derived.
2. `fitdocs check` shall report each period in which, for a discipline with a threshold heart rate in force, the resting heart rate in force is not below that threshold or the threshold is above the maximum heart rate in force, and at least one of the resting and maximum heart rates in force is derived, naming the period, the discipline and the three values with their dates.
3. When the heart-rate stage writes, or in preview mode would write, entries that produce a period criterion 1 or 2 describes, the fitdocs CLI shall report that period too.
4. If `athlete.toml` cannot be read, `fitdocs check` shall report one finding naming the file and the reason and shall still complete its other checks.
5. `fitdocs check` shall remain read-only and offline: it shall read `athlete.toml` and shall open no archived source and no wellness file for these findings.
6. The heart-rate stage shall never adjust, clamp or drop a derived value to avoid an inconsistency.

### Requirement 10: Training Load Reads Derived Entries Unchanged
**Objective:** As an athlete, I want heart-rate load to use derived values
exactly as it uses values I typed, and to say which dated values it used, so
that I can tell what a heart-rate load number rests on.

#### Acceptance Criteria
1. The fitdocs CLI shall pass a derived resting- or maximum-heart-rate entry to the threshold calculator as an ordinary dated entry, selected by the same rule as every other entry, with no change to the calculator's arithmetic, its channel selection or its prompts.
2. When the heart-rate channel computes a load, the inputs it reports shall name the resting and maximum heart rates it used and the measurement date of the entry each came from, alongside the values it already reports.
3. The impulse and reference values the heart-rate channel reports shall be the values that produced the load.
4. The heart-rate stage shall write no workout document; a document whose load was already computed shall keep it until the athlete recomputes load, and when a run changes the heart-rate timeline the fitdocs CLI shall say that recomputing load applies it.
5. The threshold calculator and the load channels shall import nothing the heart-rate stage adds, and shall estimate no threshold from activity data.
6. The heart-rate stage shall write no undated top-level `max_hr_bpm` or `resting_hr_bpm` key, and zones and the page's own TRIMP figure shall keep reading those keys exactly as today.
7. When the analytics index refreshes after a run, its existing benchmark tables shall list the derived heart-rate entries and their in-force periods under the unchanged selection rule, with no new table or column.

### Requirement 11: Documentation
**Objective:** As an athlete or agent, I want the derivation, its rules and
its announcements documented where I already look, so that I can predict
what a run will do to my timeline.

#### Acceptance Criteria
1. The README's benchmarks section and the configuration guide's athlete-profile section shall state that `derive-benchmarks` derives resting and maximum heart rate, from what evidence, with which windows and steps, and that a hand-recorded value wins under the rule of Requirement 5.
2. The published ownership contract's description of `derive-benchmarks` shall state what the command reads and writes, that it writes the athlete profile at most once per stage, and that it never modifies a hand-recorded entry; because that changes a stated guarantee, the contract shall carry a new contract version whose change note says so, restated in every in-tree ownership declaration.
3. The documentation shall state how a takeover is announced, how long `fitdocs check` lists it, how the athlete answers it, and how derived entries narrow a hand-recorded entry's applies-from back-reach.
4. The packaged workouts skill shall tell an agent how to read a takeover and an inconsistency finding and what to suggest to the athlete.
5. The release notes shall describe the heart-rate stage, the hand-recorded-wins rule, the new `check` findings, the need to recompute load to apply a changed timeline, and that on the first run historic heart-rate load before a hand-recorded entry's date moves to derived values where derived evidence exists.
6. The documentation and every test shall use synthetic values only and shall contain no value from the maintainer's own data.
