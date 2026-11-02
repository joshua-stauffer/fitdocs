"""`run_server`: the claim, the signals, the uvicorn configuration, the shutdown."""

from __future__ import annotations

import json
import logging
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import pytest
import uvicorn
from tests.conftest import TEST_PEPPER

from fitdocs_relay import logs, serve
from fitdocs_relay.config import PostgresTarget, RelayConfig, SqliteTarget
from fitdocs_relay.contract import (
    ENV_DATABASE_PASSWORD,
    ENV_DATABASE_URL,
    ENV_EXTENSIONS,
    ENV_FORWARDED_ALLOW_IPS,
    ENV_HOST,
    ENV_LOG_LEVEL,
    ENV_PORT,
    ENV_SHUTDOWN_GRACE,
    ENV_TOKEN_PEPPER,
)
from fitdocs_relay.storage import open_storage
from fitdocs_relay.storage.interface import StorageUnreachable
from fitdocs_relay.storage.migrate import migrate

CHILD_DIR = Path(__file__).parent / "serve_child"
ENTRY = CHILD_DIR / "entry.py"
WAIT_S = 30.0
SLOW_S = 3.0


# --- helpers ----------------------------------------------------------------


def free_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def config_for(database: Any, **overrides: Any) -> RelayConfig:
    values: dict[str, Any] = {
        "database": database,
        "pepper": TEST_PEPPER.encode(),
        "host": "127.0.0.1",
        "port": 8080,
        "forwarded_allow_ips": (),
        "token_limit_per_minute": 60,
        "client_limit_per_minute": 20,
        "shutdown_grace_s": 20,
        "log_level": "info",
        "extensions": (),
    }
    values.update(overrides)
    return RelayConfig(**values)


@pytest.fixture
def restore_logging() -> Iterator[None]:
    root = logging.getLogger()
    handlers, level = list(root.handlers), root.level
    yield
    root.handlers[:] = handlers
    root.setLevel(level)


# --- in process: the order, the uvicorn configuration, the cleanup ----------


class FakeClaim:
    def __init__(self, events: list[str]) -> None:
        self.events = events

    def release(self) -> None:
        self.events.append("release")


class FakeStorage:
    def __init__(self, events: list[str], *, held: bool = False) -> None:
        self.events = events
        self.held = held

    def claim_serving(self) -> FakeClaim | None:
        self.events.append("claim")
        return None if self.held else FakeClaim(self.events)

    def close(self) -> None:
        self.events.append("close")


class FakeServer:
    """Stands in for uvicorn.Server: records the Config, runs `behaviour`."""

    configs: list[Any] = []
    instances: list[FakeServer] = []
    behaviour: Callable[[], None] = staticmethod(lambda: None)

    def __init__(self, config: Any) -> None:
        FakeServer.configs.append(config)
        FakeServer.instances.append(self)
        self.should_exit = False

    def run(self) -> None:
        type(self).behaviour()


@pytest.fixture
def fake_uvicorn(monkeypatch: pytest.MonkeyPatch) -> type[FakeServer]:
    FakeServer.configs = []
    FakeServer.instances = []
    FakeServer.behaviour = staticmethod(lambda: None)
    monkeypatch.setattr(uvicorn, "Server", FakeServer)
    return FakeServer


def install_storage(
    monkeypatch: pytest.MonkeyPatch, events: list[str], *, held: bool = False
) -> None:
    def opener(target: object) -> FakeStorage:
        events.append("open")
        return FakeStorage(events, held=held)

    monkeypatch.setattr(serve, "open_storage", opener)
    monkeypatch.setattr(
        serve, "create_app", lambda config, *, extensions, storage: "the-app"
    )


def record_logging_order(monkeypatch: pytest.MonkeyPatch, events: list[str]) -> None:
    real = logs.configure_logging

    def spy(**kwargs: Any) -> logging.Handler:
        events.append("logging")
        return real(**kwargs)

    monkeypatch.setattr("fitdocs_relay.serve.configure_logging", spy)


