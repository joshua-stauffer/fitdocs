"""Task 5.1: read workout documents once and form deterministic snapshots."""

from __future__ import annotations

import builtins
from collections.abc import Callable, Mapping, Set
from dataclasses import fields
from datetime import date
from pathlib import Path
from typing import Any, Literal, get_type_hints

import pytest

from fitdocs import contract, docio
from fitdocs.index import corpus
from fitdocs.index.fingerprint import document_fingerprint
from fitdocs.index.producer import (
    CorpusLeftOut,
    CorpusPage,
    CorpusSnapshot,
    LoadRegionReading,
)
from fitdocs.layout import WORKOUTS_DIR
from fitdocs.load import docedit
from fitdocs.load.docedit import RegionClassification, RegionState, classify_load_region
from fitdocs.load.render import render_computed, render_unsupported
from fitdocs.load.types import LoadResult


def _markdown(frontmatter: str, *, load: str = contract.LOAD_NOT_COMPUTED) -> str:
    return (
        f"---\ntype: workout\n{frontmatter}---\n\n"
        f"<!-- fitdocs:begin:load -->\n{load}\n<!-- fitdocs:end:load -->\n"
    )


def _write_page(
    path: Path, sources: list[str] | None, *, title: str = "synthetic"
) -> bytes:
    source_lines = (
        "sources: []\n"
        if sources is None
        else "sources:\n" + "".join(f"  - {source!r}\n" for source in sources)
    )
    data = _markdown(f"title: {title!r}\n" + source_lines).encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return data


