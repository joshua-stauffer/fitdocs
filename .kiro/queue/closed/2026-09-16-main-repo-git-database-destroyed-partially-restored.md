---
id: 2026-09-16-main-repo-git-database-destroyed-partially-restored
title: Finish restoring the main repository's git database after the 2026-09-16 rm -rf .git incident
status: done
importance: high
importance_why: Two unpushed main commits and two batch-branch commits exist only as working-tree files; the shared agent log is gone; the phase-7 worktree cannot run git until its link is rebuilt.
effort: S
kind: chore
area: repository, .git, .kiro/steering/concurrency.md
created: 2026-09-16
surfaced_by: kiro-spec-batch Phase 7 wave 3 (build-training-block spec generation subagent)
pinned_at: ab6309e
resume_command: "do: nothing -- restored by the spec-batch controller on 2026-09-16 (see Resolution); hardening is 2026-09-16-change-guard-deny-rm-rf-git"
context:
  - .kiro/steering/change-protocol.md
  - .kiro/steering/concurrency.md
  - .kiro/specs/build-training-block/spec.json
blocked_by: []
---

## What
During wave 3 of the Phase 7 spec batch, a packaging probe intended for the
scratchpad ran in the tool's default working directory instead: a `cd` to a
not-yet-created scratch path failed and the rest of the command line
(`rm -rf .git && git init -q ...`) executed in `/Users/josh/code/fitdocs_oss`.
The main repository's `.git` directory was deleted and replaced with an
empty one. Every working-tree file in both `/Users/josh/code/fitdocs_oss`
and the worktree `/Users/josh/code/fitdocs-spec-batch-phase7` is intact.

Lost: all local objects and refs (local `main` at `3664a0d`, which was two
commits ahead of the GitHub remote; the batch branch `chore/spec-batch-phase7`
at `0994bf0` with commits `e40e361` and `0994bf0`), all reflogs, the worktree
administrative directory `.git/worktrees/fitdocs-spec-batch-phase7`, and the
shared agent log `.git/agent-log` (the repository-root `agent-log` symlink
now dangles).

Restored so far (non-destructive, from the GitHub remote): `origin` re-added
and fetched; `HEAD` -> `refs/heads/main` at `ab6309e` (the remote tip); the
index rebuilt with `git reset --mixed` so the working tree is untouched.
`git status` in `fitdocs_oss` now shows exactly the content of the two lost
commits as an uncommitted diff (`.kiro/steering/product.md`,
`.kiro/steering/roadmap.md`, `README.md`, the three Phase 7 spec `brief.md`
directories, the queue moves) plus `.claude/scheduled_tasks.lock`. The
auto-mode classifier then refused further writes under `.git/` (branch
creation, worktree admin files), so the rest is below.

## Why it matters
Until the branch and worktree link exist again, the batch controller cannot
commit wave 3 (or re-commit waves 1 and 2) from the worktree; until the two
lost `main` commits are re-created, `main` on disk and `main` in git
disagree; until `.git/agent-log` exists again, every session's first command
(`cat "$(git rev-parse --git-common-dir)/agent-log"`) fails and peer
coordination is blind. If a Time Machine destination can be mounted, the
original `.git` (with reflogs and the full agent log) may be recoverable
outright and should be preferred over re-creation.

## Evidence
- `ls -la /Users/josh/code/fitdocs_oss/.git` at 02:36 local: only
  `config, description, HEAD, hooks, info, objects, refs` (fresh `git init`
  layout); `HEAD` read `ref: refs/heads/probe`.
- `cat /Users/josh/code/fitdocs-spec-batch-phase7/.git` ->
  `gitdir: /Users/josh/code/fitdocs_oss/.git/worktrees/fitdocs-spec-batch-phase7`
  (target absent); `git status` there -> `fatal: not a git repository`.
- `git ls-remote git@github.com:joshua-stauffer/fitdocs.git` ->
  `ab6309e78a440e5f0423c2889027db1f8695faad refs/heads/main`.
- Session-start `git log --oneline -5` (recorded in the wave-3 subagent's
  context): `3664a0d chore(queue): spec-batch has no rule for a multi-phase
  roadmap; close the Phase 4 status-lines item`, `5def7a7 docs(discovery):
  Phase 7 -- training blocks`, `ab6309e ...`, `fdf10a7 ...`, `aa851a3 ...`.
  Batch-branch commit subjects: `e40e361 spec(training-blocks):
  requirements, design, tasks (Phase 7 wave 1)`, `0994bf0
  spec(plan-resolution): requirements, design, tasks (Phase 7 wave 2)`.
- `tmutil latestbackup` -> "Failed to mount destination"; the controller's
  `tmutil destinationinfo` -> "No destinations configured" and
  `tmutil listlocalsnapshots /` shows only OS-update snapshots. **There was
  no Time Machine backup to restore from.**
