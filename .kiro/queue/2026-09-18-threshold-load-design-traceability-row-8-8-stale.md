---
id: 2026-09-18-threshold-load-design-traceability-row-8-8-stale
title: threshold-load's own design.md traceability row for Req 8.8 still cites flags = () as that requirement's implementation, now superseded
status: open
importance: low
importance_why: Documentation-only drift in a merged spec's own design.md; does not affect shipped behavior, but a reader of threshold-load's design would learn something false about the current shape of build_result.
effort: S
kind: inconsistency
area: threshold-load, .kiro/specs/threshold-load/design.md
created: 2026-09-18
surfaced_by: /kiro-impl activity-qa-flags task 3.2 review, re-confirmed at feature-level validation
pinned_at: d26b682
resume_command: "do: update .kiro/specs/threshold-load/design.md's Req 8.8 traceability row (around line 530) to reflect that build_result now takes flags: tuple[QualityFlag, ...] = (), supplied by activity-qa-flags task 3.2, rather than the literal always-empty flags = ()"
context:
  - .kiro/specs/threshold-load/design.md
  - src/fitdocs/load/threshold/calculator.py
---

## What

`.kiro/specs/threshold-load/design.md:530` records `flags = ()` as Req
8.8's ("no flags of its own") implementation. `activity-qa-flags` task 3.2
added a keyword-only `flags: tuple[QualityFlag, ...] = ()` parameter to
`build_result` and wired `ThresholdCalculator.compute` to populate it with
real verdicts from `qa.evaluate_flags` on every successful selection --
`threshold-load`'s own design row now describes a stale, superseded state.

## Why it matters

Requirement 8.8 itself is still satisfied -- `threshold-load` originates no
flags of its own; `activity-qa-flags` supplies them from outside, through the
additive parameter `threshold-load`'s own pre-task docstring anticipated
("adding one later is an additive signature change"). The row just no
longer describes what ships.

## Evidence

Verified directly at `d26b682`:
- `.kiro/specs/threshold-load/design.md:530`: `| 8.8 | No flags of its own,
  no placeholders | ResultAssembly | `flags = ()` | — |`
- `src/fitdocs/load/threshold/calculator.py:617`: `flags=flags` (the
  parameter, not a literal empty tuple)

## How to pick it up

1. Open `.kiro/specs/threshold-load/design.md`, find the Req 8.8
   traceability row (`grep -n "8.8"`).
2. Update the Interface column to name the `flags` parameter and its
   default, and add a note that `activity-qa-flags` task 3.2 supplies the
   real values through it.

Done looks like: the row accurately describes the shipped `build_result`
signature.

## Open questions

None.
