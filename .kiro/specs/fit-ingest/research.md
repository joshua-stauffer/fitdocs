# Research & Design Decisions — fit-ingest

## Summary
- **Feature**: `fit-ingest`
- **Discovery Scope**: New Feature (greenfield foundation layer)
- **Key Findings**:
  - `garmin-fit-sdk` 21.208.0 (PyPI, 2026-06-16) verifies the full decode API
    the reference app used — and now also ships an `Encoder`, so synthetic
    test fixtures can be built with the same official SDK (no extra encode
    dependency).
  - FIT `set` message fields are confirmed: `set_type` ('active'/'rest'),
    `duration` (s), `repetitions`, `weight` (kg after scale), `start_time`,
    `category` (string array), `category_subtype` (raw uint16 array requiring
    a manual Profile lookup for the exercise name), `wkt_step_index`,
    `message_index`. `exercise_title` messages appear only for structured
    workouts — free watch recordings must not depend on them.
  - Sport/sub-sport enum strings and `device_info` fields (manufacturer,
    product_name, serial_number, software_version, battery_status values)
    are confirmed from the SDK profile, giving the sport map and indoor
    detection a verified vocabulary.

## Research Log

### garmin-fit-sdk API surface (Python)
- **Context**: Steering pins `garmin-fit-sdk`; the design needs verified
  call signatures and message keys before committing contracts.
- **Sources Consulted**: PyPI `garmin-fit-sdk` 21.208.0 wheel (decoder.py,
  encoder.py, profile.py inspected), github.com/garmin/fit-python-sdk README.
- **Findings**:
  - `Stream.from_file(path)` / `Stream.from_byte_array(bytes)`;
    `Decoder.is_fit()`, `Decoder.check_integrity()` (both advance the
    stream — reset before `read()`), `Decoder.read(...)` returns
    `(messages, errors)`.
  - `read()` defaults: `apply_scale_and_offset=True`,
    `convert_datetimes_to_dates=True`, `convert_types_to_strings=True`,
    `expand_sub_fields=True`, `expand_components=True`,
    `merge_heart_rates=True` (requires scale/offset + component expansion).
  - Message dict keys: `record_mesgs`, `session_mesgs`, `lap_mesgs`,
    `set_mesgs`, `exercise_title_mesgs`, `device_info_mesgs`, `sport_mesgs`,
    `activity_mesgs`, `file_id_mesgs`, …
  - **Encoder exists in 21.208.0**: `Encoder().write_mesg(dict)` with
    profile field names (`'mesg_num'` required), `close() -> bytes`;
    un-applies scale/offset internally. Older releases were decode-only, so
    the version floor matters.
  - License: "FIT Protocol License" (Garmin); PyPI license field empty.
- **Implications**: Decode wrapper mirrors the reference flags but keeps
  string conversion and sub-field expansion on; pin
  `garmin-fit-sdk>=21.208.0` so the Encoder is available for fixtures.

### FIT set/exercise_title semantics (strength)
- **Context**: The reference app never parsed `set_mesgs`; we add it, and
  the user records with standard watch files (no custom workout profiles).
- **Sources Consulted**: SDK profile.py (mesg 225 `set`, mesg 264
  `exercise_title`, per-category `*_exercise_name` type tables), Garmin
  FIT SDK forum thread on encoding strength activities.
- **Findings**:
  - `set.weight` decodes to kg (scale 16) with scale/offset applied;
    `set.duration` to seconds (scale 1000); `set.set_type` to
    'active'/'rest' strings.
  - `category` is an array of strings (e.g. 'bench_press');
    `category_subtype` stays a raw int array — the exercise name requires a
    manual lookup in `Profile['types'][f'{category}_exercise_name']`
    (51 per-category enums).
  - `exercise_title`/`workout_step` linkage (`wkt_step_index`) exists only
    for structured workouts; free recordings are expected to carry sets with
    category/subtype only (inferred — no authoritative statement found).
- **Implications**: The set extractor resolves names via the Profile lookup
  as the primary path and treats `exercise_title` as an optional refinement;
  every set field is `None` when absent (hard project rule).

