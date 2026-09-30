"""Pins the published surface of ``fitdocs.connectors`` (design.md
"PackageInit", Req 2.7).

The expected list is copied literally, in design.md's own order, from its
"PackageInit" section -- not derived from ``fitdocs.connectors.__all__``
itself, so a name silently dropped (or added) from ``__all__`` in production
code reds this test rather than the test trivially agreeing with it.
"""

from __future__ import annotations

import fitdocs.connectors as connectors_package
from fitdocs.connectors import errors, http, protocol, registry, secrets

# design.md "PackageInit": the 46 names, in design's listed order.
EXPECTED_ALL: tuple[str, ...] = (
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
)

# The module design.md says defines each name (used only for the identity
# pin below -- never for building the expected list itself).
_DEFINING_MODULE = {
    "Capability": protocol,
    "CapabilityInfo": protocol,
    "CAPABILITIES": protocol,
    "DRIVEN_CAPABILITIES": protocol,
    "AuthStyle": protocol,
    "SUPPORTED_AUTH_STYLES": protocol,
    "CredentialField": protocol,
    "RemoteActivity": protocol,
    "Listing": protocol,
    "ListingDeferral": protocol,
    "Fetched": protocol,
    "Declined": protocol,
    "Deferred": protocol,
    "FetchResult": protocol,
    "Granted": protocol,
    "TokenSet": protocol,
    "SettingsContext": protocol,
    "CredentialAccess": protocol,
    "ConnectorSession": protocol,
    "Connector": protocol,
    "KeyVerifier": protocol,
    "TokenIssuer": protocol,
    "ActivityPuller": protocol,
    "AuthFailure": errors,
    "AuthFailureKind": errors,
    "ConnectorError": errors,
    "NotConnectedError": errors,
    "ConnectorSettingsError": errors,
    "Secret": secrets,
    "REDACTED": secrets,
    "Redactor": secrets,
    "HttpClient": http,
    "CallMode": http,
    "Transport": http,
    "HttpRequest": http,
    "HttpResponse": http,
    "TransportError": http,
    "auth_failure_from": http,
    "register": registry,
    "unregister": registry,
    "get": registry,
    "available": registry,
    "validate_connector": registry,
    "DuplicateConnectorIdError": registry,
    "InvalidConnectorError": registry,
    "UnknownConnectorError": registry,
}


def test_expected_all_has_exactly_46_names_with_no_duplicates() -> None:
    assert len(EXPECTED_ALL) == 46
    assert len(set(EXPECTED_ALL)) == 46


def test_expected_all_covers_every_name_this_test_checks_identity_for() -> None:
    # Guards the fixture itself: if a name were added to EXPECTED_ALL above
    # without a matching _DEFINING_MODULE entry, the identity test below
    # would KeyError rather than silently skip it.
    assert set(EXPECTED_ALL) == set(_DEFINING_MODULE)


def test_published_surface_equals_the_design_literal_list_exactly() -> None:
    assert list(connectors_package.__all__) == list(EXPECTED_ALL)


def test_published_surface_has_no_duplicates() -> None:
    assert len(connectors_package.__all__) == len(set(connectors_package.__all__))


def test_every_published_name_is_identical_to_its_defining_modules_object() -> None:
    for name in EXPECTED_ALL:
        defining_module = _DEFINING_MODULE[name]
        published = getattr(connectors_package, name)
        original = getattr(defining_module, name)
        assert published is original, (
            f"{name!r} exposed by fitdocs.connectors is not the same object "
            f"as {defining_module.__name__}.{name}"
        )


def test_import_fitdocs_connectors_exposes_exactly_46_names() -> None:
    assert len(connectors_package.__all__) == 46
    for name in connectors_package.__all__:
        # Every published name must actually resolve on the package -- an
        # __all__ entry with nothing behind it would raise here.
        getattr(connectors_package, name)
