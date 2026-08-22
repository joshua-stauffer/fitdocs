# Requirements Document

## Project Description (Input)

fitdocs needs one training-load number per activity that means the same thing
across running, cycling and hiking, and that stays interoperable with
intervals.icu. The original design proposed fusing an HR load and a power load
per activity via a cross-correction step; the 2026-07-20 research pass killed
it — that synthesis has **no prior art in any product, paper, or open-source
implementation surveyed, intervals.icu included.** Every platform computes
single-channel loads and *selects one* with fallback.

The replacement is the better design: computing every channel and selecting one
satisfies the graceful-degradation requirement *by construction*. The athlete's
real data shows why selection has to be per-activity dynamic rather than a fixed
rule — 7 of 9 rides carry no power, one run has full power but no GPS, and HR
coverage collapses to 60% on some files. Whichever single channel you hardcode,
real activities exist that it cannot score.

This feature delivers a registered calculator, id `threshold`, that for each
activity computes every channel with sufficient data, selects exactly one by
**user-configured priority with fallback**, and returns the selected value
together with the non-selected channel values and the insufficiency reasons for
channels that could not be computed. Only the selected value is the activity's
load; the rest are diagnostics — persisted, clearly marked as not-the-load,
never silently averaged in. Supported modalities are Run, Ride, Walk and Hike;
strength training returns the honest unsupported outcome rather than a
computable-but-meaningless heart-rate load. Missing benchmarks route through the
existing prompt flow via declared athlete inputs — asked once, persisted, never
defaulted. When no channel has sufficient data, the outcome is a typed
insufficiency, not a load of zero.

With the withdrawn methodology withdrawn (training-load Amendment 2), this is
fitdocs' **first and only built-in calculator**, and therefore the spec on the
critical path for fitdocs computing any load at all.

Source: `.kiro/specs/threshold-load/brief.md`; Phase 4 scope, discovery
decisions, constraints and boundary strategy in `.kiro/steering/roadmap.md`;
upstream contracts in `.kiro/specs/athlete-benchmarks/`,
`.kiro/specs/load-channels/` and `.kiro/specs/training-load/` (Amendments 1,
2 and 3).

## Amendment 1 (2026-07-25): the cross-spec review round

A cross-spec review of the Phase 4 specs adjudicated five findings against this
spec; the user approved every ruling. All five are recorded here and carried
into design.md and tasks.md.

1. **The calculator contract gains a per-activity context**, rather than this
   feature parking configuration on the profile view. `training-load`
   Amendment 3 adds `LoadContext(activity_date, settings)` as a `compute`
   parameter, so `ProfileView` reverts to a pure benchmark-store view and sheds
   both `activity_date` and `staleness_window_days`. This feature no longer adds
   `ProfileView.load_settings`; it reads the activity date and the resolved
   `[load]` configuration from the context. Requirements 1.6, 4.1 and 5.3 are
   restated against the context; the previously recorded
   `staleness_window_days` redundancy is resolved upstream and no longer this
   feature's note to carry.
2. **The heart-rate intensity semantic changed upstream.** `load-channels` had
   defined heart-rate intensity as the impulse *ratio*, the square of the power
   and pace channels' intensity, so this feature's single `Intensity` input
   label meant two different things depending on which channel was selected.
   `load-channels` now reports `sqrt(impulse_ratio)` and states one intensity
   semantic — dimensionless, exactly 1.0 at threshold,
   `load == hours × intensity² × 100` on every channel. New criterion 8.11 pins
   that this feature records the intensity under one label precisely because the
   semantic is now shared.
3. **A coverage figure must name its basis.** `activity-qa-flags` Requirement 8
   established the rule after finding that the load layer's coverage is measured
   over recorded time while the workout document's own coverage table counts
   samples, and that the two differ under non-uniform sampling. The rule extends
   to this feature, whose coverage input lands in the same document; new
   criterion 8.12 pins it.
4. **`NotConfirmed` is renamed `NotComputed`** by `training-load` Amendment 3.
   This feature is its sole producer and the old name was withdrawn-
   methodology-era confirmation vocabulary. Engine routing is unchanged; only the identifier
   moves, and only design.md and tasks.md named it.
