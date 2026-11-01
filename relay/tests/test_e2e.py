"""The relay end to end, across the real process boundary, with planted secrets.

One server (`python -m fitdocs_relay serve`) serves while operator commands run
against the same database from other processes: mint, check, revoke by command,
then the next request answers `token-revoked`; registration through a test
provider; rate limiting; a failure path. The planted values are the pepper (an
environment input), the registration email and poll secret (request bodies),
the minted, registered and logged tokens (each whole and as its secret part),
and, on PostgreSQL, the database password: once in
`FITDOCS_RELAY_DATABASE_PASSWORD` (the main run) and once embedded in the
URL's userinfo (`test_a_password_in_the_url_...`). SQLite cannot take a
password (the contract refuses one), so its leg plants it only in a refusal
test. Every captured stdout and stderr of the server and of each command is
scanned for each value. One stream is exempt: the stdout of `token mint`,
which prints the token once by design; the exemption applies only after that
stdout is asserted to be exactly one token and a newline.
Runs on both backends (Requirements 3.5, 9.8).
"""

from __future__ import annotations

import getpass
import http.client
import json
import os
import re
import socket
import subprocess
import sys
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import IO
from urllib.parse import quote, unquote, urlsplit

import pytest
from tests.conftest import TEST_PEPPER

from fitdocs_relay.config import PostgresTarget, SqliteTarget
from fitdocs_relay.contract import (
    ENV_CLIENT_RATE_LIMIT,
    ENV_DATABASE_PASSWORD,
    ENV_DATABASE_URL,
    ENV_EXTENSIONS,
    ENV_HOST,
    ENV_LOG_LEVEL,
    ENV_PORT,
    ENV_SHUTDOWN_GRACE,
    ENV_TOKEN_PEPPER,
    ENV_TOKEN_RATE_LIMIT,
)
from fitdocs_relay.shared.relay_envelope import encode_request

CHILD_DIR = Path(__file__).parent / "e2e_child"
WAIT_S = 30.0
TOKEN_LIMIT = 4
CLIENT_LIMIT = 12

PEPPER = TEST_PEPPER
EMAIL = "planted.e2e.person@example.test"
FAILING_EMAIL = "fail.planted.e2e.person@example.test"
POLL_SECRET = "Pq7-planted_e2e-poll-secret_Zk3wLm9xRv2Tb5Nc8Hd4Ys1Jf6"
PLANTED_PASSWORD = "planted-e2e-db-password-Vn4Qz8"
USER_CODE = "BCDF-GHJK"
EXPECTED_SECRETS = {
    "pepper",
    "email",
    "poll secret",
    "failing email",
    "minted token",
    "minted token secret",
    "registered token",
    "registered token secret",
    "logged token",
    "logged token secret",
}
MINT_STDOUT = "cli token mint --new-principal stdout"


# --- processes ---------------------------------------------------------------


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


@dataclass
class Captured:
    """One process's whole output, kept under a label for the scan."""

    label: str
    stdout: str
    stderr: str


