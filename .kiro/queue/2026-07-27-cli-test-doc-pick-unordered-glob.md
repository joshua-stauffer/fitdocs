---
id: 2026-07-27-cli-test-doc-pick-unordered-glob
title: Three CLI tests pick their workout document with an unordered `glob` over a directory that also holds AGENTS.md
status: open
importance: low
importance_why: A filesystem-order-dependent fixture pick is a latent flake that will surface on a different machine or filesystem, not on the one that wrote it.
effort: S
kind: chore
area: tests/test_cli.py
created: 2026-07-27
surfaced_by: /kiro-impl athlete-benchmarks (task 5.3 review, round 1)
pinned_at: bb5ab9d
resume_command: "do: make the workout-document pick deterministic in tests/test_cli.py by sorting and filtering the declaration file, reusing the _docs() helper [queue: .kiro/queue/2026-07-27-cli-test-doc-pick-unordered-glob.md]"
context:
  - tests/test_cli.py
blocked_by: []
---

## What

`tests/test_cli.py` picks the workout document under test with
`doc_path = next((data_root / "workouts").glob("*.md"))` at `:311`, `:349` and
`:383`. `glob` does not guarantee ordering, and `workouts/` also contains
`AGENTS.md`, so which file the test inspects is filesystem-order dependent.

A `_docs()` helper at `tests/test_cli.py:97` already implements the sorted,
declaration-file-filtered pick these call sites want.

## Why it matters

The tests pass today because the local filesystem happens to return the workout
document first. On a filesystem with different ordering — another OS, a different
temp backend, a CI runner — `next(...)` can return `AGENTS.md`, and the test then
asserts byte-identity or content against the wrong file. That fails confusingly,
far from the cause, and looks like a real regression.

## Evidence

- `tests/test_cli.py:311`, `:349`, `:383`: `next((data_root / "workouts").glob("*.md"))`.
- `workouts/` contains `AGENTS.md` alongside the workout documents in these
  fixtures.
- The correct pattern already exists in the same file: `_docs()` at
  `tests/test_cli.py:97` sorts and filters by `DECLARATION_FILENAME`.

## How to pick it up

1. Read `_docs()` at `tests/test_cli.py:97`.
2. Replace the three `next(...glob(...))` picks with it (or with
   `sorted(...)` plus the same filter).
3. Done looks like: no `next(...glob(...))` remains in `tests/test_cli.py`, and
   the suite is green. Sanity check the change is not cosmetic by confirming each
   call site still selects the same document it did before.
