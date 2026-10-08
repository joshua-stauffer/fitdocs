"""Write-confinement guard for every writing entry point (Req 7.5, 7.6).

fitdocs installs into markdown wikis it does not control, so the ownership
contract's central promise is negative: a run creates, modifies, and deletes
files **only** inside the paths the contract names as fitdocs-owned
(:data:`~fitdocs.layout.OWNED_PATHS`) together with the locations the user's
settings explicitly configure fitdocs to write into (Req 7.5). Requirement 7.6
adds that *every* entry point observes the same confinement, so adding one must
never widen the owned set.

This module enforces both by running a real, offline, full pipeline over a
disposable sandbox and diffing a whole-tree snapshot taken before and after.
It is deliberately parameterized on the two axes the requirement pairs, so
neither the sibling ingestion spec nor a later settings key forces a rewrite:

* **(a) The entry point.** Registered in :data:`WRITING_ENTRY_POINTS`,
  including explicit ``index`` and the external-cache ``sync`` post-pass.
* **(b) The permitted set.** Computed by :func:`permitted_locations` as the owned
  paths **union** the contract-named shared files fitdocs legitimately writes
  **union** the locations resolved from the settings under test, never
  hardcoded to the owned set. A run that writes into a legitimately configured
  location therefore passes, which is what lets inbox's configured intake
  directory (and its optional ``processed/`` subdirectory) exist without being
  added to ``OWNED_PATHS`` -- see the design's cross-spec integration obligations.

"Owned" and "permitted to write" are deliberately distinct sets here.
:data:`~fitdocs.layout.OWNED_PATHS` is the contract's claim that fitdocs may
create, rewrite, or delete a path *wholesale, on its own initiative* --
``docs/ownership-contract.md`` states that of ``workouts/``, ``fit-archive/``,
``.cache/``, and ``.fitdocs/`` alone. ``athlete.toml`` is not in that set --
the load pass (:func:`~fitdocs.load.engine.apply_load`) only ever writes its
*own* keys into it and preserves the rest, which is the published contract's
"shared file" guarantee (Req 2.7), not ownership. Widening ``OWNED_PATHS`` to
admit it would falsify that document and its conformance test
(``tests/test_ownership_contract.py``); instead :data:`PERMITTED_SHARED_FILES`
names it as a *permitted write location* distinct from the owned set, so this
guard can register ``load`` -- which writes both documents and
``athlete.toml`` -- as a writing entry point (Req 7.5, 7.6) without touching
either the owned-path contract or its test.

The sandbox holds the data root *and* the source directory as siblings, so a
stray write into the read-only source tree is caught as surely as one at the
data root. Directories are compared by existence only: writing a permitted file
necessarily bumps its parent's mtime, and that is not a violation. Everything
runs offline -- the tile store's fetch seam is injected, so the only network-
capable code path never opens a socket.
"""

from __future__ import annotations

import hashlib
import os
import re
import socket
import stat
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta, timezone
from pathlib import Path
from typing import Final, NoReturn
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from fitdocs.athlete import ATHLETE_FILE, load_athlete_inputs
from fitdocs.cli import app
from fitdocs.connectors.connect import Connected, run_connect
from fitdocs.connectors.credentials import CredentialStore
from fitdocs.connectors.http import HttpResponse
from fitdocs.connectors.protocol import Granted, SettingsContext
from fitdocs.connectors.pull import PullOptions, run_pull
from fitdocs.connectors.secrets import Redactor
from fitdocs.connectors.settings import ConnectorInstance, load_connectors_settings
from fitdocs.declaration import DECLARATION_FILENAME
from fitdocs.history import run_history
from fitdocs.inbox import (
    create_inbox_paths,
    load_inbox_settings,
    prepare_inbox,
    validate_inbox_paths,
)
from fitdocs.layout import (
    ARCHIVE_DIR,
    BLOCKS_DIR,
    CONNECTOR_STATE_DIR,
    DEFAULT_PLANS_DIR,
    HISTORY_DIR,
    HISTORY_DOC_STEM,
    OWNED_PATHS,
    SETTINGS_FILE,
    WORKOUTS_DIR,
    settings_path,
)
from fitdocs.load import registry
from fitdocs.load.engine import apply_load
from fitdocs.load.types import InteractionSession
from fitdocs.performance import derive_benchmarks
from fitdocs.plans import run_plan
from fitdocs.plans.reconcile import run_reconcile
from fitdocs.quarantine import load_quarantine
from fitdocs.settings import load_settings_document
from fitdocs.sync import drain, regen, sync
from fitdocs.tiles import DEFAULT_TILE_SETTINGS, TileSource, TileStore
from tests.connectors.conftest import (
    FakeTransport,
    ScriptedPersonalKeyConnector,
    isolate_connector_environment,
)
from tests.fixtures import builder
from tests.fixtures import identity as identity_fixtures
from tests.load.conftest import ComputingCalculator

# PINNED timezone: a FIXED -06:00 offset (never the system zone) so document
# stems are stable wherever the suite runs.
_TZ = timezone(timedelta(hours=-6))
_CLI_RUNNER = CliRunner()

#: The bytes the injected tile fetch serves. Any bytes will do -- the guard
#: cares where tiles land (``.cache/tiles/...``), not what they contain.
_TILE_PNG: Final[bytes] = b"\x89PNG\r\n\x1a\n"

#: Snapshot markers. A directory has no content to hash and a path that does not
#: exist has no state at all; giving both a distinct sentinel keeps the diff a
#: plain string comparison.
_DIRECTORY: Final[str] = "<directory>"
_ABSENT: Final[str] = "<absent>"

#: ``(table, key)`` pairs of settings that name a location fitdocs may write
#: into -- guard axis (b), the configured half of the permitted set. inbox
#: (task 5.2) registers its ``[inbox]`` intake and processed-files keys here,
#: and every registered entry point is checked against the widened set with
#: no other change to this module. A settings document with no ``[inbox]``
#: table (the ``sync``/``regen``/``load`` entry points' fixtures) still
#: resolves neither key, so the configured half degrades to empty for them --
#: see :func:`test_settings_without_an_inbox_table_configure_no_write_location`.
SETTINGS_LOCATION_KEYS: Final[tuple[tuple[str, str], ...]] = (
    ("inbox", "path"),
    ("inbox", "processed_dir"),
)

#: Data-root-relative files that are not owned paths (`layout.OWNED_PATHS`) but
#: are contract-named *shared* files fitdocs legitimately writes -- rewriting
#: only its own keys and preserving the rest, per the published ownership
#: contract's shared-file guarantee (Req 2.7), never a wholesale rewrite. This
#: is deliberately a **different set** from `OWNED_PATHS`: "owned" means
#: fitdocs may create/rewrite/delete a path on its own initiative, which is
#: false of `athlete.toml` (`fitdocs.load.profile.save_profile` reads the
#: existing file and only ever adds/updates the load-methodology keys it
#: knows about). Registering `load` as a writing entry point below requires
#: this set to exist -- `apply_load` writes `athlete.toml` via
#: `fitdocs.load.profile.save_profile` (`load/engine.py:385`) whenever a
#: prompted athlete field is accepted, and that write is not inside any
#: `OWNED_PATHS` prefix.
PERMITTED_SHARED_FILES: Final[tuple[str, ...]] = (ATHLETE_FILE,)


# --- the permitted set (axis b) ---------------------------------------------


def configured_locations(
    data_root: Path,
    keys: Sequence[tuple[str, str]] = SETTINGS_LOCATION_KEYS,
) -> tuple[Path, ...]:
    """Resolve every write location the settings under test configure (Req 7.5).

    Reads ``<data_root>/fitdocs.toml`` through the shared settings parse (absent
    file -> empty mapping) and resolves each string value named by ``keys``
    against the data root, absolute values being taken as-is. ``keys`` is a
    parameter rather than a constant so a test can exercise the mechanism with
    the shape a future table will use; the module-level default
    (:data:`SETTINGS_LOCATION_KEYS`) is what production settings configure today.
    """
    document = load_settings_document(data_root)
    resolved: list[Path] = []
    for table_name, key in keys:
        table = document.get(table_name)
        if not isinstance(table, dict):
            continue
        value = table.get(key)
        if not isinstance(value, str):
            continue
        resolved.append((data_root / value).resolve())
    return tuple(resolved)


def permitted_locations(
    data_root: Path, configured: Sequence[Path] = ()
) -> tuple[Path, ...]:
    """The permitted set: owned paths **union** shared files **union** configured
    locations.

    Three distinct grants make up the union, and the distinction between the
    first two is deliberate, not cosmetic: ``OWNED_PATHS`` is what the
    published contract calls fitdocs-owned (create/rewrite/delete at will);
    :data:`PERMITTED_SHARED_FILES` is what it calls merely *shared* (fitdocs
    writes only its own keys and preserves the rest) -- ``athlete.toml`` is
    the latter, never the former, so this guard grants it permission without
    ever adding it to ``OWNED_PATHS``. ``configured`` is whatever the settings
    under test grant (guard axis b), so a write into a configured intake
    directory is a pass rather than a failure and inbox never has to widen
    either fixed set to make its own tests green.
    """
    owned = tuple(data_root / path for path in OWNED_PATHS)
    shared = tuple(data_root / name for name in PERMITTED_SHARED_FILES)
    return owned + shared + tuple(configured)


# --- the snapshot diff -------------------------------------------------------


def _snapshot(root: Path) -> dict[str, str]:
    """State of every path under ``root``: content hash and mtime, or the dir marker.

    Files are keyed by their sandbox-relative POSIX path and valued by a content
    hash *and* modification time, so a modification is visible whether or not the
    bytes changed -- rewriting a file with identical content is still a write, and
    a guard that missed it would miss a run that clobbers a user's file with a
    copy of itself. Directories carry :data:`_DIRECTORY`, which makes their
    creation and deletion visible while the mtime bump a *permitted* child write
    causes on its parent is not treated as a change.
    """
    state: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        key = path.relative_to(root).as_posix()
        if path.is_dir():
            state[key] = _DIRECTORY
        else:
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            state[key] = f"{digest}:{path.stat().st_mtime_ns}"
    return state


def _touched(before: dict[str, str], after: dict[str, str]) -> tuple[str, ...]:
    """Sandbox-relative paths created, modified, or deleted between snapshots."""
    return tuple(
        sorted(
            key
            for key in set(before) | set(after)
            if before.get(key, _ABSENT) != after.get(key, _ABSENT)
        )
    )


def _inside(path: Path, location: Path) -> bool:
    """Is ``path`` the permitted ``location`` itself or anything beneath it?"""
    return path == location or location in path.parents


def assert_confined(
    sandbox: Path,
    permitted: Sequence[Path],
    before: dict[str, str],
    after: dict[str, str],
) -> None:
    """Assert nothing outside ``permitted`` changed between the two snapshots.

    The guard proper (Req 7.5): every created, modified, or deleted path must lie
    inside one of the permitted locations. The failure message names each stray
    path and the whole permitted set, so a regression points straight at the
    write site rather than at this assertion.
    """
    strays = [
        key
        for key in _touched(before, after)
        if not any(_inside(sandbox / key, location) for location in permitted)
    ]
    assert not strays, (
        f"wrote outside the permitted locations: {strays}; "
        f"permitted: {[str(location) for location in permitted]}"
    )


def _derived_guard_snapshot(
    root: Path, index_directory: Path
) -> dict[str, tuple[object, ...]]:
    """Inventory every non-index entry without following links.

    File bytes and lstat metadata catch content changes and same-byte rewrites.
    Directory mtimes are omitted because a legitimate index write changes the
    cache's ancestor timestamps; directory presence and mode remain pinned.
    """
    entries: dict[str, tuple[object, ...]] = {}

    def visit(directory: Path) -> None:
        for child in sorted(directory.iterdir()):
            if _inside(child, index_directory):
                continue
            relative = child.relative_to(root).as_posix()
            metadata = child.lstat()
            mode = metadata.st_mode
            if stat.S_ISLNK(mode):
                entries[relative] = (
                    "symlink",
                    os.readlink(child),
                    stat.S_IMODE(mode),
                    metadata.st_mtime_ns,
                )
            elif stat.S_ISDIR(mode):
                entries[relative] = ("directory", stat.S_IMODE(mode))
                visit(child)
            elif stat.S_ISREG(mode):
                entries[relative] = (
                    "file",
                    child.read_bytes(),
                    stat.S_IMODE(mode),
                    metadata.st_mtime_ns,
                )
            else:
                entries[relative] = (
                    "other",
                    stat.S_IFMT(mode),
                    stat.S_IMODE(mode),
                    metadata.st_mtime_ns,
                )

    visit(root)
    return entries


def _assert_derived_index_unchanged_outside_cache(
    before: dict[str, tuple[object, ...]],
    after: dict[str, tuple[object, ...]],
) -> None:
    """Require the derived-index pass to leave all non-cache entries intact."""
    changed = tuple(
        sorted(
            key for key in set(before) | set(after) if before.get(key) != after.get(key)
        )
    )
    assert not changed, (
        f"derived index changed data/source entries outside external index: {changed}"
    )


# --- the registered entry points (axis a) ------------------------------------


def _tiles(data_root: Path) -> TileSource:
    """A real :class:`TileStore` with an injected fetch: offline, and it caches.

    Using the real store (not a stub) is deliberate -- it exercises the tile
    cache writes under ``.cache/tiles/``, which are exactly the kind of
    out-of-the-way write the guard exists to police.
    """
    return TileStore(data_root, DEFAULT_TILE_SETTINGS, fetch=lambda _url: _TILE_PNG)


def _stage_sources(source_dir: Path) -> None:
    """Stage a representative ``.fit`` set: mapped run, no-GPS ride, strength."""
    fixtures = {
        "run.fit": builder.run_fit_bytes(),
        "ride.fit": builder.ride_fit_bytes(),
        "strength.fit": builder.strength_fit_bytes(),
    }
    source_dir.mkdir(parents=True, exist_ok=True)
    for name, data in fixtures.items():
        (source_dir / name).write_bytes(data)


