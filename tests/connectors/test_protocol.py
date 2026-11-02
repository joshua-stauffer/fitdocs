"""Pins for the published connector protocol (design.md "Protocol layer",
Req 1.1-1.9).

Flags and vocabularies are asserted as sets collected by iterating
``CAPABILITIES``/``AuthStyle`` themselves, so an addition, removal, or
mislabeling of any single member changes the collected set. Summary text is
not compared against a literal because design.md states only "one line,
user-facing" for the field, not the wording itself -- pinned instead as
single-line, non-empty and pairwise distinct, which a shared, blank, or
multi-line placeholder would fail.

Every value dataclass's field names, order, and which fields carry a
default are pinned against a design-literal tuple built independently of
the module under test (``_fields_and_defaults`` below), and every
``frozen=True`` design states is pinned against
``__dataclass_params__.frozen``. Every protocol member's signature (using
``.fget`` for a property's getter) is pinned against a design-literal
string built from design.md's code block, not against anything imported
from ``protocol.py`` itself.

The stub class near the bottom is assigned to both a ``Connector``- and an
``ActivityPuller``-typed module-level name purely so ``uv run mypy``
structurally checks it against the two protocols; the typed names are not
otherwise imported by anything.
"""

from __future__ import annotations

import ast
import dataclasses
import inspect
import re
from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path

from fitdocs.connectors.http import CallMode, HttpClient
from fitdocs.connectors.protocol import (
    CAPABILITIES,
    DRIVEN_CAPABILITIES,
    SUPPORTED_AUTH_STYLES,
    ActivityPuller,
    AuthStyle,
    BrowserConsentClient,
    Capability,
    CapabilityInfo,
    Connector,
    ConnectorSession,
    ConsentPolled,
    ConsentStarted,
    CredentialAccess,
    CredentialField,
    Declined,
    Deferred,
    Fetched,
    FetchResult,
    Granted,
    KeyVerifier,
    Listing,
    ListingDeferral,
    RegistrationPolled,
    RegistrationStarted,
    RelayBound,
    RelayCapabilities,
    RelayRefused,
    RelayTokenClient,
    RemoteActivity,
    SettingsContext,
    TokenIssuer,
    TokenSet,
)
from fitdocs.connectors.relay_codes import RelayCode
from fitdocs.connectors.secrets import Redactor, Secret
from tests.connectors.conftest import FakeTransport


def _property_getter(cls: type, name: str) -> Callable[..., object]:
    """The getter function backing a ``Protocol``'s ``@property`` member.

    Mypy types ``SomeProtocol.some_property`` as a plain ``Callable`` (a
    property inside a ``Protocol`` body has no ``.fget`` in mypy's static
    view), so the one dynamic ``getattr`` needed to reach the real runtime
    ``property`` object's ``.fget`` lives here, not scattered across every
    call site.
    """
    getter: Callable[..., object] = getattr(cls, name).fget
    return getter


def _fields_and_defaults(
    cls: type,
    expected: tuple[tuple[str, str], ...],
    *,
    frozen: bool,
    defaulted: frozenset[str],
) -> None:
    """Pin one dataclass's field names, order, *types*, frozen-ness, and
    which fields carry a default -- each against a literal given by the
    caller, copied from design.md's code block, never derived from ``cls``
    itself.

    ``expected`` is an ``(name, type_string)`` pair per field, in design
    order. Under ``from __future__ import annotations`` (both here and in
    ``protocol.py``), ``dataclasses.Field.type`` is the annotation's exact
    source text, so the type half of ``expected`` must match that text
    verbatim (e.g. ``"str | None"``, not ``"Optional[str]"``).
    """
    fields = dataclasses.fields(cls)
    assert tuple((f.name, f.type) for f in fields) == expected
    assert cls.__dataclass_params__.frozen is frozen  # type: ignore[attr-defined]
    for f in fields:
        has_default = (
            f.default is not dataclasses.MISSING
            or f.default_factory is not dataclasses.MISSING
        )
        assert has_default == (f.name in defaulted), (
            f"{cls.__name__}.{f.name}: expected default={f.name in defaulted}, "
            f"found default={has_default}"
        )


# ---------------------------------------------------------------------------
# Capabilities
# ---------------------------------------------------------------------------


_DECLARED_ORDER = (
    Capability.PULL_ACTIVITIES,
    Capability.PUSH_ACTIVITY,
    Capability.ANNOTATE_REMOTE_ACTIVITY,
    Capability.RESOLVE_REMOTE_ACTIVITY,
    Capability.PUSH_PLANNED_WORKOUT,
    Capability.PULL_PLANNED_WORKOUTS,
    Capability.PULL_PLANS,
    Capability.PULL_THRESHOLDS,
    Capability.PULL_WELLNESS,
)

