"""Activity-identity end-to-end suite over temp data roots (engine level).

One headed section per task (tasks.md, Test File Ownership): this file grows a
section each for renames (4.2), planned sync runs (4.3), drain (4.4),
regeneration (4.5) and the measured-shape CLI scenarios (7.2). A task edits
only its own section.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Mapping, Sequence
from dataclasses import replace
from datetime import timedelta, timezone
from pathlib import Path

import pytest
import yaml

import fitdocs.sync as sync_module
from fitdocs import Activity, DerivedMetrics, Modality
from fitdocs import compute_metrics as real_compute_metrics
from fitdocs import parse_fit as real_parse_fit
from fitdocs.contract import format_session_uuid
from fitdocs.declaration import DECLARATION_FILENAME
from fitdocs.identity.kinds import SourceKind
from fitdocs.identity.roles import (
    DEFAULT_PRECEDENCE,
    PageRoles,
    Precedence,
    PrecedenceEntry,
    resolve_precedence,
)
from fitdocs.inbox import DEFAULT_INBOX_SETTINGS
from fitdocs.layout import WORKOUTS_DIR, archive_path, source_ref
from fitdocs.quarantine import QuarantineRecord
from fitdocs.render import TileRef
from fitdocs.sync import SyncReport, drain, regen, sync
from tests.fixtures import identity as fx

# A fixed -06:00 zone so stems never depend on where the suite runs.
_TZ = timezone(timedelta(hours=-6))


class _NoTiles:
    """The fixtures record no position, so no tile is ever requested."""

    attribution = "test"

    def resolve(self, refs: Sequence[TileRef]) -> dict[TileRef, bytes]:
        assert not refs
        return {}


_TILES = _NoTiles()


# --- helpers ----------------------------------------------------------------


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _ref(species: fx.Species) -> str:
    return source_ref(_sha(species.data))


def _uuid_text(species: fx.Species) -> str:
    text = format_session_uuid(tuple(species.session_uuid or ()))
    assert text is not None
    return text


def _sync_one(data_root: Path, work: Path, species: fx.Species) -> None:
    """Sync one file alone (its own source dir) and require a clean write."""
    source = work / f"src-{_sha(species.data)[:8]}"
    source.mkdir(parents=True, exist_ok=True)
    (source / "f.fit").write_bytes(species.data)
    report = sync(source, data_root, athlete=None, tz=_TZ, tiles=_TILES)
    assert report.failures == ()
    assert len(report.written) == 1, report


def _pages(data_root: Path) -> list[Path]:
    return sorted(
        p
        for p in (data_root / WORKOUTS_DIR).glob("*.md")
        if p.name != DECLARATION_FILENAME
    )


def _only_page(data_root: Path) -> Path:
    pages = _pages(data_root)
    assert len(pages) == 1, [p.name for p in pages]
    return pages[0]


def _frontmatter(page: Path) -> dict[str, object]:
    block = page.read_text(encoding="utf-8").split("---\n", 2)[1]
    parsed = yaml.safe_load(block)
    assert isinstance(parsed, dict)
    return parsed


_SOURCES_BLOCK = re.compile(r"^sources:\n(?:- .*\n)+", re.MULTILINE)


def _set_sources(page: Path, refs: Sequence[str]) -> None:
    """Hand-edit a page's ``sources`` list (the staged 2026-09-12 shape)."""
    text = page.read_text(encoding="utf-8")
    block = "sources:\n" + "".join(f"- {ref}\n" for ref in refs)
    edited, count = _SOURCES_BLOCK.subn(block, text)
    assert count == 1
    page.write_text(edited, encoding="utf-8")


def _archive(data_root: Path, species: fx.Species) -> None:
    """Place a file in the archive without any page listing it."""
    path = archive_path(data_root, _sha(species.data))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(species.data)


def _regen(data_root: Path, precedence: Precedence = DEFAULT_PRECEDENCE) -> SyncReport:
    return regen(data_root, athlete=None, tz=_TZ, tiles=_TILES, precedence=precedence)


