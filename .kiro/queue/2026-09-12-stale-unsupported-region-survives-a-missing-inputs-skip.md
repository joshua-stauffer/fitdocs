---
id: 2026-09-12-stale-unsupported-region-survives-a-missing-inputs-skip
title: A load region written as "unsupported" before threshold-load shipped is never refreshed once the calculator supports the sport but skips the doc for missing inputs
status: open
importance: medium
importance_why: On the maintainer's real archive 622 runs, 243 rides and 119 walks/hikes still read "No training-load methodology supports Run activities yet" after a full `fitdocs load`, while the pass itself reports each as "missing required inputs" -- the page states something the tool knows to be false.
effort: S
kind: inconsistency
area: threshold-load, training-load, src/fitdocs/load/engine.py, src/fitdocs/load/render.py
created: 2026-09-12
surfaced_by: hand session tagging 13 historical races on the real data root, then running derive-benchmarks + load --no-prompt + history
pinned_at: e8416b5
resume_command: "do: decide what a doc whose region holds a pre-calculator 'unsupported' state should read when the compute path now selects a supporting calculator but yields MissingInputs/NotComputed under --no-prompt -- most likely rewrite the region to the 'not computed' placeholder (honest absence) instead of leaving the stale sport-level claim; pin it with a test in tests/load/test_engine.py"
context:
  - src/fitdocs/load/engine.py
  - src/fitdocs/load/render.py
  - .kiro/specs/threshold-load/requirements.md
  - .kiro/specs/training-load/requirements.md
blocked_by: []
---

## What

`_compute_document` (`src/fitdocs/load/engine.py`, the `MissingInputs` /
`NotComputed` arms) records a skip and returns without touching the document.
That is correct for a placeholder region, but a region that already holds the
*unsupported* state written by an earlier fitdocs -- when no calculator was
registered at all -- keeps that text verbatim. The text is a claim about the
tool ("No training-load methodology supports Run activities yet"), and the
claim is now false: the threshold calculator supports Run, arbitration
selected it, and the doc was skipped for a different reason (no applicable
benchmark on that date, or a stream the pass judged insufficient).

## Why it matters

The document is the only thing a wiki reader sees. After the first real load
pass on the maintainer's archive (2026-09-12), 1,016 of 2,536 documents were
skipped, and every one of them still tells the reader the wrong reason. A
reader who wants to fix it (record an FTP, add an `applies_from` benchmark)
is pointed away from the fix.

## Evidence

- `fitdocs load --no-prompt` on the real data root, 2026-09-12: `Computed 897
  / Skipped 1016 / Unsupported 0 / Failed 0`. Skip reasons: 622 × `missing
  required inputs: Running FTP (W)…`, 275 × `… Cycling FTP (W)`, 119 × `…
  Maximum heart rate (bpm)`.
- Those same documents' load regions afterwards (grep over `workouts/`):
  1,497 still carry `"status":"unsupported"` stamps; e.g.
  `workouts/2022-12-07-run-2355.md` reads `_No training-load methodology
  supports Run activities yet._` while the report line for it is `missing
  required inputs: Running FTP (W), Maximum heart rate (bpm), Resting heart
  rate (bpm)`.
- `src/fitdocs/load/engine.py` `_compute_document`: the `MissingInputs` and
  `NotComputed` arms append to `buckets.skipped` and `return profile` with no
  write; `_write_unsupported` is reached only from `NoCalculator`, the
  `supports_activity` check, and the `Unsupported` outcome.

## How to pick it up

1. Read `_compute_document` and `_write_unsupported` in
   `src/fitdocs/load/engine.py`, then `render.py`'s placeholder /
   unsupported renderers and the `RegionState` vocabulary in `docedit.py`.
2. Decide the honest state for "supported sport, no result": the existing
   `_Training load not computed._` placeholder is the obvious candidate --
   it makes no claim about the tool. Check whether threshold-load or
   training-load requirements already pin the skip-leaves-doc-untouched
   behaviour for the *unsupported* prior state specifically (they pin it for
   computed regions).
3. Done when a doc holding a stale unsupported region, processed under
   `--no-prompt` with a supporting calculator and missing inputs, is
   rewritten to the placeholder (and a test pins that), while a placeholder
   region stays byte-identical as today.