def test_logging_is_configured_before_storage_opens_and_the_claim_is_released_last(
    monkeypatch: pytest.MonkeyPatch,
    fake_uvicorn: type[FakeServer],
    restore_logging: None,
) -> None:
    events: list[str] = []
    record_logging_order(monkeypatch, events)
    install_storage(monkeypatch, events)
    fake_uvicorn.behaviour = staticmethod(lambda: events.append("run"))

    assert serve.run_server(config_for(SqliteTarget(Path("x.db")))) == 0

    assert events == ["logging", "open", "claim", "run", "release", "close"]


def test_a_held_claim_returns_one_and_logs_the_fixed_refusal_without_serving(
    monkeypatch: pytest.MonkeyPatch,
    fake_uvicorn: type[FakeServer],
    restore_logging: None,
    capsys: pytest.CaptureFixture[str],
) -> None:
    events: list[str] = []
    install_storage(monkeypatch, events, held=True)

    assert serve.run_server(config_for(SqliteTarget(Path("x.db")))) == 1

    assert fake_uvicorn.configs == []
    assert events == ["open", "claim", "close"]
    lines = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert [(r["event"], r["level"]) for r in lines] == [("serve-refused", "ERROR")]


def test_the_claim_is_released_and_storage_closed_when_the_server_raises(
    monkeypatch: pytest.MonkeyPatch,
    fake_uvicorn: type[FakeServer],
    restore_logging: None,
) -> None:
    events: list[str] = []
    install_storage(monkeypatch, events)

    def explode() -> None:
        raise RuntimeError("the server failed")

    fake_uvicorn.behaviour = staticmethod(explode)
    with pytest.raises(RuntimeError, match="the server failed"):
        serve.run_server(config_for(SqliteTarget(Path("x.db"))))
    assert events == ["open", "claim", "release", "close"]


def test_the_uvicorn_configuration_follows_the_contract(
    monkeypatch: pytest.MonkeyPatch,
    fake_uvicorn: type[FakeServer],
    restore_logging: None,
) -> None:
    install_storage(monkeypatch, [])
    config = config_for(
        SqliteTarget(Path("x.db")),
        host="127.0.0.2",
        port=9123,
        shutdown_grace_s=7,
        forwarded_allow_ips=("10.0.0.0/8", "192.0.2.1"),
    )
    serve.run_server(config)
    (built,) = fake_uvicorn.configs
    assert built.app == "the-app"
    assert (built.host, built.port) == ("127.0.0.2", 9123)
    assert built.timeout_graceful_shutdown == 7
    assert built.lifespan == "on"
    assert built.access_log is False
    assert built.log_config is None
    assert built.proxy_headers is True
    assert built.forwarded_allow_ips == ["10.0.0.0/8", "192.0.2.1"]


def test_no_proxy_trust_is_an_empty_list_not_uvicorn_s_loopback_default(
    monkeypatch: pytest.MonkeyPatch,
    fake_uvicorn: type[FakeServer],
    restore_logging: None,
) -> None:
    # uvicorn turns None into $FORWARDED_ALLOW_IPS or "127.0.0.1,::1".
    monkeypatch.setenv("FORWARDED_ALLOW_IPS", "203.0.113.9")
    install_storage(monkeypatch, [])
    serve.run_server(config_for(SqliteTarget(Path("x.db"))))
    (built,) = fake_uvicorn.configs
    assert built.forwarded_allow_ips == []
    assert isinstance(built.forwarded_allow_ips, list)


