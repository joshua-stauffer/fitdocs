"""Recovery engine behavior using synthetic roots and public data interfaces."""

from __future__ import annotations

import os
import stat
import tempfile
import time
from dataclasses import FrozenInstanceError, fields
from datetime import date, timedelta
from pathlib import Path
from typing import Any, cast

import pytest

import fitdocs.recovery.engine as engine
from fitdocs.contract import GENERATED_PREFIX, is_generated
from fitdocs.declaration import ensure_declarations
from fitdocs.history import (
    HistoryComputation,
    compute_history,
    day_rows,
    read_history_inputs,
)
from fitdocs.recovery.baselines import Baselines
from fitdocs.recovery.charts import render_charts
from fitdocs.recovery.engine import (
    FileOutcome,
    FileResult,
    RecoveryReport,
    run_recovery,
)
from fitdocs.recovery.page import render_page
from fitdocs.recovery.view import RecoveryView, build_view
from fitdocs.render.charts.kit import describe_kinds
from fitdocs.settings import SettingsError
from fitdocs.wellness import Metric, SeriesValue, read_series
from tests.recovery.builders import series_value, workout_page
from tests.wellness.builders_series import write_series

D = date(2024, 8, 19)
NAMES = ("load", "hrv-sdnn", "hrv-rmssd", "resting-hr", "sleep", "other")
PAGE = "recovery/recovery.md"
MARKER = f"{GENERATED_PREFIX} -->\n"


def _write(root: Path, rel: str, data: str | bytes) -> Path:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data.encode() if isinstance(data, str) else data)
    return path


def _value(
    metric: Metric, value: float, *, offset: int = 0, source: str = "device"
) -> SeriesValue:
    return series_value(
        D + timedelta(days=offset),
        value,
        metric=metric,
        source=source,
        canonical=True,
        origin="local",
    )


def _stage(root: Path, *, full: bool = False) -> list[SeriesValue]:
    root.mkdir(parents=True, exist_ok=True)
    values = [_value(Metric.RESTING_HR_BPM, 57)]
    if full:
        values += [
            _value(Metric.HRV_SDNN_MS, 43),
            _value(Metric.HRV_RMSSD_MS, 31),
            _value(Metric.SLEEP_S, 25800),
            _value(Metric.STEPS, 6243),
        ]
        workout_page(root, "older", D - timedelta(days=6), 37)
        workout_page(root, "latest", D, 83)
    write_series(root, values)
    return values


def _projection(report: RecoveryReport) -> tuple[tuple[str, str, str | None], ...]:
    return tuple((item.path, item.outcome.value, item.detail) for item in report.files)


def _file_state(path: Path) -> tuple[bytes | str | None, int, int, int]:
    st = path.lstat()
    content: bytes | str | None
    if path.is_symlink():
        content = os.readlink(path)
    elif path.is_dir():
        content = None
    else:
        content = path.read_bytes()
    return content, st.st_mode, st.st_mtime_ns, st.st_ctime_ns


def _snapshot(root: Path) -> dict[str, tuple[bytes | str | None, int, int, int]]:
    return {
        path.relative_to(root).as_posix(): _file_state(path)
        for path in sorted(root.rglob("*"))
    }


def test_real_run_and_report(tmp_path: Path) -> None:
    root = tmp_path / "nested" / "Athlete Alpha"
    _stage(root, full=True)
    report = run_recovery(root)
    assert (
        report.as_of,
        report.window_start,
        report.methodology,
        report.note,
        report.failure,
        report.failed,
    ) == (D, date(2024, 5, 22), "threshold", None, None, False)
    assert _projection(report) == tuple(
        (f"recovery/assets/recovery-{name}.svg", "written", None) for name in NAMES
    ) + ((PAGE, "written", None),)
    assert (root / "recovery/AGENTS.md").read_text() == (
        Path(__file__).parents[1] / "declaration_golden/recovery.AGENTS.md"
    ).read_text()
    series = read_series(root)
    history = compute_history(read_history_inputs(root), methodology=None)
    view = build_view(series, Baselines.of(series), history, panel_limit=12)
    expected = render_page(
        cast(RecoveryView, view), render_charts(cast(RecoveryView, view))
    )
    assert (root / PAGE).read_text() == expected.markdown
    assert tuple(
        (name, (root / f"recovery/assets/recovery-{name}.svg").read_text())
        for name in NAMES
    ) == tuple((name, MARKER + svg) for name, svg in expected.charts)


def test_reports_public_fields_and_frozen_records() -> None:
    assert tuple((item.name, item.value) for item in FileOutcome) == (
        ("WRITTEN", "written"),
        ("UNCHANGED", "unchanged"),
        ("REMOVED", "removed"),
        ("FOREIGN", "foreign"),
        ("FAILED", "failed"),
    )
    assert tuple(f.name for f in fields(FileResult)) == ("path", "outcome", "detail")
    assert tuple(f.name for f in fields(RecoveryReport)) == (
        "as_of",
        "window_start",
        "methodology",
        "files",
        "note",
        "failure",
    )
    file = FileResult(
        "recovery/assets/recovery-sleep.svg", FileOutcome.FAILED, "denied"
    )
    report = RecoveryReport(D, date(2024, 5, 22), "custom", (file,), "note", "failure")
    with pytest.raises(FrozenInstanceError):
        cast(Any, file).detail = "changed"
    with pytest.raises(FrozenInstanceError):
        cast(Any, report).note = "changed"


