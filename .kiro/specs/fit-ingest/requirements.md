# Requirements Document

## Project Description (Input)
Foundation layer for fitdocs (an installable `.fit` → markdown personal
knowledge manager for fitness). Athletes using fitdocs need every downstream
feature — workout documents, charts, training-load calculation — to work from
a reliable, typed view of a workout, but today nothing exists: `.fit` is a
binary format with device quirks, sport-specific message types, and
absent-vs-zero pitfalls. This spec delivers a pure library layer that parses
a `.fit` file into a normalized activity model (session summary, laps
projected onto sample indices, per-sample channel arrays, strength sets from
`set_mesgs`, devices, sport/modality detection) and computes derived metrics
locally at fitdocs.ai parity (moving/elapsed time, distance, HR/power/cadence
aggregates, normalized power, intensity factor, variability index, efficiency
factor, decoupling, pace, elevation, time-in-zone, TRIMP, power TSS) — with
no user-facing surface of its own. See `.kiro/specs/fit-ingest/brief.md` and
`docs/reference/fitdocs-ai-reference.md`.

> **Amended.** Amendment 1 below removes `docs/reference/fitdocs-ai-reference.md`
> §2 as the cited authority for any constant this library computes from. The
> description above is preserved as the original input; where it names that
> document as the source of a formula, Requirement 15 now governs.

## Amendment 1 (2026-07-26): primary sourcing for the metrics layer's constants

Every numeric constant in the metrics package is cited to
`docs/reference/fitdocs-ai-reference.md` §2 — a working extraction from a
secondary web source, never a published methodology. That was adequate while
fit-ingest was the only layer computing anything. It is not adequate now, and
the project has already recorded why: `src/fitdocs/load/channels/sources.py`
opens by naming this module's TRIMP coefficients as a formula "cited only to
`docs/reference/fitdocs-ai-reference.md` — a secondary web source presented
without qualification — and that exact coefficient string was refuted 0-3 in
adversarial verification." That module marks `BANISTER_TRIMP` as
`SECONDARY_ATTESTATION` and states plainly that "re-sourcing them is out of
this feature's scope." This amendment is that re-sourcing.

Three findings drove it.

- **The constants' provenance is unaudited.** `docs/reference/` is described by
  the repository's own README as research backing the specs, not as a source of
  record. Yet `_TRIMP_COEFFICIENT`, `_TRIMP_EXPONENT`, `_TSS_SCALE`,
  `_NP_ROLLING_WINDOW_S`, `_NP_MIN_SPAN_S` and `_ALTITUDE_SMOOTHING_WINDOW` all
  point there, and the moving-time threshold is not even a named constant — it
  is the bare literal `0.5` at `src/fitdocs/metrics/aggregates.py:103`. Every
  metric a fitdocs document reports rests on that chain.
- **The obligation already exists one layer down.** `.kiro/steering/tech.md`
  requires load calculators to be "validated against their source methodology's
  own published worked examples, not only against themselves," and
  `load-channels` Requirement 8 makes "no constant without a citation" a
  structural, test-enforced rule. The foundation layer those rules sit on top of
  carries no equivalent obligation. This amendment gives it one.
- **A sex-specific model was collapsed into a single pair.** Banister's
  training-impulse weighting defines different terms per sex. fit-ingest applies
  one pair to every athlete and calls the result "sex-neutral" in its own
  docstring. Whether that collapse is defensible is precisely the kind of
  question reading the primary text answers, and the answer is a different
  reported number for some athletes.

The amendment therefore requires that each constant be **read from the
publishing work's own text** (Requirement 15), that the citation live in code as
a **typed, testable record** rather than a docstring path (Requirement 16), that
the training-impulse weighting become a **caller-selected pair** with the
current pair as its default (Requirement 17), and that documents already written
be corrected **by regeneration** (Requirement 18) — the migration story
`src/fitdocs/sync.py` already establishes: "regeneration *is* the upgrade, there
is no in-place transform."

Requirements 7, 8, 9 and 11 are revised in place where they name the reference
document as an authority; Requirements 15 through 18 are added. **No existing
requirement or criterion is renumbered** — code docstrings, `design.md` and
`tasks.md` all cite these numbers.

Two consequences are deliberate and were confirmed before drafting.

