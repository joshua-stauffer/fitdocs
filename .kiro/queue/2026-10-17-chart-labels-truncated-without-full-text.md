---
id: 2026-10-17-chart-labels-truncated-without-full-text
title: Small-multiples panel titles and long legend labels are cut with an ellipsis and the full text appears nowhere in the SVG
status: open
importance: low
importance_why: Two panels of one metric from different sources become indistinguishable, and screen readers lose the label; cosmetic otherwise.
effort: S
kind: gap
area: chart-kit, recovery, src/fitdocs/render/charts/kit/layout.py, src/fitdocs/recovery/charts.py
created: 2026-10-17
surfaced_by: maintainer-requested Phase 12 re-validation (recovery reviewer finding 4; reproduced by the parent on a real-data recovery page)
pinned_at: 160b007
resume_command: "do: keep truncated chart-kit labels readable: carry the full text of every truncated panel title and legend label in the SVG (per-text <title> or the chart <desc>), and/or shorten recovery's panel label format [queue: .kiro/queue/2026-10-17-chart-labels-truncated-without-full-text.md]"
context:
  - src/fitdocs/render/charts/kit/layout.py
  - src/fitdocs/render/charts/kit/format.py
  - .kiro/specs/chart-kit/design.md
  - .kiro/specs/recovery/design.md
blocked_by: []
---

## What
chart-kit truncates text to fit (`layout.py:95-96`, ellipsis `…`). On a recovery
page rendered from real data at 160b007, the SVGs contained these truncated
strings:
- `recovery-other.svg` panel titles: `SpO2 (%) · intervals-…`,
  `Weight (kg) · interva…`, `VO2max (mL/kg/min) · …`;
- `recovery-hrv-sdnn.svg` legend: `normal range low to normal ra…`.

The panel title is `<label> (<unit>) · <source>`, so the source, which is
the part that tells two panels of one metric apart, is the part cut off.
The chart `<desc>` names the facet channel but not the panel names, so the
full label is nowhere in the file.

## Why it matters
Recovery Req 8.1 shows one panel per metric **and source**. With two
sources of one metric the panels can't be told apart, and accessible text
loses the identity too. Dashboards over `wellness_daily` will hit the same
truncation.

## Evidence
`grep -o "<text[^>]*>[^<]*…</text>"` over the two SVGs listed the four
strings above. `<desc>` read "Small-multiples chart: Other signals. x: day;
y: value; facet: panel. 360 rows. ...", with no panel names. The recovery
reviewer saw the same on a synthetic root ("Body battery (highest…").

## How to pick it up
1. In chart-kit, when a text node is truncated, emit the full string as a
   child `<title>` of that `<text>`, or list facet values and series names
   in `<desc>`. Pin the change with a golden.
2. In recovery, consider a shorter panel label (for example the source on
   its own line, or the unit dropped from the title), so the source survives
   at 720 px.
3. Re-check the budgets in chart-catalog's typical/live pins.
