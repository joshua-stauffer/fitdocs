---
id: 2026-10-18-heart-rate-zero-as-dropout-decision
title: Decide whether a recorded heart rate of 0 is a dropout (absent) or data, for load coverage and impulse
status: open
importance: low
importance_why: Today a device that writes heart_rate=0 for a strap dropout counts that span as covered and scores zero impulse for it; whether that happens on real files is unmeasured.
effort: S
kind: research
area: load-channels, src/fitdocs/load/channels/sufficiency.py, .kiro/specs/load-channels/requirements.md
created: 2026-10-18
surfaced_by: queue-prerelease session (chore/q-sufficiency implementer + review)
pinned_at: aaf0a1a
resume_command: "/kiro-spec-requirements load-channels [queue: .kiro/queue/2026-10-18-heart-rate-zero-as-dropout-decision.md] Decide whether heart rate 0 is a dropout, after measuring how often real files record it"
context:
  - src/fitdocs/load/channels/sufficiency.py
  - .kiro/specs/load-channels/requirements.md
  - .kiro/queue/closed/2026-09-12-sufficiency-zero-samples-and-fabricated-observed.md
blocked_by: []
---

## Question

load-channels Req 2.10 (requirements.md:159) treats every recorded zero as recorded data, so a
coasting 0 W counts toward power coverage. The coverage gate is shared by all channels, so a
`heart_rate_bpm == 0` sample also counts as covered. Physiologically HR 0 is never a measurement.

## Options

- A. Leave it: Req 2.10 is intended for every channel (recommended if real files never write HR 0).
- B. Normalise HR 0 to None at ingest or in the heart-rate channel (Req 2.10 amendment; changes load
  values, so a version decision; computed values persist until `fitdocs load --recompute`).
- C. A channel-specific "zero is absent" rule inside `sufficiency.evaluate` (amendment).

## Evidence needed first

Count `heart_rate == 0` records across the real archive (pkm-data fit-archive) per device.
