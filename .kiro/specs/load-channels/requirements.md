# Requirements Document

## Project Description (Input)

Compute-all/select-one needs something to compute. Three independent,
threshold-anchored load values — Power, HR, Pace — each computed from the sample
streams when there is enough data, and each honestly reporting insufficiency
when there is not.

"When there is not" is the hard part, and it is not hypothetical. Across the
athlete's 74 real files, HR coverage drops to 60%, 63%, 73%, 74%, 78% and 83% on
otherwise ordinary activities. Without an explicit sufficiency gate, a run with
60% HR coverage silently produces an HRSS computed over the 40% that is missing —
a confident number that is simply wrong. The same applies to a GPS-less run (one
exists, at 0% coverage with full power) and to the 7 of 9 rides carrying no
power at all.

There is also a sourcing defect to fix. `metrics/stress.py` implements Banister
TRIMP with the coefficients `0.64 · e^(1.92 · HRr)`, cited to
`docs/reference/fitdocs-ai-reference.md`. That exact formula string was
**refuted 0-3** in adversarial verification — not because the concept is wrong
(Banister is genuinely the HR-*reserve* variant with exponential weighting) but
because the coefficients trace to secondary web sources, not the literature.

Desired outcome: three channel functions, pure and I/O-free, each returning
either a load value with the inputs that produced it, or a typed insufficiency
reason — Power (Coggan NP → IF → TSS anchored to FTP, 1 h @ FTP = 100), HR
(Banister TRIMP → HRSS anchored to LTHR, 1 h @ LTHR = 100, coefficients sourced
from the primary literature and cited in code), and Pace (grade-adjusted pace
anchored to a threshold pace, same scale) — plus an explicit, configurable
sufficiency gate per channel expressed in terms the data actually varies on
(sample coverage of the required stream, and minimum duration). Every channel
must be verifiable against published worked examples, not only against itself.

Source: `.kiro/specs/load-channels/brief.md`; Phase 4 scope, discovery decisions
and boundary strategy in `.kiro/steering/roadmap.md`; upstream benchmark store
contract in `.kiro/specs/athlete-benchmarks/`.

## Introduction

load-channels is the second spec of the Phase 4 threshold load engine. It owns
**the arithmetic of a single training-load channel** and nothing else: given one
activity, one already-resolved threshold benchmark, and one resolved sufficiency
configuration, produce either a load value on the shared "one hour at threshold
= 100" scale, or a typed statement of why no honest value exists.

Three properties make that a feature rather than three formulas.

**Insufficiency is a first-class result, not an error.** A channel is asked to
score every activity it is offered, including the 7-of-9 rides with no power,
the run at 0% GPS coverage, and the ordinary sessions whose heart-rate strap
dropped to 60% coverage. In every one of those cases the correct answer is a
named reason, carrying the number that failed and the number it was measured
against — never a load of zero, never a value computed over the fraction of the
activity that was actually recorded and presented as if it covered all of it.

**The scale is the contract.** Power, heart rate and pace are three different
measurements of the same hour of work. What makes them comparable — and what
lets the downstream calculator select among them and the QA layer compare them —
is that all three are defined so that one hour at the athlete's threshold scores
exactly 100. That invariant is testable directly and is asserted per channel.

The scale contract has a second half that is easy to lose: the **intensity** the
channels report must carry one meaning too. Load and intensity are tied together
by `load = hours × intensity² × 100` on the power and pace channels, so the
heart-rate channel must report an intensity obeying the same relation rather
than the impulse *ratio*, which is that intensity squared and therefore agrees
with the other two channels at exactly one point — threshold itself. Anchoring
the comparison only at 1.0 cannot detect the difference, so the shared relation
is stated as its own invariant and verified at more than one intensity.

**Provenance is part of the number.** The refuted-coefficient episode is what
uncited constants cost. Every constant in this layer carries its source in code,
records whether that source was verified against primary text or only attested
by secondary literature, and — where fitdocs deviates from intervals.icu's
established behavior — carries the stated reason for the divergence.

This feature computes; it does not choose. Which channel wins, what a stale
benchmark means, what gets rendered, and where benchmarks come from are all
owned elsewhere.

## Boundary Context

