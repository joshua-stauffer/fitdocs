"""The one connector network module (design.md `HttpClient and Transport`,
Requirements 9.1-9.8, 10.4).

:class:`HttpRequest`/:class:`HttpResponse` are the plain value types every
connector and every transport speaks. :class:`TransportError` is what a
:data:`Transport` callable raises for a network failure, a timeout, a bad
URL, or an oversize body; its message never interpolates the underlying
exception's own text (a real ``ValueError`` or ``http.client.InvalidURL``
from a malformed URL carries the full URL -- query string, signed location,
and all -- inside its message, so repeating it would defeat the redaction
this module exists to provide). Every ``TransportError`` message is instead
built from a fixed reason naming only the exception's *type*, plus the
target: ``f"invalid request ({type(exc).__name__}): {target}"`` for a bad
URL or malformed request, ``"timed out: {target}"`` for a timeout raised
once the connection is made (urllib reports a connect-time timeout as a
``URLError``, which takes the network-failure reason),
``f"network failure ({type(exc).__name__}): {target}"`` for any other
network failure, and ``"response too large: {target}"`` for an oversize
body -- where ``target`` names only the scheme, host and path (Req 10.4),
never the query string, any fragment, or userinfo, and is replaced by a
fixed marker entirely when the request's URL is itself secret.

:class:`HttpClient` is the seam every connector calls through. It always
composes and sends the one fitdocs User-Agent (:func:`fitdocs.version.user_agent`),
overriding whatever the caller supplied -- case-insensitively -- (Req 9.1),
bounds every call with a timeout (Req 9.2), and registers every secret
header value and secret URL with its
:class:`~fitdocs.connectors.secrets.Redactor` before the first attempt (Req
10.1-10.4). ``HttpClient`` itself never redacts anything it sends or
returns -- it only ensures the values are registered early enough that a
caller's own later redaction (of a raised message, a logged line, a report)
catches them. In :attr:`CallMode.AUTH` it makes exactly one call, whatever
the response, and never retries a rejection (Req 9.4, 9.5). In
:attr:`CallMode.DATA` it retries a network failure or a retryable status up
to :data:`MAX_DATA_ATTEMPTS` times, honoring the service's stated
``Retry-After`` when it is within :data:`MAX_RETRY_AFTER_SECONDS`, else
:data:`BACKOFF_SECONDS` (Req 9.3).

**No module here reads the system clock** (package-wide rule, see
``connectors/__init__.py``): an HTTP-date ``Retry-After`` is not measured
against this process's own idea of "now". It is measured against the
*response's own* ``Date`` header instead -- the server's stated clock, not
ours -- via :func:`_parse_retry_after`. If the response carries no ``Date``
header, or that header is itself unparseable, an HTTP-date ``Retry-After``
is treated as unparseable too: :class:`HttpClient` falls back to
:data:`BACKOFF_SECONDS`, and :func:`auth_failure_from` reports
``retry_after_s=None``. A numeric (delta-seconds) ``Retry-After`` needs no
reference time and is unaffected by this rule; a negative value clamps to
``0.0`` and a non-finite value (``nan``, ``inf``, or ``-inf``) is treated as
unparseable.

:func:`urllib_transport` is the standard-library :data:`Transport`
implementation: it sends secret headers only as *unredirected* headers, so a
redirect target never receives them (Req 9.6), and it caps the body it reads
at :data:`MAX_RESPONSE_BYTES` (Req 9.7). :data:`Transport` itself is a plain
callable type, so tests substitute a scripted fake with no network access
(Req 9.8, see ``tests/connectors/conftest.py``'s ``FakeTransport``).

This is the only module in :mod:`fitdocs.connectors` that may import
``urllib.request``/``urllib.error``/``http.client`` (design.md "Allowed
Dependencies").
"""

from __future__ import annotations

import http.client
import math
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from datetime import UTC
from email.utils import parsedate_to_datetime
from enum import StrEnum
from typing import Final, Literal
from urllib.parse import urlsplit

from fitdocs.connectors.errors import AuthFailure, AuthFailureKind
from fitdocs.connectors.secrets import Redactor, Secret
from fitdocs.version import user_agent

DEFAULT_TIMEOUT_SECONDS: Final[float] = 30.0
MAX_DATA_ATTEMPTS: Final[int] = 3
BACKOFF_SECONDS: Final[tuple[float, ...]] = (2.0, 4.0)  # waits before attempts 2 and 3
MAX_RETRY_AFTER_SECONDS: Final[float] = 60.0
MAX_RESPONSE_BYTES: Final[int] = 64 * 1024 * 1024
RETRYABLE_STATUSES: Final[frozenset[int]] = frozenset({429, 500, 502, 503, 504})

