"""The standalone recovery CLI over synthetic data roots."""

from __future__ import annotations

import ast
import inspect
import re
from datetime import date
from pathlib import Path
from typing import cast

import pytest
import typer.core
import typer.main
from typer.testing import CliRunner

from fitdocs import cli
from fitdocs.history import compute_history, read_history_inputs
from fitdocs.recovery.engine import (
    FileOutcome,
    FileResult,
    RecoveryReport,
    run_recovery,
)
from fitdocs.settings import SettingsError
from fitdocs.wellness import Metric
from tests.recovery.builders import series_value, workout_page
from tests.wellness.builders_series import write_series

runner = CliRunner()
PAGE = "recovery/recovery.md"


def _stage(root: Path) -> None:
    write_series(
        root,
        [
            series_value(
                date(2024, 8, 19),
                57,
                metric=Metric.RESTING_HR_BPM,
                source="device",
                canonical=True,
            )
        ],
    )
    workout_page(root, "older", date(2024, 8, 13), 37)
    workout_page(root, "latest", date(2024, 8, 19), 83)


def _snapshot(root: Path) -> dict[str, tuple[bytes, int]]:
    return {
        p.relative_to(root).as_posix(): (p.read_bytes(), p.stat().st_mtime_ns)
        for p in root.rglob("*")
        if p.is_file()
    }


