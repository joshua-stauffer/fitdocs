---
id: 2026-08-18-task-7-7-inherits-the-porcelain-trap
title: 7.7's rehearsal must assert empty porcelain and observe the surviving untracked symlink, which cannot both hold
status: open
importance: high
importance_why: The next task to run carries the exact false-red 7.4 removed for the real repository, and it would present as a failed rehearsal of a correct swap.
effort: S
kind: inconsistency
area: encumbered-content-purge, .kiro/specs/encumbered-content-purge/tasks.md
created: 2026-08-18
surfaced_by: /kiro-impl encumbered-content-purge (task 7.4 review)
pinned_at: c3d2201
resume_command: "do: decide whether task 7.7's rehearsal asserts a tracked-files-scoped porcelain or omits the root symlink from the scratch working tree, before 7.7 is implemented"
context:
  - .kiro/specs/encumbered-content-purge/tasks.md
  - .kiro/specs/encumbered-content-purge/design.md
blocked_by: []
---

## What

Task 7.7 requires the rehearsal to assert **"empty porcelain status"** among its
post-swap results. `design.md` › `HistoryReplacement` (Decision 7, point 4)
separately says the root `agent-log` symlink "survives the swap unchanged and
resolves again the moment the log is present in the new `.git` at the same
relative path -- **that is an observable, not an assumption**."

Both cannot hold in one rehearsal. A root symlink planted in the scratch
working tree so that its resolution can be observed is untracked, matched by no
ignore rule, and therefore makes a bare `git status --porcelain` return
`?? agent-log`.

## Why it matters

This is precisely the defect task 7.4's declared correction removed for the
real repository: a bare porcelain check is a **guaranteed swap-back trigger**
on a correct replacement. 7.7 is the rehearsal that exists to exercise the
recovery path before it is needed; a rehearsal that reds by construction
teaches the operator the wrong thing about a one-shot operation.

7.4 could not fix this — `tasks.md` is outside its boundary, and the reviewer
correctly ruled the fourth `design.md` porcelain sentence exempt because the
*carry-over* fixture is `.git`-resident and leaves the scratch working tree
tracked-clean. The trap only appears if 7.7 additionally plants the root
symlink to observe the resolution property.

## Evidence

Measured at `b7c5a3d`:

- `tasks.md` task 7.7: "swap, and assert on the result -- tree identity with
  the source tree, **empty porcelain status**, exactly one reachable commit …
  and the carried fixture present at its destination"
- `design.md` › HistoryReplacement, Decision 7 point 4: "The root `agent-log`
  symlink in the working tree survives the swap unchanged and resolves again
  … that is an observable, not an assumption."
- In the primary repository the property is already demonstrated:
  `agent-log -> .git/agent-log`; `git ls-files --error-unmatch agent-log`
  fails; `git check-ignore -v agent-log` is silent;
  `git status --porcelain --untracked-files=all` → `?? agent-log`;
  `git status --porcelain --untracked-files=no` → empty.

## How to pick it up

Two coherent resolutions, and the first is probably right. (a) The rehearsal
asserts a **tracked-files-scoped** porcelain, matching 7.4's correction, and
plants the root symlink so the resolution observable is genuinely exercised.
(b) The rehearsal carries only the `.git`-resident log, keeps the bare
porcelain assertion, and the symlink-resolution observable is checked at 8.2
against the real repository instead.

Done when 7.7's implementer is given the answer rather than discovering the
contradiction mid-task.
