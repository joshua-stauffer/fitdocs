---
id: 2026-09-12-missing-input-names-a-key-the-profile-visibly-has
title: The load pass reports "missing: a maximum heart rate (max_hr_bpm)" and "Cycling FTP" against an athlete.toml that visibly carries max_hr_bpm = 194 and ftp_watts = 340
status: open
importance: low
importance_why: Designed behaviour (athlete-benchmarks froze the flat keys as the rendering projection, separate from dated benchmarks) but the message names the flat key's exact spelling as the thing that is missing, so the one athlete who reads it will conclude the tool is broken rather than that a dated entry is wanted.
effort: S
kind: docs
area: athlete-benchmarks, threshold-load, src/fitdocs/load/threshold/calculator.py, src/fitdocs/load/channels/heart_rate.py, README.md
created: 2026-09-12
surfaced_by: hand session tagging 13 historical races on the real data root, then running load --no-prompt
pinned_at: e8416b5
resume_command: "do: make the missing-input wording (and the README's athlete.toml section) say that a *dated benchmark entry* ([[benchmarks.athlete.max_hr_bpm]] / [[benchmarks.ride.ftp_watts]]) is what the load pass reads, and that the flat max_hr_bpm / resting_hr_bpm / ftp_watts keys feed only zones and TRIMP; do not change the read path"
context:
  - src/fitdocs/load/threshold/calculator.py
  - src/fitdocs/load/channels/heart_rate.py
  - src/fitdocs/load/channels/power.py
  - .kiro/specs/athlete-benchmarks/design.md
  - README.md
blocked_by: []
---

## What

`athlete-benchmarks` design.md ("two facts drive the whole design") splits
`athlete.toml` into the flat *athlete-inputs projection* (`athlete.py` →
zones, TRIMP) and the dated benchmark tree the calculators read through
`ProfileView`. The flat keys are deliberately not a fallback. Nothing in the
load pass's output says so: the rendered "Not selected" lines and the skip
reasons name `max_hr_bpm`, `resting_hr_bpm`, "Running FTP (W)" / "Cycling
FTP (W)" -- the flat keys' own spellings -- as missing, next to a file whose
first lines are `max_hr_bpm = 194` and `ftp_watts = 340.0`.

## Why it matters

The message is the only guidance a non-developer gets. It reads as a bug, and
the natural "fix" (re-typing the flat key) does nothing. The real fix -- a
dated `[[benchmarks.athlete.max_hr_bpm]]` entry, or answering the prompt --
is documented only in a spec design.

## Evidence

- `workouts/2023-04-01-run-1301.md` (real data root, after `fitdocs load
  --no-prompt` on 2026-09-12), "Not selected" block: `Heart rate: not
  computed — missing: a threshold heart rate (lthr_bpm), a resting heart rate
  (resting_hr_bpm), a maximum heart rate (max_hr_bpm)`; the same root's
  `athlete.toml` lines 1–3: `resting_hr_bpm = 48`, `max_hr_bpm = 194`,
  `ftp_watts = 340.0`.
- 275 rides skipped with `missing required inputs: Cycling FTP (W)` in the
  same run.
- `src/fitdocs/load/threshold/anchors.py:156-157`: max/resting HR resolve
  through `resolve_athlete_scoped(BenchmarkKind.MAX_HR_BPM)` -- the benchmark
  tree only.

## How to pick it up

1. Read the "Physical Data Model" section of
   `.kiro/specs/athlete-benchmarks/design.md` (the flat-vs-dated split) and
   the message sites in `channels/heart_rate.py`, `channels/power.py` and
   `threshold/calculator.py::_missing_inputs`.
2. Reword to name the dated entry, and add one paragraph to README.md's
   athlete.toml / Benchmarks section stating which keys feed what.
3. Done when a reader of either the doc or the README can tell, without
   opening a spec, that the flat keys do not anchor load.
