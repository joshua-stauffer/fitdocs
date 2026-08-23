---
id: 2026-07-26-benchmarks-serializer-sort-confounded
title: The serializer's date-sort is unpinned by its own test module — the fixture cannot tell date-sort from value-sort
status: open
importance: medium
importance_why: Req 6.6's determinism guarantee rests on this sort; its owning suite passes under a wrong sort key, so only a downstream consumer's test catches a regression.
effort: S
kind: gap
area: athlete-benchmarks, tests/test_benchmarks.py, src/fitdocs/benchmarks.py
created: 2026-07-26
surfaced_by: /kiro-impl athlete-benchmarks (task 3.2, rounds 2-3 review)
pinned_at: c3d2201
resume_command: "/kiro-impl athlete-benchmarks [queue: .kiro/queue/2026-07-26-benchmarks-serializer-sort-confounded.md] Make the serializer's own sort test discriminate date-sort from value-sort"
context:
  - .kiro/specs/athlete-benchmarks/requirements.md
  - .kiro/specs/athlete-benchmarks/tasks.md
  - src/fitdocs/benchmarks.py
  - tests/test_benchmarks.py
blocked_by: []
---

## What
`benchmarks_to_document` emits each `(scope, kind)` group sorted ascending by
`measured_on` (Req 6.6). Its own test module's ordering test uses a fixture
whose `value` ascends together with `measured_on`, so `sorted(key=measured_on)`
and `sorted(key=value)` produce identical output and the assertion cannot
distinguish them — the "confounded fixture" anti-pattern named in
`.kiro/steering/change-protocol.md` § Fixture Discrimination.

## Why it matters
Req 6.6 exists so that identical inputs produce an identical file. Today a
regression in the sort key is caught only by a test in a *different* module
that happens to consume the serializer (`tests/load/test_profile.py`, added by
task 3.2). If that consumer's fixture is ever retuned — and it was retuned
three times during task 3.2's five review rounds — the sort silently loses all
coverage, because the module that owns the behavior never pinned it.

## Evidence
Reproduced in this session at `84e5e56`. Mutating
`src/fitdocs/benchmarks.py:451`:

    sorted(entries, key=lambda benchmark: benchmark.measured_on)
    ->
    sorted(entries, key=lambda benchmark: benchmark.value)

then running cache-cleared:

    find . -name __pycache__ -type d -prune -exec rm -rf {} + ; uv run pytest -q -p no:cacheprovider tests/test_benchmarks.py
    70 passed in 0.05s

The serializer's entire owning suite passes under a wrong sort key. The full
suite catches it with exactly one failure, in another module:

    1 failed, 1990 passed
    FAILED tests/load/test_profile.py::test_with_benchmark_round_trip_upserts_sorts_and_preserves

Mutation reverted; `git diff --stat src/fitdocs/benchmarks.py` empty afterwards.

## How to pick it up
Open `tests/test_benchmarks.py` and find the serializer ordering test
(`test_benchmarks_to_document_groups_by_scope_and_quantity_sorted_by_date`).
Its fixture needs `value` to **counter-vary** with `measured_on` — the earlier
entry carrying the larger value — so that a value-keyed sort produces a
different order than a date-keyed one. Task 3.2's own round-trip fixture was
fixed the same way (earlier→300, later→240) and is a working model.

Done when: the mutation above reds a test **in `tests/test_benchmarks.py`**,
verified cache-cleared per
`2026-07-26-pycache-masks-length-preserving-mutations`. Note this mutation is
length-changing, so the cache hazard does not apply to it specifically.

## Open questions
Whether task 1.2's other serializer assertions have the same shape. The
grouping-by-scope-and-quantity half was not probed.
