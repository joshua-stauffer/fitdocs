---
id: 2026-11-05-refused-delivery-day-stays-recorded-as-delivered
title: A refused wellness delivery's day stays recorded as delivered
status: open
importance: low
importance_why: Needs a delivery the drain refuses, which requires damage after the pull; the file is reported and quarantined.
effort: M
kind: gap
area: connectors, wellness-store, src/fitdocs/connectors/pull.py
created: 2026-11-05
surfaced_by: /kiro-impl garmin-connector review
pinned_at: 154315c7
resume_command: "do: Decide whether a wellness delivery the drain refuses should clear its days from the connector ledger"
context:
  - src/fitdocs/connectors/pull.py
  - src/fitdocs/connectors/ledger.py
  - .kiro/specs/wellness-store/requirements.md
blocked_by: []
---

## What
The ledger records a day's revision at delivery. If the drain then refuses that delivery, the next pull reports the day as unchanged, exit 0, and the series keeps the older value until the day changes at the source.

## Why it matters
A value can stay stale without further notice after the one quarantine report.

## Evidence
`src/fitdocs/connectors/pull.py:592` (`with_days`). Task 5.2 reviewer, real pull then damage then drain then pull: "Days unchanged", exit 0, series kept 5002 instead of 9999.

## How to pick it up
Read how `with_pending` resolves after a drain, then decide whether a refused pending delivery forgets its days. This covers every wellness connector, not only Garmin.