def test_the_signal_handlers_are_ours_while_serving_and_restored_afterwards(
    monkeypatch: pytest.MonkeyPatch,
    fake_uvicorn: type[FakeServer],
    restore_logging: None,
) -> None:
    install_storage(monkeypatch, [])
    seen: dict[str, object] = {}

    def look() -> None:
        seen["term"] = signal.getsignal(signal.SIGTERM)
        seen["int"] = signal.getsignal(signal.SIGINT)

    fake_uvicorn.behaviour = staticmethod(look)
    before = (signal.getsignal(signal.SIGTERM), signal.getsignal(signal.SIGINT))
    serve.run_server(config_for(SqliteTarget(Path("x.db"))))
    assert isinstance(seen["term"], serve._StopRequest)
    assert isinstance(seen["int"], serve._StopRequest)
    assert before[0] is not seen["term"]
    assert before[1] is not seen["int"]
    assert (signal.getsignal(signal.SIGTERM), signal.getsignal(signal.SIGINT)) == before


def test_extensions_in_the_configuration_are_loaded_and_passed_to_the_app(
    monkeypatch: pytest.MonkeyPatch,
    fake_uvicorn: type[FakeServer],
    restore_logging: None,
) -> None:
    given: dict[str, object] = {}
    monkeypatch.setattr(serve, "open_storage", lambda target: FakeStorage([]))

    def app(config: object, *, extensions: object, storage: object) -> str:
        given["extensions"] = extensions
        return "the-app"

    monkeypatch.setattr(serve, "create_app", app)
    monkeypatch.setattr(
        serve,
        "load_extensions",
        lambda refs: ("loaded", *refs),
    )
    serve.run_server(config_for(SqliteTarget(Path("x.db")), extensions=("a:b",)))
    assert given["extensions"] == ("loaded", "a:b")


# --- in process: the database password never reaches the output -------------


PASSWORD = "p@ss/w:rd#1"
ENCODED = "p%40ss%2Fw%3Ard%231"


@pytest.mark.parametrize(
    ("target", "forms"),
    [
        (
            PostgresTarget(conninfo="postgresql://u@h/db", password=PASSWORD),
            [PASSWORD, ENCODED],
        ),
        (
            PostgresTarget(conninfo=f"postgresql://u:{ENCODED}@h/db", password=None),
            [PASSWORD, ENCODED],
        ),
        (
            PostgresTarget(
                conninfo=f"postgresql://u@h/db?sslmode=require&Password={ENCODED}",
                password=None,
            ),
            [PASSWORD, ENCODED],
        ),
    ],
    ids=["password variable", "password in the URL", "password in the query"],
)
def test_the_password_in_either_form_is_redacted_from_every_log_line(
    target: PostgresTarget,
    forms: list[str],
    monkeypatch: pytest.MonkeyPatch,
    fake_uvicorn: type[FakeServer],
    restore_logging: None,
    capsys: pytest.CaptureFixture[str],
) -> None:
    install_storage(monkeypatch, [])
    logger = logging.getLogger("uvicorn.error")

    def chatter() -> None:
        for form in forms:
            logger.error("connecting with %s", form)
            logger.error("conninfo %s", target.conninfo)

    fake_uvicorn.behaviour = staticmethod(chatter)
    serve.run_server(config_for(target))
    out = capsys.readouterr().out
    assert out.count("[redacted]") >= len(forms)  # the records were emitted
    for form in forms:
        assert form not in out


def test_a_pepper_inside_the_password_leaves_no_password_fragment(
    monkeypatch: pytest.MonkeyPatch,
    fake_uvicorn: type[FakeServer],
    restore_logging: None,
    capsys: pytest.CaptureFixture[str],
) -> None:
    password = "left-side-" + TEST_PEPPER + "-right-side"
    install_storage(monkeypatch, [])
    logger = logging.getLogger("uvicorn.error")
    fake_uvicorn.behaviour = staticmethod(lambda: logger.error("pw %s", password))
    target = PostgresTarget(conninfo="postgresql://u@h/db", password=password)
    serve.run_server(config_for(target))
    out = capsys.readouterr().out
    assert "pw [redacted]" in out
    assert "left-side" not in out
    assert "right-side" not in out
    assert TEST_PEPPER not in out


