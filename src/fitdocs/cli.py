"""The ``fitdocs`` command-line entry point.

A thin typer shell (design: CliApp, ``src/fitdocs/cli.py``): it parses flags,
resolves configuration, calls the engine, and reports -- it contains no
rendering or file-pipeline logic of its own. Thirteen commands are registered
on top of the baseline ``--version`` / ``--help`` shell. The tree-processing
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
* ``fitdocs query [SQL | -] [--file PATH] [--schema] [--format table|csv|json]
[--max-rows N] [--timeout SECONDS] [--out PATH]`` -- read-only: run one SQL
statement against the analytics index in a sandbox, or describe its schema.
* ``fitdocs index [--out PATH] [--rebuild]`` -- build or refresh the disposable
  analytics index from the data root's workout pages (analytics-index Req
  10.1).

Two further commands describe the installed tool rather than a tree and sit
outside the list above: ``fitdocs plugins`` and ``fitdocs skill [NAME]`` --
list every packaged agent skill and its installed directory, or (given
``NAME``) print one skill's directory and a copy recipe (Req 1.3, 1.4, 1.5,
1.6, 1.7, 7.2, 7.5).

``fitdocs connect NAME [--out PATH]`` sits between these two shapes: it
resolves the data root to read the configured ``[connectors]`` instances
(connectors Req 3.9) but writes nothing under it -- it makes exactly one
authentication attempt against the named instance's connector and, on
acceptance, stores the credentials under the resolved per-user credentials
directory, never under the data root (connectors Req 5.1-5.9). It prompts
interactively for each field the connector declares, reading any field
marked secret through a no-echo prompt; when standard input is not an
interactive terminal it prompts for nothing and fails loudly instead
(connectors Req 5.4).

``fitdocs pull [NAMES...] [--out PATH] [--since DATE] [--dry-run] [--sync]
[--no-prompt]`` fetches new activities from the connectors configured under
``[connectors]`` -- every configured instance, in name order, or only the
named ones when NAMES is given -- and delivers each into the configured
inbox, inside a subdirectory named for its instance (connectors Req 6.1-6.13,
8.1-8.4). Every check the preflight can make -- the data root, a ``--sync``/
``--dry-run`` conflict, the ``--since`` date, the settings document, the
inbox, the connectors table, an unknown instance name, and (for a selected
instance whose connector authenticates) the credentials directory -- runs
before any request or write (Req 3.9, 4.2); with no instance configured it
reports that and completes with the success code rather than treating it as
an error (Req 6.3). ``--since DATE`` lists each instance from the start of
that day in the local time zone instead of its ledger's watermark less its
look-back (Req 6.4); ``--dry-run`` lists and reports what each instance
would fetch, fetching, delivering, removing, and recording nothing under the
data root or in the inbox -- except a token renewal the listing needed,
which is still persisted to the credentials store (Req 6.9). ``--sync`` is
declared, validated, and refused together with ``--dry-run`` here (Req
12.4); after the pull report it chains the same drain ``fitdocs sync``'s
own no-SOURCE branch runs -- the inbox drain, then the load pass, then the
plan reconciling pass, labeled ``pull`` -- via the shared
``_run_drain_passes`` helper (connectors Req 12.1-12.3), regardless of
whether the pull itself reported a failure or no connector was configured
(Req 12.2); the run exits with the failure code when the pull or the
chained drain failed (Req 12.5). The printed report and the exit codes
below follow connectors Req 11.1-11.5.

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
  and/or skipped, nothing failed), a ``check`` run that reports nothing, a
  ``plan`` run with no plan sources present, or a ``pull`` run with no
  connector configured or whose only exceptional entries are deferrals and
  skips (connectors Req 6.3, 11.4); ``query`` also exits 0 for a result or
  schema description, including a result cut at its row limit;
* ``1`` -- one or more per-file *or* per-document (load) failures occurred,
  ``check`` reports one or more findings, ``plan`` finds an invalid, blocked,
  or failed block, the plan reconciling pass -- chained after ``sync``'s
  and ``regen``'s load pass, and run standalone by ``plan`` -- finds an
  override problem (plan-resolution Req 8.7), ``pull`` reports any
  instance or activity failure (connectors Req 11.4), or (``--sync``) the
  chained drain -- the inbox drain, its load pass, or its reconciling pass --
  failed (connectors Req 12.5);
  ``query`` exits 1 when its statement is refused, fails or times out, the
  sandbox cannot be verified, or the index is unavailable or incompatible;
* ``2`` -- a configuration error: an unresolvable data root (its message lists
  the three configuration options), a malformed ``athlete.toml`` / profile, a
  malformed ``fitdocs.toml`` ``[tiles]``, ``[load]``, ``[history]`` or
  ``[plans]`` table (the reconciling pass reads ``[history]`` and ``[load]``
  before it ever calls the plan engine, plan-resolution Req 8.7), an unknown
  ``--calculator``/configured-default id, or a missing source directory --
  including a configured plan-source directory that does not exist or is not
  a directory -- or (``query``) invalid query input or data-root/index
  location, or (``skill``) an unknown or absent packaged skill name.
  ``pull`` adds its own preflight configuration errors: an unknown connector
  instance name, an invalid ``--since`` date, ``--sync`` combined with
  ``--dry-run``, and a credentials directory that is the data root or lies
  inside it (connectors Req 3.9, 4.2, 6.2, 12.4). The
  ``[load]`` table is read inside the load pass itself (task 4.1); this
  module reads none of it directly. A configuration error writes nothing,
  and for ``check`` means nothing was
  scanned either. ``fitdocs index`` exits 0 when it is current, 1 when it
  cannot be brought current, and 2 for invalid configuration. The index
  post-pass never changes another command's exit code.

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

Network-capable code lives in exactly two modules (Req 14.2): :mod:`fitdocs.tiles`,
which fetches missing basemap tiles during ``sync``/``regen`` map rendering
and only while tile requests are enabled (Req 4.2), and :mod:`fitdocs.connectors.http`,
the connector transport the connector commands -- ``fitdocs connect``
(one authentication attempt against a configured source) and ``fitdocs pull``
(fetching activities from a configured connector) -- send every request
through. Every other operation -- and the entire ``load`` command -- stays
fully offline; a warm tile cache makes even map rendering network-free.

Requirements 1.3, 1.4, 1.5, 2.1, 3.5, 8.1, 8.2, 8.3, 8.4, 8.6, 14.1, 14.2, 14.4.
"""

