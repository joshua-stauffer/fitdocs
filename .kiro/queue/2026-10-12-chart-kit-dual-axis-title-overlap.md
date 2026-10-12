---
id: 2026-10-12-chart-kit-dual-axis-title-overlap
title: Dual-axis charts: left and right axis titles can overlap
status: open
importance: medium
importance_why: chart-catalog task 1.1 item 3 is a stop-and-report seam check that will fail against the landed frame.axis.
effort: S
kind: seam-defect
area: chart-kit frame.axis / chart-catalog dual-axis
created: 2026-10-12
surfaced_by: /kiro-impl chart-kit (reviews + /kiro-validate-impl)
pinned_at: d03e85e
resume_command: "/kiro-impl chart-kit [queue: .kiro/queue/2026-10-12-chart-kit-dual-axis-title-overlap.md] Dual-axis charts: left and right axis titles can overlap"
context:
  - src/fitdocs/render/charts/kit/frame.py
  - .kiro/specs/chart-catalog/tasks.md
  - .kiro/specs/chart-catalog/design.md
blocked_by: []
---

## What
`frame.axis` fits the LEFT axis title to `width − PAD − plot.left` (nearly the full width) and end-anchors the RIGHT title at `plot.right`; each side is fitted independently, so on a dual-axis chart two long titles on the shared y-title row overlap.

## Why it matters
chart-catalog's dual-axis kind expects (tasks.md:21-23, seam check 3) the right title end-anchored and not overlapping a left title; its task 1.1 stops on this.

## Evidence
Validation probe (chart-kit validate-impl, 2026-10-12): two long titles at width 720 → left spans x 46–447, right spans 270–664 (≈177 px overlap). frame.py:305-314 (at d03e85e).

## How to pick it up
Decide whether frame.axis takes a shared title-row budget (e.g. an optional `max_title_width`) or chart-catalog splits the row itself; add a test with both titles long at width 720 asserting no overlap. Read chart-catalog tasks.md 1.1 item 3 first.
