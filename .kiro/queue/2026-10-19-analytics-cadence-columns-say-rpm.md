---
id: 2026-10-19-analytics-cadence-columns-say-rpm
title: The analytics schema calls running cadence "revolutions per minute" with no strides-per-minute caveat
status: open
importance: medium
importance_why: An agent answering from the schema alone reports running cadence at half the steps-per-minute figure runners expect, with confidence.
effort: S
kind: docs
area: analytics-index, src/fitdocs/index/, docs/analytics.md, src/fitdocs/skills/fitdocs-analytics/SKILL.md
created: 2026-10-19
surfaced_by: 0.2 site-copy update (analytics fact-gathering subagent; verified by the session)
pinned_at: 90cd00b
resume_command: "do: state in the analytics schema's column descriptions (the source docs/analytics.md is generated from) and in the fitdocs-analytics skill that running cadence columns ending _cadence_rpm hold strides per minute (one foot, the FIT convention; double for steps per minute), regenerate docs/analytics.md, and pin the sentence"
context:
  - docs/analytics.md
  - src/fitdocs/index/schema.py
  - src/fitdocs/skills/fitdocs-analytics/SKILL.md
  - src/fitdocs/skills/fitdocs-dashboards/SKILL.md
  - .kiro/queue/2026-09-29-record-fields-still-dropped-at-ingest.md
blocked_by: []
---

## What
- **Where the caveat is missing.** `docs/analytics.md` describes
  `avg_cadence_rpm` and `max_cadence_rpm` (and the matching `laps` and
  `records` columns) only as "revolutions per minute". The
  `fitdocs-analytics` skill does not mention cadence either.
- **What a running cadence holds.** For a run, the stored value is strides
  per minute (one foot, the FIT convention), so steps per minute is double.
- **Where it is already stated.** Only the `fitdocs-dashboards` skill says
  so.
- **What the site does.** The new site page (branch `chore/site-copy-0-2`,
  `website/content/guides/analytics.md`) states the caveat. The repo's own
  schema reference still does not.

## Why it matters
An agent that knows only the schema will report "85 spm", or compare 85
against the usual 170–180 spm guidance and conclude something nonsensical.
The maintainer's first real analytics session hit exactly this. His notes
are in an untracked file in the main working tree, not in git, so they are
not quoted here.

## Evidence
- `docs/analytics.md:150-151` (activities):
  `| avg_cadence_rpm | DOUBLE | revolutions per minute | Average cadence in revolutions per minute. |`
  and the max row. Also `:256` and `:421`, which are the laps and records
  rows. All at 90cd00b.
- `src/fitdocs/skills/fitdocs-dashboards/SKILL.md:147-153` ("## Running
  cadence"): "Running cadence columns, those ending `_cadence_rpm`, hold
  strides per minute: one foot, the FIT convention. They are not steps per
  minute."
- `grep -n -i cadence src/fitdocs/skills/fitdocs-analytics/SKILL.md` prints
  nothing at 90cd00b: the analytics skill never mentions cadence.

## How to pick it up
1. Find where the column descriptions are defined. `docs/analytics.md` is
   generated from a schema-only index, so start from
   `src/fitdocs/index/schema.py` and the generator test.
2. Add the strides-per-minute sentence for the cadence columns, plus a line
   in the `fitdocs-analytics` skill.
3. Regenerate `docs/analytics.md`.
4. Done when `fitdocs query --schema` and the doc both carry the caveat.

The related precision gap (`fractional_cadence` is never read) is
`2026-09-29-record-fields-still-dropped-at-ingest`.