### Fixture strategy (no personal data in repo)
- **Context**: Golden tests need `.fit` inputs, but personal data can never
  live in the repo, and Garmin's sample `.fit` files sit in a repo with no
  LICENSE file (redistribution rights unclear; no strength samples anyway).
- **Sources Consulted**: PyPI `fit-tool` 0.9.15 (community fork, Beta,
  BSD-3), github.com/garmin/fit-python-sdk `tests/fits/` listing.
- **Findings**: The official SDK Encoder can write every profile message we
  need (record/session/lap/set/device_info/exercise_title); `fit-tool` is a
  beta community fork of a package its original author deleted from PyPI.
- **Implications**: Build synthetic fixtures with the SDK's own Encoder in a
  test-support builder; no extra dependency, encode→decode round-trips
  through the library under test.

### Sport / sub-sport / device vocabulary
- **Context**: Sport detection is deliberately isolated (device-quirk churn).
- **Sources Consulted**: SDK profile.py type tables.
- **Findings**: sport strings include 'generic', 'running', 'cycling',
  'fitness_equipment', 'swimming', 'training', 'walking', 'rowing',
  'hiking'; sub_sport 'strength_training' (20) plus indoor variants
  'treadmill', 'spin', 'indoor_cycling', 'indoor_rowing', 'indoor_walking',
  'indoor_running', 'virtual_activity', 'lap_swimming', 'elliptical',
  'stair_climbing', 'cardio_training'. `device_info.battery_status` decodes
  to 'new'/'good'/'ok'/'low'/'critical'/'charging'/'unknown'.
- **Implications**: The sport map and indoor set in `sport.py` use these
  exact strings; unknown values fall back to Workout/other without failing.

## Architecture Pattern Evaluation

| Option | Description | Strengths | Risks / Limitations | Notes |
|--------|-------------|-----------|---------------------|-------|
| Layered pipeline (chosen) | `model` (pure dataclasses) ← `ingest` (FIT → model) ← `metrics` (pure functions over model) | Matches steering dependency direction (`metrics → ingest → model`); downstream specs consume only `model` + metric results; parsing quirks contained in `ingest` | Requires discipline that `metrics` never imports `ingest` | Direct fit with brief's boundary candidates |
| Single flat module | One module doing decode + metrics | Fewer files | Parsing concerns leak into metric code; sport-quirk churn touches everything | Rejected |
| Hexagonal with parser port | Abstract `FitParser` interface with SDK adapter | Swappable parser | Speculative — only one parser exists or is planned; `.gpx`/`.tcx` are explicitly out of scope | Rejected (simplification lens) |

## Design Decisions

### Decision: Synthetic fixtures via the SDK Encoder
- **Context**: Golden tests need `.fit` inputs; personal data is banned from
  the repo; Garmin sample files have unclear redistribution rights.
- **Alternatives Considered**:
  1. `fit-tool` community fork — beta, fork of a deleted package.
  2. Redistribute Garmin sample `.fit` files — no LICENSE, no strength data.
  3. Commit personal `.fit` files — violates the hard data-root rule.
- **Selected Approach**: A test-support builder constructs deterministic
  synthetic activities (run, ride, strength, degenerate/corrupt cases) with
  `garmin_fit_sdk.Encoder` at test-session time; golden JSON snapshots of
  the resulting model/metrics are committed instead of binaries.
- **Rationale**: Zero new dependencies; guaranteed no personal data; the
  round trip exercises the same profile tables the decoder uses.
- **Trade-offs**: Encoder is recent and less battle-tested; encode→decode
  through one library can't catch SDK-internal decode bugs (acceptable — we
  own extraction logic, not the SDK).
- **Follow-up**: Verify Encoder output passes `check_integrity()` during
  implementation; if an encoding gap appears, fall back to committing the
  generated binaries (still synthetic).

### Decision: Decode errors ride on the Activity (no wrapper type)
- **Context**: Requirement 1.4 — return the model together with collected
  message-level decode errors.
- **Alternatives Considered**: 1. `ParseResult(activity, errors)` wrapper.
  2. `decode_errors` inside the Activity's provenance block.