def test_read_document_returns_one_bytes_text_and_frontmatter_value(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "workout.md"
    data = b"---\r\ntype: workout\r\ntitle: Caf\xc3\xa9\r\n---\r\nbody\r\n"
    path.write_bytes(data)
    original_read_bytes = Path.read_bytes
    reads: list[Path] = []

    def read_once(candidate: Path) -> bytes:
        reads.append(candidate)
        return original_read_bytes(candidate)

    monkeypatch.setattr(Path, "read_bytes", read_once)

    result = docio.read_document(path)

    assert result is not None
    assert result.data == data
    assert result.text == "---\r\ntype: workout\r\ntitle: Caf\u00e9\r\n---\r\nbody\r\n"
    assert result.frontmatter == {"type": "workout", "title": "Caf\u00e9"}
    assert reads == [path]
    assert [field.name for field in fields(result)] == ["data", "text", "frontmatter"]


@pytest.mark.parametrize(
    "case",
    ["missing", "undecodable", "unparseable", "symlink"],
)
def test_read_document_refuses_symlinks_and_unreadable_files(
    tmp_path: Path, case: str
) -> None:
    path = tmp_path / "candidate.md"
    if case == "undecodable":
        path.write_bytes(b"\xff\xfe")
    elif case == "unparseable":
        path.write_text("---\n: bad yaml\n---\n", encoding="utf-8")
    elif case == "symlink":
        target = tmp_path / "target.md"
        target.write_text("---\ntype: workout\n---\n", encoding="utf-8")
        path.symlink_to(target)

    result = docio.read_document(path)
    if case == "unparseable":
        assert result is not None
        assert result.data == b"---\n: bad yaml\n---\n"
        assert result.frontmatter is None
    else:
        assert result is None


@pytest.mark.parametrize("error_type", [PermissionError, OSError])
def test_read_os_errors_return_none_and_scanning_continues(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, error_type: type[OSError]
) -> None:
    workout_dir = tmp_path / WORKOUTS_DIR
    denied_path = workout_dir / "a-denied.md"
    _write_page(denied_path, ["fit-archive/" + "a" * 64 + ".fit"])
    readable_path = workout_dir / "b-readable.md"
    _write_page(readable_path, ["fit-archive/" + "b" * 64 + ".fit"])
    original_read_bytes = Path.read_bytes
    attempted: list[Path] = []

    def read_with_error(path: Path) -> bytes:
        attempted.append(path)
        if path == denied_path:
            raise error_type("synthetic document read failure")
        return original_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", read_with_error)

    def captured_read(reader: Callable[[Path], object | None]) -> None:
        try:
            result = reader(denied_path)
        except error_type as raised:
            result = raised
        assert result is None

    captured_read(docio.read_document)
    captured_read(docio.read_frontmatter)

    scan: object | None = None
    try:
        scan = corpus.scan_workout_pages(tmp_path)
    except error_type as raised:
        scan = raised
    assert isinstance(scan, corpus.CorpusScan)
    assert tuple(page.path for page in scan.pages) == (f"{WORKOUTS_DIR}/b-readable.md",)
    assert scan.left_out == ()
    assert attempted == [denied_path, denied_path, denied_path, readable_path]


@pytest.mark.parametrize("error_type", [PermissionError, OSError])
def test_scanner_keeps_readable_sibling_after_document_oserror(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, error_type: type[OSError]
) -> None:
    workout_dir = tmp_path / WORKOUTS_DIR
    denied_path = workout_dir / "a-denied.md"
    _write_page(denied_path, ["fit-archive/" + "c" * 64 + ".fit"])
    readable_path = workout_dir / "b-readable.md"
    _write_page(readable_path, ["fit-archive/" + "d" * 64 + ".fit"])
    original_read_bytes = Path.read_bytes

    def read_with_error(path: Path) -> bytes:
        if path == denied_path:
            raise error_type("synthetic scan read failure")
        return original_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", read_with_error)
    scan: object | None = None
    try:
        scan = corpus.scan_workout_pages(tmp_path)
    except error_type as raised:
        scan = raised
    assert isinstance(scan, corpus.CorpusScan)
    assert tuple(page.path for page in scan.pages) == (f"{WORKOUTS_DIR}/b-readable.md",)
    assert scan.left_out == ()


def test_read_frontmatter_delegates_to_document_reader(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    expected: dict[str, object] = {"type": "workout", "title": "delegated"}
    calls: list[Path] = []

    def read_once(path: Path) -> docio.DocumentRead:
        calls.append(path)
        return docio.DocumentRead(b"bytes", "text", expected)

    monkeypatch.setattr(docio, "read_document", read_once)
    path = tmp_path / "delegated.md"

    assert docio.read_frontmatter(path) == expected
    assert calls == [path]


def test_new_docio_and_corpus_carriers_are_frozen_dataclasses() -> None:
    for carrier in (
        docio.DocumentRead,
        corpus.ScannedPage,
        corpus.LeftOutPage,
        corpus.CorpusScan,
    ):
        assert carrier.__dict__["__dataclass_params__"].frozen is True


def test_docio_and_corpus_carrier_annotations_match_their_contracts() -> None:
    assert get_type_hints(docio.DocumentRead) == {
        "data": bytes,
        "text": str,
        "frontmatter": dict[str, object] | None,
    }
    assert get_type_hints(corpus.ScannedPage) == {
        "page_key": str,
        "path": str,
        "text": str,
        "frontmatter": Mapping[str, object],
        "sources": tuple[str, ...],
        "document_fingerprint": str,
    }
    assert get_type_hints(corpus.LeftOutPage) == {
        "path": str,
        "reason": Literal["no_base_reference", "duplicate_base"],
        "collides_with": str | None,
        "document_fingerprint": str,
    }
    assert get_type_hints(corpus.CorpusScan) == {
        "pages": tuple[corpus.ScannedPage, ...],
        "left_out": tuple[corpus.LeftOutPage, ...],
    }
    assert get_type_hints(CorpusSnapshot) == {
        "data_root": Path,
        "pages": tuple[CorpusPage, ...],
        "left_out": tuple[CorpusLeftOut, ...],
        "today": date,
        "athlete_fingerprint": str,
    }
    assert get_type_hints(corpus.scan_workout_pages) == {
        "data_root": Path,
        "return": corpus.CorpusScan,
    }
    assert get_type_hints(corpus.corpus_snapshot) == {
        "data_root": Path,
        "scan": corpus.CorpusScan,
        "today": date,
        "athlete_fingerprint": str,
        "held": Set[str] | None,
        "return": CorpusSnapshot,
    }
    assert get_type_hints(corpus.corpus_snapshot)["held"] == Set[str] | None


def test_scan_uses_base_hash_reads_each_workout_once_and_filters_other_files(
    synced_workout_pages: tuple[Path, ...], monkeypatch: pytest.MonkeyPatch
) -> None:
    workout_dir = synced_workout_pages[0].parent
    note = workout_dir / "note.md"
    note.write_text("---\ntype: note\n---\n", encoding="utf-8")
    agents = workout_dir / "AGENTS.md"
    agents.write_text("instructions\n", encoding="utf-8")
    symlink = workout_dir / "symlink.md"
    symlink.symlink_to(synced_workout_pages[0])

    original = docio.read_document
    calls: list[Path] = []

    def counted(path: Path) -> docio.DocumentRead | None:
        calls.append(path)
        return original(path)

    monkeypatch.setattr(docio, "read_document", counted)
    scan = corpus.scan_workout_pages(workout_dir.parent)

    expected_paths = tuple(
        path.relative_to(workout_dir.parent).as_posix() for path in synced_workout_pages
    )
    assert tuple(page.path for page in scan.pages) == expected_paths
    assert scan.left_out == ()
    assert calls == sorted(workout_dir.glob("*.md"))
    for page in scan.pages:
        sources = contract.source_refs(page.frontmatter)
        assert page.sources == sources
        if len(sources) > 1:
            assert sources[0] != sources[-1]
        assert page.page_key == contract.sha_of_ref(sources[-1])
        assert page.document_fingerprint == document_fingerprint(
            page.path, (workout_dir.parent / page.path).read_bytes()
        )
        page_bytes = (workout_dir.parent / page.path).read_bytes()
        assert page.text == page_bytes.decode("utf-8")
        assert page.frontmatter == contract.parse_frontmatter(page.text)
    assert any(len(page.sources) == 2 for page in scan.pages)
    assert [field.name for field in fields(corpus.ScannedPage)] == [
        "page_key",
        "path",
        "text",
        "frontmatter",
        "sources",
        "document_fingerprint",
    ]
    assert [field.name for field in fields(corpus.CorpusScan)] == ["pages", "left_out"]


def test_scan_sorts_and_classifies_no_base_and_duplicate_with_fingerprints(
    tmp_path: Path,
) -> None:
    workout_dir = tmp_path / WORKOUTS_DIR
    base = "a" * 64
    _write_page(
        workout_dir / "z-no-base.md", [f"fit-archive/{base}.fit", "foreign.fit"]
    )
    no_sources_path = workout_dir / "x-no-sources.md"
    no_sources_bytes = _write_page(no_sources_path, None).replace(b"\n", b"\r\n")
    no_sources_path.write_bytes(no_sources_bytes)
    assert (
        no_sources_path.read_text(encoding="utf-8").encode("utf-8") != no_sources_bytes
    )
    duplicate_bytes = _write_page(
        workout_dir / "b-duplicate.md", [f"fit-archive/{base}.fit"]
    )
    winner_bytes = _write_page(workout_dir / "a-winner.md", [f"fit-archive/{base}.fit"])
    unique = "b" * 64
    _write_page(workout_dir / "c-unique.md", [f"fit-archive/{unique}.fit"])

    scan = corpus.scan_workout_pages(tmp_path)

    assert tuple(page.path for page in scan.pages) == (
        f"{WORKOUTS_DIR}/a-winner.md",
        f"{WORKOUTS_DIR}/c-unique.md",
    )
    assert tuple(page.page_key for page in scan.pages) == (base, unique)
    assert tuple(
        (item.path, item.reason, item.collides_with, item.document_fingerprint)
        for item in scan.left_out
    ) == (
        (
            f"{WORKOUTS_DIR}/b-duplicate.md",
            "duplicate_base",
            f"{WORKOUTS_DIR}/a-winner.md",
            document_fingerprint(f"{WORKOUTS_DIR}/b-duplicate.md", duplicate_bytes),
        ),
        (
            f"{WORKOUTS_DIR}/x-no-sources.md",
            "no_base_reference",
            None,
            document_fingerprint(f"{WORKOUTS_DIR}/x-no-sources.md", no_sources_bytes),
        ),
        (
            f"{WORKOUTS_DIR}/z-no-base.md",
            "no_base_reference",
            None,
            document_fingerprint(
                f"{WORKOUTS_DIR}/z-no-base.md",
                (workout_dir / "z-no-base.md").read_bytes(),
            ),
        ),
    )
    assert [field.name for field in fields(corpus.LeftOutPage)] == [
        "path",
        "reason",
        "collides_with",
        "document_fingerprint",
    ]
    assert winner_bytes == (workout_dir / "a-winner.md").read_bytes()


def test_corpus_snapshot_partitions_scanned_and_left_out_pages_without_io(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = Path("relative/root-as-passed")
    today = date(2042, 7, 9)
    athlete = "athlete-fingerprint-distinct-from-default"
    key_alpha = "archive-key-alpha"
    key_beta = "archive-key-beta"
    page_alpha = corpus.ScannedPage(
        key_alpha,
        f"{WORKOUTS_DIR}/z-alpha.md",
        "alpha markdown bytes decoded",
        {"type": "workout", "title": "alpha title"},
        ("fit-archive/extra-alpha.fit", "fit-archive/base-alpha.fit"),
        "document-fingerprint-alpha",
    )
    page_beta = corpus.ScannedPage(
        key_beta,
        f"{WORKOUTS_DIR}/a-beta.md",
        "beta markdown bytes decoded",
        {"type": "workout", "title": "beta title"},
        ("fit-archive/base-beta.fit",),
        "document-fingerprint-beta",
    )
    duplicate = corpus.LeftOutPage(
        f"{WORKOUTS_DIR}/d-duplicate.md",
        "duplicate_base",
        f"{WORKOUTS_DIR}/z-alpha.md",
        "document-fingerprint-duplicate",
    )
    no_base = corpus.LeftOutPage(
        f"{WORKOUTS_DIR}/c-no-base.md",
        "no_base_reference",
        None,
        "document-fingerprint-no-base",
    )
    scan = corpus.CorpusScan((page_alpha, page_beta), (duplicate, no_base))
    expected_paths = (
        f"{WORKOUTS_DIR}/a-beta.md",
        f"{WORKOUTS_DIR}/c-no-base.md",
        f"{WORKOUTS_DIR}/d-duplicate.md",
        f"{WORKOUTS_DIR}/z-alpha.md",
    )

    all_pages = (
        CorpusPage(
            key_beta,
            f"{WORKOUTS_DIR}/a-beta.md",
            {"type": "workout", "title": "beta title"},
            "document-fingerprint-beta",
        ),
        CorpusPage(
            key_alpha,
            f"{WORKOUTS_DIR}/z-alpha.md",
            {"type": "workout", "title": "alpha title"},
            "document-fingerprint-alpha",
        ),
    )
    scanned_left_out = (
        CorpusLeftOut(f"{WORKOUTS_DIR}/c-no-base.md", "document-fingerprint-no-base"),
        CorpusLeftOut(
            f"{WORKOUTS_DIR}/d-duplicate.md", "document-fingerprint-duplicate"
        ),
    )
    every_expected = CorpusSnapshot(root, all_pages, scanned_left_out, today, athlete)
    missing_beta_expected = CorpusSnapshot(
        root,
        (all_pages[1],),
        (
            CorpusLeftOut(f"{WORKOUTS_DIR}/a-beta.md", "document-fingerprint-beta"),
            *scanned_left_out,
        ),
        today,
        athlete,
    )
    mixed_beta_expected = CorpusSnapshot(
        root,
        (all_pages[0],),
        (
            CorpusLeftOut(
                f"{WORKOUTS_DIR}/c-no-base.md", "document-fingerprint-no-base"
            ),
            CorpusLeftOut(
                f"{WORKOUTS_DIR}/d-duplicate.md", "document-fingerprint-duplicate"
            ),
            CorpusLeftOut(f"{WORKOUTS_DIR}/z-alpha.md", "document-fingerprint-alpha"),
        ),
        today,
        athlete,
    )
    empty_expected = CorpusSnapshot(
        root,
        (),
        (
            CorpusLeftOut(f"{WORKOUTS_DIR}/a-beta.md", "document-fingerprint-beta"),
            *scanned_left_out,
            CorpusLeftOut(f"{WORKOUTS_DIR}/z-alpha.md", "document-fingerprint-alpha"),
        ),
        today,
        athlete,
    )
    assert len(scan.pages) == 2
    assert len(scan.left_out) == 2
    assert key_alpha != key_beta
    empty_held: set[str] = set()
    assert not empty_held
    absent_key = "key-not-held-by-the-index"
    assert absent_key not in {page.page_key for page in scan.pages}
    assert every_expected.pages[0].frontmatter != every_expected.pages[1].frontmatter

    # Activate all filesystem-read monitors only after input and expected values
    # exist, so a read by the builder reaches the postcondition below.
    read_events: list[str] = []
    real_builtin_open = builtins.open
    real_path_open = Path.open
    real_path_read_bytes = Path.read_bytes
    real_path_read_text = Path.read_text

    def watch_builtin_open(file: Any, *args: Any, **kwargs: Any) -> Any:
        read_events.append("builtins.open")
        return real_builtin_open(file, *args, **kwargs)

    def watch_path_open(self: Path, *args: Any, **kwargs: Any) -> Any:
        read_events.append("Path.open")
        return real_path_open(self, *args, **kwargs)

    def watch_read_bytes(self: Path) -> bytes:
        read_events.append("Path.read_bytes")
        return real_path_read_bytes(self)

    def watch_read_text(self: Path, *args: Any, **kwargs: Any) -> str:
        read_events.append("Path.read_text")
        return real_path_read_text(self, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", watch_builtin_open)
    monkeypatch.setattr(Path, "open", watch_path_open)
    monkeypatch.setattr(Path, "read_bytes", watch_read_bytes)
    monkeypatch.setattr(Path, "read_text", watch_read_text)

    def snapshot(held: Set[str] | None) -> CorpusSnapshot:
        return corpus.corpus_snapshot(
            root, scan, today=today, athlete_fingerprint=athlete, held=held
        )

    all_actual = snapshot(None)
    missing_beta_actual = snapshot({key_alpha})
    mixed_beta_actual = snapshot({key_beta, absent_key})
    empty_actual = snapshot(empty_held)
    unknown_only_actual = snapshot({absent_key})

    assert all_actual == every_expected
    assert missing_beta_actual == missing_beta_expected
    assert mixed_beta_actual == mixed_beta_expected
    assert empty_actual == empty_expected
    assert unknown_only_actual == empty_expected

    for actual in (
        all_actual,
        missing_beta_actual,
        mixed_beta_actual,
        empty_actual,
        unknown_only_actual,
    ):
        actual_paths = tuple(page.path for page in actual.pages) + tuple(
            page.path for page in actual.left_out
        )
        assert tuple(sorted(actual_paths)) == expected_paths
        assert len(set(actual_paths)) == len(expected_paths)
        assert tuple(page.path for page in actual.pages) == tuple(
            sorted(page.path for page in actual.pages)
        )
        assert tuple(page.path for page in actual.left_out) == tuple(
            sorted(page.path for page in actual.left_out)
        )
    assert read_events == []

    assert [field.name for field in fields(CorpusPage)] == [
        "page_key",
        "path",
        "frontmatter",
        "document_fingerprint",
    ]
    assert [field.name for field in fields(CorpusLeftOut)] == [
        "path",
        "document_fingerprint",
    ]
    assert [field.name for field in fields(CorpusSnapshot)] == [
        "data_root",
        "pages",
        "left_out",
        "today",
        "athlete_fingerprint",
    ]


def test_load_region_reading_maps_every_state_and_preserves_supported_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    real_classifier = docedit.classify_load_region
    classifications: list[RegionClassification] = []

    def record_classification(markdown: str) -> RegionClassification:
        result = real_classifier(markdown)
        classifications.append(result)
        return result

    monkeypatch.setattr(docedit, "classify_load_region", record_classification)
    computed = render_computed(
        LoadResult(
            calculator_id="synthetic-calculator",
            display_name="Synthetic calculator",
            value=12.5,
            basis="synthetic basis",
            non_selected=(),
            flags=(),
            inputs_used=(),
            notes=(),
        )
    )
    computed_reading = corpus._load_region_reading(_markdown("", load=computed))
    computed_classification = classify_load_region(_markdown("", load=computed))
    assert computed_classification.state is RegionState.COMPUTED
    assert isinstance(computed_reading, LoadRegionReading)
    assert computed_reading.status == "computed"
    assert computed_reading.payload == computed_classification.payload
    assert computed_reading.payload is not None
    assert computed_reading.payload is classifications[-1].payload

    unsupported_markdown = _markdown("", load=render_unsupported("run"))
    unsupported_classification = classify_load_region(unsupported_markdown)
    unsupported = corpus._load_region_reading(unsupported_markdown)
    assert unsupported_classification.state is RegionState.UNSUPPORTED
    assert unsupported.status == "unsupported"
    assert unsupported.payload == unsupported_classification.payload
    assert unsupported.payload is not None
    assert unsupported.payload is classifications[-1].payload

    superseded = _markdown(
        "", load='<!-- fitdocs-load:v1 {"v":1,"status":"computed"} -->'
    )
    old_unsupported = _markdown(
        "", load='<!-- fitdocs-load:v1 {"v":1,"status":"unsupported"} -->'
    )
    foreign = _markdown("", load="user-owned result")
    placeholder = _markdown("", load=contract.LOAD_NOT_COMPUTED)
    assert classify_load_region(superseded).state is RegionState.SUPERSEDED
    assert classify_load_region(old_unsupported).state is RegionState.UNSUPPORTED
    assert classify_load_region(foreign).state is RegionState.FOREIGN
    assert classify_load_region(placeholder).state is RegionState.PLACEHOLDER
    for markdown in (superseded, foreign):
        reading = corpus._load_region_reading(markdown)
        assert reading.status == "unreadable"
        assert reading.payload is None
    for markdown in (placeholder,):
        reading = corpus._load_region_reading(markdown)
        assert reading.status == "not_computed"
        assert reading.payload is None
    old_unsupported_reading = corpus._load_region_reading(old_unsupported)
    assert old_unsupported_reading.status == "unsupported"
    assert old_unsupported_reading.payload is None
