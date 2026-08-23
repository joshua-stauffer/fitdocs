---
id: 2026-07-26-benchmark-value-validation-duplicated
title: Benchmark value validation is implemented twice with divergent error types and nothing asserts the two agree
status: open
importance: low
importance_why: The two validators can drift silently, letting the store accept a value the parser would reject on the next read — a write that cannot be read back.
effort: S
kind: inconsistency
area: athlete-benchmarks, src/fitdocs/load/profile.py, src/fitdocs/benchmarks.py
created: 2026-07-26
surfaced_by: /kiro-impl athlete-benchmarks (task 3.2, round-1 review)
pinned_at: c3d2201
resume_command: "/kiro-impl athlete-benchmarks [queue: .kiro/queue/2026-07-26-benchmark-value-validation-duplicated.md] Bind the store's and the parser's benchmark value rules with a test quantified over BenchmarkKind"
context:
  - src/fitdocs/load/profile.py
  - src/fitdocs/benchmarks.py
  - tests/load/test_profile.py
  - tests/test_benchmarks.py
blocked_by: []
---

## What
Two functions implement the same benchmark value rules — reject a `bool`,
require finite and positive, require a whole number for an `INTEGRAL_KINDS`
quantity:

- `_validate_benchmark_value` in `src/fitdocs/load/profile.py` (~`:565-580`),
  raising `ValueError`, for values arriving from a caller
- `_validate_value` in `src/fitdocs/benchmarks.py` (`:244+`), raising
  `BenchmarkError`, for values arriving from disk

The split is deliberate and documented — a caller error and an on-disk error are
different failures with different audiences — but nothing asserts the two accept
and reject the same set of values.

## Why it matters
Drift is silent and asymmetric in the dangerous direction. If the store's
validator ever becomes more permissive than the parser's, `with_benchmark`
accepts a value, `save_profile` writes it, and the next `load_profile` rejects
the file — a write that cannot be read back, which is the failure class task 3.2
spent five rounds eliminating from the *shape* of the document and never
addressed for its *values*.

Task 3.2 already hit one instance of the two disagreeing: the store coerced
every value to `float`, so `with_benchmark(FTP_WATTS, value=260)` wrote `260.0`
where the same value from the parser wrote `260`. That was fixed by making the
store mirror the parser's type contract — by hand, with nothing to keep it
mirrored.

## Evidence
At `84e5e56`, both validators exist and encode the same four rules with
different exception types and different message wording. The float-coercion
divergence is recorded in the debug report for task 3.2 (row 4 of its defect
set, classified LOSSY) and was fixed in round 3; see this spec's `tasks.md`
Implementation Notes.

Reported by the round-1 reviewer subagent as a follow-up; the duplication is
verifiable by reading the two functions, the historical divergence by
`git log -p src/fitdocs/load/profile.py` around the round-3 fix.

## How to pick it up
Read both functions side by side. Add one test, in
`tests/load/test_profile.py`, quantified over `BenchmarkKind`: for a table of
candidate values spanning the rules — a `bool`, `nan`, `inf`, zero, a negative,
a fraction, a whole `float`, a whole `int` — assert that the store's validator
and the parser's agree on accept/reject for every kind. Do not assert the same
exception type; assert the same *verdict*.

Done when: making one validator more permissive than the other reds that test.
Verify cache-cleared per `2026-07-26-pycache-masks-length-preserving-mutations`.

## Open questions
Whether to go further and have the store delegate to the parser's validator,
translating the exception type at the boundary. That removes the drift entirely
but couples the two modules more tightly than the current design intends —
worth a look while writing the test, since the test may make the case either way.