_SIGNED_LOCATION_MARKER: Final[str] = "<signed location>"


@dataclass(frozen=True)
class HttpRequest:
    """One outgoing request. ``secret_headers`` are sent unredirected
    (Req 9.6, see :func:`urllib_transport`); ``url_is_secret`` marks a signed
    download location, never named in a failure message (Req 10.4)."""

    method: Literal["GET", "POST"]
    url: str
    headers: Mapping[str, str] = field(default_factory=dict)
    secret_headers: Mapping[str, Secret] = field(default_factory=dict)
    body: bytes | None = None
    url_is_secret: bool = False


@dataclass(frozen=True)
class HttpResponse:
    """A completed response, whatever its status. ``headers`` names are
    lowercased."""

    status: int
    headers: Mapping[str, str]
    body: bytes


class TransportError(Exception):
    """A network failure, a timeout, a bad URL, or an oversize body. The
    message never interpolates the underlying exception's text -- only its
    type name -- and never names more of the target than scheme, host and
    path (Req 10.4), or the signed-location marker when the request's URL
    is secret."""


Transport = Callable[[HttpRequest, float], HttpResponse]


def _describe_target(url: str, *, url_is_secret: bool) -> str:
    """Scheme, host and path only -- never userinfo, query, or fragment."""

    if url_is_secret:
        return _SIGNED_LOCATION_MARKER
    parts = urlsplit(url)
    host = parts.hostname or ""
    netloc = host if parts.port is None else f"{host}:{parts.port}"
    return f"{parts.scheme}://{netloc}{parts.path}"


def _lowered_headers(headers: Mapping[str, str]) -> dict[str, str]:
    return {name.lower(): value for name, value in headers.items()}


def urllib_transport(request: HttpRequest, timeout: float) -> HttpResponse:
    """The standard-library :data:`Transport`. ``urllib.request.urlopen`` is
    referenced through the module (``urllib.request.urlopen``, not a bound
    import), so tests can substitute it."""

    target = _describe_target(request.url, url_is_secret=request.url_is_secret)
    try:
        urllib_request = urllib.request.Request(
            request.url,
            data=request.body,
            method=request.method,
            headers=dict(request.headers),
        )
        for name, secret in request.secret_headers.items():
            # Unredirected: a redirect target never receives this header
            # (Req 9.6).
            urllib_request.add_unredirected_header(name, secret.reveal())

        with urllib.request.urlopen(urllib_request, timeout=timeout) as response:
            status = response.status
            headers = _lowered_headers(dict(response.headers))
            body = response.read(MAX_RESPONSE_BYTES + 1)
    except urllib.error.HTTPError as exc:
        status = exc.code
        headers = _lowered_headers(dict(exc.headers or {}))
        body = exc.read(MAX_RESPONSE_BYTES + 1)
    except urllib.error.URLError as exc:
        raise TransportError(
            f"network failure ({type(exc).__name__}): {target}"
        ) from exc
    except TimeoutError as exc:
        raise TransportError(f"timed out: {target}") from exc
    except (ValueError, http.client.HTTPException) as exc:
        raise TransportError(
            f"invalid request ({type(exc).__name__}): {target}"
        ) from exc
    except OSError as exc:
        raise TransportError(
            f"network failure ({type(exc).__name__}): {target}"
        ) from exc

    if len(body) > MAX_RESPONSE_BYTES:
        raise TransportError(f"response too large: {target}")
    return HttpResponse(status=status, headers=headers, body=body)


class CallMode(StrEnum):
    AUTH = "auth"
    DATA = "data"


def _parse_retry_after(headers: Mapping[str, str]) -> float | None:
    """The wait a ``Retry-After`` header (lowercased key) states, in
    seconds, or ``None`` when absent or unparseable as either a
    delta-seconds number or an HTTP-date.

    An HTTP-date is measured against the response's own ``date`` header
    (also lowercased) -- never against this process's clock (module
    docstring). Absent or unparseable ``date`` makes an HTTP-date
    ``Retry-After`` unparseable too. A negative delta-seconds value clamps
    to ``0.0``; a non-finite one (``nan``, ``inf``, or ``-inf``) is
    unparseable.
    """

    value = headers.get("retry-after")
    if value is None:
        return None
    text = value.strip()
    try:
        seconds = float(text)
    except ValueError:
        pass
    else:
        if not math.isfinite(seconds):
            return None
        return max(seconds, 0.0)

    try:
        retry_at = parsedate_to_datetime(text)
    except (TypeError, ValueError, IndexError):
        return None

    date_value = headers.get("date")
    if date_value is None:
        return None
    try:
        reference = parsedate_to_datetime(date_value)
    except (TypeError, ValueError, IndexError):
        return None

    if retry_at.tzinfo is None:
        retry_at = retry_at.replace(tzinfo=UTC)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=UTC)
    delta = (retry_at - reference).total_seconds()
    return max(delta, 0.0)


