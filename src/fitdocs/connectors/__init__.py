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
``fitdocs.version``, and -- in ``connectors/ledger.py`` and
``connectors/credentials.py`` only -- ``tomli_w``. Only
``connectors/http.py`` may import ``urllib.request``/``urllib.error``. No
module here reads the system clock directly; ``now`` and ``sleep`` are always
passed in by the caller.

The published surface (``__all__``) is the 46 names design.md's "PackageInit"
section lists (pinned by ``tests/connectors/test_surface.py``): the protocol
layer's types and vocabularies, the transport layer, the typed failures, the
secret and its redactor, and the registration operations. The built-in
folder connector (``FolderConnector``) is deliberately not published here --
internal, like ``fitdocs.load``'s ``ThresholdCalculator`` -- and its
registration line is added by a later task.
"""

from __future__ import annotations

from fitdocs.connectors.errors import (
    AuthFailure,
    AuthFailureKind,
    ConnectorError,
    ConnectorSettingsError,
    NotConnectedError,
)
from fitdocs.connectors.http import (
    CallMode,
    HttpClient,
    HttpRequest,
    HttpResponse,
    Transport,
    TransportError,
    auth_failure_from,
)
from fitdocs.connectors.protocol import (
    CAPABILITIES,
    DRIVEN_CAPABILITIES,
    SUPPORTED_AUTH_STYLES,
    ActivityPuller,
    AuthStyle,
    Capability,
    CapabilityInfo,
    Connector,
    ConnectorSession,
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
    RemoteActivity,
    SettingsContext,
    TokenIssuer,
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
from fitdocs.connectors.secrets import REDACTED, Redactor, Secret

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
]
