"""RateLimiter: per-token and per-client windows over the configured storage."""

from __future__ import annotations

import ast
import hashlib
import hmac
from collections.abc import Callable
from pathlib import Path

from tests.conformance.state_support import Target, raw

from fitdocs_relay import ratelimit
from fitdocs_relay.config import load_config
from fitdocs_relay.ratelimit import RateLimiter
from fitdocs_relay.storage.interface import Storage

PEPPER = b"ratelimit-test-pepper-0123456789abcdefghijklmnop"
OTHER_PEPPER = b"another-test-pepper-0123456789abcdefghijklmnopqr"
START = 1_700_000_040  # a multiple of 60
TOKEN_LIMIT = 7
CLIENT_LIMIT = 11

IPV4 = "203.0.113.77"
IPV6 = "2001:db8:85a3::8a2e:370:7334"


def expected_client_key(pepper: bytes, address: str) -> str:
    digest = hmac.new(pepper, b"client\0" + address.encode(), hashlib.sha256)
    return "c:" + digest.hexdigest()[:32]


class Clock:
    def __init__(self, now: int = START) -> None:
        self.now = now

    def __call__(self) -> int:
        return self.now


def make(
    open_full_storage: Callable[[], Storage],
    clock: Clock,
    *,
    pepper: bytes = PEPPER,
    storage: Storage | None = None,
) -> RateLimiter:
    return RateLimiter(
        storage or open_full_storage(),
        pepper=pepper,
        clock=clock,
        token_limit=TOKEN_LIMIT,
        client_limit=CLIENT_LIMIT,
    )


def stored_keys(target: Target) -> list[str]:
    return sorted(str(k) for (k,) in raw(target, "SELECT key FROM rate_counts"))


def test_the_token_limit_refuses_the_request_after_it_with_the_seconds_to_wait(
    open_full_storage: Callable[[], Storage],
) -> None:
    clock = Clock(START + 25)
    limiter = make(open_full_storage, clock)
    for n in range(1, TOKEN_LIMIT + 1):
        decision = limiter.check_token("tok_abc")
        assert (decision.allowed, decision.count, decision.retry_after_s) == (
            True,
            n,
            None,
        )
    refused = limiter.check_token("tok_abc")
    assert (refused.allowed, refused.count) == (False, TOKEN_LIMIT + 1)
    assert refused.retry_after_s == 35  # 60 - 25


def test_the_client_limit_refuses_the_request_after_it(
    open_full_storage: Callable[[], Storage],
) -> None:
    clock = Clock(START + 40)
    limiter = make(open_full_storage, clock)
    for _ in range(CLIENT_LIMIT):
        assert limiter.check_client(IPV4).allowed
    refused = limiter.check_client(IPV4)
    assert (refused.allowed, refused.count, refused.retry_after_s) == (
        False,
        CLIENT_LIMIT + 1,
        20,
    )


def test_each_limit_is_its_own_configured_number_not_the_other_or_sixty(
    open_full_storage: Callable[[], Storage],
) -> None:
    assert len({TOKEN_LIMIT, CLIENT_LIMIT, 60}) == 3
    limiter = make(open_full_storage, Clock())
    token_allowed = sum(limiter.check_token("t1").allowed for _ in range(80))
    client_allowed = sum(limiter.check_client(IPV4).allowed for _ in range(80))
    assert (token_allowed, client_allowed) == (TOKEN_LIMIT, CLIENT_LIMIT)


def test_a_new_window_allows_again_and_the_old_one_stays_refused_until_then(
    open_full_storage: Callable[[], Storage],
) -> None:
    clock = Clock(START + 59)
    limiter = make(open_full_storage, clock)
    for _ in range(TOKEN_LIMIT):
        limiter.check_token("t1")
    last_second = limiter.check_token("t1")
    assert (last_second.allowed, last_second.retry_after_s) == (False, 1)
    clock.now = START + 60
    fresh = limiter.check_token("t1")
    assert (fresh.allowed, fresh.count, fresh.retry_after_s) == (True, 1, None)


