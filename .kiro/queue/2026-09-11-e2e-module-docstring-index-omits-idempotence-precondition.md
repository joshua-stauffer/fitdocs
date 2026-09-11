---
id: 2026-09-11-e2e-module-docstring-index-omits-idempotence-precondition
title: The effort-tags e2e module docstring index does not mention the idempotence test's precondition
status: open
importance: low
importance_why: The file's own index summarises a test as weaker than it now is, inconsistently with how the same docstring treats the load leg.
effort: S
kind: docs
area: tests/test_effort_tags_e2e.py
created: 2026-09-11
surfaced_by: review of queue item 2026-09-11-e2e-idempotence-test-passes-with-carry-dropped
pinned_at: 9942964
resume_command: "do: mention the tag precondition in the e2e module docstring's summary of the idempotence test"
context:
  - tests/test_effort_tags_e2e.py
blocked_by: []
---

## What

`tests/test_effort_tags_e2e.py`'s module docstring indexes what each test
covers. Line ~26 still summarises the idempotence test as "two consecutive
`regen` runs are byte-identical", with no mention of the tag precondition added
when `2026-09-11-e2e-idempotence-test-passes-with-carry-dropped` was closed.

The same docstring spells the analogous precondition out for the `load` leg at
lines ~20-23, so the file is internally inconsistent about the one thing that
distinguishes these tests from vacuous ones.

## Why it matters

The precondition is the whole point of both tests -- without it each passes on a
build that does nothing. A reader skimming the index sees one leg described as
precondition-guarded and the other not, and may reasonably conclude the
idempotence test is the weaker kind. That is precisely backwards now.

Genuinely low: the inline comment sits at the assertion, which is the better
location for someone who actually hits it. This is about the index being
consistent with itself.

## Evidence

`tests/test_effort_tags_e2e.py:14-32` read at `9942964`: the `load` leg's entry
states its precondition, the idempotence entry does not. The assertion it omits
is at `:372-375`.

## How to pick it up

1. Read lines 14-32 and the two tests they index.
2. Add a clause to the idempotence entry matching how the `load` leg's entry is
   worded -- the precondition is that the tag is present in the first
   regeneration's bytes, so byte-identity is not satisfiable by a build that
   drops every tag.
3. Prose only; no assertion changes. Confirm `uv run pytest tests/test_effort_tags_e2e.py`
   still passes and that you have not restated coverage the tests do not have.

Done looks like: the module docstring describes both legs' preconditions, or
neither, rather than one of two.
