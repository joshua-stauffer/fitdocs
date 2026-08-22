# Research & Design Decisions — activity-qa-flags

## Summary

- **Feature**: `activity-qa-flags`
- **Discovery Scope**: Extension (integration-focused) of the Phase 4 threshold
  load engine — new stream analysis, no new subsystem.
- **Key Findings**:
  1. **fitdocs records FIT `cadence` verbatim, and for running that field is
     per-limb.** Measured over the athlete's 74 real files: the median recorded
     cadence on runs is 83–90, while HR medians run 88–172. Comparing HR against
     the recorded cadence number directly would be wrong by a factor of two; the
     comparable quantity is `2 × cadence_rpm` (steps per minute), which is the
     165–185 band the cadence-lock literature actually describes.
  2. **The real corpus contains no cadence lock.** Whole-activity Pearson
     correlation between HR and steps/min peaks at **0.605** across all files
     (median 0.157 over 40 assessable runs). Under the conjunctive detection rule
     this design adopts, the worst false-positive accumulation on the entire real
     corpus is **137 s in a single 120 s window**. The corpus is therefore the
     *negative* evidence base; positive cases must be constructed.
  3. **No published retrospective cadence-lock detector exists.** The PPG
     literature (TROIKA, SpaMA) solves real-time HR *estimation* with an onboard
     accelerometer, not after-the-fact detection from a recorded FIT file. This
     detector is original design work and every one of its defaults is fitdocs'
     own, justified by measurement rather than citation.
  4. **17 of 74 real files carry 0% cadence** (10 runs, 7 workout/strength
     files), and `efficiency_factor` / `decoupling_pct` are `None` for every
     walk, hike and strength file and for 8 of 10 rides. Not-assessed is the
     *majority* verdict on several checks, not an edge case.
  5. **No training platform surveyed distinguishes "not assessed" from "checked
     and clean".** Strava's flag is a leaderboard-eligibility verdict;
     intervals.icu, TrainingPeaks/WKO expose *correction* tools, not stored
     verdicts. The three-verdict vocabulary fixed by `training-load` has no prior
     art to copy — which is a reason to state the design rationale, not a reason
     to doubt it.

## Research Log

### fitdocs' shipped efficiency-factor and decoupling definitions

- **Context**: The brief instructs reuse of the shipped `efficiency_factor` and
  `decoupling_pct` rather than recomputation. Reuse is only safe once their exact
  semantics — and their divergence from intervals.icu — are known.
- **Sources Consulted**: `src/fitdocs/metrics/power.py` (lines 155–249);
  `src/fitdocs/metrics/types.py` (`DerivedMetrics`);
  TrainingPeaks Help Centre, *Aerobic Decoupling (Pw:Hr and Pa:HR) and Efficiency
  Factor (EF)*; intervals.icu forum thread *Aerobic decoupling calculation
  question*; intervals.icu decoupling feature page.
- **Findings**:
  - Shipped `efficiency_factor(activity, np_w)` = normalized power ÷ average HR
    for `Modality.BIKE`, and (average speed m/s × 60) ÷ average HR for
    `Modality.RUN`. Every other modality returns `None`.
  - Shipped `decoupling_pct(activity)` splits at the **elapsed-time midpoint**
    (`mid = t[0] + (t[-1] - t[0]) / 2`), computes `mean(output) / mean(HR)` over
    paired samples per half, and returns `(ef1 - ef2) / ef1 × 100`. The output
    channel is raw **power** for bike and raw **speed** for run.
  - intervals.icu's published formula is the same ratio-of-halves expression,
    but the halves are split at the **sample-index midpoint** and the numerator
    is raw average power. TrainingPeaks' EF, by contrast, uses **normalized**
    power and **normalized graded** pace.
  - Consequence: fitdocs' own EF (NP-based on the bike) and fitdocs' own
    decoupling (raw-power-based on the bike) do not share a numerator. That is a
    pre-existing inconsistency in a fit-ingest-owned module.
  - intervals.icu additionally documents a distinct **"Seiler Decoupling"**
    using 60 s moving averages expressed as % of heart-rate reserve and power
    reserve. fitdocs implements neither variant of that.
- **Implications**: This feature consumes both metrics **verbatim from
  `DerivedMetrics`** and changes neither (Req 4.1, 9.8). Four divergences from
  intervals.icu are recorded with stated reasons in `design.md`; three of the
  four are fit-ingest's to resolve if it ever chooses to, and are reported
  upward rather than worked around here.

