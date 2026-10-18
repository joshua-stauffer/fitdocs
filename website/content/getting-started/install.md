---
title: Install
description: Install fitdocs from PyPI with uv or pipx, check that it works, and learn how to upgrade and uninstall.
section: Get started
order: 1
---

# Install

fitdocs is a Python command-line tool published on [PyPI](https://pypi.org/project/fitdocs/). It needs Python 3.11 or newer. Install it as a standalone app with either of the standard tools:

```sh
uv tool install fitdocs
```

```sh
pipx install fitdocs
```

Both install fitdocs in its own environment and put the `fitdocs` command on your `PATH`, without touching any other Python project. If you don't have either one, [uv](https://docs.astral.sh/uv/) is a single download, and it will fetch a suitable Python version for you.

fitdocs brings DuckDB with it, about 44 MB installed, to power the [analytics index](../guides/analytics.md). DuckDB has no prebuilt package for musl-based Linux (such as Alpine) or free-threaded Python builds, so on those you'll need a working build toolchain.

Check that it worked:

```sh
fitdocs --version
fitdocs --help
```

**Installing doesn't create anything.** No config file, no profile, no data folder. fitdocs writes nothing until you run a command and point it at a folder.

> **Hand it to your LLM.** If you work with a coding agent (Claude Code, Codex, or similar), you can let it do the install:
>
> *"Install the `fitdocs` command-line tool from PyPI using `uv tool install fitdocs` (or `pipx install fitdocs` if uv isn't available), then run `fitdocs --version` to confirm it's on my PATH."*

## Upgrade

```sh
uv tool upgrade fitdocs      # or: pipx upgrade fitdocs
```

An upgrade never touches your data folder, your settings, your athlete profile, your notes, or your archived `.fit` files. If a release changes the document format, `fitdocs check` will tell you, and one command brings every page up to date:

```sh
fitdocs regen
```

`regen` rebuilds every page from the archived `.fit` files. You don't need the original exports, and you don't import anything again. Your notes are kept exactly as they are.

### From 0.1 to 0.2

fitdocs 0.2 changes the page format. After upgrading, run `fitdocs regen` once, before you sync anything new, then build the analytics index:

```sh
fitdocs regen
fitdocs index
fitdocs check
```

That first `regen` does a few things worth knowing about:

- **It renames many pages.** Pages are now named and dated by the time zone your device recorded, so pages recorded while traveling, or in the other half of the daylight-saving year, get new names. Each rename prints a warning with the old name. **Links to the old names aren't updated**, in your notes or in your training plans' overrides, so search for the old names and fix them.
- **It lets fitdocs recognize a workout you already have when another file of it arrives.** Run it before you sync, say, a Garmin original of a run you have as a HealthFit copy, and before your first `fitdocs pull`.
- **It sets up the new folders**, `dashboards/`, `wellness/`, `wellness-archive/`, and `recovery/`, each with its `AGENTS.md`.

Then `fitdocs check` reports anything left to sort out. If it finds one workout recorded on two pages, keep one, move anything worth keeping out of the other's notes, delete the other page, and run `fitdocs regen`. A page whose files changed keeps its old load until you run `fitdocs load --recompute`. And if you keep your plan files in `dashboards/`, move them and update `[plans] path`: fitdocs now refuses a plan folder there.

If you installed the agent skills by copying, copy them again, and add the two new ones, `fitdocs-analytics` and `fitdocs-dashboards` (see [Agent skills](../guides/wiki-integration.md#agent-skills)).

The full list of changes is in the [changelog](../changelog.md).

## Uninstall

```sh
uv tool uninstall fitdocs    # or: pipx uninstall fitdocs
```

Uninstalling removes the tool, not your data. Your workout pages, archives, settings, and athlete profile stay where they are, still readable as plain files. So do the two things fitdocs keeps outside your data root: the analytics index in `~/.cache/fitdocs/index/` and any connector keys in `~/.config/fitdocs/credentials/` (or wherever you pointed them). Delete those yourself if you don't need them.

## Install from source

To run unreleased changes or to contribute, install from a clone of the repository:

```sh
git clone https://github.com/joshua-stauffer/fitdocs.git
uv tool install --from ./fitdocs fitdocs
```

See [CONTRIBUTING.md](https://github.com/joshua-stauffer/fitdocs/blob/main/CONTRIBUTING.md) for the development setup.

**Next:** [Quickstart →](quickstart.md)
