"""Conformance test for ``docs/compatibility.md`` (design: CompatibilityPolicy,
Req 3.1-3.10, 6.6).

This is a documentation guard, not a behavioural test: the policy's *prose*
is the deliverable, so the assertions here pin structure and required
vocabulary rather than a computed result. Each check is designed to fail
under a plausible drift -- a renamed heading, a dropped module name, a
restored duplicate compatibility statement in ``docs/plugins.md``, a broken
link, or a policy that silently disagrees with the CLI's own data-root
posture rule.
"""

from __future__ import annotations

import importlib
import re
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[1]
_POLICY_PATH = _REPO_ROOT / "docs" / "compatibility.md"
_PLUGINS_DOC_PATH = _REPO_ROOT / "docs" / "plugins.md"

# Fixed order -- this becomes the expected heading tuple. Each entry is the
# exact ATX heading text `docs/compatibility.md` must carry, in this order.
EXPECTED_HEADINGS: tuple[str, ...] = (
    "## The governed contracts",
    "## Breaking, additive and internal",
    "## Version numbering",
    "## Internal versions and what they cost you",
    "## Deprecation",
    "## The compatible-upgrade guarantee",
    "## Public versus internal",
    "## Which commands need a data root",
)

# The internal modules 3.9 requires the policy to name, plus the built-in
# calculator's class -- confirmed importable below as a positive control
# (an assertion that these are real modules, not merely strings the doc
# happens to spell correctly).
INTERNAL_MODULES: tuple[str, ...] = (
    "fitdocs.contract",
    "fitdocs.inbox",
    "fitdocs.plugins",
    "fitdocs.version",
    "fitdocs.agentskill",
    "fitdocs.layout",
    "fitdocs.settings",
)

BUILT_IN_CALCULATOR_CLASS = "ThresholdCalculator"

# The data-root-posture phrase the CLI module docstring and the policy must
# share verbatim (design 3.10: "cli.py's module docstring carries the same
# rule in code").
_SHARED_DATA_ROOT_PHRASE = (
    "a command that describes a tree requires a data root; a command that "
    "describes the installed tool does not"
)

# A phrase distinctive to this policy alone -- used as the positive control
# proving `docs/plugins.md` carries no second, competing compatibility
# statement.
_DISTINCTIVE_POLICY_PHRASE = "two minor releases"

_OLD_PLUGINS_PHRASE = "carries no backward-compatibility obligation"


def _read(path: Path) -> str:
    assert path.is_file(), f"expected {path} to exist"
    return path.read_text(encoding="utf-8")


def _headings(markdown: str) -> list[str]:
    return [
        line.strip()
        for line in markdown.splitlines()
        if re.match(r"^#{1,6}\s+\S", line)
    ]


def _section(markdown: str, heading: str) -> str:
    """Return the body of the section headed exactly ``heading`` (up to the
    next heading of the same or shallower level)."""
    lines = markdown.splitlines()
    level = len(heading) - len(heading.lstrip("#"))
    start = None
    for i, line in enumerate(lines):
        if line.strip() == heading:
            start = i + 1
            break
    assert start is not None, f"heading {heading!r} not found"
    end = len(lines)
    for i in range(start, len(lines)):
        stripped = lines[i].strip()
        match = re.match(r"^(#{1,6})\s+\S", stripped)
        if match and len(match.group(1)) <= level:
            end = i
            break
    return "\n".join(lines[start:end])


def _markdown_links(markdown: str) -> list[str]:
    """Every inline-link target ``[text](target)`` in ``markdown``, excluding
    absolute URLs (``http://``/``https://``) and bare in-page anchors."""
    targets = re.findall(r"\]\(([^)]+)\)", markdown)
    return [
        t
        for t in targets
        if not t.startswith(("http://", "https://")) and not t.startswith("#")
    ]


def test_positive_control_internal_modules_and_calculator_class_are_real() -> None:
    """Every module 3.9 requires the policy to name as internal actually
    exists and imports -- otherwise the string-presence checks below would
    be pinning typos, not modules."""
    for module in INTERNAL_MODULES:
        importlib.import_module(module)

    calc_module = importlib.import_module("fitdocs.load.threshold.calculator")
    assert hasattr(calc_module, BUILT_IN_CALCULATOR_CLASS)


