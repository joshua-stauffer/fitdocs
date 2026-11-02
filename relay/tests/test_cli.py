"""The operator commands (OperatorCli): outputs, exit codes, ordering, secrets.

Every test calls `cli.main` in-process (the conftest removes inherited
`FITDOCS_RELAY_*` names) except the module-entry test, which spawns an
interpreter with `-B -I`.
"""

from __future__ import annotations

import argparse
import logging
import os
import re
import socket
import sqlite3
import subprocess
import sys
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast
from urllib.parse import quote

import pytest
from tests.test_cli_strava import STRAVA_COMMANDS
from tests.test_config_strava import KEY_ONE, TOKEN
from tests.test_config_strava import env as strava_env

from fitdocs_relay import cli, contract, identity
from fitdocs_relay.config import PostgresTarget, SqliteTarget
from fitdocs_relay.contract import (
    ENV_DATABASE_PASSWORD,
    ENV_DATABASE_URL,
    ENV_EXTENSIONS,
    ENV_HOST,
    ENV_PORT,
    ENV_TOKEN_PEPPER,
)
from fitdocs_relay.seam import SeamError, load_extensions
from fitdocs_relay.storage import open_storage
from fitdocs_relay.storage.interface import (
    Storage,
    StorageError,
    StorageUnreachable,
)
from fitdocs_relay.storage.migrate import migrate, schema_changes

PEPPER = "planted-pepper-" + "p" * 30
PASSWORD = "planted-Passw0rd!"
TARGET_SECRET = "planted-client-secret-" + "s" * 20
TARGET_TOKEN = TOKEN
EXPECTED = len(schema_changes("sqlite"))
TOKEN_LINE = re.compile(r"fdr1_[a-z2-7]{16}_[a-z2-7]{52}\n")
PRINCIPAL_ID = re.compile(r"prn_[a-z2-7]{16}")
T0 = 1_700_000_000  # 2023-11-14T22:13:20Z
ISO_T0 = "2023-11-14T22:13:20Z"


@dataclass
class Result:
    code: int
    out: str
    err: str


class Clock:
    def __init__(self) -> None:
        self.now = T0

    def __call__(self) -> int:
        return self.now


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> Clock:
    fixed = Clock()
    monkeypatch.setattr(cli, "_wall_clock", fixed)
    return fixed


@pytest.fixture(autouse=True)
def _west_coast_time_zone() -> Iterator[None]:
    """Run under a zone that is not UTC, so a local-time rendering differs."""
    previous = os.environ.get("TZ")
    os.environ["TZ"] = "America/Los_Angeles"
    time.tzset()
    yield
    if previous is None:
        del os.environ["TZ"]
    else:
        os.environ["TZ"] = previous
    time.tzset()


