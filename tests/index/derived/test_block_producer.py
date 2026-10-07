"""Block producer projections stay equal to plan reconciliation."""

from __future__ import annotations

import os
import shutil
import stat
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import pytest

from fitdocs import plans
from fitdocs.index.derived import blocks as blocks_module
from fitdocs.index.derived.blocks import (
    BLOCK_PRODUCER,
    BLOCKS_TABLE,
    MESOCYCLES_TABLE,
    PLANNED_WORKOUT_PAGES_TABLE,
    PLANNED_WORKOUTS_TABLE,
    UNPLANNED_PAGES_TABLE,
)
from fitdocs.index.derived.inputs import workouts_digest
from fitdocs.index.producer import CorpusSnapshot
from fitdocs.index.schema import ColumnType
from fitdocs.layout import settings_path
from fitdocs.plans.reconcile import resolve_plans, run_reconcile
from fitdocs.settings import SettingsError
from tests.index.derived.conftest import (
    TODAY,
    _frontmatter_page,
    build_fixture_root,
    snapshot_of,
)


def _entry_inventory(root: Path) -> dict[str, tuple[str, bytes | str | None]]:
    """Capture root-relative entries without following directory symlinks."""
    inventory: dict[str, tuple[str, bytes | str | None]] = {".": ("directory", None)}

    def walk(directory: Path) -> None:
        for entry in os.scandir(directory):
            path = Path(entry.path)
            relative = path.relative_to(root).as_posix()
            if entry.is_symlink():
                inventory[relative] = ("symlink", os.readlink(path))
            elif entry.is_dir(follow_symlinks=False):
                inventory[relative] = ("directory", None)
                walk(path)
            elif entry.is_file(follow_symlinks=False):
                inventory[relative] = ("file", path.read_bytes())
            else:
                mode = path.lstat().st_mode
                kind = "special" if stat.S_IFMT(mode) else "unknown"
                inventory[relative] = (kind, None)

    walk(root)
    return inventory


