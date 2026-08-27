---
id: 2026-08-27-req-2-6-contradicted-by-shipped-supports
title: Req 2.6 says support comes from the sport label alone; the shipped supports() conjoins modality, and no task paired them
status: open
importance: medium
importance_why: A requirement and the code that implements it now disagree, and requirements.md was never amended to record the deliberate departure.
effort: S
kind: requirement-drift
area: threshold-load, .kiro/specs/threshold-load/requirements.md
created: 2026-08-27
surfaced_by: /kiro-validate-impl threshold-load
pinned_at: 3e14ab9
resume_command: "/kiro-impl threshold-load [queue: .kiro/queue/2026-08-27-req-2-6-contradicted-by-shipped-supports.md] Amend Req 2.6 to record the modality conjunct"
context:
  - .kiro/specs/threshold-load/requirements.md
  - src/fitdocs/load/threshold/calculator.py
blocked_by: []
---

## What

Req 2.6 states support is determined "from the activity's normalized sport
label alone". The shipped `supports` (`calculator.py:326-328`) conjoins
`activity.modality in DECLARED_MODALITIES`.

The conjunction is **correct and necessary** — it is what satisfies Req 2.2,
because `detect_sport("running", "strength_training")` yields
`(Sport.RUN, Modality.STRENGTH)` and a sport-only answer would widen past the
declared modalities on the forced/default arbitration path, violating the
"only ever narrow" obligation at `types.py:433-437`. It is argued at length in
the module docstring (`calculator.py:66-88`) and tested
(`test_calculator.py:341-353`).

But **Req 2.6 sits on task 2.1** (the tables) while the shipped decision lives
in **task 3.3**, so no task's `_Requirements:_` line ever paired 2.6 with
`supports`, and requirements.md was never amended.

## Why it matters

Requirements.md is the contract. A reader checking 2.6 against the code finds
a contradiction with no recorded resolution, and the argument for the
departure lives only in a module docstring.

## Evidence

`3e14ab9`. `grep -n "_Requirements" .kiro/specs/threshold-load/tasks.md` shows 2.6
on task 2.1 only.

## How to pick it up

Amend Req 2.6 to state the two-part answer and cite Req 2.2 as the reason,
in the style of Amendment 1's rulings. Pairs naturally with
`2026-08-27-threshold-load-design-doc-stale`, which records the same
departure on the design side — do both in one pass.
