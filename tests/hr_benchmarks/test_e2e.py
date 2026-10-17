"""Synthetic CLI flow from FIT intake to dated heart-rate load."""

import copy
import os
from datetime import UTC, date, timedelta
from pathlib import Path
from typing import Any, cast

import pytest
import tomli_w
from typer.testing import CliRunner

from fitdocs import cli
from fitdocs.benchmarks import Benchmark, BenchmarkKind, benchmarks_to_document
from fitdocs.load.docedit import classify_load_region
from fitdocs.load.profile import AthleteProfile, load_profile, save_profile
from fitdocs.load.render import LoadPayload
from fitdocs.load.types import LoadResult
from fitdocs.model import Sport
from fitdocs.wellness import Metric, SeriesValue
from tests.fixtures import builder
from tests.hr_benchmarks.builders import hand_benchmark
from tests.wellness.builders_series import write_series

RUNNER = CliRunner()


def _fit(day: date, peak: int, serial: int, sport: str) -> bytes:
    start = builder.FIT_TIMESTAMP_BASE + (day - date(2021, 9, 8)).days * 86400
    records: list[dict[str, object]] = [
        {
            "mesg_num": 20,
            "timestamp": start + t,
            "heart_rate": peak,
            "distance": float(t * 3),
            "enhanced_speed": 3.0,
        }
        for t in range(0, 601, 5)
    ]
    return builder.encode(
        [
            {
                "mesg_num": 0,
                "type": "activity",
                "manufacturer": "garmin",
                "product": 1,
                "serial_number": serial,
                "time_created": start,
            },
            {"mesg_num": 12, "sport": sport, "sub_sport": "generic"},
            *records,
            {
                "mesg_num": 18,
                "sport": sport,
                "sub_sport": "generic",
                "start_time": start,
                "timestamp": start + 600,
                "total_elapsed_time": 600.0,
                "total_timer_time": 600.0,
                "total_distance": 1800.0,
                "avg_heart_rate": peak,
                "max_heart_rate": peak,
            },
            {
                "mesg_num": 34,
                "timestamp": start + 600,
                "total_timer_time": 600.0,
                "num_sessions": 1,
                "type": "manual",
            },
        ]
    )


def stage_root(root: Path) -> tuple[Path, Path, int]:
    """Sync FIT inputs, then stage the hand profile and normalized series."""
    root.mkdir(parents=True)
    (root / "inbox").mkdir()
    (root / "fitdocs.toml").write_text(
        '[load]\ndefault_calculator = "threshold"\n'
        '[wellness]\nprecedence = ["intervals-icu", "garmin-export"]\n'
    )
    for index, (day, peak, sport) in enumerate(
        [
            (date(2021, 9, 1), 181, "running"),
            (date(2021, 9, 2), 193, "running"),
            (date(2021, 9, 3), 187, "running"),
            (date(2021, 9, 5), 123, "walking"),
            (date(2022, 10, 1), 199, "running"),
            (date(2022, 10, 2), 191, "running"),
            (date(2022, 10, 3), 195, "running"),
        ]
    ):
        (root / "inbox" / f"synthetic-{index}.fit").write_bytes(
            _fit(day, peak, 5100 + index, sport)
        )
    synced = RUNNER.invoke(cli.app, ["sync", "--out", str(root), "--no-prompt"])
    race = next((root / "workouts").glob("2021-09-02-*.md"))
    race.write_text(
        race.read_text().replace(
            "---\n",
            "---\neffort: race\neffort_distance_m: 10000\neffort_time_s: 2400\n",
            1,
        )
    )
    hand = [
        hand_benchmark(
            BenchmarkKind.MAX_HR_BPM,
            date(2022, 9, 10),
            179,
            applies_from=date(2021, 8, 1),
            note="hand max",
        ),
        hand_benchmark(
            BenchmarkKind.RESTING_HR_BPM, date(2021, 8, 1), 48, note="hand rest"
        ),
        hand_benchmark(
            BenchmarkKind.LTHR_BPM,
            date(2021, 8, 30),
            171,
            discipline=Sport.RUN,
            note="hand run threshold",
        ),
    ]
    document = benchmarks_to_document(hand)
    document["future"] = {"sentinel": "outside benchmarks", "number": 37}
    (root / "athlete.toml").write_text(tomli_w.dumps(document))
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
                ("intervals-icu", 53, False),
                ("garmin-export", 67, True),
            )
        ),
    )
    walk = next((root / "workouts").glob("2021-09-05-*.md"))
    return race, walk, synced.exit_code


