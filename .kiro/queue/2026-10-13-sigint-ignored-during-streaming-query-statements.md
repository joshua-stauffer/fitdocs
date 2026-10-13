---
id: 2026-10-13-sigint-ignored-during-streaming-query-statements
title: Ctrl-C does not stop `fitdocs query` while a streaming (non-aggregating) statement runs; it hangs for 20 s or more on duckdb 1.5.6, although --timeout works
status: open
importance: medium
importance_why: A user who types a slow cross join and hits Ctrl-C gets no exit, against analytics-query Req 6.6; every real-process interrupt test uses an aggregating statement, so the suite is green over it.
effort: M
kind: bug
area: analytics-query, src/fitdocs/query/statement.py, src/fitdocs/query/command.py, src/fitdocs/index/store.py
created: 2026-10-13
surfaced_by: /kiro-impl dashboards (task 2.2 review; reproduced against the real CLI in the queue-writing session)
pinned_at: 0a98d5c
resume_command: "/kiro-spec-design analytics-query [queue: .kiro/queue/2026-10-13-sigint-ignored-during-streaming-query-statements.md] make a user interrupt stop a streaming non-aggregating statement"
context:
  - src/fitdocs/query/statement.py
  - src/fitdocs/query/command.py
  - src/fitdocs/index/store.py
  - tests/query/test_interrupt.py
  - tests/dashboards/test_interrupt.py
  - .kiro/specs/analytics-query/requirements.md
  - .kiro/specs/analytics-query/design.md
  - .kiro/queue/2026-10-08-store-facade-user-interrupt-unwrapped.md
blocked_by: []
---

