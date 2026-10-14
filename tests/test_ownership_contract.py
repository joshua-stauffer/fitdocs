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


# --- the dashboards category (wiki-contract Amendment 5; dashboards 8.1) ----

_DASHBOARD_HEADING = "Dashboard Pages: Athlete Pages with fitdocs Regions"


def _flat(text: str) -> str:
    return " ".join(text.split())


def _flat_section(heading: str) -> str:
    return _flat(_section(_read_doc(), heading))


def test_dashboard_section_states_the_page_rule_and_the_inverse_ownership() -> None:
    section = _flat_section(_DASHBOARD_HEADING)
    for phrase in (
        "The page is yours.",
        "named `<page name>.md`",
        "never creates, renames or deletes a page",
        "never changes a byte of it outside its chart regions",
        "`type: dashboard`",
        "never requires it, never writes it",
        "The directive is yours.",
        "Chart regions are fitdocs's.",
        "`<!-- fitdocs:begin:chart:<id> -->`",
        "`<!-- fitdocs:end:chart:<id> -->`",
        "Do not edit inside a chart region",
        "A page is never a generated document.",
        "never writes a generated-file banner or provenance line into a page",
    ):
        assert phrase in section, phrase


def test_dashboard_section_states_the_asset_snapshot_and_cleanup_rules() -> None:
    section = _flat_section(_DASHBOARD_HEADING)
    for phrase in (
        "`dashboards/assets/<page name>/<chart id>.svg`",
        "never overwrites or deletes a file in `dashboards/assets/` that does "
        "not carry the mark",
        "fitdocs never modifies or deletes a snapshot",
        "new file that never replaces an existing one",
        "`fitdocs regen`, `fitdocs index --rebuild`, a chart-kit upgrade and "
        "image cleanup leave every snapshot unchanged",
        "deletes a marked chart image only if no dashboard page's text contains "
        "that image's path relative to `dashboards/`",
        "A link from outside `dashboards/` does not protect an image",
    ):
        assert phrase in section, phrase


def test_head_and_definitions_agree_with_the_dashboards_section() -> None:
    text = _flat(_read_doc())
    assert "inside the eight owned directories" in text
    assert "each of those four commands refreshes every declared directory's" in text
    owned = _flat_section("Owned Paths")
    assert (
        '"owned" in this contract means "fitdocs may create, rewrite, or delete '
        'wholesale, on its own initiative" for everything it generates; under '
        "`dashboards/` the pages are the one exception"
    ) in owned


def test_regions_and_overwrite_sections_carry_the_dashboards_rules() -> None:
    regions = _flat_section("User-Owned and Tool-Filled Regions")
    assert (
        "A chart region in a dashboard page is the inverse case: it is "
        "tool-owned inside a page that is yours"
    ) in regions
    overwrite = _flat_section("Overwrite Semantics of Every Writing Operation")
    for phrase in (
        "**`dashboard`** — `fitdocs dashboard check` writes and deletes nothing",
        "never builds or rebuilds the analytics index",
        "never changes its command's exit code",
        "`dashboards/AGENTS.md`",
        "`sync` (with or without a source; without one it is the inbox drain), "
        "`regen`, `load` and `pull --sync`",
        "changes no dashboard page, asset or snapshot",
    ):
        assert phrase in overwrite, phrase
    history = overwrite[overwrite.index("**`history`**") :]
    history = history[: history.index(" - **")]
    assert (
        "`fit-archive/AGENTS.md`, `dashboards/AGENTS.md`, `wellness/AGENTS.md`, "
        "`wellness-archive/AGENTS.md`, and `recovery/AGENTS.md` — through the same "
        "function"
    ) in history
    for command in ("**`sync`**", "**`regen`**", "**`load`**", "**`pull`**"):
        bullet = overwrite[overwrite.index(command) :]
        bullet = bullet[: bullet.index(" - **") if " - **" in bullet else None]
        assert "dashboard pass" in bullet, command


def test_root_instructions_example_names_all_eight_declarations() -> None:
    text = _read_doc()
    example = _section(
        text, "Referencing `workouts/AGENTS.md` from Your Wiki's Root Instructions"
    )
    flat = _flat(example)
    assert "`dashboards/AGENTS.md`" in flat
    assert "those eight files are generated" in flat
    assert "those four files" not in text
    assert "each of the five refreshes" not in flat
    assert "each of those four commands refreshes every declared directory's" in flat


