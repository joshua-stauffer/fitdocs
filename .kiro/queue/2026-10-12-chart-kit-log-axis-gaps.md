---
id: 2026-10-12-chart-kit-log-axis-gaps
title: Log axes and time-axis nice: design gaps
status: open
importance: medium
importance_why: A log axis can render with no tick labels at all.
effort: S
kind: design-gap
area: chart-kit design § Scales / kit/scales.py
created: 2026-10-12
surfaced_by: /kiro-impl chart-kit (reviews + /kiro-validate-impl)
pinned_at: d03e85e
resume_command: "/kiro-impl chart-kit [queue: .kiro/queue/2026-10-12-chart-kit-log-axis-gaps.md] Log axes and time-axis nice: design gaps"
context:
  - src/fitdocs/render/charts/kit/scales.py
  - src/fitdocs/render/charts/kit/ticks.py
  - .kiro/specs/chart-kit/design.md
blocked_by: []
---

## What
(1) A log axis with nice=False (line/area x) can draw no ticks (x 6..9 → no labels). (2) log_ticks thinning can leave the niced top edge untick'd (log_ticks(5,7200,6,duration=True) → last tick 3600 under a 7200 domain). (3) scatter's nice=True on a date x keeps the exact extent (no calendar enclosing domain). (4) line `y_zero` with `y_scale: log` silently ignores include_zero instead of an option conflict.

## Why it matters
A tickless axis fails Req 6.2/7.1.

## Evidence
5.1 review probe (x log, 6..9); 2.3 review (log_ticks edge); 4.1 review (scatter date nice, y_zero+log).

- chart-catalog (2026-10-12, c52da2d): (5) a sub-second log-duration domain labels every tick `0:00` (rows 0.1 s and 0.4 s → three `0:00` x ticks) because `format_duration` rounds to whole seconds — any kind with a log duration axis inherits it (`scales.numeric_scale`, `ticks._log_duration_ladder`). mean-max keeps `numeric_scale`'s own ticks when no landmark is in the domain, so it shows this; its tests deliberately do not pin the broken labels. Reported by the 2.6 reviewer, reproduced in review scratch.

## How to pick it up
Rule a minimum of 2 log ticks (fall back to 1-2-5 mantissas inside the exact extent), decide edge-tick retention, add an option_conflict for y_zero+log; amend design § Scales.
