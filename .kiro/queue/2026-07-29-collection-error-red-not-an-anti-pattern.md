---
id: 2026-07-29-collection-error-red-not-an-anti-pattern
title: A mutation that breaks the environment reads as discrimination evidence, and the anti-pattern table does not name it
status: open
importance: medium
importance_why: The Fixture Discrimination gate accepts "I mutated X and the suite went red" as evidence. A mutation that uninstalls the package reds every run without the pinned assertion ever executing, so the gate's central artifact can be satisfied by a mutation that proves nothing. Observed once, and it passed the implementer's own self-check.
effort: S
kind: gap
area: steering, .kiro/steering/change-protocol.md, .claude/skills/kiro-impl/templates, .claude/skills/kiro-review
created: 2026-07-29
surfaced_by: adversarial review of the branch that added the sdist exclusion for the withdrawn methodology's tables (queue-top7 batch)
pinned_at: c3d2201
resume_command: "do: add a named anti-pattern to .kiro/steering/change-protocol.md § Fixture Discrimination for a mutation whose red is a collection/import error rather than the pinned assertion failing, and require the evidence to name WHICH assertion failed rather than only that the suite went red [queue: .kiro/queue/2026-07-29-collection-error-red-not-an-anti-pattern.md]"
context:
  - .kiro/steering/change-protocol.md
  - .claude/skills/kiro-impl/templates/implementer-prompt.md
  - .claude/skills/kiro-impl/templates/reviewer-prompt.md
  - .claude/skills/kiro-review/SKILL.md
  - tests/conftest.py
blocked_by: []
---

## What

`.kiro/steering/change-protocol.md` § Fixture Discrimination requires naming a
single-line production mutation, running it, and observing the assertion go
red. It does not require the observer to check **which** thing went red. A
mutation that breaks the interpreter or the environment — rather than the
behaviour under test — produces a red run in which the pinned assertion never
executes at all.

## Why it matters

The gate's whole output is claims of the form "mutation X reds assertion Y".
This failure shape produces a confident, evidence-backed claim that assertion Y
discriminates, when Y did not run. It is a sibling of the existing **vacuous
walk** and **stale bytecode** rows: all three are cases where evidence appears
to have been gathered but was not. The other two are already named; this one is
not, so a reviewer has no vocabulary to reject it with.

It survived the implementer's own reporting on a real task and was caught only
because an independent reviewer re-ran the mutation instead of reading the
claim.

## Evidence

On the branch that added the sdist exclusion for the withdrawn methodology's tables, the implementer reported as its positive
control: mutate `pyproject.toml`'s `packages = ["src/fitdocs"]` to a nonexistent
module, observe red, revert. That mutation uninstalls the project, so:

```
$ uv run pytest
ERROR tests/conftest.py:14 - ModuleNotFoundError: No module named 'fitdocs'
```

Zero tests collected. `tests/load/test_packaging.py:384-389` — the
archive-non-empty control it claimed to pin — never executed. The report
recorded it as confirmed discrimination evidence.

The property was real; the reviewer proved it properly by adding `"src/"` to
the sdist `exclude`, which keeps the build working and the archive non-empty
while producing sole failure on exactly that assertion with its intended
message. So the fix here is to the evidence standard, not to that test.

## How to pick it up

1. Read `.kiro/steering/change-protocol.md` § Fixture Discrimination, in
   particular the "Sole failure" property (~:168) and the **Named
   anti-patterns** table (~:185-197).
2. Add a row. Suggested shape — "**Collection-error red** — the mutation breaks
   the import, the environment, or the package install, so the suite reds
   without the pinned assertion running. A red that is a collection error is
   not evidence." Rule: the evidence must name the failing test and its
   assertion message, not merely that the suite went red.
3. The "Sole failure" bullet already asks for a mutation that reds the target
   "and ideally nothing else" — strengthen it to require that the target
   actually ran, since zero-collected is trivially "nothing else".
4. Every copy of the rule moves in the same change: the word list and the
   discrimination gate are restated in
   `.claude/skills/kiro-impl/templates/implementer-prompt.md`,
   `.claude/skills/kiro-impl/templates/reviewer-prompt.md` and
   `.claude/skills/kiro-review/SKILL.md`. Check each for the "observe it go
   red" wording.

## Open questions

Whether the reporting templates should require pasting the pytest summary line
(`N passed, M failed`) alongside each mutation claim — a collection error shows
up there unmistakably as `ERROR`/`0 passed`, which would make this class
self-evident without the reviewer needing to re-run it.
