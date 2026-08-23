# Brief: threshold-load

> **Amendment 1 (2026-08-23) — the withdrawn calculator no longer exists.**
> This brief was written while a second built-in calculator was registered
> alongside `threshold`. training-load Amendment 2 withdrew that methodology
> and `6386361` deleted its package outright; `src/fitdocs/load/registry.py:15`
> now states that importing `fitdocs.load` "registers no built-in calculator of
> its own (Req 13.2)", and a full-archive run on 2026-08-23 reported training
> load `Unsupported` for all 2478 documents because **zero** calculators are
> registered.
>
> `threshold` is therefore the first and only built-in calculator, not the
> second. Four consequences for anyone implementing this spec:
>
> 1. There is no arbitration contest to win. The registration-order accident
>    described under *Current State* was real when written and was fixed by the
>    training-load contract update; with one calculator it cannot arise at all.
> 2. Nothing is "registered alongside" anything. Registration is this spec's
>    own single `register()` call.
> 3. The `threshold` vs `withdrawn` choice under *Out of Boundary* has no
>    second operand. Engine arbitration still owns calculator selection, and
>    still matters for future plugins — it is simply not exercised today.
> 4. Shipping `threshold` is what makes training load computable at all. Until
>    it lands, every rendered document honestly reports unsupported.
>
> The claims below are left as written, per the retain-the-record convention;
> read them against this note. Corrected under queue item
> `2026-08-04-present-tense-claims-about-removed-material-survive-redaction`.

## Problem

fitdocs needs one training-load number per activity that means the same thing
across running, cycling and hiking, and that stays interoperable with
intervals.icu — the platform actually in use.

The original design proposed fusing an HR load and a power load per activity
via a cross-correction step. The 2026-07-20 research pass killed it: that
synthesis has **no prior art in any product, paper, or open-source
implementation surveyed, intervals.icu included.** Every platform computes
single-channel loads and *selects one* with fallback; users request true
synthesis as a *missing* feature. A bespoke fused number would be
un-interoperable — precisely the opposite of the strategy.

The replacement is not a compromise, it is the better design: computing every
channel and selecting one satisfies the graceful-degradation requirement *by
construction*. Josh's real data shows why it has to be per-activity dynamic
rather than a fixed rule — 7 of 9 rides carry no power, one run has full power
but no GPS, and HR coverage collapses to 60% on some files. Whichever single
channel you hardcode, real activities exist that it cannot score.

## Current State

`training-load` shipped the seam this plugs into: the `LoadCalculator`
Protocol, an id-addressed registry with validation and per-plugin failure
isolation, an athlete profile with a declaration-driven prompt flow, an engine
that walks documents and writes results, and the withdrawn methodology's
implementation. *(Amendment 1: that implementation is deleted.)*

Two things block a multi-channel calculator. `LoadResult` carries exactly one
`points` value with no room for the non-selected channels or their reasons.
And the engine picks the **first non-`Unsupported` calculator in registration
order** — which becomes an accident of import order the moment `threshold` and
`withdrawn` both declare running. Both are fixed by the `training-load` contract
update, which this spec depends on. That update is free to *redefine* the
contract rather than extend it (pre-production, no external plugin authors), so
this spec should be designed against the right shape, not around the old one.

## Desired Outcome

- A registered calculator, id `threshold`, that for each activity computes
  every channel with sufficient data, selects exactly one by **user-configured
  priority with fallback**, and returns the selected value together with the
  non-selected channel values and the insufficiency reasons for channels that
  could not be computed.
- Only the selected value is the activity's load. The rest are diagnostics —
  persisted, clearly marked as not-the-load, never silently averaged in.
- Supported modalities: Run, Ride, Walk, Hike. Strength returns the honest
  `Unsupported` outcome rather than a computable-but-meaningless HRSS.
- Missing benchmarks route through the existing prompt flow via declared
  `AthleteField`s — asked once, persisted, never defaulted.
- When no channel has sufficient data, the outcome is a typed insufficiency,
  not a load of zero.

## Approach

A thin policy layer over `load-channels`: the channels do the math, this spec
decides which one counts. Priority is a configured ordered list per discipline
(running commonly prefers pace, cycling prefers power) — **not hardcoded**; the
research found the fixed `Power > Pace > HR` ordering was only a 1-2 split
vote. Fallback walks the configured order and takes the first channel that
cleared its sufficiency gate.

The withdrawn calculator stays registered and untouched. *(Amendment 1: it does
not — it is deleted, and `threshold` is the only calculator.)* Which calculator
runs is settled by the
configured default plus `--calculator`, per the arbitration decision — not by
this spec.

## Scope

- **In**: the `threshold` calculator; per-discipline priority configuration and
  its validation; the fallback walk; assembling the selected value plus
  diagnostics into the widened result; declared `AthleteField`s for the
  benchmarks it needs; the modality support set; registration alongside the
  withdrawn calculator *(Amendment 1: plain registration; there is no sibling)*.
- **Out**: the channel math itself (load-channels); the result contract, the
  document payload and rendering (the training-load update); the benchmark
  store (athlete-benchmarks); the QA flags (activity-qa-flags); any fusion,
  averaging, blending or cross-correction of channel values — explicitly and
  permanently; weekly/CTL/ATL aggregation.

## Boundary Candidates

- Priority configuration + validation vs. the selection/fallback walk vs.
  result assembly.
- The modality support decision (including the deliberate strength refusal) as
  its own small unit with its own test.

## Out of Boundary

- Choosing between *calculators* (`threshold` vs `withdrawn`) — that is engine
  arbitration, owned by the training-load update.
- Interpreting the number. The LLM layer sits on top and only interprets;
  nothing in this spec explains what a load means.

## Upstream / Downstream

- **Upstream**: athlete-benchmarks; load-channels; the training-load contract
  update (the widened result and the configured-default arbitration).
- **Downstream**: activity-qa-flags (divergence compares the selected channel
  against the HR channel); future cycle/block aggregation specs, which will
  consume the selected value only.

## Existing Spec Touchpoints

- **Extends**: training-load — registers a second built-in calculator into its
  registry and consumes its redefined contract. *(Amendment 1: the paragraph that followed
  said the withdrawn calculator would be adapted to the new result shape rather
  than replaced or deprecated. It was deleted instead, so no adaptation is owed
  by any spec.)*
- **Adjacent**: plugin-api — `threshold` is a built-in, so `fitdocs plugins`
  must report its version as the fitdocs version, and it must pass the same
  `validate_calculator` gate as any third-party plugin. It should not need
  privileges a plugin author lacks; if it does, that is a defect in the public
  surface worth surfacing.

## Constraints

- **No per-activity fusion, ever.** This is the design's load-bearing
  constraint, not a preference. Compute all, select one.
- **Priority is configurable**, never hardcoded.
- Deterministic: identical inputs and identical configuration produce a
  byte-identical result.
- A calculator never fabricates. Absent benchmarks or insufficient data yield
  the typed `MissingInputs` / insufficiency outcomes the shipped contract
  already defines; `Computed` without the required confirmation is forbidden.
- `LoadOutcome` is a closed union folded with `assert_never` — any new variant
  is a static error at every handling site, by design.
