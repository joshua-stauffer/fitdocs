"""The published connector protocol (design.md "Protocol layer", Req 1.1-1.9).

This module is pure declaration: value types, enums, and
:class:`typing.Protocol` shapes. Nothing here performs I/O, reads the clock,
or mutates the registry (``connectors/registry.py``, a later task, is the
only place a connector is registered).

:data:`CAPABILITIES` is the fixed vocabulary of nine things a connector may
offer, each carrying a user-facing summary and three flags: whether it
changes state at the remote service, whether that change is irreversible,
and whether this version of fitdocs actually drives it (only
``PULL_ACTIVITIES`` is driven in this version -- a connector may declare any
other capability, and the framework accepts the declaration without
requiring an operation for it or ever invoking it, Req 1.4).

:class:`AuthStyle` is the fixed vocabulary of four ways a connector
authenticates; ``OAUTH_BROWSER`` is reserved -- a connector may declare it,
but ``fitdocs connect`` (a later task) refuses it as unsupported by this
version (Req 1.7).

:class:`Connector` is the shape every connector implements: an id, a display
name, one auth style, its capabilities, and its credential fields, plus
``parse_settings`` for its own settings keys. :class:`KeyVerifier`,
:class:`TokenIssuer`, and :class:`ActivityPuller` are the optional-operation
protocols a connector implements when its auth style or a driven capability
requires them (Req 1.1, 1.5, 1.6, 1.9).
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Final, Protocol

from fitdocs.connectors.http import HttpClient
from fitdocs.connectors.secrets import Redactor, Secret


class Capability(StrEnum):
    """The nine things a connector may offer (Req 1.2). Declaration order
    here is the order :data:`CAPABILITIES` iterates in."""

    PULL_ACTIVITIES = "pull-activities"
    PUSH_ACTIVITY = "push-activity"
    ANNOTATE_REMOTE_ACTIVITY = "annotate-remote-activity"
    RESOLVE_REMOTE_ACTIVITY = "resolve-remote-activity"
    PUSH_PLANNED_WORKOUT = "push-planned-workout"
    PULL_PLANNED_WORKOUTS = "pull-planned-workouts"
    PULL_PLANS = "pull-plans"
    PULL_THRESHOLDS = "pull-thresholds"
    PULL_WELLNESS = "pull-wellness"


@dataclass(frozen=True)
class CapabilityInfo:
    """One capability's user-facing summary and flags (Req 1.3, 1.4).

    ``irreversible`` equals ``changes_remote`` in this version -- kept as a
    separate field so a later capability with an undo path can be a
    reversible remote change without a shape change here. ``driven`` is
    ``True`` only for :attr:`Capability.PULL_ACTIVITIES`: the only
    capability this version of fitdocs actually invokes.
    """

    capability: Capability
    summary: str
    changes_remote: bool
    irreversible: bool
    driven: bool


CAPABILITIES: Final[Mapping[Capability, CapabilityInfo]] = {
    Capability.PULL_ACTIVITIES: CapabilityInfo(
        capability=Capability.PULL_ACTIVITIES,
        summary="Pull activity files from the service.",
        changes_remote=False,
        irreversible=False,
        driven=True,
    ),
    Capability.PUSH_ACTIVITY: CapabilityInfo(
        capability=Capability.PUSH_ACTIVITY,
        summary="Upload an activity file to the service.",
        changes_remote=True,
        irreversible=True,
        driven=False,
    ),
    Capability.ANNOTATE_REMOTE_ACTIVITY: CapabilityInfo(
        capability=Capability.ANNOTATE_REMOTE_ACTIVITY,
        summary="Write a note or field onto a remote activity.",
        changes_remote=True,
        irreversible=True,
        driven=False,
    ),
    Capability.RESOLVE_REMOTE_ACTIVITY: CapabilityInfo(
        capability=Capability.RESOLVE_REMOTE_ACTIVITY,
        summary="Match a local workout to its remote counterpart.",
        changes_remote=False,
        irreversible=False,
        driven=False,
    ),
    Capability.PUSH_PLANNED_WORKOUT: CapabilityInfo(
        capability=Capability.PUSH_PLANNED_WORKOUT,
        summary="Send a planned workout to the service.",
        changes_remote=True,
        irreversible=True,
        driven=False,
    ),
    Capability.PULL_PLANNED_WORKOUTS: CapabilityInfo(
        capability=Capability.PULL_PLANNED_WORKOUTS,
        summary="Read planned workouts from the service.",
        changes_remote=False,
        irreversible=False,
        driven=False,
    ),
    Capability.PULL_PLANS: CapabilityInfo(
        capability=Capability.PULL_PLANS,
        summary="Read a whole training plan from the service.",
        changes_remote=False,
        irreversible=False,
        driven=False,
    ),
    Capability.PULL_THRESHOLDS: CapabilityInfo(
        capability=Capability.PULL_THRESHOLDS,
        summary="Read threshold values (e.g. FTP, paces) from the service.",
        changes_remote=False,
        irreversible=False,
        driven=False,
    ),
    Capability.PULL_WELLNESS: CapabilityInfo(
        capability=Capability.PULL_WELLNESS,
        summary="Read wellness data (e.g. sleep, HRV) from the service.",
        changes_remote=False,
        irreversible=False,
        driven=False,
    ),
}

DRIVEN_CAPABILITIES: Final[frozenset[Capability]] = frozenset(
    {Capability.PULL_ACTIVITIES}
)


class AuthStyle(StrEnum):
    """The four ways a connector authenticates (Req 1.7). ``OAUTH_BROWSER``
    is reserved: a connector may declare it, but ``fitdocs connect`` refuses
    it as unsupported by this version."""

    NONE = "none"
    API_KEY = "api-key"
    LOGIN = "login"
    OAUTH_BROWSER = "oauth-browser"  # reserved


SUPPORTED_AUTH_STYLES: Final[frozenset[AuthStyle]] = frozenset(
    {AuthStyle.NONE, AuthStyle.API_KEY, AuthStyle.LOGIN}
)


@dataclass(frozen=True)
class CredentialField:
    """One credential value a connector asks the user to supply (Req 1.1).

    ``name`` doubles as the environment-variable suffix a later task builds
    from it; ``secret`` marks a field prompted without echo and redacted
    everywhere it might be reported.
    """

    name: str
    label: str
    secret: bool


@dataclass(frozen=True)
class RemoteActivity:
    """One activity a connector's listing reports (Req 1.5, 1.8). A value
    the service does not state is ``None`` -- never zero, an empty string,
    or another default (Req 1.8)."""

    remote_id: str
    original_available: bool
    unavailable_reason: str | None = None
    start: datetime | None = None
    sport: str | None = None
    duration_s: float | None = None
    revision: str | None = None
    suggested_name: str | None = None


@dataclass(frozen=True)
class ListingDeferral:
    """One entry a listing could not resolve yet."""

    subject: str
    reason: str


@dataclass(frozen=True)
class Listing:
    """The answer to :meth:`ActivityPuller.list_activities` (Req 1.5)."""

    activities: tuple[RemoteActivity, ...]
    deferred: tuple[ListingDeferral, ...] = ()


@dataclass(frozen=True)
class Fetched:
    """A fetch answered with the activity's original bytes (Req 1.6)."""

    data: bytes


