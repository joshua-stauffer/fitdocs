---
id: 2026-09-17-plan-resolution-coverage-partials-to-pin
title: Coverage partials feature validation left unpinned (corpus 1.6 shapes, never-prompt, three seam halves)
status: open
importance: low
importance_why: Every criterion has a named pin; these are the clauses pinned by a weaker rule or by one half of a seam.
effort: S
kind: gap
area: plan-resolution, tests/plans/test_corpus.py, tests/plans/test_boundary.py, tests/test_cli_reconcile.py, tests/plans/test_placement.py
created: 2026-09-17
surfaced_by: /kiro-validate-impl plan-resolution (coverage dimension)
pinned_at: fbba78b
resume_command: "do: add the five pins listed in .kiro/queue/2026-09-17-plan-resolution-coverage-partials-to-pin.md, each with its named mutation run through uv run pytest"
context:
  - tests/plans/test_corpus.py
  - tests/plans/test_boundary.py
  - tests/test_cli_reconcile.py
  - tests/plans/test_placement.py
  - tests/plans/fixtures/reconcile/full.toml
blocked_by: []
---

## What
1. Req 1.6: a fence-less `workouts/plain.md` and a permission-denied page (skip on Windows) beside a clean sibling — corpus-level pins (today delegated to `docio.read_frontmatter`).
2. Req 8.4 "never prompts": an AST scan of `src/fitdocs/plans/` for `input(`/`typer.prompt`/`typer.confirm`/`rich.prompt` beside `TestClockScan`.
3. The CLI missing-stem pins assert only the `stem ... not found` substring; pin the `override[0] (id w1):` prefix on real data.
4. No CLI/e2e fixture carries a Req 4.4 conflict (two overrides naming one stem) — add one and assert the report line.
5. `load_phrase`'s `unscored` branch on a FULFILLING bullet is pinned only via the unplanned listing; assert a matched-unscored planned page's section (`w2-wed` -> `w2-unscored-log` in the placement fixture).
6. `tests/plans/test_placement.py` `_CHOICE`/`_PROBLEM` hand-built fixtures state `'banister' (1 pages), 'threshold' (7 pages)` while the corpus now carries 2 and 8 (inert for placement; the problem golden's Methodology line states a count the page's corpus contradicts).
