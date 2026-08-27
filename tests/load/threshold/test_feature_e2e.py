"""Feature-level end-to-end validation of the threshold calculator (task 5.3,
design.md ``## Testing Strategy`` -- ``### E2E Tests``, requirements 1.3, 1.4,
7.8, 7.9, 8.9).

Every scenario below drives the **real** sync pipeline
(:func:`fitdocs.sync.sync`), the **real** ``athlete.toml`` write path
(:meth:`~fitdocs.load.profile.AthleteProfile.with_benchmark` +
:func:`~fitdocs.load.profile.save_profile`), and the **registered built-in**
:class:`~fitdocs.load.threshold.calculator.ThresholdCalculator` through
:func:`~fitdocs.load.engine.apply_load` (and, for the configuration-gate
scenario, the ``fitdocs load`` CLI command) -- no stub calculator, no stub
profile, no hand-built ``Activity``. This is the one place in the feature's
own test suite that composes a real multi-sport data root, a real populated
benchmark store, and the real registered calculator together; every sibling
suite drives at most two of those three for real
(``test_benchmark_selection_e2e.py`` real store + stub calculator;
``test_anchoring_e2e.py``/``test_outcomes.py`` real calculator + hand-built
profile double).

Six sports share one data root for the first scenario: Run, Ride, Walk and
Hike are all built long enough (600 s, well over the 60 s default minimum)
and fully covered so every declared anchor is on file and all four compute;
Strength (``Modality.STRENGTH``, never a declared modality) and Rowing
(``Modality.OTHER``, declared but outside ``SUPPORTED_SPORTS``) both reach
``report.unsupported`` through the SAME path: arbitration's own
``NoCalculator`` outcome (``engine.py:473-475``). With only the threshold
calculator registered and no forced/default calculator configured,
``arbitrate`` (``arbitrate.py:134-143``) asks
:func:`~fitdocs.load.types.supports_activity` itself while narrowing
candidates and finds none for either sport, so it returns ``NoCalculator``
before the engine's own post-arbitration support check
(``engine.py:491-493``) is ever reached by this scenario. Both land in the
same bucket and both name ``activity.sport.value`` (``"Workout"`` for
Strength -- ``Sport`` has no STRENGTH member of its own, only ``Modality``
does; ``"Rowing"`` for Rowing). Exercising the engine's OWN supports-check
refusal (as opposed to arbitration's) would need a second registered
calculator or a forced ``--calculator threshold``, either of which is out
of this task's scope -- that coverage belongs to 5.2's suite, not here.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

import pytest
from typer.testing import CliRunner

from fitdocs import cli
from fitdocs.athlete import load_athlete_inputs
from fitdocs.benchmarks import BenchmarkKind
from fitdocs.cli import app
from fitdocs.docio import read_frontmatter
from fitdocs.layout import WORKOUTS_DIR
from fitdocs.load import engine as load_engine
from fitdocs.load.docedit import RegionState, classify_load_region
from fitdocs.load.engine import DocLoadEntry, LoadReport, apply_load
from fitdocs.load.profile import AthleteProfile, save_profile
from fitdocs.load.prompts import NonInteractiveSession
from fitdocs.load.types import LoadResult, NonSelectedValue
from fitdocs.model import FIT_EPOCH, Sport
from fitdocs.settings import SettingsError
from fitdocs.sync import sync
from tests.fixtures import builder

runner = CliRunner()

# PINNED timezone (never the system zone) so document stems are byte-stable.
_TZ = timezone(timedelta(hours=-6))

# Long enough (600 s) to clear the shared 60 s default minimum duration with
# margin, so a config that tightens the minimum can be chosen deliberately
# (task bullet 2) without accidentally starving the baseline pass too.
_RECORD_COUNT = 601
_SPEED_MPS = 3.0

_ACTIVITY_DATE = date(2026, 6, 1)


class _ServingTiles:
    """The always-supplied basemap-tile source these setup runs inject."""

    attribution = "© OpenStreetMap contributors"

    def resolve(self, refs: Sequence[object]) -> dict[object, bytes]:
        return {ref: b"\x89PNG\r\n\x1a\n" for ref in refs}


_TILES: _ServingTiles = _ServingTiles()


# --- fixture builders (self-contained; this file borrows no helper from a
# sibling test module) ---------------------------------------------------


def _timestamp_offset_for(day: date) -> int:
    """A FIT-epoch offset (seconds from ``builder.FIT_TIMESTAMP_BASE``) that
    places a noon-local (``_TZ``) record on ``day``'s own calendar date once
    synced with ``tz=_TZ`` -- the same lever
    ``test_benchmark_selection_e2e.py`` uses to control an activity's own
    recorded date deliberately.

    Computed from real datetime arithmetic (via :data:`~fitdocs.model.
    FIT_EPOCH`, the same conversion ``fit_datetime`` applies) rather than a
    hand-derived day-count, so this can never again silently overflow into
    the next local calendar date the way a fixed "+18h" offset from
    ``FIT_TIMESTAMP_BASE`` did (``FIT_TIMESTAMP_BASE`` resolves to
    2021-09-07 19:46:40 in ``_TZ``, not midnight)."""
    base_instant = FIT_EPOCH + timedelta(seconds=builder.FIT_TIMESTAMP_BASE)
    target_instant = datetime.combine(day, time(12, 0), tzinfo=_TZ)
    offset = (target_instant - base_instant).total_seconds()
    assert offset.is_integer()
    return int(offset)


def _long_fit_bytes(
    serial: int,
    fit_sport: str,
    *,
    sub_sport: str = "generic",
    day: date = _ACTIVITY_DATE,
    record_count: int = _RECORD_COUNT,
    speed_mps: float = _SPEED_MPS,
    hr_base: int = 140,
    power_w: int | None = None,
    hr_gap: tuple[int, int] | None = None,
) -> bytes:
    """A long, fully-covered (or, with ``hr_gap``, partially covered) FIT
    fixture: continuous ``distance`` and (when ``power_w`` is set) continuous
    ``power``, heart rate continuous except inside the half-open ``hr_gap``
    index range -- the one lever this file needs to make one channel's
    coverage fall strictly between the default and a tightened minimum.
    """
    base = builder.FIT_TIMESTAMP_BASE + _timestamp_offset_for(day)
    mesgs: list[builder.Mesg] = [
        builder._file_id(serial),
        builder._device_info(serial, f"Synthetic{fit_sport.title()}Watch"),
        {"mesg_num": builder._MESG_SPORT, "sport": fit_sport, "sub_sport": sub_sport},
    ]
    for i in range(record_count):
        record: builder.Mesg = {
            "mesg_num": builder._MESG_RECORD,
            "timestamp": base + i,
            "distance": speed_mps * i,
        }
        if hr_gap is None or not (hr_gap[0] <= i < hr_gap[1]):
            record["heart_rate"] = hr_base + (i % 5)
        if power_w is not None:
            record["power"] = power_w
        mesgs.append(record)
    session: builder.Mesg = {
        "mesg_num": builder._MESG_SESSION,
        "start_time": base,
        "timestamp": base + (record_count - 1),
        "sport": fit_sport,
        "sub_sport": sub_sport,
        "total_elapsed_time": float(record_count - 1),
        "total_timer_time": float(record_count - 1),
        "total_distance": speed_mps * (record_count - 1),
        "avg_heart_rate": hr_base,
        "max_heart_rate": hr_base + 4,
    }
    if power_w is not None:
        session["avg_power"] = power_w
        session["max_power"] = power_w
    mesgs.append(session)
    mesgs.append(builder._activity(record_count - 1, float(record_count - 1)))
    return builder.encode(mesgs)


def _run_fit_bytes(*, hr_gap: tuple[int, int] | None = None) -> bytes:
    return _long_fit_bytes(6101, "running", power_w=250, hr_gap=hr_gap)


def _ride_fit_bytes() -> bytes:
    return _long_fit_bytes(6102, "cycling", power_w=210, hr_base=150)


def _walk_fit_bytes() -> bytes:
    return _long_fit_bytes(6103, "walking", speed_mps=1.4, hr_base=110)


def _hike_fit_bytes() -> bytes:
    return _long_fit_bytes(6104, "hiking", speed_mps=1.2, hr_base=115)


def _standard_fixtures() -> dict[str, bytes]:
    return {
        "run.fit": _run_fit_bytes(),
        "ride.fit": _ride_fit_bytes(),
        "walk.fit": _walk_fit_bytes(),
        "hike.fit": _hike_fit_bytes(),
        "strength.fit": builder.strength_fit_bytes(),
        "row.fit": builder.small_sport_fit_bytes(6105, "rowing"),
    }


def _build_data_root(tmp_path: Path, fixtures: dict[str, bytes]) -> Path:
    """Render ``fixtures`` into a temp data root via the real sync pipeline."""
    src = tmp_path / "src"
    data_root = tmp_path / "data"
    data_root.mkdir(parents=True)
    for name, data in fixtures.items():
        path = src / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    sync(src, data_root, athlete=load_athlete_inputs(data_root), tz=_TZ, tiles=_TILES)
    return data_root


def _populated_profile(
    *,
    run_ftp: float | None = 250.0,
    ride_ftp: float = 210.0,
    run_lthr: float = 165.0,
    ride_lthr: float = 160.0,
    max_hr: float = 190.0,
    resting_hr: float = 50.0,
) -> AthleteProfile:
    """A profile carrying every benchmark all four supported disciplines need
    (Run/Ride FTP + LTHR of their own; Walk/Hike borrow Run's LTHR since no
    Walk/Hike LTHR is recorded here -- the borrowing chain
    ``discipline.ANCHOR_PLANS`` documents) plus the two athlete-wide
    heart-rate quantities every channel needs. ``run_ftp=None`` omits the Run
    FTP entry entirely -- for a caller (the two-entry latest-wins scenario)
    that must control every Run FTP entry on file itself, since
    :meth:`~fitdocs.load.profile.AthleteProfile.with_benchmark` ADDS an entry
    keyed by ``(discipline, kind, measured_on)`` rather than replacing a
    same-kind entry dated differently -- a default entry here would silently
    become a second, contaminating entry in that scenario."""
    profile = AthleteProfile(data={})
    if run_ftp is not None:
        profile = profile.with_benchmark(
            BenchmarkKind.FTP_WATTS,
            discipline=Sport.RUN,
            value=run_ftp,
            measured_on=_ACTIVITY_DATE - timedelta(days=30),
        )
    profile = profile.with_benchmark(
        BenchmarkKind.FTP_WATTS,
        discipline=Sport.RIDE,
        value=ride_ftp,
        measured_on=_ACTIVITY_DATE - timedelta(days=30),
    )
    profile = profile.with_benchmark(
        BenchmarkKind.LTHR_BPM,
        discipline=Sport.RUN,
        value=run_lthr,
        measured_on=_ACTIVITY_DATE - timedelta(days=30),
    )
    profile = profile.with_benchmark(
        BenchmarkKind.LTHR_BPM,
        discipline=Sport.RIDE,
        value=ride_lthr,
        measured_on=_ACTIVITY_DATE - timedelta(days=30),
    )
    profile = profile.with_benchmark(
        BenchmarkKind.THRESHOLD_PACE_S_PER_KM,
        discipline=Sport.RUN,
        value=300.0,
        measured_on=_ACTIVITY_DATE - timedelta(days=30),
    )
    profile = profile.with_benchmark(
        BenchmarkKind.MAX_HR_BPM,
        discipline=None,
        value=max_hr,
        measured_on=_ACTIVITY_DATE - timedelta(days=30),
    )
    profile = profile.with_benchmark(
        BenchmarkKind.RESTING_HR_BPM,
        discipline=None,
        value=resting_hr,
        measured_on=_ACTIVITY_DATE - timedelta(days=30),
    )
    return profile


def _write_profile(data_root: Path, profile: AthleteProfile) -> None:
    save_profile(data_root, profile)


def _write_settings(data_root: Path, text: str) -> None:
    (data_root / "fitdocs.toml").write_text(text, encoding="utf-8")


def _doc(data_root: Path, needle: str) -> Path:
    matches = [p for p in (data_root / WORKOUTS_DIR).glob("*.md") if needle in p.name]
    assert len(matches) == 1, f"expected exactly one {needle!r} doc, found {matches}"
    return matches[0]


def _rel(data_root: Path, doc: Path) -> str:
    return doc.relative_to(data_root).as_posix()


def _docs_of(entries: tuple[DocLoadEntry, ...]) -> set[str]:
    return {entry.doc for entry in entries}


def _snapshot(data_root: Path) -> dict[str, bytes]:
    return {
        p.relative_to(data_root).as_posix(): p.read_bytes()
        for p in sorted(data_root.rglob("*"))
        if p.is_file()
    }


def _computed_result(doc: Path) -> LoadResult:
    """The decoded, computed :class:`LoadResult` embedded in ``doc``'s load
    region -- asserts the region is genuinely COMPUTED first, so a caller
    reading ``.basis``/``.value``/``.non_selected`` off it never silently
    reads ``None``."""
    classification = classify_load_region(doc.read_text(encoding="utf-8"))
    assert classification.state is RegionState.COMPUTED
    assert classification.payload is not None
    result = classification.payload.result
    assert result is not None
    return result


def _basis_of(doc: Path) -> str:
    return _computed_result(doc).basis


def _non_selected_entry(doc: Path, key: str) -> NonSelectedValue:
    matches = [
        entry for entry in _computed_result(doc).non_selected if entry.key == key
    ]
    assert len(matches) == 1, f"expected exactly one {key!r} entry, found {matches}"
    return matches[0]


def _non_selected_value(doc: Path, key: str) -> float | None:
    return _non_selected_entry(doc, key).value


# ---------------------------------------------------------------------------
# Scenario 1: a real load pass over Run, Ride, Walk, Hike, Strength, Rowing
# (Req 1.3, 1.4 -- the built-in computes for real, deterministically)
# ---------------------------------------------------------------------------


def test_real_pass_scores_four_disciplines_and_refuses_strength_and_rowing(
    tmp_path: Path,
) -> None:
    """A real data root holding Run, Ride, Walk, Hike, Strength and Rowing,
    with a populated benchmark file, produces exactly the report the design
    doc's own multi-document E2E scenario names: four computed documents
    carrying the expected channel basis each, and Strength/Rowing landing in
    the same ``unsupported`` bucket, each naming its own sport."""
    data_root = _build_data_root(tmp_path, _standard_fixtures())
    _write_profile(data_root, _populated_profile())

    run = _doc(data_root, "run")
    ride = _doc(data_root, "ride")
    walk = _doc(data_root, "walk")
    hike = _doc(data_root, "hike")
    strength = _doc(data_root, "strength")
    row = _doc(data_root, "row")

    report = apply_load(data_root, session=NonInteractiveSession())

    assert isinstance(report, LoadReport)
    assert _docs_of(report.computed) == {
        _rel(data_root, run),
        _rel(data_root, ride),
        _rel(data_root, walk),
        _rel(data_root, hike),
    }
    assert _docs_of(report.unsupported) == {
        _rel(data_root, strength),
        _rel(data_root, row),
    }
    assert report.skipped == () and report.failures == () and report.restored == ()

    # The four computed documents each select the discipline's default-order
    # first available channel: Run -> pace, Ride -> power, Walk/Hike -> the
    # only channel they ever have (heart rate).
    assert _basis_of(run) == "pace"
    assert _basis_of(ride) == "power"
    assert _basis_of(walk) == "heart_rate"
    assert _basis_of(hike) == "heart_rate"

    # Strength (Modality.STRENGTH, never declared) and Rowing (Modality.OTHER,
    # declared but Sport.ROWING is outside SUPPORTED_SPORTS) reach the same
    # unsupported bucket through the SAME path -- arbitration's own
    # NoCalculator outcome (engine.py:473-475; arbitrate.py:134-143) -- both
    # naming ``activity.sport.value`` (Req 2.2, 2.3): Strength surfaces as
    # "Workout" (Sport carries no STRENGTH member of its own -- only Modality
    # does) and Rowing surfaces as "Rowing". Neither exercises the engine's
    # own post-arbitration supports check (engine.py:491-493); see the module
    # docstring.
    strength_classification = classify_load_region(strength.read_text(encoding="utf-8"))
    row_classification = classify_load_region(row.read_text(encoding="utf-8"))
    assert strength_classification.state is RegionState.UNSUPPORTED
    assert row_classification.state is RegionState.UNSUPPORTED
    assert strength_classification.payload is not None
    assert row_classification.payload is not None
    assert strength_classification.payload.sport == "Workout"
    assert row_classification.payload.sport == "Rowing"


# ---------------------------------------------------------------------------
# Scenario 1b: closing the "real store + real calculator, two-entry
# benchmark set" seam the task brief names -- the store's latest-measured-
# wins rule proven end to end through this feature's own selection path.
# ---------------------------------------------------------------------------


def test_two_qualifying_ftp_entries_the_store_selects_the_latest_measured(
    tmp_path: Path,
) -> None:
    """A single quantity (Run FTP) carries two entries that both qualify (both
    measured on or before the activity's own date): an old, low value and a
    newer, higher one. The real :class:`~fitdocs.benchmarks.BenchmarkSet`'s
    "most recently measured wins" rule (``benchmarks.py:152``) is exercised
    end to end through :class:`~fitdocs.load.threshold.anchors` and the
    power channel: the two-entry data root's Run power-channel number equals
    a control data root carrying ONLY the newer entry, and differs from a
    second control carrying ONLY the older one -- proved comparatively rather
    than by predicting the real normalized-power algorithm's exact output,
    which this file does not reimplement."""
    old_value, new_value = 200.0, 250.0
    old_date = _ACTIVITY_DATE - timedelta(days=60)
    new_date = _ACTIVITY_DATE - timedelta(days=5)

    def _root_with_ftp_entries(
        label: str, entries: Sequence[tuple[float, date]]
    ) -> Path:
        root = _build_data_root(tmp_path / label, {"run.fit": _run_fit_bytes()})
        profile = _populated_profile(run_ftp=None)
        for value, measured_on in entries:
            profile = profile.with_benchmark(
                BenchmarkKind.FTP_WATTS,
                discipline=Sport.RUN,
                value=value,
                measured_on=measured_on,
            )
        _write_profile(root, profile)
        return root

    # Two configured priorities so the run's SELECTED channel is power, not
    # pace -- the number under test must be the one written to load_value,
    # not merely a non-selected diagnostic, so a mutation to how a selected
    # value is assembled would also be caught.
    power_first_settings = '[load.priority]\nrun = ["power", "pace", "heart_rate"]\n'

    root_old_only = _root_with_ftp_entries("old-only", [(old_value, old_date)])
    _write_settings(root_old_only, power_first_settings)
    root_new_only = _root_with_ftp_entries("new-only", [(new_value, new_date)])
    _write_settings(root_new_only, power_first_settings)
    root_both = _root_with_ftp_entries(
        "both", [(old_value, old_date), (new_value, new_date)]
    )
    _write_settings(root_both, power_first_settings)

    report_old = apply_load(root_old_only, session=NonInteractiveSession())
    report_new = apply_load(root_new_only, session=NonInteractiveSession())
    report_both = apply_load(root_both, session=NonInteractiveSession())

    run_old = _doc(root_old_only, "run")
    run_new = _doc(root_new_only, "run")
    run_both = _doc(root_both, "run")

    # Live: all three passes actually computed the run (not, say, all three
    # silently skipping it, which would make the equalities below vacuous).
    assert _docs_of(report_old.computed) == {_rel(root_old_only, run_old)}
    assert _docs_of(report_new.computed) == {_rel(root_new_only, run_new)}
    assert _docs_of(report_both.computed) == {_rel(root_both, run_both)}

    # Pin the produced documents' own frontmatter date to _ACTIVITY_DATE: the
    # "both entries qualify (measured on or before the activity's own date)"
    # claim this scenario depends on is only true if the activity really is
    # recorded on _ACTIVITY_DATE itself, not some other date a timestamp
    # off-by-one could silently produce.
    for doc in (run_old, run_new, run_both):
        frontmatter = read_frontmatter(doc)
        assert frontmatter is not None
        assert frontmatter["date"] == _ACTIVITY_DATE.isoformat()

    assert _basis_of(run_old) == "power"
    assert _basis_of(run_new) == "power"
    assert _basis_of(run_both) == "power"

    value_old = _computed_result(run_old).value
    value_new = _computed_result(run_new).value
    value_both = _computed_result(run_both).value

    assert value_old != value_new, (
        "the two control FTP values must actually produce different loads, "
        "or the comparison below proves nothing"
    )
    assert value_both == value_new
    assert value_both != value_old


# ---------------------------------------------------------------------------
# Scenario 2a: a tightened sufficiency minimum flips a channel from computed
# to uncomputed (Req 8.9's "identical inputs -> identical diagnostics" is
# what makes the flip itself legible as a diagnostic, not a crash)
# ---------------------------------------------------------------------------


def test_tightened_sufficiency_minimum_flips_one_channel_to_uncomputed(
    tmp_path: Path,
) -> None:
    """The Run document's heart-rate stream is deliberately 85% covered (a 90
    s gap out of 600 s) while power and distance stay fully covered. Under
    the shipped default (``min_stream_coverage = 0.80``) all three channels
    compute; tightening it to ``0.90`` in ``[load.sufficiency]`` flips ONLY
    the heart-rate channel to an uncomputed diagnostic (Req 3.3 of the
    upstream ``load-channels`` sufficiency gate, reached here through
    ``LoadContext.settings``) while the selected channel (pace) and its
    value are untouched -- proving the configuration path from the settings
    file through the per-activity context to the channel."""
    baseline_root = _build_data_root(
        tmp_path / "baseline", {"run.fit": _run_fit_bytes(hr_gap=(255, 345))}
    )
    _write_profile(baseline_root, _populated_profile())

    tightened_root = _build_data_root(
        tmp_path / "tightened", {"run.fit": _run_fit_bytes(hr_gap=(255, 345))}
    )
    _write_profile(tightened_root, _populated_profile())
    _write_settings(tightened_root, "[load.sufficiency]\nmin_stream_coverage = 0.90\n")

    baseline_run = _doc(baseline_root, "run")
    tightened_run = _doc(tightened_root, "run")

    baseline_report = apply_load(baseline_root, session=NonInteractiveSession())
    tightened_report = apply_load(tightened_root, session=NonInteractiveSession())

    # Live: both passes actually computed the run (not both skipping it).
    assert _docs_of(baseline_report.computed) == {_rel(baseline_root, baseline_run)}
    assert _docs_of(tightened_report.computed) == {_rel(tightened_root, tightened_run)}

    baseline_hr = _non_selected_entry(baseline_run, "heart_rate")
    tightened_hr = _non_selected_entry(tightened_run, "heart_rate")

    # Baseline: heart rate computed a real number under the default 0.80.
    assert baseline_hr.value is not None
    # Tightened: the same stream, same activity, now reports no number and a
    # reason naming the coverage shortfall -- flipped computed -> uncomputed
    # by configuration alone.
    assert tightened_hr.value is None
    assert "coverage" in tightened_hr.reason and "0.9" in tightened_hr.reason

    # The selected channel (pace) is untouched by the tightened minimum.
    assert _basis_of(baseline_run) == "pace"
    assert _basis_of(tightened_run) == "pace"
    assert _computed_result(baseline_run).value == _computed_result(tightened_run).value


# ---------------------------------------------------------------------------
# Scenario 2b: a reconfigured priority changes the selection, never a value
# ---------------------------------------------------------------------------


def test_reconfigured_priority_changes_selection_not_any_computed_value(
    tmp_path: Path,
) -> None:
    """Two configurations over the SAME Run document: the shipped default
    order (pace, power, heart_rate) selects pace; a reconfigured order
    (power, pace, heart_rate) selects power instead. Both halves of the
    sharp claim are asserted: the SELECTED channel differs (pace vs power),
    and every channel's own computed number -- pace's and power's alike --
    is identical across the two configurations, proving the reconfiguration
    only changes which channel is read out, never what any channel computed."""
    default_root = _build_data_root(tmp_path / "default", {"run.fit": _run_fit_bytes()})
    _write_profile(default_root, _populated_profile())

    reconfigured_root = _build_data_root(
        tmp_path / "reconfigured", {"run.fit": _run_fit_bytes()}
    )
    _write_profile(reconfigured_root, _populated_profile())
    _write_settings(
        reconfigured_root, '[load.priority]\nrun = ["power", "pace", "heart_rate"]\n'
    )

    default_run = _doc(default_root, "run")
    reconfigured_run = _doc(reconfigured_root, "run")

    default_report = apply_load(default_root, session=NonInteractiveSession())
    reconfigured_report = apply_load(reconfigured_root, session=NonInteractiveSession())

    assert _docs_of(default_report.computed) == {_rel(default_root, default_run)}
    assert _docs_of(reconfigured_report.computed) == {
        _rel(reconfigured_root, reconfigured_run)
    }

    assert _basis_of(default_run) == "pace"
    assert _basis_of(reconfigured_run) == "power"

    default_result = _computed_result(default_run)
    reconfigured_result = _computed_result(reconfigured_run)

    # The selected value itself differs (a different channel was read out) --
    # asserted first so the "no value changed" claim below cannot be made
    # vacuously true by a pass that selected the same channel both times.
    assert default_result.value != reconfigured_result.value

    # pace's own number: selected in the default config, non-selected in the
    # reconfigured one -- identical either way.
    default_pace = default_result.value
    reconfigured_pace = _non_selected_value(reconfigured_run, "pace")
    assert reconfigured_pace is not None
    assert default_pace == reconfigured_pace

    # power's own number: non-selected in the default config, selected in
    # the reconfigured one -- identical either way.
    default_power = _non_selected_value(default_run, "power")
    reconfigured_power = reconfigured_result.value
    assert default_power is not None
    assert default_power == reconfigured_power

    # heart_rate appears in BOTH configured orders (default: pace, power,
    # heart_rate; reconfigured: power, pace, heart_rate) and loses to
    # whichever channel is selected in each -- its own computed number is
    # unaffected by the priority reconfiguration regardless.
    default_hr = _non_selected_value(default_run, "heart_rate")
    reconfigured_hr = _non_selected_value(reconfigured_run, "heart_rate")
    assert default_hr is not None and reconfigured_hr is not None
    assert default_hr == reconfigured_hr

    # And its RECORDED REASON is the in-order "prefers <winner>" form
    # (selection.py:115-119), not the "not in the configured order" form --
    # naming the channel that actually won in each configuration.
    default_hr_reason = _non_selected_entry(default_run, "heart_rate").reason
    reconfigured_hr_reason = _non_selected_entry(reconfigured_run, "heart_rate").reason
    assert "prefers Pace" in default_hr_reason
    assert "prefers Power" in reconfigured_hr_reason


# ---------------------------------------------------------------------------
# Scenario 3: the configuration gate -- a malformed [load.priority] entry
# aborts before any document is written (Req 7.8)
# ---------------------------------------------------------------------------


def test_malformed_priority_configuration_aborts_before_any_write(
    tmp_path: Path,
) -> None:
    """A settings file whose ``[load.priority]`` table names ``run`` as a bare
    string (not a list) is a configuration error the CLI maps to exit code 2
    -- and, because :func:`~fitdocs.load.settings.load_load_settings` is
    called once, before the per-document loop, in
    :func:`~fitdocs.load.engine.apply_load`, NO document, profile, or any
    other file under the data root is touched: every byte, snapshotted
    before the run, matches the snapshot taken after."""
    data_root = _build_data_root(tmp_path, _standard_fixtures())
    _write_profile(data_root, _populated_profile())
    _write_settings(data_root, '[load.priority]\nrun = "pace"\n')

    # The subject is non-trivial before the byte-identity compare means
    # anything: every workout doc carries real frontmatter and a load region
    # placeholder, and the profile carries the seven benchmarks just written.
    # (Filtered to the six workout docs by name -- ``sync`` also lays down a
    # non-workout ``AGENTS.md`` file in the same directory.)
    six_docs = {
        needle: _doc(data_root, needle)
        for needle in ("run", "ride", "walk", "hike", "strength", "row")
    }
    docs_before = {p: p.read_text(encoding="utf-8") for p in six_docs.values()}
    assert len(docs_before) == 6
    for text in docs_before.values():
        assert text.strip() and "---" in text  # real frontmatter, not empty
    profile_text_before = (data_root / "athlete.toml").read_text(encoding="utf-8")
    assert "run" in profile_text_before and "ftp_watts" in profile_text_before

    snapshot_before = _snapshot(data_root)

    # Aborts through apply_load itself, before any document processing --
    # the same LoadSettingsError (a SettingsError) the CLI's _config_error
    # maps to exit 2.
    with pytest.raises(SettingsError):
        apply_load(data_root, session=NonInteractiveSession())

    assert _snapshot(data_root) == snapshot_before

    # And through the actual CLI entry point, which is what a user runs: the
    # documented exit code, nothing printed as if the pass proceeded, and
    # -- again -- not one byte moved.
    result = runner.invoke(app, ["load", "--out", str(data_root)])
    assert result.exit_code == cli._EXIT_CONFIG_ERROR

    assert _snapshot(data_root) == snapshot_before


# ---------------------------------------------------------------------------
# Scenario 4: determinism -- the same data root scored twice is byte-
# identical, and the second pass performs no writes (Req 1.4, 8.9)
# ---------------------------------------------------------------------------


def test_repeated_pass_is_byte_identical_and_performs_no_writes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A first pass over the full six-document data root computes the four
    scorable documents and marks the other two unsupported (asserted first,
    so the byte-identity/no-writes claims below have a non-trivial,
    genuinely-processed subject rather than an untouched one). A second,
    identical pass then changes not one byte across the whole data root AND
    is directly observed to call the engine's atomic-write seam zero times
    -- proving "no writes", not merely inferring it from equal bytes (an
    unconditional same-content rewrite would pass a byte comparison but not
    a call count)."""
    data_root = _build_data_root(tmp_path, _standard_fixtures())
    _write_profile(data_root, _populated_profile())

    run = _doc(data_root, "run")
    ride = _doc(data_root, "ride")
    walk = _doc(data_root, "walk")
    hike = _doc(data_root, "hike")
    strength = _doc(data_root, "strength")
    row = _doc(data_root, "row")

    first = apply_load(data_root, session=NonInteractiveSession())

    assert _docs_of(first.computed) == {
        _rel(data_root, run),
        _rel(data_root, ride),
        _rel(data_root, walk),
        _rel(data_root, hike),
    }
    assert _docs_of(first.unsupported) == {
        _rel(data_root, strength),
        _rel(data_root, row),
    }
    for doc in (run, ride, walk, hike):
        assert classify_load_region(doc.read_text(encoding="utf-8")).state is (
            RegionState.COMPUTED
        )
    for doc in (strength, row):
        assert classify_load_region(doc.read_text(encoding="utf-8")).state is (
            RegionState.UNSUPPORTED
        )

    snapshot_after_first = _snapshot(data_root)

    write_calls: list[Path] = []
    monkeypatch.setattr(
        load_engine, "_atomic_write", lambda doc, new: write_calls.append(doc)
    )

    second = apply_load(data_root, session=NonInteractiveSession())

    assert _snapshot(data_root) == snapshot_after_first
    assert write_calls == []
    assert second.computed == () and second.unsupported == ()
    assert second.skipped == () and second.restored == () and second.failures == ()

    # A THIRD pass, forced through ``recompute=True``, is a genuine
    # independent re-computation (not the restore-only path the untouched
    # second pass took) -- Req 1.4/8.9's "identical inputs produce an
    # identical result" claim, including the non-selected values', inputs'
    # and notes' deterministic ordering, is only proven by two REAL
    # computations agreeing, which this is.
    monkeypatch.undo()
    third = apply_load(data_root, session=NonInteractiveSession(), recompute=True)
    assert _docs_of(third.computed) == {
        _rel(data_root, run),
        _rel(data_root, ride),
        _rel(data_root, walk),
        _rel(data_root, hike),
    }
    assert _snapshot(data_root) == snapshot_after_first
