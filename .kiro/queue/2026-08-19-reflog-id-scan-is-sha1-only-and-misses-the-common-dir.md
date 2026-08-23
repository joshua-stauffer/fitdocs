---
id: 2026-08-19-reflog-id-scan-is-sha1-only-and-misses-the-common-dir
title: The 7.7 rehearsal's own id-scan helper is still 40-hex-only, now that its production copy is not; plus a safety net that never stats the shared common object DB
status: open
importance: medium
importance_why: The rehearsal helper and the production row's id-scan have now diverged in width; a future edit to one that assumes it matches the other would be wrong. The safety-net gap is unchanged from when this item was opened.
effort: S
kind: gap
area: encumbered-content-purge, tests/purge/test_replace_rehearsal.py
created: 2026-08-19
surfaced_by: /kiro-impl encumbered-content-purge (task 7.7 remediation review, reviewer FOLLOW_UPS 2 and 3)
pinned_at: c3d2201
resume_command: "do: widen tests/purge/test_replace_rehearsal.py's own _REFLOG_HEX_ID_RE to 64-hex to match scripts/purge/verify.py::check_reflog_and_unreachable_gone's now-widened pattern (item 1, partially resolved below), and decide whether the rehearsal's safety net should stat the shared common object DB (item 2, still fully open)"
context:
  - tests/purge/test_replace_rehearsal.py
  - scripts/purge/verify.py
  - tests/purge/test_verify.py
  - .kiro/queue/closed/2026-08-18-reflog-row-literal-emptiness-does-not-hold-post-swap.md
blocked_by: []
---

## What

Two independent findings from the same review, kept in one item because both
are small, bounded, and touch the same module.

**1. The reflog id scan is 40-hex only.** *(Partially resolved -- see
Resolution below.)* `_REFLOG_HEX_ID_RE` in `tests/purge/test_replace_
rehearsal.py` matches exactly 40 hex characters, so a repository using the
sha256 object format (64-hex ids) would have foreign ids pass invisibly.
Measured by the reviewer: planting `'b' * 64` into `logs/HEAD` left the
helper passing.

Harmless today — this repository is sha1 — but the sibling queue item
`2026-08-18-reflog-row-literal-emptiness-does-not-hold-post-swap.md` (closed)
directed the next session to reuse this file-reading approach for
`scripts/purge/verify.py::check_reflog_and_unreachable_gone`, the row that runs
during the irreversible replacement. A width assumption is cheap to widen now
and expensive to discover later.

**2. The rehearsal's safety net never stats the shared common object DB.**
`_assert_untouched` resolves `Path(__file__).resolve().parents[2] / ".git"`,
which in a worktree is the pointer file, and compares its stat plus `HEAD`.
`git rev-parse --git-common-dir` for this worktree is
`/Users/josh/code/fitdocs_oss/.git` — the shared object database — and the
assertion never looks at it.

That directory is precisely the blast radius of the 2026-08-09 incident, in
which a gc/prune run from a worktree copy pruned the shared object DB. So the
one historical accident this project has actually suffered is the one the
safety net cannot see.

This is **distinct from** the move-aside-and-back gap recorded in
`2026-08-18-assert-untouched-is-blind-to-move-aside-and-back.md`, which the
maintainer has ruled ships as-is; that ruling was about a different tamper
class and does not cover this.

## Evidence

Both measured by the reviewer at `7da5ce3`, through `uv run pytest`, against
scratch repositories only:

- `'b' * 64` planted in `logs/HEAD`: helper passed ("64-hex (sha256) foreign id
  NOT detected").
- `git rev-parse --git-common-dir` in the worktree resolves to
  `/Users/josh/code/fitdocs_oss/.git`; `_assert_untouched` stats only
  `<worktree>/.git`, the 73-byte pointer file.

## How to pick it up

For (1): widen the pattern to `[0-9a-f]{40}|[0-9a-f]{64}` (or `{40,64}` with an
explicit length check) and pin it with a planted 64-hex id that reds. Do this
**before** the logic is folded into `check_reflog_and_unreachable_gone`, not
after.

For (2): decide whether the rehearsal's safety net should additionally
snapshot `git rev-parse --git-common-dir`'s target — a directory whose mtime
and inode DO respond to activity, unlike the pointer file. If the answer is no,
say so in the helper's docstring with the reason, so the next reader does not
re-derive the gap. Note the maintainer has already ruled that
`_assert_untouched` ships as-is for the move-aside-and-back class; this needs
its own ruling because it is a different class and a much larger blast radius.

## Resolution (partial)

Item (1) is fixed in the production copy only. The maintainer-approved defect
fix that closed `2026-08-18-reflog-row-literal-emptiness-does-not-hold-post-
swap.md` reused this helper's file-reading approach inside `scripts/purge/
verify.py::check_reflog_and_unreachable_gone`, and widened THAT copy's id
pattern to `(?<![0-9a-f])(?:[0-9a-f]{64}|[0-9a-f]{40})(?![0-9a-f])` --
longest-alternative-first, tested with a planted 64-hex id via
`tests/purge/test_verify.py::test_check_reflog_and_unreachable_gone_
catches_a_64_hex_id`. The negative lookarounds themselves are now pinned too
(remediation to an independent review, this same change):
`test_check_reflog_and_unreachable_gone_ignores_a_41_hex_run_boundary_case`
plants a run of 41 consecutive hex characters -- one hex digit too long to
be either a 40- or a 64-hex id -- and asserts the row reports it clean;
without the lookarounds, `[0-9a-f]{40}` alone still matches the run's first
40 characters as a spurious foreign id. Measured: deleting both lookarounds
reds exactly that one test, nothing else. So the "before it's reused"
ordering this item's `resume_command` asked for was not honoured; the copy
was made and only the copy was widened. `tests/purge/test_replace_
rehearsal.py::_REFLOG_HEX_ID_RE` itself is UNCHANGED and still 40-hex-only
-- that file was outside this fix's declared boundary. The two copies have
now diverged: production catches a 64-hex foreign id, the rehearsal's own
safety check still would not. Item (2) is entirely untouched. This item
stays open for both.
