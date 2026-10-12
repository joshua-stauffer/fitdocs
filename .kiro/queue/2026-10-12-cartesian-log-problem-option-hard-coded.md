---
id: 2026-10-12-cartesian-log-problem-option-hard-coded
title: cartesian.log_problem hard-codes an `<channel>_scale` option and fix text
status: open
importance: low
importance_why: Only mean-max hits it today and works around it; a parameter removes the workaround.
effort: S
kind: inconsistency
area: chart-kit cartesian.py; chart-catalog mean-max
created: 2026-10-12
surfaced_by: /kiro-impl chart-catalog
pinned_at: c52da2d
resume_command: "/kiro-impl chart-kit [queue: .kiro/queue/2026-10-12-cartesian-log-problem-option-hard-coded.md] let log_problem take its option and fix"
context:
  - src/fitdocs/render/charts/kit/cartesian.py
  - src/fitdocs/render/charts/kit/kinds/mean_max.py
blocked_by: []
---

## What
`cartesian.log_problem` (cartesian.py ~173–194) always sets `option=f"{channel}_scale"` and a fix telling the user to set that option to linear. mean-max has a fixed log x and no `x_scale` option, so its `_check` post-edits the problem with `dataclasses.replace` (fix "Remove the rows with a duration at or below zero.", `option=None`).

## Why it matters
A kind with a fixed log axis publishes a problem naming an option it does not have unless it patches the problem after the fact.

## Evidence
On impl/chart-catalog c52da2d: `src/fitdocs/render/charts/kit/kinds/mean_max.py` `_check` uses `dataclasses.replace` on `log_problem`'s result; pinned by its zero-duration test (exact fix text, `option is None`).

## How to pick it up
Add optional `option`/`fix` parameters to `log_problem` (defaults unchanged), switch mean-max to pass them, delete the replace. Its existing test stays green.
