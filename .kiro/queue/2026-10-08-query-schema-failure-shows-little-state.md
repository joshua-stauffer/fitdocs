---
id: 2026-10-08-query-schema-failure-shows-little-state
title: Req 10.8: show more index state when `--schema` cannot open the index
status: open
importance: low
importance_why: The requirement asks for 'as much of the state as it can read'; today an absent, corrupt or busy index prints only a one-line reason.
effort: S
kind: gap
area: analytics-query, src/fitdocs/cli.py, src/fitdocs/query/command.py
created: 2026-10-08
surfaced_by: /kiro-validate-impl analytics-query
pinned_at: cc4af5b
resume_command: "do: req 10.8: show more index state when `--schema` cannot open the index [queue: .kiro/queue/2026-10-08-query-schema-failure-shows-little-state.md]"
context:
  - .kiro/specs/analytics-query/requirements.md
  - src/fitdocs/query/command.py
  - src/fitdocs/cli.py
blocked_by: []
---

## What
When the index is absent, corrupt, busy or unverified, `--schema` prints only the reason, with no path and no workout-page count. State is printed only when bookkeeping is unreadable or the schema version differs (`command.py` around lines 154 and 168-184).

## Why it matters
Agents diagnosing a broken index get less context than the requirement promises.

## Evidence
Reported by the 2026-10-08 validation reviewer (note N1). The design permits the narrower behavior ('when a state was read'), so this is a requirement/design gap rather than a defect.

## How to pick it up
Decide whether to widen the behavior (print the index path and the data root's page count, which are readable without the index) or narrow Req 10.8's wording. Either way, pin the result.
