---
id: 2026-10-13-dashboards-docs-omit-the-problem-code-list
title: The dashboard engine emits 38 stable problem codes and docs/dashboards.md lists none of them, though agents are told to parse the code
status: open
importance: low
importance_why: The JSON report's `code` is the machine-readable handle (docs call it stable); without a list an agent matches on message text or guesses, and a code rename has no documented contract to break.
effort: S
kind: docs
area: dashboards, docs/dashboards.md, src/fitdocs/skills/fitdocs-dashboards/SKILL.md, src/fitdocs/dashboards/problems.py
created: 2026-10-13
surfaced_by: /kiro-validate-impl dashboards (coverage dimension)
pinned_at: 0a98d5c
resume_command: "do: add a problem-code table (code, meaning, who fixes it) to docs/dashboards.md generated from or pinned against DashboardCode, link it from the packaged skill, and add a test that every DashboardCode value appears in the docs table [queue: .kiro/queue/2026-10-13-dashboards-docs-omit-the-problem-code-list.md]"
context:
  - src/fitdocs/dashboards/problems.py
  - docs/dashboards.md
  - src/fitdocs/skills/fitdocs-dashboards/SKILL.md
  - tests/dashboards/test_docs_dashboards.py
  - tests/dashboards/test_problems.py
blocked_by:
  - dashboards
---

## What
`DashboardCode` (`src/fitdocs/dashboards/problems.py:27-65`) has 38 values
(`location_foreign` through `write_failed`). `docs/dashboards.md` line 239 says
"Every problem carries a stable code" and explains the fields, but names no
code. The packaged skill mentions two (`index_unavailable`, `sql_changed`).

## Why it matters
The skill and guide are written for agents, and the JSON report is how they
read results. A stable code nobody can look up is a code agents cannot rely on.
It also leaves no written contract against which a rename in `problems.py` would
be a breaking change.

## Evidence
Run at 0a98d5c:

```
len(list(DashboardCode)) -> 38
codes whose value appears in docs/dashboards.md   -> []
codes whose value appears in the skill SKILL.md   -> ['index_unavailable', 'sql_changed']
```

The kit's own codes (`source: "chart"` problems) are separate and listed by the
kit (`ProblemCode`); the report passes them through (`docs/dashboards.md:244-246`).

## How to pick it up
1. Read `problems.py` and the report writer (`src/fitdocs/dashboards/report.py`) for each code's message and fix wording, and `docs/dashboards.md` lines 236-250 for where the table belongs.
2. Write the table (code, when it is raised, what to do). A short sentence each is enough; the engine's `fix` text already says what to do.
3. Add a docs test (see how `tests/dashboards/test_docs_dashboards.py` pins the live kinds block) asserting every `DashboardCode` value appears in the table and the table names no unknown code. Add one line to the skill pointing at the table.
