---
id: 2026-11-02-strava-publish-step-outcomes-refresh-column-duplicated-in-custody
title: "Custody carries its own copy of the refresh failure mapping instead of reading STEP_OUTCOMES"
status: open
importance: low
importance_why: "Two tables for one mapping; only a test pins them equal."
effort: S
kind: chore
area: "relay/src/fitdocs_relay/strava/custody.py, relay/src/fitdocs_relay/strava/publish.py"
created: 2026-11-02
surfaced_by: "/kiro-impl strava-publish 3.6 review"
pinned_at: 964cc419
resume_command: "do: have Custody._refresh_failed read STEP_OUTCOMES for the refresh column (read .kiro/queue/2026-11-02-strava-publish-step-outcomes-refresh-column-duplicated-in-custody.md first)"
context:
  - relay/src/fitdocs_relay/strava/custody.py
  - relay/src/fitdocs_relay/strava/publish.py
blocked_by: []
---

## What
`STEP_OUTCOMES` (publish.py:140) has a refresh column that is never consulted at runtime; `_refresh_failed` (custody.py:212-229) hard-codes the same outcomes.

## Why it matters
Drift risk if one is changed without the other.

## Evidence
`relay/src/fitdocs_relay/strava/publish.py:140`; `relay/src/fitdocs_relay/strava/custody.py:212-229`.

## How to pick it up
Check import direction (custody must not import publish if publish imports custody); move the table to a shared module if needed.
