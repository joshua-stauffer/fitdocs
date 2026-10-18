---
id: 2026-10-18-morning-pass-skips-newer-pages-silently
title: The morning pass counts pages written by a newer fitdocs but never prints them, so their blocks go stale silently
status: open
importance: low
importance_why: Only reachable after a downgrade or a mixed-version wiki. When it happens it contradicts Req 8's objective that nothing is silently stale.
effort: S
kind: gap
area: workout-wellness, src/fitdocs/cli.py, src/fitdocs/morning/engine.py
created: 2026-10-18
surfaced_by: /kiro-validate-impl workout-wellness (review of Astra decision 15)
pinned_at: a0e4b92
resume_command: "do: decide whether the morning report should print a count of pages skipped as newer (MorningReport.newer), and if so add one line to cli._report_morning plus its SKILL.md report-line entry [queue: .kiro/queue/2026-10-18-morning-pass-skips-newer-pages-silently.md]"
context:
  - src/fitdocs/morning/engine.py
  - src/fitdocs/cli.py
  - .kiro/specs/workout-wellness/requirements.md
  - src/fitdocs/skills/fitdocs-workouts/SKILL.md
blocked_by: []
---

## What

`engine.py:68-70` counts a page whose `doc_version` is newer than
`DOC_VERSION` into `MorningReport.newer` and skips it. `cli._report_morning`
(`cli.py:781-806`) never reads `report.newer`. Such a page's block is never
refreshed, and no run says so.

No acceptance criterion is broken. Req 8.2 only says to leave the page
untouched, and Req 8.7 only requires report lines for rewrites and failures.
But Req 8's objective says "nothing is silently stale".

Astra decision 15 noticed this and removed the "universal reporting" claim
from the ownership guide, so the docs now match the code. The behavioural
question was left open.

## Why it matters

A maintainer who runs an older fitdocs against a wiki a newer one wrote gets
morning blocks that stop updating, with no signal. `fitdocs check` already
reports a newer `doc_version` for each such page, which partly mitigates this.

## Evidence

- `src/fitdocs/morning/engine.py:68-70`: `if version is not None and version > DOC_VERSION: newer += 1; continue`
- `src/fitdocs/cli.py:781-806`: there is no branch on `report.newer`.

## Open questions

- Is the `check` finding enough (then close this as dropped), or should the
  run print "Morning of: N pages written by a newer fitdocs were not
  refreshed"? Either is spec-conformant; it is the maintainer's call.
