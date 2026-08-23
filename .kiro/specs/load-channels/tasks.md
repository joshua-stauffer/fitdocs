# Implementation Plan

## Upstream Prerequisite

Every task below consumes types two upstream specs deliver, and the two are
**not** the same spec:

- `athlete-benchmarks` delivers `fitdocs.benchmarks` (`Benchmark`,
  `BenchmarkKind`). It must be implemented before task 1.2 starts.
- **`training-load` owns `src/fitdocs/load/settings.py`** — `LoadSettings` with
  every field defaulted, `DEFAULT_LOAD_SETTINGS`,
  `LoadSettingsError(SettingsError)` and the single reader
  `load_load_settings(document: Mapping[str, object], settings_file: Path) ->
  LoadSettings`. Task 2.3 adds one defaulted field and one projection inside
  that reader without changing the pinned signature.

These are spec-level dependencies recorded in the roadmap, not tasks in this
plan.

## Test File Ownership

Each task owns exactly one test module, so no two tasks write the same
assertions. `test_types.py` → 1.2; `test_sufficiency.py` → 1.3;
`test_weighting.py` → 2.1; `test_grade.py` → 2.2; `test_settings.py`
(existing, extended) → 2.3; `test_power.py` → 3.1; `test_heart_rate.py` → 3.2;
`test_pace.py` → 3.3; `test_sources.py` → 1.1; `test_purity.py` → 4.2;
`test_worked_examples.py` → 5.1; `test_insufficiency.py` → 5.2;
`test_intensity_semantic.py` → 5.3. The one test
module that is *modified* rather than owned is the existing published-surface
pin, edited by task 4.1. Where a requirement appears on both a channel task and
a validation task, the channel task asserts it against *its own* fixtures and
the validation task asserts it against the *published* source values or across
all three channels at once. Tasks 5.1, 5.2 and 5.3 name channel components in
their boundaries as **read-only subjects**: none edits any source module, which
is what makes them safe to run concurrently despite overlapping names.

- [ ] 1. Foundation: package, provenance, vocabulary and the one gating rule

- [x] 1.1 Create the channel package and establish its provenance record
  - Create the channel package and its mirrored test package so every later
    task has somewhere to land; the package initializer stays a re-export point
    with no logic and no import side effect and is populated in task 4.1
  - Create the citation vocabulary — a source's authors, year, work, locator and
    an explicit verification status — plus a divergence record naming a
    behavior, what intervals.icu does, what fitdocs does, and why
  - Define the verification status with **all three** members up front: "read
    from the source's own text", "attested only by consistent secondary
    literature", and "chosen by fitdocs and justified by a recorded measurement
    rather than by a published source". The third member is defined here, and
    only here, even though no constant in this feature carries it — the quality
    flags feature is its only consumer and merely *uses* it, so defining it now
    is what stops a sibling feature from reaching across the boundary to widen
    this enum and to edit this task's own test module. This feature's own
    postconditions are untouched by it
  - Populate the named citations every constant in this layer will point at: the
    Coggan power-load definitions and their worked examples, the Banister
    training-impulse weighting, the Minetti energy-cost-of-running model, the
    intervals.icu pace-load and heart-rate-load formulations, and the published
    coverage requirement that justifies the default coverage threshold
  - Mark the Banister and Minetti citations as secondary-attested with a note
    stating why the primary text was not obtained, and record on the Minetti
    citation that the walking form of the model was not obtained and is
    therefore not implemented
  - _(amended 2026-07-27, queue 2026-07-26-citation-vocabulary-diverges-
    across-layers, criteria 8.9/8.10)_ Superseded in part: Coggan, Minetti and
    the intervals.icu pace-load citations were re-sourced to PRIMARY_TEXT
    after their actual primary texts were located and read; only Banister
    remains secondary-attested, now named in `BLOCKED_CITATIONS` as a tracked
    exception with a note recording the search that failed to obtain it.
    The bullet above's claim that the Minetti walking form "was not obtained"
    is also superseded: re-sourcing `MINETTI_2002` to `PRIMARY_TEXT` read
    Fig. 1's caption in full, which gives both the running and the walking
    regressions together, so the walking form was read alongside the running
    form. It remains unimplemented, but by scope choice, not for lack of a
    source (Req 7.9, amended 2026-07-27 to match)
  - _(amended again 2026-07-29, queue
    2026-07-27-banister-morton-primary-texts-obtained)_ Superseded further:
    Banister no longer remains secondary-attested either. Both Banister
    (1991) and Morton, Fitz-Clarke & Banister (1990) were obtained and read
    in full (`docs/reference/banister-trimp-primary-sources.md`), so
    `BANISTER_TRIMP` was re-sourced to `PRIMARY_TEXT` and `BLOCKED_CITATIONS`
    is now the empty set, retained as the mechanism rather than deleted
  - Record at least the three known divergences: running power computed from
    recorded watts intervals.icu does not ingest; a pace formulation that does
    not variability-normalize the way the alternative published method does; and
    the reported heart-rate *intensity*, where intervals.icu publishes a
    heart-rate load definition but no heart-rate intensity definition and
    fitdocs reports the square root of the impulse ratio so that one intensity
    semantic spans all three channels. State on that third entry that the
    heart-rate **load** is on the same scale intervals.icu states for HRSS
    (normalized TRIMP, 100 = one hour at max effort), so the two are directly
    comparable, and that only the reported intensity differs. *Corrected
    2026-07-26: this bullet previously said "remains an exact interop match".
    `INTERVALS_ICU_HRSS` publishes no formula, so it supports the shared scale
    and not numeric identity; do not restore the stronger wording without a
    source that publishes intervals.icu's HRSS arithmetic.*
  - Assert uniqueness over fields that actually exist: citations are unique by
    their key, and divergences are unique by their behavior name — the
    divergence record carries no key field and none is added, so the uniqueness
    rule is written against `behavior` rather than against a field that does not
    exist
  - Observable: the package imports cleanly; the citation module exposes a
    complete set of citations and divergences whose test asserts every citation
    carries a non-empty work and a verification status, the two
    secondary-attested ones explicitly saying so, no citation in this package
    carrying the fitdocs-measured status while that status is nonetheless
    defined and exported, keys unique across citations, and behavior names
    unique across divergences
  - _Requirements: 3.10, 4.9, 6.8, 7.9, 8.1, 8.2, 8.3, 8.5, 8.8_
  - _Boundary: ProvenanceRecord_

