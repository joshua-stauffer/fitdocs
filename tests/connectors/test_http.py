"""Pins for :mod:`fitdocs.connectors.http` (Requirements 9.1-9.8, 10.4)."""

from __future__ import annotations

import email.message
import http.client
import io
import math
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any, Literal

import pytest

from fitdocs.connectors import http as http_module
from fitdocs.connectors.errors import AuthFailureKind
from fitdocs.connectors.http import (
    BACKOFF_SECONDS,
    DEFAULT_TIMEOUT_SECONDS,
    MAX_DATA_ATTEMPTS,
    MAX_RETRY_AFTER_SECONDS,
    CallMode,
    HttpClient,
    HttpRequest,
    HttpResponse,
    TransportError,
    auth_failure_from,
    urllib_transport,
)
from fitdocs.connectors.secrets import REDACTED, Redactor, Secret
from fitdocs.version import user_agent
from tests.connectors.conftest import FakeTransport

SECRET_VALUE = "tok-live-9f8e7d6c5b4a"


def _sleeps() -> tuple[list[float], Any]:
    recorded: list[float] = []

    def sleep(seconds: float) -> None:
        recorded.append(seconds)

    return recorded, sleep


def _client(
    transport: FakeTransport,
    *,
    mode: CallMode,
    redactor: Redactor | None = None,
    timeout: float | None = None,
) -> tuple[HttpClient, list[float]]:
    sleeps, sleep = _sleeps()
    kwargs: dict[str, Any] = {}
    if timeout is not None:
        kwargs["timeout"] = timeout
    client = HttpClient(
        transport, mode=mode, redactor=redactor or Redactor(), sleep=sleep, **kwargs
    )
    return client, sleeps


def _response(status: int, headers: dict[str, str] | None = None) -> HttpResponse:
    return HttpResponse(status=status, headers=headers or {}, body=b"")


# --- User-Agent (Req 9.1) ----------------------------------------------------


def test_user_agent_is_always_the_composed_one_even_when_caller_supplies_another() -> (
    None
):
    transport = FakeTransport([_response(200)])
    client, _ = _client(transport, mode=CallMode.AUTH)

    client.send(
        HttpRequest(
            method="GET",
            url="https://svc.example/x",
            headers={"User-Agent": "caller-agent/1"},
        )
    )

    assert transport.requests[0].headers["User-Agent"] == user_agent()
    assert transport.requests[0].headers["User-Agent"] != "caller-agent/1"


def test_user_agent_override_is_case_insensitive() -> None:
    # A caller might spell the header any case; HttpClient must still
    # recognize and replace it rather than leaving a duplicate under a
    # differently-cased key.
    transport = FakeTransport([_response(200)])
    client, _ = _client(transport, mode=CallMode.AUTH)

    client.send(
        HttpRequest(
            method="GET",
            url="https://svc.example/x",
            headers={"user-agent": "lowercase-caller-agent"},
        )
    )

    sent_headers = transport.requests[0].headers
    assert sent_headers == {"User-Agent": user_agent()}
    assert "lowercase-caller-agent" not in sent_headers.values()


