"""Channel-merge end to end: the load and benchmark passes score the composition
(task 4.3; Req 6.1-6.6), over temporary data roots with the passes run directly.

The ride pair is the fixture: the Garmin original (the page's base) records
power and no heart rate, the phone copy (an extra) records the heart rate. A
pass that read the base alone sees no heart rate; one that composes sees the
copy's values.
"""

from __future__ import annotations

import hashlib
import re
from datetime import date, timedelta, timezone
from pathlib import Path

import pytest

import fitdocs.load.engine as load_engine
import fitdocs.performance.engine as performance_engine
from fitdocs import Activity, Sport, parse_fit
from fitdocs.benchmarks import BenchmarkKind
from fitdocs.declaration import DECLARATION_FILENAME
from fitdocs.docmerge import begin_marker, end_marker
from fitdocs.layout import WORKOUTS_DIR, archive_path
from fitdocs.load.engine import LoadReport, apply_load
from fitdocs.load.profile import AthleteProfile, save_profile
from fitdocs.load.prompts import NonInteractiveSession
from fitdocs.load.render import parse_payload
from fitdocs.performance.engine import DeriveReport, derive_benchmarks
from fitdocs.sync import SyncReport, sync
from tests.fixtures import merge

_TZ = timezone(timedelta(hours=-6))

# The copy's heart rate by the fixture's own formula (merge.py: 90 + 3 * (g % 34)
# over 102 samples), written here so the pins do not decode the file they check.
_DONATED_HEART_RATE = tuple(90 + 3 * (g % 34) for g in range(102))


class _NoTiles:
    attribution = "test"

    def resolve(self, refs: object) -> dict[object, bytes]:
        return {ref: b"\x89PNG\r\n\x1a\n" for ref in refs}  # type: ignore[attr-defined]


def _stage(source: Path, **files: bytes) -> Path:
    source.mkdir(parents=True, exist_ok=True)
    for name, data in files.items():
        (source / f"{name}.fit").write_bytes(data)
    return source


def _sync(source: Path, data_root: Path) -> SyncReport:
    report = sync(source, data_root, athlete=None, tz=_TZ, tiles=_NoTiles())  # type: ignore[arg-type]
    assert report.failures == ()
    return report


def _only_page(data_root: Path) -> Path:
    pages = [
        p
        for p in sorted((data_root / WORKOUTS_DIR).glob("*.md"))
        if p.name != DECLARATION_FILENAME
    ]
    assert len(pages) == 1, [p.name for p in pages]
    return pages[0]


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write_profile(data_root: Path) -> None:
    """A cycling FTP and LTHR and athlete-wide max and resting heart rate, so the
    heart-rate channel can be scored whenever the activity has heart rate."""
    on = date(2020, 1, 1)
    profile = AthleteProfile(data={})
    profile = profile.with_benchmark(
        BenchmarkKind.FTP_WATTS, discipline=Sport.RIDE, value=250.0, measured_on=on
    )
    profile = profile.with_benchmark(
        BenchmarkKind.LTHR_BPM, discipline=Sport.RIDE, value=170.0, measured_on=on
    )
    profile = profile.with_benchmark(
        BenchmarkKind.MAX_HR_BPM, discipline=None, value=190.0, measured_on=on
    )
    profile = profile.with_benchmark(
        BenchmarkKind.RESTING_HR_BPM, discipline=None, value=50.0, measured_on=on
    )
    save_profile(data_root, profile)


def _tag_hard(page: Path) -> None:
    """Add an effort tag to the page's frontmatter, by one line before ``sources``."""
    text = page.read_text(encoding="utf-8")
    assert text.count("\nsources:\n") == 1
    page.write_text(
        text.replace("\nsources:\n", "\neffort: hard\nsources:\n"), encoding="utf-8"
    )


def _ride_root(tmp_path: Path, label: str) -> Path:
    """A data root holding the ride pair's one page (Garmin base, copy extra)."""
    garmin, copy = merge.ride_pair_fit_bytes()
    data_root = tmp_path / label / "data"
    data_root.mkdir(parents=True)
    _sync(_stage(tmp_path / label / "work", garmin=garmin, copy=copy), data_root)
    _write_profile(data_root)
    _tag_hard(_only_page(data_root))
    return data_root