_REMOTE_CHANGING = frozenset(
    {
        Capability.PUSH_ACTIVITY,
        Capability.ANNOTATE_REMOTE_ACTIVITY,
        Capability.PUSH_PLANNED_WORKOUT,
    }
)


def test_capability_is_a_str_enum() -> None:
    # A plain ``Enum`` (or a hand-rolled class with matching string values)
    # would pass every value/membership pin above while failing this: only
    # a ``StrEnum`` member *is* its own string, e.g. in an f-string or a
    # TOML/JSON value written without an explicit ``.value``.
    assert issubclass(Capability, StrEnum)
    assert str(Capability.PULL_ACTIVITIES) == "pull-activities"


def test_capability_has_exactly_nine_members_in_declaration_order() -> None:
    assert tuple(Capability) == _DECLARED_ORDER
    assert len(Capability) == 9


def test_capability_string_values_match_design() -> None:
    # Pins the literal wire value of each member, not just its Python
    # identity -- comparing against ``Capability.PUSH_ACTIVITY`` elsewhere
    # would stay green even if that member's own string value changed.
    assert Capability.PULL_ACTIVITIES.value == "pull-activities"
    assert Capability.PUSH_ACTIVITY.value == "push-activity"
    assert Capability.ANNOTATE_REMOTE_ACTIVITY.value == "annotate-remote-activity"
    assert Capability.RESOLVE_REMOTE_ACTIVITY.value == "resolve-remote-activity"
    assert Capability.PUSH_PLANNED_WORKOUT.value == "push-planned-workout"
    assert Capability.PULL_PLANNED_WORKOUTS.value == "pull-planned-workouts"
    assert Capability.PULL_PLANS.value == "pull-plans"
    assert Capability.PULL_THRESHOLDS.value == "pull-thresholds"
    assert Capability.PULL_WELLNESS.value == "pull-wellness"


def test_capabilities_mapping_holds_all_nine_in_declaration_order() -> None:
    assert tuple(CAPABILITIES.keys()) == _DECLARED_ORDER
    assert len(CAPABILITIES) == 9
    for capability, info in CAPABILITIES.items():
        assert isinstance(info, CapabilityInfo)
        assert info.capability is capability


def test_exactly_push_and_annotate_members_are_remote_changing_and_irreversible() -> (
    None
):
    changing = {c for c, info in CAPABILITIES.items() if info.changes_remote}
    irreversible = {c for c, info in CAPABILITIES.items() if info.irreversible}
    assert changing == _REMOTE_CHANGING
    assert irreversible == _REMOTE_CHANGING


def test_every_other_capability_is_not_remote_changing_and_reversible() -> None:
    for capability, info in CAPABILITIES.items():
        if capability in _REMOTE_CHANGING:
            continue
        assert info.changes_remote is False
        assert info.irreversible is False


_DRIVEN_LITERAL = {
    Capability.PULL_ACTIVITIES,
    Capability.PULL_WELLNESS,
    Capability.PUSH_ACTIVITY,
    Capability.ANNOTATE_REMOTE_ACTIVITY,
    Capability.RESOLVE_REMOTE_ACTIVITY,
}


def test_exactly_the_two_pulls_and_the_three_publish_capabilities_are_driven() -> None:
    driven = {c for c, info in CAPABILITIES.items() if info.driven}
    assert driven == _DRIVEN_LITERAL
    assert _DRIVEN_LITERAL == DRIVEN_CAPABILITIES
    assert isinstance(DRIVEN_CAPABILITIES, frozenset)


def test_capability_summaries_are_non_empty_and_pairwise_distinct() -> None:
    summaries = [info.summary for info in CAPABILITIES.values()]
    assert all(isinstance(summary, str) and summary.strip() for summary in summaries)
    assert len(set(summaries)) == len(summaries)


def test_capability_summaries_are_single_line() -> None:
    for capability, info in CAPABILITIES.items():
        assert "\n" not in info.summary, capability
        assert "\r" not in info.summary, capability


# ---------------------------------------------------------------------------
# Authentication styles
# ---------------------------------------------------------------------------


def test_auth_style_is_a_str_enum() -> None:
    assert issubclass(AuthStyle, StrEnum)
    assert str(AuthStyle.API_KEY) == "api-key"


def test_auth_style_has_exactly_five_members_with_the_designed_values() -> None:
    assert {member.value for member in AuthStyle} == {
        "none",
        "api-key",
        "login",
        "oauth-browser",
        "relay-token",
    }
    assert len(AuthStyle) == 5
    assert AuthStyle.RELAY_TOKEN.value == "relay-token"
    # appended: the relay style is the last member, earlier order untouched
    assert list(AuthStyle)[-1] is AuthStyle.RELAY_TOKEN
    assert list(AuthStyle)[:4] == [
        AuthStyle.NONE,
        AuthStyle.API_KEY,
        AuthStyle.LOGIN,
        AuthStyle.OAUTH_BROWSER,
    ]


