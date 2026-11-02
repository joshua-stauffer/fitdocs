"""The relay's one client for provider calls (Outbound).

A request carries plain headers and secret headers. Secret headers are added
unredirected, so a redirect to another address never carries them. A failure
is raised as `OutboundError` whose message is its kind and nothing else: no
URL, header or body reaches the error's message, args, repr, chained
exceptions or formatted traceback. This module is the only importer of
`urllib.request` and `http.client` in the relay.

The response body is returned as bytes, undecoded; the caller decides how to
read it.
"""

from __future__ import annotations

import http.client
import urllib.error
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from email.message import Message
from typing import Final, Literal

from . import __version__

MAX_OUTBOUND_RESPONSE_BYTES: Final = 8 * 1024 * 1024
USER_AGENT: Final = f"fitdocs-relay/{__version__}"

ErrorKind = Literal["timeout", "network", "invalid", "too-large"]

# Replaced by tests so no real connection is made.
_HttpsHandler = urllib.request.HTTPSHandler


class OutboundError(Exception):
    """A provider call failed; the message is the kind only."""

    def __init__(self, kind: ErrorKind) -> None:
        super().__init__(kind)
        self.kind: ErrorKind = kind

    def __repr__(self) -> str:
        return f"OutboundError({self.kind!r})"


@dataclass(frozen=True)
class OutboundRequest:
    method: Literal["GET", "POST", "PUT", "DELETE"]
    url: str
    headers: Mapping[str, str]
    secret_headers: Mapping[str, str] = field(repr=False)
    body: bytes | None = field(default=None, repr=False)
    url_is_secret: bool = False

    def __repr__(self) -> str:
        shown = "<secret>" if self.url_is_secret else self.url
        return f"OutboundRequest({self.method} {shown})"


@dataclass(frozen=True)
class OutboundResponse:
    status: int
    headers: Mapping[str, str]
    body: bytes = field(repr=False)


Outbound = Callable[[OutboundRequest, float], OutboundResponse]


class _HttpsOnlyRedirects(urllib.request.HTTPRedirectHandler):
    """Follow a redirect only for a body-less request, and only to https.

    A request with a body (which may carry client credentials) never follows a
    redirect: the 3xx is returned to the caller as the response, so the body
    is never resent to another address.
    """

    def redirect_request(  # type: ignore[no-untyped-def]
        self, req, fp, code, msg, headers, newurl
    ):
        if req.data is not None:
            return None
        if not newurl.lower().startswith("https://"):
            fp.close()
            raise OutboundError("invalid")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _opener() -> urllib.request.OpenerDirector:
    opener = urllib.request.OpenerDirector()
    for handler in (
        urllib.request.ProxyHandler(),
        _HttpsHandler(),
        _HttpsOnlyRedirects(),
        urllib.request.HTTPDefaultErrorHandler(),
        urllib.request.HTTPErrorProcessor(),
    ):
        opener.add_handler(handler)
    return opener


def _clean(text: str) -> bool:
    return "\r" not in text and "\n" not in text and "\0" not in text


def _build(request: OutboundRequest) -> urllib.request.Request:
    if not request.url.lower().startswith("https://"):
        raise OutboundError("invalid")
    names = [n.lower() for n in request.headers] + [
        n.lower() for n in request.secret_headers
    ]
    if len(set(names)) != len(names):
        raise OutboundError("invalid")
    for mapping in (request.headers, request.secret_headers):
        for name, value in mapping.items():
            if not name or not _clean(name) or ":" in name or not _clean(value):
                raise OutboundError("invalid")
    plain = {**request.headers, "User-Agent": USER_AGENT}
    built = urllib.request.Request(
        request.url, data=request.body, headers=plain, method=request.method
    )
    for name, value in request.secret_headers.items():
        built.add_unredirected_header(name, value)
    return built


def _read_capped(source: http.client.HTTPResponse | urllib.error.HTTPError) -> bytes:
    """Read one byte past the cap, so the caller can tell over from exactly at."""
    return source.read(MAX_OUTBOUND_RESPONSE_BYTES + 1)


def _headers(source: Message[str, str]) -> dict[str, str]:
    joined: dict[str, str] = {}
    for name, value in source.items():
        key = name.lower()
        joined[key] = f"{joined[key]}, {value}" if key in joined else value
    return joined


def urllib_outbound(request: OutboundRequest, timeout: float) -> OutboundResponse:
    if not timeout > 0:
        raise OutboundError("invalid")
    built = _build(request)
    kind: ErrorKind | None = None
    status = 0
    headers: dict[str, str] = {}
    body = b""
    # Every OutboundError is raised below, outside any `except`, so none
    # carries the exception that caused it as its __context__.
    try:
        try:
            reply = _opener().open(built, timeout=timeout)
        except urllib.error.HTTPError as error:
            with error:
                status, headers = error.code, _headers(error.headers)
                body = _read_capped(error)
        else:
            with reply:
                status, headers = reply.status, _headers(reply.headers)
                body = _read_capped(reply)
    except TimeoutError:
        kind = "timeout"
    except http.client.InvalidURL:
        kind = "invalid"
    except urllib.error.URLError as error:
        kind = "timeout" if isinstance(error.reason, TimeoutError) else "network"
    except (OSError, http.client.HTTPException):
        kind = "network"
    except ValueError:
        kind = "invalid"
    if kind is None and len(body) > MAX_OUTBOUND_RESPONSE_BYTES:
        kind = "too-large"
    if kind is not None:
        raise OutboundError(kind)
    return OutboundResponse(status, headers, body)
