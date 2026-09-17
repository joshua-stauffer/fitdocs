# fitdocs

An installable personal knowledge manager for fitness. Consumes `.fit` files and
writes one markdown document per workout — rich, readable activity pages for
running, cycling, and weight training, with charts and computed training load.

Built to plug into a larger markdown PKM (wiki-style, Obsidian-compatible) as a
first-class path, while remaining feature-complete standalone.

## Status

Early discovery / spec phase. No installable package yet.

- `.kiro/steering/` — persistent project knowledge (product, tech, structure, roadmap)
- `.kiro/specs/` — feature specs (requirements → design → tasks → implementation)
- `docs/reference/` — research and methodology references backing the specs

## What it will do (first pass)

1. **Ingest** `.fit` files from a watched/target directory (user drops files in).
2. **Render** one markdown doc per activity — summary metrics, laps/splits or
   sets/reps, and embedded charts (e.g. the power-vs-heart-rate hero graph) —
   modeled on [fitdocs.ai](https://github.com/joshua-stauffer/fitdocs.ai)'s
   activity views.
3. **Compute training load** through a pluggable `LoadCalculator` interface.
   fitdocs ships one built-in methodology, `threshold`, and is otherwise the
   carrier: any other calculator is a plugin, installed or dropped in
   locally, and contributions are welcome. If an activity is missing data a
   calculator needs (e.g. max heart rate, a threshold pace), fitdocs prompts
   for it and completes the calculation; when the activity predates the
   prompt, fitdocs also asks whether the answer covers earlier activities
   too.
4. **Show training history.** `fitdocs history` renders one longitudinal
   page — a fitness/fatigue/form model and chart built from the training
   load already recorded on your workout documents — with no new data to
   enter and no `.fit` file read.
5. **Render training blocks.** `fitdocs plan` renders one block page per
   source in your plan directory, with one planned-workout page per row
   underneath it — rebuilt from your plan sources and reconciled against
   your logged workout pages; the same pass also runs at the end of
   `fitdocs sync` and `fitdocs regen` (see [Training blocks](#training-blocks)).

Organizing workouts into cycles/training blocks was deliberately deferred
through the first releases; Phase 7 of the roadmap (2026-09-15) adds training
blocks — a plan document rendered from an athlete-owned source and reconciled
against logged workouts — as the `training-blocks` (shipped: the plan
source, the two page types and `fitdocs plan`) and `plan-resolution`
(shipped: the reconciling pass chained after `fitdocs sync`/`fitdocs regen`
and run standalone through `fitdocs plan`) specs; only `build-training-block`
is not yet shipped.

## Route maps

Outdoor activities (runs, rides, and other workouts whose samples carry GPS
positions) get a **Map** section in their document: the route drawn over real
basemap tiles. Rendering that map is the *only* time fitdocs touches the
network — every other operation runs fully offline.

### What leaves your machine, and when

To draw the basemap, fitdocs fetches the map tiles that cover your route from
the configured tile provider (OpenStreetMap by default). A tile request is a
standard slippy-map URL of the form `.../{z}/{x}/{y}.png`, so it reveals your
**approximate activity location, at basemap-tile granularity**, to that
provider — along with fitdocs' descriptive user agent:

```
fitdocs/<version> (+https://github.com/joshua-stauffer/fitdocs)
```

No GPS coordinates, credentials, or personal data are ever sent — only the
tile-URL requests the provider needs to serve the basemap.

This happens **only on a cache miss**, and **only during `sync`/`regen`** while
a map is being rendered. Each tile is fetched at most once and then cached (see
below), so a warm cache — like every other fitdocs operation — is fully
offline.

### Turning tile requests off (the persistent opt-out)

To stop fitdocs from ever making a tile request, set `enabled = false` under
`[tiles]` in `<data-root>/fitdocs.toml`. This is a persistent opt-out: it
disables all tile fetching permanently.

With it off, maps render **only from tiles already in the cache**. When a map
needs a tile that isn't cached, fitdocs omits that document's Map section, emits
a warning, and renders the rest of the document normally — the run still
succeeds. This is the same warn-and-skip behavior used when the provider is
unreachable; no document or run is ever failed because a map couldn't be drawn.

### Choosing a provider

The tile provider is configured in the `[tiles]` table of
`<data-root>/fitdocs.toml` — a user-owned file that fitdocs only ever reads (it
never creates or writes it). Every key is optional; omit the file or the table
entirely to accept the OpenStreetMap defaults.

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

A malformed `[tiles]` table — a `url` missing a placeholder, a non-slug `name`,
or a non-boolean `enabled` — fails loudly (exit code 2) rather than silently
misdirecting tile traffic.

### Attribution

The configured provider's `attribution` text is rendered legibly on every map
image — by default `© OpenStreetMap contributors`. When you switch providers,
set `attribution` to the credit that provider requires (for example, the
OpenTopoMap string shown above).

### Tile cache

Fetched tiles are cached under the data root at:

```
<data-root>/.cache/tiles/<name>/<z>/<x>/<y>.png
```

where `<name>` is the provider's cache slug. The cache always lives under your
data root — never inside this repository or the installed package. It is
**append-only and never pruned**: fitdocs only ever adds tiles, never deletes
them. Deleting the cache is safe — the only effect is that its tiles are
re-fetched on the next render.

## Plugins

fitdocs ships one built-in training-load methodology, `threshold`, and
discovers any other calculator as a plugin, from two channels: an installed
Python distribution advertising the `fitdocs.load_calculators` entry point
(`pip install fitdocs-mycalc` is the whole install), or a local plugin
file/directory named by `[plugins].path` in `<data-root>/fitdocs.toml`. Run
`fitdocs plugins` at any time to see every registered calculator (id, version,
origin, modalities) and any plugin load errors — a plugin failure is always a
warning, never a run failure.

**Local plugin files are executed as ordinary code with your own user
privileges — fitdocs applies no sandboxing.** Only point `[plugins].path` at
code you trust.

See [`docs/plugins.md`](docs/plugins.md) for the full guide — the worked
packaged example, the local-file alternative, the public API surface, the
compatibility policy, and diagnosis of every rejection reason — and
[`docs/contributing-calculators.md`](docs/contributing-calculators.md) for how
to write the calculator itself.

## Agent skills

fitdocs packages agent skills inside the wheel. Run `fitdocs skill` to list
the packaged skills and their installed directories, and
`fitdocs skill <name>` to print one skill's installed directory and a
recipe for putting it where your agent can use it.

**Install** a packaged skill by copying its directory into your agent's
skills directory — the open SKILL.md standard fixes no location, so your
agent's own documentation is where you find it.

**Verify** a packaged skill is active by asking the agent to list its
skills; the packaged skill appears under its frontmatter `name`.

**Update** a packaged skill once you have upgraded fitdocs: run
`fitdocs skill <name>` again and replace the old directory with the new
one; the copied `SKILL.md`'s `metadata.version` says which fitdocs release
it came from.

`build-training-block` is the one packaged skill shipped today — it walks an
agent through building a training block from the athlete's answers as a plan
source, rendering it with `fitdocs plan`, amending it, and settling
ambiguous matches.

## Inbox

fitdocs defines a standing inbox: get `.fit` files there, however you like —
HealthFit → iCloud, watch sync, a manual drop, your own script — and
`fitdocs sync`, run with no arguments, drains it. `fitdocs sync SOURCE` keeps
working exactly as before and never reads the inbox or its settings.

**Delivering files is entirely your concern. fitdocs performs no watching and
no scheduling of any kind** — there is no daemon, no filesystem watcher, and
no background process. A drain happens only when `fitdocs sync` is invoked,
one shot, by you, your cron job, or your wiki agent.

### Default location and configuration

The inbox is configured in the `[inbox]` table of `<data-root>/fitdocs.toml` —
the same user-owned, fitdocs-only-reads settings file `[tiles]` and
`[plugins]` share. Every key is optional and defaults independently; omit the
table entirely to accept every default below.

| Key | Meaning | Default |
|-----|---------|---------|
| `path` | The inbox location. An absolute path is used as given; a relative path resolves against the data root. Created automatically if it lies inside the data root and is missing; an absent path outside the data root is a configuration error (guarding against typos and unmounted cloud storage). | `"inbox"` (i.e. `<data-root>/inbox/`) |
| `settle_seconds` | The stability-check settle interval, in seconds. `0` disables the wait entirely. | `2` |
| `ignore` | Additional glob patterns to ignore, matched against a candidate's basename or inbox-relative path (case-normalized). Applied *in addition to* the built-in ignore rules described under Safeguards below, never in place of them. | `[]` (no additional patterns) |
| `disposition` | What happens to a file once it has been successfully processed: `"leave"` (never touch it) or `"move"` (relocate it to `processed_dir`). Deletion is not a disposition fitdocs offers under any configuration. | `"leave"` |
| `processed_dir` | The processed-files destination; required when `disposition = "move"`, and must not equal or be nested inside the inbox. Same resolution and auto-creation rule as `path`. | `null` (unset) |

### Drain semantics

Bare `fitdocs sync` drains the resolved inbox exactly once: it selects
eligible candidates, applies the stability check, processes each stable
candidate through the same per-file pipeline an explicit-source `sync` uses,
then applies the configured disposition and runs the usual training-load
pass. The run's output names the inbox path being drained alongside the
existing written/skipped/failed summary, extended with deferred, quarantined,
moved, and failed-move counts. An inbox with no eligible files completes
successfully, reporting nothing written. `--out`, `--force`, and
`--no-prompt` all keep their explicit-source meanings on a drain.

### Safeguards

**Ignore rules.** Only regular files with a `.fit` extension (case-insensitive)
are candidates. Any candidate whose inbox-relative path has a path component
starting with a dot is ignored — this covers hidden files, AppleDouble `._*`
companions, and everything inside a hidden sync-tool staging directory (for
example `.stversions/`). A configured `ignore` pattern is checked in addition
to that dot-component rule and does exclude matching candidates. Ignored
files are excluded from processing entirely; they are never reported as
failures.

**Stability check.** Before a candidate is processed, fitdocs verifies it is
stable: its size and modification time are observed twice, separated by the
`settle_seconds` interval (once per drain for the whole batch of candidates,
never once per file). A candidate that changes or disappears between the two
observations is deferred — left completely untouched and reported by name —
and is simply re-considered, with no memory of the deferral, on the next
drain. `settle_seconds = 0` disables the wait and admits every candidate that
can be observed once.

**Quarantine record.** A file that fails processing because of a
source-level fault — the `.fit` bytes themselves cannot be decoded or
parsed — is recorded by content hash, name, and failure reason in
`<data-root>/.fitdocs/quarantine.toml`. A subsequent drain reports it once
from that record, in its own `quarantined` channel, without re-processing it
or failing the run on its account — so a known-bad file is surfaced once and
then remembered rather than looping as a fresh failure on every scheduled
run. The record is keyed on content, not name: a same-named file with
different bytes is treated as new. A failure that is instead a property of
an *existing document* — a damaged preserved region being the representative
case — is reported as a failure but is **not** recorded in the quarantine, so
simply repairing the document is enough to make the next drain succeed. Pass
`--retry-quarantined` to re-attempt every currently quarantined inbox file: a
renewed success clears its entry, and a renewed failure updates it.

### Disposition policy

The default disposition, `"leave"`, never writes, moves, renames, or deletes
an inbox file — processed files are simply left where they are, and the
archive's content dedupe makes subsequent drains skip them. **No configuration
ever deletes an inbox file: deletion is not an option fitdocs offers, under
any disposition.** The opt-in `"move"` disposition relocates a file out
of the inbox to `processed_dir` only once its content is confirmed present in
the archive, preserving both files on a name collision rather than ever
overwriting. A file that failed, was deferred, was quarantined, or whose
processing was skipped without an archived copy — including a document whose
existing `doc_version` is newer than this fitdocs produces — is never moved:
**it stays in the inbox and is retried on the next drain.** That includes a
file whose document could not be updated for any reason; leaving it in place
is what makes the retry possible.

### Ownership of the locations the inbox uses

The inbox directory and its optional `processed_dir` destination are
**user-configured locations fitdocs may create**, exactly as the
[published ownership contract](https://github.com/joshua-stauffer/fitdocs/blob/main/docs/ownership-contract.md)
defines that category: fitdocs may create and write there because your
settings name them, not because they are part of the fixed owned-path set.
The quarantine record's directory, `<data-root>/.fitdocs/`, is **tool-owned
state** — one of the fixed paths the ownership contract already lists fitdocs
as owning outright.

## Training blocks

`fitdocs plan` renders every plan source in your plan directory into a block
page under `blocks/`, plus one planned-workout page per row in a subdirectory
per block. The plan directory itself is **user-owned and read-only to
fitdocs**: fitdocs never creates, writes, renames, or deletes anything
there. It is configured in the `[plans]` table of
`<data-root>/fitdocs.toml`, the same settings file `[tiles]`, `[inbox]`, and
`[plugins]` share, which is itself read-only to fitdocs.

| Key | Meaning | Default |
|-----|---------|---------|
| `path` | The plan-source location. An absolute path is used as given; a relative path resolves against the data root. **Never created** by fitdocs. Must lie outside the owned paths — configuring it inside `blocks/` or another owned path is a configuration error. | `"plans"` (i.e. `<data-root>/plans/`) |

`fitdocs plan`, and the same pass chained at the end of `fitdocs sync` and
`fitdocs regen`, also reconciles each row against the logged workout pages,
resolving it to one of five states — `matched`, `overridden`, `skipped`,
`not logged`, or `upcoming` — a `matched` row further labeled `exact` (one
candidate), `absorbed` (several candidates, all taken by that one row — a
split session), or `ambiguous` when two or more planned workouts on the
same day compete for the same candidates, in which case the proposed
pairing is never presented as settled. An `[[override]]` entry in a plan
source pins a row to named logged workouts, or marks it skipped, ahead of
that automatic matching. Standalone or chained, the resolution shown is
re-derived from whatever the logged workout pages currently record —
nothing about the match is stored, and nothing is written back into a
workout page or a plan source.

## Benchmarks

`fitdocs derive-benchmarks [--out PATH] [--dry-run]` turns your tagged
efforts (races, tests, and hard efforts you marked with the `effort`
frontmatter key) into dated benchmarks — threshold pace, lactate-threshold
heart rate, and functional threshold power — written to `athlete.toml`
alongside anything you typed in by hand. It never touches a benchmark you
recorded yourself, reports exactly why any tagged page was declined or
failed, and `--dry-run` prints the identical report without writing
anything.

## Ownership

fitdocs writes into a wiki it does not control, so what it owns and what
you own is a published, versioned contract, not an implicit arrangement:
see the
[fitdocs Ownership Contract](https://github.com/joshua-stauffer/fitdocs/blob/main/docs/ownership-contract.md).

In short: fitdocs owns `workouts/`, `workouts/assets/`, `history/`,
`history/assets/`, `blocks/`, `fit-archive/`, `.cache/`, and `.fitdocs/`
under your data root (plus any location your `fitdocs.toml` settings
configure it to write into — the [Inbox](#inbox)'s `path` and
`processed_dir` are the first example), and writes nowhere else. `history/`
and `history/assets/` hold a second, generated document type — the
training-history page `fitdocs history` writes, alongside the per-workout
documents under `workouts/` — and carry no user-owned content of their own.
`blocks/` holds two further generated document types — one block page per
plan source and one planned-workout page per row, written by `fitdocs plan`
— of which the block page carries one user-owned region, `notes`, preserved
the same way a workout document's `notes` region is; the planned-workout
page carries no user-owned content. You own every workout document's
`notes` and `workout` regions, and its effort-tag frontmatter keys (`effort`,
`effort_distance_m`, `effort_time_s`, `effort_event`) — see the published
contract for the full detail. And `athlete.toml`'s hand-added keys survive
every fitdocs write. Every generated document carries a provenance stamp,
and the four owned directories a human or agent browses — `workouts/`,
`history/`, `blocks/`, and `fit-archive/` — each carry an `AGENTS.md`
restating the same contract for LLM agents maintaining the wiki.

## Development workflow

All feature work follows Kiro-style Spec-Driven Development via
[cc-sdd](https://github.com/gotalab/cc-sdd) (`/kiro-*` skills in Claude Code).
Start with `.kiro/steering/roadmap.md` for the current plan.