def test_every_auth_style_is_supported() -> None:
    assert set(AuthStyle) - SUPPORTED_AUTH_STYLES == set()
    assert {
        AuthStyle.NONE,
        AuthStyle.API_KEY,
        AuthStyle.LOGIN,
        AuthStyle.OAUTH_BROWSER,
        AuthStyle.RELAY_TOKEN,
    } == SUPPORTED_AUTH_STYLES


# ---------------------------------------------------------------------------
# Value types
# ---------------------------------------------------------------------------


def test_credential_field_carries_name_label_and_secret_flag() -> None:
    field = CredentialField(name="api_key", label="API key", secret=True)
    assert field.name == "api_key"
    assert field.label == "API key"
    assert field.secret is True


def test_remote_activity_unset_optional_fields_are_none_not_defaults() -> None:
    # A fixture that supplies only the two required fields: any default
    # other than None on an optional field (0.0, "", etc.) would show up
    # here instead of None.
    activity = RemoteActivity(remote_id="abc123", original_available=True)
    assert activity.unavailable_reason is None
    assert activity.start is None
    assert activity.sport is None
    assert activity.duration_s is None
    assert activity.revision is None
    assert activity.suggested_name is None


def test_remote_activity_carries_stated_values_unchanged() -> None:
    start = datetime(2026, 1, 1, tzinfo=UTC)
    activity = RemoteActivity(
        remote_id="abc123",
        original_available=False,
        unavailable_reason="deleted upstream",
        start=start,
        sport="running",
        duration_s=1234.5,
        revision="rev-9",
        suggested_name="abc123.fit",
    )
    assert activity.original_available is False
    assert activity.unavailable_reason == "deleted upstream"
    assert activity.start == start
    assert activity.sport == "running"
    assert activity.duration_s == 1234.5
    assert activity.revision == "rev-9"
    assert activity.suggested_name == "abc123.fit"


def test_listing_defaults_deferred_to_empty_tuple() -> None:
    activity = RemoteActivity(remote_id="a", original_available=True)
    listing = Listing(activities=(activity,))
    assert listing.deferred == ()
    deferral = ListingDeferral(subject="b", reason="not stable yet")
    listing_with_deferral = Listing(activities=(activity,), deferred=(deferral,))
    assert listing_with_deferral.deferred == (deferral,)


def test_fetch_result_is_exactly_one_of_the_three_shapes() -> None:
    fetched: FetchResult = Fetched(data=b"bytes")
    declined: FetchResult = Declined(reason="no original")
    deferred: FetchResult = Deferred(reason="not ready")
    assert isinstance(fetched, Fetched)
    assert not isinstance(fetched, (Declined, Deferred))
    assert isinstance(declined, Declined)
    assert not isinstance(declined, (Fetched, Deferred))
    assert isinstance(deferred, Deferred)
    assert not isinstance(deferred, (Fetched, Declined))
    assert fetched.data == b"bytes"
    assert declined.reason == "no original"
    assert deferred.reason == "not ready"


def test_granted_scopes_none_means_unreported_not_empty() -> None:
    unreported = Granted(scopes=None)
    empty = Granted(scopes=())
    reported = Granted(scopes=("read", "write"))
    assert unreported.scopes is None
    assert empty.scopes == ()
    assert unreported.scopes != empty.scopes
    assert reported.scopes == ("read", "write")


def test_token_set_carries_values_expiry_and_scopes() -> None:
    token = TokenSet(
        values={"access": Secret("tok-value")},
        expires_at=datetime(2026, 1, 1, tzinfo=UTC),
        scopes=("read",),
    )
    assert token.values["access"].reveal() == "tok-value"
    assert token.expires_at == datetime(2026, 1, 1, tzinfo=UTC)
    assert token.scopes == ("read",)


def test_settings_context_carries_data_root_and_inbox() -> None:
    context = SettingsContext(data_root=Path("/data"), inbox=Path("/data/inbox"))
    assert context.data_root == Path("/data")
    assert context.inbox == Path("/data/inbox")


# ---------------------------------------------------------------------------
# Value-type dataclass shapes: field names, order, frozen-ness, defaults.
# Every ``expected_names``/``defaulted`` literal below is copied from
# design.md's code block, independent of ``protocol.py``.
# ---------------------------------------------------------------------------


def test_capability_info_shape() -> None:
    _fields_and_defaults(
        CapabilityInfo,
        (
            ("capability", "Capability"),
            ("summary", "str"),
            ("changes_remote", "bool"),
            ("irreversible", "bool"),
            ("driven", "bool"),
        ),
        frozen=True,
        defaulted=frozenset(),
    )


