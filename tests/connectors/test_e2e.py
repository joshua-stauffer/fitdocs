"""End-to-end tests for the connectors spec (task 9.2; design.md "Testing
Strategy" § CLI / E2E; Req 8.5, 8.9, 12.1, 14.1, 14.5).

Two scenarios, both driven through :class:`typer.testing.CliRunner` against
the real, installed ``fitdocs`` entry point, with the package-level
``tests/connectors/conftest.py`` autouse fixtures doing the isolation (socket
guard, registry snapshot/restore, credentials/environment isolation):

1. ``fitdocs pull --sync --no-prompt`` over a synthetic folder source AND a
   synthetic personal-key connector, both behind the patched transport seam:
   delivery, the chained drain into workout documents, the second run's
   archived-delivery removal and empty fetch, and two hand-dropped `.fit`
   files (one at the inbox root, one inside an instance's own delivery
   directory) that the first drain archives and that survive both runs:
   archived inbox files the ledger does not own are the drain's business,
   never the pull's.
2. With ``[connectors]`` configured, every command Req 14.1 names that is
   not ``connect``/``pull`` itself -- ``sync``, ``regen``, ``load``,
   ``check``, ``history``, ``plan``, ``derive-benchmarks`` -- completing
   exactly as it would with no ``[connectors]`` table at all: same exit
   code and output, the same number of socket attempts as the bare run (an
   in-test recorder that also raises), and no call on a scripted connector.
"""

from __future__ import annotations

import hashlib
import socket
from pathlib import Path

import pytest
from typer.testing import CliRunner

import fitdocs.cli as cli_module
from fitdocs.cli import app
from fitdocs.connectors import registry as connector_registry
from fitdocs.connectors.credentials import env_var_name
from fitdocs.connectors.protocol import Capability, Fetched, Listing, RemoteActivity
from fitdocs.layout import archive_path
from tests.connectors.conftest import ScriptedPersonalKeyConnector
from tests.fixtures import builder

runner = CliRunner()


def _write_settings(data_root: Path, *, connectors: str) -> None:
    (data_root / "fitdocs.toml").write_text(connectors, encoding="utf-8")


def _forbidden_transport(request: object, timeout: float) -> object:
    raise AssertionError(
        "neither the folder connector nor the scripted personal-key connector "
        "needs a real HTTP request in this test"
    )


def _patch_pull_transport(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        cli_module, "_connector_transport", lambda: _forbidden_transport
    )


def _collapsed(output: str) -> str:
    cleaned = "".join(ch for ch in output if ch not in "│╭╮╰╯─┃┏┓┗┛")
    return " ".join(cleaned.split())


# =============================================================================
# 1. End-to-end pull + drain over a folder source AND a personal-key
#    connector (Req 8.5, 8.9, 12.1).
# =============================================================================


