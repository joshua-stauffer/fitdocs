---
title: Pulling from intervals.icu
description: Connect an intervals.icu account, or a local folder, so `fitdocs pull` fetches new activities and wellness into the inbox.
section: Guides
order: 2
---

# Pulling from intervals.icu

Instead of dropping files into the [inbox](inbox.md) yourself, you can set up a **connector**. You configure it once, and `fitdocs pull` fetches whatever is new and delivers it into the inbox, where the next drain turns it into pages as if you’d dropped the files there yourself.

Fitdocs ships two connectors:

- **`intervals`** reads an [intervals.icu](https://intervals.icu) account with your own API key. It never writes to the account.
- **`folder`** reads a local directory, such as a folder another app exports to. It needs no account and makes no network request.

Fitdocs doesn’t read Garmin Connect or Strava directly. intervals.icu is free, community-supported, and syncs with most fitness platforms, so connect your devices there and let fitdocs read the original files from it.

## Set up intervals.icu

**1. Add the connector** to `fitdocs.toml` at the top of your data root. An empty table is enough:

```toml
# <data-root>/fitdocs.toml
[connectors.intervals]
```

**2. Create a key.** In intervals.icu, open Settings, then Developer Settings, and create a personal API key.

**3. Connect once:**

```sh
fitdocs connect intervals
```

Fitdocs asks for the key without echoing it, makes one read request to check it, and saves it in a credentials store outside your data root (see [Credentials](#credentials)). If intervals.icu refuses the key, nothing is saved. Create a new key and run `connect` again.

**4. If you already have pages, run `fitdocs regen` first.** Pages written before fitdocs 0.2 don’t yet carry what fitdocs needs to recognize a pulled file as a workout you already have. Without the regen, a pulled copy of an old run may not be recognized as that run.

**5. Pull:**

```sh
fitdocs pull --sync
```

`--sync` drains the inbox right after the pull, so new pages are written in the same run. Without it, the files wait in the inbox for your next `fitdocs sync`.

## What a pull fetches

The first pull lists the last 30 days. To go further back, give it a start date:

```sh
fitdocs pull intervals --since 2025-01-01
```

A long backfill can run into intervals.icu’s rate limits, so step `--since` back one season at a time. Fitdocs remembers what each run delivered, so a later run fetches only what the earlier ones didn’t. After the first pull, each pull starts 30 days before the newest activity it has already recorded (`lookback_days` changes that).

By default a pull keeps only the activities that reached intervals.icu from Garmin Connect, so other copies of the same workouts, like uploads from a phone app, aren’t fetched a second time. To pull from other platforms, list them:

```toml
[connectors.intervals]
sources = ["GARMIN_CONNECT", "COROS", "WAHOO"]
```

The names are intervals.icu’s own, in upper case: `GARMIN_CONNECT`, `COROS`, `POLAR`, `SUUNTO`, `WAHOO`, `ZWIFT`, `UPLOAD`, `STRAVA`, and others listed in the [connectors reference](https://github.com/joshua-stauffer/fitdocs/blob/main/docs/connectors.md#configuring).

Some activities can’t be fetched, and the pull says so and moves on. intervals.icu shares only a stub, with no file, for an activity that came from Strava. An activity whose original isn’t a FIT file (GPX or TCX), or that has no file at all, is skipped too. Each one is recorded, so it isn’t asked about again.

Use `--dry-run` to see what a pull would fetch without downloading or delivering anything.

## Wellness

intervals.icu also keeps your daily wellness: resting heart rate, HRV, sleep, weight, and more. To pull it too, turn it on for the connector:

```toml
[connectors.intervals]
wellness = true
```

The first wellness pull reads back to 2010, or to `--since` if you give one. Each later pull re-checks the 30 days before the newest day it has already delivered. [Wellness and recovery](wellness.md) covers what fitdocs does with it.

## The folder connector

Point a `folder` connector at any directory, and each pull copies new `.fit` files from it into the inbox. It never moves, renames, or deletes anything in that directory.

```toml
[connectors.watch-exports]
connector = "folder"
path = "/Users/you/Documents/WatchExports"
```

The name in brackets is yours to choose (lowercase letters, digits, and hyphens). The folder can’t be your inbox, sit inside it, or contain it.

## Credentials

Keys are never stored in your data root. They live in your user’s config folder, `~/.config/fitdocs/credentials/` by default (or under `$XDG_CONFIG_HOME`, or wherever `FITDOCS_CREDENTIALS_DIR` points). Fitdocs refuses a credentials folder inside the data root, so a key can’t end up in your wiki’s git history or a shared folder. Each key file is readable only by you.

`fitdocs.toml` can’t hold a key either. Fitdocs refuses a setting there with the same name as a connector’s key, like `api_key`. To use a key without storing it, set an environment variable instead. For an instance named `intervals`, that’s `FITDOCS_CONNECTOR_INTERVALS_API_KEY`. A variable that’s set always wins over a stored key.

## What lands in your inbox

Each instance delivers into its own subfolder of the inbox, like `inbox/intervals/`. Those files are fitdocs’s own copies: once the archive holds identical bytes, the next pull removes them. A connector never touches anything you or your own tools put in the inbox.

Each instance keeps a record of what it has delivered in `.fitdocs/connectors/<name>.toml`. That record, not the service’s listing, decides what’s new. Don’t edit it. Deleting it makes the next pull start over like a first pull, and fitdocs no longer cleans up the deliveries still waiting in the inbox.

## Running it on a schedule

Fitdocs doesn’t schedule anything itself. Run the pull from cron, launchd, or your agent’s daily routine, with `--no-prompt` so it never waits for an answer:

```sh
fitdocs pull --sync --no-prompt
```

## Turning a connector off

Delete its `[connectors.<name>]` table. There’s no other switch: an instance without a table is never contacted again. Your pages, archive, and stored key stay where they are.

The full rules, including every report row and exit code, are in the [connectors reference](https://github.com/joshua-stauffer/fitdocs/blob/main/docs/connectors.md).
