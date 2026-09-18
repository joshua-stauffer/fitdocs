"""The ``fitdocs`` command-line entry point.

A thin typer shell (design: CliApp, ``src/fitdocs/cli.py``): it parses flags,
resolves configuration, calls the engine, and reports -- it contains no
rendering or file-pipeline logic of its own. Nine commands are registered on
top of the baseline ``--version`` / ``--help`` shell. The tree-processing
commands documented here are:

* ``fitdocs sync SOURCE [--out PATH] [--force] [--no-prompt]`` -- turn every
  ``.fit`` file under SOURCE into a workout document under the data root,
  then run the training-load pass over those documents, then the plan
  reconciling pass (Req 8.1, plan-resolution Req 8.1).
* ``fitdocs regen [--out PATH]`` -- rebuild every document from the data root's
  archived sources alone, then run the load pass prompt-free so previously
  computed load is restored without user interaction, then the plan
  reconciling pass (Req 7.4, plan-resolution Req 8.1).
* ``fitdocs load [--out PATH] [--recompute] [--calculator ID] [--no-prompt]`` --
  run the load pass standalone over the data root's workout documents, filling
  those that lack results (Req 8.2).
* ``fitdocs check [--out PATH]`` -- read-only: report every place the data
  root diverges from the installed contract (an out-of-date or damaged
  document, an unmanaged frontmatter key, a malformed effort tag, a
  missing/stale/foreign ownership declaration) without creating, modifying,
  or deleting anything (Req 8.1).
* ``fitdocs plan [--out PATH]`` -- render every plan source under the
  plan-source directory into its block page and planned pages, reporting
  rendered, unchanged, invalid, blocked and failed per source, then run the
  plan reconciling pass over the same sources -- resolving every planned row
  against the workout corpus and printing the reconciliation (training-blocks
  Req 8.2, 8.3, 8.6, 8.9; plan-resolution Req 4.3, 8.1). Standalone: this
  command is never chained onto ``sync``, ``regen``, ``load``, ``history`` or
  ``check``, and none of those commands change because it exists (Req 8.8).

Two further commands describe the installed tool rather than a tree and sit
outside the list above: ``fitdocs plugins`` and ``fitdocs skill [NAME]`` --
list every packaged agent skill and its installed directory, or (given
``NAME``) print one skill's directory and a copy recipe (Req 1.3, 1.4, 1.5,
1.6, 1.7, 7.2, 7.5).

Every tree-processing command (each command in the list above), *before any
processing* (Req 2.1), resolves the data root by the explicit precedence
(``--out`` > ``FITDOCS_DATA`` > ``.fitdocs/data-root`` pointer). ``sync`` and
``regen`` additionally load the optional athlete inputs
and thread the *system local* timezone explicitly into the engine so document
dates read in the user's own zone. ``sync``/``regen`` end with a summary of
documents written, skipped, and failed (Req 1.4); the load pass adds its own
summary of documents computed, restored, unsupported, skipped (with reasons),
and failed (Req 8.6).

The load pass is interactive only on a real terminal with prompting enabled:
the CLI decides interactivity (a TTY check plus ``--no-prompt``) and builds the
session, so :class:`~fitdocs.load.prompts.RichInteractionSession` never probes
the environment (Req 3.5). ``regen`` is always non-interactive, which makes its
load pass restore-only and deterministic.

Exit codes (Req 1.5, 2.2, 8.5, 8.7):

* ``0`` -- success, including an all-skipped no-op run (everything written
  and/or skipped, nothing failed), a ``check`` run that reports nothing, or a
  ``plan`` run with no plan sources present;
* ``1`` -- one or more per-file *or* per-document (load) failures occurred,
  ``check`` reports one or more findings, ``plan`` finds an invalid, blocked,
  or failed block, or the plan reconciling pass -- chained after ``sync``'s
  and ``regen``'s load pass, and run standalone by ``plan`` -- finds an
  override problem (plan-resolution Req 8.7);
* ``2`` -- a configuration error: an unresolvable data root (its message lists
  the three configuration options), a malformed ``athlete.toml`` / profile, a
  malformed ``fitdocs.toml`` ``[tiles]``, ``[load]``, ``[history]`` or
  ``[plans]`` table (the reconciling pass reads ``[history]`` and ``[load]``
  before it ever calls the plan engine, plan-resolution Req 8.7), an unknown
  ``--calculator``/configured-default id, or a missing source directory --
  including a configured plan-source directory that does not exist or is not
  a directory -- or (``skill``) an unknown or absent packaged skill name. The
  ``[load]`` table is read inside the load pass itself (task 4.1); this
  module reads none of it directly. A configuration error writes nothing,
  and for ``check`` means nothing was
  scanned either.

Data-root posture (stated here because ``check`` is the first new command to
exercise it): *a command that describes a tree requires a data root; a
command that describes the installed tool does not.* ``check`` describes a
tree, so an unresolvable data root is a hard configuration error for it (exit
``2``), not a degraded success -- see ``check_command``'s own docstring.
``skill`` is the second such instance, beside ``plugins``: it describes the
installed tool, resolves nothing, and cannot fail for want of a data root.

Third-party calculator discovery (plugin-api): ``sync``, ``regen``, and
``load`` each load the ``[plugins]`` settings and run discovery exactly once
per invocation, after the data root is resolved and before any engine call, so
a plugin-provided calculator can be selected by id (including via ``load``'s
``--calculator`` option) and an unknown id's error message lists plugin ids
alongside the built-in ones. A malformed ``[plugins]`` table is a configuration
error exactly like a malformed ``[tiles]`` table (an instructive message and
exit ``2``, before anything is written). Plugin load errors, in contrast, are
warnings, never failures: they are printed after the run's existing summaries
and never change the exit code.

Network access is confined to :mod:`fitdocs.tiles`: the only network the tool
performs is fetching missing basemap tiles during ``sync``/``regen`` map
rendering, and only while tile requests are enabled (Req 4.2). Every other
operation -- and the entire ``load`` command -- stays fully offline; a warm tile
cache makes even map rendering network-free.

Requirements 1.3, 1.4, 1.5, 2.1, 3.5, 8.1, 8.2, 8.3, 8.4, 8.6, 14.1, 14.2, 14.4.
"""

from __future__ import annotations

import os
import sys
from datetime import date, datetime, tzinfo
from pathlib import Path
from typing import NoReturn

import typer
from rich.console import Console
from rich.table import Table

from fitdocs import AthleteInputs
from fitdocs.agentskill import PACKAGED_SKILLS, skill_root
from fitdocs.athlete import AthleteFileError, load_athlete_inputs
from fitdocs.audit import AuditReport, audit
from fitdocs.benchmarks import BenchmarkKind
from fitdocs.config import DataRootError, resolve_data_root
from fitdocs.history.engine import HistoryReport, run_history
from fitdocs.inbox import (
    InboxNote,
    InboxPaths,
    InboxSettings,
    create_inbox_paths,
    load_inbox_settings,
    validate_inbox_paths,
)
from fitdocs.layout import block_doc_path, settings_path
from fitdocs.load.engine import DocLoadEntry, LoadReport, apply_load
from fitdocs.load.profile import ProfileError
from fitdocs.load.prompts import NonInteractiveSession, RichInteractionSession
from fitdocs.load.registry import UnknownCalculatorError
from fitdocs.load.types import InteractionSession
from fitdocs.performance.engine import DeriveReport, derive_benchmarks
from fitdocs.plans import (
    BlockStatus,
    PlanReport,
    ReconcileReport,
    RowState,
    actual_load_sentence,
    run_reconcile,
)
from fitdocs.plugins import (
    DEFAULT_PLUGIN_SETTINGS,
    BuiltIn,
    Distribution,
    LocalFile,
    PluginInfo,
    PluginReport,
    discover,
    load_plugin_settings,
)
from fitdocs.quarantine import QuarantineError, QuarantineRecord, load_quarantine
from fitdocs.settings import SettingsError, load_settings_document
from fitdocs.sync import DrainReport, SyncReport, drain, regen, sync
from fitdocs.tiles import TileStore, load_tile_settings, tile_settings_from_document
from fitdocs.version import UNKNOWN_VERSION, version_display

