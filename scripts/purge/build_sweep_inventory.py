"""One-shot driver for task 3.2: run `scripts.purge.sweep.run_full_sweep`
over the real working tree and write the classified inventory to a scratch
path outside the repository.

Not one of the nine CLI subcommands task 1 stubbed out (manifest,
preflight, fingerprints, plan, rewrite, verify-local, adopt, verify-remote,
pins) -- `ReproductionSweep` is, per design.md's component-to-file map, an
editorial pass with "no module of their own" as a *deliverable*; this
script is tooling that produces the inventory record for that pass, run
directly rather than wired into the shared dispatcher.

Usage::

    uv run python -m scripts.purge.build_sweep_inventory \\
        --forbidden-strings "$FITDOCS_FORBIDDEN_STRINGS" \\
        --out "$TMPDIR/fitdocs-purge/sweep-inventory.tsv"

Holds one path decision only (the default `--out` location, inside the
already-established `$TMPDIR/fitdocs-purge/` scratch root every other
out-of-repository artifact in this purge lives in); the forbidden-strings
source and the fingerprint data module are read from the same places every
other consumer reads them from.
"""

from __future__ import annotations

import os
from pathlib import Path

import typer
from tests import _content_fingerprints as fingerprints_module

from scripts.purge.sweep import (
    UnreadableFile,
    run_full_sweep,
    write_inventory,
)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_DEFAULT_OUT = Path(
    os.environ.get("TMPDIR", "/tmp"), "fitdocs-purge", "sweep-inventory.tsv"
)

_FORBIDDEN_STRINGS_OPTION = typer.Option(
    ...,
    "--forbidden-strings",
    help="Path to the FITDOCS_FORBIDDEN_STRINGS match-data file (task 2.3).",
)
_OUT_OPTION = typer.Option(
    _DEFAULT_OUT,
    "--out",
    help="Scratch path (outside the repo) to write the classified inventory to.",
)


def _report_unreadable(unreadable: tuple[UnreadableFile, ...]) -> None:
    if not unreadable:
        return
    typer.echo(
        f"build-sweep-inventory: {len(unreadable)} tracked file(s) could not be "
        "read as UTF-8 text -- their content surface was NOT scanned (path "
        "surface only); see below:",
        err=True,
    )
    for item in unreadable:
        typer.echo(f"  {item.relative_path}: {item.reason}", err=True)


def run(
    forbidden_strings: Path = _FORBIDDEN_STRINGS_OPTION,
    out: Path = _OUT_OPTION,
) -> None:
    """`purge build-sweep-inventory` (task 3.2, `#### ReproductionSweep`)."""
    classified, unreadable = run_full_sweep(
        _PROJECT_ROOT,
        forbidden_strings_path=forbidden_strings,
        fingerprints=fingerprints_module.FINGERPRINTS,
        window_lengths=fingerprints_module.WINDOW_LENGTHS,
        salt=fingerprints_module.SALT,
    )
    write_inventory(classified, out)
    _report_unreadable(unreadable)

    by_disposition: dict[str, int] = {}
    for item in classified:
        by_disposition[item.disposition] = by_disposition.get(item.disposition, 0) + 1
    typer.echo(f"wrote {len(classified)} classified hits to {out}")
    for disposition, count in sorted(by_disposition.items()):
        typer.echo(f"  {disposition}: {count}")


if __name__ == "__main__":
    typer.run(run)