- **Selected Approach**: Provenance carries `decode_errors: tuple[str, ...]`
  alongside source path and content hash.
- **Rationale**: One return object; decode errors are parse provenance, and
  downstream renderers may want to surface them next to the source link.
- **Trade-offs**: Model carries operation metadata; contained to Provenance.

### Decision: Timestamps converted manually from the FIT epoch
- **Context**: SDK can return datetimes, but the reference app decodes raw
  ints (`convert_datetimes_to_dates=False`) and converts explicitly.
- **Selected Approach**: Follow the reference: decode raw seconds, convert
  once at ingest to timezone-aware UTC datetimes anchored at the FIT epoch
  (1989-12-31T00:00:00Z); per-sample time is stored as float offsets from
  activity start, with absolute record timestamps used internally for lap
  projection only.
- **Rationale**: Deterministic, explicit, keeps the model lean (offsets +
  one anchor), and matches requirement 2.4.
- **Trade-offs**: One manual conversion to maintain; trivially tested.

### Decision: Generic zone math, no embedded zone definitions
- **Context**: Requirements 10.1–10.5 — time-in-zone for HR/power/pace with
  caller-supplied boundaries; zone definitions belong to training-load.
- **Selected Approach**: One `ZoneSpec` (ascending numeric dividers → n+1
  bands) and a single `time_in_zone(values, time_s, spec)` function reused
  for all three channels; inter-sample duration attributed to the earlier
  sample's zone; `None`-valued samples excluded entirely.
- **Rationale**: Generalization lens — three requirements are one problem;
  numeric bands keep pace semantics (lower s/km = faster) the caller's
  concern.
- **Trade-offs**: Callers map band indices to athletic zone labels
  themselves — intentional, since labels are a zone-definition concern.

### Decision: Pin the formulas the reference leaves undocumented
- **Context**: NP/IF/TSS/TRIMP and the moving-time/elevation heuristics are
  documented verbatim in `docs/reference/fitdocs-ai-reference.md` §2, but
  EF and decoupling were imported from Intervals.icu without formulas.
- **Selected Approach**: EF = output ÷ avg HR, where output is normalized
  power (bike) or avg speed in m/min (run); decoupling % =
  `(EF_first_half − EF_second_half) / EF_first_half × 100`, halves split at
  the elapsed-time midpoint, each half requiring at least one sample with
  both output and HR present. NP requires ≥ 30 s of power data, else `None`.
  Power TSS uses moving time as its duration term.
- **Rationale**: These are the standard TrainingPeaks-style definitions and
  the closest interpretation of "fitdocs.ai parity" for imported metrics.
- **Trade-offs**: Values may differ slightly from Intervals.icu's internal
  variants (e.g. GAP-based run EF is deferred with GAP itself).
- **Follow-up**: Revisit when grade-adjusted pace lands in a later spec.

### Decision: stdlib frozen dataclasses for the model (steering-pinned)
- **Context**: tech.md mandates stdlib dataclasses, `mypy --strict`.
- **Selected Approach**: All model types are `@dataclass(frozen=True)` with
  tuples for sequences; `SCHEMA_VERSION` string constant stamped on every
  Activity.
- **Rationale**: Immutability supports the purity/determinism requirement
  (13.2, 13.3) and keeps the dependency footprint at zero.

## Risks & Mitigations
- SDK Encoder is new/less proven — verify integrity of encoded fixtures
  early (first foundation task); fall back to committing synthetic binaries.
- Device quirk churn in sport/sub-sport values — isolated in `sport.py` by
  design; unknown values degrade to Workout/other, never fail.
- `exercise_title` absent on free strength recordings (inferred, not
  authoritative) — set extractor never requires it; Profile category lookup
  is the primary naming path.
- Formula drift vs. fitdocs.ai for EF/decoupling — pinned definitions are
  documented in design.md and validated with hand-computed unit tests.

## Real-Data Verification (HealthFit Exports)
- **Context**: Post-approval verification of the approved spec against the
  user's real `.fit` files — HealthFit exports from Apple Watch, several
  runs paired with a Stryd pod. Shapes and field names only are recorded
  here; no personal values (identifiers, coordinates, dates, serial
  numbers) enter the spec, per the hard data-root rule.
