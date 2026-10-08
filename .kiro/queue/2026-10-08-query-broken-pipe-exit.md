---
id: 2026-10-08-query-broken-pipe-exit
title: Decide `fitdocs query` behavior on a closed stdout (broken pipe)
status: open
importance: low
importance_why: `fitdocs query ... | head -1` exits 1 silently; Req 4 says a failure is never mistaken for an empty answer, but a consumer closing the pipe is not a query failure.
effort: S
kind: research
area: analytics-query, src/fitdocs/cli.py
created: 2026-10-08
surfaced_by: /kiro-validate-impl analytics-query
pinned_at: cc4af5b
resume_command: "do: decide `fitdocs query` behavior on a closed stdout (broken pipe) [queue: .kiro/queue/2026-10-08-query-broken-pipe-exit.md]"
context:
  - src/fitdocs/cli.py
  - .kiro/specs/analytics-query/requirements.md
  - .kiro/specs/analytics-query/design.md
blocked_by: []
---

## What
There is no BrokenPipeError/EPIPE handling in `src/fitdocs/cli.py` (grep finds none). When stdout closes early, the process exits 1 with no message.

## Why it matters
Scripts that pipe into `head` see a nonzero exit, which may read as a failed query.

## Evidence
Reported by the 2026-10-08 validation reviewer (smoke run, ownership UNCLEAR). The missing handler was verified by grep; the behavior was not re-run by the parent.

## How to pick it up
Read Req 4 and the design's exit-code table, and decide the intended code (0 and silent is the common convention, as is 141). Implement it in `query_command`, pin it with a real pipe test, and document it in `docs/analytics.md` if it changes.
