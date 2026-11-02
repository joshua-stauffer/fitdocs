"""The deploy contract pinned as literals, and its tie to the relay changelog.

The contract tests (version, environment table, probe paths, image constants,
commands) compare `fitdocs_relay.contract` to values typed out here
(Requirement 9.10); a change to the contract edits these literals. The
changelog tests compare the newest changelog section to the live
DEPLOY_CONTRACT_VERSION, ENVELOPE_VERSION and SEAM_VERSION, so a version bump
also needs a new newest section naming the new versions (Requirement 9.12),
and a section whose deploy contract or seam version advanced over the one
below it must carry the breaking marker.
"""

from __future__ import annotations

import re
from pathlib import Path

from fitdocs_relay import contract
from fitdocs_relay.seam import SEAM_VERSION
from fitdocs_relay.shared.relay_envelope import (
    ENVELOPE_VERSION,
    ROUTE_LIVEZ,
    ROUTE_READYZ,
)

CHANGELOG = Path(__file__).resolve().parents[1] / "CHANGELOG.md"

# (name, required, default, secret, meaning), copied from design.md's table.
PINNED_ENVIRONMENT: list[tuple[str, bool, str | None, bool, str]] = [
    (
        "FITDOCS_RELAY_DATABASE_URL",
        True,
        None,
        True,
        "`sqlite:///relative.db`, `sqlite:////absolute/path.db`, or `postgresql://` / "
        "`postgres://user@host:port/db[?params]`; anything else, including in-memory "
        "SQLite, is an error",
    ),
    (
        "FITDOCS_RELAY_DATABASE_PASSWORD",
        False,
        None,
        True,
        "PostgreSQL password. An error with a SQLite URL, or when the URL already "
        "carries a password",
    ),
    (
        "FITDOCS_RELAY_TOKEN_PEPPER",
        True,
        None,
        True,
        "Token-hashing secret, at least 43 characters (`fitdocs-relay new-pepper` "
        "prints one)",
    ),
    (
        "FITDOCS_RELAY_HOST",
        False,
        "127.0.0.1",
        False,
        "Listen address (the image sets `0.0.0.0`)",
    ),
    ("FITDOCS_RELAY_PORT", False, "8080", False, "Listen port, 1-65535"),
    (
        "FITDOCS_RELAY_FORWARDED_ALLOW_IPS",
        False,
        "",
        False,
        "Comma-separated proxy addresses trusted for forwarded client addresses",
    ),
    (
        "FITDOCS_RELAY_TOKEN_RATE_LIMIT_PER_MINUTE",
        False,
        "60",
        False,
        "Requests per token per minute, 1-100000",
    ),
    (
        "FITDOCS_RELAY_CLIENT_RATE_LIMIT_PER_MINUTE",
        False,
        "20",
        False,
        "Unauthenticated requests per client address per minute, 1-100000",
    ),
    (
        "FITDOCS_RELAY_SHUTDOWN_GRACE_SECONDS",
        False,
        "20",
        False,
        "Graceful-shutdown wait, 0-600",
    ),
    (
        "FITDOCS_RELAY_LOG_LEVEL",
        False,
        "info",
        False,
        "`debug`, `info`, `warning` or `error`",
    ),
    (
        "FITDOCS_RELAY_EXTENSIONS",
        False,
        "",
        False,
        "Comma-separated `module:attribute` references to `RelayExtension` objects",
    ),
]


def test_contract_version_is_one() -> None:
    assert contract.DEPLOY_CONTRACT_VERSION == 1
    assert type(contract.DEPLOY_CONTRACT_VERSION) is int


def test_other_versions_are_plain_ints() -> None:
    assert type(ENVELOPE_VERSION) is int
    assert type(SEAM_VERSION) is int


def test_environment_table_is_pinned_whole() -> None:
    actual = [
        (v.name, v.required, v.default, v.secret, v.meaning)
        for v in contract.ENVIRONMENT
    ]
    assert actual == PINNED_ENVIRONMENT
    assert len(PINNED_ENVIRONMENT) == 11, "the pin lost rows"
    assert contract.ENV_PREFIX == "FITDOCS_RELAY_"


def test_probe_paths() -> None:
    assert ROUTE_LIVEZ == "/livez"
    assert ROUTE_READYZ == "/readyz"


