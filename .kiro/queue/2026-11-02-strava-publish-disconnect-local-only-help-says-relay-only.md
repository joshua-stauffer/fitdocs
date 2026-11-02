---
id: 2026-11-02-strava-publish-disconnect-local-only-help-says-relay-only
title: "`fitdocs disconnect --local-only` help says relay instances only, but it also works for a browser-consent (Strava) instance"
status: open
importance: medium
importance_why: "Help text is what an athlete reads before choosing a flag that skips revocation at Strava; it understates where the flag applies."
effort: S
kind: docs
area: "src/fitdocs/cli.py, src/fitdocs/connectors/disconnect.py"
created: 2026-11-02
surfaced_by: "/kiro-impl strava-publish 7.5 review"
pinned_at: 964cc419
resume_command: "do: reword the --local-only option help and the disconnect docstring to cover browser-consent instances, and pin it in the CLI test (read .kiro/queue/2026-11-02-strava-publish-disconnect-local-only-help-says-relay-only.md first)"
context:
  - src/fitdocs/cli.py
  - src/fitdocs/connectors/disconnect.py
  - docs/configuration.md
blocked_by: []
---

## What
The option help reads "Relay instances only: forget the stored token without asking the relay to revoke it (the token stays valid until its operator revokes it)", but `run_disconnect` honours `local_only` for every revoking style, including oauth-browser, whose token stays valid at Strava, not only at the operator.

## Why it matters
Wrong guidance about whether a token stays valid after a local-only disconnect.

## Evidence
- `src/fitdocs/cli.py:578-584` (help text).
- `src/fitdocs/connectors/disconnect.py:241`: `if style in _REVOKING_STYLES and not local_only:`; `:259-261` the local-only removal path with `_LOCAL_ONLY_NOTES.get(style, SERVICE_NOTE)`.

## How to pick it up
Update the help, check `_LOCAL_ONLY_NOTES` wording for the browser style, and update the tests that assert the help string.
