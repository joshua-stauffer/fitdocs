---
id: 2026-11-05-stress-level-description-says-zero-to-100
title: STRESS_LEVEL says a 0-100 scale while its minimum is 1
status: open
importance: low
importance_why: A description mismatch; values are handled consistently.
effort: S
kind: inconsistency
area: wellness-store, src/fitdocs/wellness/model.py
created: 2026-11-05
surfaced_by: /kiro-impl garmin-connector review
pinned_at: 154315c7
resume_command: "do: Make the STRESS_LEVEL description and its accepted minimum agree"
context:
  - src/fitdocs/wellness/model.py
blocked_by: []
---

## What
The metric's description reads "Garmin's 0–100 scale" while its accepted range starts at 1, so a stress of 0 reads as absent.

## Why it matters
A reader of the description expects 0 to be a value.

## Evidence
`src/fitdocs/wellness/model.py:183-185`.

## How to pick it up
Check whether 0 is a real Garmin value or a sentinel, then change the description or the minimum. A minimum change moves the series.
