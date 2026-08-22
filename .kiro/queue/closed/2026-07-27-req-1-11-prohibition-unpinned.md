---
id: 2026-07-27-req-1-11-prohibition-unpinned
title: Req 1.11's prohibition clause is unpinned suite-wide — a flat athlete-input key can be overridden from benchmarks with all 2012 tests green
status: done
importance: high
importance_why: The whole feature's safety story is that benchmarks never reinterpret the flat athlete inputs; an implementation that violates that passes the entire suite, so the guarantee is asserted in prose and enforced nowhere.
effort: S
kind: gap
area: athlete-benchmarks, src/fitdocs/athlete.py, tests/test_athlete.py
created: 2026-07-27
surfaced_by: /kiro-impl athlete-benchmarks (task 6.2 review, round 2, mutation N9b)
pinned_at: 24536f0
resume_command: "do: add the guard that reds when a flat athlete-input key is derived, overridden or reinterpreted from the [benchmarks] table [queue: .kiro/queue/2026-07-27-req-1-11-prohibition-unpinned.md]"
context:
  - .kiro/specs/athlete-benchmarks/requirements.md
  - src/fitdocs/athlete.py
  - tests/test_athlete.py
  - tests/load/test_absent_store_e2e.py
blocked_by: []
---

## What

Requirement 1.11 has two clauses: the flat athlete-input keys stay **readable
with unchanged meaning**, and they shall **not be derived, overridden or
reinterpreted from benchmarks**. The first clause is well covered. The second is
pinned by nothing in the repository.

No test anywhere writes an `athlete.toml` carrying *both* a flat athlete-input
key *and* a `[benchmarks]` table for the same quantity — which is the only fixture
shape on which the prohibition can be observed at all.

## Why it matters

This prohibition is the load-bearing safety property of the whole
`athlete-benchmarks` feature: benchmarks are additive history, and the flat keys a
user hand-wrote must keep meaning exactly what they said. An implementation that
quietly prefers a benchmark entry over the user's own flat value would change
rendered output for every document while the entire suite stays green — and the
divergence would be invisible until a user noticed a number they never entered.

Two separate task-6.2 review rounds cited existing tests as covering this clause.
Both citations were false, which is itself the argument for a real guard: the gap
is not obvious by reading, and reviewers keep filling it with tests that pin the
*readability* half instead.

## Evidence

Mutation **N9b** — make `load_athlete_inputs` derive the flat key from the store.
At `src/fitdocs/athlete.py:123`, replace
`max_hr_bpm=_optional_int(data, "max_hr_bpm", path)` with a read that prefers
`data["benchmarks"]["athlete"]["max_hr_bpm"][-1]["value"]` when present and falls
back to the flat key otherwise.

- Result: `uv run pytest` → **2012 passed**. The whole suite, including
  `tests/test_athlete.py::test_partial_file_maps_only_present_keys` and
  `tests/test_sync_e2e.py::test_athlete_file_present_renders_zone_strip_and_trimp_chip`,
  stays green.
- The mutation is **live, not inert**: a direct probe with an `athlete.toml`
  holding flat `max_hr_bpm = 188` plus
  `[[benchmarks.athlete.max_hr_bpm]] value = 200` returned **200** — the flat key
  overridden from benchmarks, exactly what 1.11 forbids.
- Root cause of the blind spot: neither cited test's fixture contains flat keys
  *and* a `benchmarks` table, so neither can redden on this clause.

## How to pick it up

1. Read Req 1.11 in `.kiro/specs/athlete-benchmarks/requirements.md` and confirm
   the two clauses are distinct — the guard is for the prohibition half only.
2. Add a test in `tests/test_athlete.py` whose fixture carries a flat
   `max_hr_bpm` **and** an athlete-scoped `max_hr_bpm` benchmark with a
   *different* value, asserting `load_athlete_inputs` returns the flat value.
   Pairwise-distinct values are essential — equal values make the mutation
   invisible (a **confounded fixture**, per `change-protocol.md`).
3. Verify with N9b above: the new test must red, and ideally as a sole failure.
   Restore from a scratch copy, never `git checkout`.
4. Done looks like: N9b reds at least one test, and no docstring claims the
   prohibition is pinned by a test that only covers readability.

## Resolution

Closed 2026-07-29, merged to `main` as `421c075` (branch
`chore/flat-key-prohibition-guards`, 5 commits, `--ff-only`, validated after
rebase: 2112 passed, ruff check + `ruff format --check` + mypy clean).
**Test-only — zero production changes.** Three adversarial review rounds.

Req 1.11 is now pinned across every axis the criterion names, not one:
`test_flat_key_not_overridden_or_reinterpreted_by_benchmark` (6 cases:
`ftp_watts`/`resting_hr_bpm`/`max_hr_bpm` × flat-lt-benchmark /
flat-gt-benchmark) and `test_absent_flat_key_is_not_derived_from_a_benchmark_of_the_same_quantity`
(3 cases). Both assert whole-`AthleteInputs` equality, so a derivation into
*any* field is caught, not just the one under test.

**The finding that justified the whole item**: a reviewer mutation made
`AthleteInputs.ftp_watts` return a fabricated `285.0` sourced from
`benchmarks.run.ftp_watts` where production correctly returns `None` — and
the path is already traversed green by
`tests/load/test_benchmark_selection_e2e.py::test_date_scoped_selection_end_to_end_across_a_hardware_change`.
That is the inverse of the harm this item described (not a user's value
overwritten, but a value the user never entered silently invented, unlocking
IF and TSS in rendered output) and it is the `CLAUDE.md` hard rule — absent
data is `None`, never a fabricated default — with nothing behind it.

**Two defects found and closed in review:**
1. Round 1 pinned one quantity via one verb while the docstring claimed all
   three verbs — seven reviewer mutations survived.
2. Round 2's parametrization fixed that but silently traded whole-dataclass
   equality for single-attribute assertions, **regressing zone-derivation
   coverage that had been red the round before**. Caught only by re-running
   the prior round's survivor list, which is now this batch's standard.

**Declared residual, verified structural**: `lthr_bpm` and
`threshold_pace_s_per_km` have no field in `AthleteInputs`
(`src/fitdocs/metrics/types.py:71-76`), so there is no reader-side path to
override — inapplicable for 1.11, and still covered on the 6.8 write side.
