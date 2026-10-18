"""Synthetic integration cases for the morning-of page pass."""

from __future__ import annotations

import os
from dataclasses import replace
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import Mock

import pytest

from fitdocs import docio
from fitdocs.contract import DOC_VERSION, MORNING_REGION, region_block
from fitdocs.docmerge import begin_marker, end_marker
from fitdocs.morning import engine
from fitdocs.morning.block import MorningInputs, render_region
from fitdocs.morning.docedit import read_morning, replace_morning
from fitdocs.morning.engine import (
    MorningPage,
    MorningReport,
    PageOutcome,
    run_morning_pass,
)
from fitdocs.wellness import Metric, SeriesReadError, WellnessSeries, read_series
from tests.morning.builders import (
    rendered_page,
    series_value,
    stage_series,
    wellness_series,
    workout_page,
)

DAY = date(2021, 9, 8)


def _series(day: date = DAY, days: int = 75) -> WellnessSeries:
    return wellness_series(
        series_value(
            day - timedelta(days=days - 1 - i),
            47.0 + i % 19,
            metric=Metric.RESTING_HR_BPM,
            source="intervals-icu",
            canonical=True,
            origin="apple",
        )
        for i in range(days)
    )


def _page(root: Path, name: str, text: str) -> Path:
    path = root / "workouts" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="")
    os.utime(path, ns=(1_000_000_000, 1_000_000_000))
    return path


def _state(path: Path) -> tuple[bytes, int]:
    return path.read_bytes(), path.stat().st_mtime_ns


def _outside(data: bytes) -> tuple[bytes, bytes]:
    begin = begin_marker(MORNING_REGION).encode() + b"\n"
    end = b"\n" + end_marker(MORNING_REGION).encode()
    prefix, _, rest = data.partition(begin)
    _, _, suffix = rest.partition(end)
    return prefix + begin, end + suffix


def _fresh(root: Path, day: date | None = DAY) -> str:
    return render_region(
        MorningInputs.of(read_series(root)).block(day) if day else None
    )


@pytest.mark.parametrize(
    "observable",
    [
        "initial-empty",
        "first-pages",
        "first-counters",
        "first-status",
        "first-replaces",
        "filled-bytes-z-real.md",
        "filled-bytes-a-synthetic.md",
        "filled-mtime-z-real.md",
        "filled-mtime-a-synthetic.md",
        "filled-content-z-real.md",
        "filled-content-a-synthetic.md",
        "outside-z-real.md",
        "outside-a-synthetic.md",
        "populated-precondition",
        "second-report",
        "second-state",
        "second-replaces",
        "no-temps",
    ],
)
def test_fills_synthetic_and_real_pages_then_second_pass_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, observable: str
) -> None:
    stage_series(tmp_path, _series())
    paths = [
        _page(tmp_path, "z-real.md", rendered_page()),
        _page(tmp_path, "a-synthetic.md", workout_page()),
    ]
    before = {path: _state(path) for path in paths}
    if observable == "initial-empty":
        assert all(read_morning(data.decode()) == "" for data, _ in before.values())
    spy = Mock(wraps=os.replace)
    monkeypatch.setattr(os, "replace", spy)
    first = run_morning_pass(tmp_path)
    if observable == "first-pages":
        assert first.pages == tuple(
            MorningPage(f"workouts/{path.name}", PageOutcome.UPDATED, None)
            for path in sorted(paths)
        )
    if observable == "first-counters":
        assert (first.unchanged, first.without_region, first.newer) == (0, 0, 0)
    if observable == "first-status":
        assert (
            first.series_has_values and first.unavailable is None and not first.failed
        )
    if observable == "first-replaces":
        assert spy.call_count == len(paths)
    for path in paths:
        after = _state(path)
        if observable == f"filled-bytes-{path.name}":
            assert after[0] != before[path][0]
        if observable == f"filled-mtime-{path.name}":
            assert after[1] != before[path][1]
        if observable == f"filled-content-{path.name}":
            assert read_morning(after[0].decode()) == _fresh(tmp_path)
        if observable == f"outside-{path.name}":
            assert _outside(after[0]) == _outside(before[path][0])
    populated = {path: _state(path) for path in paths}
    if observable == "populated-precondition":
        assert all(b"## Morning Of" in data for data, _ in populated.values())
    spy.reset_mock()
    second = run_morning_pass(tmp_path)
    if observable == "second-report":
        assert second == MorningReport((), 2, 0, 0, True, None)
    if observable == "second-state":
        assert {path: _state(path) for path in paths} == populated
    if observable == "second-replaces":
        assert spy.call_count == 0
    if observable == "no-temps":
        assert not list((tmp_path / "workouts").glob(".morning-*.tmp"))