- [x] 1.2 Define the channel result vocabulary and the sufficiency value
  - Define the three channel identifiers and the closed set of insufficiency
    reasons: no benchmark, mutually inconsistent benchmarks, stream absent,
    stream coverage below minimum, activity too short, model not defined for the
    modality, and a required derived value not computable
  - Define the computed-load value carrying the channel, the load, the intensity
    ratio, the anchoring benchmark, the scored duration, the measured stream
    coverage, the ordered inputs that produced it and any notes; and the
    insufficiency value carrying the channel, the reason, a human explanation
    and — for the two threshold reasons only — the observed and required values
  - Define the outcome as a closed two-variant union with no third state, and a
    stream-coverage value whose fraction is derived rather than stored
  - State the shared intensity semantic **once**, at the definition of the
    computed-load value and nowhere else: the load equals the scored duration in
    hours times the square of the reported intensity times one hundred, so the
    intensity is dimensionless, is exactly 1.0 at threshold, and means the same
    thing on every channel. Every channel task is then written to satisfy this
    definition rather than to invent its own
  - Define the resolved sufficiency configuration as a value with a shared
    minimum coverage, a shared minimum duration, and an optional per-channel
    coverage override, resolving to the shared value when no override is set;
    document the coverage default against the cited published precedent and the
    duration default as this project's own, justified as twice the longest
    window any channel's inputs require
  - Add the guard that rejects a benchmark of the wrong quantity as a
    programming error rather than computing from it; the guard is defined here
    and *called* by each channel in tasks 3.1, 3.2 and 3.3
  - Observable: every type is frozen and compares equal for equal inputs; unit
    tests cover the override resolution, the derived fraction, and the
    wrong-quantity guard raising with both quantities named
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.9, 1.11, 2.7, 3.2, 3.3, 3.9, 3.10_
  - _Boundary: ChannelVocabulary_

- [x] 1.3 Implement the shared data-sufficiency gate
  - Measure a stream's coverage as time-weighted: sum the positive intervals
    between consecutive samples, and count an interval as covered when the
    earlier sample carries a recorded value — the same accumulation domain the
    shipped training-impulse metric uses — measured on the raw ingested arrays
    with a recorded zero counted as data and only an unrecorded value as missing
  - Implement one gate serving all three channels, differing only in which
    stream it inspects and which configured minimum applies, and returning
    either the measured coverage or a typed insufficiency
  - Accept an optional explicit minimum that overrides the per-channel
    resolution, because the pace channel's altitude check is a refinement input
    rather than a channel of its own and must be judged against the shared
    minimum, never against the pace channel's own override
  - Fix and document the evaluation order so that the reported reason is
    deterministic when more than one condition fails: no measurable span or a
    span below the minimum duration first, then a wholly absent stream, then
    coverage below the minimum, each naming the observed and required values
    where a threshold failed
  - Never raise: fewer than two samples, a zero-length span, and an entirely
    unrecorded stream are all typed outcomes
  - Observable: unit tests show a dropout reducing coverage by exactly the
    expected fraction, a recorded zero counting as covered, a device pause
    credited to its pre-pause sample not reducing coverage, an activity failing
    both duration and coverage reporting the duration reason every time, and an
    explicit minimum winning over a configured per-channel override
  - _Requirements: 1.8, 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7, 2.8, 2.9, 2.10_
  - _Boundary: SufficiencyGate_

- [ ] 2. The model units: weighting, terrain, configuration

