---
id: 2026-07-29-task-13-1-undercounts-np-migration-sites
title: Task 13.1's migration-surface note names two NP value sites, and task 10.2 left four
status: open
importance: medium
importance_why: 13.1 is the value-moving unit whose task text exists precisely to stop an implementer meeting an unlisted hard failure; two of the four sites it must move are newer than the note.
effort: S
kind: gap
area: fit-ingest, .kiro/specs/fit-ingest/tasks.md
created: 2026-07-29
surfaced_by: /kiro-impl fit-ingest (task 10.2, review round 1)
pinned_at: 373405a
resume_command: "do: Update fit-ingest tasks.md task 13.1's migration-surface note to name all four exact-value NP sites that task 10.2 left behind, with the recomputed complete-window values"
context:
  - .kiro/specs/fit-ingest/tasks.md
  - tests/metrics/test_power.py
  - src/fitdocs/metrics/power.py
blocked_by: []
---

## What

Task 13.1 ("Emit only complete rolling windows in normalized power") carries a
note naming the migration surface an implementer must move when the value
changes. It names two sites: "the exact-value assertion in the power unit tests"
and "that test's surrounding comment".

Task 10.2 added two more full-precision NP literals to
`tests/metrics/test_power.py`, and both move under complete-windows-only.

## Why it matters

That note exists for a specific reason, recorded in `spec.json`: the independent
task-graph review found 13.1 originally routed all value migration through
snapshots, which is vacuous here — every committed snapshot reports no
normalized power at all, because the fixtures span about 9 seconds. The exact-
value unit assertions *are* the migration surface, so an under-count sends the
implementer into a hard failure with no instruction covering it. That is the
precise failure the note was written to prevent, and it is now under-counting
again.

The task-graph review also established that an unchanged snapshot is not
evidence nothing moved. The same caution applies to the new literals: they are
pinned by `==`, so they will red loudly — but only if the implementer knows to
recompute rather than to assume the old numbers still hold.

## Evidence

At `373405a`, `tests/metrics/test_power.py` contains four exact NP values:

- the pre-existing `261.09384206589294` assertion and its surrounding comment
  (the two sites 13.1 already names);
- `240.8357362432989` at the averaging-exponent swap test — a live `==` pin;
- `255.49899514298704` at the rolling-window swap test — a live `==` pin, added
  by 10.2's Finding-3 fix, replacing a weaker `!=` form.

The task 10.2 reviewer recomputed both under complete-windows-only:
`244.03877169307256` (exponent 4) and `218.64272181950125` (exponent 2). Those
figures are the reviewer's; they were not re-derived when this item was written
and should be recomputed rather than trusted.

Separately, `tests/metrics/test_power.py:190` still describes the algorithm in a
comment as `mean(ra30 ** 4) ** 0.25` — literals the module no longer contains
after 10.2's exponent collapse. 13.1 already owns recomputing that comment; it
is listed here so the sweep is complete.

## How to pick it up

1. Open `.kiro/specs/fit-ingest/tasks.md` task 13.1 and read the existing
   migration-surface note — the shape to follow is already there.
2. Add the two new sites by test name, not by line number (line numbers in this
   spec have gone stale repeatedly; a separate item tracks that).
3. State that the values must be RECOMPUTED under complete-windows-only, and do
   not paste the figures above as authoritative — an implementer that copies an
   unverified number reproduces the transcription hazard the 9.x tasks were
   rejected for.
4. Keep the note's existing warning that the snapshots are vacuous for NP; this
   addition does not replace it.

## Open questions

None. This is a task-text correction, in a task that has not started.