- **In scope**: the three channel computations (power, heart rate, pace) and
  their shared result vocabulary; the data-sufficiency gate shared by all three
  and its user configuration; the conversion of a threshold pace into the speed
  the pace math needs; grade adjustment for the pace channel, including its
  behavior when altitude is missing or the terrain falls outside the published
  model's validated range; the substitutable seam through which the heart-rate
  channel obtains its intensity weighting; in-code sourcing and citation of
  every constant this feature introduces; and verification of each channel
  against a published worked example.
- **Out of scope**: choosing between channels — priority, fallback, arbitration
  and the calculator itself (threshold-load); the QA and divergence flags, the
  cadence-lock detection and the surfacing of benchmark staleness
  (activity-qa-flags); where benchmarks come from, how they are validated, and
  which one applies to a date (athlete-benchmarks); the load result contract, the
  document payload, frontmatter and rendered breakdown (the training-load
  update); mapping an activity's modality to a benchmark discipline
  (threshold-load); re-sourcing the shipped TRIMP coefficients (the fit-ingest
  update); any running-power model — Stryd RSS, GOVSS and Skiba are not
  implemented; a build-time power-calibrated heart-rate regression; a
  strength-training load number; and any aggregation of loads over time.
- **Adjacent expectations**: the benchmark store hands out per-discipline, dated
  benchmarks whose **unit is fixed by the quantity's name** — watts, beats per
  minute, seconds per kilometre — and performs no conversion; this feature
  converts pace to speed itself. The shipped settings file is read once per
  invocation, an absent settings file yields no configuration rather than an
  error, and the `[load]` table is co-owned: this feature extends the single
  existing reader rather than adding a second one, and unrecognized keys and
  sub-tables in that table are ignored so sibling features can land
  independently. The shipped derived-metric layer already computes normalized
  power, moving time and Banister TRIMP and is owned by fit-ingest; this feature
  consumes those definitions and changes none of them, so a later re-sourcing of
  the TRIMP coefficients moves the shipped metric and this feature's heart-rate
  load together. Absent data is reported as absent at every boundary, never as a
  fabricated zero.

## Requirements

### Requirement 1: One Honest Answer Per Channel

**Objective:** As a load-calculator author, I want every channel to return either
a load value or a named reason it could not produce one, so that I never have to
distinguish a real zero from a missing measurement.

#### Acceptance Criteria

1. The fitdocs load-channel layer shall provide exactly three channels — a power channel, a heart-rate channel, and a pace channel — each addressable by a stable identifier.
2. When a channel is asked to score an activity, the fitdocs load-channel layer shall return exactly one of two outcomes: a computed channel load, or an insufficiency report; it shall never return both and shall never represent an uncomputable channel as a load of zero.
3. When a channel returns a computed load, the fitdocs load-channel layer shall report alongside it the channel identifier, the load value, the intensity ratio relative to threshold, the anchoring benchmark's value and measurement date, the duration that was scored, the observed coverage of the required stream, and the ordered inputs that produced the value.
4. When a channel returns an insufficiency report, the fitdocs load-channel layer shall report the channel identifier, a reason drawn from a closed, enumerated set, a human-readable explanation, and — where the reason is a failed threshold — both the observed value and the value that was required.
5. The enumerated insufficiency reasons shall distinguish at least: no applicable anchoring benchmark; anchoring benchmarks that are individually valid but mutually inconsistent; a required stream that records no value at all; a required stream whose coverage is below the configured minimum; an activity shorter than the configured minimum duration; a channel model that is not defined for the activity's modality; and a required derived value that could not be computed from the data present.
6. The fitdocs load-channel layer shall define every channel so that an activity of exactly one hour spent entirely at the athlete's threshold for that channel scores exactly 100.
7. The fitdocs load-channel layer shall compute each channel independently, so that one channel's insufficiency neither suppresses nor alters another channel's result for the same activity.
8. The fitdocs load-channel layer shall not raise for absent, sparse, or unusable activity data; it shall report insufficiency instead.
9. If a caller supplies a benchmark whose quantity is not the one the channel anchors on, the fitdocs load-channel layer shall fail loudly as a programming error rather than computing a value from it.
10. The fitdocs load-channel layer shall produce an equal result for equal inputs on every invocation, and shall read no file, open no network connection, consult no clock, prompt for nothing, read no configuration of its own, and invoke no language model.
11. The fitdocs load-channel layer shall define one intensity semantic shared by all three channels: for every computed load, the reported load shall equal the scored duration in hours multiplied by the square of the reported intensity multiplied by one hundred, within a stated numeric tolerance, so that the reported intensity is dimensionless, is exactly 1.0 at threshold, and means the same thing on every channel.

