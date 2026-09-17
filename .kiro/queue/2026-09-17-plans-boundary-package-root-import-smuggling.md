---
id: 2026-09-17-plans-boundary-package-root-import-smuggling
title: The plans boundary test records `from fitdocs.plans import <sibling>` as the package root, so an upward import can slip through
status: open
importance: medium
importance_why: Any plans module already allowed `fitdocs.plans` (placement, via its page import) can import engine or reconcile through the package root without the equality pin noticing -- the cycle the design's import order exists to prevent.
effort: S
kind: gap
area: plan-resolution PackageBoundary, training-blocks, tests/plans/test_boundary.py
created: 2026-09-17
surfaced_by: /kiro-impl plan-resolution (task 2.4 round-2 review; task 3.3 review)
pinned_at: fbba78b
resume_command: "do: make _import_targets in tests/plans/test_boundary.py resolve `from fitdocs.plans import X` to fitdocs.plans.X when X is a submodule, add the smuggling probe as a synthetic control, and extend _threshold_import_closure the same way for non-fitdocs roots"
context:
  - tests/plans/test_boundary.py
  - src/fitdocs/plans/placement.py
blocked_by: []
---

## What
`_import_targets` (tests/plans/test_boundary.py ~L189-208) records
`from fitdocs.plans import engine` as target `fitdocs.plans`, so adding it to
`placement.py` leaves all boundary tests green, while `import
fitdocs.plans.engine` and `from fitdocs.plans.engine import run_plan` red the
equality pin. `_threshold_import_closure` (added by 3.3) has the same
limitation for `from <pkg> import <submodule>` under non-`fitdocs` roots.

## Evidence
- 2.4 round-2 review: mutation p2 (`from fitdocs.plans import engine` in placement.py) → 53 boundary tests passed; p3/p4 → 1 failed.
- 3.3 review: a `fitdocs/load/_zz_probe.py` importing `fitdocs.plans`, pulled via `from fitdocs.load import _zz_probe` in `threshold/selection.py` → closure test green, wave-1 reverse-reachability red.

## How to pick it up
1. In `_import_targets`, when a `from` import's module is a package and the imported name resolves to a submodule file, record `module.name`.
2. Add a synthetic control (the p2 shape) that must red; keep the existing alphabetical entries untouched.
