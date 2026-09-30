"""Pins for the ``[connectors]`` table reader (design.md "State layer",
``ConnectorsSettings``, Req 3.1-3.8).

Every registered test connector is built by :func:`_make_connector`, a
:class:`types.SimpleNamespace` (mirroring ``tests/connectors/test_registry.py``'s
own helper) so a test can override any number of its members at once --
``parse_settings``, ``credential_fields``, ``auth_style``, and so on --
without inheriting behavior from ``tests/connectors/conftest.py``'s scripted
connectors, whose ``parse_settings`` always returns ``None`` and can neither
raise, echo the table it received, nor record the :class:`~fitdocs.connectors.
protocol.SettingsContext` it was given -- all three needed here.

Per-instance error assertions go through :func:`_assert_prefixed` (the
collision error through :func:`_assert_collision_prefixed`, and the
whole-table shape error through its own ``startswith``), each of which checks
the *entire* documented prefix; :func:`_assert_prefixed` checks
``f"{settings_file}: [connectors.{name}] {key}: "`` with ``str.startswith``
and returns only what follows it. A prefix compared with ``str.startswith``
cannot pass by coincidence the way a bare ``"word" in message`` check could
(for example against a word that happens to appear inside pytest's own
per-test ``tmp_path`` directory name) -- the *whole* file path, instance name,
and key must appear, in that order, with that punctuation.

The registry-isolation fixture in ``conftest.py`` restores
``registry._REGISTRY`` around every test in this module, so a test here may
freely register without affecting any other test.
"""

from __future__ import annotations

import dataclasses
from collections.abc import Mapping
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest

import fitdocs.settings as fitdocs_settings
from fitdocs.connectors.credentials import env_var_name
from fitdocs.connectors.errors import ConnectorSettingsError
from fitdocs.connectors.protocol import (
    AuthStyle,
    Capability,
    Connector,
    CredentialField,
    SettingsContext,
)
from fitdocs.connectors.registry import register
from fitdocs.connectors.settings import (
    DEFAULT_LOOKBACK_DAYS,
    INSTANCE_NAME_PATTERN,
    MAX_LOOKBACK_DAYS,
    ConnectorInstance,
    ConnectorsSettingsError,
    load_connectors_settings,
)

_UNSET = object()


def _make_connector(**overrides: Any) -> Connector:
    """A minimal, always-valid connector; any number of members overridable.

    Defaults: ``auth_style=NONE`` (no credential fields required), one
    non-driven capability (no operation required), and a ``parse_settings``
    that, on every call: appends the table it received (as a plain ``dict``)
    to the returned object's ``.calls``; appends the exact
    :class:`~fitdocs.connectors.protocol.SettingsContext` object it received
    to ``.contexts``; raises ``overrides["_raise"]`` when given; and
    otherwise returns ``overrides["_return"]`` when given (any object,
    including ``None``, via the ``_UNSET`` sentinel so ``None`` is a valid
    override), else a plain ``dict`` copy of the table.
    """
    calls: list[dict[str, object]] = []
    contexts: list[SettingsContext] = []

    def _parse_settings(
        table: Mapping[str, object], context: SettingsContext
    ) -> object:
        calls.append(dict(table))
        contexts.append(context)
        raise_exc = overrides.get("_raise")
        if raise_exc is not None:
            raise raise_exc
        return_value = overrides.get("_return", _UNSET)
        if return_value is not _UNSET:
            return return_value
        return dict(table)

    def _noop_verify(session: object, values: object) -> object:
        raise NotImplementedError

    fields: dict[str, object] = {
        "connector_id": "generic-connector",
        "display_name": "Generic Connector",
        "auth_style": AuthStyle.NONE,
        "capabilities": frozenset({Capability.PULL_THRESHOLDS}),
        "credential_fields": (),
        "parse_settings": _parse_settings,
        "verify": _noop_verify,
        "calls": calls,
        "contexts": contexts,
    }
    fields.update(
        {k: v for k, v in overrides.items() if k not in ("_raise", "_return")}
    )
    return cast(Connector, SimpleNamespace(**fields))


