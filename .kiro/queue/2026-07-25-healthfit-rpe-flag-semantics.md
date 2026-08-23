---
id: 2026-07-25-healthfit-rpe-flag-semantics
title: Confirm what HealthFit's WORKOUT RPE ESTIMATED actually means
status: open
importance: low
importance_why: Nothing false is printed now that the key is unrecognized; this only unlocks a signal we currently discard.
effort: S
kind: research
area: workout-docs, src/fitdocs/render/sections.py
created: 2026-07-25
surfaced_by: /kiro-validate-design on the Avg METs scale defect
pinned_at: c3d2201
resume_command: 'do: Re-scan the HealthFit corpus for WORKOUT RPE ESTIMATED values outside {0,1}; if any exist it is a value, not a flag — re-add it to _SUPPLEMENTALS with the confirmed scale.'
context:
  - src/fitdocs/render/sections.py
  - .kiro/specs/workout-docs/design.md
  - .kiro/specs/workout-docs/requirements.md
blocked_by: []
---

## What

`WORKOUT RPE ESTIMATED` was removed from the recognized supplementals
(`_SUPPLEMENTALS` in `src/fitdocs/render/sections.py`) because the evidence says
it is a boolean flag — "the RPE was estimated" — rather than an RPE value. That
reading is well-supported but not *confirmed* against HealthFit documentation,
and the field is still ingested and available on `Activity.developer_fields`.
If it turns out to carry a real RPE on some scale, we are discarding a signal
present on 14 of 74 files.

Josh decided on 2026-07-25 to drop the investigation and ship the removal; this
item exists so a later session can resume from the evidence rather than
re-derive it.

## Why it matters

Low stakes in the current state — omitting the row is the safe direction, and
no document asserts anything false. The upside is recovering a per-workout
subjective-effort signal, which is the one input `training-load` cannot derive
from telemetry. The downside of leaving it is only the lost signal.

## Evidence

Corpus scan over 74 real HealthFit files in `~/code/fitdocs-demo/inbox/`,
decoding `field_description_mesgs` + `session_mesgs[0]['developer_fields']`:

```
WORKOUT RPE ESTIMATED  n=14  min=0 max=1  base type 2 (UINT8)
  values: [0, 0, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1]
```

No correlation with effort — `RPE=1` spans 2.59 kcal/min (walking) to
13.45 kcal/min (running), and both `RPE=0` files (5.02, 5.71 kcal/min) sit
*inside* that range. A value of 0 or 1 is not a valid RPE on Borg 6–20 or on
CR10 0–10, and the field name reads naturally as a past participle ("RPE was
estimated"). The descriptor declares `scale=None, offset=None, units=None`, so
no scale is recoverable from the file.

Before removal it rendered as `| RPE | 1 |` in 12 demo documents and
`| RPE | 0 |` in 2.

## How to pick it up

1. Read the `_SUPPLEMENTALS` comment block in `src/fitdocs/render/sections.py` —
   it records the full reasoning and the numbers above.
2. Re-run the corpus scan against the current `~/code/fitdocs-demo/inbox/` (it
   grows as Josh exports). Done means: either a value outside `{0,1}` appears —
   in which case it is a value, determine its scale the way `AVG METs` was
   determined and re-add it — or the range still holds and this item closes as
   `dropped` with the flag reading confirmed.
3. If it is confirmed a flag and worth surfacing at all, the honest rendering is
   `RPE estimated | Yes/No`, not a number. That needs a `_SUPPLEMENTALS` entry
   shape that can format a bool, which the current 5-tuple cannot.

## Open questions

- Is a boolean "RPE was estimated" worth a summary row at all? It says nothing
  about the workout, only about how HealthFit filled a field.
