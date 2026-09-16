---
id: 2026-09-16-plans-engine-outcome-should-carry-the-block-page
title: BlockOutcome should expose the block page path so the CLI stops re-deriving it
status: open
importance: low
importance_why: The CLI couples to layout path composition only to count planned pages; harmless today, but a second consumer (plan-resolution's chained report) would copy the same recomputation.
effort: S
kind: chore
area: training-blocks, src/fitdocs/plans/engine.py, src/fitdocs/cli.py
created: 2026-09-16
surfaced_by: /kiro-impl training-blocks 4.3 (reviewer FOLLOW_UPS)
pinned_at: 68fe42e
resume_command: "do: add `block_page: str` (the report path) to BlockOutcome in src/fitdocs/plans/engine.py, have _report_plan count planned pages as written entries other than it, drop _report_plan's data_root parameter and the cli.py block_doc_path import; keep tests/test_cli_plan.py's counts green"
context:
  - src/fitdocs/plans/engine.py
  - src/fitdocs/cli.py
  - tests/test_cli_plan.py
  - .kiro/specs/training-blocks/design.md
blocked_by: []
---

## What
`BlockOutcome.written` lists the block page only when its bytes changed, so
`_report_plan` recomputes the block page's report path via
`layout.block_doc_path(data_root, outcome.block_id)` and filters it out of
`written` to print `(+n planned, -m removed)`. The engine already knows the
path; the outcome should carry it.

## Why it matters
Two modules now agree on the block page's location by convention rather than
by one being told by the other. plan-resolution chains the pass after sync,
drain and regen and prints the same report; it would inherit the recomputation.

## Evidence
- `src/fitdocs/cli.py:118` imports `block_doc_path`; `:1270`
  `block_page = block_doc_path(data_root, outcome.block_id)` inside
  `_report_plan`; its docstring (:1236) explains why.
- `src/fitdocs/plans/engine.py` `BlockOutcome` fields: source, block_id,
  status, written, removed, problems, foreign, failures -- no block page.
- `tests/test_cli_plan.py::test_second_run_planned_count_excludes_unwritten_block_page`
  pins the count semantics that the recomputation serves.

## How to pick it up
1. Read `BlockOutcome` and `_render_and_write` in engine.py; add the field
   where the outcome is built (all five statuses, including INVALID).
2. Update `_report_plan`; delete the `data_root` parameter and the import.
3. Done when `uv run pytest tests/test_cli_plan.py tests/plans/test_engine.py -q`
   is green and `grep -n block_doc_path src/fitdocs/cli.py` is empty. Record
   the field in design.md PlanEngine's Contracts block.
