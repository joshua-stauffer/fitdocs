"""The Strava operator commands (task 4.5): each state, each exit code, no secret.

Every test calls `cli.main` in-process. Strava is the scripted outbound
(`cli.urllib_outbound` is replaced), so a request nobody scripted raises
`UnscriptedCall`, and `Result.calls` lists the requests that left.
"""

from __future__ import annotations

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
from fitdocs_relay.outbound import OutboundError
from fitdocs_relay.storage import open_storage
from fitdocs_relay.storage.interface import (
    NewConnection,
    NewPrincipal,
    SealedTokens,
)
from fitdocs_relay.storage.migrate import migrate

P = "FITDOCS_RELAY_"
API: Final = "https://api.example/v3"
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