def test_the_log_level_comes_from_the_configuration(
    monkeypatch: pytest.MonkeyPatch,
    fake_uvicorn: type[FakeServer],
    restore_logging: None,
) -> None:
    install_storage(monkeypatch, [])
    seen: list[int] = []
    fake_uvicorn.behaviour = staticmethod(
        lambda: seen.append(logging.getLogger().level)
    )
    serve.run_server(config_for(SqliteTarget(Path("x.db")), log_level="warning"))
    serve.run_server(config_for(SqliteTarget(Path("x.db")), log_level="debug"))
    assert seen == [logging.WARNING, logging.DEBUG]


def test_an_unreachable_store_at_claim_time_is_one_failure_record_and_exit_one(
    monkeypatch: pytest.MonkeyPatch,
    fake_uvicorn: type[FakeServer],
    restore_logging: None,
    capsys: pytest.CaptureFixture[str],
) -> None:
    events: list[str] = []
    install_storage(monkeypatch, events)

    def unreachable(self: FakeStorage) -> None:
        self.events.append("claim")
        raise StorageUnreachable("down")

    monkeypatch.setattr(FakeStorage, "claim_serving", unreachable)
    assert serve.run_server(config_for(SqliteTarget(Path("x.db")))) == 1
    assert events == ["open", "claim", "close"]
    assert fake_uvicorn.configs == []
    records = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert [(r["event"], r["level"], r["error_type"]) for r in records] == [
        ("serve-failed", "ERROR", "StorageUnreachable")
    ]


def test_a_signal_before_uvicorn_runs_skips_the_run_and_still_releases(
    monkeypatch: pytest.MonkeyPatch,
    fake_uvicorn: type[FakeServer],
    restore_logging: None,
) -> None:
    events: list[str] = []
    install_storage(monkeypatch, events)

    def app_then_signal(config: object, *, extensions: object, storage: object) -> str:
        if not isinstance(signal.getsignal(signal.SIGTERM), serve._StopRequest):
            pytest.fail("the stop handler is not installed; raising would kill pytest")
        signal.raise_signal(signal.SIGTERM)  # handled in this thread, right now
        return "the-app"

    fake_uvicorn.behaviour = staticmethod(lambda: events.append("run"))
    monkeypatch.setattr(serve, "create_app", app_then_signal)
    assert serve.run_server(config_for(SqliteTarget(Path("x.db")))) == 0
    assert events == ["open", "claim", "release", "close"]


def test_a_signal_after_the_server_exists_sets_its_exit_flag_and_still_releases(
    monkeypatch: pytest.MonkeyPatch,
    fake_uvicorn: type[FakeServer],
    restore_logging: None,
) -> None:
    events: list[str] = []
    install_storage(monkeypatch, events)

    def late_signal() -> None:
        (server,) = fake_uvicorn.instances
        assert server.should_exit is False
        if not isinstance(signal.getsignal(signal.SIGTERM), serve._StopRequest):
            pytest.fail("the stop handler is not installed")
        signal.raise_signal(signal.SIGTERM)
        events.append(f"flag={server.should_exit}")

    fake_uvicorn.behaviour = staticmethod(late_signal)
    assert serve.run_server(config_for(SqliteTarget(Path("x.db")))) == 0
    assert events == ["open", "claim", "flag=True", "release", "close"]


# --- subprocesses -----------------------------------------------------------


def child_env(database: Path, port: int, started: Path, **extra: str) -> dict[str, str]:
    """The child's whole environment: no inherited FITDOCS_RELAY_* name."""
    env = {
        name: value
        for name, value in os.environ.items()
        if not name.startswith(("FITDOCS_RELAY_", "PYTHON", "FORWARDED_"))
    }
    env.update(
        {
            ENV_DATABASE_URL: f"sqlite:///{database}",
            ENV_TOKEN_PEPPER: TEST_PEPPER,
            ENV_HOST: "127.0.0.1",
            ENV_PORT: str(port),
            ENV_SHUTDOWN_GRACE: "15",
            ENV_LOG_LEVEL: "info",
            ENV_EXTENSIONS: "slow_extension:EXTENSION",
            "SERVE_TEST_STARTED_FILE": str(started),
            "SERVE_TEST_DELAY_SECONDS": str(SLOW_S),
            "PYTHONDONTWRITEBYTECODE": "1",
        }
    )
    env.update(extra)
    return env


