---
id: 2026-09-16-change-guard-deny-rm-rf-git
title: A subagent destroyed the repository database with `cd <missing dir> && rm -rf .git && git init`; the change-guard hook lets any `rm -rf` through and every kiro skill lets subagents improvise shell probes
status: open
importance: high
importance_why: One failed `cd` cost the reflogs, two unpushed commits, the worktree link and the shared agent log; only a session-start copy of the log made recovery possible. The same command shape recurs every time an agent probes packaging or git behaviour.
effort: S
kind: gap
area: .claude/hooks/change-guard.py, .claude/skills/kiro-spec-batch/SKILL.md, .claude/skills/kiro-spec-design/SKILL.md, .kiro/steering/change-protocol.md, .kiro/steering/concurrency.md
created: 2026-09-16
surfaced_by: /kiro-spec-batch (Phase 7, wave 3 build-training-block) -- the incident itself, closed as 2026-09-16-main-repo-git-database-destroyed-partially-restored
pinned_at: 5dff756
resume_command: "do: under the change ritual (hooks and skills are non-trivial class), (1) extend .claude/hooks/change-guard.py PreToolUse to deny a Bash command that contains `rm -rf`/`rm -r` whose target names `.git` or resolves to a versioned repo root or the worktree root, with a synthetic payload that fires and one that passes; (2) add to change-protocol.md a 'Destructive shell' rule -- never `cd X && <destructive>`; `mkdir -p` the scratch dir first or use `cd X || exit 1`; throwaway repos only in the session scratchpad; (3) add one sentence to the kiro-spec-batch, kiro-spec-design and kiro-spec-requirements subagent prompt templates forbidding `rm -rf` and `git init` outside the scratchpad; (4) add to concurrency.md a line saying the agent log has no backup and a session that reads it whole at start is the only copy"
context:
  - .claude/hooks/change-guard.py
  - .kiro/steering/change-protocol.md
  - .kiro/steering/concurrency.md
  - .claude/skills/kiro-spec-batch/SKILL.md
  - .kiro/queue/closed/2026-09-16-main-repo-git-database-destroyed-partially-restored.md
blocked_by: []
---

## What

On 2026-09-16 ~02:36Z a `general-purpose` subagent generating the
`build-training-block` spec wanted to prove empirically which files
Hatchling ships in the wheel. It composed a one-line probe of the form
`cd <scratchpad>/pkgprobe && rm -rf .git && git init -q && ...` -- the
scratch directory did not exist yet, `cd` failed, `&&` short-circuited only
the `cd`'s own success check, and `rm -rf .git && git init` ran in the Bash
tool's default cwd, `/Users/josh/code/fitdocs_oss`. The repository database
was deleted and re-initialised. Working trees were untouched.

Two independent gaps let it happen:

1. **The hook does not look at `rm`.** `change-guard.py` PreToolUse covers
   `Edit`/`Write`/`NotebookEdit` and `git commit` only
   (`.claude/hooks/change-guard.py:11-12, 19-21`); its docstring says so as
   a limit "by design". It already parses a leading `cd`/`pushd` and
   `git -C` out of a command (`:49, :55`), so the machinery to judge "which
   tree does this land in" exists; it is never applied to `rm`.
2. **No skill or steering text tells a subagent how to run a destructive
   probe safely.** `change-protocol.md` § Not Allowed lists `git add -A`
   but nothing about `rm -rf`, `git init`, or chaining after `cd`;
   the kiro-spec-* skills encourage empirical verification ("verify every
   file:line ... still holds", "packaging facts verified empirically") with
   no boundary on where a probe may run. The subagent's own report shows it
   knew the scratchpad was the right place -- the failure was the command
   shape, not the intent.

## Why it matters

Lost outright: every reflog, the original SHAs of two unpushed `main`
commits and two branch commits (every open queue pin naming them had to be
moved), and `.git/agent-log` -- the sole coordination artifact
`concurrency.md` relies on, which has no backup anywhere. It was recovered
only because the controller had `cat`-ed the whole log at session start and
the harness persists large tool results to disk. A session that had read
only the tail would have lost 775 lines of cross-session history for good.
No Time Machine destination is configured on this machine
(`tmutil destinationinfo`), so the hook is the only line of defence.

## Evidence

- Wave-3 subagent report, 2026-09-16: "a command whose `cd` to a
  not-yet-created scratch path failed, and the rest of the line
  (`rm -rf .git && git init -q ...`) executed in the tool's default cwd
  `/Users/josh/code/fitdocs_oss`."
- `ls -la /Users/josh/code/fitdocs_oss/.git` afterwards: fresh `git init`
  layout, `HEAD` -> `refs/heads/probe`; `git for-each-ref` after the
  subagent's re-fetch: only `refs/heads/main` and `refs/remotes/origin/*`
  at `ab6309e`.
- `grep -n "rm\b" .claude/hooks/change-guard.py` -> no match: the hook has
  no notion of `rm`.
- `grep -n -i "rm -rf\|git init\|scratch" .kiro/steering/change-protocol.md
  .kiro/steering/concurrency.md .claude/skills/kiro-spec-*/SKILL.md` -> no
  rule (the only "scratch" mentions are unrelated).
- Recovery record: `.kiro/queue/closed/2026-09-16-main-repo-git-database-destroyed-partially-restored.md`
  § Resolution; agent-log WARN 2026-09-16T07:35Z.

## How to pick it up

1. In a worktree, add to `change-guard.py` a `RM_TARGET` regex over the
   Bash command (`rm` with any `-r`/`-R`/`-rf`/`-fr` flag), resolve each
   target the way `commit_tree` resolves `git -C` (`:145-165`) -- honouring
   the leading `cd` *and* the case where the `cd` target does not exist,
   which must be judged as "lands in cwd" -- and deny when the resolved
   target is `.git`, a `.git/*` path, a repo root, or a worktree root.
   Validate per the hooks row of change-protocol.md: one synthetic payload
   that fires (the exact incident command), one that passes
   (`rm -rf "$SCRATCH/pkgprobe"` with the variable expanded to a real
   scratch path), output shown.
2. Add the destructive-shell rule to change-protocol.md § Not Allowed and a
   one-line "how to probe" recipe (`SCRATCH=...; mkdir -p "$SCRATCH/x" && cd
   "$SCRATCH/x" || exit 1`). Grep steering + CLAUDE.md for contradictions.
3. Add the forbidding sentence to the three skills' subagent prompt
   templates. Exercise one skill end to end or state why not.
4. `concurrency.md`: the log's only durability is the file itself; a
   session that reads it whole at start holds the only copy. Consider a
   Stop-hook or per-MERGED copy to `.kiro/agent-log.snapshot` (untracked,
   gitignored) so the next loss is bounded to one session.

## Open questions

- Whether to deny all `rm -r*` inside a versioned tree outright (simplest,
  may block legitimate cleanups of build dirs) or only targets naming
  `.git`/the root. Recommendation: the narrow rule first; widen if it
  proves too permissive.