def _context(tmp_path: Path) -> SettingsContext:
    return SettingsContext(data_root=tmp_path, inbox=tmp_path / "inbox")


def _settings_file(tmp_path: Path) -> Path:
    # Deliberately never created: the reader must never touch it.
    return tmp_path / "fitdocs.toml"


def _assert_prefixed(
    exc: BaseException, settings_file: Path, name: str, key: str
) -> str:
    """Assert ``exc``'s message starts with the documented, exact prefix and
    return what follows it.

    The prefix is ``f"{settings_file}: [connectors.{name}] {key}: "`` --
    every one of the file, the instance, and the key, in that order, with
    that punctuation (design.md: "every error is a settings error naming the
    file, the instance and the key"). Comparing the *whole* prefix with
    ``str.startswith`` (rather than checking each component's word appears
    somewhere in the message) cannot be satisfied by an accidental substring
    match against pytest's own per-test ``tmp_path`` directory name.
    """
    message = str(exc)
    prefix = f"{settings_file}: [connectors.{name}] {key}: "
    assert message.startswith(prefix), (message, prefix)
    return message[len(prefix) :]


def _assert_collision_prefixed(exc: BaseException, settings_file: Path) -> str:
    message = str(exc)
    prefix = f"{settings_file}: [connectors] instances "
    assert message.startswith(prefix), (message, prefix)
    return message[len(prefix) :]


# ---------------------------------------------------------------------------
# Design literals (pinned once; every other test that needs a boundary value
# uses the literal directly, never these names, so a change to a constant
# here cannot silently move a boundary pin)
# ---------------------------------------------------------------------------


def test_design_literal_constants() -> None:
    assert DEFAULT_LOOKBACK_DAYS == 30
    assert MAX_LOOKBACK_DAYS == 3650
    assert INSTANCE_NAME_PATTERN == r"^[a-z0-9][a-z0-9-]{0,63}$"


# ---------------------------------------------------------------------------
# Absent configuration (Req 3.7)
# ---------------------------------------------------------------------------


def test_absent_document_yields_no_instances(tmp_path: Path) -> None:
    result = load_connectors_settings(
        {}, settings_file=_settings_file(tmp_path), context=_context(tmp_path)
    )
    assert result == ()


def test_connectors_table_absent_from_nonempty_document_yields_no_instances(
    tmp_path: Path,
) -> None:
    result = load_connectors_settings(
        {"tiles": {"enabled": True}},
        settings_file=_settings_file(tmp_path),
        context=_context(tmp_path),
    )
    assert result == ()


def test_empty_connectors_table_yields_no_instances(tmp_path: Path) -> None:
    result = load_connectors_settings(
        {"connectors": {}},
        settings_file=_settings_file(tmp_path),
        context=_context(tmp_path),
    )
    assert result == ()


def test_connectors_table_not_a_table_is_refused(tmp_path: Path) -> None:
    settings_file = _settings_file(tmp_path)
    with pytest.raises(ConnectorsSettingsError) as excinfo:
        load_connectors_settings(
            {"connectors": "oops"},
            settings_file=settings_file,
            context=_context(tmp_path),
        )
    message = str(excinfo.value)
    assert message.startswith(f"{settings_file}: [connectors] must be a table, ")


# ---------------------------------------------------------------------------
# Reads no file, writes nothing (Req 3.8)
# ---------------------------------------------------------------------------


def test_reader_reads_no_file_and_writes_nothing(tmp_path: Path) -> None:
    register(_make_connector(connector_id="zzz-noio"))
    settings_file = _settings_file(tmp_path)
    before = sorted(p.name for p in tmp_path.iterdir())
    result = load_connectors_settings(
        {"connectors": {"zzz-noio": {}}},
        settings_file=settings_file,
        context=_context(tmp_path),
    )
    after = sorted(p.name for p in tmp_path.iterdir())
    assert before == [] == after
    assert not settings_file.exists()
    assert len(result) == 1


