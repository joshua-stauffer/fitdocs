"""Reconciled settings attribution and its visible documentation (task 7.1)."""

from __future__ import annotations

import copy
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import cast

import pytest
from markdown_it import MarkdownIt

from fitdocs.connectors import get, intervals
from fitdocs.connectors.credentials import ResolvedCredentials
from fitdocs.connectors.http import CallMode, HttpClient, HttpResponse
from fitdocs.connectors.protocol import (
    AuthStyle,
    ConnectorSession,
    WellnessDay,
    WellnessPackage,
    WellnessPuller,
)
from fitdocs.connectors.secrets import Redactor, Secret
from tests.connectors.conftest import FakeTransport
from tests.fixtures import builder

_CLOCK = datetime(1989, 12, 31, tzinfo=UTC) + timedelta(
    seconds=builder.FIT_TIMESTAMP_BASE
)
_DAY = _CLOCK.date()
_ROOT = Path(__file__).resolve().parents[2]
_SWITCHES = (
    ("garmin", "icu_garmin_download_wellness"),
    ("polar", "polar_download_wellness"),
    ("suunto", "suunto_download_wellness"),
    ("coros", "coros_download_wellness"),
    ("zepp", "zepp_download_wellness"),
    ("huawei", "huawei_download_wellness"),
)
_SWITCH_VALUES = [
    pytest.param(True, True, id="true"),
    pytest.param(False, False, id="false"),
    pytest.param(None, False, id="null"),
    pytest.param(0, False, id="int-zero"),
    pytest.param(1, False, id="int-one"),
    pytest.param(0.0, False, id="float-zero"),
    pytest.param(1.5, False, id="float-positive"),
    pytest.param("", False, id="string-empty"),
    pytest.param("true", False, id="string-true"),
    pytest.param([], False, id="list-empty"),
    pytest.param([True], False, id="list-true"),
    pytest.param({}, False, id="object-empty"),
    pytest.param({"enabled": True}, False, id="object-enabled"),
]


def _package(
    tmp_path: Path,
    athlete: dict[str, object],
    records: list[dict[str, object]] | None = None,
) -> WellnessPackage:
    transport = FakeTransport([HttpResponse(200, {}, json.dumps(athlete).encode())])
    redactor = Redactor()
    key = Secret("ik-synthetic-7Q2x9")
    redactor.add(key)
    session = ConnectorSession(
        instance="intervals",
        settings=intervals.IntervalsSettings(sources=intervals.DEFAULT_SOURCES),
        http=HttpClient(
            transport, mode=CallMode.DATA, redactor=redactor, sleep=lambda _: None
        ),
        credentials=ResolvedCredentials(
            connector_id="intervals",
            auth_style=AuthStyle.API_KEY,
            values={"api_key": key},
            expires_at=None,
            scopes=None,
            store=None,
            instance_name="intervals",
        ),
        data_root=tmp_path,
        now=lambda: _CLOCK,
        sleep=lambda _: None,
        redactor=redactor,
    )
    selected = records if records is not None else [{"id": _DAY.isoformat()}]
    days = tuple(WellnessDay(_DAY, "synthetic-revision", record) for record in selected)
    return cast(WellnessPuller, get("intervals")).package_wellness(session, days)


def _observe(package: WellnessPackage) -> tuple[object, frozenset[str]]:
    return json.loads(package.data).get("origins"), package.origins


@pytest.mark.parametrize("platform,switch", _SWITCHES)
@pytest.mark.parametrize("prefix", ["", "icu_"], ids=["plain", "prefixed"])
@pytest.mark.parametrize("value,admitted", _SWITCH_VALUES)
def test_present_switch_native_json_partition(
    tmp_path: Path,
    platform: str,
    switch: str,
    prefix: str,
    value: object,
    admitted: bool,
) -> None:
    field = f"signal-{platform}"
    athlete = {f"{prefix}{platform}_wellness_keys": [field], switch: value}
    envelope, metadata = _observe(_package(tmp_path, athlete))
    assert envelope == ({field: platform} if admitted else None)
    assert metadata == (frozenset({platform}) if admitted else frozenset())


