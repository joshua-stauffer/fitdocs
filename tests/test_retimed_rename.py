"""A page fitdocs named follows a changed local start (activity-identity Req 6.9).

Pages are written by the sync engine under one zone and regenerated under
another, which moves every page's computed local start the way the local-time
fix (workout-docs Amendment 6) does for pages written before it. A page whose
filename is the name fitdocs computed from the start its frontmatter records
moves to the new name like a base-change rename: one page, its charts renamed
with it and the old ones removed, a rename warning. A filename the user chose
stays (Req 6.3). Two pages of one local minute move without sharing a chart,
and a second regeneration changes nothing.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import timedelta, timezone
from pathlib import Path

from fitdocs.docmerge import begin_marker, end_marker
from fitdocs.render import TileRef
from fitdocs.sync import SyncReport, regen, sync
from tests.fixtures import builder
from tests.fixtures import identity as fx

_EAST = timezone(timedelta(hours=2))
_WEST = timezone(timedelta(hours=-5))
# The fixtures start at 2021-09-08 01:46:40 UTC.
_OLD = "2021-09-08-run-0346"
_NEW = "2021-09-07-run-2046"


class _NoTiles:
    """The fixtures record no position, so no tile is ever requested."""

    attribution = "test"

    def resolve(self, refs: Sequence[TileRef]) -> dict[TileRef, bytes]:
        assert not refs
        return {}


def _sync(tmp_path: Path, *files: bytes) -> Path:
    data_root = tmp_path / "data"
    source = tmp_path / "source"
    data_root.mkdir()
    source.mkdir()
    for index, data in enumerate(files):
        (source / f"{index}.fit").write_bytes(data)
    report = sync(source, data_root, athlete=None, tz=_EAST, tiles=_NoTiles())
    assert report.failures == ()
    return data_root


def _regen(data_root: Path) -> SyncReport:
    report = regen(data_root, athlete=None, tz=_WEST, tiles=_NoTiles())
    assert report.failures == ()
    return report


def _files(data_root: Path) -> set[str]:
    workouts = data_root / "workouts"
    return {
        path.relative_to(workouts).as_posix()
        for path in workouts.rglob("*")
        if path.is_file() and path.name != "AGENTS.md"
    }


def _links(page: Path) -> set[str]:
    return set(re.findall(r"\]\((assets/[^)]+\.svg)\)", page.read_text()))


def _run() -> bytes:
    return builder.encode(builder.run_no_gps_mesgs())


def _same_minute_run() -> bytes:
    start = builder.FIT_TIMESTAMP_BASE
    return fx.session_fit_bytes(
        sport="running",
        start=start,
        elapsed_s=3000.0,
        timer_s=3000.0,
        distance_m=8000.0,
        manufacturer="garmin",
        product=1,
        serial=4200000401,
        time_created=start,
    )


def test_regen_moves_a_fitdocs_named_page_and_its_charts(tmp_path: Path) -> None:
    data_root = _sync(tmp_path, _run())
    assert _files(data_root) == {f"{_OLD}.md", f"assets/{_OLD}-hero.svg"}

    report = _regen(data_root)

    assert _files(data_root) == {f"{_NEW}.md", f"assets/{_NEW}-hero.svg"}
    assert [(w.doc, w.detail) for w in report.warnings] == [
        (
            f"workouts/{_NEW}.md",
            f"page renamed from workouts/{_OLD}.md to workouts/{_NEW}.md because "
            "its local start time changed; wiki links to the old name and plan "
            "overrides naming the old stem need updating",
        )
    ]
    text = (data_root / "workouts" / f"{_NEW}.md").read_text()
    assert "start_time: '2021-09-07T20:46:40-05:00'" in text


def test_a_filename_the_user_chose_stays(tmp_path: Path) -> None:
    data_root = _sync(tmp_path, _run())
    workouts = data_root / "workouts"
    (workouts / f"{_OLD}.md").rename(workouts / "long-run.md")

    report = _regen(data_root)

    assert sorted(p.name for p in workouts.glob("*.md") if p.name != "AGENTS.md") == [
        "long-run.md"
    ]
    assert report.warnings == ()
    assert (
        "start_time: '2021-09-07T20:46:40-05:00'"
        in (workouts / "long-run.md").read_text()
    )


def test_a_chart_the_notes_link_survives_the_move(tmp_path: Path) -> None:
    data_root = _sync(tmp_path, _run())
    page = data_root / "workouts" / f"{_OLD}.md"
    note = f"![kept](assets/{_OLD}-hero.svg)"
    text = page.read_text()
    begin, end = begin_marker("notes"), end_marker("notes")
    head, rest = text.split(begin, 1)
    page.write_text(f"{head}{begin}\n{note}\n{end}{rest.split(end, 1)[1]}")

    _regen(data_root)

    moved = data_root / "workouts" / f"{_NEW}.md"
    assert note in moved.read_text()
    assert _files(data_root) == {
        f"{_NEW}.md",
        f"assets/{_NEW}-hero.svg",
        f"assets/{_OLD}-hero.svg",
    }


def test_two_pages_of_one_minute_move_without_sharing_a_chart(
    tmp_path: Path,
) -> None:
    data_root = _sync(tmp_path, _run(), _same_minute_run())
    pages = sorted((data_root / "workouts").glob(f"{_OLD}*.md"))
    assert [p.stem[: len(_OLD)] for p in pages] == [_OLD, _OLD]

    _regen(data_root)

    moved = sorted((data_root / "workouts").glob("*.md"))
    moved = [p for p in moved if p.name != "AGENTS.md"]
    assert [p.stem[: len(_NEW)] for p in moved] == [_NEW, _NEW]
    links = [_links(p) for p in moved]
    assert all(
        link.startswith(f"assets/{p.stem}-")
        for p, ls in zip(moved, links, strict=True)
        for link in ls
    )
    assert links[0].isdisjoint(links[1])
    linked = links[0] | links[1]
    assert {f for f in _files(data_root) if f.startswith("assets/")} == linked


def test_a_second_regen_changes_nothing(tmp_path: Path) -> None:
    data_root = _sync(tmp_path, _run(), _same_minute_run())
    _regen(data_root)
    before = {f: (data_root / "workouts" / f).read_bytes() for f in _files(data_root)}

    report = _regen(data_root)

    assert report.warnings == ()
    assert {
        f: (data_root / "workouts" / f).read_bytes() for f in _files(data_root)
    } == before


def test_an_unchanged_local_start_renames_nothing(tmp_path: Path) -> None:
    data_root = _sync(tmp_path, _run())

    report = regen(data_root, athlete=None, tz=_EAST, tiles=_NoTiles())

    assert report.warnings == ()
    assert _files(data_root) == {f"{_OLD}.md", f"assets/{_OLD}-hero.svg"}
