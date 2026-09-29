"""Typed connector failures and their next-step guidance (Req 1.7, 5.6, 6.10, 6.11).

:class:`AuthFailure` is what a connector's ``verify``/``login``/``refresh``
raises on refusal; :func:`auth_failure_from` (``connectors/http.py``) builds
one from an HTTP response. :class:`ConnectorError` ends the current
instance's pull with a user-facing message; :class:`NotConnectedError` is
the subclass raised when an instance has no usable credentials.
:class:`ConnectorSettingsError` is raised by ``parse_settings`` for a
connector's own malformed settings key.

:data:`NEXT_STEPS` and :func:`next_step` live here, rather than in
``connect.py``, so both ``connect.py`` and ``pull.py`` can render the same
guidance without importing each other.
"""

from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from typing import Final


class AuthFailureKind(StrEnum):
    """Why an authentication attempt or a stored credential was refused."""

    REJECTED = "rejected"  # bad or revoked credentials (typically 401)
    RATE_LIMITED = "rate-limited"  # 429 or a service throttle
    CHALLENGE = "challenge"  # an extra verification step fitdocs cannot answer
    LOCKED = "locked"  # account lockout
    BLOCKED = "blocked"  # the client was refused (typically 403)
    UNAVAILABLE = "unavailable"  # 5xx or unreachable


class AuthFailure(Exception):
    """Raised by ``verify``/``login``/``refresh`` on refusal."""

    def __init__(
        self,
        kind: AuthFailureKind,
        service_message: str,
        retry_after_s: float | None = None,
    ) -> None:
        super().__init__(service_message)
        self.kind = kind
        self.service_message = service_message
        self.retry_after_s = retry_after_s


class ConnectorError(Exception):
    """Ends this instance's pull; the message is user-facing."""


class NotConnectedError(ConnectorError):
    """Raised when an instance has no usable credentials."""


class ConnectorSettingsError(Exception):
    """Raised by a connector's ``parse_settings`` for its own malformed key."""

    def __init__(self, key: str, message: str) -> None:
        super().__init__(message)
        self.key = key
        self.message = message


NEXT_STEPS: Final[Mapping[AuthFailureKind, str]] = {
    AuthFailureKind.REJECTED: (
        "Check the credentials and run `fitdocs connect {name}` again."
    ),
    AuthFailureKind.RATE_LIMITED: (
        "Wait{retry} before trying again. fitdocs never retries a sign-in: "
        "some services extend the limit on every attempt."
    ),
    AuthFailureKind.CHALLENGE: (
        "The service asked for a verification step fitdocs cannot complete. "
        "Complete it on the service's own site, then run `fitdocs connect "
        "{name}` again."
    ),
    AuthFailureKind.LOCKED: (
        "The service reports the account locked. Unlock it on the service's "
        "own site; do not try again until it is unlocked."
    ),
    AuthFailureKind.BLOCKED: (
        "The service refused this client. Please report it at "
        "https://github.com/joshua-stauffer/fitdocs/issues with the message "
        "above."
    ),
    AuthFailureKind.UNAVAILABLE: ("The service could not be reached. Try again later."),
}


def _render_retry(retry_after_s: float | None) -> str:
    if retry_after_s is None:
        return ""
    seconds: float | int = retry_after_s
    if float(retry_after_s).is_integer():
        seconds = int(retry_after_s)
    return f" at least {seconds} seconds"


def next_step(kind: AuthFailureKind, *, name: str, retry_after_s: float | None) -> str:
    """Render the next-step guidance for ``kind``, naming ``name``.

    ``retry_after_s`` is only used for :attr:`AuthFailureKind.RATE_LIMITED`:
    a known wait is named, an unknown one (``None``) renders no wait at all.
    """
    return NEXT_STEPS[kind].format(name=name, retry=_render_retry(retry_after_s))
