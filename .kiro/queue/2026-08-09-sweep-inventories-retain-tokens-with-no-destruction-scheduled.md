---
id: 2026-08-09-sweep-inventories-retain-tokens-with-no-destruction-scheduled
title: The sweep inventories retain identifying tokens in their matched column, are consumed by nothing after adoption, and no task destroys them
status: open
importance: low
importance_why: They live outside the repository so they breach nothing, but the provenance record states probe sets are destroyed with the material, and these are token-bearing files that outlive it with no owner.
effort: S
kind: gap
area: encumbered-content-purge
created: 2026-08-09
surfaced_by: reviewer subagent during /kiro-impl encumbered-content-purge (review of the artifact reconstruction and task 7.1)
pinned_at: 8391e47
resume_command: "do: Decide the disposition of the two sweep inventories and the evasion-acceptance record after the rewrite lands -- destroy them with the material as history-rewrites.md says probe sets are, or state explicitly why they are retained and for how long."
context:
  - scripts/purge/adopt.py
  - docs/reference/history-rewrites.md
blocked_by: []
---

## What

`~/.fitdocs-purge/sweep-inventory.tsv` and `sweep-inventory-at-3.2.tsv` carry
identifying tokens verbatim in their `matched` column — that is what makes them
useful as an inventory. Neither they nor `evasion-acceptance.txt` appear in
`scripts/purge/adopt.py`'s `_REQUIRED_SCRATCH_LABELS`, which is exactly
`commit-map`, `first-changed-commits`, `forbidden-string-file`, `m0-manifest`,
`m1-manifest`, `prior-map-rows`, `spec-status-baseline`, `suboptimal-issues`.

So nothing after the adoption boundary consumes them, and no task schedules
their destruction.

## Why it matters

`docs/reference/history-rewrites.md:80-82` states that probe sets are
"destroyed with the material rather than retained". These files are the same
kind of artifact and they currently outlive it, indefinitely, with no owner.

This is not a breach — they are outside the repository by construction, which
is where they belong, and the forbidden-string source is retained there
deliberately for the standing guard. The gap is that their retention is
accidental rather than decided, which is the same class of problem as the
artifact loss: no one owns the file's lifetime.

## Evidence

- `scripts/purge/adopt.py:108-116` — `_REQUIRED_SCRATCH_LABELS`, which omits
  all three. **Superseded 2026-08-18 at `0a6535d`**: task 7.3 deleted that
  constant when Decision 7 re-scoped the carry-over checklist to the
  `.git`-resident items. The citation no longer resolves, and with it goes the
  only mechanism that enumerated these artifacts at all — which strengthens
  this item rather than resolving it: nothing now names the sweep inventories,
  so nothing owns their lifetime. The retention is still accidental.
- `~/.fitdocs-purge/sweep-inventory*.tsv` — token-bearing `matched` column
- `docs/reference/history-rewrites.md:80-82` — the stated destruction posture

## How to pick it up

Decide, do not default. Either destroy the two inventories and the evasion
record once Major 8 completes and the provenance record has absorbed what they
prove, or record in `history-rewrites.md` that they are retained, where, and
why the stated probe-set posture does not apply to them.

Note the forbidden-string source is a separate case with a live consumer (the
standing guard) and should not be swept up in this decision.

Done when their lifetime is written down.
