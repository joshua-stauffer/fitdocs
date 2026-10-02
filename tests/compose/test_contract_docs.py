"""``docs/ownership-contract.md`` states the channel composition as the code
implements it (channel-merge Req 6.6, 8.3, 8.4).

The alignment table is parsed out of the subsection "Channels a Page Takes from
Its Extras" and compared, in both directions and in order, with the constants
of :mod:`fitdocs.compose.alignment` and :mod:`fitdocs.compose.stretches` and
with :data:`fitdocs.compose.alignment.ALIGNMENT_SOURCES`: a value that moves, a
source that is reworded, a row added without a constant and a constant added
without a row each red. The subsection's named statements (the Channel Sources
section, the recompute action, the whole-hour shift constants) are checked for
presence. The ownership contract's version header is pinned by
``tests/test_ownership_contract.py``.
"""

from __future__ import annotations

import re
from pathlib import Path

from fitdocs.compose import alignment, stretches
from fitdocs.identity import matching

_DOC = Path(__file__).resolve().parents[2] / "docs" / "ownership-contract.md"
_HEADING = "### Channels a Page Takes from Its Extras"
_HEADER = ["Constant", "Value", "Source"]
_KEYS_ROW = "ALIGNMENT_KEYS"


def _subsection() -> str:
    """The subsection's text, up to the next heading of level two or three."""
    text = _DOC.read_text(encoding="utf-8")
    assert text.count(_HEADING) == 1, f"expected one {_HEADING!r} heading"
    rest = text[text.index(_HEADING) + len(_HEADING) :]
    end = re.search(r"^#{2,3} ", rest, re.MULTILINE)
    return rest[: end.start()] if end else rest


def _table_rows() -> list[list[str]]:
    """The alignment table's body rows: the subsection's only pipe table."""
    rows: list[list[str]] = []
    for line in _subsection().splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if all(re.fullmatch(r"-+", cell) for cell in cells):
            continue
        rows.append(cells)
    assert rows, "the subsection carries no table"
    assert rows[0] == _HEADER, rows[0]
    return rows[1:]


def _unquote(cell: str) -> str:
    return cell.strip("`")


def _scalar_constants() -> dict[str, int]:
    return {
        "PAUSE_GAP_S": stretches.PAUSE_GAP_S,
        "MAX_LAG_S": alignment.MAX_LAG_S,
        "MIN_MATCHED_SAMPLES": alignment.MIN_MATCHED_SAMPLES,
    }


def test_the_table_names_the_recorded_sources_in_their_order() -> None:
    names = [_unquote(row[0]) for row in _table_rows()]
    assert len(names) >= 2, "the table is nearly empty"
    assert names == list(alignment.ALIGNMENT_SOURCES)


def test_every_constant_with_a_recorded_source_is_a_known_constant() -> None:
    known = set(_scalar_constants()) | {_KEYS_ROW}
    assert set(alignment.ALIGNMENT_SOURCES) == known


def test_each_scalar_value_equals_its_constant() -> None:
    constants = _scalar_constants()
    checked = 0
    for row in _table_rows():
        name = _unquote(row[0])
        if name == _KEYS_ROW:
            continue
        assert _unquote(row[1]) == str(constants[name]), (name, row[1])
        checked += 1
    assert checked == len(constants)


def test_the_keys_value_lists_each_key_label_and_resolution_in_order() -> None:
    row = next(r for r in _table_rows() if _unquote(r[0]) == _KEYS_ROW)
    listed = [
        (label, float(resolution))
        for label, resolution in re.findall(r"([a-z]+) \(([0-9.]+) ", row[1])
    ]
    expected = [(key.label, key.resolution) for key in alignment.ALIGNMENT_KEYS]
    assert len(expected) == 2, "the key list is not the two-channel list"
    assert listed == expected


def test_each_table_source_equals_its_recorded_source() -> None:
    checked = 0
    for row in _table_rows():
        name = _unquote(row[0])
        assert row[2] == alignment.ALIGNMENT_SOURCES[name], name
        checked += 1
    assert checked == len(alignment.ALIGNMENT_SOURCES)


def test_the_subsection_names_the_statements_it_owes() -> None:
    text = _subsection()
    assert "`## Channel Sources`" in text
    assert "`fitdocs load --recompute`" in text
    assert "`derive-benchmarks`" in text
    assert "records both latitude and longitude" in text
    for constant in ("SHIFT_STEP_S", "SHIFT_MAX_HOURS", "START_TOLERANCE_S"):
        assert hasattr(matching, constant), constant
        assert f"`{constant}`" in text, constant