### Requirement 2: The Data-Sufficiency Gate

**Objective:** As an athlete whose heart-rate strap sometimes drops out, I want a
load computed only when enough of the activity was actually recorded, so that a
number derived from 60% of a workout is never presented as if it described all
of it.

#### Acceptance Criteria

1. Before computing a load, the fitdocs load-channel layer shall evaluate a data-sufficiency gate over the stream that channel requires.
2. The fitdocs load-channel layer shall measure a stream's coverage as the proportion of the activity's recorded time during which that stream carries a recorded value, so that the measured coverage describes exactly the span the load itself is accumulated over.
3. The fitdocs load-channel layer shall measure coverage on the recorded samples as they were ingested, before any resampling, forward-fill, or gap substitution, so that a substituted value never counts as recorded data.
4. If the required stream carries no recorded value anywhere in the activity, the fitdocs load-channel layer shall report insufficiency with the stream-absent reason, distinct from the reason used for partial coverage.
5. If the required stream's coverage is below the configured minimum for that channel, the fitdocs load-channel layer shall report insufficiency naming the observed coverage and the configured minimum.
6. If the activity's recorded span is below the configured minimum duration, the fitdocs load-channel layer shall report insufficiency naming the observed duration and the configured minimum, and shall do so for every channel alike.
7. When the gate passes, the fitdocs load-channel layer shall still report the observed coverage and the observed duration on the computed result, so that a downstream consumer can surface how well-covered the number is.
8. The fitdocs load-channel layer shall apply one gating rule to all three channels, varying only in which stream is inspected and which configured thresholds apply.
9. If an activity carries fewer than two recorded samples, or its recorded samples span no time at all, the fitdocs load-channel layer shall report insufficiency rather than computing coverage or a load from it.
10. The fitdocs load-channel layer shall treat a recorded zero as recorded data and only an unrecorded value as missing, so that coasting at zero watts counts toward power coverage.

### Requirement 3: Sufficiency Configuration

**Objective:** As an athlete, I want the coverage and duration thresholds to be
settings rather than constants baked into the tool, so that I can tighten or
relax them to match how my devices actually record.

#### Acceptance Criteria

1. The fitdocs settings reader shall read the minimum stream coverage and the minimum activity duration from the data root's settings file, within the same `[load]` table the load layer already reads.
2. The fitdocs settings reader shall accept a per-channel override of the minimum stream coverage for each of the three channels, and shall apply the shared minimum to any channel that has no override.
3. If the settings file, the load table, the sufficiency settings, or any individual key is absent, the fitdocs settings reader shall use documented defaults and shall not treat the absence as an error.
4. If a configured minimum stream coverage is not a number, is a boolean, or does not lie above zero and at or below one, the fitdocs CLI shall fail with a configuration error naming the file, the key and the offending value.
5. If a configured minimum duration is not a whole number of seconds, is a boolean, or is zero or negative, the fitdocs CLI shall fail with a configuration error naming the file, the key and the offending value.
6. If the sufficiency settings are present but are not a table, the fitdocs CLI shall fail with a configuration error naming the file and the offending path.
7. The fitdocs settings reader shall extend the single existing reader of the load settings table rather than introducing a second reader of the same file, and shall continue to ignore keys and sub-tables it does not recognize.
8. When a load pass begins, the fitdocs CLI shall validate the sufficiency settings and, on a configuration error, terminate before any document is written or modified.
9. The fitdocs load-channel layer shall receive the resolved sufficiency configuration as an argument and shall not read, locate, or re-read any settings file itself.
10. The documented default minimum stream coverage shall match a published, citable coverage requirement from an established training platform rather than an invented figure, and the source of that default shall be recorded.

### Requirement 4: The Power Channel

**Objective:** As an athlete with a power meter, I want my ride and run power
scored the way the rest of the sport scores it, so that the number is comparable
to what every other platform reports.

#### Acceptance Criteria

