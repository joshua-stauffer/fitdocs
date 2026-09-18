"""Bind every name a packaged skill teaches to the object that makes it true
(design: SkillConformance, task 2.2; extended by distribution task 4.2).

Parametrized over :data:`fitdocs.agentskill.PACKAGED_SKILLS` for the shared
contract that every packaged skill must satisfy regardless of subject matter
(frontmatter, heading order against its own profile, command/option binding,
published-URL references, no owned-path/managed-key spelled in the ownership
section, no ``allowed-tools``); ``_SKILL_PROFILES`` supplies what differs per
skill -- the heading tuple, and, for a skill whose body reports drain
channels, the channel binding.

A handful of tests below are pinned to ``build-training-block`` by name
rather than parametrized over every registered skill: they assert content
specific to that skill's own domain (its outcome/state/label/exit tables,
its sports/modality vocabularies, its byte-identical TOML example, and its
`regen`-scoping rule) that no other packaged skill is required to carry.
Distribution task 4.2 adds the inbox skill's entry to ``_SKILL_PROFILES``
(its heading tuple and its channel binding) and its own channel-binding
test, without touching the shared-contract tests above it.

See change-protocol § Fixture Discrimination for the mutation each
assertion here is meant to red.
"""

from __future__ import annotations

import dataclasses
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

from fitdocs.agentskill import (
    BLOCK_SKILL_NAME,
    INBOX_SKILL_NAME,
    PACKAGED_SKILLS,
    skill_file,
    skill_root,
)
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
from fitdocs.sync import DrainReport, SyncReport

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

_INBOX_HEADINGS: tuple[str, ...] = (
    "When this applies",
    "Commands to run",
    "Reading the report",
    "Ownership boundary",
    "Further reading",
)

#: The drain report's own channel fields, minus the two explicitly excluded
#: names that are not channels at all (a nested report and a path). Computed
#: by introspecting the real dataclasses -- not hardcoded -- so a channel
#: added, renamed, or dropped by :mod:`fitdocs.sync` changes this set without
#: anyone editing this file. Compared below against the profile's own
#: hardcoded literal (``_SkillProfile.channels``), which is what actually
#: catches such a change: the literal stays fixed while this derived set
#: moves.
_CHANNEL_EXCLUSIONS = frozenset({"inbox", "sync"})
_DRAIN_REPORT_CHANNELS = (
    frozenset(field.name for field in dataclasses.fields(DrainReport))
    - _CHANNEL_EXCLUSIONS
)
_SYNC_REPORT_CHANNELS = frozenset(
    field.name for field in dataclasses.fields(SyncReport)
)
_EXPECTED_CHANNELS = _DRAIN_REPORT_CHANNELS | _SYNC_REPORT_CHANNELS

#: Hardcoded literal -- the channel names the inbox skill's body is
#: *expected* to document, spelled out independently of the dataclass
#: introspection above so the two can disagree when the dataclasses change.
_INBOX_CHANNELS_LITERAL: frozenset[str] = frozenset(
    {
        "written",
        "skipped",
        "failures",
        "warnings",
        "deferred",
        "quarantined",
        "moved",
        "move_failures",
    }
)


@dataclass(frozen=True)
class _SkillProfile:
    """What differs between packaged skills for the shared contract.

    ``channels`` is ``None`` for a skill whose body does not report drain
    channels at all (``build-training-block``); a skill that does carries
    the frozen set of channel names its own ``## Reading the report``
    section is expected to document.
    """

    headings: tuple[str, ...]
    channels: frozenset[str] | None = None


_SKILL_PROFILES: dict[str, _SkillProfile] = {
    BLOCK_SKILL_NAME: _SkillProfile(headings=_BLOCK_HEADINGS),
    INBOX_SKILL_NAME: _SkillProfile(
        headings=_INBOX_HEADINGS, channels=_INBOX_CHANNELS_LITERAL
    ),
}


