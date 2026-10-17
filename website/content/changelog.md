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