# ---------------------------------------------------------------------------
# Check order (design.md: table shape; name pattern; connector; lookback_days;
# credential key; parse_settings). Each test below has TWO violations that
# would each independently raise, shaped so the surfaced error identifies
# which check ran first.
# ---------------------------------------------------------------------------


def test_shape_check_runs_before_name_check(tmp_path: Path) -> None:
    # "Bad" is both an invalid table (a bare string) AND an invalid name
    # (uppercase). The shape check must win.
    settings_file = _settings_file(tmp_path)
    with pytest.raises(ConnectorsSettingsError) as excinfo:
        load_connectors_settings(
            {"connectors": {"Bad": "oops"}},
            settings_file=settings_file,
            context=_context(tmp_path),
        )
    detail = _assert_prefixed(excinfo.value, settings_file, "Bad", "table")
    assert "must be a table" in detail


def test_connector_check_runs_before_lookback_check(tmp_path: Path) -> None:
    register(_make_connector(connector_id="zzz-order-a"))
    settings_file = _settings_file(tmp_path)
    with pytest.raises(ConnectorsSettingsError) as excinfo:
        load_connectors_settings(
            {"connectors": {"zzz-order-a": {"connector": "", "lookback_days": True}}},
            settings_file=settings_file,
            context=_context(tmp_path),
        )
    detail = _assert_prefixed(excinfo.value, settings_file, "zzz-order-a", "connector")
    assert "non-empty string" in detail


def test_lookback_check_runs_before_credential_key_check(tmp_path: Path) -> None:
    register(
        _make_connector(
            connector_id="zzz-order-b",
            auth_style=AuthStyle.API_KEY,
            credential_fields=(CredentialField("api_key", "API Key", secret=True),),
        )
    )
    settings_file = _settings_file(tmp_path)
    with pytest.raises(ConnectorsSettingsError) as excinfo:
        load_connectors_settings(
            {"connectors": {"zzz-order-b": {"lookback_days": -1, "api_key": "leaked"}}},
            settings_file=settings_file,
            context=_context(tmp_path),
        )
    detail = _assert_prefixed(
        excinfo.value, settings_file, "zzz-order-b", "lookback_days"
    )
    assert "must be between 0 and 3650" in detail


def test_credential_key_check_runs_before_parse_settings(tmp_path: Path) -> None:
    connector = _make_connector(
        connector_id="zzz-order-c",
        auth_style=AuthStyle.API_KEY,
        credential_fields=(CredentialField("api_key", "API Key", secret=True),),
        _raise=RuntimeError("parse_settings must never run"),
    )
    register(connector)
    settings_file = _settings_file(tmp_path)
    with pytest.raises(ConnectorsSettingsError) as excinfo:
        load_connectors_settings(
            {"connectors": {"zzz-order-c": {"api_key": "leaked"}}},
            settings_file=settings_file,
            context=_context(tmp_path),
        )
    _assert_prefixed(excinfo.value, settings_file, "zzz-order-c", "api_key")
    assert connector.calls == []  # type: ignore[attr-defined]


def test_per_instance_error_wins_over_the_collision_check(tmp_path: Path) -> None:
    # Two earlier instances that DO collide, valid on their own; a third,
    # later instance with its own unrelated violation. The per-instance loop
    # must raise the third instance's own error before the collision check
    # (which only runs after every instance has individually validated) ever
    # sees the earlier two.
    register(
        _make_connector(
            connector_id="zzz-order-first",
            auth_style=AuthStyle.API_KEY,
            credential_fields=(CredentialField("c", "C", secret=True),),
        )
    )
    register(
        _make_connector(
            connector_id="zzz-order-second",
            auth_style=AuthStyle.API_KEY,
            credential_fields=(CredentialField("b_c", "B C", secret=True),),
        )
    )
    document = {
        "connectors": {
            "a-b": {"connector": "zzz-order-first"},
            "a": {"connector": "zzz-order-second"},
            "zzz-order-bad": {"connector": ""},
        }
    }
    settings_file = _settings_file(tmp_path)
    with pytest.raises(ConnectorsSettingsError) as excinfo:
        load_connectors_settings(
            document, settings_file=settings_file, context=_context(tmp_path)
        )
    _assert_prefixed(excinfo.value, settings_file, "zzz-order-bad", "connector")


