"""Tests for the data-root layout, activity identity, and document naming.

These lock the pure helpers in :mod:`fitdocs.layout` (design: DataRootLayout,
``src/fitdocs/layout.py``) that the sync engine depends on for output placement
and stable identity (Req 2.4-2.7, 3.1, 3.6, 5.6):

* ``sport_slug`` -- ``"strength"`` for the strength modality, else the normalized
  sport label lowercased (2.4);
* ``activity_uid`` -- the recorded ``SESSION UUID`` developer field as a canonical
  UUID string when present and well-formed, else the content hash; malformed
  values never raise, they fall back to the hash (3.6, 5.6);
* ``doc_stem`` -- date-prefixed kebab-case from *local* start time, an
  identity-prefixed undated fallback that never fabricates a date, and a
  deterministic collision suffix that depends only on recorded identity (2.5,
  2.6);
* the path/reference helpers -- ``doc_path``, ``archive_path`` (real filesystem
  paths) and ``asset_rel_path``, ``source_ref`` (POSIX, data-root-relative
  strings so moving the whole data root never breaks a document) (2.7, 3.1);
* the ownership constants -- ``OWNED_PATHS`` (every path the contract calls
  fitdocs-owned, covering each write site and already admitting the ownership
  declarations task 4.2 writes) and ``DECLARED_DIRS`` (the owned top-level
  directories that receive one), plus the exclusions that matter: the user-owned
  data-root files and the source-tree ``.fitdocs/data-root`` pointer, which is a
  different thing from the ``.fitdocs/`` state directory *inside* the data root
  (wiki-contract Req 7.5, 7.6, 3.1).

The module is pure (no file I/O; ``taken`` is an injected predicate), so every
case is exercised by constructing model dataclasses directly.
"""

from __future__ import annotations

import inspect
import uuid
from datetime import UTC, datetime, timedelta, timezone, tzinfo
from pathlib import Path
from types import MappingProxyType
from zoneinfo import ZoneInfo

from fitdocs import (
    SCHEMA_VERSION,
    Activity,
    Modality,
    Provenance,
    Samples,
    SessionSummary,
    Sport,
    layout,
)
from fitdocs.athlete import ATHLETE_FILE
from fitdocs.config import POINTER_RELPATH
from fitdocs.layout import (
    ARCHIVE_DIR,
    ASSETS_SUBDIR,
    CACHE_DIR,
    DECLARED_DIRS,
    DEFAULT_INBOX_DIR,
    OWNED_PATHS,
    SETTINGS_FILE,
    TILE_CACHE_DIR,
    TOOL_STATE_DIR,
    WORKOUTS_DIR,
    activity_uid,
    archive_path,
    asset_rel_path,
    doc_path,
    doc_stem,
    quarantine_path,
    settings_path,
    source_ref,
    sport_slug,
    tile_cache_path,
)

# A known 16-byte identifier: bytes 0..15 map to a clean canonical UUID string.
_UUID_BYTES: tuple[int, ...] = tuple(range(16))
_CANONICAL_UUID = "00010203-0405-0607-0809-0a0b0c0d0e0f"

_SHA = "b" * 64  # stand-in content hash used as the identity fallback


# --- construction helpers ---------------------------------------------------


def _empty_samples() -> Samples:
    return Samples(
        time_s=(),
        heart_rate_bpm=(),
        power_w=(),
        cadence_rpm=(),
        speed_mps=(),
        distance_m=(),
        altitude_m=(),
        latitude_deg=(),
        longitude_deg=(),
        temperature_c=(),
    )


def _empty_summary() -> SessionSummary:
    return SessionSummary(
        sport=None,
        sub_sport=None,
        start_time=None,
        total_elapsed_time_s=None,
        total_timer_time_s=None,
        total_distance_m=None,
        total_calories_kcal=None,
        total_ascent_m=None,
        total_descent_m=None,
        avg_heart_rate_bpm=None,
        max_heart_rate_bpm=None,
        avg_power_w=None,
        max_power_w=None,
        avg_cadence_rpm=None,
        max_cadence_rpm=None,
        avg_speed_mps=None,
        max_speed_mps=None,
    )


