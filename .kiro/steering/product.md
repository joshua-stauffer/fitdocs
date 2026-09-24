# Product Overview

**fitdocs** is an installable personal knowledge manager for fitness: it
consumes `.fit` files and writes one rich markdown document per workout.
It serves athletes who keep their life in a markdown PKM (Obsidian-style
wiki or similar) and want their training to live there too — owned locally,
readable as plain text, linkable like any other note — instead of locked
inside a vendor platform.

## Core Capabilities

1. **`.fit` → markdown, one-to-one.** Each activity becomes one workout
   document. The user gets the files into a target directory (Garmin exports,
   watch sync, etc.), or, from Phase 8 of the roadmap, a configured connector
   fetches them. fitdocs does the rest. When several files record the same
   session (a phone-side re-export and the device original, say), Phase 8
   makes them one document: a base file plus extras that add only the
   channels the base lacks, never a duplicate.
2. **Strong workout-level documents.** Per-sport views for running, cycling,
   and weight training modeled on fitdocs.ai's activity pages: summary
   metrics, laps/splits or sets/reps, and rich embedded charts — headlined by
   the power-vs-heart-rate hero graph. Full metric parity with fitdocs.ai.
3. **Pluggable training-load calculation.** A `LoadCalculator` interface with
   shipped implementations (first: the threshold engine — compute a load per
   available channel, select one). When a calculator needs data the activity
   doesn't have (thresholds, benchmarks, tested maxima), fitdocs prompts the
   user and completes the computation.
4. **PKM-native output.** Documents carry wiki-standard YAML frontmatter,
   `[[wikilinks]]`, and provenance back to the source `.fit` file, so they
   slot directly into a larger PKM (the reference integration is the
   joshua-stauffer/pkm wiki). Standalone use is equally supported.

## Target Use Cases

- A runner/cyclist/lifter who exports `.fit` files and wants a permanent,
  local, human-readable training log with computed training load.
- A PKM user who wants workouts as first-class wiki pages, linked to daily
  notes, gear, races, and people.
- A coach or self-coached athlete applying a load methodology to manage
  weekly training stress.

## Value Proposition

- **Your data, in plain text, forever** — no platform lock-in; documents are
  useful without fitdocs installed.
- **Training load as the killer feature** — most exporters stop at raw
  metrics; fitdocs computes load through a clean interface and invites the
  community to contribute calculators for other methodologies.
- **PKM-first design** — not an afterthought export, but pages built to link
  and compound inside a knowledge base.

## Explicitly deferred (first pass)

- Plan-level concepts *(lifted 2026-09-15 by Phase 7 of the roadmap: a
  training block is one document with dated bounds, a goal, a mesocycle
  length and a table of planned workouts, rendered from an athlete-owned plan
  source and reconciled against logged workouts — `training-blocks`,
  `plan-resolution`, `build-training-block`. Weekly aggregation views were
  deferred here too until 2026-09-09; Phase 6 lifted that one — the
  longitudinal fitness/fatigue page is `load-history`'s.)* Still deferred at
  the plan level: forecasting form from a plan, and macrocycles spanning
  several blocks.
- Automated `.fit` acquisition *(lifted 2026-09-23 by Phase 8 of the
  roadmap: connectors pull files the athlete does not yet have into the
  inbox (`connectors`, `intervals-connector`). A second file of an activity
  already held enriches its document instead of duplicating it
  (`activity-identity`, `channel-merge`, `running-dynamics`).)* Still
  deferred: pushing to platforms (Strava posts, intervals.icu uploads and
  planned workouts), pulling thresholds, wellness or plans, and device sync.

---
_Focus on patterns and purpose, not exhaustive feature lists_