## What
`fitdocs query` reads a statement's first rows with `result.fetchmany(...)` on
the main thread (`src/fitdocs/query/statement.py:202`). Measured: with a
streaming statement the process stays in that call after SIGINT, so the
command's interrupt handling (interrupt the connection, close, exit 130) does
not run; with an aggregating statement it is honoured at once. The likely cause
(inferred from the evidence below, not checked in DuckDB's source) is that
DuckDB sits inside the call without returning to the Python interpreter, so the
pending signal is not turned into `KeyboardInterrupt` until the call returns.
The statement deadline (`--timeout`) is unaffected, which fits: its timer
thread calls `interrupt()` from another thread.

`fitdocs dashboard` shares the machinery: it runs chart SQL through
`QuerySession`, and its own interrupt test was written around an aggregating
statement for this reason (`tests/dashboards/test_interrupt.py:67-71`).

## Why it matters
Req 6.6 of analytics-query (`.kiro/specs/analytics-query/requirements.md:173`) is "if the user interrupts `fitdocs query`, then
fitdocs shall stop the statement and close the index before exiting". For a
streaming statement that does not hold, and the failure is a process that
ignores Ctrl-C while burning CPU. The hang is also intermittent, which is what
let it past the tests.

## Evidence
All run against 0a98d5c (this worktree), duckdb 1.5.6, macOS arm64, Python 3.11,
isolated `HOME`/`FITDOCS_INDEX_DIR`/`TMPDIR`, an index built over an empty
data root. Probe scripts were in the session scratchpad under
`/private/tmp/claude-501/-Users-josh-code-fitdocs-oss/43144b56-a94d-45f3-a857-8e0a466250cf/scratchpad/`
(`cli_sigint.py`, `cli_sigint_dbg.py`, `cli_timeout.py`) and
`/private/tmp/claude-501/-Users-josh-code-fitdocs-oss/e6978888-5f66-4ba4-8392-5c49f509f8bf/scratchpad/db-2-2-review/`
(`sigint_child.py`, `sigint_parent.py`). `/private/tmp` is wiped on reboot, so
the observed output is quoted here.

1. Real CLI, SIGINT 3.0 s after start, 20 s bound, 3 trials per shape
   (`fitdocs query "<sql>" --out <root> --timeout 300`):
   ```
   agg trial 0..2:    exit 130 in 0.0s  stderr='Query interrupted.'   (3 of 3)
   stream trial 0:    exit 130 in 0.0s  stderr='Query interrupted.'
   stream trial 1:    NO EXIT within 20s of SIGINT (killed)
   stream trial 2:    NO EXIT within 20s of SIGINT (killed)
   ```
   agg = `SELECT sum(a.range * b.range) FROM range(100000000) a, range(100000000) b`
   (this is `_JOIN_STATEMENT` in `tests/query/test_interrupt.py:55`).
   stream = `SELECT a.range FROM range(1000000000) a, range(1000000) b WHERE (a.range * b.range) % 1000000007 = 3`.
2. Where the hung process sits (faulthandler dump on SIGUSR1; 3 of 3 runs hung):
   `src/fitdocs/index/store.py:126 in fetchmany` <- `src/fitdocs/query/statement.py:202 in execute_statement` <- `statement.py:274 in run_statement` <- `src/fitdocs/query/command.py:266 in run_query` <- `src/fitdocs/cli.py:2017 in query_command`.
3. The deadline still works on the same statements (`--timeout 3`, 2 trials each):
   `agg trial 0: exit 1 after 3.2s stderr='Query stopped: it ran longer than 3 s. Narrow it, or raise --timeout.'`, and the same for the other three trials, `stream` included.
4. Raw DuckDB, no fitdocs code, SIGINT 1.5 s in, no `interrupt()` call, 20 s bound:
   ```
   duckdb 1.5.6   stream cursor    -9 20.0 [TIMEOUT-killed]
   duckdb 1.5.6   stream relation  -9 20.0 executed | EXC RuntimeError: Query interrupted <- KeyboardInterrupt | [TIMEOUT-killed]
   duckdb 1.5.6   agg cursor        0  0.0 EXC RuntimeError: Query interrupted <- KeyboardInterrupt
   duckdb 1.5.6   agg relation      0  0.0 executed | EXC RuntimeError: Query interrupted <- KeyboardInterrupt
   duckdb 1.2.0   stream cursor    -9 20.0 [TIMEOUT-killed]
   duckdb 1.2.0   stream relation  -9 20.0 executed | EXC RuntimeError: Query interrupted <- KeyboardInterrupt | [TIMEOUT-killed]
   duckdb 1.2.0   agg cursor        0  0.0 EXC RuntimeError: Query interrupted <- KeyboardInterrupt
   duckdb 1.2.0   agg relation     -9 20.0 executed | EXC RuntimeError: Query interrupted <- KeyboardInterrupt | [TIMEOUT-killed]
   ```
   ("cursor" is `con.execute`, "relation" is `con.sql` then `fetchmany`; the
   1.2.0 venv was `.../db-2-1-impl/venv12`.) The 2.2 reviewer reported that on
   1.2.0 every path hangs; this re-run found the aggregating cursor path
   honoured and the other three hung, so the exact 1.2.0 matrix is unsettled.
   A "stream relation" or "agg relation" line that prints `EXC` and still times
   out is the connection teardown blocking after the exception, which is the
   separate close() hang in `2026-10-08-store-facade-user-interrupt-unwrapped`.
5. Test-suite coverage: `tests/query/test_interrupt.py:55-57` and
   `tests/dashboards/test_interrupt.py:67-71` both pick an aggregating
   statement; neither tests a streaming one.

## How to pick it up
1. Trap to avoid: run any SIGINT probe from a foreground shell. A job started with `&` inherits SIGINT as ignored, Python then installs no KeyboardInterrupt handler, and every case hangs, which looks exactly like this bug. The first runs in the writing session were fooled by this.
2. Read `execute_statement` in `src/fitdocs/query/statement.py` (lines 170-230), the interrupt branches in `src/fitdocs/query/command.py` (lines 280-290), and the 2.2 notes in `.kiro/specs/dashboards/tasks.md` (search "aggregat").
3. Hypothesis, not verified: the signal is pending until DuckDB returns, because the main thread is inside C++. The deadline works because it interrupts from a timer thread. A fix in that shape runs the fetch on a worker thread while the main thread waits interruptibly (for example `Event.wait` or `thread.join` in a loop), and on `KeyboardInterrupt` calls `connection.interrupt()` and joins. Check it on 1.5.6 and on the 1.2.0 floor.
4. Add a streaming-statement case to `tests/query/test_interrupt.py` (and to `tests/dashboards/test_interrupt.py`, which can then drop its aggregating-only comment). Repeat trials: the hang is intermittent (1 of 3 passed above). Done means 14 consecutive trials exit 130 within the bound on both versions.

## Open questions
Whether the fix belongs in the store facade (so `fitdocs dashboard` and any future consumer get it) or in `statement.py`. `2026-10-08-store-facade-user-interrupt-unwrapped` argues for the facade owning interrupt handling; decide the two together.