- [x] 2.1 (P) Build the substitutable heart-rate weighting seam
  - Define the weighting seam as a protocol exposing an activity impulse and the
    impulse of one hour held at a given heart rate, and ship exactly one
    implementation of it — no second implementation, no registry, no
    configuration key selecting one, and no unreachable branch anticipating one
  - Delegate the activity impulse to the shipped training-impulse metric
    unchanged, restating none of its coefficients and editing none of its module
  - Compute the one-hour reference through that same shipped function by scoring
    a synthetic one-hour constant-heart-rate sample series, so the reference and
    the activity value can never be weighted differently; document the
    construction so it is not mistaken for test scaffolding
  - Cite the roadmap decision that requires the seam and the citation record
    created in task 1.1, and record that the deferred power-calibrated
    regression slots in later as a second implementer
  - Observable: the implementation reproduces the published training-impulse
    worked example through the shipped metric, the one-hour reference is
    strictly positive for valid inputs, and rescaling the shipped multiplicative
    coefficient scales both returned values by the same factor
  - _Requirements: 5.4, 5.5, 5.6, 5.7, 5.8, 8.6, 9.8_
  - _Boundary: HeartRateIntensityModel_
  - _Depends: 1.1_

- [x] 2.2 (P) Implement grade adjustment as its own unit
  - Implement the published energy-cost-of-running polynomial as a ratio against
    its level-ground cost, citing the record created in task 1.1 and pinning its
    coefficients, and note in the docstring the widely-mirrored corrupted
    transcription that must not be "corrected" into the code
  - Clamp gradients to the model's published validated range rather than
    extrapolating, and report whether clamping occurred so the caller can say so
  - Derive each interval's gradient from altitude smoothed before differencing,
    reusing the width and trailing alignment the shipped elevation metrics
    already pin but emitting a series aligned index-for-index with the samples;
    document why the shipped helper could not be reused directly
  - Treat an interval whose distance delta is not positive, or is below a
    minimum meaningful displacement, as level rather than producing an extreme
    gradient
  - Produce a grade-equivalent distance alongside the raw recorded distance,
    with a flag for whether the model was applied and a count of clamped
    intervals; leave every measured value — distance, duration, anything else —
    untouched
  - Observable: unit tests pin the coefficient tuple, assert exactly 1.0 at zero
    gradient, accept the range boundaries un-clamped and clamp beyond them with
    the flag set, show a lone altitude spike damped by the smoothing, and show
    that not applying the model returns the raw distance exactly
  - _Requirements: 7.1, 7.2, 7.3, 7.4, 7.5, 7.7, 7.8, 7.9_
  - _Boundary: GradeAdjustment_
  - _Depends: 1.1_

- [ ] 2.3 (P) Project the sufficiency settings from the shared load table
  - Extend the load-settings value and reader that already live in the load
    layer's settings module — a module `training-load` owns, whose reader
    signature `(document, settings_file) -> LoadSettings`, error type and
    all-fields-defaulted dataclass are pinned there and must not change here —
    with the sufficiency sub-table; confirm first that exactly one reader of
    that table exists there and stop rather than adding a second if two are
    found, since the single-reader invariant is what lets three sibling features
    share the table
  - Preserve the reader's existing behavior of ignoring keys and sub-tables it
    does not recognize, and open no file of its own
  - Read the shared minimum coverage, the shared minimum duration and the three
    optional per-channel coverage overrides, applying the documented defaults
    when the settings file, the load table, the sub-table or any individual key
    is absent — never treating absence as an error
  - Reject a coverage value that is not a number, is a boolean, or falls outside
    the range above zero and at or below one; reject a duration that is not a
    whole number of seconds, is a boolean, or is zero or negative; reject a
    non-table sub-table — each naming the file, the key or path, and the
    offending value, raised as the configuration error type the load layer
    already defines
  - Keep the dependency running from settings to the channel value type and
    never the reverse, so the channels acquire no configuration dependency
  - Observable: absent file, absent table, absent sub-table and absent keys each
    resolve to the documented defaults; each invalid form raises naming the key;
    an unknown key inside the sub-table parses cleanly; and an integration test
    over a data root carrying an invalid sufficiency value shows the load pass
    terminating at the configuration exit with no document created or modified
  - That last assertion relies on inherited behavior: the load pass already
    validates the load table before any document is written. If that upstream
    wiring is absent when this task runs, stop and coordinate rather than
    reaching into the engine or the command surface — both are outside this
    task's boundary
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8_
  - _Boundary: LoadSettingsExtension_
  - _Depends: 1.2_

- [ ] 3. The three channels