def test_channel_exclusion_set_is_non_vacuous() -> None:
    """``inbox`` and ``sync`` are real :class:`DrainReport` field names --
    the exclusion set actually removes something, rather than naming fields
    that were never going to be counted anyway."""
    all_drain_fields = {field.name for field in dataclasses.fields(DrainReport)}
    assert all_drain_fields >= _CHANNEL_EXCLUSIONS
    assert "inbox" in all_drain_fields
    assert "sync" in all_drain_fields


def test_literal_channel_set_matches_the_derived_dataclass_union() -> None:
    """The hardcoded literal the inbox profile is built from agrees with
    the independently-derived union of the two dataclasses' fields. A
    rename/add/drop on either dataclass moves ``_EXPECTED_CHANNELS`` without
    moving ``_INBOX_CHANNELS_LITERAL``, so the two go out of sync and this
    test is what catches it."""
    assert _INBOX_CHANNELS_LITERAL == _EXPECTED_CHANNELS
    assert len(_EXPECTED_CHANNELS) == 8


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
    license_expression = project["license"]
    assert isinstance(license_expression, str)
    assert frontmatter["license"] == license_expression

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


def test_inbox_compatibility_omits_the_data_root_clause_block_carries_it() -> None:
    """Amendment 2's decision, pinned directly: `build-training-block`'s
    compatibility clause requires a configured data root because its body
    teaches a workflow that reads one; the inbox skill's body teaches
    configuring the data root as part of its own workflow (Req 8.7), so its
    compatibility note must not presuppose one. Checking both skills in one
    test is the positive control -- a `"data root" not in text` assertion by
    itself would also pass if the whole frontmatter contract test were
    vacuous."""
    inbox_text = _skill_text(INBOX_SKILL_NAME)
    inbox_frontmatter, _ = _split_frontmatter(inbox_text)
    inbox_compatibility = yaml.safe_load(inbox_frontmatter)["compatibility"]
    assert "data root" not in inbox_compatibility

    block_text = _skill_text(BLOCK_SKILL_NAME)
    block_frontmatter, _ = _split_frontmatter(block_text)
    block_compatibility = yaml.safe_load(block_frontmatter)["compatibility"]
    assert "data root" in block_compatibility


# --- order (Req 3.1) --------------------------------------------------------


@pytest.mark.parametrize("name", PACKAGED_SKILLS)
def test_heading_order_matches_the_profile(name: str) -> None:
    text = _skill_text(name)
    _frontmatter, body = _split_frontmatter(text)
    order = _heading_order(body)
    assert order == _SKILL_PROFILES[name].headings


# --- channel binding (Req 8.2, 8.8) -----------------------------------------

_CHANNEL_SKILLS = tuple(
    name for name, profile in _SKILL_PROFILES.items() if profile.channels is not None
)


def test_channel_skills_is_non_vacuous() -> None:
    """At least one registered skill declares a channel binding -- the
    parametrized test below is not silently walking zero cases."""
    assert _CHANNEL_SKILLS
    assert INBOX_SKILL_NAME in _CHANNEL_SKILLS
    assert BLOCK_SKILL_NAME not in _CHANNEL_SKILLS


@pytest.mark.parametrize("name", _CHANNEL_SKILLS)
def test_channel_binding_matches_the_drain_and_sync_report_fields(name: str) -> None:
    """Every channel name the body's ``## Reading the report`` table
    documents (its backticked field-name column) is compared against the
    profile's declared channel set, which in turn is pinned against the
    dataclasses above (`test_literal_channel_set_matches_the_derived_
    dataclass_union`). A channel added, renamed, or dropped from either
    dataclass, or a row added/dropped/mis-spelled in the body, breaks this
    chain at the point it actually diverges."""
    text = _skill_text(name)
    _frontmatter, body = _split_frontmatter(text)
    sections = _sections(body)
    rows = _table_rows(sections["Reading the report"], "Channel")
    assert rows, "vacuous walk: no channel row found"

    field_names = {_cell_token(row[1]) for row in rows}
    assert len(field_names) == len(rows), "duplicate field name in the channel table"

    expected = _SKILL_PROFILES[name].channels
    assert expected is not None
    assert field_names == expected

    for row in rows:
        assert row[0].strip(), f"empty Channel label cell: {row!r}"
        assert row[2].strip(), f"empty Meaning cell: {row!r}"
        assert row[3].strip(), f"empty Do cell: {row!r}"


