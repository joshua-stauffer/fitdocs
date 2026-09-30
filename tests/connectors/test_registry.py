"""Pins for the connector registry, the one validation gate every connector
passes (design.md "Registry layer", Req 2.2-2.8).

Every expected rejection reason below is a hardcoded string literal, one per
member design.md's ordered rule list under "Registry layer" names
(`validate_connector` checks ... in order) -- never imported from
``registry.py`` -- so a change to the wording in production code reds the
pin instead of silently tracking it.

The registry-isolation fixture in ``conftest.py`` restores
``registry._REGISTRY`` around every test in this module, so a test here may
freely register, leave registered, or unregister without affecting any
other test.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, cast

import pytest

from fitdocs.connectors.http import CallMode, HttpClient, HttpResponse
from fitdocs.connectors.protocol import (
    AuthStyle,
    Capability,
    ConnectorSession,
    CredentialField,
    Fetched,
    Granted,
    Listing,
    RemoteActivity,
    SettingsContext,
    TokenSet,
)
from fitdocs.connectors.registry import (
    DuplicateConnectorIdError,
    InvalidConnectorError,
    UnknownConnectorError,
    available,
    get,
    register,
    unregister,
    validate_connector,
)
from fitdocs.connectors.secrets import Redactor, Secret
from tests.connectors.conftest import (
    FakeTransport,
    ScriptedLoginConnector,
    ScriptedPersonalKeyConnector,
    ScriptedPuller,
    UnscriptedCall,
)


def _noop_parse_settings(
    table: Mapping[str, object], context: SettingsContext
) -> object:
    return None


def _make_connector(**overrides: Any) -> SimpleNamespace:
    """A minimal, always-valid connector, one field overridable at a time.

    Defaults: ``auth_style=NONE`` (so no credential fields are required),
    one non-driven capability (so no operation is required), and a plain
    ``parse_settings``. A test overrides exactly the field(s) whose
    violation it means to pin.
    """
    fields: dict[str, object] = {
        "connector_id": "generic-connector",
        "display_name": "Generic Connector",
        "auth_style": AuthStyle.NONE,
        "capabilities": frozenset({Capability.PULL_THRESHOLDS}),
        "credential_fields": (),
        "parse_settings": _noop_parse_settings,
    }
    fields.update(overrides)
    return SimpleNamespace(**fields)


# ---------------------------------------------------------------------------
# register / unregister / get / available
# ---------------------------------------------------------------------------


def test_register_then_get_returns_the_same_connector() -> None:
    connector = _make_connector(connector_id="alpha")
    register(connector)
    assert get("alpha") is connector


def test_available_lists_connectors_in_registration_order() -> None:
    first = _make_connector(connector_id="first-in")
    second = _make_connector(connector_id="second-in")
    register(second)
    register(first)
    # Registration order (second, then first) is the opposite of every
    # plausible alphabetical or id-sorted order, so a wrong implementation
    # that sorts ids would read (first-in, second-in) here.
    ids = [c.connector_id for c in available()]
    assert ids == ["second-in", "first-in"]


def test_unregister_removes_the_connector() -> None:
    connector = _make_connector(connector_id="removable")
    register(connector)
    assert "removable" in [c.connector_id for c in available()]

    unregister("removable")

    assert "removable" not in [c.connector_id for c in available()]


def test_unregister_unknown_id_is_a_noop() -> None:
    connector = _make_connector(connector_id="stays")
    register(connector)
    before = available()

    unregister("never-registered")

    assert available() == before


def test_get_unknown_id_raises_naming_the_id_and_every_registered_id() -> None:
    register(_make_connector(connector_id="known-one"))
    register(_make_connector(connector_id="known-two"))

    try:
        get("missing-id")
        raise AssertionError("expected UnknownConnectorError")
    except UnknownConnectorError as exc:
        message = str(exc)
        assert "missing-id" in message
        assert "known-one" in message
        assert "known-two" in message


def test_register_duplicate_id_keeps_the_incumbent_and_names_the_id() -> None:
    incumbent = _make_connector(connector_id="dup", display_name="First")
    challenger = _make_connector(connector_id="dup", display_name="Second")
    register(incumbent)

    try:
        register(challenger)
        raise AssertionError("expected DuplicateConnectorIdError")
    except DuplicateConnectorIdError as exc:
        assert exc.connector_id == "dup"
        assert "dup" in str(exc)

    # Falsity in the starting state is the registration above; now confirm
    # the incumbent, not the challenger, answers a lookup.
    assert get("dup") is incumbent
    assert get("dup").display_name == "First"


def test_register_invalid_connector_raises_and_registers_nothing() -> None:
    connector = _make_connector(connector_id="Not Valid!")
    before = available()

    try:
        register(connector)
        raise AssertionError("expected InvalidConnectorError")
    except InvalidConnectorError:
        pass

    assert available() == before
    try:
        get("Not Valid!")
        raise AssertionError("expected UnknownConnectorError")
    except UnknownConnectorError:
        pass


# ---------------------------------------------------------------------------
# validate_connector: one rejection per violated member, in design order
# ---------------------------------------------------------------------------


def test_rejects_a_connector_id_that_is_not_a_lowercase_slug() -> None:
    connector = _make_connector(connector_id="Not_A-Slug")
    assert (
        validate_connector(connector)
        == "connector_id must match ^[a-z0-9][a-z0-9-]{0,63}$"
    )


def test_rejects_an_empty_display_name() -> None:
    connector = _make_connector(display_name="")
    assert validate_connector(connector) == "display_name must be a non-empty str"


def test_rejects_an_auth_style_outside_the_vocabulary() -> None:
    connector = _make_connector(auth_style="api-key")  # a plain str, not AuthStyle
    assert validate_connector(connector) == "auth_style must be an AuthStyle"


def test_rejects_empty_capabilities() -> None:
    connector = _make_connector(capabilities=frozenset())
    assert (
        validate_connector(connector)
        == "capabilities must be a non-empty frozenset of Capability"
    )


def test_rejects_a_capability_outside_the_vocabulary() -> None:
    connector = _make_connector(capabilities=frozenset({"pull-activities"}))
    assert (
        validate_connector(connector)
        == "capabilities must be a non-empty frozenset of Capability"
    )


def test_rejects_credential_fields_that_are_not_credentialfield_instances() -> None:
    connector = _make_connector(
        auth_style=AuthStyle.API_KEY,
        credential_fields=("api_key",),
    )
    assert (
        validate_connector(connector)
        == "credential_fields must be a tuple of CredentialField"
    )


def test_rejects_a_malformed_credential_field_name() -> None:
    connector = _make_connector(
        auth_style=AuthStyle.API_KEY,
        credential_fields=(CredentialField("API_KEY", "API Key", secret=True),),
    )
    assert validate_connector(connector) == "credential_fields must have valid names"


def test_rejects_a_credential_field_with_an_empty_label() -> None:
    connector = _make_connector(
        auth_style=AuthStyle.API_KEY,
        credential_fields=(CredentialField("api_key", "", secret=True),),
    )
    assert (
        validate_connector(connector) == "credential_fields must have non-empty labels"
    )


def test_rejects_credential_fields_sharing_a_name() -> None:
    connector = _make_connector(
        auth_style=AuthStyle.API_KEY,
        credential_fields=(
            CredentialField("api_key", "API Key", secret=True),
            CredentialField("api_key", "API Key Again", secret=True),
        ),
    )
    assert validate_connector(connector) == "credential_fields must have unique names"


def test_rejects_credential_fields_declared_under_the_none_style() -> None:
    """The "none style declares no fields" rule (named mutation target)."""
    connector = _make_connector(
        auth_style=AuthStyle.NONE,
        credential_fields=(CredentialField("token", "Token", secret=True),),
    )
    assert (
        validate_connector(connector)
        == "credential_fields must be empty when auth_style is NONE"
    )


def test_rejects_no_credential_fields_under_a_non_none_style() -> None:
    connector = _make_connector(auth_style=AuthStyle.API_KEY, credential_fields=())
    assert (
        validate_connector(connector)
        == "credential_fields must be non-empty when auth_style is not NONE"
    )


def test_rejects_a_non_callable_parse_settings() -> None:
    connector = _make_connector(parse_settings="not callable")
    assert validate_connector(connector) == "parse_settings must be callable"


def test_rejects_missing_verify_when_auth_style_is_api_key() -> None:
    connector = _make_connector(
        auth_style=AuthStyle.API_KEY,
        credential_fields=(CredentialField("api_key", "API Key", secret=True),),
    )
    assert (
        validate_connector(connector)
        == "verify must be callable when auth_style is API_KEY"
    )


def test_rejects_missing_login_when_auth_style_is_login() -> None:
    connector = _make_connector(
        auth_style=AuthStyle.LOGIN,
        credential_fields=(CredentialField("username", "Username", secret=False),),
    )
    assert (
        validate_connector(connector)
        == "login must be callable when auth_style is LOGIN"
    )


def test_rejects_missing_refresh_when_auth_style_is_login() -> None:
    connector = _make_connector(
        auth_style=AuthStyle.LOGIN,
        credential_fields=(CredentialField("username", "Username", secret=False),),
        login=lambda session, values: None,
    )
    assert (
        validate_connector(connector)
        == "refresh must be callable when auth_style is LOGIN"
    )


def test_rejects_missing_list_activities_when_pull_activities_is_declared() -> None:
    connector = _make_connector(capabilities=frozenset({Capability.PULL_ACTIVITIES}))
    assert (
        validate_connector(connector)
        == "list_activities must be callable when PULL_ACTIVITIES is declared"
    )


def test_rejects_missing_fetch_activity_when_pull_activities_is_declared() -> None:
    connector = _make_connector(
        capabilities=frozenset({Capability.PULL_ACTIVITIES}),
        list_activities=lambda session, since: None,
    )
    assert (
        validate_connector(connector)
        == "fetch_activity must be callable when PULL_ACTIVITIES is declared"
    )


# ---------------------------------------------------------------------------
# Adjacent-rule pairs: each fixture violates BOTH rules in the pair; the
# earlier rule (design order) must be the one reported. A registry that
# checked these two rules in the other order, or interleaved with the rules
# either side of the pair, would report the later rule's reason here instead
# -- these fixtures pin the *order*, not merely each rule in isolation.
# ---------------------------------------------------------------------------


def test_id_and_display_name_both_violated_reports_id_first() -> None:
    connector = _make_connector(connector_id="Bad_ID!", display_name="")
    assert (
        validate_connector(connector)
        == "connector_id must match ^[a-z0-9][a-z0-9-]{0,63}$"
    )


def test_display_name_and_auth_style_both_violated_reports_display_name_first() -> None:
    connector = _make_connector(display_name="", auth_style="not-a-style")
    assert validate_connector(connector) == "display_name must be a non-empty str"


def test_auth_style_and_capabilities_both_violated_reports_auth_style_first() -> None:
    connector = _make_connector(auth_style="not-a-style", capabilities=frozenset())
    assert validate_connector(connector) == "auth_style must be an AuthStyle"


def test_capabilities_and_fields_violated_reports_capabilities_first() -> None:
    connector = _make_connector(
        capabilities=frozenset(),
        credential_fields=(
            CredentialField("dup", "Label", secret=True),
            CredentialField("dup", "Label Two", secret=True),
        ),
    )
    assert (
        validate_connector(connector)
        == "capabilities must be a non-empty frozenset of Capability"
    )


def test_credential_fields_and_parse_settings_both_violated_reports_fields_first() -> (
    None
):
    connector = _make_connector(
        credential_fields=(
            CredentialField("dup", "Label", secret=True),
            CredentialField("dup", "Label Two", secret=True),
        ),
        parse_settings="not callable",
    )
    assert validate_connector(connector) == "credential_fields must have unique names"


def test_parse_settings_and_verify_violated_reports_parse_settings_first() -> None:
    connector = _make_connector(
        auth_style=AuthStyle.API_KEY,
        credential_fields=(CredentialField("api_key", "API Key", secret=True),),
        parse_settings="not callable",
        # No `verify` attribute at all -- rule 7 is also violated.
    )
    assert validate_connector(connector) == "parse_settings must be callable"


def test_parse_settings_and_login_violated_reports_parse_settings_first() -> None:
    connector = _make_connector(
        auth_style=AuthStyle.LOGIN,
        credential_fields=(CredentialField("username", "Username", secret=False),),
        parse_settings="not callable",
        # No `login`/`refresh` attributes -- rule 8 is also violated.
    )
    assert validate_connector(connector) == "parse_settings must be callable"


def test_login_and_pull_ops_missing_reports_login_first() -> None:
    connector = _make_connector(
        auth_style=AuthStyle.LOGIN,
        credential_fields=(CredentialField("username", "Username", secret=False),),
        capabilities=frozenset({Capability.PULL_ACTIVITIES}),
        # No `login`/`refresh` (rule 8) and no `list_activities`/
        # `fetch_activity` (rule 9) attributes at all.
    )
    assert (
        validate_connector(connector)
        == "login must be callable when auth_style is LOGIN"
    )


def test_verify_and_pull_ops_missing_reports_verify_first() -> None:
    connector = _make_connector(
        auth_style=AuthStyle.API_KEY,
        credential_fields=(CredentialField("api_key", "API Key", secret=True),),
        capabilities=frozenset({Capability.PULL_ACTIVITIES}),
        # No `verify` (rule 7) and no `list_activities`/`fetch_activity`
        # (rule 9) attributes at all.
    )
    assert (
        validate_connector(connector)
        == "verify must be callable when auth_style is API_KEY"
    )


# ---------------------------------------------------------------------------
# Sub-rule boundaries, parametrized over the design-literal patterns.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("connector_id", "expected_valid"),
    [
        pytest.param("a", True, id="single-char-accepted"),
        pytest.param("a" * 64, True, id="64-chars-accepted"),
        pytest.param("a" * 65, False, id="65-chars-rejected"),
        pytest.param("-abc", False, id="leading-hyphen-rejected"),
    ],
)
def test_connector_id_length_and_leading_character_boundaries(
    connector_id: str, expected_valid: bool
) -> None:
    connector = _make_connector(connector_id=connector_id)
    reason = validate_connector(connector)
    if expected_valid:
        assert reason is None
    else:
        assert reason == "connector_id must match ^[a-z0-9][a-z0-9-]{0,63}$"


@pytest.mark.parametrize(
    ("field_name", "expected_valid"),
    [
        pytest.param("1key", False, id="leading-digit-rejected"),
        pytest.param("_key", False, id="leading-underscore-rejected"),
        pytest.param("a" * 64, True, id="64-chars-accepted"),
        pytest.param("a" * 65, False, id="65-chars-rejected"),
    ],
)
def test_credential_field_name_boundaries(
    field_name: str, expected_valid: bool
) -> None:
    connector = _make_connector(
        auth_style=AuthStyle.API_KEY,
        credential_fields=(CredentialField(field_name, "Label", secret=True),),
        verify=lambda session, values: None,
    )
    reason = validate_connector(connector)
    if expected_valid:
        assert reason is None
    else:
        assert reason == "credential_fields must have valid names"


def test_rejects_a_non_str_display_name() -> None:
    connector = _make_connector(display_name=5)
    assert validate_connector(connector) == "display_name must be a non-empty str"


def test_rejects_capabilities_given_as_a_plain_set_not_frozenset() -> None:
    connector = _make_connector(capabilities={Capability.PULL_THRESHOLDS})
    assert (
        validate_connector(connector)
        == "capabilities must be a non-empty frozenset of Capability"
    )


def test_rejects_credential_fields_given_as_a_list_not_tuple() -> None:
    connector = _make_connector(
        auth_style=AuthStyle.API_KEY,
        credential_fields=[CredentialField("api_key", "API Key", secret=True)],
    )
    assert (
        validate_connector(connector)
        == "credential_fields must be a tuple of CredentialField"
    )


def test_rejects_a_non_str_credential_field_label() -> None:
    connector = _make_connector(
        auth_style=AuthStyle.API_KEY,
        credential_fields=(CredentialField("api_key", 5, secret=True),),  # type: ignore[arg-type]
    )
    assert (
        validate_connector(connector) == "credential_fields must have non-empty labels"
    )


# ---------------------------------------------------------------------------
# Validation never calls an operation; reserved members impose none
# ---------------------------------------------------------------------------


def test_validation_never_calls_parse_settings(
    personal_key_connector: ScriptedPersonalKeyConnector,
) -> None:
    assert personal_key_connector.parse_settings_calls == 0

    assert validate_connector(personal_key_connector) is None

    assert personal_key_connector.parse_settings_calls == 0


def test_validation_never_calls_any_operation(
    scripted_puller_connector: ScriptedPuller,
) -> None:
    # Falsity in the starting state: an empty script means calling either
    # operation raises UnscriptedCall (a BaseException, so it would escape
    # validate_connector's own `except Exception` boundary rather than be
    # absorbed into a reason string) -- so a green result here is only
    # possible if validate_connector truly never called one.
    assert scripted_puller_connector.listing_script == []
    assert scripted_puller_connector.fetch_script == []

    assert validate_connector(scripted_puller_connector) is None

    assert scripted_puller_connector.parse_settings_calls == 0
    assert scripted_puller_connector.list_calls == []
    assert scripted_puller_connector.fetch_calls == []


def test_validation_of_login_connector_never_calls_login_or_refresh(
    login_style_connector: ScriptedLoginConnector,
) -> None:
    assert validate_connector(login_style_connector) is None
    assert login_style_connector.login_calls == []
    assert login_style_connector.refresh_calls == 0


def test_a_non_driven_capability_requires_no_operation() -> None:
    connector = _make_connector(capabilities=frozenset({Capability.PUSH_ACTIVITY}))
    # No push-related attribute exists at all on this object.
    assert validate_connector(connector) is None


def test_the_reserved_auth_style_requires_no_operation() -> None:
    connector = _make_connector(
        auth_style=AuthStyle.OAUTH_BROWSER,
        credential_fields=(CredentialField("token", "Token", secret=True),),
    )
    # No login/refresh/verify attribute exists at all on this object.
    assert validate_connector(connector) is None


# ---------------------------------------------------------------------------
# validate_connector never raises for a malformed object
# ---------------------------------------------------------------------------


def test_validate_connector_returns_a_reason_string_for_arbitrary_objects() -> None:
    # None, an int, object(), and an empty SimpleNamespace each lack every
    # member validate_connector reads; getattr's own default (never a raise)
    # covers a missing attribute, so this holds even though every read and
    # check in validate_connector runs inside one broad except-Exception
    # boundary. A candidate that *raised* here would surface as this test
    # erroring, not merely failing.
    for candidate in (object(), None, 42, "a string", SimpleNamespace()):
        reason = validate_connector(candidate)
        assert isinstance(reason, str)
        assert reason != ""


def test_validate_connector_treats_a_raising_property_as_a_reason() -> None:
    class _RaisesOnAccess:
        @property
        def connector_id(self) -> str:
            raise RuntimeError("boom")

    reason = validate_connector(_RaisesOnAccess())
    assert reason == "reading 'connector_id' raised RuntimeError('boom')"


def _noop(*args: object, **kwargs: object) -> None:
    return None


# member -> (auth_style, capabilities) that make it required and reached
_MEMBER_CONTEXT: dict[str, tuple[AuthStyle, frozenset[Capability]]] = {
    "connector_id": (AuthStyle.NONE, frozenset({Capability.PULL_THRESHOLDS})),
    "display_name": (AuthStyle.NONE, frozenset({Capability.PULL_THRESHOLDS})),
    "auth_style": (AuthStyle.NONE, frozenset({Capability.PULL_THRESHOLDS})),
    "capabilities": (AuthStyle.NONE, frozenset({Capability.PULL_THRESHOLDS})),
    "credential_fields": (AuthStyle.NONE, frozenset({Capability.PULL_THRESHOLDS})),
    "parse_settings": (AuthStyle.NONE, frozenset({Capability.PULL_THRESHOLDS})),
    "verify": (AuthStyle.API_KEY, frozenset({Capability.PULL_THRESHOLDS})),
    "login": (AuthStyle.LOGIN, frozenset({Capability.PULL_THRESHOLDS})),
    "refresh": (AuthStyle.LOGIN, frozenset({Capability.PULL_THRESHOLDS})),
    "list_activities": (AuthStyle.NONE, frozenset({Capability.PULL_ACTIVITIES})),
    "fetch_activity": (AuthStyle.NONE, frozenset({Capability.PULL_ACTIVITIES})),
}


def test_a_raising_capabilities_membership_test_is_named_capabilities() -> None:
    class _RaisingContains(frozenset[Capability]):
        def __contains__(self, item: object) -> bool:
            raise RuntimeError("contains boom")

    attrs: dict[str, object] = {
        "connector_id": "generic-connector",
        "display_name": "Generic Connector",
        "auth_style": AuthStyle.NONE,
        "capabilities": _RaisingContains({Capability.PULL_THRESHOLDS}),
        "credential_fields": (),
        "parse_settings": _noop,
    }
    candidate = type("_Candidate", (), attrs)()
    assert validate_connector(candidate) == (
        "reading 'capabilities' raised RuntimeError('contains boom')"
    )


@pytest.mark.parametrize("member", list(_MEMBER_CONTEXT))
def test_every_raising_member_is_named_in_the_reason(member: str) -> None:
    auth_style, capabilities = _MEMBER_CONTEXT[member]
    fields = (
        (CredentialField("api_key", "API key", secret=True),)
        if auth_style is AuthStyle.API_KEY
        else (CredentialField("username", "Username", secret=False),)
        if auth_style is AuthStyle.LOGIN
        else ()
    )
    attrs: dict[str, object] = {
        "connector_id": "generic-connector",
        "display_name": "Generic Connector",
        "auth_style": auth_style,
        "capabilities": capabilities,
        "credential_fields": fields,
        "parse_settings": _noop,
        "verify": _noop,
        "login": _noop,
        "refresh": _noop,
        "list_activities": _noop,
        "fetch_activity": _noop,
    }

    def _boom(self: object) -> object:
        raise RuntimeError("boom")

    attrs[member] = property(_boom)
    candidate = type("_Candidate", (), attrs)()
    assert validate_connector(candidate) == (
        f"reading {member!r} raised RuntimeError('boom')"
    )


def test_a_raising_attributes_reason_names_the_member_being_read() -> None:
    """The reason names *which* member raised, not merely that something
    did -- pinned on a member other than ``connector_id`` so this cannot
    pass merely because ``connector_id`` happens to be the one member the
    registry's own error path always mentions."""

    class _RaisesOnDisplayName:
        connector_id = "generic-connector"

        @property
        def display_name(self) -> str:
            raise RuntimeError("boom")

    reason = validate_connector(_RaisesOnDisplayName())
    assert reason == "reading 'display_name' raised RuntimeError('boom')"


