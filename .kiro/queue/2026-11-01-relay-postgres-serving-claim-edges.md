---
id: 2026-11-01-relay-postgres-serving-claim-edges
title: 'PostgreSQL serving claim: misleading refusal on a NULL schema, and silent loss if its connection drops'
status: open
importance: medium
importance_why: A lost claim lets a second relay serve against the same schema; the operator is told only to restart after a DB restart.
effort: M
kind: bug
area: relay/src/fitdocs_relay/storage/postgres.py, relay/src/fitdocs_relay/serve.py
created: 2026-11-01
surfaced_by: /kiro-impl relay-server 2.5 review
pinned_at: 774a883c
resume_command: "/kiro-impl relay-server [queue: .kiro/queue/2026-11-01-relay-postgres-serving-claim-edges.md] Fix the NULL-schema refusal message and decide the dropped-claim behaviour"
context:
  - relay/src/fitdocs_relay/storage/postgres.py
  - relay/src/fitdocs_relay/serve.py
  - .kiro/specs/relay-server/design.md
  - docs/relay.md
blocked_by: []
---

## What
Two edges in the advisory-lock claim.
(1) With a search_path that names no existing schema, `current_schema()` is NULL, `pg_try_advisory_lock(hashtext('fitdocs-relay:' || NULL))` is NULL and `claim_serving` returns None, which the serve path logs as "held by another". The cause is a bad search_path.
(2) A held claim lives on a dedicated connection; if that connection drops (database restart, idle timeout) the lock is gone and nothing re-checks it (Req 9.6, design Serve lifecycle).

## Why it matters
(1) misleads the operator toward the wrong cause. (2) removes the single-server guarantee without any log line; docs/relay.md currently tells operators to restart the relay after restarting its database as a workaround.

## Evidence
- `SET search_path TO no_such_schema; SELECT current_schema() IS NULL, pg_try_advisory_lock(hashtext('fitdocs-relay:' || current_schema())) IS NULL` returns `t|t` (observed during 2.5).
- `relay/src/fitdocs_relay/storage/postgres.py:400-413`: `claim_serving`.
- `.kiro/specs/relay-server/design.md:594`: Serve lifecycle section has no re-check step.

## How to pick it up
1. For (1), have `claim_serving` raise a typed configuration error when `current_schema()` is NULL.
2. For (2), decide on a cheap periodic liveness check of the claim connection (or a clean exit when it fails) and amend the design's Serve lifecycle and Req 9.6 first.
3. Done when a conformance test kills the claim connection and observes the specified outcome.
