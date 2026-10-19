---
title: Getting your files in
description: Set up the inbox so a plain `fitdocs sync` picks up new .fit files and wellness exports. It never deletes your files and runs nothing in the background.
section: Guides
order: 1
---

# Getting your files in: the inbox

Once you're past the first run, you shouldn't have to type a folder path every time. fitdocs has a **standing inbox**: a folder where `.fit` files and wellness exports land. Running `fitdocs sync` with no arguments processes whatever is waiting there.

```sh
fitdocs sync
```

You decide how files get there, and fitdocs processes them only when you (or your cron job, or your LLM agent) run `sync`. There's no watcher, daemon, or schedule. If you'd rather not move files by hand, a [connector](connectors.md) can fill the inbox for you.

## Where the inbox is

By default the inbox is `inbox/` inside your data root. fitdocs creates it the first time you drain it. To use a different folder, set it in `fitdocs.toml` at the top of your data root:

```toml
# <data-root>/fitdocs.toml. This file is yours; fitdocs only reads it.
[inbox]
path = "/Users/you/Library/Mobile Documents/iCloud~com~altifondo~HealthFit/Documents"
```

A relative path is resolved from the data root. If an absolute path outside the data root doesn't exist, fitdocs stops with an error.

## Common ways to fill it

Anything that produces a `.fit` file works. Some examples:

| Source | How files arrive |
|---|---|
| **intervals.icu** | `fitdocs pull` fetches your original files with the `intervals` connector. See [Pulling from intervals.icu](connectors.md). |
| **Apple Watch** via HealthFit | Turn on HealthFit's automatic export to iCloud Drive, then point `[inbox].path` at that folder. |
| **Garmin Connect** | Export the original file for an activity and save or unzip it into the inbox. |
| **Stryd PowerCenter** | Download the activity's FIT file. It carries running dynamics that phone-side copies often drop. |
| **Another app's export folder** | Point a `folder` connector at it, and `fitdocs pull` copies new files in. |
| **Your own script** | Anything that copies `.fit` files into the folder. |

The inbox takes wellness too: an Apple Health export, the JSON files from a Garmin data export, or intervals.icu wellness. See [Wellness and recovery](wellness.md).

The same workout from several sources makes one page. If your watch's original, HealthFit's phone copy, and a Stryd file all record one run, fitdocs puts them on one page. It builds the page from the best file (a Garmin original first, by default) and fills in any channel that file lacks, like Stryd's running dynamics, from the others. See [Your workout pages](workout-pages.md#several-files-one-workout).

## What a drain does

1. **Picks candidates.** Regular files ending in `.fit` are workouts. Files ending in `.json`, `.zip`, or `.xml` are wellness candidates. Capitalization doesn't matter. Anything with a dot-prefixed path component is ignored, including hidden files, macOS `._` files, and sync-tool staging folders.
2. **Checks that files are finished writing.** It checks each file's size and timestamp twice, a couple of seconds apart. A file still being written is **deferred**: left alone and picked up next time.
3. **Handles wellness first.** A recognized export is archived in `wellness-archive/`, and the daily wellness series is rebuilt. A `.json`, `.zip`, or `.xml` file it doesn't recognize is reported as unrecognized and left where it is. Add it to `ignore` to stop seeing it.
4. **Processes workouts**, each stable `.fit` file the same way `fitdocs sync <folder>` would. A file of a workout you already have joins that workout's page. A `.fit` file that isn't an activity, like a Garmin monitoring or sleep file, is skipped with a warning and left in place.
5. **Remembers bad files.** A file whose bytes can't be decoded, or a recognized wellness file that can't be read, is recorded once in `.fitdocs/quarantine.toml`. It's reported, then skipped on later runs so it doesn't fail again every time. Use `--retry-quarantined` to try those again.
6. **Handles processed files** according to your disposition setting (below).
7. **Runs the passes that follow:** the Morning Of blocks, training load, training blocks, the [analytics index](analytics.md) refresh, and [dashboards](dashboards.md).

The report lists how many files were written, skipped, failed, deferred, quarantined, moved, and unrecognized, and how many wellness files were archived, skipped, or failed.

## Never deletes

By default a processed file stays where it is (`disposition = "leave"`). Later drains skip it because its contents are already archived. This is the right setting when another app owns the folder, like HealthFit's export folder.

If you'd like the inbox to empty itself, opt in to moving files:

```toml
[inbox]
disposition = "move"
processed_dir = "processed"
```

A file is only moved after its contents are confirmed in the archive. If a name collides, both files are kept. Failed, deferred, and quarantined files are never moved; they stay in the inbox and get retried. Unrecognized files and `.fit` files that aren't activities are never moved either.

No setting makes fitdocs delete a file you or your own tools put in the inbox. The only files it removes are a connector's own deliveries, on the next `fitdocs pull` after their bytes are archived.

## Automating it

Because `sync` is a single command, you can run it however you like:

- **From your LLM agent:** install the packaged `fitdocs-workouts` skill ([Wiki integration](wiki-integration.md)) and say "process my workouts."
- **From cron or launchd:** `fitdocs sync --no-prompt`, or `fitdocs pull --sync --no-prompt` if you use a connector. `--no-prompt` makes sure an unattended run never waits for input. Anything that needed an answer is left uncomputed until you run `fitdocs load` yourself.

## All the settings

| Key | Default | What it does |
|---|---|---|
| `path` | `"inbox"` | Inbox location. Relative paths resolve from the data root. |
| `settle_seconds` | `2` | How long to wait between the two checks, as a finite number of seconds. `0` skips the wait. |
| `ignore` | `[]` | Extra glob patterns to skip, on top of the built-in rules, such as an unrelated JSON file. |
| `disposition` | `"leave"` | `"leave"` or `"move"`. There's no delete option. |
| `processed_dir` | unset | Where moved files go. Required when `disposition = "move"`. |

The full specification is the [inbox interface](https://github.com/joshua-stauffer/fitdocs/blob/main/docs/inbox.md) in the repository.
