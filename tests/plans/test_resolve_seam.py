"""The public plan read and resolution seam, against the writing pass."""

from __future__ import annotations

import shutil
from dataclasses import fields
from datetime import date
from pathlib import Path
from typing import get_type_hints

import pytest

import fitdocs.history
import fitdocs.plans.reconcile as reconcile_module
from fitdocs.history import MethodologyChoice, MethodologyProblem
from fitdocs.model import Sport
from fitdocs.plans.corpus import Corpus, LoggedWorkout, scan_corpus
from fitdocs.plans.engine import (
    BlockStatus,
    ParsedSource,
    PlanSources,
    read_plan_sources,
    run_plan,
)
from fitdocs.plans.model import Block, PlanProblem
from fitdocs.plans.placement import BlockReconciliation
from fitdocs.plans.reconcile import PlanResolution, resolve_plans, run_reconcile
from fitdocs.plans.settings import PlanSettingsError
from fitdocs.plans.source import load_block

TODAY = date(2026, 2, 24)
FULL_SOURCE = Path(__file__).parent / "fixtures" / "reconcile" / "full.toml"


def _write(root: Path, relative: str, text: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _root_with_sources(root: Path, *, invalid: bool = True) -> Path:
    _write(root, "fitdocs.toml", '[plans]\npath = "plans"\n')
    _write(root, "plans/full.toml", FULL_SOURCE.read_text(encoding="utf-8"))
    if invalid:
        _write(root, "plans/broken.toml", "this is not valid toml [[[\n")
    _write(
        root,
        "workouts/w1-mon.md",
        "\n".join(
            [
                "---",
                "title: Run",
                "type: workout",
                'date: "2026-02-02"',
                "sport: Run",
                "load_value: 73.5",
                "load_methodology: threshold",
                "---",
                "",
                "# Run",
                "",
            ]
        ),
    )
    # Existing, nontrivial declaration files are foreign and must survive.
    _write(root, "AGENTS.md", "root instruction marker\n")
    _write(root, "blocks/AGENTS.md", "block instruction marker\n")
    return root


def _tree_state(root: Path) -> dict[str, tuple[str, bytes | None, int]]:
    state: dict[str, tuple[str, bytes | None, int]] = {
        ".": ("dir", None, root.lstat().st_mtime_ns)
    }
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root).as_posix()
        info = path.lstat()
        if path.is_dir():
            state[relative] = ("dir", None, info.st_mtime_ns)
        elif path.is_file():
            state[relative] = ("file", path.read_bytes(), info.st_mtime_ns)
    return state


def _tree_bytes(root: Path) -> dict[str, bytes]:
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def test_plan_seam_carriers_have_exact_frozen_fields() -> None:
    assert tuple(field.name for field in fields(ParsedSource)) == (
        "entry",
        "source",
        "block_id",
        "block",
        "problems",
    )
    assert vars(ParsedSource)["__dataclass_params__"].frozen is True
    assert get_type_hints(ParsedSource) == {
        "entry": Path,
        "source": str,
        "block_id": str,
        "block": Block | None,
        "problems": tuple[PlanProblem, ...],
    }
    assert tuple(field.name for field in fields(PlanSources)) == (
        "source_dir",
        "present",
        "sources",
    )
    assert vars(PlanSources)["__dataclass_params__"].frozen is True
    assert get_type_hints(PlanSources) == {
        "source_dir": Path,
        "present": bool,
        "sources": tuple[ParsedSource, ...],
    }
    assert tuple(field.name for field in fields(PlanResolution)) == (
        "sources",
        "corpus",
        "methodology",
        "blocks",
    )
    assert vars(PlanResolution)["__dataclass_params__"].frozen is True
    assert get_type_hints(PlanResolution) == {
        "sources": PlanSources,
        "corpus": Corpus | None,
        "methodology": (
            fitdocs.history.MethodologyChoice
            | fitdocs.history.MethodologyProblem
            | None
        ),
        "blocks": tuple[BlockReconciliation, ...],
    }


