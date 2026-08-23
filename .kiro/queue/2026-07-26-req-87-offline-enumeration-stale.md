---
id: 2026-07-26-req-87-offline-enumeration-stale
title: Requirement 8.7's offline enumeration was not updated when Amendment 3 moved the [load] read into the pass
status: open
importance: low
importance_why: The invariant it states is true and enforced; only its list of what the pass reads is incomplete, so shipped source cites the criterion for a read the criterion does not name.
effort: S
kind: inconsistency
area: training-load, .kiro/specs/training-load/requirements.md
created: 2026-07-26
surfaced_by: /kiro-impl training-load (task 4.1, exhaustive requirement sweep)
pinned_at: c3d2201
resume_command: "do: extend requirements.md criterion 8.7's enumeration to include the resolved [load] configuration, which Amendment 3 moved into the load pass via Req 14.4, and confirm no other criterion enumerates the pass's reads"
context:
  - .kiro/specs/training-load/requirements.md
  - src/fitdocs/load/engine.py
  - .kiro/specs/training-load/design.md
blocked_by: []
---

## What

Requirement 8.7 states the load pass's offline guarantee by **enumerating what it
may read**:

> "The load pass shall operate fully offline, using only the data root's
> documents, archived sources, and the athlete profile."

Amendment 3 moved the `[load]` configuration read *into* the pass (Req 14.4:
read the table exactly once per invocation, inside `apply_load`). Task 4.1
implemented that. The enumeration in 8.7 was never extended, so it now omits one
of the things the pass reads.

Shipped source already cites the criterion for the wider set —
`src/fitdocs/load/engine.py:33-35` documents the pass as reading "the data root's
documents, archived sources, the athlete profile, and its own resolved
``[load]`` configuration (Req 8.7)". The code is right and the criterion is
narrower than the code it governs.

## Why it matters

Deliberately filed `low`. **The invariant itself is true and enforced**: the
`[load]` table lives inside the data root, so reading it breaks nothing about
offline operation, and `tests/load/test_feature_e2e.py::test_load_layer_imports_no_network_libraries`
pins the real guarantee. Nothing is broken and no behavior is wrong.

It is worth recording because 8.7 is written as a **closed list**, and a closed
list that omits a real read is the kind of thing a later reviewer reasonably
reads as a violation — or that a later implementer "fixes" by removing the
configuration read the design now requires. Four sibling specs are about to add
keys to that table, so the list will be consulted.

## Evidence

Verified in this run at `1b40c02` (branch `impl/training-load`):

- `requirements.md:355` (criterion 8.7) — enumerates only "the data root's
  documents, archived sources, and the athlete profile".
- `src/fitdocs/load/engine.py:33-35` — cites `(Req 8.7)` for a four-item list
  including "its own resolved ``[load]`` configuration".
- The read itself is at `src/fitdocs/load/engine.py:259-263`, pinned by
  `tests/load/test_engine.py::test_load_settings_document_is_read_exactly_once_per_invocation`
  (Req 14.4).

Surfaced by the task-4.1 reviewer during an exhaustive sweep of that task's 23
listed requirements; recorded rather than fixed because `requirements.md` lay
outside task 4.1's boundary.

## How to pick it up

1. Open `.kiro/specs/training-load/requirements.md` at criterion 8.7 and extend
   the enumeration with the resolved `[load]` configuration. Keep the sentence's
   shape — the closed-list form is deliberate and is what makes the criterion
   testable.
2. Check whether any **other** criterion enumerates the pass's reads and would
   drift the same way (grep for "archived sources" and "athlete profile" across
   `requirements.md` and `design.md`); if design.md carries a parallel list,
   move it in the same change.
3. This is a criterion **clarification**, not a new obligation — no behavior
   changes, no task is reopened, and nothing needs re-approval. Record it in
   `spec.json`'s `phase_note` the way the other in-place corrections were.
4. Done looks like: 8.7 names every source the implemented pass reads, and
   `engine.py:33-35`'s citation is accurate against the criterion it cites.
