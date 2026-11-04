"""Release-note pins for strava-publish task 7.5 (Req 16.5, 17.5).

The root entries postdate the last release, so they are read through
``unreleased_since`` anchored at ``V0_2_0``. The relay changelog is read as a
file; its newest section is the first ``## `` heading.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from tests._changelog_view import V0_2_0, read_unreleased_since

_ROOT = Path(__file__).resolve().parents[2]
_CHANGELOG = _ROOT / "CHANGELOG.md"
_RELAY_CHANGELOG = _ROOT / "relay" / "CHANGELOG.md"

_BRAND = re.compile(
    r"\b(Compatible with|Connect with|View on|Powered by|Sign in with|Login with|"
    r"Log in with|Works with|Built on|Made with)\s+Strava\b",
    re.I,
)

_ADDED_CONNECTOR: dict[str, str] = {
    "brand": "Compatible with Strava",
    "kind": '`connector = "strava"`',
    "relay key": '`relay = "RELAY"`',
    "upload key": "optional `upload` key, default `false`",
    "connect": "run `fitdocs connect NAME`",
    "schema": "`fitdocs.toml` settings schema (additive)",
    "action": "Action: none; add the instance table to use it.",
}
_ADDED_NO_BROWSER: dict[str, str] = {
    "flag": "`fitdocs connect NAME --no-browser`",
    "opens": "opens the connect page address in your browser",
    "action": "Action: none; add the flag only to stop the browser opening.",
}
_ADDED_DISCONNECT: dict[str, str] = {
    "command": "`fitdocs disconnect NAME` for a Strava instance",
    "local": "`--local-only` removes the file without contacting the relay",
    "stays": "stays at the relay",
    "revoked": "or access is revoked in Strava's settings",
    "action": "Action: run `fitdocs disconnect NAME`",
}
_CHANGED_BROWSER: dict[str, str] = {
    "style": "The credentials file's `auth_style` value `oauth-browser`",
    "supported": "is now supported",
    "action": "Action: none for existing files.",
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


@pytest.mark.parametrize("name", sorted(_ADDED_CONNECTOR))
def test_connector_entry_carries_the_clause(name: str) -> None:
    bullet = _bullet(_section("Added"), "The `strava` connector")
    assert _ADDED_CONNECTOR[name] in bullet, name


@pytest.mark.parametrize("name", sorted(_ADDED_NO_BROWSER))
def test_no_browser_entry_carries_the_clause(name: str) -> None:
    bullet = _bullet(_section("Added"), "`fitdocs connect NAME --no-browser`")
    assert _ADDED_NO_BROWSER[name] in bullet, name


@pytest.mark.parametrize("name", sorted(_ADDED_DISCONNECT))
def test_disconnect_entry_carries_the_clause(name: str) -> None:
    bullet = _bullet(_section("Added"), "Disconnecting a Strava instance")
    assert _ADDED_DISCONNECT[name] in bullet, name


@pytest.mark.parametrize("name", sorted(_CHANGED_BROWSER))
def test_browser_consent_entry_carries_the_clause(name: str) -> None:
    bullet = _bullet(
        _section("Changed"), "The credentials file's `auth_style` value `oauth-browser`"
    )
    assert _CHANGED_BROWSER[name] in bullet, name


def test_the_entries_use_no_brand_phrase_but_compatible_with_strava() -> None:
    new = " ".join(
        (
            _bullet(_section("Added"), "The `strava` connector"),
            _bullet(_section("Added"), "`fitdocs connect NAME --no-browser`"),
            _bullet(_section("Added"), "Disconnecting a Strava instance"),
            _bullet(
                _section("Changed"),
                "The credentials file's `auth_style` value `oauth-browser`",
            ),
        )
    )
    assert {m.group(0) for m in _BRAND.finditer(new)} == {"Compatible with Strava"}


def test_the_entries_are_not_in_the_0_2_0_section_or_older() -> None:
    view = read_unreleased_since(_CHANGELOG, V0_2_0)
    released = " ".join(view.split("\n## [", 2)[2].split())
    for clause in (
        *_ADDED_CONNECTOR.values(),
        *_ADDED_NO_BROWSER.values(),
        *_ADDED_DISCONNECT.values(),
        *_CHANGED_BROWSER.values(),
    ):
        assert clause not in released, clause


# ---- the relay changelog's Strava section ---------------------------------

_COMMANDS = (
    "`strava webhook create`",
    "`strava webhook show`",
    "`strava webhook delete`",
    "`reencrypt`",
    "`new-encryption-key`",
)
_SCHEMA = ("Migration `0002_target_custody`", "additive")
_RESTATED = (
    "- Deploy contract version: 1",
    "- Envelope version: 1",
    "- Seam version: 1",
)


def _relay_sections() -> list[str]:
    text = _RELAY_CHANGELOG.read_text(encoding="utf-8")
    return re.split(r"^## ", text, flags=re.MULTILINE)[1:]


def _newest() -> str:
    return _relay_sections()[0]


@pytest.mark.parametrize("command", _COMMANDS)
def test_newest_relay_section_names_each_command(command: str) -> None:
    assert command in _newest()


@pytest.mark.parametrize("clause", _SCHEMA)
def test_newest_relay_section_records_the_schema_change(clause: str) -> None:
    assert clause in _newest()


@pytest.mark.parametrize("line", _RESTATED)
def test_newest_relay_section_restates_the_versions(line: str) -> None:
    assert line in _newest().splitlines()


def test_the_relay_section_is_new_and_the_first_release_section_stays() -> None:
    sections = _relay_sections()
    assert len(sections) >= 2
    assert "First release of the relay server" in sections[1]
    assert "First release of the relay server" not in sections[0]


def test_the_relay_section_uses_no_brand_phrase_and_marks_nothing_breaking() -> None:
    newest = _newest()
    assert not _BRAND.findall(newest)
    assert "Breaking for deployments" not in newest