### The published "under 5%" reference point

- **Context**: The brief names `<5%` decoupling as the published "good"
  reference point. The project has been burned once by adopting a
  secondary-sourced constant (the refuted Banister coefficient string), so the
  provenance had to be established before the number became a default.
- **Sources Consulted**: TrainingPeaks Help Centre article above; multiple
  coaching blogs attributing the figure to Joe Friel; joefrieltraining.com.
- **Findings**:
  - The **5% figure itself is published by TrainingPeaks in its own words** —
    "a smaller change in EF (less than 5%)" indicates a well-coupled aerobic
    effort. That is a platform-published primary statement.
  - The near-universal attribution of the figure **to Joe Friel personally is
    secondary-attestation only**; it was not confirmed against Friel's own
    published text in this pass.
- **Implications**: `DEFAULT_AEROBIC_DRIFT_MAX_PCT = 5.0` is cited to
  TrainingPeaks with verification status *published by the platform; the common
  Friel attribution is unverified and is not claimed in code*.

### Cadence lock: mechanism, signature, and the absence of prior art

- **Context**: Req 2 asks for temporal-correlation detection with an explicit
  warning that single-point value matching false-positives at high intensity.
  Both the mechanism and any established algorithm had to be established.
- **Sources Consulted**: runningwritings.com, *Cadence lock: why GPS watches have
  a hard time*; fellrnr.com wiki, *Optical Heart Rate Monitoring*; Zhang et al.
  (2014), TROIKA, arXiv:1409.5181; Salehizadeh et al., SpaMA, PMC4732043;
  Dubey/Kumaresan/Mankodiya (2016), arXiv:1610.05112; plus direct measurement
  over the athlete's 74-file corpus.
- **Findings**:
  - Mechanism: the PPG sensor's motion-artifact rejection mistakes the
    accelerometer-derived motion frequency for the pulse signal. The reported
    lock is **1:1 with cadence in steps per minute**, anecdotally in the
    165–185 band. No harmonic (half-rate) lock pattern is documented.
  - The high-intensity false-positive caveat is real but **qualitative only** —
    no source quantifies it, gives a correlation threshold, or names a window.
  - SpaMA is the closest primary numeric anchor and it is a *real-time
    estimator*: 20 Hz sampling, 8 s analysis window with 2 s shift, HR search
    band 0.5–3 Hz. It confirms that the cadence frequency can become the
    dominant spectral peak — the phenomenon — but its parameters describe an
    onboard signal-processing pipeline, not a retrospective file-level detector.
  - **No published retrospective detector was found in any source.**
- **Implications**: every cadence-lock default is fitdocs' own and must be
  justified by measurement (Req 6.10). The SpaMA reference is recorded as
  corroboration of the *phenomenon* and explicitly not as the source of any
  fitdocs constant.

### Direct measurement over the real corpus

- **Context**: With no published thresholds available, the defaults had to be
  set from the data. Two probe scripts were run against the athlete's HealthFit
  data root (74 `.fit` files); no file, value or derived personal figure enters
  the repository — only the aggregate statistics below.
- **Findings**:

  | Measurement | Result |
  |---|---|
  | Files parsed | 74 (50 Run, 10 Ride, 4 Hike, 3 Walk, 7 Workout by normalized sport) |
  | Files with 0% cadence coverage | **17** (10 runs, 7 workout/strength) |
  | Median recorded cadence, runs | 83–90 (per-limb; ⇒ 166–180 steps/min) |
  | Median HR, runs | 88–172 |
  | Whole-activity Pearson r, HR vs 2×cadence | Run: min −0.225, median 0.157, max 0.552 (n=40); Ride max 0.605; Hike median −0.068; Walk median 0.071 |
  | Median \|HR − 2×cadence\| per run | 9–90 bpm |
  | Fraction of 120 s windows with r > 0.9, real runs | 0.00 on 35 of 40; max 0.06 |
  | **Worst-case locked duration under the conjunctive rule, entire real corpus** | **137 s** (one window; invariant across r ∈ {0.80, 0.90, 0.95} and δ ∈ {3, 5, 10} bpm) |
  | `efficiency_factor` available | Run 50/50, Ride 2/10, Walk 0/3, Hike 0/4, Workout 0/7 |
  | `decoupling_pct` available | Run 49/50, Ride 2/10, Walk 0/3, Hike 0/4, Workout 0/7 |

