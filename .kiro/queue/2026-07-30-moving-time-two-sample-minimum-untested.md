---
id: 2026-07-30-moving-time-two-sample-minimum-untested
title: The moving-time two-sample minimum is covered by no behavioural test, only by a literal guard
status: open
importance: medium
importance_why: A mutation to the guard condition reddened only the new ConstantGuard tests and nothing in the metric's own suite, so the boundary that decides whether moving time is computed at all is pinned by a test that does not care what the number means.
effort: S
kind: gap
area: fit-ingest, tests/metrics/test_aggregates.py, src/fitdocs/metrics/aggregates.py
created: 2026-07-30
surfaced_by: /kiro-impl fit-ingest (task 12.2, reviewer follow-up round 1)
pinned_at: c3d2201
resume_command: "/kiro-impl fit-ingest [queue: .kiro/queue/2026-07-30-moving-time-two-sample-minimum-untested.md] Add a behavioural test for the two-sample minimum in _derive_moving_time_s"
context:
  - src/fitdocs/metrics/aggregates.py
  - tests/metrics/test_aggregates.py
  - .kiro/specs/fit-ingest/requirements.md
blocked_by: []
---

## What

`_derive_moving_time_s` in `src/fitdocs/metrics/aggregates.py` refuses to
compute moving time for a series shorter than two samples:

```python
if not (has_speed or has_distance) or len(time_s) < 2:
```

No test in `tests/metrics/test_aggregates.py` feeds it a two-sample series, so
nothing in the metric's own suite distinguishes `< 2` from `< 3` — or from
`< 1`, which would index past the end of a one-sample series.

## Why it matters

This is the boundary that decides whether moving time is reported at all
versus reported as absent, and absent-vs-present is precisely the distinction
this repo treats as load-bearing (`None`, never a fabricated `0`). A wrong
threshold here either fabricates a moving time from a degenerate series or
suppresses a legitimate one.

It is `medium` rather than `high` because the condition is correct today and
the ConstantGuard does red on the mutation — but it reds for the wrong
reason. The guard notices that a *literal changed*; it cannot notice that the
*behaviour* changed. If the guard's exemption list is ever edited to
accommodate the new value, the last thing standing over this boundary goes
away silently.

## Evidence

At `2d69443` plus the uncommitted task 12.2 work, mutating
`src/fitdocs/metrics/aggregates.py:120` from `len(time_s) < 2` to
`len(time_s) < 3` and running the full suite:

```
2226 passed, 2 failed
```

Both failures were the new ConstantGuard tests in
`tests/metrics/test_constant_guard.py` (the literal `2` is no longer at its
exempted site, and the exemption entry for it is now unmatched). **Zero tests
in `tests/metrics/test_aggregates.py` failed.**

Independently confirmed: `grep -n 'time_s=\[0' tests/metrics/test_aggregates.py`
returns no two-element series.

Run by the task 12.2 reviewer as a sole-failure check while verifying the
guard's value sensitivity — the guard behaved correctly; the gap it exposed is
in the metric's own coverage.

## How to pick it up

1. Open `tests/metrics/test_aggregates.py` and find the existing moving-time
   cases to match their fixture style.
2. Add cases at the boundary: a one-sample series (expect absent), a
   two-sample series (expect a computed value), and — if the fixture shape
   allows — an empty series. Make the two-sample case's expected value one
   that a `< 3` threshold could not also produce, so the mutation below is a
   sole failure in this file.
3. Verify by mutation, per `.kiro/steering/change-protocol.md` § Fixture
   Discrimination: `< 2` → `< 3` must red your new test specifically, and
   `< 2` → `< 1` should red or raise rather than pass. Run mutations through
   `uv run pytest`, never `uv run python -c`.

Done looks like: the two-sample boundary reds a test in
`tests/metrics/test_aggregates.py`, not only the literal guard.