# ---------------------------------------------------------------------------
# Instance name validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("name", "expect_ok"),
    [
        pytest.param("a" * 64, True, id="64-chars-accepted"),
        pytest.param("1" + "a" * 63, True, id="digit-start-accepted"),
        pytest.param("a" * 65, False, id="65-chars-rejected"),
        pytest.param("-abc", False, id="leading-hyphen-rejected"),
        pytest.param("aBc", False, id="uppercase-after-first-rejected"),
        pytest.param("a_bc", False, id="underscore-rejected"),
        # `.match` anchors only the start; `$` matches immediately before a
        # trailing "\n" too, so this must be rejected by `.fullmatch`.
        pytest.param("abc\n", False, id="trailing-newline-rejected"),
    ],
)
def test_instance_name_boundaries(name: str, expect_ok: bool, tmp_path: Path) -> None:
    document: dict[str, object] = {"connectors": {name: {}}}
    settings_file = _settings_file(tmp_path)
    context = _context(tmp_path)
    if expect_ok:
        register(_make_connector(connector_id=name))
        result = load_connectors_settings(
            document, settings_file=settings_file, context=context
        )
        assert result[0].name == name
    else:
        with pytest.raises(ConnectorsSettingsError) as excinfo:
            load_connectors_settings(
                document, settings_file=settings_file, context=context
            )
        detail = _assert_prefixed(excinfo.value, settings_file, name, "name")
        assert "lowercase slug" in detail


def test_instance_sub_table_not_a_table_is_refused(tmp_path: Path) -> None:
    settings_file = _settings_file(tmp_path)
    with pytest.raises(ConnectorsSettingsError) as excinfo:
        load_connectors_settings(
            {"connectors": {"zzz-shape": "oops"}},
            settings_file=settings_file,
            context=_context(tmp_path),
        )
    detail = _assert_prefixed(excinfo.value, settings_file, "zzz-shape", "table")
    assert "must be a table" in detail
    # The doubled "[connectors.<name>]" bug: _fail already prefixes the
    # instance, so the detail itself must not repeat it.
    assert "[connectors." not in detail


# ---------------------------------------------------------------------------
# Connector resolution: default-to-name, explicit key, unknown id (Req 3.2)
# ---------------------------------------------------------------------------


def test_absent_connector_key_defaults_to_the_instance_name(tmp_path: Path) -> None:
    connector = _make_connector(connector_id="zzz-my-instance")
    register(connector)
    result = load_connectors_settings(
        {"connectors": {"zzz-my-instance": {}}},
        settings_file=_settings_file(tmp_path),
        context=_context(tmp_path),
    )
    assert len(result) == 1
    assert result[0].connector is connector


def test_explicit_connector_key_overrides_the_instance_name(tmp_path: Path) -> None:
    default_connector = _make_connector(connector_id="zzz-my-instance2")
    other_connector = _make_connector(connector_id="zzz-other-id")
    register(default_connector)
    register(other_connector)
    result = load_connectors_settings(
        {"connectors": {"zzz-my-instance2": {"connector": "zzz-other-id"}}},
        settings_file=_settings_file(tmp_path),
        context=_context(tmp_path),
    )
    assert len(result) == 1
    assert result[0].connector is other_connector
    assert result[0].connector is not default_connector


def test_empty_string_connector_key_is_refused(tmp_path: Path) -> None:
    register(_make_connector(connector_id="zzz-empty-conn"))
    settings_file = _settings_file(tmp_path)
    with pytest.raises(ConnectorsSettingsError) as excinfo:
        load_connectors_settings(
            {"connectors": {"zzz-empty-conn": {"connector": ""}}},
            settings_file=settings_file,
            context=_context(tmp_path),
        )
    detail = _assert_prefixed(
        excinfo.value, settings_file, "zzz-empty-conn", "connector"
    )
    # An empty string is a str, so it must be rejected by the emptiness
    # check, not merely fall through to registry.get("") -> "unknown
    # connector id ''" (which would also happen to raise, but for the wrong
    # reason).
    assert "non-empty string" in detail


