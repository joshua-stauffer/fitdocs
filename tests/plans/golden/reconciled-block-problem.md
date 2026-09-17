---
title: "Reconcile fixture block"
type: "training-block"
generator: "fitdocs"
block_version: 1
block: "reconcile-fixture"
starts: "2026-02-02"
ends: "2026-03-01"
goal: "A block built to exercise every reconciliation grammar row."
mesocycle_days: 7
---

<!-- fitdocs:generated: everything outside the notes/workout/load regions is replaced on regeneration -- see this directory's AGENTS.md -->

# Reconcile fixture block

<!-- fitdocs:begin:notes -->
_Your notes go here. This section is preserved when the document is regenerated._
<!-- fitdocs:end:notes -->

Starts: 2026-02-02

Ends: 2026-03-01 (28 days)

Mesocycle length: 7 days (4 mesocycles; the last is 7 days)

### Goal

A block built to exercise every reconciliation grammar row.

## Mesocycle 1 -- 2026-02-02 to 2026-02-08 (7 days)

Focus: Base

Target load: 300

Actual load: not computed -- no methodology chosen (see Resolution below).

| Day | Sport | Planned | Summary | Resolution |
|---|---|---|---|---|
| Mon 2026-02-02 | Run | [Easy aerobic run](reconcile-fixture/w1-mon.md) | Zone 2 | matched: [w1-mon-log](../workouts/w1-mon-log.md) |
| Tue 2026-02-03 | Ride | [Endurance ride](reconcile-fixture/w1-tue.md) | Zone 2 spin | matched (absorbed 3): [w1-tue-log-a](../workouts/w1-tue-log-a.md), [w1-tue-log-b](../workouts/w1-tue-log-b.md), [w1-tue-log-c](../workouts/w1-tue-log-c.md) |
| Wed 2026-02-04 | Run | [Recovery run](reconcile-fixture/w1-wed-run.md) | Easy shakeout | not logged |
| Wed 2026-02-04 | Ride | [Recovery spin](reconcile-fixture/w1-wed-ride.md) | Easy spin | matched: [w1-wed-ride-log](../workouts/w1-wed-ride-log.md) |
| Thu 2026-02-05 | | _rest_ | | |
| Fri 2026-02-06 | Run | [Tempo run A](reconcile-fixture/w1-fri-a.md) | Threshold work | matched (ambiguous): [w1-fri-log](../workouts/w1-fri-log.md) |
| Fri 2026-02-06 | Run | [Tempo run B](reconcile-fixture/w1-fri-b.md) | Threshold work, alternate | not logged |
| Sat 2026-02-07 | | _rest_ | | |
| Sun 2026-02-08 | | _rest_ | | |

## Mesocycle 2 -- 2026-02-09 to 2026-02-15 (7 days)

Focus: Build

Target load: 250

Actual load: not computed -- no methodology chosen (see Resolution below).

| Day | Sport | Planned | Summary | Resolution |
|---|---|---|---|---|
| Mon 2026-02-09 | Run | [Planned long run](reconcile-fixture/w2-mon.md) | Long steady run | overridden: [w2-existing-log](../workouts/w2-existing-log.md), `w2-missing-log` (not found) |
| Tue 2026-02-10 | Run | [Planned intervals](reconcile-fixture/w2-tue.md) | Speed work | skipped |
| Wed 2026-02-11 | Run | [Easy run](reconcile-fixture/w2-wed.md) | Zone 2 | matched: [w2-unscored-log](../workouts/w2-unscored-log.md) |
| Thu 2026-02-12 | Run | [Easy run](reconcile-fixture/w2-thu.md) | Zone 2 | matched: [w2-excluded-log](../workouts/w2-excluded-log.md) |
| Fri 2026-02-13 | | _rest_ | | |
| Sat 2026-02-14 | | _rest_ | | |
| Sun 2026-02-15 | | _rest_ | | |

## Mesocycle 3 -- 2026-02-16 to 2026-02-22 (7 days)

Target load: none

Actual load: not computed -- no methodology chosen (see Resolution below).

| Day | Sport | Planned | Summary | Resolution |
|---|---|---|---|---|
| Mon 2026-02-16 | | _rest_ | | |
| Tue 2026-02-17 | | _rest_ | | |
| Wed 2026-02-18 | | _rest_ | | |
| Thu 2026-02-19 | | _rest_ | | |
| Fri 2026-02-20 | | _rest_ | | |
| Sat 2026-02-21 | | _rest_ | | |
| Sun 2026-02-22 | | _rest_ | | |

Unplanned: 2 logged workouts in this window match no planned workout.
- [m3-unscored-a](../workouts/m3-unscored-a.md) -- 2026-02-18, Run, unscored
- [m3-unscored-b](../workouts/m3-unscored-b.md) -- 2026-02-19, Run, unscored

## Mesocycle 4 -- 2026-02-23 to 2026-03-01 (7 days)

Target load: none

Actual load: not computed -- no methodology chosen (see Resolution below).

| Day | Sport | Planned | Summary | Resolution |
|---|---|---|---|---|
| Mon 2026-02-23 | | _rest_ | | |
| Tue 2026-02-24 | | _rest_ | | |
| Wed 2026-02-25 | | _rest_ | | |
| Thu 2026-02-26 | Run | [Future tempo run](reconcile-fixture/w4-thu.md) | Threshold work | upcoming |
| Fri 2026-02-27 | | _rest_ | | |
| Sat 2026-02-28 | | _rest_ | | |
| Sun 2026-03-01 | | _rest_ | | |

Unplanned: 1 logged workout in this window matches no planned workout.
- [m4-unplanned-log](../workouts/m4-unplanned-log.md) -- 2026-02-28, Ride, load 60

## Resolution

Planned workouts: 11 -- 6 matched (1 ambiguous), 1 overridden, 1 skipped, 2 not logged, 1 upcoming.
Methodology: none chosen -- the archive records more than one methodology and none was requested or configured: 'banister' (1 pages), 'threshold' (7 pages). Pass --methodology, or set [history].methodology or [load].default_calculator, to choose one.
Ambiguous: `w1-fri-a` -- settle them with override entries.
Problems:
- override[0] (id w2-mon): stem `w2-missing-log` not found among the logged workouts

## Revision record

### As first written

| Id | Date | Sport | Title | Summary |
|---|---|---|---|---|
| w1-mon | 2026-02-02 | Run | Easy aerobic run | Zone 2 |
| w1-tue | 2026-02-03 | Ride | Endurance ride | Zone 2 spin |
| w1-wed-run | 2026-02-04 | Run | Recovery run | Easy shakeout |
| w1-wed-ride | 2026-02-04 | Ride | Recovery spin | Easy spin |
| w1-fri-a | 2026-02-06 | Run | Tempo run A | Threshold work |
| w1-fri-b | 2026-02-06 | Run | Tempo run B | Threshold work, alternate |
| w2-mon | 2026-02-09 | Run | Planned long run | Long steady run |
| w2-tue | 2026-02-10 | Run | Planned intervals | Speed work |
| w2-wed | 2026-02-11 | Run | Easy run | Zone 2 |
| w2-thu | 2026-02-12 | Run | Easy run | Zone 2 |
| w4-thu | 2026-02-26 | Run | Future tempo run | Threshold work |

Mesocycle targets as first written: 1: 300 (Base); 2: 250 (Build); 3: none; 4: none

No amendments.
