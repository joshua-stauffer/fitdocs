---
id: 2026-09-16-load-history-leftovers-found-by-training-blocks-review
title: Four load-history leftovers the training-blocks reviewers tripped over (stale anchor, USER_REGIONS-only pin, unpinned temp-file cleanup, interning-blind prose)
status: open
importance: low
importance_why: All four are in load-history-owned files; each is prose or a pin that a reader trusts today and that the sibling training-blocks copy has already corrected.
effort: S
kind: gap
area: load-history, src/fitdocs/declaration.py, tests/test_declaration.py, src/fitdocs/history/engine.py, tests/history/test_engine.py, tests/test_public_api.py
created: 2026-09-16
surfaced_by: /kiro-impl training-blocks (reviewers of 1.2, 4.2, 4.4)
pinned_at: 68fe42e
resume_command: "do: fix the four load-history leftovers listed in .kiro/queue/2026-09-16-load-history-leftovers-found-by-training-blocks-review.md, each with its named mutation run before and after"
context:
  - src/fitdocs/declaration.py
  - tests/test_declaration.py
  - src/fitdocs/history/engine.py
  - tests/history/test_engine.py
  - tests/test_public_api.py
  - .kiro/specs/load-history/tasks.md
blocked_by: []
---

## What
1. `src/fitdocs/declaration.py:164` -- the `_WRITTEN_AND_OWNED` claim anchor
   still says "the (not-yet-implemented) `history/engine.py`'s
   `HistoryEngine` ... lands in task 5.2"; history shipped 2026-09-12.
2. `tests/test_declaration.py::test_history_declaration_names_no_region_id`
   (~:131-137) iterates `contract.USER_REGIONS` only, so a `load` region id
   (a `TOOL_REGIONS` member) in the history declaration text passes it. The
   sibling blocks pin was widened to `contract.PRESERVED_REGIONS` in
   training-blocks 1.2 round 2 for exactly this reason.
3. `src/fitdocs/history/engine.py::_atomic_write`'s `except BaseException:
   unlink` cleanup branch -- the same idiom the plans engine copied -- may be
   unpinned by any history test (the plans copy was, until an
   `os.replace`-raises test was added in training-blocks 4.2 round 2).
4. `tests/test_public_api.py` `_HISTORY_SURFACE` comment (~:837 per the
   reviewer) appears to make the interning-blind claim that a re-spelled
   identifier-like literal would fail an `is` identity check; CPython interns
   such literals, so it does not. The `_PLANS_SURFACE` comment at
   `tests/test_public_api.py:1018-1023` states the corrected mechanism.

## Why it matters
Items 2-4 are the "prose is not evidence" species change-protocol.md
rejects on; item 1 is a stale anchor in the file that tells agents what
holds each declaration sentence true.

## Evidence
- `grep -n "not-yet-implemented" src/fitdocs/declaration.py` -> 164.
- `tests/test_declaration.py:134-136` -- the `USER_REGIONS` loop.
- Items 3 and 4: reported by reviewer subagents (4.2 round 1 FOLLOW_UPS;
  4.4 round 1 finding 4), not independently reproduced here -- verify item 3
  by monkeypatching `os.replace` to raise under the history engine and
  deleting the cleanup, item 4 by adding a re-spelled literal to
  `history/page.py` and running the surface test.

## How to pick it up
1. Fix the anchor sentence (1) to name the shipped `history/engine.py`.
2. Widen the loop (2) to `PRESERVED_REGIONS`; run the `load`-in-text
   mutation.
3. For (3) add the `os.replace`-raises test in the shape of
   `tests/plans/test_engine.py::test_atomic_write_leaves_no_partial_file_when_replace_fails`.
4. For (4) rewrite the comment to the true mechanism (identity rules out a
   runtime-constructed or differently-valued object; re-spelling is pinned by
   an AST assignment scan, as `tests/plans/test_boundary.py::TestNoLocalContractNameRebinding` does).
