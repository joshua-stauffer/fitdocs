---
id: 2026-07-26-contributing-example-omits-benchmark-queries
title: The contributing guide's mypy-checked worked example does not exercise the new `ProfileView` benchmark queries
status: open
importance: medium
importance_why: That example is both the only plugin-author documentation of the profile contract and the repo's one structural pin for declared contract types with no `src/` consumer; it now documents a third of the protocol.
effort: S
kind: docs
area: athlete-benchmarks, docs/, tests/test_contributing_calculators_doc.py
created: 2026-07-26
surfaced_by: /kiro-impl athlete-benchmarks (task 4.1 round-2 reviewer, control mutation)
pinned_at: 9a22c87
resume_command: "do: extend the contributing guide's worked calculator example to consume ProfileView.benchmark and .has_benchmark, so tests/test_contributing_calculators_doc.py type-checks both new members [queue: .kiro/queue/2026-07-26-contributing-example-omits-benchmark-queries.md]"
context:
  - tests/test_contributing_calculators_doc.py
  - src/fitdocs/load/types.py
  - docs/plugins.md
blocked_by: []
---

## What
`tests/test_contributing_calculators_doc.py` runs `mypy --strict` over the
contributing guide's worked calculator example. That example consumes only
`ProfileView.get_number`. Task 4.1 added `benchmark(kind, *, discipline, on)`
and `has_benchmark(kind, *, discipline)` to the protocol, and the example
mentions neither.

Two consequences, one documentary and one mechanical:

- A plugin author reading the guide cannot discover the members that are the
  entire point of the athlete-benchmarks feature — asking for a threshold by
  discipline and activity date instead of encoding structure in a key string.
- That test is the repo's **only** structural pin for a declared contract type
  that has no `src/` consumer. Extending the example is the general close for
  [[2026-07-26-protocol-return-annotations-unpinned]] and for every future
  contract member, and it closes them by making the type *load-bearing* rather
  than by asserting annotation strings.

## Why it matters
The mechanical half is the reason this is `medium` rather than `low`. Without a
consumer in that example, every new `ProfileView` or `AthleteField` member
lands with its declared types checkable only by signature introspection —
which task 4.1 proved is easy to omit and was in fact omitted, costing a
rejection round.

## Evidence
At `9a22c87`:

```
grep -n "ProfileView\|get_number" tests/test_contributing_calculators_doc.py
```
shows no reference to either new member.

The pin is real and measurable — the reviewer's control mutation: widening the
**pre-existing** `ProfileView.get_number` return to `object | None` reds
`tests/test_contributing_calculators_doc.py::test_worked_example_type_checks_against_the_shipped_contract`
while `uv run mypy --strict src/` stays green. So the mechanism works; the two
new members simply are not routed through it.

## How to pick it up
1. Read `tests/test_contributing_calculators_doc.py` (the worked example is embedded around lines 67–80) to see how the example is assembled and type-checked.
2. Extend the example calculator so it resolves a benchmark by discipline and the context's activity date and consumes the returned value in a way mypy must check arithmetically (the `get_number` control shows why arithmetic consumption is what makes the pin bite).
3. Done looks like: widening `has_benchmark() -> bool` to `-> object` in `src/fitdocs/load/types.py` now reds this test, and the guide's prose names both members.

Best sequenced after athlete-benchmarks task 5.2, which gives the members their
first real `src/` consumer and a `LoadContext.activity_date` to pass. Note the
guide's surface list is separately stale — [[2026-07-26-plugin-surface-list-stale-after-amendment-3]].
