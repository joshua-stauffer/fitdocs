# Requirements Document

## Project Description (Input)

A load number computed from bad data looks exactly like a load number computed
from good data. Three failure modes are detectable and currently invisible:
a wrist optical sensor reporting step cadence as heart rate (**cadence lock**),
sharp disagreement between the channel that was selected and the heart-rate
channel about how hard an activity was (**cross-channel divergence**), and a
threshold measured so long ago that a confident load is anchored to a benchmark
that may no longer have been valid (**threshold staleness**).

This spec is where the rejected per-activity fusion / cross-correction design's
*intent* actually lands. The 2026-07-20 research pass was clear that Efficiency
Factor and aerobic decoupling are established as **diagnostic signals — never a
load-combination step**, so the divergence becomes a flag on the record, not an
adjustment to the number.

`fitdocs/metrics/power.py` already ships both halves of the divergence signal:
`efficiency_factor` and `decoupling_pct`. They are computed and rendered as
ordinary derived metrics today, but nothing interprets them, compares them
against a reference, or attaches a verdict to the activity. Nothing detects
cadence lock. Nothing surfaces a benchmark's age.

Desired outcome: a flag layer that reads sample streams and channel outcomes and
emits typed verdicts — detected / not-detected / not-assessed, each carrying its
basis — attached to the load result and rendered into the document, never
modifying a load value. Flags degrade honestly: 17 of the athlete's 74 real
files carry **0% cadence**, and those must report "not assessed", never "no lock
detected", which would claim a check that did not happen. Detection thresholds
are configuration in `fitdocs.toml` `[load]`, not constants — they are the
tuning surface, and the false-positive regime is real.

Source: `.kiro/specs/activity-qa-flags/brief.md`; Phase 4 scope, discovery
decisions, constraints and boundary strategy in `.kiro/steering/roadmap.md`;
upstream contracts in `.kiro/specs/athlete-benchmarks/`,
`.kiro/specs/load-channels/`, `.kiro/specs/threshold-load/` and
`.kiro/specs/training-load/` (Amendments 1 and 2).

## Introduction

activity-qa-flags is the fourth and last spec of the Phase 4 threshold load
engine. It owns **verdicts about the data behind a load number, and nothing
about the number itself**. Its output is a set of typed quality flags that ride
in the result contract `training-load` defines, are rendered into the document's
training-load section, and are never projected into frontmatter and never
consulted by any arithmetic.

Three principles govern every requirement below.

**A flag is never a load combiner.** The research confirmed 3-0 that Efficiency
Factor and aerobic decoupling are diagnostic. Using either to adjust a load
value would reintroduce the fused metric the whole Phase 4 design rejects, so
this feature computes no load, alters no load, and provides no path by which a
verdict could reach a value.

**Not-assessed is a first-class state, distinct from a passed check.** The
project's standing rule is that absent data is `None`, never a fabricated `0`.
Its consequence here is sharper than usual: the absence of a *finding* and the
absence of a *check* are different facts and must be reported differently. A run
with no cadence stream has not been cleared of cadence lock; it has not been
examined. 17 of 74 real files are in exactly that position for the cadence
check, and every walk, hike and strength activity is in it for the decoupling
check.

**A verdict states its basis.** Every flag carries the measurements that
produced it — the observed figure, the configured threshold it was compared
against, and the span it was measured over — so a reader can disagree with the
threshold without re-running the tool, and so a reader can tell a marginal
verdict from an emphatic one.

## Amendments — 2026-07-25 cross-spec review

A cross-spec review of the four Phase 4 specs adjudicated five findings against
this document. All were approved. Each is applied below and each is recorded
here so the reasoning is not lost:

