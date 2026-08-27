---
id: 2026-08-27-anchor-provenance-missing-for-pace-and-hr
title: Reqs 3.7/8.6 unmet — build_result never reads selected.anchor, so only a power-selected result carries the benchmark's date and discipline
status: open
importance: high
importance_why: Running's default channel is pace; a pace-selected document shows no measurement date and no anchoring discipline, which is the provenance Req 3.7 exists for. User-visible in shipped markdown.
effort: S
kind: requirement-gap
area: threshold-load, src/fitdocs/load/threshold/calculator.py
created: 2026-08-27
surfaced_by: /kiro-validate-impl threshold-load
pinned_at: 3e14ab9
resume_command: "/kiro-impl threshold-load [queue: .kiro/queue/2026-08-27-anchor-provenance-missing-for-pace-and-hr.md] Emit the anchor triple in build_result from selected.anchor"
context:
  - src/fitdocs/load/threshold/calculator.py
  - src/fitdocs/load/channels/types.py
  - tests/load/threshold/test_result_assembly.py
  - .kiro/specs/threshold-load/design.md
blocked_by: []
---

## What

Req 3.7 requires reporting, for every computed channel, the anchoring
benchmark's **value**, its **measurement date** and the **discipline it was
recorded under**. Req 8.6 requires the same among `inputs_used`.

`build_result` (`calculator.py:544-600`) forwards `*selected.inputs_used` and
**never reads `selected.anchor`** — the `Benchmark` carrying all three values
reaches the calculator and is discarded. `grep -rn "\.anchor\b"
src/fitdocs/load/threshold/` returns nothing.

The triple is therefore complete only when **power** is selected, because only
`power.py` happens to put all three in its own `inputs_used`:

| selected | value | date | discipline |
|---|---|---|---|
| power | `ftp_watts` | `ftp_measured_on` | `anchoring_discipline` |
| heart rate | `lthr_bpm` | `lthr_measured_on` | **absent** |
| pace | `threshold_speed_mps` (derived m/s, not the benchmark's own value) | **absent** | **absent** |

Second half: Req 3.7 says "for every computed channel", but
`NonSelectedValue` (`load/types.py:141-148`) carries only key/label/value/reason,
so a computed-but-not-selected channel reports none of the triple.

## Why it matters

Pace is the **documented default first channel for running**
(`priority.py`: run prefers pace, then power, then heart rate), so the common
case is the one missing its provenance. `render.py:419-421` writes
`inputs_used` straight into the shipped markdown table and `:137` into the
machine-readable payload, so a reader cannot tell which threshold a run was
scored against or when it was measured.

## Evidence

Live `compute()` on a Run selected on pace, at `3e14ab9`:

```
('Intensity', '1.200') ('Scored duration', '0:10:00')
('Coverage', 'distance 100.0% of recorded time')
('grade_adjusted_speed_mps', '4') ('threshold_speed_mps', '3.33333')
('moving_time_s', '600') ('grade_adjustment_applied', 'False')
('clamped_intervals', '0')
```

No measurement date anywhere in `inputs_used`, `notes` or the payload.

**Why twelve per-task reviews missed it**: task 3.2's owned fixture
`_PACE_LOAD` (`tests/load/threshold/test_result_assembly.py:133-145`)
hand-authors rows `("Threshold pace", "300.0 s/km"), ("Anchor discipline",
"Run"), ("Measured on", "2026-01-01")` that `pace_compute` never emits, and
`test_inputs_used_appends_the_selected_channels_own_inputs_verbatim` cites Req
3.7 against that fabricated fixture. The fabrication traces to a false claim in
`design.md:1174` — "the selected channel's own `inputs_used` verbatim — which
already carries the anchor value, its discipline and its measurement date" —
which is true for power, false for pace, partly false for heart rate.

Not upstream: `ChannelLoad.anchor` (`channels/types.py:121`) carries all three
into this feature. The fix is inside `build_result`.

## How to pick it up

Read `calculator.py:544-600` and `channels/types.py:100-130`. Emit the triple
from `selected.anchor` as its own `inputs_used` rows rather than relying on
the channel's, so it is uniform across channels. Decide whether the
non-selected half of Req 3.7 is in scope or should be amended — it needs a
field on `NonSelectedValue`, which is `training-load`'s type.

Done looks like: a pace-selected result carrying the benchmark's own value,
its `measured_on` and its discipline, pinned by a test that drives the **real**
`pace_compute` rather than a hand-authored fixture, and `design.md:1174`
corrected.