def derived_identity(root: Path) -> tuple[tuple[object, ...], ...]:
    return tuple(
        sorted(
            (
                entry.kind.value,
                entry.discipline.value if entry.discipline else None,
                entry.value,
                entry.measured_on.isoformat(),
                entry.applies_from,
                entry.source.kind.value,
                entry.source.document,
                entry.source.series,
            )
            for entry in load_profile(root).benchmarks.entries
            if entry.source is not None and entry.source.is_derived
        )
    )


EXPECTED_DERIVED = (
    (
        "max_hr_bpm",
        None,
        195,
        "2022-10-03",
        None,
        "derived",
        "workouts/2022-10-03-run-0146.md",
        None,
    ),
    (
        "resting_hr_bpm",
        None,
        53,
        "2021-09-01",
        None,
        "derived",
        "wellness/2021.csv",
        "intervals-icu:resting_hr_bpm",
    ),
    (
        "threshold_pace_s_per_km",
        "Run",
        245.5719006069221,
        "2021-09-02",
        None,
        "derived",
        "workouts/2021-09-02-run-0146.md",
        None,
    ),
)


def walk_result(walk: Path) -> LoadResult:
    return cast(
        LoadResult,
        cast(LoadPayload, classify_load_region(walk.read_text()).payload).result,
    )


def _input_dates(result: LoadResult) -> tuple[tuple[str, str], ...]:
    return tuple(
        (key, value)
        for key, value in result.inputs_used
        if key.endswith("_bpm") or key.endswith("_measured_on")
    )