def _channel_rows_by_field(name: str) -> dict[str, list[str]]:
    """The inbox skill's ``## Reading the report`` table, keyed by the
    backticked field name in each row's second cell -- so a claim can be
    pinned against the *specific* row it belongs to rather than the body as
    a whole (a whole-body substring check cannot tell a claim in the right
    row from the same claim relocated to the wrong one)."""
    text = _skill_text(name)
    _frontmatter, body = _split_frontmatter(text)
    sections = _sections(body)
    rows = _table_rows(sections["Reading the report"], "Channel")
    return {_cell_token(row[1]): row for row in rows}


def test_move_failures_row_states_processed_and_retried_never_reprocess() -> None:
    """Sentence-level pins for the task's three called-out claims, each
    asserted against the specific row's own cells (not the body as a
    whole) so a claim relocated to the wrong row is caught rather than
    satisfying a whole-file substring scan. Each phrase is also asserted
    ABSENT from the *other* packaged skill's body, as a positive control
    that the assertion is not simply always true of any markdown file."""
    inbox_rows = _channel_rows_by_field(INBOX_SKILL_NAME)
    block_text = _skill_text(BLOCK_SKILL_NAME)

    move_failure_do = inbox_rows["move_failures"][3]
    deferred_do = inbox_rows["deferred"][3]
    quarantined_do = inbox_rows["quarantined"][3]

    move_failure_claim = "retried automatically on the next drain"
    reprocess_claim = "never a reason to reprocess"
    quarantine_claim = "needs the user, not the agent"
    deferred_claim = "No action -- it is reconsidered automatically"

    assert move_failure_claim in move_failure_do
    assert reprocess_claim in move_failure_do
    assert quarantine_claim in quarantined_do
    assert deferred_claim in deferred_do
    # The Deferred Do cell must never suggest deleting the file -- fitdocs's
    # inbox never deletes anything, and a "no action" claim that is merely
    # appended after some other imperative sentence must not satisfy this
    # test by substring alone.
    assert "delete" not in deferred_do.lower()

    # Negative control on the move-failures Do cell specifically: it must
    # never suggest reprocessing, in any letter case (the only permitted occurrence of
    # "reprocess" is inside "never a reason to reprocess") and must never
    # mention `--force`, which is exactly how one would reprocess a file.
    assert move_failure_do.lower().count("reprocess") == 1
    assert "--force" not in move_failure_do

    for phrase in (
        move_failure_claim,
        reprocess_claim,
        quarantine_claim,
        deferred_claim,
    ):
        assert phrase not in block_text, (
            f"positive control failed -- {phrase!r} found in the other skill too"
        )


# --- positive controls: nothing scanned nothing ----------------------------


@pytest.mark.parametrize("name", PACKAGED_SKILLS)
def test_positive_controls_are_reached(name: str) -> None:
    """Shared across every packaged skill: the section walk actually found
    every heading its profile declares, and the body carries at least one
    fenced ``bash`` command."""
    text = _skill_text(name)
    _frontmatter, body = _split_frontmatter(text)

    sections = _sections(body)
    assert len(sections) == len(_SKILL_PROFILES[name].headings)

    stripped, fences = _strip_fences(body)
    assert any(lang == "bash" for lang, _content in fences), "no bash fence found"

    spans = _code_spans_in(stripped)
    assert any(re.match(r"^fitdocs [a-z]", span.strip()) for span in spans), (
        "no inline `fitdocs <command>` span found"
    )


