---
id: 2026-10-17-hr-max-evidence-projects-past-last-session
title: derive-benchmarks writes future-dated max-HR entries as sessions age out of the window after the newest session
status: done
importance: high
importance_why: Fabricated future-dated benchmarks reach athlete.toml on the first real run, put open-ended false findings in fitdocs check, and hide the real current takeover.
effort: S
kind: bug
area: hr-derivation, src/fitdocs/hr_benchmarks/maximum.py
created: 2026-10-17
surfaced_by: maintainer-requested Phase 12 re-validation (real-data smoke on a scratch copy of the maintainer's data root)
pinned_at: 160b007
resume_command: "/kiro-impl hr-derivation [queue: .kiro/queue/2026-10-17-hr-max-evidence-projects-past-last-session.md] Stop max-HR evidence days at the newest session day"
context:
  - src/fitdocs/hr_benchmarks/maximum.py
  - src/fitdocs/hr_benchmarks/inspect.py
  - src/fitdocs/audit.py
  - .kiro/specs/hr-derivation/design.md
  - .kiro/specs/hr-derivation/requirements.md
blocked_by: []
---

## What
`max_evidence` (`src/fitdocs/hr_benchmarks/maximum.py:11-19`) makes an
evidence day of every `session.day` **and** every `session.day + 365`
(the day the session leaves the rolling window), with no upper bound. Every
departure day after the newest session is a projection, not evidence: the
window shrinks to the last few sessions, the median of the top three falls,
and the engine writes derived `max_hr_bpm` entries whose `measured_on` lies
up to a year in the future. Near the end it takes the median of whatever
remains, including strength or walking sessions that never approach maximum.
The engine has no clock by design, so nothing caps these days.

## Why it matters
- `athlete.toml` gains derived max-HR entries dated in the future, with
  values that decay towards resting-level heart rates.
- `fitdocs check` lists open-ended `hr_benchmark_inconsistent` findings for
  those future periods ("heart-rate load is not computed in this period;
  record the correct value by hand"). These are false alarms.
- `current_takeovers` (`inspect.py:43-49`) lists a takeover only when the
  derived entry is the newest of its kind. A future entry is always the
  newest, so `check` never lists the real current takeover of a hand value,
  which defeats the maintainer's rule that every takeover is announced.
- Any workout synced after one of those future dates, before
  `derive-benchmarks` is re-run, is scored against the projected value.

## Evidence
Synthetic reproduction (no personal data), run at 160b007 with
`uv run python <script>`. Five `SessionPeak`s were dated 2026-01-10 (188),
2026-03-01 (186), 2026-05-01 (184), 2026-06-01 (101, a strength session) and
2026-06-02 (98). `max_evidence` returned:

```
2026-05-01 186
2026-06-01 186
2026-06-02 186
2027-01-10 184 AFTER LAST SESSION
2027-03-01 101 AFTER LAST SESSION
```

On a scratch copy of the maintainer's full data root (2,567 workout pages,
real Garmin-export and intervals.icu wellness), `derive-benchmarks
--dry-run` and a write on the copy produced:
- 21 `max_hr_bpm` entries, 5 of them dated after the newest session; the
  last of those is about 51% of the hand-recorded maximum;
- 4 `threshold_outside_reserve` periods, all in the future, the last one
  `open`;
- `fitdocs check` listing those 4 periods and **no** `hr_benchmark_takeover`,
  although a derived entry dated before the newest session supersedes the
  hand value.

Only counts are recorded here; nothing from the maintainer's data root
entered the repository. The hr-derivation re-validation reviewer
independently reported the related departure-day mechanism (see
`2026-10-17-hr-max-evidence-sparse-windows-need-ruling`).

## How to pick it up
1. Read `design.md` § max evidence (the `max_evidence` rule, design lines
   692-693) and Req 3.7, 4.3 and 5.2.
2. Bound the evidence days at the newest session day:
   `days = sorted(d for d in ... if d <= max(session.day))`. Departure days up
   to the newest session stay, because they are inside observed history.
3. Add a test pinning that no evidence day exceeds the newest session day,
   using the five-session reproduction above, and a `check` test showing
   that the current takeover is listed when the newest session's evidence
   supersedes a hand entry.
4. Re-run the maintainer's 5.3* dry-run on a scratch copy. Expect no entry
   after the newest session and no future inconsistency period.

## Open questions
- Whether `CONTRACT_VERSION` or a rules version moves. Probably not: no
  owned format changes, only which entries a run writes.

## Resolution (2026-10-17)
Fixed by hr-derivation Amendment 1 (maintainer ruling 2026-10-17) on chore/hr-max-ruling: max-HR evidence days are session days only (departure days removed), so nothing is dated after the newest qualifying session. Real data (scratch full-corpus copy, clean snapshot of 1ed4ec0): 0 derived maxima with the hand entry, 9 rising entries without it, none future-dated; no future inconsistency periods. Independently reviewed (two rounds), APPROVED.
