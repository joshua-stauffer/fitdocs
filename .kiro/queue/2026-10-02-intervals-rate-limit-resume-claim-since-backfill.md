---
id: 2026-10-02-intervals-rate-limit-resume-claim-since-backfill
title: The intervals.icu rate-limit and unavailable messages promise "the next pull resumes where it stopped", which an interrupted --since backfill does not do
status: open
importance: low
importance_why: A user backfilling history with --since who hits a 429, then runs a plain pull, silently misses the rest of the backfill window and is told otherwise.
effort: S
kind: inconsistency
area: intervals-connector, src/fitdocs/connectors/intervals.py, src/fitdocs/connectors/pull.py, docs/connectors.md
created: 2026-10-02
surfaced_by: /kiro-impl intervals-connector (4.2 review)
pinned_at: 9d08482
resume_command: "/kiro-impl intervals-connector [queue: .kiro/queue/2026-10-02-intervals-rate-limit-resume-claim-since-backfill.md] Make the rate-limit/unavailable messages and docs true for an interrupted --since backfill"
context:
  - src/fitdocs/connectors/intervals.py
  - src/fitdocs/connectors/pull.py
  - docs/connectors.md
  - .kiro/specs/intervals-connector/design.md
  - .kiro/specs/connectors/design.md
blocked_by: []
---

## What
`RATE_LIMITED_MESSAGE` and `UNAVAILABLE_MESSAGE` in
`src/fitdocs/connectors/intervals.py` both end "this pull stopped, and the
next pull resumes where it stopped". `docs/connectors.md` repeats the
promise. In `connectors/pull.py::_window_start`, a pull without `--since`
lists from the watermark less `lookback_days`, and the watermark never moves
backward. So when a `--since 2024-01-01` backfill is cut short by a 429, a
following plain `fitdocs pull` lists only from the watermark window. The
older part of the backfill is never resumed unless the user passes the same
`--since` again.

## Why it matters
The message tells the user they need to do nothing. For a backfill, that is
false, and the history gap is silent.

## Evidence
- `src/fitdocs/connectors/intervals.py:100`: `"this pull stopped, and the next pull resumes where it stopped"`.
- `src/fitdocs/connectors/pull.py:221-234`: `_window_start` returns `since` when
  given, otherwise `watermark - lookback_days`.
- Raised by the 4.2 reviewer from reading pull.py's `_compute_watermark`
  docstring. The controller read `_window_start` but did not run an
  interrupted-backfill scenario.

## How to pick it up
1. Confirm the behaviour with a FakeTransport test. Run a `run_pull` with
   `since` far back that hits a persistent 429 partway through, then a second
   `run_pull` without `since`, and show the older entries are never listed.
2. Decide: either reword both messages and the docs (e.g. "rerun with the
   same --since to continue a backfill"), or change the framework so the
   watermark records an unfinished backfill (that is a connectors design
   change and an amendment).
3. Pin the chosen wording and run its mutation.
