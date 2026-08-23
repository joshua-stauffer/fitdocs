---
id: 2026-08-23-data-root-readers-have-no-cloud-placeholder-category
title: The data-root readers call an evicted cloud file corrupt or skip it silently, where the inbox drain calls the same condition a deferral
status: open
importance: medium
importance_why: Latent today, but it makes `regen` undercount silently and tells `check` users to delete a file that is fine — the same silent-undercount shape that once produced 74-file builds mistaken for a scope choice.
effort: M
kind: gap
area: wiki-contract, src/fitdocs/audit.py, src/fitdocs/docio.py
created: 2026-08-23
surfaced_by: moving the maintainer's demo data root onto iCloud Drive
pinned_at: bfe3b96
resume_command: "/kiro-spec-requirements wiki-contract [queue: .kiro/queue/2026-08-23-data-root-readers-have-no-cloud-placeholder-category.md] Give the data-root readers a cloud-placeholder category so an unmaterialized file is a deferral, not corruption and not a silent skip"
context:
  - .kiro/specs/wiki-contract/design.md
  - .kiro/specs/inbox/research.md
  - .kiro/specs/inbox/design.md
  - src/fitdocs/audit.py
  - src/fitdocs/docio.py
blocked_by: []
---

## What

The `inbox` spec reasoned carefully about macOS APFS **dataless files** — a
cloud file that keeps its real name, reports its full downloaded size from
`stat`, holds no data extents, and whose read blocks on a network fetch and
*fails when offline*. It concluded that such a file is a **timing** condition,
so the drain treats an unreadable candidate as a deferral, "never a failure and
never a permanent verdict about the file".

That reasoning was applied to the inbox only. The **data-root** readers — the
ones `check`, `regen`, and `sync`'s load pass use to walk `wiki/workouts/` and
`wiki/fit-archive/` — have no equivalent category. They classify the identical
`OSError` as a permanent property of the file:

- `fitdocs check` reports it as an `OS_ERROR` finding whose remedy is
  "restore access to this path, **or remove it if it is no longer a
  document**" — advice that, followed, deletes a document whose only problem
  is that the machine is offline.
- `fitdocs regen` does not report it at all: `read_frontmatter` swallows
  `OSError` and returns `None`, and "the caller simply skips the file and the
  scan continues".

Nothing distinguishes "this file is damaged" from "this file is fine and the
network is not".

## Why it matters

The data root is now on eviction-eligible storage. The maintainer's demo moved
to iCloud Drive on 2026-08-23, and `defaults read com.apple.bird
optimize-storage` returns `1`, so macOS may evict archived sources and
generated documents under disk pressure. Any user following the documented
"HealthFit → iCloud" story is in the same position, and `inbox/research.md`
already names iCloud as the *expected* location.

The failure is silent in the case that matters most. An offline `fitdocs regen`
over a partly-evicted data root skips the evicted documents and reports a
number lower than the archive holds, with no finding naming the cause. This
project has already been burned by exactly that shape once: a listing that
under-reported an archive of 2478 files as 74 produced 74-file builds that were
mistaken for a deliberate scope decision rather than read as a symptom. That
time it was the source side; the data root now carries the same exposure with
*less* diagnosis than the inbox has.

The `check` remedy is the sharper edge: it is not merely unhelpful but wrong,
proposing removal of a file that is intact.

## Evidence

Verified at `bfe3b96`.

The inbox side, which got this right:

- `.kiro/specs/inbox/research.md:46` — "macOS Sonoma replaced these with APFS
  **dataless files** that keep the real name, report the *full downloaded
  size* from `stat`, and have no data extents. Detection requires
  `SF_DATALESS` in `st_flags`; a read blocks while the kernel fetches, and
  fails when offline."
- `.kiro/specs/inbox/design.md:259` — "A read that fails is treated as a
  deferral with its reason … a not-yet-downloaded export is a *timing*
  problem, and permanently quarantining it as unprocessable would be the wrong
  and hard-to-undo answer."
- `tests/test_drain.py:311` — an unmaterialized cloud placeholder "is a
  deferral, never a failure".

The data-root side, which does not:

- `src/fitdocs/audit.py:341-345` — a generic `OSError` becomes
  `_UnreadableCause.OS_ERROR`.
- `src/fitdocs/audit.py:289` — `OS_ERROR` maps to `_REMEDY_RESTORE_ACCESS`,
  defined at `src/fitdocs/audit.py:163` as "restore access to this path, or
  remove it if it is no longer a document".
- `src/fitdocs/docio.py:91-94` — `read_frontmatter` catches
  `(OSError, UnicodeDecodeError)` and returns `None`; its docstring
  (`docio.py:87`) states "the caller simply skips the file and the scan
  continues".
- `src/fitdocs/audit.py:292-302` confirms this is understood and accepted for
  the causes it enumerates: `regen` "silently skips a directory, a
  permission-denied file, an other OS-level failure, or invalid UTF-8". The
  cloud-placeholder case is not among the causes considered.
- No coverage in the owning spec: `grep -rniE "icloud|dataless|placeholder"
  .kiro/specs/wiki-contract/` returns only region-placeholder-text hits,
  nothing about cloud materialization.

Not currently broken. At the new location, fully materialized:
`fitdocs check` = 2478 inspected / 0 findings; `fitdocs sync inbox
--no-prompt` = 0 written / 2478 skipped / 0 failed. This is a latent hazard,
not a live defect.

## How to pick it up

1. Read `.kiro/specs/inbox/design.md:259` and `research.md:46` first — the
   analysis is already done there, including the explicit rejection of
   `SF_DATALESS` detection as "platform-specific for no additional benefit"
   because the read probe covers the same case portably. Decide whether that
   rejection still holds for the data-root readers, where there is no probe
   read to piggyback on.
2. Read `src/fitdocs/audit.py:280-350` for the `_UnreadableCause` enum and its
   remedy map. The likely shape is a new cause distinguishing "unreadable, and
   this is plausibly a timing condition" from "unreadable, and the file is
   damaged", with a remedy that names materialization rather than removal.
3. Decide the `regen` question separately: silent-skip is the current contract
   for every unreadable cause, so making the cloud case loud means either a
   new warning channel or a deliberate exception. Note that `sync`/`regen`
   already emit a `DocWarning` for the SYMLINK cause (wiki-contract task 7.2),
   so the precedent for lifting one cause out of silence exists.
4. Done means: an evicted-and-offline document produces a finding a reader can
   act on correctly, `regen` does not silently undercount, and no remedy tells
   anyone to delete an intact file. A test can simulate this with an
   unreadable file — `inbox/research.md:93` records the same fallback ("verify
   with a real dataless-file scenario if a macOS test environment is
   available; otherwise simulate with an unreadable file"), and that follow-up
   is still open.

## Open questions

- Should the data-root readers distinguish the cloud case at all, or is the
  honest answer that `check` should simply stop proposing removal for a cause
  it cannot diagnose? The narrower fix — correcting `_REMEDY_RESTORE_ACCESS`
  — is an `S` and may be the right whole answer.
- Does fitdocs want to state a supported-storage position (data root on cloud
  storage: supported, with what caveat), or stay silent? `README.md:154`
  already advertises "HealthFit → iCloud" for the *inbox* without saying
  anything about the data root.
