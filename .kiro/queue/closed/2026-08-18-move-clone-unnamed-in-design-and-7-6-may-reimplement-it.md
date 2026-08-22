---
id: 2026-08-18-move-clone-unnamed-in-design-and-7-6-may-reimplement-it
title: move_clone is the one adopt.py function design.md never names, and 7.6 may reimplement its guard
status: closed
importance: medium
importance_why: Task 7.6 could land a driver that duplicates the refuse-if-target-exists guard, giving two divergent implementations of the swap's safety check.
effort: S
kind: inconsistency
area: encumbered-content-purge, scripts/purge/adopt.py, .kiro/specs/encumbered-content-purge/design.md
created: 2026-08-18
surfaced_by: /kiro-impl encumbered-content-purge (task 7.3 review)
pinned_at: 0a6535d
resume_command: "do: decide whether task 7.6's replacement driver calls adopt.move_clone for the fresh-.git move or implements the move itself, and state the answer in design.md's HistoryReplacement step 7 before 7.6 is implemented"
context:
  - scripts/purge/adopt.py
  - .kiro/specs/encumbered-content-purge/design.md
  - .kiro/specs/encumbered-content-purge/tasks.md
blocked_by: []
---

## What

`design.md` › `#### HistoryReplacement` names three of `adopt.py`'s four public
functions in its ordering block -- `assert_commit_identity` at step 3,
`assert_carry_over` and the checklist build at step 6. `move_clone` is never
named. Step 7 states where its *operation* sits ("the fresh `.git` is moved
into its place") without saying which helper performs it.

Meanwhile `adopt.py` itself says the swap's two directory moves "are
deliberately kept out of this module, orchestrated by the replacement driver".

## Why it matters

`move_clone` already carries a non-obvious safety guard: it refuses when
`target` exists, because `shutil.move` would otherwise **nest** the source
inside the existing target directory rather than replacing it -- neither
raising nor doing what the caller meant. A 7.6 driver that implements the move
itself is likely to miss that, and the repository would then hold two
divergent notions of what the swap's safety check is.

The swap is a one-shot, irreversible step. Two implementations of its guard is
one too many.

## Evidence

Reported by the task 7.3 reviewer, which verified the nesting behaviour by
execution: `shutil.move` on an existing-directory destination creates `b/a/x`,
and `move_clone` raises `AdoptionError` instead.

Confirmed at `0a6535d`: `design.md:1450` is `#### HistoryReplacement`, its
ordering block at `:1491`, step 7 at `:1542`; `grep` for `move_clone` in
`design.md` returns nothing. `adopt.py`'s "kept out of this module" statement
is in the module docstring.

## How to pick it up

Read `design.md` › `HistoryReplacement` step 7 and task 7.6's driver bullet in
`tasks.md`. Decide: either 7.6 calls `adopt.move_clone` for the fresh-`.git`
move (and step 7 says so), or the driver owns the move and the design states
which guard it must carry. Done when the answer is written down before 7.6 is
implemented, not after.

## Closed by task 7.6

`scripts/purge/replace.py::run_replace` calls `adopt.move_clone` directly for
both swap moves (`adopt.move_clone(old_git_dir, archive_dir)` then
`adopt.move_clone(scratch_clone_dir / ".git", repo_root / ".git")`), reusing
the refuse-if-target-exists guard rather than reimplementing it. See
`run_replace`'s own module docstring and the task 7.6 status report for the
decision record.

**Amendment (7.6 remediation, controller ruling):** the item's own stated
done-condition was narrower than the paragraph above -- "the answer is
written down in design.md's HistoryReplacement step 7 before 7.6 is
implemented", not merely resolved in code. `grep -n move_clone
.kiro/specs/encumbered-content-purge/design.md` still returns nothing at this
remediation's tip: design.md step 7 was never amended to name `move_clone`.
The two-divergent-implementations risk this item exists to prevent is
genuinely closed (one call site per move, one guard, reused unchanged, not
reimplemented) -- but on code-review terms, not on the item's own stated
terms. A later reader should not infer from this closure that design.md was
updated; it was not.