@dataclass
class Deployment:
    env: dict[str, str]
    port: int
    secrets: dict[str, str]
    captures: list[Captured] = field(default_factory=list)
    unscanned: set[str] = field(default_factory=set)
    server: subprocess.Popen[str] | None = None
    exit_code: int | None = None
    _sinks: list[IO[str]] = field(default_factory=list)

    def start_server(self, directory: Path) -> None:
        out = (directory / "serve.out").open("w+", encoding="utf-8")
        err = (directory / "serve.err").open("w+", encoding="utf-8")
        self._sinks = [out, err]
        self.server = subprocess.Popen(
            [sys.executable, "-B", "-s", "-E", "-m", "fitdocs_relay", "serve"],
            env=self.env,
            stdin=subprocess.DEVNULL,
            stdout=out,
            stderr=err,
            cwd=str(CHILD_DIR),
            text=True,
        )

    def output_so_far(self) -> str:
        return "".join(_read(sink) for sink in self._sinks)

    def stop(self) -> None:
        """End the server (SIGTERM, then kill after a timeout) and keep its output."""
        server = self.server
        if server is None:
            return
        self.server = None
        if server.poll() is None:
            server.terminate()
        try:
            server.wait(timeout=WAIT_S)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait(timeout=WAIT_S)
        out, err = self._sinks
        self.exit_code = server.returncode
        self.captures.append(Captured("serve", _read(out), _read(err)))
        for sink in self._sinks:
            sink.close()
        self._sinks = []

    def command(self, *args: str) -> subprocess.CompletedProcess[str]:
        """An operator command against the same database; output is captured."""
        done = subprocess.run(
            [sys.executable, "-B", "-I", "-m", "fitdocs_relay", *args],
            env=self.env,
            capture_output=True,
            text=True,
            timeout=WAIT_S,
            check=False,
            cwd=str(CHILD_DIR),
        )
        label = " ".join(args) if args == ("migrate",) else "cli " + " ".join(args)
        self.captures.append(Captured(label, done.stdout, done.stderr))
        return done

    def request(
        self, method: str, path: str, *, token: str | None = None, body: bytes = b""
    ) -> tuple[int, dict[str, object]]:
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=20)
        try:
            headers = {"Content-Length": str(len(body))}
            if token is not None:
                headers["Authorization"] = f"Bearer {token}"
            connection.request(method, path, body=body or None, headers=headers)
            response = connection.getresponse()
            parsed = json.loads(response.read().decode("utf-8"))
            assert isinstance(parsed, dict)
            return response.status, parsed
        finally:
            connection.close()


def child_env(
    database_url: str, port: int, password: str | None, home: Path
) -> dict[str, str]:
    """The whole environment of every child: no inherited FITDOCS_RELAY_* name."""
    env = {
        name: value
        for name, value in os.environ.items()
        if not name.startswith(("FITDOCS_RELAY_", "PYTHON", "FORWARDED_"))
    }
    env.update(
        {
            ENV_DATABASE_URL: database_url,
            ENV_TOKEN_PEPPER: PEPPER,
            ENV_HOST: "127.0.0.1",
            ENV_PORT: str(port),
            ENV_SHUTDOWN_GRACE: "5",
            ENV_LOG_LEVEL: "info",
            ENV_EXTENSIONS: "e2e_extension:EXTENSION",
            ENV_TOKEN_RATE_LIMIT: str(TOKEN_LIMIT),
            ENV_CLIENT_RATE_LIMIT: str(CLIENT_LIMIT),
            "E2E_POLL_SECRET": POLL_SECRET,
            "E2E_LOGGED_TOKEN_FILE": str(home / "logged-token"),
            "PYTHONDONTWRITEBYTECODE": "1",
            "HOME": str(home),
        }
    )
    if password is not None:
        env[ENV_DATABASE_PASSWORD] = password
    return env


def postgres_url(
    target: PostgresTarget, test_url: str, *, embed_password: bool = False
) -> tuple[str, str | None]:
    """The test schema as a contract URL, and the password it needs.

    By default the URL carries no password and the second value is the password
    for `FITDOCS_RELAY_DATABASE_PASSWORD`, the contract's own input for it (the
    decoded password of `test_url`, else a planted one, which a server that
    needs none ignores). With `embed_password` the password is in the URL's
    userinfo, percent-encoded, and the second value is None.
    """
    import psycopg.conninfo

    schema = str(psycopg.conninfo.conninfo_to_dict(target.conninfo)["options"])
    parts = urlsplit(test_url)
    userinfo, _, hostport = parts.netloc.rpartition("@")
    user, _, raw_password = userinfo.partition(":")
    password = unquote(raw_password) if raw_password else PLANTED_PASSWORD
    if embed_password:
        user = user or quote(getpass.getuser(), safe="")
        userinfo = f"{user}:{quote(password, safe='')}"
    else:
        userinfo = user
    netloc = f"{userinfo}@{hostport}" if userinfo else hostport
    options = f"options={quote(schema, safe='')}"
    query = f"{parts.query}&{options}" if parts.query else options
    url = f"{parts.scheme}://{netloc}{parts.path}?{query}"
    return url, None if embed_password else password


