---
id: 2026-10-17-recovery-crashes-on-zero-log-signal
title: read_series does not apply metric ranges, so an HRV of 0 in the series crashes fitdocs recovery with a math domain error
status: done
importance: low
importance_why: Needs a hand-edited or corrupted series file, but the failure is an uncaught traceback instead of the documented exit 1 with a remedy.
effort: S
kind: bug
area: wellness-store, recovery, src/fitdocs/wellness/series.py, src/fitdocs/recovery/baselines.py
created: 2026-10-17
surfaced_by: maintainer-requested Phase 12 re-validation (recovery reviewer finding 5; code path confirmed by the parent)
pinned_at: 160b007
resume_command: "do: reject or skip out-of-range values when read_series decodes the yearly CSVs (MetricInfo minimum/maximum), so a zero HRV is reported as an unreadable series rather than crashing recovery's log transform [queue: .kiro/queue/2026-10-17-recovery-crashes-on-zero-log-signal.md]"
context:
  - src/fitdocs/wellness/series.py
  - src/fitdocs/recovery/baselines.py
  - .kiro/specs/wellness-store/design.md
  - docs/wellness.md
blocked_by: []
---

## What
`read_series` (`src/fitdocs/wellness/series.py:340-350`) decodes the yearly
CSVs without applying `MetricInfo`'s accepted range. `Baselines`
(`src/fitdocs/recovery/baselines.py:66-75`) takes `math.log` of HRV values.
An `hrv_sdnn_ms` or `hrv_rmssd_ms` value of 0 in a series file therefore
raises `ValueError: math domain error` out of `fitdocs recovery`.

## Why it matters
The documentation promises that an unreadable series reports the error and
the `sync`/`regen` remedy with exit 1 (`docs/recovery.md`, Run the command).
Producers never write a 0 HRV, so only a hand edit or a corrupted or foreign
file reaches this.

## Evidence
- Code read at 160b007: no range check on the read path; `math.log` is
  applied unguarded.
- The recovery reviewer staged `hrv_rmssd_ms=0` with the sanctioned
  `write_series` builder and got the traceback (reported, not re-run by the
  parent).

## How to pick it up
1. Decide where the guard belongs. In `read_series` (treat an out-of-range
   row as a series fault, so the existing unreadable-series path reports it)
   is the more general fix.
2. Add a test: a zero HRV row makes `recovery` exit 1 with the remedy, and
   the series reader raises its documented error.

## Resolution (2026-10-17)
Fixed on chore/wellness-garmin-biometrics: `read_series` faults an out-of-range or non-finite series value as SeriesReadError naming file, line, day, metric and value (kept out of `decode_year`, so the engine's rebuild still repairs a hand-edited series). `fitdocs recovery` exits 1 with the sync/regen remedy, derive-benchmarks records a resting failure, `fitdocs index` reports a derived.wellness producer error; `check` unchanged. APPROVED.
