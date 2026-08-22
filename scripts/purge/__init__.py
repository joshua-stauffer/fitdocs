"""The `encumbered-content-purge` tooling package.

One CLI entry point (`scripts/purge/__main__.py`), nine subcommands, one
module per subcommand (`verify.py` supplies two: `verify-local` and
`verify-remote`). `__main__.py` only imports each module's command callable
and registers it; it is never edited again once every module has a home --
that is what keeps the later tasks in Major 5 parallel-safe. See
`.kiro/specs/encumbered-content-purge/design.md` (`## File Structure Plan`)
for the file map and `## Components and Interfaces` for what each module
owns.
"""

from __future__ import annotations
