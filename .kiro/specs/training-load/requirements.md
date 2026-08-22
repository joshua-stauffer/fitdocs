# Requirements Document

## Project Description (Input)
Differentiating layer of fitdocs (an installable `.fit` → markdown personal
knowledge manager for fitness). Training load is the primary value fitdocs
adds over raw exporters: a single comparable number per workout that athletes
plan weeks around. Methodologies vary and are opinionated, so load must be
pluggable — a `LoadCalculator` interface with a registry, shipped
implementations, and a clean seam for community contributions. This spec
delivers the interface and registry, the athlete profile store (a versioned
file in the data root), a generic interactive prompt flow that collects
missing required athlete inputs at sync time and persists them so users are
asked once, the withdrawn methodology's implementation (zone determination from
average HR as % of tested max and/or average pace vs the HPL pace table,
surfaced for user confirmation; interval workouts mapped from laps with the
workbook's discount/adjustment math; reproduces workbook numbers exactly),
bundled withdrawn-methodology lookup tables (pending licensing sign-off), and rendering of load
results into the workout document's reserved load section and frontmatter.
Load is calculated for running only in this first pass; calculators cleanly
decline unsupported sports. See `.kiro/specs/training-load/brief.md` and
the reference writeup, recorded in the purge's provenance record.

> **Superseded in part.** Amendment 2 below withdraws the withdrawn methodology
> from this spec's scope. The description above is preserved as the original
> input; where it describes the withdrawn methodology, Requirements 4, 5, 6 and 12 are withdrawn and
> no withdrawn-methodology work remains in this feature.

## Amendment 1 (2026-07-25): the multi-channel result contract

The original contract was shaped around the one methodology that existed. Its
result type carries a single point value plus `zone`, `zone_label` and
`structure` — withdrawn-methodology vocabulary. The Phase 4 threshold engine
(roadmap: `athlete-benchmarks` → `load-channels` → `threshold-load` →
`activity-qa-flags`) computes a load per available channel and selects one, so
it has several values where the contract has one, a selection basis where the
contract has a zone, and quality flags the contract cannot carry at all.

This amendment therefore **redefines** the result contract rather than
extending it, and settles which calculator runs when more than one applies.
fitdocs is pre-production with no external plugin authors, so the plugin-author
surface carries no backward-compatibility obligation; `tests/test_public_api.py`
is repinned to the new shape rather than treated as frozen. Requirements 1 and
7 are revised in place and Requirements 10, 11 and 12 are added. **No existing
requirement or criterion is renumbered** — code comments and the design and
task documents cite these numbers.

## Amendment 2 (2026-07-25): withdrawing the withdrawn methodology

Amendment 1 was written to redefine the result contract *while keeping the
withdrawn methodology working* — Requirement 12 existed solely to guarantee that
continuity. That constraint is now removed: **the withdrawn methodology is
withdrawn from fitdocs entirely.** Three findings drove the decision.

- **It does not produce numbers in practice.** The withdrawn methodology requires per-activity
  interactive confirmation of the zone and of the interval-vs-continuous
  structure. Any non-interactive pass yields `NotConfirmed` by design, so a
  full rebuild over 71 real activities leaves every document's load "not
  computed". Realizing the shipped capability means confirming each activity by
  hand at a terminal.
- **It blocks public distribution.** The withdrawn-methodology lookup tables and its name
  require the third party's explicit permission before public redistribution. That
  permission was never obtained, and it gates any release of this repository.
- **It is the constraint shaping the wrong contract.** `zone`, `zone_label` and
  `structure` are withdrawn-methodology vocabulary. With the withdrawn methodology withdrawn, the result contract is
  *defined* for the multi-channel threshold engine rather than *migrated* from a
  single-channel one, and Requirement 12's continuity guarantee has nothing to
  guarantee.