_EXIT_SUCCESS: int = 0
"""Everything written and/or skipped; no failures (an all-skipped run, too)."""
_EXIT_FILE_FAILURES: int = 1
"""One or more per-file failures occurred during the run (Req 1.5)."""
_EXIT_CONFIG_ERROR: int = 2
"""A configuration error prevented the run: nothing was written (Req 2.2)."""

app = typer.Typer(
    name="fitdocs",
    help="Turn .fit files into rich markdown workout documents.",
    add_completion=False,
    no_args_is_help=True,
)


def _print_version(value: bool) -> None:
    """Print the installed package version and exit (eager ``--version``).

    Reads :func:`fitdocs.version.version_display`, which never raises: from
    an uninstalled source tree this prints the unknown token and exits 0
    rather than propagating ``PackageNotFoundError`` (Req 2.4).
    """
    if value:
        typer.echo(version_display())
        raise typer.Exit


@app.callback()
def main(
    _version: bool = typer.Option(
        False,
        "--version",
        help="Show the installed fitdocs version and exit.",
        callback=_print_version,
        is_eager=True,
    ),
) -> None:
    """fitdocs: a .fit -> markdown personal knowledge manager for fitness."""


# typer parameter declarations, defined at module scope so the ``typer.Option`` /
# ``typer.Argument`` calls do not sit inside an argument default (flake8-bugbear
# B008); the command functions read these singletons as their defaults.
_SOURCE_ARGUMENT = typer.Argument(
    None,
    help=(
        "Directory of .fit files to ingest (searched recursively). Omit to "
        "drain the configured inbox instead -- the inbox table's path key in "
        "<data-root>/fitdocs.toml, defaulting to inbox/ under the data root."
    ),
)
_OUT_OPTION = typer.Option(
    None,
    "--out",
    help="Output data root; overrides FITDOCS_DATA and any pointer file.",
)
_FORCE_OPTION = typer.Option(
    False,
    "--force",
    help="Re-render already-archived files (never rewrites the archive).",
)
_RECOMPUTE_OPTION = typer.Option(
    False,
    "--recompute",
    help="Recompute already-computed load, re-confirming zone and structure.",
)
_CALCULATOR_OPTION = typer.Option(
    None,
    "--calculator",
    help="Use only the calculator with this id.",
)
_NO_PROMPT_OPTION = typer.Option(
    False,
    "--no-prompt",
    help="Never prompt during the load pass; leave affected documents uncomputed.",
)
_DRY_RUN_OPTION = typer.Option(
    False,
    "--dry-run",
    help="Print the identical report but write nothing to the profile.",
)
_RETRY_QUARANTINED_OPTION = typer.Option(
    False,
    "--retry-quarantined",
    help=(
        "Inbox drains only: re-attempt files already recorded in the "
        "quarantine record. A configuration error when combined with SOURCE."
    ),
)
_METHODOLOGY_OPTION = typer.Option(
    None,
    "--methodology",
    help="Sum the history page's curve under only this methodology id.",
)


@app.command("sync")
def sync_command(
    source: Path | None = _SOURCE_ARGUMENT,
    out: Path | None = _OUT_OPTION,
    force: bool = _FORCE_OPTION,
    no_prompt: bool = _NO_PROMPT_OPTION,
    retry_quarantined: bool = _RETRY_QUARANTINED_OPTION,
) -> None:
    """Ingest .fit files into the data root, then compute load, then reconcile.

    With SOURCE: ingest every .fit file under it into the data root -- today's
    exact behavior (recursive discovery, a strictly read-only source, no
    inbox settings read, and no inbox policy applied).

    Without SOURCE: drain the configured inbox instead -- the location named
    by the inbox table's path key in <data-root>/fitdocs.toml, defaulting to
    inbox/ under the data root when the file or that key is absent. The drain
    selects eligible files (ignoring hidden/junk entries), defers files still
    being written, skips known-quarantined files, processes the rest through
    the same per-file pipeline SOURCE uses, and applies the configured
    disposition -- never deleting inbox files. --retry-quarantined re-attempts
    previously quarantined inbox files and is a configuration error when
    combined with SOURCE.

    Either way, after processing the load pass runs over the data root,
    interactively unless --no-prompt is given or stdin is not a terminal, and
    --out/--force/--no-prompt keep their exact meanings on both paths. The
    plan reconciling pass then runs, chained, over the same data root
    (plan-resolution Req 8.1): its own report is printed only when it has
    something to say, and an override problem it finds folds into this
    command's exit status exactly like a per-file or load failure. Third-party
    calculator discovery runs once, before any engine call (plugin-api); a
    plugin load error is a warning, printed after the summaries -- never a
    failure, and never changes the exit code.
    """
    tz = _local_tz()
    data_root = _resolved_data_root(out)
    athlete = _loaded_athlete(data_root)

    if source is not None:
        # Explicit-source path: today's exact behavior, byte-for-byte -- no
        # inbox settings are read and no inbox policy is applied (inbox Req
        # 2.2, 7.3). --retry-quarantined is inbox-only (inbox Req 5.5).
        if retry_quarantined:
            _config_error(
                "--retry-quarantined applies only to an inbox drain "
                "(omit SOURCE to drain the inbox)."
            )
        if not source.is_dir():
            _config_error(
                f"The source path does not exist or is not a directory: {source}"
            )
        # Discover plugins once, before any engine call (a malformed [plugins] table
        # exits 2 here, before any write).
        plugin_report = _plugin_report(data_root)
        # Build the tile store once (a malformed [tiles] table exits 2 here, before any
        # write); pass it to the engine as the always-supplied basemap-tile source.
        tiles = _tile_store(data_root)
        report = sync(
            source, data_root, athlete=athlete, tz=tz, tiles=tiles, force=force
        )
        _report(report, command="sync")
        # The load pass runs after writing documents (Req 8.1), honoring --no-prompt.
        load_report = _run_load_pass(
            data_root, session=_build_session(no_prompt=no_prompt)
        )
        # The plan reconciling pass runs after the load pass, chained
        # (plan-resolution Req 8.1, 8.2, 8.5).
        plan_report = _run_plan_pass(data_root, today=_today(), chained=True)
        _report_plugin_errors(plugin_report)
        # A per-file OR a per-document (load) OR a reconciling-pass failure
        # makes the run exit 1 (8.5, plan-resolution Req 8.7).
        _finish(
            failed=bool(report.failures)
            or bool(load_report.failures)
            or plan_report.failed
        )
        return

    # No SOURCE: drain the configured inbox (inbox Req 2.1).
    # Discover plugins once, before any engine call (a malformed [plugins] table
    # exits 2 here, before any write) -- same position as the explicit-source
    # path (cross-spec landing order: plugin-api's edit lands first).
    plugin_report = _plugin_report(data_root)
    inbox_settings, inbox_paths, quarantine, tiles = _inbox_preflight(data_root)
    drain_report = drain(
        inbox_paths.inbox,
        data_root,
        settings=inbox_settings,
        processed_dir=inbox_paths.processed,
        quarantine=quarantine,
        athlete=athlete,
        tz=tz,
        tiles=tiles,
        force=force,
        retry_quarantined=retry_quarantined,
    )
    _report_drain(drain_report, command="sync")
    # The load pass runs after the drain (Req 2.1), honoring --no-prompt exactly
    # as the explicit-source path does (Req 2.5).
    load_report = _run_load_pass(data_root, session=_build_session(no_prompt=no_prompt))
    # The plan reconciling pass runs after the load pass, chained
    # (plan-resolution Req 8.1, 8.2, 8.5), same as the explicit-source path.
    plan_report = _run_plan_pass(data_root, today=_today(), chained=True)
    _report_plugin_errors(plugin_report)
    # Per-file failures, load failures and a reconciling-pass failure drive
    # the failure outcome -- deferrals, known-quarantined files, and failed
    # moves never do (inbox Req 4.6, 5.3, 6.5, 7.2; plan-resolution Req 8.7).
    _finish(
        failed=bool(drain_report.sync.failures)
        or bool(load_report.failures)
        or plan_report.failed
    )


