"""Activity-identity end-to-end suite over temp data roots (engine level).

One headed section per task (tasks.md, Test File Ownership): this file grows a
section each for renames (4.2), planned sync runs (4.3), drain (4.4),
regeneration (4.5) and the measured-shape CLI scenarios (7.2). A task edits
only its own section.
"""

from __future__ import annotations

import hashlib
import itertools
import re
from collections.abc import Mapping, Sequence
from dataclasses import replace
from datetime import timedelta, timezone
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

import fitdocs.sync as sync_module
from fitdocs import Activity, DerivedMetrics, Modality
from fitdocs import cli as cli_module
from fitdocs import compute_metrics as real_compute_metrics
from fitdocs import parse_fit as real_parse_fit
from fitdocs.cli import app
from fitdocs.compose.types import Composition
from fitdocs.contract import DOC_VERSION, format_session_uuid
from fitdocs.declaration import DECLARATION_FILENAME
from fitdocs.docmerge import begin_marker, end_marker
from fitdocs.identity import planning
from fitdocs.identity.holds import (
    HeldSource,
    HoldRecord,
    HoldRecordError,
    load_holds,
)
from fitdocs.identity.kinds import SourceKind
from fitdocs.identity.roles import (
    DEFAULT_PRECEDENCE,
    PageRoles,
    Precedence,
    PrecedenceEntry,
    resolve_precedence,
)
from fitdocs.inbox import DEFAULT_INBOX_SETTINGS, Disposition
from fitdocs.layout import (
    WORKOUTS_DIR,
    archive_path,
    doc_stem,
    held_path,
    quarantine_path,
    source_ref,
)
from fitdocs.quarantine import QuarantineRecord, load_quarantine
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
_CHANNEL_SOURCES = re.compile(r"\n## Channel Sources\n.*?(?=\n## |\Z)", re.DOTALL)
_TABLE_REF = re.compile(r"^\| `(fit-archive/[0-9a-f]{64}\.fit)` \|", re.MULTILINE)


def _without_channel_sources(text: str) -> str:
    """The page text minus its channel-merge ``## Channel Sources`` section."""
    return _CHANNEL_SOURCES.sub("", text)


def _channel_sources_lines(text: str) -> list[str]:
    """The lines of the page's Channel Sources section (empty without one)."""
    section = _CHANNEL_SOURCES.search(text)
    return section.group(0).strip("\n").splitlines() if section else []


def _extra_channels_cells(text: str) -> list[str]:
    """The Channels cell of every ``extra`` row of the Channel Sources table."""
    cells = [
        [c.strip() for c in line.strip("|").split("|")]
        for line in _channel_sources_lines(text)
        if line.startswith("| `fit-archive")
    ]
    return [row[3] for row in cells if row[1] == "extra"]


def _channel_source_refs(text: str) -> list[str]:
    """The files the page's Channel Sources table names, base first."""
    section = _CHANNEL_SOURCES.search(text)
    return _TABLE_REF.findall(section.group(0)) if section else []


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
        # Channel composition: the page now names both files, base first.
        assert _channel_source_refs(texts[label]) == [_ref(newer), _ref(older)]
    assert texts["ab"] == texts["ba"]
    # ...and it is the newer export's page (the base): it matches what the
    # newer export alone renders, apart from the ``sources`` list and the
    # Channel Sources section (whose one extra row, the older export, donates
    # nothing).
    alone_root = tmp_path / "alone" / "data"
    alone_root.mkdir(parents=True)
    _sync_one(alone_root, tmp_path / "alone", newer)
    alone = _only_page(alone_root).read_text(encoding="utf-8")
    assert _channel_source_refs(alone) == []
    assert _extra_channels_cells(texts["ab"]) == ["–"]
    assert _SOURCES_BLOCK.sub("", _without_channel_sources(texts["ab"])) == (
        _SOURCES_BLOCK.sub("", alone)
    )


