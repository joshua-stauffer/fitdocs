"""Nothing Strava returns leaves the relay but the landed activity's link
(strava-publish 6.2; Requirements 12.1, 12.2, 12.3, 12.5).

One scripted Strava plants a sentinel in every free-text field and every header
it returns, and distinctive activity and athlete ids.
The relay is driven through connect (start, page, callback, poll), a refresh,
publish, upload, the operator's subscription commands, a disconnect and a
webhook deauthorization, on both backends. Afterwards the sentinel and the
planted ids are searched for in the envelope answers, the pages, the
operator-command reports, the log records the relay wrote and the rows of every
table (a snapshot taken while connected, one after the disconnect and two after
the webhook events). The authorization states, claim cookies, poll secrets,
connection tokens, client secret and webhook secret are searched for in the log
records.
"""

# ruff: noqa: F811
from __future__ import annotations

import json
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from typing import Any
from urllib.parse import urlsplit

import pytest
from tests.conformance.state_support import raw
from tests.strava.scripted_strava import reply
from tests.strava.test_connect import FULL
from tests.strava.test_publish import (
    ACTIVITY_ID,
    API,
    FACTS,
    LIST_URL,
    NOW,
    OAUTH,
    OTHER_ID,
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
from tests.test_strava_pages_routes import cookie_header
from tests.test_strava_routes import (  # noqa: F401  (make_world is a fixture)
    FIT,
    PUBLISH_PATH,
    ROUTES,
    UPLOAD_PATH,
    World,
    make_world,
    started_session,
)

from fitdocs_relay.config import SqliteTarget
from fitdocs_relay.shared.relay_envelope import decode_answer, encode_request
from fitdocs_relay.shared.relay_targets import (
    ACTION_CONNECT_POLL,
    ACTION_DISCONNECT,
    LINK_FIELD,
    publish_fields,
    upload_fields,
)
from fitdocs_relay.strava.cli import webhook_create, webhook_delete, webhook_show
from fitdocs_relay.strava.connect import ShowConsent

SENTINEL = "PLANTED-7f3a91c2-from-strava"
ATHLETE_ID = 7_314_265_901  # distinctive; no test default uses it
DECOY_ID = 6_428_113_575  # an activity in a listing that is never the match
THIRD_ID = "c" * 32
FOURTH_ID = "d" * 32
FIFTH_ID = "e" * 32
HOOK_SECRET = "t" * 40
HOOK = f"/strava/webhook/{HOOK_SECRET}"
CALLBACK = "/strava/callback"
CONNECT_PAGE = "/connect/strava"
SUBSCRIPTION_ID = 5_550_123
HOSTILE_HEADERS = {
    "X-Note": SENTINEL,
    "X-RateLimit-Usage": SENTINEL,
    "X-RateLimit-Limit": SENTINEL,
    "X-ReadRateLimit-Usage": SENTINEL,
    "X-ReadRateLimit-Limit": SENTINEL,
    "Retry-After": SENTINEL,
    "Set-Cookie": f"strava={SENTINEL}",
}
MATCHED_ID = "1" * 32
FAILED_ID = "2" * 32
BOOM_ID = "3" * 32
# every publication id the scenario sends, publish and upload alike
DRIVEN_PUBLICATION_IDS = (
    PUB_ID,
    OTHER_ID,
    THIRD_ID,
    FOURTH_ID,
    FIFTH_ID,
    MATCHED_ID,
    FAILED_ID,
    BOOM_ID,
)
IDS = [ACTIVITY_ID, NEW_ID, DECOY_ID, ATHLETE_ID, UPLOAD_ID, SUBSCRIPTION_ID]


def strava_says(status: int, body: object) -> Any:
    """A Strava answer whose headers are all the sentinel."""
    return reply(status, body, HOSTILE_HEADERS)


def hostile_entry(activity_id: int, **changes: object) -> dict[str, object]:
    """A listing entry whose free-text fields are all the sentinel."""
    return {
        **entry(activity_id, **changes),  # type: ignore[arg-type]
        "name": SENTINEL,
        "description": SENTINEL,
        "athlete": {"id": ATHLETE_ID, "firstname": SENTINEL},
        "map": {"summary_polyline": SENTINEL},
        "external_id": SENTINEL,
        "private_note": SENTINEL,
    }


def hostile_grant(access: str, expires_at: int) -> dict[str, object]:
    return {
        "token_type": SENTINEL,
        "access_token": f"{SENTINEL}-access-{access}",
        "refresh_token": f"{SENTINEL}-refresh-{access}",
        "expires_at": expires_at,
        "expires_in": SENTINEL,
        "scope": SENTINEL,
        "athlete": {
            "id": ATHLETE_ID,
            "username": SENTINEL,
            "firstname": SENTINEL,
            "lastname": SENTINEL,
            "profile": f"https://{SENTINEL}.example/p.jpg",
        },
        "message": SENTINEL,
    }


@dataclass
class Seen:
    """Everything the scenario sent and received, plus what it must not leak."""

    responses: list[tuple[str, Any]] = field(default_factory=list)
    secrets: list[str] = field(default_factory=list)
    reports: list[str] = field(default_factory=list)
    snapshots: list[dict[str, list[str]]] = field(default_factory=list)


def tables(w: World, target: Any) -> dict[str, list[str]]:
    """Every table of the database, each as its sorted rows."""
    if isinstance(target, SqliteTarget):
        sql = (
            "SELECT name FROM sqlite_master WHERE type = 'table' "
            "AND name NOT LIKE 'sqlite_%'"
        )
    else:
        sql = (
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = current_schema() AND table_type = 'BASE TABLE'"
        )
    return {
        str(name): sorted(repr(row) for row in raw(target, f"SELECT * FROM {name}"))
        for (name,) in raw(target, sql)
    }


def present(text: str, needle: str | int) -> bool:
    """Whether `needle` is in `text`; a number only as a whole token."""
    if isinstance(needle, int):
        return re.search(rf"(?<![0-9A-Za-z]){needle}(?![0-9A-Za-z])", text) is not None
    return needle.casefold() in text.casefold()


def log_text(records: list[logging.LogRecord]) -> str:
    formatter = logging.Formatter()
    parts = []
    for record in records:
        parts.append(record.getMessage())
        parts.append(repr(record.__dict__))
        if record.exc_info:
            parts.append(formatter.formatException(record.exc_info))
    return "\n".join(parts)


class Scenario:
    def __init__(self, w: World, target: Any) -> None:
        self.w = w
        self.target = target
        self.seen = Seen()
        self.connection_token = ""

    # --- recording -----------------------------------------------------

    def envelope(self, path: str, fields: dict[str, object] | None = None) -> Any:
        token = self.connection_token or self.w.token
        sent = self.w.client.post(
            path,
            content=encode_request(fields or {}),
            headers={"Authorization": f"Bearer {token}"},
        )
        self.seen.responses.append(("envelope", sent))
        return sent

    def page(self, path: str, headers: dict[str, str] | None = None) -> Any:
        if path.startswith(CONNECT_PAGE):
            self.w.client.cookies.clear()  # each connect is a fresh browser
        sent = self.w.client.get(path, headers=headers or {}, follow_redirects=False)
        self.seen.responses.append(("page", sent))
        return sent

    def snapshot(self) -> dict[str, list[str]]:
        dumped = tables(self.w, self.target)
        self.seen.snapshots.append(dumped)
        return dumped

    # --- the connect flow ------------------------------------------------

    def connect(self, *, expires_at: int) -> None:
        w = self.w
        started = started_session(w)
        self.seen.secrets.append(started.poll_secret)
        shown = self.page(f"{CONNECT_PAGE}?code={started.user_code}")
        assert shown.status_code == 200
        cookie = shown.headers["set-cookie"].split(";")[0].partition("=")[2]
        consent = w.strava().connect.page(started.user_code, cookie)
        assert isinstance(consent, ShowConsent)
        state = urlsplit(consent.authorize_url).query.split("state=")[1].split("&")[0]
        self.seen.secrets += [cookie, state]
        w.outbound.expect(
            "POST",
            f"{OAUTH}/token",
            strava_says(200, hostile_grant("A", expires_at)),
        )
        self.page(
            f"{CALLBACK}?state={state}&code={SENTINEL}-code"
            f"&scope={FULL},{SENTINEL}&extra={SENTINEL}",
            cookie_header(cookie),
        )
        polled = w.post(
            ROUTES[ACTION_CONNECT_POLL], {"poll_secret": started.poll_secret}
        )
        self.seen.responses.append(("envelope", polled))
        answer = decode_answer(polled.content)
        assert answer.code.value == "connect-granted"
        token = answer.data["token"]
        assert isinstance(token, str)
        self.connection_token = token
        self.seen.secrets.append(self.connection_token)

    def declined_connects(self) -> None:
        """A Strava error on the redirect, and a refused code exchange."""
        w = self.w
        for failure in ("redirect", "exchange"):
            started = started_session(w)
            self.seen.secrets.append(started.poll_secret)
            shown = self.page(f"{CONNECT_PAGE}?code={started.user_code}")
            cookie = shown.headers["set-cookie"].split(";")[0].partition("=")[2]
            consent = w.strava().connect.page(started.user_code, cookie)
            assert isinstance(consent, ShowConsent)
            state = urlsplit(consent.authorize_url).query.split("state=")[1]
            state = state.split("&")[0]
            self.seen.secrets += [cookie, state]
            if failure == "redirect":
                query = (
                    f"state={state}&error={SENTINEL}&scope={SENTINEL}&code={SENTINEL}"
                )
            else:
                query = f"state={state}&code={SENTINEL}&scope={FULL}"
                w.outbound.expect(
                    "POST",
                    f"{OAUTH}/token",
                    strava_says(
                        400, {"message": SENTINEL, "errors": [{"code": SENTINEL}]}
                    ),
                )
            self.page(f"{CALLBACK}?{query}", cookie_header(cookie))
            polled = w.post(
                ROUTES[ACTION_CONNECT_POLL], {"poll_secret": started.poll_secret}
            )
            self.seen.responses.append(("envelope", polled))


def drive(s: Scenario, monkeypatch: pytest.MonkeyPatch) -> None:
    """The whole exercise; every scripted answer carries the sentinel in its headers."""
    w = s.w
    s.declined_connects()
    # An access token inside the refresh margin: the first publish refreshes.
    s.connect(expires_at=NOW + 100)

    # --- publish: a refresh, a listing, an update --------------------------
    w.outbound.expect(
        "POST",
        f"{OAUTH}/token",
        strava_says(
            200,
            {
                "access_token": f"{SENTINEL}-access-R",
                "refresh_token": f"{SENTINEL}-refresh-R",
                "expires_at": NOW + 10_000,
                "athlete": {"id": ATHLETE_ID},
                "message": SENTINEL,
            },
        ),
    )
    w.outbound.expect(
        "GET",
        LIST_URL,
        strava_says(
            200,
            [
                hostile_entry(ACTIVITY_ID),
                hostile_entry(DECOY_ID, sport_type="Ride"),
            ],
        ),
    )
    w.outbound.expect("PUT", UPDATE_URL, strava_says(200, {"name": SENTINEL}))
    s.envelope(PUBLISH_PATH, publish_fields(FACTS))

    # Strava failures: an error body, then a refused update; a rate limit
    # comes last (it holds the relay off Strava), an exception in the upload.
    w.outbound.expect(
        "GET", LIST_URL, strava_says(500, {"message": SENTINEL, "errors": [SENTINEL]})
    )
    s.envelope(PUBLISH_PATH, publish_fields(replace(FACTS, publication_id=THIRD_ID)))
    w.outbound.expect("GET", LIST_URL, strava_says(200, [hostile_entry(ACTIVITY_ID)]))
    w.outbound.expect(
        "PUT",
        UPDATE_URL,
        strava_says(403, {"message": SENTINEL, "errors": [{"field": SENTINEL}]}),
    )
    s.envelope(PUBLISH_PATH, publish_fields(replace(FACTS, publication_id=FIFTH_ID)))

    # --- upload: created, matched, failed, then an exception ---------------
    upload_facts = replace(FACTS, publication_id=OTHER_ID)
    w.outbound.expect(
        "GET", LIST_URL, strava_says(200, [hostile_entry(DECOY_ID, sport_type="Ride")])
    )
    w.outbound.expect(
        "POST",
        UPLOAD_URL,
        strava_says(
            201,
            {"id": UPLOAD_ID, "error": None, "status": SENTINEL, "id_str": SENTINEL},
        ),
    )
    w.outbound.expect(
        "GET",
        STATUS_URL,
        strava_says(
            200,
            {
                "id": UPLOAD_ID,
                "error": None,
                "status": SENTINEL,
                "external_id": SENTINEL,
                "activity_id": NEW_ID,
            },
        ),
    )
    s.envelope(UPLOAD_PATH, upload_fields(upload_facts, FIT))

    matched = replace(FACTS, publication_id=MATCHED_ID)
    w.outbound.expect("GET", LIST_URL, strava_says(200, [hostile_entry(ACTIVITY_ID)]))
    w.outbound.expect("PUT", UPDATE_URL, strava_says(200, {"name": SENTINEL}))
    s.envelope(UPLOAD_PATH, upload_fields(matched, FIT))

    failed = replace(FACTS, publication_id=FAILED_ID)
    w.outbound.expect("GET", LIST_URL, strava_says(200, []))
    w.outbound.expect(
        "POST", UPLOAD_URL, strava_says(201, {"id": UPLOAD_ID, "error": None})
    )
    w.outbound.expect(
        "GET",
        STATUS_URL,
        strava_says(
            200,
            {
                "id": UPLOAD_ID,
                "error": SENTINEL,
                "status": SENTINEL,
                "activity_id": None,
            },
        ),
    )
    s.envelope(UPLOAD_PATH, upload_fields(failed, FIT))

    boom = replace(FACTS, publication_id=BOOM_ID)
    w.outbound.expect("GET", LIST_URL, strava_says(200, []))
    w.outbound.expect(
        "POST", UPLOAD_URL, strava_says(201, {"id": UPLOAD_ID, "error": None})
    )
    real_call = type(w.outbound).__call__

    def raising(self: Any, request: Any, timeout: float) -> Any:
        if request.url == STATUS_URL:
            raise RuntimeError(SENTINEL)
        return real_call(self, request, timeout)

    monkeypatch.setattr(type(w.outbound), "__call__", raising)
    s.envelope(UPLOAD_PATH, upload_fields(boom, FIT))
    monkeypatch.setattr(type(w.outbound), "__call__", real_call)

    for path in ("/privacy", f"{CONNECT_PAGE}?code=NOSUCHCODE"):
        s.page(path)
    s.snapshot()  # the connected state: sealed tokens, budget

    # --- the operator's subscription commands -------------------------------
    cfg = w.strava().config
    client = f"client_id={cfg.client_id}&client_secret={cfg.client_secret}"
    view = f"{API}/push_subscriptions?{client}"
    elsewhere = {
        "id": SUBSCRIPTION_ID,
        "callback_url": f"https://{SENTINEL}.example/hook",
        "application_id": SENTINEL,
        "created_at": SENTINEL,
        "resource_state": SENTINEL,
    }
    callback = "https://relay.example/strava/webhook/" + HOOK_SECRET
    api = w.strava().api
    w.outbound.expect("GET", view, strava_says(200, [elsewhere]))
    s.seen.reports.append(webhook_show(api, callback).line)
    w.outbound.expect("GET", view, strava_says(200, []))
    w.outbound.expect(
        "POST",
        f"{API}/push_subscriptions",
        strava_says(201, {"id": SUBSCRIPTION_ID, "message": SENTINEL}),
    )
    s.seen.reports.append(webhook_create(api, callback).line)
    w.outbound.expect("GET", view, strava_says(200, [elsewhere]))
    w.outbound.expect(
        "DELETE",
        f"{API}/push_subscriptions/{SUBSCRIPTION_ID}?{client}",
        strava_says(204, b""),
    )
    s.seen.reports.append(webhook_delete(api).line)

    # --- disconnect, then a connection ended by Strava's deauthorization ---
    w.outbound.expect(
        "POST", f"{OAUTH}/revoke", strava_says(200, {"message": SENTINEL})
    )
    s.envelope(ROUTES[ACTION_DISCONNECT])
    assert w.store.get_connection(w.principal, "strava") is None
    s.snapshot()

    s.connection_token = ""
    s.connect(expires_at=NOW + 10_000)
    assert w.store.get_connection(w.principal, "strava") is not None
    w.outbound.expect(
        "GET", LIST_URL, strava_says(429, {"message": SENTINEL, "errors": [SENTINEL]})
    )
    s.envelope(PUBLISH_PATH, publish_fields(replace(FACTS, publication_id=FOURTH_ID)))
    activity_event = json.dumps(
        {
            "object_type": "activity",
            "object_id": ACTIVITY_ID,
            "aspect_type": "update",
            "owner_id": ATHLETE_ID,
            "updates": {"title": SENTINEL},
            "extra": SENTINEL,
        }
    ).encode()
    assert w.client.post(HOOK, content=activity_event).status_code == 200
    assert w.store.get_connection(w.principal, "strava") is not None
    s.snapshot()
    deauthorization = json.dumps(
        {
            "object_type": "athlete",
            "object_id": ATHLETE_ID,
            "aspect_type": "update",
            "owner_id": ATHLETE_ID,
            "subscription_id": SUBSCRIPTION_ID,
            "event_time": 1_700_000_000,
            "updates": {"authorized": "false", "note": SENTINEL},
            "extra": SENTINEL,
        }
    ).encode()
    sent = w.client.post(HOOK, content=deauthorization)
    assert (sent.status_code, sent.content) == (200, b"")
    s.seen.responses.append(("webhook", sent))
    assert w.store.get_connection(w.principal, "strava") is None
    s.snapshot()
    assert w.outbound.unserved() == 0  # every scripted answer was served


def leaks(needles: list[str | int], text: str) -> list[str | int]:
    return [needle for needle in needles if present(text, needle)]


def headers_text(sent: Any) -> str:
    return "\n".join(f"{name}: {value}" for name, value in sent.headers.items())


def test_nothing_strava_returns_escapes_the_relay_but_the_landed_link(
    make_world: Callable[..., World],
    database_target: Any,
    caplog: pytest.LogCaptureFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    w = make_world()
    caplog.set_level(logging.DEBUG)
    scenario = Scenario(w, database_target)
    drive(scenario, monkeypatch)
    seen = scenario.seen
    secrets = [*seen.secrets, w.strava().config.client_secret, HOOK_SECRET]
    words: list[str | int] = [SENTINEL]
    identifiers: list[str | int] = [*IDS]

    # --- the scenario reached what it claims to ----------------------------
    envelopes = [r for kind, r in seen.responses if kind == "envelope"]
    codes = [decode_answer(r.content) for r in envelopes]
    outcomes = [a.outcome for a in codes]
    assert outcomes.count("posted") == 2  # a publish and an upload that matched
    assert outcomes.count("uploaded") == 1
    assert {"unavailable", "rate_limited", "unconfirmed"} <= set(outcomes)
    rich = seen.snapshots[0]
    stored = " ".join(" ".join(rows) for rows in rich.values())
    assert [pid for pid in DRIVEN_PUBLICATION_IDS if pid in stored] == []
    assert rich["target_connections"], "the connected snapshot holds no connection"

    # --- Req 12.1: answers carry the link and nothing else of Strava's -----
    linked = [(a.outcome, a.data[LINK_FIELD]) for a in codes if LINK_FIELD in a.data]
    assert linked == [
        ("posted", f"{WEB}/activities/{ACTIVITY_ID}"),
        ("uploaded", f"{WEB}/activities/{NEW_ID}"),
        ("posted", f"{WEB}/activities/{ACTIVITY_ID}"),
    ]
    for sent, answer in zip(envelopes, codes, strict=True):
        assert set(answer.data) <= {
            LINK_FIELD,
            "token",
            "user_code",
            "poll_secret",
            "interval_s",
            "expires_in_s",
        }
        text = sent.content.decode()
        link = answer.data.get(LINK_FIELD)
        if link is not None:
            assert text.count(link) == 1
            text = text.replace(link, "")
        assert leaks(words + identifiers, text + headers_text(sent)) == []
    for kind, sent in seen.responses:
        if kind == "envelope":
            continue
        text = sent.text + headers_text(sent)
        assert leaks(words + identifiers, text) == []
    for line in seen.reports:
        assert leaks(words + identifiers, line) == []
    assert len(seen.reports) == 3

    # --- Req 12.2: no log record carries Strava's data or a secret ---------
    relay_records = [
        r for r in caplog.records if r.name.startswith(("fitdocs_relay", "uvicorn"))
    ]
    assert relay_records, "the relay wrote no log record: the log check is vacuous"
    assert any(r.levelno >= logging.ERROR for r in relay_records)
    logged = log_text(relay_records)
    assert "RuntimeError" in logged  # the sentinel exception was raised and logged
    assert leaks(words + identifiers + secrets, logged) == []

    # --- Req 12.3: no row holds Strava Data beyond the sealed tokens -------
    for dumped in seen.snapshots:
        assert dumped, "the database dump holds no table"
        everything = "\n".join(
            f"{name}: {row}" for name, rows in dumped.items() for row in rows
        )
        assert leaks(words + identifiers, everything) == []

    # --- the tokens are held, sealed: the one lasting Strava record --------
    (connection,) = rich["target_connections"]
    assert connection.count("'v1.") == 2  # access and refresh, both sealed
