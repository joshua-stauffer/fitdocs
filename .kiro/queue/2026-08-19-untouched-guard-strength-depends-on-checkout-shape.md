---
id: 2026-08-19-untouched-guard-strength-depends-on-checkout-shape
title: Two residual imprecisions in the 7.7 safety net's docstring and its dependence on checkout shape
status: open
importance: low
importance_why: Both are conservative — they understate rather than overstate what is detected — but the second means the same assertion is materially stronger outside a worktree and nothing pins which shape it runs in.
effort: S
kind: gap
area: encumbered-content-purge, tests/purge/test_replace_rehearsal.py
created: 2026-08-19
surfaced_by: /kiro-impl encumbered-content-purge (task 7.7, final review FOLLOW_UPS 1 and 2)
pinned_at: c3d2201
resume_command: "do: tighten the _assert_untouched docstring's HEAD-arm clause to the measured general rule, and decide whether the rehearsal should pin its checkout shape"
context:
  - tests/purge/test_replace_rehearsal.py
  - .kiro/queue/2026-08-18-assert-untouched-is-blind-to-move-aside-and-back.md
blocked_by: []
---

## What

Two low-severity residuals from task 7.7's final review, recorded so they are
not re-derived. Neither blocks; both were explicitly routed here rather than
into a fourth rewrite of the same paragraph, which had already oscillated for
three rounds.

**1. A clause is quantified over a class containing one non-holding sub-case.**
`_assert_untouched`'s docstring (and the module docstring) say *"a pointer
rewritten to name a different gitdir is caught by the `HEAD` arm too"*. Measured
counter-case: a different gitdir checked out at the **same commit** leaves the
`HEAD` arm silent while the stat arm fires — so there the stat arm *is* the sole
detector.

The sentence's conclusion ("it is not a general detector of `.git` being
replaced") is unaffected and independently proven by the different-commit case.
The imprecision is **conservative**: it credits the `HEAD` arm rather than
over-claiming the stat arm, so no wrong inference is licensed. The measured
general rule is: *the stat arm is the only arm that fires whenever the swap
leaves `HEAD`'s value unchanged.*

**2. The assertion's strength silently depends on checkout shape.** In the
worktree this test runs in, `real_repo / ".git"` is a ~73-byte pointer file, so
its stat is insensitive to activity inside the real gitdir. In a plain
(non-worktree) clone, `.git` is a **directory** whose mtime *does* respond to
writes — so the same assertion is materially stronger there. The docstring
scopes itself honestly ("In the worktree this test runs in"), but nothing pins
which shape CI or a future operator actually runs it in.

## Evidence

Measured by the final reviewer at `7da5ce3` in scratch fixtures only (the real
`.git` and the shared common dir were `stat`/`ls`-read, never written):

- clone of the fixture repo checked out at the identical SHA →
  `stat arm fires: True, HEAD arm fires: False`; the different-commit case →
  both `True`.
- `/Users/josh/code/fitdocs-purge-major7/.git` is `ASCII text`, 73 bytes
  (`file`), whereas a scratch `git init` repo's `.git` is a directory.

## How to pick it up

For (1): replace the class-quantified clause with the measured general rule
above. **Do not re-author the surrounding paragraph** — it took three rounds to
stabilise and the remaining text is measured true clause by clause. Change the
one clause, re-run the four probes (writes inside the real gitdir; byte-identical
pointer rewrite; pointer to a different gitdir at a different commit; pointer to
a different gitdir at the same commit; move-aside-and-back), and state all five
outcomes rather than generalising over them.

For (2): decide whether the rehearsal should assert its own checkout shape (a
one-line `assert (real_repo / ".git").is_file()` with the reason, or the
converse), so a future run in a plain clone does not silently get a different
guarantee than the docstring describes. Either answer is defensible; the defect
is that it is currently unstated.
