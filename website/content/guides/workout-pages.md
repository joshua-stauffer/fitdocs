---
title: Your workout pages
description: A tour of a generated workout page, section by section, and which parts are yours to edit.
section: Guides
order: 2
---

# Your workout pages

Every activity becomes one markdown file in `workouts/`, named after its local start time, like `2026-09-16-run-1132.md`. Charts and maps are SVG files in `workouts/assets/`, linked as ordinary images, so they show up in any markdown viewer without plugins.

Here's what's in a run or ride page, top to bottom.

## Frontmatter

A YAML header with the key facts, so other tools, Obsidian's Dataview, or an LLM can search across hundreds of workouts without reading each page in full:

```yaml
---
title: Run 2026-09-16 11:32
type: workout
generator: fitdocs
doc_version: 5
date: '2026-09-16'
sport: Run
distance_km: 14.5
moving_time: '1:02:03'
avg_hr_bpm: 160
avg_power_w: 295
elevation_gain_m: 55.0
sources:
- fit-archive/294a56e1….fit
load_value: 72.6
load_methodology: threshold
load_basis: pace
---
```

`sources` points to the archived `.fit` files the page was built from.

## Notes 

A section for storing your notes, workout assignment, reactions, or any other free text. Notes is never altered by fitdocs. When you upgrade to a newer fitdocs version and regenerate your workout pages, the notes section is always stable.

## Summary

Distance, moving and elapsed time, pace or speed, elevation, and average and max heart rate.

## Map

For outdoor activities with GPS: your route drawn over real basemap tiles, with start and finish markers. (This is the only feature that uses the network. See [Privacy and the network](privacy-and-network.md).)

## Telemetry

A line of headline numbers (heart rate, power, cadence, speed, TRIMP, TSS), then the **hero chart**: power and heart rate on one shared timeline. It's the quickest way to see whether your heart rate tracked your effort, drifted, or dropped out. Once your zones are known, a heart-rate time-in-zone chart follows.

## Splits

Your device laps (manual button presses or workout steps) and automatic per-kilometre splits, each with distance, time, heart rate, and pace. The fastest and slowest splits are marked.

## Training load (filled in by fitdocs)

The load number, the method that produced it, and everything it was based on: which channel (pace, power, or heart rate) was picked and why, the inputs, how much of the activity the data covered, and why each other channel was or wasn't used. Data-quality warnings show up here too. See [Training load](training-load.md).

fitdocs writes this section, but a regen keeps it just like your notes, so a computed load isn't lost when pages are rebuilt.

## Device and data quality

The recording device and its software, battery status, a coverage table showing what share of the activity had heart rate, power, cadence, speed, distance, altitude, and GPS data, and any decode errors. When a number looks wrong, check here first.

## Strength sessions

Watches record a strength session's time and heart rate, not what you lifted. Strength pages add a **Workout** section that belongs to you, where you log exercises, sets, reps, and weights in whatever markdown you like. Like Notes, fitdocs never overwrites it.

## Editing rules, in one place

| Part of the page | Owner | On regen |
|---|---|---|
| Notes section | you | kept exactly |
| Workout section (strength) | you | kept exactly |
| Race tag keys in frontmatter (`effort`, …) | you | kept exactly |
| Training load section | fitdocs | kept (recomputed only when you ask) |
| Everything else | fitdocs | rebuilt from the archived `.fit` |

Edit your sections between their `<!-- fitdocs:begin:… -->` and `<!-- fitdocs:end:… -->` markers. Don't add new markers: fitdocs won't rebuild a page that has a marker it doesn't recognize. The full rules are in the [ownership contract](https://github.com/joshua-stauffer/fitdocs/blob/main/docs/ownership-contract.md).

## Other page types

- **`history/training-load-history.md`**: one page showing fitness, fatigue, and form across your whole archive ([Training history](history.md)).
- **`blocks/`**: a block page and planned-workout pages for each training plan ([Training blocks](training-blocks.md)).