- **Implications**:
  - Correlation **alone** is not sufficient — genuine correlated effort reaches
    r = 0.605, and individual 120 s windows on clean runs exceed r = 0.9.
  - Value proximity **alone** is not sufficient — six real runs sit within
    9–12 bpm of `2 × cadence` on median, purely by coincidence of range.
  - The **conjunction of both, sustained**, separates cleanly: no real file
    accumulates more than 137 s. A 300 s minimum lock duration therefore carries
    better than 2× measured headroom over the entire corpus.
  - Not-assessed is the dominant verdict for the aerobic-drift check outside
    running, and for the cadence check on 17 of 74 files. Requirement 1's
    insistence that not-assessed be first-class is load-bearing, not decorative.

### Prior art for per-activity quality verdicts

- **Context**: Before defining a verdict vocabulary, check whether an
  established one should be adopted instead (build-vs-adopt).
- **Sources Consulted**: Strava Help Centre (*How to resolve an activity flag*,
  *Bad GPS data*); intervals.icu forum (*Fix activity data*, *Heart rate spikes
  now automatically fixed*); TrainingPeaks/WKO5 data-repair help; Garmin Connect
  documentation.
- **Findings**: Strava's flag is binary and scoped to segment-leaderboard
  eligibility. intervals.icu and WKO expose *correction* tooling — they change
  the data rather than record a verdict about it. No surveyed platform stores a
  per-activity quality verdict, and none distinguishes "not assessed" from
  "checked and clean".
- **Implications**: nothing to adopt. The vocabulary is already fixed by
  `training-load`'s `QualityFlag` (`detected` / `not-detected` / `not-assessed`),
  which this feature consumes rather than defines. The absence of prior art also
  means the *correction* path other platforms take is a road fitdocs is
  deliberately not on: this feature never repairs a stream (Req 9.1, 9.8).

### The "19 versus 241" anecdote

- **Context**: The brief cites an intervals.icu case where one workout scored 19
  on one channel and 241 on another, as motivation for the divergence flag.
- **Findings**: **Not located.** No intervals.icu forum post, documentation page
  or blog matching that pair of numbers was found.
- **Implications**: the anecdote is not cited anywhere in `design.md`, in code,
  or in any test. The divergence flag's justification rests on the measured fact
  that the corpus's channels are frequently the only channel available and on the
  research-established finding that platforms select rather than reconcile —
  neither of which needs the anecdote. Reported to the brief's owner.

## Architecture Pattern Evaluation

| Option | Description | Strengths | Risks / Limitations | Notes |
|---|---|---|---|---|
| Post-hoc pass over `LoadResult` | A separate stage reads the finished result and appends flags | Calculator-agnostic; no threshold-load change | `LoadResult` carries no anchor date and no numeric intensity — only formatted display strings in `inputs_used`; staleness would be unimplementable and divergence would require parsing presentation text back into floats | **Rejected** |
| Evaluate inside `compute`, over raw `ChannelOutcome`s | The calculator hands typed channel outcomes and samples to a pure flag layer, then passes the flags to `build_result` | Exact typed inputs (`ChannelLoad.anchor`, `.intensity`, `.coverage`); no round-trip through formatting; one additive signature change and one call site | Flags are produced by the threshold calculator rather than universally; another calculator would have to produce its own | **Selected** |
| A `ChannelOutcome`-carrying field on `LoadResult` | Widen the contract so any consumer can see raw outcomes | Enables the post-hoc pass | Leaks channel vocabulary into the methodology-agnostic contract that `training-load` deliberately keeps generic; contradicts Req 9 of `load-channels` and Req 11.2 of `threshold-load` | **Rejected** |

## Design Decisions

### Decision: Consume raw `ChannelOutcome`s inside `compute`

- **Context**: `threshold-load` explicitly hands this feature the choice between
  consuming the raw channel outcomes inside `compute` and re-deriving from the
  recorded non-selected values on the assembled result.
- **Alternatives Considered**:
  1. Re-derive from `LoadResult` after assembly.
  2. Evaluate inside `compute` from the typed `Mapping[ChannelId, ChannelOutcome]`.