@pytest.mark.parametrize(
    "failure,outcomes,expected",
    [
        (None, (), False),
        ("", (), True),
        ("unreadable", (), True),
        (None, (FileOutcome.FOREIGN,), False),
        (None, (FileOutcome.WRITTEN,), False),
        (None, (FileOutcome.FAILED,), True),
        (None, (FileOutcome.FAILED, FileOutcome.UNCHANGED), True),
    ],
)
def test_failed_property(
    failure: str | None, outcomes: tuple[FileOutcome, ...], expected: bool
) -> None:
    report = RecoveryReport(
        None,
        None,
        None,
        tuple(FileResult(str(i), outcome, None) for i, outcome in enumerate(outcomes)),
        None,
        failure,
    )
    assert report.failed is expected


def test_second_run_unchanged_and_one_new_day(tmp_path: Path) -> None:
    values = _stage(tmp_path, full=True)
    first = run_recovery(tmp_path)
    paths = [tmp_path / item.path for item in first.files] + list(
        tmp_path.rglob("AGENTS.md")
    )
    for index, path in enumerate(paths):
        os.utime(path, ns=(1_000_000_000, 1_000_000_000 + index))
    before = {path: _file_state(path) for path in paths}
    second = run_recovery(tmp_path)
    assert _projection(second) == tuple(
        (f"recovery/assets/recovery-{name}.svg", "unchanged", None) for name in NAMES
    ) + ((PAGE, "unchanged", None),)
    assert {path: _file_state(path) for path in paths} == before
    values.append(_value(Metric.RESTING_HR_BPM, 69, offset=-1))
    write_series(tmp_path, values)
    third = run_recovery(tmp_path)
    assert _projection(third) == tuple(
        (
            f"recovery/assets/recovery-{name}.svg",
            "written" if name == "resting-hr" else "unchanged",
            None,
        )
        for name in NAMES
    ) + ((PAGE, "written", None),)
    assert tuple(
        path.relative_to(tmp_path).as_posix()
        for path in paths
        if _file_state(path) != before[path]
    ) == ("recovery/assets/recovery-resting-hr.svg", PAGE)


def test_empty_before_settings_and_no_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_series(tmp_path, [])
    _write(tmp_path, "fitdocs.toml", "[history]\ntau_fitness_days = 'malformed'\n")
    _write(tmp_path, PAGE, MARKER + "existing generated page\n")
    before = _snapshot(tmp_path)
    calls: list[Path] = []
    original = read_series

    def read(root: Path) -> Any:
        calls.append(root)
        return original(root)

    monkeypatch.setattr(engine, "read_series", read)
    report = run_recovery(tmp_path)
    assert calls == [tmp_path]
    assert (
        report.as_of,
        report.window_start,
        report.methodology,
        report.files,
        report.failure,
        report.failed,
    ) == (None, None, None, (), None, False)
    assert (
        report.note is not None
        and "no" in report.note.lower()
        and "value" in report.note.lower()
    )
    assert _snapshot(tmp_path) == before


def test_corrupt_listed_year_fails_before_settings_and_writes(tmp_path: Path) -> None:
    _stage(tmp_path)
    _write(tmp_path, "wellness/2024.csv", "corrupt listed year\n")
    _write(tmp_path, "fitdocs.toml", "[history]\ntau_fitness_days = 'malformed'\n")
    before = _snapshot(tmp_path)
    report = run_recovery(tmp_path)
    assert (
        report.as_of,
        report.window_start,
        report.methodology,
        report.files,
        report.note,
        report.failed,
    ) == (None, None, None, (), None, True)
    assert (
        report.failure is not None
        and "2024.csv" in report.failure
        and "fitdocs sync" in report.failure
        and "fitdocs regen" in report.failure
    )
    assert _snapshot(tmp_path) == before


@pytest.mark.parametrize(
    "settings,methodology",
    [
        ("[history]\ntau_fitness_days = 'bad'\n", None),
        ("[load]\ndefault_calculator = 12\n", None),
        ("", "not-recorded"),
        ("", None),
    ],
)
def test_history_errors_before_writes(
    tmp_path: Path, settings: str, methodology: str | None
) -> None:
    _stage(tmp_path, full=True)
    if not settings and methodology is None:
        workout_page(
            tmp_path, "alternate", D - timedelta(days=2), 29, methodology="alternate"
        )
    _write(tmp_path, "fitdocs.toml", settings)
    before = _snapshot(tmp_path)
    with pytest.raises(SettingsError) as expected:
        compute_history(read_history_inputs(tmp_path), methodology=methodology)
    with pytest.raises(type(expected.value), match=".") as actual:
        run_recovery(tmp_path, methodology=methodology)
    assert str(actual.value) == str(expected.value)
    assert _snapshot(tmp_path) == before