def _stage_adopted(
    tmp_path: Path, listed: str
) -> tuple[Path, Path, fx.Species, fx.Species]:
    """A data root shaped like the 2026-09-12 hand adoption.

    The page was rendered from the HealthFit copy; the Garmin original was then
    archived and listed by hand. ``listed`` is ``"copy-first"`` (the adoption's
    own order) or ``"original-first"`` (the reverse, which the engine must fix).
    """
    data_root = tmp_path / "data"
    data_root.mkdir()
    copy, original = fx.healthfit_copy(), fx.garmin_original()
    _sync_one(data_root, tmp_path, copy)
    _archive(data_root, original)
    page = _only_page(data_root)
    assert _frontmatter(page)["source_elapsed_s"] == copy.elapsed_s  # precondition
    order = (
        [_ref(copy), _ref(original)]
        if listed == "copy-first"
        else [_ref(original), _ref(copy)]
    )
    _set_sources(page, order)
    return data_root, page, copy, original


# --- roles (4.1) ---


def test_reexport_pair_in_either_order_renders_byte_identical_pages(
    tmp_path: Path,
) -> None:
    """Req 5.1, 5.2, 5.7: the base and the order of ``sources`` depend on the
    files, not on which arrived first.

    Fixture: the two exports differ in start (one hour), so a page rendered from
    the wrong export differs in its text. Mutations: render from the last
    listed file (reds the b-then-a run, whose last listed file is the older
    export); order ``sources`` by arrival (reds the b-then-a run's ``sources``).
    """
    older, newer = fx.healthfit_reexport_pair()
    assert older.start != newer.start  # the property the fixture must violate
    texts: dict[str, str] = {}
    for label, arrivals in (("ab", (older, newer)), ("ba", (newer, older))):
        data_root = tmp_path / label / "data"
        data_root.mkdir(parents=True)
        for species in arrivals:
            _sync_one(data_root, tmp_path / label, species)
        page = _only_page(data_root)
        assert _frontmatter(page)["sources"] == [_ref(older), _ref(newer)]
        texts[label] = page.read_text(encoding="utf-8")
    assert texts["ab"] == texts["ba"]
    # ...and it is the newer export's page (the base): it matches what the
    # newer export alone renders, apart from the ``sources`` list.
    alone_root = tmp_path / "alone" / "data"
    alone_root.mkdir(parents=True)
    _sync_one(alone_root, tmp_path / "alone", newer)
    alone = _only_page(alone_root).read_text(encoding="utf-8")
    assert _SOURCES_BLOCK.sub("", texts["ab"]) == _SOURCES_BLOCK.sub("", alone)


def test_file_below_the_base_leaves_base_and_filename_unchanged(
    tmp_path: Path,
) -> None:
    """Req 5.3, 5.7: a file that ranks below the base changes neither the base
    nor the page's filename, only the ``sources`` list.

    Mutation: render from the last listed file (the older export, which arrives
    last, would become the rendered activity and move ``start_time``).
    """
    older, newer = fx.healthfit_reexport_pair()
    data_root = tmp_path / "data"
    data_root.mkdir()
    _sync_one(data_root, tmp_path, newer)
    page = _only_page(data_root)
    before = page.read_text(encoding="utf-8")
    name = page.name
    _sync_one(data_root, tmp_path, older)
    assert _only_page(data_root).name == name
    after = page.read_text(encoding="utf-8")
    assert _frontmatter(page)["sources"] == [_ref(older), _ref(newer)]
    normalized = _SOURCES_BLOCK.sub("", after)
    assert normalized == _SOURCES_BLOCK.sub("", before)


def test_hand_adopted_page_regenerates_from_the_original_and_keeps_the_uuid(
    tmp_path: Path,
) -> None:
    """Req 5.1, 5.5, 7.2: a page whose ``sources`` lists the phone copy then the
    device original renders the original's values and keeps the copy's UUID.

    The two files differ in every rendered identity value (elapsed, distance,
    device, kind, moving time), so rendering from the copy reds. Mutation: drop
    UUID retention (the original records none, so ``uuid`` vanishes).
    """
    data_root, page, copy, original = _stage_adopted(tmp_path, "copy-first")
    report = _regen(data_root)
    assert report.failures == ()
    assert report.written == (f"{WORKOUTS_DIR}/{page.name}",)
    front = _frontmatter(page)
    assert front["uuid"] == _uuid_text(copy)
    assert front["source_kind"] == "original"
    assert front["source_elapsed_s"] == original.elapsed_s != copy.elapsed_s
    assert front["source_distance_m"] == original.distance_m != copy.distance_m
    assert front["moving_time"] == "48:00"  # the original's timer, not the copy's
    assert front["sources"] == [_ref(copy), _ref(original)]


