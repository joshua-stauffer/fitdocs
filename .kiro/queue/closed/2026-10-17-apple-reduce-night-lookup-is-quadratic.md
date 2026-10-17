---
id: 2026-10-17-apple-reduce-night-lookup-is-quadratic
title: Apple Health reducer matches each HRV/respiration/SpO2 reading against every night, so rebuild time grows with nights × readings
status: done
importance: medium
importance_why: Paid twice per import and on every series rebuild any later wellness intake triggers, such as a daily intervals pull; cost grows with history.
effort: S
kind: bug
area: apple-health-import, src/fitdocs/wellness/formats/apple/reduce.py
created: 2026-10-17
surfaced_by: maintainer-requested Phase 12 re-validation (apple-health-import reviewer; loop confirmed by the parent)
pinned_at: 160b007
resume_command: "/kiro-impl apple-health-import [queue: .kiro/queue/2026-10-17-apple-reduce-night-lookup-is-quadratic.md] Replace the per-night reading scan with one global bisect"
context:
  - src/fitdocs/wellness/formats/apple/reduce.py
  - .kiro/specs/apple-health-import/design.md
  - src/fitdocs/wellness/engine.py
blocked_by: []
---

## What
`DayReducer.snapshots()` (`src/fitdocs/wellness/formats/apple/reduce.py:345-354`)
loops `for day, intervals in watch_intervals.items()` for every reading and
bisects inside each night. A reading taken while awake, which is most
daytime SpO2, scans every night before it is discarded. The design
(`design.md:560`) specifies a bisect over the nights' intervals and
estimates a decade rebuild at seconds to tens of seconds (§ Performance).

## Why it matters
The reducer runs when the import commits, again when the series rebuilds
from the extract, and on every later rebuild that any new wellness entry
triggers (`engine.py` `rebuild_series` parses the winning extract each
time). With a daily `fitdocs pull --sync`, every drain pays it.

## Evidence
- The loop shape was confirmed by the parent at 160b007 (lines 345-354).
- The reviewer measured, with 50 readings per day (reported, not re-run by
  the parent): 365 nights 0.51 s, 730 nights 2.11 s, 1,460 nights 8.56 s,
  3,650 nights 56.8 s. Doubling the nights quadruples the time.
- Memory is unaffected; the 400 MB synthetic export peaked at 51.6 MB RSS.

## How to pick it up
1. Build one sorted list of `(start, end, day)` asleep intervals across all
   nights. Intervals are disjoint within a night; check whether they can
   overlap across nights (naps). Bisect once per reading.
2. Add a scaling test, for example asserting that 10× the nights costs well
   under 20× the time, or a call-count guard, plus an equality test of old
   and new means on the existing fixtures.
3. Confirm the extract bytes and series are unchanged (pure refactor; no
   `RULES_VERSION` bump).

## Resolution (2026-10-17)
Fixed on chore/apple-import-hardening: `_NightIndex` sweeps all asleep intervals once (earliest covering night wins, as the old first-match loop did) and each reading is one bisect. Reviewer differential: 2.65M probes, 0 mismatches; 3,650 nights x 30 readings/day 15.25 s -> 0.029 s. The maintainer's real export (3.24 GB export.xml) imported in 56 s. APPROVED.
