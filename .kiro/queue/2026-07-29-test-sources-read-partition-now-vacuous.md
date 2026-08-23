---
id: 2026-07-29-test-sources-read-partition-now-vacuous
title: test_sources.py's module docstring still partitions the constant sync test into two cases that task 10.1 collapsed into one
status: open
importance: low
importance_why: Redundant rather than false — it describes a distinction that no longer exists, which costs a reader time and invites re-introducing the weaker of the two shapes.
effort: S
kind: docs
area: fit-ingest, tests/metrics/test_sources.py
created: 2026-07-29
surfaced_by: /kiro-impl fit-ingest (task 10.1, review round 3)
pinned_at: c3d2201
resume_command: "do: Simplify the tests/metrics/test_sources.py module docstring's description of the constant sync test, since all seven constants are now read the same way"
context:
  - tests/metrics/test_sources.py
  - src/fitdocs/metrics/aggregates.py
blocked_by: []
---

## What

`tests/metrics/test_sources.py`'s module docstring describes the
record-versus-module sync test as covering "seven against named constants, six
... directly, and the moving-time threshold against
`aggregates._MOVING_SPEED_THRESHOLD_MPS`".

That partition existed because the moving-time threshold was a bare literal
with no module constant to read, so its assertion had a different shape from
the other six. Task 10.1 promoted it, and all seven are now read the same way —
live, off a named module attribute. The distinction the sentence draws no
longer exists.

## Why it matters

Nothing is false and nothing is unpinned; the assertions themselves are correct
and were verified by mutation during task 10.1's review. The cost is a reader's
time, and a mild hazard: a docstring that singles out one constant as read
differently invites a later session to "restore" the special case, which would
mean reintroducing the hand-transcribed literal that task 10.1 removed. That
literal was a real hole — with it in place, deleting a test's module-state
restoration left the entire suite green.

## Evidence

At `4449d3e`:

- The docstring text sits at `tests/metrics/test_sources.py:33-38`.
- The seven reads it describes are at `:1382-1383`, `:1395-1397` and
  `:1409-1412`; all seven now compare against a module attribute, none against
  a transcribed number.

Reported by the task 10.1 reviewer subagent as a non-blocking residual, with
the line references above.

## How to pick it up

1. Open `tests/metrics/test_sources.py` and read the sync test the docstring
   describes before touching the docstring — the point is to make the prose
   match the assertions, not to guess from the prose.
2. Collapse the two-case description into one: all constants covered by the
   test are read live from their modules' named constants.
3. No test change is needed and none should be made. If you find yourself
   editing an assertion, stop — that is a different item.

## Open questions

None.
