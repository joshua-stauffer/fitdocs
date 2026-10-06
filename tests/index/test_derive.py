"""Task 5.2: re-derive page computations from their listed archives."""

from __future__ import annotations

import hashlib
import os
import stat
from collections.abc import Sequence
from dataclasses import fields
from datetime import timedelta, timezone
from pathlib import Path
from typing import get_type_hints

import pytest

from fitdocs import AthleteInputs, compute_metrics, contract, parse_fit
from fitdocs.compose.archive import compose_listed
from fitdocs.compose.types import Composition
from fitdocs.index import derive
from fitdocs.index.bookkeeping import ComputedState
from fitdocs.layout import ARCHIVE_DIR, WORKOUTS_DIR, archive_path, source_ref
from fitdocs.metrics.types import DerivedMetrics
from fitdocs.model import Activity
from fitdocs.render import TileRef
from fitdocs.sync import SyncReport, sync
from tests.fixtures.merge import run_trio_fit_bytes


class _Tiles:
    attribution = "test"

    def resolve(self, refs: Sequence[TileRef]) -> dict[TileRef, bytes]:
        return {ref: b"\x89PNG\r\n\x1a\n" for ref in refs}


def _stage_and_sync(tmp_path: Path) -> Path:
    source = tmp_path / "source"
    data_root = tmp_path / "data"
    source.mkdir()
    data_root.mkdir()
    names = ("healthfit", "stryd_a", "stryd_b")
    for name, data in zip(names, run_trio_fit_bytes(), strict=True):
        (source / f"{name}.fit").write_bytes(data)
    report: SyncReport = sync(
        source,
        data_root,
        athlete=None,
        tz=timezone(timedelta(hours=-6)),
        tiles=_Tiles(),
    )
    assert report.failures == ()
    pages = tuple(
        path
        for path in (data_root / WORKOUTS_DIR).glob("*.md")
        if path.name != "AGENTS.md"
    )
    assert len(pages) == 1
    return data_root


def _page_sources(data_root: Path) -> tuple[str, ...]:
    pages = tuple(
        path
        for path in (data_root / WORKOUTS_DIR).glob("*.md")
        if path.name != "AGENTS.md"
    )
    assert len(pages) == 1
    markdown = pages[0].read_text(encoding="utf-8")
    frontmatter = contract.parse_frontmatter(markdown)
    assert frontmatter is not None
    return contract.source_refs(frontmatter)


def _sha_ref(data: bytes) -> str:
    return source_ref(hashlib.sha256(data).hexdigest())


def test_derived_carrier_is_frozen_and_has_design_fields() -> None:
    assert derive.Derived.__dict__["__dataclass_params__"].frozen is True
    assert [field.name for field in fields(derive.Derived)] == [
        "composition",
        "metrics",
    ]
    assert get_type_hints(derive.Derived) == {
        "composition": Composition,
        "metrics": DerivedMetrics,
    }


def test_derive_computes_metrics_from_returned_composition_activity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_root = _stage_and_sync(tmp_path)
    sources = _page_sources(data_root)
    base_path = derive.base_archive(data_root, sources)
    assert base_path is not None
    parsed_base = parse_fit(base_path.read_bytes())
    recorded_activities: list[Activity] = []
    real_compute_metrics = compute_metrics

    def record_metrics(
        activity: Activity, athlete: AthleteInputs | None
    ) -> DerivedMetrics:
        recorded_activities.append(activity)
        return real_compute_metrics(activity, athlete)

    monkeypatch.setattr("fitdocs.index.derive.compute_metrics", record_metrics)
    result = derive.derive_page(data_root, sources, None)

    assert isinstance(result, derive.Derived)
    assert result.composition.activity != parsed_base
    assert len(recorded_activities) == 1
    assert recorded_activities[0] is result.composition.activity


def test_base_archive_uses_last_valid_archive_reference(tmp_path: Path) -> None:
    root = tmp_path / "data"
    root.mkdir()
    first_bytes = b"extra archive bytes"
    base_bytes = b"base archive bytes"
    first_sha = hashlib.sha256(first_bytes).hexdigest()
    base_sha = hashlib.sha256(base_bytes).hexdigest()
    (root / ARCHIVE_DIR).mkdir()
    (root / ARCHIVE_DIR / f"{first_sha}.fit").write_bytes(first_bytes)
    base_path = archive_path(root, base_sha)
    base_path.write_bytes(base_bytes)
    fallback_path = archive_path(root, "f" * 64)
    fallback_path.write_bytes(b"distinct fallback candidate")
    sources = (source_ref(first_sha), source_ref(base_sha))

    assert derive.base_archive(root, sources) == base_path
    empty_sources: Path | None | IndexError
    try:
        empty_sources = derive.base_archive(root, ())
    except IndexError as error:
        empty_sources = error
    assert empty_sources is None
    assert derive.base_archive(root, ("foreign/source.fit",)) is None
    assert (
        derive.base_archive(root, (source_ref(first_sha), source_ref("e" * 64))) is None
    )