- **Selected Approach**: (2).
- **Rationale**: the assembled result is **lossy by design**.
  `NonSelectedValue` carries `value`, `key`, `label` and a prose `reason` — it
  carries no intensity, no coverage and no anchor. The selected channel's
  intensity and coverage survive only as *formatted display strings* inside
  `inputs_used` (`("Intensity", "0.912")`), and the anchoring benchmark's
  `measured_on` date survives only inside the channel's own formatted
  `inputs_used` entries. Recovering a `date` and a `float` by parsing a
  presentation layer would make the staleness and divergence checks depend on
  `threshold-load`'s formatter strings, which that spec pins as user-visible
  text subject to change. Req 7.7 forbids exactly this.
- **Trade-offs**: the flag layer is invoked by the threshold calculator, so
  flags are that calculator's output rather than a universal post-processing
  stage. Accepted: all three checks are *about channels*, and only a
  channel-based calculator has channels. `training-load`'s `flags` field stays
  methodology-agnostic, so a future calculator can emit its own verdicts.
- **Follow-up**: if a second channel-based calculator ever ships, the flag layer
  is already a pure function over `(Activity, DerivedMetrics, outcomes,
  selected, date, settings)` and can be called from it unchanged.

### Decision: Conjunctive cadence-lock rule over successive fixed-width spans

- **Context**: Req 2.1, 2.2, 2.4, 2.9. The brief warns that single-point value
  matching false-positives at high intensity; the measurement shows correlation
  alone false-positives too.
- **Alternatives Considered**:
  1. Whole-activity correlation above a threshold.
  2. Value proximity (|HR − steps/min| small) over a sustained span.
  3. Both conditions, evaluated per span, with a minimum total locked duration.
  4. Frequency-domain (spectral peak coincidence), following TROIKA/SpaMA.
- **Selected Approach**: (3). Successive non-overlapping spans of a configured
  width, anchored at the first paired sample; a span is *locked* when Pearson r
  ≥ the configured minimum **and** the median absolute difference between HR and
  steps/min is ≤ the configured tolerance; the activity is *detected* when the
  summed locked duration reaches the configured minimum.
- **Rationale**: measurement. Alternative 1 fires on genuine correlated effort
  (real r reaches 0.605, and single windows on clean runs exceed 0.9);
  alternative 2 fires on six real runs whose HR happens to sit within 9–12 bpm
  of `2 × cadence`; the conjunction fires on none, with a measured worst case of
  137 s against a 300 s default. Alternative 4 needs resampling to a uniform
  grid — which Req 2.10 forbids — and would import a real-time estimator's
  machinery to answer a much simpler retrospective question.
- **Trade-offs**: non-overlapping spans can split a lock across a boundary and
  under-count it. At a 120 s width and a 300 s minimum, a genuine multi-minute
  lock still produces enough fully-contained spans regardless of phase, and the
  alternative — a rolling window advancing per sample — costs determinism-free
  complexity and more false positives for no measured gain.
- **Follow-up**: all four parameters are configuration, so a corpus that ever
  *does* contain a lock can retune without a code change.

### Decision: Compare HR against `2 × cadence_rpm`, and only for running

- **Context**: Req 2.3, 2.8.
- **Rationale**: `ingest/records.py` stores the FIT `cadence` field verbatim,
  and for running that field is per-limb; the measurement confirms it (median
  83–90 on runs). The literature's lock signature is 1:1 against **steps per
  minute**. Restricting to `Modality.RUN` follows the mechanism: the artifact is
  a wrist PPG locking onto arm-swing frequency, which equals stride frequency
  when running. On a bicycle the arm is largely static and pedal cadence is not
  the wrist's motion frequency, so the same comparison has no mechanistic basis;
  walking cadence sits below the plausible HR band. The corpus corroborates —
  every ride, walk and hike is far from lock on both axes.
- **Trade-offs**: a walk-mode lock, if it exists, is reported *not-assessed*
  rather than detected. That is the honest verdict for a check fitdocs has no
  basis to run, and it follows the precedent `load-channels` set by defining the
  pace channel for running only.

### Decision: Efficiency factor is a reported basis, never a verdict

- **Context**: Req 4.5. The brief and the roadmap both name "Efficiency Factor /
  aerobic decoupling" as the divergence signal.