- **A primary text that cannot be obtained blocks the feature.** Requirement
  15.4 does not permit falling back to a secondary attestation, which was the
  pattern `MINETTI_2002` and `BANISTER_TRIMP` set one layer down at the time
  this amendment was drafted. Banister (1991) is a book chapter and Morton
  (1990) is a paywalled journal paper, so this was assessed as a real risk of
  an unsatisfiable requirement rather than a theoretical one. It was accepted
  knowingly: the point of the amendment is that these numbers stop being taken
  on trust. This applies where a defining work *exists* and proves hard to
  obtain — not to a constant no published work defines at all, which the
  revision below separates out. _(The risk materialized as accepted, then
  retired: `.kiro/specs/load-channels` re-sourced `MINETTI_2002` to
  `PRIMARY_TEXT` 2026-07-27 and `BANISTER_TRIMP` to `PRIMARY_TEXT` 2026-07-29,
  queue 2026-07-27-banister-morton-primary-texts-obtained, once both Banister
  (1991) and Morton, Fitz-Clarke & Banister (1990) were obtained and read in
  full — see `docs/reference/banister-trimp-primary-sources.md`. Neither
  citation remains an illustration of the pattern this bullet describes;
  design.md's own Amendment 1 section already records the resolved sourcing
  table this criterion's risk assessment predates.)_
- **The weighting selection reaches fit-ingest as an argument, never from a
  file.** Athlete profile storage is out of this spec's scope and stays out
  (Requirement 17.3); the stored field is an adjacent expectation on the spec
  that owns `athlete.py`.

### Revision (2026-07-26): the fitdocs-chosen category

Amendment 1 was blocked at its own design gate, before any design was drafted,
by a case its criteria had no category for. Requirement 15.6 enumerates seven
items — the training-impulse weighting counts as one item though it names two
constants, the coefficient and the exponent, so the enumeration covers eight
named constants in all — and required each to be read from "the published
work that defines them" — but **three of the seven items are defined by no
published work at all**:

| Constant | Site | Defining work |
|---|---|---|
| moving-time movement threshold `0.5` | `metrics/aggregates.py:103` | none — a fitdocs convention, not even a named constant |
| minimum power-stream span `30.0` | `metrics/power.py:55` | none — fitdocs' choice of when to *refuse* to report |
| altitude-smoothing window `10` | `metrics/aggregates.py:238` | none — its only cited source is the §2 document 15.5 forbids naming |

Criterion 15.1 presupposed a defining work exists; 15.7 exempted only values
carrying no methodological choice, which a movement threshold plainly carries;
and 15.4 then blocked the feature on a primary text that could never be
obtained because none was ever written. Amendment 1 as first drafted was
therefore **unsatisfiable by construction** — not through the accepted
Banister/Morton risk, but through a category it was missing.

The revision adds that category. Criteria 15.8 and 15.9 are added and 15.1,
15.4, 15.6 and 16.4 are scoped to match; 16.7 carries the record shape.
**No criterion is renumbered and none is withdrawn.** A constant no published
work defines is recorded as fitdocs' own choice, with its justification and
supporting measurement — the semantics `VerificationStatus.FITDOCS_MEASURED`
already established one layer down at
`src/fitdocs/load/channels/sources.py:60`, rather than a fourth vocabulary.

Criterion 15.9 is what keeps this from reopening the hole the amendment
closes: the *conclusion* that no published work defines a value must itself be
recorded with what was searched, so "fitdocs chose it" cannot become a cheaper
answer than obtaining a text that exists. Requirement 15.4's bar over Banister,
Morton and Coggan is untouched, and recording a secondary attestation remains
forbidden.

### Revision (2026-07-30): the rolling-window start condition

Task 13.1 (`142da42`) changed the normalized-power rolling mean to emit only
complete windows — the amendment's single value-moving change, recorded in
`design.md`'s PowerSeriesMetrics section and `research.md` Decision D7.
Amendment 1 shipped complete at task 13.4 (`68be52c`). Criterion 8.4 cites the
rolling mean's window width, averaging exponent, and minimum span to
Requirement 15, but never stated *where the window starts*: before criterion
8.9 existed, nothing in this document would have failed if a later change
reverted `_trailing_rolling_mean` to the partial-window form it replaced,
moving normalized power (and with it intensity factor, variability index,
training-stress score, and cycling efficiency factor) a second time — for any
activity whose dropped leading windows' mean fourth power differs from the
retained series' — with no requirement noticing.

Criterion 8.9 closes that gap. **No existing criterion is renumbered.** See
`.kiro/queue/closed/2026-07-28-np-window-start-has-no-criterion.md` for the
finding; this is that item's resolution.

## Amendment 2 (2026-07-27): a declared scale/offset is decoding, not interpretation

Requirement 14.2 read "pass developer-field values through as decoded ...
without interpretation, derivation, or renaming" — wording broad enough to
also forbid applying a scale or offset the FIT file's own `field_description`
message declares for that field. `garmin-fit-sdk` parses a developer field's
declared `scale`/`offset` into its field profile but never applies them
(unlike a native profile field, where it does), so `extract_developer_fields`
returned a raw, wrong-by-a-constant-factor number whenever a writer declared
either. No file in the current corpus does — all six developer-field
descriptors across 74 files declare `scale=None` — so this was latent, not
active, but Requirement 14.2 as worded endorsed the gap rather than closing
it.

The distinction this amendment draws: applying a scale/offset the file
**itself** declares is decoding the value the file recorded — the same act
`garmin-fit-sdk` already performs for every native profile field, using the
FIT-protocol formula `value / scale - offset`. Inferring an **undeclared**
convention (for example, guessing that an integer field is "really"
hundredths because no writer would record something that granular — the
`AVG METs` defect this same investigation surfaced) remains interpretation,
and stays forbidden. Requirement 14.2 is revised to say which is which;
Requirement 14.1, 14.3, and 14.4 are unaffected and unchanged. No criterion is
renumbered.

**Revision (2026-07-27, post-review):** review of this amendment's first commit
found the amended criterion prescribed division by zero for a DECLARED
`scale=0` ("defaulting an undeclared term to its identity" does not cover a
term that IS declared), left the non-numeric passthrough undocumented outside
a docstring, and — the critical finding — left `render/sections.py` applying
its own hardcoded hundredths-guess factor UNCONDITIONALLY, so a writer that
actually declares a scale would have its already-correct, ingest-decoded value
silently multiplied by 0.01 a second time on the rendered page (measured:
`9.5` in `Activity.developer_fields` rendered as `0.1`). Two questions went to
the maintainer and both are now ruled:

- **`scale=0`:** OMIT the field entirely from the developer-field mapping
  rather than emit the raw undecoded value. The raw-value fallback would
  reinstate exactly the wrong-by-a-constant-factor, no-signal shape the
  originating queue item condemned, and conflicts with CLAUDE.md's
  absent-data-is-`None` rule and this requirement's own Criterion 14.4
  never-fabricate posture. Criterion 14.2 above is revised to state this.
- **What the render layer needs surfaced:** scale/offset DECLAREDNESS only —
  not the full field description (`units`, `components`, `bits`,
  `accumulate` stay out of scope and remain the open question in the
  originating queue item). `Activity.developer_fields_declared_scale`
  (`src/fitdocs/model.py`) carries this as a `frozenset` of field names ingest
  already decoded against a declaration; `render/sections.py` consults it and
  applies its hundredths-guess fallback only when a key is ABSENT from that
  set. This is a workout-docs-consuming change to `Activity`'s contract; see
  this amendment's `cross_spec` record in `spec.json`.

The non-numeric passthrough (a malformed declaration on a real value, e.g. a
string-typed field) is unchanged in behavior but is now stated in Criterion
14.2 itself rather than only in `summary.py`'s docstrings.

## Introduction

fit-ingest is the foundation layer of fitdocs: a pure library that decodes a
`.fit` file into a normalized, typed activity model and computes derived
metrics locally at fitdocs.ai parity. It has no user-facing surface — no CLI,
no prompts, no file output — and exists so downstream features (workout-docs
rendering, training-load calculation) consume one reliable contract instead
of re-reading binary FIT data. Two principles govern every requirement:
absent data is `None`, never a fabricated zero or default; and derived
metrics that lack required inputs return `None` instead of guessing.

## Boundary Context

- **In scope**: `.fit` decode and validation; the normalized activity model
  (session summary, laps projected onto sample indices, per-sample channel
  arrays, strength sets, devices, sport/modality detection); derived-metric
  computation over the model (times, distance, pace/speed, HR/power/cadence
  aggregates, normalized power, intensity factor, variability index,
  efficiency factor, decoupling, elevation, temperature, time-in-zone given
  caller-supplied zone boundaries, TRIMP, power TSS, calories passthrough);
  generic exposure of session-scoped developer-defined fields as a
  name-to-raw-value mapping (no interpretation).
- **Out of scope**: file discovery, CLI, configuration, markdown rendering,
  and charts (workout-docs spec); the `LoadCalculator` interface, load
  methodologies (e.g. the withdrawn methodology), athlete profile storage, and
  interactive prompting (training-load spec); `.gpx`/`.tcx` formats; zone
  *definitions* — athlete thresholds and zone boundaries arrive as
  caller-supplied inputs, never from stored profile data owned here.
- **Adjacent expectations**: workout-docs renders from the activity model and
  training-load calculates from it — the model schema is the shared,
  versioned contract, and breaking changes ripple to both. Training-load
  methodology is running-only in the first pass; fit-ingest carries the
  running data that layer needs (samples, timestamps, heart rate, speed/pace,
  session summary) but performs no methodology-based load calculation itself.
  TRIMP and power TSS in this spec are generic derived metrics at reference
  parity, not `LoadCalculator` results.
- **In scope (Amendment 1)**: the provenance of every numeric constant this
  library computes a reported metric from — which published work defines it,
  where in that work it appears, and whether the value was read from that work's
  own text, or, where no published work defines it, that fitdocs chose it and on
  what basis; the training-impulse weighting becoming a caller-selected pair; and
  correcting whatever metric values the re-sourcing changes.
- **Out of scope (Amendment 1)**: the constants of any layer other than this
  one — `load-channels` already carries its own citation record and Requirement 8
  obligations, and nothing here changes them; the chart palette and layout
  figures cited to `docs/reference/fitdocs-ai-reference.md` §3, which are
  presentation choices owned by workout-docs, not values a metric is computed
  from; storing the athlete's weighting selection anywhere; and re-deriving any
  formula's *shape* — this amendment audits the numbers a published work fixes,
  not the decision to implement that work.
- **Adjacent expectations (Amendment 1)**: the weighting selection reaches this
  library as a caller-supplied argument, exactly as thresholds and zone
  boundaries already do; whichever spec owns the athlete profile decides whether
  to store it and how to prompt for it, and fit-ingest works unchanged if it
  never does. Correcting already-written documents is likewise not this
  library's act: fit-ingest reports a different number, and the document layer's
  existing format-version gate and `regen` pass are what turn that into
  corrected files on disk. This library still writes nothing.

## Requirements

### Requirement 1: FIT File Decoding and Validation
**Objective:** As a fitdocs developer, I want the library to decode a `.fit`
file or fail with a clear, specific error, so that downstream layers never
operate unknowingly on misparsed or partial data.

#### Acceptance Criteria
1. When given the path or raw bytes of a valid `.fit` file, the fit-ingest library shall decode it and return a normalized activity model.
2. If the input is not a FIT file, the fit-ingest library shall raise a descriptive error identifying the input as non-FIT and shall not return an activity model.
3. If the FIT integrity check fails, the fit-ingest library shall raise a descriptive error that is distinguishable from the non-FIT error.
4. When decoding completes but individual messages produced decode errors, the fit-ingest library shall return the activity model together with the collected decode errors so callers can surface them.
5. The fit-ingest library shall never modify or delete the source `.fit` file.

### Requirement 2: Normalized Activity Model Contract
**Objective:** As a downstream feature author (workout-docs, training-load),
I want a typed, versioned activity model, so that renderers and load
calculators depend on one stable contract instead of FIT internals.

#### Acceptance Criteria
1. The fit-ingest library shall expose an activity model comprising: session summary, laps, per-sample channel arrays, strength sets, device information, detected sport and modality, and source provenance.
2. The activity model shall carry a schema version identifier so downstream consumers can detect contract changes.
3. The activity model shall record source provenance as the content hash of the source `.fit` bytes, plus the source path when decoded from a file.
4. When timestamps are decoded, the fit-ingest library shall express them as timezone-aware UTC datetimes, correctly converted from the FIT epoch (1989-12-31 UTC).
5. The activity model shall represent every absent value as `None` and shall never substitute zero or any other fabricated default for data the device did not record.
6. The activity model shall be consumable without FIT-format knowledge: all FIT-specific field names, units, and encodings are normalized at ingest.

### Requirement 3: Per-Sample Channel Extraction
**Objective:** As a chart renderer or metric consumer, I want the record
stream as parallel typed channel arrays, so that time-series computation and
plotting need no FIT-message handling.

#### Acceptance Criteria
1. When record messages are present, the fit-ingest library shall extract per-sample channels as parallel arrays of equal length with one entry per record: time offset since activity start (seconds), heart rate, power, cadence, speed, cumulative distance, altitude, latitude, longitude, and temperature.
2. When a channel value is absent for a sample, the fit-ingest library shall store `None` at that index and keep positions aligned across all channel arrays.
3. When both an enhanced and a basic variant of a field are present (speed, altitude), the fit-ingest library shall prefer the enhanced variant and fall back to the basic variant.
4. When position coordinates are recorded in semicircles, the fit-ingest library shall convert them to decimal degrees.
5. The fit-ingest library shall express speed in meters per second, distance in meters, altitude in meters, and temperature in degrees Celsius after scale/offset normalization.
6. The fit-ingest library shall preserve raw sample values in the channel arrays without smoothing or resampling; smoothing is a concern of individual metric formulas and downstream renderers.

### Requirement 4: Session, Lap, and Device Extraction
**Objective:** As a docs renderer, I want session totals, laps mapped onto
the sample stream, and device information, so that summary views and split
tables come straight from the model.

#### Acceptance Criteria
1. When a session message is present, the fit-ingest library shall expose its summary fields — including start time, total elapsed time, total timer time, total distance, total calories, total ascent, total descent, and sport — with absent fields as `None`.
2. If no session message is present, the fit-ingest library shall fall back to activity-level totals where available and leave remaining summary fields as `None`.
3. When lap messages are present, the fit-ingest library shall expose each lap's recorded summary fields and shall project each lap onto the record stream as an inclusive start/end sample index range derived from matching lap start times to record timestamps.
4. If a lap cannot be matched to any record samples, the fit-ingest library shall set that lap's sample index range to `None` while preserving its recorded summary fields.
5. When device information messages are present, the fit-ingest library shall expose the reporting devices — including manufacturer, product, and battery status where recorded — with absent fields as `None`.

### Requirement 5: Sport and Modality Detection
**Objective:** As a downstream consumer, I want a normalized sport label and
a coarse modality, so that per-sport rendering and calculator applicability
checks never parse device-specific sport codes.

#### Acceptance Criteria
1. When the FIT sport is cycling, running, swimming, walking, hiking, or rowing, the fit-ingest library shall map it to the corresponding normalized sport label (Ride, Run, Swim, Walk, Hike, Rowing).
2. When the FIT sport is training, fitness_equipment, or generic, the fit-ingest library shall map it to the normalized sport label Workout.
3. If the FIT sport is unrecognized or absent, the fit-ingest library shall assign the fallback sport label Workout and shall not fail.
4. The fit-ingest library shall classify each activity into exactly one modality: run, bike, swim, strength, or other.
5. When the FIT sub-sport indicates strength training, the fit-ingest library shall classify the modality as strength.
6. When the FIT sub-sport indicates an indoor variant, the fit-ingest library shall flag the activity as indoor, separately from the sport label.

### Requirement 6: Strength Set Extraction
**Objective:** As a lifter recording with a standard watch, I want everything
the watch recorded about my sets exposed faithfully, so that my
weight-training document reflects the real session and I can fill in the
exercises manually later.

#### Acceptance Criteria
1. When FIT set messages (`set_mesgs`) are present, the fit-ingest library shall extract one set entry per set message, preserving recorded order.
2. The fit-ingest library shall expose for each set the recorded fields among: set type (active or rest), start time, duration, repetition count, weight, and exercise category/name — with any field the watch did not record as `None`.
3. When exercise title information is present, the fit-ingest library shall expose it as the set's exercise name.
4. If an activity contains no set messages, the fit-ingest library shall represent strength sets as an empty collection and shall not treat this as an error.
5. The fit-ingest library shall never infer, default, or fabricate set fields (for example, an assumed weight or repetition count) beyond what the file records.

### Requirement 7: Time, Distance, and Speed Metrics
**Objective:** As a docs renderer, I want the core motion metrics computed
locally, so that summary statistics work fully offline at fitdocs.ai parity.

#### Acceptance Criteria
1. _(revised by Amendment 1)_ When a session timer total is recorded, the fit-ingest library shall report it as moving time; if it is absent, the fit-ingest library shall derive moving time from the sample stream using a movement threshold and a distance-increase fallback whose values are sourced and cited per Requirement 15.
2. The fit-ingest library shall report elapsed time from session totals when recorded, otherwise derived from the span of record timestamps.
3. The fit-ingest library shall report total distance from session totals when recorded, otherwise from the final value of the cumulative distance channel.
4. When speed data is available, the fit-ingest library shall report average and maximum speed, preferring recorded session values and otherwise computing them from the speed channel.
5. When total distance and moving time are both available, the fit-ingest library shall compute average pace as moving time per unit distance.
6. If the required inputs for any metric in this requirement are unavailable, the fit-ingest library shall report that metric as `None`.

### Requirement 8: Heart Rate, Power, and Cadence Metrics
**Objective:** As a cyclist or runner, I want heart-rate, power, and cadence
metrics — including the advanced power metrics fitdocs.ai imports from
Intervals.icu — computed locally, so that my documents are complete without
any external service.

#### Acceptance Criteria
1. When heart-rate data is available, the fit-ingest library shall report average and maximum heart rate, preferring recorded session values and otherwise computing them from the heart-rate channel.
2. When power data is available, the fit-ingest library shall report average and maximum power, preferring recorded session values and otherwise computing them from the power channel.
3. When cadence data is available, the fit-ingest library shall report average and maximum cadence, preferring recorded session values and otherwise computing them from the cadence channel.
4. _(revised by Amendment 1)_ When power samples are present, the fit-ingest library shall compute normalized power by 1 Hz resampling with coasting as zero, a trailing rolling mean, and a power mean, whose window width, averaging exponent and minimum required span are sourced and cited per Requirement 15.
5. When normalized power is computed and the caller supplies functional threshold power, the fit-ingest library shall compute intensity factor; if functional threshold power is not supplied, intensity factor shall be `None`.
6. When normalized power and average power are both available, the fit-ingest library shall compute variability index as their ratio.
7. When output data (normalized power for cycling; speed for running) and average heart rate are both available, the fit-ingest library shall compute efficiency factor as the ratio of output to average heart rate.
8. When output and heart-rate data cover both halves of the activity, the fit-ingest library shall compute aerobic decoupling as the percentage change of the output-to-heart-rate ratio between the first and second halves; if either half lacks sufficient data, decoupling shall be `None`.
9. _(added by Amendment 1, revision 2026-07-30)_ The rolling mean criterion 8.4 establishes shall contribute only windows spanning the full cited width: it shall not average over a shorter span at the start of the power stream, and a power-stream span insufficient to complete one such window shall report normalized power as `None`.

### Requirement 9: Elevation and Temperature Metrics
**Objective:** As a runner or cyclist in varied terrain, I want elevation and
temperature aggregates, so that climb and conditions appear in my documents.

#### Acceptance Criteria
1. _(revised by Amendment 1)_ When a session ascent total is recorded, the fit-ingest library shall report it as elevation gain; if it is absent and altitude samples are present, the fit-ingest library shall derive elevation gain from positive deltas of smoothed altitude, with the smoothing window width sourced and cited per Requirement 15.
2. When a session descent total is recorded, the fit-ingest library shall report it as elevation loss; if it is absent and altitude samples are present, the fit-ingest library shall derive elevation loss from negative deltas of the same smoothed altitude.
3. When altitude samples are present, the fit-ingest library shall report minimum and maximum altitude.
4. When temperature samples are present, the fit-ingest library shall report minimum, maximum, and average temperature.
5. If altitude or temperature data is entirely absent, the fit-ingest library shall report the corresponding metrics as `None`.

### Requirement 10: Time-in-Zone Computation
**Objective:** As the workout-docs and training-load layers, I want
time-in-zone for heart rate, power, and pace computed from caller-supplied
zone boundaries, so that zone displays and load math use the athlete's actual
zones rather than hard-coded bands.

#### Acceptance Criteria
1. When the caller supplies zone boundaries for a channel (heart rate, power, or pace) and that channel has samples, the fit-ingest library shall compute the total time spent in each zone.
2. The fit-ingest library shall attribute the duration between consecutive samples to the zone containing the earlier sample's value.
3. The fit-ingest library shall exclude from all zones any duration whose attributing sample value is `None`.
4. The fit-ingest library shall accept an arbitrary number of caller-defined zones and shall not embed default or fallback zone boundaries.
5. If zone boundaries are not supplied for a channel, or that channel has no samples, the fit-ingest library shall report time-in-zone for that channel as `None` rather than zeros.

### Requirement 11: Training Stress Metrics and Calories
**Objective:** As an athlete tracking training stress, I want TRIMP and power
TSS computed from documented formulas and calories passed through, so that
generic stress numbers are available to any consumer without fabrication.

#### Acceptance Criteria
1. _(revised by Amendment 1)_ When heart-rate samples are present and the caller supplies resting and maximum heart rate, the fit-ingest library shall compute TRIMP per Banister's training-impulse formula, with its weighting terms sourced and cited per Requirement 15 and selected per Requirement 17; if resting or maximum heart rate is not supplied, TRIMP shall be `None`.
2. _(revised by Amendment 1)_ When power samples are present and the caller supplies functional threshold power, the fit-ingest library shall compute power TSS per Coggan's training-stress-score formula, with its scale sourced and cited per Requirement 15; if functional threshold power is not supplied, power TSS shall be `None`.
3. When session calories are recorded, the fit-ingest library shall pass them through unchanged; the fit-ingest library shall never estimate calories.
4. The fit-ingest library shall perform no methodology-based load calculation (for example, points from the withdrawn methodology); TRIMP and power TSS are generic derived metrics, not `LoadCalculator` results.

### Requirement 12: Missing-Data Integrity
**Objective:** As a fitdocs user, I want absent data represented honestly
everywhere, so that no document or load number is ever built on a fabricated
value.

#### Acceptance Criteria
1. If the required inputs for any derived metric are absent or insufficient, the fit-ingest library shall return `None` for that metric rather than raising an error or substituting a fabricated value.
2. When a channel is entirely absent from an activity, the fit-ingest library shall report metrics depending on that channel as `None` while computing all independent metrics normally.
3. When a device records a true zero value (for example, zero power while coasting), the fit-ingest library shall preserve the zero as recorded data; `None` shall be reserved exclusively for values the device did not record.

### Requirement 13: Library Purity and Determinism
**Objective:** As a fitdocs developer, I want ingestion to be a pure,
deterministic library layer, so that outputs are reproducible and golden-file
tests are reliable.

#### Acceptance Criteria
1. The fit-ingest library shall perform no input/output other than reading the provided `.fit` input: no file writes, no network access, and no user interaction.
2. When given identical input bytes and identical caller-supplied parameters, the fit-ingest library shall produce an identical activity model and identical derived-metric values on every invocation.
3. The fit-ingest library shall compute derived metrics as pure functions over the activity model and caller-supplied athlete parameters, with no hidden state or configuration.

### Requirement 14: Developer-Defined Field Exposure
**Objective:** As a downstream feature author (workout-docs, training-load),
I want session-scoped developer-defined FIT fields exposed generically by
name, so that exporter-specific values such as a stable session identifier
or an estimated RPE reach consumers without fit-ingest interpreting them.

#### Acceptance Criteria
1. When developer field descriptions are present (`field_description_mesgs` with `developer_data_id_mesgs`), the fit-ingest library shall expose the developer fields recorded on the session message as a mapping from each described field name to its raw decoded value.
2. _(revised by Amendment 2, corrected by its post-review revision)_ The fit-ingest library shall decode each developer-field value by applying any scale and/or offset that field's own `field_description` declares — the FIT-protocol formula `value / scale - offset`, defaulting an UNDECLARED term to its identity (scale 1, offset 0) — preserving array values element-wise (for example, a 16-byte identifier stays 16 entries). A DECLARED `scale` of `0` is unrepresentable (division by zero, not an identity): the fit-ingest library shall OMIT that field entirely from the developer-field mapping rather than fabricate a value or emit the raw undecoded one — the maintainer's ruling (2026-07-27, see the amendment record), pinned by a test. A non-numeric raw value under a declared scale (for example a string-typed field) shall pass through UNSCALED — the malformed part is the declaration, not the value, which is real data worth keeping. The fit-ingest library shall not infer any scale, offset, or other convention the file does not itself declare, derive a value, or rename a field.
3. If an activity contains no developer field descriptions, or the session message records none of the described fields, the fit-ingest library shall represent the developer-field mapping as empty and shall not treat this as an error.
4. The fit-ingest library shall include only fields that are both described in a field description message and recorded on the session message, and shall never fabricate or default a developer-field entry.

### Requirement 15: Primary-Source Provenance for Computed Constants
_(added by Amendment 1)_

**Objective:** As an athlete reading the numbers in my own training documents,
I want every constant those numbers are computed from to have been read from
the publishing work's own text — or, where no published work defines it, to be
declared as fitdocs' own choice — so that no metric fitdocs reports rests on a
second-hand summary nobody checked.

#### Acceptance Criteria
1. _(revised: fitdocs-chosen category)_ Where a published work defines a constant's value, the fit-ingest library shall compute a reported metric from that constant only if its value has been read from that work's primary text; where no published work defines it, criterion 15.8 governs instead.
2. Where a constant is a term of Banister's training-impulse weighting, the fit-ingest library shall record Banister (1991) and Morton (1990) as its sources, together with the locator within each work at which the value appears.
3. When a value read from a primary text differs from the value the fit-ingest library computed with before Amendment 1, the fit-ingest library shall adopt the primary-text value and shall record both the adopted value's locator and the value it replaced.
4. _(revised: fitdocs-chosen category)_ If the primary text for a constant a published work defines cannot be obtained, then the fit-ingest library shall not present that constant as verified against a primary text and shall not record an attestation from secondary sources in its place; such a constant blocks this feature's completion rather than shipping under a weaker status. This criterion applies only where a defining published work exists; a constant governed by 15.8 is not blocked by it.
5. The fit-ingest library shall not name `docs/reference/fitdocs-ai-reference.md`, or any other working document in `docs/reference/`, as the source of a numeric constant it computes a reported metric from.
6. _(revised: fitdocs-chosen category)_ The fit-ingest library shall classify each of the following under either criterion 15.1 or criterion 15.8, leaving none unclassified: the training-impulse weighting coefficient and exponent, the training-stress-score scale, the normalized-power rolling-window width, the normalized-power averaging exponent, the minimum power-stream span below which normalized power is not reported, the moving-time movement threshold, and the altitude-smoothing window width.
7. The fit-ingest library shall exempt from criteria 15.1 through 15.5 only those numeric values that carry no methodological choice — unit conversions, arithmetic identities, and percentage scalings that follow from a definition already cited.
8. _(added: fitdocs-chosen category)_ Where no published work defines a constant's value, the fit-ingest library shall record that constant as fitdocs' own choice, stating the justification for the value and the measurement supporting it where the choice rests on one, and shall never present such a constant as verified against a primary text.
9. _(added: fitdocs-chosen category)_ Where the fit-ingest library records a constant under criterion 15.8, it shall also record the basis for concluding that no published work defines that value — what was searched and what was found — so that criterion 15.8 cannot be used to avoid obtaining a primary text that exists.

### Requirement 16: The Citation Record in Code
_(added by Amendment 1)_

**Objective:** As a fitdocs maintainer adding or changing a metric, I want each
constant's source recorded as a machine-readable artifact rather than as prose
in a docstring, so that an uncited constant fails a check instead of shipping
unnoticed.

#### Acceptance Criteria
1. The fit-ingest library shall carry the source of each constant covered by Requirement 15 as a machine-readable record stating the authors, year, work, locator within that work, and verification status.
2. The fit-ingest library shall associate every constant covered by Requirement 15 with exactly one such record.
3. If a numeric constant covered by Requirement 15 has no associated citation record, then the fit-ingest library's own checks shall fail rather than the constant shipping uncited.
4. _(revised: fitdocs-chosen category)_ The fit-ingest library shall record a verification status distinguishing a value read from the cited work's own text from one chosen by fitdocs itself under criterion 15.8, and shall never record the former where only the latter holds. Recording a value as attested only by secondary sources remains forbidden by criterion 15.4.
5. Where the fit-ingest library's behavior departs deliberately from what the cited work specifies, the fit-ingest library shall record the departure, what the source specifies, and the reason for departing, alongside the citation.
6. The fit-ingest library shall keep its citation records readable by any consumer without computing a metric, so that a document or report can name the source of a number it displays.
7. _(added: fitdocs-chosen category)_ Where a record carries the fitdocs-chosen status, the fit-ingest library shall carry with it the justification required by criterion 15.8 and the basis required by criterion 15.9, in place of the authors, year, work and locator a published source supplies.

### Requirement 17: Selectable Training-Impulse Weighting
_(added by Amendment 1)_

**Objective:** As an athlete whose sex the training-impulse model distinguishes,
I want TRIMP computed with the weighting terms its source specifies for me, so
that my training-impulse numbers are the ones the published model actually
defines rather than another athlete's.

#### Acceptance Criteria
1. Where the caller supplies a weighting selection, the fit-ingest library shall compute TRIMP using the weighting pair the cited primary text specifies for that selection.
2. If the caller supplies no weighting selection, then the fit-ingest library shall compute TRIMP using the weighting pair it applied before Amendment 1, rather than reporting TRIMP as `None`.
3. The fit-ingest library shall accept the weighting selection as a caller-supplied input only, and shall not read it from stored athlete profile data or from any configuration file.
4. If the caller supplies a weighting selection for which the cited source defines no pair, then the fit-ingest library shall reject the input with an error naming the selection and the selections the source defines, rather than substituting a pair.
5. When resting or maximum heart rate is absent, the fit-ingest library shall report TRIMP as `None` regardless of whether a weighting selection was supplied.
6. The fit-ingest library shall report, alongside TRIMP, which weighting pair produced the value, so that two athletes' training-impulse numbers are never compared without that distinction being visible.

### Requirement 18: Correcting Already-Written Documents by Regeneration
_(added by Amendment 1)_

**Objective:** As a fitdocs user with a library of documents already on disk, I
want any metric value this re-sourcing changes to be corrected by rebuilding
documents from their source `.fit` files, so that my library never mixes numbers
computed under two different sets of constants without telling me.

#### Acceptance Criteria
1. When Amendment 1 changes the value the fit-ingest library reports for a metric of an already-documented activity, the fitdocs document-format version shall advance, so that every document written before the change is recognized as below the current version.
2. When a document below the current format version is processed by the fitdocs regeneration pass, the fitdocs document layer shall rewrite it from its source `.fit` file at the current version; no in-place transform of an existing document's metric values shall be performed.
3. While documents written before Amendment 1 remain unregenerated, the fitdocs audit shall report them as stale rather than as current.
4. If a constant's primary-text value equals the value the fit-ingest library already computed with, then the fit-ingest library shall report identical metric values and no document shall be made stale on that constant's account.
5. The fit-ingest library shall itself read, write, and migrate no document; its only contribution to this correction is reporting a different value from the same input bytes.
