"""Synthetic Apple exports across interpreter timezones and without sockets."""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import os
import socket
import subprocess
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any, cast
from unittest.mock import Mock

import pytest

from fitdocs.wellness.engine import SeriesStatus, rebuild_series
from fitdocs.wellness.formats import apple
from fitdocs.wellness.settings import DEFAULT_WELLNESS_SETTINGS
from fitdocs.wellness.spec import ExtractContext
from tests.wellness.apple.builders import WATCH, export_document, export_zip, record_xml
from tests.wellness.apple.test_import import run_drain, values

_EXPECTED_VALUES = {
    "resting_hr_bpm": 53.0,
    "hrv_sdnn_ms": 47.2,
    "respiration_brpm": 14.3,
    "spo2_pct": 97.0,
    "vo2max_ml_per_kg_min": 51.4,
    "steps": 1234.0,
    "weight_kg": 71.25,
    "sleep_s": 12600.0,
    "sleep_deep_s": 3600.0,
    "sleep_light_s": 7200.0,
    "sleep_rem_s": 1800.0,
    "sleep_awake_s": 900.0,
}
_EXPECTED_SNAPSHOTS = [
    {
        "day": "2024-02-03",
        "covers": sorted(_EXPECTED_VALUES),
        "values": _EXPECTED_VALUES,
        "origins": {key: "apple" for key in _EXPECTED_VALUES if key != "weight_kg"},
        "revision": None,
        "ordinal": 0,
    }
]
_EXPECTED_ROWS = [
    (
        "2024-02-03",
        metric,
        "apple-health",
        None if metric == "weight_kg" else "apple",
        value,
    )
    for metric, value in sorted(_EXPECTED_VALUES.items())
]
_CHILD = """
import json
import sys
from pathlib import Path
from tests.wellness.apple.test_determinism import _produce
print(json.dumps(_produce(Path(sys.argv[1])), sort_keys=True))
"""


def _payload() -> bytes:
    watch = replace(WATCH, device="manufacturer:Apple Inc., model:Watch")
    records = []
    for kind, value, unit in [
        ("RestingHeartRate", "53", "count/min"),
        ("HeartRateVariabilitySDNN", "47.2", "ms"),
        ("RespiratoryRate", "14.3", "count/min"),
        ("OxygenSaturation", "0.97", "%"),
        ("VO2Max", "51.4", "mL/min·kg"),
        ("StepCount", "1234", "count"),
        ("BodyMass", "71.25", "kg"),
    ]:
        instant = (
            "2024-02-03 00:15:00 -0800"
            if kind
            in {"HeartRateVariabilitySDNN", "RespiratoryRate", "OxygenSaturation"}
            else "2024-02-03 23:15:00 -0800"
        )
        records.append(
            record_xml(
                "HKQuantityTypeIdentifier" + kind,
                writer=watch,
                start=instant,
                end=instant,
                value=value,
                unit=unit,
            )
        )
    for stage, start, end in [
        ("Deep", "2024-02-02 23:00:00", "2024-02-03 00:00:00"),
        ("Core", "2024-02-03 00:00:00", "2024-02-03 02:00:00"),
        ("REM", "2024-02-03 02:00:00", "2024-02-03 02:30:00"),
        ("Awake", "2024-02-03 02:30:00", "2024-02-03 02:45:00"),
    ]:
        records.append(
            record_xml(
                "HKCategoryTypeIdentifierSleepAnalysis",
                writer=watch,
                start=start + " -0800",
                end=end + " -0800",
                value="HKCategoryValueSleepAnalysis"
                + (stage if stage == "Awake" else "Asleep" + stage),
            )
        )
    return export_zip(export_document(records))


def _produce(root: Path) -> dict[str, Any]:
    inbox = root / "inbox"
    inbox.mkdir(parents=True)
    candidate = inbox / "export.zip"
    payload = _payload()
    candidate.write_bytes(payload)
    sink = io.BytesIO()
    apple.extract(
        candidate,
        sink,
        ExtractContext(hashlib.sha256(payload).hexdigest(), len(payload), None),
    )
    extracted = sink.getvalue()
    snapshots = [
        {
            "day": snapshot.day.isoformat(),
            "covers": sorted(metric.value for metric in snapshot.covers),
            "values": {
                metric.value: value for metric, value in snapshot.values.items()
            },
            "origins": {
                metric.value: origin for metric, origin in snapshot.origins.items()
            },
            "revision": snapshot.revision,
            "ordinal": snapshot.ordinal,
        }
        for snapshot in apple.parse(io.BytesIO(extracted))
    ]
    report = run_drain(inbox, root)
    if len(report.wellness_archived) != 1 or report.wellness_failures:
        raise RuntimeError(report)
    return {
        "extract": gzip.decompress(extracted).decode("utf-8"),
        "snapshots": snapshots,
        "tree": {
            path.relative_to(root / "wellness").as_posix(): path.read_bytes().hex()
            for path in (root / "wellness").rglob("*")
            if path.is_file()
        },
    }


