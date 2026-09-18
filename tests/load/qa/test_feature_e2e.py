"""Feature-level end-to-end validation of the activity-qa-flags feature (task
4.2, requirements 7.1, 7.3, 7.4, 7.6).

Drives the **real** pipeline -- :func:`fitdocs.sync.sync`, a real
``athlete.toml`` write via
:meth:`~fitdocs.load.profile.AthleteProfile.with_benchmark` /
:func:`~fitdocs.load.profile.save_profile`, and the real registered
:class:`~fitdocs.load.threshold.calculator.ThresholdCalculator` through
:func:`~fitdocs.load.engine.apply_load` -- so the four verdicts asserted here
are the ones the calculator's own call to
:func:`fitdocs.load.qa.evaluate_flags` actually produced for a real activity,
not a hand-built :class:`~fitdocs.load.types.LoadResult` fed straight to the
renderer. This file follows the construction pattern
``tests/load/threshold/test_feature_e2e.py`` establishes (see its module
docstring), scaled down to the single activity this task needs: one Run, long
enough and covered enough on pace/heart-rate to reach the computed path, with
one benchmark set on file. Cadence is deliberately absent -- a not-assessed
cadence-lock verdict is a realistic, typical outcome and needs no special
casing (see the task brief).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

from fitdocs.athlete import load_athlete_inputs
from fitdocs.benchmarks import BenchmarkKind
from fitdocs.docio import read_frontmatter
from fitdocs.layout import WORKOUTS_DIR
from fitdocs.load.docedit import RegionState, classify_load_region
from fitdocs.load.engine import apply_load
from fitdocs.load.profile import AthleteProfile, save_profile
from fitdocs.load.prompts import NonInteractiveSession
from fitdocs.load.qa import FLAG_ORDER, FlagKey
from fitdocs.load.render import LoadPayload, parse_payload
from fitdocs.load.types import LoadResult
from fitdocs.model import FIT_EPOCH, Sport
from fitdocs.sync import sync
from tests.fixtures import builder

# PINNED timezone (never the system zone) so document stems are byte-stable,
# matching the threshold feature's own e2e convention.
_TZ = timezone(timedelta(hours=-6))

# Long enough (600 s) to clear the shared 60 s default minimum duration with
# margin -- the same constant the threshold e2e suite uses.
_RECORD_COUNT = 601
_SPEED_MPS = 3.0
_ACTIVITY_DATE = date(2026, 6, 1)


class _ServingTiles:
    """The always-supplied basemap-tile source ``sync`` requires, matching
    ``tests/load/threshold/test_feature_e2e.py``'s own fixture. This run
    carries no GPS position, so ``resolve`` is never actually called -- it
    only needs to exist to satisfy ``sync``'s ``tiles`` parameter."""

    attribution = "© OpenStreetMap contributors"

    def resolve(self, refs: Sequence[object]) -> dict[object, bytes]:
        return {ref: b"\x89PNG\r\n\x1a\n" for ref in refs}


_TILES: _ServingTiles = _ServingTiles()


def _timestamp_offset_for(day: date) -> int:
    """A FIT-epoch offset (seconds from ``builder.FIT_TIMESTAMP_BASE``) that
    places a noon-local (``_TZ``) record on ``day``'s own calendar date once
    synced with ``tz=_TZ`` -- the same lever
    ``tests/load/threshold/test_feature_e2e.py`` uses, needed here so
    ``_ACTIVITY_DATE`` (what the written benchmarks are measured relative
    to) actually matches the recorded activity's own calendar date rather
    than silently landing on whatever date ``FIT_TIMESTAMP_BASE`` alone
    resolves to."""
    base_instant = FIT_EPOCH + timedelta(seconds=builder.FIT_TIMESTAMP_BASE)
    target_instant = datetime.combine(day, time(12, 0), tzinfo=_TZ)
    offset = (target_instant - base_instant).total_seconds()
    assert offset.is_integer()
    return int(offset)


def _run_fit_bytes() -> bytes:
    """A single, fully-covered outdoor run: continuous distance and heart
    rate, no power and no cadence -- enough for the pace channel (and heart
    rate, non-selected) to compute, while leaving the cadence-lock check
    nothing paired to detect against (an expected not-assessed outcome, not
    a gap in this fixture)."""
    base = builder.FIT_TIMESTAMP_BASE + _timestamp_offset_for(_ACTIVITY_DATE)
    mesgs: list[builder.Mesg] = [
        builder._file_id(9101),
        builder._device_info(9101, "SyntheticQaRunWatch"),
        {"mesg_num": builder._MESG_SPORT, "sport": "running", "sub_sport": "generic"},
    ]
    for i in range(_RECORD_COUNT):
        mesgs.append(
            {
                "mesg_num": builder._MESG_RECORD,
                "timestamp": base + i,
                "distance": _SPEED_MPS * i,
                "heart_rate": 140 + (i % 5),
            }
        )
    mesgs.append(
        {
            "mesg_num": builder._MESG_SESSION,
            "start_time": base,
            "timestamp": base + (_RECORD_COUNT - 1),
            "sport": "running",
            "sub_sport": "generic",
            "total_elapsed_time": float(_RECORD_COUNT - 1),
            "total_timer_time": float(_RECORD_COUNT - 1),
            "total_distance": _SPEED_MPS * (_RECORD_COUNT - 1),
            "avg_heart_rate": 140,
            "max_heart_rate": 144,
        }
    )
    mesgs.append(builder._activity(_RECORD_COUNT - 1, float(_RECORD_COUNT - 1)))
    return builder.encode(mesgs)


