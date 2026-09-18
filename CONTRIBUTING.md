# Contributing to fitdocs

This page is the contributor path: how to set up the development
environment, what must pass before a change is accepted, the duty a
user-visible change carries, what is public versus internal, how to publish
your own calculator, and the rule for third-party material. It links to the
documents that already own the detail rather than restating it.

## Development environment

fitdocs is developed with [`uv`](https://docs.astral.sh/uv/). From a clone
of the repository:

```
uv sync
```

`uv sync` installs the project's development dependency group (`pytest`,
`ruff`, `mypy`, their supporting stubs, and the test-support packages) by
default — you do not need `--group dev` or any other flag. If you have
previously run `uv sync --no-dev` in this checkout, run a plain `uv sync`
again before continuing.

## The three quality gates

Every change is accepted only after three gates pass on the exact revision
being proposed. Run all three locally before opening a change:

```
uv run pytest
```

```
uv run ruff check . && uv run ruff format --check .
```

```
uv run mypy
```

The first runs the full test suite. The second lints and checks formatting.
The third runs the strict type check. These are the same three commands the
project's continuous integration runs on every push and pull request, and
the same three a release cannot skip — see the fixture-discrimination
discipline in [`.kiro/steering/change-protocol.md`](.kiro/steering/change-protocol.md)
for what a passing test is expected to prove.

## Changelog duty

A user-visible change requires an entry in [`CHANGELOG.md`](CHANGELOG.md),
added to the standing `## [Unreleased]` section as part of the same change
— not reconstructed later at release time. `CHANGELOG.md`'s own convention
note states it plainly: an entry that touches a governed contract names the
contract and the action a user or plugin author must take. In the note's
own words: entries describe user-observable behavior, not commit subjects.
`tests/test_changelog.py` enforces the file's format (heading order,
category names, link form); if your entry fails that test, that is the
module to read.

## Versioning a change that moves a contract

If your change touches a contract the compatibility policy governs, apply
that policy to the version number as part of the same change — see
[`docs/compatibility.md#version-numbering`](docs/compatibility.md#version-numbering)
for the pre-1.0 and post-1.0 rules and which version position a breaking,
additive, or internal change moves. State the contract and the required
action in the changelog entry as well; the two obligations travel together.

## Public versus internal

This project has exactly one public-versus-internal statement, and it lives
in [`docs/compatibility.md#public-versus-internal`](docs/compatibility.md#public-versus-internal).
That page defers in turn to the plugin API's own enumeration of the public
import surface, so this document does not repeat, and does not attempt to
re-derive, any name from either list. If you are unsure whether something
you are changing is public, follow the reference chain rather than guessing
from where a name is imported.

## Publishing your own calculator

If you are publishing your own training-load calculator as a separate
distribution, this section is the range-and-verification checklist; the
authoring mechanics — implementing the calculator contract, registering the
entry point, handling missing inputs — belong to
[`docs/plugins.md`](docs/plugins.md) and
[`docs/contributing-calculators.md`](docs/contributing-calculators.md), and
are not repeated here.

- **Declare a version range, not a bare dependency.** Before fitdocs
  reaches `1.0`, the compatibility policy lets a minor release break a
  governed contract, so pin to the minor rather than leaving the upper
  bound open. In your own `pyproject.toml`:

  ```toml
  [project]
  dependencies = ["fitdocs>=0.4,<0.5"]
  ```

  Widen the range only after reading the `CHANGELOG.md` entries for the
  versions in between — an entry that moves a governed contract names it
  and the action a calculator author must take.
- **Verify against a released version.** Install a released fitdocs
  (`uv tool install fitdocs==<version>`, or into a virtual environment) and
  confirm your calculator's row appears in `fitdocs plugins` — see
  [`docs/plugins.md`'s Verify step](docs/plugins.md#5-verify) for the exact
  command and what the row shows.
- **What the policy guarantees you.** As long as fitdocs stays within a
  range the policy calls compatible — bounded by your `pyproject.toml`
  declaration — the calculator contract, the entry-point group name, and
  every name in the documented public import surface stay stable under the
  guarantees in [`docs/compatibility.md`](docs/compatibility.md); a breaking
  change to any of them costs a major (or, pre-1.0, minor) version bump on
  the fitdocs side, recorded in `CHANGELOG.md`.

## Encumbered material

Material encumbered by a third party's license or trademark — an
identifying token, a lookup table, a copyright or trademark notice, or a
fragment of a removed path — must never be added to this repository or to
any published artifact without recorded permission. This is not a
style preference: the repository carries a guard that reads its match data
from outside the repository through the `FITDOCS_FORBIDDEN_STRINGS`
environment variable, and the release gate (`python -m
scripts.check_artifacts`) inspects every built artifact against the same
data and fails closed — an unrun gate is treated as a failed gate, never as
a pass. If you are unsure whether something you want to add is encumbered,
ask before adding it rather than after.

## How changes land

This repository lands every non-trivial change through one ritual —
develop on a branch, keep the three quality gates green, merge, and push —
described in full in
[`.kiro/steering/change-protocol.md`](.kiro/steering/change-protocol.md).
A human contributor follows the same gates an automated change does; there
is no separate, lighter path for a change opened by hand.
