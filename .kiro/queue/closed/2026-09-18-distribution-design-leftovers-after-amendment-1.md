---
id: 2026-09-18-distribution-design-leftovers-after-amendment-1
title: distribution design.md still names the retired single-skill constant in three places, and the compatibility-note clause is undecided for the shared frontmatter contract
status: done
importance: low
importance_why: distribution 4.2's implementer reads these lines; two contradict Amendment 1 and one is a decision nobody has made.
effort: S
kind: docs
area: distribution, .kiro/specs/distribution/design.md
created: 2026-09-18
surfaced_by: /kiro-impl build-training-block (reviewers, the recorded exercise, /kiro-validate-impl)
pinned_at: e45f114
resume_command: "do: in .kiro/specs/distribution/design.md replace SKILL_NAME/'the constant' at :206, :503, :514, :524 (and the Unit Tests 'Skill frontmatter' bullet) with INBOX_SKILL_NAME/PACKAGED_SKILLS wording, and record whether 'a data root already configured' is part of every packaged skill's compatibility note"
context:
  - .kiro/specs/distribution/design.md
  - .kiro/specs/distribution/requirements.md
  - src/fitdocs/skills/build-training-block/SKILL.md
  - tests/test_agent_skill.py
blocked_by: []
---

## What
Task 3.3 appended Amendment 1 notes without rewriting blocks (by design), so
`.kiro/specs/distribution/design.md:206` (`SKILL_NAME` in the file tree),
`:503` ("the constant is what the conformance test asserts both against"),
`:514` (`SKILL_NAME: Final[str] = "fitdocs-workouts"`) and `:524`
("equals `SKILL_NAME`") still describe the retired single-skill locator.
Separately, the shipped `SKILL.md:5` compatibility note says "and a fitdocs
data root already configured", which Req 2.3 of build-training-block does not
require and `tests/test_agent_skill.py` pins only by the substring `fitdocs`;
distribution 4.2 must decide whether its inbox skill carries the clause.

## How to pick it up
Read Amendment 1's notes in that file first (grep `Amendment 1`), then fix
the four lines by content. Record the compatibility decision in the same
amendment block.

## Resolution (2026-09-18) -- done

Folded into distribution Amendment 2's design rewrite (`219e7bf`). The
AgentSkillLocator block shows the landed `PACKAGED_SKILLS` /
`INBOX_SKILL_NAME` / `skill_root(name)` shape; "the constant" is now "the
registry entry"; the AgentSkillPackage frontmatter bullet, its validation
note, the Skill-frontmatter data-model row and the unit-test bullet all say
"its `PACKAGED_SKILLS` entry" (closing script: no `SKILL_NAME: Final` and
no "equals `SKILL_NAME`" remain). The compatibility-note clause is decided
in the Skill-frontmatter table: the contract for every packaged skill is
"the `fitdocs` command must be installed and reachable"; a skill may add
clauses (`build-training-block` does); the inbox skill does **not** carry
"a data root already configured", because configuring the data root is
part of the workflow its body teaches (8.7).