5. **The load pass asks a calculator whether it supports an activity** *before*
   the prompt flow, because declaring the catch-all modality to
   reach Walk and Hike also drew Rowing and Workout documents through the full
   interactive prompt flow before they were refused by sport. New criterion 2.7
   requires this feature to answer it from the supported-sport set; the existing
   sport check inside `compute` stays as defence in depth. *Repinned 2026-07-26,
   in place (design.md Amendment 2): the criterion's intent and its shipped
   behaviour are unchanged — only the mechanism moved. The question is asked
   through the module-level `supports_activity(calculator, activity)`, which
   reads a calculator's own optional, off-Protocol `supports`; the
   `LoadCalculator` Protocol declares no such member.* The related
   activity-blind `required_athlete_fields()` — which still asks a runner with
   no bicycle for a cycling threshold power — is a **known limitation** the user
   deferred, recorded in design.md rather than fixed here.

A sixth finding needed no change: this spec's "resolution never raises"
(Requirement 1.7) does not conflict with `athlete-benchmarks`' benchmark-age
computation raising on a future-dated benchmark, because this feature never
calls it — the only caller inside `compute` is `activity-qa-flags`' staleness
check, which guards the future-date case and degrades to not-assessed.

## Introduction

threshold-load is the third spec of the Phase 4 threshold load engine, and the
one that turns the other two into a number a document can carry. It owns
**policy**: which activities are in scope, which threshold anchors each of them,
which channel's value becomes the activity's load, and what happens to the
values that did not win.

It computes nothing itself. The per-channel arithmetic belongs to
`load-channels`, the benchmarks to `athlete-benchmarks`, and the result contract
and calculator arbitration to `training-load`. This feature is the thin,
reviewable layer between them, and three principles govern every requirement
below.

**Compute all, select one — permanently.** Every channel is computed for every
supported activity, and exactly one of them is the load. There is no fusion, no
average, no blend, no cross-correction, and no configuration that could produce
one. This is the design's load-bearing constraint, established by research
rather than preference, and it is stated here as an exclusion so that a later
change cannot introduce it by accident.

**The selection rule is the athlete's, not the tool's.** A hardcoded
`Power > Pace > HR` ordering was refuted in adversarial verification (split vote
1-2); running commonly prefers pace, and the athlete's own data contains
activities that only one specific channel can score. Priority is therefore
configured per discipline, with documented defaults and a fallback walk.

**A diagnostic is never the load.** The values that were computed and not
selected, and the reasons the rest could not be computed, are recorded next to
the selected value precisely because they are useful — for auditing a selection,
and for the divergence flag `activity-qa-flags` will build. They are never
averaged in, never substituted for an absent selected value, and never presented
as the activity's load.

## Boundary Context

- **In scope**: registration of the `threshold` calculator as fitdocs' built-in
  methodology; the set of activities it supports and the honest refusal of the
  rest; the mapping from an activity's sport to the discipline whose benchmarks
  anchor each of its channels, including the walk/hike case neither upstream
  spec owns; resolving each channel's benchmarks for the activity's own date;
  running every channel; the per-discipline channel-priority configuration, its
  documented defaults and its validation; the fallback walk that selects exactly
  one channel; assembling the selected value, the non-selected values with their
  reasons, and the inputs and notes that make a number checkable, into the load
  result the contract defines; the athlete inputs this calculator declares so
  the shipped prompt flow can collect them; and the honest outcomes when no
  channel can be computed.
- **Out of scope**: the per-channel arithmetic and its data-sufficiency gates
  (`load-channels`); the load result contract, the machine-readable payload,
  frontmatter, the rendered breakdown, the registry and the arbitration that
  decides which *calculator* runs (`training-load`); the benchmark store, its
  file format, its validation and its staleness computation
  (`athlete-benchmarks`); detecting the quality conditions behind any flag —
  cadence lock, cross-channel divergence, staleness surfacing
  (`activity-qa-flags`); weekly, cycle or block aggregation of loads; automatic
  threshold estimation of any kind (auto-FTP, eFTP); a strength-training load
  number; a modelled running power; and **any per-activity fusion, averaging,
  blending or cross-correction of channel values, permanently**.
