---
id: 2026-07-30-phase5-constraints-outrank-settled-requirements
title: Steering Phase 5 still states three constraints the requirements phase settled the other way, and the rewrite is scheduled for tomorrow
status: done
importance: high
importance_why: Steering is loaded as project memory by every session; requirements.md is read only by someone working this spec. On the two points where they now disagree, steering is the one a purge session is more likely to obey, and one disagreement is the difference between halting and destroying two peers' unlanded branches. The rewrite is scheduled 2026-07-31.
effort: S
kind: inconsistency
area: encumbered-content-purge, .kiro/steering/roadmap.md
created: 2026-07-30
surfaced_by: reading roadmap.md Phase 5 end to end as steering-class validation for 2026-07-30-purge-brief-carries-superseded-counts
pinned_at: 07f274e
resume_command: "do: reconcile .kiro/steering/roadmap.md Phase 5 with the four decisions settled in encumbered-content-purge/requirements.md, or record why steering should keep its wording [queue: .kiro/queue/2026-07-30-phase5-constraints-outrank-settled-requirements.md]"
context:
  - .kiro/steering/roadmap.md
  - .kiro/specs/encumbered-content-purge/requirements.md
  - .kiro/specs/encumbered-content-purge/brief.md
blocked_by: []
---

## What

Four questions left open at Phase 5 discovery were put to the maintainer during
`/kiro-spec-requirements encumbered-content-purge` on 2026-07-30 and answered.
`requirements.md` records all four. `roadmap.md` Phase 5 was not updated in the
same change, so on three of them steering still states the unsettled — or
opposite — position:

| Phase 5 says | requirements.md says |
|---|---|
| `roadmap.md:804-811` — "Every unmerged branch must land before the rewrite runs, **or be orphaned by it** … anything still on a branch when the rewrite runs is orphaned by it" | **Req 6** — the purge **halts** rather than orphans, and **an additional worktree blocks it too**, not only a branch |
| `roadmap.md:817-820` — "`refs/original/` holds the only copies of two never-pushed branches … **Decide deliberately.**" | **Decision 2** — decided: **destroyed**, with the reason (they are pre-2026-07-26 tips carrying the personal address in their commit headers) |
| `roadmap.md:776-784` — "**Purge depth: content only** … The verbatim tables and the extracted methodology writeup are deleted" | **Decision 1 / Req 1.2-1.3** — depth still excludes the name, but the sweep now covers **every tracked file**, because `.kiro/specs/training-load/research.md` reproduces the load formulas, the discount-generating rule and two worked-example vectors in symbolic form |

The fourth decision — that the provenance record carries a full SHA map and the
open items' pins are repaired mechanically — has no contradicting Phase 5 text;
`roadmap.md:795-803` says "the purge spec owns stating the position on each
class", which stays true.

## Why it matters

`CLAUDE.md` instructs every session to "Load entire `.kiro/steering/` as project
memory". `requirements.md` is read only by a session working this spec. So on
any point where they disagree, the steering wording is the one more likely to be
in context — and it is currently the wrong one.

The branch/worktree row is the dangerous one. A session that runs the purge with
`roadmap.md` in memory and not `requirements.md` reads "anything still on a
branch when the rewrite runs is orphaned by it" as authorisation to proceed over
unlanded work. Two peers had unmerged branches during the requirements phase and
both posted that they intended to land first. Req 6 exists precisely so that
proceeding is not possible; steering currently says it is expected.

The `refs/original` row is lower risk but the same shape: "Decide deliberately"
invites a design session to re-open a question the maintainer already closed,
and to reach a different answer.

The depth row understates scope rather than contradicting it, so a design that
follows steering alone would produce a purge that misses the reproduced content
in `training-load/research.md` — the exact gap the requirements phase was widened
to close.

## Evidence

The three Phase 5 passages, at `07f274e`:

```
$ sed -n '804,811p;817,820p;776,777p' .kiro/steering/roadmap.md
- **Every unmerged branch must land before the rewrite runs, or be orphaned
  by it.** ... anything still on a branch when the rewrite runs is orphaned by
  it. Nothing else runs concurrently with the rewrite.
- **`refs/original/` holds the only copies of two never-pushed branches**
  ... Expiring it to complete the purge destroys them. Decide
  deliberately.
- **Purge depth: content only.** The verbatim tables and the extracted
  methodology writeup are deleted from the tree and from history.
```

The four settled decisions are at `requirements.md` › "Decisions taken with the
maintainer during requirements (2026-07-30)"; Req 6's acceptance criteria 1-3
carry the halt behaviour and the worktree clause.

This was found while reading Phase 5 end to end as the steering-class validation
for a *different* change (`2026-07-30-purge-brief-carries-superseded-counts`),
not by looking for it.

## How to pick it up

1. Decide first whether steering should move at all right now:
   `requirements.md` is `approvals.requirements.approved: false`. The four
   decisions came from the maintainer directly rather than from the document, so
   they are settled independently of the approval — but if the review changes
   any of them, steering would move twice. Landing this after approval is
   defensible; leaving the branch/worktree row wrong until then is the risk that
   argues against waiting.
2. Move all three passages in one change, and say in each that the position was
   settled during the requirements phase, not at discovery — Phase 5's own
   convention is to record when a decision was taken and by whom.
3. Do not delete the "or be orphaned by it" framing wholesale: the *warning* to
   peers is still useful. What must change is that it currently reads as
   permission for the purge to proceed. Req 6 makes the purge halt; the peer
   warning becomes "land early, because a blocked purge is everyone's problem",
   not "land early or lose your work".
4. Class is `.kiro/steering/**`: worktree, branch, the edited doc read end to
   end, and a grep for every other copy of the rules being moved.

## Open questions

- Should Phase 5 carry the settled decisions at all, or a pointer to
  `requirements.md`? Duplicating them is what created this divergence; a pointer
  costs a session one extra file read but cannot drift.

## Resolution

Done 2026-08-05 (`encumbered-content-purge` task 3.12). The correction is
task 3.10's. It is committed on branch `impl/encumbered-content-purge`, not
yet merged to `main`. `.kiro/steering/roadmap.md` Phase 5 no longer
contradicts `requirements.md` on any of the three points this item named.
The "Purge depth — two things discovery's reading got wrong" bullet now
records the sweep widened to every tracked file. The "`refs/original/` held
the only copies of two never-pushed branches" bullet now records that the
branches were deleted as a settled decision. The "The rewrite halts rather
than orphans unlanded work" bullet now matches Requirement 6 instead of the
superseded "orphaned by it" framing. The peer warning that unlanded work
should land early was kept. It was reworded so it no longer reads as
permission for the purge to proceed over unlanded work. The open question
above was answered implicitly: the settled decisions were rewritten in place
in `roadmap.md` rather than replaced with a pointer.
