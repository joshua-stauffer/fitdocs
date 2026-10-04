---
id: 2026-10-05-history-negative-load-uncaught-traceback
title: A negative load_value in a workout page makes `fitdocs history` crash with an uncaught ValueError
status: open
importance: medium
importance_why: One hand-edited or plugin-written negative load turns `fitdocs history` into a traceback, and in Phase 10 a refresh failure of derived.load_series.
effort: S
kind: bug
area: load-history, src/fitdocs/history/documents.py, src/fitdocs/history/model.py, src/fitdocs/cli.py
created: 2026-10-05
surfaced_by: /kiro-spec-batch phase 10 (analytics-derived spec writer)
pinned_at: 19fc92e
resume_command: "/kiro-spec-requirements load-history [queue: .kiro/queue/2026-10-05-history-negative-load-uncaught-traceback.md] Decide how a negative load_value is read (skip as unreadable vs report) and stop it reaching run_model"
context:
  - src/fitdocs/history/documents.py
  - src/fitdocs/history/model.py
  - src/fitdocs/cli.py
  - .kiro/specs/load-history/requirements.md
blocked_by: []
---

## What
`history/documents.py:147-159` (`_read_load`) accepts any finite float,
negatives included. `history/model.py:67-80` (`_require_nonnegative_finite`,
via `_validate_inputs`) raises `ValueError` for a negative daily load, and
`cli.py:715-722` (`history`) catches only `SettingsError`. Result: an
uncaught traceback. No test covers a negative `load_value`.

## Why it matters
Frontmatter is hand-editable and plugin calculators can emit any float. A
single bad page takes down the whole history command (and, once
analytics-derived lands, the `derived.load_series` corpus producer).

## Evidence
- `history/documents.py:147-159` at 19fc92e: only `isinstance` + `math.isfinite` checks.
- `history/model.py:67-71`: `if not math.isfinite(value) or value < 0: raise ValueError(...)`.
- `cli.py:716-722`: `except SettingsError as exc:` only.

## How to pick it up
1. Read load-history requirements for how unreadable loads are treated (Req 4.x) -- a negative load is probably "unreadable", returned as `(None, None)` with the page counted as skipped.
2. Fix at the reader, not the CLI, so every consumer (history page, derived producer) agrees.
3. Add a page fixture with `load_value: -5` and assert the page is skipped and reported, not raised.
