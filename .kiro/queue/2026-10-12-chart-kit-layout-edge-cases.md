---
id: 2026-10-12-chart-kit-layout-edge-cases
title: Layout edge cases: plot collapse, sub-pixel margin crossing, band-label room by subtraction, hbar height cap
status: open
importance: low
importance_why: Degenerate canvases render silently wrong.
effort: S
kind: defect
area: chart-kit layout/frame/hbar
created: 2026-10-12
surfaced_by: /kiro-impl chart-kit (reviews + /kiro-validate-impl)
pinned_at: d03e85e
resume_command: "/kiro-impl chart-kit [queue: .kiro/queue/2026-10-12-chart-kit-layout-edge-cases.md] Layout edge cases: plot collapse, sub-pixel margin crossing, band-label room by subtraction, hbar height cap"
context:
  - src/fitdocs/render/charts/kit/layout.py
  - src/fitdocs/render/charts/kit/frame.py
  - src/fitdocs/render/charts/kit/kinds/hbar.py
blocked_by: []
---

## What
(1) plan_frame lets the plot height collapse to 0 when the legend fills a small canvas (320×160, 8 long series) → flat marks, no warning. (2) Overhang measured on the provisional plot; after the plot narrows labels can cross PAD/width−4 by ≤0.49 px (62/3780 sweep cases, line and area). (3) frame.axis derives side band-label room by subtraction, so an exactly-fitting label truncates on float noise (hbar adds `_FIT_SLACK=1e-6`). (4) hbar auto height is uncapped (50 rows → 1391 px) while the explicit height option caps at 1200.

## Why it matters
Small but real layout correctness gaps.

## Evidence
5.1/5.2/5.4 reviews; frame.py:277-288; hbar `_FIT_SLACK`.

## How to pick it up
Refuse or note a collapsed plot; iterate the overhang pass to a fixed point or add slack; compute band-label room from the plan directly; state the hbar height asymmetry in design or cap it.
