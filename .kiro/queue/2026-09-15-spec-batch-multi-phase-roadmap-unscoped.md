---
id: 2026-09-15-spec-batch-multi-phase-roadmap-unscoped
title: kiro-spec-batch parses "the ## Specs (dependency order) section" (singular, H2) — a multi-phase roadmap has five, and a scan of all of them sweeps the gated performance-model-fit into Phase 7's waves
status: open
importance: medium
importance_why: Bites every future phase; a literal parse dispatches nothing and a broad scan generates a spec the roadmap explicitly gates.
effort: S
kind: inconsistency
area: .claude/skills/kiro-spec-batch/SKILL.md, .kiro/steering/roadmap.md
created: 2026-09-15
surfaced_by: /kiro-discovery (Phase 7, training blocks) — independent reviewer pass on the discovery change
pinned_at: ab6309e
resume_command: "do: under the change ritual (skills are non-trivial class), amend .claude/skills/kiro-spec-batch/SKILL.md Step 1 so the wave input is the newest phase's `#### Specs (dependency order)` section (earlier sections are history), an item whose bullet is marked **gated** is skipped unless named in the invocation, and an item whose `.kiro/specs/<name>/spec.json` already exists is never regenerated; then run `/kiro-spec-batch` for Phase 7 and confirm it dispatches exactly training-blocks, plan-resolution, build-training-block"
context:
  - .claude/skills/kiro-spec-batch/SKILL.md
  - .kiro/steering/roadmap.md
  - .kiro/specs/performance-model-fit/brief.md
  - .kiro/queue/2026-09-10-spec-batch-skill-rereads-log-once.md
blocked_by: []
---

## What

`kiro-spec-batch` Step 1 says "Parse the `## Specs (dependency order)`
section" and its constraints say that section "remains authoritative for
batch execution: other roadmap sections are context, not wave inputs". The
roadmap has had one H2 `## Specs (dependency order)` (the first-pass three
specs, all `[x]`) since 2026-07-14 and, since Phase 4, one H4
`#### Specs (dependency order)` per phase — five sections in total after
Phase 7. The skill has no rule for choosing among them and no notion of a
phase. Two failure shapes follow: a literal parse finds only the H2, sees no
pending feature, and dispatches nothing; a controller that instead scans
every H4 section (which is what the Phase 6 run must have done to work) also
picks up `performance-model-fit`, whose bullet is `[ ]`, explicitly
**gated** ("requirements begin only after `load-history` reports the
archive's criterion-point count"), and whose `brief.md` exists — so the
missing-brief stop in Step 1.5 does not catch it and it is generated in the
same waves as Phase 7's three specs.

## Why it matters

Every future phase runs through this ambiguity. The gated spec is the
concrete casualty today: the roadmap made a deliberate decision to hold it
until a measured precondition is met, and the batch skill would override
that decision silently. A regenerated spec for an already-implemented
feature is the same hazard one step further (the Phase 6 bullets were `[ ]`
with `spec.json` present until 2026-09-15; the discovery change ticked them).

## Evidence

- `.claude/skills/kiro-spec-batch/SKILL.md:27` — "Parse the `## Specs
  (dependency order)` section to extract:"; `:176` — "`## Specs (dependency
  order)` remains authoritative for batch execution: Other roadmap sections
  are context, not wave inputs." `grep -n -i phase` on the skill finds no
  phase rule (only "For each phase" of the spec pipeline at `:76` and
  spec.json's `phase` field at `:146`).
- `.kiro/steering/roadmap.md` on branch `chore/discovery-training-blocks`:
  `grep -n 'Specs (dependency order)'` → `104` (H2), `681`, `905`, `1124`,
  `1388` (H4, Phases 4–7).
- `performance-model-fit`: roadmap bullet at `:1138` begins
  `- [ ] performance-model-fit — **gated**`; `ls .kiro/specs/performance-model-fit/`
  → `brief.md` only.
- Reported by the Phase 7 discovery reviewer subagent on 2026-09-15 and
  re-verified by the discovery session with the greps above.

## How to pick it up

1. Read `.claude/skills/kiro-spec-batch/SKILL.md` Step 1 and the constraints
   block at the end; read `.kiro/steering/roadmap.md` §Phase 7
   `#### Specs (dependency order)` and §Phase 6's, noting the **gated**
   marker on `performance-model-fit`.
2. In a worktree, amend Step 1 with three rules: the wave input is the
   newest `#### Specs (dependency order)` section (or the section named in
   the invocation); a bullet carrying **gated** is skipped unless the
   invocation names it; a feature whose `spec.json` exists is reported as
   already generated, never regenerated. Keep the H2 wording only as history.
3. Validate per the `.claude/skills/**` row of change-protocol: dry-run the
   amended Step 1 against the current roadmap and show that the parsed set
   is exactly `training-blocks`, `plan-resolution`, `build-training-block`.
   Done means that dry run is in the merge's log line.

## Update 2026-09-16 (Phase 7 spec batch)

The Phase 7 batch was run with the invocation scoped by name
(`/kiro-spec-batch stage 7`): the controller parsed only Phase 7's
`#### Specs (dependency order)`, dispatched exactly `training-blocks` →
`plan-resolution` → `build-training-block` in three single-feature waves,
and left `performance-model-fit` untouched (brief only). That is the
workaround, not the fix -- the skill text still says `## Specs (dependency
order)` (singular H2) and has no gated/already-generated rules. Items (1)-(3)
above stand. Also for the fix: the roadmap checkbox means *implemented*
(commit `b370406`'s message), so Step 5's "mark completed specs as `[x]`"
should become "annotate as spec-written", the way b370406 and this run did.
