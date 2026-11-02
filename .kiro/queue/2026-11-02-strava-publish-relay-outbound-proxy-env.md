---
id: 2026-11-02-strava-publish-relay-outbound-proxy-env
title: "Relay Outbound honours HTTPS_PROXY and the test network guard cannot see through a loopback proxy"
status: open
importance: low
importance_why: "Behaviour is safe (CONNECT keeps secrets inside TLS) but undocumented, and the test guard has a hole an unlucky environment could use."
effort: S
kind: docs
area: "relay-server, strava-publish, docs/relay.md, relay/tests/conftest.py"
created: 2026-11-02
surfaced_by: "/kiro-impl strava-publish 2.3 and 4.1 reviews"
pinned_at: 964cc419
resume_command: "do: document the proxy behaviour in docs/relay.md and clear proxy env vars in the relay test network-guard fixture (read .kiro/queue/2026-11-02-strava-publish-relay-outbound-proxy-env.md first)"
context:
  - docs/relay.md
  - relay/src/fitdocs_relay/outbound.py
  - relay/conftest.py
  - .kiro/specs/strava-publish/design.md
blocked_by: []
---

## What
The relay's `Outbound` builds its opener with `urllib.request.ProxyHandler()`, so it honours `HTTPS_PROXY`/system proxy settings. docs/relay.md never says so. Separately, a loopback `HTTPS_PROXY` in a developer's environment would carry a test request off the machine through that handler while the socket guard sees only a loopback connect.

## Why it matters
An operator behind a proxy gets surprising behaviour with no documentation; a test run could reach the real network unnoticed.

## Evidence
- `relay/src/fitdocs_relay/outbound.py:92`: `urllib.request.ProxyHandler(),`
- `grep -n -i proxy docs/relay.md` shows only forwarded-IP and reverse-proxy text (lines 213, 358), nothing about outbound proxies.
- The test-guard half was reported by a reviewer subagent (task 4.1), unverified.

## How to pick it up
1. Add one sentence to docs/relay.md (outbound calls follow the standard proxy environment variables; secrets stay inside the TLS tunnel).
2. In the relay autouse network-guard fixture, delete `HTTPS_PROXY`, `HTTP_PROXY`, `ALL_PROXY` (and lower-case forms) via monkeypatch.
3. Done when a test sets a loopback proxy and still shows the guard refusing the request.
