"""Bind every name a packaged skill teaches to the object that makes it true
(design: SkillConformance, task 2.2).

Parametrized over :data:`fitdocs.agentskill.PACKAGED_SKILLS` for the shared
contract (frontmatter, references, command/option binding, fenced-command
set, no ``allowed-tools``); ``_SKILL_PROFILES`` supplies what differs per
skill -- today, only the heading tuple. Distribution's task 4.2 appends the
inbox skill's entry to that map (its heading tuple, later its channel
binding) without touching this frame.

See change-protocol § Fixture Discrimination for the mutation each
assertion here is meant to red.
"""

from __future__ import annotations

import re
import tomllib
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import pytest
import typer.core
import typer.main
import yaml

from fitdocs.agentskill import PACKAGED_SKILLS, skill_file, skill_root
from fitdocs.cli import (
    _EXIT_CONFIG_ERROR,
    _EXIT_FILE_FAILURES,
    _EXIT_SUCCESS,
)
from fitdocs.cli import app as cli_app
from fitdocs.contract import MANAGED_KEYS, PRESERVED_REGIONS
from fitdocs.declaration import CONTRACT_DOCUMENTATION_URL
from fitdocs.layout import OWNED_PATHS
from fitdocs.model import Modality, Sport
from fitdocs.plans.engine import BlockStatus
from fitdocs.plans.matching import Confidence, RowState
from fitdocs.plans.model import RowAdded, RowChanged, RowRemoved, TargetChanged
from fitdocs.plans.source import parse_block

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_URL_PREFIX = "https://github.com/joshua-stauffer/fitdocs/"

_BLOCK_HEADINGS: tuple[str, ...] = (
    "When this applies",
    "Before you write: what to ask",
    "The plan source, by example",
    "Where the source lives",
    "Render it and read the report",
    "Amend midstream",
    "Settle an ambiguous match",
    "Ownership",
    "What this skill never does",
)


@dataclass(frozen=True)
class _SkillProfile:
    """What differs between packaged skills for the shared contract.

    Distribution 4.2 appends the inbox skill's entry here (its heading
    tuple; later its eight-channel binding) without touching the frame this
    module defines.
    """

    headings: tuple[str, ...]


_SKILL_PROFILES: dict[str, _SkillProfile] = {
    "build-training-block": _SkillProfile(headings=_BLOCK_HEADINGS),
}


# --- registry <-> profile map, both ways ----------------------------------


def test_every_registered_skill_has_a_profile() -> None:
    assert set(PACKAGED_SKILLS) == set(_SKILL_PROFILES)


def test_every_profile_names_a_registered_skill() -> None:
    assert set(_SKILL_PROFILES) == set(PACKAGED_SKILLS)


# --- shared parsing helpers ------------------------------------------------


def _skill_text(name: str) -> str:
    path = skill_file(name)
    assert path is not None
    return path.read_text(encoding="utf-8")


def _split_frontmatter(text: str) -> tuple[str, str]:
    """(frontmatter block, body) -- the file must open with the fence."""
    lines = text.splitlines(keepends=True)
    assert lines, "empty skill file"
    assert lines[0].rstrip("\n") == "---", "skill file does not open with the fence"
    for index in range(1, len(lines)):
        if lines[index].rstrip("\n") == "---":
            frontmatter = "".join(lines[1:index])
            body = "".join(lines[index + 1 :])
            return frontmatter, body
    raise AssertionError("no closing frontmatter fence found")


_HEADING_RE = re.compile(r"^## (.+)$", re.MULTILINE)


def _heading_order(body: str) -> tuple[str, ...]:
    return tuple(match.group(1).strip() for match in _HEADING_RE.finditer(body))


def _sections(body: str) -> dict[str, str]:
    """Heading text -> the section's own content (excluding the heading
    line itself), in file order."""
    matches = list(_HEADING_RE.finditer(body))
    assert matches, "the section walk found no H2 headings -- wrong body"
    result: dict[str, str] = {}
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        result[match.group(1).strip()] = body[start:end]
    return result


