---
id: 2026-11-05-wellness-json-recursion-escapes-refusal
title: Deeply nested JSON raises RecursionError past the wellness refusal path
status: open
importance: low
importance_why: Needs a pathological file in the inbox; the failure is a traceback, with no wrong data.
effort: S
kind: bug
area: wellness-store, src/fitdocs/wellness/probe.py, src/fitdocs/wellness/archive.py
created: 2026-11-05
surfaced_by: /kiro-impl garmin-connector review
pinned_at: 154315c7
resume_command: "do: Refuse deeply nested JSON in the wellness inbox with the normal format message"
context:
  - src/fitdocs/wellness/probe.py
  - src/fitdocs/wellness/archive.py
  - src/fitdocs/wellness/formats/garmin.py
blocked_by: []
---

## What
`probe.py` catches only `ValueError` and `UnicodeError` around `json.loads`, and `commit_original` only `WellnessFormatError` and `OSError`, so a very deeply nested JSON file escapes as `RecursionError`.

## Why it matters
One bad file could end a drain with a traceback rather than a named refusal.

## Evidence
`src/fitdocs/wellness/probe.py:82`. Task 2.1 reviewer: 200,000 nested brackets raised `RecursionError` from `SLEEP_FORMAT.parse` and `PERSONAL_FORMAT.parse`. The drain path was read, not run.

## How to pick it up
Reproduce through a drain with such a file. Catching `RecursionError` beside `ValueError` is the likely fix.
