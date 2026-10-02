---
id: 2026-10-02-bytecode-hygiene-test-flaky-under-shared-worktrees
title: test_no_bytecode_cache_exists_under_src_during_the_run fails when another process runs Python in the same worktree during the suite
status: open
importance: low
importance_why: A false red that clears on a re-run, seen once; it matters only while peer sessions or a shell share a worktree, and it can send a session chasing a non-existent defect.
effort: S
kind: bug
area: tests/test_bytecode_hygiene.py, conftest.py
created: 2026-10-02
surfaced_by: /kiro-impl channel-merge
pinned_at: 5c41759
resume_command: "do: decide how test_no_bytecode_cache_exists_under_src_during_the_run should treat caches created by another process mid-run (re-purge and re-check, or assert only on caches this pytest session could read), then pin it [queue: .kiro/queue/2026-10-02-bytecode-hygiene-test-flaky-under-shared-worktrees.md]"
context:
  - tests/test_bytecode_hygiene.py
  - conftest.py
  - .kiro/queue/2026-09-19-root-conftest-bytecode-purge-misses-scripts.md
blocked_by: []
---

## What
`tests/test_bytecode_hygiene.py` asserts that no `__pycache__` directory exists
under `src/` while the suite runs. The purge that makes that true runs once, at
`conftest.py` import. A second process that runs `uv run python ...` or
`uv run fitdocs ...` in the same worktree while the suite is running writes
`src/**/__pycache__`, and the assertion then fails although nothing in the
session itself wrote one.

## Why it matters
The failure is real as a guard (a cache a later mutation could read stale) but
false as a signal about the session under test. With peer worktrees and shells
running Python beside the suite, it costs a red run and an investigation that
ends at "re-run it".

## Evidence
- Observed once during channel-merge feature validation; not reproducible when
  the suite runs alone (reported by the validation subagent, unverified in this
  run: I did not re-create it).
- Mechanism, read at 5c41759: `conftest.py:37-55` purges `src/**/__pycache__`
  once at import and then sets `sys.dont_write_bytecode = True` (this process
  only); `tests/test_bytecode_hygiene.py:33-43` globs `_SRC.rglob("__pycache__")`
  at test time and asserts the list is empty. Nothing re-purges between import
  and the test, and nothing stops another interpreter writing in between.
- This run's own probes avoided it by running Python with
  `PYTHONDONTWRITEBYTECODE=1` and `-B`; `find src -name __pycache__` printed
  nothing afterwards.

## How to pick it up
1. Reproduce: start `uv run pytest tests/test_bytecode_hygiene.py` in a loop in
   one shell and run `uv run python -c "import fitdocs"` in another.
2. Choose a rule: re-purge and re-check once at test time (the assertion then
   checks that a purge leaves nothing readable), or compare against a listing
   taken at conftest import and fail only on caches present at both points.
3. Keep the guard's purpose (no stale cache can be read mid-run) and pin the
   chosen rule with a test that creates a cache mid-run.

## Open questions
Whether the stronger hazard (a cache written by another process mid-run, which
this session might read stale) should stay a hard failure; if so the fix is to
document the shared-worktree limitation, not to loosen the test.
