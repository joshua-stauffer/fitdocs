---
id: 2026-08-18-gh-token-lacks-delete-repo-scope
title: The gh token cannot delete the remote, which task 8.4 requires
status: done
importance: high
importance_why: Blocks task 8.4 outright, and discovering it there strands the run between a completed local replacement and a remote still serving the old history.
effort: S
kind: gap
area: encumbered-content-purge, operator environment
created: 2026-08-18
surfaced_by: /kiro-impl encumbered-content-purge (pre-Major-8 check during task 7.3)
pinned_at: dac1a7a
resume_command: "do: run `gh auth refresh -h github.com -s delete_repo` (interactive browser authorisation, maintainer action) and re-confirm with `gh auth status` before task 8.2 swaps .git"
context:
  - .kiro/specs/encumbered-content-purge/tasks.md
  - .kiro/specs/encumbered-content-purge/design.md
blocked_by: []
---

## RESOLVED 2026-08-22 — the blocker is dissolved, not fixed

The maintainer is deleting and recreating the GitHub repository **himself**, out
of band, so no `gh` token scope is needed and `gh auth refresh -h github.com -s
delete_repo` should NOT be run. Measured the same day: the new repository
`git@github.com:joshua-stauffer/fitdocs.git` already exists and is empty, and
the old `git@github.com:joshua-stauffer/fitdocs_oss.git` is still live at
`73344d6`.

This changes what task 8.4 automates: the delete half becomes a maintainer act
outside the tool, and recreate-push-and-measure is what remains. Note the new
URL is a **rename**, not a same-name recreate — tracked as
`2026-08-22-the-new-remote-renames-the-repository-and-nine-tracked-urls-still-name-the-old-one`,
which gates task 8.1.

## What

Task 8.4 deletes and recreates the remote repository via the `gh` CLI. The
authenticated token lacks the `delete_repo` scope, so `gh repo delete` will
refuse.

## Why it matters

Task 8.3 forbids **any** remote action until every local verification row is
green, and 8.4 is the only step after it. Discovering the missing scope at
that point leaves the repository in the worst available state: the local
`.git` already replaced, the old history only in the archive, and the remote
still serving everything the purge exists to remove.

The fix is an interactive browser authorisation, so no session can perform it
for itself. It must happen before 8.2.

## Evidence

Measured 2026-08-18:

    $ gh auth status
    github.com
      Logged in to github.com account joshua-stauffer (keyring)
      Token scopes: 'admin:org', 'admin:public_key', 'project',
                    'read:discussion', 'repo', 'workflow'

No `delete_repo`. Confirmed by `gh auth status | grep -o delete_repo` ->
no match.

Also measured the same day, and Req 8.1 requires 8.4 to re-measure rather
than trust this line: the repository is private, `forkCount` 0, open PRs 0,
issues 0, stars 0, default branch `main` -- so the nil-cost premise for
delete-and-recreate holds as of this date.

## How to pick it up

Run `gh auth refresh -h github.com -s delete_repo`, complete the browser
flow, then `gh auth status` and confirm `delete_repo` appears. Done means the
scope is present before task 8.2 runs.
