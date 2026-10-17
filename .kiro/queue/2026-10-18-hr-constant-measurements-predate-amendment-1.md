---
id: 2026-10-18-hr-constant-measurements-predate-amendment-1
title: Two heart-rate constant measurements still describe the pre-Amendment-1 rule
status: open
importance: low
importance_why: Citation-record prose only; no value or behaviour is wrong, but the records misstate what was measured under the shipped rule.
effort: S
kind: inconsistency
area: hr-derivation, src/fitdocs/hr_benchmarks/sources.py
created: 2026-10-18
surfaced_by: Phase 12 follow-ups, hr-derivation Amendment 1 review (non-blocking)
pinned_at: 0c4b8b5
resume_command: "do: re-measure MAX_RECENCY_CHOICE (365 vs 730 days under rises-only, run/bike only) and MAX_SUSTAINED_PEAK_CHOICE (sessions with a peak, run/bike only) on a scratch copy of the maintainer's data root and update their measurement strings, counts only [queue: .kiro/queue/2026-10-18-hr-constant-measurements-predate-amendment-1.md]"
context:
  - src/fitdocs/hr_benchmarks/sources.py
  - .kiro/specs/hr-derivation/requirements.md
blocked_by: []
---

## What
`MAX_RECENCY_CHOICE.measurement` ("730 days changed the entry count by one")
and `MAX_SUSTAINED_PEAK_CHOICE.measurement` (2,371 sessions with a peak, every
sport) were measured before Amendment 1. Amendment 1 made the maximum
rises-only and limited it to run and bike, and on the maintainer's data it
excludes 644 sessions. `MAX_TIMELINE_CHOICE` was re-measured; these two were
not.

## Why it matters
The citation records are the published reference for each constant's
justification. Stale measurements describe a rule that no longer ships.

## Evidence
`src/fitdocs/hr_benchmarks/sources.py` at 0c4b8b5. The hr-max-ruling reviewer
flagged both as non-blocking.

## How to pick it up
Run the two comparisons on a scratch copy (a `git archive` snapshot of main)
and replace the two measurement strings with counts only.
