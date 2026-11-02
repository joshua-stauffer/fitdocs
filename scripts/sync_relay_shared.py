"""Sync the modules the relay shares with fitdocs (design: SharedCopySync).

The relay is its own project and cannot import `fitdocs`, so the few modules
both sides must agree on are pinned into `relay/src/fitdocs_relay/shared/` as
byte-identical copies. `SHARED_MODULES` is the single table of
`(source, copy)` pairs; a later spec that shares another module appends its
pair here and re-runs this script.

    python -m scripts.sync_relay_shared           # write every copy
    python -m scripts.sync_relay_shared --check   # write nothing; exit 1 on drift

Exit codes: 0 in sync (or written), 1 drift found in `--check` mode, 2 a source
is missing. Stdlib only.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Final

SHARED_MODULES: Final[tuple[tuple[str, str], ...]] = (
    (
        "src/fitdocs/connectors/relay_codes.py",
        "relay/src/fitdocs_relay/shared/relay_codes.py",
    ),
    (
        "src/fitdocs/connectors/relay_envelope.py",
        "relay/src/fitdocs_relay/shared/relay_envelope.py",
    ),
    (
        "src/fitdocs/publish/outcomes.py",
        "relay/src/fitdocs_relay/shared/outcomes.py",
    ),
    (
        "src/fitdocs/connectors/relay_targets.py",
        "relay/src/fitdocs_relay/shared/relay_targets.py",
    ),
    (
        "src/fitdocs/identity/strict.py",
        "relay/src/fitdocs_relay/shared/strict.py",
    ),
)

REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[1]

SYNC_COMMAND: Final[str] = "uv run python -B -m scripts.sync_relay_shared"


def drifted(root: Path, pairs: Sequence[tuple[str, str]] = SHARED_MODULES) -> list[str]:
    """Each pair whose copy is missing or differs from its source, as a line."""
    problems: list[str] = []
    for source, copy in pairs:
        source_bytes = (root / source).read_bytes()
        target = root / copy
        if not target.is_file():
            problems.append(f"{copy}: missing (source {source})")
        elif target.read_bytes() != source_bytes:
            problems.append(f"{copy}: differs from {source}")
    return problems


def write_copies(
    root: Path, pairs: Sequence[tuple[str, str]] = SHARED_MODULES
) -> list[str]:
    """Write every copy byte for byte; return the copies written."""
    written: list[str] = []
    for source, copy in pairs:
        data = (root / source).read_bytes()
        target = root / copy
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        written.append(copy)
    return written


def main(argv: Sequence[str] | None = None, root: Path = REPO_ROOT) -> int:
    parser = argparse.ArgumentParser(prog="python -m scripts.sync_relay_shared")
    parser.add_argument(
        "--check",
        action="store_true",
        help="write nothing; exit 1 listing every drifted copy",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=None,
        help="repository root to sync (default: the checkout holding this script)",
    )
    args = parser.parse_args(argv)
    if args.root is not None:
        root = args.root
    try:
        if args.check:
            problems = drifted(root)
            if problems:
                print("shared copies have drifted:", file=sys.stderr)
                for line in problems:
                    print(f"  {line}", file=sys.stderr)
                print(f"fix: {SYNC_COMMAND}", file=sys.stderr)
                return 1
            print(f"{len(SHARED_MODULES)} shared copies in sync")
            return 0
        for copy in write_copies(root):
            print(f"wrote {copy}")
    except FileNotFoundError as error:
        print(f"missing shared source: {error.filename}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
