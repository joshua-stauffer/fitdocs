---
id: 2026-09-12-missing-input-names-a-key-the-profile-visibly-has
title: The load pass reports "missing: a maximum heart rate (max_hr_bpm)" and "Cycling FTP" against an athlete.toml that visibly carries max_hr_bpm = 194 and ftp_watts = 340
status: open
importance: medium
importance_why: Raised from low on 2026-09-12 (validate-impl): the heart-rate channel is not merely mis-worded, it is structurally unreachable for a pace- or power-anchored athlete -- the prompt for the two athlete-wide HR benchmarks fires only when NO channel selects, so it never fires on a run or a powered ride, and the 111 walks / 8 hikes that would ask were run under --no-prompt; the result is zero HR load anywhere in a 2767-doc archive whose profile visibly carries both numbers.
effort: S (docs) / M (seed or prompt path)
kind: gap
area: athlete-benchmarks, threshold-load, src/fitdocs/load/threshold/calculator.py, src/fitdocs/load/channels/heart_rate.py, README.md
created: 2026-09-12
surfaced_by: hand session tagging 13 historical races on the real data root, then running load --no-prompt
pinned_at: e8416b5
resume_command: "do: decide between (a) wording+README only (dated entry is what load reads; flat keys feed zones/TRIMP) and (b) giving the athlete-wide HR benchmarks an entry point that does not require no channel to select -- e.g. collect declared fields whose kind is athlete-scoped and not_on_file even when another channel wins, or seed [[benchmarks.athlete.*]] from the flat keys on first load with an explicit applies_from; keep the read path (flat keys are never a fallback) either way"
context:
  - src/fitdocs/load/threshold/calculator.py
  - src/fitdocs/load/channels/heart_rate.py
  - src/fitdocs/load/channels/power.py
  - .kiro/specs/athlete-benchmarks/design.md
  - README.md
  - src/fitdocs/load/threshold/anchors.py
  - src/fitdocs/load/priority.py
  - .kiro/specs/threshold-load/requirements.md
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

## Update 2026-09-12 (validate-impl, "was heart rate included in historical load?")

Re-verified at fdf10a7 on a scratch copy of the real data root. The wording
is the symptom; the gap is that nothing ever *collects* the two athlete-wide
HR benchmarks for this athlete:

- `src/fitdocs/load/threshold/calculator.py::compute` returns `MissingInputs`
  (the only path that prompts) **only when `select()` picked no channel**.
  `src/fitdocs/load/priority.py:40-43`: Run = pace > power > heart_rate,
  Ride = power > heart_rate. So every run with an applicable threshold pace
  and every ride with an applicable FTP selects, and the HR channel's
  `NO_BENCHMARK` outcome is written as a "Not selected" line forever, never
  asked about. Only Walk/Hike (order = heart_rate alone) would prompt, and
  the real run used `--no-prompt`.
- Real archive tally (2767 docs): 1027 runs `computed/pace`, 92 rides
  `computed/power`, **0 docs with any HR value, selected or not**; 603 runs,
  182 rides, 111 walks, 8 hikes stamped `unsupported` (see sibling item
  `2026-09-12-stale-unsupported-region-survives-a-missing-inputs-skip`).
- Verified unlock (scratch root = real `athlete.toml` + two entries
  `[[benchmarks.athlete.max_hr_bpm]] value=194 measured_on=2022-01-01` and
  `[[benchmarks.athlete.resting_hr_bpm]] value=48 measured_on=2022-01-01`,
  `fitdocs load --out <scratch> --recompute --no-prompt`):
  - `2024-10-13-run-0910.md`: still `basis: pace` 118, but the HR line now
    reads `heart_rate -> 112.887 not selected: the configured order for Run
    prefers Pace` (values agree to ~5%).
  - `2024-03-12-walk-2259.md`: `computed`, `basis: heart_rate`, 12.0,
    `lthr_bpm = 173` borrowed from Run per `discipline.ANCHOR_PLANS`.
  - `2025-07-25-ride-1530.md`: still skipped, `missing required inputs:
    Cycling LTHR (bpm)` -- the Ride chain does not borrow the Run LTHR.
- The agent-log claim of 2026-09-12T13:45:34Z ("pre-2022-12-29 files carry NO
  distance stream ... unscoreable by threshold-load regardless of
  benchmarks") holds for the pace channel only. With the two entries above
  plus `applies_from = 2018-01-01` on the earliest Run LTHR, a plain
  `fitdocs load --no-prompt` (no --recompute) revisited the stale
  `unsupported` region of `2022-09-29-run-0028.md` and wrote `computed`,
  `basis: heart_rate`, 42.3, `Coverage heart_rate 100.0%`. A 2019 sample
  (`2019-02-09-run-0445.md`) stays unscoreable for a different reason: HR is
  non-null on 26 of 3102 samples. So the pre-pace era is *partly* HR-scoreable
  and the history series could start earlier than 2022-12-29 -- a data-root
  decision for Josh (the `applies_from` backdate is an athlete declaration,
  athlete-benchmarks 3.10), not a code change.
- Note for whoever picks this up: `MissingInputs` also masks the HR reason --
  the 2019 run was reported as `missing required inputs: Running FTP (W)`
  because run FTP is `not_on_file`, while the HR channel's own reason (max /
  resting not applicable on that date) never reached the summary.

