---
id: 2026-09-30-hr-max-all-none-reads-as-zero-unpinned
title: No test catches heart-rate max reporting 0 for an all-None heart-rate channel
status: open
importance: medium
importance_why: After running-dynamics made 0 bpm samples None, an all-placeholder heart-rate stream is exactly the all-None case; a regression would print a fabricated max HR of 0.
effort: S
kind: gap
area: fit-metrics, src/fitdocs/metrics/aggregates.py, tests/metrics/test_aggregates.py
created: 2026-09-30
surfaced_by: /kiro-impl running-dynamics
pinned_at: 8b07b9f
resume_command: "do: add a metrics test that an activity with no session max HR and an all-None heart-rate channel yields max_heart_rate_bpm None"
context:
  - src/fitdocs/metrics/aggregates.py
  - tests/metrics/test_aggregates.py
  - .kiro/specs/fit-metrics/requirements.md
blocked_by: []
---

## What
`max_heart_rate_bpm` (src/fitdocs/metrics/aggregates.py:~212) falls back to `_max_non_none(heart_rate_bpm)` when the session has no max. A mutation feeding `v or int()` into `_max_non_none` turns an all-None channel into 0, and no test notices.

## Why it matters
The hard rule is that absent data is None, never a fabricated 0. After running-dynamics task 2.3, a file whose every HR sample is a 0 placeholder has an all-None channel. If the session also lacks max HR, a regression here would put `Max HR 0` on the page.

## Evidence
Reported by the running-dynamics 2.3 reviewer subagent: the mutation `lambda: _max_non_none([v or int() for v in activity.samples.heart_rate_bpm])` left the full suite green (5769 passed at that branch state). Not re-run in this session.

## How to pick it up
1. Re-run the mutation above through `uv run pytest` to confirm it survives on main.
2. Add a test to tests/metrics/test_aggregates.py: an Activity with `summary.max_heart_rate_bpm=None` and `heart_rate_bpm=(None, None, None)` must give `max_heart_rate_bpm(...) is None`. Do the same for the average, if it is also unpinned.
3. Done when the mutation reds the new test.
