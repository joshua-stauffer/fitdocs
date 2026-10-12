"""Byte-exact golden comparison for the chart kit's kind tests.

A golden lives at ``golden/<kind>/<case>.<suffix>`` beside this module.
:func:`assert_golden` compares bytes and does not create a missing file;
:func:`write_golden` is for a kind module's ``main()`` writer.
"""

from __future__ import annotations

from pathlib import Path

GOLDEN_ROOT = Path(__file__).parent / "golden"


def golden_path(kind: str, case: str, suffix: str) -> Path:
    """The golden file of ``case`` under ``kind``; ``suffix`` has no dot."""
    return GOLDEN_ROOT / kind / f"{case}.{suffix}"


def assert_golden(path: Path, text: str) -> None:
    """Fail unless ``text`` encodes to exactly the bytes stored at ``path``."""
    if not path.is_file():
        raise AssertionError(
            f"golden missing: {path} (regenerate with the kind module's main())"
        )
    expected = path.read_bytes()
    actual = text.encode("utf-8")
    if actual == expected:
        return
    offset = next(
        (i for i, (a, b) in enumerate(zip(actual, expected, strict=False)) if a != b),
        min(len(actual), len(expected)),
    )
    raise AssertionError(
        f"golden differs: {path} (rendered {len(actual)} bytes, golden "
        f"{len(expected)} bytes, first difference at byte {offset})"
    )


def write_golden(path: Path, text: str) -> None:
    """Write ``text`` as UTF-8 bytes, creating parents; for ``main()`` writers."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.encode("utf-8"))
