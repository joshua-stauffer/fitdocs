---
id: 2026-11-05-transport-and-cli-report-pins-have-small-gaps
title: Two small test gaps: default POST on a 429, and CLI note text
status: open
importance: low
importance_why: Neither path is broken today; each is a wrong change that the suite would miss.
effort: S
kind: gap
area: connectors, tests/connectors/test_http.py, tests/connectors/test_cli_connectors.py
created: 2026-11-05
surfaced_by: /kiro-impl garmin-connector review
pinned_at: 154315c7
resume_command: "do: Pin a default DATA-mode POST retrying a 429, and the full printed text of a pull note"
context:
  - tests/connectors/test_http.py
  - src/fitdocs/connectors/http.py
  - src/fitdocs/cli.py
  - tests/connectors/test_cli_connectors.py
blocked_by: []
---

## What
A `post` hardwired to `retry_rate_limits=False` passes `tests/connectors/test_http.py`, whose POST test uses a 503. Truncating `note.detail` in `cli.py` at its first colon passed the five connector test files tried, except for the one deferral case garmin-connector now pins.

## Why it matters
A later edit could silently change either behavior.

## Evidence
Mutations run by the task 1.2 and 5.1 reviewers: 1102 passed in four files with the hardwired `post`; 521 passed in five files with the truncated note. `src/fitdocs/cli.py:2239,2322,3417`.

## How to pick it up
Add one test each, then re-run those two mutations.
