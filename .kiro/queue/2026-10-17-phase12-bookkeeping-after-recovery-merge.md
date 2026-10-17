---
id: 2026-10-17-phase12-bookkeeping-after-recovery-merge
title: Recovery's spec.json and roadmap rows still show pre-implementation state after its 240ed2f merge; peers keep stale landing notes
status: open
importance: low
importance_why: Status-only drift; /kiro-spec-status and /kiro-queue would show recovery and its amendments as unstarted.
effort: S
kind: chore
area: recovery, hr-derivation, apple-health-import, .kiro/steering/roadmap.md
created: 2026-10-17
surfaced_by: maintainer-requested Phase 12 re-validation (all four reviewers)
pinned_at: 160b007
resume_command: "do: sync Phase 12 bookkeeping to the merged state: recovery spec.json phase, roadmap recovery/wiki-contract/connectors/chart-catalog rows, and the stale landing sentences in hr-derivation and apple-health-import [queue: .kiro/queue/2026-10-17-phase12-bookkeeping-after-recovery-merge.md]"
context:
  - .kiro/specs/recovery/spec.json
  - .kiro/specs/recovery/tasks.md
  - .kiro/steering/roadmap.md
  - .kiro/specs/hr-derivation/spec.json
  - .kiro/specs/apple-health-import/spec.json
  - .kiro/specs/apple-health-import/tasks.md
blocked_by: []
---

## What
Recovery merged to main at 240ed2f (agent log: "Recovery COMPLETE 21/21
mandatory ... MERGED"), but its records were not moved:
- `.kiro/specs/recovery/spec.json`: `"phase": "tasks-generated"`. All four
  Phase 12 peers moved to `implementation-complete` in their completion
  commits (for example a885031 and 700b32e).
- `.kiro/steering/roadmap.md:3343`: `- [ ] recovery ...`, still worded as
  spec-written, with no implementation date or contract 14.
- `roadmap.md:3156`: the wiki-contract item's recovery half
  (`recovery/`, `recovery/assets/`) has no implemented marker.
- `roadmap.md:3180-3181`: "Recovery's half is not yet on main, so this
  shared update remains open." But connectors Amendment 5 is on main
  (`.kiro/specs/connectors/requirements.md`, recovery in Req 14.1).
- `roadmap.md:3203`: `- [ ] chart-catalog ... Amendment 1, the
  reference-band kind`, which landed with recovery.

Peers keep notes that were true only before landing:
- `.kiro/specs/hr-derivation/spec.json` `phase_note` still says exact
  final-HEAD CI is required before landing. The log records CI
  38932318838 SUCCESS and MERGED at 700b32e.
- `.kiro/specs/apple-health-import/spec.json` `phase_note`, and
  `tasks.md:846`, still say CI, main merge/push and main CI are required.
  The log records DoD complete at a885031.

## Why it matters
`/kiro-spec-status` and `/kiro-queue` read these files. Recovery shows as
unimplemented, and the roadmap's open "Existing Spec Updates" rows rank as
pending work that is already done.

## Evidence
`git show 240ed2f --stat` does not touch `recovery/spec.json`; its last
change is 9d4d737. The three reviewer reports, and a parent re-read of the
lines above at 160b007, agree.

## How to pick it up
1. Set recovery `spec.json` phase to `implementation-complete` and add a
   short landing note (merge 240ed2f, CONTRACT_VERSION 14).
2. Tick and annotate the four roadmap rows above, citing the amendment
   numbers actually on main.
3. Trim the two stale landing sentences. Commit on main as a bookkeeping
   change.
