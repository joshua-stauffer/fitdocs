---
id: 2026-09-17-cli-and-test-prose-nits-from-plan-resolution
title: Small prose/rendering nits in cli.py, its help output and two test docstrings
status: open
importance: low
importance_why: Cosmetic; batched so they are not forgotten.
effort: S
kind: docs
area: src/fitdocs/cli.py, tests/test_plan_e2e.py, tests/load/test_settings.py, src/fitdocs/plans/placement.py
created: 2026-09-17
surfaced_by: /kiro-impl plan-resolution (task 3.2, 3.4, validation reviews)
pinned_at: fbba78b
resume_command: "do: apply the six nits in .kiro/queue/2026-09-17-cli-and-test-prose-nits-from-plan-resolution.md as one trivial commit on main"
context:
  - src/fitdocs/cli.py
  - tests/test_plan_e2e.py
  - tests/load/test_settings.py
blocked_by: []
---

## What
1. `cli.py:5-6` "Four feature commands sit on top of the baseline" lists five bullets; eight `@app.command`s registered (pre-existing).
2. `fitdocs plan --help` renders the docstring's `[plans]`/`[history]`/`[load]` as empty backticks (rich markup eats the brackets); and `plan_command`'s first paragraph spans two lines so the help table wraps mid-sentence.
3. `tests/test_plan_e2e.py:300-316` two-dates docstring: "With the default (unresolved) resolution, `fitdocs plan` reads no clock" and "once that spec adds the precondition" are stale (it did; the tense is wrong) — the docstring says it was written knowing it would move.
4. `tests/load/test_settings.py` ~L1960-1968 "reddens this test's `fitdocs check` assertion as a sole failure" — the sibling licensed-callers guard also reds under that mutation since 94f2aea.
5. `cli._report_reconcile` prints `mesocycle {index}` from `enumerate(start=1)` rather than `mesocycle.number` (equal today; use the number).
6. A stem containing `|` is escaped by `page.link_text` and again by `block_page.py` `page.cell` (GFM unescapes correctly; cosmetic).
