---
id: 2026-07-26-bullet-2-same-root-control-inert
title: Task 6.1 bullet 2 mandates a same-data-root control that is provably inert
status: open
importance: low
importance_why: Spec text asks for a comparison that cannot discriminate; the implementation correctly deviated and the text should match.
effort: S
kind: inconsistency
area: training-load, .kiro/specs/training-load/tasks.md
created: 2026-07-26
surfaced_by: /kiro-validate-impl training-load
pinned_at: c3d2201
resume_command: "do: Amend task 6.1's bullet 2 in .kiro/specs/training-load/tasks.md to describe the two-root design that was implemented, and record why the same-root form cannot discriminate"
context:
  - .kiro/specs/training-load/tasks.md
  - tests/load/test_arbitration_e2e.py
blocked_by: []
---

## What
Task 6.1's bullet 2 requires that the zero-prompt and does-prompt halves be observed "in the same data root". With one configured default declaring one required field, the pass-wide prompt count is 1 in either processing order whether or not the support gate fired, because the first document's answer is persisted and the second finds it present. The implementation used two roots differing only in sport, which is the controlled form.

## Why it matters
Nobody is harmed today -- the guard works and is mutation-verified. But the spec text asks for something unsatisfiable-non-vacuously, so the next reader either implements the inert version or spends a round rediscovering why it was not implemented.

## Evidence
Measured by the task 6.1 round-2 reviewer: it wrote the literal same-root form and ran it under the gate-moved mutation; it passed, in either scan order. The two-root implementation reddens under the same mutation. See `tests/load/test_arbitration_e2e.py::test_configured_default_prompts_only_for_the_activity_it_covers`.

## How to pick it up
Open `.kiro/specs/training-load/tasks.md` at task 6.1's bullet 2. Rewrite it to require a fresh profile per assertion (or distinct required fields per calculator), which is what makes the zero-prompt claim observable. Add one clause recording the absorption mechanism so it is not reintroduced. Done when the text describes the shipped design and says why.
