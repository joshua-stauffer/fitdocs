---
id: 2026-07-26-change-guard-blocks-documented-lifecycle
title: change-guard blocks commits from the worktree lifecycle its own steering doc prescribes
status: done
importance: high
importance_why: Every session that followed change-protocol.md's documented `cd ../fitdocs-<slug>` lifecycle was blocked from committing, and the block message told it to create the worktree it was already in.
effort: S
kind: bug
area: .claude/hooks/change-guard.py, .kiro/steering/change-protocol.md
created: 2026-07-26
closed: 2026-07-26
surfaced_by: chore/queue-resume — hit twice while committing inside a worktree
pinned_at: 36cfcaa
resume_command: "do: none — fixed on chore/change-guard-cd"
context:
  - .claude/hooks/change-guard.py
  - .kiro/steering/change-protocol.md
blocked_by: []
---

## What

The PreToolUse branch resolved a commit's tree from `git -C` or, failing that,
the session's `cwd`. The Bash tool resets cwd between calls, so a session
working in a linked worktree still reported the **main** tree — and
`cd ../fitdocs-<slug> && git commit`, the lifecycle `change-protocol.md`
prescribes, was judged against `main` and denied.

The report was accurate in every particular, including that the Write/Edit
branch was already correct and only the Bash branch had the gap.

## Resolution

`commit_tree()` now reads the command text the way the shell would: a leading
`cd`/`pushd` moves the base, a following `git -C` resolves against that base,
and only then does the session's cwd apply as a fallback. Shell-expanded
targets (`-C $W`, backticks, globs) cannot be resolved from text, so they are
no longer silently treated as cwd — the deny message names the unresolvable
token and says which tree was judged instead.

The second defect in the report is fixed too: the block message now states
that the trivial marker must be created in its own tool call, because
PreToolUse evaluates a command before any of it runs — so the `touch && git
commit` one-liner the old message invited was always denied.
`change-protocol.md`'s Enforcement section records both behaviors.

Ten synthetic cases cover the lifecycle specifically — absolute, relative,
quoted and `pushd` forms, a multi-step `cd … && git add && git commit`, `cd`
into a tree that is itself on `main` (still denied), `cd .` on main (denied),
`cd` then `git -C .`, and both shell-expanded `-C` cases. Suite: 43/43.

## Note for the next reader

This one was found the hard way: the guard's own author never hit it, because
the hook file was temporarily stashed out of the main tree during the landing
that introduced it. The first real session to follow the documented lifecycle
hit it twice. A hook is only proven by the payloads you actually feed it — the
`.claude/hooks/**` validation class exists for this reason, and the original
suite simply had no `cd` case in it.

## Open questions — carried forward

The report's open question stands and is not closed here: any future tool call
that changes directory inside a command string has the same blind spot. The
`cd`/`pushd` fix closes the documented path; a general fix would mean asking
git for the tree after the command's own directory changes, which the hook
cannot do without executing the command.
