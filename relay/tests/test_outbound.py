"""The relay's outbound client (Outbound): headers, redirects, caps, error kinds."""

from __future__ import annotations

import http.client
import io
import re
import socket
import ssl
import traceback
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

import pytest

from fitdocs_relay import outbound
from fitdocs_relay.outbound import (
    MAX_OUTBOUND_RESPONSE_BYTES,
    OutboundError,
    OutboundRequest,
    OutboundResponse,
    urllib_outbound,
)

SECRET_TOKEN = "tok-9f3a-SECRET"
SECRET_QUERY = "sig=Zq81-PLANTED-SECRET"
URL = "https://api.example.test/v3/thing?page=2"
SECRET_URL = f"https://hook.example.test/path?{SECRET_QUERY}"


class _Stream(io.BytesIO):
    """The response stream; records how many bytes the client pulled from it."""

    def __init__(self, raw: bytes) -> None:
        super().__init__(raw)
        self.delivered = 0

    def read(self, size: int | None = -1) -> bytes:
        chunk = super().read(size)
        self.delivered += len(chunk)
        return chunk

    def readline(self, size: int | None = -1) -> bytes:
        chunk = super().readline(size)
        self.delivered += len(chunk)
        return chunk

    def read1(self, size: int | None = -1) -> bytes:
        chunk = super().read1(size)
        self.delivered += len(chunk)
        return chunk

    def readinto(self, buffer: Any) -> int:
        count = super().readinto(buffer) or 0
        self.delivered += count
        return count


class _Socket:
    def __init__(self, raw: bytes, streams: list[_Stream]) -> None:
        self._raw = raw
        self._streams = streams

    def makefile(self, *_args: Any, **_kwargs: Any) -> io.BytesIO:
        stream = _Stream(self._raw)
        self._streams.append(stream)
        return stream


def raw(
    status: int = 200,
    body: bytes = b"",
    headers: tuple[tuple[str, str], ...] = (),
    reason: str = "R",
) -> bytes:
    lines = [f"HTTP/1.1 {status} {reason}", f"Content-Length: {len(body)}"]
    lines += [f"{name}: {value}" for name, value in headers]
    return ("\r\n".join(lines) + "\r\n\r\n").encode("latin-1") + body


@dataclass
class Seen:
    url: str
    method: str
    data: bytes | None
    headers: dict[str, str]
    unredirected: dict[str, str]


class Script:
    """Stands in for the HTTPS handler; each entry is raw bytes or an exception."""

    def __init__(self, *steps: bytes | BaseException) -> None:
        self.steps = list(steps)
        self.seen: list[Seen] = []
        self.timeouts: list[object] = []
        self.streams: list[_Stream] = []
        self.responses: list[http.client.HTTPResponse] = []

    def handler(self) -> urllib.request.BaseHandler:
        script = self

        class Fake(urllib.request.BaseHandler):
            def https_open(self, req: urllib.request.Request) -> Any:
                script.seen.append(
                    Seen(
                        req.full_url,
                        req.get_method(),
                        req.data if isinstance(req.data, bytes) else None,
                        {k.lower(): v for k, v in req.headers.items()},
                        {k.lower(): v for k, v in req.unredirected_hdrs.items()},
                    )
                )
                script.timeouts.append(req.timeout)
                step = script.steps.pop(0)
                if isinstance(step, BaseException):
                    raise step
                response = http.client.HTTPResponse(
                    _Socket(step, script.streams),  # type: ignore[arg-type]
                    method=req.get_method(),
                )
                response.begin()
                script.responses.append(response)
                response.url = req.full_url
                response.msg = response.reason  # type: ignore[assignment]
                return response

        return Fake()


@pytest.fixture
def script(monkeypatch: pytest.MonkeyPatch) -> Callable[..., Script]:
    def install(*steps: bytes | BaseException) -> Script:
        scripted = Script(*steps)
        monkeypatch.setattr(outbound, "_HttpsHandler", scripted.handler)
        return scripted

    return install


def req(
    url: str = URL,
    method: Literal["GET", "POST", "PUT", "DELETE"] = "GET",
    headers: dict[str, str] | None = None,
    secret: dict[str, str] | None = None,
    body: bytes | None = None,
    url_is_secret: bool = False,
) -> OutboundRequest:
    return OutboundRequest(
        method=method,
        url=url,
        headers=headers or {},
        secret_headers=secret if secret is not None else {},
        body=body,
        url_is_secret=url_is_secret,
    )