_FENCE_BLOCK_RE = re.compile(
    r"^```([a-zA-Z0-9_-]*)[ \t]*\r?\n(.*?)^```[ \t]*\r?\n?",
    re.MULTILINE | re.DOTALL,
)


def _strip_fences(text: str) -> tuple[str, list[tuple[str, str]]]:
    """(text with every fenced block removed, [(lang, content), ...]) --
    content is the exact text between the fence delimiter lines, so a toml
    fence's content can be compared byte-for-byte against a companion file."""
    fences: list[tuple[str, str]] = []

    def _capture(match: re.Match[str]) -> str:
        fences.append((match.group(1), match.group(2)))
        return ""

    stripped = _FENCE_BLOCK_RE.sub(_capture, text)
    return stripped, fences


_DOUBLE_BACKTICK_RE = re.compile(r"``(.+?)``")
_SINGLE_BACKTICK_RE = re.compile(r"(?<!`)`([^`\n]+?)`(?!`)")


def _code_spans_in(text: str) -> list[str]:
    """Every inline code span in ``text`` (fences already assumed stripped):
    double-backtick spans first (so a literal backtick inside one, as in
    `` `notes` ``, is not re-split by the single-backtick pass), then
    single-backtick spans over what remains."""
    spans: list[str] = []
    parts: list[str] = []
    last_end = 0
    for match in _DOUBLE_BACKTICK_RE.finditer(text):
        spans.append(match.group(1))
        parts.append(text[last_end : match.start()])
        last_end = match.end()
    parts.append(text[last_end:])
    remainder = "".join(parts)
    spans.extend(_SINGLE_BACKTICK_RE.findall(remainder))
    return spans


def _strip_code(text: str) -> str:
    """``text`` with every fenced block and every inline code span removed
    -- what the link-target and bare-URL scan reads. The forbidden-substring
    scan reads the raw, un-stripped body instead: a repository-relative
    reference is just as forbidden inside a code span or fence (for example
    `` `.kiro/steering` ``) as it is in prose, and stripping first would let
    it through."""
    stripped, _fences = _strip_fences(text)
    stripped = _DOUBLE_BACKTICK_RE.sub("", stripped)
    stripped = _SINGLE_BACKTICK_RE.sub("", stripped)
    return stripped


def _cell_token(cell: str) -> str:
    spans = _code_spans_in(cell)
    assert spans, f"expected a backticked token in cell {cell!r}"
    return spans[0]


_TABLE_ROW_RE = re.compile(r"^\|(.+)\|\s*$")
_TABLE_SEPARATOR_RE = re.compile(r"^\|?\s*:?-+:?\s*(\|\s*:?-+:?\s*)*\|?\s*$")


def _table_rows(section_text: str, header_first_cell: str) -> list[list[str]]:
    """The data rows of the one markdown table in ``section_text`` whose
    header's first cell is ``header_first_cell`` -- pinned below over a
    synthetic table string before it is trusted against real content."""
    lines = section_text.splitlines()
    index = 0
    while index < len(lines):
        header_match = _TABLE_ROW_RE.match(lines[index].strip())
        if (
            header_match
            and index + 1 < len(lines)
            and _TABLE_SEPARATOR_RE.match(lines[index + 1].strip())
        ):
            header_cells = [cell.strip() for cell in header_match.group(1).split("|")]
            if header_cells and header_cells[0] == header_first_cell:
                rows: list[list[str]] = []
                cursor = index + 2
                while cursor < len(lines):
                    row_match = _TABLE_ROW_RE.match(lines[cursor].strip())
                    if row_match is None:
                        break
                    rows.append(
                        [cell.strip() for cell in row_match.group(1).split("|")]
                    )
                    cursor += 1
                return rows
            index += 2
            continue
        index += 1
    raise AssertionError(f"no table with header {header_first_cell!r} found")


