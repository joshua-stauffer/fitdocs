"""Pins for the ``## Strava`` section of ``docs/connectors.md``
(strava-publish design.md "ConnectorsDocs", task 7.1; Requirements 5.10,
16.4, 16.5, 17.1, 17.7).

The two mapping tables are parsed from the page and compared with
``PUBLISH_MAPPING`` and ``UPLOAD_MAPPING`` in both directions; the settings
table with the connector's own parsing; the quoted command output and notes
with the code that prints them; the limits with the codec's constants. The
heading rows and the neutral-scan entry live in ``test_docs.py``.
"""

from __future__ import annotations

import inspect
import re
from collections.abc import Mapping
from pathlib import Path
from urllib.parse import urlparse

import pytest

from fitdocs import cli
from fitdocs.connectors import disconnect
from fitdocs.connectors.credentials import env_var_name
from fitdocs.connectors.errors import ConnectorSettingsError
from fitdocs.connectors.protocol import PublishCode, SettingsContext
from fitdocs.connectors.relay import DEFAULT_RELAY_URL
from fitdocs.connectors.relay_codes import RelayCode
from fitdocs.connectors.relay_targets import (
    MAX_DESCRIPTION_CHARS,
    MAX_FIT_BYTES,
    MAX_TITLE_CHARS,
    PUBLISH_OUTCOMES,
    UPLOAD_OUTCOMES,
)
from fitdocs.connectors.strava import (
    PUBLISH_MAPPING,
    UPLOAD_MAPPING,
    StravaConnector,
)

_DOC = Path(__file__).resolve().parents[2] / "docs" / "connectors.md"
_ID = "0123456789abcdef0123456789abcdef"


def _text() -> str:
    return _DOC.read_text(encoding="utf-8")


def _section(text: str | None = None, heading: str = "Strava") -> str:
    source = _text() if text is None else text
    match = re.search(
        rf"^## {re.escape(heading)}\n(.*?)(?=\n## |\Z)", source, re.S | re.M
    )
    assert match, f"the ## {heading} section is missing from docs/connectors.md"
    return match.group(1)


def _flat(text: str) -> str:
    return " ".join(text.split())


def _subsection(name: str, text: str | None = None) -> str:
    body = _section(text)
    match = re.search(rf"^### {re.escape(name)}\n(.*?)(?=\n### |\Z)", body, re.S | re.M)
    assert match, f"the ### {name} subsection is missing"
    return match.group(1)


def _table_after(body: str, lead_in: str) -> dict[str, str]:
    """The two-column table that follows the line ``lead_in``, as a
    dict; a repeated first cell is an error."""
    start = body.index(f"\n{lead_in}\n\n") + len(lead_in) + 3
    rows: dict[str, str] = {}
    for line in body[start:].splitlines()[2:]:
        if not line.startswith("|"):
            break
        cells = [c.strip().strip("`") for c in line.strip("|").split("|")]
        assert len(cells) == 2, line
        assert cells[0] not in rows, f"duplicate row {cells[0]!r}"
        rows[cells[0]] = cells[1]
    return rows


def _as_table(mapping: Mapping[RelayCode, PublishCode]) -> dict[str, str]:
    return {code.value: result.value for code, result in mapping.items()}


# --- the mapping tables ----------------------------------------------------


def test_the_publish_table_is_the_publish_mapping_in_both_directions() -> None:
    """Mutation: deleting a row, swapping a code, or adding a row on the page
    (each by editing the page text) reds this; so does changing the mapping."""
    page = _table_after(_subsection("Publishing and uploads"), "The publish request:")
    assert page == _as_table(PUBLISH_MAPPING)
    assert len(page) == len(RelayCode)


def test_the_upload_table_is_the_upload_mapping_in_both_directions() -> None:
    page = _table_after(_subsection("Publishing and uploads"), "The upload request:")
    assert page == _as_table(UPLOAD_MAPPING)
    assert len(page) == len(RelayCode)


def test_the_two_tables_differ_where_the_mappings_differ() -> None:
    """The two mappings differ, so each table test above compares a table
    with its own mapping and not with the other."""
    assert _as_table(PUBLISH_MAPPING) != _as_table(UPLOAD_MAPPING)


def test_the_accepted_outcomes_are_the_routes_sets() -> None:
    body = _flat(_subsection("Publishing and uploads"))
    match = re.search(
        r"The publish request accepts (.*?) and the upload request accepts (.*?);",
        body,
    )
    assert match, "the accepted-outcome sentence is missing"
    publish = set(re.findall(r"`([a-z_]+)`", match.group(1)))
    upload = set(re.findall(r"`([a-z_]+)`", match.group(2)))
    assert publish == PUBLISH_OUTCOMES
    assert upload == UPLOAD_OUTCOMES


