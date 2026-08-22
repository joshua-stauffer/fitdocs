---
id: 2026-08-18-change-guard-false-positive-on-git-commit-tree
title: The change guard denies `git commit-tree`, the central plumbing command of this spec's own mechanism
status: open
importance: medium
importance_why: It blocks hand-rehearsing the replacement from a shell on main and denies it with a message describing something the command never did, which invites a session to misread the guard rather than the command.
effort: S
kind: inconsistency
area: .claude/hooks/change-guard.py
created: 2026-08-18
surfaced_by: /kiro-impl encumbered-content-purge (task 7.7, parent session reproducing the post-swap reflog state by hand)
pinned_at: aeabf8e
resume_command: "do: make change-guard.py's GIT_COMMIT regex not match `git commit-tree` (and check `git commit-graph` too), then pin both with a test"
context:
  - .claude/hooks/change-guard.py
  - .kiro/steering/change-protocol.md
blocked_by: []
---

## What

`change-guard.py` denies `git commit` on `main` via

    GIT_COMMIT = re.compile(r"\bgit\b(?:\s+-[^\s]+(?:\s+[^\s]+)?)*\s+commit\b")

`\bcommit\b` matches `git commit-tree`: the trailing `\b` is satisfied by the
hyphen, which is a non-word character. So a plumbing command that creates an
object and moves no ref, and cannot advance a branch, is denied as though it
were a commit onto `main`.

`git commit-graph` matches the same way and has the same property.

## Why it matters

`git commit-tree` is not an incidental command here — it is *the* mechanism
Decision 7 chose. `scripts/purge/replace.py::build_commit_tree_command` forges
the replacement root with it. A session doing exactly what this spec's own
rehearsal task asks — reproducing the forge/clone/swap by hand in a shell to
check a claim about git — is denied from the primary worktree, and the denial
message says work "reaches main by `git merge --ff-only`", which describes
nothing the command was doing.

The failure mode is not the denial, it is the misdiagnosis: the message points
at branch discipline, so the natural next move is to reach for the
trivial-change escape hatch, which would be a false declaration. (This session
declined it and satisfied the guard's real condition instead, by running from
the worktree, which is on a branch.)

Major 8 itself is NOT blocked: it drives `commit-tree` through Python inside
`run_replace`, and the hook inspects Bash command text only — a limit its own
docstring states. So this is a defect in the guard's precision, not a blocker
for the one-shot.

## Evidence

Measured at `aeabf8e`. Two Bash commands were denied from the primary worktree
on `main`, neither containing `git commit` as a command:

- a script whose only git-writing verbs were `hash-object -w`, `mktree`,
  `commit-tree`, `update-ref` and `symbolic-ref`, all with `-C` pointed at a
  throwaway repository under the session scratchpad
- the same script after every `git commit` invocation had already been replaced
  by plumbing, confirming `commit-tree` alone triggers it

The `$`-heavy paths also made the guard's target unresolvable
(`UNRESOLVABLE = re.compile(r"[$`*?]")`), so it denied conservatively — correct
behaviour on its own terms, and a second reason the message did not describe
the command.

## How to pick it up

Tighten the pattern so a hyphen (or any non-space) after `commit` does not
match — for example require a word boundary that is whitespace or
end-of-command, or negative-lookahead `commit(?!-)`. Check `commit-graph` and
any other `commit-*` plumbing in the same pass.

Then pin it: a test asserting `git commit-tree <tree> -m x` is ALLOWED on main
while `git commit -m x` is DENIED. Per this repo's own rules the guard is
behaviour like any other code, so the change runs the full ritual and the
assertion needs a mutation that reds it.
