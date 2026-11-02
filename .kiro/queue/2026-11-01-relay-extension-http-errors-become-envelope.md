---
id: 2026-11-01-relay-extension-http-errors-become-envelope
title: 'An extension route''s HTTPException is rewritten to a not-offered envelope; Mount prefixes must be sub-paths'
status: open
importance: medium
importance_why: Wrappers will hit both when they add real routes; Req 4.11 says browser-facing extension routes are served outside the envelope.
effort: M
kind: gap
area: relay/src/fitdocs_relay/app.py, relay/src/fitdocs_relay/seam.py, docs/relay.md
created: 2026-11-01
surfaced_by: /kiro-impl relay-server 4.4 review
pinned_at: 774a883c
resume_command: "/kiro-impl relay-server [queue: .kiro/queue/2026-11-01-relay-extension-http-errors-become-envelope.md] Decide and implement how extension routes' own HTTP errors are served"
context:
  - relay/src/fitdocs_relay/app.py
  - relay/src/fitdocs_relay/seam.py
  - .kiro/specs/relay-server/design.md
  - .kiro/specs/relay-server/requirements.md
  - docs/relay.md
  - relay/tests/smoke_extension
blocked_by: []
---

## What
(1) The app registers one `HTTPException` handler for all routes, so an `HTTPException(403)` raised by a route under `/x/<name>/` becomes a 404 `not-offered` envelope. That conflicts with Req 4.11 (served outside the envelope) and the design does not say what an extension's own HTTP errors become.
(2) A Starlette `Mount("/x/<name>/")` normalises to `/x/<name>`, which the seam's prefix rule refuses, so a wrapper must mount at a sub-path such as `/x/<name>/app`. The seam docs do not say so.

## Why it matters
A wrapper author writing a normal 403 or 404 page gets a JSON envelope, and one writing the natural Mount gets a start-up refusal with no guidance.

## Evidence
- `relay/src/fitdocs_relay/app.py:364`: `HTTPException: _not_offered`; `:223-224` the handler.
- Probe (4.4 review): `Route("/x/smoke/forbid")` raising `HTTPException(403)` returned the 404 envelope `not-offered`.
- `relay/src/fitdocs_relay/seam.py:29`: `EXTENSION_ROUTE_PREFIX = "/x/"`.

## How to pick it up
1. Decide the rule: HTTPException under `/x/` passes through unchanged, or stays an envelope (then amend Req 4.11 and the design).
2. Implement by scoping the handler on path prefix; add a test using `relay/tests/smoke_extension`.
3. Add the Mount sub-path note to docs/relay.md's seam section.
