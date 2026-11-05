---
id: 2026-11-05-sleep-total-can-be-an-unmarked-partial-sum
title: SLEEP_S can be an unmarked partial sum of the stages
status: open
importance: low
importance_why: Only on a record with a bad stage, and the Garmin export has always behaved this way; a maintainer decision.
effort: S
kind: gap
area: wellness-store, src/fitdocs/wellness/formats/garmin.py
created: 2026-11-05
surfaced_by: /kiro-impl garmin-connector review
pinned_at: 154315c7
resume_command: "do: Decide whether total sleep should be absent when any stage is unreadable"
context:
  - src/fitdocs/wellness/formats/garmin.py
  - src/fitdocs/wellness/model.py
  - .kiro/specs/garmin-connector/requirements.md
blocked_by: []
---

## What
`_sleep` sums the stages it can read. A null or unreadable stage understates total sleep with no marker, a -1 stage subtracts, and one over-range stage removes the total. Req 10.3 asks for the same derivation as the export, so both formats share this.

## Why it matters
A total that looks complete can be short, against the rule that absent data stays absent.

## Evidence
`src/fitdocs/wellness/formats/garmin.py`, `_sleep`. Task 2.1 reviewer's probe: 18005 instead of 20006 with one stage unreadable; 18004 with a -1 stage. Pinned as shipped by `test_negative_stage_is_absent_but_counts_in_the_shared_total` and `test_out_of_range_stage_absent_and_the_total_is_the_raw_sum`.

## How to pick it up
Ask the maintainer. If the total should go absent, change `_sleep`, update those pins, and note the series change.