def _nothing(data_root: Path, source_dir: Path) -> None:
    """No preparation: the entry point runs against a fresh data root."""


def _sync_once_then_drop_a_document(data_root: Path, source_dir: Path) -> None:
    """Populate the data root, then delete one document so ``regen`` rebuilds it.

    Documents are derived artifacts, so removing one leaves an archived source
    referenced by nothing -- the state in which regeneration genuinely writes,
    which keeps the guard from passing vacuously over a run that produced
    byte-identical output.
    """
    _run_sync(data_root, source_dir)
    docs = sorted((data_root / WORKOUTS_DIR).glob("*.md"))
    docs[0].unlink()


def _run_sync(data_root: Path, source_dir: Path) -> None:
    """The ``sync`` entry point, driven exactly as the CLI drives it."""
    sync(
        source_dir,
        data_root,
        athlete=load_athlete_inputs(data_root),
        tz=_TZ,
        tiles=_tiles(data_root),
    )


def _prepare_index_build(data_root: Path, source_dir: Path) -> None:
    _stage_sources(source_dir)
    _run_sync(data_root, source_dir)


def _run_cli_index(data_root: Path, source_dir: Path) -> None:
    index_dir = source_dir.parent / "index-cache"
    with patch.dict(os.environ, {"FITDOCS_INDEX_DIR": str(index_dir)}):
        result = _CLI_RUNNER.invoke(app, ["index", "--out", str(data_root)])
    assert result.exit_code == 0, result.output


def _prepare_sync_with_index(data_root: Path, source_dir: Path) -> None:
    _prepare_index_build(data_root, source_dir)
    _run_cli_index(data_root, source_dir)
    # A new source makes the measured CLI sync write a new workout and refresh
    # the already-populated external index.
    (source_dir / "hike.fit").write_bytes(builder.hike_fit_bytes())


def _run_cli_sync_with_index(data_root: Path, source_dir: Path) -> None:
    index_dir = source_dir.parent / "index-cache"
    with (
        patch.dict(os.environ, {"FITDOCS_INDEX_DIR": str(index_dir)}),
        patch("fitdocs.tiles._default_fetch", lambda _url: _TILE_PNG),
    ):
        result = _CLI_RUNNER.invoke(
            app, ["sync", str(source_dir), "--out", str(data_root)]
        )
    assert result.exit_code == 0, result.output


def _wrote_index_file(touched: Sequence[str]) -> bool:
    return any(path.endswith("/index.duckdb") for path in touched)


def _wrote_document_and_index(touched: Sequence[str]) -> bool:
    return _wrote_index_file(touched) and any(
        path.startswith("data/workouts/") and path.endswith(".md") for path in touched
    )


def _run_regen(data_root: Path, source_dir: Path) -> None:
    """The ``regen`` entry point, driven exactly as the CLI drives it."""
    regen(
        data_root,
        athlete=load_athlete_inputs(data_root),
        tz=_TZ,
        tiles=_tiles(data_root),
    )


def _stage_drain_inbox(data_root: Path, source_dir: Path) -> None:
    """Prepare a fresh data root for the ``drain`` entry point (inbox Req
    8.5): a settings file configuring the move disposition. No
    ``fitdocs.toml``-adjacent directory is created here -- neither the inbox
    nor the processed-files destination exists yet, so the measured run is
    what creates *both* (``prepare_inbox``, Req 1.5, 6.7) as well as the
    tool-state directory (a fresh quarantine entry for the undecodable file,
    Req 5.1). ``source_dir`` is unused: a drain reads only the configured
    inbox, never the sibling source directory the other entry points stage.
    """
    settings_path(data_root).write_text(
        '[inbox]\npath = "inbox"\ndisposition = "move"\n'
        'processed_dir = "processed"\nsettle_seconds = 0\n',
        encoding="utf-8",
    )


def _run_drain(data_root: Path, source_dir: Path) -> None:
    """The ``drain`` entry point, driven through the same pre-flight steps
    the CLI's no-argument ``sync`` performs: parse the settings document
    once, project ``[inbox]``, resolve/create the inbox and processed-files
    directories, load the quarantine record, then drain. Since ``prepare``
    leaves the inbox absent, one processable file and one undecodable one
    are staged into it only once ``prepare_inbox`` has created it here --
    keeping the inbox's own creation inside the measured run. The move
    disposition then relocates the processable file out of the inbox into
    the freshly created processed directory, and the undecodable file's
    source-level failure is recorded into the freshly created quarantine
    record under the tool-state directory -- exercising every write this
    guard's non-vacuity and confinement assertions check (inbox Req 6.2,
    8.5).
    """
    document = load_settings_document(data_root)
    settings = load_inbox_settings(document, data_root=data_root)
    paths = prepare_inbox(data_root, settings)
    (paths.inbox / "good.fit").write_bytes(builder.run_fit_bytes())
    (paths.inbox / "bad.fit").write_bytes(builder.non_fit_bytes())
    quarantine = load_quarantine(data_root)
    drain(
        paths.inbox,
        data_root,
        settings=settings,
        processed_dir=paths.processed,
        quarantine=quarantine,
        athlete=load_athlete_inputs(data_root),
        tz=_TZ,
        tiles=_tiles(data_root),
        sleep=lambda _seconds: None,
    )


@dataclass
class _StubRunSession:
    """Answers exactly what one ``ComputingCalculator`` compute dialog asks
    (:mod:`tests.load.conftest`, task 1.1), for an EMPTY starting profile, over
    ``builder.run_fit_bytes()``.

    Scoped to this guard's one purpose: making the ``load`` entry point
    genuinely write ``athlete.toml`` -- via
    :func:`fitdocs.load.profile.save_profile`'s immediate-persistence path
    (Req 3.3) -- so the confinement guard exercises the very write this task
    registers ``load`` to police, rather than passing vacuously. The
    ride/strength documents this guard's shared fixtures also stage are
    unsupported modalities for the stub and never consult these queues at all.
    """

    _ints: list[int]
    _confirms: list[bool]
    _floats: list[float]
    _chooses: list[int]

    def confirm(self, question: str, *, default: bool = True) -> bool | None:
        return self._confirms.pop(0)

    def ask_int(
        self,
        question: str,
        *,
        minimum: int | None = None,
        maximum: int | None = None,
        default: int | None = None,
    ) -> int | None:
        return self._ints.pop(0)

    def ask_float(
        self,
        question: str,
        *,
        minimum: float | None = None,
        maximum: float | None = None,
        default: float | None = None,
    ) -> float | None:
        return self._floats.pop(0)

    def choose(
        self,
        question: str,
        options: Sequence[str],
        *,
        default_index: int | None = None,
    ) -> int | None:
        return self._chooses.pop(0)

    def inform(self, message: str) -> None:
        pass


def _load_session() -> InteractionSession:
    return _StubRunSession(
        _ints=[7],  # the stub's one declared field ("level")
        _confirms=[True],  # confirm the computed result
        _floats=[],
        _chooses=[],
    )


def _run_load(data_root: Path, source_dir: Path) -> None:
    """The ``load`` entry point, driven exactly as the CLI drives it.

    fitdocs ships no calculator (Amendment 2), so ``ComputingCalculator`` is
    registered around the call -- isolated from whatever else is registered on
    import -- so the pass has exactly one supporter for the run document's
    modality.

    Writes both a workout document (the ``run`` document's ``load`` region and
    its three frontmatter keys) and ``athlete.toml`` (via
    :func:`fitdocs.load.engine.apply_load`'s field-collection persistence) --
    the second of which is not inside any ``OWNED_PATHS`` prefix, which is
    exactly why :data:`PERMITTED_SHARED_FILES` exists.
    """
    saved = dict(registry._REGISTRY)
    registry._REGISTRY.clear()
    registry.register(ComputingCalculator())
    try:
        apply_load(data_root, session=_load_session())
    finally:
        registry._REGISTRY.clear()
        registry._REGISTRY.update(saved)


