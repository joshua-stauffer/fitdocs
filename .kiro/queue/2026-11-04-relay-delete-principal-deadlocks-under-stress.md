---
id: 2026-11-04-relay-delete-principal-deadlocks-under-stress
title: Deleting a principal can deadlock against concurrent token writes on PostgreSQL
status: open
importance: low
importance_why: Needs a principal deleted while its own tokens are being written, which is rare at this volume; it surfaces as a storage error the operator can retry, and loses nothing.
effort: S
kind: bug
area: relay-server, relay/src/fitdocs_relay/storage/postgres.py
created: 2026-11-04
surfaced_by: review of the strava-publish Amendment 1 branch
pinned_at: 61c2ece1
resume_command: "do: reproduce deadlocks between delete_principal and token writes under concurrent load on PostgreSQL, then decide whether to retry or order the locks (read .kiro/queue/2026-11-04-relay-delete-principal-deadlocks-under-stress.md first)"
context:
  - relay/src/fitdocs_relay/storage/postgres.py
  - .kiro/specs/relay-server/requirements.md
blocked_by: []
---

## What
Under stress on PostgreSQL, `delete_principal` deadlocked against concurrent token
writes. The transaction that loses surfaces as a storage error.

## Why it matters
An operator's `principal delete` can fail and need running again. Nothing is lost,
because the deadlock aborts one whole transaction. It predates Amendment 1.

## Evidence
Reported by a reviewer subagent, and not re-run by the session that wrote this item:
- An 8-thread stress of `put_connection`, `claim_refresh`, `swap_tokens`,
  `release_refresh`, `issue_connection_token` and `delete_connection` showed no
  deadlock in about 400,000 operations on PostgreSQL 16.14.
- Adding `delete_principal` gave 40 deadlocks in 36,346 operations at the base and
  42 in 26,301 with the amendment. All 82 were `DELETE FROM principals` against
  `UPDATE tokens` or `INSERT INTO tokens`.

## How to pick it up
1. Read `delete_principal` and the token writes in `storage/postgres.py`.
2. Reproduce with a small script on a local PostgreSQL.
3. Decide between taking the principal's row lock first in token writes, and leaving
   it as it is with a note that the operator retries. Done means that decision is
   recorded and, if a change is made, a conformance test shows no deadlock.
