"""``docs/configuration.md`` and its neighbours state the ``[identity]``
setting as the code implements it (Req 9.7, 9.8).

The documented default and vocabulary are parsed out of the page and compared
with :data:`fitdocs.identity.roles.DEFAULT_PRECEDENCE` and
:class:`fitdocs.identity.kinds.SourceKind`; the settings table and the count
word before it are compared with each other, so a lander that adds a row
without the count (or the count without a row) reds.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

from fitdocs.identity.kinds import SourceKind
from fitdocs.identity.roles import DEFAULT_PRECEDENCE, Precedence
from fitdocs.identity.settings import load_identity_settings

_DOCS = Path(__file__).resolve().parents[2] / "docs"
_CONFIGURATION = _DOCS / "configuration.md"
_COMPATIBILITY = _DOCS / "compatibility.md"
_UPGRADING = _DOCS / "upgrading.md"
_INBOX = _DOCS / "inbox.md"

_IDENTITY_HEADING = "### `[identity]`: source precedence"
_NUMBER_WORDS = {
    "one": 1,
    "two": 2,
    "three": 3,
    "four": 4,
    "five": 5,
    "six": 6,
    "seven": 7,
    "eight": 8,
    "nine": 9,
    "ten": 10,
    "eleven": 11,
    "twelve": 12,
}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _section(markdown: str, heading: str) -> str:
    """The text from ``heading`` to the next heading of the same or higher level."""
    start = markdown.index(heading)
    level = len(heading) - len(heading.lstrip("#"))
    rest = markdown[start + len(heading) :]
    end = re.search(rf"^#{{1,{level}}} ", rest, re.MULTILINE)
    return heading + (rest[: end.start()] if end else rest)


def _identity_section() -> str:
    return _section(_read(_CONFIGURATION), _IDENTITY_HEADING)


def _prose(markdown: str) -> str:
    """The text with whitespace collapsed."""
    return " ".join(markdown.split())


def _paragraph(section: str, lead: str) -> str:
    """The whitespace-collapsed paragraph that starts with ``lead``."""
    for block in re.split(r"\n\s*\n", section):
        if block.startswith(lead):
            return _prose(block)
    raise AssertionError(f"no paragraph starting with {lead!r}")


def _entry_texts(precedence: Precedence) -> list[str]:
    return [
        entry.kind.value
        if entry.manufacturer is None
        else f"{entry.kind.value}:{entry.manufacturer}"
        for entry in precedence
    ]


def _table_rows(block: str) -> list[list[str]]:
    rows: list[list[str]] = []
    for line in block.splitlines():
        if not line.startswith("|"):
            continue
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if all(re.fullmatch(r"-+", cell) for cell in cells):
            continue
        rows.append(cells)
    return rows[1:]  # the header


def _settings_table_rows() -> list[list[str]]:
    section = _section(_read(_CONFIGURATION), "## The settings file: ")
    intro = section.split("\n### ", 1)[0]
    return _table_rows(intro)


def _count_words(markdown: str) -> list[int]:
    """Every "<number word> tables today" in the page, as numbers."""
    return [
        _NUMBER_WORDS[word]
        for word in re.findall(r"(\w+)\s+tables\s+today", " ".join(markdown.split()))
    ]


def test_documented_default_equals_the_code_default() -> None:
    rows = _table_rows(_identity_section())
    precedence_rows = [row for row in rows if row[0] == "`precedence`"]
    assert len(precedence_rows) == 1
    default_cell = precedence_rows[0][2]
    documented = re.findall(r'"([^"]+)"', default_cell)
    assert documented == _entry_texts(DEFAULT_PRECEDENCE)


def test_documented_default_prose_names_the_tiers_in_the_code_order() -> None:
    prose = _paragraph(_identity_section(), "**Default.**")
    assert "2026-09-29" in prose
    # One phrase per tier of DEFAULT_PRECEDENCE, in its order.
    phrases = ["Garmin original", "phone copy", "every other original", "unknown"]
    positions = [prose.index(phrase) for phrase in phrases]
    assert positions == sorted(positions)
    assert len(_entry_texts(DEFAULT_PRECEDENCE)) == len(phrases)


def test_documented_vocabulary_equals_the_source_kinds() -> None:
    section = _identity_section()
    start = section.index("**Vocabulary.**")
    block = section[start : section.index("**Default.**")]
    bullets = re.findall(r"^- `([^`]+)`", block, re.MULTILINE)
    kinds = {bullet for bullet in bullets if ":" not in bullet}
    assert kinds == {kind.value for kind in SourceKind}
    assert [b for b in bullets if ":" in b] == ["original:<manufacturer>"]


def test_documented_example_lets_every_original_outrank_the_phone_copy() -> None:
    fences = re.findall(r"```toml\n(.*?)```", _identity_section(), re.DOTALL)
    assert len(fences) == 1
    settings = load_identity_settings(tomllib.loads(fences[0]), Path("fitdocs.toml"))
    texts = _entry_texts(settings.precedence)
    assert texts.index("original") < texts.index("phone_copy")
    assert not any(text.startswith("original:") for text in texts)


def test_settings_table_has_an_identity_row() -> None:
    rows = [row for row in _settings_table_rows() if row[0] == "`[identity]`"]
    assert len(rows) == 1
    assert rows[0][2] == "below"
    assert _IDENTITY_HEADING in _read(_CONFIGURATION)


def test_configuration_table_count_word_equals_the_row_count() -> None:
    rows = _settings_table_rows()
    assert rows, "the settings table was not found"
    section = _section(_read(_CONFIGURATION), "## The settings file: ")
    assert _count_words(section.split("\n### ", 1)[0]) == [len(rows)]


def test_compatibility_counts_equal_the_configuration_row_count() -> None:
    expected = len(_settings_table_rows())
    found = _count_words(_read(_COMPATIBILITY))
    assert found == [expected, expected]


def test_compatibility_enumerations_name_the_identity_table() -> None:
    text = " ".join(_read(_COMPATIBILITY).split())
    matches = re.findall(r"\w+ tables today[^.]*?`\[identity\]`", text)
    assert len(matches) == 2


def test_upgrading_states_regenerate_before_the_first_pull() -> None:
    section = _section(
        _read(_UPGRADING), "### Before syncing a file of a workout you already have"
    )
    prose = _paragraph(section, "Pages written before")
    assert (
        "run `fitdocs regen` before syncing a file of a workout your wiki already has "
        "from another source"
    ) in prose
    orphan = _paragraph(section, "The first `fitdocs check`")
    assert '"orphaned"' in orphan
    assert "Run `fitdocs regen` to render it" in orphan
    assert "writes a new page only when it matches none" in orphan
    assert "delete the archived file instead" in orphan


def test_inbox_states_a_held_file_is_archived_and_disposed_not_quarantined() -> None:
    prose = _paragraph(
        _section(_read(_INBOX), "## Disposition policy"), "**Held files.**"
    )
    assert "archived and disposed of like any processed file" in prose
    assert "never quarantined" in prose
    assert ".fitdocs/held.toml" in prose