def test_non_string_connector_key_is_refused(tmp_path: Path) -> None:
    register(_make_connector(connector_id="zzz-nonstr-conn"))
    settings_file = _settings_file(tmp_path)
    with pytest.raises(ConnectorsSettingsError) as excinfo:
        load_connectors_settings(
            {"connectors": {"zzz-nonstr-conn": {"connector": 5}}},
            settings_file=settings_file,
            context=_context(tmp_path),
        )
    detail = _assert_prefixed(
        excinfo.value, settings_file, "zzz-nonstr-conn", "connector"
    )
    # A truthy non-string value (5) must be rejected by the type check, not
    # merely fall through to "unknown connector id 5" via registry.get.
    assert "non-empty string" in detail
    assert "int" in detail


def test_unknown_connector_id_names_the_id_and_every_registered_id(
    tmp_path: Path,
) -> None:
    register(_make_connector(connector_id="zzz-known-one"))
    register(_make_connector(connector_id="zzz-known-two"))
    settings_file = _settings_file(tmp_path)
    with pytest.raises(ConnectorsSettingsError) as excinfo:
        load_connectors_settings(
            {"connectors": {"zzz-unknown-inst": {"connector": "zzz-not-registered"}}},
            settings_file=settings_file,
            context=_context(tmp_path),
        )
    detail = _assert_prefixed(
        excinfo.value, settings_file, "zzz-unknown-inst", "connector"
    )
    assert "zzz-not-registered" in detail
    assert "zzz-known-one" in detail
    assert "zzz-known-two" in detail


# ---------------------------------------------------------------------------
# lookback_days (Req 3.3)
# ---------------------------------------------------------------------------


def test_lookback_days_defaults_when_absent(tmp_path: Path) -> None:
    register(_make_connector(connector_id="zzz-lb-default"))
    result = load_connectors_settings(
        {"connectors": {"zzz-lb-default": {}}},
        settings_file=_settings_file(tmp_path),
        context=_context(tmp_path),
    )
    assert result[0].lookback_days == 30


def test_lookback_days_bool_is_refused(tmp_path: Path) -> None:
    register(_make_connector(connector_id="zzz-lb-bool"))
    settings_file = _settings_file(tmp_path)
    with pytest.raises(ConnectorsSettingsError) as excinfo:
        load_connectors_settings(
            {"connectors": {"zzz-lb-bool": {"lookback_days": True}}},
            settings_file=settings_file,
            context=_context(tmp_path),
        )
    detail = _assert_prefixed(
        excinfo.value, settings_file, "zzz-lb-bool", "lookback_days"
    )
    assert "whole number of days" in detail


def test_lookback_days_non_int_is_refused(tmp_path: Path) -> None:
    register(_make_connector(connector_id="zzz-lb-str"))
    settings_file = _settings_file(tmp_path)
    with pytest.raises(ConnectorsSettingsError) as excinfo:
        load_connectors_settings(
            {"connectors": {"zzz-lb-str": {"lookback_days": "30"}}},
            settings_file=settings_file,
            context=_context(tmp_path),
        )
    detail = _assert_prefixed(
        excinfo.value, settings_file, "zzz-lb-str", "lookback_days"
    )
    assert "whole number of days" in detail


