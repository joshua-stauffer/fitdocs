---
id: 2026-09-18-parser-accepts-amendment-with-zero-operations
title: parse_block accepts an `[[amendment]]` carrying no update/add/remove/mesocycle -- a dated, reasoned change that changes nothing
status: open
importance: low
importance_why: Harmless today; the skill had to say 'and any of' rather than 'one or more of' because the parser does not enforce it.
effort: S
kind: research
area: training-blocks, src/fitdocs/plans/source.py
created: 2026-09-18
surfaced_by: /kiro-impl build-training-block (reviewers, the recorded exercise, /kiro-validate-impl)
pinned_at: e45f114
resume_command: "do: decide whether an empty amendment is a validation error (PlanProblem) or an allowed no-op; if an error, add it in src/fitdocs/plans/source.py with a test in tests/plans/, and tighten SKILL.md's key table back to 'one or more of'"
context:
  - src/fitdocs/plans/source.py
  - .kiro/specs/training-blocks/design.md
  - src/fitdocs/skills/build-training-block/SKILL.md
blocked_by: []
---

## Evidence
2.1 round-1 review probe: `parse_block(header + '[[amendment]]\ndate = 2030-01-15\nreason = "x"\n', block_id=...)`
returns a Block with `amendments[0].changes == ()`; the training-blocks
grammar table (`.kiro/specs/training-blocks/design.md`, grammar section)
states no rule. `SKILL.md:155` was changed from "one or more of" to "and any
of" to stay truthful.

## How to pick it up
Read the grammar table and `source.py`'s amendment parsing; pick a rule;
either way make the skill's key table and the parser agree.