def test_credential_field_shape() -> None:
    _fields_and_defaults(
        CredentialField,
        (
            ("name", "str"),
            ("label", "str"),
            ("secret", "bool"),
        ),
        frozen=True,
        defaulted=frozenset(),
    )


def test_remote_activity_shape() -> None:
    _fields_and_defaults(
        RemoteActivity,
        (
            ("remote_id", "str"),
            ("original_available", "bool"),
            ("unavailable_reason", "str | None"),
            ("start", "datetime | None"),
            ("sport", "str | None"),
            ("duration_s", "float | None"),
            ("revision", "str | None"),
            ("suggested_name", "str | None"),
        ),
        frozen=True,
        defaulted=frozenset(
            {
                "unavailable_reason",
                "start",
                "sport",
                "duration_s",
                "revision",
                "suggested_name",
            }
        ),
    )


def test_listing_deferral_shape() -> None:
    _fields_and_defaults(
        ListingDeferral,
        (
            ("subject", "str"),
            ("reason", "str"),
        ),
        frozen=True,
        defaulted=frozenset(),
    )


def test_listing_shape() -> None:
    _fields_and_defaults(
        Listing,
        (
            ("activities", "tuple[RemoteActivity, ...]"),
            ("deferred", "tuple[ListingDeferral, ...]"),
        ),
        frozen=True,
        defaulted=frozenset({"deferred"}),
    )


def test_fetched_shape() -> None:
    _fields_and_defaults(
        Fetched, (("data", "bytes"),), frozen=True, defaulted=frozenset()
    )


def test_declined_shape() -> None:
    _fields_and_defaults(
        Declined, (("reason", "str"),), frozen=True, defaulted=frozenset()
    )


def test_deferred_shape() -> None:
    _fields_and_defaults(
        Deferred, (("reason", "str"),), frozen=True, defaulted=frozenset()
    )


def test_granted_shape() -> None:
    _fields_and_defaults(
        Granted,
        (("scopes", "tuple[str, ...] | None"),),
        frozen=True,
        defaulted=frozenset(),
    )


def test_token_set_shape() -> None:
    _fields_and_defaults(
        TokenSet,
        (
            ("values", "Mapping[str, Secret]"),
            ("expires_at", "datetime | None"),
            ("scopes", "tuple[str, ...] | None"),
        ),
        frozen=True,
        defaulted=frozenset(),
    )


def test_settings_context_shape() -> None:
    _fields_and_defaults(
        SettingsContext,
        (
            ("data_root", "Path"),
            ("inbox", "Path"),
        ),
        frozen=True,
        defaulted=frozenset(),
    )


def test_relay_refused_shape() -> None:
    _fields_and_defaults(
        RelayRefused,
        (
            ("code", "RelayCode"),
            ("retry_after_s", "int | None"),
        ),
        frozen=True,
        defaulted=frozenset({"retry_after_s"}),
    )
    assert RelayRefused(RelayCode.RATE_LIMITED).retry_after_s is None


def test_relay_capabilities_shape() -> None:
    _fields_and_defaults(
        RelayCapabilities,
        (
            ("envelopes", "tuple[int, ...]"),
            ("registration", "bool"),
            ("targets", "tuple[str, ...]"),
        ),
        frozen=True,
        defaulted=frozenset(),
    )


def test_registration_started_shape() -> None:
    _fields_and_defaults(
        RegistrationStarted,
        (
            ("user_code", "str"),
            ("poll_secret", "Secret"),
            ("interval_s", "int"),
            ("expires_at", "datetime"),
        ),
        frozen=True,
        defaulted=frozenset(),
    )


def test_registration_polled_shape() -> None:
    _fields_and_defaults(
        RegistrationPolled,
        (
            ("code", "RelayCode"),
            ("token", "Secret | None"),
        ),
        frozen=True,
        defaulted=frozenset(),
    )


def test_connector_session_shape() -> None:
    _fields_and_defaults(
        ConnectorSession,
        (
            ("instance", "str"),
            ("settings", "object"),
            ("http", "HttpClient"),
            ("credentials", "CredentialAccess"),
            ("data_root", "Path"),
            ("now", "Callable[[], datetime]"),
            ("sleep", "Callable[[float], None]"),
            ("redactor", "Redactor"),
        ),
        frozen=True,
        defaulted=frozenset(),
    )


# ---------------------------------------------------------------------------
# Protocol member signatures, pinned against a design-literal string built
# from design.md's code block -- never against anything imported from
# ``protocol.py``. ``.fget`` reaches a property's getter function.
# ---------------------------------------------------------------------------


def test_credential_access_signatures() -> None:
    assert (
        str(inspect.signature(CredentialAccess.value))
        == "(self, field: 'str') -> 'Secret'"
    )
    assert (
        str(inspect.signature(_property_getter(CredentialAccess, "scopes")))
        == "(self) -> 'tuple[str, ...] | None'"
    )
    assert (
        str(inspect.signature(_property_getter(CredentialAccess, "expires_at")))
        == "(self) -> 'datetime | None'"
    )
    assert (
        str(inspect.signature(CredentialAccess.replace))
        == "(self, tokens: 'TokenSet') -> 'None'"
    )


