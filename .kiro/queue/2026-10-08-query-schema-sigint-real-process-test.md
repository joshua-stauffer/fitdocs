---
id: 2026-10-08-query-schema-sigint-real-process-test
title: Add a real-process SIGINT case for `fitdocs query --schema`
status: open
importance: low
importance_why: The --schema interrupt is only pinned by fake-read unit tests; a real DuckDB shape change there would go unnoticed.
effort: S
kind: gap
area: analytics-query, tests/query/test_interrupt.py
created: 2026-10-08
surfaced_by: /kiro-validate-impl analytics-query
pinned_at: cc4af5b
resume_command: "do: add a real-process SIGINT case for `fitdocs query --schema` [queue: .kiro/queue/2026-10-08-query-schema-sigint-real-process-test.md]"
context:
  - tests/query/test_interrupt.py
  - tests/query/test_command.py
  - src/fitdocs/query/command.py
  - .kiro/specs/analytics-query/design.md
blocked_by: []
---

## What
`tests/query/test_interrupt.py` has one real-process test (`test_sigint_during_running_statement_exits_cleanly`, line 151) covering the statement path only. Ctrl-C during a slow `--schema` read (bookkeeping, catalog, row counts, athlete drift) is pinned only by `test_schema_read_interrupt_interrupts_then_closes_and_raises_keyboard_interrupt` in `tests/query/test_command.py`, which uses a fake connection.

## Why it matters
The statement-path hang was found only because real DuckDB behaved differently from the fake; the schema path carries the same risk.

## Evidence
Re-validation (2026-10-08) verified the schema path by a private probe only: 11 real-CLI trials on 1.5.6 and 3 on 1.2.0, all exit 130 (`~/code/fitdocs-private-evidence/analytics-query-revalidate/probe/schema.txt`). Reported by the validation reviewer; the test-file shape was verified by grep at the pinned commit.

## How to pick it up
Add a parametrized case to `test_interrupt.py` that replaces one schema-path read in the child with a genuinely long DuckDB statement on the live connection, then sends SIGINT. Reuse the existing marker, timeout and killpg harness, and run it on 1.5.6 and the 1.2.0 floor. Done means: removing `run_query`'s conversion in `command.py` reds it.
