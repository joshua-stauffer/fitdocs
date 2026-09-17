---
id: 2026-09-17-override-for-a-removed-row-claims-stems
title: An override dated before an amendment that removes its row still claims its stems from every live row
status: open
importance: medium
importance_why: A parser-valid plan can leave a logged workout unmatched-and-unplanned while a live same-day row reads not logged, with no problem reported -- a silent wrong page.
effort: S
kind: bug
area: plan-resolution design § Matcher (Claims), training-blocks check_overrides, src/fitdocs/plans/matching.py
created: 2026-09-17
surfaced_by: /kiro-impl plan-resolution (task 2.2 round-1 review)
pinned_at: fbba78b
resume_command: "do: decide whether an effective override whose row is absent from block.current.rows is ignored (with a problem naming it) or keeps claiming; pin it in tests/plans/test_matching.py and amend design § Matcher (Claims)"
context:
  - src/fitdocs/plans/matching.py
  - src/fitdocs/plans/model.py
  - .kiro/specs/plan-resolution/design.md
blocked_by: []
---

## What
`check_overrides` (training-blocks, `model.py:666-700`) validates an override
as of the override's date, so an override dated before a later amendment
that removes its row is valid; the row is absent from `block.current.rows`.
`match_rows` then treats the override as effective — its stems leave every
live row's candidate set — yet `claimed` excludes them (no current row is
overridden), so the stem becomes unmatched-and-unplanned while a live
same-day row goes NOT_LOGGED.

## Why it matters
The athlete sees a not-logged row beside a workout that was logged, and no
problem line explains why.

## Evidence
- 2.2 round-1 review scratch probe: `current ids ['w-b']`, `override ids ['w-a']`, `w-b` NOT_LOGGED with `same_day (('run-x', None),)`, `claimed frozenset()`.

## How to pick it up
1. Read `effective_overrides` and the claims step in `matching.py`; read `check_overrides` in `model.py`.
2. Choose: ignore overrides whose row is not current (report a `ReconcileProblem` naming the entry) — the safer reading. Pin both the claim and the problem.
