---
id: 2026-10-12-calendar-heatmap-axis-spans-plot-not-grid
title: calendar-heatmap: the date axis spans the plot, not the grid, when cells are capped
status: open
importance: low
importance_why: Cosmetic: a short span draws a 640 px baseline under a narrow grid, and a tall explicit height leaves a gap above the axis.
effort: S
kind: gap
area: chart-catalog calendar-heatmap
created: 2026-10-12
surfaced_by: /kiro-impl chart-catalog
pinned_at: c52da2d
resume_command: "/kiro-impl chart-catalog [queue: .kiro/queue/2026-10-12-calendar-heatmap-axis-spans-plot-not-grid.md] align the calendar date axis with the grid"
context:
  - src/fitdocs/render/charts/kit/kinds/calendar_heatmap.py
  - .kiro/specs/chart-catalog/design.md
blocked_by: []
---

## What
When the pitch is capped at CAL_MAX_CELL the grid is narrower than the plot, but the date axis baseline and its title span the whole plot; with an explicit height taller than the auto height the grid sits at the plot top with the axis at plot.bottom and a gap between.

## Why it matters
Design § CalendarHeatmap is silent; the result looks unanchored for short spans (single day, a few weeks).

## Evidence
Reported by the 2.1 reviewer subagent: `tests/render/charts/kit/golden/calendar-heatmap/single.svg` baseline x 43.2 → 680.8 under a 20 px grid (impl/chart-catalog c52da2d).

## How to pick it up
Decide (design) whether the axis spans the grid (and the title centres on it) and whether an explicit tall height anchors the grid to the axis; implement and regenerate the affected goldens.
