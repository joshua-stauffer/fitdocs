---
id: 2026-07-26-region-preservation-unpinned-e2e
title: Req 7.1's "without altering any other section" has no end-to-end pin
status: done
importance: medium
importance_why: Region preservation is this feature's most load-bearing contract with workout-docs, and only a pure-function test covers it.
effort: S
kind: gap
area: training-load, src/fitdocs/load/engine.py, tests/load/
created: 2026-07-26
surfaced_by: /kiro-validate-impl training-load
pinned_at: 3121bb6
resume_command: "/kiro-impl training-load [queue: .kiro/queue/2026-07-26-region-preservation-unpinned-e2e.md] Pin region preservation across a real apply_load pass"
context:
  - .kiro/specs/training-load/requirements.md
  - src/fitdocs/load/engine.py
  - tests/load/test_docedit.py
  - tests/load/test_feature_e2e.py
blocked_by: []
---

## What
Requirement 7.1 says the load pass writes its section "without altering any other section or user-editable region". The surgery lives in `docedit.replace_load_region` and the write in `engine.py`, but 7.1 is claimed only by task 2.1, whose boundary is the renderer -- which produces content and performs no surgery. The only test is `tests/load/test_docedit.py:325`, a pure-function test.

## Why it matters
No fixture in `tests/load/` ever places user content in a non-load region and then runs `apply_load`. A mutation making `_apply_result` re-render the whole document from the archived source instead of calling `replace_load_region` would leave the frontmatter and the load region correct, reset the user's notes region, and the suite would stay green. Production is correct today (traced at `engine.py:497,565` -- surgical, then `_atomic_write`); this is a missing pin, not a live defect. `workout-docs` consumes this contract.

## Evidence
`grep -rn extract_regions tests/load/` returns hits only in `test_docedit.py` (pure-function) and `test_feature_e2e.py:232`, which reads `["load"]` only. No load test asserts a non-load region survives a pass. Verified at 3121bb6, suite 1852 passed.

## How to pick it up
Open `tests/load/test_feature_e2e.py` and copy an existing sync-built data-root fixture. Write distinctive text into a document's `notes` region, run a computing `apply_load`, and assert `extract_regions(after)["notes"] == extract_regions(before)["notes"]` plus the load region did change. Done when the mutation above (re-render from source instead of `replace_load_region`) reddens that test -- verify by making it.

## Resolution

**Done 2026-07-26** (queue sweep, merged to `main` at `e806c57`).

`b773826`. A computing `apply_load` over a doc with user content now asserts the notes region survives byte-for-byte AND the load region changed, with a non-empty precondition so the check cannot pass as "" == "". Verified against a notes-clobbering mutation.
