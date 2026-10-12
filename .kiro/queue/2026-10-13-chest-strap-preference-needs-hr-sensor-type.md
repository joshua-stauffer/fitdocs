---
id: 2026-10-13-chest-strap-preference-needs-hr-sensor-type
title: "Max-heart-rate derivation cannot prefer chest-strap sessions because fit-ingest records no heart-rate sensor type"
status: open
importance: low
importance_why: Optical wrist sensors read high or low in ways a strap does not, so a derived maximum can be biased by the sensor; the derivation's sustained-peak maxima and cadence-lock rejection (brief.md:89-91) blunt the worst of it, and a hand-recorded value is never replaced by agreeing evidence.
effort: M
kind: gap
area: fit-ingest, hr-derivation, src/fitdocs/model.py, src/fitdocs/ingest/summary.py
created: 2026-10-13
surfaced_by: /kiro-spec-batch phase 12 (hr-derivation spec, controller queue triage)
pinned_at: 86cdf14
resume_command: "/kiro-spec-requirements fit-ingest [queue: .kiro/queue/2026-10-13-chest-strap-preference-needs-hr-sensor-type.md] Record the heart-rate sensor's device type (including the ANT+ device type) on DeviceInfo so a later heart-rate derivation can prefer chest-strap sessions"
context:
  - src/fitdocs/model.py
  - src/fitdocs/ingest/summary.py
  - .kiro/specs/hr-derivation/design.md
  - .kiro/specs/hr-derivation/research.md
  - .kiro/specs/hr-derivation/brief.md
  - .kiro/specs/fit-ingest/design.md
blocked_by: []
---

## What

The hr-derivation brief asked for "a preference for chest-strap sessions where
the source is known" when deriving the maximum heart rate. The spec drops it:
`DeviceInfo`, the model's record of a device that contributed to an activity,
holds a manufacturer, product name, serial number, software version and
battery status, and no device type or ANT+ device type, so a strap cannot be
told from a wrist sensor in any activity fitdocs has read. The derivation
treats every session alike.

## Why it matters

Maximum heart rate is the number most affected by sensor type: a wrist sensor
can lock onto cadence or miss a spike, and a strap rarely does. With no
preference, a strap-recorded effort and a wrist-recorded one count equally
toward the sustained maximum. The cost is accuracy of a derived benchmark, not
correctness of any figure fitdocs prints, which is why this is low.

## Evidence

Read at `86cdf14`.

- `src/fitdocs/model.py:249-258` -- `DeviceInfo` has six fields:
  `device_index`, `manufacturer`, `product_name`, `serial_number`,
  `software_version`, `battery_status`.
- `src/fitdocs/ingest/summary.py:302-311` -- `_build_device` maps exactly those
  six keys from the `device_info` message; no device-type key is read.
  `grep -rn "device_type\|antplus\|ant_device" src/fitdocs` returns nothing.
- `.kiro/specs/hr-derivation/brief.md:92` -- the wished-for "preference for
  chest-strap sessions where the source is known".
- `.kiro/specs/hr-derivation/research.md:166-171` -- "A chest-strap preference
  cannot be implemented without a fit-ingest amendment; it is out of scope and
  recorded as a follow-up."
- `.kiro/specs/hr-derivation/design.md:1352` -- decision 12: "No chest-strap
  preference: the model does not record the sensor type."
  `requirements.md:103-111` says the same in its Out of scope list
  ("telling a chest strap from a wrist sensor, because no activity fitdocs
  reads records the heart-rate sensor's type").

## How to pick it up

1. Probe what a real activity's `device_info` messages carry for the heart-rate
   sensor (the FIT profile has `device_type` and `antplus_device_type` fields;
   which files populate them is unknown to this session). Count only; no
   personal data enters the repository.
2. Draft a fit-ingest amendment: add the field(s) to `DeviceInfo` with the
   usual absent-is-`None` rule, update `_build_device`, `docs/plugins.md:252` (`DeviceInfo` is on
   the listed plugin surface), and the plugin-surface pins.
3. Then amend hr-derivation to weigh or prefer strap sessions, with a stated
   rule for sessions whose sensor is unknown (treated as today, never assumed
   optical). Done when the preference changes a derived maximum in a test that
   would not have changed it before.

## Open questions

- Prefer, weight, or require a strap? A requirement would leave athletes
  without a strap with no derived maximum.
