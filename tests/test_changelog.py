"""Tests for ``CHANGELOG.md`` (design.md "Changelog (`CHANGELOG.md`)"; task
1.3): Keep a Changelog 1.1.2 conformance -- title line, a single standing
``## [Unreleased]`` heading that precedes every released entry, released
entries in strictly descending version order, only the six canonical
category names with no repeat inside one section, and every markdown link
target either an absolute ``https://`` URL or an in-document ``#anchor`` --
never a bare repo-relative path -- since the changelog ships inside the
source distribution (design.md "Doc references leave the repository").

:func:`check_changelog` is the one walker every test in this module drives.
Negative cases are unit-tested against synthetic text so a rule's
discrimination does not depend on ever mutating the real file; the real
``CHANGELOG.md`` is then exercised as one more case (Req 4.1-4.6).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_CHANGELOG_PATH = _PROJECT_ROOT / "CHANGELOG.md"

#: The six canonical Keep a Changelog category names (case-sensitive).
CANONICAL_CATEGORIES = frozenset(
    {"Added", "Changed", "Deprecated", "Removed", "Fixed", "Security"}
)

_UNRELEASED_HEADING = "## [Unreleased]"
_RELEASE_HEADING_RE = re.compile(r"^## \[(\d+)\.(\d+)\.(\d+)\] - (\d{4}-\d{2}-\d{2})$")

#: Every markdown link target in the file, e.g. the ``X`` in ``](X)``.
_LINK_TARGET_RE = re.compile(r"\]\(([^)]*)\)")


def _is_allowed_link_target(target: str) -> bool:
    """A changelog link target must be an absolute URL or an in-document
    anchor -- never a bare repo-relative path (``docs/x.md``, ``./x``,
    ``../x``, or an un-prefixed filename like ``LICENSE``). The changelog
    ships inside the source distribution, so a repo-relative target resolves
    to nothing for the reader who has only the distribution -- design.md
    "Doc references leave the repository". An allowlist (rather than a
    denylist of repo-relative *prefixes*) is used deliberately: a denylist of
    ``docs/``/``./``/``../`` misses a bare project-root file reference such
    as ``](LICENSE)`` or ``](pyproject.toml)``, which is exactly as
    unreachable from the sdist-embedded changelog as a ``docs/`` link is."""
    return target.startswith("https://") or target.startswith("#")


#: The convention this file itself records (task 1.3 deliverable 3):
#: a governed-contract entry names the contract and the required action.
CONVENTION_PHRASE = "names the contract"


@dataclass(frozen=True)
class _Section:
    heading: str
    categories: list[str]


def _parse_sections(text: str) -> list[_Section]:
    """Split *text* into ``## `` sections, each carrying its ``### ``
    category headings (with a leading ``### `` stripped) in document order."""
    sections: list[_Section] = []
    current: _Section | None = None
    for line in text.splitlines():
        if line.startswith("## "):
            current = _Section(heading=line, categories=[])
            sections.append(current)
        elif line.startswith("### ") and current is not None:
            current.categories.append(line[len("### ") :].strip())
    return sections


def check_changelog(text: str) -> list[str]:
    """Return every Keep a Changelog conformance violation found in *text*.

    An empty list means *text* is conformant. Each violation is a
    human-readable string naming the rule it broke, so tests can match on a
    stable substring rather than an index.
    """
    violations: list[str] = []
    lines = text.splitlines()

    if not lines or lines[0] != "# Changelog":
        violations.append("first line is not '# Changelog'")

    sections = _parse_sections(text)
    headings = [section.heading for section in sections]
    if not headings:
        violations.append("no '## ' headings found")

    unreleased_count = headings.count(_UNRELEASED_HEADING)
    if unreleased_count != 1:
        violations.append(
            f"'## [Unreleased]' appears {unreleased_count} times, expected exactly 1"
        )
    unreleased_index = (
        headings.index(_UNRELEASED_HEADING) if _UNRELEASED_HEADING in headings else None
    )

    release_versions: list[tuple[int, int, int]] = []
    for index, heading in enumerate(headings):
        if heading == _UNRELEASED_HEADING:
            continue
        match = _RELEASE_HEADING_RE.match(heading)
        if match is None:
            violations.append(
                f"heading {heading!r} does not match '## [X.Y.Z] - YYYY-MM-DD'"
            )
            continue
        if unreleased_index is not None and index < unreleased_index:
            violations.append(
                f"released heading {heading!r} precedes '## [Unreleased]'"
            )
        major, minor, patch = (int(part) for part in match.groups()[:3])
        release_versions.append((major, minor, patch))

    for earlier, later in zip(release_versions, release_versions[1:], strict=False):
        if not earlier > later:
            violations.append(
                "released entries are not in strictly descending version order: "
                f"{earlier} is not after {later}"
            )

    for section in sections:
        seen: set[str] = set()
        for category in section.categories:
            if category not in CANONICAL_CATEGORIES:
                violations.append(
                    f"{section.heading!r} has non-canonical category {category!r}"
                )
            if category in seen:
                violations.append(f"{section.heading!r} repeats category {category!r}")
            seen.add(category)

    for match in _LINK_TARGET_RE.finditer(text):
        target = match.group(1)
        if not _is_allowed_link_target(target):
            violations.append(
                f"link target {target!r} is not in project-URL form; "
                "documentation links must be an https:// URL or an in-document #anchor"
            )

    return violations


_VALID_SYNTHETIC_CHANGELOG = """# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

An entry that touches a governed contract names the contract and the action
a user or plugin author must take.

## [Unreleased]

### Added

- Something user-observable.
"""


def test_valid_synthetic_changelog_has_no_violations() -> None:
    assert check_changelog(_VALID_SYNTHETIC_CHANGELOG) == []


def test_missing_title_line_is_a_violation() -> None:
    text = _VALID_SYNTHETIC_CHANGELOG.replace("# Changelog", "Changelog", 1)
    violations = check_changelog(text)
    assert any("first line" in v for v in violations)


def test_correct_title_line_is_not_a_violation() -> None:
    assert not any(
        "first line" in v for v in check_changelog(_VALID_SYNTHETIC_CHANGELOG)
    )


def test_change_log_two_words_title_is_a_violation() -> None:
    text = _VALID_SYNTHETIC_CHANGELOG.replace("# Changelog", "# Change Log", 1)
    violations = check_changelog(text)
    assert any("first line" in v for v in violations)


def test_lowercase_title_is_a_violation() -> None:
    text = _VALID_SYNTHETIC_CHANGELOG.replace("# Changelog", "# changelog", 1)
    violations = check_changelog(text)
    assert any("first line" in v for v in violations)


def test_title_with_trailing_whitespace_is_a_violation() -> None:
    text = _VALID_SYNTHETIC_CHANGELOG.replace("# Changelog", "# Changelog ", 1)
    violations = check_changelog(text)
    assert any("first line" in v for v in violations)


def test_title_with_trailing_suffix_is_a_violation() -> None:
    text = _VALID_SYNTHETIC_CHANGELOG.replace("# Changelog", "# Changelog x", 1)
    violations = check_changelog(text)
    assert any("first line" in v for v in violations)


def test_title_truncated_is_a_violation() -> None:
    text = _VALID_SYNTHETIC_CHANGELOG.replace("# Changelog", "# Change", 1)
    violations = check_changelog(text)
    assert any("first line" in v for v in violations)


def test_missing_unreleased_heading_is_a_violation() -> None:
    text = _VALID_SYNTHETIC_CHANGELOG.replace(_UNRELEASED_HEADING, "## Unreleased", 1)
    violations = check_changelog(text)
    assert any("expected exactly 1" in v for v in violations)


def test_duplicate_unreleased_heading_is_a_violation() -> None:
    text = (
        _VALID_SYNTHETIC_CHANGELOG
        + "\n"
        + _UNRELEASED_HEADING
        + "\n\n### Added\n\n- x\n"
    )
    violations = check_changelog(text)
    assert any("expected exactly 1" in v for v in violations)


def test_single_unreleased_heading_is_not_a_violation() -> None:
    assert not any(
        "expected exactly 1" in v for v in check_changelog(_VALID_SYNTHETIC_CHANGELOG)
    )


def test_lowercase_unreleased_heading_is_a_violation() -> None:
    text = _VALID_SYNTHETIC_CHANGELOG.replace(_UNRELEASED_HEADING, "## [unreleased]", 1)
    violations = check_changelog(text)
    assert any("expected exactly 1" in v for v in violations)


def test_unreleased_heading_trailing_whitespace_is_a_violation() -> None:
    text = _VALID_SYNTHETIC_CHANGELOG.replace(
        _UNRELEASED_HEADING, _UNRELEASED_HEADING + " ", 1
    )
    violations = check_changelog(text)
    assert any("expected exactly 1" in v for v in violations)


def test_unreleased_heading_with_suffix_is_a_violation() -> None:
    text = _VALID_SYNTHETIC_CHANGELOG.replace(
        _UNRELEASED_HEADING, _UNRELEASED_HEADING + " (soon)", 1
    )
    violations = check_changelog(text)
    assert any("expected exactly 1" in v for v in violations)


def test_heading_without_space_after_hashes_counts_as_no_heading() -> None:
    text = "# Changelog\n\n##[Unreleased]\n\n### Added\n\n- x\n"
    violations = check_changelog(text)
    assert any("no '## ' headings found" in v for v in violations)


def test_release_heading_wrong_format_is_a_violation() -> None:
    text = _VALID_SYNTHETIC_CHANGELOG + "\n## 1.2.3 - 2026-01-01\n\n### Added\n\n- x\n"
    violations = check_changelog(text)
    assert any("does not match" in v for v in violations)


def test_release_heading_missing_date_is_a_violation() -> None:
    text = _VALID_SYNTHETIC_CHANGELOG + "\n## [1.2.3]\n\n### Added\n\n- x\n"
    violations = check_changelog(text)
    assert any("does not match" in v for v in violations)


def test_release_heading_two_part_version_is_a_violation() -> None:
    text = _VALID_SYNTHETIC_CHANGELOG + "\n## [1.0] - 2026-01-01\n\n### Added\n\n- x\n"
    violations = check_changelog(text)
    assert any("does not match" in v for v in violations)


def test_release_heading_malformed_date_is_a_violation() -> None:
    text = _VALID_SYNTHETIC_CHANGELOG + "\n## [1.2.3] - 2026-1-1\n\n### Added\n\n- x\n"
    violations = check_changelog(text)
    assert any("does not match" in v for v in violations)


def test_release_heading_trailing_text_is_a_violation() -> None:
    text = (
        _VALID_SYNTHETIC_CHANGELOG
        + "\n## [1.0.0] - 2026-01-01 draft\n\n### Added\n\n- x\n"
    )
    violations = check_changelog(text)
    assert any("does not match" in v for v in violations)


#: Every malformed release-heading shape the rule must reject, beyond the
#: individually named cases above. Leading zeros in a version part (e.g.
#: ``01.0.0``) are deliberately NOT included here: SemVer disallows them, but
#: neither Keep a Changelog nor this task's design/requirements call out
#: leading-zero rejection, so `\d+` is left permissive rather than adding
#: unrequested production behavior. If that changes, add the case here.
_MALFORMED_RELEASE_HEADINGS: tuple[tuple[str, str], ...] = (
    ("no_separator", "## [1.0.0] 2026-01-01"),
    ("four_version_parts", "## [1.0.0.0] - 2026-01-01"),
    ("v_prefix", "## [v1.0.0] - 2026-01-01"),
    ("one_digit_day", "## [1.0.0] - 2026-01-1"),
    ("two_digit_year", "## [1.0.0] - 26-01-01"),
    ("no_space_before_date", "## [1.0.0] -2026-01-01"),
    ("no_space_before_dash", "## [1.0.0]- 2026-01-01"),
    ("one_digit_month", "## [1.0.0] - 2026-1-01"),
    ("extra_space_around_dash", "## [1.0.0]  -  2026-01-01"),
    ("non_numeric_version_part", "## [1.a.0] - 2026-01-01"),
)


@pytest.mark.parametrize(
    "heading",
    [heading for _, heading in _MALFORMED_RELEASE_HEADINGS],
    ids=[name for name, _ in _MALFORMED_RELEASE_HEADINGS],
)
def test_release_heading_malformed_variants_are_violations(heading: str) -> None:
    text = _VALID_SYNTHETIC_CHANGELOG + f"\n{heading}\n\n### Added\n\n- x\n"
    violations = check_changelog(text)
    assert any("does not match" in v for v in violations)


def test_empty_document_is_a_violation() -> None:
    violations = check_changelog("")
    assert any("first line" in v for v in violations)
    assert any("no '## ' headings found" in v for v in violations)


def test_release_entry_with_no_unreleased_heading_does_not_crash_or_precede() -> None:
    # No ``[Unreleased]`` heading at all -- ``unreleased_index`` stays ``None``.
    # The precedes-check must not run (and must not raise) when there is
    # nothing for a release heading to precede.
    text = "# Changelog\n\n## [1.0.0] - 2026-01-01\n\n### Added\n\n- x\n"
    violations = check_changelog(text)
    assert any("expected exactly 1" in v for v in violations)
    assert not any("precedes" in v for v in violations)


def test_release_heading_before_unreleased_is_a_violation() -> None:
    text = (
        "# Changelog\n\n"
        "## [1.0.0] - 2026-01-01\n\n### Added\n\n- x\n\n"
        f"{_UNRELEASED_HEADING}\n\n### Added\n\n- y\n"
    )
    violations = check_changelog(text)
    assert any("precedes" in v for v in violations)


def test_release_heading_after_unreleased_is_not_a_violation() -> None:
    text = (
        "# Changelog\n\n"
        f"{_UNRELEASED_HEADING}\n\n### Added\n\n- y\n\n"
        "## [1.0.0] - 2026-01-01\n\n### Added\n\n- x\n"
    )
    assert not any("precedes" in v for v in check_changelog(text))


def test_ascending_release_order_is_a_violation() -> None:
    text = (
        "# Changelog\n\n"
        f"{_UNRELEASED_HEADING}\n\n"
        "## [1.0.0] - 2026-01-01\n\n### Added\n\n- x\n\n"
        "## [2.0.0] - 2026-02-01\n\n### Added\n\n- y\n"
    )
    violations = check_changelog(text)
    assert any("strictly descending" in v for v in violations)


def test_descending_release_order_is_not_a_violation() -> None:
    text = (
        "# Changelog\n\n"
        f"{_UNRELEASED_HEADING}\n\n"
        "## [2.0.0] - 2026-02-01\n\n### Added\n\n- y\n\n"
        "## [1.0.0] - 2026-01-01\n\n### Added\n\n- x\n"
    )
    assert check_changelog(text) == []


def test_equal_release_versions_is_a_violation() -> None:
    text = (
        "# Changelog\n\n"
        f"{_UNRELEASED_HEADING}\n\n"
        "## [1.0.0] - 2026-02-01\n\n### Added\n\n- y\n\n"
        "## [1.0.0] - 2026-01-01\n\n### Added\n\n- x\n"
    )
    violations = check_changelog(text)
    assert any("strictly descending" in v for v in violations)


def test_same_major_ascending_minor_is_a_violation() -> None:
    text = (
        "# Changelog\n\n"
        f"{_UNRELEASED_HEADING}\n\n"
        "## [1.1.0] - 2026-01-01\n\n### Added\n\n- x\n\n"
        "## [1.2.0] - 2026-02-01\n\n### Added\n\n- y\n"
    )
    violations = check_changelog(text)
    assert any("strictly descending" in v for v in violations)


def test_same_major_descending_minor_is_not_a_violation() -> None:
    text = (
        "# Changelog\n\n"
        f"{_UNRELEASED_HEADING}\n\n"
        "## [1.2.0] - 2026-02-01\n\n### Added\n\n- y\n\n"
        "## [1.1.0] - 2026-01-01\n\n### Added\n\n- x\n"
    )
    assert check_changelog(text) == []


def test_patch_ascending_is_a_violation() -> None:
    text = (
        "# Changelog\n\n"
        f"{_UNRELEASED_HEADING}\n\n"
        "## [1.0.0] - 2026-01-01\n\n### Added\n\n- x\n\n"
        "## [1.0.1] - 2026-01-02\n\n### Added\n\n- y\n"
    )
    violations = check_changelog(text)
    assert any("strictly descending" in v for v in violations)


def test_patch_descending_is_not_a_violation() -> None:
    text = (
        "# Changelog\n\n"
        f"{_UNRELEASED_HEADING}\n\n"
        "## [1.0.1] - 2026-01-02\n\n### Added\n\n- y\n\n"
        "## [1.0.0] - 2026-01-01\n\n### Added\n\n- x\n"
    )
    assert check_changelog(text) == []


def test_third_release_out_of_order_is_a_violation() -> None:
    # First adjacent pair (3.0.0, 1.0.0) is correctly descending; only the
    # *second* pair (1.0.0, 2.0.0) is out of order -- a walker that stops
    # after the first comparison would miss this.
    text = (
        "# Changelog\n\n"
        f"{_UNRELEASED_HEADING}\n\n"
        "## [3.0.0] - 2026-03-01\n\n### Added\n\n- z\n\n"
        "## [1.0.0] - 2026-01-01\n\n### Added\n\n- x\n\n"
        "## [2.0.0] - 2026-02-01\n\n### Added\n\n- y\n"
    )
    violations = check_changelog(text)
    assert any("strictly descending" in v for v in violations)


def test_multi_digit_versions_order_numerically_not_lexically() -> None:
    text = (
        "# Changelog\n\n"
        f"{_UNRELEASED_HEADING}\n\n"
        "## [10.0.0] - 2026-02-01\n\n### Added\n\n- y\n\n"
        "## [9.0.0] - 2026-01-01\n\n### Added\n\n- x\n"
    )
    assert check_changelog(text) == []


def test_lexicographic_order_is_a_violation() -> None:
    text = (
        "# Changelog\n\n"
        f"{_UNRELEASED_HEADING}\n\n"
        "## [9.0.0] - 2026-01-01\n\n### Added\n\n- x\n\n"
        "## [10.0.0] - 2026-02-01\n\n### Added\n\n- y\n"
    )
    violations = check_changelog(text)
    assert any("strictly descending" in v for v in violations)


def test_three_releases_fully_descending_is_not_a_violation() -> None:
    text = (
        "# Changelog\n\n"
        f"{_UNRELEASED_HEADING}\n\n"
        "## [3.0.0] - 2026-03-01\n\n### Added\n\n- z\n\n"
        "## [2.0.0] - 2026-02-01\n\n### Added\n\n- y\n\n"
        "## [1.0.0] - 2026-01-01\n\n### Added\n\n- x\n"
    )
    assert check_changelog(text) == []


def test_non_canonical_category_is_a_violation() -> None:
    text = _VALID_SYNTHETIC_CHANGELOG.replace("### Added", "### Additions", 1)
    violations = check_changelog(text)
    assert any("non-canonical category" in v for v in violations)


def test_canonical_category_with_trailing_text_is_a_violation() -> None:
    text = _VALID_SYNTHETIC_CHANGELOG.replace("### Added", "### Added (draft)", 1)
    violations = check_changelog(text)
    assert any("non-canonical category" in v for v in violations)


def test_unreleased_section_with_no_categories_is_not_a_violation() -> None:
    text = "# Changelog\n\n" + _UNRELEASED_HEADING + "\n"
    assert check_changelog(text) == []


def test_category_heading_before_any_section_is_ignored() -> None:
    # A ``### `` line with no enclosing ``## `` heading above it is dropped
    # by the parser, not attributed to the section that follows it.
    text = "# Changelog\n\n### Added\n\n- orphan\n\n" + _UNRELEASED_HEADING + "\n"
    assert check_changelog(text) == []


def test_canonical_category_is_not_a_violation() -> None:
    violations = check_changelog(_VALID_SYNTHETIC_CHANGELOG)
    assert not any("non-canonical category" in v for v in violations)


def test_repeated_category_within_one_section_is_a_violation() -> None:
    text = _VALID_SYNTHETIC_CHANGELOG.replace(
        "### Added\n\n- Something user-observable.\n",
        "### Added\n\n- Something user-observable.\n\n### Added\n\n- Something else.\n",
    )
    violations = check_changelog(text)
    assert any("repeats category" in v for v in violations)


def test_different_case_categories_are_not_treated_as_repeats() -> None:
    text = _VALID_SYNTHETIC_CHANGELOG.replace(
        "### Added\n\n- Something user-observable.\n",
        "### Added\n\n- x.\n\n### added\n\n- y.\n",
    )
    violations = check_changelog(text)
    assert not any("repeats category" in v for v in violations)
    assert any("non-canonical category 'added'" in v for v in violations)


def test_trailing_whitespace_variant_is_still_a_repeat() -> None:
    text = _VALID_SYNTHETIC_CHANGELOG.replace(
        "### Added\n\n- Something user-observable.\n",
        "### Added\n\n- x.\n\n### Added \n\n- y.\n",
    )
    violations = check_changelog(text)
    assert any("repeats category" in v for v in violations)


def test_same_category_in_different_sections_is_not_a_violation() -> None:
    text = (
        "# Changelog\n\n"
        f"{_UNRELEASED_HEADING}\n\n### Added\n\n- y\n\n"
        "## [1.0.0] - 2026-01-01\n\n### Added\n\n- x\n"
    )
    assert check_changelog(text) == []


def test_lowercase_category_is_a_violation() -> None:
    text = _VALID_SYNTHETIC_CHANGELOG.replace("### Added", "### added", 1)
    violations = check_changelog(text)
    assert any("non-canonical category" in v for v in violations)


def test_all_six_canonical_categories_in_one_section_is_not_a_violation() -> None:
    text = (
        "# Changelog\n\n"
        f"{_UNRELEASED_HEADING}\n\n"
        "### Added\n\n- a\n\n"
        "### Changed\n\n- b\n\n"
        "### Deprecated\n\n- c\n\n"
        "### Removed\n\n- d\n\n"
        "### Fixed\n\n- e\n\n"
        "### Security\n\n- f\n"
    )
    assert check_changelog(text) == []


def test_category_heading_with_trailing_space_is_not_a_violation() -> None:
    text = _VALID_SYNTHETIC_CHANGELOG.replace("### Added", "### Added ", 1)
    assert check_changelog(text) == []


def test_repo_relative_docs_link_is_a_violation() -> None:
    text = (
        _VALID_SYNTHETIC_CHANGELOG
        + "\nSee [the contract](docs/ownership-contract.md).\n"
    )
    violations = check_changelog(text)
    assert any("not in project-URL form" in v for v in violations)


def test_repo_relative_dot_slash_link_is_a_violation() -> None:
    text = _VALID_SYNTHETIC_CHANGELOG + "\nSee [it](./CHANGELOG.md).\n"
    violations = check_changelog(text)
    assert any("not in project-URL form" in v for v in violations)


def test_repo_relative_dot_dot_slash_link_is_a_violation() -> None:
    text = _VALID_SYNTHETIC_CHANGELOG + "\nSee [it](../docs/plugins.md).\n"
    violations = check_changelog(text)
    assert any("not in project-URL form" in v for v in violations)


def test_bare_relative_file_link_is_a_violation() -> None:
    # The reviewer's non-blocking finding: a denylist of ``docs/``/``./``/
    # ``../`` prefixes misses a bare, un-prefixed repo file reference. The
    # allowlist form (https:// or #anchor only) catches this in the same
    # pass instead of needing a fourth enumerated prefix.
    text = _VALID_SYNTHETIC_CHANGELOG + "\nSee [the license](LICENSE).\n"
    violations = check_changelog(text)
    assert any("not in project-URL form" in v for v in violations)


def test_project_url_form_link_is_not_a_violation() -> None:
    text = (
        _VALID_SYNTHETIC_CHANGELOG
        + "\nSee [the contract]"
        + "(https://github.com/joshua-stauffer/fitdocs/blob/main/docs/ownership-contract.md).\n"
    )
    assert not any("not in project-URL form" in v for v in check_changelog(text))


def test_in_document_anchor_link_is_not_a_violation() -> None:
    text = _VALID_SYNTHETIC_CHANGELOG + "\nSee [Unreleased](#unreleased).\n"
    assert not any("not in project-URL form" in v for v in check_changelog(text))


def test_no_headings_is_a_violation() -> None:
    violations = check_changelog("just some prose, no headings at all")
    assert any("no '## ' headings found" in v for v in violations)


# ---------------------------------------------------------------------------
# The real file
# ---------------------------------------------------------------------------


def _real_changelog_text() -> str:
    assert _CHANGELOG_PATH.is_file(), f"{_CHANGELOG_PATH} does not exist"
    return _CHANGELOG_PATH.read_text(encoding="utf-8")


def test_real_changelog_has_no_violations() -> None:
    violations = check_changelog(_real_changelog_text())
    assert violations == [], violations


def test_real_changelog_heading_scan_is_non_vacuous() -> None:
    sections = _parse_sections(_real_changelog_text())
    assert sections, "the changelog heading scan found nothing -- check the path"


def test_real_changelog_has_added_entries_under_unreleased() -> None:
    sections = _parse_sections(_real_changelog_text())
    unreleased = next(s for s in sections if s.heading == _UNRELEASED_HEADING)
    assert "Added" in unreleased.categories


def test_real_changelog_carries_the_convention_note() -> None:
    assert CONVENTION_PHRASE in _real_changelog_text()


def test_real_changelog_has_no_released_version_literal() -> None:
    """Requirement 4.7 / task 1.3: nothing has been released yet, so no
    ``## [X.Y.Z] - YYYY-MM-DD`` heading may appear -- only ``[Unreleased]``.
    (``tests/test_version_identity.py`` separately scans for the manifest's
    version literal across the whole repository; this pins the changelog's
    own release-heading count independent of that scan.)"""
    headings = [s.heading for s in _parse_sections(_real_changelog_text())]
    released_headings = [h for h in headings if h != _UNRELEASED_HEADING]
    assert released_headings == []
