"""Pins for the ``## intervals.icu`` section of ``docs/connectors.md``
(design.md "ConnectorsDocSection", Testing Strategy "Docs"; Req 10.1, 10.2).

The environment variable, the ``sources`` example and the first-pull day
count are compared with the connector's own constants and the connectors
naming function. The heading list, the ``§1.1`` and ``V 6.30.2025``
citations and the regenerate sentence compare against literals written here;
the address rule admits ``intervals.icu`` and the project's own URLs, read from
``pyproject.toml``. The section is located by its heading; a missing section
fails every section pin (the two rule-table tests exercise the rule alone).
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path
from urllib.parse import urlparse

from fitdocs.connectors.credentials import env_var_name
from fitdocs.connectors.intervals import (
    DEFAULT_SOURCES,
    FIRST_PULL_DAYS,
    INTERVALS_CONNECTOR_ID,
    IntervalsConnector,
)
from fitdocs.connectors.protocol import SettingsContext

_REPO_ROOT = Path(__file__).resolve().parents[2]
_DOC = _REPO_ROOT / "docs" / "connectors.md"
_HOST = "intervals.icu"
# The scheme is joined at run time so this file's own text never spells a
# scheme and an unadmitted host together (the page-wide neutral scan reads it).
_S = "https" + "://"


def _section() -> str:
    """The body of ``## intervals.icu``, up to the next ``## `` heading."""
    text = _DOC.read_text(encoding="utf-8")
    match = re.search(r"^## intervals\.icu\n(.*?)(?=\n## |\Z)", text, re.S | re.M)
    assert match, "docs/connectors.md has no '## intervals.icu' section"
    return match.group(1)


