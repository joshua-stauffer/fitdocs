"""StravaApi's OAuth calls and `classify` (task 3.1), against a scripted Outbound."""

from __future__ import annotations

import base64
import logging
from urllib.parse import parse_qs, urlsplit

import pytest
from tests.strava.scripted_strava import (
    ScriptedOutbound,
    UnscriptedCall,
    reply,
)

from fitdocs_relay.outbound import OutboundError
from fitdocs_relay.strava.api import (
    REQUESTED_SCOPES,
    Failure,
    Grant,
    Step,
    StravaApi,
    StravaFailure,
    TokenPair,
    classify,
    daily_spent,
)
from fitdocs_relay.strava.config import Limits, StravaConfig

CLIENT_ID = "4711"
CLIENT_SECRET = "client-secret-SENTINEL"
OAUTH = "https://oauth.example/oauth"
TOKEN_URL = f"{OAUTH}/token"
REVOKE_URL = f"{OAUTH}/revoke"
LIMITS = Limits(overall_15m=200, overall_day=2000, read_15m=100, read_day=1000)
CONFIG = StravaConfig(
    client_id=CLIENT_ID,
    client_secret=CLIENT_SECRET,
    webhook_token="w" * 40,
    api_url="https://api.example/v3",
    oauth_url=OAUTH,
    web_url="https://web.example",
    limits=LIMITS,
)

ACCESS = "access-tok-AAA"
REFRESH = "refresh-tok-RRR"
ATHLETE = 90210123
SENTINEL = "STRAVA-ERROR-TEXT-SENTINEL"
TOKENS = {"access_token": ACCESS, "refresh_token": REFRESH, "expires_at": 1_800_000_000}
GRANT_BODY = {**TOKENS, "athlete": {"id": ATHLETE, "firstname": SENTINEL}}


def make() -> tuple[StravaApi, ScriptedOutbound]:
    fake = ScriptedOutbound()
    return StravaApi(CONFIG, outbound=fake), fake


# --- classify: every row, for every step ------------------------------------

ALL_STEPS = list(Step)
# Bodies a 2xx may carry so that every step counts it as answered.
READABLE = {
    Step.EXCHANGE: GRANT_BODY,
    Step.REFRESH: TOKENS,
    Step.REVOKE: {},
    Step.LIST: [],
    Step.UPDATE: {},
    Step.UPLOAD: {"id": 7},
    Step.UPLOAD_STATUS: {"id": 7},
    Step.SUBSCRIPTION: {},
}

STATUS_ROWS = [
    (400, Failure.INVALID),
    (401, Failure.AUTH),
    (402, Failure.INVALID),
    (403, Failure.FORBIDDEN),
    (404, Failure.MISSING),
    (409, Failure.INVALID),
    (422, Failure.INVALID),
    (428, Failure.INVALID),
    (429, Failure.LIMITED),
    (451, Failure.INVALID),
    (499, Failure.INVALID),
    (500, Failure.SERVER),
    (502, Failure.SERVER),
    (503, Failure.SERVER),
    (599, Failure.SERVER),
    # not a success, not a client or server error: a 3xx answer did nothing and
    # refused nothing, so it is transient (SERVER)
    (300, Failure.SERVER),
    (301, Failure.SERVER),
    (302, Failure.SERVER),
    (303, Failure.SERVER),
    (307, Failure.SERVER),
    (308, Failure.SERVER),
    (399, Failure.SERVER),
    (100, Failure.SERVER),
    (199, Failure.SERVER),
    (600, Failure.SERVER),
    (0, Failure.SERVER),
]


@pytest.mark.parametrize("step", ALL_STEPS)
@pytest.mark.parametrize(("status", "expected"), STATUS_ROWS)
def test_status_rows(step: Step, status: int, expected: Failure) -> None:
    # a body that would read as a success, so only the status decides
    assert classify(step, reply(status, READABLE[step])) is expected


@pytest.mark.parametrize("step", ALL_STEPS)
@pytest.mark.parametrize("status", [200, 201, 202, 204, 299])
def test_readable_2xx_is_success(step: Step, status: int) -> None:
    assert classify(step, reply(status, READABLE[step])) is None


@pytest.mark.parametrize("step", ALL_STEPS)
@pytest.mark.parametrize("kind", ["timeout", "network", "invalid", "too-large"])
def test_every_outbound_error_kind_is_network(step: Step, kind: str) -> None:
    assert classify(step, OutboundError(kind)) is Failure.NETWORK  # type: ignore[arg-type]