def test_connector_signatures() -> None:
    assert (
        str(inspect.signature(_property_getter(Connector, "connector_id")))
        == "(self) -> 'str'"
    )
    assert (
        str(inspect.signature(_property_getter(Connector, "display_name")))
        == "(self) -> 'str'"
    )
    assert (
        str(inspect.signature(_property_getter(Connector, "auth_style")))
        == "(self) -> 'AuthStyle'"
    )
    assert (
        str(inspect.signature(_property_getter(Connector, "capabilities")))
        == "(self) -> 'frozenset[Capability]'"
    )
    assert (
        str(inspect.signature(_property_getter(Connector, "credential_fields")))
        == "(self) -> 'tuple[CredentialField, ...]'"
    )
    expected_parse_settings = (
        "(self, table: 'Mapping[str, object]', context: 'SettingsContext') -> 'object'"
    )
    assert str(inspect.signature(Connector.parse_settings)) == expected_parse_settings


def test_key_verifier_signature() -> None:
    expected_verify = (
        "(self, session: 'ConnectorSession', values: 'Mapping[str, Secret]')"
        " -> 'Granted'"
    )
    assert str(inspect.signature(KeyVerifier.verify)) == expected_verify


def test_token_issuer_signatures() -> None:
    expected_login = (
        "(self, session: 'ConnectorSession', values: 'Mapping[str, Secret]')"
        " -> 'TokenSet'"
    )
    assert str(inspect.signature(TokenIssuer.login)) == expected_login
    assert (
        str(inspect.signature(TokenIssuer.refresh))
        == "(self, session: 'ConnectorSession') -> 'TokenSet'"
    )


def test_relay_token_client_signatures() -> None:
    expected = {
        "check_token": (
            "(self, session: 'ConnectorSession', token: 'Secret')"
            " -> 'RelayRefused | None'"
        ),
        "read_capabilities": (
            "(self, session: 'ConnectorSession') -> 'RelayCapabilities | RelayRefused'"
        ),
        "start_registration": (
            "(self, session: 'ConnectorSession', email: 'str')"
            " -> 'RegistrationStarted | RelayRefused'"
        ),
        "poll_registration": (
            "(self, session: 'ConnectorSession', started: 'RegistrationStarted')"
            " -> 'RegistrationPolled | RelayRefused'"
        ),
        "revoke_token": (
            "(self, session: 'ConnectorSession', token: 'Secret')"
            " -> 'RelayRefused | None'"
        ),
    }
    for name, signature in expected.items():
        assert str(inspect.signature(getattr(RelayTokenClient, name))) == signature


def test_activity_puller_signatures() -> None:
    assert (
        str(inspect.signature(ActivityPuller.list_activities))
        == "(self, session: 'ConnectorSession', since: 'datetime | None') -> 'Listing'"
    )
    expected_fetch_activity = (
        "(self, session: 'ConnectorSession', activity: 'RemoteActivity')"
        " -> 'FetchResult'"
    )
    assert (
        str(inspect.signature(ActivityPuller.fetch_activity)) == expected_fetch_activity
    )


def test_connector_session_secret_signature() -> None:
    assert (
        str(inspect.signature(ConnectorSession.secret))
        == "(self, value: 'str') -> 'Secret'"
    )


# ---------------------------------------------------------------------------
# Protocol member *sets*: an addition or removal of a member changes the
# public-name set even where every remaining member's own signature pin
# above stays green. Each expected set is a design-literal copied from
# design.md's code block, not derived from the module under test.
# ---------------------------------------------------------------------------


def _public_names(cls: type) -> set[str]:
    return {name for name in vars(cls) if not name.startswith("_")}


def test_key_verifier_member_set() -> None:
    assert _public_names(KeyVerifier) == {"verify"}


def test_token_issuer_member_set() -> None:
    assert _public_names(TokenIssuer) == {"login", "refresh"}


def test_relay_token_client_member_set() -> None:
    assert _public_names(RelayTokenClient) == {
        "check_token",
        "read_capabilities",
        "start_registration",
        "poll_registration",
        "revoke_token",
    }


def test_connector_member_set() -> None:
    assert _public_names(Connector) == {
        "connector_id",
        "display_name",
        "auth_style",
        "capabilities",
        "credential_fields",
        "parse_settings",
    }


def test_credential_access_member_set() -> None:
    assert _public_names(CredentialAccess) == {
        "value",
        "scopes",
        "expires_at",
        "replace",
    }


def test_activity_puller_member_set() -> None:
    assert _public_names(ActivityPuller) == {"list_activities", "fetch_activity"}


