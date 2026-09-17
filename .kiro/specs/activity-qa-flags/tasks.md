# Implementation Plan

## Amendments — 2026-07-25 cross-spec review

Applied throughout this plan; the reasoning is in `requirements.md` and
`design.md`:

- The **import-cycle invariant is withdrawn** (its original cause,
  `ProfileView.load_settings`, is removed by `training-load` Amendment 3 in
  favour of a per-pass `LoadContext`). A second edge did survive that removal —
  `LoadContext.settings` keeps `load/types.py → load/settings.py` alive and
  `load/settings.py` must reach into this package for `FlagSettings`, which runs
  this package's initializer. That cycle was real and the review reproduced it,
  on **every** entry point rather than only when `load.types` is imported first.
  It is cut upstream, in `training-load`, by a `TYPE_CHECKING`-only import of
  `LoadSettings` in `src/fitdocs/load/types.py`. Consequently task 1.1 creates an
  **ordinary eager** package initializer, task 3.1 adds a plain `from .flags
  import evaluate_flags` to it — no module-level `__getattr__`, no
  `TYPE_CHECKING` shim — and task 1.3 adds **no** import assertion at all:
  `training-load` owns the single fresh-interpreter guard, extending the
  existing `subprocess.run([sys.executable, "-c", ...])` check at
  `tests/test_public_api.py:353` to cover `import fitdocs.load.qa` and `import
  fitdocs.load.types`.
- The **`src/fitdocs/load/settings.py` ownership pin is recorded**: the module
  belongs to `training-load` task 3.1, not to `athlete-benchmarks`. The
  prerequisite bullets and the task 1.3 stop-condition below name the right
  spec.
- Task 1.2 **no longer edits `load-channels`**: that spec's task 1.1 defines all
  three `VerificationStatus` members, including `FITDOCS_MEASURED`. This feature
  consumes the status only.
- Task 1.2 gains the **provisional-defaults record** (Req 6.10, 6.11) and the
  two withdrawn brief claims (Req 3.10, 4.5).
- Task 2.3 gains the **sub-threshold agreement regression** (Req 3.9) that pins
  the corrected shared intensity semantic.
- Tasks 2.5 and 3.2 read the activity date and the staleness window from the
  `LoadContext`, not from the profile view.

## Amendment — 2026-09-16: retroactive anchors

`athlete-benchmarks` Amendment 1 retired the premise behind task 2.5's
ordering guard: `benchmark_age` no longer raises for a benchmark measured after
the activity — it returns a negative age, and selection yields such an anchor
only when the athlete declared it to apply retroactively. Task 2.5 no longer
guards the ordering and instead surfaces a negative age as the reading's own
retroactive outcome; task 3.1 maps that outcome to *not-detected* and its basis
states both dates. New criterion 5.8 is traced to both. No task added or
removed.

## Upstream Prerequisites

Every task below consumes contracts three other Phase 4 specs deliver, none of
them implemented yet. This plan re-specifies none of them:

