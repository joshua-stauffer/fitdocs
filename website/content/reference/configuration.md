---
title: Configuration
description: The data root, fitdocs.toml (settings, which fitdocs only reads), athlete.toml (thresholds), and the files fitdocs keeps outside your data root.
section: Reference
order: 2
---

# Configuration

Fitdocs reads three things: where your data root is, `fitdocs.toml` (your settings), and `athlete.toml` (your thresholds). Every setting has a default, so all of them are optional. If you use a connector, its key is kept separately, outside the data root (see [Connector credentials](#connector-credentials)).

## The data root

Resolved in this order:

1. `--out PATH` on the command
2. the `FITDOCS_DATA` environment variable
3. a `.fitdocs/data-root` pointer file, found by searching up from the current directory. Its first line is the path; a relative path is resolved from the pointer file's own folder.

The first one that's set must point to an existing folder, or fitdocs stops with exit code 2 and says which source failed. fitdocs never creates the data root and never falls back to the current directory.

Only `fitdocs plugins`, `fitdocs skill`, and `fitdocs dashboard kinds` work without a data root, because they describe the tool rather than your data.

## `fitdocs.toml`

Lives at `<data-root>/fitdocs.toml`. You own this file. Fitdocs reads it but never creates, rewrites, or asks about it. A missing file, table, or key means "use the default". A value that's present but invalid is an error (exit 2).

### `[inbox]`

| Key | Default | |
|---|---|---|
| `path` | `"inbox"` | Inbox folder. Relative paths resolve from the data root. |
| `settle_seconds` | `2` | Time between the two checks that a file has finished writing, as a finite number of seconds. `0` skips the wait. |
| `ignore` | `[]` | Extra glob patterns to skip, such as an unrelated `.json`, `.zip`, or `.xml` file. |
| `disposition` | `"leave"` | `"leave"` or `"move"`. There's no delete option. |
| `processed_dir` | unset | Where moved files go. Required when `disposition = "move"`. |

See [Getting your files in](../guides/inbox.md).

### `[tiles]`

| Key | Default | |
|---|---|---|
| `enabled` | `true` | `false` = never request a tile; only draw maps from cached tiles. Connectors aren't affected. |
| `name` | `"osm"` | Cache folder name for this provider |
| `url` | OSM standard layer | Tile URL template containing `{z}`, `{x}`, `{y}` |
| `attribution` | `© OpenStreetMap contributors` | Printed on every map |

See [Privacy and the network](../guides/privacy-and-network.md).

### `[load]`

| Key | Default | |
|---|---|---|
| `default_calculator` | unset | Calculator id to use when none is given |
| `benchmark_staleness_days` | `84` | Age after which a benchmark is flagged as stale |

**`[load.priority]`**: the order channels are tried in, per sport. Only `run`, `ride`, `walk`, and `hike` are allowed as keys. Any other key is an error.

```toml
[load.priority]
run  = ["pace", "power", "heart_rate"]   # default
ride = ["power", "heart_rate"]           # default
walk = ["heart_rate"]                    # default
hike = ["heart_rate"]                    # default
```

**`[load.sufficiency]`**: how much data a channel needs before it counts.

| Key | Default |
|---|---|
| `min_duration_s` | `60` |
| `min_stream_coverage` | `0.80` |
| `power_min_stream_coverage`, `hr_min_stream_coverage`, `pace_min_stream_coverage` | unset (uses `min_stream_coverage`) |

**`[load.flags]`**: thresholds for the data-quality warnings.

| Key | Default |
|---|---|
| `cadence_lock_min_correlation` | `0.90` |
| `cadence_lock_max_delta_bpm` | `5.0` |
| `cadence_lock_window_s` | `120` |
| `cadence_lock_min_duration_s` | `300` |
| `cadence_lock_min_paired_coverage` | `0.50` |
| `divergence_max_intensity_delta` | `0.20` |
| `aerobic_drift_max_pct` | `5.0` |

`cadence_lock_max_delta_bpm`, `divergence_max_intensity_delta`, and `aerobic_drift_max_pct` must be finite numbers above zero.

### `[history]`

| Key | Default | |
|---|---|---|
| `tau_fitness_days` | `45.0` | Fitness time constant |
| `tau_fatigue_days` | `15.0` | Fatigue time constant |
| `k_fitness` | `1.0` | Fitness weight |
| `k_fatigue` | `1.0` | Fatigue weight |
| `coverage_threshold` | `0.80` | Share of a period's pages that need a load before the curve is drawn |
| `methodology` | unset | Which calculator's load to use (falls back to `[load].default_calculator`) |

### `[plans]`

| Key | Default | |
|---|---|---|
| `path` | `"plans"` | Folder for plan source files. fitdocs never creates it or writes to it. It must be outside the folders fitdocs owns, and can't be `dashboards/` or inside it. |

### `[plugins]`

| Key | Default | |
|---|---|---|
| `enabled` | `true` | `false` turns off all plugin discovery |
| `path` | unset | A local calculator file or folder. Relative paths resolve from the data root. |

**Local plugin files run as ordinary Python code with your user permissions. There's no sandbox.** Only point this at code you trust.

### `[identity]`

When several files record the same workout, they share one page, built from the best-ranked file. This sets the ranking.

| Key | Default | |
|---|---|---|
| `precedence` | `["original:garmin", "phone_copy", "original", "unknown"]` | Best first: a Garmin original, then a phone copy (such as HealthFit's), then any other original (such as a Stryd file), then anything else |

`original:<manufacturer>` ranks one manufacturer's originals separately. Kinds you leave out are added after yours. To let every original outrank a phone copy:

```toml
[identity]
precedence = ["original", "phone_copy", "unknown"]
```

`fitdocs regen` applies a change to every page, and may rename a page whose best file changes. See [Several files, one workout](../guides/workout-pages.md#several-files-one-workout).

### `[wellness]`

Which source's value to use when several record the same wellness signal on the same day. Every source's value is kept either way.

| Key | Default | |
|---|---|---|
| `precedence` | `[]` (built-in order: `garmin-export`, `apple-health`, `intervals-icu`) | Sources, best first. Sources you leave out follow in the built-in order. |
| `metric_precedence` | `{}` | A source list for one signal, such as `hrv_rmssd_ms`, replacing `precedence` for it |

```toml
[wellness]
precedence = ["apple-health", "garmin-export", "intervals-icu"]

[wellness.metric_precedence]
hrv_rmssd_ms = ["intervals-icu", "garmin-export"]
```

A change takes effect on the next sync or `fitdocs regen`. See [Wellness and recovery](../guides/wellness.md).

### `[connectors.<name>]`

One table per connector instance. `<name>` is yours to choose: lowercase letters, digits, and hyphens.

| Key | Default | |
|---|---|---|
| `connector` | the instance's name | Which connector to use: `intervals` or `folder` |
| `lookback_days` | `30` | How many days before the newest activity already recorded each pull starts listing (0 to 3650). Also how far back wellness is re-checked. |
| `wellness` | `false` | Also pull wellness. Only for a connector that has it (`intervals`). |
| `sources` | `["GARMIN_CONNECT"]` | (`intervals`) Which of intervals.icu's upload sources to keep |
| `path` | required | (`folder`) The folder to read. Relative paths resolve from the data root. It can't be, contain, or sit inside the inbox. |
| `settle_seconds` | `2` (the inbox's default) | (`folder`) How long a file must sit unchanged before it's read |

```toml
[connectors.intervals]
wellness = true

[connectors.watch-exports]
connector = "folder"
path = "/Users/you/Documents/WatchExports"
```

Fitdocs refuses a setting here with the same name as a connector's key, like `api_key`. See [Pulling from intervals.icu](../guides/connectors.md).

## `athlete.toml`

Lives at `<data-root>/athlete.toml` and holds your thresholds. Unlike `fitdocs.toml`, fitdocs writes to this file, but only values you gave it at a prompt or that `derive-benchmarks` derived: thresholds from a tagged effort, resting heart rate from your wellness series, and max heart rate from your runs and rides. It saves changes safely, never changes or deletes a benchmark you entered, and keeps every key it doesn't manage. Comments and formatting aren't kept when it writes the file.

```toml
[[benchmarks.athlete.max_hr_bpm]]
value = 190
measured_on = 2026-06-01

[[benchmarks.athlete.resting_hr_bpm]]
value = 48
measured_on = 2026-06-01

[[benchmarks.run.threshold_pace_s_per_km]]
value = 240
measured_on = 2026-09-01

[[benchmarks.run.lthr_bpm]]
value = 172
measured_on = 2026-09-01

[[benchmarks.ride.ftp_watts]]
value = 270
measured_on = 2026-08-15
```

| Benchmark | Scope | Unit |
|---|---|---|
| `max_hr_bpm`, `resting_hr_bpm` | `athlete` | bpm |
| `threshold_pace_s_per_km` | per sport | seconds per km |
| `lthr_bpm` | per sport | bpm |
| `ftp_watts` | per sport | watts |

You can add several entries per benchmark. Each activity is scored with the one that applied on its date. A missing file means no thresholds yet. A malformed file is an error (exit 2) whose message tells you what to fix, and so is a value of `nan` or `inf`.

## Outside the data root

Fitdocs keeps two things outside your data root, so they don't travel with your notes.

### Connector credentials

`fitdocs connect` stores keys outside the data root, in the first of these that's set:

1. `FITDOCS_CREDENTIALS_DIR` (an absolute path)
2. `$XDG_CONFIG_HOME/fitdocs/credentials`
3. `~/.config/fitdocs/credentials`

A credentials folder inside the data root is refused. An environment variable named `FITDOCS_CONNECTOR_<INSTANCE>_<FIELD>` supplies a value without storing it and always wins over a stored one, for example `FITDOCS_CONNECTOR_INTERVALS_API_KEY`.

### The analytics index location

The [analytics index](../guides/analytics.md) lives outside the data root too, under `FITDOCS_INDEX_DIR` if it's set, otherwise `$XDG_CACHE_HOME/fitdocs/index`, otherwise `~/.cache/fitdocs/index`. Each data root gets its own folder there. It's a cache: delete it any time, and `fitdocs index` builds it again.

The full specification is [docs/configuration.md](https://github.com/joshua-stauffer/fitdocs/blob/main/docs/configuration.md) in the repository.
