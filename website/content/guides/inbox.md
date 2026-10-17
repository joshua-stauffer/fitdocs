---
title: Getting your files in
description: Set up the inbox so a plain `fitdocs sync` picks up new .fit files. It never deletes anything and runs nothing in the background.
section: Guides
order: 1
---

# Getting your files in: the inbox

Once you're past the first run, you shouldn't have to type a folder path every time. fitdocs has a **standing inbox**: a folder where `.fit` files land. Running `fitdocs sync` with no arguments processes whatever is waiting there.

```sh
fitdocs sync
```

**You decide how files get there. fitdocs only processes them when you ask.** There's no watcher, no daemon, and no schedule. Nothing happens until you (or your cron job, or your LLM agent) run `sync`.

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
| **Apple Watch** via HealthFit | Turn on HealthFit's automatic export to iCloud Drive, then point `[inbox].path` at that folder. |
| **Garmin Connect** | Export the original file for an activity and save or unzip it into the inbox. |
| **Stryd PowerCenter** | Download the activity's FIT file. It carries running dynamics that phone-side copies often drop. |
| **Your own script** | Anything that copies `.fit` files into the folder. |

## What a drain does

1. **Picks candidates.** Only regular files ending in `.fit` (any capitalization). Anything with a dot-prefixed path component is ignored, including hidden files, macOS `._` files, and sync-tool staging folders.
2. **Checks that files are finished writing.** It checks each file's size and timestamp twice, a couple of seconds apart. A file still being written is **deferred**: left alone and picked up next time.
3. **Processes** each stable file exactly like `fitdocs sync <folder>` would.
4. **Remembers bad files.** A file whose bytes can't be decoded is recorded once in `.fitdocs/quarantine.toml`. It's reported, then skipped on later runs so it doesn't fail again every time. Use `--retry-quarantined` to try those again.
5. **Handles processed files** according to your disposition setting (below).
6. **Runs the training-load pass** and updates any training blocks.

The report lists how many files were written, skipped, failed, deferred, quarantined, and moved.

## Never deletes

By default a processed file stays exactly where it is (`disposition = "leave"`). Later drains skip it because its contents are already archived. This is the right setting when another app owns the folder, like HealthFit's export folder.

If you'd like the inbox to empty itself, opt in to moving files:

```toml
[inbox]
disposition = "move"
processed_dir = "processed"
```

A file is only moved after its contents are confirmed in the archive. If a name collides, both files are kept. Failed, deferred, and quarantined files are never moved; they stay in the inbox and get retried.

**No setting makes fitdocs delete a file from your inbox.**

## Automating it

Because `sync` is a single command, you can run it however you like:

- **From your LLM agent:** install the packaged `fitdocs-workouts` skill ([Wiki integration](wiki-integration.md)) and say "process my workouts."
- **From cron or launchd:** `fitdocs sync --no-prompt`. `--no-prompt` makes sure an unattended run never waits for input. Anything that needed an answer is left uncomputed until you run `fitdocs load` yourself.

## All the settings

| Key | Default | What it does |
|---|---|---|
| `path` | `"inbox"` | Inbox location. Relative paths resolve from the data root. |
| `settle_seconds` | `2` | How long to wait between the two checks. `0` skips the wait. |
| `ignore` | `[]` | Extra glob patterns to skip, on top of the built-in rules. |
| `disposition` | `"leave"` | `"leave"` or `"move"`. There's no delete option. |
| `processed_dir` | unset | Where moved files go. Required when `disposition = "move"`. |

The full specification is the [inbox interface](https://github.com/joshua-stauffer/fitdocs/blob/main/docs/inbox.md) in the repository.
