---
id: 2026-09-10-kiro-impl-subagents-do-not-inherit-the-worktree
title: kiro-impl says implementer subagents "inherit this tree", but every subagent starts in the session's original directory (main), so the worktree ritual only works if each prompt carries the absolute worktree path and a cd prefix
status: open
importance: medium
importance_why: Followed literally, the skill sends every implementer and reviewer into a tree the change guard denies edits to; the run only progressed because the controller added a hand-written WORKTREE preamble to all twenty-two dispatches, and that preamble lives nowhere a future controller will find it.
effort: S
kind: inconsistency
area: .claude/skills/kiro-impl/SKILL.md, .claude/skills/kiro-impl/templates/implementer-prompt.md, .claude/skills/kiro-impl/templates/reviewer-prompt.md, .claude/skills/kiro-impl/templates/debugger-prompt.md
created: 2026-09-10
surfaced_by: /kiro-impl training-load (Amendment 4; twenty-two subagent dispatches into a worktree)
pinned_at: 664960a
resume_command: "do: under the change ritual (skills are non-trivial class), correct kiro-impl's Preflight 'implementer subagents inherit this tree' sentence and add a mandatory WORKTREE block to the three templates: the absolute worktree path, a cd prefix on every shell command, absolute paths for every file tool, and the no-destructive-git rule; validate by dispatching one implementer into a scratch worktree from a session rooted at main"
context:
  - .claude/skills/kiro-impl/SKILL.md
  - .claude/skills/kiro-impl/templates/implementer-prompt.md
  - .claude/skills/kiro-impl/templates/reviewer-prompt.md
  - .kiro/steering/change-protocol.md
  - .kiro/queue/2026-07-29-destructive-reset-reaches-implementers-nowhere.md
blocked_by: []
---

## What

`.claude/skills/kiro-impl/SKILL.md` § Preflight, "Confirm the worktree":
"implementer subagents inherit this tree, so starting on `main` puts every
task's commits on it". In this run the controller created the worktree and
worked from it, but the session's shell cwd reset to the original directory
(`/Users/josh/code/fitdocs_oss`, on `main`) after every tool call, and every
subagent started there too. A subagent that ran `uv run pytest` or edited
`src/...` by relative path would have acted on `main`, where the change guard
denies edits and commits. The three prompt templates say nothing about a
worktree.

## Why it matters

The change protocol's whole ritual rests on subagents working in the branch's
tree. Without an explicit path, an implementer either fails on the guard
(best case) or reports against the wrong tree. Twenty-two dispatches in this
run each carried a hand-written "WORKTREE — read this first" block (absolute
path, `cd` prefix on every command, absolute file paths, no destructive git);
none of that text is in the skill, so the next controller rediscovers it.

## Evidence

- `.claude/skills/kiro-impl/SKILL.md` — Preflight, "Confirm the worktree"
  paragraph ("implementer subagents inherit this tree").
- Every Bash tool result in this session ended with "Shell cwd was reset to
  /Users/josh/code/fitdocs_oss"; the change guard denied two `main`-rooted
  commands on 2026-09-10 (03:2xZ) with "Committing on main".
- Shared agent log, `2026-09-10T00:20:27Z impl-training-load-prompt-date
  NOTE`: "on this task every dispatch was into a WORKTREE while the session
  cwd is main — subagents need the absolute worktree path and a cd prefix on
  every command, or the change-guard denies their edits."
- The templates: `grep -n worktree .claude/skills/kiro-impl/templates/*.md`
  → no matches.

## How to pick it up

1. Read the Preflight paragraph and the three templates.
2. Replace the inheritance claim with the mechanism: the controller passes
   the absolute worktree path; templates carry a mandatory WORKTREE block
   (path, `cd` prefix, absolute paths, no `git checkout/restore/stash/reset/
   clean`, cp-and-restore for mutations). Fold in
   `2026-07-29-destructive-reset-reaches-implementers-nowhere` if convenient
   — same block, same templates.
3. Done: a dry run from a session rooted at `main` dispatches one
   implementer into a scratch worktree and its edits land there.