- [ ] 3.1 (P) Implement the power channel
  - Compose the shipped normalized power, the shipped moving time and the
    shipped power-load formula rather than restating the rolling-average window,
    the gap handling or the load arithmetic
  - Anchor exclusively on the dated threshold-power benchmark supplied, calling
    the wrong-quantity guard on it at entry, with no default, no estimate and no
    fallback to any flat profile value; an absent or non-positive threshold is
    the no-benchmark insufficiency
  - Gate on the power stream before computing, and report the not-computable
    insufficiency when normalized power or the scored duration cannot be derived
  - Score any modality that records power, running included, and report the
    anchoring discipline and the anchor's measurement date among the inputs
  - Record in the module documentation that computing a running power load from
    recorded watts diverges from intervals.icu, which does not ingest those
    fields natively, and why fitdocs does it anyway
  - Report the intensity as normalized power over threshold power — the
    reference form of the shared intensity semantic, since the shipped power
    load formula is algebraically that ratio squared times hours times one
    hundred
  - Observable: in this channel's own test module, an hour held exactly at
    threshold power scores exactly 100 with an intensity of exactly 1.0, the
    shared intensity relation holds at a sub-threshold effort as well as at
    threshold, each gate and benchmark failure returns its own named reason, and
    a benchmark of the wrong quantity raises rather than computing
  - _Requirements: 1.6, 1.7, 1.9, 1.11, 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 4.9_
  - _Boundary: PowerChannel_
  - _Depends: 1.3_

- [ ] 3.2 (P) Implement the heart-rate channel
  - Compute the load as the activity's impulse divided by the impulse of one
    hour held at the threshold heart rate, times one hundred, taking both terms
    from the injected weighting seam and never from the derived-metric field
    that is computed against the flat profile keys
  - Report the intensity as the **square root** of the mean impulse rate
    relative to threshold — the square root of the load divided by one hundred
    and by the scored duration in hours. The bare impulse rate is *not* the
    intensity: it is the square of what the other two channels report, so it
    agrees with them at threshold and nowhere else, and reporting it under the
    same label would make every downstream cross-channel comparison wrong on
    easy aerobic efforts. Taking the square root puts this channel on the one
    shared semantic — dimensionless, exactly 1.0 at threshold, and satisfying
    the load relation stated in task 1.2
  - Compute and return the load **before** and independently of the intensity,
    so that the intensity definition cannot move the load; assert in this
    channel's tests that the load values are exactly what the impulse ratio
    produces, unchanged by how the intensity is reported
  - Require a threshold, a resting and a maximum heart rate, calling the
    wrong-quantity guard on each supplied benchmark and naming every absent one;
    reject mutually inconsistent values — a maximum not above the resting rate,
    or a threshold not above the resting rate and at or below the maximum — with
    the inconsistent-benchmarks reason and no computed value
  - Gate on the heart-rate stream before computing, and report the scored
    duration as the covered time the impulse actually integrated over
  - Report the impulse, the reference, all three heart-rate inputs and the
    anchor's measurement date among the inputs that produced the value
  - Record in the module documentation that intervals.icu computes the heart-rate
    **load** the same way and requires the same three inputs, so the load is an
    interop match rather than a divergence — and that the reported **intensity**
    is the one stated divergence: intervals.icu publishes no heart-rate
    intensity definition, so there is no published value to match, and fitdocs
    reports the square root of the impulse ratio so one semantic spans all three
    channels. Point at the divergence entry recorded in task 1.1
  - Observable: in this channel's own test module, an hour held exactly at the
    threshold heart rate scores exactly 100 with an intensity of exactly 1.0;
    at a clearly sub-threshold constant heart rate the reported intensity equals
    the square root of the impulse ratio and the shared load relation holds,
    while the load itself equals the impulse ratio times one hundred times
    hours; each missing, inconsistent or wrong-quantity benchmark and each gate
    failure behaves as specified; and the computed load is unchanged when the
    shipped weighting's multiplicative coefficient is rescaled
  - _Requirements: 1.6, 1.7, 1.9, 1.11, 5.1, 5.2, 5.3, 5.9, 5.10, 5.11_
  - _Boundary: HeartRateChannel_
  - _Depends: 1.3, 2.1_

- [ ] 3.3 (P) Implement the pace channel
  - Compute the load from mean grade-adjusted speed against the athlete's
    threshold speed over moving time, matching the published interoperability
    formulation including its use of moving rather than elapsed time, and
    converting the threshold benchmark from seconds per kilometre into speed
    within this channel
  - Check modality first and report the model-not-defined reason naming the
    modality for anything other than running, without implying which channel
    should have been used instead
  - Anchor exclusively on the dated threshold-pace benchmark supplied, calling
    the wrong-quantity guard on it; gate on the distance stream; report the
    not-computable reason when moving time or accumulated distance is absent or
    not positive
  - Decide whether to apply grade adjustment by running the shared gate over the
    altitude stream with the explicit shared minimum coverage rather than this
    channel's own override; when altitude is absent or thinly covered, compute
    from unadjusted pace, note on the result that adjustment was not applied and
    why, and do not report insufficiency for that reason alone
  - Report the grade-adjusted speed, the threshold speed, the moving time,
    whether adjustment was applied and how many intervals were clamped among the
    inputs; record the stated divergence from the alternative published method
    that variability-normalizes graded pace
  - Report the intensity as grade-adjusted speed over threshold speed, which is
    the shared intensity semantic in its published form for this channel
  - Observable: in this channel's own test module, an hour held exactly at
    threshold pace on level ground scores exactly 100 with an intensity of
    exactly 1.0; the shared intensity relation holds at a sub-threshold pace as
    well as at threshold; the same run with and without an altitude stream both
    compute, differ in value, and differ in the recorded note while reporting
    identical distance and duration; a configured pace-coverage override does
    not change the altitude decision; a non-running modality returns
    model-not-defined
  - _Requirements: 1.6, 1.7, 1.9, 1.11, 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7, 6.8, 6.9, 7.6_
  - _Boundary: PaceChannel_
  - _Depends: 1.3, 2.2_

