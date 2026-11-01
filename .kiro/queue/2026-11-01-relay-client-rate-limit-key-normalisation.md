---
id: 2026-11-01-relay-client-rate-limit-key-normalisation
title: 'Client-address rate-limit keys are not normalised, so one IPv6 host can rotate spellings'
status: open
importance: low
importance_why: A holder of an IPv6 block gets many separate limits; unauthenticated registration polling is the abuse surface.
effort: S
kind: bug
area: relay/src/fitdocs_relay/ratelimit.py
created: 2026-11-01
surfaced_by: /kiro-impl relay-server 3.2 review
pinned_at: 774a883c
resume_command: "/kiro-impl relay-server [queue: .kiro/queue/2026-11-01-relay-client-rate-limit-key-normalisation.md] Canonicalise client addresses before keying the rate limit"
context:
  - relay/src/fitdocs_relay/ratelimit.py
  - .kiro/specs/relay-server/design.md
  - relay/tests/test_ratelimit.py
blocked_by: []
---

## What
`_client_key` hashes the address string as given. Different spellings of one IPv6 address, and IPv4-mapped forms, produce different keys. Whether to also bucket by prefix (for example a /64) is a design question the design is silent on.

## Why it matters
Per-address limiting is the relay's only defence for unauthenticated routes; spelling variants and address rotation within a prefix bypass it.

## Evidence
- `relay/src/fitdocs_relay/ratelimit.py:37-41`: `hmac.new(pepper, b"client\0" + address.encode(), ...)`.
- `_client_key("::1") != _client_key("0:0:0:0:0:0:0:1")` (observed in 3.2 review).
- `design.md:1340-1346` documents the key as the HMAC of the raw address.

## How to pick it up
1. Canonicalise with `ipaddress.ip_address(...)`, unmapping IPv4-mapped IPv6, before hashing; fall back to the raw string if it does not parse.
2. State the key rule in design.md; decide separately whether to collapse IPv6 to a /64.
3. Done when equal addresses in different spellings share one counter.