- `ls -la /Users/josh/code/fitdocs_oss/agent-log` ->
  `agent-log -> .git/agent-log` (dangling).

## How to pick it up
1. **Try the backup first.** Connect the Time Machine destination and check
   whether `/Users/josh/code/fitdocs_oss/.git` exists in the latest backup
   from before 2026-09-16 02:36 local. If it does, move the current
   (re-initialized) `.git` aside and restore the backed-up one whole; the
   worktree link, the branch, the reflogs and `.git/agent-log` come back
   with it. Then `git status` in both trees should show only the wave-3
   spec files as untracked. Skip steps 2-4.
2. **Otherwise re-create the two lost `main` commits from disk**, in
   `/Users/josh/code/fitdocs_oss`, on a branch (the change-guard denies
   commits on `main`; use the lifecycle in change-protocol.md): first
   commit the discovery content (`product.md`, `roadmap.md`, `README.md`,
   the three `brief.md` dirs) with the subject `docs(discovery): Phase 7 --
   training blocks (re-created after the 2026-09-16 .git loss)`, then the
   queue moves with `chore(queue): spec-batch has no rule for a multi-phase
   roadmap; close the Phase 4 status-lines item (re-created)`; merge
   `--ff-only` to `main`. Do not commit `.claude/scheduled_tasks.lock`.
3. **Re-link the worktree**: `git branch chore/spec-batch-phase7 main`,
   then create `.git/worktrees/fitdocs-spec-batch-phase7/` holding `HEAD`
   (`ref: refs/heads/chore/spec-batch-phase7`), `commondir` (`../..`) and
   `gitdir` (`/Users/josh/code/fitdocs-spec-batch-phase7/.git`); verify with
   `git worktree list`; in the worktree run `git reset --mixed` (index only)
   and `git status` -- the wave-1, wave-2 and wave-3 spec files appear as
   untracked; commit them as three commits with the original subjects.
4. **Re-create the agent log**: `touch /Users/josh/code/fitdocs_oss/.git/agent-log`
   and append a line recording the loss and the recovery (the root
   `agent-log` symlink resolves again). Peers must re-read it: the earlier
   history is gone unless step 1 succeeded.
5. Done means: `git log --oneline -3` on `main` shows the two re-created
   commits above `ab6309e`, `git worktree list` shows the phase-7 worktree
   on `chore/spec-batch-phase7`, and `cat "$(git rev-parse --git-common-dir)/agent-log"`
   succeeds from both trees.

## Open questions
- Whether the Time Machine backup predates the loss closely enough to hold
  `3664a0d` and the batch branch; if not, the reflog and the pre-incident
  agent-log history are unrecoverable and step 4's line should say so.

## Resolution (spec-batch controller, 2026-09-16 ~07:30-08:00Z)

Restored additively -- nothing in either working tree was reset, checked
out or deleted:

1. **Agent log**: the controller had read the whole log at session start
   (2026-09-15T21:08Z) and the harness had persisted that tool result to
   disk; lines 1-775 of the new `.git/agent-log` are that copy, byte-exact
   (`wc -c` 762171, equal to the pre-loss size the controller had also
   recorded). Lines 776-780 are the controller's own five lines from this
   session, re-appended from the transcript (two RELEASE timestamps are
   approximate to the minute). No peer session wrote to the log between the
   session-start read and the loss -- verified at each wave dispatch -- so
   nothing is missing. Line 781 is the incident WARN.
2. **`main`**: the two lost commits were re-created from the intact working
   tree on a `restore/` branch and fast-forwarded: `4981bb2` (twin of
   `5def7a7`, `docs(discovery): Phase 7`) and `5dff756` (twin of `3664a0d`,
   `chore(queue): ...`). Trees are identical to the originals -- the spec
   worktree's checked-out copies of every one of those files, which the
   loss did not touch, compare byte-equal. Original commit bodies and the
   exact file split between the two are not recoverable. Every open queue
   item, research note and memory that pinned `3664a0d` now names `5dff756`
   with a parenthetical; closed items are left as the README requires.
3. **Worktree and branch**: `chore/spec-batch-phase7` re-created at
   `5dff756`; `.git/worktrees/fitdocs-spec-batch-phase7/{HEAD,commondir,gitdir}`
   written by hand (`git worktree repair` cannot rebuild a missing admin
   directory); index rebuilt with `git read-tree HEAD`. Waves 1-3 re-committed
   with their original messages plus a re-commit note (`b381f0d` twin of
   `e40e361`, `bdfeb8a` twin of `0994bf0`, wave 3 first-committed).
4. `.git/info/exclude` was also lost; `.claude/scheduled_tasks.lock` (the
   one machine-local file it evidently held) re-added to it.

Not recoverable: reflogs; the original SHAs (references to them are dead;
`git log <old>..HEAD` fails, so every open pin was moved). Root cause and
the guard that would have stopped it: `2026-09-16-change-guard-deny-rm-rf-git`.
