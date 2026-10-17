---
id: 2026-10-17-recovery-sleep-origins-total-only
title: The recovery Sleep section names origins from total-sleep values only, not from stage values
status: open
importance: low
importance_why: Only matters if a source records a stage with a different origin than its total, which no shipped format does today.
effort: S
kind: gap
area: recovery, src/fitdocs/recovery/page.py, src/fitdocs/recovery/view.py
created: 2026-10-17
surfaced_by: Phase 12 follow-ups, recovery stream review (non-blocking)
pinned_at: 5cb2931
resume_command: "do: decide whether the Sleep section's Sources shown line should union origins across the stage metrics of the shown night's source, and either implement it or record in recovery design that totals govern [queue: .kiro/queue/2026-10-17-recovery-sleep-origins-total-only.md]"
context:
  - src/fitdocs/recovery/page.py
  - src/fitdocs/recovery/view.py
  - .kiro/specs/recovery/design.md
blocked_by: []
---

## What
The Sleep section's `Sources shown:` line comes from `SleepView.total.sources`,
the `sleep_s` signal. Origins recorded only on stage values (deep, light, REM,
awake) from the same source are not named. The recovery design's Amendment 1
note sanctions `SleepView.total`, so this is a recorded limitation.

## Why it matters
Req 5.6 asks the page to name the origins a shown source's values record. All
three shipped formats give a night's stages the same origin as its total, so
this is latent.

## Evidence
`page.py` renders `_source_lines(view.sleep.total, ...)` at 5cb2931. The
recovery reviewer recorded it as non-blocking finding 3.

## How to pick it up
Either union stage-metric origins into the line, or add one design sentence
saying a night's total governs, then add the matching test.
