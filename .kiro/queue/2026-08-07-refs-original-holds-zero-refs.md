---
id: 2026-08-07-refs-original-holds-zero-refs
title: An open queue item says the backup refs still hold three pre-rewrite tips; they hold none
status: open
importance: high
importance_why: A session planning around that safety net is planning around something already gone, and the item instructs future sessions not to expire refs that do not exist.
effort: S
kind: inconsistency
area: .kiro/queue, encumbered-content-purge
created: 2026-08-07
surfaced_by: /kiro-impl encumbered-content-purge (task 4.3 review)
pinned_at: c3d2201
resume_command: "do: Correct .kiro/queue/2026-07-26-rewrite-map-not-durable.md's refs/original paragraph to what the commands decide -- the directory is empty -- and remove the do-not-expire-them-yet instruction, which names a safety net that no longer exists."
context:
  - .kiro/queue/2026-07-26-rewrite-map-not-durable.md
  - scripts/purge/preflight.py
  - .kiro/specs/encumbered-content-purge/tasks.md
blocked_by: []
---

## What

`.kiro/queue/2026-07-26-rewrite-map-not-durable.md` asserts that the backup ref
namespace "still holds all three pre-rewrite tips" and instructs a reader **Do
not expire them yet**. The namespace holds zero refs.

## Why it matters

The instruction tells a future session to preserve a safety net that is already
gone, which is worse than saying nothing: it invites planning around a recovery
path that does not exist. This spec's own quiescence gate was originally
designed to derive the abandoned branch names from those refs, which would have
found an empty set and discharged the abandonment obligation by accident. That
design was changed for this reason; the queue item was not.

## Evidence

Measured during task 4.3's review at this branch tip: `git for-each-ref
refs/original/` returns nothing, `packed-refs` carries no such entry, and the
`refs/original` directory under the git dir is empty. The queue item's own
paragraph asserts the opposite and cites a re-verification.

## How to pick it up

Read the item's `refs/original` paragraph. Run the three commands above and
record what they return. Rewrite the paragraph in the past tense, stating that
the refs were deleted and when, and delete the do-not-expire instruction. Leave
the rest of the item alone -- its rewrite-map subject is separate and was
corrected during task 4.3. Done when no sentence in the item asserts a ref that
`for-each-ref` cannot find.

## Open questions

None. This is a factual correction to a record.
