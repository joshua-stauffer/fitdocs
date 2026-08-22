# Brief: fit-ingest

## Problem

Everything downstream (documents, charts, load) needs a reliable, typed view
of what happened in a workout. `.fit` is a binary format with device quirks,
sport-specific message types, and absent-vs-zero pitfalls; parsing concerns
must not leak into renderers or load calculators.

## Current State

Greenfield. fitdocs.ai proves the parsing approach (`garmin-fit-sdk`, message
types, channel extraction — see `docs/reference/fitdocs-ai-reference.md`) but
computes only a minimal scalar set locally and never parses strength sets.

## Desired Outcome

A pure library layer: given a `.fit` file, return a normalized **activity
model** — session summary, laps (projected onto sample indices), per-sample
channel arrays, strength sets (from `set_mesgs`), devices, detected
sport/modality — plus **locally computed derived metrics** at fitdocs.ai
parity: moving/elapsed time, distance, avg/max HR, avg/max power, normalized
power, intensity factor, variability index, efficiency factor, decoupling %,
avg pace, cadence, elevation gain/loss, min/max altitude, temperature
aggregates, time-in-zone (HR/power/pace, given athlete zones), calories
passthrough, TRIMP, power TSS.

## Approach

Port fitdocs.ai's ingestion pipeline shape (decode flags, channel arrays with
`None` for absent, lap index projection, sport map) into a standalone module;
implement the Intervals-imported metrics locally from the documented formulas;
add `set_mesgs`/`exercise_title` parsing for weight training.

## Scope

- **In**: `.fit` decode; activity model dataclasses; sport/modality detection;
  strength sets; derived-metric computation (pure functions over the model);
  fixture-based golden tests.
- **Out**: file discovery/CLI, markdown rendering, charts, load-calculator
  interface, `.gpx`/`.tcx`, athlete profile storage (zones arrive as inputs).

## Boundary Candidates

- Decode/extraction vs. derived-metric computation (two submodules; metrics
  are pure functions over the model).
- Sport detection as an isolated map (device quirk churn lands here).

## Out of Boundary

- Anything user-facing (prompts, output paths, doc formatting).
- Zone *definitions* (athlete profile is owned by training-load; zone
  *math* given boundaries lives here).

## Upstream / Downstream

- **Upstream**: none (foundation).
- **Downstream**: workout-docs (renders the model), training-load
  (calculates from the model).

## Existing Spec Touchpoints

- **Extends**: none.
- **Adjacent**: the activity model schema is the contract both downstream
  specs consume — version it deliberately.

## Constraints

- Python 3.11+, `garmin-fit-sdk`; stdlib dataclasses for the model.
- Absent data is `None`, never fabricated; metrics missing inputs return `None`.
- Metric formulas must match `docs/reference/fitdocs-ai-reference.md` §2.
