---
id: 2026-07-29-aggregates-import-purity-unguarded
title: The metric modules' import-purity sentences are unguarded prose, and two false ones shipped into review in a single day
status: open
importance: high
importance_why: Nothing mechanical can catch a false import claim, and task 10.2 shipped one twice — the sentence ends in "only" and this amendment is adding an import to every metric module in turn.
effort: S
kind: gap
area: fit-ingest, tests/metrics/test_aggregates.py, tests/metrics/test_power.py
created: 2026-07-29
surfaced_by: /kiro-impl fit-ingest (task 10.1 review round 3; escalated by task 10.2 review rounds 1-2)
pinned_at: 4449d3e
resume_command: "/kiro-impl fit-ingest [queue: .kiro/queue/2026-07-29-aggregates-import-purity-unguarded.md] Add import-purity guards for aggregates.py and power.py mirroring test_stress.py's, asserting the docstring enumeration matches the real import set"
context:
  - src/fitdocs/metrics/aggregates.py
  - tests/metrics/test_stress.py
  - tests/metrics/test_aggregates.py
  - .kiro/specs/fit-ingest/design.md
blocked_by: []
---

## What

`src/fitdocs/metrics/aggregates.py`'s module docstring states it imports
`fitdocs.model`, `fitdocs.metrics.sources` and the standard library only —
never `fitdocs.ingest` or the FIT SDK. That is true today and nothing checks it.

`tests/metrics/test_stress.py:279` has exactly this guard for the sibling
module (`test_module_imports_only_model_and_stdlib`, asserting the set of
internal imports at `:292`). `tests/metrics/test_aggregates.py` has no
equivalent.

## Why it matters

The metrics layer sitting below the ingest layer is a structural claim the
design makes repeatedly, and it is the reason metric functions are pure and
testable without touching the FIT SDK. An unguarded claim of this kind does not
fail loudly when broken — a stray `from fitdocs.ingest import ...` added for
convenience during a later task would keep every test green while quietly
inverting the dependency direction.

Task 10.1 added a new internal import to this module (`fitdocs.metrics.sources`)
and updated the docstring to match. That is the moment the claim became easiest
to get wrong, and it is guarded by nothing.

## Evidence

At `4449d3e`:

- The claim: `src/fitdocs/metrics/aggregates.py` module docstring, the
  "imports ... only" paragraph.
- The sibling guard that does exist:
  `tests/metrics/test_stress.py:279` `test_module_imports_only_model_and_stdlib`,
  with `assert internal == {"fitdocs.model"}` at `:292`.
- `grep -n 'def test_module_imports_only\|def test_module_source_imports_only'
  tests/metrics/*.py` returns hits in `test_stress.py` and `test_sources.py`
  only — `test_aggregates.py` and `test_power.py` have none.

Reported by the task 10.1 reviewer subagent, re-verified here by the grep above.

**Escalated 2026-07-29, after task 10.2 hit it twice in one day.** This is no
longer a hypothetical gap; it is the root cause of two review rejections.

`power.py`'s equivalent sentence reads "This module imports `fitdocs.model`,
`fitdocs.metrics.aggregates` (intra-`metrics` reuse is allowed), and the
standard library **only** — never `fitdocs.ingest` or the FIT SDK." Task 10.2
added `from fitdocs.metrics import aggregates, sources` at `power.py:75` and did
not update the sentence, making it false. The implementer's own claim inventory
then verdicted it SUPPORTED, reasoning that the sentence "is about
`aggregates`/`ingest`/FIT SDK boundary, unaffected by `sources` import" — an
enumeration closed by "only" does not get to mean the narrower thing.

The 10.2 reviewer applied the *correction* as a probe — naming `sources` in the
sentence — and the suite stayed at **2204 passed**. Nothing in the tree can tell
these two apart, which is precisely why it must be a guard rather than a review
habit.

Note the two modules now disagree: task 10.1 fixed `aggregates.py`'s sentence to
name `fitdocs.metrics.sources` (`4449d3e`), while `power.py`'s still omits it.
Majors 10-13 add a `sources` import to `stress.py` next (task 10.3), so this
recurs once more unless a guard lands.

## How to pick it up

1. Read `tests/metrics/test_stress.py:279-297` — it is the working pattern, and
   copying it is the whole job.
2. Add the equivalent to `tests/metrics/test_aggregates.py` (permitted set:
   `fitdocs.model`, `fitdocs.metrics.sources`) and to `tests/metrics/test_power.py`
   (permitted set: `fitdocs.model`, `fitdocs.metrics.aggregates`,
   `fitdocs.metrics.sources`). Assert the docstring and the real import set agree,
   not merely that the SDK is absent — a guard that only forbids `fitdocs.ingest`
   would have passed on both false sentences.
3. While there, check `zones.py` and any other metric module for the same gap —
   the sweep is cheaper now than one module at a time, and task 10.3 adds a
   `sources` import to `stress.py`, whose guard at `test_stress.py:292` pins
   `{"fitdocs.model"}` and will red when it lands.
4. Verify by mutation: add a `fitdocs.ingest` import to the module under test
   and confirm the new guard reds; revert and confirm green. Per
   `.kiro/steering/change-protocol.md` § Fixture Discrimination, a guard whose
   mutation was not run is not done.

## Open questions

`tests/metrics/test_stress.py:292`'s assertion will need updating when task 10.3
re-points `stress.py` at its records — that is already noted in the fit-ingest
`tasks.md` Implementation Notes and is not this item's work, but a session doing
both at once should expect to touch that line.