@pytest.mark.parametrize(
    ("value", "expect_ok"),
    [
        (-1, False),  # min - 1
        (0, True),  # min
        (3650, True),  # max
        (3651, False),  # max + 1
    ],
)
def test_lookback_days_range_boundaries(
    value: int, expect_ok: bool, tmp_path: Path
) -> None:
    register(_make_connector(connector_id="zzz-lb-range"))
    document = {"connectors": {"zzz-lb-range": {"lookback_days": value}}}
    settings_file = _settings_file(tmp_path)
    context = _context(tmp_path)
    if expect_ok:
        result = load_connectors_settings(
            document, settings_file=settings_file, context=context
        )
        assert result[0].lookback_days == value
    else:
        with pytest.raises(ConnectorsSettingsError) as excinfo:
            load_connectors_settings(
                document, settings_file=settings_file, context=context
            )
        detail = _assert_prefixed(
            excinfo.value, settings_file, "zzz-lb-range", "lookback_days"
        )
        assert "must be between 0 and 3650" in detail


# ---------------------------------------------------------------------------
# Credential-key refusal (Req 3.5)
# ---------------------------------------------------------------------------


def test_credential_named_key_is_refused_with_the_credentials_message(
    tmp_path: Path,
) -> None:
    register(
        _make_connector(
            connector_id="zzz-cred-inst",
            auth_style=AuthStyle.API_KEY,
            credential_fields=(CredentialField("api_key", "API Key", secret=True),),
        )
    )
    settings_file = _settings_file(tmp_path)
    with pytest.raises(ConnectorsSettingsError) as excinfo:
        load_connectors_settings(
            # The credential key sits between two unrelated keys (neither
            # first nor last), so a check of only one end cannot refuse it.
            {
                "connectors": {
                    "zzz-cred-inst": {
                        "unrelated": 1,
                        "api_key": "sk-leaked",
                        "trailing": 2,
                    }
                }
            },
            settings_file=settings_file,
            context=_context(tmp_path),
        )
    message = str(excinfo.value)
    detail = _assert_prefixed(excinfo.value, settings_file, "zzz-cred-inst", "api_key")
    assert "fitdocs connect" in detail
    assert "environment" in detail
    # The value itself is never echoed into the error message.
    assert "sk-leaked" not in message


def test_a_key_matching_no_credential_field_reaches_parse_settings(
    tmp_path: Path,
) -> None:
    connector = _make_connector(
        connector_id="zzz-cred-passthrough",
        auth_style=AuthStyle.API_KEY,
        credential_fields=(CredentialField("api_key", "API Key", secret=True),),
    )
    register(connector)
    result = load_connectors_settings(
        {"connectors": {"zzz-cred-passthrough": {"unrelated_key": "value"}}},
        settings_file=_settings_file(tmp_path),
        context=_context(tmp_path),
    )
    assert result[0].settings == {"unrelated_key": "value"}


# ---------------------------------------------------------------------------
# connector.parse_settings and unknown-key pass-through (Req 3.3, 3.4)
# ---------------------------------------------------------------------------


def test_unknown_keys_are_ignored_by_the_reader_and_handed_to_the_connector(
    tmp_path: Path,
) -> None:
    connector = _make_connector(connector_id="zzz-unknown-keys")
    register(connector)
    result = load_connectors_settings(
        {"connectors": {"zzz-unknown-keys": {"some_option": 42, "another": "x"}}},
        settings_file=_settings_file(tmp_path),
        context=_context(tmp_path),
    )
    assert result[0].settings == {"some_option": 42, "another": "x"}


def test_connector_and_lookback_keys_are_never_handed_to_parse_settings(
    tmp_path: Path,
) -> None:
    other = _make_connector(connector_id="zzz-other-id2")
    register(other)
    mine = _make_connector(connector_id="zzz-mine")
    register(mine)
    result = load_connectors_settings(
        {
            "connectors": {
                "zzz-mine": {"connector": "zzz-other-id2", "lookback_days": 5, "x": 1}
            }
        },
        settings_file=_settings_file(tmp_path),
        context=_context(tmp_path),
    )
    # "connector" and "lookback_days" -- the two reserved keys -- never
    # appear in what parse_settings received; only the unrelated key "x" does.
    assert result[0].settings == {"x": 1}


