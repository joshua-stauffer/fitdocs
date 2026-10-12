# Research & Design Decisions — hr-derivation

## Summary
- **Feature**: `hr-derivation`
- **Discovery Scope**: Extension (complex integration): a new derivation stage
  inside an existing command, an amendment to benchmark selection, an
  amendment to the derived-write seam, new `check` findings, and a new
  upstream (the wellness series, specified by `wellness-store`, not yet
  implemented).
- **Key Findings**:
  - Benchmark selection is date-only (`benchmarks.py:189-243`). A hand entry's
    back-reach (`applies_from`) only fills dates no earlier-measured entry
    covers, so derived entries dated before it apply on their own dates. The
    maintainer's own profile has exactly this shape: one hand-recorded
    `max_hr_bpm` entry whose back-reach covers the whole workout corpus. The
    first draft proposed a selection amendment; the maintainer chose
    (2026-10-12, second round) to keep selection unchanged for every kind and
    to make "evidence must disagree" a write-time rule, accepting that
    historic heart-rate load before the hand date moves to derived values.
  - The derived write replaces every derived entry
    (`load/profile.py:342-445`), and the tagged-effort stage's change test
    compares against every derived entry (`performance/engine.py:438-446`).
    A second stage would erase the first and make the first rewrite on every
    run. Both the write and the change test must be partitioned by kind.
  - Measured on the maintainer's data (aggregate counts only, nothing
    written to the repository): a 28-day median with a 3 bpm step and a
    14-day confirmation gives 20 resting-HR entries over Garmin's 937 daily
    values; a 30-second sustained peak, a 365-day window, the median of the
    three highest sessions and a 2 bpm step give 19 maximum-HR entries over
    the whole 2017-2026 corpus, and 18 (two takeovers, 14 dated before the
    hand entry's measurement date) with the maintainer's hand-recorded
    maximum under the write-time rule. Parsing and composing every workout costs about
    84 ms per document (216 s for 2,564 documents).

## Research Log

### Benchmark selection and the hand back-reach
- **Context**: the brief's open question on "hand-recorded wins"; the
  maintainer's decision of 2026-10-12 ("evidence must disagree") asked
  requirements to make the back-reach interaction precise.
- **Sources consulted**: `src/fitdocs/benchmarks.py:157-243`,
  `.kiro/specs/athlete-benchmarks/requirements.md` (Amendment 1, 3.10),
  `src/fitdocs/index/derived/benchmarks.py:136-196`,
  `src/fitdocs/load/profile.py:148-169`; a keys-and-dates-only probe of the
  maintainer's `athlete.toml`.
- **Findings**:
  - Tier 1 (latest entry measured on or before the date) always beats tier 2
    (an `applies_from` back-reach) — athlete-benchmarks 3.10.
  - The two callers of `BenchmarkSet.applicable` are
    `AthleteProfile.benchmark` (`load/profile.py:169`) and
    `in_force_periods` (`index/derived/benchmarks.py:162`), verified by grep.
    Every load consumer reaches selection through `AthleteProfile.benchmark`
    (`load/threshold/anchors.py:142-157`).
  - `in_force_periods` samples `applicable` at every `measured_on` and
    `applies_from` breakpoint, so any selection rule that changes only at
    those breakpoints is projected correctly with no code change.
  - Maintainer profile (keys and counts only): `athlete.max_hr_bpm` 1 hand
    entry with `applies_from`; its back-reach span is 2,927 days and starts
    before the first workout document, its measurement date falls 2,823 days
    into a 3,467-day corpus; no `resting_hr_bpm` entry; `run.lthr_bpm` 5
    derived; `run.threshold_pace_s_per_km` 13 derived + 1 hand;
    `run.ftp_watts` 1 and `ride.ftp_watts` 2 hand entries, none with
    `applies_from`.
- **Implications**: with selection unchanged, derived maxima dated
  2017-2025 replace the athlete's declared back-reach value on their own
  dates. The maintainer accepted this (decision 3, 2026-10-12): the run
  reports the change of back-reach once, and the release notes state it.
  The first draft's alternative (a derived entry never applies inside a hand
  back-reach) contradicted training-load Amendment 4 and athlete-benchmarks
  Amendment 1 and was withdrawn.

### The derived-write seam
- **Sources consulted**: `src/fitdocs/load/profile.py:319-445`,
  `src/fitdocs/performance/engine.py:410-455`, grep for
  `with_derived_benchmarks` (callers: `performance/engine.py:445` only, plus
  tests).
