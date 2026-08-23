---
id: 2026-08-23-classification-appendix-stale-after-majors-8-and-9
title: The record's requirement-classification appendix still says Majors 8 and 9 have not run, while the same document's sections 7 and 8 record them as done
status: open
importance: low
importance_why: Self-contradiction inside one shipped document — the appendix says the remote reconciliation has not run and the retirement is unpinned, while sections 7 and 8 of the same file record both as complete with dated evidence. Low because no decision rests on the appendix, but it is the kind of drift that makes a reader distrust the sections that are correct.
effort: M
kind: inconsistency
area: encumbered-content-purge, docs/reference
created: 2026-08-23
surfaced_by: /kiro-impl encumbered-content-purge tasks 9.3 and 9.4 (both implementers, deliberately out of boundary)
pinned_at: c786326
resume_command: "do: re-run the criterion classification sweep over the whole of requirements.md now that Majors 8 and 9 have landed, and refresh the appendix rows that still say the replacement and retirement have not run"
context:
  - docs/reference/history-rewrites.md
  - .kiro/specs/encumbered-content-purge/requirements.md
  - .kiro/specs/encumbered-content-purge/tasks.md
blocked_by: []
---

## What

`docs/reference/history-rewrites.md`'s "Classification of all 82 requirement
criteria" appendix was written by tasks 6.1 and 7.8, before Majors 8 and 9 ran.
Several rows are now false:

- `8.2` — "Remote reconciliation has not run"
- `8.4`, `8.6` — unrun / part two of the record unwritten
- `12.1`–`12.5` — `UNPINNED ... has not run`
- `4.4` — cites `tests/purge/test_manifest.py`, deleted at task 9.3, and calls
  task 8.3's comparison unrun
- `5.1` — "the history replacement that would make this true has not run"

All of them ran. The replacement landed at task 8.2 (root `c3d2201`), the push
and measurement at 8.4, the retirement at 9.3, the survivor ledger at 9.4.

## Why it matters

Sections 7 and 8 of the *same document* record these as complete with dated
evidence. So the file contradicts itself: a reader who reaches section 7 learns
the remote was reconciled and measured on 2026-08-22, then reaches the appendix
and reads that reconciliation has not run.

Nothing depends on the appendix — no test reads it, no decision rests on it —
which is why this is `low`. But it is the largest remaining internal
inconsistency in the record, and the record's credibility is the deliverable.

The appendix is honest about its own volatility: it declares itself a dated
snapshot and says "re-run this sweep" once Majors 8 and 9 land. This item is
that re-run coming due.

Both the 9.3 and 9.4 implementers spotted it and deliberately left it alone as
outside `MachineryRetirement`'s boundary — the right call, and the reason it
needs its own owner rather than being folded into a task that would have had to
widen its scope to reach it.

## Evidence

```
$ grep -n "has not run\|unrun" docs/reference/history-rewrites.md
170:...(task 9.4, unrun as of ...)
1016:| 4.4 | UNPINNED | `tests/purge/test_manifest.py` ... that comparison is task 8.3's, unrun |
1018:| 5.1 | UNPINNED | ... the history replacement that would make this true has not run |
1038:| 8.2 | UNPINNED | Remote reconciliation has not run |
```

Against: `git rev-list --max-parents=0 HEAD` = `c3d2201`; record sections 7 and
8; `tasks.md` with every one of its 48 sub-tasks `[x]` as of `c786326`.

Rows `7.1` and `7.2` were already corrected in place once before, and their
correction notes are a good model for the tone this refresh should take.

## How to pick it up

This is a full sweep, not a patch — the appendix classifies **every** criterion,
and Majors 8 and 9 moved many of them at once. Re-run the classification the
way tasks 6.1 and 7.8 did rather than editing the rows that happen to contain
"has not run", or you will fix the ones that are grep-visible and leave the
ones that are merely stale.

Note the appendix header says 82 criteria; `requirements.md` is now 12
requirements / 81 criteria after Amendment 1, and Req 9.3 was textually amended
again at task 9.2. Reconcile the count as part of the sweep rather than
assuming either number.

Preserve the existing in-place-correction convention: rows corrected after the
fact carry a note saying so, rather than being silently rewritten. The
historical record of what was true when a task ran is not to be erased.

Done when no row asserts an event has not happened that the same document
records as having happened, and the criterion count matches `requirements.md`.