def test_file_below_the_base_leaves_base_and_filename_unchanged(
    tmp_path: Path,
) -> None:
    """Req 5.3, 5.7: a file that ranks below the base changes neither the base
    nor the page's filename, only the ``sources`` list and the page's Channel
    Sources section, whose one extra row (the older export) donates nothing.

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
    assert _channel_source_refs(before) == []
    assert _extra_channels_cells(after) == ["–"]
    assert _channel_source_refs(after) == [_ref(newer), _ref(older)]
    normalized = _SOURCES_BLOCK.sub("", _without_channel_sources(after))
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
    # The phone copy that becomes the base starts two hours later than the
    # original did, so the page follows it to its new name (Req 6.2).
    renamed = _only_page(data_root)
    assert renamed != page
    assert _frontmatter(renamed)["source_kind"] == "phone_copy"


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
    # The base becomes the later-starting phone copy, so the page is renamed
    # (Req 6.2): it is the only page, at a new name.
    renamed = _only_page(data_root)
    assert renamed != page
    assert _frontmatter(renamed)["source_kind"] == "phone_copy"
    assert len(_frontmatter(renamed)["sources"]) == 3  # type: ignore[arg-type]


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
    """Req 5.1: the incoming file and every resolved listed file are parsed once
    per page task.

    Regenerating the two-file adopted page parses twice. Syncing a third file
    onto it parses that file once in run preparation (the planner needs its
    key) and the page task then parses it and the two listed files once each:
    four in all (4.3 moved the count from three; the task re-reads its member
    and does not retain the preparation's parse). Mutation: a second
    ``parse_fit`` per member inside the task.
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
    assert counter.calls == 4


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
    # The base changed (partner -> original), so the page left its user-chosen
    # name for the computed one, whose suffix is the uid: the base's own hash
    # (Req 6.2). The unsuffixed name is held by the other file.
    assert not moved2.exists()
    renamed2 = moved2.with_name(f"{stem2}-{_sha(original.data)[:8]}.md")
    text2 = renamed2.read_text(encoding="utf-8")
    assert f"assets/{stem2}-{_sha(original.data)[:8]}-hero.svg" in text2
    assert _frontmatter(renamed2)["sources"] == [_ref(partner), _ref(original)]


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

    def seam(roles: PageRoles, parsed: Mapping[str, Activity]) -> Composition:
        composed = real(roles, parsed)
        base = composed.activity
        assert roles.base.kind is SourceKind.ORIGINAL  # incoming ranks below
        out = replace(
            base, samples=replace(base.samples, latitude_deg=lat, longitude_deg=lon)
        )
        returned.append(out)
        return replace(composed, activity=out)

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

    def seam(roles: PageRoles, parsed: Mapping[str, Activity]) -> Composition:
        composed = real(roles, parsed)
        return replace(
            composed, activity=replace(composed.activity, modality=Modality.STRENGTH)
        )

    plans: list[object] = []

    def spy_plan(latitudes: object, longitudes: object) -> None:
        plans.append(latitudes)

    monkeypatch.setattr(sync_module, "_render_activity", seam)
    monkeypatch.setattr(sync_module, "plan_map", spy_plan)
    report = sync(source, data_root, athlete=None, tz=_TZ, tiles=_TILES)
    assert report.failures == ()
    assert plans == []


# --- renames (4.2) ---

_NOTE = "walked the dog before this run; keep me"


def _write_note(page: Path, note: str) -> None:
    """Replace the page's ``notes`` region content (a user edit)."""
    text = page.read_text(encoding="utf-8")
    pattern = re.compile(
        re.escape(begin_marker("notes")) + r"\n.*?\n" + re.escape(end_marker("notes")),
        re.DOTALL,
    )
    edited, count = pattern.subn(
        lambda _m: f"{begin_marker('notes')}\n{note}\n{end_marker('notes')}", text
    )
    assert count == 1
    page.write_text(edited, encoding="utf-8")


def _assets(data_root: Path) -> set[str]:
    """Every file under ``workouts/assets/``, relative to it."""
    root = data_root / WORKOUTS_DIR / "assets"
    return {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file()}


def _linked_assets(page: Path) -> set[str]:
    return set(
        re.findall(r"!\[[^\]]*\]\(assets/([^)]+)\)", page.read_text(encoding="utf-8"))
    )


def _stage_reexport(tmp_path: Path) -> tuple[Path, Path, fx.Species, fx.Species]:
    """The older export synced, a note written, the newer export in a source dir.

    The newer export corrects the start (one hour earlier), so its page name
    differs from the older export's.
    """
    older, newer = fx.healthfit_reexport_pair()
    data_root = tmp_path / "data"
    data_root.mkdir()
    _sync_one(data_root, tmp_path, older)
    _write_note(_only_page(data_root), _NOTE)
    source = tmp_path / "newer"
    source.mkdir()
    (source / "newer.fit").write_bytes(newer.data)
    return data_root, source, older, newer


def _sync_dir(data_root: Path, source: Path) -> SyncReport:
    return sync(source, data_root, athlete=None, tz=_TZ, tiles=_TILES)


def _rename_warnings(report: SyncReport) -> list[sync_module.DocWarning]:
    return [w for w in report.warnings if "renamed" in w.detail]


def test_reexport_that_corrects_the_start_renames_the_page(tmp_path: Path) -> None:
    """Req 6.2, 6.4, 6.5: the newer export moves the page to the name its
    start computes, its old chart is removed with nothing else, a note written
    before survives, and the run warns once, naming both paths.

    Fixture: the pair's starts differ by an hour (different stems), the assets
    directory also holds a file the page never linked and a file the page
    links through a two-component path, neither of which may go. Mutations:
    skip the stale-asset removal (the old hero stays); drop the
    single-component rule (``sub/deep.svg`` goes); rename on no base change
    (the page keeps its old name).
    """
    data_root, source, older, newer = _stage_reexport(tmp_path)
    old_page = _only_page(data_root)
    old_hero = f"{old_page.stem}-hero.svg"
    assert _assets(data_root) == {old_hero}  # precondition: one chart, the old one
    (data_root / WORKOUTS_DIR / "assets" / "sub").mkdir()
    (data_root / WORKOUTS_DIR / "assets" / "sub" / "deep.svg").write_text("<svg/>")
    (data_root / WORKOUTS_DIR / "assets" / "keep-me.svg").write_text("<svg/>")
    text = old_page.read_text(encoding="utf-8")
    old_page.write_text(
        text + "\n![deep](assets/sub/deep.svg)\n", encoding="utf-8"
    )  # a generated-content link with two components

    report = _sync_dir(data_root, source)

    assert report.failures == ()
    new_page = _only_page(data_root)
    assert new_page.name != old_page.name
    assert not old_page.exists()
    assert report.written == (f"{WORKOUTS_DIR}/{new_page.name}",)
    new_hero = f"{new_page.stem}-hero.svg"
    assert _assets(data_root) == {new_hero, "sub/deep.svg", "keep-me.svg"}
    assert _NOTE in new_page.read_text(encoding="utf-8")
    assert _frontmatter(new_page)["sources"] == [_ref(older), _ref(newer)]
    warnings = _rename_warnings(report)
    assert report.warnings == tuple(warnings)  # exactly one warning, the rename
    assert len(warnings) == 1
    assert warnings[0].doc == f"{WORKOUTS_DIR}/{new_page.name}"
    detail = warnings[0].detail
    assert f"{WORKOUTS_DIR}/{old_page.name}" in detail
    assert f"{WORKOUTS_DIR}/{new_page.name}" in detail
    assert "wiki links" in detail and "plan overrides" in detail


def test_user_renamed_page_keeps_its_name_when_the_base_does_not_change(
    tmp_path: Path,
) -> None:
    """Req 6.3: a page the user renamed, rewritten by a file ranking below its
    base, keeps that name and is not warned about.

    The rewrite really happens (the older export is now listed). Mutation:
    rename on every rewrite rather than on a base change (the page moves to
    its computed name).
    """
    older, newer = fx.healthfit_reexport_pair()
    data_root = tmp_path / "data"
    data_root.mkdir()
    _sync_one(data_root, tmp_path, newer)
    computed = _only_page(data_root)
    mine = computed.with_name("my-favourite-run.md")
    computed.rename(mine)
    source = tmp_path / "older"
    source.mkdir()
    (source / "older.fit").write_bytes(older.data)

    report = _sync_dir(data_root, source)

    assert report.failures == ()
    assert _only_page(data_root) == mine
    assert _frontmatter(mine)["sources"] == [_ref(older), _ref(newer)]  # rewritten
    assert _rename_warnings(report) == []


def test_chart_linked_from_a_note_survives_the_rename(tmp_path: Path) -> None:
    """Req 6.4: a chart a user-owned region links is kept, whatever its name.

    The note links the old hero. Mutation: remove assets linked from a
    preserved region (the old hero goes and the note's image breaks).
    """
    data_root, source, _older, _newer = _stage_reexport(tmp_path)
    old_page = _only_page(data_root)
    old_hero = f"{old_page.stem}-hero.svg"
    _write_note(old_page, f"{_NOTE}\n![mine](assets/{old_hero})")

    report = _sync_dir(data_root, source)

    assert report.failures == ()
    new_page = _only_page(data_root)
    assert new_page.stem != old_page.stem
    assert _assets(data_root) == {old_hero, f"{new_page.stem}-hero.svg"}
    assert f"![mine](assets/{old_hero})" in new_page.read_text(encoding="utf-8")


def _trade_export(
    *,
    start_hours: int,
    created_hours: int,
    session: int,
    elapsed_s: float,
    distance_m: float,
) -> bytes:
    """One HealthFit-style export of a session that starts ``start_hours``
    after the fixtures' common start and was created ``created_hours`` after
    the copy's creation (a later export outranks an earlier one); sessions
    differ in every value."""
    base = fx.healthfit_copy()
    return fx.session_fit_bytes(
        sport="running",
        start=base.start + start_hours * 3600,
        elapsed_s=elapsed_s,
        timer_s=elapsed_s,
        distance_m=distance_m,
        manufacturer="development",
        product=0,
        serial=base.serial + session,
        time_created=base.time_created + created_hours * 3600,
        session_uuid=tuple(range(session * 16, session * 16 + 16)),
        device_manufacturer="garmin",
    )


def _run_trade(
    mode: str, tmp_path: Path, data_root: Path, a_new: bytes, b_new: bytes
) -> SyncReport:
    """Deliver both corrections to pages A (session 1) and B (session 2) in one
    ``sync``, one ``drain``, or one ``regen`` (A's is discovered first except
    under ``regen``, which walks the pages by name)."""
    both = tmp_path / "both"
    both.mkdir()
    if mode == "regen":
        for data in (a_new, b_new):
            path = archive_path(data_root, _sha(data))
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        for page in _pages(data_root):
            sources = _frontmatter(page)["sources"]
            assert isinstance(sources, list)
            newer = a_new if _frontmatter(page)["uuid"] == _uuid_of(1) else b_new
            # Listed newer-first (the un-ranked shape): the last listed file,
            # the page's recorded base, is the older export.
            _set_sources(page, [source_ref(_sha(newer)), *sources])
        return _regen(data_root)
    (both / "1-a.fit").write_bytes(a_new)
    (both / "2-b.fit").write_bytes(b_new)
    if mode == "sync":
        return _sync_dir(data_root, both)
    return drain(
        both,
        data_root,
        settings=DEFAULT_INBOX_SETTINGS,
        processed_dir=None,
        quarantine=QuarantineRecord(entries=()),
        athlete=None,
        tz=_TZ,
        tiles=_TILES,
        sleep=lambda _seconds: None,
    ).sync


def _uuid_of(session: int) -> str:
    text = format_session_uuid(tuple(range(session * 16, session * 16 + 16)))
    assert text is not None
    return text


@pytest.mark.parametrize("mode", ["sync", "drain", "regen"])
def test_two_pages_trading_names_in_one_run_end_unsuffixed(
    tmp_path: Path, mode: str
) -> None:
    """Req 6.6: one page's correction takes the name the other still holds (so
    it is written under a collision suffix), the other's correction takes the
    first's old name, and the settle pass moves the suffixed page to the name
    that was freed -- after ``sync``, ``drain`` and ``regen`` alike.

    Mutation: drop the settle pass from that entry point (the suffixed name
    stays). The report's ``written`` names each page where it ended.
    """
    a_old = _trade_export(
        start_hours=1, created_hours=0, session=1, elapsed_s=3000.0, distance_m=9000.0
    )
    a_new = _trade_export(
        start_hours=0, created_hours=1, session=1, elapsed_s=3000.0, distance_m=9000.0
    )
    b_old = _trade_export(
        start_hours=0, created_hours=0, session=2, elapsed_s=2000.0, distance_m=6000.0
    )
    b_new = _trade_export(
        start_hours=1, created_hours=1, session=2, elapsed_s=2000.0, distance_m=6000.0
    )
    data_root = tmp_path / "data"
    data_root.mkdir()
    for index, data in enumerate((a_old, b_old)):
        source = tmp_path / f"first-{index}"
        source.mkdir()
        (source / "f.fit").write_bytes(data)
        assert _sync_dir(data_root, source).failures == ()
    by_uuid_before = {_frontmatter(p)["uuid"]: p.name for p in _pages(data_root)}
    name_a, name_b = by_uuid_before[_uuid_of(1)], by_uuid_before[_uuid_of(2)]
    assert name_a > name_b  # A starts later: its correction takes B's name

    report = _run_trade(mode, tmp_path, data_root, a_new, b_new)

    assert report.failures == ()
    names = sorted(p.name for p in _pages(data_root))
    assert names == sorted([name_a, name_b])  # each name once, no suffix
    by_uuid = {_frontmatter(p)["uuid"]: p.name for p in _pages(data_root)}
    assert by_uuid == {_uuid_of(1): name_b, _uuid_of(2): name_a}  # traded
    for ref in report.written:
        assert (data_root / ref).is_file()
    assert sorted(report.written) == sorted(f"{WORKOUTS_DIR}/{n}" for n in names)
    assert _assets(data_root) == {f"{p.stem}-hero.svg" for p in _pages(data_root)}


_STEPS = (
    "_write_assets",
    "_remove_stale_assets",
    "_move_document",
    "_write_document",
    "_write_archive",
)


@pytest.mark.parametrize("step", _STEPS)
def test_a_fault_after_each_write_step_leaves_one_page_and_the_next_run_heals(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, step: str
) -> None:
    """Req 6.7: whichever write step a run dies after, the page is at exactly
    one path, and the next run over the same inputs completes the rename with
    no chart left behind.

    The state at the fault pins the order: through the stale-asset removal the
    page is still at its old path (and old content); after the move it is at
    the new path with its old content; after the document write its content is
    new; only after the archive step is the file archived. Mutation: write the
    document before the move (the page holds new content at its old path when
    the move step ends, and at its new path only after).
    """
    data_root, source, older, newer = _stage_reexport(tmp_path)
    old_page = _only_page(data_root)
    real = getattr(sync_module, step)

    def dying(*args: object, **kwargs: object) -> None:
        real(*args, **kwargs)
        raise RuntimeError(f"fault after {step}")

    with monkeypatch.context() as patch:
        patch.setattr(sync_module, step, dying)
        report = _sync_dir(data_root, source)
    assert len(report.failures) == 1
    assert f"fault after {step}" in report.failures[0].reason

    pages = _pages(data_root)
    assert len(pages) == 1  # never at two paths
    page = pages[0]
    front = _frontmatter(page)
    at_old_path = page == old_page
    assert at_old_path == (step in ("_write_assets", "_remove_stale_assets"))
    new_content = front["sources"] == [_ref(older), _ref(newer)]
    assert new_content == (step in ("_write_document", "_write_archive"))
    assert archive_path(data_root, _sha(newer.data)).exists() == (
        step == "_write_archive"
    )
    assert _NOTE in page.read_text(encoding="utf-8")

    healed = _sync_dir(data_root, source)
    assert healed.failures == ()
    final = _only_page(data_root)
    assert final.name != old_page.name
    assert _frontmatter(final)["sources"] == [_ref(older), _ref(newer)]
    assert _assets(data_root) == {f"{final.stem}-hero.svg"}
    assert _NOTE in final.read_text(encoding="utf-8")
    assert archive_path(data_root, _sha(newer.data)).is_file()


def _put_files(root: Path, name: str, files: dict[str, bytes]) -> Path:
    directory = root / name
    directory.mkdir()
    for file_name, data in files.items():
        (directory / file_name).write_bytes(data)
    return directory


def test_rename_back_to_the_same_stem_keeps_the_chart_it_just_wrote(
    tmp_path: Path,
) -> None:
    """Req 6.2, 6.4: a user-renamed page whose base changes while its computed
    stem stays the same is renamed back to that stem, and its old and new
    charts are one file (``<stem>-hero.svg``), which must survive.

    Mutation: the stale set forgets to subtract the assets the new render
    writes (the rename deletes the chart it just wrote).
    """
    old = _trade_export(
        start_hours=0, created_hours=0, session=1, elapsed_s=3000.0, distance_m=9000.0
    )
    new = _trade_export(
        start_hours=0, created_hours=1, session=1, elapsed_s=3000.0, distance_m=9000.0
    )
    data_root = tmp_path / "data"
    data_root.mkdir()
    assert (
        _sync_dir(data_root, _put_files(tmp_path, "a", {"f.fit": old})).failures == ()
    )
    page = _only_page(data_root)
    stem = page.stem
    page.rename(page.with_name("mine.md"))

    report = _sync_dir(data_root, _put_files(tmp_path, "b", {"f.fit": new}))

    assert report.failures == ()
    final = _only_page(data_root)
    assert final.stem == stem  # back at the computed name
    assert len(_rename_warnings(report)) == 1  # precondition: it did rename
    assert _assets(data_root) == {f"{stem}-hero.svg"} == _linked_assets(final)


def test_user_named_page_is_not_settled_onto_a_freed_name(tmp_path: Path) -> None:
    """Req 6.3, 6.6: page P, at a user-chosen name, is rewritten by a lower
    ranked file while its computed stem is held by page Q (so P's stem is
    suffixed); Q then moves off that stem in the same run. P keeps its name:
    only a page written *at* its suffixed name is settled.

    Mutation: record every page whose stem is suffixed as a settle candidate
    (P moves to Q's old name).
    """
    p_base = _trade_export(
        start_hours=0, created_hours=1, session=1, elapsed_s=3000.0, distance_m=9000.0
    )
    p_extra = _trade_export(
        start_hours=0, created_hours=0, session=1, elapsed_s=3000.0, distance_m=9000.0
    )
    q_old = _trade_export(
        start_hours=0, created_hours=0, session=2, elapsed_s=2000.0, distance_m=6000.0
    )
    q_new = _trade_export(
        start_hours=1, created_hours=1, session=2, elapsed_s=2000.0, distance_m=6000.0
    )
    data_root = tmp_path / "data"
    data_root.mkdir()
    assert (
        _sync_dir(data_root, _put_files(tmp_path, "a", {"f.fit": p_base})).failures
        == ()
    )
    p_page = _only_page(data_root)
    p_page.rename(p_page.with_name("mine.md"))
    assert (
        _sync_dir(data_root, _put_files(tmp_path, "b", {"f.fit": q_old})).failures == ()
    )
    assert {p.name for p in _pages(data_root)} == {"mine.md", f"{p_page.stem}.md"}

    report = _sync_dir(
        data_root, _put_files(tmp_path, "c", {"1-p.fit": p_extra, "2-q.fit": q_new})
    )

    assert report.failures == ()
    by_uuid = {_frontmatter(p)["uuid"]: p.name for p in _pages(data_root)}
    assert by_uuid[_uuid_of(1)] == "mine.md"
    assert len(_frontmatter(data_root / WORKOUTS_DIR / "mine.md")["sources"]) == 2  # type: ignore[arg-type]


def _links_and_assets_consistent(data_root: Path) -> None:
    """Every image link resolves, and no chart is unlinked."""
    linked: set[str] = set()
    for page in _pages(data_root):
        links = _linked_assets(page)
        assert links <= _assets(data_root), (page.name, links)
        linked |= links
    assert _assets(data_root) == linked


@pytest.mark.parametrize("heal", ["sync", "regen"])
@pytest.mark.parametrize("step", _STEPS[:4])
def test_a_fault_in_a_settle_rename_heals_on_the_next_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, step: str, heal: str
) -> None:
    """Req 6.7: the settle rename of the trading scenario is interrupted after
    each write step; the next ``sync`` over the same inputs (which skips every
    archived file) and, separately, ``regen`` end with each page at one path
    under its unsuffixed name, every image link resolving and no chart left.

    The states at the fault differ by step (still suffixed with both charts;
    still suffixed with broken links; moved with old content; complete), so
    the two shapes of stranded page are both exercised. Mutations: drop the
    stranded-page candidates from the settle pass (the ``sync`` heals of the
    first three steps redden); drop the in-task finish of a suffixed page
    (the ``regen`` heal after the asset step reddens, leaving the suffixed
    chart behind).
    """
    a_old = _trade_export(
        start_hours=1, created_hours=0, session=1, elapsed_s=3000.0, distance_m=9000.0
    )
    a_new = _trade_export(
        start_hours=0, created_hours=1, session=1, elapsed_s=3000.0, distance_m=9000.0
    )
    b_old = _trade_export(
        start_hours=0, created_hours=0, session=2, elapsed_s=2000.0, distance_m=6000.0
    )
    b_new = _trade_export(
        start_hours=1, created_hours=1, session=2, elapsed_s=2000.0, distance_m=6000.0
    )
    data_root = tmp_path / "data"
    data_root.mkdir()
    assert (
        _sync_dir(data_root, _put_files(tmp_path, "x", {"f.fit": a_old})).failures == ()
    )
    assert (
        _sync_dir(data_root, _put_files(tmp_path, "y", {"f.fit": b_old})).failures == ()
    )
    before = {_frontmatter(p)["uuid"]: p.name for p in _pages(data_root)}
    source = _put_files(tmp_path, "both", {"1-a.fit": a_new, "2-b.fit": b_new})

    real = getattr(sync_module, step)
    real_settle = sync_module._settle_pass
    settling = {"now": False}

    def settle_marker(*args: object, **kwargs: object) -> None:
        settling["now"] = True
        real_settle(*args, **kwargs)  # type: ignore[arg-type]

    def dying(*args: object, **kwargs: object) -> None:
        real(*args, **kwargs)
        if settling["now"]:
            raise RuntimeError("fault in settle")

    with monkeypatch.context() as patch:
        patch.setattr(sync_module, "_settle_pass", settle_marker)
        patch.setattr(sync_module, step, dying)
        crashed = _sync_dir(data_root, source)
    assert len(crashed.failures) == 1  # the settle really died
    assert len(_pages(data_root)) == 2  # each page at one path

    healed = _regen(data_root) if heal == "regen" else _sync_dir(data_root, source)
    assert healed.failures == ()
    after = {_frontmatter(p)["uuid"]: p.name for p in _pages(data_root)}
    assert after == {_uuid_of(1): before[_uuid_of(2)], _uuid_of(2): before[_uuid_of(1)]}
    _links_and_assets_consistent(data_root)


@pytest.mark.parametrize("heal", ["sync", "regen"])
def test_a_user_named_page_shaped_like_a_suffixed_one_is_never_moved(
    tmp_path: Path, heal: str
) -> None:
    """Req 6.3, 6.6: a page the user named ``<stem>-<8 hex>.md`` whose hex is not
    its uid is not a stranded page, though ``<stem>.md`` is free and it would
    compute that stem.

    Mutation: match the suffix by shape (any 8 hex characters) rather than by
    the page's own uid (the page moves).
    """
    data_root = tmp_path / "data"
    data_root.mkdir()
    older, _newer = fx.healthfit_reexport_pair()
    _sync_one(data_root, tmp_path, older)
    page = _only_page(data_root)
    assert not _uuid_text(older).startswith("deadbeef")
    mine = page.with_name(f"{page.stem}-deadbeef.md")
    page.rename(mine)
    _assets_before = _assets(data_root)

    if heal == "regen":
        assert _regen(data_root).failures == ()
    else:
        assert _sync_dir(data_root, tmp_path / "src-empty-not-there").failures == ()
    assert _only_page(data_root) == mine
    assert _assets(data_root) == _assets_before