def test_the_failure_vocabulary_is_closed() -> None:
    assert [f.value for f in Failure] == [
        "auth",
        "forbidden",
        "missing",
        "limited",
        "invalid",
        "server",
        "network",
        "unreadable",
    ]
    assert [s.value for s in Step] == [
        "exchange",
        "refresh",
        "revoke",
        "list",
        "update",
        "upload",
        "upload-status",
        "subscription",
    ]


# --- a 2xx that lacks what the step needs ------------------------------------


def _without(body: dict[str, object], key: str) -> dict[str, object]:
    return {k: v for k, v in body.items() if k != key}


def _athlete(value: object) -> dict[str, object]:
    return {**TOKENS, "athlete": value}


HOSTILE_TOKEN_BODIES: dict[str, object] = {
    "empty": b"",
    "not json": b"<html>nope</html>",
    "non-utf8": b'{"access_token": "\xff\xfe"}',
    "non-utf8 lead": b"\xff" + b"{}",
    "non-utf8 in an unused field": (
        b'{"access_token":"a","refresh_token":"r","expires_at":5,"x":"\xff"}'
    ),
    "array": [TOKENS],
    "string": "text",
    "null": None,
    "deep": b"[" * 100_000 + b"]" * 100_000,
    "deep object": b'{"a":' * 50_000 + b"1" + b"}" * 50_000,
    "nan expiry": b'{"access_token":"a","refresh_token":"r","expires_at":NaN}',
    "infinity expiry": (
        b'{"access_token":"a","refresh_token":"r","expires_at":Infinity}'
    ),
    "huge int": b'{"access_token":"a","refresh_token":"r","expires_at":'
    + b"9" * 5000
    + b"}",
    "no access": _without(TOKENS, "access_token"),
    "no refresh": _without(TOKENS, "refresh_token"),
    "no expiry": _without(TOKENS, "expires_at"),
    "null access": {**TOKENS, "access_token": None},
    "numeric access": {**TOKENS, "access_token": 5},
    "empty access": {**TOKENS, "access_token": ""},
    "empty refresh": {**TOKENS, "refresh_token": ""},
    "spaced access": {**TOKENS, "access_token": "a b"},
    "newline refresh": {**TOKENS, "refresh_token": "r\nx"},
    "non-ascii access": {**TOKENS, "access_token": "tökén"},
    "long access": {**TOKENS, "access_token": "a" * 5000},
    "string expiry": {**TOKENS, "expires_at": "1800000000"},
    "float expiry": {**TOKENS, "expires_at": 1.8e9},
    "bool expiry": {**TOKENS, "expires_at": True},
    "zero expiry": {**TOKENS, "expires_at": 0},
    "negative expiry": {**TOKENS, "expires_at": -5},
    "absurd expiry": {**TOKENS, "expires_at": 10**13},
}
HOSTILE_GRANT_BODIES: dict[str, object] = {
    **HOSTILE_TOKEN_BODIES,
    "non-utf8 in the athlete": (
        b'{"access_token":"a","refresh_token":"r","expires_at":5,'
        b'"athlete":{"id":9,"x":"\xff"}}'
    ),
    "no athlete": TOKENS,
    "null athlete": _athlete(None),
    "athlete list": _athlete([ATHLETE]),
    "athlete without id": _athlete({"firstname": "x"}),
    "string athlete id": _athlete({"id": "90210123"}),
    "bool athlete id": _athlete({"id": True}),
    "float athlete id": _athlete({"id": 1.5}),
    "zero athlete id": _athlete({"id": 0}),
    "negative athlete id": _athlete({"id": -3}),
    "huge athlete id": _athlete({"id": 10**19}),
}


@pytest.mark.parametrize("name", HOSTILE_GRANT_BODIES)
def test_exchange_with_unreadable_200_is_classified_not_raised(name: str) -> None:
    body = HOSTILE_GRANT_BODIES[name]
    assert classify(Step.EXCHANGE, reply(200, body)) is Failure.UNREADABLE
    api, fake = make()
    fake.expect("POST", TOKEN_URL, reply(200, body))
    assert api.exchange("c", timeout=5.0) == StravaFailure(
        Step.EXCHANGE, Failure.UNREADABLE, False
    )


