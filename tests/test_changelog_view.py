"""`tests/_changelog_view.py`: release-note pins hold before and after a cut."""

from __future__ import annotations

from tests._changelog_view import current_changelog

_BEFORE = """# Changelog

## [Unreleased]

### Added

- new thing

## [7.1.0] - 2026-01-01

### Added

- old thing
"""

_AFTER_CUT = """# Changelog

## [Unreleased]

## [7.2.0] - 2026-02-01

### Added

- new thing

## [7.1.0] - 2026-01-01

### Added

- old thing
"""


def test_a_populated_unreleased_section_is_returned_unchanged() -> None:
    assert current_changelog(_BEFORE) == _BEFORE


def test_an_empty_unreleased_section_takes_the_newest_release_body() -> None:
    view = current_changelog(_AFTER_CUT)
    unreleased = view.split("## [Unreleased]", 1)[1].split("\n## [", 1)[0]
    assert "- new thing" in unreleased
    assert "## [7.2.0]" not in view
    older = view.split("\n## [", 2)[2]
    assert older.startswith("7.1.0] - 2026-01-01") and "- old thing" in older


def test_the_view_of_a_cut_matches_the_view_before_it() -> None:
    before = current_changelog(_BEFORE).split("## [7.1.0]")[0]
    after = current_changelog(_AFTER_CUT).split("## [7.1.0]")[0]
    assert " ".join(after.split()) == " ".join(before.split())


def test_an_entry_in_an_older_release_is_not_pulled_in() -> None:
    two_cuts = _AFTER_CUT.replace(
        "## [Unreleased]\n", "## [Unreleased]\n\n- newest\n", 1
    )
    view = current_changelog(two_cuts)
    unreleased = view.split("## [Unreleased]", 1)[1].split("\n## [", 1)[0]
    assert "newest" in unreleased and "new thing" not in unreleased


def test_no_unreleased_heading_or_no_release_is_returned_unchanged() -> None:
    assert current_changelog("# Changelog\n") == "# Changelog\n"
    only = "# Changelog\n\n## [Unreleased]\n"
    assert current_changelog(only) == only