def test_real_success_reports_window_methodology_and_files(tmp_path: Path) -> None:
    _stage(tmp_path)
    result = runner.invoke(cli.app, ["recovery", "--out", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert "2024-08-19" in result.stdout
    assert "2024-05-22" in result.stdout
    assert "threshold" in result.stdout
    for path in (
        "recovery/assets/recovery-load.svg",
        "recovery/assets/recovery-resting-hr.svg",
        PAGE,
    ):
        assert any(
            path in line and "written" in line for line in result.stdout.splitlines()
        )
        assert (tmp_path / path).is_file()


def test_unreadable_listed_series_is_failure_with_remedy(tmp_path: Path) -> None:
    _stage(tmp_path)
    (tmp_path / "wellness/2024.csv").unlink()
    before = _snapshot(tmp_path)
    result = runner.invoke(cli.app, ["recovery", "--out", str(tmp_path)])
    assert result.exit_code == 1
    assert "wellness/2024.csv" in result.stdout
    assert "fitdocs sync" in result.stdout and "fitdocs regen" in result.stdout
    assert _snapshot(tmp_path) == before


@pytest.mark.parametrize(
    "metric", [Metric.HRV_RMSSD_MS, Metric.HRV_SDNN_MS], ids=lambda m: m.value
)
def test_zero_hrv_in_series_is_unreadable_series_with_remedy(
    tmp_path: Path, metric: Metric
) -> None:
    write_series(
        tmp_path,
        [
            series_value(
                date(2024, 8, 19), 0, metric=metric, source="device", canonical=True
            )
        ],
    )
    workout_page(tmp_path, "latest", date(2024, 8, 19), 83)
    before = _snapshot(tmp_path)
    result = runner.invoke(cli.app, ["recovery", "--out", str(tmp_path)])
    assert result.exit_code == 1
    assert result.exception is None or isinstance(result.exception, SystemExit)
    assert "wellness/2024.csv:2" in result.stdout
    assert f"2024-08-19 {metric.value} 0" in result.stdout
    assert "fitdocs sync" in result.stdout and "fitdocs regen" in result.stdout
    assert _snapshot(tmp_path) == before


def test_unresolvable_root_uses_standard_guidance_without_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("FITDOCS_DATA", raising=False)
    result = runner.invoke(cli.app, ["recovery"])
    assert result.exit_code == 2
    assert all(
        token in result.stderr
        for token in ("--out", "FITDOCS_DATA", ".fitdocs/data-root")
    )
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "fault",
    ["ambiguous", "history", "load"],
)
def test_methodology_configuration_matches_history_without_writes(
    tmp_path: Path, fault: str
) -> None:
    _stage(tmp_path)
    if fault == "ambiguous":
        workout_page(
            tmp_path, "alternative", date(2024, 8, 17), 29, methodology="alternative"
        )
    else:
        (tmp_path / "fitdocs.toml").write_text(
            "[history]\ntau_fitness_days = 'bad'\n"
            if fault == "history"
            else "[load]\ndefault_calculator = 7\n"
        )
    with pytest.raises(SettingsError) as history_error:
        compute_history(read_history_inputs(tmp_path), methodology=None)
    before = _snapshot(tmp_path)
    result = runner.invoke(cli.app, ["recovery", "--out", str(tmp_path)])
    assert result.exit_code == 2
    assert str(history_error.value) in result.stderr
    assert _snapshot(tmp_path) == before


@pytest.mark.parametrize("methodology", [None, "alternate-A", "alternate-B"])
def test_explicit_root_and_methodology_reach_engine(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, methodology: str | None
) -> None:
    root = tmp_path / "Athlete chosen root"
    root.mkdir()
    other = tmp_path / "environment root"
    other.mkdir()
    monkeypatch.setenv("FITDOCS_DATA", str(other))
    calls = []

    def engine(data_root: Path, *, methodology: str | None = None) -> RecoveryReport:
        calls.append((data_root, methodology))
        return RecoveryReport(None, None, None, (), "No values.", None)

    monkeypatch.setattr(cli, "run_recovery", engine)
    args = ["recovery", "--out", str(root)]
    if methodology is not None:
        args += ["--methodology", methodology]
    result = runner.invoke(cli.app, args)
    assert result.exit_code == 0, result.output
    expected_method = {
        None: None,
        "alternate-A": "alternate-A",
        "alternate-B": "alternate-B",
    }[methodology]
    assert calls == [(tmp_path / "Athlete chosen root", expected_method)]


@pytest.mark.parametrize("selection", ["environment", "pointer"])
def test_root_fallbacks_reach_engine(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, selection: str
) -> None:
    monkeypatch.chdir(tmp_path)
    root = tmp_path / "environment choice"
    root.mkdir()
    pointer_root = tmp_path / "pointer choice"
    pointer_root.mkdir()
    pointer = tmp_path / ".fitdocs/data-root"
    pointer.parent.mkdir()
    pointer.write_text(str(pointer_root))
    monkeypatch.delenv("FITDOCS_DATA", raising=False)
    if selection == "environment":
        monkeypatch.setenv("FITDOCS_DATA", str(root))
    calls = []

    def engine(data_root: Path, *, methodology: str | None = None) -> RecoveryReport:
        calls.append(data_root)
        return RecoveryReport(None, None, None, (), "No values.", None)

    monkeypatch.setattr(cli, "run_recovery", engine)
    result = runner.invoke(cli.app, ["recovery"])
    assert result.exit_code == 0, result.output
    assert calls == [
        tmp_path
        / {"environment": "environment choice", "pointer": "pointer choice"}[selection]
    ]


REPORTS = (
    (
        "success",
        RecoveryReport(
            date(2023, 11, 29),
            date(2023, 9, 1),
            "method-zeta",
            (
                FileResult(
                    "recovery/assets/recovery-load.svg",
                    FileOutcome.WRITTEN,
                    "created-alpha",
                ),
                FileResult("recovery/recovery.md", FileOutcome.UNCHANGED, "same-beta"),
                FileResult(
                    "recovery/assets/recovery-sleep.svg",
                    FileOutcome.REMOVED,
                    "stale-gamma",
                ),
                FileResult(
                    "recovery/assets/recovery-other.svg",
                    FileOutcome.FOREIGN,
                    "athlete-delta",
                ),
            ),
            None,
            None,
        ),
        0,
        ("2023-11-29", "2023-09-01", "method-zeta"),
        (
            ("recovery/assets/recovery-load.svg", "written", "created-alpha"),
            ("recovery/recovery.md", "unchanged", "same-beta"),
            ("recovery/assets/recovery-sleep.svg", "removed", "stale-gamma"),
            ("recovery/assets/recovery-other.svg", "foreign", "athlete-delta"),
        ),
    ),
    (
        "partial",
        RecoveryReport(
            date(2022, 4, 30),
            date(2022, 1, 31),
            "method-eta",
            (
                FileResult(
                    "recovery/assets/recovery-resting-hr.svg", FileOutcome.WRITTEN, None
                ),
                FileResult(
                    "recovery/recovery.md", FileOutcome.FAILED, "disk-denied-epsilon"
                ),
            ),
            None,
            None,
        ),
        1,
        ("2022-04-30", "2022-01-31", "method-eta"),
        (
            ("recovery/assets/recovery-resting-hr.svg", "written", None),
            ("recovery/recovery.md", "failed", "disk-denied-epsilon"),
        ),
    ),
    (
        "without-load",
        RecoveryReport(
            date(2021, 8, 30),
            date(2021, 6, 2),
            None,
            (FileResult("recovery/", FileOutcome.FOREIGN, "directory-kept-kappa"),),
            None,
            None,
        ),
        0,
        ("2021-08-30", "2021-06-02"),
        (("recovery/", "foreign", "directory-kept-kappa"),),
    ),
    (
        "empty",
        RecoveryReport(None, None, None, (), "No wellness values: empty-theta.", None),
        0,
        ("No wellness values: empty-theta.",),
        (),
    ),
    (
        "unreadable",
        RecoveryReport(
            None, None, None, (), None, "series-unreadable-iota; run fitdocs regen"
        ),
        1,
        ("series-unreadable-iota; run fitdocs regen",),
        (),
    ),
)


@pytest.mark.parametrize(
    "report,exit_code,metadata,rows",
    [pytest.param(*row[1:], id=row[0]) for row in REPORTS],
)
def test_report_fields_and_failed_exit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    report: RecoveryReport,
    exit_code: int,
    metadata: tuple[str, ...],
    rows: tuple[tuple[str, str, str | None], ...],
) -> None:
    monkeypatch.setattr(cli, "run_recovery", lambda *args, **kwargs: report)
    result = runner.invoke(cli.app, ["recovery", "--out", str(tmp_path)])
    assert result.exit_code == exit_code, result.output
    assert all(value in result.stdout for value in metadata)
    if report.as_of is None:
        assert not re.search(r"\b\d{4}-\d{2}-\d{2}\b", result.stdout)
    if report.methodology is None:
        assert "threshold" not in result.stdout
    for path, outcome, detail in rows:
        assert any(
            path in line and outcome in line and (detail is None or detail in line)
            for line in result.stdout.splitlines()
        )


