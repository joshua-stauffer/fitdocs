---
id: 2026-09-12-benchmark-source-store-duplications
title: Duplicated source-key-order and grouping logic between benchmarks.py and profile.py
status: open
importance: medium
importance_why: Two independent implementations of the same key order and grouping rule can silently diverge; an empty benchmarks table and whitespace-only detail strings are also handled inconsistently.
effort: S
kind: inconsistency
area: performance-benchmarks, athlete-benchmarks, src/fitdocs/benchmarks.py, src/fitdocs/load/profile.py
created: 2026-09-12
surfaced_by: /kiro-impl performance-benchmarks (adversarial reviews, 2026-09-11/12)
pinned_at: d4fbc6f
resume_command: "do: derive profile._SOURCE_RECOGNIZED_KEYS and profile._benchmark_group_key from benchmarks.py (or add a guard that they agree), and decide the empty-table and whitespace-detail cases"
context:
  - src/fitdocs/benchmarks.py
  - src/fitdocs/load/profile.py
blocked_by: []
---

## What

Four related duplications/gaps between `benchmarks.py` and `profile.py`:

- Two sources of truth for the `source` inner key order:
  `benchmarks_to_document` (in `benchmarks.py`) vs
  `profile._SOURCE_RECOGNIZED_KEYS`.
- `profile._benchmark_group_key` re-implements `benchmarks_to_document`'s
  `(scope, kind)` grouping in a second module.
- A hand-written EMPTY `[benchmarks]` table is dropped by
  `with_derived_benchmarks(())`, while `save_profile` alone preserves it.
- Whitespace-only derived detail strings are accepted, though the design
  says "non-empty" (`"   "` passes as non-empty).

## Why it matters

The key-order and grouping duplication can silently diverge under a future
edit to one module without the other; nothing currently guards agreement.
The empty-table and whitespace-detail cases are unresolved by the spec and
currently behave inconsistently across write paths.

## Evidence

- (2.2 reviewer) "two sources of truth for the source inner key order:
  benchmarks_to_document and profile._SOURCE_RECOGNIZED_KEYS; derive one
  from the other or add a guard that they agree."
- (2.3 r2 reviewer) "profile._benchmark_group_key re-implements
  benchmarks_to_document's (scope, kind) grouping in a second module; a
  public grouping helper on fitdocs.benchmarks would remove the
  duplication."
- (2.3 r2 reviewer) "a hand-written EMPTY [benchmarks] table is dropped by
  with_derived_benchmarks(()) while save_profile alone preserves it; decide
  whether an athlete-written empty table counts under 6.3/6.6."
- (2.1 reviewer) "whitespace-only derived detail strings accepted (design
  says non-empty; `'   '` is non-empty). Undecided by spec. Queue
  candidate, low."

## How to pick it up

1. Read `benchmarks_to_document` and `profile._SOURCE_RECOGNIZED_KEYS`/
   `profile._benchmark_group_key` side by side.
2. Either derive the profile-side constants/grouping from
   `benchmarks.py`'s public surface, or add an equality guard test that
   fails if they diverge.
3. Decide and implement the empty-table and whitespace-detail cases,
   documenting the decision in the relevant spec (athlete-benchmarks for
   the empty table, performance-benchmarks for the detail string).
</content>
