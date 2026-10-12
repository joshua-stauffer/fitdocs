---
id: 2026-10-12-chart-kit-shared-helper-duplication
title: Move per-kind copies of overhang, duration-family and range formatting into the shared layer
status: open
importance: medium
importance_why: chart-catalog's eight kinds will copy these again, multiplying drift risk.
effort: M
kind: debt
area: chart-kit kinds / shared layer
created: 2026-10-12
surfaced_by: /kiro-impl chart-kit (reviews + /kiro-validate-impl)
pinned_at: d03e85e
resume_command: "/kiro-impl chart-kit [queue: .kiro/queue/2026-10-12-chart-kit-shared-helper-duplication.md] Move per-kind copies of overhang, duration-family and range formatting into the shared layer"
context:
  - src/fitdocs/render/charts/kit/kinds/line.py
  - src/fitdocs/render/charts/kit/kinds/area.py
  - src/fitdocs/render/charts/kit/kinds/hbar.py
  - src/fitdocs/render/charts/kit/kinds/histogram.py
  - src/fitdocs/render/charts/kit/kinds/scatter.py
  - src/fitdocs/render/charts/kit/format.py
  - src/fitdocs/render/charts/kit/scales.py
blocked_by: []
---

## What
Cross-kind rulings were implemented per kind: `_overhangs` exists 4× (line, area, hbar, histogram) plus a scatter variant; the duration-family check ~7× (plus private `format._is_duration`, `scales._duration_family`); range-extreme formatting 6 variants; scales keeps a private `_hms` though `format_duration(hours=True)` now exists.

## Why it matters
Each copy is pinned by its own tests today, but chart-catalog will add more copies and a future ruling must be re-applied N times.

## Evidence
chart-kit validate-impl integration review (2026-10-12) E2 file:line list; tests/render/charts/kit/test_describe_ranges.py pins the behaviour cross-kind.

- chart-catalog (2026-10-12, c52da2d) adds more copies: `_overhangs` in calendar_heatmap, mean_max, dual_axis, band, small_multiples; duration-family checks in stacked_100 (`_y_hours`), heatmap, mean_max, small_multiples (`_in_one_form`); `_exact` (10-significant-digit value_order fallback) duplicated in band and box; cells copies frame.legend's offsets (rank forbids importing frame; pinned by a parity test in test_cells.py).

## How to pick it up
Add public helpers (e.g. `layout.x_label_overhangs`, `units`/`format.is_duration_family`, `frame.range_text`) and migrate the kinds; goldens must stay byte-identical (test_describe_ranges and every kind golden are the safety net). Do it before chart-catalog implementation if possible.
