---
id: 2026-09-17-plan-resolution-spec-prose-stale-after-implementation
title: plan-resolution design/tasks prose that implementation showed false or stale (nine sentences, one file list)
status: open
importance: low
importance_why: Each is a sentence a future implementer would trust; none affects the shipped code, but design Amendment 1 covers only the largest one.
effort: S
kind: docs
area: plan-resolution, .kiro/specs/plan-resolution/design.md, .kiro/specs/plan-resolution/tasks.md
created: 2026-09-17
surfaced_by: /kiro-impl plan-resolution (reviews of 1.1, 1.2, 3.1, 3.3; /kiro-validate-impl design dimension)
pinned_at: fbba78b
resume_command: "do: apply the nine corrections listed in .kiro/queue/2026-09-17-plan-resolution-spec-prose-stale-after-implementation.md to design.md and tasks.md as a docs commit; no criterion changes"
context:
  - .kiro/specs/plan-resolution/design.md
  - .kiro/specs/plan-resolution/tasks.md
  - tests/plans/test_boundary.py
blocked_by: []
---

## What
1. design § Cross-spec obligations item 6 (~L175): "Wave 1's boundary test pins `page.py`'s import *targets*, not names, so nothing there moves" — false: `tests/plans/test_boundary.py::TestContractImporters::test_each_contract_importer_binds_exactly_its_registered_names` pins from-import NAMES by equality (1.1 had to widen `_CONTRACT_FROM_IMPORT_NAMES["fitdocs.plans.page"]`).
2. design § HistoryRecordProtocol Implementation Notes: "`tests/history/test_series.py` unchanged and green" — tasks.md grants 1.2 one by-identity assertion there, and it was added (c23686f). Also no 1.2 Implementation Note records that append.
3. design cites `tests/test_contract.py:974` for the import guard and `:186-212` for the managed-key tests; the guard is at ~:1221 and the schema pin at ~:199-225.
4. design § Allowed Dependencies sketches `from fitdocs.history import ...` / `from fitdocs.load.settings import load_load_settings`; the exact-pair exemption map cannot admit a from-import, so the code imports the roots whole-module (Implementation Notes 2.3/2.4/3.1) — state the import form.
5. design § ReconcilePass: `Reconciler.blocks -> Mapping[...]`; code returns `dict[...]` (a fresh copy; compatible narrowing).
6. design § ConfinementRegistration / task 3.3: "the four typed test modules" — five (`test_placement.py` is 2.4's).
7. tasks.md "Shared source files" / "Wave-1 files this plan edits by exception" omit `tests/load/test_settings.py` (the licensed-callers guard widened to four passes in 3.1; the per-command `[load]` read count widened in 3.2) and the four wave-1 tests that stage the override's page (3.2) — design Amendment 1 records them; the lists should too.
8. design § Placement grammar table: the `Unplanned:` row shows only the plural sentence (shipped singular: `1 logged workout in this window matches no planned workout.`); the `Ambiguous:` line's "settle them" is plural for one id.
9. `_agrees`/`_after_table_lines`/`_block_lines`/`_split_section` now emit blank `""` entries between paragraph-level lines (validation fix fbba78b); the grammar table's "then"/"+" joins should say a blank line separates paragraph-level entries.

## How to pick it up
One docs commit on `main` (trivial class), each item checked against the file it names before editing.