def test_policy_heading_order_matches_the_fixed_sequence() -> None:
    markdown = _read(_POLICY_PATH)
    headings = [h for h in _headings(markdown) if h.startswith("## ")]
    # Positive control: a vacuous walk (empty file, or a heading regex that
    # matches nothing) must not pass silently.
    assert len(headings) >= 8, (
        f"expected at least 8 top-level headings, found {headings}"
    )
    assert headings == list(EXPECTED_HEADINGS)


SETTINGS_TABLE_LITERALS: tuple[str, ...] = (
    "[tiles]",
    "[inbox]",
    "[plugins]",
    "[load]",
    "[plans]",
    "[history]",
)


def _numbered_list_items(section: str) -> list[str]:
    """The governed-contracts numbered list, as a list of item bodies.

    Bounded to the contiguous ``1. ...`` through the next blank line, so a
    later unrelated paragraph containing the word "settings" (e.g.
    "Documented means public") is never mistaken for a fifth list item.
    """
    match = re.search(r"(?ms)^(1\.\s.*?)\n\n", section)
    assert match is not None, "no numbered list found in governed-contracts section"
    block = match.group(1)
    items = re.split(r"(?m)^(?=\d+\.\s)", block)
    return [i.strip() for i in items if i.strip()]


def test_governed_contracts_section_names_the_three_contracts_and_settings() -> None:
    markdown = _read(_POLICY_PATH)
    section = _section(markdown, "## The governed contracts")
    items = _numbered_list_items(section)
    # Positive control: the numbered-list walk must actually find all four
    # items, or "exactly one names settings" below could pass vacuously
    # with a shrunken or absent list.
    assert len(items) == 4, f"expected 4 numbered contract items, found {len(items)}"

    for label in ("document", "ownership", "inbox", "plugin"):
        assert any(label in item.lower() for item in items), (
            f"expected a governed-contracts item naming {label!r}"
        )

    # "settings" is otherwise an ever-present token (item 2 used to say
    # "[inbox] settings table"), so this must be scoped to the ONE item that
    # names the settings schema as a governed contract, and that item alone
    # must name `fitdocs.toml` and every one of its six tables -- deleting
    # the whole item, or leaving only some of the six tables, must both red.
    settings_items = [item for item in items if "settings" in item.lower()]
    assert len(settings_items) == 1, (
        f"expected exactly one item naming the settings schema, "
        f"found {len(settings_items)}"
    )
    settings_item = settings_items[0]
    assert "fitdocs.toml" in settings_item
    for literal in SETTINGS_TABLE_LITERALS:
        assert literal in settings_item, (
            f"expected {literal!r} named in the settings-schema governed-contracts item"
        )


def _bold_led_subsections(section: str) -> list[str]:
    """Split a section body into paragraphs, each starting with a bold
    ``**Lead-in.**`` marker -- the per-contract subsection convention this
    policy uses inside "Breaking, additive and internal". Splitting on the
    marker (rather than treating the whole section as one blob) is what lets
    a per-contract assertion actually discriminate: dropping a word from one
    subsection must not be masked by its presence in a sibling subsection.
    """
    # A bold lead-in starts a new paragraph: "**...**." at the start of a line.
    pieces = re.split(r"(?m)^(?=\*\*[^*]+\*\*)", section.strip())
    return [p for p in pieces if p.strip()]


# Per-contract distinctive tokens: a phrase that belongs to THIS contract's
# definition and no other's, so a definition swapped between two contracts
# (same vocabulary, wrong subject) still reds instead of passing on the
# strength of the words "breaking"/"additive"/"internal" alone.
_DISTINCTIVE_SUBSECTION_TOKEN: dict[str, str] = {
    "document": "frontmatter",
    "inbox": "disposition guarantee",
    "plugin": "entry-point discovery group",
    "settings": "shared loader",
}