def test_connector_settings_error_is_wrapped_naming_the_key(tmp_path: Path) -> None:
    connector = _make_connector(
        connector_id="zzz-cse",
        _raise=ConnectorSettingsError("bad_key", "must be a positive integer"),
    )
    register(connector)
    settings_file = _settings_file(tmp_path)
    with pytest.raises(ConnectorsSettingsError) as excinfo:
        load_connectors_settings(
            {"connectors": {"zzz-cse": {"bad_key": -1}}},
            settings_file=settings_file,
            context=_context(tmp_path),
        )
    detail = _assert_prefixed(excinfo.value, settings_file, "zzz-cse", "bad_key")
    assert detail == "must be a positive integer"


@pytest.mark.parametrize("exc_type", [ValueError, RuntimeError, KeyError])
def test_other_exception_from_parse_settings_is_wrapped_naming_the_connector(
    tmp_path: Path, exc_type: type[Exception]
) -> None:
    connector = _make_connector(
        connector_id="zzz-explodes-oddly", _raise=exc_type("boom-detail")
    )
    register(connector)
    settings_file = _settings_file(tmp_path)
    with pytest.raises(ConnectorsSettingsError) as excinfo:
        load_connectors_settings(
            {"connectors": {"zzz-other-exc-inst": {"connector": "zzz-explodes-oddly"}}},
            settings_file=settings_file,
            context=_context(tmp_path),
        )
    detail = _assert_prefixed(
        excinfo.value, settings_file, "zzz-other-exc-inst", "connector"
    )
    assert "zzz-explodes-oddly" in detail
    assert "boom-detail" in detail


def test_parse_settings_receives_the_exact_context_object(tmp_path: Path) -> None:
    # inbox is neither data_root nor a path under it.
    data_root = tmp_path / "root"
    data_root.mkdir()
    inbox = tmp_path / "elsewhere" / "inbox"
    inbox.mkdir(parents=True)
    context = SettingsContext(data_root=data_root, inbox=inbox)
    connector = _make_connector(connector_id="zzz-ctx")
    register(connector)
    load_connectors_settings(
        {"connectors": {"zzz-ctx": {}}},
        settings_file=_settings_file(tmp_path),
        context=context,
    )
    assert connector.contexts == [context]  # type: ignore[attr-defined]
    assert connector.contexts[0] is context  # type: ignore[attr-defined]


def test_parse_settings_return_value_is_passed_through_by_identity(
    tmp_path: Path,
) -> None:
    sentinel = object()
    connector = _make_connector(connector_id="zzz-sentinel", _return=sentinel)
    register(connector)
    result = load_connectors_settings(
        {"connectors": {"zzz-sentinel": {}}},
        settings_file=_settings_file(tmp_path),
        context=_context(tmp_path),
    )
    assert result[0].settings is sentinel


# ---------------------------------------------------------------------------
# Environment-variable collisions across instances (Req 3.6)
# ---------------------------------------------------------------------------


def test_two_instances_sharing_a_credential_variable_are_refused_naming_both(
    tmp_path: Path,
) -> None:
    # instance "a-b" field "c" -> FITDOCS_CONNECTOR_A_B_C
    # instance "a" field "b_c" -> FITDOCS_CONNECTOR_A_B_C  (same string)
    # Each colliding field is its connector's middle field (neither first
    # nor last), so a check of only one end cannot find the collision.
    register(
        _make_connector(
            connector_id="zzz-first-kind",
            auth_style=AuthStyle.API_KEY,
            credential_fields=(
                CredentialField("x", "X", secret=True),
                CredentialField("c", "C", secret=True),
                CredentialField("z", "Z", secret=True),
            ),
        )
    )
    register(
        _make_connector(
            connector_id="zzz-second-kind",
            auth_style=AuthStyle.API_KEY,
            credential_fields=(
                CredentialField("y", "Y", secret=True),
                CredentialField("b_c", "B C", secret=True),
                CredentialField("w", "W", secret=True),
            ),
        )
    )
    document = {
        "connectors": {
            "a-b": {"connector": "zzz-first-kind"},
            "a": {"connector": "zzz-second-kind"},
        }
    }
    assert (
        env_var_name("a-b", "c")
        == env_var_name("a", "b_c")
        == "FITDOCS_CONNECTOR_A_B_C"
    )
    settings_file = _settings_file(tmp_path)
    with pytest.raises(ConnectorsSettingsError) as excinfo:
        load_connectors_settings(
            document, settings_file=settings_file, context=_context(tmp_path)
        )
    detail = _assert_collision_prefixed(excinfo.value, settings_file)
    assert "'a-b'" in detail
    assert "'a'" in detail
    assert "FITDOCS_CONNECTOR_A_B_C" in detail


