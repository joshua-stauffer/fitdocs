---
id: 2026-09-18-flags-py-verdict-literal-duplicates-training-load-vocabulary
title: flags.py defines a local Verdict Literal duplicating training-load's out-of-boundary three-value vocabulary, with nothing keeping the two in sync
status: open
importance: low
importance_why: mypy would catch a narrowing/rename on the training-load side (the assignment to QualityFlag.verdict would fail to type-check), so the risk is caught mechanically already -- this is a design-boundary tidiness note, not a live gap.
effort: S
kind: inconsistency
area: activity-qa-flags, src/fitdocs/load/qa/flags.py, src/fitdocs/load/types.py
created: 2026-09-18
surfaced_by: /kiro-impl activity-qa-flags feature-level validation pass (Finding G.5-extra)
pinned_at: d26b682
resume_command: "do: decide whether flags.py's local Verdict = Literal[...] alias (line 52) should import the verdict type from fitdocs.load.types instead of restating it, or leave it as a local alias with a comment naming QualityFlag.verdict as its source of truth; either way, add a test pinning the two literals equal so a future rename is caught by pytest, not only by mypy"
context:
  - src/fitdocs/load/qa/flags.py
  - src/fitdocs/load/types.py
  - .kiro/specs/activity-qa-flags/design.md
---

## What

`src/fitdocs/load/qa/flags.py:52` defines a module-local
`Verdict = Literal["detected", "not-detected", "not-assessed"]`. This exact
three-value vocabulary is `training-load`'s (`fitdocs.load.types.QualityFlag
.verdict`), and design.md's Out of Boundary list explicitly assigns
"`QualityFlag`'s three-value `verdict` vocabulary" to `training-load`, not
this feature. No test currently asserts the local alias and the upstream
type stay in sync.

## Why it matters

Low practical risk: every value assigned through `Verdict` ultimately flows
into a real `QualityFlag(verdict=...)` construction, so mypy already catches
the dangerous direction (a narrowing or rename on the `training-load` side
would fail type-checking here). This is a design-boundary cleanliness
question -- should a leaf module restate a sibling spec's vocabulary as a
local alias, even one mypy keeps honest -- not a live defect.

## Evidence

Verified at `d26b682`:
- `src/fitdocs/load/qa/flags.py:52`: `Verdict = Literal["detected",
  "not-detected", "not-assessed"]`
- `.kiro/specs/activity-qa-flags/design.md` Out of Boundary: "The
  `QualityFlag` type, its three-value `verdict` vocabulary... —
  `training-load`."
- No test in `tests/load/qa/test_flags.py` asserts `Verdict`'s members equal
  `QualityFlag.__annotations__["verdict"]`'s members.

## How to pick it up

1. Read `flags.py`'s use of `Verdict` (it's used as the outcome-mapping
   functions' return type).
2. Decide: keep it as a local alias with a comment naming
   `fitdocs.load.types.QualityFlag.verdict` as the source of truth, or
   import the type directly if a clean import path exists without creating
   an upward dependency the design forbids.
3. Either way, add a small runtime test asserting the two vocabularies'
   literal members are equal, so a future divergence reds a test rather
   than waiting for mypy.

Done looks like: the relationship between the two vocabularies is either
enforced at runtime or explicitly documented as mypy's job.

## Open questions

None.