1. The fitdocs power load channel shall compute a load from normalized power, an intensity factor relative to functional threshold power, and duration, following the published Coggan definitions.
2. The fitdocs power load channel shall anchor on the dated functional-threshold-power benchmark it is handed, and shall not read, derive, estimate, or default a threshold power of its own.
3. The fitdocs power load channel shall reuse the shipped normalized-power definition unchanged, including its rolling-average window, its treatment of the first seconds of the activity, and its gap handling, and shall not restate or re-derive that algorithm.
4. If no functional-threshold-power benchmark is supplied, the fitdocs power load channel shall report insufficiency with the no-benchmark reason and shall not substitute a default.
5. If normalized power or the scored duration cannot be derived from the data present, the fitdocs power load channel shall report insufficiency with the not-computable reason.
6. The fitdocs power load channel shall require the power stream and shall gate on that stream's coverage and the activity's duration.
7. The fitdocs power load channel shall compute for any modality that records power, including running, and shall record which discipline's threshold power anchored the result.
8. The fitdocs power load channel shall reproduce the published worked examples of the source methodology, and those examples shall be recorded with their source as verification cases.
9. The fitdocs power load channel shall compute running power from the watts the device recorded, and the documentation shall record that this diverges from intervals.icu — which does not ingest those fields natively — together with the reason.

### Requirement 5: The Heart-Rate Channel

**Objective:** As an athlete whose walks, hikes and power-less rides carry only
heart rate, I want those sessions scored on the same scale as my power sessions,
so that every trained hour is represented.

#### Acceptance Criteria

1. The fitdocs heart-rate load channel shall compute a load by normalizing the activity's training impulse against the training impulse of one hour spent entirely at the athlete's lactate threshold heart rate, expressed so that one such hour scores exactly 100.
2. The fitdocs heart-rate load channel shall require a lactate-threshold heart rate, a resting heart rate and a maximum heart rate, and shall report insufficiency naming which of them was absent when any is missing.
3. If the supplied heart-rate benchmarks are mutually inconsistent — in particular when the lactate threshold does not lie above the resting heart rate and at or below the maximum heart rate, or when the maximum does not exceed the resting rate — the fitdocs heart-rate load channel shall report insufficiency with the inconsistent-benchmarks reason and shall not compute a value.
4. The fitdocs heart-rate load channel shall obtain the activity's training impulse from the same single definition the shipped derived-metric layer uses, so that two different training-impulse computations cannot exist in the tool.
5. The fitdocs heart-rate load channel shall compute its one-hour-at-threshold reference through that same definition, so that the reference and the activity value can never be weighted differently.
6. The fitdocs heart-rate load channel shall not restate, re-derive, or alter the shipped training-impulse coefficients; re-sourcing them is out of this feature's scope, and the channel shall be constructed so that a later change to them changes the shipped metric and this channel's output consistently.
7. The fitdocs heart-rate load channel shall reach its heart-rate intensity weighting through a substitutable component, so that a later build-time power-calibrated regression can replace the fixed physiological weighting without a rewrite.
8. The fitdocs load-channel layer shall ship exactly one implementation of that component — the fixed physiological weighting — and shall provide no alternative implementation, no configuration key selecting one, and no unreachable code path anticipating one.
9. The fitdocs heart-rate load channel shall require the heart-rate stream and shall gate on that stream's coverage and the activity's duration.
10. The fitdocs heart-rate load channel shall be verified against a published worked example of the underlying training-impulse computation, and against the property that the computed load is unchanged by any rescaling of the weighting's multiplicative constant, so that the disputed constant cannot silently move the result.
11. The fitdocs heart-rate load channel shall report as its intensity the square root of the ratio between the activity's mean training-impulse rate and the training-impulse rate of one hour at threshold, so that its intensity obeys the shared relation between load and intensity rather than being that intensity squared; the reported load value shall be unaffected by how the intensity is reported, and the resulting divergence from intervals.icu — which publishes a heart-rate *load* definition and no heart-rate intensity definition — shall be recorded with its reason.

### Requirement 6: The Pace Channel

**Objective:** As a runner whose watch sometimes loses power data but never loses
distance, I want a load computed from pace on the same scale as the others, so
that a run is scored even when the power channel cannot score it.

#### Acceptance Criteria