@pytest.mark.parametrize("name", HOSTILE_TOKEN_BODIES)
def test_refresh_with_unreadable_200_is_classified_not_raised(name: str) -> None:
    body = HOSTILE_TOKEN_BODIES[name]
    assert classify(Step.REFRESH, reply(200, body)) is Failure.UNREADABLE
    api, fake = make()
    fake.expect("POST", TOKEN_URL, reply(200, body))
    assert api.refresh("r", timeout=5.0) == StravaFailure(
        Step.REFRESH, Failure.UNREADABLE, False
    )


def test_refresh_does_not_need_an_athlete() -> None:
    assert classify(Step.REFRESH, reply(200, TOKENS)) is None


@pytest.mark.parametrize(
    "body", [b"", b"nope", b"\xff", b"{}", b'{"id": 1}', b"null", b"[1]"]
)
def test_steps_that_read_nothing_accept_any_2xx_body(body: bytes) -> None:
    for step in (Step.REVOKE, Step.UPDATE, Step.SUBSCRIPTION):
        assert classify(step, reply(200, body)) is None


def test_list_needs_an_array_and_upload_an_object_with_an_id() -> None:
    assert classify(Step.LIST, reply(200, {"id": 1})) is Failure.UNREADABLE
    assert classify(Step.LIST, reply(200, b"\xff")) is Failure.UNREADABLE
    assert classify(Step.LIST, reply(200, [])) is None
    assert classify(Step.UPLOAD, reply(200, {})) is Failure.UNREADABLE
    assert classify(Step.UPLOAD, reply(200, [{"id": 1}])) is Failure.UNREADABLE
    assert classify(Step.UPLOAD, reply(200, {"id": 1})) is None
    assert classify(Step.UPLOAD_STATUS, reply(200, [])) is Failure.UNREADABLE
    assert classify(Step.UPLOAD_STATUS, reply(200, b"{")) is Failure.UNREADABLE
    assert classify(Step.UPLOAD_STATUS, reply(200, {})) is None
    # 3.2: the readers are structural, not just "an array" or "an object with an id"
    start = {"id": 1, "start_date": "2026-03-04T05:06:07Z"}
    assert classify(Step.LIST, reply(200, [start])) is None
    assert classify(Step.LIST, reply(200, [{"id": 1}])) is Failure.UNREADABLE
    assert (
        classify(Step.LIST, reply(200, [{"start_date": start["start_date"]}]))
        is Failure.UNREADABLE
    )
    assert classify(Step.UPLOAD, reply(200, {"id": "7"})) is Failure.UNREADABLE
    assert classify(Step.UPLOAD, reply(200, {"id": None})) is Failure.UNREADABLE
    assert classify(Step.UPLOAD_STATUS, reply(200, {"error": "x"})) is None
    assert (
        classify(Step.UPLOAD_STATUS, reply(200, {"activity_id": "7"}))
        is Failure.UNREADABLE
    )


# --- the daily-spent flag ----------------------------------------------------


def _limited(**headers: str) -> object:
    return reply(429, {}, {k.replace("_", "-"): v for k, v in headers.items()})


@pytest.mark.parametrize(
    ("headers", "expected"),
    [
        # overall usage against the overall daily limit (2000), not the read one
        ({"x-ratelimit-usage": "10,2000"}, True),
        ({"x-ratelimit-usage": "10,1999"}, False),
        ({"x-ratelimit-usage": "10,1500"}, False),
        ({"x-ratelimit-usage": "10,2001"}, True),
        # read usage against the read daily limit (1000)
        ({"x-readratelimit-usage": "10,1000"}, True),
        ({"x-readratelimit-usage": "10,999"}, False),
        ({"x-readratelimit-usage": "10,1500"}, True),
        # the 15 minute figure reaching its limit is not the day
        ({"x-ratelimit-usage": "200,5"}, False),
        ({"x-readratelimit-usage": "100,5"}, False),
        ({"x-ratelimit-usage": "5000,5"}, False),
        # either header can speak
        ({"x-ratelimit-usage": "1,1", "x-readratelimit-usage": "1,1000"}, True),
        ({"x-ratelimit-usage": "1,2000", "x-readratelimit-usage": "1,1"}, True),
        ({"x-ratelimit-usage": "1,1", "x-readratelimit-usage": "1,1"}, False),
        ({"x-ratelimit-usage": " 1 , 2000 "}, True),
        # absent or hostile headers are never spent
        ({}, False),
        ({"x-ratelimit-usage": ""}, False),
        ({"x-ratelimit-usage": "2000"}, False),
        ({"x-ratelimit-usage": "1,2000,3"}, False),
        ({"x-ratelimit-usage": "a,2000"}, False),
        ({"x-ratelimit-usage": "1,-2000"}, False),
        ({"x-ratelimit-usage": "1," + "9" * 5000}, False),
        ({"x-ratelimit-usage": "1,２０００"}, False),
        # a limit header is not a usage header
        ({"x-ratelimit-limit": "200,2000"}, False),
        ({"x-readratelimit-limit": "100,1000"}, False),
    ],
)
def test_daily_spent_from_usage_headers(
    headers: dict[str, str], expected: bool
) -> None:
    assert daily_spent(reply(429, {}, headers), LIMITS) is expected
    api, fake = make()
    fake.expect("POST", TOKEN_URL, reply(429, {}, headers))
    assert api.refresh("r", timeout=5.0) == StravaFailure(
        Step.REFRESH, Failure.LIMITED, expected
    )