@pytest.mark.parametrize("today", [date(2026, 2, 26), date(2026, 2, 27)])
def test_resolution_blocks_equal_the_writing_pass_on_a_copy(
    tmp_path: Path, today: date
) -> None:
    root = _root_with_sources(tmp_path / "source")
    _write(root, "plans/alpha.toml", FULL_SOURCE.read_text(encoding="utf-8"))
    before = resolve_plans(root, today=today)
    assert tuple(block.block_id for block in before.blocks) == ("alpha", "full")
    assert tuple(item.source for item in before.sources.sources) == (
        "plans/alpha.toml",
        "plans/broken.toml",
        "plans/full.toml",
    )
    assert before.sources.sources[1].block is None
    assert before.sources.sources[1].problems
    (upcoming,) = (row for row in before.blocks[0].rows if row.row_id == "w4-thu")
    if today == date(2026, 2, 26):
        assert upcoming.state.value == "upcoming"
    else:
        assert upcoming.state.value == "not logged"

    reference = tmp_path / "reference"
    shutil.copytree(root, reference)
    expected = run_reconcile(reference, today=today)
    assert tuple(block.block_id for block in expected.blocks) == ("alpha", "full")
    assert before.blocks == expected.blocks


def test_read_sources_matches_run_plan_valid_invalid_paths_and_problems(
    tmp_path: Path,
) -> None:
    root = _root_with_sources(tmp_path / "root")
    sources = read_plan_sources(root)
    assert sources.present is True
    assert sources.source_dir == root / "plans"
    assert tuple(item.source for item in sources.sources) == (
        "plans/broken.toml",
        "plans/full.toml",
    )
    assert tuple(item.entry.name for item in sources.sources) == (
        "broken.toml",
        "full.toml",
    )
    assert tuple(item.entry for item in sources.sources) == (
        root / "plans/broken.toml",
        root / "plans/full.toml",
    )
    assert tuple(item.block_id for item in sources.sources) == ("broken", "full")
    assert sources.sources[0].block is None
    invalid_source = ParsedSource(
        entry=root / "plans/broken.toml",
        source="plans/broken.toml",
        block_id="broken",
        block=None,
        problems=(
            PlanProblem(
                entry="file",
                field=None,
                message="Expected '=' after a key in a key/value pair "
                "(at line 1, column 6)",
            ),
        ),
    )
    assert sources.sources[0] == invalid_source
    assert sources.sources[1].block is not None
    valid_source = ParsedSource(
        entry=root / "plans/full.toml",
        source="plans/full.toml",
        block_id="full",
        block=load_block(root / "plans/full.toml", block_id="full"),
        problems=(),
    )
    assert sources.sources[1] == valid_source

    reference = tmp_path / "reference"
    shutil.copytree(root, reference)
    report = run_plan(reference)
    outcomes = {outcome.block_id: outcome for outcome in report.blocks}
    assert tuple(outcomes) == ("broken", "full")
    for parsed in sources.sources:
        outcome = outcomes[parsed.block_id]
        assert parsed.source == outcome.source
        assert (parsed.block is None) is (outcome.status is BlockStatus.INVALID)
        assert parsed.problems == outcome.problems

    resolution = resolve_plans(root, today=TODAY)
    assert resolution.sources == sources
    assert resolution.sources.source_dir == root / "plans"
    assert resolution.sources.present is True
    assert resolution.sources.sources == (invalid_source, valid_source)
    assert tuple(item.source for item in resolution.sources.sources) == (
        "plans/broken.toml",
        "plans/full.toml",
    )
    assert resolution.sources.sources[0].entry == root / "plans/broken.toml"
    assert resolution.sources.sources[0].block is None
    assert resolution.sources.sources[0].problems == outcomes["broken"].problems
    assert resolution.sources.sources[1].entry == root / "plans/full.toml"
    assert resolution.sources.sources[1].block == sources.sources[1].block
    assert resolution.sources.sources[1].problems == ()


