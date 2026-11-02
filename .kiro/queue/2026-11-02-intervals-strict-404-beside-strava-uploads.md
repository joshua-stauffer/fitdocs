---
id: 2026-11-02-intervals-strict-404-beside-strava-uploads
title: A strict listing match that answers 404 beside a Strava import uploads instead of answering not_updatable
status: open
importance: medium
importance_why: With publish_upload on, a page can create a second copy of an activity that already exists as a Strava import, which Req 4.1 says must neither be updated nor uploaded over.
effort: S
kind: design-question
area: intervals-publish, src/fitdocs/connectors/intervals.py
created: 2026-11-02
surfaced_by: /kiro-impl intervals-publish
pinned_at: 978c74fa
resume_command: "/kiro-spec-design intervals-publish [queue: .kiro/queue/2026-11-02-intervals-strict-404-beside-strava-uploads.md] Decide whether a set-aside listing match next to a Strava import answers not_updatable"
context:
  - .kiro/specs/intervals-publish/requirements.md
  - .kiro/specs/intervals-publish/design.md
  - src/fitdocs/connectors/intervals.py
blocked_by: []
---

## What
When the listing holds one strict (non-Strava) match that answers 404 to the update and also a Strava import starting within a second of the page, `publish()` routes the 404 to the absent branch: with `publish_upload` on it uploads (answer `uploaded`), with it off it answers `not_found`. The Strava check in `_match_listing` only runs when no non-Strava entry matched, so it never fires here.

## Why it matters
Req 4.1 says that when the only activity is a Strava import the connector shall neither update nor upload. A vanished strict match next to a live Strava import is that situation, but the code uploads a second copy. This is the maintainer's call: amend Req 4.1 to the design's narrower reading, or re-run the Strava check after a set-aside match.

## Evidence
Reviewer scenario S25 (task 4.1 round 3 review, scratch file review-4.1r3/tree/tests/connectors/test_r3_flow.py): strict entry i7 answers 404 + Strava entry at the start -> `uploaded` (uploads on), `not_found` (off). Design flowchart routes `UpdList absent` to `Absent` (design.md, System Flows 'One publish request'). Code: `IntervalsConnector.publish` in src/fitdocs/connectors/intervals.py, the listing branch.

## How to pick it up
1. Read Req 4.1 and design.md's flow step 4/5. 2. Ask the maintainer which reading holds. 3. Either amend Req 4.1, or make publish() re-check the listing for a Strava import after the match is set aside, with a `_Flow` test (strict 404 + Strava -> not_updatable, no POST).
