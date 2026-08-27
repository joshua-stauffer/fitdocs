---
id: 2026-08-27-cast-drops-static-protocol-conformance
title: THRESHOLD_CALCULATOR's cast means mypy never structurally checks the shipped built-in against LoadCalculator
status: open
importance: medium
importance_why: The one calculator fitdocs ships is the one whose Protocol conformance is checked only at runtime, and a plugin author copying its frozen-dataclass shape hits an error the docs do not explain.
effort: M
kind: type-safety
area: training-load, threshold-load, src/fitdocs/load/types.py, src/fitdocs/load/threshold/calculator.py
created: 2026-08-27
surfaced_by: /kiro-validate-impl threshold-load
pinned_at: 3e14ab9
resume_command: "/kiro-impl training-load [queue: .kiro/queue/2026-08-27-cast-drops-static-protocol-conformance.md] Decide whether LoadCalculator's members should be read-only"
context:
  - src/fitdocs/load/types.py
  - src/fitdocs/load/threshold/calculator.py
  - docs/contributing-calculators.md
blocked_by: []
---

## What

`calculator.py:454` is
`THRESHOLD_CALCULATOR: Final[LoadCalculator] = cast(LoadCalculator, ThresholdCalculator())`.

Removing the cast fails `mypy --strict`:
`Protocol member LoadCalculator.calculator_id expected settable variable, got
read-only attribute`. Unfreezing the dataclass with the cast removed
type-checks clean, so the **sole** nonconformance is the frozen read-only rule;
every method, including the off-Protocol `supports`, conforms structurally.

The cast is genuine and correctly explained in the code — but its consequence
is that mypy never structurally verifies fitdocs' own built-in against the
Protocol it must satisfy.

## Why it matters

Two things design asserts are now untrue in a way nobody is told about:
`design.md:297-299` ("a frozen dataclass instance satisfies it with no
privilege a plugin author lacks") and `:1022` ("nothing a plugin author could
not write"). And `docs/contributing-calculators.md`'s `ExampleCalculator` uses
plain class attributes, so an author copying **fitdocs' own built-in shape** —
a frozen dataclass, which the codebase otherwise prefers — hits an error the
docs do not explain.

## Evidence

`3e14ab9`. Reproduced by the feature-level design validator: cast removed →
`expected settable variable, got read-only attribute`; cast removed **and**
`frozen=True` dropped → `Success: no issues found`.

## How to pick it up

The fix is upstream in `training-load`, which owns `LoadCalculator`: declare
the three attributes as read-only (`@property`, or `ReadOnly` where the Python
version allows) so a frozen dataclass conforms without a cast. Check the
installed plugin fixture and `docs/contributing-calculators.md`'s example
still conform. If the Protocol stays as-is, say so in
`contributing-calculators.md` and show the cast, so authors are not surprised.
