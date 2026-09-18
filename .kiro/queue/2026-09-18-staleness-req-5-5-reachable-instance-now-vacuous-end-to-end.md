---
id: 2026-09-18-staleness-req-5-5-reachable-instance-now-vacuous-end-to-end
title: design.md's claim that Req 5.5's not-assessed instance is "reachable" is only true at the library level, not through the shipped calculator
status: open
importance: low
importance_why: The defensive branch is still correct and required for Requirement 1.10 (never raise for absent data), so nothing is broken -- this is a precision gap in the design's own claim, not a coverage gap.
effort: S
kind: inconsistency
area: activity-qa-flags, .kiro/specs/activity-qa-flags/design.md
created: 2026-09-18
surfaced_by: /kiro-impl activity-qa-flags feature-level validation pass (Finding G-2)
pinned_at: d26b682
resume_command: "do: add a qualifying sentence to design.md's StalenessSurfacing section (the 'Requirement 5.5, precisely' subsection) noting that the activity-date-absent instance, though reachable at the staleness.evaluate() function's own contract, is not reachable through the shipped ThresholdCalculator.compute() because compute() itself returns NotComputed before evaluating any flag when context.activity_date is None"
context:
  - .kiro/specs/activity-qa-flags/design.md
  - src/fitdocs/load/threshold/calculator.py
  - src/fitdocs/load/qa/staleness.py
---

## What

`design.md`'s StalenessSurfacing section ("Requirement 5.5, precisely")
argues the "computed without an anchoring benchmark carrying a measurement
date" instance of Req 5.5 has exactly one *reachable* case: an activity with
no calendar date. That claim is accurate for `staleness.evaluate()` as a
standalone function -- but at the feature level, through the shipped
calculator, that case never actually reaches `evaluate_flags` at all:
`ThresholdCalculator.compute()` (`calculator.py:406`) returns `NotComputed`
whenever `context.activity_date is None`, before any channel is selected and
before `evaluate_flags` is ever called.

## Why it matters

Nothing is broken -- the defensive not-assessed branch in `staleness.py` is
still exactly right, both as a library-level guarantee (Requirement 1.10:
never raise for absent data) and as future-proofing against a different
caller. But the design's "one reachable instance" framing, read alongside
the actually-shipped calculator, overstates what's exercised end to end
today; a reader tracing the claim through the real call chain would find it
unreachable, not merely rare.

## Evidence

Verified at `d26b682`:
- `src/fitdocs/load/threshold/calculator.py:400-406`: `if
  context.activity_date is None: return NotComputed(...)` -- precedes
  channel evaluation and selection entirely
- `src/fitdocs/load/qa/staleness.py`'s own `evaluate()`: `activity_date is
  None -> NOT_ASSESSED` -- correct as a function-level contract, just not
  reachable through the one caller that exists

## How to pick it up

1. Read design.md's "Requirement 5.5, precisely" subsection under
   StalenessSurfacing.
2. Add one sentence distinguishing the function-level guarantee (reachable,
   and required by Req 1.10) from the calculator-level reality (currently
   unreachable, because `compute()`'s own earlier date gate short-circuits
   first).

Done looks like: the design text no longer implies this path is exercised
end to end when it is not.

## Open questions

None.
