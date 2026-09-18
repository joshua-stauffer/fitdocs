---
id: 2026-09-18-divergence-design-postconditions-omit-shipped-absent-heart-rate-gate
title: design.md's DivergenceAnalysis postconditions enumerate two not-assessed exits; the shipped module has three (the absent-heart-rate-outcome gate), so the design's gate list no longer matches the code's
status: open
importance: low
importance_why: The extra gate is defensive and justified by Req 1.10, unreachable from the shipped calculator, and correct; the only cost is a design section that a future reader will trust as the complete gate list and be wrong.
effort: S
kind: docs
area: activity-qa-flags, .kiro/specs/activity-qa-flags/design.md, src/fitdocs/load/qa/divergence.py
created: 2026-09-18
surfaced_by: /kiro-validate-impl activity-qa-flags (post-merge pass, 2026-09-18; design-alignment reviewer, confirmed by the controller)
pinned_at: e16acc3
resume_command: "do: in .kiro/specs/activity-qa-flags/design.md's DivergenceAnalysis 'Postconditions, in order' list (design.md:1065-1073) insert the absent-heart-rate-outcome exit between the HR-selected and HR-insufficient entries, stating it is unreachable through the shipped ThresholdCalculator (which evaluates all three channels unconditionally) and exists for Req 1.10 and the lazy-evaluation revalidation trigger, matching src/fitdocs/load/qa/divergence.py's own gate-order docstring"
context:
  - .kiro/specs/activity-qa-flags/design.md
  - src/fitdocs/load/qa/divergence.py
  - tests/load/qa/test_divergence.py
blocked_by: []
---

## What

`design.md`'s DivergenceAnalysis section lists the not-assessed exits as
(1) `selected is ChannelId.HEART_RATE` and (2) `outcomes[HEART_RATE]` is a
`ChannelInsufficient`, then the reached verdicts. The shipped
`src/fitdocs/load/qa/divergence.py:137-149` has a third exit between them:
`outcomes.get(ChannelId.HEART_RATE) is None` → `NOT_ASSESSED` with reason
"the heart-rate channel was not evaluated for this activity". The module
docstring (:27-35) and the function docstring's "Gate order, exactly"
list (:103-118) both document it and tie it to Req 1.10 ("shall not raise
for absent ... channel ... data") and to the design's own revalidation note
about `threshold-load` ever evaluating channels lazily.

## Why it matters

The design's postcondition list is what a reviewer or a future amendment
reads as the complete decision table for this check. It is now one row
short. The 2026-09-18 validation pass had to reconcile code and design by
reading the module's docstring; the next pass should not have to.

## Evidence

- `sed -n '137,149p' src/fitdocs/load/qa/divergence.py` — the gate.
- `sed -n '952,1100p' .kiro/specs/activity-qa-flags/design.md | grep -n -i "postcondition\|NOT_ASSESSED"` — two enumerated not-assessed
  postconditions (HR selected; HR insufficient).
- `tests/load/qa/test_divergence.py` covers the absent-HR path (grep
  `not evaluated for this activity`).

## How to pick it up

1. Read `divergence.py:95-120` (the gate-order docstring) — that is the
   authoritative order.
2. Edit the design's postcondition list to match, one inserted entry; do
   not touch code or tests.
3. Also read FlagAssembly's precondition at design.md:1352 ("`outcomes`
   holds ...") and decide whether it should note that DivergenceAnalysis
   tolerates an absent heart-rate entry even though the assembly's caller
   never omits one.
4. Done means the design's list and the docstring's list have the same
   entries in the same order.