- **Adjacent expectations**: the benchmark store hands out per-discipline dated
  benchmarks, distinguishes "none on file" from "none applicable on that date",
  and never falls back across disciplines or scopes — any cross-discipline
  borrowing is this feature's own explicit policy and must be reported as such.
  The activity's calendar date and the resolved load configuration reach a
  calculator on the per-activity context the contract supplies; the date is the
  local date the document is named from, not a value read from any clock or time
  zone this feature holds. The channel layer takes already-resolved benchmarks,
  returns either a computed channel load or one of a closed set of insufficiency
  reasons, never raises for absent or sparse data, reports every channel's
  intensity on one shared semantic — dimensionless, exactly 1.0 at threshold,
  and satisfying `load = hours × intensity² × 100` on every channel — measures
  the coverage it reports over recorded time rather than over sample counts, and
  is not defined for pace on any modality other than
  running. The load result contract carries exactly one value that counts plus
  non-selected values and quality flags, and a calculator supplies empty
  collections rather than placeholders when it has nothing to report; it also
  asks a calculator whether it supports a given activity before running the
  prompt flow for it. The
  settings file is read once per invocation and an absent file yields no
  configuration rather than an error; the load configuration table is co-owned
  by several sibling features, so this feature extends the single existing
  reader and adds no second one. This calculator is a built-in and must pass the
  same registration validation as any third-party plugin, needing no privilege a
  plugin author lacks.

## Requirements

### Requirement 1: The Threshold Calculator as fitdocs' Built-In Methodology

**Objective:** As an athlete who has synced workouts, I want fitdocs to ship a
working load methodology behind the same pluggable seam a third party would use,
so that documents carry a real number without me installing anything, and so
that the seam is proven by the tool's own calculator.

#### Acceptance Criteria

1. The fitdocs load layer shall register a built-in calculator addressed by the identifier `threshold`, carrying a human-readable methodology name.
2. The fitdocs threshold calculator shall satisfy the same registration validation every third-party calculator passes, and shall require no capability, privilege, or private interface that a third-party calculator author cannot use.
3. When the installed plugin inventory is listed, the fitdocs CLI shall report the threshold calculator as a built-in whose version is the installed fitdocs version.
4. When the same activity, the same benchmark data and the same configuration are supplied, the fitdocs threshold calculator shall produce an identical result on every invocation.
5. The fitdocs threshold calculator shall compute entirely from recorded activity data, stored benchmarks and stored configuration, and shall consult no network service, no clock, and no language model.
6. The fitdocs threshold calculator shall not read, locate, or re-read any configuration or profile file itself, and shall receive every configured value on the per-activity context the calculator contract supplies and every stored benchmark through the contract's profile view.
7. The fitdocs threshold calculator shall not raise for absent, sparse, malformed or unusable activity or athlete data, and shall return a typed outcome instead.

### Requirement 2: Supported Activities and the Honest Refusal of the Rest

**Objective:** As an athlete who also lifts and occasionally rows, I want fitdocs
to score the activities its methodology actually covers and to say plainly that
it does not cover the others, so that no document carries a number that means
nothing.

#### Acceptance Criteria

1. The fitdocs threshold calculator shall support running, cycling, walking and hiking activities.
2. When asked to score a strength-training activity, the fitdocs threshold calculator shall return the unsupported outcome naming the sport, and shall not compute a heart-rate-derived value for it.
3. When asked to score an activity of any sport other than running, cycling, walking or hiking, the fitdocs threshold calculator shall return the unsupported outcome naming that sport.
4. The fitdocs threshold calculator shall declare the movement modalities it covers so that the load pass can route an activity it does not cover to the honest unsupported state without invoking it.
5. Where the declared modality set is coarser than the supported sport set, the fitdocs threshold calculator shall return the unsupported outcome for the sports inside that modality it does not support, so that the sport set is authoritative.
6. The fitdocs threshold calculator shall determine support from the activity's normalized sport label alone, and shall not infer support from the presence or absence of any recorded data stream.
7. When the load pass asks whether a given activity is supported, the fitdocs threshold calculator shall answer from its supported sport set, so that an activity inside a declared modality but outside the supported sport set is refused before the athlete is prompted for any input, and shall still refuse that activity by sport if asked to compute it.

### Requirement 3: Mapping an Activity to the Disciplines That Anchor It

