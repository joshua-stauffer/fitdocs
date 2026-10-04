---
id: 2026-10-05-config-error-docstring-wrong-for-chained-passes
title: cli._config_error docstring claims nothing was written at any call site, but chained passes exit 2 after sync/load wrote
status: open
importance: low
importance_why: A docstring that instructs maintainers wrongly about write state; prose that instructs an agent is behavior here.
effort: S
kind: docs
area: src/fitdocs/cli.py
created: 2026-10-05
surfaced_by: /kiro-spec-batch phase 10 (analytics-index spec writer)
pinned_at: 19fc92e
resume_command: "do: under the change ritual, reword cli.py _config_error's docstring so it says which call sites precede every write and that chained passes (plan/reconcile after sync, load) may exit 2 after documents were written; cite tests/test_cli_reconcile.py::test_malformed_history_table_exits_two"
context:
  - src/fitdocs/cli.py
  - tests/test_cli_reconcile.py
blocked_by: []
---

## What
`src/fitdocs/cli.py:1724-1731`: "Nothing has been written at any call site
... so a configuration error leaves the data root untouched." But
`tests/test_cli_reconcile.py:434-445` runs `sync`, which writes pages and then
exits 2 on a malformed `[history]` table in the chained pass.

## Why it matters
A later session relying on the docstring (e.g. the Phase 10 index post-pass,
which runs after writing commands) would assume a config error means no
write happened.

## Evidence
- `cli.py:1726-1728` at 19fc92e (docstring text above).
- `tests/test_cli_reconcile.py:434-445`: `_first_sync`, malformed `[history]`, then `sync` exits 2.

## How to pick it up
1. List `_config_error` call sites (`grep -n _config_error src/fitdocs/cli.py`) and classify each as pre-write or post-write.
2. Reword the docstring to match; no behavior change.