def test_five_table_contracts_and_agreement_descriptions() -> None:
    assert BLOCK_PRODUCER.name == "derived.blocks"
    expected_names = (
        "blocks",
        "mesocycles",
        "planned_workouts",
        "planned_workout_pages",
        "unplanned_pages",
    )
    assert tuple(table.name for table in BLOCK_PRODUCER.tables) == expected_names
    assert BLOCK_PRODUCER.tables == (
        BLOCKS_TABLE,
        MESOCYCLES_TABLE,
        PLANNED_WORKOUTS_TABLE,
        PLANNED_WORKOUT_PAGES_TABLE,
        UNPLANNED_PAGES_TABLE,
    )
    assert all(
        actual is expected
        for actual, expected in zip(
            BLOCK_PRODUCER.tables,
            (
                BLOCKS_TABLE,
                MESOCYCLES_TABLE,
                PLANNED_WORKOUTS_TABLE,
                PLANNED_WORKOUT_PAGES_TABLE,
                UNPLANNED_PAGES_TABLE,
            ),
            strict=True,
        )
    )
    expected_columns = {
        "blocks": (
            "block_id",
            "source_path",
            "valid",
            "problems",
            "title",
            "goal",
            "starts_on",
            "ends_on",
            "mesocycle_days",
            "resolved_on",
        ),
        "mesocycles": (
            "block_id",
            "mesocycle",
            "starts_on",
            "ends_on",
            "nominal_days",
            "days",
            "target_load",
            "focus",
            "load_methodology",
            "actual_load",
            "actual_load_lower_bound",
            "actual_load_of_target_pct",
            "pages",
            "scored_pages",
            "unscored_pages",
            "excluded_pages",
            "unplanned_pages",
        ),
        "planned_workouts": (
            "block_id",
            "workout_id",
            "mesocycle",
            "day",
            "sport",
            "modality",
            "indoor",
            "title",
            "summary",
            "state",
            "confidence",
            "override_date",
            "claimed_pages",
            "missing_pages",
        ),
        "planned_workout_pages": (
            "block_id",
            "workout_id",
            "stem",
            "path",
            "page_key",
            "found",
        ),
        "unplanned_pages": ("block_id", "mesocycle", "stem", "path", "page_key"),
    }
    expected_types = {
        "blocks": (
            ColumnType.VARCHAR,
            ColumnType.VARCHAR,
            ColumnType.BOOLEAN,
            ColumnType.INTEGER,
            ColumnType.VARCHAR,
            ColumnType.VARCHAR,
            ColumnType.DATE,
            ColumnType.DATE,
            ColumnType.INTEGER,
            ColumnType.DATE,
        ),
        "mesocycles": (
            ColumnType.VARCHAR,
            ColumnType.INTEGER,
            ColumnType.DATE,
            ColumnType.DATE,
            ColumnType.INTEGER,
            ColumnType.INTEGER,
            ColumnType.DOUBLE,
            ColumnType.VARCHAR,
            ColumnType.VARCHAR,
            ColumnType.DOUBLE,
            ColumnType.BOOLEAN,
            ColumnType.INTEGER,
            ColumnType.INTEGER,
            ColumnType.INTEGER,
            ColumnType.INTEGER,
            ColumnType.INTEGER,
            ColumnType.INTEGER,
        ),
        "planned_workouts": (
            ColumnType.VARCHAR,
            ColumnType.VARCHAR,
            ColumnType.INTEGER,
            ColumnType.DATE,
            ColumnType.VARCHAR,
            ColumnType.VARCHAR,
            ColumnType.BOOLEAN,
            ColumnType.VARCHAR,
            ColumnType.VARCHAR,
            ColumnType.VARCHAR,
            ColumnType.VARCHAR,
            ColumnType.DATE,
            ColumnType.INTEGER,
            ColumnType.INTEGER,
        ),
        "planned_workout_pages": (
            ColumnType.VARCHAR,
            ColumnType.VARCHAR,
            ColumnType.VARCHAR,
            ColumnType.VARCHAR,
            ColumnType.VARCHAR,
            ColumnType.BOOLEAN,
        ),
        "unplanned_pages": (
            ColumnType.VARCHAR,
            ColumnType.INTEGER,
            ColumnType.VARCHAR,
            ColumnType.VARCHAR,
            ColumnType.VARCHAR,
        ),
    }
    for table in BLOCK_PRODUCER.tables:
        assert (
            tuple(column.name for column in table.columns)
            == expected_columns[table.name]
        )
        assert (
            tuple(column.type for column in table.columns) == expected_types[table.name]
        )
        assert table.description
        assert all(column.description for column in table.columns)
        assert "as of the last refresh" in table.description
        assert "fitdocs plan" in table.description
    column_descriptions = {
        table.name: {column.name: column.description for column in table.columns}
        for table in BLOCK_PRODUCER.tables
    }
    assert (
        "dimensionless load points" in column_descriptions["mesocycles"]["target_load"]
    )
    assert (
        "dimensionless load points" in column_descriptions["mesocycles"]["actual_load"]
    )
    assert "percent" in column_descriptions["mesocycles"]["actual_load_of_target_pct"]
    assert "days" in column_descriptions["mesocycles"]["nominal_days"]
    assert "days" in column_descriptions["mesocycles"]["days"]


