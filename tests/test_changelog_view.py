"""`tests/_changelog_view.py`: release-note pins hold across release cuts."""

from __future__ import annotations

from tests._changelog_view import unreleased_since

_BASE = "7.1.0"

_BEFORE = """# Changelog

## [Unreleased]

### Added

- new thing

### Changed

- changed thing

## [7.1.0] - 2026-01-01

### Added

- old thing
"""

_CUT = """# Changelog

## [Unreleased]

## [7.2.0] - 2026-02-01

### Added

- new thing

### Changed

- changed thing

## [7.1.0] - 2026-01-01

### Added

- old thing
"""

_CUT_PLUS_NEW = _CUT.replace(
    "## [Unreleased]\n", "## [Unreleased]\n\n### Added\n\n- later thing\n", 1
)


def _unreleased(view: str) -> str:
    return view.split("## [Unreleased]", 1)[1].split("\n## [", 1)[0]


def _added(view: str) -> str:
    return _unreleased(view).split("### Added", 1)[1].split("\n### ", 1)[0]


def test_before_a_cut_the_text_is_unchanged() -> None:
    assert unreleased_since(_BEFORE, _BASE) == _BEFORE


def _changed(view: str) -> str:
    return _unreleased(view).split("### Changed", 1)[1].split("\n### ", 1)[0]


def test_after_a_cut_the_newer_release_stands_in_for_unreleased() -> None:
    view = unreleased_since(_CUT, _BASE)
    assert "- new thing" in _added(view)
    assert "- changed thing" in _changed(view)
    assert "- changed thing" not in _added(view)
    assert "- new thing" not in _changed(view)
    assert "## [7.2.0]" not in view
    assert "- old thing" not in _unreleased(view)


def test_after_a_cut_and_new_work_both_stay_in_one_added_section() -> None:
    view = unreleased_since(_CUT_PLUS_NEW, _BASE)
    assert _unreleased(view).count("### Added") == 1
    assert "- new thing" in _added(view) and "- later thing" in _added(view)


def test_an_entry_misplaced_into_the_anchor_release_is_outside_the_view() -> None:
    misplaced = _BEFORE.replace("- old thing", "- old thing\n- new thing", 1).replace(
        "- new thing\n\n### Changed", "- other\n\n### Changed", 1
    )
    view = unreleased_since(misplaced, _BASE)
    assert "- new thing" not in _unreleased(view)


def test_two_releases_newer_than_the_anchor_are_both_merged() -> None:
    two = _CUT.replace(
        "## [7.2.0]", "## [7.3.0] - 2026-03-01\n\n### Added\n\n- third\n\n## [7.2.0]", 1
    )
    view = unreleased_since(two, _BASE)
    assert "- third" in _added(view) and "- new thing" in _added(view)


def test_the_anchor_and_older_sections_are_kept_verbatim() -> None:
    view = unreleased_since(_CUT, _BASE)
    assert view.endswith("## [7.1.0] - 2026-01-01\n\n### Added\n\n- old thing\n")


def test_no_unreleased_heading_is_returned_unchanged() -> None:
    assert unreleased_since("# Changelog\n", _BASE) == "# Changelog\n"


def test_a_category_only_a_newer_release_has_keeps_its_own_subsection() -> None:
    text = _CUT_PLUS_NEW  # [Unreleased] has Added only; 7.2.0 has Changed too
    view = unreleased_since(text, _BASE)
    assert "### Changed" in _unreleased(view)
    assert "- changed thing" in _changed(view)
    assert "- later thing" not in _changed(view)
    assert "- changed thing" not in _added(view)
