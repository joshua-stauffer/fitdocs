---
title: Your workout pages
description: A tour of a generated workout page, section by section, and which parts are yours to edit.
section: Guides
order: 3
---

# Your workout pages

Every activity becomes one markdown file in `workouts/`, named after its local start time, like `2026-09-16-run-1132.md`. That’s the time your device recorded, so a run on a trip keeps that trip’s date and time of day. Charts and maps are SVG files in `workouts/assets/`, linked as ordinary images, so they show up in any markdown viewer without plugins.

If the same workout reached you as several files, from your watch, your phone, and a Stryd pod, they all go on one page. See [Several files, one workout](#several-files-one-workout).

A run or ride page has these sections, top to bottom.

## Frontmatter

A YAML header with the key facts, so other tools, Obsidian's Dataview, or an LLM can search across hundreds of workouts without reading each page in full:

```yaml
---
title: Run 2026-09-16 11:32
type: workout
generator: fitdocs
doc_version: 11
date: '2026-09-16'
start_time: '2026-09-16T11:32:05+02:00'
sport: Run
modality: run
distance_km: 14.5
moving_time: '1:02:03'
avg_hr_bpm: 160
avg_power_w: 295
elevation_gain_m: 55.0
source_kind: original
source_elapsed_s: 3780.0
source_distance_m: 14512.3
source_device: 0d977e5a14df9a9a
sources:
- fit-archive/294a56e1….fit
load_value: 72.6
load_methodology: threshold
load_basis: pace
---
```

`sources` lists every archived `.fit` file of the workout, with the one the page is built from last. The `source_` keys describe that file. `source_device` is a short fingerprint of the recording device, never its serial number.

## Notes 

A section for storing your notes, workout assignment, reactions, or any other free text. Notes is never altered by fitdocs, even when you upgrade to a newer version and regenerate your workout pages.

## Summary

Distance, moving and elapsed time, pace or speed, elevation, and average and max heart rate.

## Map

For outdoor activities with GPS: your route drawn over real basemap tiles, with start and finish markers. (Drawing a map fetches tiles over the network. See [Privacy and the network](privacy-and-network.md).)

## Telemetry

A line of headline numbers (heart rate, power, cadence, speed, TRIMP, TSS), then the **hero chart**: power and heart rate on one shared timeline. It shows whether your heart rate tracked your effort, drifted, or dropped out. Once your zones are known, a heart-rate time-in-zone chart follows.

## Running Dynamics

On a run recorded with running dynamics, from the watch itself or from a pod like Stryd: ground contact time, vertical oscillation, step length, form power, leg spring stiffness, and the others your device records. A table gives each one’s average, its 10th to 90th percentile range, and how much of the run it covered, and a chart plots two of them over the run.

## Splits

Your device laps (manual button presses or workout steps) and automatic per-kilometre splits, each with distance, time, heart rate, and pace. The fastest and slowest splits are marked.

## Morning Of

If you bring in [wellness](wellness.md) data, this block shows that morning’s resting heart rate, HRV, and sleep, each against your own recent normal and labelled with its source. Fitdocs refreshes it on every sync and regen, so it’s not a place for your own writing. When there’s no wellness that day, in the week up to it, or in the 60 days before, the page has no block.

## Training load (filled in by fitdocs)

The load number, the method that produced it, and everything it was based on: which channel (pace, power, or heart rate) was picked and why, the inputs, how much of the activity the data covered, and why each other channel was or wasn't used. Data-quality warnings show up here too. See [Training load](training-load.md).

Fitdocs writes this section, but a regen keeps it, like your notes.

## Device and data quality

The recording device and its software, battery status, a coverage table showing what share of the activity had heart rate, power, cadence, speed, distance, altitude, and GPS data, and any decode errors. When a number looks wrong, check here first.

## Channel Sources

On a page built from several files, this section names each file, its role, and the channels it supplied. It’s how you tell which device a number came from.

## Strength sessions

Watches record a strength session's time and heart rate, not what you lifted. Strength pages add a **Workout** section that belongs to you, where you log exercises, sets, reps, and weights in whatever markdown you like. Like Notes, fitdocs never overwrites it.

## Editing rules

| Part of the page | Owner | On regen |
|---|---|---|
| Notes section | you | kept exactly |
| Workout section (strength) | you | kept exactly |
| Race tag keys in frontmatter (`effort`, …) | you | kept exactly |
| Training load section | fitdocs | kept (recomputed only when you ask) |
| Morning Of block | fitdocs | refreshed from your wellness series |
| Everything else | fitdocs | rebuilt from the archived `.fit` files |

Edit your sections between their `<!-- fitdocs:begin:… -->` and `<!-- fitdocs:end:… -->` markers. Don't add new markers: fitdocs won't rebuild a page that has a marker it doesn't recognize. The full rules are in the [ownership contract](https://github.com/joshua-stauffer/fitdocs/blob/main/docs/ownership-contract.md).

## Other page types

- **`history/training-load-history.md`**: one page showing fitness, fatigue, and form across your whole archive ([Training history](history.md)).
- **`recovery/recovery.md`**: your HRV, resting heart rate, and sleep next to your training load ([Wellness and recovery](wellness.md)).
- **`blocks/`**: a block page and planned-workout pages for each training plan ([Training blocks](training-blocks.md)).
- **`dashboards/`**: pages you write, with charts fitdocs draws and keeps current ([Dashboards](dashboards.md)).

## Several files, one workout

A run can reach you three times: the watch’s original file, a phone copy from an app like HealthFit, and a Stryd file. Fitdocs recognizes files of the same sport that started within a second of each other and covered about the same distance as one workout, and puts them on one page.

The page is built from the highest-ranked file, a Garmin original first by default. Any channel that file doesn’t record at all, like power or running dynamics from a Stryd pod, is filled in from the others, and Channel Sources says where each one came from. A channel the main file does record stays its own, gaps included. Change the ranking with `[identity] precedence` in [`fitdocs.toml`](../reference/configuration.md#identity).

When a file could belong to more than one page, fitdocs archives it without adding it to any page, and `fitdocs check` reports it. Fitdocs never merges two pages. If `check` reports a workout recorded on two pages, keep one, move anything worth keeping out of the other’s notes, delete it, and run `fitdocs regen`.

## When a page is renamed

A page can be renamed in two situations:

- **Its main file changes.** When a better-ranked file of the workout arrives, or you change the ranking, the page is rebuilt from the new main file, and renamed if that file gives a different name. This happens even if you chose the old name yourself.
- **A name frees up.** A page fitdocs had to write as `<name>-<8 characters>.md`, because `<name>.md` was taken, moves to `<name>.md` once that name is free.

Each rename prints a warning with the old and new names, and the page’s charts move with it. **Links to the old name aren’t updated**, in your notes or in a training plan’s overrides. Search for the old names the warnings print.
