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

This happens only when a tile isn't already cached, and only while `sync`, `pull --sync`, or `regen` is drawing a map. Every tile is cached in `<data-root>/.cache/tiles/`, so once a route's tiles are cached, re-rendering it needs no network.

## Turning tiles off

```toml
# <data-root>/fitdocs.toml
[tiles]
enabled = false
```

With tiles turned off, maps are drawn only from tiles already in the cache. If a map needs a tile that isn't cached, that page skips its Map section with a warning, everything else renders normally, and the run doesn't fail.

## Choosing a different provider

```toml
[tiles]
name = "opentopomap"
url = "https://tile.opentopomap.org/{z}/{x}/{y}.png"
attribution = "Map data: © OpenStreetMap contributors, SRTM | Map style: © OpenTopoMap (CC-BY-SA)"
```

Each provider's tiles are cached separately. The attribution text you set is printed on every map.

## Connectors

If you set up the [intervals.icu connector](connectors.md), `fitdocs connect` and `fitdocs pull` send requests to intervals.icu while you run them. Each request carries the same user agent as a tile request, and your API key in a header. The key is sent only to intervals.icu and never appears in an address. The connector never writes to your account.

No other command contacts a connector, and the `folder` connector makes no network request. `[tiles] enabled = false` doesn't affect connectors. To stop fitdocs contacting a service, delete that connector's `[connectors.<name>]` table.

Your keys are stored in your user's config folder, never in your data root, so they don't travel with your notes or end up in your wiki's git history. See [Credentials](connectors.md#credentials).

## Everything else

- **No account or telemetry.** Fitdocs needs no account, sends no telemetry, and doesn't check for updates.
- **No background process.** Nothing runs unless you run a command.
- **Your questions stay local.** `fitdocs query` refuses any SQL that tries to reach the network, and dashboard charts are drawn without one. The analytics index is a file on your own machine.
- **Your LLM is your choice.** fitdocs doesn't call any model. If you point an LLM at your data, the privacy of that setup depends on the model and provider you choose, including whether the model runs on your own machine.
- **Sharing is your choice.** Fitdocs publishes nothing. Your data root is a folder of files: back it up, sync it, or put it under git however you like.
