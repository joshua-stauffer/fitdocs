"""Published analytics-index contract and release-note pins (task 8.1)."""

from __future__ import annotations

import re
from pathlib import Path

from fitdocs import contract
from fitdocs.index.store import WRITER_SPILL_DIRNAME
from tests._changelog_view import V0_1_0, read_unreleased_since

ROOT = Path(__file__).resolve().parents[2]
OWNERSHIP = (ROOT / "docs/ownership-contract.md").read_text(encoding="utf-8")


def _unreleased_subsection(name: str) -> str:
    unreleased = read_unreleased_since(ROOT / "CHANGELOG.md", V0_1_0)
    unreleased = unreleased.split("## [Unreleased]", 1)[1].split("\n## [", 1)[0]
    heading = re.search(rf"(?m)^### {re.escape(name)}[ \t]*\n", unreleased)
    assert heading is not None, f"Unreleased has no ### {name} subsection"
    body = unreleased[heading.end() :]
    next_heading = re.search(r"(?m)^### [^\n]+[ \t]*$", body)
    if next_heading is not None:
        body = body[: next_heading.start()]
    return " ".join(body.split())


def _index_section() -> str:
    section = OWNERSHIP.split("## The analytics index (outside the data root)", 1)[1]
    return " ".join(section.split("\n## ", 1)[0].split())


def test_index_contract_publishes_agreement_rule_and_file_names() -> None:
    section = _index_section()
    for phrase in (
        "Document values follow every change of a page",
        "Computed values follow the page's rendering",
        "`fitdocs regen` brings documents and the index forward together after "
        "the athlete inputs change",
        "a build computes every page under the athlete inputs current at that build",
        "`index.duckdb`",
        "`.wal` recovery file",
        "`index.lock`",
        "separate build file `.building`",
        "completed replacement `.rebuilt`",
        "`writer-spill/` (transient; DuckDB's spill space for fitdocs's own "
        "index writes, set by the store)",
        "`query-spill-<pid>/` (transient; created by `fitdocs query`, removed "
        "on close or by the next query)",
    ):
        assert phrase in section, phrase
    assert "`writer-spill/`" in section
    assert WRITER_SPILL_DIRNAME == "writer-spill"
    assert "`.tmp/`" not in section


def test_index_contract_states_refresh_and_build_overwrite_semantics() -> None:
    section = _index_section()
    assert "refresh replaces only the rows of pages that moved" in section
    assert "After every other write of a writing command" in section
    assert "never changes that command's exit code" in section
    assert "builds a separate file and swaps it into place whole" in section
    assert "It writes only inside the resolved per-data-root index directory" in section
    assert (
        "complete set of index writes stays inside this resolved per-data-root "
        "directory"
    ) in section


def test_contract_bump_and_release_notes_are_current() -> None:
    assert contract.CONTRACT_VERSION == "19"
    added = _unreleased_subsection("Added")
    changed = _unreleased_subsection("Changed")
    for phrase in (
        "`fitdocs index [--rebuild]`",
        "writing commands refresh it after their document and load writes",
        "The per-data-root index lives outside the data root",
        "`FITDOCS_INDEX_DIR`",
        "Run `fitdocs index` once to build it",
        "`duckdb>=1.2,<2`",
        "about 44 MB",
        "musl",
        "free-threaded",
    ):
        assert phrase in added, phrase
    for phrase in (
        "The ownership contract version advances from 8 to 9 to describe the "
        "analytics index's external location, disposable-cache behavior and "
        "refresh agreement.",
        "No action is needed for documents",
    ):
        assert phrase in changed, phrase


def test_install_note_covers_duckdb_footprint_without_changing_format_version() -> None:
    install = (ROOT / "docs/install.md").read_text(encoding="utf-8")
    section = " ".join(
        install.split("## Install the tool", 1)[1].split("\n## ", 1)[0].split()
    )
    assert "44 MB" in section
    assert "musl" in section
    assert "free-threaded" in section
    assert (
        "Its prebuilt package is unavailable on musl-based Linux and free-threaded "
        "Python builds; on those platforms, installation needs a working native "
        "build toolchain."
    ) in section
    assert "Installing or upgrading never creates a directory" in section
    assert contract.DOC_VERSION == 12
