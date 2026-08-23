---
id: 2026-08-07-vacuous-walk-in-load-engine-test
title: A loop in the load engine's tests executes zero iterations, so both assertions inside it cannot fail
status: open
importance: medium
importance_why: Two assertions read as coverage and pin nothing; the vacuity predates the purge and is invisible to a green suite.
effort: S
kind: bug
area: tests/load/test_engine.py
created: 2026-08-07
surfaced_by: /kiro-impl encumbered-content-purge (task 3.11 review)
pinned_at: c3d2201
resume_command: "do: Fix the zero-iteration loop in tests/load/test_engine.py's superseded-result test so its two assertions execute, then confirm each can fail by mutation."
context:
  - tests/load/test_engine.py
  - src/fitdocs/load/engine.py
  - .kiro/steering/change-protocol.md
blocked_by: []
---

## What

In `tests/load/test_engine.py`'s superseded-computed-result test, the loop that
iterates the report's computed, restored and unsupported entries executes **zero
times**. Both assertions inside it, including one checking that a recorded
identity does not leak into an entry's detail, therefore cannot fail under any
implementation.

## Why it matters

This is `change-protocol.md`'s named vacuous-walk anti-pattern. Two assertions
that look like coverage provide none, and the file reads as though the property
is pinned. It is pre-existing -- task 3.11 edited a line inside the loop but did
not create the vacuity -- so nothing in the purge introduced it and nothing in
the purge is required to fix it.

## Evidence

Task 3.11's reviewer instrumented the loop with a counter and observed
"LOOP ITERATIONS: 0", then reverted the instrumentation. The suite is green
with and without the assertions.

## How to pick it up

Read the test and work out why the three collections are all empty in that
scenario -- most likely the fixture's result is skipped rather than computed,
restored or unsupported. Either build a fixture that populates one of them, or
assert directly on the collection that the scenario actually fills. Add the
non-empty precondition the protocol requires for any walking assertion. Done
when a mutation to the entry-detail path reds the test.

## Open questions

Whether the scenario can populate any of the three collections at all. If it
structurally cannot, the two assertions belong on a different fixture and the
loop should be deleted rather than repaired.
