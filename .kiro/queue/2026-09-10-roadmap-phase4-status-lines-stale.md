---
id: 2026-09-10-roadmap-phase4-status-lines-stale
title: Roadmap Phase 4 status lines are stale — threshold-load shows [ ] though implemented, load-channels shows "1 of 20" though all 20 are ticked
status: open
importance: low
importance_why: The roadmap is the planning source of truth and /kiro-queue ranks from it; two shipped specs reading as pending misleads the next planning pass, but nothing executes on it.
effort: S
kind: docs
area: .kiro/steering/roadmap.md, threshold-load, load-channels
created: 2026-09-10
surfaced_by: /kiro-spec-batch (Phase 6 finalize step, checking the checkbox convention)
pinned_at: 1251a98
resume_command: "do: under the steering ritual, update roadmap.md Phase 4 — mark threshold-load [x] done 2026-08-29 (merged 09aa9b2, spec.json phase implemented, 18/18 ticked) and bring the load-channels line from '[~] in flight (task 1.1 landed; 1 of 20)' to its real state after checking its merge record in the agent log and whether its spec.json phase should read implemented; leave activity-qa-flags and distribution as they are (0 ticked)"
context:
  - .kiro/steering/roadmap.md
  - .kiro/specs/threshold-load/spec.json
  - .kiro/specs/load-channels/spec.json
  - .kiro/specs/load-channels/tasks.md
blocked_by: []
---

## What
The roadmap's checkbox convention is `[x]` = implemented with a done date,
`[~]` = in flight, `[ ]` = pending. Two Phase 4 lines no longer match the
specs they describe.

## Why it matters
`/kiro-queue` and any planning session read the roadmap's open items. A
completed calculator spec reading as pending, and a finished channels spec
reading as one-twentieth done, both misstate what is left in Phase 4.

## Evidence
- `.kiro/steering/roadmap.md:758` — `- [ ] threshold-load — …` while
  `.kiro/specs/threshold-load/spec.json` has `phase: implemented` and
  `tasks.md` has 18 ticked, 0 unticked; the agent log records the merge to
  `main` at `09aa9b2` on 2026-08-29 and the bookkeeping tail at `be99755`.
- `.kiro/steering/roadmap.md:747` — `- [~] load-channels — **in flight (task
  1.1 landed; 1 of 20 checklist items).**` while
  `.kiro/specs/load-channels/tasks.md` has 20 ticked, 0 unticked and
  `spec.json` still reads `phase: tasks-generated`.
- Agent-log merge lines for load-channels (grep `impl-load-channels` +
  `MERGED`), appended below at the time of writing:
  - `2026-07-25T23:28:29Z	impl-load-channels	MERGED	load-channels task 1.1 -> main (b6e686f), worktree+branch removed. Spec NOT complete: 12 tasks remain, blocked on`
  - `2026-07-31T05:22:25Z	impl-load-channels	MERGED	impl/load-channels -> main --ff-only (e71e008, 3 commits), worktree+branch REMOVED. Validated AFTER rebase onto 1`

## How to pick it up
1. Confirm load-channels' final merge sha from the log and whether a later
   session left its spec.json phase unflipped on purpose.
2. Edit the two roadmap lines in the style of the Phase 3 done lines
   (`**done YYYY-MM-DD** (…)`), on a chore branch, read the Phase 4 section
   end to end afterwards.
3. If load-channels' spec.json should read `implemented`, flip it in the same
   change with a phase_note, as threshold-load's was.