def test_cli_history_takeover_and_recompute(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(cli, "_local_tz", lambda: UTC)
    root = tmp_path / "flow"
    race, walk, sync_exit = stage_root(root)
    baseline = RUNNER.invoke(
        cli.app, ["load", "--out", str(root), "--recompute", "--no-prompt"]
    )
    old_result = walk_result(walk)
    old_walk = walk.read_bytes()
    assert (
        sync_exit,
        baseline.exit_code,
        len(tuple((root / "workouts").glob("20*.md"))),
        derived_identity(root),
        _input_dates(old_result),
    ) == (
        0,
        0,
        7,
        (),
        (
            ("lthr_bpm", "171"),
            ("resting_hr_bpm", "48"),
            ("max_hr_bpm", "179"),
            ("lthr_measured_on", "2021-08-30"),
            ("resting_hr_measured_on", "2021-08-01"),
            ("max_hr_measured_on", "2022-09-10"),
        ),
    )
    hand_before = tuple(entry for entry in load_profile(root).benchmarks.entries)
    first = RUNNER.invoke(cli.app, ["derive-benchmarks", "--out", str(root)])
    assert (
        first.exit_code,
        derived_identity(root),
        walk.read_bytes(),
        tuple(
            entry
            for entry in load_profile(root).benchmarks.entries
            if entry.source is None
        ),
    ) == (0, EXPECTED_DERIVED, old_walk, hand_before)
    max_lines = tuple(
        line
        for line in first.stdout.splitlines()
        if line.startswith("Takeover max_hr_bpm:")
    )
    assert max_lines == (
        "Takeover max_hr_bpm: 195 bpm measured 2022-10-03 (derived) supersedes your "
        "179 bpm measured 2022-09-10 (hand-recorded; applies from 2021-08-01); "
        "applied by measurement; method=max_hr_sustained_peak; "
        "document=workouts/2022-10-03-run-0146.md; inputs=median of the three highest "
        "30-second sustained peaks (199.0, 195.0, 191.0 bpm) among 3 sessions dated "
        "2022-09-11 to 2022-10-03; citation=max_hr_timeline_choice; series=none",
    )
    assert (
        first.stdout.count("Profile written: yes"),
        first.stdout.count("Heart-rate benchmarks written: yes"),
        first.stdout.count("Back-reach max_hr_bpm:"),
        first.stdout.count(
            "before [2021-08-01, 2022-09-10); after [2021-08-01, 2021-09-03)"
        ),
        first.stdout.count("The heart-rate timeline changed:"),
        race.name in first.stdout,
    ) == (1, 1, 0, 0, 1, True)
    profile_path = root / "athlete.toml"
    os.utime(profile_path, ns=(1_600_000_000_000_000_000, 1_600_000_000_000_000_000))
    stable = profile_path.read_bytes(), profile_path.stat().st_mtime_ns
    second = RUNNER.invoke(cli.app, ["derive-benchmarks", "--out", str(root)])
    assert (
        second.exit_code,
        profile_path.read_bytes(),
        profile_path.stat().st_mtime_ns,
        second.stdout.count("Takeover "),
        second.stdout.count("Back-reach "),
        second.stdout.count("The heart-rate timeline changed:"),
        second.stdout.count("Profile written: no"),
        second.stdout.count("Heart-rate benchmarks written: no"),
    ) == (0, *stable, 0, 0, 0, 1, 1)
    checked = RUNNER.invoke(cli.app, ["check", "--out", str(root)])
    max_findings = tuple(
        line.strip()
        for line in checked.stdout.splitlines()
        if line.strip().startswith("max_hr_bpm:")
    )
    assert (
        max_findings,
        "record a new max_hr_bpm entry by hand" in checked.stdout,
        "to accept the derived value, leave it" in checked.stdout,
    ) == (
        (
            "max_hr_bpm: derived 195 bpm from 2022-10-03 takes over from your "
            "hand-recorded 179 bpm of 2022-09-10 (applied by measurement date); "
            "evidence: median of the three highest 30-second sustained peaks "
            "(199.0, 195.0, 191.0 bpm) among 3 sessions dated 2022-09-11 to "
            "2022-10-03; document: workouts/2022-10-03-run-0146.md",
        ),
        True,
        True,
    )
    raw = cast(dict[str, Any], copy.deepcopy(dict(load_profile(root).data)))
    raw["benchmarks"]["athlete"]["max_hr_bpm"].append(
        {"value": 201, "measured_on": date(2022, 10, 20), "note": "later hand"}
    )
    save_profile(root, AthleteProfile(raw))
    later = RUNNER.invoke(cli.app, ["check", "--out", str(root)])
    applicable = cast(
        Benchmark,
        load_profile(root).benchmarks.applicable(
            BenchmarkKind.MAX_HR_BPM, discipline=None, on=date(2022, 10, 20)
        ),
    )
    assert (
        "max_hr_bpm: derived" in later.stdout,
        applicable.value,
        applicable.measured_on,
        derived_identity(root),
    ) == (False, 201, date(2022, 10, 20), EXPECTED_DERIVED)
    before_load = profile_path.read_bytes()
    scored = RUNNER.invoke(
        cli.app, ["load", "--out", str(root), "--recompute", "--no-prompt"]
    )
    result = walk_result(walk)
    assert (
        scored.exit_code,
        result.calculator_id,
        result.basis,
        _input_dates(result),
        (round(old_result.value, 9), round(result.value, 9)),
        profile_path.read_bytes(),
    ) == (
        0,
        "threshold",
        "heart_rate",
        (
            ("lthr_bpm", "171"),
            ("resting_hr_bpm", "53"),
            ("max_hr_bpm", "179"),
            ("lthr_measured_on", "2021-08-30"),
            ("resting_hr_measured_on", "2021-09-01"),
            ("max_hr_measured_on", "2022-09-10"),
        ),
        (5.028908812, 4.757835143),
        before_load,
    )
