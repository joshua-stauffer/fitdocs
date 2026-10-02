---
id: 2026-10-02-intervals-any-422-is-permanent-no-file-skip
title: intervals.icu connector treats every download 422 as "no original file", a final skip, whatever the body says
status: open
importance: low
importance_why: Any other 422 meaning would permanently skip a real activity, and the only recovery is editing the ledger; the live service has so far shown 422 only for the no-file case.
effort: S
kind: risk
area: intervals-connector, src/fitdocs/connectors/intervals.py
created: 2026-10-02
surfaced_by: /kiro-validate-impl intervals-connector (integration validator)
pinned_at: 9d08482
resume_command: "/kiro-impl intervals-connector [queue: .kiro/queue/2026-10-02-intervals-any-422-is-permanent-no-file-skip.md] Decline a download 422 only when its body says the activity has no original file"
context:
  - src/fitdocs/connectors/intervals.py
  - .kiro/specs/intervals-connector/design.md
  - .kiro/specs/intervals-connector/research.md
blocked_by: []
---

## What
`fetch_activity` maps any 404 or 422 to `Declined(NO_FILE_REASON)`, which the
pull engine records as a final skip and never asks about again. The mapping
was added after the 2026-10-02 live check found intervals.icu answers an
activity without a file with 422 `{"status":422,"error":"Activity has no
original file to download"}` (research.md "Live check findings", TBC-6). A
422 that means something else, such as a transient processing state, would
also be skipped permanently.

## Why it matters
The skip is silent and permanent. It is cheap to make the decline depend on
the body, or to treat other 422s as an ordinary download failure that is
retried next pull.

## Evidence
- `src/fitdocs/connectors/intervals.py:246`: `if response.status in (404, 422):`.
- research.md "Live check findings", TBC-6: the 422 body as observed (one
  activity, one account).

## How to pick it up
1. Decide the rule. One option: decline a 422 only when the JSON body's
   `error` names a missing original file. Any other 422 becomes an
   `IntervalsDownloadError`, a per-item failure retried next pull.
2. Amend design.md's download mapping and the Error Handling table (TBC-6
   note), then pin both branches in `tests/connectors/test_intervals.py` and
   run the mutation that makes them equal.
