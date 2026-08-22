---
id: 2026-07-27-plugin-api-enumeration-restaled-by-benchmarks
title: plugin-api's design public-surface enumeration omits the five benchmark exports, re-staled the day task 4.4 reconciled it
status: done
importance: medium
importance_why: The enumeration has now gone stale four times by the same mechanism; each spec that adds an export re-breaks it, and plugin-api task 4.4 just finished fixing the previous round.
effort: S
kind: inconsistency
area: plugin-api, .kiro/specs/plugin-api/design.md
created: 2026-07-27
surfaced_by: /kiro-validate-impl athlete-benchmarks (design/boundary dimension)
pinned_at: 32441af
resume_command: "do: add Benchmark, BenchmarkKind, BenchmarkRef, BenchmarkAge and benchmark_age to plugin-api design.md's public-surface enumeration (~lines 800-812) [queue: .kiro/queue/2026-07-27-plugin-api-enumeration-restaled-by-benchmarks.md]"
context:
  - .kiro/specs/plugin-api/design.md
  - .kiro/specs/athlete-benchmarks/design.md
  - src/fitdocs/load/__init__.py
  - docs/plugins.md
  - .kiro/queue/2026-07-27-design-md-enumeration-unguarded.md
blocked_by: []
---

## What

`athlete-benchmarks` added five names to `fitdocs.load.__all__` — `Benchmark`,
`BenchmarkKind`, `BenchmarkRef`, `BenchmarkAge`, `benchmark_age` (task 4.1,
Req 7.6). `.kiro/specs/plugin-api/design.md`'s public-surface enumeration
(~lines 800-812) still omits all five.

This spec's own `design.md` declares a revalidation trigger on
`ProfileView`/`AthleteField` naming "`threshold-load`, `plugin-api`'s published
surface, and `tests/test_public_api.py`". Two-thirds of that trigger was
discharged; the `plugin-api` design copy was not.

## Why it matters

`plugin-api` task 4.4 reconciled this very enumeration on 2026-07-27 — the same
day. Merging `athlete-benchmarks` re-stales it immediately, for the fourth time
by the same mechanism.

Note the asymmetry that makes this recur: `docs/plugins.md` is **mechanically
guarded** (`tests/test_docs_guarantees.py::test_every_fitdocs_load_export_appears_in_the_plugins_doc_surface_list`
reds if any export is missing, which is exactly how this spec's own omission was
caught during rebase), but `.kiro/specs/plugin-api/design.md`'s copy of the same
list is guarded by nothing. The guarded copy stays correct; the unguarded copy
drifts every time.

## Relationship to an existing item

`.kiro/queue/2026-07-27-design-md-enumeration-unguarded.md` predicts this exact
failure but attributes it to "the next export added by `threshold-load`".
Nothing records that it has now already happened, via `athlete-benchmarks`. That
item is the durable fix (guard the design enumeration, or stop duplicating the
list into design at all); this item is the concrete instance to close now.
Consider closing both together — fixing the instance without the guard just
schedules the fifth recurrence.

## Evidence

- `uv run python -c "import fitdocs.load as l; print(len(l.__all__))"` → **30**
  exports on this branch.
- `.kiro/specs/plugin-api/design.md` ~lines 800-812: enumeration lacks all five
  benchmark names.
- `docs/plugins.md` was updated on this branch (commit adding the benchmark
  vocabulary to the surface list) **because the guard forced it** — the design
  copy has no such forcing function.

## How to pick it up

1. Read `.kiro/specs/plugin-api/design.md` ~lines 800-812 and compare against
   `src/fitdocs/load/__all__`.
2. Add the five names, matching the surrounding entries' format.
3. Read `2026-07-27-design-md-enumeration-unguarded` and decide whether to close
   the recurrence permanently — either a test asserting the design enumeration
   matches `__all__`, or removing the duplicate list from design in favour of a
   pointer to `docs/plugins.md`, which is already guarded.

## Resolution

Closed 2026-07-29, merged to `main` as part of `5214c30` (commit `058f942`,
`spec(plugin-api): reconcile design.md's public-surface enumeration with the
five benchmark exports`).

`Benchmark`, `BenchmarkKind`, `BenchmarkRef`, `BenchmarkAge` and
`benchmark_age` were added to the enumeration at `design.md:800-812`. The
pre-fix failure was recorded as the discrimination evidence: with the new
guard in place and design.md still stale, the suite reds with
`AssertionError: plugin-api design.md's public-surface enumeration omits
exported name(s) ['Benchmark', 'BenchmarkAge', 'BenchmarkKind',
'BenchmarkRef', 'benchmark_age']` — exactly the five.

**The mechanism that re-staled this enumeration five times is now closed**,
which is the durable half: see
`.kiro/queue/closed/2026-07-27-design-md-enumeration-unguarded.md`. A sixth
recurrence would require deleting the guard, not merely forgetting the doc.

**Governance**: `tasks.md:291-294` reserves edits to `plugin-api/design.md`
to a task like 4.4, and this landed via queue items instead. Recorded as a
dated `2026-07-29` entry in `spec.json`'s `phase_note`, mirroring the
precedent task 4.4 itself set for additive corrections. Task 4.4's `RESOLVED
2026-07-27` note was left intact, with its one now-stale sentence ("the
`fitdocs` root list ... required no change") scoped in place to the date it
describes. Whether queue-driven design corrections should be formalised as
exempt, or need their own leaf task, is left to the maintainer.