def test_regen_restores_canonical_order_from_a_reversed_listing(
    tmp_path: Path,
) -> None:
    """Req 5.2, 7.2: the listed order is not trusted; the ranking decides.

    Listed original-first, the last listed file is the copy. Rendering from the
    last listed file shows the copy's ``source_elapsed_s``; computing metrics
    from the incoming file (the copy) shows the copy's ``moving_time`` "50:00"
    where the original's is "48:00"; keeping the listed order leaves
    ``sources`` reversed. Each of the three reds an assertion below.
    """
    data_root, page, copy, original = _stage_adopted(tmp_path, "original-first")
    assert _regen(data_root).failures == ()
    front = _frontmatter(page)
    assert front["sources"] == [_ref(copy), _ref(original)]
    assert front["source_elapsed_s"] == original.elapsed_s
    assert front["moving_time"] == "48:00"
    assert front["uuid"] == _uuid_text(copy)


def test_unresolvable_listed_ref_stays_first_and_the_recorded_uuid_survives(
    tmp_path: Path,
) -> None:
    """Req 5.2, 5.5, 7.7: a listed file no longer in the archive keeps the front
    of ``sources``, and the page's recorded UUID survives although no resolved
    file carries one.

    Mutation: pass no recorded UUID to the retention rule (``uuid`` vanishes);
    order ``sources`` by arrival (the ghost is listed between the two files).
    """
    data_root, page, copy, original = _stage_adopted(tmp_path, "copy-first")
    ghost = "fit-archive/" + "f" * 64 + ".fit"
    archive_path(data_root, _sha(copy.data)).unlink()  # the copy is now unresolved
    _set_sources(page, [_ref(original), ghost, _ref(copy)])
    assert _regen(data_root).failures == ()
    front = _frontmatter(page)
    assert front["sources"] == [ghost, _ref(copy), _ref(original)]
    assert front["uuid"] == _uuid_text(copy)
    assert front["source_elapsed_s"] == original.elapsed_s


def test_page_whose_listed_files_are_all_missing_fails_with_todays_reason(
    tmp_path: Path,
) -> None:
    """Req 7.6: nothing to render from is a failure, and the page is untouched."""
    data_root, page, copy, original = _stage_adopted(tmp_path, "copy-first")
    archive_path(data_root, _sha(copy.data)).unlink()
    archive_path(data_root, _sha(original.data)).unlink()
    before = page.read_bytes()
    report = _regen(data_root)
    assert report.written == ()
    assert len(report.failures) == 1
    failure = report.failures[0]
    assert failure.source == f"{WORKOUTS_DIR}/{page.name}"
    assert failure.reason.startswith("no archived source to regenerate from")
    assert page.read_bytes() == before


def test_regen_uses_the_given_precedence(tmp_path: Path) -> None:
    """Req 7.2: regeneration rebuilds roles with the precedence it is given.

    Phone copies first makes the copy the base, so the page shows the copy's
    values and lists the original first. Mutation: ignore the keyword.
    """
    data_root, page, copy, original = _stage_adopted(tmp_path, "copy-first")
    precedence = resolve_precedence([PrecedenceEntry(SourceKind.PHONE_COPY)])
    assert _regen(data_root, precedence).failures == ()
    front = _frontmatter(page)
    assert front["source_kind"] == "phone_copy"
    assert front["source_elapsed_s"] == copy.elapsed_s
    assert front["sources"] == [_ref(original), _ref(copy)]


def _stage_with_a_reexport_of_the_copy(tmp_path: Path) -> tuple[Path, Path]:
    """The adopted page, plus the copy's re-export waiting in a source dir."""
    data_root, page, _copy, _original = _stage_adopted(tmp_path, "copy-first")
    source = tmp_path / "incoming"
    source.mkdir()
    (source / "again.fit").write_bytes(fx.healthfit_shifted().data)
    return data_root, source


def test_sync_ranks_a_matched_page_with_the_given_precedence(tmp_path: Path) -> None:
    """Req 5.1, 5.7: ``sync`` matches the re-export by session UUID, ranks it
    with the page's files, and renders the base the precedence chooses.

    Default: the Garmin original stays the base. Phone copies first: the new
    export (or its fellow copy) is. Mutation: drop the keyword.
    """
    data_root, source = _stage_with_a_reexport_of_the_copy(tmp_path)
    page = _only_page(data_root)
    default = sync(source, data_root, athlete=None, tz=_TZ, tiles=_TILES)
    assert default.failures == ()
    assert _only_page(data_root) == page
    assert _frontmatter(page)["source_kind"] == "original"
    assert len(_frontmatter(page)["sources"]) == 3  # type: ignore[arg-type]

    precedence = resolve_precedence([PrecedenceEntry(SourceKind.PHONE_COPY)])
    again = sync(
        source,
        data_root,
        athlete=None,
        tz=_TZ,
        tiles=_TILES,
        force=True,
        precedence=precedence,
    )
    assert again.failures == ()
    assert _frontmatter(page)["source_kind"] == "phone_copy"