def _activity(
    *,
    sport: Sport = Sport.RUN,
    modality: Modality = Modality.RUN,
    start_time: datetime | None = None,
    developer_fields: dict[str, object] | None = None,
    sha256: str = _SHA,
) -> Activity:
    return Activity(
        schema_version=SCHEMA_VERSION,
        provenance=Provenance(sha256=sha256, source_path=None, decode_errors=()),
        sport=sport,
        modality=modality,
        is_indoor=False,
        start_time=start_time,
        summary=_empty_summary(),
        laps=(),
        samples=_empty_samples(),
        sets=(),
        devices=(),
        developer_fields=MappingProxyType(dict(developer_fields or {})),
    )


def _never_taken(stem: str) -> bool:
    return False


# --- layout constants -------------------------------------------------------


def test_layout_constants() -> None:
    assert WORKOUTS_DIR == "workouts"
    assert ASSETS_SUBDIR == "assets"
    assert ARCHIVE_DIR == "fit-archive"
    assert TILE_CACHE_DIR == ".cache/tiles"


# --- sport_slug -------------------------------------------------------------


def test_sport_slug_run() -> None:
    assert sport_slug(_activity(sport=Sport.RUN, modality=Modality.RUN)) == "run"


def test_sport_slug_ride() -> None:
    assert sport_slug(_activity(sport=Sport.RIDE, modality=Modality.BIKE)) == "ride"


def test_sport_slug_strength_uses_modality_not_sport() -> None:
    # A strength session's raw sport is often "Workout"; the slug is driven by the
    # strength MODALITY, not the sport label.
    activity = _activity(sport=Sport.WORKOUT, modality=Modality.STRENGTH)
    assert sport_slug(activity) == "strength"


def test_sport_slug_non_strength_uses_lowercased_sport() -> None:
    assert sport_slug(_activity(sport=Sport.SWIM, modality=Modality.SWIM)) == "swim"
    assert sport_slug(_activity(sport=Sport.HIKE, modality=Modality.OTHER)) == "hike"


# --- activity_uid -----------------------------------------------------------


def test_activity_uid_from_well_formed_session_uuid() -> None:
    activity = _activity(developer_fields={"SESSION UUID": _UUID_BYTES})
    result = activity_uid(activity, _SHA)
    # Canonical, lowercase 8-4-4-4-12 form, independently derived from the bytes.
    assert result == str(uuid.UUID(bytes=bytes(_UUID_BYTES)))
    assert result == _CANONICAL_UUID
    assert result != _SHA


def test_activity_uid_falls_back_to_hash_when_absent() -> None:
    assert activity_uid(_activity(developer_fields={}), _SHA) == _SHA
    other = _activity(developer_fields={"AVG METs": 6.2})
    assert activity_uid(other, _SHA) == _SHA


def test_activity_uid_falls_back_when_wrong_length() -> None:
    short = _activity(developer_fields={"SESSION UUID": tuple(range(15))})
    long = _activity(developer_fields={"SESSION UUID": tuple(range(17))})
    assert activity_uid(short, _SHA) == _SHA
    assert activity_uid(long, _SHA) == _SHA


def test_activity_uid_falls_back_when_byte_out_of_range() -> None:
    over = _activity(developer_fields={"SESSION UUID": (256, *range(15))})
    under = _activity(developer_fields={"SESSION UUID": (-1, *range(15))})
    assert activity_uid(over, _SHA) == _SHA
    assert activity_uid(under, _SHA) == _SHA


def test_activity_uid_falls_back_when_element_not_int() -> None:
    floaty = _activity(developer_fields={"SESSION UUID": (1.5, *range(15))})
    stringy = _activity(developer_fields={"SESSION UUID": ("x", *range(15))})
    assert activity_uid(floaty, _SHA) == _SHA
    assert activity_uid(stringy, _SHA) == _SHA


def test_activity_uid_falls_back_when_wrong_type() -> None:
    # A scalar, a string, and a list are all "not the recorded 16-tuple".
    assert activity_uid(_activity(developer_fields={"SESSION UUID": 42}), _SHA) == _SHA
    assert (
        activity_uid(_activity(developer_fields={"SESSION UUID": "nope"}), _SHA) == _SHA
    )
    listed = _activity(developer_fields={"SESSION UUID": list(range(16))})
    assert activity_uid(listed, _SHA) == _SHA


def test_activity_uid_never_raises_on_malformed() -> None:
    for value in (None, (), (1, 2, 3), object(), {"a": 1}):
        activity = _activity(developer_fields={"SESSION UUID": value})
        # Must not raise; malformed always degrades to the hash.
        assert activity_uid(activity, _SHA) == _SHA


