---
id: 2026-08-18-double-assertion-rule-absent-from-steering
title: change-protocol.md's Fixture Discrimination table has no anti-pattern for a test double that never took effect
status: open
importance: high
importance_why: Cost task 7.2 two review rounds and a debug escalation; every example in the table is about input data, so an agent applying it faithfully still ships the defect.
effort: S
kind: gap
area: .kiro/steering/change-protocol.md, encumbered-content-purge
created: 2026-08-18
surfaced_by: /kiro-impl encumbered-content-purge (task 7.2, debug pass)
pinned_at: c3d2201
resume_command: "do: add the double-assertion anti-pattern to .kiro/steering/change-protocol.md's Fixture Discrimination named-anti-pattern list -- a test that installs a double must assert the double is in effect via an observation the undoubled call could not produce -- and cite the task 7.2 instance as the worked example"
context:
  - .kiro/steering/change-protocol.md
  - .kiro/specs/encumbered-content-purge/tasks.md
blocked_by: []
---

## What

`.kiro/steering/change-protocol.md` › `## Fixture Discrimination` names ten
anti-patterns. Every one is about **input data** being pre-satisfied. None
covers the case where a test installs a **double** (`monkeypatch.setattr`,
a stub, a fake) and the assertion would hold identically if the double had
never applied.

The missing rule: *a test that installs a double must assert the double is in
effect, via an observation the undoubled call could not produce.* Capture the
unpatched result, assert the patched result differs, then assert the value.

## Why it matters

Three tests in task 7.2 monkeypatched `subprocess.run` and asserted
`_root_commit_ids(tmp_path) == ()` / `_commit_message(...) == ""` against a
`tmp_path` that was not a git repository -- where the **unpatched** call
returns exactly those values. All three passed. All three pinned nothing. An
ordinary `from subprocess import run` refactor silently defeated the guard
they existed to be, and the suite stayed green.

The reviewer that found it had to invent the defeat itself; the implementer
had applied the steering table faithfully and still shipped it, because the
table's examples do not reach doubles.

## Evidence

Reported and independently reproduced across two subagent rounds during task
7.2. The debug investigator measured the blast radius mechanically:
`monkeypatch` appeared in exactly three added tests, all three defective.
The fix shape (real repository + captured unpatched value + `assert got !=
unpatched`) was validated empirically before being prescribed: green on
correct code, red under the import-binding refactor.

Landed fix visible at `dac1a7a` in `tests/test_forbidden_strings_source.py` --
four tests now install a `subprocess.run` double and each asserts difference
from the unpatched result first.

## How to pick it up

Read `.kiro/steering/change-protocol.md` › `## Fixture Discrimination`, the
named-anti-pattern bullet list. Add one bullet in the same voice as its
neighbours. Use the task 7.2 instance as the worked example -- it is concrete,
measured, and already written up in
`.kiro/specs/encumbered-content-purge/tasks.md` › Implementation Notes.
Done means the bullet exists and names both the failure and the fix shape.