@pytest.fixture
def deployment(
    database_target: SqliteTarget | PostgresTarget,
    request: pytest.FixtureRequest,
    tmp_path: Path,
) -> Iterator[Deployment]:
    port = free_port()
    if isinstance(database_target, SqliteTarget):
        url = f"sqlite:///{database_target.path}"
        password = None
    else:
        test_url: str = request.getfixturevalue("postgres_test_url")
        url, password = postgres_url(database_target, test_url)
    secrets = {"pepper": PEPPER, "email": EMAIL, "poll secret": POLL_SECRET}
    secrets["failing email"] = FAILING_EMAIL
    if password is not None:
        secrets["database password"] = password
    home = tmp_path / "home"
    home.mkdir()
    deployed = Deployment(child_env(url, port, password, home), port, secrets)

    migrated = deployed.command("migrate")
    assert migrated.returncode == 0, migrated.stderr
    yield from serving(deployed, tmp_path)


def serving(deployed: Deployment, directory: Path) -> Iterator[Deployment]:
    """Start the server on a migrated database; stop it however the caller ends."""
    deployed.start_server(directory)
    try:
        deadline = time.monotonic() + WAIT_S
        while True:
            assert deployed.server is not None and deployed.server.poll() is None, (
                deployed.output_so_far()
            )
            try:
                if deployed.request("GET", "/livez")[0] == 200:
                    break
            except (OSError, ValueError):
                pass
            assert time.monotonic() < deadline, "the server never answered /livez"
            time.sleep(0.1)
        yield deployed
    finally:
        deployed.stop()


def _read(handle: IO[str]) -> str:
    handle.flush()
    handle.seek(0)
    return handle.read()


# --- the scan ----------------------------------------------------------------


def leaks(
    captures: list[Captured], secrets: dict[str, str], skip: set[str]
) -> list[str]:
    """Every (stream, secret name) where a planted value appears in the output."""
    found: list[str] = []
    for capture in captures:
        for stream, text in (("stdout", capture.stdout), ("stderr", capture.stderr)):
            if f"{capture.label} {stream}" in skip:
                continue
            found.extend(
                f"{capture.label} {stream}: {name}"
                for name, value in secrets.items()
                if value in text
            )
    return found


def server_records(captures: list[Captured]) -> list[dict[str, object]]:
    serve = next(c for c in captures if c.label == "serve")
    records = []
    for line in serve.stdout.splitlines():
        parsed = json.loads(line)
        assert isinstance(parsed, dict)
        records.append(parsed)
    return records


# --- the exercise ------------------------------------------------------------


def code_of(answer: dict[str, object]) -> object:
    return answer["code"]


