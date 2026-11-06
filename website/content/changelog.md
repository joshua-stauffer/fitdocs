---
title: Changelog
description: Every release of fitdocs and what changed for users, mirrored from the repository's CHANGELOG.md.
section: Project
order: 1
---

# Changelog

This page mirrors [`CHANGELOG.md`](https://github.com/joshua-stauffer/fitdocs/blob/main/CHANGELOG.md) in the repository. It follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and fitdocs uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

**How to read it:** entries describe what you'll notice, not internal commits. When a release changes a **governed contract** (the document and ownership contract, the inbox interface, the plugin API, or the `fitdocs.toml` settings), the entry names the contract and says what you or a plugin author need to do. Adding or removing the built-in `threshold` calculator counts as a contract change. See the [compatibility policy](https://github.com/joshua-stauffer/fitdocs/blob/main/docs/compatibility.md) for what each version number promises.

## Unreleased

### Upgrading

This release changes the page format. After upgrading, run `fitdocs regen` once, then `fitdocs check`:

```sh
fitdocs regen
fitdocs check
```

The regen adds the two new regions to every page, rewrites chart files in a smaller form, refreshes each folder's `AGENTS.md`, and rebuilds the wellness series. It keeps every region and key you wrote. Until you run it, `fitdocs publish` reports a page written by an older fitdocs that opts in to a target as out of date.

If you installed the agent skills by copying, copy them again.

### Added

- **Publishing.** `fitdocs publish` turns workout pages into posts and sends them to the publish targets you configured as connectors. A page is posted only to the targets its `publish` key names, and a run without `--yes` is a dry run: it sends nothing and prints what each post would carry. The `[publish]` table sets the templates. See [Publishing posts](guides/publishing.md).
- **Two new regions on every workout page.** The `post` region is yours: write the page's own post there. The `published` region is fitdocs': `fitdocs publish --yes` fills it with links to the posted activities and replaces hand edits. The `publish` frontmatter key is yours, like the race-tag keys.
- **Publishing to intervals.icu.** The `intervals` connector is a publish target. For a page that opts in, `fitdocs publish --yes` sets the matching activity's name and description, and with `publish_upload = true` it uploads the page's base `.fit` file when no activity matches. `fitdocs connect` and `fitdocs pull` still only read. See [Publishing to intervals.icu](guides/connectors.md#publishing-to-intervalsicu).
- **The `garmin` connector** reads a Garmin Connect account with a personal API key you create. `fitdocs pull` fetches each activity's original `.fit` file, at most 200 per pull, and `wellness = true` adds Garmin's daily summaries, sleep, heart rate variability, and weight under a new source, `garmin-personal`. It only reads. Under the default `[identity] precedence`, the first `fitdocs sync` after a pull makes the Garmin original the main file of each page that holds another copy of the activity, so those pages re-render and some may be renamed. See [what the first sync does](guides/connectors.md#what-the-first-sync-does-to-an-existing-wiki).
- **The `relay` connector**, for a fitdocs relay. `fitdocs connect NAME` checks and stores a relay token, and `--register [--email ADDRESS]` registers an address with a relay that offers registration. See [Connecting to a relay](guides/connectors.md#connecting-to-a-relay).
- **The `strava` connector**, Compatible with Strava, reaches Strava only through a relay that offers the Strava target. For a page whose `publish` key names the instance, `fitdocs publish --yes` updates the name and description of its Strava activity, and with `upload = true` a publish that finds no matching activity sends the page's base `.fit` file for the relay to create the activity. `fitdocs connect NAME` opens the relay's connect page in your browser, unless you pass `--no-browser`. See [Strava](guides/connectors.md#strava).
- **`fitdocs disconnect NAME [--local-only]`** forgets an instance's stored credentials. For a relay or Strava instance it first asks the relay to revoke the token or end the connection, and keeps the file if the relay can't confirm. `--local-only` removes the file without contacting the relay. See [Commands](reference/cli.md#fitdocs-disconnect-name).

### Changed

- **The network.** `fitdocs publish --yes` and `fitdocs disconnect` can now send requests, and `fitdocs connect NAME --register` sends the email address you give. [Privacy and the network](guides/privacy-and-network.md) lists each command and where its requests go.
- **A bare `fitdocs pull`** pulls only instances whose connector fetches activities or wellness, so it skips `relay` and `strava` instances and doesn't contact them.
- **The wellness source order** is now `garmin-export`, `garmin-personal`, `apple-health`, `intervals-icu`. In a data root that already holds wellness, the first `fitdocs sync` or `fitdocs regen` after upgrading rebuilds the series once, and until then `fitdocs check` reports it as stale.
- **Governed contracts.** The ownership contract moves from version 16 to 19, and the document format (`doc_version`) from 11 to 12: run `fitdocs regen`. The `fitdocs.toml` settings gain the optional `[publish]` table and the connector keys `url`, `relay`, `upload`, and `publish_upload`, and `[wellness] precedence` accepts `garmin-personal`. An older fitdocs reports a credentials file holding a relay token as malformed, so don't share a credentials folder with an older version.

This release also makes chart files much smaller and carries other changes and fixes. The [full changelog](https://github.com/joshua-stauffer/fitdocs/blob/main/CHANGELOG.md) lists every change, with the action each contract change needs.

## 0.2.0 — 2026-10-19

[PyPI](https://pypi.org/project/fitdocs/0.2.0/) · [tag `v0.2.0`](https://github.com/joshua-stauffer/fitdocs/tree/v0.2.0)

### Upgrading from 0.1

This release changes the page format. After upgrading, run `fitdocs regen` once, before you sync anything new, then build the analytics index:

```sh
fitdocs regen
fitdocs index
fitdocs check
```

That first `regen` does three things:

- **It renames many pages.** Pages are now named and dated by the time zone your device recorded, so pages recorded while traveling, or in the other half of the daylight-saving year, get new names. Each rename prints a warning with the old name. **Links to the old names aren't updated**, in your notes or in your training plans' overrides, so search for the old names and fix them.
- **It lets fitdocs recognize a workout you already have when another file of it arrives.** Run it before you sync, say, a Garmin original of a run you have as a HealthFit copy, and before your first `fitdocs pull`.
- **It sets up the new folders**, `dashboards/`, `wellness/`, `wellness-archive/`, and `recovery/`, each with its `AGENTS.md`.

Then `fitdocs check` reports anything left to sort out. If it finds one workout recorded on two pages, keep one, move anything worth keeping out of the other's notes, delete the other page, and run `fitdocs regen`. A page whose files changed keeps its old load until you run `fitdocs load --recompute`. If you keep your plan files in `dashboards/`, move them and update `[plans] path`, because fitdocs now refuses a plan folder there.

If you installed the agent skills by copying, copy them again, and add the two new ones, `fitdocs-analytics` and `fitdocs-dashboards` (see [Agent skills](guides/wiki-integration.md#agent-skills)).

### Added

- **Connectors.** `fitdocs connect` and `fitdocs pull` fetch new activities, and wellness if you turn it on, from an intervals.icu account into the inbox. A `folder` connector does the same for a local folder. See [Pulling from intervals.icu](guides/connectors.md).
- **Wellness.** The inbox now takes an Apple Health export, Garmin data-export JSON files, and intervals.icu wellness. fitdocs keeps the source files in `wellness-archive/` and a daily series in `wellness/`. See [Wellness and recovery](guides/wellness.md).
- **The Morning Of block** on every workout page: that morning's resting heart rate, HRV, and sleep against your own recent normal.
- **`fitdocs recovery`** writes a recovery page with HRV, resting heart rate, and sleep next to fitness, fatigue, and form.
- **Heart-rate benchmarks.** `fitdocs derive-benchmarks` also derives resting heart rate from your wellness series and max heart rate from your runs and rides. Values you entered by hand are never changed.
- **The analytics index.** `fitdocs index` builds a local DuckDB database of your whole training log, and `fitdocs query` runs read-only SQL against it. DuckDB is a new dependency, about 44 MB installed. See [The analytics index](guides/analytics.md).
- **Dashboards.** Pages you write in `dashboards/` get charts drawn from the index and kept current, in 17 chart kinds. `fitdocs dashboard` checks, refreshes, and freezes them. See [Dashboards](guides/dashboards.md).
- **One page per workout, from several files.** Files of the same workout from different sources now share one page, and channels the main file lacks are filled in from the others, listed in a new Channel Sources section. The `[identity]` settings table chooses which file ranks first. `fitdocs check` reports files it couldn't place, archived files no page lists, and workouts recorded on two pages.
- **Running Dynamics** on run pages, from the watch's own fields or a pod like Stryd.
- **Two new agent skills**, `fitdocs-analytics` and `fitdocs-dashboards`.

### Changed

- **Pages use the local time your device recorded.** A page's date, start time, title, and filename now come from the time zone its `.fit` file records, so runs from the other half of the daylight-saving year, or from a trip, are no longer an hour or a day off. Upgrading renames those pages, and links to the old names aren't updated.
- **The inbox** treats `.json`, `.zip`, and `.xml` files as possible wellness exports, handles wellness before workouts, and skips `.fit` files that aren't activities (like Garmin monitoring files) with a warning. A connector's own deliveries are removed once they're archived. Nothing else in the inbox is ever deleted.
- **Governed contracts.** The ownership contract moves from version 4 to 16, and the document format (`doc_version`) from 5 to 11: run `fitdocs regen`. The `fitdocs.toml` settings gain the optional `[identity]`, `[wellness]`, and `[connectors]` tables, and `[plans] path` can no longer be inside `dashboards/`. The plugin API gains `FileIdentity`, an additive change. `athlete.toml` and several settings now refuse `nan` and `inf`.

This release also carries many fixes. The [full changelog](https://github.com/joshua-stauffer/fitdocs/blob/main/CHANGELOG.md) lists every change, with the action each contract change needs.

## 0.1.0 — 2026-09-19

The first public release. [PyPI](https://pypi.org/project/fitdocs/0.1.0/) · [tag `v0.1.0`](https://github.com/joshua-stauffer/fitdocs/tree/v0.1.0)

### Added

- `fitdocs` can be installed as a Python package with a single console command.
- `fitdocs sync` reads `.fit` files from the configured inbox, archives each source, and writes one markdown page per workout under the data root's `workouts/` folder, with charts and computed training load. `fitdocs regen` rebuilds every workout page using only the data root (the archive, the athlete profile, and settings). The original files and the inbox aren't needed.
- The data root's owned paths, the overwrite rules, and the user-owned sections of every generated page are published as the ownership contract. The four owned folders people and agents browse (`workouts/`, `fit-archive/`, `history/`, `blocks/`) each get a generated `AGENTS.md` restating it, and every generated page carries a matching notice.
- The inbox is configured through the `[inbox]` table in `<data-root>/fitdocs.toml`: a folder fitdocs drains on `sync`, with a disposition setting that never deletes a source file.
- Training-load calculation is pluggable through the `LoadCalculator` interface. A calculator is discovered as an installed package advertising the `fitdocs.load_calculators` entry point, or as a local plugin file or folder named in `[plugins]`. fitdocs ships one built-in calculator, `threshold`.
- `fitdocs plugins` lists every registered calculator (built-in, packaged, and local) with its id, display name, version, origin, and supported sports, plus every plugin load error. It works with or without a configured data root.
- `fitdocs check` reports every place a data root doesn't match the installed ownership contract.
- Every packaged agent skill ships inside the package and can be found with `fitdocs skill`, which prints a skill's folder and a one-line copy command without reading a data root or writing anything.
- `fitdocs --version` reports the installed version.

Also in 0.1.0, beyond the changelog's headline list: route maps, the training-history page (`fitdocs history`), race tags and `fitdocs derive-benchmarks`, training blocks (`fitdocs plan`), data-quality warnings on training load, and the `fitdocs-workouts` and `build-training-block` agent skills.
