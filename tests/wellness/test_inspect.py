"""Read-only wellness findings from metadata and the last manifest."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from fitdocs.wellness.archive import Committed, commit_original
from fitdocs.wellness.engine import rebuild_series
from fitdocs.wellness.inspect import WellnessProblemKind as Kind
from fitdocs.wellness.inspect import inspect_wellness
from fitdocs.wellness.registry import format_named
from fitdocs.wellness.settings import DEFAULT_WELLNESS_SETTINGS
from tests.wellness._helpers import CountingOpener, tree_snapshot
from tests.wellness.builders_intervals import intervals_list_bytes, intervals_record


def _archive(
    root: Path, name: str = "input.json", value: int = 57, weight: int | None = None
) -> Path:
    candidate = root / name
    candidate.write_bytes(
        intervals_list_bytes(
            [intervals_record("2025-04-09", restingHR=value, weight=weight)]
        )
    )
    format = format_named("intervals-icu")
    if format is None:
        raise AssertionError("published intervals format missing")
    from hashlib import sha256

    result = commit_original(
        root, format, candidate, sha256(candidate.read_bytes()).hexdigest()
    )
    if not isinstance(result, Committed):
        raise AssertionError(result)
    return result.entry.path


def _build(root: Path) -> None:
    rebuild_series(root, settings=DEFAULT_WELLNESS_SETTINGS, force=False)


def test_clean_and_missing_root(tmp_path: Path) -> None:
    missing = tmp_path / "absent"
    assert inspect_wellness(missing) == ()
    assert not missing.exists()
    _archive(tmp_path)
    _build(tmp_path)
    assert inspect_wellness(tmp_path) == ()


def test_orphans_each_named(tmp_path: Path) -> None:
    directory = tmp_path / "wellness-archive" / "intervals-icu"
    directory.mkdir(parents=True)
    (directory / "bad.json").write_text("ignored")
    (directory / "other.txt").write_text("also ignored")
    problems = inspect_wellness(tmp_path)
    assert [(p.kind.value, p.subject) for p in problems] == [
        ("orphaned_entry", "wellness-archive/intervals-icu/bad.json"),
        ("orphaned_entry", "wellness-archive/intervals-icu/other.txt"),
    ]
    assert all("never reads" in p.detail for p in problems)


@pytest.mark.parametrize(
    "change, reason",
    [
        ("no-series", "series manifest is missing"),
        ("added", "archive, parsing rules or precedence changed"),
        ("settings", "archive, parsing rules or precedence changed"),
        ("edited", "wellness/2025.csv: missing or changed"),
        ("missing", "wellness/2025.csv: missing or changed"),
    ],
)
def test_stale_reasons(tmp_path: Path, change: str, reason: str) -> None:
    _archive(tmp_path)
    if change != "no-series":
        _build(tmp_path)
    if change == "added":
        _archive(tmp_path, "second.json", 63)
    elif change == "settings":
        (tmp_path / "fitdocs.toml").write_text(
            '[wellness]\nprecedence=["intervals-icu"]\n'
        )
    elif change == "edited":
        year = tmp_path / "wellness/2025.csv"
        year.write_bytes(year.read_bytes().replace(b"57", b"68"))
    elif change == "missing":
        (tmp_path / "wellness/2025.csv").unlink()
    problems = inspect_wellness(tmp_path)
    assert len(problems) == 1
    assert problems[0].kind is Kind.SERIES_STALE
    assert problems[0].subject == "wellness"
    assert reason in problems[0].detail


def test_aggregates_all_reasons(tmp_path: Path) -> None:
    _archive(tmp_path)
    _build(tmp_path)
    _archive(tmp_path, "added.json", 73)
    (tmp_path / "wellness/2025.csv").unlink()
    problems = inspect_wellness(tmp_path)
    assert len(problems) == 1
    assert problems[0].kind is Kind.SERIES_STALE
    assert all(
        reason in problems[0].detail
        for reason in (
            "archive, parsing rules or precedence changed",
            "series year files differ from manifest",
            "wellness/2025.csv: missing or changed",
        )
    )


@pytest.mark.parametrize(
    "document", ['[wellness]\nprecedence=["unknown"]', "not valid [toml"]
)
def test_invalid_settings(tmp_path: Path, document: str) -> None:
    (tmp_path / "fitdocs.toml").write_text(document)
    problems = inspect_wellness(tmp_path)
    assert len(problems) == 1
    assert problems[0].kind is Kind.SERIES_STALE
    assert "cannot be judged" in problems[0].detail
    assert "fitdocs.toml" in problems[0].detail


def test_each_occupied_path(tmp_path: Path) -> None:
    directory = tmp_path / "wellness"
    directory.mkdir()
    (directory / "2021.csv").mkdir()
    (directory / "2022.csv").write_text("foreign")
    (directory / "2023.csv").symlink_to(tmp_path / "private")
    problems = inspect_wellness(tmp_path)
    occupied = [p for p in problems if p.kind is Kind.SERIES_OCCUPIED]
    assert [p.subject for p in occupied] == [
        "wellness/2021.csv",
        "wellness/2022.csv",
        "wellness/2023.csv",
    ]
    assert [p.detail for p in occupied] == [
        "occupied series path",
        "foreign year file: wrong series header",
        "occupied series path",
    ]


def test_unreadable_series(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _archive(tmp_path)
    _build(tmp_path)
    paths = {tmp_path / "wellness/2025.csv", tmp_path / "wellness/manifest.toml"}
    original = Path.open

    def unreadable(path: Path, *args: Any, **kwargs: Any) -> Any:
        if path in paths:
            raise PermissionError("cloud unavailable")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", unreadable)
    problems = inspect_wellness(tmp_path)
    assert len(problems) == 1
    assert problems[0].kind is Kind.SERIES_STALE
    assert all(
        f"wellness/{name}: could not be read" in problems[0].detail
        for name in ("2025.csv", "manifest.toml")
    )


def test_conflicts_from_last_manifest(tmp_path: Path) -> None:
    first = _archive(tmp_path, weight=83)
    second = _archive(tmp_path, "second.json", 69, weight=91)
    _build(tmp_path)
    # The archive now disagrees with the last successful rebuild.
    first.unlink()
    second.unlink()
    problems = inspect_wellness(tmp_path)
    conflicts = [p for p in problems if p.kind is Kind.CONFLICT]
    assert len(conflicts) == 2
    assert [p.subject for p in conflicts] == [
        "2025-04-09 resting_hr_bpm intervals-icu",
        "2025-04-09 weight_kg intervals-icu",
    ]
    kept = max(first, second, key=lambda p: p.as_posix())
    value = 57 if kept == first else 69
    assert (
        conflicts[1].detail
        == f"kept {83 if kept == first else 91} "
        + f"from {kept.relative_to(tmp_path).as_posix()}; "
        + "conflicting entries: "
        + ", ".join(
            sorted(
                [
                    first.relative_to(tmp_path).as_posix(),
                    second.relative_to(tmp_path).as_posix(),
                ]
            )
        )
    )
    assert (
        conflicts[0].detail
        == f"kept {value} from {kept.relative_to(tmp_path).as_posix()}; "
        + "conflicting entries: "
        + ", ".join(
            sorted(
                [
                    first.relative_to(tmp_path).as_posix(),
                    second.relative_to(tmp_path).as_posix(),
                ]
            )
        )
    )


@pytest.mark.parametrize("restricted", [False, True])
def test_metadata_only_read_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, restricted: bool
) -> None:
    entry = _archive(tmp_path)
    _build(tmp_path)
    ignored = tmp_path / "wellness/athlete-notes.md"
    ignored.write_text("private")
    before = tree_snapshot(tmp_path)
    directories = {p.relative_to(tmp_path) for p in tmp_path.rglob("*") if p.is_dir()}
    opener = CountingOpener(entry)
    opener.install(monkeypatch)
    original = Path.open
    reads: list[Path] = []

    def allowed(path: Path, *args: Any, **kwargs: Any) -> Any:
        reads.append(path)
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", allowed)
    if restricted:
        entry.chmod(0)
    try:
        assert inspect_wellness(tmp_path) == ()
    finally:
        entry.chmod(0o600)
    assert opener.opens == 0
    assert set(reads) == {
        tmp_path / "wellness/2025.csv",
        tmp_path / "wellness/manifest.toml",
    }
    monkeypatch.undo()
    assert tree_snapshot(tmp_path) == before
    assert {
        p.relative_to(tmp_path) for p in tmp_path.rglob("*") if p.is_dir()
    } == directories


def test_invalid_settings_preserves_other_findings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _archive(tmp_path)
    _build(tmp_path)
    (tmp_path / "fitdocs.toml").write_text("[wellness]\nprecedence=3")
    (tmp_path / "wellness/2020.csv").mkdir()
    (tmp_path / "wellness-archive/loose.txt").write_text("orphan")
    original = Path.read_bytes

    def read(path: Path) -> bytes:
        if path.name == "2025.csv":
            raise OSError("offline")
        return original(path)

    monkeypatch.setattr(Path, "read_bytes", read)
    problems = inspect_wellness(tmp_path)
    assert {p.kind for p in problems} == {
        Kind.ORPHANED_ENTRY,
        Kind.SERIES_OCCUPIED,
        Kind.SERIES_STALE,
    }
    stale = next(p for p in problems if p.kind is Kind.SERIES_STALE)
    assert "cannot be judged" in stale.detail
    assert "wellness/2025.csv: could not be read" in stale.detail


@pytest.mark.parametrize(
    "name,value",
    [
        ("ORPHANED_ENTRY", "orphaned_entry"),
        ("SERIES_STALE", "series_stale"),
        ("SERIES_OCCUPIED", "series_occupied"),
        ("CONFLICT", "conflict"),
    ],
)
def test_kind_values(name: str, value: str) -> None:
    assert Kind[name].value == value


def test_independent_manifest_conflict_fields(tmp_path: Path) -> None:
    import tomllib

    import tomli_w

    from tests.wellness.builders_series import write_series

    write_series(tmp_path, ())
    manifest = tmp_path / "wellness/manifest.toml"
    document = tomllib.loads(manifest.read_text())
    from datetime import date

    document["conflicts"] = [
        dict(
            day=date(2024, 9, 3),
            metric="weight_kg",
            source="garmin-export",
            kept_entry="wellness-archive/z.json",
            kept_value=83,
            other_entries=["wellness-archive/a.json"],
            other_values=[79],
        ),
        dict(
            day=date(2025, 2, 8),
            metric="resting_hr_bpm",
            source="intervals-icu",
            kept_entry="wellness-archive/c.json",
            kept_value=61,
            other_entries=["wellness-archive/b.json", "wellness-archive/d.json"],
            other_values=[58, 63],
        ),
    ]
    manifest.write_text(tomli_w.dumps(document))
    problems = inspect_wellness(tmp_path)
    assert [(p.subject, p.detail) for p in problems if p.kind is Kind.CONFLICT] == [
        (
            "2024-09-03 weight_kg garmin-export",
            "kept 83 from wellness-archive/z.json; conflicting entries: "
            "wellness-archive/a.json, wellness-archive/z.json",
        ),
        (
            "2025-02-08 resting_hr_bpm intervals-icu",
            "kept 61 from wellness-archive/c.json; conflicting entries: "
            "wellness-archive/b.json, wellness-archive/c.json, wellness-archive/d.json",
        ),
    ]


def test_occupied_directory_does_not_open_external_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tests.wellness.builders_series import write_series

    root = tmp_path / "data"
    root.mkdir()
    external = tmp_path / "external"
    write_series(external, ())
    (external / "sentinel.txt").write_bytes(b"athlete-owned sentinel")
    link = root / "wellness"
    link.symlink_to(external / "wellness", target_is_directory=True)
    before = tree_snapshot(external)
    link_before = (link.readlink(), link.lstat().st_mtime_ns)
    opened: list[Path] = []
    original = Path.open

    def record_reads(path: Path, *args: Any, **kwargs: Any) -> Any:
        mode = args[0] if args else kwargs.get("mode", "r")
        if str(mode).startswith("r"):
            opened.append(path)
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", record_reads)
    problems = inspect_wellness(root)
    assert [(p.kind, p.subject) for p in problems] == [
        (Kind.SERIES_OCCUPIED, "wellness")
    ]
    assert opened == []
    monkeypatch.undo()
    assert tree_snapshot(external) == before
    assert (link.readlink(), link.lstat().st_mtime_ns) == link_before
