---
id: 2026-09-10-applies-from-equality-participation-unpinned
title: applies_from's participation in Benchmark equality and hashing is pinned by nothing — declaring it compare=False leaves the whole suite green
status: open
importance: low
importance_why: The carry of the field is pinned by direct reads, so no requirement is unpinned; but two entries differing only in applies_from would compare equal, and the profile store's replace-by-key and the e2e whole-entry assertions lean on equality without saying so.
effort: S
kind: gap
area: athlete-benchmarks, src/fitdocs/benchmarks.py, tests/test_benchmarks.py
created: 2026-09-10
surfaced_by: /kiro-impl training-load (Amendment 4, task 7.1 review round 7)
pinned_at: 664960a
resume_command: "do: in tests/test_benchmarks.py add one assertion that Benchmark(..., applies_from=A) != Benchmark(..., applies_from=B) with every other field equal (and that their hashes differ), then confirm that `applies_from: date | None = field(default=None, compare=False)` reds it"
context:
  - src/fitdocs/benchmarks.py
  - tests/test_benchmarks.py
  - .kiro/specs/athlete-benchmarks/design.md
blocked_by: []
---

## What

`Benchmark` is a frozen dataclass; `applies_from` was added as a plain
field, so it participates in `__eq__` and `__hash__`. The round-7 reviewer
of task 7.1 changed it to `field(default=None, compare=False)` and the full
suite stayed green: every test that reads the field does so by direct
attribute access, and the whole-entry `==` assertions compare against
entries that also match on every other field.

## Why it matters

Nothing observable breaks today. But `AthleteProfile.with_benchmark`
replaces by `(discipline, kind, measured_on)` and the e2e module asserts
whole-entry equality; if a later change relies on two entries differing only
in `applies_from` being *unequal* (a set of entries, a dedupe, a diff), the
suite will not notice a `compare=False` that sneaks in with Phase 6's
`source` field work on the same dataclass.

## Evidence

- 7.1 review round 7, finding 1 (Opus reviewer, 2026-09-10): mutation
  `applies_from: date | None = field(default=None, compare=False)` → full
  suite green (3127 passed at the time).
- `src/fitdocs/benchmarks.py` `class Benchmark` — `applies_from: date | None
  = None`, no `field(...)` call.

## How to pick it up

1. Read `Benchmark` and `test_benchmark_applies_from_can_be_set_explicitly`
   in `tests/test_benchmarks.py`.
2. Add the inequality (and hash) assertion beside it; run the mutation.
3. Done: the `compare=False` mutation reds exactly that assertion.
