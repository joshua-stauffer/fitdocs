"""``fitdocs sync``: optional SOURCE and the inbox-drain wiring (task 4.2,
design: CliInboxWiring, inbox Req 1.7, 2.1, 2.2, 2.5, 4.6, 5.3, 5.5, 5.6, 7.2,
7.3, 8.3).

Coverage, end to end through :class:`typer.testing.CliRunner`:

* An explicit ``SOURCE`` invocation behaves exactly as before -- no inbox
  settings are read (proven by an exploding monkeypatch on
  :func:`fitdocs.cli.load_inbox_settings`), and the existing exit-code
  contract holds (Req 2.2, 7.3).
* Every pre-flight error -- an unreadable or invalid settings file, a
  malformed ``[inbox]`` table, a malformed ``[tiles]`` table, an inbox path
  outside the data root that is missing, a malformed quarantine record, and
  ``--retry-quarantined`` combined with an explicit ``SOURCE`` -- exits with
  the configuration code and writes nothing (Req 1.4, 1.6, 1.7, 5.5, 5.6,
  7.2), and the pre-flight's documented order is pinned directly (Req 1.4 vs
  5.6).
* An empty-inbox drain succeeds, and a drain whose only exceptional entries
  are deferrals, known-quarantined files, or failed moves exits 0 (Req 2.4,
  4.6, 5.3, 6.5, 7.2).
* ``--out`` resolves the data root the drain runs against; ``--force``
  re-renders an already-archived inbox file; ``--no-prompt`` is forwarded to
  the load-pass session builder exactly as on the explicit-source path (Req
  2.5). ``--retry-quarantined`` genuinely reaches :func:`fitdocs.sync.drain`
  and reattempts a previously quarantined file (Req 5.5) -- not merely
  rejected in combination with SOURCE.
* The drain is rooted at the *configured* inbox path with the *configured*
  settings (ignore patterns, move disposition/processed_dir) and the loaded
  athlete inputs -- not at the data root, not at
  :data:`~fitdocs.inbox.DEFAULT_INBOX_SETTINGS`, and not with a ``None``
  processed directory or athlete (Req 1.1, 2.1, 2.3).
* The settings document is parsed once during the pre-flight -- checked by
  spying the shared reader in *every* module that can call it, not only
  ``fitdocs.cli`` (Req 1.7).
* Plugin load errors are still reported after the drain summary (mirroring
  the explicit-source path), and ``sync --help`` documents the no-argument
  drain and how the inbox location is determined (Req 8.3).
"""

from __future__ import annotations

import re
import stat
from pathlib import Path

import pytest
from typer.testing import CliRunner

import fitdocs.cli as cli
import fitdocs.tiles as tiles_module
from fitdocs.cli import app
from fitdocs.inbox import InboxNote
from fitdocs.sync import DrainReport, FileFailure, SyncReport
from tests.fixtures import builder

runner = CliRunner()

_BROKEN_PLUGIN_SOURCE = "raise RuntimeError('simulated local plugin import failure')\n"

# A drain sleeps for the configured settle interval (default 2s) once per
# invocation, REGARDLESS of candidate count (inbox Req 4.5) -- ``settle_seconds
# = 0`` is Req 4.4's documented, supported value that disables the wait
# entirely (task 2.2: a zero interval performs no sleep at all), so tests that
# do not exercise the settle interval itself use it to stay wall-clock-free.
_ZERO_SETTLE_TOML = "[inbox]\nsettle_seconds = 0\n"


