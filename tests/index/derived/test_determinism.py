"""Integration checks for derived rows across index refresh routes."""

from __future__ import annotations

import shutil
from pathlib import Path

from tests.index.derived.conftest import (
    TODAY,
    build_fixture_root,
    build_index,
    read_table,
    refresh,
    snapshot_of,
    sync_with_handoff,
)

DERIVED_TABLES = (
    "mean_max",
    "load_series",
    "daily_load",
    "weekly_load",
    "benchmarks",
    "benchmark_periods",
    "blocks",
    "mesocycles",
    "planned_workouts",
    "planned_workout_pages",
    "unplanned_pages",
)


def _rows(root: Path) -> dict[str, tuple[tuple[object, ...], ...]]:
    result = {name: read_table(root, name) for name in DERIVED_TABLES}
    for name, rows in result.items():
        assert rows, f"{name} must have rows before cross-route comparison"
    return result


def test_derived_rows_match_across_refresh_routes(tmp_path: Path) -> None:
    source_root = build_fixture_root(tmp_path / "composed-source", composed=True)
    source_dir = source_root / "composed-source"
    build_index(source_root, today=TODAY)
    sync_with_handoff(source_root, source_dir, today=TODAY)

    source_rows = snapshot_of(source_root, today=TODAY)
    last_source_page = max(source_rows.pages, key=lambda page: page.path)
    last_page_file = source_root / last_source_page.path
    source_text = last_page_file.read_text(encoding="utf-8")
    source_text = source_text.replace(
        "---\n",
        '---\nload_value: 97\nload_methodology: "threshold"\n',
        1,
    )
    last_page_file.write_text(source_text, encoding="utf-8")
    refresh(source_root, today=TODAY)

    source_snapshot = snapshot_of(source_root, today=TODAY)
    page_paths = tuple(sorted(page.path for page in source_snapshot.pages))
    assert len(page_paths) > 1
    last_page = next(
        page for page in source_snapshot.pages if page.path == page_paths[-1]
    )
    assert last_page.frontmatter.get("load_value") == 97
    combined_paths = sorted(
        [page.path for page in source_snapshot.pages]
        + [page.path for page in source_snapshot.left_out]
    )
    assert (page_paths[0], page_paths[-1]) == (
        combined_paths[0],
        combined_paths[-1],
    )
    page_bytes = {Path(path): (source_root / path).read_bytes() for path in page_paths}

    by_route: dict[str, Path] = {"handoff": source_root}

    for route in ("incremental", "reverse", "rederive", "rebuild"):
        root = tmp_path / route
        shutil.copytree(source_root, root)
        by_route[route] = root

    incremental = by_route["incremental"]
    ordered_pages = sorted(page_bytes)
    first_path = ordered_pages[0]
    last_path = ordered_pages[-1]
    first_bytes = page_bytes[first_path]
    first_fingerprint = next(
        page.document_fingerprint
        for page in source_snapshot.pages
        if page.path == first_path.as_posix()
    )
    for relative in ordered_pages:
        (incremental / relative).unlink()
    build_index(incremental, today=TODAY, rebuild=True)
    assert all(not (incremental / path).exists() for path in ordered_pages)
    added_paths: list[Path] = []
    for relative in ordered_pages:
        (incremental / relative).write_bytes(page_bytes[relative])
        refresh(incremental, today=TODAY)
        added_paths.append(relative)
        snapshot = snapshot_of(incremental, today=TODAY)
        assert added_paths == ordered_pages[: len(added_paths)]
        assert (incremental / first_path).read_bytes() == first_bytes
        assert (
            next(
                page.document_fingerprint
                for page in snapshot.pages
                if page.path == first_path.as_posix()
            )
            == first_fingerprint
        )
    final_snapshot = snapshot_of(incremental, today=TODAY)
    held_last = {page.path for page in final_snapshot.pages}
    assert last_path.as_posix() in held_last
    assert (
        next(
            page.frontmatter.get("load_value")
            for page in final_snapshot.pages
            if page.path == last_path.as_posix()
        )
        == 97
    )
    reverse = by_route["reverse"]
    for relative in ordered_pages:
        (reverse / relative).unlink()
    created_reverse: list[Path] = []
    for relative in reversed(ordered_pages):
        (reverse / relative).write_bytes(page_bytes[relative])
        created_reverse.append(relative)
    assert created_reverse == list(reversed(ordered_pages))
    build_index(reverse, today=TODAY, rebuild=True)

    rederive = by_route["rederive"]
    for relative in ordered_pages:
        (rederive / relative).unlink()
    build_index(rederive, today=TODAY)
    for relative in ordered_pages:
        (rederive / relative).write_bytes(page_bytes[relative])
    refresh(rederive, today=TODAY)

    rebuild = by_route["rebuild"]
    build_index(rebuild, today=TODAY, rebuild=True)

    outputs = {route: _rows(root) for route, root in by_route.items()}
    assert len(outputs["handoff"]["mean_max"]) == 11
    assert outputs["handoff"]["mean_max"][0][1] == 1
    assert outputs["handoff"]["mean_max"][0][2] == 222.0
    for route in ("rebuild", "reverse", "handoff", "rederive"):
        assert outputs[route] == outputs["incremental"], route
    assert any(row[2] == 97.0 for row in outputs["incremental"]["daily_load"])
