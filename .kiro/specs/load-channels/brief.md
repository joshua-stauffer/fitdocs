# Brief: load-channels

## Problem

Compute-all/select-one needs something to compute. Three independent,
threshold-anchored load values — Power, HR, Pace — each computed from the
sample streams when there is enough data, and each honestly reporting
insufficiency when there is not.

"When there is not" is the hard part, and it is not hypothetical. Across Josh's
74 real files, HR coverage drops to 60%, 63%, 73%, 74%, 78% and 83% on
otherwise ordinary activities. Without an explicit sufficiency gate, a run with
60% HR coverage silently produces an HRSS computed over the 40% that is
missing — a confident number that is simply wrong. The same applies to a
GPS-less run (one exists, at 0% coverage with full power) and to the 7 of 9
rides carrying no power at all.

There is also a sourcing defect to fix. `metrics/stress.py` implements Banister
TRIMP with the coefficients `0.64 · e^(1.92 · HRr)`, cited to
`docs/reference/fitdocs-ai-reference.md`. That exact formula string was
**refuted 0-3** in adversarial verification — not because the concept is wrong
(Banister is genuinely the HR-*reserve* variant with exponential weighting) but
because the coefficients trace to secondary web sources, not the literature.

## Current State

`fitdocs/metrics/` already ships much of the power channel as generic derived
metrics: `normalized_power` (4th-root of mean 4th-powers over a 30 s trailing
rolling average), `intensity_factor`, `variability_index`, `efficiency_factor`,
`decoupling_pct`, plus `trimp` and `power_tss` in `stress.py`. That module is
fit-ingest-owned and deliberately holds *no* methodology — its docstring states
that load methodology lives downstream.

Missing entirely: HRSS (TRIMP normalized to a 1-hour-at-LTHR reference), any
pace channel, and any notion of data sufficiency. `DerivedMetrics` fields are
`None`-when-absent but there is no coverage threshold anywhere — a single
recorded sample is treated the same as full coverage.

## Desired Outcome

- Three channel functions, pure and I/O-free, each returning either a load
  value with the inputs that produced it, or a typed insufficiency reason:
  - **Power** — Coggan NP → IF → TSS anchored to FTP, 1 h @ FTP = 100.
  - **HR** — Banister TRIMP → HRSS anchored to LTHR, 1 h @ LTHR = 100, with
    coefficients sourced from the primary literature and **cited in code**.
  - **Pace** — grade-adjusted pace anchored to a threshold pace, same scale.
- An explicit, configurable sufficiency gate per channel, expressed in terms
  the data actually varies on (sample coverage of the required stream, and
  minimum duration).
- Every channel verifiable against published worked examples (e.g. the Coggan
  IF example: 210 W NP ÷ 280 W FTP = 0.75), not only against itself.

## Approach

New `fitdocs/load/channels/` module reusing the existing `metrics` primitives
rather than reimplementing them — `normalized_power` is already correct and
already tested. Each channel is a pure function of `(Samples, benchmark,
config)`; nothing reads files, prompts, or touches the registry.

The HR channel's intensity weighting is reached through a **substitutable
component** so that intervals.icu-style build-time power-calibrated regression
can replace the fixed physiological curve later without a rewrite. That
component is *not* stubbed with dead code in v1 — fixed TRIMP/HRSS is simply
the only implementation, which is also the right default for the low-history
athlete that standalone fitdocs assumes.

## Scope

- **In**: the three channel implementations; the sufficiency gate and its
  configuration; primary-literature sourcing and in-code citation of the TRIMP
  coefficients; grade adjustment for the pace channel; worked-example test
  vectors from the published sources.
- **Out**: choosing between channels (threshold-load owns priority and
  fallback); the QA/divergence flags (activity-qa-flags); any running-power
  *model* — Stryd RSS, GOVSS and Skiba are explicitly not implemented, since
  every run in the real data carries recorded watts; build-time HR regression;
  strength-training load.

## Boundary Candidates

- Power channel vs. HR channel vs. Pace channel — three independent units,
  each independently verifiable.
- The sufficiency gate as its own unit, shared by all three.
- Grade adjustment (the fuzzy part of the pace channel) separated from the
  anchoring math (the exact part) — same split the existing spec used for
  the withdrawn methodology's zone determination vs. points math.

## Out of Boundary

- Where benchmarks come from (athlete-benchmarks owns the store).
- Which channel wins (threshold-load owns selection).
- Document rendering of any kind.

## Upstream / Downstream

- **Upstream**: athlete-benchmarks (FTP, LTHR, threshold pace); fit-ingest
  (`Samples`, `metrics.power`, `metrics.stress`).
- **Downstream**: threshold-load (selects among these); activity-qa-flags
  (divergence compares channel outputs).

## Existing Spec Touchpoints

- **Extends**: fit-ingest — the TRIMP coefficient re-sourcing lands in
  `metrics/stress.py`, whose `trimp` is already rendered into shipped
  documents. Changing it changes existing output and must ride wiki-contract's
  migration-by-regen. HRSS must agree with whatever `stress.py` lands on;
  two different TRIMPs in one codebase is the failure to avoid.
- **Adjacent**: training-load — `metrics/` holds generic stress numbers and
  `load/` holds methodology. That separation is stated in `stress.py`'s own
  docstring; anchoring and sufficiency are methodology and belong in `load/`.

## Constraints

- **Deterministic math only.** No LLM anywhere in the numeric path.
- **Cite sources in code.** The refuted-coefficient episode is exactly what
  uncited constants cost; every formula carries its primary reference.
- Absent data is `None` / insufficient, never a fabricated `0`. A channel
  without its stream reports insufficiency; it does not report zero load.
- Match intervals.icu where it has established behavior; record a reason for
  every divergence. One is already known and accepted: intervals.icu does not
  ingest Stryd fields natively, so fitdocs's running Power Load is computed
  from data intervals.icu does not have.
- The 30 s rolling-average window, first-30 s handling and gap handling in
  `normalized_power` are shipped and tested — reuse, do not re-litigate.
