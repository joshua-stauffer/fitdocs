---
id: 2026-08-09-major-7-checkboxes-have-no-owning-task
title: No task instructs ticking Major 7's checkboxes, so after adoption the only record that 7.1 ran is the agent log
status: open
importance: low
importance_why: Cosmetic while the agent log survives, but tasks.md is the spec's own progress record and it will read as though Major 7 never started, which misleads the next session at exactly the point the repository is least recoverable.
effort: S
kind: gap
area: encumbered-content-purge, .kiro/specs/encumbered-content-purge/tasks.md
created: 2026-08-09
surfaced_by: reviewer subagent during /kiro-impl encumbered-content-purge (review of the artifact reconstruction and task 7.1)
pinned_at: 8391e47
resume_command: "do: Decide where Major 7's checkboxes get ticked. They cannot be committed during 7.1-7.3 (a commit then is carried into the 7.2 clone mid-rewrite) and task 8.3 never mentions checkboxes, so add the instruction to 8.3 or to a successor task."
context:
  - .kiro/specs/encumbered-content-purge/tasks.md
blocked_by: []
---

## What

Task 7.1 is complete — the quiescence gate ran, the abandonment was recorded
naming both branches, and no backup ref exists — but `tasks.md:955` still shows
`- [ ] 7.1` with a clean worktree.

That was deliberate: a commit during 7.1-7.3 would be carried into the clone
that 7.2 rewrites, so the checkbox updates were deferred to the post-rewrite
commit. The problem is that task 8.3, where they were deferred to, never
mentions checkboxes at all (`tasks.md:1117-1152`).

## Why it matters

Nothing owns the update, so by default it does not happen. After 7.4 adopts the
clone and destroys the old repository, `tasks.md` will show all of Major 7
unstarted while the work is done and unrepeatable. A session reading the spec's
own progress record at that moment would conclude the rewrite had not run.

The agent log does carry it, but the log is the coordination channel, not the
spec's progress record, and the two disagreeing is the failure mode.

## Evidence

- `.kiro/specs/encumbered-content-purge/tasks.md:955` — still `- [ ] 7.1`
- `.kiro/specs/encumbered-content-purge/tasks.md:1117-1152` — task 8.3 never
  mentions checkboxes
- the shared agent log, session `impl-purge-7`, records 7.1 complete and
  records the deferral and its reason

## How to pick it up

Add an explicit instruction to 8.3 (or a successor) to tick every Major 7
checkbox in the post-rewrite commit, and state the reason they could not be
ticked earlier so the next reader does not "fix" it by committing mid-rewrite.

Done when some task owns the update.
