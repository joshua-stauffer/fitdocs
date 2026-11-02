---
id: 2026-11-02-strava-publish-reencrypt-all-leaves-busy-rows-unreported
title: "reencrypt_all can finish with a row still sealed under the retiring key and report it in neither count"
status: open
importance: medium
importance_why: "The operator is told `unreadable 0` and may drop the old key, turning that connection not-connected."
effort: S
kind: bug
area: "relay/src/fitdocs_relay/strava/custody.py, relay/src/fitdocs_relay/strava/cli.py, strava-publish design RelayOperatorCli"
created: 2026-11-02
surfaced_by: "/kiro-impl strava-publish 3.5 and 7.2 reviews"
pinned_at: 964cc419
resume_command: "/kiro-spec-design strava-publish [queue: .kiro/queue/2026-11-02-strava-publish-reencrypt-all-leaves-busy-rows-unreported.md] Add a third left-for-later count (or non-zero exit) to the reencrypt command"
context:
  - .kiro/specs/strava-publish/design.md
  - relay/src/fitdocs_relay/strava/custody.py
  - relay/src/fitdocs_relay/strava/cli.py
  - docs/relay.md
blocked_by: []
---

## What
A connection whose swap stays refused after `LEASE_S` (a refresh lease holds it) is left as it is and counted in neither number. The command prints `re-encrypted n, unreadable 0` and exits 0, while the rotation procedure says to remove the old key only when nothing is unreadable.

## Why it matters
An operator following the documented rotation can strand a connection.

## Evidence
- `relay/src/fitdocs_relay/strava/custody.py:272-306` (docstring: "counted in neither number: running the command again picks it up").
- `relay/src/fitdocs_relay/strava/cli.py:97`: `f"re-encrypted {done}, unreadable {unreadable}"`.
- Design RelayOperatorCli row at design.md:1713-1726 (reviewer's citation).

## How to pick it up
1. Change `reencrypt_all` to return a third count, print `left for later n`, and exit non-zero when it is above 0.
2. Update design, docs/relay.md rotation step and the CLI test.