def _copy_archive(data_root: Path) -> Path:
    return archive_path(data_root, _sha(merge.ride_pair_fit_bytes()[1]))


def _run_load(data_root: Path) -> LoadReport:
    return apply_load(
        data_root, session=NonInteractiveSession(), today=date(2042, 5, 1)
    )


def _spy_load(monkeypatch: pytest.MonkeyPatch) -> list[Activity]:
    seen: list[Activity] = []
    real = getattr(load_engine, "compute_metrics")  # noqa: B009

    def spy(activity: Activity, *args: object, **kwargs: object) -> object:
        seen.append(activity)
        return real(activity, *args, **kwargs)

    monkeypatch.setattr(load_engine, "compute_metrics", spy)
    return seen


def _spy_derive(monkeypatch: pytest.MonkeyPatch) -> list[Activity]:
    seen: list[Activity] = []
    real = getattr(performance_engine, "derive")  # noqa: B009

    def spy(activity: Activity, *args: object, **kwargs: object) -> object:
        seen.append(activity)
        return real(activity, *args, **kwargs)

    monkeypatch.setattr(performance_engine, "derive", spy)
    return seen


def _run_benchmarks(data_root: Path) -> DeriveReport:
    return derive_benchmarks(data_root, dry_run=True)


def _heart_rate_of(activity: Activity) -> tuple[int | None, ...]:
    return tuple(activity.samples.heart_rate_bpm)


def _load_region(text: str) -> str:
    start = text.index(begin_marker("load"))
    return text[start : text.index(end_marker("load")) + len(end_marker("load"))]


def _heart_rate_load_value(text: str) -> float | None:
    """The page's heart-rate load (the non-selected entry; power is selected)."""
    payload = parse_payload(_load_region(text))
    assert payload is not None and payload.result is not None
    entries = [e for e in payload.result.non_selected if e.key == "heart_rate"]
    assert len(entries) == 1
    return entries[0].value


# --- preconditions: the premise of every pin below is false without composition


def test_the_base_records_no_heart_rate_and_the_copy_records_the_donated_values() -> (
    None
):
    garmin, copy = merge.ride_pair_fit_bytes()
    assert _sha(garmin) != _sha(copy)
    assert all(v is None for v in _heart_rate_of(parse_fit(garmin)))
    assert len(set(_DONATED_HEART_RATE)) == 34  # pairwise distinct within a stretch
    assert _heart_rate_of(parse_fit(copy)) == _DONATED_HEART_RATE


# --- the load pass (Req 6.1, 6.5) ---------------------------------------------


def test_the_load_pass_computes_metrics_from_the_composed_activity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Req 6.1. Mutation: skip the adapter in the load pass (the metrics call
    receives the base, whose heart rate is absent)."""
    data_root = _ride_root(tmp_path, "pair")
    seen = _spy_load(monkeypatch)
    report = _run_load(data_root)
    assert report.failures == ()
    assert len(report.computed) == 1
    assert len(seen) == 1
    assert _heart_rate_of(seen[0]) == _DONATED_HEART_RATE


def test_the_ride_page_load_is_computed_with_heart_rate_available(
    tmp_path: Path,
) -> None:
    """Req 6.1, 6.5: against the base alone the heart-rate load is not computable
    (None); on the composed page it is. Mutation: skip the adapter in the load
    pass."""
    garmin, _copy = merge.ride_pair_fit_bytes()
    alone = tmp_path / "alone" / "data"
    alone.mkdir(parents=True)
    _sync(_stage(tmp_path / "alone" / "work", garmin=garmin), alone)
    _write_profile(alone)
    assert _run_load(alone).failures == ()
    assert _heart_rate_load_value(_only_page(alone).read_text("utf-8")) is None

    data_root = _ride_root(tmp_path, "pair")
    assert _run_load(data_root).failures == ()
    value = _heart_rate_load_value(_only_page(data_root).read_text("utf-8"))
    assert value is not None and value > 0


def test_with_the_copys_archive_file_removed_the_load_pass_composes_from_the_base(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Req 6.3. Mutation: delete the missing-file skip in ``compose_listed``."""
    data_root = _ride_root(tmp_path, "pair")
    copy_file = _copy_archive(data_root)
    assert copy_file.is_file()
    copy_file.unlink()
    seen = _spy_load(monkeypatch)
    report = _run_load(data_root)
    assert report.failures == ()
    assert len(report.computed) == 1
    assert len(seen) == 1
    assert all(v is None for v in _heart_rate_of(seen[0]))


