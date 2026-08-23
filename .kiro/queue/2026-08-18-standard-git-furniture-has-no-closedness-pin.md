---
id: 2026-08-18-standard-git-furniture-has-no-closedness-pin
title: Adding an entry to _STANDARD_GIT_FURNITURE silently suppresses the carry-over halt
status: open
importance: high
importance_why: The halt is the one thing standing between an unanticipated .git entry and silent loss during the one-shot replacement, and its exclusion list is unpinned.
effort: S
kind: gap
area: encumbered-content-purge, scripts/purge/adopt.py
created: 2026-08-18
surfaced_by: /kiro-impl encumbered-content-purge (task 7.3 review)
pinned_at: c3d2201
resume_command: "do: pin _STANDARD_GIT_FURNITURE's closed-ness in tests/purge/test_adopt.py the way _PINNED_ATTRS is pinned -- as a symmetric difference, so a spurious addition reds -- before Major 8 runs the halt for real"
context:
  - scripts/purge/adopt.py
  - tests/purge/test_adopt.py
blocked_by: []
---

## What

`build_checklist` halts on any `.git`-resident entry that is neither the agent
log nor a member of `_STANDARD_GIT_FURNITURE` nor `lost-found`. The furniture
set has **no closed-ness pin**: adding an entry to it silently suppresses a
halt, and no test notices.

## Why it matters

The halt exists because silence is the failure mode. An entry quietly added to
the exclusion set converts an unanticipated `.git` resident into exactly the
silent skip the enumeration was built to abolish -- and it would do so during
a one-shot, irreversible operation.

The contrast is instructive and the fix is already in the same file:
`_PINNED_ATTRS` is pinned as a **symmetric difference**, so a spurious addition
reds just as a removal does. `_STANDARD_GIT_FURNITURE` has no equivalent.

## Evidence

Reported by the task 7.3 reviewer, which verified the asymmetry directly:
adding a spurious `"rmtree"` to `_PINNED_ATTRS` or `"eval"` to
`_PINNED_FREE_NAMES` reds `test_module_source_contains_no_directory_removal_call`;
nothing comparable guards the furniture set.

Confirmed present at `0a6535d`: `_STANDARD_GIT_FURNITURE` is defined in
`scripts/purge/adopt.py` and consumed by `build_checklist`'s foreign-entry
filter. Its measured contents were independently reproduced by the reviewer
against a fresh `git init` + commit + `gc` (`COMMIT_EDITMSG config description
HEAD hooks index info logs objects packed-refs refs`, with the primary `.git`
additionally carrying `ORIG_HEAD FETCH_HEAD worktrees`).

## How to pick it up

Open `tests/purge/test_adopt.py` and find the `_PINNED_ATTRS` symmetric-difference
assertion. Write the same shape for `_STANDARD_GIT_FURNITURE`. Verify by adding a
plausible entry (`"modules"`, say) and watching it red, then removing a real one
and watching it red too. Done when both directions fail.