@pytest.mark.parametrize("observable", ["date"])
def test_frontmatter_date_overrides_filename(tmp_path: Path, observable: str) -> None:
    stage_series(tmp_path, _series())
    path = _page(tmp_path, "1999-01-01-misleading.md", workout_page())
    run_morning_pass(tmp_path)
    if observable == "date":
        assert read_morning(path.read_text()) == _fresh(tmp_path, DAY)


@pytest.mark.parametrize(
    "observable",
    [
        "populated-precondition",
        "inside-bytes-0",
        "inside-bytes-60",
        "inside-mtime-0",
        "inside-mtime-60",
        "outside-region-0",
        "outside-region-60",
        "outside-day-bytes--1",
        "outside-day-bytes-61",
        "outside-day-mtime--1",
        "outside-day-mtime-61",
        "report-pages",
        "report-unchanged",
    ],
)
def test_origin_change_updates_endpoints_and_preserves_nonempty_outside_days(
    tmp_path: Path,
    observable: str,
) -> None:
    x = DAY
    series = _series(x + timedelta(days=61), days=150)
    stage_series(tmp_path, series)
    paths = {
        offset: _page(
            tmp_path, f"{offset + 2:03}.md", workout_page(x + timedelta(days=offset))
        )
        for offset in (-1, 0, 60, 61)
    }
    run_morning_pass(tmp_path)
    before = {offset: _state(path) for offset, path in paths.items()}
    if observable == "populated-precondition":
        assert all(b"## Morning Of" in data for data, _ in before.values())
    stage_series(
        tmp_path,
        wellness_series(
            replace(v, origin="garmin") if v.day == x else v for v in series.values
        ),
    )
    report = run_morning_pass(tmp_path)
    for offset in (0, 60):
        if observable == f"inside-bytes-{offset}":
            assert _state(paths[offset])[0] != before[offset][0]
        if observable == f"inside-mtime-{offset}":
            assert _state(paths[offset])[1] != before[offset][1]
        if observable == f"outside-region-{offset}":
            assert _outside(paths[offset].read_bytes()) == _outside(before[offset][0])
    for offset in (-1, 61):
        if observable == f"outside-day-bytes-{offset}":
            assert _state(paths[offset])[0] == before[offset][0]
        if observable == f"outside-day-mtime-{offset}":
            assert _state(paths[offset])[1] == before[offset][1]
    if observable == "report-pages":
        assert report.pages == tuple(
            MorningPage(f"workouts/{paths[o].name}", PageOutcome.UPDATED, None)
            for o in (0, 60)
        )
    if observable == "report-unchanged":
        assert report.unchanged == 2


@pytest.mark.parametrize(
    "observable",
    ["populated-precondition", "report", "content", "bytes", "mtime", "outside"],
)
def test_empty_series_clears_populated_blocks(tmp_path: Path, observable: str) -> None:
    stage_series(tmp_path, _series())
    path = _page(tmp_path, "page.md", workout_page())
    run_morning_pass(tmp_path)
    before = _state(path)
    if observable == "populated-precondition":
        assert b"## Morning Of" in before[0]
    stage_series(tmp_path, wellness_series(()))
    report = run_morning_pass(tmp_path)
    if observable == "report":
        assert report == MorningReport(
            (MorningPage("workouts/page.md", PageOutcome.REMOVED, None),),
            0,
            0,
            0,
            False,
            None,
        )
    if observable == "content":
        assert read_morning(path.read_text()) == ""
    if observable == "bytes":
        assert _state(path)[0] != before[0]
    if observable == "mtime":
        assert _state(path)[1] != before[1]
    if observable == "outside":
        assert _outside(path.read_bytes()) == _outside(before[0])