from __future__ import annotations

import getpass
import math
import os
import re
import sys
import threading
import time
from datetime import UTC, date, datetime, tzinfo
from pathlib import Path
from typing import TYPE_CHECKING, Final, NoReturn

import typer
from rich.console import Console
from rich.table import Table

from fitdocs import AthleteInputs
from fitdocs.agentskill import PACKAGED_SKILLS, skill_root
from fitdocs.athlete import AthleteFileError, load_athlete_inputs
from fitdocs.audit import AuditReport, audit
from fitdocs.benchmarks import BenchmarkKind
from fitdocs.config import DataRootError, resolve_data_root
from fitdocs.connectors.connect import Connected, ConnectFailed, run_connect
from fitdocs.connectors.credentials import (
    CredentialsLocationError,
    CredentialStore,
    check_outside_data_root,
    env_var_name,
    resolve_credentials_dir,
)
from fitdocs.connectors.http import Transport, urllib_transport
from fitdocs.connectors.protocol import (
    SUPPORTED_AUTH_STYLES,
    AuthStyle,
    SettingsContext,
)
from fitdocs.connectors.pull import (
    Delivered,
    InstancePullReport,
    PullNote,
    PullOptions,
    PullReport,
    run_pull,
)
from fitdocs.connectors.secrets import Redactor
from fitdocs.connectors.settings import load_connectors_settings
from fitdocs.history.engine import HistoryReport, run_history
from fitdocs.identity.holds import HoldRecordError, load_holds
from fitdocs.identity.settings import IdentitySettings, load_identity_settings
from fitdocs.inbox import (
    InboxNote,
    InboxPaths,
    InboxSettings,
    create_inbox_paths,
    load_inbox_settings,
    validate_inbox_paths,
)
from fitdocs.index.location import IndexLocationError
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
from fitdocs.query.command import (
    DEFAULT_MAX_ROWS,
    DEFAULT_TIMEOUT_S,
    OutcomeKind,
    QueryEnvironment,
    QueryRequest,
    run_query,
)
from fitdocs.query.format import OutputFormat, default_format, render_result
from fitdocs.query.sandbox import process_is_running
from fitdocs.query.schemaview import (
    render_schema_json,
    render_schema_text,
    render_state_text,
    undescribed,
)
from fitdocs.query.statement import (
    RESTRICTION_TEXT,
    Restriction,
    statement_kind_refusal,
)
from fitdocs.settings import SettingsError, load_settings_document
from fitdocs.sync import DrainReport, SyncReport, drain, regen, sync
from fitdocs.tiles import TileStore, load_tile_settings, tile_settings_from_document
from fitdocs.version import UNKNOWN_VERSION, version_display

if TYPE_CHECKING:
    from fitdocs.index.handoff import HandoffCollector
    from fitdocs.index.refresh import IndexReport, ProgressCallback

_EXIT_SUCCESS: int = 0
"""Everything written and/or skipped; no failures (an all-skipped run, too)."""
_EXIT_FILE_FAILURES: int = 1
"""One or more per-file failures occurred during the run (Req 1.5)."""
_EXIT_INTERRUPTED: int = 130
"""A user interrupt (SIGINT) ended `fitdocs query`: 128 + 2, the shell convention."""
_EXIT_CONFIG_ERROR: int = 2
"""A configuration error prevented the run: nothing was written (Req 2.2)."""