**Objective:** As an athlete whose walks and hikes have no thresholds of their
own, I want fitdocs to state which discipline's threshold it anchored each
channel to, so that those sessions are scored at all and I can see exactly what
the number was measured against.

#### Acceptance Criteria

1. The fitdocs threshold calculator shall resolve, for each channel of a supported activity, which discipline's benchmark anchors it, and shall not delegate that decision to the benchmark store.
2. The fitdocs threshold calculator shall anchor a running activity's channels on running benchmarks and a cycling activity's channels on cycling benchmarks.
3. When scoring a walking or hiking activity, the fitdocs threshold calculator shall anchor the heart-rate channel on that activity's own discipline benchmark when one is on file, and shall otherwise anchor it on the running discipline's benchmark.
4. Where a benchmark is anchored on a discipline other than the activity's own, the fitdocs threshold calculator shall record that substitution on the result, naming both disciplines.
5. The fitdocs threshold calculator shall provide no threshold-power and no threshold-pace anchor for walking or hiking activities, so that those channels report a missing anchor rather than a number scaled from a different form of movement.
6. The fitdocs threshold calculator shall anchor maximum and resting heart rate on the athlete-wide benchmarks, which carry no discipline.
7. The fitdocs threshold calculator shall report, for every computed channel, the anchoring benchmark's value, its measurement date and the discipline it was recorded under.

### Requirement 4: Resolving Benchmarks for the Activity's Own Date

**Objective:** As an athlete regenerating years of history across a change of
measurement hardware, I want each activity anchored to the threshold that was
current when it happened, so that a threshold measured in 2026 never rescales
2023 training.

#### Acceptance Criteria

1. The fitdocs threshold calculator shall request each benchmark for the activity's own local calendar date, as supplied by the calculator contract.
2. The fitdocs threshold calculator shall pass already-resolved benchmarks to the channel layer and shall not ask that layer to resolve, select, or date-scope a benchmark.
3. If the activity carries no local calendar date, the fitdocs threshold calculator shall treat every benchmark as unavailable and shall report the activity as not computed with a reason naming the absent date.
4. If a benchmark exists for the requested quantity and discipline but none applies on the activity's date, the fitdocs threshold calculator shall treat the anchor as unavailable and shall record a reason distinguishing that case from a benchmark that was never provided.
5. The fitdocs threshold calculator shall not substitute a default, an estimated, or a later-measured benchmark for an unavailable one.
6. When the same activity is scored twice against the same stored benchmarks, the fitdocs threshold calculator shall resolve the same benchmarks both times.

### Requirement 5: Computing Every Channel

**Objective:** As an athlete whose devices record different things on different
days, I want every channel evaluated on every activity, so that the selection is
made from what was actually recorded rather than from what was assumed.

#### Acceptance Criteria

1. For every supported activity, the fitdocs threshold calculator shall evaluate all three channels — power, heart rate and pace — regardless of which channel the configured priority prefers.
2. The fitdocs threshold calculator shall evaluate each channel independently, so that one channel's insufficiency neither suppresses nor alters another channel's outcome for the same activity.
3. The fitdocs threshold calculator shall supply each channel with the resolved sufficiency configuration carried on the per-activity context and shall not apply, restate, or override any sufficiency rule of its own.
4. The fitdocs threshold calculator shall carry each channel's reported outcome forward unmodified, and shall not round, rescale, clamp, or otherwise adjust a channel's computed load or intensity.
5. The fitdocs threshold calculator shall not combine, average, blend, weight, or cross-correct the values of two or more channels under any configuration.
6. The fitdocs threshold calculator shall preserve the channel layer's insufficiency reason for every channel that produced no value, so that the recorded reason is the one the channel actually reported.
7. Where a channel reports that it is not defined for the activity's modality, the fitdocs threshold calculator shall record that reason as reported and shall not treat it as an error.

### Requirement 6: Selecting Exactly One Channel

**Objective:** As an athlete, I want exactly one of the computed channels to be
my activity's load, chosen by a rule I set and can predict, so that my numbers
are stable and I can explain any of them.

#### Acceptance Criteria

