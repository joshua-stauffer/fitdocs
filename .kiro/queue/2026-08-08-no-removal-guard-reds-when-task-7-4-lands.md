---
id: 2026-08-08-no-removal-guard-reds-when-task-7-4-lands
title: Task 5.5's no-removal guard contradicts task 7.4 by construction and will red the moment 7.4 lands
status: open
importance: medium
importance_why: 7.4's author will hit a red guard in their own boundary with no prior warning, and the obvious repair -- deleting the guard -- destroys the only standing proof that adopt.py cannot remove the source repository.
effort: S
kind: inconsistency
area: encumbered-content-purge, tests/purge/test_adopt.py, scripts/purge/adopt.py
created: 2026-08-08
surfaced_by: /kiro-impl encumbered-content-purge (task 5.5, debug escalation and rounds 3-5 review)
pinned_at: e40f6ec
resume_command: "do: Before implementing task 7.4 of encumbered-content-purge, read this item -- 7.4 must NARROW the pins in tests/purge/test_adopt.py so destruction exists but is gated on verification, and must not delete test_module_source_contains_no_directory_removal_call."
context:
  - tests/purge/test_adopt.py
  - scripts/purge/adopt.py
  - .kiro/specs/encumbered-content-purge/tasks.md
blocked_by: []
---

## What

Task 5.5's observable is "the tool has no code path that removes the source
directory". Task 7.4's, in the *same* `CloneAdoption` boundary and the same
module, is "Destroy the old repository directory" once verification passes.

These contradict at module level. Any faithful implementation of 5.5's
observable reds when 7.4 lands. This is not a mechanism weakness — no static
guard over `adopt.py` can be true of both tasks at once — and it was settled
deliberately rather than designed around.

## Why it matters

The failure arrives as a red test inside 7.4's own boundary, in a file 7.4 has
every reason to think it owns. The cheapest repair from that position is to
delete the guard, which would remove the only standing proof that the module
cannot destroy the source repository — the invariant that exists because, until
verification passes, the source is the only copy of anything.

The correct move is to **narrow** the pins: destruction exists, and is gated on
verification having passed. The guard's own failure message says so, but a
message is read after the surprise, not before.

## Evidence

Verified by simulation, three separate times during 5.5's review rounds:
appending `def destroy_source(repo: Path) -> None: shutil.rmtree(str(repo))` to
`scripts/purge/adopt.py` reds `test_module_source_contains_no_directory_removal_call`
with `['surface-attr:rmtree']`, and reds the arm-A vacuity controls whose
precondition it independently invalidates. Restored and re-confirmed green each
time.

The scope note is recorded in three places in the tree: `_removal_call_names`'s
docstring, `test_module_source_contains_no_directory_removal_call`'s docstring,
and the module-level comment block above the pins. The assertion's failure
message directs the reader to re-verify by hand and update the pin.

## How to pick it up

Read the pin block in `tests/purge/test_adopt.py` — `_PINNED_ATTRS`,
`_PINNED_FREE_NAMES`, `_PINNED_IMPORTS`, `_PINNED_RUN_ARGV_SHAPES`,
`_PINNED_MOVE_UNPARSE`, `_PINNED_RUN_CALL_COUNT`, `_PINNED_MOVE_CALL_COUNT`,
`_EFFECTFUL_ATTRS` — and the three-arm mechanism above it. Each pin has a
vacuity control proving it is load-bearing; keep that property.

Narrowing means the new destructive call is admitted *and* something asserts it
is unreachable unless verification passed. The pins are deliberately
location-blind (a verbatim relocation of a pinned call into another function
stays green), so a name-and-count pin alone will not express the gating — the
reachability condition needs its own assertion.

Done when 7.4's destruction is implemented, the guard still fails on a removal
that is *not* verification-gated, and every vacuity control still reds.

## Open questions

Whether the gating assertion belongs in the same static guard or in a runtime
test of the gate. 5.5's module is deliberately never executed — 7.2 builds the
clone, 7.4 wires the CLI — so 7.4 is the first task in this boundary that could
have a runtime test at all.