def test_drain_ranks_a_matched_page_with_the_given_precedence(tmp_path: Path) -> None:
    """Req 5.1, 5.7: ``drain`` takes the same keyword and applies it."""
    data_root, source = _stage_with_a_reexport_of_the_copy(tmp_path)
    page = _only_page(data_root)
    precedence = resolve_precedence([PrecedenceEntry(SourceKind.PHONE_COPY)])
    report = drain(
        source,
        data_root,
        settings=DEFAULT_INBOX_SETTINGS,
        processed_dir=None,
        quarantine=QuarantineRecord(entries=()),
        athlete=None,
        tz=_TZ,
        tiles=_TILES,
        sleep=lambda _seconds: None,
        precedence=precedence,
    )
    assert report.sync.failures == ()
    assert _only_page(data_root) == page
    assert _frontmatter(page)["source_kind"] == "phone_copy"
    assert len(_frontmatter(page)["sources"]) == 3  # type: ignore[arg-type]


def _set_uuid(page: Path, value: str) -> None:
    text = page.read_text(encoding="utf-8")
    edited, count = re.subn(r"^uuid: .*$", f"uuid: {value}", text, flags=re.MULTILINE)
    assert count == 1
    page.write_text(edited, encoding="utf-8")


def test_extra_session_uuid_outranks_the_recorded_value(tmp_path: Path) -> None:
    """Req 5.5: the UUID comes from the base, then the extras, and only then from
    the page's recorded value.

    The adopted page carries a hand-set, different, well-formed ``uuid``; the
    copy (an extra) records its own, which wins. Mutation: consult the recorded
    value before the extras.
    """
    data_root, page, copy, _original = _stage_adopted(tmp_path, "copy-first")
    other = "11111111-2222-3333-4444-555555555555"
    assert other != _uuid_text(copy)
    _set_uuid(page, other)
    assert _regen(data_root).failures == ()
    assert _frontmatter(page)["uuid"] == _uuid_text(copy)


class _CountingParse:
    """Wraps ``parse_fit`` and counts the calls the engine makes."""

    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, data: bytes) -> Activity:
        self.calls += 1
        return real_parse_fit(data)