def test_positive_controls_block_skill_also_carries_a_toml_example() -> None:
    """``build-training-block`` alone teaches a TOML plan-source example;
    that requirement is this skill's own, not the shared contract every
    packaged skill carries."""
    text = _skill_text(BLOCK_SKILL_NAME)
    _frontmatter, body = _split_frontmatter(text)
    _stripped, fences = _strip_fences(body)
    assert any(lang == "toml" for lang, _content in fences), "no toml fence found"


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


def test_block_skill_fenced_commands_are_exactly_plan() -> None:
    """``build-training-block``'s own body only ever fences ``fitdocs
    plan`` -- this is that skill's own command surface, not a property
    every packaged skill shares (the inbox skill fences ``sync``, ``check``,
    and ``regen`` instead)."""
    text = _skill_text(BLOCK_SKILL_NAME)
    _frontmatter, body = _split_frontmatter(text)
    _stripped, fences = _strip_fences(body)

    fence_commands = set()
    for lang, content in fences:
        if lang not in ("bash", "sh"):
            continue
        for line in content.splitlines():
            command_name = _validate_fitdocs_mention(line)
            if command_name is not None:
                fence_commands.add(command_name)

    assert fence_commands == {"plan"}


def _inbox_bash_fence_command_sets() -> list[frozenset[str]]:
    """The commands named in each individual fenced ``bash``/``sh`` block of
    the inbox skill's body, one frozenset per fence -- kept per-fence rather
    than unioned, because *which* commands share a fence is exactly what
    distinguishes the routine pair from the conditional ``regen`` fence."""
    text = _skill_text(INBOX_SKILL_NAME)
    _frontmatter, body = _split_frontmatter(text)
    _stripped, fences = _strip_fences(body)

    fence_sets: list[frozenset[str]] = []
    for lang, content in fences:
        if lang not in ("bash", "sh"):
            continue
        commands = set()
        for line in content.splitlines():
            command_name = _validate_fitdocs_mention(line)
            if command_name is not None:
                commands.add(command_name)
        if commands:
            fence_sets.append(frozenset(commands))
    return fence_sets


def test_inbox_skill_routine_fence_is_exactly_sync_and_check() -> None:
    """The routine drain pair lives in one fence together, and that fence
    names exactly ``sync`` and ``check`` -- never ``regen``, which an agent
    that blindly executes every fenced block in a skill would otherwise run
    on every drain (the defect this rewrite fixes)."""
    fence_sets = _inbox_bash_fence_command_sets()
    assert frozenset({"sync", "check"}) in fence_sets


def test_inbox_skill_regen_is_never_in_the_routine_fence() -> None:
    """``regen`` is fenced too (so the command/option binding scan still
    reaches it), but never in the same fence as the routine pair -- an agent
    that runs only the routine fence must never run ``regen`` as a side
    effect."""
    fence_sets = _inbox_bash_fence_command_sets()
    assert any("regen" in commands for commands in fence_sets), (
        "vacuous walk: regen is not fenced anywhere"
    )
    for commands in fence_sets:
        if "regen" in commands:
            assert commands == {"regen"}, (
                f"regen shares a fence with other commands: {commands!r}"
            )


_BARE_OPTION_RE = re.compile(r"^--[a-zA-Z][a-zA-Z0-9-]*$")