def test_every_never_read_back_sentence_carries_the_named_exception() -> None:
    text = _flat(_read_doc())
    phrases = ("back into a document", "back into documents")
    sentences = re.split(r"(?<=[.;:])\s+", text)
    hits = [sentence for sentence in sentences if any(p in sentence for p in phrases)]
    assert hits, "no sentence states the index is never read back into a document"
    for sentence in hits:
        assert "except the chart regions" in sentence, sentence


def _bullet(section: str, name: str) -> str:
    start = section.index(name)
    end = section.find(" - **", start + 1)
    return section[start : end if end != -1 else None]


def test_safety_relevant_dashboard_sentences_are_pinned() -> None:
    page = _flat_section(_DASHBOARD_HEADING)
    overwrite = _flat_section("Overwrite Semantics of Every Writing Operation")
    ordering = _flat_section("Commit Ordering and Re-Derivability")
    dashboard = _bullet(overwrite, "**`dashboard`**")
    load = _bullet(overwrite, "**`load`**")
    history = _bullet(overwrite, "**`history`**")
    assert (
        "a run writes in the order new snapshots, then chart images, then the "
        "page itself"
    ) in ordering
    assert "Per page the order is the new snapshots, then the chart images, then" in (
        dashboard
    )
    assert "A run that cannot read every page completely deletes nothing." in page
    assert "runs over every dashboard page only when that refresh succeeded" in (
        dashboard
    )
    assert "so it does not write `dashboards/AGENTS.md`" in load
    assert "does not write `dashboards/AGENTS.md`" not in history
    assert "an `assets/<page name>/` folder that removal emptied" in dashboard
    assert (
        "A chart with a directive or region problem is left untouched and only reported"
    ) in dashboard
    assert "a failing `freeze` writes nothing, not even a note" in dashboard
    assert "a frozen chart with none runs its SQL once and stores its first" in (
        dashboard
    )
    assert (
        "the chart images under `dashboards/assets/` carry the generated-file mark"
        in (page)
    )
    assert "a snapshot is created atomically as a new file" in page
    assert (
        "at most a few of its regions are yours (none on a history or "
        "planned-workout page)"
    ) in page
    assert "(a misnamed markdown file there is reported)" in dashboard
    assert (
        "When a chart's image, snapshot or page cannot be written, its region is "
        "left as it was and the failure is only reported"
    ) in dashboard
    assert "or whose first frozen result cannot be stored" in dashboard
    assert (
        "fitdocs creates each snapshot as a new file that never replaces an "
        "existing one"
    ) in page
    assert (
        "`dashboard` command itself does not write `dashboards/AGENTS.md`"
    ) in dashboard
    assert (
        "were not refreshed and why when `dashboards/` holds a markdown file "
        "besides its `AGENTS.md`"
    ) in dashboard
    assert "when at least one page exists" not in dashboard


def test_wellness_locations_have_scoped_contract_guarantees() -> None:
    section = _flat_section("Wellness Archive and Series")
    for phrase in (
        "`wellness-archive/`",
        "fitdocs never modifies an archive entry",
        "one directory per format",
        "SHA-256 of the original",
        "`wellness/` holds one CSV file per calendar year",
        "`manifest.toml`",
        "`[wellness]` settings",
        "overwrites hand edits to the series",
    ):
        assert phrase in section, phrase


def test_recovery_section_states_the_location_and_write_rules() -> None:
    assert _flat_section("Recovery Page") == (
        "`recovery/recovery.md` is one generated recovery page per data root. "
        "Its chart images live under `recovery/assets/` and are linked relative "
        "to the page's directory. `fitdocs recovery` derives the page and charts "
        "from the normalized wellness series and the workout documents, writes "
        "each file atomically, and rewrites it only when its content changes. "
        "It removes a chart image it wrote earlier when the new page no longer "
        "references it. The page and charts carry no user-owned region. "
        "fitdocs never writes a workout, history, block or wellness file, "
        "settings file or athlete profile during a recovery run. It leaves "
        "foreign files, symlinks and directories occupying output-file paths "
        "untouched and reports them. `recovery/AGENTS.md` names fitdocs as owner "
        "and states that the page is re-derivable from `wellness/` and the "
        "workout documents alone."
    )
