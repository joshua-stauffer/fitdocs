---
id: 2026-08-18-adopt-enumeration-is-top-level-only
title: The .git enumeration is top-level only, so nested foreign state is neither carried nor surfaced
status: done
importance: low
importance_why: Measured absent today, but it is a silent scope limit on a halt whose entire purpose is to make the unanticipated visible.
effort: S
kind: gap
area: encumbered-content-purge, scripts/purge/adopt.py
created: 2026-08-18
surfaced_by: /kiro-impl encumbered-content-purge (task 7.3 review)
pinned_at: c3d2201
resume_command: "do: state the top-level-only scope of build_checklist's .git enumeration in the provenance record as a known limit, or extend the enumeration to the nested cases (custom hooks, non-default info/exclude)"
context:
  - scripts/purge/adopt.py
  - docs/reference/history-rewrites.md
blocked_by: []
---

## What

`build_checklist` enumerates the old `.git`'s entries at the **top level only**.
Foreign state nested inside a standard-furniture directory -- a custom hook in
`hooks/`, a non-default `info/exclude` -- is neither carried nor surfaced by
the halt.

## Why it matters

Low in practice and worth writing down anyway: the halt's whole purpose is to
make unanticipated `.git` residents visible before a one-shot replacement. A
scope limit that is invisible in the code reads as coverage it does not have.

The right resolution may well be "state the limit" rather than "extend the
enumeration" -- nested git-managed state is exactly what the fresh `.git`
should not inherit.

## Evidence

Reported by the task 7.3 reviewer as a scope note explicitly classified not a
defect, having measured the current state: `hooks/` holds only `.sample` files
and `info/exclude` is default, so nothing is silently lost today.

Confirmed at `0a6535d`: `build_checklist`'s enumeration uses a single
`iterdir()` over the old git directory, with no recursion.

## How to pick it up

Decide which resolution applies. If stating the limit, it belongs in the
provenance record alongside the other given-up-capability notes, phrased as a
property of the enumeration rather than a defect. If extending it, the halt
must stay a halt -- do not let a nested entry become a silent carry. Done when
the limit is either closed or recorded.

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