# --- the request as sent -----------------------------------------------------


@pytest.mark.parametrize(
    ("method", "body"),
    [("GET", None), ("POST", b"a=1"), ("PUT", b"\x00\x01"), ("DELETE", None)],
)
def test_each_method_body_and_timeout_reach_the_wire(
    script: Callable[..., Script], method: Any, body: bytes | None
) -> None:
    s = script(raw())
    urllib_outbound(req(method=method, body=body), 7.5)
    (seen,) = s.seen
    assert seen.method == method
    assert seen.data == body
    assert s.timeouts == [7.5]


def test_the_relay_user_agent_replaces_a_caller_one(
    script: Callable[..., Script],
) -> None:
    s = script(raw())
    urllib_outbound(req(headers={"user-agent": "caller/9", "X-Plain": "p"}), 5)
    sent = s.seen[0].headers
    assert re.fullmatch(r"fitdocs-relay/\d+\.\d+\.\d+", sent["user-agent"])
    assert sent["x-plain"] == "p"


def test_secret_headers_go_out_unredirected_and_absent_from_the_redirect_target(
    script: Callable[..., Script],
) -> None:
    s = script(
        raw(302, headers=(("Location", "https://other.example.test/next"),)),
        raw(200, b"ok"),
    )
    response = urllib_outbound(
        req(
            headers={"X-Plain": "p"}, secret={"Authorization": f"Bearer {SECRET_TOKEN}"}
        ),
        5,
    )
    first, second = s.seen
    assert response.body == b"ok"
    assert first.url == URL
    assert second.url == "https://other.example.test/next"
    # The precondition: the first hop did carry it, and as an unredirected header.
    assert first.unredirected == {"authorization": f"Bearer {SECRET_TOKEN}"}
    assert "authorization" not in first.headers
    # The plain header follows the redirect; the secret one does not.
    assert second.headers["x-plain"] == "p"
    assert SECRET_TOKEN not in repr(second)
    assert second.unredirected == {}


def test_a_redirect_to_plain_http_is_refused_and_never_requested(
    script: Callable[..., Script],
) -> None:
    s = script(raw(302, headers=(("Location", "http://other.example.test/x"),)))
    with pytest.raises(OutboundError) as caught:
        urllib_outbound(req(secret={"Authorization": SECRET_TOKEN}), 5)
    assert caught.value.kind == "invalid"
    assert len(s.seen) == 1
    assert caught.value.__context__ is None
    (first_hop,) = s.responses
    assert first_hop.isclosed()


def test_the_plain_http_refusal_carries_nothing_from_the_redirect(
    script: Callable[..., Script],
) -> None:
    planted = "LOC-PLANTED.example"
    s = script(
        raw(
            302,
            reason="REASON-PLANTED",
            headers=(
                ("Location", f"http://{planted}/x?{SECRET_QUERY}"),
                ("X-Hdr", "HDR-PLANTED"),
            ),
        )
    )
    with pytest.raises(OutboundError) as caught:
        urllib_outbound(
            req(
                url=SECRET_URL,
                url_is_secret=True,
                secret={"Authorization": f"Bearer {SECRET_TOKEN}"},
            ),
            5,
        )
    error = caught.value
    assert len(s.seen) == 1  # the refusal came from the redirect, not the request
    assert error.__cause__ is None
    assert error.__context__ is None
    assert str(error) == "invalid"
    assert repr(error) == "OutboundError('invalid')"
    shown = "".join(traceback.format_exception(error))
    for needle in (
        planted,
        SECRET_QUERY,
        SECRET_TOKEN,
        "REASON-PLANTED",
        "HDR-PLANTED",
        "hook.example.test",
    ):
        assert needle not in shown


@pytest.mark.parametrize("code", [301, 302, 303, 307, 308])
def test_a_request_with_a_body_never_follows_a_redirect(
    script: Callable[..., Script], code: int
) -> None:
    credentials = b"client_secret=BODY-PLANTED"
    s = script(
        raw(code, headers=(("Location", "https://other.example.test/next"),)),
        raw(200, b"followed"),
    )
    response = urllib_outbound(req(method="POST", body=credentials), 5)
    # The precondition: the first hop did carry the body.
    assert [seen.data for seen in s.seen] == [credentials]
    assert response.status == code
    assert response.headers["location"] == "https://other.example.test/next"
    assert response.body == b""


