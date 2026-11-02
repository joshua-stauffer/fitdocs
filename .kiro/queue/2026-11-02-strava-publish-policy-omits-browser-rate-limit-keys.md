---
id: 2026-11-02-strava-publish-policy-omits-browser-rate-limit-keys
title: "The relay privacy policy never says it keeps per-client rate-limit counts keyed by a hashed network address and the claim cookie"
status: open
importance: medium
importance_why: "Req 16.1 says the policy states what the relay receives; the browser-facing routes receive and key on the client address."
effort: S
kind: gap
area: "strava-publish Req 16.1, relay/src/fitdocs_relay/strava/policy.py"
created: 2026-11-02
surfaced_by: "/kiro-impl strava-publish 3.11 review"
pinned_at: 964cc419
resume_command: "/kiro-spec-design strava-publish [queue: .kiro/queue/2026-11-02-strava-publish-policy-omits-browser-rate-limit-keys.md] Amend the Pages and Policy section so the policy names the rate-limit keys, then update policy.py"
context:
  - .kiro/specs/strava-publish/requirements.md
  - .kiro/specs/strava-publish/design.md
  - relay/src/fitdocs_relay/strava/policy.py
  - relay/src/fitdocs_relay/ratelimit.py
blocked_by: []
---

## What
The nine design-fixed policy headings do not say that the connect page, callback and /go/ routes count requests per client, keyed by an HMAC of the client network address, nor that the claim cookie exists.

## Why it matters
The policy is incomplete against its own requirement; operators publish it as the legal statement.

## Evidence
- `relay/src/fitdocs_relay/ratelimit.py:34-40`: `check_client` / `_client_key` return `"c:" + hmac(pepper, address)` digest.
- `relay/src/fitdocs_relay/strava/policy.py:22,91`: heading list including "Deletion"; grep for `address`/`rate` in that file finds none of this.
- Design § StravaRoutes "Browser routes are rate-limited per client".

## How to pick it up
1. Read the design's Pages and Policy section; pick which heading carries a sentence (the headings are fixed, so fold into an existing one or amend the heading list).
2. Update policy.py and the test that pins the policy text.
