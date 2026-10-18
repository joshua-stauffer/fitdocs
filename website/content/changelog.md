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

Nothing yet.

## 0.2.0 — YYYY-MM-DD

[PyPI](https://pypi.org/project/fitdocs/0.2.0/) · [tag `v0.2.0`](https://github.com/joshua-stauffer/fitdocs/tree/v0.2.0)

**Upgrading from 0.1:** run `fitdocs regen` once, then `fitdocs index`. The regen renames many pages and doesn't update links to their old names. See [Upgrade](getting-started/install.md#upgrade).

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
- **Garmin attribution.** Garmin devices are named by model, and a page built from a Garmin-recorded file carries a `Data source: Garmin <model>` line under its title.
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
