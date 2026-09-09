# Brief: performance-model-fit

## Problem

`load-history` draws fitness and fatigue with **seed** constants. The primary
texts are explicit that those seeds are not findings: Banister (1991) offers
45 d / 15 d as "on average" starting values, and Morton, Fitz-Clarke &
Banister (1990) Table 2 reports the *fitted* values for two runners as τ₁ =
50 / 40 d, τ₂ = 11 d for both, k₂ = 1.8 / 2.0
(`docs/reference/banister-trimp-primary-sources.md` §3, D5). The model's
entire claim to describe *this* athlete rests on fitting its four constants to
that athlete's own measured performances — which is what the races are.

The athlete asked for exactly this: use races to calculate historical fitness.
The two-step decision at discovery (2026-09-09) put the seeded curve first so
value lands before the fit's data-sufficiency question is settled, and made
the fit its own spec so it can refuse honestly when the archive cannot support
it.

## Current State

- After `effort-tags`, tagged races carry an official distance and time, or
  fall back to the recorded ones. After `performance-benchmarks`, a cited
  race-equivalence model (Riegel's power law — secondary attestation until the
  1981 text is read, see that brief) exists in the tree to express a result at
  one distance as an equivalent at another.
- After `load-history`, a daily load series over the archive exists, with a
  coverage measure per period, and the recursion is implemented against
  Morton et al. eq. (4), (5), (8).
- Morton et al. §"Quantifying actual performance" converts race times to a
  criterion points score (eq. 13–14, a 1500 m world-record scale) before
  fitting; the reference doc records the equations and notes fitdocs "has no
  use for this today". This spec is the use.
- The fitted constants in Morton et al. were obtained by least squares
  against roughly two dozen criterion performances measured weekly over a
  season (df 4,21 and 4,18). Banister (1991) p. 415 adds that a fitted set
  holds for **60–90 days** before refitting is needed. D6 records that the
  fitted model's predicted time-to-peak missed the observed one by days to
  weeks for both subjects.
- No optimiser, no numerical dependency, and no fitting code exists in the
  tree. The dependency footprint is deliberately stdlib-only (tech.md).

## Desired Outcome

- A `fitdocs history fit` (name to be settled) command that fits k₁, k₂, τ₁,
  τ₂ and the baseline p₀ of `p(t) = p₀ + k₁·g(t) − k₂·h(t)` to the athlete's
  tagged races by least squares, over a window the athlete chooses, and
  reports the fit: the constants, r², standard error, and the residual per
  race, in a form the athlete can read on the history page.
- A **data-sufficiency gate** that refuses, with the reason, when the window
  holds too few criterion performances, spans too short a period, mixes
  distances the criterion scale cannot reconcile, or covers a stretch whose
  load coverage is below `load-history`'s threshold — a fit over missing loads
  is fiction.
- The fitted set, once accepted, is recorded with provenance (fit date,
  window, N, fidelity) and offered to `load-history` as the constants for the
  curve, with the seeds as the fallback and a staleness note after the 60–90
  day horizon Banister states.
- A **criterion-performance scale** with a citation: either Morton et al.'s
  points scale generalised through the race-equivalence model, or the
  equivalent time at one reference distance. The scale is stated on the page.

## Approach

A pure fitting module beside `load-history`'s model: criterion series in,
constants and fidelity out, deterministic. The optimiser is a bounded
coordinate/grid search or Nelder–Mead written in stdlib Python — four to five
parameters over a ~3,000-day series and a few dozen criterion points is small
enough that reproducibility matters more than speed, and a fixed search
schedule is reproducible where a library's default tolerances are not. The
gate runs before the optimiser and its thresholds are configuration with
cited or measured defaults.

## Scope

- **In**: the criterion-performance scale; the least-squares fit and its
  fidelity report; the sufficiency gate; recording the fitted set with
  provenance; `load-history` consuming it in place of the seeds; the command.
- **Out**: predicting a future race; recommending a taper; plan documents;
  fitting anything other than the Morton et al. model (no Busso variants, no
  PerPot); fitting on hard efforts that are not races unless the athlete
  tagged them as tests with a result; changing how loads or thresholds are
  computed.

