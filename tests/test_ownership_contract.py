"""Conformance test for `docs/ownership-contract.md` (design: ContractDocs).

The published ownership contract is the authoritative, user-facing statement
of what fitdocs owns. This test does not check prose quality -- it checks
that the document's *enumerable* claims (owned paths, preserved region ids,
managed frontmatter keys, contract version) agree exactly with the code that
implements them, so the document can never drift from behavior without a
test failing (design's ContractDocs "Observable").

Set equality, not subset (wiki-contract Req 2.1, 2.10, 6.4, 7.4): a test that
only asserts "every real path/key/region appears somewhere in the document"
would still pass if the document additionally claimed ownership of a path it
does not own -- the dangerous direction, since a user or an LLM agent reading
the document would then believe fitdocs writes somewhere it does not. Every
list this test parses is asserted equal, as a set, to the corresponding
code-level constant.

The configured-location clause (Req 2.10) is checked for presence as prose,
and explicitly checked *not* to be an enumerated list item under the Owned
Paths heading -- listing a configured location there would falsely widen the
owned-path set and would also break the set-equality assertion above the
moment a real inbox intake path was added to fixtures.
"""

from __future__ import annotations

import re
from pathlib import Path

from fitdocs import contract, layout

_DOC_PATH = Path(__file__).resolve().parent.parent / "docs" / "ownership-contract.md"


def _read_doc() -> str:
    return _DOC_PATH.read_text(encoding="utf-8")


def _section(text: str, heading: str) -> str:
    """The body of the markdown section titled exactly ``heading``.

    ``heading`` is matched as a line starting with one or more ``#`` followed
    by the given text. The section runs until the next heading line of the
    same or shallower level, or end of document.
    """
    pattern = re.compile(
        rf"^(#+)\s+{re.escape(heading)}\s*$",
        re.MULTILINE,
    )
    match = pattern.search(text)
    assert match is not None, f"heading {heading!r} not found in {_DOC_PATH}"
    level = len(match.group(1))
    start = match.end()
    next_heading = re.search(
        rf"^#{{1,{level}}}\s+\S",
        text[start:],
        re.MULTILINE,
    )
    end = start + next_heading.start() if next_heading else len(text)
    return text[start:end]


def _backticked_list_items(section_text: str) -> set[str]:
    """Every top-level markdown list item's *first* backtick-quoted token.

    Only lines that open a list item (``- `` or ``* ``) are considered, so
    prose elsewhere in the section (including the configured-location clause)
    is never mistaken for an enumerated owned path.
    """
    items: set[str] = set()
    for line in section_text.splitlines():
        stripped = line.strip()
        if not (stripped.startswith("- ") or stripped.startswith("* ")):
            continue
        token = re.search(r"`([^`]+)`", stripped)
        if token is not None:
            items.add(token.group(1))
    return items


def test_contract_version_matches_code() -> None:
    text = _read_doc()
    match = re.search(r"[Cc]ontract [Vv]ersion:?\**\s*`([^`]+)`", text)
    assert match is not None, "no contract-version statement found"
    assert match.group(1) == contract.CONTRACT_VERSION


def test_owned_paths_equal_layout_owned_paths_exactly() -> None:
    section = _section(_read_doc(), "Owned Paths")
    documented = _backticked_list_items(section)
    assert documented == set(layout.OWNED_PATHS)


def test_owned_paths_mutation_bogus_addition_is_caught() -> None:
    """Mutation check: an extra bogus path in the section must fail equality."""
    section = _section(_read_doc(), "Owned Paths")
    documented = _backticked_list_items(section)
    mutated = documented | {"bogus-not-owned/"}
    assert mutated != set(layout.OWNED_PATHS)


def test_owned_paths_mutation_real_removal_is_caught() -> None:
    """Mutation check: removing a real owned path must fail equality."""
    section = _section(_read_doc(), "Owned Paths")
    documented = _backticked_list_items(section)
    assert documented, "expected at least one owned path documented"
    one_removed = set(list(documented)[1:])
    assert one_removed != set(layout.OWNED_PATHS)


