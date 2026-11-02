---
id: 2026-11-02-strava-publish-policy-deletion-omits-reconnect-and-account-move
title: "Policy Deletion section omits the re-connect and account-moved deletions"
status: open
importance: low
importance_why: "Req 16.1 asks the policy to say what the relay deletes and when; two deletion triggers are missing."
effort: S
kind: gap
area: "relay/src/fitdocs_relay/strava/policy.py, strava-publish Req 16.1, 3.10, 3.11"
created: 2026-11-02
surfaced_by: "/kiro-impl strava-publish 3.11 and 7.2 reviews"
pinned_at: 964cc419
resume_command: "do: add the re-connect (3.10/3.11) and account-moved-to-another-principal cases to the Deletion paragraph of policy.py and its pinning test (read .kiro/queue/2026-11-02-strava-publish-policy-deletion-omits-reconnect-and-account-move.md first)"
context:
  - relay/src/fitdocs_relay/strava/policy.py
  - .kiro/specs/strava-publish/requirements.md
  - relay/src/fitdocs_relay/storage/sqlite.py
blocked_by: []
---

## What
The Deletion text lists four cases but not that reconnecting deletes the earlier connection's link records (Req 3.10/3.11), nor that when an account moves to another principal the first principal's connection is removed (storage `put_connection` rival removal).

## Why it matters
The policy understates when data is deleted; low risk because deletion happens anyway.

## Evidence
`relay/src/fitdocs_relay/strava/policy.py:91` `"Deletion": (` ... lists the cases; the two missing cases are the reviewers' finding (3.11, 7.2), unverified beyond reading that heading.

## How to pick it up
Read the `_SHARED["Deletion"]` entry, add the two clauses in plain words, and update the test that pins the policy sentences.
