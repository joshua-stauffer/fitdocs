---
id: 2026-11-02-intervals-listing-elapsed-int
title: Confirm the intervals.icu listing's elapsed_time is an integer
status: open
importance: low
importance_why: A float elapsed_time would read as absent and weaken the strict match for pages without distance.
effort: XS
kind: unverified-assumption
area: intervals-publish design / task 5.2 live check
created: 2026-11-02
surfaced_by: /kiro-impl intervals-publish
pinned_at: 978c74fa
resume_command: "/kiro-impl intervals-publish 5.2 [queue: .kiro/queue/2026-11-02-intervals-listing-elapsed-int.md] Also record the listing's elapsed_time form"
context:
  - .kiro/specs/intervals-publish/design.md
  - .kiro/specs/intervals-publish/research.md
  - src/fitdocs/connectors/intervals.py
blocked_by: []
---

## What
design.md's ListedActivity says `elapsed_s ... # int >= 0, not bool`, and `_listed_activity` treats a float elapsed_time as absent. research.md's TBC-P2 names distance, external_id and start_date_local but not elapsed_time's form.

## Why it matters
If intervals.icu returns floats, every listing entry loses its elapsed time and pages without distance never match strictly.

## Evidence
design.md ActivityFinding `ListedActivity`; tests pin float -> absent (tests/connectors/test_intervals_publish.py malformed elapsed cases); research.md TBC-P2.

## How to pick it up
During the maintainer-gated live check (task 5.2), record elapsed_time's JSON form. If it can be a float, amend the design and accept finite non-negative floats.
