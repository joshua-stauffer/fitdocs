---
id: 2026-10-12-chart-kit-design-wording-rulings
title: chart-kit design wording questions left open
status: open
importance: low
importance_why: Ambiguous design text invites divergent downstream readings.
effort: XS
kind: design-gap
area: chart-kit design.md
created: 2026-10-12
surfaced_by: /kiro-impl chart-kit (reviews + /kiro-validate-impl)
pinned_at: d03e85e
resume_command: "/kiro-impl chart-kit [queue: .kiro/queue/2026-10-12-chart-kit-design-wording-rulings.md] chart-kit design wording questions left open"
context:
  - .kiro/specs/chart-kit/design.md
  - src/fitdocs/render/charts/kit/format.py
blocked_by: []
---

## What
(1) clean_text 'collapses CR/LF/tab to a space' — implemented per character (CRLF → two spaces) vs per run; it is a revalidation trigger consumed by dashboards. (2) Settled Seams Theme says the base ink is ≥3.96:1; measured minimum 4.004:1. (3) Stacked charts describe y by raw values, not stack totals (Req 10.1 'range of each axis' ambiguous). (4) MarkBound/channel description wording differs across kinds in describe_kinds.

## Why it matters
Dashboards consumes clean_text and describe_kinds text.

## Evidence
2.2, 2.4, 5.2 reviews; describe_kinds dump.

## How to pick it up
Rule each; amend design and, for (1)/(4), the code + tests in one change.
