---
id: 2026-08-18-notice-guard-count-anchor-survives-a-narrowing
title: The notice/mark guard's count anchor cannot see a realistic file-type narrowing
status: open
importance: medium
importance_why: The guard survives Req 12 retirement and becomes a standing tip guard; a narrowing that halves its corpus would pass unnoticed.
effort: S
kind: gap
area: encumbered-content-purge, tests/test_forbidden_strings.py
created: 2026-08-18
surfaced_by: /kiro-impl encumbered-content-purge (task 7.2 review round 1)
pinned_at: c3d2201
resume_command: "do: replace the bare `len(texts) > 100` anchor in tests/test_forbidden_strings.py's notice/mark guard with the two-non-adjacent-different-kind-members shape already used by test_standing_guard_scans_tracked_content_and_path_names"
context:
  - tests/test_forbidden_strings.py
  - .kiro/steering/change-protocol.md
blocked_by: []
---

## What

The re-homed notice/mark tip guard anchors its walk with
`assert len(texts) > 100` against 636 tracked files. A hard truncation to
`[:1]` reds it, so it is not vacuous -- but a *plausible* narrowing does not.

## Why it matters

Under Req 12 the purge machinery retires and this guard is one of the
survivors. Its whole job is scanning every tracked file's working-tree
content. A corpus narrowing that leaves 362 of 636 files still clears a
`> 100` threshold, so the guard would report clean having stopped looking at
most of the tree.

The fix shape already exists two lines away in the same module.

## Evidence

Reported by the task 7.2 reviewer, which measured it: filtering
`_notice_guard_tracked_texts` to `.md` files only (362 of 636) left the guard
passing. Hard truncation to `[:1]` does red it.

Anchor location confirmed at `dac1a7a`:
`tests/test_forbidden_strings.py:1299`, `assert len(texts) > 100`, with the
corpus builder at `:1261`.

Pre-existing and carried over unchanged -- the retiring `_tracked_text_files`
used the same threshold -- so it was out of scope for a move-only task.

## How to pick it up

Open `tests/test_forbidden_strings.py` at `_notice_guard_tracked_texts` and
the guard that consumes it. Copy the coverage shape from
`test_standing_guard_scans_tracked_content_and_path_names`: assert two
non-adjacent members of different kinds (a `.kiro/` prefix and a
`tests/purge/` prefix, say) beside the count. Verify by re-running the `.md`-only
narrowing and watching it red. Done when that narrowing fails.