- [ ] 4. Integration: the layer's public surface and its boundary

- [ ] 4.1 Publish and pin the channel layer's surface
  - Expose the result vocabulary, the three computation entry points under
    channel-qualified names, the weighting seam with its shipped instance, and
    the provenance records as the layer's public surface, with no logic and no
    registration side effect on import; the settings projection is deliberately
    not part of this surface
  - Extend the test that pins the published surface so the members of the
    computed-load value, the insufficiency value and the reason set cannot drift
    accidentally
  - Observable: importing the layer exposes exactly the intended names, and the
    surface pin fails if a member is added, renamed or removed
  - _Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7_
  - _Boundary: ChannelSurface, PublicSurfacePin_
  - _Depends: 3.1, 3.2, 3.3_

- [ ] 4.2 Prove purity and the boundary by import and by behavior
  - Assert that importing the channel layer pulls in no load engine, registry,
    profile, calculator-contract, settings, CLI or render module, so the
    dependency direction stated in the design is enforced rather than assumed
  - Assert that no module in the layer references a filesystem, network, clock
    or prompting interface, and that no module selects between channels,
    computes a quality flag, resolves a benchmark, or maps a modality to a
    discipline
  - Assert determinism by computing every channel twice over identical inputs
    and comparing the results for equality
  - Assert the provenance rule structurally: every module in the package that
    defines a numeric constant names a citation key in its module docstring, so
    "no constant without a citation" is enforced by the suite rather than by
    review
  - Observable: the boundary test module fails if a future edit introduces any
    of the forbidden imports, a non-deterministic result, or an uncited constant
    module
  - _Requirements: 1.10, 8.3, 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7_
  - _Boundary: ChannelSurface — read-only; whole package import graph_
  - _Depends: 4.1_

- [ ] 5. Validation

- [ ] 5.1 (P) Verify every channel against published worked examples
  - Reproduce the published power-load worked examples — the intensity case and
    at least two complete duration-and-threshold cases — asserting the stated
    results, with the source and the input values recorded in the test
  - Reproduce the published training-impulse worked example through the shipped
    metric the heart-rate channel consumes, and the published pace-load
    formulation, each recording its source
  - **TRAP — do not pin B91's printed worked examples as vectors.** Banister
    1991 prints three worked training-impulse examples in the Fig. 9.5 / 9.6
    captions (pp. 409-410). **None of the three satisfies the equation printed
    one page earlier**, and the third is not even internally consistent with
    itself. Quoting them produces a test that disagrees with the shipped metric
    by 8% to 370% depending on the row — with an impeccable citation, so review
    by reading will pass it. `docs/reference/banister-trimp-primary-sources.md`
    § D4 carries the full table and the standing ruling: *any worked example
    fitdocs ships must be computed from the formula and labelled as such*, never
    transcribed from a caption. Queue item
    `2026-07-27-banister-figure-captions-unusable-as-vectors`
  - Assert the threshold identity across all three channels in one place: one
    hour held exactly at threshold scores exactly 100 for each, with an
    intensity of exactly 1.0. This is deliberately only half the scale
    contract — the intensity semantic away from threshold is task 5.3's, because
    a threshold-only assertion cannot distinguish a linear intensity from a
    squared one
  - Assert that rescaling the shipped training-impulse multiplicative
    coefficient leaves the heart-rate load bit-identical while the raw impulse
    moves, bounding the blast radius of the pending upstream re-sourcing
  - Observable: every worked example passes to its published value within a
    stated tolerance, and the invariance assertion fails if the normalization is
    ever removed
  - _Requirements: 1.6, 4.8, 5.10, 8.4_
  - _Boundary: PowerChannel, HeartRateChannel, PaceChannel — read-only_
  - _Depends: 3.1, 3.2, 3.3_

- [ ] 5.2 (P) Prove the insufficiency matrix and channel independence
  - Cover every reason in the closed set at least once per channel that can
    produce it, asserting the reason, that the explanation names what failed,
    and that observed and required values are populated for exactly the two
    threshold reasons and for no others
  - Assert that a computed result always carries its coverage and duration even
    when the gate passed comfortably, and that a benchmark's measurement date
    and note reach the result so a caller can report what the number anchored to
  - Score one activity with full power and thin heart-rate coverage and assert a
    computed power load alongside a heart-rate insufficiency, neither affecting
    the other
  - Observable: the matrix fails if any reason becomes unreachable, if a reason
    is reported without its supporting numbers, or if one channel's failure
    changes another's result
  - _Requirements: 1.2, 1.4, 1.5, 1.7, 1.8, 2.4, 2.5, 2.6, 2.7_
  - _Boundary: ChannelVocabulary, SufficiencyGate, PowerChannel, HeartRateChannel, PaceChannel — read-only_
  - _Depends: 3.1, 3.2, 3.3_

