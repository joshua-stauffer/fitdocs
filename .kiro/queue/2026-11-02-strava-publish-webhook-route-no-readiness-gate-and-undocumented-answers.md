---
id: 2026-11-02-strava-publish-webhook-route-no-readiness-gate-and-undocumented-answers
title: "The Strava webhook route has no readiness gate and several answers are unrecorded in the design"
status: open
importance: low
importance_why: "A right-secret POST during a bad-schema window calls Custody.forget_account against an unready store."
effort: S
kind: gap
area: "relay/src/fitdocs_relay/strava/routes.py, strava-publish design"
created: 2026-11-02
surfaced_by: "/kiro-impl strava-publish 4.3 review"
pinned_at: 964cc419
resume_command: "/kiro-spec-design strava-publish [queue: .kiro/queue/2026-11-02-strava-publish-webhook-route-no-readiness-gate-and-undocumented-answers.md] Decide the webhook route's behaviour while services are not ready and record the status answers"
context:
  - .kiro/specs/strava-publish/design.md
  - relay/src/fitdocs_relay/strava/routes.py
blocked_by: []
---

## What
A POST with the right secret while `services.ready` is False answers 200 and calls `Custody.forget_account`. A wrong secret while the store is unreachable yields a 503 envelope, not the 404 the secret rule implies. HEAD on browser routes is 405 while other unsupported methods answer not-offered. Design is silent on all three. (The 413 for oversized bodies is already recorded in the Amendment note.)

## Why it matters
Possible write against a store on the wrong schema; minor inconsistency in status codes.

## Evidence
`relay/src/fitdocs_relay/strava/routes.py:304-316`: `webhook_endpoint` compares the secret, then on POST calls `strava.webhook.event(...)` and returns 200 with no `services.ready` check. Other two answers reported by reviewer subagent, unverified.

## How to pick it up
Add a readiness check (answer 503 envelope while not ready), then record the three answers in the design.
