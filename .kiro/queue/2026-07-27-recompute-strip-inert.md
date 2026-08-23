---
id: 2026-07-27-recompute-strip-inert
title: The engine's recompute-time frontmatter strip is inert suite-wide, but its docstring cites Req 8.3 to justify it
status: open
importance: medium
importance_why: Either the line is dead code whose stated justification is stale, or it guards something no test exercises — and the ambiguity is what makes a real second-pass byte-identity assertion unpinnable by any single-line mutation.
effort: S
kind: inconsistency
area: training-load, src/fitdocs/load/engine.py
created: 2026-07-27
surfaced_by: /kiro-impl athlete-benchmarks (task 6.1 review, rounds 1 and 2, independently)
pinned_at: c3d2201
resume_command: "do: decide whether the recompute-time strip at src/fitdocs/load/engine.py:402-403 is redundant with apply_frontmatter_load's own filter — remove it and correct the docstring, or add the test that makes it observable [queue: .kiro/queue/2026-07-27-recompute-strip-inert.md]"
context:
  - src/fitdocs/load/engine.py
  - src/fitdocs/load/docedit.py
  - tests/load/test_feature_e2e.py
  - tests/load/test_benchmark_selection_e2e.py
blocked_by: []
---

## What

`src/fitdocs/load/engine.py:402-403` strips the managed frontmatter keys when
`recompute` is set. That line is inert: replacing `if recompute:` with
`if False:` leaves the **entire suite green (2011 passed)**. It is inert because
`apply_frontmatter_load` (`src/fitdocs/load/docedit.py:287`) already performs the
same strip before re-appending.

The engine's own docstring at `engine.py:394-400` cites `training-load` Req 8.3
to justify the line — "a recompute strips the managed frontmatter keys first so
the confirmation truly happens from scratch". So either the strip is genuinely
redundant and that justification is stale, or it has a purpose that no test
exercises.

## Why it matters

Two guards that each fully mask the other cannot be individually verified, so
neither is protected against deletion: a future session removing *either* one
sees a green suite and concludes it was dead. It also has a concrete downstream
cost already observed — it is the structural reason task 6.1 could not pin its
second-pass byte-identity assertion by any single-line mutation, which forced an
honest UNPINNED declaration on part of Req 3.8.

## Evidence

- `if recompute:` → `if False:` at `src/fitdocs/load/engine.py:402`:
  `uv run pytest -q` → **2011 passed**. Measured twice, by two independent
  reviewers (task 6.1 rounds 1 and 2), each through `uv run pytest`.
- The converse direction: mutating `apply_frontmatter_load`'s own filter at
  `src/fitdocs/load/docedit.py:287` to `kept = list(lines[1:close])` leaves
  `tests/load/test_benchmark_selection_e2e.py` green, but **does** red
  `tests/load/test_feature_e2e.py:309::test_second_identical_pass_writes_no_bytes`
  at its byte-identity assertion (`test_feature_e2e.py:335`). So the behavior is
  covered on the non-recompute path only.
- Note when reproducing: `docedit.py` has two byte-identical `_is_managed_line`
  filter lines (`:287` in `apply_frontmatter_load`, `:326` in
  `strip_frontmatter_load`). Mutate by line number and diff the file before
  trusting a green result.

## How to pick it up

1. Read `src/fitdocs/load/engine.py:394-403` and `src/fitdocs/load/docedit.py:287`
   and `:326` together; establish whether the engine strip can ever see input the
   `apply_frontmatter_load` filter would not already handle.
2. If it cannot: delete the line and rewrite the docstring so it no longer cites
   Req 8.3 for behavior that lives in `docedit`. If it can: write the test that
   distinguishes them — a fixture whose managed lines survive one path but not
   the other.
3. Done looks like: mutating whichever guard remains reds at least one test, and
   no docstring claims a justification the code does not carry.
