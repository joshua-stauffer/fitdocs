---
id: 2026-08-18-row-names-carries-a-name-no-function-emits
title: ROW_NAMES lists "fresh clone clean" but no function emits it as a RowResult row
status: done
importance: low
importance_why: A task-7.6 driver enumerating rows from this tuple finds one name with no producer, and would either skip it silently or report a row that never ran.
effort: S
kind: inconsistency
area: encumbered-content-purge, scripts/purge/verify.py
created: 2026-08-18
surfaced_by: /kiro-impl encumbered-content-purge (task 7.4 review round 2)
pinned_at: c3d2201
resume_command: "do: at task 7.6, decide whether ROW_NAMES' 'fresh clone clean' entry gains a producing RowResult or is dropped from the tuple, so a driver enumerating rows finds a producer for every name"
context:
  - scripts/purge/verify.py
  - .kiro/specs/encumbered-content-purge/design.md
blocked_by: []
---

## What

`ROW_NAMES` in `scripts/purge/verify.py` carries `"fresh clone clean"` as an
entry, but no function ever emits it as a `RowResult.row`. `check_fresh_clone`
returns four rows that reuse **other** functions' labels (tree identity,
path/blob token, message token, old identifiers refused). By contrast
`check_built_artifacts` does emit `"artifacts clean"`.

## Why it matters

Task 7.6 builds the replacement driver, which is the first consumer to
enumerate rows programmatically. A driver iterating `ROW_NAMES` and matching
against emitted `RowResult.row` values finds one name with no producer — and
would either skip it silently or report a row that never ran. Neither is what
a one-shot acceptance procedure wants.

The module's docstring is careful not to claim otherwise, so this is a shape
problem rather than a false statement.

## Evidence

Reported by the task 7.4 reviewer, which read every `row=` literal in the
module while re-deriving the 9/4/5 count independently: nine single-`RowResult`
functions each emit a literal `ROW_NAMES[0..8]` entry; `check_fresh_clone`
returns four of those same labels rather than its own.

Confirmed present in the task 7.4 diff at `scripts/purge/verify.py`
(`ROW_NAMES` definition and `check_fresh_clone`'s return).

## How to pick it up

At task 7.6, when the driver starts consuming rows, decide: either
`check_fresh_clone` emits its own summary `RowResult` labelled
`"fresh clone clean"` alongside the four it forwards, or the name leaves
`ROW_NAMES` and the design table's fresh-clone row is understood as a
composition rather than a row. Done when every name in the tuple has a
producer.

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
