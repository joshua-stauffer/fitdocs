# Implementation Plan

> **Amended 2026-07-25 (Amendment 1, cross-spec review).** Task 1.3 is
> **withdrawn**: `training-load` Amendment 3 carries the resolved `[load]`
> configuration and the activity date to a calculator on a per-activity
> `LoadContext`, so this feature adds nothing to `ProfileView` and edits neither
> `load/types.py`, `load/profile.py` nor `load/engine.py`. Its requirement
> coverage (1.6, 5.3) moves to task 3.3. Tasks 3.2 and 3.3 gain the amended
> details: the coverage figure names its basis, the single `Intensity` label is
> now honest across channels, the not-computed variant is `NotComputed`, and the
> calculator defines an optional, off-Protocol `supports(activity)` that the
> engine reaches through `supports_activity`. See requirements.md Amendment 1 and
> design.md Amendment 2.

## Upstream Prerequisites

Every task below consumes contracts three other specs deliver. None of them is
implemented yet, and this plan does not re-specify them:

- **`athlete-benchmarks`** — `fitdocs.benchmarks` (`Benchmark`, `BenchmarkKind`,
  the athlete-wide scope), `ProfileView.{benchmark, has_benchmark}` (a pure
  store view: `activity_date` and `staleness_window_days` move off it under
  `training-load` Amendment 3), and `AthleteField.benchmark` / `BenchmarkRef`.
- **`load-channels`** — `fitdocs.load.channels` (`ChannelId`, `ChannelLoad`,
  `ChannelInsufficient`, `InsufficiencyReason`, `SufficiencySettings`, and the
  three `compute` entry points), each channel reporting an intensity on the one
  shared semantic and a time-weighted coverage.
- **`training-load`** — the redefined `LoadResult`, `NonSelectedValue`,
  `QualityFlag`, the arbitration path, `src/fitdocs/load/settings.py` with
  `load_load_settings(document, settings_file) -> LoadSettings`,
  `LoadSettingsError` and the `default_calculator` key, and — from Amendment 3 —
  `LoadContext(activity_date, settings)` on `compute`, the module-level
  `supports_activity(calculator, activity)` seam (**not** a protocol member — see
  design.md Amendment 2), and the `NotConfirmed` → `NotComputed` rename.

**One shared module**: `src/fitdocs/load/settings.py` is owned by
`training-load`, which pins the reader's name and signature. Task 1.2 **extends
that one reader and creates no second module and no second reader**. If it has
not landed when task 1.2 starts, stop and sequence the upstream spec rather than
creating a variant.

**Hard prerequisite for task 3.3**: `LoadContext` — **satisfied**, it landed in
`training-load`. Without it there is no way to reach the configuration, and the
earlier workaround — `ProfileView.load_settings` — is withdrawn.

*Repinned 2026-07-26 (design.md Amendment 2).* This prerequisite previously also
named "the `supports` protocol member". **That member does not exist and never
will** — `training-load` reversed the clause on measured grounds and deleted the
declaration in `3121bb6`; `hasattr(LoadCalculator, "supports")` is `False`.
Nothing here is blocked by it: the capability moved to the module-level
`supports_activity(calculator, activity)` (`src/fitdocs/load/types.py:378`),
which finds a calculator's own optional, off-Protocol `supports` by `getattr`.
Task 3.3 writes that method exactly as designed. **Do not add the member to the
Protocol** — that re-lands the drift `3121bb6` removed and breaks structural
conformance for every existing stub and the installed plugin fixture.

## Test File Ownership

