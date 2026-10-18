---
id: 2026-10-12-chart-kit-first-band-label-truncated-at-left-edge
title: Band x axes cut the first tick label short at the left canvas edge
status: done
importance: medium
importance_why: Hits the canonical weekly heatmap and every bar/stacked-100 chart over weeks: the first date label reads `2026-0…`.
effort: S
kind: bug
area: chart-kit frame.axis / layout.plan_frame; chart-catalog heatmap, stacked-100; core bar
created: 2026-10-12
surfaced_by: /kiro-impl chart-catalog
pinned_at: c52da2d
resume_command: "/kiro-impl chart-kit [queue: .kiro/queue/2026-10-12-chart-kit-first-band-label-truncated-at-left-edge.md] reserve the first band label's left overhang"
context:
  - src/fitdocs/render/charts/kit/frame.py
  - src/fitdocs/render/charts/kit/layout.py
  - .kiro/specs/chart-kit/design.md
blocked_by: []
---

## What
`frame.axis` fits each bottom band label to `2*min(at - PAD, width - PAD - at)` (frame.py ~250–262), and band kinds pass `x_label_overhang=0.0`, so nothing is reserved on the left: the first label is truncated to fit the space between the canvas edge and its band centre.

## Why it matters
Truncated labels on the most common dashboard shapes (weeks × zones heatmap, weekly bars). Numeric axes already reserve the overhang (line/area); band axes do not.

## Evidence
Reported and reproduced by the 2.2 reviewer subagent: heatmap 26 weeks at 720 px → first label `2026-0…`, 52 weeks → `2026-…`, 8 weeks at 320 px → `2026-01-…`; core bar 26 weeks → `2026-01-…`; `tests/render/charts/kit/golden/heatmap/at_bound.svg` first x label is `2026-0…` (on impl/chart-catalog c52da2d).

## How to pick it up
Open frame.py's BOTTOM band-label branch and layout.plan_frame's `x_label_overhang`. Measure the first band label's left overhang in band kinds (bar, stacked-100, heatmap) like line/area do, or have plan_frame reserve it. Done when the first label of a 26-week band axis at 720 px is untruncated and bar/heatmap/stacked-100 goldens regenerate with the change only at the left margin.

## Resolution (2026-10-18)

Fixed on main at 227729d (review APPROVED). New `cartesian.band_x_axis` widens the left margin by the first
band label's shortfall (re-planning up to 6 passes; measured max 3; silent fallback to frame.axis's
edge clamp), capped at 25% of the canvas so a very long first category does not squeeze the plot --
labels wider than the cap are still cut (recorded in chart-kit design.md, said in the CHANGELOG). Wired
into bar, stacked-100, box and heatmap; only kit golden heatmap/at_bound.svg moved. The right-edge
counterpart is queued: .kiro/queue/2026-10-18-band-axis-last-label-cut-at-right-edge.md.
