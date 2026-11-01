---
id: 2026-11-01-relay-registration-poll-interval-vs-rate-limit
title: 'A registration provider answering interval_s 1-3 cannot finish; poll interval and per-client rate limit disagree'
status: open
importance: medium
importance_why: A legitimate provider choice (interval 1) fails every registration after about 20 polls, and the default 5 s advice only lives in docs.
effort: M
kind: inconsistency
area: relay/src/fitdocs_relay/shared/relay_envelope.py, relay/src/fitdocs_relay/contract.py, src/fitdocs/connectors/relay_connect.py
created: 2026-11-01
surfaced_by: /kiro-validate-impl relay-server (E-1)
pinned_at: 774a883c
resume_command: "/kiro-spec-requirements relay-server [queue: .kiro/queue/2026-11-01-relay-registration-poll-interval-vs-rate-limit.md] Resolve registration poll interval versus the per-client rate limit (needs Josh's choice)"
context:
  - .kiro/specs/relay-server/requirements.md
  - .kiro/specs/relay-server/design.md
  - relay/src/fitdocs_relay/shared/relay_envelope.py
  - relay/src/fitdocs_relay/contract.py
  - relay/src/fitdocs_relay/routes.py
  - src/fitdocs/connectors/relay_connect.py
  - docs/relay.md
blocked_by: []
---

## What
Registration polls are unauthenticated, so each counts against the per-client limit (default 20 per minute). The envelope allows `interval_s` as low as 1, and the client ends a registration on `rate-limited` (Req 13.7). With interval 1 the client makes 18 polls, receives pending each time, then a 429 and exits 1.
The maintainer must choose the resolution; `docs/relay.md` now advises providers to answer 5 seconds or more (774a883c) as a stopgap.

## Why it matters
Any provider using a short interval produces a registration that fails after about 20 seconds. The advice sits in docs only, not in code or the wire contract.

## Evidence
- Reproduced in validation: interval 1 -> 18 pending then 429, exit 1 after 19.5 s (log kept by the validating session; not in the repo).
- `relay/src/fitdocs_relay/contract.py:103-106`: client limit default 20.
- `relay/src/fitdocs_relay/routes.py:252`: `_client_limit(request)` applies to the poll route.
- `relay/src/fitdocs_relay/shared/relay_envelope.py:39`: `MIN_POLL_INTERVAL_S = 1`.
- `src/fitdocs/connectors/relay_connect.py:333-336`: a refused poll (rate-limited) ends the registration.
- `docs/relay.md:502`: "answer 5 seconds or more unless the limit is raised".

## How to pick it up
1. Josh picks an option (below).
2. Implement it in code, the envelope contract file and both copies of relay_envelope.py as needed.
3. Add a test that drives a full registration at the smallest accepted interval and finishes.

## Open questions
Which resolution?
- A. Raise `MIN_POLL_INTERVAL_S` to 5 (a wire change inside envelope v1; both shared copies and the replay file change).
- B. Amend Req 13.7 so a rate-limited poll that carries a wait sleeps and continues inside the deadline.
- C. Exempt registration polls from the per-client limit (weakens the unauthenticated-route defence; needs a per-poll_secret limit instead).
