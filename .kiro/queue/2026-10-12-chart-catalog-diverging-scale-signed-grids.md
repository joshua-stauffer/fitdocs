---
id: 2026-10-12-chart-catalog-diverging-scale-signed-grids
title: Grid kinds (calendar-heatmap, heatmap) refuse signed values; a diverging scale for form, TSB or deltas was deferred
status: open
importance: low
importance_why: Form (TSB) and week-over-week deltas are natural calendar heatmaps for this athlete. Today the kinds refuse them, so an agent falls back to a line chart. That is safe, never wrong, but less useful.
effort: M
kind: gap
area: chart-catalog, src/fitdocs/render/charts/kit/cells.py, src/fitdocs/render/palette.py
created: 2026-10-12
surfaced_by: /kiro-spec-batch phase 11 (chart-catalog writer, research.md follow-ons)
pinned_at: e340d15
resume_command: "do: after chart-catalog lands, design a diverging cell scale for the grid kinds (zero-centred, both signs distinguishable without colour alone, absent still a cross, zero still an outline) that meets chart-kit's 3:1-on-four-backgrounds ink rule; spec it as a chart-catalog amendment or a small new spec"
context:
  - .kiro/specs/chart-catalog/design.md
  - .kiro/specs/chart-catalog/research.md
  - .kiro/specs/chart-kit/design.md
blocked_by:
  - chart-catalog
---

## What
chart-catalog's grid kinds draw magnitude by cell area, with colour as a second
carrier, from a five-step sequential ramp (`SEQUENTIAL_RAMP`). Signed values are
refused with a validation problem, and a diverging scale is explicitly deferred.
The writer's research found that chart-kit's ink rule (base inks at least 3:1 on
`#ffffff`, `#1e1e1e`, `#0d1117` and `#1e2129`) leaves no lightness-monotone ramp
with good step separation. Adjacent steps differ by only about 0.05 OKLab, and
by about 0.037 under tritanopia. A two-sided ramp is harder still.

## Why it matters
Signed daily series are common in this corpus's analytics: form (TSB), and
deltas against a baseline. Today a dashboard author must use `line` or `bar` for
them. Nothing is drawn wrong, because the refusal is explicit, but the calendar
view the athlete would want is unavailable.

## Evidence
- `.kiro/specs/chart-catalog/research.md`: the ramp-separation analysis and the follow-on list (diverging scale for signed calendars).
- `.kiro/specs/chart-catalog/design.md:38` (Non-Goals): "A diverging (signed) colour scale; a signed `calendar-heatmap` is refused".
- `.kiro/specs/chart-catalog/research.md:316`: the option table row "Diverging scale for signed values … Deferred (follow-on)".
- chart-catalog final report (2026-10-12): "Signed values on grids are refused; a diverging scale is deferred."

## How to pick it up
1. Read chart-catalog's design (grid kinds, cells) and research.md's ramp analysis, and chart-kit's design § Theme.
2. Prototype a zero-centred encoding in a scratch script. One candidate: area for magnitude plus a sign glyph or hatch, so sign never depends on hue alone. Check it against the four reference backgrounds and the CVD simulations already in chart-kit's palette tests.
3. Decide with the maintainer whether this is a chart-catalog amendment or a new kind (e.g. `diverging-calendar`).

## Open questions
- Is sign-by-glyph acceptable visually, or does the maintainer prefer relaxing the 3:1 rule for the grid fill only?
