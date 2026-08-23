---
id: 2026-07-30-sourced-names-tuple-goes-stale
title: ConstantGuard's sourced_names is a hardcoded 7-tuple that goes silently stale when an eighth cited constant is read
status: open
importance: low
importance_why: An 8th module-level constant read through .value is not noticed by anything, but the dangerous direction (a bare literal) is still caught with sole-failure scope, so no uncited value can ship — this is the last un-derived instance of the tuple shape that cost task 12.2 four review rounds.
effort: S
kind: gap
area: fit-ingest, tests/metrics/test_constant_guard.py
created: 2026-07-30
surfaced_by: /kiro-impl fit-ingest (task 12.2, round-5 review follow-up)
pinned_at: c3d2201
resume_command: "/kiro-impl fit-ingest [queue: .kiro/queue/2026-07-30-sourced-names-tuple-goes-stale.md] Derive sourced_names from the metric modules' ASTs instead of hardcoding seven names"
context:
  - tests/metrics/test_constant_guard.py
  - src/fitdocs/metrics/sources.py
  - .kiro/steering/change-protocol.md
blocked_by: []
---

## What

`test_a_cited_constant_access_does_not_appear_as_a_literal` in
`tests/metrics/test_constant_guard.py` checks that each module-level constant
read from a `CitedConstant` is accessed by attribute rather than re-spelled as
a literal. Its subject is a hardcoded 7-tuple, `sourced_names`, plus an
`assert checked == 7`.

Add an eighth module-level constant that reads a record through `.value` and
nothing notices.

## Why it matters

Low, and deliberately so — the reviewer verified the dangerous direction is
still closed. What this leaves open is only a *missed check*, not a hole:

- An 8th constant read correctly through `.value` is simply not verified —
  harmless.
- An 8th constant written as a **bare literal** is still caught with
  sole-failure scope by `test_every_numeric_literal_in_the_three_metric_modules_is_exempted`.

It is worth recording because it is the **last un-derived instance** of the
shape that caused four of task 12.2's five rejections: a tuple written when
there were N records, never updated when N+1 arrived. Seven other instances of
it were found one per review round. The structural answer — derive the subject
instead of enumerating it — was applied to eleven walks in
`tests/metrics/test_sources.py` and not to this one.

## Evidence

Mutation run by the task 12.2 round-5 reviewer against the pre-commit tree
(now `ab1038d`), line-count-preserving, appended at EOF:

```python
# in src/fitdocs/metrics/power.py
_EIGHTH_SOURCED: Final[float] = sources.NP_MIN_SPAN_S.value
```
→ **suite stayed green at 2230.** The 7-tuple did not notice.

Contrast, same position:
```python
_EIGHTH_BARE: Final[float] = 0.75
```
→ **sole failure**, `test_every_numeric_literal_in_the_three_metric_modules_is_exempted`.

Both reverted; tree verified byte-identical afterwards.

## How to pick it up

1. Open `test_a_cited_constant_access_does_not_appear_as_a_literal` in
   `tests/metrics/test_constant_guard.py` and find `sourced_names` and its
   `assert checked == 7`.
2. Derive the set instead: AST-walk the three metric modules for module-level
   assignments whose value is an attribute access ending in `.value` on the
   `sources` module. Keep a non-emptiness assert — a walk that finds nothing
   must red, per this repo's repeated experience with vacuous walks.
3. Better still, reuse the shape that survived four separate attacks in
   `tests/metrics/test_sources.py`: derive the set, then assert a closing
   bijection against the enumerated names compared over identity, so a new
   constant reds loudly rather than being silently absorbed.
4. Verify by mutation: re-run both mutations above. The `_EIGHTH_SOURCED` case
   must now red; the `_EIGHTH_BARE` case must still red.

Done looks like: adding an eighth `.value`-read module-level constant to a
metric module reds a named assertion.
