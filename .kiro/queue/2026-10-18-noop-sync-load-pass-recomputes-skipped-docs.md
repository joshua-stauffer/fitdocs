---
id: 2026-10-18-noop-sync-load-pass-recomputes-skipped-docs
title: A no-op `fitdocs sync` on the real corpus spends about a minute in the load pass re-attempting 1,403 documents that stay skipped
status: open
importance: medium
importance_why: Every routine sync pays the cost, and it grows with the corpus. The real 2,567-page wiki takes 70-82 s per sync with nothing new.
effort: M
kind: gap
area: training-load, load-history, src/fitdocs/load/engine.py
created: 2026-10-18
surfaced_by: /kiro-validate-impl workout-wellness (real-corpus scratch rebuild, profiling the second sync)
pinned_at: a0e4b92
resume_command: "do: profile a no-op sync's load pass on a large corpus and skip re-deriving documents whose skip reason and inputs are unchanged since the last run (or cache the per-doc decode), keeping skipped-doc reporting intact [queue: .kiro/queue/2026-10-18-noop-sync-load-pass-recomputes-skipped-docs.md]"
context:
  - src/fitdocs/load/engine.py
  - .kiro/specs/training-load/design.md
  - .kiro/specs/load-history/design.md
  - .kiro/queue/2026-10-16-heart-rate-session-peak-cache.md
blocked_by: []
---

## What

On a scratch copy of the maintainer's real data root (2,567 workout pages,
fully rebuilt: sync, regen, derive-benchmarks, `load --recompute`), the
results were:
- A second `fitdocs sync --no-prompt` with nothing new took **70.6 s** wall.
- The same sync with the 255 MB Apple export moved out of the inbox took
  **82.4 s**. So the export is not the cost.
- Under cProfile (190 s total), `load/engine.py:197 apply_load` accounted for
  173 s. That is 2,567 `_process_document` calls, of which **1,403** reached
  `_compute_document` (`engine.py:431`).
- The morning-of pass, measured standalone over the same 2,567 pages, took
  2.1 s.

The load table that run reported: Computed 0, Skipped 880. The skips are
mostly "no channel produced a load" on 598 pre-threshold pages and "missing
required inputs: Cycling LTHR" on 183.

## Why it matters

Each routine `sync`, inbox drain, `pull --sync` and `regen` re-attempts load
on every uncomputed page. That decodes `.fit` files whose outcome cannot have
changed: the inputs and benchmarks are the same. The cost is linear in
history and is paid on every run.

## Evidence

- The timings above, from the 2026-10-18 scratch rebuild (logs kept in that
  session's scratchpad, not in the repo).
- Profile lines: `fitdocs/load/engine.py:197(apply_load)` 173.3 s cumulative;
  `engine.py:320(_process_document)` 2567 calls / 168.9 s;
  `engine.py:431(_compute_document)` 1403 calls / 164.9 s.

Not established: whether hr-derivation's derived resting HR moved pages from
an early "missing required inputs: Resting heart rate" skip to a later,
decode-then-fail skip, which would make the cost newer. Measure that before
assuming a cause.

## How to pick it up

1. Reproduce on a synthetic corpus of a few hundred uncomputed pages, then
   time `fitdocs sync` with nothing new.
2. Find whether `_compute_document` decodes the `.fit` before it discovers
   the missing threshold/benchmark. If so, check the cheap preconditions
   first.
3. Consider recording an inputs fingerprint per skipped page, so an
   unchanged skip is not recomputed. Keep Req-level reporting of skipped docs.
