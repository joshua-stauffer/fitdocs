---
id: 2026-11-02-intervals-record-ignores-absent-set
title: The pull-record step ignores activities already set aside after a 404
status: open
importance: low
importance_why: A stale id in the pull record can turn a resolvable page into `ambiguous`, or stop the record's second tier from being consulted.
effort: S
kind: inconsistency
area: intervals-publish, src/fitdocs/connectors/intervals.py
created: 2026-11-02
surfaced_by: /kiro-impl intervals-publish
pinned_at: 978c74fa
resume_command: "/kiro-impl intervals-publish [queue: .kiro/queue/2026-11-02-intervals-record-ignores-absent-set.md] Make _record_activity skip ids already set aside"
context:
  - .kiro/specs/intervals-publish/requirements.md
  - src/fitdocs/connectors/intervals.py
  - tests/connectors/test_intervals_publish.py
blocked_by: []
---

## What
`_record_activity` does not see the `absent` set that `publish()` keeps. If the recorded link's activity answered 404 and the pull record's base digest names that id plus another, the answer is `ambiguous`; if the base names only the set-aside id, the extra-digest tier is never consulted and the answer can be `not_found` while another activity is named.

## Why it matters
Req 3.10 says an activity answered absent is excluded for the rest of the request; Req 3.2 reads the second tier only when the base names no activity. Both readings are violated when the base's only id is already set aside.

## Evidence
Validation review spot2.py: link i8000001 -> 404, base names {i8000001, i5001} -> `ambiguous`; base -> i8000001, extra -> i5001, empty listing -> `not_found` with puts == ['i8000001']. Code: `_record_activity` (intervals.py ~932-961) takes no `absent` argument.

## How to pick it up
1. Pass `absent` into `_record_activity` and drop set-aside ids per tier. 2. Add `_Flow` tests for both scenarios above. 3. Check the docs Publishing notes still match.
