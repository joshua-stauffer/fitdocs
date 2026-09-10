---
id: 2026-09-10-spec-batch-skill-rereads-log-once
title: kiro-spec-batch reads the shared log only before Step 1 — it must re-read before each wave and relay peer TOUCHING/WARN lines into subagent prompts
status: open
importance: medium
importance_why: A multi-wave batch runs for hours; a peer's shape constraint logged two minutes after the batch's first claim never reached a wave 2 subagent, and the resulting spec now needs an amendment (see the applies_from item).
effort: S
kind: docs
area: .claude/skills/kiro-spec-batch/SKILL.md, .kiro/steering/concurrency.md
created: 2026-09-10
surfaced_by: /kiro-spec-batch (Phase 6) — post-merge log read
pinned_at: bb848a4
resume_command: "do: under the change ritual (skills are non-trivial class), add to .claude/skills/kiro-spec-batch/SKILL.md Step 3 a mandatory per-wave log re-read immediately before each wave's CLAIM — everything since the last read — with the rule that any peer TOUCHING/WARN/NOTE naming a module, spec or shape a wave's feature will specify is pasted into that subagent's prompt verbatim; then exercise the skill once or state why it cannot be run and what was inspected instead"
context:
  - .claude/skills/kiro-spec-batch/SKILL.md
  - .kiro/steering/concurrency.md
  - .kiro/queue/2026-09-10-performance-benchmarks-design-predates-applies-from.md
blocked_by: []
---

## What
`kiro-spec-batch`'s "Shared-log preflight" reads the log once, before Step 1.
Its subagents "do not read or write the log themselves — this controller
session owns both on their behalf". Between the wave 1 claim (22:04Z) and the
wave 2 dispatch (22:59Z) of the Phase 6 batch, a peer claimed wave 0 and
logged a benchmark-entry shape addressed to performance-benchmarks by name.
The controller followed the skill as written and did not re-read; the wave 2
subagent therefore specified an entry shape the peer had just superseded.

## Why it matters
`concurrency.md`'s read points already say "before entering a choke-point
module" and "on resume after any pause"; a wave dispatch is both, but the
skill does not say so, and the controller is the only party that can carry
log content into a subagent's context. Without the rule, every multi-wave
batch that overlaps an implementation session repeats this.

## Evidence
- `.claude/skills/kiro-spec-batch/SKILL.md` — "Shared-log preflight … Before
  Step 1"; no later read point in Step 3.
- Shared agent log: `2026-09-09T22:04:23Z spec-batch CLAIM` (wave 1),
  `2026-09-09T22:06:59Z impl-training-load-prompt-date CLAIM`,
  `2026-09-09T22:15:37Z impl-training-load-prompt-date TOUCHING` (the shape
  addressed to performance-benchmarks), `2026-09-09T22:59:46Z spec-batch
  CLAIM` (wave 2, dispatched without that line).
- Consequence item: `2026-09-10-performance-benchmarks-design-predates-applies-from`.

## How to pick it up
1. Read the skill's preflight and Step 3, and concurrency.md § Read points.
2. Add the per-wave re-read and the relay rule to Step 3 (one short paragraph
   before the CLAIM snippet); consider the same for the cross-spec review
   dispatch, which should also see peer shape statements.
3. Validate per the skills row of change-protocol.md's table.
