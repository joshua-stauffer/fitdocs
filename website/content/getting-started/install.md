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

If a release needs more than that, its entry in the [changelog](../changelog.md) says what to run.

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
