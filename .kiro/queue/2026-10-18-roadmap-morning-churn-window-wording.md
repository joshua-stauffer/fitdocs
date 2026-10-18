---
id: 2026-10-18-roadmap-morning-churn-window-wording
title: Roadmap churn summary omits prior-day inputs to morning baseline windows
status: open
importance: low
importance_why: An older discovery summary understates refresh influence while the approved spec and current implementation are correct.
effort: S
kind: docs
area: workout-wellness, .kiro/steering/roadmap.md
created: 2026-10-18
surfaced_by: /kiro-impl workout-wellness task 5.1 full roadmap read
pinned_at: cc1f6b4
resume_command: "do: align the roadmap morning-of churn sentence with shared rolling and prior-60-day baseline influence, retaining byte-difference write semantics [queue: .kiro/queue/2026-10-18-roadmap-morning-churn-window-wording.md]"
context:
  - .kiro/steering/roadmap.md
  - .kiro/specs/workout-wellness/requirements.md
  - .kiro/specs/workout-wellness/design.md
  - tests/morning/test_block.py
  - tests/morning/test_engine.py
blocked_by: []
---

## What

The Phase 12 discovery summary at `.kiro/steering/roadmap.md:3079` says
morning-of re-renders happen only when a page's own day's inputs change.
A changed earlier wellness day can also change a displayed rolling mean,
normal range or baseline mean on a later page. The approved requirement
and implementation already account for this influence.

## Why it matters

Someone reading the older roadmap summary can infer an incorrect invalidation
rule. The feature's final task explicitly changes only two roadmap completion
rows, so this separate wording correction was recorded rather than silently
expanding that boundary.

## Evidence

At `cc1f6b4`, the controller directly read the sentence:

```text
morning-of re-renders, which happen only when a page's own day's inputs
change;
```

Workout-wellness requirements 7.2 and 7.4 say to compare the full current block
and preserve pages before changed day X or more than 60 days after X.
The shared figure definitions also use seven days ending on the page date
and the 60 days before it. Existing accepted tests
`test_a_day_change_affects_x_and_x_plus_60_but_neither_neighbor` and
`test_origin_change_updates_endpoints_and_preserves_nonempty_outside_days`
pin these boundaries. This is a directly verified prose mismatch, not a new
runtime failure or an unverified claim of fresh behavioral execution.

The root queue frontmatters and relevant bodies plus roadmap open rows were
checked; no existing item or unchecked task owns this sentence correction.

## How to pick it up

Read the summary and approved figure/window definitions. Rewrite only the
churn sentence to refer to changed contributing inputs or changed printed
block content, preserving sparse writes and the existing derived-HR bullet.
Read the surrounding paragraph for consistency and run `git diff --check`.
No runtime change or duplicate baseline computation is needed.