# ---------------------------------------------------------------------------
# ConnectorSession.secret
# ---------------------------------------------------------------------------


class _StubCredentialAccess:
    """Structurally satisfies ``CredentialAccess`` for a typed session."""

    def value(self, field: str) -> Secret:
        return Secret("stub-value")

    @property
    def scopes(self) -> tuple[str, ...] | None:
        return None

    @property
    def expires_at(self) -> datetime | None:
        return None

    def replace(self, tokens: TokenSet) -> None:
        return None


def _make_session(redactor: Redactor) -> ConnectorSession:
    from pathlib import Path

    http = HttpClient(
        FakeTransport([]),
        mode=CallMode.DATA,
        redactor=redactor,
        sleep=lambda seconds: None,
    )
    return ConnectorSession(
        instance="example",
        settings=None,
        http=http,
        credentials=_StubCredentialAccess(),
        data_root=Path("/data"),
        now=lambda: datetime(2026, 1, 1, tzinfo=UTC),
        sleep=lambda seconds: None,
        redactor=redactor,
    )


def test_session_secret_wraps_the_value_and_registers_it_with_the_redactor() -> None:
    redactor = Redactor()
    session = _make_session(redactor)
    # Falsity in the starting state: the raw value is not yet redacted before
    # the call -- the plain string below would otherwise pass through
    # ``redact`` unchanged.
    raw = "unique-session-secret-42"
    before = redactor.redact(f"prefix {raw} suffix")
    assert before == f"prefix {raw} suffix"

    wrapped = session.secret(raw)

    assert isinstance(wrapped, Secret)
    assert wrapped.reveal() == raw
    after = redactor.redact(f"prefix {raw} suffix")
    assert after == "prefix <redacted> suffix"


# ---------------------------------------------------------------------------
# Minimal typed stub: mypy structurally checks it against the protocols
# (task requirement -- see the module docstring above).
# ---------------------------------------------------------------------------


class _MinimalStubConnector:
    @property
    def connector_id(self) -> str:
        return "stub"

    @property
    def display_name(self) -> str:
        return "Stub Connector"

    @property
    def auth_style(self) -> AuthStyle:
        return AuthStyle.NONE

    @property
    def capabilities(self) -> frozenset[Capability]:
        return frozenset({Capability.PULL_ACTIVITIES})

    @property
    def credential_fields(self) -> tuple[CredentialField, ...]:
        return ()

    def parse_settings(
        self, table: Mapping[str, object], context: SettingsContext
    ) -> object:
        return None

    def list_activities(
        self, session: ConnectorSession, since: datetime | None
    ) -> Listing:
        return Listing(activities=())

    def fetch_activity(
        self, session: ConnectorSession, activity: RemoteActivity
    ) -> FetchResult:
        return Declined(reason="stub connector declines everything")


_typed_as_connector: Connector = _MinimalStubConnector()
_typed_as_activity_puller: ActivityPuller = _MinimalStubConnector()


def test_minimal_stub_satisfies_connector_and_activitypuller_at_runtime() -> None:
    assert _typed_as_connector.connector_id == "stub"
    assert _typed_as_connector.auth_style is AuthStyle.NONE
    assert _typed_as_connector.capabilities == frozenset({Capability.PULL_ACTIVITIES})
    result = _typed_as_activity_puller.fetch_activity(
        _make_session(Redactor()),
        RemoteActivity(remote_id="x", original_available=False),
    )
    assert isinstance(result, Declined)


# ---------------------------------------------------------------------------
# The relay types' design block, pinned whole. Each literal is the AST
# rendering (docstrings stripped) of the class as design.md's
# "ProtocolAmendment, RegistryAmendment, CredentialsAmendment" code block
# gives it, so a decorator, base class, field or signature added or dropped
# anywhere in the class changes the rendering.
# ---------------------------------------------------------------------------

