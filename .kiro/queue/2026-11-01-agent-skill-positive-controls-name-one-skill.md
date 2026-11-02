---
id: 2026-11-01-agent-skill-positive-controls-name-one-skill
title: 'Agent-skill positive controls check absence in one ''other'' skill but four skills are packaged'
status: open
importance: low
importance_why: The control no longer proves the phrase is absent from the other packaged skills' bodies.
effort: S
kind: gap
area: tests/test_agent_skill.py
created: 2026-11-01
surfaced_by: /kiro-impl relay-server 8.6 review
pinned_at: 774a883c
resume_command: "/kiro-impl relay-server [queue: .kiro/queue/2026-11-01-agent-skill-positive-controls-name-one-skill.md] Run the positive controls against every other packaged skill"
context:
  - tests/test_agent_skill.py
  - src/fitdocs/skills
blocked_by: []
---

## What
Several tests assert a pinned phrase is absent from "the other packaged skill" (singular) as a positive control. fitdocs-analytics and fitdocs-dashboards are now packaged as well, so the control covers only build-training-block.

## Why it matters
A phrase that has leaked into boilerplate in the newer skills would still count as skill-specific.

## Evidence
- `tests/test_agent_skill.py:16`, `:970`, `:1007`, `:1045`, and the tests near `:1162` word the control as the other packaged skill.

## How to pick it up
1. List the packaged skill names (`ls src/fitdocs/skills`).
2. Loop each positive control over every other packaged skill body.
3. Update the docstrings.