class Child:
    def __init__(self, env: dict[str, str], out: Path) -> None:
        self.out = out
        self._sink = out.open("wb")
        # -B: no bytecode under src/; -s -E: ignore user site and PYTHON* vars.
        # The script's directory is on sys.path, which is how the test
        # extension is found without a PYTHONPATH.
        self.process = subprocess.Popen(
            [sys.executable, "-B", "-s", "-E", str(ENTRY)],
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=self._sink,
            stderr=subprocess.STDOUT,
            cwd=str(CHILD_DIR),
        )

    def text(self) -> str:
        return self.out.read_text(encoding="utf-8")

    def wait(self, timeout: float = WAIT_S) -> int:
        try:
            return self.process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            pytest.fail(f"the child did not exit within {timeout}s:\n{self.text()}")

    def stop(self) -> None:
        if self.process.poll() is None:
            self.process.kill()
        self.process.wait(timeout=WAIT_S)
        self._sink.close()


@pytest.fixture
def children() -> Iterator[list[Child]]:
    started: list[Child] = []
    yield started
    for child in started:
        child.stop()


def migrated(path: Path) -> Path:
    store = open_storage(SqliteTarget(path))
    try:
        migrate(store, now=1)
    finally:
        store.close()
    return path


def get(port: int, path: str, timeout: float = 20.0) -> tuple[int, str]:
    url = f"http://127.0.0.1:{port}{path}"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:  # noqa: S310
            return response.status, response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode("utf-8")


def await_livez(child: Child, port: int) -> None:
    deadline = time.monotonic() + WAIT_S
    while time.monotonic() < deadline:
        if child.process.poll() is not None:
            pytest.fail(
                f"the child exited early ({child.process.returncode}):\n{child.text()}"
            )
        try:
            if get(port, "/livez", timeout=2.0)[0] == 200:
                return
        except OSError:
            time.sleep(0.1)
    pytest.fail(f"the child never answered /livez:\n{child.text()}")


def await_file(path: Path, child: Child) -> None:
    deadline = time.monotonic() + WAIT_S
    while time.monotonic() < deadline:
        if path.exists():
            return
        if child.process.poll() is not None:
            pytest.fail(f"the child exited early:\n{child.text()}")
        time.sleep(0.05)
    pytest.fail("the slow request never reached the extension")


@pytest.mark.parametrize("number", [signal.SIGTERM, signal.SIGINT], ids=["term", "int"])
def test_a_signal_during_a_slow_request_completes_it_and_exits_zero(
    number: signal.Signals, tmp_path: Path, children: list[Child]
) -> None:
    database = migrated(tmp_path / "relay.db")
    started = tmp_path / "started"
    port = free_port()
    child = Child(child_env(database, port, started), tmp_path / "out.log")
    children.append(child)
    await_livez(child, port)
    assert not started.exists()  # the request has not started yet

    with ThreadPoolExecutor(max_workers=1) as pool:
        pending = pool.submit(get, port, "/x/slow/wait", 25.0)
        await_file(started, child)
        assert child.process.poll() is None
        sent = time.monotonic()
        child.process.send_signal(number)
        status, body = pending.result(timeout=WAIT_S)
        finished = time.monotonic()
    assert (status, body) == (200, "finished the slow request")
    assert finished - sent > 0.3  # the signal really arrived mid-request
    assert child.wait() == 0
    assert child.process.returncode == 0


