---
id: 2026-10-13-packaging-skill-listing-test-name-counts-skills
title: test_installed_tool_skill_lists_both_packaged_skills is named and described for two skills while four are registered
status: open
importance: low
importance_why: Name and prose only; the assertion iterates the registry, so behaviour is right, but the name has been stale since the third skill landed and a reader trusts it.
effort: S
kind: chore
area: distribution, tests/test_packaging.py
created: 2026-10-13
surfaced_by: /kiro-impl dashboards (task 7.1 reviewer)
pinned_at: 0a98d5c
resume_command: "do: rename test_installed_tool_skill_lists_both_packaged_skills in tests/test_packaging.py to name no count (for example ..._lists_every_packaged_skill) and fix its docstring, and grep tests for other 'both' / 'two skills' prose [queue: .kiro/queue/2026-10-13-packaging-skill-listing-test-name-counts-skills.md]"
context:
  - tests/test_packaging.py
  - src/fitdocs/agentskill.py
blocked_by: []
---

## What
`tests/test_packaging.py:877` defines `test_installed_tool_skill_lists_both_packaged_skills`.
`PACKAGED_SKILLS` (`src/fitdocs/agentskill.py:52-57`) holds four names on the
dashboards branch (`build-training-block`, the inbox skill, `fitdocs-analytics`,
`fitdocs-dashboards`); on `main` at 8ecc0f9 it holds three, so "both" was
already stale before dashboards.

## Why it matters
A name that says "both" tells a reader the test checks two skills; it checks
whatever the registry holds. It will be stale again at the next skill.

## Evidence
- `tests/test_packaging.py:877`: the function name; its docstring says "lists :data:`PACKAGED_SKILLS`, from the installed tool" and the assertion loops over `PACKAGED_SKILLS` (lines 883-891), so only the name is wrong.
- `src/fitdocs/agentskill.py:52-57` (four entries on the branch); `git show main:src/fitdocs/agentskill.py` header says "Three skills are registered today".
- `grep -n "both\|four\|three" tests/test_packaging.py` also shows prose that counts other things; check each when renaming.

## How to pick it up
1. Rename the test to carry no count and keep the body unchanged.
2. Search the other skill tests in `tests/test_packaging.py` (the `skill` command tests after line 894) for prose that names how many skills there are.
3. Run `uv run pytest tests/test_packaging.py -q -k skill`.
