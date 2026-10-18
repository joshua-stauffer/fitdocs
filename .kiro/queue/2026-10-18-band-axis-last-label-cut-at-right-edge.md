---
id: 2026-10-18-band-axis-last-label-cut-at-right-edge
title: Band x axes cut the last labelled band at the right canvas edge (the right-side counterpart of the first-label fix)
status: open
importance: medium
importance_why: see body
effort: S
kind: defect
area: chart-kit cartesian.band_x_axis / layout.plan_frame
created: 2026-10-18
surfaced_by: independent review of chore/q-chart-labels (queue-prerelease session)
pinned_at: 227729d
resume_command: "do: reserve the last band label's right overhang in cartesian.band_x_axis (mirror the left-edge reservation, chart-kit tasks.md 5.1-5.6 ruling (1) reserves both sides) with a discriminating test per band kind [queue: .kiro/queue/2026-10-18-band-axis-last-label-cut-at-right-edge.md]"
context:
  - src/fitdocs/render/charts/kit/cartesian.py
  - src/fitdocs/render/charts/kit/layout.py
  - .kiro/specs/chart-kit/design.md
blocked_by: []
---

Reviewer sweep (probes under the queue-prerelease scratchpad, not durable): with the left-edge fix,
1991 of 7920 weekly renders have a non-first label ending in `…`, e.g. bar 13 weeks @720 -> `2026-03-…`,
26 weeks @320 -> `2026-…`; stacked-100 shows 507 such renders both before and after the fix (pre-existing).
Band kinds pass x_label_overhang=0 so no right overhang is reserved.