def test_the_window_is_sixty_seconds_long(
    open_full_storage: Callable[[], Storage],
) -> None:
    clock = Clock(START)
    limiter = make(open_full_storage, clock)
    for _ in range(TOKEN_LIMIT):
        limiter.check_token("t1")
    refused = limiter.check_token("t1")
    assert (refused.allowed, refused.retry_after_s) == (False, 60)


def test_counts_live_in_the_database_not_the_limiter(
    open_full_storage: Callable[[], Storage],
) -> None:
    storage = open_full_storage()
    clock = Clock()
    for _ in range(TOKEN_LIMIT):
        make(open_full_storage, clock, storage=storage).check_token("t1")
    assert not make(open_full_storage, clock, storage=storage).check_token("t1").allowed


def test_the_stored_client_key_is_the_keyed_hash_and_never_holds_the_address(
    open_full_storage: Callable[[], Storage],
    database_target: Target,
) -> None:
    limiter = make(open_full_storage, Clock())
    addresses = [IPV4, IPV6]
    for address in addresses:
        limiter.check_client(address)
    keys = stored_keys(database_target)
    assert keys == sorted(expected_client_key(PEPPER, a) for a in addresses)
    for key in keys:
        for address in addresses:
            for piece in (address, *address.replace(":", ".").split(".")):
                if len(piece) >= 3:
                    assert piece not in key.removeprefix("c:"), (key, piece)
        assert len(key) == len("c:") + 32


def test_a_token_key_is_the_token_id_under_a_t_prefix(
    open_full_storage: Callable[[], Storage],
    database_target: Target,
) -> None:
    make(open_full_storage, Clock()).check_token("tok_Zq9")
    assert stored_keys(database_target) == ["t:tok_Zq9"]


def test_two_addresses_get_two_buckets(
    open_full_storage: Callable[[], Storage],
    database_target: Target,
) -> None:
    limiter = make(open_full_storage, Clock())
    for _ in range(CLIENT_LIMIT):
        limiter.check_client(IPV4)
    assert not limiter.check_client(IPV4).allowed
    other = limiter.check_client(IPV6)
    assert (other.allowed, other.count) == (True, 1)
    assert len(set(stored_keys(database_target))) == 2


def test_the_keyed_hash_changes_with_the_pepper(
    open_full_storage: Callable[[], Storage],
    database_target: Target,
) -> None:
    storage = open_full_storage()
    clock = Clock()
    make(open_full_storage, clock, pepper=PEPPER, storage=storage).check_client(IPV4)
    make(open_full_storage, clock, pepper=OTHER_PEPPER, storage=storage).check_client(
        IPV4
    )
    assert stored_keys(database_target) == sorted(
        [expected_client_key(PEPPER, IPV4), expected_client_key(OTHER_PEPPER, IPV4)]
    )
    assert expected_client_key(PEPPER, IPV4) != expected_client_key(OTHER_PEPPER, IPV4)


def test_an_absent_address_shares_one_key_distinct_from_any_real_address(
    open_full_storage: Callable[[], Storage],
    database_target: Target,
) -> None:
    limiter = make(open_full_storage, Clock())
    for n in range(1, 4):
        assert limiter.check_client(None).count == n
    assert limiter.check_client(IPV4).count == 1
    assert limiter.check_client("unknown").count == 1
    assert stored_keys(database_target) == sorted(
        [
            "c:unknown",
            expected_client_key(PEPPER, IPV4),
            expected_client_key(PEPPER, "unknown"),
        ]
    )