- [ ] 5.3 (P) Prove the intensity semantic holds across channels away from threshold
  - Assert, per channel, that the reported load equals the scored duration in
    hours times the square of the reported intensity times one hundred, within a
    stated relative tolerance, for power, heart rate and pace alike
  - Assert the cross-channel agreement at **more than one point**: construct a
    heart-rate result and a power result carrying the same load over the same
    duration and assert their reported intensities agree, at threshold *and* at
    sub-threshold efforts where a linear and a square-root intensity definition
    differ by a wide margin. Use at least two clearly sub-threshold anchors — for
    a 48/190/165 athlete, roughly 120 bpm and 140 bpm, where the two candidate
    definitions differ by about 0.24 and 0.19 respectively. Those gaps straddle
    the divergence threshold the quality-flags feature will compare against, so
    this is the assertion that catches a mis-scaled intensity before it becomes a
    false divergence flag on easy aerobic sessions
  - Record in the test module, in prose, why a threshold-only assertion is
    insufficient: at intensity 1.0 the impulse ratio and its square root are
    equal, so a test anchored only there passes under either definition and
    proves nothing. A future editor must not be able to weaken this module back
    to the threshold case without reading that sentence
  - Demonstrate the test's own sensitivity: substituting the bare impulse ratio
    for the heart-rate channel's reported intensity must fail these assertions at
    the sub-threshold anchors while still passing at threshold
  - Assert that the heart-rate loads used here are numerically identical to the
    impulse-ratio loads, so the record shows the intensity definition moved no
    load value
  - Observable: the module passes as written and fails under the substituted
    intensity definition, at the sub-threshold anchors specifically
  - _Requirements: 1.11, 5.11, 8.7_
  - _Boundary: PowerChannel, HeartRateChannel, PaceChannel, ChannelVocabulary — read-only_
  - _Depends: 3.1, 3.2, 3.3_

- [ ] 5.4 Prove no shipped output moved and close the quality gates
  - Run the existing golden-file document tests unchanged and assert they still
    pass, proving that no derived metric, no rendered value and no document
    changed as a result of this feature
  - Assert that the shipped derived-metric modules this layer consumes are
    untouched by this feature's diff, in particular the training-impulse
    coefficients and the normalized-power window
  - Run the full suite, including every test module added by this plan, with the
    project's lint and strict type-checking gates clean
  - Observable: the full suite, the linter and the strict type check all pass,
    and the golden files are byte-identical to their pre-feature state
  - Runs last by design: its observable covers the whole repository, so it
    cannot be asserted while 5.1, 5.2 and 5.3 are still adding test modules
  - _Requirements: 9.8_
  - _Boundary: whole repository_
  - _Depends: 4.2, 5.1, 5.2, 5.3_

## Coverage Notes

- Every acceptance criterion in `requirements.md` is claimed by at least one
  task. Criteria that are properties of the whole layer rather than of one unit
  — 1.10 (purity and determinism) and 9.1–9.7 (the feature boundary) — are
  enforced by tasks 4.1 and 4.2 rather than restated on every implementation
  task.
- Requirement 8's provenance obligations land in task 1.1 as a structured,
  testable record, so 8.3's "no constant without a citation" is checkable rather
  than aspirational; the individual citations are consumed by tasks 2.1, 2.2,
  3.1, 3.2 and 3.3.
- Requirement 1.9 is *defined* in task 1.2 and *invoked* in tasks 3.1, 3.2 and
  3.3, which is why all four claim it.
- Requirement 1.11, the shared intensity semantic, is *stated* in task 1.2,
  *satisfied* by tasks 3.1, 3.2 and 3.3, and *verified across channels* in task
  5.3. Requirement 8.7 belongs to 5.3 alone, because it is precisely the
  assertion no single channel's own test module can make.
- Requirement 8.2's third verification status is defined in task 1.1 even though
  no constant in this feature carries it; the boundary reason is recorded on the
  task and again under Cross-Spec Coordination.
- No requirement is deferred.

## Cross-Spec Coordination

- **Task 2.3 edits the load layer's settings module, which `training-load`
  owns.** `src/fitdocs/load/settings.py` is `training-load`'s, and its surface is
  pinned there: `LoadSettings` with every field defaulted,
  `DEFAULT_LOAD_SETTINGS`, `LoadSettingsError(SettingsError)` and the single
  reader `load_load_settings(document: Mapping[str, object], settings_file:
  Path) -> LoadSettings`. This task extends exactly that file — one defaulted
  field, one projection inside the existing reader — and changes neither the
  signature nor the error type. Two other specs co-own the `[load]` table, so
  the task's first step is to confirm one reader exists there and stop rather
  than add a second — the invariant is one reader per table, never two, and
  resolving a collision is a coordination decision, not something a task may
  silently paper over.
