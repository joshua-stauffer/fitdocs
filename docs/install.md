# Install

A first-run path from nothing to a generated workout document: install the
tool, choose a data root and point at it, get a `.fit` file where fitdocs
finds it, run it, and read the result.

## Install the tool

fitdocs installs as a single console entry point with either of the standard
isolated-application installers — pick whichever you already have:

```sh
uv tool install fitdocs
```

```sh
pipx install fitdocs
```

Both commands install fitdocs into its own isolated environment and put the
`fitdocs` command on your `PATH`, without touching any project's dependencies.

**Until the package is published to PyPI**, install straight from a checkout
instead — the command below is proven against a clean, isolated environment
by `tests/test_packaging.py`:

```sh
uv tool install --from /path/to/fitdocs-checkout fitdocs
```

Once published, `uv tool install fitdocs` / `pipx install fitdocs` install
the same way from the public index.

Installing or upgrading never creates a directory, configuration file,
profile, or data root anywhere on your machine — nothing is written until you
run a command against one.

## Choose a data root and point at it

fitdocs writes every generated document under one directory you choose: the
**data root**. It is resolved by an explicit precedence and never guessed —
see [`docs/configuration.md`](configuration.md#the-data-root-contract) for
the full contract. fitdocs never creates the data root itself (an
unresolvable or missing directory fails loudly instead), so create it first:

```sh
mkdir -p ~/fitdocs-data
```

Then point at it, three ways:

```sh
# 1. Name it explicitly on every command:
fitdocs sync ~/Downloads/fit-files --out ~/fitdocs-data

# 2. Or export it once for the session:
export FITDOCS_DATA=~/fitdocs-data
fitdocs sync ~/Downloads/fit-files

# 3. Or drop a pointer file once, in the *source* tree you run fitdocs
#    from (e.g. a wiki checkout) -- found by walking upward from the
#    working directory, never inside the data root itself:
mkdir -p ~/notes/.fitdocs
echo ~/fitdocs-data > ~/notes/.fitdocs/data-root
cd ~/notes && fitdocs sync ~/Downloads/fit-files
```

An unresolvable data root fails loudly rather than silently writing
somewhere unexpected — including into a code repository, which fitdocs never
does by default.

## Get `.fit` files where fitdocs finds them

Either point a `sync` at a directory of `.fit` files directly:

```sh
fitdocs sync ~/Downloads/fit-files --out ~/fitdocs-data
```

or drop files into the standing inbox and drain it with no arguments — see
[`docs/inbox.md`](inbox.md) for the full interface (default location, drain
semantics, safeguards):

```sh
mkdir -p ~/fitdocs-data/inbox
cp ~/Downloads/*.fit ~/fitdocs-data/inbox/
fitdocs sync --out ~/fitdocs-data
```

## The first run

```sh
$ fitdocs sync ~/Downloads/fit-files --out ~/fitdocs-data
```

ingests every `.fit` file it finds into the data root, then runs the
training-load pass (prompting for anything a calculator needs, unless
`--no-prompt` is given or stdin is not a terminal), then reconciles any plan
sources. It ends with a summary of documents written, skipped, and failed.

## What the resulting document looks like

Each activity becomes one markdown document under
`<data-root>/workouts/`, named from the activity's local start time —
`YYYY-MM-DD-<slug>-HHMM.md` (an activity with no recorded start time gets an
`undated-<slug>-<uid>` stem instead of a fabricated date). Every `sync` and
`regen` run also writes or refreshes an `AGENTS.md` in each of the four
declared directories — `workouts/`, `fit-archive/`, `history/`, and
`blocks/` — unconditionally, not only the one this run's own output lands
in: a restatement, for a human or an LLM agent browsing the tree, of the
same [ownership contract](https://github.com/joshua-stauffer/fitdocs/blob/main/docs/ownership-contract.md)
that governs what fitdocs owns and what you own in every generated document.

## Standalone data root

Point `--out` (or `FITDOCS_DATA`, or a pointer file) at a directory that
exists only to hold your fitdocs data. Nothing else differs from the steps
above: fitdocs creates its owned subdirectories (`workouts/`, `fit-archive/`,
`.cache/`, `.fitdocs/`, and so on) under it and writes nowhere else.

## Inside an existing markdown wiki

Point the data root at (or inside) a wiki you already maintain — with an
agent, by hand, or both. What differs from the standalone case:

- **Ownership declaration.** Because fitdocs now writes inside a tree you
  otherwise own, the emitted `AGENTS.md` files and each document's
  provenance banner are how you and any agent maintaining the wiki find the
  boundary — see the
  [ownership contract](https://github.com/joshua-stauffer/fitdocs/blob/main/docs/ownership-contract.md)
  for the full, authoritative statement of what fitdocs owns.
- **The agent skill.** fitdocs packages an agent skill that gives an
  agent-managed wiki a turnkey workflow for processing the inbox and
  respecting the ownership boundary; see the README's
  [Agent skills](../README.md#agent-skills) section for where it lands, how
  to verify it is active, and how to update it. This has no
  standalone-data-root equivalent — nothing is packaged for wikis that carry
  no agent.
- **Where the inbox lives.** The inbox still resolves the same way (the
  `[inbox]` table's `path` key, default `<data-root>/inbox/`), but in a
  wiki-hosted data root you will typically point it at wherever your sync
  tool (HealthFit, a watch sync, iCloud) already lands files inside that
  wiki, rather than at a directory created solely for fitdocs.

## See also

- [`docs/configuration.md`](configuration.md) — the full data-root contract,
  the settings file, and the network/offline behavior.
- [`docs/inbox.md`](inbox.md) — the inbox interface in full.
