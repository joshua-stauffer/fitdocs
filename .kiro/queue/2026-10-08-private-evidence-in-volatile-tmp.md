---
id: 2026-10-08-private-evidence-in-volatile-tmp
title: Move private run evidence out of /private/tmp and repoint dead references
status: open
importance: high
importance_why: A reboot already destroyed one run's evidence; every committed record citing /private/tmp now points at nothing, and the count grows per run.
effort: S
kind: gap
area: analytics-query, .kiro/steering/concurrency.md, .kiro/steering/change-protocol.md, .kiro/queue
created: 2026-10-08
surfaced_by: post-reboot recovery of the Codex `$kiro-impl analytics-query` run
pinned_at: f8cc39b
resume_command: "do: choose a durable private evidence root for kiro-impl runs, record it in steering, and repoint the /private/tmp references in analytics-query tasks.md and open queue items [queue: .kiro/queue/2026-10-08-private-evidence-in-volatile-tmp.md]"
context:
  - .kiro/steering/concurrency.md
  - .kiro/steering/change-protocol.md
  - .kiro/specs/analytics-query/tasks.md
  - .kiro/queue/2026-10-06-preview-delete-readiness-race.md
blocked_by: []
---

## What
kiro-impl runs keep their worktrees and private evidence in `/private/tmp`:
reviewer REVIEW.md files, frozen manifests, debug reports, plans, mutation
results. macOS wipes `/private/tmp` on boot. Steering does not prescribe this
location (`grep -rn /private/tmp .kiro/steering .claude/skills .agents/skills`
finds nothing). It is a habit, and nothing tells sessions to put evidence
somewhere durable. Committed spec notes and queue items cite these paths as
the place where the evidence lives.

## Why it matters
The reboot at 13:41 CEST on 2026-10-08 (forced by Ghostty growing to 92 GB)
deleted about 35 worktrees and every analytics-query evidence directory. That
included the blocked handoff for tasks 2.3 and 8.2 that the RELEASE log entry
told the resumer to read. Recovery only worked because the Codex transcripts
happened to echo the files. Every later run that does the same adds more dead
references.

## Evidence
- `git grep -c 'private/tmp/' origin/impl/analytics-query -- .kiro/specs/analytics-query/tasks.md` → 36
- `git grep -c 'private/tmp/' origin/impl/analytics-query -- .kiro/queue/2026-10-08-query-spill-groupby-memory-flake.md` → 12
- `grep -c private/tmp .kiro/queue/2026-10-06-preview-delete-readiness-race.md` (main, f8cc39b) → 16
- `ls -d /private/tmp/*analytics*` after the reboot → no matches
- Agent-log NOTE `reboot-recovery` at 2026-10-08T12:05:13Z records the loss and the recovery.
- Recovered copy (outside the repo, private): `~/code/fitdocs-private-evidence/2026-10-08-reboot-recovery/README.md`.
  Six candidate `.py` files and the cycle-2 REVIEW.md are byte-exact; everything else is best effort.

## How to pick it up
1. Read the recovery README above for what survived, and `.kiro/steering/concurrency.md` for where sessions record state.
2. Choose a durable private root outside the repo (for example `~/code/fitdocs-private-evidence/<run>/`). Add one rule to steering: evidence a committed record cites must live there, not in `/private/tmp`. Worktrees may stay in tmp because the branch is on origin.
3. Repoint the cited paths in analytics-query `tasks.md` (on `impl/analytics-query`) and in the two queue items to the recovered copies, or mark each one "lost in 2026-10-08 reboot".
   Done means: `git grep private/tmp/ -- .kiro` returns only historical mentions that are explicitly marked as such.

## Open questions
- Whether the private root should be iCloud-synced (`pkm-data/raw` style). If so, the iCloud eviction hazard in project memory applies.