def test_plan_projection_equals_reconcile_report_and_preserves_inputs(
    tmp_path: Path,
) -> None:
    root = build_fixture_root(tmp_path / "fixture")
    settings_path(root).write_text(
        settings_path(root).read_text(encoding="utf-8") + "\n", encoding="utf-8"
    )
    plan_path = root / "plans" / "derived.toml"
    plan_path.write_text(
        plan_path.read_text(encoding="utf-8").replace(
            "date = 2026-02-11", "date = 2026-02-23"
        )
        + (
            '\n[[workout]]\nid = "modality-case"\ndate = 2026-02-25\n'
            + 'sport = "Workout"\nmodality = "strength"\nindoor = true\n'
            + 'title = "Modality case"\nsummary = "Distinct summary"\n'
            + 'prescription = "UNSTORED_PRESCRIPTION_MARKER"\n'
            + '\n[[mesocycle]]\nnumber = 4\ntarget_load = 217\nfocus = "Recovery"\n'
        ),
        encoding="utf-8",
    )
    _extra_left_out = root / "workouts" / "2026-02-16-left-out-unplanned.md"
    _extra_left_out.write_text(
        _frontmatter_page(
            day="2026-02-16",
            sport="Run",
            sha=None,
            load=97,
            methodology="threshold",
        ),
        encoding="utf-8",
    )
    fractional_page = root / "workouts" / "2026-02-02-run-a.md"
    fractional_page.write_text(
        fractional_page.read_text(encoding="utf-8").replace(
            "load_value: 11", "load_value: 11.5"
        ),
        encoding="utf-8",
    )
    plan_text = plan_path.read_text(encoding="utf-8")
    assert "UNSTORED_PRESCRIPTION_MARKER" in plan_text
    assert 'prescription = "Synthetic."' in plan_text
    assert 'reason = "Synthetic override"' in plan_text
    linked_content = tmp_path / "linked-content"
    linked_content.mkdir()
    (linked_content / "outside-root.txt").write_bytes(b"outside-root")
    (root / "linked-content").symlink_to(linked_content, target_is_directory=True)
    before = _entry_inventory(root)
    assert before["linked-content"] == ("symlink", os.fspath(linked_content))
    assert "linked-content/outside-root.txt" not in before
    corpus = snapshot_of(root, today=TODAY)
    result = BLOCK_PRODUCER.rows(corpus)
    after = _entry_inventory(root)
    assert before == after
    reference_root = shutil.copytree(root, tmp_path / "reference", symlinks=True)
    reference = run_reconcile(reference_root, today=TODAY)
    resolution = resolve_plans(reference_root, today=TODAY)
    assert resolution.blocks == reference.blocks
    parsed_sources = {source.block_id: source for source in resolution.sources.sources}

    assert set(result) == {table.name for table in BLOCK_PRODUCER.tables}
    blocks = result["blocks"]
    assert len(blocks) == 2
    valid = next(row for row in blocks if row[0] == "derived")
    invalid = next(row for row in blocks if row[0] == "invalid")
    invalid_reference = next(
        outcome for outcome in reference.plan.blocks if outcome.block_id == "invalid"
    )
    assert valid[2] is True and valid[9] == TODAY
    valid_block = parsed_sources["derived"].block
    assert valid_block is not None
    assert valid_block.goal
    assert valid_block.mesocycles[-1].days != valid_block.mesocycles[-1].nominal_days
    assert valid == (
        "derived",
        parsed_sources["derived"].source,
        True,
        len(reference.blocks[0].problems),
        valid_block.title,
        valid_block.goal,
        valid_block.starts,
        valid_block.ends,
        valid_block.mesocycle_days,
        TODAY,
    )
    assert invalid[2] is False
    assert invalid[3] == len(invalid_reference.problems)
    assert invalid[4:9] == (None,) * 5
    invalid_source = parsed_sources["invalid"]
    assert invalid == (
        "invalid",
        invalid_source.source,
        False,
        len(invalid_source.problems),
        None,
        None,
        None,
        None,
        None,
        TODAY,
    )
    for table_name in (
        "mesocycles",
        "planned_workouts",
        "planned_workout_pages",
        "unplanned_pages",
    ):
        assert not any(row[0] == "invalid" for row in result[table_name])
    assert all(row[9] == TODAY for row in blocks)
    assert len(result["mesocycles"]) == len(reference.blocks[0].mesocycles)

    planned = {}
    planned_rows = result["planned_workouts"]
    for row in planned_rows:
        workout_id = row[1]
        assert isinstance(workout_id, str)
        planned[workout_id] = row
    expected_outcomes = {
        outcome.row_id: outcome for outcome in reference.blocks[0].rows
    }
    assert len(planned_rows) == len(expected_outcomes)
    assert len(planned) == len(planned_rows)
    assert set(planned) == set(expected_outcomes)
    assert {row[9] for row in planned.values()} == {
        "matched",
        "overridden",
        "skipped",
        "not logged",
        "upcoming",
    }
    assert {row[10] for row in planned.values() if row[10] is not None} == {
        "exact",
        "absorbed",
        "ambiguous",
    }
    assert planned["modality-case"][5:7] == ("strength", True)
    assert planned["exact"][5:7] == (None, None)
    assert expected_outcomes["override"].missing == ("missing-override-stem",)
    for workout_id, output in planned.items():
        outcome = expected_outcomes[workout_id]
        assert (output[9], output[10], output[11]) == (
            outcome.state.value,
            outcome.confidence.value if outcome.confidence is not None else None,
            outcome.override_date,
        )
        assert output[12:] == (len(outcome.stems), len(outcome.missing))
    assert planned["upcoming"][3] == TODAY
    assert planned["not-logged"][3] == TODAY - timedelta(days=1)
    assert planned["not-logged"][9] == "not logged"

    reference_mesocycles = reference.blocks[0].mesocycles
    assert resolution.corpus is not None
    assert any(cycle.total is not None for cycle in reference_mesocycles)
    assert any(cycle.unplanned for cycle in reference_mesocycles)
    assert any(cycle.unscored for cycle in reference_mesocycles)
    assert any(cycle.excluded for cycle in reference_mesocycles)
    assert any(cycle.lower_bound for cycle in reference_mesocycles)
    assert any(not cycle.lower_bound for cycle in reference_mesocycles)
    assert any(
        cycle.target is not None and cycle.target for cycle in reference_mesocycles
    )
    assert any(cycle.target is None for cycle in reference_mesocycles)
    assert any(cycle.focus is not None for cycle in valid_block.mesocycles)
    assert any(cycle.focus is None for cycle in valid_block.mesocycles)
    assert any(
        cycle.target is not None and cycle.total is None
        for cycle in reference_mesocycles
    )
    assert any(
        cycle.total is not None and cycle.total % 1 != 0
        for cycle in reference_mesocycles
    )
    for actual, expected, planned_cycle in zip(
        result["mesocycles"],
        reference_mesocycles,
        valid_block.mesocycles,
        strict=True,
    ):
        assert actual[:8] == (
            "derived",
            expected.number,
            planned_cycle.starts,
            planned_cycle.ends,
            planned_cycle.nominal_days,
            planned_cycle.days,
            planned_cycle.target_load,
            planned_cycle.focus,
        )
    assert len(result["mesocycles"]) == len(reference_mesocycles)
    for actual, expected in zip(
        result["mesocycles"], reference_mesocycles, strict=True
    ):
        assert actual[0:2] == ("derived", expected.number)
        assert actual[8:17] == (
            expected.methodology,
            expected.total,
            expected.lower_bound,
            expected.percent_of_target,
            len(expected.pages),
            len(expected.scored),
            len(expected.unscored),
            len(expected.excluded),
            len(expected.unplanned),
        )

    expected_claim_rows: list[tuple[str, str, str, str | None, str | None, bool]] = []
    for workout_id, outcome in expected_outcomes.items():
        planned_workout = next(
            workout
            for mesocycle in valid_block.mesocycles
            for workout in mesocycle.workouts
            if workout.id == workout_id
        )
        assert planned[workout_id][:9] == (
            "derived",
            planned_workout.id,
            valid_block.mesocycle_of(planned_workout.date),
            planned_workout.date,
            str(planned_workout.sport),
            str(planned_workout.modality)
            if planned_workout.modality is not None
            else None,
            planned_workout.indoor,
            planned_workout.title,
            planned_workout.summary,
        )
        for stem in outcome.stems:
            logged = resolution.corpus.by_stem(stem)
            assert logged is not None
            page_row = next(
                row
                for row in result["planned_workout_pages"]
                if row[1:3] == (workout_id, stem)
            )
            assert page_row == (
                "derived",
                workout_id,
                stem,
                logged.path,
                dict((page.path, page.page_key) for page in corpus.pages).get(
                    logged.path
                ),
                True,
            )
            expected_claim_rows.append(
                (
                    "derived",
                    workout_id,
                    stem,
                    logged.path,
                    dict((page.path, page.page_key) for page in corpus.pages).get(
                        logged.path
                    ),
                    True,
                )
            )
        for stem in outcome.missing:
            missing_page_row = (
                "derived",
                workout_id,
                stem,
                None,
                None,
                False,
            )
            assert missing_page_row in result["planned_workout_pages"]
            expected_claim_rows.append(missing_page_row)
    assert len(result["planned_workout_pages"]) == len(expected_claim_rows)
    assert len(set(result["planned_workout_pages"])) == len(
        result["planned_workout_pages"]
    )
    assert sorted(result["planned_workout_pages"]) == sorted(expected_claim_rows)

    no_sources = next(
        row
        for row in result["planned_workout_pages"]
        if row[2] == "2026-02-14-left-out"
    )
    assert any(
        item.path == "workouts/2026-02-14-left-out.md" for item in corpus.left_out
    )
    assert planned["no-sources-match"][9] == "matched"
    assert (
        no_sources[3] == "workouts/2026-02-14-left-out.md"
        and no_sources[4] is None
        and no_sources[5] is True
    )
    assert planned["upcoming"][9] == "upcoming"
    assert planned["not-logged"][9] == "not logged"
    expected_unplanned = [
        (
            "derived",
            mesocycle.number,
            page.stem,
            page.path,
            dict((item.path, item.page_key) for item in corpus.pages).get(page.path),
        )
        for mesocycle in reference_mesocycles
        for page in mesocycle.unplanned
    ]
    assert len(result["unplanned_pages"]) == len(expected_unplanned)
    assert len(set(result["unplanned_pages"])) == len(result["unplanned_pages"])
    assert sorted(result["unplanned_pages"]) == sorted(expected_unplanned)
    assert {row[:4] for row in result["unplanned_pages"]} == {
        row[:4] for row in expected_unplanned
    }
    left_out_unplanned = next(
        item for item in corpus.left_out if item.path.endswith("left-out-unplanned.md")
    )
    assert left_out_unplanned.path == "workouts/2026-02-16-left-out-unplanned.md"
    owning_unplanned = next(
        page
        for cycle in reference_mesocycles
        for page in cycle.unplanned
        if page.path == left_out_unplanned.path
    )
    assert owning_unplanned.load == 97
    assert any(
        page.path == left_out_unplanned.path
        for cycle in reference_mesocycles
        for page in cycle.unplanned
    )
    left_out_row = next(
        row for row in result["unplanned_pages"] if row[3] == left_out_unplanned.path
    )
    assert left_out_row[4] is None
    page_key_by_path = {page.path: page.page_key for page in corpus.pages}
    for row in result["unplanned_pages"]:
        path = row[3]
        assert isinstance(path, str)
        assert row[4] == page_key_by_path.get(path)
    flat = repr(tuple(result.values()))
    assert "Synthetic." not in flat
    assert "Synthetic override" not in flat
    assert "UNSTORED_PRESCRIPTION_MARKER" not in flat