@pytest.mark.parametrize(
    "requested,configured,chosen",
    [(None, "threshold", "threshold"), ("alternate", "threshold", "alternate")],
)
def test_actual_history_rows_and_reader_order(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    requested: str | None,
    configured: str,
    chosen: str,
) -> None:
    _stage(tmp_path, full=True)
    workout_page(
        tmp_path, "alternate-first", D - timedelta(days=9), 113, methodology="alternate"
    )
    workout_page(
        tmp_path, "alternate-last", D - timedelta(days=1), 23, methodology="alternate"
    )
    _write(
        tmp_path,
        "fitdocs.toml",
        f'[history]\nmethodology = "{configured}"\ncoverage_threshold = 0.0\n',
    )
    inputs = read_history_inputs(tmp_path)
    computation = compute_history(inputs, methodology=requested)
    if computation is None:
        pytest.fail("staged workout loads must produce a computation")
    rows = day_rows(computation.series, computation.model, computation.weeks)
    expected_by_day = {row.day: row for row in rows}
    captured: list[Any] = []
    trace: list[tuple[str, Any]] = []
    original_read, original_inputs, original_compute = (
        read_series,
        read_history_inputs,
        compute_history,
    )

    def read(root: Path) -> Any:
        trace.append(("series", root))
        return original_read(root)

    def read_inputs(root: Path) -> Any:
        trace.append(("history", root))
        return original_inputs(root)

    def compute(value: Any, *, methodology: str | None) -> Any:
        trace.append(("compute", methodology))
        return original_compute(value, methodology=methodology)

    def view(series: Any, baselines: Any, load: Any, *, panel_limit: int) -> Any:
        result = build_view(series, baselines, load, panel_limit=panel_limit)
        captured.append((load, result))
        return result

    monkeypatch.setattr(engine, "read_series", read)
    monkeypatch.setattr(engine, "read_history_inputs", read_inputs)
    monkeypatch.setattr(engine, "compute_history", compute)
    monkeypatch.setattr(engine, "build_view", view)
    report = run_recovery(tmp_path, methodology=requested)
    assert trace == [
        ("series", tmp_path),
        ("history", tmp_path),
        ("compute", requested),
    ]
    assert len(captured) == 1 and isinstance(captured[0][0], HistoryComputation)
    actual_view = captured[0][1]
    assert (
        report.methodology,
        actual_view.load.methodology,
        actual_view.load.rows,
    ) == (
        chosen,
        chosen,
        tuple(
            expected_by_day.get(date(2024, 5, 22) + timedelta(days=i))
            for i in range(90)
        ),
    )


@pytest.mark.parametrize(
    "limit,count,last", [(12, 13, "sensor-12"), (3, 4, "sensor-03")]
)
def test_live_panel_limit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, limit: int, count: int, last: str
) -> None:
    values = [
        _value(Metric.STEPS, 1450 + i * 173, source=f"sensor-{i:02}", offset=-i)
        for i in range(count)
    ]
    write_series(tmp_path, values)
    listings = describe_kinds()
    if limit == 3:
        listings = tuple(
            {**item, "bound": {**item["bound"], "limit": 3}}
            if item["name"] == "small-multiples"
            else item
            for item in listings
        )
    monkeypatch.setattr(engine, "describe_kinds", lambda: listings)
    captured: list[int] = []

    def view(series: Any, baselines: Any, load: Any, *, panel_limit: int) -> Any:
        captured.append(panel_limit)
        return build_view(series, baselines, load, panel_limit=panel_limit)

    monkeypatch.setattr(engine, "build_view", view)
    run_recovery(tmp_path)
    page = (tmp_path / PAGE).read_text()
    assert captured == [limit]
    assert (
        f"Also recorded in this window but not charted: Steps ({last})."
        in page.splitlines()
    )


@pytest.mark.parametrize("relative", ["recovery", "recovery/assets"])
@pytest.mark.parametrize("kind", ["file", "symlink", "dangling"])
def test_foreign_location_before_declarations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, relative: str, kind: str
) -> None:
    _stage(tmp_path)
    target = tmp_path / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    if kind == "file":
        target.write_text("athlete-owned location")
    else:
        outside = tmp_path / "private-target"
        if kind == "symlink":
            outside.mkdir()
            _write(outside, "keep", "private target contents")
        target.symlink_to(outside, target_is_directory=True)
    before = _snapshot(tmp_path)
    refreshes: list[Path] = []
    monkeypatch.setattr(
        engine, "ensure_declarations", lambda root: refreshes.append(root)
    )
    report = run_recovery(tmp_path)
    assert tuple((item.path, item.outcome) for item in report.files) == (
        (relative, FileOutcome.FOREIGN),
    )
    assert report.failed is False
    assert refreshes == []
    assert _snapshot(tmp_path) == before


