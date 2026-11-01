---
id: 2026-11-01-render-avg-hr-rounding-coupling
title: "The contract reader and the renderer must agree on avg_hr rounding, and nothing pins the renderer's side"
status: open
importance: low
importance_why: Switching the renderer to half-up rounding leaves tests green while the reader and renderer silently disagree.
effort: S
kind: gap
area: src/fitdocs/render/frontmatter.py
created: 2026-11-01
surfaced_by: "/kiro-impl publish-core"
pinned_at: dd9fcaa1
resume_command: "do: pin the renderer's int(round(...)) of avg_hr in a test beside the contract reader's rounding [queue: .kiro/queue/2026-11-01-render-avg-hr-rounding-coupling.md]"
context:
  - src/fitdocs/render/frontmatter.py
  - src/fitdocs/contract.py
blocked_by: []
---

## What
The contract reader and the renderer must round `avg_hr` the same way.
Changing `src/fitdocs/render/frontmatter.py` (~148) to half-up rounding leaves
the suite green.

## Why it matters
A disagreement changes a value by one between what is rendered and what the
reader recovers.

## Evidence
`src/fitdocs/render/frontmatter.py:~148` uses `int(round(...))`; mutating it to
half-up passes all tests.

## How to pick it up
Add a test with a .5 average heart rate that pins the renderer's `int(round(...))`
result and asserts the reader returns the same value.
