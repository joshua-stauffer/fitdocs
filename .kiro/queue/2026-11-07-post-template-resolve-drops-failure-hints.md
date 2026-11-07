---
id: 2026-11-07-post-template-resolve-drops-failure-hints
title: "Keep the query module's failure hint in post-template STATEMENT_FAILED details"
status: open
importance: low
importance_why: "Users lose the actionable hint (e.g. out of memory) that `fitdocs query` prints for the same failure."
effort: S
kind: gap
area: "post-templates, src/fitdocs/post_template/resolve.py"
created: 2026-11-07
surfaced_by: /kiro-impl post-templates
pinned_at: e1fdf861
resume_command: "do: in post_template/resolve.py, append StatementFailed.hint to the STATEMENT_FAILED detail when present (except the TIMESTAMPTZ hint, already mapped) [queue: .kiro/queue/2026-11-07-post-template-resolve-drops-failure-hints.md]"
context:
  - src/fitdocs/post_template/resolve.py
  - src/fitdocs/query/statement.py
blocked_by: []
---

## What
`SessionResolver.resolve` maps `StatementFailed` to a one-line `str(error)` and drops `error.hint`, apart from the TIMESTAMPTZ case.

## Why it matters
The check and refill output says less than `fitdocs query` for the same SQL error.

## Evidence
Reported by a reviewer subagent during `/kiro-impl post-templates`, which ran the probe; the parent session did not re-run it. See `src/fitdocs/query/statement.py` `failure_hint` and resolve.py's `_one_line(str(error))` mapping.

## How to pick it up
1. Read `failure_hint`.
2. Join hint and message on one line in resolve.
3. Pin it with a fake `StatementFailed` carrying a hint.
