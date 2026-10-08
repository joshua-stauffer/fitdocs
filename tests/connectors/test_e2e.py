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
   ``check``, ``history``, ``plan``, ``derive-benchmarks``, ``index`` and
   ``query`` -- completing exactly as it would with no ``[connectors]`` table
   at all: same exit code and output, the same number of socket attempts as
   the bare run (an in-test recorder that also raises), and no call on a
   scripted connector.
"""

from __future__ import annotations

import contextlib
import hashlib
import os
import socket
from collections.abc import Iterator
from pathlib import Path

import pytest
from typer.testing import CliRunner

import fitdocs.cli as cli_module
from fitdocs import Modality
from fitdocs.cli import app
from fitdocs.connectors import registry as connector_registry
from fitdocs.connectors.credentials import env_var_name
from fitdocs.connectors.protocol import Capability, Fetched, Listing, RemoteActivity
from fitdocs.index.location import resolve_index_location
from fitdocs.index.store import open_index, read_bookkeeping
from fitdocs.layout import archive_path
from fitdocs.load import registry as load_registry
from fitdocs.load.docedit import apply_frontmatter_load, replace_load_region
from fitdocs.load.types import (
    AthleteField,
    Computed,
    InteractionSession,
    LoadContext,
    LoadOutcome,
    LoadResult,
    ProfileView,
)
from fitdocs.metrics.types import DerivedMetrics
from fitdocs.model import Activity
from tests.connectors.conftest import ScriptedPersonalKeyConnector
from tests.fixtures import builder

runner = CliRunner()

_STUB_CALCULATOR_ID = "stub-analytics-index-parity"


class _FieldFreeIndexParityCalculator:
    calculator_id = _STUB_CALCULATOR_ID
    display_name = "Analytics Index Parity Stub"
    supported_modalities = frozenset({Modality.RUN})

    def required_athlete_fields(self) -> tuple[AthleteField, ...]:
        return ()

    def compute(
        self,
        activity: Activity,
        metrics: DerivedMetrics,
        profile: ProfileView,
        session: InteractionSession,
        context: LoadContext,
    ) -> LoadOutcome:
        if activity.modality is not Modality.RUN:
            raise AssertionError("the test calculator only accepts RUN activities")
        return Computed(
            result=LoadResult(
                calculator_id=self.calculator_id,
                display_name=self.display_name,
                value=42.0,
                basis="stub e2e basis",
                non_selected=(),
                flags=(),
                inputs_used=(),
                notes=(),
            )
        )


@contextlib.contextmanager
def _forced_index_parity_calculator() -> Iterator[None]:
    saved = dict(load_registry._REGISTRY)
    load_registry._REGISTRY.clear()
    load_registry.register(_FieldFreeIndexParityCalculator())
    try:
        yield
    finally:
        load_registry._REGISTRY.clear()
        load_registry._REGISTRY.update(saved)


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


def _data_root_bytes(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _data_root_snapshot(root: Path) -> dict[str, tuple[bytes, int]]:
    return {
        path.relative_to(root).as_posix(): (path.read_bytes(), path.stat().st_mtime_ns)
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_data_root_snapshot_matches_literal_nested_files_and_mtimes(
    tmp_path: Path,
) -> None:
    root = tmp_path / "literal-snapshot"
    nested = root / "nested" / "deeper"
    nested.mkdir(parents=True)
    alpha = root / "alpha.bin"
    beta = nested / "beta.bin"
    alpha_bytes = b"literal alpha payload"
    beta_bytes = b"\x00literal beta payload\xff"
    alpha_mtime = 1_700_000_000_000_000_001
    beta_mtime = 1_700_000_100_000_000_003
    alpha.write_bytes(alpha_bytes)
    beta.write_bytes(beta_bytes)
    os.utime(alpha, ns=(alpha_mtime, alpha_mtime))
    os.utime(beta, ns=(beta_mtime, beta_mtime))

    assert _data_root_snapshot(root) == {
        "alpha.bin": (b"literal alpha payload", 1_700_000_000_000_000_001),
        "nested/deeper/beta.bin": (
            b"\x00literal beta payload\xff",
            1_700_000_100_000_000_003,
        ),
    }


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


def _fresh_synced_root(
    tmp_path: Path,
    name: str,
    *,
    with_connectors: bool,
    tiles_disabled: bool = False,
) -> Path:
    """A freshly synced data root with one workout document, optionally
    carrying a `[connectors]` table naming the built-in folder connector
    and the scripted personal-key connector."""
    source = tmp_path / f"{name}-src"
    source.mkdir()
    (source / "run.fit").write_bytes(builder.run_fit_bytes())
    data_root = tmp_path / f"{name}-root"
    data_root.mkdir()
    settings = ""
    if with_connectors:
        settings += (
            '[connectors.folder-src]\nconnector = "folder"\n'
            'path = "unused-folder"\n\n'
            '[connectors.key-src]\nconnector = "personal-key"\n'
        )
    if tiles_disabled:
        settings += "\n[tiles]\nenabled = false\n"
    if settings:
        _write_settings(data_root, connectors=settings)
    result = runner.invoke(app, ["sync", str(source), "--out", str(data_root)])
    assert result.exit_code == 0, result.output
    return data_root


@pytest.mark.parametrize(
    "command,args",
    [
        ("sync", []),
        ("regen", []),
        ("load", []),
        ("check", []),
        ("history", []),
        ("plan", []),
        ("derive-benchmarks", []),
        ("index", []),
        ("query", ["SELECT count(*) AS n FROM pages"]),
    ],
)
def test_offline_commands_complete_unchanged_with_connectors_and_socket_guarded(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    command: str,
    args: list[str],
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
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "fallback-xdg-cache"))
    is_query = command == "query"
    bare_root = _fresh_synced_root(
        tmp_path,
        f"bare-{command}",
        with_connectors=False,
        tiles_disabled=is_query,
    )
    wired_root = _fresh_synced_root(
        tmp_path,
        f"wired-{command}",
        with_connectors=True,
        tiles_disabled=is_query,
    )

    bare_index = tmp_path / f"bare-{command}-index"
    wired_index = tmp_path / f"wired-{command}-index"
    assert bare_index != wired_index
    if is_query:
        for root, index_dir in ((bare_root, bare_index), (wired_root, wired_index)):
            monkeypatch.setenv("FITDOCS_INDEX_DIR", str(index_dir))
            built = runner.invoke(app, ["index", "--out", str(root)])
            assert built.exit_code == 0, built.output
            database = next(index_dir.rglob("index.duckdb"))
            assert database.stat().st_size > 0

    attempts: list[object] = []

    def _record_and_refuse(*args: object, **kwargs: object) -> object:
        attempts.append(args)
        raise RuntimeError("tests/connectors must not open a real network socket")

    monkeypatch.setattr(socket, "socket", _record_and_refuse)

    bare_root_before = _data_root_snapshot(bare_root)
    wired_root_before = _data_root_snapshot(wired_root)
    assert bare_root_before
    assert wired_root_before
    monkeypatch.setenv("FITDOCS_INDEX_DIR", str(bare_index))
    bare = runner.invoke(app, [command, *args, "--out", str(bare_root)])
    bare_attempts = len(attempts)
    monkeypatch.setenv("FITDOCS_INDEX_DIR", str(wired_index))
    wired = runner.invoke(app, [command, *args, "--out", str(wired_root)])
    bare_root_after = _data_root_snapshot(bare_root)
    wired_root_after = _data_root_snapshot(wired_root)

    assert wired.exception is None, wired.output
    assert wired.exit_code == bare.exit_code, (bare.output, wired.output)
    bare_output = bare.output
    wired_output = wired.output
    bare_location = resolve_index_location(
        bare_root, {"FITDOCS_INDEX_DIR": str(bare_index)}, tmp_path
    )
    wired_location = resolve_index_location(
        wired_root, {"FITDOCS_INDEX_DIR": str(wired_index)}, tmp_path
    )
    bare_output = bare_output.replace(str(bare_root), "<data-root>").replace(
        str(bare_location.database), "<resolved-index-database>"
    )
    wired_output = wired_output.replace(str(wired_root), "<data-root>").replace(
        str(wired_location.database), "<resolved-index-database>"
    )
    assert wired_output == bare_output
    if is_query:
        assert bare.stdout == "n\n1"
        assert bare_attempts == 0
        assert len(attempts) == 0
    if command == "index":
        assert bare_root_after == bare_root_before
        assert wired_root_after == wired_root_before
        bare_databases = list(bare_index.rglob("index.duckdb"))
        wired_databases = list(wired_index.rglob("index.duckdb"))
        assert len(bare_databases) == len(wired_databases) == 1
        assert bare_databases[0].stat().st_size > 0
        assert wired_databases[0].stat().st_size > 0
    # `regen` re-renders maps, so its tile fetch reaches for a socket in both
    # roots (and falls back): the wired run may make exactly as many attempts
    # as the bare one -- a swallowed connector request adds one.
    if command == "index":
        assert bare_attempts == 0
        assert len(attempts) == 0
    else:
        assert len(attempts) - bare_attempts == bare_attempts
    assert key_connector.verify_calls == []
    assert key_connector.list_calls == []
    assert key_connector.fetch_calls == []


def test_sync_and_load_parity_with_and_without_prebuilt_index(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "parity-source"
    source.mkdir()
    (source / "run.fit").write_bytes(builder.run_fit_bytes())
    bare_root = tmp_path / "parity-bare"
    indexed_root = tmp_path / "parity-indexed"
    bare_root.mkdir()
    indexed_root.mkdir()
    bare_index = tmp_path / "parity-bare-cache"
    indexed_index = tmp_path / "parity-indexed-cache"

    def invoke(root: Path, index_dir: Path, arguments: list[str]) -> tuple[int, str]:
        monkeypatch.setenv("FITDOCS_INDEX_DIR", str(index_dir))
        result = runner.invoke(app, [*arguments, "--out", str(root)])
        return result.exit_code, result.output

    for root, cache in ((bare_root, bare_index), (indexed_root, indexed_index)):
        initial_code, initial_output = invoke(root, cache, ["sync", str(source)])
        assert initial_code == 0, initial_output
    prebuilt_code, prebuilt_output = invoke(indexed_root, indexed_index, ["index"])
    assert prebuilt_code == 0, prebuilt_output
    database = next(indexed_index.rglob("index.duckdb"))
    assert database.stat().st_size > 0
    with open_index(database, read_only=True) as connection:
        before_sync_bookkeeping = read_bookkeeping(connection)
    assert before_sync_bookkeeping is not None
    assert len(before_sync_bookkeeping.pages) == 1
    assert _data_root_bytes(bare_root) == _data_root_bytes(indexed_root)

    # Make sync do useful work after the index was built. The corresponding
    # post-pass must refresh the existing index without putting index files in
    # either data root.
    (source / "run.fit").write_bytes(builder.run_native_dynamics_fit_bytes())
    for root, cache in ((bare_root, bare_index), (indexed_root, indexed_index)):
        synced_code, synced_output = invoke(root, cache, ["sync", str(source)])
        assert synced_code == 0, synced_output
    with open_index(database, read_only=True) as connection:
        after_sync_bookkeeping = read_bookkeeping(connection)
    assert after_sync_bookkeeping is not None
    assert len(after_sync_bookkeeping.pages) == 1
    assert set(after_sync_bookkeeping.pages) != set(before_sync_bookkeeping.pages)
    assert database.stat().st_size > 0

    def independent_root_bytes(root: Path) -> dict[str, bytes]:
        files = tuple(sorted(path for path in root.rglob("*") if path.is_file()))
        assert files
        return {path.relative_to(root).as_posix(): path.read_bytes() for path in files}

    before_sync_load = {
        root: _data_root_bytes(root) for root in (bare_root, indexed_root)
    }
    assert before_sync_load[bare_root] == independent_root_bytes(bare_root)
    assert before_sync_load[indexed_root] == independent_root_bytes(indexed_root)
    assert len(before_sync_load[bare_root]) > 2
    assert before_sync_load[bare_root] == before_sync_load[indexed_root]

    docs_by_root: dict[Path, tuple[Path, ...]] = {}
    for root in (bare_root, indexed_root):
        docs = tuple(
            sorted(
                path
                for path in (root / "workouts").glob("*.md")
                if path.name != "AGENTS.md"
            )
        )
        assert docs
        docs_by_root[root] = docs
        for number, document in enumerate(docs, start=1):
            text = document.read_text(encoding="utf-8")
            stale = apply_frontmatter_load(
                text,
                LoadResult(
                    calculator_id="stale-calculator",
                    display_name="Stale load",
                    value=float(10 + number),
                    basis=f"stale basis {number}",
                    non_selected=(),
                    flags=(),
                    inputs_used=(),
                    notes=(),
                ),
            )
            stale = replace_load_region(stale, f"stale load content {number}")
            document.write_text(stale, encoding="utf-8")
            assert "stale-calculator" in document.read_text(encoding="utf-8")

    before_load = {root: _data_root_bytes(root) for root in (bare_root, indexed_root)}
    assert before_load[bare_root]
    assert before_load[indexed_root]
    assert before_load[bare_root] == independent_root_bytes(bare_root)
    assert before_load[indexed_root] == independent_root_bytes(indexed_root)
    assert len(before_load[bare_root]) > 2
    assert before_load[bare_root] == before_load[indexed_root]
    for _root, docs in docs_by_root.items():
        for number, document in enumerate(docs, start=1):
            from fitdocs.load.docedit import read_frontmatter_load

            assert (
                read_frontmatter_load(document.read_text(encoding="utf-8"))[
                    "load_value"
                ]
                == 10 + number
            )

    original_calculators = dict(load_registry._REGISTRY)
    with _forced_index_parity_calculator():
        for root, cache in ((bare_root, bare_index), (indexed_root, indexed_index)):
            loaded_code, loaded_output = invoke(
                root,
                cache,
                [
                    "load",
                    "--no-prompt",
                    "--recompute",
                    "--calculator",
                    _STUB_CALCULATOR_ID,
                ],
            )
            assert loaded_code == 0, loaded_output
    assert set(load_registry._REGISTRY) == set(original_calculators)
    assert all(
        load_registry._REGISTRY[key] is calculator
        for key, calculator in original_calculators.items()
    )
    from fitdocs.load.docedit import read_frontmatter_load

    after_load = {root: _data_root_bytes(root) for root in (bare_root, indexed_root)}
    assert after_load[bare_root] != before_load[bare_root]
    assert after_load[indexed_root] != before_load[indexed_root]
    assert after_load[bare_root] == independent_root_bytes(bare_root)
    assert after_load[indexed_root] == independent_root_bytes(indexed_root)
    for docs in docs_by_root.values():
        for document in docs:
            loaded = read_frontmatter_load(document.read_text(encoding="utf-8"))
            assert loaded["load_value"] == 42
            assert loaded["load_methodology"] == _STUB_CALCULATOR_ID
            assert loaded["load_basis"] == "stub e2e basis"
    with open_index(database, read_only=True) as connection:
        indexed_loads = connection.execute(
            "SELECT calculator_id, load_value FROM loads"
        ).fetchall()
    assert indexed_loads
    assert all(
        (calculator_id, load_value) == (_STUB_CALCULATOR_ID, 42.0)
        for calculator_id, load_value in indexed_loads
    )
    assert after_load[bare_root] == after_load[indexed_root]