@pytest.mark.parametrize("relative", [PAGE, "recovery/assets/recovery-resting-hr.svg"])
@pytest.mark.parametrize(
    "kind", ["file", "directory", "symlink", "dangling", "unreadable", "nonutf8"]
)
def test_foreign_output_kept(tmp_path: Path, relative: str, kind: str) -> None:
    if kind == "unreadable" and os.geteuid() == 0:
        pytest.skip("root bypasses file permissions")
    _stage(tmp_path)
    target = tmp_path / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    if kind == "directory":
        target.mkdir()
        _write(target, "inside", "foreign child")
    elif kind in ("symlink", "dangling"):
        other = tmp_path / "foreign-target"
        if kind == "symlink":
            other.write_text(MARKER + "private generated-looking target")
        target.symlink_to(other)
    else:
        target.write_bytes(
            MARKER.encode() + b"\xff\xfe"
            if kind == "nonutf8"
            else b"athlete authored content"
        )
        if kind == "unreadable":
            target.chmod(0)
    if kind == "unreadable":
        before = target.lstat()
    else:
        before_state = (
            _file_state(target),
            _snapshot(target) if target.is_dir() else None,
        )
    try:
        report = run_recovery(tmp_path)
        assert tuple((item.path, item.outcome) for item in report.files) == (
            (
                "recovery/assets/recovery-resting-hr.svg",
                FileOutcome.FOREIGN
                if relative.endswith(".svg")
                else FileOutcome.WRITTEN,
            ),
            (PAGE, FileOutcome.FOREIGN if relative == PAGE else FileOutcome.WRITTEN),
        )
        assert report.failed is False
        if kind == "unreadable":
            after = target.lstat()
            assert (after.st_mode, after.st_mtime_ns, after.st_ctime_ns) == (
                before.st_mode,
                before.st_mtime_ns,
                before.st_ctime_ns,
            )
        else:
            assert (
                _file_state(target),
                _snapshot(target) if target.is_dir() else None,
            ) == before_state
    finally:
        if kind == "unreadable":
            target.chmod(0o600)


@pytest.mark.parametrize("relative", [PAGE, "recovery/assets/recovery-resting-hr.svg"])
def test_later_generated_marker_allows_replacement(
    tmp_path: Path, relative: str
) -> None:
    _stage(tmp_path)
    target = _write(
        tmp_path, relative, "earlier line\n" + MARKER + "obsolete generated content\n"
    )
    before = target.read_bytes()
    report = run_recovery(tmp_path)
    assert (
        next(item.outcome for item in report.files if item.path == relative)
        == FileOutcome.WRITTEN
    )
    assert target.read_bytes() != before and is_generated(target.read_text())


