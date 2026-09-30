---
id: 2026-09-30-chart-axis-drop-rule-only-synthetic-pin
title: No golden chart covers a distance-less sample inside a distance-bearing run
status: open
importance: low
importance_why: The x-axis drop rule shared by the hero and dynamics charts is pinned only by one synthetic unit test.
effort: S
kind: gap
area: workout-docs, running-dynamics, src/fitdocs/render/sections.py
created: 2026-09-30
surfaced_by: /kiro-impl running-dynamics
pinned_at: 8b07b9f
resume_command: "do: add or extend a golden fixture whose distance channel has a gap so the hero/dynamics chart goldens exercise chart_axis's drop rule"
context:
  - src/fitdocs/render/sections.py
  - tests/render/test_sections.py
  - tests/render/test_golden_docs.py
  - tests/fixtures/builder.py
blocked_by: []
---

## What
`chart_axis` (src/fitdocs/render/sections.py) drops samples that lack distance when the run has distance at all. No golden fixture has such a gap, so the rule is pinned only by `tests/render/test_sections.py::test_chart_axis_is_km_and_drops_samples_lacking_distance`.

## Why it matters
Real GPS files have distance dropouts. A regression here would bend both the hero and the dynamics charts on real pages, and every golden would stay green.

## Evidence
Reported by the running-dynamics 3.1 reviewer subagent (not re-run here): renumbering `chart_axis`'s kept indices with `range` (mutation O4) left every golden green and redded only that synthetic test.

## How to pick it up
1. Pick or add a golden fixture with a short run of records without distance mid-run (the builder can omit distance on a few records).
2. Regenerate that fixture's goldens and confirm the charts show the gap.
3. Re-run the O4-style mutation and confirm a golden reds.
