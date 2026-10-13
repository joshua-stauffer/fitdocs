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

## Update 2026-10-13 (dashboards run, task 6.4 reviewer)

- The docstring this item already names has moved and is wider than plan and
  reconcile: `test_entry_point_writes_only_inside_the_permitted_locations`
  (`tests/test_confinement.py:1566`) now says, at `:1582-1583`, that
  `entry_point.non_vacuous` is "a workout document under `workouts/` for every
  entry point but `history`". At 0a98d5c, 16 entry points are registered
  and only four use the default `_wrote_a_workout_document` as their own proof
  (`sync`, `regen`, `load`, `drain`); the others use `_wrote_index_file`,
  `_wrote_document_and_index`, `_wrote_the_history_document`,
  `_wrote_only_the_athlete_profile`, `_wrote_a_block_page`,
  `_wrote_a_reconciled_block`, `_renamed_a_workout_document`,
  `_wrote_a_ledger_and_a_delivery`, `_derived_tables_populated` and the three
  dashboard predicates (`dashboard`, `dashboard-freeze`, `sync-with-dashboards`).
  Listing the registry (`[(e.id, e.non_vacuous.__name__) for e in WRITING_ENTRY_POINTS]`)
  gives the table. When fixing the docstring, say "each entry point's own
  `non_vacuous` predicate" rather than naming workout documents and exceptions.
- A separate gap in the same predicates (they count a deleted path as touched)
  is `2026-10-13-confinement-non-vacuity-predicates-count-deletions`.
