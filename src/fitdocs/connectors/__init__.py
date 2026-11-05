"""Pluggable remote data sources for fitdocs (design: connectors spec).

This package is the boundary between fitdocs and any remote service that
supplies ``.fit`` files: authentication, listing, fetching, and delivery into
the inbox. It owns the one place in ``src/`` (besides :mod:`fitdocs.tiles`)
allowed to open a network connection. It defines
:class:`fitdocs.connectors.secrets.Secret`, which carries credentials and
tokens and shows only a redaction marker in every text form, and
:class:`fitdocs.connectors.secrets.Redactor`, which scrubs every registered
secret value (signed download locations included) from any text before it
is reported.

A module inside this package may import only the standard library,
``fitdocs.layout``, ``fitdocs.settings``, ``fitdocs.inbox``,
``fitdocs.version``, the publish request and vocabulary leaves
(``fitdocs.publish.request`` and ``fitdocs.publish.outcomes``, imported only
by ``connectors/protocol.py``, and ``fitdocs.publish.request`` also by
``connectors/registry.py``), ``fitdocs.identity.matching`` (imported only
inside the listing-match helper of ``connectors/intervals.py``), and -- in
``connectors/ledger.py`` and ``connectors/credentials.py`` only -- ``tomli_w``. Only
``connectors/http.py`` may import ``urllib.request``/``urllib.error``. No
module here reads the system clock directly; ``now`` and ``sleep`` are always
passed in by the caller.

The published surface (``__all__``) is 67 names: the 50 that design.md's
"PackageInit" section and wellness-pull's "PackageSurface" list together, plus
publish-core's eight publish names, plus relay-server's five relay names, plus
strava-publish's four new protocol names (pinned by
``tests/connectors/test_surface.py``): the protocol layer's types and
vocabularies, the transport layer, the typed failures, the secret and its
redactor, and the registration operations. The built-in
connectors (``FolderConnector``, ``IntervalsConnector`` for an
intervals.icu account, ``RelayConnector`` for a fitdocs relay,
``StravaConnector`` for Strava through a relay, and ``GarminConnector`` for
Garmin's Connect Personal API) are
deliberately not published here -- internal, like
``fitdocs.load``'s ``ThresholdCalculator`` -- but each is registered under its
id at import time, below, so ``get("folder")``, ``get("intervals")``,
``get("relay")``, ``get("strava")`` and ``get("garmin")`` answer without any
settings file naming them.
"""

from __future__ import annotations

from fitdocs.connectors.errors import (
    AuthFailure,
    AuthFailureKind,
    ConnectorError,
    ConnectorSettingsError,
    NotConnectedError,
)
from fitdocs.connectors.folder import FolderConnector
from fitdocs.connectors.garmin import GarminConnector
from fitdocs.connectors.http import (
    CallMode,
    HttpClient,
    HttpRequest,
    HttpResponse,
    Transport,
    TransportError,
    auth_failure_from,
)
from fitdocs.connectors.intervals import IntervalsConnector
from fitdocs.connectors.protocol import (
    CAPABILITIES,
    DRIVEN_CAPABILITIES,
    PUBLISH_CAPABILITIES,
    SUPPORTED_AUTH_STYLES,
    TARGET_CODES,
    ActivityPuller,
    AuthStyle,
    BrowserConsentClient,
    Capability,
    CapabilityInfo,
    CompletedActivity,
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
    Post,
    PostPublisher,
    PublishCode,
    PublishRequest,
    PublishResult,
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
    WellnessDay,
    WellnessListing,
    WellnessPackage,
    WellnessPuller,
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
from fitdocs.connectors.relay import RelayConnector
from fitdocs.connectors.secrets import REDACTED, Redactor, Secret
from fitdocs.connectors.strava import StravaConnector

__all__ = [
    "Capability",
    "CapabilityInfo",
    "CAPABILITIES",
    "DRIVEN_CAPABILITIES",
    "AuthStyle",
    "SUPPORTED_AUTH_STYLES",
    "CredentialField",
    "RemoteActivity",
    "Listing",
    "ListingDeferral",
    "Fetched",
    "Declined",
    "Deferred",
    "FetchResult",
    "Granted",
    "TokenSet",
    "SettingsContext",
    "CredentialAccess",
    "ConnectorSession",
    "Connector",
    "KeyVerifier",
    "TokenIssuer",
    "ActivityPuller",
    "AuthFailure",
    "AuthFailureKind",
    "ConnectorError",
    "NotConnectedError",
    "ConnectorSettingsError",
    "Secret",
    "REDACTED",
    "Redactor",
    "HttpClient",
    "CallMode",
    "Transport",
    "HttpRequest",
    "HttpResponse",
    "TransportError",
    "auth_failure_from",
    "register",
    "unregister",
    "get",
    "available",
    "validate_connector",
    "DuplicateConnectorIdError",
    "InvalidConnectorError",
    "UnknownConnectorError",
    "WellnessPuller",
    "WellnessDay",
    "WellnessListing",
    "WellnessPackage",
    "PostPublisher",
    "PUBLISH_CAPABILITIES",
    "Post",
    "CompletedActivity",
    "PublishRequest",
    "PublishResult",
    "PublishCode",
    "TARGET_CODES",
    "RelayTokenClient",
    "RelayRefused",
    "RelayCapabilities",
    "RegistrationStarted",
    "RegistrationPolled",
    "BrowserConsentClient",
    "ConsentStarted",
    "ConsentPolled",
    "RelayBound",
]

# The built-in connectors: registered at import time so `get("folder")`,
# `get("intervals")`, `get("relay")`, `get("strava")` and `get("garmin")`
# answer whether or not any settings file names them. None of `FolderConnector`,
# `IntervalsConnector`, `RelayConnector`, `StravaConnector` and
# `GarminConnector` is in `__all__`
# above (internal, like `ThresholdCalculator`).
register(FolderConnector())
register(IntervalsConnector())
register(RelayConnector())
register(StravaConnector())
register(GarminConnector())
