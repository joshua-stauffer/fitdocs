---
id: 2026-11-06-env-override-always-wins-except-disconnect
title: docs/connectors.md says an environment variable always wins over stored credentials, but disconnect uses only the stored token
status: open
importance: low
importance_why: One word overstates a rule in one command; disconnect's behaviour is deliberate, but after removing a stored file its output names no remaining override.
effort: S
kind: docs
area: connectors, docs/connectors.md, src/fitdocs/connectors/disconnect.py
created: 2026-11-06
surfaced_by: website copy for the new connectors (draft PR 5)
pinned_at: f4bc152a
resume_command: "do: reword docs/connectors.md line 443 so the environment-override rule states the disconnect exception [queue: .kiro/queue/2026-11-06-env-override-always-wins-except-disconnect.md]"
context:
  - docs/connectors.md
  - src/fitdocs/connectors/disconnect.py
blocked_by: []
---

## What
`docs/connectors.md:443` says "A variable that is set and non-empty always wins over whatever is stored." `src/fitdocs/connectors/disconnect.py` revokes with "the stored token and never the environment override" (module docstring, line 8).

## Why it matters
A reader with an override set could expect `fitdocs disconnect` to revoke that value. It revokes the stored one and leaves the variable's token valid.

## Evidence
The two lines above, read at f4bc152a; a reviewer ran revoke and `--local-only` with a stored file and the variable set, and neither output names the variable. `_env_override` (`disconnect.py:136`) is printed only when nothing was stored (`cli.py:1921`), so a removal does not mention a variable still set.

## How to pick it up
Add the exception to the sentence, for example "for every command but `fitdocs disconnect`, which revokes only what is stored". Check it against `_revoke_then_remove` first. Done when the sentence is true for every command.
