---
id: 2026-10-17-hr-max-evidence-sparse-windows-need-ruling
title: Max-HR derivation takes the median of sparse or non-maximal windows (history start, window departures) and needs a maintainer ruling
status: open
importance: medium
importance_why: Writes implausible derived maxima into athlete.toml at the start of history; no load moves today only because those early pages are unscored.
effort: S
kind: spec-work
area: hr-derivation, src/fitdocs/hr_benchmarks/maximum.py, src/fitdocs/hr_benchmarks/sources.py
created: 2026-10-17
surfaced_by: maintainer-requested Phase 12 re-validation (real-data smoke on a scratch copy; hr-derivation reviewer finding 1)
pinned_at: 160b007
resume_command: "/kiro-spec-requirements hr-derivation [queue: .kiro/queue/2026-10-17-hr-max-evidence-sparse-windows-need-ruling.md] Decide the minimum evidence for a derived maximum HR"
context:
  - src/fitdocs/hr_benchmarks/maximum.py
  - src/fitdocs/hr_benchmarks/sources.py
  - src/fitdocs/hr_benchmarks/timeline.py
  - .kiro/specs/hr-derivation/requirements.md
  - .kiro/specs/hr-derivation/design.md
  - docs/configuration.md
blocked_by: []
---

## What
A derived maximum is the median of the three highest 30-second sustained
peaks in a 365-day window, and the only minimum is three sessions
(`sources.MAX_TOP_SESSIONS`). Any session with heart rate counts, including
strength and walking. When the window is sparse, the "median of the top
three" is a non-maximal session's peak. This happens:
1. **At the start of history.** The first few windows hold three to a dozen
   sessions.
2. **On departure days.** A session leaving the window creates an evidence
   day although no new session happened. The re-validation reviewer staged
   this: a hand max measured 2024-05-01 was taken over on 2025-03-01 by
   peaks that all came from sessions *before* the hand date
   (`maximum.py:11-19`, `timeline.py:29`).

Both match Req 3.7, 4.3 and 5.2 as written. The maintainer's 2026-10-12
decision 1 ("a hand value holds until evidence dated after it disagrees")
arguably intends *sessions* after the hand entry, not evidence *days*.

## Why it matters
On a scratch copy of the maintainer's full data root (counts only), the
first derived entry, at the start of history, came out at about 55% of the
hand-recorded maximum. Its "top three" were one real effort and two
low-intensity sessions. Five early entries ramp up over three weeks before
the window holds enough real efforts. Every one of them takes over the hand
value through its `applies_from`. Workouts in that period are unscored today,
so no load moved, but the profile holds implausible values and any future
scoring of early history would use them.

## Evidence
- `src/fitdocs/hr_benchmarks/maximum.py:24-31`: the only guard is
  `len(window) < MAX_TOP_SESSIONS`, and `median = top[1]`.
- Real-data counts from the scratch copy: 21 derived `max_hr_bpm` entries;
  the first 5 span about 3 weeks, rising from about 55% to 91% of the
  hand-recorded maximum. Reported in this session's validation; no values
  recorded here.
- The reviewer's departure-day case was staged on synthetic data. It was
  reported, not re-run by the parent session.

## How to pick it up
1. Present the maintainer with options: (a) count only modalities able to
   reach maximum (run, ride, ...) or sessions above a fraction of the
   current hand value; (b) require a minimum session count or span before
   the first derived maximum (for example 20 qualifying sessions); (c) only
   sessions dated after a hand entry may take it over (departure days never
   do). (a)+(c) is the smallest change that matches decision 1.
2. Amend the requirements with the ruling, then the design's max evidence
   section, then the tests.
3. Re-run the 5.3* dry-run on a scratch copy and compare the early-history
   entries.

## Open questions
- Which of (a), (b) or (c), or a combination. This is a maintainer
  decision.
