"""Real TAGGED overlay passed to HR and displayed by the CLI."""

from datetime import date
from pathlib import Path
from typing import Any, cast

import pytest
import tomli_w
from typer.testing import CliRunner

from fitdocs import cli
from fitdocs.benchmarks import BenchmarkKind
from fitdocs.hr_benchmarks import engine as hr
from fitdocs.hr_benchmarks.inspect import inconsistencies
from fitdocs.hr_benchmarks.types import HR_KINDS
from fitdocs.load.profile import load_profile
from fitdocs.performance.engine import derive_benchmarks
from tests.hr_benchmarks.test_engine import (
    _basic_root,
    _session_fit,
    _tree_snapshot,
    _workout_archive,
    _workout_page,
)


def _accepted_root(root: Path) -> None:
    _basic_root(root)
    ref = _workout_archive(root, _session_fit(50, duration=1800))
    page = _workout_page(root, "future-threshold.md", [ref], day="2021-02-10")
    page.write_text(page.read_text().replace("---\n", "---\neffort: hard\n", 1))
    derive_benchmarks(root)
    raw = cast(dict[str, Any], dict(load_profile(root).data))
    raw["benchmarks"]["run"]["lthr_bpm"][0]["applies_from"] = date(2021, 1, 1)
    (root / "athlete.toml").write_text(tomli_w.dumps(raw))


@pytest.mark.parametrize("dry_run", [False, True], ids=["write", "preview"])
def test_real_accepted_overlay_matches_complete_hr_timeline(
    tmp_path: Path, dry_run: bool
) -> None:
    _accepted_root(tmp_path)
    tagged = derive_benchmarks(tmp_path, dry_run=dry_run)
    assert [
        (entry.kind, entry.value, entry.measured_on, entry.applies_from)
        for entry in tagged.accepted
    ] == [(BenchmarkKind.LTHR_BPM, 50, date(2021, 2, 10), date(2021, 1, 1))]
    report = hr.derive_hr_benchmarks(
        tmp_path,
        settings=hr.load_hr_stage_settings({}, data_root=tmp_path),
        dry_run=dry_run,
        other_derived=tagged.accepted,
    )
    merged = load_profile(tmp_path).with_derived_benchmarks(
        tuple(entry for outcome in report.kinds for entry in outcome.entries),
        kinds=HR_KINDS,
        replace_applies_from=True,
    )
    actual = inconsistencies(merged.benchmarks)
    assert [
        (period.starts_on, period.lthr.applies_from if period.lthr else None)
        for period in actual
    ] == [
        (date(2021, 2, 3), date(2021, 1, 1)),
        (date(2022, 2, 1), date(2021, 1, 1)),
    ]
    assert report.inconsistencies == actual


@pytest.mark.parametrize("dry_run", [False, True], ids=["write", "preview"])
def test_cli_accepted_overlay_reports_actual_period(
    tmp_path: Path, dry_run: bool
) -> None:
    _accepted_root(tmp_path)
    before = _tree_snapshot(tmp_path)
    result = CliRunner().invoke(
        cli.app,
        [
            "derive-benchmarks",
            "--out",
            str(tmp_path),
            *(["--dry-run"] if dry_run else []),
        ],
    )
    assert (result.exit_code, result.output.count("[2021-02-03, 2022-02-01)")) == (0, 1)
    if dry_run:
        assert _tree_snapshot(tmp_path) == before
