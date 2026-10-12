---
id: 2026-10-12-value-order-fallback-unit-name
title: band/box value_order fallback writes the unit's name (`w`) where the rounded form writes its symbol (`W`)
status: open
importance: low
importance_why: Only reached when rounding hides a low/high difference; reads oddly.
effort: S
kind: inconsistency
area: chart-catalog band, box
created: 2026-10-12
surfaced_by: /kiro-impl chart-catalog
pinned_at: c52da2d
resume_command: "/kiro-impl chart-catalog [queue: .kiro/queue/2026-10-12-value-order-fallback-unit-name.md] use the unit symbol in the exact value_order fallback"
context:
  - src/fitdocs/render/charts/kit/kinds/band.py
  - src/fitdocs/render/charts/kit/kinds/box.py
  - src/fitdocs/units.py
blocked_by: []
---

## What
`_exact` in band.py and box.py (10-significant-digit fallback when two formatted values are equal) appends `column.unit` (e.g. `w`), so a message reads `175.4 w above 175.2 w` while the rounded form shows `175 W`.

## Why it matters
Inconsistent unit display inside one product's error messages.

## Evidence
2.5 reviewer subagent (impl/chart-catalog c52da2d); `_exact` code in both kinds.

## How to pick it up
Use the unit's display symbol (whatever format_value uses) in both `_exact` helpers; update their fallback tests. Consider moving `_exact` into the shared layer (see `2026-10-12-chart-kit-shared-helper-duplication`).
