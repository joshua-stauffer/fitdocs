---
id: 2026-11-01-connect-prompt-suffix-and-ctrl-c-exit
title: '`fitdocs connect` doubles the prompt colon and exits 1 on Ctrl-C for non-relay instances'
status: open
importance: low
importance_why: Cosmetic output defect plus an exit-code inconsistency with the relay path (130).
effort: S
kind: bug
area: src/fitdocs/cli.py
created: 2026-11-01
surfaced_by: /kiro-impl relay-server 6.6 review (pre-existing, connectors 5.1)
pinned_at: 774a883c
resume_command: "/kiro-impl relay-server [queue: .kiro/queue/2026-11-01-connect-prompt-suffix-and-ctrl-c-exit.md] Fix the doubled prompt suffix and non-relay Ctrl-C exit code"
context:
  - src/fitdocs/cli.py
  - tests/connectors/test_cli_connectors.py
blocked_by: []
---

## What
(1) `_ask_value(prompt)` passes a prompt that already ends in `: ` to `typer.prompt`, which appends its own `prompt_suffix=": "`, so the user sees `Label: : `. (2) The non-relay prompt loop is outside any try, so Ctrl-C reaches typer as `Abort` and exits 1 with "Aborted."; the relay path catches the interrupt and exits 130.

## Why it matters
Visible rough edge on the first command a new user runs, and two instance types disagree on interrupt exit codes.

## Evidence
- `src/fitdocs/cli.py:1319-1321` `_ask_value`; `:1561-1562` builds `prompt = f"{credential_field.label}: "` and calls it.
- CliRunner: `typer.prompt('Email address: ')` returned output `Email address: : x@y.org`.
- `src/fitdocs/cli.py:1399-1400` (relay path catches `typer.Abort`) versus `:1555-1565` (no handler); `:345` `_EXIT_INTERRUPTED = 130`.

## How to pick it up
1. Drop the trailing `: ` from the prompt strings (or pass `prompt_suffix=""`).
2. Wrap the non-relay prompt loop in the same interrupt handling and exit 130.
3. Add CliRunner tests for both.