def test_a_malformed_field_name_breaking_regex_match_is_a_str_reason() -> None:
    """A non-string ``CredentialField.name`` (here an ``int``) makes
    ``_FIELD_NAME_PATTERN.match`` raise ``TypeError`` -- a *post-read check*
    raising, not an attribute read. Before the broad ``except Exception``
    boundary was restored, this escaped ``validate_connector`` uncaught."""
    connector = _make_connector(
        auth_style=AuthStyle.API_KEY,
        credential_fields=(CredentialField(5, "Label", secret=True),),  # type: ignore[arg-type]
        verify=lambda session, values: None,
    )
    reason = validate_connector(connector)
    assert isinstance(reason, str)
    assert reason.startswith("reading 'credential_fields' raised TypeError(")


def test_a_raising_iter_capabilities_gives_a_reason_naming_capabilities() -> None:
    """``isinstance(capabilities, frozenset)`` passes for a ``frozenset``
    subclass whose ``__iter__`` itself raises; the raise happens inside the
    ``all(isinstance(c, Capability) for c in capabilities)`` check, while
    ``current`` is still ``"capabilities"``."""

    class _RaisingIterFrozenset(frozenset[Capability]):
        def __iter__(self) -> Iterator[Capability]:
            raise RuntimeError("iter boom")

    connector = _make_connector(
        capabilities=_RaisingIterFrozenset({Capability.PULL_THRESHOLDS})
    )
    reason = validate_connector(connector)
    assert reason == "reading 'capabilities' raised RuntimeError('iter boom')"


