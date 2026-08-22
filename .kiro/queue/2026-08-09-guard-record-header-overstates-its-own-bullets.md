---
id: 2026-08-09-guard-record-header-overstates-its-own-bullets
title: A landed guard commit's mutation-evidence header claims every mutation was observed red while its own final bullet records one that reddens nothing
status: open
importance: low
importance_why: The commit message is uneditable, so the contradiction is permanent; the provenance record inherits it unless it says otherwise, and Req 3.5 rests on these records being read literally.
effort: S
kind: inconsistency
area: encumbered-content-purge, docs/reference/history-rewrites.md
created: 2026-08-09
surfaced_by: /kiro-impl encumbered-content-purge (task 6.1 review, rounds 1 and 2)
pinned_at: d6fe28f
resume_command: "do: Decide whether docs/reference/history-rewrites.md should state that f1dad15's mutation-evidence header overstates its own bullets, since the commit message cannot be edited and Req 3.5 rests on these records."
context:
  - docs/reference/history-rewrites.md
  - .kiro/specs/encumbered-content-purge/requirements.md
blocked_by: []
---

## What

Commit `f1dad15` (task 4.2, the documentation guard) carries a `MUTATION
EVIDENCE` block whose header says every mutation was "run through `uv run
pytest`, **observed red**, reverted".

Its ninth and final bullet records an escape that **leaves the suite green** —
a real-tree plant the guard did not catch, disclosed deliberately. That is
exactly the right thing to record, and it is not something the header describes.

## Why it matters

Req 3.5 is discharged by these commit messages: the per-guard mutation evidence
lives in the commit that landed each guard, because a later task cannot write
into an already-made commit message. That makes the records load-bearing and
permanent — the message cannot be edited now.

A reader who takes the header literally concludes nine mutations were observed
red. Eight were; the ninth is an escape probe that reddens nothing by design.
The underlying work is sound and the disclosure is honest — the header is
simply broader than the bullets beneath it.

Task 6.1's provenance record initially inherited the overstatement, asserting
that "every named mutation either reddens only the assertion it pins, or is
explicitly declared a preserved control … the commit message states the
difference at each site". That sentence was corrected during review to name
where the messages do and do not quantify blast radius. What remains open is
whether the record should say plainly that `f1dad15`'s *header* is wrong, as
opposed to merely not repeating its claim.

## Evidence

`git log -1 --format=%B f1dad15` — the header sentence and the ninth bullet,
which states in its own words that the plant "leaves the suite green".

Two reviewers reached this independently: round 1 of task 6.1's review flagged
the header contradiction as a follow-up, and round 2 confirmed the bullet count
(9 bullets, 7 named sole failures, one reddening two tests by design, one
reddening nothing).

A neighbouring case in the same family, already corrected in the record:
`7f447da` states no blast radius at two of its six sites — "The path-only
exemption keying: red." and a sixth bullet saying only "still caught". Both are
in fact sole failures, re-measured during task 6.1: removing the surface gate
reds `test_reviewed_exemption_never_exempts_a_path_surface_hit` alone. So that
record *understates* its evidence, where `f1dad15`'s header overstates it.

## How to pick it up

Read `f1dad15`'s message, then the "Guard re-basing: mutation evidence" section
of `docs/reference/history-rewrites.md` as it now stands — the section already
names what each commit does and does not quantify, so this is a question of one
more sentence rather than a rewrite.

The decision is whether a provenance record should annotate a source it cannot
change. Arguments both ways: recording it means a reader of the record is not
misled by the commit; not recording it keeps the record from accumulating
commentary on every imprecision in the history it summarises.

Done when either the record says the header overstates its bullets, or a
deliberate decision not to annotate it is recorded.

## Open questions

Whether any other landed guard commit has the same shape. Only `221d60a`,
`f1dad15` and `7f447da` carry mutation-evidence blocks, and all three have now
been read bullet-by-bullet, so the class is bounded and closed — but that
enumeration lives in a review transcript, not in the tree.
