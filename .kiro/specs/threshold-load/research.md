# Research & Design Decisions — threshold-load

## Summary

- **Feature**: `threshold-load`
- **Discovery Scope**: Complex Integration — a thin policy layer whose every
  input and output is another spec's contract, three of which are approved but
  none of which is implemented yet.
- **Key Findings**:
  1. **The shipped calculator contract gives a calculator no way to reach its own
     configuration.** `LoadCalculator.compute(activity, metrics, profile,
     session)` was left unchanged by training-load's Amendment 1, and the roadmap
     hand-off note anticipated a per-activity context that the approved design
     did not introduce. Channel priority *and* the sufficiency settings the
     channel layer requires must therefore reach the calculator the same way
     `athlete-benchmarks` routed `activity_date` and `staleness_window_days`:
     bound onto the profile view by the engine.
  2. **`Modality` and `Sport` are different vocabularies, and Walk/Hike collapse
     into `Modality.OTHER`.** The registry, the modality filter and the engine's
     declaration check are all `Modality`-based; the benchmark store, the
     document and this feature's support decision are all `Sport`-based. The
     support set must be authoritative at the sport level, with the modality
     declaration as a coarse pre-filter.
  3. **Three approved specs each create `src/fitdocs/load/settings.py`** with a
     different `LoadSettings` shape and two different reader names. This feature
     needs `[load]` keys too. It extends the single dataclass and adds no second
     reader — and the collision is a sequencing risk, not a design choice.
  4. **`Modality.OTHER` and the activity-blind field declaration together leak
     prompts** onto sports this calculator does not support and onto benchmarks
     the athlete will never own. Mitigable only in the contract, not here.
  5. The closed `LoadOutcome` union has **no variant meaning "computed nothing,
     here is why"** other than `NotConfirmed`, whose name is withdrawn-
     methodology-era confirmation vocabulary. The behavior is exactly right; the name is not.

## Research Log

### The calculator's access to configuration

- **Context**: this feature owns a configurable channel priority, and it must
  hand `load-channels` a resolved `SufficiencySettings`. Requirement 1.6 forbids
  the calculator from reading a settings file itself, and `load-channels`
  Req 3.9 forbids the channel layer from reading one either.
- **Sources consulted**: `src/fitdocs/load/types.py` (shipped `LoadCalculator`
  protocol), `.kiro/specs/training-load/design.md` (LoadContracts: "**Unchanged
  by this design**: … `LoadCalculator`"; LoadSettings; LoadEngine's
  `apply_load` signature), `.kiro/specs/athlete-benchmarks/design.md`
  (ProfileContract, "Rationale for `activity_date` on the view").
- **Findings**:
  - `compute()` receives no data root, no settings, and no per-activity context.
    Nothing in the four parameters can carry a configured value except
    `profile`.
  - `athlete-benchmarks` already set the precedent deliberately, and recorded
    the move-it-later trigger: "When the `training-load` Amendment 1 update
    introduces a proper per-activity context parameter, `activity_date` moves
    there and the view sheds it."
  - training-load's approved design did **not** introduce that parameter. The
    trigger did not fire, so the parking spot is the contract.
  - Registration-time configuration was rejected: the engine registers built-ins
    at import, before a data root exists, and a plugin author's entry point is
    called with no arguments — configuring at registration would be a privilege
    a plugin author lacks, which the brief names as a defect to surface rather
    than a design to adopt.
- **Implications**: `ProfileView` gains one member carrying the resolved load
  settings. `load/types.py` must then import `load/settings.py`, inverting one
  edge of training-load's stated internal chain. Recorded as the top cross-spec
  risk; the alternative long-term fix (a per-pass context parameter on
  `compute`) is named in the design so training-load can adopt it instead
  without changing anything else here.

### Sport, modality, and where Walk and Hike actually live

- **Context**: roadmap decision 4 puts Run, Ride, Walk and Hike in scope and
  everything else out. Both upstream Phase-4 specs explicitly disowned the
  mapping.
