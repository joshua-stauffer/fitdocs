---
id: 2026-07-29-altitude-record-swap-restoration-unpinned
title: The altitude record-swap test's module restoration is detected only by a test in another file, so its own file passes green when the restoration is dropped
status: open
importance: medium
importance_why: A dropped restoration leaks a mutated module constant into every later test in the run; the moving-time half was fixed in task 10.1 and the altitude half was left with the weaker shape.
effort: S
kind: gap
area: fit-ingest, tests/metrics/test_aggregates.py
created: 2026-07-29
surfaced_by: /kiro-impl fit-ingest (task 10.1, review round 3)
pinned_at: 4449d3e
resume_command: "/kiro-impl fit-ingest [queue: .kiro/queue/2026-07-29-altitude-record-swap-restoration-unpinned.md] Assert the altitude record-swap test's restoration inside the test itself, mirroring the moving-time half"
context:
  - tests/metrics/test_aggregates.py
  - tests/metrics/test_sources.py
  - .kiro/steering/change-protocol.md
blocked_by: []
---

## What

`test_altitude_smoothing_window_is_read_from_its_record` in
`tests/metrics/test_aggregates.py` swaps the citation record's value and
`importlib.reload`s `aggregates`, restoring it in a `finally`. If that
restoration is dropped, the mutated constant leaks into the rest of the run —
and `tests/metrics/test_aggregates.py` stays entirely green. The leak is caught
only by `tests/metrics/test_sources.py::test_moving_and_altitude_constants_match_aggregates_py`,
in a different file, and so only in directory or full-suite runs.

The sibling `test_moving_time_threshold_is_read_from_its_record` had exactly
this shape and was fixed during task 10.1: it now asserts the restored value
inside the test itself, after its `try`/`finally` closes. The altitude half was
not given the same treatment.

## Why it matters

This is a detected leak reported in the wrong place, not an undetected one — so
it is a robustness gap rather than a live defect. But the failure it produces is
maximally confusing: a test in `test_sources.py` reds because of a bug in
`test_aggregates.py`, and only when the two are run together. A session running
the file alone while iterating would see green and conclude the restoration is
unnecessary.

It also depends on a cross-file guard continuing to exist. Task 12.1 ships a
`ConstantGuard` that may reorganize those assertions; if the `test_sources.py`
sync test moves or narrows, this leak becomes invisible entirely.

## Evidence

At `4449d3e`, neutering the `finally` body of the altitude swap test to `pass`:

- `uv run pytest tests/metrics/test_aggregates.py` → **42 passed** (green)
- `uv run pytest tests/metrics/` → reds only
  `tests/metrics/test_sources.py::test_moving_and_altitude_constants_match_aggregates_py`

The same mutation applied to the moving-time swap test reds *within its own
file*, and reds even when that single test is selected alone — the property
task 10.1's review round 3 required and confirmed.

Reported by the task 10.1 reviewer subagent with the commands above; the
asymmetry between the two halves is visible in the source without running
anything.

## How to pick it up

1. Open `tests/metrics/test_aggregates.py` and read
   `test_moving_time_threshold_is_read_from_its_record` — the fixed shape is the
   assertion placed after the `try`/`finally` block closes, comparing the module
   constant against the record's original value.
2. Apply the same assertion to the altitude swap test. Do **not** add a separate
   test that checks restoration: that formulation was tried during task 10.1 and
   rejected, because it passes vacuously when selected alone and goes green when
   a neighbouring test is reordered ahead of it.
3. Verify by mutation: neuter the `finally` body and confirm the altitude test
   itself reds, including when selected entirely alone. Revert and confirm green.
   That single-test-alone run is the acceptance evidence.

## Open questions

An autouse teardown fixture asserting every reloaded module constant still
matches its record would cover both halves and any future swap test. That is a
larger change than this item needs and interacts with task 12.1's guard; the
picking-up session should take the local fix unless 12.1 has already landed.
