---
id: 2026-11-02-strava-publish-custody-withdraw-skips-revoke-without-refresh-token
title: "Custody.withdraw makes no revoke call for a row with a readable access token but no refresh token"
status: open
importance: low
importance_why: "Strava accepts either token for revoke; skipping leaves an authorization live at Strava after the athlete disconnected."
effort: S
kind: bug
area: "relay/src/fitdocs_relay/strava/custody.py"
created: 2026-11-02
surfaced_by: "/kiro-impl strava-publish 3.5 review"
pinned_at: 964cc419
resume_command: "do: revoke with the access token when no refresh token is stored, and add a custody test (read .kiro/queue/2026-11-02-strava-publish-custody-withdraw-skips-revoke-without-refresh-token.md first)"
context:
  - relay/src/fitdocs_relay/strava/custody.py
  - .kiro/specs/strava-publish/research.md
blocked_by: []
---

## What
`_revoke_once` returns early when `tokens[1]` (the refresh token) is None, although Strava's deauthorize accepts the access token too (research.md records the form-body revoke).

## Why it matters
Disconnect leaves the app authorized at Strava for such rows (rare: how a row lacks a refresh token is unclear).

## Evidence
`relay/src/fitdocs_relay/strava/custody.py:260-265`: `if tokens is None or tokens[1] is None: return`.

## How to pick it up
Decide whether a row without a refresh token can exist at all (storage constraint); if yes, fall back to the access token; add a test in relay/tests/strava/test_custody.py.
