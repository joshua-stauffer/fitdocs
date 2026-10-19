---
id: 2026-10-08-docs-analytics-missing-h1
title: Give docs/analytics.md a page title
status: done
importance: low
importance_why: The page renders untitled; every other docs page opens with an H1.
effort: S
kind: docs
area: analytics-query, docs/analytics.md
created: 2026-10-08
surfaced_by: /kiro-validate-impl analytics-query
pinned_at: cc4af5b
resume_command: "do: give docs/analytics.md a page title [queue: .kiro/queue/2026-10-08-docs-analytics-missing-h1.md]"
context:
  - docs/analytics.md
  - tests/query/test_docs_analytics.py
blocked_by: []
---

## What
`docs/analytics.md` starts at `## Before you start` and has no `# ` line. Other pages (connectors, inbox, install) open with `# Title`.

## Why it matters
The page shows no title on GitHub, and possibly in the site navigation.

## Evidence
`head -3 docs/analytics.md` at the pinned commit.

## How to pick it up
Add an H1. Check whether `tests/query/test_docs_analytics.py` or the docs-site build pins the heading structure, and update the design's heading list if it is enumerated.

## Resolution (2026-10-19, commit 07e50df, branch chore/docs-0-2)

`docs/analytics.md` now opens with `# Analytics`, the page's name in
`docs/index.md`. Checked first: every other `docs/*.md` page has an H1
except `docs/dashboards.md` (same gap, not in this item's scope);
`tests/query/test_docs_analytics.py` enumerates only `## ` headings and the
regenerator writes only between the schema-reference markers, so neither
needed changing; `analytics-query` design.md lists H2 sections only. The
documented-contract test now also pins the H1 ahead of `## Before you start`.
