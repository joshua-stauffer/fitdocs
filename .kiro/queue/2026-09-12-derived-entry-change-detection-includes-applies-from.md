---
id: 2026-09-12-derived-entry-change-detection-includes-applies-from
title: The derivation pass rewrites and reports written=True on every run once an athlete adds applies_from to a derived entry
status: open
importance: low
importance_why: Bytes stay identical (Req 6.5 holds) but the report's "Profile written: yes" and the file's mtime churn on every run for any athlete who used the sanctioned hand-annotation.
effort: S
kind: bug
area: performance-benchmarks, src/fitdocs/performance/engine.py
created: 2026-09-12
surfaced_by: /kiro-validate-impl performance-benchmarks (feature-level review, 2026-09-12)
pinned_at: 8644bcc
resume_command: "/kiro-impl performance-benchmarks [queue: .kiro/queue/2026-09-12-derived-entry-change-detection-includes-applies-from.md] compare the derived subset on the fields the pass owns, excluding applies_from"
context:
  - src/fitdocs/performance/engine.py
  - .kiro/specs/performance-benchmarks/design.md
  - tests/performance/test_engine.py
blocked_by: []
---

## What
`derive_benchmarks` decides "the derived subset changed" with
`frozenset(accepted) != previous_derived` over whole `Benchmark` values. The
design's cross-spec obligation 4 lets an athlete hand-add `applies_from` to a
derived entry, and the merge's inherit-on-absent rule preserves it on a
refresh -- but the freshly accepted candidate carries `applies_from=None`, so
the two sets differ on every run, `save_profile` is called and
`written=True` is reported while the bytes stay identical.

## Why it matters
"Profile written: yes" on every run is a false report for exactly the users
who followed the sanctioned annotation path; the profile's mtime churns
although nothing changed.

## Evidence
Feature-level reviewer's scratch probe on the rebased branch: a derived entry
given `applies_from` by hand, then two further runs -> `written: True` both
times, `bytes changed: False`. Source: `src/fitdocs/performance/engine.py`,
the reconciliation block (`frozenset(accepted) != previous_derived`).

## How to pick it up
1. Read the reconciliation block in `src/fitdocs/performance/engine.py` and
   `with_derived_benchmarks`'s overlay in `src/fitdocs/load/profile.py`.
2. Compare on the fields the pass owns (kind, discipline, value, measured_on,
   note, source) -- e.g. project both sets through `dataclasses.replace(...,
   applies_from=None)` before comparing.
3. Add a test in `tests/performance/test_engine.py`: derive once, hand-add
   `applies_from` via `with_benchmark`, run again -> `written is False` and
   bytes identical; run the mutation (compare whole values) and watch it red.
