"""Feature-level determinism, immutability, and purity guarantees (Req 1.5, 13).

Task 7.1 froze the full model + metrics *shape* of every fixture into committed
golden JSON. This suite pins the three cross-cutting properties that make those
snapshots -- and every downstream consumer -- trustworthy:

* **Determinism (Req 13.2, 13.3).** Parsing and computing over identical bytes
  yields byte-identical serialized output, for every fixture and both the
  no-athlete and fully-specified athlete paths. Re-parsing the same bytes twice
  produces independent but identical Activities (no hidden run-to-run state), and
  two *distinct* byte objects with the same content produce identical output.
* **Immutability (Req 1.5).** Parsing from a path never modifies or deletes the
  source file (content hash, size, and mtime all unchanged; the file still
  exists), and parsing raw bytes leaves the input buffer's content intact.
* **Purity (Req 13.1).** The whole parse + compute flow completes with guards
  active that make *any* file write or socket construction raise -- proving the
  library does I/O only to read its input, never writing, prompting, or reaching
  the network. Self-check tests confirm those guards actually trip on a real
  violation, so the purity tests are not vacuous.

The deterministic serializer, fixed athlete, and fixture registry are reused from
:mod:`tests.golden._serialize` (task 7.1) rather than re-derived here, so this
suite and the golden suite agree on exactly what "identical output" means.

Section 5 extends the network-purity guard to the *route-maps* render + compose
path (route-maps Req 4.2). route-maps narrows the package's fully-offline
guarantee to "offline except basemap tile fetch on cache miss": the sole
network-touching module is :mod:`fitdocs.tiles`, which lives OUTSIDE the pure
render layer. That carve-out is asserted here by rendering a map-bearing document
-- so ``compose_map`` actually runs -- under the same ``socket``-blocking guard
and proving no socket is ever constructed.

Section 6 raises determinism from the render function to the *whole written
tree* (wiki-contract Req 1.6): repeated ``sync`` and ``regen`` runs over the same
fixture data root must produce byte-identical documents **and** byte-identical
assets. See that section's header for what it adds over the neighbouring suites
it deliberately does not duplicate.

Section 7 extends the offline guarantee to plugin discovery (plugin-api Req
7.1, 7.2): running :func:`fitdocs.plugins.discover` with nothing installed or
configured constructs no socket -- reusing the same ``_no_socket`` guard
section 3 proves is load-bearing -- and the tool's runtime dependency
footprint (``[project].dependencies`` in ``pyproject.toml``) stays exactly
what it was before this feature, so a new third-party runtime dependency
fails this suite loudly.
"""

from __future__ import annotations

import base64
import builtins
import hashlib
import socket
import tomllib
from collections.abc import Callable, Sequence
from datetime import UTC, timedelta, timezone
from pathlib import Path
from unittest import mock

import pytest

from fitdocs import plugins
from fitdocs.athlete import ATHLETE_FILE, load_athlete_inputs
from fitdocs.declaration import DECLARATION_FILENAME
from fitdocs.ingest import parse_fit
from fitdocs.layout import ASSETS_SUBDIR, WORKOUTS_DIR, doc_path
from fitdocs.metrics import compute_metrics
from fitdocs.metrics.types import AthleteInputs
from fitdocs.render import DocContext, MapData, plan_map, render_document
from fitdocs.sync import SyncReport, regen, sync
from tests.fixtures import builder
from tests.golden._serialize import (
    FIXTURE_BYTES,
    FIXTURE_NAMES,
    GOLDEN_ATHLETE,
    canonical_json,
    to_jsonable,
)

# Both the no-athlete and the fully-specified-athlete computation paths must be
# deterministic and pure (Req 13.2, 13.3): threshold-dependent fields (TRIMP,
# time-in-zone, ...) are exercised only when GOLDEN_ATHLETE is supplied.
_ATHLETES: dict[str, AthleteInputs | None] = {
    "no_athlete": None,
    "with_athlete": GOLDEN_ATHLETE,
}


class _WriteAttempted(AssertionError):
    """Raised by the guarded ``open`` if a write-mode open slips through."""


class _NetworkAttempted(AssertionError):
    """Raised by the guarded ``socket`` factory if a socket is constructed."""