Each task owns exactly one test module, so no two tasks write the same
assertions. `tests/load/test_priority.py` → 1.1; `tests/load/test_settings.py`
(`training-load`'s module for the `[load]` reader, extended) → 1.2;
`tests/load/threshold/test_discipline.py` → 2.1;
`tests/load/threshold/test_selection.py` → 2.2;
`tests/load/threshold/test_anchors.py` → 2.3;
`tests/load/threshold/test_fields.py` → 3.1;
`tests/load/threshold/test_result_assembly.py` → 3.2;
`tests/load/threshold/test_calculator.py` → 3.3;
`tests/load/threshold/test_registration.py` → 4.1;
`tests/load/threshold/test_anchoring_e2e.py` → 5.1;
`tests/load/threshold/test_outcomes.py` → 5.2;
`tests/load/threshold/test_feature_e2e.py` → 5.3;
`tests/load/threshold/test_boundary.py` → 5.4. The one shared module *modified*
rather than owned is `tests/test_public_api.py`, edited by task 4.1 alone.

**Shared source file**: tasks 3.1, 3.2 and 3.3 all write
`src/fitdocs/load/threshold/calculator.py` under three different component
boundaries. The boundaries are *responsibility* boundaries, not file boundaries,
so none of the three may be promoted to `(P)` without first splitting the module.
They are deliberately kept strictly sequential for that reason.

- [ ] 1. Foundation: the configuration value, its reader, and the path that
      carries it to a calculator

- [x] 1.1 Create the channel-priority value with its documented defaults
  - Add a leaf module holding the per-discipline channel ordering as an
    immutable, comparable value: a mapping from discipline to an ordered tuple of
    channel identifiers, with a lookup that returns the empty ordering for a
    discipline this calculator does not support
  - Define the documented defaults for all four supported disciplines — running
    prefers pace then power then heart rate, cycling prefers power then heart
    rate, and walking and hiking name heart rate alone — and record at the
    constant why running does not default to power: fitdocs reads a running power
    stream the interop target does not ingest, so a power-first default would make
    every run's headline number unreproducible elsewhere
  - Keep the module a leaf: it may import the sport vocabulary and the channel
    identifiers and nothing else from the load layer, because the settings reader
    must import it without pulling in the calculator
  - Observable: a default-constructed priority value equals the documented
    defaults, every supported discipline has a non-empty order, an unsupported
    discipline yields an empty order, and two equal configurations compare equal
  - _Requirements: 7.3, 7.4_
  - _Boundary: ChannelPriorityValue_

- [x] 1.2 Extend the load configuration reader with the priority table
  - Add the channel-priority member to the **single existing** load settings
    value and teach the **single existing** reader to project and validate the
    priority sub-table; create no second module, no second reader, and open no
    file
  - Apply the documented defaults during projection so the produced value is
    complete over every supported discipline, with configured entries overriding
    defaults
  - Reject, as configuration errors naming the file, the key and the offending
    value: a non-table priority section, a key that is not a recognized sport or
    is a sport this calculator does not support, a value that is not a list, an
    element that is not a string, an unrecognized channel name, a repeated
    channel, and an empty list
  - Accept a valid-but-futile order such as a pace channel configured for cycling
    — it is not a configuration error, and those activities report the channel's
    own reason instead
  - Preserve the additivity contract: unknown keys and unknown sub-tables inside
    the load table stay ignored so the sibling features' keys land independently
  - Observable: an absent settings file, an absent load table, an absent priority
    section and an absent discipline entry all yield the documented defaults with
    no error; each malformed form above raises the configuration error type
    naming file, key and value; and a document carrying the priority, sufficiency
    and flag sub-tables together with the default-calculator key parses cleanly
  - _Requirements: 7.1, 7.2, 7.5, 7.6, 7.7, 7.8, 7.9_
  - _Boundary: PrioritySettingsReader_

> **Task 1.3 withdrawn (Amendment 1).** It added the resolved load configuration
> as a `ProfileView` member and bound it in the load pass, because `compute`'s
> parameter list carried no configuration. `training-load` Amendment 3 supplies
> `LoadContext(activity_date, settings)` instead, so there is nothing to add:
> `load/types.py`, `load/profile.py` and `load/engine.py` are untouched by this
> feature. Its requirements (1.6, 5.3) are covered by task 3.3, which reads both
> values off the context. No task is renumbered — 1.3 was the last task in its
> group — and the dependency edge that pointed at it now points at 1.2.

- [ ] 2. Policy: the tables, the walk, and benchmark resolution

- [x] 2.1 (P) Declare which activities are scored and what anchors them
  - Add the supported-sport set — running, cycling, walking and hiking — and the
    coarser movement-modality set the calculator declares to the registry, and
    record why they differ: walking and hiking share a catch-all modality with
    rowing and generic workouts, so the sport set has to be the authoritative one
    and strength training is deliberately left undeclared so it never reaches the
    calculator at all
  - Add the per-sport anchor plan: for each of threshold power, threshold heart
    rate and threshold pace, the ordered chain of disciplines whose benchmark may
    anchor that channel, where an empty chain states that the quantity does not
    anchor that sport
  - Populate the plans: running and cycling anchor on themselves; walking and
    hiking anchor their heart-rate channel on their own discipline first and the
    running discipline second, and have no power and no pace anchor at all
  - Record at the tables why the walk and hike chains exist — the benchmark store
    never falls back across disciplines, so without an explicit chain those
    activities are unscorable — and why their power and pace chains are empty:
    a walking watt scaled against a running threshold is the same
    computable-but-meaningless number strength training was refused for
  - Observable: the supported-sport set and the anchor-plan table have identical
    key sets, walking and hiking each carry an empty power chain, an empty pace
    chain and a two-element heart-rate chain whose first element is their own
    sport, and running and cycling anchor only on themselves
  - _Requirements: 2.1, 2.4, 2.6, 3.1, 3.2, 3.5_
  - _Boundary: DisciplineSupport_

- [x] 2.2 (P) Implement the priority walk and the non-selected records
  - Add a pure selection function that walks the configured order for a
    discipline and returns the first channel that produced a computed load, or
    nothing when none did — reading only membership in the order and whether an
    outcome is a computed load, never a load value, an intensity, a coverage
    figure or a benchmark date
  - Add a pure companion that records every channel other than the selected one
    exactly once, in a canonical channel order that does not depend on the
    configured order, so two differently-configured data roots still produce
    diffable documents
  - Give each non-selected record its reason: a computed channel that a
    higher-priority channel beat, a computed channel that is absent from the
    configured order, or an uncomputed channel carrying the channel layer's own
    explanation verbatim with no number in place of the absent value
  - Fold the channel outcome union exhaustively so a future variant is a static
    error rather than a silent gap
  - Observable: the first computed channel in the order wins while earlier
    uncomputed ones are skipped; a computed channel outside the order is never
    selected; an all-uncomputed mapping selects nothing; altering a non-selected
    channel's load value leaves the selection and the selected value unchanged;
    and the non-selected records always appear in the canonical order regardless
    of configuration
  - _Requirements: 5.4, 5.5, 5.6, 5.7, 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 8.3, 8.4, 8.5, 8.9_
  - _Boundary: ChannelSelection_

- [x] 2.3 Resolve an activity's benchmarks from its sport and its own date
  - Add the one module that asks the benchmark store for values: for each
    quantity, walk that sport's discipline chain and take the first benchmark
    applicable on the activity's own local calendar date, asking one discipline
    at a time so the store's never-fall-back rule stays intact and the fallback
    is visibly this feature's own
  - Resolve the maximum and resting heart rate in the athlete-wide scope, which
    carries no discipline
  - Classify every absence into three distinguishable states the caller can act
    on differently — resolved but borrowed from another discipline, no benchmark
    of that kind on file anywhere in the chain, and one on file but none dated on
    or before the activity — and record the borrowings naming both disciplines
  - Take the activity date as an argument sourced from the per-activity context
    the calculator contract supplies rather than from the activity's recorded
    start instant, so scoring agrees with the date the document is named from,
    and read no clock
  - Contribute nothing to either absence list for a quantity whose chain is
    empty: it was never sought
  - Observable: with a threshold measured in 2026 and another in 2024, a
    2024-dated activity resolves the 2024 entry and a 2026-dated one resolves the
    2026 entry; a walk with only a running threshold on file resolves it and
    records the borrowing; a benchmark measured after the activity is reported as
    not-applicable rather than as not-on-file; and repeated calls with equal
    inputs are equal
  - _Requirements: 3.3, 3.4, 3.6, 4.1, 4.2, 4.4, 4.5, 4.6_
  - _Boundary: BenchmarkResolution_
  - _Depends: 2.1_

- [ ] 3. The calculator: declaration, computation and assembly

- [x] 3.1 Declare the athlete inputs the prompt flow must collect
  - Declare the seven benchmarks required to score the supported disciplines —
    running and cycling threshold power, running and cycling threshold heart
    rate, running threshold pace, and the athlete-wide maximum and resting heart
    rate — each carrying the benchmark it collects, a label, a validation range
    and help text that names the discipline plainly and says how the value is
    measured
  - Declare no walking or hiking threshold heart rate: those only refine an
    anchor the chain already resolves, and declaring them would prompt for a
    threshold the tool does not need
  - Observable: the declared set is exactly the quantities reachable through a
    non-empty anchor chain plus the two athlete-wide heart-rate quantities,
    asserted against the anchor-plan table so that adding a chain entry without
    declaring its field fails the suite; every field carries a benchmark
    reference, a bounded range and non-empty help text
  - _Requirements: 9.1, 9.2, 9.3_
  - _Boundary: AthleteFieldDeclaration_
  - _Depends: 2.1_

- [x] 3.2 Assemble the selected value and its diagnostics into the result
  - Build the contract's computed result in one place: the selected channel's
    load verbatim as the one value that counts, the selected channel's identity
    as the basis, the non-selected records from the selection step, and an empty
    quality-flag set with no placeholder entries
  - Record among the inputs the selected channel, the configured order it came
    from, the channel's intensity relative to threshold, the scored duration and
    the observed stream coverage, followed by the channel's own reported inputs —
    which already carry the anchoring value, its discipline and its measurement
    date
  - Record the intensity under one label whose meaning does not depend on which
    channel was selected: emit the channel's reported intensity verbatim,
    neither rescaled nor per-channel qualified, which is honest because the
    channel layer now defines one intensity semantic for all three channels —
    dimensionless, exactly 1.0 at threshold, with the load equal to the scored
    hours times the square of the intensity times one hundred
  - Name the basis on the coverage figure — for example
    `"distance 99.8% of recorded time"`, never a bare percentage — because the
    channel layer measures coverage over recorded time while the workout
    document's own coverage table counts samples, the two differ under
    non-uniform sampling, both are correct for their own question, and this
    figure lands in the same document as that table
  - Record as notes the qualifying facts that do not change the number: each
    borrowed anchor naming both disciplines, then the selected channel's own
    notes prefixed with the channel name
  - Add deterministic formatters for intensity, coverage and duration, so
    identical computations produce identical records
  - Do not add a flags parameter today: it is an additive signature change when
    the quality-flag feature lands, whereas an always-empty parameter now would
    be anticipatory dead code
  - Observable: a result built from a selected channel carries that channel's
    exact load and no other number of its own; every non-selected channel appears
    exactly once; a borrowed anchor produces a note naming both disciplines; the
    flag set is empty; the recorded intensity equals the selected channel's
    reported intensity for a heart-rate selection as well as for a power one;
    the coverage input names its basis; and building the same result twice
    produces equal records field for field
  - _Requirements: 3.7, 6.6, 8.1, 8.2, 8.6, 8.7, 8.8, 8.9, 8.10, 8.11, 8.12, 10.3, 10.4_
  - _Boundary: ResultAssembly_
  - _Depends: 2.2, 2.3_

- [x] 3.3 Implement the calculator's decision sequence
  - Answer the contract's support question for a given activity from the
    supported-sport set, overriding the protocol's modality-test default: the
    load pass asks it **before** the prompt flow, so a rowing or generic-workout
    document — which shares the catch-all modality this calculator must declare
    to reach walking and hiking — is refused without costing the athlete a
    question
  - Read the activity's local calendar date and the resolved load configuration
    from the per-activity context the contract supplies, and open, locate or
    re-read no settings or profile file; take the configured channel order and
    the sufficiency configuration from that same value
  - Implement the contract's compute step in a fixed order: refuse an unsupported
    sport by name first — retained as defence in depth now that the support
    answer screens the same condition earlier — so it costs no lookup and no
    channel call; then refuse an activity carrying no local calendar date with a
    reason naming the absent date; then resolve the anchors; then evaluate **all
    three** channels with those anchors and the resolved sufficiency
    configuration, passing each channel's outcome forward unmodified
  - Evaluate every channel regardless of what the configured order prefers, so
    the diagnostics are complete and the heart-rate outcome exists even when
    another channel is selected — the comparison the planned quality-flag feature
    depends on
  - Apply no sufficiency rule, no rounding and no adjustment of a channel's
    reported load or intensity
  - When nothing was selected, distinguish the two honest outcomes: report
    missing inputs naming the declared fields when a channel in the configured
    order was blocked by a benchmark that is not on file at all, and otherwise
    report not-computed with a reason naming every evaluated channel and why it
    produced no value
  - Use the contract's existing closed outcome set unchanged, naming the
    not-computed variant by its current identifier — renamed upstream from the
    old confirmation-flavoured one — and record in the module why the
    not-computed case rides that variant rather than the unsupported or
    missing-inputs one
  - Never raise, never prompt, never persist, and never use the interaction
    session
  - Observable: the support answer is true for running, cycling, walking and
    hiking and false for rowing, generic workouts, swimming, strength training
    and an unrecognized sport, and agrees with what compute refuses; a strength
    or rowing activity yields the unsupported outcome naming its sport; an
    undated document yields not-computed naming the missing date; a run with
    power, heart rate and distance produces three channel outcomes and one
    selection; a stub context carrying a non-default priority and a non-default
    sufficiency minimum is observed to reach the selection and the channels
    respectively; each channel is observed to receive an already-resolved
    benchmark object rather than any means of resolving one; and the same inputs
    produce the same outcome and the same reason string on every call
  - _Requirements: 1.4, 1.5, 1.6, 1.7, 2.2, 2.3, 2.5, 2.7, 4.2, 4.3, 5.1, 5.2, 5.3, 5.4, 6.7, 9.4, 9.5, 9.6, 9.7, 10.1, 10.2, 10.5, 10.6_
  - _Boundary: ThresholdCalculator_
  - _Depends: 1.2, 2.2, 2.3, 3.1, 3.2_

- [ ] 4. Integration: registration and the published surface

- [x] 4.1 Register the built-in and republish the surface
  - Register the calculator from the load package's initializer so that importing
    the load layer makes it available, and keep the calculator module itself free
    of registration side effects so importing it for a test mutates no global
    state
  - Export the calculator on the published plugin surface and update the pin that
    guards that surface — the calculator export only: this feature adds no
    profile-view member
  - Confirm the built-in needs no privilege a third-party author lacks: it passes
    the same registration validation, and the plugin inventory reports it as a
    built-in at the installed fitdocs version with no change to the inventory code
  - Update the upstream invariant this supersedes: the load layer's registry is
    no longer empty of built-ins, and the assertions stating that it is become
    assertions naming this one
  - Observable: a fresh interpreter reports exactly one registered calculator
    under the identifier `threshold`; the registration validator accepts it; the
    plugin inventory lists it as built-in at the fitdocs version; and the public
    surface test passes against the new shape
  - _Requirements: 1.1, 1.2, 1.3, 11.2, 11.3_
  - _Boundary: BuiltInRegistration, PublicSurfacePin_
  - _Depends: 3.3_

- [ ] 5. Validation

- [ ] 5.1 (P) Prove anchoring and fallback against realistic data
  - Assert the hardware-boundary case end to end: two running threshold-power
    entries measured years apart, with each dated activity scored against the
    entry current at its own date, and regeneration resolving identically
  - Assert the walk and hike anchoring policy: a walk with only a running
    threshold heart rate on file is scored and records the borrowing note; adding
    a walking threshold flips the anchor to it and drops the note; and a walk
    with a full power stream and a running threshold power on file still reports
    the power channel's no-benchmark reason and is scored from heart rate
  - Assert the fallback walk in both directions: a run with no usable distance
    data falls from pace to power, and a ride with no power falls from power to
    heart rate, each asserting the recorded basis, the non-selected entries and
    their reasons
  - Assert that a run selected on pace still records a heart-rate value, which is
    the comparison the planned quality-flag feature consumes
  - Observable: each scenario produces the expected basis, the expected
    non-selected entries with their reasons, and the expected notes
  - _Requirements: 3.3, 3.4, 4.1, 4.4, 6.2, 6.3, 6.4_
  - _Boundary: BenchmarkResolution, ChannelSelection, ThresholdCalculator_
  - _Depends: 3.3_

- [ ] 5.2 (P) Prove the honest outcomes for everything that cannot be scored
  - Cover, one case each: an unsupported sport by name; a strength activity
    reaching the honest unsupported state without the calculator being invoked;
    a rowing document — inside the declared catch-all modality — refused by the
    support answer with **no prompt asked for it** on an interactive pass; an
    undated document; every channel insufficient with the blockers on file;
    every channel insufficient with a required benchmark never on file; and a
    benchmark on file whose only entry postdates the activity
  - Assert the two absence cases are reported differently — missing inputs naming
    the declared fields versus not-computed with the distinguishing reason — and
    that the second is never reported as missing inputs
  - Assert that no path emits a zero, a default or a placeholder load, and that
    an activity reported not-computed is scored normally once the missing data is
    supplied
  - Observable: every case above produces the stated outcome with the stated
    reason, no case produces a number, and the retry case computes on a second
    pass with no other change
  - _Requirements: 2.2, 2.3, 2.7, 9.4, 9.5, 10.1, 10.2, 10.3, 10.4, 10.5, 10.6_
  - _Boundary: ThresholdCalculator_
  - _Depends: 4.1_

- [ ] 5.3 (P) Prove the feature through a real load pass
  - Run a load pass over a data root holding running, cycling, walking, hiking,
    strength and rowing documents with a populated benchmark file, and assert the
    four scored documents carry the expected bases while strength and rowing
    carry the honest unsupported state naming their sports
  - Assert the configuration path end to end: a tightened sufficiency minimum
    flips a channel from computed to uncomputed, and a reconfigured priority
    changes which channel is selected without changing any computed value
  - Assert the configuration gate: a data root whose settings file carries a
    malformed priority entry aborts the pass with the configuration exit code and
    leaves **every** document byte-identical, proving the validation happens
    before any write rather than per document
  - Assert determinism: the same data root scored twice produces byte-identical
    documents and the second pass performs no writes
  - Observable: the pass completes cleanly, the report buckets match the
    expectation per document, the malformed-configuration run writes nothing at
    all, and the repeated pass is a no-op
  - _Requirements: 1.3, 1.4, 7.8, 7.9, 8.9_
  - _Boundary: ThresholdCalculator, BuiltInRegistration_
  - _Depends: 4.1_

- [ ] 5.4 Close the boundary guards and the quality gates
  - Assert the import boundary: the priority leaf pulls in no calculator module;
    no module in this feature imports the CLI, the renderer, the load pass, the
    document editor or the load-section renderer; and no module in this feature
    references a filesystem, network, clock, prompting or language-model API
  - Assert the permanent exclusion structurally as well as behaviourally: no
    module in this feature reads two channels' load values in one expression, and
    altering a non-selected channel's value provably changes nothing about the
    result
  - Assert the feature writes no document, defines no result type, consults no
    registry during computation, writes no benchmark, detects no quality
    condition and aggregates nothing
  - Run the full suite with the linter and the strict type checker clean, and
    regenerate only the golden documents that now carry a computed load
  - Observable: the boundary tests pass, the full suite is green, and the linter
    and strict type checker report no findings
  - _Requirements: 1.5, 11.1, 11.2, 11.3, 11.4, 11.5, 11.6, 11.7_
  - _Boundary: all components (read-only subjects)_
  - _Depends: 5.1, 5.2, 5.3_