@pytest.mark.parametrize(
    "day", [None, date(1999, 1, 1)], ids=["missing-date", "no-figure"]
)
@pytest.mark.parametrize(
    "observable",
    [
        "stale-precondition",
        "removed-report",
        "empty-content",
        "removed-bytes",
        "removed-mtime",
        "second-report",
        "second-state",
    ],
)
def test_absent_day_clears_stale_content_and_keeps_empty_region_unchanged(
    tmp_path: Path, day: date | None, observable: str
) -> None:
    stage_series(tmp_path, _series())
    path = _page(
        tmp_path, "2021-09-08.md", workout_page(day, morning="stale morning\n")
    )
    before = _state(path)
    if observable == "stale-precondition":
        assert read_morning(before[0].decode()) == "stale morning\n"
    report = run_morning_pass(tmp_path)
    if observable == "removed-report":
        assert report.pages == (
            MorningPage("workouts/2021-09-08.md", PageOutcome.REMOVED, None),
        )
    if observable == "empty-content":
        assert read_morning(path.read_text()) == ""
    if observable == "removed-bytes":
        assert _state(path)[0] != before[0]
    if observable == "removed-mtime":
        assert _state(path)[1] != before[1]
    empty = _state(path)
    report = run_morning_pass(tmp_path)
    if observable == "second-report":
        assert report == MorningReport((), 1, 0, 0, True, None)
    if observable == "second-state":
        assert _state(path) == empty


@pytest.mark.parametrize(
    ("version", "with_region", "observable"),
    [
        pytest.param(
            version,
            with_region,
            observable,
            id=f"{label}-{'region' if with_region else 'no-region'}-{observable}",
        )
        for version, label in (
            (None, "missing"),
            ("true", "bool"),
            (DOC_VERSION - 1, "old"),
        )
        for with_region in (True, False)
        for observable in (
            ("status", "updated-report", "content", "changed-bytes", "changed-mtime")
            if with_region
            else ("status", "missing-report", "untouched-bytes", "untouched-mtime")
        )
    ],
)
def test_unusable_and_old_versions_process_or_count_missing_region(
    tmp_path: Path, version: int | str | None, with_region: bool, observable: str
) -> None:
    stage_series(tmp_path, _series())
    text = workout_page(doc_version=version)
    if not with_region:
        text = text.replace(region_block(MORNING_REGION, "").rstrip("\n"), "")
    path = _page(tmp_path, "page.md", text)
    before = _state(path)
    report = run_morning_pass(tmp_path)
    if observable == "status":
        assert (report.newer, report.failed, report.unavailable) == (0, False, None)
    if with_region:
        if observable == "updated-report":
            assert report.pages == (
                MorningPage("workouts/page.md", PageOutcome.UPDATED, None),
            )
        if observable == "content":
            assert read_morning(path.read_text()) == _fresh(tmp_path)
        if observable == "changed-bytes":
            assert _state(path)[0] != before[0]
        if observable == "changed-mtime":
            assert _state(path)[1] != before[1]
    else:
        if observable == "missing-report":
            assert report == MorningReport((), 0, 1, 0, True, None)
        if observable == "untouched-bytes":
            assert _state(path)[0] == before[0]
        if observable == "untouched-mtime":
            assert _state(path)[1] == before[1]


@pytest.mark.parametrize(
    "observable", ["stale-precondition", "report", "bytes", "mtime"]
)
def test_newer_version_with_stale_block_is_untouched(
    tmp_path: Path, observable: str
) -> None:
    stage_series(tmp_path, _series())
    path = _page(
        tmp_path,
        "page.md",
        workout_page(doc_version=DOC_VERSION + 1, morning="stale\n"),
    )
    before = _state(path)
    if observable == "stale-precondition":
        assert read_morning(before[0].decode()) != _fresh(tmp_path)
    report = run_morning_pass(tmp_path)
    if observable == "report":
        assert report == MorningReport((), 0, 0, 1, True, None)
    if observable == "bytes":
        assert _state(path)[0] == before[0]
    if observable == "mtime":
        assert _state(path)[1] == before[1]


