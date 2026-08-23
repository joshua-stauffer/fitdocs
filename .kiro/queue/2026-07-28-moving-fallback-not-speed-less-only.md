---
id: 2026-07-28-moving-fallback-not-speed-less-only
title: The moving-time distance fallback fires for present-but-slow speed samples, not only speed-less channels
status: open
importance: medium
importance_why: A stationary sample with drifting GPS distance is counted as moving, which is the noise the 0.5 m/s threshold exists to reject; moving_time_s is reported in every document.
effort: S
kind: inconsistency
area: fit-ingest, src/fitdocs/metrics/aggregates.py
created: 2026-07-28
surfaced_by: /kiro-impl fit-ingest (task 9.2, round-3 reviewer)
pinned_at: c3d2201
resume_command: "/kiro-impl fit-ingest 10.1 [queue: .kiro/queue/2026-07-28-moving-fallback-not-speed-less-only.md] Reconcile the moving-time distance fallback's scope with MOVING_THRESHOLD_CHOICE's stated rationale"
context:
  - src/fitdocs/metrics/aggregates.py
  - src/fitdocs/metrics/sources.py
  - .kiro/specs/fit-ingest/requirements.md
  - .kiro/specs/fit-ingest/design.md
blocked_by: []
---

## What

`MOVING_THRESHOLD_CHOICE.justification` (landed in task 9.2) describes the
cumulative-distance fallback as applying "for a speed-less channel" — i.e. as
the substitute rule when no speed stream exists. The code applies it whenever
the *speed test fails*, which includes a sample whose speed is present and at
or below 0.5 m/s. So a standing-still sample that carries a real speed reading
of 0.1 m/s is still counted as moving if the distance channel ticked up between
it and the next sample.

That is in tension with the record's own rationale for the threshold — that it
"keeps brief stationary noise from being counted as movement" — because GPS
distance drift at a standstill is exactly the noise it names. Either the code's
scope is wrong or the record's wording is; this item is to decide which, not to
assume.

Note that Req 7.1 itself says only "session timer, else threshold +
distance-increase fallback", with no speed-less qualifier — so the requirement
arguably licenses the current code and the *record* is the thing that drifted.
That reading should be checked first, since it is the cheaper fix and does not
move any reported value.

## Why it matters

`moving_time_s` appears in every generated workout document. If the fallback is
over-broad, moving time is inflated for any activity with a speed channel and a
noisy distance channel — stop-and-go city rides, treadmill runs with GPS
drift — and the inflation is silent. If instead the record's wording is the
error, then a provenance record that Amendment 1 exists to make trustworthy is
describing behavior the code does not have, which is the defect class that
rejected task 9.2 three times.

## Evidence

`src/fitdocs/metrics/aggregates.py:101-107`, at `03221ca`:

```python
s = speed[i]
moving = s is not None and s > 0.5
if not moving:
    d0 = distance[i]
    d1 = distance[i + 1]
    moving = d0 is not None and d1 is not None and d1 > d0
```

`if not moving:` is entered both when `s is None` (speed-less channel, the case
the record describes) and when `s <= 0.5` (speed present but below threshold,
the case it does not).

Against `src/fitdocs/metrics/sources.py:200-202`, same commit:

> "treating a sample above it (or a cumulative-distance increase across the
> pair, for a speed-less channel) as 'moving' …"

Req 7.1 (`.kiro/specs/fit-ingest/requirements.md`) states the fallback without
the speed-less qualifier.

Reported by the task-9.2 round-3 reviewer subagent; the `file:line` reading and
the branch analysis above were independently confirmed in this session.

## How to pick it up

1. Read `src/fitdocs/metrics/aggregates.py:95-110` and Req 7.1 in
   `.kiro/specs/fit-ingest/requirements.md`. Decide which of the two is
   authoritative for the fallback's scope. Req 7.1's silence on the qualifier
   is the strongest evidence available, so the likely answer is that the code
   is correct and `MOVING_THRESHOLD_CHOICE`'s parenthetical needs rewording.
2. If the record is what changes: edit the clause in
   `src/fitdocs/metrics/sources.py` **and** its whole-value backstop
   `BACKSTOP_MOVING_THRESHOLD_JUSTIFICATION` in `tests/metrics/test_sources.py`
   in lockstep — retype the backstop by hand, never copy it out of the module,
   or it pins nothing. Re-run the mutation for that clause.
3. If the code is what changes: this moves a reported value, so it needs a
   golden-snapshot regeneration and belongs in task 10.1's value-moving lane
   rather than a drive-by edit. Add a test with a fixture whose speed is present
   and below threshold while distance increases — no such fixture exists today,
   which is why nothing caught this.

Done means: the record's description and the code's behavior agree, one test
distinguishes the present-but-slow case from the speed-less case, and a
mutation proves that test can fail.
