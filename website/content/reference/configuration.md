---
title: Configuration
description: The data root, fitdocs.toml (settings, which fitdocs only reads), and athlete.toml (thresholds), key by key.
section: Reference
order: 2
---

# Configuration

fitdocs reads three things: **where your data root is**, **`fitdocs.toml`** (your settings), and **`athlete.toml`** (your thresholds). Every setting has a default, so all of them are optional.

## The data root

Resolved in this order, and no other way:

1. `--out PATH` on the command
2. the `FITDOCS_DATA` environment variable
3. a `.fitdocs/data-root` pointer file, found by searching up from the current directory. Its first line is the path; a relative path is resolved from the pointer file's own folder.

The first one that's set must point to an existing folder, or fitdocs stops with **exit code 2** and says which source failed. fitdocs never creates the data root and never falls back to the current directory.

Only `fitdocs plugins` and `fitdocs skill` work without a data root, because they describe the tool rather than your data.

## `fitdocs.toml`

Lives at `<data-root>/fitdocs.toml`. **You own this file. fitdocs only reads it** and never creates, rewrites, or asks about it. A missing file, table, or key just means "use the default". A value that's present but invalid is an error (exit 2), never silently ignored.

### `[inbox]`

| Key | Default | |
|---|---|---|
| `path` | `"inbox"` | Inbox folder. Relative paths resolve from the data root. |
| `settle_seconds` | `2` | Time between the two checks that a file has finished writing. `0` skips the wait. |
| `ignore` | `[]` | Extra glob patterns to skip. |
| `disposition` | `"leave"` | `"leave"` or `"move"`. There's no delete option. |
| `processed_dir` | unset | Where moved files go. Required when `disposition = "move"`. |

See [Getting your files in](../guides/inbox.md).

### `[tiles]`

| Key | Default | |
|---|---|---|
| `enabled` | `true` | `false` = never make a network request; only draw maps from cached tiles |
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
| `path` | `"plans"` | Folder for plan source files. fitdocs never creates it or writes to it. It must be outside the folders fitdocs owns. |

### `[plugins]`

| Key | Default | |
|---|---|---|
| `enabled` | `true` | `false` turns off all plugin discovery |
| `path` | unset | A local calculator file or folder. Relative paths resolve from the data root. |

**Local plugin files run as ordinary Python code with your user permissions. There's no sandbox.** Only point this at code you trust.

## `athlete.toml`

Lives at `<data-root>/athlete.toml` and holds your thresholds. Unlike `fitdocs.toml`, fitdocs **does write to this file**, but only values you gave it at a prompt or that `derive-benchmarks` derived from a tagged effort. It saves changes safely, never overwrites a benchmark you entered, and keeps any keys it doesn't manage exactly as they were.

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

You can add several entries per benchmark. Each activity is scored with the one that applied on its date. A missing file just means no thresholds yet. A malformed file is an error (exit 2) whose message tells you what to fix.

The full specification is [docs/configuration.md](https://github.com/joshua-stauffer/fitdocs/blob/main/docs/configuration.md) in the repository.