1. The fitdocs pace load channel shall compute a load from grade-adjusted speed, an intensity ratio relative to the athlete's threshold speed, and the moving duration, expressed so that one hour at threshold pace scores exactly 100.
2. The fitdocs pace load channel shall convert the supplied threshold-pace benchmark from seconds per kilometre into the speed its arithmetic requires, and shall not expect the benchmark store to have converted it.
3. The fitdocs pace load channel shall anchor on the dated threshold-pace benchmark it is handed, and shall not derive, estimate, or default a threshold pace of its own.
4. If no threshold-pace benchmark is supplied, the fitdocs pace load channel shall report insufficiency with the no-benchmark reason.
5. The fitdocs pace load channel shall require the distance stream and shall gate on that stream's coverage and the activity's duration.
6. If the moving duration or the accumulated distance cannot be derived, or is not positive, the fitdocs pace load channel shall report insufficiency with the not-computable reason.
7. The fitdocs pace load channel shall be defined for the running modality only; given an activity of any other modality it shall report insufficiency with the model-not-defined reason naming that modality, and shall not decide whether some other channel should have been used instead.
8. The fitdocs pace load channel shall match intervals.icu's published pace-load formulation, including its use of moving time rather than elapsed time, and the documentation shall record every point at which it deviates and why.
9. The fitdocs pace load channel shall report the grade-adjusted speed and the threshold speed among the inputs that produced the value, so that the number can be checked by hand.

### Requirement 7: Grade Adjustment

**Objective:** As a runner on hilly terrain, I want uphill effort counted as the
harder work it is, so that a hill session is not scored as an easy run merely
because the pace was slow.

#### Acceptance Criteria

