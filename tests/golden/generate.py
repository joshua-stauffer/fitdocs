"""Regenerate the committed golden JSON snapshots.

Run only when a model/metric change is *intended*::

    uv run python -m tests.golden.generate

Writes ``tests/golden/<name>.json`` for every fixture from the exact same
:func:`~tests.golden._serialize.build_snapshot` /
:func:`~tests.golden._serialize.canonical_json` the test uses, so the committed
files and the live comparison can never drift by construction. The snapshots are
synthetic-fixture-derived and byte-deterministic -- no personal data enters the
repo. This is a developer utility, not a test; pytest does not collect it.
"""

from __future__ import annotations

from pathlib import Path

from tests.golden._serialize import FIXTURE_NAMES, build_snapshot, canonical_json

_GOLDEN_DIR = Path(__file__).parent


def main() -> None:
    for name in FIXTURE_NAMES:
        path = _GOLDEN_DIR / f"{name}.json"
        path.write_text(canonical_json(build_snapshot(name)), encoding="utf-8")
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