- **Rationale**: EF has **no absolute reference point** and its units are
  sport-dependent (W·bpm⁻¹ on the bike, m·min⁻¹·bpm⁻¹ running). A single
  activity's EF admits no threshold; it is only meaningful as a trend across an
  athlete's own history, which is plan-level analysis this project defers. What
  *is* thresholdable is decoupling — which is precisely the comparison of
  first-half EF against second-half EF. So EF enters the design exactly where it
  is defensible: as the constituent of the decoupling figure and as a stated
  part of that verdict's basis.
- **Trade-offs**: a reader expecting an "EF flag" gets none. The design states
  the reason at the point where they would look for it.

### Decision: Divergence compares intensities, not loads

- **Context**: Req 3.1, 3.4. `load-channels` defines `intensity` as
  dimensionless and exactly 1.0 at threshold on **all three** channels.
- **Rationale**: that shared definition is the only quantity in the system that
  is genuinely comparable across channels. Loads are not: they scale with
  duration and with each channel's own scored span, so two channels can differ
  in load merely because one gated on a shorter covered span. Comparing
  intensities isolates the disagreement about *how hard*, which is the question.
- **Trade-offs**: an intensity difference does not distinguish a fitness change
  from a bad sensor — but distinguishing them is explicitly the interpretation
  layer's job, and Req 9 puts it out of boundary.

### Decision: Do not unify the two coverage figures

- **Context**: `load-channels` recorded that its time-weighted coverage differs
  from the sample-count percentage `render/sections.py` displays under
  non-uniform sampling, and named this feature the natural reconciler.
- **Alternatives Considered**:
  1. Change `render/sections.py` to time-weighted coverage.
  2. Compute a sample-count figure in the load layer to match the document.
  3. Keep both, name the basis of every figure this feature reports, and record
     the difference.
- **Selected Approach**: (3).
- **Rationale**: the two figures are **both correct for different questions**.
  The gate's figure answers "how much of the time the load was accumulated over
  carried a value", which is the only figure that can honestly qualify a load.
  The table's figure answers "what fraction of recorded samples carry this
  channel", which is a device-behavior fact. Option 1 changes already-rendered
  output in a file this spec does not own, for every document in the data root,
  to fix a labelling problem; option 2 introduces a second coverage definition
  inside the load layer, which is worse than the divergence it fixes.
- **Trade-offs**: the divergence survives. It is mitigated by naming the basis
  in every figure this feature emits (Req 8.1) and by a recommendation, recorded
  and not implemented here, that `workout-docs` relabel its table header to
  *Sample coverage*.
- **Follow-up**: reported to `workout-docs` / `fit-ingest` as a one-word
  documentation change in their own file.

### Decision: Reuse the channel layer's coverage function for the paired gate

- **Context**: Req 2.7 needs "the proportion of the activity for which heart rate
  and cadence were both recorded".
- **Selected Approach**: build a derived presence sequence — a value at index
  *i* when both HR and cadence are recorded there, `None` otherwise — and pass it
  to `channels.sufficiency.stream_coverage`.
- **Rationale**: build-vs-adopt. The shipped gate already implements exactly the
  time-weighted measurement this needs, including the two-sample and zero-span
  degenerate cases. Reusing it means the load layer has **one** coverage
  definition, which is what makes the Req 8 story ("the load layer measures time,
  the document counts samples") true rather than aspirational.
- **Trade-offs**: a dependency from `load/qa` onto `load/channels`. Declared, and
  in the permitted direction.

### Decision: A future-dated anchor reports not-assessed rather than raising

- **Context**: `benchmarks.benchmark_age` raises `ValueError` when
  `measured_on > activity_date`, on the stated grounds that date-aware selection
  can never produce one. Req 1.10 forbids this layer from raising, and
  `threshold-load` Req 1.7 forbids the calculator from raising at all.
- **Selected Approach**: the staleness check guards the ordering itself and
  reports *not-assessed* naming the inconsistency, so `benchmark_age` is only
  ever called with a satisfied precondition.
- **Rationale**: a triggered guard means an upstream defect, and "could not
  check" is the honest verdict for an input the layer cannot trust. Converting an
  upstream invariant violation into a crashed load pass would fail the whole
  document for a diagnostic.
- **Trade-offs**: the defect is reported quietly in a flag rather than loudly as
  a crash. A test asserts the guard fires, so the path is not dead code.

## Risks & Mitigations

- **No true-positive real data exists for cadence lock.** The detector's
  positive path is validated only against constructed streams. *Mitigation*: the
  negative path is validated against statistics measured on the whole real
  corpus, every parameter is configuration, and the measured 137 s worst case is
  recorded so a future retune has a baseline to compare against.
- **The divergence tolerance is fitdocs' own with no published anchor.** *
  Mitigation*: it is configuration; its default and the reasoning behind it are
  cited in code as fitdocs' own rather than dressed up as sourced; and the flag
  is advisory by construction, so a mis-set tolerance changes no number.
- **The shipped `decoupling_pct` is confounded on hilly runs**, because it uses
  raw speed rather than grade-adjusted speed. A hilly run can show large drift
  purely from terrain. *Mitigation*: recorded as a stated divergence from
  TrainingPeaks' normalized-graded-pace EF, and reported to `fit-ingest` as its
  metric to change if it chooses; this feature must not fork the definition.
  Note that `load-channels` builds a grade-adjustment unit that would make a
  corrected variant possible later.
- **fitdocs' EF and its decoupling do not share a numerator on the bike** (NP
  versus raw power). Pre-existing, fit-ingest-owned, reported not worked around.
