---
title: Quickstart
description: From a folder of .fit files to your first workout pages in about five minutes.
section: Get started
order: 2
---

# Quickstart

This guide walks you through setting up your fitdocs training log. You need fitdocs [installed](install.md) and a few `.fit` files. Any recent Garmin, Coros, Wahoo, Stryd, or Apple Watch (exported through an app like HealthFit) workout will do.

## 1. Pick a data folder

fitdocs writes everything into one folder you choose, called the **data root**. Create it first, if it doesn’t already exist:

```sh
mkdir -p ~/fitdocs-data
```

## 2. Tell fitdocs where it is

Fitdocs needs to know where the data folder lives in order to write the wiki. You can pass it directly to a fitdocs command, export it in your shell profile, or add a .fitdocs/data-root file in your wiki.

```sh
# A. Pass it on each command
fitdocs sync ~/Downloads/fit-files --out ~/fitdocs-data

# B. Set it once for your shell session (or in your shell profile)
export FITDOCS_DATA=~/fitdocs-data

# C. Add a pointer file to a folder you work from, such as your notes folder.
#    fitdocs finds it by searching up from wherever you run the command.
mkdir -p ~/notes/.fitdocs
echo ~/fitdocs-data > ~/notes/.fitdocs/data-root
```

If you haven’t set a data root, fitdocs will raise an error and exit.

## 3. Run your first sync

```sh
fitdocs sync ~/Downloads/fit-files
```

This searches the folder (and its subfolders) for `.fit` files and then:

1. **archives** each source file, untouched, under `fit-archive/`
2. **writes** one markdown page per activity under `workouts/`, with its charts in `workouts/assets/`
3. **computes training load**, asking for anything it's missing, like your max heart rate or threshold pace (see [Training load](../guides/training-load.md))
4. ends with a summary of pages written, skipped, and failed

The source folder is only read. Running the same sync again is safe: files that are already archived are skipped. If the folder holds two files of the same workout, say from your watch and from HealthFit, they share one page.

Don't have your thresholds handy? Add `--no-prompt`. The pages still get written, just without a load number, and you can fill it in later with `fitdocs load`.

## 4. Open the result

```
~/fitdocs-data/
├── workouts/
│   ├── 2026-09-16-run-1132.md
│   ├── assets/…               charts and route maps (SVG)
│   └── AGENTS.md              the ownership rules, for people and LLMs
├── fit-archive/               your original .fit files, never modified
├── history/  blocks/          ready for the history page and training blocks
├── wellness/  wellness-archive/  recovery/
│                              ready for sleep, HRV, and resting heart rate
├── dashboards/                ready for the dashboard pages you write
├── .cache/                    map tiles (safe to delete)
└── athlete.toml               thresholds you entered (created on your first answer)
```

Open `workouts/` in anything that reads markdown. Obsidian, VS Code, iA Writer, or a GitHub repo will all show the charts, because they're ordinary image links. [Tour a workout page →](../guides/workout-pages.md)

## 5. Build the analytics index

```sh
fitdocs index
```

This builds a local database of everything in your training log, so you, or your LLM, can ask questions across all your workouts in SQL. You build it once, and every later sync keeps it current. See [The analytics index](../guides/analytics.md).

## 6. Check that everything is healthy

```sh
fitdocs check
```

`check` only reads. It reports anything in the data root that doesn't match what the installed fitdocs expects, and tells you how to fix it.

## Where to go next

- **Stop pointing at folders by hand:** set up the [inbox](../guides/inbox.md) so a plain `fitdocs sync` picks up new files, or [pull from intervals.icu](../guides/connectors.md) automatically.
- **Get load numbers you trust:** [Training load](../guides/training-load.md) and [Benchmarks and race tags](../guides/benchmarks.md).
- **Add sleep, HRV, and resting heart rate:** [Wellness and recovery](../guides/wellness.md).
- **Ask questions across years of training:** [The analytics index](../guides/analytics.md) and [Dashboards](../guides/dashboards.md).
- **Put it in your notes:** [Use fitdocs inside your wiki or vault](../guides/wiki-integration.md).
- **Plan and review your training with an LLM:** [Working with an LLM](../llm/index.md).