- **Sources consulted**: `src/fitdocs/model.py` (`Sport`, `Modality`,
  `Activity`), `src/fitdocs/ingest/sport.py` (`SPORT_MAP`, `MODALITY_MAP`),
  `src/fitdocs/load/registry.py` (`for_modality`, `validate_calculator`),
  `.kiro/specs/training-load/design.md` (the engine's declaration check).
- **Findings**:
  - `Activity` carries both `sport: Sport` and `modality: Modality`.
  - `MODALITY_MAP` maps only running/cycling/swimming; **walking, hiking, rowing,
    unknown and absent sports all become `Modality.OTHER`**, and a
    `strength_training` sub-sport forces `Modality.STRENGTH`.
  - `LoadCalculator.supported_modalities` is a `frozenset[Modality]`, and both
    `registry.for_modality` and the engine's declaration check use it.
  - The benchmark store scopes benchmarks by `Sport` (lowercased as the TOML
    table name), not by `Modality`.
- **Implications**: the calculator declares `{RUN, BIKE, OTHER}` so Walk and Hike
  reach it at all, and returns `Unsupported` from `compute` for the other sports
  inside `OTHER` (Rowing, Workout, and any unrecognized sport). `STRENGTH` is not
  declared, so strength activities never reach `compute` and take the engine's
  unsupported path directly — the cheapest possible honest refusal. The
  consequence is that Rowing/Workout documents pass the declaration check and
  therefore run the prompt flow before being refused; see the risks.

### Anchoring Walk and Hike

- **Context**: `athlete-benchmarks` never falls back across disciplines, and
  Walk/Hike have no LTHR of their own. Without a policy, roadmap decision 4's
  "Walk/Hike are in" is unrealizable — the athlete's 5 hikes and 3 walks would go
  unscored despite carrying good heart rate.
- **Findings**:
  - The store distinguishes "none on file" from "none applicable", so a
    calculator-side chain can prefer the activity's own discipline and fall back
    without ever asking the store to fall back.
  - Threshold power and threshold pace have no defensible walking equivalent:
    `load-channels` returns `MODEL_NOT_DEFINED` for pace on any non-running
    modality (Minetti's walking polynomial was not obtained), and anchoring
    walking watts to a running FTP would be exactly the
    computable-but-meaningless number roadmap decision 1 refused for strength.
- **Implications**: the anchor map is per (sport, quantity), not a blanket
  discipline alias. Walk and Hike resolve LTHR through `own → run`, resolve the
  athlete-wide heart-rate benchmarks normally, and have **no** power or pace
  anchor. Every borrowing is reported on the result.

### Default channel priority and intervals.icu interop

- **Context**: a hardcoded `Power > Pace > HR` order was refuted 1-2; priority is
  configurable, but the *defaults* still have to be chosen and justified.
- **Findings**:
  - Every one of the athlete's ~45 runs carries recorded power at 99–100%
    coverage, and the roadmap already records that intervals.icu does not ingest
    those fields natively. A power-first default for running would therefore make
    **every** run's headline load a number intervals.icu cannot reproduce.
  - 7 of 9 rides carry no power at all, so a power-first cycling default must
    fall back rather than fail — which is what the fallback walk is for.
  - One run has 100% power and 0% GPS, so a pace-first running default must fall
    back too. The two defaults exercise the fallback in opposite directions,
    which is the behavior the design most needs covered.
- **Implications**: defaults are Run `pace → power → heart_rate`, Ride
  `power → heart_rate`, Walk and Hike `heart_rate`. The interop reason for the
  running default is recorded as a divergence entry: fitdocs *can* score running
  power and will when configured to, but it does not do so by default, because
  the default should be the number another platform can check.

### The load settings table

- **Context**: instruction 6 of the task brief, confirmed by direct reading.
- **Findings**: `athlete-benchmarks` creates `load/settings.py` with
  `LoadSettings(benchmark_staleness_days)` and
  `load_settings_from_document(document, path)`; `training-load` task 3.1 creates
  the same module with `LoadSettings(default_calculator)` and
  `load_load_settings(document, settings_file)`; `load-channels` extends
  whichever exists with `sufficiency: SufficiencySettings`. Neither creating spec
  has been implemented. All three agree on the additivity contract: unknown keys
  and unknown sub-tables inside `[load]` are ignored.
- **Implications**: this feature adds `channel_priority` to the same dataclass
  and the same reader, and states the collision in the design as a sequencing
  risk rather than picking a winner.

### The outcome vocabulary for "computed nothing"

- **Findings**: `LoadOutcome = Computed | Unsupported | MissingInputs |
  NotConfirmed` is closed and folded with `assert_never`. `Unsupported` means the
  sport is out of scope and drives a *document state*, so it cannot carry "the HR
  strap dropped out". `MissingInputs` carries declared fields and renders as
  "missing required inputs", which is wrong for a coverage failure. `NotConfirmed`
  renders as a skip carrying the calculator's own reason string — behaviorally
  exactly right, semantically named for a confirmation step that left the tool
  with the withdrawn methodology.
- **Implications**: conform — use the existing variant, do not widen a closed
  union from a downstream spec — and record the naming mismatch as a
  recommendation for training-load.

## Architecture Pattern Evaluation

| Option | Description | Strengths | Risks / Limitations | Notes |
|--------|-------------|-----------|---------------------|-------|
| **Thin policy layer over pure leaves** (selected) | A leaf for the priority value, a leaf for the discipline tables, a pure selection function, and one calculator object that wires them | Every decision independently testable without an activity; matches the brief's boundary candidates exactly | Four small modules for one calculator | Mirrors `load-channels`' own split of gate / weighting / grade / channels |
| One `threshold.py` module | Everything in the calculator class | Fewest files | The priority value type must be importable by `load/settings.py`, which would create an import cycle through the calculator; and the modality-support decision loses its own test | Rejected on the cycle alone |
| Channel-selection strategy objects | A `SelectionStrategy` protocol with a priority implementation | Extensible | No second strategy exists or is wanted; fusion is permanently excluded, so an extension point for "another way to combine channels" is precisely the thing Req 11.7 forbids | Rejected |

## Design Decisions

### Decision: Configuration reaches the calculator through the profile view

- **Context**: Req 1.6 and `load-channels` Req 3.9 both forbid a settings read
  below the engine, and `compute()` has no parameter for configuration.
- **Alternatives considered**:
  1. Widen `compute()` with a per-pass context — the right long-term shape, but
     it is training-load's contract and its approved design declines to change
     it.
  2. Configure the calculator instance at registration — impossible for a plugin
     author, and the data root is unknown at import.
  3. Bind the resolved settings onto the profile view, as `activity_date` and
     `staleness_window_days` already are.
- **Selected approach**: 3, with `ProfileView` gaining a single
  `load_settings: LoadSettings` member bound by `apply_load`.
- **Rationale**: it reuses an already-approved mechanism rather than inventing a
  second one, keeps every settings read in the engine, and leaves alternative 1
  available later as a pure refactor.
- **Trade-offs**: `load/types.py` must import `load/settings.py`, inverting one
  edge of training-load's stated chain; `staleness_window_days` becomes redundant
  with `load_settings.benchmark_staleness_days` (left alone — it is
  `athlete-benchmarks`' member to retire).
- **Follow-up**: if training-load adopts a context parameter, `activity_date` and
  `load_settings` move together and this design changes in one file.

### Decision: Compute all three channels even when priority names one

- **Context**: Req 5.1. A cheaper design would evaluate only the configured
  channels and stop at the first success.
- **Selected approach**: evaluate all three, always, then select.
- **Rationale**: `activity-qa-flags` compares the selected channel against the
  **heart-rate** channel to detect divergence, so the HR outcome must exist even
  when power was selected. Evaluating lazily would make that spec's central
  comparison unavailable exactly when it matters. It also makes the diagnostics
  complete, which is what lets a user audit why their configured first choice did
  not win.
- **Trade-offs**: a small amount of arithmetic is discarded per activity; the
  channels are pure and cheap, and the modality and benchmark gates short-circuit
  before any stream is walked.

### Decision: The sport set is authoritative, the modality set is a pre-filter

- **Context**: Walk and Hike are `Modality.OTHER`, alongside Rowing and Workout.
- **Selected approach**: declare `{RUN, BIKE, OTHER}`; refuse unsupported sports
  from inside `compute`.
- **Rationale**: it is the only shape the shipped registry admits, and the
  refusal is the contract's own `Unsupported` outcome, which the engine already
  turns into the honest unsupported document state.
- **Trade-offs**: a rowing document runs the prompt flow before being refused.
  Recorded as a risk with the contract-level fix named.

### Decision: Walk and Hike borrow the running LTHR, and nothing else

- Covered under the research log above. The alternative — requiring a walk LTHR
  before a walk can be scored — was rejected because it makes roadmap decision 4
  false in practice for every athlete who has not tested one, and because the
  borrowing is reported rather than hidden.

### Decision: Selection ignores magnitude entirely

- **Context**: Req 6.5. A "prefer the highest-confidence channel" rule was
  considered and rejected.
- **Rationale**: any rule that reads the values is a step toward the fusion the
  research refuted, and it makes a number's origin unpredictable from
  configuration alone. Order plus computed-or-not is total, deterministic, and
  explainable in one sentence.

## Recorded Divergences from intervals.icu

Every entry states the behavior, what interop would imply, what fitdocs does, and
why (roadmap constraint: *"where intervals.icu has an established behavior, match
it; every divergence needs a stated reason recorded in the spec"*).

1. **Default running channel** — fitdocs defaults running to pace, not to the
   recorded running power it is uniquely able to use. Reason: the roadmap already
   records that intervals.icu does not ingest those fields natively, so a
   power-first default would make every run's headline number unreproducible
   there. Power remains one configuration line away, and its use is recorded on
   the result when configured.
2. **Non-selected channels are persisted** — intervals.icu records the selected
   load. fitdocs records the others as explicitly-not-the-load diagnostics.
   Reason: they are the input to the planned divergence flag and they make a
   selection auditable; they are never aggregated and never rendered as the load.
3. **Walk and Hike are anchored on a borrowed running LTHR** — the benchmark
   store itself never falls back. Reason: without it those activities are
   unscorable; the substitution is a calculator-level policy, is reported on
   every result that used it, and is overridden the moment the athlete records a
   walk or hike LTHR of their own.

## Risks & Mitigations

1. **`load/settings.py` is created by two upstream specs and extended by two
   more.** — Whichever lands first defines the module, its error type and its
   reader name; the three others extend it. This feature's task explicitly says
   "extend, do not create", and its test asserts that a document carrying every
   sibling's `[load]` sub-table parses cleanly.
2. **`ProfileView` grows a member owned by neither of its two current authors.**
   — Stated as a cross-spec coordination item that must land with this feature;
   `tests/test_public_api.py` is the pin that will catch it either way.
3. **Prompt leakage on unsupported sports and unowned benchmarks.** —
   `required_athlete_fields()` is activity-blind, so a runner with no bike is
   asked for a cycling FTP on every interactive pass, and a rowing document is
   prompted before being refused. Not fixable inside this feature. Mitigation:
   help text that names the discipline plainly so declining is obvious, and a
   recommendation that the contract either take the activity or persist a
   declined marker.
4. **`NotConfirmed` is the only available "computed nothing" variant.** —
   Conform now; recommend a rename in training-load. If it is renamed, this
   feature changes one identifier.
5. **Nothing upstream is implemented.** — All three dependencies are approved
   specs, not code. The task plan front-loads the two leaves that depend on
   nothing but `Sport` and the channel vocabulary, so an ordering slip upstream
   blocks late tasks rather than all of them.
6. **The default running priority is a judgement call about another platform's
   behavior.** — It is recorded as a divergence with its reason rather than as a
   fact about intervals.icu, and it is one settings line to change.

## References

- `.kiro/steering/roadmap.md` — Phase 4 scope, the seven discovery decisions,
  the rejected fusion design and the refuted `Power > Pace > HR` ordering.
- `.kiro/specs/athlete-benchmarks/design.md` — `BenchmarkSet.applicable`,
  `has_benchmark`, `ProfileView`, `load/settings.py`, and the recorded
  `activity_date` relocation trigger.
- `.kiro/specs/load-channels/design.md` — `ChannelOutcome`, the seven
  `InsufficiencyReason` values, `SufficiencySettings`, the fixed gate order, and
  the three `compute` signatures.
- `.kiro/specs/training-load/design.md` — the redefined `LoadResult`,
  `NonSelectedValue`, `QualityFlag`, arbitration, and payload v2.
- `src/fitdocs/model.py`, `src/fitdocs/ingest/sport.py`,
  `src/fitdocs/load/types.py`, `src/fitdocs/load/registry.py`,
  `src/fitdocs/load/engine.py` — the shipped surfaces this feature plugs into.