@pytest.mark.parametrize("heal", ["sync", "regen"])
def test_a_page_at_its_own_uid_suffix_stays_when_it_computes_another_stem(
    tmp_path: Path, heal: str
) -> None:
    """Req 6.3, 6.6: a page whose filename is ``<U>-<its own uid8>.md`` with
    ``<U>.md`` free is moved only when the stem it computes unsuffixed is
    ``U``; here ``U`` is not that stem, so the page stays.

    Mutation: move a stranded-shaped page without comparing ``U`` to the
    computed stem (it moves to ``<U>.md``).
    """
    data_root = tmp_path / "data"
    data_root.mkdir()
    older, _newer = fx.healthfit_reexport_pair()
    _sync_one(data_root, tmp_path, older)
    page = _only_page(data_root)
    mine = page.with_name(f"not-the-computed-stem-{_uuid_text(older)[:8]}.md")
    page.rename(mine)
    before = mine.read_text(encoding="utf-8")

    if heal == "regen":
        assert _regen(data_root).failures == ()
    else:
        assert _sync_dir(data_root, tmp_path / "src-empty-not-there").failures == ()
    assert _only_page(data_root) == mine
    if heal == "sync":  # nothing was rewritten
        assert mine.read_text(encoding="utf-8") == before


# --- stranded-page settling (4.2, opportunistic) ---


def _stage_stranded(tmp_path: Path) -> tuple[Path, Path, Path, fx.Species]:
    """A synced page moved to ``<stem>-<uid8>.md`` (its own uid), its stem free."""
    data_root = tmp_path / "data"
    data_root.mkdir()
    older, _newer = fx.healthfit_reexport_pair()
    _sync_one(data_root, tmp_path, older)
    page = _only_page(data_root)
    stranded = page.with_name(f"{page.stem}-{_uuid_text(older)[:8]}.md")
    page.rename(stranded)
    return data_root, page, stranded, older


def _idle_sync(data_root: Path, tmp_path: Path) -> SyncReport:
    empty = tmp_path / "idle-src"
    empty.mkdir(exist_ok=True)
    return _sync_dir(data_root, empty)


def test_note_linking_a_suffixed_chart_does_not_make_a_page_stranded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Req 6.4, 6.7: only a page's generated content decides whether it is
    stranded; a note that links a chart named for the suffix (kept by Req 6.4)
    does not, so an idle sync writes nothing.

    Mutation: search the whole text (the page is rewritten on every idle run).
    """
    data_root, _page, stranded, older = _stage_stranded(tmp_path)
    settled = (
        data_root
        / WORKOUTS_DIR
        / stranded.name.replace(f"-{_uuid_text(older)[:8]}", "")
    )
    stranded.rename(settled)
    _write_note(
        settled, f"![old](assets/{settled.stem}-{_uuid_text(older)[:8]}-hero.svg)"
    )
    calls: list[Path] = []
    real = sync_module._write_document

    def spy(document: Path, markdown: str) -> None:
        calls.append(document)
        real(document, markdown)

    monkeypatch.setattr(sync_module, "_write_document", spy)
    report = _idle_sync(data_root, tmp_path)
    assert report.failures == () and report.written == ()
    assert calls == []


def test_a_stranded_page_settles_with_its_notices_and_the_free_reason(
    tmp_path: Path,
) -> None:
    """Req 6.5, 6.7: a page not written this run keeps its unmanaged-key notice
    when settled, and its rename notice says the unsuffixed name became free.

    Mutation: silence the notices for stranded pages too; report a base change
    as the reason.
    """
    data_root, page, stranded, _older = _stage_stranded(tmp_path)
    text = stranded.read_text(encoding="utf-8")
    stranded.write_text(text.replace("\n---\n", "\nmy_stray_key: 1\n---\n", 1))
    report = _idle_sync(data_root, tmp_path)
    assert report.failures == ()
    assert _only_page(data_root) == page
    details = [w.detail for w in report.warnings]
    assert any("my_stray_key" in d for d in details)
    renames = _rename_warnings(report)
    assert len(renames) == 1
    assert (
        f"the unsuffixed name {WORKOUTS_DIR}/{page.name} became free"
        in renames[0].detail
    )
    assert "base file changed" not in renames[0].detail


def test_a_regen_finish_of_a_stranded_page_gives_the_free_reason(
    tmp_path: Path,
) -> None:
    """Req 6.5: the in-task finish (no base change) is not blamed on the base."""
    data_root, page, stranded, _older = _stage_stranded(tmp_path)
    report = _regen(data_root)
    assert report.failures == ()
    assert _only_page(data_root) == page
    (rename,) = _rename_warnings(report)
    assert (
        f"the unsuffixed name {WORKOUTS_DIR}/{page.name} became free" in rename.detail
    )


def test_a_stranded_page_that_cannot_be_settled_is_left_and_reported_silently(
    tmp_path: Path,
) -> None:
    """Req 6.7: settling a stranded page is opportunistic. With its archived
    source gone, or its document version newer than this fitdocs, an idle sync
    exits clean with an empty report and the page untouched.

    Mutation: report the failure or the version warning (as a ledger entry
    would be).
    """
    for case in ("no-archive", "newer-version"):
        root = tmp_path / case
        root.mkdir()
        data_root, _page, stranded, older = _stage_stranded(root)
        if case == "no-archive":
            archive_path(data_root, _sha(older.data)).unlink()
        else:
            text = stranded.read_text(encoding="utf-8")
            edited, count = re.subn(
                r"^doc_version: \d+$", "doc_version: 9999", text, flags=re.MULTILINE
            )
            assert count == 1
            stranded.write_text(edited, encoding="utf-8")
        before = stranded.read_bytes()
        report = _idle_sync(data_root, root)
        assert report == SyncReport(written=(), skipped=(), failures=(), warnings=()), (
            case
        )
        assert stranded.read_bytes() == before, case
        assert _pages(data_root) == [stranded], case


@pytest.mark.parametrize("which", ["base", "first"])
def test_uid_of_a_page_without_a_session_uuid_is_its_base_hash(
    tmp_path: Path, which: str
) -> None:
    """Req 6.7: with no recorded UUID a page's uid is the sha of its LAST listed
    source (the base). Stranded at ``<U>-<base sha8>.md`` it settles; at
    ``<U>-<first source sha8>.md`` it is a user's name and stays.

    Mutations: no fallback (the base case stays); the first listed source (the
    decoy settles, the base case stays).
    """
    data_root = tmp_path / "data"
    data_root.mkdir()
    original, partner = fx.garmin_original(), fx.partner_copy()
    _sync_one(data_root, tmp_path, partner)
    _archive(data_root, original)
    page = _only_page(data_root)
    _set_sources(page, [_ref(original), _ref(partner)])
    assert _regen(data_root).failures == ()
    assert _frontmatter(page)["sources"] == [_ref(partner), _ref(original)]  # base last
    assert "uuid" not in _frontmatter(page)
    chosen = original if which == "base" else partner
    moved = page.with_name(f"{page.stem}-{_sha(chosen.data)[:8]}.md")
    page.rename(moved)

    assert _idle_sync(data_root, tmp_path).failures == ()
    assert _only_page(data_root) == (page if which == "base" else moved)


def test_a_ledger_settle_does_not_repeat_the_pages_notices(tmp_path: Path) -> None:
    """Req 6.5: the page the trading run writes carries an invalid effort tag.
    That run reports the tag once (on its write); the settle that then moves
    the same page is quiet about it.

    Mutation: settle ledger entries without ``quiet`` (two notices).
    """
    a_old = _trade_export(
        start_hours=1, created_hours=0, session=1, elapsed_s=3000.0, distance_m=9000.0
    )
    a_new = _trade_export(
        start_hours=0, created_hours=1, session=1, elapsed_s=3000.0, distance_m=9000.0
    )
    b_old = _trade_export(
        start_hours=0, created_hours=0, session=2, elapsed_s=2000.0, distance_m=6000.0
    )
    b_new = _trade_export(
        start_hours=1, created_hours=1, session=2, elapsed_s=2000.0, distance_m=6000.0
    )
    data_root = tmp_path / "data"
    data_root.mkdir()
    assert (
        _sync_dir(data_root, _put_files(tmp_path, "x", {"f.fit": a_old})).failures == ()
    )
    assert (
        _sync_dir(data_root, _put_files(tmp_path, "y", {"f.fit": b_old})).failures == ()
    )
    for page in _pages(data_root):
        if _frontmatter(page)["uuid"] == _uuid_of(1):
            text = page.read_text(encoding="utf-8")
            page.write_text(text.replace("\n---\n", "\neffort: banana\n---\n", 1))

    report = _sync_dir(
        data_root, _put_files(tmp_path, "both", {"1-a.fit": a_new, "2-b.fit": b_new})
    )

    assert report.failures == ()
    assert len(_rename_warnings(report)) == 3  # precondition: A moved twice, B once
    assert sum("effort" in w.detail for w in report.warnings) == 1


# --- planned sync runs (4.3) ---


def _tree(root: Path) -> dict[str, bytes]:
    """Every file under ``root`` (pages, assets, archive, tool state) by path."""
    return {
        str(path.relative_to(root)): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _sync_files(
    tmp_path: Path,
    data_root: Path,
    files: Sequence[tuple[str, bytes]],
    *,
    precedence: Precedence = DEFAULT_PRECEDENCE,
) -> SyncReport:
    """One ``sync`` over ``files``, discovered in the order given (each file's
    name starts with its position, and discovery sorts by path)."""
    source = tmp_path / f"run-{len(list(tmp_path.glob('run-*')))}"
    source.mkdir()
    for position, (name, data) in enumerate(files):
        (source / f"{position}-{name}.fit").write_bytes(data)
    return sync(
        source, data_root, athlete=None, tz=_TZ, tiles=_TILES, precedence=precedence
    )


def _garmin_run(*, elapsed_s: float, serial: int) -> bytes:
    """A Garmin run at the fixtures' common start: nine kilometres, its own device.

    Two of these differ only in ``elapsed_s`` and ``serial``, so the rule reads
    them as one session when their elapsed times are within 10 s and as two
    otherwise.
    """
    start = fx.garmin_original().start
    return fx.session_fit_bytes(
        sport="running",
        start=start,
        elapsed_s=elapsed_s,
        timer_s=elapsed_s,
        distance_m=9_000.0,
        manufacturer="garmin",
        product=3843,
        serial=serial,
        time_created=start,
    )


def _ride_pair() -> tuple[bytes, bytes]:
    """(Garmin original, HealthFit copy) of one ride."""
    run = fx.garmin_original()
    original = fx.session_fit_bytes(
        sport="cycling",
        start=run.start,
        elapsed_s=3000.0,
        timer_s=2900.0,
        distance_m=30_000.0,
        manufacturer="garmin",
        product=3843,
        serial=fx.garmin_original().serial,
        time_created=run.start,
        undocumented=fx.UNDOCUMENTED_COUNT,
    )
    copy = fx.session_fit_bytes(
        sport="cycling",
        start=run.start,
        elapsed_s=3000.5,
        timer_s=3000.5,
        distance_m=30_002.0,
        manufacturer="development",
        product=0,
        serial=fx.healthfit_copy().serial,
        time_created=run.start + 4 * 3600,
        session_uuid=tuple(range(60, 76)),
        device_manufacturer="garmin",
    )
    return original, copy


def _ref_of(data: bytes) -> str:
    return source_ref(_sha(data))


def test_a_healthfit_copy_and_its_garmin_original_give_one_page(
    tmp_path: Path,
) -> None:
    """Req 4.3, 5.7: the copy and its original are one page whether they arrive
    in one run or in two, and the original (the Garmin file) is the base.

    Mutation: decide each file against the pages as they stood before the run
    (the one-run case renders two pages).
    """
    copy, original = fx.healthfit_copy(), fx.garmin_original()
    trees: dict[str, dict[str, bytes]] = {}
    for label, batches in (
        ("one-run", [[copy, original]]),
        ("copy-then-original", [[copy], [original]]),
        ("original-then-copy", [[original], [copy]]),
    ):
        data_root = tmp_path / label / "data"
        data_root.mkdir(parents=True)
        for number, batch in enumerate(batches):
            report = _sync_files(
                tmp_path / label,
                data_root,
                [(f"f{number}-{n}", s.data) for n, s in enumerate(batch)],
            )
            assert report.failures == ()
        page = _only_page(data_root)
        assert _frontmatter(page)["sources"] == [_ref(copy), _ref(original)], label
        assert _frontmatter(page)["source_kind"] == "original"
        trees[label] = _tree(data_root)
    assert trees["one-run"] == trees["copy-then-original"]
    assert trees["one-run"] == trees["original-then-copy"]


def test_every_arrival_order_of_three_files_of_one_session_gives_one_tree(
    tmp_path: Path,
) -> None:
    """Req 4.8, 5.7: an original, its partner-API copy and the HealthFit copy
    give the same tree -- pages, assets and archive, byte for byte -- in every
    one of the six orders, delivered in one run or in three.

    Fixture: the three differ in undocumented messages, kind and creation time,
    so a page ranked or matched by arrival differs in its ``sources`` list or its
    base. Mutation: plan each file against the pages as they stood before the
    run (the one-run orders render three pages).
    """
    files = {
        "original": fx.garmin_original(),
        "partner": fx.partner_copy(),
        "copy": fx.healthfit_copy(),
    }
    trees: dict[tuple[str, tuple[str, ...]], dict[str, bytes]] = {}
    for order in itertools.permutations(files):
        for mode in ("one-run", "three-runs"):
            data_root = tmp_path / mode / "-".join(order) / "data"
            data_root.mkdir(parents=True)
            batches = (
                [[name] for name in order] if mode == "three-runs" else [list(order)]
            )
            for batch in batches:
                report = _sync_files(
                    tmp_path / mode / "-".join(order),
                    data_root,
                    [(name, files[name].data) for name in batch],
                )
                assert report.failures == (), (mode, order)
                assert report.warnings == () or all(
                    "renamed" in w.detail for w in report.warnings
                ), (mode, order, report.warnings)
            trees[(mode, order)] = _tree(data_root)
    assert len(trees) == 12
    reference = trees[("one-run", tuple(files))]
    page_paths = [
        name for name in reference if re.fullmatch(rf"{WORKOUTS_DIR}/20[^/]*\.md", name)
    ]
    assert len(page_paths) == 1  # one page, and the run wrote assets and archive
    assert len(reference) > 1 + len(files)
    sources = re.search(
        r"^sources:\n((?:- .*\n)+)",
        reference[page_paths[0]].decode(),
        re.MULTILINE,
    )
    assert sources is not None
    assert sources.group(1).split("\n")[:-1] == [
        f"- {_ref(files['copy'])}",
        f"- {_ref(files['partner'])}",
        f"- {_ref(files['original'])}",
    ]
    for key, tree in trees.items():
        assert tree == reference, key


def _stage_two_pages(tmp_path: Path) -> tuple[Path, bytes]:
    """Two pages (elapsed 3000 s and 3016 s: 16 s apart, so two sessions) and a
    third file 8 s from each, which matches both."""
    data_root = tmp_path / "data"
    data_root.mkdir()
    for number, elapsed in enumerate((3000.0, 3016.0)):
        report = _sync_files(
            tmp_path,
            data_root,
            [("page", _garmin_run(elapsed_s=elapsed, serial=11 + number))],
        )
        assert report.failures == ()
    assert len(_pages(data_root)) == 2  # precondition: two separate pages
    return data_root, _garmin_run(elapsed_s=3008.0, serial=13)


def test_a_file_matching_two_pages_is_held_archived_recorded_and_skipped(
    tmp_path: Path,
) -> None:
    """Req 4.5, 4.7, 4.11, 7.1, 7.5: a file that matches two pages changes
    neither, is archived, recorded in ``held.toml``, warned about (naming its
    archive ref, both pages and the evidence) and counted skipped -- never a
    failure -- and a second sync skips it quietly.

    Mutations: resolve the file to the first page (page changed, nothing held);
    count a held file as a failure (``failures``); archive without recording
    (no ``held.toml``); skip the warning (``warnings`` empty).
    """
    data_root, ambiguous = _stage_two_pages(tmp_path)
    before = _tree(data_root)
    pages = [str(p.relative_to(data_root).as_posix()) for p in _pages(data_root)]

    report = _sync_files(tmp_path, data_root, [("ambiguous", ambiguous)])

    sha = _sha(ambiguous)
    assert report.failures == ()
    assert report.written == ()
    assert len(report.skipped) == 1
    after = _tree(data_root)
    assert {path: after[path] for path in before} == before  # both pages unchanged
    assert set(after) - set(before) == {
        str(archive_path(data_root, sha).relative_to(data_root)),
        ".fitdocs/held.toml",
    }
    (entry,) = load_holds(data_root).entries
    assert entry.sha256 == sha
    assert entry.candidates == tuple(pages)
    assert entry.evidence == ("strict", "strict")
    (warning,) = report.warnings
    assert warning.doc == source_ref(sha)
    assert all(page in warning.detail for page in pages)
    assert "strict" in warning.detail

    again = _sync_files(tmp_path, data_root, [("ambiguous", ambiguous)])

    assert again.failures == ()
    assert len(again.skipped) == 1
    assert again.warnings == ()
    assert _tree(data_root) == after


def test_two_unlinked_files_claiming_one_page_are_both_held(tmp_path: Path) -> None:
    """Req 4.6, 4.7: two files 16 s apart in elapsed time, each 8 s from the
    page, each claim the page as a separate group; neither joins it.

    Mutation: resolve a double claim to the first group (the first file joins,
    the page changes).
    """
    data_root = tmp_path / "data"
    data_root.mkdir()
    _sync_files(tmp_path, data_root, [("p", _garmin_run(elapsed_s=3000.0, serial=11))])
    before = _tree(data_root)
    first = _garmin_run(elapsed_s=3008.0, serial=21)
    second = _garmin_run(elapsed_s=2992.0, serial=22)

    report = _sync_files(tmp_path, data_root, [("a", first), ("b", second)])

    assert report.failures == ()
    assert report.written == ()
    assert len(report.skipped) == 2
    after = _tree(data_root)
    assert {path: after[path] for path in before} == before
    record = load_holds(data_root)
    assert sorted(e.sha256 for e in record.entries) == sorted(
        [_sha(first), _sha(second)]
    )
    assert len(report.warnings) == 2
    for data in (first, second):
        assert archive_path(data_root, _sha(data)).read_bytes() == data


def test_a_sync_that_holds_nothing_creates_no_tool_state(
    tmp_path: Path,
) -> None:
    """Design (SyncEngine): the hold record is saved only when it changed, so a
    sync that holds nothing never creates ``.fitdocs/``.

    Mutation: save the (empty) record at the end of every run.
    """
    data_root = tmp_path / "data"
    data_root.mkdir()
    report = _sync_files(
        tmp_path,
        data_root,
        [("a", fx.garmin_original().data), ("b", fx.healthfit_copy().data)],
    )
    assert report.failures == ()
    assert len(report.written) == 2  # precondition: the run wrote a page
    assert not (data_root / ".fitdocs").exists()


def test_a_damaged_hold_record_stops_sync_before_any_write(tmp_path: Path) -> None:
    """Req 4.7: the record is read before anything is written; the error
    propagates and the data root is untouched.

    Mutation: load the record after the declarations are refreshed (the
    declaration files appear).
    """
    data_root = tmp_path / "data"
    data_root.mkdir()
    held = held_path(data_root)
    held.parent.mkdir()
    held.write_text("this is [not valid toml\n", encoding="utf-8")
    before = _tree(data_root)

    with pytest.raises(HoldRecordError, match="held.toml"):
        _sync_files(tmp_path, data_root, [("a", fx.garmin_original().data)])

    assert _tree(data_root) == before


def test_the_default_precedence_end_to_end(tmp_path: Path) -> None:
    """Maintainer decision 2026-09-29, Req 2.5, 5.1: a Stryd file and a HealthFit
    copy of one run take the copy as base; a Garmin original and a HealthFit copy
    of one ride take the original as base.

    Mutation: swap the ``original:garmin`` and ``phone_copy`` default tiers (the
    ride takes the copy).
    """
    copy, stryd = fx.healthfit_copy(), fx.stryd_file()
    run_root = tmp_path / "run" / "data"
    run_root.mkdir(parents=True)
    report = _sync_files(
        tmp_path / "run", run_root, [("stryd", stryd.data), ("copy", copy.data)]
    )
    assert report.failures == ()
    run_page = _frontmatter(_only_page(run_root))
    assert run_page["sources"] == [_ref(stryd), _ref(copy)]
    assert run_page["source_kind"] == "phone_copy"

    ride_original, ride_copy = _ride_pair()
    ride_root = tmp_path / "ride" / "data"
    ride_root.mkdir(parents=True)
    report = _sync_files(
        tmp_path / "ride",
        ride_root,
        [("copy", ride_copy), ("original", ride_original)],
    )
    assert report.failures == ()
    ride_page = _frontmatter(_only_page(ride_root))
    assert ride_page["sources"] == [_ref_of(ride_copy), _ref_of(ride_original)]
    assert ride_page["source_kind"] == "original"


def test_a_configured_precedence_makes_the_stryd_file_the_base(
    tmp_path: Path,
) -> None:
    """Req 2.6: under ``["original", "phone_copy", "unknown"]`` the run of the
    Stryd file and the HealthFit copy renders from the Stryd file.

    Mutation: plan the run without the given precedence (the copy stays base).
    """
    copy, stryd = fx.healthfit_copy(), fx.stryd_file()
    data_root = tmp_path / "data"
    data_root.mkdir()
    precedence = resolve_precedence(
        [
            PrecedenceEntry(SourceKind.ORIGINAL),
            PrecedenceEntry(SourceKind.PHONE_COPY),
            PrecedenceEntry(SourceKind.UNKNOWN),
        ]
    )

    report = _sync_files(
        tmp_path,
        data_root,
        [("copy", copy.data), ("stryd", stryd.data)],
        precedence=precedence,
    )

    assert report.failures == ()
    page = _frontmatter(_only_page(data_root))
    assert page["sources"] == [_ref(copy), _ref(stryd)]
    assert page["source_kind"] == "original"


def test_a_group_claiming_a_page_of_a_newer_version_changes_nothing(
    tmp_path: Path,
) -> None:
    """Req 6.8: a group of two files that would outrank the page's base (and
    rename it) leaves the page, its filename and its assets byte-unchanged,
    archives neither member, and warns once naming the page.

    Fixture: the page was rendered from a copy shifted two hours, so the same
    group on a page of the current version renames it (the control below).
    Mutation: apply the version gate after the writes (the page moves and the
    members are archived).
    """
    original, partner = fx.garmin_original(), fx.partner_copy()

    def stage(name: str) -> tuple[Path, Path]:
        data_root = tmp_path / name / "data"
        data_root.mkdir(parents=True)
        _sync_one(data_root, tmp_path / name, fx.healthfit_shifted())
        return data_root, _only_page(data_root)

    control_root, _ = stage("control")
    control = _sync_files(
        tmp_path / "control",
        control_root,
        [("o", original.data), ("p", partner.data)],
    )
    assert len(_rename_warnings(control)) == 1  # precondition: it would rename

    data_root, page = stage("gated")
    page.write_text(
        page.read_text(encoding="utf-8").replace(
            f"doc_version: {DOC_VERSION}", "doc_version: 9999", 1
        ),
        encoding="utf-8",
    )
    before = _tree(data_root)

    report = _sync_files(
        tmp_path / "gated", data_root, [("o", original.data), ("p", partner.data)]
    )

    assert report.failures == ()
    assert report.written == ()
    assert len(report.skipped) == 2
    assert _tree(data_root) == before
    assert not archive_path(data_root, _sha(original.data)).exists()
    assert not archive_path(data_root, _sha(partner.data)).exists()
    (warning,) = report.warnings
    assert warning.doc == page.relative_to(data_root).as_posix()
    assert "9999" in warning.detail


def test_when_the_hold_record_cannot_be_saved_the_file_is_not_archived(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Req 4.7, 6.7: the record is saved before the archive is written, so a
    failed save leaves the file unarchived; the next run plans it again and
    holds it.

    Mutation: archive the file before recording it (it is archived, so the next
    run skips it with nothing naming it).
    """
    data_root, ambiguous = _stage_two_pages(tmp_path)
    before = _tree(data_root)

    def failing(*_args: object, **_kwargs: object) -> bool:
        raise OSError("disk full")

    with monkeypatch.context() as patch:
        patch.setattr(sync_module, "save_holds", failing)
        report = _sync_files(tmp_path, data_root, [("ambiguous", ambiguous)])

    assert len(report.failures) == 1
    assert "disk full" in report.failures[0].reason
    assert report.skipped == ()
    assert _tree(data_root) == before
    assert not archive_path(data_root, _sha(ambiguous)).exists()

    retry = _sync_files(tmp_path, data_root, [("ambiguous", ambiguous)])

    assert retry.failures == ()
    assert len(retry.skipped) == 1
    assert [e.sha256 for e in load_holds(data_root).entries] == [_sha(ambiguous)]
    assert archive_path(data_root, _sha(ambiguous)).is_file()


