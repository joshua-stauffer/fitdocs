---
id: 2026-11-02-strava-publish-relay-publish-deadlines-unpinned-and-constants-undocumented
title: "Nothing pins the relay's publish and upload deadlines below the fitdocs request timeout, and docs/relay.md omits the budget constants"
status: open
importance: low
importance_why: "Req 7.7 depends on an ordering that only comments hold; the requirements call these values documented."
effort: S
kind: gap
area: "relay/src/fitdocs_relay/strava/publish.py, relay/src/fitdocs_relay/strava/budget.py, docs/relay.md, src/fitdocs/connectors/http.py"
created: 2026-11-02
surfaced_by: "/kiro-validate-impl strava-publish"
pinned_at: 964cc419
resume_command: "do: add a test asserting PUBLISH_DEADLINE_S and UPLOAD_DEADLINE_S are below fitdocs's DEFAULT_TIMEOUT_SECONDS, and document the window, listing size, PRINCIPAL_SHARE, LINK_HEADROOM and deadlines in docs/relay.md (read .kiro/queue/2026-11-02-strava-publish-relay-publish-deadlines-unpinned-and-constants-undocumented.md first)"
context:
  - relay/src/fitdocs_relay/strava/publish.py
  - relay/src/fitdocs_relay/strava/budget.py
  - docs/relay.md
  - src/fitdocs/connectors/http.py
  - .kiro/specs/strava-publish/requirements.md
blocked_by: []
---

## What
`PUBLISH_DEADLINE_S` is 20 and `UPLOAD_DEADLINE_S` 25 (reviewer), fitdocs's default timeout 30; no test compares them. `PRINCIPAL_SHARE` (0.5), `LINK_HEADROOM` (0.2), window and listing size are not in docs/relay.md.

## Why it matters
A later edit to a deadline could exceed the client's timeout silently.

## Evidence
- `relay/src/fitdocs_relay/strava/publish.py:64`: `PUBLISH_DEADLINE_S: Final = 20.0`.
- `relay/src/fitdocs_relay/strava/budget.py:25-26`: `PRINCIPAL_SHARE`, `LINK_HEADROOM`.
- `grep -n 'PRINCIPAL_SHARE\|LINK_HEADROOM\|UPLOAD_DEADLINE' docs/relay.md` -> no output.
- `UPLOAD_DEADLINE_S` value and the fitdocs 30 s default (`DEFAULT_TIMEOUT_SECONDS`) are from the reviewer; the `grep` for the constant name in src found nothing - locate it before writing the test.

## How to pick it up
Locate the client timeout constant, write the ordering test, then add a table of the budget numbers to docs/relay.md.