def test_the_relay_end_to_end_leaks_no_planted_secret(deployment: Deployment) -> None:
    d = deployment

    # mint by operator command; the token is on stdout, alone, by design
    minted = d.command("token", "mint", "--new-principal")
    assert minted.returncode == 0, minted.stderr
    assert re.fullmatch(r"fdr1_[A-Za-z0-9]{16}_[A-Za-z0-9_-]{52}\n", minted.stdout)
    token = minted.stdout.strip()
    d.secrets["minted token"] = token
    d.secrets["minted token secret"] = token.split("_", 2)[2]
    d.unscanned.add(MINT_STDOUT)  # prints it, once
    token_id = token.split("_")[1]
    assert f"token_id={token_id}\n" in minted.stderr

    # check: the token is valid, and the operator can see it live
    status, answer = d.request("GET", "/v1/token", token=token)
    assert (status, code_of(answer)) == (200, "ok")
    listing = d.command("token", "list")
    assert listing.returncode == 0 and token_id in listing.stdout

    # revoke by command; the next request answers token-revoked
    revoked = d.command("token", "revoke", token_id)
    assert revoked.returncode == 0, revoked.stderr
    status, answer = d.request("GET", "/v1/token", token=token)
    assert (status, code_of(answer)) == (401, "token-revoked")

    # registration through the test provider
    status, answer = d.request(
        "POST", "/v1/registrations", body=encode_request({"email": EMAIL})
    )
    assert (status, code_of(answer)) == (200, "registration-started")
    started = answer["data"]
    assert isinstance(started, dict) and started["user_code"] == USER_CODE
    status, answer = d.request(
        "POST",
        "/v1/registrations/poll",
        body=encode_request({"poll_secret": POLL_SECRET}),
    )
    assert (status, code_of(answer)) == (200, "registration-issued")
    issued = answer["data"]
    assert isinstance(issued, dict)
    registered = str(issued["token"])
    d.secrets["registered token"] = registered
    d.secrets["registered token secret"] = registered.split("_", 2)[2]
    status, answer = d.request("GET", "/v1/token", token=registered)
    assert (status, code_of(answer)) == (200, "ok")

    # a failure path: the provider raises with the email and poll secret in its message
    status, answer = d.request(
        "POST", "/v1/registrations", body=encode_request({"email": FAILING_EMAIL})
    )
    assert (status, code_of(answer)) == (500, "relay-failure")
    logged = Path(d.env["E2E_LOGGED_TOKEN_FILE"]).read_text(encoding="utf-8")
    d.secrets["logged token"] = logged
    d.secrets["logged token secret"] = logged.split("_", 2)[2]

    # rate limiting: the registered token's own window fills (a window rolling
    # over mid-test only delays it, hence the doubled bound)
    limited = None
    for _ in range(2 * TOKEN_LIMIT + 2):
        status, answer = d.request("GET", "/v1/token", token=registered)
        if code_of(answer) == "rate-limited":
            limited = (status, answer)
            break
    assert limited is not None, "the token limit never answered rate-limited"
    assert limited[0] == 429

    # end the server so its output is complete, then scan everything captured
    d.stop()
    assert d.unscanned == {MINT_STDOUT}, "only the mint's own stdout is exempt"
    assert leaks(d.captures, d.secrets, d.unscanned) == []
    scanned = {(c.label, stream) for c in d.captures for stream in ("stdout", "stderr")}
    assert scanned >= {
        ("migrate", "stdout"),
        ("serve", "stdout"),
        ("serve", "stderr"),
        ("cli token revoke " + token_id, "stderr"),
        ("cli token list", "stdout"),
    }
    assert d.exit_code == 0
    assert set(d.secrets) == EXPECTED_SECRETS | (
        {"database password"} if "database password" in d.secrets else set()
    )
    assert all(len(v) >= 8 for v in d.secrets.values())

    # non-vacuity: the log holds the events the exercise caused
    records = server_records(d.captures)
    requests = [r for r in records if r.get("event") == "request"]
    revoked_record = [r for r in requests if r.get("code") == "token-revoked"]
    assert len(revoked_record) == 1
    assert (
        revoked_record[0]["route"] == "/v1/token" and revoked_record[0]["status"] == 401
    )
    assert "token_id" not in revoked_record[0]
    registered_id = d.secrets["registered token"].split("_")[1]
    assert any(r.get("token_id") == registered_id for r in requests)
    assert any(r.get("code") == "rate-limited" and r["status"] == 429 for r in requests)
    failures = [r for r in requests if r.get("code") == "relay-failure"]
    assert len(failures) == 1
    assert failures[0]["route"] == "/v1/registrations"
    assert failures[0]["error_type"] == "RuntimeError"
    trouble = [r for r in records if str(r.get("event")).startswith("provider trouble")]
    assert len(trouble) == 1
    redactions = 3 if "database password" in d.secrets else 2
    assert str(trouble[0]["event"]).count("[redacted]") == redactions
    assert any(r.get("code") == "registration-started" for r in requests)
    assert any(r.get("code") == "registration-issued" for r in requests)


