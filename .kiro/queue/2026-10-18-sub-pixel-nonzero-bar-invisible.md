---
id: 2026-10-18-sub-pixel-nonzero-bar-invisible
title: A tiny non-zero bar renders with height 0, indistinguishable from a zero value
status: open
importance: low
importance_why: see body
effort: S
kind: design-gap
area: chart-kit kinds/bar, marks.bar
created: 2026-10-18
surfaced_by: independent review of chore/q-chart-labels (queue-prerelease session)
pinned_at: 227729d
resume_command: "do: decide whether sub-pixel non-zero bars get a minimum visible height (like the zero-stub's 2 px) and implement with a test [queue: .kiro/queue/2026-10-18-sub-pixel-nonzero-bar-invisible.md]"
context:
  - src/fitdocs/render/charts/kit/kinds/bar.py
  - .kiro/queue/closed/2026-10-12-chart-kit-bar-category-label-collision.md
blocked_by: []
---

Split from the bar-collision item: a value such as 0.001 on a scale of hundreds renders `height="0"`,
so a real non-zero measurement looks like zero (or absent). Product choice: a minimum visible height for
non-zero bars, or leave as is.
