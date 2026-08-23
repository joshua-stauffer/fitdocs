---
id: 2026-08-07-design-prescribes-names-for-deleted-constants
title: The vocabulary table prescribes replacement names for two constants that task 4.1 deleted outright
status: open
importance: medium
importance_why: Seven citation sites across five files now name identifiers that exist at no commit, and the table that mandated them is the artifact later tasks are told to take forms from.
effort: S
kind: inconsistency
area: encumbered-content-purge, .kiro/specs/encumbered-content-purge/design.md
created: 2026-08-07
surfaced_by: /kiro-impl encumbered-content-purge (tasks 4.1, 5.2 reviews)
pinned_at: c3d2201
resume_command: "do: Reconcile design.md's IdentityErasure vocabulary table with what task 4.1 actually did -- the two table-value constants were deleted, not renamed -- and correct the citation sites that now name identifiers existing at no commit."
context:
  - .kiro/specs/encumbered-content-purge/design.md
  - .kiro/specs/encumbered-content-purge/brief.md
  - tests/purge/test_tree_removal.py
blocked_by: []
---

## What

`design.md`'s `IdentityErasure` vocabulary table assigns neutral replacement
names to two constants. Task 4.1 **deleted** both constants rather than
renaming them -- correctly, since its own text says renames apply only over
what survives the deletions. The table still prescribes names for them, and
several tasks took forms from that table on the standing instruction to do so.

## Why it matters

Seven citation sites across five files -- this spec's brief, four queue items
and two test comments -- now name identifiers that exist at no commit in this
repository's history and never will. Each was reviewer-approved under the rule
"take the form from the table; do not improvise", so the table is the upstream
cause rather than any one task's mistake. A later session reading those
citations will look for constants that cannot be found.

## Why it was not fixed in place

Task 4.1's boundary is the guard module. Editing the brief, the queue items and
a peer test module to chase a design-level inconsistency was out of scope, and
the task correctly reported which names exist after its change rather than
resurrecting a constant to make a citation resolve.

## Evidence

Task 4.1's status report records that after its change only one of the three
token-bearing constants survives, and names the two that do not. The reviewer
enumerated the seven citation sites and confirmed each names a deleted
identifier.

## How to pick it up

Read the vocabulary table's rows for the two deleted constants. Decide whether
the table should record them as deleted rather than renamed, or whether the
citations should describe them by role. Apply one decision consistently across
all seven sites. Done when no tracked file names an identifier that
`git log -S` cannot find at any commit.

## Open questions

Whether a vocabulary table should carry rows for erased-and-deleted things at
all, or only for erased-and-renamed ones. That choice affects how task 7.2
reads the table.