def test_inbox_bare_option_spans_are_valid_for_a_fenced_command() -> None:
    """A bare ``--option`` code span (not attached to a ``fitdocs <command>``
    mention on the same span/line, so :func:`_validate_fitdocs_mention` never
    reaches it) is otherwise invisible to the shared command/option binding
    scan. This test closes that gap for the inbox skill by checking every
    bare option span against the union of options belonging to a command the
    body actually fences -- a misspelled option here (an extra letter, a
    missing letter) is caught even though it is never attached to a
    ``fitdocs`` mention."""
    text = _skill_text(INBOX_SKILL_NAME)
    _frontmatter, body = _split_frontmatter(text)
    stripped, fences = _strip_fences(body)

    fence_commands: set[str] = set()
    for commands in _inbox_bash_fence_command_sets():
        fence_commands |= commands
    assert fence_commands, "vacuous walk: no fenced command found"

    allowed_opts: set[str] = set()
    for command_name in fence_commands:
        command = _COMMAND_MAP[command_name]
        allowed_opts |= {
            opt for param in command.params for opt in getattr(param, "opts", ())
        }

    bare_option_spans = [
        span
        for span in _code_spans_in(stripped)
        if _BARE_OPTION_RE.fullmatch(span.strip())
    ]
    assert bare_option_spans, "vacuous walk: no bare option span found"
    for span in bare_option_spans:
        assert span.strip() in allowed_opts, (
            f"{span!r} is not an option of any fenced command "
            f"({sorted(fence_commands)}; allowed: {sorted(allowed_opts)})"
        )


# --- scoping of `regen` (Req 4.2, build-training-block only) ---------------


def test_regen_is_scoped_to_the_chaining_line_and_the_last_section() -> None:
    """``build-training-block`` never runs ``regen`` itself; the inbox
    skill's own body runs it deliberately (as a fenced command, in its
    ``## Commands to run`` section), so this scoping rule is
    ``build-training-block``'s own and not shared."""
    text = _skill_text(BLOCK_SKILL_NAME)
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


@pytest.mark.parametrize("name", (BLOCK_SKILL_NAME,))
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


@pytest.mark.parametrize("name", (BLOCK_SKILL_NAME,))
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


@pytest.mark.parametrize("name", (BLOCK_SKILL_NAME,))
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


@pytest.mark.parametrize("name", (BLOCK_SKILL_NAME,))
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


@pytest.mark.parametrize("name", (BLOCK_SKILL_NAME,))
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


@pytest.mark.parametrize("name", (BLOCK_SKILL_NAME,))
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
    # The ownership heading's exact wording differs per skill ("Ownership"
    # vs. "Ownership boundary"); found by content rather than hardcoded
    # against one skill's spelling, so this test keeps applying once a
    # second skill's heading differs (a vacuous walk if no such heading
    # existed at all is guarded by the assert on the match).
    ownership_headings = [h for h in sections if "Ownership" in h]
    assert ownership_headings, f"no Ownership heading found among {list(sections)!r}"
    assert len(ownership_headings) == 1, ownership_headings
    ownership_text = sections[ownership_headings[0]]
    tokens = set(_code_spans_in(ownership_text))

    assert PRESERVED_REGIONS, "PRESERVED_REGIONS is unexpectedly empty"
    assert MANAGED_KEYS, "MANAGED_KEYS is unexpectedly empty"

    offending_regions = tokens & set(PRESERVED_REGIONS)
    assert not offending_regions, (
        f"preserved region id in Ownership: {offending_regions}"
    )
    offending_keys = tokens & MANAGED_KEYS
    assert not offending_keys, f"managed key in Ownership: {offending_keys}"


def test_inbox_ownership_names_declaration_contract_and_never_hand_edits() -> None:
    """Req 8.3: the ownership section must state the boundary and point at
    the in-tree declaration and the published contract as its authority --
    pinned as three separate, specific assertions on the section's own text
    rather than on the whole body, so a section that states the boundary
    vaguely (with no declaration name, no contract link, and no never-edit
    statement) is caught rather than passing on adjacent body content."""
    text = _skill_text(INBOX_SKILL_NAME)
    _frontmatter, body = _split_frontmatter(text)
    sections = _sections(body)
    ownership_text = sections["Ownership boundary"]

    assert "AGENTS.md" in ownership_text
    assert CONTRACT_DOCUMENTATION_URL in ownership_text
    assert "never hand-edits" in ownership_text