**Consequences.** Requirements 4, 5, 6 and 12 are withdrawn. Requirements 1, 2,
3, 9 and 10 are revised where they named the withdrawn methodology. Requirements 7, 8 and 11 are
unaffected by this amendment (7 remains as Amendment 1 revised it).
**Withdrawn requirements keep their numbers and are marked withdrawn in place;
nothing is renumbered**, so every code comment, design and task citation of a
surviving requirement stays valid.

**This spec now ships no calculator.** It delivers the contract, the registry,
the profile store, the prompt flow, the document integration and the load pass —
the carrier. The first and only calculator is the threshold engine, delivered by
`threshold-load`. Until it lands, no registered calculator supports any sport
and every workout document correctly receives the honest unsupported state of
Requirement 7.7. That interim is a specified, honest outcome, not a regression.

**Arbitration survives this amendment.** Requirement 10 was motivated partly by
two built-in calculators both claiming running, but its load-bearing motivation
is independent of the withdrawn methodology: the plugin surface lets a third-party calculator
register for a sport a built-in already covers, and today's engine would let it
silently displace the built-in by registration order. Requirement 10 is revised,
not withdrawn.

## Amendment 3 (2026-07-25): the calculator's per-pass context, and the pinned `[load]` reader

A cross-spec consistency review over the Phase 4 chain (`athlete-benchmarks` →
`load-channels` → `threshold-load` → `activity-qa-flags`) found four places where
this spec's carrier is under-specified enough that four sibling specs each
invented a different answer. All four rulings are applied here, in this spec,
because this spec owns the carrier every one of them extends. **No existing
requirement or criterion is renumbered.** Requirements 1, 3 and 10 are revised in
place, criteria 1.12–1.15 are added, and Requirement 14 is added.

- **The `[load]` settings module has one owner and one pinned surface.**
  `src/fitdocs/load/settings.py` does not exist yet and five specs claim it: this
  spec creates it as `load_load_settings(document, settings_file)`,
  `athlete-benchmarks` independently creates it as
  `load_settings_from_document(document, path)`, and three more say "extend
  whichever exists". The second lander would rename a public symbol. **This spec
  is the owner.** `load_load_settings` matches the dominant shipped convention
  (`plugins.load_plugin_settings(document, settings_file)`,
  `inbox.load_inbox_settings(document, *, data_root)`), whereas
  `load_settings_from_document` follows the older `tiles` variant and collides
  confusingly with `fitdocs.settings.load_settings_document`, which reads the
  *file*. The surface is now pinned by criteria (Requirement 14) rather than left
  in design prose, every field is defaulted, and siblings extend the one
  `LoadSettings` dataclass instead of adding a second reader.
- **`apply_load` reads `[load]` once and owns the resolved settings.** Two
  incompatible wirings were specified: this spec had `cli.py` read the table and
  thread a lone `default_calculator` scalar into `apply_load`, while
  `athlete-benchmarks` had `apply_load` read it and `threshold-load` required the
  whole resolved `LoadSettings` to be bound for the pass. Landing both reads the
  document twice per invocation and leaves `apply_load` carrying a scalar that is
  already a member of the settings object it also holds. The `default_calculator`
  parameter on `apply_load` is **dropped**; `--calculator` remains the sole
  command-line override.
- **A calculator gets a per-pass context.** Amendment 1 left `compute()`'s
  parameter list unchanged, so a calculator has no route to its own configuration
  (channel priority, sufficiency thresholds, staleness window) or to the
  activity's date. Three downstream specs each worked around this by parking
  per-pass state on `ProfileView` — a protocol documented as a "minimal read-only
  view of the athlete profile" — which also inverts the `types → settings` import
  direction and forces `load/qa/__init__.py` to be crippled so its own
  `evaluate_flags` is unreachable from the package root. A `LoadContext`
  parameter replaces all three workarounds, and `ProfileView` reverts to a pure
  store view.