@pytest.mark.parametrize("platform,switch", _SWITCHES)
@pytest.mark.parametrize("prefix", ["", "icu_"], ids=["plain", "prefixed"])
def test_absent_switch_retains_list_compatibility(
    tmp_path: Path, platform: str, switch: str, prefix: str
) -> None:
    envelope, metadata = _observe(
        _package(
            tmp_path, {f"{prefix}{platform}_wellness_keys": [f"signal-{platform}"]}
        )
    )
    assert envelope == {f"signal-{platform}": platform}
    assert metadata == frozenset({platform})


@pytest.mark.parametrize("enabled,switch", _SWITCHES)
@pytest.mark.parametrize("prefix", ["", "icu_"], ids=["plain", "prefixed"])
def test_each_switch_controls_its_own_platform(
    tmp_path: Path, enabled: str, switch: str, prefix: str
) -> None:
    athlete: dict[str, object] = {key: False for _, key in _SWITCHES}
    athlete.update(
        {
            f"{prefix}{platform}_wellness_keys": [f"signal-{platform}"]
            for platform, _ in _SWITCHES
        }
    )
    athlete[switch] = True
    envelope, metadata = _observe(_package(tmp_path, athlete))
    assert envelope == {f"signal-{enabled}": enabled}
    assert metadata == frozenset({enabled})


@pytest.mark.parametrize("namespace", ["private", "icu", "icu_private", "icu_icu"])
def test_nonplatform_namespace_has_no_origins(tmp_path: Path, namespace: str) -> None:
    envelope, metadata = _observe(
        _package(tmp_path, {f"{namespace}_wellness_keys": ["private-signal"]})
    )
    assert envelope is None
    assert metadata == frozenset()


_IGNORED_LISTS = [
    pytest.param(f"{namespace}_wellness_keys", {}, id=namespace)
    for namespace in ("private", "icu", "icu_private", "icu_icu")
] + [
    pytest.param(
        f"{prefix}{platform}_wellness_keys", {switch: False}, id=f"{prefix}{platform}"
    )
    for platform, switch in _SWITCHES
    for prefix in ("", "icu_")
]


@pytest.mark.parametrize("ignored,settings", _IGNORED_LISTS)
def test_ignored_lists_do_not_make_enabled_platform_ambiguous(
    tmp_path: Path, ignored: str, settings: dict[str, object]
) -> None:
    athlete = {**settings, ignored: ["shared"], "other_wellness_keys": ["shared"]}
    envelope, metadata = _observe(_package(tmp_path, athlete))
    assert envelope == {"shared": "other"}
    assert metadata == frozenset({"other"})


def test_enabled_platform_collision_omits_only_shared_field(tmp_path: Path) -> None:
    envelope, metadata = _observe(
        _package(
            tmp_path,
            {
                "garmin_wellness_keys": ["shared", "garmin-only"],
                "icu_garmin_wellness_keys": ["shared"],
                "polar_wellness_keys": ["shared", "polar-only"],
                "icu_polar_wellness_keys": ["shared"],
                "icu_garmin_download_wellness": True,
                "polar_download_wellness": True,
            },
        )
    )
    assert envelope == {"garmin-only": "garmin", "polar-only": "polar"}
    assert metadata == frozenset({"garmin", "polar"})


@pytest.mark.parametrize("wellness,health", [(True, False), (False, True)])
@pytest.mark.parametrize("prefix", ["", "icu_"], ids=["plain", "prefixed"])
def test_garmin_health_does_not_replace_wellness_switch(
    tmp_path: Path, wellness: bool, health: bool, prefix: str
) -> None:
    envelope, metadata = _observe(
        _package(
            tmp_path,
            {
                f"{prefix}garmin_wellness_keys": ["signal"],
                "icu_garmin_download_wellness": wellness,
                "icu_garmin_health": health,
            },
        )
    )
    assert envelope == ({"signal": "garmin"} if wellness else None)
    assert metadata == (frozenset({"garmin"}) if wellness else frozenset())