def _callers(source: str) -> list[str]:
    tree = ast.parse(source)
    calls: list[str] = []
    names = {"run_recovery"}
    names.update(
        alias.asname or alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module == "fitdocs.recovery.engine"
        for alias in node.names
        if alias.name == "run_recovery"
    )

    def walk(node: ast.AST, owner: str) -> None:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            owner = node.name
        if (
            isinstance(node, ast.Name)
            and isinstance(node.ctx, ast.Load)
            and node.id in names
        ) or (
            isinstance(node, ast.Attribute)
            and isinstance(node.ctx, ast.Load)
            and node.attr == "run_recovery"
        ):
            calls.append(owner)
        for child in ast.iter_child_nodes(node):
            walk(child, owner)

    walk(tree, "<module>")
    return calls


def test_only_recovery_command_calls_engine() -> None:
    source = Path(inspect.getfile(cli)).read_text()
    callers = _callers(source)
    assert callers, "No recovery calls found in actual cli.py"
    assert set(callers) == {"recovery_command"}


@pytest.mark.parametrize("owner", ["history_command", "_run_drain_passes", "<module>"])
def test_caller_guard_positive_controls(owner: str) -> None:
    source = Path(inspect.getfile(cli)).read_text()
    if owner == "<module>":
        source += "\nrun_recovery(Path('/synthetic'))\n"
    else:
        tree = ast.parse(source)
        target = next(
            n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == owner
        )
        lines = source.splitlines()
        lines.insert(
            target.body[-1].end_lineno or 0, "    run_recovery(Path('/synthetic'))"
        )
        source = "\n".join(lines)
    assert owner in _callers(source)


@pytest.mark.parametrize(
    "extra",
    [
        "_recovery_alias = run_recovery",
        "from fitdocs.recovery.engine import run_recovery as another\n"
        "another(Path('/synthetic'))",
        "import fitdocs.recovery.engine as recovery_engine\n"
        "recovery_engine.run_recovery(Path('/synthetic'))",
    ],
    ids=["assigned alias", "imported alias", "module attribute"],
)
def test_caller_guard_alias_controls(extra: str) -> None:
    source = Path(inspect.getfile(cli)).read_text()
    assert "<module>" in _callers(source + "\n" + extra + "\n")