# --- doc_stem: timed --------------------------------------------------------


def test_doc_stem_timed_no_shift_in_utc() -> None:
    activity = _activity(
        sport=Sport.RUN,
        modality=Modality.RUN,
        start_time=datetime(2026, 7, 12, 14, 30, tzinfo=UTC),
    )
    stem = doc_stem(activity, _SHA, UTC, _never_taken)
    assert stem == "2026-07-12-run-1430"


def test_doc_stem_timed_local_conversion_rolls_date_back() -> None:
    # 01:30 UTC is the previous evening in a UTC-6 zone -- the LOCAL date/time is
    # what names the document, so the date rolls back to the 11th.
    minus_six = timezone(timedelta(hours=-6))
    activity = _activity(
        sport=Sport.RUN,
        modality=Modality.RUN,
        start_time=datetime(2026, 7, 12, 1, 30, tzinfo=UTC),
    )
    stem = doc_stem(activity, _SHA, minus_six, _never_taken)
    assert stem == "2026-07-11-run-1930"


def test_doc_stem_timed_with_named_zone() -> None:
    # America/Denver observes MDT (UTC-6) in July; 06:15 UTC -> 00:15 local, same
    # calendar day boundary crossed backwards.
    denver: tzinfo = ZoneInfo("America/Denver")
    activity = _activity(
        sport=Sport.RIDE,
        modality=Modality.BIKE,
        start_time=datetime(2026, 7, 12, 6, 15, tzinfo=UTC),
    )
    stem = doc_stem(activity, _SHA, denver, _never_taken)
    assert stem == "2026-07-12-ride-0015"


def test_doc_stem_timed_zero_padded_time() -> None:
    activity = _activity(
        sport=Sport.RUN,
        modality=Modality.RUN,
        start_time=datetime(2026, 1, 5, 7, 3, tzinfo=UTC),
    )
    stem = doc_stem(activity, _SHA, UTC, _never_taken)
    assert stem == "2026-01-05-run-0703"


def test_doc_stem_timed_strength_uses_strength_slug() -> None:
    activity = _activity(
        sport=Sport.WORKOUT,
        modality=Modality.STRENGTH,
        start_time=datetime(2026, 7, 12, 17, 45, tzinfo=UTC),
    )
    stem = doc_stem(activity, _SHA, UTC, _never_taken)
    assert stem == "2026-07-12-strength-1745"


# --- doc_stem: undated ------------------------------------------------------


def test_doc_stem_undated_uses_identity_prefix_not_a_date() -> None:
    activity = _activity(sport=Sport.RUN, modality=Modality.RUN, start_time=None)
    stem = doc_stem(activity, _CANONICAL_UUID, UTC, _never_taken)
    assert stem == f"undated-run-{_CANONICAL_UUID[:12]}"
    # No fabricated date: the stem must not begin with a YYYY- prefix.
    assert not stem[:4].isdigit()


def test_doc_stem_undated_strength() -> None:
    activity = _activity(
        sport=Sport.WORKOUT, modality=Modality.STRENGTH, start_time=None
    )
    stem = doc_stem(activity, _SHA, UTC, _never_taken)
    assert stem == f"undated-strength-{_SHA[:12]}"


# --- doc_stem: collision policy ---------------------------------------------


def test_doc_stem_collision_appends_identity_suffix() -> None:
    activity = _activity(
        sport=Sport.RUN,
        modality=Modality.RUN,
        start_time=datetime(2026, 7, 12, 14, 30, tzinfo=UTC),
    )
    base = "2026-07-12-run-1430"
    stem = doc_stem(activity, _CANONICAL_UUID, UTC, lambda s: s == base)
    assert stem == f"{base}-{_CANONICAL_UUID[:8]}"


def test_doc_stem_collision_is_deterministic() -> None:
    activity = _activity(
        sport=Sport.RUN,
        modality=Modality.RUN,
        start_time=datetime(2026, 7, 12, 14, 30, tzinfo=UTC),
    )
    always_taken = lambda s: True  # noqa: E731 - inline predicate for the test
    first = doc_stem(activity, _CANONICAL_UUID, UTC, always_taken)
    second = doc_stem(activity, _CANONICAL_UUID, UTC, always_taken)
    assert first == second == f"2026-07-12-run-1430-{_CANONICAL_UUID[:8]}"