app = typer.Typer(
    name="fitdocs",
    help="Turn .fit files into rich markdown workout documents.",
    add_completion=False,
    no_args_is_help=True,
    pretty_exceptions_show_locals=False,
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
_REBUILD_INDEX_OPTION = typer.Option(
    False,
    "--rebuild",
    help="Build a fresh index and atomically replace any existing one.",
)
_QUERY_SQL_ARGUMENT = typer.Argument(
    None, help="One SQL statement, or '-' to read it from standard input."
)
_QUERY_FILE_OPTION = typer.Option(
    None, "--file", help="Read the SQL statement from PATH."
)
_QUERY_SCHEMA_OPTION = typer.Option(
    False, "--schema", help="Describe the indexed schema."
)
_QUERY_FORMAT_OPTION = typer.Option(
    None,
    "--format",
    case_sensitive=False,
    help="Result format: table, csv, or json (default depends on stdout).",
)
_QUERY_MAX_ROWS_OPTION = typer.Option(
    DEFAULT_MAX_ROWS, "--max-rows", min=1, help="Maximum result rows to print."
)
_QUERY_TIMEOUT_OPTION = typer.Option(
    DEFAULT_TIMEOUT_S, "--timeout", help="Query time limit in seconds."
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
_CONNECT_NAME_ARGUMENT = typer.Argument(
    ...,
    help=(
        "The name of a configured connector instance (a table under the "
        "connectors table in fitdocs.toml)."
    ),
)
_PULL_NAMES_ARGUMENT = typer.Argument(
    None,
    help=(
        "Configured connector instance names to pull (default: every "
        "configured instance, in name order)."
    ),
)
_SINCE_OPTION = typer.Option(
    None,
    "--since",
    help=(
        "YYYY-MM-DD; list activities from the start of that day in the local time zone."
    ),
)
_PULL_DRY_RUN_OPTION = typer.Option(
    False,
    "--dry-run",
    help=(
        "List and report what each instance would fetch; fetch, deliver, "
        "remove, and record nothing -- except a token renewal the listing "
        "needs, which is still saved to the credentials store."
    ),
)
_SYNC_OPTION = typer.Option(
    False,
    "--sync",
    help="Then drain the inbox exactly as `fitdocs sync` does.",
)
_SINCE_DATE_RE: Final[re.Pattern[str]] = re.compile(r"\d{4}-\d{2}-\d{2}")


@app.command("index")
def index_command(
    out: Path | None = _OUT_OPTION,
    rebuild: bool = _REBUILD_INDEX_OPTION,
) -> None:
    """Build or refresh the disposable analytics index."""
    from fitdocs.index.build import run_index_command
    from fitdocs.index.location import IndexLocationError
    from fitdocs.index.refresh import Outcome

    data_root = _resolved_data_root(out)
    athlete = _loaded_athlete(data_root)
    try:
        report = run_index_command(
            data_root,
            environ=os.environ,
            home=Path.home(),
            athlete=athlete,
            today=_today(),
            rebuild=rebuild,
            progress=_index_progress(),
        )
    except IndexLocationError as error:
        _config_error(str(error))

    _report_index_command(report)
    result = report.result
    successful_outcome = report.outcome in {
        Outcome.BUILT,
        Outcome.REFRESHED,
        Outcome.UNCHANGED,
    }
    has_errors = result is not None and bool(
        result.page_errors or result.producer_errors
    )
    if successful_outcome and not has_errors:
        raise typer.Exit(code=_EXIT_SUCCESS)
    raise typer.Exit(code=_EXIT_FILE_FAILURES)


def _index_progress() -> ProgressCallback:
    """Print index computation progress on stderr, separate from the report."""

    def report(done: int, total: int) -> None:
        Console(stderr=True, markup=False, highlight=False, soft_wrap=True).print(
            f"Indexing: {done}/{total} pages"
        )

    return report


def _new_index_handoff() -> HandoffCollector:
    from fitdocs.index.handoff import HandoffCollector

    return HandoffCollector()


def _run_index_pass(data_root: Path, *, handoff: HandoffCollector | None) -> None:
    try:
        from fitdocs.index.refresh import refresh_after_command

        report = refresh_after_command(
            data_root,
            environ=os.environ,
            home=Path.home(),
            handoff=handoff,
            today=_today(),
            progress=_index_progress(),
        )
        _report_index_pass(report)
    except Exception as exc:
        Console(markup=False, highlight=False, soft_wrap=True).print(
            f"Index: not refreshed; {type(exc).__name__}: {exc}."
        )


def _report_index_pass(report: IndexReport) -> None:
    from fitdocs.index.refresh import Outcome

    console = Console(markup=False, highlight=False, soft_wrap=True)
    result = report.result
    if (
        report.outcome is Outcome.REFRESHED
        and result is not None
        and (result.added or result.updated or result.removed)
    ):
        console.print(
            f"Index: {len(result.added)} added, {len(result.updated)} updated, "
            f"{len(result.removed)} removed."
        )
    if result is not None:
        for path, error in result.page_errors:
            console.print(f"Index: could not index {path}: {error}")
        for producer, error in result.producer_errors:
            console.print(f"Index: could not refresh {producer}: {error}")
    if report.outcome is Outcome.NOT_BUILT:
        console.print("Index: not built; run 'fitdocs index' to build it.")
    elif report.outcome is Outcome.NEEDS_REBUILD:
        reason = report.detail or "the index is not readable"
        console.print(f"Index: {reason}; run 'fitdocs index' to rebuild it.")
    elif report.outcome is Outcome.BUSY:
        if report.detail and report.detail.startswith("writer lock is held"):
            console.print(
                "Index: not refreshed; another fitdocs command is writing it. "
                "The next writing command or 'fitdocs index' will catch up."
            )
        elif report.holder_pid is None:
            console.print(
                "Index: not refreshed; it is open in another program. "
                "Close it; the next writing command or 'fitdocs index' will catch up."
            )
        else:
            console.print(
                "Index: not refreshed; it is open in another program "
                f"(process {report.holder_pid}). Close it; the next writing "
                "command or 'fitdocs index' will catch up."
            )
    elif report.outcome is Outcome.STAGED:
        console.print("Index replacement staged; run 'fitdocs index' again to finish.")
        if report.detail:
            console.print(f"  {report.detail}")
    elif report.outcome is Outcome.FAILED:
        console.print(f"Index: not refreshed; {report.detail or 'unknown failure'}.")


def _report_index_command(report: IndexReport) -> None:
    """Print the full `fitdocs index` result and any per-page detail."""
    from fitdocs.index.bookkeeping import ComputedState
    from fitdocs.index.schema import SCHEMA_VERSION

    console = Console(markup=False, highlight=False, soft_wrap=True)
    result = report.result
    table = Table(title="fitdocs index")
    table.add_column("Result")
    table.add_column("Count", justify="right")
    table.add_row("Result", report.outcome.value.replace("_", " ").upper())
    table.add_row("Pages held", str(result.pages_held if result is not None else 0))
    table.add_row("Added", str(len(result.added) if result is not None else 0))
    table.add_row("Updated", str(len(result.updated) if result is not None else 0))
    table.add_row("Removed", str(len(result.removed) if result is not None else 0))
    table.add_row(
        "Without computed values",
        str(len(result.without_computed) if result is not None else 0),
    )
    table.add_row("Left out", str(len(result.left_out) if result is not None else 0))
    error_count = (
        len(result.page_errors) + len(result.producer_errors)
        if result is not None
        else 0
    )
    table.add_row("Errors", str(error_count))
    console.print(table)

    if report.location is not None:
        console.print(f"Index file: {report.location.database}")
        console.print(f"Schema version: {SCHEMA_VERSION}")
    if report.outcome.value in {"built", "needs_rebuild"} and report.detail is not None:
        console.print(f"Rebuilt: {report.detail}")
    elif report.outcome.value == "staged":
        console.print("Index replacement staged; run 'fitdocs index' again to finish.")
        if report.detail:
            console.print(f"  {report.detail}")
    elif report.outcome.value == "busy":
        if report.holder_pid is None:
            console.print("Index is busy; close the other writer and try again.")
        else:
            console.print(
                f"Index is open in another program (process {report.holder_pid}); "
                "close it and try again."
            )
    elif report.outcome.value == "failed" and report.detail is not None:
        console.print(f"Index failed: {report.detail}")
    elif report.outcome.value == "not_built":
        console.print("Index is not built.")

    if result is None:
        return
    missing_messages = {
        ComputedState.SOURCE_MISSING: "base file missing from the archive",
        ComputedState.SOURCE_UNREADABLE: "base file could not be read",
        ComputedState.SOURCE_UNDECODABLE: "base file could not be decoded",
    }
    for path, state in result.without_computed:
        console.print(f"{path}: {missing_messages[state]}")
    for item in result.left_out:
        if item.reason == "no_base_reference":
            detail = "no archived base reference"
        else:
            detail = f"lists the same base file as {item.collides_with}; not indexed"
        console.print(f"{item.path}: {detail}")
    for path, error in result.page_errors:
        console.print(f"Could not index {path}: {error}")
    for producer, error in result.producer_errors:
        console.print(f"Could not refresh {producer}: {error}")


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
    failure, and never changes the exit code. The analytics index is refreshed
    best-effort after the plan pass and cannot change this command's exit code.
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
        # Load [identity] once (a malformed table exits 2 here, before any write).
        identity = _identity_settings(data_root)
        handoff = _new_index_handoff()
        try:
            report = sync(
                source,
                data_root,
                athlete=athlete,
                tz=tz,
                tiles=tiles,
                force=force,
                precedence=identity.precedence,
                on_rendered=handoff.add,
            )
        except HoldRecordError as exc:
            _hold_record_error(exc)
        _report(report, command="sync")
        # The load pass runs after writing documents (Req 8.1), honoring --no-prompt.
        load_report = _run_load_pass(
            data_root, session=_build_session(no_prompt=no_prompt)
        )
        # The plan reconciling pass runs after the load pass, chained
        # (plan-resolution Req 8.1, 8.2, 8.5).
        plan_report = _run_plan_pass(data_root, today=_today(), chained=True)
        _run_index_pass(data_root, handoff=handoff)
        _report_plugin_errors(plugin_report)
        # A per-file OR a per-document (load) OR a reconciling-pass failure
        # makes the run exit 1 (8.5, plan-resolution Req 8.7).
        _finish(
            failed=bool(report.failures)
            or bool(load_report.failures)
            or plan_report.failed
        )
        return

    # No SOURCE: drain the configured inbox (inbox Req 2.1), then run the
    # load and plan passes -- extracted into a shared helper so a later
    # `pull --sync` call can chain the identical drain (Req 12.1, 12.3).
    failed = _run_drain_passes(
        data_root,
        tz=tz,
        athlete=athlete,
        force=force,
        retry_quarantined=retry_quarantined,
        no_prompt=no_prompt,
        command="sync",
    )
    _finish(failed=failed)


def _run_drain_passes(
    data_root: Path,
    *,
    tz: tzinfo,
    athlete: AthleteInputs | None,
    force: bool,
    retry_quarantined: bool,
    no_prompt: bool,
    command: str,
) -> bool:
    """Drain the configured inbox, then run the load and plan passes.

    The body of ``sync_command``'s no-source branch, moved verbatim so a
    later ``pull --sync`` call can chain the identical drain (design:
    CliCommands "``_run_drain_passes``"; Req 12.1, 12.3): plugin discovery,
    the inbox preflight, the drain, the drain report (titled with
    ``command``), the load pass, the plan pass, then plugin errors. Returns
    whether anything failed -- a per-file drain failure, a load failure, or
    a reconciling-pass failure -- so the caller decides how to exit. The
    analytics index is refreshed best-effort after the plan pass and cannot
    change the returned failure state.
    """
    # Discover plugins once, before any engine call (a malformed [plugins] table
    # exits 2 here, before any write) -- same position as the explicit-source
    # path (cross-spec landing order: plugin-api's edit lands first).
    plugin_report = _plugin_report(data_root)
    # The [identity] table and the hold record are validated before the inbox
    # pre-flight, which creates the inbox (and processed) directory: a
    # malformed table or a damaged record writes nothing (identity Req 2.7).
    identity = _identity_settings(data_root)
    try:
        load_holds(data_root)
    except HoldRecordError as exc:
        _hold_record_error(exc)
    inbox_settings, inbox_paths, quarantine, tiles = _inbox_preflight(data_root)
    handoff = _new_index_handoff()
    try:
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
            precedence=identity.precedence,
            on_rendered=handoff.add,
        )
    except HoldRecordError as exc:
        _hold_record_error(exc)
    _report_drain(drain_report, command=command)
    # The load pass runs after the drain (Req 2.1), honoring --no-prompt exactly
    # as the explicit-source path does (Req 2.5).
    load_report = _run_load_pass(data_root, session=_build_session(no_prompt=no_prompt))
    # The plan reconciling pass runs after the load pass, chained
    # (plan-resolution Req 8.1, 8.2, 8.5), same as the explicit-source path.
    plan_report = _run_plan_pass(data_root, today=_today(), chained=True)
    _run_index_pass(data_root, handoff=handoff)
    _report_plugin_errors(plugin_report)
    # Per-file failures, load failures and a reconciling-pass failure drive
    # the failure outcome -- deferrals, known-quarantined files, and failed
    # moves never do (inbox Req 4.6, 5.3, 6.5, 7.2; plan-resolution Req 8.7).
    return (
        bool(drain_report.sync.failures)
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
    writes nothing (inbox Req 1.4, 1.6, 5.6, 7.2). The ``[identity]`` table
    and the hold record are not this helper's: :func:`sync_command` validates
    both before calling it, because it is the step that creates directories.
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
    code. The analytics index is refreshed best-effort after the plan pass and
    cannot change this command's exit code.
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
    identity = _identity_settings(data_root)
    handoff = _new_index_handoff()
    report = regen(
        data_root,
        athlete=athlete,
        tz=tz,
        tiles=tiles,
        precedence=identity.precedence,
        on_rendered=handoff.add,
    )
    _report(report, command="regen")
    # regen is always non-interactive, which makes its load pass restore-only:
    # computed load is re-derived from the preserved payload, no prompting (7.4).
    load_report = _run_load_pass(data_root, session=NonInteractiveSession())
    # The plan reconciling pass runs after the load pass, chained
    # (plan-resolution Req 8.1, 8.2, 8.5).
    plan_report = _run_plan_pass(data_root, today=_today(), chained=True)
    _run_index_pass(data_root, handoff=handoff)
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
    the exit code. A best-effort index refresh follows the load pass and cannot
    change the command's exit code.
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
    _run_index_pass(data_root, handoff=None)
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


def _connector_transport() -> Transport:
    """The real connector transport (design: CliCommands); tests patch this."""
    return urllib_transport


def _stdin_is_interactive() -> bool:
    """Whether standard input is a real terminal (design: CliCommands)."""
    return sys.stdin.isatty()


def _ask_secret(prompt: str) -> str:
    """Read one line with no echo (design: CliCommands, Req 5.1)."""
    return getpass.getpass(prompt)


def _ask_value(prompt: str) -> str:
    """Read one ordinary, echoed line (design: CliCommands)."""
    return str(typer.prompt(prompt))


@app.command("connect")
def connect_command(
    name: str = _CONNECT_NAME_ARGUMENT,
    out: Path | None = _OUT_OPTION,
) -> None:
    """Authenticate one configured connector instance once and store its
    credentials only on success.

    (connectors design: CliCommands "``connect`` flow"; Req 1.7, 3.9, 4.2,
    5.1-5.9, 10.6.)

    Resolves the data root (Req 3.9), reads the settings document, validates
    -- without creating -- the configured inbox (needed only so a connector's
    own settings can refuse a configuration that would loop into it), and
    projects the connectors table. NAME must be a configured instance;
    otherwise this exits with the configuration-error code naming every
    configured instance (Req 5.3). A connector that needs no authentication
    reports that there is nothing to connect and exits with the success code,
    prompting for and writing nothing (Req 5.2); a connector whose
    authentication style is reserved exits with the configuration-error code
    naming it unsupported by this version (Req 1.7, 5.3).

    The per-user credentials directory is then resolved and checked to be
    outside the data root (Req 4.1, 4.2); when standard input is not an
    interactive terminal this command prompts for nothing and exits with the
    configuration-error code, naming -- for a personal-key connector only --
    the environment variables an unattended pull can use instead (Req 5.4).
    Otherwise every credential field the connector declares is prompted for,
    a field marked secret through the no-echo seam (Req 5.1); an empty
    answer exits with the configuration-error code before any request is
    made (Req 5.7).

    The one authentication attempt itself is :func:`~fitdocs.connectors.
    connect.run_connect`. On success this prints the instance, the
    credentials file's location, and the granted scopes (or that the service
    reported none) and any environment variable that will override a stored
    value during a pull, then exits with the success code (Req 5.5). On
    refusal it prints which of the typed failure kinds occurred, the
    service's own message with every secret redacted, and the next step,
    then exits with the failure code; nothing is stored either way (Req
    5.6). An exception ``run_connect`` does not itself map -- a connector's
    ``verify``/``login`` raising something other than the typed failures --
    is still never shown unredacted or as a traceback: this command maps it
    to ``<ExceptionType>: <redacted message>`` and the failure code, the same
    shape a mapped failure uses (interpretation: design.md states this rule
    for the pull command's own exceptions, Req 10.2, and is silent for
    connect's; applied here identically since nothing here may ever show an
    unredacted secret). Nothing is written under the data root either way
    (Req 5.9); this command never touches the inbox, a ledger, or a
    delivery.
    """
    data_root = _resolved_data_root(out)
    try:
        document = load_settings_document(data_root)
        inbox_settings = load_inbox_settings(document, data_root=data_root)
        validated_inbox = validate_inbox_paths(data_root, inbox_settings)
        instances = load_connectors_settings(
            document,
            settings_file=settings_path(data_root),
            context=SettingsContext(
                data_root=data_root, inbox=validated_inbox.inbox_resolved
            ),
        )
    except SettingsError as exc:
        _config_error(str(exc))

    by_name = {instance.name: instance for instance in instances}
    instance = by_name.get(name)
    if instance is None:
        configured = ", ".join(sorted(by_name)) or "none"
        _config_error(
            f"{name!r} is not a configured connector instance; "
            f"configured instances: {configured}"
        )

    connector = instance.connector
    if connector.auth_style is AuthStyle.NONE:
        Console().print(
            f"{name}: this connector requires no authentication; nothing to connect.",
            markup=False,
            highlight=False,
            soft_wrap=True,
        )
        raise typer.Exit(code=_EXIT_SUCCESS)

    if connector.auth_style not in SUPPORTED_AUTH_STYLES:
        _config_error(
            f"{name}: {connector.auth_style.value} authentication is "
            "reserved; this version of fitdocs does not support it."
        )

    try:
        credentials_dir = resolve_credentials_dir(os.environ, Path.home())
        check_outside_data_root(credentials_dir, data_root)
    except CredentialsLocationError as exc:
        _config_error(str(exc))

    if not _stdin_is_interactive():
        if connector.auth_style is AuthStyle.API_KEY:
            variables = ", ".join(
                env_var_name(name, field.name) for field in connector.credential_fields
            )
            _config_error(
                f"{name}: standard input is not an interactive terminal; "
                f"an unattended pull can use {variables} instead."
            )
        _config_error(
            f"{name}: standard input is not an interactive terminal; "
            "`fitdocs connect` needs one to prompt for credentials."
        )

    answers: dict[str, str] = {}
    for credential_field in connector.credential_fields:
        prompt = f"{credential_field.label}: "
        value = _ask_secret(prompt) if credential_field.secret else _ask_value(prompt)
        if not value:
            _config_error(f"{name}: {credential_field.label} must not be empty.")
        answers[credential_field.name] = value

    store = CredentialStore(credentials_dir)
    redactor = Redactor()
    try:
        outcome = run_connect(
            instance,
            answers,
            store=store,
            transport=_connector_transport(),
            environ=os.environ,
            now=lambda: datetime.now(UTC),
            sleep=time.sleep,
            redactor=redactor,
        )
    except Exception as exc:  # noqa: BLE001 - mapped to a redacted, typed line
        message = redactor.redact(str(exc))
        Console().print(
            f"{type(exc).__name__}: {message}",
            markup=False,
            highlight=False,
            soft_wrap=True,
        )
        raise typer.Exit(code=_EXIT_FILE_FAILURES) from None

    if isinstance(outcome, Connected):
        console = Console()
        console.print(
            f"{name}: connected.", markup=False, highlight=False, soft_wrap=True
        )
        console.print(
            f"Credentials: {outcome.path}",
            markup=False,
            highlight=False,
            soft_wrap=True,
        )
        scopes_line = (
            ", ".join(outcome.scopes)
            if outcome.scopes
            else "the service reported no scopes"
        )
        console.print(
            f"Scopes: {scopes_line}",
            markup=False,
            highlight=False,
            soft_wrap=True,
        )
        if outcome.env_override:
            console.print(
                "Overriding environment variables (used instead of the "
                f"stored values during a pull): {', '.join(outcome.env_override)}",
                markup=False,
                highlight=False,
                soft_wrap=True,
            )
        raise typer.Exit(code=_EXIT_SUCCESS)

    assert isinstance(outcome, ConnectFailed)
    console = Console()
    console.print(
        f"{name}: {outcome.kind.value}: {outcome.message}",
        markup=False,
        highlight=False,
        soft_wrap=True,
    )
    console.print(outcome.next_step, markup=False, highlight=False, soft_wrap=True)
    raise typer.Exit(code=_EXIT_FILE_FAILURES)


def _parse_since(value: str) -> datetime:
    """Parse ``--since``'s ``YYYY-MM-DD`` value as local midnight, in UTC
    (design: CliCommands pull preflight, Req 6.4).

    ``date.fromisoformat`` alone accepts more than this shape (ISO week
    dates, the compact ``YYYYMMDD`` form); the leading ``fullmatch`` keeps
    the documented ``YYYY-MM-DD`` shape the only one accepted.
    """
    if not _SINCE_DATE_RE.fullmatch(value):
        _config_error(f"--since {value!r} is not a valid date; use YYYY-MM-DD.")
    try:
        since_date = date.fromisoformat(value)
    except ValueError:
        _config_error(f"--since {value!r} is not a valid date; use YYYY-MM-DD.")
    # A naive local midnight's ``astimezone()`` applies the local zone's
    # offset *on that date*; ``_local_tz()`` is today's fixed offset, which
    # is an hour off for a date on the other side of a DST change.
    return (
        datetime.combine(since_date, datetime.min.time()).astimezone().astimezone(UTC)
    )


@app.command("pull")
def pull_command(
    names: list[str] | None = _PULL_NAMES_ARGUMENT,
    out: Path | None = _OUT_OPTION,
    since: str | None = _SINCE_OPTION,
    dry_run: bool = _PULL_DRY_RUN_OPTION,
    sync_after: bool = _SYNC_OPTION,
    no_prompt: bool = _NO_PROMPT_OPTION,
) -> None:
    """Fetch new activities from every configured connector instance, or the
    named ones, and deliver them into the inbox.

    (connectors design: CliCommands "``fitdocs pull``"; Req 3.9, 4.2, 6.1-6.3,
    6.9, 8.4, 11.1-11.5.)

    Every preflight check runs, in design.md's order, before any request or
    write: the data root (Req 3.9); ``--sync`` combined with ``--dry-run``
    (Req 12.4); ``--since`` parsed as ``YYYY-MM-DD`` at local midnight; the
    settings document; the configured inbox, validated but not created (Req
    8.4); the connectors table; NAMES, when given, matched against the
    configured instances -- an unknown name exits with the configuration-error
    code naming every configured instance (Req 6.2); and, when any selected
    instance's connector authenticates, the per-user credentials directory,
    resolved and checked to lie outside the data root (Req 4.2). With
    ``--sync`` the preflight also loads the athlete inputs, runs plugin
    discovery, projects the tiles table, and loads the quarantine
    record -- the same checks ``fitdocs sync``'s own drain path makes before
    its first write -- plus the identity settings and the hold record
    (identity Req 2.7), each before any request or write; after the pull
    report, ``--sync`` chains :func:`_run_drain_passes` (task 1.4), labeled
    ``pull``, even when an instance failed and even when no connector is
    configured. The drain re-reads the identity table and the hold record
    itself (a harmless repeat of this preflight's own read, the same pattern
    :func:`_plugin_report` already runs twice on this path) and passes the
    configured precedence into the drain call (connectors Req 12.1-12.3,
    12.5; the join with activity-identity, design.md CliCommands "Identity
    wiring").

    Unless ``--dry-run``, the inbox (and, under the move disposition, the
    processed-files destination) is created once every check above has
    passed. With no instance configured, this prints that nothing is
    configured and continues rather than returning early (Req 6.3) -- the
    pull still runs, over no instances, so the report and (under
    ``--sync``) the drain behave exactly as they would with a connectors
    table that happens to be empty.

    The pull itself is :func:`~fitdocs.connectors.pull.run_pull`, which
    isolates every instance's and every activity's own failure into the
    returned report (Req 6.10, 6.11); an exception it does not itself catch
    -- a genuine bug, never an ordinary per-instance failure -- is still
    never shown unredacted or as a traceback here: mapped to
    ``<ExceptionType>: <redacted message>`` and the failure code, the same
    convention :func:`connect_command` already applies to its own call (Req
    10.1-10.2). Otherwise :func:`_report_pull` prints the report and this
    command exits with the failure code when :attr:`PullReport.failed` is
    true, else the success code (Req 11.4).
    """
    data_root = _resolved_data_root(out)

    if sync_after and dry_run:
        _config_error(
            "--sync cannot be combined with --dry-run: a dry run writes nothing."
        )

    since_dt = _parse_since(since) if since is not None else None

    try:
        document = load_settings_document(data_root)
        inbox_settings = load_inbox_settings(document, data_root=data_root)
        validated_inbox = validate_inbox_paths(data_root, inbox_settings)
        all_instances = load_connectors_settings(
            document,
            settings_file=settings_path(data_root),
            context=SettingsContext(
                data_root=data_root, inbox=validated_inbox.inbox_resolved
            ),
        )
    except SettingsError as exc:
        _config_error(str(exc))

    by_name = {instance.name: instance for instance in all_instances}
    if names:
        unknown = sorted(set(names) - by_name.keys())
        if unknown:
            configured = ", ".join(sorted(by_name)) or "none"
            _config_error(
                f"unknown connector instance(s): {', '.join(unknown)}; "
                f"configured instances: {configured}"
            )
        wanted = set(names)
        selected = tuple(
            instance for instance in all_instances if instance.name in wanted
        )
    else:
        selected = all_instances

    store: CredentialStore | None = None
    if any(
        instance.connector.auth_style is not AuthStyle.NONE for instance in selected
    ):
        try:
            credentials_dir = resolve_credentials_dir(os.environ, Path.home())
            check_outside_data_root(credentials_dir, data_root)
        except CredentialsLocationError as exc:
            _config_error(str(exc))
        store = CredentialStore(credentials_dir)

    athlete: AthleteInputs | None = None
    if sync_after:
        athlete = _loaded_athlete(data_root)
        _plugin_report(data_root)
        try:
            tile_settings_from_document(document, settings_path(data_root))
        except SettingsError as exc:
            _config_error(str(exc))
        try:
            load_quarantine(data_root)
        except QuarantineError as exc:
            _config_error(str(exc))
        _identity_settings(data_root)
        try:
            load_holds(data_root)
        except HoldRecordError as exc:
            _hold_record_error(exc)

    if dry_run:
        inbox_path = validated_inbox.inbox_resolved
    else:
        inbox_path = create_inbox_paths(validated_inbox).inbox

    if not selected:
        Console().print(
            "No connectors are configured; nothing to pull.",
            markup=False,
            highlight=False,
            soft_wrap=True,
        )

    redactor = Redactor()
    try:
        report = run_pull(
            data_root,
            selected,
            inbox=inbox_path,
            store=store,
            transport=_connector_transport(),
            options=PullOptions(since=since_dt, dry_run=dry_run),
            environ=os.environ,
            now=lambda: datetime.now(UTC),
            sleep=time.sleep,
            redactor=redactor,
        )
    except Exception as exc:  # noqa: BLE001 - mapped to a redacted, typed line
        message = redactor.redact(str(exc))
        Console().print(
            f"{type(exc).__name__}: {message}",
            markup=False,
            highlight=False,
            soft_wrap=True,
        )
        raise typer.Exit(code=_EXIT_FILE_FAILURES) from None

    _report_pull(report)
    # Under --sync, the drain chains after the pull table regardless of
    # whether the pull itself failed, and regardless of whether any instance
    # was configured (no early return): the chained drain is the join with
    # activity-identity -- `_run_drain_passes` loads its own [identity]
    # table and hold record again (a redundant, harmless re-read, the same
    # pattern `_plugin_report` already runs twice on this path) and passes
    # the configured precedence into the drain itself (Req 12.1-12.3, 12.5).
    drain_failed = False
    if sync_after:
        drain_failed = _run_drain_passes(
            data_root,
            tz=_local_tz(),
            athlete=athlete,
            force=False,
            retry_quarantined=False,
            no_prompt=no_prompt,
            command="pull",
        )
    # The pull or the chained drain failing makes the run exit 1 (Req 12.5).
    _finish(failed=report.failed or drain_failed)


_PULL_REPORT_ROWS: Final[tuple[tuple[str, str], ...]] = (
    ("Listed", "listed"),
    ("Delivered", "delivered"),
    ("Would fetch", "would_fetch"),
    ("Already held", "held"),
    ("Skipped", "skipped"),
    ("Deferred", "deferred"),
    ("Failed", "failed"),
    ("Removed", "removed"),
    ("Error", "error"),
)
"""The pull report table's rows, each naming the :class:`InstancePullReport`
field it counts (design: CliCommands "``_report_pull``", Req 11.1) -- the
one ordered source of truth both the table and (via
:data:`_PULL_REPORT_ROWS`) any later consumer read, so a channel can never
be renamed or dropped in one place and not the other."""


def _report_pull(report: PullReport) -> None:
    """Print the pull report exactly as design.md's ``_report_pull`` states
    (Req 11.1, 11.2, 11.3, 11.5): the inbox line or the dry-run line, then
    per instance an always-complete counts table and its detail blocks.
    """
    console = Console()
    if report.dry_run:
        console.print(
            "Dry run — nothing fetched or written.",
            markup=False,
            highlight=False,
            soft_wrap=True,
        )
    else:
        console.print(
            f"Inbox: {report.inbox}", markup=False, highlight=False, soft_wrap=True
        )

    instance: InstancePullReport
    for instance in report.instances:
        table = Table(title=f"fitdocs pull: {instance.name} ({instance.connector_id})")
        table.add_column("Result")
        table.add_column("Count", justify="right")
        for label, field_name in _PULL_REPORT_ROWS:
            if field_name == "listed":
                count = instance.listed
            elif field_name == "error":
                count = 1 if instance.error is not None else 0
            else:
                count = len(getattr(instance, field_name))
            table.add_row(label, str(count))
        console.print(table)

        if instance.delivered:
            console.print("Delivered:")
            delivered_item: Delivered
            for delivered_item in instance.delivered:
                console.print(
                    f"  {delivered_item.path}",
                    markup=False,
                    highlight=False,
                    soft_wrap=True,
                )

        if instance.would_fetch:
            console.print("Would fetch:")
            for remote_id in instance.would_fetch:
                console.print(
                    f"  {remote_id}", markup=False, highlight=False, soft_wrap=True
                )

        def _print_notes(label: str, notes: tuple[PullNote, ...]) -> None:
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

        _print_notes("Skipped", instance.skipped)
        _print_notes("Deferred", instance.deferred)
        _print_notes("Failed", instance.failed)

        if instance.removed:
            console.print("Removed:")
            for path in instance.removed:
                console.print(
                    f"  {path}", markup=False, highlight=False, soft_wrap=True
                )

        if instance.error is not None:
            console.print("Error:")
            console.print(
                f"  {instance.error.detail}",
                markup=False,
                highlight=False,
                soft_wrap=True,
            )


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


@app.command("query")
def query_command(
    sql: str | None = _QUERY_SQL_ARGUMENT,
    file: Path | None = _QUERY_FILE_OPTION,
    schema: bool = _QUERY_SCHEMA_OPTION,
    output_format: OutputFormat | None = _QUERY_FORMAT_OPTION,
    max_rows: int = _QUERY_MAX_ROWS_OPTION,
    timeout: float = _QUERY_TIMEOUT_OPTION,
    out: Path | None = _OUT_OPTION,
) -> None:
    """Run one read-only SQL statement against the analytics index,
    or describe its schema."""
    console = Console(stderr=True, markup=False, highlight=False, soft_wrap=True)

    if not math.isfinite(timeout) or timeout <= 0:
        _config_error("--timeout must be a finite number greater than zero.")
    if schema and output_format is OutputFormat.CSV:
        _config_error("fitdocs query does not support --format csv with --schema.")

    positional_source = sql is not None and sql != "-"
    stdin_source = sql == "-"
    file_source = file is not None
    source_count = sum((positional_source, stdin_source, file_source))
    if (schema and source_count != 0) or (not schema and source_count != 1):
        _config_error(
            "provide exactly one SQL source (SQL, --file PATH, or '-' for "
            "standard input); --schema accepts no SQL source."
        )

    statement = None if schema else _read_statement(sql, file)

    data_root = _resolved_data_root(out)

    def on_wait(holder_pid: int | None) -> None:
        process = f" (process {holder_pid})" if holder_pid is not None else ""
        console.print(
            f"Index: waiting for another process{process} to finish writing the index…"
        )

    request = QueryRequest(
        data_root=data_root,
        sql=statement,
        schema=schema,
        max_rows=max_rows,
        timeout_s=timeout,
        today=_today(),
    )
    environment = QueryEnvironment(
        environ=os.environ,
        home=Path.home(),
        pid=os.getpid(),
        monotonic=time.monotonic,
        sleep=time.sleep,
        on_wait=on_wait,
        is_running=process_is_running,
        timer=threading.Timer,
    )
    try:
        outcome = run_query(request, environment)
    except IndexLocationError as error:
        _config_error(str(error))
    except KeyboardInterrupt:
        console.print("Query interrupted.")
        raise typer.Exit(code=_EXIT_INTERRUPTED) from None

    if (
        schema
        and outcome.kind not in {OutcomeKind.RESULT, OutcomeKind.SCHEMA}
        and outcome.state is not None
    ):
        console.print(render_state_text(outcome.state))

    drift = outcome.drift
    if outcome.kind is OutcomeKind.SCHEMA and outcome.schema is not None:
        drift = outcome.drift or outcome.schema.state.drift

    if outcome.kind in {OutcomeKind.RESULT, OutcomeKind.SCHEMA}:
        if drift is not None and drift.behind:
            console.print(
                "Index: behind the data root "
                f"({drift.added} added, {drift.changed} changed, "
                f"{drift.removed} removed pages since the last refresh); "
                "run 'fitdocs index' to bring it level."
            )
        if outcome.kind is OutcomeKind.RESULT:
            assert outcome.result is not None
            if output_format is not None:
                selected_format = output_format
            else:
                selected_format = default_format(_stdout_is_terminal())
            rendered = render_result(
                outcome.result,
                selected_format,
                freshness=drift.as_mapping() if drift is not None else {},
            )
            typer.echo(rendered)
            if outcome.result.truncated:
                console.print(
                    f"Query: showing the first {outcome.result.max_rows} rows; "
                    "the result has more. Narrow or aggregate the query, or "
                    "raise --max-rows."
                )
        else:
            assert outcome.schema is not None
            report = outcome.schema
            if output_format is OutputFormat.JSON:
                rendered = render_schema_json(
                    report.state, report.tables, report.counts
                )
            else:
                rendered = render_schema_text(
                    report.state, report.tables, report.counts
                )
            typer.echo(rendered)
            for name in undescribed(report.tables):
                console.print(
                    f"Schema: {name} has no description. This is a fitdocs defect; "
                    "please report it."
                )
        return

    if outcome.kind is OutcomeKind.NOT_BUILT:
        console.print("Index: not built; run 'fitdocs index' to build it.")
    elif outcome.kind is OutcomeKind.NEEDS_REBUILD:
        reason = outcome.message or "the index is incompatible"
        console.print(f"Index: {reason}; run 'fitdocs index' to rebuild it.")
    elif outcome.kind is OutcomeKind.BUSY:
        holder = (
            f" by process {outcome.holder_pid}"
            if outcome.holder_pid is not None
            else ""
        )
        console.print(
            "Index: still locked after 10 s"
            f"{holder}: a fitdocs command is refreshing it, or another program "
            "has it open for writing. Run the query again once that finishes."
        )
    elif outcome.kind is OutcomeKind.UNVERIFIED:
        message = outcome.message or "the sandbox settings could not be verified"
        console.print(
            f"Query not run: {message}. This is a fitdocs defect; please report it."
        )
    elif outcome.kind is OutcomeKind.REFUSED:
        restriction = outcome.restriction
        detail = outcome.message or ""
        if restriction is Restriction.ONE_STATEMENT:
            refusal = RESTRICTION_TEXT[restriction]
            console.print(f"Query refused: {refusal}.")
        elif restriction is Restriction.STATEMENT_KIND:
            refusal = statement_kind_refusal(detail)
            console.print(f"Query refused: {refusal}.")
        elif restriction is not None:
            console.print(f"Query refused: {RESTRICTION_TEXT[restriction]}.")
            console.print(f"DuckDB: {detail}")
        else:
            console.print(f"Query refused: {detail}.")
    elif outcome.kind is OutcomeKind.FAILED:
        console.print(f"Query failed: {outcome.message or 'unknown query error'}")
        if outcome.hint:
            console.print(f"Hint: {outcome.hint}")
    elif outcome.kind is OutcomeKind.TIMED_OUT:
        console.print(
            f"Query stopped: it ran longer than {timeout:g} s. "
            "Narrow it, or raise --timeout."
        )
    else:
        raise AssertionError(f"Unhandled query outcome: {outcome.kind}")
    raise typer.Exit(code=_EXIT_FILE_FAILURES)


def _stdout_is_terminal() -> bool:
    """Report whether the query result stream is an interactive terminal."""
    return sys.stdout.isatty()


def _read_statement(sql: str | None, file: Path | None) -> str:
    """Read the already-selected query source as strict UTF-8 text."""
    statement: str | None
    try:
        if file is not None:
            statement = file.read_bytes().decode("utf-8", errors="strict")
        elif sql == "-":
            statement = sys.stdin.buffer.read().decode("utf-8", errors="strict")
        else:
            statement = sql
    except UnicodeDecodeError as error:
        _config_error(f"SQL source is not valid UTF-8: {error}.")
    except OSError as error:
        _config_error(f"cannot read SQL source: {error}.")
    if statement is None or not statement.strip():
        _config_error("SQL statement cannot be empty or whitespace-only.")
    return statement


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


def _identity_settings(data_root: Path) -> IdentitySettings:
    """Load the ``[identity]`` settings from the data root (Req 2.7).

    Mirrors :func:`_tile_store`: a malformed ``[identity]`` table raises
    :class:`~fitdocs.identity.settings.IdentitySettingsError` and a file-level
    fault the shared :class:`~fitdocs.settings.SettingsError` it subclasses;
    either becomes a configuration error (stderr message, exit ``2``). It runs
    before the engine call, so a malformed table writes nothing. Absent table
    or key yields the default precedence.
    """
    try:
        document = load_settings_document(data_root)
        return load_identity_settings(document, settings_path(data_root))
    except SettingsError as exc:
        _config_error(str(exc))


def _hold_record_error(exc: HoldRecordError) -> NoReturn:
    """Map a damaged hold record to a configuration error (exit ``2``).

    The error message already names the file; the remedy is ``fitdocs regen``,
    which rebuilds the record.
    """
    _config_error(f"{exc}\nRun `fitdocs regen` to rebuild the hold record.")


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
    configuration error leaves the data root untouched. Printed with
    ``soft_wrap=True`` so a long path embedded in the message is never split
    across a line break.
    """
    Console(stderr=True).print(message, markup=False, highlight=False, soft_wrap=True)
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
    truncated and bracketed text is never reinterpreted as markup. The
    leading ``Inbox:`` line is likewise printed with ``soft_wrap=True`` so a
    long configured inbox path is never split across a line break.
    """
    console = Console()
    console.print(
        f"Inbox: {report.inbox}", markup=False, highlight=False, soft_wrap=True
    )

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
