---
id: 2026-09-17-placement-wording-asymmetries-on-the-pages-and-report
title: Three athlete-facing wording asymmetries the placement grammar inherits verbatim from the design
status: open
importance: low
importance_why: Each reads wrong to an athlete but changes no decision; all three are design-level wording, so the fix is a grammar amendment plus goldens.
effort: S
kind: inconsistency
area: plan-resolution design § Placement / § ReconcilePass, load-history select_methodology, src/fitdocs/plans/placement.py, src/fitdocs/cli.py
created: 2026-09-17
surfaced_by: /kiro-validate-impl plan-resolution (integration dimension); task 2.4 and 3.2 reviews
pinned_at: fbba78b
resume_command: "do: amend design § Placement for the three items in .kiro/queue/2026-09-17-placement-wording-asymmetries-on-the-pages-and-report.md, then change placement.py/cli.py and regenerate tests/plans/golden/reconciled-*.md"
context:
  - src/fitdocs/plans/placement.py
  - src/fitdocs/cli.py
  - src/fitdocs/history/series.py
  - tests/plans/golden/reconciled-block.md
blocked_by: []
---

## What
1. A matched page scored under ANOTHER methodology reads `load 55` on the planned page (`_fulfilling_bullet` calls `load_phrase(w, None)` because `row_section` has no methodology parameter, design ~L1106) while the block page lists the same stem as `load 55 under other (excluded from the sum)`.
2. `Methodology: none chosen -- <detail>` reuses `MethodologyProblem.detail` verbatim on block pages and in sync/regen/plan output: "Pass --methodology, or set [history].methodology ..." — `--methodology` is a `fitdocs history` option those commands lack; and `actual_load_sentence`'s "(see Resolution below)" is printed on the CLI where there is no Resolution below.
3. The report prints `reconciled <id>: ...` for a BLOCKED block (the resolver ran before the write was refused) — design-conformant, but the word overstates.

## Evidence
- Validation scratch root (`/kiro-validate-impl` integration report): `b-tue` bullet vs block-page listing; `methodology: none chosen -- ... Pass --methodology ...` lines in `sync` output; `blocked plans/race.toml: blocks/race.md` followed by `reconciled race: 2 planned ...`.

## How to pick it up
Thread the methodology into `row_section` (or accept the asymmetry and say so in the design); give the CLI/plan-page a command-appropriate remedy sentence; print `resolved` (not `reconciled`) or skip the line for blocked blocks. Goldens move.
