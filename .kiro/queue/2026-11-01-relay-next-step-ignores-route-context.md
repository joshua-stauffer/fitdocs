---
id: 2026-11-01-relay-next-step-ignores-route-context
title: 'relay_next_step gives paste-oriented advice for token codes during --register'
status: open
importance: low
importance_why: A user running `connect --register` is told to check a token they never pasted.
effort: S
kind: bug
area: src/fitdocs/connectors/relay_connect.py
created: 2026-11-01
surfaced_by: /kiro-impl relay-server 6.4 review
pinned_at: 774a883c
resume_command: "/kiro-impl relay-server [queue: .kiro/queue/2026-11-01-relay-next-step-ignores-route-context.md] Make relay_next_step flow-aware for token codes"
context:
  - src/fitdocs/connectors/relay_connect.py
  - tests/connectors
blocked_by: []
---

## What
`relay_next_step(code, *, name, retry_after_s)` has no parameter saying which flow produced the code. A `token-*` code arriving on a registration poll gets the text written for a pasted token.

## Why it matters
Wrong remediation advice at the moment a user is most likely to need it.

## Evidence
- `src/fitdocs/connectors/relay_connect.py:128` signature; `:145` "Check the token you pasted, or ask the relay's operator for a new one, ...".

## How to pick it up
1. Add a `registering: bool` (or flow enum) parameter and branch the token-* texts.
2. Update the callers in the register path and the pull path.
3. Add a test per flow.
