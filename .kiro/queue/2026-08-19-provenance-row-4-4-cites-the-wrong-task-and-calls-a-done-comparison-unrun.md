---
id: 2026-08-19-provenance-row-4-4-cites-the-wrong-task-and-calls-a-done-comparison-unrun
title: The provenance record's row 4.4 defers to a task that does not own the work, and calls a completed comparison unrun
status: open
importance: medium
importance_why: The classification table is the durable public record of what this purge did and did not verify; a row deferring to unrun work that has in fact already run understates the evidence and points a reader at the wrong task.
effort: S
kind: inconsistency
area: encumbered-content-purge, docs/reference/history-rewrites.md
created: 2026-08-19
surfaced_by: /kiro-impl encumbered-content-purge (task 7.8 classification; implementer flagged it as out of its Req 6-10/12 boundary, parent measured it)
pinned_at: 831aa5c
resume_command: "do: re-measure Req 4.4's classification against task 6.2's completed spec-status comparison and correct the row, checking the other Req 1-5 rows for the same class of staleness"
context:
  - docs/reference/history-rewrites.md
  - .kiro/specs/encumbered-content-purge/tasks.md
blocked_by: []
---

## What

`docs/reference/history-rewrites.md`'s classification table, row 4.4, reads:

    | 4.4 | UNPINNED | `tests/purge/test_manifest.py` pins the *capture* of the
    spec-status baseline, not a before/after comparison -- that comparison is
    task 8.3's, unrun |

Two things in that deferral are false against the current tree.

1. **Task 8.3 does not own the comparison.** In the current plan, task 8.3 is
   "Verify the replaced repository by inspection, and treat any red as
   swap-back". The `training-load` spec-status comparison belongs to **task
   6.2**, whose text says: "Compare the `training-load` spec-status report
   against the baseline captured in task 1: the same requirement and criterion
   counts, the same completed..."
2. **It is not unrun.** Task 6.2 is checked `[x]` in `tasks.md` — it is the
   task that validated the tree work and landed it on `main`.

So a row that defers to future work is deferring to work that has already
happened, under a task number that never owned it. The classification may well
be wrong as a result: if 6.2 actually performed a field-for-field comparison,
Req 4.4 may be PRESERVED-ONLY or PINNED rather than UNPINNED.

## Why it matters

This table is the durable, tracked record of exactly which criteria this purge
verified and which it did not — the document that outlives the spec and that a
future reader consults instead of re-deriving. Its own preamble commits to
PINNED rows naming a mutation and UNPINNED rows being declared deliberately. A
row that defers to the wrong task, and calls completed work unrun, fails that
standard in the direction of understating what was verified.

The row number citation is also a stale-task-number instance of exactly the
class task 7.8 was written to sweep — but 7.8's scope is Requirements 6 through
10 and 12, so row 4.4 was correctly left alone by that task rather than fixed
opportunistically outside its boundary.

## Evidence

Measured at `831aa5c`:

- `grep -n "spec-status" .kiro/specs/encumbered-content-purge/tasks.md` puts the
  comparison obligation in task 6.2's body (and the baseline capture in task 1).
- `grep -n "^- \[.\] 8\.3" tasks.md` → task 8.3 is the post-swap inspection task.
- `grep -n "^- \[.\] 6\.2" tasks.md` → `- [x] 6.2 Validate the tree work and land
  it on main`.

## How to pick it up

Read what task 6.2 actually performed and recorded, then re-classify Req 4.4 on
that evidence — PINNED with a named test and mutation, PRESERVED-ONLY after
watching the named test red, or UNPINNED with the mutation that proves it, per
the section's own standard. Correct the task citation either way.

While there: sweep the Req 1–5 rows for the same class. They were written by
task 6.1 before Amendment 1 regenerated Majors 7–9, so any row deferring to a
task number in that range is suspect. Task 7.8 swept Reqs 6–10 and 12 only.
