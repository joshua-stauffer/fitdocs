---
id: 2026-07-26-benchmarkset-invariants-unenforced
title: design.md claims BenchmarkSet invariants the type does not enforce
status: open
importance: medium
importance_why: BenchmarkSet is publicly constructible and consumed by name by two downstream specs; a hand-built set with duplicate keys makes applicable() order-dependent, which is the determinism Req 9.5 and the type's own docstring rest on.
effort: S
kind: inconsistency
area: athlete-benchmarks, src/fitdocs/benchmarks.py
created: 2026-07-26
surfaced_by: /kiro-impl athlete-benchmarks (task 1.3 reviewer FOLLOW_UPS)
pinned_at: c3d2201
resume_command: "do: reconcile design.md's BenchmarkSelection/BenchmarkVocabulary invariants with what src/fitdocs/benchmarks.py actually enforces -- either add the __post_init__ uniqueness check and establish a canonical order, or correct the design text to state both are parser-boundary guarantees [queue: .kiro/queue/2026-07-26-benchmarkset-invariants-unenforced.md]"
context:
  - src/fitdocs/benchmarks.py
  - tests/test_benchmarks.py
  - .kiro/specs/athlete-benchmarks/design.md
  - .kiro/specs/athlete-benchmarks/requirements.md
blocked_by: []
---

## What

`design.md` states two invariants about `BenchmarkSet` that the shipped type
does not enforce. Neither is a live defect today, but both are load-bearing
claims that a reader — or a downstream spec — would reasonably rely on.

1. **"Entries are held in a canonical order and ties are impossible"**
   (`design.md`, BenchmarkSelection). `parse_benchmarks` appends entries as it
   walks the decoded mapping, so `BenchmarkSet.entries` is in
   document-iteration order, not a canonical one. Determinism is real but comes
   from somewhere else: `(discipline, kind, measured_on)` is rejected as a
   duplicate at parse time, so `max(qualifying, key=measured_on)` has a unique
   winner regardless of order.

2. **"`(discipline, kind, measured_on)` is unique within a set"**
   (`design.md`, BenchmarkVocabulary invariants). Only `parse_benchmarks`
   checks this. `BenchmarkSet` is a public frozen dataclass that anyone can
   construct directly — the task 1.3 tests do exactly that — and a
   hand-constructed set carrying two entries with the same natural key makes
   `applicable()`'s `max` order-dependent, breaking the very determinism the
   type's docstring leans on.

## Why it matters

`BenchmarkSet` is not an internal detail. `load-channels` and `threshold-load`
consume the benchmarks module by name, and task 3.1 will hand profile-store
callers a `BenchmarkSet` built from disk. Today every set reaching
`applicable()` came through `parse_benchmarks`, so the invariant holds by
construction — but nothing in the type says so, and nothing stops a later spec,
a test fixture, or a store method from building one directly.

The failure mode is quiet: no exception, no wrong type, just a benchmark
resolving to one of two same-dated entries depending on dict iteration order.
Requirement 9.5 ("repeated calls with equal inputs return equal results") would
still pass every test, because the tests build their sets the same way twice.

The canonical-order sentence is the cheaper half: it describes something untrue
and should either become true or be reworded, because a future reader
optimizing `applicable()` might reasonably drop the `max` in favor of "take the
last entry" on the strength of that sentence.

## Evidence

- `src/fitdocs/benchmarks.py` — `BenchmarkSet` is `@dataclass(frozen=True)`
  with `entries: tuple[Benchmark, ...]` and no `__post_init__`; uniqueness is
  enforced only inside `parse_benchmarks`.
- Task 1.3 reviewer, FOLLOW_UPS 1 and 2: "the design sentence is descriptively
  inaccurate and should be corrected to say determinism rests on the
  duplicate-key rejection invariant"; "`BenchmarkSet` is a publicly
  constructible frozen dataclass... a hand-constructed set with two same-key
  entries makes `max` order-dependent, which is exactly the determinism the new
  docstring leans on."
- Task 1.3 implementer resolved the ordering question as option (b) — rely on
  the duplicate-rejection invariant, do not sort — and recorded it in the
  `BenchmarkSet` docstring. The reviewer independently judged that reasoning
  sound. So the *code* is fine; the *design text* and the *type's guarantees*
  are what disagree.
- `uv run pytest -q` at `e50522c` → 1793 passed. Nothing fails; this is not
  detectable by the suite.

## How to pick it up

1. Read `src/fitdocs/benchmarks.py`'s `BenchmarkSet` and `applicable`, then the
   BenchmarkSelection and BenchmarkVocabulary sections of
   `.kiro/specs/athlete-benchmarks/design.md`. The disagreement is two
   sentences against ~40 lines of code.
2. Decide the cheaper direction. Adding a `__post_init__` that rejects
   duplicate `(discipline, kind, measured_on)` keys makes both design sentences
   true and costs one method — but it moves a parse-time error into the type
   constructor, so check it does not change which error type surfaces where
   (parse validation raises `BenchmarkError`; the selection precondition raises
   `ValueError`, per `design.md`'s error table).
3. Otherwise correct the design text: say entries are held in document order,
   that uniqueness is a `parse_benchmarks` guarantee rather than a type
   invariant, and that `applicable()`'s determinism follows from the former.
4. Done looks like: the design text and the code agree, and if a
   `__post_init__` landed, a test constructs a duplicate-key set directly and
   asserts it raises.

## Open questions

- If `__post_init__` validation is added, does it raise `BenchmarkError` (data
  validation, matching the parser) or `ValueError` (programming error, matching
  the selection precondition)? A set built by hand in a downstream spec is
  arguably the latter, but a set built from disk by the task 3.1 store is the
  former, and the same constructor serves both.

## Update 2026-09-10 (training-load Amendment 4, design + boundary validation)

One more invariant of the same kind: `applies_from <= measured_on` is
enforced by the parser (2.11) and by `AthleteProfile.with_benchmark` (6.10),
never by the frozen `Benchmark` value type — its docstring says so
deliberately ("enforced by the parser, not by this value type", verified by
constructing `Benchmark(measured_on=2020-01-01, applies_from=2030-01-01)`
without error). A plugin building `Benchmark` directly can therefore make
`BenchmarkSet.applicable`'s tier 2 return a nonsense entry. Whether the value
type should validate is the same design-intent question this item already
asks; decide it once for all three invariants.
