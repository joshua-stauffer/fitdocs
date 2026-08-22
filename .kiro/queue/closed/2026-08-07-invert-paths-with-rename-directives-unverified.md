---
id: 2026-08-07-invert-paths-with-rename-directives-unverified
title: Settle whether path inversion deletes the paths it is asked to rename, before the one-shot rewrite runs
status: done
importance: high
importance_why: If a rename line's source path joins the inverted selection set, the queue items are deleted rather than renamed on a one-shot run against the only copy, silently under-delivering Req 11.2.
effort: S
kind: gap
area: encumbered-content-purge, .kiro/specs/encumbered-content-purge/design.md
created: 2026-08-07
surfaced_by: /kiro-impl encumbered-content-purge (task 5.3 review, three rounds)
pinned_at: 7d49c84
resume_command: "do: On a throwaway clone, run the design's rewrite invocation shape -- path inversion combined with rename directives in one paths-from-file -- and record whether the renamed sources survive under their new names or are deleted. Write the result into design.md's HistoryRewrite section as recorded evidence, replacing the unrecorded claim."
context:
  - .kiro/specs/encumbered-content-purge/design.md
  - scripts/purge/rewrite.py
  - .kiro/specs/encumbered-content-purge/tasks.md
blocked_by: []
---

## What

`design.md`'s `HistoryRewrite` invocation passes the path-inversion flag and
the rename directives inside a single paths-from-file. Inversion turns that
file from "remove these paths" into "keep only these paths". Whether a rename
line's source path also joins the inverted selection set decides whether the
token-bearing queue items are renamed to their neutral stems or deleted
outright. Nobody in the implementing session could settle it.

## Why it matters

Major 7 is one-shot and runs against the only copy. A deletion where a rename
was intended satisfies no requirement, removes items the queue contract says
are kept rather than deleted, and is not recoverable afterwards. The failure is
silent: the run succeeds, and the absence looks like a successful purge.

## Evidence

`design.md` § HistoryRewrite states the shape was "verified end to end on a
throwaway clone during design" but records no evidence -- no command, no
output, no commit. `command -v git-filter-repo` returns nothing on this
machine, so three review rounds of task 5.3 could not settle it by experiment.
Task 5.3's own driver is built and never executed, so it cannot settle it
either.

## How to pick it up

Install the rewrite tool. Build a throwaway repository with one path that must
be removed and one that must be renamed. Run the exact invocation shape
`design.md` specifies. Check whether the renamed path exists under its new name
afterwards. Record the command and its output in `design.md` § HistoryRewrite in
place of the unrecorded claim. Done when a reader can see the evidence rather
than the assertion.

## Open questions

If inversion does consume rename sources, the design needs a second invocation
or a different directive shape, which changes task 7.2's plan. That is a design
decision, not an implementation one.

## Resolution, 2026-08-08

**Settled by measurement: inversion does not consume rename sources. The queue
items are renamed, not deleted.**

`git-filter-repo` was fetched as the single file the design already specifies
(it is still not installed, and is not a project dependency). On a throwaway
repository carrying one path to remove, one to rename and one control, the
design's invocation shape produced the intended outcome on every one: the
removed path is gone from the tip and from every commit, the renamed path
exists under its new stem with its content byte-identical, and the control is
untouched.

The mechanism, read from the tool's `newname` function *after* measuring rather
than instead of it: only `filter` directives set the `wanted` flag that
`--invert-paths` tests. A `rename` directive rewrites the pathname and leaves
`wanted` untouched, so a renamed path is never a candidate for the inverted
removal set.

**The hazard is a different one, and it is real.** A path listed as *both* a
deletion line and a rename source resolves by file order: deletion line first
deletes it and the rename is lost; rename line first renames it and the later
deletion line matches nothing. Both directions measured on the same fixture.

**That shape is unreachable from our tooling**, which is what closes this rather
than merely documenting it. `scripts/purge/plan.py::classify_path` returns
exactly one disposition per path and checks `rename_targets` before `forbidden`,
because a path being renamed still matches `forbidden` — its old stem carries
the token being erased. Reversing those two checks reds four tests in
`tests/purge/test_plan.py`, one named for this exact case
(`test_classify_path_renamed_when_in_rename_targets_even_if_also_forbidden`).

The evidence now lives in `design.md` § HistoryRewrite in place of the
unrecorded "verified end to end during design" claim.

**One carry-forward for task 7.2**, recorded because it is the way the closed
hazard could return: `paths.txt` must be built from the plan's dispositions,
not from two independently-derived lists of removals and renames. The
single-disposition guarantee is what prevents a double listing, and it only
holds if one source produces both blocks.
