---
id: 2026-07-30-np-direction-claim-is-conditional
title: tasks.md states the normalized-power change raises NP unconditionally, but the direction depends on the series shape
status: done
importance: medium
importance_why: Task 13.4 has to measure this change on real files, and a signed expectation ("NP rises") is wrong for any activity that opens at or above its own overall intensity — validating against it would either pass vacuously or flag a correct result as a regression.
effort: S
kind: inconsistency
area: fit-ingest, .kiro/specs/fit-ingest/tasks.md
created: 2026-07-30
surfaced_by: /kiro-impl fit-ingest (task 13.1 — found by the implementer, confirmed independently by the parent and the reviewer)
pinned_at: 99f098c
resume_command: "/kiro-impl fit-ingest [queue: .kiro/queue/2026-07-30-np-direction-claim-is-conditional.md] Qualify tasks.md's NP direction claim before task 13.4 validates against it"
context:
  - .kiro/specs/fit-ingest/tasks.md
  - src/fitdocs/metrics/power.py
  - tests/metrics/test_power.py
blocked_by: []
---

## What

`.kiro/specs/fit-ingest/tasks.md:262` describes task 13.1:

> "This is the only value-moving change in the amendment: dropping the low
> partial-window averages raises normalized power and with it intensity
> factor, variability index, training-stress score and cycling efficiency
> factor"

The first half is correctly qualified — it says dropping the **low** partial-window
averages. The downstream clause reads as unconditional, and that is how a
later task will use it.

The direction is not unconditional. NP rises **iff** the dropped leading
windows' mean fourth power is below that of the retained series. Partial
windows are means over shorter spans; they are neither systematically higher
nor lower than the series they precede.

## Why it matters

Task 13.4 must "re-parse and re-compute over the maintainer's real files so the
conformance change is measured on real activities". If it validates a signed
movement — asserting NP went up — it will be wrong for a real and common case:
any activity that opens at or above its own overall intensity, such as a hard
opener, a race start, or an interval set beginning at full effort.

Two outcomes, both bad. If such a file is present, a correct result is flagged
as a regression. If none is present, the assertion passes without ever having
been able to fail, and the 13.4 gate reports a validated direction it never
tested.

13.4 should validate a **per-file recomputation** — that the new value equals
the complete-window definition applied to that file's own series — and report
the observed movement per file as data, not assert its sign.

## Evidence

Both fixtures are in `tests/metrics/test_power.py` at `99f098c`, and both
values were derived three times independently (implementer, parent session,
reviewer) with exact rationals, none importing the module under test. All
three agree bit-for-bit.

**Falls 17 W** — `test_normalized_power_exact_value_pins_fourth_power_exponent`,
a 60 s block at 300 W then 60 s at 100 W:

```
partial-window (old): 261.0938420658929   (n=120)
complete-window (new): 244.03877169307256 (n=91)
```

The 300 W block starts at t=0, so the leading partial windows are already at
the steady value; dropping them removes high points and lowers the mean.

**Rises 24.6 W** — `test_normalized_power_complete_window_raises_np_over_partial_window`,
29 s at 0 W then 61 s at 300 W:

```
partial-window (old): 241.0463756814967   (n=90)
complete-window (new): 265.66159423758893 (n=61)
```

The test file already documents this distinction explicitly and scopes its
direction claim to the second fixture; the code asserts no direction at all.
**The artifact is correct — only the spec prose overreaches.**

## How to pick it up

1. Read `tasks.md:262` and `tasks.md`'s 13.4 clauses (~line 291).
2. Qualify the downstream clause: the movement's *direction* depends on
   whether the dropped leading windows sit below the retained series, and NP
   rises for the common warm-up shape while falling for an activity that opens
   at full effort.
3. Make 13.4's Observable explicit that it validates a per-file recomputation
   and **reports** the movement, rather than asserting its sign. The existing
   wording — "with the normalized-power movement on real data measured and
   reported rather than asserted" — is already close to right; it just needs to
   not be read through 262's unconditional clause.
4. If 13.4 has already run when you pick this up, check what it actually
   asserted.

Done looks like: no spec sentence claims an unconditional direction, and 13.4
validates recomputation rather than sign.

## Resolution

Closed 2026-07-30. Point 4 checked first: task 13.4 had already run
(Implementation Notes, `tasks.md:613-623`) and asserts nothing about
direction in the test suite — `grep` for its real-data figures ("53 rose, 1
fell", "median") across `tests/` finds no matches, confirming the real-data
pass is a measured-and-reported script run, not a pytest assertion. Nothing
there needed correcting.

`tasks.md:262` rewritten to state the movement is directional on whether the
dropped leading windows' mean fourth power sits below or above the retained
series, citing both fixtures (`test_normalized_power_exact_value_pins_fourth_power_exponent`
falls, `test_normalized_power_complete_window_raises_np_over_partial_window`
rises) and the 13.4 Implementation Notes' real-data confirmation (53 rose, 1
fell).

**Correction, same day, after independent review rejected the closing
commit:** "No other spec sentence was found asserting an unconditional
direction" (above) was wrong — the sweep that produced it was not
exhaustive. Four more instances turned up on the reviewer's own re-sweep:
design.md's PowerSeriesMetrics bullet, its Testing Strategy §13 NP-fixture
note, its "What actually moves a value" narrative, and research.md Decision
D7's Trade-off bullet — all now corrected the same way. The reviewer also
found the "falls" attribution above needs a precision the closing commit
missed: `test_normalized_power_exact_value_pins_fourth_power_exponent` pins
its complete-window value by exact assertion and documents the
higher partial-window value it replaces in a comment, but does not itself
assert that the two differ in that direction — only
`test_normalized_power_complete_window_raises_np_over_partial_window`
asserts a direction directly. Every corrected sentence now says so rather
than calling both "pinned" identically.