def _inbox_preflight(
    data_root: Path,
) -> tuple[InboxSettings, InboxPaths, QuarantineRecord, TileStore]:
    """Run the inbox drain pre-flight, in order, entirely before any engine call
    (design: CliInboxWiring, inbox Req 1.4, 1.6, 1.7, 5.6, 7.2).

    Parses the settings document once with the shared reader, projects the
    ``[inbox]`` table, resolves and *validates* the inbox (and, under the
    move disposition, the processed-files destination) without writing
    anything, loads the quarantine record, and builds the tile store from
    that *same* parsed document -- so within this helper a file-level
    settings fault (an unreadable or invalid ``fitdocs.toml``) is read once
    and would be reported once as the shared
    :class:`~fitdocs.settings.SettingsError`, not once per table reader
    (inbox Req 1.7). In practice, on the drain path this helper runs *after*
    :func:`_plugin_report`, which already reads and projects the settings
    document for the ``[plugins]`` table; a file-level fault is therefore
    already caught and reported there, and this helper's own ``except
    SettingsError`` is reachable only for a table-level fault --
    :class:`~fitdocs.inbox.InboxSettingsError` or
    :class:`~fitdocs.tiles.TileSettingsError`, which both subclass it. Every
    typed error this helper can raise or catch -- those two, plus
    :class:`~fitdocs.quarantine.QuarantineError` for a malformed quarantine
    record -- routes through :func:`_config_error`: an instructive stderr
    message and exit 2. Every check that can fail runs before the inbox (and,
    under the move disposition, the processed-files destination) is created,
    so a configuration error -- including a malformed quarantine record --
    writes nothing (inbox Req 1.4, 1.6, 5.6, 7.2).
    """
    try:
        document = load_settings_document(data_root)
        inbox_settings = load_inbox_settings(document, data_root=data_root)
        validated_inbox_paths = validate_inbox_paths(data_root, inbox_settings)
        quarantine = load_quarantine(data_root)
        tile_settings = tile_settings_from_document(document, settings_path(data_root))
        inbox_paths = create_inbox_paths(validated_inbox_paths)
    except SettingsError as exc:
        _config_error(str(exc))
    except QuarantineError as exc:
        _config_error(str(exc))
    return inbox_settings, inbox_paths, quarantine, TileStore(data_root, tile_settings)


@app.command("regen")
def regen_command(
    out: Path | None = _OUT_OPTION,
) -> None:
    """Rebuild every workout document from the data root's archived sources.

    Regeneration resets frontmatter to generated values; a following prompt-free
    load pass restores previously computed load from the preserved region, then
    the plan reconciling pass runs, chained, over the same data root
    (plan-resolution Req 8.1). Third-party calculator discovery runs once,
    before any engine call (plugin-api); a plugin load error is a warning,
    printed after the summaries -- never a failure, and never changes the exit
    code.
    """
    tz = _local_tz()
    data_root = _resolved_data_root(out)
    athlete = _loaded_athlete(data_root)
    # Discover plugins once, before any engine call (a malformed [plugins] table
    # exits 2 here, before any write).
    plugin_report = _plugin_report(data_root)
    # Build the tile store once (a malformed [tiles] table exits 2 here, before any
    # write); pass it to the engine as the always-supplied basemap-tile source.
    tiles = _tile_store(data_root)
    report = regen(data_root, athlete=athlete, tz=tz, tiles=tiles)
    _report(report, command="regen")
    # regen is always non-interactive, which makes its load pass restore-only:
    # computed load is re-derived from the preserved payload, no prompting (7.4).
    load_report = _run_load_pass(data_root, session=NonInteractiveSession())
    # The plan reconciling pass runs after the load pass, chained
    # (plan-resolution Req 8.1, 8.2, 8.5).
    plan_report = _run_plan_pass(data_root, today=_today(), chained=True)
    _report_plugin_errors(plugin_report)
    _finish(
        failed=bool(report.failures) or bool(load_report.failures) or plan_report.failed
    )


@app.command("load")
def load_command(
    out: Path | None = _OUT_OPTION,
    recompute: bool = _RECOMPUTE_OPTION,
    calculator: str | None = _CALCULATOR_OPTION,
    no_prompt: bool = _NO_PROMPT_OPTION,
) -> None:
    """Run the training-load pass over the data root's workout documents.

    Fills documents that lack results without re-syncing. Use --recompute to
    re-confirm and replace existing results, --calculator to force one
    methodology, and --no-prompt to never prompt (leaving docs uncomputed).
    Third-party calculator discovery runs once, before this pass (plugin-api),
    so --calculator can name a plugin-provided id; a plugin load error is a
    warning, printed after the summary -- never a failure, and never changes
    the exit code.
    """
    # Standalone load pass (Req 8.2): resolve the root, build the session
    # (interactive only on a TTY with prompting enabled, Req 3.5), then run.
    data_root = _resolved_data_root(out)
    # Discover plugins once, before the engine call, so a plugin-provided
    # --calculator id resolves and an unknown id's error lists plugin ids too.
    plugin_report = _plugin_report(data_root)
    session = _build_session(no_prompt=no_prompt)
    load_report = _run_load_pass(
        data_root, session=session, calculator_id=calculator, recompute=recompute
    )
    _report_plugin_errors(plugin_report)
    # Any per-document failure exits 1; all-skipped/all-restored is success (8.6).
    _finish(failed=bool(load_report.failures))


@app.command("check")
def check_command(
    out: Path | None = _OUT_OPTION,
) -> None:
    """Report every place the data root diverges from the installed contract.

    Read-only (Req 8.1): ``check`` creates, modifies, and deletes nothing. It
    never builds a tile store, never loads the athlete profile, and never runs
    the load pass -- unlike sync/regen/load it describes what is already on
    disk instead of writing to it.

    Data-root posture: *a command that describes a tree requires a data root;
    a command that describes the installed tool does not.* ``check`` reports
    on a data root's contents, so an unresolvable data root is a hard
    configuration error here -- an instructive stderr message and exit 2,
    with nothing scanned -- rather than a degraded success (Req 8.7). (The
    sibling distribution spec's compatibility document carries this rule's
    project-wide statement; it is not restated for its commands.)
    """
    # The data root is resolved -- and can fail with exit 2 -- before audit()
    # is ever called, so an unresolvable data root scans nothing (Req 8.7).
    data_root = _resolved_data_root(out)
    report = audit(data_root)
    _report_audit(report)
    # Any finding exits 1, exactly like a per-file or per-document failure;
    # nothing found is success (Req 8.7).
    _finish(failed=bool(report.findings))


@app.command("history")
def history_command(
    out: Path | None = _OUT_OPTION,
    methodology: str | None = _METHODOLOGY_OPTION,
) -> None:
    """Regenerate the one longitudinal fitness/fatigue/form history page.

    Rebuilds the history document and its chart from the data root's
    documents as they currently stand (Req 8.1) -- there is no --force and
    no --recompute, because the page is always rebuilt in full. --methodology
    sums the curve under only that id, overriding the configured default and
    the archive's own single-methodology inference (Req 4.2). Distinct from
    -- and never chained onto -- sync, regen or load (Req 8.7): this is the
    only place in the module that calls the history engine.
    """
    data_root = _resolved_data_root(out)
    try:
        history_report = run_history(data_root, methodology=methodology)
    except SettingsError as exc:
        # Covers a malformed [history]/[load] settings table
        # (HistorySettingsError/LoadSettingsError) and an unresolved
        # methodology (MethodologyConfigurationError) alike -- both are
        # SettingsError subclasses, so no new branch is needed (Req 8.4).
        _config_error(str(exc))
    _report_history(history_report)
    # Suppressed weeks, excluded pages and skipped documents never fail the
    # run on their own; only a write failure does (Req 8.8).
    _finish(failed=bool(history_report.failures))


