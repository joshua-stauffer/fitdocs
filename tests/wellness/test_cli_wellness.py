"""Wellness CLI settings, presentation, ordering, exits and extraction progress."""

from __future__ import annotations

import sys
from dataclasses import replace
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from typer.testing import CliRunner

from fitdocs import cli
from fitdocs.inbox import InboxNote
from fitdocs.sync import DrainReport, FileFailure, SyncReport
from fitdocs.wellness import Metric, SeriesValue, WellnessSettings, read_series
from fitdocs.wellness.engine import SeriesNote, SeriesReport, SeriesStatus
from fitdocs.wellness.intake import Identified, archive_identified, identify
from tests.wellness._helpers import (
    EXTRACT_FORMAT,
    EXTRACT_SOURCE,
    build_extract,
    tree_snapshot,
    use_formats,
)
from tests.wellness.builders_intervals import intervals_list_bytes, intervals_record
from tests.wellness.builders_series import write_series

runner = CliRunner()
_DAY = date(2029, 6, 14)
_EMPTY = SyncReport((), (), (), ())


@pytest.fixture(autouse=True)
def _postpasses(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        cli, "_run_load_pass", lambda *a, **k: SimpleNamespace(failures=())
    )
    monkeypatch.setattr(
        cli, "_run_plan_pass", lambda *a, **k: SimpleNamespace(failed=False)
    )
    monkeypatch.setattr(cli, "_run_index_pass", lambda *a, **k: None)
    monkeypatch.setattr(cli, "_run_dashboard_pass", lambda *a, **k: None)


def _root(tmp_path: Path) -> Path:
    root = tmp_path / "data"
    root.mkdir()
    (root / "fitdocs.toml").write_text(
        "[inbox]\nsettle_seconds = 0\n[tiles]\nenabled = false\n"
    )
    return root


def _report(**kwargs: Any) -> DrainReport:
    return DrainReport("synthetic-inbox", _EMPTY, (), (), (), (), **kwargs)


def _invoke(command: str, root: Path) -> Any:
    return runner.invoke(cli.app, [command, "--out", str(root)])


@pytest.mark.parametrize("command", ["sync", "regen"])
@pytest.mark.parametrize(
    ("table", "key"),
    [
        ('precedence = ["missing-source"]', "precedence[0]"),
        ('precedence = ["garmin-export", "garmin-export"]', "precedence[1]"),
        ("precedence = 13", "precedence"),
        (
            '[wellness.metric_precedence]\nmissing_metric = ["garmin-export"]',
            "metric_precedence.missing_metric",
        ),
    ],
)
def test_malformed_settings_before_writes(
    tmp_path: Path, command: str, table: str, key: str
) -> None:
    root = _root(tmp_path)
    candidate = tmp_path / "archived-wellness.json"
    candidate.write_bytes(intervals_list_bytes([intervals_record(_DAY, restingHR=47)]))
    _archive(root, candidate)
    settings = root / "fitdocs.toml"
    settings.write_text(settings.read_text() + "[wellness]\n" + table + "\n")
    (root / "sentinel.bin").write_bytes(b"existing athlete-owned bytes")
    before = tree_snapshot(root)
    dirs = {str(p.relative_to(root)) for p in root.rglob("*") if p.is_dir()}
    result = _invoke(command, root)
    assert result.exit_code == 2, result.output
    assert str(settings) in result.stderr
    assert key in result.stderr
    assert tree_snapshot(root) == before
    assert {str(p.relative_to(root)) for p in root.rglob("*") if p.is_dir()} == dirs


@pytest.mark.parametrize(
    ("field", "heading", "subject", "detail"),
    [
        ("unrecognized", "Unrecognized", "odd[7].json", "unrecognized shape [u]"),
        ("wellness_archived", "Wellness archived", "saved[8].json", "archive ref [a]"),
        ("wellness_skipped", "Wellness skipped", "held[9].json", "existing ref [s]"),
        ("wellness_failures", "Wellness failed", "broken[6].json", "parse issue [f]"),
    ],
)
def test_wellness_detail_blocks(
    capsys: pytest.CaptureFixture[str],
    field: str,
    heading: str,
    subject: str,
    detail: str,
) -> None:
    cli._report_drain(_report(**{field: (InboxNote(subject, detail),)}), command="sync")
    block = capsys.readouterr().out.partition(f"{heading}:\n")[2]
    assert block.splitlines() == [f"  {subject}", f"    {detail}"]


