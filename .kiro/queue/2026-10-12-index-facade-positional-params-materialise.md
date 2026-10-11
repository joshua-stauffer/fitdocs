---
id: 2026-10-12-index-facade-positional-params-materialise
title: Positional IndexConnection.execute still routes params through .sql(params=), which materialises the whole result before fetchmany caps it
status: open
importance: low
importance_why: No shipped caller reads a large result through it today, since the writer statements return no rows and athlete_drift is a one-row count, but the next positional read of a big table inherits a 7 GB / 21 s-interrupt trap silently.
effort: S
kind: gap
area: analytics-index, src/fitdocs/index/store.py
created: 2026-10-12
surfaced_by: /kiro-spec-batch phase 11 (dashboards Step 3.5 RETURN_TO_DESIGN, controller ruling)
pinned_at: e340d15
resume_command: "do: decide whether positional IndexConnection.execute should also stream (connection.execute(sql, params) + cursor fetchmany) once dashboards' execute_named has landed; if so, migrate it under the change ritual with the existing writer tests unedited and a child-process RSS-growth test like dashboards task 2.1, otherwise document the hazard in the facade's docstring"
context:
  - src/fitdocs/index/store.py
  - src/fitdocs/query/freshness.py
  - .kiro/specs/dashboards/design.md
  - .kiro/specs/dashboards/tasks.md
  - .kiro/specs/analytics-index/design.md
blocked_by:
  - dashboards
---

## What
`IndexConnection.execute(sql, params: Sequence[object] = ())` runs
`self._connection.sql(sql, params=params)` (`src/fitdocs/index/store.py:146-151`).
The Phase 11 discovery viability probe found that the `.sql(..., params=)` path
materialises the whole result before `fetchmany` caps it. On duckdb 1.5.6, 60M
rows reached 7 GB, and a 2 s interrupt landed at 21 s. The dashboards writer
measured about 255 MB of RSS growth at 5M rows, against 42 MB peak through
`connection.execute` + `fetchmany`.

The dashboards spec first tried to switch `execute` itself to a `Mapping`. That
would have broken every index write: the writer binds positional `$1` through
`execute` at `store.py:400, 426, 486, 500, 513, 523, 524`, and tests monkeypatch
the `Sequence` signature. The controller ruled that dashboards adds a separate
`execute_named(sql, Mapping)` that streams, and leaves positional `execute`
unchanged. analytics-index Amendment 1, carried by dashboards, states this
residual as out of scope. This item is that residual.

## Why it matters
The only positional read today is `query/freshness.py:119` (`athlete_drift`), a
one-row `count(*)`. Nothing breaks now. But the facade's positional method looks
equivalent to `execute_named`, and a future caller that reads a large result
through it gets full materialisation and a slow interrupt, with no warning at
the call site.

## Evidence
- `src/fitdocs/index/store.py:146-151`: `relation = self._connection.sql(sql, params=params)`.
- Roadmap Phase 11 › Viability, "`$today` under the sandbox" › Issue: 60M rows → 7 GB, interrupt 2 s → 21 s on 1.5.6.
- `.kiro/specs/dashboards/research.md` and `design.md` § Upstream amendments › IndexFacade record the false "only caller" claim, the correction, and the 5M-row RSS probe.
- `.kiro/steering/roadmap.md` Phase 11 › Existing Spec Updates, analytics-index line (corrected 2026-10-12).

## How to pick it up
1. Wait until dashboards has landed `execute_named` and `IndexResult.from_cursor` (dashboards task 2.1).
2. Check whether `connection.execute(sql, list_params)` + cursor `fetchmany` gives the writer statements (`INSERT … $1` JSON batch, `DELETE … $1`) identical behaviour on duckdb 1.2.0 and the current version. Run DuckDB probes under `sandbox-exec` with network denied and a fresh HOME.
3. If it does, route positional params through the cursor path too, and keep every existing store test unedited. If it doesn't, put the hazard in `execute`'s docstring and name `execute_named` as the read path.

## Open questions
- Is a second public read method enough of a signpost, or should positional reads be forbidden outside the writer?
