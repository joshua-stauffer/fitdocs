---
title: Training load
description: How the built-in threshold calculator scores each workout, what it needs from you, and how it tells you when not to trust a number.
section: Guides
order: 4
---

# Training load

Training load is a single number for how much a workout took out of you. fitdocs computes it with a built-in calculator called **`threshold`**, and shows its work on every page.

## The scale

All of fitdocs' load numbers use the standard scale: **one hour at your threshold intensity = 100.** An easy 45-minute run might score 40. A hard two-hour ride might score 150. Because every sport uses the same scale, a week of running, cycling, and hiking adds up to one meaningful total.

## Three channels, one pick

For each activity, the `threshold` calculator computes a load from every channel that has enough data:

| Channel | Method | Based on your |
|---|---|---|
| **Power** | Normalized power → intensity factor → TSS (Coggan) | functional threshold power (FTP) |
| **Heart rate** | TRIMP → HRSS (Banister) | lactate-threshold heart rate, plus resting and max HR |
| **Pace** | Grade-adjusted pace → intensity | threshold pace |

Then it picks one using a per-sport priority order, and uses only that number for totals, history, and training blocks. The other channels' loads still appear on the workout page. Default orders:

| Sport | Priority |
|---|---|
| Run | pace → power → heart rate |
| Ride | power → heart rate |
| Walk | heart rate |
| Hike | heart rate |

If the first channel in line can't be computed (no power meter that day, or a threshold you haven't recorded), the reason is recorded and the next one is used.

Change the order in `fitdocs.toml`:

```toml
[load.priority]
run = ["power", "pace", "heart_rate"]   # trust the footpod over GPS pace
```

Custom load calculators can be added as [plugins](../extend/load-calculators.md).

## What it needs from you

Load is measured against *your* thresholds, which fitdocs stores in `athlete.toml` in your data root:

- **Resting and max heart rate**
- **Threshold pace**, **FTP**, and **threshold heart rate**, per sport

There are three ways to fill them in:

1. **Answer the prompts.** When `fitdocs sync` or `fitdocs load` needs a value it doesn't have, it asks, checks your answer, and saves it. If the activity is older than your answer, it also asks whether that answer should apply to earlier activities too.
2. **Let fitdocs work them out from your races and your own data.** Tag your races and hard efforts, and `fitdocs derive-benchmarks` turns them into dated thresholds. It also works out your resting heart rate from your [wellness](wellness.md) data and your max heart rate from your hardest runs and rides. See [Benchmarks and race tags](benchmarks.md).
3. **Write them by hand:**

```toml
# <data-root>/athlete.toml
[[benchmarks.athlete.max_hr_bpm]]
value = 190
measured_on = 2026-06-01

[[benchmarks.athlete.resting_hr_bpm]]
value = 48
measured_on = 2026-06-01

[[benchmarks.run.threshold_pace_s_per_km]]
value = 240            # 4:00 /km
measured_on = 2026-09-01

[[benchmarks.ride.ftp_watts]]
value = 270
measured_on = 2026-08-15
```

Every benchmark has a date, and each activity is scored with the value that applied *on that day*. A threshold you set this week doesn't change how your runs from 2022 are scored.

## Data Quality

If you’ve worn a fitness wearable for any amount of time, you’ve likely encountered bad data. Using poor quality training data to plan future workouts leads to confidently wrong decisions.
fitdocs evaluates the data quality of each channel, and adds a warning to the page of any flagged workout:

- **Cadence lock.** Wrist heart-rate sensors sometimes pick up your running cadence and report it as your heart rate. fitdocs checks whether "heart rate" is following cadence suspiciously closely.
- **Channels disagree.** If the picked channel and heart rate disagree sharply about how hard the session was, the page flags it.
- **Aerobic drift.** Heart rate rising steadily against steady output is flagged when it passes a threshold.
- **Stale threshold.** A benchmark older than 12 weeks (configurable) gets flagged. The load is still computed, but you'll know it rests on an old number.

## Running the load pass yourself

Load runs automatically at the end of every `sync`, `pull --sync`, and `regen`. You can also run it on its own:

```sh
fitdocs load                    # fill in pages that don't have a load yet
fitdocs load --recompute        # recompute pages that already have one
fitdocs load --no-prompt        # never ask; skip pages that would need an answer
fitdocs load --calculator ID    # use one specific calculator
```

Run `fitdocs load` after adding new benchmarks to fill in pages that were missing a number. A page that already has a load keeps it until you run `fitdocs load --recompute`.

A page built from [several files](workout-pages.md#several-files-one-workout) is scored from all of them together, so power from a Stryd pod counts even when the watch’s file is the main one. If more files of a workout arrive after its load was computed, the old number is kept until you recompute it.

## Tuning

Everything the calculator uses can be set in `fitdocs.toml`: how much data a channel needs before it counts, the priority order, the warning thresholds, and when a benchmark counts as stale. See [Configuration](https://github.com/joshua-stauffer/fitdocs/blob/main/docs/configuration.md#load-calculator-selection-and-training-load-computation).