def test_a_raising_refresh_property_gives_a_reason_naming_refresh() -> None:
    """Kills the mutation that reverts to per-member guards without
    restoring a check-level boundary for ``login``/``refresh`` (R7): a
    raising *property* here, not a raising read of a plain attribute."""

    class _RaisesOnRefresh:
        connector_id = "generic-connector"
        display_name = "Generic Connector"
        auth_style = AuthStyle.LOGIN
        capabilities = frozenset({Capability.PULL_THRESHOLDS})
        credential_fields = (CredentialField("username", "Username", secret=False),)

        def parse_settings(
            self, table: Mapping[str, object], context: SettingsContext
        ) -> object:
            return None

        def login(
            self, session: ConnectorSession, values: Mapping[str, Secret]
        ) -> None:
            return None

        @property
        def refresh(self) -> object:
            raise RuntimeError("refresh boom")

    reason = validate_connector(_RaisesOnRefresh())
    assert reason == "reading 'refresh' raised RuntimeError('refresh boom')"


def test_a_raising_list_activities_property_gives_a_reason_naming_it() -> None:
    class _RaisesOnListActivities:
        connector_id = "generic-connector"
        display_name = "Generic Connector"
        auth_style = AuthStyle.NONE
        capabilities = frozenset({Capability.PULL_ACTIVITIES})
        credential_fields: tuple[CredentialField, ...] = ()

        def parse_settings(
            self, table: Mapping[str, object], context: SettingsContext
        ) -> object:
            return None

        @property
        def list_activities(self) -> object:
            raise RuntimeError("list_activities boom")

    reason = validate_connector(_RaisesOnListActivities())
    assert reason == (
        "reading 'list_activities' raised RuntimeError('list_activities boom')"
    )