@pytest.mark.parametrize(
    "contract_label",
    ["document", "inbox", "plugin", "settings"],
)
def test_each_contract_subsection_defines_breaking_additive_and_internal(
    contract_label: str,
) -> None:
    markdown = _read(_POLICY_PATH)
    section = _section(markdown, "## Breaking, additive and internal")
    subsections = _bold_led_subsections(section)
    # Positive control: the split must actually find the four subsections,
    # or a regex that matches nothing would let every per-contract assertion
    # below pass vacuously (no subsection => the "matching" one below via
    # next() would raise, not silently pass -- but confirm the count anyway).
    assert len(subsections) == 4, (
        f"expected 4 contract subsections, found {len(subsections)}"
    )

    # Match on the bold LEAD-IN only (e.g. "The document and ownership
    # contract."), never the whole subsection body -- otherwise an unrelated
    # subsection whose prose happens to contain the word (the plugin
    # subsection says "a documented public name") would count as a match
    # too, and "expected exactly one" would never discriminate.
    leads = [(s, re.match(r"^\*\*(.*?)\*\*", s)) for s in subsections]
    matching = [
        s for s, lead in leads if lead and contract_label in lead.group(1).lower()
    ]
    assert len(matching) == 1, (
        f"expected exactly one subsection naming {contract_label!r}, "
        f"found {len(matching)}"
    )
    subsection = matching[0].lower()
    assert "breaking" in subsection
    assert "additive" in subsection
    assert "internal" in subsection

    # A distinctive phrase belonging to this contract alone, and to no
    # sibling subsection -- catches a definition swapped between two
    # contracts, which the bare breaking/additive/internal words above
    # would not.
    distinctive = _DISTINCTIVE_SUBSECTION_TOKEN[contract_label]
    assert distinctive in subsection, (
        f"expected {contract_label!r} subsection to carry {distinctive!r}"
    )
    others = [s for s in subsections if s not in matching]
    for other in others:
        assert distinctive not in other.lower(), (
            f"{distinctive!r} is not actually distinctive -- also found in a "
            "sibling subsection"
        )


def test_settings_schema_subsection_names_all_six_tables() -> None:
    markdown = _read(_POLICY_PATH)
    section = _section(markdown, "## Breaking, additive and internal")
    subsections = _bold_led_subsections(section)
    matching = [s for s in subsections if "settings" in s.lower()]
    assert len(matching) == 1, (
        f"expected exactly one settings-schema subsection, found {len(matching)}"
    )
    subsection = matching[0]
    for literal in SETTINGS_TABLE_LITERALS:
        assert literal in subsection, (
            f"the tile/inbox/plugin/load/plans/history tables must all be "
            f"named as governed, not left implicit -- missing {literal!r}"
        )


def test_version_numbering_section_states_the_1_0_boundary() -> None:
    markdown = _read(_POLICY_PATH)
    section = _section(markdown, "## Version numbering")
    assert "1.0" in section


def test_version_numbering_section_states_the_pre_and_post_1_0_regimes() -> None:
    markdown = _read(_POLICY_PATH)
    section = _section(markdown, "## Version numbering").lower()
    assert "0.x" in section or "before the first stable release" in section
    assert "semantic versioning" in section


def test_governed_contracts_section_states_documented_means_public() -> None:
    markdown = _read(_POLICY_PATH)
    section = _section(markdown, "## The governed contracts")
    assert "documented means public" in section.lower()


def _dash_led_bullets(section: str) -> list[str]:
    """Split a section body into its top-level ``- `` bulleted items,
    dropping any leading prose paragraph that precedes the first bullet."""
    stripped = section.strip()
    first_bullet = re.search(r"(?m)^-\s", stripped)
    assert first_bullet is not None, "no bulleted list found in section"
    stripped = stripped[first_bullet.start() :]
    pieces = re.split(r"(?m)^(?=-\s)", stripped)
    return [p.strip() for p in pieces if p.strip()]


def test_internal_versions_section_names_each_mapping() -> None:
    markdown = _read(_POLICY_PATH)
    section = _section(markdown, "## Internal versions and what they cost you")
    bullets = _dash_led_bullets(section)
    # Positive control: the bullet split must find all four mappings.
    assert len(bullets) == 4, (
        f"expected 4 internal-version bullets, found {len(bullets)}"
    )

    doc_version_bullet = next(b for b in bullets if "document-format" in b.lower())
    assert "fitdocs regen" in doc_version_bullet

    contract_version_bullet = next(
        b for b in bullets if "ownership-contract version" in b.lower()
    )
    assert "costs the user nothing" in contract_version_bullet.lower()

    settings_bullet = next(b for b in bullets if "settings-schema change" in b.lower())
    assert "breaking" in settings_bullet.lower()

    calculator_bullet = next(b for b in bullets if "built-in calculator" in b.lower())
    assert "contract change" in calculator_bullet.lower()