def test_user_agent_delegates_to_version_user_agent_not_a_copied_literal(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pins the *delegation*, not an equality against a fresh call to the
    same :func:`fitdocs.version.user_agent` the module under test imports
    (a self-referential compare that a hand-copied literal in ``http.py``
    would also satisfy today, by coincidence). The underlying
    ``importlib.metadata.version`` lookup is patched to a sentinel that
    differs from the real installed version, and the expected header is
    built here from that sentinel and :data:`PROJECT_URL` independently --
    mirroring ``tests/test_version_identity.py``'s own
    ``test_user_agent_equals_the_literal_format_with_a_patched_version`` and
    ``test_tile_fetcher_delegates_to_the_one_user_agent_definition`` --
    rather than by calling ``user_agent()`` a second time.
    """
    from fitdocs import version as version_module

    monkeypatch.setattr(version_module, "version", lambda name: "9.9.9-http-ua-patched")

    transport = FakeTransport([_response(200)])
    client, _ = _client(transport, mode=CallMode.AUTH)

    client.send(HttpRequest(method="GET", url="https://svc.example/x"))

    expected = (
        "fitdocs/9.9.9-http-ua-patched (+https://github.com/joshua-stauffer/fitdocs)"
    )
    assert transport.requests[0].headers["User-Agent"] == expected


# --- Timeout reaches the transport (Req 9.2) --------------------------------


def test_default_timeout_seconds_literal_is_thirty() -> None:
    # The literal is pinned directly.
    assert DEFAULT_TIMEOUT_SECONDS == 30.0


def test_default_timeout_reaches_the_transport_in_auth_mode() -> None:
    transport = FakeTransport([_response(200)])
    client, _ = _client(transport, mode=CallMode.AUTH)

    client.send(HttpRequest(method="GET", url="https://svc.example/x"))

    assert transport.timeouts == [30.0]


def test_default_timeout_reaches_the_transport_in_data_mode() -> None:
    transport = FakeTransport([_response(200)])
    client, _ = _client(transport, mode=CallMode.DATA)

    client.send(HttpRequest(method="GET", url="https://svc.example/data"))

    assert transport.timeouts == [30.0]


def test_custom_timeout_reaches_every_attempt_in_data_mode() -> None:
    transport = FakeTransport([_response(503), _response(503), _response(200)])
    client, _ = _client(transport, mode=CallMode.DATA, timeout=9.5)

    client.send(HttpRequest(method="GET", url="https://svc.example/data"))

    assert transport.timeouts == [9.5, 9.5, 9.5]


def test_custom_timeout_reaches_the_transport_in_auth_mode() -> None:
    transport = FakeTransport([_response(200)])
    client, _ = _client(transport, mode=CallMode.AUTH, timeout=3.25)

    client.send(HttpRequest(method="GET", url="https://svc.example/x"))

    assert transport.timeouts == [3.25]


# --- AUTH mode: exactly one call, whatever the response (Req 9.4, 9.5) ------


@pytest.mark.parametrize("status", [429, 503])
def test_auth_mode_makes_exactly_one_call_on_a_retryable_status(status: int) -> None:
    transport = FakeTransport([_response(status)])
    client, sleeps = _client(transport, mode=CallMode.AUTH)

    response = client.send(HttpRequest(method="GET", url="https://svc.example/auth"))

    assert len(transport.requests) == 1
    assert response.status == status
    assert sleeps == []


def test_auth_mode_makes_exactly_one_call_and_propagates_a_network_error() -> None:
    transport = FakeTransport(
        [TransportError("network error: https://svc.example/auth")]
    )
    client, sleeps = _client(transport, mode=CallMode.AUTH)

    with pytest.raises(TransportError):
        client.send(HttpRequest(method="GET", url="https://svc.example/auth"))

    assert len(transport.requests) == 1
    assert sleeps == []


def test_auth_mode_still_makes_one_call_when_three_retryable_responses_are_queued() -> (
    None
):
    # Three responses are queued, exactly as DATA mode would consume on
    # persistent 503 (see
    # test_data_mode_makes_three_calls_on_persistent_503_and_sleeps_2_then_4
    # below).
    transport = FakeTransport([_response(503), _response(503), _response(503)])
    client, _ = _client(transport, mode=CallMode.AUTH)

    client.send(HttpRequest(method="GET", url="https://svc.example/auth"))

    assert len(transport.requests) == 1


# --- Single-attempt requests (publish-core Req 10.1, 10.2) -----------------

_SINGLE_OUTCOMES: list[Any] = [
    pytest.param(lambda: _response(429), id="429"),
    pytest.param(lambda: _response(503), id="503"),
    pytest.param(lambda: _response(500), id="500"),
    pytest.param(lambda: _response(502), id="502"),
    pytest.param(lambda: _response(504), id="504"),
    pytest.param(lambda: TransportError("boom: https://svc.example/w"), id="failure"),
]


def _script_for(outcome: Any) -> list[HttpResponse | TransportError]:
    # Three of the same outcome are queued, so a retrying implementation has
    # something to consume; the tests then read the call count and the sleeps.
    return [outcome(), outcome(), outcome()]


def _send_marked(client: HttpClient, outcome: Any, method: Any = "POST") -> None:
    # A GET carries no body and a POST carries one, so the guard cannot get
    # away with keying on either the method or the body.
    request = HttpRequest(
        method=method,
        url="https://svc.example/w",
        body=b"x" if method == "POST" else None,
        single_attempt=True,
    )
    if isinstance(outcome(), TransportError):
        with pytest.raises(TransportError):
            client.send(request)
    else:
        assert client.send(request).status == outcome().status


def test_http_request_is_unmarked_by_default() -> None:
    assert (
        HttpRequest(method="GET", url="https://svc.example/w").single_attempt is False
    )


@pytest.mark.parametrize("method", ["GET", "POST"])
@pytest.mark.parametrize("outcome", _SINGLE_OUTCOMES)
def test_marked_data_request_is_sent_exactly_once(outcome: Any, method: str) -> None:
    transport = FakeTransport(_script_for(outcome))
    client, sleeps = _client(transport, mode=CallMode.DATA)

    _send_marked(client, outcome, method)

    assert len(transport.requests) == 1
    assert sleeps == []


@pytest.mark.parametrize("mode", [CallMode.DATA, CallMode.AUTH])
def test_marked_request_is_prepared_and_secrets_registered_before_the_call(
    mode: CallMode,
) -> None:
    redactor = Redactor()
    signed_url = "https://svc.example/signed?sig=abc123"
    seen: list[tuple[bool, bool, str]] = []

    def checking_transport(request: HttpRequest, timeout: float) -> HttpResponse:
        # Observed from inside the call: registration after the call is too late.
        seen.append(
            (
                redactor.redact(SECRET_VALUE) == REDACTED,
                redactor.redact(signed_url) == REDACTED,
                request.headers["User-Agent"],
            )
        )
        return _response(503)

    sleeps, sleep = _sleeps()
    client = HttpClient(checking_transport, mode=mode, redactor=redactor, sleep=sleep)

    client.send(
        HttpRequest(
            method="POST",
            url=signed_url,
            url_is_secret=True,
            body=b"x",
            headers={"User-Agent": "caller-agent/1"},
            secret_headers={"Authorization": Secret(SECRET_VALUE)},
            single_attempt=True,
        )
    )

    assert user_agent() != "caller-agent/1"
    assert seen == [(True, True, user_agent())]
    assert sleeps == []


@pytest.mark.parametrize("mode", [CallMode.DATA, CallMode.AUTH])
def test_marked_request_uses_the_clients_timeout_and_returns_the_response_as_is(
    mode: CallMode,
) -> None:
    # A retryable status, so a client that wrongly treats this request as
    # unmarked consumes the further queued responses.
    ok = HttpResponse(status=503, headers={"x-k": "v"}, body=b"busy")
    transport = FakeTransport([ok, ok, ok])
    client, _ = _client(transport, mode=mode, timeout=7.5)

    response = client.post("https://svc.example/w", body=b"x", single_attempt=True)

    assert response is ok
    assert transport.timeouts == [7.5]
    assert DEFAULT_TIMEOUT_SECONDS != 7.5


@pytest.mark.parametrize("outcome", _SINGLE_OUTCOMES)
def test_marked_auth_request_is_sent_exactly_once(outcome: Any) -> None:
    transport = FakeTransport(_script_for(outcome))
    client, sleeps = _client(transport, mode=CallMode.AUTH)

    _send_marked(client, outcome)

    assert len(transport.requests) == 1
    assert sleeps == []


@pytest.mark.parametrize("outcome", _SINGLE_OUTCOMES)
def test_the_same_unmarked_data_request_is_sent_three_times(outcome: Any) -> None:
    transport = FakeTransport(_script_for(outcome))
    client, sleeps = _client(transport, mode=CallMode.DATA)
    request = HttpRequest(method="POST", url="https://svc.example/w", body=b"x")

    if isinstance(outcome(), TransportError):
        with pytest.raises(TransportError):
            client.send(request)
    else:
        assert client.send(request).status == outcome().status

    assert len(transport.requests) == 3
    assert sleeps == [2.0, 4.0]


@pytest.mark.parametrize("outcome", _SINGLE_OUTCOMES)
def test_the_same_unmarked_auth_request_is_sent_once(outcome: Any) -> None:
    transport = FakeTransport(_script_for(outcome))
    client, _ = _client(transport, mode=CallMode.AUTH)
    request = HttpRequest(method="POST", url="https://svc.example/w", body=b"x")

    if isinstance(outcome(), TransportError):
        with pytest.raises(TransportError):
            client.send(request)
    else:
        assert client.send(request).status == outcome().status

    assert len(transport.requests) == 1


@pytest.mark.parametrize("mode", [CallMode.DATA, CallMode.AUTH])
def test_post_marks_the_request_single_attempt_when_asked(mode: CallMode) -> None:
    transport = FakeTransport([_response(503), _response(503), _response(503)])
    client, _ = _client(transport, mode=mode)

    client.post("https://svc.example/w", body=b"x", single_attempt=True)

    assert len(transport.requests) == 1
    assert transport.requests[0].single_attempt is True


def test_post_is_unmarked_by_default_and_retries_in_data_mode() -> None:
    transport = FakeTransport([_response(503), _response(503), _response(503)])
    client, _ = _client(transport, mode=CallMode.DATA)

    client.post("https://svc.example/w", body=b"x")

    assert len(transport.requests) == 3
    assert all(r.single_attempt is False for r in transport.requests)


# --- the update method (intervals-publish Req 5.5) ---------------------------


def test_put_reaches_the_transport_with_its_method_body_and_secret_headers() -> None:
    transport = FakeTransport([_response(200)])
    client, _ = _client(transport, mode=CallMode.DATA)

    response = client.put(
        "https://svc.example/w/1",
        body=b'{"name": "x"}',
        headers={"Content-Type": "application/json"},
        secret_headers={"Authorization": Secret(SECRET_VALUE)},
    )

    assert response.status == 200
    assert len(transport.requests) == 1
    sent = transport.requests[0]
    assert sent.method == "PUT"
    assert sent.url == "https://svc.example/w/1"
    assert sent.body == b'{"name": "x"}'
    assert sent.headers["Content-Type"] == "application/json"
    assert sent.secret_headers["Authorization"].reveal() == SECRET_VALUE
    assert sent.single_attempt is False


def test_unmarked_put_in_data_mode_is_retried_like_any_data_request() -> None:
    transport = FakeTransport([_response(503), _response(503), _response(200)])
    client, sleeps = _client(transport, mode=CallMode.DATA)

    response = client.put("https://svc.example/w/1", body=b"x")

    assert response.status == 200
    assert [r.method for r in transport.requests] == ["PUT", "PUT", "PUT"]
    assert sleeps == [2.0, 4.0]


def test_marked_put_is_sent_once_even_when_the_answer_is_retryable() -> None:
    transport = FakeTransport([_response(503), _response(503), _response(200)])
    client, sleeps = _client(transport, mode=CallMode.DATA)

    response = client.put("https://svc.example/w/1", body=b"x", single_attempt=True)

    assert response.status == 503
    assert len(transport.requests) == 1
    assert transport.requests[0].method == "PUT"
    assert transport.requests[0].single_attempt is True
    assert sleeps == []


# --- DATA mode: bounded retries (Req 9.3) -----------------------------------


def test_data_mode_makes_three_calls_on_persistent_503_and_sleeps_2_then_4() -> None:
    transport = FakeTransport([_response(503), _response(503), _response(503)])
    client, sleeps = _client(transport, mode=CallMode.DATA)

    response = client.send(HttpRequest(method="GET", url="https://svc.example/data"))

    assert len(transport.requests) == MAX_DATA_ATTEMPTS == 3
    assert sleeps == [2.0, 4.0]
    assert response.status == 503


@pytest.mark.parametrize("status", [500, 502, 504])
def test_data_mode_retries_every_retryable_status_not_just_503(status: int) -> None:
    transport = FakeTransport([_response(status), _response(200)])
    client, sleeps = _client(transport, mode=CallMode.DATA)

    response = client.send(HttpRequest(method="GET", url="https://svc.example/data"))

    assert len(transport.requests) == 2
    assert sleeps == [2.0]
    assert response.status == 200


def test_data_mode_succeeds_after_one_retryable_failure() -> None:
    transport = FakeTransport([_response(503), _response(200)])
    client, sleeps = _client(transport, mode=CallMode.DATA)

    response = client.send(HttpRequest(method="GET", url="https://svc.example/data"))

    assert len(transport.requests) == 2
    assert sleeps == [2.0]
    assert response.status == 200


def test_data_mode_retries_a_network_error_then_returns_the_eventual_response() -> None:
    transport = FakeTransport(
        [TransportError("boom: https://svc.example/data"), _response(200)]
    )
    client, sleeps = _client(transport, mode=CallMode.DATA)

    response = client.send(HttpRequest(method="GET", url="https://svc.example/data"))

    assert len(transport.requests) == 2
    assert sleeps == [2.0]
    assert response.status == 200


def test_data_mode_propagates_the_final_transport_error_after_exhausting_attempts() -> (
    None
):
    transport = FakeTransport(
        [
            TransportError("boom1: https://svc.example/data"),
            TransportError("boom2: https://svc.example/data"),
            TransportError("boom3: https://svc.example/data"),
        ]
    )
    client, sleeps = _client(transport, mode=CallMode.DATA)

    with pytest.raises(TransportError, match="boom3"):
        client.send(HttpRequest(method="GET", url="https://svc.example/data"))

    assert len(transport.requests) == 3
    assert sleeps == [2.0, 4.0]


# --- DATA mode: opting out of 429 retries (garmin-connector Req 4.7) ---------

_RATE_URL = "https://svc.example/data"


def test_retry_rate_limits_defaults_to_true_on_the_request_and_the_get_helper() -> None:
    import dataclasses
    import inspect

    request_default = {f.name: f.default for f in dataclasses.fields(HttpRequest)}
    get_default = inspect.signature(HttpClient.get).parameters["retry_rate_limits"]

    assert request_default["retry_rate_limits"] is True
    assert get_default.default is True
    assert get_default.kind is inspect.Parameter.KEYWORD_ONLY


@pytest.mark.parametrize("retry_after", [None, "7"])
def test_get_with_retry_rate_limits_off_returns_a_429_after_one_attempt(
    retry_after: str | None,
) -> None:
    headers = {} if retry_after is None else {"retry-after": retry_after}
    # A second scripted outcome makes a wrongly issued retry observable as a
    # second request instead of an exhausted-script error.
    transport = FakeTransport([_response(429, headers), _response(200)])
    client, sleeps = _client(transport, mode=CallMode.DATA)

    response = client.get(_RATE_URL, retry_rate_limits=False)

    assert response.status == 429
    assert len(transport.requests) == 1
    assert sleeps == []


def test_get_carries_the_option_into_the_request_the_transport_receives() -> None:
    off_transport = FakeTransport([_response(200)])
    off_client, _ = _client(off_transport, mode=CallMode.DATA)
    on_transport = FakeTransport([_response(200)])
    on_client, _ = _client(on_transport, mode=CallMode.DATA)

    off_client.get(_RATE_URL, retry_rate_limits=False)
    on_client.get(_RATE_URL)

    assert off_transport.requests[0].retry_rate_limits is False
    assert on_transport.requests[0].retry_rate_limits is True


@pytest.mark.parametrize("status", [500, 502, 503, 504])
def test_get_with_retry_rate_limits_off_still_retries_a_5xx_with_the_same_waits(
    status: int,
) -> None:
    transport = FakeTransport([_response(status)] * 3)
    client, sleeps = _client(transport, mode=CallMode.DATA)

    response = client.get(_RATE_URL, retry_rate_limits=False)

    assert response.status == status
    assert len(transport.requests) == MAX_DATA_ATTEMPTS
    assert sleeps == [2.0, 4.0]


def test_get_with_retry_rate_limits_off_recovers_from_a_503_then_a_200() -> None:
    transport = FakeTransport([_response(503), _response(200)])
    client, sleeps = _client(transport, mode=CallMode.DATA)

    response = client.get(_RATE_URL, retry_rate_limits=False)

    assert response.status == 200
    assert len(transport.requests) == 2
    assert sleeps == [2.0]


def test_get_with_retry_rate_limits_off_returns_the_429_with_its_headers_and_body() -> (
    None
):
    stated = HttpResponse(status=429, headers={"retry-after": "7"}, body=b"slow down")
    transport = FakeTransport([stated, _response(200)])
    client, sleeps = _client(transport, mode=CallMode.DATA)

    response = client.get(_RATE_URL, retry_rate_limits=False)

    assert response.status == 429
    assert response.headers == {"retry-after": "7"}
    assert response.body == b"slow down"
    assert len(transport.requests) == 1
    assert sleeps == []


def test_get_with_retry_rate_limits_off_honors_a_503_retry_after() -> None:
    transport = FakeTransport([_response(503, {"retry-after": "7"}), _response(200)])
    client, sleeps = _client(transport, mode=CallMode.DATA)

    response = client.get(_RATE_URL, retry_rate_limits=False)

    assert response.status == 200
    assert len(transport.requests) == 2
    assert sleeps == [7.0]


def test_get_with_retry_rate_limits_off_returns_a_503_with_retry_after_over_cap() -> (
    None
):
    over_cap = str(int(http_module.MAX_RETRY_AFTER_SECONDS) + 60)
    stated = _response(503, {"retry-after": over_cap})
    transport = FakeTransport([stated, _response(200)])
    client, sleeps = _client(transport, mode=CallMode.DATA)

    response = client.get(_RATE_URL, retry_rate_limits=False)

    assert response.status == 503
    assert response.headers == {"retry-after": over_cap}
    assert len(transport.requests) == 1
    assert sleeps == []


@pytest.mark.parametrize("method", ["GET", "POST", "PUT"])
def test_send_with_retry_rate_limits_off_returns_a_429_for_every_method(
    method: Literal["GET", "POST", "PUT"],
) -> None:
    transport = FakeTransport([_response(429), _response(200)])
    client, sleeps = _client(transport, mode=CallMode.DATA)

    response = client.send(
        HttpRequest(method=method, url=_RATE_URL, retry_rate_limits=False)
    )

    assert response.status == 429
    assert len(transport.requests) == 1
    assert sleeps == []


def test_get_with_retry_rate_limits_off_returns_a_429_with_secrets_set() -> None:
    transport = FakeTransport([_response(429), _response(200)])
    client, sleeps = _client(transport, mode=CallMode.DATA)

    response = client.get(
        _RATE_URL,
        headers={"a": "b"},
        secret_headers={"Authorization": Secret("k")},
        url_is_secret=True,
        retry_rate_limits=False,
    )

    assert response.status == 429
    assert len(transport.requests) == 1
    assert sleeps == []


def test_get_with_retry_rate_limits_off_still_retries_a_network_error() -> None:
    transport = FakeTransport(
        [
            TransportError("boom1: https://svc.example/data"),
            TransportError("boom2: https://svc.example/data"),
            TransportError("boom3: https://svc.example/data"),
        ]
    )
    client, sleeps = _client(transport, mode=CallMode.DATA)

    with pytest.raises(TransportError, match="boom3"):
        client.get(_RATE_URL, retry_rate_limits=False)

    assert len(transport.requests) == MAX_DATA_ATTEMPTS
    assert sleeps == [2.0, 4.0]


@pytest.mark.parametrize(
    "first",
    [_response(503), TransportError("boom1: https://svc.example/data")],
    ids=["503", "network-error"],
)
def test_get_with_retry_rate_limits_off_returns_a_429_met_on_a_later_attempt(
    first: HttpResponse | TransportError,
) -> None:
    transport = FakeTransport([first, _response(429), _response(200)])
    client, sleeps = _client(transport, mode=CallMode.DATA)

    response = client.get(_RATE_URL, retry_rate_limits=False)

    assert response.status == 429
    assert len(transport.requests) == 2
    assert sleeps == [2.0]


_ONE_ATTEMPT_FIRST = [
    pytest.param(_response(429), id="429"),
    pytest.param(_response(503), id="503"),
    pytest.param(TransportError("boom: https://svc.example/data"), id="network-error"),
]


def _assert_one_attempt(
    transport: FakeTransport,
    sleeps: list[float],
    call: Callable[[HttpClient], HttpResponse],
    client: HttpClient,
    first: HttpResponse | TransportError,
) -> None:
    if isinstance(first, TransportError):
        with pytest.raises(TransportError, match="boom"):
            call(client)
    else:
        assert call(client).status == first.status
    assert len(transport.requests) == 1
    assert sleeps == []


@pytest.mark.parametrize("first", _ONE_ATTEMPT_FIRST)
def test_auth_mode_get_with_retry_rate_limits_off_makes_one_attempt(
    first: HttpResponse | TransportError,
) -> None:
    transport = FakeTransport([first, _response(200)])
    client, sleeps = _client(transport, mode=CallMode.AUTH)

    _assert_one_attempt(
        transport,
        sleeps,
        lambda c: c.get(_RATE_URL, retry_rate_limits=False),
        client,
        first,
    )


@pytest.mark.parametrize("first", _ONE_ATTEMPT_FIRST)
def test_single_attempt_post_with_retry_rate_limits_off_makes_one_attempt(
    first: HttpResponse | TransportError,
) -> None:
    transport = FakeTransport([first, _response(200)])
    client, sleeps = _client(transport, mode=CallMode.DATA)

    _assert_one_attempt(
        transport,
        sleeps,
        lambda c: c.send(
            HttpRequest(
                method="POST",
                url=_RATE_URL,
                single_attempt=True,
                retry_rate_limits=False,
            )
        ),
        client,
        first,
    )


def test_get_by_default_retries_a_429_on_the_unchanged_sequence() -> None:
    transport = FakeTransport([_response(429), _response(429), _response(429)])
    client, sleeps = _client(transport, mode=CallMode.DATA)

    response = client.get(_RATE_URL)

    assert response.status == 429
    assert len(transport.requests) == MAX_DATA_ATTEMPTS
    assert sleeps == [2.0, 4.0]


def test_get_by_default_honors_a_429_retry_after_then_returns_the_next_response() -> (
    None
):
    transport = FakeTransport([_response(429, {"retry-after": "7"}), _response(200)])
    client, sleeps = _client(transport, mode=CallMode.DATA)

    response = client.get(_RATE_URL)

    assert response.status == 200
    assert len(transport.requests) == 2
    assert sleeps == [7.0]


def test_data_mode_429_with_no_retry_after_uses_backoff() -> None:
    transport = FakeTransport([_response(429), _response(200)])
    client, sleeps = _client(transport, mode=CallMode.DATA)

    client.send(HttpRequest(method="GET", url="https://svc.example/data"))

    assert sleeps == [2.0]


def test_retry_after_seven_seconds_sleeps_seven() -> None:
    transport = FakeTransport([_response(429, {"retry-after": "7"}), _response(200)])
    client, sleeps = _client(transport, mode=CallMode.DATA)

    client.send(HttpRequest(method="GET", url="https://svc.example/data"))

    assert sleeps == [7.0]


def test_retry_after_beyond_the_maximum_returns_after_one_call() -> None:
    transport = FakeTransport([_response(429, {"retry-after": "120"})])
    client, sleeps = _client(transport, mode=CallMode.DATA)

    response = client.send(HttpRequest(method="GET", url="https://svc.example/data"))

    assert len(transport.requests) == 1
    assert sleeps == []
    assert response.status == 429


def test_retry_after_exactly_at_the_maximum_is_honored_not_stopped() -> None:
    # The boundary itself: design.md says "when present and <= MAX" is
    # honored, and only a wait *above* the maximum stops retrying. A `>=`
    # mutation on that comparison would treat exactly-at-max as "stop" too,
    # which this fixture -- sitting precisely on MAX_RETRY_AFTER_SECONDS,
    # not comfortably under or over it -- is built to catch.
    transport = FakeTransport(
        [
            _response(429, {"retry-after": str(MAX_RETRY_AFTER_SECONDS)}),
            _response(200),
        ]
    )
    client, sleeps = _client(transport, mode=CallMode.DATA)

    response = client.send(HttpRequest(method="GET", url="https://svc.example/data"))

    assert len(transport.requests) == 2
    assert sleeps == [MAX_RETRY_AFTER_SECONDS]
    assert response.status == 200


def test_retry_after_non_numeric_non_date_falls_back_to_backoff() -> None:
    transport = FakeTransport(
        [_response(429, {"retry-after": "not-a-number-or-date"}), _response(200)]
    )
    client, sleeps = _client(transport, mode=CallMode.DATA)

    client.send(HttpRequest(method="GET", url="https://svc.example/data"))

    # Falls through to BACKOFF_SECONDS[0], exactly as an absent header would.
    assert sleeps == [BACKOFF_SECONDS[0]]


def test_retry_after_negative_number_clamps_to_zero() -> None:
    transport = FakeTransport([_response(429, {"retry-after": "-5"}), _response(200)])
    client, sleeps = _client(transport, mode=CallMode.DATA)

    client.send(HttpRequest(method="GET", url="https://svc.example/data"))

    assert sleeps == [0.0]


def test_retry_after_nan_is_treated_as_unparseable() -> None:
    transport = FakeTransport([_response(429, {"retry-after": "nan"}), _response(200)])
    client, sleeps = _client(transport, mode=CallMode.DATA)

    client.send(HttpRequest(method="GET", url="https://svc.example/data"))

    # Falls back to backoff, not to a NaN sleep. (A NaN reaching the real
    # ``time.sleep`` would raise ``ValueError`` immediately -- loudly, not
    # silently -- but a NaN reaching *this* fake sleep would sit unnoticed
    # in ``sleeps`` unless checked explicitly, which is what the second
    # assertion below does.)
    assert sleeps == [BACKOFF_SECONDS[0]]
    assert not any(math.isnan(s) for s in sleeps)


# --- Retry-After HTTP-date is measured against the response's own Date
# header, never the system clock (controller ruling, finding 1) ------------


def test_retry_after_http_date_is_measured_against_the_response_date_header() -> None:
    # Both headers are fixed literals with no dependency on wall-clock time
    # at all: this test is clock-free by construction, not merely
    # clock-tolerant. Date and Retry-After sit exactly 7 seconds apart.
    date_header = "Mon, 01 Jan 2024 00:00:00 GMT"
    retry_after_header = "Mon, 01 Jan 2024 00:00:07 GMT"
    transport = FakeTransport(
        [
            _response(429, {"date": date_header, "retry-after": retry_after_header}),
            _response(200),
        ]
    )
    client, sleeps = _client(transport, mode=CallMode.DATA)

    client.send(HttpRequest(method="GET", url="https://svc.example/data"))

    assert sleeps == [7.0]


def test_retry_after_http_date_without_a_date_header_falls_back_to_backoff() -> None:
    # No `date` header at all: per the controller's ruling, an HTTP-date
    # Retry-After with no reference clock is unparseable, not a silent
    # zero or a real-clock read.
    retry_after_header = "Mon, 01 Jan 2024 00:00:07 GMT"
    transport = FakeTransport(
        [_response(429, {"retry-after": retry_after_header}), _response(200)]
    )
    client, sleeps = _client(transport, mode=CallMode.DATA)

    client.send(HttpRequest(method="GET", url="https://svc.example/data"))

    assert sleeps == [BACKOFF_SECONDS[0]]


def test_retry_after_http_date_with_unparseable_date_header_falls_back_to_backoff() -> (
    None
):
    retry_after_header = "Mon, 01 Jan 2024 00:00:07 GMT"
    transport = FakeTransport(
        [
            _response(
                429,
                {"date": "not-a-date-either", "retry-after": retry_after_header},
            ),
            _response(200),
        ]
    )
    client, sleeps = _client(transport, mode=CallMode.DATA)

    client.send(HttpRequest(method="GET", url="https://svc.example/data"))

    assert sleeps == [BACKOFF_SECONDS[0]]


def test_retry_after_http_date_earlier_than_date_header_clamps_to_zero() -> None:
    # Retry-After sits *before* Date -- a negative delta. The clamp
    # (max(delta, 0.0)) must produce 0.0, not the delta's absolute value: an
    # `abs()` mutation would sleep 7.0 here instead of 0.0, since the two
    # headers are exactly 7 seconds apart in this fixture.
    date_header = "Mon, 01 Jan 2024 00:00:10 GMT"
    retry_after_header = "Mon, 01 Jan 2024 00:00:03 GMT"
    transport = FakeTransport(
        [
            _response(429, {"date": date_header, "retry-after": retry_after_header}),
            _response(200),
        ]
    )
    client, sleeps = _client(transport, mode=CallMode.DATA)

    client.send(HttpRequest(method="GET", url="https://svc.example/data"))

    assert sleeps == [0.0]


def test_retry_after_infinite_is_treated_as_unparseable_in_data_mode() -> None:
    transport = FakeTransport([_response(429, {"retry-after": "inf"}), _response(200)])
    client, sleeps = _client(transport, mode=CallMode.DATA)

    client.send(HttpRequest(method="GET", url="https://svc.example/data"))

    assert sleeps == [BACKOFF_SECONDS[0]]


def test_retry_after_negative_infinite_is_treated_as_unparseable_in_data_mode() -> None:
    transport = FakeTransport([_response(429, {"retry-after": "-inf"}), _response(200)])
    client, sleeps = _client(transport, mode=CallMode.DATA)

    client.send(HttpRequest(method="GET", url="https://svc.example/data"))

    assert sleeps == [BACKOFF_SECONDS[0]]


@pytest.mark.parametrize("status", [401, 403])
def test_401_and_403_are_never_retried_in_data_mode(status: int) -> None:
    transport = FakeTransport([_response(status), _response(200)])
    client, sleeps = _client(transport, mode=CallMode.DATA)

    response = client.send(HttpRequest(method="GET", url="https://svc.example/data"))

    assert len(transport.requests) == 1
    assert sleeps == []
    assert response.status == status


def test_a_non_retryable_4xx_status_is_not_retried() -> None:
    # 400 is neither in RETRYABLE_STATUSES nor 401/403 -- a distinct case
    # from both, since a mutation that merely special-cased 401/403 would
    # still retry this one.
    transport = FakeTransport([_response(400), _response(200)])
    client, sleeps = _client(transport, mode=CallMode.DATA)

    response = client.send(HttpRequest(method="GET", url="https://svc.example/data"))

    assert len(transport.requests) == 1
    assert sleeps == []
    assert response.status == 400


# --- Secrets registered before the first call (Req 10.1-10.4) --------------


def test_secret_header_is_registered_with_the_redactor_before_the_first_call() -> None:
    redactor = Redactor()
    transport = FakeTransport([TransportError(f"boom: leaked {SECRET_VALUE} in body")])
    client, _ = _client(transport, mode=CallMode.AUTH, redactor=redactor)

    with pytest.raises(TransportError):
        client.send(
            HttpRequest(
                method="GET",
                url="https://svc.example/auth",
                secret_headers={"Authorization": Secret(SECRET_VALUE)},
            )
        )

    assert redactor.redact(f"leaked {SECRET_VALUE} here") == f"leaked {REDACTED} here"


def test_secret_url_is_registered_with_the_redactor_before_the_first_call() -> None:
    redactor = Redactor()
    signed_url = "https://cdn.example/dl?sig=abc123secretsig"
    transport = FakeTransport([TransportError(f"boom: {signed_url}")])
    client, _ = _client(transport, mode=CallMode.AUTH, redactor=redactor)

    with pytest.raises(TransportError):
        client.send(HttpRequest(method="GET", url=signed_url, url_is_secret=True))

    assert redactor.redact(f"see {signed_url} again") == f"see {REDACTED} again"


def test_secret_is_registered_before_the_transport_is_ever_invoked() -> None:
    """A stronger pin than the two above: this checks the redactor's state
    *from inside* the transport call itself, so a mutation that defers
    registration to a ``finally`` block around the call (rather than doing
    it strictly before) is caught even though the transport call below
    succeeds and never raises.

    A ``finally``-deferred registration would run *after* the transport
    call returns but *before* the outer ``except``/assertion in the two
    tests above ever gets a chance to observe the redactor -- so those two
    fixtures alone cannot tell "before" from "after, but still before the
    caller sees the result". Checking from inside the transport call closes
    that gap: at the moment this callable executes, deferred registration
    genuinely has not happened yet.
    """
    redactor = Redactor()
    checked: list[bool] = []

    def checking_transport(request: HttpRequest, timeout: float) -> HttpResponse:
        checked.append(redactor.redact(SECRET_VALUE) == REDACTED)
        return _response(200)

    client = HttpClient(
        checking_transport, mode=CallMode.AUTH, redactor=redactor, sleep=lambda s: None
    )

    client.send(
        HttpRequest(
            method="GET",
            url="https://svc.example/auth",
            secret_headers={"Authorization": Secret(SECRET_VALUE)},
        )
    )

    assert checked == [True]


# --- urllib_transport: the Request object (Req 9.1, 9.2, 9.6) ---------------


class _FakeUrlResponse:
    def __init__(self, status: int, headers: dict[str, str], body: bytes) -> None:
        self.status = status
        self.headers = headers
        self._body = body
        self.read_sizes: list[int] = []

    def __enter__(self) -> _FakeUrlResponse:
        return self

    def __exit__(self, *exc_info: object) -> None:
        return None

    def read(self, size: int = -1) -> bytes:
        self.read_sizes.append(size)
        if size < 0:
            chunk, self._body = self._body, b""
        else:
            chunk, self._body = self._body[:size], self._body[size:]
        return chunk


def test_urllib_transport_sends_composed_agent_and_the_given_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_urlopen(
        request: urllib.request.Request, timeout: float
    ) -> _FakeUrlResponse:
        captured["request"] = request
        captured["timeout"] = timeout
        return _FakeUrlResponse(200, {}, b"ok")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    request = HttpRequest(
        method="GET",
        url="https://svc.example/path",
        headers={"User-Agent": user_agent()},
    )
    response = urllib_transport(request, 12.5)

    sent: urllib.request.Request = captured["request"]
    assert sent.get_header("User-agent") == user_agent()
    assert captured["timeout"] == 12.5
    assert response.status == 200
    assert response.body == b"ok"


def test_urllib_transport_sends_the_user_agent_as_an_ordinary_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The opposite check from the secret-header test below: the composed
    # User-Agent must be an *ordinary* header, reaching every redirect
    # target, not an unredirected one (which would silently drop it after
    # the first hop).
    captured: dict[str, Any] = {}

    def fake_urlopen(
        request: urllib.request.Request, timeout: float
    ) -> _FakeUrlResponse:
        captured["request"] = request
        return _FakeUrlResponse(200, {}, b"")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    request = HttpRequest(
        method="GET",
        url="https://svc.example/path",
        headers={"User-Agent": "fitdocs-test-agent/1"},
    )
    urllib_transport(request, 5.0)

    sent: urllib.request.Request = captured["request"]
    assert sent.get_header("User-agent") == "fitdocs-test-agent/1"
    assert "User-agent" not in sent.unredirected_hdrs


def test_urllib_transport_sends_the_secret_header_only_unredirected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_urlopen(
        request: urllib.request.Request, timeout: float
    ) -> _FakeUrlResponse:
        captured["request"] = request
        return _FakeUrlResponse(200, {}, b"")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    request = HttpRequest(
        method="GET",
        url="https://svc.example/path",
        secret_headers={"Authorization": Secret(SECRET_VALUE)},
    )
    urllib_transport(request, 5.0)

    sent: urllib.request.Request = captured["request"]
    # unredirected_hdrs carries the credential; ordinary headers do not
    # (mutation: `add_header` instead of `add_unredirected_header`).
    assert sent.unredirected_hdrs.get("Authorization") == SECRET_VALUE
    assert "Authorization" not in sent.headers


def test_urllib_transport_sends_the_method_it_is_given_for_an_update(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    def fake_urlopen(
        request: urllib.request.Request, timeout: float
    ) -> _FakeUrlResponse:
        captured["request"] = request
        return _FakeUrlResponse(200, {}, b"")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    request = HttpRequest(method="PUT", url="https://svc.example/path", body=b"payload")
    urllib_transport(request, 5.0)

    sent: urllib.request.Request = captured["request"]
    assert sent.get_method() == "PUT"
    assert sent.data == b"payload"


def test_urllib_transport_converts_httperror_into_a_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_urlopen(
        request: urllib.request.Request, timeout: float
    ) -> _FakeUrlResponse:
        headers = email.message.Message()
        headers["Retry-After"] = "5"
        raise urllib.error.HTTPError(
            request.full_url, 503, "Service Unavailable", headers, io.BytesIO(b"")
        )

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    request = HttpRequest(method="GET", url="https://svc.example/path")
    response = urllib_transport(request, 5.0)

    assert response.status == 503
    assert response.headers.get("retry-after") == "5"


def test_urllib_transport_lowercases_success_path_headers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_urlopen(
        request: urllib.request.Request, timeout: float
    ) -> _FakeUrlResponse:
        return _FakeUrlResponse(200, {"Retry-After": "5", "X-Custom": "v"}, b"")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    request = HttpRequest(method="GET", url="https://svc.example/path")
    response = urllib_transport(request, 5.0)

    # Header names lowercased on the success path too, not only on the
    # HTTPError-converted path (which a separate code branch handles).
    assert "Retry-After" not in response.headers
    assert response.headers.get("retry-after") == "5"
    assert response.headers.get("x-custom") == "v"


class _SpyBody:
    """A minimal file-like body that records the ``size`` argument every
    ``read`` call was given, so a mutation that reads unbounded
    (``.read()`` with no size, or a size that isn't ``MAX_RESPONSE_BYTES +
    1``) is directly observable rather than inferred from behavior."""

    def __init__(self, body: bytes) -> None:
        self._body = body
        self.read_sizes: list[int] = []

    def read(self, size: int = -1) -> bytes:
        self.read_sizes.append(size)
        return self._body[:size] if size >= 0 else self._body

    def close(self) -> None:
        pass


def test_urllib_transport_reads_capped_size_on_the_success_branch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(http_module, "MAX_RESPONSE_BYTES", 10)
    fake_response = _FakeUrlResponse(200, {}, b"x" * 5)

    def fake_urlopen(
        request: urllib.request.Request, timeout: float
    ) -> _FakeUrlResponse:
        return fake_response

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    urllib_transport(HttpRequest(method="GET", url="https://svc.example/path"), 5.0)

    assert fake_response.read_sizes == [11]


def test_urllib_transport_reads_capped_size_on_the_httperror_branch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(http_module, "MAX_RESPONSE_BYTES", 10)
    spy_body = _SpyBody(b"x" * 5)

    def fake_urlopen(
        request: urllib.request.Request, timeout: float
    ) -> _FakeUrlResponse:
        raise urllib.error.HTTPError(
            request.full_url,
            503,
            "Service Unavailable",
            email.message.Message(),
            spy_body,  # type: ignore[arg-type]
        )

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    urllib_transport(HttpRequest(method="GET", url="https://svc.example/path"), 5.0)

    assert spy_body.read_sizes == [11]


def test_urllib_transport_raises_when_an_httperror_body_exceeds_the_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(http_module, "MAX_RESPONSE_BYTES", 10)

    def fake_urlopen(
        request: urllib.request.Request, timeout: float
    ) -> _FakeUrlResponse:
        raise urllib.error.HTTPError(
            request.full_url,
            503,
            "Service Unavailable",
            email.message.Message(),
            io.BytesIO(b"x" * 11),
        )

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    request = HttpRequest(method="GET", url="https://svc.example/path")
    with pytest.raises(TransportError, match="too large"):
        urllib_transport(request, 5.0)


def test_urllib_transport_raises_transport_error_on_network_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_urlopen(
        request: urllib.request.Request, timeout: float
    ) -> _FakeUrlResponse:
        raise urllib.error.URLError("nodename nor servname provided")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    request = HttpRequest(
        method="GET", url="https://svc.example/path?token=leak-me&x=1"
    )
    with pytest.raises(TransportError) as excinfo:
        urllib_transport(request, 5.0)

    message = str(excinfo.value)
    assert "svc.example/path" in message
    assert "token=leak-me" not in message
    assert "?" not in message


def test_urllib_transport_masks_a_secret_url_in_the_failure_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_urlopen(
        request: urllib.request.Request, timeout: float
    ) -> _FakeUrlResponse:
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    signed_url = "https://cdn.example/dl?sig=abc123secretsig"
    request = HttpRequest(method="GET", url=signed_url, url_is_secret=True)
    with pytest.raises(TransportError) as excinfo:
        urllib_transport(request, 5.0)

    message = str(excinfo.value)
    assert "cdn.example" not in message
    assert "sig=abc123secretsig" not in message
    assert "<signed location>" in message


def test_urllib_transport_raises_transport_error_on_a_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_urlopen(
        request: urllib.request.Request, timeout: float
    ) -> _FakeUrlResponse:
        raise TimeoutError("timed out")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    request = HttpRequest(method="GET", url="https://svc.example/path")
    with pytest.raises(TransportError):
        urllib_transport(request, 5.0)


def test_urllib_transport_timeout_message_names_host_and_path_not_query_or_signed_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_urlopen(
        request: urllib.request.Request, timeout: float
    ) -> _FakeUrlResponse:
        raise TimeoutError("timed out")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    request = HttpRequest(
        method="GET", url="https://svc.example/path?token=leak-me&x=1"
    )
    with pytest.raises(TransportError) as excinfo:
        urllib_transport(request, 5.0)

    message = str(excinfo.value)
    assert "svc.example/path" in message
    assert "token=leak-me" not in message
    assert "?" not in message


def test_urllib_transport_timeout_masks_a_secret_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_urlopen(
        request: urllib.request.Request, timeout: float
    ) -> _FakeUrlResponse:
        raise TimeoutError("timed out")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    signed_url = "https://cdn.example/dl?sig=abc123secretsig"
    request = HttpRequest(method="GET", url=signed_url, url_is_secret=True)
    with pytest.raises(TransportError) as excinfo:
        urllib_transport(request, 5.0)

    message = str(excinfo.value)
    assert "cdn.example" not in message
    assert "sig=abc123secretsig" not in message
    assert "<signed location>" in message


def test_urllib_transport_converts_bad_url_value_error_into_transport_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_urlopen(
        request: urllib.request.Request, timeout: float
    ) -> _FakeUrlResponse:
        raise ValueError("unknown url type: 'ftp'")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    request = HttpRequest(method="GET", url="https://svc.example/path?token=leak-me")
    with pytest.raises(TransportError) as excinfo:
        urllib_transport(request, 5.0)

    message = str(excinfo.value)
    assert "svc.example/path" in message
    assert "token=leak-me" not in message


def test_urllib_transport_converts_a_value_error_from_request_construction_itself(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Distinct from the test above: this fails inside
    ``urllib.request.Request(...)`` itself, before ``urlopen`` is ever
    reached, so it only passes if ``Request`` construction sits *inside*
    the ``try`` block -- pinning the follow-up brought into this task's
    scope (build the ``Request`` inside the ``try``), not merely the
    existing ``urlopen``-side ValueError handling above.
    """

    def raising_request(*args: object, **kwargs: object) -> urllib.request.Request:
        raise ValueError("bad request construction")

    monkeypatch.setattr(urllib.request, "Request", raising_request)

    request = HttpRequest(method="GET", url="https://svc.example/path?token=leak-me")
    with pytest.raises(TransportError) as excinfo:
        urllib_transport(request, 5.0)

    message = str(excinfo.value)
    assert "svc.example/path" in message
    assert "token=leak-me" not in message


def test_urllib_transport_converts_http_client_exception_into_transport_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_urlopen(
        request: urllib.request.Request, timeout: float
    ) -> _FakeUrlResponse:
        raise http.client.BadStatusLine("garbage status line")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    request = HttpRequest(method="GET", url="https://svc.example/path?token=leak-me")
    with pytest.raises(TransportError) as excinfo:
        urllib_transport(request, 5.0)

    message = str(excinfo.value)
    assert "svc.example/path" in message
    assert "token=leak-me" not in message


def test_urllib_transport_raises_when_the_body_exceeds_the_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(http_module, "MAX_RESPONSE_BYTES", 10)

    def fake_urlopen(
        request: urllib.request.Request, timeout: float
    ) -> _FakeUrlResponse:
        return _FakeUrlResponse(200, {}, b"x" * 11)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    request = HttpRequest(method="GET", url="https://svc.example/path")
    with pytest.raises(TransportError, match="too large"):
        urllib_transport(request, 5.0)


def test_urllib_transport_accepts_a_body_exactly_at_the_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(http_module, "MAX_RESPONSE_BYTES", 10)

    def fake_urlopen(
        request: urllib.request.Request, timeout: float
    ) -> _FakeUrlResponse:
        return _FakeUrlResponse(200, {}, b"x" * 10)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    request = HttpRequest(method="GET", url="https://svc.example/path")
    response = urllib_transport(request, 5.0)

    assert len(response.body) == 10


def test_urllib_transport_message_excludes_userinfo_query_and_fragment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_urlopen(
        request: urllib.request.Request, timeout: float
    ) -> _FakeUrlResponse:
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    request = HttpRequest(
        method="GET",
        url="https://alice:s3cretpw@svc.example:8443/api/path?token=leak-me#frag-secret",
    )
    with pytest.raises(TransportError) as excinfo:
        urllib_transport(request, 5.0)

    message = str(excinfo.value)
    assert "alice" not in message
    assert "s3cretpw" not in message
    assert "token=leak-me" not in message
    assert "frag-secret" not in message
    assert "svc.example:8443/api/path" in message


# --- No TransportError message ever interpolates exception text (Req 10.4,
# controller ruling: a real ValueError/InvalidURL from a malformed URL
# carries the full URL, query and all, in its own message) -----------------


def test_urllib_transport_real_no_scheme_url_value_error_never_leaks_the_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A URL with no scheme makes the *real*
    ``urllib.request.Request.__init__`` raise ``ValueError`` itself --
    before ``urlopen`` is ever reached, so ``urlopen`` is patched to a
    raiser only defensively (it is never actually called). The real
    stdlib ``ValueError``'s own message embeds the full URL, query
    included -- this is exactly the leak the controller's ruling closes:
    the production code must never interpolate ``str(exc)``.
    """

    def unreachable_urlopen(
        request: urllib.request.Request, timeout: float
    ) -> _FakeUrlResponse:
        raise AssertionError("urlopen must not be reached for a no-scheme URL")

    monkeypatch.setattr(urllib.request, "urlopen", unreachable_urlopen)

    request = HttpRequest(method="GET", url="svc.example/p?token=leak-me")
    with pytest.raises(TransportError) as excinfo:
        urllib_transport(request, 5.0)

    assert "token=leak-me" not in str(excinfo.value)


def test_urllib_transport_real_no_scheme_url_with_secret_url_shows_only_the_marker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unreachable_urlopen(
        request: urllib.request.Request, timeout: float
    ) -> _FakeUrlResponse:
        raise AssertionError("urlopen must not be reached for a no-scheme URL")

    monkeypatch.setattr(urllib.request, "urlopen", unreachable_urlopen)

    request = HttpRequest(
        method="GET", url="svc.example/p?sig=leak-me", url_is_secret=True
    )
    with pytest.raises(TransportError) as excinfo:
        urllib_transport(request, 5.0)

    message = str(excinfo.value)
    assert "sig=leak-me" not in message
    assert "svc.example" not in message
    assert "<signed location>" in message


def test_urllib_transport_http_client_invalid_url_never_leaks_the_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    url = "https://svc.example/path?token=leak-me"

    def fake_urlopen(
        request: urllib.request.Request, timeout: float
    ) -> _FakeUrlResponse:
        raise http.client.InvalidURL(f"URL can't contain control characters. {url!r}")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    request = HttpRequest(method="GET", url=url)
    with pytest.raises(TransportError) as excinfo:
        urllib_transport(request, 5.0)

    assert "token=leak-me" not in str(excinfo.value)


def test_urllib_transport_urlerror_reason_text_never_leaks_the_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    url = "https://svc.example/path?token=leak-me"

    def fake_urlopen(
        request: urllib.request.Request, timeout: float
    ) -> _FakeUrlResponse:
        raise urllib.error.URLError(OSError(f"failed to connect to {url}"))

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    request = HttpRequest(method="GET", url=url)
    with pytest.raises(TransportError) as excinfo:
        urllib_transport(request, 5.0)

    assert "token=leak-me" not in str(excinfo.value)


def test_urllib_transport_bare_oserror_text_never_leaks_the_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Distinct from the URLError test above: this raises a plain OSError
    # directly (neither URLError nor TimeoutError), reaching the final
    # catch-all `except OSError` arm, whose own message must equally never
    # interpolate the exception's text.
    url = "https://svc.example/path?token=leak-me"

    def fake_urlopen(
        request: urllib.request.Request, timeout: float
    ) -> _FakeUrlResponse:
        raise OSError(f"some os-level error mentioning {url}")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    request = HttpRequest(method="GET", url=url)
    with pytest.raises(TransportError) as excinfo:
        urllib_transport(request, 5.0)

    assert "token=leak-me" not in str(excinfo.value)


def test_urllib_transport_timeout_exception_text_never_leaks_the_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Distinct from test_urllib_transport_raises_transport_error_on_a_timeout
    # above: that fixture's TimeoutError message ("timed out") never
    # contained the URL in the first place, so restoring `{exc}`
    # interpolation there would not have been observable. This fixture's
    # TimeoutError message embeds the URL directly, so it is.
    url = "https://svc.example/path?token=leak-me"

    def fake_urlopen(
        request: urllib.request.Request, timeout: float
    ) -> _FakeUrlResponse:
        raise TimeoutError(f"connection to {url} timed out")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    request = HttpRequest(method="GET", url=url)
    with pytest.raises(TransportError) as excinfo:
        urllib_transport(request, 5.0)

    assert "token=leak-me" not in str(excinfo.value)
    # The dedicated timeout reason, not the generic network-failure one.
    assert str(excinfo.value) == "timed out: https://svc.example/path"


@pytest.mark.parametrize(
    ("url_is_secret", "expected"),
    [
        (False, "response too large: https://svc.example/path"),
        (True, "response too large: <signed location>"),
    ],
)
def test_urllib_transport_too_large_message_names_only_the_target(
    monkeypatch: pytest.MonkeyPatch, url_is_secret: bool, expected: str
) -> None:
    monkeypatch.setattr(http_module, "MAX_RESPONSE_BYTES", 10)

    def fake_urlopen(
        request: urllib.request.Request, timeout: float
    ) -> _FakeUrlResponse:
        return _FakeUrlResponse(200, {}, b"x" * 11)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    request = HttpRequest(
        method="GET",
        url="https://svc.example/path?token=leak-me",
        url_is_secret=url_is_secret,
    )
    with pytest.raises(TransportError) as excinfo:
        urllib_transport(request, 5.0)

    assert str(excinfo.value) == expected


# --- auth_failure_from (design.md) ------------------------------------------


@pytest.mark.parametrize(
    ("status", "kind"),
    [
        (401, AuthFailureKind.REJECTED),
        (403, AuthFailureKind.BLOCKED),
        (429, AuthFailureKind.RATE_LIMITED),
        (500, AuthFailureKind.UNAVAILABLE),
        (501, AuthFailureKind.UNAVAILABLE),
        (599, AuthFailureKind.UNAVAILABLE),
    ],
)
def test_auth_failure_from_maps_each_status_to_its_kind(
    status: int, kind: AuthFailureKind
) -> None:
    failure = auth_failure_from(_response(status))

    assert failure is not None
    assert failure.kind is kind


@pytest.mark.parametrize("status", [200, 499, 600])
def test_auth_failure_from_returns_none_outside_the_mapped_ranges(status: int) -> None:
    assert auth_failure_from(_response(status)) is None


def test_auth_failure_from_parses_retry_after_on_429() -> None:
    failure = auth_failure_from(_response(429, {"retry-after": "13"}))

    assert failure is not None
    assert failure.retry_after_s == 13.0


def test_auth_failure_from_parses_an_http_date_retry_after_against_date_header() -> (
    None
):
    date_header = "Mon, 01 Jan 2024 00:00:00 GMT"
    retry_after_header = "Mon, 01 Jan 2024 00:00:07 GMT"
    failure = auth_failure_from(
        _response(429, {"date": date_header, "retry-after": retry_after_header})
    )

    assert failure is not None
    assert failure.retry_after_s == 7.0


def test_auth_failure_from_http_date_retry_after_without_date_header_is_none() -> None:
    retry_after_header = "Mon, 01 Jan 2024 00:00:07 GMT"
    failure = auth_failure_from(_response(429, {"retry-after": retry_after_header}))

    assert failure is not None
    assert failure.retry_after_s is None


def test_auth_failure_from_treats_infinite_retry_after_as_unparseable() -> None:
    failure = auth_failure_from(_response(429, {"retry-after": "inf"}))

    assert failure is not None
    assert failure.retry_after_s is None


def test_auth_failure_from_uses_the_given_service_message_verbatim() -> None:
    failure = auth_failure_from(_response(401), service_message="account disabled")

    assert failure is not None
    assert failure.service_message == "account disabled"
    # Distinguishing from the default-message fallback: str(401) would not
    # equal this custom text, so a mutation that ignores service_message
    # cannot pass.
    assert failure.service_message != str(401)