- **`[load]` now has four co-owning specs.** *Mitigation*: this feature adds one
  member to the single `LoadSettings` dataclass and one projection helper, adds
  no reader, and its landing test asserts a document carrying
  `default_calculator`, `[load.priority]`, `[load.sufficiency]` and
  `[load.flags]` together parses cleanly.
- **`build_result` gains a parameter.** *Mitigation*: keyword-only with an empty
  default, so the change is additive and the single existing call site is the
  only one updated; `threshold-load` anticipated and endorsed exactly this.

## References

- TrainingPeaks Help Centre — *Aerobic Decoupling (Pw:Hr and Pa:HR) and
  Efficiency Factor (EF)*: the EF definition and the "less than 5%" reference
  point. *Published by the platform; the widespread attribution of the 5% figure
  to Joe Friel is secondary and unverified.*
  https://help.trainingpeaks.com/hc/en-us/articles/204071724-Aerobic-Decoupling-Pw-Hr-and-Pa-HR-and-Efficiency-Factor-EF
- forum.intervals.icu — *Aerobic decoupling calculation question*: the
  `(ef1 − ef2) × 100 / ef1` formula and the sample-index half split.
  https://forum.intervals.icu/t/aerobic-decoupling-calculation-question/1823
- intervals.icu — decoupling feature page, including the distinct "Seiler
  Decoupling" variant (60 s moving averages over %HRR and %power reserve), which
  fitdocs does not implement. https://www.intervals.icu/features/decoupling/
- runningwritings.com (2021) — *Cadence lock: why GPS watches have a hard time*:
  the mechanism and the 1:1 steps-per-minute signature. *Secondary.*
  https://runningwritings.com/2021/05/cadence-lock-why-gps-watches-have-hard.html
- fellrnr.com wiki — *Optical Heart Rate Monitoring*. *Secondary.*
- Salehizadeh et al., SpaMA, *Sensors* / PMC4732043 — primary, peer-reviewed
  confirmation that motion cadence can become the dominant PPG spectral peak;
  20 Hz sampling, 8 s window, 2 s shift, 0.5–3 Hz search band. *Cited as
  corroboration of the phenomenon only; no fitdocs constant derives from it.*
  https://pmc.ncbi.nlm.nih.gov/articles/PMC4732043/
- Zhang et al. (2014), TROIKA, arXiv:1409.5181; Dubey, Kumaresan & Mankodiya
  (2016), arXiv:1610.05112 — real-time PPG motion-artifact suppression. *Same
  status: phenomenon, not parameters.*
- Strava Help Centre — *How to resolve an activity flag*, *Bad GPS data*: the
  closest prior art for a stored per-activity verdict, and its limits.
- forum.intervals.icu — *Fix activity data*, *Heart rate spikes now
  automatically fixed*: correction tooling rather than verdicts.
- `src/fitdocs/metrics/power.py`, `src/fitdocs/render/sections.py`,
  `src/fitdocs/model.py` — the shipped definitions this feature consumes
  unchanged.
- Measurement scripts run against the athlete's HealthFit data root on
  2026-07-25; aggregate statistics only are recorded above, per the standing
  rule that personal data never enters this repository.
