---
id: 2026-10-02-packaged-workouts-skill-unpinned-clauses
title: Three fitdocs-workouts skill clauses are unpinned -- the regen fence's exact command line, the Deferred row's "no action" against an appended re-run instruction, and the skill description against the README and wiki-integration summaries
status: open
importance: low
importance_why: The skill is executed by agents verbatim; each gap lets an edit change what an agent runs or is told with the suite green, but nothing is wrong today.
effort: S
kind: gap
area: distribution, connectors, src/fitdocs/skills/fitdocs-workouts/SKILL.md, tests/test_agent_skill.py, README.md, docs/wiki-integration.md
created: 2026-10-02
surfaced_by: /kiro-impl connectors (task 8.3, 8.4 reviews)
pinned_at: ad985b3
resume_command: "do: in tests/test_agent_skill.py pin the inbox skill's regen fence to the exact line `fitdocs regen`, assert the Deferred row's Do cell contains no re-run/retry imperative, and assert the README and docs/wiki-integration.md fitdocs-workouts summaries agree with the SKILL.md description (or derive them), each with a mutation that goes red"
context:
  - src/fitdocs/skills/fitdocs-workouts/SKILL.md
  - tests/test_agent_skill.py
  - README.md
  - docs/wiki-integration.md
  - .kiro/queue/2026-09-29-packaged-skill-silent-on-page-renames.md
blocked_by: []
---

## What
1. **Regen fence options.** The skill's second fence is `fitdocs regen`
   (`src/fitdocs/skills/fitdocs-workouts/SKILL.md:54-56`).
   `test_inbox_skill_regen_is_never_in_the_routine_fence`
   (`tests/test_agent_skill.py:950-965`) pins that the fence's command set
   is `{"regen"}`, but not its options: `fitdocs regen --out <x>` or any
   other real option passes. The routine fence, by contrast, is pinned to
   its exact literal lines (`:915-948`).
2. **Deferred row.** `tests/test_agent_skill.py:735-745` asserts the Deferred
   row's Do cell contains "No action -- it is reconsidered automatically" and
   not "delete"; a cell that appends "then re-run `fitdocs pull` immediately"
   still passes.
3. **Description vs summaries.** SKILL.md's frontmatter description (`:3`)
   and the summaries in `README.md:115-117` and
   `docs/wiki-integration.md:24-27` say the same thing in three wordings
   (e.g. "drains the inbox" vs "drains the fitdocs inbox"); no test relates
   them, so one can drift (as when connectors changed the skill from sync to
   pull).

The `--retry-quarantined` sentence, listed among these by the task 8.4
reviewer, is now pinned (`tests/test_agent_skill.py:681`, sentence-level),
so it is not part of this item.

## Why it matters
An agent runs fenced commands as written; an option slipped into the regen
fence would run on every upgrade. A "re-run immediately" instruction would
turn a rate-limit deferral into a retry loop against a service. The README
is what a human reads before installing the skill.

## Evidence
Lines read at `ad985b3`. Gaps reported by the connectors task 8.3/8.4
reviewers (8.4 implementer listed 2-3 as optional hardening it skipped); the
assertions cited were re-read here, no mutation re-run.

## How to pick it up
1. Read `tests/test_agent_skill.py:860-965` (fence helpers and pins) and
   `:715-760` (row pins).
2. Add: an exact-lines assertion for the regen fence; a negative assertion
   on the Deferred Do cell for `re-run`, `retry`, `again now`, `immediately`;
   a shared-key-phrase assertion (or exact equality, if the maintainer
   wants one canonical sentence) across the three summaries.
3. Done when each mutation (add `--out x` to the fence; append "re-run
   immediately" to the cell; reword the README summary) goes red.