@pytest.mark.parametrize("status", [401, 403, 404, 400, 500, 302])
def test_daily_spent_is_set_only_on_limited(status: int) -> None:
    api, fake = make()
    spent = {"x-ratelimit-usage": "1,2000", "x-readratelimit-usage": "1,1000"}
    fake.expect("POST", TOKEN_URL, reply(status, {}, spent))
    result = api.refresh("r", timeout=5.0)
    assert isinstance(result, StravaFailure)
    assert result.failure is not Failure.LIMITED
    assert result.daily_spent is False


def test_usage_header_values_are_not_kept() -> None:
    api, fake = make()
    fake.expect("POST", TOKEN_URL, reply(429, {}, {"x-ratelimit-usage": "77,2000"}))
    result = api.refresh("r", timeout=5.0)
    assert repr(result) == (
        "StravaFailure(step=<Step.REFRESH: 'refresh'>, "
        "failure=<Failure.LIMITED: 'limited'>, daily_spent=True)"
    )


# --- the authorization address -----------------------------------------------


def test_authorize_url_has_the_two_scopes_and_the_state() -> None:
    api, _ = make()
    url = api.authorize_url(state="st-ate_1", redirect_uri="https://relay.example/cb")
    parts = urlsplit(url)
    assert f"{parts.scheme}://{parts.netloc}{parts.path}" == f"{OAUTH}/authorize"
    assert parse_qs(parts.query, strict_parsing=True) == {
        "client_id": [CLIENT_ID],
        "redirect_uri": ["https://relay.example/cb"],
        "response_type": ["code"],
        "approval_prompt": ["auto"],
        "scope": ["activity:read_all,activity:write"],
        "state": ["st-ate_1"],
    }
    assert REQUESTED_SCOPES == ("activity:read_all", "activity:write")
    assert CLIENT_SECRET not in url


def test_authorize_url_escapes_what_it_interpolates() -> None:
    api, _ = make()
    url = api.authorize_url(
        state="a&scope=evil b#x", redirect_uri="https://r/cb?x=1&y=2"
    )
    query = parse_qs(urlsplit(url).query, strict_parsing=True)
    assert query["state"] == ["a&scope=evil b#x"]
    assert query["redirect_uri"] == ["https://r/cb?x=1&y=2"]
    assert query["scope"] == ["activity:read_all,activity:write"]
    assert urlsplit(url).fragment == ""


# --- the exchange, the refresh and the revoke ---------------------------------


def test_exchange_posts_the_code_and_returns_the_grant() -> None:
    api, fake = make()
    fake.expect("POST", TOKEN_URL, reply(200, GRANT_BODY))
    result = api.exchange("the-code", timeout=4.5)
    assert result == Grant(ACCESS, REFRESH, 1_800_000_000, str(ATHLETE))
    assert len(fake.calls) == 1
    call = fake.calls[0]
    assert call.timeout == 4.5
    assert call.request.method == "POST"
    assert call.request.url == TOKEN_URL
    assert call.form == {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "code": "the-code",
        "grant_type": "authorization_code",
    }
    assert call.request.headers["Content-Type"] == "application/x-www-form-urlencoded"
    assert call.request.headers["Accept"] == "application/json"
    assert dict(call.request.secret_headers) == {}
    assert not call.request.url_is_secret
    assert "code" not in call.request.url and CLIENT_SECRET not in call.request.url


