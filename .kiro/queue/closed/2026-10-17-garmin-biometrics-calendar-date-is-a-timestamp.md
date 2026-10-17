---
id: 2026-10-17-garmin-biometrics-calendar-date-is-a-timestamp
title: A real Garmin userBioMetrics export fails as a whole because metaData.calendarDate is a local timestamp, not a date
status: done
importance: medium
importance_why: No real Garmin export imports any weight; the file is quarantined and reported on every drain.
effort: S
kind: bug
area: wellness-store, src/fitdocs/wellness/formats/garmin.py, tests/wellness/builders_garmin.py
created: 2026-10-17
surfaced_by: maintainer-requested Phase 12 re-validation (real-data drain on a scratch data root; wellness-store optional task 6.3* shape)
pinned_at: 160b007
resume_command: "do: accept a local ISO timestamp in Garmin userBioMetrics metaData.calendarDate (take its date part), make builders_garmin emit the real shape, add a regression test [queue: .kiro/queue/2026-10-17-garmin-biometrics-calendar-date-is-a-timestamp.md]"
context:
  - src/fitdocs/wellness/formats/garmin.py
  - tests/wellness/builders_garmin.py
  - .kiro/specs/wellness-store/research.md
  - .kiro/specs/wellness-store/design.md
  - docs/wellness.md
blocked_by: []
---

## What
`_day` (`src/fitdocs/wellness/formats/garmin.py:91-98`) requires
`calendarDate` to match `\d{4}-\d{2}-\d{2}` exactly. In the maintainer's real
Garmin export, `*_userBioMetrics.json` has 1,795 records, and **every**
`metaData.calendarDate` is a local timestamp with a fractional second:
1,785 are shaped `YYYY-MM-DDTHH:MM:SS.f`, 8 `...SS.fff` and 2 `...SS.ff`.
The first record raises `WellnessFormatError("invalid Garmin calendar
date")`, so the whole file fails. Its 23 weight records never import, and the
file is quarantined.

`research.md:196-198` recorded that `metaData.calendarDate` is present on
all records, but not its shape. The test builder
(`tests/wellness/builders_garmin.py:53-62`) writes a bare date, so no test
sees the real shape. The other three Garmin formats (UDS, sleep, MaxMet)
imported cleanly from the same export: 65 files and 9,048 values, with
resting HR on 937 days, matching research.md exactly.

## Why it matters
Garmin-era body weight is silently missing from the series. The drain
reports `Wellness failed: ... invalid Garmin calendar date` on first contact
and `Quarantined` on every later drain. The documentation
(`docs/wellness.md:59`) promises weight from this file.

## Evidence
Scratch data root drain at 160b007 (counts and shapes only):
`fitdocs sync --out <scratch>` reported `Wellness archived 65`,
`Wellness failed 1` and `<inbox>/garmin-export/<id>_userBioMetrics.json:
invalid Garmin calendar date`, exit 1. On the next drain the file showed
under `Quarantined`. The shape census came from a `python3 -I` record walk,
which digit-masked each `metaData.calendarDate`.

## How to pick it up
1. In `garmin.py`, for kind `biometrics`, accept `YYYY-MM-DD` optionally
   followed by `T` and a local time (with or without a fraction), and keep
   the date part. It is local, so no timezone conversion is needed.
   Keep rejecting anything else.
2. Make `garmin_biometrics_record` emit the real timestamp shape by default
   and keep one bare-date case.
3. Re-drain a scratch root holding the real file; expect 23 weight values
   and no quarantine. Correct research.md's shape note (append only).

## Open questions
- Whether the date part of a biometrics timestamp equals the weigh-in's
  local wake date, or needs the `weight.timestampGMT` cross-check. The
  wellness-day rule in `docs/wellness.md` § Wellness day governs.

## Resolution (2026-10-17)
Fixed on chore/wellness-garmin-biometrics (landed via chore/p12-followups): biometrics `metaData.calendarDate` accepts a local timestamp (HH:MM:SS with an optional 1-6 digit fraction; date part kept; other shapes rejected, other Garmin kinds unchanged); builder emits the real shape; research.md shape note appended; no rules_version bump (a failed file was never archived). Real-data check: the maintainer's quarantined file, retried with `--retry-quarantined`, imported 23 weigh-ins on 17 days (one genuine same-timestamp conflict, reported). Independently reviewed (two rounds), APPROVED.
