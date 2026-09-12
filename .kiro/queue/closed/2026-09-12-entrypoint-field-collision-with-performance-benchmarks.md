---
id: 2026-09-12-entrypoint-field-collision-with-performance-benchmarks
title: tests/test_confinement.py EntryPoint gained `non_vacuous` on load-history while performance-benchmarks adds `wrote` -- whoever merges second must reconcile to one field
status: done
importance: medium
importance_why: Both branches extend the same frozen dataclass in an append-only shared test; a keep-both rebase compiles and then every EntryPoint literal fails on a missing keyword, which looks like an unrelated confinement failure.
effort: S
kind: inconsistency
area: performance-benchmarks, load-history, tests/test_confinement.py, tests/load/test_settings.py
created: 2026-09-12
surfaced_by: /kiro-impl load-history 5.4 (controller, agent-log TOUCHING/WARN)
pinned_at: 8cd0062
resume_command: "do: after both impl/load-history and impl/performance-benchmarks are on main, collapse EntryPoint.non_vacuous / EntryPoint.wrote into one field with one meaning, and make tests/load/test_settings.py's licensed-caller set the union {load/engine.py, history/engine.py, <benchmarks caller>} with the docstring count updated"
context:
  - tests/test_confinement.py
  - tests/load/test_settings.py
  - .kiro/specs/load-history/tasks.md
blocked_by: []
---

## What
load-history added `EntryPoint.non_vacuous: bool` (the history entry point
writes nothing on an empty archive, so its "confined" check needs a
non-vacuous input). The peer `impl-performance-benchmarks` session's WARN
line says it adds `EntryPoint.wrote`. Both express "this entry point
actually produced output". Two fields with one meaning is the drift the
test exists to prevent. `tests/load/test_settings.py`'s one-caller guard was
widened to a two-element set on this branch; the peer adds a third.

## Evidence
Agent log: `impl-load-history` TOUCHING (tests/test_confinement.py) and
WARN (EntryPoint collision); `impl-performance-benchmarks` WARN naming
`EntryPoint.wrote`. tasks.md Implementation Notes for 5.4.

## How to pick it up
Close as no-op if the second merge already reconciled them (check
`grep -n "non_vacuous\|wrote" tests/test_confinement.py` on main). Otherwise
a one-field refactor plus the caller-set union; trivial class, but touch it
on a branch since it is a shared guard.

## Closed 2026-09-12 (performance-benchmarks merge-back)

Resolved on the rebase of impl/performance-benchmarks onto main at
9a86e48: `tests/test_confinement.py` keeps ONE field,
`EntryPoint.non_vacuous: Callable[[Sequence[str]], bool]` (load-history's
name, default `_wrote_a_workout_document`), and the `derive-benchmarks`
entry passes `_wrote_only_the_athlete_profile` through it (equality with
`("data/athlete.toml",)`); `EntryPoint.wrote` no longer exists.
`tests/load/test_settings.py::test_load_load_settings_is_called_from_exactly_the_licensed_modules`
pins the three-set `{load/engine.py, history/engine.py,
performance/engine.py}` with the docstring count updated, and the
per-command companion carries both the `history` and `derive-benchmarks`
rows. Verified: full suite 4041 passed on the rebased tree;
`tests/test_confinement.py -k derive-benchmarks` passes with the equality
predicate.

