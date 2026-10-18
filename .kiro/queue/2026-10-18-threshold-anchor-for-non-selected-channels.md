---
id: 2026-10-18-threshold-anchor-for-non-selected-channels
title: threshold-load Req 3.7 "every computed channel" is unmet for computed-but-not-selected channels -- amend the requirement or extend NonSelectedValue
status: open
importance: medium
importance_why: Contract disagreement between Req 3.7 / design.md:507 and the shipped payload; a non-selected channel's anchor (value, date, discipline) is not recorded anywhere on the page.
effort: M
kind: inconsistency
area: threshold-load, training-load, src/fitdocs/load/types.py, src/fitdocs/load/render.py, .kiro/specs/threshold-load/requirements.md
created: 2026-10-18
surfaced_by: independent review of chore/q-threshold-notes (queue-prerelease session)
pinned_at: 055bd213
resume_command: "/kiro-spec-requirements threshold-load [queue: .kiro/queue/2026-10-18-threshold-anchor-for-non-selected-channels.md] Decide whether Req 3.7 covers non-selected channels (amend) or NonSelectedValue gains anchor fields (payload change, LOAD_PAYLOAD_VERSION bump)"
context:
  - .kiro/specs/threshold-load/requirements.md
  - .kiro/specs/threshold-load/design.md
  - src/fitdocs/load/types.py
  - src/fitdocs/load/render.py
  - .kiro/queue/closed/2026-08-27-anchor-provenance-missing-for-pace-and-hr.md
blocked_by: []
---

## Evidence

Real run selected on pace: Power (16.7) and Heart rate (9.7) are computed but not selected and carry no
anchor value, date or discipline. `NonSelectedValue` (src/fitdocs/load/types.py ~131-148) has only
key/label/value/reason; design.md ~507 still traces Req 3.7 as "per computed channel". The selected
channel's triple was fixed at 055bd213.

## Options

- Amend Req 3.7 to "the selected channel" (cheapest; maintainer call).
- Add anchor fields to `NonSelectedValue`: payload encode/decode change + `LOAD_PAYLOAD_VERSION` bump;
  existing results become SUPERSEDED.
- Emit per-channel rows into `inputs_used` (conflicts with Req 8.6 "inputs that produced the selected value").
