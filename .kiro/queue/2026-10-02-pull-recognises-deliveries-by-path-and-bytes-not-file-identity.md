---
id: 2026-10-02-pull-recognises-deliveries-by-path-and-bytes-not-file-identity
title: A pull recognises its own pending delivery by path and bytes only, so an exact copy the user writes back at that path is removed once archived -- accepted by maintainer decision; recording file identity (inode + mtime) would remove the qualification
status: open
importance: low
importance_why: Accepted behaviour, documented, and lossless (the bytes are always archived before removal); this records the hardening that would make "nothing you put in the inbox is ever removed" unconditional.
effort: M
kind: spec-work
area: connectors, src/fitdocs/connectors/ledger.py, src/fitdocs/connectors/delivery.py, src/fitdocs/connectors/pull.py
created: 2026-10-02
surfaced_by: /kiro-impl connectors (feature validation; maintainer decision 2026-10-02)
pinned_at: ad985b3
resume_command: "/kiro-spec-requirements connectors [queue: .kiro/queue/2026-10-02-pull-recognises-deliveries-by-path-and-bytes-not-file-identity.md] Decide whether the ledger records a delivered file's identity so the sweep releases rather than removes a byte-identical replacement"
context:
  - .kiro/specs/connectors/requirements.md
  - .kiro/specs/connectors/design.md
  - src/fitdocs/connectors/ledger.py
  - src/fitdocs/connectors/delivery.py
  - docs/connectors.md
  - docs/compatibility.md
blocked_by: []
---

## What
The ledger records, per pending delivery, its inbox-relative path and
SHA-256. The sweep (`src/fitdocs/connectors/delivery.py`, `sweep`, rules at
`:240-260`) removes the file at that path once the archive holds those bytes.
It cannot tell fitdocs's own file from a different file with the same name
and bytes -- for example, the user deletes the delivery and a sync tool
writes the same export back. That file is removed on the next pull.

At feature validation (2026-10-02) the maintainer chose to qualify Req 15.4
rather than change the code: requirements.md now says "a pull recognizes its
own delivery by the path and bytes it wrote, so an exact copy of a
still-pending delivery's bytes written back at that delivery's own path
counts as that delivery" (`.kiro/specs/connectors/requirements.md:58-62`,
`:304`), and `docs/compatibility.md:54` carries the same exception.

The alternative is to record the delivered file's identity (`st_ino`,
`st_dev`, `st_mtime_ns`, size) in the ledger at delivery, and have the sweep
*release* (stop tracking, leave in place) a pending path whose identity no
longer matches, instead of removing it.

## Why it matters
Today the user-facing guarantee carries an exception. It is lossless (the
archive holds identical bytes before anything is removed), so this is a
polish item, not a defect. Recording identity changes the ledger format
(a ledger version bump and a migration of pending entries with no identity),
which is why it wants a requirements decision first.

## Evidence
- Requirements text and docs lines above, read at `ad985b3`.
- `ad985b3` itself ("a pull never adopts an inbox file it did not deliver
  with those bytes; Req 15.4 states path+bytes recognition") is the commit
  that landed the decision.
- No run in this session; the behaviour is what the amended requirement
  states.

## How to pick it up
1. Read requirements.md Req 15.4 and the amended paragraph at `:55-62`,
   then design.md's Delivery lifecycle and the ledger format.
2. Decide (maintainer) whether to keep the qualification. If not: add the
   identity fields to `LedgerEntry`, bump the ledger format version, treat a
   pending entry without identity as path+bytes (today's rule), and change
   the sweep's "archived, file present, hash matches" branch to release on
   identity mismatch.
3. Done when the requirement drops the exception, the docs drop it, and a
   test writes back an identical copy at a pending path and sees it left in
   place after the next pull.

## Open questions
- Is `st_ino`+`st_dev`+`st_mtime_ns` stable enough across the cloud-sync
  folders users point the inbox at (iCloud, Dropbox rewrite files in place)?
  If not, the qualification may be the better rule.
