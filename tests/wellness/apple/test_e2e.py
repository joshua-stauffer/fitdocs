"""Apple export lifecycle through CliRunner."""

from __future__ import annotations

import gzip
import importlib
import json
import re
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner, Result

from fitdocs.cli import app
from fitdocs.wellness.engine import SeriesReport, SeriesStatus
from tests.wellness._helpers import tree_snapshot
from tests.wellness.apple.builders import export_zip
from tests.wellness.apple.test_import import document, put, ref, states, values

runner = CliRunner()


@pytest.fixture(autouse=True)
def isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for name, directory in [
        ("HOME", "home"),
        ("FITDOCS_INDEX_DIR", "index"),
        ("XDG_CACHE_HOME", "cache"),
    ]:
        monkeypatch.setenv(name, str(tmp_path / directory))


def invoke(root: Path, command: str, *args: str) -> Result:
    return runner.invoke(app, [command, *args, "--out", str(root)])


def root_at(tmp_path: Path) -> Path:
    root = tmp_path / "data"
    root.mkdir()
    (root / "fitdocs.toml").write_text(
        "[inbox]\nsettle_seconds = 0\n[tiles]\nenabled = false\n"
    )
    return root


def test_cli_sync_check_regen_query(tmp_path: Path) -> None:
    root = root_at(tmp_path)
    put(root / "inbox", "export.zip", export_zip(document()))
    synced = invoke(root, "sync", "--no-prompt")
    assert synced.exit_code == 0, (synced.output, synced.exception)
    counts = {
        label.strip(): int(count)
        for label, count in re.findall(
            r"│ ([^│\n]+) │\s*(\d+) │", synced.stdout.split("└", 1)[0]
        )
    }
    assert {
        key: counts[key]
        for key in ["Wellness archived", "Wellness skipped", "Wellness failed"]
    } == {"Wellness archived": 1, "Wellness skipped": 0, "Wellness failed": 0}
    checked = invoke(root, "check")
    assert checked.exit_code == 0, (checked.output, checked.exception)
    before = tree_snapshot(root / "wellness")
    assert "2024.csv" in before and values(root) == [
        ("2024-02-02", "resting_hr_bpm", "apple-health", "apple", 53.0)
    ]
    regenerated = invoke(root, "regen")
    assert (
        regenerated.exit_code == 0 and "Wellness series:" not in regenerated.stdout
    ), (regenerated.output, regenerated.exception)
    assert tree_snapshot(root / "wellness") == before
    indexed = invoke(root, "index")
    assert indexed.exit_code == 0, (indexed.output, indexed.exception)
    queried = invoke(
        root,
        "query",
        "SELECT day, metric, source, origin, value, canonical "
        "FROM wellness_daily ORDER BY day, metric, source",
        "--format",
        "json",
    )
    assert queried.exit_code == 0, (queried.output, queried.exception)
    assert json.loads(queried.stdout)["rows"] == [
        ["2024-02-02", "resting_hr_bpm", "apple-health", "apple", 53.0, True]
    ]


def test_regen_reads_superseded_header_without_body(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = root_at(tmp_path)
    older, later = document("89", date="03"), export_zip(document("41", date="09"))
    put(root / "inbox", "older.xml", older)
    put(root / "inbox", "later.zip", later)
    synced = invoke(root, "sync", "--no-prompt")
    assert synced.exit_code == 0, (synced.output, synced.exception)
    assert states(root) == {ref(older): "superseded", ref(later): "contributed"}
    assert values(root) == [
        ("2024-02-02", "resting_hr_bpm", "apple-health", "apple", 41.0)
    ]
    entry = root / ref(older)
    header = gzip.decompress(entry.read_bytes()).splitlines(keepends=True)[0]
    corrupt = header + b"garbled record body\n"
    entry.write_bytes(gzip.compress(corrupt, mtime=0))
    assert (
        gzip.decompress(entry.read_bytes()) == corrupt
        and json.loads(header)["export_date_utc"] == "2024-02-03T22:30:00Z"
    )
    before = tree_snapshot(root / "wellness")
    reports: list[SeriesReport] = []
    module = importlib.import_module("fitdocs.cli")
    original = module.rebuild_series

    def record(*args: Any, **kwargs: Any) -> SeriesReport:
        report: SeriesReport = original(*args, **kwargs)
        reports.append(report)
        return report

    monkeypatch.setattr(module, "rebuild_series", record)
    regenerated = invoke(root, "regen")
    assert regenerated.exit_code == 0, (regenerated.output, regenerated.exception)
    assert [(report.status, report.notes) for report in reports] == [
        (SeriesStatus.UNCHANGED, ())
    ]
    assert tree_snapshot(root / "wellness") == before
