"""Webhook (task 3.10) on both backends, against the real tables.

The tests that expect no change compare a dump of every table in the database
before and after. The deauthorization test compares the dump of every table but
the three it expects to change, and states exactly what changed in those three.
"""

from __future__ import annotations

import hmac
import json
import logging
from collections.abc import Callable
from typing import Any

import pytest
from tests.conformance.state_support import Target, raw
from tests.strava.scripted_strava import ScriptedOutbound

from fitdocs_relay.config import SqliteTarget
from fitdocs_relay.crypto import EncryptionKey, Keyring
from fitdocs_relay.storage.interface import NewPrincipal, NewToken, Storage
from fitdocs_relay.strava.api import MAX_ATHLETE_ID, Grant, StravaApi
from fitdocs_relay.strava.budget import StravaBudget
from fitdocs_relay.strava.config import Limits, LinkSetting, StravaConfig
from fitdocs_relay.strava.custody import Custody
from fitdocs_relay.strava.webhook import MAX_EVENT_BYTES, Webhook

NOW = 1_700_000_000
SECRET = "s3cret-" + "w" * 33
ATHLETE = "90210123"
OTHER_ATHLETE = "5551"
HUGE = 1_000_000
CONFIG = StravaConfig(
    client_id="4711",
    client_secret="client-secret",
    webhook_token=SECRET,
    api_url="https://api.example/v3",
    oauth_url="https://oauth.example/oauth",
    web_url="https://web.example",
    limits=Limits(HUGE, HUGE, HUGE, HUGE),
    links=LinkSetting.ACTIVITY,
)
DECOYS = {
    "d-true": "True",
    "d-float": "90210123.0",
    "d-zero": "0",
    "d-neg": "-90210123",
    "d-big": str(MAX_ATHLETE_ID + 1),
}
PEPPER = b"webhook-test-pepper-0123456789abcdef"


class World:
    def __init__(self, store: Storage, target: Target) -> None:
        self.store = store
        self.target = target
        self.outbound = ScriptedOutbound()
        self.custody = Custody(
            store,
            Keyring((EncryptionKey("k001", bytes(range(32))),)),
            StravaApi(CONFIG, outbound=self.outbound),
            StravaBudget(store, CONFIG.limits, clock=lambda: NOW),
            pepper=PEPPER,
            clock=lambda: NOW,
            monotonic=lambda: 0.0,
            sleep=lambda _s: None,
        )
        self.webhook = Webhook(self.custody, secret=SECRET)

    def dump(self) -> dict[str, list[str]]:
        if isinstance(self.target, SqliteTarget):
            sql = (
                "SELECT name FROM sqlite_master WHERE type = 'table' "
                "AND name NOT LIKE 'sqlite_%'"
            )
        else:
            sql = (
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema = current_schema() AND table_type = 'BASE TABLE'"
            )
        names = sorted(str(r[0]) for r in raw(self.target, sql))
        return {
            name: sorted(repr(r) for r in raw(self.target, f"SELECT * FROM {name}"))
            for name in names
        }


@pytest.fixture
def world(database_target: Target, open_full_storage: Callable[[], Storage]) -> World:
    store = open_full_storage()
    w = World(store, database_target)
    for pid, athlete in (("ann", ATHLETE), ("bea", OTHER_ATHLETE)):
        store.create_principal(NewPrincipal(pid, None), now=1)
        w.custody.store_grant(
            pid, Grant(f"access-{pid}", f"refresh-{pid}", NOW, athlete)
        )
        assert store.issue_connection_token(
            pid, "strava", NewToken(f"tok-{pid}", "v", None), now=NOW
        )
        for n in (1, 2):
            raw(
                database_target,
                "INSERT INTO target_publications (target, publication_id, "
                "principal_id, sport, start_s, elapsed_s, distance_m, created_at, "
                "updated_at) VALUES ('strava', ?, ?, 'run', 1.0, NULL, NULL, 1, 1)",
                (f"pub-{pid}-{n}", pid),
            )
    # accounts whose ids are what a lax reading of an owner would produce
    for pid, athlete in DECOYS.items():
        store.create_principal(NewPrincipal(pid, None), now=1)
        w.custody.store_grant(
            pid, Grant(f"access-{pid}", f"refresh-{pid}", NOW, athlete)
        )
    return w


def _rows(world: World, sql: str, *params: str) -> list[str]:
    """The sorted `repr` of each row `sql` selects, as `World.dump` writes them."""
    return sorted(repr(r) for r in raw(world.target, sql, params))


