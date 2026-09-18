# Configuration

Everything fitdocs reads to decide where it writes, what it fetches, and how
it computes — the data root, its resolution order, the one settings file
under it, and the network behavior that file controls.

## The data-root contract

Every command that describes or changes a tree (`sync`, `regen`, `load`,
`check`, `plan`, `history`, `derive-benchmarks`, and any future one) needs a
data root — the directory fitdocs writes documents, assets, the source
archive, and its own state into. Only a command that describes the
*installed tool itself*, rather than any tree (today: `fitdocs plugins`,
`fitdocs skill [NAME]`), needs no data root at all.

The data root is resolved by an explicit precedence, and by no other means —
there is **no current-working-directory fallback and no implicit default**:

1. The `--out PATH` flag.
2. The `FITDOCS_DATA` environment variable.
3. A `.fitdocs/data-root` pointer file, found by walking the current
   directory and its ancestors upward. The pointer file's first line names
   the real data root; a relative target resolves against the pointer
   file's own directory.

The first of these that is configured must resolve to an existing directory,
or resolution fails loudly: fitdocs never creates a data root, and a typo in
a path never silently redirects your workout documents into the wrong place.
An unresolvable or non-directory data root is a **configuration error, exit
code `2`**, with a message that names the specific source that failed (the
`--out` flag, the `FITDOCS_DATA` value, or the pointer file) followed by all
three configuration options, for example:

```
No output location is configured.

Configure the output location with one of:
  - the --out flag
  - the FITDOCS_DATA environment variable
  - a .fitdocs/data-root pointer file
```

Because there is no fallback to the current directory, **fitdocs never
writes into a code repository by default**: running `fitdocs sync` from
inside a source checkout that has not been explicitly pointed at a data root
fails loudly instead of writing generated documents into that checkout.

## The settings file: `<data-root>/fitdocs.toml`

A single user-owned file lives at `<data-root>/fitdocs.toml`. fitdocs only
ever *reads* it — it never creates, prompts for, or writes it. It carries six
tables today, each documented in full where noted:

| Table | Configures | Documented in |
|-------|------------|----------------|
| `[tiles]` | The basemap tile provider and the persistent offline opt-out | below |
| `[inbox]` | The standing inbox's location, stability check, and disposition | [`docs/inbox.md`](inbox.md) |
| `[plugins]` | Third-party training-load calculator discovery | below |
| `[load]` (and its sub-tables `[load.sufficiency]`, `[load.priority]`, `[load.flags]`) | The default calculator, benchmark staleness, and channel-sufficiency/priority/flagging behavior training-load computation reads | below |
| `[plans]` | Where `fitdocs plan` looks for plan sources | the [README's Training blocks section](../README.md#training-blocks) |
| `[history]` | The fitness/fatigue/form model constants and coverage threshold `fitdocs history` renders from | below |

Every table's keys default independently, so an absent file, an absent
table, or a partially filled table is never an error on its own — only a
malformed value inside a present table is (a non-boolean `enabled`, an
unparseable `url`, and so on), and it fails loudly with exit code `2` rather
than silently misdirecting behavior.

### `[tiles]`: the map-tile provider and the offline opt-out

Outdoor activities (runs, rides, and other workouts whose samples carry GPS
positions) get a **Map** section in their document: the route drawn over real
basemap tiles. Rendering that map is the *only* time fitdocs touches the
network — every other operation runs fully offline.

**What leaves your machine, and when.** To draw the basemap, fitdocs fetches
the map tiles that cover your route from the configured tile provider
(OpenStreetMap by default). A tile request is a standard slippy-map URL of
the form `.../{z}/{x}/{y}.png`, so it reveals your **approximate activity
location, at basemap-tile granularity**, to that provider — along with
fitdocs' descriptive user agent:

```
fitdocs/<version> (+https://github.com/joshua-stauffer/fitdocs)
```

No GPS coordinates, credentials, or personal data are ever sent — only the
tile-URL requests the provider needs to serve the basemap.

This happens **only on a cache miss**, and **only during `sync`/`regen`**
while a map is being rendered. Each tile is fetched at most once and then
cached (see below), so a warm cache — like every other fitdocs operation —
is fully offline.

**Turning tile requests off (the persistent opt-out).** To stop fitdocs from
ever making a tile request, set `enabled = false` under `[tiles]` in
`<data-root>/fitdocs.toml`. This is a persistent opt-out: it disables all
tile fetching permanently.

With it off, maps render **only from tiles already in the cache**. When a map
needs a tile that isn't cached, fitdocs omits that document's Map section,
emits a warning, and renders the rest of the document normally — the run
still succeeds. This is the same warn-and-skip behavior used when the
provider is unreachable; no document or run is ever failed because a map
couldn't be drawn.

**Choosing a provider.** The tile provider is configured in the `[tiles]`
table of `<data-root>/fitdocs.toml` — a user-owned file that fitdocs only
ever reads (it never creates or writes it). Every key is optional; omit the
file or the table entirely to accept the OpenStreetMap defaults.

| Key | Meaning |
|-----|---------|
| `enabled` | `true` / `false` — the opt-out above. Default `true`. |
| `name` | Cache slug for this provider (path-safe: `[a-z0-9][a-z0-9-]*`). Keys the on-disk cache, so switching providers never mixes basemaps. Default `"osm"`. |
| `url` | Tile-URL template; must contain the `{z}`, `{x}`, and `{y}` placeholders. Default is the OSM standard layer. |
| `attribution` | Attribution text rendered on every map image. Default `© OpenStreetMap contributors`. |

The default (OpenStreetMap standard layer), written out explicitly, with the
built-in OpenTopoMap alternative shown commented below:

```toml
# <data-root>/fitdocs.toml — user-owned; fitdocs only reads it.
[tiles]
enabled = true
name = "osm"
url = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
attribution = "© OpenStreetMap contributors"

# To use OpenTopoMap (topographic style) instead, replace the three lines
# above with:
#   name = "opentopomap"
#   url = "https://tile.opentopomap.org/{z}/{x}/{y}.png"
#   attribution = "Map data: © OpenStreetMap contributors, SRTM | Map style: © OpenTopoMap (CC-BY-SA)"
```

A malformed `[tiles]` table — a `url` missing a placeholder, a non-slug
`name`, or a non-boolean `enabled` — fails loudly (exit code 2) rather than
silently misdirecting tile traffic.

**Attribution.** The configured provider's `attribution` text is rendered
legibly on every map image — by default `© OpenStreetMap contributors`. When
you switch providers, set `attribution` to the credit that provider requires
(for example, the OpenTopoMap string shown above).

**Tile cache.** Fetched tiles are cached under the data root at:

```
<data-root>/.cache/tiles/<name>/<z>/<x>/<y>.png
```

where `<name>` is the provider's cache slug. The cache always lives under
your data root — never inside this repository or the installed package. It
is **append-only and never pruned**: fitdocs only ever adds tiles, never
deletes them. Deleting the cache is safe — the only effect is that its tiles
are re-fetched on the next render.

### `[plugins]`: third-party calculator discovery

fitdocs ships one built-in training-load methodology, `threshold`, and
discovers any other calculator as a plugin, from two channels: an installed
Python distribution advertising the `fitdocs.load_calculators` entry point,
or a local plugin file/directory named by `[plugins].path`.

| Key | Meaning | Default |
|-----|---------|---------|
| `enabled` | `false` disables both discovery channels (entry-point and local). | `true` |
| `path` | A local plugin file or directory; a relative path resolves against the data root. `null` means no local plugins are discovered. | `null` (unset) |

Path existence is never checked at configuration time — a missing path is a
plugin load *error* (a warning, never a run failure), not a configuration
error. See [`docs/plugins.md`](plugins.md) for the full guide — the worked
packaged example, the public API surface, the compatibility policy, and
diagnosis of every rejection reason.

### `[load]`: calculator selection and training-load computation

| Key | Meaning | Default |
|-----|---------|---------|
| `default_calculator` | The registered calculator id to use when none is given explicitly (e.g. via `load`'s `--calculator`). | `null` (unset) |
| `benchmark_staleness_days` | How many days after which a recorded benchmark (threshold pace, LTHR, FTP) is considered stale. | `84` (12 weeks) |

Three further sub-tables configure calculator-internal behavior. An absent
sub-table is never an error — each key's default is the shipped module
constant. Within `[load]`, `[load.sufficiency]`, and `[load.flags]`, an
unknown key is silently ignored; `[load.priority]` is the one exception —
every key in it must be one of the four supported discipline names below,
or it is a **configuration error (exit code 2)** naming the offending key:

- **`[load.sufficiency]`** — the data-sufficiency gates a channel must clear
  before it contributes a result: `min_duration_s` (`60`), the shared
  `min_stream_coverage` (`0.80`), and three optional per-channel overrides,
  each meaning "use the shared minimum" when unset:
  `power_min_stream_coverage` (`null`), `hr_min_stream_coverage` (`null`),
  `pace_min_stream_coverage` (`null`). Unknown keys are ignored.
- **`[load.priority]`** — the per-discipline channel try-order (a list of
  `"power"` / `"heart_rate"` / `"pace"`), one key per lowercase sport name
  — `run`, `ride`, `walk`, or `hike`, and no other key. The shipped
  defaults: `run = ["pace", "power", "heart_rate"]`,
  `ride = ["power", "heart_rate"]`, `walk = ["heart_rate"]`,
  `hike = ["heart_rate"]`. A configured discipline overrides only its own
  entry; every other discipline keeps its default. A key that is not one of
  the four names above — including a recognized sport this calculator does
  not support, such as `swim` — fails loudly rather than being ignored.
- **`[load.flags]`** — seven QA detection thresholds: `cadence_lock_min_correlation`
  (`0.90`), `cadence_lock_max_delta_bpm` (`5.0`), `cadence_lock_window_s`
  (`120`), `cadence_lock_min_duration_s` (`300`),
  `cadence_lock_min_paired_coverage` (`0.50`),
  `divergence_max_intensity_delta` (`0.20`), and `aerobic_drift_max_pct`
  (`5.0`). Unknown keys are ignored.

See [`docs/plugins.md`](plugins.md) and
[`docs/contributing-calculators.md`](contributing-calculators.md) for how a
calculator reads its resolved `[load]` configuration.

### `[history]`: the fitness/fatigue model `fitdocs history` renders from

Every key defaults to `null` ("use the shipped seed"). Unconfigured fields
keep their seed and configured ones don't, so a partially configured set is
reported as configured rather than silently mixed with seeds — the rendered
page's own origin line names, field by field, which is which:

| Key | Meaning | Default (shipped seed) |
|-----|---------|--------------------------|
| `tau_fitness_days` | The fitness (CTL-equivalent) exponential time constant, in days. | `45.0` |
| `tau_fatigue_days` | The fatigue (ATL-equivalent) exponential time constant, in days. | `15.0` |
| `k_fitness` | The fitness-curve weighting coefficient. | `1.0` |
| `k_fatigue` | The fatigue-curve weighting coefficient. | `1.0` |
| `coverage_threshold` | The minimum share of a period's pages that must record a load before its curve is drawn rather than suppressed. | `0.80` |
| `methodology` | Which calculator's load values to read; falls back to `[load].default_calculator` when unset. | `null` (unset) |

## The athlete profile: `<data-root>/athlete.toml`

Alongside the settings file, an optional `<data-root>/athlete.toml` carries
the athlete inputs (thresholds, max heart rate, and similar) a calculator may
need. Unlike `fitdocs.toml`, this file is not read-only: fitdocs **writes**
it — atomically, and only user-provided, validated values — whenever the
load pass prompts you for a missing input and you answer, and whenever
`fitdocs derive-benchmarks` derives a new dated benchmark from a tagged
effort. It never overwrites a benchmark you already recorded yourself, and
every hand-added key or table it does not manage survives a rewrite
verbatim. An absent file is not an error — it degrades to no configured
inputs — and a malformed one is a configuration error (exit code 2).

## Related pages

- [`docs/inbox.md`](inbox.md) — the full inbox interface.
- [`docs/plugins.md`](plugins.md) — the plugin platform.
- [`docs/ownership-contract.md`](ownership-contract.md) — what fitdocs owns
  in your data root and what you own.
- [`docs/compatibility.md`](compatibility.md) — what a version number
  promises about this settings schema, among the other governed contracts.