def test_pull_sync_folder_and_personal_key_second_run_removes_only_its_own(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "phone-exports"
    source.mkdir()
    (source / "run.fit").write_bytes(builder.run_fit_bytes())

    key_connector = ScriptedPersonalKeyConnector(
        capabilities=frozenset({Capability.PULL_ACTIVITIES})
    )
    key_connector.listing_script.append(
        Listing(
            activities=(RemoteActivity(remote_id="ride-1", original_available=True),)
        )
    )
    key_connector.fetch_script.append(Fetched(data=builder.ride_fit_bytes()))
    connector_registry.register(key_connector)

    _write_settings(
        tmp_path,
        connectors=(
            '[connectors.folder-src]\nconnector = "folder"\n'
            f'path = "{source.as_posix()}"\nsettle_seconds = 0\n\n'
            '[connectors.key-src]\nconnector = "personal-key"\n'
        ),
    )
    monkeypatch.setenv(env_var_name("key-src", "api_key"), "s3cr3t-api-key")
    _patch_pull_transport(monkeypatch)

    # Two .fit files a person drops into the inbox by hand, under names no
    # delivery uses -- one at the inbox root, one inside an instance's own
    # delivery subdirectory -- with bytes no connector delivers. The first
    # run's drain archives both (leave disposition), so at the second run's
    # sweep each is an archived inbox file the ledger does not own.
    inbox = tmp_path / "inbox"
    (inbox / "key-src").mkdir(parents=True)
    hand_dropped = {
        inbox / "hand-dropped.fit": builder.strength_fit_bytes(),
        inbox / "key-src" / "my-own-copy.fit": builder.hike_fit_bytes(),
    }
    for path, data in hand_dropped.items():
        path.write_bytes(data)

    first = runner.invoke(
        app, ["pull", "--sync", "--no-prompt", "--out", str(tmp_path)]
    )
    assert first.exit_code == 0, first.output
    for data in hand_dropped.values():
        assert archive_path(tmp_path, hashlib.sha256(data).hexdigest()).is_file()
    docs_after_first = sorted(
        p for p in (tmp_path / "workouts").glob("*.md") if p.name != "AGENTS.md"
    )
    # Without the personal-key delivery there would be three documents;
    # asserting exactly four defeats a run that silently dropped it while
    # still exiting 0.
    assert len(docs_after_first) == 4, (
        f"expected one document per connector plus the two hand-dropped files, "
        f"got {docs_after_first}"
    )
    assert (tmp_path / ".fitdocs" / "connectors" / "folder-src.toml").is_file()
    assert (tmp_path / ".fitdocs" / "connectors" / "key-src.toml").is_file()

    # The next run must fetch nothing new. The key connector's second
    # listing re-lists the SAME activity, same revision, still available --
    # the engine must recognize it as already final in the ledger and
    # never call `fetch_activity` again; no second `fetch_script` entry is
    # queued, so a wrongly repeated fetch raises `UnscriptedCall` and fails
    # this test outright rather than silently redelivering.
    key_connector.listing_script.append(
        Listing(
            activities=(RemoteActivity(remote_id="ride-1", original_available=True),)
        )
    )

    second = runner.invoke(
        app, ["pull", "--sync", "--no-prompt", "--out", str(tmp_path)]
    )
    assert second.exit_code == 0, second.output
    collapsed = _collapsed(second.output)
    # Both instances' earlier deliveries are now archived; each instance's
    # own sweep removes exactly its one earlier delivery (two separate
    # per-instance "Removed 1" rows, not a coincidental aggregate "Removed 2"
    # that a single mis-scoped sweep could also produce).
    assert collapsed.count("Removed 1") == 2, collapsed
    assert "Removed 2" not in collapsed
    # Nothing new was delivered or archived by the second run.
    docs_after_second = sorted(
        p for p in (tmp_path / "workouts").glob("*.md") if p.name != "AGENTS.md"
    )
    assert docs_after_second == docs_after_first
    assert key_connector.fetch_calls == [
        RemoteActivity(remote_id="ride-1", original_available=True)
    ], "the second run must not re-fetch the already-delivered activity"

    # Archived but not the ledger's: neither sweep may remove them (Req 8.6).
    for path, data in hand_dropped.items():
        assert path.is_file(), path
        assert path.read_bytes() == data, path


# =============================================================================
# 2. Offline commands with [connectors] configured and a socket patched to
#    raise (Req 14.1).
# =============================================================================


def _fresh_synced_root(tmp_path: Path, name: str, *, with_connectors: bool) -> Path:
    """A freshly synced data root with one workout document, optionally
    carrying a `[connectors]` table naming the built-in folder connector
    and the scripted personal-key connector."""
    source = tmp_path / f"{name}-src"
    source.mkdir()
    (source / "run.fit").write_bytes(builder.run_fit_bytes())
    data_root = tmp_path / f"{name}-root"
    data_root.mkdir()
    if with_connectors:
        _write_settings(
            data_root,
            connectors=(
                '[connectors.folder-src]\nconnector = "folder"\n'
                'path = "unused-folder"\n\n'
                '[connectors.key-src]\nconnector = "personal-key"\n'
            ),
        )
    result = runner.invoke(app, ["sync", str(source), "--out", str(data_root)])
    assert result.exit_code == 0, result.output
    return data_root


@pytest.mark.parametrize(
    "command",
    ["sync", "regen", "load", "check", "history", "plan", "derive-benchmarks"],
)
def test_offline_commands_complete_unchanged_with_connectors_and_socket_guarded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, command: str
) -> None:
    """Every command Req 14.1 names, other than `connect`/`pull`, completes
    exactly as it would with no `[connectors]` table -- compared directly
    (both roots are built from the identical single-file source). A
    connector call is visible even when a command swallows the error: the
    socket-attempt counts of the two runs must be equal and the scripted
    connector's call lists must stay empty."""
    key_connector = ScriptedPersonalKeyConnector(
        capabilities=frozenset({Capability.PULL_ACTIVITIES})
    )
    connector_registry.register(key_connector)
    monkeypatch.setenv(env_var_name("key-src", "api_key"), "s3cr3t-api-key")
    bare_root = _fresh_synced_root(tmp_path, f"bare-{command}", with_connectors=False)
    wired_root = _fresh_synced_root(tmp_path, f"wired-{command}", with_connectors=True)

    attempts: list[object] = []

    def _record_and_refuse(*args: object, **kwargs: object) -> object:
        attempts.append(args)
        raise RuntimeError("tests/connectors must not open a real network socket")

    monkeypatch.setattr(socket, "socket", _record_and_refuse)

    bare = runner.invoke(app, [command, "--out", str(bare_root)])
    bare_attempts = len(attempts)
    wired = runner.invoke(app, [command, "--out", str(wired_root)])

    assert wired.exception is None, wired.output
    assert wired.exit_code == bare.exit_code, (bare.output, wired.output)
    assert wired.output.replace(str(wired_root), "<root>") == bare.output.replace(
        str(bare_root), "<root>"
    )
    # `regen` re-renders maps, so its tile fetch reaches for a socket in both
    # roots (and falls back): the wired run may make exactly as many attempts
    # as the bare one -- a swallowed connector request adds one.
    assert len(attempts) - bare_attempts == bare_attempts
    assert key_connector.verify_calls == []
    assert key_connector.list_calls == []
