---
id: 2026-07-26-sample-aggregate-postcondition-unpinned
title: Req 9.2's sample-aggregate obligation lives in one docstring nothing pins
status: done
importance: medium
importance_why: Four sibling specs are about to implement calculators against a postcondition that can be deleted silently.
effort: S
kind: gap
area: training-load, src/fitdocs/load/types.py, docs/contributing-calculators.md
created: 2026-07-26
surfaced_by: /kiro-validate-impl training-load
pinned_at: 3121bb6
resume_command: "/kiro-impl training-load [queue: .kiro/queue/2026-07-26-sample-aggregate-postcondition-unpinned.md] Pin Req 9.2's sample-aggregate obligation textually or move it into the contributor guide"
context:
  - .kiro/specs/training-load/requirements.md
  - src/fitdocs/load/types.py
  - docs/contributing-calculators.md
  - tests/test_contributing_calculators_doc.py
blocked_by: []
---

## What
Requirement 9.2 requires a value derived from a recorded sample stream to be an aggregate over the samples *actually recorded*, never treating missing samples as zeros. By its own text it is a stated-not-enforced contract obligation, so a docstring is the right implementation -- but nothing pins the docstring, and it is absent from the contributor guide that calculator authors actually read.

## Why it matters
Deleting the paragraph leaves all 1852 tests green, and the obligation silently stops being communicated to `threshold-load`, `load-channels`, `activity-qa-flags` and `athlete-benchmarks` -- the exact audience it exists for. This is the species task 5.1's own Implementation Note names: "A deleted rule cannot be caught by a type checker ... needs a textual assertion on the extracted source", applied to the guide's narrowing rule but never to this one.

## Evidence
The obligation exists only at `src/fitdocs/load/types.py:367-373` (verified: the paragraph is there at 3121bb6). `grep -n "aggregate\|actually recorded" docs/contributing-calculators.md` returns nothing, and `tests/test_contributing_calculators_doc.py` has no assertion for it.

## How to pick it up
Read `tests/test_contributing_calculators_doc.py` for the textual-assertion pattern it already uses for the narrowing rule. Preferred fix: move the rule into `docs/contributing-calculators.md` and assert it there, since that is what authors read; second best, assert on the extracted `compute` docstring. Done when deleting the rule from wherever it lives reddens a test.

## Resolution

**Done 2026-07-26** (queue sweep, merged to `main` at `e806c57`).

`e806c57`. Rule moved into `docs/contributing-calculators.md` and asserted on a distinctive phrase appearing exactly once. The `types.py` copy stays as the authoritative source and is DECLARED UNPINNED — deleting it alone fails nothing, stated rather than left implicit. Section insertion broke two markdown anchors; both repointed, gap tracked at `2026-07-26-doc-anchor-links-unchecked`.
