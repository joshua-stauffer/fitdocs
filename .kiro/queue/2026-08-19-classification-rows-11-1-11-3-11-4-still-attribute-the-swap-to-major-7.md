---
id: 2026-08-19-classification-rows-11-1-11-3-11-4-still-attribute-the-swap-to-major-7
title: "Classification rows 11.1/11.3/11.4 in history-rewrites.md still say \"unreached before Major 7\" / \"a Major 7 transform\" for at-any-commit and commit-message properties that are Major 8's event"
status: open
importance: medium
importance_why: Same false-attribution pattern task 7.8's 2026-08-19 remediation round just fixed on rows 7.1, 7.2 and 10.3 (Major 7 vs Major 8), left uncorrected on three more rows in the same table this round did not touch.
effort: S
kind: inconsistency
area: encumbered-content-purge, docs/reference/history-rewrites.md
created: 2026-08-19
surfaced_by: /kiro-impl encumbered-content-purge 7.8 (remediation round for a REJECTED classification half)
pinned_at: c3d2201
resume_command: "/kiro-impl encumbered-content-purge 7.8 [queue: .kiro/queue/2026-08-19-classification-rows-11-1-11-3-11-4-still-attribute-the-swap-to-major-7.md] Re-attribute rows 11.1, 11.3 and 11.4 from Major 7 to Major 8, matching the 7.1/7.2/10.3 correction pattern"
context:
  - docs/reference/history-rewrites.md
  - .kiro/specs/encumbered-content-purge/requirements.md
  - .kiro/specs/encumbered-content-purge/tasks.md
blocked_by: []
---

## What

`docs/reference/history-rewrites.md`'s "Classification of all 81 requirement
criteria" table has three rows that name Major 7 as the event that must
complete before their criterion becomes reachable:

- Row 11.1: "...scoped to the working tree today, the at-any-commit-in-history
  half is unreached before Major 7"
- Row 11.3: "Commit-message rewriting is a Major 7 transform; has not run"
- Row 11.4: "...the at-any-commit claim over all of history is unreached
  before Major 7"

All three concern Req 11.1/11.3/11.4, each of which reads "at any commit
reachable from any ref" — a property that becomes true only once the
history replacement (the fresh-root swap) has actually run. Under Amendment
1's regenerated plan, Major 7 (tasks 7.1-7.7, all `[x]` on this branch) only
re-scopes the replacement *machinery* — it performs no history operation
against the working repository. The actual swap that makes an at-any-commit
property true is Major 8 (`tasks.md` task 8.2, `[ ]`, unrun), the same
mis-attribution the 2026-08-19 remediation round of task 7.8 just corrected
on rows 7.1, 7.2 and 10.3 ("the same posture 7.1/7.2 already state for their
own Major-8-dependent criteria").

Row 11.3's "Commit-message rewriting is a Major 7 transform" is doubly
stale: under the retired in-place-rewrite plan every commit's message was
rewritten across history (a Major 7 task in the old numbering); under the
amended fresh-root plan there is no per-commit message rewriting left at
all — there is exactly one new root commit, whose single message is
checked once (task 8.2's observable: "The root message through the token
matcher"). The row's own vocabulary ("rewriting", plural, across history)
may need correcting alongside the Major-number fix.

## Why it matters

The durable provenance record misattributes which Major makes these three
criteria reachable, in the same direction and for the same underlying reason
the reviewer already rejected this task's first pass over 7.1, 7.2 and 10.3.
A reader following this table to decide "has this become true yet" would
watch Major 7 finish (it already has, on this branch) and wrongly expect
these three criteria to be reachable, when in fact nothing changes until
Major 8's task 8.2 runs.

## Evidence

- `tasks.md`: task 7.1-7.7 all `[x]`; task 8.2 ("Run the gated replacement
  through the swap") `[ ]`, tagged `_Requirements: 1.7, 5.3, 6.1, 6.2, 6.3,
  6.4, 6.5, 6.6, 7.1, 7.7, 10.3, 11.1, 11.2, 11.3, 11.4, 11.13_` — Req
  11.1/11.3/11.4 are explicitly tagged to task 8.2, not to any Major 7 task.
- `requirements.md` Requirement 11, criteria 1/3/4: each begins "When the
  purge is complete, no [file/commit message] at any commit reachable from
  any ref shall...".
- `docs/reference/history-rewrites.md` rows 11.1, 11.3, 11.4 (current text,
  quoted above).
- The correction pattern this queue item asks to extend: the same file's
  rows 7.1, 7.2 and 10.3, corrected in this round with the citation "Req 7.1
  is carried by task 8.2 ... Req 7.2 by task 8.3 ... Major 8, not Major 7".

## How to pick it up

1. Re-read Req 11.1/11.3/11.4 and confirm which task(s) in the current
   `tasks.md` carry each (grep `_Requirements:.*\b11\.[134]\b`).
2. Re-verify task 8.2 is still `[ ]` and still the task tagged with these
   criteria before editing anything (do not assume this queue item's
   snapshot is still current).
3. Correct rows 11.1, 11.3 and 11.4 in place, following the same
   "Corrected in place" citation style the 7.1/7.2/10.3 rows already use,
   and re-verify row 11.3's "rewriting" vocabulary against task 8.2's
   observable for the root commit message check.
4. Do not change any label (PINNED/UNPINNED) — this is a Major-number and
   vocabulary correction, not a re-classification.

## Open questions

None — the correction pattern to follow already exists in the same table.
