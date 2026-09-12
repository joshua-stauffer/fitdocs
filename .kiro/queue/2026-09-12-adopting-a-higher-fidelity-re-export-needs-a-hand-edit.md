---
id: 2026-09-12-adopting-a-higher-fidelity-re-export-needs-a-hand-edit
title: A device-original .fit for an activity already ingested from a degraded third-party export can only be adopted by hand-editing the document's sources list
status: open
importance: medium
importance_why: Real case, 761 documents. Activity identity is session UUID or exact bytes; a Garmin original has neither in common with HealthFit's re-export of the same session, so `fitdocs sync` would have written 761 duplicate documents. The only working path was appending the new archive ref to each document's `sources` frontmatter by script and then syncing -- a hand edit of a fitdocs-managed key that the ownership contract says fitdocs owns.
effort: M
kind: gap
area: wiki-contract, workout-docs, src/fitdocs/sync.py (find_document, activity identity)
created: 2026-09-12
surfaced_by: hand session adopting 761 Garmin originals into the real data root (pkm-data/raw/garmin-adoption/README.md)
pinned_at: aa851a3
resume_command: "/kiro-spec-requirements wiki-contract [queue: .kiro/queue/2026-09-12-adopting-a-higher-fidelity-re-export-needs-a-hand-edit.md] Give sync a third identity path (or an explicit adopt command) for a re-export of one activity that shares neither session UUID nor bytes with the archived source"
context:
  - src/fitdocs/sync.py
  - src/fitdocs/contract.py
  - docs/ownership-contract.md
  - .kiro/specs/wiki-contract/requirements.md
blocked_by: []
---

## What

`find_document` (`src/fitdocs/sync.py`) matches an incoming activity to an
existing document by `uuid` (the recorded session UUID) and then by exact
`sources` membership. A device-original FIT (Garmin) for an activity whose
document was rendered from a HealthFit re-export has a different sha and no
session UUID, so it is a fresh document. There is no third path -- session
start + duration + distance within a tolerance, or an explicit "this file
supersedes that document" instruction -- and no CLI verb for it.

## Why it matters

The degraded re-export is the common case for anyone who came to fitdocs
through a phone app: HealthFit's Garmin-Connect copies carry ~30 HR samples,
no distance/position stream, and (244 of 761 here) a start time off by whole
hours. Every one of those documents was un-scoreable and, for 243, on the
wrong day. The fix was a script that appends `- fit-archive/<sha>.fit` to
`sources:` and then runs `sync`, which then matches by that history entry,
re-renders, carries the user regions and archives the file -- exactly the
behaviour a re-export *should* get, reached only by editing a managed key.

## Evidence

- `pkm-data/raw/garmin-adoption/README.md` and `plan.json` (maintainer's
  data, not in this repo): 761 `adopt` rows, 11 `fresh`, 126 `keep`;
  strict match |Δduration| ≤ 5 s, |Δdistance| ≤ 10 m (true pairs agree to
  ≤ 1 s / ≤ 1 m; the first loose attempt at 90 s / 300 m produced 4
  collisions and 2 false matches).
- `fitdocs sync <staging> --no-prompt` after the append: `Written 772 /
  Skipped 0 / Failed 0 / Warnings 0`; `fitdocs check` afterwards: 2547
  inspected, 0 findings.
- Stem collision seen once: the corrected stem of one ride was still held by
  another document being corrected in the same run, so fitdocs suffixed it
  `-47d9d6f8`; a second `sync --force` of that one file after the other's
  rename produced the clean stem. Any adopt path must order renames.
- `src/fitdocs/sync.py` `_process_file`: a matched document keeps
  `match.path` while `stem` (and every asset name) is recomputed, so a
  timestamp correction leaves the filename stale and the old assets
  orphaned -- the post step had to rename 243 documents and delete 287 assets.

## How to pick it up

1. Read `find_document` and `_process_file`, then `docs/ownership-contract.md`
   on `sources` and document identity.
2. Decide between (a) a bounded third identity path in `find_document`
   (same sport, |Δstart| ≤ N min, |Δtimer| ≤ 5 s, |Δdistance| ≤ 10 m, one
   candidate only, reported as a warning naming both files), and (b) an
   explicit `fitdocs adopt <file> <document>` that does the append + render
   in one atomic step. (b) is safer and matches the contract's "never
   guess" stance; (a) is what a user actually wants for a 761-file batch.
3. Either way, decide what happens to the filename and assets of a matched
   document whose stem changes: rename in place (content-based identity
   already makes that safe) or keep and document the mismatch.

## Open questions

- Should a document whose current source was superseded keep the old
  session `uuid`? Today the re-render drops it (the Garmin file has none),
  so a later HealthFit re-export of the same session would match only by
  its archived sha.