@pytest.mark.parametrize(
    "observable",
    [
        "failed-doc",
        "failed-outcome",
        "failed-detail",
        "failed-status",
        "failed-bytes",
        "failed-mtime",
        "next-report",
        "next-content",
    ],
)
def test_damaged_other_region_fails_then_next_page_updates(
    tmp_path: Path, observable: str
) -> None:
    stage_series(tmp_path, _series())
    bad = _page(
        tmp_path,
        "a-bad.md",
        workout_page().replace(
            "<!-- fitdocs:end:notes -->", "<!-- fitdocs:end:load -->"
        ),
    )
    good = _page(tmp_path, "z-good.md", workout_page())
    before = _state(bad)
    report = run_morning_pass(tmp_path)
    if observable == "failed-doc":
        assert report.pages[0].doc == "workouts/a-bad.md"
    if observable == "failed-outcome":
        assert report.pages[0].outcome == PageOutcome.FAILED
    if observable == "failed-detail":
        assert report.pages[0].detail and "notes" in report.pages[0].detail
    if observable == "failed-status":
        assert report.failed and report.without_region == 0
    if observable == "failed-bytes":
        assert _state(bad)[0] == before[0]
    if observable == "failed-mtime":
        assert _state(bad)[1] == before[1]
    if observable == "next-report":
        assert report.pages[1] == MorningPage(
            "workouts/z-good.md", PageOutcome.UPDATED, None
        )
    if observable == "next-content":
        assert read_morning(good.read_text()) == _fresh(tmp_path)


@pytest.mark.parametrize(
    "observable", ["same-stamp-precondition", "report", "content", "bytes", "mtime"]
)
def test_hand_edited_body_retaining_stamp_is_repaired(
    tmp_path: Path, observable: str
) -> None:
    stage_series(tmp_path, _series())
    fresh = _fresh(tmp_path)
    edited = fresh.replace("## Morning Of", "## Hand edit")
    path = _page(tmp_path, "page.md", workout_page(morning=edited))
    before = _state(path)
    if observable == "same-stamp-precondition":
        assert edited.partition("\n")[0] == fresh.partition("\n")[0] and edited != fresh
    report = run_morning_pass(tmp_path)
    if observable == "report":
        assert report.pages == (
            MorningPage("workouts/page.md", PageOutcome.UPDATED, None),
        )
    if observable == "content":
        assert read_morning(path.read_text()) == fresh
    if observable == "bytes":
        assert _state(path)[0] != before[0]
    if observable == "mtime":
        assert _state(path)[1] != before[1]


@pytest.mark.parametrize("failure", ["oserror", "unexpected"])
@pytest.mark.parametrize(
    "observable",
    [
        "failed-report",
        "failed-status",
        "failed-bytes",
        "failed-mtime",
        "next-report",
        "next-content",
        "no-temps",
    ],
)
def test_one_page_failure_leaves_it_whole_and_continues(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str, observable: str
) -> None:
    stage_series(tmp_path, _series())
    bad = _page(tmp_path, "a-bad.md", workout_page())
    good = _page(tmp_path, "z-good.md", workout_page())
    before = _state(bad)
    real_replace = os.replace

    def chosen_failure(src: str, dst: Path) -> None:
        if dst == bad:
            if failure == "oserror":
                raise OSError("chosen replacement failed")
            raise ValueError("chosen unexpected failure")
        real_replace(src, dst)

    monkeypatch.setattr(os, "replace", chosen_failure)
    report = run_morning_pass(tmp_path)
    if observable == "failed-report":
        assert report.pages[0] == MorningPage(
            "workouts/a-bad.md",
            PageOutcome.FAILED,
            "chosen replacement failed"
            if failure == "oserror"
            else "ValueError: chosen unexpected failure",
        )
    if observable == "failed-status":
        assert report.failed
    if observable == "failed-bytes":
        assert _state(bad)[0] == before[0]
    if observable == "failed-mtime":
        assert _state(bad)[1] == before[1]
    if observable == "next-report":
        assert report.pages[1] == MorningPage(
            "workouts/z-good.md", PageOutcome.UPDATED, None
        )
    if observable == "next-content":
        assert read_morning(good.read_text()) == _fresh(tmp_path)
    if observable == "no-temps":
        assert not list(bad.parent.glob(".morning-*.tmp"))


@pytest.mark.skipif(os.geteuid() == 0, reason="root bypasses directory permissions")
@pytest.mark.parametrize("observable", ["outcomes", "details", "state", "no-temps"])
def test_readonly_workouts_directory_fails_every_page_without_temps(
    tmp_path: Path,
    observable: str,
) -> None:
    stage_series(tmp_path, _series())
    paths = [_page(tmp_path, f"{i}.md", workout_page()) for i in range(2)]
    before = {path: _state(path) for path in paths}
    paths[0].parent.chmod(0o555)
    try:
        report = run_morning_pass(tmp_path)
    finally:
        paths[0].parent.chmod(0o755)
    if observable == "outcomes":
        assert [p.outcome for p in report.pages] == [
            PageOutcome.FAILED,
            PageOutcome.FAILED,
        ]
    if observable == "details":
        assert all(p.detail for p in report.pages) and report.failed
    if observable == "state":
        assert {path: _state(path) for path in paths} == before
    if observable == "no-temps":
        assert not list(paths[0].parent.glob(".morning-*.tmp"))


