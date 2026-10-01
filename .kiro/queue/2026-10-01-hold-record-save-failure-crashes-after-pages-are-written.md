---
id: 2026-10-01-hold-record-save-failure-crashes-after-pages-are-written
title: A failing hold-record save at the end of sync, drain or regen raises out of the command after every page was already written, losing the run's report
status: open
importance: low
importance_why: Needs an unwritable `.fitdocs/` (permissions, full disk), but then the user gets a traceback, no report, and a data root that is half-updated with the hold record stale.
effort: S
kind: bug
area: activity-identity, src/fitdocs/sync.py, src/fitdocs/identity/holds.py
created: 2026-10-01
surfaced_by: /kiro-impl activity-identity
pinned_at: fc5c06d
resume_command: "/kiro-impl activity-identity [queue: .kiro/queue/2026-10-01-hold-record-save-failure-crashes-after-pages-are-written.md] Turn an end-of-run hold-record save failure into a reported failure that still returns the run's report"
context:
  - src/fitdocs/sync.py
  - src/fitdocs/identity/holds.py
  - .kiro/specs/activity-identity/design.md
blocked_by: []
---

## What
Holds are recorded as each file is held (`_hold_task` catches a save failure and
fails that file, before archiving it), but two later saves are unguarded:
`_finish_holds` (rewrites candidates through the run's renames) and, in `regen`,
the closing `save_holds` that replaces or empties the record. `save_holds`
raises `OSError` when it cannot write. Both run after the page tasks and the
settle pass, so every page write has already happened when the exception leaves
`sync`, `drain` or `regen`, and the caller never receives a `SyncReport`.

## Why it matters
The failure mode is a traceback instead of the per-file or run-level failure
the rest of the engine reports (Req 1.3 "the batch never aborts"), and the user
cannot tell from it what changed on disk. The record is left naming pre-rename
paths or stale entries, to be rebuilt by the next successful regen.

## Evidence
Reproduced at `fc5c06d` for the regen path.
- `src/fitdocs/sync.py:1631-1657` `_finish_holds` (`save_holds` at `:1656`, no
  handler); call sites `:638` (sync), `:987` (drain), `:1222` (regen);
  `:1223-1227` the closing `save_holds(data_root, holds.record)` in regen.
  `src/fitdocs/identity/holds.py:171-204` `save_holds` re-raises
  (`except BaseException: tmp_path.unlink(...); raise`).
- Repro: sync the builder's `run_fit_bytes()` into a data root, write a
  `.fitdocs/held.toml` with one entry via `save_holds`, tamper the page's
  generated `## Summary` heading, `chmod 555 .fitdocs`, run `fitdocs regen`.
  Result: exit 1 with `PermissionError` from `sync.py:1227 in regen` ->
  `identity/holds.py:197 in save_holds`; the tampered heading is gone (the page
  was rewritten before the crash) and no report is printed. The `sync` and drain
  call sites were not run; they share `_finish_holds`.

## How to pick it up
1. Wrap both saves so an `OSError` becomes a `FileFailure` (naming
   `.fitdocs/held.toml`) appended to the run's failures, and the report still
   returns; for sync/drain decide the exit status that follows.
2. Pin with the repro (the permission change is portable on POSIX; skip on
   Windows) for regen and for a sync with a rename that needs the rewrite.
3. Check `drain`'s disposition logic: a held file whose record could not be
   updated must not be moved out of the inbox as processed.

## Open questions
- Should the failure be per-run (one new failure entry) or abort-before-writes
  by checking that `.fitdocs/` is writable up front? The first is the smaller change.
