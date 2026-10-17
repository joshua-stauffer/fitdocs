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

Reads `.fit` files, archives them, writes workout pages, computes load, then updates training blocks.

- **With `SOURCE`:** processes every `.fit` file under that folder, including subfolders. The source is only read.
- **Without `SOURCE`:** drains the configured [inbox](../guides/inbox.md).

| Option | Meaning |
|---|---|
| `--out PATH` | Data root |
| `--force` | Re-render pages for files that are already archived (the archive itself is never rewritten) |
| `--no-prompt` | Never ask for missing inputs; leave those pages without a load |
| `--retry-quarantined` | (Inbox only) Try previously quarantined files again |

### `fitdocs regen`

Rebuilds every workout page from the archive in `fit-archive/`, using your current athlete profile and settings. You don't need the original files or the inbox. Your Notes, Workout sections, race tags, and computed load are kept. Run it when `check` asks you to, or after a release that changes the document format.

### `fitdocs load`

Runs the training-load pass over existing pages without syncing.

| Option | Meaning |
|---|---|
| `--recompute` | Recompute pages that already have a load |
| `--calculator ID` | Use only this calculator (see `fitdocs plugins`) |
| `--no-prompt` | Never ask; leave pages that would need an answer without a load |

## Your training over time

### `fitdocs history`

Rebuilds the fitness/fatigue/form page at `history/training-load-history.md` from the load on your pages. It never reads `.fit` files.

| Option | Meaning |
|---|---|
| `--methodology ID` | Use only this calculator's load values |

### `fitdocs derive-benchmarks`

Turns tagged races, tests, and hard efforts into dated benchmarks in `athlete.toml`. See [Benchmarks](../guides/benchmarks.md).

| Option | Meaning |
|---|---|
| `--dry-run` | Print the same report, but write nothing |

### `fitdocs plan`

Renders every plan source into a block page and planned-workout pages, then matches your logged workouts against them and prints the full report. See [Training blocks](../guides/training-blocks.md).

## Inspecting

### `fitdocs check`

Only reads. Reports every place the data root doesn't match the installed contract (missing `AGENTS.md` files, out-of-date document formats, damaged regions) and tells you how to fix each one.

### `fitdocs plugins`

Lists every registered load calculator (built-in, installed as a package, or local) with its id, version, where it came from, and the sports it supports, followed by any plugin load errors. Works without a data root.

### `fitdocs skill [NAME]`

With no name, lists the packaged agent skills and where they're installed. With a name, prints that skill's folder and a copy command. Doesn't read or write any data.

### `fitdocs --version`

Prints the installed version.

## Exit codes

| Code | Meaning |
|---|---|
| `0` | Success. A declined benchmark or an unsupported sport isn't a failure. |
| `1` | At least one file or page failed. The report says which ones and why. |
| `2` | Configuration error: no data root found, a malformed `fitdocs.toml` or `athlete.toml`, or an invalid option combination. The message names what's wrong and how to fix it. |

A plugin that fails to load prints a warning. It never fails a run or changes the exit code.
