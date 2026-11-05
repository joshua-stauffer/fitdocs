---
id: 2026-11-05-activities-failing-at-the-front-can-stall-a-garmin-history
title: Activities that always fail at the front of the history can stall a Garmin first pull
status: open
importance: low
importance_why: Needs persistent failures on the oldest activities; visible in every report, and unmeasured on a real account.
effort: M
kind: gap
area: garmin-connector, connectors, src/fitdocs/connectors/garmin.py, src/fitdocs/connectors/pull.py
created: 2026-11-05
surfaced_by: /kiro-impl garmin-connector review
pinned_at: 154315c7
resume_command: "do: After the garmin-connector live check, decide whether a permanently failing activity needs a way out of the per-pull limit"
context:
  - src/fitdocs/connectors/garmin.py
  - src/fitdocs/connectors/pull.py
  - .kiro/specs/garmin-connector/design.md
  - .kiro/specs/garmin-connector/tasks.md
blocked_by: [garmin-connector]
---

## What
A failed activity stays not final, holds the watermark and takes a slot of the 200 per pull. With 200 permanent failures at the front every pull reads fetched 0, failed 200. Five server errors in a row at the front end each activity pull at the same place. No athlete-side skip exists.

## Why it matters
Later history could wait indefinitely, though each report shows the failures.

## Evidence
Task 3.4 reviewer, through `run_pull`: `(fetched 0, listed 200, failed 200, 250 more)` on every pull with 200 permanent failures. Task 3.5 reviewer: with one always-failing activity, the watermark stayed put over two pulls. The five-in-a-row case is reasoned from Req 6.6 and `_count_failure`, not run at the front of a history.

## How to pick it up
Wait for task 7.2's findings. If real accounts show persistent failures, design a skip that stays visible and reversible. Otherwise close it.
