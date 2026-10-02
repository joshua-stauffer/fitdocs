---
id: 2026-10-02-pull-delivery-race-stale-held-hashes-and-crash-orphan
title: Three pull delivery edges -- deliver can overwrite a file created between its exists() check and os.replace, held_hashes keeps a hash after a revision releases it, and a hard kill between delivery and ledger save leaves an undocumented untracked copy
status: open
importance: medium
importance_why: The first edge can overwrite a user's inbox file, against Req 8.3's "never overwrite"; the window is tiny but the inbox is a folder other tools write into concurrently by design.
effort: S
kind: bug
area: connectors, src/fitdocs/connectors/delivery.py, src/fitdocs/connectors/_atomic.py, src/fitdocs/connectors/pull.py, docs/connectors.md
created: 2026-10-02
surfaced_by: /kiro-impl connectors
pinned_at: ad985b3
resume_command: "/kiro-impl connectors [queue: .kiro/queue/2026-10-02-pull-delivery-race-stale-held-hashes-and-crash-orphan.md] Make deliver's final placement refuse an existing file, drop released hashes from held_hashes, and document the hard-kill orphan"
context:
  - src/fitdocs/connectors/delivery.py
  - src/fitdocs/connectors/_atomic.py
  - src/fitdocs/connectors/pull.py
  - tests/connectors/test_delivery.py
  - tests/connectors/test_pull.py
  - docs/connectors.md
  - .kiro/specs/connectors/requirements.md
  - .kiro/queue/2026-09-15-atomic-write-helper-copied-per-engine.md
blocked_by: []
---

## What
1. **Check-then-replace race (Req 8.3).** `deliver`
   (`src/fitdocs/connectors/delivery.py:161-174`) tests each candidate with
   `candidate.is_file()` / `candidate.exists()` and, when free, calls
   `write_atomic(candidate, ...)`, which ends in `os.replace(tmp_path, path)`
   (`src/fitdocs/connectors/_atomic.py:41`). `os.replace` overwrites
   silently, so a file another tool creates at that name between the check
   and the replace is clobbered. Req 8.3: "shall never overwrite an existing
   file" (`.kiro/specs/connectors/requirements.md:219`).
2. **Stale `held_hashes`.** `held_hashes` is built once per instance from the
   ledger's pending entries (`src/fitdocs/connectors/pull.py:494-498`) and
   only ever grows (`:684`). When a new revision with different bytes
   replaces a pending entry -- through `deliver` (`:645-683`) or through the
   already-held branch (`:633-643`) -- the old entry's hash is no longer
   tracked, yet stays in `held_hashes`. A later activity in the same run
   with those released bytes is then recorded `ALREADY_HELD` against a copy
   the ledger no longer tracks (it will be drained as an ordinary file, so
   nothing is lost, but the outcome is wrong).
3. **Hard-kill orphan.** The ledger is saved in a `finally` (`pull.py:694-698`),
   which covers exceptions and Ctrl-C but not SIGKILL or power loss. A file
   delivered before such a stop has no ledger entry: it is drained as an
   untracked inbox file and never removed by a pull, and the next pull
   fetches the activity again (delivering a second copy, deduplicated by the
   archive). `docs/connectors.md` does not mention this.

## Why it matters
(1) is the only path by which a pull can destroy a file it does not own --
the property the page's "never touched" paragraph and Req 8.3 promise. (2)
and (3) produce a wrong `held` count and a surplus inbox file respectively;
neither loses data.

## Evidence
- (1) and (2) read in the code at `ad985b3` (lines above). Not reproduced:
  the race needs a concurrent writer and (2) needs two activities whose bytes
  equal a released revision's, in one listing.
- (2) first reported by the feature-validation round-1 reviewer; (1) and (3)
  by the task 4.1/8.3 and feature-validation reviewers. (3) is a reviewer
  claim checked only statically (the `finally` placement); no kill was run.

## How to pick it up
1. Read `delivery.py:119-176` (`deliver`) and `_atomic.py`, then the per-
   activity loop in `pull.py:600-690`.
2. (1): place the final file with a no-clobber primitive -- `os.link(tmp,
   candidate)` then unlink the temp (fails with `FileExistsError` if taken),
   falling through to the next candidate on that error; keep fsync before.
   Note `_atomic.py` is a private copy tracked by
   `2026-09-15-atomic-write-helper-copied-per-engine`; a no-clobber variant
   may belong in the shared helper.
3. (2): when an entry is replaced, remove the old entry's `sha256` from
   `held_hashes` unless another still-pending entry holds it.
4. (3): add one sentence to `docs/connectors.md`'s delivery section (an
   abruptly killed pull can leave a delivered file untracked; the drain
   handles it as your own file), or save the ledger entry before writing
   the file (pending-before-write), which changes the crash outcome to a
   ledger entry with no file -- "forgotten" on the next sweep.
5. Pin (1) with a test that creates the target inside a patched
   `os.replace`/`os.link` window and asserts the user's bytes survive; pin
   (2) with a listing of three activities that exercises the release.