def _child(root: Path, zone: str) -> dict[str, Any]:
    environment = {
        **os.environ,
        "TZ": zone,
        "HOME": str(root / "home"),
        "FITDOCS_INDEX_DIR": str(root / "index"),
        "XDG_CACHE_HOME": str(root / "cache"),
    }
    result = subprocess.run(
        [sys.executable, "-B", "-c", _CHILD, str(root)],
        cwd=Path(__file__).resolve().parents[3],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode:
        pytest.fail(f"child failed: {result.stdout}\n{result.stderr}")
    return cast("dict[str, Any]", json.loads(result.stdout))


def test_extract_snapshots_and_drained_tree_ignore_machine_timezone(
    tmp_path: Path,
) -> None:
    first = _child(tmp_path / "los-angeles", "America/Los_Angeles")
    second = _child(tmp_path / "auckland", "Pacific/Auckland")
    records = [json.loads(line) for line in first["extract"].splitlines()][1:-1]
    assert [(record["type"], record["value"]) for record in records] == [
        ("HKQuantityTypeIdentifierRestingHeartRate", "53"),
        ("HKQuantityTypeIdentifierHeartRateVariabilitySDNN", "47.2"),
        ("HKQuantityTypeIdentifierRespiratoryRate", "14.3"),
        ("HKQuantityTypeIdentifierOxygenSaturation", "0.97"),
        ("HKQuantityTypeIdentifierVO2Max", "51.4"),
        ("HKQuantityTypeIdentifierStepCount", "1234"),
        ("HKQuantityTypeIdentifierBodyMass", "71.25"),
        (
            "HKCategoryTypeIdentifierSleepAnalysis",
            "HKCategoryValueSleepAnalysisAsleepDeep",
        ),
        (
            "HKCategoryTypeIdentifierSleepAnalysis",
            "HKCategoryValueSleepAnalysisAsleepCore",
        ),
        (
            "HKCategoryTypeIdentifierSleepAnalysis",
            "HKCategoryValueSleepAnalysisAsleepREM",
        ),
        ("HKCategoryTypeIdentifierSleepAnalysis", "HKCategoryValueSleepAnalysisAwake"),
    ]
    assert first["extract"].encode("utf-8") == second["extract"].encode("utf-8")
    assert first["snapshots"] == _EXPECTED_SNAPSHOTS
    assert first["snapshots"] == second["snapshots"]
    assert set(first["tree"]) == {"2024.csv", "manifest.toml", "AGENTS.md"}
    assert bytes.fromhex(first["tree"]["2024.csv"]).decode("utf-8").splitlines() == [
        "day,metric,source,origin,value,canonical",
        *[
            f"2024-02-03,{metric},apple-health,{origin or ''},{value:g},true"
            for _, metric, _, origin, value in _EXPECTED_ROWS
        ],
    ]
    assert first["tree"] == second["tree"]


def test_drain_and_extract_rebuild_without_sockets(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name, directory in [
        ("HOME", "home"),
        ("FITDOCS_INDEX_DIR", "index"),
        ("XDG_CACHE_HOME", "cache"),
    ]:
        monkeypatch.setenv(name, str(tmp_path / directory))
    blocked = Mock(side_effect=RuntimeError("socket creation blocked"))
    monkeypatch.setattr(socket, "socket", blocked)
    with pytest.raises(RuntimeError, match="socket creation blocked"):
        socket.socket()
    blocked.reset_mock()
    root = tmp_path / "data"
    inbox = root / "inbox"
    inbox.mkdir(parents=True)
    candidate = inbox / "export.zip"
    candidate.write_bytes(_payload())
    report = run_drain(inbox, root)
    assert (len(report.wellness_archived), report.wellness_failures) == (1, ())
    assert values(root) == _EXPECTED_ROWS
    candidate.unlink()
    (root / "wellness/2024.csv").unlink()
    rebuilt = rebuild_series(root, settings=DEFAULT_WELLNESS_SETTINGS, force=True)
    assert rebuilt.status == SeriesStatus.REBUILT
    assert values(root) == _EXPECTED_ROWS
    blocked.assert_not_called()
