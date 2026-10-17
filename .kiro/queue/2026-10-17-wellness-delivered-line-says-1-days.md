---
id: 2026-10-17-wellness-delivered-line-says-1-days
title: The pull report prints "1 days" for a single-day wellness delivery
status: open
importance: low
importance_why: Cosmetic report wording; the design literal "<n> days" is met.
effort: S
kind: chore
area: wellness-pull, src/fitdocs/cli.py
created: 2026-10-17
surfaced_by: maintainer-requested Phase 12 re-validation (wellness-pull reviewer finding 3; confirmed by the parent)
pinned_at: 160b007
resume_command: "do: pluralize the wellness Delivered detail in cli.py (1 day / n days), updating the design literal and its pinning test [queue: .kiro/queue/2026-10-17-wellness-delivered-line-says-1-days.md]"
context:
  - src/fitdocs/cli.py
  - .kiro/specs/wellness-pull/design.md
  - tests/connectors/test_cli_wellness.py
blocked_by: []
---

## What
`src/fitdocs/cli.py:1750` prints `f"  {item.path} ({item.span}, {item.days}
days)"`. A one-day delivery reads
`intervals/wellness-2026-10-11_2026-10-11.json (2026-10-11..2026-10-11, 1 days)`.
The design prescribes the literal `<n> days`, so this is a design-literal
nit, not a deviation. A sibling item of the same species exists for query:
`2026-10-08-query-truncation-notice-plural`.

## Why it matters
The report reads oddly to a maintainer whose daily pull delivers one day.

## Evidence
Code read at 160b007. The reviewer's fake-transport run printed the line
above (synthetic dates).

## How to pick it up
Pluralize (`day` if `days == 1`), amend the design literal (append-only
note), and update the test that pins the line.
