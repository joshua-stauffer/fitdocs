---
id: 2026-09-17-hand-written-workout-page-fails-chained-load-pass
title: Any hand-written `type: workout` page makes `fitdocs sync`/`load` exit 1, while the plan-resolution corpus reads such pages by design
status: open
importance: medium
importance_why: Product scope includes hand-written strength pages (the maintainer keeps manual strength markdown); on a real root with one such page every sync and regen now ends in a per-document failure, and plan-resolution's e2e had to split its sync and synthetic-corpus scenarios to work around it.
effort: M
kind: bug
area: training-load, wiki-contract, src/fitdocs/load/engine.py, src/fitdocs/plans/corpus.py
created: 2026-09-17
surfaced_by: /kiro-impl plan-resolution (task 3.5 and /kiro-validate-impl integration dimension)
pinned_at: fbba78b
resume_command: "/kiro-spec-requirements training-load [queue: .kiro/queue/2026-09-17-hand-written-workout-page-fails-chained-load-pass.md] Decide how the load pass treats a workout document with no reserved load region (skip, warn, or fail) and pin it"
context:
  - src/fitdocs/load/engine.py
  - src/fitdocs/plans/corpus.py
  - tests/test_reconcile_e2e.py
  - .kiro/specs/plan-resolution/tasks.md
blocked_by: []
---

## What
`fitdocs load` (chained ahead of the reconciling pass on `sync` and `regen`)
scans every `type: workout` document under `workouts/` and fails any that
carries no reserved `load` region (`LoadDocError: document has no reserved
'load' region`); giving a hand-written page a placeholder region fails it
instead with `no archived source`. The command exits 1. `plans/corpus.py`
deliberately reads such pages as logged workouts (a hand-written strength
page is a valid corpus member), so the two passes disagree about what a
workout page is.

## Why it matters
An athlete who writes one strength page by hand — the product's own stated
scope — gets exit 1 from every `sync`/`regen` from then on. plan-resolution's
e2e (`tests/test_reconcile_e2e.py`) had to split "sync from a fixture" and
"a synthetic corpus" into two tests because an exit-0 `sync` over a
hand-written corpus is unreachable.

## Evidence
- `/kiro-validate-impl` integration run: `uv run fitdocs sync --no-prompt --out <scratch root>` over nine hand-written pages → 10 `LoadDocError` failures, exit 1, before the reconcile report.
- 3.5 reviewer probe: a single hand-written `_page()` under `workouts/` → `Failed: workouts/hand-page.md  LoadDocError: ...`, exit 1; with a placeholder region → `no archived source`.
- `src/fitdocs/load/engine.py:220-222` scans every `type: workout` doc.
- Implementation Note 3.5 in `.kiro/specs/plan-resolution/tasks.md`.

## How to pick it up
1. Read `src/fitdocs/load/engine.py`'s document qualification and training-load's requirements for the load pass (which documents it must score).
2. Decide: a workout document with no archived source and no load region is out of the load pass's scope (skip silently or with a note), not a failure. Pin with a test that stages a hand-written page beside a synced one and asserts `sync` exits 0 and the hand-written page is untouched.
3. Done looks like: `tests/test_reconcile_e2e.py`'s split can be reunited (one sync scenario over a synthetic corpus) — note that in the item's close.

## Open questions
- Should the load pass note the skipped page in its report, or stay silent?
