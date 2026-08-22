---
id: 2026-07-27-trimp-coefficient-b91-vs-m90
title: The two primary texts disagree on the TRIMP multiplicative coefficient — decide which one fitdocs ships
status: done
importance: high
importance_why: Banister 1991 carries 0.64; Morton 1990 Eq. 2 carries no coefficient at all. Adopting Morton multiplies every rendered DerivedMetrics.trimp by 1.5625 and needs migration-by-regen. Both texts are now in hand, so this is a decision, not a research task — and it is the one thing blocking the citation from being cleanly primary-sourced.
effort: M
kind: decision
area: fit-ingest, src/fitdocs/metrics/stress.py, load-channels
created: 2026-07-27
surfaced_by: reading both primary texts side by side (docs/reference/banister-trimp-primary-sources.md §5 D1)
pinned_at: 4a5c838
resume_command: "do: decide whether raw TRIMP keeps Banister 1991's 0.64 coefficient or moves to Morton 1990 Eq. 2's bare exponential, then make stress.py and its citation say the same thing [queue: .kiro/queue/2026-07-27-trimp-coefficient-b91-vs-m90.md]"
context:
  - docs/reference/banister-trimp-primary-sources.md
  - src/fitdocs/metrics/stress.py
  - .kiro/specs/fit-ingest/requirements.md
  - .kiro/specs/load-channels/design.md
blocked_by: []
---

## What

The two defining texts state the intensity weighting differently:

| Source | Weighting | at x=0 | at x=1 |
|---|---|---:|---:|
| Banister 1991, p. 408 | `y = 0.64·e^(1.92x)` male, `0.86·e^(1.67x)` female | 0.64 | 4.365 |
| Morton 1990, Eq. 2, p. 1172 | `Y = e^(bx)`, b = 1.92 men / 1.67 women | 1.000 | 6.821 |

The exponents agree exactly. Only the leading coefficient is in dispute.
`src/fitdocs/metrics/stress.py` ships Banister's 0.64.

## Why it matters

Raw TRIMP under Morton is exactly `1/0.64 = 1.5625×` Banister's, for every
activity. `DerivedMetrics.trimp` is already rendered into documents, so a change
goes through migration-by-regen. The heart-rate *channel* is not affected either
way: HRSS's ratio form `TRIMP_activity / TRIMP_1h_at_LTHR × 100` carries the
coefficient in both numerator and denominator and it cancels exactly. So the
blast radius is raw TRIMP output only — but that output is user-visible and
already on disk.

## Evidence

- `docs/reference/banister-trimp-primary-sources.md` §5 D1 — the two forms
  tabulated, with the x=0 / x=1 values above.
- **§5 D1a is the discriminating evidence.** Morton p. 1172 illustrates the
  scale: subject RHM generated "~125 training impulses by running 14 km in 1 h
  at a heart rate of 150 beats/min". RHM is male, age 42 (Morton Table 1).
  Solving back for the ΔHR ratio that yields 125 units in 60 min:

  | Weighting | implied x | implied HR_max at HR_rest = 50 |
  |---|---:|---:|
  | Morton Eq. 2 as printed | 0.626 | 210 |
  | Banister's 0.64 form | 0.759 | 182 |

  182 is ordinary for a 42-year-old; 210 is not. **Morton's own worked example
  appears to have been computed with the coefficient Morton's equation omits.**
- `src/fitdocs/metrics/stress.py:56-59` — `_TRIMP_COEFFICIENT = 0.64`,
  `_TRIMP_EXPONENT = 1.92`.

## How to pick it up

1. Read `docs/reference/banister-trimp-primary-sources.md` §5 D1 and D1a.
2. The recommendation from the extracting session is **keep 0.64**: it is what
   Banister's own text states, what Morton's own numerical illustration implies,
   and what fitdocs already ships — so it is both the better-attested and the
   zero-migration option. The Morton conflict then gets recorded in the citation
   note rather than acted on. This is a recommendation, not a ruling.
3. Whatever is chosen, the citation note must name **both** forms. A note that
   cites Morton for a formula Morton does not print, or cites Banister without
   mentioning that the companion paper omits the coefficient, is exactly the
   kind of flattened attestation the citation-vocabulary work was about.
4. Two adjacent deviations are documented in the same reference doc §6 and are
   **not** in this item's scope, but should not be reintroduced as surprises:
   fitdocs applies the male exponent sex-neutrally, and integrates per sample
   pair rather than per steady-state segment (which, the integrand being convex,
   makes fitdocs' TRIMP systematically ≥ the textbook per-segment value whenever
   HR varies).

## Open questions

- Maintainer's call, since it changes rendered output for every athlete.
- If 0.64 is kept: does `VerificationStatus` need a way to say "primary text,
  but a companion primary text disagrees"? Today's vocabulary has no term for a
  conflict *between* primary sources.

## Resolution

**Closed 2026-07-27 — maintainer ruled: keep Banister's `0.64`.**

No code change was required: `src/fitdocs/metrics/stress.py` already ships
`_TRIMP_COEFFICIENT = 0.64`. The ruling therefore confirms the shipped value
rather than changing it, and the 1.5625× migration-by-regen exposure described
above existed only on the road not taken. **No rendered `DerivedMetrics.trimp`
moves.**

What this does *not* close, and what it hands to
`2026-07-27-banister-morton-primary-texts-obtained`:

1. The citation note must name **both** forms — B91 p. 408's
   `y = 0.64e^(1.92x)` and M90 Eq. 2 p. 1172's uncoefficiented `Y = e^(bx)` —
   and say which fitdocs ships and why. Citing B91 alone would hide the
   conflict; citing M90 for a formula M90 does not print would be worse.
2. The open question raised in this item is now live rather than hypothetical:
   `VerificationStatus` has no term for "primary text, but a companion primary
   text disagrees". Decide there whether `PRIMARY_TEXT` plus a note is
   sufficient, or whether the vocabulary needs the case.
3. The two adjacent deviations in §6 of the reference doc — the sex-neutral use
   of the male exponent, and per-sample rather than per-segment integration —
   were **not** in this item's scope and remain unaddressed. Neither was ruled
   on here.

Steering was updated in the same change: `roadmap.md`'s Phase 4 fit-ingest item
now records the ruling, states that no migration is owed, and drops the
"expect this item to need document access" warning.