class HttpClient:
    """The seam every connector sends a request through. See module
    docstring for the two modes and the clock-free ``Retry-After`` rule."""

    def __init__(
        self,
        transport: Transport,
        *,
        mode: CallMode,
        redactor: Redactor,
        sleep: Callable[[float], None],
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self._transport = transport
        self._mode = mode
        self._redactor = redactor
        self._sleep = sleep
        self._timeout = timeout

    @property
    def mode(self) -> CallMode:
        return self._mode

    def _register_secrets(self, request: HttpRequest) -> None:
        for secret in request.secret_headers.values():
            self._redactor.add(secret)
        if request.url_is_secret:
            self._redactor.add(request.url)

    def _with_composed_user_agent(self, request: HttpRequest) -> HttpRequest:
        headers = {
            name: value
            for name, value in request.headers.items()
            if name.lower() != "user-agent"
        }
        headers["User-Agent"] = user_agent()
        return replace(request, headers=headers)

    def send(self, request: HttpRequest) -> HttpResponse:
        self._register_secrets(request)
        prepared = self._with_composed_user_agent(request)
        if self._mode is CallMode.AUTH:
            return self._transport(prepared, self._timeout)
        return self._send_data(prepared)

    def _retry_wait(self, response: HttpResponse, attempt: int) -> float | None:
        """The wait before the next attempt, or ``None`` when the service's
        stated wait exceeds :data:`MAX_RETRY_AFTER_SECONDS` and retrying
        must stop."""

        retry_after = _parse_retry_after(response.headers)
        if retry_after is not None:
            if retry_after > MAX_RETRY_AFTER_SECONDS:
                return None
            return retry_after
        return BACKOFF_SECONDS[attempt - 1]

    def _send_data(self, request: HttpRequest) -> HttpResponse:
        attempt = 1
        while True:
            try:
                response = self._transport(request, self._timeout)
            except TransportError:
                if attempt == MAX_DATA_ATTEMPTS:
                    raise
                self._sleep(BACKOFF_SECONDS[attempt - 1])
                attempt += 1
                continue

            if response.status not in RETRYABLE_STATUSES:
                return response
            if attempt == MAX_DATA_ATTEMPTS:
                return response
            wait = self._retry_wait(response, attempt)
            if wait is None:
                return response
            self._sleep(wait)
            attempt += 1

    def get(
        self,
        url: str,
        *,
        headers: Mapping[str, str] | None = None,
        secret_headers: Mapping[str, Secret] | None = None,
        url_is_secret: bool = False,
    ) -> HttpResponse:
        return self.send(
            HttpRequest(
                method="GET",
                url=url,
                headers=headers or {},
                secret_headers=secret_headers or {},
                url_is_secret=url_is_secret,
            )
        )

    def post(
        self,
        url: str,
        *,
        body: bytes,
        headers: Mapping[str, str] | None = None,
        secret_headers: Mapping[str, Secret] | None = None,
    ) -> HttpResponse:
        return self.send(
            HttpRequest(
                method="POST",
                url=url,
                headers=headers or {},
                secret_headers=secret_headers or {},
                body=body,
            )
        )


def auth_failure_from(
    response: HttpResponse, *, service_message: str | None = None
) -> AuthFailure | None:
    """401 -> REJECTED, 403 -> BLOCKED, 429 -> RATE_LIMITED (``Retry-After``
    parsed against the response's own ``Date`` header, never the system
    clock), 5xx -> UNAVAILABLE; ``None`` for anything else. A connector adds
    its own service-specific kinds (CHALLENGE, LOCKED)."""

    message = service_message if service_message is not None else str(response.status)
    if response.status == 401:
        return AuthFailure(AuthFailureKind.REJECTED, message)
    if response.status == 403:
        return AuthFailure(AuthFailureKind.BLOCKED, message)
    if response.status == 429:
        retry_after = _parse_retry_after(response.headers)
        return AuthFailure(AuthFailureKind.RATE_LIMITED, message, retry_after)
    if 500 <= response.status < 600:
        return AuthFailure(AuthFailureKind.UNAVAILABLE, message)
    return None
