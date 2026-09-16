---
id: 2026-09-16-kiro-spec-design-has-no-amendment-mode-metadata-rule
title: kiro-spec-design's Step 6 metadata rule (phase design-generated, design.approved false) has no queue-scoped amendment variant, so an amendment run must choose between the skill text and the repo's amendment precedent (approvals retained, amendments[] recorded)
status: open
importance: medium
importance_why: Every queue-directed re-design of an approved spec hits this; two sessions choosing differently leaves spec.json approvals meaning different things across specs, and /kiro-spec-status has nothing to read the difference from.
effort: S
kind: gap
area: .claude/skills/kiro-spec-design, .claude/skills/kiro-spec-requirements, .claude/skills/kiro-spec-tasks, .kiro/specs/*/spec.json
created: 2026-09-16
surfaced_by: /kiro-spec-design activity-qa-flags [queue: 2026-09-10-activity-qa-flags-staleness-guard-neutralises-retroactive-anchors]
pinned_at: 41f980b
resume_command: "do: write the spec.json rule for a queue-scoped amendment run into .claude/skills/kiro-spec-design/SKILL.md Step 6 (and the matching step in kiro-spec-requirements and kiro-spec-tasks): either retain the top-level approvals and record the run in amendments[] with an explicit approval field, or reset phase/approvals as the full-regeneration path does; then say which existing records (athlete-benchmarks, training-load, activity-qa-flags) follow it and reconcile any that do not"
context:
  - .claude/skills/kiro-spec-design/SKILL.md
  - .kiro/specs/activity-qa-flags/spec.json
  - .kiro/specs/athlete-benchmarks/spec.json
  - .kiro/specs/training-load/spec.json
  - .kiro/steering/change-protocol.md
blocked_by: []
---

## What

`kiro-spec-design/SKILL.md` Step 6 says to set `phase: "design-generated"`,
`approvals.design.generated: true, approved: false` after writing
`design.md`. Its queue directive paragraph says a `[queue: <path>]` run is
scoped to the item and is not a full regeneration, but gives no metadata
rule for that case. The repo's actual amendment records (athlete-benchmarks
Amendment 1 and 2, training-load Amendment 4) kept `phase:
"tasks-generated"`, kept every approval `true`, and appended an
`amendments[]` entry — with a maintainer ruling in hand. The 2026-09-16
activity-qa-flags amendment followed that precedent without a maintainer
ruling on the amendment itself and added an `"approval"` field to its entry
to say so. Neither the skill nor `kiro-spec-status` defines that field.

## Why it matters

`change-protocol.md`'s validation row for `.kiro/specs/**` is "`spec.json`
approvals reflecting what actually happened". With no rule, one session's
"approved: true plus a pending note in amendments[]" and another's
"approved: false, phase regressed" describe the same situation, and
`kiro-impl`'s readiness check (`ready_for_implementation`, approvals) reads
them differently. The next queue-directed design run will re-derive the
choice from scratch.

## Evidence

- `.claude/skills/kiro-spec-design/SKILL.md` — Step 6 "Update Metadata"
  (design approved: false; phase design-generated) versus the "Queue
  directive" paragraph at the top of Execution Steps (no metadata rule).
- `.kiro/specs/athlete-benchmarks/spec.json` — `amendments[0]` (2026-09-10)
  and `amendments[1]` (2026-09-11): approvals all `true`, phase
  `tasks-generated`, no approval field on the entries.
- `.kiro/specs/activity-qa-flags/spec.json` — `amendments[0]` (2026-09-16)
  carries an ad-hoc `"approval"` field the skills do not know.
- `grep -rn 'amendments' .claude/skills/*/SKILL.md` at `41f980b` — no
  matches: no skill reads or writes the array.

## How to pick it up

1. Read the three skills' metadata steps and the three spec.json amendment
   records above.
2. Decide one rule (retain + record, or reset) and write it into each skill's
   queue-directive paragraph and metadata step; if retain + record, name the
   entry fields (`date`, `requirement`, `reason`, `also`, `cross_spec`,
   `approval`) and teach `kiro-spec-status` to report a pending amendment.
3. Done: the three skills state the same rule; every existing `amendments[]`
   entry conforms or is reconciled; `/kiro-spec-status` on activity-qa-flags
   shows the pending amendment.
