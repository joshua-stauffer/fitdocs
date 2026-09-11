"""Tests for the one filesystem read of the `history` package (load-history
spec, task 3.1; Req 1.1, 1.2, 1.3, 1.4, 1.9, 3.9, 5.4). See the "DocumentScan
(`src/fitdocs/history/documents.py`)" component in
`.kiro/specs/load-history/design.md`.

Every fixture here is a synthetically written page tree under `tmp_path`,
built from real frontmatter fences and real `fitdocs.contract` vocabulary --
none of it is a hand-rolled format that only a private parser in this test
module would recognize; every fixture is read by the actual
`fitdocs.docio.read_frontmatter` / `fitdocs.contract` readers `scan_documents`
itself calls. No `.fit` file is read and no real wiki page is ever used.
"""

from __future__ import annotations

import dataclasses
import os
from pathlib import Path

import pytest

from fitdocs.contract import EffortTag
from fitdocs.history.documents import (
    DocumentScan,
    PageRecord,
    SkippedPage,
    scan_documents,
)
from fitdocs.layout import WORKOUTS_DIR


def _write(root: Path, relpath: str, text: str) -> Path:
    path = root / relpath
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _page(
    *,
    workout: bool = True,
    date: str | None = "2024-06-01",
    load_lines: str = "",
    tag_lines: str = "",
) -> str:
    """A minimal, syntactically valid fitdocs document, real frontmatter fence
    and real vocabulary -- every field the actual contract readers recognize."""
    lines = ["---", "title: Test Workout"]
    if workout:
        lines.append("type: workout")
    if date is not None:
        lines.append(f'date: "{date}"')
    if load_lines:
        lines.append(load_lines)
    if tag_lines:
        lines.append(tag_lines)
    lines.append("---")
    lines.append("")
    lines.append("# Test Workout")
    lines.append("")
    return "\n".join(lines) + "\n"


# --- basic shape -------------------------------------------------------------


def test_missing_workouts_directory_yields_an_empty_scan(tmp_path: Path) -> None:
    scan = scan_documents(tmp_path)
    assert scan == DocumentScan(pages=(), skipped=())


# --- scored / unscored pages (Req 1.3, 1.4) -----------------------------------


def test_a_scored_page_records_its_load_and_methodology(tmp_path: Path) -> None:
    _write(
        tmp_path,
        f"{WORKOUTS_DIR}/scored.md",
        _page(load_lines="load_value: 42.5\nload_methodology: banister"),
    )

    scan = scan_documents(tmp_path)

    assert len(scan.pages) == 1
    page = scan.pages[0]
    assert page.load == 42.5
    assert page.methodology == "banister"


def test_an_unscored_page_records_no_load_never_a_zero(tmp_path: Path) -> None:
    _write(tmp_path, f"{WORKOUTS_DIR}/unscored.md", _page())

    scan = scan_documents(tmp_path)

    assert len(scan.pages) == 1
    page = scan.pages[0]
    assert page.load is None
    assert page.methodology is None


def test_a_load_value_with_no_methodology_is_dropped_entirely(tmp_path: Path) -> None:
    """design.md's stated postcondition is `load is None` iff `methodology is
    None`: a hand-edited page carrying `load_value` with no
    `load_methodology` at all must not surface a load with no methodology --
    `SeriesAssembly` would then sum it under whichever methodology is chosen
    (Req 4.1). Named mutation: reverting `_read_load` to return
    `(load, None)` when `load_methodology` is absent turns `page.load` into
    `7.0` and reds this assertion."""
    _write(
        tmp_path, f"{WORKOUTS_DIR}/orphan-load.md", _page(load_lines="load_value: 7.0")
    )

    scan = scan_documents(tmp_path)

    assert len(scan.pages) == 1
    page = scan.pages[0]
    assert page.load is None
    assert page.methodology is None


def test_a_non_string_methodology_drops_the_load_too(tmp_path: Path) -> None:
    """A `load_methodology` that parsed as an `int` (unquoted YAML) is not a
    genuine methodology id; per the same postcondition, the load it would
    otherwise carry must be dropped with it. Named mutation: coercing with
    `str(methodology_value)` instead of rejecting a non-`str` would turn this
    into `methodology == "123"` with `load == 7.0` -- both assertions red."""
    _write(
        tmp_path,
        f"{WORKOUTS_DIR}/numeric-methodology.md",
        _page(load_lines="load_value: 7.0\nload_methodology: 123"),
    )

    scan = scan_documents(tmp_path)

    assert len(scan.pages) == 1
    page = scan.pages[0]
    assert page.load is None
    assert page.methodology is None


