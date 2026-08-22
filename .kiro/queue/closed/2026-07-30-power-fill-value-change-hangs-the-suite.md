---
id: 2026-07-30-power-fill-value-change-hangs-the-suite
title: Changing the absent-power fill value from 0.0 to 25.0 hangs the test suite instead of failing it
status: done
importance: medium
importance_why: A plausible value for a real constant turns a 14-second suite into a run that does not terminate in 10 minutes, which means some path is non-terminating or catastrophically slow under a non-zero fill — and it also blocked the fill value's own discrimination from being assessed.
effort: M
kind: bug
area: fit-ingest, src/fitdocs/metrics/power.py, tests/metrics
created: 2026-07-30
surfaced_by: /kiro-impl fit-ingest (task 12.2, round-4 review — mutation MUT-N3)
pinned_at: 2d69443
resume_command: "/kiro-impl fit-ingest [queue: .kiro/queue/2026-07-30-power-fill-value-change-hangs-the-suite.md] Root-cause why a non-zero absent-power fill makes the suite hang rather than fail"
context:
  - src/fitdocs/metrics/power.py
  - src/fitdocs/metrics/sources.py
  - tests/metrics/test_power.py
  - .kiro/steering/change-protocol.md
blocked_by: []
---

## What

`POWER_ABSENT_SAMPLE_FILL` is the constant `power.py` substitutes for an
unrecorded power sample (`0.0` today). A reviewer running the ordinary
discrimination mutation on it — `0.0` → `25.0` — found that
`uv run pytest` **did not terminate within 10 minutes**. The baseline suite
runs in about 14 seconds.

It did not fail. It hung.

## Why it matters

Two separate concerns, and the second is the reason this is not `low`:

1. **The constant's own pin could not be assessed.** The Fixture
   Discrimination gate asks for a mutation that reds the assertion under test.
   For this constant the natural mutation cannot be run to completion, so
   whether the fill value is genuinely pinned is currently **unknown** rather
   than verified. Task 12.2 shipped with that gap declared.
2. **Something is plausibly non-terminating on real input.** `0.0` is not a
   magic sentinel — it is the fill for a *missing* reading, and the queued item
   `2026-07-30-absent-power-sample-filled-with-zero` may well change it to a
   carried-forward value or remove the fill entirely. If a non-zero fill can
   hang the computation, that change would hang production, not just a test.
   The mechanism needs to be understood before that decision is made.

A plausible mechanism worth checking first: a non-zero fill makes previously
all-zero synthetic power series non-degenerate, which may push a fixture past
the normalized-power minimum span and into the 30-second rolling window
computation for the first time — so the hang may be in a path the current
fixtures never reach, rather than in the fill itself. That is a hypothesis, not
a finding; it has not been tested.

## Evidence

Reported by the task 12.2 round-4 reviewer, as mutation `MUT-N3`, against
`2d69443` plus the uncommitted task 12.2 work on branch `impl/fit-ingest`:

> **MUT-N3** `POWER_ABSENT_SAMPLE_FILL.value` `0.0` → `25.0` —
> **INCONCLUSIVE**: `uv run pytest` hung past a 10-minute timeout rather than
> failing. Reverted.

Baseline at the same tree state: `2228 passed in 13.22s` (independently
re-run by the parent session after the review).

**Not independently reproduced by the parent session** — reproducing it costs
a >10-minute blocked run, and the branch was mid-remediation. The reviewer
reverted cleanly and the tree was verified byte-identical afterwards, so the
observation stands on that one run only. Reproduce before diagnosing.

## How to pick it up

1. Reproduce with a bounded timeout so you get a stack rather than a wall:
   `uv run pytest -x --timeout=60` (add `pytest-timeout` if absent), or run
   with `faulthandler` — `uv run pytest -p faulthandler --faulthandler-timeout=60`
   dumps the traceback of whatever is spinning. That traceback is the whole
   answer; do not reason about the cause first.
2. Narrow to the test. If it is in `tests/metrics/test_power.py`, check whether
   the fill change pushes a fixture across the `NP_MIN_SPAN_S` boundary and
   into the rolling-window path for the first time — a loop whose bound depends
   on a value derived from the samples is the shape to look for.
