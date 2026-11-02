---
id: 2026-11-02-strava-publish-skill-text-connect-and-disconnect-statements-omit-strava
title: "Packaged fitdocs-workouts skill says connect asks for secrets at a terminal and disconnect revokes at a relay; Strava breaks both"
status: open
importance: low
importance_why: "Agent-facing prose; the prohibitions it states are still right, the reasons are partly wrong."
effort: S
kind: docs
area: "src/fitdocs/skills/fitdocs-workouts/SKILL.md"
created: 2026-11-02
surfaced_by: "/kiro-impl strava-publish 7.6 review"
pinned_at: 964cc419
resume_command: "do: reword the connect/disconnect lines of the packaged skill to cover browser consent and Strava revocation (strava-publish Req 17.8 forbade touching the skill, so this needs its own change with the skill's version/pin steps) (read .kiro/queue/2026-11-02-strava-publish-skill-text-connect-and-disconnect-statements-omit-strava.md first)"
context:
  - src/fitdocs/skills/fitdocs-workouts/SKILL.md
  - .kiro/specs/strava-publish/requirements.md
  - tests/test_agent_skill.py
blocked_by: []
---

## What
The skill says `fitdocs connect` "asks the athlete for secrets at a terminal" (false for Strava's browser consent) and that disconnect "for a relay instance first revokes the token at the relay" (Strava disconnect also revokes at Strava via the relay).

## Why it matters
Agents are told the wrong reason; the rule (never run connect/disconnect) stays correct.

## Evidence
`src/fitdocs/skills/fitdocs-workouts/SKILL.md:38-45` (read at HEAD).

## How to pick it up
Edit the lines, run tests/test_agent_skill.py and any packaged-resource pin; follow change-protocol for skill text (prose that instructs an agent is behavior).
