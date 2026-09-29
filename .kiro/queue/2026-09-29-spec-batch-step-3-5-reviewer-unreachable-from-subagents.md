---
id: 2026-09-29-spec-batch-step-3-5-reviewer-unreachable-from-subagents
title: kiro-spec-batch's per-spec writers cannot dispatch kiro-spec-tasks' Step 3.5 reviewer, and the skill does not carry the controller-mediated protocol that made the Phase 8 batch work
status: open
importance: medium
importance_why: Without the protocol every batch writer silently takes Step 3.5's in-context fallback, which CLAUDE.md calls a downgrade that must be stated, and the independent task-graph review is lost for every spec in the batch.
effort: S
kind: gap
area: .claude/skills/kiro-spec-batch/SKILL.md, .claude/skills/kiro-spec-tasks/SKILL.md, .claude/skills/kiro-spec-design/SKILL.md
created: 2026-09-29
surfaced_by: /kiro-spec-batch (Phase 8, controller)
pinned_at: f500dc1
resume_command: "do: under the change ritual (skills are non-trivial class), amend .claude/skills/kiro-spec-batch/SKILL.md Step 3's dispatch prompt and wave handling with the Phase 8 protocol -- each writer stops at kiro-spec-tasks Step 3.5 with its draft task plan in a scratch file and returns STEP_3_5_DRAFT_READY; the controller dispatches a fresh reviewer subagent, relays its verdict for one repair and one re-review, then lets the writer finish; research subagents from kiro-spec-design run in-context and the writer states that downgrade; each feature runs in its own worktree and branch merged into an integration branch after each wave -- and add to Step 4 that the cross-spec review runs on the integration branch; then dry-run or state what was inspected instead"
context:
  - .claude/skills/kiro-spec-batch/SKILL.md
  - .claude/skills/kiro-spec-tasks/SKILL.md
  - .claude/skills/kiro-spec-design/SKILL.md
  - .claude/agents/reviewer.md
  - .kiro/queue/2026-09-10-kiro-impl-subagents-do-not-inherit-the-worktree.md
  - .kiro/queue/2026-09-10-spec-batch-skill-rereads-log-once.md
blocked_by: []
---

## What
kiro-spec-batch Step 3 dispatches one subagent per feature with a prompt
that says to follow kiro-spec-tasks. kiro-spec-tasks Step 3.5 wants "one
fresh review subagent" and otherwise falls back to an in-context review. In
the Phase 8 run (2026-09-29) the per-spec writers had no Agent tool, so only
the controller could dispatch that reviewer; kiro-spec-design's parallel
research subagents were likewise unavailable. The controller made Step 3.5
work by protocol: each writer stopped at Step 3.5 with its draft in scratch
and returned `STEP_3_5_DRAFT_READY`; the controller dispatched a fresh
`reviewer`, relayed the verdict by SendMessage for one repair and one
re-review, and the writer finished. Research ran in-context as a stated
downgrade. Separately, per-feature worktrees (`../fitdocs-p8-<feature>`,
branch `chore/p8-<feature>`) merged into an integration branch
(`chore/p8-spec-batch`) after each wave let each writer commit and push per
phase. None of this is in the skill; its CLAIM template names per-feature
worktrees but the dispatch prompt never mentions a worktree, a commit or a
push.

## Why it matters
The next batch run following the skill as written loses the independent
task-graph review on every spec, and CLAUDE.md's "Invoking a skill that
prescribes subagent dispatch" rule says that fallback must be reported, not
taken silently.

## Evidence
- `.claude/skills/kiro-spec-batch/SKILL.md:61-83` -- Step 3 dispatch and
  prompt (no Step 3.5 handling, no worktree/commit/push);
  `:66` -- the CLAIM template naming per-feature worktrees.
- `.claude/skills/kiro-spec-tasks/SKILL.md:83-100` -- Step 3.5, fresh
  subagent or in-context fallback.
- `.claude/skills/kiro-spec-design/SKILL.md:68-77` -- parallel research
  subagents.
- Commits on `chore/p8-spec-batch`: `aae712d`, `2c752e5`, `98a7ca9` (wave 1)
  and `2d2bbbd`, `13e165a` (wave 2) each record their Step 3.5 rounds.
- Shared agent log, `2026-09-29T15:02:15Z spec-batch CLAIM` (per-feature
  worktrees and the integration branch) and `2026-09-29T19:18:26Z spec-batch
  RELEASE` ("Each passed an independent Step 3.5 reviewer in 2 rounds").
- The "no Agent tool in the writer subagents" observation is the
  controller's report of this run; whether it holds for every harness
  version is not established here.

## How to pick it up
1. Read kiro-spec-batch Steps 3-4, kiro-spec-tasks Step 3.5, and the two
   linked queue items (worktree inheritance; per-wave log re-read), which
   amend the same Step 3.
2. In a worktree, add the protocol to Step 3 (prompt text plus the
   controller's relay loop) and one line to Step 4; a writer that can
   dispatch runs Step 3.5 itself, and the in-context fallback stays only as
   a downgrade the run's report states.
3. Validate per change-protocol's skills row; done when the next batch's
   controller can run Step 3.5 from the skill text alone.