def _result(data: bytes, athlete: AthleteInputs | None) -> tuple[object, str]:
    """Parse ``data`` and project Activity + DerivedMetrics to (structure, text).

    Returns both the JSON-native structure (for structural equality) and the
    canonical JSON text (for byte-identity) so determinism can be asserted at the
    serialized level as well as structurally.
    """
    activity = parse_fit(data)
    metrics = compute_metrics(activity, athlete)
    payload = {"activity": to_jsonable(activity), "metrics": to_jsonable(metrics)}
    return payload, canonical_json(payload)


def _read_only_open(
    file: object, mode: str = "r", *args: object, **kwargs: object
) -> object:
    """A drop-in ``open`` that blocks any write/append/create/update mode.

    Read modes pass straight through to the real ``open`` (captured at call time
    from the unpatched builtin), so legitimate reads keep working while any write
    attempt raises :class:`_WriteAttempted`.
    """
    if any(flag in mode for flag in ("w", "a", "x", "+")):
        raise _WriteAttempted(f"write-mode open attempted: {file!r} (mode {mode!r})")
    return _REAL_OPEN(file, mode, *args, **kwargs)  # type: ignore[operator]


def _no_socket(*args: object, **kwargs: object) -> object:
    """A drop-in ``socket.socket`` factory that refuses to construct a socket."""
    raise _NetworkAttempted("socket construction attempted during parse/compute")


# The genuine builtin, captured once at import (before any test patches it) so the
# read-passthrough path in _read_only_open always reaches the real implementation.
_REAL_OPEN = builtins.open


# --- 1. determinism over identical bytes (Req 13.2, 13.3) --------------------


@pytest.mark.parametrize("athlete_key", list(_ATHLETES))
@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_parse_and_compute_twice_is_byte_identical(name: str, athlete_key: str) -> None:
    """Parse + compute the same bytes twice -> identical structure and JSON text."""
    athlete = _ATHLETES[athlete_key]
    data = FIXTURE_BYTES[name]()

    struct_1, text_1 = _result(data, athlete)
    struct_2, text_2 = _result(data, athlete)

    assert text_1 == text_2  # byte-identical serialized output (13.2)
    assert struct_1 == struct_2  # equal structures (13.3)


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_reparsing_same_bytes_has_no_run_to_run_drift(name: str) -> None:
    """Two separate Activities from the same bytes serialize identically (13.3)."""
    data = FIXTURE_BYTES[name]()

    first = parse_fit(data)
    second = parse_fit(data)

    assert first is not second  # genuinely independent objects, no shared state
    assert to_jsonable(first) == to_jsonable(second)
    assert canonical_json(to_jsonable(first)) == canonical_json(to_jsonable(second))


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_distinct_byte_objects_same_content_produce_identical_output(name: str) -> None:
    """Two different ``bytes`` objects with equal content -> identical output (13.2)."""
    data = FIXTURE_BYTES[name]()
    clone = bytes(bytearray(data))  # a genuinely distinct object, equal content

    assert clone is not data
    assert clone == data

    _, text_data = _result(data, GOLDEN_ATHLETE)
    _, text_clone = _result(clone, GOLDEN_ATHLETE)

    assert text_data == text_clone


# --- 2. source-file immutability (Req 1.5) -----------------------------------


@pytest.mark.parametrize("as_str", [False, True])
@pytest.mark.parametrize("name", ["run", "strength"])
def test_parsing_a_path_never_modifies_or_deletes_the_source(
    name: str, as_str: bool, tmp_path: Path
) -> None:
    """Parsing from a path leaves the source file byte-for-byte intact (Req 1.5)."""
    data = FIXTURE_BYTES[name]()
    source = tmp_path / f"{name}.fit"
    source.write_bytes(data)

    hash_before = hashlib.sha256(source.read_bytes()).hexdigest()
    stat_before = source.stat()
    size_before = stat_before.st_size
    mtime_before = stat_before.st_mtime_ns

    activity = parse_fit(str(source) if as_str else source)

    assert activity is not None
    assert source.exists()  # never deleted (Req 1.5)
    stat_after = source.stat()
    assert hashlib.sha256(source.read_bytes()).hexdigest() == hash_before  # content
    assert stat_after.st_size == size_before  # size
    assert stat_after.st_mtime_ns == mtime_before  # modification time


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_parsing_bytes_does_not_mutate_the_input_buffer(name: str) -> None:
    """Parsing raw bytes never mutates the caller's input buffer (Req 1.5, 13.1)."""
    data = FIXTURE_BYTES[name]()
    hash_before = hashlib.sha256(data).hexdigest()
    len_before = len(data)

    first = parse_fit(data)
    second = parse_fit(data)  # same object handed in twice -> no per-call state

    assert hashlib.sha256(data).hexdigest() == hash_before  # input still intact
    assert len(data) == len_before
    assert to_jsonable(first) == to_jsonable(second)