## Boundary Candidates

- **Criterion scale** (pure): race result → comparable performance number,
  with its citation.
- **Fit** (pure): series + criterion points → constants + fidelity, with the
  optimiser's schedule pinned.
- **Gate** (pure): the refusal rules and their thresholds.
- **Persistence and consumption**: where the fitted set lives and how
  `load-history` picks it up.

## Out of Boundary

- The daily series, the recursion and the page (`load-history`).
- The race-equivalence model itself (`performance-benchmarks` owns it; this
  spec reuses it).
- Deciding which activities are races (`effort-tags`).

## Upstream / Downstream

- **Upstream**: `load-history` (series, recursion, coverage measure, page),
  `performance-benchmarks` (race-equivalence model), `effort-tags` (results),
  `docs/reference/banister-trimp-primary-sources.md` (the equations and the
  D5/D6 caveats).
- **Downstream**: a future forecast or taper-planning feature would be built
  on the fitted constants; nothing else.

## Existing Spec Touchpoints

- **Extends**: `load-history` (a constants source other than seeds).
- **Adjacent**: `athlete-benchmarks` (if the fitted set is stored in
  `athlete.toml`, it is a new table under the same schema-version discipline;
  if in `fitdocs.toml`, a new settings table — design decides, and it is
  written by fitdocs either way so the ownership contract must say so).

## Constraints

- **Identifiability is the known weakness of this model, and the literature
  is worse than the seeds suggest.** Hellard et al. (2006) *J Sports Sci*
  24(5):509–520 fitted nine elite swimmers over a season and found bootstrap
  95% intervals of τ₁ = 38 (17–59) d and τ₂ = 19 (6–32) d, with "some
  parameters highly correlated, making their interpretation worthless".
  Marchal et al. (2025) *Sci Rep* 15:3706 found the fitness and fatigue gains
  antagonistic and non-identifiable even with 35–54 performances per athlete
  in 10–13 weeks, found the fatigue term added no out-of-sample accuracy, and
  recommended a fitness-only model. Vermeire et al. (2022) *Int J Sports
  Physiol Perform* 17(5):810–813 showed the estimates depend on starting
  values and technique. **No peer-reviewed minimum-N rule exists**; the only
  quantitative guidance is Coggan's (2006, secondary): 5–50 measurements per
  adjustable parameter, refit every 60–90 days. Every published fit used dense
  data (weekly or better, ≤15 weeks); a few dozen races over nine years is
  sparser than anything in the literature. Consequences for this spec: the
  gate's defaults cite Hellard 2006 and Marchal 2025 or are recorded as a
  fitdocs choice with that justification; the fit **must report confidence
  intervals or a profile-likelihood flatness check**, not a point estimate
  alone; and a **fitness-only fit** (k₂ = 0, two constants) is a first-class
  option the requirements phase should weigh as the default, per Marchal
  2025. Clarke & Skiba (2013) *Adv Physiol Educ* 37(2):134–152 is the
  teaching reference for the least-squares procedure itself.
- **Refusal is a first-class outcome.** An archive with three races does not
  get a fit with r² attached; it gets the reason and the seeded curve.
- **Every constant, including the seeds the fit replaces, the optimiser's
  bounds and the gate's thresholds, is a `CitedConstant` or a recorded fitdocs
  choice.** No bare literals.
- **Determinism**: the same documents and configuration yield the same fitted
  constants to the last digit. The optimiser's schedule is part of the
  contract, not an implementation detail.
- **Stdlib only.** No numpy, no scipy. Feasibility was checked: two O(N)
  exponential recursions per evaluation over ~3,000 days and a few thousand
  optimiser evaluations is seconds in CPython. `math.exp` is libm-backed, so
  cross-platform golden tests compare fitted constants with a stated
  tolerance rather than byte-for-byte; the optimiser's schedule is what makes
  two runs on one machine identical.
- **D6 travels with every user-facing claim**: the page never says "peak" or
  "ready" as a fact; it shows the model's number and the source's own
  measured error.
