"""Conformance for task 5.3: the upgrade and uninstall documentation
(design.md "UpgradeDocs", ``docs/upgrading.md`` summary bullet, "Doc
references leave the repository -> docs cross-link repo-relatively",
``docs/compatibility.md`` "The compatible-upgrade guarantee"; Req 3.5, 7.3,
7.4, 7.5, 7.6).

Eight properties, one per test group below:

(a) the fixed H2 heading order (>= 6 headings found -- a vacuous walk over
    zero headings would pass the tuple-equality check by accident only if
    the fixed tuple were itself empty, which it is not).
(b) the ``Upgrade commands`` section carries both upgrade commands verbatim,
    and the ``Uninstalling`` section carries both uninstall commands
    verbatim -- checked *per section*, so a command misplaced into the wrong
    section fails even though the whole-document search would still find it.
(c) the "what an upgrade does not touch" section names each of the five
    categories as its own list item, deriving the expected token for four of
    them from the real code constants (``fitdocs.layout.SETTINGS_FILE``,
    ``fitdocs.athlete.ATHLETE_FILE``, ``fitdocs.layout.ARCHIVE_DIR``) so a
    rename reds this test rather than leaving a stale literal in the doc --
    plus a *distinctness* check: each list item matches exactly one category
    token and the five items' matched tokens union to the full set, so five
    copies of one catch-all bullet (which independently satisfies every
    "some item contains this token" check) is caught, and so is a fixture
    that merges two categories' text into a single bullet.
(d) the regen section names exactly one ``fitdocs <command>`` inside a fenced
    code block (``fitdocs regen``) and states the "nothing else is required"
    polarity -- not merely the word "regen" -- and does not carry a second
    fenced ``fitdocs`` command.
(e) the "what remains after uninstalling" section asserts the
    where-the-tool-writes property (not an installer-behavior claim), and its
    list names each of Req 7.6's four categories (generated documents,
    archived sources, settings, profile) via the real code constants, plus
    the pointer file, plus the configured-inbox/processed-directory
    exception -- again with the distinctness check above, so collapsing the
    list to "your data root in full" is caught rather than accidentally
    satisfied by a substring match somewhere in the section's prose.
(f) the compatible-upgrade-guarantee section links
    ``compatibility.md#the-compatible-upgrade-guarantee`` *as the link's
    href*, not merely somewhere in the section's text (a bad href behind a
    correctly-worded label must still fail), and that slug is a real heading
    in ``docs/compatibility.md``.
(g) every relative markdown link inside ``docs/upgrading.md`` resolves to a
    file that exists on disk, and every in-page ``#anchor`` link resolves to
    a real heading slug on the page itself.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from fitdocs.athlete import ATHLETE_FILE
from fitdocs.config import POINTER_RELPATH
from fitdocs.layout import (
    ARCHIVE_DIR,
    BLOCKS_DIR,
    HISTORY_DIR,
    SETTINGS_FILE,
    WORKOUTS_DIR,
)
from tests.test_docs_guarantees import _heading_slugs

_REPO_ROOT = Path(__file__).resolve().parent.parent
_UPGRADING = _REPO_ROOT / "docs" / "upgrading.md"

_UV_UPGRADE = "uv tool upgrade fitdocs"
_UV_UNINSTALL = "uv tool uninstall fitdocs"
_PIPX_UPGRADE = "pipx upgrade fitdocs"
_PIPX_UNINSTALL = "pipx uninstall fitdocs"

#: The fixed H2 order the doc must carry, in this exact sequence.
_EXPECTED_H2_ORDER = (
    "Upgrade commands",
    "What an upgrade does not touch",
    "When a release moves the document format",
    "Uninstalling",
    "What remains on disk after uninstalling",
    "The compatible-upgrade guarantee",
)


def _text() -> str:
    assert _UPGRADING.is_file(), f"{_UPGRADING} does not exist"
    return _UPGRADING.read_text(encoding="utf-8")


def _h2_headings(text: str) -> list[str]:
    """Every ATX H2 heading line, skipping fenced code blocks (a shell
    comment such as ``## upgrade`` inside an example would otherwise be
    indistinguishable from a real heading)."""
    headings = []
    in_fence = False
    for line in text.splitlines():
        if line.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        if line.startswith("## ") and not line.startswith("### "):
            headings.append(line[len("## ") :].strip())
    return headings


def _section(text: str, heading: str) -> str:
    """The body of the H2 section named *heading*, up to (not including)
    the next H2 heading."""
    marker = f"## {heading}"
    start = text.index(marker)
    body_start = start + len(marker)
    rest = text[body_start:]
    next_h2 = re.search(r"^## ", rest, re.M)
    end = body_start + (next_h2.start() if next_h2 else len(rest))
    return text[body_start:end]


def _fenced_blocks(text: str) -> list[str]:
    return re.findall(r"```[^\n]*\n(.*?)```", text, re.S)


def _list_items(section: str) -> list[str]:
    return [
        line.strip() for line in section.splitlines() if line.strip().startswith("-")
    ]


def _assert_distinct_categories(
    items: list[str], tokens: tuple[str, ...], section_name: str
) -> None:
    """Each item in *items* must match exactly one of *tokens*, and the
    tokens matched across all items must union to the full set.

    This is the check a plain "some item contains token X" search cannot
    make: N copies of one bullet naming every token satisfies every
    per-token search individually while carrying only one real category, and
    a bullet that merges two categories' text satisfies both per-token
    searches while collapsing two categories into one item. Both are caught
    here because each item's matched-token *count* must be exactly one.
    """
    matched_per_item = [{tok for tok in tokens if tok in item} for item in items]
    for item, matched in zip(items, matched_per_item, strict=True):
        assert len(matched) == 1, (
            f"{section_name!r} list item matches {len(matched)} categories "
            f"(expected exactly 1): {item!r} -> {sorted(matched)}"
        )
    all_matched: set[str] = set()
    for matched in matched_per_item:
        all_matched |= matched
    assert all_matched == set(tokens), (
        f"{section_name!r} list items collectively name {sorted(all_matched)}, "
        f"expected exactly {sorted(tokens)}"
    )


# --- (a) fixed heading order -------------------------------------------------


def test_heading_order_is_the_fixed_tuple() -> None:
    headings = _h2_headings(_text())
    # Positive control: the fixed tuple itself must be non-trivial, or an
    # empty-vs-empty comparison below would pass having found nothing.
    assert len(_EXPECTED_H2_ORDER) >= 6
    assert headings == list(_EXPECTED_H2_ORDER), (
        f"docs/upgrading.md's H2 heading order is {headings}, expected "
        f"{list(_EXPECTED_H2_ORDER)}"
    )


# --- (b) the four exact command strings, scoped per section -----------------


def test_upgrade_commands_section_carries_both_upgrade_commands() -> None:
    section = _section(_text(), "Upgrade commands")
    assert _UV_UPGRADE in section
    assert _PIPX_UPGRADE in section
    # The uninstall commands belong in the Uninstalling section, not here.
    assert _UV_UNINSTALL not in section
    assert _PIPX_UNINSTALL not in section


def test_uninstalling_section_carries_both_uninstall_commands() -> None:
    section = _section(_text(), "Uninstalling")
    assert _UV_UNINSTALL in section
    assert _PIPX_UNINSTALL in section
    # The upgrade commands belong in the Upgrade commands section, not here.
    assert _UV_UPGRADE not in section
    assert _PIPX_UPGRADE not in section


# --- (c) the five not-touched categories, four derived from real code -------

_NOT_TOUCHED_SECTION = "What an upgrade does not touch"

_NOT_TOUCHED_TOKENS = (
    "user-owned",  # user-owned document regions -- category 1
    SETTINGS_FILE,  # fitdocs.toml -- category 2
    ATHLETE_FILE,  # athlete.toml -- category 3
    "plugin",  # local plugin files -- category 4
    ARCHIVE_DIR,  # fit-archive -- category 5
)


@pytest.mark.parametrize("expected_token", _NOT_TOUCHED_TOKENS)
def test_not_touched_section_names_each_category_as_its_own_list_item(
    expected_token: str,
) -> None:
    section = _section(_text(), _NOT_TOUCHED_SECTION)
    items = _list_items(section)
    # Positive control: the walk must find list items at all.
    assert len(items) >= 5, (
        f"{_NOT_TOUCHED_SECTION!r} section has fewer than 5 list items: {items}"
    )
    matching = [item for item in items if expected_token in item]
    assert matching, (
        f"no list item in {_NOT_TOUCHED_SECTION!r} names the token "
        f"{expected_token!r}: {items}"
    )


def test_not_touched_section_items_are_distinct_categories() -> None:
    """Distinctness guard: matching *some* item per token (the parametrized
    test above) does not prove the five categories occupy five *distinct*
    items. Confirmed by mutation: five copies of one bullet naming all five
    tokens passes every parametrized case above, and a bullet merging two
    categories' text passes both of their per-token searches. Both are
    caught here because each item must match exactly one token, and the
    matched tokens across all items must union to the full set -- which also
    pins the count at exactly 5."""
    section = _section(_text(), _NOT_TOUCHED_SECTION)
    items = _list_items(section)
    assert len(items) == 5, (
        f"expected exactly 5 list items in {_NOT_TOUCHED_SECTION!r}, got "
        f"{len(items)}: {items}"
    )
    _assert_distinct_categories(items, _NOT_TOUCHED_TOKENS, _NOT_TOUCHED_SECTION)


# --- (d) the regen section: exactly one fenced fitdocs command, and polarity


def test_regen_section_names_exactly_one_fenced_fitdocs_command() -> None:
    section = _section(_text(), "When a release moves the document format")
    fenced = _fenced_blocks(section)
    fitdocs_commands = {
        line.strip()
        for block in fenced
        for line in block.splitlines()
        if line.strip().startswith("fitdocs ")
    }
    assert fitdocs_commands == {"fitdocs regen"}, (
        f"expected exactly one fenced fitdocs command, 'fitdocs regen', "
        f"got {fitdocs_commands}"
    )


def test_regen_section_states_nothing_else_is_required_polarity() -> None:
    section = _section(_text(), "When a release moves the document format").lower()
    normalized = re.sub(r"\s+", " ", section)
    assert re.search(r"no other action|nothing else is required", normalized), (
        "the regen section does not state the 'no other action needed' "
        "polarity -- merely naming 'regen' is not this assertion"
    )
    # Falsity-in-starting-state / discrimination companion: the wrong-polarity
    # phrasing must NOT itself already be present (guards against a doc that
    # states the opposite and still matches a too-loose regex).
    assert "you may also need to" not in normalized


# --- (e) what remains: where-the-tool-writes property, four Req 7.6 --------
# --- categories via real constants, plus the pointer file and the ----------
# --- configured-inbox exception, each its own distinct list item -----------

_REMAINS_SECTION = "What remains on disk after uninstalling"

#: One token per required item: the four Req 7.6 categories (generated
#: documents -- represented by all three owned document directories, so the
#: category is only satisfied when the item names every one of them --
#: archived sources, settings file, athlete profile), the pointer file, and
#: the configured-inbox/processed-directory exception. Every token except
#: the last two is read from the real code constant it names, so a rename
#: reds this test instead of leaving a stale literal in the doc.
_GENERATED_DOCS_TOKEN = f"{WORKOUTS_DIR}\0{HISTORY_DIR}\0{BLOCKS_DIR}"
_REMAINS_TOKENS = (
    _GENERATED_DOCS_TOKEN,
    ARCHIVE_DIR,
    SETTINGS_FILE,
    ATHLETE_FILE,
    POINTER_RELPATH,
    "inbox\0processed",
)


def _remains_token_in_item(token: str, item: str) -> bool:
    """A composite token (parts joined by ``\\0``) matches an item only when
    *every* part is present -- used for the "generated documents" category
    (all three directory names) and the "configured inbox" category (both
    "inbox" and "processed"), so a bullet naming only one of the required
    parts does not falsely satisfy the whole category."""
    return all(part in item for part in token.split("\0"))


@pytest.mark.parametrize(
    "expected_token",
    _REMAINS_TOKENS,
    ids=[
        "generated_documents",
        "archived_sources",
        "settings_file",
        "athlete_profile",
        "pointer_file",
        "configured_inbox",
    ],
)
def test_remains_section_names_each_required_category_as_its_own_list_item(
    expected_token: str,
) -> None:
    section = _section(_text(), _REMAINS_SECTION)
    items = _list_items(section)
    assert len(items) >= 6, (
        f"{_REMAINS_SECTION!r} section has fewer than 6 list items: {items}"
    )
    matching = [item for item in items if _remains_token_in_item(expected_token, item)]
    assert matching, (
        f"no list item in {_REMAINS_SECTION!r} names the required category "
        f"{expected_token!r}: {items}"
    )


def test_remains_section_items_are_distinct_categories() -> None:
    """Distinctness guard, same shape as the not-touched section's: reducing
    the list to a single "your data root in full" item (confirmed by
    mutation) must fail here even though a whole-section substring search
    for "data root" would still pass."""
    section = _section(_text(), _REMAINS_SECTION)
    items = _list_items(section)
    assert len(items) == 6, (
        f"expected exactly 6 list items in {_REMAINS_SECTION!r}, got "
        f"{len(items)}: {items}"
    )
    matched_per_item = [
        {tok for tok in _REMAINS_TOKENS if _remains_token_in_item(tok, item)}
        for item in items
    ]
    for item, matched in zip(items, matched_per_item, strict=True):
        assert len(matched) == 1, (
            f"{_REMAINS_SECTION!r} list item matches {len(matched)} "
            f"categories (expected exactly 1): {item!r} -> {sorted(matched)}"
        )
    all_matched: set[str] = set()
    for matched in matched_per_item:
        all_matched |= matched
    assert all_matched == set(_REMAINS_TOKENS), (
        f"{_REMAINS_SECTION!r} list items collectively name "
        f"{sorted(all_matched)}, expected exactly {sorted(_REMAINS_TOKENS)}"
    )


def test_remains_section_states_where_the_tool_writes_property() -> None:
    section = _section(_text(), _REMAINS_SECTION).lower()
    normalized = re.sub(r"\s+", " ", section)
    assert re.search(r"fitdocs writes only (under|to|into)", normalized), (
        "the remains section does not state the property as where the tool "
        "writes, rather than as a claim about what an installer removes"
    )
    assert "data root" in normalized
    assert "pointer file" in normalized


# --- (f) the compatible-upgrade-guarantee link resolves to a real heading --


def test_compatible_upgrade_guarantee_links_a_real_heading_in_compatibility_md() -> (
    None
):
    section = _section(_text(), "The compatible-upgrade guarantee")
    # Match the link's HREF specifically -- ``[label](href)`` -- not merely
    # the string "compatibility.md#..." anywhere in the section, which would
    # also match inside the visible link *label* even when the href behind
    # it is broken.
    match = re.search(r"\]\(compatibility\.md#([\w-]+)\)", section)
    assert match is not None, (
        "the compatible-upgrade-guarantee section has no markdown link whose "
        "href is compatibility.md#<anchor>"
    )
    slug = match.group(1)
    compat_text = (_REPO_ROOT / "docs" / "compatibility.md").read_text(encoding="utf-8")
    real_slugs = _heading_slugs(compat_text)
    # Positive control: the walk over compatibility.md must find headings.
    assert real_slugs, "docs/compatibility.md has no headings -- the walk found none"
    assert slug in real_slugs, (
        f"docs/upgrading.md links compatibility.md#{slug}, but no heading in "
        f"docs/compatibility.md produces that anchor slug (real slugs: "
        f"{sorted(real_slugs)})"
    )
    assert slug == "the-compatible-upgrade-guarantee"


# --- (g) every relative link, and every in-page anchor, resolves -----------


def test_every_relative_link_in_upgrading_doc_resolves() -> None:
    text = _text()
    targets = re.findall(r"\]\(([^)]+)\)", text)
    relative = [t for t in targets if not t.startswith(("http://", "https://", "#"))]
    # Positive control: docs/upgrading.md must actually link at least one
    # sibling page, or this walk checks nothing.
    assert relative, "docs/upgrading.md carries no relative links to check"
    for target in relative:
        path_part = target.split("#", 1)[0]
        resolved = (_UPGRADING.parent / path_part).resolve()
        assert resolved.is_file(), (
            f"docs/upgrading.md links {target!r}, which resolves to "
            f"{resolved}, a file that does not exist"
        )


def test_every_in_page_anchor_in_upgrading_doc_resolves() -> None:
    text = _text()
    own_slugs = _heading_slugs(text)
    anchors = re.findall(r"\]\(#([\w-]+)\)", text)
    # Positive control: the page must actually carry at least one same-page
    # anchor link, or this walk checks nothing.
    assert anchors, "docs/upgrading.md carries no in-page #anchor links to check"
    missing = [a for a in anchors if a not in own_slugs]
    assert not missing, (
        f"docs/upgrading.md links in-page anchor(s) {missing} that match no "
        f"heading on the page (real slugs: {sorted(own_slugs)})"
    )