def test_the_athlete_id_is_only_inside_the_grant_value() -> None:
    api, fake = make()
    fake.expect("POST", TOKEN_URL, reply(200, GRANT_BODY))
    result = api.exchange("c", timeout=5.0)
    assert isinstance(result, Grant)
    assert result.athlete_id == "90210123"
    assert isinstance(result.athlete_id, str)
    shown = repr(result) + str(result)
    for secret in (str(ATHLETE), ACCESS, REFRESH, SENTINEL):
        assert secret not in shown
    assert "1800000000" in shown  # the expiry is shown: the repr is not empty


def test_refresh_posts_the_refresh_token_and_returns_the_pair() -> None:
    api, fake = make()
    fake.expect("POST", TOKEN_URL, reply(200, {**TOKENS, "athlete": {"id": 1}}))
    result = api.refresh("old-refresh", timeout=3.0)
    assert result == TokenPair(ACCESS, REFRESH, 1_800_000_000)
    assert not isinstance(result, Grant)
    call = fake.calls[0]
    assert call.timeout == 3.0
    assert call.request.url == TOKEN_URL
    assert call.form == {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "grant_type": "refresh_token",
        "refresh_token": "old-refresh",
    }
    assert "old-refresh" not in call.request.url
    assert "old-refresh" not in str(dict(call.request.headers))
    assert dict(call.request.secret_headers) == {}
    assert repr(result) == "TokenPair(expires_at=1800000000)"


def test_revoke_sends_the_token_with_basic_client_credentials() -> None:
    api, fake = make()
    fake.expect("POST", REVOKE_URL, reply(200, {}))
    assert api.revoke("tok-to-revoke", timeout=2.5) is None
    call = fake.calls[0]
    assert call.timeout == 2.5
    assert call.request.method == "POST"
    assert call.request.url == REVOKE_URL
    assert call.form == {"token": "tok-to-revoke"}
    basic = dict(call.request.secret_headers)["Authorization"]
    assert basic.startswith("Basic ")
    assert base64.b64decode(basic[6:]).decode() == f"{CLIENT_ID}:{CLIENT_SECRET}"
    assert "tok-to-revoke" not in call.request.url
    assert CLIENT_SECRET not in call.request.url
    assert CLIENT_SECRET not in str(dict(call.request.headers))
    assert CLIENT_SECRET not in repr(call.request)


def test_form_values_are_encoded_not_interpolated() -> None:
    api, fake = make()
    fake.expect("POST", TOKEN_URL, reply(200, GRANT_BODY))
    api.exchange("a&grant_type=x b=c", timeout=5.0)
    assert fake.calls[0].form["code"] == "a&grant_type=x b=c"
    assert fake.calls[0].form["grant_type"] == "authorization_code"


@pytest.mark.parametrize("status", [302, 301, 303, 307, 308])
def test_a_redirect_is_never_a_success(status: int) -> None:
    api, fake = make()
    redirect = reply(status, b"", {"location": "https://elsewhere.example/"})
    fake.expect("POST", TOKEN_URL, redirect, redirect)
    fake.expect("POST", REVOKE_URL, redirect)
    assert api.exchange("c", timeout=5.0) == StravaFailure(
        Step.EXCHANGE, Failure.SERVER
    )
    assert api.refresh("r", timeout=5.0) == StravaFailure(Step.REFRESH, Failure.SERVER)
    assert api.revoke("t", timeout=5.0) == StravaFailure(Step.REVOKE, Failure.SERVER)


@pytest.mark.parametrize("kind", ["timeout", "network", "invalid", "too-large"])
def test_an_outbound_error_is_a_network_failure_for_every_call(kind: str) -> None:
    api, fake = make()
    error = OutboundError(kind)  # type: ignore[arg-type]
    fake.expect("POST", TOKEN_URL, error, error)
    fake.expect("POST", REVOKE_URL, error)
    assert api.exchange("c", timeout=5.0) == StravaFailure(
        Step.EXCHANGE, Failure.NETWORK
    )
    assert api.refresh("r", timeout=5.0) == StravaFailure(Step.REFRESH, Failure.NETWORK)
    assert api.revoke("t", timeout=5.0) == StravaFailure(Step.REVOKE, Failure.NETWORK)


