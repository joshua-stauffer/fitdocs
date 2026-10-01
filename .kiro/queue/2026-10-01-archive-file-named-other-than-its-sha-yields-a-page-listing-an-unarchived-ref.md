---
id: 2026-10-01-archive-file-named-other-than-its-sha-yields-a-page-listing-an-unarchived-ref
title: An fit-archive file whose name is not its content sha makes regen write a page that lists an unarchived ref, then fail and rewrite it on every later run
status: open
importance: medium
importance_why: The page it writes can never be rebuilt (regen reports Failed 1 each run), and `fitdocs check` is silent about both the misnamed file and the dangling ref.
effort: S
kind: bug
area: activity-identity, src/fitdocs/sync.py, src/fitdocs/audit.py
created: 2026-10-01
surfaced_by: /kiro-impl activity-identity
pinned_at: fc5c06d
resume_command: "/kiro-impl activity-identity [queue: .kiro/queue/2026-10-01-archive-file-named-other-than-its-sha-yields-a-page-listing-an-unarchived-ref.md] Decide and implement what regen does with an archive file whose name is not its content hash"
context:
  - src/fitdocs/sync.py
  - src/fitdocs/audit.py
  - .kiro/specs/activity-identity/requirements.md
  - .kiro/specs/activity-identity/design.md
blocked_by: []
---

## What
`regen` treats every `fit-archive/*.fit` whose filename stem is not listed by a
page as "unreferenced", but plans it from its *content*: the page it writes
lists `fit-archive/<sha256 of the bytes>.fit`. When the file's name is not that
sha (a file copied in by hand, or a rename), the listed ref does not exist.
Archive writes are disabled in regen (`write_archive=False`, "the bytes are
already archived"), so nothing creates the file the page now lists.

## Why it matters
The result is a page that cannot be rebuilt and a run that never settles:
`regen` #1 reports `Written 1`, and every later run reports `Written 1` and
`Failed 1` (the per-page rebuild fails with "no archived source to regenerate
from" while the misnamed file is planned again and the page rewritten).
`fitdocs check` reports nothing, so the user has no pointer to the cause.

## Evidence
Reproduced at `fc5c06d` in a scratch data root.
- Setup: `fit-archive/my-own-name.fit` holding a valid FIT file (builder
  `run_fit_bytes()`), empty `workouts/`.
- `fitdocs regen --out <root>` #1: `Written 1`; the new page's `sources:` is
  `fit-archive/399c333ece990fe8fb43b28e27afd7ba841f510b67194d1593a73a810302214f.fit`,
  which is absent from `fit-archive/` (still only `AGENTS.md`, `my-own-name.fit`).
- `regen` #2 and #3: `Written 1`, `Failed 1`, with
  `no archived source to regenerate from: the document's 'sources' history is
  empty or unresolvable, or its current source is missing from the archive`.
- `fitdocs check --out <root>`: `Findings 0`.
- Code: `src/fitdocs/sync.py:2372-2386` `_unreferenced_archives` compares
  `path.stem` with the referenced shas; `:1193` regen builds
  `_RunItem(source_ref(archive.stem), archive)`; `:1402`/`:1416` the run file's
  ref is `source_ref(sha)` of the content; `:1208` `write_archive=False`.
  `src/fitdocs/audit.py:507-509` `_orphan_findings` does
  `sha = sha_of_ref(ref)` and `continue`s on `sha is None` (a non-hex stem), and
  the dangling ref on the page is not an orphan either, so `check` finds nothing
  (the `Findings 0` output above is the observed result).

## How to pick it up
1. Reproduce with the setup above; write the failing e2e test.
2. Pick one behavior (Open questions) and make regen, `check` and the docs
   agree: either regen refuses the file (a per-file failure naming it, and a
   `check` finding), or it adopts it by writing the bytes to
   `fit-archive/<sha>.fit` when that path is absent.
3. Done: a second `regen` is a no-op (`Failed 0`, byte-identical pages).

## Open questions
- Adopting a file means regen writes into `fit-archive/`; `regen`'s own
  docstring (`src/fitdocs/sync.py:1050-1135`) says it writes no archive file and
  cites Req 3.5 (the archive is never rewritten). A
  write-if-absent exception (never overwriting) is the lighter option; it needs
  the maintainer's ruling and a wording change in the ownership contract.
