"""The Strava envelope routes and `/go/` (strava-publish 4.2), on both backends.

Every app here is `build_app` over `core_routes` with real services built by
`make_services`; Strava is the scripted outbound, so a request nobody scripted
raises `UnscriptedCall` and the recorded calls are the count of Strava requests.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass, replace
from typing import Any
from urllib.parse import parse_qs, urlsplit

import pytest
from starlette.testclient import TestClient
from tests.strava.scripted_strava import ScriptedOutbound, reply
from tests.strava.test_connect import FULL, cookie_value, grant_body
from tests.strava.test_publish import (
    ACTIVITY_ID,
    API,
    FACTS,
    LIST_URL,
    PUB_ID,
    UPDATE_URL,
    WEB,
    entry,
)
from tests.strava.test_publish_upload import (
    NEW_ID,
    STATUS_URL,
    UPLOAD_ID,
    UPLOAD_URL,
)
from tests.test_config_strava import env as strava_env

from fitdocs_relay.app import RelayServices, build_app, make_services
from fitdocs_relay.config import load_config
from fitdocs_relay.routes import core_routes
from fitdocs_relay.shared.outcomes import PublishCode
from fitdocs_relay.shared.relay_codes import RelayCode
from fitdocs_relay.shared.relay_envelope import (
    MAX_REQUEST_BYTES,
    decode_answer,
    encode_request,
    parse_started,
)
from fitdocs_relay.shared.relay_targets import (
    ACTION_CONNECT,
    ACTION_CONNECT_POLL,
    ACTION_DISCONNECT,
    ACTION_PUBLISH,
    ACTION_UPLOAD,
    LINK_FIELD,
    PUBLISH_OUTCOMES,
    STRAVA,
    UPLOAD_OUTCOMES,
    link_path,
    publish_fields,
    target_route,
    upload_fields,
)
from fitdocs_relay.storage.interface import Storage
from fitdocs_relay.strava.api import Grant
from fitdocs_relay.strava.connect import (
    CONNECT_EXPIRES_IN_S,
    CONNECT_INTERVAL_S,
    CONNECTION_TOKEN_LABEL,
    ShowConsent,
)
from fitdocs_relay.strava.pages import PAGE_HEADERS

OAUTH = "https://oauth.example/oauth"
NOW = 1_700_000_040
DAY = 86_400
CLIENT = ("203.0.113.9", 4711)
HUGE = "1000000,1000000"
ROUTES = {
    action: target_route(STRAVA, action)
    for action in (
        ACTION_CONNECT,
        ACTION_CONNECT_POLL,
        ACTION_PUBLISH,
        ACTION_UPLOAD,
        ACTION_DISCONNECT,
    )
}
PUBLISH_PATH = ROUTES[ACTION_PUBLISH]
UPLOAD_PATH = ROUTES[ACTION_UPLOAD]
GO_PATH = link_path(PUB_ID)
FIT = b"\x0e\x10\x00\x00\x00\x00\x00\x00.FIT-route-test-payload"  # a FIT header
POST_ROUTES = pytest.mark.parametrize("action", list(ROUTES))
P = PublishCode


def clock() -> int:
    return NOW


@dataclass
class World:
    client: TestClient
    services: RelayServices
    outbound: ScriptedOutbound
    store: Storage
    token: str
    principal: str

    def strava(self) -> Any:
        assert self.services.strava is not None
        return self.services.strava

    def post(self, path: str, fields: dict[str, object] | bytes | None = None) -> Any:
        body = fields if isinstance(fields, bytes) else encode_request(fields or {})
        return self.client.post(path, content=body, headers=self.auth())

    def auth(self, token: str | None = None) -> dict[str, str]:
        return {"Authorization": f"Bearer {token or self.token}"}

    def connect(self, *, refresh: str | None = "refresh-tok") -> None:
        assert refresh is not None
        self.strava().custody.store_grant(
            self.principal, Grant("access-tok", refresh, NOW + DAY, "who-ann")
        )

    def script_list(self, *entries: dict[str, object]) -> None:
        self.outbound.expect("GET", LIST_URL, reply(200, list(entries)))


@pytest.fixture
def make_world(
    database_target: Any, open_full_storage: Callable[[], Storage]
) -> Iterator[Callable[..., World]]:
    entered: list[TestClient] = []

    def make(
        *,
        strava: bool = True,
        links: str = "activity",
        token_limit: int | None = None,
        client_limit: int | None = None,
    ) -> World:
        environ = (
            strava_env(
                {
                    "FITDOCS_RELAY_STRAVA_API_URL": API,
                    "FITDOCS_RELAY_STRAVA_OAUTH_URL": OAUTH,
                    "FITDOCS_RELAY_STRAVA_WEB_URL": WEB,
                    "FITDOCS_RELAY_STRAVA_LINKS": links,
                    "FITDOCS_RELAY_STRAVA_RATE_LIMIT": HUGE,
                    "FITDOCS_RELAY_STRAVA_READ_RATE_LIMIT": HUGE,
                }
            )
            if strava
            else {
                "FITDOCS_RELAY_DATABASE_URL": "sqlite:///unused.db",
                "FITDOCS_RELAY_TOKEN_PEPPER": "p" * 43,
            }
        )
        loaded = load_config(environ)
        config = replace(
            loaded,
            database=database_target,
            token_limit_per_minute=token_limit or 100_000,
            client_limit_per_minute=client_limit or 100_000,
        )
        store = open_full_storage()
        outbound = ScriptedOutbound()
        services = make_services(
            config,
            store,
            clock=clock,
            outbound=outbound,
            monotonic=lambda: 0.0,
            sleep=lambda seconds: None,
        )
        app = build_app(services, core_routes(services))
        client = TestClient(app, client=CLIENT)
        client.__enter__()
        entered.append(client)
        minted = services.tokens.mint(principal_id=None, label=None)
        return World(
            client, services, outbound, store, minted.token, minted.principal_id
        )

    yield make
    for client in entered:
        client.__exit__(None, None, None)


@pytest.fixture
def world(make_world: Callable[..., World]) -> World:
    return make_world()


def decoded(sent: Any) -> Any:
    return decode_answer(sent.content)


def publish_body(**changes: object) -> dict[str, object]:
    return publish_fields(FACTS) | changes


def upload_body() -> dict[str, object]:
    return upload_fields(FACTS, FIT)


# --- an unconfigured relay --------------------------------------------------


@POST_ROUTES
def test_an_unconfigured_relay_answers_not_offered_on_each_route(
    make_world: Callable[..., World], action: str
) -> None:
    w = make_world(strava=False)
    assert w.services.strava is None  # the decoy: a valid token is presented
    sent = w.post(ROUTES[action])
    assert sent.status_code == 404
    assert decoded(sent).code is RelayCode.NOT_OFFERED


def test_an_unconfigured_relay_does_not_serve_the_link(
    make_world: Callable[..., World],
) -> None:
    w = make_world(strava=False)
    sent = w.client.get(GO_PATH, follow_redirects=False)
    assert sent.status_code == 404
    assert decoded(sent).code is RelayCode.NOT_OFFERED


# --- authentication and the per-token limit, on every route -------------------


@POST_ROUTES
def test_each_route_requires_a_token_and_does_nothing_without_one(
    world: World, action: str
) -> None:
    sent = world.client.post(ROUTES[action], content=encode_request({}))
    assert sent.status_code == 401
    assert decoded(sent).code is RelayCode.TOKEN_MISSING
    assert world.outbound.calls == []


@POST_ROUTES
def test_each_route_refuses_a_revoked_token(world: World, action: str) -> None:
    minted = world.services.tokens.mint(principal_id=world.principal, label=None)
    parts = minted.token_id
    world.services.tokens.revoke(parts)
    sent = world.client.post(
        ROUTES[action], content=encode_request({}), headers=world.auth(minted.token)
    )
    assert decoded(sent).code is RelayCode.TOKEN_REVOKED


@POST_ROUTES
def test_each_route_counts_the_token_against_its_own_limit(
    make_world: Callable[..., World], action: str
) -> None:
    w = make_world(token_limit=1)
    first = w.post(ROUTES[action], {"junk": 1})  # malformed, but counted
    second = w.post(ROUTES[action], {"junk": 1})
    assert decoded(first).code is not RelayCode.RATE_LIMITED
    assert second.status_code == 429
    assert decoded(second).code is RelayCode.RATE_LIMITED
    assert "retry-after" in second.headers


# --- connect ----------------------------------------------------------------


def test_connect_starts_a_session_and_answers_connect_started(world: World) -> None:
    sent = world.post(ROUTES[ACTION_CONNECT])
    assert sent.status_code == 200
    answer = decoded(sent)
    assert answer.code is RelayCode.CONNECT_STARTED
    started = parse_started(answer.data)
    assert started.interval_s == CONNECT_INTERVAL_S
    assert started.expires_in_s == CONNECT_EXPIRES_IN_S
    # The session exists: the page for the code is the consent page.
    shown = world.strava().connect.page(started.user_code, None)
    assert isinstance(shown, ShowConsent)
    assert sent.headers["cache-control"] == "no-store"


def test_connect_starts_the_session_for_the_presenting_principal(
    world: World,
) -> None:
    started = parse_started(decoded(world.post(ROUTES[ACTION_CONNECT])).data)
    other = world.services.tokens.mint(principal_id=None, label=None)
    assert other.principal_id != world.principal
    polled = world.client.post(
        ROUTES[ACTION_CONNECT_POLL],
        content=encode_request({"poll_secret": started.poll_secret}),
        headers=world.auth(other.token),
    )
    assert decoded(polled).code is RelayCode.CONNECT_EXPIRED  # not theirs
    own = world.post(ROUTES[ACTION_CONNECT_POLL], {"poll_secret": started.poll_secret})
    assert decoded(own).code is RelayCode.CONNECT_PENDING


def test_connect_takes_an_empty_request_only(world: World) -> None:
    sent = world.post(ROUTES[ACTION_CONNECT], {"email": "a@b.example"})
    assert sent.status_code == 400
    assert decoded(sent).code is RelayCode.REQUEST_MALFORMED


# --- poll -------------------------------------------------------------------


def started_session(world: World) -> Any:
    return parse_started(decoded(world.post(ROUTES[ACTION_CONNECT])).data)


def complete_in_browser(
    world: World, started: Any, *, code: str | None = "the-code"
) -> None:
    flow = world.strava().connect
    shown = flow.page(started.user_code, None)
    assert isinstance(shown, ShowConsent) and shown.set_cookie is not None
    state = parse_qs(urlsplit(shown.authorize_url).query)["state"][0]
    if code is not None:
        world.outbound.expect("POST", f"{OAUTH}/token", reply(200, grant_body("A1")))
    flow.callback(
        state=state,
        code=code,
        scope=FULL,
        error=None if code is not None else "access_denied",
        cookie=cookie_value(shown.set_cookie),
    )


def poll(world: World, started: Any) -> Any:
    return world.post(ROUTES[ACTION_CONNECT_POLL], {"poll_secret": started.poll_secret})


def test_poll_answers_connect_pending_with_no_data_before_the_browser_step(
    world: World,
) -> None:
    sent = poll(world, started_session(world))
    assert sent.status_code == 200
    answer = decoded(sent)
    assert (answer.code, answer.data) == (RelayCode.CONNECT_PENDING, {})


def test_poll_issues_the_connection_token_once_then_expires(world: World) -> None:
    started = started_session(world)
    complete_in_browser(world, started)
    first = poll(world, started)
    assert first.status_code == 200
    answer = decoded(first)
    assert answer.code is RelayCode.CONNECT_GRANTED
    assert set(answer.data) == {"token"}
    authed = world.services.tokens.authenticate(answer.data["token"])
    assert not isinstance(authed, RelayCode)
    assert authed.principal_id == world.principal
    again = poll(world, started)
    assert again.status_code == 410
    assert decoded(again).code is RelayCode.CONNECT_EXPIRED


def test_poll_answers_connect_refused_when_the_athlete_declined(
    world: World,
) -> None:
    started = started_session(world)
    complete_in_browser(world, started, code=None)
    sent = poll(world, started)
    assert sent.status_code == 403
    answer = decoded(sent)
    assert (answer.code, answer.data) == (RelayCode.CONNECT_REFUSED, {})


def test_poll_of_an_unknown_secret_answers_connect_expired(world: World) -> None:
    started = started_session(world)
    other = "A" * len(started.poll_secret)
    assert other != started.poll_secret
    sent = world.post(ROUTES[ACTION_CONNECT_POLL], {"poll_secret": other})
    assert sent.status_code == 410
    assert decoded(sent).code is RelayCode.CONNECT_EXPIRED


@pytest.mark.parametrize(
    "fields",
    [{}, {"poll_secret": "short"}, {"poll_secret": 7}, {"poll_secret": "x", "a": 1}],
)
def test_poll_refuses_a_request_that_is_not_exactly_a_poll_secret(
    world: World, fields: dict[str, object]
) -> None:
    sent = world.post(ROUTES[ACTION_CONNECT_POLL], fields)
    assert sent.status_code == 400
    assert decoded(sent).code is RelayCode.REQUEST_MALFORMED


# --- publish ----------------------------------------------------------------


def test_publish_posts_and_answers_ok_posted_with_the_activity_link(
    world: World,
) -> None:
    world.connect()
    world.script_list(entry())
    world.outbound.expect("PUT", UPDATE_URL, reply(200, {}))
    sent = world.post(PUBLISH_PATH, publish_body())
    assert sent.status_code == 200
    answer = decoded(sent)
    assert (answer.code, answer.outcome) == (RelayCode.OK, "posted")
    assert answer.data == {LINK_FIELD: f"{WEB}/activities/{ACTIVITY_ID}"}


def test_publish_posted_carries_no_link_under_the_relay_setting(
    make_world: Callable[..., World],
) -> None:
    w = make_world(links="relay")
    w.connect()
    w.script_list(entry())
    w.outbound.expect("PUT", UPDATE_URL, reply(200, {}))
    answer = decoded(w.post(PUBLISH_PATH, publish_body()))
    assert (answer.code, answer.outcome) == (RelayCode.OK, "posted")
    assert answer.data == {}


def test_publish_with_no_match_answers_not_found_and_no_link(world: World) -> None:
    world.connect()
    world.script_list()
    answer = decoded(world.post(PUBLISH_PATH, publish_body()))
    assert (answer.code, answer.outcome, answer.data) == (
        RelayCode.OK,
        "not_found",
        {},
    )


def test_publish_without_a_connection_answers_not_connected_with_no_call(
    world: World,
) -> None:
    answer = decoded(world.post(PUBLISH_PATH, publish_body()))
    assert (answer.code, answer.outcome, answer.data) == (
        RelayCode.OK,
        "not_connected",
        {},
    )
    assert world.outbound.calls == []


def test_publish_without_facts_answers_activity_facts_missing_with_no_call(
    world: World,
) -> None:
    world.connect()
    sent = world.post(PUBLISH_PATH, publish_body(elapsed_s=None, distance_m=None))
    assert decoded(sent).outcome == "activity_facts_missing"
    assert world.outbound.calls == []


def test_a_strava_limit_is_an_outcome_not_a_rate_limited_answer(
    world: World,
) -> None:
    world.connect()
    world.outbound.expect("GET", LIST_URL, reply(429))
    sent = world.post(PUBLISH_PATH, publish_body())
    answer = decoded(sent)
    assert (sent.status_code, answer.code) == (200, RelayCode.OK)
    assert (answer.outcome, answer.data) == ("rate_limited", {})
    assert "retry-after" not in sent.headers


def test_publish_with_two_matches_answers_ambiguous(world: World) -> None:
    world.connect()
    world.script_list(entry(), entry(ACTIVITY_ID + 1))
    answer = decoded(world.post(PUBLISH_PATH, publish_body()))
    assert (answer.outcome, answer.data) == ("ambiguous", {})


def test_the_publish_route_answers_the_publish_vocabulary_only(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    publisher = world.strava().publisher
    assert P.UPLOADED.value not in PUBLISH_OUTCOMES  # the decoy is outside the set
    monkeypatch.setattr(publisher, "publish", lambda principal, facts: P.UPLOADED)
    world.client.raise_server_exceptions = False
    sent = world.post(PUBLISH_PATH, publish_body())
    assert sent.status_code == 500
    answer = decoded(sent)
    assert (answer.code, answer.outcome) == (RelayCode.RELAY_FAILURE, None)


def test_the_upload_route_answers_the_upload_vocabulary_only(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    publisher = world.strava().publisher
    assert P.NOT_FOUND.value not in UPLOAD_OUTCOMES
    monkeypatch.setattr(publisher, "upload", lambda principal, facts, fit: P.NOT_FOUND)
    world.client.raise_server_exceptions = False
    sent = world.post(UPLOAD_PATH, upload_body())
    assert sent.status_code == 500
    assert decoded(sent).code is RelayCode.RELAY_FAILURE


def test_the_publish_route_serves_a_member_of_its_set_the_upload_route_lacks(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    # not_found is a publish outcome; routing it through the publish route works,
    # so the check above refuses by membership and not by blanket.
    assert P.NOT_FOUND.value in PUBLISH_OUTCOMES
    monkeypatch.setattr(
        world.strava().publisher, "publish", lambda principal, facts: P.NOT_FOUND
    )
    assert decoded(world.post(PUBLISH_PATH, publish_body())).outcome == "not_found"


def test_an_unexpected_exception_before_the_upload_answers_relay_failure(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(principal: str, facts: object, fit: bytes) -> Any:
        raise RuntimeError("storage went away")

    monkeypatch.setattr(world.strava().publisher, "upload", boom)
    world.client.raise_server_exceptions = False
    sent = world.post(UPLOAD_PATH, upload_body())
    assert sent.status_code == 500
    assert decoded(sent).code is RelayCode.RELAY_FAILURE


@pytest.mark.parametrize(
    "changes",
    [
        {"publication_id": "nope"},
        {"start": "2026-03-01T10:00:00"},
        {"sport": "run"},
        {"title": ""},
        {"elapsed_s": -1},
    ],
)
def test_publish_refuses_fields_out_of_format(
    world: World, changes: dict[str, object]
) -> None:
    sent = world.post(PUBLISH_PATH, publish_body(**changes))
    assert sent.status_code == 400
    assert decoded(sent).code is RelayCode.REQUEST_MALFORMED
    assert world.outbound.calls == []


def test_publish_refuses_a_missing_field_and_an_extra_one(world: World) -> None:
    short = publish_body()
    del short["description"]
    for fields in (short, publish_body(fit="AAAA"), publish_body(extra=1)):
        sent = world.post(PUBLISH_PATH, fields)
        assert decoded(sent).code is RelayCode.REQUEST_MALFORMED


# --- upload -----------------------------------------------------------------


def script_new_upload(world: World) -> None:
    world.script_list()
    world.outbound.expect(
        "POST", UPLOAD_URL, reply(201, {"id": UPLOAD_ID, "error": None})
    )
    world.outbound.expect(
        "GET",
        STATUS_URL,
        reply(200, {"id": UPLOAD_ID, "error": None, "activity_id": NEW_ID}),
    )


def test_upload_creates_the_activity_and_answers_uploaded_with_its_link(
    world: World,
) -> None:
    world.connect()
    script_new_upload(world)
    sent = world.post(UPLOAD_PATH, upload_body())
    assert sent.status_code == 200
    answer = decoded(sent)
    assert (answer.code, answer.outcome) == (RelayCode.OK, "uploaded")
    assert answer.data == {LINK_FIELD: f"{WEB}/activities/{NEW_ID}"}
    (sent_up,) = [c for c in world.outbound.calls if c.request.url == UPLOAD_URL]
    assert sent_up.request.body is not None
    assert FIT in sent_up.request.body  # the decoded file, not the request text


def test_upload_uploaded_carries_no_link_under_the_relay_setting(
    make_world: Callable[..., World],
) -> None:
    w = make_world(links="relay")
    w.connect()
    script_new_upload(w)
    answer = decoded(w.post(UPLOAD_PATH, upload_body()))
    assert (answer.code, answer.outcome, answer.data) == (RelayCode.OK, "uploaded", {})


def test_upload_that_updates_a_match_answers_posted_with_the_link(
    world: World,
) -> None:
    world.connect()
    world.script_list(entry())
    world.outbound.expect("PUT", UPDATE_URL, reply(200, {}))
    answer = decoded(world.post(UPLOAD_PATH, upload_body()))
    assert answer.outcome == "posted"
    assert answer.data == {LINK_FIELD: f"{WEB}/activities/{ACTIVITY_ID}"}


def test_upload_posted_carries_no_link_under_the_relay_setting(
    make_world: Callable[..., World],
) -> None:
    w = make_world(links="relay")
    w.connect()
    w.script_list(entry())
    w.outbound.expect("PUT", UPDATE_URL, reply(200, {}))
    answer = decoded(w.post(UPLOAD_PATH, upload_body()))
    assert (answer.outcome, answer.data) == ("posted", {})


def test_an_unconfirmed_upload_is_an_upload_outcome_without_a_link(
    world: World,
) -> None:
    world.connect()
    world.script_list()
    world.outbound.expect(
        "POST", UPLOAD_URL, reply(201, {"id": UPLOAD_ID, "error": None})
    )
    world.outbound.expect("GET", STATUS_URL, reply(500))
    answer = decoded(world.post(UPLOAD_PATH, upload_body()))
    assert (answer.code, answer.outcome, answer.data) == (
        RelayCode.OK,
        "unconfirmed",
        {},
    )


def test_upload_without_a_connection_answers_not_connected(world: World) -> None:
    answer = decoded(world.post(UPLOAD_PATH, upload_body()))
    assert (answer.outcome, answer.data) == ("not_connected", {})
    assert world.outbound.calls == []


@pytest.mark.parametrize(
    "changes",
    [{"fit": "not base64!"}, {"fit": "AAAA"}, {"fit": 5}, {"publication_id": "x"}],
)
def test_upload_refuses_a_file_that_is_not_a_fit_file_and_bad_facts(
    world: World, changes: dict[str, object]
) -> None:
    sent = world.post(UPLOAD_PATH, upload_body() | changes)
    assert sent.status_code == 400
    assert decoded(sent).code is RelayCode.REQUEST_MALFORMED
    assert world.outbound.calls == []


def test_upload_refuses_a_request_without_the_file(world: World) -> None:
    sent = world.post(UPLOAD_PATH, publish_body())
    assert decoded(sent).code is RelayCode.REQUEST_MALFORMED


# --- the body bound, per route ----------------------------------------------


def padded(fields: dict[str, object], size: int) -> bytes:
    raw = encode_request(fields, max_bytes=size)
    return raw + b" " * (size - len(raw))


def test_a_70_kib_body_is_refused_on_publish_and_accepted_on_upload(
    world: World,
) -> None:
    size = 70 * 1024
    assert size > MAX_REQUEST_BYTES
    refused = world.post(PUBLISH_PATH, padded(publish_body(), size))
    assert refused.status_code == 413
    assert decoded(refused).code is RelayCode.REQUEST_TOO_LARGE
    accepted = world.post(UPLOAD_PATH, padded(upload_body(), size))
    assert accepted.status_code == 200
    answer = decoded(accepted)
    assert (answer.code, answer.outcome) == (RelayCode.OK, "not_connected")


def test_the_other_envelope_routes_keep_the_default_bound(world: World) -> None:
    for action in (ACTION_CONNECT, ACTION_CONNECT_POLL, ACTION_DISCONNECT):
        sent = world.post(ROUTES[action], padded({}, 70 * 1024))
        assert sent.status_code == 413


# --- disconnect -------------------------------------------------------------


def test_disconnect_with_no_connection_answers_ok_and_calls_nothing(
    world: World,
) -> None:
    assert world.store.get_connection(world.principal, STRAVA) is None
    sent = world.post(ROUTES[ACTION_DISCONNECT])
    assert sent.status_code == 200
    answer = decoded(sent)
    assert (answer.code, answer.data, answer.outcome) == (RelayCode.OK, {}, None)
    assert world.outbound.calls == []


def connection_token(world: World) -> str:
    prepared = world.services.tokens.prepare(label=CONNECTION_TOKEN_LABEL)
    issued = world.store.issue_connection_token(
        world.principal, STRAVA, prepared.new_token, now=NOW
    )
    assert issued is not None
    return prepared.token


def test_disconnect_revokes_at_strava_deletes_the_connection_and_its_token(
    world: World,
) -> None:
    world.connect()
    token = connection_token(world)
    world.outbound.expect("POST", f"{OAUTH}/revoke", reply(200, {}))
    sent = world.client.post(
        ROUTES[ACTION_DISCONNECT], content=encode_request({}), headers=world.auth(token)
    )
    assert decoded(sent).code is RelayCode.OK
    assert len(world.outbound.calls) == 1
    assert world.store.get_connection(world.principal, STRAVA) is None
    after = world.client.post(
        ROUTES[ACTION_DISCONNECT], content=encode_request({}), headers=world.auth(token)
    )
    assert decoded(after).code is RelayCode.TOKEN_REVOKED


def test_disconnect_answers_ok_and_deletes_when_strava_refuses_the_revoke(
    world: World,
) -> None:
    world.connect()
    token = connection_token(world)
    world.outbound.expect("POST", f"{OAUTH}/revoke", reply(500))
    sent = world.post(
        ROUTES[ACTION_DISCONNECT]
    )  # presents world.token, not the connection's
    assert decoded(sent).code is RelayCode.OK
    assert world.store.get_connection(world.principal, STRAVA) is None
    # only the connection's own token is revoked; the presented token still works
    gone = world.client.post(
        ROUTES[ACTION_DISCONNECT], content=encode_request({}), headers=world.auth(token)
    )
    assert decoded(gone).code is RelayCode.TOKEN_REVOKED
    assert decoded(world.post(ROUTES[ACTION_DISCONNECT])).code is RelayCode.OK


def test_disconnect_takes_an_empty_request_only(world: World) -> None:
    world.connect()
    sent = world.post(ROUTES[ACTION_DISCONNECT], {"all": True})
    assert decoded(sent).code is RelayCode.REQUEST_MALFORMED
    assert world.store.get_connection(world.principal, STRAVA) is not None


# --- /go/ -------------------------------------------------------------------


@pytest.mark.parametrize("links", ["activity", "relay"])
def test_go_redirects_to_the_activity_under_either_link_setting(
    make_world: Callable[..., World], links: str
) -> None:
    w = make_world(links=links)
    w.connect()
    w.script_list(entry())
    w.outbound.expect("PUT", UPDATE_URL, reply(200, {}))
    assert decoded(w.post(PUBLISH_PATH, publish_body())).outcome == "posted"
    w.script_list(entry())
    sent = w.client.get(GO_PATH, follow_redirects=False)
    assert sent.status_code == 302
    assert sent.headers["location"] == f"{WEB}/activities/{ACTIVITY_ID}"
    for name, value in PAGE_HEADERS.items():
        assert sent.headers[name] == value
    assert sent.content == b""


def test_go_of_an_unknown_publication_is_the_not_found_page_with_no_call(
    world: World,
) -> None:
    sent = world.client.get(GO_PATH, follow_redirects=False)
    assert sent.status_code == 404
    assert "location" not in sent.headers
    assert sent.headers["content-type"].startswith("text/html")
    assert world.outbound.calls == []


def test_go_of_a_malformed_id_is_not_found_without_a_lookup(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    looked_up: list[str] = []

    def spy(publication_id: str) -> str:
        looked_up.append(publication_id)
        return "https://elsewhere.example/"

    monkeypatch.setattr(world.strava().publisher, "resolve_link", spy)
    sent = world.client.get("/go/NOT-AN-ID", follow_redirects=False)
    assert sent.status_code == 404
    assert looked_up == []
    # the same spy is reached by a well-formed id, so the lookup was available
    world.client.get(GO_PATH, follow_redirects=False)
    assert looked_up == [PUB_ID]


def test_go_when_strava_limits_the_lookup_is_the_try_later_page(world: World) -> None:
    world.connect()
    world.script_list(entry())
    world.outbound.expect("PUT", UPDATE_URL, reply(200, {}))
    assert decoded(world.post(PUBLISH_PATH, publish_body())).outcome == "posted"
    world.outbound.expect("GET", LIST_URL, reply(429))
    sent = world.client.get(GO_PATH, follow_redirects=False)
    assert sent.status_code == 429
    assert "location" not in sent.headers


def test_go_while_the_relay_is_not_ready_is_the_unavailable_page(
    world: World,
) -> None:
    world.services.ready = False
    sent = world.client.get(GO_PATH, follow_redirects=False)
    assert sent.status_code == 503
    assert world.outbound.calls == []


def test_go_is_rate_limited_per_client(make_world: Callable[..., World]) -> None:
    w = make_world(client_limit=2)
    statuses = [
        w.client.get(GO_PATH, follow_redirects=False).status_code for _ in range(3)
    ]
    assert statuses == [404, 404, 429]
