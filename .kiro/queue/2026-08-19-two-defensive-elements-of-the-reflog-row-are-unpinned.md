---
id: 2026-08-19-two-defensive-elements-of-the-reflog-row-are-unpinned
title: Two defensive elements of check_reflog_and_unreachable_gone survive deletion with the suite green
status: open
importance: low
importance_why: Both are pass-widening or belt-and-braces rather than load-bearing today, but the row runs during the irreversible replacement, and an unpinned element is one a later edit can delete without noticing.
effort: S
kind: gap
area: encumbered-content-purge, scripts/purge/verify.py
created: 2026-08-19
surfaced_by: /kiro-impl encumbered-content-purge (task 7.7 remediation review, reviewer mutations R4 and R9; both re-measured by the parent)
pinned_at: c3d2201
resume_command: "do: pin or declare the sha256 all-zeros placeholder and the fsck returncode conjunct in check_reflog_and_unreachable_gone"
context:
  - scripts/purge/verify.py
  - tests/purge/test_verify.py
blocked_by: []
---

## What

The row's decision surface was swept exhaustively during review: 15 elements,
13 PINNED, 0 PRESERVED-ONLY, and these 2 UNPINNED. Recorded so the gap is
declared rather than latent — a declared gap is acceptable in this repo; an
undeclared one is the defect.

**1. The sha256 all-zeros placeholder.** `_REFLOG_NULL_IDS` holds both
`"0" * 40` and `"0" * 64`. Deleting the 64-character entry leaves the suite
green. The 40-character entry *is* pinned (removing it reds two tests), and
64-hex *detection* is pinned by `..._catches_a_64_hex_id` — it is only the
sha256 placeholder's presence in the discard set that nothing exercises.

This is a **pass-widening** element: its absence would produce a false RED in
a sha256 repository (the legitimate all-zeros "from" side of a branch creation
would read as a foreign id), not a false pass. Harmless in this sha1
repository.

**2. The `fsck` exit-code conjunct.** `fsck_clean = fsck_proc.returncode == 0
and not fsck_output`. Dropping `fsck_proc.returncode == 0` — keeping the
stdout+stderr fold — leaves the suite green. The zero-padded-filemode fixture
that pins the fsck strengthening is an `rc==0 && stdout empty && stderr
non-empty` shape, so the stderr fold alone catches it; no fixture presents a
non-zero exit with empty output.

Note this conjunct is not decorative in principle: the review measured real
`git fsck` exits of 1 (badident), 2 (invalid reflog entry), 10 (missing
object) and 128 (truncated object). Every one of those also writes to a
stream, which is why the fold alone suffices in practice — but a git version
or corruption class that exits non-zero *silently* would slip past.

## Evidence

Both re-measured by the parent at `8d922a3` + the uncommitted remediation,
through `uv run pytest`, each mutation reverted and the file re-hashed
identical afterwards:

- `_REFLOG_NULL_IDS = frozenset({"0" * 40})` → `101 passed`
- `fsck_clean = not fsck_output` → `101 passed`

The zero-padded-filemode test's own docstring now states the second of these
in place, rather than claiming the combination is what catches it.

## How to pick it up

For (1): either add a fixture planting a sha256-shaped all-zeros id and assert
it is NOT reported (which pins the discard), or state in a comment that the
entry is forward-looking for sha256 repositories and unexercised here.

For (2): construct a fixture where `fsck` exits non-zero with both streams
empty, if one exists for any corruption class — and if none does, say so at
the code site, because "we could not build the case" is a materially different
statement from "we did not try".

Do not resolve either by asserting the exemption without measuring.
