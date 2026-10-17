---
id: 2026-10-18-hr-derivation-5-3-run-not-recorded
title: hr-derivation optional task 5.3* (maintainer data dry run) was run on 2026-10-17 but is not ticked or noted in tasks.md
status: open
importance: low
importance_why: Bookkeeping only; /kiro-spec-status shows an optional task as unrun that was run.
effort: S
kind: chore
area: hr-derivation, .kiro/specs/hr-derivation/tasks.md
created: 2026-10-18
surfaced_by: Phase 12 follow-ups
pinned_at: 0c4b8b5
resume_command: "do: tick hr-derivation 5.3* and append a counts-only Implementation Note (scratch full-corpus copy; ~195-225 s per run; before Amendment 1: 21 max entries, 5 future-dated, 4 future inconsistency periods, 24 resting; after: 0 max with the hand entry, 9 without, 24 resting, 644 not_run_or_bike) [queue: .kiro/queue/2026-10-18-hr-derivation-5-3-run-not-recorded.md]"
context:
  - .kiro/specs/hr-derivation/tasks.md
  - src/fitdocs/hr_benchmarks/sources.py
blocked_by: []
---

## What
Task 5.3* asks for a dry run on a scratch copy of the real data root, with
counts and runtime recorded in Implementation Notes. That was done on
2026-10-17, before and after Amendment 1. The counts are in the resume
command, and the post-amendment counts are also in
`MAX_TIMELINE_CHOICE.measurement`. The task is not ticked and has no note.

## How to pick it up
Tick the task and add the note, in a small chore branch: tasks.md is a spec
file.