@dataclass(frozen=True)
class Declined:
    """A fetch answered that the activity has no usable original (Req 1.6)."""

    reason: str


@dataclass(frozen=True)
class Deferred:
    """A fetch answered that the original cannot be fetched yet (Req 1.6)."""

    reason: str


FetchResult = Fetched | Declined | Deferred


@dataclass(frozen=True)
class Granted:
    """The scopes a service reported after a personal-key verification.
    ``scopes=None`` means the service did not report scopes at all (Req 4.8)
    -- distinct from an empty grant."""

    scopes: tuple[str, ...] | None


@dataclass(frozen=True)
class TokenSet:
    """What a login-style connector's service issues, and all that a
    login-style connector persists (Req 4.6)."""

    values: Mapping[str, Secret]
    expires_at: datetime | None
    scopes: tuple[str, ...] | None


@dataclass(frozen=True)
class SettingsContext:
    """What ``parse_settings`` needs beyond its own table (Req 1.1).

    ``inbox`` exists so a connector can refuse a configuration that would
    loop into the inbox (the folder connector, a later task, does).
    """

    data_root: Path
    inbox: Path


class CredentialAccess(Protocol):
    """What a connector session uses to read and rotate its credentials."""

    def value(self, field: str) -> Secret: ...

    @property
    def scopes(self) -> tuple[str, ...] | None: ...

    @property
    def expires_at(self) -> datetime | None: ...

    def replace(self, tokens: TokenSet) -> None: ...


@dataclass(frozen=True)
class ConnectorSession:
    """Everything a connector operation receives (Req 1.9): the instance
    name, its own configuration, the transport, its credentials, the data
    root, the clock (``now``/``sleep``), and the redactor. A connector keeps
    no state between sessions.
    """

    instance: str
    settings: object
    http: HttpClient
    credentials: CredentialAccess
    data_root: Path
    now: Callable[[], datetime]
    sleep: Callable[[float], None]
    redactor: Redactor

    def secret(self, value: str) -> Secret:
        """Wrap ``value`` as a :class:`Secret` and register it with
        :attr:`redactor` in the same step, so a caller can never forget to
        register a value it wraps."""
        wrapped = Secret(value)
        self.redactor.add(wrapped)
        return wrapped


class Connector(Protocol):
    """What every connector declares (Req 1.1)."""

    @property
    def connector_id(self) -> str: ...

    @property
    def display_name(self) -> str: ...

    @property
    def auth_style(self) -> AuthStyle: ...

    @property
    def capabilities(self) -> frozenset[Capability]: ...

    @property
    def credential_fields(self) -> tuple[CredentialField, ...]: ...

    def parse_settings(
        self, table: Mapping[str, object], context: SettingsContext
    ) -> object: ...


class KeyVerifier(Protocol):
    """Required when :attr:`AuthStyle.API_KEY` is declared."""

    def verify(
        self, session: ConnectorSession, values: Mapping[str, Secret]
    ) -> Granted: ...


class TokenIssuer(Protocol):
    """Required when :attr:`AuthStyle.LOGIN` is declared."""

    def login(
        self, session: ConnectorSession, values: Mapping[str, Secret]
    ) -> TokenSet: ...

    def refresh(self, session: ConnectorSession) -> TokenSet: ...


class ActivityPuller(Protocol):
    """Required when :attr:`Capability.PULL_ACTIVITIES` is declared."""

    def list_activities(
        self, session: ConnectorSession, since: datetime | None
    ) -> Listing: ...

    def fetch_activity(
        self, session: ConnectorSession, activity: RemoteActivity
    ) -> FetchResult: ...
