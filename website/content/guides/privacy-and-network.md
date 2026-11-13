---
title: Privacy and the network
description: What leaves your machine (map tiles, and any connector you set up), when, and how to turn it off.
section: Guides
order: 12
---

# Privacy and the network

After you install fitdocs, you can run it offline, including in sandboxed environments. 

Only map tiles and connectors use the network, and only when you use them.

## Map tiles

To draw the basemap under an outdoor route, fitdocs downloads the map tiles that cover it from a tile provider (the OpenStreetMap standard layer by default). A tile request is a standard web-map URL (`…/{zoom}/{x}/{y}.png`) sent with an identifying user agent:

```
fitdocs/<version> (+https://github.com/joshua-stauffer/fitdocs)
```

**What the provider learns:** roughly where you were active, at map-tile precision.
**What it never gets:** your GPS track, your times, your heart rate, your name, or any account details.

This happens only when a tile isn’t already cached, and only while `sync`, `pull --sync`, or `regen` is drawing a map. Every tile is cached in `<data-root>/.cache/tiles/`, so once a route’s tiles are cached, re-rendering it needs no network.

## Turning tiles off

```toml
# <data-root>/fitdocs.toml
[tiles]
enabled = false
```

With tiles turned off, maps are drawn only from tiles already in the cache. If a map needs a tile that isn’t cached, that page skips its Map section with a warning, everything else renders normally, and the run doesn’t fail.

## Choosing a different provider

```toml
[tiles]
name = "opentopomap"
url = "https://tile.opentopomap.org/{z}/{x}/{y}.png"
attribution = "Map data: © OpenStreetMap contributors, SRTM | Map style: © OpenTopoMap (CC-BY-SA)"
```

Each provider’s tiles are cached separately. The attribution text you set is printed on every map.

## Connectors

A [connector](connectors.md) contacts its service only while you run `fitdocs connect`, `fitdocs disconnect`, `fitdocs pull`, or `fitdocs publish --yes`, and only for an instance you configured. `fitdocs publish` without `--yes` and `fitdocs publish --targets` send nothing.

| Connector | Where its requests go | Commands that send them |
|---|---|---|
| `folder` | Nowhere; it makes no network request | None |
| `intervals` | intervals.icu | `connect`, `pull`, `publish --yes` |
| `garmin` | personal.connectapi.garmin.com | `connect`, `pull` |
| `relay` | The instance’s `url`, which is `https://api.fitdocs.ai` unless you set another | `connect`, `disconnect` |
| `strava` | The `url` of the `relay` instance it names | `connect`, `disconnect`, `publish --yes` |

Each request carries the same user agent as a tile request. Your key or token never appears in an address, and fitdocs doesn’t send it, or a request’s body, to an address a service redirects to.

### intervals.icu

`fitdocs connect` makes one read request to check your API key. `fitdocs pull` lists your activities and downloads their original files. With `wellness = true` it also reads your wellness records and the import settings that say which platform each value came from. `fitdocs pull --dry-run` sends the listing requests and downloads nothing.

`fitdocs publish --yes` is the one command that writes to your account. For a page that opts in, it sets the matching activity’s name and description to the post’s, and it may list your activities around the page’s start to find that activity. With `publish_upload = true`, when no activity matches, it also uploads the page’s main `.fit` file, with a random id fitdocs generates for the post.

`fitdocs disconnect` removes the stored key with no request, and the key stays valid at intervals.icu.

### Garmin

`fitdocs connect` sends your personal API key to Garmin once to check it. Each `fitdocs pull` exchanges the key for a short-lived token, kept only in memory, and its other requests carry that token. They read your activity list and activity files and, with `wellness = true`, your daily summaries, sleep, heart rate variability, and weight. Fitdocs changes nothing in your Garmin account.

`fitdocs disconnect` removes the stored key with no request, and the key stays valid at Garmin until you delete it or it expires.

### A relay

