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
resume_command: "/kiro-impl intervals-connector [queue: .kiro/queue/2026-10-02-intervals-rate-limit-resume-claim-since-backfill.md] Make the rate-limit/unavailable runtime messages true for an interrupted --since backfill (docs/connectors.md already is)"
context:
  - src/fitdocs/connectors/intervals.py
  - src/fitdocs/connectors/pull.py
  - docs/connectors.md
  - .kiro/specs/intervals-connector/design.md
  - .kiro/specs/connectors/design.md
blocked_by: []
---

## What
Narrowed 2026-10-19 to the runtime messages; `docs/connectors.md` is fixed
(see the update below).

`RATE_LIMITED_MESSAGE` and `UNAVAILABLE_MESSAGE` in
`src/fitdocs/connectors/intervals.py` (~:97-105) both end "this pull stopped,
and the next pull resumes where it stopped". In
`connectors/pull.py::_window_start`, a pull without `--since` lists from the
watermark less `lookback_days`, and the watermark never moves backward. So
when a `--since 2024-01-01` backfill into an instance that has pulled before
is cut short by a 429, a following plain `fitdocs pull` lists only from the
watermark window. The older part of the backfill is never resumed unless the
user passes the same `--since` again.

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

## Update 2026-10-19 (chore/docs-0-2, docs half)

`docs/connectors.md` "What a pull fetches" no longer says the next pull
resumes (46a6f7a). The rate-limit and unavailable bullets now say only that
the pull stops. A new paragraph explains that a plain pull resumes, or
retries a failed download, only inside its window, and that a `--since`
backfill into an instance that has pulled before is continued by rerunning
the same `--since`. Pinned by
`tests/connectors/test_docs.py::test_intervals_section_does_not_promise_a_plain_pull_resumes_a_backfill`.
Still open: the two runtime messages, pinned verbatim in
`tests/connectors/test_intervals.py` (~:973, :986, :1347, :1360) and
`tests/connectors/test_intervals_wellness.py` (~:506, :1193). The same
window logic also stops a plain pull from retrying a failed download older
than the window after such a backfill (`docs/connectors.md` now says so).
