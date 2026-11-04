---
id: 2026-11-04-disconnect-silent-when-relay-skips-the-strava-revoke
title: fitdocs disconnect does not say when the relay's budget skipped the revoke at Strava
status: open
importance: low
importance_why: Needs a disconnect while the application's call budget is spent, which is rare at this volume; the relay's own copy is deleted either way, and only the grant at Strava remains.
effort: S
kind: gap
area: strava-publish, relay/src/fitdocs_relay/strava/custody.py, src/fitdocs/connectors/disconnect.py
created: 2026-11-04
surfaced_by: review of the strava-publish Amendment 1 branch
pinned_at: 40f989fb
resume_command: "/kiro-spec-requirements strava-publish [queue: .kiro/queue/2026-11-04-disconnect-silent-when-relay-skips-the-strava-revoke.md] Decide whether fitdocs disconnect should say that the grant remains at Strava when the revoke was skipped"
context:
  - relay/src/fitdocs_relay/strava/custody.py
  - src/fitdocs/connectors/disconnect.py
  - .kiro/specs/strava-publish/requirements.md
blocked_by: []
---

## What
When a disconnect reaches the relay and its call budget refuses, the relay skips the
revoke at Strava and still deletes its own copy. It answers a bare `ok`, so `fitdocs
disconnect` prints that the relay deleted the connection. That is true, but the
athlete is not told that the grant remains at Strava until they revoke it there.

## Why it matters
The athlete may believe the relay's access has ended at Strava too. With its tokens
deleted, the relay can no longer use that grant, so this is about what the athlete's
Strava settings show. The built-in policy says "when the relay's call budget allows",
so nothing false is promised.

## Evidence
- `relay/src/fitdocs_relay/strava/custody.py`, `_revoke_once`: calls `self._api.revoke`
  only when `self._budget.spend(...)` is allowed. `withdraw` deletes the connection in
  a `finally`.
- `src/fitdocs/connectors/disconnect.py`: `CONSENT_DELETED_NOTE` is the only note on
  an `ok`.

## How to pick it up
1. Read `withdraw` and the relay's disconnect route.
2. Take the maintainer's answer to the open question below.
3. Done means that either the answer tells fitdocs that the revoke was skipped and the
   command says so, or this item is closed as accepted.

## Open questions
Is this worth a new answer field, at a volume where the budget is very unlikely to be
spent? Revoking without counting against the budget would be another way to close it.
