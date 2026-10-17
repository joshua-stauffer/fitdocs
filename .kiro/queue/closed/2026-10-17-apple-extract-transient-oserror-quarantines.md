---
id: 2026-10-17-apple-extract-transient-oserror-quarantines
title: A transient read error while extracting an Apple Health zip quarantines it as "not an Apple Health export" instead of deferring it
status: done
importance: low
importance_why: Needs a one-off read failure after a successful probe, a plausible iCloud-inbox event; recovery is --retry-quarantined, but the reason misleads.
effort: S
kind: bug
area: apple-health-import, src/fitdocs/wellness/formats/apple/reader.py
created: 2026-10-17
surfaced_by: maintainer-requested Phase 12 re-validation (apple-health-import reviewer fault injection; code confirmed by the parent)
pinned_at: 160b007
resume_command: "/kiro-impl apple-health-import [queue: .kiro/queue/2026-10-17-apple-extract-transient-oserror-quarantines.md] Defer, not quarantine, on an OSError during extraction"
context:
  - src/fitdocs/wellness/formats/apple/reader.py
  - src/fitdocs/wellness/probe.py
  - .kiro/specs/apple-health-import/design.md
blocked_by: []
---

## What
`open_main_document` (`src/fitdocs/wellness/formats/apple/reader.py:80`) calls
`zipfile.is_zipfile(bounded)`. `is_zipfile` catches `OSError` and returns
`False`, so a read error at that moment makes the zip be parsed as bare XML.
The import then fails with `Failed("not an Apple Health export: no HealthData
element in its first 1 MiB")` and the file is quarantined. The design
(`design.md:936`) says an unreadable candidate is deferred. The probe's
`_ZipReader` already guards this case for recognition. A side note: the
`RuntimeError` catch at `reader.py:95` wraps the `yield`, so a consumer's
`RecursionError` would also become a quarantine.

## Why it matters
The maintainer's inbox is an iCloud folder, where reads can fail
transiently while a file materialises. A quarantined export needs
`fitdocs sync --retry-quarantined`, and its stated reason points the user
at the wrong cause.

## Evidence
- Code at 160b007: `reader.py:76-97`.
- The reviewer injected one `OSError` at the zip's end-of-file read after the
  probe and hash succeeded, and observed the `Failed(...)` above (reported,
  not re-run by the parent). Persistent read failures were correctly
  deferred, and a `chmod 000` zip was deferred.

## How to pick it up
1. Replace `is_zipfile` with a check that lets `OSError` propagate (read the
   end-of-central-directory signature yourself, or `try: ZipFile(...)` and
   catch only `BadZipFile`). Make sure the intake classifies a propagated
   `OSError` as deferred.
2. Narrow the `RuntimeError` catch to the `ZipFile` and member-open calls,
   not the `yield`.
3. Add a fault-injection test: one `OSError` on the extract-time read gives
   deferred, not quarantined.

## Resolution (2026-10-17)
Fixed on chore/apple-import-hardening: zip detection notes only read errors (a seek EINVAL on a sub-22-byte file is 'not a zip', not a read fault, after a review rejection), so a transient OSError defers end to end; zlib.error and EOFError during member reads are format errors (quarantine); RecursionError propagates at open and read sites. APPROVED after two rejection rounds.
