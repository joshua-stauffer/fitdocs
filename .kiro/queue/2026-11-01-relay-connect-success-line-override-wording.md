---
id: 2026-11-01-relay-connect-success-line-override-wording
title: 'The relay connect success line misdescribes what an environment override does'
status: open
importance: low
importance_why: The message tells the user a pull will use a token that a pull never uses for relay instances.
effort: S
kind: bug
area: src/fitdocs/cli.py
created: 2026-11-01
surfaced_by: /kiro-impl relay-server 8.4 review
pinned_at: 774a883c
resume_command: "/kiro-impl relay-server [queue: .kiro/queue/2026-11-01-relay-connect-success-line-override-wording.md] Correct the relay connect success wording"
context:
  - src/fitdocs/cli.py
  - docs/relay.md
blocked_by: []
---

## What
When a relay connect runs with an environment override, the success text says the override is "used instead of the stored values during a pull". A pull never uses a relay token from the stored values or the environment in that way, so the relay case is misdescribed.

## Why it matters
Users are told something false about where their token is read from.

## Evidence
- `src/fitdocs/cli.py:1414-1419`: the `env_override` branch ending "(used instead of the".

## How to pick it up
1. Read how the relay pull resolves its token (`src/fitdocs/connectors/relay*.py`).
2. Write a relay-specific line, or suppress this one for relay.
3. Pin the new text in `tests/connectors/test_cli_relay_connect.py` (or the nearest connect test).
