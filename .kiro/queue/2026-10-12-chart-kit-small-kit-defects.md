---
id: 2026-10-12-chart-kit-small-kit-defects
title: Small chart-kit output defects: -0.0 deltas, zero-column table, histogram bin_width listing
status: open
importance: low
importance_why: Visible but rare output oddities.
effort: S
kind: defect
area: chart-kit format, stat, table, histogram
created: 2026-10-12
surfaced_by: /kiro-impl chart-kit (reviews + /kiro-validate-impl)
pinned_at: d03e85e
resume_command: "/kiro-impl chart-kit [queue: .kiro/queue/2026-10-12-chart-kit-small-kit-defects.md] Small chart-kit output defects: -0.0 deltas, zero-column table, histogram bin_width listing"
context:
  - src/fitdocs/render/charts/kit/format.py
  - src/fitdocs/render/charts/kit/kinds/stat.py
  - src/fitdocs/render/charts/kit/kinds/table.py
  - src/fitdocs/render/charts/kit/kinds/histogram.py
blocked_by: []
---

## What
(1) format_delta and stat's percent take the sign from the unrounded value, printing `-0.0 km`/`-0.0%` (value 10.0 vs 10.01). (2) A zero-column table renders invalid GFM `|  |\n|  |\n\nNo data`. (3) histogram `bin_width > 0` is not machine-readable in describe_kinds (`minimum: None`) and its over_bound puts the bin count into `rows`.

## Why it matters
Agents reading describe_kinds cannot learn the >0 rule; -0.0 reads as a regression.

## Evidence
Probe `(-0.0 km, -0.1% vs 10.0 km)`; format.py:183, stat.py:114, histogram.py:191,223-224 (at d03e85e).

## How to pick it up
Normalise the sign after rounding; refuse or special-case zero-column tables at stage 1; consider an exclusive-minimum in OptionSpec or describe the >0 rule in the option description.
