---
id: 2026-11-02-strava-publish-reserved-prefixes-have-no-runtime-reader
title: "RESERVED_PREFIXES in the relay routes module has no runtime reader; its Strava entries are enforced by nothing"
status: open
importance: low
importance_why: "A list that reads as a guard but only two tests pin it."
effort: S
kind: chore
area: "relay/src/fitdocs_relay/routes.py, relay/tests/test_targets_pipeline.py, relay/tests/test_app_pipeline.py"
created: 2026-11-02
surfaced_by: "/kiro-impl strava-publish 7.5 review"
pinned_at: 964cc419
resume_command: "do: either enforce RESERVED_PREFIXES where extension routes are mounted or document it as a test-only list (read .kiro/queue/2026-11-02-strava-publish-reserved-prefixes-have-no-runtime-reader.md first)"
context:
  - relay/src/fitdocs_relay/routes.py
  - .kiro/specs/strava-publish/design.md
blocked_by: []
---

## What
`RESERVED_PREFIXES` now lists `/connect/`, `/strava/`, `/go/`, `/privacy`, `/robots.txt` in addition to the original four, but the only references are two test assertions.

## Why it matters
An extension route could collide with a reserved prefix undetected.

## Evidence
`grep -rn RESERVED_PREFIXES relay src` -> routes.py:73 (definition), relay/tests/test_targets_pipeline.py:163, relay/tests/test_app_pipeline.py:529.

## How to pick it up
Look at how extension routes are mounted (see 2026-11-01-relay-extension-http-errors-become-envelope.md); enforce at mount time or relabel.
