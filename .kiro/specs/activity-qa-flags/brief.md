# Brief: activity-qa-flags

## Problem

A load number computed from bad data looks exactly like a load number computed
from good data. Three failure modes are detectable and currently invisible:

1. **Cadence lock.** A wrist optical (PPG) sensor can report *step cadence* as
   heart rate, so the recorded "HR" tracks cadence almost perfectly in the
   165–185 range. The research rated this the strongest programmatically
   detectable HR artifact (3-0). Any HR-channel load computed over a
   cadence-locked stream is fiction.
2. **Cross-channel divergence.** When power and HR disagree sharply about how
   hard an activity was, something is true and worth knowing — a fitness
   change, a pacing problem, or a bad sensor. intervals.icu documents a case
   where the same workout scored 19 versus 241 across channels with no
   reconciliation at all.
3. **Stale thresholds.** An FTP measured eight months ago still produces a
   confident TSS today. The research kept this flag explicitly and refuted 0-3
   the claim that real-time FTP determination makes it unnecessary.

This spec is where the original design's cross-correction intent actually
lands. The research was clear that Efficiency Factor and aerobic decoupling are
established as **diagnostic signals — never a load-combination step.** So the
divergence becomes a flag on the record, not an adjustment to the number.

## Current State

`fitdocs/metrics/power.py` already ships both halves of the divergence signal:
`efficiency_factor` (NP ÷ average HR) and `decoupling_pct` (first-half EF vs
second-half EF). They are computed and rendered as ordinary derived metrics
today, but nothing interprets them, compares them against a threshold, or
attaches a verdict to the activity.

Nothing detects cadence lock. Nothing knows a benchmark's age — athlete
benchmarks are currently undated, which is what athlete-benchmarks fixes.

## Desired Outcome

- **Cadence-lock detection** via *temporal correlation* of the HR stream
  against the cadence stream — sustained lock-step tracking, not single-point
  value matching. The research is explicit that single-point matching produces
  false positives precisely at high intensity, where cadence naturally
  approaches true HR.
- **Divergence flag** comparing the selected channel against the HR channel,
  using EF and decoupling as the agreement signal, with `<5%` decoupling as the
  published "good" reference point.
- **Staleness flag** surfacing the benchmark age that athlete-benchmarks
  computes, evaluated against the activity's own date rather than today's.
- Flags degrade honestly. ~10 of Josh's runs carry **0% cadence** — those must
  report "not assessed", never "no lock detected", which would claim a check
  that did not happen.
- Flags are attached to the record and rendered so the document stays
  self-contained and rebuildable; they never modify a load value.

## Approach

A flag layer that reads streams and channel outputs and emits typed verdicts —
detected / not-detected / not-assessed, each carrying its basis. Reuse the
shipped `efficiency_factor` and `decoupling_pct` rather than recomputing them.
Cadence-lock detection is a pure function over two aligned streams and is
testable against synthetic locked and unlocked signals plus the real files that
exhibit each.

Thresholds (correlation strength, lock duration, divergence tolerance) are
configuration in `fitdocs.toml` `[load]`, not constants — they are the
tuning surface, and the research is explicit that the false-positive regime is
real.

## Scope

- **In**: cadence-lock detection; cross-channel divergence evaluation;
  staleness surfacing; the typed flag vocabulary including the not-assessed
  state; flag thresholds as configuration; rendering flags into the document.
- **Out**: changing any load value in response to a flag — flags are
  advisory and never adjust the number; chest-strap vs wrist-optical *sensor
  provenance* detection, which the research could not substantiate and which
  remains an open question, not a deliverable; quarantining or rejecting
  activities; HRV or recovery analysis.

## Boundary Candidates

- Cadence-lock detection (stream analysis) vs. divergence evaluation (channel
  comparison) vs. staleness surfacing (benchmark metadata) — three independent
  inputs, three independent tests.
- The flag vocabulary and its rendering, shared by all three.

## Out of Boundary

- Computing loads or channels.
- Deciding what a flagged activity means for training. The LLM layer
  interprets; this layer only reports facts.

## Upstream / Downstream

- **Upstream**: athlete-benchmarks (benchmark dates); load-channels (channel
  values and EF/decoupling); threshold-load (which channel was selected);
  fit-ingest (`Samples`).
- **Downstream**: the LLM interpretation layer; any future analysis that wants
  to exclude low-quality activities from aggregates.

## Existing Spec Touchpoints

- **Extends**: training-load — flags ride in the redefined result contract and
  its payload v2. Since that contract is being rewritten rather than extended
  (pre-production, no compatibility obligation), the flag vocabulary should be
  a first-class part of its shape from the start, not appended later.
- **Adjacent**: wiki-contract — flag rendering lands in the tool-owned region
  and must respect `doc_version` and migration-by-regen; fit-ingest —
  `efficiency_factor` / `decoupling_pct` are its metrics, consumed here, not
  redefined.

## Constraints

- **Never a load combiner.** The research confirmed 3-0 that EF and decoupling
  are diagnostic; using them to adjust a load value would reintroduce the fused
  metric the whole design rejects.
- **Not-assessed is a first-class state**, distinct from a passed check. A
  missing cadence stream must never render as a clean bill of health.
- Deterministic and configurable; identical input and configuration produce an
  identical verdict.
- Detection tuned against real data, where the failure modes actually occur —
  and evaluated for false positives at high intensity specifically.
