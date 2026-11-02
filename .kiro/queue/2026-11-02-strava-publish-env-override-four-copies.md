---
id: 2026-11-02-strava-publish-env-override-four-copies
title: "`_env_override` exists as four private copies in the connector modules"
status: open
importance: low
importance_why: "Shared logic with no owner; a fix to one copy silently misses the others."
effort: S
kind: chore
area: "src/fitdocs/connectors/connect.py, relay_connect.py, browser_connect.py, disconnect.py"
created: 2026-11-02
surfaced_by: "/kiro-impl strava-publish 5.6 review and validate-impl"
pinned_at: 964cc419
resume_command: "do: move `_env_override` to one public helper in connectors/credentials.py and delete the copies (read .kiro/queue/2026-11-02-strava-publish-env-override-four-copies.md first)"
context:
  - src/fitdocs/connectors/credentials.py
  - src/fitdocs/connectors/connect.py
  - src/fitdocs/connectors/relay_connect.py
  - src/fitdocs/connectors/browser_connect.py
  - src/fitdocs/connectors/disconnect.py
  - tests/connectors/test_boundary.py
blocked_by: []
---

## What
The function that names which environment variables override a stored credential is copied verbatim into four modules.

## Why it matters
Divergence risk: a new auth style or variable rule has to be changed in four places.

## Evidence
`grep -n "def _env_override" -r src` -> connect.py:115, disconnect.py:132, browser_connect.py:169, relay_connect.py:194.

## How to pick it up
1. Diff the four bodies to confirm they are identical.
2. Add one public helper next to the credential readers in credentials.py; check tests/connectors/test_boundary.py allowed imports.
3. Replace the four call sites; done when `grep -rn 'def _env_override' src` finds nothing.
