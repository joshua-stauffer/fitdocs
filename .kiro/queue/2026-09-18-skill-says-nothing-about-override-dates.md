---
id: 2026-09-18-skill-says-nothing-about-override-dates
title: SKILL.md states no rule for override dates and never says what an amendment/override `date` is relative to
status: open
importance: low
importance_why: An agent following the skill has to guess two things the tool has rules for; the recorded exercise agent guessed right, the next may not.
effort: S
kind: docs
area: build-training-block, src/fitdocs/skills/build-training-block/SKILL.md
created: 2026-09-18
surfaced_by: /kiro-impl build-training-block (reviewers, the recorded exercise, /kiro-validate-impl)
pinned_at: e45f114
resume_command: "do: read SKILL.md sections 6-7 and src/fitdocs/plans/source.py's override/amendment date handling; add one sentence each on (a) what `date` records (the day the decision was made, in the block's calendar) and (b) whether override dates are constrained; keep every 2.2 conformance pin green (uv run pytest tests/test_agent_skill.py)"
context:
  - src/fitdocs/skills/build-training-block/SKILL.md
  - src/fitdocs/plans/source.py
  - .kiro/specs/build-training-block/tasks.md
  - .kiro/specs/build-training-block/design.md
blocked_by: []
---

## What
`SKILL.md:209` gives amendments a rule ("Amendment dates must be non-decreasing")
but `SKILL.md:235` gives overrides only the tiebreak ("the latest one -- by
`date`, then by file position -- wins"). Neither section says what a `date`
on an amendment or override is relative to: the day the athlete decided, or
a date inside the block. The shipped example uses in-story 2030 dates.

## Why it matters
The skill's whole premise is that the agent never learns the tool by reading
a parser. Two guesses per settlement is two chances to write a source the
reconciler orders differently from what the athlete meant.

## Evidence
- `src/fitdocs/skills/build-training-block/SKILL.md:209` (amendment rule) vs `:235` (override tiebreak only).
- The recorded exercise (`.kiro/specs/build-training-block/tasks.md`, Implementation Notes 3.4) -- the walking agent's `SKILL_GAPS` named exactly these two, chose in-story dates by analogy with the example, and the tool accepted them.

## How to pick it up
1. Confirm in `src/fitdocs/plans/source.py` whether override dates are validated at all (the exercise suggests not) and what `effective_overrides` orders on.
2. Add the two sentences to sections 6/7 of `SKILL.md`; every command mention stays a code span; no owned path.
3. Done when `uv run pytest tests/test_agent_skill.py tests/test_skill_e2e.py -q` is green and the sentences are true of the parser.