1. **Requirement 3.1's premise was false when it was written and is now true.**
   `load-channels` defined power and pace intensity as `value / threshold` but
   heart-rate intensity as the impulse *ratio* — the **square** of the other two
   for the same load, coinciding with them at exactly one point, 1.0 at
   threshold. Two channels reporting identical loads for the same hour therefore
   reported intensities 0.244 apart at 120 bpm and 0.188 apart at 140 bpm, so
   the divergence check as designed reported *detected* on easy aerobic sessions
   where the channels agreed perfectly, and *not-detected* near threshold where
   a real disagreement is most likely. `load-channels` Requirement 1.11 and 5.11
   now define **one** intensity semantic for all three channels — heart-rate
   intensity is the square root of the impulse ratio — so `load == hours ×
   intensity² × 100` holds on every channel within a stated tolerance. Req 3.1
   is restated against that invariant and Req 3.9 pins it with a sub-threshold
   regression case.
2. **The divergence tolerance's provenance was overstated.** `0.20` was chosen
   against the broken scale and was recorded as a measured value. It is not
   measured. Req 6.10 is extended and Req 6.11 added so an unvalidated default
   must say so and must name the measurement that would settle it. The ruling on
   the value itself is recorded in `design.md`.
3. **The import-cycle constraint is withdrawn, and the cycle behind it is cut
   upstream.** The constraint rested on `ProfileView.load_settings`, which
   `training-load` Amendment 3 removes in favour of a per-pass
   `LoadContext(activity_date, settings)` handed to `compute`. A different edge
   did survive that removal — `LoadContext.settings` keeps `load/types.py →
   load/settings.py` alive while `load/settings.py` must reach into this package
   for `FlagSettings` — and the review reproduced the resulting `ImportError` on
   every entry point. `training-load` cuts it at source with a
   `TYPE_CHECKING`-only import of `LoadSettings` in `src/fitdocs/load/types.py`,
   restoring that module's shipped "no imports from other `fitdocs.load.*`
   modules" invariant. This feature therefore ships an **ordinary eager**
   `src/fitdocs/load/qa/__init__.py` exporting `evaluate_flags`, with no lazy
   `__getattr__`, no import-order invariant and no import-order regression test;
   the staleness window is read from `context.settings` and the activity date
   from `context.activity_date`.
4. **The third verification status is no longer this feature's to add.**
   `load-channels` defines all three `VerificationStatus` members in its own
   task 1.1. This feature only *consumes* the measured status; it edits no
   module and no test module belonging to `load-channels`.
5. **Two brief corrections are carried into the spec text** so they cannot
   resurface: the "19 versus 241" cross-channel scoring anecdote could not be
   located in any published source and justifies nothing here (Req 3.10); and
   the brief's framing of Efficiency Factor as a signal in its own right is
   wrong — EF has no absolute reference point and its units differ by sport, so
   it enters only as a constituent of decoupling and as a stated basis, never as
   a verdict (Req 4.5).

## Amendment — 2026-09-16: retroactive anchors (`athlete-benchmarks` Amendment 1)

