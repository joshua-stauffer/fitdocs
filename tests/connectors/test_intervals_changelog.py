"""Release-note pins for intervals-publish task 4.3 (Req 11.4).

The entry postdates the last release, so it is read through
``unreleased_since`` anchored at ``V0_2_0``: it must sit in the standing
``[Unreleased]`` section before the cut and in the next release after it,
never in 0.2.0 or an older section.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from fitdocs.connectors.intervals import IntervalsSettings
from tests._changelog_view import V0_2_0, read_unreleased_since

_CHANGELOG = Path(__file__).resolve().parents[2] / "CHANGELOG.md"

_ADDED: dict[str, str] = {
    "publishing": "Publishing to intervals.icu",
    "update": "the activity's name and description become the post's",
    "trigger": "updated by `fitdocs publish --yes`",
    "upload": "uploads the page's base `.fit` file",
    "schema": "`fitdocs.toml` settings schema (additive)",
    "action": "Action: none; add the key only to enable the upload",
    "switch": "`publish_upload = true`",
    "link": "link that goes straight to the activity",
}
_CHANGED: dict[str, str] = {
    "writes": "The `intervals` connector now writes to the account",
    "network": "names `fitdocs publish --yes` among the commands that make connector",
    "no contract change": "advances no contract version",
    "no action": "Action: none.",
    "reads": "`fitdocs connect` and `fitdocs pull` still only read",
}


def _section(heading: str) -> str:
    view = read_unreleased_since(_CHANGELOG, V0_2_0)
    unreleased = view.split("## [Unreleased]", 1)[1].split("\n## [", 1)[0]
    body = unreleased.split(f"### {heading}", 1)[1].split("\n### ", 1)[0]
    return " ".join(body.split())


def _bullet(text: str, start: str) -> str:
    bullets = [b for b in ("- " + p for p in text.split(" - ")) if start in b[:80]]
    assert len(bullets) == 1, start
    return bullets[0]


@pytest.mark.parametrize("name", sorted(_ADDED))
def test_added_entry_carries_the_clause(name: str) -> None:
    bullet = _bullet(_section("Added"), _ADDED["publishing"])
    assert _ADDED[name] in bullet, name


def test_added_entry_states_the_default_the_code_has() -> None:
    default = str(IntervalsSettings(sources=frozenset()).publish_upload).lower()
    bullet = _bullet(_section("Added"), _ADDED["publishing"])
    assert f"optional `publish_upload` key, default `{default}`" in bullet


@pytest.mark.parametrize("name", sorted(_CHANGED))
def test_changed_entry_carries_the_clause(name: str) -> None:
    bullet = _bullet(_section("Changed"), _CHANGED["writes"])
    assert _CHANGED[name] in bullet, name


def test_entry_is_not_in_the_0_2_0_section_or_older() -> None:
    view = read_unreleased_since(_CHANGELOG, V0_2_0)
    released = " ".join(view.split("\n## [", 2)[2].split())
    for clause in (*_ADDED.values(), *_CHANGED.values()):
        assert clause not in released, clause