@pytest.mark.parametrize(
    "name,platform", [("oura", "oura"), ("google_fit", "google-fit"), ("123", "123")]
)
@pytest.mark.parametrize("prefix", ["", "icu_"], ids=["plain", "prefixed"])
def test_unknown_platform_ignores_invented_switch(
    tmp_path: Path, name: str, platform: str, prefix: str
) -> None:
    envelope, metadata = _observe(
        _package(
            tmp_path,
            {
                f"{prefix}{name}_wellness_keys": ["signal"],
                f"{name}_download_wellness": False,
                f"icu_{name}_download_wellness": False,
            },
        )
    )
    assert envelope == {"signal": platform}
    assert metadata == frozenset({platform})


@pytest.mark.parametrize(
    "values",
    [{}, {"signal": None}, {"signal": 0}, {"signal": "polar"}],
    ids=["missing", "null", "zero", "other-name"],
)
def test_attribution_preserves_opaque_records(
    tmp_path: Path, values: dict[str, object]
) -> None:
    record: dict[str, object] = {
        "id": _DAY.isoformat(),
        **values,
        "nested": [True, 1, "ñ"],
    }
    before = copy.deepcopy(record)
    package = _package(
        tmp_path,
        {"garmin_wellness_keys": ["signal"], "icu_garmin_download_wellness": True},
        [record],
    )
    envelope, metadata = _observe(package)
    assert envelope == {"signal": "garmin"}
    assert metadata == frozenset({"garmin"})
    assert json.loads(package.data)["records"] == [before]
    assert record == before


def test_settings_input_is_preserved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = intervals._wellness_origins
    seen: list[tuple[dict[str, object], dict[str, object]]] = []

    def observe(athlete: dict[str, object]) -> dict[str, str]:
        before = copy.deepcopy(athlete)
        result = original(athlete)
        seen.append((before, athlete))
        return result

    monkeypatch.setattr(intervals, "_wellness_origins", observe)
    _package(
        tmp_path,
        {"garmin_wellness_keys": ["signal"], "icu_garmin_download_wellness": True},
    )
    assert seen == [
        (
            {"garmin_wellness_keys": ["signal"], "icu_garmin_download_wellness": True},
            {"garmin_wellness_keys": ["signal"], "icu_garmin_download_wellness": True},
        )
    ]


_POLICY_CLAUSES = (
    "The private and ICU namespaces do not name source platforms.",
    "A known platform's wellness-download switch must be boolean true when present; "
    "an absent switch keeps list-based compatibility.",
    "The Garmin health switch does not enable wellness imports.",
    "Only enabled platform lists count toward ambiguity; a field claimed by multiple "
    "enabled platforms has no platform attribution.",
)
_DOC_PATHS = (
    ("connectors.md", [(1, "Connectors"), (2, "intervals.icu"), (3, "Wellness")]),
    ("wellness.md", [(1, "Wellness"), (2, "Delivery envelope")]),
)


def _visible_policy(filename: str, expected: list[tuple[int, str]]) -> str:
    tokens = MarkdownIt("commonmark").parse((_ROOT / "docs" / filename).read_text())
    path: list[tuple[int, str]] = []
    paragraphs: list[str] = []
    for index, token in enumerate(tokens):
        if token.type == "heading_open":
            level = int(token.tag[1:])
            while path and path[-1][0] >= level:
                path.pop()
            path.append((level, tokens[index + 1].content))
        elif (
            token.type == "inline"
            and path == expected
            and index
            and tokens[index - 1].type == "paragraph_open"
        ):
            text = "".join(
                child.content if child.type in {"text", "code_inline"} else " "
                for child in token.children or []
                if child.type != "html_inline"
            )
            paragraphs.append(" ".join(text.split()))
    return " ".join(paragraphs)


@pytest.mark.parametrize("filename,path", _DOC_PATHS)
@pytest.mark.parametrize("clause", _POLICY_CLAUSES)
def test_visible_attribution_policy(
    filename: str, path: list[tuple[int, str]], clause: str
) -> None:
    assert clause in _visible_policy(filename, path)