def test_doc_stem_no_collision_returns_base() -> None:
    activity = _activity(
        sport=Sport.RUN,
        modality=Modality.RUN,
        start_time=datetime(2026, 7, 12, 14, 30, tzinfo=UTC),
    )
    stem = doc_stem(activity, _CANONICAL_UUID, UTC, _never_taken)
    assert stem == "2026-07-12-run-1430"


def test_doc_stem_undated_collision_appends_suffix() -> None:
    activity = _activity(sport=Sport.RUN, modality=Modality.RUN, start_time=None)
    base = f"undated-run-{_CANONICAL_UUID[:12]}"
    stem = doc_stem(activity, _CANONICAL_UUID, UTC, lambda s: s == base)
    assert stem == f"{base}-{_CANONICAL_UUID[:8]}"


# --- path / reference helpers -----------------------------------------------


def test_doc_path_lives_under_workouts() -> None:
    root = Path("/data/root")
    assert doc_path(root, "2026-07-12-run-1430") == (
        root / "workouts" / "2026-07-12-run-1430.md"
    )


def test_archive_path_lives_under_fit_archive() -> None:
    root = Path("/data/root")
    assert archive_path(root, _SHA) == root / "fit-archive" / f"{_SHA}.fit"


def test_asset_rel_path_is_posix_and_doc_relative() -> None:
    rel = asset_rel_path("2026-07-12-run-1430", "hero")
    assert rel == "assets/2026-07-12-run-1430-hero.svg"
    # POSIX separators only -- never a backslash, so links survive on any OS.
    assert "\\" not in rel
    # Doc-relative: joined onto the document's own directory it lands in the
    # workouts/assets area beside the doc.
    root = Path("/data/root")
    doc = doc_path(root, "2026-07-12-run-1430")
    resolved = doc.parent / rel
    assert resolved == root / "workouts" / "assets" / "2026-07-12-run-1430-hero.svg"


def test_source_ref_is_data_root_relative_posix() -> None:
    ref = source_ref(_SHA)
    assert ref == f"fit-archive/{_SHA}.fit"
    assert "\\" not in ref
    # Consistent with the real archive path taken relative to the data root.
    root = Path("/data/root")
    assert archive_path(root, _SHA).relative_to(root).as_posix() == ref


# --- tile_cache_path --------------------------------------------------------


def test_tile_cache_path_is_provider_keyed_zxy_under_data_root() -> None:
    root = Path("/data/root")
    path = tile_cache_path(root, "osm", 12, 23, 45)
    # Provider name, then z/x/y, then a .png leaf -- the slippy-tile cache layout.
    assert path == root / ".cache" / "tiles" / "osm" / "12" / "23" / "45.png"
    assert path.suffix == ".png"
    # Anchored under the data root: never inside a code repo or the package
    # installation (Req 3.3). The whole tree resolves relative to data_root.
    assert path.is_relative_to(root)
    assert path.relative_to(root) == Path(".cache/tiles/osm/12/23/45.png")
    # The cache root is exactly the TILE_CACHE_DIR contract.
    assert path.relative_to(root).parts[:2] == (".cache", "tiles")


def test_tile_cache_path_separates_providers() -> None:
    root = Path("/data/root")
    osm = tile_cache_path(root, "osm", 5, 1, 2)
    topo = tile_cache_path(root, "opentopomap", 5, 1, 2)
    # Same tile coordinate, different providers -> different subdirectories, so
    # switching providers never mixes basemap skins in one cache tree.
    assert osm != topo
    # The per-provider directory sits directly under <data-root>/.cache/tiles/.
    provider_root = root / ".cache" / "tiles"
    assert osm.relative_to(provider_root).parts[0] == "osm"
    assert topo.relative_to(provider_root).parts[0] == "opentopomap"


def test_tile_cache_path_coordinates_are_plain_ints() -> None:
    root = Path("/data/root")
    # Distinct coordinates land in distinct paths; ints render as bare path parts.
    a = tile_cache_path(root, "osm", 0, 0, 0)
    b = tile_cache_path(root, "osm", 17, 65535, 43210)
    assert a == root / ".cache" / "tiles" / "osm" / "0" / "0" / "0.png"
    assert b == root / ".cache" / "tiles" / "osm" / "17" / "65535" / "43210.png"
    assert a != b


