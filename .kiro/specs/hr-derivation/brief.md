# Brief: hr-derivation

## Problem

HR-based load needs a resting and a maximum heart rate:
- TRIMP uses the reserve `(hr - rest) / (max - rest)`;
- the threshold heart-rate channel needs LTHR, rest and max, mutually
  consistent.

Today both values exist only if the athlete types them in, and nothing keeps
them current. A resting HR typed once in 2023 still scores 2026 workouts.
fitdocs now holds the evidence to derive both:
- every workout's HR stream gives the observed maxima;
- from `wellness-store`, a daily resting-HR series per source.

The maintainer wants the derived values to apply automatically by date
(maintainer, 2026-10-12).

## Current State

- **Dated benchmarks.**
  - `max_hr_bpm` and `resting_hr_bpm` are athlete-scoped benchmark kinds
    (`benchmarks.py:45-52`, `:55`, `:69-72`), in whole bpm (`:74-82`).
  - They are resolved per activity date by `BenchmarkSet.applicable`
    (`benchmarks.py:189-243`). Tier 1 is the latest entry measured on or
    before the date; tier 2 is the earliest entry whose `applies_from`
    reaches back.
  - Resolution is by date only. Source plays no part.
- **Flat keys.** The undated `max_hr_bpm` / `resting_hr_bpm` in
  `athlete.toml` feed TRIMP only (`athlete.py:120-127`,
  `metrics/__init__.py:121-126`, `metrics/stress.py:137-152`). The dated tree
  deliberately does not fall back to them (athlete-benchmarks
  `design.md:241-251`). The confusion this causes is queued:
  `.kiro/queue/2026-09-12-missing-input-names-a-key-the-profile-visibly-has.md`.
- **Consumers.**
  - The threshold HR channel checks `max > rest` and `rest < LTHR <= max`
    (`load/channels/heart_rate.py:178-221`, `:236-244`).
  - HR zones do not read max or rest. They are absolute dividers
    (`metrics/__init__.py:153`).
- **Provenance.**
  - `BenchmarkSourceKind` is closed: `{DERIVED, MEASURED}`
    (`benchmarks.py:85-95`).
  - A derived entry needs `method`, `document`, `inputs` and `citation`
    (`:473-484`). `document` is one page, which the index exposes as
    `source_page` (`index/derived/benchmarks.py:67-70`). A resting HR
    derived from a daily series has no single page.
- **The derived-write seam replaces the whole derived subset.**
  `AthleteProfile.with_derived_benchmarks` (`load/profile.py:342-447`) is
  called only by the performance pass (`performance/engine.py:445`). A
  second derivation pass would therefore erase the performance pass's
  entries. `is_recorded` (`profile.py:319-340`) protects only hand entries
  at the exact same key.
- **Explicit prohibitions to lift:**
  - performance-benchmarks Req 10.4 says that feature "shall derive no
    maximum heart rate and no resting heart rate" (`requirements.md:263`;
    `performance/derive.py:747`);
  - threshold-load Req 11.6 says the calculator "estimate[s] no threshold
    from activity data". It still holds, because derivation happens in a
    pass outside the calculator.
- **Roadmap.** Phase 6's follow-on list carries "Maximum and resting
  heart-rate derivation, if a defensible method exists" (roadmap Phase 6).

## Desired Outcome

- A derivation pass writes dated `max_hr_bpm` and `resting_hr_bpm` entries
  into the benchmark timeline, as derived entries with method, inputs and a
  citation.
- Load and TRIMP pick them up by date like any other entry.
- A hand-recorded value always wins where both could apply (maintainer
  intent, 2026-10-12). Requirements define that rule precisely; see Open
  questions.
- Rerunning the pass on unchanged inputs changes nothing.
- When the derivation moves, historic HR load moves with it. The maintainer
  accepted that churn.

## Approach

**An automatic, dated, derived benchmark source** (maintainer, 2026-10-12),
over suggestions the athlete adopts by hand.

- **Resting HR** comes from the normalized wellness series:
  - a robust baseline per source (a rolling median or low percentile);
  - a new dated entry only when the baseline moves by more than a
    hysteresis step, so the timeline does not churn daily;
  - never across sources with different definitions (see Constraints).