- **Task 2.1 depends on the shipped training-impulse metric staying where it
  is.** The pending fit-ingest re-sourcing of its coefficients is deliberately
  *not* in this plan; this feature is built so that update changes the shipped
  metric and the heart-rate load together. If that update makes the weighting
  sex-dependent, the weighting seam needs an athlete input this feature does not
  have — flagged to the fit-ingest owner.
- **Task 1.2's result vocabulary is `threshold-load`'s and
  `activity-qa-flags`' input.** Those specs consume the outcome union and the
  reason set directly, so any later change to either is a revalidation trigger
  for both. The reported intensity is defined here to be dimensionless, exactly
  1.0 at threshold, and to satisfy `load = hours × intensity² × 100` on **every**
  channel — that single semantic, and not merely the threshold identity, is what
  makes `activity-qa-flags`' cross-channel divergence comparison valid away from
  threshold and what makes `threshold-load`'s single `"Intensity"` label in
  `inputs_used` mean one thing. Task 3.2 takes the square root of the heart-rate
  impulse ratio for exactly this reason; task 5.3 is the assertion that keeps it
  true.
- **Task 1.1 defines the third verification status,
  `chosen-by-fitdocs-and-measured`, that `activity-qa-flags` needs.** That spec
  merely *uses* the member for its own measured defaults; it neither widens this
  enum nor edits `tests/load/channels/test_sources.py`, both of which belong to
  this spec. This spec's own citations are unaffected by that third member — no
  citation here carries it. _(The claim this bullet originally made about the
  first two members was stale independently of that: it said "the Minetti and
  Banister citations stay secondary-attested", which `MINETTI_2002`'s
  2026-07-27 re-sourcing had already falsified for Minetti before this
  correction, and `BANISTER_TRIMP`'s 2026-07-29 re-sourcing (queue
  2026-07-27-banister-morton-primary-texts-obtained) now falsifies for
  Banister too. Corrected: this module's citation vocabulary today carries no
  `SECONDARY_ATTESTATION` record at all, and `BLOCKED_CITATIONS` is the empty
  set kept in place as the mechanism's honest remainder.)_
- **Task 1.3's coverage figure differs from the sample-count percentage the
  shipped document renderer displays** under non-uniform sampling. The render
  layer is out of boundary here; `activity-qa-flags` is the natural place to
  surface the gate's own figure if the two ever need reconciling.

## Implementation Notes

- **Never use `hasattr` to assert a dataclass field is absent.** A field
  declared without a default is an annotation only, never a class attribute, so
  `hasattr(Cls, "x")` is `False` whether or not the field exists — the
  assertion passes under both states and pins nothing. Task 1.1 shipped
  `assert not hasattr(Divergence, "key")` for Req 8.8 and it was caught only by
  mutation testing. Use `{f.name for f in dataclasses.fields(Cls)}`. This
  matters again wherever a task asserts a type's shape rather than its values.
- **Prove new assertions can fail before claiming a task done.** Task 1.1's
  first round also shipped `assert module is not None` and
  `assert not hasattr(sources, "compute")`, neither of which any code change
  could break. Mutation-test the assertion, don't eyeball it.
- **`mypy` is `strict = true` in `pyproject.toml`**, so `uv run mypy src/`
  already satisfies design references to `mypy --strict`; the two are the same
  run in this repo.
- **`field.default is MISSING` does not pin a field as required.** Switching the
  field to `dataclasses.field(default_factory=...)` leaves that assertion green
  while making the field omittable — proved on task 1.2 by constructing
  `ChannelLoad` with `coverage` absent, full suite still green. Assert
  `default_factory is MISSING` too, and add a positive control that omitting the
  field raises `TypeError`. Same family as the `hasattr` trap above: the natural
  spelling of the guard is blind in exactly the direction that matters.
- **An AST import guard must resolve relative spellings.** Matching only
  absolute dotted names misses `from .. import settings` (`node.module` is
  `None`, `level > 0`) and `from ..settings import X` (`node.module ==
  "settings"`, so `.endswith(".settings")` never fires); both resolve to the
  forbidden module at runtime and both passed green on task 1.2. Record
  `"." * node.level + (node.module or "")` plus each alias and match with
  `re.search(r"(^|\.)settings$", ...)`. Tasks 4.1/4.2 own the runtime
  import-graph assertion, which is the only thing that can see
  `importlib.import_module(...)` — a static walk cannot, by construction.
- **An enum- or string-valued field asserted against ONE value pins only "not
  that value".** Task 1.3 hardcoded `channel=ChannelId.POWER` at all three
  `ChannelInsufficient` sites and the suite reddened — but hardcoding
  `ChannelId.HEART_RATE` instead left all 2348 green, because every new
  assertion named the same member. Tied values, per change-protocol.md. Assert
  each caller-derived field against **pairwise-distinct** values, and verify by
  hardcoding to *each* other legal member, at *every* construction site
  (three branches each built their own result here). Tasks 3.1/3.2/3.3 build
  results the same way and inherit this exactly.
