---
id: 2026-08-17-purge-queue-re-triage-after-amendment-1
title: Re-triage the open purge queue items against Amendment 1's fresh-root decision
status: open
importance: high
importance_why: Dozens of open items direct work at a mechanism that will never run; each one picked up before triage wastes a session.
effort: M
kind: chore
area: encumbered-content-purge, .kiro/queue/
created: 2026-08-17
surfaced_by: encumbered-content-purge Amendment 1 (spec/purge-fresh-root)
pinned_at: c3d2201
resume_command: "do: read .kiro/specs/encumbered-content-purge/requirements.md Decision 6 and Req 12, then classify every open queue item matching grep -l 'encumbered-content-purge' .kiro/queue/*.md as moot-under-replacement (close as dropped with a one-line reason), folds-into-Req-12-retirement (note it in the item and mark blocked_by the design regeneration), or still-live (tip-guard and record-keeping items; leave open)"
context:
  - .kiro/specs/encumbered-content-purge/requirements.md
  - .kiro/specs/encumbered-content-purge/brief.md
  - .kiro/specs/encumbered-content-purge/spec.json
blocked_by: []
---

## What

Amendment 1 (Decision 6, merged at `19bd786`) replaced the purge's execution
mechanism: the in-place filter-repo rewrite of every commit is retired before
ever running, in favour of a fresh root commit of the certified tip plus
deletion and recreation of the remote. A large share of the open queue was
written against the retired mechanism — items about rewrite rules and their
regeneration, rewrite preconditions, the adopt/carry-over checklist,
commit-map and per-pin repair, and rule-set blind spots in historical blobs.
None of those items has been re-examined since the decision.

## Why it matters

The queue is the ranked source of next work. Until it is re-triaged, a fresh
session running /kiro-queue will be handed high-ranked items directing effort
at machinery Req 12 schedules for deletion. Every such pickup is a wasted
session, and some items (e.g. hardening rewrite-rule generation) would
actively grow the surface the amendment exists to shrink.

## Evidence

- `git show 19bd786 --stat` — the amendment commit: brief.md, requirements.md,
  spec.json.
- `.kiro/specs/encumbered-content-purge/requirements.md` › "Decision taken at
  Amendment 1 (2026-08-17)" and Requirement 12.
- `grep -l 'encumbered-content-purge' .kiro/queue/*.md | wc -l` → 52 at
  `19bd786` (measured 2026-08-17; re-measure, do not trust the count).
- Examples spanning the three classes: `2026-08-09-replacement-rules-need-a-tested-generator.md`
  (likely moot — the rules only exist to rewrite historical blobs),
  `2026-08-09-adopt-checklist-can-destroy-carried-material.md` (folds into
  Req 12 / regeneration), `2026-08-02-purge-guard-of-a-guard-unpinned.md`
  (re-examine: live only if the guard survives retirement).

## How to pick it up

1. Read requirements.md Decision 6 and Requirement 12 (the classification
   rubric: does the item's subject exist after a fresh root and after Req 12
   retirement?).
2. Enumerate open items with the grep above; classify each moot / folds-into-
   retirement / still-live. When in doubt whether a module survives Req 12,
   leave the item open with a note rather than dropping it — the design
   regeneration settles the retained-guard boundary.
3. Close moot items to `.kiro/queue/closed/` with `status: dropped` and a
   one-line reason naming Decision 6; do not delete them.
4. Done: every open purge item either carries a post-amendment note or is
   closed, and /kiro-queue's next ranking contains no item that assumes the
   in-place rewrite.

## Open questions

- The exact retained-guard set is a design decision (Req 12.2 names Reqs 3 and
  11's guards as survivors); items targeting modules on that boundary should
  wait for the design regeneration rather than be dropped now.
