---
id: 2026-10-17-inbox-recovery-availability
title: Correct the inbox guide's Recovery availability statement
status: open
importance: low
importance_why: The inbox guide calls an available standalone command future work.
effort: S
kind: docs
area: inbox documentation, recovery
created: 2026-10-17
surfaced_by: /kiro-validate-impl recovery post-Apple integration coverage audit
pinned_at: 240ed2f
resume_command: "do: Update docs/inbox.md to describe standalone Recovery as available while retaining future wording only for morning-of workout blocks."
context:
  - docs/inbox.md
  - docs/recovery.md
  - src/fitdocs/cli.py
blocked_by: []
---

## What
The wellness paragraph in docs/inbox.md still says “Recovery pages and
morning-of workout blocks remain future work.” Recovery now has its own
implemented standalone command and guide. Morning-of workout blocks remain
the separate planned workout-wellness feature.

## Why it matters
A reader using the inbox guide can conclude that Recovery is unavailable.
The command and dedicated Recovery guide already describe its actual behavior.

## Evidence
At 240ed2f, docs/inbox.md:86 contains the quoted sentence. Read-only
git-show checks in this run confirmed the same future-work characterization
at 700b32e (within a longer sentence) and the current sentence at Apple
main a885031. docs/recovery.md documents the command, and src/fitdocs/cli.py
registers recovery_command. This is an adjacent documentation follow-up,
not a rendering failure or a new scientific rule.

## How to pick it up
Read the wellness paragraph in docs/inbox.md beside docs/recovery.md.
Replace only Recovery's future-work wording with accurate availability and,
if useful, a relative link to the guide. Keep morning-of workout blocks
explicitly future work. Preserve the current Apple ZIP/XML import, source
precedence and inbox-ownership statements. Check the affected Markdown and
existing inbox/Apple documentation tests; no runtime change is needed.