def test_caller_guard_allows_imports_and_report_annotations() -> None:
    source = Path(inspect.getfile(cli)).read_text()
    source += (
        "\nimport fitdocs.recovery.engine as recovery_engine\n"
        "def typed(report: RecoveryReport) -> RecoveryReport:\n    return report\n"
    )
    assert _callers(source) == ["recovery_command"]


@pytest.mark.parametrize("command", ["sync", "regen", "load", "history"])
def test_other_commands_do_not_write_recovery(tmp_path: Path, command: str) -> None:
    from hashlib import sha256

    from fitdocs.wellness.archive import entry_ref
    from fitdocs.wellness.engine import rebuild_series
    from fitdocs.wellness.formats.intervals import FORMAT
    from fitdocs.wellness.settings import DEFAULT_WELLNESS_SETTINGS
    from tests.wellness.builders_intervals import intervals_list_bytes, intervals_record

    root = tmp_path / "athlete"
    payload = intervals_list_bytes([intervals_record("2024-08-19", restingHR=57)])
    archive = root / entry_ref(FORMAT, sha256(payload).hexdigest())
    archive.parent.mkdir(parents=True)
    archive.write_bytes(payload)
    rebuild_series(root, settings=DEFAULT_WELLNESS_SETTINGS, force=False)
    page = root / PAGE
    assert not page.exists()
    args = [command, "--out", str(root)]
    if command in {"sync", "load"}:
        args.append("--no-prompt")
    result = runner.invoke(cli.app, args)
    assert result.exit_code == 0, result.output
    assert not page.exists()
    report = run_recovery(root)
    assert not report.failed
    assert page.is_file()


def test_registration_options_and_plain_summary() -> None:
    group = cast(typer.core.TyperGroup, typer.main.get_command(cli.app))
    command = group.commands["recovery"]
    assert {param.name for param in command.params} == {"out", "methodology"}
    assert " ".join((cli.recovery_command.__doc__ or "").split("\n\n")[0].split()) == (
        "Regenerate the recovery page from the wellness series "
        "and the workout documents."
    )


@pytest.mark.parametrize(
    "branch,expected",
    [
        ("real", [("2024-08-19",), ("2024-05-22", "2024-08-19")]),
        ("success", [("2023-11-29",), ("2023-09-01", "2023-11-29")]),
        ("partial", [("2022-04-30",), ("2022-01-31", "2022-04-30")]),
        ("without-load", [("2021-08-30",), ("2021-06-02", "2021-08-30")]),
    ],
    ids=["real", "success", "partial", "without-load"],
)
def test_report_dates_keep_independent_roles(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    branch: str,
    expected: list[tuple[str, ...]],
) -> None:
    if branch == "real":
        _stage(tmp_path)
    else:
        report = next(row[1] for row in REPORTS if row[0] == branch)
        monkeypatch.setattr(cli, "run_recovery", lambda *args, **kwargs: report)
    result = runner.invoke(cli.app, ["recovery", "--out", str(tmp_path)])
    records = [
        tuple(re.findall(r"\b\d{4}-\d{2}-\d{2}\b", line))
        for line in result.stdout.splitlines()
        if re.search(r"\b\d{4}-\d{2}-\d{2}\b", line)
    ]
    assert sorted(records) == sorted(expected), result.stdout


@pytest.mark.parametrize("root_name", ["athlete[bold]name", "athlete:smile:"])
def test_unreadable_series_keeps_literal_root_text(
    tmp_path: Path, root_name: str
) -> None:
    root = tmp_path / root_name
    write_series(
        root,
        [
            series_value(
                date(2024, 8, 19),
                57,
                metric=Metric.RESTING_HR_BPM,
                source="device",
                canonical=True,
            )
        ],
    )
    (root / "wellness/2024.csv").unlink()
    result = runner.invoke(cli.app, ["recovery", "--out", str(root)])
    assert root_name in result.stdout, result.stdout
