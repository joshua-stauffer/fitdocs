---
id: 2026-08-17-decision-7-binds-the-fresh-root-mechanism
title: Decision 7 fixes three mechanism details of the fresh-root replacement, and design regeneration must pin all three
status: done
importance: high
importance_why: The design has not been regenerated yet, so these commitments exist only in the agent log and this item. A regeneration that picks a different mechanism would silently discard a maintainer decision taken specifically to remove a data-loss path.
effort: S
kind: decision
area: encumbered-content-purge
created: 2026-08-17
pinned_at: 5683dc1
resume_command: "do: When regenerating design.md and tasks.md after Amendment 1, pin Decision 7's three mechanism commitments into the design's execution section -- .git swap for the fresh object database, old .git archived not deleted, and a carry-over checklist scoped to .git-resident items with the agent log first. Read this item and Amendment 1 (19bd786) first."
context:
  - .kiro/specs/encumbered-content-purge/requirements.md
  - .kiro/specs/encumbered-content-purge/design.md
  - .kiro/specs/encumbered-content-purge/brief.md
blocked_by: []
---

## What

Amendment 1 (`19bd786`) replaced the in-place `git filter-repo` rewrite with a
fresh root commit of the certified tip plus deletion and recreation of the
remote. It deliberately left `design.md` and `tasks.md` untouched, so the
*mechanism* of the replacement is not yet specified anywhere.

On **2026-08-17 the maintainer took Decision 7**, which fixes three details of
that mechanism. They were taken together with the commitment that **the working
directory and its untracked material are never moved and never deleted** — the
fresh root is made in place.

1. **The fresh object database arrives by swapping `.git`, never by pruning in
   place.** A prune leaves the outcome dependent on what the prune reached; a
   swap makes the new object database's contents true by construction.
2. **The old `.git` is archived, not deleted.** The irreversible step becomes
   reversible for as long as the archive is kept, which is the single largest
   risk reduction available on this operation.
3. **The carry-over checklist reduces to the `.git`-resident items, the shared
   agent log first among them.**

## Why the third one matters more than it looks

Because the working tree never moves, `data/`, the Requirement 1.7 source
workbooks and the reference scans are no longer at risk at all — the entire
class of "the only copy on disk is about to be deleted" disappears.

What does **not** disappear is anything living inside `.git`. The shared agent
log is at `$(git rev-parse --git-common-dir)/agent-log`, so a `.git` swap moves
it out from under every session that depends on it. It is untracked, exists in
one place, and is the record of how the whole purge was coordinated.

So the carry-over checklist is not retired by Decision 7 — it is **re-scoped**,
from a broad working-tree checklist to a narrow `.git`-resident one, and the
agent log becomes its first and most important entry.

## What already exists to build on

`scripts/purge/adopt.py::assert_carry_over` (hardened at `5683dc1`) already
asks a transfer question rather than an existence question: destinations inside
the doomed root are refused, content is compared by digest recursively, and the
root is keyword-only and non-defaultable. Its `doomed_root` concept maps onto
the archived `.git` rather than a doomed working directory, which is a narrower
and safer shape than the one it was built for.

Note Req 12.1 schedules that module for retirement once the replacement is
verified. Re-scoping it is still worth doing, because it runs *before* the
retirement and the agent log is what it protects.

## How to pick it up

1. Read Amendment 1 (`git show 19bd786`) and this item.
2. When `/kiro-spec-design` regenerates the execution section, pin all three
   commitments as design constraints with Decision 7 named as their source, not
   as one option among several.
3. Carry them into `tasks.md` as observables — in particular, that the archived
   `.git` exists and is readable after the swap, and that every `.git`-resident
   carried item is verified present at its destination before the swap is
   treated as complete.
4. Re-scope `assert_carry_over`'s checklist to the `.git`-resident items rather
   than deleting it.

## Done when

`design.md` and `tasks.md` state the swap, the archive and the `.git`-resident
carry-over checklist as fixed constraints attributed to Decision 7, and no
regenerated section proposes an in-place prune or the deletion of the old
`.git`.

## Resolution

Done on 2026-08-17, in two changes. `design.md`'s regeneration (7fd19cc) pins
all three commitments as fixed constraints of `HistoryReplacement`, attributed
to Decision 7 by name. The tasks regeneration in this same change states them
as execution rules binding every task and carries the observables this item
asked for: task 8.2 asserts every `.git`-resident carried item — the shared
agent log first — present and digest-identical at its destination before the
swap proceeds, and asserts the archived `.git` readable (the old tip resolves,
a connectivity-only fsck is clean) after it; task 7.3 re-scopes the carry-over
checklist to the old `.git` rather than deleting it. No regenerated section
proposes an in-place prune or the deletion of the old `.git` or the working
directory.
