"""Published statements of publishing in the ownership contract (publish-core 8.1).

The contract's version advanced from 17 to 18 with an appended history
paragraph (Req 13.1); relay-server, landing second, raised it to 19 and replaced
the version head, so the publishing change is pinned in the history, and the
published contract states the ``post`` region as
user-owned, the ``published`` region as fitdocs-owned and refreshed by
``fitdocs publish --yes``, the ``publish`` key, the ledger's place in the
tool-owned state, the ``[publish]`` table, and that ``fitdocs publish`` writes
only ledgers and ``published`` regions (Req 13.3); the workouts declaration
names the ``published`` region as generated content refilled from the ledger
(Req 13.4). Every version below is a landed literal, never derived from the
live constant.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

from fitdocs import contract
from fitdocs.declaration import declaration_text

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/ownership-contract.md"


def _flat(text: str) -> str:
    return " ".join(text.split())


def _doc() -> str:
    return DOC.read_text(encoding="utf-8")


def _section(heading: str) -> str:
    body = _doc().split(f"\n## {heading}\n", 1)[1]
    return _flat(body.split("\n## ", 1)[0])


def _history() -> str:
    return _flat(inspect.getsource(contract))


def test_the_versions_are_the_landed_literals() -> None:
    assert contract.CONTRACT_VERSION == "19"
    assert contract.DOC_VERSION == 12


@pytest.mark.parametrize(
    "phrase",
    [
        "Raised from ``17`` to ``18`` by publish-core (Req 13.1, 13.3)",
        "reserves a user-owned ``post`` region",
        "a fitdocs-owned ``published`` region that ``fitdocs publish --yes`` "
        "fills from the publish ledger",
        "The ``publish`` frontmatter key is user-owned",
        "one TOML file per publish target under ``.fitdocs/publish/``",
        "a ``[publish]`` table that fitdocs only reads",
        "``fitdocs publish`` writes only those ledgers and the ``published`` "
        "region of pages",
        "never the ``post`` region or any other content of a page",
        "A publish target that renews its credentials through its session updates "
        "only that instance's credentials file",
        "which fitdocs writes only as a hidden-comment placeholder in a new page "
        "and carries unchanged",
        "that a fresh render leaves empty",
        "fitdocs never writes it and carries it unchanged",
        "``fitdocs publish`` does not publish a page stamped with an older "
        "document-format version",
        "Run ``fitdocs regen`` once to bring existing pages current",
    ],
)
def test_the_version_history_records_the_publishing_change(phrase: str) -> None:
    assert phrase in _history()


def test_the_previous_version_paragraphs_stay_in_the_history() -> None:
    history = _history()
    assert "Raised from ``16`` to ``17`` by compact-chart-assets" in history
    assert "Raised from ``15`` to ``16`` by the local-time fix" in history


def test_owned_paths_name_the_ledger_under_the_tool_owned_state() -> None:
    section = _section("Owned Paths")
    for phrase in (
        "each publish target's ledger, one TOML file per target under "
        "`.fitdocs/publish/`, recording what `fitdocs publish` has posted",
    ):
        assert phrase in section, phrase


def test_the_settings_file_lists_the_publish_table_and_stays_read_only() -> None:
    section = _section("Shared and User-Owned Files")
    assert "`[connectors]`, and `[publish]` today" in section
    assert "This file is **read-only to fitdocs**" in section


def test_the_regions_section_names_the_published_pointer_and_post() -> None:
    section = _section("User-Owned and Tool-Filled Regions")
    assert (
        "`post` — user-owned. The page's own post for publishing. fitdocs writes "
        "a hidden-comment instruction into a brand-new document"
    ) in section
    assert (
        "The `published` region is refreshed too; see "
        "[The Published Region](#the-published-region)."
    ) in section


def test_the_published_region_names_what_replaces_hand_edits() -> None:
    section = _section("The Published Region")
    assert "`published` — fitdocs-owned." in section
    assert (
        "`fitdocs publish --yes` fills it from the publish ledger and replaces "
        "its content whenever it differs; hand edits there are replaced"
    ) in section
    assert "It is never user-owned and carries no user content" in section
    # The lead-in belongs to the first refreshed-region section only.
    assert "Refreshed regions are disjoint" not in section
    assert _flat(_doc()).count("Refreshed regions are disjoint") == 1


def test_replaces_and_preserves_carries_the_published_region() -> None:
    section = _section("What Regeneration Replaces and Preserves")
    assert (
        "The `published` region is generated content: the merge carries it into "
        "the rewritten page, and `fitdocs publish --yes` is what refills it from "
        "the publish ledger."
    ) in section
    assert "`notes`, `workout`, `post`, and `load`" in section


def test_the_credentials_store_entry_names_the_publishing_writer() -> None:
    section = _section("Shared and User-Owned Files")
    assert (
        "`fitdocs connect`, a credential-renewing `fitdocs pull`, a "
        "credential-renewing `fitdocs publish --yes` and `fitdocs disconnect` are "
        "the only operations that write to or remove from it, each one "
        "instance's file at a time"
    ) in section


def test_a_publish_entry_in_the_overwrite_semantics() -> None:
    section = _section("Overwrite Semantics of Every Writing Operation")
    for phrase in (
        "- **`publish`** — `fitdocs publish` without `--yes` writes nothing.",
        "With `--yes` its only writes are the publish ledgers, one file per "
        "target under `.fitdocs/publish/`, and the inner content of the "
        "`published` region of workout pages at the current document-format "
        "version",
        "It never writes the `post` region, the frontmatter or any other byte of a "
        "page, a workout page of an older or newer format, an asset, an archived "
        "file, the athlete profile or the settings file, and never creates, renames "
        "or deletes a workout page",
        "A target that renews its credentials through its session updates only "
        "that instance's credentials file",
        "rewrites only when the bytes differ",
        "A page whose ledger records are ambiguous is left as it is and reported",
        "reads the publish targets from the `[publish]` and `[connectors]` tables "
        "of `fitdocs.toml`",
    ):
        assert phrase in section, phrase


def test_sync_force_names_post_among_the_carried_regions() -> None:
    section = _section("Overwrite Semantics of Every Writing Operation")
    assert "`notes`, `workout`, `post`, and `load`, and every user-owned" in section


def test_hand_authored_places_name_the_post_region() -> None:
    text = _flat(_doc())
    assert (
        "the `notes` region (or, for a strength document, the `workout` region), "
        "the `post` region and the user-owned frontmatter keys below"
    ) in text


def test_training_history_reserved_names_include_post_and_publish() -> None:
    section = _section("A Second Document Type: Training History")
    assert (
        "unlike the `notes`, `workout` and `post` regions and the effort-tag and "
        "`publish` keys a workout document reserves"
    ) in section


def test_rederivability_names_the_published_region() -> None:
    section = _section("Commit Ordering and Re-Derivability")
    assert (
        "The `published` region is generated content too and is refilled from the "
        "publish ledger by `fitdocs publish --yes`."
    ) in section


def test_the_format_version_section_states_the_older_page_rule() -> None:
    section = _section("Document-Format Versions and Migration")
    assert (
        "A page stamped with a `doc_version` below 12 has neither the `post` nor "
        "the `published` region: `fitdocs publish` does not publish it, and "
        "`fitdocs regen` brings it current with both regions."
    ) in section


def test_the_workouts_declaration_names_the_published_region() -> None:
    sentence = (
        "The `published` region is generated content too: fitdocs refills it from "
        "the publish ledger."
    )
    assert sentence in declaration_text("workouts/")
    golden = (ROOT / "tests/declaration_golden/workouts.AGENTS.md").read_text(
        encoding="utf-8"
    )
    assert sentence in golden
    assert "Ownership contract version: `19`." in golden


def test_no_other_declaration_names_the_published_region() -> None:
    for directory in (
        "history/",
        "blocks/",
        "fit-archive/",
        "dashboards/",
        "wellness/",
        "wellness-archive/",
        "recovery/",
    ):
        assert "`published`" not in declaration_text(directory), directory