def test_configured_location_clause_present_and_is_prose() -> None:
    text = _read_doc()
    section = _section(text, "Configured Locations fitdocs May Create")
    assert "widen" in section
    assert "fitdocs.toml" in section
    # Prose, not an enumerated owned path: no list item in this section names
    # a configured location as if it belonged to the fixed owned-path set.
    assert _backticked_list_items(section) == set()
    # And it must not have leaked into the Owned Paths list either.
    owned_section = _section(text, "Owned Paths")
    assert "intake" not in owned_section
    assert "processed/" not in owned_section


def test_preserved_regions_equal_contract_exactly() -> None:
    section = _section(_read_doc(), "User-Owned and Tool-Filled Regions")
    documented = _backticked_list_items(section)
    assert documented == set(contract.PRESERVED_REGIONS)


def test_managed_keys_equal_contract_exactly() -> None:
    section = _section(_read_doc(), "Managed Frontmatter Keys")
    documented = _backticked_list_items(section)
    assert documented == contract.MANAGED_KEYS


def test_user_owned_keys_equal_contract_exactly() -> None:
    """The document's `## User-Owned Frontmatter Keys` list (effort-tags
    design: ContractDocs) must equal `contract.USER_KEYS` exactly -- same
    set-equality discipline as owned paths, regions, and managed keys above,
    using the same two helpers.

    A heading-not-found parse does not reach this assertion at all: `_section`
    itself raises (`AssertionError: heading ... not found`) before returning,
    which this task's own RED-phase run demonstrated when this section did
    not yet exist. An empty-section parse (the heading present with no
    backtick-quoted list items) reaches this assertion and is already caught
    by the equality on its own -- `set() != contract.USER_KEYS` reds without
    any separate emptiness check, verified by parsing a synthetic empty
    section through `_section`/`_backticked_list_items` and confirming
    inequality. `assert documented` above is therefore a redundant, cheap
    positive control, not what makes the empty-parse case fail.

    This single equality is also the mutation surface the task's three named
    mutations exercise directly against the real document text: adding a
    bogus key to the list, removing a real one, or moving the effort kinds
    (`race`, `test`, `hard`) into this section as a backticked list all
    change what `_backticked_list_items` returns here and so must fail this
    assertion -- verified by hand-editing `docs/ownership-contract.md` for
    each case and re-running this test (see the task's DISCRIMINATION
    report; the edits are not left in the tree)."""
    section = _section(_read_doc(), "User-Owned Frontmatter Keys")
    documented = _backticked_list_items(section)
    assert documented, "expected at least one user-owned key documented"
    assert documented == contract.USER_KEYS


def test_deferred_5_9_clause_is_echoed() -> None:
    """Task 5.1's deferred clause (Req 5.9) must be echoed here, not summarized
    away. Distinctive substrings, not the whole sentence, so a paraphrase that
    keeps the meaning still passes but a document that drops the guarantee
    entirely fails."""
    text = _read_doc()
    assert "skipped" in text
    assert "not a completed file" in text or "not** a completed file" in text
    assert "archive" in text
    assert "disposition" in text or "cleanup" in text or "archival policy" in text
    # Pin the discriminator sentence itself, not just its neighboring clauses:
    # deleting "Presence in the archive -- never the `skipped` label -- is the
    # authoritative discriminator..." must fail this test.
    assert "authoritative discriminator" in text
    assert "Presence in the archive" in text


def test_no_gitattributes_statement_present() -> None:
    text = _read_doc()
    assert "gitattributes" in text.lower()
    assert "does not write" in text or "never writes" in text


def test_agents_md_reference_guidance_present() -> None:
    text = _read_doc()
    assert "AGENTS.md" in text


def test_readme_points_at_contract_by_project_documentation_url() -> None:
    from fitdocs.declaration import CONTRACT_DOCUMENTATION_URL

    readme = (Path(__file__).resolve().parent.parent / "README.md").read_text(
        encoding="utf-8"
    )
    assert "## Ownership" in readme
    assert CONTRACT_DOCUMENTATION_URL in readme
    # The README must not point at the repo-relative path instead/as well in
    # the ownership section (it is rendered into distribution metadata, where
    # a repo-relative docs/ path does not resolve).
    heading_start = readme.index("## Ownership")
    body = readme[heading_start + len("## Ownership") :]
    next_heading = re.search(r"^#{1,2}\s+\S", body, re.MULTILINE)
    ownership_section = body[: next_heading.start()] if next_heading else body
    assert "docs/ownership-contract.md" not in ownership_section.replace(
        CONTRACT_DOCUMENTATION_URL, ""
    )