@app.command("plan")
def plan_command(
    out: Path | None = _OUT_OPTION,
) -> None:
    """Render every plan source into its block page and planned pages, then
    reconcile every current row against the workout corpus.

    Rebuilds every block from whatever the plan-source directory currently
    holds (Req 8.1) -- there is no --force and no --dry-run, because the
    pages are always rebuilt and an unchanged block is detected by byte
    comparison alone (Req 8.5). Standalone (Req 8.8): this command is never
    chained onto sync, regen, load, history or check, and none of those
    commands change because this command exists. After rendering, the plan
    reconciling pass resolves every current row of every valid block against
    the workout corpus and prints its own report in full -- unlike the
    chained call sites, this command's own report is never suppressed
    (plan-resolution Req 4.3, 8.6). A malformed ``[plans]``, ``[history]`` or
    ``[load]`` settings table, or a configured plan-source directory that
    does not exist or is not a directory, is a configuration error exactly
    like every other malformed table this module reads (Req 8.3,
    plan-resolution Req 8.3).
    """
    data_root = _resolved_data_root(out)
    report = _run_plan_pass(data_root, today=_today(), chained=False)
    # Any invalid, blocked or failed block, or a reconciled block carrying an
    # override problem, exits 1; a run with no plan sources -- or none
    # configured at all -- is success (Req 8.9, plan-resolution Req 8.7).
    _finish(failed=report.failed)


@app.command("plugins")
def plugins_command(
    out: Path | None = _OUT_OPTION,
) -> None:
    """List every registered calculator and every plugin load error.

    Describes the installed tool, not a specific tree: with a resolvable data
    root, the standard settings/discovery path runs (a malformed [plugins]
    table is still a loud configuration error -- exit 2, Req 2.7). When the
    data root cannot be resolved, this command deliberately departs from every
    other command's exit-2 treatment (Req 4.7) -- it still lists the built-in
    and distribution-provided calculators (the entry-point channel needs no
    data root), states that no local plugin configuration was consulted (the
    local channel is skipped because there is no data root to resolve a path
    against), and exits 0, so the command remains usable as a diagnostic
    outside a configured vault. Read-only: performs no network access and
    writes nothing to the data root (Req 4.8).
    """
    data_root: Path | None
    try:
        data_root = resolve_data_root(out, env=os.environ, start_dir=Path.cwd())
    except DataRootError:
        # Unlike every other command, an unresolvable data root here is the
        # degraded listing path (Req 4.7), not a configuration error.
        data_root = None

    if data_root is not None:
        report = _plugin_report(data_root)
    else:
        report = discover(None, DEFAULT_PLUGIN_SETTINGS)

    _report_plugins(report, data_root_resolved=data_root is not None)
    # Exits 0 whenever a listing was produced -- including with load errors
    # present (Req 4.6); no call to _finish() here.


@app.command("derive-benchmarks")
def derive_benchmarks_command(
    out: Path | None = _OUT_OPTION,
    dry_run: bool = _DRY_RUN_OPTION,
) -> None:
    """Turn tagged efforts into dated athlete-profile benchmarks.

    Resolves the data root by the usual precedence (Req 9.6), runs the
    benchmark-derivation pass (:func:`fitdocs.performance.engine.
    derive_benchmarks`) over every generated workout document, and prints the
    report: a summary line, the derived entries, the declines grouped by
    document, the failures, and the per-quantity summaries (Req 7.1-7.3,
    7.8). ``--dry-run`` produces the identical report but writes nothing (Req
    1.1, 1.9). Exits ``2`` on a configuration fault (an unresolvable data
    root, a malformed profile, or a malformed ``[load]`` table -- the pass
    reads the same stream-sufficiency settings the load pass does), ``1``
    when any document failed, and ``0`` otherwise -- a decline is an outcome,
    never a failure, so a run that only derived and declined still exits
    ``0`` (Req 1.9, 1.10).
    """
    data_root = _resolved_data_root(out)
    try:
        report = derive_benchmarks(data_root, dry_run=dry_run)
    except (ProfileError, SettingsError) as exc:
        _config_error(str(exc))
    _report_derive(report, dry_run=dry_run)
    # A decline is a successful outcome (Req 7.8); only a failure exits 1.
    _finish(failed=bool(report.failures))


@app.command("skill")
def skill_command(
    name: str | None = typer.Argument(
        None, help="A packaged skill's name; omit to list every packaged skill."
    ),
) -> None:
    """List every packaged agent skill, or print one's directory and copy recipe.

    Describes the installed tool, not a data root (Req 1.7): resolves no data
    root, reads no settings, loads no profile, builds no tile store, runs no
    engine, and writes nothing.

    No argument: one line per registered skill -- its name and installed
    directory, or "(not present in this installation)" -- in registry order
    (Req 1.3). If any packaged skill is absent, that is a configuration error
    (exit 2, Req 1.6); otherwise exit 0.

    With ``NAME``: an unregistered name is a configuration error naming it and
    listing the packaged names (exit 2, Req 1.5); a registered name whose
    directory is absent is a configuration error naming it as packaged but not
    present (exit 2, Req 1.6); a present skill prints its absolute directory
    followed by a one-line ``cp -R`` recipe, and exits 0 (Req 1.4).
    """
    if name is None:
        absent = _report_skill_listing()
        if absent:
            _config_error(
                "packaged skill(s) not present in this installation: "
                + ", ".join(absent)
                + " -- the installation is incomplete."
            )
        return

    if name not in PACKAGED_SKILLS:
        _config_error(
            f"unknown skill {name!r}; packaged skills: " + ", ".join(PACKAGED_SKILLS)
        )

    root = skill_root(name)
    if root is None:
        _config_error(
            f"skill {name!r} is packaged with fitdocs but not present in this "
            "installation -- the install is incomplete; reinstall fitdocs."
        )

    console = Console()
    console.print(str(root), markup=False, highlight=False, soft_wrap=True)
    console.print(
        f"Copy it into your agent's skills directory: cp -R {root} <skills-dir>/{name}",
        markup=False,
        highlight=False,
        soft_wrap=True,
    )


def _report_skill_listing() -> tuple[str, ...]:
    """Print one line per :data:`PACKAGED_SKILLS` entry; return the absent names.

    ``f"{name}  {root}"`` for a present skill, ``f"{name}  (not present in
    this installation)"`` for an absent one, in registry order.
    """
    console = Console()
    absent: list[str] = []
    for skill_name in PACKAGED_SKILLS:
        root = skill_root(skill_name)
        if root is None:
            absent.append(skill_name)
            console.print(
                f"{skill_name}  (not present in this installation)",
                markup=False,
                highlight=False,
                soft_wrap=True,
            )
        else:
            console.print(
                f"{skill_name}  {root}", markup=False, highlight=False, soft_wrap=True
            )
    return tuple(absent)


def _report_plugins(report: PluginReport, *, data_root_resolved: bool) -> None:
    """Print the ``plugins`` listing table plus the load-error block (4.1-4.5).

    The table carries one row per registered calculator: id, display name,
    version (the literal ``unknown`` when :attr:`PluginInfo.version` is
    ``None`` -- never fabricated, Req 4.3), origin (``built-in``, ``<dist>
    <entry point>``, or ``local: <path>``, Req 4.2), and its sorted
    modalities joined into a readable string. When ``data_root_resolved`` is
    ``False`` an explicit line states that no local plugin configuration was
    consulted (Req 4.7). The load-error block lists each error's subject and
    detail, or an explicit "no plugin load errors" line when there are none
    (Req 4.4, 4.5).
    """
    console = Console()
    if not data_root_resolved:
        console.print(
            "No data root resolved: listing installed calculators only -- "
            "no local plugin configuration was consulted.",
            markup=False,
            highlight=False,
            soft_wrap=True,
        )

    table = Table(title="fitdocs plugins")
    table.add_column("Id")
    table.add_column("Display name")
    table.add_column("Version")
    table.add_column("Origin")
    table.add_column("Modalities")
    for calculator in report.calculators:
        table.add_row(
            calculator.calculator_id,
            calculator.display_name,
            calculator.version if calculator.version is not None else UNKNOWN_VERSION,
            _origin_text(calculator),
            ", ".join(calculator.modalities),
        )
    console.print(table)

    if not report.errors:
        console.print("No plugin load errors.")
        return
    console.print("Plugin errors:")
    for error in report.errors:
        console.print(
            f"  {error.subject}", markup=False, highlight=False, soft_wrap=True
        )
        console.print(
            f"    {error.detail}", markup=False, highlight=False, soft_wrap=True
        )


