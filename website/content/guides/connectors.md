---
title: Connectors
description: Pull activities and wellness from intervals.icu, Garmin Connect, or a local folder with `fitdocs pull`, and connect the targets `fitdocs publish` sends posts to.
section: Guides
order: 2
---

# Connectors

Instead of dropping files into the [inbox](inbox.md) yourself, you can set up a **connector**. You configure it once, and `fitdocs pull` fetches whatever is new and delivers it into the inbox, where the next drain turns it into pages as if you’d dropped the files there yourself. Some connectors also take the posts you send with [`fitdocs publish`](publishing.md).

Fitdocs ships five connectors:

- **`intervals`** reads an [intervals.icu](https://intervals.icu) account with your own API key. When you publish, it writes a page’s post to that account.
- **`garmin`** reads a Garmin Connect account with a personal API key you create. It never writes to the account.
- **`folder`** reads a local directory, such as a folder another app exports to. It needs no account and makes no network request.
- **`relay`** connects to a fitdocs relay, a small server that holds a platform application on your behalf. It has nothing to pull.
- **`strava`** publishes posts through a relay that offers the Strava target. It’s Compatible with Strava, and it has nothing to pull.

Fitdocs can’t pull activities from Strava. If your device doesn’t sync to Garmin Connect, connect it to intervals.icu and let fitdocs read the original files from there. intervals.icu is free, community-supported, and syncs with most fitness platforms.

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

## What an intervals.icu pull fetches

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

## Wellness from intervals.icu

intervals.icu also keeps your daily wellness: resting heart rate, HRV, sleep, weight, and more. To pull it too, turn it on for the connector:

```toml
[connectors.intervals]
wellness = true
```

The first wellness pull reads back to 2010, or to `--since` if you give one. Each later pull re-checks the 30 days before the newest day it has already delivered. [Wellness and recovery](wellness.md) covers what fitdocs does with it.

If intervals.icu refuses a wellness request, the pull says so. Set `wellness = false` to stop asking. For Garmin wellness, use Garmin’s own data export or the [`garmin` connector](#wellness-from-garmin).

## Publishing to intervals.icu

The `intervals` connector is also a [publish target](publishing.md). A page opts in with the instance’s name in its `publish` key, and `fitdocs publish --yes` makes the matching activity on intervals.icu carry the page’s post: its name becomes the post’s title, and its description the post’s description.

```yaml
publish: intervals
```

Fitdocs looks for the activity in this order, and stops at the first step that finds one:

1. **The recorded link**, from an earlier publish of this page to this instance.
2. **The pull record**, which names the activities this instance delivered, by the digests of what it delivered.
3. **A listing around the page’s start.** An activity matches when it carries this page’s publication id, or when it starts within a second of the page and has a matching distance or, if either has no distance, a matching elapsed time. The sport isn’t compared.

If several activities match in one step, the answer is `ambiguous` and nothing changes. Fitdocs never picks one.

A listed activity that intervals.icu imported from Strava is never chosen. When nothing else matches and a Strava import starts within a second of the page, the answer is `not_updatable`.

When nothing matches, the answer is `not_found` and nothing is created, unless you turn uploads on:

```toml
[connectors.intervals]
publish_upload = true
```

With `publish_upload` on, fitdocs uploads the page’s base `.fit` file, unmodified, once, and then sets the name and description of the activity that results. The file must be in the archive and match the digest the page records, or the answer is `activity_file_missing` and nothing is uploaded. A Strava import that lists no start time is recognized only when it and the page were recorded in the same time zone, so with uploads on, a publish can create a second copy of it.

If the instance’s ledger can’t be read, fitdocs can’t rule out that the activity is already in its pull record. It still updates an activity it finds through the link or the listing. If it finds none, it uploads nothing and the answer is `local_record_unreadable`.

A post that lands records a direct link to the activity, labelled `intervals.icu`, in the page’s `published` region. The [connectors reference](https://github.com/joshua-stauffer/fitdocs/blob/main/docs/connectors.md#publishing) has what each request sends and the answer to each reply.

## Garmin

The `garmin` connector lists the activities of the Garmin Connect account a personal API key belongs to and fetches each one’s original `.fit` file, byte for byte as Garmin stored it. With `wellness = true` it adds daily wellness. It only reads. It never uploads to Garmin or changes anything there, and it has no publish side.

Fitdocs isn’t affiliated with or endorsed by Garmin. The name Garmin is used only descriptively, to say which service the connector reads, and fitdocs claims no permission from Garmin of any kind. What you may do with a key is set by [Garmin’s own terms](#garmins-terms).

### Set up Garmin

**1. Create a key.** In Garmin Connect, create a personal API key for the Connect Personal API. Garmin describes the key and its expiry in the [Personal API FAQ](https://developer.garmin.com/gc-developer-program/personal/personal-faq/). Garmin shows the key once, when you create it, so copy it then.

**2. Add the connector** to `fitdocs.toml`. An empty table is enough:

```toml
[connectors.garmin]
wellness = true   # optional; false by default
```

**3. Connect once:**

```sh
fitdocs connect garmin
```

Fitdocs asks for the key without echoing it, makes one request to exchange it for a token and check that Garmin accepts it, discards the token, and saves the key in the credentials store. If Garmin refuses the key, nothing is saved.

**4. Decide when your pages change**, if you already have some. Read [What the first sync does to an existing wiki](#what-the-first-sync-does-to-an-existing-wiki) first.

**5. Pull:**

```sh
fitdocs pull garmin
```

The key goes only to Garmin’s token call. Each pull exchanges it for a token that lasts about a day, holds that token in memory for the pull, and never stores it.

A key expires after the period you chose when you created it: 30, 90, 180, or 365 days. Garmin sends a reminder before then. To renew, create a new key on Garmin Connect and run `fitdocs connect garmin` again, which replaces the stored key. A key Garmin refuses, because it’s wrong, expired, or deleted, ends the pull with a message that says so.

### Garmin’s terms

You accept Garmin’s own terms when you create a key, and fitdocs isn’t a party to them. Garmin’s terms say a key is “personal to you”, and that it’s for “applications, services, or tools that you develop or operate for your own use”. Fitdocs runs on your machine, with your key, to read your own account, and the key goes only to Garmin. Fitdocs doesn’t claim that Garmin has approved this use and can’t tell you how Garmin reads those words, so read the terms you’re shown before you accept them.

The same terms say Garmin may throttle or restrict access and may revoke a key. If Garmin refuses a listing or a download, the pull stops, says that Garmin refused the request, and doesn’t repeat it. Check the key’s status on Garmin Connect.

### What a first pull does

A pull with no earlier record and no `--since` takes your whole activity history, oldest first. Fitdocs waits one second between requests. When Garmin says it’s limiting a request after the token call, fitdocs waits for the time Garmin states, up to five minutes, or else 30 seconds to four minutes, before trying again. If that doesn’t clear it, the pull stops and says so, and the next pull resumes where this one stopped. A pull prints no progress while it runs, so a long wait looks like a pause.

A pull fetches at most 200 activities. When more remain, the report has one deferred entry that says how many, and the next plain `fitdocs pull` continues from there and fetches nothing already recorded. An account of 1,000 activities takes five pulls.

`fitdocs pull garmin --since YYYY-MM-DD` lists only the activities from the start of that local day, with the same pacing and limit. On an instance that has pulled before, a `--since` backfill continues only when you run it again with the same `--since`. A plain pull won’t finish it.

Wellness has no such limit. With `wellness = true`, the first pull covers the whole range: from the start of your history, or from `--since`, to today. A year of wellness takes about 27 requests, so twelve years is about 330 requests, or 6 to 8 minutes. If a wellness request fails, the next pull starts that range again.

### Wellness from Garmin

`wellness = true` adds Garmin’s daily summaries, sleep, heart rate variability, and weight to your wellness series under the source `garmin-personal`: resting, minimum, and maximum heart rate, steps, sleep and its stages, respiration, blood oxygen, stress, body battery, weight, and overnight heart rate variability. A metric Garmin has no value for stays absent. It’s never recorded as zero. See [Wellness and recovery](wellness.md).

### What the first sync does to an existing wiki

A Garmin original ranks first as a page’s main file under the default `[identity] precedence`. So the first `fitdocs sync` after a pull, on a wiki that already holds pages built from other copies of the same activities, like a phone app’s, makes the Garmin original the main file of each of those pages. Those pages re-render. Some may be [renamed](workout-pages.md#when-a-page-is-renamed), and some may change their time, when the other copy’s clock was shifted by hours. Regions you own are kept.

A wiki whose pages predate fitdocs 0.2 needs `fitdocs regen` before the first pull, or the Garmin file starts a second page.

You have two controls:

- **Run `fitdocs pull garmin` without `--sync`.** The files wait in the inbox until you run `fitdocs sync`, so you choose when the pages change.
- **Set `[identity] precedence` to keep the base you have.** For a wiki built from phone copies, this ranks them first:

    ```toml
    [identity]
    precedence = ["phone_copy", "original", "unknown"]
    ```

    On a page whose main file is a phone copy, the Garmin file then joins as an extra. A page whose main file is another original, like a Stryd file, is still ranked against the Garmin file, and the Garmin file can win. To keep that main file, list its `original:<manufacturer>` entry first. See [`[identity]`](../reference/configuration.md#identity).

### What the Garmin connector doesn’t do

- Activities that came from another app as a GPX or TCX upload have no `.fit` original. They’re skipped, and the report says why.
- An activity whose download holds several FIT files is skipped, and the report names how many it found.
- Women’s health, courses, and training aren’t pulled, and VO2max isn’t read.
- Accounts on Garmin’s China service aren’t supported.

### Moving from intervals.icu

If you pull Garmin activities through the `intervals` connector, stop it fetching Garmin’s copies once this one is connected, so each activity arrives once. `GARMIN_CONNECT` is the default value of its `sources` setting, so name only the sources you still want:

```toml
[connectors.intervals]
sources = ["WAHOO", "ZWIFT"]
```

`sources` can’t be empty, so if you want nothing else from that instance, delete its table.

## The folder connector

Point a `folder` connector at any directory, and each pull copies new `.fit` files from it into the inbox. It never moves, renames, or deletes anything in that directory.

```toml
[connectors.watch-exports]
connector = "folder"
path = "/Users/you/Documents/WatchExports"
```

The name in brackets is yours to choose (lowercase letters, digits, and hyphens). The folder can’t be your inbox, sit inside it, or contain it.

## Connecting to a relay

A relay is a small server that holds a platform application on your behalf, so the `fitdocs` command doesn’t carry it. Fitdocs talks to a relay with a relay token. A `relay` instance holds that token: you connect it once, and you can revoke it later. A relay has no activities or wellness, so `fitdocs pull` doesn’t contact it.

```toml
[connectors.relay]
url = "https://relay.example.com"
```

Leave `url` out and the instance uses `https://api.fitdocs.ai`, the maintainer’s relay. The address must be `https`. Plain `http` is accepted only for `localhost`, `127.0.0.1`, and `::1`, for testing a relay on your own machine. To use more than one relay, name each instance and set `connector = "relay"` in its table.

A relay token comes from the relay’s operator, or from registering with a relay that offers registration. With a token in hand:

```sh
fitdocs connect relay
```

Fitdocs asks for the token without echoing it and makes one request to check it. It stores the token only if the relay accepts it. To register instead, for a relay that offers it:

```sh
fitdocs connect relay --register --email you@example.com
```

Without `--email`, fitdocs asks for the address. It prints a code. Confirm the registration at the relay’s confirmation page only if it shows the same code, because that match is what stops someone else’s registration from being confirmed as yours. Fitdocs waits until the registration is confirmed, refused, or expired, then stores the token the relay issues. Press Ctrl-C to stop waiting, and nothing is stored.

`fitdocs disconnect relay` asks the relay to revoke the stored token, then removes the instance’s credentials file. If the relay can’t confirm, the file stays and the command exits `1`. `--local-only` removes the file without contacting the relay, and the token stays valid until the relay’s operator revokes it.

To run a relay yourself, see the [relay guide](https://github.com/joshua-stauffer/fitdocs/blob/main/docs/relay.md#self-hosting-guide) in the repository.

## Strava

The `strava` connector is Compatible with Strava. It never contacts Strava itself. A Strava instance talks to a fitdocs relay, and the relay holds the connection to your account and does the work on Strava. It pulls nothing. What it does is `fitdocs publish --yes`: the post on a workout page is written onto the matching activity on Strava, and the page links to that activity with a View on Strava link.

An instance needs a relay instance to talk to, and the relay behind it has to offer the Strava target, which depends on how its operator set it up. See [Connecting to a relay](#connecting-to-a-relay).

```toml
[connectors.relay]

[connectors.strava]
relay = "relay"
upload = false   # optional; this is the default
```

`relay` is the name of a configured `relay` instance, and that instance’s `url` must be the relay’s public address, because the connect page is served there. Connect the relay instance first, then this one:

```sh
fitdocs connect relay
fitdocs connect strava
```

`fitdocs connect strava` asks you for nothing. It prints an address on the relay, a code, and how long the attempt lasts, and opens the address in your browser, unless you pass `--no-browser`. Give consent on that page with its Connect with Strava control, but only if the page shows the same code, because that match is what stops someone else’s connection from being completed as yours. Fitdocs waits until the connection is complete, refused, or expired, then stores the connection token the relay issues. Press Ctrl-C to stop waiting, and nothing is stored.

A page opts in with the instance’s name in its [`publish` key](publishing.md#opt-a-page-in):

```yaml
publish: strava
```

For each post, the relay finds the page’s activity on Strava, by the same rule fitdocs uses to recognize one activity recorded twice, and sets the activity’s name to the post’s title and its description to the post’s description. Nothing else on the activity changes, and nothing on Strava is deleted. If more than one activity matches, the answer is `ambiguous` and nothing changes.

While `upload` is `false`, a publish that finds no matching activity answers `not_found`. While it’s `true`, fitdocs sends the page’s base `.fit` file, unmodified, and the relay creates the activity. A file over 16 MiB is `rejected`, and a file that isn’t in the archive is `activity_file_missing`, with no upload request in either case. A page that records neither an elapsed time nor a distance is `activity_facts_missing`, and a title over 255 characters or a description over 8,000 is `rejected`, each with no request.

A post that lands records a View on Strava link in the page’s `published` region, when the relay’s answer carries a usable one. Each publish and upload request is attempted once, whatever the answer.

`fitdocs disconnect strava` asks the relay to end the connection, then removes the instance’s credentials file. If the relay can’t confirm, the file stays and the command exits `1`. `--local-only` removes the file without contacting the relay, and the connection stays at the relay until the instance is connected and disconnected again, or access is revoked in Strava’s settings. Neither touches the relay instance’s own token.

[Privacy and the network](privacy-and-network.md#strava) says what each request sends, and the [connectors reference](https://github.com/joshua-stauffer/fitdocs/blob/main/docs/connectors.md#strava) has every answer.

## Credentials

Keys and tokens are never stored in your data root. They live in your user’s config folder, `~/.config/fitdocs/credentials/` by default (or under `$XDG_CONFIG_HOME`, or wherever `FITDOCS_CREDENTIALS_DIR` points). Fitdocs refuses a credentials folder inside the data root, so a key can’t end up in your wiki’s git history or a shared folder. Each instance’s file is readable only by you.

Don’t put a key in `fitdocs.toml`. Fitdocs refuses a setting in an instance’s table with the same name as that connector’s own credential: `api_key` on `intervals` and `garmin`, `token` on `relay` and `strava`. To use one without storing it, set an environment variable instead. For an instance named `intervals`, that’s `FITDOCS_CONNECTOR_INTERVALS_API_KEY`, and for one named `relay`, `FITDOCS_CONNECTOR_RELAY_TOKEN`. A variable that’s set wins over a stored value, except in `fitdocs disconnect`, which acts only on what’s stored.

`fitdocs disconnect NAME` forgets one instance’s stored credentials and removes nothing else. For an `intervals` or `garmin` instance it sends no request, so the key stays valid at the service until you delete it there or it expires.

## What lands in your inbox

Each instance delivers into its own subfolder of the inbox, like `inbox/intervals/`. Those files are fitdocs’s own copies: once the archive holds identical bytes, the next pull removes them. A connector never touches anything you or your own tools put in the inbox.

Each instance that pulls keeps a record of what it has delivered in `.fitdocs/connectors/<name>.toml`. That record, not the service’s listing, decides what’s new. Don’t edit it. Deleting it makes the next pull start over like a first pull, and fitdocs no longer cleans up the deliveries still waiting in the inbox.

## Running it on a schedule

Fitdocs doesn’t schedule anything itself. Run the pull from cron, launchd, or your agent’s daily routine, with `--no-prompt` so it never waits for an answer:

```sh
fitdocs pull --sync --no-prompt
```

## Turning a connector off

Delete its `[connectors.<name>]` table. There’s no other switch: an instance without a table is never contacted again. Your pages, archive, and stored key stay where they are.

Deleting the table doesn’t revoke a key or end a connection. To do that, run `fitdocs disconnect NAME` first, because it works only on a configured instance. Delete a `strava` table before or along with the `relay` table it names, because fitdocs refuses a `strava` instance whose relay instance isn’t configured.

The full rules, including every report row and exit code, are in the [connectors reference](https://github.com/joshua-stauffer/fitdocs/blob/main/docs/connectors.md).