def test_a_non_finite_load_value_is_dropped(tmp_path: Path) -> None:
    """`.inf` and `.nan` load values are real Python `float`s but never a
    usable load (Req 1.4); the `.nan` fixture pairs a `load_methodology`
    alongside it so this also exercises "methodology unset whenever load is
    unset" on a *present* methodology, not merely an absent one. Named
    mutation: deleting the `math.isfinite` check in `_read_load` leaves
    `page.load == math.inf` / `math.isnan(page.load)` and reds these
    assertions."""
    _write(
        tmp_path,
        f"{WORKOUTS_DIR}/inf-load.md",
        _page(load_lines="load_value: .inf"),
    )
    _write(
        tmp_path,
        f"{WORKOUTS_DIR}/nan-load.md",
        _page(load_lines="load_value: .nan\nload_methodology: banister"),
    )

    scan = scan_documents(tmp_path)

    assert len(scan.pages) == 2
    for page in scan.pages:
        assert page.load is None, f"{page.path} scored a non-finite load"
        assert page.methodology is None


def test_an_overflowing_load_value_is_dropped_without_raising(tmp_path: Path) -> None:
    """A YAML integer literal with 400+ digits parses to a real Python `int`
    (Python ints are arbitrary precision) but overflows `float()` with an
    `OverflowError`. Named mutation: deleting the `except OverflowError`
    guard in `_read_load` makes `scan_documents` raise instead of returning a
    scan, which this test would catch as an unhandled exception."""
    huge_digits = "9" * 400
    _write(
        tmp_path,
        f"{WORKOUTS_DIR}/overflow-load.md",
        _page(load_lines=f"load_value: {huge_digits}"),
    )

    scan = scan_documents(tmp_path)

    assert len(scan.pages) == 1
    page = scan.pages[0]
    assert page.load is None
    assert page.methodology is None


def test_a_string_load_value_is_not_a_load(tmp_path: Path) -> None:
    """Named mutation target: a naive `float(value)` would coerce the
    string `"42.5"` to a real load. `_read_load` must reject it outright
    because it is not an `int`/`float` in the first place."""
    _write(
        tmp_path,
        f"{WORKOUTS_DIR}/string-load.md",
        _page(load_lines='load_value: "42.5"\nload_methodology: banister'),
    )

    scan = scan_documents(tmp_path)

    assert len(scan.pages) == 1
    page = scan.pages[0]
    assert page.load is None
    assert page.methodology is None


def test_a_boolean_load_value_is_not_a_load(tmp_path: Path) -> None:
    """Named mutation: accepting `bool` as numeric (deleting the
    `isinstance(value, bool)` guard in `_read_load`) would score this page
    at `1.0`. Pins Req 1.4 against Python's `bool`-subclasses-`int` trap."""
    _write(
        tmp_path,
        f"{WORKOUTS_DIR}/bool-load.md",
        _page(load_lines="load_value: true\nload_methodology: banister"),
    )

    scan = scan_documents(tmp_path)

    assert len(scan.pages) == 1
    page = scan.pages[0]
    assert page.load is None, (
        "a boolean load_value scored the page -- the bool guard was bypassed"
    )
    assert page.methodology is None


# --- dates (Req 1.2, 1.9) ------------------------------------------------------


def test_a_page_with_no_date_is_skipped_and_named(tmp_path: Path) -> None:
    _write(tmp_path, f"{WORKOUTS_DIR}/no-date.md", _page(date=None))

    scan = scan_documents(tmp_path)

    assert scan.pages == ()
    assert len(scan.skipped) == 1
    skipped = scan.skipped[0]
    assert skipped.path == f"{WORKOUTS_DIR}/no-date.md"
    assert skipped.reason


def test_skipped_pages_are_sorted_by_path_not_by_filesystem_order(
    tmp_path: Path,
) -> None:
    """`zz-undated.md` is written before `aa-undated.md`; `scan_documents`
    already iterates a sorted glob, so both `aa` and `zz` are appended to
    `skipped` in ascending path order regardless of write order -- this
    fixture pins the *output* order, not a claim about write order mattering.
    Named mutation: replacing `skipped.sort(key=lambda s: s.path)` with
    `tuple(reversed(skipped))` reverses the already-ascending append order to
    `[zz, aa]` and reds this assertion."""
    _write(tmp_path, f"{WORKOUTS_DIR}/zz-undated.md", _page(date=None))
    _write(tmp_path, f"{WORKOUTS_DIR}/aa-undated.md", _page(date=None))

    scan = scan_documents(tmp_path)

    assert [s.path for s in scan.skipped] == [
        f"{WORKOUTS_DIR}/aa-undated.md",
        f"{WORKOUTS_DIR}/zz-undated.md",
    ]


# --- non-workout / foreign files (silently excluded) --------------------------


