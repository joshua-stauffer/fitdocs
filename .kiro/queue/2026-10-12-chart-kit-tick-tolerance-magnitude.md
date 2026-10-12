---
id: 2026-10-12-chart-kit-tick-tolerance-magnitude
title: ticks: float tolerance scales with input magnitude
status: open
importance: medium
importance_why: Large-magnitude inputs can get nice ticks that do not enclose the data.
effort: S
kind: defect
area: chart-kit kit/ticks.py
created: 2026-10-12
surfaced_by: /kiro-impl chart-kit (reviews + /kiro-validate-impl)
pinned_at: d03e85e
resume_command: "/kiro-impl chart-kit [queue: .kiro/queue/2026-10-12-chart-kit-tick-tolerance-magnitude.md] ticks: float tolerance scales with input magnitude"
context:
  - src/fitdocs/render/charts/kit/ticks.py
  - src/fitdocs/render/charts/kit/scales.py
blocked_by: []
---

## What
`_TOLERANCE * max(|lo|,|hi|) / step` grows with magnitude: ~64 s for epoch seconds in clock_ticks (scales now works around it by passing seconds relative to midnight), and for linear_ticks on large numbers the rounding can leave nice=True ticks that do not enclose the data.

## Why it matters
Any caller passing large absolute values (epoch seconds, big counters) gets ceil/floor behaving like round.

## Evidence
4.1 review: clock_ticks on epoch seconds misplaced ticks; clock_ticks(43220.0, 43800.0, 8) correct. ticks.py:166,:357 (at d03e85e).

- chart-catalog (2026-10-12, c52da2d): the non-enclosure also happens for SMALL values: `linear_ticks(0, 0.1 + 0.2, 6)` ends at 0.3 < hi (rounding to 12 significant figures + `_ceil` snapping within tolerance), while the `linear_ticks` docstring (`ticks.py` ~line 148) says the outermost ticks enclose the data. `cells.BinnedScale.classify` now clamps a value above the last edge into the top bin as a workaround (design § Cells amended, task 1.4). Fixing the tick contract would let that clamp go.

## How to pick it up
Make the tolerance relative to the step or span instead of the magnitude; add tests with 1e10-scale linear inputs and epoch-second clock inputs; keep the scales relative-base workaround or drop it once ticks is fixed.
