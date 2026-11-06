---
id: 2026-11-06-intervals-upload-followup-update-has-no-strava-check
title: After an upload, the intervals connector updates the activity it is told about with no Strava check, though the docs say a Strava import is never updated
status: open
importance: low
importance_why: Needs intervals.icu to answer an upload by naming a Strava import, which nobody has observed; publish_upload is off by default.
effort: S
kind: inconsistency
area: intervals-publish, src/fitdocs/connectors/intervals.py, docs/connectors.md
created: 2026-11-06
surfaced_by: independent fact-check of draft PR 5
pinned_at: 7f58681e
resume_command: "do: decide whether the update after an intervals.icu upload should check the activity's source, or whether docs/connectors.md line 284 should narrow to listed activities [queue: .kiro/queue/2026-11-06-intervals-upload-followup-update-has-no-strava-check.md]"
context:
  - src/fitdocs/connectors/intervals.py
  - docs/connectors.md
  - .kiro/specs/intervals-publish/requirements.md
  - .kiro/queue/2026-11-02-intervals-strict-404-beside-strava-uploads.md
blocked_by: []
---

## What
`docs/connectors.md:284` says "An activity that intervals.icu imported from Strava is never updated." That holds for the listing, where a Strava import is never matched. After an upload, `IntervalsConnector.publish` takes the activity id the answer names and updates it without checking its source (`src/fitdocs/connectors/intervals.py:461-467`: `named = uploaded.activity_id`, then `_update(session, headers, named, request.post)`).

## Why it matters
If intervals.icu ever answered an upload by naming an existing Strava import, fitdocs would change that activity's name and description, which intervals-publish Requirement 4.1 and the docs rule out.

## Evidence
- The lines above, read at 7f58681e.
- A reviewer ran this with a scripted fake transport: an upload answer naming an activity led to a `PUT` with no source check. Not run against intervals.icu.
- Unknown: whether intervals.icu ever answers this way. The upload may refuse or deduplicate first.
- Draft PR 5's website copy already says "A listed activity that intervals.icu imported from Strava is never chosen", so the site is narrower than `docs/`.

## How to pick it up
1. Read Requirement 4.1 and `publish`'s upload branch.
2. If the maintainer has an intervals.icu account with a Strava import, check what an upload of that activity's file answers.
3. Either narrow the sentence at `docs/connectors.md:284` to listed activities, or have the update read the activity's source first, with a `_Flow` test. Decide with `2026-11-02-intervals-strict-404-beside-strava-uploads`, which is the same requirement.