_RELAY_DESIGN_RENDERINGS = {
    "RelayRefused": (
        "@dataclass(frozen=True)\n"
        "class RelayRefused:\n"
        "    code: RelayCode\n"
        "    retry_after_s: int | None = None"
    ),
    "RelayCapabilities": (
        "@dataclass(frozen=True)\n"
        "class RelayCapabilities:\n"
        "    envelopes: tuple[int, ...]\n"
        "    registration: bool\n"
        "    targets: tuple[str, ...]"
    ),
    "RegistrationStarted": (
        "@dataclass(frozen=True)\n"
        "class RegistrationStarted:\n"
        "    user_code: str\n"
        "    poll_secret: Secret\n"
        "    interval_s: int\n"
        "    expires_at: datetime"
    ),
    "RegistrationPolled": (
        "@dataclass(frozen=True)\n"
        "class RegistrationPolled:\n"
        "    code: RelayCode\n"
        "    token: Secret | None"
    ),
    "RelayTokenClient": (
        "class RelayTokenClient(Protocol):\n"
        "\n"
        "    def check_token(self, session: ConnectorSession, token: Secret)"
        " -> RelayRefused | None:\n"
        "        ...\n"
        "\n"
        "    def read_capabilities(self, session: ConnectorSession)"
        " -> RelayCapabilities | RelayRefused:\n"
        "        ...\n"
        "\n"
        "    def start_registration(self, session: ConnectorSession, email: str)"
        " -> RegistrationStarted | RelayRefused:\n"
        "        ...\n"
        "\n"
        "    def poll_registration(self, session: ConnectorSession,"
        " started: RegistrationStarted) -> RegistrationPolled | RelayRefused:\n"
        "        ...\n"
        "\n"
        "    def revoke_token(self, session: ConnectorSession, token: Secret)"
        " -> RelayRefused | None:\n"
        "        ..."
    ),
}


def _render_class_without_docstrings(name: str) -> str:
    import fitdocs.connectors.protocol as protocol_module

    tree = ast.parse(inspect.getsource(protocol_module))
    matches = [
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef) and node.name == name
    ]
    assert len(matches) == 1, f"{name} must be defined exactly once"
    for node in ast.walk(matches[0]):
        if isinstance(node, ast.ClassDef | ast.FunctionDef):
            first = node.body[0]
            if (
                isinstance(first, ast.Expr)
                and isinstance(first.value, ast.Constant)
                and isinstance(first.value.value, str)
            ):
                node.body = node.body[1:] or [ast.Expr(ast.Constant(...))]
    return ast.unparse(matches[0])


def test_the_five_relay_types_match_the_design_block_whole() -> None:
    assert set(_RELAY_DESIGN_RENDERINGS) == {
        "RelayRefused",
        "RelayCapabilities",
        "RegistrationStarted",
        "RegistrationPolled",
        "RelayTokenClient",
    }
    for name, expected in _RELAY_DESIGN_RENDERINGS.items():
        assert _render_class_without_docstrings(name) == expected, name


# ---------------------------------------------------------------------------
# The publish capabilities and the publish operation protocol (publish-core
# 3.2, Req 9.1, 9.5, 9.6, 9.8, 9.9)
# ---------------------------------------------------------------------------


def test_publish_capabilities_are_exactly_push_annotate_and_resolve() -> None:
    from fitdocs.connectors.protocol import PUBLISH_CAPABILITIES

    assert isinstance(PUBLISH_CAPABILITIES, frozenset)
    assert (
        frozenset(
            {
                Capability.PUSH_ACTIVITY,
                Capability.ANNOTATE_REMOTE_ACTIVITY,
                Capability.RESOLVE_REMOTE_ACTIVITY,
            }
        )
        == PUBLISH_CAPABILITIES
    )


def test_the_four_other_reserved_capabilities_stay_undriven() -> None:
    reserved = {c for c, info in CAPABILITIES.items() if not info.driven}
    assert reserved == {
        Capability.PUSH_PLANNED_WORKOUT,
        Capability.PULL_PLANNED_WORKOUTS,
        Capability.PULL_PLANS,
        Capability.PULL_THRESHOLDS,
    }


def test_publish_capability_flags_are_unchanged() -> None:
    flags = {
        c: (CAPABILITIES[c].changes_remote, CAPABILITIES[c].irreversible)
        for c in (
            Capability.PUSH_ACTIVITY,
            Capability.ANNOTATE_REMOTE_ACTIVITY,
            Capability.RESOLVE_REMOTE_ACTIVITY,
        )
    }
    assert flags == {
        Capability.PUSH_ACTIVITY: (True, True),
        Capability.ANNOTATE_REMOTE_ACTIVITY: (True, True),
        Capability.RESOLVE_REMOTE_ACTIVITY: (False, False),
    }


def test_post_publisher_shape_and_target_obligations() -> None:
    from fitdocs.connectors.protocol import PostPublisher

    assert str(inspect.signature(PostPublisher.publish)) == (
        "(self, session: 'ConnectorSession', request: 'PublishRequest')"
        " -> 'PublishResult'"
    )
    assert isinstance(PostPublisher.__dict__["link_label"], property)
    assert str(inspect.signature(PostPublisher.link_label.fget)) == (  # type: ignore[attr-defined]
        "(self) -> 'str'"
    )
    doc = PostPublisher.__doc__ or ""
    # The framing is pinned too: nothing may sit between the header and the
    # first bullet, and the header itself is the exact phrase.
    head, _, rest = doc.partition("obligations:")
    assert " ".join(head.split()).endswith(". A target's")
    assert re.match(r"\s*\n\s*- ", rest)
    bullets = tuple(
        " ".join(chunk.split())
        for chunk in re.split(r"\n\s*- ", doc.split("obligations:", 1)[1])[1:]
    )
    assert bullets == (
        "It returns one code from ``TARGET_CODES`` per request.",
        "It returns a link only with a landed code.",
        "It never prints, logs or returns service text (text a service sent).",
        "It resolves the remote activity before creating anything, with the "
        "publication id as the idempotency key.",
        "It returns ``AMBIGUOUS`` when several remote activities match, and "
        "``ACTIVITY_FACTS_MISSING`` when the activity facts given cannot "
        "identify the activity -- never a pick, and never an upload.",
        "It returns ``LOCAL_RECORD_UNREADABLE``, never an upload, when its own "
        "local record of the connection's activities cannot be read and "
        "resolution fails.",
        "It marks a request that is not idempotent ``single_attempt``.",
    )


