---
id: 2026-07-31-non-monotonic-time-unspecified-in-coverage-and-trimp
title: Non-monotonic time_s is silently skipped by both stream_coverage and trimp, and untested in either
status: open
importance: low
importance_why: >
  Not a live defect -- no shipped decoder is known to emit backwards
  timestamps. But two independent accumulators now carry the same unspecified
  guard, and a third (the pace channel's grade series, task 2.2) is about to
  reuse the same domain. If the guard is ever "simplified" away, both a
  derived metric and a load gate change silently, with every suite green.
effort: S
kind: gap
area: fitdocs.metrics.stress, fitdocs.load.channels.sufficiency
created: 2026-07-31
surfaced_by: /kiro-impl load-channels (task 1.3 adversarial review, rounds 1-3)
pinned_at: c3d2201
resume_command: "/kiro-impl fit-ingest [queue: .kiro/queue/2026-07-31-non-monotonic-time-unspecified-in-coverage-and-trimp.md] Specify and pin the non-monotonic time_s contract shared by trimp and stream_coverage"
context:
  - src/fitdocs/metrics/stress.py
  - src/fitdocs/load/channels/sufficiency.py
  - tests/load/channels/test_sufficiency.py
  - .kiro/specs/load-channels/design.md
blocked_by: []
---

## What

`fitdocs.load.channels.sufficiency.stream_coverage` accumulates coverage over
`dt = time_s[i + 1] - time_s[i]` and skips any interval where `dt <= 0`. The
shipped `fitdocs.metrics.stress.trimp` it deliberately mirrors does the same.
Neither requirement nor design states what should happen when `time_s` is
non-monotonic, and neither module's tests exercise it. The `dt <= 0` guard is
therefore load-bearing in production and invisible to both suites: deleting it
outright leaves every test green.

Note this is *not* the same as the zero-length-span case, which **is**
specified (load-channels Req 2.9) and pinned — a zero total span returns the
`TOO_SHORT` insufficiency. The unspecified case is a *negative* `dt` between
two consecutive samples, i.e. time running backwards mid-activity.

## Why it matters

Two accumulators in different layers now share an undocumented convention, and
a third is about to: load-channels task 2.2 derives per-interval gradients over
the same sample domain. "Skip the interval" is a defensible rule, but it is
currently a coincidence of implementation rather than a stated contract, so
nothing stops the three from diverging — one skipping, one taking `abs(dt)`,
one propagating a negative. A future editor removing the guard as dead code
would silently change both a rendered derived metric and a load-gating decision
with no test objecting.

Deciding the rule is cheap now and gets more expensive once three modules and a
regenerated golden set depend on whichever behaviour each happens to have.

## Evidence

- `src/fitdocs/metrics/stress.py:133-141` — documents the `dt > 0` /
  earlier-sample rule for TRIMP's accumulation domain.
- `src/fitdocs/load/channels/sufficiency.py:78-79` — the `if dt <= 0: continue`
  guard in `stream_coverage`.
- Mutation run by the task 1.3 reviewer, twice, through `uv run pytest`:
  dropping the non-positive `dt` guard leaves `tests/load` at **496 passed**.
  The full suite is likewise green (2350 passed at `b06256b`).
- Contrast: `total_s <= 0` → `total_s < 0` **does** red two tests
  (`test_single_sample_yields_no_measurement`,
  `test_zero_span_series_yields_no_measurement`), which is what shows the
  zero-span case is specified and pinned while the negative-`dt` case is not.

## How to pick it up

1. Read `src/fitdocs/metrics/stress.py:133-141` and
   `src/fitdocs/load/channels/sufficiency.py:60-92` together — the second was
   written to mirror the first, and the docstrings say so.
2. Decide the contract and write it down as a requirement, in whichever spec
   owns the accumulation domain: skip non-positive intervals (current
   behaviour, and the conservative choice), or reject the sample series as
   malformed. Do not leave it implicit in two places.
3. Pin it in both modules — a fixture with a backwards timestamp mid-series,
   asserting the stated outcome — and verify by deleting the `dt <= 0` guard
   and watching a test in *each* suite red. That mutation is the acceptance
   evidence; it currently kills nothing.
4. Done looks like: one stated rule, cited from both modules' docstrings, with
   a failing-on-mutation test on each side. Check whether load-channels task
   2.2's grade series (`src/fitdocs/load/channels/grade.py`) needs the same
   treatment when it lands.