- **Two contract corrections.** The `NotConfirmed` outcome is renamed
  `NotComputed`: it is documented for a confirmation step that Amendment 2
  withdrew with Requirement 4, has no producer in shipped source, and
  `threshold-load` is about to become its sole producer for the unrelated meaning
  "no channel could be scored" — exactly the misleading contract Amendment 1 set
  out to eliminate. And `LoadCalculator` gains a `supports(activity)` question the
  engine can ask *before* the prompt flow, because a calculator that must declare
  a broad modality to reach a few sports within it (`threshold-load` declares
  `Modality.OTHER` to reach Walk and Hike) otherwise drags Rowing and Workout
  documents through the whole interactive prompt flow before refusing them by
  sport.

**Legitimacy of the contract change.** Adding a parameter to `compute()`, renaming
an outcome variant and adding a Protocol member all break any implementation of
the published plugin-author surface. This is explicitly permitted by the
roadmap's ratified position (2026-07-25): fitdocs is pre-production with no
external plugin authors, the plugin-author surface carries no
backward-compatibility obligation before 1.0, and `tests/test_public_api.py` is a
guard against *accidental* drift, to be repinned rather than frozen — the same
basis Amendment 1 used to redefine `LoadResult`. `docs/contributing-calculators.md`,
the stub calculators, `engine.py` and `load/__init__.py` move with it.

**Known open item, deliberately deferred.** `required_athlete_fields()` remains
activity-blind: a calculator declares one field set for all activities, so a
runner with no bicycle is asked for a cycling FTP on every interactive pass, and
`athlete-benchmarks` Req 8.5 (a decline persists nothing) means the question
repeats on every pass forever. Making the declaration activity-aware is **not** in
this amendment's scope; `supports(activity)` narrows the blast radius to sports a
calculator actually covers but does not close it. Recorded here so the next spec
to hit it inherits the finding rather than rediscovering it.

## Introduction

training-load is the differentiating layer of fitdocs: it turns each workout
into a single comparable training-load number through a pluggable calculator
contract, and writes the result into the workout document that workout-docs
reserved for it. It owns the *carrier* — the contract every methodology
implements, the registry that addresses them, the arbitration that decides which
one runs, the athlete profile that holds the inputs they declare, the prompt
flow that collects those inputs once, and the document surgery that records the
result. It owns no methodology of its own.

Load often needs athlete data a `.fit` file does not carry — thresholds,
benchmarks, tested maxima — so this layer owns an athlete profile file and a
generic prompt flow that asks for missing required inputs once and persists the
answers. Three principles govern every requirement: absent data yields "not
computed", never a fabricated value; estimates derived from recorded data are
confirmed by the user, never silently guessed; and the value that counts is
always distinguishable from the values that do not, so a diagnostic can never be
mistaken for the activity's load.

## Boundary Context

- **In scope (Amendment 1)**: the shape of the load result — one value that
  counts, the basis it came from, any values computed but not selected with the
  reason each was not, and any quality flags raised; which calculator runs when
  several apply, and the behavior when the configured one is absent or
  unregistered; how all of that appears in the document section, its
  machine-readable record, and frontmatter; and recognizing results written
  under a superseded result format.
- **Out of scope (Amendment 1)**: the per-channel load math and its
  data-sufficiency rules (`load-channels`); the threshold calculator's
  channel-priority and fallback policy (`threshold-load`); the athlete
  benchmark store and staleness computation (`athlete-benchmarks`); detecting
  the quality conditions that raise flags (`activity-qa-flags`) — this feature
  defines the carrier and the presentation, never the detection.
- **In scope (Amendment 2)**: removing the withdrawn calculator, its bundled
  lookup tables and their packaging, its tests, and its methodology-specific
  profile fields from the shipped tool; and keeping every surviving
  requirement — contract, registry, arbitration, profile, prompt flow, document
  integration, load pass — working with no built-in calculator registered.
- **Out of scope (Amendment 2)**: retiring the plugin extension point, which is
  retained (`plugin-api` continues to own the published surface); the threshold
  engine itself (`threshold-load`); any replacement methodology.
