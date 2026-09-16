---
id: 2026-09-16-change-guard-push-check-blind-to-worktree-branches
title: The Stop push check judges only the cwd branch plus `main`, so a worktree branch driven from a session rooted at `main` can hold never-pushed commits in silence
status: open
importance: medium
importance_why: The rooted-at-main-driving-a-worktree configuration is the one /kiro-impl actually runs in (see the 2026-09-10 item), and it is exactly where the 2026-09-16 spec batch sat unpushed.
effort: S
kind: gap
area: .claude/hooks/change-guard.py, .kiro/steering/change-protocol.md, tests/test_change_guard.py
created: 2026-09-16
surfaced_by: chore/push-on-commit (landing the push-on-commit standard at 701bae3)
pinned_at: 701bae3
resume_command: "do: extend change-guard.py handle_stop so the unpushed() check also covers every branch checked out in a linked worktree of this repo (`git worktree list --porcelain`), without turning a peer's not-yet-pushed branch into a block on this session; pin it in tests/test_change_guard.py with a worktree fixture and a mutation that drops the worktree loop"
context:
  - .claude/hooks/change-guard.py
  - .kiro/steering/change-protocol.md
  - .kiro/steering/concurrency.md
  - tests/test_change_guard.py
  - .kiro/queue/2026-09-10-kiro-impl-subagents-do-not-inherit-the-worktree.md
blocked_by: []
---

## What

`change-guard.py`'s Stop handler (`handle_stop`, at 701bae3) runs the new
`unpushed()` check twice: once for the branch checked out in the payload's
`cwd` (line 353–362, only when that branch is not `main`) and once for `main`
by name (line 367). A branch checked out in a *linked worktree* is judged only
if the session's `cwd` is that worktree. The Bash tool resets cwd to the
session's original directory after every call, so a session rooted at the main
tree that drives `cd ../fitdocs-<slug> && git commit` — the lifecycle
`change-protocol.md` prescribes, and the configuration `/kiro-impl` runs in
per the 2026-09-10 item — stops with `cwd` on `main`. Its worktree branch's
commits are checked for being pushed only once they reach `main`.

This is the same blind spot the pre-existing merge-back check
(`rev-list --count main..HEAD`, line 355) has always had, and it is documented
as such in `change-protocol.md` line 358–362. Documented is not closed.

## Why it matters

The standard this check enforces exists because on 2026-09-16 the entire
Phase 7 spec batch sat on a worktree branch that had never been pushed when
`.git` was deleted. That branch was driven from a session rooted at the main
tree. Under the current check, an identical session today would stop with no
block until its merge — the exact window the standard was written to close.
The merge-back check's version of the gap costs an unmerged branch; this one
costs the branch itself.

## Evidence

Scratch repo: bare `origin`, `main` pushed, linked worktree on `impl/x` with
one commit and no upstream, Stop payload with `cwd` = the main tree:

```
$ git -C ../wt rev-list --count main..HEAD
1
$ git for-each-ref --format='%(refname:short) upstream=[%(upstream:short)]' refs/heads/impl/x
impl/x upstream=[]
$ printf '{"hook_event_name":"Stop","session_id":"bs","cwd":"<main tree>",...}' | python3 .claude/hooks/change-guard.py
(silent)
```

The same payload with `cwd` = the worktree blocks with "Branch `impl/x` has
never been pushed" (`tests/test_change_guard.py::test_never_pushed_branch_blocks_until_push_u`
pins that half).

`.claude/hooks/change-guard.py:353-367` — the two `unpushed()` call sites.
`.kiro/steering/change-protocol.md:358-362` — the limitation as written.

## How to pick it up

1. Read `handle_stop` in `.claude/hooks/change-guard.py` and the "What the
   log is not" / "Why this needs no session identity" arguments in
   `concurrency.md` and `queue-commit-guard.py`. The design constraint: the
   hook must not block *this* session because a *peer's* worktree branch is
   unpushed — a peer mid-`commit && push` is a normal state, and
   `concurrency.md` forbids gating on peer state. `git worktree list
   --porcelain` gives every linked worktree's path and branch; nothing in it
   says whose it is.
2. Decide the mechanism. Candidates, in rough preference order: (a) judge
   every worktree branch but downgrade findings for worktrees other than
   `cwd` to advisory text (`additionalContext`, the `log-guard.py` pattern)
   rather than a block; (b) judge only worktrees whose branch names appear in
   this session's transcript (the `session_writes` pattern already reads it),
   which is session-scoped by construction; (c) block on all of them and rely
   on block-once. (b) is the one that satisfies the concurrency constraint
   without weakening the check; note it inherits the transcript-reading
   caveats `log-guard.py` documents.
3. Pin it in `tests/test_change_guard.py`: a fixture with a linked worktree,
   a Stop payload whose `cwd` is the main tree, the finding present before
   `git push -u` and absent after. Mutation: delete the worktree loop —
   observed red through `uv run pytest`, reverted, observed green. Update
   `change-protocol.md`'s Enforcement paragraph (the "same blind spot"
   sentence) in the same change; it is a steering edit and moves with the
   hook.

Done means: the scratch scenario in Evidence blocks (or advises, per the
decision in step 2) with `cwd` on the main tree, and a second worktree on a
branch this session never touched does not.

## Open questions

- Advisory or blocking for worktrees other than `cwd`? Blocking is what the
  standard says; advisory is what `concurrency.md`'s peer-state rule permits
  without a session-identity signal. Option (b) above dissolves the question
  if the transcript signal is judged reliable enough.
