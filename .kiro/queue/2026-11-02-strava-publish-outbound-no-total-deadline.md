---
id: 2026-11-02-strava-publish-outbound-no-total-deadline
title: "Relay Outbound's per-call timeout is per socket operation, so a slow provider holds a worker far past it"
status: open
importance: medium
importance_why: "A trickling response keeps a worker (and a refresh lease) for far longer than any documented deadline; the same shape exists in the fitdocs HTTP client."
effort: M
kind: gap
area: "strava-publish, relay-server, relay/src/fitdocs_relay/outbound.py, src/fitdocs/connectors/http.py"
created: 2026-11-02
surfaced_by: "/kiro-impl strava-publish 2.3 / 3.5 review"
pinned_at: 964cc419
resume_command: "/kiro-spec-design strava-publish [queue: .kiro/queue/2026-11-02-strava-publish-outbound-no-total-deadline.md] Decide whether Outbound (and the connector HTTP client) needs a total wall-clock deadline"
context:
  - .kiro/specs/strava-publish/design.md
  - relay/src/fitdocs_relay/outbound.py
  - src/fitdocs/connectors/http.py
  - relay/src/fitdocs_relay/strava/custody.py
blocked_by: []
---

## What
`urllib_outbound` passes its `timeout` straight to `urllib` as a socket timeout, which bounds each connect or read, not the whole call. A provider that sends bytes just under the timeout can hold a relay worker for as long as it takes to deliver the (up to 8 MiB) body. A refresh holder can then outlive its lease (`LEASE_S`), lose its swap after Strava has already invalidated the old refresh token, and the next refresh gets a 400 that deletes the connection.

## Why it matters
A slow or hostile upstream ties up relay workers (a denial-of-service shape against the relay's small pool) and, through the refresh path, can cost an athlete their connection.

## Evidence
- `relay/src/fitdocs_relay/outbound.py:140-152`: `urllib_outbound(request, timeout)` -> `_opener().open(built, timeout=timeout)`; no total deadline anywhere in that function.
- `src/fitdocs/connectors/http.py:149`: `urllib_transport(request, timeout)` has the same shape.
- Lease-outliving half reported by reviewer subagent (task 3.5), unverified by a run.

## How to pick it up
1. Decide: a total deadline in Outbound (reading in chunks against a monotonic clock) vs accepting the per-operation bound and documenting it in docs/relay.md.
2. If adding it, make the same decision for `connectors/http.py` or record why the fitdocs side is exempt.
3. Done when a test with a transport that trickles bytes shows the call ending at the total bound, or the docs and design state the accepted limit.

## Open questions
Does the fitdocs client need the same bound, or is a user at a terminal enough of a backstop?
