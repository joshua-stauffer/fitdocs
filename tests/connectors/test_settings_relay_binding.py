"""Pins for the cross-instance relay binding pass (strava-publish Req 1.3).

No Strava connector exists in this module's world: browser-consent instances
here are a stand-in registered per test. The registry-isolation fixture in
``conftest.py`` restores the registry around every test.
"""

from __future__ import annotations

import builtins
import dataclasses
import pathlib
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

from fitdocs.connectors.errors import ConnectorSettingsError
from fitdocs.connectors.protocol import (
    AuthStyle,
    Capability,
    Connector,
    CredentialField,
    RelayBound,
    SettingsContext,
)
from fitdocs.connectors.registry import register
from fitdocs.connectors.relay import RelaySettings
from fitdocs.connectors.settings import (
    ConnectorInstance,
    ConnectorsSettingsError,
    load_connectors_settings,
)

_TOKEN_FIELD = (CredentialField("token", "Token", secret=True),)


@dataclasses.dataclass(frozen=True)
class _BoundSettings:
    relay_instance: str
    relay: object = None

    def bound(self, relay_settings: object) -> _BoundSettings:
        return dataclasses.replace(self, relay=relay_settings)


def _unused(*_args: object, **_kwargs: object) -> object:
    raise NotImplementedError


def _connector(connector_id: str, auth_style: AuthStyle, **extra: Any) -> Connector:
    fields: dict[str, Any] = {
        "connector_id": connector_id,
        "display_name": connector_id,
        "auth_style": auth_style,
        "capabilities": frozenset({Capability.PULL_THRESHOLDS}),
        "credential_fields": _TOKEN_FIELD,
        "verify": _unused,
        "parse_settings": lambda table, context: dict(table),
    }
    if auth_style is AuthStyle.RELAY_TOKEN:
        fields.update(
            check_token=_unused,
            read_capabilities=_unused,
            start_registration=_unused,
            poll_registration=_unused,
            revoke_token=_unused,
        )
    if auth_style is AuthStyle.OAUTH_BROWSER:
        fields.update(
            start_consent=_unused, poll_consent=_unused, withdraw_consent=_unused
        )
    fields.update(extra)
    return cast(Connector, SimpleNamespace(**fields))


def _register_stand_ins(
    *, browser_settings: Callable[[Any, Any], object] | None = None
) -> None:
    register(
        _connector(
            "zz-relay",
            AuthStyle.RELAY_TOKEN,
            parse_settings=lambda table, context: RelaySettings(url=table["url"]),
        )
    )
    register(
        _connector(
            "zz-browser",
            AuthStyle.OAUTH_BROWSER,
            capabilities=frozenset(
                {Capability.PULL_THRESHOLDS, Capability.PULL_WELLNESS}
            ),
            list_wellness=_unused,
            package_wellness=_unused,
            parse_settings=browser_settings
            or (lambda table, context: _BoundSettings(relay_instance=table["relay"])),
        )
    )
    register(_connector("zz-plain", AuthStyle.API_KEY))


def _context(tmp_path: Path) -> SettingsContext:
    return SettingsContext(data_root=tmp_path, inbox=tmp_path / "inbox")


def _load(
    tmp_path: Path, instances: dict[str, dict[str, object]]
) -> tuple[ConnectorInstance, ...]:
    return load_connectors_settings(
        {"connectors": instances},
        settings_file=tmp_path / "fitdocs.toml",
        context=_context(tmp_path),
    )


def _refusal(tmp_path: Path, instances: dict[str, dict[str, object]]) -> str:
    """Load the instances, expecting a ConnectorsSettingsError; return its message."""
    with pytest.raises(ConnectorsSettingsError) as excinfo:
        _load(tmp_path, instances)
    return str(excinfo.value)