def _origin_text(calculator: PluginInfo) -> str:
    """Render a calculator's origin for the ``plugins`` table (Req 4.2)."""
    origin = calculator.origin
    if isinstance(origin, BuiltIn):
        return "built-in"
    if isinstance(origin, Distribution):
        return f"{origin.name} {origin.entry_point}"
    if isinstance(origin, LocalFile):
        return f"local: {origin.path}"
    raise AssertionError(f"unreachable origin variant: {origin!r}")  # pragma: no cover


def _build_session(*, no_prompt: bool) -> InteractionSession:
    """Build the load-pass interaction session; the CLI decides interactivity.

    A :class:`~fitdocs.load.prompts.RichInteractionSession` is used only when
    prompting is enabled *and* stdin is a real terminal; otherwise a
    :class:`~fitdocs.load.prompts.NonInteractiveSession` is returned so the pass
    never blocks and never fabricates consent (Req 3.5). The session itself
    never probes the environment -- this factory is the single decision point.
    """
    if no_prompt or not sys.stdin.isatty():
        return NonInteractiveSession()
    return RichInteractionSession()


def _run_load_pass(
    data_root: Path,
    *,
    session: InteractionSession,
    calculator_id: str | None = None,
    recompute: bool = False,
) -> LoadReport:
    """Run the load pass, print its summary, and return the report (Req 8.6).

    A configuration error raised by the engine (a malformed ``athlete.toml`` or
    profile, an unknown ``--calculator``/configured-default id, or a malformed
    ``[load]`` table) is classified exactly like ``fitdocs sync`` -- an
    instructive message to stderr and exit ``2`` -- via :func:`_config_error`;
    per-document failures are collected in the returned report instead (they
    drive the exit code at the call site). The ``[load]`` table is read
    *inside* :func:`~fitdocs.load.engine.apply_load` (task 4.1), not here --
    this module holds no load-settings type and performs no read of that
    table itself (task 4.2). Its error, :class:`~fitdocs.load.settings.
    LoadSettingsError`, needs no dedicated ``except`` clause: it subclasses
    the shared :class:`~fitdocs.settings.SettingsError` this function already
    maps to the same exit status for every other settings-table fault.
    """
    try:
        report = apply_load(
            data_root,
            session=session,
            calculator_id=calculator_id,
            recompute=recompute,
        )
    except (
        ProfileError,
        AthleteFileError,
        UnknownCalculatorError,
        SettingsError,
    ) as exc:
        _config_error(str(exc))
    _report_load(report)
    return report


def _run_plan_pass(data_root: Path, *, today: date, chained: bool) -> ReconcileReport:
    """Run the plan reconciling pass, print its report, and return it
    (plan-resolution Req 4.3, 8.1, 8.2, 8.5, 8.6, 8.7).

    A configuration error raised by :func:`~fitdocs.plans.run_reconcile` (a
    malformed ``[plans]``, ``[history]`` or ``[load]`` table, or a configured
    plan-source directory that does not exist or is not a directory) is
    classified exactly like every other settings fault this module reads --
    an instructive message to stderr and exit ``2`` -- via
    :func:`_config_error`; every one of those errors is a
    :class:`~fitdocs.settings.SettingsError` subclass, so one ``except``
    clause covers them all.

    The wave-1 plan report (:func:`_report_plan`) prints in full when
    ``chained`` is ``False`` -- including the absent-directory note wave 1
    pins -- and is suppressed only when ``chained`` is ``True`` *and* the
    plan report has no block, no unsourced path and no foreign declaration:
    a chained run over an unconfigured or empty plan-source directory stays
    silent about it, but a chained run that actually found something to
    report still prints it. The reconciliation report
    (:func:`_report_reconcile`) always prints, chained or not.
    """
    try:
        report = run_reconcile(data_root, today=today)
    except SettingsError as exc:
        _config_error(str(exc))
    plan = report.plan
    quiet = (
        chained
        and not plan.blocks
        and not plan.unsourced
        and not plan.declarations_foreign
    )
    if not quiet:
        _report_plan(plan, data_root=data_root)
    _report_reconcile(report)
    return report


def _local_tz() -> tzinfo:
    """The system local timezone, threaded explicitly into the engine (Req 5.x).

    ``datetime.now().astimezone()`` attaches the local zone to a naive now, so
    its ``tzinfo`` is always populated; the assertion documents that invariant
    for the type checker rather than guarding a reachable branch.
    """
    local = datetime.now().astimezone().tzinfo
    assert local is not None  # astimezone() always attaches the local tzinfo
    return local


def _today() -> date:
    """The local calendar date, for the plan reconciling pass (Req 5.5).

    Deliberately ``date.today()`` and not ``datetime.now(_local_tz()).date()``:
    ``date.today()`` reads the clock through the Python-level ``time.time`` and
    honours ``TZ``/``tzset``, which is exactly what the fake-date context
    manager the end-to-end tests reuse (``tests/test_history_e2e.py:211-245``)
    hooks; ``datetime.now()`` reads the C clock and is invisible to it, so the
    end-to-end tests could never move ``today`` if this read the clock that
    way instead. This is the only clock read this feature makes; no guard
    forbids a clock read in this module.
    """
    return date.today()  # deliberately date.today(), not datetime.now(...) -- see above


def _resolved_data_root(out: Path | None) -> Path:
    """Resolve the data root by the explicit precedence, or fail loudly (Req 2.1).

    A :class:`DataRootError` -- an unresolvable or non-directory data root --
    becomes a configuration error (exit ``2``) whose message already lists the
    three configuration options (Req 2.2).
    """
    try:
        return resolve_data_root(out, env=os.environ, start_dir=Path.cwd())
    except DataRootError as exc:
        _config_error(str(exc))


def _loaded_athlete(data_root: Path) -> AthleteInputs | None:
    """Load the optional athlete inputs, or fail loudly on a bad file (Req 8.3).

    An absent ``athlete.toml`` yields ``None``; a malformed one raises
    :class:`AthleteFileError`, which becomes a configuration error (exit ``2``).
    """
    try:
        return load_athlete_inputs(data_root)
    except AthleteFileError as exc:
        _config_error(str(exc))


def _tile_store(data_root: Path) -> TileStore:
    """Build the basemap-tile store from the data root's settings (Req 4.2, 5.1).

    Reads ``<data_root>/fitdocs.toml`` ``[tiles]`` via
    :func:`~fitdocs.tiles.load_tile_settings`. A malformed ``[tiles]`` table raises
    :class:`~fitdocs.tiles.TileSettingsError` and a file-level fault (unreadable,
    invalid TOML) raises the shared :class:`~fitdocs.settings.SettingsError` it
    subclasses; either becomes a configuration error (an instructive stderr message
    and exit ``2``) exactly like a bad ``athlete.toml``. Since the settings load
    precedes the engine call, a malformed table exits before anything is written.
    Otherwise returns a
    :class:`~fitdocs.tiles.TileStore` bound to the data root and settings --
    constructed once per command and passed to the engine as its always-supplied
    tile source. Nothing is written; the settings file is read-only to fitdocs.
    """
    try:
        settings = load_tile_settings(data_root)
    except SettingsError as exc:
        _config_error(str(exc))
    return TileStore(data_root, settings)