def test_derive_page_matches_load_pass_composition_for_ranked_run_trio(
    tmp_path: Path,
) -> None:
    data_root = _stage_and_sync(tmp_path)
    sources = _page_sources(data_root)
    assert len(sources) == 3
    healthfit, stryd_a, stryd_b = run_trio_fit_bytes()
    assert sources == (_sha_ref(stryd_a), _sha_ref(stryd_b), _sha_ref(healthfit))
    athlete = AthleteInputs(ftp_watts=237.0, resting_hr_bpm=53, max_hr_bpm=191)
    base_path = derive.base_archive(data_root, sources)
    assert base_path is not None
    assert base_path.is_file()

    expected_base = parse_fit(base_path.read_bytes())
    expected_composition = compose_listed(data_root, sources, expected_base)
    expected_metrics = compute_metrics(expected_composition.activity, athlete)
    assert expected_metrics != DerivedMetrics()
    assert expected_metrics != compute_metrics(expected_composition.activity, None)
    assert (
        expected_composition.activity.provenance.sha256
        == hashlib.sha256(base_path.read_bytes()).hexdigest()
    )

    result = derive.derive_page(data_root, sources, athlete)

    assert isinstance(result, derive.Derived)
    assert result.composition == expected_composition
    assert result.metrics == expected_metrics
    assert len(result.composition.activity.samples.time_s) > 0
    assert (
        result.composition.activity.samples.form_power_w
        != expected_base.samples.form_power_w
    )
    assert any(
        value is not None for value in result.composition.activity.samples.form_power_w
    )


def test_missing_base_archive_returns_source_missing(tmp_path: Path) -> None:
    data_root = tmp_path / "data"
    data_root.mkdir()
    missing_sha = "e" * 64
    sources = (source_ref("a" * 64), source_ref(missing_sha))

    assert derive.base_archive(data_root, sources) is None
    assert derive.derive_page(data_root, sources, None) is ComputedState.SOURCE_MISSING


def test_missing_extra_and_unknown_extra_are_skipped_like_load_pass(
    tmp_path: Path,
) -> None:
    data_root = _stage_and_sync(tmp_path)
    sources = _page_sources(data_root)
    assert len(sources) == 3
    existing = tuple(
        source
        for source in sources
        if archive_path(data_root, contract.sha_of_ref(source) or "").is_file()
    )
    assert len(existing) == 3
    base = existing[-1]
    missing_extra = source_ref("d" * 64)
    refs = ("foreign/source.fit", missing_extra, *existing[:-1], base)
    expected_activity = compose_listed(
        data_root,
        existing,
        parse_fit(
            archive_path(data_root, contract.sha_of_ref(base) or "").read_bytes()
        ),
    )

    result = derive.derive_page(data_root, refs, None)

    assert isinstance(result, derive.Derived)
    assert result.composition == expected_activity
    assert result.metrics == compute_metrics(expected_activity.activity, None)


@pytest.mark.parametrize("target", ["base", "extra"])
def test_oserror_reading_base_or_extra_returns_source_unreadable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, target: str
) -> None:
    data_root = _stage_and_sync(tmp_path)
    sources = _page_sources(data_root)
    assert len(sources) == 3
    base_path = derive.base_archive(data_root, sources)
    assert base_path is not None and base_path.is_file()
    extra_path = archive_path(data_root, contract.sha_of_ref(sources[0]) or "")
    assert extra_path.is_file()
    original_read_bytes = Path.read_bytes

    blocked_path = base_path if target == "base" else extra_path

    def deny(candidate: Path) -> bytes:
        if candidate == blocked_path:
            raise PermissionError("synthetic archive read denial")
        return original_read_bytes(candidate)

    monkeypatch.setattr(Path, "read_bytes", deny)
    result: ComputedState | derive.Derived | OSError
    try:
        result = derive.derive_page(data_root, sources, None)
    except OSError as error:
        result = error
    assert result is ComputedState.SOURCE_UNREADABLE


