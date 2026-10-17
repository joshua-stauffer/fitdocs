---
id: 2026-10-17-recovery-relay-source-one-day-flips
title: The recovery page flips its shown source for one day when a relay (intervals.icu) has a value the device source lacks
status: open
importance: low
importance_why: Correct by Req 5.1-5.5, but on the maintainer's data it prints paired "changed from apple-health to intervals-icu" and back lines for single days, and each flip restarts a baseline from a differently defined relay value.
effort: S
kind: spec-work
area: recovery, wellness-store precedence, src/fitdocs/recovery/view.py
created: 2026-10-17
surfaced_by: Phase 12 follow-ups, maintainer-data recovery page (real Apple Health export plus a live intervals.icu pull)
pinned_at: 5cb2931
resume_command: "/kiro-spec-requirements recovery [queue: .kiro/queue/2026-10-17-recovery-relay-source-one-day-flips.md] Decide how the shown source treats a relay that duplicates a device source"
context:
  - .kiro/specs/recovery/requirements.md
  - .kiro/specs/recovery/design.md
  - docs/wellness.md
  - docs/recovery.md
blocked_by: []
---

## What
On the maintainer's data, apple-health (the Watch, overnight-mean HRV)
outranks intervals-icu, which relays HealthFit's daily Apple values under a
different day definition. On a night the Watch recorded no asleep HRV but the
relay had a value, intervals-icu is canonical for that day. The page then
states a change to intervals-icu and, the next day, a change back. The
day's 7-day mean and range are intervals-icu's own.

## Why it matters
The page is correct to Req 5 and never pools sources. But a relay that mostly
duplicates the device source makes the page noisy, and each one-day switch
restarts the baseline from a source with a different definition.

## Evidence
Scratch maintainer-data page, window 2026-07-20..2026-10-17 at 5cb2931:
"On 2026-07-25 the shown source changed from apple-health to intervals-icu
..." and "On 2026-07-26 ... back to apple-health". The coverage table shows
HRV (SDNN) on 89 days from apple-health and 88 from intervals-icu.

## How to pick it up
Options for the maintainer:
- (a) Leave it as is; it is correct and descriptive.
- (b) Let the shown source carry the previous source across a day the
  previous source lacks, even when another source has a value (the carry
  rule extended past "no canonical source").
- (c) Let `[wellness] precedence` exclude a source for a metric, which today
  is impossible: partial lists are completed with the rest.
- (d) Stop pulling intervals.icu wellness now that Apple exports cover the
  same data (`wellness = false`). This loses daily freshness between manual
  exports.

## Open questions
Which option. (b) is a Req 5.2 change; (c) is a wellness-store settings
change.
