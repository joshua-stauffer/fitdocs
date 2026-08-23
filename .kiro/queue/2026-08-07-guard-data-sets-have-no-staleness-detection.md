---
id: 2026-08-07-guard-data-sets-have-no-staleness-detection
title: Three guard data sets have no staleness or count detection, and one already opened a hole
status: open
importance: medium
importance_why: A stale exemption entry protects nothing and permits everything, and that exact failure shipped once already in this spec.
effort: S
kind: gap
area: encumbered-content-purge, tests/test_forbidden_strings.py, scripts/purge/sweep.py
created: 2026-08-07
surfaced_by: /kiro-impl encumbered-content-purge (tasks 4.4, 5.2, 5.4 reviews)
pinned_at: c3d2201
resume_command: "do: Add a reconciliation test that the standing guard's exemption table matches a live scan with no stale and no uncovered entries, and give the sweep's probe set a count anchor in its own module's tests."
context:
  - tests/test_forbidden_strings.py
  - scripts/purge/sweep.py
  - tests/purge/test_sweep.py
  - tests/purge/test_plan.py
blocked_by: []
---

## What

Three data sets that guards depend on have nothing detecting when they go
stale.

The standing guard's exemption table is reconciled against a live scan only by
an ad-hoc script a reviewer wrote; no repo test performs it. The sweep's
symbolic probe set has its **size** anchored only from a peer module's test
file, while its own module's test asserts non-emptiness alone. And the
inventory sample tuple is down to two entries with only a non-empty check
between it and vacuity.

## Why it matters

A stale exemption entry is worse than a missing guard: it protects nothing and
permits everything, silently. That failure shipped once already in this spec --
task 4.4's deletions left three exemption entries pointing at files that no
longer matched anything, so re-introducing the retired needle into precisely
the two files that task had just cleaned was silently exempt on every surface.
It was found by mutation, not by any test, and closing it was a one-fixture
change once someone looked.

The probe-set case has the same shape one module over: shrinking the sweep's
tuple reds exactly one test in the whole suite, and that test is in a different
module's file.

## Evidence

Task 4.4's reviewer measured the three stale entries and confirmed removing
them redded exactly one test. Task 5.4's reviewer reproduced the exemption
table's reconciliation in a throwaway script -- 24 entries against 24 real
triples, zero stale, zero uncovered -- and noted no repo test does it. Task
5.2's reviewer confirmed the probe set's only size guard lives in
`tests/purge/test_plan.py`.

## How to pick it up

Write the reconciliation as a real test: scan every tracked file, resolve each
hit to its exemption key, and assert the table and the live set match exactly
in both directions. Add a count anchor for the probe set in its own module's
tests. Decide whether the inventory sample's decay needs more than its
non-empty check now that two Major 4 tasks removed entries from it. Done when a
stale entry in any of the three reds something.

## Open questions

None.
