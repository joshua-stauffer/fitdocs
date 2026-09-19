---
id: 2026-09-19-wheel-required-skills-not-derived-from-registry
title: [wheel].required's SKILL.md entries and their test fixture are literal lists, not bound to agentskill.PACKAGED_SKILLS
status: open
importance: low
importance_why: A third registered skill with no policy entry would ship unrequired; today both lists agree.
effort: S
kind: gap
area: distribution, release/artifact-policy.toml, tests/test_release_artifacts.py, src/fitdocs/agentskill.py
created: 2026-09-19
surfaced_by: /kiro-impl distribution (reviewers, /kiro-validate-impl)
pinned_at: b29bde8
resume_command: "do: add one test deriving the expected `fitdocs/skills/<name>/SKILL.md` set from fitdocs.agentskill.PACKAGED_SKILLS and asserting it is a subset of the policy's [wheel].required"
context:
  - release/artifact-policy.toml
  - src/fitdocs/agentskill.py
  - tests/test_release_artifacts.py
blocked_by: []
---

## What
The registry, the policy and tests/test_release_artifacts.py:~143-152 each name the two skills by hand.

## Why it matters
The seam between the skill registry (4.1/4.2) and the artifact gate (1.4) is held together by three copies of the same list.

## Evidence
Validation integration report seam 4 / finding 6 (2026-09-19).

## How to pick it up
One test; mutation: append a fake name to PACKAGED_SKILLS in a scratch run and confirm it reds. Done when the test exists and is green.