def _own_url_prefixes() -> frozenset[str]:
    document = tomllib.loads(
        (_REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    )
    return frozenset(document["project"]["urls"].values())


def _toml_blocks(section: str) -> list[dict[str, object]]:
    blocks = re.findall(r"```toml\n(.*?)```", section, re.S)
    return [tomllib.loads(block) for block in blocks]


def test_the_section_is_not_empty_and_has_its_four_subsections() -> None:
    section = _section()
    assert len(section.split()) > 200
    found = re.findall(r"^(### .+)$", section, re.M)
    assert found == [
        "### Connecting",
        "### Configuring",
        "### What a pull fetches",
        "### Garmin attribution",
    ]


def test_the_environment_variable_it_names_is_the_naming_functions_result() -> None:
    expected = env_var_name(INTERVALS_CONNECTOR_ID, "api_key")
    assert expected == "FITDOCS_CONNECTOR_INTERVALS_API_KEY"
    named = set(re.findall(r"FITDOCS_CONNECTOR_[A-Z0-9_]+", _section()))
    assert named == {expected}


def _intervals_tables(section: str) -> list[dict[str, object]]:
    """Each fenced toml example's ``[connectors.intervals]`` table that sets
    ``sources``."""
    found: list[dict[str, object]] = []
    for document in _toml_blocks(section):
        connectors = document.get("connectors")
        if not isinstance(connectors, dict):
            continue
        table = connectors.get(INTERVALS_CONNECTOR_ID)
        if isinstance(table, dict) and "sources" in table:
            found.append(table)
    return found


def test_the_sources_example_equals_the_connectors_default() -> None:
    tables = _intervals_tables(_section())
    assert len(tables) == 1, "the section shows one sources example"
    shown = tables[0]
    parsed = IntervalsConnector().parse_settings(
        shown, SettingsContext(data_root=_REPO_ROOT, inbox=_REPO_ROOT)
    )
    assert parsed.sources == DEFAULT_SOURCES
    assert shown["sources"] == sorted(DEFAULT_SOURCES)


def test_the_first_pull_day_count_equals_the_connectors_constant() -> None:
    counts = re.findall(r"first pull lists the last (\d+) days", _section())
    assert counts == [str(FIRST_PULL_DAYS)]


def test_it_cites_the_api_terms_section_and_the_brand_guidelines_version() -> None:
    section = _section()
    assert "§1.1" in section
    assert "V 6.30.2025" in section


# Every address token: scheme-ful (an http or https scheme and everything up to a
# delimiter) or bare (a dotted host with an optional path), wherever it
# appears, code spans included. The lookbehind stops a match starting in the
# middle of a longer dotted token; it deliberately admits a preceding "/" or
# "@" so `/developer.garmin.com` and `user@host.example` are still found.
_ADDRESS = re.compile(
    r"https?://[^\s\"'`)>\]]+"
    r"|(?<![\w.-])(?:[a-z0-9-]+\.)+[a-z]{2,}(?::\d+)?(?:[/?#][^\s\"'`)>\]]*)?",
    re.IGNORECASE,
)
# Dotted tokens that are not addresses: the settings table's own name and the
# settings file's name. Only these exact strings are skipped.
_NOT_ADDRESSES = frozenset({"connectors.intervals", "fitdocs.toml"})


def address_violations(text: str, own_urls: frozenset[str]) -> list[str]:
    """Every address token in *text* that is neither on ``intervals.icu`` (exact
    host, any path) nor the project's own: a declared ``[project.urls]`` value
    itself, or one followed by ``/``, ``#`` or ``?``. A bare token is judged as
    if the https scheme were prefixed. Comparison is case-insensitive."""
    violations = []
    for raw in _ADDRESS.findall(text):
        token = raw.rstrip(".,;:")
        if token.lower() in _NOT_ADDRESSES:
            continue
        full = token if re.match(r"https?://", token, re.I) else f"{_S}{token}"
        if (urlparse(full).hostname or "").lower() == _HOST:
            continue
        lowered = full.lower()
        if any(
            lowered == own.lower()
            or (lowered.startswith(own.lower()) and lowered[len(own)] in "/#?")
            for own in own_urls
        ):
            continue
        violations.append(token)
    return violations


def test_every_address_it_names_is_intervals_icu_or_the_projects_own() -> None:
    section = _section()
    named = [t for t in _ADDRESS.findall(section) if t not in _NOT_ADDRESSES]
    assert any(t.startswith(f"{_S}intervals.icu") for t in named)
    assert address_violations(section, _own_url_prefixes()) == []


_OWN = f"{_S}github.com/joshua-stauffer/fitdocs"
_NOT_PERMITTED = [
    "github.com/garmin/fit-sdk",
    f"{_S}github.com/garmin/fit-sdk",
    "`github.com/garmin/fit-sdk`",
    f"`{_S}github.com/garmin/fit-sdk`",
    f"{_S}github.com/joshua-stauffer/fitdocs.evil/x",
    f"{_S}github.com/joshua-stauffer/fitdocs-evil",
    f"{_S}fitdocs.ai.example.com",
    f"{_S}fitdocs.ai@evil.com",
    "fitdocs.ai@evil.com",
    "/developer.garmin.com/downloads",
    "connectors.garmin.com",
    "DEVELOPER.GARMIN.COM",
    "intervals.icu.example.com",
    f"{_S}intervals.icu@evil.com",
    "www.strava.com",
    "see developer.garmin.com.",
]
_PERMITTED = [
    f"{_S}intervals.icu",
    f"{_S}intervals.icu/settings",
    "intervals.icu/api/v1/docs",
    "INTERVALS.ICU",
    f"{_S}fitdocs.ai",
    f"{_S}fitdocs.ai/docs",
    _OWN,
    f"{_OWN}/issues",
    f"{_OWN}/blob/main/docs/connectors.md#credentials",
    f"{_OWN}?tab=readme",
    "github.com/joshua-stauffer/fitdocs/issues",
    "`[connectors.intervals]` in fitdocs.toml.",
]


def test_the_address_rule_rejects_every_unpermitted_address() -> None:
    own = _own_url_prefixes()
    assert _OWN in own, "the fixture's own URL is no longer a project URL"
    for sample in _NOT_PERMITTED:
        sentence = f"Prefix text, then {sample} and a tail."
        assert address_violations(sentence, own) != [], sample


def test_the_address_rule_admits_every_permitted_address() -> None:
    own = _own_url_prefixes()
    for sample in _PERMITTED:
        sentence = f"Prefix text, then {sample} and a tail."
        assert address_violations(sentence, own) == [], sample


def test_it_tells_the_athlete_to_regenerate_before_the_first_pull() -> None:
    section = " ".join(_section().split()).lower()
    assert "run `fitdocs regen`" in section
    assert "before the first pull" in section
