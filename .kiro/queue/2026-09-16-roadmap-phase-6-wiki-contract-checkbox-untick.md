---
id: 2026-09-16-roadmap-phase-6-wiki-contract-checkbox-untick
title: Roadmap Phase 6 wiki-contract Existing Spec Update is still unticked although both halves landed
status: open
importance: low
importance_why: A ticked box is how /kiro-queue decides the roadmap line is done; unticked, it keeps ranking finished work.
effort: S
kind: chore
area: .kiro/steering/roadmap.md, wiki-contract
created: 2026-09-16
surfaced_by: /kiro-impl training-blocks 4.5 (reviewer FOLLOW_UPS)
pinned_at: 68fe42e
resume_command: "do: tick .kiro/steering/roadmap.md:1098 (Phase 6 `#### Existing Spec Updates` wiki-contract) with 'landed by effort-tags as Amendment 1 and load-history as Amendment 2' in the style of the Phase 7 wiki-contract line (:1349)"
context:
  - .kiro/steering/roadmap.md
  - .kiro/specs/wiki-contract/spec.json
  - .kiro/specs/wiki-contract/requirements.md
blocked_by: []
---

## What
`.kiro/steering/roadmap.md:1098` -- `- [ ] wiki-contract — user-owned
frontmatter keys as a contract class with ...` under Phase 6 `#### Existing
Spec Updates` is unticked. Both halves landed on 2026-09-11: Amendment 1
(effort-tags, criteria 6.5-6.8) and Amendment 2 (load-history, 2.11/3.9),
recorded in `.kiro/specs/wiki-contract/spec.json` `amendments` and
`requirements.md:104-141`.

## Why it matters
Trivial, but the roadmap's Existing Spec Updates are read by `/kiro-queue`
as open work.

## Evidence
- `grep -n '^- \[ \] wiki-contract' .kiro/steering/roadmap.md` -> 1098 (the
  Phase 7 line at 1349 was ticked by training-blocks 4.5).
- `.kiro/specs/wiki-contract/spec.json` amendments entries dated 2026-09-11.

## How to pick it up
One-line edit on `main` (trivial per change-protocol triage), committed and
pushed. Not done by the training-blocks session because task 4.5 was
allowed exactly one roadmap edit and kiro-queue-add does not edit the
roadmap.
