---
id: 2026-07-30-absent-power-sample-filled-with-zero
title: An absent power sample is resampled as a fabricated 0.0, which the steering hard rule forbids
status: done
importance: medium
importance_why: A fabricated 0 for missing data flows into normalized power and everything downstream of it (IF, VI, TSS, EF), and it is the one data-integrity rule CLAUDE.md and tech.md state as absolute. Task 12.2 made the choice honestly *recorded*; nobody has ruled on whether it is *right*.
effort: M
kind: inconsistency
area: fit-ingest, src/fitdocs/metrics/power.py, .kiro/steering/tech.md
created: 2026-07-30
surfaced_by: /kiro-impl fit-ingest (task 12.2, reviewer finding 3 of round 1)
pinned_at: 2d69443
resume_command: "/kiro-impl fit-ingest [queue: .kiro/queue/2026-07-30-absent-power-sample-filled-with-zero.md] Rule on whether an absent power sample may be resampled as 0.0, given the never-fabricate-a-zero hard rule"
context:
  - src/fitdocs/metrics/power.py
  - src/fitdocs/metrics/sources.py
  - .kiro/steering/tech.md
  - CLAUDE.md
  - .kiro/specs/fit-ingest/requirements.md
blocked_by: []
---

## What

`_resample_power_1hz` in `src/fitdocs/metrics/power.py` substitutes `0.0` for
any power sample the device did not record, and every downstream metric then
treats that fabricated zero as a real observation of zero watts.

The repo's steering states the opposite rule without qualification. `CLAUDE.md`
and `.kiro/steering/tech.md`: *absent data is `None`, never a fabricated `0`
or default.*

Task 12.2 (`ConstantGuard`) collided with this while classifying numeric
literals. The `0.0` was first filed as an `ARITHMETIC_IDENTITY` exemption — an
assertion that it carries no methodological choice — and the reviewer rejected
that as exactly the "dishonestly classified constant" the guard exists to
catch. The remediation recorded it honestly as a `FitdocsChoice`
(`POWER_ABSENT_SAMPLE_CHOICE` / `POWER_ABSENT_SAMPLE_FILL` in
`src/fitdocs/metrics/sources.py`), with a justification naming the two
rejected alternatives.

**That change made the provenance honest. It did not resolve the conflict.**
The behaviour is unchanged and the rule it contradicts is still absolute.

## Why it matters

The fill is not cosmetic. A coasting or dropout sample entering the
30-second rolling average as `0.0` pulls the average down, and normalized
power is a fourth-power mean over that series — so the error propagates into
intensity factor, variability index, training-stress score and cycling
efficiency factor, all of which are written into rendered workout documents.

The three plausible rules give materially different numbers on real data:
fill with `0.0` (today), carry the last non-`None` sample forward, or omit
the sample and shrink the denominator. Nobody has ruled between them, and
the current answer was arrived at by implementation rather than decision.

There is also a live question of whether the hard rule even *reaches* here.
A rider genuinely coasting produces no power, so `0.0` may be the physically
correct reading rather than a fabrication — in which case the rule stands and
this site is simply outside it. That distinction is the decision this item
wants; it is not currently written down anywhere.

## Evidence

At `2d69443` plus the uncommitted task 12.2 work, in the `impl/fit-ingest`
worktree:

- `src/fitdocs/metrics/power.py:138` —
  `float(value) if value is not None else _POWER_ABSENT_SAMPLE_FILL`
- `src/fitdocs/metrics/power.py:108` —
  `_POWER_ABSENT_SAMPLE_FILL: Final[float] = sources.POWER_ABSENT_SAMPLE_FILL.value`
- `src/fitdocs/metrics/power.py:126` — the helper's own docstring naming the
  fill; the module docstring calls the step "fitdocs' own resample step"
- `CLAUDE.md`, Hard rules: *"absent data is `None`, never a fabricated `0`"*

Round 1 of the task 12.2 review raised this as finding 3 and the round-2
reviewer restated it as an explicit follow-up, both times ruling only that
the *provenance* is now honest and that the behavioural question was outside
the task's boundary.

## How to pick it up

1. Read `src/fitdocs/metrics/power.py`'s module docstring and
   `_resample_power_1hz`, then `POWER_ABSENT_SAMPLE_CHOICE` in
   `src/fitdocs/metrics/sources.py` — its `justification` already names the
   two alternatives that were rejected and why, which is the argument you are
   re-opening.
2. Settle the framing question first: is a `None` power sample a *missing
   reading* (the hard rule applies, and `0.0` is a fabrication) or a
   *recorded absence of power* (the rider is coasting, and `0.0` is the true
   value)? The answer may differ by device and by whether the FIT file
   distinguishes the two; check what the ingest layer actually produces
   before deciding, rather than reasoning from the metric layer alone.