def test_register_with_a_raising_repr_still_raises_invalidconnectorerror() -> None:
    """``register``'s own error message must not call ``repr`` on the
    rejected candidate -- a malformed connector may be malformed in its
    ``__repr__`` too."""

    class _BadRepr:
        connector_id = "not valid!"

        def __repr__(self) -> str:
            raise RuntimeError("repr boom")

    with pytest.raises(InvalidConnectorError) as excinfo:
        register(cast(Any, _BadRepr()))
    assert "_BadRepr" in str(excinfo.value)
    assert "connector_id" in str(excinfo.value)


# ---------------------------------------------------------------------------
# The synthetic connectors themselves validate (sanity: they are the
# fixtures every later task will register)
# ---------------------------------------------------------------------------


def test_personal_key_connector_fixture_validates(
    personal_key_connector: ScriptedPersonalKeyConnector,
) -> None:
    assert validate_connector(personal_key_connector) is None


def test_login_style_connector_fixture_validates(
    login_style_connector: ScriptedLoginConnector,
) -> None:
    assert validate_connector(login_style_connector) is None


def test_scripted_puller_connector_fixture_validates(
    scripted_puller_connector: ScriptedPuller,
) -> None:
    assert validate_connector(scripted_puller_connector) is None


def test_scripted_connectors_answer_when_scripted(
    personal_key_connector: ScriptedPersonalKeyConnector,
    login_style_connector: ScriptedLoginConnector,
    scripted_puller_connector: ScriptedPuller,
) -> None:
    """Sanity for reuse by later tasks: a scripted answer really flows back,
    not merely "does not raise"."""
    session = cast(ConnectorSession, SimpleNamespace())

    personal_key_connector.verify_script.append(Granted(scopes=("read",)))
    granted = personal_key_connector.verify(session, {})
    assert granted.scopes == ("read",)

    login_style_connector.login_script.append(
        TokenSet(values={}, expires_at=None, scopes=None)
    )
    tokens = login_style_connector.login(session, {})
    assert tokens.scopes is None


