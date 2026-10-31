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
5. **Queryable by agents** *(Phase 10 of the roadmap, shipped 2026-10-08)*.
   A derived DuckDB index of every workout lets agents
   answer statistical questions with standard SQL through `fitdocs query`,
   instead of reading documents and doing the arithmetic themselves. It
   covers summaries, laps, sets, per-second streams, zone times, loads,
   mean-max curves, fitness and form, benchmarks and blocks. The index is a
   disposable cache; the documents stay the truth.
6. **Dashboards in the wiki** *(planned: Phase 11 of the roadmap, discovery
   2026-10-11)*.
   - **What a dashboard is.** A page under `dashboards/`, written by the
     athlete or their LLM assistant, with charts that fitdocs draws from the
     analytics index.
   - **How charts are declared.** Hidden directives in the page declare
     each chart's kind and SQL.
   - **Relative and frozen.** Relative charts refresh with the most recent
     data after every index refresh. Frozen charts are snapshots that always
     show the same thing.
   - **Who owns what.** fitdocs owns the charts, which are lightweight SVG
     behind ordinary image links. The athlete owns every word of prose
     around them.
7. **Wellness and recovery** *(planned: Phase 12 of the roadmap, discovery
   2026-10-12)*.
   - **Sources.** Daily wellness is resting HR, HRV, sleep, weight, SpO2,
     VO2max and steps. It arrives through the inbox like any file: an
     intervals.icu pull, a Garmin data export, an Apple Health export.
     fitdocs archives it and keeps one normalized daily series, with every
     value tagged by its source.
   - **What the athlete sees.** A recovery page puts each signal against the
     athlete's own baseline and normal range, beside fitness, fatigue and
     form. Each workout page shows the morning's numbers. The view is
     descriptive, never a verdict.
   - **What load gains.** Resting and max HR are derived automatically into
     the benchmark timeline. A hand-recorded value stays in force until
     newer evidence disagrees with it, and any takeover is announced.
8. **Publishing posts** *(planned: Phase 14 of the roadmap, discovery
   2026-10-31)*.
   - **What gets posted.** A workout's title and description go to the
     platforms where the athlete's training is seen: intervals.icu and
     Strava first.
   - **Where the text comes from.** By default it is composed from a
     per-target template, with values filled in from the page. An
     athlete-owned `post` region on the page overrides it. Numbers always
     come from the page's own computed values.
   - **When it posts.** A page posts only once it has opted in.
     `fitdocs publish` is a dry run unless told `--yes`.
   - **What comes back.** Every outcome is one of fitdocs's own codes.
     Nothing a platform's API returns is printed, logged or written. The
     page links to the posted activity.
   - **How it reaches the platforms.** intervals.icu is reached directly
     with the athlete's API key. Strava is reached through a self-hostable
     relay, run at fitdocs.ai, which holds one Strava application.

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
  deferred: pushing planned workouts, pulling thresholds or plans, and
  device sync. *(Pushing posts was deferred here too until 2026-10-31.
  Phase 14 plans it: capability 8 above.)*
  *(Pulling wellness was deferred here too until 2026-10-12. Phase 12
  lifted it: `wellness-pull` drives the reserved `pull-wellness`
  capability.)*

---
_Focus on patterns and purpose, not exhaustive feature lists_
