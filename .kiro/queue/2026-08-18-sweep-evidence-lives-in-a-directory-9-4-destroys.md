---
id: 2026-08-18-sweep-evidence-lives-in-a-directory-9-4-destroys
title: Task 7.2's mutation sweep is the only record of its own bound, and 9.4 destroys the directory holding it
status: open
importance: medium
importance_why: The artifact that terminated a task with three rejections is scheduled for deletion; if 7.8 or Req 12.3 needs it as retained evidence, that must be decided before Major 9.
effort: S
kind: gap
area: encumbered-content-purge, docs/reference/history-rewrites.md
created: 2026-08-18
surfaced_by: /kiro-impl encumbered-content-purge (task 7.2)
pinned_at: c3d2201
resume_command: "do: decide whether task 7.2's sweep-7-2-era-signal.md is evidence Req 12.3 retains or scratch 9.4 destroys, and either fold its conclusions into the provenance record or state explicitly that it is scratch"
context:
  - .kiro/specs/encumbered-content-purge/tasks.md
  - docs/reference/history-rewrites.md
blocked_by: []
---

## What

Task 7.2's 25-row mutation sweep lives out of repository at
`sweep-7-2-era-signal.md` in the purge scratch root. Task 9.4 destroys
everything in that directory except the forbidden-string source.

## Why it matters

The sweep exists because the same task was rejected three times, each round
finding new real ground, and the debug pass diagnosed the cause as a sweep
that had been *asserted rather than produced*. Writing it to a file is what
bounded the remainder and terminated the task.

Task 7.8 extends the tracked criterion classification in the provenance
record, and Req 12.3 requires recorded evidence to be retained. If the sweep
is part of either, it cannot live only in a directory scheduled for deletion.
If it is genuinely scratch -- its conclusions already absorbed into the
tests and the commit message -- that is a fine answer, but it should be the
stated one.

## Evidence

Sweep file measured 2026-08-18 at 10,182 bytes, 25 mutation rows plus 3
re-derived population facts. Its verdicts were independently reproduced
25/25 by the task 7.2 reviewer, and one row (`--all` -> `--branches`) was
re-run by the controller: red on the named test, green on revert.

Task 9.4's text: "Destroy everything in the out-of-repository scratch
directory except the forbidden-string source, which is standing guard data
and survives indefinitely".

Task 7.2's commit `dac1a7a` names the sweep by filename and location.

## How to pick it up

Read task 9.4's scratch-disposition bullet and task 7.8's classification
bullet. Decide. If retained, fold the sweep's conclusions -- not its full
table -- into the provenance record, where Req 12.3 keeps them. If scratch,
say so in the record's stated-positions section so a later reader does not
hunt for a deleted file. Done when the disposition is written down.
