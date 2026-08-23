---
id: 2026-07-26-benchmark-region-roundtrip-untested
title: Nothing tests read-then-write idempotence over the wider grammar the benchmark parser accepts
status: open
importance: medium
importance_why: The three write-path defects that cost task 3.2 five rounds were all instances of this one missing property, and each was found only by a reviewer inventing the right hand-edited file.
effort: M
kind: gap
area: athlete-benchmarks, tests/test_benchmarks.py, tests/load/test_profile.py
created: 2026-07-26
surfaced_by: /kiro-impl athlete-benchmarks (task 3.2, rounds 2-3 review + debug pass)
pinned_at: c3d2201
resume_command: "/kiro-impl athlete-benchmarks [queue: .kiro/queue/2026-07-26-benchmark-region-roundtrip-untested.md] Add a parse->serialize->parse idempotence property test over hand-edited benchmark region variants"
context:
  - .kiro/specs/athlete-benchmarks/requirements.md
  - .kiro/specs/athlete-benchmarks/design.md
  - src/fitdocs/benchmarks.py
  - src/fitdocs/load/profile.py
  - tests/test_benchmarks.py
blocked_by: []
---

## What
`parse_benchmarks` accepts a strictly wider on-disk grammar than
`benchmarks_to_document` emits: case-variant scope tables, unrecognized
quantity tables, unrecognized keys inside an entry, `int` and `float` value
spellings, entries in any order, and both the inline-table-array and
array-of-tables TOML spellings. Nothing asserts that a document in that wider
grammar survives a read-then-write cycle — that parse → serialize → parse
yields the same entry set, and that a second cycle is a fixed point.

## Why it matters
Every defect that made task 3.2 take five review rounds and a debug pass was an
instance of this missing property:

- round 1: whole-region overwrite destroyed unrecognized quantity tables and
  unrecognized entry keys (Req 1.10 forward-compat data)
- round 2: a case-variant scope table was duplicated rather than folded, so
  `save_profile` wrote files `load_profile` could never read again
- round 4: the fold's non-list branch was last-spelling-wins, silently losing an
  unrecognized scalar carried under both spellings

Each was found by a reviewer constructing one specific hand-edited file. A
property test over the accepted grammar would have caught all three by
construction, and would bound the class rather than sampling it.

## Evidence
The defect set and its closure argument are recorded in this spec's `tasks.md`
Implementation Notes at `84e5e56` ("A parser that accepts a wider grammar than
its serializer emits makes merge-on-write unsafe by construction", and the
completeness argument over the parser's three key→identity resolution steps).

The debug pass established the bound: corruption requires the parser's
resolution to be non-injective; scope name → `Sport | None` is many-to-one
(case-insensitive), while kind name → `BenchmarkKind` and `measured_on` → `date`
are exact. That gives the property test its axis list directly.

Today's coverage is example-based and lives in
`tests/load/test_profile.py` — added defect by defect as each was found.

## How to pick it up
Read `src/fitdocs/benchmarks.py` (`parse_benchmarks`, `_resolve_scope`,
`_validate_value`, `_validate_measured_on`, `benchmarks_to_document`) and list
the axes on which the accepted grammar is wider than the emitted one. The debug
pass's enumeration is reproduced in `tasks.md`'s Implementation Notes and is a
good starting list; treat it as a hypothesis to re-derive, not a given.

Then write a test that, for each variant, asserts: `parse(serialize(parse(doc)))`
has the same entry set as `parse(doc)`, and that serializing twice is a fixed
point. Drive at least one variant through the *store* as well
(`load_profile` → `with_benchmark` → `save_profile` → `load_profile`), since
that is the path where the merge lives.

Done when: the three historical defects above are each caught by the property
test with the example-based tests deleted — verify by reverting each fix in turn
(they are all in `src/fitdocs/load/profile.py` at `84e5e56`) and watching the
property test red. Keep the example tests; the point is that the property would
have caught them unaided.

## Open questions
Whether to use a property-testing library (none is currently a dependency) or a
hand-written table of variants. A table is probably enough — the axis list is
short and bounded by the argument above.