# --- 3. purity: no writes, no network (Req 13.1) -----------------------------


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_parse_and_compute_perform_no_writes_or_network(name: str) -> None:
    """The whole flow completes with write- and network-blocking guards active."""
    data = FIXTURE_BYTES[name]()

    # Guards tightly scoped to the flow and auto-restored on exit. The pure-bytes
    # input path opens no files at all, so the write guard must pass cleanly.
    with (
        mock.patch("builtins.open", _read_only_open),
        mock.patch("socket.socket", _no_socket),
    ):
        activity = parse_fit(data)
        metrics = compute_metrics(activity, GOLDEN_ATHLETE)

    assert activity is not None
    assert metrics is not None


def test_write_guard_blocks_writes_but_allows_reads(tmp_path: Path) -> None:
    """The write guard is load-bearing: it blocks writes yet lets reads through."""
    existing = tmp_path / "readme.txt"
    existing.write_text("payload")  # created before the guard is active

    with mock.patch("builtins.open", _read_only_open):
        # Reads still succeed through the guard.
        with open(existing, encoding="utf-8") as handle:
            assert handle.read() == "payload"
        # Every write/append/create/update mode is refused. The guard raises
        # before any handle exists, so a context manager is inapplicable here.
        for mode in ("w", "a", "x", "r+", "wb", "ab"):
            with pytest.raises(_WriteAttempted):
                open(tmp_path / "blocked", mode)  # noqa: SIM115

    assert not (tmp_path / "blocked").exists()


def test_network_guard_blocks_socket_construction() -> None:
    """The network guard is load-bearing: constructing a socket raises."""
    with mock.patch("socket.socket", _no_socket), pytest.raises(_NetworkAttempted):
        socket.socket(socket.AF_INET, socket.SOCK_STREAM)


