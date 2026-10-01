---
id: 2026-10-01-regen-writes-over-or-beside-an-unreadable-page
title: regen plans the archive file of a page whose frontmatter is unreadable, writing a duplicate page beside it or a fresh page over it and dropping the user's notes
status: open
importance: high
importance_why: Silent loss of user-written notes (regen exits 0 with zero warnings) and a duplicate page for one activity; the pre-existing collision rule has only one suffix level and never checks the path it is about to write.
effort: M
kind: bug
area: activity-identity, workout-docs, src/fitdocs/sync.py, src/fitdocs/layout.py
created: 2026-10-01
surfaced_by: /kiro-impl activity-identity
pinned_at: fc5c06d
resume_command: "/kiro-impl activity-identity [queue: .kiro/queue/2026-10-01-regen-writes-over-or-beside-an-unreadable-page.md] Make a page task never write over an existing file it did not match, and report a workouts page the scan cannot read"
context:
  - src/fitdocs/sync.py
  - src/fitdocs/layout.py
  - src/fitdocs/identity/pages.py
  - .kiro/specs/activity-identity/design.md
  - .kiro/specs/activity-identity/requirements.md
  - .kiro/queue/2026-10-01-parse-frontmatter-raises-on-unconstructible-yaml-values.md
blocked_by: []
---

## What
A `workouts/*.md` page whose frontmatter does not parse is skipped by
`scan_pages` ("not a fitdocs document", wiki-contract Req 1.2). `regen` then
finds the page's archive file listed by no page, plans it as a new activity and
seeds a new page. The new page's path comes from `doc_stem(..., taken)`, whose
collision rule has one level: if the computed stem is taken it appends
`-<uid[:8]>` and never checks whether *that* path exists. Two outcomes follow,
both on `main` and both reproduced:
1. The garbled page sits at its computed stem: regen leaves it and writes a
   second page at `<stem>-<uid8>.md`. One activity, two pages, no warning.
2. The garbled page sits at the suffixed name `<stem>-<uid8>.md` (a page that
   was itself a collision page, or a user's rename to that name) while
   `<stem>.md` is occupied: the new page's target is the garbled page's own
   path, and it is overwritten. With no match there is no `merge_regions`, so
   the user's notes region is replaced by the placeholder.

## Why it matters
Outcome 2 destroys user-written content silently: exit 0, `Written 1`,
`Warnings 0`. The ownership contract promises notes survive regeneration; a
page that has become unreadable to the scan (a bad YAML edit, or the
`date: 2026-02-30` class in the sibling item once that is fixed to return
`None`) is exactly when the user most needs that promise kept. Outcome 1 leaves
two pages for one activity that `fitdocs check` does not connect (the garbled
page is not scanned).

## Evidence
Read and reproduced at `fc5c06d`.
- `src/fitdocs/sync.py:1933-1939` `taken()` is `candidate_path.exists()` (false
  for a path the task itself will match); `:1941-1944` `unsuffixed` / `stem`;
  `:1953-1954` with `match is None`, `target = doc_path(data_root, stem)` with no
  existence check; `:2023` `merge_regions` runs only `if existing_text is not None`.
- `src/fitdocs/layout.py:239-241`: `if taken(base): return f"{base}-{uid[:8]}"` -
  one suffix level, the suffixed path is not tested.
- `src/fitdocs/sync.py:1190-1195` regen plans `_unreferenced_archives(...)`;
  `src/fitdocs/identity/pages.py:83-86` skips a page whose
  `read_frontmatter` is `None`. The unreferenced-archive planning predates the
  spec (`git show c3d2201:src/fitdocs/sync.py` already has
  `_unreferenced_archives` at line 1400).
- Repro, outcome 1: `sync` the builder's `run_fit_bytes()` into a fresh data
  root, edit its page so frontmatter has `tags: [unclosed` and the notes region
  holds `MY IMPORTANT NOTE`, run `fitdocs regen --out <root>`:
  `Written: workouts/2021-09-08-run-0346-399c333e.md`, `Warnings 0`; the garbled
  `2021-09-08-run-0346.md` still holds the note, the new page has the placeholder.
- Repro, outcome 2: same, but save the garbled page as
  `2021-09-08-run-0346-399c333e.md` and put any other file at
  `2021-09-08-run-0346.md`; `fitdocs regen` reports
  `Written: workouts/2021-09-08-run-0346-399c333e.md`, exit 0, and
  `grep -c "IMPORTANT NOTE"` on every page returns 0.

## How to pick it up
1. Write the failing e2e tests first (`tests/test_identity_e2e.py` has the
   `_sync_files` / `_pages` helpers): outcome 2 must not lose the note, and
   neither outcome may complete silently.
2. Smallest safe fix: in `_page_task`, when `match is None` and the chosen
   `target` already exists, do not write; raise a per-file failure naming the
   path and saying a page there could not be read, so regen reports it and
   keeps going (`FileFailure`, Req 1.3). Consider making `doc_stem`'s
   collision rule loop until a free path.
3. Decide the reporting for outcome 1 (see Open questions) and pin it.

## Open questions
- For outcome 1, should regen refuse to seed a page for an archive file when a
  `workouts/*.md` it cannot read exists at that file's computed stem (a warning
  naming the unreadable page and asking the user to repair or delete it), or
  accept the duplicate and only warn? Needs a maintainer ruling; the file
  cannot be tied to the unreadable page with certainty.
