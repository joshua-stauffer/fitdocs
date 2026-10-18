---
title: Wellness and recovery
description: Bring in resting heart rate, HRV, sleep, and other daily signals from Apple Health, a Garmin export, or intervals.icu. See them on each workout page and on one recovery page.
section: Guides
order: 7
---

# Wellness and recovery

Your workouts are only half the story. How you slept, your resting heart rate, and your HRV say a lot about how a session went and how you’re absorbing your training. Fitdocs keeps a local record of those daily signals, shows the morning’s numbers on each workout page, and builds a recovery page that puts them next to your training load.

Fitdocs reports what was recorded and how it compares with your own recent normal. It never gives a readiness score, a verdict, or a training recommendation. What to make of the numbers is your call.

## Get your data in

Wellness arrives the same way workouts do: put the file in your [inbox](inbox.md) and run a plain `fitdocs sync`. Fitdocs recognizes a wellness file by what’s in it, not by its name. (`fitdocs sync <folder>` only processes `.fit` workout files, so wellness needs the inbox.)

### Apple Health

On your iPhone, open the Health app, tap your profile picture, choose **Export All Health Data**, then **Export**. Put the `export.zip` it gives you in the inbox (the `export.xml` inside it works too) and run `fitdocs sync`.

- Fitdocs keeps a compact extract of the wellness types it reads, not your whole export. Your profile, workouts, routes, clinical records, and ECGs are never kept.
- A newer export replaces the earlier one entirely, so export everything each time.
- A large export takes a while: about 10 to 20 seconds for each GB of `export.xml`. On a terminal you see the progress.
- Fitdocs doesn’t delete the original. If your inbox is an iCloud folder, move the export out yourself once it’s been archived, so it isn’t read again on every sync.

The Health export carries wellness only. Apple Watch workouts still come in as `.fit` files from an app like HealthFit.

### Garmin export

Request your data export from Garmin, unzip it yourself, and drop these JSON files into the inbox, with every date range you want:

- `UDSFile_*.json`: daily summaries, such as resting heart rate, steps, SpO2, stress, and Body Battery
- `*_sleepData.json`: sleep stages and respiration
- `MetricsMaxMetData_*.json`: running and cycling VO2max
- `*_userBioMetrics.json`: weight

Fitdocs doesn’t read the whole export ZIP, or Garmin’s monitoring and sleep `.fit` files. A `.fit` file that isn’t an activity is skipped with a warning and left in the inbox.

### intervals.icu

If you use the intervals.icu connector, set `wellness = true` on it and run `fitdocs pull --sync`. See [Pulling from intervals.icu](connectors.md).

## What fitdocs keeps

Two folders in your data root hold your wellness:

- **`wellness-archive/`** keeps every source file exactly as it arrived (for Apple Health, the extract). It’s never modified, and it’s the record everything else is rebuilt from, so back it up along with `fit-archive/`.
- **`wellness/`** holds the daily series: one CSV per year, like `wellness/2026.csv`, with every value from every source. Fitdocs rebuilds it from the archive whenever something changes, and overwrites any edits you make to it. Open it in a spreadsheet, or query it with SQL as `wellness_daily` in the [analytics index](analytics.md).

The signals include resting, lowest, and highest heart rate; HRV, both SDNN and rMSSD; sleep, with deep, light, REM, and awake time and sleeping heart rate; respiration, SpO2, weight, VO2max, steps, stress, and Body Battery; and subjective ratings like fatigue, mood, and soreness, when a source records them. SDNN and rMSSD are kept apart and never converted into each other, because they measure different things.

Each value belongs to a day, and a night’s sleep belongs to the morning you woke up. A value a source didn’t record stays missing. Fitdocs never fills it with a zero or carries an old value forward.

## When sources disagree

Your watch, your phone, and intervals.icu often record the same signal. Fitdocs keeps every source’s value and marks one per day and signal as the one to use. By default it prefers the device’s own export, then Apple Health, then intervals.icu (`garmin-export`, `apple-health`, `intervals-icu`). To choose differently, set the order, for everything or per signal:

```toml
# <data-root>/fitdocs.toml
[wellness]
precedence = ["apple-health", "garmin-export", "intervals-icu"]

[wellness.metric_precedence]
hrv_rmssd_ms = ["intervals-icu", "garmin-export"]
```

Fitdocs never mixes or averages sources. A change takes effect on your next sync or `fitdocs regen`.

## The Morning Of block

Every workout page gets a **Morning Of** block, just before Training Load. It shows resting heart rate, HRV, and sleep for the day of the workout, each next to its 7-day mean and the source it came from. Heart rate and HRV are also set against your normal range from the 60 days before, and sleep against its 60-day mean.

The block is refreshed on every `sync`, `pull --sync`, and `regen`. When none of those were recorded for that day, the page has no block. Fitdocs owns it and replaces any edits, so write your own thoughts in Notes.

## The recovery page

```sh
fitdocs recovery
```

This writes `recovery/recovery.md`, with its charts in `recovery/assets/`. The page covers the 90 days that end on the latest day in your wellness series:

- **Fitness, fatigue, and form**, computed the same way as the [history page](history.md)
- **HRV (SDNN), HRV (rMSSD), and resting heart rate**, each with a chart, its 7-day mean against your normal range, the stretches it ran above or below, and any change of source
- **Sleep**, with its 7-day mean and a table of the latest night’s stages
- **Other signals**, as small charts with no baseline
- **Coverage**, and the **method and references** behind every number

Each mean and normal range comes from a single source. Fitdocs never pools two sources into one baseline.

`fitdocs recovery` never runs automatically. Run it after a sync that brought in new wellness, or whenever you want a fresh page. It works offline, and it doesn’t change your workout pages or your wellness files. The whole page is generated, so there’s nothing on it for you to edit.

## Resting and max heart rate from your own data

`fitdocs derive-benchmarks` can now work out your resting heart rate from your wellness series and your max heart rate from your hardest runs and rides. See [Benchmarks and race tags](benchmarks.md#heart-rate-benchmarks).

## Taking an import back out

To withdraw a file you imported, delete its entry from `wellness-archive/`, remove its copy from the inbox, and run `fitdocs regen`.

The full details are in the repository: the [wellness guide](https://github.com/joshua-stauffer/fitdocs/blob/main/docs/wellness.md) (every supported field, the day rules, and the CSV format) and the [recovery guide](https://github.com/joshua-stauffer/fitdocs/blob/main/docs/recovery.md) (the method and its sources).