@pytest.mark.parametrize("name", NAMES)
@pytest.mark.parametrize("kind", ["generated", "foreign", "symlink"])
def test_stale_known_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str, kind: str
) -> None:
    _stage(tmp_path)
    target = tmp_path / f"recovery/assets/recovery-{name}.svg"
    target.parent.mkdir(parents=True, exist_ok=True)
    if kind == "symlink":
        other = _write(
            tmp_path, "unrelated-target", MARKER + "owned-looking foreign target"
        )
        target.symlink_to(other)
    else:
        target.write_text((MARKER if kind == "generated" else "") + "old chart\n")
    unknowns = [
        _write(tmp_path, "recovery/assets/unrelated.svg", MARKER + "unknown svg"),
        _write(
            tmp_path,
            "recovery/assets/recovery-mystery.svg",
            MARKER + "unknown named svg",
        ),
        _write(tmp_path, "recovery/assets/notes.txt", "user note"),
    ]
    before = {path: _file_state(path) for path in [target, *unknowns]}
    unknown_reads: list[Path] = []
    original_read = Path.read_bytes
    original_text = Path.read_text

    def read(path: Path) -> bytes:
        if path in unknowns:
            unknown_reads.append(path)
        return original_read(path)

    def read_text(path: Path, *args: Any, **kwargs: Any) -> str:
        if path in unknowns:
            unknown_reads.append(path)
        return original_text(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_bytes", read)
    monkeypatch.setattr(Path, "read_text", read_text)
    monkeypatch.setattr(engine, "render_charts", lambda view: ())
    report = run_recovery(tmp_path)
    monkeypatch.setattr(Path, "read_bytes", original_read)
    monkeypatch.setattr(Path, "read_text", original_text)
    assert unknown_reads == []
    assert tuple((item.path, item.outcome) for item in report.files) == (
        (PAGE, FileOutcome.WRITTEN),
        (
            f"recovery/assets/recovery-{name}.svg",
            FileOutcome.REMOVED if kind == "generated" else FileOutcome.FOREIGN,
        ),
    )
    assert (target.exists() or target.is_symlink()) is (kind != "generated")
    assert all(path.exists() for path in unknowns)
    assert {path: _file_state(path) for path in unknowns} == {
        path: before[path] for path in unknowns
    }
    if kind != "generated":
        assert _file_state(target) == before[target]


@pytest.mark.parametrize("name", NAMES)
def test_current_chart_not_removed_and_ordered(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    _stage(tmp_path)
    _write(tmp_path, f"recovery/assets/recovery-{name}.svg", MARKER + "previous")
    monkeypatch.setattr(
        engine, "render_charts", lambda view: ((name, f"<svg>{name}</svg>"),)
    )
    report = run_recovery(tmp_path)
    assert _projection(report) == (
        (f"recovery/assets/recovery-{name}.svg", "written", None),
        (PAGE, "written", None),
    )
    assert (
        tmp_path / f"recovery/assets/recovery-{name}.svg"
    ).read_text() == MARKER + f"<svg>{name}</svg>"


def test_section_disappears_removes_chart_after_page(tmp_path: Path) -> None:
    values = _stage(tmp_path, full=True)
    run_recovery(tmp_path)
    write_series(
        tmp_path, [item for item in values if item.metric != Metric.HRV_SDNN_MS]
    )
    report = run_recovery(tmp_path)
    assert _projection(report) == tuple(
        (f"recovery/assets/recovery-{name}.svg", "unchanged", None)
        for name in NAMES
        if name != "hrv-sdnn"
    ) + (
        (PAGE, "written", None),
        ("recovery/assets/recovery-hrv-sdnn.svg", "removed", None),
    )
    assert not (tmp_path / "recovery/assets/recovery-hrv-sdnn.svg").exists()
    assert "assets/recovery-hrv-sdnn.svg" not in (tmp_path / PAGE).read_text()


@pytest.mark.parametrize("failure_at", ["tempfile", "write", "replace"])
@pytest.mark.parametrize("existing", [False, True])
def test_atomic_chart_failure_cleanup_and_page_suppression(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure_at: str, existing: bool
) -> None:
    _stage(tmp_path)
    target = tmp_path / "recovery/assets/recovery-resting-hr.svg"
    target.parent.mkdir(parents=True, exist_ok=True)
    if existing:
        target.write_text(MARKER + "old whole chart")
    page = _write(tmp_path, PAGE, MARKER + "old whole page")
    before = _file_state(target) if existing else None
    page_before = _file_state(page)
    real_temp, real_fdopen, real_replace = tempfile.mkstemp, os.fdopen, os.replace
    seen: list[tuple[str, Any]] = []

    def temp(**kwargs: Any) -> tuple[int, str]:
        seen.append(("temp", kwargs))
        if failure_at == "tempfile":
            raise PermissionError("injected tempfile refusal")
        return real_temp(**kwargs)

    class BadWriter:
        def __init__(self, handle: Any):
            self.handle = handle

        def __enter__(self) -> Any:
            self.handle.__enter__()
            return self

        def write(self, data: bytes) -> int:
            self.handle.write(data[:7])
            raise PermissionError("injected write refusal")

        def __exit__(self, *args: Any) -> Any:
            return self.handle.__exit__(*args)

    def fdopen(fd: int, *args: Any, **kwargs: Any) -> Any:
        handle = real_fdopen(fd, *args, **kwargs)
        return BadWriter(handle) if failure_at == "write" else handle

    def replace_file(source: Any, destination: Any) -> None:
        seen.append(("replace", (Path(source), Path(destination))))
        if failure_at == "replace":
            raise PermissionError("injected replace refusal")
        real_replace(source, destination)

    monkeypatch.setattr(tempfile, "mkstemp", temp)
    monkeypatch.setattr(os, "fdopen", fdopen)
    monkeypatch.setattr(os, "replace", replace_file)
    report = run_recovery(tmp_path)
    assert tuple((item.path, item.outcome, item.detail) for item in report.files) == (
        (
            "recovery/assets/recovery-resting-hr.svg",
            FileOutcome.FAILED,
            f"PermissionError: injected {failure_at} refusal",
        ),
        (PAGE, FileOutcome.FAILED, "not written because a chart failed"),
    )
    assert report.failed is True
    assert _file_state(page) == page_before
    assert (_file_state(target) if existing else target.exists()) == (
        before if existing else False
    )
    assert list(target.parent.glob(".recovery-*.tmp")) == []
    assert (
        seen[0][0],
        Path(seen[0][1]["dir"]),
        seen[0][1]["prefix"],
        seen[0][1]["suffix"],
    ) == ("temp", target.parent, ".recovery-", ".tmp")
    if failure_at == "replace":
        source, destination = seen[1][1]
        assert (
            source.parent,
            source.name.startswith(".recovery-"),
            source.suffix,
            destination,
        ) == (target.parent, True, ".tmp", target)


def test_read_only_assets_and_page_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    if os.geteuid() == 0:
        pytest.skip("root bypasses directory permissions")
    _stage(tmp_path)
    assets = tmp_path / "recovery/assets"
    assets.mkdir(parents=True)
    assets.chmod(0o500)
    try:
        report = run_recovery(tmp_path)
        assert tuple(item.outcome for item in report.files) == (
            FileOutcome.FAILED,
            FileOutcome.FAILED,
        )
        assert report.failed and not (tmp_path / PAGE).exists()
    finally:
        assets.chmod(0o700)
    original = os.replace

    def fail_page(source: Any, target: Any) -> None:
        if Path(target).name == "recovery.md":
            raise OSError("page denied")
        original(source, target)

    monkeypatch.setattr(os, "replace", fail_page)
    report = run_recovery(tmp_path)
    assert _projection(report) == (
        ("recovery/assets/recovery-resting-hr.svg", "written", None),
        (PAGE, "failed", "OSError: page denied"),
    )
    assert report.failed and not (tmp_path / PAGE).exists()
    assert list((tmp_path / "recovery").rglob(".recovery-*.tmp")) == []


def test_stale_removal_failure_reported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stage(tmp_path)
    target = _write(
        tmp_path, "recovery/assets/recovery-sleep.svg", MARKER + "old sleep"
    )
    original = Path.unlink

    def unlink(path: Path, *args: Any, **kwargs: Any) -> None:
        if path == target:
            raise OSError("stale denied")
        original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", unlink)
    report = run_recovery(tmp_path)
    assert _projection(report) == (
        ("recovery/assets/recovery-resting-hr.svg", "written", None),
        (PAGE, "written", None),
        ("recovery/assets/recovery-sleep.svg", "failed", "OSError: stale denied"),
    )
    assert report.failed and target.read_text() == MARKER + "old sleep"


def test_confinement_and_snapshot_sensitivity(tmp_path: Path) -> None:
    root = tmp_path / "athlete"
    _stage(root, full=True)
    for rel, text in (
        ("fitdocs.toml", "[history]\ncoverage_threshold = 0.0\n"),
        ("athlete.toml", 'name = "Synthetic"\n'),
        ("history/keep.md", "history note"),
        ("workouts/assets/keep.svg", "workout image"),
        ("wellness-archive/keep.bin", "archive data"),
        ("inbox/keep.json", "inbox data"),
        ("notes/note.md", "athlete note"),
        ("blocks/block.md", "training block"),
    ):
        _write(root, rel, text)
    ensure_declarations(root)
    before = _snapshot(root)
    report = run_recovery(root)
    after = _snapshot(root)
    changed = {key for key in before if after[key] != before[key]}
    added = set(after) - set(before)
    assert changed == {"recovery"}
    assert added == {
        "recovery/assets",
        PAGE,
        *(f"recovery/assets/recovery-{name}.svg" for name in NAMES),
    }
    assert len(report.files) == 7


def test_snapshot_sensitivity_controls(tmp_path: Path) -> None:
    probe = _write(tmp_path, "probe/keep", "probe contents")
    initial = _snapshot(tmp_path / "probe")
    os.utime(probe, ns=(123, 456))
    assert _snapshot(tmp_path / "probe") != initial
    initial = _snapshot(tmp_path / "probe")
    probe.chmod(stat.S_IMODE(probe.stat().st_mode) ^ stat.S_IXUSR)
    assert _snapshot(tmp_path / "probe") != initial


def test_cross_root_clock_timezone_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    roots = (tmp_path / "alpha", tmp_path / "nested" / "Beta Different")
    old_tz = os.environ.get("TZ")
    results = []
    try:
        for root, zone, timestamp in zip(
            roots,
            ("Pacific/Honolulu", "Asia/Tokyo"),
            (946684800.0, 1893456000.0),
            strict=True,
        ):
            _stage(root, full=True)
            monkeypatch.setenv("TZ", zone)
            monkeypatch.setattr(time, "time", lambda stamp=timestamp: stamp)
            if hasattr(time, "tzset"):
                time.tzset()
            report = run_recovery(root)
            results.append(
                (
                    report,
                    tuple((root / item.path).read_bytes() for item in report.files),
                )
            )
    finally:
        if old_tz is None:
            monkeypatch.delenv("TZ", raising=False)
        else:
            monkeypatch.setenv("TZ", old_tz)
        if hasattr(time, "tzset"):
            time.tzset()
    assert results[0] == results[1]
    assert len(results[0][1]) == 7 and all(results[0][1])


def test_generated_crlf_bytes_are_rewritten(tmp_path: Path) -> None:
    _stage(tmp_path)
    run_recovery(tmp_path)
    target = tmp_path / PAGE
    desired = target.read_bytes()
    target.write_bytes(desired.replace(b"\n", b"\r\n"))
    os.utime(target, ns=(456, 789))
    report = run_recovery(tmp_path)
    assert _projection(report) == (
        ("recovery/assets/recovery-resting-hr.svg", "unchanged", None),
        (PAGE, "written", None),
    )
    assert (target.read_bytes(), target.stat().st_mtime_ns != 789) == (desired, True)


def test_write_arguments_and_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "sub" / "Different Athlete"
    _stage(root)
    trace: list[tuple[Any, ...]] = []
    real_atomic = engine._atomic_write

    def declarations(data_root: Path) -> Any:
        trace.append(("declarations", data_root))
        return ensure_declarations(data_root)

    def atomic(path: Path, data: bytes) -> None:
        trace.append(("write", path, data))
        real_atomic(path, data)

    monkeypatch.setattr(engine, "ensure_declarations", declarations)
    monkeypatch.setattr(engine, "_atomic_write", atomic)
    monkeypatch.setattr(
        engine,
        "render_charts",
        lambda view: (
            ("other", "<svg>six</svg>"),
            ("resting-hr", "<svg>four</svg>"),
            ("sleep", "<svg>five</svg>"),
            ("hrv-rmssd", "<svg>three</svg>"),
            ("load", "<svg>one</svg>"),
            ("hrv-sdnn", "<svg>two</svg>"),
        ),
    )
    report = run_recovery(root)
    assert trace[:-1] == [
        ("declarations", root),
        (
            "write",
            root / "recovery/assets/recovery-load.svg",
            (MARKER + "<svg>one</svg>").encode(),
        ),
        (
            "write",
            root / "recovery/assets/recovery-hrv-sdnn.svg",
            (MARKER + "<svg>two</svg>").encode(),
        ),
        (
            "write",
            root / "recovery/assets/recovery-hrv-rmssd.svg",
            (MARKER + "<svg>three</svg>").encode(),
        ),
        (
            "write",
            root / "recovery/assets/recovery-resting-hr.svg",
            (MARKER + "<svg>four</svg>").encode(),
        ),
        (
            "write",
            root / "recovery/assets/recovery-sleep.svg",
            (MARKER + "<svg>five</svg>").encode(),
        ),
        (
            "write",
            root / "recovery/assets/recovery-other.svg",
            (MARKER + "<svg>six</svg>").encode(),
        ),
    ]
    assert (trace[-1][0], trace[-1][1]) == ("write", root / PAGE)
    assert tuple(item.path for item in report.files) == (
        "recovery/assets/recovery-load.svg",
        "recovery/assets/recovery-hrv-sdnn.svg",
        "recovery/assets/recovery-hrv-rmssd.svg",
        "recovery/assets/recovery-resting-hr.svg",
        "recovery/assets/recovery-sleep.svg",
        "recovery/assets/recovery-other.svg",
        PAGE,
    )


def test_series_only_public_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stage(tmp_path)
    forbidden = tuple(
        _write(tmp_path, rel, "unrelated private data")
        for rel in (
            "wellness-archive/private.bin",
            "inbox/private.json",
            "cache/index.duckdb",
        )
    )
    reads: list[Path] = []
    series_calls: list[Path] = []
    real_bytes, real_text = Path.read_bytes, Path.read_text

    def read_bytes(path: Path) -> bytes:
        if path in forbidden:
            reads.append(path)
        return real_bytes(path)

    def read_text(path: Path, *args: Any, **kwargs: Any) -> str:
        if path in forbidden:
            reads.append(path)
        return real_text(path, *args, **kwargs)

    def series(root: Path) -> Any:
        series_calls.append(root)
        return read_series(root)

    monkeypatch.setattr(Path, "read_bytes", read_bytes)
    monkeypatch.setattr(Path, "read_text", read_text)
    monkeypatch.setattr(engine, "read_series", series)
    report = run_recovery(tmp_path)
    assert (series_calls, reads) == ([tmp_path], [])
    assert tuple((item.path, item.outcome) for item in report.files) == (
        ("recovery/assets/recovery-resting-hr.svg", FileOutcome.WRITTEN),
        (PAGE, FileOutcome.WRITTEN),
    )


@pytest.mark.parametrize("name", ["resting-hr", "sleep"])
def test_nonregular_current_and_stale_are_foreign_without_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, name: str
) -> None:
    _stage(tmp_path)
    target = tmp_path / f"recovery/assets/recovery-{name}.svg"
    target.parent.mkdir(parents=True)
    os.mkfifo(target)
    before = target.lstat()
    attempted: list[Path] = []
    real_read = Path.read_bytes

    def guarded_read(path: Path) -> bytes:
        if path == target:
            attempted.append(path)
            return MARKER.encode() + b"FIFO guard payload"
        return real_read(path)

    monkeypatch.setattr(Path, "read_bytes", guarded_read)
    report = run_recovery(tmp_path)
    assert attempted == []
    assert tuple((item.path, item.outcome) for item in report.files) == (
        (
            ("recovery/assets/recovery-resting-hr.svg", FileOutcome.FOREIGN),
            (PAGE, FileOutcome.WRITTEN),
        )
        if name == "resting-hr"
        else (
            ("recovery/assets/recovery-resting-hr.svg", FileOutcome.WRITTEN),
            (PAGE, FileOutcome.WRITTEN),
            ("recovery/assets/recovery-sleep.svg", FileOutcome.FOREIGN),
        )
    )
    after = target.lstat()
    assert (after.st_mode, after.st_mtime_ns, after.st_ctime_ns) == (
        before.st_mode,
        before.st_mtime_ns,
        before.st_ctime_ns,
    )


@pytest.mark.parametrize("relative", [PAGE, "recovery/assets/recovery-resting-hr.svg"])
@pytest.mark.parametrize("present", [True, False], ids=["live", "dangling"])
def test_foreign_symlink_referent_preserved(
    tmp_path: Path, relative: str, present: bool
) -> None:
    root = tmp_path / "data"
    _stage(root)
    referent = tmp_path / "athlete-file"
    if present:
        referent.write_text(MARKER + "athlete's nontrivial generated-looking content")
        os.utime(referent, ns=(123456, 789012))
    link = root / relative
    link.parent.mkdir(parents=True, exist_ok=True)
    link.symlink_to(referent)
    before = (_file_state(link), _file_state(referent) if present else None)
    run_recovery(root)
    assert (
        _file_state(link),
        _file_state(referent) if referent.exists() else None,
    ) == before


def test_empty_series_does_not_call_history_reader(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_series(tmp_path, [])
    _write(tmp_path, "fitdocs.toml", "[history]\ncoverage_threshold = 0.35\n")
    calls: list[Path] = []

    def history_inputs(root: Path) -> Any:
        calls.append(root)
        return read_history_inputs(root)

    monkeypatch.setattr(engine, "read_history_inputs", history_inputs)
    run_recovery(tmp_path)
    assert calls == []


@pytest.mark.parametrize("location", ["recovery", "recovery/assets"])
def test_foreign_location_retains_full_report_metadata(
    tmp_path: Path, location: str
) -> None:
    values = _stage(tmp_path, full=True)
    write_series(tmp_path, values + [_value(Metric.RESTING_HR_BPM, 63, offset=3)])
    workout_page(tmp_path, "chosen", date(2024, 8, 20), 109, methodology="alternate")
    _write(tmp_path, location, "athlete-owned location")
    report = run_recovery(tmp_path, methodology="alternate")
    assert (
        report.as_of,
        report.window_start,
        report.methodology,
        report.note,
        report.failure,
        report.failed,
    ) == (date(2024, 8, 22), date(2024, 5, 25), "alternate", None, None, False)
    assert isinstance(report.files, tuple)


def test_normal_nonempty_report_files_are_a_tuple(tmp_path: Path) -> None:
    _stage(tmp_path, full=True)
    report = run_recovery(tmp_path)
    assert isinstance(report.files, tuple)


@pytest.mark.parametrize("failed_name", ["load", "sleep"])
def test_all_six_charts_continue_after_a_write_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failed_name: str
) -> None:
    _stage(tmp_path, full=True)
    series = read_series(tmp_path)
    computation = compute_history(read_history_inputs(tmp_path), methodology=None)
    view = cast(
        RecoveryView,
        build_view(series, Baselines.of(series), computation, panel_limit=12),
    )
    expected_charts = render_charts(view)
    page = _write(tmp_path, PAGE, MARKER + "existing whole page before chart failure\n")
    page_before = _file_state(page)
    original_replace = os.replace

    def replace(source: Any, destination: Any) -> None:
        if Path(destination).name == f"recovery-{failed_name}.svg":
            raise OSError("specific failed chart")
        original_replace(source, destination)

    monkeypatch.setattr(os, "replace", replace)
    report = run_recovery(tmp_path)
    assert (
        report.failed,
        tuple(
            (
                item.path,
                item.outcome.value,
                (
                    isinstance(item.detail, str)
                    and "specific failed chart" in item.detail
                    if item.path == f"recovery/assets/recovery-{failed_name}.svg"
                    else item.detail
                ),
            )
            for item in report.files
        ),
    ) == (
        True,
        (
            ("recovery/assets/recovery-load.svg", "failed", True)
            if failed_name == "load"
            else ("recovery/assets/recovery-load.svg", "written", None),
            ("recovery/assets/recovery-hrv-sdnn.svg", "written", None),
            ("recovery/assets/recovery-hrv-rmssd.svg", "written", None),
            ("recovery/assets/recovery-resting-hr.svg", "written", None),
            ("recovery/assets/recovery-sleep.svg", "failed", True)
            if failed_name == "sleep"
            else ("recovery/assets/recovery-sleep.svg", "written", None),
            ("recovery/assets/recovery-other.svg", "written", None),
            (PAGE, "failed", "not written because a chart failed"),
        ),
    )
    assert tuple(
        (name, (tmp_path / f"recovery/assets/recovery-{name}.svg").read_bytes())
        for name, _ in expected_charts
        if name != failed_name
    ) == tuple(
        (name, (MARKER + svg).encode())
        for name, svg in expected_charts
        if name != failed_name
    )
    assert _file_state(page) == page_before


@pytest.mark.parametrize(
    "stale,current,expected",
    [
        (
            ("load", "sleep", "other"),
            ("hrv-sdnn", "hrv-rmssd", "resting-hr"),
            (
                ("recovery/assets/recovery-hrv-sdnn.svg", "written", None),
                ("recovery/assets/recovery-hrv-rmssd.svg", "written", None),
                ("recovery/assets/recovery-resting-hr.svg", "written", None),
                (PAGE, "written", None),
                ("recovery/assets/recovery-load.svg", "removed", None),
                ("recovery/assets/recovery-sleep.svg", "removed", None),
                ("recovery/assets/recovery-other.svg", "removed", None),
            ),
        ),
        (
            ("hrv-sdnn", "hrv-rmssd", "resting-hr"),
            ("load", "sleep", "other"),
            (
                ("recovery/assets/recovery-load.svg", "written", None),
                ("recovery/assets/recovery-sleep.svg", "written", None),
                ("recovery/assets/recovery-other.svg", "written", None),
                (PAGE, "written", None),
                ("recovery/assets/recovery-hrv-sdnn.svg", "removed", None),
                ("recovery/assets/recovery-hrv-rmssd.svg", "removed", None),
                ("recovery/assets/recovery-resting-hr.svg", "removed", None),
            ),
        ),
    ],
    ids=["outer-stale", "middle-stale"],
)
def test_multiple_stale_charts_follow_normal_writes_and_page(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stale: tuple[str, ...],
    current: tuple[str, ...],
    expected: tuple[tuple[str, str, None], ...],
) -> None:
    _stage(tmp_path, full=True)
    ensure_declarations(tmp_path)
    for name in reversed(stale):
        _write(tmp_path, f"recovery/assets/recovery-{name}.svg", MARKER + f"old {name}")
    trace: list[tuple[str, str, None]] = []
    original_replace, original_unlink = os.replace, Path.unlink

    def replace(source: Any, destination: Any) -> None:
        original_replace(source, destination)
        trace.append(
            (Path(destination).relative_to(tmp_path).as_posix(), "written", None)
        )

    def unlink(path: Path, *args: Any, **kwargs: Any) -> None:
        original_unlink(path, *args, **kwargs)
        if path.name in {f"recovery-{name}.svg" for name in stale}:
            trace.append((path.relative_to(tmp_path).as_posix(), "removed", None))

    monkeypatch.setattr(
        engine,
        "render_charts",
        lambda view: tuple(
            (name, svg) for name, svg in render_charts(view) if name in current
        ),
    )
    monkeypatch.setattr(os, "replace", replace)
    monkeypatch.setattr(Path, "unlink", unlink)
    for relative, outcome, _ in expected:
        if outcome == "written":
            _write(tmp_path, relative, MARKER + f"obsolete {relative}")
    report = run_recovery(tmp_path)
    assert _projection(report) == expected
    assert tuple(trace) == expected
    assert tuple(
        (tmp_path / f"recovery/assets/recovery-{name}.svg").exists() for name in stale
    ) == (
        False,
        False,
        False,
    )