def test_held_candidates_follow_a_rename_the_same_run_makes(tmp_path: Path) -> None:
    """Design (SyncEngine hold task): a page a hold names is renamed in the same
    run, and the record names the page where it ended.

    Fixture: page A is the older HealthFit export, page B a Garmin run; a file
    that matches both is held while the newer export (pinned to A by its session
    UUID) corrects A's start and renames it. Mutation: skip the rewrite (the
    record names the path A had before the run).
    """
    older, newer = fx.healthfit_reexport_pair()
    data_root = tmp_path / "data"
    data_root.mkdir()
    _sync_files(tmp_path, data_root, [("a", older.data)])
    _sync_files(tmp_path, data_root, [("b", _garmin_run(elapsed_s=3008.0, serial=12))])
    old_paths = {p.relative_to(data_root).as_posix() for p in _pages(data_root)}
    assert len(old_paths) == 2  # precondition: two pages
    ambiguous = _garmin_run(elapsed_s=3004.0, serial=13)

    report = _sync_files(
        tmp_path, data_root, [("1-newer", newer.data), ("2-ambiguous", ambiguous)]
    )

    assert report.failures == ()
    assert len(_rename_warnings(report)) == 1  # precondition: A was renamed
    new_paths = {p.relative_to(data_root).as_posix() for p in _pages(data_root)}
    assert new_paths != old_paths
    (entry,) = load_holds(data_root).entries
    assert set(entry.candidates) == new_paths
    assert len(entry.candidates) == 2