@pytest.mark.parametrize("target", ["base", "extra"])
def test_general_oserror_reading_base_or_extra_returns_source_unreadable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, target: str
) -> None:
    data_root = _stage_and_sync(tmp_path)
    sources = _page_sources(data_root)
    base_path = derive.base_archive(data_root, sources)
    assert base_path is not None and base_path.is_file()
    extra_path = archive_path(data_root, contract.sha_of_ref(sources[0]) or "")
    assert extra_path.is_file()
    blocked_path = base_path if target == "base" else extra_path
    original_read_bytes = Path.read_bytes

    def deny(candidate: Path) -> bytes:
        if candidate == blocked_path:
            raise OSError("synthetic general archive read error")
        return original_read_bytes(candidate)

    monkeypatch.setattr(Path, "read_bytes", deny)
    try:
        result: ComputedState | derive.Derived | OSError
        try:
            result = derive.derive_page(data_root, sources, None)
        except OSError as error:
            result = error
        assert result is ComputedState.SOURCE_UNREADABLE
    finally:
        monkeypatch.setattr(Path, "read_bytes", original_read_bytes)


def test_unreadable_base_archive_returns_source_unreadable(tmp_path: Path) -> None:
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        pytest.skip("chmod(0) does not deny read access to uid 0")
    data_root = _stage_and_sync(tmp_path)
    sources = _page_sources(data_root)
    base_path = derive.base_archive(data_root, sources)
    assert base_path is not None and base_path.is_file()
    original_mode = stat.S_IMODE(base_path.stat().st_mode)
    base_path.chmod(0)
    try:
        result: ComputedState | derive.Derived | OSError
        try:
            result = derive.derive_page(data_root, sources, None)
        except OSError as error:
            result = error
        assert result is ComputedState.SOURCE_UNREADABLE
    finally:
        base_path.chmod(original_mode)


@pytest.mark.parametrize("target", ["base", "extra"])
def test_fit_decode_error_in_base_or_extra_returns_source_undecodable(
    tmp_path: Path, target: str
) -> None:
    data_root = _stage_and_sync(tmp_path)
    sources = _page_sources(data_root)
    assert len(sources) == 3
    refs: Sequence[str]
    corrupt_sha = hashlib.sha256(b"not a FIT archive").hexdigest()
    corrupt_path = archive_path(data_root, corrupt_sha)
    if target == "base":
        base_sha = contract.sha_of_ref(sources[-1])
        assert base_sha is not None
        corrupt_path = archive_path(data_root, base_sha)
        corrupt_path.write_bytes(b"not a FIT archive")
        refs = sources
    else:
        corrupt_path.write_bytes(b"not a FIT archive")
        refs = (source_ref(corrupt_sha), *sources)
    assert corrupt_path.read_bytes() == b"not a FIT archive"

    result = derive.derive_page(data_root, refs, None)

    assert result is ComputedState.SOURCE_UNDECODABLE


def test_unexpected_metric_errors_propagate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    data_root = _stage_and_sync(tmp_path)
    sources = _page_sources(data_root)
    expected_error = RuntimeError("unexpected metric failure")

    def fail_metrics(
        _activity: object, _athlete: AthleteInputs | None
    ) -> DerivedMetrics:
        raise expected_error

    monkeypatch.setattr(derive, "compute_metrics", fail_metrics)

    with pytest.raises(RuntimeError) as caught:
        derive.derive_page(data_root, sources, None)
    assert caught.value is expected_error


@pytest.mark.parametrize("stage", ["parse_fit", "compose_listed"])
def test_unexpected_parse_and_compose_errors_propagate_by_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, stage: str
) -> None:
    data_root = _stage_and_sync(tmp_path)
    sources = _page_sources(data_root)
    expected_error = RuntimeError(f"unexpected {stage} failure")

    def fail_parse(_source: bytes | str | Path) -> Activity:
        raise expected_error

    def fail_compose(
        _data_root: Path, _sources: Sequence[str], _base: Activity
    ) -> Composition:
        raise expected_error

    if stage == "parse_fit":
        monkeypatch.setattr(derive, "parse_fit", fail_parse)
    else:
        monkeypatch.setattr(derive, "compose_listed", fail_compose)

    with pytest.raises(RuntimeError) as caught:
        derive.derive_page(data_root, sources, None)
    assert caught.value is expected_error


def test_public_function_annotations_match_design() -> None:
    assert get_type_hints(derive.base_archive) == {
        "data_root": Path,
        "sources": Sequence[str],
        "return": Path | None,
    }
    assert get_type_hints(derive.derive_page) == {
        "data_root": Path,
        "sources": Sequence[str],
        "athlete": AthleteInputs | None,
        "return": derive.Derived | ComputedState,
    }
