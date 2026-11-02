"""The Strava browser pages, the link and the webhook (strava-publish 4.3).

Run on both backends.

Built on the 4.2 world: real services over a real store, Strava scripted at the
outbound seam, so a request nobody scripted raises and `outbound.calls` is the
count of Strava requests.
"""

# ruff: noqa: F811
from __future__ import annotations

import hmac
import html
import json
import logging
from collections.abc import Callable
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest
from tests.strava.scripted_strava import reply
from tests.strava.test_connect import FULL, grant_body
from tests.strava.test_publish import (
    ACTIVITY_ID,
    LIST_URL,
    UPDATE_URL,
    entry,
)
from tests.test_strava_routes import (  # noqa: F401  (fixtures)
    GO_PATH,
    OAUTH,
    PUBLISH_PATH,
    ROUTES,
    World,
    decoded,
    make_world,
    publish_body,
    started_session,
    world,
)

from fitdocs_relay.shared.relay_codes import RelayCode
from fitdocs_relay.shared.relay_targets import (
    ACTION_CONNECT_POLL,
    STRAVA,
    connect_page_path,
)
from fitdocs_relay.storage.interface import StorageUnreachable
from fitdocs_relay.strava.api import Grant
from fitdocs_relay.strava.config import LinkSetting
from fitdocs_relay.strava.connect import CLAIM_COOKIE, ShowConsent
from fitdocs_relay.strava.pages import PAGE_HEADERS, privacy_page
from fitdocs_relay.strava.policy import POLICY_HEADINGS, consent_text
from fitdocs_relay.strava.webhook import MAX_EVENT_BYTES

SECRET = "t" * 40  # the webhook secret of tests.test_config_strava.env
HOOK = f"/strava/webhook/{SECRET}"
SENTINEL = "SENTINEL-9f3b-from-strava"
CONNECT_PAGE = "/connect/strava"
CALLBACK = "/strava/callback"
ATHLETE = "90210"
DEAUTH = json.dumps(
    {
        "object_type": "athlete",
        "owner_id": int(ATHLETE),
        "updates": {"authorized": "false"},
    }
).encode()
PAGE_ROUTES = ["/privacy", "/robots.txt", CONNECT_PAGE, CALLBACK, GO_PATH]


def cookie_header(value: str) -> dict[str, str]:
    return {"Cookie": f"{CLAIM_COOKIE}={value}"}


def open_page(w: World, code: str, headers: dict[str, str] | None = None) -> Any:
    w.client.cookies.clear()
    return w.client.get(f"{CONNECT_PAGE}?code={code}", headers=headers or {})


def claimed(w: World) -> tuple[Any, str, str]:
    """A started session whose page has been opened: (started, cookie, state)."""
    started = started_session(w)
    sent = open_page(w, started.user_code)
    assert sent.status_code == 200
    cookie = sent.headers["set-cookie"].split(";")[0].partition("=")[2]
    shown = w.strava().connect.page(started.user_code, cookie)
    assert isinstance(shown, ShowConsent)
    state = parse_qs(urlsplit(shown.authorize_url).query)["state"][0]
    return started, cookie, state


def assert_page_headers(sent: Any) -> None:
    for name, value in PAGE_HEADERS.items():
        assert sent.headers[name] == value


# --- the connect page and the claim cookie ----------------------------------


def test_the_connect_page_shows_the_session_and_sets_the_claim_cookie(
    world: World,
) -> None:
    started = started_session(world)
    sent = open_page(world, started.user_code)
    assert sent.status_code == 200
    assert sent.headers["content-type"].startswith("text/html")
    assert_page_headers(sent)
    assert started.user_code in sent.text
    assert "Connect with Strava" in sent.text
    cookies = sent.headers.get_list("set-cookie")
    assert len(cookies) == 1
    name_value, *attributes = (part.strip() for part in cookies[0].split(";"))
    assert name_value.startswith(f"{CLAIM_COOKIE}=")
    assert len(name_value.partition("=")[2]) >= 40
    assert sorted(attributes) == sorted(
        ["Max-Age=600", "Path=/", "HttpOnly", "SameSite=Lax", "Secure"]
    )