def test_public_versus_internal_section_links_the_enumerated_surface_anchor() -> None:
    markdown = _read(_POLICY_PATH)
    section = _section(markdown, "## Public versus internal")
    assert "the-public-import-surface" in section


def test_data_root_section_names_the_cli_module() -> None:
    markdown = _read(_POLICY_PATH)
    section = _section(markdown, "## Which commands need a data root")
    assert "fitdocs.cli" in section


def test_deprecation_section_states_the_window_and_forbids_patch_removal() -> None:
    markdown = _read(_POLICY_PATH)
    section = _section(markdown, "## Deprecation").lower()
    assert "two minor releases" in section
    assert "changelog" in section
    # "patch" alone is an ever-present token: "may be removed in a patch"
    # and "see the release notes" would both still contain a bare "patch"
    # or a synonym-adjacent word, so this pins the actual POLARITY of the
    # rule, not merely the word.
    assert "never removed in a patch" in section


def test_upgrade_guarantee_names_settings_file_profile_and_local_plugin() -> None:
    markdown = _read(_POLICY_PATH)
    section = _section(markdown, "## The compatible-upgrade guarantee").lower()
    assert "settings" in section
    assert "athlete profile" in section
    assert "local plugin" in section


def test_public_versus_internal_section_names_every_internal_module() -> None:
    markdown = _read(_POLICY_PATH)
    section = _section(markdown, "## Public versus internal")
    for module in INTERNAL_MODULES:
        assert module in section, f"expected {module!r} named as internal"
    assert BUILT_IN_CALCULATOR_CLASS in section


def test_data_root_section_names_the_three_commands() -> None:
    markdown = _read(_POLICY_PATH)
    section = _section(markdown, "## Which commands need a data root")
    for command in ("skill", "plugins", "check"):
        assert command in section


def test_data_root_section_shares_the_exact_cli_docstring_phrase() -> None:
    """The policy and `fitdocs.cli`'s module docstring must agree on the
    data-root rule using the SAME sentence, not a paraphrase -- so the two
    cannot silently drift apart (design 3.10)."""
    import fitdocs.cli as cli_module

    markdown = _read(_POLICY_PATH)
    section = _section(markdown, "## Which commands need a data root")

    assert cli_module.__doc__ is not None
    cli_doc = " ".join(cli_module.__doc__.split())
    policy_text = " ".join(section.split())

    assert _SHARED_DATA_ROOT_PHRASE in cli_doc, (
        "fixture assumption: cli.py's own docstring changed"
    )
    assert _SHARED_DATA_ROOT_PHRASE in policy_text


def test_plugins_doc_compatibility_section_points_at_the_policy_only() -> None:
    markdown = _read(_PLUGINS_DOC_PATH)
    section = _section(markdown, "## Compatibility policy")
    assert "compatibility.md" in section
    assert _OLD_PLUGINS_PHRASE not in section


def test_only_the_policy_carries_the_distinctive_compatibility_phrase() -> None:
    """Positive control for the previous test: `docs/compatibility.md` is the
    only file under `docs/` or the README whose text contains a phrase
    distinctive to this policy. If `docs/plugins.md` regained its own
    duplicate compatibility paragraph, this catches it even if the paragraph
    used different wording than `_OLD_PLUGINS_PHRASE`."""
    doc_paths = [_REPO_ROOT / "README.md", *sorted((_REPO_ROOT / "docs").rglob("*.md"))]
    doc_paths = [p for p in doc_paths if p.is_file()]
    assert len(doc_paths) >= 2, (
        "the documentation set is too small for this control to mean anything"
    )

    carriers = [
        p
        for p in doc_paths
        if _DISTINCTIVE_POLICY_PHRASE in p.read_text(encoding="utf-8")
    ]
    assert carriers == [_POLICY_PATH]


def test_every_relative_link_in_the_policy_resolves_to_an_existing_file() -> None:
    markdown = _read(_POLICY_PATH)
    links = _markdown_links(markdown)
    # Positive control -- a link-regex change that matches nothing must not
    # pass silently.
    assert len(links) >= 3, f"expected at least 3 relative links, found {links}"

    for target in links:
        path_part = target.split("#", 1)[0]
        if not path_part:
            continue  # pure in-page anchor form, e.g. "other.md#x" already handled
        resolved = (_POLICY_PATH.parent / path_part).resolve()
        assert resolved.is_file(), f"broken link target: {target} -> {resolved}"
