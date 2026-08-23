---
id: 2026-07-26-counterfactual-prose-task-1-2
title: Remove the counterfactual test-power claim left in task 1.2's rejection-matrix comment
status: open
importance: low
importance_why: One comment, already-approved code, currently true — but it is the exact claim class that was false in four consecutive review rounds and it will rot the moment the 2.5/2.6 fixtures change.
effort: S
kind: docs
area: athlete-benchmarks, tests/test_benchmarks.py
created: 2026-07-26
surfaced_by: /kiro-impl athlete-benchmarks (task 1.3 final reviewer FOLLOW_UPS)
pinned_at: c3d2201
resume_command: "do: delete the counterfactual claim in tests/test_benchmarks.py's unrecognized_discipline_table case so it states only what the case asserts, not what it would detect [queue: .kiro/queue/2026-07-26-counterfactual-prose-task-1-2.md]"
context:
  - tests/test_benchmarks.py
  - .kiro/specs/athlete-benchmarks/tasks.md
blocked_by: []
---

## What

Task 1.3 established a rule, now recorded in `athlete-benchmarks`'
`## Implementation Notes`: a comment may state what a test asserts, but may not
state which hypothetical wrong implementations it would detect. That claim
class is unverifiable at review time and was false in four consecutive review
rounds of task 1.3, in both directions.

One instance of the prohibited form predates the rule and is still in the tree,
from task 1.2's rejection matrix — the `unrecognized_discipline_table` case,
roughly `tests/test_benchmarks.py:256-260`:

> "if 2.5's own rejection in `_resolve_scope` were ever deleted, the entry
> would resolve to the athlete scope and `_check_scope`'s 2.6 rule ... would
> have nothing to object to, so this case would only fail if 2.5 itself still
> raises."

It was outside task 1.3's diff, so the final reviewer correctly declined to
reject on it and routed it here instead.

## Why it matters

The claim is **currently true** — that is precisely the problem. Every false
claim found during task 1.3 was also true when written; they became false as
fixtures moved underneath them, and each one then actively misinformed the next
editor about coverage that no longer existed. One of them sat in the very
sentence that would have exposed a surviving mutation.

This particular claim describes the interaction between the Requirement 2.5 and
2.6 rejection rules, which is exactly the kind of coupling a later task might
change. Low urgency, but it is a known-shape trap sitting in a file two more
tasks in this spec will edit.

## Evidence

- `tests/test_benchmarks.py`, the `unrecognized_discipline_table` entry in
  `REJECTION_CASES` (introduced by task 1.2, commit now `7e4c513`).
- Task 1.3 final reviewer, FOLLOW_UPS 2: "Outside this diff, so not a rejection
  ground, but it is the same prohibited form and should be queued for cleanup."
- The rule it violates: `.kiro/specs/athlete-benchmarks/tasks.md` →
  `## Implementation Notes` → "Never claim in a comment what a test would
  catch."

## How to pick it up

1. Open `tests/test_benchmarks.py`, find the `unrecognized_discipline_table`
   case in `REJECTION_CASES`.
2. Cut the sentence back to what the case asserts — that the message names the
   offending discipline and lists the recognized names — and drop the reasoning
   about what would happen if rule 2.5 were deleted.
3. Run `uv run pytest -q`; a comment-only edit must not change the count.
4. Done looks like: `grep -iE "were ever|were deleted|would only fail|would wrongly" tests/test_benchmarks.py` returns nothing.

## Open questions

None.
