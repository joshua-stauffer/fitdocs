# fitdocs

An installable personal knowledge manager for fitness. Consumes `.fit` files and
writes one markdown document per workout — rich, readable activity pages for
running, cycling, and weight training, with charts and computed training load.

Built to plug into a larger markdown PKM (wiki-style, Obsidian-compatible) as a
first-class path, while remaining feature-complete standalone.

## Install

fitdocs installs as a single console entry point with either standard
isolated-application installer:

```sh
uv tool install fitdocs
```

```sh
pipx install fitdocs
```

See [Install](https://github.com/joshua-stauffer/fitdocs/blob/main/docs/install.md)
for the full first-run path — installing from a checkout before the package
is published, choosing a data root, getting `.fit` files where fitdocs finds
them, the first run, and what differs between a standalone data root and one
inside an existing markdown wiki.

## What it does

1. **Ingest** `.fit` files from a target directory or the standing inbox (user drops files in; fitdocs never watches for them).
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

Outdoor activities get a **Map** section drawn over real basemap tiles —
the only time fitdocs touches the network. What leaves your machine and
when, the persistent opt-out, choosing a provider, attribution, and the tile
cache all now live in
[Configuration](https://github.com/joshua-stauffer/fitdocs/blob/main/docs/configuration.md#tiles-the-map-tile-provider-and-the-offline-opt-out).

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

See [`docs/plugins.md`](https://github.com/joshua-stauffer/fitdocs/blob/main/docs/plugins.md)
for the full guide — the worked packaged example, the local-file alternative,
the public API surface, the compatibility policy, diagnosis of every
rejection reason, and (linked from there) how to write the calculator itself.

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

fitdocs defines a standing inbox: get `.fit` files there however you like,
and `fitdocs sync`, run with no arguments, drains it — performing no
watching and no scheduling of any kind. See
[Inbox](https://github.com/joshua-stauffer/fitdocs/blob/main/docs/inbox.md)
for the full interface: every settings key and its default, drain semantics,
the safeguards, and the disposition policy's never-delete guarantee.

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
Start with `.kiro/steering/roadmap.md` for the current plan; `.kiro/specs/`
holds every feature spec (requirements → design → tasks → implementation),
and `docs/reference/` holds the research and methodology references backing
them.

## Learn more

- [Documentation index](https://github.com/joshua-stauffer/fitdocs/blob/main/docs/index.md) — the single entry point into every page below.
- [Install](https://github.com/joshua-stauffer/fitdocs/blob/main/docs/install.md) — the full first-run path, standalone or wiki-hosted.
- [Configuration](https://github.com/joshua-stauffer/fitdocs/blob/main/docs/configuration.md) — the data-root contract, the settings file, and the network/offline behavior.
- [Inbox](https://github.com/joshua-stauffer/fitdocs/blob/main/docs/inbox.md) — the full inbox interface.
- [Compatibility policy](https://github.com/joshua-stauffer/fitdocs/blob/main/docs/compatibility.md) — what a version number promises.
- [Plugin platform](https://github.com/joshua-stauffer/fitdocs/blob/main/docs/plugins.md) — the calculator plugin API.
- [Ownership contract](https://github.com/joshua-stauffer/fitdocs/blob/main/docs/ownership-contract.md) — what fitdocs owns in your data root and what you own.
