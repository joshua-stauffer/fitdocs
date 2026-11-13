---
title: Getting your files in
description: Set up the inbox so a plain `fitdocs sync` picks up new .fit files and wellness exports. It never deletes your files and runs nothing in the background.
section: Guides
order: 1
---

# Getting your files in: the inbox

Once you're past the first run, you shouldn't have to type a folder path every time. fitdocs has a **standing inbox**, a folder where `.fit` files and wellness exports land. Running `fitdocs sync` with no arguments processes whatever is waiting there.

```sh
fitdocs sync
```

You decide how files get there, and fitdocs processes them only when you (or your cron job, or your LLM agent) run `sync`. If you'd rather not move files by hand, a [connector](connectors.md) can fill the inbox for you.

## Where the inbox is

By default the inbox is `inbox/` inside your data root. To use a different folder, set it in `fitdocs.toml` at the top of your data root:

```toml
# <data-root>/fitdocs.toml. This file is yours; fitdocs only reads it.
[inbox]
path = "/Users/you/Library/Mobile Documents/iCloud~com~altifondo~HealthFit/Documents"
```

A relative path is resolved from the data root.

## Common ways to fill it

Anything that produces a `.fit` file works. Some examples:

| Source | How files arrive |
|---|---|
| **intervals.icu** | `fitdocs pull` fetches your original files with the `intervals` connector. See [Connectors](connectors.md). |
| **Apple Watch** via HealthFit | Turn on HealthFit's automatic export to iCloud Drive, then point `[inbox].path` at that folder. |
| **Garmin Connect** | `fitdocs pull` fetches your original files with the `garmin` connector. See [Connectors](connectors.md#garmin). Or export the original file for an activity and save or unzip it into the inbox. |
| **Stryd PowerCenter** | Download the activity's FIT file. It carries running dynamics that phone-side copies often drop. |
| **Another app's export folder** | Point a `folder` connector at it, and `fitdocs pull` copies new files in. |
| **Your own script** | Anything that copies `.fit` files into the folder. |

The inbox takes wellness too: an Apple Health export, the JSON files from a Garmin data export, or what the `garmin` and `intervals` connectors pull. See [Wellness and recovery](wellness.md).

If your watch's original, HealthFit's phone copy, and a Stryd file all record one run, fitdocs puts them on one page. See [Your workout pages](workout-pages.md#several-files-one-workout).

## What a drain does

1. **Picks candidates.** Regular files ending in `.fit` are workouts. Files ending in `.json`, `.zip`, or `.xml` are wellness candidates.
2. **Checks that files are finished writing.** It checks each file's size and timestamp twice, a couple of seconds apart. A file still being written is **deferred**: left alone and picked up next time.
3. **Handles wellness first.** A recognized export is archived in `wellness-archive/`, and the daily wellness series is rebuilt. A `.json`, `.zip`, or `.xml` file it doesn't recognize is reported as unrecognized and left where it is. Add it to `ignore` to stop seeing it.
4. **Processes workouts**, each stable `.fit` file the same way `fitdocs sync <folder>` would.
5. **Remembers bad files.** A file whose bytes can't be decoded, or a recognized wellness file that can't be read, is quarantined, and later runs skip it. Use `--retry-quarantined` to try those again.
6. **Handles processed files** according to your disposition setting (below).
7. **Runs the passes that follow:** the Morning Of blocks, training load, training blocks, the [analytics index](analytics.md) refresh, and [dashboards](dashboards.md).

## Never deletes

By default a processed file stays where it is (`disposition = "leave"`). Later drains skip it because its contents are already archived. This is the right setting when another app owns the folder, like HealthFit's export folder.

If you'd like the inbox to empty itself, opt in to moving files:

```toml
[inbox]
disposition = "move"
processed_dir = "processed"
```

A file is only moved after its contents are confirmed in the archive. Anything else stays in the inbox.

No setting makes fitdocs delete a file you or your own tools put in the inbox. The only files it removes are a connector's own deliveries, on the next `fitdocs pull` after they're archived.

## Automating it

You can run `sync` however you like:

- **From your LLM agent:** install the packaged `fitdocs-workouts` skill ([Wiki integration](wiki-integration.md)) and say "process my workouts."
- **From cron or launchd:** `fitdocs sync --no-prompt`, or `fitdocs pull --sync --no-prompt` if you use a connector. `--no-prompt` makes sure an unattended run never waits for input. Anything that needed an answer is left uncomputed until you run `fitdocs load` yourself.

## All the settings

| Key | Default | What it does |
|---|---|---|
| `path` | `"inbox"` | Inbox location. Relative paths resolve from the data root. |
| `settle_seconds` | `2` | How long to wait between the two checks, in seconds. `0` skips the wait. |
| `ignore` | `[]` | Extra glob patterns to skip, on top of the built-in rules, such as an unrelated JSON file. |
| `disposition` | `"leave"` | `"leave"` or `"move"`. |
| `processed_dir` | unset | Where moved files go. Required when `disposition = "move"`. |

The full specification is the [inbox interface](https://github.com/joshua-stauffer/fitdocs/blob/main/docs/inbox.md) in the repository.