def test_image_constants() -> None:
    assert contract.IMAGE_USER_ID == 10001
    assert contract.IMAGE_PORT == 8080
    assert contract.IMAGE_ENTRYPOINT == ("fitdocs-relay",)
    assert contract.IMAGE_DEFAULT_COMMAND == ("serve",)
    assert contract.IMAGE_ENVIRONMENT == "/opt/fitdocs-relay"


def test_command_list() -> None:
    assert contract.COMMANDS == ("serve", "migrate", "principal", "token", "new-pepper")


# ---- the changelog tie (Requirement 9.12) ----

_LINE = re.compile(
    r"^- (Deploy contract|Envelope|Seam) version: ([0-9]+)$", re.MULTILINE
)


def newest_section(text: str) -> str:
    """The text of the first `## ` section of a changelog."""
    sections = re.split(r"^## ", text, flags=re.MULTILINE)[1:]
    assert sections, "the changelog has no section"
    return sections[0]


def named_versions(section: str) -> dict[str, list[int]]:
    found: dict[str, list[int]] = {}
    for label, number in _LINE.findall(section):
        found.setdefault(label, []).append(int(number))
    return found


def test_newest_changelog_section_names_current_versions() -> None:
    section = newest_section(CHANGELOG.read_text(encoding="utf-8"))
    assert named_versions(section) == {
        "Deploy contract": [contract.DEPLOY_CONTRACT_VERSION],
        "Envelope": [ENVELOPE_VERSION],
        "Seam": [SEAM_VERSION],
    }


def test_newest_section_is_the_first_not_the_last() -> None:
    text = (
        "# Changelog\n\n"
        "## 2.0.0\n\n- Deploy contract version: 2\n- Envelope version: 3\n"
        "- Seam version: 4\n\n"
        "## 1.0.0\n\n- Deploy contract version: 1\n- Envelope version: 1\n"
        "- Seam version: 1\n"
    )
    assert named_versions(newest_section(text)) == {
        "Deploy contract": [2],
        "Envelope": [3],
        "Seam": [4],
    }


def test_a_missing_or_repeated_line_is_not_a_match() -> None:
    missing = "## 1\n\n- Deploy contract version: 1\n- Seam version: 1\n"
    assert "Envelope" not in named_versions(missing)
    twice = "## 1\n\n- Seam version: 1\n- Seam version: 2\n"
    assert named_versions(twice)["Seam"] == [1, 2]


# ---- a breaking change is called out (Requirement 9.12) ----

BREAKING_MARKER = "**Breaking for deployments:**"


def sections_of(text: str) -> list[str]:
    return re.split(r"^## ", text, flags=re.MULTILINE)[1:]


def unmarked_advances(text: str) -> list[int]:
    """Indexes of sections whose deploy contract or seam version advanced over
    the next-older section without carrying the breaking marker."""
    sections = sections_of(text)
    bad: list[int] = []
    for i in range(len(sections) - 1):
        new, old = named_versions(sections[i]), named_versions(sections[i + 1])
        advanced = any(new.get(k) != old.get(k) for k in ("Deploy contract", "Seam"))
        if advanced and BREAKING_MARKER not in sections[i]:
            bad.append(i)
    return bad


def _two(new_contract: int, new_seam: int, marker: bool) -> str:
    note = f"- {BREAKING_MARKER} x\n" if marker else "- x\n"
    return (
        f"## 2\n\n- Deploy contract version: {new_contract}\n"
        f"- Envelope version: 1\n- Seam version: {new_seam}\n{note}\n"
        "## 1\n\n- Deploy contract version: 1\n- Envelope version: 1\n"
        "- Seam version: 1\n"
    )


def test_real_changelog_marks_every_advance() -> None:
    text = CHANGELOG.read_text(encoding="utf-8")
    assert sections_of(text), "the walk saw no section"
    assert unmarked_advances(text) == []


def test_advance_needs_the_marker() -> None:
    assert unmarked_advances(_two(2, 1, marker=False)) == [0]
    assert unmarked_advances(_two(1, 2, marker=False)) == [0]
    assert unmarked_advances(_two(2, 1, marker=True)) == []
    assert unmarked_advances(_two(1, 2, marker=True)) == []


def test_no_advance_needs_no_marker() -> None:
    assert unmarked_advances(_two(1, 1, marker=False)) == []
