---
title: The analytics index
description: Ask SQL questions across your whole training history. One command builds a local DuckDB index from your pages, and `fitdocs query` reads it in a read-only sandbox.
section: Guides
order: 9
---

# The analytics index

Workout pages are good for reading one session at a time. They’re slow for questions across years, like how your weekly volume has trended, how much time you spend in each zone, or how your resting heart rate moved through a training block. Adding those up page by page is also where an LLM is most likely to get a number wrong.

The analytics index answers those questions. It’s a local [DuckDB](https://duckdb.org) database built from your workout pages, archived files, benchmarks, training blocks, and wellness series. You ask it questions in SQL with `fitdocs query`, or have your agent do it for you.

## Build it once

```sh
fitdocs index
```

That’s the only time you need to build it. After that, `sync`, `pull --sync`, `regen`, and `load` refresh it automatically once they’ve written your pages, updating only the pages that changed. A refresh never makes one of those commands fail.

The index is a disposable cache, not part of your data. It lives outside your data root, in your user’s cache folder (`~/.cache/fitdocs/index/` by default, or wherever `FITDOCS_INDEX_DIR` points), with one index for each data root. You can delete it any time: `fitdocs index` builds it again, and it only costs time. `fitdocs index` prints where the file is.

When an upgrade changes the index’s layout, fitdocs tells you, and `fitdocs index` rebuilds it. `fitdocs index --rebuild` builds a fresh one whenever you want.

## Ask a question

Pass one SQL statement:

```sh
fitdocs query "SELECT start_utc, sport, distance_m FROM activities ORDER BY start_utc DESC LIMIT 5"
```

Weekly distance by sport:

```sh
fitdocs query "
  SELECT date_trunc('week', start_utc)::DATE AS week, sport,
         round(sum(distance_m) / 1000, 1) AS km
  FROM activities
  GROUP BY ALL
  ORDER BY week DESC
  LIMIT 12"
```

Your resting heart rate over the last 90 days:

```sh
fitdocs query "
  SELECT day, value AS resting_hr_bpm, source
  FROM wellness_daily
  WHERE metric = 'resting_hr_bpm' AND canonical AND day >= current_date - 90
  ORDER BY day"
```

For longer queries, keep the SQL in a file and pass `--file weekly.sql`, or pipe it in with `fitdocs query -`.

On a terminal, results print as a table. Piped into another program, they come out as CSV. `--format json` gives you JSON. A query returns at most 1,000 rows unless you raise `--max-rows`, and stops after 30 seconds unless you raise `--timeout`. If the index is behind your pages, the query tells you to run `fitdocs index`.

## What’s in it

`fitdocs query --schema` lists every table and column, with units and a description of each. The main tables:

- **`activities`**: one row per workout, with its summary numbers (time, distance, pace, heart rate, power, cadence, elevation, TRIMP, TSS)
- **`pages`**: each workout page’s frontmatter, including its load and race tags
- **`laps`**, **`records`**, and **`strength_sets`**: every lap, every recorded sample, and every logged set
- **`zone_times`**: time in each heart-rate, power, and pace zone
- **`loads`** and **`quality_flags`**: every channel’s load and every data-quality check
- **`mean_max`**: the best power, speed, and heart rate each workout held for each duration
- **`daily_load`** and **`weekly_load`**: load totals, with fitness, fatigue, and form computed the same way as the [history page](history.md)
- **`benchmarks`** and **`benchmark_periods`**: every threshold in `athlete.toml`, and when each one applied
- **`blocks`**, **`mesocycles`**, and **`planned_workouts`**: your [training blocks](training-blocks.md), matched against what you logged
- **`wellness_daily`**: every [wellness](wellness.md) value from every source, with the one to use marked `canonical`

A missing value is `NULL`, never zero. Running cadence columns hold strides per minute, the FIT convention, so double them for steps per minute.

## With an LLM

Install the packaged **`fitdocs-analytics`** skill (see [Inside your wiki or vault](wiki-integration.md#agent-skills)). It teaches your agent to check the schema first, use the index for counts, totals, averages, and trends instead of reading pages one by one, show you the SQL it ran, and tell an empty result from a measured zero. Then ask in plain words: *“How has my weekly running volume changed since January?”*

To turn a query into a chart that stays up to date, see [Dashboards](dashboards.md).

The complete schema, column by column, is in the [analytics reference](https://github.com/joshua-stauffer/fitdocs/blob/main/docs/analytics.md).
