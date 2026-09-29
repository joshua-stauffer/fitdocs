---
id: 2026-09-29-record-fields-still-dropped-at-ingest
title: Record fields fractional_cadence, stance_time_percent and gps_accuracy are still read nowhere, and cadence loses its fractional part
status: open
importance: low
importance_why: No page is wrong without them, but files the athlete already holds carry them and running-dynamics scoped them out; they are the natural next ingest widening.
effort: M
kind: gap
area: fit-ingest, running-dynamics, src/fitdocs/ingest/records.py, src/fitdocs/model.py
created: 2026-09-29
surfaced_by: /kiro-spec-batch (Phase 8, running-dynamics writer)
pinned_at: f500dc1
resume_command: "do: after running-dynamics lands, decide with the maintainer which of fractional_cadence (record field 53), stance_time_percent (40) and gps_accuracy (31) earn model channels; if any do, start a small ingest spec (/kiro-spec-init) that widens Samples append-only the way running-dynamics did, combines cadence + fractional_cadence into one cadence value, and states how each renders or why it does not"
context:
  - src/fitdocs/ingest/records.py
  - src/fitdocs/model.py
  - .kiro/specs/running-dynamics/research.md
  - .kiro/specs/running-dynamics/design.md
  - .kiro/specs/running-dynamics/brief.md
blocked_by: [running-dynamics]
---

## What
The record reader takes cadence from the integer `cadence` field only
(`records.py:99`); `fractional_cadence` (1/128 rpm) is never read, so
cadence precision below 1 rpm is lost. `stance_time_percent` and
`gps_accuracy` are not read anywhere under `src/`. running-dynamics lists
all three (with cycling dynamics) as out of scope.

## Why it matters
Low. Cadence precision matters for run cadence comparisons across devices;
GPS accuracy is the one signal that could explain a bad route segment. The
files that carry them are already archived.

## Evidence
- `grep -rn -i "fractional_cadence\|stance_time_percent\|gps_accuracy" src/ tests/`
  -- no hits at this pin.
- `src/fitdocs/ingest/records.py:99` -- `cadence_rpm` from `r.get("cadence")`.
- FIT SDK profile, record message: `cadence` 4 (uint8, rpm),
  `gps_accuracy` 31 (uint8, m), `stance_time_percent` 40 (uint16, scale 100,
  percent), `fractional_cadence` 53 (uint8, scale 128, rpm) -- read from
  `garmin_fit_sdk.profile.Profile['messages'][20]`.
- `.kiro/specs/running-dynamics/design.md:39` (non-goal);
  `research.md:79-80`; `brief.md:46-47` (HealthFit copies carry fractional
  cadence and GPS accuracy).

## How to pick it up
1. Read running-dynamics' shipped `Samples` widening for the append-only
   pattern and its golden/version re-pin steps.
2. Put the three fields to the maintainer; each needs a stated use on the
   page or in a metric, not just a slot on the model.
3. Spec it small; done when each chosen field is on the model with a
   synthesized fixture and absent data stays `None`.
