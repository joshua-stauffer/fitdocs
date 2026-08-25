---
id: 2026-08-25-load-channels-spec-demands-exact-floats-hr-cannot-deliver
title: Req 1.6's "exactly 100" threshold identity is false for the heart-rate channel, and a merged test is named for an exactness it does not assert
status: open
importance: medium
importance_why: A merged test is named ..._exactly_100_... while asserting approx; the next session that "restores" == to match the name reds the suite and misreads it as a production regression.
effort: S
kind: inconsistency
area: load-channels, .kiro/specs/load-channels/requirements.md, .kiro/specs/load-channels/design.md, tests/load/channels/test_heart_rate.py
created: 2026-08-25
surfaced_by: /kiro-impl load-channels (task 5.1 review rounds 1-2; measured independently by the parent session)
pinned_at: bf10391
resume_command: "do: correct load-channels Req 1.6 / design.md's 'exactly 100, intensity exactly 1.0' wording to the tolerance the heart-rate channel can meet, and rename tests/load/channels/test_heart_rate.py's test_one_hour_at_threshold_scores_exactly_100_with_intensity_1 to match what it asserts"
context:
  - .kiro/specs/load-channels/requirements.md
  - .kiro/specs/load-channels/design.md
  - tests/load/channels/test_heart_rate.py
  - src/fitdocs/load/channels/heart_rate.py
blocked_by: []
---

## What

**Req 1.6 and design.md** state that one hour held at threshold scores
**"exactly 100"** with an intensity of **"exactly 1.0"**. That is true for the
power and pace channels and **false for heart rate**.

The cause is inherent to the design, not a bug: `trimp()` sums 3600
per-sample-pair contributions while the reference is a single-interval
computation, so the two paths agree to ~3.6e-14 rather than to the bit. The
shipped numbers are correct; the spec's wording is not.

The consequence has already reached merged code.
`tests/load/channels/test_heart_rate.py:200` is named
`test_one_hour_at_threshold_scores_exactly_100_with_intensity_1` and asserts
`pytest.approx`. A test name is prose a later editor trusts.

> **Scope correction, 2026-08-25.** An earlier revision of this item also
> claimed the coefficient-invariance requirement ("bit-identical") was
> unattainable. **That was wrong and has been removed.** Bit-identity *is*
> achievable — see Evidence — and task 5.1 now delivers it. Only the
> threshold-identity wording is defective. The error is recorded rather than
> silently dropped because the wrong version was committed (`510419e`) and a
> reader may have seen it.

## Why it matters

The failing direction is not the risk. The risk is the *passing* one: an editor
who believes "exactly 100" tightens `approx` to `==`, sees red, and concludes
the production channel regressed — when the spec sentence is what is wrong.

Task 5.3 asserts the intensity semantic across channels and will read the same
"exactly" language, so the wording keeps propagating until it is fixed.

## Evidence

Threshold identity, measured at `bf10391` against the merged test module's own
fixtures:

```
HR load      = 100.00000000000355
HR intensity = 1.0000000000000178
load == 100.0      -> False
intensity == 1.0   -> False
```

Power and pace are genuinely exact — `tests/load/channels/test_power.py:149`
asserts bare `result.load == 100.0` / `result.intensity == 1.0` and passes.

The mismatched name is at `tests/load/channels/test_heart_rate.py:200`,
asserting `pytest.approx(100.0)` at :210.

**Why the invariance half was struck.** Coefficient rescale measured on the
same fixture, varying only the factor:

```
factor 2.0   bit-identical: True   relerr 0.000e+00
factor 4.0   bit-identical: True   relerr 0.000e+00
factor 8.0   bit-identical: True   relerr 0.000e+00
factor 7.0   bit-identical: False  relerr 8.455e-14
factor 3.0   bit-identical: False  relerr 5.826e-15
factor 1.5   bit-identical: False  relerr 5.826e-15
```

Non-associative addition **cancels exactly** — both runs sum the same 3600
terms in the same order. The imprecision at factor 7.0 comes from rounding when
each per-term product is scaled by a non-power-of-two, not from summation
order. So `design.md:1381-1383` and `tasks.md:453-455`'s "bit-identical" is
**satisfiable as written**, with a power-of-two factor, and needs no amendment.

## How to pick it up

1. Re-run the threshold measurement above — one command against merged code,
   and it confirms the whole item.
2. Decide the wording for Req 1.6 and its design.md restatement. The honest
   form states the tolerance and the reason (summation order against a
   single-interval reference). **Do not flatten all three channels into one
   weaker claim** — power and pace really are exact, and saying otherwise
   discards real coverage.
3. Amend `requirements.md` Req 1.6 and the matching design.md line. Spec edits
   need whatever re-approval the phase requires.
4. Rename `test_one_hour_at_threshold_scores_exactly_100_with_intensity_1` to
   match what it asserts. **Leave the assertion alone** — it is correct.

**Done** looks like: no spec sentence claims a threshold exactness the
heart-rate channel cannot deliver, no test name claims one either, and the
power/pace exactness that does hold is still stated.

## Open questions

- Should Req 1.6 state one tolerance for all three channels, or keep the
  stronger exact claim for power and pace and qualify only heart rate? The
  latter preserves more coverage but is wordier. `activity-qa-flags` consumes
  the threshold identity — check what that spec assumes before weakening a
  claim it may rely on.
