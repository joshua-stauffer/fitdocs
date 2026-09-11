---
id: 2026-09-12-kiro-impl-templates-scratch-namespace-and-cp-revert
title: kiro-impl implementer/reviewer templates should require per-task scratch namespacing and forbid git checkout as a revert
status: open
importance: medium
importance_why: On the parallel load-history run a reviewer's `git checkout -- <file>` deleted an implementer's uncommitted work in a sibling stream, and two reviewers clobbered each other's scratchpad/mut.sh; both cost a re-run and neither is mentioned in the templates.
effort: S
kind: docs
area: .claude/skills/kiro-impl/templates/reviewer-prompt.md, .claude/skills/kiro-impl/templates/implementer-prompt.md, .claude/skills/kiro-review/SKILL.md
created: 2026-09-12
surfaced_by: /kiro-impl load-history (controller, parallel streams)
pinned_at: 8cd0062
resume_command: "do: add to the reviewer template (and kiro-review § 5.5) that mutation scratch files are namespaced by task id under the scratchpad and that reverting a mutation is `cp` from a saved copy, never `git checkout`/`git stash`/`git restore`; add the scratch-namespace rule to the implementer template"
context:
  - .claude/skills/kiro-impl/templates/reviewer-prompt.md
  - .claude/skills/kiro-impl/templates/implementer-prompt.md
  - .claude/skills/kiro-review/SKILL.md
blocked_by: []
---

## What
Two incidents on 2026-09-11, both from reviewers running mutation tests
concurrently in different worktrees that share one scratchpad:
- A reviewer restored a mutated file with `git checkout -- path`, which also
  discarded the implementer's uncommitted edits to that file (the reviewer
  was in the same worktree as a still-open task). The controller re-ran the
  task.
- Two reviewers both wrote `scratchpad/mut.sh`; the second overwrote the
  first mid-run and one report cited the other's mutation output.

The controller worked around both by adding ad-hoc sentences to every later
prompt. The templates should carry the rule so a future controller does not
rediscover it.

## Evidence
Agent log WARN lines from `impl-load-history` on 2026-09-11; the
controller's notes at rounds 1.1 R2 and 4.3 R2.

## How to pick it up
Prose-only change to skill templates -- still worktree+branch per
change-protocol (skills are behavior). Verify by reading the templates back.
