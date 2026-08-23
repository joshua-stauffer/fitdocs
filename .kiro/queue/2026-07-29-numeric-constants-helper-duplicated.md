---
id: 2026-07-29-numeric-constants-helper-duplicated
title: The AST numeric-literal helper is copied verbatim into each metric test module, and task 10.3 makes a third copy
status: open
importance: low
importance_why: Pure duplication with no behavioral risk today, but it is copied once per 10.x task and task 12.2 ships the guard that should replace all of them.
effort: S
kind: chore
area: fit-ingest, tests/metrics/
created: 2026-07-29
surfaced_by: /kiro-impl fit-ingest (task 10.2, review round 1)
pinned_at: c3d2201
resume_command: "/kiro-impl fit-ingest [queue: .kiro/queue/2026-07-29-numeric-constants-helper-duplicated.md] Fold the duplicated _numeric_constants_in_source helper into task 12.2's package-wide literal guard, or hoist it into a shared test helper"
context:
  - tests/metrics/test_aggregates.py
  - tests/metrics/test_power.py
  - .kiro/specs/fit-ingest/tasks.md
blocked_by: []
---

## What

`_numeric_constants_in_source`, a ten-line helper that walks a module's AST and
collects its numeric constants, exists verbatim in both
`tests/metrics/test_aggregates.py` (task 10.1) and `tests/metrics/test_power.py`
(task 10.2). Task 10.3 needs the same check for `stress.py` and will make a
third copy.

## Why it matters

No behavioral risk: each copy is exercised by its own module's guard and the
duplication is visible. The cost is that a fix to one copy does not reach the
others — and there is already a known weakness to fix. The helper's guard cannot
tell which module it scanned (pointing it at a different module leaves the test
green), tracked separately at
`2026-07-29-literal-guard-does-not-pin-its-module`. Fixing that in three places
is three times the work and two chances to miss one.

## Why it may not be worth doing on its own

Task 12.2 ("Guard the literal surface of the metric modules") ships a
package-wide numeric-literal scan that supersedes all three per-module guards.
If 12.2 lands as specified, the right outcome is that these copies are deleted
rather than consolidated. This item exists so that is a decision rather than an
accumulation.

## Evidence

At `373405a`: identical helper definitions in `tests/metrics/test_aggregates.py`
and `tests/metrics/test_power.py`, each followed by a
`test_module_source_has_no_bare_..._literal` guard using it. Reported by the
task 10.2 reviewer; the duplication is visible by reading both files.

## How to pick it up

1. Check whether task 12.2 has landed. If it has, delete the per-module helpers
   and their guards, and confirm 12.2's scan covers every module they covered —
   `aggregates.py`, `power.py`, `stress.py` — before removing anything.
2. If 12.2 has not landed, hoist the helper into the metrics test package's
   `conftest.py` or a shared helper module, and leave the per-module guards
   calling it.
3. Either way, close
   `2026-07-29-literal-guard-does-not-pin-its-module` in the same change if the
   consolidated form can assert which module it scanned — the two items share a
   fix.
4. If a test module is added to hold the shared helper, add it to
   `[tool.mypy].files` in `pyproject.toml`, which names checked test modules
   explicitly.

## Open questions

None.