A relay is a small server that holds the developer registration a service like Strava requires.

- `fitdocs connect NAME` makes one request carrying the token you pasted, to check it.
- `fitdocs connect NAME --register`, for a relay that offers registration, sends the relay the email address you give, then checks back with it until registration finishes.
- `fitdocs disconnect NAME` makes one request carrying the stored token, to revoke it. With `--local-only` it sends nothing, and the token stays valid until the relay’s operator revokes it.

### Strava

The `strava` connector is “Compatible with Strava”. It sends its requests only to the relay instance it names, and the relay does the work on Strava.

- `fitdocs connect NAME` makes one request, carrying the relay instance’s token, to start the connection, then checks back with the relay until the connection finishes. It also opens the relay’s connect page in your browser, unless you pass `--no-browser`. From there, your browser talks to the relay and to Strava.
- `fitdocs publish --yes` sends one request for each new or changed post on a page that opts in. It carries the post’s title and description, a random id fitdocs generates for the post, the activity’s sport, its start time with the recorded clock offset, its elapsed time and distance where the page records them, and the instance’s connection token.
- With `upload = true`, when the relay finds no matching activity, a second request carries the same fields and the page’s main `.fit` file.
- `fitdocs disconnect NAME` makes one request carrying the stored connection token, to end the connection. With `--local-only` it sends nothing, and the connection stays at the relay until the instance is connected and disconnected again, or access is revoked in Strava’s settings.

The relay holds your connection to Strava, so read its privacy policy, linked from its Strava connect page. The default relay (https://api.fitdocs.ai) publishes its privacy policy at [https://api.fitdocs.ai/privacy](https://api.fitdocs.ai/privacy). What the relay software keeps, and when it deletes it, is in the [relay guide](https://github.com/joshua-stauffer/fitdocs/blob/main/docs/relay.md#what-the-relay-keeps-and-when-it-deletes-it).

### What a post carries

A post template can put any number from your analytics index in a post, such as your weekly load. Filling a post sends nothing; publishing sends it. The built-in template includes distance, time, pace or speed, average heart rate, average power, and elevation gain when the page records them, so read the preview from `fitdocs publish` before you add `--yes`. Your notes and the rest of the page’s text aren’t sent.

An upload sends the file as it is, and a `.fit` file can hold your GPS track, your heart rate, and details of your device. Uploads are off unless you turn them on.

### Turning connectors off

`[tiles] enabled = false` doesn’t affect connectors. To stop fitdocs contacting a service, delete that connector’s `[connectors.<name>]` table. A `strava` table needs the `relay` table it names, so delete them together if you’re done with both.

Deleting a table doesn’t revoke a relay token or end a Strava connection. To do that, run `fitdocs disconnect NAME` before you delete it, because the command works only on a configured instance. An intervals.icu or Garmin key stays valid until you delete it on that service.

Your keys and tokens are stored in your user’s config folder, never in your data root, so they don’t travel with your notes or end up in your wiki’s git history. See [Credentials](connectors.md#credentials).

## Everything else

- **No account or telemetry.** Using fitdocs needs no account, and it sends no telemetry and doesn’t check for updates. A connector uses the account or relay registration you set up for it.
- **No background process.** Nothing runs unless you run a command.
- **Your questions stay local.** `fitdocs query` refuses any SQL that tries to reach the network, and dashboard charts are drawn without one. The analytics index is a file on your own machine.
- **Your LLM is your choice.** fitdocs doesn’t call any model. If you point an LLM at your data, the privacy of that setup depends on the model and provider you choose, including whether the model runs on your own machine.
- **Plugins are your code.** A load calculator plugin runs as ordinary Python with your user permissions, and fitdocs doesn’t limit what it does on the network.
- **Sharing is your choice.** Nothing is published unless a page’s `publish` key names a target and you run `fitdocs publish --yes`. Your data root is a folder of files: back it up, sync it, or put it under git however you like.