def _build_data_root(tmp_path: Path) -> Path:
    """Render a single run fixture into a temp data root via the real sync
    pipeline, matching ``tests/load/threshold/test_feature_e2e.py``'s
    ``_build_data_root``."""
    src = tmp_path / "src"
    data_root = tmp_path / "data"
    data_root.mkdir(parents=True)
    path = src / "run.fit"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_run_fit_bytes())
    sync(src, data_root, athlete=load_athlete_inputs(data_root), tz=_TZ, tiles=_TILES)
    return data_root


def _write_profile(data_root: Path) -> None:
    """A profile carrying the one benchmark the pace channel needs (Run
    threshold pace) plus the athlete-wide HR quantities every channel
    consults, so at least one benchmark is genuinely on file (task brief)."""
    profile = AthleteProfile(data={})
    profile = profile.with_benchmark(
        BenchmarkKind.THRESHOLD_PACE_S_PER_KM,
        discipline=Sport.RUN,
        value=300.0,
        measured_on=_ACTIVITY_DATE - timedelta(days=30),
    )
    profile = profile.with_benchmark(
        BenchmarkKind.LTHR_BPM,
        discipline=Sport.RUN,
        value=165.0,
        measured_on=_ACTIVITY_DATE - timedelta(days=30),
    )
    profile = profile.with_benchmark(
        BenchmarkKind.MAX_HR_BPM,
        discipline=None,
        value=190.0,
        measured_on=_ACTIVITY_DATE - timedelta(days=30),
    )
    profile = profile.with_benchmark(
        BenchmarkKind.RESTING_HR_BPM,
        discipline=None,
        value=50.0,
        measured_on=_ACTIVITY_DATE - timedelta(days=30),
    )
    save_profile(data_root, profile)


def _doc(data_root: Path) -> Path:
    matches = list((data_root / WORKOUTS_DIR).glob("*run*.md"))
    assert len(matches) == 1, f"expected exactly one run doc, found {matches}"
    return matches[0]


def _computed_payload(doc: Path) -> LoadPayload:
    classification = classify_load_region(doc.read_text(encoding="utf-8"))
    assert classification.state is RegionState.COMPUTED
    assert classification.payload is not None
    return classification.payload


def _computed_result(doc: Path) -> LoadResult:
    result = _computed_payload(doc).result
    assert result is not None
    return result


def test_real_load_pass_carries_verdicts_through_render_and_payload(
    tmp_path: Path,
) -> None:
    """A real load pass over a single-Run data root with one benchmark on
    file reaches the computed path, and the four verdicts this feature's
    real ``evaluate_flags`` produced travel through the real renderer:
    visibly, in the document's quality-flags block, and durably, in the
    embedded machine-readable payload comment -- both derived from the SAME
    real result the calculator returned, not reconstructed independently."""
    data_root = _build_data_root(tmp_path)
    _write_profile(data_root)
    doc = _doc(data_root)

    report = apply_load(data_root, session=NonInteractiveSession())

    # Live: the pass actually reached the computed path (not skipped/failed),
    # so every assertion below has a non-vacuous subject.
    assert [entry.doc for entry in report.computed] == [
        doc.relative_to(data_root).as_posix()
    ]
    assert report.unsupported == () and report.skipped == () and report.failures == ()

    result = _computed_result(doc)

    # The real calculator produced exactly the four flags this feature
    # defines, in FLAG_ORDER -- not a hand-built LoadResult's flags.
    assert len(result.flags) == 4
    assert tuple(flag.key for flag in result.flags) == tuple(
        key.value for key in FLAG_ORDER
    )
    assert {FlagKey(flag.key) for flag in result.flags} == set(FlagKey)
    for flag in result.flags:
        assert flag.verdict in ("detected", "not-detected", "not-assessed")
        assert flag.detail  # never empty

    doc_text = doc.read_text(encoding="utf-8")

    # 1. The rendered training-load section visibly carries the verdict
    # block with its four entries, matching the real result's own flags.
    assert "**Quality flags:**" in doc_text
    for flag in result.flags:
        assert f"**{flag.label}:** {flag.verdict} — {flag.detail}" in doc_text

    # 2. The embedded machine-readable payload comment round-trips them:
    # decoding the payload straight out of the document text yields a
    # LoadResult whose flags tuple is exactly the same four entries.
    decoded_payload = parse_payload(doc_text)
    assert decoded_payload is not None
    assert decoded_payload.status == "computed"
    assert decoded_payload.result is not None
    assert decoded_payload.result.flags == result.flags
    assert len(decoded_payload.result.flags) == 4

    # 3. No verdict appears in document frontmatter, and this feature
    # introduced no frontmatter key: none of the four FlagKey values, the
    # string "flags", or any verdict literal appears as a frontmatter key.
    frontmatter = read_frontmatter(doc)
    assert frontmatter is not None
    forbidden_keys = {key.value for key in FlagKey} | {
        "flags",
        "detected",
        "not-detected",
        "not-assessed",
    }
    assert forbidden_keys.isdisjoint(frontmatter.keys())

    # 4. Regenerating the same document over the same data root reproduces
    # it byte for byte.
    bytes_after_first = doc.read_bytes()
    apply_load(data_root, session=NonInteractiveSession())
    assert doc.read_bytes() == bytes_after_first

    # And a forced recompute -- a genuine independent re-computation, not
    # the restore-only path an untouched second pass takes -- reproduces the
    # same four verdicts and the same bytes too (Req 7.6).
    apply_load(data_root, session=NonInteractiveSession(), recompute=True)
    assert doc.read_bytes() == bytes_after_first
