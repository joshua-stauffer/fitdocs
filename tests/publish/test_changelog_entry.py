"""Release-note pins for publish-core task 8.4 (Req 16.2).

The entry postdates the last release, so it is read through
``unreleased_since`` anchored at ``V0_2_0``: it must sit in the standing
``[Unreleased]`` section before the cut and in the next release after it,
never in that release or an older one. The version changes are pinned as the
landed literals, not derived from the live constants, so a later bump does not
rewrite what this release said.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests._changelog_view import V0_2_0, read_unreleased_since

_ROOT = Path(__file__).resolve().parents[2]
_CHANGELOG = _ROOT / "CHANGELOG.md"

#: Each clause names one thing the entry must say, keyed by what dropping it
#: would lose.
_CLAUSES: dict[str, str] = {
    "publishing": "`fitdocs publish` turns workout pages into posts",
    "settings table": "`[publish]` settings table",
    "dry run": "a run without `--yes` is a dry run: it sends nothing",
    "yes": "`fitdocs publish --yes` sends them",
    "targets": "`fitdocs publish --targets` lists the configured targets",
    "post region": "The `post` region is yours",
    "published region": "The `published` region is fitdocs-owned",
    "publish key": "The `publish` frontmatter key",
    "contract version": "advances from version 17 to 18 (contract version 18)",
    "document version": "the document format version from 11 to 12",
    "regen": "run `fitdocs regen` once to bring an existing archive's pages",
}

_SERVICE_NAMES = ("intervals", "strava", "fitdocs.ai")


def _unreleased() -> str:
    text = read_unreleased_since(_CHANGELOG, V0_2_0)
    section = text.split("## [Unreleased]", 1)[1].split("\n## [", 1)[0]
    return " ".join(section.split())


@pytest.mark.parametrize("name", sorted(_CLAUSES))
def test_unreleased_entry_carries_the_clause(name: str) -> None:
    assert _CLAUSES[name] in _unreleased(), name


def test_entry_names_no_service() -> None:
    entry = _unreleased()
    # Only the publish-core bullets: the section also carries other features.
    start = entry.index(_CLAUSES["publishing"])
    # Through the end of the bullet that closes the publish-core entry (the
    # next bullet, or the section's end), so text appended to it is scanned.
    after = entry.index("until you do.")
    stop = entry.find(" - ", after)
    if stop == -1:
        stop = len(entry)
    assert start < after < stop
    published = entry[start:stop].lower()
    for name in _SERVICE_NAMES:
        assert name not in published, name


@pytest.mark.parametrize(
    "phrase",
    (
        "`notes`, `workout` and `post` regions",
        "`effort_event`, and `publish`)",
        "fitdocs owns the `published` region",
    ),
)
def test_readme_ownership_summary_names_the_new_regions_and_key(phrase: str) -> None:
    readme = " ".join((_ROOT / "README.md").read_text(encoding="utf-8").split())
    assert phrase in readme, phrase
