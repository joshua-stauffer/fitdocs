---
id: 2026-10-13-wellness-wrist-temperature-has-no-metric
title: "Sleeping wrist temperature has no wellness metric, so the Apple Health import drops a record type its own brief lists"
status: open
importance: low
importance_why: A signal the athlete's watch records nightly goes unused; nothing is wrong with what is imported, and a later export holds the whole history, so adding the metric later loses no data.
effort: M
kind: gap
area: wellness-store, apple-health-import, src/fitdocs/units.py
created: 2026-10-13
surfaced_by: /kiro-spec-batch phase 12 (apple-health-import spec, controller queue triage)
pinned_at: 86cdf14
resume_command: "do: after wellness-store and apple-health-import have landed, add a sleeping wrist temperature metric to the wellness vocabulary (unit token c already exists in src/fitdocs/units.py), map the Apple record type to it in the Apple Health extract and reducer, and raise the extract and rules versions; the maintainer re-exports once because older extracts do not keep the type [queue: .kiro/queue/2026-10-13-wellness-wrist-temperature-has-no-metric.md]"
context:
  - .kiro/specs/apple-health-import/brief.md
  - .kiro/specs/apple-health-import/design.md
  - .kiro/specs/apple-health-import/requirements.md
  - .kiro/specs/wellness-store/design.md
  - src/fitdocs/units.py
blocked_by: [wellness-store, apple-health-import]
---

## What

The apple-health-import brief lists `AppleSleepingWristTemperature` among the
Health record types that matter. wellness-store's metric vocabulary has 28
metrics and none is a temperature, so the import's requirements exclude the
type ("wrist temperature" is named in the list of types fitdocs imports no
other of), and its extract deliberately does not keep the records "for later".
`src/fitdocs/units.py` already has a degrees-Celsius unit (`c`), so the unit
side is ready. A follow-on would add the metric to the vocabulary, map the
Apple type to it, and make the extract keep the type.

## Why it matters

Sleeping wrist temperature is one of the nightly signals an Apple Watch
records and a plausible input for a recovery view; the recovery spec could
only show it once the series carries it. Because the extract drops the type,
adding it later needs the athlete to produce a new export (an export always
holds the whole history, so no data is lost, but the step is manual).

## Evidence

Read at `86cdf14`.

- `.kiro/specs/apple-health-import/brief.md:26-28` -- lists
  `AppleSleepingWristTemperature` among the record types that matter.
- `.kiro/specs/apple-health-import/requirements.md:182` -- Req 7.7: "fitdocs
  shall import no other Apple Health record type, including heart rate,
  walking heart rate, wrist temperature, workouts, nutrition and the rMSSD
  type"; `design.md:37-39` (Non-Goals) says the same.
- `.kiro/specs/apple-health-import/research.md:231-239` and `design.md:1109-1110`
  -- the extract keeps exactly the eight read types; wrist temperature and
  rMSSD "are not kept for later (a later fitdocs asks for one new export,
  which always holds the whole history)".
- `.kiro/specs/wellness-store/design.md:1386-1421` -- the metric vocabulary:
  28 rows, none a temperature. Task 1.1 (`tasks.md:181-188`) appends only two
  units, `ml_per_kg_min` and `brpm`.
- `src/fitdocs/units.py:61` -- `Unit("c", "degrees Celsius", "°C", ...)`
  already exists; `src/fitdocs/model.py:142`
  (`temperature_c`) is the activity-stream use.

## How to pick it up

1. Read the metric vocabulary in wellness-store `design.md` § The Metric
   Vocabulary and its model task (1.1), and apple-health-import `design.md`
   § Reduce (the `POLICIES` table, `:887-904`).
2. Decide the metric name, valid range and the day rule. This session did not
   see a real export, so whether Apple states the value as an absolute
   temperature or as a deviation from a baseline is unknown; check a real
   export first (task 6.2* in apple-health-import is the maintainer-run
   smoke, and its `research.md` marks such identifiers and units `[verify]`).
3. Add the metric, the Apple mapping and a `rules_version` bump in the same
   change as the extract keeping the type. Done when the series carries the
   metric from a fresh export and the recovery spec has been told it exists.

## Open questions

- Does Garmin's export carry a comparable skin-temperature field? If so the
  metric's meaning should be defined across sources (as the vocabulary does
  for HRV) before it is named.
