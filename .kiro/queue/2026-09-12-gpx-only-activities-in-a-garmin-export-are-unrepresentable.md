---
id: 2026-09-12-gpx-only-activities-in-a-garmin-export-are-unrepresentable
title: 169 activities in the maintainer's Garmin export exist only as GPX (2014-2018 uploads from another app) and fitdocs has no way to represent them
status: open
importance: low
importance_why: The roadmap excludes GPX/TCX on the measured premise that HealthFit's GPX sidecars are the FIT track re-encoded and gain nothing; that premise does not cover a GPX with no FIT counterpart at all. 169 real activities, four years of them before any FIT exists, stay outside the wiki.
effort: M
kind: gap
area: fit-ingest, roadmap (non-.fit formats), src/fitdocs/ingest/
created: 2026-09-12
surfaced_by: hand session adopting the Garmin export into the real data root (pkm-data/raw/garmin-adoption/README.md)
pinned_at: aa851a3
resume_command: "do: decide whether a GPX-only activity (trackpoints, optional HR, no FIT) is in scope -- if yes, spec a minimal GPX reader onto the existing Activity model in src/fitdocs/ingest/ (no laps, no power, provenance says gpx); if no, record the decision beside the roadmap's GPX line so the measured-sidecar argument is not read as covering this case"
context:
  - .kiro/steering/roadmap.md
  - src/fitdocs/ingest/decode.py
  - src/fitdocs/model.py
blocked_by: []
---

## What

The Garmin "complete data" export's `DI-Connect-Uploaded-Files` zips hold
169 GPX files and the summarized-activities JSON lists exactly 169
activities with `deviceId 0` / `activityType other` (names like "Palisades
Park Uncategorized"): 2014 × 75, 2016 × 14, 2017 × 11, 2018 × 69. None has a
FIT file in the export and none has a document in the wiki (matched by GPX
`<time>` against every archived FIT's session start, ±3 min and whole-hour
offsets both checked). `fitdocs sync` discovers `*.fit` only.

## Why it matters

Four years of the maintainer's running history predate any FIT-recording
device. `.kiro/steering/roadmap.md` line ~55 rules out GPX/TCX because
HealthFit's sidecars duplicate the FIT; that measurement is right and
irrelevant here. The history page's span, the criterion-point count and any
future model fit all start at the first FIT.

## Evidence

- `pkm-data/raw/garmin-adoption/README.md`, "Not represented".
- `DI_CONNECT/DI-Connect-Fitness/*_summarizedActivities.json`: 1,067
  activities; 898 have an `activity` FIT (`garmin-fit-index.json`); the 169
  without one are all `deviceId: 0`, `activityType: "other"`.
- Sample GPX header: `joshua@joshuastauffer.com_27650511204_2014-01-17-161739.gpx`,
  `<time>2014-01-17T21:17:39Z</time>`, `<trkpt>` present, no `hr` extension.

## How to pick it up

1. Read the roadmap's non-`.fit` paragraph and `src/fitdocs/ingest/decode.py`
   to see how narrow the Activity model's inputs are.
2. Measure what the 169 GPX files carry (trackpoints only? elevation? HR
   extensions on any?) before deciding; a track-only reader is small, a
   GPX→FIT converter is not (the Python garmin-fit-sdk has no encoder).
3. Done when either a reader lands with provenance naming the format, or
   the roadmap line carries the explicit "FIT-less GPX is also out" decision.
