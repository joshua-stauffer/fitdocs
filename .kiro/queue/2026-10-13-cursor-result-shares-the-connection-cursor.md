---
id: 2026-10-13-cursor-result-shares-the-connection-cursor
title: A cursor-backed IndexResult from execute_named is the connection's own cursor, so a second execute_named silently replaces the first result's columns and rows
status: open
importance: low
importance_why: No shipped caller holds two results at once (QuerySession consumes each statement before the next), so the trap is latent; the next consumer of execute_named inherits it with no warning.
effort: S
kind: gap
area: analytics-index, src/fitdocs/index/store.py, src/fitdocs/query/command.py
created: 2026-10-13
surfaced_by: /kiro-impl dashboards (task 2.1 reviewer)
pinned_at: 0a98d5c
resume_command: "do: either document 'one live result per connection' on IndexConnection.execute_named and _CursorResult, or capture the column description when the result is built and make a result read after a later execute fail loudly; pin it with a two-result test [queue: .kiro/queue/2026-10-13-cursor-result-shares-the-connection-cursor.md]"
context:
  - src/fitdocs/index/store.py
  - src/fitdocs/query/command.py
  - tests/index/test_store.py
  - .kiro/specs/analytics-index/design.md
blocked_by:
  - dashboards
---

## What
`IndexConnection.execute_named` (`src/fitdocs/index/store.py:187`) returns
`IndexResult.from_cursor(cursor, ...)`, a `_CursorResult` (`store.py:146`) whose
`columns`, `fetchmany` and `fetchall` all read `self._cursor`, which is the
DuckDB connection itself (`connection.execute(...)` returns the connection).
A second `execute_named` on the same connection therefore changes what the
earlier result reports. The relation-backed result that positional `execute`
returns does not have this property, so the two result types behave
differently under the same interface.

## Why it matters
Anything that opens two results on one connection and reads them in turn gets
the second statement's columns and rows from the first handle, with no error.
`QuerySession` avoids it by consuming each statement before the next
(`src/fitdocs/query/command.py:398-404` says so), but that invariant is
documented only there.

## Evidence
Probe `/private/tmp/claude-501/-Users-josh-code-fitdocs-oss/e6978888-5f66-4ba4-8392-5c49f509f8bf/scratchpad/2.1-reviewer/probe.py`
(the /private/tmp path is wiped on reboot; the output is quoted so the claim
survives). Re-run in this item's session against 0a98d5c, duckdb 1.5.6:

```
r1 cols (ResultColumn(name='a', type_name='BIGINT'), ResultColumn(name='b', type_name='VARCHAR'))
r1 cols after r2 (ResultColumn(name='z', type_name='DOUBLE'),)
r1 fetch after r2 [(2.5,)]
```

`r1` was `SELECT 1::BIGINT AS a, 'x' AS b`; `r2` was `SELECT 2.5::DOUBLE AS z`.
After `r2` ran, `r1` reports `r2`'s column and returns `r2`'s row.

## How to pick it up
1. Read `IndexResult`, `_CursorResult` and `execute_named` in `src/fitdocs/index/store.py` (lines 100-200) and the `QuerySession` docstring in `src/fitdocs/query/command.py`.
2. Pick one. Cheapest: state "one live result per connection" in the docstrings of `execute_named` and `_CursorResult`. Stronger: capture `description` at construction, and have a stale `_CursorResult` raise when read after a later `execute_named` (a generation counter on the connection).
3. Add a test with two `execute_named` results on one connection that fails under the old behaviour. Done means the behaviour is either documented and pinned by the test, or refused.

## Open questions
Whether the facade should refuse (stronger) or only document. The 2.1 reviewer rated it low.
