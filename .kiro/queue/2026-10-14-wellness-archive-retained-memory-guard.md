---
id: 2026-10-14-wellness-archive-retained-memory-guard
title: Measure retained-memory regression sensitivity of wellness archive copying
status: open
importance: low
importance_why: Production copying is bounded; existing counters cannot detect future chunk accumulation.
effort: S
kind: gap
area: wellness-store, tests/wellness/test_archive.py
created: 2026-10-14
surfaced_by: /kiro-impl wellness-store task 2.6 independent review
pinned_at: 6b23c37
resume_command: "/kiro-spec-tasks wellness-store [queue: .kiro/queue/2026-10-14-wellness-archive-retained-memory-guard.md] Add one retained-memory regression task without changing completed tasks"
context:
  - .kiro/specs/wellness-store/requirements.md
  - .kiro/specs/wellness-store/design.md
  - .kiro/specs/wellness-store/tasks.md
  - src/fitdocs/wellness/archive.py
  - tests/wellness/test_archive.py
blocked_by:
  - wellness-store
---

## What

Requirement 3.3 bounds content retained during wellness archival, apart from
format parsing results. The current copy loop is bounded, but the streaming
regression test measures read-request sizes only. A future implementation
could accumulate every chunk while passing that test. This measurement clause
was explicitly declared UNPINNED in the accepted task 2.6 evidence.

## Why it matters

A regression could exhaust memory on a large export despite continuing to use
bounded read calls. There is no current production accumulation defect.

## Evidence

At `6b23c37`, `commit_original` in `src/fitdocs/wellness/archive.py` writes and
hashes one `CHUNK_BYTES` chunk at a time. `test_streaming` in
`tests/wellness/test_archive.py` checks bounded requests using CountingOpener.
The implementer and two independent review passes ran this single-line mutation:

```python
sink.write(chunk); retained_chunks = locals().get("retained_chunks", []) + [chunk]
```

replacing `sink.write(chunk)` in `commit_original`. The selected command
`uv run pytest 'tests/wellness/test_archive.py::test_streaming[test-original]' -q`
stayed green (`1 passed`). Review artifacts on the originating machine:
`/private/tmp/review-archive2-6-replay-mutant-sweep-retained-memory.txt` and
`/private/tmp/archive2-6-review-r2-replay-mutation-results.json`. The controller
inspected the mutation and captured output; it did not run an additional replay
while the independent reviewer owned the worktree. The exact replacement above
makes the evidence reproducible without those temporary artifacts.

## How to pick it up

Read requirement 3.3 and the Archive design, then the copy loop and
`test_streaming`. Reproduce the surviving mutation on the current source and
restore it. Add a narrowly scoped, portable measurement test with a synthetic
input and a constant-space test parser so permitted parsed-result storage does
not confound copying. Python allocation tracing in an isolated process is one
possible approach; avoid a machine-specific RSS threshold. Preserve the
read-size controls. Done means the normal copy passes, deliberate chunk
retention fails specifically at the new assertion, restoration passes, and
canonical checks are green. The follow-up changes regression evidence, not the
archive API or formats.