- **Findings**: `with_derived_benchmarks` keeps every non-derived entry and
  replaces the whole derived subset; groups that held derived entries and are
  no longer covered are dropped. The tagged-effort stage writes when
  `frozenset(accepted) != previous_derived`, where `previous_derived` is
  every derived entry of every kind.
- **Implications**: a required `kinds` partition on the write, and the
  tagged-effort stage's change test restricted to its own three kinds
  (otherwise a heart-rate entry on file makes it rewrite on every run).

### Resting heart rate: the daily series is noisy
- **Context**: controller note — Garmin's series value is the daily
  `currentDayRestingHeartRate`, not the smoothed 7-day `restingHeartRate`.
- **Sources consulted**: the maintainer's Garmin export `UDSFile_*.json`
  (30 files), read by a scratchpad probe printing counts and spreads only.
- **Findings** (aggregates):
  - 937 days with a value; per year 36/259/233/60/301/47/1 for 2018-2025.
  - Mean absolute day-to-day change 6.51 bpm; mean within-window
    interquartile range over 28 days 8.69 bpm; the 28-day median moves
    0.32 bpm per day on average.
  - Entry counts for the hysteresis walk (first entry immediate):

    | Window / minimum values | Step | Confirmation 1 day | 7 days | 14 days |
    |---|---|---|---|---|
    | 28 / 14, median | 2 | 63 | 38 | 29 |
    | 28 / 14, median | 3 | 45 | 29 | 20 |
    | 28 / 14, median | 4 | 33 | 22 | 16 |
    | 14 / 7, median | 2 | 125 | — | — |
    | 42 / 21, median | 2 | 47 | 34 | 25 |
    | 56 / 28, median | 3 | 28 | 22 | 18 |

    A lower-quartile statistic instead of the median changed counts by
    10-15 % and was not pursued.
- **Implications**: the median alone does not keep the timeline sparse on a
  daily series this noisy; a confirmation run is needed. Chosen: 28-day
  window, at least 14 values, median, 3 bpm step, 14-day confirmation —
  20 entries over 937 daily values (8 of them in 2022, the densest year).
  Apple's sedentary estimate and the intervals.icu relay could not be
  measured (no Apple export in the data root; no network); both are
  expected to be smoother than Garmin's daily value.

### Load sensitivity to the two values
- A 3 bpm change of resting heart rate moves the heart-rate reserve
  fraction at 150 bpm (rest 50, max 190) from 0.714 to 0.710 — under 1 %.
  A 2 bpm change of maximum moves it to 0.704 — about 1.5 %, compounded by
  the exponential weighting. Hence a larger step for the noisier, less
  influential resting value and a smaller one for the maximum.

### Maximum heart rate: sustained peaks over the workout corpus
- **Sources consulted**: every workout document of the maintainer's data
  root, parsed and composed with `fitdocs.parse_fit` and
  `fitdocs.compose.archive.compose_listed` by a scratchpad probe; per-session
  peaks kept in the scratchpad only; counts printed.
- **Findings** (aggregates):
  - 2,564 workout documents; 2,475 with heart rate; 89 without; 0 failed;
    0 sessions with a `locked` cadence-lock verdict under default settings;
    1,675 samples excluded by the 30-230 bpm range and the 10 bpm/s rate
    rule.
  - Sessions with a sustained peak: 2,373 (15 s), 2,371 (30 s), 2,358 (60 s);
    by modality (30 s) run 1,558, strength 286, bike 273, other 252, swim 2.
  - A session's single-sample maximum exceeds its 30-second sustained peak
    by 2.54 bpm on average and by more than 10 bpm in 2.5 % of sessions.
  - Entry counts under the first draft's span rule (no hand entry / with
    the maintainer's hand entry), 365-day window, median of the three
    highest:

    | Peak window | Step 1 | Step 2 | Step 3 |
    |---|---|---|---|
    | 15 s | 34 / 11 | 19 / 5 | 16 / 4 |
    | 30 s | 30 / 11 | 19 / 4 | 12 / 4 |
    | 60 s | 28 / 10 | 16 / 7 | 16 / 4 |

    A 730-day window gave 18 / 5 at 30 s, step 2; the single highest session
    instead of the median of three gave 13 / 4.
  - Recomputed under the write-time rule with selection unchanged (the rule
    adopted), median of three, 365-day window: 15 s step 2 → 18 entries, 2
    takeovers, 13 before the hand date; 30 s step 1/2/3 → 30/18/13 entries,
    2 takeovers each, 19/14/9 before the hand date; 60 s step 2 → 19
    entries, 2 takeovers, 12 before the hand date. One takeover is the first
    derived maximum replacing the hand entry's back-reach value; the other
    falls after the hand entry's measurement date.
  - On 12 evidence days the median-of-three maximum fell below the run
    threshold heart rate in force (no hand entry considered).
  - Runtime: 305 s total, of which parse and compose 216 s (84 ms per
    document); the rest was the probe's quadratic peak search.
