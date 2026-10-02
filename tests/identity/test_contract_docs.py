"""``docs/ownership-contract.md`` states the identity guarantees as the code
implements them (Req 3.11, 9.1-9.5).

The tolerance table is parsed out of the section "Source Files and Their
Roles" and compared, in both directions, with the public numeric constants of
:mod:`fitdocs.identity.matching` and with
:data:`fitdocs.identity.matching.TOLERANCE_SOURCES`: a constant whose value
moves, a source string that is reworded, a constant added without a row and a
row added without a constant each red. The section's key names, kind names and
hold-record path are compared with the code that owns them; its precedence link
is checked for presence, and its anchor's resolution is checked by
``tests/test_docs_guarantees.py``.
"""

from __future__ import annotations

import re
from pathlib import Path

from fitdocs import contract, layout
from fitdocs.declaration import declaration_text
from fitdocs.identity import matching
from fitdocs.identity.kinds import SourceKind

_DOC = Path(__file__).resolve().parents[2] / "docs" / "ownership-contract.md"
_HEADING = "## Source Files and Their Roles"
_PRECEDENCE_LINK = "configuration.md#identity-source-precedence"


def _section() -> str:
    """The section's text, up to the next second-level heading or the channels
    subsection (channel-merge), which carries its own table."""
    text = _DOC.read_text(encoding="utf-8")
    start = text.index(_HEADING)
    rest = text[start + len(_HEADING) :]
    end = re.search(r"^## |^### Channels a Page Takes", rest, re.MULTILINE)
    return rest[: end.start()] if end else rest


def _table_rows() -> list[list[str]]:
    """The tolerance table's body rows: the section's only pipe table."""
    rows: list[list[str]] = []
    for line in _section().splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if all(re.fullmatch(r"-+", cell) for cell in cells):
            continue
        rows.append(cells)
    assert rows, "the section carries no table"
    header, body = rows[0], rows[1:]
    assert header == ["Constant", "Value", "Compares", "Measured source"], header
    return body


def _unquote(cell: str) -> str:
    return cell.strip("`")


def _numeric_constants() -> dict[str, float]:
    """The module's public numeric constants: every tolerance the rule uses."""
    found = {
        name: getattr(matching, name)
        for name in matching.__all__
        if name.isupper() and isinstance(getattr(matching, name), int | float)
    }
    assert found, "no numeric constant found in fitdocs.identity.matching"
    return found


def test_the_module_records_a_source_for_exactly_its_numeric_constants() -> None:
    assert set(matching.TOLERANCE_SOURCES) == set(_numeric_constants())


def test_the_table_names_exactly_the_constants() -> None:
    rows = _table_rows()
    names = [_unquote(row[0]) for row in rows]
    assert len(names) == len(set(names)), f"a constant is listed twice: {names}"
    assert set(names) == set(_numeric_constants())


def test_each_table_value_equals_its_constant() -> None:
    constants = _numeric_constants()
    checked = 0
    for row in _table_rows():
        name = _unquote(row[0])
        assert _unquote(row[1]) == str(constants[name]), (name, row[1])
        checked += 1
    assert checked == len(constants)


def test_each_table_source_equals_its_recorded_source() -> None:
    checked = 0
    for row in _table_rows():
        name = _unquote(row[0])
        assert row[3] == matching.TOLERANCE_SOURCES[name], name
        checked += 1
    assert checked == len(matching.TOLERANCE_SOURCES)


def test_the_section_links_the_precedence_setting_with_its_anchor() -> None:
    assert f"({_PRECEDENCE_LINK})" in _section()


def test_the_section_names_the_four_base_keys_and_the_kinds() -> None:
    section = _section()
    assert len(contract.SOURCE_IDENTITY_KEYS) == 4
    for key in contract.SOURCE_IDENTITY_KEYS:
        assert f"`{key}`" in section, key
    for kind in SourceKind:
        assert f"`{kind.value}`" in section, kind


def test_the_section_names_the_hold_record_at_the_path_the_code_writes() -> None:
    relative = layout.held_path(Path("root")).relative_to("root").as_posix()
    assert relative == ".fitdocs/held.toml"
    assert f"`{relative}`" in _section()


def test_the_declarations_carry_the_rename_and_held_sentences() -> None:
    assert "may be renamed" in declaration_text("workouts/")
    assert "fitdocs holds them for a decision" in declaration_text("fit-archive/")
    for directory in ("history/", "blocks/"):
        text = declaration_text(directory)
        assert "renamed" not in text
        assert "holds them for a decision" not in text
