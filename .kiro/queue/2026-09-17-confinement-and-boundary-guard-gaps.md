---
id: 2026-09-17-confinement-and-boundary-guard-gaps
title: Confinement negative-half filters miss non-document strays under history/ and fit-archive/; one confinement docstring is stale
status: open
importance: low
importance_why: A pass that wrote a dotfile under history/ or anything under fit-archive/ would pass tests/test_confinement.py; only the static write-shaped-name scan catches it today.
effort: S
kind: gap
area: plan-resolution, training-blocks, tests/test_confinement.py
created: 2026-09-17
surfaced_by: /kiro-impl plan-resolution (task 3.3 review)
pinned_at: fbba78b
resume_command: "do: in tests/test_confinement.py widen the plan and reconcile entries' history clause beyond .md, add a fit-archive clause, and fix test_entry_point_writes_only_inside_the_permitted_locations's docstring ('a workout document under workouts/ for every entry point but history' is stale since plan and reconcile)"
context:
  - tests/test_confinement.py
  - tests/plans/test_boundary.py
blocked_by: []
---

## Evidence
- 3.3 review: injecting `(data_root / "history" / ".reconcile").write_text(...)` and `(data_root / "fit-archive" / "stray.fit").write_text(...)` after `run_plan` in `reconcile.py` → confinement 19 passed; `tests/plans/test_boundary.py::TestNoSourceWrite::test_no_module_but_engine_spells_a_write_shaped_name` red.
- `tests/test_confinement.py` ~L882-889 docstring vs the `plan`/`reconcile` predicates.
