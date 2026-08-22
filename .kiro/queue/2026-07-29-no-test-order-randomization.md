---
id: 2026-07-29-no-test-order-randomization
title: Nothing in the suite can detect a test whose discrimination depends on the order of its neighbours
status: open
importance: medium
importance_why: An order-dependent assertion passes CI forever while pinning nothing, and this repo has now shipped one into review twice; the fixture-discrimination gate has no mechanical check for it.
effort: S
kind: gap
area: tooling, pyproject.toml, .kiro/steering/change-protocol.md
created: 2026-07-29
surfaced_by: /kiro-impl fit-ingest (task 10.1, review rounds 2-3)
pinned_at: 4449d3e
resume_command: "do: Evaluate adding a test-order randomization plugin (e.g. pytest-randomly) to the dev group and decide whether it runs by default or on demand; if adopted, name the order-dependence anti-pattern in change-protocol.md's table"
context:
  - pyproject.toml
  - .kiro/steering/change-protocol.md
  - tests/metrics/test_aggregates.py
blocked_by: []
---

## What

The project depends on `pytest` alone — no ordering or shuffling plugin is
installed. Test execution order is therefore file order, always, and a test
whose ability to fail depends on a *neighbouring* test having run first will
pass every run, in every environment, indefinitely.

`.kiro/steering/change-protocol.md`'s fixture-discrimination gate is built to
catch assertions that cannot fail, and its anti-pattern table names eight
shapes. Order-dependent discrimination is not one of them, and unlike the
others it cannot be found by the mandated apply-mutate-revert loop unless the
reviewer happens to also vary the selection.

## Why it matters

This is not hypothetical here. During task 10.1 an implementer closed a real
coverage hole with a test that reds under the target mutation in the full
suite, the file, the directory, and under `-k` — and **passes when selected
alone**, and **passes when a neighbouring test is reordered ahead of it**. It
was the sole catcher for that mutation, so the hole would have reopened
silently the first time someone moved or deleted the neighbour.

It was caught only because a reviewer was specifically asked to attack the
ordering assumption. Nothing in the repo's tooling would have surfaced it, and
the same shape has now appeared twice in this spec.

## Evidence

At `4449d3e`:

- Installed test tooling is `pytest` only; `-p no:randomly` is unavailable
  (unrecognized plugin), confirming no shuffling plugin is present.
- The rejected formulation, with the target mutation applied: selected alone →
  `1 passed` (vacuous); reordered as `[altitude, moving, restoration]` →
  `3 passed`; full suite → red. Same code, three different verdicts, decided
  entirely by selection.

Both observations were made by the task 10.1 reviewer subagent and are
reproducible from the commands in that round's report.

## How to pick it up

1. Decide the mechanism first — this is the real question, not the install.
   A randomizing plugin makes ordering bugs surface eventually but turns them
   into intermittent failures with a seed, which is its own cost in a repo that
   leans this hard on reproducible mutation evidence. A cheaper option is a
   documented reviewer step: for any assertion claimed as the sole catcher of a
   mutation, also run it selected alone.
2. If a plugin is adopted, add it to the dev group in `pyproject.toml` and
   decide explicitly whether it runs by default or behind a flag. Note the root
   `conftest.py` already does bytecode-cache purging; check the interaction.
3. Either way, add the anti-pattern to `.kiro/steering/change-protocol.md`'s
   table — "order-dependent discrimination: the assertion reds only because a
   neighbouring test ran first; run it selected alone" — since that table is
   what implementers and reviewers actually check against.
4. Done means: the shape is named in the protocol, and if a plugin landed, a
   deliberately order-dependent test is shown to fail under it.

## Open questions

Whether randomization runs by default is a maintainer call: it trades
reproducibility for detection, and this repo's review process is unusually
dependent on a mutation producing the same result twice.