1. The fitdocs threshold calculator shall select exactly one channel's computed load as the activity's load.
2. When selecting, the fitdocs threshold calculator shall walk the configured priority order for the activity's discipline and shall select the first channel in that order that produced a computed load.
3. If a channel earlier in the configured order produced no computed load, the fitdocs threshold calculator shall continue to the next channel in the order rather than abandoning the activity.
4. The fitdocs threshold calculator shall not select a channel that is absent from the configured priority order for that discipline, even when that channel produced a computed load.
5. The fitdocs threshold calculator shall base the selection only on the configured order and on whether each channel produced a value, and shall not compare, rank or prefer channels by the magnitude of their loads, their coverage, or their intensity.
6. When the selection is made, the fitdocs threshold calculator shall record which channel was selected and the configured order it was selected from.
7. If no channel in the configured order produced a computed load, the fitdocs threshold calculator shall report the activity as not computed rather than selecting a value from outside the order or reporting a load of zero.

### Requirement 7: Channel Priority Configuration

**Objective:** As an athlete, I want to set which channel counts for each of my
sports, so that my runs can be scored on pace and my rides on power without
editing code, and so that a bad setting fails loudly instead of quietly changing
my numbers.

#### Acceptance Criteria

1. The fitdocs settings reader shall read a per-discipline ordered list of channels from the load configuration table of the data root's settings file.
2. The fitdocs settings reader shall extend the single existing reader of that table rather than introducing a second reader of the same file, and shall continue to ignore keys and sub-tables it does not recognize.
3. If the settings file, the load table, the priority configuration, or an individual discipline's entry is absent, the fitdocs settings reader shall use the documented default order for that discipline and shall not treat the absence as an error.
4. The fitdocs settings reader shall document a default order for every supported discipline, and the default order for running, cycling, walking and hiking shall each name at least one channel.
5. If a configured priority entry names a discipline that is not a recognized sport, or a sport this calculator does not support, the fitdocs CLI shall fail with a configuration error naming the file, the offending name, and the supported disciplines.
6. If a configured priority entry names a channel that is not one of the three recognized channels, the fitdocs CLI shall fail with a configuration error naming the file, the key, the offending value, and the recognized channels.
7. If a configured priority entry is not a list of channel names, contains a repeated channel, or is empty, the fitdocs CLI shall fail with a configuration error naming the file, the key and the offending value.
8. When a load pass begins, the fitdocs CLI shall validate the priority configuration and, on a configuration error, terminate before any document is written or modified.
9. The fitdocs settings reader shall not reject a configured order that names a channel which can never produce a value for that discipline, and the resulting activities shall report that channel's reason as an ordinary insufficiency.

### Requirement 8: The Result — One Selected Value and Its Diagnostics

**Objective:** As a PKM user, I want the activity's load recorded together with
the values that were not selected and the reasons the rest were not computed, so
that I can audit any number without re-running the tool and can never mistake a
diagnostic for the load.

#### Acceptance Criteria

1. When a channel is selected, the fitdocs threshold calculator shall return the contract's computed result carrying the selected channel's load as the one value that counts.
2. The fitdocs threshold calculator shall record the selected channel's identity as the basis the value was derived from.
3. The fitdocs threshold calculator shall record every channel other than the selected one exactly once as a non-selected value, and shall not omit, duplicate, or merge any of them.
4. Where a non-selected channel produced a computed load, the fitdocs threshold calculator shall record that load together with a reason stating that a higher-priority channel was selected, or that the channel is absent from the configured order.
5. Where a non-selected channel produced no load, the fitdocs threshold calculator shall record no number for it and shall state the reason it reported, and shall never record a zero in place of an absent value.
6. The fitdocs threshold calculator shall record, among the inputs that produced the selected value, the selected channel's intensity relative to threshold, the anchoring benchmark's value and measurement date, the scored duration, and the observed coverage of the stream the channel required.
7. The fitdocs threshold calculator shall record explanatory notes for the facts that qualify a number without changing it, including a benchmark borrowed from another discipline and a channel note the channel layer itself reported.
8. The fitdocs threshold calculator shall emit no quality flags of its own, and shall record an empty flag set rather than a placeholder entry.
9. The fitdocs threshold calculator shall order the non-selected values, the inputs and the notes deterministically, so that two identical computations produce identical records.
10. The fitdocs threshold calculator shall never derive the selected value from, or adjust it by, any non-selected value or any recorded diagnostic.
11. The fitdocs threshold calculator shall record the selected channel's intensity under a single label that means the same thing whichever channel was selected, relying on the channel layer's one shared intensity semantic, and shall neither rescale an intensity nor qualify the label per channel.
12. The fitdocs threshold calculator shall name, on every coverage figure it records, the basis that figure was measured on, so that it is not read as the sample-count coverage percentage the workout document's own coverage table already displays.