def test_a_non_workout_markdown_file_is_neither_a_page_nor_a_skip(
    tmp_path: Path,
) -> None:
    _write(tmp_path, f"{WORKOUTS_DIR}/not-a-workout.md", _page(workout=False))

    scan = scan_documents(tmp_path)

    assert scan == DocumentScan(pages=(), skipped=())


# --- filesystem shape: no descent, no symlink following (Req 1.1) -------------


def test_a_nested_subdirectory_is_never_descended_into(tmp_path: Path) -> None:
    """A real, scoreable workout page sits one directory down. If the scan
    ever switched from `glob` to `rglob`, this page would appear -- the
    fixture only discriminates because the nested page is itself valid."""
    _write(
        tmp_path,
        f"{WORKOUTS_DIR}/nested/buried.md",
        _page(load_lines="load_value: 99.0\nload_methodology: banister"),
    )
    _write(
        tmp_path,
        f"{WORKOUTS_DIR}/top-level.md",
        _page(load_lines="load_value: 10.0\nload_methodology: banister"),
    )

    scan = scan_documents(tmp_path)

    assert [page.path for page in scan.pages] == [f"{WORKOUTS_DIR}/top-level.md"]
    assert scan.skipped == ()


def test_a_symlink_is_neither_a_page_nor_a_skip(tmp_path: Path) -> None:
    """The target is a genuine, scoreable workout page so this fixture only
    discriminates a real bypass: if `scan_documents` ever read the file
    directly (`path.read_text()` + `contract.parse_frontmatter`) instead of
    going through `docio.read_frontmatter`, the symlink's refusal would
    never fire and this page would show up."""
    target = _write(
        tmp_path,
        f"{WORKOUTS_DIR}/real.md",
        _page(load_lines="load_value: 5.0\nload_methodology: banister"),
    )
    link_path = tmp_path / WORKOUTS_DIR / "linked.md"
    if os.name == "nt":  # pragma: no cover - platform guard, not under test
        pytest.skip("symlinks require elevated privileges on this platform")
    link_path.symlink_to(target)

    scan = scan_documents(tmp_path)

    assert [page.path for page in scan.pages] == [f"{WORKOUTS_DIR}/real.md"]
    assert scan.skipped == ()


# --- effort tags (Req 3.9, 5.4) ------------------------------------------------


def test_a_valid_race_tag_is_recorded_with_no_problem(tmp_path: Path) -> None:
    _write(
        tmp_path,
        f"{WORKOUTS_DIR}/race.md",
        _page(tag_lines=("effort: race\neffort_distance_m: 5000\neffort_time_s: 1200")),
    )

    scan = scan_documents(tmp_path)

    assert len(scan.pages) == 1
    page = scan.pages[0]
    assert page.effort == EffortTag(
        kind="race", distance_m=5000.0, time_s=1200.0, event=None
    )
    assert page.tag_problem is None


def test_a_valid_test_tag_with_a_time_is_recorded(tmp_path: Path) -> None:
    _write(
        tmp_path,
        f"{WORKOUTS_DIR}/test-effort.md",
        _page(tag_lines="effort: test\neffort_time_s: 600"),
    )

    scan = scan_documents(tmp_path)

    assert len(scan.pages) == 1
    page = scan.pages[0]
    assert page.effort == EffortTag(
        kind="test", distance_m=None, time_s=600.0, event=None
    )
    assert page.tag_problem is None


def test_a_hard_tag_is_recorded(tmp_path: Path) -> None:
    _write(tmp_path, f"{WORKOUTS_DIR}/hard.md", _page(tag_lines="effort: hard"))

    scan = scan_documents(tmp_path)

    assert len(scan.pages) == 1
    page = scan.pages[0]
    assert page.effort == EffortTag(
        kind="hard", distance_m=None, time_s=None, event=None
    )
    assert page.tag_problem is None


def test_a_malformed_tag_is_reported_but_the_load_is_still_counted(
    tmp_path: Path,
) -> None:
    """Named mutation: treating `InvalidEffortTag` as `None` (dropping the
    `isinstance(tag, InvalidEffortTag)` branch in `_read_effort`) would make
    this page silently look untagged -- `tag_problem` would read `None` and
    the malformed tag would carry no marker at all, which Req 3.9 forbids."""
    _write(
        tmp_path,
        f"{WORKOUTS_DIR}/malformed.md",
        _page(
            load_lines="load_value: 30.0\nload_methodology: banister",
            tag_lines="effort: bogus",
        ),
    )

    scan = scan_documents(tmp_path)

    assert len(scan.pages) == 1
    page = scan.pages[0]
    assert page.effort is None, "a malformed tag must place no marker"
    assert page.tag_problem, "a malformed tag's own description must be recorded"
    assert "bogus" in page.tag_problem
    assert page.load == 30.0, "a malformed tag must not withhold the page's load"


# --- ordering (Req 1.9, 5.4; design.md postcondition) --------------------------


