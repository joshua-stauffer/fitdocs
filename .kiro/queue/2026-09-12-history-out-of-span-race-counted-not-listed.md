---
id: 2026-09-12-history-out-of-span-race-counted-not-listed
title: A race dated outside the series span is counted in criterion points but neither marked on the chart nor listed under Races
status: open
importance: medium
importance_why: The page contradicts itself on that edge -- "criterion points: 2, earliest 2024-01-02" above a Races list with one entry -- and the athlete cannot tell why.
effort: S
kind: inconsistency
area: load-history, src/fitdocs/history/engine.py, src/fitdocs/history/page.py
created: 2026-09-12
surfaced_by: /kiro-impl load-history 5.2 (reviewer rounds 1-4)
pinned_at: 8cd0062
resume_command: "do: decide whether an out-of-span race (a load-less race before the first or after the last contributing page) is listed under Races without a marker, or the criterion section says how many counted points lie outside the chart's span; pin it in tests/history/test_engine.py (test_a_race_page_dated_before_the_series_start_is_not_a_chart_marker currently pins the present behaviour) and amend design.md"
context:
  - src/fitdocs/history/engine.py
  - src/fitdocs/history/page.py
  - tests/history/test_engine.py
  - .kiro/specs/load-history/requirements.md
blocked_by: []
---

## What
`criterion_points(scan.pages)` counts every valid race/test with a time
(Req 6.1); the engine's marker filter keeps only races inside
`[series.start, series.end]` because the chart has no day index for them
(Req 1.8, CalendarChartSpec's in-range precondition). A load-less race dated
before the span is therefore counted and dated in the criterion section but
absent from the Races list and the chart.

## Evidence
`tests/history/test_engine.py::test_a_race_page_dated_before_the_series_start_is_not_a_chart_marker`
pins today's behaviour; the 5.2 round-1 review probe printed
`criterion_points=1, "Earliest 2024-01-02", Races: []`.

## How to pick it up
Read `engine.py`'s marker comprehension and `page.py`'s race list and
criterion section. Pick one presentation; pin it; amend the design.
