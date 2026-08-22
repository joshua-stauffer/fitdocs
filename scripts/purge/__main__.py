"""The single CLI entry point for the `encumbered-content-purge` tooling.

Ten subcommands, one registration line each: `manifest` (a `typer.Typer`
sub-app with `tree` and `spec-status`, `scripts/purge/manifest.py`),
`preflight`, `fingerprints`, `plan`, `rewrite`, `verify-local`, `adopt`,
`verify-remote`, `pins`, `replace`. This file only imports each module's
command callable and registers it -- it never contains a module's logic.
Major 5's original plan for this file ("never edited again once every
module has a home") described the nine subcommands that existed before
Amendment 1; task 7.6 added the tenth (`replace`,
`scripts/purge/replace.py`), the one edit to this file Major 7 makes
(design.md `### New files`).

Run as `python -m scripts.purge <subcommand> ...` or `uv run python -m
scripts.purge <subcommand> ...`.
"""

from __future__ import annotations

import typer

from scripts.purge import (
    adopt,
    fingerprints,
    manifest,
    pins,
    plan,
    preflight,
    replace,
    rewrite,
    verify,
)

app = typer.Typer(no_args_is_help=True, add_completion=False)

app.add_typer(manifest.app, name="manifest")
app.command("preflight")(preflight.run)
app.command("fingerprints")(fingerprints.run)
app.command("plan")(plan.run)
app.command("rewrite")(rewrite.run)
app.command("verify-local")(verify.verify_local)
app.command("adopt")(adopt.run)
app.command("verify-remote")(verify.verify_remote)
app.command("pins")(pins.run)
app.command("replace")(replace.run)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
