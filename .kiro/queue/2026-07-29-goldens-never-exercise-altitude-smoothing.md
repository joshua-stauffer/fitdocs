---
id: 2026-07-29-goldens-never-exercise-altitude-smoothing
title: No golden fixture reaches the altitude-smoothing path, so the elevation snapshots cannot detect a change to it
status: open
importance: medium
importance_why: The golden suite is the spec's regression evidence for derived metrics, and for elevation it pins the passthrough rather than the derivation — an unchanged snapshot is not evidence nothing moved.
effort: S
kind: gap
area: fit-ingest, tests/golden/, src/fitdocs/metrics/aggregates.py
created: 2026-07-29
surfaced_by: /kiro-impl fit-ingest (task 10.1, review round 1)
pinned_at: c3d2201
resume_command: "/kiro-impl fit-ingest [queue: .kiro/queue/2026-07-29-goldens-never-exercise-altitude-smoothing.md] Add a golden fixture whose elevation is derived from the altitude channel rather than read from session totals"
context:
  - tests/golden/run.json
  - tests/fixtures/
  - src/fitdocs/metrics/aggregates.py
  - .kiro/specs/fit-ingest/tasks.md
blocked_by: []
---

## What

`_smoothed_altitude` and the boxcar window it applies are not reached by any
committed golden snapshot. Three of the four fixtures carry an all-`None`
altitude channel, and the fourth (`run.json`) has altitude samples but also
carries session `total_ascent_m` / `total_descent_m`, which win under the
module's session-summary-first rule — so its reported elevation is the recorded
summary passed through, not the derived value.

## Why it matters

The golden suite is what the spec leans on to show that a change to the metrics
layer moved nothing. For elevation that reassurance is hollow: any change to
the smoothing window, the boxcar alignment, or the gain/loss accumulation would
leave all four snapshots byte-identical.

This already had a concrete consequence. Task 10.1 re-pointed
`_ALTITUDE_SMOOTHING_WINDOW` at its citation record, and the observable was
"elevation gain and loss are identical to before" — which the goldens could not
have falsified. The task was settled instead by a reviewer running 18,000
randomized comparisons against the pre-change module. The same hole is
reachable by any later task in majors 10-13 that touches this path.

## Evidence

At `4449d3e`, over the committed goldens:

```
tests/golden/minimal.json  altitude all-None
tests/golden/ride.json     altitude all-None
tests/golden/run.json      altitude has 10 values
tests/golden/strength.json altitude all-None
```

and in `run.json` the reported values equal the recorded summary exactly:

```
.activity.summary.total_ascent_m    = 9
.activity.summary.total_descent_m   = 0
.metrics_no_athlete.elevation_gain_m  = 9
.metrics_no_athlete.elevation_loss_m  = 0
```

So the derived path is never the thing being snapshotted. Independently
reported by the task 10.1 reviewer, and re-verified here by the commands above.

## How to pick it up

1. Read the fixture builder under `tests/fixtures/` and
   `src/fitdocs/metrics/aggregates.py`'s `_session_or_channel` rule — the
   session value winning is correct behavior and must not be changed to close
   this.
2. Add a fixture (or a variant of an existing one) with a real altitude channel
   and **no** session ascent/descent totals, so the derived path is what the
   snapshot records. Include both a rise and a fall so gain and loss are
   independently pinned, and enough samples that the smoothing window actually
   engages rather than degenerating.
3. Regenerate the goldens and confirm the new file's elevation values differ
   from a naive unsmoothed sum — otherwise the fixture pins the smoothing no
   better than the current ones.
4. Done means: mutating the smoothing window width reds the golden suite. Run
   that mutation and confirm it, per `.kiro/steering/change-protocol.md`
   § Fixture Discrimination — a new fixture that cannot fail is the defect this
   item is about, reproduced.

## Open questions

Whether this lands as its own fixture or as a variant of `run.json` is the
picking-up session's call; a separate fixture avoids disturbing the four
existing snapshots, which several other tasks' observables reference.