3. Decide whether the fix is in production code (a genuinely unbounded path,
   which is a real bug) or in a fixture (a test that becomes pathologically
   large under a non-zero fill, which is a test-design problem). Say which.
4. Once it terminates, complete the discrimination the reviewer could not:
   confirm `POWER_ABSENT_SAMPLE_FILL.value` is pinned by a test that reds when
   the value moves, and record the mutation.

Done looks like: the mutation reds in bounded time, and the fill value's pin is
verified rather than unknown.

## Open questions

- Does this reproduce with any non-zero fill, or only with values above some
  threshold? That distinguishes "a path that assumes zero" from "a path whose
  cost scales with the value".

## Resolution

**Status: done. Closed 2026-07-30.** This item had two halves and they resolved
differently. Recording both honestly, because the first half is a
**non-reproduction**, not a fix.

### Half 1 — the hang: NOT REPRODUCIBLE. No fix was made, and none was faked.

The reported symptom was that changing the absent-power fill from `0.0` to
`25.0` made `uv run pytest` **hang** rather than fail. Two independent
investigations failed to reproduce it:

- **Implementer**: replayed the exact literal mutation against both the branch
  base and `2d69443` — the commit the report was actually filed against, mid
  task-12.2, before task 13.1's rolling-window rewrite. Both completed in
  ~15-17s with only the expected assertion failure, `faulthandler` armed
  throughout.
- **Reviewer**, going further: ran the full suite on the **old** code path (where
  the fill reaches every dropout) at fill ∈ `{25.0, 0.5, -500.0, 1e12, NaN, Inf}`.
  All completed in 15.4-16.7s. It then scanned `power.py`, `test_power.py`,
  `test_sources.py` and `test_constant_guard.py` for any unbounded construct —
  no `while`, no retry, no search, no `hypothesis` generator. `_resample_power_1hz`,
  `_trailing_rolling_mean` and `normalized_power` are linear and value-independent
  in bound.

**Conclusion**: the hang was specific to that session's uncommitted, never-merged
task-12.2 branch state — something in an in-progress `ConstantGuard` /
`test_sources.py` variant that no longer exists. It is not a property of any code
that survives on `main`.

Re-verified at close time. The originally-reported mutation site no longer exists
(the constant was deleted at `dd10f9f`), so the nearest live analogue was used —
mutating the value the resample carries forward:

```
$ # last_recorded = float(first_value)  ->  last_recorded = 25.0
$ time uv run pytest -q
12 failed, 2295 passed in 14.82s          (15.0s wall)
```

Reds in bounded time, exactly as it should. **If this ever recurs, re-open with a
fresh live reproduction** — do not treat this close as evidence the class is
impossible, only that it does not reproduce on `main`.

### Half 2 — the fill-value pin: SATISFIED, via a route the item did not anticipate

The item's step 4 required: *"confirm `POWER_ABSENT_SAMPLE_FILL.value` is pinned
by a test that reds when the value moves."*

The first remediation round **failed** this. The reviewer found that the new test
read its expected value from the module under test:

```python
fill = sources.POWER_ABSENT_SAMPLE_FILL.value
assert resampled == [fill, fill, 200.0, 200.0]
```

so `0.0 → 25.0` left all 2291 tests green — a **net loss** of discrimination
against the base commit, which had pinned it. That was rejected and fixed.

The final resolution is stronger than the item asked for: **the constant is gone
entirely** (`dd10f9f`), so there is no value left to pin. The behaviour that
replaced it is pinned by hand-written literals in
`test_resample_power_1hz_leading_none_truncates_the_grid` and
`test_resample_power_1hz_scans_every_sample_between_two_grid_seconds`, both shown
red under their respective mutations.

### Why `done` rather than `dropped`

Half 2 is genuinely resolved. Half 1 was investigated properly — six fill values,
two code paths, a source scan for unbounded constructs — and found not to
reproduce. That is a resolution, not an abandonment. The item is not being
discarded for lack of interest.
