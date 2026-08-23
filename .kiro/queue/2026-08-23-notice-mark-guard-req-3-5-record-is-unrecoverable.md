---
id: 2026-08-23-notice-mark-guard-req-3-5-record-is-unrecoverable
title: The notice/mark tip guard has no recorded Req 3.5 mutation, and the commits that carried it were destroyed by the history replacement
status: open
importance: medium
importance_why: Req 3.5 is undischarged for a surviving guard and cannot be discharged the way this spec discharges it, because the medium was a commit message and those commits no longer exist. Someone must rule on what replaces it, or the criterion stays open forever with no owner.
effort: S
kind: gap
area: encumbered-content-purge, tests
created: 2026-08-23
surfaced_by: /kiro-impl encumbered-content-purge task 9.4 (per-survivor ledger); upheld by two independent reviewers
pinned_at: c786326
resume_command: "do: rule on how Req 3.5 is discharged for the notice/mark tip guard, whose recorded mutation was destroyed with the pre-replacement commits -- either record a fresh mutation in the provenance record or declare the criterion permanently undischarged for it"
context:
  - docs/reference/history-rewrites.md
  - tests/test_forbidden_strings.py
  - tests/_forbidden_strings.py
  - .kiro/specs/encumbered-content-purge/requirements.md
blocked_by: []
---

## What

Task 9.4's per-survivor ledger re-ran every surviving guard's recorded
single-line mutation. One survivor has no recorded mutation to re-run: the
notice/mark tip guard —
`tests/test_forbidden_strings.py::test_the_notice_phrase_and_mark_are_absent_from_every_tracked_file`,
built on `tests/_forbidden_strings.py::_count_notice_phrase`.

It was built at task 6.5 and moved into the surviving guard module at task 7.2.
`tasks.md` task 7.2's own body claims the mutation act was performed.

## Why it matters

This is not a misplaced record. **It is unrecoverable in the medium this spec
uses.**

`docs/reference/history-rewrites.md` records how Req 3.5 is discharged here,
quoting commit `7f447da`: *"Req 3.5 is a commit-message act and is UNPINNED;
this message is the act."* The guard's own act lived in tasks 6.5 and 7.2's
commit messages — and the history replacement at task 8.2 destroyed every
pre-replacement commit. `HEAD` now reaches six commits from the fresh root.

So the guard is alive but undocumented, and no amount of searching will find
the record. A mutation invented today is **new evidence, not the missing
record** — which is why task 9.4 declined to treat its own supplementary probe
as a discharge, and why both reviewers upheld that as the right call rather
than an evasion.

The guard itself is fine. Task 9.4 ran a supplementary probe: mutating
`_count_notice_phrase`'s `for index in range(len(chunks) - span + 1):` to
`range(0)` reds the guard's own planted positive control as a sole failure,
and reverts green. Both 9.4 reviewers reproduced it.

## Evidence

Absence verified three independent ways by the task 9.4 reviewer:

- no mention in `docs/reference/history-rewrites.md` (the only hits are task
  9.4's own ledger entry and descriptive references)
- nothing in `_count_notice_phrase`'s docstring, nor the guard test's
- nothing in any of the six commit messages reachable from `HEAD`

The § "Guard re-basing: mutation evidence (tasks 4.1-4.3)" section covers only
`221d60a`, `f1dad15` and `7f447da` — none reaching a guard built at task 6.5.

Task 7.2's claim is verbatim and accurate as a claim
(`.kiro/specs/encumbered-content-purge/tasks.md`, task 7.2 body), and 7.2 is
`[x]`.

## How to pick it up

This is a ruling, not a repair. Two honest options:

1. **Record a fresh mutation.** Run the probe above (or design one), and write
   it into the provenance record's ledger as a *2026-08-23 re-derivation*,
   stated as such — not backdated, and not presented as the task 6.5 act.
   Req 3.5 then has a durable record again, in the record rather than in a
   commit message, which is the medium that survives a replacement.
2. **Declare it permanently undischarged.** Write into the record that this
   guard's Req 3.5 act existed, was made in a commit message, and was destroyed
   by the replacement — an accepted, stated loss under the same pattern the
   record already uses for the other declared losses.

Either is defensible. Leaving it unstated is not: task 9.4's ledger currently
says the criterion "remains open", which is true and needs an owner.

Note the related, *stronger* weakness in the same guard, already tracked
separately at
`.kiro/queue/2026-08-18-notice-guard-count-anchor-survives-a-narrowing.md`.
Do not re-file it; consider fixing both together if you are in this code.

Done when the record states which option was chosen and why.