def test_the_real_opener_connects_with_a_verifying_tls_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Stop(BaseException):
        pass

    contexts: list[ssl.SSLContext] = []

    def record_and_stop(self: http.client.HTTPSConnection) -> None:
        contexts.append(self._context)  # type: ignore[attr-defined]
        raise Stop

    monkeypatch.setattr(http.client.HTTPSConnection, "connect", record_and_stop)
    with pytest.raises(Stop):
        urllib_outbound(req(), 5)
    # The connection was reached through the real opener, and stopped there:
    # no socket was opened.
    (context,) = contexts
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname


# --- the response ------------------------------------------------------------


def test_non_2xx_is_a_response_with_lowercased_joined_headers_and_raw_bytes(
    script: Callable[..., Script],
) -> None:
    hostile = b"\xff\xfe{not utf-8"
    script(
        raw(
            429,
            hostile,
            headers=(
                ("X-RateLimit-Usage", "5,50"),
                ("Set-Cookie", "a=1"),
                ("Set-Cookie", "b=2"),
            ),
        )
    )
    response = urllib_outbound(req(), 5)
    assert response.status == 429
    assert response.body == hostile
    assert response.headers["x-ratelimit-usage"] == "5,50"
    assert response.headers["set-cookie"] == "a=1, b=2"


def test_a_2xx_response_is_returned_with_status_and_headers(
    script: Callable[..., Script],
) -> None:
    script(raw(201, b"made", headers=(("Content-Type", "application/json"),)))
    response = urllib_outbound(req(method="POST", body=b"x"), 5)
    assert (response.status, response.body) == (201, b"made")
    assert response.headers["content-type"] == "application/json"


def test_a_body_of_exactly_the_cap_is_accepted(script: Callable[..., Script]) -> None:
    script(raw(200, b"a" * MAX_OUTBOUND_RESPONSE_BYTES))
    assert len(urllib_outbound(req(), 5).body) == MAX_OUTBOUND_RESPONSE_BYTES


@pytest.mark.parametrize("status", [200, 404])
def test_a_body_one_byte_over_the_cap_is_refused(
    script: Callable[..., Script], status: int
) -> None:
    reason = "REASON-PLANTED"
    header = ("X-Planted", "HEADER-PLANTED")
    s = script(
        raw(
            status,
            b"a" * (MAX_OUTBOUND_RESPONSE_BYTES + 1),
            headers=(header,),
            reason=reason,
        )
    )
    with pytest.raises(OutboundError) as caught:
        urllib_outbound(
            req(
                url=SECRET_URL,
                secret={"Authorization": SECRET_TOKEN},
                url_is_secret=True,
            ),
            5,
        )
    error = caught.value
    assert error.kind == "too-large"
    assert error.__context__ is None
    assert error.__cause__ is None
    rendered = "".join(traceback.format_exception(error))
    for planted in (SECRET_QUERY, SECRET_TOKEN, "hook.example.test", reason, header[1]):
        assert planted not in rendered
    assert len(s.streams) == 1
    assert s.streams[0].delivered == MAX_OUTBOUND_RESPONSE_BYTES + 1 + _head_length(
        status, reason, header
    )


def _head_length(status: int, reason: str, header: tuple[str, str]) -> int:
    body = b"a" * (MAX_OUTBOUND_RESPONSE_BYTES + 1)
    return len(raw(status, body, headers=(header,), reason=reason)) - len(body)


@pytest.mark.parametrize("status", [200, 404])
def test_the_read_never_pulls_more_than_the_cap_plus_one_byte(
    script: Callable[..., Script], status: int
) -> None:
    oversize = 4096
    s = script(raw(status, b"a" * (MAX_OUTBOUND_RESPONSE_BYTES + oversize)))
    with pytest.raises(OutboundError) as caught:
        urllib_outbound(req(), 5)
    assert caught.value.kind == "too-large"
    (stream,) = s.streams
    # The head is under 64 bytes more than an empty reply's (longer length digits).
    assert stream.delivered <= len(raw(status)) + 64 + MAX_OUTBOUND_RESPONSE_BYTES + 1
    assert stream.delivered > MAX_OUTBOUND_RESPONSE_BYTES


def test_the_cap_is_eight_mebibytes() -> None:
    assert MAX_OUTBOUND_RESPONSE_BYTES == 8388608


# --- failures carry a kind and nothing else ----------------------------------

PLANTED = f"{SECRET_URL} Bearer {SECRET_TOKEN}"