@pytest.mark.parametrize("command", ["sync", "regen"])
@pytest.mark.parametrize("status", list(SeriesStatus))
def test_series_summary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, command: str, status: SeriesStatus
) -> None:
    root = _root(tmp_path)
    series = SeriesReport(
        status,
        ("wellness/2029.csv", "wellness/manifest.toml"),
        ("wellness/2018.csv",),
        17,
        23,
        31,
        43,
        59,
        (SeriesNote("wellness-archive/entry[5].json", "reason [detail]"),),
    )
    monkeypatch.setattr(cli, "drain", lambda *a, **k: _report(wellness_series=series))
    monkeypatch.setattr(cli, "regen", lambda *a, **k: _EMPTY)
    monkeypatch.setattr(cli, "rebuild_series", lambda *a, **k: series, raising=False)
    result = _invoke(command, root)
    if status == SeriesStatus.UNCHANGED:
        assert "Wellness series:" not in result.stdout
    else:
        summary = result.stdout.split("Wellness series: ", 1)[1]
        assert summary.splitlines() == [
            status.value,
            "Values added: 17",
            "Values changed: 23",
            "Values removed: 31",
            "Canonical days changed: 43",
            "Conflicts: 59",
            "Series written:",
            "  wellness/2029.csv",
            "  wellness/manifest.toml",
            "Series removed:",
            "  wellness/2018.csv",
            "  wellness-archive/entry[5].json",
            "    reason [detail]",
        ]
    assert result.exit_code == (1 if status == SeriesStatus.FAILED else 0)


