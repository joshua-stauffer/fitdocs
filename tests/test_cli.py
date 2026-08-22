"""CLI end-to-end tests: the installable ``fitdocs`` entry point.

The baseline shell answers ``--version`` and ``--help`` (Requirements 14.1,
14.2, 14.3). On top of that this module drives the two feature commands
end-to-end through :class:`typer.testing.CliRunner` over temporary data roots
and synthetic ``.fit`` fixtures, locking the observable contract of task 4.4:

* ``sync SOURCE [--out PATH] [--force]`` and ``regen [--out PATH]`` resolve the
  data root and load athlete inputs *before* any processing, thread the system
  local timezone into the engine, and print an end-of-run summary of written,
  skipped, and failed files with the reason for each failure (Req 1.4, 2.1).
* Exit codes (Req 1.5, 2.2): ``0`` on success including an all-skipped run,
  ``1`` when any file failed, ``2`` for configuration errors -- an unresolvable
  data root (message listing the three options), a missing source directory, or
  a malformed ``athlete.toml``.

Content assertions read ``result.output`` (combined stdout + stderr) and match
robust fragments -- file basenames and reason text -- rather than table borders.
"""

from __future__ import annotations

import ast
import inspect
from collections.abc import Callable, Sequence
from datetime import UTC
from importlib.metadata import version
from pathlib import Path

import pytest
from typer.testing import CliRunner

from fitdocs import Activity, DerivedMetrics, Modality
from fitdocs import cli as cli_module
from fitdocs.cli import app
from fitdocs.config import DataRootError
from fitdocs.declaration import DECLARATION_FILENAME
from fitdocs.load import engine as load_engine_module
from fitdocs.load import registry as load_registry
from fitdocs.load import settings as load_settings_module
from fitdocs.load.engine import apply_load
from fitdocs.load.types import (
    Computed,
    InteractionSession,
    LoadContext,
    LoadOutcome,
    LoadResult,
    ProfileView,
    Unsupported,
)
from fitdocs.plugins import (
    BuiltIn,
    Distribution,
    LocalFile,
    PluginInfo,
    PluginLoadError,
    PluginReport,
)
from fitdocs.render.charts.map import TileRef
from fitdocs.sync import sync as _engine_sync
from tests.fixtures import builder

runner = CliRunner()


