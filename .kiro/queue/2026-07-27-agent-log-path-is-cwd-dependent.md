---
id: 2026-07-27-agent-log-path-is-cwd-dependent
title: The root `agent-log` is a deliberate symlink — protect it, and make the documented log path cwd-independent
status: open
importance: medium
importance_why: The maintainer symlinked `agent-log` at the repo root so the log is visible in the IDE, which `.git/agent-log` is not. It is untracked, so it sits in the blast radius of the `git add -A` these sessions run routinely — committing it would put the coordination log in source control. A session already mistook it for a stray duplicate and deleted it (restored immediately, nothing lost); nothing in the repo says it is intentional.
effort: S
kind: gap
area: .kiro/steering/concurrency.md, .gitignore, CLAUDE.md
created: 2026-07-27
surfaced_by: deleting the symlink by mistake during the Banister steering sync, then restoring it
pinned_at: ec44cb6
resume_command: "do: record that the root agent-log symlink is intentional and protect it from being committed, and make the documented --git-common-dir log path cwd-independent [queue: .kiro/queue/2026-07-27-agent-log-path-is-cwd-dependent.md]"
context:
  - .kiro/steering/concurrency.md
  - .kiro/steering/change-protocol.md
  - .gitignore
  - CLAUDE.md
blocked_by: []
---

## What

Two small things about the shared log's path, one of which nearly cost the
maintainer a piece of their tooling.

**1. The root `agent-log` is a symlink to `.git/agent-log`, on purpose.** The
maintainer created it because the canonical file inside `.git/` does not show up
in their IDE. Nothing in `concurrency.md`, `change-protocol.md` or `CLAUDE.md`
mentions it, so to a session reading `git status` it looks like an untracked
stray — and it is untracked, so `git add -A` would commit it.

**2. The documented way to find the log is cwd-dependent.** All three documents
say:

```bash
LOG="$(git rev-parse --git-common-dir)/agent-log"
```

`--git-common-dir` returns an absolute path from a **linked** worktree and the
relative string `.git` from the **main** worktree:

```
$ git rev-parse --git-common-dir                       # main worktree
.git
$ cd <linked worktree> && git rev-parse --git-common-dir
/Users/josh/code/fitdocs_oss/.git
```

So in the main worktree the command is correct only while the shell's cwd is the
repo root. This is latent, not observed: sessions do their work in linked
worktrees, which is the case where the command is already absolute.

## Why it matters

The log is the only mechanism by which sessions discover each other — worktree
isolation hides peers completely. Two failure modes follow from the above:
committing it (item 1) puts every session's internal coordination notes into a
public repo permanently, and a cwd-dependent write (item 2) would fork it
silently, with both reader and writer succeeding against different files.

The immediate risk is item 1, and it is not hypothetical: the session that filed
this deleted the symlink after misreading `ls -lT` output piped through `awk`,
which stripped the `-> .git/agent-log` suffix, and then "confirmed" the file was
a duplicate with `cmp` and `wc`, both of which follow symlinks. It was restored
in the same session and no log content was ever at risk, because the symlink's
target was never touched.

## Evidence

```
$ ls -l agent-log
lrwxr-xr-x  1 josh  staff  14 Jul 27 23:20 agent-log -> .git/agent-log
$ git log --oneline --all -- agent-log     # never tracked, no output
```

Note the trap for the next session: `ls -lT` shows the *symlink's* own mtime,
which differs from the target's, and every content comparison (`cmp`, `diff`,
`wc`) follows the link and reports identity. Symlink-ness is visible only in the
mode column and the `->` suffix. Use `ls -l` unfiltered, or `test -L`.

## How to pick it up

1. Add `/agent-log` to `.gitignore` — anchored, so it protects the root symlink
   without ignoring anything named `agent-log` elsewhere. This is the fix that
   removes the `git add -A` hazard.
2. Say in `concurrency.md` that the root symlink is intentional, exists for IDE
   visibility, and must not be "cleaned up" — one sentence next to the existing
   read-the-log instruction.
3. Make the path cwd-independent: `git rev-parse --path-format=absolute
   --git-common-dir` (git ≥ 2.31 — confirm the version first). Fix all three
   copies in one change; a partial fix leaves a session following a stale one.
4. Check whether `.claude/hooks/log-guard.py` resolves the log the same way — if
   so it can inspect a different file than the session it guards.
5. Done looks like: `git status` is clean with the symlink present, and the log
   command run from a subdirectory of the main worktree appends to
   `.git/agent-log`.