def test_each_file_is_parsed_once_per_page_task(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Req 5.1: the incoming file and every resolved listed file are parsed once.

    Regenerating the two-file adopted page parses twice; syncing a third file
    onto it parses three times. Mutation: a second ``parse_fit`` per member.
    """
    data_root, _page, _copy, _original = _stage_adopted(tmp_path, "copy-first")
    counter = _CountingParse()
    monkeypatch.setattr(sync_module, "parse_fit", counter)
    assert _regen(data_root).failures == ()
    assert counter.calls == 2
    counter.calls = 0
    source = tmp_path / "third"
    source.mkdir()
    (source / "t.fit").write_bytes(fx.healthfit_shifted().data)
    report = sync(source, data_root, athlete=None, tz=_TZ, tiles=_TILES)
    assert report.failures == ()
    assert len(report.written) == 1
    assert counter.calls == 3


def _force_collision(data_root: Path, page: Path) -> tuple[Path, str]:
    """Move the page to a user-chosen name and occupy its computed stem.

    A matched page whose computed stem is taken by another file gets the
    ``-<uid[:8]>`` suffix, which makes the page's uid visible in its chart links.
    Returns the moved page and the unsuffixed stem.
    """
    stem = page.stem
    moved = page.with_name("moved-by-user.md")
    page.rename(moved)
    page.write_text("not a workout document\n", encoding="utf-8")
    return moved, stem


def test_page_uid_is_the_retained_uuid_else_the_base_hash(tmp_path: Path) -> None:
    """Req 5.5, 5.6: the page's uid seeds its collision suffix, and it is the
    retained session UUID, or else the base's own hash.

    Case 1, the adopted page: the incoming file is the original, the retained
    UUID is the copy's. Mutations: the incoming file's identity as the uid
    (``activity_uid``-style, the original's hash here).
    Case 2, no UUID anywhere: listed original then its lower-ranked partner
    copy, so the incoming file (the last listed) is not the base. Mutation:
    the incoming file's hash as the fallback.
    """
    data_root, page, copy, _original = _stage_adopted(tmp_path, "copy-first")
    moved, stem = _force_collision(data_root, page)
    assert _regen(data_root).failures == ()
    uid8 = _uuid_text(copy)[:8]
    assert f"assets/{stem}-{uid8}-hero.svg" in moved.read_text(encoding="utf-8")

    root2 = tmp_path / "second" / "data"
    root2.mkdir(parents=True)
    original, partner = fx.garmin_original(), fx.partner_copy()
    assert _sha(original.data) != _sha(partner.data)
    _sync_one(root2, tmp_path / "second", partner)
    _archive(root2, original)
    page2 = _only_page(root2)
    _set_sources(page2, [_ref(original), _ref(partner)])
    moved2, stem2 = _force_collision(root2, page2)
    assert _regen(root2).failures == ()
    text2 = moved2.read_text(encoding="utf-8")
    assert f"assets/{stem2}-{_sha(original.data)[:8]}-hero.svg" in text2
    assert _frontmatter(moved2)["sources"] == [_ref(partner), _ref(original)]


def _stage_below_base_arrival(tmp_path: Path) -> tuple[Path, Path]:
    """The adopted page and a source dir holding a lower-ranked new file."""
    return _stage_with_a_reexport_of_the_copy(tmp_path)


def test_metrics_and_map_come_from_the_render_activity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Req 5.8: metrics and the map plan are computed from what
    ``_render_activity`` returns, not from the incoming file.

    The incoming file ranks below the base. The seam is wrapped to return a
    distinct activity with distinct position channels; ``compute_metrics`` must
    receive that exact object and ``plan_map`` its channels. Mutations:
    ``compute_metrics(activity, ...)``; ``plan_map(activity.samples...)``.
    """
    data_root, source = _stage_below_base_arrival(tmp_path)
    real = sync_module._render_activity
    returned: list[Activity] = []
    lat = (1.0, 2.0)
    lon = (3.0, 4.0)

    def seam(roles: PageRoles, parsed: Mapping[str, Activity]) -> Activity:
        base = real(roles, parsed)
        assert roles.base.kind is SourceKind.ORIGINAL  # incoming ranks below
        out = replace(
            base, samples=replace(base.samples, latitude_deg=lat, longitude_deg=lon)
        )
        returned.append(out)
        return out

    metric_args: list[Activity] = []
    plan_args: list[tuple[object, object]] = []

    def spy_metrics(activity: Activity, athlete: object) -> DerivedMetrics:
        metric_args.append(activity)
        return real_compute_metrics(activity, athlete)  # type: ignore[arg-type]

    def spy_plan(latitudes: object, longitudes: object) -> None:
        plan_args.append((latitudes, longitudes))

    monkeypatch.setattr(sync_module, "_render_activity", seam)
    monkeypatch.setattr(sync_module, "compute_metrics", spy_metrics)
    monkeypatch.setattr(sync_module, "plan_map", spy_plan)
    report = sync(source, data_root, athlete=None, tz=_TZ, tiles=_TILES)
    assert report.failures == ()
    assert len(returned) == 1
    assert len(metric_args) == 1 and metric_args[0] is returned[0]
    assert len(plan_args) == 1
    assert plan_args[0][0] is lat and plan_args[0][1] is lon


def test_the_map_decision_follows_the_render_activitys_modality(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Req 5.8: whether a map is planned follows the rendered activity's
    modality. The seam returns a strength-modality activity while the incoming
    file is a run, so no map is planned. Mutation: read the incoming file's
    modality."""
    data_root, source = _stage_below_base_arrival(tmp_path)
    real = sync_module._render_activity

    def seam(roles: PageRoles, parsed: Mapping[str, Activity]) -> Activity:
        return replace(real(roles, parsed), modality=Modality.STRENGTH)

    plans: list[object] = []

    def spy_plan(latitudes: object, longitudes: object) -> None:
        plans.append(latitudes)

    monkeypatch.setattr(sync_module, "_render_activity", seam)
    monkeypatch.setattr(sync_module, "plan_map", spy_plan)
    report = sync(source, data_root, athlete=None, tz=_TZ, tiles=_TILES)
    assert report.failures == ()
    assert plans == []
