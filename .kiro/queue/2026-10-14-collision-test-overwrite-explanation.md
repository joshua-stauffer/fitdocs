---
id: 2026-10-14-collision-test-overwrite-explanation
title: Correct the collision test's claim that removing the engine filter overwrites the hand entry
status: open
importance: low
importance_why: The existing test rejects the fault, but its explanation names assertions that are never reached because the writer rejects the collision first.
effort: S
kind: docs
area: performance-benchmarks, tests/performance/test_engine.py
created: 2026-10-14
surfaced_by: /kiro-impl hr-derivation task 1.2 independent review
pinned_at: 4267c7f
resume_command: "do: correct the named-mutation paragraph in test_candidate_colliding_with_a_hand_written_entry_declines_and_is_dropped to describe the profile writer's ValueError before report assertions; rerun the mutation and restored test [queue: .kiro/queue/2026-10-14-collision-test-overwrite-explanation.md]"
context:
  - tests/performance/test_engine.py
  - src/fitdocs/performance/engine.py
  - src/fitdocs/load/profile.py
  - .kiro/specs/performance-benchmarks/tasks.md
  - .kiro/steering/change-protocol.md
blocked_by: []
---

## What

The unchanged named-mutation paragraph in
`test_candidate_colliding_with_a_hand_written_entry_declines_and_is_dropped`
(`tests/performance/test_engine.py:1865` during this review) says removing
the engine collision filter writes over the hand entry and is caught by
the later report and value assertions. The profile writer rejects that
candidate with `ValueError` before the report exists. The test still catches
the fault; its explanation of the mechanism is wrong.

## Why it matters

A later maintainer could trust the explanation and mistake this test for
direct coverage of an overwrite. Correcting the prose preserves the useful
test while identifying the actual failure path. This pre-existing explanation
belongs to performance-benchmarks; hr-derivation's partition integration did
not change the collision-filter behavior.

## Evidence

The independent task 1.2 reviewer disabled the engine's collision-filter
condition, ran the named test through `uv run --no-sync pytest ... -q`,
then restored source bytes and observed green. Its captured output was
inspected by the controller:

```text
report = derive_benchmarks(tmp_path)
... profile.with_derived_benchmarks(accepted, kinds=TAGGED_EFFORT_KINDS)
ValueError: with_derived_benchmarks: threshold_pace_s_per_km at 2024-05-01 collides with a retained non-derived entry
src/fitdocs/load/profile.py:431: ValueError
1 failed in 0.15s
```

Evidence was gathered in the task 1.2 worktree based on `4267c7f`; the
misdescribing paragraph is also present unchanged at that commit. The
mutation execution was reviewer-run; the controller confirmed its captured
trace and current source paths, rather than rerunning that mutation itself.
Fresh controller regression after restoration: 1,798 tests passed.

## How to pick it up

1. Read the named test, `_recorded_collision`'s call in the tagged engine,
   and the profile writer's retained-key refusal.
2. Replace the named-mutation paragraph with the observed failure mechanism;
   keep the behavior and assertions unchanged.
3. Disable only the engine filter, run the exact test through `uv run pytest`,
   restore source from a copy and confirm green. Done means the description
   names the actual `ValueError` path and no longer claims an overwrite or
   that the later assertions catch this particular fault.