def test_token_and_client_keys_never_share_a_bucket(
    open_full_storage: Callable[[], Storage],
    database_target: Target,
) -> None:
    limiter = make(open_full_storage, Clock())
    colliding_id = IPV4
    for _ in range(TOKEN_LIMIT):
        limiter.check_token(colliding_id)
    assert not limiter.check_token(colliding_id).allowed
    client = limiter.check_client(colliding_id)
    assert (client.allowed, client.count) == (True, 1)
    unknown_id = limiter.check_token("unknown")
    assert (unknown_id.allowed, unknown_id.count) == (True, 1)
    limiter.check_client(None)
    again = limiter.check_token("unknown")
    assert again.count == 2
    assert "c:unknown" in stored_keys(database_target)
    assert "t:unknown" in stored_keys(database_target)


def test_a_second_storage_instance_sees_counts_the_first_one_wrote(
    open_full_storage: Callable[[], Storage],
) -> None:
    seeding = open_full_storage()
    for _ in range(TOKEN_LIMIT):
        seeding.count_request(key="t:t1", window_s=60, limit=TOKEN_LIMIT, now=START)
    limiter = make(open_full_storage, Clock())  # opens its own, second instance
    refused = limiter.check_token("t1")
    assert (refused.allowed, refused.count) == (False, TOKEN_LIMIT + 1)


def test_the_limits_default_from_the_loaded_configuration(
    open_full_storage: Callable[[], Storage],
) -> None:
    config = load_config(
        {
            "FITDOCS_RELAY_DATABASE_URL": "sqlite:///relay.db",
            "FITDOCS_RELAY_TOKEN_PEPPER": "p" * 43,
        }
    )
    assert (config.token_limit_per_minute, config.client_limit_per_minute) == (60, 20)
    limiter = RateLimiter(
        open_full_storage(),
        pepper=config.pepper,
        clock=Clock(START + 10),
        token_limit=config.token_limit_per_minute,
        client_limit=config.client_limit_per_minute,
    )
    for n in range(1, 61):
        allowed = limiter.check_token("t1")
        assert (allowed.allowed, allowed.count) == (True, n)
    token_refused = limiter.check_token("t1")
    assert (token_refused.allowed, token_refused.count) == (False, 61)
    assert token_refused.retry_after_s == 50
    for _ in range(20):
        assert limiter.check_client(IPV4).allowed
    client_refused = limiter.check_client(IPV4)
    assert (client_refused.allowed, client_refused.count) == (False, 21)
    assert client_refused.retry_after_s == 50


def test_a_known_pepper_and_address_give_the_written_out_key(
    open_full_storage: Callable[[], Storage],
    database_target: Target,
) -> None:
    make(open_full_storage, Clock(), pepper=b"known-pepper").check_client("192.0.2.1")
    assert stored_keys(database_target) == ["c:981bb090a7022b025a5f6759a78ccb28"]


DESIGNED_RATE_LIMITER = {
    "decorators": [],
    "bases": [],
    "members": [
        "def __init__(self, storage: Storage, *, pepper: bytes, "
        "clock: Callable[[], int], token_limit: int, client_limit: int) -> None",
        "def check_token(self, token_id: str) -> RateDecision",
        "def check_client(self, address: str | None) -> RateDecision",
    ],
}


def _render_rate_limiter(source: str) -> dict[str, list[str]]:
    classes = [
        n
        for n in ast.parse(source).body
        if isinstance(n, ast.ClassDef) and n.name == "RateLimiter"
    ]
    assert len(classes) == 1
    node = classes[0]
    members = [
        f"def {f.name}({ast.unparse(f.args)}) -> {ast.unparse(f.returns)}"
        for f in node.body
        if isinstance(f, ast.FunctionDef)
        and (f.name == "__init__" or not f.name.startswith("_"))
        and f.returns is not None
    ]
    return {
        "decorators": [ast.unparse(d) for d in node.decorator_list],
        "bases": [ast.unparse(b) for b in node.bases],
        "members": members,
    }


def test_the_limiter_class_has_the_designed_signatures() -> None:
    source = Path(ratelimit.__file__).read_text(encoding="utf-8")
    assert _render_rate_limiter(source) == DESIGNED_RATE_LIMITER