# ---------------------------------------------------------------------------
# UnscriptedCall, capabilities overrides, and the puller's data-fetching
# request.
# ---------------------------------------------------------------------------


def test_an_unscripted_call_raises_unscripted_call(
    personal_key_connector: ScriptedPersonalKeyConnector,
) -> None:
    # Falsity in the starting state: no answer has been queued.
    assert personal_key_connector.verify_script == []

    session = cast(ConnectorSession, SimpleNamespace())
    with pytest.raises(UnscriptedCall):
        personal_key_connector.verify(session, {})


def test_a_scripted_exception_is_raised_not_returned(
    login_style_connector: ScriptedLoginConnector,
) -> None:
    boom = RuntimeError("scripted refusal")
    login_style_connector.login_script.append(boom)

    session = cast(ConnectorSession, SimpleNamespace())
    with pytest.raises(RuntimeError) as excinfo:
        login_style_connector.login(session, {})
    assert excinfo.value is boom


def test_capabilities_override_takes_effect_on_personal_key_connector() -> None:
    default_connector = ScriptedPersonalKeyConnector()
    overridden = ScriptedPersonalKeyConnector(
        capabilities=frozenset({Capability.PULL_ACTIVITIES})
    )
    # The override must actually differ from the default, or this test would
    # pass even if the constructor argument were silently ignored.
    assert default_connector.capabilities != overridden.capabilities
    assert overridden.capabilities == frozenset({Capability.PULL_ACTIVITIES})


