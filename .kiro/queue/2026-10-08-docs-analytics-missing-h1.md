---
id: 2026-10-08-docs-analytics-missing-h1
title: Give docs/analytics.md a page title
status: open
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
