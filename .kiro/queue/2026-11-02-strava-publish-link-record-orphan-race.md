---
id: 2026-11-02-strava-publish-link-record-orphan-race
title: "A publish finishing after disconnect or account change can leave a link record the relay promises to delete"
status: open
importance: low
importance_why: "Maintainer 2026-11-04: not worth fixing now. A disconnect must commit in the gap between two adjacent database calls, at low volume; the leftover row holds only fitdocs facts and no longer resolves anything once /go/ is gone."
effort: M
kind: bug
area: "relay storage, relay/src/fitdocs_relay/strava/publish.py, relay/src/fitdocs_relay/storage/sqlite.py, postgres.py"
created: 2026-11-02
surfaced_by: "/kiro-impl strava-publish 2.7, 3.6 reviews and validate-impl"
pinned_at: 964cc419
resume_command: "/kiro-spec-design strava-publish [queue: .kiro/queue/2026-11-02-strava-publish-link-record-orphan-race.md] Specify a storage-level conditional put_publication that requires a live connection for the same account"
context:
  - .kiro/specs/strava-publish/design.md
  - .kiro/specs/strava-publish/requirements.md
  - relay/src/fitdocs_relay/strava/publish.py
  - relay/src/fitdocs_relay/storage/sqlite.py
  - relay/src/fitdocs_relay/storage/postgres.py
  - relay/tests/conformance/test_publications.py
blocked_by: []
---

## What
`put_publication` needs no live connection. Sequence `put_connection(ann, X)` -> `delete_connection(ann)` -> `put_publication` (returns True) -> `put_connection(ann, Z)` leaves the record, because the account-change delete only runs when a previous row exists. The landed mitigation (ruling 3.6) checks the connection exists just before the put, which narrows but does not close the window; the publish.py docstring admits the gap. `/go/<id>` would then resolve the leftover record against the new account. Fix proposed by the reviewer: a design amendment making the put conditional on a live connection for the same account, checked under the connection's lock in the put's transaction.

## Why it matters
Req 11.5 and 3.11 and the privacy policy's "deleted at once" are not strictly true under the race; cost grows with relay traffic.

## Evidence
- `relay/src/fitdocs_relay/storage/sqlite.py` and `postgres.py` `put_publication`/`put_connection` (reviewer cited ~380 and ~486; re-read before editing).
- Design amendment note records ruling 3.6 (connection-exists check just before the put) at `.kiro/specs/strava-publish/design.md:1987+`.
- The race sequence is reported by reviewer subagent, unverified by a run; no conformance test covers two principals racing one new id either (reviewer's 20x30 race was owner-safe on both backends).

## How to pick it up
1. Write the sequence as a failing test in relay/tests/conformance/ on both backends.
2. Amend the design with the conditional-put signature, then implement in sqlite.py and postgres.py in the put's transaction.
3. Also add the missing conformance test for two principals racing `put_publication` on one new id.
