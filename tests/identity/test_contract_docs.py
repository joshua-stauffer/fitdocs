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

import ast
import re
from pathlib import Path

import pytest

from fitdocs import contract, layout
from fitdocs.declaration import declaration_text
from fitdocs.identity import matching
from fitdocs.identity.kinds import SourceKind
from tests._changelog_view import V0_1_0, read_unreleased_since

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


# --- Amendment 1 (A1.3): the amended strict tier, stated where it is read ----


def _flat(text: str) -> str:
    return " ".join(text.split())


def _contract_version_history() -> str:
    tree = ast.parse(Path(contract.__file__).read_text(encoding="utf-8"))
    for index, node in enumerate(tree.body[:-1]):
        if not isinstance(node, ast.AnnAssign):
            continue
        if (
            not isinstance(node.target, ast.Name)
            or node.target.id != "CONTRACT_VERSION"
        ):
            continue
        following = tree.body[index + 1]
        if (
            isinstance(following, ast.Expr)
            and isinstance(following.value, ast.Constant)
            and isinstance(following.value.value, str)
        ):
            return _flat(following.value.value)
        raise AssertionError("CONTRACT_VERSION has no adjacent history string")
    raise AssertionError("CONTRACT_VERSION declaration was not found")


def test_the_strict_bullet_states_the_amended_tier() -> None:
    section = _flat(_section())
    assert (
        "**strict** — the starts are no more than `START_TOLERANCE_S` apart, and "
        "either both files record a distance and the distances are no more than "
        "`DISTANCE_TOLERANCE_M` or `DISTANCE_TOLERANCE_FRACTION` of the longer "
        "distance apart, whichever is larger (elapsed times are then not "
        "compared), or a distance is missing and the elapsed times are no more "
        "than `ELAPSED_TOLERANCE_S` apart;"
    ) in section


def test_the_absent_value_sentence_states_the_device_only_case() -> None:
    assert (
        "Two files of which one records no distance and one records no elapsed "
        "time are recognized as one session only by device evidence"
    ) in _flat(_section())


def test_the_changed_at_this_version_paragraph_names_the_amendment() -> None:
    head = _flat(_DOC.read_text(encoding="utf-8").split("\n\nThis document", 1)[0])
    assert f"**Contract version:** `{contract.CONTRACT_VERSION}`" in head


@pytest.mark.parametrize(
    "phrase",
    [
        "Workout documents gain the `morning` region",
        "fitdocs alone writes from the wellness series and replaces "
        "whenever it differs",
        "The morning-of pass that `fitdocs sync`, `fitdocs pull --sync` and "
        "`fitdocs regen` run rewrites only that region",
        "generated content is re-derivable from the wellness series as well as "
        "from the archived sources, the athlete profile, the configured timezone "
        "and the tile source",
        "Run `fitdocs regen` once to bring existing workout pages current",
    ],
    ids=["region", "ownership", "pass", "rederivability", "action"],
)
def test_current_change_paragraph_states_workout_wellness(phrase: str) -> None:
    head = _flat(_DOC.read_text(encoding="utf-8").split("\n\nThis document", 1)[0])
    assert phrase in head


@pytest.mark.parametrize(
    "phrase",
    [
        "the data root gains an owned location",
        "``recovery/`` holds the recovery page ``recovery/recovery.md``",
        "charts under ``recovery/assets/``",
        "written by ``fitdocs recovery`` from the wellness series and the "
        "workout documents",
        "rewritten only when their content changes",
        "a chart the page no longer shows is removed",
        "Run ``fitdocs sync``, ``fitdocs regen``, ``fitdocs history`` or "
        "``fitdocs recovery``",
        "once to place ``recovery/AGENTS.md``",
    ],
    ids=[
        "location",
        "page",
        "charts",
        "inputs",
        "rewrites",
        "removal",
        "commands",
        "declaration",
    ],
)
def test_version_history_retains_recovery_change_paragraph(phrase: str) -> None:
    assert phrase in _contract_version_history()


def test_the_version_history_records_the_amendment() -> None:
    history = _contract_version_history()
    assert "Raised from ``13`` to ``14`` by recovery" in history
    assert "Raised from ``9`` to ``10`` by dashboards" in history
    assert "Dashboard chart regions and assets are the only document content" in history
    assert "Raised from ``10`` to ``11`` by wellness-store" in history
    assert "``wellness-archive/`` keeps every wellness file fitdocs handled" in history
    assert "Raised from ``7`` to ``8`` by activity-identity Amendment 1" in history
    assert "Elapsed time is compared only when a distance is missing." in history
    assert "Raised from ``8`` to ``9`` by analytics-index" in history
    assert (
        "The rule that decides whether two files are one workout no longer compares "
        "elapsed times when both files record a distance."
    ) in history
    assert (
        "``DISTANCE_TOLERANCE_FRACTION`` of the longer distance apart, "
        "whichever is larger"
    ) in history
    assert (
        "When a distance is missing, elapsed times are compared as before." in history
    )
    assert (
        "Run ``fitdocs check`` to see pages that the rule now recognizes as one "
        "workout."
    ) in history
    for phrase in (
        "the data root gains two owned locations",
        "``wellness/`` holds the normalized daily series",
        "one CSV file per year and ``manifest.toml``",
        "Run ``fitdocs sync`` or ``fitdocs regen`` once to place "
        "``wellness/AGENTS.md``",
        "``wellness-archive/AGENTS.md``",
    ):
        assert phrase in history, phrase
    assert "Raised from ``11`` to ``12`` by wellness-pull" in history
    assert (
        "A connector's ledger that holds wellness records is ledger format 2."
        in history
    )
    assert (
        "Raised from ``12`` to ``13`` by hr-derivation because ``derive-benchmarks`` "
        "now also reads every workout's listed files and the normalized wellness "
        "series and may write ``athlete.toml`` at most once per stage."
    ) in history

    assert "Raised from ``14`` to ``15`` by workout-wellness." in history
    assert (
        "Workout documents gain the ``morning`` region, a third region class "
        "whose content fitdocs alone writes from the wellness series and "
        "replaces whenever it differs; the morning-of pass that ``fitdocs "
        "sync``, ``fitdocs pull --sync`` and ``fitdocs regen`` run rewrites only "
        "that region; and a workout document's generated content is re-derivable "
        "from the wellness series as well as from the archived sources, the "
        "athlete profile, the configured timezone and the tile source."
    ) in history


def test_the_unreleased_entry_states_the_rule_and_the_actions() -> None:
    changelog = read_unreleased_since(_DOC.parents[1] / "CHANGELOG.md", V0_1_0)
    unreleased = changelog.split("## [Unreleased]", 1)[1].split("\n## [", 1)[0]
    entries = [
        _flat(e) for e in unreleased.split("\n- ") if "DISTANCE" in e or "20 %" in e
    ]
    assert len(entries) == 1, len(entries)
    entry = entries[0]
    for phrase in (
        "two files of the same sport whose starts are no more than 1 s apart",
        "5 m or 20 % of the longer distance apart, whichever is larger",
        "Elapsed time is compared only when a distance is missing.",
        "The ownership contract's version advances.",
        "run `fitdocs check`",
        "deleting one of its pages (move anything worth keeping out of its "
        "notes first) and running `fitdocs regen`",
    ):
        assert phrase in entry, phrase
