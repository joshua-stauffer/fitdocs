---
id: 2026-11-07-post-template-check-only-parses-sql
title: Bind-check post-template SQL once in check instead of failing every page
status: open
importance: low
importance_why: An unknown column passes check, then fails every page as STATEMENT_FAILED.
effort: S
kind: gap
area: post-templates, src/fitdocs/post_template/resolve.py
created: 2026-11-07
surfaced_by: /kiro-impl post-templates
pinned_at: e1fdf861
resume_command: "/kiro-spec-design post-templates [queue: .kiro/queue/2026-11-07-post-template-check-only-parses-sql.md] Consider a prepare/bind step in SessionResolver.check"
context:
  - src/fitdocs/post_template/resolve.py
  - .kiro/specs/post-templates/design.md
blocked_by: []
---

## What
`check` only screens and lints (parse level). Binder errors such as `SELECT nosuch FROM pages WHERE start_time_local <= $as_of` pass `check`. That is the 2.3 ruling recorded in design.md.

## Why it matters
The user learns of a typo'd column only through per-page failures.

## Evidence
Reported by a reviewer subagent during `/kiro-impl post-templates`, which ran the probe; the parent session did not re-run it. `check` returned `()` for that SQL.

## How to pick it up
1. Check whether the sandbox can `PREPARE` or `EXPLAIN` without executing.
2. If so, add a bind step to `check` that reports once.
3. Update the design ruling.
