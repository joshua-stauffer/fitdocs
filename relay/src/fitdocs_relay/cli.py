"""The `fitdocs-relay` command (a usage stub until the operator commands land)."""

from __future__ import annotations

import sys
from collections.abc import Sequence

USAGE = "usage: fitdocs-relay <command> [options]\n"


def main(argv: Sequence[str] | None = None) -> int:
    """Print usage; the commands are added by a later task."""
    del argv
    sys.stdout.write(USAGE)
    return 0
