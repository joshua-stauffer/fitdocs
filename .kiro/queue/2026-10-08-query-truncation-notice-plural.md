---
id: 2026-10-08-query-truncation-notice-plural
title: Singular/plural in the `fitdocs query` truncation notice
status: open
importance: low
importance_why: Cosmetic: 'showing the first 1 rows' on stderr disagrees with the '(first 1 row; ...)' footer.
effort: S
kind: inconsistency
area: analytics-query, src/fitdocs/cli.py
created: 2026-10-08
surfaced_by: /kiro-validate-impl analytics-query
pinned_at: cc4af5b
resume_command: "do: singular/plural in the `fitdocs query` truncation notice [queue: .kiro/queue/2026-10-08-query-truncation-notice-plural.md]"
context:
  - src/fitdocs/cli.py
  - src/fitdocs/query/format.py
  - .kiro/specs/analytics-query/design.md
blocked_by: []
---

## What
`src/fitdocs/cli.py:1967` formats `Query: showing the first {max_rows} rows; ...`. The footer now uses the singular for 1, after remediation round 1.

## Why it matters
Two adjacent outputs disagree for `--max-rows 1`.

## Evidence
`fitdocs query --max-rows 1 ...` prints 'showing the first 1 rows'. Observed by the re-validation reviewer (2026-10-08); the line was verified by grep.

## How to pick it up
Reuse format.py's row-noun helper in the notice, update the design's stderr message table, and pin both 1 and N with discrimination.
