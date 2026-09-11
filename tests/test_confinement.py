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

* **(a) The entry point.** Registered in :data:`WRITING_ENTRY_POINTS` -- ``sync``,
  ``regen``, ``load``, and (inbox task 5.2) ``drain`` today.
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
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import timedelta, timezone
from pathlib import Path
from typing import Final

import pytest

from fitdocs.athlete import ATHLETE_FILE, load_athlete_inputs
from fitdocs.declaration import DECLARATION_FILENAME
from fitdocs.history import run_history
from fitdocs.inbox import load_inbox_settings, prepare_inbox
from fitdocs.layout import (
    ARCHIVE_DIR,
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
from fitdocs.quarantine import load_quarantine
from fitdocs.settings import load_settings_document
from fitdocs.sync import drain, regen, sync
from fitdocs.tiles import DEFAULT_TILE_SETTINGS, TileSource, TileStore
from tests.fixtures import builder
from tests.load.conftest import ComputingCalculator

# PINNED timezone: a FIXED -06:00 offset (never the system zone) so document
# stems are stable wherever the suite runs.
_TZ = timezone(timedelta(hours=-6))

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


def _wrote_the_history_document(touched: Sequence[str]) -> bool:
    """The ``history`` entry point's own non-vacuity check (load-history
    spec, task 5.4): its measured run wrote the one history document it
    owns. Deliberately distinct from :func:`_wrote_a_workout_document` --
    the history pass writes no ``workouts/*.md`` document at all (Req 7.5),
    so reusing that check here would fail on every genuinely successful run
    and the guard would never be able to tell a real write from a silent
    no-op for this entry point."""
    return f"data/{HISTORY_DIR}/{HISTORY_DOC_STEM}.md" in touched


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


#: Every fitdocs entry point that writes into the data root (Req 7.6).
WRITING_ENTRY_POINTS: Final[tuple[EntryPoint, ...]] = (
    EntryPoint(id="sync", prepare=_nothing, run=_run_sync),
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
    directories for ``drain``. The run is also asserted to have produced its
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
    assert_confined(sandbox, permitted_locations(data_root, configured), before, after)


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