def test_a_truncated_copy_is_a_per_document_load_failure_and_the_page_is_untouched(
    tmp_path: Path,
) -> None:
    """Req 6.4. Mutation: catch the adapter's decode error in the load pass (the
    page is then computed from the base alone, no failure)."""
    data_root = _ride_root(tmp_path, "pair")
    copy_file = _copy_archive(data_root)
    copy_file.write_bytes(copy_file.read_bytes()[:40])
    page = _only_page(data_root)
    before = page.read_bytes()
    report = _run_load(data_root)
    assert [e.doc for e in report.failures] == [page.relative_to(data_root).as_posix()]
    assert report.computed == ()
    assert page.read_bytes() == before


def test_an_undecodable_extra_is_reported_as_an_undecodable_base_is(
    tmp_path: Path,
) -> None:
    """Req 6.4: the failure detail for a truncated extra equals the detail for
    a base truncated the same way, and names the decode error. Mutation: wrap
    the adapter in ``try/except Exception: raise ValueError(...) from None`` in
    the load pass."""
    extra_root = _ride_root(tmp_path, "extra")
    copy_file = _copy_archive(extra_root)
    copy_file.write_bytes(copy_file.read_bytes()[:40])
    extra_failures = _run_load(extra_root).failures

    base_root = _ride_root(tmp_path, "base")
    garmin_file = archive_path(base_root, _sha(merge.ride_pair_fit_bytes()[0]))
    garmin_file.write_bytes(garmin_file.read_bytes()[:40])
    base_failures = _run_load(base_root).failures

    assert len(extra_failures) == len(base_failures) == 1
    assert extra_failures[0].detail.startswith("FitIntegrityError:")
    assert extra_failures[0].detail == base_failures[0].detail


# --- the benchmark pass (Req 6.2, 6.4) ----------------------------------------


def test_the_benchmark_pass_derives_from_the_composed_activity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Req 6.2. Mutation: skip the adapter in the benchmark pass."""
    data_root = _ride_root(tmp_path, "pair")
    seen = _spy_derive(monkeypatch)
    report = _run_benchmarks(data_root)
    assert report.failures == ()
    assert len(seen) == 1
    assert _heart_rate_of(seen[0]) == _DONATED_HEART_RATE


def test_with_the_copys_archive_file_removed_the_benchmark_pass_composes_from_the_base(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Req 6.3. Mutation: delete the missing-file skip in ``compose_listed``."""
    data_root = _ride_root(tmp_path, "pair")
    copy_file = _copy_archive(data_root)
    assert copy_file.is_file()
    copy_file.unlink()
    seen = _spy_derive(monkeypatch)
    report = _run_benchmarks(data_root)
    assert report.failures == ()
    assert len(seen) == 1
    assert all(v is None for v in _heart_rate_of(seen[0]))


