---
id: 2026-09-17-req-8-5-write-nothing-pinned-on-output-only
title: Req 8.5's "shall write nothing" for a chained pass with no plan directory is pinned on CLI output, never on files
status: open
importance: medium
importance_why: The reconciling pass runs on every chained sync/regen even with no plan directory; an idempotent write to workouts/ or a plans/ creation during that pass is invisible to every test that exercises it.
effort: S
kind: gap
area: plan-resolution, tests/test_cli_reconcile.py, tests/test_reconcile_e2e.py
created: 2026-09-17
surfaced_by: /kiro-impl plan-resolution (task 3.5 round-2 review)
pinned_at: fbba78b
resume_command: "do: in the three no-plan-directory quiet tests of tests/test_cli_reconcile.py, snapshot the data root (all files, bytes) before the run and assert equality after, so an idempotent write or a plans/ creation by the chained pass reds"
context:
  - tests/test_cli_reconcile.py
  - tests/test_reconcile_e2e.py
  - src/fitdocs/plans/reconcile.py
blocked_by: []
---

## What
The quiet pins compare `baseline.output == stubbed.output`; no test hashes
files around a chained pass over a root with no plan directory. The e2e
sync-first scenarios bracket only after the setup sync.

## Evidence
- 3.5 round-2 review probes: an idempotent `<!-- r -->` append to every workout page from `run_reconcile` → 3/8 e2e red (plan-only scenarios), the three sync scenarios green; `plans/` + stable marker created by the pass → 5/8.

## How to pick it up
1. Add a `_snapshot`-style bracket around the three quiet tests (and the e2e setup sync) covering the whole data root minus the run's own legitimate outputs.
2. Run the two probes; both must red.
