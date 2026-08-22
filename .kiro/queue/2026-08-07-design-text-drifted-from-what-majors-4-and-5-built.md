---
id: 2026-08-07-design-text-drifted-from-what-majors-4-and-5-built
title: Four design statements no longer describe what Majors 4 and 5 built
status: open
importance: medium
importance_why: Later tasks are told to take forms and file names from the design, so a drifted statement propagates into the work rather than being caught by it.
effort: S
kind: inconsistency
area: encumbered-content-purge, .kiro/specs/encumbered-content-purge/design.md
created: 2026-08-07
surfaced_by: /kiro-impl encumbered-content-purge (tasks 4.2, 5.2, 5.4 reviews)
pinned_at: 7d49c84
resume_command: "do: Reconcile the four drifted design statements with what Majors 4 and 5 actually built -- the documentation guard's self-contradiction, the redaction plan's safe-to-retain claim, the Component-to-file map's omissions, and the provenance record's dangling citation."
context:
  - .kiro/specs/encumbered-content-purge/design.md
  - docs/reference/history-rewrites.md
  - tests/test_docs_guarantees.py
  - scripts/purge/plan.py
blocked_by: []
---

## What

Four statements in the approved design, each contradicted by the work that
implemented it.

The `ReintroductionGuards` section says the documentation guard "keeps its
content-absence assertion" and its rename table assigns that test a replacement
name, while the modified-files row and task 4.2 both delete it. The
implementation followed the task; the design still says both things.

The `RedactionPlan` section says the emitted path classification is "safe to
retain: identifiers and dispositions, not content" -- but an emitted path row
necessarily contains a removed path fragment, which is why the writer now
refuses an in-repository destination.

The Component-to-file map omits two modules task 4.4 was required to edit, and
named a test file that task 5.3 had to rename to match.

The provenance record cites "the value the packaging guard's own docstring
names"; after task 4.1 that docstring names no value.

## Why it matters

Every task in this spec is instructed to take vocabulary, file names and
component boundaries from the design. A drifted statement is not caught by that
instruction -- it is propagated by it. Two tasks in this run had to make a
declared deviation from the design and say so in their reports, which is the
right behaviour but should not be necessary four times.

## Evidence

Task 4.2's reviewer cited the three mutually inconsistent design locations for
the documentation guard. Task 5.2's reviewer measured a one-row emitted path
plan and found two forbidden-string hits in it. Task 5.3 renamed its test file
to match the map after the reviewer flagged the substitution. Task 4.1's
reviewer confirmed the docstring the provenance record cites now names no value.

## How to pick it up

Take the four in any order; none blocks another. For each, decide whether the
design or the implementation is right, and change the one that is wrong. The
documentation-guard one needs a real decision -- the other three are
corrections. Done when no task in Majors 6 to 8 has to declare a deviation for
these reasons.

## Open questions

Whether amending an approved design mid-implementation needs an approval flag
moved, or whether a declared in-place correction is sufficient. This plan's own
execution rules allow the latter and two tasks have already used it.