def event(**changes: Any) -> bytes:
    body: dict[str, Any] = {
        "object_type": "athlete",
        "object_id": int(ATHLETE),
        "aspect_type": "update",
        "updates": {"authorized": "false"},
        "owner_id": int(ATHLETE),
        "subscription_id": 120475,
        "event_time": 1516126040,
    }
    body.update(changes)
    return json.dumps(body).encode()


# --- validate ---------------------------------------------------------------


def test_the_configured_token_is_answered_with_the_challenge_echoed(
    world: World,
) -> None:
    assert world.webhook.validate(
        "subscribe", "15f7d1a91c1f40f8a748fd134752feb3", SECRET
    ) == {"hub.challenge": "15f7d1a91c1f40f8a748fd134752feb3"}
    assert world.webhook.validate("subscribe", "other-challenge", SECRET) == {
        "hub.challenge": "other-challenge"
    }


@pytest.mark.parametrize(
    ("mode", "challenge", "token"),
    [
        ("subscribe", "c", "wrong"),
        ("subscribe", "c", SECRET[:-1]),
        ("subscribe", "c", SECRET + "x"),
        ("subscribe", "c", SECRET.upper()),
        ("subscribe", "c", ""),
        ("subscribe", "c", None),
        ("subscribe", "c", "s3cret-é" + "w" * 32),
        ("subscribe", "c", "\ud800"),
        ("unsubscribe", "c", SECRET),
        ("Subscribe", "c", SECRET),
        ("", "c", SECRET),
        (None, "c", SECRET),
        ("subscribe", None, SECRET),
    ],
)
def test_every_other_validation_request_is_refused(
    world: World, mode: str | None, challenge: str | None, token: str | None
) -> None:
    assert world.webhook.validate(mode, challenge, token) is None