@pytest.mark.parametrize("failure", ["wellness", "fit", "load", "plan", "none"])
def test_drain_failure_channels(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    root = _root(tmp_path)
    report = _report(
        unrecognized=(InboxNote("unknown.json", "shape"),),
        wellness_skipped=(InboxNote("known.json", "archived"),),
        wellness_failures=(InboxNote("broken.json", "bad"),)
        if failure == "wellness"
        else (),
    )
    report = replace(
        report,
        deferred=(InboxNote("later.json", "busy"),),
        quarantined=(InboxNote("held.json", "bad SHA"),),
    )
    if failure == "fit":
        report = replace(
            report, sync=replace(_EMPTY, failures=(FileFailure("bad.fit", "CRC"),))
        )
    monkeypatch.setattr(cli, "drain", lambda *a, **k: report)
    monkeypatch.setattr(
        cli,
        "_run_load_pass",
        lambda *a, **k: SimpleNamespace(
            failures=("bad load",) if failure == "load" else ()
        ),
    )
    monkeypatch.setattr(
        cli, "_run_plan_pass", lambda *a, **k: SimpleNamespace(failed=failure == "plan")
    )
    result = _invoke("sync", root)
    assert result.exit_code == (0 if failure == "none" else 1), result.output


def _archive(root: Path, path: Path) -> None:
    identified = identify(path)
    if not isinstance(identified, Identified):
        raise AssertionError(identified)
    archive_identified(root, path, identified, None)


def test_regen_rebuilds_stale_series_before_pages(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _root(tmp_path)
    path = tmp_path / "wellness.json"
    path.write_bytes(intervals_list_bytes([intervals_record(_DAY, restingHR=47)]))
    _archive(root, path)
    write_series(
        root,
        [SeriesValue(_DAY, Metric.RESTING_HR_BPM, "intervals-icu", None, 62, True)],
    )
    assert [v.value for v in read_series(root).values] == [62]
    observed: list[float] = []

    def pages(*args: Any, **kwargs: Any) -> SyncReport:
        observed.extend(value.value for value in read_series(root).values)
        return _EMPTY

    monkeypatch.setattr(cli, "regen", pages)
    result = _invoke("regen", root)
    assert observed == [47]
    assert result.exit_code == 0, result.output
    assert "Wellness series: rebuilt" in result.stdout


def test_regen_forces_rebuild_and_passes_settings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _root(tmp_path)
    (root / "fitdocs.toml").write_text(
        '[wellness]\nprecedence = ["intervals-icu", "garmin-export"]\n'
    )
    calls: list[tuple[Path, object, bool]] = []

    def rebuild(
        data_root: Path, settings: object, *, force: bool = False
    ) -> SeriesReport:
        calls.append((data_root, settings, force))
        return SeriesReport(SeriesStatus.UNCHANGED)

    monkeypatch.setattr(cli, "rebuild_series", rebuild, raising=False)
    monkeypatch.setattr(cli, "regen", lambda *a, **k: _EMPTY)
    result = _invoke("regen", root)
    assert calls == [
        (root, WellnessSettings(("intervals-icu", "garmin-export"), {}), True)
    ]
    assert result.exit_code == 0, result.output


@pytest.mark.parametrize("tty", [False, True])
def test_extract_progress_real_drain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, tty: bool
) -> None:
    root = _root(tmp_path)
    inbox = root / "inbox"
    inbox.mkdir()
    payload = build_extract("2029-06-14")
    header, body = payload.split(b"\n", 1)
    payload = header + b"\n" + b" " * (2_000_000 - len(payload)) + body
    (inbox / "large.test-extract").write_bytes(payload)
    original_extract = EXTRACT_FORMAT.extract

    def extract(path: Path, sink: Any, context: Any) -> None:
        monkeypatch.setattr(sys.stderr, "isatty", lambda: tty)
        if original_extract is None:
            raise AssertionError("extract fixture missing")
        original_extract(path, sink, context)

    use_formats(
        monkeypatch, (replace(EXTRACT_FORMAT, extract=extract),), (EXTRACT_SOURCE,)
    )
    result = _invoke("sync", root)
    assert result.exit_code == 0, result.output
    assert len(read_series(root).values) == 1
    assert result.stderr == (
        "large.test-extract: 52%\nlarge.test-extract: 100%\n" if tty else ""
    )
    assert "large.test-extract: 100%" not in result.stdout


def test_drain_passes_wellness_settings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _root(tmp_path)
    (root / "fitdocs.toml").write_text(
        '[wellness]\nprecedence = ["intervals-icu"]\n'
        '[wellness.metric_precedence]\nweight_kg = ["garmin-export"]\n'
    )
    observed: list[object] = []

    def drain(*args: Any, **kwargs: Any) -> DrainReport:
        observed.append(kwargs.get("wellness_settings"))
        return _report()

    monkeypatch.setattr(cli, "drain", drain)
    result = _invoke("sync", root)
    assert observed == [
        WellnessSettings(("intervals-icu",), {Metric.WEIGHT_KG: ("garmin-export",)})
    ]
    assert result.exit_code == 0, result.output


@pytest.mark.parametrize("failure", ["fit", "load", "plan", "none"])
def test_regen_preserves_failure_channels(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    root = _root(tmp_path)
    monkeypatch.setattr(
        cli, "rebuild_series", lambda *a, **k: SeriesReport(SeriesStatus.UNCHANGED)
    )
    monkeypatch.setattr(
        cli,
        "regen",
        lambda *a, **k: replace(
            _EMPTY,
            failures=(FileFailure("broken.fit", "bad FIT"),)
            if failure == "fit"
            else (),
        ),
    )
    monkeypatch.setattr(
        cli,
        "_run_load_pass",
        lambda *a, **k: SimpleNamespace(
            failures=("failed load",) if failure == "load" else ()
        ),
    )
    monkeypatch.setattr(
        cli, "_run_plan_pass", lambda *a, **k: SimpleNamespace(failed=failure == "plan")
    )
    result = _invoke("regen", root)
    assert result.exit_code == (0 if failure == "none" else 1), result.output