def _stage_history_pages(data_root: Path, source_dir: Path) -> None:
    """A real, minimal workout document recording a load under a real
    frontmatter fence and real ``fitdocs.contract`` vocabulary (load-history
    spec, task 5.4) -- the same construction ``tests/history/test_engine.py``'s
    own ``_page`` fixture builder uses, restated here rather than imported so
    this guard's own fixtures never depend on another test module. Without a
    page recording a load the history pass takes the empty-archive path
    (Req 1.10) and writes nothing at all, which would make the measured run
    below vacuous. ``source_dir`` is unused -- the history pass reads only
    already-generated workout documents, never a ``.fit`` source (Req 1.1).
    """
    workouts_dir = data_root / WORKOUTS_DIR
    workouts_dir.mkdir(parents=True, exist_ok=True)
    (workouts_dir / "confinement-fixture.md").write_text(
        "\n".join(
            [
                "---",
                "title: Confinement Fixture",
                "type: workout",
                'date: "2024-01-01"',
                "load_value: 100",
                "load_methodology: threshold",
                "---",
                "",
                "# Confinement Fixture",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _run_history(data_root: Path, source_dir: Path) -> None:
    """The ``history`` entry point, driven exactly as the CLI drives it
    (load-history spec, task 5.4; Req 7.4, 7.5)."""
    run_history(data_root)


def _wrote_a_workout_document(touched: Sequence[str]) -> bool:
    """The default non-vacuity check every entry point but ``history`` uses:
    the measured run produced a real *workout document* under ``workouts/``
    (the ownership declaration excluded, since every entry point writes it
    on every run regardless of whether any source was processed)."""
    return any(
        key.startswith(f"data/{WORKOUTS_DIR}/")
        and key.endswith(".md")
        and not key.endswith(f"/{DECLARATION_FILENAME}")
        for key in touched
    )


def _stage_tagged_race(data_root: Path, source_dir: Path) -> None:
    """Stage one tagged, dated running race with a resolvable archive (Req
    1.10, 9.4, 9.5, 10.3, 10.8): a distance/time pair (10000 m, 2400 s) well
    inside Riegel's validity window, which is what makes the measured
    ``derive-benchmarks`` run below actually accept a candidate and reach the
    reconciling write, rather than only exercising the decline path -- a
    guard that never wrote would pass vacuously. ``source_dir`` is unused:
    this entry point reads only the data root, never a sibling source
    directory of raw ``.fit`` files, mirroring ``drain``'s prepare.
    """
    data = builder.run_fit_bytes()
    sha256 = hashlib.sha256(data).hexdigest()
    archive_dir = data_root / ARCHIVE_DIR
    archive_dir.mkdir(parents=True, exist_ok=True)
    (archive_dir / f"{sha256}.fit").write_bytes(data)

    workouts = data_root / WORKOUTS_DIR
    workouts.mkdir(parents=True, exist_ok=True)
    (workouts / "race.md").write_text(
        "---\n"
        "type: workout\n"
        'date: "2024-05-01"\n'
        "effort: race\n"
        "effort_distance_m: 10000\n"
        "effort_time_s: 2400\n"
        "sources:\n"
        f"  - {ARCHIVE_DIR}/{sha256}.fit\n"
        "---\n"
        "\nBody.\n",
        encoding="utf-8",
    )


def _run_derive_benchmarks(data_root: Path, source_dir: Path) -> None:
    """The ``derive-benchmarks`` entry point, driven exactly as the CLI
    drives it: one call over the data root, no dry run (Req 1.10).

    Writes only ``athlete.toml`` (via
    :func:`fitdocs.load.profile.save_profile`'s reconciling write) -- never a
    workout document (``tasks.md``'s hard rule for every task: "no document
    is written by anything in this plan") -- which is exactly why this entry
    point
    reuses :data:`PERMITTED_SHARED_FILES` rather than adding a location of
    its own.
    """
    derive_benchmarks(data_root)


def _wrote_only_the_athlete_profile(touched: Sequence[str]) -> bool:
    """``derive-benchmarks``'s own non-vacuity predicate (Req 1.10, 9.4): the
    touched set is *exactly* ``{"data/athlete.toml"}`` -- no more, no less.
    Equality rather than membership pins two things in one clause: the run
    really wrote (never calling ``save_profile`` leaves ``touched`` empty and
    fails), and it wrote *nothing but* the profile (a stray lock file, a
    stray cache entry, or a workout document alongside it also fails, because
    the touched set is then a strict superset of the singleton).
    """
    return tuple(touched) == (f"data/{ATHLETE_FILE}",)


#: One small, valid plan source -- the same shape
#: `tests/plans/fixtures/minimal.toml` holds, restated here rather than read
#: from that fixture file so this guard's own fixture never depends on
#: another test module (mirrors :func:`_stage_history_pages`'s own choice to
#: restate rather than import). One workout row is enough to make the
#: measured `plan` run genuinely write a block page and one planned-workout
#: page, rather than passing vacuously over a plan with no rows.
#:
#: Also carries one ``[[amendment]]`` (an ``update`` op) and one
#: ``[[override]]`` (round-1 review recommendation, item 10): Req 3.9's own
#: negative claim -- "never itself append to a source" -- is otherwise
#: exercised only by a source with *no* amendment or override at all, which
#: cannot distinguish "the pass never writes here" from "the pass never had
#: anything to append in the first place". Both post-date the one workout
#: row (2026-02-02), so both are valid as of their own dates.
_PLAN_SOURCE_TEXT: Final[str] = (
    'title = "Confinement Fixture Block"\n'
    "starts = 2026-02-02\n"
    "ends = 2026-02-08\n"
    'goal = "A minimal valid plan source for the confinement guard."\n'
    "mesocycle_days = 7\n"
    "\n"
    "[[workout]]\n"
    'id = "w1-mon"\n'
    "date = 2026-02-02\n"
    'sport = "Run"\n'
    'title = "Easy run"\n'
    'summary = "Zone 2"\n'
    'prescription = "30 minutes easy."\n'
    "\n"
    "[[amendment]]\n"
    "date = 2026-02-03\n"
    'reason = "Confinement guard fixture amendment"\n'
    "\n"
    "[[amendment.update]]\n"
    'id = "w1-mon"\n'
    'prescription = "35 minutes easy."\n'
    "\n"
    "[[override]]\n"
    "date = 2026-02-04\n"
    'id = "w1-mon"\n'
    "skipped = true\n"
    'reason = "Confinement guard fixture override"\n'
)

#: The plan source's own report-relative filename under the default plan
#: directory -- used both to stage it and, in the negative-half test, to
#: assert its bytes are unchanged after the run.
_PLAN_SOURCE_NAME: Final[str] = "confinement-fixture.toml"


def _stage_plan_source(data_root: Path, source_dir: Path) -> None:
    """Stage one small valid plan source under the *default* plan directory
    inside the data root (training-blocks task 4.4; Req 1.2, 7.2, 7.7).

    The default location, so no ``[plans]`` table and no
    :data:`SETTINGS_LOCATION_KEYS` entry are needed -- the plan pass never
    writes under its own source directory (design.md, "PlanEngine": every
    write path is composed from the layout helpers or the declaration
    refresh, never from the resolved source directory), so this guard
    measures that promise directly rather than granting the location.
    ``source_dir`` is unused: the plan pass reads only the data root's own
    configured (or default) plan directory, never the sibling ``.fit``
    source directory the other entry points stage.
    """
    plans_dir = data_root / DEFAULT_PLANS_DIR
    plans_dir.mkdir(parents=True, exist_ok=True)
    (plans_dir / _PLAN_SOURCE_NAME).write_text(_PLAN_SOURCE_TEXT, encoding="utf-8")


def _run_plan(data_root: Path, source_dir: Path) -> None:
    """The ``plan`` entry point, driven directly through
    :func:`fitdocs.plans.run_plan` -- the plan CLI command does not exist
    yet (task 4.3 owns ``cli.py`` and is not a dependency of this task), so
    this registers the engine function itself rather than a CLI
    invocation, exactly as :func:`_run_history` registers
    :func:`fitdocs.history.run_history` directly rather than going through
    the CLI."""
    run_plan(data_root)


def _wrote_a_block_page(touched: Sequence[str]) -> bool:
    """The ``plan`` entry point's own non-vacuity check (Req 1.2, 8.4):
    the measured run wrote *the block page itself*, named exactly by the
    source's own block id -- ``fitdocs.plans.engine`` composes it as
    ``blocks/<block_id>.md`` (``layout.block_doc_path``), and the source
    staged by :func:`_stage_plan_source` names its block ``confinement-
    fixture`` (its filename's stem, :data:`_PLAN_SOURCE_NAME`).

    Deliberately **not** "any ``.md`` under ``blocks/``" (round-1 review
    fix, item 6): that broader check would also accept a run that wrote
    only the planned-workout page and silently skipped the block page
    itself -- `run_plan`'s own write order (design.md, "PlanEngine":
    planned pages before the block page) makes that a real, distinguishable
    outcome, not a hypothetical one, and this check is written to require
    the specific artifact it claims to observe.

    ``blocks/AGENTS.md`` needs no explicit exclusion here (unlike
    :func:`_wrote_a_workout_document`'s): ``ensure_declarations`` is called
    only when at least one block is *valid* (Req 8.10; ``fitdocs.plans.engine
    .run_plan``, ``if valid_blocks: ensure_declarations(...)``), so it is
    never a stand-in non-vacuity signal in the first place -- a run over an
    all-invalid source creates no ``blocks/`` directory at all, and the one
    path this check requires is the block page, never the declaration.
    """
    block_id = Path(_PLAN_SOURCE_NAME).stem
    return f"data/{BLOCKS_DIR}/{block_id}.md" in touched


# --- the reconcile entry point (plan-resolution task 3.3; Req 4.6, 8.8) -----

#: The reconcile entry point's own small, valid plan source -- one ``Run``
#: row dated ``_RECONCILE_ROW_DATE``, deliberately simpler than
#: :data:`_PLAN_SOURCE_TEXT` (no amendment, no override: this entry point's
#: whole point is a resolved match, not the plan pass's own write shape,
#: which :func:`_wrote_a_block_page`'s sibling test already covers).
_RECONCILE_ROW_DATE: Final[date] = date(2026, 3, 2)
_RECONCILE_BLOCK_SOURCE_TEXT: Final[str] = (
    'title = "Reconcile Confinement Fixture Block"\n'
    "starts = 2026-03-02\n"
    "ends = 2026-03-08\n"
    'goal = "A minimal valid plan source for the reconcile confinement guard."\n'
    "mesocycle_days = 7\n"
    "\n"
    "[[workout]]\n"
    'id = "w1-mon"\n'
    "date = 2026-03-02\n"
    'sport = "Run"\n'
    'title = "Easy run"\n'
    'summary = "Zone 2"\n'
    'prescription = "30 minutes easy."\n'
)

#: The plan source's own report-relative filename -- also the resolved
#: block id (:data:`_wrote_a_reconciled_block`'s own use).
_RECONCILE_BLOCK_SOURCE_NAME: Final[str] = "reconcile-confinement-fixture.toml"

#: One synthetic *generated* workout page, dated the same day as the plan
#: row above, sport ``Run``, with a load -- a real match candidate
#: (``fitdocs.plans.matching.is_candidate``: equal dates, equal sports) so
#: the measured run's resolver actually matches this row rather than
#: leaving it ``not logged`` (which would make the guard's stronger
#: non-vacuity predicate, :func:`_wrote_a_reconciled_block`, vacuously
#: false over a run that wrote a block page with no real reconciliation in
#: it). The same minimal frontmatter shape :func:`_stage_history_pages`
#: restates for its own entry point, restated here rather than imported for
#: the same reason that function's own docstring gives.
_RECONCILE_WORKOUT_STEM: Final[str] = "reconcile-confinement-workout"


def _stage_plan_and_logged_page(data_root: Path, source_dir: Path) -> None:
    """Stage one valid plan source under the default plan directory and one
    matching, already-generated workout page under ``workouts/`` (Req 4.6,
    8.8) -- the state the ``reconcile`` entry point's measured run
    resolves. ``source_dir`` is unused, mirroring :func:`_stage_plan_source`
    and :func:`_stage_history_pages`: the reconciling pass reads only the
    data root's plan directory and its already-generated workout pages,
    never a sibling ``.fit`` source directory.
    """
    plans_dir = data_root / DEFAULT_PLANS_DIR
    plans_dir.mkdir(parents=True, exist_ok=True)
    (plans_dir / _RECONCILE_BLOCK_SOURCE_NAME).write_text(
        _RECONCILE_BLOCK_SOURCE_TEXT, encoding="utf-8"
    )

    workouts_dir = data_root / WORKOUTS_DIR
    workouts_dir.mkdir(parents=True, exist_ok=True)
    (workouts_dir / f"{_RECONCILE_WORKOUT_STEM}.md").write_text(
        "\n".join(
            [
                "---",
                "title: Reconcile Confinement Fixture",
                "type: workout",
                f'date: "{_RECONCILE_ROW_DATE.isoformat()}"',
                "sport: Run",
                "load_value: 100",
                "load_methodology: threshold",
                "---",
                "",
                "# Reconcile Confinement Fixture",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _run_reconcile(data_root: Path, source_dir: Path) -> None:
    """The ``reconcile`` entry point, driven directly through
    :func:`fitdocs.plans.reconcile.run_reconcile` -- the guard's
    ``(data_root, source_dir)`` signature is wider than this pass needs
    (mirrors :func:`_run_plan`, :func:`_run_history`); ``source_dir`` is
    ignored. ``today`` is fixed a week after the staged row's own date, well
    clear of it either way this entry point's resolver reads it, so the row
    resolves the same regardless of exactly how ``today`` participates in
    matching."""
    run_reconcile(data_root, today=_RECONCILE_ROW_DATE + timedelta(days=7))


def _wrote_a_reconciled_block(touched: Sequence[str]) -> bool:
    """The ``reconcile`` entry point's own non-vacuity check (Req 4.6,
    8.8), deliberately **stronger** than :func:`_wrote_a_block_page`: both
    the block page *and* the row's own planned page must be in ``touched``
    (``layout.planned_doc_path``, ``blocks/<block_id>/<row_id>.md``) --
    `run_plan` writes a planned page for *every* current row regardless of
    what the resolver returns (wave 1's own write shape), so
    :func:`_wrote_a_block_page`'s single-page check cannot tell a run whose
    resolver actually reconciled the row from one that returned
    ``fitdocs.plans.resolution.unresolved()`` for it; requiring both pages
    does not discriminate that either, but the sibling behavioural test
    below (:func:`test_reconcile_entry_point_writes_a_resolved_match`)
    reads the block page's own cell text to close that last gap."""
    block_id = Path(_RECONCILE_BLOCK_SOURCE_NAME).stem
    row_id = "w1-mon"
    block_page = f"data/{BLOCKS_DIR}/{block_id}.md" in touched
    planned_page = f"data/{BLOCKS_DIR}/{block_id}/{row_id}.md" in touched
    return block_page and planned_page


def _wrote_the_history_document(touched: Sequence[str]) -> bool:
    """The ``history`` entry point's own non-vacuity check (load-history
    spec, task 5.4): its measured run wrote the one history document it
    owns. Deliberately distinct from :func:`_wrote_a_workout_document` --
    the history pass writes no ``workouts/*.md`` document at all (Req 7.5),
    so reusing that check here would fail on every genuinely successful run
    and the guard would never be able to tell a real write from a silent
    no-op for this entry point."""
    return f"data/{HISTORY_DIR}/{HISTORY_DOC_STEM}.md" in touched


#: The two page stems of the ``sync-base-change`` entry point's fixture under
#: the pinned ``_TZ``: the older export's page and the corrected start's page.
_BASE_CHANGE_OLD_STEM: Final[str] = "2043-11-13-run-1713"
_BASE_CHANGE_NEW_STEM: Final[str] = "2043-11-13-run-1613"


def _stage_base_change(data_root: Path, source_dir: Path) -> None:
    """Sync the older export of a re-exported session, then stage the newer one.

    The newer export corrects the start by an hour, so syncing it renames the
    page (activity-identity Req 6.2). It waits in its own directory beside the
    sandbox's ``src`` (staged before the snapshot, so its creation is not a
    measured write); the older export goes through a throwaway directory.
    """
    older, newer = identity_fixtures.healthfit_reexport_pair()
    first = source_dir.parent / "older-export"
    first.mkdir()
    (first / "older.fit").write_bytes(older.data)
    sync(
        first,
        data_root,
        athlete=load_athlete_inputs(data_root),
        tz=_TZ,
        tiles=_tiles(data_root),
    )
    second = source_dir.parent / "newer-export"
    second.mkdir()
    (second / "newer.fit").write_bytes(newer.data)


def _run_sync_base_change(data_root: Path, source_dir: Path) -> None:
    """``sync`` over the newer export: the page is renamed (Req 6.2)."""
    _run_sync(data_root, source_dir.parent / "newer-export")


def _renamed_a_workout_document(touched: Sequence[str]) -> bool:
    """The ``sync-base-change`` entry point's own non-vacuity check: the old
    page's document was deleted and the new one created. The prepare step
    creates the old document, and nothing else names either path, so a run
    that touches both did both -- a run that only rewrote a page in place
    (or wrote nothing) touches at most one of them.
    """
    old = f"data/{WORKOUTS_DIR}/{_BASE_CHANGE_OLD_STEM}.md"
    new = f"data/{WORKOUTS_DIR}/{_BASE_CHANGE_NEW_STEM}.md"
    return old in touched and new in touched


# --- the pull entry point (connectors task 6.3; Req 5.9, 13.5, 15.3) --------

#: A fixed point in time for every ``run_pull``/``run_connect`` call this
#: module makes -- never the real clock (this module imports no clock call,
#: matching design.md's "no clock call inside the package" rule for the
#: package itself, kept here as the same discipline for its own tests).
_PULL_NOW: Final[datetime] = datetime(2026, 6, 1, tzinfo=UTC)

#: The instance name :func:`_stage_pull_folder` configures -- also the
#: ledger's and delivery subdirectory's own name
#: (:data:`fitdocs.layout.connector_ledger_path`,
#: ``connectors/delivery.py``'s ``inbox / instance`` convention).
_PULL_INSTANCE_NAME: Final[str] = "src"


def _socket_raises(*args: object, **kwargs: object) -> NoReturn:
    raise RuntimeError(
        "test_confinement's connector cases must not open a real network socket"
    )


def _raise_if_transport_called(request: object, timeout: float) -> NoReturn:
    """A :data:`~fitdocs.connectors.http.Transport` that raises the moment it
    is called -- the folder connector is network-free (Req 13.9), so the
    measured ``pull`` run below must never reach it. The raise itself is
    absorbed by the pull engine's per-instance error isolation (it becomes a
    failed/errored instance report, not a propagated exception); what
    actually fails the test is the call recorded by the wrapper in
    :func:`_run_pull`, asserted empty after the run.
    """
    raise AssertionError(
        "pull entry point's confinement run reached the transport -- the "
        "folder connector must never make a network request"
    )


def _stage_pull_folder(data_root: Path, source_dir: Path) -> None:
    """Prepare a fresh data root for the ``pull`` entry point (design.md
    "ConfinementRegistration"): an ``[inbox]`` table and one ``folder``
    connector instance (:data:`_PULL_INSTANCE_NAME`) whose configured source
    *is* the sandbox's own staged source directory -- the same ``.fit``
    fixtures :func:`_stage_sources` already staged for every other entry
    point, reused here rather than staged a second time. ``settle_seconds =
    0`` on both tables is the design's stated configuration for this guard,
    not a value chosen to make the run deterministic by timing: the measured
    run is deterministic because the ``sleep`` seam :func:`_run_pull` passes
    to :func:`~fitdocs.connectors.pull.run_pull` is an injected no-op, so the
    ``[inbox]`` table's ``settle_seconds`` value has no effect on a pull
    (only on inbox's own settle wait, a different code path).
    """
    settings_path(data_root).write_text(
        "\n".join(
            [
                "[inbox]",
                'path = "inbox"',
                "settle_seconds = 0",
                "",
                f"[connectors.{_PULL_INSTANCE_NAME}]",
                'connector = "folder"',
                f'path = "{source_dir.as_posix()}"',
                "settle_seconds = 0",
                "",
            ]
        ),
        encoding="utf-8",
    )


def _run_pull(data_root: Path, source_dir: Path) -> None:
    """The ``pull`` entry point, driven exactly as design.md's
    ConfinementRegistration states and as ``cli.py``'s own connector commands
    order it: settings -> inbox validation -> connector instances -> inbox
    creation -> the pull engine, with a transport that raises if called (the
    folder connector reads only the local filesystem, Req 13.9).

    This module sits outside ``tests/connectors/conftest.py``'s autouse
    fixtures (that conftest's own docstring), so the environment isolation
    and the socket guard every connector test gets for free are applied
    here directly -- in a throwaway directory created and torn down inside
    this call, outside the sandbox this guard snapshots, so the isolation
    itself is never mistaken for a measured write.
    """
    monkeypatch = pytest.MonkeyPatch()
    try:
        with tempfile.TemporaryDirectory() as base_dir:
            isolate_connector_environment(monkeypatch, Path(base_dir))
            monkeypatch.setattr(socket, "socket", _socket_raises)

            calls: list[object] = []

            def transport(request: object, timeout: float) -> NoReturn:
                calls.append(request)
                _raise_if_transport_called(request, timeout)

            document = load_settings_document(data_root)
            inbox_settings = load_inbox_settings(document, data_root=data_root)
            validated = validate_inbox_paths(data_root, inbox_settings)
            context = SettingsContext(
                data_root=data_root, inbox=validated.inbox_resolved
            )
            instances = load_connectors_settings(
                document, settings_file=settings_path(data_root), context=context
            )
            inbox_paths = create_inbox_paths(validated)
            report = run_pull(
                data_root,
                instances,
                inbox=inbox_paths.inbox,
                store=None,
                transport=transport,
                options=PullOptions(since=None, dry_run=False),
                environ={},
                now=lambda: _PULL_NOW,
                sleep=lambda seconds: None,
                redactor=Redactor(),
            )
    finally:
        monkeypatch.undo()

    assert calls == [], f"pull reached the transport: {calls}"
    (instance_report,) = report.instances
    assert instance_report.error is None, instance_report.error
    assert instance_report.failed == (), instance_report.failed
    assert instance_report.deferred == (), instance_report.deferred


def _wrote_a_ledger_and_a_delivery(touched: Sequence[str]) -> bool:
    """The ``pull`` entry point's own non-vacuity check (Req 5.9, 13.5,
    15.3): the measured run wrote the instance's own ledger
    (:data:`~fitdocs.layout.CONNECTOR_STATE_DIR`) *and* delivered at least
    one ``.fit`` file into its own inbox subdirectory
    (``connectors/delivery.py``'s ``inbox / instance`` convention) --
    requiring both keeps a run that only ever saved an empty ledger (no
    activity actually delivered) from passing vacuously.
    """
    ledger_touched = f"data/{CONNECTOR_STATE_DIR}/{_PULL_INSTANCE_NAME}.toml" in touched
    delivery_touched = any(
        key.startswith(f"data/inbox/{_PULL_INSTANCE_NAME}/") and key.endswith(".fit")
        for key in touched
    )
    return ledger_touched and delivery_touched


@dataclass(frozen=True)
class EntryPoint:
    """One registered writing entry point -- guard axis (a).

    ``prepare`` brings the data root to the state the entry point runs against
    and is executed *before* the snapshot, so its writes are not measured;
    ``run`` performs the measured run. Both take ``(data_root, source_dir)``,
    a signature wide enough for an ingestion entry point that reads a staged
    directory as well as for one that reads only the data root. ``non_vacuous``
    is the entry point's own proof that its measured run actually wrote
    something observable (load-history task 5.4): every entry point before
    ``history`` writes a workout document, so :func:`_wrote_a_workout_document`
    is the default every existing registration keeps without change; the
    ``history`` pass writes no such document at all (Req 7.5), so it supplies
    :func:`_wrote_the_history_document` instead.
    """

    id: str
    prepare: Callable[[Path, Path], None]
    run: Callable[[Path, Path], None]
    non_vacuous: Callable[[Sequence[str]], bool] = _wrote_a_workout_document


# analytics-derived task 5.4: the full derived fixture includes composed pages,
# benchmark entries, recorded loads and plan sources so every derived table has
# rows when the CLI's registered producers are exercised.
def _prepare_derived_index(data_root: Path, source_dir: Path) -> None:
    import shutil

    from tests.index.derived.conftest import build_fixture_root

    build_fixture_root(data_root, composed=True)
    fixture_source = data_root / "composed-source"
    shutil.copytree(fixture_source, source_dir, dirs_exist_ok=True)
    sync(
        source_dir,
        data_root,
        athlete=load_athlete_inputs(data_root),
        tz=_TZ,
        tiles=_tiles(data_root),
    )


_DERIVED_INDEX_DATABASE: Path | None = None


def _run_cli_derived_index(data_root: Path, source_dir: Path) -> None:
    global _DERIVED_INDEX_DATABASE
    from fitdocs.index.location import resolve_index_location
    from tests.index.derived.conftest import TODAY

    index_dir = source_dir.parent / "derived-index-cache"

    _DERIVED_INDEX_DATABASE = resolve_index_location(
        data_root, {"FITDOCS_INDEX_DIR": str(index_dir)}, source_dir.parent
    ).database
    with (
        patch.dict(os.environ, {"FITDOCS_INDEX_DIR": str(index_dir)}),
        patch("fitdocs.cli._today", lambda: TODAY),
    ):
        result = _CLI_RUNNER.invoke(app, ["index", "--out", str(data_root)])
    assert result.exit_code == 0, result.output


def _derived_tables_populated(touched: Sequence[str]) -> bool:
    from fitdocs.index.store import open_index

    table_names = (
        "mean_max",
        "load_series",
        "daily_load",
        "weekly_load",
        "benchmarks",
        "benchmark_periods",
        "blocks",
        "mesocycles",
        "planned_workouts",
        "planned_workout_pages",
        "unplanned_pages",
    )
    if not any(relative.endswith("/index.duckdb") for relative in touched):
        return False
    if _DERIVED_INDEX_DATABASE is None:
        return False
    with open_index(_DERIVED_INDEX_DATABASE, read_only=True) as connection:
        counts = {
            name: connection.execute(f'SELECT count(*) FROM "{name}"').fetchall()[0][0]
            for name in table_names
        }
    assert all(isinstance(count, int) and count > 0 for count in counts.values()), (
        counts
    )
    return True


#: Every fitdocs entry point that writes into the data root (Req 7.6).
WRITING_ENTRY_POINTS: Final[tuple[EntryPoint, ...]] = (
    EntryPoint(id="sync", prepare=_nothing, run=_run_sync),
    EntryPoint(
        id="index",
        prepare=_prepare_index_build,
        run=_run_cli_index,
        non_vacuous=_wrote_index_file,
    ),
    EntryPoint(
        id="sync-with-index",
        prepare=_prepare_sync_with_index,
        run=_run_cli_sync_with_index,
        non_vacuous=_wrote_document_and_index,
    ),
    EntryPoint(id="regen", prepare=_sync_once_then_drop_a_document, run=_run_regen),
    EntryPoint(id="load", prepare=_run_sync, run=_run_load),
    EntryPoint(id="drain", prepare=_stage_drain_inbox, run=_run_drain),
    # Disclosure (round-2 remediation): `EntryPoint.non_vacuous` did not
    # exist before this history registration. It was added specifically
    # because the history pass writes no workout document at all (Req
    # 7.5); the old hard-coded `_wrote_a_workout_document` check reds on
    # every genuinely successful history run, so the field-with-default was
    # introduced to let `history` supply its own check without changing
    # any other registration's behavior. This shared-file change (an
    # addition to `EntryPoint`, not the `history` entry itself) was logged
    # to the agent log by the controller.
    EntryPoint(
        id="history",
        prepare=_stage_history_pages,
        run=_run_history,
        non_vacuous=_wrote_the_history_document,
    ),
    EntryPoint(
        id="derive-benchmarks",
        prepare=_stage_tagged_race,
        run=_run_derive_benchmarks,
        non_vacuous=_wrote_only_the_athlete_profile,
    ),
    # training-blocks task 4.4: the plan pass, registered against the engine
    # function directly (`fitdocs.plans.run_plan`) rather than the CLI --
    # the `plan` command does not exist in this tree (task 4.3, not a
    # dependency of this one). No SETTINGS_LOCATION_KEYS entry: the pass
    # writes only into `blocks/` (already in OWNED_PATHS), never under the
    # resolved plan-source directory.
    EntryPoint(
        id="plan",
        prepare=_stage_plan_source,
        run=_run_plan,
        non_vacuous=_wrote_a_block_page,
    ),
    # plan-resolution task 3.3: the reconciling pass, registered against the
    # engine function directly (`fitdocs.plans.reconcile.run_reconcile`) --
    # no CLI wiring is a dependency of this task (that is task 3.2's own,
    # parallel task). No SETTINGS_LOCATION_KEYS entry: like `plan`, this
    # pass writes only into `blocks/` (already in OWNED_PATHS).
    EntryPoint(
        id="reconcile",
        prepare=_stage_plan_and_logged_page,
        run=_run_reconcile,
        non_vacuous=_wrote_a_reconciled_block,
    ),
    # activity-identity task 4.2: a sync whose run renames a page (a session-UUID
    # re-export whose corrected start changes the name), removing its old chart
    # and moving its document: the deletes and the move are what this guard
    # must see stay inside `workouts/`.
    EntryPoint(
        id="sync-base-change",
        prepare=_stage_base_change,
        run=_run_sync_base_change,
        non_vacuous=_renamed_a_workout_document,
    ),
    # connectors task 6.3: the pull engine, driven directly (the CLI's own
    # `pull` command is task 5.2, not a dependency of this one -- mirrors
    # `plan` and `reconcile` registering their engine functions directly).
    # A `folder` instance is the only connector that needs no credentials,
    # so this entry point's own run isolates the environment and forbids a
    # real socket locally (see `_run_pull`'s own docstring).
    EntryPoint(
        id="pull",
        prepare=_stage_pull_folder,
        run=_run_pull,
        non_vacuous=_wrote_a_ledger_and_a_delivery,
    ),
    EntryPoint(
        id="index-derived",
        prepare=_prepare_derived_index,
        run=_run_cli_derived_index,
        non_vacuous=_derived_tables_populated,
    ),
)


# --- the guard ---------------------------------------------------------------


@pytest.mark.parametrize(
    "entry_point",
    WRITING_ENTRY_POINTS,
    ids=[entry_point.id for entry_point in WRITING_ENTRY_POINTS],
)
def test_entry_point_writes_only_inside_the_permitted_locations(
    entry_point: EntryPoint, tmp_path: Path
) -> None:
    """A full run touches nothing outside the permitted set (Req 7.5, 7.6).

    Runs the registered entry point over a fresh data root that shares a sandbox
    with the source directory, then asserts every created, modified, or deleted
    path lies inside the permitted set -- the owned paths, plus the
    contract-named shared files fitdocs legitimately writes (``athlete.toml``,
    which the ``load`` entry point updates and which is deliberately *not*
    owned), plus the locations the settings under test configure -- empty for
    ``sync``/``regen``/``load``/``history``, whose fixtures write no
    ``[inbox]`` table, and the configured inbox and processed-files
    directories for ``drain``, plus an explicit external index cache for the
    two index entry points. The run is also asserted to have produced its
    own observable, non-vacuous write (``entry_point.non_vacuous`` -- a
    workout document under ``workouts/`` for every entry point but
    ``history``, the history document itself for ``history``, since that
    pass writes no workout document at all), so a pipeline that silently
    stopped writing could not pass this guard by doing nothing.

    Mutation caught: any write outside the owned tree -- a stray file at the data
    root, a report dropped beside the source directory, a temp file left in the
    working directory -- appears in the diff and fails the assertion.
    """
    sandbox = tmp_path
    data_root = sandbox / "data"
    data_root.mkdir()
    source_dir = sandbox / "src"
    _stage_sources(source_dir)
    entry_point.prepare(data_root, source_dir)

    index_base = source_dir.parent / (
        "derived-index-cache" if entry_point.id == "index-derived" else "index-cache"
    )
    if entry_point.id in {"index", "sync-with-index", "index-derived"}:
        index_base.mkdir(parents=True, exist_ok=True)

    derived_before: dict[str, tuple[object, ...]] | None = None
    derived_index_directory: Path | None = None
    if entry_point.id == "index-derived":
        from fitdocs.index.location import resolve_index_location

        derived_index_directory = resolve_index_location(
            data_root,
            {"FITDOCS_INDEX_DIR": str(index_base)},
            sandbox,
        ).directory
        derived_before = _derived_guard_snapshot(sandbox, derived_index_directory)

    before = _snapshot(sandbox)
    entry_point.run(data_root, source_dir)
    after = _snapshot(sandbox)

    # Non-vacuity: the run really did produce its own registered observable
    # write. See EntryPoint.non_vacuous's own docstring for why this is no
    # longer a single hardcoded check shared by every entry point.
    assert entry_point.non_vacuous(_touched(before, after)), (
        f"{entry_point.id} entry point's measured run produced no observable "
        "write; the guard would pass vacuously over a pipeline that wrote nothing"
    )
    configured = configured_locations(data_root)
    if entry_point.id in {"index", "sync-with-index", "index-derived"}:
        from fitdocs.index.location import resolve_index_location

        resolved_index = resolve_index_location(
            data_root,
            {"FITDOCS_INDEX_DIR": str(index_base)},
            sandbox,
        )
        configured += (resolved_index.directory,)
    if entry_point.id == "index-derived":
        assert derived_before is not None
        assert derived_index_directory is not None
        derived_after = _derived_guard_snapshot(sandbox, derived_index_directory)
        _assert_derived_index_unchanged_outside_cache(derived_before, derived_after)
    else:
        assert_confined(
            sandbox, permitted_locations(data_root, configured), before, after
        )


def test_derived_index_rejects_managed_workout_write_negative_control(
    tmp_path: Path,
) -> None:
    """The derived-index entry point may write only to its external index.

    The producer mutation appends to an existing managed workout on a full
    fixture. Generic ownership confinement permits that path, so this
    derived-only negative control must be rejected by the stricter boundary.
    """
    from fitdocs.index.derived.blocks import BlockProducer
    from fitdocs.index.producer import CorpusSnapshot, Rows

    derived_entry = next(
        entry for entry in WRITING_ENTRY_POINTS if entry.id == "index-derived"
    )
    original_rows = BlockProducer.rows
    marker = b"\n<!-- simulated derived producer write -->\n"
    writes: list[tuple[Path, bytes, bytes]] = []

    def append_to_existing_workout(
        producer: BlockProducer, corpus: CorpusSnapshot
    ) -> Rows:
        rows = original_rows(producer, corpus)
        workout = corpus.data_root / "workouts" / "2026-02-02-run-a.md"
        if workout.is_file():
            before_bytes = workout.read_bytes()
            after_bytes = before_bytes + marker
            workout.write_bytes(after_bytes)
            writes.append((workout, before_bytes, after_bytes))
        return rows

    failure: AssertionError | None = None
    with patch.object(BlockProducer, "rows", append_to_existing_workout):
        try:
            test_entry_point_writes_only_inside_the_permitted_locations(
                derived_entry, tmp_path
            )
        except AssertionError as error:
            failure = error

    expected_path = tmp_path / "data" / "workouts" / "2026-02-02-run-a.md"
    assert len(writes) == 1
    assert writes[0][0] == expected_path
    assert writes[0][2] == writes[0][1] + marker
    assert expected_path.read_bytes() == writes[0][2]
    assert failure is not None, "DID NOT RAISE: derived-only strict confinement"
    assert "derived index changed data/source entries outside external index" in str(
        failure
    )
    assert "data/workouts/2026-02-02-run-a.md" in str(failure)


def _assert_derived_snapshot_rejects(
    before: dict[str, tuple[object, ...]],
    after: dict[str, tuple[object, ...]],
    relative_path: str,
) -> None:
    with pytest.raises(
        AssertionError,
        match="derived index changed data/source entries outside external index",
    ) as caught:
        _assert_derived_index_unchanged_outside_cache(before, after)
    assert relative_path in str(caught.value)


def test_derived_guard_snapshot_pins_file_bytes_independent_of_mtime(
    tmp_path: Path,
) -> None:
    root = tmp_path / "bytes-sensitivity"
    root.mkdir()
    file = root / "page.md"
    original = b"original payload"
    replacement = b"different payload"
    file.write_bytes(original)
    fixed_ns = 1_700_000_000_000_000_000
    os.utime(file, ns=(fixed_ns, fixed_ns))
    before = _derived_guard_snapshot(root, root / "cache" / "index")

    file.write_bytes(replacement)
    os.utime(file, ns=(fixed_ns, fixed_ns))
    after = _derived_guard_snapshot(root, root / "cache" / "index")

    assert before["page.md"][1] == original
    assert after["page.md"] == (
        "file",
        replacement,
        stat.S_IMODE(file.lstat().st_mode),
        fixed_ns,
    )
    assert after["page.md"][2:] == before["page.md"][2:]
    _assert_derived_snapshot_rejects(before, after, "page.md")


def test_derived_guard_snapshot_pins_mtime_independent_of_file_bytes(
    tmp_path: Path,
) -> None:
    root = tmp_path / "mtime-sensitivity"
    root.mkdir()
    file = root / "page.md"
    contents = b"unchanged payload"
    file.write_bytes(contents)
    original_ns = 1_700_000_000_000_000_000
    changed_ns = original_ns + 5_000_000_000
    os.utime(file, ns=(original_ns, original_ns))
    before = _derived_guard_snapshot(root, root / "cache" / "index")

    os.utime(file, ns=(changed_ns, changed_ns))
    after = _derived_guard_snapshot(root, root / "cache" / "index")

    assert before["page.md"][1] == after["page.md"][1] == contents
    assert before["page.md"][3] == original_ns
    assert after["page.md"][3] == changed_ns
    _assert_derived_snapshot_rejects(before, after, "page.md")


def test_derived_guard_snapshot_pins_file_permissions(tmp_path: Path) -> None:
    root = tmp_path / "permission-sensitivity"
    root.mkdir()
    file = root / "page.md"
    file.write_bytes(b"same bytes")
    file.chmod(0o600)
    fixed_ns = 1_700_000_000_000_000_000
    os.utime(file, ns=(fixed_ns, fixed_ns))
    before = _derived_guard_snapshot(root, root / "cache" / "index")

    file.chmod(0o640)
    after = _derived_guard_snapshot(root, root / "cache" / "index")

    assert before["page.md"][1] == after["page.md"][1] == b"same bytes"
    assert before["page.md"][2] == 0o600
    assert after["page.md"][2] == 0o640
    assert before["page.md"][3] == after["page.md"][3] == fixed_ns
    _assert_derived_snapshot_rejects(before, after, "page.md")


def test_derived_guard_snapshot_pins_empty_directory_presence(tmp_path: Path) -> None:
    root = tmp_path / "directory-sensitivity"
    root.mkdir()
    before = _derived_guard_snapshot(root, root / "cache" / "index")

    empty = root / "empty"
    empty.mkdir()
    after = _derived_guard_snapshot(root, root / "cache" / "index")

    assert after["empty"] == ("directory", stat.S_IMODE(empty.lstat().st_mode))
    _assert_derived_snapshot_rejects(before, after, "empty")


def test_derived_guard_snapshot_pins_directory_permissions(tmp_path: Path) -> None:
    root = tmp_path / "directory-permission-sensitivity"
    root.mkdir()
    directory = root / "empty"
    directory.mkdir()
    directory.chmod(0o700)
    before = _derived_guard_snapshot(root, root / "cache" / "index")

    directory.chmod(0o750)
    after = _derived_guard_snapshot(root, root / "cache" / "index")

    assert before["empty"] == ("directory", 0o700)
    assert after["empty"] == ("directory", 0o750)
    _assert_derived_snapshot_rejects(before, after, "empty")


def test_derived_guard_snapshot_pins_link_target_with_metadata_held(
    tmp_path: Path,
) -> None:
    root = tmp_path / "link-sensitivity"
    root.mkdir()
    (root / "first.txt").write_bytes(b"first")
    (root / "second.txt").write_bytes(b"second")
    link = root / "link"
    link.symlink_to("first.txt")
    original = link.lstat()
    os.utime(
        link,
        ns=(original.st_atime_ns, original.st_mtime_ns),
        follow_symlinks=False,
    )
    before = _derived_guard_snapshot(root, root / "cache" / "index")

    link.unlink()
    link.symlink_to("second.txt")
    os.utime(
        link,
        ns=(original.st_atime_ns, original.st_mtime_ns),
        follow_symlinks=False,
    )
    after = _derived_guard_snapshot(root, root / "cache" / "index")

    assert before["link"][0] == after["link"][0] == "symlink"
    assert before["link"][1] == "first.txt"
    assert after["link"][1] == "second.txt"
    assert before["link"][2:] == after["link"][2:]
    _assert_derived_snapshot_rejects(before, after, "link")


def test_derived_guard_snapshot_pins_distinct_special_file_kinds(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    if not hasattr(os, "mkfifo") or not hasattr(socket, "AF_UNIX"):
        pytest.skip("FIFO and Unix-domain sockets are required")
    root = tmp_path / "special-kind-sensitivity"
    root.mkdir()
    special = root / "special"
    os.mkfifo(special)
    before = _derived_guard_snapshot(root, root / "cache" / "index")

    special.unlink()
    monkeypatch.chdir(root)
    sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        sock.bind("special")
        after = _derived_guard_snapshot(root, root / "cache" / "index")
    finally:
        sock.close()

    assert before["special"][0:2] == ("other", stat.S_IFIFO)
    assert after["special"][0:2] == ("other", stat.S_IFSOCK)
    _assert_derived_snapshot_rejects(before, after, "special")


def test_derived_guard_snapshot_records_dangling_and_loop_links_without_following(
    tmp_path: Path,
) -> None:
    root = tmp_path / "nofollow-sensitivity"
    root.mkdir()
    dangling = root / "dangling"
    dangling.symlink_to("missing-target")
    loop = root / "loop"
    loop.symlink_to(".")

    snapshot = _derived_guard_snapshot(root, root / "cache" / "index")

    assert snapshot["dangling"][0:2] == ("symlink", "missing-target")
    assert snapshot["loop"][0:2] == ("symlink", ".")


def test_derived_guard_snapshot_excludes_exact_cache_subtree_only(
    tmp_path: Path,
) -> None:
    root = tmp_path / "cache-boundary-sensitivity"
    cache_parent = root / "cache"
    index_directory = cache_parent / "index-data"
    sibling = cache_parent / "index-data-neighbor"
    index_directory.mkdir(parents=True)
    sibling.mkdir()
    sibling_file = sibling / "page.txt"
    sibling_file.write_bytes(b"before")
    before = _derived_guard_snapshot(root, index_directory)

    assert "cache/index-data" not in before
    assert "cache/index-data/page.duckdb" not in before
    assert "cache/index-data-neighbor" in before
    assert "cache/index-data-neighbor/page.txt" in before
    (index_directory / "page.duckdb").write_bytes(b"cache output")
    cache_after = _derived_guard_snapshot(root, index_directory)
    assert cache_after == before

    sibling_file.write_bytes(b"after")
    sibling_after = _derived_guard_snapshot(root, index_directory)
    assert sibling_after["cache/index-data-neighbor/page.txt"][1] == b"after"
    _assert_derived_snapshot_rejects(
        before, sibling_after, "cache/index-data-neighbor/page.txt"
    )


def test_derive_benchmarks_is_a_registered_writing_entry_point() -> None:
    """``derive-benchmarks`` must be registered in :data:`WRITING_ENTRY_POINTS`
    (Req 7.6) so it is checked by the confinement guard like every other
    writing entry point -- dropping its registration is this task's own named
    mutation, and this test dies on it in this file rather than only being
    caught indirectly by the parametrized guard silently losing a case.
    """
    assert "derive-benchmarks" in {
        entry_point.id for entry_point in WRITING_ENTRY_POINTS
    }


@pytest.mark.parametrize("entry_id", ["index", "sync-with-index"])
def test_index_commands_are_registered_writing_entry_points(entry_id: str) -> None:
    assert entry_id in {entry_point.id for entry_point in WRITING_ENTRY_POINTS}


def test_plan_is_a_registered_writing_entry_point() -> None:
    """``plan`` must be registered in :data:`WRITING_ENTRY_POINTS` (training-
    blocks task 4.4; Req 1.2, 7.2, 7.7), the same discipline
    :func:`test_derive_benchmarks_is_a_registered_writing_entry_point` states
    for its own entry point.

    Deleting the registration is caught here, but by **nothing else** in
    this suite: the parametrized guard
    (``test_entry_point_writes_only_inside_the_permitted_locations``) would
    simply run one fewer case rather than fail, and
    ``tests/test_effort_tags_e2e.py``'s own subset check
    (``{"sync", "regen", "load", "drain"} <= registered``) never named
    ``"plan"`` at all, so it stays green either way -- this dedicated
    membership assertion is the only thing in the suite that reds when the
    registration is dropped.

    Checks identity against the registered callables themselves, not only
    the id (round-1 review fix, item 7): an id-only check is satisfied by
    ``EntryPoint(id="plan", prepare=_nothing, run=_nothing, non_vacuous=
    lambda touched: True)`` just as much as by the real registration, so a
    swapped-in vacuous stand-in for any of the three callables would pass
    an id-only membership test silently.
    """
    registered = {entry_point.id: entry_point for entry_point in WRITING_ENTRY_POINTS}
    assert "plan" in registered
    entry = registered["plan"]
    assert entry.prepare is _stage_plan_source
    assert entry.run is _run_plan
    assert entry.non_vacuous is _wrote_a_block_page


def test_reconcile_is_a_registered_writing_entry_point() -> None:
    """``reconcile`` must be registered in :data:`WRITING_ENTRY_POINTS`
    (plan-resolution task 3.3; Req 4.6, 8.8), the same discipline
    :func:`test_plan_is_a_registered_writing_entry_point` states for its
    own entry point -- including the identity check against the registered
    callables themselves, not only the id, for the same reason that test's
    own docstring gives."""
    registered = {entry_point.id: entry_point for entry_point in WRITING_ENTRY_POINTS}
    assert "reconcile" in registered
    entry = registered["reconcile"]
    assert entry.prepare is _stage_plan_and_logged_page
    assert entry.run is _run_reconcile
    assert entry.non_vacuous is _wrote_a_reconciled_block


def test_reconcile_non_vacuous_predicate_discriminates_the_plan_entrys_own() -> None:
    """Named mutation guard: swapping :data:`_wrote_a_reconciled_block` for
    :func:`_wrote_a_block_page` (the ``plan`` entry's own predicate) on the
    ``reconcile`` registration must be caught.

    :func:`_wrote_a_reconciled_block`'s own pin (using the reconcile
    fixture's real block id and row id, :data:`_RECONCILE_BLOCK_SOURCE_NAME`
    and ``"w1-mon"``): the block page alone in ``touched`` is ``False``; the
    block page *and* its row's planned page is ``True`` -- proving the
    stronger predicate actually requires both writes, not merely the one
    ``plan``'s own predicate checks.

    :func:`_wrote_a_block_page`'s own shape, over its own fixture's block
    id (:data:`_PLAN_SOURCE_NAME`) -- the plan entry's predicate never
    inspects any planned-page path at all, so it answers ``True`` whether
    or not one is present in ``touched``: this is the design's own named
    point, that a run whose resolver returns
    ``fitdocs.plans.resolution.unresolved()`` for every row would still
    pass ``plan``'s own predicate (wave 1 writes a planned page for every
    current row regardless of what the resolver returns), which is exactly
    why this task registers the stronger, row-aware predicate instead of
    reusing that one for ``reconcile``.
    """
    reconcile_block_id = Path(_RECONCILE_BLOCK_SOURCE_NAME).stem
    reconcile_row_id = "w1-mon"
    block_only = (f"data/{BLOCKS_DIR}/{reconcile_block_id}.md",)
    block_and_planned = (
        f"data/{BLOCKS_DIR}/{reconcile_block_id}.md",
        f"data/{BLOCKS_DIR}/{reconcile_block_id}/{reconcile_row_id}.md",
    )
    assert _wrote_a_reconciled_block(block_only) is False
    assert _wrote_a_reconciled_block(block_and_planned) is True

    plan_block_id = Path(_PLAN_SOURCE_NAME).stem
    plan_block_only = (f"data/{BLOCKS_DIR}/{plan_block_id}.md",)
    plan_block_and_a_planned_page = (
        f"data/{BLOCKS_DIR}/{plan_block_id}.md",
        f"data/{BLOCKS_DIR}/{plan_block_id}/some-row.md",
    )
    assert _wrote_a_block_page(plan_block_only) is True
    assert _wrote_a_block_page(plan_block_and_a_planned_page) is True


def test_guard_catches_a_stray_create_modify_and_delete(tmp_path: Path) -> None:
    """The guard fails on a write outside the permitted set -- in all three forms.

    Proves the guard is not vacuous: a stand-in run that performs a real ``sync``
    and then creates a file at the data root, modifies a staged source, and
    deletes another one fails with all three paths named. Without this, a guard
    that never fails would silently certify a pipeline that writes anywhere.
    """
    sandbox = tmp_path
    data_root = sandbox / "data"
    data_root.mkdir()
    source_dir = sandbox / "src"
    _stage_sources(source_dir)

    before = _snapshot(sandbox)
    _run_sync(data_root, source_dir)
    # Three strays, one of each kind, all outside the owned paths.
    (data_root / "stray-report.md").write_text("stray", encoding="utf-8")
    (source_dir / "run.fit").write_bytes(b"clobbered")
    (source_dir / "ride.fit").unlink()
    after = _snapshot(sandbox)

    with pytest.raises(AssertionError) as caught:
        assert_confined(sandbox, permitted_locations(data_root), before, after)

    message = str(caught.value)
    assert "data/stray-report.md" in message
    assert "src/run.fit" in message
    assert "src/ride.fit" in message


def test_configured_write_location_passes_and_only_the_configuration_permits_it(
    tmp_path: Path,
) -> None:
    """A write into a configured location is a pass, not a failure (Req 7.5).

    Exercises guard axis (b) end to end with the settings shape inbox will
    register: a table naming a directory resolves to a permitted location, so
    writing into it (and into a subdirectory of it) passes -- while the *same*
    writes fail the guard when the permitted set is the owned paths alone. That
    contrast is the proof the permitted set is computed as a union rather than
    hardcoded to ``OWNED_PATHS``.
    """
    sandbox = tmp_path
    data_root = sandbox / "data"
    data_root.mkdir()
    intake = sandbox / "intake"
    intake.mkdir()
    settings_path(data_root).write_text(
        '[inbox]\ndirectory = "../intake"\n', encoding="utf-8"
    )
    # The key the settings under test use; today's shipped set is empty.
    keys = (("inbox", "directory"),)

    before = _snapshot(sandbox)
    # A stand-in run that writes only inside the configured location.
    (intake / "processed").mkdir()
    (intake / "processed" / "run.fit").write_bytes(builder.run_fit_bytes())
    after = _snapshot(sandbox)

    configured = configured_locations(data_root, keys)
    assert configured == (intake.resolve(),)
    assert_confined(sandbox, permitted_locations(data_root, configured), before, after)

    # Without the configured half of the union the very same writes are strays.
    with pytest.raises(AssertionError):
        assert_confined(sandbox, permitted_locations(data_root), before, after)


def test_settings_without_an_inbox_table_configure_no_write_location(
    tmp_path: Path,
) -> None:
    """A settings document with no ``[inbox]`` table still resolves neither
    registered key, so the permitted set is the owned paths plus the shared
    files fitdocs writes -- nothing configured.

    inbox (task 5.2) has registered its two location keys in
    :data:`SETTINGS_LOCATION_KEYS`, so this no longer pins an empty tuple --
    it pins that a settings file lacking the ``[inbox]`` table still makes
    the configured half of the union degrade to empty, exactly as it did
    before inbox shipped. This is stronger than the ``sync``/``regen``/
    ``load`` entry points' own runs above, none of whose ``prepare``
    callables write a ``fitdocs.toml`` at all -- an absent file also
    resolves to ``()``, but this test pins the behavior with an explicit,
    ``[inbox]``-less file present instead of relying on absence.
    """
    data_root = tmp_path / "data"
    data_root.mkdir()
    settings_path(data_root).write_text("[tiles]\nenabled = false\n", encoding="utf-8")

    assert SETTINGS_LOCATION_KEYS == (("inbox", "path"), ("inbox", "processed_dir"))
    assert configured_locations(data_root) == ()
    assert permitted_locations(data_root) == tuple(
        data_root / owned for owned in OWNED_PATHS
    ) + tuple(data_root / name for name in PERMITTED_SHARED_FILES)


def test_history_entry_point_writes_no_workout_doc_asset_source_profile_or_settings(
    tmp_path: Path,
) -> None:
    """The history run's own, narrower negative claim (Req 7.5), additional to
    the generic confinement check above.

    ``workouts/``, ``workouts/assets/`` and ``fit-archive/`` are all inside
    :data:`~fitdocs.layout.OWNED_PATHS`, so the generic ``assert_confined``
    check in ``test_entry_point_writes_only_inside_the_permitted_locations``
    above would pass a history run that wrote a stray workout document --
    that path is itself permitted, for *other* entry points (``sync``,
    ``regen``, ``load``, ``drain``). The history pass's own guarantee is
    narrower than "somewhere permitted": stated precisely (Req 7.5, and the
    task's own "state it precisely rather than broadly"), the run creates,
    modifies or deletes **no** ``workouts/*.md`` document, **no** file under
    ``workouts/assets/``, and **no** ``fit-archive/*.fit`` archived source,
    and it writes neither ``athlete.toml`` nor ``fitdocs.toml`` itself.

    Deliberately **excluded** from this claim: the two in-tree ownership
    declarations (``workouts/AGENTS.md``, ``fit-archive/AGENTS.md``) --
    ``fitdocs.declaration.ensure_declarations`` may legitimately create or
    rewrite either on a data root that has never been synced
    (``fitdocs.history.engine``'s own module docstring, "Ownership
    declarations"), so asserting those two files untouched would itself be a
    false negative claim -- exactly the kind the module docstring above
    warns a blanket "touches nothing under ``workouts/``" assertion would be.

    Mutation caught: a stand-in run that also writes
    ``workouts/injected.md`` fails this test's own assertion while the
    generic confinement guard above stays green for the same write (the path
    lies inside ``OWNED_PATHS``, so it is merely "permitted", not "forbidden
    for this pass") -- proving this test catches a class of regression the
    generic one cannot.
    """
    sandbox = tmp_path
    data_root = sandbox / "data"
    data_root.mkdir()
    source_dir = sandbox / "src"
    _stage_history_pages(data_root, source_dir)

    before = _snapshot(sandbox)
    _run_history(data_root, source_dir)
    after = _snapshot(sandbox)

    touched = _touched(before, after)

    no_workout_document = [
        key
        for key in touched
        if key.startswith(f"data/{WORKOUTS_DIR}/")
        and key.endswith(".md")
        and not key.endswith(f"/{DECLARATION_FILENAME}")
    ]
    no_workout_asset = [
        key for key in touched if key.startswith(f"data/{WORKOUTS_DIR}/assets/")
    ]
    no_archived_source = [
        key
        for key in touched
        if key.startswith(f"data/{ARCHIVE_DIR}/") and key.endswith(".fit")
    ]

    assert no_workout_document == [], (
        f"history run wrote a workout document: {no_workout_document}"
    )
    assert no_workout_asset == [], (
        f"history run wrote a workout asset: {no_workout_asset}"
    )
    assert no_archived_source == [], (
        f"history run wrote an archived source: {no_archived_source}"
    )
    assert f"data/{ATHLETE_FILE}" not in touched, (
        "history run wrote the athlete profile"
    )
    assert f"data/{SETTINGS_FILE}" not in touched, "history run wrote the settings file"

    # Non-vacuity for this test's own precondition: the run actually wrote
    # something (the history document), so the negative assertions above are
    # not vacuously true over a run that did nothing at all.
    assert f"data/{HISTORY_DIR}/{HISTORY_DOC_STEM}.md" in touched


def test_plan_entry_point_touches_only_the_plan_directory_and_writes_no_other_document(
    tmp_path: Path,
) -> None:
    """The ``plan`` entry point's own, narrower negative claim (Req 1.2, 7.2,
    7.7), stated precisely rather than broadly.

    The generic confinement check above only proves the run stayed inside
    the permitted set -- ``blocks/`` among it, since that prefix is already
    in :data:`~fitdocs.layout.OWNED_PATHS`. It would pass a run that (for
    example) also rewrote a workout document, since ``workouts/`` is itself
    permitted for *other* entry points. This test states the plan pass's
    own guarantee precisely: the staged source file's bytes are byte-for-byte
    unchanged, and **nothing** under the plan-source directory
    (:data:`~fitdocs.layout.DEFAULT_PLANS_DIR`) was created, modified or
    deleted at all -- no new file, no rewrite, no removal, matching the
    plan's hard rule that no task "writes, creates, renames or deletes
    anything under the resolved plan-source directory". It also asserts the
    run wrote no ``workouts/*.md`` document, no ``history/*.md`` page, and
    neither ``athlete.toml`` nor ``fitdocs.toml`` itself.

    Deliberately **excluded** from this claim: the other three in-tree
    ownership declarations (``workouts/AGENTS.md``, ``history/AGENTS.md``,
    ``fit-archive/AGENTS.md``) -- ``fitdocs.declaration.ensure_declarations``
    legitimately creates every entry of :data:`~fitdocs.layout.DECLARED_DIRS`
    that is still absent on a data root that has never been synced, exactly
    the same exclusion the history entry point's own precise test states for
    the same reason (see its docstring above). ``blocks/AGENTS.md`` is not
    excluded from anything here because nothing above claims it untouched --
    it lies inside the plan pass's own owned prefix and is exactly what a
    genuinely successful run creates.

    Mutation caught (measured): a stand-in run that also writes
    ``workouts/injected.md`` fails this test's own ``no_workout_document``
    assertion while the generic confinement guard above
    (``test_entry_point_writes_only_inside_the_permitted_locations[plan]``)
    stays green for the very same write, since ``workouts/`` is itself
    inside :data:`~fitdocs.layout.OWNED_PATHS` and therefore "permitted" in
    the generic sense -- for other entry points, never for this one --
    proving this test catches a class of regression the generic one
    cannot, the same way
    ``test_history_entry_point_writes_no_workout_doc_asset_source_profile_or_settings``
    does for ``history``. (A stray write under the plan-source directory
    itself, by contrast, already reds the generic guard too, since
    :data:`~fitdocs.layout.DEFAULT_PLANS_DIR` is deliberately *not* an owned
    path -- this test's ``no_plan_source_writes`` assertion and the
    source-bytes check above are the *precise* statement of that same
    claim, not the only place it is caught.)
    """
    sandbox = tmp_path
    data_root = sandbox / "data"
    data_root.mkdir()
    source_dir = sandbox / "src"
    _stage_plan_source(data_root, source_dir)
    plan_source_path = data_root / DEFAULT_PLANS_DIR / _PLAN_SOURCE_NAME
    source_bytes_before = plan_source_path.read_bytes()

    before = _snapshot(sandbox)
    _run_plan(data_root, source_dir)
    after = _snapshot(sandbox)

    touched = _touched(before, after)

    no_plan_source_writes = [
        key for key in touched if key.startswith(f"data/{DEFAULT_PLANS_DIR}/")
    ]
    no_workout_document = [
        key
        for key in touched
        if key.startswith(f"data/{WORKOUTS_DIR}/")
        and key.endswith(".md")
        and not key.endswith(f"/{DECLARATION_FILENAME}")
    ]
    no_history_document = [
        key
        for key in touched
        if key.startswith(f"data/{HISTORY_DIR}/")
        and key.endswith(".md")
        and not key.endswith(f"/{DECLARATION_FILENAME}")
    ]

    assert no_plan_source_writes == [], (
        f"plan run wrote under the plan-source directory: {no_plan_source_writes}"
    )
    assert plan_source_path.read_bytes() == source_bytes_before, (
        "plan run modified the staged source's bytes"
    )
    assert no_workout_document == [], (
        f"plan run wrote a workout document: {no_workout_document}"
    )
    assert no_history_document == [], (
        f"plan run wrote a history document: {no_history_document}"
    )
    assert f"data/{ATHLETE_FILE}" not in touched, "plan run wrote the athlete profile"
    assert f"data/{SETTINGS_FILE}" not in touched, "plan run wrote the settings file"

    # Non-vacuity for this test's own precondition: the run actually wrote
    # something (a block page), so the negative assertions above are not
    # vacuously true over a run that did nothing at all.
    assert _wrote_a_block_page(touched)


def test_reconcile_entry_point_writes_a_resolved_match(tmp_path: Path) -> None:
    """Sibling behavioural test (plan-resolution task 3.3; Req 4.6, 8.8):
    the block page the guarded ``reconcile`` run wrote actually carries a
    resolved match, not merely a block page written by wave 1's own
    unconditional render step regardless of what the resolver returned --
    the gap :func:`_wrote_a_reconciled_block`'s own docstring names as the
    one its stronger, two-page predicate still cannot close by itself.
    """
    sandbox = tmp_path
    data_root = sandbox / "data"
    data_root.mkdir()
    source_dir = sandbox / "src"
    _stage_plan_and_logged_page(data_root, source_dir)

    _run_reconcile(data_root, source_dir)

    block_id = Path(_RECONCILE_BLOCK_SOURCE_NAME).stem
    block_page_path = data_root / BLOCKS_DIR / f"{block_id}.md"
    assert block_page_path.exists(), "the reconcile run wrote no block page at all"
    block_page_text = block_page_path.read_text(encoding="utf-8")
    assert "matched:" in block_page_text, (
        "the block page carries no 'matched:' cell -- the resolver did not "
        f"run, or did not resolve a match:\n{block_page_text}"
    )


def test_reconcile_touches_only_the_plan_directory_and_writes_no_other_document(
    tmp_path: Path,
) -> None:
    """The ``reconcile`` entry point's own, narrower negative claim (Req
    4.6, 8.8), stated precisely rather than broadly -- the same discipline
    :func:`test_plan_entry_point_touches_only_the_plan_directory_and_writes_no_other_document`
    states for ``plan``, phrased in that test's own words (design.md,
    "ConfinementRegistration"): the staged plan source's bytes are
    byte-for-byte unchanged, and **nothing** under the plan-source
    directory was created, modified or deleted; the staged, already-
    generated workout page's bytes are unchanged, and no other workout
    document under ``workouts/`` was created, modified or deleted (the
    declaration file there, ``workouts/AGENTS.md``, excluded -- the
    measured ``run_plan`` beneath this pass refreshes every declared
    directory's declaration, exactly as ``plan``'s own test excludes it);
    no history page; neither the athlete profile nor the settings file.

    Deliberately **excluded** from this claim, mirroring ``plan``'s own
    test: the other two in-tree ownership declarations
    (``history/AGENTS.md``, ``fit-archive/AGENTS.md``) that
    ``ensure_declarations`` may legitimately create or rewrite, and
    ``blocks/AGENTS.md`` itself, which lies inside this pass's own owned
    prefix.

    Mutation caught (measured): a stand-in run that writes a marker file
    under ``workouts/`` (e.g. ``workouts/.reconcile``) fails this test's own
    ``no_workout_write`` assertion -- deliberately not narrowed to ``.md``
    documents the way
    :func:`test_plan_entry_point_touches_only_the_plan_directory_and_writes_no_other_document`'s
    own ``no_workout_document`` is, precisely so a non-document marker like
    this one is still caught.
    """
    sandbox = tmp_path
    data_root = sandbox / "data"
    data_root.mkdir()
    source_dir = sandbox / "src"
    _stage_plan_and_logged_page(data_root, source_dir)
    plan_source_path = data_root / DEFAULT_PLANS_DIR / _RECONCILE_BLOCK_SOURCE_NAME
    source_bytes_before = plan_source_path.read_bytes()
    workout_page_path = data_root / WORKOUTS_DIR / f"{_RECONCILE_WORKOUT_STEM}.md"
    workout_bytes_before = workout_page_path.read_bytes()

    before = _snapshot(sandbox)
    _run_reconcile(data_root, source_dir)
    after = _snapshot(sandbox)

    touched = _touched(before, after)

    no_plan_source_writes = [
        key for key in touched if key.startswith(f"data/{DEFAULT_PLANS_DIR}/")
    ]
    # Deliberately not narrowed to `.md` (unlike the `plan` entry's own
    # analogous filter): this task's own named mutation is a `.reconcile`
    # marker file dropped under `workouts/`, which is not a workout
    # *document* in the ".md" sense but is exactly the kind of stray write
    # under this owned-but-foreign-to-this-pass prefix the negative half
    # forbids -- so the filter here is "anything under `workouts/` but the
    # declaration file", catching a non-document write a `.md`-only filter
    # would miss.
    no_workout_write = [
        key
        for key in touched
        if key.startswith(f"data/{WORKOUTS_DIR}/")
        and not key.endswith(f"/{DECLARATION_FILENAME}")
    ]
    no_history_document = [
        key
        for key in touched
        if key.startswith(f"data/{HISTORY_DIR}/")
        and key.endswith(".md")
        and not key.endswith(f"/{DECLARATION_FILENAME}")
    ]

    assert no_plan_source_writes == [], (
        f"reconcile run wrote under the plan-source directory: {no_plan_source_writes}"
    )
    assert plan_source_path.read_bytes() == source_bytes_before, (
        "reconcile run modified the staged plan source's bytes"
    )
    assert workout_page_path.read_bytes() == workout_bytes_before, (
        "reconcile run modified the staged workout page's bytes"
    )
    assert no_workout_write == [], (
        f"reconcile run wrote under the workouts directory: {no_workout_write}"
    )
    assert no_history_document == [], (
        f"reconcile run wrote a history document: {no_history_document}"
    )
    assert f"data/{ATHLETE_FILE}" not in touched, (
        "reconcile run wrote the athlete profile"
    )
    assert f"data/{SETTINGS_FILE}" not in touched, (
        "reconcile run wrote the settings file"
    )

    # Non-vacuity for this test's own precondition: the run actually wrote
    # both pages, so the negative assertions above are not vacuously true
    # over a run that did nothing at all.
    assert _wrote_a_reconciled_block(touched)


def test_sync_base_change_is_a_registered_writing_entry_point() -> None:
    """``sync-base-change`` is registered with its own callables (activity-
    identity Req 6.2, 6.4): dropping the registration would only shrink the
    parametrized guard by one case, so this membership check pins it."""
    registered = {entry_point.id: entry_point for entry_point in WRITING_ENTRY_POINTS}
    assert "sync-base-change" in registered
    entry = registered["sync-base-change"]
    assert entry.prepare is _stage_base_change
    assert entry.run is _run_sync_base_change
    assert entry.non_vacuous is _renamed_a_workout_document


def test_base_change_non_vacuous_predicate_needs_a_delete_and_a_create() -> None:
    """A run that touched only the new document (a fresh page) or only the old
    one (a rewrite in place) is vacuous for this entry; both is not."""
    old = f"data/{WORKOUTS_DIR}/{_BASE_CHANGE_OLD_STEM}.md"
    new = f"data/{WORKOUTS_DIR}/{_BASE_CHANGE_NEW_STEM}.md"
    assert _renamed_a_workout_document((old,)) is False
    assert _renamed_a_workout_document((new,)) is False
    assert _renamed_a_workout_document((old, new)) is True


def test_pull_is_a_registered_writing_entry_point() -> None:
    """``pull`` must be registered in :data:`WRITING_ENTRY_POINTS` (connectors
    task 6.3; Req 5.9, 13.5, 15.3), the same discipline
    :func:`test_plan_is_a_registered_writing_entry_point` states for its own
    entry point -- including the identity check against the registered
    callables themselves, not only the id, for the same reason that test's
    own docstring gives: an id-only check cannot catch a swapped-in vacuous
    stand-in for ``prepare``, ``run``, or ``non_vacuous``.

    Named mutation: dropping this registration reds this test directly; the
    parametrized guard above merely runs one fewer case (it iterates
    whatever :data:`WRITING_ENTRY_POINTS` holds), so this is the only thing
    in the suite that fails outright, matching every sibling membership
    test's own docstring on this point.
    """
    registered = {entry_point.id: entry_point for entry_point in WRITING_ENTRY_POINTS}
    assert "pull" in registered
    entry = registered["pull"]
    assert entry.prepare is _stage_pull_folder
    assert entry.run is _run_pull
    assert entry.non_vacuous is _wrote_a_ledger_and_a_delivery


def test_pull_non_vacuous_predicate_needs_a_ledger_and_a_delivery() -> None:
    """:func:`_wrote_a_ledger_and_a_delivery` requires both the ledger write
    and a delivered ``.fit`` file -- neither alone is enough, so a run that
    only ever saved an (empty) ledger cannot pass this guard vacuously."""
    ledger = f"data/{CONNECTOR_STATE_DIR}/{_PULL_INSTANCE_NAME}.toml"
    delivery = f"data/inbox/{_PULL_INSTANCE_NAME}/run.fit"
    assert _wrote_a_ledger_and_a_delivery((ledger,)) is False
    assert _wrote_a_ledger_and_a_delivery((delivery,)) is False
    assert _wrote_a_ledger_and_a_delivery((ledger, delivery)) is True
    assert (
        _wrote_a_ledger_and_a_delivery((ledger, f"data/inbox/{_PULL_INSTANCE_NAME}"))
        is False
    )
    assert (
        _wrote_a_ledger_and_a_delivery(
            (ledger, f"data/inbox/{_PULL_INSTANCE_NAME}/.run.fit-x.tmp")
        )
        is False
    )
    assert (
        _wrote_a_ledger_and_a_delivery((f"data/{CONNECTOR_STATE_DIR}", delivery))
        is False
    )
    assert (
        _wrote_a_ledger_and_a_delivery(
            (f"data/{CONNECTOR_STATE_DIR}/other.toml", delivery)
        )
        is False
    )


def test_connect_writes_only_the_credentials_file(tmp_path: Path) -> None:
    """``connect`` touches only its own credentials directory and file (Req
    5.9, 15.3) -- a sibling claim to the generic ``pull`` confinement guard
    above, proved directly over :func:`~fitdocs.connectors.connect.run_connect`
    rather than through the :class:`EntryPoint` registry: ``connect`` makes no
    data-root write at all (design.md ConfinementRegistration states this
    test standalone, not as a registered writing entry point).

    Isolated locally, the same way :func:`_run_pull` is (this module sits
    outside ``tests/connectors/conftest.py``'s autouse fixtures): the
    environment isolation and the socket guard are applied here directly,
    and the credentials directory (``<sandbox>/user-config``) is deliberately
    inside the sandbox this test snapshots but outside the data root, so a
    stray write under ``data/`` or ``src/`` would be visible in the diff.
    """
    sandbox = tmp_path
    data_root = sandbox / "data"
    data_root.mkdir()
    source_dir = sandbox / "src"
    source_dir.mkdir()
    credentials_dir = sandbox / "user-config"

    monkeypatch = pytest.MonkeyPatch()
    try:
        with tempfile.TemporaryDirectory() as base_dir:
            isolate_connector_environment(monkeypatch, Path(base_dir))
            monkeypatch.setattr(socket, "socket", _socket_raises)

            store = CredentialStore(credentials_dir)
            connector = ScriptedPersonalKeyConnector()
            connector.verify_script.append(Granted(scopes=("read",)))
            instance = ConnectorInstance(
                name="svc", connector=connector, lookback_days=30, settings=None
            )
            transport = FakeTransport(
                [HttpResponse(status=200, headers={}, body=b"{}")]
            )

            before = _snapshot(sandbox)
            result = run_connect(
                instance,
                {"api_key": "s3cr3t-connect-fixture"},
                store=store,
                transport=transport,
                environ={},
                now=lambda: _PULL_NOW,
                sleep=lambda seconds: None,
                redactor=Redactor(),
            )
            after = _snapshot(sandbox)
    finally:
        monkeypatch.undo()

    assert isinstance(result, Connected), result

    touched = _touched(before, after)
    assert touched == ("user-config", "user-config/svc.toml"), (
        f"connect wrote outside its own credentials directory: {touched}"
    )
    for key in touched:
        assert not key.startswith("data/"), f"connect wrote under the data root: {key}"
        assert not key.startswith("src/"), (
            f"connect wrote under the source directory: {key}"
        )


def test_index_derived_is_a_registered_writing_entry_point() -> None:
    assert "index-derived" in {entry_point.id for entry_point in WRITING_ENTRY_POINTS}


# Query-local inventory preparation is intentionally independent of the generic
# writer snapshot above: query permits only real per-process spill directories.
def _query_inventory(root: Path) -> dict[str, tuple[object, ...]]:
    inventory: dict[str, tuple[object, ...]] = {}
    pending = [root]
    while pending:
        directory = pending.pop()
        with os.scandir(directory) as entries:
            for entry in sorted(entries, key=lambda item: item.name):
                path = Path(entry.path)
                relative = path.relative_to(root).as_posix()
                if entry.is_symlink():
                    metadata = entry.stat(follow_symlinks=False)
                    inventory[relative] = (
                        "symlink",
                        metadata.st_size,
                        metadata.st_mtime_ns,
                        os.readlink(path),
                    )
                elif entry.is_dir(follow_symlinks=False):
                    inventory[relative] = ("directory",)
                    pending.append(path)
                elif entry.is_file(follow_symlinks=False):
                    metadata = entry.stat(follow_symlinks=False)
                    digest = hashlib.sha256(path.read_bytes()).hexdigest()
                    inventory[relative] = (
                        "file",
                        metadata.st_size,
                        metadata.st_mtime_ns,
                        digest,
                    )
    return inventory


def _query_spill_exemptions(root: Path, index_dir: Path) -> frozenset[str]:
    resolved_root = root.resolve()
    resolved_index = index_dir.resolve()
    if not resolved_index.is_relative_to(resolved_root) or not resolved_index.is_dir():
        return frozenset()
    exemptions: set[str] = set()
    with os.scandir(resolved_index) as entries:
        for entry in entries:
            if re.fullmatch(r"query-spill-\d+", entry.name) is None:
                continue
            if entry.is_dir(follow_symlinks=False):
                path = Path(entry.path)
                exemptions.add(Path(os.path.relpath(path, resolved_root)).as_posix())
    return frozenset(exemptions)


def test_query_inventory_fixed_input_types_and_spill_scope(tmp_path: Path) -> None:
    root = tmp_path / "sandbox"
    index = root / "index"
    index.mkdir(parents=True)
    (root / "empty").write_bytes(b"")
    (root / "binary").write_bytes(b"\x00A\xff")
    (index / "query-spill-123").mkdir()
    (index / "query-spill-123" / "payload").write_bytes(b"spill")
    (index / "query-spill-123" / "empty-child").mkdir()
    (index / "query-spill-123" / "query-spill-246").mkdir()
    (index / "query-spill-123-neighbor").mkdir()
    (index / "query-spill-456").write_text("file", encoding="utf-8")
    outside = root / "elsewhere"
    outside.mkdir()
    (outside / "query-spill-123").mkdir()
    (index / "query-spill-789").symlink_to("../elsewhere")
    (root / "link").symlink_to("empty")
    (root / "raw-relative").symlink_to("../elsewhere")
    (root / "dangling").symlink_to("absent")
    (root / "loop-a").symlink_to("loop-b")
    (root / "loop-b").symlink_to("loop-a")
    fixed_mtime_ns = 1_700_000_000_123_456_789
    for file_path in (
        root / "empty",
        root / "binary",
        index / "query-spill-123" / "payload",
        index / "query-spill-456",
    ):
        os.utime(file_path, ns=(fixed_mtime_ns, fixed_mtime_ns))
    for link_path in (
        root / "link",
        root / "raw-relative",
        root / "dangling",
        root / "loop-a",
        root / "loop-b",
        index / "query-spill-789",
    ):
        os.utime(
            link_path,
            ns=(fixed_mtime_ns, fixed_mtime_ns),
            follow_symlinks=False,
        )

    inventory = _query_inventory(root)
    assert inventory == {
        "binary": (
            "file",
            3,
            fixed_mtime_ns,
            "fae12c85cb1b6aca5070c8837c2b720665f35afabe2dcd504d6c970de880d834",
        ),
        "dangling": ("symlink", 6, fixed_mtime_ns, "absent"),
        "empty": (
            "file",
            0,
            fixed_mtime_ns,
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        ),
        "elsewhere": ("directory",),
        "elsewhere/query-spill-123": ("directory",),
        "index": ("directory",),
        "index/query-spill-123": ("directory",),
        "index/query-spill-123/empty-child": ("directory",),
        "index/query-spill-123/query-spill-246": ("directory",),
        "index/query-spill-123/payload": (
            "file",
            5,
            fixed_mtime_ns,
            "234a838aaa5e6ae0a9a2076d47b8e1d571c40e8e42c72d07719cfaceab508225",
        ),
        "index/query-spill-123-neighbor": ("directory",),
        "index/query-spill-456": (
            "file",
            4,
            fixed_mtime_ns,
            "3b9c358f36f0a31b6ad3e14f309c7cf198ac9246e8316f9ce543d5b19ac02b80",
        ),
        "index/query-spill-789": ("symlink", 12, fixed_mtime_ns, "../elsewhere"),
        "link": ("symlink", 5, fixed_mtime_ns, "empty"),
        "loop-a": ("symlink", 6, fixed_mtime_ns, "loop-b"),
        "loop-b": ("symlink", 6, fixed_mtime_ns, "loop-a"),
        "raw-relative": ("symlink", 12, fixed_mtime_ns, "../elsewhere"),
    }
    assert _query_spill_exemptions(root, index) == frozenset({"index/query-spill-123"})
    external_index = tmp_path / "external-index"
    external_index.mkdir()
    (external_index / "query-spill-654").mkdir()
    assert _query_spill_exemptions(root, external_index) == frozenset()


def test_query_inventory_discriminates_size_mtime_digest_and_path_changes(
    tmp_path: Path,
) -> None:
    root = tmp_path / "inventory-deltas"
    root.mkdir()
    sized = root / "size"
    timed = root / "mtime"
    digested = root / "digest"
    retargeted = root / "retarget"
    sized.write_bytes(b"A")
    timed.write_bytes(b"same")
    digested.write_bytes(b"ABCD")
    retargeted.symlink_to("one")
    timed_ns = 1_700_000_000_123_456_789
    os.utime(timed, ns=(timed_ns, timed_ns))
    link_mtime_ns = 1_700_000_000_223_456_789
    os.utime(retargeted, ns=(link_mtime_ns, link_mtime_ns), follow_symlinks=False)
    initial = _query_inventory(root)
    assert set(initial) == {"size", "mtime", "digest", "retarget"}
    assert initial["size"][1] == 1
    assert initial["mtime"] == (
        "file",
        4,
        timed_ns,
        "0967115f2813a3541eaef77de9d9d5773f1c0c04314b0bbfe4ff3b3b1c55b5d5",
    )
    assert initial["digest"][1] == 4
    assert initial["retarget"] == ("symlink", 3, link_mtime_ns, "one")

    sized.write_bytes(b"AB")
    after_size = _query_inventory(root)
    assert after_size["size"][1] == 2

    updated_time_ns = timed_ns + 10_000_000
    os.utime(timed, ns=(updated_time_ns, updated_time_ns))
    after_mtime = _query_inventory(root)
    assert after_mtime["mtime"] == (
        "file",
        4,
        updated_time_ns,
        "0967115f2813a3541eaef77de9d9d5773f1c0c04314b0bbfe4ff3b3b1c55b5d5",
    )

    original_digest_mtime = digested.stat().st_mtime_ns
    digested.write_bytes(b"WXYZ")
    os.utime(digested, ns=(original_digest_mtime, original_digest_mtime))
    after_digest = _query_inventory(root)
    assert after_digest["digest"] == (
        "file",
        4,
        original_digest_mtime,
        "21e32f5321cad49ab4cf78ba5ed231e0f36d0c78d34108fda1be939f33fba149",
    )

    original_link_stat = retargeted.lstat()
    retargeted.unlink()
    retargeted.symlink_to("two")
    os.utime(
        retargeted,
        ns=(original_link_stat.st_atime_ns, original_link_stat.st_mtime_ns),
        follow_symlinks=False,
    )
    changed_link_stat = retargeted.lstat()
    assert changed_link_stat.st_size == original_link_stat.st_size
    assert changed_link_stat.st_mtime_ns == original_link_stat.st_mtime_ns
    after_retarget = _query_inventory(root)
    assert after_retarget["retarget"] == ("symlink", 3, link_mtime_ns, "two")

    (root / "added-empty").mkdir()
    after_add = _query_inventory(root)
    assert "added-empty" in after_add
    (root / "added-empty").rmdir()
    (root / "size").unlink()
    after_delete = _query_inventory(root)
    assert "added-empty" not in after_delete
    assert "size" not in after_delete


def test_query_inventory_keeps_directory_symlink_without_walking_target(
    tmp_path: Path,
) -> None:
    root = tmp_path / "symlink-walk"
    target = root / "target"
    target.mkdir(parents=True)
    (target / "child").write_bytes(b"x")
    alias = root / "alias"
    alias.symlink_to("target")
    fixed_mtime_ns = 1_700_000_000_333_456_789
    os.utime(target / "child", ns=(fixed_mtime_ns, fixed_mtime_ns))
    os.utime(alias, ns=(fixed_mtime_ns, fixed_mtime_ns), follow_symlinks=False)

    inventory = _query_inventory(root)
    assert inventory == {
        "alias": ("symlink", 6, fixed_mtime_ns, "target"),
        "target": ("directory",),
        "target/child": (
            "file",
            1,
            fixed_mtime_ns,
            "2d711642b726b04401627ca9fbac32f5c8530fb1903cc4db02258717921a4881",
        ),
    }


def test_query_writes_nothing_outside_its_spill_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from fitdocs.index.location import resolve_index_location
    from fitdocs.index.store import create_index, open_index, read_bookkeeping

    sandbox = tmp_path / "query-confinement"
    sandbox.mkdir()
    data_root = sandbox / "data"
    data_root.mkdir()
    source = sandbox / "source"
    source.mkdir()
    (source / "run.fit").write_bytes(builder.run_fit_bytes())
    index_base = sandbox / "index-cache"
    home = sandbox / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("FITDOCS_INDEX_DIR", str(index_base))
    monkeypatch.setenv("XDG_CACHE_HOME", str(sandbox / "xdg-cache"))
    (data_root / "fitdocs.toml").write_text(
        "[tiles]\nenabled = false\n", encoding="utf-8"
    )

    synced = _CLI_RUNNER.invoke(
        app, ["sync", str(source), "--out", str(data_root), "--no-prompt"]
    )
    assert synced.exit_code == 0, synced.output
    indexed = _CLI_RUNNER.invoke(app, ["index", "--out", str(data_root)])
    assert indexed.exit_code == 0, indexed.output

    location = resolve_index_location(data_root, os.environ, home)
    index_dir = location.directory.resolve()
    database = location.database
    page_paths = tuple(
        sorted(
            path
            for path in (data_root / WORKOUTS_DIR).glob("*.md")
            if path.name != "AGENTS.md"
        )
    )
    assert len(page_paths) == 1
    page = page_paths[0]
    assert page.read_bytes()
    assert database.is_file() and database.stat().st_size > 0
    with open_index(database, read_only=True) as connection:
        bookkeeping = read_bookkeeping(connection)
    assert bookkeeping is not None
    assert len(bookkeeping.pages) == 1
    assert (
        next(iter(bookkeeping.pages.values())).path
        == page.relative_to(data_root).as_posix()
    )

    copy_target = data_root / "copy-output.csv"
    csv_decoy = data_root / "readable-decoy.csv"
    csv_decoy.write_text("answer\n42\n", encoding="utf-8")
    assert csv_decoy.read_text(encoding="utf-8") == "answer\n42\n"
    attached_database = data_root / "valid-attachment.duckdb"
    with create_index(attached_database) as attachment:
        attachment.execute("CREATE TABLE fixture (answer INTEGER)")
        attachment.execute("INSERT INTO fixture VALUES (42)")
    assert attached_database.is_file() and attached_database.stat().st_size > 0
    assert not copy_target.exists()
    assert tuple(home.iterdir()) == ()

    monkeypatch.setattr("fitdocs.cli._stdout_is_terminal", lambda: False)

    def snapshot() -> dict[str, tuple[object, ...]]:
        inventory = _query_inventory(sandbox)
        spill_paths = _query_spill_exemptions(sandbox, index_dir)
        return {
            path: entry for path, entry in inventory.items() if path not in spill_paths
        }

    before = snapshot()
    assert before
    assert f"data/{page.relative_to(data_root).as_posix()}" in before
    assert any(path.endswith("index.duckdb") for path in before)

    select = _CLI_RUNNER.invoke(
        app,
        ["query", "SELECT count(*) AS n FROM pages", "--out", str(data_root)],
    )
    assert (select.exit_code, select.stdout, select.stderr) == (0, "n\n1\n", "")
    assert snapshot() == before
    assert tuple(home.iterdir()) == ()

    schema = _CLI_RUNNER.invoke(app, ["query", "--schema", "--out", str(data_root)])
    assert schema.exit_code == 0, schema.output
    assert "Database:" in schema.stdout and "pages" in schema.stdout
    assert snapshot() == before
    assert tuple(home.iterdir()) == ()

    copy = _CLI_RUNNER.invoke(
        app,
        [
            "query",
            f"COPY (SELECT 1) TO '{copy_target}' (HEADER, DELIMITER ',')",
            "--out",
            str(data_root),
        ],
    )
    assert copy.exit_code == 1
    assert copy.stderr.splitlines()[0] == (
        "Query refused: the query sandbox runs only queries and EXPLAIN; "
        "this is a COPY statement."
    )
    assert not copy_target.exists()
    assert snapshot() == before
    assert tuple(home.iterdir()) == ()

    read_file = _CLI_RUNNER.invoke(
        app,
        [
            "query",
            f"SELECT * FROM read_csv_auto('{csv_decoy}')",
            "--out",
            str(data_root),
        ],
    )
    assert read_file.exit_code == 1
    assert read_file.stderr.splitlines()[0] == (
        "Query refused: the query sandbox cannot read or write files or "
        "addresses outside the index."
    )
    assert read_file.stderr.splitlines()[1].startswith("DuckDB: ")
    assert snapshot() == before
    assert tuple(home.iterdir()) == ()

    attach = _CLI_RUNNER.invoke(
        app,
        [
            "query",
            f"ATTACH '{attached_database}' AS external_db",
            "--out",
            str(data_root),
        ],
    )
    assert attached_database.is_file() and attached_database.stat().st_size > 0
    assert attach.exit_code == 1
    assert attach.stderr.splitlines()[0] == (
        "Query refused: the query sandbox runs only queries and EXPLAIN; "
        "this is an ATTACH statement."
    )
    assert snapshot() == before
    assert tuple(home.iterdir()) == ()

    malformed = _CLI_RUNNER.invoke(app, ["query", "SELEC 1", "--out", str(data_root)])
    assert malformed.exit_code == 1
    assert malformed.stderr == (
        'Query failed: Parser Error: syntax error at or near "SELEC"\n\n'
        "LINE 1: SELEC 1\n        ^\n"
    )
    assert snapshot() == before
    assert tuple(home.iterdir()) == ()

    timed_out = _CLI_RUNNER.invoke(
        app,
        [
            "query",
            "SELECT sum(i) FROM range(1000000000000) AS r(i)",
            "--timeout",
            "0.5",
            "--out",
            str(data_root),
        ],
    )
    assert timed_out.exit_code == 1
    assert timed_out.stderr == (
        "Query stopped: it ran longer than 0.5 s. Narrow it, or raise --timeout.\n"
    )
    assert snapshot() == before
    assert tuple(home.iterdir()) == ()