def test_a_file_that_changes_during_the_run_fails_alone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Design (page task): a task re-reads its files and fails a member whose
    bytes changed since planning; its group's other member is still written and
    nothing is archived for the changed one.

    Fixture: after the plan, the original's file is replaced by another valid
    ``.fit`` (the partner copy), so a task that trusts the planned hash would
    archive the wrong bytes. Mutation: skip the hash comparison.
    """
    copy, original, partner = (
        fx.healthfit_copy(),
        fx.garmin_original(),
        fx.partner_copy(),
    )
    data_root = tmp_path / "data"
    data_root.mkdir()
    source = tmp_path / "src"
    source.mkdir()
    (source / "1-copy.fit").write_bytes(copy.data)
    (source / "2-original.fit").write_bytes(original.data)
    real_plan = planning.plan_run

    def plan_then_change(*args: object, **kwargs: object) -> object:
        plan = real_plan(*args, **kwargs)  # type: ignore[arg-type]
        (source / "2-original.fit").write_bytes(partner.data)
        return plan

    monkeypatch.setattr(sync_module, "plan_run", plan_then_change)
    report = sync(source, data_root, athlete=None, tz=_TZ, tiles=_TILES)

    assert [f.source for f in report.failures] == [str(source / "2-original.fit")]
    assert "changed during the run" in report.failures[0].reason
    assert len(report.written) == 1
    assert _frontmatter(_only_page(data_root))["sources"] == [_ref(copy)]
    assert not archive_path(data_root, _sha(original.data)).exists()
    assert not archive_path(data_root, _sha(partner.data)).exists()
    assert archive_path(data_root, _sha(copy.data)).is_file()


def test_outcomes_are_reported_in_discovery_order_whatever_order_tasks_run(
    tmp_path: Path,
) -> None:
    """Req 4.8 (design, Report): a group's members are reported where each was
    discovered, not together, and a failure keeps its own slot.

    Fixture: files 0 and 3 are one session (one group, one task, run first),
    files 1 and 4 are two other sessions and file 2 is not a ``.fit`` file, so
    task order (0/3, 1, 4) differs from discovery order (0, 1, 3, 4) and the
    expected list is not a palindrome. Mutation: report in reverse.
    """
    copy, original = fx.healthfit_copy(), fx.garmin_original()
    other, last = fx.ten_k_pair()
    data_root = tmp_path / "data"
    data_root.mkdir()

    report = _sync_files(
        tmp_path,
        data_root,
        [
            ("copy", copy.data),
            ("other", other.data),
            ("bad", b"not a fit file"),
            ("original", original.data),
            ("last", last.data),
        ],
    )

    pages: dict[tuple[str, ...], str] = {}
    for page in _pages(data_root):
        listed = _frontmatter(page)["sources"]
        assert isinstance(listed, list)
        pages[tuple(str(ref) for ref in listed)] = page.relative_to(
            data_root
        ).as_posix()
    shared = pages[(_ref(copy), _ref(original))]
    solo = pages[(_ref(other),)]
    final = pages[(_ref(last),)]
    assert shared != solo  # precondition: two pages
    assert report.written == (shared, solo, shared, final)
    assert [Path(f.source).name for f in report.failures] == ["2-bad.fit"]


def test_a_held_file_that_changes_during_the_run_is_failed_not_recorded(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Design (hold task): the hold task re-reads its file and refuses one whose
    bytes changed since planning -- nothing is recorded or archived for it.

    Fixture: after the plan, the ambiguous file is replaced by another valid
    ``.fit``, so a task that trusts the planned hash would record and archive
    the wrong bytes under it. Mutation: the hold task reads the file without
    comparing its hash.
    """
    data_root, ambiguous = _stage_two_pages(tmp_path)
    replacement = fx.partner_copy().data
    before = _tree(data_root)
    source = tmp_path / "src"
    source.mkdir()
    (source / "a.fit").write_bytes(ambiguous)
    real_plan = planning.plan_run

    def plan_then_change(*args: object, **kwargs: object) -> object:
        plan = real_plan(*args, **kwargs)  # type: ignore[arg-type]
        (source / "a.fit").write_bytes(replacement)
        return plan

    monkeypatch.setattr(sync_module, "plan_run", plan_then_change)
    report = sync(source, data_root, athlete=None, tz=_TZ, tiles=_TILES)

    assert len(report.failures) == 1
    assert "changed during the run" in report.failures[0].reason
    assert report.skipped == ()
    assert _tree(data_root) == before  # no archive at either hash, no held.toml
    assert not archive_path(data_root, _sha(ambiguous)).exists()
    assert not archive_path(data_root, _sha(replacement)).exists()
    assert not held_path(data_root).exists()


def _stage_damaged_page(tmp_path: Path) -> tuple[Path, Path]:
    """A page rendered from the HealthFit copy whose ``notes`` end marker is gone,
    so any rewrite of it raises a region error."""
    data_root = tmp_path / "data"
    data_root.mkdir()
    _sync_one(data_root, tmp_path, fx.healthfit_copy())
    page = _only_page(data_root)
    text = page.read_text(encoding="utf-8")
    assert end_marker("notes") in text
    page.write_text(text.replace(end_marker("notes"), "", 1), encoding="utf-8")
    return data_root, page


def test_a_task_exception_fails_every_member_of_its_group_with_one_reason(
    tmp_path: Path,
) -> None:
    """Req 1.3 (design, page task): when a group's task raises, every member
    fails with the same reason and none is archived.

    Fixture: a two-file group (the original and its partner copy) claims a page
    whose region markers are damaged. Mutation: only the first member fails
    (the second is reported written or skipped, or archived).
    """
    data_root, page = _stage_damaged_page(tmp_path)
    original, partner = fx.garmin_original(), fx.partner_copy()
    before = _tree(data_root)

    report = _sync_files(
        tmp_path, data_root, [("o", original.data), ("p", partner.data)]
    )

    assert len(report.failures) == 2
    assert {Path(f.source).name for f in report.failures} == {"0-o.fit", "1-p.fit"}
    assert len({f.reason for f in report.failures}) == 1
    assert "Region" in report.failures[0].reason
    assert report.skipped == ()
    assert report.written == ()
    assert _tree(data_root) == before
    assert not archive_path(data_root, _sha(original.data)).exists()
    assert not archive_path(data_root, _sha(partner.data)).exists()


def test_a_duplicate_of_a_file_whose_task_failed_is_a_failure_too(
    tmp_path: Path,
) -> None:
    """Design (preparation): identical bytes discovered twice are one file; when
    its task fails, the second copy inherits the failure, as two runs of the
    old per-file pipeline would have reported it.

    Mutation: report the duplicate as skipped whatever its first copy did.
    """
    data_root, _page = _stage_damaged_page(tmp_path)
    original = fx.garmin_original()

    report = _sync_files(
        tmp_path, data_root, [("a", original.data), ("b", original.data)]
    )

    assert {Path(f.source).name for f in report.failures} == {"0-a.fit", "1-b.fit"}
    assert len({f.reason for f in report.failures}) == 1
    assert report.skipped == ()
    assert not archive_path(data_root, _sha(original.data)).exists()


@pytest.mark.parametrize("entry_point", ["sync", "drain"])
def test_settle_renames_of_the_run_carry_into_the_held_candidates(
    tmp_path: Path, entry_point: str
) -> None:
    """Design (hold task): candidates are rewritten through the task renames and
    then the settle renames, so a candidate settled onto a freed name is recorded
    at that name.

    Fixture: three pages 16 s apart in elapsed time (the first owns the
    unsuffixed name, the others sit under a suffix); the first is deleted, and a
    file 8 s from the second and third matches both. The run's settle pass moves
    one suffixed page onto the freed name. Mutation: rewrite through the task
    renames only (the record names the vanished suffixed path), in ``sync`` and
    in the drain alike.
    """
    data_root = tmp_path / "data"
    data_root.mkdir()
    for number, elapsed in enumerate((3000.0, 3016.0, 3032.0)):
        _sync_files(
            tmp_path,
            data_root,
            [("p", _garmin_run(elapsed_s=elapsed, serial=11 + number))],
        )
    pages = _pages(data_root)
    assert len(pages) == 3  # precondition: three separate pages
    unsuffixed = min(pages, key=lambda p: len(p.name))
    unsuffixed.unlink()
    ambiguous = _garmin_run(elapsed_s=3024.0, serial=14)

    if entry_point == "sync":
        report = _sync_files(tmp_path, data_root, [("x", ambiguous)])
    else:
        inbox = _put_inbox(tmp_path, [("x", ambiguous)])
        report = _drain_inbox(tmp_path, data_root, inbox).sync

    assert report.failures == ()
    (entry,) = load_holds(data_root).entries
    now = {p.relative_to(data_root).as_posix() for p in _pages(data_root)}
    assert len(now) == 2
    assert set(entry.candidates) == now
    freed = unsuffixed.relative_to(data_root).as_posix()
    assert freed in now  # precondition: the settle pass did move a page onto it


def test_a_hold_is_applied_in_discovery_order_among_the_page_tasks(
    tmp_path: Path,
) -> None:
    """Design (SyncEngine): hold tasks and page tasks run in first-member order,
    and warnings are in task order -- not sorted by anything else.

    Fixture: the ambiguous file is discovered once before and once after the
    re-export that renames a page. The archive ref of the held warning sorts
    before the renamed page's path, so the discovery order that puts the rename
    first is the one a sort by ``doc`` cannot fake. Mutations: apply every hold
    after the page tasks (the held-first order reds); sort the run's warnings by
    ``doc`` (the renamed-first order reds).
    """
    older, newer = fx.healthfit_reexport_pair()
    ambiguous = _garmin_run(elapsed_s=3004.0, serial=13)
    held_doc = source_ref(_sha(ambiguous))
    for label, order in (
        ("held-first", ("ambiguous", "newer")),
        ("renamed-first", ("newer", "ambiguous")),
    ):
        base = tmp_path / label
        base.mkdir()
        data_root = base / "data"
        data_root.mkdir()
        _sync_files(base, data_root, [("a", older.data)])
        _sync_files(base, data_root, [("b", _garmin_run(elapsed_s=3008.0, serial=12))])
        data = {"ambiguous": ambiguous, "newer": newer.data}

        report = _sync_files(base, data_root, [(n, data[n]) for n in order])

        assert report.failures == ()
        kinds = [
            "held" if w.doc == held_doc else "renamed"
            for w in report.warnings
            if w.doc == held_doc or "renamed" in w.detail
        ]
        expected = (
            ["held", "renamed"] if order[0] == "ambiguous" else ["renamed", "held"]
        )
        assert kinds == expected, label


def test_held_candidates_follow_a_task_rename_and_then_a_settle_rename(
    tmp_path: Path,
) -> None:
    """Design (hold task): the run's renames are applied in the order they
    happened -- the task renames, then the settle renames -- so a page moved
    ``a`` to ``b`` and then ``b`` to ``c`` is recorded at ``c``.

    Mutation: apply the maps in reverse order (the record names ``b``).
    """
    entry = HeldSource(
        sha256="0" * 64, name="x.fit", candidates=("a", "other"), evidence=("strict",)
    )
    holds = sync_module._HoldState(HoldRecord(entries=(entry,)))

    sync_module._finish_holds(tmp_path, holds, {"a": "b"}, {"b": "c"})

    assert holds.record.entries[0].candidates == ("c", "other")
    assert load_holds(tmp_path).entries[0].candidates == ("c", "other")


# --- drain (4.4) ---

_MOVE_INBOX = replace(
    DEFAULT_INBOX_SETTINGS, settle_seconds=0.0, disposition=Disposition.MOVE
)


def _inbox_files(inbox: Path) -> list[str]:
    return sorted(p.name for p in inbox.iterdir()) if inbox.exists() else []


def _put_inbox(base: Path, files: Sequence[tuple[str, bytes]]) -> Path:
    """A fresh inbox holding ``files`` (name, bytes), a directory per call."""
    inbox = base / f"inbox-{len(list(base.glob('inbox-*')))}"
    inbox.mkdir(parents=True)
    for name, data in files:
        (inbox / f"{name}.fit").write_bytes(data)
    return inbox


def _drain_inbox(
    base: Path,
    data_root: Path,
    inbox: Path,
    *,
    precedence: Precedence = DEFAULT_PRECEDENCE,
) -> sync_module.DrainReport:
    """One draining run under the move disposition (processed files go to
    ``<base>/processed``)."""
    return drain(
        inbox,
        data_root,
        settings=_MOVE_INBOX,
        processed_dir=base / "processed",
        quarantine=load_quarantine(data_root),
        athlete=None,
        tz=_TZ,
        tiles=_TILES,
        sleep=lambda _seconds: None,
        precedence=precedence,
    )


def test_a_healthfit_page_then_a_garmin_original_in_the_inbox_join_and_move(
    tmp_path: Path,
) -> None:
    """Req 4.1, 4.3, 4.11: the HealthFit page exists; the Garmin original dropped
    in the inbox joins it (one page, the original its base) and is moved out; the
    same two files dropped in one inbox give the tree ``sync`` gives them in one
    run.

    Mutation: skip planning in the drain and run the old per-file pipeline
    (``_process_isolated``) on each candidate (this test reds). Planning each
    candidate alone through ``_run_planned`` would not: one file per run joins
    the same page in either order.
    """
    copy, original = fx.healthfit_copy(), fx.garmin_original()
    data_root = tmp_path / "then" / "data"
    data_root.mkdir(parents=True)
    _sync_one(data_root, tmp_path / "then", copy)
    inbox = _put_inbox(tmp_path / "then", [("original", original.data)])

    report = _drain_inbox(tmp_path / "then", data_root, inbox)

    assert report.sync.failures == ()
    assert len(report.sync.written) == 1
    assert report.moved != () and len(report.moved) == 1
    assert _inbox_files(inbox) == []
    page = _only_page(data_root)
    assert _frontmatter(page)["sources"] == [_ref(copy), _ref(original)]
    assert _frontmatter(page)["source_kind"] == "original"

    together_root = tmp_path / "together" / "data"
    together_root.mkdir(parents=True)
    both = _put_inbox(
        tmp_path / "together", [("a-copy", copy.data), ("b-original", original.data)]
    )
    drained = _drain_inbox(tmp_path / "together", together_root, both)
    assert drained.sync.failures == ()
    assert len(drained.moved) == 2
    assert _inbox_files(both) == []
    reference_root = tmp_path / "reference" / "data"
    reference_root.mkdir(parents=True)
    reference = _sync_files(
        tmp_path / "reference",
        reference_root,
        [("a-copy", copy.data), ("b-original", original.data)],
    )
    assert reference.failures == ()
    together = _tree(together_root)
    assert together == _tree(reference_root)