def test_capabilities_override_takes_effect_on_login_connector() -> None:
    default_connector = ScriptedLoginConnector()
    overridden = ScriptedLoginConnector(
        capabilities=frozenset({Capability.PULL_ACTIVITIES})
    )
    assert default_connector.capabilities != overridden.capabilities
    assert overridden.capabilities == frozenset({Capability.PULL_ACTIVITIES})


def test_scripted_puller_with_data_url_issues_a_request_through_session_http() -> None:
    response = HttpResponse(status=200, headers={}, body=b"[]")
    transport = FakeTransport([response])
    http = HttpClient(
        transport, mode=CallMode.DATA, redactor=Redactor(), sleep=lambda seconds: None
    )
    session = cast(ConnectorSession, SimpleNamespace(http=http))
    puller = ScriptedPuller(data_url="https://example.test/activities")
    # A non-trivial, non-default scripted answer: an implementation that
    # ignores the script and returns an empty ``Listing`` (the type's own
    # zero value) would still pass an assertion scripted with that same
    # empty value.
    scripted = Listing(
        activities=(
            RemoteActivity(remote_id="puller-activity-1", original_available=True),
        )
    )
    puller.listing_script.append(scripted)

    # Falsity in the starting state: no request has been sent yet.
    assert transport.requests == []

    result = puller.list_activities(session, None)

    assert result == scripted
    assert len(transport.requests) == 1
    assert transport.requests[0].method == "GET"
    assert transport.requests[0].url == "https://example.test/activities"
    assert puller.http_responses == [response]