- **Method**: 16 files decoded with `garmin-fit-sdk` 21.208.0 using the
  design's decode flags; 16/16 decoded successfully with zero decoder
  errors.
- **Findings**:
  - **Developer fields (spec gap found)**: newer exports carry
    `developer_data_id_mesgs` plus `field_description_mesgs` describing
    session-scoped developer fields: `SESSION UUID` (16-byte uint8 array),
    `SESSION INDOOR`, `SESSION ACTIVITY TYPE`, `SESSION WEATHER HUMIDITY`,
    `WORKOUT RPE ESTIMATED`, and — on Stryd-paired files — `AVG METs`. The
    UUID is a stable per-activity identity useful for workout-docs
    regeneration; RPE may feed future load work.
  - Strength files carry **no `set_mesgs`** — their record streams are
    heart rate plus timestamp only; the empty-collection path (Req 6.4) is
    the normal case for this device, and strength docs will lean on HR data.
  - Running power is present in the record streams from both Apple Watch
    (native) and Stryd-paired files.
  - Session messages carry **no normalized power, TSS, or IF** — local
    derivation (Req 8.4–8.5, 11.2) is mandatory, not a fallback.
  - Heart-rate record coverage can drop to 62–72% on some files — the
    `None`-hole channel convention (Req 3.2) is exercised by real data.
  - One outdoor run lacks GPS entirely (no position or altitude channels) —
    absent-channel `None` propagation (Req 12.2) occurs in practice.
  - `manufacturer` decodes as `development` with `product_name` strings
    like `Watch7,5` — manufacturer strings are not a reliable device
    identity for these exports.
- **Implications**: Added Requirement 14 — generic exposure of
  session-scoped developer fields as a name-to-raw-value mapping, empty
  when absent, with no interpretation or derivation in fit-ingest
  (SummaryExtractor + `Activity.developer_fields`, task 3.6). No other
  contract changes were needed: the approved model and metric set already
  cover every observed message shape.

## Amendment 1 (2026-07-26): primary sourcing for the metrics constants

- **Discovery Scope**: Extension (light discovery). The feature is implemented
  and its 20 execution units stand; the amendment adds a provenance layer
  beneath the metric modules and revises the notes that named
  `docs/reference/fitdocs-ai-reference.md` §2 as a source. Discovery was
  codebase-focused: the constants' actual sites, the existing citation
  vocabulary one layer up, the document-version machinery, and the live
  consumers of every signature this amendment changes.
- **Deliberately not researched**: the constants' values. See Decision D4.

### Measured surface (verified in-tree at `c7eaa2e`)

| Constant | Site | Shape today |
|---|---|---|
| `_TRIMP_COEFFICIENT` `0.64` | `metrics/stress.py:55` | named `Final[float]`, docstring cites "reference section 2" |
| `_TRIMP_EXPONENT` `1.92` | `metrics/stress.py:58` | named `Final[float]` |
| `_TSS_SCALE` `100.0` | `metrics/stress.py:61` | named `Final[float]` |
| `_NP_MIN_SPAN_S` `30.0` | `metrics/power.py:55` | named `Final[float]` |
| `_NP_ROLLING_WINDOW_S` `30` | `metrics/power.py:58` | named `Final[int]` |
| NP averaging exponent | `metrics/power.py:126-127` | **not a constant** — inline `value**4` and `**0.25` |
| moving-time threshold `0.5` | `metrics/aggregates.py:103` | **not a constant** — bare literal inside `_derive_moving_time_s` |
| `_ALTITUDE_SMOOTHING_WINDOW` `10` | `metrics/aggregates.py:238` | named `Final[int]`, docstring quotes the reference doc |

Two of the eight are not named constants at all, which is why Req 15.6's list
and the design's File Structure Plan both treat "make it a named, cited
constant" as part of the work rather than as a precondition.

Exempt under 15.7 and left where they are: `_SECONDS_PER_MINUTE` (60.0),
`_SECONDS_PER_HOUR` (3600.0), the metres-per-kilometre 1000 in the pace and
pace-zone conversions, and the `0.0`/`1.0` clamp bounds — unit conversions and
arithmetic identities carrying no methodological choice.