1. The fitdocs grade adjustment shall convert each recorded movement interval into an equivalent level-ground effort using a published energy-cost-of-running model, and shall cite that model and its coefficients in code.
2. The fitdocs grade adjustment shall derive the gradient of each interval from the recorded altitude and distance streams, smoothing the altitude before differencing it so that single-sample jitter does not create fictitious gradients.
3. The fitdocs grade adjustment shall apply the same smoothing width and alignment convention the shipped elevation metrics already use, so that the climb a document reports and the climb the load is adjusted for describe the same terrain.
4. If a gradient falls outside the published validated range of the energy-cost model, the fitdocs grade adjustment shall clamp it to that range rather than extrapolating the model, and shall record that clamping occurred.
5. If an interval's recorded distance is zero, negative, or too small for a gradient to be meaningful, the fitdocs grade adjustment shall treat that interval as level rather than producing an extreme gradient.
6. If the altitude stream is absent or its coverage is below the configured minimum, the fitdocs pace load channel shall compute the load from unadjusted pace, shall record on the result that grade adjustment was not applied and why, and shall not report insufficiency for that reason alone.
7. The fitdocs grade adjustment shall not alter the activity's reported distance, duration, or any other measured value; it shall affect only the intensity the pace channel computes.
8. The fitdocs grade adjustment shall be expressed as a unit separate from the threshold-anchoring arithmetic, so that the model can be replaced without touching the scale contract.
9. The fitdocs grade adjustment shall be defined for running only, and the documentation shall record that the walking form of the same published model, though it was read in the same source used for the running form, was not implemented — a scope decision, not a sourcing gap. _(amended 2026-07-27, queue 2026-07-26-citation-vocabulary-diverges-across-layers: the original wording said the walking form "was not obtained"; the re-sourcing of `MINETTI_2002` to `PRIMARY_TEXT` under criterion 8.9 read Fig. 1's caption, which gives both the running and the walking regressions together, so the walking form was in fact read alongside the running form. The criterion is corrected to state the true reason it is unimplemented — a scope choice, not unavailability — rather than leave a now-false sourcing claim standing.)_

### Requirement 8: Sourcing, Citation and Verification

**Objective:** As a reviewer of this codebase, I want every constant in the load
arithmetic to name its source and state how well that source was verified, so
that the refuted-coefficient episode cannot repeat silently.

#### Acceptance Criteria

1. The fitdocs load-channel layer shall carry, in code, at the point of definition, a citation for every numeric constant it introduces, naming the author or organization, the year, and the work.
2. The fitdocs load-channel layer shall record, alongside each citation, one of exactly three verification statuses — verified against the primary source's own text, attested only by secondary literature, or chosen by fitdocs and justified by a recorded measurement rather than by a published source — and shall never present a secondary attestation or a fitdocs-chosen value as a primary one. This feature introduces no constant of its own carrying the third status; the status exists so that a sibling feature's measured defaults can be recorded honestly through the same vocabulary rather than by extending it later. Criterion 8.9 narrows when the second status may be recorded at all.
3. The fitdocs load-channel layer shall not introduce a numeric constant without a citation and a stated verification status.
4. Each of the three channels shall be verified by at least one test that reproduces a worked example published by the source of its methodology, with the source, the input values and the expected result recorded in the test.
5. Where the fitdocs load-channel layer's behavior differs from intervals.icu's established behavior, the documentation shall record the divergence and the reason for it.
6. The fitdocs load-channel layer shall not restate the disputed training-impulse coefficients in its own code, and shall consume them from the single place they are already defined.
7. The fitdocs load-channel layer shall verify the shared intensity semantic across all three channels at more than one intensity — including at least one sub-threshold point at which an intensity defined as the impulse ratio and an intensity defined as its square root differ materially — so that a channel reporting a differently-scaled intensity is detected rather than coinciding with the others at threshold alone.
8. Each recorded citation shall be identifiable by a key unique within the recorded citations, and each recorded divergence shall be identifiable by a behavior name unique within the recorded divergences, so that a consumer can name one without ambiguity.
9. _(added 2026-07-27, queue 2026-07-26-citation-vocabulary-diverges-across-layers; amended 2026-07-27 on maintainer ruling, same queue item)_ The fitdocs load-channel layer shall hold itself to a **named-exception variant** of the bar fit-ingest Requirement 15.4 states for the layer beneath it, not the identical bar: where a published work defines a constant's value, the layer shall not record a *new* citation as attested only by secondary sources in place of a primary-text verification. Unlike 15.4, which blocks fit-ingest's completion outright for an unobtainable primary text with no exception set, this layer's criterion 8.10 permits an unobtainable primary text for such a constant to ship as an explicitly tracked, named exception rather than blocking this feature's completion — the maintainer ruling (2026-07-27) is that this residual difference is acceptable, so a constant in this state may ship recorded as `SECONDARY_ATTESTATION` while named in `BLOCKED_CITATIONS`. This criterion applies only where a defining published work exists; it does not require obtaining a primary text for a value no published work defines. _(The original wording said the layer "shall hold itself to the same bar" as 15.4 with no exception mentioned, which self-contradicted the tracked exception criterion 8.10 grants; corrected to describe the mechanism honestly rather than read as identical to 15.4.)_ _(Amended again 2026-07-29, queue 2026-07-27-banister-morton-primary-texts-obtained: `BANISTER_TRIMP`, this criterion's sole illustration since 2026-07-27, has been re-sourced to `PRIMARY_TEXT` — both Banister (1991) and Morton, Fitz-Clarke & Banister (1990) were obtained and read in full, retiring the premise that either text was unreachable. `BLOCKED_CITATIONS` is now the empty set. The criterion's mechanism is unchanged and stays live for the next citation that genuinely cannot be obtained; only the illustrative example is corrected here, since naming a specific citation that no longer occupies the exception would otherwise leave this requirement asserting something no longer true.)_
10. _(added 2026-07-27, queue 2026-07-26-citation-vocabulary-diverges-across-layers)_ Where the fitdocs load-channel layer records a citation as an exception under criterion 8.9, it shall also record what was searched for that citation's primary text and why the search did not succeed, so that the exception cannot be used to avoid obtaining a primary text that is in fact reachable. _(No citation currently occupies this exception as of 2026-07-29, queue 2026-07-27-banister-morton-primary-texts-obtained; the criterion's obligation applies the next time one does.)_

### Requirement 9: Feature Boundary

**Objective:** As the owner of the surrounding specs, I want this feature to stop
exactly at the channel arithmetic, so that selection policy, quality flags and
document output remain reviewable as separate decisions.

#### Acceptance Criteria

1. The fitdocs load-channel layer shall not select, rank, prioritize, or fall back between channels, and shall not decide which channel's value should be used.
2. The fitdocs load-channel layer shall not compute or emit any quality or divergence flag, any cadence-lock verdict, or any benchmark-staleness verdict.
3. The fitdocs load-channel layer shall not read, write, or render any document, frontmatter key, or machine-readable payload.
4. The fitdocs load-channel layer shall not resolve a benchmark from a file, a date, or a discipline; it shall consume the benchmarks it is handed.
5. The fitdocs load-channel layer shall not map an activity's modality to a benchmark discipline.
6. The fitdocs load-channel layer shall not implement a strength-training load, a modelled running-power estimate, or a build-time power-calibrated heart-rate regression.
7. The fitdocs load-channel layer shall not register a calculator, consult the calculator registry, or participate in calculator arbitration.
8. The fitdocs load-channel layer shall not change the shipped derived-metric definitions it consumes, so that no already-rendered metric value changes as a result of this feature.
