---
id: 2026-09-11-effort-tags-design-878-user-keys-stale
title: effort-tags design.md:878 prescribes USER_KEYS where the declaration binds EFFORT_KEYS
status: done
importance: low
importance_why: A later reader following the design literally would register a binding that reds the identity test; the correction lives only in tasks.md.
effort: S
kind: docs
area: .kiro/specs/effort-tags/design.md
created: 2026-09-11
surfaced_by: /kiro-impl effort-tags 5.1
pinned_at: d1147a0
resume_command: "do: correct .kiro/specs/effort-tags/design.md:876-878 to name EFFORT_KEYS, the binding the declaration module actually has"
context:
  - .kiro/specs/effort-tags/design.md
  - src/fitdocs/declaration.py
  - tests/test_contract_consumers.py
blocked_by: []
---

## What

`.kiro/specs/effort-tags/design.md:876-878` prescribes that
`CONTRACT_BINDINGS["fitdocs.declaration"]` gains `USER_KEYS`. The module binds
`EFFORT_KEYS` and has no `USER_KEYS` attribute at all -- design.md:789 itself
mandates that the declaration fragment render from `EFFORT_KEYS`, so the design
contradicts itself across two lines.

Task 5.1 registered `EFFORT_KEYS`, which is correct and was pre-commissioned by
`tasks.md`. The design line was not corrected in that change.

## Why it matters

The design document outlives the task list as the explanation of why the code is
shaped as it is. A later session reading design.md and following it literally
registers `USER_KEYS` and reds `test_converted_module_binds_the_contract_definitions_themselves[fitdocs.declaration]`,
then has to rediscover why. The correction currently exists only in an
Implementation Note near the bottom of `tasks.md`.

## Evidence

Executed at `e39b35f`: `hasattr(fitdocs.declaration, 'USER_KEYS')` -> `False`,
`hasattr(fitdocs.declaration, 'EFFORT_KEYS')` -> `True`. The RED-phase probe in
task 5.1 confirmed registering `USER_KEYS` fails with
`AssertionError: fitdocs.declaration does not use contract.USER_KEYS`.

`src/fitdocs/declaration.py:48-55` is the import block; `design.md:789` is the
line mandating `EFFORT_KEYS` as the fragment's source.

## How to pick it up

1. Read `design.md:876-879` alongside `design.md:789` -- the inconsistency is
   internal to the design, not between design and code.
2. Change the binding line to `EFFORT_KEYS` and say in one clause why, so the
   next reader does not "fix" it back.
3. Check whether any other spec's design copies the same prescription.

Done looks like: design.md names the binding the module has, and the two design
lines agree.
