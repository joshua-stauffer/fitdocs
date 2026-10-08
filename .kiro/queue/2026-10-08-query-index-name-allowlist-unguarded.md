---
id: 2026-10-08-query-index-name-allowlist-unguarded
title: Pin the exact `fitdocs.index` names `fitdocs.query` may import
status: open
importance: low
importance_why: The code complies with the design's Seam 5 name list today, but no guard stops a new import of a non-listed index name.
effort: S
kind: gap
area: analytics-query, tests/query/test_boundary.py
created: 2026-10-08
surfaced_by: /kiro-validate-impl analytics-query
pinned_at: cc4af5b
resume_command: "do: pin the exact `fitdocs.index` names `fitdocs.query` may import [queue: .kiro/queue/2026-10-08-query-index-name-allowlist-unguarded.md]"
context:
  - tests/query/test_boundary.py
  - .kiro/specs/analytics-query/design.md
  - src/fitdocs/query
blocked_by: []
---

## What
design.md (around lines 125-160) lists the `fitdocs.index` names the query package may use. `tests/query/test_boundary.py` pins the module direction but not that name list.

## Why it matters
Boundary erosion into index internals would pass review silently.

## Evidence
Reported by the 2026-10-08 validation reviewer (note N2); not re-verified by the parent beyond reading the report.

## How to pick it up
Add an AST guard in `test_boundary.py` that collects every `from fitdocs.index... import` in `src/fitdocs/query` and asserts it is a subset of the design's list. Mutation: import one non-listed name, and the guard reds.