@pytest.fixture(autouse=True)
def _offline_tiles(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep this suite network-free, mirroring ``tests/test_cli.py``."""
    monkeypatch.setattr(
        "fitdocs.tiles._default_fetch", lambda _url: b"\x89PNG\r\n\x1a\n"
    )


def _put(directory: Path, name: str, data: bytes) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    path.write_bytes(data)
    return path


def _nothing_written(data_root: Path) -> bool:
    """True when the pipeline's write-visible paths are all absent."""
    return not (
        (data_root / "workouts").exists()
        or (data_root / "fit-archive").exists()
        or (data_root / ".fitdocs" / "quarantine.toml").exists()
    )


def _empty_sync_report() -> SyncReport:
    return SyncReport(written=(), skipped=(), failures=(), warnings=())


def _drain_report(
    *,
    inbox: str = "inbox",
    sync: SyncReport | None = None,
    deferred: tuple[InboxNote, ...] = (),
    quarantined: tuple[InboxNote, ...] = (),
    moved: tuple[str, ...] = (),
    move_failures: tuple[InboxNote, ...] = (),
) -> DrainReport:
    return DrainReport(
        inbox=inbox,
        sync=sync if sync is not None else _empty_sync_report(),
        deferred=deferred,
        quarantined=quarantined,
        moved=moved,
        move_failures=move_failures,
    )


def _table_region(output: str) -> str:
    """Return only the box-drawn table's lines, excluding the ``Label:``
    detail headings printed beneath it (borrowed from
    ``tests/test_cli_drain_report.py`` so a row and a heading sharing text
    can never be confused)."""
    lines = output.splitlines()
    start = next(i for i, line in enumerate(lines) if line.lstrip().startswith("┏"))
    end = next(i for i, line in enumerate(lines) if line.lstrip().startswith("└"))
    return "\n".join(lines[start : end + 1])


def _row_count(table_region: str, label: str) -> int:
    """The single named row's count column; fails loudly if the row is
    missing or duplicated, rather than returning a misleading ``0``."""
    matches = re.findall(rf"│\s*{re.escape(label)}\s*│\s*(\d+)\s*│", table_region)
    assert len(matches) == 1, (
        f"expected exactly one {label!r} row, found {len(matches)}:\n{table_region}"
    )
    return int(matches[0])


# --- SOURCE becomes optional; help text describes the drain (Req 8.3) -------


def test_sync_help_describes_the_no_argument_drain_and_inbox_resolution() -> None:
    result = runner.invoke(app, ["sync", "--help"])

    assert result.exit_code == 0
    lowered = result.output.lower()
    assert "inbox" in lowered
    assert "fitdocs.toml" in result.output
    assert "--retry-quarantined" in result.output


# --- explicit-source path is untouched (Req 2.2, 7.3) ------------------------


def test_explicit_source_sync_never_reads_inbox_settings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Spies that explode if any inbox pre-flight step is ever consulted:
    an explicit-source invocation must not call any of them at all (Req 2.2,
    7.3)."""

    def _exploder(name: str) -> object:
        def _explode(*_args: object, **_kwargs: object) -> object:
            raise AssertionError(f"{name} must not run on the SOURCE path")

        return _explode

    monkeypatch.setattr(cli, "load_inbox_settings", _exploder("load_inbox_settings"))
    monkeypatch.setattr(cli, "validate_inbox_paths", _exploder("validate_inbox_paths"))
    monkeypatch.setattr(cli, "create_inbox_paths", _exploder("create_inbox_paths"))
    monkeypatch.setattr(cli, "load_quarantine", _exploder("load_quarantine"))

    source = tmp_path / "src"
    data_root = tmp_path / "data"
    data_root.mkdir()
    _put(source, "run.fit", builder.run_fit_bytes())

    result = runner.invoke(app, ["sync", str(source), "--out", str(data_root)])

    assert result.exit_code == 0
    assert "Written" in result.output


def test_explicit_source_behavior_and_exit_codes_are_unchanged(tmp_path: Path) -> None:
    source = tmp_path / "src"
    data_root = tmp_path / "data"
    data_root.mkdir()
    _put(source, "run.fit", builder.run_fit_bytes())

    result = runner.invoke(app, ["sync", str(source), "--out", str(data_root)])

    assert result.exit_code == 0
    assert (data_root / "fit-archive").exists()
    assert "Written" in result.output


# --- --retry-quarantined with an explicit source: config error (Req 5.5) ----


def test_retry_quarantined_with_explicit_source_is_a_configuration_error(
    tmp_path: Path,
) -> None:
    source = tmp_path / "src"
    data_root = tmp_path / "data"
    data_root.mkdir()
    _put(source, "run.fit", builder.run_fit_bytes())

    result = runner.invoke(
        app, ["sync", str(source), "--out", str(data_root), "--retry-quarantined"]
    )

    assert result.exit_code == 2
    assert "--retry-quarantined" in result.output
    assert _nothing_written(data_root)


# --- pre-flight errors: exit 2, nothing written (Req 1.4, 1.6, 1.7, 5.6) ----


def test_invalid_toml_settings_file_exits_two_before_any_write(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    data_root.mkdir()
    (data_root / "fitdocs.toml").write_text("not [ valid toml", encoding="utf-8")

    result = runner.invoke(app, ["sync", "--out", str(data_root)])

    assert result.exit_code == 2
    assert "fitdocs.toml" in result.output
    assert _nothing_written(data_root)


def test_unreadable_settings_file_exits_two_before_any_write(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    data_root.mkdir()
    settings = data_root / "fitdocs.toml"
    settings.write_text("[inbox]\npath = 'inbox'\n", encoding="utf-8")
    settings.chmod(0o000)
    try:
        result = runner.invoke(app, ["sync", "--out", str(data_root)])
    finally:
        settings.chmod(stat.S_IRUSR | stat.S_IWUSR)

    assert result.exit_code == 2
    assert "fitdocs.toml" in result.output
    assert _nothing_written(data_root)


def test_malformed_inbox_table_exits_two_before_any_write(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    data_root.mkdir()
    (data_root / "fitdocs.toml").write_text(
        "[inbox]\nsettle_seconds = 'not a number'\n", encoding="utf-8"
    )

    result = runner.invoke(app, ["sync", "--out", str(data_root)])

    assert result.exit_code == 2
    assert "settle_seconds" in result.output
    assert _nothing_written(data_root)


def test_malformed_tiles_table_on_drain_path_exits_two_before_any_write(
    tmp_path: Path,
) -> None:
    """The pre-flight's last step, the tile store, is a config error too --
    exercised specifically on the no-SOURCE drain path (design's five-step
    pre-flight sequence)."""
    data_root = tmp_path / "data"
    data_root.mkdir()
    (data_root / "fitdocs.toml").write_text(
        '[tiles]\nurl = "https://tiles.example/static.png"\n', encoding="utf-8"
    )

    result = runner.invoke(app, ["sync", "--out", str(data_root)])

    assert result.exit_code == 2
    assert "fitdocs.toml" in result.output
    assert "url" in result.output
    assert _nothing_written(data_root)


def test_inbox_outside_data_root_and_missing_exits_two_before_any_write(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "data"
    data_root.mkdir()
    outside_missing = tmp_path / "does-not-exist-inbox"
    (data_root / "fitdocs.toml").write_text(
        f'[inbox]\npath = "{outside_missing.as_posix()}"\n', encoding="utf-8"
    )

    result = runner.invoke(app, ["sync", "--out", str(data_root)])

    assert result.exit_code == 2
    assert (
        str(outside_missing) in result.output or outside_missing.name in result.output
    )
    assert _nothing_written(data_root)
    assert not outside_missing.exists()


def test_malformed_quarantine_record_exits_two_before_any_write(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    data_root.mkdir()
    state_dir = data_root / ".fitdocs"
    state_dir.mkdir()
    (state_dir / "quarantine.toml").write_text("not [ valid toml", encoding="utf-8")

    result = runner.invoke(app, ["sync", "--out", str(data_root)])

    assert result.exit_code == 2
    assert "quarantine.toml" in result.output
    # The pre-flight must not have created workouts/ or fit-archive/ -- the
    # quarantine.toml itself pre-existed this run and stays as the user left it.
    assert not (data_root / "workouts").exists()
    assert not (data_root / "fit-archive").exists()


def test_inbox_path_error_is_reported_before_the_quarantine_error(
    tmp_path: Path,
) -> None:
    """Pinning the documented order directly: with BOTH an outside-the-root
    missing inbox path AND a malformed quarantine record present, the inbox
    path error wins -- ``validate_inbox_paths`` runs, and refuses, before
    ``load_quarantine`` is ever called; the write-performing
    ``create_inbox_paths`` runs only after the quarantine record has been
    read successfully, so it never runs here at all."""
    data_root = tmp_path / "data"
    data_root.mkdir()
    outside_missing = tmp_path / "does-not-exist-inbox"
    (data_root / "fitdocs.toml").write_text(
        f'[inbox]\npath = "{outside_missing.as_posix()}"\n', encoding="utf-8"
    )
    state_dir = data_root / ".fitdocs"
    state_dir.mkdir()
    (state_dir / "quarantine.toml").write_text("not [ valid toml", encoding="utf-8")

    result = runner.invoke(app, ["sync", "--out", str(data_root)])

    assert result.exit_code == 2
    assert (
        str(outside_missing) in result.output or outside_missing.name in result.output
    )
    assert "quarantine.toml" not in result.output


# --- pre-flight parses the settings document once (Req 1.7) -----------------


def test_settings_document_is_parsed_once_during_the_inbox_preflight(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The inbox pre-flight (``[inbox]`` projection + tile-store construction)
    consults exactly one already-parsed document. The shared reader is
    spied in *both* ``fitdocs.cli`` (where the pre-flight and the
    pre-existing plugin-settings read call it) and ``fitdocs.tiles`` (where
    the convenience ``load_tile_settings`` would call it if the pre-flight
    mistakenly used that entry point instead of the already-parsed
    document) -- a Python ``from x import y`` binds a name per importing
    module, so a spy on only one module is blind to the other."""
    data_root = tmp_path / "data"
    data_root.mkdir()
    (data_root / "fitdocs.toml").write_text(_ZERO_SETTLE_TOML, encoding="utf-8")
    calls: list[Path] = []
    original = cli.load_settings_document

    def _spy(root: Path) -> object:
        calls.append(root)
        return original(root)

    monkeypatch.setattr(cli, "load_settings_document", _spy)
    monkeypatch.setattr(tiles_module, "load_settings_document", _spy)

    result = runner.invoke(app, ["sync", "--out", str(data_root)])

    assert result.exit_code == 0
    # One read for plugin discovery (pre-existing, separate concern) plus one
    # read inside the inbox pre-flight -- never a third for the tile store.
    assert len(calls) == 2


# --- empty inbox drains successfully (Req 2.4) -------------------------------


def test_empty_inbox_drain_succeeds_and_reports_nothing_written(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "data"
    data_root.mkdir()
    (data_root / "fitdocs.toml").write_text(_ZERO_SETTLE_TOML, encoding="utf-8")

    result = runner.invoke(app, ["sync", "--out", str(data_root)])

    assert result.exit_code == 0
    assert "Inbox" in result.output
    assert (data_root / "inbox").is_dir()
    assert _row_count(_table_region(result.output), "Written") == 0
    # No workout documents were produced (the declaration refresh may still
    # create workouts/ for its AGENTS.md, which is not a workout document).
    workouts = data_root / "workouts"
    docs = list(workouts.glob("*.md")) if workouts.exists() else []
    assert [p for p in docs if p.name != "AGENTS.md"] == []
    archive = data_root / "fit-archive"
    assert not archive.exists() or list(archive.glob("*.fit")) == []


# --- --out/--force/--no-prompt keep their meanings on the drain path (2.5) --


def test_out_option_resolves_the_data_root_the_drain_runs_against(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "elsewhere"
    data_root.mkdir()
    (data_root / "fitdocs.toml").write_text(_ZERO_SETTLE_TOML, encoding="utf-8")

    result = runner.invoke(app, ["sync", "--out", str(data_root)])

    assert result.exit_code == 0
    assert (data_root / "inbox").is_dir()


def test_force_option_re_renders_an_already_archived_inbox_file(
    tmp_path: Path,
) -> None:
    """``--force`` keeps its ordinary meaning on the drain path: an
    unforced re-drain of an unchanged, already-archived inbox file is
    skipped, and ``--force`` re-renders it (Req 2.5)."""
    data_root = tmp_path / "data"
    data_root.mkdir()
    (data_root / "fitdocs.toml").write_text(_ZERO_SETTLE_TOML, encoding="utf-8")
    inbox = data_root / "inbox"
    _put(inbox, "run.fit", builder.run_fit_bytes())

    first = runner.invoke(app, ["sync", "--out", str(data_root), "--no-prompt"])
    assert first.exit_code == 0
    assert _row_count(_table_region(first.output), "Written") == 1

    second = runner.invoke(app, ["sync", "--out", str(data_root), "--no-prompt"])
    assert second.exit_code == 0
    table2 = _table_region(second.output)
    assert _row_count(table2, "Written") == 0
    assert _row_count(table2, "Skipped") == 1

    third = runner.invoke(
        app, ["sync", "--out", str(data_root), "--no-prompt", "--force"]
    )
    assert third.exit_code == 0
    assert _row_count(_table_region(third.output), "Written") == 1


def test_no_prompt_flag_is_forwarded_to_the_session_builder_on_the_drain_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``--no-prompt`` is forwarded through ``_build_session`` exactly as on
    the explicit-source path (Req 2.5). Spied rather than asserted on
    output, since ``CliRunner``'s stdin is never a TTY -- the *value*
    forwarded is what distinguishes the two, not the resulting session
    class."""
    data_root = tmp_path / "data"
    data_root.mkdir()
    (data_root / "fitdocs.toml").write_text(_ZERO_SETTLE_TOML, encoding="utf-8")
    calls: list[bool] = []
    original = cli._build_session

    def _spy(*, no_prompt: bool) -> object:
        calls.append(no_prompt)
        return original(no_prompt=no_prompt)

    monkeypatch.setattr(cli, "_build_session", _spy)

    result = runner.invoke(app, ["sync", "--out", str(data_root), "--no-prompt"])
    assert result.exit_code == 0
    assert calls == [True]

    calls.clear()
    result = runner.invoke(app, ["sync", "--out", str(data_root)])
    assert result.exit_code == 0
    assert calls == [False]


def test_drain_processes_a_real_inbox_file_and_runs_the_load_pass(
    tmp_path: Path,
) -> None:
    """A genuine inbox file is admitted, written, and the training-load pass
    runs afterward exactly as it does for an explicit-source sync (Req 2.1)."""
    data_root = tmp_path / "data"
    data_root.mkdir()
    (data_root / "fitdocs.toml").write_text(_ZERO_SETTLE_TOML, encoding="utf-8")
    inbox = data_root / "inbox"
    _put(inbox, "run.fit", builder.run_fit_bytes())

    result = runner.invoke(app, ["sync", "--out", str(data_root), "--no-prompt"])

    assert result.exit_code == 0
    assert "Written" in result.output
    # The load pass ran (its own summary table is printed after the drain's).
    assert "Unsupported" in result.output or "Computed" in result.output
    assert list((data_root / "fit-archive").glob("*.fit"))


# --- known-quarantined files: reported quietly, drain still succeeds (5.3) --


def test_a_second_drain_reports_a_quarantined_file_quietly_and_exits_zero(
    tmp_path: Path,
) -> None:
    data_root = tmp_path / "data"
    data_root.mkdir()
    (data_root / "fitdocs.toml").write_text(_ZERO_SETTLE_TOML, encoding="utf-8")
    inbox = data_root / "inbox"
    _put(inbox, "bad.fit", builder.non_fit_bytes())

    first = runner.invoke(app, ["sync", "--out", str(data_root), "--no-prompt"])
    assert first.exit_code == 1  # the fresh source-level failure fails the run

    second = runner.invoke(app, ["sync", "--out", str(data_root), "--no-prompt"])

    assert second.exit_code == 0
    assert "Quarantined" in second.output
    assert "bad.fit" in second.output


# --- --retry-quarantined genuinely reaches drain() (Req 5.5) ----------------


def test_retry_quarantined_reattempts_and_clears_the_quarantine_entry(
    tmp_path: Path,
) -> None:
    """Not just "rejected with SOURCE": ``--retry-quarantined`` actually
    reaches :func:`fitdocs.sync.drain` and re-attempts a known-bad inbox
    file -- a fresh failure moves it from the Quarantined channel back to
    Failed and clears its Quarantined count to zero (Req 5.5)."""
    data_root = tmp_path / "data"
    data_root.mkdir()
    (data_root / "fitdocs.toml").write_text(_ZERO_SETTLE_TOML, encoding="utf-8")
    inbox = data_root / "inbox"
    _put(inbox, "bad.fit", builder.non_fit_bytes())

    first = runner.invoke(app, ["sync", "--out", str(data_root), "--no-prompt"])
    assert first.exit_code == 1

    second = runner.invoke(app, ["sync", "--out", str(data_root), "--no-prompt"])
    assert second.exit_code == 0
    assert _row_count(_table_region(second.output), "Quarantined") == 1

    third = runner.invoke(
        app,
        ["sync", "--out", str(data_root), "--no-prompt", "--retry-quarantined"],
    )

    assert third.exit_code == 1
    table3 = _table_region(third.output)
    assert _row_count(table3, "Quarantined") == 0
    assert _row_count(table3, "Failed") == 1
    assert "bad.fit" in third.output


# --- the drain is rooted/configured correctly, not at defaults (Req 1.1, 2.1, 2.3) -


def test_drain_uses_the_configured_inbox_path_and_ignore_patterns(
    tmp_path: Path,
) -> None:
    """The drain must be rooted at the *configured* inbox path with the
    *configured* ignore patterns -- not at the data root as a whole (which
    would also sweep in an unrelated file sitting at the never-configured
    default ``inbox/`` location) and not at
    :data:`~fitdocs.inbox.DEFAULT_INBOX_SETTINGS` (whose empty ``ignore``
    would let a file meant to be excluded reach the pipeline and fail)."""
    data_root = tmp_path / "data"
    data_root.mkdir()
    (data_root / "fitdocs.toml").write_text(
        '[inbox]\npath = "incoming"\nignore = ["skip-*"]\nsettle_seconds = 0\n',
        encoding="utf-8",
    )
    configured_inbox = data_root / "incoming"
    _put(configured_inbox, "run.fit", builder.run_fit_bytes())
    # Would fail if ever handed to the pipeline -- only excluded if the
    # configured ignore pattern actually reaches select_candidates().
    _put(configured_inbox, "skip-me.fit", builder.non_fit_bytes())
    # Sits at the DEFAULT (unconfigured) inbox location: must never be
    # scanned at all -- only reachable if the drain were wrongly rooted at
    # the whole data root instead of the configured "incoming" directory.
    _put(data_root / "inbox", "decoy.fit", builder.non_fit_bytes())

    result = runner.invoke(app, ["sync", "--out", str(data_root), "--no-prompt"])

    assert result.exit_code == 0
    assert "incoming" in result.output  # names the drained inbox path (2.3)
    table = _table_region(result.output)
    assert _row_count(table, "Written") == 1
    assert _row_count(table, "Failed") == 0
    assert "skip-me.fit" not in result.output
    assert "decoy.fit" not in result.output


def test_drain_receives_the_configured_settings_and_loaded_athlete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A spy that wraps the real :func:`fitdocs.sync.drain` (so the drain
    still genuinely runs) and records the arguments it was called with:
    the resolved configured inbox path, the settings actually projected
    from ``[inbox]`` (not :data:`~fitdocs.inbox.DEFAULT_INBOX_SETTINGS`),
    and the loaded athlete inputs (not ``None``)."""
    data_root = tmp_path / "data"
    data_root.mkdir()
    (data_root / "fitdocs.toml").write_text(
        '[inbox]\npath = "incoming"\nsettle_seconds = 0\n', encoding="utf-8"
    )
    (data_root / "athlete.toml").write_text("ftp_watts = 250\n", encoding="utf-8")
    configured_inbox = data_root / "incoming"
    _put(configured_inbox, "run.fit", builder.run_fit_bytes())

    calls: list[tuple[object, ...]] = []
    original_drain = cli.drain

    def _spy(inbox_arg: object, data_root_arg: object, **kwargs: object) -> object:
        calls.append((inbox_arg, data_root_arg, kwargs))
        return original_drain(inbox_arg, data_root_arg, **kwargs)

    monkeypatch.setattr(cli, "drain", _spy)

    result = runner.invoke(app, ["sync", "--out", str(data_root), "--no-prompt"])

    assert result.exit_code == 0
    assert len(calls) == 1
    inbox_arg, data_root_arg, kwargs = calls[0]
    assert inbox_arg == configured_inbox
    assert data_root_arg == data_root
    assert kwargs["settings"].path == "incoming"  # type: ignore[union-attr]
    assert kwargs["athlete"] is not None


def test_move_disposition_actually_relocates_a_processed_file(
    tmp_path: Path,
) -> None:
    """A real, unmocked drain under the configured move disposition: the
    processed-files destination genuinely reaches :func:`fitdocs.sync.drain`
    (not ``None``) -- the file is relocated out of the inbox into the
    configured destination."""
    data_root = tmp_path / "data"
    data_root.mkdir()
    (data_root / "fitdocs.toml").write_text(
        '[inbox]\npath = "incoming"\ndisposition = "move"\n'
        'processed_dir = "processed"\nsettle_seconds = 0\n',
        encoding="utf-8",
    )
    inbox = data_root / "incoming"
    _put(inbox, "run.fit", builder.run_fit_bytes())

    result = runner.invoke(app, ["sync", "--out", str(data_root), "--no-prompt"])

    assert result.exit_code == 0
    table = _table_region(result.output)
    assert _row_count(table, "Moved") == 1
    assert not (inbox / "run.fit").exists()
    assert list((data_root / "processed").glob("*.fit"))


# --- exit-code contract: deferrals/quarantined/move-failures never fail -----
#
# These exercise the CLI's own exit-code decision (``_finish`` reads only
# ``drain_report.sync.failures``) via a canned DrainReport returned from a
# monkeypatched ``drain()`` -- legitimate for this task, which wires the
# already-implemented ``drain()`` rather than reimplementing its channel
# semantics (already locked by ``tests/test_drain.py``).


def test_drain_with_only_deferrals_exits_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_root = tmp_path / "data"
    data_root.mkdir()
    report = _drain_report(
        deferred=(InboxNote(subject="partial.fit", detail="size still changing"),)
    )
    monkeypatch.setattr(cli, "drain", lambda *a, **k: report)

    result = runner.invoke(app, ["sync", "--out", str(data_root), "--no-prompt"])

    assert result.exit_code == 0
    assert "Deferred" in result.output
    assert "partial.fit" in result.output


def test_drain_with_only_quarantined_exits_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_root = tmp_path / "data"
    data_root.mkdir()
    report = _drain_report(
        quarantined=(InboxNote(subject="known-bad.fit", detail="CRC mismatch"),)
    )
    monkeypatch.setattr(cli, "drain", lambda *a, **k: report)

    result = runner.invoke(app, ["sync", "--out", str(data_root), "--no-prompt"])

    assert result.exit_code == 0
    assert "Quarantined" in result.output
    assert "known-bad.fit" in result.output


def test_drain_with_only_failed_moves_exits_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_root = tmp_path / "data"
    data_root.mkdir()
    report = _drain_report(
        move_failures=(
            InboxNote(
                subject="processed-elsewhere.fit",
                detail="destination is read-only",
            ),
        )
    )
    monkeypatch.setattr(cli, "drain", lambda *a, **k: report)

    result = runner.invoke(app, ["sync", "--out", str(data_root), "--no-prompt"])

    assert result.exit_code == 0
    assert "Move failures" in result.output
    assert "processed-elsewhere.fit" in result.output


def test_drain_with_a_genuine_failure_exits_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A genuine per-file failure in the wrapped sync report still drives the
    failure exit code on the drain path (Req 7.2)."""
    data_root = tmp_path / "data"
    data_root.mkdir()
    sync_report = SyncReport(
        written=(),
        skipped=(),
        failures=(FileFailure(source="broken.fit", reason="CRC mismatch"),),
        warnings=(),
    )
    report = _drain_report(sync=sync_report)
    monkeypatch.setattr(cli, "drain", lambda *a, **k: report)

    result = runner.invoke(app, ["sync", "--out", str(data_root), "--no-prompt"])

    assert result.exit_code == 1
    assert "broken.fit" in result.output


# --- plugin load errors are still reported on the drain path (parity) -------


def test_drain_reports_plugin_load_errors_after_the_drain_summary(
    tmp_path: Path,
) -> None:
    """A broken local plugin is still reported after the run's summaries on
    the drain path, exactly as on the explicit-source path -- never a
    failure, never changes the exit code (mirrors ``tests/test_cli.py``'s
    ``test_sync_with_broken_local_plugin_reports_failure_and_exits_zero``)."""
    data_root = tmp_path / "data"
    data_root.mkdir()
    plugins_dir = data_root / "plugins"
    plugins_dir.mkdir()
    (plugins_dir / "broken.py").write_text(_BROKEN_PLUGIN_SOURCE, encoding="utf-8")
    (data_root / "fitdocs.toml").write_text(
        '[plugins]\npath = "plugins"\n\n[inbox]\nsettle_seconds = 0\n',
        encoding="utf-8",
    )

    result = runner.invoke(app, ["sync", "--out", str(data_root), "--no-prompt"])

    assert result.exit_code == 0
    assert "broken.py" in result.output
    assert "simulated local plugin import failure" in result.output