@pytest.fixture
def fixed_ids(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Queue 16-character identifiers for the next principals and tokens.

    Each `principal create` takes one; `token mint --new-principal` takes the
    token's, then the principal's; `token mint --principal` takes the token's.
    """
    queue: list[str] = []
    real = identity._random

    def fake(length: int) -> str:
        if length == 16 and queue:
            return queue.pop(0)
        return real(length)

    monkeypatch.setattr(identity, "_random", fake)
    return queue


@pytest.fixture
def db_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    path = tmp_path / "relay.sqlite3"
    monkeypatch.setenv(ENV_DATABASE_URL, f"sqlite:///{path}")
    monkeypatch.setenv(ENV_TOKEN_PEPPER, PEPPER)
    return path


@pytest.fixture
def run(capsys: pytest.CaptureFixture[str]) -> Callable[..., Result]:
    def call(*argv: str) -> Result:
        code = cli.main(list(argv))
        captured = capsys.readouterr()
        return Result(code, captured.out, captured.err)

    return call


@pytest.fixture
def restore_logging() -> Iterator[None]:
    root = logging.getLogger()
    handlers, level = list(root.handlers), root.level
    yield
    root.handlers[:] = handlers
    root.setLevel(level)


def store_at(path: Path) -> Storage:
    return open_storage(SqliteTarget(path))


def migrated(path: Path) -> None:
    store = store_at(path)
    try:
        migrate(store, now=1)
    finally:
        store.close()


def snapshot(store: Storage) -> tuple[Any, ...]:
    """Every principal and token row, verifier included, plus the schema state."""
    tokens = tuple(
        (summary, store.find_token(summary.token_id))
        for summary in store.list_tokens(None)
    )
    return (store.list_principals(), tokens, store.schema_state())


# --- command table ------------------------------------------------------------

SESSION_COMMANDS: list[list[str]] = [
    ["principal", "create"],
    ["principal", "list"],
    ["principal", "delete", "prn_gone"],
    ["token", "mint", "--new-principal"],
    ["token", "mint", "--principal", "prn_gone"],
    ["token", "list"],
    ["token", "list", "--principal", "prn_gone"],
    ["token", "revoke", "gone"],
]
ALL_COMMANDS: list[list[str]] = [
    ["serve"],
    ["migrate"],
    ["migrate", "--check"],
    *SESSION_COMMANDS,
    ["new-pepper"],
]


def test_the_command_list_covers_every_registered_command() -> None:
    pairs = {
        tuple(argv[:2]) for argv in ALL_COMMANDS if argv[0] in ("principal", "token")
    }
    assert pairs == set(cli._SESSION_COMMANDS)
    assert len(pairs) == 6
    covered = [*ALL_COMMANDS, *STRAVA_COMMANDS]  # the Strava rows: test_cli_strava
    assert {argv[0] for argv in covered} == set(contract.COMMANDS)


def test_the_subcommands_are_the_contracts_commands_in_order() -> None:
    parser = cli.build_parser()
    actions = [a for a in parser._actions if isinstance(a, argparse._SubParsersAction)]
    assert len(actions) == 1
    assert tuple(actions[0].choices) == contract.COMMANDS


# --- new-pepper ---------------------------------------------------------------


def test_new_pepper_prints_a_fresh_long_url_safe_secret_and_needs_no_configuration(
    run: Callable[..., Result],
) -> None:
    first = run("new-pepper")
    second = run("new-pepper")
    assert (first.code, first.err, second.code, second.err) == (0, "", 0, "")
    for result in (first, second):
        assert re.fullmatch(r"[A-Za-z0-9_-]{43}\n", result.out)
    assert first.out != second.out


def test_new_pepper_ignores_a_broken_environment(
    monkeypatch: pytest.MonkeyPatch, run: Callable[..., Result]
) -> None:
    monkeypatch.setenv("FITDOCS_RELAY_NOT_A_VARIABLE", "x")
    monkeypatch.setenv(ENV_PORT, "not-a-port")
    result = run("new-pepper")
    assert result.code == 0
    assert re.fullmatch(r"[A-Za-z0-9_-]{43}\n", result.out)


# --- migrate ------------------------------------------------------------------


def test_check_exits_three_before_migration_and_zero_after_and_changes_nothing(
    db_path: Path, run: Callable[..., Result]
) -> None:
    assert EXPECTED >= 1
    before = run("migrate", "--check")
    assert before == Result(3, f"schema 0 -> {EXPECTED}\n", "migrations are pending\n")
    again = run("migrate", "--check")  # check mode applied nothing
    assert again == before

    applied = run("migrate")
    assert applied == Result(0, f"schema 0 -> {EXPECTED}\n", "")

    after = run("migrate", "--check")
    assert after == Result(0, f"schema {EXPECTED} -> {EXPECTED}\n", "")
    rerun = run("migrate")
    assert rerun == Result(0, f"schema {EXPECTED} -> {EXPECTED}\n", "")


def test_migrate_refuses_a_newer_database_naming_both_versions_and_changes_nothing(
    db_path: Path, run: Callable[..., Result]
) -> None:
    migrated(db_path)
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "INSERT INTO relay_schema (version, name, applied_at) VALUES (?, 'x', 1)",
            (EXPECTED + 1,),
        )
    expected_err = (
        f"the database schema is newer than this build (found {EXPECTED + 1}, "
        f"expected {EXPECTED})\n"
    )
    for argv in (("migrate",), ("migrate", "--check")):
        assert run(*argv) == Result(1, "", expected_err)
    with sqlite3.connect(db_path) as connection:
        rows = connection.execute("SELECT version FROM relay_schema").fetchall()
    assert sorted(v for (v,) in rows) == list(range(1, EXPECTED + 2))


# --- the schema gate ----------------------------------------------------------


def test_every_other_command_refuses_a_database_that_is_not_current_and_changes_nothing(
    db_path: Path, run: Callable[..., Result]
) -> None:
    behind = (
        f"the database schema is not current (found 0, expected {EXPECTED}); "
        "run 'fitdocs-relay migrate'\n"
    )
    for argv in SESSION_COMMANDS:
        assert run(*argv) == Result(1, "", behind), argv
    store = store_at(db_path)
    try:
        assert store.schema_state().current == 0  # no table was created
    finally:
        store.close()


def test_every_other_command_refuses_a_database_that_is_ahead_and_changes_nothing(
    db_path: Path, run: Callable[..., Result], clock: Clock
) -> None:
    migrated(db_path)
    assert run("principal", "create", "--label", "kept").code == 0
    assert run("token", "mint", "--new-principal").code == 0
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "INSERT INTO relay_schema (version, name, applied_at) VALUES (?, 'x', 1)",
            (EXPECTED + 1,),
        )
    store = store_at(db_path)
    try:
        before = snapshot(store)
    finally:
        store.close()
    assert len(before[0]) == 2 and len(before[1]) == 1  # a non-trivial subject
    ahead = (
        f"the database schema is newer than this build (found {EXPECTED + 1}, "
        f"expected {EXPECTED})\n"
    )
    for argv in SESSION_COMMANDS:
        assert run(*argv) == Result(1, "", ahead), argv
    store = store_at(db_path)
    try:
        assert snapshot(store) == before
    finally:
        store.close()


def test_a_database_that_cannot_be_reached_or_opened_exits_one_naming_the_condition(
    db_path: Path, run: Callable[..., Result], monkeypatch: pytest.MonkeyPatch
) -> None:
    def unreachable(target: object) -> Storage:
        raise StorageUnreachable("detail that must not be printed")

    def broken(target: object) -> Storage:
        raise StorageError("detail that must not be printed")

    for opener, message in (
        (unreachable, "the database is unreachable\n"),
        (broken, "the database could not be opened\n"),
    ):
        monkeypatch.setattr(cli, "open_storage", opener)
        for argv in ALL_COMMANDS:
            if argv[0] in ("serve", "new-pepper"):
                continue
            assert run(*argv) == Result(1, "", message), argv


def test_a_database_lost_after_opening_exits_one(
    db_path: Path, run: Callable[..., Result], monkeypatch: pytest.MonkeyPatch
) -> None:
    migrated(db_path)
    real = open_storage

    def opener(target: Any) -> Storage:
        store = real(target)

        def lost() -> None:
            raise StorageUnreachable("gone")

        monkeypatch.setattr(store, "schema_state", lost)
        return store

    monkeypatch.setattr(cli, "open_storage", opener)
    assert run("principal", "list") == Result(1, "", "the database is unreachable\n")
    assert run("migrate") == Result(1, "", "the database is unreachable\n")


def test_a_missing_postgres_extra_is_a_configuration_error(
    db_path: Path, run: Callable[..., Result], monkeypatch: pytest.MonkeyPatch
) -> None:
    from fitdocs_relay.storage import POSTGRES_EXTRA_MESSAGE, MissingPostgresSupport

    def missing(target: object) -> Storage:
        raise MissingPostgresSupport(POSTGRES_EXTRA_MESSAGE)

    monkeypatch.setattr(cli, "open_storage", missing)
    assert run("migrate") == Result(2, "", POSTGRES_EXTRA_MESSAGE + "\n")


# --- principals and tokens (every command's output, exit code, order) -----------


def test_the_principal_and_token_commands_print_their_pinned_outputs(
    db_path: Path, run: Callable[..., Result], clock: Clock, fixed_ids: list[str]
) -> None:
    assert run("migrate").code == 0

    # Three principals created in reverse creation-time order, with ids that
    # sort the opposite way from their times (earliest time, highest id).
    clock.now = T0 + 20
    fixed_ids.append("a" * 16)
    third = run("principal", "create", "--label", "third")
    clock.now = T0 + 10
    fixed_ids.append("m" * 16)
    second = run("principal", "create", "--label", "second")
    clock.now = T0
    fixed_ids.append("z" * 16)
    first = run("principal", "create")
    ids = []
    for created in (first, second, third):
        assert (created.code, created.err) == (0, "")
        assert re.fullmatch(PRINCIPAL_ID.pattern + "\n", created.out)
        ids.append(created.out.strip())
    assert ids == ["prn_" + "z" * 16, "prn_" + "m" * 16, "prn_" + "a" * 16]
    assert sorted(ids) != ids  # the time order is not the id order

    listed = run("principal", "list")
    assert listed == Result(
        0,
        f"{ids[0]}\t\t{ISO_T0}\n"
        f"{ids[1]}\tsecond\t2023-11-14T22:13:30Z\n"
        f"{ids[2]}\tthird\t2023-11-14T22:13:40Z\n",
        "",
    )

    # Mint for a new principal: token alone on stdout, ids on stderr.
    clock.now = T0 + 100
    fixed_ids.extend(["b" * 16, "k" * 16])  # the token's id, then the principal's
    minted = run(
        "token", "mint", "--new-principal", "--label", "laptop",
        "--principal-label", "fresh",
    )  # fmt: skip
    assert minted.code == 0
    assert TOKEN_LINE.fullmatch(minted.out)
    token_id = minted.out.split("_")[1]
    err_lines = minted.err.splitlines()
    assert len(err_lines) == 2
    assert err_lines[0] == f"token_id={token_id}"
    assert re.fullmatch(f"principal_id={PRINCIPAL_ID.pattern}", err_lines[1])
    new_principal = err_lines[1].removeprefix("principal_id=")
    assert new_principal not in ids

    # Mint for an existing principal, later.
    clock.now = T0 + 50
    fixed_ids.append("y" * 16)
    second_mint = run("token", "mint", "--principal", ids[0])
    assert second_mint.code == 0 and TOKEN_LINE.fullmatch(second_mint.out)
    second_id = second_mint.out.split("_")[1]
    assert second_mint.err == f"token_id={second_id}\nprincipal_id={ids[0]}\n"

    # Listings: ordered by creation time, no value or verifier, state columns.
    store = store_at(db_path)
    try:
        verifier = store.find_token(token_id)
        assert verifier is not None
    finally:
        store.close()
    token_list = run("token", "list")
    assert token_list == Result(
        0,
        f"{second_id}\t{ids[0]}\t\t2023-11-14T22:14:10Z\tactive\t\n"
        f"{token_id}\t{new_principal}\tlaptop\t2023-11-14T22:15:00Z\tactive\t\n",
        "",
    )
    secret = minted.out.strip().split("_")[2]
    for hidden in (secret, verifier.verifier, "fdr1"):
        assert hidden not in token_list.out
    assert sorted([second_id, token_id]) != [second_id, token_id]
    assert run("principal", "list") == Result(
        0,
        f"{ids[0]}\t\t{ISO_T0}\n"
        f"{ids[1]}\tsecond\t2023-11-14T22:13:30Z\n"
        f"{ids[2]}\tthird\t2023-11-14T22:13:40Z\n"
        f"{new_principal}\tfresh\t2023-11-14T22:15:00Z\n",
        "",
    )

    only = run("token", "list", "--principal", ids[0])
    assert only == Result(
        0, f"{second_id}\t{ids[0]}\t\t2023-11-14T22:14:10Z\tactive\t\n", ""
    )
    none = run("token", "list", "--principal", ids[1])
    assert none == Result(0, "", "")

    # Revoke: the state flips, the time is the revoke time; twice is idempotent.
    clock.now = T0 + 500
    revoked = run("token", "revoke", token_id)
    assert revoked == Result(0, f"revoked {token_id}\n", "")
    clock.now = T0 + 900
    again = run("token", "revoke", token_id)
    assert again == Result(0, f"already revoked {token_id}\n", "")
    after = run("token", "list", "--principal", new_principal)
    assert after == Result(
        0,
        f"{token_id}\t{new_principal}\tlaptop\t2023-11-14T22:15:00Z\trevoked\t"
        "2023-11-14T22:21:40Z\n",
        "",
    )

    # Delete: the principal and its tokens go.
    deleted = run("principal", "delete", ids[0])
    assert deleted == Result(0, f"deleted {ids[0]}\n", "")
    assert ids[0] not in run("principal", "list").out
    assert second_id not in run("token", "list").out


def test_rows_created_in_the_same_second_list_by_id(
    db_path: Path, run: Callable[..., Result], clock: Clock, fixed_ids: list[str]
) -> None:
    assert run("migrate").code == 0
    clock.now = T0 + 30
    for letter, label in (("q", "later-id"), ("b", "earlier-id")):
        fixed_ids.append(letter * 16)
        assert run("principal", "create", "--label", label).code == 0
    assert run("principal", "list") == Result(
        0,
        f"prn_{'b' * 16}\tearlier-id\t2023-11-14T22:13:50Z\n"
        f"prn_{'q' * 16}\tlater-id\t2023-11-14T22:13:50Z\n",
        "",
    )
    owner = f"prn_{'q' * 16}"
    for letter in ("y", "c"):
        fixed_ids.append(letter * 16)
        assert run("token", "mint", "--principal", owner).code == 0
    assert run("token", "list") == Result(
        0,
        f"{'c' * 16}\t{owner}\t\t2023-11-14T22:13:50Z\tactive\t\n"
        f"{'y' * 16}\t{owner}\t\t2023-11-14T22:13:50Z\tactive\t\n",
        "",
    )


def test_times_are_rendered_in_utc_whatever_the_local_zone(
    db_path: Path, run: Callable[..., Result], clock: Clock
) -> None:
    assert time.tzname[0] == "PST"  # the autouse fixture's zone is in force
    assert run("migrate").code == 0
    assert run("principal", "create").code == 0
    assert run("principal", "list").out.endswith(f"\t{ISO_T0}\n")


def test_the_lifecycle_runs_identically_on_both_backends(
    database_target: SqliteTarget | PostgresTarget,
    run: Callable[..., Result],
    clock: Clock,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setenv(ENV_DATABASE_URL, f"sqlite:///{tmp_path}/unused.sqlite3")
    monkeypatch.setenv(ENV_TOKEN_PEPPER, PEPPER)
    monkeypatch.setattr(
        cli, "open_storage", lambda target: open_storage(database_target)
    )
    assert run("migrate", "--check").code == 3
    assert run("migrate") == Result(0, f"schema 0 -> {EXPECTED}\n", "")
    assert run("migrate", "--check").code == 0
    created = run("principal", "create", "--label", "p")
    pid = created.out.strip()
    minted = run("token", "mint", "--principal", pid, "--label", "t")
    token_id = minted.out.split("_")[1]
    assert run("token", "list") == Result(
        0, f"{token_id}\t{pid}\tt\t{ISO_T0}\tactive\t\n", ""
    )
    assert run("token", "revoke", token_id).out == f"revoked {token_id}\n"
    assert run("principal", "delete", pid).out == f"deleted {pid}\n"
    assert run("principal", "list") == Result(0, "", "")
    assert run("token", "list") == Result(0, "", "")


def test_an_unknown_id_exits_one_names_it_and_changes_nothing(
    db_path: Path, run: Callable[..., Result], clock: Clock
) -> None:
    assert run("migrate").code == 0
    pid = run("principal", "create", "--label", "keep").out.strip()
    run("token", "mint", "--principal", pid)
    run("token", "mint", "--new-principal")
    store = store_at(db_path)
    try:
        before = snapshot(store)
    finally:
        store.close()
    assert len(before[0]) == 2 and len(before[1]) == 2

    cases = [
        (("principal", "delete", "prn_missing"), "unknown principal: prn_missing\n"),
        (("token", "revoke", "tokmissing"), "unknown token: tokmissing\n"),
        (
            ("token", "mint", "--principal", "prn_missing"),
            "unknown principal: prn_missing\n",
        ),
        (
            ("token", "list", "--principal", "prn_missing"),
            "unknown principal: prn_missing\n",
        ),
        (
            ("token", "mint", "--principal", "prn_missing", "--label", "x"),
            "unknown principal: prn_missing\n",
        ),
    ]
    for argv, message in cases:
        assert run(*argv) == Result(1, "", message), argv
    store = store_at(db_path)
    try:
        assert snapshot(store) == before
    finally:
        store.close()


def test_a_secret_typed_as_an_unknown_id_is_not_echoed(
    db_path: Path, run: Callable[..., Result]
) -> None:
    assert run("migrate").code == 0
    assert run("principal", "delete", PEPPER) == Result(
        1, "", "unknown principal: [redacted]\n"
    )
    token = "fdr1_" + "a" * 16 + "_" + "b" * 52
    assert run("token", "revoke", token) == Result(1, "", "unknown token: [redacted]\n")


def test_a_listing_redacts_a_label_that_is_a_secret(
    db_path: Path, run: Callable[..., Result], clock: Clock
) -> None:
    assert run("migrate").code == 0
    assert run("principal", "create", "--label", PEPPER[:64]).code == 0
    listed = run("principal", "list")
    assert listed.out.endswith(f"\t{ISO_T0}\n") and PEPPER not in listed.out
    assert "\t[redacted]\t" in listed.out


# --- usage rules ----------------------------------------------------------------


def test_principal_label_with_an_existing_principal_is_refused_before_anything_runs(
    db_path: Path, run: Callable[..., Result], clock: Clock
) -> None:
    assert run("migrate").code == 0
    pid = run("principal", "create").out.strip()
    store = store_at(db_path)
    try:
        before = snapshot(store)
    finally:
        store.close()
    result = run("token", "mint", "--principal", pid, "--principal-label", "ignored")
    assert result == Result(
        2, "", "fitdocs-relay: --principal-label needs --new-principal\n"
    )
    store = store_at(db_path)
    try:
        assert snapshot(store) == before
    finally:
        store.close()


@pytest.mark.parametrize(
    "argv",
    [
        ["token", "mint"],
        ["token", "mint", "--principal", "p", "--new-principal"],
        ["token", "mint", "--new-principal", "--label", ""],
        ["token", "mint", "--new-principal", "--label", "x" * 65],
        ["token", "mint", "--new-principal", "--label", "a\tb"],
        ["token", "mint", "--new-principal", "--principal-label", "a\nb"],
        ["principal", "create", "--label", "x" * 65],
        ["principal"],
        ["token"],
        ["frobnicate"],
        [],
    ],
)
def test_a_usage_error_exits_two_and_prints_nothing_on_stdout(
    argv: list[str], db_path: Path, run: Callable[..., Result]
) -> None:
    migrated(db_path)
    result = run(*argv)
    assert result.code == 2 and result.out == "" and result.err
    store = store_at(db_path)
    try:
        assert store.list_principals() == ()  # nothing was created
    finally:
        store.close()


def test_a_usage_error_does_not_echo_a_pasted_secret(
    db_path: Path, run: Callable[..., Result], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(ENV_DATABASE_URL, "postgresql://relay@127.0.0.1:1/relay")
    monkeypatch.setenv(ENV_DATABASE_PASSWORD, PASSWORD)
    token = "fdr1_" + "a" * 16 + "_" + "b" * 52
    for secret in (PEPPER, PASSWORD, token):
        result = run("principal", "delete", "x", secret)
        assert result.code == 2 and result.out == ""
        assert "unrecognized arguments: [redacted]" in result.err
        assert secret not in result.err
    # A password embedded in the raw URL (userinfo, or the password query
    # parameter), as written, decoded and re-encoded; the password variable unset.
    monkeypatch.delenv(ENV_DATABASE_PASSWORD)
    embedded = "p@ss w/rd%1"
    encoded = quote(embedded, safe="")
    for url in (
        f"postgresql://relay:{encoded}@127.0.0.1:1/relay",
        f"postgres://relay@127.0.0.1:1/relay?password={encoded}",
    ):
        monkeypatch.setenv(ENV_DATABASE_URL, url)
        for secret in (embedded, encoded):
            result = run("principal", "delete", "x", secret)
            assert result.code == 2
            assert "unrecognized arguments: [redacted]" in result.err
            assert secret not in result.err
    # A URL that cannot be read neither breaks the error output nor hides it.
    monkeypatch.setenv(ENV_DATABASE_URL, "postgresql://[bad")
    result = run("principal", "delete", "x", "plain")
    assert result.code == 2 and "unrecognized arguments: plain" in result.err
    # The password variable is redacted on its own when the URL contributes
    # nothing (a SQLite URL), not only through the PostgreSQL target.
    monkeypatch.setenv(ENV_DATABASE_URL, "sqlite:///relay.db")
    monkeypatch.setenv(ENV_DATABASE_PASSWORD, PASSWORD)
    result = run("principal", "delete", "x", PASSWORD)
    assert result.code == 2
    assert "unrecognized arguments: [redacted]" in result.err
    assert PASSWORD not in result.err
    monkeypatch.delenv(ENV_DATABASE_PASSWORD)
    # With no secret in the environment nothing is replaced.
    monkeypatch.delenv(ENV_DATABASE_URL)
    monkeypatch.delenv(ENV_TOKEN_PEPPER)
    assert (
        "unrecognized arguments: plain" in run("principal", "delete", "x", "plain").err
    )


def test_a_label_of_sixty_four_printable_characters_is_accepted(
    db_path: Path, run: Callable[..., Result], clock: Clock
) -> None:
    assert run("migrate").code == 0
    label = "é" + "x" * 62 + "ß"
    assert len(label) == 64
    assert run("principal", "create", "--label", label).code == 0
    assert f"\t{label}\t" in run("principal", "list").out


# --- configuration errors ---------------------------------------------------------


def test_every_command_but_new_pepper_reports_a_configuration_error_with_exit_two(
    run: Callable[..., Result],
) -> None:
    for argv in ALL_COMMANDS:
        if argv[0] == "new-pepper":
            continue
        assert run(*argv) == Result(
            2, "", "FITDOCS_RELAY_DATABASE_URL: is required\n"
        ), argv


def configured_targets(db_path: Path, monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """The target secrets in the environment: the client secret planted, the
    rest from the test configuration. Returned as the forms to look for."""
    for name, value in strava_env(
        {"FITDOCS_RELAY_STRAVA_CLIENT_SECRET": TARGET_SECRET}
    ).items():
        if name not in (ENV_DATABASE_URL, ENV_TOKEN_PEPPER):
            monkeypatch.setenv(name, value)
    key_text = KEY_ONE.partition(":")[2]
    return [TARGET_SECRET, TARGET_TOKEN, KEY_ONE, key_text]


def test_a_failing_operator_command_does_not_print_a_target_secret(
    db_path: Path, run: Callable[..., Result], monkeypatch: pytest.MonkeyPatch
) -> None:
    migrated(db_path)
    secrets = configured_targets(db_path, monkeypatch)
    assert len(set(secrets)) == 4
    for secret in secrets:
        result = run("principal", "delete", secret)
        assert result.code == 1 and result.out == ""
        assert result.err.endswith(": [redacted]\n"), result.err
        assert secret not in result.err


def test_a_usage_error_does_not_echo_a_pasted_target_secret(
    db_path: Path, run: Callable[..., Result], monkeypatch: pytest.MonkeyPatch
) -> None:
    secrets = configured_targets(db_path, monkeypatch)
    for secret in secrets:
        result = run("principal", "delete", "x", secret)
        assert result.code == 2 and result.out == ""
        assert "unrecognized arguments: [redacted]" in result.err
        assert secret not in result.err
    # A key list that is not valid still hides what it holds, and a value
    # that holds no key leaves the output alone.
    monkeypatch.setenv("FITDOCS_RELAY_ENCRYPTION_KEYS", "k9:not-a-key, x")
    result = run("principal", "delete", "x", "k9:not-a-key")
    assert "unrecognized arguments: [redacted]" in result.err
    result = run("principal", "delete", "x", "x")
    assert "unrecognized arguments: x" in result.err


def test_configuration_errors_name_the_variable_and_never_print_its_value(
    db_path: Path, run: Callable[..., Result], monkeypatch: pytest.MonkeyPatch
) -> None:
    short = "short-secret-value"
    monkeypatch.setenv(ENV_TOKEN_PEPPER, short)
    for argv in SESSION_COMMANDS:
        assert run(*argv) == Result(
            2, "", "FITDOCS_RELAY_TOKEN_PEPPER: must be at least 43 characters\n"
        )
    monkeypatch.setenv(ENV_TOKEN_PEPPER, PEPPER)
    monkeypatch.setenv(ENV_PORT, "70000" + PASSWORD)
    assert run("migrate") == Result(
        2, "", "FITDOCS_RELAY_PORT: must be an integer from 1 to 65535\n"
    )
    monkeypatch.delenv(ENV_PORT)
    monkeypatch.setenv("FITDOCS_RELAY_" + "MYSTERY", PASSWORD)
    assert run("migrate") == Result(
        2,
        "",
        "FITDOCS_RELAY_MYSTERY: unknown variable with the reserved prefix "
        "FITDOCS_RELAY_\n",
    )


# --- serve -----------------------------------------------------------------------


def test_serve_returns_run_servers_code_with_the_loaded_configuration(
    db_path: Path, run: Callable[..., Result], monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[Any] = []

    def fake(config: Any) -> int:
        seen.append(config)
        return len(seen) - 1

    monkeypatch.setattr(cli, "run_server", fake)
    assert run("serve") == Result(0, "", "")
    assert run("serve") == Result(1, "", "")
    assert [c.pepper for c in seen] == [PEPPER.encode()] * 2
    assert seen[0].database == SqliteTarget(db_path)


def test_serve_does_not_require_the_schema_the_readiness_probe_reports_it(
    db_path: Path, run: Callable[..., Result], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli, "run_server", lambda config: 0)
    assert not db_path.exists()
    assert run("serve") == Result(0, "", "")
    assert not db_path.exists()  # the command itself opened nothing


def test_serve_without_the_postgres_extra_is_a_configuration_error(
    db_path: Path, run: Callable[..., Result], monkeypatch: pytest.MonkeyPatch
) -> None:
    from fitdocs_relay.storage import POSTGRES_EXTRA_MESSAGE, MissingPostgresSupport

    def missing(config: Any) -> int:
        raise MissingPostgresSupport(POSTGRES_EXTRA_MESSAGE)

    monkeypatch.setattr(cli, "run_server", missing)
    assert run("serve") == Result(2, "", POSTGRES_EXTRA_MESSAGE + "\n")


@pytest.mark.parametrize("code", [0, None])
def test_a_clean_system_exit_from_the_server_is_success(
    code: int | None,
    db_path: Path,
    run: Callable[..., Result],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def stops(config: Any) -> int:
        raise SystemExit(code)

    monkeypatch.setattr(cli, "run_server", stops)
    assert run("serve") == Result(0, "", "")


def test_a_schema_that_turns_out_ahead_during_migrate_exits_one_with_its_message(
    db_path: Path, run: Callable[..., Result], monkeypatch: pytest.MonkeyPatch
) -> None:
    from fitdocs_relay.storage.interface import SchemaAhead

    def refuses(storage: Storage, *, now: int) -> None:
        raise SchemaAhead("the database is at schema version 9, newer than 1")

    monkeypatch.setattr(cli, "migrate", refuses)
    assert run("migrate") == Result(
        1, "", "the database is at schema version 9, newer than 1\n"
    )


def test_a_uvicorn_startup_failure_exits_one_never_three(
    db_path: Path, run: Callable[..., Result], monkeypatch: pytest.MonkeyPatch
) -> None:
    def startup_failure(config: Any) -> int:
        raise SystemExit(3)

    monkeypatch.setattr(cli, "run_server", startup_failure)
    assert run("serve") == Result(1, "", "the server could not start\n")


def test_serving_on_a_port_that_is_taken_exits_one_for_real(
    db_path: Path,
    run: Callable[..., Result],
    monkeypatch: pytest.MonkeyPatch,
    restore_logging: None,
) -> None:
    migrated(db_path)
    with socket.socket() as taken:
        taken.bind(("127.0.0.1", 0))
        taken.listen()
        monkeypatch.setenv(ENV_HOST, "127.0.0.1")
        monkeypatch.setenv(ENV_PORT, str(taken.getsockname()[1]))
        result = run("serve")
    assert result.code == 1
    assert result.err == "the server could not start\n"
    assert PEPPER not in result.out


def test_a_seam_error_exits_two_with_its_message(
    db_path: Path,
    run: Callable[..., Result],
    monkeypatch: pytest.MonkeyPatch,
    restore_logging: None,
) -> None:
    reference = "fitdocs_relay_no_such_module:extension"
    monkeypatch.setenv(ENV_EXTENSIONS, reference)
    with pytest.raises(SeamError) as raised:
        load_extensions((reference,))
    result = run("serve")
    assert result.code == 2
    assert result.err == str(raised.value) + "\n"
    assert reference in result.err and result.out == ""


# --- no secret in any output ------------------------------------------------------


class Exploding:
    """A storage whose every data operation fails with the secrets in its message."""

    def __init__(
        self,
        inner: Storage,
        error: Callable[[str], BaseException] = RuntimeError,
    ) -> None:
        self._inner = inner
        self._error = error

    def __getattr__(self, name: str) -> Any:
        if name in ("schema_state", "close", "backend", "ping"):
            return getattr(self._inner, name)

        def fail(*args: Any, **kwargs: Any) -> Any:
            raise self._error(f"{PASSWORD} {PEPPER} {quote(PASSWORD, safe='')}")

        return fail


def secret_forms() -> tuple[str, ...]:
    return (PASSWORD, quote(PASSWORD, safe=""), PEPPER)


ENV_VARIANTS = {
    "variable": {
        ENV_DATABASE_URL: "postgresql://relay@127.0.0.1:1/relay",
        ENV_DATABASE_PASSWORD: PASSWORD,
    },
    "url": {
        ENV_DATABASE_URL: (
            f"postgresql://relay:{quote(PASSWORD, safe='')}@127.0.0.1:1/relay"
        ),
    },
}


def seed(path: Path) -> None:
    """Rows whose labels are the secrets, so a listing has something to redact."""
    store = store_at(path)
    try:
        migrate(store, now=1)
        from fitdocs_relay.identity import TokenService

        service = TokenService(store, pepper=PEPPER.encode(), clock=lambda: T0)
        service.mint(principal_id=None, label=PASSWORD, principal_label=PEPPER[:64])
    finally:
        store.close()


def scan(result: Result) -> None:
    text = result.out + result.err
    for secret in secret_forms():
        assert secret not in text


@pytest.mark.parametrize("variant", sorted(ENV_VARIANTS))
def test_no_command_prints_the_password_or_the_pepper_when_it_succeeds_or_refuses(
    variant: str,
    tmp_path: Path,
    run: Callable[..., Result],
    monkeypatch: pytest.MonkeyPatch,
    clock: Clock,
) -> None:
    for name, value in ENV_VARIANTS[variant].items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv(ENV_TOKEN_PEPPER, PEPPER)
    path = tmp_path / "real.sqlite3"
    seed(path)
    monkeypatch.setattr(cli, "open_storage", lambda target: store_at(path))
    monkeypatch.setattr(cli, "run_server", lambda config: 0)

    # Healthy: ids typed as the secrets are echoed redacted.
    secret_ids = {
        ("principal", "delete"): ["principal", "delete", PASSWORD],
        ("token", "revoke"): ["token", "revoke", PEPPER],
        ("token", "mint"): ["token", "mint", "--principal", quote(PASSWORD, safe="")],
        ("token", "list"): ["token", "list", "--principal", PASSWORD],
    }
    scanned = 0
    for argv in ALL_COMMANDS:
        key = tuple(argv[:2])
        argv = secret_ids.get(key, argv)  # type: ignore[arg-type]
        result = run(*argv)
        scan(result)
        scanned += 1
        if key in secret_ids:
            assert result.code == 1
            assert result.err.endswith(": [redacted]\n"), argv
    assert scanned == len(ALL_COMMANDS)
    listing = run("principal", "list")
    assert "[redacted]" in listing.out and listing.code == 0
    scan(listing)
    assert "[redacted]" in run("token", "list").out

    # Every error path, for every command that opens the database.
    def exploding_open(target: object) -> Storage:
        return cast(Storage, Exploding(store_at(path)))

    def raising(error: BaseException) -> Callable[[object], Storage]:
        def opener(target: object) -> Storage:
            raise error

        return opener

    from fitdocs_relay.storage import MissingPostgresSupport

    secret_text = f"{PASSWORD} {PEPPER} {quote(PASSWORD, safe='')}"
    openers = {
        "explodes": exploding_open,
        "unreachable": raising(StorageUnreachable(secret_text)),
        "storage-error": raising(StorageError(secret_text)),
        "missing-extra": raising(MissingPostgresSupport("install the extra")),
    }
    for label, opener in openers.items():
        monkeypatch.setattr(cli, "open_storage", opener)
        for argv in ALL_COMMANDS:
            if argv[0] in ("serve", "new-pepper"):
                continue
            result = run(*argv)
            scan(result)
            if label == "explodes" and argv[0] == "migrate":
                continue  # migrate touches only the schema, which does not fail
            assert result.code in (1, 2), (label, argv)
            assert result.err, (label, argv)

    def serve_fails(config: object) -> int:
        raise RuntimeError(secret_text)

    monkeypatch.setattr(cli, "run_server", serve_fails)
    result = run("serve")
    scan(result)
    assert result == Result(1, "", "unexpected failure: RuntimeError\n")

    def seam_fails(config: object) -> int:
        raise SeamError(f"extension 'x': {PASSWORD}")

    # A wrapper's own message is its own; the redactor still runs over it.
    monkeypatch.setattr(cli, "run_server", seam_fails)
    result = run("serve")
    scan(result)
    assert result == Result(2, "", "extension 'x': [redacted]\n")


def test_a_storage_error_during_an_operation_reports_only_its_type(
    db_path: Path, run: Callable[..., Result], monkeypatch: pytest.MonkeyPatch
) -> None:
    migrated(db_path)
    monkeypatch.setenv(ENV_TOKEN_PEPPER, PEPPER)

    def failing(target: object) -> Storage:
        return cast(Storage, Exploding(store_at(db_path), StorageError))

    monkeypatch.setattr(cli, "open_storage", failing)
    for argv in (["principal", "list"], ["token", "list"], ["principal", "create"]):
        result = run(*argv)
        assert result == Result(1, "", "unexpected failure: StorageError\n"), argv


def test_storage_is_closed_exactly_once_on_every_exit_path(
    db_path: Path, run: Callable[..., Result], monkeypatch: pytest.MonkeyPatch
) -> None:
    migrated(db_path)
    closes: list[str] = []

    class Counting:
        def __init__(self) -> None:
            self._inner = store_at(db_path)

        def __getattr__(self, name: str) -> Any:
            return getattr(self._inner, name)

        def close(self) -> None:
            closes.append("close")
            self._inner.close()

    monkeypatch.setattr(cli, "open_storage", lambda target: Counting())
    runs = [
        ["principal", "list"],  # success
        ["principal", "delete", "prn_missing"],  # unknown id
        ["migrate", "--check"],
        ["migrate"],
    ]
    for argv in runs:
        closes.clear()
        run(*argv)
        assert closes == ["close"], argv
    with sqlite3.connect(db_path) as connection:
        connection.execute(
            "INSERT INTO relay_schema (version, name, applied_at) VALUES (?, 'x', 1)",
            (EXPECTED + 1,),
        )
    for argv in (["principal", "list"], ["migrate"]):  # refused by the gate
        closes.clear()
        assert run(*argv).code == 1
        assert closes == ["close"], argv


def test_a_failing_operation_reports_only_the_error_type(
    db_path: Path, run: Callable[..., Result], monkeypatch: pytest.MonkeyPatch
) -> None:
    migrated(db_path)

    def explode(target: object) -> Storage:
        return cast(Storage, Exploding(store_at(db_path)))

    monkeypatch.setattr(cli, "open_storage", explode)
    assert run("principal", "list") == Result(
        1, "", "unexpected failure: RuntimeError\n"
    )


# --- the module entry point ---------------------------------------------------------


def test_python_dash_m_runs_the_same_command() -> None:
    env = {k: v for k, v in os.environ.items() if not k.startswith("FITDOCS_RELAY_")}
    pepper = subprocess.run(
        [sys.executable, "-B", "-I", "-m", "fitdocs_relay", "new-pepper"],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert pepper.returncode == 0 and pepper.stderr == ""
    assert re.fullmatch(r"[A-Za-z0-9_-]{43}\n", pepper.stdout)
    usage = subprocess.run(
        [sys.executable, "-B", "-I", "-m", "fitdocs_relay", "token"],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert usage.returncode == 2 and usage.stdout == ""
