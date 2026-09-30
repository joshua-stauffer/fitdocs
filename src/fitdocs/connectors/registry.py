"""The connector registry: the one gate every connector passes (design.md
"Registry layer", Req 2.1-2.6, 2.8).

Shaped like :mod:`fitdocs.load.registry`, the calculator registry this
package mirrors (Req 2.1, "the surface the plugin kind validates against"):
a module-level ``dict`` keyed by ``connector_id`` that preserves registration
order, one validation gate every registration passes through, and the same
three error shapes. This module registers no connector of its own; the
folder connector's own registration line lives in ``connectors/__init__.py``
(a later task), exactly as importing :mod:`fitdocs.load` registers the
built-in ``threshold`` calculator through :func:`fitdocs.load.registry.register`.

:func:`validate_connector` is pure introspection: it reads and checks every
member inside one broad ``except Exception`` boundary -- a raising property
*or* a raising post-read check (e.g. a malformed ``CredentialField`` whose
non-string name breaks a regex match, or a ``capabilities`` value whose
``__iter__`` raises) is a reason, never an exception that escapes this
function. A ``current`` variable, updated immediately before each member's
read and again before its check, names *which* member was being processed
when the boundary catches something, so the reason says where in the
declaration the problem was, not only what the underlying exception said.
It never calls any operation a connector declares (``parse_settings``,
``verify``, ``login``, ``refresh``, ``list_activities``, ``fetch_activity``).
Registering (and therefore validating) a connector has no side effects
(Req 2.2).
"""

from __future__ import annotations

import re

from fitdocs.connectors.protocol import (
    AuthStyle,
    Capability,
    Connector,
    CredentialField,
)

__all__ = [
    "DuplicateConnectorIdError",
    "InvalidConnectorError",
    "UnknownConnectorError",
    "available",
    "get",
    "register",
    "unregister",
    "validate_connector",
]

_REGISTRY: dict[str, Connector] = {}
"""Module-global store keyed by ``connector_id`` in registration order."""

_CONNECTOR_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
_FIELD_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,63}$")


class InvalidConnectorError(ValueError):
    """Raised when a connector offered for registration fails the contract.

    Subclasses :class:`ValueError`, matching
    :class:`fitdocs.load.registry.InvalidCalculatorError`.
    """


class DuplicateConnectorIdError(ValueError):
    """Raised when a connector claims an id that is already registered.

    The incumbent registration is left untouched (Req 2.4). Carries the
    contested :attr:`connector_id` so a caller that catches this can name the
    incumbent's id without parsing the message, matching
    :class:`fitdocs.load.registry.DuplicateCalculatorIdError`.
    """

    def __init__(self, message: str, *, connector_id: str) -> None:
        super().__init__(message)
        self.connector_id = connector_id


class UnknownConnectorError(Exception):
    """Raised when a connector id is looked up that is not registered.

    The message names the requested id and every registered id (Req 2.5).
    """


def _reason_for_credential_fields(fields: object, auth_style: object) -> str | None:
    if not isinstance(fields, tuple) or not all(
        isinstance(field, CredentialField) for field in fields
    ):
        return "credential_fields must be a tuple of CredentialField"

    names = [field.name for field in fields]
    for field in fields:
        if not _FIELD_NAME_PATTERN.fullmatch(field.name):
            return "credential_fields must have valid names"
        if not isinstance(field.label, str) or not field.label:
            return "credential_fields must have non-empty labels"
    if len(names) != len(set(names)):
        return "credential_fields must have unique names"

    if auth_style is AuthStyle.NONE:
        if fields:
            return "credential_fields must be empty when auth_style is NONE"
    else:
        if not fields:
            return "credential_fields must be non-empty when auth_style is not NONE"

    return None