def test_scripted_puller_without_data_url_issues_no_request() -> None:
    puller = ScriptedPuller()
    puller.listing_script.append(Listing(activities=()))
    session = cast(ConnectorSession, SimpleNamespace(http=None))

    puller.list_activities(session, None)

    assert puller.http_responses == []


# ---------------------------------------------------------------------------
# fetch_activity: scripted exceptions, unscripted calls, call recording, and
# FIFO ordering (fetch_activity is not routed through _consume_script -- see
# its own docstring -- so these pin the inlined logic independently).
# ---------------------------------------------------------------------------


def test_fetch_activity_raises_a_queued_exception_by_identity(
    scripted_puller_connector: ScriptedPuller,
) -> None:
    boom = RuntimeError("fetch refused")
    scripted_puller_connector.fetch_script.append(boom)
    session = cast(ConnectorSession, SimpleNamespace())
    activity = RemoteActivity(remote_id="a1", original_available=True)

    with pytest.raises(RuntimeError) as excinfo:
        scripted_puller_connector.fetch_activity(session, activity)
    assert excinfo.value is boom


def test_unscripted_fetch_activity_raises_unscripted_call(
    scripted_puller_connector: ScriptedPuller,
) -> None:
    # Falsity in the starting state: no answer has been queued.
    assert scripted_puller_connector.fetch_script == []

    session = cast(ConnectorSession, SimpleNamespace())
    activity = RemoteActivity(remote_id="a1", original_available=True)
    with pytest.raises(UnscriptedCall):
        scripted_puller_connector.fetch_activity(session, activity)


def test_fetch_calls_records_the_passed_activity(
    scripted_puller_connector: ScriptedPuller,
) -> None:
    first = RemoteActivity(remote_id="first-activity", original_available=True)
    second = RemoteActivity(remote_id="second-activity", original_available=False)
    scripted_puller_connector.fetch_script.append(Fetched(data=b"one"))
    scripted_puller_connector.fetch_script.append(Fetched(data=b"two"))
    session = cast(ConnectorSession, SimpleNamespace())

    scripted_puller_connector.fetch_activity(session, first)
    scripted_puller_connector.fetch_activity(session, second)

    assert scripted_puller_connector.fetch_calls == [first, second]


def test_list_calls_records_the_passed_since(
    scripted_puller_connector: ScriptedPuller,
) -> None:
    since = datetime(2026, 1, 1, tzinfo=UTC)
    scripted_puller_connector.listing_script.append(Listing(activities=()))
    scripted_puller_connector.listing_script.append(Listing(activities=()))
    session = cast(ConnectorSession, SimpleNamespace())

    scripted_puller_connector.list_activities(session, since)
    scripted_puller_connector.list_activities(session, None)

    assert scripted_puller_connector.list_calls == [since, None]