def _plugin_report(data_root: Path) -> PluginReport:
    """Load the ``[plugins]`` settings and run discovery once (Req 1.2, 2.7).

    Mirrors :func:`_tile_store`: the shared settings document is read, then the
    ``[plugins]`` table is projected via
    :func:`~fitdocs.plugins.load_plugin_settings`. Because
    :class:`~fitdocs.plugins.PluginSettingsError` subclasses the shared
    :class:`~fitdocs.settings.SettingsError`, a single ``except SettingsError``
    catches both a file-level fault (unreadable, invalid TOML) and a malformed
    ``[plugins]`` table -- either becomes a configuration error (an instructive
    stderr message and exit ``2``) via :func:`_config_error`, before anything is
    written. Otherwise runs :func:`~fitdocs.plugins.discover`, which registers
    every third-party calculator and isolates each plugin's own failure into
    the returned report's ``errors`` rather than raising -- a plugin load error
    is a warning, never a failure (Req 3.5, 3.6), reported later by
    :func:`_report_plugin_errors`.
    """
    try:
        document = load_settings_document(data_root)
        settings = load_plugin_settings(document, settings_path(data_root))
    except SettingsError as exc:
        _config_error(str(exc))
    return discover(data_root, settings)


def _report_plugin_errors(report: PluginReport) -> None:
    """Print every plugin load error's subject and detail (Req 3.5, 3.6).

    Printed after the run's existing end-of-run summaries and never affects
    the exit code -- a plugin load error is a warning, never a failure. When
    there are no errors, nothing is printed here (a standing "no errors" line
    belongs to the ``plugins`` listing command, not to this reporter).
    """
    if not report.errors:
        return
    console = Console()
    console.print("Plugin errors:")
    for error in report.errors:
        console.print(
            f"  {error.subject}", markup=False, highlight=False, soft_wrap=True
        )
        console.print(
            f"    {error.detail}", markup=False, highlight=False, soft_wrap=True
        )


def _config_error(message: str) -> NoReturn:
    """Print an instructive configuration error to stderr and exit ``2`` (Req 2.2).

    Nothing has been written at any call site (data-root resolution, athlete
    loading, and the source-directory check all precede every engine call), so a
    configuration error leaves the data root untouched.
    """
    Console(stderr=True).print(message, markup=False, highlight=False)
    raise typer.Exit(code=_EXIT_CONFIG_ERROR)


def _report(report: SyncReport, *, command: str) -> None:
    """Print the end-of-run summary: a counts table plus the per-file detail (1.4).

    The rich table carries the written / skipped / failed / warnings counts; the
    written documents, every failure (its source and reason), and every
    :class:`~fitdocs.sync.DocWarning` (the document it names and its detail) are
    listed beneath it -- see :attr:`~fitdocs.sync.SyncReport.warnings` for the
    causes that can appear there rather than re-enumerating them here, since that
    list grows independently of this presentation layer. Warnings are a separate,
    additive channel: they are reported but never alter the exit code (Req 4.4).
    Detail lines are printed with
    ``soft_wrap`` so long paths and reasons are never truncated, and with markup
    disabled so bracketed reason text is shown verbatim.
    """
    console = Console()
    table = Table(title=f"fitdocs {command}")
    table.add_column("Result")
    table.add_column("Count", justify="right")
    table.add_row("Written", str(len(report.written)))
    table.add_row("Skipped", str(len(report.skipped)))
    table.add_row("Failed", str(len(report.failures)))
    table.add_row("Warnings", str(len(report.warnings)))
    console.print(table)

    if report.written:
        console.print("Written:")
        for ref in report.written:
            console.print(f"  {ref}", markup=False, highlight=False, soft_wrap=True)
    if report.failures:
        console.print("Failed:")
        for failure in report.failures:
            console.print(
                f"  {failure.source}", markup=False, highlight=False, soft_wrap=True
            )
            console.print(
                f"    {failure.reason}", markup=False, highlight=False, soft_wrap=True
            )
    if report.warnings:
        console.print("Warnings:")
        for warning in report.warnings:
            console.print(
                f"  {warning.doc}", markup=False, highlight=False, soft_wrap=True
            )
            console.print(
                f"    {warning.detail}", markup=False, highlight=False, soft_wrap=True
            )


def _report_drain(report: DrainReport, *, command: str) -> None:
    """Print the drain summary: the inbox path, an extended counts table, and
    per-file detail, without disturbing :func:`_report` (inbox Req 2.3, 7.1, 7.3).

    Prints the inbox path being drained, then the existing written / skipped /
    failed / warnings counts table extended with four distinctly named rows --
    Deferred, Quarantined, Moved, and Move failures -- so all eight channels a
    drain can report (written, skipped, failures, warnings, deferred,
    quarantined, moved, move_failures) are each individually nameable.
    ``Move failures`` is never folded into ``Failed`` (a failed move does not
    fail the run) or into ``Moved`` (the file never moved). All eight rows
    render unconditionally, including when a channel is empty, so downstream
    documentation and the packaged agent skill can always find each channel by
    name in the table shape. Beneath the table: the existing Written/Failed/
    Warnings detail listings (unchanged, printed only when non-empty, exactly
    as :func:`_report` prints them), then per-file detail with reasons for
    deferred entries, quarantined entries, and failed moves, and finally the
    list of moved destinations. Detail lines use ``soft_wrap`` with markup
    disabled, matching :func:`_report`, so long paths/reasons are never
    truncated and bracketed text is never reinterpreted as markup.
    """
    console = Console()
    console.print(f"Inbox: {report.inbox}", markup=False, highlight=False)

    sync = report.sync
    table = Table(title=f"fitdocs {command}")
    table.add_column("Result")
    table.add_column("Count", justify="right")
    table.add_row("Written", str(len(sync.written)))
    table.add_row("Skipped", str(len(sync.skipped)))
    table.add_row("Failed", str(len(sync.failures)))
    table.add_row("Warnings", str(len(sync.warnings)))
    table.add_row("Deferred", str(len(report.deferred)))
    table.add_row("Quarantined", str(len(report.quarantined)))
    table.add_row("Moved", str(len(report.moved)))
    table.add_row("Move failures", str(len(report.move_failures)))
    console.print(table)

    if sync.written:
        console.print("Written:")
        for ref in sync.written:
            console.print(f"  {ref}", markup=False, highlight=False, soft_wrap=True)
    if sync.failures:
        console.print("Failed:")
        for failure in sync.failures:
            console.print(
                f"  {failure.source}", markup=False, highlight=False, soft_wrap=True
            )
            console.print(
                f"    {failure.reason}", markup=False, highlight=False, soft_wrap=True
            )
    if sync.warnings:
        console.print("Warnings:")
        for warning in sync.warnings:
            console.print(
                f"  {warning.doc}", markup=False, highlight=False, soft_wrap=True
            )
            console.print(
                f"    {warning.detail}", markup=False, highlight=False, soft_wrap=True
            )

    def _notes(label: str, notes: tuple[InboxNote, ...]) -> None:
        if not notes:
            return
        console.print(f"{label}:")
        for note in notes:
            console.print(
                f"  {note.subject}", markup=False, highlight=False, soft_wrap=True
            )
            console.print(
                f"    {note.detail}", markup=False, highlight=False, soft_wrap=True
            )

    _notes("Deferred", report.deferred)
    _notes("Quarantined", report.quarantined)
    _notes("Move failures", report.move_failures)

    if report.moved:
        console.print("Moved:")
        for destination in report.moved:
            console.print(
                f"  {destination}", markup=False, highlight=False, soft_wrap=True
            )


def _report_load(report: LoadReport) -> None:
    """Print the load-pass summary: a counts table plus per-document detail (8.6).

    The rich table carries the computed / restored / unsupported / skipped /
    failed counts; beneath it, the computed documents are listed with the
    calculator that scored them, and the skipped and failed documents are listed
    with their reasons so the user sees *why* each was not computed. Detail lines
    use ``soft_wrap`` so long paths and reasons are never truncated, and disable
    markup so bracketed reason/id text is shown verbatim.
    """
    console = Console()
    table = Table(title="fitdocs load")
    table.add_column("Result")
    table.add_column("Count", justify="right")
    table.add_row("Computed", str(len(report.computed)))
    table.add_row("Restored", str(len(report.restored)))
    table.add_row("Unsupported", str(len(report.unsupported)))
    table.add_row("Skipped", str(len(report.skipped)))
    table.add_row("Failed", str(len(report.failures)))
    console.print(table)

    if report.computed:
        console.print("Computed:")
        for entry in report.computed:
            console.print(
                f"  {entry.doc} [{entry.detail}]",
                markup=False,
                highlight=False,
                soft_wrap=True,
            )
    _print_detail(console, "Skipped", report.skipped)
    _print_detail(console, "Failed", report.failures)


