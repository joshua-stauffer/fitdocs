# Configuration

Everything fitdocs reads to decide where it writes, what it fetches, and how
it computes — the data root, its resolution order, the one settings file
under it, and the network behavior that file controls.

## The data-root contract

Every command that describes or changes a tree (`sync`, `regen`, `load`,
`check`, `plan`, `history`, `derive-benchmarks`, `connect`, `pull`, and any
future one) needs a data root — the directory fitdocs writes documents,
assets, the source archive, and its own state into. Only a command that describes the
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
ever *reads* it — it never creates, prompts for, or writes it. It carries nine
tables today, each documented in full where noted:

| Table | Configures | Documented in |
|-------|------------|----------------|
| `[tiles]` | The basemap tile provider and the persistent offline opt-out | below |
| `[inbox]` | The standing inbox's location, stability check, and disposition | [`docs/inbox.md`](inbox.md) |
| `[plugins]` | Third-party training-load calculator discovery | below |
| `[load]` (and its sub-tables `[load.sufficiency]`, `[load.priority]`, `[load.flags]`) | The default calculator, benchmark staleness, and channel-sufficiency/priority/flagging behavior training-load computation reads | below |
| `[plans]` | Where `fitdocs plan` looks for plan sources | the [README's Training blocks section](../README.md#training-blocks) |
| `[history]` | The fitness/fatigue/form model constants and coverage threshold `fitdocs history` renders from | below |
| `[wellness]` | Source precedence for the daily wellness series | below |
| `[identity]` | The source precedence that chooses each page's base file | below |
| `[connectors]` | Per-instance connector configuration for `fitdocs connect` and `fitdocs pull` | below |

Every table's keys default independently, so an absent file, an absent
table, or a partially filled table is never an error on its own — only a
malformed value inside a present table is (a non-boolean `enabled`, an
unparseable `url`, and so on), and it fails loudly with exit code `2` rather
than silently misdirecting behavior.

### `[tiles]`: the map-tile provider and the offline opt-out

Outdoor activities (runs, rides, and other workouts whose samples carry GPS
positions) get a **Map** section in their document: the route drawn over real
basemap tiles. Rendering that map, and the connector commands — `fitdocs
connect` (authenticating once against a configured source) and `fitdocs
pull` (fetching activities from it) — are the only times fitdocs touches the
network — every other operation runs fully offline. Map tiles are switched
off with `[tiles] enabled = false` (below); a connector only ever runs when
`fitdocs connect` or `fitdocs pull` is run against it, and removing its
`[connectors.<name>]` table removes it from both commands entirely.

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
while a map is being rendered. Each map tile is fetched at most once and
then cached (see below), so a warm tile cache is fully offline — like every
fitdocs operation except the connector commands, `fitdocs connect` and
`fitdocs pull`, which run only when invoked and are switched off simply by
not running them, or by removing the instance's `[connectors.<name>]`
table.

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

### `[identity]`: source precedence

When more than one file records the same workout, fitdocs keeps one page for
it and renders that page from one of its files, the page's **base**; the other
files are its **extras**. The `[identity]` table chooses which file is the
base. It has one key.

| Key | Meaning | Default |
|-----|---------|---------|
| `precedence` | A list of strings, best first. Each file ranks at the position of the entry that matches it; the file with the best rank is the page's base. | `["original:garmin", "phone_copy", "original", "unknown"]` |

**Vocabulary.** Each entry is one of:

- `original` — a file that records a `file_id` manufacturer other than
  `development`, for any manufacturer not named by an `original:<manufacturer>`
  entry;
- `phone_copy` — a file whose manufacturer is `development` (what a phone app
  such as HealthFit writes) and that records a well-formed session UUID;
- `unknown` — any other file: no recorded manufacturer, or `development`
  without a well-formed session UUID;
- `original:<manufacturer>` — an `original` file whose `file_id`
  manufacturer is exactly `<manufacturer>` (for example `original:garmin`),
  ranked at the position you give that entry rather than at the bare
  `original` entry's. `original:development` is not accepted, because
  `development` is the manufacturer that marks a phone copy; use `phone_copy`.

**Default.** The default is the maintainer decision of 2026-09-29: a Garmin
original, then the phone copy, then every other original (a Stryd file, for
example), then unknown files. Files that share a position are ordered by the
number of undocumented messages they carry (more first, a file with no count
last), then by creation time (newer first, a file with none last), then by
content hash.

**A partial list is completed.** A kind you leave out of a configured list is
appended after your entries, in the order `original`, `phone_copy`,
`unknown`. The default's `original:garmin` is not appended: a list that names
no `original:<manufacturer>` entry ranks every original alike.

**Validation.** An absent file, an absent `[identity]` table, or an absent
`precedence` key means the default. A present `[identity]` that is not valid
fails loudly with exit code `2` before anything is written: an `[identity]`
that is not a table, a `precedence` that is not a list of strings, an entry
listed twice, an entry that is neither one of the three kinds nor
`original:<manufacturer>`, `original:` with no manufacturer, and
`original:development`. The message names the settings file and the offending key or entry.
Keys other than `precedence` are ignored.

**Example.** To let every original outrank the phone copy, whichever
manufacturer wrote it:

```toml
[identity]
precedence = ["original", "phone_copy", "unknown"]
```

A change to `precedence` applies to every page on the next `fitdocs regen`,
which re-ranks the files of every page and may rename a page whose base
changes, and to the pages a `sync` adds files to; see the [ownership contract](ownership-contract.md#source-files-and-their-roles).

### `[wellness]`: source precedence for wellness

The daily wellness series retains every source's value. Precedence chooses
which present value is canonical for each day and metric; it does not erase
other sources or change their definitions.

| Key | Meaning | Default |
|-----|---------|---------|
| `precedence` | Source identifiers, best first. Omitted sources follow in the built-in order. | `[]` (built-in order: `garmin-export`, then `apple-health`, then `intervals-icu`) |
| `metric_precedence` | A table mapping metric identifiers to source lists. An entry replaces the general list for that metric; omitted sources still follow in built-in order. | `{}` (use the general list) |

```toml
[wellness]
precedence = ["garmin-export", "apple-health", "intervals-icu"]

[wellness.metric_precedence]
hrv_rmssd_ms = ["intervals-icu", "garmin-export"]
```

Only registered source identifiers (`intervals-icu`, `apple-health` and
`garmin-export`) and the [wellness metric identifiers](wellness.md#metrics) are
accepted.
A list must contain strings without duplicates. A non-table `[wellness]`, a
non-table `metric_precedence`, an unknown metric, an unknown source or a
malformed list is a settings error. Unknown top-level wellness keys are
ignored. Bare `fitdocs sync` and `fitdocs regen` validate these settings
before writing and exit `2` on an error; `fitdocs check` reports invalid
settings as a stale-series finding. Explicit-source `fitdocs sync SOURCE`
keeps its workout-only behavior. An absent file, table or key uses the
defaults; changing the settings rebuilds the series on the next drain or
`fitdocs regen`. See the [wellness guide](wellness.md) for canonical
selection, reading the series and the [day rule](wellness.md#wellness-day).

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

### `[connectors]`: pulling from a configured source

Each `[connectors.<name>]` table configures one connector instance for
`fitdocs connect` and `fitdocs pull`: which connector it uses (by default
the one named like the instance), how far back a pull lists (30 days by
default), and any keys the connector itself takes.
Credentials never belong in this file. See
[`docs/connectors.md`](connectors.md) for the full guide — configuring an
instance, the built-in folder and intervals.icu connectors, connecting, where credentials
live, pulling, delivery and removal, and what leaves your machine.

## The athlete profile: `<data-root>/athlete.toml`

Alongside the settings file, an optional `<data-root>/athlete.toml` carries
the athlete inputs (thresholds, max heart rate, and similar) a calculator may
need. Unlike `fitdocs.toml`, this file is not read-only: fitdocs writes it
atomically when you answer a load prompt with a validated value, and when
`fitdocs derive-benchmarks` updates dated benchmarks. The command first
derives threshold pace, lactate-threshold heart rate and functional
threshold power from tagged efforts, then resting and maximum heart rate
from wellness and workout evidence. Each stage writes at most once, only
when its derived entries change; `--dry-run` previews without writing.
Hand-recorded benchmarks and unknown keys, tables and values survive a
rewrite. Comments and formatting do not: the file is parsed and
re-serialized. An absent file means no configured inputs; a malformed one
is a configuration error (exit code 2). Numeric values must be finite: a
TOML `nan`, `inf` or `-inf` (for example `ftp_watts = nan`) is rejected the
same way, naming the key, rather than producing `nan` load values.

### Derived heart-rate benchmarks

Run `fitdocs derive-benchmarks --dry-run` to review both stages, then
`fitdocs derive-benchmarks` to write their entries. Heart-rate entries are
athlete-wide dated `resting_hr_bpm` and `max_hr_bpm` benchmarks. This stage
does not write the undated profile keys used by zones and the page's own
TRIMP figure, and requires no new configuration.

Resting evidence is the median of at least 14 daily values from one source
within the 28 days ending on the evidence date, counting only days after the
latest hand-recorded resting entry measured before that date. Sources are kept separate:
`[wellness]` precedence chooses the first source whose baseline is formed,
rather than mixing the per-day canonical values. A higher-ranked source
without enough values does not displace a formed lower-ranked baseline.

Maximum evidence comes from each workout's composed activity, using all
archive files listed by its page. Only run and ride sessions supply it; the
report lists every other session under `not_run_or_bike`. A session peak is its
highest 30-second sustained, time-weighted heart rate. The stage rejects
implausible samples and rapid changes, breaks stretches at gaps over 10
seconds, and excludes cadence-locked runs and cadence-locked spans in runs.
Evidence is worked out only on the dates of qualifying sessions: it takes the
median of the three highest session peaks within the 365 days ending on that
date, counting only sessions after the latest hand-recorded maximum measured
before it. Fewer than three such sessions gives no maximum evidence, and no
evidence is ever dated after the newest qualifying session. Both kinds round
to whole bpm, with halfway values rounded up.

The write-time rules compare rounded evidence with the value in force on
that date, whether hand-recorded or derived:

- Resting disagreement step: more than 3 bpm.
- Resting confirmation: 14 consecutive days.
- Maximum rise step: more than 2 bpm above the value in force.
- Maximum confirmation: 1 day (no waiting period).

A derived maximum never falls: evidence at or below the value in force plus
the step starts no entry, so a year without hard efforts does not lower it.
Record a lower maximum by hand.

Where no value is in force, the first evidence starts an entry immediately.
Otherwise, agreement within the step starts no entry. Resting confirmation
requires the same source throughout; a missing evidence day, an agreeing
day or a source change restarts it. A confirmed entry is dated on the first day of
the run and uses that day's value. A hand entry is challenged only by
evidence dated after its measurement date and formed from sessions or
wellness days after it. Evidence on or before that date, including days its
applies-from date covers, never starts an entry. Later evidence must pass
these rules before it takes over. Hand entries are never modified or deleted.

These are rules for writing entries, not changes to dated benchmark
selection. The most recent entry measured on or before a workout's date
wins; `applies_from` fills earlier dates only where no such entry exists.
Derived entries carry no `applies_from`. A hand entry's back-reach keeps
covering the days before its measurement date, because evidence dated there
starts nothing. It narrows only where a derived entry is dated before the
cover begins, since the most recent entry measured on or before a date wins.
The hand entry wins from its measurement date until a later entry supersedes
it. Existing load is rescored only when you explicitly run
`fitdocs load --recompute` after derivation. Derivation itself writes no
workout page and recomputes no load.

A new takeover is announced by the derivation run (including `--dry-run`)
with the kind, values, dates and evidence. The timeline entry's note also
names the superseded hand value and its date. A change to a hand entry's
back-reach, such as one widening because an earlier derived entry was
replaced, is reported once by the run that changes it.

`fitdocs check` lists a takeover only while that derived entry is the
latest entry of its kind; a later hand-recorded or derived entry ends
the listing.

To keep your own value, record a new hand entry dated after the takeover;
it wins from its date, and later derivation treats it by the same
write-time rules. To accept the derived value, leave it. The takeover
remains visible in the timeline after the `check` listing ends. Inspect
the derived entry's provenance for the wellness source and series file,
or the workout page, window and peaks used.

The heart-rate stage re-parses and composes archived workout files each
run, so a large archive can take several minutes. A terminal shows
progress. There is no per-session peak cache.

## Related pages

- [`docs/inbox.md`](inbox.md) — the full inbox interface.
- [`docs/connectors.md`](connectors.md) — configuring and running a
  connector.
- [`docs/plugins.md`](plugins.md) — the plugin platform.
- [`docs/ownership-contract.md`](ownership-contract.md) — what fitdocs owns
  in your data root and what you own.
- [`docs/compatibility.md`](compatibility.md) — what a version number
  promises about this settings schema, among the other governed contracts.
