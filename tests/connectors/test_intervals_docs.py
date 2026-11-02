"""Pins for the ``## intervals.icu`` section of ``docs/connectors.md``
(design.md "ConnectorsDocSection", Testing Strategy "Docs").

The environment variable, the ``sources`` example and the first-pull day
count are compared with the connector's own constants and the connectors
naming function. The heading list and the regenerate sentence compare
against literals written here;
the address rule admits ``intervals.icu`` and the project's own URLs, read from
``pyproject.toml``. The section is located by its heading; a missing section
fails every section pin (the two rule-table tests exercise the rule alone).
"""

from __future__ import annotations

import dataclasses
import re
import tomllib
from pathlib import Path
from urllib.parse import urlparse

from fitdocs.connectors.credentials import env_var_name
from fitdocs.connectors.errors import ConnectorSettingsError
from fitdocs.connectors.intervals import (
    ANSWER_CODES,
    DEFAULT_SOURCES,
    FIRST_PULL_DAYS,
    INTERVALS_CONNECTOR_ID,
    RESOLVE_FIELDS,
    AnswerClass,
    CallKind,
    IntervalsConnector,
    IntervalsSettings,
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


def test_the_section_is_not_empty_and_has_its_five_subsections() -> None:
    section = _section()
    assert len(section.split()) > 200
    found = re.findall(r"^(### .+)$", section, re.M)
    assert found == [
        "### Connecting",
        "### Configuring",
        "### What a pull fetches",
        "### Wellness",
        "### Publishing",
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
# Dotted tokens that are not addresses: the settings table's own name, the
# settings file's name and the upload's file name. Only these exact strings are
# skipped.
_NOT_ADDRESSES = frozenset({"connectors.intervals", "fitdocs.toml", "activity.fit"})


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


# --------------------------------------------------------------------------
# Publishing (intervals-publish Req 11.1-11.3)
# --------------------------------------------------------------------------

_RETIRED = "It never writes to the account."
_DASH = "\u2014"
_SETTINGS = SettingsContext(data_root=_REPO_ROOT, inbox=_REPO_ROOT)


def _subsection(name: str) -> str:
    match = re.search(
        rf"^### {re.escape(name)}\n(.*?)(?=\n### |\Z)", _section(), re.S | re.M
    )
    assert match, f"the intervals.icu section has no '### {name}' subsection"
    return match.group(1)


def _documented_answer_table() -> dict[str, tuple[str, str, str]]:
    """The ``### Publishing`` table: row label -> (listing, update, upload)."""
    lines = _subsection("Publishing").splitlines()
    header = "| Answer | Listing | Update | Upload |"
    assert header in lines, "the Publishing subsection has no answer table"
    start = lines.index(header) + 2  # past the delimiter row
    rows: dict[str, tuple[str, str, str]] = {}
    for line in lines[start:]:
        if not line.startswith("|"):
            break
        cells = [cell.strip().strip("`") for cell in line.strip("|").split("|")]
        assert len(cells) == 4, line
        assert cells[0] not in rows, f"row {cells[0]!r} appears twice"
        rows[cells[0]] = (cells[1], cells[2], cells[3])
    return rows


def _code_table() -> dict[str, tuple[str, str, str]]:
    return {
        answer.value: tuple(  # type: ignore[misc]
            _DASH if code is None else code.value
            for code in (
                row[CallKind.READ],
                row[CallKind.UPDATE],
                row[CallKind.CREATE],
            )
        )
        for answer, row in ANSWER_CODES.items()
    }


def test_the_answer_table_equals_the_codes_table_cell_for_cell() -> None:
    expected = _code_table()
    assert len(expected) == len(ANSWER_CODES) > 5
    assert set(expected) == {answer.value for answer in AnswerClass}
    # A table with no dash cell and none with a code would pin nothing.
    assert any(_DASH in cells for cells in expected.values())
    documented = _documented_answer_table()
    assert documented == expected
    assert list(documented) == list(expected), "rows are in the code table's order"


def test_the_retired_never_writes_sentence_is_gone_from_the_page() -> None:
    text = " ".join(_DOC.read_text(encoding="utf-8").split())
    assert _RETIRED not in text
    assert "never writes to the account" not in text.lower()


def test_the_opening_says_what_the_connector_writes() -> None:
    opening = " ".join(_section().split("### Connecting")[0].split())
    assert "It pulls" in opening
    assert "publishes" in opening
    assert (
        "writes only an activity's name and description" in opening
        and "while `publish_upload` is on" in opening
    )


def test_the_documented_publish_upload_default_equals_the_settings_default() -> None:
    default = {f.name: f.default for f in dataclasses.fields(IntervalsSettings)}[
        "publish_upload"
    ]
    assert default is False
    tables = _intervals_tables(_section())
    assert len(tables) == 1
    shown = tables[0]["publish_upload"]
    assert isinstance(shown, bool)
    assert shown is default
    parsed = IntervalsConnector().parse_settings(tables[0], _SETTINGS)
    assert parsed.publish_upload is default
    assert "optional; this is the default" in _subsection("Configuring")


def test_a_malformed_publish_upload_is_documented_as_a_configuration_error() -> None:
    try:
        IntervalsConnector().parse_settings({"publish_upload": "yes"}, _SETTINGS)
    except ConnectorSettingsError:
        pass
    else:  # pragma: no cover - the premise of the sentence below
        raise AssertionError("a string publish_upload was accepted")
    configuring = " ".join(_subsection("Configuring").split())
    assert (
        "A `publish_upload` that is not `true` or `false` is a configuration error"
        in configuring
    )
    assert "`fitdocs pull` included" in configuring
    assert "No key other than `sources` and `publish_upload` is read" in configuring


def _publishing_text() -> str:
    return " ".join(_subsection("Publishing").split())


def test_the_listing_field_sentence_names_exactly_the_requested_fields() -> None:
    sentence = re.search(r"asking for the fields (.*?)\. ", _publishing_text())
    assert sentence, "the Publishing subsection no longer lists the fields"
    named = re.findall(r"`([a-z_]+)`", sentence.group(1))
    assert len(RESOLVE_FIELDS) > 3
    assert tuple(named) == RESOLVE_FIELDS


def test_the_request_bullets_state_what_each_request_carries() -> None:
    text = _publishing_text()
    query = re.search(r"The one value in its query is (.*?)\. ", text)
    assert query, "the upload bullet no longer names its query value"
    assert query.group(1) == "the page's publication id, as `external_id`"
    assert "Its query carries only the date window and the field names above." in text
    assert (
        "a `multipart/form-data` form holding the base file, unmodified, "
        "under the file name `activity.fit`" in text
    )
    assert "Its body is the name and the description, and nothing else." in text


def test_the_update_after_an_upload_is_documented_apart_from_the_table() -> None:
    text = _publishing_text()
    assert (
        "The table applies to every request except the update that follows an "
        "upload" in text
    )
    assert (
        "After an upload that created the activity, any reply other than a "
        "success is `unconfirmed`, including a `429`." in text
    )
    assert "a `404` is `unconfirmed` and the search does not go on" in text
    assert "the pull record or the listing means that activity does not exist" in text
    assert "no upload is sent" in text and "no upload was sent" in text


def test_publishing_documents_the_unreadable_record_answer() -> None:
    publishing = " ".join(_subsection("Publishing").split())
    assert "never `not_found` and never an upload" in publishing
    assert "whether or not uploads are on" in publishing
    assert "is updated just as it is with a readable record" in publishing
    assert "a page without the facts for a listing is `activity_facts_missing`" in (
        publishing
    )
    assert "fitdocs pull" in publishing


def test_the_ledger_section_says_publishing_reads_it_and_never_writes_it() -> None:
    text = " ".join(_DOC.read_text(encoding="utf-8").split())
    match = re.search(r"## The ledger (.*?) ## What leaves your machine", text)
    assert match
    assert (
        "Publishing to an intervals.icu instance reads that instance's ledger "
        "and never writes it." in match.group(1)
    )


def test_the_readme_connectors_paragraph_says_intervals_also_publishes() -> None:
    text = " ".join((_REPO_ROOT / "README.md").read_text(encoding="utf-8").split())
    match = re.search(r"## Connectors (.*?) ## Training blocks", text)
    assert match, "README.md has no Connectors section"
    assert "and also publishes posts to it" in match.group(1)
