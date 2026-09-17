---
id: 2026-09-18-override-problems-two-shapes-report-vs-page
title: The CLI report prints override problems as bare indented lines while the block page prefixes them with `Problems:`
status: open
importance: low
importance_why: One fact, two shapes; the skill needed a two-clause sentence to describe it and an agent reading the report cannot grep for a header.
effort: S
kind: inconsistency
area: plan-resolution, src/fitdocs/cli.py, src/fitdocs/plans/placement.py
created: 2026-09-18
surfaced_by: /kiro-impl build-training-block (reviewers, the recorded exercise, /kiro-validate-impl)
pinned_at: e45f114
resume_command: "do: decide whether _report_reconcile should print a `Problems:` line before the indented problem lines (matching the page) and update SKILL.md:235 and tests/test_skill_e2e.py accordingly"
context:
  - src/fitdocs/cli.py
  - src/fitdocs/plans/placement.py
  - src/fitdocs/skills/build-training-block/SKILL.md
  - tests/test_skill_e2e.py
blocked_by: []
---

## Evidence
`src/fitdocs/plans/placement.py:467-469` (page header `Problems:`);
`src/fitdocs/cli.py:1579` prints `f"  {problem.describe()}"` with no header.
Observed in the recorded exercise (Implementation Notes 3.4): report line
`  override[2] (id w2-tue): stem ... not found ...` vs page `Problems:` + bullet.
