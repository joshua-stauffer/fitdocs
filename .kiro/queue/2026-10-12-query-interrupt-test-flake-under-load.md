---
id: 2026-10-12-query-interrupt-test-flake-under-load
title: test_sigint_during_running_statement_exits_cleanly[join] failed once under machine load
status: open
importance: low
importance_why: One failure in one full run under heavy parallel load; passed alone and in a full re-run.
effort: S
kind: bug
area: analytics-query tests/query/test_interrupt.py
created: 2026-10-12
surfaced_by: full suite on fix/chart-kit-dual-axis-title-room
pinned_at: c52da2d
resume_command: "do: run tests/query/test_interrupt.py under CPU load (e.g. alongside a full suite) ~20 times and harden its timing if it flakes"
context:
  - tests/query/test_interrupt.py
  - .kiro/specs/analytics-query/design.md
blocked_by: []
---

## What
During the chart-catalog run (2026-10-12) a full `uv run pytest -x -p no:randomly` on branch fix/chart-kit-dual-axis-title-room failed `tests/query/test_interrupt.py::test_sigint_during_running_statement_exits_cleanly[join]` while seven agents were running test suites; the test passed alone (2 passed, 15.8 s) and the full suite then passed (11461 passed).

## Why it matters
A real-process SIGINT timing test that flakes under load will eventually red CI; the impl-dashboards session separately logged a DuckDB interrupt race under CPU load (agent-log WARN 2026-10-12T17:14).

## Evidence
Observed directly by the controller (output not preserved beyond the failing test id). Related: queue `2026-10-08-store-facade-user-interrupt-unwrapped`.

## How to pick it up
Read the test's timing (how it waits for the statement to be running before SIGINT). Reproduce under load; if it flakes, wait on an observable readiness signal instead of a sleep, or accept the race's alternate exception class as dashboards found.
