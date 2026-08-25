---
id: 2026-08-25-load-channels-spec-demands-exact-floats-hr-cannot-deliver
title: load-channels' spec demands exact float equality ("bit-identical", "exactly 100") that the heart-rate channel structurally cannot deliver
status: open
importance: medium
importance_why: Two shipped tests are named for an exactness they do not assert; the next session that "restores" == to match a name reds the suite, and the spec re-imposes the impossible wording on every future task.
effort: S
kind: inconsistency
area: load-channels, .kiro/specs/load-channels/tasks.md, .kiro/specs/load-channels/design.md, tests/load/channels/test_heart_rate.py
created: 2026-08-25
surfaced_by: /kiro-impl load-channels (task 5.1 review; verified independently by the parent session)
pinned_at: bf10391
resume_command: "do: correct load-channels' exactness wording -- task 5.1's 'bit-identical' bullet and Req 1.6 / design.md's 'exactly 100' -- to the tolerance the heart-rate channel can actually meet, and rename tests/load/channels/test_heart_rate.py's test_one_hour_at_threshold_scores_exactly_100_with_intensity_1 to match what it asserts"
context:
  - .kiro/specs/load-channels/tasks.md
  - .kiro/specs/load-channels/design.md
  - .kiro/specs/load-channels/requirements.md
  - tests/load/channels/test_heart_rate.py
  - src/fitdocs/load/channels/heart_rate.py
blocked_by: []
---

## What

Two places in the `load-channels` spec demand **exact** floating-point results
from the heart-rate channel, and the channel cannot produce them. Both are
wording defects, not arithmetic defects — the shipped numbers are correct.

1. **Task 5.1's bullet and design.md's "Coefficient invariance" line** require
   that rescaling the training-impulse coefficient leaves the heart-rate load
   **"bit-identical"**. It does not: the error is real, tiny, and depends on the
   rescale factor.
2. **Req 1.6 and design.md** state that one hour at threshold scores
   **"exactly 100"** with intensity **"exactly 1.0"**. True for the power and
   pace channels; false for heart rate.

The cause is the same for both and is inherent to the design, not a bug:
`trimp()` sums 3600 per-sample-pair contributions, while the reference is a
single-interval computation. Float addition is not associative, so the two
paths agree to ~1e-14 rather than to the bit.

The consequence has already reached the code. `tests/load/channels/test_heart_rate.py:200`
is named `test_one_hour_at_threshold_scores_exactly_100_with_intensity_1` and
asserts `pytest.approx`. A name is prose a later editor trusts: the next session
that "restores" `==` to match the name reds the suite for a reason the name
actively conceals.

## Why it matters

The spec re-imposes the impossible wording on every task that reads it. Task
5.1 hit it and had to ship a test whose name contradicted its own assertion;
that was caught in review, but only because a reviewer measured the value
rather than reading the docstring. Task 5.3 asserts the intensity semantic
across channels and will read the same "exactly" language.

The costly direction is not the failing test — it is the passing one. An editor
who believes "exactly 100" tightens `approx` to `==`, sees red, and concludes
the *production* code regressed.

## Evidence

Measured this run at `bf10391`, driving the merged test module's own fixtures:

```
HR load      = 100.00000000000355
HR intensity = 1.0000000000000178
load == 100.0      -> False
intensity == 1.0   -> False
```

The other two channels are genuinely exact — `tests/load/channels/test_power.py:149`
asserts bare `result.load == 100.0` and `result.intensity == 1.0` and passes.

Coefficient invariance, measured by the task 5.1 reviewer under
`replace(coefficient, value=v*7.0)`:

```
56.07873353156187  vs  56.07873353156503     # rel err 5.626e-14
```

Exact only when the rescale factor is a power of two (factor 2.0 exact; factor
1.5 gives 1.5e-14).

The mismatched name is at `tests/load/channels/test_heart_rate.py:200`
(`test_one_hour_at_threshold_scores_exactly_100_with_intensity_1`, asserting
`pytest.approx(100.0)` at :210).

Surfaced as `FOLLOW_UPS` 1 and 2 by the task 5.1 reviewer subagent; the parent
session reproduced every number above before filing.

## How to pick it up

1. Read this item's Evidence and re-run the measurement — it is one command
   against merged code and confirms the whole item.
2. Decide the wording. The honest form is what task 5.1's own invariance
   docstring already uses: state the tolerance and the reason (summation order),
   rather than claiming exactness. Note power and pace *are* exact, so the
   replacement should not flatten all three channels into one weaker claim —
   that would lose real coverage.
3. Amend `tasks.md` task 5.1's bullet, `design.md`'s "Coefficient invariance"
   line, and Req 1.6 / its design restatement. Spec edits need whatever
   re-approval the phase requires.
4. Rename `test_one_hour_at_threshold_scores_exactly_100_with_intensity_1` to
   match what it asserts. Leave the assertion alone — it is correct.

**Done** looks like: no spec sentence claims an exactness the heart-rate
channel cannot deliver, no test name claims one either, and the power/pace
exactness that *does* hold is still stated.

## Open questions

- Should Req 1.6 state a single tolerance for all three channels, or keep the
  stronger exact claim for power and pace and qualify only heart rate? The
  latter preserves more coverage but is wordier, and `activity-qa-flags`
  consumes the threshold identity — worth checking what that spec assumes
  before weakening a claim it may rely on.