def test_a_successful_bind_carries_the_named_relay_instances_url(
    tmp_path: Path,
) -> None:
    _register_stand_ins()
    result = _load(
        tmp_path,
        {
            "s-two": {"connector": "zz-browser", "relay": "r-b"},
            "r-b": {"connector": "zz-relay", "url": "https://b.example"},
            "s-one": {
                "connector": "zz-browser",
                "relay": "r-a",
                "lookback_days": 7,
                "wellness": True,
            },
            "r-a": {"connector": "zz-relay", "url": "https://a.example"},
        },
    )
    by_name = {instance.name: instance for instance in result}
    assert [instance.name for instance in result] == ["r-a", "r-b", "s-one", "s-two"]
    one = cast(_BoundSettings, by_name["s-one"].settings)
    two = cast(_BoundSettings, by_name["s-two"].settings)
    assert one.relay == RelaySettings(url="https://a.example")
    assert two.relay == RelaySettings(url="https://b.example")
    assert one.relay is by_name["r-a"].settings
    assert by_name["r-a"].settings == RelaySettings(url="https://a.example")
    assert one.relay_instance == "r-a"
    assert by_name["s-one"].connector.connector_id == "zz-browser"
    assert by_name["s-one"].lookback_days == 7
    assert by_name["s-one"].wellness is True
    assert by_name["s-two"].lookback_days == 30
    assert by_name["s-two"].wellness is False


@pytest.mark.parametrize(
    "named",
    ["no-such", "plain", "other-browser"],
    ids=["unknown-name", "non-relay-instance", "browser-instance"],
)
def test_an_unknown_or_non_relay_name_is_refused_listing_the_relay_instances(
    named: str, tmp_path: Path
) -> None:
    _register_stand_ins()
    settings_file = tmp_path / "fitdocs.toml"
    message = _refusal(
        tmp_path,
        {
            "strava": {"connector": "zz-browser", "relay": named},
            "relay-b": {"connector": "zz-relay", "url": "https://b.example"},
            "plain": {"connector": "zz-plain"},
            "other-browser": {"connector": "zz-browser", "relay": "relay-b"},
            "relay-a": {"connector": "zz-relay", "url": "https://a.example"},
        },
    )
    assert message == (
        f"{settings_file}: [connectors.strava] relay: must name a configured "
        "relay instance; configured relay instances: relay-a, relay-b"
    )


def test_no_configured_relay_instance_is_listed_as_none(tmp_path: Path) -> None:
    _register_stand_ins()
    message = _refusal(
        tmp_path,
        {
            "strava": {"connector": "zz-browser", "relay": "relay-a"},
            "plain": {"connector": "zz-plain"},
        },
    )
    assert message.endswith(
        "relay: must name a configured relay instance; configured relay instances: none"
    )


def test_a_second_browser_instance_is_checked_too(tmp_path: Path) -> None:
    _register_stand_ins()
    message = _refusal(
        tmp_path,
        {
            "a-ok": {"connector": "zz-browser", "relay": "r"},
            "b-bad": {"connector": "zz-browser", "relay": "missing"},
            "r": {"connector": "zz-relay", "url": "https://r.example"},
        },
    )
    assert "[connectors.b-bad] relay: " in message


def test_instances_that_are_not_browser_consent_take_no_part(tmp_path: Path) -> None:
    _register_stand_ins()
    # A relay-token instance whose settings look bindable, naming nobody.
    register(
        _connector(
            "zz-relay-bindable",
            AuthStyle.RELAY_TOKEN,
            parse_settings=lambda table, context: _BoundSettings(relay_instance="x"),
        )
    )
    result = _load(tmp_path, {"zz-relay-bindable": {}})
    assert result[0].settings == _BoundSettings(relay_instance="x", relay=None)


def test_browser_settings_that_cannot_be_bound_are_a_connector_defect(
    tmp_path: Path,
) -> None:
    _register_stand_ins(browser_settings=lambda table, context: {"relay": "r"})
    settings_file = tmp_path / "fitdocs.toml"
    message = _refusal(
        tmp_path,
        {
            "strava": {"connector": "zz-browser", "relay": "r"},
            "r": {"connector": "zz-relay", "url": "https://r.example"},
        },
    )
    assert message.startswith(f"{settings_file}: [connectors.strava] connector: ")
    assert "zz-browser" in message


