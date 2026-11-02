---
id: 2026-11-01-http-marked-request-rebuild-unpinned
title: "No test pins that a single-attempt request reaches the transport unchanged apart from the User-Agent"
status: open
importance: low
importance_why: A marked-only rebuild that drops secret fields would survive the suite, but no such rebuild exists today.
effort: S
kind: gap
area: connectors, src/fitdocs/connectors/http.py, tests/connectors/test_http.py
created: 2026-11-01
surfaced_by: "/kiro-impl publish-core"
pinned_at: dd9fcaa1
resume_command: "do: add the transport-equality assertion for marked requests to tests/connectors/test_http.py [queue: .kiro/queue/2026-11-01-http-marked-request-rebuild-unpinned.md]"
context:
  - src/fitdocs/connectors/http.py
  - tests/connectors/test_http.py
blocked_by: []
---

## What
Nothing pins that a single-attempt (marked) request reaches the transport
unchanged apart from the composed User-Agent. A rebuild used only for marked
requests could drop `secret_headers`, `body`, `url_is_secret` or `headers`
and every test would stay green.

## Why it matters
Dropping `secret_headers` or `url_is_secret` would leak what the redaction
fields exist to protect.

## Evidence
`src/fitdocs/connectors/http.py` and `tests/connectors/test_http.py`: no
assertion compares `transport.requests[0]` to the original request.

## How to pick it up
Assert `transport.requests[0] == replace(request, headers={..., 'User-Agent':
user_agent()})` for a marked request, then confirm by mutation that dropping
each field fails it.