@pytest.mark.parametrize("observable", ["same-interrupt", "bytes", "mtime", "no-temps"])
def test_interrupt_removes_temp_and_propagates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, observable: str
) -> None:
    stage_series(tmp_path, _series())
    path = _page(tmp_path, "page.md", workout_page())
    before = _state(path)
    interrupt = KeyboardInterrupt("chosen interrupt")
    monkeypatch.setattr(os, "replace", Mock(side_effect=interrupt))
    with pytest.raises(KeyboardInterrupt) as caught:
        run_morning_pass(tmp_path)
    if observable == "same-interrupt":
        assert caught.value is interrupt
    if observable == "bytes":
        assert _state(path)[0] == before[0]
    if observable == "mtime":
        assert _state(path)[1] == before[1]
    if observable == "no-temps":
        assert not list(path.parent.glob(".morning-*.tmp"))


@pytest.mark.parametrize("observable", ["report", "state", "symlink"])
def test_unusable_documents_are_silently_skipped(
    tmp_path: Path, observable: str
) -> None:
    stage_series(tmp_path, _series())
    target = tmp_path / "external.md"
    target.write_text(workout_page())
    other = _page(
        tmp_path, "other.md", workout_page().replace("type: workout", "type: note")
    )
    binary = _page(tmp_path, "binary.md", workout_page())
    binary.write_bytes(b"\xff\xfe")
    link = other.parent / "link.md"
    link.symlink_to(target)
    nested = _page(tmp_path, "nested/page.md", workout_page())
    before = {path: _state(path) for path in (target, other, binary, nested)}
    report = run_morning_pass(tmp_path)
    if observable == "report":
        assert report == MorningReport((), 0, 0, 0, True, None)
    if observable == "state":
        assert {path: _state(path) for path in before} == before
    if observable == "symlink":
        assert link.is_symlink()


@pytest.mark.parametrize("observable", ["report", "zero-reads", "state"])
def test_unreadable_native_series_prevents_all_document_reads(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, observable: str
) -> None:
    files = stage_series(tmp_path, _series())
    files[0].unlink()
    paths = [
        _page(tmp_path, f"{i}.md", workout_page(morning="stale\n")) for i in range(2)
    ]
    before = {path: _state(path) for path in paths}
    with pytest.raises(SeriesReadError) as caught:
        read_series(tmp_path)
    spy = Mock(wraps=docio.read_document)
    monkeypatch.setattr(docio, "read_document", spy)
    report = run_morning_pass(tmp_path)
    if observable == "report":
        assert report == MorningReport((), 0, 0, 0, False, str(caught.value))
    if observable == "zero-reads":
        assert spy.call_count == 0
    if observable == "state":
        assert {path: _state(path) for path in paths} == before


@pytest.mark.parametrize("observable", ["read-events", "one-inputs", "pages"])
def test_reads_series_first_once_and_documents_once_in_sorted_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, observable: str
) -> None:
    stage_series(tmp_path, _series())
    paths = [_page(tmp_path, name, workout_page()) for name in ("z.md", "a.md", "m.md")]
    events: list[tuple[str, Path]] = []
    real_read = docio.read_document
    real_series = read_series
    inputs = Mock(wraps=MorningInputs.of)

    def series(root: Path) -> WellnessSeries:
        events.append(("series", root))
        return real_series(root)

    def document(path: Path) -> docio.DocumentRead | None:
        events.append(("document", path))
        return real_read(path)

    monkeypatch.setattr(engine, "read_series", series)
    monkeypatch.setattr(docio, "read_document", document)
    monkeypatch.setattr(MorningInputs, "of", inputs)
    report = run_morning_pass(tmp_path)
    if observable == "read-events":
        assert events == [
            ("series", tmp_path),
            *(("document", path) for path in sorted(paths)),
        ]
    if observable == "one-inputs":
        assert inputs.call_count == 1
    if observable == "pages":
        assert len(report.pages) == 3


