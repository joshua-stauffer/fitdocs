---
id: 2026-10-13-chart-sql-kind-refusal-drops-the-query-layers-advice
title: A chart whose SQL is a CALL, LOAD or SET statement loses the query layer's advice and display name, because binding builds its own statement-kind refusal
status: open
importance: low
importance_why: The chart author still learns the statement was refused; they lose the one-line `use SELECT * FROM <function>(...) instead` for CALL and read `LOAD`/`SET` where `fitdocs query` says `INSTALL or LOAD` / `SET, RESET or USE`.
effort: S
kind: inconsistency
area: dashboards, analytics-query, src/fitdocs/dashboards/binding.py, src/fitdocs/query/statement.py
created: 2026-10-13
surfaced_by: /kiro-impl dashboards (task 4.3 reviewer)
pinned_at: 0a98d5c
resume_command: "do: have dashboards.binding._kind_refusal append the CALL advice and use the same display names as query.statement.statement_kind_refusal, or reuse its pieces, keeping the chart-specific lead sentence (ruling R4); update the 4.3 tests [queue: .kiro/queue/2026-10-13-chart-sql-kind-refusal-drops-the-query-layers-advice.md]"
context:
  - src/fitdocs/dashboards/binding.py
  - src/fitdocs/query/statement.py
  - tests/dashboards/test_binding.py
  - .kiro/specs/dashboards/tasks.md
blocked_by:
  - dashboards
---

## What
Under controller ruling R4 (`.kiro/specs/dashboards/tasks.md`, the 4.3 note at
line 1395), refusals at the screen stage use binding's own chart message
instead of the query layer's `RESTRICTION_TEXT`, because the latter ("runs only
queries and EXPLAIN") misleads a chart author. The replacement,
`_kind_refusal` (`src/fitdocs/dashboards/binding.py:133`), prints the raw
statement kind. The query layer's `statement_kind_refusal`
(`src/fitdocs/query/statement.py:48`) does two extra things that chart authors
lose: a display name for `LOAD` and `SET`, and the `CALL` hint.

## Why it matters
A chart written with `CALL some_function()` is refused with no pointer to the
working form, and the message names `LOAD` or `SET` where the same refusal in
`fitdocs query` is clearer. It is a small, user-visible difference between two
commands that screen the same statements.

## Evidence
Run against 0a98d5c:

```
CALL   | a chart runs exactly one SELECT statement; this is a CALL statement
       | the query sandbox runs only queries and EXPLAIN; this is a CALL statement; use SELECT * FROM <function>(…) instead
LOAD   | a chart runs exactly one SELECT statement; this is a LOAD statement
       | the query sandbox runs only queries and EXPLAIN; this is an INSTALL or LOAD statement
SET    | a chart runs exactly one SELECT statement; this is a SET statement
       | the query sandbox runs only queries and EXPLAIN; this is a SET, RESET or USE statement
```

(first line of each pair: `binding._kind_refusal`; second: `query.statement.statement_kind_refusal`.)
The `sql_refused` fix text for these is `Give the chart exactly one SELECT statement.` (`binding.py:_ONE_SELECT_FIX`).

## How to pick it up
1. Read `_kind_refusal` (`binding.py:133-137`) and `statement_kind_refusal` (`statement.py:48-60`).
2. Keep the chart-specific lead sentence from R4. Factor the display-name map and the CALL advice so both callers share them (a small public helper in `query/statement.py`), or copy them with a test that pins equality.
3. Update the 4.3 binding tests for CALL, LOAD and SET and the docs/skill wording if they quote the message. Done means a chart with `CALL f()` is refused with the `SELECT * FROM <function>(...)` advice.
