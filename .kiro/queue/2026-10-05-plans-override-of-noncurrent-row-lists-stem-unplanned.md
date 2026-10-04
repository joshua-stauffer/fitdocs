---
id: 2026-10-05-plans-override-of-noncurrent-row-lists-stem-unplanned
title: A workout claimed by an override whose row is no longer current is withheld from matching but may still be listed as unplanned
status: open
importance: low
importance_why: Unverified by a test; if real, a block page lists an overridden workout as unplanned after its row is removed from the plan.
effort: S
kind: research
area: plan-resolution, src/fitdocs/plans/matching.py
created: 2026-10-05
surfaced_by: /kiro-spec-batch phase 10 (analytics-derived research subagent; read by the controller, not reproduced)
pinned_at: 19fc92e
resume_command: "do: write a failing-or-passing test in tests/plans/ for an effective override naming a row id absent from block.current.rows; if the overridden stem shows up in the unplanned list, decide with plan-resolution's requirements whether that is intended, then fix or document"
context:
  - src/fitdocs/plans/matching.py
  - .kiro/specs/plan-resolution/requirements.md
  - .kiro/specs/plan-resolution/design.md
blocked_by: []
---

## What
In `match_rows` (`src/fitdocs/plans/matching.py:315-380`), `claimed_by_override`
comes from every effective override (`winners`), and those stems are removed
from every row's candidates (:329-336). But an override outcome is recorded
only for rows in `block.current.rows` (:322-325), and `claimed` is built from
`outcomes` alone (:376). An override whose row id is not current therefore
withholds its stem from matching without claiming it, so the stem could be
reported as unplanned.

## Why it matters
Unplanned-workout listings feed the block page and, after Phase 10,
`unplanned_pages` in the analytics index. A misreport there is silent.

## Evidence
- `matching.py:318-325` at 19fc92e: `winners = effective_overrides(block)`; outcomes only `for row in block.current.rows: if row.id in winners`.
- `matching.py:376`: `claimed = frozenset(stem for outcome in outcomes.values() for stem in outcome.stems)`.
- Not reproduced: `effective_overrides` may already drop overrides for non-current rows, which would make this a non-issue -- check it first.

## How to pick it up
1. Read `effective_overrides` and `_override_problems`; check whether a non-current row's override can be a winner at all.
2. If it can, write the test described in resume_command.
3. Close as `dropped` with the reason if it cannot.
