# Brief: training-load

## Problem

Training load is the primary value fitdocs adds over raw exporters: a single
comparable number per workout that athletes plan weeks around. Methodologies
vary and are opinionated, so load must be pluggable — shipped implementations
plus a clean seam for community contributions. Load often needs athlete data
a `.fit` file doesn't carry (max HR, performance level, FTP); when it's
missing the tool must ask, not guess.

## Current State

Greenfield; depends on fit-ingest (activity model) and workout-docs (reserved
load section). The first methodology is fully extracted in
the reference writeup: zones, points/min, continuous and
interval formulas, lookup tables (CSV), validation ranges, workbook test
vectors. fitdocs.ai additionally gives TRIMP and power-TSS formulas — cheap
secondary calculators that exercise the interface's generality.

## Desired Outcome

- A `LoadCalculator` interface: declares id, display name, supported sports,
  and **required inputs** (athlete fields + activity fields); returns a typed
  result (points, methodology, inputs used, confidence/notes) or a typed
  "unsupported" / "missing inputs" outcome.
- **The withdrawn methodology's** implementation: zone determination from avg HR
  (% tested max) and/or avg pace vs HPL pace table, surfaced for user
  confirmation; interval workouts mapped from laps (N repeats × duration ×
  zone) with the workbook's discount/adjustment math; reproduces workbook
  numbers exactly (100 min Z3 = 1700; 3×20 Z6 = 2473.2).
- **Interactive completion**: generic prompt flow (driven by declared
  required inputs) collects missing fields at sync time; answers persist to
  an athlete profile file so users are asked once.
- Load results rendered into the workout doc's reserved section (points,
  methodology, zone, inputs).

## Approach

Interface + registry; athlete profile as a simple versioned file in the data
root; withdrawn-methodology tables shipped as package data (pending licensing sign-off);
TRIMP/TSS as secondary reference implementations if cheap. Calculators may
decline sports (the withdrawn methodology: running first; HR-variant for other endurance sports
is a design decision; strength unsupported).

## Scope

- **In**: interface + registry, athlete profile store, prompting flow, the
  withdrawn methodology's implementation + bundled tables, doc-section
  rendering, workbook-vector tests, contributor docs for new calculators.
- **Out**: weekly/cycle aggregation and guardrail analytics (deferred with
  the plan level); auto-updating athlete fitness from race results.

## Boundary Candidates

- Interface/registry vs. profile+prompting vs. the withdrawn methodology's implementation.
- Zone determination (fit data → withdrawn-methodology zone estimate) as its own module —
  it's the fuzzy part; keep the points math pure.

## Out of Boundary

- Doc template structure (owns only the content of the load section).
- Metric computation (consumes fit-ingest outputs).

## Upstream / Downstream

- **Upstream**: fit-ingest (model), workout-docs (placeholder contract,
  prompting surface in the CLI).
- **Downstream**: future cycle/block specs (weekly load rollups, Δ% guardrails
  from the withdrawn-methodology planner); community calculator contributions.

## Existing Spec Touchpoints

- **Extends**: workout-docs (fills its reserved section).
- **Adjacent**: pkm wiki pages may later query load from frontmatter — expose
  load in frontmatter, not just prose.

## Constraints

- **Licensing**: the withdrawn methodology's tables/name require the third
  party's permission before public redistribution
  (see the reference writeup, recorded in the purge's provenance record).
- The withdrawn methodology's math is authoritative from the spreadsheet, not the prose guide;
  invalid combinations (e.g. repeat counts outside the discount table) are
  surfaced to the user, not silently clamped.
- No fabricated numbers: missing inputs → prompt or `None`, never defaults.
