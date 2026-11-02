---
id: 2026-11-02-strava-publish-reencrypt-all-covers-strava-rows-only
title: "The reencrypt operator command re-seals Strava rows only, though Req 4.2 says every stored token"
status: open
importance: low
importance_why: "Latent: only one target exists today; a second target would silently be skipped during key rotation."
effort: S
kind: gap
area: "relay/src/fitdocs_relay/strava/custody.py, strava-publish Req 4.2"
created: 2026-11-02
surfaced_by: "/kiro-impl strava-publish 3.5 review"
pinned_at: 964cc419
resume_command: "do: when a second target gains stored tokens, make the reencrypt command iterate every target; until then narrow Req 4.2's wording or add a test that fails when another target exists (read .kiro/queue/2026-11-02-strava-publish-reencrypt-all-covers-strava-rows-only.md first)"
context:
  - .kiro/specs/strava-publish/requirements.md
  - relay/src/fitdocs_relay/strava/custody.py
blocked_by: []
---

## What
`reencrypt_all` iterates `list_connections(STRAVA)` only.

## Why it matters
A future target's tokens would stay under a retired key unnoticed.

## Evidence
`relay/src/fitdocs_relay/strava/custody.py:286`: `for listed in self._storage.list_connections(STRAVA):`.

## How to pick it up
Either narrow the requirement wording to the Strava target or add a guard test that enumerates OFFERED_TARGETS and fails if one is not covered.
