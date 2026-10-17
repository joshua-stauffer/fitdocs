---
title: Privacy and the network
description: Exactly what leaves your machine (only map tiles), when, and how to turn it off.
section: Guides
order: 8
---

# Privacy and the network

After you install fitdocs, it can be run entirely offline, which makes it simple to use in sandboxed environments. 

## The one exception: map tiles

To draw the basemap under an outdoor route, fitdocs downloads the map tiles that cover it from a tile provider (the OpenStreetMap standard layer by default). A tile request is a standard web-map URL (`…/{zoom}/{x}/{y}.png`) sent with an identifying user agent:

```
fitdocs/<version> (+https://github.com/joshua-stauffer/fitdocs)
```

**What the provider learns:** roughly where you were active, at map-tile precision.
**What it never gets:** your GPS track, your times, your heart rate, your name, or any account details.

This only happens when a tile **isn't already cached**, and only while `sync` or `regen` is drawing a map. Every tile is cached in `<data-root>/.cache/tiles/`, so once a route's tiles are cached, re-rendering it is fully offline.

## Turning it off

```toml
# <data-root>/fitdocs.toml
[tiles]
enabled = false
```

With tiles turned off, maps are drawn only from tiles already in the cache. If a map needs a tile that isn't cached, that page skips its Map section with a warning, and everything else renders normally. No run fails because a map couldn't be drawn.

## Choosing a different provider

```toml
[tiles]
name = "opentopomap"
url = "https://tile.opentopomap.org/{z}/{x}/{y}.png"
attribution = "Map data: © OpenStreetMap contributors, SRTM | Map style: © OpenTopoMap (CC-BY-SA)"
```

Each provider's tiles are cached separately. The attribution text you set is printed on every map.

## Everything else

- **No account, no telemetry, no update checks.** fitdocs doesn't phone home.
- **No background process.** Nothing runs unless you run a command.
- **Your LLM is your choice.** fitdocs doesn't call any model. If you point an LLM at your data, the privacy of that setup depends on the model and provider you choose, which could be a model running on your own machine.
- **Sharing is your choice.** Nothing is published anywhere. Your data root is a folder of files: back it up, sync it, or put it under git however you like.