def test_tile_cache_path_never_inside_repo_or_package() -> None:
    # Whatever data root the caller supplies, the tile lands beneath it -- the
    # helper only ever prepends provider/z/x/y under TILE_CACHE_DIR (Req 3.3).
    for root in (Path("/data/root"), Path("/Users/someone/fit-data")):
        path = tile_cache_path(root, "osm", 3, 4, 5)
        assert path.is_relative_to(root)
        # Not anchored anywhere the source lives: no source-tree marker on the way.
        parts = path.relative_to(root).parts
        assert "src" not in parts
        assert "site-packages" not in parts


# --- ownership constants: OWNED_PATHS / DECLARED_DIRS (Req 7.5, 7.6) --------


def _owned_locations(root: Path) -> tuple[Path, ...]:
    """The owned paths as real locations under a data root."""
    return tuple(root / owned for owned in OWNED_PATHS)


def _is_owned(path: Path, root: Path) -> bool:
    """Is ``path`` an owned location itself, or anything beneath one?"""
    return any(
        path == owned or owned in path.parents for owned in _owned_locations(root)
    )


def test_owned_paths_name_every_fitdocs_owned_location() -> None:
    """The contract's owned set: documents, assets, archive, cache, tool state.

    Each entry is a data-root-relative POSIX *directory prefix* (trailing slash),
    so everything beneath it is owned too -- that is what makes the set admit
    files it does not enumerate, such as the per-directory ownership
    declarations. The entries are composed from the individual directory
    constants rather than respelled, so the two can never drift.
    """
    assert OWNED_PATHS == (
        "workouts/",
        "workouts/assets/",
        "fit-archive/",
        ".cache/",
        ".fitdocs/",
    )
    # Composed from the directory constants, never respelled -- renaming a
    # directory constant moves its owned prefix with it.
    for directory in (WORKOUTS_DIR, ARCHIVE_DIR, CACHE_DIR, TOOL_STATE_DIR):
        assert f"{directory}/" in OWNED_PATHS
    assert f"{WORKOUTS_DIR}/{ASSETS_SUBDIR}/" in OWNED_PATHS
    assert len(set(OWNED_PATHS)) == len(OWNED_PATHS)  # no duplicates
    for owned in OWNED_PATHS:
        assert owned.endswith("/")
        assert not owned.startswith("/")  # data-root-relative, never absolute
        assert "\\" not in owned  # POSIX separators only


def test_owned_paths_cover_every_path_the_engines_write() -> None:
    """Every path the layout composes for a write lies inside an owned location.

    Mutation caught: dropping an entry from ``OWNED_PATHS`` (or moving an output
    out from under one) would leave a real write site unowned, which is exactly
    the confinement guard's failure mode.
    """
    root = Path("/data/root")
    stem = "2026-07-12-run-1430"
    document = doc_path(root, stem)
    assert _is_owned(document, root)
    assert _is_owned(document.parent / asset_rel_path(stem, "hero"), root)
    assert _is_owned(archive_path(root, _SHA), root)
    assert _is_owned(tile_cache_path(root, "osm", 12, 23, 45), root)


def test_owned_paths_admit_the_declaration_files_task_4_2_writes() -> None:
    """An ``AGENTS.md`` in any declared directory is already inside the owned set.

    The ownership declarations are not written yet (task 4.2 does that), but the
    owned-path set must admit them in advance, or the confinement guard would
    start failing the moment sync begins writing them.
    """
    root = Path("/data/root")
    for directory in DECLARED_DIRS:
        assert _is_owned(root / directory / "AGENTS.md", root)


def test_owned_paths_exclude_the_user_owned_data_root_files() -> None:
    """The shared/user-owned files at the data root are deliberately not owned.

    ``fitdocs.toml`` and ``athlete.toml`` are the user's (Req 2.7): fitdocs reads
    them and, for the profile, writes only its own keys. They are not part of the
    regenerated, tool-owned tree, so they must not appear inside ``OWNED_PATHS``.
    """
    root = Path("/data/root")
    assert not _is_owned(settings_path(root), root)
    assert not _is_owned(root / ATHLETE_FILE, root)
    assert not _is_owned(root, root)  # the data root itself is not owned wholesale
    assert SETTINGS_FILE not in OWNED_PATHS


