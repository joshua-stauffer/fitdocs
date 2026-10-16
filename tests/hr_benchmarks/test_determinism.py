"""Discovery/environment repeatability and real-stage partition preservation."""

import copy
import json
import locale
import os
import time
from collections.abc import Callable
from datetime import UTC, date, timedelta
from pathlib import Path
from typing import Any, cast

import pytest
import tomli_w

from fitdocs import cli
from fitdocs.benchmarks import BenchmarkKind
from fitdocs.hr_benchmarks import engine as hr
from fitdocs.hr_benchmarks.types import HR_KINDS
from fitdocs.load.profile import AthleteProfile, load_profile, save_profile
from fitdocs.performance import engine as tagged
from fitdocs.performance.types import TAGGED_EFFORT_KINDS
from fitdocs.wellness import Metric, SeriesValue
from tests.hr_benchmarks.test_e2e import (
    EXPECTED_DERIVED,
    RUNNER,
    derived_identity,
    stage_root,
)
from tests.wellness.builders_series import write_series


@pytest.mark.skipif(not hasattr(time, "tzset"), reason="requires POSIX time.tzset")
def test_discovery_timezone_and_locale(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli, "_local_tz", lambda: UTC)
    control, variant = tmp_path / "control", tmp_path / "variant"
    stage_root(control)
    stage_root(variant)
    original_locale = locale.setlocale(locale.LC_ALL)
    original_tz = os.environ.get("TZ")
    real_glob = Path.glob
    discovery: list[tuple[tuple[str, ...], tuple[str, ...]]] = []

    def reverse_glob(path: Path, pattern: str) -> list[Path]:
        paths = list(real_glob(path, pattern))
        if path == variant / "workouts" and pattern == "*.md":
            reversed_paths = list(reversed(paths))
            discovery.append(
                (tuple(p.name for p in paths), tuple(p.name for p in reversed_paths))
            )
            return reversed_paths
        return paths

    try:
        locale.setlocale(locale.LC_ALL, "C")
        os.environ["TZ"] = "Etc/GMT+12"
        time.tzset()
        control_environment = (
            time.localtime(1631059200).tm_hour,
            locale.localeconv()["decimal_point"],
        )
        first = RUNNER.invoke(cli.app, ["derive-benchmarks", "--out", str(control)])
        try:
            locale.setlocale(locale.LC_ALL, "de_DE.UTF-8")
        except locale.Error:
            pytest.skip("locale de_DE.UTF-8 is not installed")
        os.environ["TZ"] = "Pacific/Kiritimati"
        time.tzset()
        variant_environment = (
            time.localtime(1631059200).tm_hour,
            locale.localeconv()["decimal_point"],
        )
        monkeypatch.setattr(Path, "glob", reverse_glob)
        second = RUNNER.invoke(cli.app, ["derive-benchmarks", "--out", str(variant)])
    finally:
        locale.setlocale(locale.LC_ALL, original_locale)
        if original_tz is None:
            os.environ.pop("TZ", None)
        else:
            os.environ["TZ"] = original_tz
        time.tzset()
    assert (
        first.exit_code,
        second.exit_code,
        control_environment,
        variant_environment,
        len(discovery),
        tuple(
            (len(before), before != after, before == after[::-1])
            for before, after in discovery
        ),
    ) == (0, 0, (12, "."), (14, ","), 2, ((8, True, True), (8, True, True)))
    assert (derived_identity(control), derived_identity(variant)) == (
        EXPECTED_DERIVED,
        EXPECTED_DERIVED,
    )
    assert (control / "athlete.toml").read_bytes() == (
        variant / "athlete.toml"
    ).read_bytes()


def _protected(root: Path, changing: frozenset[BenchmarkKind]) -> bytes:
    raw = cast(dict[str, Any], copy.deepcopy(dict(load_profile(root).data)))
    for group in raw["benchmarks"].values():
        for kind, entries in group.items():
            if kind in {item.value for item in changing}:
                group[kind] = [
                    entry
                    for entry in entries
                    if entry.get("source", {}).get("kind") != "derived"
                ]
    return json.dumps(raw, sort_keys=True, default=str).encode()


