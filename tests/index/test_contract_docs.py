"""Published analytics-index contract and release-note pins (task 8.1)."""

from __future__ import annotations

import re
from pathlib import Path

from fitdocs import contract
from fitdocs.index.store import WRITER_SPILL_DIRNAME

ROOT = Path(__file__).resolve().parents[2]
OWNERSHIP = (ROOT / "docs/ownership-contract.md").read_text(encoding="utf-8")


def _unreleased_subsection(name: str) -> str:
    unreleased = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
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


def test_index_contract_publishes_location_order_key_refusal_and_permissions() -> None:
    section = _index_section()
    env_fallback = section.index("`FITDOCS_INDEX_DIR`")
    xdg_fallback = section.index("`XDG_CACHE_HOME`")
    home_fallback = section.index("`.cache/fitdocs/index`")
    assert env_fallback < xdg_fallback < home_fallback
    for phrase in (
        "`FITDOCS_INDEX_DIR`",
        "otherwise `fitdocs/index` under an absolute `XDG_CACHE_HOME`",
        "otherwise `.cache/fitdocs/index` under the user's home directory",
        "`<slug>-<digest>`",
        "fully resolved absolute path",
        "root basename lowercased",
        "runs of characters outside `[a-z0-9]` replaced by hyphens",
        "cut to 24 characters (or `root` if empty)",
        "first 16 hexadecimal characters",
        "non-empty relative `FITDOCS_INDEX_DIR` is refused",
        "naming the variable and value",
        "resolves to the data root itself or a location inside it",
        "naming both resolved paths",
        "writes nothing there",
        "`0o700`",
        "readable, writable and searchable only by the current user",
        "disposable cache",
        "never reads the index back into a document",
    ):
        assert phrase in section, phrase

    key_rule = (
        "Within that base, fitdocs names one directory `<slug>-<digest>` from the "
        "data root's fully resolved absolute path. The slug is the root basename "
        "lowercased, with runs of characters outside `[a-z0-9]` replaced by "
        "hyphens, trimmed, and cut to 24 characters (or `root` if empty); the "
        "digest is the first 16 hexadecimal characters of that path's SHA-256."
    )
    assert key_rule in section
    assert (
        "Newly created index directories have mode `0o700`, readable, writable "
        "and searchable only by the current user; existing directory permissions "
        "are left unchanged."
    ) in section


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


def test_index_is_counted_as_an_external_location_not_an_owned_data_root_path() -> None:
    assert (
        "Three locations at the top of the data root (by default), and three outside"
        in OWNERSHIP
    )
    section = OWNERSHIP.split("## Owned Paths", 1)[1].split("\n## ", 1)[0]
    assert "analytics-index" not in section
    configured = OWNERSHIP.split("## Configured Locations fitdocs May Create", 1)[1]
    configured = " ".join(configured.split("\n## ", 1)[0].split())
    assert "the external analytics-index directory specified below" in configured
    flat_ownership = " ".join(OWNERSHIP.split())
    write_set_start = flat_ownership.index("The full set of places a given run")
    write_set_end = flat_ownership.index(
        " ## The analytics index (outside the data root)", write_set_start
    )
    write_set = flat_ownership[write_set_start:write_set_end]
    assert write_set == (
        "The full set of places a given run of fitdocs may write is therefore "
        "always *the owned paths above, union whatever your settings currently "
        "configure* — never more, apart from the files under [Shared and "
        "User-Owned Files](#shared-and-user-owned-files) that state their own "
        "write rule (`athlete.toml`, and outside the data root the connector "
        "credentials store) and the external analytics-index directory "
        "specified below."
    )


def test_contract_bump_and_release_notes_are_current() -> None:
    assert contract.CONTRACT_VERSION == "9"
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
    assert contract.DOC_VERSION == 9
