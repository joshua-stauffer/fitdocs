---
id: 2026-10-27-transparent-tile-pixels-now-composite-onto-white
title: Transparent tile pixels and out-of-range rows now render white instead of showing the viewer's background
status: open
importance: low
importance_why: Invisible with the default opaque OSM tiles; visible only with a transparent-tile [tiles] provider in a dark theme, and the design chose it deliberately — a requirement-vs-design wording gap, not a defect.
effort: S
kind: inconsistency
area: compact-chart-assets, route-maps, src/fitdocs/basemap.py
created: 2026-10-27
surfaced_by: /kiro-validate-impl compact-chart-assets
pinned_at: 10610817
resume_command: "do: decide whether Req 3.2 ('same imagery') should state the white backing explicitly, or whether the basemap should keep alpha (RGBA WebP) so transparent areas show the viewer background as before"
context:
  - src/fitdocs/basemap.py
  - .kiro/specs/compact-chart-assets/requirements.md
  - .kiro/specs/compact-chart-assets/design.md
  - .kiro/specs/route-maps/requirements.md
blocked_by: []
---

## What
Before this change, each tile was its own `<image>`, so transparent pixels and
any uncovered area showed whatever was behind the SVG. `fitdocs.basemap` now
composites every tile onto an opaque white RGB canvas
(src/fitdocs/basemap.py ~:118, :131; design § fitdocs.basemap "Composition":
"composited onto an opaque white canvas"). Requirement 3.2 says the basemap
shows the same imagery, and it does not mention the white backing.

## Why it matters
With a custom transparent-overlay tile server and a dark viewer theme, the map
area now shows as a white rectangle where it was dark before. The design made
this choice on purpose, so the open question is only whether the requirement
should say so.

## Evidence
Reported by the validation reviewer subagent. The design sentence is quoted
from design.md. I did not render a transparent-tile map in a dark theme.

## How to pick it up
Either amend compact-chart-assets Req 3.2 (and route-maps Amendment 2) to name
the white backing, or move the encode step to RGBA WebP and re-measure the
budgets and the cross-platform golden.
</content>
</invoke>