def test_read_sources_distinguishes_absent_unconfigured_and_configured(
    tmp_path: Path,
) -> None:
    absent = read_plan_sources(tmp_path / "unconfigured")
    assert absent.present is False
    assert absent.sources == ()

    configured = tmp_path / "configured"
    _write(configured, "fitdocs.toml", '[plans]\npath = "missing-plans"\n')
    with pytest.raises(PlanSettingsError, match="does not exist"):
        read_plan_sources(configured)


def test_resolve_plans_preserves_the_whole_root_and_plan_pass_writes_on_copy(
    tmp_path: Path,
) -> None:
    root = _root_with_sources(tmp_path / "root")
    before = _tree_state(root)

    reference = tmp_path / "write-control"
    shutil.copytree(root, reference)
    reference_bytes_before = _tree_bytes(reference)
    written = run_plan(reference)
    assert any(outcome.status is BlockStatus.RENDERED for outcome in written.blocks)
    assert any(outcome.written for outcome in written.blocks)
    written_paths = tuple(
        reference / relative
        for outcome in written.blocks
        for relative in outcome.written
    )
    assert written_paths
    assert all(path.is_file() and path.read_bytes() for path in written_paths)
    assert _tree_bytes(reference) != reference_bytes_before

    result = resolve_plans(root, today=TODAY)
    assert tuple(item.source for item in result.sources.sources) == (
        "plans/broken.toml",
        "plans/full.toml",
    )
    assert result.sources.sources[0].entry == root / "plans/broken.toml"
    assert result.sources.sources[1].entry == root / "plans/full.toml"
    assert _tree_state(root) == before


def test_resolve_plans_returns_the_scanned_corpus_and_inferred_methodology(
    tmp_path: Path,
) -> None:
    root = _root_with_sources(tmp_path / "root")
    result = resolve_plans(root, today=TODAY)

    expected_workout = LoggedWorkout(
        stem="w1-mon",
        path="workouts/w1-mon.md",
        day=date(2026, 2, 2),
        sport=Sport.RUN,
        modality=None,
        indoor=None,
        start_time=None,
        load=73.5,
        methodology="threshold",
    )
    assert result.corpus == Corpus(workouts=(expected_workout,))
    assert result.corpus == scan_corpus(root)
    assert result.corpus.workouts == (expected_workout,)
    assert result.methodology == MethodologyChoice("threshold", "inferred", ())


def test_resolve_plans_returns_methodology_problem_when_sources_conflict(
    tmp_path: Path,
) -> None:
    root = _root_with_sources(tmp_path / "root")
    _write(
        root,
        "workouts/other-methodology.md",
        "\n".join(
            [
                "---",
                "title: Other Methodology",
                "type: workout",
                'date: "2026-02-03"',
                "sport: Ride",
                "load_value: 41.25",
                "load_methodology: banister",
                "---",
                "",
                "# Other Methodology",
                "",
            ]
        ),
    )
    result = resolve_plans(root, today=TODAY)

    assert result.methodology == MethodologyProblem(
        "the archive records more than one methodology and none was "
        "requested or configured: 'banister' (1 pages), 'threshold' (1 pages). "
        "Pass --methodology, or set [history].methodology or "
        "[load].default_calculator, to choose one."
    )
    assert result.corpus == scan_corpus(root)
    assert result.corpus is not None
    assert tuple(workout.stem for workout in result.corpus.workouts) == (
        "w1-mon",
        "other-methodology",
    )


def test_no_valid_source_never_scans_the_corpus(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = _root_with_sources(tmp_path / "root", invalid=False)
    (root / "plans/full.toml").write_text("invalid [[[\n", encoding="utf-8")
    calls = 0

    def scan_spy(data_root: Path) -> object:
        nonlocal calls
        calls += 1
        return object()

    monkeypatch.setattr(reconcile_module, "scan_corpus", scan_spy)
    result = resolve_plans(root, today=TODAY)
    assert result.corpus is None
    assert result.methodology is None
    assert result.blocks == ()
    assert calls == 0