# --- the settings table ----------------------------------------------------


def test_the_settings_table_agrees_with_parse_settings() -> None:
    body = _section()
    start = body.index("| Key | Required | Meaning |")
    rows = {}
    for line in body[start:].splitlines()[2:]:
        if not line.startswith("|"):
            break
        key, required, _meaning = (c.strip() for c in line.strip("|").split("|", 2))
        rows[key.strip("`")] = required
    assert rows == {"relay": "yes", "upload": "no"}

    connector = StravaConnector()
    context = SettingsContext(data_root=Path("."), inbox=Path("."))
    with pytest.raises(ConnectorSettingsError):
        connector.parse_settings({}, context)
    parsed = connector.parse_settings({"relay": "relay"}, context)
    assert parsed.upload is False
    assert "`false` by default" in _flat(body)


# --- the quoted output and notes -------------------------------------------


_CONNECT_LINES = (
    "open this address in a browser to connect this instance:",
    "Continue only if the page shows this same code.",
    "This attempt expires in",
    "Could not open a browser; open the address above yourself.",
)


def test_the_connect_output_quotes_the_cli() -> None:
    page = _flat(_subsection("Connecting a Strava instance"))
    source = inspect.getsource(cli)
    for line in _CONNECT_LINES:
        assert line in page, line
        assert line in source, line
    # The success line is the browser branch's own, not any "connected." in cli.
    assert "`strava: connected.`" in page
    assert 'f"{name}: connected."' in inspect.getsource(cli._connect_browser)


def test_the_disconnect_notes_are_the_codes_notes() -> None:
    page = _flat(_subsection("Disconnecting a Strava instance"))
    local = (
        "stays at the relay until this instance is connected and disconnected "
        "again, or access is revoked in Strava's settings"
    )
    unknown = (
        "the relay no longer knows the token and that a remaining Strava "
        "connection can be revoked in Strava's settings"
    )
    assert local in page
    assert local in disconnect.CONSENT_LOCAL_ONLY_NOTE
    assert unknown in page
    assert "the relay no longer knows this token" in disconnect.CONSENT_UNKNOWN_NOTE
    assert "a remaining Strava connection can be revoked in Strava's settings" in (
        disconnect.CONSENT_UNKNOWN_NOTE
    )
    assert "strava: disconnected." in page


def test_the_environment_variable_is_the_connectors() -> None:
    assert f"`{env_var_name('strava', 'token')}`" in _section()


# --- limits ----------------------------------------------------------------


def test_the_stated_limits_are_the_codecs() -> None:
    page = _flat(_subsection("Publishing and uploads"))
    assert MAX_FIT_BYTES == 16 * 1024 * 1024
    assert "over 16 MiB" in page
    assert f"over {MAX_TITLE_CHARS} characters" in page
    assert f"over {MAX_DESCRIPTION_CHARS} characters" in page


# --- wording ---------------------------------------------------------------

_BRAND = re.compile(
    r"\b(Compatible with|Connect with|View on|Powered by|Sign in with|Login with|"
    r"Log in with|Works with|Built on|Made with)\s+Strava\b",
    re.I,
)
_ALLOWED_BRAND = {"Compatible with Strava", "View on Strava"}


def test_only_the_permitted_brand_phrases_appear() -> None:
    flat_found = {m.group(0) for m in _BRAND.finditer(_flat(_section()))}
    assert flat_found == _ALLOWED_BRAND


def test_the_section_names_no_strava_host() -> None:
    section = _section()
    assert not re.search(r"strava\.[a-z]", section, re.I)
    hosts = {
        urlparse(url).hostname for url in re.findall(r"https?://[^\s\"')>\]]+", section)
    }
    assert hosts == {"api.fitdocs.ai", "github.com"}
    assert DEFAULT_RELAY_URL.endswith("api.fitdocs.ai")


def test_the_default_relays_policy_address_is_stated() -> None:
    address = re.escape(f"{DEFAULT_RELAY_URL}/privacy")
    assert re.search(address + r"(?![\w/-])", _flat(_section()))


def test_the_prerequisites_are_stated() -> None:
    page = _flat(_section())
    assert "has to be connected before the Strava instance can be" in page
    assert "relay instance's `url` must be the relay's public address" in page
    assert "offer Strava" in page