def test_an_unscripted_call_escapes_an_except_exception_block(
    scripted_puller_connector: ScriptedPuller,
) -> None:
    """UnscriptedCall subclasses BaseException specifically so it is not
    caught by an ``except Exception:`` -- the shape every per-connector
    isolation boundary (this registry's own included) uses."""
    session = cast(ConnectorSession, SimpleNamespace())
    activity = RemoteActivity(remote_id="a1", original_available=True)

    caught: Exception | None = None
    try:
        try:
            scripted_puller_connector.fetch_activity(session, activity)
        except Exception as exc:  # noqa: BLE001 - exactly what is under test
            caught = exc
    except UnscriptedCall:
        pass
    else:
        raise AssertionError(
            "UnscriptedCall was caught by `except Exception:` or not raised at all"
        )
    assert caught is None


def test_two_queued_listing_answers_come_back_fifo(
    scripted_puller_connector: ScriptedPuller,
) -> None:
    first = Listing(
        activities=(RemoteActivity(remote_id="first", original_available=True),)
    )
    second = Listing(
        activities=(RemoteActivity(remote_id="second", original_available=True),)
    )
    scripted_puller_connector.listing_script.append(first)
    scripted_puller_connector.listing_script.append(second)
    session = cast(ConnectorSession, SimpleNamespace())

    result_one = scripted_puller_connector.list_activities(session, None)
    result_two = scripted_puller_connector.list_activities(session, None)

    assert result_one == first
    assert result_two == second


def test_two_queued_fetch_answers_come_back_fifo(
    scripted_puller_connector: ScriptedPuller,
) -> None:
    first = Fetched(data=b"first")
    second = Fetched(data=b"second")
    scripted_puller_connector.fetch_script.append(first)
    scripted_puller_connector.fetch_script.append(second)
    session = cast(ConnectorSession, SimpleNamespace())
    activity = RemoteActivity(remote_id="a1", original_available=True)

    result_one = scripted_puller_connector.fetch_activity(session, activity)
    result_two = scripted_puller_connector.fetch_activity(session, activity)

    assert result_one == first
    assert result_two == second


def test_data_url_request_is_sent_exactly_once_when_the_script_raises() -> None:
    response = HttpResponse(status=200, headers={}, body=b"[]")
    transport = FakeTransport([response])
    http = HttpClient(
        transport, mode=CallMode.DATA, redactor=Redactor(), sleep=lambda seconds: None
    )
    session = cast(ConnectorSession, SimpleNamespace(http=http))
    puller = ScriptedPuller(data_url="https://example.test/activities")
    boom = RuntimeError("listing refused")
    puller.listing_script.append(boom)

    # Falsity in the starting state: no request has been sent yet.
    assert transport.requests == []

    with pytest.raises(RuntimeError) as excinfo:
        puller.list_activities(session, None)
    assert excinfo.value is boom
    assert len(transport.requests) == 1


# ---------------------------------------------------------------------------
# A personal-key or login connector overridden to declare PULL_ACTIVITIES
# must actually validate and be able to pull -- not merely declare the
# capability: both classes mix in _ScriptedActivityPullerMixin, which
# supplies the list_activities/fetch_activity the capability requires.
# ---------------------------------------------------------------------------


def test_personal_key_connector_with_pull_activities_validates_and_can_pull() -> None:
    connector = ScriptedPersonalKeyConnector(
        capabilities=frozenset({Capability.PULL_ACTIVITIES})
    )

    assert validate_connector(connector) is None

    # A non-trivial, non-default scripted answer: an implementation that
    # ignores the script and returns an empty ``Listing`` (the type's own
    # zero value) would still pass an assertion scripted with the same
    # empty value, so this pins the scripted value flowing through, not
    # merely that *a* ``Listing`` comes back.
    scripted = Listing(
        activities=(RemoteActivity(remote_id="pk-activity-1", original_available=True),)
    )
    connector.listing_script.append(scripted)
    session = cast(ConnectorSession, SimpleNamespace())
    result = connector.list_activities(session, None)
    assert result == scripted


def test_login_connector_with_pull_activities_validates_and_can_pull() -> None:
    connector = ScriptedLoginConnector(
        capabilities=frozenset({Capability.PULL_ACTIVITIES})
    )

    assert validate_connector(connector) is None

    scripted = Listing(
        activities=(
            RemoteActivity(remote_id="login-activity-1", original_available=True),
        )
    )
    connector.listing_script.append(scripted)
    session = cast(ConnectorSession, SimpleNamespace())
    result = connector.list_activities(session, None)
    assert result == scripted

    connector.listing_script.append(Listing(activities=()))
    session = cast(ConnectorSession, SimpleNamespace())
    result = connector.list_activities(session, None)
    assert result == Listing(activities=())