def test_published_publish_names_are_the_leaf_objects() -> None:
    from fitdocs.connectors import protocol
    from fitdocs.publish import outcomes, request

    assert protocol.PublishCode is outcomes.PublishCode
    assert protocol.TARGET_CODES is outcomes.TARGET_CODES
    assert protocol.Post is request.Post
    assert protocol.CompletedActivity is request.CompletedActivity
    assert protocol.PublishRequest is request.PublishRequest
    assert protocol.PublishResult is request.PublishResult


# ---------------------------------------------------------------------------
# The browser-consent types (strava-publish Req 2.6; design.md
# "ProtocolAmendment ..."), pinned whole like the relay types above.
# ---------------------------------------------------------------------------

_CONSENT_DESIGN_RENDERINGS = {
    "ConsentStarted": (
        "@dataclass(frozen=True)\n"
        "class ConsentStarted:\n"
        "    user_code: str\n"
        "    page_url: str\n"
        "    poll_secret: Secret\n"
        "    interval_s: int\n"
        "    expires_at: datetime"
    ),
    "ConsentPolled": (
        "@dataclass(frozen=True)\n"
        "class ConsentPolled:\n"
        "    code: RelayCode\n"
        "    token: Secret | None"
    ),
    "RelayBound": (
        "@runtime_checkable\n"
        "class RelayBound(Protocol):\n"
        "\n"
        "    @property\n"
        "    def relay_instance(self) -> str:\n"
        "        ...\n"
        "\n"
        "    def bound(self, relay_settings: object) -> object:\n"
        "        ..."
    ),
    "BrowserConsentClient": (
        "class BrowserConsentClient(Protocol):\n"
        "\n"
        "    def start_consent(self, session: ConnectorSession,"
        " relay_token: Secret) -> ConsentStarted | RelayRefused:\n"
        "        ...\n"
        "\n"
        "    def poll_consent(self, session: ConnectorSession,"
        " started: ConsentStarted, relay_token: Secret)"
        " -> ConsentPolled | RelayRefused:\n"
        "        ...\n"
        "\n"
        "    def withdraw_consent(self, session: ConnectorSession, token: Secret)"
        " -> RelayRefused | None:\n"
        "        ..."
    ),
}


def test_the_four_consent_types_match_the_design_block_whole() -> None:
    assert set(_CONSENT_DESIGN_RENDERINGS) == {
        "ConsentStarted",
        "ConsentPolled",
        "RelayBound",
        "BrowserConsentClient",
    }
    for name, expected in _CONSENT_DESIGN_RENDERINGS.items():
        assert _render_class_without_docstrings(name) == expected, name


def test_consent_value_types_are_frozen_with_no_defaults() -> None:
    _fields_and_defaults(
        ConsentStarted,
        (
            ("user_code", "str"),
            ("page_url", "str"),
            ("poll_secret", "Secret"),
            ("interval_s", "int"),
            ("expires_at", "datetime"),
        ),
        frozen=True,
        defaulted=frozenset(),
    )
    _fields_and_defaults(
        ConsentPolled,
        (("code", "RelayCode"), ("token", "Secret | None")),
        frozen=True,
        defaulted=frozenset(),
    )


def test_browser_consent_client_member_set() -> None:
    assert _public_names(BrowserConsentClient) == {
        "start_consent",
        "poll_consent",
        "withdraw_consent",
    }


class _BoundSettings:
    relay_instance = "home-relay"

    def bound(self, relay_settings: object) -> object:
        return self


class _SettingsWithoutBound:
    relay_instance = "home-relay"


class _SettingsWithoutRelayInstance:
    def bound(self, relay_settings: object) -> object:
        return self


def test_relay_bound_is_checkable_at_run_time_and_needs_both_members() -> None:
    assert isinstance(_BoundSettings(), RelayBound)
    assert not isinstance(_SettingsWithoutBound(), RelayBound)
    assert not isinstance(_SettingsWithoutRelayInstance(), RelayBound)
    assert not isinstance(object(), RelayBound)
