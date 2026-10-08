---
id: 2026-10-08-store-facade-user-interrupt-unwrapped
title: Map DuckDB's user-interrupt RuntimeError to a named store-facade error
status: open
importance: medium
importance_why: Every facade consumer must special-case a raw RuntimeError on Ctrl-C, or it hangs on close; analytics-query already had to.
effort: S
kind: gap
area: analytics-index, src/fitdocs/index/store.py
created: 2026-10-08
surfaced_by: /kiro-validate-impl analytics-query (smoke dimension, SIGINT probe)
pinned_at: 646f42c
resume_command: "/kiro-spec-requirements analytics-index [queue: .kiro/queue/2026-10-08-store-facade-user-interrupt-unwrapped.md] map the DuckDB user-interrupt RuntimeError to a named facade error and interrupt before close"
context:
  - .kiro/specs/analytics-index/design.md
  - src/fitdocs/index/store.py
  - src/fitdocs/query/statement.py
  - src/fitdocs/query/command.py
blocked_by: []
---

## What
On duckdb 1.5.6, SIGINT during a running statement surfaces from
`relation.fetchmany` as `RuntimeError('Query interrupted')` with a
`KeyboardInterrupt` `__cause__`. It is not a `duckdb.Error`. The facade wraps
only `duckdb.Error` and `duckdb.InterruptException`
(`src/fitdocs/index/store.py`, `_DuckDBErrorTypes(duckdb.Error,
duckdb.InterruptException)` in the connect helper; `fetchmany` catches only
`self._errors.error_type`). The raw RuntimeError therefore escapes the facade.
In addition, a connection whose statement was interrupted this way blocks in
`close()` (DuckDB `ClientContext` destructor → `Executor::CancelTasks`) unless
`interrupt()` is called first.

## Why it matters
The facade's contract is that consumers see named errors, never raw DuckDB
types. Each consumer currently has to discover this shape on its own, and
missing it means a hung process on Ctrl-C. analytics-query hit exactly that:
4 of 5 real CLI runs hung for 40 s or more during its 2026-10-08 feature
validation. It is being handled locally on `impl/analytics-query`
(remediation round 1).

## Evidence
- The validation reviewer's probes (private, outside the repo):
  `~/code/fitdocs-private-evidence/analytics-query-validate/smoke/probe/sigint_probe3.py`
  and `sigint_probe4.py`. `close()` without interrupt hung for more than 20 s
  in 7/7 runs across four query shapes; with `conn.interrupt()` first it
  returned in 0.0 s, 7/7.
- A faulthandler dump of the hung CLI: main thread at `store.py` `close` ←
  `query/command.py` `run_query` `finally`.
- Reported by validation reviewer subagents and not re-run by the parent.
  The code shape was verified by reading `store.py` at 646f42c.

## How to pick it up
1. Read the analytics-index design's error-mapping section, and `store.py`'s
   `IndexConnection` and `_DuckDBErrorTypes`.
2. Decide the facade shape. One option: map
   `RuntimeError` whose `__cause__` is a `KeyboardInterrupt` to a named error
   (or re-raise `KeyboardInterrupt`), and have `IndexConnection.close()` call
   `interrupt()` when a statement may still be running. Check the same
   behavior on duckdb 1.2.0, the declared floor.
3. Once the facade owns it, remove the local special-case from
   `src/fitdocs/query/` and keep the real-process SIGINT test there green.
   Done means: a facade-level test with a real interrupted statement shows
   the named error and a non-hanging close.
