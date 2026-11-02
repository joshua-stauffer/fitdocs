---
id: 2026-11-02-strava-publish-relay-largest-upload-body-fit-test-missing
title: "No test shows the largest valid upload body fits under MAX_UPLOAD_REQUEST_BYTES"
status: open
importance: low
importance_why: "The envelope overhead could push a maximum-size upload over the route's bound unnoticed."
effort: S
kind: chore
area: "relay/src/fitdocs_relay/routes.py, relay/tests/test_targets_pipeline.py"
created: 2026-11-02
surfaced_by: "/kiro-impl strava-publish 1.2 review"
pinned_at: 964cc419
resume_command: "do: add a test that builds the largest valid upload (max file bytes plus envelope fields, base encoding) and shows it is within MAX_UPLOAD_REQUEST_BYTES (read .kiro/queue/2026-11-02-strava-publish-relay-largest-upload-body-fit-test-missing.md first)"
context:
  - relay/src/fitdocs_relay/routes.py
  - relay/src/fitdocs_relay/shared/relay_envelope.py
  - src/fitdocs/connectors
blocked_by: []
---

## What
The route bound is `MAX_UPLOAD_REQUEST_BYTES` (routes.py:56, :86); nothing builds a maximum-size request to show it passes.

## Why it matters
Off-by-overhead would refuse legitimate maximum uploads.

## Evidence
`relay/src/fitdocs_relay/routes.py:56,86`; absence of the test is the reviewer's claim (1.2), unverified.

## How to pick it up
Find the maximum file size constant, construct the request body the client would send, assert length <= bound and that the pipeline admits it.
