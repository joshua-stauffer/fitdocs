---
id: 2026-10-01-docs-site-smoke-misses-content-asset-in-html
title: "The smoke build never asserts that a content asset (images/diagram.svg) reaches the built html/"
status: open
importance: low
importance_why: "Req 1.5 is pinned at staging only; a generator bump that stopped copying assets would slip through."
effort: S
kind: gap
area: docs-site, tests/sitebuild/test_build_smoke.py
created: 2026-10-01
surfaced_by: /kiro-impl docs-site (validation)
pinned_at: ba76d03
resume_command: "/kiro-impl docs-site [queue: .kiro/queue/2026-10-01-docs-site-smoke-misses-content-asset-in-html.md] The smoke build never asserts that a content asset (images/diagram.svg) reaches the built "
context:
  - tests/sitebuild/test_build_smoke.py
  - tests/sitebuild/fixtures/site
blocked_by: []
---

## What
test_build_smoke checks `_brand/hero-chart.svg` but not a content asset.

## Why it matters
Req 1.5 partial coverage.

## Evidence
- Coverage-validation reviewer matrix, 1.5 PARTIAL (pinned at ba76d03).

## How to pick it up
1. Add an assertion that `html/images/diagram.svg` exists and is byte-identical to the fixture copy.
2. Mutate the stager to drop assets; confirm red.