@pytest.mark.parametrize(
    ("status", "expected"),
    [
        (400, Failure.INVALID),
        (401, Failure.AUTH),
        (403, Failure.FORBIDDEN),
        (404, Failure.MISSING),
        (429, Failure.LIMITED),
        (500, Failure.SERVER),
    ],
)
def test_the_calls_map_status_through_classify(status: int, expected: Failure) -> None:
    api, fake = make()
    fake.expect("POST", TOKEN_URL, reply(status, {}), reply(status, {}))
    fake.expect("POST", REVOKE_URL, reply(status, {}))
    assert api.exchange("c", timeout=5.0) == StravaFailure(Step.EXCHANGE, expected)
    assert api.refresh("r", timeout=5.0) == StravaFailure(Step.REFRESH, expected)
    assert api.revoke("t", timeout=5.0) == StravaFailure(Step.REVOKE, expected)


def test_revoke_accepts_any_2xx_body() -> None:
    api, fake = make()
    fake.expect("POST", REVOKE_URL, reply(200, b"\xff not json"), reply(204))
    assert api.revoke("t", timeout=5.0) is None
    assert api.revoke("t", timeout=5.0) is None


# --- nothing Strava says comes back -------------------------------------------


def test_a_sentinel_in_an_error_body_appears_in_no_returned_value(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    leak = {
        "message": SENTINEL,
        "errors": [{"resource": SENTINEL, "field": SENTINEL, "code": SENTINEL}],
    }
    headers = {"x-ratelimit-usage": "1,2000", "www-authenticate": SENTINEL}
    results: list[object] = []
    for status in (400, 401, 403, 404, 429, 500, 302):
        api, fake = make()
        fake.expect("POST", TOKEN_URL, *[reply(status, leak, headers)] * 2)
        fake.expect("POST", REVOKE_URL, reply(status, leak, headers))
        results += [
            api.exchange("c", timeout=5.0),
            api.refresh("r", timeout=5.0),
            api.revoke("t", timeout=5.0),
        ]
    # a 200 whose body is the sentinel, and one that is partly readable
    for body in (leak, {**TOKENS, "athlete": SENTINEL}, SENTINEL.encode()):
        api, fake = make()
        fake.expect("POST", TOKEN_URL, reply(200, body), reply(200, body))
        results += [api.exchange("c", timeout=5.0), api.refresh("r", timeout=5.0)]
    assert len(results) == 7 * 3 + 3 * 2
    # the one partly readable body is a readable refresh; the rest are failures
    assert sum(isinstance(r, StravaFailure) for r in results) == 7 * 3 + 5
    assert sum(isinstance(r, TokenPair) for r in results) == 1
    for result in results:
        assert SENTINEL not in repr(result)
        assert SENTINEL not in str(vars(result))
    assert SENTINEL not in caplog.text


def test_a_sentinel_in_the_success_body_is_not_in_the_grant() -> None:
    api, fake = make()
    body = {
        **GRANT_BODY,
        "message": SENTINEL,
        "athlete": {"id": ATHLETE, "x": SENTINEL},
    }
    fake.expect("POST", TOKEN_URL, reply(200, body))
    result = api.exchange("c", timeout=5.0)
    assert isinstance(result, Grant)
    assert SENTINEL not in str(vars(result))


# --- the scripted fake ---------------------------------------------------------


def test_an_unscripted_request_fails_loudly_and_is_not_a_provider_failure() -> None:
    api, fake = make()
    with pytest.raises(UnscriptedCall):
        api.exchange("c", timeout=5.0)
    assert [c.request.url for c in fake.calls] == [TOKEN_URL]
    fake.expect("POST", TOKEN_URL, reply(200, GRANT_BODY))
    with pytest.raises(UnscriptedCall):
        api.revoke("t", timeout=5.0)  # another address: still unscripted
    assert issubclass(UnscriptedCall, AssertionError)
    assert not issubclass(UnscriptedCall, OutboundError)


def test_the_fake_serves_each_answer_once_in_order_and_records_requests() -> None:
    api, fake = make()
    fake.expect("POST", TOKEN_URL, reply(500), reply(200, GRANT_BODY))
    first = api.exchange("c1", timeout=1.0)
    second = api.exchange("c2", timeout=2.0)
    assert first == StravaFailure(Step.EXCHANGE, Failure.SERVER)
    assert isinstance(second, Grant)
    assert [c.form["code"] for c in fake.calls] == ["c1", "c2"]
    assert [c.timeout for c in fake.calls] == [1.0, 2.0]
    assert fake.unserved() == 0
    with pytest.raises(UnscriptedCall):
        api.exchange("c3", timeout=1.0)


def test_the_fixture_is_a_fresh_fake(scripted_outbound: ScriptedOutbound) -> None:
    assert scripted_outbound.calls == []
    assert scripted_outbound.unserved() == 0