def test_a_truncated_copy_is_a_per_document_benchmark_failure_and_the_page_is_untouched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Req 6.4. Mutation: call the adapter outside the pass's ``try`` (the decode
    error escapes the pass instead of becoming a failure)."""
    data_root = _ride_root(tmp_path, "pair")
    copy_file = _copy_archive(data_root)
    copy_file.write_bytes(copy_file.read_bytes()[:40])
    page = _only_page(data_root)
    before = page.read_bytes()
    seen = _spy_derive(monkeypatch)
    report = _run_benchmarks(data_root)
    assert [f.document for f in report.failures] == [
        page.relative_to(data_root).as_posix()
    ]
    assert report.failures[0].reason.startswith("undecodable archive for ")
    assert seen == []
    assert page.read_bytes() == before


# --- a computed load is kept (Req 6.6) ----------------------------------------


def test_a_load_computed_before_the_copy_arrived_survives_a_later_sync_and_load_pass(
    tmp_path: Path,
) -> None:
    """Req 6.6. The Garmin original is synced and scored alone; the copy then
    arrives and re-renders the page; the chained load pass restores, never
    recomputes. Mutation: recompute every region in the load pass
    (``recompute`` forced true)."""
    garmin, copy = merge.ride_pair_fit_bytes()
    data_root = tmp_path / "data"
    data_root.mkdir()
    _sync(_stage(tmp_path / "a", garmin=garmin), data_root)
    _write_profile(data_root)
    page = _only_page(data_root)
    assert _run_load(data_root).failures == ()
    before_text = page.read_text("utf-8")
    before_region = _load_region(before_text)
    assert _heart_rate_load_value(before_text) is None

    # The control: the pair scored as one gives a different load region, so the
    # equality below is not a region that composition leaves unchanged anyway.
    control = _ride_root(tmp_path, "control")
    assert _run_load(control).failures == ()
    assert _load_region(_only_page(control).read_text("utf-8")) != before_region

    _sync(_stage(tmp_path / "b", copy=copy), data_root)
    synced = page.read_text("utf-8")
    assert "## Channel Sources" in synced  # the copy joined the page
    assert _load_region(synced) == before_region

    report = _run_load(data_root)
    assert report.failures == ()
    assert report.computed == ()
    after = page.read_text("utf-8")
    assert _load_region(after) == before_region
    assert re.findall(r"^load_\w+: .*$", after, re.MULTILINE) == re.findall(
        r"^load_\w+: .*$", before_text, re.MULTILINE
    )


# --- ranking order through the passes (Req 6.1, 6.2) --------------------------

# Form power by the fixture's formula (merge.py: 50 + 2 * ((5 * g) % 13)); stryd_b
# records one watt more at every sample, so its values are the odd ones and
# stryd_a's the even ones.
_FORM_POWER_A = {float(50 + 2 * k) for k in range(13)}
_FORM_POWER_B = {float(51 + 2 * k) for k in range(13)}


def _trio_root(tmp_path: Path) -> Path:
    healthfit, stryd_a, stryd_b = merge.run_trio_fit_bytes()
    data_root = tmp_path / "trio" / "data"
    data_root.mkdir(parents=True)
    _sync(
        _stage(
            tmp_path / "trio" / "work",
            healthfit=healthfit,
            stryd_a=stryd_a,
            stryd_b=stryd_b,
        ),
        data_root,
    )
    on = date(2020, 1, 1)
    profile = AthleteProfile(data={}).with_benchmark(
        BenchmarkKind.FTP_WATTS, discipline=Sport.RUN, value=250.0, measured_on=on
    )
    profile = profile.with_benchmark(
        BenchmarkKind.LTHR_BPM, discipline=Sport.RUN, value=170.0, measured_on=on
    )
    save_profile(data_root, profile)
    _tag_hard(_only_page(data_root))
    return data_root


def _form_power_values(activity: Activity) -> set[float]:
    return {v for v in activity.samples.form_power_w if v is not None}


def test_the_load_pass_ranks_the_later_stryd_file_first(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Req 6.1: the page lists the files in ascending rank, base last; the pass
    gives form power from stryd_b, the highest-ranked extra. Mutation: reverse
    the extras in ``_listed_refs``."""
    data_root = _trio_root(tmp_path)
    seen = _spy_load(monkeypatch)
    assert _run_load(data_root).failures == ()
    assert len(seen) == 1
    values = _form_power_values(seen[0])
    assert len(values) > 5
    assert values <= _FORM_POWER_B
    assert not values & _FORM_POWER_A


def test_the_benchmark_pass_ranks_the_later_stryd_file_first(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Req 6.2. Mutation: reverse the extras in the refs the benchmark pass
    hands to ``compose_listed``."""
    data_root = _trio_root(tmp_path)
    seen = _spy_derive(monkeypatch)
    assert _run_benchmarks(data_root).failures == ()
    assert len(seen) == 1
    values = _form_power_values(seen[0])
    assert len(values) > 5
    assert values <= _FORM_POWER_B
    assert not values & _FORM_POWER_A