def _print_detail(
    console: Console, heading: str, entries: tuple[DocLoadEntry, ...]
) -> None:
    """List each ``entries`` document and its reason under ``heading`` (if any)."""
    if not entries:
        return
    console.print(f"{heading}:")
    for entry in entries:
        console.print(f"  {entry.doc}", markup=False, highlight=False, soft_wrap=True)
        console.print(
            f"    {entry.detail}", markup=False, highlight=False, soft_wrap=True
        )


_QUANTITY_UNITS: dict[BenchmarkKind, str] = {
    BenchmarkKind.FTP_WATTS: "W",
    BenchmarkKind.LTHR_BPM: "bpm",
    BenchmarkKind.THRESHOLD_PACE_S_PER_KM: "s/km",
}


def _report_derive(report: DeriveReport, *, dry_run: bool) -> None:
    """Print the derivation-pass report: a summary line, the derived
    entries, the declines grouped by document, the failures, and the
    per-quantity summaries (design: DeriveCommand; Req 7.1-7.3, 7.7, 7.8).

    ``--dry-run``'s leading line states that nothing was written (Req 1.9),
    printed before anything else so it cannot be missed even if the rest of
    the report is redirected or truncated. Every printed reason, path and
    detail uses ``markup=False`` so a bracketed reason (e.g. an insufficiency
    detail) or path is shown literally, matching the escaping idiom
    ``tests/test_cli_drain_report.py`` already pins for ``_report_drain``.
    """
    console = Console()
    if dry_run:
        console.print(
            "Dry run: nothing was written to the profile.",
            markup=False,
            highlight=False,
        )

    table = Table(title="fitdocs derive-benchmarks")
    table.add_column("Result")
    table.add_column("Count", justify="right")
    table.add_row("Considered", str(report.considered))
    table.add_row("Tagged", str(report.tagged))
    table.add_row("Derived", str(len(report.derived)))
    table.add_row("Declined", str(len(report.declined)))
    table.add_row("Failed", str(len(report.failures)))
    console.print(table)
    console.print(
        f"Profile written: {'yes' if report.written else 'no'}",
        markup=False,
        highlight=False,
    )

    if report.derived:
        console.print("Derived:")
        for benchmark in report.derived:
            unit = _QUANTITY_UNITS.get(benchmark.kind, "")
            console.print(
                f"  {benchmark.kind.value} ({benchmark.discipline.value}): "
                f"{benchmark.value:g}{(' ' + unit) if unit else ''} on "
                f"{benchmark.measured_on.isoformat()} via {benchmark.method.value}"
                f" [{benchmark.document}]",
                markup=False,
                highlight=False,
                soft_wrap=True,
            )

    declined_entries = [entry for entry in report.entries if entry.declined]
    if declined_entries:
        console.print("Declined:")
        for entry in declined_entries:
            console.print(
                f"  {entry.document}", markup=False, highlight=False, soft_wrap=True
            )
            for outcome in entry.declined:
                console.print(
                    f"    {outcome.kind.value}: {outcome.reason.value} -- "
                    f"{outcome.detail}",
                    markup=False,
                    highlight=False,
                    soft_wrap=True,
                )
                if outcome.observed is not None or outcome.required is not None:
                    console.print(
                        f"      observed={outcome.observed!r} "
                        f"required={outcome.required!r}",
                        markup=False,
                        highlight=False,
                        soft_wrap=True,
                    )

    if report.failures:
        console.print("Failed:")
        for failure in report.failures:
            console.print(
                f"  {failure.document}", markup=False, highlight=False, soft_wrap=True
            )
            console.print(
                f"    {failure.reason}", markup=False, highlight=False, soft_wrap=True
            )

    if report.summaries:
        console.print("Quantity summaries:")
        for summary in report.summaries:
            reason_text = (
                summary.dominant_reason.value
                if summary.dominant_reason is not None
                else "never attempted"
            )
            console.print(
                f"  {summary.kind.value}: {reason_text}",
                markup=False,
                highlight=False,
                soft_wrap=True,
            )


def _report_audit(report: AuditReport) -> None:
    """Print the ``check`` summary: a counts table plus the per-finding detail.

    The rich table carries the inspected-document and findings counts; when
    there are no findings a single "no findings" line is printed instead of a
    detail listing (a clean tree, Req 8.6). Otherwise each finding is listed
    under its own subject with the observed detail and the remedy beneath it,
    in the same ``markup=False, soft_wrap=True`` style as :func:`_print_detail`
    and :func:`_report` so long paths and remedy text are never truncated or
    hard-wrapped.
    """
    console = Console()
    table = Table(title="fitdocs check")
    table.add_column("Result")
    table.add_column("Count", justify="right")
    table.add_row("Documents inspected", str(report.documents))
    table.add_row("Findings", str(len(report.findings)))
    console.print(table)

    if not report.findings:
        console.print(
            "No findings: every inspected document and declaration matches "
            "the installed contract."
        )
        return

    console.print("Findings:")
    for finding in report.findings:
        console.print(
            f"  {finding.subject}", markup=False, highlight=False, soft_wrap=True
        )
        console.print(
            f"    {finding.detail}", markup=False, highlight=False, soft_wrap=True
        )
        console.print(
            f"    {finding.remedy}", markup=False, highlight=False, soft_wrap=True
        )


def _report_history(report: HistoryReport) -> None:
    """Print the ``history`` run report (Req 8.6): the two written paths (or
    ``None`` when not written), a counts table, each excluded methodology
    with its own page count, every foreign path left alone, every skipped
    document with its reason, every write failure with its reason, and the
    empty-archive note when the run set one.

    Detail lines use ``soft_wrap`` with markup disabled, matching every other
    reporter in this module, so long paths and reasons are never truncated
    or reinterpreted as markup.
    """
    console = Console()
    console.print(
        f"Document: {report.document or '(not written)'}",
        markup=False,
        highlight=False,
        soft_wrap=True,
    )
    console.print(
        f"Chart: {report.chart or '(not written)'}",
        markup=False,
        highlight=False,
        soft_wrap=True,
    )

    table = Table(title="fitdocs history")
    table.add_column("Result")
    table.add_column("Count", justify="right")
    table.add_row("Pages read", str(report.pages_read))
    table.add_row("Contributing", str(report.pages_contributing))
    table.add_row("Without a load", str(report.pages_without_load))
    table.add_row("Out of span", str(report.pages_out_of_span))
    table.add_row("Suppressed weeks", str(report.suppressed_weeks))
    table.add_row("Criterion points", str(report.criterion_points))
    table.add_row("Methodology", report.methodology or "(none)")
    console.print(table)

    if report.pages_excluded:
        console.print("Excluded methodologies:")
        for name, count in report.pages_excluded:
            console.print(
                f"  {name}: {count}", markup=False, highlight=False, soft_wrap=True
            )

    if report.foreign:
        console.print("Foreign (left untouched):")
        for path in report.foreign:
            console.print(f"  {path}", markup=False, highlight=False, soft_wrap=True)

    if report.skipped:
        console.print("Skipped:")
        for skip in report.skipped:
            console.print(
                f"  {skip.path}", markup=False, highlight=False, soft_wrap=True
            )
            console.print(
                f"    {skip.reason}", markup=False, highlight=False, soft_wrap=True
            )

    if report.failures:
        console.print("Failed:")
        for path, reason in report.failures:
            console.print(f"  {path}", markup=False, highlight=False, soft_wrap=True)
            console.print(
                f"    {reason}", markup=False, highlight=False, soft_wrap=True
            )

    if report.note is not None:
        console.print(report.note, markup=False, highlight=False, soft_wrap=True)