- **Implications**: 30-second peaks, 365-day window, median of three, 2 bpm
  step. The single-sample maximum is the spike-prone statistic the sustained
  peak exists to avoid. The heart-rate stage costs minutes on a large
  corpus; a cache of per-session peaks is a follow-up, not part of this
  spec.

### What the activity model records about the heart-rate sensor
- `DeviceInfo` carries manufacturer, product name, serial, software version
  and battery status only (`src/fitdocs/model.py:249-258`); no device type or
  ANT+ device type. A chest-strap preference cannot be implemented without
  a fit-ingest amendment; it is out of scope and recorded as a follow-up.

### Upstream: the wellness series (wellness-store, specified, not landed)
- `fitdocs.wellness.read_series(data_root) -> WellnessSeries`;
  `WellnessSeries.sources(metric)`, `.by_source(metric, source)`;
  `Metric.RESTING_HR_BPM`; `load_wellness_settings(document, *, data_root)`;
  `effective_order(settings, metric)`; `SeriesReadError`;
  `WellnessSettingsError(SettingsError)`; `layout.wellness_series_path(data_root,
  year)` (wellness-store `design.md` § Seams for downstream specs, items 4-6
  and 8). Nothing missing for this feature: no wellness-store amendment.
- The series also carries a `max_hr_bpm` wellness metric (the day's highest
  heart rate, workouts included, from all-day monitoring). It is not used:
  it is a single-sample daily maximum from a monitoring source, the
  spike-prone statistic the sustained peak avoids.

### Citations
- No network access was available to this spec writer. The brief's research
  note (2026-10-12) names two works: Ausland, Kelemen & Seiler (2026) on the
  error of age formulas, and a 2002 field-versus-laboratory peak-heart-rate
  study recommending a median of several maximal efforts. Neither was read
  here, and the second is not identified by author.
- Consequence: every constant is governed by a `FitdocsChoice` record (the
  numbers are fitdocs' own choices, several backed by the measurements
  above), and published works enter only as corroborators whose status the
  implementing task records honestly after reading them, or which it drops.

## Architecture Pattern Evaluation

| Option | Description | Strengths | Risks / Limitations | Notes |
|--------|-------------|-----------|---------------------|-------|
| Stage of `derive-benchmarks` | A second stage after the tagged-effort stage, same command | Keeps performance-benchmarks 1.10 ("only this command derives") true; one place to look | The command gets slower (minutes on a large corpus) | Selected |
| New command | `fitdocs derive-hr` | Fast tagged-effort command unchanged | A second deriving command contradicts 1.10; two commands to remember | Rejected |
| Chained into `sync`/`regen` | Derive on every drain | Always current | Minutes per drain; derived entries churn the profile on every sync; load still needs `--recompute` | Rejected |
| Index-backed peaks | Read per-second streams from the analytics index | Fast | The index is never read to produce a document, a document value or any command output but the analytics commands (analytics-index Req 5.6, `requirements.md:186`) | Forbidden |

## Design Decisions

### Decision: selection unchanged; "evidence must disagree" is a write rule
- **Context**: Requirements 5.2-5.7; maintainer decisions 2026-10-12 (first
  and second round).