Queue item
`2026-09-10-activity-qa-flags-staleness-guard-neutralises-retroactive-anchors`.
`athlete-benchmarks` Amendment 1 (2026-09-10, under `training-load` Amendment
4 and the maintainer's 2026-08-29 ruling to extend the design to past dates)
lets the athlete declare, per entry, that a benchmark measured on the day they
answered a prompt also stands in for earlier activities (`applies_from`); the
store then resolves such an entry for an activity no earlier measurement
covers, and its staleness computation reports a **negative age and a current
verdict** for it instead of failing (its 4.6 revised). Its amendment record
names this feature: a negative age must be read as "measured after this
activity, applied by declaration", never as stale.

This document's Requirement 5 had been satisfied by a design that guarded the
ordering of the two dates before consulting the store and reported a violation
as *not-assessed*, on the premise that the store raised for it. That premise is
false now, and the guard would have reported *not-assessed* on precisely the
anchors the amendment exists to create — a first-time athlete's whole archive.
Criterion 5.8 is added so the retroactive case is a stated obligation rather
than a design accident: the check reports *not-detected* (it ran, and the
anchor is not stale) and its basis explains the later measurement date by the
athlete's own declaration. No criterion is revised, withdrawn or renumbered;
the Adjacent expectations paragraph below records the store's revised
behaviour.

## Boundary Context

- **In scope**: the flag vocabulary and its three verdicts, including the
  not-assessed state and the basis every verdict carries; cadence-lock detection
  from the temporal relationship between the recorded heart-rate and cadence
  streams; cross-channel divergence between the channel that became the
  activity's load and the heart-rate channel, together with the aerobic-drift
  diagnostic that explains it; surfacing the age and staleness of the benchmark
  that anchored the selected channel; the configuration of every detection
  threshold this feature introduces and its validation; attaching the flags to
  the computed load result; and the naming of any coverage figure this feature
  reports so it is not mistaken for the sample-count figure the document already
  displays.
- **Out of scope**: computing, adjusting, rounding, suppressing, replacing or
  re-deriving any load value, channel value, intensity or benchmark — this
  feature reads and reports only; the channel arithmetic and its
  data-sufficiency gates; channel selection, priority and fallback; the
  benchmark store, its file format, its validation, its date-aware selection and
  its staleness computation, all of which are consumed here and specified
  elsewhere; the definitions of the shipped efficiency-factor and
  aerobic-decoupling metrics, which are consumed unchanged; the result contract,
  the machine-readable payload, the frontmatter projection and the mechanics of
  section rendering; deciding what a flagged activity means for training, which
  the interpretation layer above this one does; quarantining, rejecting or
  excluding a flagged activity from anything; sensor-provenance detection
  (chest strap versus wrist optical), which the research could not substantiate;
  and heart-rate variability or recovery analysis.
- **Adjacent expectations**: the result contract carries quality flags as a
  possibly-empty collection of verdicts, each with a key, a display label, one
  of exactly three verdict values and a non-empty detail string, and it carries
  them **without altering the load value**; flags appear in the document's
  training-load section and its machine-readable record, and are deliberately
  absent from frontmatter. The channel layer reports, for every channel it
  computed, an intensity that is dimensionless, is exactly 1.0 at threshold on
  **all three channels alike**, and obeys one shared relation to the load it
  accompanies — the load equals the scored hours multiplied by the square of
  that intensity multiplied by one hundred, within a stated numeric tolerance —
  so that two channels reporting the same load for the same duration report the
  same intensity at *every* effort rather than only at threshold; that
  comparability is what makes a cross-channel divergence verdict meaningful, and
  this feature depends on it. The channel layer also reports a closed set of insufficiency
  reasons for channels it could not compute, and its coverage figure is measured
  over the recorded time span rather than by counting samples. The calculator
  evaluates the heart-rate channel on **every** supported activity even when
  another channel wins, which is what makes the divergence comparison available;
  that is a deliberate commitment of the calculator's design, not an incidental
  side effect. The benchmark store already computes a benchmark's age in days
  against the activity's own date and the configured window, and already
  reports whether that age exceeds the window; this feature surfaces that
  computation and does not repeat it. Since `athlete-benchmarks` Amendment 1
  the store may resolve, for an activity that no earlier-measured entry
  covers, an entry the athlete declared to apply from an earlier date; it
  returns that applies-from date alongside the measurement date, and its age
  computation then reports a negative age and a current verdict rather than
  failing. The tool itself never applies a later measurement on its own, so a
  negative age reaching this feature is always the athlete's declaration. The
  calculator receives the activity's
  calendar date and the resolved load configuration through a per-pass context
  value the load layer hands to `compute`, rather than through the athlete
  profile view, which is a pure store view; this feature reads both from that
  context and constructs neither. The settings file is read once per
  invocation, an absent file yields no configuration rather than an error, and
  the load configuration table is co-owned by several sibling features, so this
  feature extends the single existing reader and adds no second one.

## Requirements

### Requirement 1: The Flag Vocabulary and Its Three Verdicts

**Objective:** As a fitdocs user reading a workout document, I want every quality
check to report one of exactly three outcomes with the basis behind it, so that
I can tell a clean bill of health from a check that never ran.

#### Acceptance Criteria

1. The fitdocs quality-flag layer shall produce, for an activity whose load was computed, a set of quality verdicts in which each verdict names the check it reports on, a display label, exactly one of the verdict values *detected*, *not-detected* or *not-assessed*, and a human-readable basis.
2. The fitdocs quality-flag layer shall use *detected* only when the check ran to completion and the condition it looks for was found, *not-detected* only when the check ran to completion and the condition was not found, and *not-assessed* whenever the check could not run to completion.
3. The fitdocs quality-flag layer shall never report *not-detected* for a check whose required input was absent, insufficient, or undefined for the activity.
4. When a verdict is *detected* or *not-detected*, the fitdocs quality-flag layer shall state in the basis the observed figure, the configured threshold it was compared against, and the span or population the figure was measured over.
5. When a verdict is *not-assessed*, the fitdocs quality-flag layer shall state in the basis which input was missing or which precondition was unmet, and shall state no observed figure that was not actually measured.
6. The fitdocs quality-flag layer shall emit a verdict for every check it defines whenever a load result is produced, so that a check's absence from the record is never how a reader learns it was not applicable.
7. The fitdocs quality-flag layer shall emit verdicts in a fixed order that does not depend on the activity, the configuration, or which verdicts were reached, so that two identical computations produce identical records.
8. The fitdocs quality-flag layer shall express every basis without a fabricated zero, a default, or a placeholder standing in for a value that was not measured.
9. The fitdocs quality-flag layer shall produce an equal set of verdicts for equal inputs on every invocation, and shall read no file, open no network connection, consult no clock, prompt for nothing, read no configuration of its own, and invoke no language model.
10. The fitdocs quality-flag layer shall not raise for absent, sparse, or unusable activity, channel or benchmark data, and shall report *not-assessed* instead.

### Requirement 2: Cadence-Lock Detection

**Objective:** As a runner whose watch sometimes reports my step rate as my heart
rate, I want fitdocs to tell me when the recorded heart rate tracked cadence in
lock step, so that I know a heart-rate-derived number for that run is fiction.

#### Acceptance Criteria

1. The fitdocs cadence-lock check shall evaluate the *temporal* relationship between the recorded heart-rate stream and the recorded cadence stream over the course of the activity, and shall not decide from a single-point comparison of average or instantaneous values.
2. The fitdocs cadence-lock check shall require both a sustained statistical association between the two streams and a sustained numerical closeness between them, and shall report *detected* only when both conditions hold together over at least the configured minimum lock duration.
3. The fitdocs cadence-lock check shall compare heart rate against the cadence stream expressed as full movement cycles per minute, so that a cadence recorded per limb is not compared against heart rate at half its true rate.
4. The fitdocs cadence-lock check shall evaluate the association and the closeness over successive spans of a configured width rather than over the whole activity at once, so that a lock affecting part of an activity is detectable and a whole-activity average cannot mask or manufacture one.
5. When the conditions hold over one or more spans whose combined duration is below the configured minimum lock duration, the fitdocs cadence-lock check shall report *not-detected* and shall state the combined duration observed and the minimum required.
6. If the activity records no cadence value anywhere, the fitdocs cadence-lock check shall report *not-assessed* naming the absent stream, and shall never report *not-detected*.
7. If the proportion of the activity for which heart rate and cadence were both recorded is below the configured minimum, or no span of the configured width can be formed, the fitdocs cadence-lock check shall report *not-assessed* naming the observed proportion and what was required.
8. The fitdocs cadence-lock check shall be defined for running activities only; for an activity of any other movement modality it shall report *not-assessed* naming that modality, and the documentation shall record why the check is not defined there.
9. The fitdocs cadence-lock check shall report *not-detected* on an activity whose heart rate and cadence rise and fall together as a genuine consequence of effort, so that correlated effort at high intensity is not reported as a sensor artifact.
10. The fitdocs cadence-lock check shall determine its verdict from the recorded samples as they were ingested, without resampling, forward-filling, interpolating or substituting a value for an unrecorded one.
11. The fitdocs cadence-lock check shall be verified by tests over constructed streams that exhibit lock and over constructed streams that reproduce the statistics measured on the athlete's real activity corpus, and the documentation shall record that measurement, the false-positive headroom it establishes for each default, and the fact that the corpus itself never enters the repository.

### Requirement 3: Cross-Channel Divergence

**Objective:** As an athlete, I want to know when the channel that scored my
activity and my heart rate disagree sharply about how hard it was, so that I can
tell whether I am looking at a fitness change, a pacing problem, or a bad sensor.

#### Acceptance Criteria

1. The fitdocs divergence check shall compare the intensity the selected channel reported against the intensity the heart-rate channel reported for the same activity, using the single dimensionless threshold-relative intensity semantic the channel layer defines for all three channels — the one under which the reported load equals the scored hours multiplied by the square of the reported intensity multiplied by one hundred, so that two channels agreeing about how hard an activity was report equal intensities at every effort and not merely at threshold.
2. The fitdocs divergence check shall report *detected* when the magnitude of the difference between the two intensities exceeds the configured tolerance, and *not-detected* when it does not.
3. When reporting *detected* or *not-detected*, the fitdocs divergence check shall state both intensities, the difference between them, and the configured tolerance.
4. The fitdocs divergence check shall compare intensities and shall not compare, average, blend, reconcile or substitute the channels' load values.
5. While the heart-rate channel is the channel that was selected, the fitdocs divergence check shall report *not-assessed* stating that there is no second channel to compare against, and shall not compare the channel with itself.
6. If the heart-rate channel produced no value for the activity, the fitdocs divergence check shall report *not-assessed* carrying the reason the heart-rate channel itself reported, and shall never report *not-detected*.
7. The fitdocs divergence check shall report a verdict without altering, qualifying, re-deriving or suppressing either channel's value or the activity's load.
8. The fitdocs divergence check shall be evaluated for every supported activity whose load was computed, regardless of which channel the configured priority preferred.
9. The fitdocs divergence check shall be verified by a regression case in which the selected channel and the heart-rate channel report the same load for the same scored duration at an effort **materially below threshold**, and shall report *not-detected* for it, so that a channel whose intensity is reported on a different scale is detected by the check's own tests rather than coinciding with the others at threshold alone.
10. The documentation shall record that the cross-channel scoring anecdote quoted in the feature brief could not be located in any published source, that it is cited nowhere in this feature's design, code or tests, and that no default or verdict depends on it.

### Requirement 4: Aerobic Drift as the Corroborating Diagnostic

**Objective:** As an athlete, I want the established aerobic-decoupling figure
turned into a verdict against its published reference point, so that the
diagnostic fitdocs already computes tells me something instead of sitting on the
page as a bare number.

#### Acceptance Criteria

1. The fitdocs aerobic-drift check shall consume the aerobic-decoupling percentage the shipped derived-metric layer already computes, and shall not restate, re-derive or alter that definition.
2. The fitdocs aerobic-drift check shall report *detected* when the decoupling percentage exceeds the configured reference point and *not-detected* when it does not, and shall state the observed percentage and the reference point it was compared against.
3. The documented default reference point shall be the published figure below which an activity is conventionally described as well-coupled, and its source shall be recorded; where fitdocs' comparison differs from the established platform behavior in any respect, the documentation shall record the divergence and the reason for it.
4. If the aerobic-decoupling percentage is unavailable for the activity, the fitdocs aerobic-drift check shall report *not-assessed* naming why it was unavailable, and shall never report *not-detected*.
5. The fitdocs quality-flag layer shall report the efficiency factor as a stated part of a verdict's basis where it is available, and shall not turn the efficiency factor into a verdict of its own; the documentation shall record that it carries no absolute reference point and that its units differ by sport, so a single activity's value admits no threshold, and shall record that the feature brief's framing of the efficiency factor as a signal in its own right is therefore withdrawn — it enters this feature only as a constituent of the decoupling percentage and as a stated basis, never as a verdict.
6. The fitdocs aerobic-drift check shall report a verdict without altering or adjusting the activity's load, any channel value, or the decoupling metric the document already renders.
7. The fitdocs aerobic-drift check shall report the same verdict for the same activity whether or not any other check reached a verdict.

### Requirement 5: Threshold-Staleness Surfacing

**Objective:** As an athlete, I want a load number to carry the age of the
threshold behind it, so that a confident-looking figure anchored to an eight
month old test says so.

#### Acceptance Criteria

1. The fitdocs staleness check shall report on the benchmark that anchored the channel whose value became the activity's load, and shall not report on a benchmark that anchored a channel that was not selected.
2. The fitdocs staleness check shall obtain the benchmark's age in days, the window it was compared against, and whether that age exceeds the window from the computation the benchmark store already performs, and shall not compute, re-derive or restate any of them.
3. The fitdocs staleness check shall report *detected* when the anchoring benchmark's age exceeds the configured window and *not-detected* when it does not, and shall state the measurement date, the age in days, and the window.
4. The fitdocs staleness check shall evaluate age against the activity's own calendar date rather than the current date, so that regenerating an old document produces the verdict the original run produced.
5. If the activity's load was computed without an anchoring benchmark carrying a measurement date, the fitdocs staleness check shall report *not-assessed* naming what was absent.
6. The fitdocs staleness check shall report a verdict without altering, suppressing or adjusting the benchmark value or the load derived from it.
7. The fitdocs staleness check shall use the same staleness window the benchmark store is configured with, and shall not introduce a second window or a second default.
8. _(added 2026-09-16, retroactive-anchor amendment)_ When the anchoring benchmark's measurement date falls after the activity's date — which the benchmark store reports as a negative age, and which its selection yields only for an entry the athlete declared to apply from a date on or before the activity's — the fitdocs staleness check shall report *not-detected*, shall state the measurement date, how many days after the activity it falls, the applies-from date the athlete declared (or that the anchor carries none) and the window, and shall not report the benchmark as stale, shall not report the check as *not-assessed* on the ordering of the two dates, and shall not treat that ordering as an error.

### Requirement 6: Flag Threshold Configuration

**Objective:** As an athlete, I want every detection threshold to be a setting
rather than a constant baked into the tool, so that I can tune a check that
fires too readily or not readily enough without editing code.

#### Acceptance Criteria

1. The fitdocs settings reader shall read this feature's detection thresholds from the load configuration table of the data root's settings file, in a sub-table of its own.
2. The fitdocs settings reader shall extend the single existing reader of that table rather than introducing a second reader of the same file, and shall continue to ignore keys and sub-tables it does not recognize.
3. If the settings file, the load table, this feature's sub-table, or any individual key within it is absent, the fitdocs settings reader shall use documented defaults and shall not treat the absence as an error.
4. The fitdocs settings reader shall accept configuration for the cadence-lock association strength, the cadence-lock numerical closeness, the span width, the minimum lock duration, the minimum paired coverage, the divergence tolerance, and the aerobic-drift reference point.
5. If a configured threshold is not a number, is a boolean, or falls outside the range its quantity admits, the fitdocs CLI shall fail with a configuration error naming the file, the key, the offending value and the admissible range.
6. If this feature's settings are present but are not a table, the fitdocs CLI shall fail with a configuration error naming the file and the offending path.
7. When a load pass begins, the fitdocs CLI shall validate this feature's settings and, on a configuration error, terminate before any document is written or modified.
8. The fitdocs quality-flag layer shall receive the resolved threshold configuration as an argument and shall not read, locate, or re-read any settings file itself.
9. The fitdocs settings reader shall not read a staleness window of its own, and the staleness check shall use the window the benchmark store's configuration already defines.
10. Each documented default shall carry, in code at the point of definition, its source and whether that source is a published figure or a value fitdocs chose, and where fitdocs chose it, the measurement or reasoning that justifies it; a default justified by neither a published figure nor a recorded measurement shall be recorded as provisional in a form a test can check, naming the reasoning that produced it and the measurement that would settle it, and shall not be recorded as measured.
11. The documented default divergence tolerance shall be recorded as provisional, because the measured activity corpus contains no activity for which two channels both computed a value and therefore establishes no agreement distribution to set a tolerance against; the documentation shall state the reasoning behind the shipped value under the shared intensity semantic, shall state that the value was originally chosen against a heart-rate intensity scale that has since been corrected, and shall name the measurement that would replace the reasoning with evidence.

### Requirement 7: Attaching Flags to the Load Result

**Objective:** As a PKM user, I want the flags recorded alongside the load in the
document, so that the quality of a number travels with the number and survives
regeneration without recomputation.

#### Acceptance Criteria

1. When a load is computed for a supported activity, the fitdocs load layer shall attach the quality verdicts to the computed result the contract defines.
2. The fitdocs quality-flag layer shall attach flags without changing the load value, the selected channel, the non-selected values, the inputs recorded, or any other field of the result.
3. Where no load was computed for an activity, the fitdocs load layer shall attach no quality verdicts, so that a flag never appears without a number it qualifies.
4. The fitdocs quality-flag layer shall not introduce a frontmatter key, and the verdicts shall not appear in document frontmatter.
5. The fitdocs quality-flag layer shall not define, extend or version the result contract, the machine-readable record, or the rendering of the training-load section, and shall consume all three as they are defined elsewhere.
6. When the same activity, the same benchmark data and the same configuration are supplied, the fitdocs load layer shall attach an identical set of verdicts on every invocation, so that a regenerated document is byte-identical to the original.
7. The fitdocs quality-flag layer shall derive every verdict from the typed channel outcomes and recorded samples the calculator holds, and shall not re-derive a verdict from a rendered or formatted representation of a result.

### Requirement 8: Coverage Figures and Their Basis

**Objective:** As a reader comparing the coverage figure in the load section
against the coverage table in the same document, I want to know why they differ,
so that I do not conclude one of them is wrong.

#### Acceptance Criteria

1. Where the fitdocs quality-flag layer reports a coverage or proportion figure, it shall name the basis on which that figure was measured and the span it covers.
2. The fitdocs quality-flag layer shall not present a figure it reports as equivalent to the per-channel coverage percentage the workout document's own coverage table displays.
3. The documentation shall record that the load layer's coverage figure is measured over recorded time while the document's coverage table counts samples, that the two can differ under non-uniform sampling, and that both are correct for their own purpose.
4. The fitdocs quality-flag layer shall not modify, relabel or replace the workout document's existing coverage table.

### Requirement 9: Feature Boundary and Permanent Exclusions

**Objective:** As the owner of the surrounding specs, I want this feature to stop
exactly at reporting verdicts, so that the rejected fusion design cannot return
through the diagnostic door and the load engine remains reviewable separately.

#### Acceptance Criteria

1. The fitdocs quality-flag layer shall compute no training load, no channel value, no intensity, no benchmark and no aggregate of any of them.
2. The fitdocs quality-flag layer shall provide no configuration key, code path, or extension point by which a verdict, an efficiency factor, a decoupling percentage or a channel intensity could modify a load value.
3. The fitdocs quality-flag layer shall not select, rank, re-select or override the channel the calculator selected.
4. The fitdocs quality-flag layer shall not read, write, validate or migrate the benchmark store, and shall not resolve a benchmark for a date.
5. The fitdocs quality-flag layer shall not quarantine, reject, exclude, or mark an activity as unusable, and shall not omit an activity from any output on the basis of a verdict.
6. The fitdocs quality-flag layer shall not detect sensor provenance, distinguish a chest strap from a wrist optical sensor, or infer the device behind a stream.
7. The fitdocs quality-flag layer shall not analyze heart-rate variability or recovery, and shall not aggregate verdicts over time.
8. The fitdocs quality-flag layer shall not change the shipped derived-metric definitions it consumes, so that no already-rendered metric value changes as a result of this feature.
9. The fitdocs quality-flag layer shall register no calculator, consult no calculator registry, and participate in no calculator arbitration.
