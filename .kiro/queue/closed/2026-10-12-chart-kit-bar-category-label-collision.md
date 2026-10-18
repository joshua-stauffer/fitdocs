---
id: 2026-10-12-chart-kit-bar-category-label-collision
title: Bar: distinct categories that format alike share one band and hide each other
status: done
importance: medium
importance_why: A row's mark can vanish without a note (Req 9.3 / 11.2 spirit).
effort: S
kind: defect
area: chart-kit kinds/bar, cartesian.category_order
created: 2026-10-12
surfaced_by: /kiro-impl chart-kit (reviews + /kiro-validate-impl)
pinned_at: d03e85e
resume_command: "/kiro-impl chart-kit [queue: .kiro/queue/2026-10-12-chart-kit-bar-category-label-collision.md] Bar: distinct categories that format alike share one band and hide each other"
context:
  - src/fitdocs/render/charts/kit/kinds/bar.py
  - src/fitdocs/render/charts/kit/cartesian.py
blocked_by: []
---

## What
bar keys bands by the formatted label, while `cartesian.category_order` and `duplicate_problem` compare raw values, so two different raw categories whose cleaned labels are equal ("a\tb" vs "a b", or a literal "—" vs absent) map to one band; one bar draws over the other with no refusal or note. Related: a tiny non-zero value (0.001 on a 0–50 axis) renders a `height="0"` rect that looks absent.

## Why it matters
Silent data loss in a chart is exactly what the absent/undrawn rules exist to prevent.

## Evidence
Probe: rows x='a\tb' (1.0) and x='a b' (5.0) both render at x=509.76; band 0 empty. bar.py:87-91, cartesian.py:62,134 (at d03e85e).

## How to pick it up
Pick one identity: either key bands and duplicates on the cleaned label (refuse a duplicate when labels collide) or keep raw identity and disambiguate labels. Add a test for each collision case; decide whether sub-pixel non-zero bars get a minimum visible height.

## Resolution (2026-10-18)

Fixed on main at 227729d (chore/q-chart-labels; two Opus review rounds, final APPROVED; full suite green;
branch CI green). New `cartesian.category_bands(bound, channel)` keys bands on the raw category value;
bar, stacked-100 and box use it (their per-kind label-keyed `_bands` copies are deleted), and so does
small-multiples for its panels (the reviewer found it mixed and duplicated colliding facets' rows). Two
categories that print alike now get two bands/panels with equal labels (no refusal), matching
`category_order`'s existing raw-value identity. Every kind's collision case is mutation-pinned.
The sub-pixel non-zero bar question this item also raised is split out to
.kiro/queue/2026-10-18-sub-pixel-nonzero-bar-invisible.md.
