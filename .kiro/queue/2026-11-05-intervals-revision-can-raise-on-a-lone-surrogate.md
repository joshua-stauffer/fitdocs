---
id: 2026-11-05-intervals-revision-can-raise-on-a-lone-surrogate
title: The intervals content revision can raise on a lone surrogate
status: open
importance: low
importance_why: Needs an unusual JSON escape in a record with no updated field; reasoned, not run.
effort: S
kind: bug
area: wellness-pull, src/fitdocs/connectors/intervals.py
created: 2026-11-05
surfaced_by: /kiro-impl garmin-connector review
pinned_at: 154315c7
resume_command: "do: Confirm whether a lone surrogate breaks intervals _content_revision, and fix it if so"
context:
  - src/fitdocs/connectors/intervals.py
  - src/fitdocs/connectors/garmin.py
blocked_by: []
---

## What
`_content_revision` in `intervals.py` uses `ensure_ascii=False` then `.encode("utf-8")`, which raises `UnicodeEncodeError` on a lone surrogate from a JSON `\\ud83d` escape.

## Why it matters
A raw exception instead of a named problem during a wellness pull.

## Evidence
`src/fitdocs/connectors/intervals.py:715-720`. Reasoned from the same form in Garmin, where `test_a_lone_surrogate_in_a_value_is_kept_and_hashed` goes red; not run on intervals (task 4.1 reviewer).

## How to pick it up
Write the failing test first. `ensure_ascii=True` would change every non-ASCII revision and so re-deliver those days, so weigh that.