def validate_connector(obj: object) -> str | None:
    """Return ``None`` when ``obj`` satisfies the connector contract, else a
    human-readable reason naming the first violated member.

    Checked in design.md's order (Req 2.3): ``connector_id`` matches
    ``^[a-z0-9][a-z0-9-]{0,63}$``; ``display_name`` is a non-empty ``str``;
    ``auth_style`` is an :class:`~fitdocs.connectors.protocol.AuthStyle`;
    ``capabilities`` is a non-empty ``frozenset`` of
    :class:`~fitdocs.connectors.protocol.Capability`; ``credential_fields``
    is a ``tuple`` of :class:`~fitdocs.connectors.protocol.CredentialField`
    with valid, unique names and non-empty labels, empty exactly when
    ``auth_style`` is ``NONE``; ``parse_settings`` is callable; ``verify`` is
    callable when ``API_KEY`` is the auth style; ``login`` and ``refresh``
    are callable when ``LOGIN`` is the auth style; ``list_activities`` and
    ``fetch_activity`` are callable when ``PULL_ACTIVITIES`` is declared.

    Every other capability and the reserved ``OAUTH_BROWSER`` auth style
    impose no operation: this version of fitdocs never invokes them (Req
    1.4, 1.7).

    Never calls ``parse_settings``, ``verify``, ``login``, ``refresh``,
    ``list_activities``, or ``fetch_activity`` -- registration stays
    side-effect free. Accepts any object without raising: a malformed shape
    (a missing attribute, a raising property, or a raising post-read check
    such as a non-string ``CredentialField.name`` breaking a regex match, or
    a ``capabilities`` value whose ``__iter__`` raises) produces a reason
    rather than an exception, and that reason names the member being
    processed when the problem surfaced.
    """
    current = "connector_id"
    try:
        connector_id = getattr(obj, current, None)
        if not isinstance(connector_id, str) or not _CONNECTOR_ID_PATTERN.fullmatch(
            connector_id
        ):
            return "connector_id must match ^[a-z0-9][a-z0-9-]{0,63}$"

        current = "display_name"
        display_name = getattr(obj, current, None)
        if not isinstance(display_name, str) or not display_name:
            return "display_name must be a non-empty str"

        current = "auth_style"
        auth_style = getattr(obj, current, None)
        if not isinstance(auth_style, AuthStyle):
            return "auth_style must be an AuthStyle"

        current = "capabilities"
        capabilities = getattr(obj, current, None)
        if not isinstance(capabilities, frozenset) or not capabilities:
            return "capabilities must be a non-empty frozenset of Capability"
        if not all(isinstance(c, Capability) for c in capabilities):
            return "capabilities must be a non-empty frozenset of Capability"

        current = "credential_fields"
        credential_fields = getattr(obj, current, None)
        reason = _reason_for_credential_fields(credential_fields, auth_style)
        if reason is not None:
            return reason

        current = "parse_settings"
        parse_settings = getattr(obj, current, None)
        if not callable(parse_settings):
            return "parse_settings must be callable"

        if auth_style is AuthStyle.API_KEY:
            current = "verify"
            verify = getattr(obj, current, None)
            if not callable(verify):
                return "verify must be callable when auth_style is API_KEY"

        if auth_style is AuthStyle.LOGIN:
            current = "login"
            login = getattr(obj, current, None)
            if not callable(login):
                return "login must be callable when auth_style is LOGIN"

            current = "refresh"
            refresh = getattr(obj, current, None)
            if not callable(refresh):
                return "refresh must be callable when auth_style is LOGIN"

        current = "capabilities"
        if Capability.PULL_ACTIVITIES in capabilities:
            current = "list_activities"
            list_activities = getattr(obj, current, None)
            if not callable(list_activities):
                return (
                    "list_activities must be callable when PULL_ACTIVITIES is declared"
                )

            current = "fetch_activity"
            fetch_activity = getattr(obj, current, None)
            if not callable(fetch_activity):
                return (
                    "fetch_activity must be callable when PULL_ACTIVITIES is declared"
                )
    except Exception as exc:  # noqa: BLE001 - a raising property/check is a reason
        return f"reading {current!r} raised {exc!r}"

    return None


def register(connector: Connector) -> None:
    """Register ``connector`` under its ``connector_id`` in registration order.

    Validates ``connector`` against the contract first (Req 2.2); a rejected
    connector never enters the registry and :class:`InvalidConnectorError`
    is raised, naming the violated member.

    Raises :class:`DuplicateConnectorIdError` if a connector with the same id
    is already registered (the message names the id); the existing
    registration is left untouched (Req 2.4). Both error types subclass
    :class:`ValueError`.
    """
    reason = validate_connector(connector)
    if reason is not None:
        # type(connector).__name__, never repr(connector): a malformed
        # candidate can be malformed in its __repr__ too, and this error's
        # own construction must not raise on the way to reporting one.
        raise InvalidConnectorError(
            f"a {type(connector).__name__} instance does not satisfy the "
            f"connector contract: {reason}"
        )

    connector_id = connector.connector_id
    if connector_id in _REGISTRY:
        raise DuplicateConnectorIdError(
            f"a connector is already registered under id {connector_id!r}",
            connector_id=connector_id,
        )
    _REGISTRY[connector_id] = connector


def unregister(connector_id: str) -> None:
    """Remove ``connector_id`` from the registry when present; a no-op
    otherwise (Req 2.6)."""
    _REGISTRY.pop(connector_id, None)


def get(connector_id: str) -> Connector:
    """Return the connector registered under ``connector_id``.

    Raises :class:`UnknownConnectorError` when no connector is registered
    under that id; the message names the id and lists the registered ids
    (Req 2.5).
    """
    try:
        return _REGISTRY[connector_id]
    except KeyError:
        registered = ", ".join(_REGISTRY) or "none"
        raise UnknownConnectorError(
            f"unknown connector id {connector_id!r}; registered: {registered}"
        ) from None


def available() -> tuple[Connector, ...]:
    """Return all registered connectors in registration order."""
    return tuple(_REGISTRY.values())