def test_the_set_cookie_value_is_sent_back_verbatim_as_one_header(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    given = f"{CLAIM_COOKIE}=abc123; Max-Age=77; Path=/x; HttpOnly; Odd=1"
    shown = ShowConsent("BCDF-GHJK", "https://oauth.example/authorize?state=s", given)
    monkeypatch.setattr(world.strava().connect, "page", lambda code, cookie: shown)
    sent = open_page(world, "BCDF-GHJK")
    assert sent.headers.get_list("set-cookie") == [given]


def test_the_claim_cookie_is_read_from_the_cookie_header(world: World) -> None:
    started = started_session(world)
    first = open_page(world, started.user_code)
    cookie = first.headers["set-cookie"].split(";")[0].partition("=")[2]
    assert open_page(world, started.user_code).status_code == 409  # no cookie
    own = open_page(world, started.user_code, cookie_header(cookie))
    assert own.status_code == 200
    assert "set-cookie" not in own.headers
    other = open_page(world, started.user_code, cookie_header(cookie + "x"))
    assert other.status_code == 409
    assert "set-cookie" not in other.headers
    assert_page_headers(other)


@pytest.mark.parametrize("query", ["", "?code=not-a-code", "?code=BCDF-GHJK"])
def test_a_malformed_absent_or_unknown_code_is_the_invalid_page(
    world: World, query: str
) -> None:
    sent = world.client.get(CONNECT_PAGE + query)
    assert sent.status_code == 404
    assert "set-cookie" not in sent.headers
    assert_page_headers(sent)
    assert "does not work" in sent.text


# --- the callback ------------------------------------------------------------


def test_a_granted_callback_serves_the_granted_page_and_the_poll_issues_the_token(
    world: World,
) -> None:
    started, cookie, state = claimed(world)
    world.outbound.expect("POST", f"{OAUTH}/token", reply(200, grant_body("A1")))
    sent = world.client.get(
        f"{CALLBACK}?state={state}&code=the-code&scope={FULL}",
        headers=cookie_header(cookie),
    )
    assert sent.status_code == 200
    assert "Connected" in sent.text
    assert_page_headers(sent)
    assert len(world.outbound.calls) == 1  # one exchange
    polled = world.post(
        ROUTES[ACTION_CONNECT_POLL], {"poll_secret": started.poll_secret}
    )
    assert decoded(polled).code is RelayCode.CONNECT_GRANTED


def test_a_callback_without_the_claim_is_refused_and_spends_nothing(
    world: World,
) -> None:
    started, cookie, state = claimed(world)
    sent = world.client.get(f"{CALLBACK}?state={state}&code=the-code&scope={FULL}")
    assert sent.status_code == 404
    assert "Connected" not in sent.text
    assert world.outbound.calls == []
    # the state was not burnt: the claiming browser can still finish
    world.outbound.expect("POST", f"{OAUTH}/token", reply(200, grant_body("A1")))
    again = world.client.get(
        f"{CALLBACK}?state={state}&code=the-code&scope={FULL}",
        headers=cookie_header(cookie),
    )
    assert again.status_code == 200 and "Connected" in again.text


def test_a_declined_callback_serves_the_refused_page_and_the_poll_is_refused(
    world: World,
) -> None:
    started, cookie, state = claimed(world)
    sent = world.client.get(
        f"{CALLBACK}?state={state}&error=access_denied", headers=cookie_header(cookie)
    )
    assert sent.status_code == 200
    assert "Not connected" in sent.text
    assert_page_headers(sent)
    polled = world.post(
        ROUTES[ACTION_CONNECT_POLL], {"poll_secret": started.poll_secret}
    )
    assert decoded(polled).code is RelayCode.CONNECT_REFUSED
    assert world.outbound.calls == []


# --- failures answer a page, never JSON or a traceback -----------------------


def test_an_exception_out_of_the_callback_is_the_unavailable_page_and_a_log_record(
    world: World, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def boom(**_: object) -> None:
        raise RuntimeError(SENTINEL)

    monkeypatch.setattr(world.strava().connect, "callback", boom)
    with caplog.at_level(logging.INFO, logger="fitdocs_relay.app"):
        sent = world.client.get(f"{CALLBACK}?state=s&code=c")
    assert sent.status_code == 503
    assert sent.headers["content-type"].startswith("text/html")
    assert "Not available" in sent.text
    assert SENTINEL not in sent.text and "Traceback" not in sent.text
    assert_page_headers(sent)
    request = [r for r in caplog.records if getattr(r, "event", "") == "request"][-1]
    assert request.error_type == "RuntimeError"  # type: ignore[attr-defined]
    assert request.levelno == logging.ERROR
    assert SENTINEL not in json.dumps(request.__dict__, default=str)


@pytest.mark.parametrize("path", PAGE_ROUTES)
def test_a_store_that_cannot_be_reached_is_the_unavailable_page_on_every_page_route(
    world: World,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    path: str,
) -> None:
    def down(address: str | None) -> None:
        raise StorageUnreachable

    monkeypatch.setattr(world.services.limiter, "check_client", down)
    with caplog.at_level(logging.INFO, logger="fitdocs_relay.app"):
        sent = world.client.get(path, follow_redirects=False)
    # an unreachable store is an expected condition, not a logged failure
    assert [r.levelno for r in caplog.records] == [logging.INFO]
    assert sent.status_code == 503
    assert sent.headers["content-type"].startswith("text/html")
    assert_page_headers(sent)


@pytest.mark.parametrize("path", PAGE_ROUTES)
def test_every_page_route_is_the_unavailable_page_while_the_relay_is_not_ready(
    world: World, path: str
) -> None:
    world.services.ready = False
    sent = world.client.get(path, follow_redirects=False)
    assert sent.status_code == 503
    assert "Not available" in sent.text
    assert_page_headers(sent)
    assert world.outbound.calls == []


@pytest.mark.parametrize("path", PAGE_ROUTES)
def test_a_relay_that_is_not_ready_answers_unavailable_before_any_client_limit(
    make_world: Callable[..., World], path: str
) -> None:
    w = make_world(client_limit=1)
    w.services.ready = False
    statuses = [w.client.get(path, follow_redirects=False) for _ in range(3)]
    assert [sent.status_code for sent in statuses] == [503, 503, 503]
    assert all("Not available" in sent.text for sent in statuses)


@pytest.mark.parametrize("path", PAGE_ROUTES)
def test_every_page_route_is_limited_per_client_with_the_try_later_page(
    make_world: Callable[..., World], path: str
) -> None:
    w = make_world(client_limit=2)
    statuses = [
        w.client.get(path, follow_redirects=False).status_code for _ in range(3)
    ]
    assert 429 not in statuses[:2]
    assert statuses[2] == 429
    third = w.client.get(path, follow_redirects=False)
    assert "Try again later" in third.text
    assert_page_headers(third)


def test_the_page_routes_share_one_client_count(
    make_world: Callable[..., World],
) -> None:
    w = make_world(client_limit=2)
    assert w.client.get("/privacy").status_code == 200
    assert w.client.get("/robots.txt").status_code == 200
    assert w.client.get("/privacy").status_code == 429


# --- /go/ --------------------------------------------------------------------


def posted(w: World) -> None:
    w.connect()
    w.script_list(entry())
    w.outbound.expect("PUT", UPDATE_URL, reply(200, {}))
    assert decoded(w.post(PUBLISH_PATH, publish_body())).outcome == "posted"


def test_the_redirect_carries_only_location_and_the_page_headers(
    world: World,
) -> None:
    posted(world)
    world.script_list(entry())
    sent = world.client.get(GO_PATH, follow_redirects=False)
    assert sent.status_code == 302
    assert set(sent.headers) == {
        "location",
        "content-length",
        *(name.lower() for name in PAGE_HEADERS),
    }
    assert sent.content == b""


def test_every_go_refusal_carries_the_page_headers(world: World) -> None:
    posted(world)
    world.outbound.expect("GET", LIST_URL, reply(429))
    answers = {
        "limited": world.client.get(GO_PATH),
        "unknown": world.client.get("/go/" + "b" * 32),
        "malformed": world.client.get("/go/NOT-AN-ID"),
    }
    assert [a.status_code for a in answers.values()] == [429, 404, 404]
    for sent in answers.values():
        assert sent.headers["content-type"].startswith("text/html")
        assert_page_headers(sent)


@pytest.mark.parametrize("failure", [StorageUnreachable(), RuntimeError(SENTINEL)])
def test_a_failure_resolving_the_link_is_the_unavailable_page_with_page_headers(
    world: World, monkeypatch: pytest.MonkeyPatch, failure: Exception
) -> None:
    def fail(publication_id: str) -> str:
        raise failure

    monkeypatch.setattr(world.strava().publisher, "resolve_link", fail)
    sent = world.client.get(GO_PATH, follow_redirects=False)
    assert sent.status_code == 503
    assert sent.headers["content-type"].startswith("text/html")
    assert "Not available" in sent.text and SENTINEL not in sent.text
    assert "location" not in sent.headers
    assert_page_headers(sent)


def test_head_does_nothing_on_any_page_route(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []
    flow, publisher = world.strava().connect, world.strava().publisher
    real_page = flow.page

    def spy(name: str) -> Callable[..., Any]:
        def record(*args: object, **kwargs: object) -> None:
            calls.append(name)
            raise AssertionError(name)

        return record

    monkeypatch.setattr(publisher, "resolve_link", spy("resolve_link"))
    monkeypatch.setattr(flow, "callback", spy("callback"))
    started = started_session(world)
    monkeypatch.setattr(flow, "page", spy("page"))
    for path in (
        GO_PATH,
        f"{CONNECT_PAGE}?code={started.user_code}",
        f"{CALLBACK}?state=s",
    ):
        sent = world.client.head(path)
        assert sent.status_code == 405
        assert sent.headers["allow"] == "GET"
        assert_page_headers(sent)
    assert calls == [] and world.outbound.calls == []
    # the session was not claimed by the HEAD request
    monkeypatch.setattr(flow, "page", real_page)
    first = open_page(world, started.user_code)
    assert first.status_code == 200 and "set-cookie" in first.headers


# --- /privacy and /robots.txt ------------------------------------------------


def test_the_privacy_page_is_served_with_the_policy_and_the_operator(
    world: World,
) -> None:
    sent = world.client.get("/privacy")
    assert sent.status_code == 200
    assert_page_headers(sent)
    for heading in POLICY_HEADINGS:
        assert html.escape(heading) in sent.text
    operator = world.strava().operator
    assert operator.name in sent.text and operator.support_contact in sent.text


@pytest.mark.parametrize("links", ["activity", "relay"])
def test_the_pages_follow_the_configured_link_setting(
    make_world: Callable[..., World], links: str
) -> None:
    w = make_world(links=links)
    setting = LinkSetting(links)
    other = (
        LinkSetting.RELAY if setting is LinkSetting.ACTIVITY else LinkSetting.ACTIVITY
    )
    operator = w.strava().operator
    assert privacy_page(operator, setting).html != privacy_page(operator, other).html
    assert w.client.get("/privacy").text == privacy_page(operator, setting).html
    started = started_session(w)
    shown = open_page(w, started.user_code).text
    own = [html.escape(p) for p in consent_text(setting)]
    foreign = [
        html.escape(p) for p in consent_text(other) if p not in consent_text(setting)
    ]
    assert foreign  # the two settings do differ in the consent text
    assert all(p in shown for p in own)
    assert not any(p in shown for p in foreign)


@pytest.mark.parametrize("links", ["activity", "relay"])
def test_robots_disallows_the_link_while_strava_is_configured(
    make_world: Callable[..., World], links: str
) -> None:
    sent = make_world(links=links).client.get("/robots.txt")
    assert sent.status_code == 200
    assert sent.headers["content-type"].startswith("text/plain")
    assert sent.text == "User-agent: *\nDisallow: /go/\n"


@pytest.mark.parametrize(
    "path",
    ["/robots.txt", "/privacy", CONNECT_PAGE, CALLBACK, GO_PATH, HOOK],
)
def test_an_unconfigured_relay_serves_none_of_the_strava_paths(
    make_world: Callable[..., World], path: str
) -> None:
    w = make_world(strava=False)
    sent = w.client.get(path)
    assert sent.status_code == 404
    assert decoded(sent).code is RelayCode.NOT_OFFERED
    assert "text/html" not in sent.headers["content-type"]
    assert w.client.get("/robots.txt").text == sent.text  # no robots body either


@pytest.mark.parametrize("method", ["POST", "HEAD"])
def test_an_unconfigured_relay_answers_a_webhook_post_or_head_as_an_unknown_path(
    make_world: Callable[..., World], method: str
) -> None:
    w = make_world(strava=False)
    sent = w.client.request(method, HOOK, content=b"{}")
    unknown = w.client.request(method, "/strava/webhook/unknown", content=b"{}")
    assert sent.status_code == 404
    assert (sent.status_code, sent.headers["content-type"], sent.text) == (
        unknown.status_code,
        unknown.headers["content-type"],
        unknown.text,
    )
    if method == "POST":
        assert decoded(sent).code is RelayCode.NOT_OFFERED


def test_the_served_connect_page_path_is_the_shared_helpers_path(world: World) -> None:
    started = started_session(world)
    path = connect_page_path(STRAVA, started.user_code)
    assert path.split("?", 1)[0] == CONNECT_PAGE
    sent = world.client.get(path)
    assert sent.status_code == 200
    assert "text/html" in sent.headers["content-type"]


# --- the page text never carries what Strava returned -------------------------


def test_no_page_carries_a_sentinel_the_scripted_strava_returned(
    world: World,
) -> None:
    pages: list[Any] = []
    # a grant whose every field carries the sentinel, then a failed exchange
    started, cookie, state = claimed(world)
    hostile = grant_body("A1")
    hostile.update(
        firstname=SENTINEL,
        message=SENTINEL,
        athlete={"id": 90210, "username": SENTINEL},
    )
    world.outbound.expect(
        "POST", f"{OAUTH}/token", reply(200, hostile, {"X-Note": SENTINEL})
    )
    pages.append(
        world.client.get(
            f"{CALLBACK}?state={state}&code=c&scope={FULL}",
            headers=cookie_header(cookie),
        )
    )
    _, cookie2, state2 = claimed(world)
    world.outbound.expect(
        "POST",
        f"{OAUTH}/token",
        reply(
            400,
            {"message": SENTINEL, "errors": [{"code": SENTINEL}]},
            {"X-Note": SENTINEL},
        ),
    )
    pages.append(
        world.client.get(
            f"{CALLBACK}?state={state2}&code=c&scope={FULL}",
            headers=cookie_header(cookie2),
        )
    )
    # values Strava puts on the redirect itself
    _, cookie3, state3 = claimed(world)
    pages.append(
        world.client.get(
            f"{CALLBACK}?state={state3}&error={SENTINEL}&scope={SENTINEL}&code={SENTINEL}",
            headers=cookie_header(cookie3),
        )
    )
    # the link, over a listing whose every field carries the sentinel
    posted(world)
    hostile_entry = {**entry(), "name": SENTINEL, "description": SENTINEL}
    world.script_list(hostile_entry)
    pages.append(world.client.get(GO_PATH, follow_redirects=False))
    world.script_list(hostile_entry, {**entry(ACTIVITY_ID + 1), "name": SENTINEL})
    pages.append(world.client.get(GO_PATH, follow_redirects=False))
    world.outbound.expect(
        "GET", LIST_URL, reply(500, SENTINEL.encode(), {"X-Note": SENTINEL})
    )
    pages.append(world.client.get(GO_PATH, follow_redirects=False))
    pages.append(world.client.get("/privacy"))
    # every scripted answer was served, so the sentinel did reach the relay
    assert world.outbound.unserved() == 0
    assert [p.status_code for p in pages] == [200, 200, 200, 302, 404, 404, 200]
    assert "Connected" in pages[0].text and "Not connected" in pages[1].text
    assert "Not connected" in pages[2].text
    for sent in pages:
        assert SENTINEL not in sent.text
        assert SENTINEL not in str(dict(sent.headers))


# --- the webhook -------------------------------------------------------------


def connect_athlete(w: World) -> None:
    w.strava().custody.store_grant(
        w.principal, Grant("access-tok", "refresh-tok", 1_700_000_040 + 86_400, ATHLETE)
    )
    assert w.store.get_connection(w.principal, STRAVA) is not None


def test_the_subscription_validation_echoes_the_challenge(world: World) -> None:
    sent = world.client.get(
        HOOK,
        params={
            "hub.mode": "subscribe",
            "hub.challenge": "c-123",
            "hub.verify_token": SECRET,
        },
    )
    assert sent.status_code == 200
    assert sent.json() == {"hub.challenge": "c-123"}
    assert world.outbound.calls == []


@pytest.mark.parametrize(
    "params",
    [
        {
            "hub.mode": "subscribe",
            "hub.challenge": "c",
            "hub.verify_token": SECRET + "x",
        },
        {"hub.mode": "unsubscribe", "hub.challenge": "c", "hub.verify_token": SECRET},
        {"hub.mode": "subscribe", "hub.verify_token": SECRET},
        {"hub.mode": "subscribe", "hub.challenge": "c"},
        {},
    ],
)
def test_a_validation_that_is_not_exactly_a_subscription_is_not_found(
    world: World, params: dict[str, str]
) -> None:
    sent = world.client.get(HOOK, params=params)
    assert sent.status_code == 404
    assert decoded(sent).code is RelayCode.NOT_OFFERED


def test_the_challenge_is_bounded(world: World) -> None:
    def ask(size: int) -> Any:
        return world.client.get(
            HOOK,
            params={
                "hub.mode": "subscribe",
                "hub.challenge": "c" * size,
                "hub.verify_token": SECRET,
            },
        )

    assert ask(256).status_code == 200
    assert ask(257).status_code == 404


def test_a_wrong_secret_is_not_found_like_any_unknown_path(world: World) -> None:
    unknown = world.client.get("/strava/nothing-here")
    for wrong in (SECRET[:-1] + "u", SECRET[:-1], SECRET + "t", "x"):
        sent = world.client.get(f"/strava/webhook/{wrong}")
        assert sent.status_code == 404
        assert sent.content == unknown.content
    post = world.client.post(f"/strava/webhook/{'u' * 40}", content=DEAUTH)
    assert post.status_code == 404 and post.content == unknown.content


def test_the_secret_is_compared_in_constant_time(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[tuple[bytes, bytes]] = []
    real = hmac.compare_digest

    def spy(a: bytes, b: bytes) -> bool:
        seen.append((a, b))
        return real(a, b)

    monkeypatch.setattr(hmac, "compare_digest", spy)
    world.client.get(f"/strava/webhook/{'w' * 40}")
    assert seen == [(b"w" * 40, SECRET.encode())]


def test_a_wrong_secret_counts_against_the_client_and_a_right_one_does_not(
    make_world: Callable[..., World],
) -> None:
    w = make_world(client_limit=2)
    for _ in range(5):  # right-secret requests are never counted
        assert w.client.post(HOOK, content=b"{}").status_code == 200
    wrong = f"/strava/webhook/{'u' * 40}"
    assert [w.client.get(wrong).status_code for _ in range(3)] == [404, 404, 429]
    limited = decoded(w.client.get(wrong))
    assert limited.code is RelayCode.RATE_LIMITED
    # the client is over its limit, yet the right secret is still served
    assert w.client.post(HOOK, content=DEAUTH).status_code == 200
    # and a page route from the same client is refused
    assert w.client.get("/privacy").status_code == 429


def test_a_deauthorization_event_forgets_the_account(world: World) -> None:
    connect_athlete(world)
    sent = world.client.post(HOOK, content=DEAUTH)
    assert sent.status_code == 200
    assert sent.content == b""
    assert world.store.get_connection(world.principal, STRAVA) is None
    assert world.outbound.calls == []


def test_an_event_at_a_wrong_secret_changes_nothing(world: World) -> None:
    connect_athlete(world)
    sent = world.client.post(f"/strava/webhook/{'u' * 40}", content=DEAUTH)
    assert sent.status_code == 404
    assert world.store.get_connection(world.principal, STRAVA) is not None


@pytest.mark.parametrize(
    "body",
    [
        b"",
        b"not json",
        json.dumps(
            {
                "object_type": "activity",
                "owner_id": 90210,
                "updates": {"authorized": "false"},
            }
        ).encode(),
        json.dumps(
            {
                "object_type": "athlete",
                "owner_id": 90210,
                "updates": {"authorized": "true"},
            }
        ).encode(),
        json.dumps(
            {
                "object_type": "athlete",
                "owner_id": 55,
                "updates": {"authorized": "false"},
            }
        ).encode(),
    ],
)
def test_every_other_event_is_acknowledged_and_ignored(
    world: World, body: bytes
) -> None:
    connect_athlete(world)
    sent = world.client.post(HOOK, content=body)
    assert sent.status_code == 200 and sent.content == b""
    assert world.store.get_connection(world.principal, STRAVA) is not None


def test_an_event_of_the_largest_accepted_size_is_still_read(world: World) -> None:
    connect_athlete(world)
    padded = DEAUTH[:-1] + b" " * (MAX_EVENT_BYTES - len(DEAUTH)) + b"}"
    assert len(padded) == MAX_EVENT_BYTES
    assert world.client.post(HOOK, content=padded).status_code == 200
    assert world.store.get_connection(world.principal, STRAVA) is None


def test_an_event_over_the_bound_is_refused_at_admission_not_acknowledged(
    world: World,
) -> None:
    connect_athlete(world)
    padded = DEAUTH[:-1] + b" " * (MAX_EVENT_BYTES + 1 - len(DEAUTH)) + b"}"
    assert len(padded) == MAX_EVENT_BYTES + 1
    sent = world.client.post(HOOK, content=padded)
    assert sent.status_code == 413
    assert decoded(sent).code is RelayCode.REQUEST_TOO_LARGE
    assert world.store.get_connection(world.principal, STRAVA) is not None


def test_the_secret_is_in_no_log_record(
    world: World, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO):
        world.client.get(
            HOOK,
            params={
                "hub.mode": "subscribe",
                "hub.challenge": "c",
                "hub.verify_token": SECRET,
            },
        )
        world.client.post(HOOK, content=b"{}")
        world.client.get(f"/strava/webhook/{'u' * 40}")
    ours = [r for r in caplog.records if r.name == "fitdocs_relay.app"]
    assert len(ours) == 3
    for record in ours:
        assert record.route == "/strava/webhook/{secret}"  # type: ignore[attr-defined]
        assert SECRET not in json.dumps(record.__dict__, default=str)
        assert "u" * 40 not in json.dumps(record.__dict__, default=str)
