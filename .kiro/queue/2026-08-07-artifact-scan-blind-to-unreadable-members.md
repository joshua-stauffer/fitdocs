---
id: 2026-08-07-artifact-scan-blind-to-unreadable-members
title: The artifacts row reports the dangling sdist symlink unreadable rather than scanning it
status: open
importance: medium
importance_why: Req 10.4's content surface has a permanent hole for exactly the member this project's own sdist is known to ship, and it now exists in a second place.
effort: S
kind: gap
area: distribution, scripts/purge/verify.py, tests/load/test_packaging.py
created: 2026-08-07
surfaced_by: /kiro-impl encumbered-content-purge (task 5.4 review)
pinned_at: c3d2201
resume_command: "do: Decide how a dangling symlink member in the built sdist should be scanned for Req 10.4, then apply that decision to both the packaging guard and the purge's artifacts verification row."
context:
  - scripts/purge/verify.py
  - tests/load/test_packaging.py
  - .kiro/queue/2026-07-31-agent-log-symlink-ships-in-sdist.md
blocked_by: []
---

## What

This project's built sdist ships a dangling symlink -- the shared agent log,
pointing into the git directory, which is not an archive member. An existing
queue item records that the packaging guard skips it. Task 5.4's verification
row now reports it as an unreadable member rather than crashing on it, which
is correct behaviour, but its **content** is still never inspected.

So the same blind spot now exists in two places, in both cases by construction
rather than by oversight.

## Why it matters

Req 10.4 says the built artifacts shall not contain the removed material at any
path. A member whose content is never read cannot satisfy that for its content
surface. The member's **name** is scanned in both places, so a token in the
path is caught -- the hole is content-only, and it is narrow, but it is real
and it is on the acceptance path for an irreversible operation.

## Evidence

Task 5.4's reviewer reproduced the crash that preceded the fix and then
confirmed the fixed behaviour: `check_built_artifacts` on a hand-built sdist
containing a dangling symlink returns a passing result whose detail reads
"unreadable member(s), content not scanned". The existing queue item records
the same shape from the packaging guard's side.

## How to pick it up

Read the existing queue item first -- it holds the prior reasoning about why
the symlink ships at all, which is the real question. Decide whether the right
fix is at the packaging level (do not ship it), at the scan level (resolve the
link against the working tree and scan the target), or a documented acceptance
that a dangling member has no content to scan. Apply the decision to both
consumers. Done when the two guards agree and the decision is written down
somewhere a reader finds it.

## Open questions

Whether a dangling symlink in a distributed artifact is itself a packaging
defect worth fixing independently of this spec. The existing item leans that
way and this spec did not settle it.
