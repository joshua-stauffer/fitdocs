---
id: 2026-08-27-not-applicable-has-no-readers
title: ResolvedAnchors.not_applicable is produced and never consumed, so Req 9.5's distinguishing reason is unrealized
status: open
importance: medium
importance_why: The field exists to break the tie between "never measured" and "measured after this activity"; nothing reads it, so no user-visible string distinguishes them.
effort: S
kind: requirement-gap
area: threshold-load, src/fitdocs/load/threshold/calculator.py, src/fitdocs/load/channels
created: 2026-08-27
surfaced_by: /kiro-validate-impl threshold-load
pinned_at: 3e14ab9
resume_command: "/kiro-impl threshold-load [queue: .kiro/queue/2026-08-27-not-applicable-has-no-readers.md] Consume not_applicable and emit a distinguishing reason"
context:
  - src/fitdocs/load/threshold/anchors.py
  - src/fitdocs/load/threshold/calculator.py
  - src/fitdocs/load/channels/power.py
  - tests/load/threshold/test_outcomes.py
blocked_by: []
---

## What

Req 9.5 asks for "a reason **distinguishing** that case" — a benchmark on file
but dated after the activity — from one never provided. An AST scan of
`calculator.py` finds exactly one attribute access, `anchors.not_on_file`
(line 697), and **zero** reads of `ResolvedAnchors.not_applicable` outside
docstrings. Both channels' `NO_BENCHMARK` detail is an unparameterised module
constant (`power.py:79`, `pace.py:130`) reading "no ... benchmark was
supplied, or its value is not positive" — affirmatively **false** for a
benchmark that was supplied, just later than the activity.

`anchors.py:32-35` states the field's purpose: "The third is what lets a
caller report 'measured after this activity' rather than 'never measured'."
No caller does.

## Why it matters

Today only the outcome **variant** distinguishes the two (`NotComputed` vs
`MissingInputs`), and that half is correctly pinned. The **text** the athlete
reads is identical and, in the not-applicable case, wrong.

## Evidence

`3e14ab9`. `tests/load/threshold/test_outcomes.py` asserts the two reasons are
**byte-identical**, deliberately and with a docstring saying why — it records
the gap honestly rather than pretending. **Any fix must revisit that
assertion; it will go red.**

## How to pick it up

Read `anchors.py:100-150` (the three absence states), `calculator.py:690-750`
(`_missing_inputs` and `_not_computed_reason`), and decide where the
distinction is rendered — the calculator's reason, or a parameterised channel
detail. Closely related to
`2026-08-27-borrowing-note-asserts-an-unestablished-cause`, which needs the
same information one layer up; consider doing both together.