- **`athlete-benchmarks`** — `fitdocs.benchmarks` (`Benchmark`, `BenchmarkAge`,
  `benchmark_age`), and the `benchmark_staleness_days` member it adds to
  `LoadSettings` (the module itself is `training-load`'s — see below).
- **`load-channels`** — `fitdocs.load.channels` (`ChannelId`, `ChannelLoad`,
  `ChannelInsufficient`, `ChannelOutcome`, `StreamCoverage`,
  `sufficiency.stream_coverage`); `channels/sources.py` (`Citation`,
  `Divergence`, and `VerificationStatus` with **all three** members, the third
  being the fitdocs-measured status this feature consumes); and the **shared
  intensity semantic** its Requirement 1.11 pins — one dimensionless intensity,
  exactly 1.0 at threshold, with `load == hours × intensity² × 100` on every
  channel. Task 2.3 depends on that semantic directly and its regression case
  fails without it.
- **`threshold-load`** — `src/fitdocs/load/threshold/calculator.py` with
  `build_result` and `ThresholdCalculator.compute`, plus the end-to-end fixture
  data root its task 5.3 builds (a run `.fit` fixture, a dated benchmark file
  and `[load]` settings that together reach the computed path).
- **`training-load`** — the redefined `LoadResult` and `QualityFlag`, the
  `LoadContext` carrying the activity date and the resolved load settings into
  `compute`, the load pass, and the section renderer that already renders a
  flags block. **It also owns `src/fitdocs/load/settings.py`** (its task 3.1),
  which pins the surface every sibling extends:

  ```python
  load_load_settings(document: Mapping[str, object], settings_file: Path) -> LoadSettings
  class LoadSettingsError(SettingsError): ...
  DEFAULT_LOAD_SETTINGS: Final[LoadSettings]   # every field defaulted
  ```

  Unknown keys **and** unknown sub-tables are ignored, so this feature's
  `[load.flags]` keys are an extension of that one `LoadSettings` dataclass read
  by that one `load_load_settings`. No second reader may exist. It also owns the
  `TYPE_CHECKING`-only import of `LoadSettings` in `src/fitdocs/load/types.py`
  and the fresh-interpreter subprocess import guard in
  `tests/test_public_api.py`.

If `src/fitdocs/load/settings.py` does not exist when task 1.3 starts, stop and
sequence `training-load` (its task 3.1) rather than creating a fourth variant of
the same reader. If `threshold-load`'s computed-path fixture data root does not exist when
task 4.2 starts, that task builds one rather than assuming it.

## Test File Ownership

Each task owns exactly one test module, so no two tasks write the same
assertions. `tests/load/qa/__init__.py` and `tests/load/qa/test_types.py` → 1.1;
`tests/load/qa/test_sources.py` → 1.2 — and **no** test module belonging to
another spec: `tests/load/channels/test_sources.py` is `load-channels`' and is
not touched here;
`tests/load/test_settings.py` (existing, extended) → 1.3;
`tests/load/qa/conftest.py` and `tests/load/qa/test_cadence_spans.py` → 2.1;
`tests/load/qa/test_cadence.py` → 2.2; `tests/load/qa/test_divergence.py` → 2.3;
`tests/load/qa/test_drift.py` → 2.4; `tests/load/qa/test_staleness.py` → 2.5;
`tests/load/qa/test_flags.py` → 3.1;
`tests/load/threshold/test_calculator.py` (existing, extended) → 3.2;
`tests/test_public_api.py` (existing, modified) → 3.3;
`tests/load/qa/test_corpus_negatives.py` → 4.1;
`tests/load/qa/test_feature_e2e.py` → 4.2;
`tests/load/qa/test_purity.py` → 4.3.

**Shared test fixture**: `tests/load/qa/conftest.py` is created by task 2.1 and
extended by task 4.1 alone. Tasks 2.3, 2.4 and 2.5 run concurrently with 2.1 and
must therefore build their own constructed values inside their own test modules;
none of them may add to `conftest.py`. This is what makes their `(P)` markers
safe, and each of those tasks restates it.

**Shared source files**: `src/fitdocs/load/qa/cadence.py` is written by tasks 2.1
and 2.2 under two different responsibility boundaries — measurement, then
verdict. They are strictly sequential for that reason and 2.2 carries no `(P)`.
`src/fitdocs/load/qa/__init__.py` is created by task 1.1 with the leaf
vocabulary and extended by task 3.1 with the assembly entry point; no other task
touches it, and tasks 1.1 and 3.1 are in different waves.

## Data rule

The athlete's real `.fit` corpus never enters this repository. Task 4.1 encodes
the *measured statistics* recorded in `research.md` as constructed streams; it
does not add, reference or read a real file.

- [ ] 1. Foundation: the flag vocabulary, its provenance, and its configuration

- [x] 1.1 Create the flag vocabulary, its emission order and its tunable defaults
  - Add a leaf module holding the four check identifiers — cadence lock, channel
    divergence, aerobic drift, benchmark staleness — their display labels, and
    the fixed order in which they are always emitted
  - Define the immutable settings value carrying the seven tunable thresholds:
    the cadence-lock association strength, numerical closeness, span width,
    minimum lock duration and minimum paired coverage, the divergence tolerance,
    and the aerobic-drift reference point, each defaulting to a module-level
    constant
  - Record in each constant's own docstring what justifies its default, naming
    the measurement for a fitdocs-chosen value and the publisher for a published
    one; where a default rests on neither — which is true of the divergence
    tolerance alone — say so plainly in the docstring and point at the
    provisional record task 1.2 lands, rather than describing it as measured;
    the module carries no staleness window of its own
  - Define the conversion factor from the recorded per-limb cadence to full
    movement cycles per minute, with a docstring naming the ingest semantic it
    depends on and the revalidation trigger if that semantic ever changes
  - Create the package initializer as an ordinary **eager** re-export point
    carrying this module's names; task 3.1 adds the assembly entry point to it
    the same way. The invariant an earlier revision declared here — a package
    root re-exporting only leaf vocabulary — is withdrawn, and so is the lazy
    re-export a later revision proposed in its place: the initializer is under
    no restriction about what it may import, because the cycle is cut upstream
    by `training-load`'s `TYPE_CHECKING`-only import of the load settings value
    in the load contract module. Also create the test package marker for this
    feature's test directory so no later task races to create it
  - Observable: importing the module exposes four identifiers, a total label
    mapping, an emission order containing each identifier exactly once, and a
    settings value whose defaults match the documented constants; tests assert
    totality and uniqueness
  - _Requirements: 1.1, 1.7, 6.4, 6.9, 6.10, 6.11_
  - _Boundary: FlagVocabulary_

- [ ] 1.2 Record the provenance of every default and every divergence from established platform behavior
  - **Consume, do not extend, the shared provenance vocabulary.** The verification
    status for a value chosen by fitdocs and justified by a recorded measurement
    is defined by the channel layer's own foundation task; use it. Edit no module
    and no test module belonging to that spec — this task's entire footprint is
    this feature's own sources module and its own test module
  - Add this feature's citation records: the platform-published aerobic-drift
    reference point, the published decoupling formula, the peer-reviewed
    confirmation of the cadence artifact as a phenomenon, and the corpus
    measurement that justifies the fitdocs-chosen defaults
  - Record each divergence from established platform behavior with its stated
    reason: the decoupling half-split convention, the running and cycling
    decoupling numerators, the unimplemented moving-average decoupling variant,
    turning a displayed diagnostic into a verdict, and the two different
    coverage bases the load layer and the document's coverage table use — six
    entries in all, and the section header must say six
  - Add the provisional-defaults record: a typed entry, for each default that
    rests on neither a published figure nor a recorded measurement, naming the
    setting, the shipped value, the reasoning that produced it and the
    measurement that would replace that reasoning with evidence. The divergence
    tolerance is the only such default today; its entry records that the measured
    corpus computed no activity with two channels, that the value was originally
    chosen against a heart-rate intensity scale since corrected, and that the
    measurement which would settle it is the distribution of the intensity
    difference over activities where two channels both computed
  - State in the module that the widely repeated attribution of the reference
    point to a named coach was not verified and is not claimed; that the
    cross-channel scoring anecdote quoted in the brief could not be located in
    any published source, is cited nowhere in this feature and justifies no
    default; and that the brief's framing of the efficiency factor as a signal in
    its own right is withdrawn, because it carries no absolute reference point
    and its units differ by sport, so it enters only as a constituent of the
    decoupling percentage and as a stated basis
  - Assert uniqueness over the fields that exist — the citation's key and the
    divergence's behavior name — and not over a divergence key, which the shared
    record type deliberately does not have
  - Observable: a test asserts every default constant names either a citation
    present in the citation set or an entry in the provisional record and never
    both, that every fitdocs-chosen citation carries its measurement note, that
    every provisional entry carries both its reasoning and what would settle it,
    that the divergence set contains all six recorded entries, and that the two
    withdrawn brief claims are stated in the module
  - _Requirements: 3.10, 4.3, 4.5, 6.10, 6.11, 8.3_
  - _Boundary: FlagProvenance_
  - _Depends: 1.1_

- [ ] 1.3 Project and validate the flag settings on the single load-settings reader
  - Extend the one load settings value with a member holding this feature's
    thresholds, and extend the one reader — `load_load_settings` in the module
    `training-load` task 3.1 owns — with a projection of the flag sub-table;
    create no second reader and no second module
  - Validate each key against the range its quantity admits, rejecting booleans
    wherever a number is required, and raise the reader's existing configuration
    error naming the file, the key, the offending value and the admissible range
  - Treat an absent settings file, an absent load table, an absent flag
    sub-table and an absent individual key as the documented default rather than
    an error, and continue ignoring keys and sub-tables the reader does not
    recognize
  - Accept a minimum lock duration below the span width as a coherent
    configuration, documented at the key, rather than overriding the athlete
  - Observable: the settings tests show the seven keys projecting, every invalid
    type and out-of-range value raising with the file, key, value and range in
    the message, and a document carrying all four sibling features' load
    settings together parsing cleanly. Assert nothing about import order here:
    `training-load` owns the single fresh-interpreter guard, a subprocess check
    in the public-API test module, and an in-process re-import inside this test
    module would be a module-cache hit after its own top-level imports and would
    prove nothing
  - _Requirements: 6.1, 6.2, 6.3, 6.5, 6.6, 6.7, 6.8, 6.9_
  - _Boundary: FlagSettingsReader_
  - _Depends: 1.1_

- [ ] 2. Core: the four checks, each a pure function over its own inputs

- [ ] 2.1 (P) Measure the paired coverage and the per-span statistics of the two streams
  - Build the paired-presence view of the heart-rate and cadence streams and
    measure its coverage through the channel layer's existing time-weighted
    coverage function, so the load layer keeps exactly one coverage definition
    and the figure names the basis it was measured on
  - Divide the paired samples into successive non-overlapping spans of the
    configured width, anchored at the first paired sample, and compute for each
    span the correlation between heart rate and full-cycle cadence and the
    median absolute difference between them
  - Read the raw ingested arrays only, with no resampling, forward-fill,
    interpolation or gap substitution, and treat a span with fewer than two
    paired samples or zero variance in either series as having no correlation at
    all rather than a fabricated one
  - Add the constructed-stream builders this feature's tests need, in the shared
    fixture module this task owns
  - Observable: tests over constructed streams show the span division landing
    where the configured width says it should, the full-cycle conversion applied
    rather than the raw per-limb number, a degenerate constant-cadence span
    yielding no correlation, and the coverage figure matching the channel
    layer's own time-weighted result for the same stream
  - _Requirements: 2.1, 2.3, 2.4, 2.10, 8.1, 8.2_
  - _Boundary: CadenceLockDetector_
  - _Depends: 1.1_

- [ ] 2.2 Decide the cadence-lock verdict from the span statistics
  - Judge a span locked only when both the association and the closeness
    conditions hold together, and report the condition found when the summed
    locked duration reaches the configured minimum
  - Return the not-assessed reading, naming the specific unmet precondition, for
    a non-running modality, a wholly absent cadence stream, paired coverage below
    the configured minimum, and an activity from which no full span can be
    formed — in that fixed decision order, and reporting no observed figure that
    was not measured
  - Report the summed locked duration and the required minimum on a
    condition-not-found reading, so a near miss is distinguishable from a clear
    result
  - Record at the definition why the check is not defined for any modality other
    than running — the artifact is a wrist sensor locking onto arm-swing
    frequency, which equals stride frequency only when running — so the
    not-assessed reason for a walk, hike or ride is a stated position rather
    than an omission
  - Observable: tests show a high-association large-offset stream and a
    low-association close-offset stream both reporting the condition not found,
    both together sustained reporting it found, a stream whose heart rate equals
    the per-limb cadence rather than twice it reporting the condition not found,
    and each not-assessed precondition reaching its own distinct reason
  - _Requirements: 1.3, 1.4, 1.5, 1.8, 1.10, 2.2, 2.5, 2.6, 2.7, 2.8, 2.9_
  - _Boundary: CadenceLockDetector_
  - _Depends: 2.1_

- [ ] 2.3 (P) Compare the selected channel's intensity against the heart-rate channel's
  - Compare only the dimensionless threshold-relative intensities the two
    channels report — the single semantic under which the reported load equals
    the scored hours times the square of the reported intensity times one
    hundred, on every channel alike — folding the closed channel-outcome union
    exhaustively, and read neither channel's load value, coverage or anchor
    anywhere in the module
  - Report the condition found when the magnitude of the difference exceeds the
    configured tolerance and not found when it does not, carrying both
    intensities, the difference and the tolerance either way
  - Report not assessed when the heart-rate channel is itself the selected
    channel, stating that there is no second channel to compare against, and
    when the heart-rate channel produced no value, carrying that channel's own
    reported reason verbatim
  - Pin the corrected premise with a sub-threshold regression case: two channels
    reporting the **same load for the same scored duration at an effort well
    below threshold** must report the condition not found, with a difference of
    exactly zero. A case built at threshold cannot fail this, which is why the
    earlier mismatched-intensity-scale defect survived review; the test comment
    says so, so the case is not "simplified" back to threshold later
  - Build every constructed channel outcome this task needs inside its own test
    module; do not add to the shared fixture module, which task 2.1 owns
  - Observable: tests show the divergent, agreed, heart-rate-selected and
    heart-rate-insufficient paths each reaching their intended verdict, the
    insufficiency reason carried through unchanged, two outcomes with equal
    intensities but wildly different load values producing an identical reading,
    and the sub-threshold agreement case reporting the condition not found
  - _Requirements: 1.3, 1.4, 1.5, 1.10, 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.9_
  - _Boundary: DivergenceAnalysis_
  - _Depends: 1.1_

- [ ] 2.4 (P) Turn the shipped aerobic-decoupling figure into a verdict
  - Consume the decoupling percentage and the efficiency factor the derived
    metric layer already computes, restating and re-deriving neither, and
    compare the percentage against the configured reference point
  - Report the condition found when the percentage exceeds the reference and not
    found when it does not, carrying the observed percentage and the reference
    either way, and carrying the efficiency factor as part of the basis when it
    is available while omitting it entirely — never as a zero — when it is not
  - Report not assessed when the decoupling percentage is unavailable, stating
    that the shipped metric is defined for running and cycling only
  - Record at the definition why the efficiency factor is reported as a basis and
    never thresholded into a verdict of its own: it carries no absolute reference
    point and its units differ by sport, so a single activity's value admits no
    threshold
  - Build every constructed metrics value this task needs inside its own test
    module; do not add to the shared fixture module, which task 2.1 owns
  - Observable: tests show percentages above, below and exactly at the reference
    reaching their intended verdicts, an unavailable percentage reaching the
    not-assessed reason, and an absent efficiency factor producing a basis with
    no numeric stand-in
  - _Requirements: 1.4, 1.5, 1.8, 1.10, 4.1, 4.2, 4.4, 4.5, 4.6, 4.7_
  - _Boundary: AerobicDriftCheck_
  - _Depends: 1.1_

- [ ] 2.5 (P) Surface the age of the benchmark that anchored the selected channel
  - Obtain the age in days, the window and the stale-or-current verdict from the
    benchmark store's existing computation, contributing no arithmetic of this
    feature's own and introducing no second window or second default
  - Report on the anchoring benchmark of the selected channel only, evaluating
    against the activity's own calendar date rather than any clock, and carry the
    measurement date, the age in days and the window on the reading
  - Take the window and the activity's calendar date from the per-pass context
    the calculator receives, never from the profile view and never from a clock
  - Report not assessed when the activity carries no calendar date, and
    otherwise consult the store's computation unconditionally: do not guard the
    ordering of the measurement date against the activity date, because the
    store no longer fails on a benchmark measured after the activity — it
    reports a negative age, and only for an entry the athlete declared to apply
    retroactively
  - Surface a negative age as the reading's own retroactive outcome, distinct
    from stale, current and not assessed, carrying the anchor so the assembly
    can state the athlete's applies-from date beside the measurement date; a
    negative age whose anchor carries no applies-from date keeps the retroactive
    outcome and is reported as that absence, never guarded, never raised
  - Record at the definition that the absent-anchor half of the missing-anchor
    requirement is structurally unreachable — the channel outcome's anchor and
    the benchmark's measurement date are both non-optional upstream — so the
    reading's anchor is non-optional here and the undated activity is the one
    reachable instance
  - Build every constructed channel load and benchmark this task needs inside its
    own test module; do not add to the shared fixture module, which task 2.1 owns
  - Observable: tests show a stale anchor, a current anchor, an undated activity
    and a retroactive anchor (measured after the activity, declared to apply
    from on or before it) each reaching their intended reading, a negative age
    with no declaration keeping the retroactive outcome, no input reaching not
    assessed on the ordering of the two dates, and the same activity date
    producing the same verdict on repeat regardless of when the test runs
  - _Requirements: 1.5, 1.8, 1.10, 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8_
  - _Boundary: StalenessSurfacing_
  - _Depends: 1.1_

- [ ] 3. Integration: assembly, the calculator call site, and the published surface

- [ ] 3.1 Assemble the four readings into the contract's quality verdicts
  - Add the single entry point that runs all four checks unconditionally and
    emits one verdict per check in the fixed order, so a check's absence from the
    record never signals inapplicability
  - Map each check's own outcome onto the contract's three verdict values
    explicitly and totally, never by name coincidence, and never emit the
    condition-not-found verdict for a check that did not run; the staleness
    check's retroactive outcome maps to the condition-not-found verdict,
    because that check ran and the anchor is not stale
  - Own the basis strings: state the observed figure, the threshold and the span
    on every reached verdict, and the unmet precondition with no unmeasured
    figure on every not-assessed verdict; on a retroactive staleness verdict
    state the measurement date, how many days after the activity it falls, the
    applies-from date read from the anchor (or that it carries none) and the
    window
  - Keep this the only module in the package that imports the load contract, and
    add the entry point to the package initializer task 1.1 created so it is
    reachable from the package root. Re-export it **eagerly** — an ordinary
    `from .flags import evaluate_flags` — with no module-level attribute hook and
    no type-checking-only shim. The loop an earlier revision guarded against is
    cut upstream by `training-load`'s type-checking-only import of the load
    settings value in the load contract module, which puts the settings module
    back above the contract module; add no import guard of this feature's own
  - Observable: a test covering every combination of reachable per-check outcomes
    shows exactly four verdicts in the fixed order with non-empty bases, the
    outcome-to-verdict mapping proven total, and equal inputs producing a
    string-equal tuple
  - _Requirements: 1.1, 1.2, 1.3, 1.6, 1.7, 1.9, 1.10, 3.8, 5.8, 7.6, 7.7_
  - _Boundary: FlagAssembly_
  - _Depends: 2.2, 2.3, 2.4, 2.5_

- [ ] 3.2 Attach the verdicts to the computed result at the calculator's one call site
  - Add a keyword-only quality-verdict argument defaulting to the empty
    collection to the calculator's result-assembly function, assigning it
    straight through to the result's verdict field and to no other field
  - Evaluate the verdicts after a successful channel selection and pass them to
    the assembly, threading the activity, the derived metrics, the channel
    outcomes, the selected channel, and — from the per-pass context the
    calculator already receives — the activity's calendar date and the configured
    staleness window; read neither from the profile view, which no longer carries
    them, and read no settings file here
  - Leave the unsupported, missing-inputs and not-computed paths untouched, so no
    verdict is ever attached to a result that carries no number
  - Observable: the calculator's tests show a computed activity carrying four
    verdicts, each of the three non-computed outcomes carrying none, and a
    result assembled with verdicts differing from one assembled without in the
    verdict field and in no other field
  - _Requirements: 7.1, 7.2, 7.3, 7.5_
  - _Boundary: CalculatorIntegration_
  - _Depends: 3.1_

- [ ] 3.3 Publish the flag identifiers and settings on the plugin-author surface
  - Export the flag identifiers and the settings value from the load package's
    public names, alongside the sibling settings value types, because the
    settings value is reachable from the per-pass context a calculator receives
  - Leave the assembly entry point unexported, since it is the threshold
    calculator's internal collaborator rather than part of the plugin surface
  - Update the test that pins the public surface to the new shape
  - Observable: the surface pin passes with the two new names present and the
    assembly entry point absent, and the root package's exported names are
    unchanged
  - _Requirements: 6.4_
  - _Boundary: PublicSurfacePin_
  - _Depends: 3.2_

- [ ] 4. Validation: false-positive headroom, end-to-end behavior, and the boundary

- [ ] 4.1 Pin the false-positive headroom against the measured corpus statistics
  - Encode as constructed streams the statistics recorded in the research log —
    the highest whole-activity association observed on a real file, the smallest
    per-file median separation between heart rate and full-cycle cadence, and
    the single longest span the conjunctive rule judged locked anywhere in the
    corpus — extending the shared fixture module this feature already owns
  - Assert every one of those streams reports the condition not found at the
    shipped defaults, and record in the test module the measured margin each one
    leaves
  - Add the correlated-effort case explicitly: a stream whose heart rate and
    cadence both rise through a hard effort reports the condition not found
  - State in the module header that these are reconstructed statistics and that
    the corpus itself is never added to, referenced by, or read from this
    repository
  - Observable: the test module fails if any default is loosened past the
    measured headroom, which is what makes the defaults a pinned decision rather
    than a comment
  - _Requirements: 2.9, 2.11_
  - _Boundary: CadenceLockDetector_
  - _Depends: 2.2_

- [ ] 4.2 Verify the verdicts end to end through a load pass
  - Run a load pass over a fixture data root that reaches the computed path —
    reusing the one the threshold calculator's own end-to-end test builds, and
    constructing it here if that spec has not yet produced one
  - Assert the rendered training-load section carries the verdict block with its
    four entries and that the embedded machine-readable record round-trips them
  - Assert no verdict appears in document frontmatter and that this feature
    introduced no frontmatter key
  - Assert regenerating the same document reproduces it byte for byte
  - Observable: a generated fixture document shows the four verdicts in the
    section, none in the frontmatter, and an unchanged second render
  - _Requirements: 7.1, 7.3, 7.4, 7.6_
  - _Depends: 3.2_

- [ ] 4.3 Guard the purity of the layer and its permanent exclusions
  - Assert the package performs no input or output, accepts and returns no file
    path, consults no clock or random source, and invokes no language model
  - Assert no module in the package imports the load engine, the renderer, the
    document editor, the calculator registry or the document contract, and that
    only the assembly module imports the load contract
  - Assert the computed load value is bit-identical with and without verdicts for
    the same activity, which makes the never-a-load-combiner constraint
    mechanical rather than declarative
  - Assert the package registers no calculator, resolves no benchmark, selects no
    channel, and neither modifies nor replaces the workout document's existing
    coverage table
  - Observable: the guard module fails on any future import that would cross one
    of these boundaries, and on any change that would let a verdict reach a load
    value
  - _Requirements: 1.9, 8.4, 9.1, 9.2, 9.3, 9.4, 9.5, 9.6, 9.7, 9.8, 9.9_
  - _Depends: 3.2_

## Implementation Notes

- **1.1**: `tests/load/test_packaging.py`'s `_LOAD_MODULE_ALLOWLIST` wheel-contents
  guard required a two-line addition for `fitdocs/load/qa/__init__.py` and
  `fitdocs/load/qa/types.py` — any later task adding a new module file under
  `load/qa/` (2.1–2.5, 3.1) owes the same allowlist line or the packaging test
  reds.
- **1.1 → 1.2**: a provenance-docstring test helper matching `rf"{name}[^\"]*\"\"\"(.*?)\"\"\""`
  slides forward into the *next* constant's docstring when the named constant's
  own docstring is empty or absent — harmless today only because the expected
  substrings still differ downstream. Task 1.2's own provenance assertions in
  `qa/sources.py`/`test_sources.py` will likely need the same regex shape;
  anchor it so a missing docstring is its own failure, not a false match on a
  neighbor's.
- **1.1 → 1.2**: a provenance docstring's opening marker (`Measured:` /
  `fitdocs' own choice` / `PROVISIONAL --` / `<Publisher>-published:`) is now
  asserted as a closed, mutually exclusive set, but free prose *inside* the
  body is not policed beyond the `"Measured:"` token search — a fabricated
  measurement claim phrased without that literal marker (e.g. "the corpus
  showed 0.20 at the 95th percentile") can sit undetected in a PROVISIONAL
  docstring's body. Worth a sentence of awareness when 1.2 writes the
  authoritative `PROVISIONAL_DEFAULTS` record for the divergence tolerance.
- **1.1 → 1.3**: `src/fitdocs/load/settings.py:46` states `load/qa/types.py`
  "does not exist yet in this checkout" — now false. Task 1.3 touches this
  file directly (extends `load_load_settings`); fix the stale comment there
  rather than filing it separately.
- **1.1 → 3.3**: `tests/test_public_api.py:713-716`'s docstring states the
  quality-assurance sub-package "does not exist in this checkout" — now stale
  (the discovery logic itself already covers `fitdocs.load.qa` correctly).
  Task 3.3 owns and modifies this test module; fix the stale docstring there.
