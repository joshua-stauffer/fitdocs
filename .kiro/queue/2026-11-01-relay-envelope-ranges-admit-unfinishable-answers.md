---
id: 2026-11-01-relay-envelope-ranges-admit-unfinishable-answers
title: 'Envelope ranges admit a registration the client cannot finish, and retry_after_s has no upper bound'
status: open
importance: low
importance_why: Both are provider-side mistakes the wire format fails to reject; the client then sees a confusing outcome or a 31-digit header.
effort: S
kind: inconsistency
area: relay/src/fitdocs_relay/shared/relay_envelope.py, src/fitdocs/connectors/relay_envelope.py
created: 2026-11-01
surfaced_by: /kiro-impl relay-server 6.4, 4.5 review
pinned_at: 774a883c
resume_command: "/kiro-impl relay-server [queue: .kiro/queue/2026-11-01-relay-envelope-ranges-admit-unfinishable-answers.md] Bound retry_after_s and reject expires_in_s <= interval_s"
context:
  - relay/src/fitdocs_relay/shared/relay_envelope.py
  - src/fitdocs/connectors/relay_envelope.py
  - .kiro/specs/relay-server/design.md
  - relay/contract/envelope-v1.json
blocked_by: []
---

## What
(1) `MAX_POLL_INTERVAL_S` is 60 and `MIN_EXPIRES_IN_S` is 60, so a started registration with interval 60 and expires_in 60 is valid but the first sleep lands on the inclusive deadline: the client reports `registration-expired` after zero polls. (2) `retry_after_s` is parsed with no upper bound, so a provider answering `RateLimitedAnswer(10**30)` is served with a 31-digit `Retry-After`.
The relay's `shared/` copy and the fitdocs copy are the same file; both must change together.

## Why it matters
A provider typo makes registration unusable (1) or emits an absurd header (2); the validation that exists elsewhere is range-based and these are the gaps in it.

## Evidence
- `relay/src/fitdocs_relay/shared/relay_envelope.py:39-42` (and the same lines in `src/fitdocs/connectors/relay_envelope.py`): MIN/MAX poll interval 1/60, MIN_EXPIRES_IN_S 60.
- `:327-330`: `_int_in` ranges for interval_s and expires_in_s. `:342-348`: `_int_in(data["retry_after_s"], 0, None)`.

## How to pick it up
1. Choose: require `expires_in_s > interval_s` in both the relay provider check (4.5) and the client parse, or document the edge in the design. Choose a retry_after_s ceiling (for example one day).
2. Change both copies identically (a test pins them equal) and bump nothing on the wire only if the envelope version rule allows; check `contract.py`.
3. Add cases to the replay tests.
