---
id: 2026-11-02-intervals-publish-req-6-8-wording
title: intervals-publish Req 6.8 wording is broader than the design and code
status: open
importance: low
importance_why: The requirement says not-found plus an unreadable record answers local-record-unreadable, but an unreadable record with only a Strava import answers not_updatable.
effort: XS
kind: spec-wording
area: intervals-publish requirements
created: 2026-11-02
surfaced_by: /kiro-impl intervals-publish
pinned_at: 978c74fa
resume_command: "/kiro-spec-requirements intervals-publish [queue: .kiro/queue/2026-11-02-intervals-publish-req-6-8-wording.md] Narrow Req 6.8 to the design's flow order"
context:
  - .kiro/specs/intervals-publish/requirements.md
  - .kiro/specs/intervals-publish/design.md
blocked_by: []
---

## What
Req 6.8 reads as if any not-found outcome with an unreadable pull record answers `local_record_unreadable`. The design's step 4 (listing match, including the Strava check) runs before the absent branch, so an unreadable record plus a Strava-only listing answers `not_updatable`, as the code and docs do.

## Why it matters
A future reader could 'fix' the code to match the requirement and break the documented behaviour.

## Evidence
requirements.md ~183 (Req 6.8) vs design.md ~736-741; reviewer scenario A (review-4.1r2 test_review_scn.py) -> not_updatable; docs/connectors.md Publishing unreadable-record paragraph.

## How to pick it up
Amend Req 6.8 with a dated amendment: local-record-unreadable applies when the link, the record and the listing (match and Strava check) found nothing.
