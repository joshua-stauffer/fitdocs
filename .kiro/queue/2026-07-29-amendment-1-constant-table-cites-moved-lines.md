---
id: 2026-07-29-amendment-1-constant-table-cites-moved-lines
title: requirements.md's Amendment 1 constant table cites line numbers that major 10 moves, and one of its descriptions is now false of the code
status: open
importance: low
importance_why: The table is a historical rationale, not a criterion, so nothing depends on it — but it reads as a description of current code and one row is now wrong.
effort: S
kind: docs
area: fit-ingest, .kiro/specs/fit-ingest/requirements.md
created: 2026-07-29
surfaced_by: /kiro-impl fit-ingest (task 10.1, review round 2)
pinned_at: c3d2201
resume_command: "do: Decide whether the Amendment 1 constant table in fit-ingest requirements.md is a historical record or a description of current code, then either date-stamp it or refresh its sites — do not renumber the lines"
context:
  - .kiro/specs/fit-ingest/requirements.md
  - .kiro/specs/fit-ingest/tasks.md
  - src/fitdocs/metrics/aggregates.py
  - .kiro/queue/2026-07-26-line-number-citations-in-tests-go-stale.md
blocked_by: []
---

## What

`.kiro/specs/fit-ingest/requirements.md` carries a table, in the Amendment 1
revision narrative, of the values no published work defines. Two of its three
rows cite `metrics/aggregates.py:103` and `metrics/aggregates.py:238`. Task 10.1
moved both constants — the threshold is now a named constant near `:99` and the
smoothing window near `:260` — and majors 10-13 will move them again.

One row is worse than stale. It describes the moving-time threshold as
"a fitdocs convention, **not even a named constant**". After task 10.1 it *is* a
named constant, `_MOVING_SPEED_THRESHOLD_MPS`, read from its citation record.
That is precisely what task 10.1 was for.

## Why it matters

Low importance and it should stay low: this table is rationale inside a revision
narrative explaining why Amendment 1 was needed. No criterion depends on it, no
test reads it, and amending `requirements.md` reopens requirements approval —
which is a real cost for a prose row.

It matters only because the table does not read as historical. It is written in
the present tense and gives file:line sites, so a session opening it to find the
constants will be sent to the wrong lines and told the threshold is unnamed. The
repo already has an open item about line-number citations going stale in tests
(`2026-07-26-line-number-citations-in-tests-go-stale`); this is the same
mechanism in a spec document.

## Evidence

At `4449d3e`, `.kiro/specs/fit-ingest/requirements.md` rows:

```
| moving-time movement threshold `0.5` | `metrics/aggregates.py:103` | none — a fitdocs convention, not even a named constant |
| altitude-smoothing window `10`       | `metrics/aggregates.py:238` | none — its only cited source is the §2 document 15.5 forbids naming |
```

Current code on `impl/fit-ingest` at `4449d3e`: `aggregates.py:103` is docstring
prose, `_MOVING_SPEED_THRESHOLD_MPS` is defined near `:99` and used near `:125`,
and `_ALTITUDE_SMOOTHING_WINDOW` sits near `:260`. Both are bound to records in
`src/fitdocs/metrics/sources.py`.

## How to pick it up

1. Decide first what the table *is*. If it is a record of the state that
   motivated Amendment 1, the right fix is a date stamp ("as of 2026-07-26,
   before major 10") and dropping the line numbers, which costs nothing and
   makes the tense honest. If it is meant to describe current code, it has to be
   refreshed after every 10.x task, which is not worth it.
2. Do **not** simply renumber the lines. They will move again with tasks 10.2,
   10.3, 11 and 13.1, and a freshly-wrong number is worse than none — the
   constant names are stable and are the better pointer.
3. Check whether amending this narrative trips the requirements-approval gate.
   `spec.json`'s approvals record and the Amendment 1 notes describe what
   counts as a reopening; if it does, that alone may be reason to leave the
   table alone and record the staleness here instead.

## Open questions

Whether touching a revision narrative counts as a requirements change for
approval purposes is a maintainer ruling, and it decides whether this item is a
two-minute edit or not worth doing.