def test_pages_are_sorted_by_day_then_path_not_by_path_alone(
    tmp_path: Path,
) -> None:
    """Three pages whose path order and day order disagree: `zzz.md` is the
    *earliest* day and `aaa.md`/`bbb.md` share a *later* day. Sorting by path
    alone would put `aaa`, `bbb`, `zzz` in that order; sorting by
    `(day, path)` puts `zzz` first. Named mutation: change the sort key from
    `(page.day, page.path)` to `page.path` -- this assertion reds.

    This test alone does not pin the `(day, path)` *tie-break* among
    same-day pages: `aaa.md`/`bbb.md` are already visited in path order by
    the sorted glob, so a day-only key (`page.day`, no `page.path`) is a
    stable sort over an already-alphabetical run and produces the identical
    `[zzz, aaa, bbb]` result -- an equivalent mutant this fixture cannot
    distinguish. The tie-break is instead guaranteed jointly by the sorted
    glob, Python's stable `list.sort`, and the explicit `(day, path)` key
    together; no single fixture in this file isolates the `path` half of the
    key from the sorted-glob's own incidental path ordering (see
    `test_two_pages_on_one_date_are_ordered_by_path` below, itself declared
    UNPINNED for the same reason)."""
    _write(
        tmp_path,
        f"{WORKOUTS_DIR}/zzz.md",
        _page(
            date="2024-01-01",
            load_lines="load_value: 1.0\nload_methodology: banister",
        ),
    )
    _write(
        tmp_path,
        f"{WORKOUTS_DIR}/bbb.md",
        _page(
            date="2024-02-01",
            load_lines="load_value: 2.0\nload_methodology: banister",
        ),
    )
    _write(
        tmp_path,
        f"{WORKOUTS_DIR}/aaa.md",
        _page(
            date="2024-02-01",
            load_lines="load_value: 3.0\nload_methodology: banister",
        ),
    )

    scan = scan_documents(tmp_path)

    assert [page.path for page in scan.pages] == [
        f"{WORKOUTS_DIR}/zzz.md",
        f"{WORKOUTS_DIR}/aaa.md",
        f"{WORKOUTS_DIR}/bbb.md",
    ]


def test_two_pages_on_one_date_are_ordered_by_path(tmp_path: Path) -> None:
    """Required fixture (Req 1.9, 5.4): two pages sharing a calendar date are
    both included, in path order between themselves. Declared UNPINNED as an
    *independent* mutation target -- the scan iterates `sorted(glob(...))`
    before any explicit sort, so for two same-day pages path order is already
    the insertion order and this assertion cannot, by itself, tell a genuine
    `(day, path)` tie-break from a same-day pair that was never reordered at
    all; `test_pages_are_sorted_by_day_then_path_not_by_path_alone` above pins
    the day-before-path half of the key (a third, differently-dated page forces
    a real reorder), while the path tie-break itself is guaranteed jointly by
    the sorted glob, the stable sort and the explicit key, and no fixture in
    this file isolates it. Kept because the fixture -- two pages, one date --
    is required and the assertion is still true and still reachable."""
    _write(
        tmp_path,
        f"{WORKOUTS_DIR}/second.md",
        _page(
            date="2024-03-01",
            load_lines="load_value: 1.0\nload_methodology: banister",
        ),
    )
    _write(
        tmp_path,
        f"{WORKOUTS_DIR}/first.md",
        _page(
            date="2024-03-01",
            load_lines="load_value: 2.0\nload_methodology: banister",
        ),
    )

    scan = scan_documents(tmp_path)

    assert [page.path for page in scan.pages] == [
        f"{WORKOUTS_DIR}/first.md",
        f"{WORKOUTS_DIR}/second.md",
    ]


# --- relative-path form (Req 1.1) ----------------------------------------------


def test_page_paths_are_data_root_relative_posix_never_absolute(
    tmp_path: Path,
) -> None:
    _write(tmp_path, f"{WORKOUTS_DIR}/relative.md", _page())

    scan = scan_documents(tmp_path)

    page = scan.pages[0]
    assert page.path == f"{WORKOUTS_DIR}/relative.md"
    assert not Path(page.path).is_absolute()
    assert str(tmp_path) not in page.path


# --- record type sanity ---------------------------------------------------------


def test_page_record_and_skipped_page_are_frozen_dataclasses() -> None:
    page = PageRecord(
        path="workouts/x.md",
        day=__import__("datetime").date(2024, 1, 1),
        load=None,
        methodology=None,
        effort=None,
        tag_problem=None,
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        page.load = 1.0  # type: ignore[misc]

    skipped = SkippedPage(path="workouts/x.md", reason="test")
    with pytest.raises(dataclasses.FrozenInstanceError):
        skipped.reason = "other"  # type: ignore[misc]
