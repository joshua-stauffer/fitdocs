---
id: 2026-10-12-small-multiples-zero-area-panels
title: small-multiples: an explicit columns or height can leave panels with zero plot area
status: open
importance: medium
importance_why: Legal option values render charts whose panels are slivers with overlapping text; the fix is a spec decision (refuse vs cap).
effort: S
kind: spec-work
area: chart-catalog, src/fitdocs/render/charts/kit/kinds/small_multiples.py
created: 2026-10-12
surfaced_by: /kiro-impl chart-catalog
pinned_at: c52da2d
resume_command: "/kiro-spec-requirements chart-catalog [queue: .kiro/queue/2026-10-12-small-multiples-zero-area-panels.md] decide refuse-or-cap for small-multiples panels too small to draw"
context:
  - .kiro/specs/chart-catalog/requirements.md
  - .kiro/specs/chart-catalog/design.md
  - src/fitdocs/render/charts/kit/kinds/small_multiples.py
blocked_by: []
---

## What
Neither the design nor Req 10.6 sets a minimum panel size for an explicit `columns` or `height`. Width 320 with `columns` 4 or 6, and width 480 with `columns` 6, give a panel plot width of 0.0 px (every point on one x, 12 text overlaps at 320/6); 6 panels at `height` 200 give a 54 px panel and a 0 px panel plot height.

## Why it matters
A user (or agent) choosing a plausible option value gets an unreadable chart with no problem reported. Capping columns contradicts Req 10.6 ("that many columns"); refusing needs a new problem code or reuse of an existing one.

## Evidence
Reported by the 2.7 reviewer subagent (probe in its review scratch, since removed with /tmp); the controller ruled no code change in 2.7. Reproduce with `render_chart` on a small-multiples request at width 320, columns 6, and inspect panel widths.

## How to pick it up
Read Req 10.6 and design § SmallMultiples. Decide (maintainer) between refusing (e.g. `option_out_of_range` with a fix naming the minimum width per column / height per row) and capping. Amend requirements/design, then implement in `kinds/small_multiples.py` with a test at width 320 columns 6 and at height 200 with 6 panels. Related: chart-kit plot collapse in `2026-10-12-chart-kit-layout-edge-cases`.