def test_a_signal_while_the_app_is_still_being_built_exits_zero_without_serving(
    tmp_path: Path, children: list[Child]
) -> None:
    database = migrated(tmp_path / "relay.db")
    port = free_port()
    building, release = tmp_path / "building", tmp_path / "release"
    child = Child(
        child_env(
            database,
            port,
            tmp_path / "s",
            **{
                ENV_EXTENSIONS: "slow_extension:BLOCKING",
                "SERVE_TEST_BUILDING_FILE": str(building),
                "SERVE_TEST_RELEASE_FILE": str(release),
            },
        ),
        tmp_path / "b.log",
    )
    children.append(child)
    await_file(building, child)
    assert child.process.poll() is None
    with pytest.raises(OSError):
        get(port, "/livez", timeout=2.0)  # nothing is listening yet
    child.process.send_signal(signal.SIGTERM)
    time.sleep(0.3)
    assert child.process.poll() is None  # the signal did not kill the build
    release.write_text("go", encoding="utf-8")
    assert child.wait(timeout=15) == 0
    assert "request" not in child.text()
    with pytest.raises(OSError):
        get(port, "/livez", timeout=2.0)


def test_a_second_serve_on_the_same_file_exits_one_while_the_first_runs(
    tmp_path: Path, children: list[Child]
) -> None:
    database = migrated(tmp_path / "relay.db")
    first_port = free_port()
    first = Child(child_env(database, first_port, tmp_path / "s1"), tmp_path / "1.log")
    children.append(first)
    await_livez(first, first_port)

    second = Child(
        child_env(database, free_port(), tmp_path / "s2"), tmp_path / "2.log"
    )
    children.append(second)
    assert second.wait() == 1
    refused = [json.loads(line) for line in second.text().splitlines()]
    assert [r["event"] for r in refused] == ["serve-refused"]
    assert first.process.poll() is None  # still running
    assert get(first_port, "/livez")[0] == 200

    first.process.send_signal(signal.SIGTERM)
    assert first.wait() == 0
    # After the first exits, a third instance serves on the same file.
    third_port = free_port()
    third = Child(child_env(database, third_port, tmp_path / "s3"), tmp_path / "3.log")
    children.append(third)
    await_livez(third, third_port)


def test_no_uvicorn_access_line_and_every_output_line_is_a_json_record(
    tmp_path: Path, children: list[Child]
) -> None:
    database = migrated(tmp_path / "relay.db")
    port = free_port()
    child = Child(child_env(database, port, tmp_path / "s"), tmp_path / "o.log")
    children.append(child)
    await_livez(child, port)
    for _ in range(3):
        assert get(port, "/livez?probe=1")[0] == 200
    child.process.send_signal(signal.SIGTERM)
    assert child.wait() == 0

    lines = child.text().splitlines()
    records = [json.loads(line) for line in lines]  # all JSON, none plain text
    requests = [r for r in records if r.get("event") == "request"]
    assert len(requests) >= 3  # the three probes were logged as request records
    assert all(r.get("route") == "/livez" for r in requests)
    text = child.text()
    assert "uvicorn.access" not in text
    assert "GET /livez?probe=1" not in text
    assert "HTTP/1.1" not in text


def test_an_unreachable_postgres_database_exits_one_with_one_failure_record(
    tmp_path: Path, children: list[Child]
) -> None:
    password = "hunter2-not-a-real-secret"
    env = child_env(
        tmp_path / "unused.db",
        free_port(),
        tmp_path / "s",
        **{
            ENV_DATABASE_URL: f"postgresql://relay@127.0.0.1:{free_port()}/relay",
            ENV_DATABASE_PASSWORD: password,
            ENV_EXTENSIONS: "",
            ENV_FORWARDED_ALLOW_IPS: "",
        },
    )
    child = Child(env, tmp_path / "pg.log")
    children.append(child)
    code = child.wait()
    output = child.text()
    assert code == 1
    records = [json.loads(line) for line in output.splitlines()]
    assert [(r["event"], r["error_type"]) for r in records] == [
        ("serve-failed", "StorageUnreachable")
    ]
