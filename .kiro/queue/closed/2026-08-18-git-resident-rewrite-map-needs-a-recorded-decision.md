---
id: 2026-08-18-git-resident-rewrite-map-needs-a-recorded-decision
title: The carry-over halt will stop Major 8 on a cleartext-address file in .git, and the decision is unwritten
status: done
importance: high
importance_why: A designed halt fires mid-replacement on a file carrying a personal address; deciding it under time pressure at the swap is exactly the wrong moment.
effort: S
kind: gap
area: encumbered-content-purge, scripts/purge/adopt.py
created: 2026-08-18
surfaced_by: /kiro-impl encumbered-content-purge (task 7.3 implementation and review)
pinned_at: c3d2201
resume_command: "do: record the disposition of .git/sha-rewrite-map-2026-07-26.tsv (leave it in the archive, never carried) in the provenance record's stated-positions section, so task 8.2's carry-over halt has a written answer before it fires"
context:
  - scripts/purge/adopt.py
  - .kiro/specs/encumbered-content-purge/design.md
  - docs/reference/history-rewrites.md
blocked_by: []
---

## What

Task 7.3's re-scoped `build_checklist` halts on any `.git`-resident entry no
checklist item anticipates. Against the real repository it will halt on
`sha-rewrite-map-2026-07-26.tsv` -- the second, untracked copy of the prior
rewrite map, sitting directly in `.git`.

The halt is correct behaviour. What is missing is the written decision it
halts *for*.

## Why it matters

The file carries a personal address in cleartext. Under Decision 7 the old
`.git` is archived rather than deleted, so the file goes to the archive --
covered by Req 11.13's recorded-acceptance position (never tracked, never
published). It must never reach the fresh `.git`.

Task 5.5's text already ruled on it ("never carry ... the second untracked
copy of the rewrite map, which carries the maintainer's address in
cleartext"), but that ruling belongs to the retired clone-adoption mechanism
and is not stated anywhere the replacement run will look. A halt with no
written answer invites an operator to improvise one mid-swap.

## Evidence

Measured 2026-08-18 against `$(git rev-parse --git-common-dir)`:

- exactly three non-standard entries: `agent-log`, `lost-found`,
  `sha-rewrite-map-2026-07-26.tsv`
- the third is 27,927 bytes / 187 lines, hits 2 forbidden values, and
  contains 2 distinct email-shaped tokens (checked without printing content)

The reviewer drove the real path through `uv run pytest` and observed:

    CarryOverError: build_checklist found .git-resident entry no checklist
    item anticipates: ['sha-rewrite-map-2026-07-26.tsv'] -- halting for a
    decision

and confirmed by mutation that even with the halt bypassed, the function
returns a literal one-element tuple containing only the agent-log item -- so
no code path carries the file into the fresh `.git`.

## The ordering defect, stated plainly

Added 2026-08-18 by the task 7.7 session, because the sequencing — not just the
missing text — is the problem.

The destination this item names is the provenance record's stated-positions
section, and **task 9.2 owns that document. 9.2 runs in Major 9, after Major
8.** So as the plan is currently sequenced, no task writes the answer before
8.2 is the task that needs it. The halt fires during the one-shot, and the
written answer arrives a major later.

This is a plan-level ordering defect, not only an unwritten decision. Either a
Major 8 task must carry the disposition (8.1, the certification task, is the
natural home — it is the last point before the swap), or the decision must be
recorded outside the provenance record ahead of 8.2 and merely *restated* by
9.2. Deciding which is the pickup work.

## How to pick it up

Write the disposition into the provenance record's stated-positions section,
and additionally resolve the ordering defect above so the answer exists before
8.2 rather than after Major 8. State it by role, never by path-plus-content.
Done means an operator hitting the halt at 8.2 finds a written answer instead
of making one.

## Resolution

**Closed `done` 2026-08-23 — the subject was retired, and retirement is the
resolution.** Post-purge queue triage after `encumbered-content-purge`
completed (spec 57/57, `87ce085`).

This item's subject was the purge's own one-shot tooling: a module under
`scripts/purge/`, a test under `tests/purge/`, or a precondition on a purge
task that has since run. Task 9.3 (`c18ec26`) deleted `scripts/` entire and
`tests/purge/` less three relocations; `ls scripts/ tests/purge/` errors on
`HEAD`. The operation those modules governed — sweep, redact, replace, adopt,
verify — executed to completion and is not repeatable: the history replacement
is a fresh root (`c3d2201`) with no mapping by construction.

There is therefore no future run for this defect to affect, and no code left to
carry it. The retirement record is `docs/reference/history-rewrites.md` § 8.

Checked before closing: the item's subject does not survive in the three
relocated guards (`tests/_forbidden_strings.py`, `tests/test_forbidden_strings.py`,
`tests/_content_oracle.py`). Items whose subject *did* survive were kept open
in the same triage.