def test_flow_creates_no_files_in_an_empty_cwd(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Parsing + computing every fixture leaves an empty working directory empty."""
    monkeypatch.chdir(tmp_path)
    before = sorted(p.name for p in tmp_path.iterdir())

    for name in FIXTURE_NAMES:
        activity = parse_fit(FIXTURE_BYTES[name]())
        compute_metrics(activity, GOLDEN_ATHLETE)

    after = sorted(p.name for p in tmp_path.iterdir())
    assert before == []
    assert after == before  # no artifacts written to disk


# --- 4. determinism of provenance (Req 13.2) ---------------------------------


@pytest.mark.parametrize("name", FIXTURE_NAMES)
def test_provenance_sha256_is_deterministic_and_is_the_content_hash(name: str) -> None:
    """provenance.sha256 is stable across calls and equals the input content hash."""
    data = FIXTURE_BYTES[name]()
    expected = hashlib.sha256(data).hexdigest()

    first = parse_fit(data).provenance.sha256
    second = parse_fit(data).provenance.sha256

    assert first == second == expected


# --- 5. render + compose are network-free (route-maps Req 4.2) ---------------
#
# route-maps narrows the package's fully-offline guarantee to "offline except
# basemap tile fetch on cache miss" (Req 4.2): the SOLE network-touching module
# is ``fitdocs.tiles`` (the tile fetch), which lives OUTSIDE the pure render
# layer and is orchestrated by the sync engine. This section extends the purity
# guard from parse + compute to the render + compose path a *map* document
# exercises. It builds a real ``MapData`` -- a ``plan_map`` over GPS coordinates
# plus synthetic tile bytes -- and runs ``render_document`` (which calls
# ``compose_map``) under the same ``_no_socket`` guard: the render layer must
# complete with NO socket construction, proving map rendering is fully offline.
#
# The ``fitdocs.tiles`` carve-out is deliberately NOT exercised here: only tile
# *acquisition* (the real ``TileStore`` fetch) touches the network, and only on a
# cache miss with tile requests enabled. A warm cache -- modelled by the fake
# below -- serves bytes with no socket, so every render + compose stays offline.

_RUN_STEM = "2021-09-07-run-1946"  # the run fixture's stable stem under _MAP_TZ
_MAP_TZ = timezone(timedelta(hours=-6))
_SYNTHETIC_TILE = b"\x89PNG\r\n\x1a\n synthetic route-map tile bytes"


class _WarmFakeTiles:
    """A warm fake tile cache: deterministic bytes per ref, never a socket.

    ``resolve`` serves the SAME synthetic bytes for any ref without touching the
    filesystem cache or the network -- exactly as a real ``TileStore`` serves
    already-cached tiles. The only code that would ever open a socket is the real
    store's cold-cache fetch, which this fake stands in for.
    """

    attribution = "© OpenStreetMap contributors"

    def resolve(self, refs: Sequence[object]) -> dict[object, bytes]:
        return {ref: _SYNTHETIC_TILE for ref in refs}


def _map_ctx(data: bytes) -> DocContext:
    """A run ``DocContext`` carrying real ``MapData`` composed from its own GPS.

    ``plan_map`` over the fixture's decoded position channels yields a real plan;
    pairing every planned tile with synthetic bytes gives a ``MapData`` that
    forces ``compose_map`` to actually run inside ``render_document`` -- so the
    offline check below is not vacuous (the map path is genuinely exercised, not
    skipped).
    """
    activity = parse_fit(data)
    metrics = compute_metrics(activity, None)
    plan = plan_map(activity.samples.latitude_deg, activity.samples.longitude_deg)
    assert plan is not None  # the run fixture carries a complete GPS route
    map_data = MapData(
        plan=plan,
        tiles=tuple((ref, _SYNTHETIC_TILE) for ref in plan.tiles),
        attribution="© OpenStreetMap contributors",
    )
    return DocContext(
        activity=activity,
        metrics=metrics,
        athlete=None,
        doc_stem="run",
        source_refs=("fit-archive/aaaa.fit",),
        tz=UTC,
        map_data=map_data,
    )


def test_render_plus_compose_perform_no_network() -> None:
    """``render_document`` over a map-bearing context composes the map offline.

    A real ``MapData`` (``plan_map`` + synthetic tiles) is rendered with the
    socket guard active: the render layer NEVER constructs a socket, so the whole
    render + compose path -- ``compose_map`` embedding the tiles included -- is
    network-free (Req 4.2). Non-vacuous: the guard is load-bearing (proven by
    ``test_network_guard_blocks_socket_construction``), and the assertions confirm
    the map genuinely composed rather than being skipped.
    """
    ctx = _map_ctx(builder.run_fit_bytes())
    tile_uri = "data:image/png;base64," + base64.b64encode(_SYNTHETIC_TILE).decode(
        "ascii"
    )

    with mock.patch("socket.socket", _no_socket):
        rendered = render_document(ctx)

    # The map genuinely composed under the guard: the section, exactly one map
    # asset, and the inline tile data-URI are all present (so this is not vacuous).
    assert "## Map" in rendered.markdown
    map_assets = [a for a in rendered.assets if a.rel_path.endswith("-map.svg")]
    assert len(map_assets) == 1
    assert tile_uri in map_assets[0].content


def test_sync_over_a_warm_fake_cache_is_network_free(tmp_path: Path) -> None:
    """A full ``sync`` of a GPS activity over a warm fake cache opens no socket.

    The warm fake ``TileSource`` serves tile bytes without a socket (as a warm
    real cache would), so the engine's map path resolves and composes with the
    socket guard active: the document and its ``-map.svg`` asset are written with
    zero network access. Only the real ``TileStore``'s cold-cache fetch -- the
    ``fitdocs.tiles`` carve-out -- would ever open a socket (Req 4.2).
    """
    source = tmp_path / "src"
    data_root = tmp_path / "data"
    data_root.mkdir()
    source.mkdir(parents=True, exist_ok=True)
    (source / "run.fit").write_bytes(builder.run_fit_bytes())

    with mock.patch("socket.socket", _no_socket):
        report = sync(
            source, data_root, athlete=None, tz=_MAP_TZ, tiles=_WarmFakeTiles()
        )

    assert report.failures == ()
    assert report.warnings == ()
    doc = doc_path(data_root, _RUN_STEM)
    assert doc.is_file()
    assert "## Map" in doc.read_text(encoding="utf-8")
    map_asset = data_root / WORKOUTS_DIR / ASSETS_SUBDIR / f"{_RUN_STEM}-map.svg"
    assert map_asset.is_file()


# --- 6. whole-tree repeat-run byte identity (wiki-contract Req 1.6) ----------
#
# Sections 1-4 pin determinism at the *parse + compute* level and section 5 pins
# it for a single ``render_document`` call. wiki-contract Req 1.6 states the
# guarantee one level up, over everything a run writes: rendering the same inputs
# repeatedly keeps producing byte-identical output. This section pins that for the
# two engine entry points a user actually runs -- ``sync`` and ``regen`` -- and
# compares EVERY byte of EVERY document and EVERY asset, assets being as much a
# part of the written output as the markdown.
#
# It is the durable half of the consolidation checkpoint: the contract refactor
# moved frontmatter reading, region policy, source-ref resolution, and session-uuid
# formatting behind ``fitdocs.contract``, and the only way that is safe is if the
# tree a run writes is bit-for-bit what it was. The committed goldens under
# ``tests/render/golden_docs/`` pin the *absolute* bytes of a render; this pins the
# *relative* property -- run it again, get the same bytes -- which goldens cannot
# express because they compare a single run against a file.
#
# Deliberately NOT duplicated from the neighbouring suites, each of which covers a
# strictly weaker slice:
#
# * ``tests.test_sync_e2e``'s
#   ``test_double_sync_leaves_data_root_byte_identical_and_all_skipped``
#   re-runs ``sync`` over the SAME root, where every source is already archived --
#   so the second run skips everything and writes nothing. It proves the skip
#   policy, not that a genuine re-render reproduces the bytes.
# * ``tests.test_route_maps_e2e.test_two_full_runs_over_warm_cache_are_byte_identical``
#   does compare two writing runs, but only documents and ``-map.svg`` assets, with
#   no athlete inputs -- so hero charts and the athlete-gated zone strips are
#   outside its comparison.
#
# What is added here: writing runs whose comparison spans the whole ``workouts/``
# tree (documents, hero charts, zone strips, and route maps alike), athlete inputs
# supplied so the athlete-gated assets exist to be compared, and ``regen`` -- the
# entry point that re-renders every document unconditionally, and therefore the
# only one that exercises re-render determinism against documents that already
# exist on disk.
#
# Everything stays offline: the warm fake tile source of section 5 serves tile
# bytes without a socket, exactly as a warm real cache does.

#: The fixture set staged for the repeat-run comparisons: a GPS run (hero chart +
#: route map), a GPS-less ride, a strength session, and a session-less minimal
#: file -- every modality the render layer branches on, so the compared tree is
#: broad rather than a single happy-path document.
_REPEAT_RUN_FIXTURES: dict[str, Callable[[], bytes]] = {
    "run.fit": builder.run_fit_bytes,
    "ride.fit": builder.ride_fit_bytes,
    "strength.fit": builder.strength_fit_bytes,
    "minimal.fit": builder.minimal_fit_bytes,
}


def _stage_repeat_run_sandbox(sandbox: Path) -> tuple[Path, Path]:
    """Build a fixture ``(data_root, source_dir)`` pair of siblings under ``sandbox``.

    The staged ``.fit`` set covers every modality the render layer branches on, and
    the ``athlete.toml`` is what makes the comparison cover the athlete-gated output
    as well: strictly-ascending ``hr_zones`` unlock the ``-zones.svg`` zone strip and
    the resting/max HR pair unlocks the TRIMP chip, so both the extra asset and the
    extra document content land inside the compared bytes. The source directory is a
    *sibling* of the data root, exactly as a user's export folder is, so nothing the
    engine reads sits inside the tree being compared.
    """
    data_root = sandbox / "data"
    data_root.mkdir(parents=True, exist_ok=True)
    (data_root / ATHLETE_FILE).write_text(
        "resting_hr_bpm = 45\nmax_hr_bpm = 190\nhr_zones = [110, 125, 140, 155, 170]\n",
        encoding="utf-8",
    )
    source = sandbox / "src"
    source.mkdir(parents=True, exist_ok=True)
    for name, make_bytes in _REPEAT_RUN_FIXTURES.items():
        (source / name).write_bytes(make_bytes())
    return data_root, source


def _written_tree(data_root: Path) -> dict[str, bytes]:
    """Every document and asset under ``workouts/`` as ``{rel-posix-path: bytes}``.

    The walk is recursive and unfiltered by suffix, so the mapping holds the full
    byte content of every markdown document *and* every asset (hero chart, zone
    strip, route map) the run wrote -- and any file a future render adds under
    ``workouts/`` joins the comparison automatically rather than escaping it.
    Comparing the mappings therefore compares every byte of every written file, and
    the key sets compare the file inventory, so an added or dropped file fails just
    as a changed byte does.
    """
    workouts = data_root / WORKOUTS_DIR
    return {
        path.relative_to(data_root).as_posix(): path.read_bytes()
        for path in sorted(workouts.rglob("*"))
        if path.is_file()
    }


def _assert_covers_documents_and_every_asset_kind(tree: dict[str, bytes]) -> None:
    """Assert the compared tree holds a document and all three asset kinds.

    Non-vacuity for every comparison below: byte-identity over an empty or
    document-only mapping would pass while proving nothing about assets, so each
    comparison first establishes that markdown, a hero chart, a zone strip, and a
    route map are all genuinely present in the bytes being compared.
    """
    # Excludes the ownership declaration: since task 4.2 it is written on every
    # run, so it would satisfy this check even if no document were rendered.
    assert any(
        key.endswith(".md") and not key.endswith(f"/{DECLARATION_FILENAME}")
        for key in tree
    )
    for suffix in ("-hero.svg", "-zones.svg", "-map.svg"):
        assert any(key.endswith(suffix) for key in tree), f"no {suffix} asset written"


def _run_sync(source: Path, data_root: Path) -> SyncReport:
    """Drive ``sync`` as the CLI does -- athlete loaded from the root, offline."""
    return sync(
        source,
        data_root,
        athlete=load_athlete_inputs(data_root),
        tz=_MAP_TZ,
        tiles=_WarmFakeTiles(),
    )


def _run_regen(data_root: Path) -> SyncReport:
    """Drive ``regen`` as the CLI does -- athlete loaded from the root, offline."""
    return regen(
        data_root,
        athlete=load_athlete_inputs(data_root),
        tz=_MAP_TZ,
        tiles=_WarmFakeTiles(),
    )


def test_two_full_syncs_write_byte_identical_documents_and_assets(
    tmp_path: Path,
) -> None:
    """Two full ``sync`` runs of identical inputs write identical bytes (Req 1.6).

    The two runs go into SEPARATE data roots so both genuinely write (a re-sync of
    the same root would skip every already-archived source and prove nothing), and
    the comparison spans the whole ``workouts/`` tree: documents, hero charts,
    athlete-gated zone strips, and route maps.

    Mutation caught: any run-to-run variability entering the written tree -- a
    timestamp, a uuid, a set-ordering leak, an unstable float format -- makes some
    document or asset differ between the roots. The non-vacuity check first proves
    all three asset kinds are inside the comparison."""
    trees: list[dict[str, bytes]] = []
    for name in ("first", "second"):
        data_root, source = _stage_repeat_run_sandbox(tmp_path / name)
        with mock.patch("socket.socket", _no_socket):
            report = _run_sync(source, data_root)
        assert len(report.written) == len(_REPEAT_RUN_FIXTURES)
        assert report.failures == ()
        assert report.warnings == ()
        trees.append(_written_tree(data_root))

    _assert_covers_documents_and_every_asset_kind(trees[0])
    assert trees[0] == trees[1]


def test_regen_rewrites_every_document_and_asset_byte_for_byte(tmp_path: Path) -> None:
    """``regen`` reproduces the synced tree byte-for-byte, repeatedly (Req 1.6).

    Regeneration re-renders every document unconditionally from the archive alone,
    so unlike a second ``sync`` it really does rewrite -- which makes it the entry
    point that proves a *re-render over existing documents* lands on exactly the
    bytes the first render produced. Two consecutive regenerations are compared as
    well, so drift that only appears once a document already exists (a merge that
    re-wraps a region, a source history that re-orders) is caught too.

    Mutation caught: any difference between rendering fresh and re-rendering in
    place -- a region merge that reflows content, a frontmatter key whose order or
    formatting depends on the prior document, an asset rewritten with different
    bytes -- makes a tree differ from the one before it."""
    data_root, source = _stage_repeat_run_sandbox(tmp_path)

    with mock.patch("socket.socket", _no_socket):
        synced = _run_sync(source, data_root)
        after_sync = _written_tree(data_root)

        first_regen = _run_regen(data_root)
        after_first_regen = _written_tree(data_root)

        second_regen = _run_regen(data_root)
        after_second_regen = _written_tree(data_root)

    # Every run genuinely wrote every document: regen has no skip path, so a
    # vacuous "nothing happened, nothing changed" pass is ruled out.
    for report in (synced, first_regen, second_regen):
        assert len(report.written) == len(_REPEAT_RUN_FIXTURES)
        assert report.failures == ()
        assert report.warnings == ()

    _assert_covers_documents_and_every_asset_kind(after_sync)
    assert after_first_regen == after_sync
    assert after_second_regen == after_first_regen


def test_the_repeat_run_comparison_detects_a_single_changed_byte(
    tmp_path: Path,
) -> None:
    """The comparison above is byte-sensitive -- in a document AND in an asset.

    Proves the guard is load-bearing rather than a mapping that would compare equal
    regardless: after a real ``sync``, flipping ONE byte of a written document, and
    separately one byte of a written SVG asset, each makes :func:`_written_tree`
    differ from the snapshot taken before it. Without this, a helper that (say)
    silently skipped assets or compared only file names would certify byte-identity
    it never checked.
    """
    data_root, source = _stage_repeat_run_sandbox(tmp_path)
    with mock.patch("socket.socket", _no_socket):
        _run_sync(source, data_root)
    baseline = _written_tree(data_root)
    _assert_covers_documents_and_every_asset_kind(baseline)

    for suffix in (".md", "-map.svg"):
        key = next(
            candidate for candidate in sorted(baseline) if candidate.endswith(suffix)
        )
        target = data_root / key
        original = target.read_bytes()
        # One byte, changed in place: same path, same length, different content.
        flipped = bytes([original[0] ^ 0x01]) + original[1:]
        assert flipped != original
        target.write_bytes(flipped)

        assert _written_tree(data_root) != baseline  # the single byte is seen

        target.write_bytes(original)  # restore, so the next suffix starts clean
        assert _written_tree(data_root) == baseline


# --- 7. plugin discovery stays offline and dependency-free (plugin-api Req 7.1, 7.2)
#
# Sections 1-6 pin the parse/compute/render/write path's offline and
# byte-identity guarantees. plugin-api adds a second entry point that runs
# before any of that -- ``fitdocs.plugins.discover()`` -- and Req 7.1/7.2 state
# it must cost the tool nothing: no network access, ever, and no new
# third-party runtime dependency to support it. Both are asserted here rather
# than in ``tests/test_plugins.py`` because they are cross-cutting
# preserved-guarantee properties, exactly like the rest of this suite, not
# discovery *behavior*.

_PYPROJECT_PATH = Path(__file__).resolve().parents[1] / "pyproject.toml"

#: The runtime dependency footprint as it stood before plugin-api. Any name
#: added to ``[project].dependencies`` (or a runtime
#: ``[project.optional-dependencies]`` group) to support plugin discovery
#: changes this set and fails the test below (Req 7.2).
_BASELINE_RUNTIME_DEPENDENCIES = frozenset(
    {
        "garmin-fit-sdk>=21.208.0",
        "typer>=0.12",
        "rich>=13",
        "pyyaml>=6.0",
        "tomli-w>=1.0",
    }
)


def test_plugin_discovery_performs_no_network_access(tmp_path: Path) -> None:
    """``discover()`` with nothing installed or configured builds no socket.

    Reuses ``_no_socket``, the same guard
    ``test_network_guard_blocks_socket_construction`` proves is load-bearing
    above, so a real regression -- discovery reaching for the network on an
    empty entry-point scan and settings read -- would raise
    ``_NetworkAttempted`` here (Req 7.1).
    """
    data_root = tmp_path / "data"
    data_root.mkdir()

    with mock.patch("socket.socket", _no_socket):
        report = plugins.discover(data_root, plugins.DEFAULT_PLUGIN_SETTINGS)

    assert report.errors == ()


def test_no_new_third_party_runtime_dependency_was_added() -> None:
    """``[project].dependencies`` is unchanged from its pre-plugin-api baseline.

    Mutation caught: adding any third-party package to ``dependencies`` -- or a
    new runtime ``optional-dependencies`` group -- to support discovery fails
    this test outright, rather than only being caught by review (Req 7.2).
    """
    with _PYPROJECT_PATH.open("rb") as handle:
        document = tomllib.load(handle)

    dependencies = frozenset(document["project"]["dependencies"])
    assert dependencies == _BASELINE_RUNTIME_DEPENDENCIES

    # No runtime optional-dependency group was introduced either.
    assert document["project"].get("optional-dependencies", {}) == {}
