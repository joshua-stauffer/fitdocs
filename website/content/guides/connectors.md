---
title: Connectors
description: Pull activities and wellness from intervals.icu, Garmin Connect, or a local folder with `fitdocs pull`, and connect the targets `fitdocs publish` sends posts to.
section: Guides
order: 2
---

# Connectors

Instead of dropping files into the [inbox](inbox.md) yourself, you can set up a **connector**. You configure it once, and `fitdocs pull` fetches whatever is new into the inbox, ready for your next sync. Some connectors can also receive posts from [`fitdocs publish`](publishing.md).

Fitdocs ships five connectors:

- **`intervals`** reads an [intervals.icu](https://intervals.icu) account with your own API key. When you publish, it writes a page’s post to that account.
- **`garmin`** reads a Garmin Connect account with a personal API key you create. It never writes to the account.
- **`folder`** reads a local directory, such as a folder another app exports to. It needs no account and makes no network request.
- **`relay`** connects to a fitdocs relay, a small server between fitdocs and services such as Strava. It has nothing to pull.
- **`strava`** publishes your posts to Strava through a relay. It has nothing to pull.

Fitdocs can’t pull activities from Strava. If your device doesn’t sync to Garmin Connect, sync it to intervals.icu, which works with most fitness platforms, and pull from there.

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

Paste the key when asked; it isn’t shown as you type. Fitdocs checks it and saves it outside your data root (see [Credentials](#credentials)).

**4. If you have pages from before fitdocs 0.2, run `fitdocs regen` first**, so fitdocs recognizes pulled copies of workouts you already have.

**5. Pull:**

```sh
fitdocs pull --sync
```

`--sync` drains the inbox right after the pull, so new pages are written in the same run. Without it, the files wait in the inbox for your next `fitdocs sync`.

## What an intervals.icu pull fetches

The first pull lists the last 30 days. To go further back, give it a start date:

```sh
fitdocs pull intervals --since 2025-01-01
```

For a long history, step `--since` back a season at a time. Each later pull fetches only what’s new.

By default a pull keeps only the activities that reached intervals.icu from Garmin Connect, so other copies of the same workouts, like uploads from a phone app, aren’t fetched a second time. To pull from other platforms, list them:

```toml
[connectors.intervals]
sources = ["GARMIN_CONNECT", "COROS", "WAHOO"]
```

The names are intervals.icu’s own, in upper case, such as `GARMIN_CONNECT`, `COROS`, `POLAR`, `SUUNTO`, `WAHOO`, and `ZWIFT`. The [connectors reference](https://github.com/joshua-stauffer/fitdocs/blob/main/docs/connectors.md#configuring) lists them all.

Activities that reached intervals.icu from Strava, or that have no `.fit` original, can’t be fetched and are skipped.

Use `--dry-run` to see what a pull would fetch without downloading or delivering anything.

## Wellness from intervals.icu

intervals.icu also keeps your daily wellness: resting heart rate, HRV, sleep, weight, and more. To pull it too, turn it on for the connector:

```toml
[connectors.intervals]
wellness = true
```

intervals.icu may refuse to share wellness that came from Garmin. For that, use the [`garmin` connector](#wellness-from-garmin) or Garmin’s own data export. [Wellness and recovery](wellness.md) covers what fitdocs does with your wellness.

## Publishing to intervals.icu

The `intervals` connector is also a [publish target](publishing.md). A page opts in with the instance’s name in its `publish` key, and `fitdocs publish --yes` sets the matching activity’s name and description to the page’s post.

```yaml
publish: intervals
```

When no activity matches, nothing is created, unless you turn uploads on:

```toml
[connectors.intervals]
publish_upload = true
```

Fitdocs then uploads the page’s main `.fit` file and sets the new activity’s name and description. With uploads on, a publish can occasionally duplicate an activity that intervals.icu imported from Strava.

## Garmin

The `garmin` connector fetches the original `.fit` file of each activity in your Garmin Connect account, and with `wellness = true`, your daily wellness.

### Set up Garmin

**1. Create a key.** Sign in to Garmin Connect on the web and open the [Personal API Key page](https://connect.garmin.com/app/settings/personalApiToken). Select **Create Key**, accept Garmin’s terms, choose when the key expires, and select **Create**. Garmin shows the key only once, so copy it now. Garmin’s [Personal API FAQ](https://developer.garmin.com/gc-developer-program/personal/personal-faq/) has more about the key.

**2. Add the connector** to `fitdocs.toml`. An empty table is enough:

```toml
[connectors.garmin]
wellness = true   # optional; false by default
```

**3. Connect once:**

```sh
fitdocs connect garmin
```

Paste the key when asked. Fitdocs checks it with Garmin and saves it in the [credentials store](#credentials).

**4. Decide when your pages change**, if you already have some. Read [What the first sync does to an existing wiki](#what-the-first-sync-does-to-an-existing-wiki) first.

**5. Pull:**

```sh
fitdocs pull garmin
```

When the key expires, create a new one and run `fitdocs connect garmin` again.

### What a first pull does

A first pull fetches your whole activity history, oldest first. It can take a while, and it prints no progress as it runs.

A pull fetches at most 200 activities, so for a long history, run `fitdocs pull` again, or have your agent run it, until everything is in.

`fitdocs pull garmin --since YYYY-MM-DD` starts from that day instead. To continue a `--since` backfill, run the same command again; a plain `fitdocs pull` won’t continue it.

Wellness isn’t limited per pull. The first pull with `wellness = true` fetches all of it, which can take several minutes for a long history.

### Wellness from Garmin

`wellness = true` adds these daily metrics to your wellness series, under the source `garmin-personal`: resting, minimum, and maximum heart rate, steps, sleep and its stages, respiration, blood oxygen, stress, body battery, weight, and overnight heart rate variability. See [Wellness and recovery](wellness.md).

### What the first sync does to an existing wiki

If your wiki already has pages built from other copies of the same activities, like a phone app’s, the first `fitdocs sync` after a Garmin pull rebuilds those pages from the Garmin originals. Some may be [renamed](workout-pages.md#when-a-page-is-renamed) or change their start time. Regions you own are kept.

A wiki whose pages predate fitdocs 0.2 needs `fitdocs regen` before the first pull, or the Garmin file starts a second page.

You have two controls:

- **Run `fitdocs pull garmin` without `--sync`.** The files wait in the inbox until you run `fitdocs sync`, so you choose when the pages change.
- **Set `[identity] precedence` to keep the main files you have.** For a wiki built from phone copies, this keeps them as the main files:

    ```toml
    [identity]
    precedence = ["phone_copy", "original", "unknown"]
    ```

    To keep another device’s originals, like a Stryd’s, list its `original:<manufacturer>` entry first. See [`[identity]`](../reference/configuration.md#identity).

### What the Garmin connector doesn’t do

Women’s health, courses, training, and VO2max aren’t pulled, and accounts on Garmin’s China service aren’t supported.

### Moving from intervals.icu

If you pull Garmin activities through the `intervals` connector, stop it fetching Garmin’s copies once this one is connected, so each activity arrives once. `GARMIN_CONNECT` is the default value of its `sources` setting, so name only the sources you still want:

```toml
[connectors.intervals]
sources = ["WAHOO", "ZWIFT"]
```

If you want nothing else from that instance, delete its table instead.

## The folder connector

Point a `folder` connector at any directory, and each pull copies new `.fit` files from it into the inbox. It never moves, renames, or deletes anything in that directory.

```toml
[connectors.watch-exports]
connector = "folder"
path = "/Users/you/Documents/WatchExports"
```

The name in brackets is yours to choose (lowercase letters, digits, and hyphens).

## Connecting to a relay

A relay is a small server that connects fitdocs to services such as Strava. You connect a `relay` instance once, with a token.

```toml
[connectors.relay]
url = "https://relay.example.com"
```

Leave `url` out to use `https://api.fitdocs.ai`, the maintainer’s relay. To use more than one relay, name each instance and set `connector = "relay"` in its table.

If the relay’s operator gave you a token, connect with it and paste the token when asked:

```sh
fitdocs connect relay
```

To register with a relay that offers registration instead:

```sh
fitdocs connect relay --register --email you@example.com
```

Fitdocs shows a code, and the relay emails you a confirmation link. Open it, check that the page shows the same code as your terminal, and confirm. Fitdocs then stores the relay’s token.

`fitdocs disconnect relay` revokes the token and forgets it. `--local-only` forgets it without contacting the relay, and the token stays valid until the relay’s operator revokes it.

To run a relay yourself, see the [relay guide](https://github.com/joshua-stauffer/fitdocs/blob/main/docs/relay.md#self-hosting-guide) in the repository.

## Strava

The `strava` connector publishes your posts to Strava through a fitdocs relay, which holds the connection to your Strava account. It doesn’t pull. When you run `fitdocs publish --yes`, each post is written onto the matching Strava activity, and the page links to it.

You need a `relay` instance whose relay offers Strava. See [Connecting to a relay](#connecting-to-a-relay).

```toml
[connectors.relay]

[connectors.strava]
relay = "relay"
upload = false   # optional; this is the default
```

`relay` names your `relay` instance. Connect it first, then this one:

```sh
fitdocs connect relay
fitdocs connect strava
```

When you run `fitdocs connect strava`, you’ll see a code, and the relay’s connect page opens in your browser (pass `--no-browser` to open it yourself). Check that the code on the page matches the one in your terminal, then select **Connect with Strava**. Fitdocs stores the connection once you’ve finished.

A page opts in with the instance’s name in its [`publish` key](publishing.md#opt-a-page-in):

```yaml
publish: strava
```

For each post, the relay finds the matching Strava activity and sets its name and description to the post’s title and description. If no activity matches, nothing is created, unless you set `upload = true`. Then fitdocs sends the page’s main `.fit` file, and the relay creates the activity.

`fitdocs disconnect strava` ends the connection and forgets it. `--local-only` forgets it without contacting the relay, and the connection stays until you revoke access in Strava’s settings.

[Privacy and the network](privacy-and-network.md#strava) says what each request sends.

## Credentials

Keys and tokens are stored outside your data root, in `~/.config/fitdocs/credentials/` by default (or under `$XDG_CONFIG_HOME`, or wherever `FITDOCS_CREDENTIALS_DIR` points), so they don’t end up in your wiki’s git history. Each instance’s file is readable only by you.

Don’t put a key in `fitdocs.toml`; fitdocs refuses it. To use a key without storing it, set an environment variable instead, such as `FITDOCS_CONNECTOR_INTERVALS_API_KEY` for an instance named `intervals`, or `FITDOCS_CONNECTOR_RELAY_TOKEN` for one named `relay`. A variable that’s set wins over a stored value, except in `fitdocs disconnect`.

`fitdocs disconnect NAME` forgets an instance’s stored credentials. An intervals.icu or Garmin key stays valid until you delete it on that service.

## What lands in your inbox

Each instance delivers into its own subfolder of the inbox, like `inbox/intervals/`, and a later pull clears out files that are already archived. A connector doesn’t touch anything else in the inbox.

Each instance keeps a record of what it has delivered in `.fitdocs/connectors/<name>.toml`. Don’t edit it. Deleting it makes the next pull start over like a first pull.

## Running it on a schedule

Fitdocs doesn’t schedule anything itself. Run the pull from cron, launchd, or your agent’s daily routine, with `--no-prompt` so it never waits for an answer:

```sh
fitdocs pull --sync --no-prompt
```

## Turning a connector off

Delete its `[connectors.<name>]` table. Your pages, archive, and stored key stay where they are.

Deleting the table doesn’t revoke a relay token or end a Strava connection, so run `fitdocs disconnect NAME` first. Delete a `strava` table along with the `relay` table it names.

The [connectors reference](https://github.com/joshua-stauffer/fitdocs/blob/main/docs/connectors.md) has the full rules.
