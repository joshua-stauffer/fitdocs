---
id: 2026-07-30-sole-failure-unreachable-in-scanned-modules
title: Sole-failure is unreachable for production mutations in the three literal-scanned modules, and no protocol document says so
status: open
importance: low
importance_why: The Fixture Discrimination gate asks for sole-failure evidence, but task 12.2's literal guard makes that impossible by construction for most mutations to three modules — so a correct mutation now looks like it violates the gate, and a reviewer or implementer will eventually "fix" a good guard to restore an unreachable property.
effort: S
kind: docs
area: .kiro/steering/change-protocol.md, .claude/skills/kiro-review, tests/metrics/test_constant_guard.py
created: 2026-07-30
surfaced_by: /kiro-impl fit-ingest (task 13.1 review)
pinned_at: 99f098c
resume_command: "do: add a note to change-protocol.md's Fixture Discrimination section (and kiro-review's mutation step) that the 12.2 literal guard reds as collateral on any line- or literal-shifting mutation to aggregates.py/power.py/stress.py, so sole-failure there means sole outside that guard [queue: .kiro/queue/2026-07-30-sole-failure-unreachable-in-scanned-modules.md]"
context:
  - .kiro/steering/change-protocol.md
  - .claude/skills/kiro-review/SKILL.md
  - tests/metrics/test_constant_guard.py
blocked_by: []
---

## What

`.kiro/steering/change-protocol.md` § Fixture Discrimination requires that a
mutation "red the assertion *you are pinning* and ideally nothing else", and
names **sole failure** as one of three properties the evidence must have.

Task 12.2 shipped `tests/metrics/test_constant_guard.py`, which pins every
numeric literal in `aggregates.py`, `power.py` and `stress.py` by
`(line, col_offset, value)`. Any mutation to those three modules that shifts a
line or changes a literal therefore reds the guard **as collateral**, on top of
whatever it was meant to red.

Sole failure is consequently unreachable by construction for most production
mutations in those modules. Only a mutation that preserves both line count and
every literal can achieve it.

## Why it matters

Low, because nothing is broken — the collateral red is the guard working
exactly as designed, and it is *more* discrimination, not less.

It matters because the gate now asks for something that cannot be produced,
and the documents do not say so. Two concrete ways that bites:

- **An implementer reports a mis-scoped claim.** Task 13.1's implementer
  reported one mutation as redding "exactly 4 tests and nothing else" when the
  true figure was 7, and another as "only the backstop test" when it was 3 —
  the extra failures were this guard, every time. The artifacts were correct;
  the reports were not.
- **The dangerous direction**: someone eventually reads the collateral red as
  evidence their mutation is wrong, or as a defect in the literal guard, and
  weakens a good guard to restore a property that was never achievable.

## Evidence

From the task 13.1 review at `99f098c`, four mutations to `power.py`, each run
through `uv run pytest` over the full suite:

| mutation | tests red | of which `test_constant_guard` |
|---|---|---|
| revert `_trailing_rolling_mean` to the partial-window body | 7 | 2 |
| delete `if not ra30: return None` | 3 | 2 |
| off-by-one: first complete window at `window` not `window - 1` | 5 | (collateral) |
| sliding-window subtraction off by one | 5 | (collateral) |

The one mutation that achieved a genuine suite-wide sole failure —
`if not values` weakening the short-series guard — did so precisely because it
preserved both line count and literals.

Reviewer's own framing: *"any production mutation to `aggregates.py`/`power.py`/
`stress.py` that shifts a line or a literal will red `test_constant_guard` as
collateral, so 'sole failure' is unreachable by construction for that class."*

## How to pick it up

1. Add a short paragraph to `.kiro/steering/change-protocol.md` § Fixture
   Discrimination, under the **Sole failure** bullet: name the three scanned
   modules, state that the literal guard reds as collateral on any line- or
   literal-shifting mutation there, and define the workable standard — *sole
   failure outside the line-pinned guard* — so a correct mutation is not read
   as violating the gate.
2. Mirror one sentence into `.claude/skills/kiro-review/SKILL.md`'s mutation
   step, since reviewers are the ones scoring sole-failure claims.
3. State the positive form too: a mutation that preserves line count and
   literals *can* still achieve true sole failure, and is the better choice
   when one is available — that is what makes the standard actionable rather
   than just an excuse.
4. Do **not** weaken `test_constant_guard.py` to reduce the collateral. The
   line/column keying is load-bearing; it is what closed the hole where a bare
   literal could hide behind a sibling exemption on the same line.

Done looks like: an implementer or reviewer meeting this collateral has a
document that tells them it is expected and what to report instead.
