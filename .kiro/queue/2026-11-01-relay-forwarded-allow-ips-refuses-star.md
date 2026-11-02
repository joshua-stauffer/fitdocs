---
id: 2026-11-01-relay-forwarded-allow-ips-refuses-star
title: 'FITDOCS_RELAY_FORWARDED_ALLOW_IPS refuses `*`, unlike uvicorn''s convention'
status: open
importance: low
importance_why: Operators coming from uvicorn expect `*`; a hard refusal is safe but surprising, and the decision shapes the documented contract.
effort: S
kind: spec-work
area: relay/src/fitdocs_relay/config.py, docs/relay.md
created: 2026-11-01
surfaced_by: /kiro-impl relay-server 2.1 review; /kiro-validate-impl relay-server
pinned_at: 774a883c
resume_command: "/kiro-spec-requirements relay-server [queue: .kiro/queue/2026-11-01-relay-forwarded-allow-ips-refuses-star.md] Record the decision on accepting `*` for FITDOCS_RELAY_FORWARDED_ALLOW_IPS (needs Josh's choice)"
context:
  - relay/src/fitdocs_relay/config.py
  - docs/relay.md
  - .kiro/specs/relay-server/design.md
  - .kiro/specs/relay-server/requirements.md
blocked_by: []
---

## What
The setting accepts comma-separated IP addresses or networks and refuses anything else, including `*`, because the design meaning is "the proxy's addresses". uvicorn's own `--forwarded-allow-ips '*'` trusts every peer. The 2.1 ruling kept the refusal and docs/relay.md documents it; the maintainer has not yet decided.

## Why it matters
Trusting `*` lets any client spoof X-Forwarded-For and dodge the per-client rate limit, so the refusal is protective. The cost is operator surprise, and the decision should be recorded in the spec rather than only in docs.

## Evidence
- `relay/src/fitdocs_relay/config.py:172-185`: `_forwarded_allow_ips` rejects non-IP entries (`must be comma-separated IP addresses or networks`).
- `docs/relay.md:334-338` documents the setting.

## How to pick it up
1. Josh decides (below).
2. Record the decision in requirements.md (the env var's Req) and design.md.
3. If allowing `*`, add a warning log line at start-up and a test; if keeping the refusal, add the reason to the config error text.

## Open questions
Keep the refusal (recommended: spoofable header otherwise) or accept `*` with a start-up warning? Either way the choice should be written into the requirements.