def test_distinct_credential_variables_across_instances_are_accepted(
    tmp_path: Path,
) -> None:
    register(
        _make_connector(
            connector_id="zzz-third-kind",
            auth_style=AuthStyle.API_KEY,
            credential_fields=(CredentialField("token", "Token", secret=True),),
        )
    )
    register(
        _make_connector(
            connector_id="zzz-fourth-kind",
            auth_style=AuthStyle.API_KEY,
            credential_fields=(CredentialField("token", "Token", secret=True),),
        )
    )
    document = {
        "connectors": {
            "zulu-instance": {"connector": "zzz-third-kind"},
            "alpha-instance": {"connector": "zzz-fourth-kind"},
        }
    }
    result = load_connectors_settings(
        document, settings_file=_settings_file(tmp_path), context=_context(tmp_path)
    )
    assert len(result) == 2


# ---------------------------------------------------------------------------
# Sorted output (Req 3.1)
# ---------------------------------------------------------------------------


def test_instances_are_returned_sorted_by_name_from_unsorted_sub_tables(
    tmp_path: Path,
) -> None:
    # Connector ids are deliberately ordered differently from the instance
    # names they belong to, so sorting by connector_id (instead of by
    # instance name) would produce a different, and therefore
    # distinguishable, order.
    register(_make_connector(connector_id="zzz-conn"))
    register(_make_connector(connector_id="mmm-conn"))
    register(_make_connector(connector_id="aaa-conn"))
    # Also out of alphabetical AND reverse-alphabetical order by instance
    # name, so neither a stable "insertion order" nor a reverse-sort
    # implementation would coincidentally match this expectation.
    document: dict[str, object] = {
        "connectors": {
            "mike": {"connector": "mmm-conn"},
            "zulu": {"connector": "aaa-conn"},
            "alpha": {"connector": "zzz-conn"},
        }
    }
    result = load_connectors_settings(
        document, settings_file=_settings_file(tmp_path), context=_context(tmp_path)
    )
    assert [instance.name for instance in result] == ["alpha", "mike", "zulu"]
    # Sorted by connector_id this would read ["aaa-conn", "mmm-conn",
    # "zzz-conn"] (zulu, mike, alpha) -- a different order, so this also
    # defeats a sort-by-connector_id implementation.
    assert [instance.connector.connector_id for instance in result] == [
        "zzz-conn",
        "mmm-conn",
        "aaa-conn",
    ]


# ---------------------------------------------------------------------------
# ConnectorInstance and ConnectorsSettingsError shape
# ---------------------------------------------------------------------------


def test_connectors_settings_error_subclasses_settings_error() -> None:
    assert issubclass(ConnectorsSettingsError, fitdocs_settings.SettingsError)


def test_connector_instance_field_names_and_order() -> None:
    names = [f.name for f in dataclasses.fields(ConnectorInstance)]
    assert names == ["name", "connector", "lookback_days", "settings"]


def test_connector_instance_is_frozen(tmp_path: Path) -> None:
    register(_make_connector(connector_id="zzz-frozen"))
    result = load_connectors_settings(
        {"connectors": {"zzz-frozen": {}}},
        settings_file=_settings_file(tmp_path),
        context=_context(tmp_path),
    )
    instance = result[0]
    assert isinstance(instance, ConnectorInstance)
    with pytest.raises(AttributeError):
        instance.name = "changed"  # type: ignore[misc]