### Existing citation vocabulary (the reuse question)

- `src/fitdocs/load/channels/sources.py` already defines `VerificationStatus`
  (three members, including `FITDOCS_MEASURED`, defined ahead of its only
  consumer), `Citation` and `Divergence`, with six records and three
  divergences, guarded by ten tests in `tests/load/channels/test_sources.py`.
- It sits **one layer above** `metrics` in the dependency order
  (`load → metrics → ingest → model`), so fit-ingest cannot import it. This is
  the open question the queue item
  `2026-07-26-citation-vocabulary-diverges-across-layers.md` explicitly hands
  to this design phase.
- `src/fitdocs/load/channels/__init__.py` is a 16-line docstring: the channel
  arithmetic is not written yet, and **nothing under `src/fitdocs/load/`
  imports `fitdocs.metrics.stress`**. `load-channels` Req 8.6 ("consume the
  training-impulse coefficients from the single place they are already
  defined") therefore has no implementation yet, so this amendment lands
  *before* the consumer exists rather than breaking one.

### Document-version machinery (Req 18)

- `fitdocs.contract.DOC_VERSION` is `3`, an `int`, with a docstring recording
  each prior bump and the rule that raising it "must land in the same change
  that regenerates every committed golden document."
- `audit.py:213` already classifies a document below `DOC_VERSION` as stale;
  `sync.py:1183` already refuses to downgrade one above it and rewrites a
  below-version document from its source. **Req 18.2 and 18.3 need no new
  code** — they are existing behavior that a changed constant activates.

### Design Decisions (Amendment 1)

#### D1: A constant is a record, not a number

- **Context**: Req 16.1–16.3 — the citation must be machine-readable, and an
  uncited constant must fail a check.
- **Alternatives**: (1) leave the constants where they are and add a
  name-keyed registry mapping constant name → record; (2) a docstring
  convention, as `load-channels` uses today.
- **Selected**: `CitedConstant` binds value and source in one frozen object,
  defined in `metrics/sources.py`; metric modules read `.value`.
- **Rationale**: (1) binds by string and can drift silently — the exact
  failure mode Req 16 exists to prevent; (2) is what Req 16.1 explicitly
  rejects ("rather than as prose in a docstring"). With `CitedConstant`, a
  covered constant without a citation is unrepresentable rather than
  discouraged, and 16.2's "exactly one record" becomes the type, not a rule.
- **Trade-off**: the number no longer sits beside the formula that uses it.
  Mitigated by each metric module's docstring naming the record it reads.

#### D2: One vocabulary, owned at the bottom of the graph

- **Context**: Req 16.1 needs the record types; they exist one layer *above*
  fit-ingest and cannot be imported from here.
- **Alternatives**: (1) define a second, identical `VerificationStatus` and
  `Citation` in `metrics/sources.py`; (2) move both to a dependency-free
  `fitdocs.citation` and have `load.channels.sources` re-export them;
  (3) leave `load-channels` alone and give fit-ingest a different vocabulary
  shape.
- **Selected**: (2).
- **Rationale**: (1) puts two definitions of "verification status" in one
  codebase — precisely the ambiguity the record exists to remove, and already
  named as a live divergence by the queue item. (3) is worse: Amendment 1's own
  revision text says the fitdocs-chosen category "reuses the semantics of
  `VerificationStatus.FITDOCS_MEASURED` … rather than inventing a fourth
  vocabulary". (2) keeps exactly one shape while touching no record, no status,
  no note and no `load-channels` obligation.
- **Boundary check**: the amendment's out-of-scope clause is about
  `load-channels`' *constants*. Re-pointing where two type definitions live
  changes none of them, and `tests/load/channels/test_sources.py` passing
  **unmodified** is the design's evidence for that claim.
- **Explicitly not decided here**: whether `load-channels` adopts Req 15.4's
  ban on `SECONDARY_ATTESTATION`. The queue item says not to settle that
  silently; the shared vocabulary keeps the member and each layer's guard
  states its own policy over it.

#### D3: A sealed union, not a widened `Citation`

- **Context**: Req 16.7 — a fitdocs-chosen record carries justification and
  search basis "in place of the authors, year, work and locator a published
  source supplies".
- **Alternatives**: (1) make `Citation.authors/year/work` optional and add
  optional justification fields; (2) `SourceRecord = Citation | FitdocsChoice`.
- **Selected**: (2).
- **Rationale**: (1) permits a record that is neither — no authors *and* no
  justification — and leaves 16.4 ("never record the former where only the
  latter holds") to a runtime check. Under (2), `FitdocsChoice` has no
  `verification` field that can be set to `PRIMARY_TEXT`, so the conflation
  16.4 forbids is unrepresentable, and 15.9's `search_basis` is a required
  field rather than a convention.
- **Trade-off**: consumers pattern-match on the union — which is exactly the
  distinction 16.6's consumers want to display.

#### D4: The values are not sourced at design time

- **Context**: this design phase could have web-searched the constants to
  de-risk Req 15.4's block before committing to it.
- **Selected**: it did not; the sourcing gate is the first implementation task
  instead.
- **Rationale**: establishing a constant's value from search results is the
  secondary-summary path Req 15.4 forbids, and the amendment exists because
  that path was taken once already and "that exact coefficient string was
  refuted 0-3 in adversarial verification". A partly pre-sourced design would
  also blur the record the amendment is trying to make legible: which values
  were actually read from a text. Feasibility is therefore expressed as a gate
  with a defined block rather than resolved in advance.
- **Trade-off**: the schedule risk on Banister (1991) and Morton (1990) is
  carried into implementation rather than retired here. Bounded by making
  sourcing the first task, so a block surfaces before dependent work exists.
- **Outcome (2026-07-27), recorded rather than rewritten**: the risk this
  decision carried has been retired, and *not* by the path it was protecting
  against. The maintainer supplied both texts and both were read directly
  (`docs/reference/banister-trimp-primary-sources.md`), and the Coggan 2003
  manuscript was fetched and read end to end rather than summarized from search
  results. So the rationale above still holds — no constant in this amendment
  rests on a search result — while its conclusion is moot: the values *are*
  known at design time now, and the design's classification table states them
  as resolved. This entry is kept rather than deleted so a later reader can see
  which distinction was being protected, and does not mistake "the design now
  names the values" for "the design sourced them from search".

#### D5: `TrimpResult`, so the value never travels without its pair

- **Context**: Req 17.6 — the applied weighting must be reported alongside
  TRIMP.
- **Alternatives**: (1) the facade sets `DerivedMetrics.trimp_weighting` from
  the selection it resolved; (2) `stress.trimp` returns
  `TrimpResult(value, weighting)`.
- **Selected**: (2).
- **Rationale**: under (1) two places decide, and the invariant "weighting is
  non-`None` exactly when TRIMP is" is maintained by agreement between them —
  it drifts the moment either changes. Under (2) no code path produces a value
  without its selection.
- **Trade-off**: `stress.trimp`'s signature changes. Verified safe: its only
  caller is `metrics/__init__.py:119`, and no `load/` module imports it yet.

#### D6: One governing source plus typed corroborators (15.2 vs 16.2)

_Added 2026-07-27 at the design gate, from `/kiro-validate-design`._

- **Context**: Req 15.2 requires a training-impulse weighting term to record
  Banister (1991) *and* Morton (1990) "together with the locator within each
  work at which the value appears." Req 16.2 requires exactly one record per
  constant. The first draft resolved this silently in favour of 16.2 —
  `CitedConstant.source` was single-valued with the stated invariant that "a
  constant with two sources cannot be constructed" — which left 15.2 traceable
  only to two module-level names that nothing bound to a constant, and no guard.
- **Alternatives**: (1) one `Citation` plus a prose `note` naming the second work
  and its locator; (2) `sources: tuple[SourceRecord, ...]`, dropping 16.2's
  cardinality; (3) one governing `source` plus
  `corroborators: tuple[Corroboration, ...]`.
- **Selected**: (3).
- **Rationale**: (1) fails 16.1's machine-readable bar for the second work's
  locator, and putting citation back into prose is the specific thing Amendment 1
  exists to stop — the `BANISTER_TRIMP` record in `load/channels/sources.py`, a
  55-line record of which ~45 lines are `note`, is the worked example of where
  that ends. (2) satisfies 15.2 but discards the useful invariant that exactly
  one work *fixes* the value, and would make "which text governs?" a matter of
  tuple order. (3) keeps both criteria: `source` is the work whose text fixes the
  value (16.2), `corroborators` carry further works with their own locators
  (15.2), and `Agreement` records whether each `AGREES` / `OMITS` / `DIFFERS` —
  which is what makes the guard possible and what the evidence actually requires
  here, since B91 and M90 agree on the exponent and disagree on the coefficient.
- **Trade-off**: one more type and one more enum in the shared vocabulary, which
  `load-channels` inherits without using. Judged cheap next to the alternative of
  a requirement satisfied only by prose. The maintainer's stated position was
  that `PRIMARY_TEXT` plus a note would have been acceptable; (3) was taken
  because it is what turns 15.2 into a test.
- **Explicitly out of scope**: `Corroboration` expresses "another work speaks to
  this value", not "one field of this citation is attested differently from the
  rest". The latter is the live `Citation.year` case (B91's copyright page carries
  no year; `1991` is catalogue-sourced) and is a `VerificationStatus` question
  owned by `.kiro/queue/2026-07-27-banister-morton-primary-texts-obtained.md`.

#### D7: Conform to the cited NP window start rather than record a departure

_Added 2026-07-27 at the design gate; maintainer ruling._

- **Context**: `power.py:87-101` averages a *partial* trailing window over the
  first 29 points (`count = min(i + 1, window)`), while Coggan's step 1 — the
  text this amendment cites for the window width — specifies a 30-second rolling
  average. The sourcing pass surfaced the divergence; Req 16.5 offers a
  `Departure` as the way to keep behavior and record the difference.
- **Alternatives**: (1) keep partial windows, record a `Departure`; (2) conform:
  emit only complete windows; (3) leave it out of Amendment 1 entirely and keep
  it queued.
- **Selected**: (2), ruled by the maintainer 2026-07-27.
- **Rationale**: a `Departure` records a difference fitdocs has a *reason* to
  keep. This one has none — the partial-window behavior was an implementation
  convenience of the first pass, never sourced from any text, so recording it
  would dress an accident as a decision. Conforming also keeps the citation
  honest: it would be odd to cite step 1 for the window width while contradicting
  step 1 about the window.
- **Trade-off**: this is the only value-moving change in the amendment. NP
  moves, carrying IF, VI, TSS and bike EF with it, in whichever direction the
  dropped partial-window averages sit relative to the retained series — not a
  uniform rise: it rises for the common warm-up shape and falls for an
  activity that opens at or above its own overall intensity, both observed on
  real files (task 13.4: 53 rose, 1 fell). `tests/metrics/test_power.py`
  asserts the rise directly
  (`test_normalized_power_complete_window_raises_np_over_partial_window`); the
  fall is documented and its complete-window value exactly pinned by
  `test_normalized_power_exact_value_pins_fourth_power_exponent`, whose
  comment records the partial-window value it replaces
  (261.09384206589294 W, higher than the pinned 244.03877169307256 W) without
  asserting that comparison directly. Either way Req 18's machinery becomes
  live and every committed document goes stale until regenerated. Accepted
  deliberately: the alternative is reporting a number that disagrees with its
  own citation.
- **Consequence for the design**: the MigrationGate's bump condition can no
  longer be `previous_value`-only, since a value moves here with every
  `previous_value` still `None`. Two independent triggers; see MigrationGate.
- **Requirements note**: Req 8.4 mandates "a trailing rolling mean" and is silent
  on the start condition, so this refines an underspecified criterion rather than
  contradicting one — no requirements amendment is strictly owed. That the
  behavior had no acceptance criterion of its own was tracked at
  `.kiro/queue/2026-07-28-np-window-start-has-no-criterion.md`; it is now
  criterion 8.9 (revision 2026-07-30), and that item is closed at
  `.kiro/queue/closed/2026-07-28-np-window-start-has-no-criterion.md`.

### Synthesis outcomes

- **Generalization**: Req 15 (provenance) and Req 16 (the record) are one
  problem — a value that carries its own source — and collapse into
  `CitedConstant`. The 15.1 and 15.8 classifications are two shapes of one
  answer and collapse into `SourceRecord`.
- **Build vs. adopt**: adopt `VerificationStatus` and `Citation` verbatim from
  the shipped, tested `load-channels` module rather than authoring new shapes
  (the amendment asks for exactly this). Build only what has no existing
  shape: `FitdocsChoice` (16.7), `Departure` (`load-channels`' `Divergence` is
  interop-specific — the wrong axis), and `CitedConstant` (the binding).
- **Simplification**: no auto-registration, no plugin surface for records, no
  runtime provenance framework. `CONSTANT_SOURCES` is a hand-written tuple and
  a test proves it complete. Only the constants Req 15.6 names move into
  records; unit conversions stay where they are under 15.7. The weighting
  selection is a `StrEnum` plus one resolver function — no strategy objects.

### Risks & Mitigations (Amendment 1)

- **An unobtainable primary text blocks the feature (15.4)** — accepted
  knowingly in the requirements. Mitigation: sourcing is the first task; a
  block is reported, not routed around; `SECONDARY_ATTESTATION` is
  unrepresentable in this layer's records by guard, so the fallback cannot be
  taken by accident.
- **The guard's exemption list is the new weak point** — an over-broad entry
  silently re-opens the hole 16.3 closes. Mitigation: every entry names its
  literal, its site and its 15.7 reason; the list is asserted to contain no
  unused entries; and the guard's discriminating power is demonstrated by a
  literal inserted and an exemption removed, per `tech.md` §Testing.
- **The `load.channels.sources` edit is cross-spec** — a reviewer may read it
  as a boundary violation. Mitigation: the edit is import-only, its
  behavior-preservation is evidenced by `tests/load/channels/test_sources.py`
  passing unmodified, and the rationale is stated in the design's Out of
  Boundary section rather than left implicit.
- **The classification table may be wrong** — the design expects five
  constants under 15.1 and three under 15.8, taken from Amendment 1's own
  revision table. Mitigation: a correction is a record edit, not a redesign;
  the `SourceRecord` union expresses either outcome without structural change.
- **Golden churn masks a real change** — every snapshot moves because
  `DerivedMetrics` gains a field, which could hide a metric value that moved
  too. Mitigation: land the additive field and the re-sourced values as
  separate commits, so the second diff shows only value changes.

## References
- https://pypi.org/project/garmin-fit-sdk/ — version, packaging
- https://github.com/garmin/fit-python-sdk — README, tests/fits listing
- https://pypi.org/project/fit-tool/ — rejected encode alternative
- https://forums.garmin.com/developer/fit-sdk/f/discussion/270009/examples-for-encoding-strength-training-activity-files — set/workout_step/exercise_title linkage
- `docs/reference/fitdocs-ai-reference.md` — pipeline shape; **no longer the
  cited source of any constant this library computes a metric from** (15.5)
- `.kiro/steering/tech.md`, `structure.md` — stack and layering constraints
- `src/fitdocs/load/channels/sources.py` — the existing citation vocabulary
  adopted by Amendment 1 (D2)
- `.kiro/queue/closed/2026-07-26-citation-vocabulary-diverges-across-layers.md`
  — the question this design phase was handed, and what it does and does not
  settle (D2). Closed `done` 2026-07-27: `load-channels` keeps a
  named-exception variant of Req 15.4's bar, ratified by the maintainer
- `docs/reference/banister-trimp-primary-sources.md` — the primary-text
  extraction that retired D4's schedule risk (B91 ch. 9 page scans, M90
  publisher PDF; page and equation numbers, and seven recorded discrepancies
  between the two texts)
- `.kiro/queue/2026-07-27-banister-morton-primary-texts-obtained.md` — owner of
  the two `VerificationStatus` vocabulary questions this work surfaced and D6
  deliberately does not pre-empt