def test_tool_state_dir_is_owned_and_is_not_the_source_tree_pointer() -> None:
    """``.fitdocs/`` under the data root is tool-owned state, declared nowhere.

    It is where tool state that is neither a document nor an archive lands (the
    sibling ingestion spec's quarantine record). It is a *different thing* from
    the ``.fitdocs/data-root`` pointer file, which lives in a source tree that is
    walked upward from the working directory -- never under the data root -- and
    stays read-only to fitdocs. Sharing a directory name does not make them the
    same location, and only the data-root one is owned.
    """
    root = Path("/data/root")
    assert TOOL_STATE_DIR == ".fitdocs"
    assert f"{TOOL_STATE_DIR}/" in OWNED_PATHS
    assert _is_owned(root / TOOL_STATE_DIR / "quarantine.toml", root)
    # The pointer file is resolved against a *source* directory, so a pointer in
    # some checkout is not inside this data root's owned tree.
    assert POINTER_RELPATH.split("/")[0] == TOOL_STATE_DIR
    assert not _is_owned(Path("/code/some-repo") / POINTER_RELPATH, root)
    # No declaration is ever placed in the tool-state directory.
    assert f"{TOOL_STATE_DIR}/" not in DECLARED_DIRS


def test_default_inbox_dir_is_the_documented_default() -> None:
    """``inbox/`` is the default location resolved under the data root (Req 1.2)."""
    assert DEFAULT_INBOX_DIR == "inbox"
    # A user-configured location fitdocs may create -- not one of the fixed,
    # always-owned prefixes (Req 8.5).
    assert f"{DEFAULT_INBOX_DIR}/" not in OWNED_PATHS


def test_quarantine_path_resolves_under_the_tool_state_directory() -> None:
    """The quarantine record's path lives under ``.fitdocs/`` (Req 5.1, 8.5).

    ``quarantine_path`` is pure path composition -- it performs no filesystem
    access -- and the resulting path already falls inside the ownership
    contract's tool-owned path set via :data:`TOOL_STATE_DIR`.
    """
    root = Path("/data/root")
    path = quarantine_path(root)
    assert path == root / TOOL_STATE_DIR / "quarantine.toml"
    assert path.parent == root / TOOL_STATE_DIR
    assert _is_owned(path, root)


def test_declared_dirs_are_the_top_level_owned_directories() -> None:
    """Declarations go in the top-level owned directories, and nowhere else.

    ``workouts/`` and ``fit-archive/`` are what a human or an agent browses; the
    assets subdirectory is not top level, and the cache and tool-state
    directories are dot-prefixed machine state that no one reads. Every declared
    directory is drawn from ``OWNED_PATHS`` -- a declaration can never be placed
    somewhere fitdocs does not own.
    """
    assert DECLARED_DIRS == ("workouts/", "fit-archive/")
    assert f"{WORKOUTS_DIR}/" in DECLARED_DIRS
    assert f"{ARCHIVE_DIR}/" in DECLARED_DIRS
    # A declaration is only ever placed where fitdocs owns the directory.
    assert set(DECLARED_DIRS) <= set(OWNED_PATHS)
    assert f"{WORKOUTS_DIR}/{ASSETS_SUBDIR}/" not in DECLARED_DIRS
    assert f"{CACHE_DIR}/" not in DECLARED_DIRS


def test_cache_dir_is_the_root_of_the_tile_cache() -> None:
    """The owned ``.cache/`` prefix is exactly the tile cache's parent.

    One constant defines the cache root and the tile cache is composed from it,
    so the owned prefix and the real cache location cannot diverge.
    """
    assert CACHE_DIR == ".cache"
    assert TILE_CACHE_DIR == ".cache/tiles"
    assert TILE_CACHE_DIR.startswith(f"{CACHE_DIR}/")


def test_layout_module_performs_no_file_io() -> None:
    """The layout stays a pure leaf: constants and path composition only.

    Mutation caught: adding a read, write, or ``mkdir`` here (rather than in the
    engine that owns the write) would move I/O into the module every other module
    imports for policy.
    """
    source = inspect.getsource(layout)
    for banned in (
        "open(",
        "read_text",
        "read_bytes",
        "write_text",
        "write_bytes",
        "mkdir",
        "unlink",
        "os.replace",
        "rglob",
        "exists()",
    ):
        assert banned not in source, f"layout performs I/O: {banned}"
