---
id: 2026-11-02-readme-connector-count-stale
title: README says fitdocs ships two connectors; relay makes three
status: open
importance: low
importance_why: The README's Connectors paragraph is false since relay-server landed.
effort: XS
kind: docs
area: relay-server docs, README.md
created: 2026-11-02
surfaced_by: /kiro-impl intervals-publish
pinned_at: 978c74fa
resume_command: "/kiro-impl relay-server [queue: .kiro/queue/2026-11-02-readme-connector-count-stale.md] Name the relay connector in the README"
context:
  - README.md
  - src/fitdocs/connectors/__init__.py
blocked_by: []
---

## What
README.md's Connectors paragraph says 'fitdocs ships two connectors: folder ... and intervals'. `register(RelayConnector())` makes three (strava-publish will add a fourth).

## Why it matters
First-contact documentation misstates what is installed.

## Evidence
README.md ~156; src/fitdocs/connectors/__init__.py ~186 `register(RelayConnector())`.

## How to pick it up
Reword the paragraph to name the built-in connectors (or avoid a count); coordinate with strava-publish's landing.