@pytest.mark.parametrize(
    "order",
    [("tagged", "hr"), ("hr", "tagged")],
    ids=["tagged-then-hr", "hr-then-tagged"],
)
def test_both_stage_orders_preserve_nonempty_partitions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, order: tuple[str, str]
) -> None:
    monkeypatch.setattr(cli, "_local_tz", lambda: UTC)
    root = tmp_path / "partitions"
    race, _, _ = stage_root(root)
    initial = RUNNER.invoke(cli.app, ["derive-benchmarks", "--out", str(root)])
    raw = cast(dict[str, Any], copy.deepcopy(dict(load_profile(root).data)))
    raw["benchmarks"]["run"]["threshold_pace_s_per_km"].insert(
        0,
        {
            "value": 333.0,
            "measured_on": date(2021, 8, 29),
            "note": "hand pace",
            "future_hand": ["hand-only", 89],
        },
    )
    for scope, group in raw["benchmarks"].items():
        for kind, entries in group.items():
            for index, entry in enumerate(entries):
                token = f"{scope}/{kind}/{index}"
                entry["future_entry"] = token
                if "source" in entry:
                    entry["source"]["future_source"] = token + "/source"
    raw["benchmarks"]["run"]["future_kind"] = [{"opaque": "future benchmark"}]
    raw["future"] = {"sentinel": "outside benchmarks", "number": 37}
    (root / "athlete.toml").write_text(tomli_w.dumps(raw))
    assert (
        initial.exit_code,
        derived_identity(root),
        _protected(root, frozenset()),
    ) == (0, EXPECTED_DERIVED, json.dumps(raw, sort_keys=True, default=str).encode())
    race.write_text(
        race.read_text().replace("effort_time_s: 2400", "effort_time_s: 2300")
    )
    write_series(
        root,
        (
            SeriesValue(
                date(2021, 8, 19) + timedelta(days=index),
                Metric.RESTING_HR_BPM,
                source,
                None,
                value,
                canonical,
            )
            for index in range(40)
            for source, value, canonical in (
                ("intervals-icu", 57, False),
                ("garmin-export", 67, True),
            )
        ),
    )
    settings = hr.load_hr_stage_settings(
        {"wellness": {"precedence": ["intervals-icu", "garmin-export"]}}, data_root=root
    )
    saves: list[str] = []
    real_save = save_profile

    def recorder(name: str) -> Callable[[Path, AthleteProfile], None]:
        def save(path: Path, profile: AthleteProfile) -> None:
            saves.append(name)
            real_save(path, profile)

        return save

    monkeypatch.setattr(hr, "save_profile", recorder("hr"))
    monkeypatch.setattr(tagged, "save_profile", recorder("tagged"))
    changing = {"hr": HR_KINDS, "tagged": TAGGED_EFFORT_KINDS}
    results = []
    for stage in order:
        before = _protected(root, changing[stage])
        saves.clear()
        report = (
            hr.derive_hr_benchmarks(root, settings=settings)
            if stage == "hr"
            else tagged.derive_benchmarks(root)
        )
        results.append(
            (
                stage,
                report.written,
                tuple(saves),
                _protected(root, changing[stage]) == before,
            )
        )
    assert results == [(stage, True, (stage,), True) for stage in order]
    path = root / "athlete.toml"
    os.utime(path, ns=(1_600_000_000_000_000_000, 1_600_000_000_000_000_000))
    before_noop = path.read_bytes(), path.stat().st_mtime_ns
    saves.clear()
    reports = [
        hr.derive_hr_benchmarks(root, settings=settings)
        if stage == "hr"
        else tagged.derive_benchmarks(root)
        for stage in order
    ]
    assert (
        tuple(report.written for report in reports),
        tuple(saves),
        path.read_bytes(),
        path.stat().st_mtime_ns,
    ) == ((False, False), (), *before_noop)