def test_no_plan_sources_returns_all_five_empty_tables(tmp_path: Path) -> None:
    root = build_fixture_root(tmp_path / "fixture")
    (root / "plans" / "derived.toml").unlink()
    (root / "plans" / "invalid.toml").unlink()
    result = BLOCK_PRODUCER.rows(snapshot_of(root, today=TODAY))
    assert result == {table.name: () for table in BLOCK_PRODUCER.tables}


def test_fingerprint_tracks_date_sources_settings_workouts_and_held_keys(
    tmp_path: Path,
) -> None:
    root = build_fixture_root(tmp_path / "fixture")
    original = snapshot_of(root, today=TODAY)
    initial = BLOCK_PRODUCER.fingerprint(original)
    later = CorpusSnapshot(
        original.data_root,
        original.pages,
        original.left_out,
        TODAY + timedelta(days=1),
        original.athlete_fingerprint,
    )
    assert initial != BLOCK_PRODUCER.fingerprint(later)
    workout = root / "workouts" / "2026-02-02-run-a.md"
    workout.write_text(workout.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    changed_workout = snapshot_of(root, today=TODAY)
    assert initial != BLOCK_PRODUCER.fingerprint(changed_workout)
    changed_plan = root / "plans" / "derived.toml"
    before_plan_change = BLOCK_PRODUCER.fingerprint(changed_workout)
    changed_plan.write_text(
        changed_plan.read_text(encoding="utf-8") + "\n", encoding="utf-8"
    )
    assert before_plan_change != BLOCK_PRODUCER.fingerprint(
        snapshot_of(root, today=TODAY)
    )
    changed_settings = settings_path(root)
    before_settings_change = BLOCK_PRODUCER.fingerprint(snapshot_of(root, today=TODAY))
    changed_settings.write_text(
        changed_settings.read_text(encoding="utf-8") + "\n", encoding="utf-8"
    )
    assert before_settings_change != BLOCK_PRODUCER.fingerprint(
        snapshot_of(root, today=TODAY)
    )
    no_sources = build_fixture_root(tmp_path / "no-plans")
    (no_sources / "plans" / "derived.toml").unlink()
    (no_sources / "plans" / "invalid.toml").unlink()
    empty_today = snapshot_of(no_sources, today=TODAY)
    empty_later = CorpusSnapshot(
        empty_today.data_root,
        empty_today.pages,
        empty_today.left_out,
        TODAY + timedelta(days=1),
        empty_today.athlete_fingerprint,
    )
    assert BLOCK_PRODUCER.fingerprint(empty_today) == BLOCK_PRODUCER.fingerprint(
        empty_later
    )
    invalid_only = build_fixture_root(tmp_path / "invalid-only")
    (invalid_only / "plans" / "derived.toml").unlink()
    invalid_today = snapshot_of(invalid_only, today=TODAY)
    invalid_later = CorpusSnapshot(
        invalid_today.data_root,
        invalid_today.pages,
        invalid_today.left_out,
        TODAY + timedelta(days=1),
        invalid_today.athlete_fingerprint,
    )
    assert BLOCK_PRODUCER.fingerprint(invalid_today) != BLOCK_PRODUCER.fingerprint(
        invalid_later
    )

    # The same page is held in the first snapshot and left out in the second.
    page = next(
        page for page in original.pages if page.path.endswith("2026-02-02-run-a.md")
    )
    assert page.path in {item.path for item in original.pages}
    left_out = tuple(original.left_out) + (
        type(original.left_out[0])(page.path, page.document_fingerprint),
    )
    pages = tuple(item for item in original.pages if item.path != page.path)
    held_transition = CorpusSnapshot(
        original.data_root,
        pages,
        left_out,
        original.today,
        original.athlete_fingerprint,
    )
    assert page.path not in {item.path for item in held_transition.pages}
    assert page.path in {item.path for item in held_transition.left_out}
    assert workouts_digest(original) == workouts_digest(held_transition)
    held_rows_before = BLOCK_PRODUCER.rows(original)["planned_workout_pages"]
    held_rows_after = BLOCK_PRODUCER.rows(held_transition)["planned_workout_pages"]
    assert any(
        row[2] == page.path.removeprefix("workouts/").removesuffix(".md")
        and row[4] is not None
        for row in held_rows_before
    )
    assert any(
        row[2] == page.path.removeprefix("workouts/").removesuffix(".md")
        and row[4] is None
        for row in held_rows_after
    )
    assert BLOCK_PRODUCER.fingerprint(original) != BLOCK_PRODUCER.fingerprint(
        held_transition
    )


def test_malformed_settings_return_an_error_marker_fingerprint(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = build_fixture_root(tmp_path / "fixture")
    corpus = snapshot_of(root, today=TODAY)
    (root / "fitdocs.toml").write_text("[history\n", encoding="utf-8")
    malformed = CorpusSnapshot(
        corpus.data_root,
        corpus.pages,
        corpus.left_out,
        corpus.today,
        corpus.athlete_fingerprint,
    )
    with pytest.raises(SettingsError) as owning_error:
        resolve_plans(root, today=TODAY)
    expected_marker = f"error:{type(owning_error.value).__name__}: {owning_error.value}"
    captured: dict[str, object] = {}

    def capture(parts: object) -> str:
        assert isinstance(parts, dict)
        captured.update(parts)
        return "captured-digest"

    monkeypatch.setattr(blocks_module, "digest", capture)
    assert BLOCK_PRODUCER.fingerprint(malformed) == "captured-digest"
    plan_marker = captured["plans"]
    assert isinstance(plan_marker, str)
    assert plan_marker == expected_marker


def test_missing_outcome_and_mismatched_mesocycle_raise(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = build_fixture_root(tmp_path / "fixture")
    corpus = snapshot_of(root, today=TODAY)
    resolution = resolve_plans(root, today=TODAY)
    reconciliation = resolution.blocks[0]
    with pytest.raises(ValueError, match="missing outcome"):
        incomplete = replace(
            reconciliation,
            rows=tuple(row for row in reconciliation.rows if row.row_id != "exact"),
        )
        monkeypatch.setattr(
            plans,
            "resolve_plans",
            lambda _root, *, today: replace(resolution, blocks=(incomplete,)),
        )
        BLOCK_PRODUCER.rows(corpus)

    cycles = tuple(
        replace(cycle, number=999) if index == 0 else cycle
        for index, cycle in enumerate(reconciliation.mesocycles)
    )
    inconsistent = replace(reconciliation, mesocycles=cycles)
    monkeypatch.setattr(
        plans,
        "resolve_plans",
        lambda _root, *, today: replace(resolution, blocks=(inconsistent,)),
    )
    with pytest.raises(ValueError, match="mesocycle numbers differ"):
        BLOCK_PRODUCER.rows(corpus)
