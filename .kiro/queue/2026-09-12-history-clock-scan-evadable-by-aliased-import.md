---
id: 2026-09-12-history-clock-scan-evadable-by-aliased-import
title: The history clock-scan guard matches substrings, so `import datetime as _dt; _dt.date.today()` passes it
status: open
importance: medium
importance_why: Req 1.x's "no wall clock in the history package" is enforced only against the spellings the guard lists; an alias or `from datetime import date as d` is a one-line bypass and the guard reports green.
effort: S
kind: gap
area: load-history, tests/history/test_boundary.py
created: 2026-09-12
surfaced_by: /kiro-impl load-history 5.6 (reviewer round 1, FOLLOW_UPS)
pinned_at: 8cd0062
resume_command: "do: rewrite TestClockScan in tests/history/test_boundary.py as an AST walk that resolves aliases (ast.Import/ImportFrom asname) and flags any Call whose resolved attribute chain ends in datetime.now/date.today/time.time/time.monotonic/perf_counter, with a positive control that the walk catches an aliased fixture module"
context:
  - tests/history/test_boundary.py
  - src/fitdocs/history/
blocked_by: []
---

## What
`TestClockScan` greps source text for `datetime.now(`, `date.today(`,
`time.time(` and similar. The 5.6 reviewer probed `import datetime as _dt`
plus `_dt.date.today()` into a temp copy of `series.py`: the scan passed.
The same holds for `from datetime import date as D; D.today()`.

## Evidence
5.6 review round 1 finding B (downgraded to FOLLOW_UP because the guard's
positive controls all pass and no shipped module aliases).

## How to pick it up
Same shape as the `test_bytecode_hygiene`/consumer-guard AST walks. Keep the
existing substring scan as a cheap first pass if you like; the AST walk is
the guard. Add the aliased positive control so the walk itself is pinned.