- **Alternatives Considered**:
  1. Keep selection date-only and put the rule in what the pass writes.
  2. Inside a back-reach, resolve among hand entries only — would resurrect
     a hand value an earlier takeover superseded.
  3. Where date-only selection picks a derived entry inside a hand span,
     pick the hand entry (the first draft's choice, for every kind).
- **Selected Approach**: 1, by maintainer decision (second round). Option 3
  contradicted training-load Amendment 4 ("which no earlier-measured entry
  covers"), athlete-benchmarks Amendment 1 (an entry measured on or before
  the activity always wins over a retroactive one) and 1.13 (provenance
  never changes selection).
- **Rationale**: one selection rule for every kind; the walk compares each
  evidence day with the value in force by that same rule, so agreeing
  evidence never replaces a hand value and a takeover happens only where
  the evidence disagrees.
- **Trade-offs**: historic load before a hand entry's date moves to derived
  values where evidence exists (accepted); the run reports the narrowed
  back-reach once and the release notes say it.

### Decision: provenance keeps `document` and adds a `series` reference
- **Context**: Requirement 7; a series-derived value has no page.
- **Alternatives Considered**: 1. make `document` optional for derived
  entries — every earlier release would reject the profile; 2. keep
  `document` required, pointing at the series file that holds the entry's
  date, and add an optional `series` key naming source and metric.
- **Selected Approach**: 2. Earlier releases read the entry as a valid
  derived entry (they ignore the unknown key).
- **Trade-offs**: the analytics `source_page` column shows a series file for
  these entries; its description still says "page" (follow-up).

### Decision: partition the derived write by kind
- **Selected Approach**: `with_derived_benchmarks(entries, *, kinds)` with
  `kinds` required; the tagged-effort stage passes its three kinds, the
  heart-rate stage its two; each stage's change test compares only its own
  partition; a test asserts the partitions are disjoint.

### Decision: two writes at most per run, one per stage
- **Alternatives**: one combined write (needs the tagged-effort engine split
  into plan and write halves, and a cross-package orchestrator); one write
  per stage.
- **Selected Approach**: one write per stage, each atomic and only on change.
  performance-benchmarks 1.7 already speaks of its own stage; the ownership
  contract's "at most once per run" sentence becomes "at most once per
  stage". That sentence and the description of what `derive-benchmarks`
  reads are a versioned guarantee (`docs/ownership-contract.md:820-826`,
  published under a bump; `contract.py:331-335`), so `CONTRACT_VERSION` is
  raised to main + 1 (controller ruling R2, reversing the first draft).

### Decision: `[load]` read once per run
- training-load 14.1 and `tests/load/test_settings.py:2478-2483` hold
  `derive-benchmarks` to exactly one `[load]` read. The heart-rate preflight
  reads it and hands the `LoadSettings` to the tagged-effort stage, which no
  longer reads it when given (controller ruling R3).

### Decision: evidence source per day = first source with a formed baseline
- **Context**: Requirement 2.4; maintainer decision "precedence picks".
- **Alternatives**: the series' per-day canonical source (flips whenever one
  source misses a day, so the baseline would switch sources day to day);
  the first source in precedence whose baseline is formed that day.
- **Selected Approach**: the latter. It applies the configured precedence
  through `effective_order`, never splices, and switches source only when a
  source's baseline starts or stops being formed.

### Decision: not recovery's baseline
- recovery owns descriptive per-(metric, source) baselines and normal ranges
  for the recovery page. This feature's resting level is a different
  statistic serving a different consumer: a 28-day median with a minimum
  count, fed into a step-and-confirmation state machine whose output is a
  sparse, hand-aware step function written into `athlete.toml`, with every
  constant chosen for load sensitivity and timeline churn. If recovery's
  baseline were reused, a change made for display would silently move
  training load across the whole history. The two may compute a similar
  median; they stay separate on purpose, and `fitdocs.hr_benchmarks` exposes
  no general baseline function.

## Risks & Mitigations
- **Runtime** — minutes per run on a large corpus; mitigation: a progress
  line on a terminal; per-session peak cache queued as follow-up.
- **Derived maximum below threshold heart rate** — 12 evidence days measured;
  mitigation: the `check` and report inconsistency findings; never clamped.
- **iCloud-evicted archives** — an unreadable archive would silently drop a
  session; mitigation: an unreadable archive is a failure and the maximum-HR
  partition is kept unchanged that run, so materialization state never
  moves the timeline.
- **Upstream not landed** — `fitdocs.wellness` is specified, not built;
  mitigation: implementation order (wellness-store first) and the seams
  quoted above.
- **Unread citations** — mitigation: governing records are fitdocs choices;
  corroborators are read or dropped by a dedicated task.

## References
- `.kiro/specs/wellness-store/design.md` § Seams for downstream specs.
- `.kiro/specs/athlete-benchmarks/requirements.md` (Amendments 1 and 2).
- `.kiro/specs/performance-benchmarks/requirements.md` (Requirements 1, 6, 10)
  and `design.md` § ProfileDerivedWrite.
- `.kiro/specs/activity-qa-flags` — the cadence-lock check
  (`src/fitdocs/load/qa/cadence.py:141-348`).
- `.kiro/queue/2026-08-25-heart-rate-inputs-used-values-unpinned.md`,
  `.kiro/queue/2026-09-12-missing-input-names-a-key-the-profile-visibly-has.md`.
