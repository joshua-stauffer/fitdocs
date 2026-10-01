---
id: 2026-10-01-held-warning-names-paths-the-run-then-renames
title: A held-file warning names its candidate pages by their pre-rename paths while the hold record is rewritten to the final ones, and the task-then-settle rename order is pinned only by a direct unit call
status: open
importance: low
importance_why: The warning is the only message the user sees at hold time, and it can name a page that no longer exists; the record and `fitdocs check` are right, so the harm is a misleading line, not lost data.
effort: S
kind: bug
area: activity-identity, src/fitdocs/sync.py, tests/test_identity_e2e.py
created: 2026-10-01
surfaced_by: /kiro-impl activity-identity
pinned_at: fc5c06d
resume_command: "/kiro-impl activity-identity [queue: .kiro/queue/2026-10-01-held-warning-names-paths-the-run-then-renames.md] Make a run's held-file warnings follow the run's renames like the hold record does, and pin the rename-map order end to end"
context:
  - src/fitdocs/sync.py
  - tests/test_identity_e2e.py
  - .kiro/specs/activity-identity/design.md
blocked_by: []
---

## What
Two linked gaps in how held candidates follow renames.
1. The warning is built when the file is held (`_held_detail(entry)`, with the
   candidates as they were at plan time) and is never rewritten. At the end of
   the run `_finish_holds` rewrites the *record* through the run's renames, and the
   settle pass rewrites `warning.doc` of the rename warnings, but nothing
   rewrites the candidate paths inside a held warning's `detail`.
2. `_finish_holds(data_root, holds, task_renames, settle_renames)` applies the
   maps in order, so a page moved `a -> b` by a task and `b -> c` by the settle
   pass is recorded at `c`. The only test of that order calls `_finish_holds`
   directly with literal maps; the call sites' argument order (three of them)
   is not pinned by any run that has both a task rename and a settle rename.

## Why it matters
A user reading the run output is told to look at a page path that was renamed
in the same run (the same output also prints the rename warning, which makes the
mismatch confusing), while `fitdocs check` and `.fitdocs/held.toml` name the new
path. The ordering gap means a swap at a call site would pass the whole suite.

## Evidence
Reproduced at `fc5c06d` using the helpers of
`tests/test_identity_e2e.py::test_held_candidates_follow_a_rename_the_same_drain_makes`
(`_sync_files`, the re-export pair, an ambiguous Garmin run), synced as one run:
- pages `2043-11-13-run-1613.md` and `2043-11-13-run-1713.md` become
  `2043-11-13-run-1613.md` and `2043-11-13-run-1613-14151617.md`;
- the held warning reads `could be the same session as
  workouts/2043-11-13-run-1613.md, workouts/2043-11-13-run-1713.md`, while
  `load_holds(data_root).entries[0].candidates` is
  `('workouts/2043-11-13-run-1613.md', 'workouts/2043-11-13-run-1613-14151617.md')`.
- Code: `src/fitdocs/sync.py:1618` (warning appended with `_held_detail(entry)`),
  `:1621-1628` `_held_detail`, `:1631-1657` `_finish_holds` (record only), `:2195-2200`
  the settle pass rewrites `warning.doc` only; call sites `:638`, `:987`, `:1222`.
- Pins: the record is pinned at `tests/test_identity_e2e.py:2010`
  (settle rename) and `:2370-2402` (task rename); the order only at `:2095-2113`
  (`_finish_holds(tmp_path, holds, {"a": "b"}, {"b": "c"})`). None asserts on the
  warning text, and none run has a task rename and a settle rename together.
  The order claim is by reading; the mutation (swap the two arguments at a call
  site) was not run.

## How to pick it up
1. Extend the `:2370` test to assert the held warning's candidate paths equal
   the final pages (it reds today), then fix by building the held warning after
   the renames are known (hold tasks return the entry; format at the end of the
   run) or by rewriting candidate paths in the pending warnings with the same
   `follow` map `_finish_holds` uses.
2. Add one e2e run with both a base-change rename and a settle rename of a page
   a hold names, asserting the record and the warning name the final path; run
   the mutation swapping `task_renames` and `settle_renames` at one call site and
   see it red.
