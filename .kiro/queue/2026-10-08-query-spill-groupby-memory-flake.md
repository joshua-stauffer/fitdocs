---
id: 2026-10-08-query-spill-groupby-memory-flake
title: Investigate intermittent OOM in the 48MB sorted group-by spill fixture
status: open
importance: medium
importance_why: A query spill regression fixture can fail unrelated integration gates without an established runtime defect.
effort: M
kind: research
area: analytics-query, tests/query/test_spill.py
created: 2026-10-08
surfaced_by: /kiro-impl analytics-query task 5.2 focused verification
pinned_at: 7d362ff
resume_command: "do: investigate the intermittent 48MB sorted group-by OOM in analytics-query task 2.3; preserve actual nonempty spilling and all cleanup/concurrency assertions [queue: .kiro/queue/2026-10-08-query-spill-groupby-memory-flake.md]"
context:
  - tests/query/test_spill.py
  - src/fitdocs/query/sandbox.py
  - src/fitdocs/index/store.py
  - .kiro/specs/analytics-query/tasks.md
  - .kiro/specs/analytics-query/design.md
blocked_by: []
---

## What

The accepted task 2.3 sorted group-by spill fixture exhausted DuckDB's configured
48MB budget during one combined query/index test run. Its intermittent trigger
is unknown. Standalone and later combined passes do not establish a repair or
host memory contention. The command orchestration added in task 5.2 is not on
the failing facade call path; production uses a separate 1GB budget.

## Why it matters

This fixture should demonstrate real process-specific spilling and cleanup.
An intermittent memory failure interrupts integration verification without
identifying a spill-directory defect. Retrying until green or replacing the
nonempty spill witness with an empty directory would hide the issue.

## Evidence

- At `7d362ff`, `tests/query/test_spill.py` sets `_ROW_COUNT=3_000_000`,
  groups `i % 750000`, sorts descending, and patches `RESOURCE_SETTINGS`
  to `48MB`, two threads and a 4GB spill limit. Task 2.3 and design's Spill
  test strategy explicitly prescribe the 48MB/3M-row workload.
- The implementer reported `1 failed, 1233 passed in 42.39s` from
  `uv run --offline --no-sync --python
  /Users/josh/.pyenv/versions/3.11.15/bin/python3.11 --all-groups pytest
  tests/query tests/index -q`. The failing node was
  `tests/query/test_spill.py::test_sorted_group_by_spills_to_its_process_directory_and_close_removes_it`.
  DuckDB reported 45.5 MiB / 45.7 MiB used during `IndexResult.fetchall`,
  wrapped as `IndexStatementError`. **This failure was reported by the
  implementer; raw stdout and process context were not retained.** Its
  explicitly transcribed record is
  `/private/tmp/analytics-query-command-audit/final-checks-v2/combined-suite-observations.json`.
- A bounded, read-only owning diagnostic on the unchanged accepted tree
  passed one fresh-process attempt (`1 passed in 0.47s`, exit 0). Root
  inspected the captured stdout: actual DuckDB 1.5.6/Python 3.11.15;
  effective memory 45.7 MiB, two threads; `ORDER_BY` above `HASH_GROUP_BY`;
  a 1,048,576-byte file in the actual per-PID spill directory while fetch
  was active. Raw captures and private observer are under
  `/private/tmp/analytics-query-spill-oom-probe/`; diagnosis is
  `/private/tmp/analytics-query-debug-spill-oom/report.md`.
  The observer adds read-only settings/EXPLAIN statements and can affect
  timing. This is healthy diagnostic evidence, not a causal correction.
- DuckDB documents that combining blocking operators can still exhaust
  memory despite out-of-core support:
  <https://duckdb.org/docs/current/guides/performance/how_to_tune_workloads#limitations>.

- At accepted CLI head `a91bbec7e71fbdabe37c1e6b9014c4544e489f13`, an independent
  task 8.3 canonical run failed in the same node: 10,055 passed, one failed,
  two optional skips in 272.09 s, exit 1. This recurrence has durable raw
  evidence, independently inspected by root:
  `/private/tmp/analytics-query-task8-3-independent-review/canonical-failure-traces.txt`,
  `pytest.stdout`, `canonical-result.json`, and `REVIEW.md`. The traceback
  identifies `IndexResult.fetchall` delegating to `_relation.fetchall`,
  with 256 KiB allocation failure at 45.5/45.7 MiB. HOME was empty, tracked
  hashes/modes unchanged and owned processes reaped. No timing query failed.
- Fresh bounded owning investigation retained 32 baseline 750k-group and
  32 contrast 375k-group successful probes, all under the normative 3M rows,
  48MB, two threads and 4GB setting. Both plans use hash aggregation and
  sorting, with nonempty active spill and exact results/cleanup/purity.
  This does not establish the intermittent allocation stage or a causal
  cardinality repair. Exact report and raw captures:
  `/private/tmp/analytics-query-debug-spill-recurrence/REPORT.md`,
  `/private/tmp/analytics-query-debug-spill-recurrence/STATUS.md`. Debug
  outcome is BLOCK_TASK with LOW causal confidence. Preserve the fixture
  pending bounded failing-suite-context diagnostics; do not accept a guessed
  reduction merely because all isolated probes passed.

- One bounded passive full-suite diagnostic passed: 10,056 passed/two optional skips in 257.35 s, exit 0, approved 3M-row/750k-group/48MB/two-thread/4GB workload, real active spill, zero observer errors, restored wrappers, unchanged inventories, empty HOME and reaped owned process group. Configured snapshots, RSS and spill observations are distinct; no failing-time native allocation evidence or causal correction was obtained. Report: `/private/tmp/analytics-query-spill-full-context/REPORT.md`.
- Independent supplementary decision justified exactly one fresh unmodified acceptance gate after the new full-context capture. That gate passed 10,056 tests/two optional skips in 271.36 s, exit 0; all source/test/venv inventories were unchanged, HOME empty and owned group gone. Task 8.3 is accepted for its measurements; this reliability issue remains **open** and the original failed run is preserved. Decision and final review: `/private/tmp/analytics-query-task8-3-independent-review/SUPPLEMENT-GATE.md` and `/private/tmp/analytics-query-task8-3-unmodified-supplementary-review/REVIEW.md`.

## How to pick it up

1. Read task 2.3 and design's Spill test strategy, then the current fixture
   and sandbox/store seams. Verify the live runtime version and prescribed
   settings; the private artifacts above may no longer exist in another
   session, so capture fresh evidence if needed.
2. Capture the unchanged failing workload with bounded fresh-process attempts,
   complete raw logs, effective settings, query plan and process context.
   Do not infer a cause from successful retries. If OOM is reproduced, test
   one controlled workload contrast, such as lower group cardinality while
   retaining the 3M rows, 48MB, two threads and sorted group-by.
3. Accept a correction only with an actual nonempty spill witness, correct
   results, cleanup after close and unchanged four-process overlap proof.
   Preserve the temp-directory mutation's five-run red-rate control and all
   stale/live/own-PID, symlink and writer-directory assertions. A different
   memory limit needs reconciliation with the explicit approved spec; do not
   change production's 1GB limit as a fixture workaround.