- **In scope (Amendment 3)**: the `[load]` configuration surface — the single
  reader module, its pinned function and error names, the totally-defaulted
  settings type, and the tolerance that lets siblings add sub-tables; where that
  table is read and who owns the resolved value for a pass; the per-activity
  context handed to `compute`, and the purity of the athlete-profile view it
  restores; the pre-prompt support question on the calculator contract; and the
  naming of the "nothing was computed" outcome.
- **Out of scope (Amendment 3)**: every key any sibling adds to `[load]` and its
  sub-tables (`[load.sufficiency]` — `load-channels`; `[load.priority]` —
  `threshold-load`; `[load.flags]` — `activity-qa-flags`; the benchmark staleness
  window — `athlete-benchmarks`), which land as additive fields on the one
  settings type without touching the reader; the document-date accessor in
  `fitdocs.contract`, which `athlete-benchmarks` specifies and this feature only
  calls; making `required_athlete_fields()` activity-aware (see the amendment's
  open item).
- **In scope**: the pluggable load-calculator contract and registry; the
  athlete profile file's full lifecycle (creation, reads, updates, the final
  key contract — workout-docs consumes it read-only); the generic interactive
  prompt flow for missing required athlete inputs; writing load results into the
  reserved training-load section of workout documents and exposing load in
  document frontmatter; a load pass that runs with sync and as a standalone
  command; contributor documentation for new calculators.
