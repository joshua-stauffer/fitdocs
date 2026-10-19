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
resume_command: "do: land the finished fix on origin/chore/q-history-unreadable (shared with 2026-09-12-history-unreadable-document-skipped-silently) -- rebase onto main, resolve the CHANGELOG.md conflict, re-run the three gates, merge per change-protocol.md, then close both items"
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

## Update 2026-10-19 -- reproduced at HEAD; a finished fix exists and never landed

The 0.2 release-readiness triage reproduced the crash at `4f1c1f4` on a scratch
data root (reported by a reviewer subagent): `fitdocs history` ends in a Rich
traceback, `ValueError: daily_loads[0] must be a finite, non-negative number`,
while `fitdocs index` handles the same page ("Could not refresh
derived.load_series"). Present in `v0.1.0` too, so not a 0.2 regression.

The fix is on `origin/chore/q-history-unreadable`, unlanded: `ceeae9c`, then
`a3db1e6 fix(history): treat a negative load like a non-finite one (no load,
page kept)` and `7c3e7ac`, with plan-resolution Amendment 3 in `0336650`. See
`2026-09-12-history-unreadable-document-skipped-silently` § Update 2026-10-19
for the branch state and merge-conflict evidence.
