"""Release-note pins for analytics-query task 8.1."""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_CHANGELOG_PATH = _REPO_ROOT / "CHANGELOG.md"
_TECH_PATH = _REPO_ROOT / ".kiro/steering/tech.md"
_PYPROJECT_PATH = _REPO_ROOT / "pyproject.toml"
_ANALYTICS_URL = (
    "https://github.com/joshua-stauffer/fitdocs/blob/main/docs/analytics.md"
)
_SYNTHETIC_RELEASE_VERSION = "98.76.54"


def _project_version() -> str:
    manifest = tomllib.loads(_PYPROJECT_PATH.read_text(encoding="utf-8"))
    version = manifest["project"]["version"]
    if not isinstance(version, str) or not version:
        raise ValueError("project version must be non-empty text")
    return version


def _current_release_heading(text: str) -> str:
    prefix = f"## [{_project_version()}]"
    headings = [line for line in text.splitlines() if line.startswith(prefix)]
    if len(headings) != 1:
        raise ValueError(f"expected one released heading for {prefix!r}")
    return headings[0]


def _assert_default_format_claim(entry: str) -> None:
    flat_entry = " ".join(entry.split())
    assert "default is a table on a terminal" in flat_entry
    assert "CSV when piped" in flat_entry
    assert "`--format` option explicitly selects table, CSV, or JSON" in flat_entry


def _heading_body(text: str, heading: str) -> str:
    level = len(heading) - len(heading.lstrip("#"))
    if level not in {2, 3} or not heading.startswith("#" * level + " "):
        raise ValueError(f"unsupported changelog heading {heading!r}")
    lines = text.splitlines()
    matches = [index for index, line in enumerate(lines) if line == heading]
    if len(matches) != 1:
        raise ValueError(f"expected one {heading!r} heading, found {len(matches)}")
    start = matches[0] + 1
    prefix = "#" * level + " "
    end = next(
        (
            index
            for index in range(start, len(lines))
            if lines[index].startswith(prefix)
            and not lines[index].startswith("#" * (level + 1))
        ),
        len(lines),
    )
    return "\n".join(lines[start:end])


def _bullets(section: str) -> tuple[str, ...]:
    bullets: list[list[str]] = []
    for line in section.splitlines():
        if line.startswith("- "):
            bullets.append([line])
        elif bullets:
            bullets[-1].append(line)
    return tuple("\n".join(lines) for lines in bullets)


def _unreleased_query_entry(text: str) -> str:
    unreleased = _heading_body(text, "## [Unreleased]")
    added = _heading_body(unreleased, "### Added")
    matching = tuple(
        bullet for bullet in _bullets(added) if "`fitdocs query`" in bullet
    )
    if len(matching) != 1:
        raise ValueError(f"expected one unreleased query entry, found {len(matching)}")
    return matching[0]


_VALID_SYNTHETIC_CHANGELOG = f"""# Changelog

## [Unreleased]

### Added

- `fitdocs query` accepts one SQL statement as a positional argument or on
  standard input (`-`), with `--file` for a file; its default is a table on a
  terminal and CSV when piped. The `--format` option explicitly selects
  table, CSV, or JSON, and it supports the sandboxed `--schema` view. The
  packaged `fitdocs-analytics` skill teaches safe SQL; see the
  [analytics guide]({_ANALYTICS_URL}).

## [98.76.54] - 2026-09-19

### Added

- Existing release content.
"""


def test_unreleased_entry_names_all_query_publication_details() -> None:
    text = _CHANGELOG_PATH.read_text(encoding="utf-8")
    entry = _unreleased_query_entry(text)
    assert _project_version() != _SYNTHETIC_RELEASE_VERSION

    assert entry.startswith("- `fitdocs query`")
    assert "positional argument" in entry
    assert "standard input (`-`)" in entry
    assert "`--file`" in entry
    assert "table" in entry
    assert "CSV" in entry
    assert "JSON" in entry
    _assert_default_format_claim(entry)
    assert "sandboxed" in entry
    assert "`--schema`" in entry
    assert "packaged `fitdocs-analytics` skill" in entry
    assert f"]({_ANALYTICS_URL})" in entry

    released = _heading_body(text, _current_release_heading(text))
    assert "`fitdocs query`" not in released
    assert "`fitdocs-analytics`" not in released
    assert _ANALYTICS_URL not in released