@pytest.fixture(autouse=True)
def _offline_tiles(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep every CLI ``sync``/``regen`` network-free (task 6.1 test guard).

    ``sync``/``regen`` now build a real ``TileStore`` from the data root's
    (defaulted) settings and pass it to the engine; a GPS-bearing fixture with the
    default provider enabled would otherwise fetch basemap tiles over the network
    on a cold cache. Patching the module fetch seam to return deterministic bytes
    makes tile resolution succeed offline, so no test in this suite performs real
    network access (Req 4.2). Tests that assert the warning path instead disable
    tile requests in ``fitdocs.toml`` -- the opt-out gate raises before fetch, so
    this patch is inert for them.
    """
    monkeypatch.setattr(
        "fitdocs.tiles._default_fetch", lambda _url: b"\x89PNG\r\n\x1a\n"
    )


# The CLI threads the *system local* timezone into the engine, so a document's
# date/time suffix is machine-dependent; tests assert on the stable sport slug
# (`-run-`, `-ride-`) the engine always embeds, never on a hardcoded time.
_RUN_SLUG = "-run-"
_RIDE_SLUG = "-ride-"


def _put(source_dir: Path, name: str, data: bytes) -> Path:
    """Write fixture ``.fit`` bytes into (a possibly fresh) source directory."""
    source_dir.mkdir(parents=True, exist_ok=True)
    path = source_dir / name
    path.write_bytes(data)
    return path


def _docs(data_root: Path) -> list[str]:
    """Every workout document basename under ``workouts/``.

    Excludes the in-tree ownership declaration (``AGENTS.md``, task 4.2, Req
    3.7): ``sync``/``regen`` place it in every declared directory, and its
    name happens to end in ``.md``, but it is not a workout document and never
    appears in the written/skipped/failed summary.
    """
    workouts = data_root / "workouts"
    if not workouts.is_dir():
        return []
    return sorted(
        p.name for p in workouts.glob("*.md") if p.name != DECLARATION_FILENAME
    )


# --- baseline shell (Req 14.1, 14.2, 14.3) ----------------------------------


def test_version_flag_reports_installed_version() -> None:
    """``--version`` prints the version resolved from package metadata."""
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert version("fitdocs") in result.stdout


def test_help_flag_documents_the_tool() -> None:
    """``--help`` exits cleanly and prints usage plus the tool name."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Usage" in result.stdout
    assert "fitdocs" in result.stdout


def test_help_lists_sync_and_regen_commands() -> None:
    """``--help`` documents the two feature commands (Req 14.2)."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "sync" in result.stdout
    assert "regen" in result.stdout


def test_sync_help_documents_flags() -> None:
    """``sync --help`` documents SOURCE and the --out / --force / --no-prompt flags."""
    result = runner.invoke(app, ["sync", "--help"])
    assert result.exit_code == 0
    assert "--out" in result.stdout
    assert "--force" in result.stdout
    # sync now runs the load pass and honors --no-prompt for it (Req 8.1, 3.5).
    assert "--no-prompt" in result.stdout


def test_regen_help_documents_flag() -> None:
    """``regen --help`` documents the --out flag."""
    result = runner.invoke(app, ["regen", "--help"])
    assert result.exit_code == 0
    assert "--out" in result.stdout


# --- success: docs written, summary printed, exit 0 (Req 1.4, 1.5, 2.1) ------


def test_sync_writes_docs_reports_summary_and_exits_zero(tmp_path: Path) -> None:
    source = tmp_path / "src"
    data_root = tmp_path / "data"
    data_root.mkdir()
    _put(source, "run.fit", builder.run_fit_bytes())
    _put(source, "ride.fit", builder.ride_fit_bytes())

    result = runner.invoke(app, ["sync", str(source), "--out", str(data_root)])

    assert result.exit_code == 0
    # A document per activity was written to disk, with its archived source.
    docs = _docs(data_root)
    assert len(docs) == 2
    assert any(_RUN_SLUG in name for name in docs)
    assert any(_RIDE_SLUG in name for name in docs)
    assert list((data_root / "fit-archive").glob("*.fit"))
    # The end-of-run summary lists the written documents and a written count.
    assert "Written" in result.output
    for name in docs:
        assert name in result.output
    # sync now runs the load pass after writing docs (Req 8.1): its summary
    # prints, and the ride doc -- a sport no calculator supports -- ends up in
    # the honest unsupported load state.
    assert "Unsupported" in result.output
    ride_doc = next(name for name in docs if _RIDE_SLUG in name)
    ride_text = (data_root / "workouts" / ride_doc).read_text(encoding="utf-8")
    assert "fitdocs-load" in ride_text


# --- all-skipped re-run is still success (Req 1.5) --------------------------


def test_rerun_sync_skips_everything_and_still_exits_zero(tmp_path: Path) -> None:
    source = tmp_path / "src"
    data_root = tmp_path / "data"
    data_root.mkdir()
    _put(source, "run.fit", builder.run_fit_bytes())

    first = runner.invoke(app, ["sync", str(source), "--out", str(data_root)])
    assert first.exit_code == 0

    second = runner.invoke(app, ["sync", str(source), "--out", str(data_root)])
    # Everything already archived -> all skipped, no failures -> success (Req 1.5).
    assert second.exit_code == 0
    assert "Skipped" in second.output


# --- partial failure: exit 1, failure named, good files still write (Req 1.5) -


def test_corrupt_file_yields_exit_one_naming_it_while_good_files_write(
    tmp_path: Path,
) -> None:
    source = tmp_path / "src"
    data_root = tmp_path / "data"
    data_root.mkdir()
    _put(source, "bad.fit", builder.non_fit_bytes())
    _put(source, "good.fit", builder.run_fit_bytes())

    result = runner.invoke(app, ["sync", str(source), "--out", str(data_root)])

    # A per-file failure makes the run exit non-zero (Req 1.5).
    assert result.exit_code == 1
    # The summary names the failed file and its reason.
    assert "bad.fit" in result.output
    assert "not a FIT file" in result.output
    assert "Failed" in result.output
    # The healthy file still produced its document (batch never aborts, Req 1.3).
    assert any(_RUN_SLUG in name for name in _docs(data_root))


# --- config error: unresolvable data root (Req 2.2) -------------------------


def test_missing_data_root_config_exits_two_listing_three_options(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("FITDOCS_DATA", raising=False)
    cwd = tmp_path / "cwd"  # a directory with no .fitdocs/data-root pointer
    cwd.mkdir()
    monkeypatch.chdir(cwd)
    source = tmp_path / "src"
    _put(source, "run.fit", builder.run_fit_bytes())

    result = runner.invoke(app, ["sync", str(source)])

    assert result.exit_code == 2
    # The instructive message lists all three configuration options (Req 2.2).
    assert "--out" in result.output
    assert "FITDOCS_DATA" in result.output
    assert ".fitdocs/data-root" in result.output
    # Nothing was written anywhere.
    assert not (cwd / "workouts").exists()


# --- config error: missing source directory (Req 1.1, 2.x) ------------------


def test_missing_source_directory_exits_two(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    data_root.mkdir()
    missing = tmp_path / "does-not-exist"

    result = runner.invoke(app, ["sync", str(missing), "--out", str(data_root)])

    assert result.exit_code == 2
    assert "does-not-exist" in result.output
    assert not (data_root / "workouts").exists()


# --- config error: malformed athlete.toml (Req 2.x, 8.3) --------------------


def test_malformed_athlete_toml_exits_two(tmp_path: Path) -> None:
    source = tmp_path / "src"
    data_root = tmp_path / "data"
    data_root.mkdir()
    _put(source, "run.fit", builder.run_fit_bytes())
    # Valid TOML, but a threshold with the wrong value type -> AthleteFileError.
    (data_root / "athlete.toml").write_text(
        "ftp_watts = 'not a number'\n", encoding="utf-8"
    )

    result = runner.invoke(app, ["sync", str(source), "--out", str(data_root)])

    assert result.exit_code == 2
    assert "athlete.toml" in result.output
    # A configuration error writes nothing (Req 2.2).
    assert not (data_root / "workouts").exists()


# --- config error: malformed [load] table (task 4.2, Req 8.4, 14.6) ---------
#
# The ``[load]`` table is read *inside* ``apply_load`` (task 4.1), not by this
# module (task 4.2's negative obligation) -- so the resulting
# ``LoadSettingsError`` must still surface as the CLI's ordinary configuration
# error (exit 2, nothing written) through the *shared* ``SettingsError`` this
# module already maps to that exit status for the malformed-athlete/-plugins/
# -tiles tables above, with no new handler naming the load-settings type.


def test_malformed_load_table_exits_two_and_writes_nothing(tmp_path: Path) -> None:
    """A malformed ``[load]`` table (wrong value type for ``default_calculator``)
    surfaces as the standard configuration error -- exit 2, an instructive
    message naming the settings file and the offending key, and the existing
    workout document left byte-identical (nothing written by the load pass)."""
    source = tmp_path / "src"
    data_root = tmp_path / "data"
    data_root.mkdir()
    _put(source, "run.fit", builder.run_fit_bytes())
    first = runner.invoke(app, ["sync", str(source), "--out", str(data_root)])
    assert first.exit_code == 0
    doc_path = next((data_root / "workouts").glob("*.md"))
    before = doc_path.read_bytes()

    (data_root / "fitdocs.toml").write_text(
        "[load]\ndefault_calculator = 123\n", encoding="utf-8"
    )

    result = runner.invoke(app, ["load", "--out", str(data_root)])

    assert result.exit_code == 2
    assert "fitdocs.toml" in result.output
    assert "default_calculator" in result.output
    # Nothing was (re)written by the load pass under the configuration error.
    assert doc_path.read_bytes() == before


# --- config error: invalid staleness window (task 5.3, Req 5.5) -------------
#
# ``benchmark_staleness_days`` is this spec's own key in the shared ``[load]``
# table (task 2.2's reader). Its ``LoadSettingsError`` must reach the CLI
# through the same shared ``SettingsError`` clause as the malformed
# ``default_calculator`` case above, with no dedicated handler naming the
# load-settings type (design: CLIErrorSurface). This is Req 5.5's CLI leg
# only: Req 2.9 (a *benchmark* validation failure, routed through
# ``ProfileError``) is a different requirement and is covered separately,
# below, by ``test_malformed_benchmark_entry_exits_two_and_writes_nothing``.


def test_invalid_staleness_window_exits_two_and_writes_nothing(
    tmp_path: Path,
) -> None:
    """A non-positive ``[load] benchmark_staleness_days`` surfaces as the
    standard configuration error -- exit 2, an instructive message naming the
    settings file and the offending key, and the existing workout document
    left byte-identical (nothing written by the load pass).

    The "nothing written" clause is only a meaningful assertion if the
    document, left alone, is something the pass *would* rewrite: a bare
    ``sync`` with no calculator registered leaves it in the honest
    ``unsupported`` state, asserted below as a precondition. Two stub
    calculators are then registered (after that first sync, so it plays no
    part in producing the precondition) and the settings file configures one
    of them, unambiguously, as the default -- so if the ``[load]`` table's
    validation were skipped or deferred past the document loop, this same
    fixture would compute and rewrite the document. Only the abort keeps it
    byte-identical; that is what the final assertion actually discriminates.
    """
    source = tmp_path / "src"
    data_root = tmp_path / "data"
    data_root.mkdir()
    _put(source, "run.fit", builder.run_fit_bytes())
    first = runner.invoke(app, ["sync", str(source), "--out", str(data_root)])
    assert first.exit_code == 0
    doc_path = next((data_root / "workouts").glob("*.md"))
    before = doc_path.read_bytes()
    # Precondition: the document is genuinely computable-and-uncomputed, not
    # merely unchanged by coincidence -- it already carries the honest
    # "unsupported" payload a supporting calculator would replace.
    assert "<!-- fitdocs-load:v2" in before.decode("utf-8")
    assert '"status":"unsupported"' in before.decode("utf-8")

    stop_stubs = _register_stub_calculators()
    try:
        (data_root / "fitdocs.toml").write_text(
            '[load]\ndefault_calculator = "cli-stub-a"\nbenchmark_staleness_days = 0\n',
            encoding="utf-8",
        )

        result = runner.invoke(app, ["load", "--out", str(data_root)])

        assert result.exit_code == 2
        unwrapped = result.output.replace("\n", "")
        assert "benchmark_staleness_days" in unwrapped
        assert str(data_root / "fitdocs.toml") in unwrapped
        # Nothing was (re)written by the load pass under the configuration
        # error -- discriminating because, with the same registered stub and
        # a valid staleness window, this exact fixture computes and rewrites
        # the document (see the docstring above).
        assert doc_path.read_bytes() == before
    finally:
        stop_stubs()


# --- config error: malformed benchmark entry (task 5.3, Req 2.9) ------------
#
# Req 2.9's CLIErrorSurface leg: a benchmark validation failure raises
# ``ProfileError`` (``fitdocs/load/profile.py``), routed through the same
# ``except (ProfileError, AthleteFileError, UnknownCalculatorError,
# SettingsError)`` clause at ``cli.py:580-585`` as every other configuration
# error this module maps to exit 2 -- not a dedicated handler. ``ProfileError``
# subclasses ``AthleteFileError``, so removing only the ``ProfileError`` tuple
# entry is a no-op mutation (``AthleteFileError`` still catches it); the test
# below is measured to redden only when *both* are removed from the tuple --
# that pair, together, is what is actually pinned.


def test_malformed_benchmark_entry_exits_two_and_writes_nothing(
    tmp_path: Path,
) -> None:
    """A malformed ``[[benchmarks...]]`` entry in ``athlete.toml`` (missing
    ``value``) surfaces as the standard configuration error through the CLI's
    ``ProfileError``/``AthleteFileError`` route -- exit 2 and a message naming
    the offending entry (Req 2.9).

    As in ``test_invalid_staleness_window_exits_two_and_writes_nothing``, a
    stub calculator is registered and configured as the default *after* the
    first (bare) sync produces the honest ``unsupported`` precondition below,
    so the byte-identical assertion is independently discriminating for this
    call site too: ``profile = load_profile(data_root)`` (``engine.py:266``)
    runs before the document loop and before ``load_load_settings``/
    ``validate_configured``. Deferring that ``load_profile`` call past the
    document loop and re-raising its error afterwards makes this exact
    fixture compute and rewrite the document with the registered stub,
    reddening the final assertion below (measured as a sole failure)."""
    source = tmp_path / "src"
    data_root = tmp_path / "data"
    data_root.mkdir()
    _put(source, "run.fit", builder.run_fit_bytes())
    first = runner.invoke(app, ["sync", str(source), "--out", str(data_root)])
    assert first.exit_code == 0
    doc_path = next((data_root / "workouts").glob("*.md"))
    before = doc_path.read_bytes()
    # Precondition: the document is genuinely computable-and-uncomputed, not
    # merely unchanged by coincidence -- it already carries the honest
    # "unsupported" payload a supporting calculator would replace.
    assert "<!-- fitdocs-load:v2" in before.decode("utf-8")
    assert '"status":"unsupported"' in before.decode("utf-8")

    stop_stubs = _register_stub_calculators()
    try:
        (data_root / "fitdocs.toml").write_text(
            '[load]\ndefault_calculator = "cli-stub-a"\n', encoding="utf-8"
        )
        (data_root / "athlete.toml").write_text(
            "[[benchmarks.run.ftp_watts]]\nmeasured_on = 2024-03-01\n",
            encoding="utf-8",
        )

        result = runner.invoke(app, ["load", "--out", str(data_root)])

        assert result.exit_code == 2
        assert "ftp_watts" in result.output
        assert "value" in result.output
        # Nothing was (re)written by the load pass under the configuration
        # error -- discriminating because, with the same registered stub and
        # a well-formed benchmark entry, this exact fixture computes and
        # rewrites the document (see the docstring above).
        assert doc_path.read_bytes() == before
    finally:
        stop_stubs()


def test_configured_default_unregistered_calculator_exits_two_and_writes_nothing(
    tmp_path: Path,
) -> None:
    """A configured ``[load] default_calculator`` naming an id no calculator
    registers is a configuration error -- exit 2, an instructive message
    naming the offending configured value and the registered ids, and the
    existing workout document left byte-identical (Req 10.4's
    configured-default scenario, reached here through the CLI itself rather
    than only at the engine/arbitrate unit level)."""
    teardown = _register_stub_calculators()
    try:
        source = tmp_path / "src"
        data_root = tmp_path / "data"
        data_root.mkdir()
        _put(source, "run.fit", builder.run_fit_bytes())
        first = runner.invoke(app, ["sync", str(source), "--out", str(data_root)])
        assert first.exit_code == 0
        doc_path = next((data_root / "workouts").glob("*.md"))
        before = doc_path.read_bytes()

        (data_root / "fitdocs.toml").write_text(
            '[load]\ndefault_calculator = "does-not-exist"\n', encoding="utf-8"
        )

        result = runner.invoke(app, ["load", "--out", str(data_root)])

        assert result.exit_code == 2
        assert "does-not-exist" in result.output
        assert "cli-stub-a" in result.output
        assert "cli-stub-b" in result.output
        # Nothing was (re)written by the load pass under the configuration error.
        assert doc_path.read_bytes() == before
    finally:
        teardown()


# --- regen after a successful sync reports and exits 0 (Req 4.3) -------------


def test_regen_after_sync_reports_summary_and_exits_zero(tmp_path: Path) -> None:
    source = tmp_path / "src"
    data_root = tmp_path / "data"
    data_root.mkdir()
    _put(source, "run.fit", builder.run_fit_bytes())
    synced = runner.invoke(app, ["sync", str(source), "--out", str(data_root)])
    assert synced.exit_code == 0

    result = runner.invoke(app, ["regen", "--out", str(data_root)])

    assert result.exit_code == 0
    assert "Written" in result.output
    for name in _docs(data_root):
        assert name in result.output


# --- route-map tile wiring: warnings channel, config errors (task 6.1) -------
#
# ``sync``/``regen`` build a ``TileStore`` from ``<data-root>/fitdocs.toml``
# ``[tiles]`` and pass it to the engine. A malformed table is a loud exit-2
# config error (nothing written); a tile miss under the persistent opt-out is a
# non-fatal, doc-scoped WARNING that is reported but NEVER changes the exit code
# (Req 4.2, 4.3, 4.4). These cases stay offline by design: the opt-out gate
# raises before any fetch, so no network access occurs.


def test_sync_reports_map_warning_row_and_detail_without_failing(
    tmp_path: Path,
) -> None:
    """A GPS run with tile requests disabled and a cold cache omits its map: the
    sync summary shows a Warnings count row plus the per-document detail (the doc
    it names and the reason), and the run still exits 0 (Req 4.3, 4.4)."""
    source = tmp_path / "src"
    data_root = tmp_path / "data"
    data_root.mkdir()
    _put(source, "run.fit", builder.run_fit_bytes())
    # Persistent opt-out: no tile requests. The GPS run plans a map whose tiles are
    # not cached, so the map is omitted with a warning -- offline by construction.
    (data_root / "fitdocs.toml").write_text(
        "[tiles]\nenabled = false\n", encoding="utf-8"
    )

    result = runner.invoke(app, ["sync", str(source), "--out", str(data_root)])

    # A map omission is never a failure: warnings do not change the exit code.
    assert result.exit_code == 0
    # The summary carries a Warnings count row and the per-document warning detail.
    assert "Warnings" in result.output
    run_doc = next(name for name in _docs(data_root) if _RUN_SLUG in name)
    assert run_doc in result.output  # the warning names the affected document
    assert "disabled" in result.output.lower()  # ...and why its map was omitted
    # The document was written -- just without a Map section.
    run_text = (data_root / "workouts" / run_doc).read_text(encoding="utf-8")
    assert "## Map" not in run_text
    assert "## Summary" in run_text  # every other section renders normally


def test_malformed_tiles_settings_exits_two_before_any_write(tmp_path: Path) -> None:
    """A malformed ``fitdocs.toml`` ``[tiles]`` table is a loud config error: the
    command exits 2 with an instructive message and writes NOTHING (Req 4.2)."""
    source = tmp_path / "src"
    data_root = tmp_path / "data"
    data_root.mkdir()
    _put(source, "run.fit", builder.run_fit_bytes())
    # A provider url template missing the {z}/{x}/{y} tile-coordinate placeholders.
    (data_root / "fitdocs.toml").write_text(
        '[tiles]\nurl = "https://tiles.example/static.png"\n', encoding="utf-8"
    )

    result = runner.invoke(app, ["sync", str(source), "--out", str(data_root)])

    assert result.exit_code == 2
    # The instructive message names the file and the offending key.
    assert "fitdocs.toml" in result.output
    assert "url" in result.output
    # A configuration error writes nothing: no documents, assets, or archive.
    assert not (data_root / "workouts").exists()
    assert not (data_root / "fit-archive").exists()


def test_regen_with_map_warning_exits_zero(tmp_path: Path) -> None:
    """``fitdocs regen`` whose only issue is an omitted map exits 0 and reports the
    warning: the document is rebuilt and warnings never alter the exit code, so
    regeneration stays offline-tolerant (Req 4.3, 4.4)."""
    source = tmp_path / "src"
    data_root = tmp_path / "data"
    data_root.mkdir()
    _put(source, "run.fit", builder.run_fit_bytes())
    # Disable tile requests for the whole scenario: the initial sync and the regen
    # both omit the map with a warning, entirely offline.
    (data_root / "fitdocs.toml").write_text(
        "[tiles]\nenabled = false\n", encoding="utf-8"
    )
    synced = runner.invoke(app, ["sync", str(source), "--out", str(data_root)])
    assert synced.exit_code == 0

    result = runner.invoke(app, ["regen", "--out", str(data_root)])

    # The map-only warning leaves the exit code at 0 (Req 4.4).
    assert result.exit_code == 0
    assert "Written" in result.output
    assert "Warnings" in result.output
    run_doc = next(name for name in _docs(data_root) if _RUN_SLUG in name)
    assert run_doc in result.output
    # The document was regenerated (still present) without a Map section.
    run_text = (data_root / "workouts" / run_doc).read_text(encoding="utf-8")
    assert "## Map" not in run_text


# --- symlink confinement through the real CLI (wiki-contract task 7.2) ------
#
# Task 5.1/5.2's engine-level tests drove ``sync()``/``regen()`` directly and
# could not see a training-load pass that skipped the symlink check the
# document-rewrite already had (found on review). These two tests instead
# drive the installed ``fitdocs`` entry point end to end, exactly like every
# other test in this module, so a future regression that only shows up when
# the CLI wires the load pass after ``sync``/``regen`` cannot hide again.
#
# Critically, the symlink's target must be a GENUINE, rewritable workout
# document -- not merely a stray file outside the data root -- in a state the
# training-load pass would actually try to write (its ``load`` region still
# the not-computed placeholder). A stray non-document is filtered out by
# ``is_workout_document`` before ``docio``'s symlink refusal is ever reached,
# so it cannot exercise -- and therefore cannot prove -- that refusal. Its
# archived source must also be present under the real data root's
# ``fit-archive/`` so the load pass's archive resolution succeeds if it were
# ever allowed to read through the symlink at all.


class _DummyTiles:
    """A minimal offline ``TileSource`` for staging a prep document (no GPS)."""

    attribution = "© OpenStreetMap contributors"

    def resolve(self, refs: Sequence[TileRef]) -> dict[TileRef, bytes]:
        return {ref: b"\x89PNG\r\n\x1a\n" for ref in refs}


def _stage_genuine_workout_document(tmp_path: Path, data_root: Path) -> Path:
    """Build a genuine strength workout document, not yet computed by the load
    pass, and copy its archived source into ``data_root``'s ``fit-archive/``.

    Strength is unsupported by every registered calculator, so the load
    pass's compute path always has *something* to
    write the first time it reaches this document (the honest "unsupported"
    state) -- guaranteeing a real write attempt if the symlink were ever
    followed, not merely a read. Uses the ``sync()`` engine function directly
    (not the CLI) so the staged document is captured *before* any load pass
    has touched it.

    Returns the path to the staged document's text, written outside the data
    root (``tmp_path / "outside.md"``) -- not yet linked from anywhere.
    """
    prep_source = tmp_path / "prep-src"
    prep_root = tmp_path / "prep-data"
    prep_root.mkdir()
    _put(prep_source, "strength.fit", builder.strength_fit_bytes())
    _engine_sync(prep_source, prep_root, athlete=None, tz=UTC, tiles=_DummyTiles())

    prep_docs = sorted(
        path
        for path in (prep_root / "workouts").glob("*.md")
        if path.name != DECLARATION_FILENAME
    )
    assert len(prep_docs) == 1
    genuine_text = prep_docs[0].read_text(encoding="utf-8")

    prep_archives = list((prep_root / "fit-archive").glob("*.fit"))
    assert len(prep_archives) == 1
    archive_dir = data_root / "fit-archive"
    archive_dir.mkdir(parents=True, exist_ok=True)
    (archive_dir / prep_archives[0].name).write_bytes(prep_archives[0].read_bytes())

    outside = tmp_path / "outside.md"
    outside.write_text(genuine_text, encoding="utf-8")
    return outside


def test_sync_does_not_follow_a_workouts_symlink_and_warns(tmp_path: Path) -> None:
    """A ``workouts/*.md`` symlink pointing at a genuine, rewritable workout
    document outside the data root survives a real ``fitdocs sync`` run -- and
    its automatic training-load pass -- byte- and mtime-identical (still a
    symlink to that same file), no duplicate document is created for it, and
    the run reports why it was skipped (Req 7.5, 7.6)."""
    source = tmp_path / "src"
    data_root = tmp_path / "data"
    data_root.mkdir()
    _put(source, "run.fit", builder.run_fit_bytes())

    workouts = data_root / "workouts"
    workouts.mkdir(parents=True)
    outside = _stage_genuine_workout_document(tmp_path, data_root)
    stray = workouts / "not-a-real-doc.md"
    stray.symlink_to(outside)
    before_mtime = outside.stat().st_mtime_ns
    before_text = outside.read_text(encoding="utf-8")

    result = runner.invoke(app, ["sync", str(source), "--out", str(data_root)])

    assert result.exit_code == 0
    # The symlink itself, and the file it points at, are completely untouched
    # -- by the document rewrite AND by the training-load pass that runs
    # immediately afterward over every workouts/*.md document.
    assert stray.is_symlink()
    assert stray.resolve() == outside.resolve()
    assert outside.read_text(encoding="utf-8") == before_text
    assert outside.stat().st_mtime_ns == before_mtime
    # Exactly one real document was produced -- the genuine incoming run -- no
    # duplicate was written for the symlinked path.
    docs = _docs(data_root)
    assert docs == sorted([stray.name, next(n for n in docs if _RUN_SLUG in n)])
    assert len([n for n in docs if _RUN_SLUG in n]) == 1
    # The run reports why the symlink was skipped.
    assert "symlink" in result.output
    assert stray.name in result.output


def test_regen_does_not_follow_a_workouts_symlink_and_warns(tmp_path: Path) -> None:
    """The same guarantee holds for ``fitdocs regen``: the symlinked path and its
    genuine outside target are untouched by regen's document rewrite and its
    following training-load pass, and the run reports why it was skipped
    (Req 7.5, 7.6).

    This scenario also stages the symlinked document's archived source under
    the real data root's ``fit-archive/`` (see
    ``_stage_genuine_workout_document``) so the load pass would have
    something to resolve if it were ever allowed through the symlink. That
    same archive, being referenced by no *readable* document, is also
    unreferenced from regeneration's point of view, so regen renders it fresh
    as a second, separate document -- the accepted archive-orphan duplicate a
    symlink refusal causes (wiki-contract task 7.2 Implementation Note,
    task 7.2 F2), not a bug this test polices. What this test polices is that
    the symlink and its target are never written through.
    """
    source = tmp_path / "src"
    data_root = tmp_path / "data"
    data_root.mkdir()
    _put(source, "run.fit", builder.run_fit_bytes())
    synced = runner.invoke(app, ["sync", str(source), "--out", str(data_root)])
    assert synced.exit_code == 0
    before_docs = set(_docs(data_root))

    workouts = data_root / "workouts"
    outside = _stage_genuine_workout_document(tmp_path, data_root)
    stray = workouts / "not-a-real-doc.md"
    stray.symlink_to(outside)
    before_mtime = outside.stat().st_mtime_ns
    before_text = outside.read_text(encoding="utf-8")

    result = runner.invoke(app, ["regen", "--out", str(data_root)])

    assert result.exit_code == 0
    assert stray.is_symlink()
    assert stray.resolve() == outside.resolve()
    assert outside.read_text(encoding="utf-8") == before_text
    assert outside.stat().st_mtime_ns == before_mtime
    # Every document that existed before is still exactly there, plus the
    # stray symlink itself -- no pre-existing document was lost or touched.
    assert before_docs | {stray.name} <= set(_docs(data_root))
    assert "symlink" in result.output
    assert stray.name in result.output


def test_a_symlinked_declaration_is_never_warned_about_as_a_workout_document(
    tmp_path: Path,
) -> None:
    """Req 3.7: the ownership declaration is never treated as a workout document
    in any document scan -- including the symlink scan.

    A symlinked ``workouts/AGENTS.md`` is already reported by the declaration
    refresh as a *foreign* declaration, which is the true and useful finding.
    The symlink scan must not also emit its workout-document warning about it,
    because that warning asserts a re-export/archive consequence which is false
    of a declaration file. This is the sixth ``*.md`` tree-walk in the package
    and the first added since task 4.2 made ``AGENTS.md`` appear in every owned
    directory; task 4.2's Implementation Note requires each new one to re-audit
    for exactly this.
    """
    source = tmp_path / "src"
    data_root = tmp_path / "data"
    data_root.mkdir()
    _put(source, "run.fit", builder.run_fit_bytes())
    first = runner.invoke(app, ["sync", str(source), "--out", str(data_root)])
    assert first.exit_code == 0

    # Replace the placed declaration with a symlink to a file outside the root.
    outside = tmp_path / "outside-agents.md"
    outside.write_text("not a fitdocs file\n", encoding="utf-8")
    declaration = data_root / "workouts" / DECLARATION_FILENAME
    declaration.unlink()
    declaration.symlink_to(outside)

    result = runner.invoke(app, ["sync", str(source), "--out", str(data_root)])

    assert result.exit_code == 0
    assert declaration.is_symlink()
    # The declaration refresh reports it (foreign, not written by fitdocs)...
    assert DECLARATION_FILENAME in result.output
    # ...but the workout-document consequence must NOT be asserted about it.
    assert "re-export of that activity" not in result.output


# --- plugin-api wiring: discovery runs before the engine (task 3.1) ---------
#
# ``sync``/``regen`` load the plugin settings and run discovery once, after the
# data root is resolved and before any engine call (Req 1.2). A malformed
# ``[plugins]`` table is a loud config error (exit 2, nothing written) exactly
# like a malformed ``[tiles]`` table (Req 2.7); a plugin load error is printed
# after the existing summaries but never changes the exit code (Req 3.5, 3.6).

_BROKEN_PLUGIN_SOURCE = "raise RuntimeError('simulated local plugin import failure')\n"


def test_malformed_plugins_settings_exits_two_before_any_write(tmp_path: Path) -> None:
    """A malformed ``[plugins]`` table is a loud config error: exit 2, nothing
    written (Req 2.7)."""
    source = tmp_path / "src"
    data_root = tmp_path / "data"
    data_root.mkdir()
    _put(source, "run.fit", builder.run_fit_bytes())
    (data_root / "fitdocs.toml").write_text(
        "[plugins]\nenabled = 1\n", encoding="utf-8"
    )

    result = runner.invoke(app, ["sync", str(source), "--out", str(data_root)])

    assert result.exit_code == 2
    assert "fitdocs.toml" in result.output
    assert "enabled" in result.output
    assert not (data_root / "workouts").exists()
    assert not (data_root / "fit-archive").exists()


def test_sync_with_broken_local_plugin_reports_failure_and_exits_zero(
    tmp_path: Path,
) -> None:
    """A run whose only anomaly is a failed local plugin prints the failure's
    subject and detail after the summaries and still exits 0 (Req 3.5, 3.6)."""
    source = tmp_path / "src"
    data_root = tmp_path / "data"
    data_root.mkdir()
    _put(source, "run.fit", builder.run_fit_bytes())
    plugins_dir = data_root / "plugins"
    plugins_dir.mkdir()
    (plugins_dir / "broken.py").write_text(_BROKEN_PLUGIN_SOURCE, encoding="utf-8")
    (data_root / "fitdocs.toml").write_text(
        '[plugins]\npath = "plugins"\n', encoding="utf-8"
    )

    result = runner.invoke(app, ["sync", str(source), "--out", str(data_root)])

    assert result.exit_code == 0
    assert "broken.py" in result.output
    assert "simulated local plugin import failure" in result.output
    # The document was still written -- a plugin failure never blocks the run.
    assert any(_RUN_SLUG in name for name in _docs(data_root))


def test_sync_plugin_failure_does_not_mask_a_genuine_file_failure(
    tmp_path: Path,
) -> None:
    """A genuine per-file failure still exits 1 even with a plugin failure
    present -- the exit-code decision is untouched by plugin reporting (Req 3.5)."""
    source = tmp_path / "src"
    data_root = tmp_path / "data"
    data_root.mkdir()
    _put(source, "bad.fit", builder.non_fit_bytes())
    plugins_dir = data_root / "plugins"
    plugins_dir.mkdir()
    (plugins_dir / "broken.py").write_text(_BROKEN_PLUGIN_SOURCE, encoding="utf-8")
    (data_root / "fitdocs.toml").write_text(
        '[plugins]\npath = "plugins"\n', encoding="utf-8"
    )

    result = runner.invoke(app, ["sync", str(source), "--out", str(data_root)])

    assert result.exit_code == 1
    assert "bad.fit" in result.output
    assert "broken.py" in result.output
    assert "simulated local plugin import failure" in result.output


def test_sync_warns_about_a_workouts_symlink_on_a_no_op_rerun(tmp_path: Path) -> None:
    """The symlink warning is a property of the data root, not of any incoming
    file: a *second* ``fitdocs sync`` over a source directory whose contents
    are already fully archived (an ordinary steady-state re-sync, with no
    per-file processing to piggyback a warning on) still reports the
    symlinked document on that second run (wiki-contract task 7.2, R2)."""
    source = tmp_path / "src"
    data_root = tmp_path / "data"
    data_root.mkdir()
    _put(source, "run.fit", builder.run_fit_bytes())

    first = runner.invoke(app, ["sync", str(source), "--out", str(data_root)])
    assert first.exit_code == 0

    workouts = data_root / "workouts"
    outside = _stage_genuine_workout_document(tmp_path, data_root)
    stray = workouts / "not-a-real-doc.md"
    stray.symlink_to(outside)

    # The source directory's only file is already archived: this second run's
    # per-file pipeline does nothing but skip it -- yet the symlink must still
    # be reported.
    second = runner.invoke(app, ["sync", str(source), "--out", str(data_root)])

    assert second.exit_code == 0
    assert stray.is_symlink()
    assert "symlink" in second.output
    assert stray.name in second.output


# --- plugins command: presentation only (task 3.2) --------------------------
#
# ``fitdocs plugins`` lists every registered calculator (id, display name,
# version, origin, modalities) and every plugin load error, exiting 0 in every
# case that produces a listing -- including with load errors present and with
# an unresolvable data root (Req 4.1-4.8). These tests inject a crafted
# ``PluginReport`` via ``fitdocs.cli.discover`` to exercise rendering rules
# that a real clean install cannot show (a distribution origin, a ``None``
# version, a load error) -- legitimate for a PRESENTATION-ONLY task.


def test_plugins_help_documents_the_command() -> None:
    """``--help`` lists the ``plugins`` command (baseline discoverability)."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "plugins" in result.stdout


def test_plugins_lists_no_calculators_on_clean_install(tmp_path: Path) -> None:
    """A clean install lists no calculators: this spec ships none (Req 13.2),
    the listing still renders and reports no load errors (Req 4.1, 4.5).

    RETIRED here (encumbered-content-purge, task 4.4), not re-based: a
    literal identifying-token-absence assertion against ``result.output``
    that used to sit here. Req 11.7 requires a guard matching an identifying
    token literally to be re-based or retired; this one's subject is the
    withdrawn calculator, which no longer exists in any form.

    ``test_fresh_interpreter_reports_the_registry_empty``
    (``tests/load/test_packaging.py``) proves only that nothing is
    registered in ``_REGISTRY`` at ``fitdocs.load`` import time, before any
    discovery runs -- it says nothing about this command's output.
    ``plugins_command`` renders ``discover()``'s report, and ``discover()``
    has an entry-point channel (installed distributions advertising the
    ``fitdocs.load_calculators`` group) and, when a data root resolves, a
    local-file channel, independent of what was registered at import.
    Confirmed directly: with a synthetic entry point injected via
    ``discover``'s ``entry_points_fn`` parameter, a full CLI invocation of
    this command rendered a planted display name in ``result.output`` while
    ``registry.available()`` was empty immediately beforehand. So this
    deleted assertion's coverage is *not* subsumed by the fresh-import
    registry check.

    It is also not replaced by the standing forbidden-string guard (task
    4.3): that guard scans tracked file content, tracked path names, and
    built-artifact members, never a captured ``CliRunner`` output, so a
    token an installed third-party distribution's entry point supplies at
    runtime is outside every surface it scans. A token literal added
    directly to ``fitdocs/cli.py``'s own tracked source is still caught
    (confirmed directly: planting one there reds
    ``test_standing_guard_scans_tracked_content_and_path_names`` and its
    sdist/wheel siblings as the sole failures; reverting restores green) --
    but that is a narrower guarantee than what was deleted, and the real gap
    (an installed distribution's entry point, not a tracked-source literal)
    is recorded in ``docs/reference/history-rewrites.md`` Section 5."""
    data_root = tmp_path / "data"
    data_root.mkdir()

    result = runner.invoke(app, ["plugins", "--out", str(data_root)])

    assert result.exit_code == 0
    assert "fitdocs plugins" in result.output
    assert "no plugin load errors" in result.output.lower()


def test_plugins_lists_injected_distribution_plugin_with_name_and_version(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """An injected distribution-origin calculator renders its distribution
    name, entry point, and version (Req 4.1, 4.2, 4.3)."""
    data_root = tmp_path / "data"
    data_root.mkdir()
    report = PluginReport(
        calculators=(
            PluginInfo(
                calculator_id="mycalc",
                display_name="My Calculator",
                version="1.2.3",
                origin=Distribution(name="fitdocs-mycalc", entry_point="mycalc"),
                modalities=("run",),
            ),
        ),
        errors=(),
    )
    monkeypatch.setattr("fitdocs.cli.discover", lambda *a, **k: report)

    result = runner.invoke(app, ["plugins", "--out", str(data_root)])

    assert result.exit_code == 0
    assert "mycalc" in result.output
    assert "My Calculator" in result.output
    assert "1.2.3" in result.output
    assert "fitdocs-mycalc" in result.output


def test_plugins_renders_unknown_for_none_version(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A ``LocalFile``-origin calculator with ``version=None`` renders the
    literal ``unknown`` -- never blank or fabricated (Req 4.3)."""
    data_root = tmp_path / "data"
    data_root.mkdir()
    report = PluginReport(
        calculators=(
            PluginInfo(
                calculator_id="localcalc",
                display_name="Local Calculator",
                version=None,
                origin=LocalFile(path="plugins/local.py"),
                modalities=("bike",),
            ),
        ),
        errors=(),
    )
    monkeypatch.setattr("fitdocs.cli.discover", lambda *a, **k: report)

    result = runner.invoke(app, ["plugins", "--out", str(data_root)])

    assert result.exit_code == 0
    assert "localcalc" in result.output
    assert "unknown" in result.output
    assert "plugins/local.py" in result.output


def test_plugins_lists_load_errors_and_still_exits_zero(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A report with load errors still exits 0; each error's subject and
    detail are printed (Req 4.4, 4.6)."""
    data_root = tmp_path / "data"
    data_root.mkdir()
    report = PluginReport(
        calculators=(
            PluginInfo(
                calculator_id="stub-calc",
                display_name="Stub Calculator",
                version="0.1.0",
                origin=BuiltIn(),
                modalities=("run",),
            ),
        ),
        errors=(
            PluginLoadError(subject="broken.py", detail="simulated import failure"),
        ),
    )
    monkeypatch.setattr("fitdocs.cli.discover", lambda *a, **k: report)

    result = runner.invoke(app, ["plugins", "--out", str(data_root)])

    assert result.exit_code == 0
    assert "broken.py" in result.output
    assert "simulated import failure" in result.output


def test_plugins_with_unresolvable_data_root_still_lists_and_exits_zero(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An unresolvable data root still produces a listing (built-ins and
    distribution-provided calculators -- none of either ship with this spec,
    Req 13.2), states that no local plugin configuration was consulted, and
    exits 0 -- the deliberate departure from the exit-2 config-error
    treatment (Req 4.7)."""

    def _raise(*_args: object, **_kwargs: object) -> Path:
        raise DataRootError("no data root configured")

    monkeypatch.setattr("fitdocs.cli.resolve_data_root", _raise)

    result = runner.invoke(app, ["plugins"])

    assert result.exit_code == 0
    # RETIRED here (encumbered-content-purge, task 4.4), not re-based: a
    # literal identifying-token-absence assertion against ``result.output``
    # that used to sit here. See the sibling retirement note in
    # `test_plugins_lists_no_calculators_on_clean_install` above for the
    # reason and the coverage analysis -- this is the second of the two
    # CLI-output token assertions Req 11.7 requires retired.
    lowered = result.output.lower()
    assert "not consulted" in lowered or "no local" in lowered


def test_plugins_with_malformed_plugins_table_still_exits_two(tmp_path: Path) -> None:
    """A resolvable data root with a malformed ``[plugins]`` table still exits
    2 (2.7) -- the degraded 4.7 path is ONLY for an unresolvable data root."""
    data_root = tmp_path / "data"
    data_root.mkdir()
    (data_root / "fitdocs.toml").write_text(
        "[plugins]\nenabled = 1\n", encoding="utf-8"
    )

    result = runner.invoke(app, ["plugins", "--out", str(data_root)])

    assert result.exit_code == 2
    assert "fitdocs.toml" in result.output
    assert "enabled" in result.output


# --- task 4.2: the command surface stays free of load configuration ---------
#
# The configured default calculator (the ``[load]`` table's
# ``default_calculator`` key) is resolved entirely inside ``apply_load``
# (task 4.1); this module threads no argument for it and reads nothing of the
# table itself. The three tests below drive that property from the command
# line: a configured default changes which calculator each of the three
# entry points uses, an explicit ``--calculator`` flag still overrides it,
# and the module's own source holds no reference to the load-settings reader
# it would need to reintroduce a surface-level read.


class _StubCalculatorA:
    """A minimal calculator supporting Modality.RUN with no required inputs,
    so it computes unconditionally and non-interactively -- exercising only
    the CLI's wiring, not any calculator-authoring concern."""

    calculator_id = "cli-stub-a"
    display_name = "CLI Stub Calculator A"
    supported_modalities = frozenset({Modality.RUN})

    def required_athlete_fields(self) -> tuple[()]:
        return ()

    def compute(
        self,
        activity: Activity,
        metrics: DerivedMetrics,
        profile: ProfileView,
        session: InteractionSession,
        context: LoadContext,
    ) -> LoadOutcome:
        if activity.modality not in self.supported_modalities:
            return Unsupported(reason=f"stub-a does not support {activity.sport}")
        return Computed(
            result=LoadResult(
                calculator_id=self.calculator_id,
                display_name=self.display_name,
                value=1.0,
                basis="cli stub a basis",
                non_selected=(),
                flags=(),
                inputs_used=(),
                notes=(),
            )
        )


class _StubCalculatorB(_StubCalculatorA):
    """A second stub, distinct id only, so two calculators can both support
    the same activity -- the ambiguity/configured-default/explicit-override
    scenarios all need at least two."""

    calculator_id = "cli-stub-b"
    display_name = "CLI Stub Calculator B"


def _register_stub_calculators() -> Callable[[], None]:
    """Register both CLI stub calculators, returning a teardown callable.

    Not a pytest fixture: some of the tests below need the registration held
    across two or three CLI invocations within one test body, so the caller
    owns the ``try/finally`` around it directly.
    """
    load_registry.register(_StubCalculatorA())
    load_registry.register(_StubCalculatorB())

    def _teardown() -> None:
        load_registry.unregister(_StubCalculatorA.calculator_id)
        load_registry.unregister(_StubCalculatorB.calculator_id)

    return _teardown


def test_configured_default_calculator_used_on_all_three_entry_points(
    tmp_path: Path,
) -> None:
    """A configured ``[load] default_calculator`` selects a calculator among
    two supporters -- with no explicit ``--calculator`` -- on ``sync``,
    ``regen``, and the standalone ``load`` command alike (Req 8.1, 8.2, 10.4,
    14.4, 14.5). Without a configured default, two supporters would leave the
    activity an unresolved ambiguity (Req 10.2); the configured default is
    what turns each pass into a computed result naming ``cli-stub-b``
    specifically -- so this also proves the value actually reaches
    ``apply_load``, not merely that the command exits cleanly.

    The ``sync`` and ``load`` legs share one data root: ``sync`` is the very
    first pass ever run over the freshly written document, so its own
    ``[cli-stub-b]`` result cannot be a restore of anything earlier, and
    ``load --recompute`` forces its own fresh compute afterwards.

    The ``regen`` leg is deliberately built on a *second*, independent data
    root, because by the time ``regen`` would run against the first root the
    document already carries a computed result -- ``regen``'s own pass would
    then take the restore branch (7.4) and observe nothing about the
    configured default at all. So here: a first ``sync`` runs with *no*
    calculator registered, leaving the document in the honest unsupported
    state (nothing to restore); only then are the stub calculators
    registered and the default configured, and ``regen`` rebuilds the
    document from its archived source. A previously-unsupported region takes
    the *compute* branch, not restore (7.7) -- so ``regen``'s printed
    ``[cli-stub-b]`` proves the configured default reached *that* pass's own
    ``apply_load`` call."""
    teardown = _register_stub_calculators()
    try:
        source = tmp_path / "src"
        data_root = tmp_path / "data"
        data_root.mkdir()
        _put(source, "run.fit", builder.run_fit_bytes())
        (data_root / "fitdocs.toml").write_text(
            '[load]\ndefault_calculator = "cli-stub-b"\n', encoding="utf-8"
        )

        sync_result = runner.invoke(app, ["sync", str(source), "--out", str(data_root)])
        assert sync_result.exit_code == 0
        assert "[cli-stub-b]" in sync_result.output

        # Force a fresh computed result on the standalone command too, so its
        # own pass -- not merely the restore path -- exercises the default.
        load_result = runner.invoke(
            app, ["load", "--out", str(data_root), "--recompute"]
        )
        assert load_result.exit_code == 0
        assert "[cli-stub-b]" in load_result.output
    finally:
        teardown()

    # regen leg, on its own data root: no calculator registered for the first
    # sync, so the document lands honestly unsupported -- there is nothing
    # yet for a later pass to merely restore.
    regen_source = tmp_path / "regen-src"
    regen_root = tmp_path / "regen-data"
    regen_root.mkdir()
    _put(regen_source, "run.fit", builder.run_fit_bytes())

    unregistered_sync = runner.invoke(
        app, ["sync", str(regen_source), "--out", str(regen_root)]
    )
    assert unregistered_sync.exit_code == 0
    assert "Computed:" not in unregistered_sync.output

    teardown = _register_stub_calculators()
    try:
        (regen_root / "fitdocs.toml").write_text(
            '[load]\ndefault_calculator = "cli-stub-b"\n', encoding="utf-8"
        )

        regen_result = runner.invoke(app, ["regen", "--out", str(regen_root)])
        assert regen_result.exit_code == 0
        assert "[cli-stub-b]" in regen_result.output
    finally:
        teardown()


def test_calculator_flag_overrides_configured_default(tmp_path: Path) -> None:
    """The explicit ``--calculator`` flag remains the sole command-line
    override and keeps precedence over a configured default (Req 8.4, 10.3):
    with the default configured as ``cli-stub-b``, ``--calculator
    cli-stub-a`` still selects ``cli-stub-a``."""
    teardown = _register_stub_calculators()
    try:
        source = tmp_path / "src"
        data_root = tmp_path / "data"
        data_root.mkdir()
        _put(source, "run.fit", builder.run_fit_bytes())
        (data_root / "fitdocs.toml").write_text(
            '[load]\ndefault_calculator = "cli-stub-b"\n', encoding="utf-8"
        )
        synced = runner.invoke(app, ["sync", str(source), "--out", str(data_root)])
        assert synced.exit_code == 0

        result = runner.invoke(
            app,
            [
                "load",
                "--out",
                str(data_root),
                "--calculator",
                "cli-stub-a",
                "--recompute",
            ],
        )

        assert result.exit_code == 0
        assert "[cli-stub-a]" in result.output
        assert "[cli-stub-b]" not in result.output
    finally:
        teardown()


def test_cli_module_holds_no_load_settings_type_or_reader() -> None:
    """The command surface performs no read of the ``[load]`` table and holds
    no load-settings type (task 4.2's load-bearing property): the reader
    module -- however it is imported: a direct name, the settings submodule
    (``from fitdocs.load import settings``), the ``fitdocs.load`` package
    itself (``from fitdocs import load``, which exposes ``.settings...`` by
    attribute chaining once the submodule is imported anywhere in the
    process), or a bare ``import fitdocs.load.settings`` -- its settings
    type, and any read of the ``[load]`` table resolve nowhere in ``cli.py``'s
    own source. The table read is covered two ways, not just by the literal
    ``default_calculator`` key: any AST subscript or ``.get(...)`` call
    keyed by the literal table name ``"load"`` is also forbidden, so a
    sibling spec adding an unrelated ``[load.*]`` key is covered too.

    Structural rather than behavioral, because the property under test is an
    *absence*. :func:`test_load_command_calls_load_load_settings_exactly_once`
    is this test's behavioral companion, pinning the same obligation from the
    call-count side -- together they cover both a statically-visible import
    and a call routed through a name this AST walk cannot resolve (e.g. one
    built via ``getattr`` or ``importlib``).

    Proven to discriminate by hand against the reviewer's exact probe: adding
    ``from fitdocs.load import settings as load_settings`` at module scope in
    ``cli.py`` plus, inside ``load_command`` before ``_build_session``, a
    guarded call to ``load_settings.load_load_settings(...)`` reddens this
    test (the forbidden submodule import) *and*
    ``test_load_command_calls_load_load_settings_exactly_once`` (a second
    read observed in one invocation) -- the rest of the suite, including
    ``test_malformed_load_table_exits_two_and_writes_nothing``, stays green:
    that test only asserts the final exit code and message content, both of
    which are identical whether the ``LoadSettingsError`` is raised by the
    probed call or by ``apply_load``'s own read, so it cannot distinguish an
    extra read from none. Measured directly rather than assumed: full-suite
    run under the probe is ``2 failed, 1813 passed`` -- these two tests,
    exactly.
    """
    source = inspect.getsource(cli_module)
    assert "default_calculator" not in source

    tree = ast.parse(source)
    forbidden_symbol_names = {
        "LoadSettings",
        "load_load_settings",
        "DEFAULT_LOAD_SETTINGS",
        "LoadSettingsError",
    }
    violations: list[str] = []

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module == "fitdocs.load.settings":
                violations.append("from fitdocs.load.settings import ...")
            if module == "fitdocs.load":
                for alias in node.names:
                    if alias.name == "settings":
                        violations.append("from fitdocs.load import settings")
            if module == "fitdocs":
                for alias in node.names:
                    if alias.name == "load":
                        violations.append("from fitdocs import load")
            for alias in node.names:
                bound = alias.asname or alias.name
                if bound in forbidden_symbol_names:
                    violations.append(f"imports {bound!r}")
        elif isinstance(node, ast.Import):
            for alias in node.names:
                dotted = alias.name
                if dotted == "fitdocs.load.settings" or dotted.startswith(
                    "fitdocs.load.settings."
                ):
                    violations.append(f"import {dotted}")
                bound = alias.asname or dotted
                if bound in forbidden_symbol_names:
                    violations.append(f"imports {bound!r}")
        elif isinstance(node, ast.Attribute):
            if node.attr in forbidden_symbol_names:
                violations.append(f"references .{node.attr}")
        elif isinstance(node, ast.Subscript):
            index = node.slice
            if isinstance(index, ast.Constant) and index.value == "load":
                violations.append('subscripts the "load" table key')
        elif isinstance(node, ast.Call):
            func = node.func
            if (
                isinstance(func, ast.Attribute)
                and func.attr == "get"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and node.args[0].value == "load"
            ):
                violations.append('.get()s the "load" table key')

    assert not violations, violations


def test_load_command_calls_load_load_settings_exactly_once(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Behavioral companion to the structural absence test above: across one
    ``fitdocs load`` invocation, ``load_load_settings`` is called exactly
    once -- the single read inside ``apply_load`` itself (task 4.1).

    **Perimeter, stated precisely.** This spies exactly two hand-picked binding
    surfaces -- ``fitdocs.load.settings`` (which a ``module.attr(...)`` call
    resolves dynamically at call time) and the name bound into
    ``fitdocs.load.engine`` at its own import time. That closes every spelling
    routed through *those two modules*, on the ``fitdocs load`` path only.

    It is **not** the perimeter this docstring used to claim. It said "both
    binding surfaces a Python import can produce"; there is one binding surface
    per importing module, not two, so a real second read added to a third module
    is invisible here. Measured: a module-level
    ``from fitdocs.load.settings import load_load_settings as _r2`` in
    ``src/fitdocs/load/arbitrate.py`` plus a call in ``validate_configured`` --
    a genuine second read on the ``fitdocs load`` path -- left this whole module
    green at 36 passed.

    Req 14.1's "anywhere in the tool" is covered instead by
    ``tests/load/test_settings.py``'s
    ``test_load_load_settings_is_called_the_documented_number_of_times_per_command``,
    which sweeps every imported ``fitdocs.*`` module rather than naming two.
    **That sweep is not redundant with this test.** It is the only guard on the
    package-wide clause; this one is a per-command companion. Do not delete it
    on the strength of this test's existence.
    """
    source = tmp_path / "src"
    data_root = tmp_path / "data"
    data_root.mkdir()
    _put(source, "run.fit", builder.run_fit_bytes())
    synced = runner.invoke(app, ["sync", str(source), "--out", str(data_root)])
    assert synced.exit_code == 0

    calls: list[object] = []
    original = load_settings_module.load_load_settings

    def _spy(document: object, settings_file: object) -> object:
        calls.append(document)
        return original(document, settings_file)  # type: ignore[arg-type]

    monkeypatch.setattr(load_settings_module, "load_load_settings", _spy)
    monkeypatch.setattr(load_engine_module, "load_load_settings", _spy)

    result = runner.invoke(app, ["load", "--out", str(data_root)])

    assert result.exit_code == 0
    assert len(calls) == 1


def test_apply_load_call_sites_pass_no_default_calculator_argument() -> None:
    """The three ``apply_load`` invocation sites -- after sync writes
    documents, after a prompt-free regeneration, and on the standalone load
    command -- drop the configured-default argument along with the pass's
    deleted parameter (task 4.2's first obligation).

    ``cli.py`` funnels every one of them through the single shared
    ``_run_load_pass`` helper, which is what actually calls ``apply_load``;
    reads ``cli.py``'s own AST for every ``_run_load_pass(...)`` call
    (expecting one inside each of ``sync_command``, ``regen_command``, and
    ``load_command``, with ``sync_command`` calling it on both its
    explicit-source and inbox-drain branches) and for the sole ``apply_load``
    call, and checks the latter's keyword set against ``apply_load``'s real
    signature -- so a call site passing an unsupported keyword (e.g. a
    resurrected ``default_calculator=``) is caught by inspecting the source
    directly, without needing to execute any of the three commands."""
    signature_params = set(inspect.signature(apply_load).parameters) - {"data_root"}
    source = inspect.getsource(cli_module)
    tree = ast.parse(source)

    def _calls_named(name: str) -> list[ast.Call]:
        return [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == name
        ]

    apply_load_calls = _calls_named("apply_load")
    assert len(apply_load_calls) == 1
    keywords = {kw.arg for kw in apply_load_calls[0].keywords if kw.arg is not None}
    assert keywords <= signature_params
    assert not any("default" in name for name in keywords)

    command_functions = {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef)
        and node.name in {"sync_command", "regen_command", "load_command"}
    }
    assert set(command_functions) == {"sync_command", "regen_command", "load_command"}
    run_pass_calls_by_command = {
        name: [
            call
            for call in ast.walk(func)
            if isinstance(call, ast.Call)
            and isinstance(call.func, ast.Name)
            and call.func.id == "_run_load_pass"
        ]
        for name, func in command_functions.items()
    }
    # sync_command calls it on both the explicit-source and inbox-drain
    # branches; regen_command and load_command call it exactly once each.
    assert len(run_pass_calls_by_command["sync_command"]) == 2
    assert len(run_pass_calls_by_command["regen_command"]) == 1
    assert len(run_pass_calls_by_command["load_command"]) == 1
