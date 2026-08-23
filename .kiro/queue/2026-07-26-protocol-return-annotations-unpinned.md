---
id: 2026-07-26-protocol-return-annotations-unpinned
title: A `ProfileView` member's declared return type can be widened invisibly to all three gates
status: open
importance: low
importance_why: An accidental Protocol return-type widening is not a plausible regression, but it is the last open axis of a defect class that cost task 4.1 a full rejection round, and the close is two assertions.
effort: S
kind: gap
area: athlete-benchmarks, src/fitdocs/load/types.py, tests/load/test_types.py
created: 2026-07-26
surfaced_by: /kiro-impl athlete-benchmarks (task 4.1 round-2 reviewer, own mutation sweep)
pinned_at: c3d2201
resume_command: "do: pin the declared return annotations of ProfileView.benchmark and .has_benchmark in tests/load/test_types.py's signature test, then verify by re-running the surviving mutation [queue: .kiro/queue/2026-07-26-protocol-return-annotations-unpinned.md]"
context:
  - src/fitdocs/load/types.py
  - tests/load/test_types.py
  - .kiro/steering/change-protocol.md
blocked_by: []
---

## What
Task 4.1 closed the *parameter* half of the "a declared type is pinned by
nothing unless a test reads it" class — `signature(...).parameters["on"]
.annotation` and `dataclasses.fields(X)[i].type` are now asserted. The
**return** annotations were not covered. Widening
`ProfileView.has_benchmark(...) -> bool` to `-> object` leaves all three
canonical gates green.

## Why it matters
Not because a maintainer will widen a return type by accident. It matters
because this is the one remaining axis of the class, and because the *reason*
it escapes is structural and will recur for every future contract member: mypy
does not check tests (`pyproject.toml` `files = ["src"]`), and a newly declared
Protocol member has no `src/` consumer to type-check against until a later task
wires one. Every new member lands unpinned in this direction by default.

## Evidence
At `9a22c87`, mutate `src/fitdocs/load/types.py:306`, `-> bool` to `-> object`:

```
uv run pytest -p no:cacheprovider   # 1998 passed
uv run ruff check .                 # All checks passed
uv run mypy --strict src/           # Success: no issues found in 59 source files
```

`bool <: object`, so `AthleteProfile` still satisfies the Protocol at
`src/fitdocs/load/engine.py:493`. Narrowing substitutions *are* caught:
`-> str` / `-> Sport` red under mypy. `-> bool | None` is caught only by ruff
`E501` (93 > 88 chars) — line length, not a semantic gate, so that kill is
luck. The reviewer ran this with `__pycache__` purged and
`-p no:cacheprovider`.

## How to pick it up
1. Read `tests/load/test_types.py::test_profile_view_benchmark_queries_take_discipline_and_date_explicitly` — it already asserts `parameters["on"].annotation == "date | None"`, so the technique is in place and this is a two-line extension.
2. Add `inspect.signature(ProfileView.has_benchmark).return_annotation == "bool"` and `inspect.signature(ProfileView.benchmark).return_annotation == "Benchmark | None"`.
3. Done looks like: the `-> object` mutation above now reds that test, verified with `__pycache__` cleared and `-p no:cacheprovider` (the mutation is byte-length-changing, but clear anyway — see [[2026-07-26-pycache-masks-length-preserving-mutations]]).

Related: the structural alternative is
[[2026-07-26-contributing-example-omits-benchmark-queries]] — giving the
members a real mypy-checked consumer closes this without signature
introspection.