def test_any_other_exception_from_bound_names_the_connector(tmp_path: Path) -> None:
    @dataclasses.dataclass(frozen=True)
    class Exploding:
        relay_instance: str

        def bound(self, relay_settings: object) -> object:
            raise ValueError("boom")

    _register_stand_ins(browser_settings=lambda t, c: Exploding(t["relay"]))
    settings_file = tmp_path / "fitdocs.toml"
    message = _refusal(
        tmp_path,
        {
            "strava": {"connector": "zz-browser", "relay": "r"},
            "r": {"connector": "zz-relay", "url": "https://r.example"},
        },
    )
    assert message == (
        f"{settings_file}: [connectors.strava] connector: "
        "zz-browser settings error: boom"
    )


def test_the_stand_in_settings_are_relay_bound() -> None:
    assert isinstance(_BoundSettings(relay_instance="r"), RelayBound)


def test_a_settings_refusal_from_bound_names_its_key(tmp_path: Path) -> None:
    @dataclasses.dataclass(frozen=True)
    class Refusing:
        relay_instance: str

        def bound(self, relay_settings: object) -> object:
            raise ConnectorSettingsError("upload", "not allowed here")

    _register_stand_ins(browser_settings=lambda t, c: Refusing(t["relay"]))
    settings_file = tmp_path / "fitdocs.toml"
    message = _refusal(
        tmp_path,
        {
            "strava": {"connector": "zz-browser", "relay": "r"},
            "r": {"connector": "zz-relay", "url": "https://r.example"},
        },
    )
    assert message == f"{settings_file}: [connectors.strava] upload: not allowed here"


def test_the_credential_collision_is_reported_before_a_binding_fault(
    tmp_path: Path,
) -> None:
    _register_stand_ins()
    # instance "a-b" field "c" and instance "a" field "b_c" share an env var.
    register(
        _connector(
            "zz-collide-one",
            AuthStyle.API_KEY,
            credential_fields=(CredentialField("c", "C", secret=True),),
        )
    )
    register(
        _connector(
            "zz-collide-two",
            AuthStyle.API_KEY,
            credential_fields=(CredentialField("b_c", "B C", secret=True),),
        )
    )
    message = _refusal(
        tmp_path,
        {
            "strava": {"connector": "zz-browser", "relay": "missing"},
            "a-b": {"connector": "zz-collide-one"},
            "a": {"connector": "zz-collide-two"},
        },
    )
    assert "would both read the environment variable" in message


def test_binding_reads_no_file_and_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _register_stand_ins()
    calls: list[object] = []

    def tripwire(*args: object, **kwargs: object) -> object:
        calls.append(args)
        raise AssertionError("a file was opened")

    monkeypatch.setattr(builtins, "open", tripwire)
    monkeypatch.setattr(pathlib.Path, "open", tripwire)
    monkeypatch.setattr(pathlib.Path, "read_text", tripwire)
    monkeypatch.setattr(pathlib.Path, "write_text", tripwire)
    monkeypatch.setattr(pathlib.Path, "read_bytes", tripwire)
    monkeypatch.setattr(pathlib.Path, "write_bytes", tripwire)
    with pytest.raises(AssertionError):
        pathlib.Path("x").read_text()  # the tripwire is live
    assert len(calls) == 1
    before = sorted(tmp_path.iterdir())
    result = _load(
        tmp_path,
        {
            "strava": {"connector": "zz-browser", "relay": "r"},
            "r": {"connector": "zz-relay", "url": "https://r.example"},
        },
    )
    with pytest.raises(ConnectorsSettingsError):
        _load(tmp_path, {"strava": {"connector": "zz-browser", "relay": "nope"}})
    assert len(calls) == 1
    assert sorted(tmp_path.iterdir()) == before == []
    assert cast(_BoundSettings, result[1].settings).relay is not None
