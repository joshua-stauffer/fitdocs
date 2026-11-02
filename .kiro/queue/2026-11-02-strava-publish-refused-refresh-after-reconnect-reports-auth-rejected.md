---
id: 2026-11-02-strava-publish-refused-refresh-after-reconnect-reports-auth-rejected
title: "A refresh refused after the athlete reconnected tells the caller to reconnect for no reason"
status: open
importance: low
importance_why: "A confusing message to the athlete in a narrow race; no data effect."
effort: S
kind: bug
area: "relay/src/fitdocs_relay/strava/custody.py"
created: 2026-11-02
surfaced_by: "/kiro-impl strava-publish 3.5 review"
pinned_at: 964cc419
resume_command: "/kiro-spec-design strava-publish [queue: .kiro/queue/2026-11-02-strava-publish-refused-refresh-after-reconnect-reports-auth-rejected.md] Decide whether Custody re-reads the connection before answering AUTH_REJECTED"
context:
  - relay/src/fitdocs_relay/strava/custody.py
  - .kiro/specs/strava-publish/design.md
blocked_by: []
---

## What
When a refresh is definitively refused, `_refresh_failed` deletes with the holder's generation and lease and returns `AUTH_REJECTED` even if a newer connection now exists (the delete is a no-op by ruling 3.5 A).

## Why it matters
The athlete is told to reconnect though they just did.

## Evidence
`relay/src/fitdocs_relay/strava/custody.py:216-224`: definitive failure -> `delete_connection(...)` -> `return PublishCode.AUTH_REJECTED` with no re-read.

## How to pick it up
Consider re-reading and, if a newer connection exists, retrying once or answering unavailable; add a custody test.
