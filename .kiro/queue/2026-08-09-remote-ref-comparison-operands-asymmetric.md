---
id: 2026-08-09-remote-ref-comparison-operands-asymmetric
title: The design's remote ref comparison names an unfiltered remote operand against a heads-only local one, which flags every legitimate remote tag
status: open
importance: medium
importance_why: Task 8.5's operator runs this comparison against the real remote after an irreversible rewrite; a literal reading reports every tag as a leftover, and the reason it is nonetheless correct for this purge is nowhere written down.
effort: S
kind: inconsistency
area: encumbered-content-purge, .kiro/specs/encumbered-content-purge/design.md, scripts/purge/verify.py
created: 2026-08-09
surfaced_by: /kiro-impl encumbered-content-purge (task 5.7 review, round 1)
pinned_at: d6fe28f
resume_command: "do: Record in design.md's RemoteReconciliation section why an unfiltered remote operand compared against a heads-only local operand is correct for this purge, or make the two operands symmetric."
context:
  - .kiro/specs/encumbered-content-purge/design.md
  - scripts/purge/verify.py
blocked_by: []
---

## What

`design.md` § RemoteReconciliation specifies the Req 8.5 check as
`git ls-remote origin` compared against `git for-each-ref refs/heads`. Those
operands are not symmetric: `ls-remote` reports every namespace the remote
serves — `HEAD`, tags and their `^{}` peels, `refs/pull/*` on a fork —
while `for-each-ref refs/heads` reports branch heads only.

Read literally, every legitimate remote tag is "a ref on the remote that is not
local" and lands in `remote_only`.

## Why it matters

It is correct *for this purge*, and that is exactly the problem: the reason is
load-bearing and unwritten. `design.md` § LocalVerification requires the
rewritten repository to carry `refs/heads/main` **only**, so after the rewrite
every non-head ref on the remote genuinely is a pre-rewrite leftover and
belongs in `remote_only`.

Task 8.5's operator runs this once, against the real remote, after the old
repository has been destroyed. If they hit a wall of tag entries and cannot
tell intended from broken, the recovery options are poor. Equally, if a future
reader "fixes" the asymmetry by filtering the remote operand to heads, they
reintroduce the blind spot task 5.7 was rejected for — a remote still carrying
`refs/original/refs/heads/main` reporting `passed=True`.

## Evidence

Measured on a throwaway repository and bare clone during task 5.7's review:
`git ls-remote` emits a `HEAD` line, and emits **both** `refs/tags/annot` and
the peeled `refs/tags/annot^{}`. `git for-each-ref --format=... refs/heads`
emits branch heads only.

`scripts/purge/verify.py::parse_ls_remote_output` implements the design
faithfully — it returns every remote ref except the `HEAD` symref and
`^{}`-peeled duplicates, deliberately *not* filtering to `refs/heads/*`. Two
tests pin that a `refs/original/*` entry and a pre-rewrite tag each fail the
comparison, which is the intended behaviour and the reason the filter was
removed.

The first draft of that function did filter to `refs/heads/*`, justified in a
docstring by a false claim that the other namespaces "sit outside the
comparison design.md specifies". Review caught it. Nothing prevents the same
reasoning recurring, because the design still reads asymmetrically.

## How to pick it up

Read `design.md` § RemoteReconciliation's Req 8.5 bullet and
`scripts/purge/verify.py::parse_ls_remote_output` together — the code is right
and the design is what needs the sentence.

Add to the design why the asymmetry is intended: the post-rewrite repository is
required to carry one head and nothing else, so an unfiltered remote operand is
what makes leftovers visible, and a symmetric operand would hide them. Say
plainly that a tag appearing in `remote_only` after the rewrite is a finding,
not noise.

Done when a reader of the design cannot conclude the operands should be made
symmetric, and task 8.5's operator knows in advance what a non-empty
`remote_only` means.

## Open questions

Whether the tool should distinguish "remote-only ref in a namespace the
rewritten repo never had" from "remote-only branch head", since only the second
is unambiguously a failed force-push. That is a reporting nicety, not a
correctness question — but 8.5 is a one-shot with an operator present, and a
report that sorts its own findings is worth more there than usual.
