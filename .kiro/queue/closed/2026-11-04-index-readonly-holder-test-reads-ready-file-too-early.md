---
id: 2026-11-04-index-readonly-holder-test-reads-ready-file-too-early
title: An index test polls for a ready file and reads it before the writer has finished
status: done
importance: low
importance_why: Test-only, and the product is unaffected; but it turns a full CI run red with nothing wrong, as it did once on 2026-11-04.
effort: S
kind: bug
area: analytics-index, tests/index/test_build.py
created: 2026-11-04
surfaced_by: branch CI for strava-publish Amendment 1
pinned_at: 03935af2
resume_command: "do: make tests/index/test_build.py::test_readonly_holder_sees_complete_old_database_during_rebuild wait for the ready file's content rather than its existence (read .kiro/queue/2026-11-04-index-readonly-holder-test-reads-ready-file-too-early.md first)"
context:
  - tests/index/test_build.py
blocked_by: []
---

## What
`test_readonly_holder_sees_complete_old_database_during_rebuild` starts a reader in a
subprocess, which calls `ready.write_text(str(before))`. The parent polls with
`ready.exists()` and then immediately asserts `ready.read_text() == "1"`. `write_text`
creates the file before writing to it, so the parent can see it existing and empty.

## Why it matters
A correct tree fails CI on the unlucky timing, and each such run costs about 20
minutes. The next session may also spend time looking for a product defect.

## Evidence
- `tests/index/test_build.py:1033`: the reader's `ready.write_text(str(before))`.
- `tests/index/test_build.py:1057-1060`: the parent polls `ready.exists()`, then
  asserts the text.
- Run 41823560909, job `supported-pythons (3.12)` at commit 2df562d4:
  `tests/index/test_build.py:1060: AssertionError: assert '' == '1'`. It passed on the
  same run's other two jobs, and on all three at the next commit, with no change under
  `src/fitdocs/index` or `tests/index`.

## How to pick it up
1. Make the parent wait until the file's text is non-empty, within the same deadline.
   Writing to a temporary name and renaming in the reader would work too.
2. Scan the rest of the file for the same pattern.
3. To check it, hold the reader between creating and writing the file, and confirm the
   parent waits rather than failing. Done means that holds and the test passes.

## Resolution
Done 2026-11-06 on chore/suite-slow. The parent now waits for the file's content, not its existence. The same race was in `tests/index/test_lock.py`'s `_wait_for_ready`, which failed on run 42239862684 (`supported-pythons (3.12)`) once CI ran in parallel, so that is fixed too. The other polls on `exists()` in the suite never read the file.

Verified as this item asked: holding the child between creating and writing the file turned both tests red with `assert '' == ...`, and both pass under the same hold after the fix.
