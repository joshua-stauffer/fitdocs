---
id: 2026-08-03-purge-design-provenance-section-stale
title: design.md's ProvenanceRecord section disagrees with tasks.md and with itself
status: dropped
importance: medium
importance_why: tasks.md was corrected on 2026-08-03 and design.md was not, so the two now disagree about a claim a reviewer already proved false; the next prose task reads whichever it opens first.
effort: S
kind: inconsistency
area: encumbered-content-purge
created: 2026-08-03
surfaced_by: /kiro-impl encumbered-content-purge (task 3.4, reviewer rounds 3-6)
pinned_at: c3d2201
resume_command: "/kiro-spec-design encumbered-content-purge [queue: .kiro/queue/2026-08-03-purge-design-provenance-section-stale.md] Reconcile design.md's ProvenanceRecord and destroyed-artifact enumerations with tasks.md's 2026-08-03 corrections"
context:
  - .kiro/specs/encumbered-content-purge/design.md
  - .kiro/specs/encumbered-content-purge/tasks.md
  - docs/reference/history-rewrites.md
blocked_by: []
---

## What

Three defects in `design.md`'s `ProvenanceRecord` section and the
destroyed-artifact enumerations around it. All three were found while
implementing task 3.4, which took eight review rounds; two of the three
directly caused a false claim to ship into a draft of the provenance record.

**1. design.md still carries a conclusion tasks.md removed as unevidenced.**
Its section-2 description says the purge "destroyed those refs and the two
branches held only there". On 2026-08-03 the equivalent bullet in `tasks.md`
was corrected in place, because that conclusion has no evidence behind it and
an implementer's invented justification for it was rejected: measured from the
deleted rewrite map's own header, **neither branch was merged when the rewrite
ran**, and both landed afterwards by rebase under different SHAs. The refs
were also already deleted during this spec's *design* phase, so the purge does
not destroy them — task 7.1 asserts their absence, and the fresh clone in 7.2
is what removes the unreachable objects. Only the `tasks.md` side was
corrected, so the two documents now disagree.

**2. The destroyed-artifact enumeration differs at three sites in one file.**
`design.md:1390` lists four items (probe set, replacement spec,
message-replacement spec, mailmap); `design.md:2029` lists three, dropping the
replacement spec; `design.md:1787` says "probe set, replacement specs and
mailmap". A reviewer flagged the omission of the path-removal/renaming spec
that `HistoryRewrite` itself lists. Related and already corrected on the
`tasks.md` side only: task 3.4's brief used to list the **match-data file**
among artifacts destroyed with the material, which would instruct a future
maintainer to destroy the standing token guard's only input. design.md is the
authority that resolved that one and is correct there — it is the enumerations
that disagree with each other.

**3. The section list numbers 1-7 but leaves two required sections
unnumbered.** Sections 3 and 7 are written in the post-rewrite commit, so part
one ships with a deliberate gap at 3. But the task also requires the 2.4
evasion-acceptance results and the 3.2 classified inventory be recorded, and
the numbered list gives them no position. The shipped document had to invent
one — an earlier draft placed them between sections 2 and 4, which would have
made part two's section 3 impossible to *append* in document order, and the
fix cost a structural rework plus two dense sentences of placement
justification that a reviewer then had to verify.

## Why it matters

`tasks.md` and `design.md` now state opposite things about what the purge does
to the abandoned branches. The next session writing prose in this spec — 3.6,
3.7 and 6.1 are all prose-heavy — will read whichever it opens first. Task 3.4
already demonstrated the cost: quoting design.md instead of measuring produced
two of the six false claims that took eight review rounds to clear, and the
plan's own execution rules exist because of it ("a figure in `design.md` is a
shape to re-measure, never a budget").

Defect 3 is the cheapest to fix and the one most likely to recur: part two of
the provenance record is written in the post-rewrite commit by task 8.2, and it
will hit the same gap.

## Evidence

Verified at `9d8ef1c`:

    $ sed -n '/^#### ProvenanceRecord/,/^#### /p' .kiro/specs/encumbered-content-purge/design.md
    ...
    2. The 2026-07-26 email rewrite, described without restating either address
       (Req 5.4, 9.2), including that it left `refs/original/*` behind and that this
       purge destroyed those refs and the two branches held only there.
    ...
    4. **What is no longer verifiable** (Req 3.6): ... the purge's own probe set,
       replacement specs and mailmap were scratch artifacts destroyed with the material.

    $ grep -n 'probe set' .kiro/specs/encumbered-content-purge/design.md
    1390:- **The probe set, the replacement spec, the message-replacement spec and the
    1787:   the purge's own probe set, replacement specs and mailmap were scratch artifacts
    2029:  probe set, the message-replacement spec and the mailmap contain the material,

    $ git for-each-ref refs/original | wc -l
    0

The branch-merge measurement was performed by a reviewer subagent using the
tips recorded in the deleted map's header (`git merge-base --is-ancestor` = NO
for both, 2 and 3 commits unique at rewrite time, both landing later by rebase
within ~32 hours). **I did not re-derive that measurement in this run** — it is
recorded here as reviewer-reported. The `refs/original` emptiness and the three
enumeration sites above I verified directly.

## How to pick it up

1. Open `design.md`'s `#### ProvenanceRecord` section and the `tasks.md` task
   3.4 bullets side by side. The `tasks.md` bullets carry three corrections
   dated 2026-08-03 and marked **Corrected in place**; they are the settled
   wording. Bring design.md's section 2 into line with them.
2. Reconcile the three destroyed-artifact enumerations to one list. Check it
   against `HistoryRewrite`'s own list of spec files, and confirm the
   match-data file is **absent** from every destroyed set — it is retained out
   of repository indefinitely, and the opt-in detection posture depends on it.
3. Give the 2.4 and 3.2 evidence sections a numbered position that lets part
   two's section 3 be appended in document order. Check the result against
   what `docs/reference/history-rewrites.md` actually ships, which is the
   reviewed-and-approved structure.
4. Re-read `docs/reference/history-rewrites.md` afterwards and confirm it does
   not need to change. It was approved after eight review rounds and every
   claim in it was independently re-derived; if a design.md correction implies
   the document is wrong, the document is more likely to be right.

Done means a session can read either document and get the same answer about
what the purge does to the abandoned branches, what is destroyed with the
working repository, and where the evidence sections sit.

## Open questions

None. All three are corrections toward what has already been verified.

## Resolution

**Dropped 2026-08-23 — the document is archival.** Post-purge queue triage
after `encumbered-content-purge` completed (spec 57/57, `87ce085`).

**Reason:** this item records an internal inconsistency in the purge spec's own
working documents — `design.md`, `tasks.md`, or `requirements.md` disagreeing
with each other, with the code, or with what the majors actually built. Those
documents drove a spec that is now complete. Nothing reads them to decide
anything; no later session's behavior depends on the disagreement; and
correcting a finished spec's internals buys nothing a reader of the durable
record would not get more reliably.

The durable, load-bearing account of what the purge did is
`docs/reference/history-rewrites.md`, which ships and stays public. Items
against **that** document were kept open in the same triage, precisely because
its accuracy still matters. This item is not one of them.

Dropped rather than closed `done`: nobody fixed the disagreement — the
document simply stopped being consulted.
