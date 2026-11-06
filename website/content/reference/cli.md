---
title: Commands
description: Every fitdocs command, its options, and its exit codes.
section: Reference
order: 1
---

# Commands

```
fitdocs [--version] [--help] COMMAND [OPTIONS]
```

Every command that reads or writes your data takes `--out PATH` to name the data root explicitly. Otherwise the data root comes from `FITDOCS_DATA`, then from a `.fitdocs/data-root` pointer file found by searching up from the current directory. See [Configuration](configuration.md#the-data-root).

## Processing workouts

### `fitdocs sync [SOURCE]`

Reads new files, archives them, and writes workout pages. Then it runs the passes that follow, in order: the Morning Of blocks, training load, training blocks, the analytics index refresh (once you've built the index), and dashboards.

- **With `SOURCE`:** processes every `.fit` file under that folder, including subfolders. The source is only read. Wellness files aren't read this way.
- **Without `SOURCE`:** drains the configured [inbox](../guides/inbox.md), wellness exports first, then `.fit` files.

| Option | Meaning |
|---|---|
| `--out PATH` | Data root |
| `--force` | Re-render pages for files that are already archived (the archive itself is never rewritten) |
| `--no-prompt` | Never ask for missing inputs; leave those pages without a load |
| `--retry-quarantined` | (Inbox only) Try previously quarantined files again |

### `fitdocs regen`

Rebuilds every workout page from the archive in `fit-archive/`, using your current athlete profile and settings, and rebuilds the wellness series from `wellness-archive/` first. You don't need the original files or the inbox. Your Notes, Workout sections, post text, race tags, `publish` keys, and computed load are kept. Then it runs the same passes as `sync`. Run it when `check` asks you to, after a release that changes the document format, or after you change `[identity]` or `[wellness]` settings.

`regen` may rename a page: any page whose best file has changed, and a page whose name fitdocs chose when its local start time has changed. Each rename prints a warning with the old name. Links to the old name aren't updated. See [When a page is renamed](../guides/workout-pages.md#when-a-page-is-renamed).

### `fitdocs load`

Runs the training-load pass over existing pages without syncing, then refreshes the analytics index and dashboards.

| Option | Meaning |
|---|---|
| `--recompute` | Recompute pages that already have a load |
| `--calculator ID` | Use only this calculator (see `fitdocs plugins`) |
| `--no-prompt` | Never ask; leave pages that would need an answer without a load |

## Getting files in automatically

### `fitdocs connect NAME`

Checks and stores the credentials for one configured connector instance (a `[connectors.NAME]` table), outside your data root. What it does depends on the connector:

- **`intervals` and `garmin`:** asks for the key without echoing it, makes one request to check it, and saves it only if it works.
- **`relay`:** asks for a relay token without echoing it, makes one request to check it, and saves it only if the relay accepts it. With `--register`, it registers an email address instead and saves the token the relay issues.
- **`strava`:** asks for nothing. It starts the connection through the relay instance it names, prints an address and a code, opens the address in your browser, and saves the connection token once you've given consent.
- **`folder`:** needs no credentials, so there's nothing to connect.

| Option | Meaning |
|---|---|
| `--register` | (`relay`) Register an email address with a relay that offers registration, instead of pasting a token |
| `--email ADDRESS` | (`relay`, with `--register`) The address to register. Without it, fitdocs asks. |
| `--no-browser` | (`strava`) Print the address and don't try to open a browser |

See [Connectors](../guides/connectors.md).

### `fitdocs disconnect NAME`

Forgets one configured instance's stored credentials and removes nothing else. It never writes under your data root.

For a `relay` or `strava` instance, it first makes one request asking the relay to revoke the token or end the connection. If the relay can't confirm, the credentials file is kept and the command exits `1`. For an `intervals` or `garmin` instance it makes no request, and the key stays valid at the service. With nothing stored, it says so and exits `0`.

| Option | Meaning |
|---|---|
| `--local-only` | (`relay`, `strava`) Remove the file without contacting the relay, even if fitdocs can't read it. A relay token stays valid until its operator revokes it. A Strava connection stays at the relay until the instance is connected and disconnected again, or access is revoked in Strava's settings. |

### `fitdocs pull [NAMES...]`

Fetches new activities, and wellness where it's turned on, from every configured connector instance that pulls, or just the ones you name, and delivers them into the inbox. Without names it skips `relay` and `strava` instances, which have nothing to pull. Naming one reports an error and exits `1`, with no request.

| Option | Meaning |
|---|---|
| `--since YYYY-MM-DD` | List from the start of that day, in local time |
| `--dry-run` | Report what would be fetched; download and deliver nothing. It still sends the listing requests. |
| `--sync` | Then drain the inbox, as `fitdocs sync` does |
| `--no-prompt` | With `--sync`, never ask during the load pass |

## Your training over time

### `fitdocs history`

Rebuilds the fitness/fatigue/form page at `history/training-load-history.md` from the load on your pages. It never reads `.fit` files.

| Option | Meaning |
|---|---|
| `--methodology ID` | Use only this calculator's load values |

### `fitdocs recovery`

Rebuilds the recovery page at `recovery/recovery.md` from your wellness series and the load on your pages. It never runs automatically. See [Wellness and recovery](../guides/wellness.md#the-recovery-page).

| Option | Meaning |
|---|---|
| `--methodology ID` | Use only this calculator's load values for fitness, fatigue, and form |

### `fitdocs derive-benchmarks`

Turns tagged races, tests, and hard efforts into dated benchmarks in `athlete.toml`, then derives your resting heart rate from your wellness series and your max heart rate from your runs and rides. Values you entered by hand are never changed. See [Benchmarks](../guides/benchmarks.md).

| Option | Meaning |
|---|---|
| `--dry-run` | Print the same report, but write nothing |

### `fitdocs plan`

Renders every plan source into a block page and planned-workout pages, then matches your logged workouts against them and prints the full report. See [Training blocks](../guides/training-blocks.md).

## Analytics

### `fitdocs index`

Builds the [analytics index](../guides/analytics.md), or brings it up to date. Run it once; after that, `sync`, `pull --sync`, `regen`, and `load` keep it current. It prints where the index file is.

| Option | Meaning |
|---|---|
| `--rebuild` | Build a fresh index and replace the old one |

### `fitdocs query [SQL]`

Runs one read-only SQL statement against the index and prints the result. Pass the statement as an argument, as `-` to read it from standard input, or with `--file`.

| Option | Meaning |
|---|---|
| `--file PATH` | Read the statement from a file |
| `--schema` | Describe every table and column instead |
| `--format FORMAT` | `table`, `csv`, or `json`. Default: a table on a terminal, CSV when piped |
| `--max-rows N` | Print at most N rows (default 1,000) |
| `--timeout SECONDS` | Stop a query after this long (default 30) |

### `fitdocs dashboard FORM [TARGETS...]`

Works on the charts in your [dashboard](../guides/dashboards.md) pages. A target is a page name, or `PAGE:CHART` for one chart. With no target, it acts on every page.

| Form | What it does |
|---|---|
| `check` | Report problems, each with its fix, without writing anything |
| `refresh` | Draw every chart and write the results |
| `freeze` | Take a new snapshot of a frozen chart. Needs at least one target |
| `kinds` | List every chart kind with its columns and options. Needs no data root |

| Option | Meaning |
|---|---|
| `--format FORMAT` | Report format: `text` (the default) or `json` |

## Publishing

### `fitdocs publish [PAGES...]`

Composes each workout page's post and, with `--yes`, sends it to the publish targets the page opts in to. Without `--yes` it sends no request and writes nothing. See [Publishing posts](../guides/publishing.md).

`PAGES` are workout pages, each a file name in `workouts/` (with or without `.md`) or a path to a file directly in `workouts/`. Without them, it considers every workout page.

| Option | Meaning |
|---|---|
| `--to TARGET` | Consider only this target. Repeat it to name several. |
| `--yes` | Post what the dry run shows |
| `--targets` | List the configured targets and whether each is ready, instead of publishing. It sends no request and writes nothing, and can't be combined with `PAGES`, `--to`, or `--yes`. |
| `--format FORMAT` | Report format: `text` (the default) or `json` |

## Inspecting

### `fitdocs check`

Reads the data root without changing it and reports every place it doesn't match the installed contract, with how to fix each one: missing `AGENTS.md` files, out-of-date document formats, damaged regions, archived files that couldn't be placed on one page or that no page lists, one workout recorded on two pages, wellness series problems, and derived heart-rate values that have taken over from ones you entered.

### `fitdocs plugins`

Lists every registered load calculator (built-in, installed as a package, or local) with its id, version, where it came from, and the sports it supports, followed by any plugin load errors. Works without a data root.

### `fitdocs skill [NAME]`

With no name, lists the four packaged agent skills and where they're installed. With a name, prints that skill's folder and a copy command. Doesn't read or write any data.

### `fitdocs --version`

Prints the installed version.

## Exit codes

| Code | Meaning |
|---|---|
| `0` | Success. A declined benchmark or an unsupported sport isn't a failure. |
| `1` | Something failed: a file or page, a connector (a refused key, an unreachable service), a published post, a query, or a dashboard chart. The report says which and why. |
| `2` | Configuration error: no data root found, a malformed `fitdocs.toml` or `athlete.toml`, an unknown connector name, or an invalid option combination. The message names what's wrong and how to fix it. |
| `130` | You stopped `fitdocs query`, `fitdocs dashboard`, `fitdocs publish`, or `fitdocs connect` for a relay or Strava instance with Ctrl-C. |

A plugin that fails to load prints a warning. It never fails a run or changes the exit code. Neither does an index or dashboard refresh that runs after `sync`, `pull --sync`, `regen`, or `load`.