def test_the_token_is_compared_in_constant_time(
    world: World, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[tuple[bytes, bytes]] = []
    real = hmac.compare_digest

    def spy(a: bytes, b: bytes) -> bool:
        seen.append((a, b))
        return bool(real(a, b))

    monkeypatch.setattr(hmac, "compare_digest", spy)
    assert world.webhook.validate("subscribe", "c", SECRET) is not None
    assert world.webhook.validate("subscribe", "c", "nope") is None
    assert seen == [(SECRET.encode(), SECRET.encode()), (b"nope", SECRET.encode())]


# --- a deauthorization ------------------------------------------------------


def test_a_deauthorization_deletes_the_connection_its_links_and_its_token(
    world: World,
) -> None:
    before = world.dump()
    assert world.store.get_connection("ann", "strava") is not None
    assert len(before["target_publications"]) == 4
    token = world.store.find_token("tok-ann")
    assert token is not None and token.revoked_at is None
    ann_connection = _rows(
        world, "SELECT * FROM target_connections WHERE principal_id = ?", "ann"
    )
    ann_token = _rows(world, "SELECT * FROM tokens WHERE token_id = ?", "tok-ann")
    assert len(ann_connection) == 1 and len(ann_token) == 1
    assert len(before["target_connections"]) == 2 + len(DECOYS)
    ann_links = _rows(
        world,
        "SELECT * FROM target_publications WHERE publication_id IN (?, ?)",
        "pub-ann-1",
        "pub-ann-2",
    )
    assert len(ann_links) == 2

    world.webhook.event(event())

    assert world.store.get_connection("ann", "strava") is None
    pubs = raw(world.target, "SELECT publication_id FROM target_publications")
    assert sorted(str(p[0]) for p in pubs) == ["pub-bea-1", "pub-bea-2"]
    token = world.store.find_token("tok-ann")
    assert token is not None and token.revoked_at == NOW
    # the other account is untouched, down to its token
    assert world.store.get_connection("bea", "strava") is not None
    bea = world.store.find_token("tok-bea")
    assert bea is not None and bea.revoked_at is None
    after = world.dump()
    changed = {"target_connections", "target_publications", "tokens"}
    assert set(after) == set(before) and changed <= set(before)
    for name in set(before) - changed:
        assert after[name] == before[name], name
    # exactly ann's connection is gone
    assert sorted(
        set(before["target_connections"]) - set(after["target_connections"])
    ) == (ann_connection)
    assert len(after["target_connections"]) == len(before["target_connections"]) - 1
    assert set(after["target_connections"]) <= set(before["target_connections"])
    # exactly her two links are gone
    assert set(before["target_publications"]) - set(
        after["target_publications"]
    ) == set(ann_links)
    assert set(after["target_publications"]) < set(before["target_publications"])
    assert len(after["target_publications"]) == 2
    # only her token's row differs
    ann_token_after = _rows(world, "SELECT * FROM tokens WHERE token_id = ?", "tok-ann")
    assert len(ann_token_after) == 1 and ann_token_after != ann_token
    assert set(before["tokens"]) - set(after["tokens"]) == set(ann_token)
    assert set(after["tokens"]) - set(before["tokens"]) == set(ann_token_after)
    assert len(after["tokens"]) == len(before["tokens"])
    assert world.outbound.calls == []


def test_an_event_logs_nothing_at_any_level(
    world: World, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.DEBUG):
        world.webhook.event(event())
        world.webhook.event(IGNORED["not JSON"]())
        world.webhook.event(IGNORED["authorized true"]())
    assert world.store.get_connection("ann", "strava") is None
    assert caplog.records == []


def test_a_deauthorization_of_an_unknown_account_changes_nothing(
    world: World,
) -> None:
    before = world.dump()
    world.webhook.event(event(owner_id=777, object_id=777))
    assert world.dump() == before


def test_the_largest_accepted_body_is_acted_on(world: World) -> None:
    base = event()
    body = base + b" " * (MAX_EVENT_BYTES - len(base))
    assert len(body) == MAX_EVENT_BYTES
    world.webhook.event(body)
    assert world.store.get_connection("ann", "strava") is None


# --- everything else is acknowledged and ignored ----------------------------

HOSTILE_DEPTH = 30_000

IGNORED: dict[str, Callable[[], bytes]] = {
    "activity create": lambda: event(
        object_type="activity", aspect_type="create", updates={}
    ),
    "activity update carrying the deauthorization shape": lambda: event(
        object_type="activity"
    ),
    "athlete update that is not a deauthorization": lambda: event(
        updates={"title": "x"}
    ),
    "authorized true": lambda: event(updates={"authorized": "true"}),
    "authorized as a JSON false": lambda: event(updates={"authorized": False}),
    "authorized with other casing": lambda: event(updates={"authorized": "False"}),
    "no updates": lambda: json.dumps(
        {"object_type": "athlete", "owner_id": int(ATHLETE)}
    ).encode(),
    "updates a list": lambda: event(updates=["authorized"]),
    "no object type": lambda: json.dumps(
        {"updates": {"authorized": "false"}, "owner_id": int(ATHLETE)}
    ).encode(),
    "no owner": lambda: json.dumps(
        {"object_type": "athlete", "updates": {"authorized": "false"}}
    ).encode(),
    "owner as a string": lambda: event(owner_id=ATHLETE),
    "owner as a bool": lambda: event(owner_id=True),
    "owner as a float": lambda: event(owner_id=float(ATHLETE)),
    "owner zero": lambda: event(owner_id=0),
    "owner negative": lambda: event(owner_id=-int(ATHLETE)),
    "owner past the largest athlete id": lambda: event(owner_id=MAX_ATHLETE_ID + 1),
    "owner with five thousand digits": lambda: (
        b'{"object_type":"athlete","updates":{"authorized":"false"},"owner_id":'
        + b"9" * 5000
        + b"}"
    ),
    "a list": lambda: b"[" + event() + b"]",
    "a bare string": lambda: json.dumps("athlete").encode(),
    "not JSON": lambda: b"object_type=athlete",
    "empty": lambda: b"",
    "not UTF-8 inside an otherwise valid deauthorization": lambda: event(
        note="\u00e9"
    ).replace(b"\\u00e9", b"\xff"),
    "deeply nested": lambda: b"[" * HOSTILE_DEPTH + b"]" * HOSTILE_DEPTH,
    "deeply nested objects": lambda: (
        b'{"a":' * (HOSTILE_DEPTH // 3) + b"1" + b"}" * (HOSTILE_DEPTH // 3)
    ),
    "one byte over the limit": lambda: (
        event() + b" " * (MAX_EVENT_BYTES + 1 - len(event()))
    ),
}


@pytest.mark.parametrize("name", list(IGNORED))
def test_every_other_event_is_acknowledged_and_changes_no_table(
    world: World, name: str
) -> None:
    body = IGNORED[name]()
    before = world.dump()
    assert before["target_connections"] and before["target_publications"]
    assert world.store.get_connection("ann", "strava") is not None

    world.webhook.event(body)

    assert world.dump() == before
    assert world.outbound.calls == []


def test_the_over_limit_body_is_otherwise_a_valid_deauthorization() -> None:
    body = IGNORED["one byte over the limit"]()
    assert len(body) == MAX_EVENT_BYTES + 1
    assert json.loads(body)["updates"] == {"authorized": "false"}
    assert json.loads(body)["owner_id"] == int(ATHLETE)


def test_the_activity_decoy_differs_only_in_its_object_type() -> None:
    assert json.loads(
        IGNORED["activity update carrying the deauthorization shape"]()
    ) == (json.loads(event()) | {"object_type": "activity"})