@pytest.mark.parametrize("observable", ["no-failed", "has-failed"])
def test_failed_property_checks_all_outcomes(observable: str) -> None:
    updated = MorningPage("workouts/a.md", PageOutcome.UPDATED, None)
    removed = MorningPage("workouts/b.md", PageOutcome.REMOVED, None)
    failed = MorningPage("workouts/c.md", PageOutcome.FAILED, "broken")
    if observable == "no-failed":
        assert not MorningReport((updated, removed), 0, 0, 0, True, None).failed
    if observable == "has-failed":
        assert MorningReport((updated, failed, removed), 0, 0, 0, True, None).failed


@pytest.mark.parametrize("observable", ["reads", "paths", "other-state"])
def test_pass_uses_only_native_series_and_existing_workout_pages(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, observable: str
) -> None:
    files = stage_series(tmp_path, _series())
    page = _page(tmp_path, "page.md", workout_page())
    sentinels = (
        "athlete.toml",
        "fitdocs.toml",
        "recovery.md",
        "index.duckdb",
        "fit-archive/synthetic.fit",
        "workouts/assets/synthetic.svg",
    )
    for name in sentinels:
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("synthetic sentinel\n")
    before = {
        path.relative_to(tmp_path).as_posix(): _state(path)
        for path in tmp_path.rglob("*")
        if path.is_file()
    }
    reads: list[Path] = []
    original = Path.read_bytes

    def read(path: Path) -> bytes:
        reads.append(path)
        return original(path)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "read_bytes", read)
        run_morning_pass(tmp_path)
    after = {
        path.relative_to(tmp_path).as_posix(): _state(path)
        for path in tmp_path.rglob("*")
        if path.is_file()
    }
    if observable == "reads":
        assert reads == [files[-1], *files[:-1], page]
    if observable == "paths":
        assert after.keys() == before.keys()
    if observable == "other-state":
        assert {
            key: value for key, value in after.items() if key != "workouts/page.md"
        } == {key: value for key, value in before.items() if key != "workouts/page.md"}


@pytest.mark.parametrize(
    "observable",
    [
        "directory",
        "prefix",
        "suffix",
        "newline",
        "encoding",
        "delete",
        "new-bytes",
        "old-state",
        "destination",
    ],
)
def test_atomic_replacement_protocol(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, observable: str
) -> None:
    import tempfile

    stage_series(tmp_path, _series())
    text = workout_page(morning="stale\n")
    path = _page(tmp_path, "page.md", text)
    before = _state(path)
    expected = replace_morning(text, _fresh(tmp_path))
    factory = Mock(wraps=tempfile.NamedTemporaryFile)
    captured: list[tuple[Path, Path, bytes, tuple[bytes, int]]] = []
    real_replace = os.replace

    def replace_file(source: Path, destination: Path) -> None:
        captured.append((source, destination, source.read_bytes(), _state(path)))
        real_replace(source, destination)

    monkeypatch.setattr(tempfile, "NamedTemporaryFile", factory)
    monkeypatch.setattr(os, "replace", replace_file)
    run_morning_pass(tmp_path)
    if observable not in ("newline", "encoding", "delete"):
        source, destination, new_bytes, old_state = captured[0]
    if observable == "directory":
        assert source.parent == path.parent
    if observable == "prefix":
        assert source.name.startswith(".morning-")
    if observable == "suffix":
        assert source.suffix == ".tmp"
    if observable == "newline":
        assert factory.call_args.kwargs["newline"] == ""
    if observable == "encoding":
        assert factory.call_args.kwargs["encoding"] == "utf-8"
    if observable == "delete":
        assert factory.call_args.kwargs["delete"] is False
    if observable == "new-bytes":
        assert new_bytes == expected.encode("utf-8")
    if observable == "old-state":
        assert old_state == before
    if observable == "destination":
        assert destination == path


@pytest.mark.parametrize(
    ("outcome", "value"),
    [
        (PageOutcome.UPDATED, "updated"),
        (PageOutcome.REMOVED, "removed"),
        (PageOutcome.FAILED, "failed"),
    ],
    ids=["updated", "removed", "failed"],
)
def test_outcome_wire_values(outcome: PageOutcome, value: str) -> None:
    assert outcome.value == value