### Requirement 9: Declared Athlete Inputs and Missing Benchmarks

**Objective:** As an athlete running a sync, I want fitdocs to ask once for a
threshold it needs and then use it forever, and to tell me plainly when a
threshold I have does not apply to an old activity, so that filling in my
benchmarks is a single conversation.

#### Acceptance Criteria

1. The fitdocs threshold calculator shall declare, as athlete inputs, the benchmark quantities and scopes its channels require in order to score a supported activity, so that the shipped prompt flow collects them without any calculator-specific prompting code.
2. The fitdocs threshold calculator shall not declare an optional benchmark that only refines an anchor it can already resolve, so that the athlete is never prompted for a threshold the tool does not need.
3. The fitdocs threshold calculator shall declare each benchmark input with a label, a valid range and help text stating what the value means and how it is measured.
4. If no channel produced a load and at least one channel was blocked by a declared benchmark that is not on file at all, the fitdocs threshold calculator shall return the missing-inputs outcome naming those declared inputs.
5. If no channel produced a load and the blocking benchmarks are on file but none applies to the activity's date, the fitdocs threshold calculator shall report the activity as not computed with a reason distinguishing that case from a benchmark that was never provided, and shall not report it as missing inputs.
6. While at least one channel produced a load, the fitdocs threshold calculator shall return the computed result and shall not report an unrelated absent benchmark as missing inputs.
7. The fitdocs threshold calculator shall not persist, request, or infer any athlete value itself, and shall not substitute a value for an input the athlete declined to provide.

### Requirement 10: Honest Outcomes When Nothing Can Be Computed

**Objective:** As a fitdocs user, I want an activity that cannot be scored to say
so and say why, so that an unscored workout is visibly unscored rather than
silently recorded as zero effort.

#### Acceptance Criteria

1. If no channel produced a computed load, the fitdocs threshold calculator shall return a typed outcome that carries no load value.
2. When reporting that nothing was computed, the fitdocs threshold calculator shall state a reason that names each evaluated channel and why that channel produced no value.
3. The fitdocs threshold calculator shall never return a computed result whose value was not produced by a selected channel.
4. The fitdocs threshold calculator shall never emit a load of zero, a default load, or a placeholder load for an activity it could not score.
5. When an activity that could not be scored is scored again after the missing data is supplied, the fitdocs threshold calculator shall compute it normally, so that a not-computed outcome is a retryable state rather than a terminal one.
6. The fitdocs threshold calculator shall report the same not-computed reason for the same inputs on every invocation.

### Requirement 11: Feature Boundary and Permanent Exclusions

**Objective:** As the owner of the surrounding specs, I want this feature to stop
exactly at selection policy, so that the channel arithmetic, the result carrier
and the quality flags remain reviewable as separate decisions and the rejected
fusion design cannot return.

#### Acceptance Criteria

1. The fitdocs threshold calculator shall implement no channel arithmetic, no data-sufficiency rule, and no grade-adjustment model of its own.
2. The fitdocs threshold calculator shall define no result type, no machine-readable payload, no frontmatter key, and no rendered output, and shall write and read no document.
3. The fitdocs threshold calculator shall not choose between calculators, consult the calculator registry, or participate in calculator arbitration.
4. The fitdocs threshold calculator shall not read, write, validate or migrate the benchmark store, and shall not compute a benchmark's staleness verdict.
5. The fitdocs threshold calculator shall detect no quality condition, including cadence lock, cross-channel divergence and benchmark staleness.
6. The fitdocs threshold calculator shall aggregate no load over time and shall estimate no threshold from activity data.
7. The fitdocs threshold calculator shall provide no configuration key, code path, or extension point by which channel values could be fused, averaged, blended or cross-corrected.