def test_synthetic_changelog_pins_each_default_format_clause() -> None:
    entry = _unreleased_query_entry(_VALID_SYNTHETIC_CHANGELOG)
    _assert_default_format_claim(entry)


def test_steering_publishes_query_network_and_sandbox_contract() -> None:
    tech = _TECH_PATH.read_text(encoding="utf-8")
    network = tech.split("## Network and Credentials", 1)[1].split(
        "## Development Standards", 1
    )[0]
    flat_network = " ".join(network.split())

    assert (
        "`check`, `query`, `history`, `plan`, `derive-benchmarks`, `index`, and "
        "rendering — makes no connector request"
    ) in flat_network
    assert (
        "`fitdocs query` runs agent SQL read-only under a locked DuckDB "
        "configuration with external access and extension loading off."
    ) in flat_network


def test_entry_parser_rejects_missing_unreleased_or_added_headers() -> None:
    missing_unreleased = _VALID_SYNTHETIC_CHANGELOG.replace("## [Unreleased]\n", "", 1)
    with pytest.raises(ValueError, match="## \\[Unreleased\\]"):
        _unreleased_query_entry(missing_unreleased)

    missing_added = _VALID_SYNTHETIC_CHANGELOG.replace("### Added\n", "", 1)
    with pytest.raises(ValueError, match="### Added"):
        _unreleased_query_entry(missing_added)


def test_heading_parser_rejects_unsupported_and_duplicate_headings() -> None:
    with pytest.raises(ValueError, match="unsupported changelog heading"):
        _heading_body("#### Subheading\nbody", "#### Subheading")

    duplicate = "## [Unreleased]\nfirst\n## [Unreleased]\nsecond\n"
    with pytest.raises(ValueError, match="expected one"):
        _heading_body(duplicate, "## [Unreleased]")


def test_heading_body_stops_at_the_next_heading_of_its_level() -> None:
    synthetic = (
        f"## [Unreleased]\nfirst section\n## [{_SYNTHETIC_RELEASE_VERSION}]"
        " - 2026-09-19\nreleased section\n"
    )
    body = _heading_body(synthetic, "## [Unreleased]")
    assert "first section" in body
    assert "released section" not in body


def test_bullet_extractor_keeps_continuations_and_separates_entries() -> None:
    synthetic = (
        "- first bullet\n  its continuation\n- second bullet\n  its continuation\n"
    )
    assert _bullets(synthetic) == (
        "- first bullet\n  its continuation",
        "- second bullet\n  its continuation",
    )


def test_released_entry_cannot_substitute_for_unreleased_entry() -> None:
    synthetic = """# Changelog

## [Unreleased]

### Added

- A different unreleased change.

## [98.76.54] - 2026-09-19

### Added

- `fitdocs query` appears only in this released section.
"""
    with pytest.raises(ValueError, match="one unreleased query entry"):
        _unreleased_query_entry(synthetic)


def test_entry_parser_does_not_combine_neighboring_bullets() -> None:
    synthetic = f"""# Changelog

## [Unreleased]

### Added

- `fitdocs query` is in this first entry only.
- The packaged `fitdocs-analytics` skill is in a neighbor, with
  [a link]({_ANALYTICS_URL}).
"""
    entry = _unreleased_query_entry(synthetic)
    assert entry == "- `fitdocs query` is in this first entry only."
    assert "fitdocs-analytics" not in entry
    assert _ANALYTICS_URL not in entry


def test_entry_parser_requires_one_query_bullet() -> None:
    duplicate = _VALID_SYNTHETIC_CHANGELOG.replace(
        "- `fitdocs query` accepts one SQL statement",
        "- `fitdocs query` duplicate.\n- `fitdocs query` accepts one SQL statement",
        1,
    )
    with pytest.raises(ValueError, match="one unreleased query entry"):
        _unreleased_query_entry(duplicate)