- **Max HR** comes from workout HR, read through ingest and composition
  rather than the index, because the index is never read to produce a
  document value (analytics-index `requirements.md:186`):
  - sustained rolling-mean maxima, not single samples;
  - rejection of implausible rates of change and of cadence-lock stretches
    (the existing QA flag, `load/qa/types.py:41-49`);
  - a preference for chest-strap sessions where the source is known;
  - a median or high percentile of the top sessions in a recency window,
    so the value can fall with age.

  No single published algorithm exists. The design must cite what it uses
  and pin the thresholds (research 2026-10-12: Ausland, Kelemen & Seiler 2026
  on formula error; the 2002 field-vs-lab peak-HR study recommending a median
  of several maximal efforts).

## Scope

- **In**:
  - the derivation pass and its command placement: a new command, or a stage
    of `derive-benchmarks`; the design decides;
  - the athlete-benchmarks amendment:
    - provenance for a series-derived entry (`document` relaxed, or a
      series reference);
    - the hand-wins rule;
  - the performance-benchmarks amendment:
    - lift Req 10.4;
    - partition `with_derived_benchmarks` by kind or method, so the two
      passes never erase each other;
  - the threshold-load and training-load consumers:
    - unchanged code paths;
    - the `inputs_used` provenance must show derived values. See
      `.kiro/queue/2026-08-25-heart-rate-inputs-used-values-unpinned.md`,
      which is worth closing here;
  - `check` findings for a derived pair that breaks `max > rest` or
    `rest < LTHR <= max`;
  - the benchmark timeline in the index, which picks up the new entries
    through its existing producer;
  - docs and skill wording.
- **Out**:
  - HRV-derived thresholds;
  - LTHR or FTP derivation, already owned by performance-benchmarks;
  - age-formula maxima (220 - age and similar) as values;
  - changing HR zones, which are absolute dividers today;
  - the flat undated keys. Their confusion stays a separate queue item
    unless the design finds a cheap reconciliation.

## Boundary Candidates

- Resting-HR derivation from the series: pure, and depends only on
  `wellness-store`.
- Max-HR derivation from workout records: pure over composed activities.
- The benchmark write seam (partitioned derived subsets) and the provenance
  amendment.

## Out of Boundary

- The wellness series itself (`wellness-store`).
- Any recovery visualisation (`recovery`, `workout-wellness`).
- The load calculators' internals.

## Upstream / Downstream

- **Upstream**:
  - `wellness-store` (the resting-HR series);
  - `athlete-benchmarks` (the timeline, `applicable`, provenance);
  - `performance-benchmarks` (the derived-write seam, the pass precedent);
  - `channel-merge` / `activity-identity` (composed HR streams);
  - `activity-qa-flags` (cadence lock).
- **Downstream**:
  - `threshold-load` and `load-channels` (HR channel), TRIMP;
  - `analytics-derived` (benchmark timeline);
  - `recovery` (it may plot the derived values).

## Existing Spec Touchpoints

- **Extends**:
  - `athlete-benchmarks`: an amendment for series provenance and the
    hand-wins rule;
  - `performance-benchmarks`: an amendment lifting Req 10.4 and partitioning
    the derived write.
- **Adjacent**:
  - `threshold-load` (Req 11.6 still holds);
  - `load-channels` (the consistency rules);
  - `analytics-derived` (the benchmark timeline projection).

## Open questions for requirements

- **"Hand-recorded wins" needs a precise rule**, because resolution is by
  date only. Candidates:
  - a hand entry masks derived entries of its kind from its `measured_on`
    until the next hand entry;
  - derived entries are emitted only where no hand entry exists within a
    window;
  - something else the maintainer prefers.

  Ask at requirements approval.
- Whether a resting HR from a source whose definition differs (Garmin's
  lowest 30-minute average vs Apple's sedentary estimate) may start a new
  derived segment, or whether each source's baseline stays separate and the
  precedence order chooses.

## Constraints

- **Absent data is `None`, never 0.** With no qualifying evidence there is no
  entry. A derived value never fills a gap with a default.
- **Determinism.**
  - The same archive, series and profile always produce the same entries.
  - No clock reads, except an explicit "as of" date if the design needs one.
- **Resting-HR definitions differ by platform**, so baselines are kept per
  source (research 2026-10-12):
  - Garmin: the lowest 30-minute average;
  - Apple: estimated from sedentary samples and revised during the day;
  - Oura and Suunto: the lowest HR in sleep;
  - Polar: none (intervals.icu substitutes average sleeping HR).
- **Churn.** Every new derived entry can rescore every later HR-loaded
  workout. Hysteresis and a minimum spacing keep the timeline sparse, and the
  design states the expected entry count on the maintainer's data.