def test_the_drain_plans_from_the_probe_bytes_and_reads_a_candidate_twice(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Design (run preparation): the drain reuses the probe read, so a written
    candidate is read twice -- the probe, and the task's confirmation that the
    planned bytes are still the file's.

    Mutation: prepare from a fresh read instead of the probe bytes (three reads).
    """
    data_root = tmp_path / "data"
    data_root.mkdir()
    inbox = _put_inbox(tmp_path, [("run", fx.garmin_original().data)])
    target = inbox / "run.fit"
    reads: list[Path] = []
    real_read = Path.read_bytes

    def counting(self: Path) -> bytes:
        if self == target:
            reads.append(self)
        return real_read(self)

    monkeypatch.setattr(Path, "read_bytes", counting)

    report = _drain_inbox(tmp_path, data_root, inbox)

    assert len(report.sync.written) == 1  # the candidate really was applied
    assert len(reads) == 2


def test_an_ambiguous_candidate_is_held_moved_and_never_quarantined(
    tmp_path: Path,
) -> None:
    """Req 4.5, 4.7, 4.11, 7.5: a candidate that matches two pages changes
    neither, is archived and recorded, is reported skipped with the hold
    warning, is moved out of the inbox under the move disposition (it is
    archived), and is absent from the quarantine record; dropped again, it is
    skipped quietly.

    Mutations: quarantine a held candidate (the record names it); leave a held
    candidate in the inbox (the inbox still lists it); hold without archiving
    (the archive is missing and the file stays).
    """
    data_root, ambiguous = _stage_two_pages(tmp_path)
    before = _tree(data_root)
    sha = _sha(ambiguous)
    inbox = _put_inbox(tmp_path, [("ambiguous", ambiguous)])

    report = _drain_inbox(tmp_path, data_root, inbox)

    assert report.sync.failures == ()
    assert report.sync.written == ()
    assert report.sync.skipped == ("ambiguous.fit",)
    (warning,) = report.sync.warnings
    assert warning.doc == source_ref(sha)
    assert "held, not merged" in warning.detail
    after = _tree(data_root)
    assert {path: after[path] for path in before} == before  # both pages unchanged
    (entry,) = load_holds(data_root).entries
    assert entry.sha256 == sha
    assert archive_path(data_root, sha).is_file()
    assert len(report.moved) == 1
    assert report.move_failures == ()
    assert _inbox_files(inbox) == []
    assert (tmp_path / "processed").is_dir()
    assert report.quarantined == ()
    assert load_quarantine(data_root).entries == ()
    assert not quarantine_path(data_root).exists()

    again = _put_inbox(tmp_path, [("ambiguous", ambiguous)])
    second = _drain_inbox(tmp_path, data_root, again)

    assert second.sync.failures == ()
    assert second.sync.warnings == ()
    assert second.sync.skipped == ("ambiguous.fit",)
    assert _tree(data_root) == after


def test_a_document_failure_in_a_group_task_quarantines_no_member(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Req 4.1, inbox 5.7: two candidates of one session join one damaged page in
    one task; the document's fault fails both, neither is quarantined (a fault of
    the page is not a property of their bytes), and both stay in the inbox.

    Mutation: treat every failure as source-level (the record names both).
    """
    copy, original, partner = (
        fx.healthfit_copy(),
        fx.garmin_original(),
        fx.partner_copy(),
    )
    data_root = tmp_path / "data"
    data_root.mkdir()
    _sync_one(data_root, tmp_path, copy)
    page = _only_page(data_root)
    text = page.read_text(encoding="utf-8")
    assert text.count(end_marker("notes")) == 1  # precondition
    page.write_text(text.replace(end_marker("notes"), ""), encoding="utf-8")
    damaged = _tree(data_root)
    inbox = _put_inbox(
        tmp_path, [("a-original", original.data), ("b-partner", partner.data)]
    )
    group_sizes: list[int] = []
    real_group = sync_module._group_task

    def spy(
        members: list[sync_module._Prepared], *args: object, **kwargs: object
    ) -> None:
        group_sizes.append(len(members))
        real_group(members, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(sync_module, "_group_task", spy)

    report = _drain_inbox(tmp_path, data_root, inbox)

    assert group_sizes == [2]  # precondition: one task, both members
    assert [f.source for f in report.sync.failures] == [
        "a-original.fit",
        "b-partner.fit",
    ]
    assert report.quarantined == ()
    assert load_quarantine(data_root).entries == ()
    assert not quarantine_path(data_root).exists()
    assert report.moved == ()
    assert _inbox_files(inbox) == ["a-original.fit", "b-partner.fit"]
    assert _tree(data_root) == damaged


def _snapshot_tree(root: Path) -> dict[str, bytes | None]:
    """Every path under ``root`` (directories as ``None``) with its bytes."""
    return {
        str(p.relative_to(root)): (p.read_bytes() if p.is_file() else None)
        for p in sorted(root.rglob("*"))
    }


def test_a_damaged_hold_record_raises_before_the_drain_writes_anything(
    tmp_path: Path,
) -> None:
    """Req 4.7, 4.10: the drain loads the hold record before the declaration
    refresh, so a damaged one raises with the data root and the inbox exactly as
    they were -- no declaration written, no candidate archived or moved.

    Mutation: load the record after the declaration refresh (the refresh writes
    ``AGENTS.md`` first, so the snapshot differs).
    """
    data_root = tmp_path / "data"
    (data_root / ".fitdocs").mkdir(parents=True)
    held_path(data_root).write_text("this is [not valid toml\n", encoding="utf-8")
    inbox = _put_inbox(tmp_path, [("run", fx.garmin_original().data)])
    before = _snapshot_tree(data_root)
    inbox_before = _snapshot_tree(inbox)
    assert set(before) == {".fitdocs", ".fitdocs/held.toml"}  # nothing to refresh yet

    with pytest.raises(HoldRecordError):
        _drain_inbox(tmp_path, data_root, inbox)

    assert _snapshot_tree(data_root) == before
    assert _snapshot_tree(inbox) == inbox_before
    assert not (tmp_path / "processed").exists()


def test_held_candidates_follow_a_rename_the_same_drain_makes(tmp_path: Path) -> None:
    """Design (hold task, drain): a page a hold names is renamed in the same
    drain, and the record names the page where it ended.

    Fixture: as the ``sync`` version above, with the newer export and the
    ambiguous file dropped in one inbox. Mutation: skip the drain's
    ``_finish_holds`` (the record names the path a page had before the run).
    """
    older, newer = fx.healthfit_reexport_pair()
    data_root = tmp_path / "data"
    data_root.mkdir()
    _sync_files(tmp_path, data_root, [("a", older.data)])
    _sync_files(tmp_path, data_root, [("b", _garmin_run(elapsed_s=3008.0, serial=12))])
    old_paths = {p.relative_to(data_root).as_posix() for p in _pages(data_root)}
    assert len(old_paths) == 2  # precondition: two pages
    inbox = _put_inbox(
        tmp_path,
        [
            ("1-newer", newer.data),
            ("2-ambiguous", _garmin_run(elapsed_s=3004.0, serial=13)),
        ],
    )

    report = _drain_inbox(tmp_path, data_root, inbox)

    assert report.sync.failures == ()
    assert len(_rename_warnings(report.sync)) == 1  # precondition: A was renamed
    new_paths = {p.relative_to(data_root).as_posix() for p in _pages(data_root)}
    assert new_paths != old_paths
    (entry,) = load_holds(data_root).entries
    assert set(entry.candidates) == new_paths
    assert len(entry.candidates) == 2


# --- regeneration (4.5) ---


def _held_text(data_root: Path) -> str:
    return held_path(data_root).read_text(encoding="utf-8")


def _sources(page: Path) -> list[str]:
    sources = _frontmatter(page)["sources"]
    assert isinstance(sources, list)
    return [str(ref) for ref in sources]


def _stage_held(tmp_path: Path) -> tuple[Path, bytes]:
    """Two pages (16 s apart) and a third file matching both, which is held."""
    data_root, ambiguous = _stage_two_pages(tmp_path)
    report = _sync_files(tmp_path, data_root, [("ambiguous", ambiguous)])
    assert report.failures == ()
    assert len(load_holds(data_root).entries) == 1  # precondition: it is held
    return data_root, ambiguous


def _archive_names(data_root: Path) -> list[str]:
    return sorted(p.name for p in (data_root / "fit-archive").glob("*.fit"))


def test_deleting_one_of_two_duplicate_pages_joins_its_files_and_empties_the_hold(
    tmp_path: Path,
) -> None:
    """Req 4.10: the held file and the deleted page's own file are archived files
    no page lists; regeneration plans them against the page that is left, both
    join it, the hold record ends with no entry, the page settles onto the freed
    name, and the archive gains and loses nothing.

    Mutations: skip held files in regeneration (the held file stays out of the
    page); merge with the old record instead of replacing it (the entry
    stays); render unreferenced archives fresh without planning (a second page
    for each, none joined).
    """
    data_root, ambiguous = _stage_held(tmp_path)
    pages = _pages(data_root)
    victim = min(pages, key=lambda p: len(p.name))  # the unsuffixed name
    (survivor,) = [p for p in pages if p != victim]
    assert survivor.stem != victim.stem  # precondition: the survivor is suffixed
    refs = {
        _ref_of(_garmin_run(elapsed_s=3000.0, serial=11)),
        _ref_of(_garmin_run(elapsed_s=3016.0, serial=12)),
        _ref_of(ambiguous),
    }
    archives = _archive_names(data_root)
    victim.unlink()

    report = _regen(data_root)

    assert report.failures == ()
    page = _only_page(data_root)
    assert page.name == victim.name  # onto the name the deletion freed
    assert len(_sources(page)) == 3
    assert set(_sources(page)) == refs
    assert load_holds(data_root).entries == ()
    assert "[[held]]" not in _held_text(data_root)
    assert _archive_names(data_root) == archives
    assert not any("held" in w.detail for w in report.warnings)


def test_a_damaged_hold_record_is_rebuilt_by_regeneration(tmp_path: Path) -> None:
    """Req 4.10: regeneration never reads the old record, so a damaged one is
    replaced by the re-derived hold (the same sha, both pages, the same
    evidence; ``name`` is the archive ref, the only label regeneration has),
    and the next sync reads it.

    Mutation: load the old record at the start of regeneration (raises).
    """
    data_root, ambiguous = _stage_held(tmp_path)
    pages = [p.relative_to(data_root).as_posix() for p in _pages(data_root)]
    held_path(data_root).write_text("this is [not valid toml\n", encoding="utf-8")
    with pytest.raises(HoldRecordError):  # precondition: it is unreadable
        load_holds(data_root)

    report = _regen(data_root)

    assert report.failures == ()
    (entry,) = load_holds(data_root).entries
    assert entry == HeldSource(
        sha256=_sha(ambiguous),
        name=_ref_of(ambiguous),
        candidates=tuple(pages),
        evidence=("strict", "strict"),
    )
    again = _sync_files(tmp_path, data_root, [("again", ambiguous)])
    assert again.failures == ()


def test_a_stale_hold_for_a_vanished_archive_is_not_re_held(tmp_path: Path) -> None:
    """Req 4.10: an entry whose archived file no longer exists names nothing
    regeneration can plan, so it does not survive; the entry for a file that is
    still archived does.

    Mutation: merge with the old record instead of replacing it.
    """
    data_root, ambiguous = _stage_held(tmp_path)
    other = _garmin_run(elapsed_s=3008.5, serial=14)  # also matches both pages
    _sync_files(tmp_path, data_root, [("other", other)])
    assert len(load_holds(data_root).entries) == 2  # precondition
    archive_path(data_root, _sha(ambiguous)).unlink()

    report = _regen(data_root)

    assert report.failures == ()
    (entry,) = load_holds(data_root).entries
    assert entry.sha256 == _sha(other)


def test_regen_that_holds_nothing_creates_no_tool_state(tmp_path: Path) -> None:
    """Design (Regeneration): a tree that never held anything is reproduced
    without ``.fitdocs/``.

    Mutation: save the (empty) record at the end of every regeneration.
    """
    data_root = tmp_path / "data"
    data_root.mkdir()
    copy, original = fx.healthfit_copy(), fx.garmin_original()
    _sync_one(data_root, tmp_path, copy)
    _archive(data_root, original)  # an unreferenced file, planned and joined
    assert not (data_root / ".fitdocs").exists()  # precondition

    report = _regen(data_root)

    assert report.failures == ()
    assert _sources(_only_page(data_root)) == [
        _ref(copy),
        _ref(original),
    ]  # precondition: the unreferenced file was planned
    assert not (data_root / ".fitdocs").exists()


def test_a_precedence_change_re_bases_and_renames_at_regeneration(
    tmp_path: Path,
) -> None:
    """Req 7.2: the page lists a shifted-start phone copy and a device original;
    with phone copies first the page keeps the copy as its base and its name;
    with the default precedence the original becomes the base, the page moves
    to the name the original's start computes and its chart follows.

    Mutations: ignore the ``precedence`` keyword (the first regeneration
    already re-bases); skip the rename in the page task (the name stays).
    """
    data_root = tmp_path / "data"
    data_root.mkdir()
    shifted, original = fx.healthfit_shifted(), fx.garmin_original()
    _sync_one(data_root, tmp_path, shifted)
    _archive(data_root, original)
    page = _only_page(data_root)
    _set_sources(page, [_ref(shifted), _ref(original)])
    phone_first = resolve_precedence([PrecedenceEntry(SourceKind.PHONE_COPY)])

    kept = _regen(data_root, phone_first)

    assert kept.failures == ()
    assert _only_page(data_root) == page  # the copy is still the base
    assert _frontmatter(page)["source_kind"] == "phone_copy"

    moved = _regen(data_root)

    assert moved.failures == ()
    new_page = _only_page(data_root)
    assert new_page.name != page.name
    assert _frontmatter(new_page)["source_kind"] == "original"
    assert _frontmatter(new_page)["source_elapsed_s"] == original.elapsed_s
    assert _assets(data_root) == {f"{new_page.stem}-hero.svg"}
    assert len(_rename_warnings(moved)) == 1


def test_two_pages_recording_one_session_uuid_are_each_rebuilt_from_their_own_list(
    tmp_path: Path,
) -> None:
    """Req 4.9, 7.2: regeneration takes each scanned page as it is, so a
    session UUID two pages record never routes one page's files onto the other.

    Fixture: two pages of one UUID (the pair's two exports), each listing one
    file, the second a copy of the other's page under a name that sorts later
    and holding a wrong generated value. Mutation: match each page by its
    session UUID and last source instead of by its own record (the later page
    is never rebuilt and keeps its wrong value).
    """
    older, newer = fx.healthfit_reexport_pair()
    root_a, root_b = tmp_path / "a", tmp_path / "b"
    root_a.mkdir()
    root_b.mkdir()
    _sync_one(root_a, tmp_path / "wa", older)
    _sync_one(root_b, tmp_path / "wb", newer)
    first = _only_page(root_a)
    second = root_a / WORKOUTS_DIR / f"zz-{_only_page(root_b).name}"
    text = _only_page(root_b).read_text(encoding="utf-8")
    assert f"source_elapsed_s: {newer.elapsed_s}" in text  # the line to falsify
    second.write_text(
        text.replace(
            f"source_elapsed_s: {newer.elapsed_s}", "source_elapsed_s: 1.0", 1
        ),
        encoding="utf-8",
    )
    archive_path(root_a, _sha(newer.data)).write_bytes(newer.data)
    assert _frontmatter(first)["uuid"] == _frontmatter(second)["uuid"]  # staged
    assert _frontmatter(second)["source_elapsed_s"] == 1.0
    names = [first.name, second.name]

    report = _regen(root_a)

    assert report.failures == ()
    assert [p.name for p in _pages(root_a)] == sorted(names)
    assert _sources(first) == [_ref(older)]
    assert _sources(second) == [_ref(newer)]
    assert _frontmatter(second)["source_elapsed_s"] == newer.elapsed_s
    assert _frontmatter(first)["source_elapsed_s"] == older.elapsed_s
    assert _rename_warnings(report) == []
    _code, output = _check(root_a)
    assert output.count("the same session as") == 2, output  # both pages report it
    assert "evidence: uuid" in output, output


def test_user_owned_frontmatter_keys_survive_a_base_change_rename(
    tmp_path: Path,
) -> None:
    """Req 6.1, 6.2: a page renamed because its base changed carries its
    user-owned frontmatter keys onto the new name.

    The rename really happens (the page name and the base change). Mutation:
    carry no user-owned lines when the page is renamed.
    """
    data_root = tmp_path / "data"
    data_root.mkdir()
    shifted, original = fx.healthfit_shifted(), fx.garmin_original()
    _sync_one(data_root, tmp_path, shifted)
    _archive(data_root, original)
    page = _only_page(data_root)
    _set_sources(page, [_ref(shifted), _ref(original)])
    phone_first = resolve_precedence([PrecedenceEntry(SourceKind.PHONE_COPY)])
    assert _regen(data_root, phone_first).failures == ()  # the copy is the base
    assert _only_page(data_root) == page
    tag = "effort: race\neffort_distance_m: 42195\neffort_time_s: 10692\n"
    text = page.read_text(encoding="utf-8")
    page.write_text(text.replace("\n---\n", f"\n{tag}---\n", 1), encoding="utf-8")
    assert _frontmatter(page)["effort"] == "race"  # staged

    report = _regen(data_root)

    assert report.failures == ()
    moved = _only_page(data_root)
    assert moved.name != page.name  # the rename happened
    assert len(_rename_warnings(report)) == 1
    front = _frontmatter(moved)
    assert front["source_kind"] == "original"
    assert front["effort"] == "race"
    assert front["effort_distance_m"] == 42195
    assert front["effort_time_s"] == 10692


def test_unreferenced_files_are_planned_against_the_rebuilt_pages(
    tmp_path: Path,
) -> None:
    """Req 4.10, 7.2: a page hand-listed with an off-by-30-s phone copy and the
    device original is rebuilt from the original; the archived partner copy of
    that original (listed by no page) then joins it. Planned against the pages
    as they stood before the rebuild (the copy's values, 30 s from the partner,
    outside the 10 s tolerance) it would match nothing and become a page of its
    own.

    Mutation: plan the unreferenced files before rebuilding the pages.
    """
    data_root = tmp_path / "data"
    data_root.mkdir()
    original, partner = fx.garmin_original(), fx.partner_copy()
    base_copy = fx.healthfit_copy()
    off = replace(
        base_copy,
        data=fx.session_fit_bytes(
            sport="running",
            start=original.start,
            elapsed_s=original.elapsed_s + 30.0,
            timer_s=original.elapsed_s + 30.0,
            distance_m=original.distance_m + 2.0,
            manufacturer="development",
            product=0,
            serial=base_copy.serial,
            time_created=original.start + 4 * 3600,
            device_manufacturer="garmin",
        ),
    )
    _sync_one(data_root, tmp_path, off)
    _archive(data_root, original)
    _archive(data_root, partner)
    _set_sources(_only_page(data_root), [_ref(off), _ref(original)])

    report = _regen(data_root)

    assert report.failures == ()
    page = _only_page(data_root)
    assert set(_sources(page)) == {_ref(off), _ref(original), _ref(partner)}
    assert not (data_root / ".fitdocs").exists()


def test_held_candidates_follow_a_rename_the_regeneration_plan_makes(
    tmp_path: Path,
) -> None:
    """Req 4.10, 4.7: page A (the older HealthFit export) and page B hold a file
    that matches both; the newer export, archived and listed by no page, is
    pinned to A by its session UUID and corrects A's start, so planning renames
    A. The re-written record names A where it ended.

    Mutation: save the record without following the plan's renames.
    """
    older, newer = fx.healthfit_reexport_pair()
    data_root = tmp_path / "data"
    data_root.mkdir()
    _sync_files(tmp_path, data_root, [("a", older.data)])
    _sync_files(tmp_path, data_root, [("b", _garmin_run(elapsed_s=3008.0, serial=12))])
    _sync_files(tmp_path, data_root, [("x", _garmin_run(elapsed_s=3004.0, serial=13))])
    _archive(data_root, newer)
    old_paths = {p.relative_to(data_root).as_posix() for p in _pages(data_root)}
    assert len(old_paths) == 2  # precondition: two pages
    assert len(load_holds(data_root).entries) == 1  # and the file is held

    report = _regen(data_root)

    assert report.failures == ()
    assert len(_rename_warnings(report)) == 1  # precondition: A was renamed
    new_paths = {p.relative_to(data_root).as_posix() for p in _pages(data_root)}
    assert new_paths != old_paths
    (entry,) = load_holds(data_root).entries
    assert set(entry.candidates) == new_paths
    assert len(entry.candidates) == 2


def test_held_candidates_follow_a_rename_the_regeneration_settle_follows(
    tmp_path: Path,
) -> None:
    """Req 4.10, 4.7: page A (the older HealthFit export) and page Y share one
    stem, so Y sits under a suffix; a file matching both is held. The newer
    export, archived and listed by no page, corrects A's start when planned, so
    A leaves the stem and the settle pass moves Y onto it. The re-written
    record names both pages where they ended.

    Mutation: save the record without following the settle's renames.
    """
    older, newer = fx.healthfit_reexport_pair()

    def near(seconds: float, serial: int) -> bytes:
        return fx.session_fit_bytes(
            sport="running",
            start=older.start,
            elapsed_s=older.elapsed_s + seconds,
            timer_s=older.elapsed_s + seconds,
            distance_m=older.distance_m,
            manufacturer="garmin",
            product=3843,
            serial=serial,
            time_created=older.start,
        )

    data_root = tmp_path / "data"
    data_root.mkdir()
    _sync_files(tmp_path, data_root, [("a", older.data)])
    _sync_files(tmp_path, data_root, [("y", near(16.0, 12))])
    _sync_files(tmp_path, data_root, [("x", near(8.0, 13))])
    _archive(data_root, newer)
    old_paths = {p.relative_to(data_root).as_posix() for p in _pages(data_root)}
    assert len(old_paths) == 2  # precondition: two pages
    assert len({Path(path).stem[:15] for path in old_paths}) == 1  # one stem
    assert len(load_holds(data_root).entries) == 1  # and the file is held

    report = _regen(data_root)

    assert report.failures == ()
    reasons = [w.detail for w in _rename_warnings(report)]
    assert any("its base file changed" in r for r in reasons)  # precondition: A
    assert any("became free" in r for r in reasons)  # precondition: Y settled
    new_paths = {p.relative_to(data_root).as_posix() for p in _pages(data_root)}
    (entry,) = load_holds(data_root).entries
    assert set(entry.candidates) == new_paths
    assert len(new_paths) == 2


def _stage_synced_corpus(tmp_path: Path) -> Path:
    """A held file, a joined pair (a ride and its copy) and their charts."""
    data_root, _ambiguous = _stage_held(tmp_path)
    original, copy = _ride_pair()
    report = _sync_files(tmp_path, data_root, [("ride", original), ("copy", copy)])
    assert report.failures == ()
    return data_root


def test_regeneration_reproduces_the_synced_tree_byte_for_byte(tmp_path: Path) -> None:
    """Req 7.3: syncing a corpus with a held file and a joined pair, then
    regenerating, leaves every page, chart and archived file byte for byte as it
    was, and the hold record as it was but for the entry's ``name`` (the path the
    file arrived under, which an archived file no longer has; regeneration
    labels it with its archive ref). A second regeneration changes nothing.

    Mutations: render unreferenced archives fresh without planning (the held
    file becomes a page); skip held files in regeneration (the entry goes).
    """
    data_root = _stage_synced_corpus(tmp_path)
    before = _tree(data_root)
    assert ".fitdocs/held.toml" in before  # precondition: something is held
    assert any(name.endswith(".svg") for name in before)  # and charts exist
    assert len(_pages(data_root)) == 3  # two run pages and the joined ride
    sync_entry = load_holds(data_root).entries[0]

    assert _regen(data_root).failures == ()

    after = _tree(data_root)
    assert {k: v for k, v in after.items() if k != ".fitdocs/held.toml"} == {
        k: v for k, v in before.items() if k != ".fitdocs/held.toml"
    }
    (entry,) = load_holds(data_root).entries
    assert entry == replace(sync_entry, name=source_ref(sync_entry.sha256))

    assert _regen(data_root).failures == ()
    assert _tree(data_root) == after


def test_regeneration_writes_no_archive_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Design (Regeneration): tasks and holds are applied without archive
    writes, since every file planned is already archived; the group path (the
    ride pair) and the hold path are both taken and neither asks for its file
    to be archived (the write-once helper is a no-op on a present file, so the
    call itself is what is observed).

    Mutation: let the planned tasks write their archive.
    """
    data_root = _stage_synced_corpus(tmp_path)
    (ride,) = [p for p in _pages(data_root) if _frontmatter(p)["modality"] == "bike"]
    ride.unlink()  # its two files are now unreferenced: a group task re-makes it
    (entry,) = load_holds(data_root).entries
    planned = {archive_path(data_root, _sha(data)) for data in _ride_pair()}
    planned.add(archive_path(data_root, entry.sha256))
    assert len(planned) == 3
    calls: list[Path] = []
    monkeypatch.setattr(
        sync_module, "_write_archive", lambda archive, data: calls.append(archive)
    )

    report = _regen(data_root)

    assert report.failures == ()
    assert len(_pages(data_root)) == 3  # precondition: the group was re-made
    assert len(load_holds(data_root).entries) == 1  # and the hold re-derived
    # The pages that were not deleted rebuild from their archived base (a
    # no-op write); the unreferenced files are the ones planned.
    assert planned.isdisjoint(calls)
    assert all(archive.exists() for archive in planned)


# --- CLI scenarios (7.2) ---
#
# These drive the real ``fitdocs`` command (typer's runner) over a temp data
# root, so the wiring -- settings, drain, planned sync, ``check``, ``regen`` --
# is what is proved, not the engines alone. Page names are computed, not
# hard-coded: the CLI names a page in the machine's local zone
# (``fitdocs.cli._local_tz``), so each expected stem is ``doc_stem`` of the
# parsed fixture in that same zone -- the suite passes under any ``TZ``.

_CLI = CliRunner()
# Listings are compared sorted: the zone decides whether the ride's stem sorts
# before or after the run's.
_RIDE_START = fx.garmin_original().start + 24 * 3600


def _stem_of(data: bytes) -> str:
    """The stem the CLI gives a page based on ``data``, in its local zone."""
    return doc_stem(real_parse_fit(data), "", cli_module._local_tz(), lambda _s: False)


def _run_stem() -> str:
    return _stem_of(fx.garmin_original().data)


def _shifted_run_stem() -> str:
    return _stem_of(fx.healthfit_shifted().data)


def _ride_stem() -> str:
    return _stem_of(_ride(_RIDE_START)[0])


_RIDE_UUID = tuple(range(60, 76))


@pytest.fixture(autouse=True)
def _cli_environment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """No inherited data root, an explicit cwd, and no network for tiles."""
    monkeypatch.delenv("FITDOCS_DATA", raising=False)
    cwd = tmp_path / "cwd"
    cwd.mkdir(exist_ok=True)
    monkeypatch.chdir(cwd)
    monkeypatch.setattr(
        "fitdocs.tiles._default_fetch", lambda _url: b"\x89PNG\r\n\x1a\n"
    )


def _cli(data_root: Path, *args: str) -> tuple[int, str]:
    """Run ``fitdocs <args> --out <data_root>``; return (exit code, output with
    every run of whitespace collapsed, so the padding of the report's table rows
    and the line breaks between them do not matter to a substring check)."""
    result = _CLI.invoke(app, [*args, "--out", str(data_root)])
    return result.exit_code, " ".join(result.output.split())


def _check(data_root: Path) -> tuple[int, str]:
    """``fitdocs check``, requiring that it wrote nothing (Req 8.5)."""
    before = _tree(data_root)
    result = _cli(data_root, "check")
    assert _tree(data_root) == before
    return result


def _workouts_tree(data_root: Path) -> dict[str, bytes]:
    return {
        path: data
        for path, data in _tree(data_root).items()
        if path.startswith(f"{WORKOUTS_DIR}/") and not path.endswith("AGENTS.md")
    }


def _cli_root(tmp_path: Path) -> Path:
    data_root = tmp_path / "data"
    data_root.mkdir(parents=True)
    (data_root / "fitdocs.toml").write_text(
        "[inbox]\nsettle_seconds = 0\n", encoding="utf-8"
    )
    return data_root


def _cli_sync_dir(tmp_path: Path, data_root: Path, *blobs: bytes) -> str:
    """``fitdocs sync <fresh dir holding blobs>``; require exit 0."""
    source = tmp_path / f"cli-src-{len(list(tmp_path.glob('cli-src-*')))}"
    source.mkdir()
    for position, data in enumerate(blobs):
        (source / f"{position}.fit").write_bytes(data)
    code, output = _cli(data_root, "sync", str(source))
    assert code == 0, output
    return output


def _ride(start: int) -> tuple[bytes, bytes]:
    """(Garmin original, HealthFit copy) of a ride at ``start``."""
    original = fx.session_fit_bytes(
        sport="cycling",
        start=start,
        elapsed_s=3000.0,
        timer_s=2900.0,
        distance_m=30_000.0,
        manufacturer="garmin",
        product=3843,
        serial=fx.garmin_original().serial + 5,
        time_created=start,
        undocumented=fx.UNDOCUMENTED_COUNT,
    )
    copy = fx.session_fit_bytes(
        sport="cycling",
        start=start,
        elapsed_s=3000.5,
        timer_s=3000.5,
        distance_m=30_002.0,
        manufacturer="development",
        product=0,
        serial=fx.healthfit_copy().serial,
        time_created=start + 4 * 3600,
        session_uuid=_RIDE_UUID,
        device_manufacturer="garmin",
    )
    return original, copy


def _page_names(data_root: Path) -> list[str]:
    return [p.name for p in _pages(data_root)]


def _asset_names(data_root: Path) -> list[str]:
    return sorted(p.name for p in (data_root / WORKOUTS_DIR / "assets").iterdir())


def _stage_cli_corpus(tmp_path: Path) -> tuple[Path, fx.Species, bytes, bytes]:
    """A data root of two HealthFit-style pages, the run's shifted two hours,
    each synced alone through the CLI; the originals wait in the inbox.

    Returns (data_root, the shifted run copy, ride original, ride copy).
    """
    data_root = _cli_root(tmp_path)
    shifted = fx.healthfit_shifted()
    ride_original, ride_copy = _ride(_RIDE_START)
    _cli_sync_dir(tmp_path, data_root, shifted.data)
    _cli_sync_dir(tmp_path, data_root, ride_copy)
    inbox = data_root / "inbox"
    inbox.mkdir()
    (inbox / "run.fit").write_bytes(fx.garmin_original().data)
    (inbox / "ride.fit").write_bytes(ride_original)
    return data_root, shifted, ride_original, ride_copy


def _drain_cli_corpus(tmp_path: Path) -> tuple[Path, str, dict[str, object]]:
    """Stage the corpus, drain the inbox with ``fitdocs sync`` (no source),
    return (data_root, the sync output, each page's frontmatter before)."""
    data_root, shifted, ride_original, ride_copy = _stage_cli_corpus(tmp_path)
    # Preconditions: the pages sit at the shifted name and the ride's; the
    # originals are in the inbox and in no page yet.
    assert _page_names(data_root) == sorted(
        [f"{_shifted_run_stem()}.md", f"{_ride_stem()}.md"]
    )
    assert _asset_names(data_root) == sorted(
        [
            f"{_shifted_run_stem()}-hero.svg",
            f"{_ride_stem()}-hero.svg",
        ]
    )
    assert sorted(p.name for p in (data_root / "inbox").iterdir()) == [
        "ride.fit",
        "run.fit",
    ]
    before = {page.name: _frontmatter(page)["sources"] for page in _pages(data_root)}
    assert before == {
        f"{_shifted_run_stem()}.md": [_ref(shifted)],
        f"{_ride_stem()}.md": [_ref_of(ride_copy)],
    }
    code, output = _cli(data_root, "sync")
    assert code == 0, output
    return data_root, output, dict(before)


def test_cli_drain_joins_originals_renames_the_shifted_page_and_check_is_clean(
    tmp_path: Path,
) -> None:
    """Req 3.4, 4.3, 5.1, 5.2, 5.5, 6.2, 6.4, 6.5, 7.1, 7.2, 7.3, 8.5: HealthFit
    pages (the run's shifted two hours) gain the Garmin originals through
    ``fitdocs sync`` from the inbox -- one page per session, the shifted page
    renamed to the original's start, its old chart gone, both copies' UUIDs
    kept, ``fitdocs check`` clean and writing nothing, and ``fitdocs regen``
    then reproducing the tree byte for byte.

    Mutations: disable the shifted tier in matching (the shifted run gets a
    second page: the page list reds); skip the rename (the run page keeps the
    shifted-start name); drop UUID retention by giving the page identity no
    session UUID (the ``uuid`` key is omitted: ``KeyError: 'uuid'``); ignoring
    only the page's own recorded UUID survives here, since the copies (extras)
    still carry it -- the engine suite owns that path; leave the old assets
    behind (the asset list reds); reverse the precedence in regeneration's page
    loop (the regen tree comparison reds).
    """
    data_root, output, _ = _drain_cli_corpus(tmp_path)
    ride_original, _ = _ride(_RIDE_START)
    shifted = fx.healthfit_shifted()
    original = fx.garmin_original()

    assert _page_names(data_root) == sorted([f"{_run_stem()}.md", f"{_ride_stem()}.md"])
    assert not (data_root / WORKOUTS_DIR / f"{_shifted_run_stem()}.md").exists()
    assert _asset_names(data_root) == sorted(
        [
            f"{_run_stem()}-hero.svg",
            f"{_ride_stem()}-hero.svg",
        ]
    )
    run_page = _frontmatter(data_root / WORKOUTS_DIR / f"{_run_stem()}.md")
    ride_page = _frontmatter(data_root / WORKOUTS_DIR / f"{_ride_stem()}.md")
    ride_copy = _ride(_RIDE_START)[1]
    run_path = data_root / WORKOUTS_DIR / f"{_run_stem()}.md"
    ride_path = data_root / WORKOUTS_DIR / f"{_ride_stem()}.md"
    # Ascending rank, the base (the Garmin original) last.
    assert _sources(run_path) == [_ref(shifted), _ref(original)]
    assert _sources(ride_path) == [_ref_of(ride_copy), _ref_of(ride_original)]
    assert run_page["source_kind"] == "original"
    assert ride_page["source_kind"] == "original"
    assert run_page["uuid"] == _uuid_text(shifted)
    assert ride_page["uuid"] == format_session_uuid(_RIDE_UUID)
    assert f"{_shifted_run_stem()}.md to workouts/{_run_stem()}.md" in output
    assert len(list((data_root / "fit-archive").glob("*.fit"))) == 4

    code, checked = _check(data_root)

    assert code == 0, checked
    assert "Findings │ 0 │" in checked
    assert "No findings" in checked

    settled = _tree(data_root)
    code, regenerated = _cli(data_root, "regen")

    assert code == 0, regenerated
    assert _tree(data_root) == settled


def test_cli_partner_copy_arriving_later_changes_nothing_but_sources(
    tmp_path: Path,
) -> None:
    """Req 2.8, 4.3, 5.6, 8.5: the Garmin original's partner copy (same ``file_id``, no
    undocumented messages) synced afterwards joins the run page and changes
    nothing but its ``sources`` list and one more row in the page's Channel
    Sources section (between the base's row and the copy's) -- every other
    byte of the page, the page name and the charts are as they were, and
    ``check`` stays clean.

    Mutations: rank the phone copy above a Garmin original in the default
    precedence (this test and the drain scenario red); prefer the file with
    fewer undocumented messages (the partner becomes the base: the ``sources``
    order reds).
    """
    data_root, _, _ = _drain_cli_corpus(tmp_path)
    run_path = data_root / WORKOUTS_DIR / f"{_run_stem()}.md"
    other_path = data_root / WORKOUTS_DIR / f"{_ride_stem()}.md"
    before = _tree(data_root)
    partner = fx.partner_copy()
    assert _sha(partner.data) not in {
        p.stem for p in (data_root / "fit-archive").glob("*.fit")
    }

    output = _cli_sync_dir(tmp_path, data_root, partner.data)

    after = _tree(data_root)
    assert "Written │ 1 │" in output
    assert _page_names(data_root) == sorted([f"{_run_stem()}.md", f"{_ride_stem()}.md"])
    new_files = set(after) - set(before)
    assert new_files == {f"fit-archive/{_sha(partner.data)}.fit"}
    changed = {path for path in before if after[path] != before[path]}
    assert changed == {f"{WORKOUTS_DIR}/{_run_stem()}.md"}
    old_text = before[f"{WORKOUTS_DIR}/{_run_stem()}.md"].decode("utf-8")
    new_text = after[f"{WORKOUTS_DIR}/{_run_stem()}.md"].decode("utf-8")
    assert _SOURCES_BLOCK.subn("", old_text)[1] == 1
    # The partner is one more extra: the section gains exactly its row, between
    # the base's row and the copy's, and every other line of it is unchanged.
    assert _channel_source_refs(new_text) == list(reversed(_sources(run_path)))
    assert len(_channel_source_refs(old_text)) == 2
    old_lines = _channel_sources_lines(old_text)
    new_lines = _channel_sources_lines(new_text)
    partner_rows = [line for line in new_lines if _ref(partner) in line]
    assert len(partner_rows) == 1
    assert new_lines.index(partner_rows[0]) == 1 + next(
        i for i, line in enumerate(new_lines) if line.startswith("| `fit-archive")
    )
    assert [line for line in new_lines if line != partner_rows[0]] == old_lines
    assert _SOURCES_BLOCK.sub(
        "", _without_channel_sources(new_text)
    ) == _SOURCES_BLOCK.sub("", _without_channel_sources(old_text))
    shifted, original = fx.healthfit_shifted(), fx.garmin_original()
    old_front = yaml.safe_load(old_text.split("---\n", 2)[1])
    assert old_front["sources"] == [_ref(shifted), _ref(original)]
    # Ascending rank, the base last: the partner ranks above the copy and below
    # the original (fewer undocumented messages), which stays the base.
    assert _sources(run_path) == [_ref(shifted), _ref(partner), _ref(original)]
    assert other_path.read_bytes() == before[f"{WORKOUTS_DIR}/{_ride_stem()}.md"]
    code, checked = _check(data_root)
    assert code == 0, checked
    assert "Findings │ 0 │" in checked


def test_cli_the_two_ten_k_runs_stay_two_pages(tmp_path: Path) -> None:
    """Req 3.5, 4.4, 8.5: two different 10 k runs a day and 17 minutes apart, synced
    in one CLI run, are two pages with one file each -- and stay two when synced
    again -- and ``check`` finds nothing.

    Mutation: widen the start, elapsed and distance tolerances until the pair
    reads as one session (one page holding both files).
    """
    data_root = _cli_root(tmp_path)
    first, second = fx.ten_k_pair()

    _cli_sync_dir(tmp_path, data_root, first.data, second.data)

    assert len(_pages(data_root)) == 2
    assert sorted(len(_sources(p)) for p in _pages(data_root)) == [1, 1]
    assert sorted(ref for p in _pages(data_root) for ref in _sources(p)) == sorted(
        [_ref(first), _ref(second)]
    )
    before = _tree(data_root)
    _cli_sync_dir(tmp_path, data_root, first.data, second.data)
    assert _tree(data_root) == before
    code, checked = _check(data_root)
    assert code == 0, checked
    assert "Findings │ 0 │" in checked


def test_cli_an_ambiguous_file_is_reported_checked_and_resolved_by_regen(
    tmp_path: Path,
) -> None:
    """Req 4.5, 4.7, 4.10, 6.6, 7.5, 8.1, 8.5: a file matching two pages is named,
    with both candidate pages, in the sync report; ``fitdocs check`` reports the
    held file (its subject and the keep-one-delete-one remedy) and exits 1;
    after the duplicate page is deleted ``fitdocs regen`` joins the file, the
    hold record is empty and ``check`` is clean. The held file is counted
    skipped, never failed, and ``check`` writes nothing.

    Mutations: skip the hold warning in the report (the sync output loses the
    candidates); ``check`` dropping ambiguous findings (exit 0 and no subject);
    ``regen`` skipping held files (the file stays out of the page and the hold
    stays); ``regen`` merging with the old record (the entry stays).
    """
    data_root = _cli_root(tmp_path)
    _cli_sync_dir(tmp_path, data_root, _garmin_run(elapsed_s=3000.0, serial=11))
    _cli_sync_dir(tmp_path, data_root, _garmin_run(elapsed_s=3016.0, serial=12))
    pages = _page_names(data_root)
    assert len(pages) == 2  # precondition: two separate pages
    unsuffixed = f"{_run_stem()}.md"  # freed below
    assert unsuffixed in pages
    (suffixed,) = [name for name in pages if name != unsuffixed]
    assert suffixed.startswith(f"{_run_stem()}-")  # the collision-suffixed one
    ambiguous = _garmin_run(elapsed_s=3008.0, serial=13)
    archived = f"fit-archive/{_sha(ambiguous)}.fit"
    assert not (data_root / archived).exists()

    output = _cli_sync_dir(tmp_path, data_root, ambiguous)

    assert _page_names(data_root) == pages  # nothing merged, nothing new
    assert (data_root / archived).is_file()
    assert f"{archived} held, not merged" in output
    assert "Skipped │ 1 │" in output
    assert "Failed │ 0 │" in output
    for page in pages:
        assert f"workouts/{page}" in output
    assert len(load_holds(data_root).entries) == 1

    code, checked = _check(data_root)

    assert code == 1, checked
    assert f"{archived} held " in checked
    assert "could be a page of" in checked
    for page in pages:
        assert f"workouts/{page}" in checked
    assert "delete the other, and run `fitdocs regen`" in checked

    (data_root / WORKOUTS_DIR / unsuffixed).unlink()
    code, regenerated = _cli(data_root, "regen")

    assert code == 0, regenerated
    assert _page_names(data_root) == sorted([unsuffixed])  # settled onto the freed name
    assert len(_sources(_only_page(data_root))) == 3
    assert _ref_of(ambiguous) in _sources(_only_page(data_root))
    assert load_holds(data_root).entries == ()
    assert "[[held]]" not in _held_text(data_root)
    code, checked = _check(data_root)
    assert code == 0, checked
    assert "Findings │ 0 │" in checked


def test_cli_the_four_files_in_any_arrival_give_the_incremental_workouts_tree(
    tmp_path: Path,
) -> None:
    """Req 4.8, 5.7: the run's four files (Garmin run and ride originals, the
    shifted run copy, the ride copy) synced all at once, in reverse order, or
    drained from an inbox whose names sort in reverse, give a ``workouts/`` tree
    byte-identical to the one the incremental staging gave.

    Mutations run: disable the shifted tier, an asymmetric shifted tier (only
    the first file of a pair may be the phone copy), leave stale assets behind
    -- each reds this test, but each also reds the incremental staging that
    feeds it, so none isolates arrival order. No rank tie exists in these
    fixtures, so dropping the final content-hash key of the rank survives; the
    arrival-order property is owned by the engine suites above.
    """
    incremental_root, _, _ = _drain_cli_corpus(tmp_path / "incremental")
    expected = _workouts_tree(incremental_root)
    assert len(expected) == 4  # two pages and their two charts
    ride_original, ride_copy = _ride(_RIDE_START)
    files = [
        fx.garmin_original().data,
        ride_original,
        fx.healthfit_shifted().data,
        ride_copy,
    ]

    forward = _cli_root(tmp_path / "forward")
    _cli_sync_dir(tmp_path / "forward", forward, *files)
    backward = _cli_root(tmp_path / "backward")
    _cli_sync_dir(tmp_path / "backward", backward, *reversed(files))
    drained = _cli_root(tmp_path / "drained")
    (drained / "inbox").mkdir()
    for position, data in enumerate(files):
        (drained / "inbox" / f"{9 - position}.fit").write_bytes(data)
    assert sorted(p.name for p in (drained / "inbox").iterdir())[0] == "6.fit"
    code, output = _cli(drained, "sync")
    assert code == 0, output

    assert _workouts_tree(forward) == expected
    assert _workouts_tree(backward) == expected
    assert _workouts_tree(drained) == expected
