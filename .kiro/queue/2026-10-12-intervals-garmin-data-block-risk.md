---
id: 2026-10-12-intervals-garmin-data-block-risk
title: intervals.icu may block Garmin-origin data from its API, which threatens Phase 8's Garmin-ride pull
status: open
importance: high
importance_why: The maintainer's Garmin Edge rides reach fitdocs only through the intervals.icu pull; a block would silently stop them, including history.
effort: M
kind: research
area: intervals-connector, connectors, src/fitdocs/connectors/intervals.py
created: 2026-10-12
surfaced_by: /kiro-discovery (Phase 12 wellness and recovery, research and viability subagents)
pinned_at: 1f984fc
resume_command: "/kiro-discovery [queue: .kiro/queue/2026-10-12-intervals-garmin-data-block-risk.md] Decide the fallback route for Garmin-origin activities if intervals.icu blocks Garmin data from its API"
context:
  - .kiro/steering/roadmap.md
  - .kiro/specs/intervals-connector/requirements.md
  - .kiro/specs/intervals-connector/research.md
  - src/fitdocs/connectors/intervals.py
  - src/fitdocs/connectors/folder.py
blocked_by: []
---

## What

Phase 8 decided that "Garmin rides come via intervals.icu" (roadmap, Phase 8
"Decisions taken at discovery"). Garmin's developer program is
business-only, so the intervals.icu activity pull, which receives Garmin
files over Garmin's partner API, is the maintainer's only automated route for
Garmin Edge rides. The intervals.icu developer has now said Garmin's updated
terms will likely force a block on Garmin-origin data in the intervals.icu
API, probably including historical data. Nothing in fitdocs detects or
reports that, and no fallback route is planned.

## Why it matters

If the block lands, `fitdocs pull` keeps working for every other source.
Garmin-origin activities would then either vanish from listings or fail to
download. A pull that finds nothing new looks exactly like a quiet week, so
the maintainer would stop getting ride pages without any error. Phase 12's
wellness pull is exposed the same way for Garmin athletes. That is
`wellness-pull`'s Constraints; this item covers activities.

## Evidence

Thread: <https://forum.intervals.icu/t/api-access-to-intervals-icu/609>.

- **#752 (2026-10-09, developer):** "Garmin terms and conditions have been
  updated and It is likely that we will have to block access to Garmin data
  via the API soon."
- **#788 (2026-10-09, developer):** "I had a good call with Garmin today".
  The developer is "continuing to discuss what this means for all athletes
  including those using the API for their own personal analysis".
- **#816 (2026-10-12 15:00 UTC, developer):** "We are still talking to Garmin
  and nothing has been finalised yet". On fields, FIT files, streams and
  wellness: "Probably all of those." On historical data: "This will likely
  apply to historical data, anything that came in via the Garmin API." Manual
  uploads: "this only applies to data received from the Garmin API." On
  timing: "I don't have any info on that."
- **Personal API keys** are still unanswered. The question was asked in #755
  and was not addressed by #816 (viability subagent, forum JSON read
  2026-10-12).
- The connector declines a missing file quietly:
  - 404 and 422 are treated as no-file (intervals-connector Req 9.5,
    amended 2026-10-02);
  - `src/fitdocs/connectors/intervals.py` declines GPX, TCX, 404 and 422
    (`:227-248`) and maps statuses at `:384-405`.

## How to pick it up

1. Re-read the forum thread from #816 onward. Has the block landed? Does it
   cover personal keys? How does a blocked activity look in
   `/athlete/0/activities` and `/activity/{id}/file`: absent, stubbed, 403,
   or 422?
2. Decide detection. A pull should report Garmin-origin activities it can see
   but not download, rather than declining them silently. The design for
   that belongs in an intervals-connector amendment.
3. Decide the fallback route for Garmin rides and record it in the roadmap.
   Candidates:
   - **The folder connector pointed at the Edge's `Garmin/Activities`.** No
     login, and device originals. Unverified: older Edge units mount as USB
     storage, but newer ones are believed to use MTP, which macOS does not
     mount natively. Check the maintainer's model first.
   - Garmin Connect's manual per-activity export.
   - The Garmin export-zip importer, a Phase 8 follow-on.

## Open questions

- Whether to act before the block is final. Detection costs little and
  helps either way; the fallback is the maintainer's call.

## Update 2026-10-13 (Phase 12 spec batch: wellness-pull covers the wellness half)

Not closed. This item stays about activities; the `wellness-pull` spec (written,
not implemented) takes the wellness half that the Why section hands to it.

- `.kiro/specs/wellness-pull/research.md:142-151` -- the block risk and its
  four implications: a withheld field arrives as `null` or missing and is
  delivered verbatim (absent, never zero); a whole-endpoint 403 on wellness
  becomes a wellness-specific error naming the restriction and the remedies
  (`wellness = false`, the Garmin export route); nothing re-delivers a day
  because the drain could not use a delivery; a vanished attribution list
  produces a notice.
- `.kiro/specs/wellness-pull/design.md:926-936` and `:1128` (the 403 mapping and
  the error-strategy row), `:1381` (decision 11), and `:1404-1407` (a block that
  nulls re-delivered days removes the intervals.icu Garmin values from the
  series by the latest-record rule; the Garmin export route is the fallback).
  Requirement: `.kiro/specs/wellness-pull/requirements.md:239` (the docs name
  the possible Garmin restriction and the export route).
- Not covered by that spec, so still this item's: detecting a blocked
  activity listing or download, and the fallback route for Garmin rides.

## Update (2026-10-18)

Docs half done at f3f901c: docs/connectors.md (intervals section, after the `sources` default) now carries a
dated, evidence-bounded caveat -- what the developer said, what a user sees status by status (silently
absent from `listed`; 404/422 -> skipped; 403 ends the instance with the refused-client message; 401
the refused-key message; rate limit/5xx end the instance; others -> failed and retried), and the
existing alternative route (folder connector or inbox; unzip Garmin Connect's download first). The
fallback-route decision this item exists for remains open and is the maintainer's.
