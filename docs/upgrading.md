# Upgrading

## Upgrade commands

fitdocs installs as an isolated application. Upgrade it with the same tool
you installed it with.

With [uv](https://docs.astral.sh/uv/):

```
uv tool upgrade fitdocs
```

With [pipx](https://pipx.pypa.io/):

```
pipx upgrade fitdocs
```

What each leaves behind: `uv tool upgrade` rebuilds the tool's isolated
virtual environment in place, under the directory `uv tool dir` prints
(`<that directory>/fitdocs`, `~/.local/share/uv/tools/fitdocs` by default),
and repoints the `fitdocs` console-script shim under the directory `uv tool
dir --bin` prints (`~/.local/bin` by default) at the rebuilt environment —
no separate copy of the previous environment is left behind under the tool
directory. uv also uses its own package cache (`uv cache dir`,
`~/.cache/uv` by default) and may download a managed Python interpreter to
build the new environment; both are uv's own state, not fitdocs state, and
neither lives inside the tool's environment or its shim. pipx documents the
same in-place-replacement behavior for its own per-tool virtual
environment; this page does not independently verify it, since pipx is not
installed in the environment used to write it.

Either way, an upgrade touches nothing under your data root and nothing in
the tree you run fitdocs from — see the next section.

## What an upgrade does not touch

While your settings file, athlete profile, and local plugins are unchanged,
an upgrade within the range the compatibility policy calls compatible
touches none of the following:

- **User-owned document regions** — the user-owned regions of a generated
  document (for example a workout's notes) that you edit by hand. See the
  ownership contract's
  [User-Owned and Tool-Filled Regions](ownership-contract.md#user-owned-and-tool-filled-regions)
  for the exact list and how region ownership works; this page does not
  restate it.
- **The settings file** — `fitdocs.toml` at the top of your data root.
  fitdocs treats this file as read-only: nothing in fitdocs, including an
  upgrade, ever creates, writes, or modifies it. See
  [Configuration](configuration.md) for the full settings-file contract.
- **The athlete profile** — `athlete.toml` at the top of your data root.
  An upgrade never edits it. (The tool itself can, separately from
  upgrading: fitdocs writes one field at a time to this file when you
  answer a training-load benchmark prompt — see the ownership contract's
  [Shared and User-Owned Files](ownership-contract.md#shared-and-user-owned-files).)
- **Local plugin files** — a calculator you configured through the
  `[plugins]` table's local channel (its `path` key), resolved against your
  data root or given as an absolute path. See
  [Configuration](configuration.md#plugins-third-party-calculator-discovery)
  and [`docs/plugins.md`](plugins.md) for how local plugins are discovered.
- **The archived source files** — `fit-archive/` under your data root. Once
  a `.fit` file is archived it is immutable; an upgrade neither rewrites nor
  re-derives it.

None of these needs an edit for a compatible upgrade — see
[The compatible-upgrade guarantee](#the-compatible-upgrade-guarantee) below
for exactly what "compatible" means here.

## When a release moves the document format

Occasionally a release changes the generated-document format — the
`doc_version` a workout document under `workouts/` carries. Bringing your
existing documents current takes one command, run from anywhere fitdocs can
resolve your data root:

```
fitdocs regen
```

No other action is required. `regen` needs nothing beyond your data root —
the original `.fit` exports and the inbox are not needed. It reads the
archived `.fit` bytes under `fit-archive/`, your athlete profile, and your
settings file, and re-derives every workout document from them, the same
way `sync` does for a newly ingested file. It does not require you to
re-import anything, re-answer any prompt, or edit any file by hand.

You learn you need it two ways: `fitdocs check` reports any document whose
recorded `doc_version` is older than the version the installed fitdocs
produces, and its report names the exact remedy — running `fitdocs regen`
to bring the document to the current format. The project's
[changelog](https://github.com/joshua-stauffer/fitdocs/blob/main/CHANGELOG.md)
also states, in the entry for the release that moved the format, that the
document-format version changed. See the ownership contract's
[Document-Format Versions and Migration](ownership-contract.md#document-format-versions-and-migration)
for the full migration story, including what happens to a document written
by a newer fitdocs than the one you have installed.

## Uninstalling

With uv:

```
uv tool uninstall fitdocs
```

With pipx:

```
pipx uninstall fitdocs
```

`uv tool uninstall` removes the tool's own environment (`<uv tool dir>/fitdocs`,
`~/.local/share/uv/tools/fitdocs` by default -- not the whole tools
directory) and the `fitdocs` shim under `uv tool dir --bin`. pipx
documents removing its equivalent per-tool virtual environment and shim;
this page does not independently verify it, since pipx is not installed in
the environment used to write it. Either way, uninstalling touches nothing
under your data root and nothing in the tree you run fitdocs from.

## What remains on disk after uninstalling

fitdocs writes only into its data root's owned paths (`workouts/`,
`history/`, `blocks/`, `fit-archive/`, `.cache/`, and `.fitdocs/`), the
athlete profile, and whatever write location your settings configure — the
inbox's `path` and, when `disposition = "move"` is set, its
`processed_dir`, either of which may be an absolute path outside the data
root. Two files fitdocs only ever reads, never writes: `fitdocs.toml` and
the `.fitdocs/data-root` pointer file it consults to find your data root in
the first place. Uninstalling removes the tool, not the
places the tool wrote to or read from — every one of the following is
untouched, because uninstalling only ever removes the isolated environment
described above:

- your generated documents: `workouts/`, `history/`, and `blocks/` under
  your data root;
- your archived sources: `fit-archive/` under your data root;
- your settings file: `fitdocs.toml` at the top of your data root;
- your athlete profile: `athlete.toml` at the top of your data root;
- the `.fitdocs/data-root` pointer file in the tree you run fitdocs from;
- any inbox or processed directory your settings configure, including one
  that lies outside the data root.

(Also untouched: the tool-owned `.fitdocs/` state directory inside your
data root, including `.fitdocs/quarantine.toml`, the tile cache under
`.cache/`, and any local plugin file or directory you configured, wherever
it lives.)

## The compatible-upgrade guarantee

The exact scope of "compatible" — what a version range promises will
require no edit to your settings file, athlete profile, or local plugins —
is stated once, in
[compatibility.md#the-compatible-upgrade-guarantee](compatibility.md#the-compatible-upgrade-guarantee).
This page does not restate it.
