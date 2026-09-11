---
id: 2026-09-12-performance-benchmarks-minor-pin-gaps
title: Several performance-benchmarks test suites leave order, edge classification, or a second citation unpinned
status: open
importance: low
importance_why: Each gap is individually minor, but together they leave several behaviors free to change silently (unpinned ordering, an untested resolver edge, an incomplete citation-agreement check).
effort: S
kind: chore
area: performance-benchmarks tests
created: 2026-09-12
surfaced_by: /kiro-impl performance-benchmarks (adversarial reviews, 2026-09-11/12)
pinned_at: d4fbc6f
resume_command: "do: add the pinning assertions/tests listed below to the performance-benchmarks and training-load test suites"
context:
  - src/fitdocs/performance/engine.py
  - tests/performance/test_engine.py
  - tests/load/test_profile.py
  - tests/performance/test_derive.py
  - src/fitdocs/load/channels/sources.py
  - src/fitdocs/metrics/sources.py
blocked_by: []
---

## What

Five small pinning gaps surfaced across performance-benchmarks review
rounds:

- `DeriveReport.entries` order across multiple documents is unpinned
  (reversed order survives); needs one assertion once 4.4 renders in
  document order.
- `_resolve_pass_archive` edge classification (empty `sources` history →
  `archive_path(root, "")`; `is_file` vs `exists` on a directory-shaped
  `<sha>.fit`) is not covered by the two-resolver equivalence test.
- Pre-existing `save_profile` tests (`tests/load/test_profile.py` ~1191,
  ~1242) never observe that the pre-write re-parse precedes `mkstemp`, only
  that no temp file is left behind.
- `test_all_three_effort_kinds_are_used_for_lthr` iterates a hand-written
  `(RACE, TEST, HARD)` tuple rather than `EffortKind` itself; moot once the
  router's `assert_never` lands.
- Req 8.8's Coggan agreement test compares only against the channels
  `COGGAN_TSS` (`sources.py:127-129` in load-channels), not
  `src/fitdocs/metrics/sources.py:192`'s `coggan_2003`, a second shipped
  citation record.

## Why it matters

Each is a place where a green suite is not proof of the specific property
it looks like it proves — an ordering, an edge case, a timing relationship,
or one of two citation records.

## Evidence

- (4.2 r3 reviewer) "DeriveReport.entries order across multiple documents
  is unpinned (reversed survives); one assertion when 4.4 renders in
  document order."
- (4.2 r3 reviewer) "_resolve_pass_archive edge classification (empty
  sources history -> archive_path(root, ''); is_file vs exists on a
  directory-shaped <sha>.fit) not covered by the two-resolver equivalence
  test."
- (2.2 reviewer) "pre-existing save_profile tests (test_profile.py ~1191,
  ~1242) never observe that the pre-write re-parse precedes mkstemp, only
  that no temp file is left. training-load."
- (3.4 reviewer) "test_all_three_effort_kinds_are_used_for_lthr iterates a
  hand-written (RACE, TEST, HARD) tuple rather than EffortKind; moot once
  the router's assert_never lands."
- (1.2 r2 reviewer) "Req 8.8 test compares only against channels
  COGGAN_TSS; metrics/sources.py:192 coggan_2003 is a second shipped
  record, transitively pinned via tests/metrics."

## How to pick it up

1. Work through the five bullets independently; each is a separate small
   test addition/change in its own file.
2. For the `entries` order and `_resolve_pass_archive` items, add the
   assertion/test case named above to the relevant `tests/performance/`
   module.
3. For the `save_profile` and `EffortKind` items, extend the existing test
   rather than replace it. For Req 8.8, add a comparison against
   `metrics/sources.py:192`'s `coggan_2003` alongside the existing channels
   comparison.
</content>
