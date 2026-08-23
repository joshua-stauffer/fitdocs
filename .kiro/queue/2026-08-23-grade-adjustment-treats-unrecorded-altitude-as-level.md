---
id: 2026-08-23-grade-adjustment-treats-unrecorded-altitude-as-level
title: Grade adjustment treats unrecorded altitude as measured level ground
status: open
importance: medium
importance_why: An interval with no terrain data is counted as level inside a result whose applied flag claims the model was applied, with nothing on the result saying so — a fabricated default where the repo rule requires None.
effort: S
kind: gap
area: load-channels, src/fitdocs/load/channels/grade.py
created: 2026-08-23
surfaced_by: /kiro-impl load-channels task 2.2 adversarial review
pinned_at: e48ca61
resume_command: "/kiro-spec-design load-channels [queue: .kiro/queue/2026-08-23-grade-adjustment-treats-unrecorded-altitude-as-level.md] Rule how GradeAdjustment should report intervals whose altitude is unrecorded"
context:
  - src/fitdocs/load/channels/grade.py
  - .kiro/specs/load-channels/design.md
  - .kiro/specs/load-channels/requirements.md
  - .kiro/steering/tech.md
blocked_by: []
---

## What

`GradeAdjustment.equivalent_distance` treats an interval whose distance delta
is valid but whose smoothed altitude is undefined at either endpoint as level
ground — it contributes its raw distance to `equivalent_distance_m` with a
ratio of exactly 1.0.

Requirement 7.5 licenses "treat as level" for exactly two cases: a distance
delta that is not positive, and one below the minimum meaningful displacement.
An unrecorded altitude is neither. The result carries `applied=True`, no note,
and no counter distinguishing these intervals from ones where the model
genuinely resolved a gradient of zero.

The task 2.2 implementer disclosed this in its own CONCERNS as an
extrapolation beyond what `design.md` specifies, rather than presenting it as
sanctioned. That judgement is correct and is why this is a ruling rather than a
defect report.

## Why it matters

`.kiro/steering/tech.md` makes absent data `None`, never a fabricated `0` or
default. "This interval was flat" and "we do not know whether this interval was
flat" are different facts, and the current result reports the second as the
first. A route with partial altitude coverage yields a grade-equivalent
distance that reads as fully modelled.

The reasonable fixes each change something a task may not change alone: adding
a counter or note widens a result shape `design.md` specifies, and returning
`None` for the whole activity would discard usable data for one missing sample.

## Evidence

At `e48ca61`, `src/fitdocs/load/channels/grade.py:220` — the guard is
`or a0 is None or a1 is None`, and deleting it left the full suite green
(2504 passed, 5 skipped): no fixture reached the branch at all. Found by the
reviewer's own mutation, not by the implementer's sweep.

Task 2.2's remediation adds a test that reaches the branch and an accurate
docstring statement, so the behaviour is now observable and honestly described
— but the underlying question of what the result *should* report is
deliberately left open here.

## How to pick it up

1. Read `#### GradeAdjustment` in `.kiro/specs/load-channels/design.md`,
   specifically the result shape and its invariants, and Req 7.5 in
   `requirements.md`.
2. Read `src/fitdocs/load/channels/grade.py`'s `equivalent_distance` and the
   test that now covers the `None`-altitude branch.
3. Decide the ruling below and amend `design.md` before changing code.

Done looks like: `design.md` states what an unrecorded-altitude interval
contributes and how the result reports it, and the code and its test match.

## Open questions

- Should the result distinguish these intervals — a counter in the same shape
  as `clamped_intervals`, a note, or a separate flag — or is "treated as level"
  an acceptable silent behaviour to record as a deliberate DIVERGENCE?
- Should `applied` stay `True` when some intervals had no terrain to model?
- Is there a coverage threshold below which grade adjustment should decline
  entirely and return the raw distance with `applied=False`, consistent with
  how the sufficiency gate declines elsewhere in this layer?