def test_table_rows_parses_a_synthetic_table() -> None:
    """Positive control for the parser itself, over a string with no
    relationship to any real skill file (design.md § SkillConformance's
    Risks line: "table parsing is fragile to formatting -- the parser is
    one small function with its own positive control over a synthetic
    table string")."""
    synthetic = "\n".join(
        [
            "Some prose before the table.",
            "",
            "| Foo | Bar |",
            "|-----|-----|",
            "| `a` | first |",
            "| `b` | second |",
            "",
            "Some prose after.",
        ]
    )
    rows = _table_rows(synthetic, "Foo")
    assert rows == [["`a`", "first"], ["`b`", "second"]]
    assert [_cell_token(row[0]) for row in rows] == ["a", "b"]


def _line_starting_with(body: str, prefix: str) -> list[str]:
    return [line for line in body.splitlines() if line.startswith(prefix)]


def _project_metadata() -> dict[str, object]:
    data = tomllib.loads((_PROJECT_ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project = data["project"]
    assert isinstance(project, dict)
    return project


_COMMAND_MAP = cast(typer.core.TyperGroup, typer.main.get_command(cli_app)).commands


# --- frontmatter (Req 2.1-2.6) ---------------------------------------------

_NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


@pytest.mark.parametrize("name", PACKAGED_SKILLS)
def test_frontmatter_opens_the_file_and_parses_as_a_mapping(name: str) -> None:
    text = _skill_text(name)
    assert text.startswith("---\n")
    frontmatter_text, _body = _split_frontmatter(text)
    loaded = yaml.safe_load(frontmatter_text)
    assert isinstance(loaded, dict)


@pytest.mark.parametrize("name", PACKAGED_SKILLS)
def test_frontmatter_contract(name: str) -> None:
    text = _skill_text(name)
    frontmatter_text, _body = _split_frontmatter(text)
    frontmatter = yaml.safe_load(frontmatter_text)
    assert isinstance(frontmatter, dict)

    root = skill_root(name)
    assert root is not None

    assert frontmatter["name"] == name
    assert frontmatter["name"] == root.name
    assert _NAME_RE.fullmatch(frontmatter["name"]) is not None
    assert len(frontmatter["name"]) <= 64

    description = frontmatter["description"]
    assert isinstance(description, str)
    assert 1 <= len(description) <= 1024
    assert "when" in description.lower()

    project = _project_metadata()
    license_block = project["license"]
    assert isinstance(license_block, dict)
    assert frontmatter["license"] == license_block["text"]

    compatibility = frontmatter["compatibility"]
    assert isinstance(compatibility, str)
    assert len(compatibility) <= 500
    assert "fitdocs" in compatibility

    metadata = frontmatter["metadata"]
    assert isinstance(metadata, dict)
    assert metadata["version"] == project["version"]

    assert set(frontmatter.keys()) == {
        "name",
        "description",
        "license",
        "compatibility",
        "metadata",
    }


# --- order (Req 3.1) --------------------------------------------------------


@pytest.mark.parametrize("name", PACKAGED_SKILLS)
def test_heading_order_matches_the_profile(name: str) -> None:
    text = _skill_text(name)
    _frontmatter, body = _split_frontmatter(text)
    order = _heading_order(body)
    assert order == _SKILL_PROFILES[name].headings


# --- positive controls: nothing scanned nothing ----------------------------


@pytest.mark.parametrize("name", PACKAGED_SKILLS)
def test_positive_controls_are_reached(name: str) -> None:
    text = _skill_text(name)
    _frontmatter, body = _split_frontmatter(text)

    sections = _sections(body)
    assert len(sections) == len(_SKILL_PROFILES[name].headings)

    stripped, fences = _strip_fences(body)
    assert any(lang == "bash" for lang, _content in fences), "no bash fence found"
    assert any(lang == "toml" for lang, _content in fences), "no toml fence found"

    spans = _code_spans_in(stripped)
    assert any(re.match(r"^fitdocs [a-z]", span.strip()) for span in spans), (
        "no inline `fitdocs <command>` span found"
    )


# --- commands and options: code scope only (Req 4.1, 4.2) ------------------

_FITDOCS_COMMAND_RE = re.compile(r"^fitdocs ([a-z][a-z-]*)\b")
_OPTION_TOKEN_RE = re.compile(r"(--[a-zA-Z][a-zA-Z0-9-]*)")


def _validate_fitdocs_mention(mention: str) -> str | None:
    """Validate one scanned code span/line against the typer registry;
    return the command name invoked, or ``None`` if ``mention`` is not a
    ``fitdocs`` mention at all (a span solely ``fitdocs`` names the tool and
    returns ``None`` too)."""
    stripped = mention.strip()
    if stripped == "fitdocs":
        return None
    first_word = stripped.split(None, 1)[0] if stripped else ""
    if first_word != "fitdocs":
        # The first word is not exactly `fitdocs` at all -- e.g.
        # `fitdocs.toml`, the settings filename, whose first (and only)
        # word is `fitdocs.toml`, not `fitdocs`. A mention whose first word
        # *is* `fitdocs` (however it is separated from the rest -- a plain
        # space, a tab, a non-breaking space) reaches the loud parse below
        # instead of being silently waved through.
        return None
    match = _FITDOCS_COMMAND_RE.match(stripped)
    assert match is not None, f"cannot parse a command from {mention!r}"
    command_name = match.group(1)
    assert command_name in _COMMAND_MAP, f"{command_name!r} is not a registered command"
    command = _COMMAND_MAP[command_name]
    allowed_opts = {
        opt for param in command.params for opt in getattr(param, "opts", ())
    }
    for token in _OPTION_TOKEN_RE.findall(stripped):
        assert token in allowed_opts, (
            f"{token!r} is not an option of {command_name!r} "
            f"(allowed: {sorted(allowed_opts)})"
        )
    return command_name


@pytest.mark.parametrize("name", PACKAGED_SKILLS)
def test_every_named_command_and_option_is_bound_to_the_tool(name: str) -> None:
    text = _skill_text(name)
    _frontmatter, body = _split_frontmatter(text)
    stripped, fences = _strip_fences(body)

    span_commands = set()
    for span in _code_spans_in(stripped):
        command_name = _validate_fitdocs_mention(span)
        if command_name is not None:
            span_commands.add(command_name)

    fence_commands = set()
    for lang, content in fences:
        if lang not in ("bash", "sh"):
            continue
        for line in content.splitlines():
            command_name = _validate_fitdocs_mention(line)
            if command_name is not None:
                fence_commands.add(command_name)

    assert span_commands or fence_commands, "no fitdocs command mention scanned"
    assert fence_commands == {"plan"}


# --- scoping of `regen` (Req 4.2) -------------------------------------------


@pytest.mark.parametrize("name", PACKAGED_SKILLS)
def test_regen_is_scoped_to_the_chaining_line_and_the_last_section(name: str) -> None:
    text = _skill_text(name)
    _frontmatter, body = _split_frontmatter(text)
    stripped, fences = _strip_fences(body)

    for _lang, content in fences:
        assert "regen" not in content, f"a fence names regen: {content!r}"

    headings = list(_HEADING_RE.finditer(body))
    assert headings
    last_heading_start = headings[-1].start()
    body_outside_last_section = body[:last_heading_start]

    offending = [
        line for line in body_outside_last_section.splitlines() if "regen" in line
    ]
    assert offending, "reachability control: no regen mention outside the last section"
    for line in offending:
        assert "sync" in line, f"regen named without sync on the same line: {line!r}"


# --- tables (Req 3.8, 3.9, 3.11, 4.3, 4.4) ----------------------------------


@pytest.mark.parametrize("name", PACKAGED_SKILLS)
def test_outcome_table_matches_block_status(name: str) -> None:
    text = _skill_text(name)
    _frontmatter, body = _split_frontmatter(text)
    sections = _sections(body)
    rows = _table_rows(sections["Render it and read the report"], "Outcome")
    values = [_cell_token(row[0]) for row in rows]
    assert set(values) == {status.value for status in BlockStatus}
    assert len(values) == len(set(values))
    for row in rows:
        assert row[2].strip(), f"empty Do cell: {row!r}"


@pytest.mark.parametrize("name", PACKAGED_SKILLS)
def test_state_table_matches_row_state(name: str) -> None:
    text = _skill_text(name)
    _frontmatter, body = _split_frontmatter(text)
    sections = _sections(body)
    rows = _table_rows(sections["Settle an ambiguous match"], "State")
    values = [_cell_token(row[0]) for row in rows]
    assert set(values) == {state.value for state in RowState}
    assert len(values) == len(set(values))
    for row in rows:
        assert row[2].strip(), f"empty Do cell: {row!r}"


@pytest.mark.parametrize("name", PACKAGED_SKILLS)
def test_label_table_matches_confidence(name: str) -> None:
    text = _skill_text(name)
    _frontmatter, body = _split_frontmatter(text)
    sections = _sections(body)
    rows = _table_rows(sections["Settle an ambiguous match"], "Label")
    values = [_cell_token(row[0]) for row in rows]
    assert set(values) == {label.value for label in Confidence}
    assert len(values) == len(set(values))
    for row in rows:
        assert row[1].strip(), f"empty Rule cell: {row!r}"
        assert row[2].strip(), f"empty Do cell: {row!r}"


@pytest.mark.parametrize("name", PACKAGED_SKILLS)
def test_exit_table_matches_cli_exit_constants(name: str) -> None:
    text = _skill_text(name)
    _frontmatter, body = _split_frontmatter(text)
    sections = _sections(body)
    rows = _table_rows(sections["Render it and read the report"], "Exit")
    values = [_cell_token(row[0]) for row in rows]
    expected = {"0", "1", "2"}
    assert set(values) == expected
    assert expected == {
        str(_EXIT_SUCCESS),
        str(_EXIT_FILE_FAILURES),
        str(_EXIT_CONFIG_ERROR),
    }
    assert len(values) == len(set(values))
    for row in rows:
        assert row[1].strip(), f"empty Meaning cell: {row!r}"


# --- vocabularies (Req 3.6, 4.5) ---------------------------------------------


@pytest.mark.parametrize("name", PACKAGED_SKILLS)
def test_sports_and_modalities_vocabularies(name: str) -> None:
    text = _skill_text(name)
    _frontmatter, body = _split_frontmatter(text)

    sports_lines = _line_starting_with(body, "Sports:")
    assert len(sports_lines) == 1
    assert set(_code_spans_in(sports_lines[0])) == {sport.value for sport in Sport}

    modality_lines = _line_starting_with(body, "Modalities:")
    assert len(modality_lines) == 1
    assert set(_code_spans_in(modality_lines[0])) == {
        modality.value for modality in Modality
    }

    # A prose-only scan: the example fence's own `sport = "Workout"` row
    # (`w1-wed`) would otherwise satisfy a bare substring check on the whole
    # body regardless of whether the modality rule is ever stated in prose
    # (an ever-present token -- the fence is present in every valid skill
    # body by construction). The rule sentence itself must state both
    # `modality` and `sport = "Workout"` on the same line.
    prose = _strip_fences(body)[0]
    modality_rule_lines = [
        line
        for line in prose.splitlines()
        if "modality" in line and 'sport = "Workout"' in line
    ]
    assert modality_rule_lines, "no prose line states the modality/sport rule"

    report_lines = _line_starting_with(body, "Report lines:")
    assert len(report_lines) == 1
    assert _code_spans_in(report_lines[0]), "the anchored line carries no token"


# --- the example (Req 3.5, 4.5, 4.7) -----------------------------------------

_MARKERS: tuple[str, ...] = (
    "# --- the plan as first written ---",
    "# --- amendments: appended, never edited ---",
    "# --- overrides: appended when settling ---",
)


@pytest.mark.parametrize("name", PACKAGED_SKILLS)
def test_example_is_byte_identical_and_parses(name: str) -> None:
    text = _skill_text(name)
    _frontmatter, body = _split_frontmatter(text)
    stripped, fences = _strip_fences(body)

    toml_fences = [content for lang, content in fences if lang == "toml"]
    assert toml_fences, "vacuous walk: no toml fence found"
    first_toml = toml_fences[0]

    root = skill_root(name)
    assert root is not None
    companion_path = root / "example-block.toml"
    companion_text = companion_path.read_text(encoding="utf-8")

    assert first_toml == companion_text

    block = parse_block(companion_text, block_id="example-block")

    change_types = {
        type(change) for amendment in block.amendments for change in amendment.changes
    }
    assert change_types == {RowChanged, RowAdded, RowRemoved, TargetChanged}

    assert any(override.stems for override in block.overrides)
    assert any(override.skipped for override in block.overrides)

    assert len(block.current.rows) <= 12

    day_sport_counts = Counter((row.date, row.sport) for row in block.current.rows)
    assert any(count >= 2 for count in day_sport_counts.values())

    assert block.starts.year >= 2030

    for marker in _MARKERS:
        assert marker in companion_text


# --- references (Req 4.6) ---------------------------------------------------

_LINK_TARGET_RE = re.compile(r"\]\(([^)]+)\)")
_BARE_URL_RE = re.compile(r"https?://\S+")
_FORBIDDEN_SUBSTRINGS: tuple[str, ...] = (
    "](docs/",
    "](./",
    "](../",
    ".kiro/",
    "src/fitdocs",
)


@pytest.mark.parametrize("name", PACKAGED_SKILLS)
def test_references_are_published_urls_only(name: str) -> None:
    text = _skill_text(name)
    _frontmatter, body = _split_frontmatter(text)

    # Code spans and fences are stripped before link targets are collected:
    # "matched (ambiguous): [stem](...)" is a code span, not a markdown
    # link, and a naive scan over the raw body would misread it as one
    # whose target "..." does not start with the published URL prefix.
    scanned = _strip_code(body)

    link_targets = _LINK_TARGET_RE.findall(scanned)
    assert link_targets, "vacuous walk: no markdown link found"
    for target in link_targets:
        assert target.startswith(_URL_PREFIX), target

    prose_without_links = _LINK_TARGET_RE.sub("", scanned)
    bare_urls = _BARE_URL_RE.findall(prose_without_links)
    for url in bare_urls:
        assert url.startswith(_URL_PREFIX), url

    for forbidden in _FORBIDDEN_SUBSTRINGS:
        assert forbidden not in body, f"forbidden reference form found: {forbidden!r}"

    assert CONTRACT_DOCUMENTATION_URL in body


# --- ownership enumerates nothing (Req 3.12) --------------------------------


@pytest.mark.parametrize("name", PACKAGED_SKILLS)
def test_no_owned_path_or_managed_key_is_spelled(name: str) -> None:
    text = _skill_text(name)
    _frontmatter, body = _split_frontmatter(text)

    assert OWNED_PATHS, "the owned-path tuple is unexpectedly empty"
    for owned_path in OWNED_PATHS:
        # A fixed-string membership check, never a regex: a naive
        # `re.search` over `.fitdocs/` (one of OWNED_PATHS' own members)
        # would match the unrelated substring inside the published URL
        # "github.com/joshua-stauffer/fitdocs/..." because "." matches any
        # character in a regex.
        assert owned_path not in body, f"owned path spelled in the body: {owned_path!r}"

    sections = _sections(body)
    ownership_text = sections["Ownership"]
    tokens = set(_code_spans_in(ownership_text))

    assert PRESERVED_REGIONS, "PRESERVED_REGIONS is unexpectedly empty"
    assert MANAGED_KEYS, "MANAGED_KEYS is unexpectedly empty"

    offending_regions = tokens & set(PRESERVED_REGIONS)
    assert not offending_regions, (
        f"preserved region id in Ownership: {offending_regions}"
    )
    offending_keys = tokens & MANAGED_KEYS
    assert not offending_keys, f"managed key in Ownership: {offending_keys}"
