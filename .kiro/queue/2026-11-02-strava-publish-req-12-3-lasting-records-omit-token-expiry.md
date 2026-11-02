---
id: 2026-11-02-strava-publish-req-12-3-lasting-records-omit-token-expiry
title: "Requirement 12.3 lists the only lasting Strava records but the relay also stores the plaintext access-token expiry"
status: open
importance: medium
importance_why: "A requirement and the schema disagree about what the relay keeps about Strava; privacy statements are built from that requirement."
effort: S
kind: inconsistency
area: "strava-publish, relay storage"
created: 2026-11-02
surfaced_by: "/kiro-impl strava-publish 3.11 review"
pinned_at: 964cc419
resume_command: "/kiro-spec-requirements strava-publish [queue: .kiro/queue/2026-11-02-strava-publish-req-12-3-lasting-records-omit-token-expiry.md] Amend 12.3 to count the access-token expiry as part of the tokens, or seal it"
context:
  - .kiro/specs/strava-publish/requirements.md
  - .kiro/specs/strava-publish/design.md
  - relay/src/fitdocs_relay/storage/sqlite.py
  - relay/src/fitdocs_relay/storage/postgres.py
blocked_by: []
---

## What
Requirement 12.3 says the relay's only lasting Strava records are the encrypted tokens, the keyed account hash and fitdocs's own publication ids and match facts. The connection row also stores `access_expires_at` in plaintext (design and migration 0002_target_custody agree on this).

## Why it matters
The privacy policy and the requirement overstate what is sealed; a strict reader of 12.3 would call the schema non-conforming.

## Evidence
- `.kiro/specs/strava-publish/requirements.md:292`: "its only lasting records for the Strava target shall be the encrypted tokens, the keyed account hash and fitdocs's own publication ids and match facts".
- `relay/src/fitdocs_relay/storage/sqlite.py:85,95,407,414`: `access_expires_at` is a plain column.

## How to pick it up
1. Choose: amend 12.3 so the expiry counts as part of the tokens (it is an expiry time, not Strava Data about the athlete), or seal it.
2. If amended, update the policy text in relay/src/fitdocs_relay/strava/policy.py if it enumerates records.
