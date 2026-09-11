---
title: "Training Load History"
type: "training-history"
generator: "fitdocs"
history_version: 1
methodology: banister_1991
methodology_source: "configured"
constants_provenance: "seeds"
tau_fitness_days: 45.0000
tau_fatigue_days: 15.0000
k_fitness: 1.0000
k_fatigue: 1.0000
coverage_threshold: 0.8000
series_start: "2024-01-01"
series_end: "2024-01-17"
pages_read: 9
pages_with_load: 5
criterion_points: 2
---

<!-- fitdocs:generated: everything outside the notes/workout/load regions is replaced on regeneration -- see this directory's AGENTS.md -->

# Training Load History

## Training Load Chart

![Training Load History chart](assets/training-load-history-fitness.svg)

Races:
1. 2024-01-03 — Winter 10K — finished in 40:00 (10.00 km)
2. 2024-01-05 — Spring 5K — finished in 25:00 (5.00 km)
3. 2024-01-16 — no result recorded

## Model Constants

This page's curve was computed with fitdocs' shipped seed values: tau_fitness = 45.0 days, tau_fatigue = 15.0 days, k_fitness = 1.0, k_fatigue = 1.0.

Origin: fitdocs' shipped seed constants (Banister (1991) pp. 413-414 for the time constants; fitdocs' own equal-weighting choice for k1/k2 -- never fitted to any athlete).

Fitness and fatigue are reported on the recursion's own daily-average scale -- each accumulator multiplied by its weighting and by (1 - e^(-1/tau)) -- so the number is in the same per-day units as a single day's load no matter how long the archive has been running.

fitdocs' shipped seed constants are illustrative starting values from the primary literature and were never fitted to any athlete.

A period whose share of pages recording a load falls below 80.0% has its curve suppressed rather than drawn.

The fitness and fatigue accumulators start at zero, so the earliest weeks of the series understate them.

Values reported after a suppressed period understate fitness and fatigue by whatever load went unrecorded during it.

## Coverage

- 2023: 0 pages, 0 recording a load (100.0%); excluded: trimp_legacy: 1
- 2024: 7 pages, 5 recording a load (71.4%); excluded: trimp_legacy: 1
- all: 7 pages, 5 recording a load (71.4%); excluded: trimp_legacy: 2; skipped: 1

## Criterion-Performance Report

2 criterion points: 2 race, 0 test — pages carrying a valid effort tag of kind race or test together with an official time. Earliest 2024-01-03, latest 2024-01-05.

Excluded from the count: 2 tagged pages.
- 1: race or test tag recorded with no official time
- 1 with a malformed tag:
  - `workouts/2024-01-17.md`: effort_time_s must be a positive number, got 'DNF'

fitdocs draws no conclusion from this count.

## Weekly Table

| Week (Monday) | Total load | Sessions | Pages w/ load | Fitness | Fatigue | Form | Note |
|---|---|---|---|---|---|---|---|
| 2024-01-01 | 45.0 | 4 | 4/4 | 0.9 | 2.4 | -1.5 |  |
| 2024-01-08 | 0.0 | 0 | 0/0 | 0.8 | 1.5 | -0.7 |  |
| 2024-01-15 | 6.0 | 1 | 1/3 | — | — | — | suppressed — coverage below threshold |

## Skipped and Excluded

Skipped (date could not be read):
- `workouts/mystery-date.md` — document date could not be read

Excluded (recording another methodology):
- trimp_legacy: 2 pages
