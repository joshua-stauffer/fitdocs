---
id: 2026-07-29-task-8-3-points-at-a-closed-queue-item
title: fit-ingest task 8.3 cites a now-closed queue item as the live flag for the still-open TrimpWeighting naming decision
status: open
importance: low
importance_why: The decision is still open and still flagged in spec.json and design.md, but the pointer a reader is most likely to follow now resolves to closed/ and reads as settled.
effort: S
kind: docs
area: fit-ingest, .kiro/specs/fit-ingest/tasks.md
created: 2026-07-29
surfaced_by: /kiro-impl fit-ingest (task 10.1 run, peer session queue-top7 closed the item mid-run)
pinned_at: 4449d3e
resume_command: "do: Repoint fit-ingest tasks.md task 8.3 at spec.json's design_revision_open_decisions as the live flag for the TrimpWeighting member naming, since the queue item it names is now closed"
context:
  - .kiro/specs/fit-ingest/tasks.md
  - .kiro/specs/fit-ingest/spec.json
  - .kiro/specs/fit-ingest/design.md
  - .kiro/queue/closed/2026-07-27-trimp-weighting-default-is-sex-named.md
blocked_by: []
---

## What

`.kiro/specs/fit-ingest/tasks.md:149` (task 8.3) says the `TrimpWeighting`
member names "are flagged in `spec.json`'s open-decisions record and in
`.kiro/queue/2026-07-27-trimp-weighting-default-is-sex-named.md`".

That queue item was closed on 2026-07-29 and now lives in
`.kiro/queue/closed/`. The path in `tasks.md` no longer resolves.

## Why it matters

The decision itself is **not** settled, and the distinction is the point of this
item. The queue item's *ask* was discharged — `design.md` now names the members,
states that `DEFAULT_TRIMP_WEIGHTING` is `BANISTER_MALE` as a consequence of
Req 17.2 rather than a preference, and records the sex-neutral application in
`DEPARTURES`. But the naming decision is still flagged for the maintainer, in
`design.md:1109-1110` and in `spec.json`'s `design_revision_open_decisions`,
and Req 17.6 puts that name in every rendered document.

So a reader following the `tasks.md` pointer finds a file marked `status: done`
in `closed/` and can reasonably conclude the naming is ratified. It is not. Any
downstream work that then pins behavior to the member *name* rather than to the
value `(0.64, 1.92)` would be silently weakened by a later rename — which is
exactly what task 8.3's own sentence, and task 11's value-pinned regression,
exist to prevent.

## Evidence

- `.kiro/specs/fit-ingest/tasks.md:149` names the queue path.
- The file is at `.kiro/queue/closed/2026-07-27-trimp-weighting-default-is-sex-named.md`
  with `status: done`, closed on `main` in `a0ef12a` by peer session
  `queue-top7` (recorded in the shared agent log, 2026-07-29T07:00:24Z and
  07:03:22Z).
- That item's own `## Resolution` says it is resolved by the design revision
  `a6418a7`, and notes `design.md:1109-1110` "flags it for the maintainer as a
  presentation-adjacent choice" — i.e. the flag survives the close.

## How to pick it up

1. Edit `.kiro/specs/fit-ingest/tasks.md:149` to point at
   `spec.json`'s `design_revision_open_decisions` and `design.md:1109-1110`,
   which are the flags that are still live, and drop the queue path.
2. Do not remove the sentence's substance. "Treat a later rename as expected
   rather than as rework; nothing downstream may pin behavior to the name"
   remains correct and is load-bearing for tasks 11 and 12.x.
3. Task 8.3 is already complete and committed, so this is a pointer repair in a
   finished task's text — trivial per `.kiro/steering/change-protocol.md`
   triage, and should be committed as such rather than reopening the task.

## Open questions

None for the edit. The underlying maintainer decision — whether
`BANISTER_MALE` / `BANISTER_FEMALE` are the names an athlete should see in a
rendered document — stays open and is not this item's to make.
