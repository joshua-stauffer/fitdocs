"""The Strava operator commands (task 4.5): each state, each exit code, no secret.

Every test calls `cli.main` in-process. Strava is the scripted outbound
(`cli.urllib_outbound` is replaced), so a request nobody scripted raises
`UnscriptedCall`, and `Result.calls` lists the requests that left.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Final
from urllib.parse import urlencode

import pytest
from tests.strava.scripted_strava import Call, ScriptedOutbound, reply

from fitdocs_relay import cli
from fitdocs_relay.config import PostgresTarget, SqliteTarget
from fitdocs_relay.crypto import Keyring, new_key, parse_keys
from fitdocs_relay.identity import TokenService
from fitdocs_relay.outbound import OutboundError
from fitdocs_relay.storage import open_storage
from fitdocs_relay.storage.interface import (
    NewConnection,
    NewPrincipal,
    NewToken,
    SealedTokens,
    StorageUnreachable,
)
from fitdocs_relay.storage.migrate import migrate
from fitdocs_relay.strava.budget import StravaBudget
from fitdocs_relay.strava.config import Limits

P = "FITDOCS_RELAY_"
API: Final = "https://api.example/v3"
OAUTH: Final = "https://oauth.example/oauth"
VIEW: Final = f"{API}/push_subscriptions?" + urlencode(
    {"client_id": "4711", "client_secret": "client-secret-Zq9"}
)
CLIENT_SECRET: Final = "client-secret-Zq9"
WEBHOOK_TOKEN: Final = "hook-" + "w" * 40
PUBLIC_URL: Final = "https://relay.example.org"
CALLBACK: Final = f"{PUBLIC_URL}/strava/webhook/{WEBHOOK_TOKEN}"
ELSEWHERE: Final = "https://elsewhere.example/SENTINEL-callback"
PEPPER: Final = "p" * 43

KEY_NEW: Final = new_key()
KEY_OLD: Final = new_key()
KEY_OTHER: Final = new_key()

# Every command the Strava target adds, as argv; the CLI suite's own table
# covers the rest of the contract's commands.
STRAVA_COMMANDS: Final[list[list[str]]] = [
    ["strava", "webhook", "show"],
    ["strava", "webhook", "create"],
    ["strava", "webhook", "delete"],
    ["reencrypt"],
    ["new-encryption-key"],
]
SECRETS: Final = (CLIENT_SECRET, WEBHOOK_TOKEN, CALLBACK, ELSEWHERE, KEY_NEW, KEY_OLD)


@dataclass
class Result:
    code: int
    out: str
    err: str
    calls: list[Call]


@pytest.fixture
def strava_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "relay.sqlite3"
    values = {
        "DATABASE_URL": f"sqlite:///{path}",
        "TOKEN_PEPPER": PEPPER,
        "PUBLIC_URL": PUBLIC_URL,
        "ENCRYPTION_KEYS": f"{KEY_NEW},{KEY_OLD}",
        "OPERATOR_NAME": "Example Operator",
        "SUPPORT_CONTACT": "help@example.org",
        "STRAVA_CLIENT_ID": "4711",
        "STRAVA_CLIENT_SECRET": CLIENT_SECRET,
        "STRAVA_WEBHOOK_TOKEN": WEBHOOK_TOKEN,
        "STRAVA_API_URL": API,
        "STRAVA_OAUTH_URL": OAUTH,
    }
    for name, value in values.items():
        monkeypatch.setenv(P + name, value)
    return path


@pytest.fixture
def scripted(monkeypatch: pytest.MonkeyPatch) -> ScriptedOutbound:
    fake = ScriptedOutbound()
    monkeypatch.setattr(cli, "urllib_outbound", fake)
    return fake


@pytest.fixture
def run(
    capsys: pytest.CaptureFixture[str], scripted: ScriptedOutbound
) -> Callable[..., Result]:
    def call(*argv: str) -> Result:
        before = len(scripted.calls)
        code = cli.main(list(argv))
        captured = capsys.readouterr()
        return Result(code, captured.out, captured.err, scripted.calls[before:])

    return call


def entry(callback: str, identifier: int = 555) -> dict[str, object]:
    return {"id": identifier, "callback_url": callback, "application_id": 1}


def assert_no_secret(result: Result) -> None:
    for secret in SECRETS:
        assert secret not in result.out, secret
        assert secret not in result.err, secret


# --- strava webhook show ---------------------------------------------------------


@pytest.mark.parametrize(
    ("listed", "line"),
    [
        ([], "not subscribed"),
        ([entry(CALLBACK)], "subscribed"),
        ([entry(ELSEWHERE)], "subscribed elsewhere"),
    ],
)
def test_show_prints_the_state_and_exits_zero(
    strava_env: Path,
    run: Callable[..., Result],
    scripted: ScriptedOutbound,
    listed: list[object],
    line: str,
) -> None:
    scripted.expect("GET", VIEW, reply(200, listed))
    result = run("strava", "webhook", "show")
    assert (result.code, result.out, result.err) == (0, line + "\n", "")
    assert [(c.request.method, c.request.url) for c in result.calls] == [("GET", VIEW)]
    assert_no_secret(result)


# --- strava webhook create -------------------------------------------------------


def test_create_subscribes_with_the_public_address_and_the_secret_as_verify_token(
    strava_env: Path, run: Callable[..., Result], scripted: ScriptedOutbound
) -> None:
    post = f"{API}/push_subscriptions"
    scripted.expect("GET", VIEW, reply(200, []))
    scripted.expect("POST", post, reply(201, {"id": 555}))
    result = run("strava", "webhook", "create")
    assert (result.code, result.out, result.err) == (0, "subscribed\n", "")
    assert [(c.request.method, c.request.url) for c in result.calls] == [
        ("GET", VIEW),
        ("POST", post),
    ]
    assert result.calls[1].form == {
        "client_id": "4711",
        "client_secret": CLIENT_SECRET,
        "callback_url": CALLBACK,
        "verify_token": WEBHOOK_TOKEN,
    }
    assert_no_secret(result)


def test_create_over_our_own_subscription_creates_nothing(
    strava_env: Path, run: Callable[..., Result], scripted: ScriptedOutbound
) -> None:
    scripted.expect("GET", VIEW, reply(200, [entry(CALLBACK)]))
    result = run("strava", "webhook", "create")
    assert (result.code, result.out, result.err) == (0, "already subscribed\n", "")
    assert [c.request.method for c in result.calls] == ["GET"]
    assert_no_secret(result)


def test_create_over_another_callback_creates_nothing_and_exits_one(
    strava_env: Path, run: Callable[..., Result], scripted: ScriptedOutbound
) -> None:
    scripted.expect("GET", VIEW, reply(200, [entry(ELSEWHERE)]))
    result = run("strava", "webhook", "create")
    assert (result.code, result.out, result.err) == (1, "", "subscribed elsewhere\n")
    assert [c.request.method for c in result.calls] == ["GET"]
    assert_no_secret(result)


# --- strava webhook delete -------------------------------------------------------


def test_delete_removes_each_listed_subscription_and_says_deleted(
    strava_env: Path, run: Callable[..., Result], scripted: ScriptedOutbound
) -> None:
    scripted.expect("GET", VIEW, reply(200, [entry(ELSEWHERE, 777)]))
    removal = f"{API}/push_subscriptions/777?" + urlencode(
        {"client_id": "4711", "client_secret": CLIENT_SECRET}
    )
    scripted.expect("DELETE", removal, reply(204))
    result = run("strava", "webhook", "delete")
    assert (result.code, result.out, result.err) == (0, "deleted\n", "")
    assert [(c.request.method, c.request.url) for c in result.calls] == [
        ("GET", VIEW),
        ("DELETE", removal),
    ]
    assert_no_secret(result)


def test_delete_with_nothing_subscribed_says_so_and_deletes_nothing(
    strava_env: Path, run: Callable[..., Result], scripted: ScriptedOutbound
) -> None:
    scripted.expect("GET", VIEW, reply(200, []))
    result = run("strava", "webhook", "delete")
    assert (result.code, result.out, result.err) == (0, "not subscribed\n", "")
    assert [c.request.method for c in result.calls] == ["GET"]


# --- a Strava failure ------------------------------------------------------------


HOSTILE = b"STRAVA-SAID-" + CLIENT_SECRET.encode() + b" " + ELSEWHERE.encode()


@pytest.mark.parametrize(
    ("argv", "method", "url", "status", "failure"),
    [
        (["show"], "GET", VIEW, 401, "auth"),
        (["create"], "GET", VIEW, 500, "server"),
        (["delete"], "GET", VIEW, 429, "limited"),
    ],
)
def test_a_failed_view_prints_only_the_failure_class_and_exits_one(
    strava_env: Path,
    run: Callable[..., Result],
    scripted: ScriptedOutbound,
    argv: list[str],
    method: str,
    url: str,
    status: int,
    failure: str,
) -> None:
    scripted.expect(method, url, reply(status, HOSTILE))
    result = run("strava", "webhook", *argv)
    assert (result.code, result.out, result.err) == (
        1,
        "",
        f"strava failure: {failure}\n",
    )
    assert "STRAVA-SAID" not in result.err
    assert_no_secret(result)


def test_a_failed_create_prints_the_failure_class_and_exits_one(
    strava_env: Path, run: Callable[..., Result], scripted: ScriptedOutbound
) -> None:
    scripted.expect("GET", VIEW, reply(200, []))
    scripted.expect("POST", f"{API}/push_subscriptions", reply(400, HOSTILE))
    result = run("strava", "webhook", "create")
    assert (result.code, result.out, result.err) == (1, "", "strava failure: invalid\n")
    assert_no_secret(result)


def test_a_failed_delete_prints_the_failure_class_and_exits_one(
    strava_env: Path, run: Callable[..., Result], scripted: ScriptedOutbound
) -> None:
    scripted.expect("GET", VIEW, reply(200, [entry(ELSEWHERE, 9)]))
    removal = f"{API}/push_subscriptions/9?" + urlencode(
        {"client_id": "4711", "client_secret": CLIENT_SECRET}
    )
    scripted.expect("DELETE", removal, reply(403, HOSTILE))
    result = run("strava", "webhook", "delete")
    assert (result.code, result.out, result.err) == (
        1,
        "",
        "strava failure: forbidden\n",
    )
    assert_no_secret(result)


def test_an_unreachable_strava_is_a_network_failure(
    strava_env: Path, run: Callable[..., Result], scripted: ScriptedOutbound
) -> None:
    scripted.expect("GET", VIEW, OutboundError("network"))
    result = run("strava", "webhook", "show")
    assert (result.code, result.out, result.err) == (1, "", "strava failure: network\n")


# --- the target is not configured ------------------------------------------------


def test_the_strava_commands_refuse_when_the_target_is_not_configured(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    run: Callable[..., Result],
) -> None:
    monkeypatch.setenv(P + "DATABASE_URL", f"sqlite:///{tmp_path}/relay.sqlite3")
    monkeypatch.setenv(P + "TOKEN_PEPPER", PEPPER)
    refused = [argv for argv in STRAVA_COMMANDS if argv[0] != "new-encryption-key"]
    assert len(refused) == 4
    for argv in refused:
        result = run(*argv)
        assert (result.code, result.out, result.err, result.calls) == (
            2,
            "",
            "the Strava target is not configured\n",
            [],
        ), argv
    assert not (tmp_path / "relay.sqlite3").exists()  # nothing was opened


# --- new-encryption-key ----------------------------------------------------------


def test_new_encryption_key_prints_a_fresh_usable_key_without_configuration(
    monkeypatch: pytest.MonkeyPatch, run: Callable[..., Result]
) -> None:
    monkeypatch.setenv(P + "PORT", "not-a-port")  # a broken environment is ignored
    first = run("new-encryption-key")
    second = run("new-encryption-key")
    assert (first.code, first.err, second.code, second.err) == (0, "", 0, "")
    assert first.out.endswith("\n") and first.out.count("\n") == 1
    assert first.out != second.out
    for result in (first, second):
        (key,) = parse_keys(result.out.strip())
        assert len(key.material) == 32
    assert first.calls == [] and second.calls == []


# --- reencrypt --------------------------------------------------------------------


def ctx(principal: str, field_name: str) -> str:
    return f"fitdocs-relay:v1:strava:{principal}:{field_name}"


def seed(
    target: SqliteTarget | PostgresTarget, rows: dict[str, str]
) -> Callable[[str], tuple[str, str | None]]:
    """Connections sealed by hand: `rows` maps a principal to the key that sealed it."""
    store = open_storage(target)
    try:
        migrate(store, now=1)
        for principal, key in rows.items():
            ring = Keyring(parse_keys(key))
            store.create_principal(NewPrincipal(principal, None), now=1)
            store.put_connection(
                NewConnection(
                    principal,
                    "strava",
                    f"acct-{principal}",
                    SealedTokens(
                        ring.seal("access-tok", context=ctx(principal, "access")),
                        ring.seal("refresh-tok", context=ctx(principal, "refresh")),
                        1_900_000_000,
                    ),
                ),
                now=1,
            )
    finally:
        store.close()

    def key_ids(principal: str) -> tuple[str, str | None]:
        reopened = open_storage(target)
        try:
            row = reopened.get_connection(principal, "strava")
            assert row is not None
            ring = Keyring(parse_keys(f"{KEY_NEW},{KEY_OLD},{KEY_OTHER}"))
            assert row.tokens.refresh is not None
            return (
                ring.key_id_of(row.tokens.access) or "?",
                ring.key_id_of(row.tokens.refresh),
            )
        finally:
            reopened.close()

    return key_ids


def use(target: SqliteTarget | PostgresTarget, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(cli, "open_storage", lambda _: open_storage(target))


def test_reencrypt_moves_readable_rows_to_the_current_key_on_both_backends(
    strava_env: Path,
    database_target: SqliteTarget | PostgresTarget,
    monkeypatch: pytest.MonkeyPatch,
    run: Callable[..., Result],
) -> None:
    use(database_target, monkeypatch)
    new_id, old_id = KEY_NEW.split(":")[0], KEY_OLD.split(":")[0]
    key_ids = seed(database_target, {"ann": KEY_OLD, "bea": KEY_OLD})
    assert key_ids("ann") == (old_id, old_id)  # the starting state is the old key
    result = run("reencrypt")
    assert (result.code, result.out, result.err) == (
        0,
        "re-encrypted 2, unreadable 0\n",
        "",
    )
    assert result.calls == []
    assert key_ids("ann") == (new_id, new_id)
    assert key_ids("bea") == (new_id, new_id)
    assert run("reencrypt").out == "re-encrypted 0, unreadable 0\n"  # nothing left


def test_reencrypt_exits_one_when_a_row_is_unreadable_and_leaves_it_alone(
    strava_env: Path,
    database_target: SqliteTarget | PostgresTarget,
    monkeypatch: pytest.MonkeyPatch,
    run: Callable[..., Result],
) -> None:
    use(database_target, monkeypatch)
    new_id, old_id = KEY_NEW.split(":")[0], KEY_OLD.split(":")[0]
    other_id = KEY_OTHER.split(":")[0]
    key_ids = seed(database_target, {"ann": KEY_OLD, "bea": KEY_OTHER, "cat": KEY_OLD})
    assert key_ids("ann") == (old_id, old_id)  # the starting state is the old key
    result = run("reencrypt")
    assert (result.code, result.out, result.err) == (
        1,
        "re-encrypted 2, unreadable 1\n",
        "",
    )
    assert key_ids("ann") == (new_id, new_id)
    assert key_ids("cat") == (new_id, new_id)
    assert key_ids("bea") == (other_id, other_id)  # no configured key opens it
    assert old_id != other_id
    assert_no_secret(result)


def test_reencrypt_refuses_a_database_that_is_not_current(
    strava_env: Path, run: Callable[..., Result]
) -> None:
    result = run("reencrypt")
    assert result.code == 1 and result.out == ""
    assert "run 'fitdocs-relay migrate'" in result.err


# --- principal delete revokes at Strava ---------------------------------------------

REVOKE: Final = f"{OAUTH}/revoke"
NOT_REVOKED: Final = cli.MSG_NOT_REVOKED + "\n"


def stored(
    target: SqliteTarget | PostgresTarget, principal: str
) -> tuple[bool, bool, bool]:
    """(principal, tokens, connection) still in storage."""
    store = open_storage(target)
    try:
        return (
            store.get_principal(principal) is not None,
            store.find_token("tok-ann") is not None,
            store.get_connection(principal, "strava") is not None,
        )
    finally:
        store.close()


def seed_deletable(
    target: SqliteTarget | PostgresTarget, key: str = KEY_NEW, *, connect: bool = True
) -> None:
    store = open_storage(target)
    try:
        migrate(store, now=1)
        store.create_principal(NewPrincipal("ann", None), now=1)
        if connect:
            ring = Keyring(parse_keys(key))
            store.put_connection(
                NewConnection(
                    "ann",
                    "strava",
                    "acct-ann",
                    SealedTokens(
                        ring.seal("access-tok", context=ctx("ann", "access")),
                        ring.seal("refresh-tok", context=ctx("ann", "refresh")),
                        1_900_000_000,
                    ),
                ),
                now=1,
            )
            assert store.issue_connection_token(
                "ann", "strava", NewToken("tok-ann", "v", None), now=1
            )
        else:
            store.mint_token(
                NewToken("tok-ann", "v", None),
                principal_id="ann",
                new_principal=None,
                now=1,
            )
    finally:
        store.close()


@pytest.mark.parametrize(
    ("answer", "warned"),
    [
        (reply(200, {}), False),
        (reply(401), True),
        (reply(403), True),
        (reply(500), True),
        (reply(429), True),
        (OutboundError("timeout"), True),
    ],
    ids=["accepted", "401", "403", "500", "429", "unreachable"],
)
def test_principal_delete_asks_strava_once_and_deletes_whatever_it_answers(
    strava_env: Path,
    database_target: SqliteTarget | PostgresTarget,
    monkeypatch: pytest.MonkeyPatch,
    run: Callable[..., Result],
    scripted: ScriptedOutbound,
    answer: object,
    warned: bool,
) -> None:
    use(database_target, monkeypatch)
    seed_deletable(database_target)
    assert stored(database_target, "ann") == (True, True, True)
    scripted.expect("POST", REVOKE, answer)  # type: ignore[arg-type]
    result = run("principal", "delete", "ann")
    assert (result.code, result.out) == (0, "deleted ann\n")
    assert result.err == (NOT_REVOKED if warned else "")
    assert len(result.calls) == 1
    assert result.calls[0].form == {"token": "refresh-tok"}
    assert stored(database_target, "ann") == (False, False, False)
    assert_no_secret(result)
    assert "refresh-tok" not in result.err + result.out


def test_principal_delete_with_the_budget_spent_makes_no_call_and_deletes(
    strava_env: Path,
    database_target: SqliteTarget | PostgresTarget,
    monkeypatch: pytest.MonkeyPatch,
    run: Callable[..., Result],
) -> None:
    monkeypatch.setenv(P + "STRAVA_READ_RATE_LIMIT", "1,1")
    use(database_target, monkeypatch)
    seed_deletable(database_target)
    store = open_storage(database_target)
    try:  # the one call the window allows is already spent
        budget = StravaBudget(
            store, Limits(10, 10, 1, 1), clock=lambda: int(time.time())
        )
        assert budget.spend("ann").allowed
    finally:
        store.close()
    result = run("principal", "delete", "ann")
    assert (result.code, result.out, result.err) == (0, "deleted ann\n", NOT_REVOKED)
    assert result.calls == []
    assert stored(database_target, "ann") == (False, False, False)


def test_principal_delete_with_unreadable_tokens_makes_no_call_and_deletes(
    strava_env: Path,
    database_target: SqliteTarget | PostgresTarget,
    monkeypatch: pytest.MonkeyPatch,
    run: Callable[..., Result],
) -> None:
    use(database_target, monkeypatch)
    seed_deletable(database_target, KEY_OTHER)
    result = run("principal", "delete", "ann")
    assert (result.code, result.out, result.err) == (0, "deleted ann\n", NOT_REVOKED)
    assert result.calls == []
    assert stored(database_target, "ann") == (False, False, False)


def test_principal_delete_with_a_raising_revoke_still_deletes_and_warns(
    strava_env: Path,
    database_target: SqliteTarget | PostgresTarget,
    monkeypatch: pytest.MonkeyPatch,
    run: Callable[..., Result],
) -> None:
    use(database_target, monkeypatch)
    seed_deletable(database_target)
    # Nothing is scripted, so the one revoke attempt raises UnscriptedCall.
    result = run("principal", "delete", "ann")
    assert (result.code, result.out, result.err) == (0, "deleted ann\n", NOT_REVOKED)
    assert len(result.calls) == 1
    assert stored(database_target, "ann") == (False, False, False)
    assert_no_secret(result)


def test_principal_delete_without_a_connection_makes_no_call(
    strava_env: Path,
    database_target: SqliteTarget | PostgresTarget,
    monkeypatch: pytest.MonkeyPatch,
    run: Callable[..., Result],
) -> None:
    use(database_target, monkeypatch)
    seed_deletable(database_target, connect=False)
    result = run("principal", "delete", "ann")
    assert (result.code, result.out, result.err) == (0, "deleted ann\n", "")
    assert result.calls == []
    assert stored(database_target, "ann") == (False, False, False)


def test_principal_delete_of_an_unknown_principal_fails_without_a_call(
    strava_env: Path,
    database_target: SqliteTarget | PostgresTarget,
    monkeypatch: pytest.MonkeyPatch,
    run: Callable[..., Result],
) -> None:
    use(database_target, monkeypatch)
    seed_deletable(database_target)
    result = run("principal", "delete", "zed")
    assert (result.code, result.out, result.err) == (
        1,
        "",
        "unknown principal: zed\n",
    )
    assert result.calls == []
    assert stored(database_target, "ann") == (True, True, True)


def test_principal_delete_without_strava_configured_is_unchanged(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    target = SqliteTarget(path=tmp_path / "plain.sqlite3")
    monkeypatch.setenv(P + "DATABASE_URL", f"sqlite:///{target.path}")
    monkeypatch.setenv(P + "TOKEN_PEPPER", PEPPER)
    for name in (
        "STRAVA_CLIENT_ID",
        "STRAVA_CLIENT_SECRET",
        "STRAVA_WEBHOOK_TOKEN",
        "PUBLIC_URL",
        "ENCRYPTION_KEYS",
    ):
        monkeypatch.delenv(P + name, raising=False)
    seed_deletable(target)  # a connection exists, but the relay does not offer Strava
    assert stored(target, "ann") == (True, True, True)

    def forbidden(*_: object, **__: object) -> None:
        raise AssertionError("Strava must not be called")

    monkeypatch.setattr(cli, "urllib_outbound", forbidden)
    use(target, monkeypatch)
    assert cli.main(["principal", "delete", "ann"]) == 0
    captured = capsys.readouterr()
    assert (captured.out, captured.err) == ("deleted ann\n", "")
    assert stored(target, "ann") == (False, False, False)


def test_a_failed_revoke_is_reported_even_when_the_delete_then_raises(
    strava_env: Path,
    database_target: SqliteTarget | PostgresTarget,
    monkeypatch: pytest.MonkeyPatch,
    run: Callable[..., Result],
    scripted: ScriptedOutbound,
) -> None:
    use(database_target, monkeypatch)
    seed_deletable(database_target)
    scripted.expect("POST", REVOKE, reply(500))

    def broken(self: object, principal_id: str) -> bool:
        raise StorageUnreachable("down")

    monkeypatch.setattr(TokenService, "delete_principal", broken)
    result = run("principal", "delete", "ann")
    assert result.code != 0 and result.out == ""
    assert NOT_REVOKED in result.err
    assert len(result.calls) == 1


def test_a_custody_that_cannot_be_built_counts_as_not_revoked_and_deletes(
    strava_env: Path,
    database_target: SqliteTarget | PostgresTarget,
    monkeypatch: pytest.MonkeyPatch,
    run: Callable[..., Result],
) -> None:
    use(database_target, monkeypatch)
    seed_deletable(database_target)

    def broken(*_: object, **__: object) -> None:
        raise ValueError("SENTINEL-keyring")

    monkeypatch.setattr(cli, "Keyring", broken)
    result = run("principal", "delete", "ann")
    assert (result.code, result.out, result.err) == (0, "deleted ann\n", NOT_REVOKED)
    assert result.calls == []
    assert stored(database_target, "ann") == (False, False, False)