def test_the_scan_finds_a_planted_value_in_any_stream_it_covers() -> None:
    secrets = {"pepper": PEPPER, "email": EMAIL}
    for stream in ("stdout", "stderr"):
        for name, value in secrets.items():
            captured = Captured(
                "probe", f"before {value} after" if stream == "stdout" else "", ""
            )
            if stream == "stderr":
                captured = Captured("probe", "", f"x{value}x")
            assert leaks([captured], secrets, set()) == [f"probe {stream}: {name}"]
    exempt = Captured("probe", EMAIL, "")
    assert leaks([exempt], secrets, {"probe stdout"}) == []
    assert leaks([Captured("probe", "", EMAIL)], secrets, {"probe stdout"}) != []


def test_a_sqlite_database_refuses_a_password_and_does_not_echo_it(
    tmp_path: Path,
) -> None:
    """A password cannot be configured for SQLite (the contract refuses it), so
    the SQLite leg plants it where the contract looks and checks the refusal."""
    home = tmp_path / "home"
    home.mkdir()
    d = Deployment(
        child_env(
            f"sqlite:///{tmp_path / 'relay.sqlite3'}",
            free_port(),
            PLANTED_PASSWORD,
            home,
        ),
        0,
        {"database password": PLANTED_PASSWORD, "pepper": PEPPER},
    )
    refused = d.command("migrate")
    assert refused.returncode == 2
    assert refused.stderr.strip() != ""
    assert leaks(d.captures, d.secrets, set()) == []


def test_a_password_in_the_url_is_redacted_from_the_server_output(
    database_target: SqliteTarget | PostgresTarget,
    request: pytest.FixtureRequest,
    tmp_path: Path,
) -> None:
    """The URL-userinfo form of the database password, planted in the URL the
    server and its extension see (no password variable), through the failure
    path that logs the URL."""
    if not isinstance(database_target, PostgresTarget):
        pytest.skip("a SQLite URL takes no password")
    test_url: str = request.getfixturevalue("postgres_test_url")
    url, none = postgres_url(database_target, test_url, embed_password=True)
    assert none is None
    password = unquote(urlsplit(url).password or "")
    assert password and quote(password, safe="") in url
    home = tmp_path / "home"
    home.mkdir()
    secrets = {"database password": password, "pepper": PEPPER}
    d = Deployment(child_env(url, free_port(), None, home), 0, secrets)
    d.port = int(d.env[ENV_PORT])
    assert ENV_DATABASE_PASSWORD not in d.env
    migrated = d.command("migrate")
    assert migrated.returncode == 0, migrated.stderr
    for _ in serving(d, tmp_path):
        status, answer = d.request(
            "POST", "/v1/registrations", body=encode_request({"email": FAILING_EMAIL})
        )
        assert (status, code_of(answer)) == (500, "relay-failure")
        d.secrets["logged token"] = Path(d.env["E2E_LOGGED_TOKEN_FILE"]).read_text(
            encoding="utf-8"
        )
        d.stop()
    assert d.exit_code == 0
    assert leaks(d.captures, d.secrets, set()) == []
    trouble = [
        r
        for r in server_records(d.captures)
        if str(r.get("event")).startswith("provider trouble")
    ]
    assert len(trouble) == 1
    assert ":[redacted]@" in str(trouble[0]["event"])


@pytest.mark.parametrize(
    ("test_url", "url", "password"),
    [
        ("postgresql:///db", "postgresql:///db?options=O", PLANTED_PASSWORD),
        (
            "postgresql://u:p@127.0.0.1:5432/postgres",
            "postgresql://u@127.0.0.1:5432/postgres?options=O",
            "p",
        ),
        (
            "postgresql:///db?host=/tmp",
            "postgresql:///db?host=/tmp&options=O",
            PLANTED_PASSWORD,
        ),
        (
            "postgresql://us%40er:p%40ss%3Aw@[::1]:5432/db",
            "postgresql://us%40er@[::1]:5432/db?options=O",
            "p@ss:w",
        ),
    ],
    ids=["hostless", "ci-shape", "query-kept", "encoded-and-ipv6"],
)
def test_postgres_url_keeps_the_shape_and_moves_the_password(
    test_url: str, url: str, password: str
) -> None:
    target = PostgresTarget(conninfo="options=O", password=None)
    assert postgres_url(target, test_url) == (url, password)
