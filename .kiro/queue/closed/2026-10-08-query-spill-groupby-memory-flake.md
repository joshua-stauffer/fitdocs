---
id: 2026-10-08-query-spill-groupby-memory-flake
title: Investigate intermittent OOM in the 48MB sorted group-by spill fixture
status: done
importance: medium
importance_why: The reduced-memory fixture now blocks mandatory floor acceptance; a runtime defect and causal correction remain unestablished.
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

- At accepted head `6194487`, task 8.2's sole designated DuckDB 1.2.0
  floor attempt failed during `IndexConnection.execute`, refusing an 8.0 MiB
  allocation at 40.5/45.7 MiB under the same 48MB workload. Store facade:
  37 passed; sandbox: 33 passed; spill: 14 passed/one failed/no skips.
  Statement, crash-vector and command modules remained unrun after STOP.
  Root inspected raw `test_spill.stdout` and independently compared complete
  before/after snapshots: source/tests/config, floor venv and Git unchanged,
  HOME empty. Evidence: `/private/tmp/analytics-query-task8-2-implementation/floor/`.
  Fresh read-only debug `/private/tmp/analytics-query-debug-floor-spill/REPORT.md`
  returned SPEC_CONFLICT / STOP_FOR_HUMAN. Failure phases differ from the
  retained 1.5.6 failure; a shared native cause is UNKNOWN. An unsafe floor
  is NOT ESTABLISHED, and floor safety acceptance remains INCOMPLETE.
  Task 8.2 explicitly requires a C1 roadmap decision on any failed floor
  test. No floor bump, fixture correction or retry is authorized by this item.

- The maintainer-approved bounded owning diagnostic at `93b27ea` exhausted its allowance: floor baselines2/2 reproduced the same execute OOM, current baselines2/2 passed with exact results/nonempty active files. Sole floor375k-group contrast returned exact results but failed the required observed nonempty spill witness. Zero observed payloads does not prove no transient native spill. One private observer import error preceded any query/fixture execution; it is retained separately from five actual workloads. Root independently inspected raw receipts and exact before/after inventories:21891 repo/current-venv entries and1171 floor-venv entries equal, Git equal/clean, allsix launch groups reaped, HOME empty. Report `/private/tmp/analytics-query-spill-owner-bounded-diagnostic/REPORT.md` returned SPEC_CONFLICT / STOP_FOR_HUMAN. No viable numeric correction or current-version causal repair is established. Any new workload capture needs a new explicit bounded decision.

- A subsequently approved native-debugger plan stopped during static host preparation at `be73b4b`, before any target launch. `/usr/bin/sandbox-exec` is restricted/compressed and SIP is enabled; the proposed first-instruction system-binary debug control conflicts with Apple protected-task policy and the Darwin launch task-port prerequisite. No raw runtime refusal is claimed. Reports `/private/tmp/analytics-query-feature-integration-audit/NATIVE-HOST-PREFLIGHT.md` and `/private/tmp/analytics-query-native-launch-policy-debug/REPORT.md` preserve metadata and primary-source reasoning. Zero native launches/workloads consumed. The proposed alternative is one initial attachment to the exact parent-owned, nonce-gated, already sandboxed Python PID, preserving every bound and protection; its scope and actual attach permission remain unapproved/unverified. Do not silently use it as a fallback or infer a numeric fixture fix.

## How to pick it up

0. Maintainer approved the bounded owner decision on 2026-10-08: task 2.3 is reopened as prerequisite to 8.2. That allowance is now exhausted without a correction. Obtain a new explicit diagnostic decision before any workload; read the amended task/design contract before diagnostics. The allowance is at most two baseline captures per runtime (1.2.0/current1.5.6) and one evidence-supported contrast per failing runtime; stop if no causal evidence. Preserve dependency declaration and production settings. No numeric adjustment is established, and floor rerun waits for independently reviewed owning correction.

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

## Update 2026-10-08: measured sweep and test-contract revision

- Fresh-process sweep through `open_sandboxed` on duckdb 1.2.0 and 1.5.6 (receipts `/Users/josh/code/fitdocs-private-evidence/analytics-query-2.3-revision/`, all `*.jsonl`): the sorted group-by (3M rows, 750k buckets) on 1.2.0 OOMs at 48MB (12/12) and 64MB (7/12) and above that finishes without ever writing a spill file; on 1.5.6 it spills at 48-128MB but OOMed 1/12 at 96MB. Rows/bucket sweeps never produced a 1.2.0 witness. No measured limit (48-256MB, plus the rows/buckets grid) satisfies spill-witness plus no-OOM on both runtimes for that query.
- A pure sort (`ORDER BY (i*2654435761) % 1000003 DESC, i`) spills with exact results and no OOM in 15/15 runs at 48MB and 64MB on both runtimes; the window/four-process test does too. The fixture now uses that sort at one named constant of 64MB.
- OOM cause on 1.2.0 remains UNKNOWN; this is not a causal correction.
- Status: resolved by test-contract revision, pending review. Left open (not moved to closed/).

## Resolution (2026-10-08) — done

Resolved by a maintainer-approved, measured test-contract revision, not by a
causal fix. The spill witness is now a pure `ORDER BY` at the shared
`_SPILL_MEMORY_LIMIT = "64MB"` in `tests/query/test_spill.py`; 48MB also
passes on both runtimes (one step of margin). Independently reviewed and
accepted as analytics-query task 2.3 (7488ca2; 0d98f45 pre-rebase). On duckdb
1.2.0 the old sorted group-by either runs out of memory (48MB 12/12, 64MB
7/12) or completes in memory without spilling (96–256MB), so no measured
limit gives a spill witness without OOM. The OOM cause on 1.2.0 remains
UNKNOWN; production settings and the dependency floor are unchanged.