- **Sweep per field × per site; do not patch the spots a reviewer named.** On
  1.3 the reviewer found `channel` and `detail` confounded; the exhaustive
  sweep that followed found two more it had not — `required` tied at 60.0
  across both TOO_SHORT fixtures, and `observed` a single-point pin at
  STREAM_COVERAGE — each confirmed by running the hardcode before the fix and
  watching it pass. Incremental discovery on this class does not terminate.
- **"There is no code to mutate away" is not evidence.** 1.3 declared Req 2.3
  UNPINNED because no resampling existed to remove; *introducing* a forward-fill
  pass reddened 9 tests. It was pinned all along. Add the thing the requirement
  forbids and see whether anything objects.
- **A test that restates the formula instead of reading it cannot fail.** Task
  1.2 shipped a "worked example" asserting `32.0 == 32.0` with no reference to
  any production symbol. Extract the relation from the module source and
  evaluate *that*, so `** 2` → `** 3` reds the value; and assert the extraction
  matched, or a regex that finds nothing is a vacuous walk in new clothing.
- **A value-equality assertion does not pin a delegation contract.** Task 2.1's
  whole reason to exist (Req 5.4) is that two training-impulse computations
  cannot coexist in the tool, yet `assert seam_value == trimp(...)` was
  satisfied *by construction* by a duplicate implementation: the reviewer
  replaced one method with a restated closed form and the other with a full
  independent integration loop — neither calling `trimp` — and both left the
  suite green. Rescaling the shipped coefficient and watching both outputs move
  proves the arithmetic is wired, not that the call path is the shipped one.
  Pin the path: monkeypatch the shipped function with a recording double,
  assert it was called once with the caller's exact object by `is` identity,
  and that its `.value` came back unmodified. Verify the patch is not a no-op
  by rebinding production to a locally-imported alias. Tasks 3.1/3.2/3.3
  delegate to `normalized_power`/`trimp`/pace the same way and inherit this.
- **Re-run the old guard's mutations before deleting it.** Task 2.1 replaced a
  substring literal scan with a strictly better AST scan — which then could not
  see comments or docstrings, silently regressing two round-1 catches to green,
  one of them the module's own written promise to restate the coefficients
  "not even in prose". Neither guard subsumes the other (`.64` is AST-visible
  and textually absent; a comment is textual and AST-invisible), so both ship.
  A replacement that improves one axis and vacates another reads as progress
  and is the oscillation shape § 5.6 warns does not terminate.
- **A helper shared by two guards is a single point of failure across both.**
  The paired scans read their values off `WEIGHTING_PAIRS` via one helper; if
  it resolved empty, both would pass blind. It carries
  `assert len(disputed_values) >= 4` so it fails loudly instead — the
  vacuous-walk rule applied one level up, at the fixture source rather than the
  walk.
- **A line-range pointer into a spec doc breaks on any edit above it.** Task
  2.1 amended `design.md` and invalidated, inside its own diff, the one pointer
  that indexed `design.md` by line — the repo's most-repeated defect species,
  self-inflicted in a single change. Cite the section heading; if a range is
  kept, re-verify both boundary lines with `sed -n '<a>p;<b>p'` after any edit
  to that file.
- **`is`-identity does not pin a derivation between float constants.** CPython
  folds equal float literals within a module to one object, so
  `assert LEVEL_COST is COEFFICIENTS[-1]` passes whether the constant is
  derived from the tuple or retyped as `3.6` — measured on task 2.2, where it
  was the reviewer's own proposed remediation and could not have failed. Pin
  the *shape* instead: walk the module's AST and assert the constant's value is
  a `Subscript` into the coefficient tuple. Same family as `hasattr` on a
  dataclass field and `dir()` on a Protocol — the natural spelling of the
  guard is blind in exactly the direction that matters.
- **A guard replacement trades axes unless you re-run the old mutations.**
  Task 2.2 needed three rounds on one documentation guard, each fix correct on
  the axis it targeted and blind on a new one: raw substring absence passed
  because the forbidden phrase wrapped across a line; whitespace normalisation
  fixed that but keyed on a fixed 200-character radius, so a false claim
  planted just after the legitimate sentence inherited its tokens; sentence
  containment closed that and admits only same-sentence splicing, which is the
  definitional limit and is documented rather than iterated on. Before deleting
  a guard, run the mutations it caught against its replacement.
- **`re.split(r"(?<=\.)\s+", ...)` splits on abbreviations and decimals.**
  `grade.py`'s own citation prose ("Fig. 1 caption (p. 1041)") fragments under
  it. It is safe here only because the rule requires *every* fragment holding
  the phrase to carry the exculpating tokens, so a mis-split fails toward a
  loud red naming the offending sentence, never toward a silent pass. Check the
  failure *direction* of any text-fragmenting guard before trusting it.
- **A test that reds via `TypeError` may be pinning the absence of a crash.**
  Task 2.2's undefined-altitude guard reddened with `float - None` when
  deleted, which proves the branch is reached but not what it contributes.
  Assert the value the branch produces as well, or a later implementation that
  returns a wrong number quietly passes.
