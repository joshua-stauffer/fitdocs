---
id: 2026-10-17-inbox-recovery-availability
title: Correct the inbox and wellness guides' Recovery availability statements
status: open
importance: low
importance_why: The inbox guide calls an available standalone command future work.
effort: S
kind: docs
area: inbox documentation, recovery
created: 2026-10-17
surfaced_by: /kiro-validate-impl recovery post-Apple integration coverage audit
pinned_at: 240ed2f
resume_command: "do: Update docs/inbox.md and docs/wellness.md to describe standalone Recovery (and HR benchmark derivation) as available while retaining future wording only for morning-of workout blocks."
context:
  - docs/inbox.md
  - docs/wellness.md
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

## Update (2026-10-17, Phase 12 re-validation)
The same stale characterization is in `docs/wellness.md` at 160b007:
- lines 5-6: "Recovery pages and workout morning blocks are future work.";
- lines 496-498: "...owes Garmin attribution, as the future recovery page and
  morning-of block will give it." The recovery page now gives it
  (`docs/recovery.md` § Garmin attribution);
- lines 511-512: "Recovery baselines, scores, benchmark derivation and new
  pages are not provided by this file import feature." This is true of the
  import feature itself, but reads as if they do not exist. Recovery
  baselines and HR benchmark derivation (`derive-benchmarks`) have landed.
  Consider linking `docs/recovery.md` and `docs/configuration.md`.
Morning-of workout blocks remain future work (workout-wellness, open).