- **Out of scope**: the workout document template, section structure, and
  region preservation mechanics (workout-docs — this feature only replaces
  the reserved load section's content and adds load metadata); `.fit` parsing
  and derived-metric formulas (fit-ingest); weekly/cycle load aggregation and
  overload guardrails (deferred with the plan level); auto-updating athlete
  fitness from race results; any load methodology whatsoever — the calculator
  contract must let methodologies slot in, but this feature specifies none;
  load derived from recorded perceived-exertion estimates (the session RPE
  developer field is noted as a possible future input only).
- **Adjacent expectations**: fit-ingest provides the activity model and
  derived metrics (including average HR, average pace, moving time, laps)
  under its versioned schema — this feature computes no metrics itself.
  workout-docs provides the reserved, marker-delimited load section in every
  document, preserves its content verbatim across regeneration, and renders a
  graceful "not computed" placeholder until this feature fills it; it also
  reads the athlete profile file read-only for zone/threshold rendering, so
  the profile keys it consumes must remain valid. TRIMP and power TSS remain
  generic derived metrics rendered by workout-docs — they are not load
  results and no calculator wraps them in this pass.
- **Adjacent expectations (Amendment 1)**: wiki-contract owns the document
  frontmatter schema, including which load keys are tool-managed and the
  document-format version; changing which keys the load pass writes requires a
  matching change there, or a document that has had a load pass reports
  unmanaged keys. plugin-api owns the published plugin-author surface and its
  compatibility statement; that statement must declare the surface unstable
  before 1.0, which is what makes redefining it legitimate rather than a
  violation. `threshold-load` supplies the calculator that motivates the
  redefined shape, and `activity-qa-flags` supplies the flags it carries —
  neither is specified here, and this feature must not assume either has
  landed in order to keep working.

## Requirements

### Requirement 1: Pluggable Load Calculator Contract and Registry
**Objective:** As a fitdocs user and community contributor, I want every load
methodology implemented behind one pluggable calculator contract with a
registry, so that workouts get load from an applicable methodology, new
methodologies can be added without touching core code, and no calculator is
ever forced to produce numbers for a sport it does not cover.

#### Acceptance Criteria
1. The training-load layer shall define a calculator contract under which each methodology declares a unique identifier, a human-readable display name, the sports it supports, and the athlete inputs it requires.
2. _(revised by Amendment 1)_ When a calculator computes load successfully, the training-load layer shall return a typed result carrying the one load value that counts, the identity of the methodology, the basis that value was derived from, the inputs used, and any explanatory notes.
3. When a calculator is applied to an activity whose sport it does not support, the calculator shall decline with a typed unsupported outcome and shall never return a load value for that activity.
4. If a calculator's required inputs are unavailable and cannot be collected, the training-load layer shall return a typed missing-inputs outcome identifying the missing fields, and shall not compute with substituted values.
5. _(revised by Amendments 1 and 2)_ The training-load layer shall maintain a registry of calculators addressable by identifier. This feature registers no calculator of its own; the registry shall behave correctly when it is empty, when it holds only built-ins, and when it holds discovered third-party calculators.
6. When selecting a calculator for an activity, the training-load layer shall consider only calculators that declare support for the activity's sport; when none support it, no load shall be computed for that activity.
7. The training-load layer shall provide contributor documentation describing how to implement and register a new calculator against the contract.
8. _(added by Amendment 1)_ Where a methodology computed values it did not select, the result shall carry each such value together with the reason it was not selected.
9. _(added by Amendment 1)_ Where a methodology raised quality flags about the data behind its result, the result shall carry those flags without altering the load value.
10. _(added by Amendment 1)_ The training-load layer shall keep the value that counts distinguishable from every value that does not, so that no consumer can read a non-selected value or a flag as the activity's load.
11. _(added by Amendment 1)_ Where a methodology produces a single value with no alternatives and no flags, the result shall represent it without fabricating alternatives, flags, or placeholder entries for them.
12. _(added by Amendment 3)_ When the training-load layer invokes a calculator for an activity, it shall pass a per-activity context carrying the activity's own recorded local calendar date (absent when the document records none) and the resolved load configuration for that pass, so that a calculator reaches its configuration and the activity's date through the contract and never by reading a settings file or a clock itself.
13. _(added by Amendment 3)_ The athlete-profile view a calculator receives shall expose stored athlete data only; no per-pass state — the activity's date, a configured window, or the resolved load configuration — shall be carried on it.
14. _(added by Amendment 3)_ The calculator contract shall let a methodology answer, for a specific activity and without any prompting or athlete data, whether it covers that activity; the training-load layer shall ask that question before collecting any athlete input, and a methodology that declares nothing more specific shall answer it by its declared modalities.
15. _(added by Amendment 3)_ The outcome variant that records "nothing was computed, and here is why" shall be named and documented for that meaning alone, and shall not be defined in terms of a confirmation step no surviving requirement mandates.

### Requirement 2: Athlete Profile Store
**Objective:** As an athlete, I want my athlete data (thresholds, benchmarks,
tested maxima) stored in one profile file in my data root, so that fitdocs asks
once and every later computation and document render reuses the same answers.

#### Acceptance Criteria
1. The training-load layer shall own the athlete profile file's lifecycle in the data root: creating it when the first answer is persisted, reading it, and updating it.
2. The athlete profile file shall carry a profile version identifier so future format changes are detectable.
3. If the athlete profile file does not exist, the training-load layer shall treat the profile as empty and shall not treat this as an error.
4. If the athlete profile file exists but cannot be parsed or contains values that fail validation, the fitdocs CLI shall fail with an instructive configuration error rather than proceeding with partial or guessed values.
5. When updating the profile, the training-load layer shall preserve entries it does not manage — including the zone and threshold keys consumed by document rendering — so that no user- or feature-owned data is lost on rewrite.
6. When persisting a value, the training-load layer shall validate it against the declaring methodology's stated range and shall never persist a value the user did not provide.
7. _(revised by Amendment 2)_ The athlete profile file shall store methodology-specific fields scoped to their declaring methodology so that fields from different calculators never collide. No methodology-scoped fields ship with this feature; the scoping mechanism shall be exercised by contract, not by a bundled calculator.

### Requirement 3: Interactive Completion of Missing Inputs
**Objective:** As an athlete syncing workouts, I want fitdocs to ask me for
missing required athlete data during the load pass — with validation, and
only once — so that load computation completes without me hand-editing
configuration files.

#### Acceptance Criteria
1. _(revised by Amendment 3)_ When the arbitrated calculator answers that it covers the activity (Requirement 1.14) and one of its required athlete inputs is absent from the profile, the fitdocs CLI shall prompt for that input during an interactive load pass; when it answers that it does not, no prompt shall be issued for that activity.
2. When prompting for an input, the fitdocs CLI shall present the field's meaning and valid range, and shall re-ask on out-of-range or unparseable answers rather than accepting them.
3. When the user provides a valid answer, the fitdocs CLI shall persist it to the athlete profile immediately so that subsequent activities and subsequent runs do not ask again.
4. If the user declines to provide a required input, the fitdocs CLI shall skip load computation for the affected activities, report the reason, and shall not substitute any value.
5. While running non-interactively (prompting disabled by the user or no interactive terminal), the fitdocs CLI shall not prompt, shall leave affected documents uncomputed with the reason reported, and shall complete the pass cleanly.
6. _(revised by Amendment 2)_ The prompt flow shall support a per-field confirmation hint through which a declaring methodology can echo derived context for the value being entered, so that a user can sanity-check an answer before it is persisted. No such hint ships with this feature.

### Requirement 4: Withdrawn-Methodology Zone Determination with Confirmation
**WITHDRAWN by Amendment 2.** The withdrawn methodology is no longer part of
fitdocs. This number is retired and shall not be reused; surviving requirements
are not renumbered.

### Requirement 5: Withdrawn-Methodology Continuous Load Computation
**WITHDRAWN by Amendment 2.** See Requirement 4. Note that criterion 5.4's
obligation — that bundled methodology data ship with the installed tool and
carry its licensing note — retires with the tables themselves; this feature
bundles no methodology data.

### Requirement 6: Withdrawn-Methodology Interval Load Computation
**WITHDRAWN by Amendment 2.** See Requirement 4.

### Requirement 7: Load Results in Workout Documents
**Objective:** As a PKM user, I want computed load written into each workout
document's reserved training-load section and exposed as queryable document
metadata, so that load lives with the workout and my wiki can query it
without parsing prose.

#### Acceptance Criteria
1. _(revised by Amendment 1)_ When load is computed for an activity, the fitdocs CLI shall replace the content of that document's reserved training-load section with the result — the load value that counts, the methodology name, the basis it came from, any non-selected values with the reason each was not selected, any quality flags, inputs used, and notes — without altering any other section or user-editable region.
2. _(revised by Amendment 1)_ When load is computed, the fitdocs CLI shall expose the load value, the methodology, and the basis in the document's frontmatter so external tools can query load directly, and shall not expose non-selected values or quality flags there.
3. _(revised by Amendment 1)_ The filled training-load section shall embed the complete result in a machine-readable form — including the non-selected values and quality flags that frontmatter omits — so the tool can recognize and recover its own previously computed results without consulting any other file.
4. When a document has been regenerated (which resets frontmatter to generated values), the fitdocs CLI shall restore the load frontmatter entries from the preserved training-load section content without recomputation and without prompting.
5. The fitdocs CLI shall not recompute or overwrite an already computed load result unless the user explicitly requests recomputation.
6. If the training-load section contains content the tool does not recognize as its own result or as the reserved placeholder, the fitdocs CLI shall leave that document's load section untouched unless recomputation is explicitly requested.
7. When no registered calculator supports an activity's sport, the fitdocs CLI shall record an honest unsupported state — naming the sport and containing no numbers — in the training-load section, and a later load pass shall compute load for that document once a supporting calculator is available.

### Requirement 8: Sync Integration and Standalone Load Command
**Objective:** As an athlete, I want load computed as part of my normal sync
and on demand for existing documents, so that no extra workflow step is
needed day-to-day and older documents can be filled retroactively.

#### Acceptance Criteria
1. When a sync run finishes writing documents, the fitdocs CLI shall run a load pass over the workout documents in the data root.
2. The fitdocs CLI shall provide a standalone load command that runs the load pass without re-syncing, filling documents that lack results.
3. Where recomputation is requested, the load pass shall recompute results for the targeted documents, including fresh confirmation of any values the calculator requires the user to confirm.
4. Where a specific methodology is requested by identifier, the load pass shall use only that calculator.
5. If processing one document fails during a load pass, the fitdocs CLI shall record the failure with its reason and continue with the remaining documents.
6. When a load pass completes, the fitdocs CLI shall report a summary of documents computed, restored, skipped (with reasons), and failed.
7. The load pass shall operate fully offline, using only the data root's documents, archived sources, the athlete profile, and its own resolved `[load]` configuration.

### Requirement 9: Missing-Data Honesty in Load Computation
**Objective:** As a fitdocs user, I want every load number traceable to real
recorded data and my own confirmed answers, so that no document ever carries
an invented training load.

#### Acceptance Criteria
1. The training-load layer shall never present, persist, or render a load value derived from fabricated, defaulted, or assumed inputs; whenever required data is absent, the outcome shall be an explicit "not computed" state with a stated reason.
2. _(revised by Amendment 2)_ Where a calculator derives a value from a recorded sample stream, the training-load contract shall require that derivation to be based on aggregates over the samples actually recorded, and shall never treat missing samples as zeros. Enforcing this for a given methodology's math is that methodology's own requirement.
3. If a document's archived source cannot be found or parsed during a load pass, the fitdocs CLI shall report that document as failed and shall not alter it.

### Requirement 10: Calculator Arbitration and Default Selection
**Objective:** As an athlete with more than one applicable methodology
installed, I want which calculator runs to be an explicit setting rather than
an accident of load order, so that my documents' numbers stay stable and I can
tell why a given methodology produced them.

_Added by Amendment 1; revised by Amendment 2._

#### Acceptance Criteria
1. When more than one registered calculator supports an activity's sport, the fitdocs CLI shall use the calculator named by the user's configured default, and shall not choose based on the order in which calculators were registered or discovered.
2. _(revised by Amendment 2)_ If no default calculator is configured and exactly one registered calculator supports the activity's sport, the fitdocs CLI shall use that calculator. If no default is configured and several support it, the fitdocs CLI shall compute no load for that activity and shall report it as skipped with a reason naming the candidates and directing the user to configure a default — never choosing by registration order.
3. When a specific methodology is requested by identifier (Requirement 8.4), the fitdocs CLI shall give that request precedence over the configured default.
4. If the configured default names an identifier that is not registered, the fitdocs CLI shall fail with an instructive error naming the configured value and the registered identifiers, and shall not fall back to another calculator.
5. When the arbitrated calculator declines an activity's sport, the fitdocs CLI shall record the honest unsupported state for that document, shall not silently substitute a different calculator that would have supported it, and shall compute load for that document on a later pass only once the arbitrated calculator supports it (qualifying Requirement 7.7).
6. When a load pass writes a result, the fitdocs CLI shall record which calculator produced it in the document, so that a number's origin is recoverable without re-running the pass.

### Requirement 11: Result-Format Versioning and Recognition
**Objective:** As a PKM user whose documents outlive tool versions, I want
fitdocs to recognize results it wrote under an earlier result format and refuse
to misread them, so that upgrading the tool never silently corrupts or
misreports load already recorded in my documents.

_Added by Amendment 1._

#### Acceptance Criteria
1. The machine-readable result embedded in the training-load section shall carry a result-format version identifier.
2. If a document's embedded result carries a result-format version the tool does not recognize, the fitdocs CLI shall leave that document's training-load section unchanged, report it as skipped with the reason, and shall not parse it partially or infer missing fields.
3. While a document carries a result written under a superseded result format, the fitdocs CLI shall treat that document as not eligible for automatic recomputation, so that an upgrade alone never rewrites results the user did not ask to change.
4. When recomputation is explicitly requested for a document carrying a superseded result format, the fitdocs CLI shall recompute from the archived source and replace the section with a result in the current format.
5. When the result format changes, the fitdocs CLI shall change the document-format version it records in frontmatter, so that documents needing regeneration are detectable without opening the training-load section.

### Requirement 12: Continuity of the Withdrawn Methodology
**WITHDRAWN by Amendment 2.** This requirement existed only to guarantee that
the Amendment 1 contract redefinition left the withdrawn methodology's results unchanged in meaning and
presentation. With the withdrawn methodology withdrawn there is nothing to keep continuous, and the
result contract is defined for the multi-channel case rather than migrated from
the single-channel one. Criterion 12.3's intent — that a methodology reporting
no channel values renders none, rather than empty or placeholder entries —
survives as Requirement 1.11 and is enforced in rendering by Requirement 7.1.

### Requirement 13: Withdrawal of the Withdrawn Methodology
**Objective:** As the maintainer, I want the withdrawn methodology removed from
the shipped tool completely and honestly, so that no partial implementation,
unreachable code path, or unlicensed data file remains, and so that documents
already carrying its results are handled deliberately rather than by accident.

_Added by Amendment 2._

#### Acceptance Criteria
1. The installed fitdocs package shall contain no withdrawn calculator implementation, no withdrawn-methodology lookup tables, and no withdrawn-methodology-derived constants, and the built distribution shall ship no withdrawn-methodology data files.
2. The training-load layer shall register no built-in calculator, and importing the load layer shall leave the registry empty of built-ins.
3. Where documentation, contributor guidance, or steering describes fitdocs' shipped methodologies, it shall not present the withdrawn methodology as available.
4. Where a workout document already carries a computed result naming the withdrawn methodology, the fitdocs CLI shall leave that document's training-load section unchanged and report it as skipped with a reason naming the unavailable methodology, and shall not silently erase, recompute, or misattribute the recorded result.
5. When recomputation is explicitly requested for a document carrying a result from the withdrawn methodology, the fitdocs CLI shall apply the ordinary arbitration and unsupported-state rules to it, so that it receives either a result from an available calculator or the honest unsupported state.
6. The removal shall leave every surviving requirement satisfied with no calculator registered, including a load pass that completes cleanly and reports honestly over a data root of workout documents.

### Requirement 14: The `[load]` Configuration Surface
**Objective:** As a fitdocs maintainer integrating four downstream features that
all configure load, I want one settings module with a pinned surface, total
defaulting and additive tolerance, so that each feature adds its own
configuration without renaming a public symbol, without a second reader, and
without a caller having to know which fields exist.

_Added by Amendment 3._

#### Acceptance Criteria

1. The training-load layer shall provide exactly one reader for the `[load]` table and every sub-table beneath it, with its module, function, settings type, default value and error type named and stable, and no second reader of that table shall exist anywhere in the tool.
2. Every field of the resolved load-settings type shall carry a default, so that a feature adding a field breaks no existing construction site and an absent settings file or absent `[load]` table resolves entirely to documented defaults rather than to an error.
3. The reader shall ignore keys and sub-tables inside `[load]` that it does not know, so that a later feature adds its own sub-table without modifying the reader and an older tool reading a newer file does not fail.
4. The load pass shall read the `[load]` table exactly once per invocation and shall own the resolved settings for that pass; no value drawn from that table shall additionally be threaded into the pass as a separate parameter.
5. The resolved load settings shall be the value bound into each calculator's per-activity context (Requirement 1.12), so a calculator consults configuration through the contract and no other reader of the table is needed.
6. If the `[load]` table or any value the reader owns is malformed, the fitdocs CLI shall fail with an instructive configuration error naming the settings file and the offending key, before any document is read or written.
7. _(added 2026-07-25 by the cross-spec import-direction ruling)_ The load-settings reader shall be free to aggregate each feature's own typed sub-settings from that feature's own module, and shall therefore sit *above* the calculator-contract module in the import direction: the contract module's reference to the resolved settings type shall exist for type checking only and shall never be a runtime import, and no package initializer beneath the load package shall eagerly import a module that in turn reaches the settings module. Conformance shall be demonstrated by importing the load package, the contract module and each load sub-package in a fresh interpreter, since an in-process re-import proves nothing.
