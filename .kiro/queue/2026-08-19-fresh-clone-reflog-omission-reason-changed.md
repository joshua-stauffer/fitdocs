---
id: 2026-08-19-fresh-clone-reflog-omission-reason-changed
title: check_fresh_clone omits check_reflog_and_unreachable_gone for a reason that no longer holds -- whether it belongs back in the re-run set is unresolved
status: open
importance: low
importance_why: Purely a completeness question about check_fresh_clone's own re-run set (C); the omitted row's reflog half would now measurably PASS against C, so nothing incorrect ships -- but the judgment call this item names has not actually been made since the reason for it changed.
effort: S
kind: gap
area: encumbered-content-purge, scripts/purge/verify.py
created: 2026-08-19
surfaced_by: /kiro-impl encumbered-content-purge (reflog row defect fix)
pinned_at: 8d922a3
resume_command: "do: decide whether check_reflog_and_unreachable_gone should be added back to check_fresh_clone's re-run set now that its reflog half is no longer a guaranteed-red hazard against C, and update check_fresh_clone's docstring/return tuple together with the sibling table-halves-disagree item"
context:
  - scripts/purge/verify.py
  - .kiro/specs/encumbered-content-purge/design.md
  - .kiro/queue/2026-08-18-replacement-verification-table-halves-disagree.md
blocked_by: []
---

## What

`check_fresh_clone`'s docstring lists `check_reflog_and_unreachable_gone` as
one of five row functions deliberately NOT re-run against `C` (the
`--no-local` verification clone), with the original reason being that its
reflog half was a "guaranteed-red-on-every-run hazard" against `C` (`git
clone` writes `clone: from <source>` reflog entries into `C`).

The reflog row's own contract changed in the same change as this item was
opened (see the closed item `2026-08-18-reflog-row-literal-emptiness-does-
not-hold-post-swap.md`): it no longer demands `git reflog show --all` report
literal emptiness, only that no reflog file under `.git/logs/**` names an id
other than the allowed replacement root. Measured directly against a real
`--no-local` clone of a single-commit repository: the `clone: from <source>`
entries it writes name only that same single commit as their new-sha, so the
reflog half of this row would now PASS against `C`, not fail. `check_fresh_
clone`'s docstring has been corrected to state this measured fact, but the
row itself is still NOT re-run there -- because re-scoping which rows
`check_fresh_clone` re-runs was outside this fix's declared boundary, not
because a new reason to exclude it was found.

## Why it matters

Low urgency: nothing incorrect ships, since the omission is conservative (a
row not run proves nothing either way, it does not assert something false).
But the ORIGINAL justification for the omission is gone, and no one has
actually decided whether the row belongs in the re-run set now. This is the
same "disagreement between the fresh-clone row's own prose and the per-row
subject column" the sibling item `2026-08-18-replacement-verification-table-
halves-disagree.md` already tracks for the other four omitted/included rows
-- this item is scoped narrowly to the one row whose omission reason just
changed, so a session picking up the sibling item has the full, current
picture rather than re-deriving this one measurement itself.

## Evidence

Measured directly (scratch repository, real git, not through pytest):
cloning a single-commit repository with `git clone --no-local` writes
`clone: from <source>` reflog entries whose only non-zero object id is that
repository's one commit -- the same id `check_reflog_and_unreachable_gone`'s
`allowed_commit` parameter would be. `check_fresh_clone`'s docstring in
`scripts/purge/verify.py` states this measurement in the bullet that used to
claim the guaranteed-red hazard for the reflog half.

## How to pick it up

1. Read `check_fresh_clone`'s current docstring bullet on `check_reflog_and_
   unreachable_gone` in full -- it already states the measured fact above.
2. Decide: does re-running the row's reflog half against `C` add real
   discriminating power (e.g. would it catch a botched clone that dragged
   extra reflog entries in), or is it genuinely redundant with the `W` run
   the same way `check_exactly_one_commit_reachable`/`check_metadata_clean`
   already are?
3. If added back: `check_fresh_clone` would need `allowed_commit` threaded
   through to the `C` call, and its return tuple/docstring updated together.
4. Fold the decision into whichever session resolves
   `2026-08-18-replacement-verification-table-halves-disagree.md`, since both
   are about the same function's re-run set.
