---
id: 2026-07-26-land-change-protocol-enforcement
title: Land the change-protocol enforcement, and the in-flight tree it is stuck behind
status: done
importance: high
importance_why: The enforcement was written but uncommitted on main — the exact failure mode it exists to prevent.
effort: S
kind: chore
area: .kiro/steering/change-protocol.md, .claude/hooks/change-guard.py, .claude/settings.json
created: 2026-07-26
closed: 2026-07-26
surfaced_by: session that wrote the change protocol
pinned_at: 2a01dfd
resume_command: "do: none — landed on main via chore/change-protocol"
context:
  - .kiro/steering/change-protocol.md
  - .claude/hooks/change-guard.py
blocked_by: []
---

## What

The change protocol was written, wired and tested but sat uncommitted on
`main`, unable to meet its own Definition of Done. Two blockers, one root
cause: 37 dirty paths of unrelated in-flight work in the primary tree.

1. **No worktree was possible.** The change's base — `.claude/settings.json`,
   `.claude/hooks/queue-guard.py`, CLAUDE.md's follow-up-queue rule — existed
   only as uncommitted state in that tree.
2. **`uv run ruff check .` was red** (2 × SIM105, `change-guard.py:238` and
   `queue-guard.py:137`) and unfixable in place, because the now-armed guard
   denies edits to `.claude/hooks/**` on `main`.

## Resolution

Josh paused all other writers, then the tree was split by classification —
20 feature paths (`src/`, `tests/`, `.kiro/specs/`) versus 17 process paths
(`CLAUDE.md`, `.claude/`, `.kiro/steering/`, `.kiro/queue/`), with no overlap.
Feature work went to a stash, process work to a second stash popped into
`../fitdocs-change-protocol` on `chore/change-protocol`, leaving `main` clean
for a conflict-free `--ff-only` merge. Feature work was restored afterwards.

Both SIM105s are fixed. A third defect surfaced during the landing and is
fixed here too: the guard judged the *session's* cwd rather than the tree a
write lands in, so `git -C <worktree> commit` from a session rooted at `main`
was denied — it now resolves the target tree, with six cross-tree regression
cases in the suite.

Backup of the pre-split tree (patch + untracked tarball + status) was written
to the session scratchpad before any destructive step.

## Open questions — resolved

Should `.kiro/queue/` be committed? **Yes**, decided here and acted on: it is
not gitignored, its items carry `pinned_at` SHAs, and its README treats closed
items as durable. A fresh clone now gets the queue.
