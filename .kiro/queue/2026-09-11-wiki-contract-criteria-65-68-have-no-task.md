---
id: 2026-09-11-wiki-contract-criteria-65-68-have-no-task
title: wiki-contract criteria 6.5-6.8 were added to a spec whose task list is fully closed
status: open
importance: low
importance_why: A future spec-status on wiki-contract reports complete against requirements that grew afterwards, with nothing mechanical tying the new criteria to their implementer.
effort: S
kind: spec-work
area: .kiro/specs/wiki-contract, .kiro/specs/effort-tags
created: 2026-09-11
surfaced_by: /kiro-validate-impl effort-tags (task 5.3 feature validation)
pinned_at: d1147a0
resume_command: "do: decide how an amended spec records that criteria added after completion are implemented by another spec"
context:
  - .kiro/specs/wiki-contract/requirements.md
  - .kiro/specs/wiki-contract/tasks.md
  - .kiro/specs/wiki-contract/spec.json
  - .claude/skills/kiro-spec-status/SKILL.md
blocked_by: []
---

## What

effort-tags task 4.3 added criteria 6.5-6.8 to `wiki-contract`'s requirements
document via an Amendment block, as the roadmap's Phase 6 Existing Spec Update
prescribes. `wiki-contract`'s `tasks.md` is 24/24 `[x]` and was deliberately not
touched -- effort-tags implements the new criteria, and the `amendments` entry
in `spec.json` says so in prose.

Nothing mechanical connects them. `/kiro-spec-status wiki-contract` reports a
fully-complete spec whose requirements grew after completion.

## Why it matters

This is the first Existing Spec Update in the repo to amend a *closed* spec, so
the convention it sets will be copied. The failure mode is not today -- today the
criteria are implemented and validated -- it is a year from now, when someone
reads wiki-contract's requirements, sees 6.5-6.8, sees 24/24 tasks complete, and
concludes those criteria were implemented by wiki-contract itself. Any question
about why they behave as they do leads to the wrong spec's design document.

The generic question is worth answering once: when an amendment adds criteria to
a completed spec, what records the implementer -- a task stub marked complete
with a pointer, a convention in the amendment block, or something
`/kiro-spec-status` learns to read?

## Evidence

At `e39b35f`:
- `git diff --name-only main..HEAD -- .kiro/specs/wiki-contract/tasks.md` is
  empty; the file is 24/24 `[x]`
- `.kiro/specs/wiki-contract/spec.json` `amendments` grew 2 -> 3, new entry
  dated 2026-09-11 with `requirement: "6.5, 6.6, 6.7, 6.8 (new)"`
- the `### Requirement 6` block diff is `10a11,14` -- four pure additions,
  existing items byte-identical, nothing renumbered

## How to pick it up

1. Read the amendment block in `.kiro/specs/wiki-contract/requirements.md` and
   the `amendments` entry in its `spec.json` -- the intent is recorded, only the
   mechanism is missing.
2. Check whether the other two existing amendments have the same shape; if they
   amended an *open* spec, this is genuinely a new case.
3. Decide the convention and apply it to all three, then say so in
   `.kiro/steering/` or the `kiro-spec-status` skill so the next amendment
   inherits it rather than inventing a fourth shape.

Done looks like: a reader of a completed, amended spec can tell which spec
implements each post-completion criterion, without reading another spec's
tasks.md.
