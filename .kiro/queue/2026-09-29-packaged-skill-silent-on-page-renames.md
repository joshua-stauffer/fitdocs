---
id: 2026-09-29-packaged-skill-silent-on-page-renames
title: The packaged fitdocs-workouts skill tells agents a sync warning "usually needs nothing further" -- after activity-identity a rename warning means the wiki's links to the old page name are now broken
status: open
importance: low
importance_why: Base changes that rename a page are rare after the first adoption, but each one silently breaks every link to the page unless the agent that ran the sync fixes them; fitdocs deliberately does not.
effort: S
kind: gap
area: activity-identity, connectors, src/fitdocs/skills/fitdocs-workouts/SKILL.md
created: 2026-09-29
surfaced_by: /kiro-spec-batch (Phase 8, activity-identity writer)
pinned_at: f500dc1
resume_command: "do: once activity-identity has landed, add to src/fitdocs/skills/fitdocs-workouts/SKILL.md's report guidance that a rename warning (previous and new page path) means the agent should update every [[wikilink]] to the previous page name across the wiki, and keep the Warnings row's usually-nothing advice for the other warnings; run the tests that pin the skill text"
context:
  - src/fitdocs/skills/fitdocs-workouts/SKILL.md
  - .kiro/specs/activity-identity/requirements.md
  - .kiro/specs/connectors/tasks.md
  - tests/test_skill_locator.py
  - tests/test_wiki_integration_docs.py
blocked_by: [activity-identity]
---

## What
activity-identity renames a page when its base changes (Req 6.2), reports
each rename as a warning naming the previous and new paths (Req 6.5), and
states that fitdocs does not update links to the previous filename (Req 9.3;
non-goal "Rewriting the athlete's wiki links"). The packaged skill that
agents follow after a sync has no word on renames or links; its Warnings row
says "Read it; it usually needs nothing further."

## Why it matters
In a markdown PKM the page name is the link target. The agent running the
sync is the only party positioned to repair `[[...]]` links, and the skill
is how it learns what to do with the report.

## Evidence
- `src/fitdocs/skills/fitdocs-workouts/SKILL.md:67` -- the Warnings row;
  `grep -n -i "rename\|wikilink" src/fitdocs/skills/fitdocs-workouts/SKILL.md`
  -- no hits.
- `.kiro/specs/activity-identity/requirements.md:200` (6.2), `:203` (6.5),
  `:242` (links not updated); `design.md:53` (non-goal).
- `.kiro/specs/connectors/tasks.md` 8.4 (~:874) also edits this skill (the
  pull); coordinate so the two edits do not collide.

## How to pick it up
1. Read the skill's "Reading the report" section and the shipped rename
   warning text from activity-identity.
2. Add one short instruction (update links to the old name; never rename the
   page back) and name the warning's wording so the agent can recognise it.
3. Run the tests that pin the skill (`grep -rln fitdocs-workouts tests`).
   Done when an agent reading only the skill knows what a rename requires.