def _report_plan(report: PlanReport, *, data_root: Path) -> None:
    """Print the ``plan`` run report (Req 8.6): the source directory, one
    line per block in its outcome's shape, every unsourced path, every
    declaration that could not be placed, and the note.

    Detail lines use ``soft_wrap`` with markup disabled -- the style most
    detail lines in this module already use -- so long paths, reasons and
    problem descriptions are never truncated or reinterpreted as markup
    (not every *summary* line in the module carries ``soft_wrap`` too --
    e.g. ``_report_drain``'s leading ``Inbox:`` line does not -- so the
    claim here is scoped to this function's own detail lines, not the
    module at large).

    The printed block-page path is derived independently of
    :attr:`~fitdocs.plans.engine.BlockOutcome.written`
    (:func:`~fitdocs.layout.block_doc_path`, made data-root-relative) rather
    than read off the end of that tuple: the block page is *not* rewritten
    -- and so does not appear in ``written`` -- on a run where only a
    planned page's bytes changed. Concretely: editing an *original* row's
    prescription in place, with no ``[[amendment.update]]`` recording the
    change, leaves the block page's bytes unchanged, because neither the
    current-plan day table nor the "as first written" table ever prints a
    row's prescription text -- only an amendment's own change bullets do
    (``block_page.py``'s ``_row_changed_bullets``). The printed
    ``+n planned`` count is therefore every ``written`` entry other than
    that path, not ``len(written) - 1``.

    A rendered or unchanged block whose pages directory holds a
    non-generated file the run left alone (Req 7.9,
    :attr:`~fitdocs.plans.engine.BlockOutcome.foreign` is populated for
    those two statuses too, not only ``blocked``) prints one further
    indented line per such path so the athlete is told about it, not just
    the engine's own report object.
    """
    console = Console()
    console.print(
        f"Source: {report.source_dir}", markup=False, highlight=False, soft_wrap=True
    )

    def _print_kept_foreign(paths: tuple[str, ...]) -> None:
        for path in paths:
            console.print(
                f"  kept (not fitdocs'): {path}",
                markup=False,
                highlight=False,
                soft_wrap=True,
            )

    for outcome in report.blocks:
        block_page = block_doc_path(data_root, outcome.block_id)
        block_page_report = block_page.relative_to(data_root).as_posix()
        if outcome.status is BlockStatus.RENDERED:
            planned = sum(1 for path in outcome.written if path != block_page_report)
            console.print(
                f"rendered  {outcome.source} -> {block_page_report} "
                f"(+{planned} planned, -{len(outcome.removed)} removed)",
                markup=False,
                highlight=False,
                soft_wrap=True,
            )
            _print_kept_foreign(outcome.foreign)
        elif outcome.status is BlockStatus.UNCHANGED:
            console.print(
                f"unchanged {outcome.source}",
                markup=False,
                highlight=False,
                soft_wrap=True,
            )
            _print_kept_foreign(outcome.foreign)
        elif outcome.status is BlockStatus.INVALID:
            console.print(
                f"invalid   {outcome.source}",
                markup=False,
                highlight=False,
                soft_wrap=True,
            )
            for problem in outcome.problems:
                console.print(
                    f"  {problem.describe()}",
                    markup=False,
                    highlight=False,
                    soft_wrap=True,
                )
        elif outcome.status is BlockStatus.BLOCKED:
            for path in outcome.foreign:
                console.print(
                    f"blocked   {outcome.source}: {path}",
                    markup=False,
                    highlight=False,
                    soft_wrap=True,
                )
        else:
            assert outcome.status is BlockStatus.FAILED
            for path, reason in outcome.failures:
                console.print(
                    f"failed    {outcome.source}: {path}: {reason}",
                    markup=False,
                    highlight=False,
                    soft_wrap=True,
                )

    for path in report.unsourced:
        console.print(
            f"No source: {path}", markup=False, highlight=False, soft_wrap=True
        )

    for path in report.declarations_foreign:
        console.print(
            f"Declaration not placed (foreign): {path}",
            markup=False,
            highlight=False,
            soft_wrap=True,
        )

    if report.note is not None:
        console.print(report.note, markup=False, highlight=False, soft_wrap=True)


def _report_reconcile(report: ReconcileReport) -> None:
    """Print the reconciling pass's own report: one summary line per block,
    each block's mesocycle/ambiguous/problem detail, then the run's chosen
    methodology once (plan-resolution Req 4.3, 6.3-6.7, 8.6).

    Per block: ``reconciled <block_id>: N planned -- a matched (b
    ambiguous), c overridden, d skipped, e not logged, f upcoming; g
    unplanned`` -- the per-state list follows the block page's own
    count-line rule (zero-count states omitted, the ambiguous parenthesis
    only when there is at least one ambiguous row, and no list -- no
    ``" -- "`` at all -- when the block has no rows); ``g unplanned`` always
    prints. Beneath that: one indented ``mesocycle n: <actual_load_sentence>``
    line per mesocycle, reusing :func:`~fitdocs.plans.actual_load_sentence`'s
    own sentence verbatim; ``ambiguous: <ids>`` when the block has any; one
    indented :meth:`~fitdocs.plans.ReconcileProblem.describe` line per
    override problem. Once, after every block: ``methodology: <name>
    (<source>)`` when the run chose one, or ``methodology: none chosen --
    <detail>`` when it could not -- nothing when the resolver was never
    called at all (no valid block existed). Detail lines print with
    ``markup=False, highlight=False, soft_wrap=True``, matching every other
    detail line this module prints.
    """
    console = Console()
    for reconciliation in report.blocks:
        counts = reconciliation.counts()
        ambiguous = reconciliation.ambiguous
        segments: list[str] = []
        for state in RowState:
            n = counts[state]
            if n == 0:
                continue
            if state is RowState.MATCHED and ambiguous:
                segments.append(f"{n} {state.value} ({len(ambiguous)} ambiguous)")
            else:
                segments.append(f"{n} {state.value}")
        block_id = reconciliation.block_id
        line = f"reconciled {block_id}: {len(reconciliation.rows)} planned"
        if segments:
            line += " -- " + ", ".join(segments)
        line += f"; {reconciliation.unplanned_count} unplanned"
        console.print(line, markup=False, highlight=False, soft_wrap=True)

        for index, mesocycle in enumerate(reconciliation.mesocycles, start=1):
            console.print(
                f"  mesocycle {index}: {actual_load_sentence(mesocycle)}",
                markup=False,
                highlight=False,
                soft_wrap=True,
            )
        if ambiguous:
            console.print(
                f"  ambiguous: {', '.join(ambiguous)}",
                markup=False,
                highlight=False,
                soft_wrap=True,
            )
        for problem in reconciliation.problems:
            console.print(
                f"  {problem.describe()}", markup=False, highlight=False, soft_wrap=True
            )

    methodology = report.methodology
    if methodology is not None:
        # Distinguished by shape (via `getattr`), not by an `isinstance`
        # against `fitdocs.history.MethodologyChoice`/`MethodologyProblem`:
        # this module imports no `fitdocs.history` name beyond
        # `fitdocs.history.engine`'s own (`test_no_other_command_
        # implementation_reaches_run_history`'s module-wide import guard
        # pins that surface to exactly one node).
        source = getattr(methodology, "source", None)  # noqa: B009
        if source is not None:
            name = getattr(methodology, "methodology")  # noqa: B009
            console.print(
                f"methodology: {name} ({source})",
                markup=False,
                highlight=False,
                soft_wrap=True,
            )
        else:
            detail = getattr(methodology, "detail")  # noqa: B009
            console.print(
                f"methodology: none chosen -- {detail}",
                markup=False,
                highlight=False,
                soft_wrap=True,
            )


def _finish(*, failed: bool) -> None:
    """Exit ``1`` when any file or load document failed, else succeed with ``0``.

    An all-skipped/all-restored run has no failures and so exits ``0`` -- a no-op
    is success (Req 1.5, 8.5, 8.6).
    """
    if failed:
        raise typer.Exit(code=_EXIT_FILE_FAILURES)
