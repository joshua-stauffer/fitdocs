---
id: 2026-10-12-small-multiples-vertical-space
title: small-multiples wastes vertical space: 2-tick panels and an empty outer x-label row
status: open
importance: low
importance_why: Cosmetic; lines use under half of each panel and the x title floats 43 px below the panels.
effort: S
kind: gap
area: chart-catalog small-multiples; chart-kit layout.plan_frame
created: 2026-10-12
surfaced_by: /kiro-impl chart-catalog
pinned_at: c52da2d
resume_command: "/kiro-impl chart-catalog [queue: .kiro/queue/2026-10-12-small-multiples-vertical-space.md] tighten small-multiples panel and title spacing"
context:
  - src/fitdocs/render/charts/kit/kinds/small_multiples.py
  - src/fitdocs/render/charts/kit/layout.py
  - .kiro/specs/chart-catalog/design.md
blocked_by: []
---

## What
(1) PANEL_HEIGHT 140 leaves an 84 px panel plot, so `numeric_scale` picks 2 vertical ticks and rounds 0–24 km up to 0–50. (2) The outer `plan_frame` always reserves an x-tick-label row, but panel labels live inside the panel cells, so the outer x title sits 43 px below the last panel's labels (16 px in core charts).

## Why it matters
Both make small multiples look sparse next to the other kinds; (2) needs a `plan_frame` flag (chart-kit) or a kind-local offset.

## Evidence
Reported by the 2.7 reviewer subagent: `tests/render/charts/kit/golden/small-multiples/typical.svg` y labels `0`, `50`; panel labels at y=320, x title at y=363 (impl/chart-catalog c52da2d). scales.py vertical tick count `max(2, floor(length / _VERTICAL_PER_TICK))`.

## How to pick it up
Decide whether PANEL_HEIGHT or the per-panel tick budget changes (design § SmallMultiples) and whether plan_frame gains a has_x_labels flag; regenerate small-multiples goldens.
