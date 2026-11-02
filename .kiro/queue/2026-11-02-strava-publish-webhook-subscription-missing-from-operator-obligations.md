---
id: 2026-11-02-strava-publish-webhook-subscription-missing-from-operator-obligations
title: "Deletion on revocation in Strava's settings needs the operator's webhook subscription, but Req 16.6 does not list it"
status: open
importance: medium
importance_why: "An operator who skips the subscription keeps tokens for athletes who revoked on Strava, contradicting the privacy policy's deletion promise."
effort: S
kind: inconsistency
area: "strava-publish Req 16.6, docs/relay.md, relay privacy policy"
created: 2026-11-02
surfaced_by: "/kiro-impl strava-publish 3.11 review"
pinned_at: 964cc419
resume_command: "/kiro-spec-requirements strava-publish [queue: .kiro/queue/2026-11-02-strava-publish-webhook-subscription-missing-from-operator-obligations.md] Add webhook subscription to the operator obligations in 16.6 and to docs/relay.md"
context:
  - .kiro/specs/strava-publish/requirements.md
  - docs/relay.md
  - relay/src/fitdocs_relay/strava/policy.py
  - relay/src/fitdocs_relay/strava/cli.py
blocked_by: []
---

## What
The relay deletes an athlete's connection when Strava's deauthorization event arrives at the webhook (Req 11.6/16.x), but that only happens if the operator created the subscription with `fitdocs-relay strava webhook create`. Req 16.6's list of operator obligations (consent and privacy pages, support contact, breach notice, athlete capacity, no charging) omits it, so the docs task may not state it.

## Why it matters
A relay run without a subscription silently never deletes on revocation, while its policy says it does.

## Evidence
- `.kiro/specs/strava-publish/requirements.md:336` (16.6 list, no subscription) vs `:282` (webhook deauthorization deletes the connection).
- Reviewer subagent claim (3.11) that docs must say so; docs/relay.md not re-checked.

## How to pick it up
1. `grep -n -i webhook docs/relay.md` to see whether the subscription is described as required or optional.
2. Amend 16.6 and the docs/policy so the dependency is stated; done when an operator reading docs/relay.md learns that deletion on revocation needs the subscription.
