# Brief: workout-docs

## Problem

The product's visible value: a `.fit` file dropped in a directory becomes a
strong, readable workout document. Without this, parsed data has nowhere to
live; with a weak template, the tool is just another exporter.

## Current State

Greenfield; depends on fit-ingest's activity model. fitdocs.ai's activity
detail view (bike/run) defines the target structure and the power-vs-HR hero
graph (`docs/reference/fitdocs-ai-reference.md` §3); strength view has no
reference implementation and needs its own design (§4 gives a display model).

## Desired Outcome

`fitdocs sync` (name TBD in design) consumes new `.fit` files from a target
directory and writes, per activity, one markdown doc + SVG chart assets into
the data root. Per-sport views:

- **Run / ride**: hero summary (KeyStats-style fields), telemetry hero chart
  (power-vs-HR overlay with elevation backdrop, athlete-zone HR strip),
  splits table (device laps + 1 km re-slice), device/data-quality section.
- **Strength**: session summary + per-exercise sets table
  (`set | reps | load | rest`).

Docs carry pkm-compatible YAML frontmatter (`title`, `type: workout`, dates,
`sport`, key metrics, `sources:` → the archived `.fit`), degrade gracefully
outside a PKM, and are idempotent (same input → same output; re-runs don't
duplicate).

## Approach

Per-sport markdown templates over the activity model; hand-generated SVG
charts reproducing the MultiChart normalization/smoothing/colors; CLI +
data-root resolution mirroring pkm's contract; source `.fit` archived
(sha256-keyed) alongside output for provenance and dedup.

## Scope

- **In**: doc templates (run/ride/strength + generic fallback), SVG chart
  generation (hero chart, HR-zone strip; others as design decides), file
  naming/layout in the data root, CLI entry + config, packaging
  (`uv tool install`), idempotent sync, golden-file tests.
- **Out**: load calculation and its doc section content (a reserved
  placeholder section is defined here, filled by training-load); route map
  (v1 skip unless static SVG is trivial — no tile servers in markdown);
  cycle/block rollups.

## Boundary Candidates

- Template/render vs. chart generation vs. CLI/config — three seams.
- Chart generator takes plain series + style params (reusable beyond the
  hero graph).

## Out of Boundary

- Metric computation (fit-ingest); athlete profile & prompting (training-load).

## Upstream / Downstream

- **Upstream**: fit-ingest (activity model + metrics).
- **Downstream**: training-load fills the reserved load section; future
  cycle/block specs will link these docs.

## Existing Spec Touchpoints

- **Extends**: none.
- **Adjacent**: fit-ingest model contract; pkm `wiki-schema.md` frontmatter
  standard (compatible, not identical — workout docs define their own `type`).

## Constraints

- Markdown + SVG only; must render in Obsidian, GitHub, and plain viewers.
- Data-root contract: `--out` > `FITDOCS_DATA` > `.fitdocs/data-root`; loud
  failure; never write into the repo.
- Chart spec fidelity per `docs/reference/fitdocs-ai-reference.md` §3
  (band normalization [0.42, 0.92], elevation backdrop [0, 0.32], boxcar k=5,
  documented oklch palette) — adapted where print/static form demands.