@pytest.mark.parametrize(
    ("raised", "kind"),
    [
        (TimeoutError(PLANTED), "timeout"),
        (urllib.error.URLError(TimeoutError(PLANTED)), "timeout"),
        (urllib.error.URLError(PLANTED), "network"),
        (urllib.error.URLError(ConnectionRefusedError(PLANTED)), "network"),
        (urllib.error.URLError(socket.gaierror(-2, PLANTED)), "network"),
        (socket.gaierror(-2, PLANTED), "network"),
        (ConnectionResetError(PLANTED), "network"),
        (http.client.IncompleteRead(b"x", 5), "network"),
        (http.client.BadStatusLine(PLANTED), "network"),
        (ValueError(PLANTED), "invalid"),
        (http.client.InvalidURL(PLANTED), "invalid"),
    ],
)
def test_failures_raise_a_fixed_kind_free_of_planted_secrets(
    script: Callable[..., Script], raised: BaseException, kind: str
) -> None:
    script(raised)
    with pytest.raises(OutboundError) as caught:
        urllib_outbound(
            req(
                url=SECRET_URL,
                secret={"Authorization": SECRET_TOKEN},
                url_is_secret=True,
            ),
            5,
        )
    error = caught.value
    assert error.kind == kind
    assert str(error) == kind
    assert repr(error) == f"OutboundError({kind!r})"
    rendered = "".join(traceback.format_exception(error))
    for planted in (SECRET_QUERY, SECRET_TOKEN, "hook.example.test"):
        assert planted not in rendered
    assert error.__cause__ is None
    assert error.__context__ is None


def test_a_timeout_during_the_body_read_is_a_timeout(
    script: Callable[..., Script], monkeypatch: pytest.MonkeyPatch
) -> None:
    script(raw(200, b"abc"))

    def slow(self: http.client.HTTPResponse, amt: int | None = None) -> bytes:
        raise TimeoutError(PLANTED)

    monkeypatch.setattr(http.client.HTTPResponse, "read", slow)
    with pytest.raises(OutboundError) as caught:
        urllib_outbound(req(url=SECRET_URL), 5)
    assert caught.value.kind == "timeout"


@pytest.mark.parametrize(
    "bad",
    [
        req(url="http://api.example.test/x"),
        req(url="ftp://api.example.test/x"),
        req(headers={"X-A": "v\r\nInjected: 1"}),
        req(headers={"X-A\nB": "v"}),
        req(headers={"X-A": "v\rInjected"}),
        req(headers={"X-A": "v\0w"}),
        req(headers={"X\0A": "v"}),
        req(secret={"Authorization": f"{SECRET_TOKEN}\0w"}),
        req(headers={"": "v"}),
        req(secret={"Authorization": f"{SECRET_TOKEN}\nInjected: 1"}),
        req(secret={"Bad:Name": "v"}),
        req(headers={"Authorization": "a"}, secret={"authorization": SECRET_TOKEN}),
    ],
)
def test_malformed_requests_are_invalid_and_never_sent(
    script: Callable[..., Script], bad: OutboundRequest
) -> None:
    s = script(raw())
    with pytest.raises(OutboundError) as caught:
        urllib_outbound(bad, 5)
    assert caught.value.kind == "invalid"
    assert SECRET_TOKEN not in str(caught.value)
    assert s.seen == []


@pytest.mark.parametrize("timeout", [0, -1, float("nan")])
def test_a_non_positive_timeout_is_invalid(
    script: Callable[..., Script], timeout: float
) -> None:
    s = script(raw())
    with pytest.raises(OutboundError) as caught:
        urllib_outbound(req(), timeout)
    assert caught.value.kind == "invalid"
    assert s.seen == []


# --- reprs hide secrets ------------------------------------------------------


def test_reprs_hide_secret_headers_bodies_and_secret_addresses() -> None:
    secret_request = req(
        url=SECRET_URL,
        method="POST",
        secret={"Authorization": SECRET_TOKEN},
        body=b"BODY-PLANTED",
        url_is_secret=True,
    )
    text = repr(secret_request)
    for planted in (SECRET_QUERY, SECRET_TOKEN, "BODY-PLANTED", "hook.example.test"):
        assert planted not in text
    assert "POST" in text
    open_request = req(url=URL)
    assert URL in repr(open_request)
    response = OutboundResponse(200, {}, b"BODY-PLANTED")
    assert "BODY-PLANTED" not in repr(response)