3. If the current rule survives, the outcome is a recorded ruling — extend
   the `FitdocsChoice`'s justification to state that the hard rule was
   considered and why this site is outside it, so the next reader does not
   re-open it. If it does not survive, the change is behavioural and moves
   reported values, so it needs the same migration treatment as task 13.1's
   rolling-window conformance change: a document-format version advance and
   regeneration of every committed golden.

Done looks like: a written ruling either way, reachable from
`power.py`, and no remaining conflict between the code and the steering rule.

## Open questions

- Does the FIT decode distinguish "sensor dropout" from "genuinely zero
  power"? If it does, the two cases plausibly want different rules and the
  single `0.0` fill is wrong for one of them.
- If the fill changes, does `.kiro/steering/tech.md` want a worked example of
  this case, given it is the first place the hard rule met a defensible
  counter-argument?

## Resolution

**Status: done. Closed 2026-07-30**, merged to `main` at `dd10f9f`
(`chore/power-absent-sample-fill`, 3 commits), validated after rebase:
2307 passed, ruff + format + mypy clean.

### The framing question this item asked was answered by evidence, not judgement

The item asked whether a `None` power sample is a *missing reading* (hard rule
applies) or a *recorded absence of power* (coasting, so `0.0` is true). Its own
Open Questions asked whether the FIT decode distinguishes them. It does:

`src/fitdocs/ingest/records.py:131-141` — `_int_channel` returns a present `0`
**verbatim** and returns `None` only when the field is absent from the record.
So a coasting rider already arrives as integer `0` and was never affected by the
fill. `None` is unambiguously a dropout, and the `0.0` was a fabrication. The
"it may be physically correct" counter-argument is falsified.

**Maintainer ruling**: forward-fill the last recorded value, with full migration.

### What changed

Three defects, all reaching rendered documents:

1. **The fabricated zero is gone.** An absent sample forward-fills the last
   recorded watt. On a 300 W → 10 s dropout → 100 W fixture, NP moves
   `168.3045019173969` → `247.5406212723606` (reviewer reproduced both to the
   last digit with exact `Fraction` arithmetic, without importing the module).
2. **A leading dropout truncates the grid** to the first recorded sample rather
   than fabricating anything — the residual the first review round caught. The
   old behaviour understated NP by **4.47% at a 10 s lead-in and 14.60% at 20 s**.
3. **A recorded sample sharing a grid second with a later one is no longer
   skipped**: `(0.0,1.0,1.0,2.0)/(100,200,None,None)` returned `[100,100,100]`,
   now returns `[100,200,200]`. Reachable because ingest retains
   duplicate-timestamp records without de-duplication.

### Verified on `main` at close time

```
POWER_ABSENT_SAMPLE_FILL exists: False
leading dropout truncates : [200.0, 200.0]     # no 0.0 anywhere
skipped recorded sample   : [100.0, 200.0, 200.0]
```

### The constant was deleted, not re-justified

`POWER_ABSENT_SAMPLE_CHOICE` and `POWER_ABSENT_SAMPLE_FILL` are **removed**.
With truncation there is no fill value anywhere, so the `CitedConstant` had
nothing left to bind and would have been dead surface. Its record's stated
premise — *"the resample still owes every grid second some float"* — was false:
the grid's origin is a free choice. `metrics/sources.py` is back to three
`FitdocsChoice` records and ten `CitedConstant` bindings; `CONSTANT_SOURCES`
unchanged at 10. The registry assertions got **stricter**: exact set equality
replaced a documented-exception carve-out, so an unregistered module-level
`CitedConstant` now reds three tests.

### Migration

`DOC_VERSION` 4 → 5, pair `(2, 5)`. New golden `ride_power_dropout` is the
**first golden in this repo's history to render an NP value at all** — every
other power fixture spans ~9 s and yields `None`, so without it the migration
would have demonstrated nothing. It pins `NP 238 w` where the old code gave
`211.4465220583894`.

### Discrimination

Reviewer ran 8 mutations in the final round, **0 survivors**, and confirmed the
resample is amortized linear (200k → 0.010s, 400k → 0.019s, ratio 1.95). The
`contract.py` scoping claim — that an activity with no dropout computes
identically before and after — was verified over 3,000 randomized dropout-free
streams (3000 identical) and 3,000 streams with 15% dropouts (0 identical).

### Follow-on

`.kiro/queue/2026-07-30-min-span-guard-bypassable-by-a-leading-dropout.md` — the
truncation made a pre-existing asymmetry reachable: the min-span guard measures
the overall sample span, so a long enough lead-in carries a sub-minimum stream
past it. Narrow band, silent, one-line fix once the intent is settled.
