---
id: 2026-11-05-intervals-403-still-calls-export-the-garmin-route
title: The intervals 403 message still calls the export the route for Garmin wellness
status: open
importance: medium
importance_why: A printed next step contradicts the corrected docs now that a Garmin connector ships.
effort: S
kind: inconsistency
area: wellness-pull, src/fitdocs/connectors/intervals.py
created: 2026-11-05
surfaced_by: /kiro-impl garmin-connector review
pinned_at: 154315c7
resume_command: "/kiro-impl wellness-pull [queue: .kiro/queue/2026-11-05-intervals-403-still-calls-export-the-garmin-route.md] Name the garmin connector in the intervals 403 message"
context:
  - src/fitdocs/connectors/intervals.py
  - .kiro/specs/wellness-pull/requirements.md
  - tests/connectors/test_intervals_wellness_pull.py
  - tests/connectors/test_intervals_wellness.py
  - docs/connectors.md
blocked_by: []
---

## What
When intervals.icu answers a wellness request with 403, fitdocs prints "Garmin's own data export is the route for Garmin wellness". Since garmin-connector, the Garmin connector is also a route, and docs/connectors.md says so.

## Why it matters
An athlete blocked at intervals.icu is pointed only at the manual export, against the docs.

## Evidence
`src/fitdocs/connectors/intervals.py:180`. garmin-connector design keeps `intervals` untouched and wellness-pull Req 12.2 binds the sentence, so it was not changed there. Code pins, per the task 6.2 reviewer: `tests/connectors/test_intervals_wellness_pull.py:445`, `tests/connectors/test_intervals_wellness.py:492,1191,1240`.

## How to pick it up
Amend wellness-pull Req 12.2. Proposed text: "Garmin's own data export or the garmin connector is the route for Garmin wellness (see the wellness guide)." Update the four code pins, which test code and so are updated, not deleted.

## Update 2026-11-06: fixed on chore/pre-cut-fixes
The message and its four pins use the proposed sentence, recorded as wellness-pull Amendment 2. Correction to this item: the sentence is bound by Requirement 9 criterion 2 (`requirements.md:202`), not 12.2. Requirement 12 criterion 2 covers the documentation, which already names both routes, and was not changed. Restoring the old sentence reds six test cases. Left open for the maintainer to close.
