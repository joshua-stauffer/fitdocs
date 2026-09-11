---
id: 2026-09-12-calendar-chart-degenerate-domains-and-band-semantics
title: render.charts.calendar has unpinned behaviour for one-day series, zero-range y, band-vs-break overlap, and out-of-range marker index
status: open
importance: low
importance_why: A one-day archive or a flat series is a legal input the chart renders something for; today what it renders is whatever the arithmetic happens to produce, and a marker index past the series end is a silent no-op rather than a contract violation.
effort: S
kind: gap
area: load-history, src/fitdocs/render/charts/calendar.py, tests/render/charts/test_calendar.py
created: 2026-09-12
surfaced_by: /kiro-impl load-history 4.1 (reviewer rounds 1-2, FOLLOW_UPS)
pinned_at: 8cd0062
resume_command: "do: pin render_calendar_chart for days==1 (band width, x-scale), a constant series (y domain must not collapse to zero height), a suppressed band that overlaps a series break, and a CalendarMarker.day_index outside [0, days) -- decide raise vs clamp and state it in the docstring"
context:
  - src/fitdocs/render/charts/calendar.py
  - tests/render/charts/test_calendar.py
  - tests/render/charts/golden/
blocked_by: []
---

## What
Four edge cases the 4.1 reviewer probed and found undefined-but-passing:
- `days == 1`: the x-scale divides by `days - 1`; a band spans zero width.
- constant series: y-domain min == max; the path collapses to the axis.
- a suppressed band overlapping a `None` gap in the series: two visual
  encodings of "no data" stack with no stated precedence.
- `CalendarMarker.day_index >= days`: silently dropped; the spec precondition
  (design.md, CalendarChartSpec) says callers must not pass it, but the
  function does not enforce it.

## Evidence
4.1 review rounds 1-2 `FOLLOW_UPS`; each probe reproduced by calling
`render_calendar_chart` with the input named.

## How to pick it up
Decide each (raise on the precondition; degenerate domains get an explicit
padding rule); pin four tests; regenerate the golden only if its input is
affected.
