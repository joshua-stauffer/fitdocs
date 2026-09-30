---
id: 2026-09-30-palette-power-cadence-same-hue
title: Power and cadence series colors share a hue although the palette comment says all series are distinguishable
status: open
importance: low
importance_why: When a ride's hero chart plots power and cadence together (no HR/speed), the two lines are near-identical amber.
effort: S
kind: inconsistency
area: workout-docs, src/fitdocs/render/charts/palette.py
created: 2026-09-30
surfaced_by: /kiro-impl running-dynamics
pinned_at: 8b07b9f
resume_command: "do: give cadence a distinct hue in src/fitdocs/render/charts/palette.py (or correct the comment) and regenerate affected chart goldens"
context:
  - src/fitdocs/render/charts/palette.py
  - src/fitdocs/render/sections.py
  - .kiro/specs/workout-docs/design.md
blocked_by: []
---

## What
`POWER_COLOR = "#cd6600"  # oklch(0.62 0.17 60)` and `CADENCE_COLOR = "#c66000"  # oklch(0.6 0.17 60)` share hue 60. The palette comments say the series hues are spread "so those nine stay mutually distinguishable" and "so all eleven stay mutually distinguishable". `hero_chart_spec` can pick power and cadence as its two series when heart rate and speed are absent.

## Why it matters
The chart becomes unreadable for exactly the sparse-data rides the hero chart's fallback exists for, and the comment claims otherwise.

## Evidence
The constants and comments are read at 8b07b9f in src/fitdocs/render/charts/palette.py (lines ~42-59). The hero precedence observation came from the running-dynamics 3.1 reviewer subagent; it was not re-run here.

## How to pick it up
1. Confirm the precedence in `hero_chart_spec` can yield (power, cadence).
2. Pick a cadence hue not used by the eleven, using the oklch conversion test in tests/render/charts/test_palette.py.
3. Regenerate the affected chart goldens and check that only the cadence colour changed.
4. If this is a deliberate power-family choice, fix the comment instead.
