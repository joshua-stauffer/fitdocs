"""End-to-end proof of date-scoped benchmark selection across a
measurement-system boundary (task 6.1, feature validation).

Drives :func:`fitdocs.load.engine.apply_load` over a real temporary data root
built through the actual sync pipeline, with an ``athlete.toml`` built through
the real write path (:meth:`~fitdocs.load.profile.AthleteProfile.with_benchmark`
+ :func:`~fitdocs.load.profile.save_profile`, never a hand-typed TOML string),
carrying a two-entry running FTP history that spans the athlete's own
hardware change (Apple Watch native power through 2024, Stryd from 2026 --
the spec's own narrative example, `.kiro/specs/athlete-benchmarks/design.md`
Physical Data Model). A stub calculator records, per activity date, what it
resolved and what staleness verdict the pass's configured window produced --
the only way a black-box, report-level test can observe what the engine
actually threaded through :class:`~fitdocs.load.types.LoadContext` (Req 3.1,
3.2, 3.3, 3.5, 3.8, 4.3, 8.4).

Deliberately its own module (task 6.1's boundary), disjoint from
``test_arbitration_e2e.py`` (task 6.1 of ``training-load``, a different
concern -- arbitration/prompt suppression, not date-scoped selection) and
from ``test_engine.py``'s per-clause wiring tests (which already pin the
context threading itself, task 5.2). This module composes the whole stack --
vocabulary, selection, staleness and engine wiring together over one
realistic multi-year fixture -- and its own report-level assertions stand on
their own mutation evidence. The file-level byte-identity assertion below
(``snapshot_after_pass2 == snapshot_after_pass1``) and the companion
per-document log-identity assertion are correct but unpinned here, because
``apply_frontmatter_load`` (``src/fitdocs/load/docedit.py:287``) already
strips managed lines before re-appending them, making the engine's own
recompute-time strip redundant; second-pass byte-identity is independently
pinned by
``tests/load/test_feature_e2e.py::test_second_identical_pass_writes_no_bytes``.
"""

from __future__ import annotations

from datetime import date, timedelta, timezone
from pathlib import Path

from fitdocs import Modality, Sport
from fitdocs.athlete import load_athlete_inputs
from fitdocs.benchmarks import BenchmarkKind, benchmark_age
from fitdocs.layout import WORKOUTS_DIR
from fitdocs.load import registry
from fitdocs.load.engine import DocLoadEntry, apply_load
from fitdocs.load.profile import AthleteProfile, save_profile
from fitdocs.load.types import (
    AthleteField,
    BenchmarkRef,
    Computed,
    LoadContext,
    LoadOutcome,
    LoadResult,
    NotComputed,
)
from fitdocs.sync import sync
from tests.fixtures import builder

_TZ = timezone(timedelta(hours=-6))

# --- fixed benchmark history: spans the athlete's own hardware change ------
_OLD_FTP_VALUE = 262.0
_OLD_FTP_MEASURED_ON = date(2024, 5, 2)
_OLD_FTP_NOTE = "Apple Watch native power"
_NEW_FTP_VALUE = 285.0
_NEW_FTP_MEASURED_ON = date(2026, 3, 14)
_NEW_FTP_NOTE = "Stryd 9-minute test"

# --- fixed activity dates: predating, between and after the two entries ----
_PREDATING_DATE = date(2023, 6, 1)
_MID_DATE = date(2024, 8, 1)
_LATE_DATE = date(2026, 6, 1)

# offsets (seconds from ``builder.FIT_TIMESTAMP_BASE``) computed so a record
# stamped at noon local (``_TZ``) time on the target date lands on that same
# local calendar date once synced with ``tz=_TZ`` -- ``FIT_TIMESTAMP_BASE``
# itself resolves to 2021-09-07 in ``_TZ``, so every offset below is relative
# to that.
_PREDATING_OFFSET = 54_576_800
_MID_OFFSET = 91_469_600
_LATE_OFFSET = 149_271_200

_STALENESS_WINDOW_DAYS = 85
"""Deliberately not the shipped default (84, ``DEFAULT_STALENESS_WINDOW_DAYS``)
-- picked so the two resolved documents land on opposite sides of it: the mid
document's benchmark is 91 days old (91 > 85 -> stale) and the late
document's is 79 days old (79 <= 85 -> current), so a single fixed window
produces both verdicts in one pass."""

_RUN_RECORD_COUNT = 5
_RUN_SPEED_MPS = 3.0


class _ServingTiles:
    """Inert basemap-tile source: this test never inspects rendered maps."""

    attribution = "© OpenStreetMap contributors"

    def resolve(self, refs: object) -> dict[object, bytes]:
        return {ref: b"\x89PNG\r\n\x1a\n" for ref in refs}  # type: ignore[union-attr]


_TILES: _ServingTiles = _ServingTiles()


def _dated_run_fit_bytes(serial: int, timestamp_offset: int) -> bytes:
    """Encoded running ``.fit`` bytes whose session/records start at
    ``builder.FIT_TIMESTAMP_BASE + timestamp_offset`` -- the only lever this
    module has to place a document's own recorded date deliberately, since
    ``builder.run_fit_bytes()`` fixes its date. Mirrors the shared-message
    construction ``builder.run_mesgs()`` uses (same message shapes and global
    message numbers), just with a caller-supplied offset."""
    base = builder.FIT_TIMESTAMP_BASE + timestamp_offset
    mesgs: list[builder.Mesg] = [
        builder._file_id(serial),
        builder._device_info(serial, "SyntheticDatedRunWatch"),
        {"mesg_num": builder._MESG_SPORT, "sport": "running", "sub_sport": "generic"},
    ]
    for i in range(_RUN_RECORD_COUNT):
        mesgs.append(
            {
                "mesg_num": builder._MESG_RECORD,
                "timestamp": base + i,
                "heart_rate": 130 + i,
                "distance": _RUN_SPEED_MPS * i,
            }
        )
    mesgs.append(
        {
            "mesg_num": builder._MESG_SESSION,
            "start_time": base,
            "timestamp": base + (_RUN_RECORD_COUNT - 1),
            "sport": "running",
            "sub_sport": "generic",
            "total_elapsed_time": float(_RUN_RECORD_COUNT - 1),
            "total_timer_time": float(_RUN_RECORD_COUNT - 1),
            "total_distance": _RUN_SPEED_MPS * (_RUN_RECORD_COUNT - 1),
            "avg_heart_rate": 132,
            "max_heart_rate": 130 + (_RUN_RECORD_COUNT - 1),
        }
    )
    mesgs.append(builder._activity(_RUN_RECORD_COUNT - 1, float(_RUN_RECORD_COUNT - 1)))
    return builder.encode(mesgs)


def _build_data_root(tmp_path: Path, fixtures: dict[str, bytes]) -> Path:
    """Render ``fixtures`` into a temp data root via the real sync pipeline."""
    src = tmp_path / "src"
    data_root = tmp_path / "data"
    data_root.mkdir()
    for name, data in fixtures.items():
        path = src / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    sync(src, data_root, athlete=load_athlete_inputs(data_root), tz=_TZ, tiles=_TILES)
    return data_root


def _doc_on(data_root: Path, day: date) -> Path:
    """Locate the one workout document recorded on ``day`` (dates are unique
    across this module's fixture, so a filename-prefix match is unambiguous)."""
    needle = day.isoformat()
    matches = [
        p for p in (data_root / WORKOUTS_DIR).glob("*.md") if p.name.startswith(needle)
    ]
    assert len(matches) == 1, (
        f"expected exactly one document dated {needle}, found {matches}"
    )
    return matches[0]


def _rel(data_root: Path, doc: Path) -> str:
    return doc.relative_to(data_root).as_posix()


def _docs_of(entries: tuple[DocLoadEntry, ...]) -> set[str]:
    return {entry.doc for entry in entries}


def _reason_for(entries: tuple[DocLoadEntry, ...], rel: str) -> str:
    matches = [entry.detail for entry in entries if entry.doc == rel]
    assert len(matches) == 1, (
        f"expected exactly one skipped entry for {rel}, found {matches}"
    )
    return matches[0]


def _snapshot(data_root: Path) -> dict[str, bytes]:
    return {
        p.relative_to(data_root).as_posix(): p.read_bytes()
        for p in sorted(data_root.rglob("*"))
        if p.is_file()
    }


def _build_profile_with_run_ftp_history(data_root: Path) -> None:
    """Write ``athlete.toml`` through the real store write path: two dated
    running FTP entries spanning the hardware change, and nothing recorded
    for cycling FTP at all -- the profile a "no benchmark on file" query
    needs to be genuinely reachable (never an artifact of a hand-typed TOML
    string skipping validation)."""
    profile = AthleteProfile(data={})
    profile = profile.with_benchmark(
        BenchmarkKind.FTP_WATTS,
        discipline=Sport.RUN,
        value=_OLD_FTP_VALUE,
        measured_on=_OLD_FTP_MEASURED_ON,
        note=_OLD_FTP_NOTE,
    )
    profile = profile.with_benchmark(
        BenchmarkKind.FTP_WATTS,
        discipline=Sport.RUN,
        value=_NEW_FTP_VALUE,
        measured_on=_NEW_FTP_MEASURED_ON,
        note=_NEW_FTP_NOTE,
    )
    save_profile(data_root, profile)


# --- the raising session: proves the presence check, not merely its outcome ---


class _RaisingSession:
    """An :class:`InteractionSession` that raises on any prompt call.

    Used instead of ``NonInteractiveSession`` deliberately: a non-interactive
    session absorbs a wrongly-triggered prompt silently (the field just stays
    unanswered), which would make "no prompt occurred" true regardless of
    whether the presence check under test is correct. A prompt attempt here
    still raises ``AssertionError``, but that raise is caught by
    ``apply_load``'s per-document exception guard
    (``src/fitdocs/load/engine.py:297-298``) and surfaces as an entry in
    ``report.failures`` rather than propagating out of the test call --
    which is exactly what the ``report1.failures == ()`` /
    ``report1.computed`` / ``report1.skipped`` assertions above check for,
    so those assertions are only true because the presence check genuinely
    suppressed the prompt -- not because prompting was impossible for some
    unrelated reason.
    """

    def __init__(self) -> None:
        self.informs: list[str] = []

    def confirm(self, question: str, *, default: bool = True) -> bool | None:
        raise AssertionError(f"unexpected confirm prompt: {question!r}")

    def ask_int(
        self,
        question: str,
        *,
        minimum: int | None = None,
        maximum: int | None = None,
        default: int | None = None,
    ) -> int | None:
        raise AssertionError(f"unexpected ask_int prompt: {question!r}")

    def ask_float(
        self,
        question: str,
        *,
        minimum: float | None = None,
        maximum: float | None = None,
        default: float | None = None,
    ) -> float | None:
        raise AssertionError(f"unexpected ask_float prompt: {question!r}")

    def choose(
        self,
        question: str,
        options: object,
        *,
        default_index: int | None = None,
    ) -> int | None:
        raise AssertionError(f"unexpected choose prompt: {question!r}")

    def inform(self, message: str) -> None:
        self.informs.append(message)


# --- the stub calculator: resolves a per-discipline running/cycling FTP ----

_FTP_RUN_FIELD = AthleteField(
    key="benchmarks.run.ftp_watts",
    label="Running FTP",
    kind="float",
    minimum=50,
    maximum=600,
    help_text="functional threshold power in watts, running-specific",
    benchmark=BenchmarkRef(kind=BenchmarkKind.FTP_WATTS, discipline=Sport.RUN),
)


class _ThresholdResolvingCalculator:
    """Supports RUN and RIDE; resolves the activity's own discipline's FTP
    benchmark against the activity's own date and records what it found,
    keyed by that date, so the test can inspect resolution results directly
    rather than only through rendered markdown."""

    calculator_id = "stub-e2e-threshold-resolving"
    display_name = "Stub E2E Threshold Resolving Calculator"
    supported_modalities = frozenset({Modality.RUN, Modality.BIKE})

    def __init__(self) -> None:
        self.log: dict[date, dict[str, object]] = {}

    def required_athlete_fields(self) -> tuple[AthleteField, ...]:
        return (_FTP_RUN_FIELD,)

    def compute(
        self,
        activity: object,
        metrics: object,
        profile: object,
        session: object,
        context: LoadContext,
    ) -> LoadOutcome:
        assert context.activity_date is not None, (
            "every document in this fixture is dated"
        )
        discipline = activity.sport  # type: ignore[attr-defined]
        has = profile.has_benchmark(BenchmarkKind.FTP_WATTS, discipline=discipline)  # type: ignore[attr-defined]
        resolved = profile.benchmark(  # type: ignore[attr-defined]
            BenchmarkKind.FTP_WATTS, discipline=discipline, on=context.activity_date
        )
        if resolved is None:
            reason = (
                f"ftp_watts on file for {discipline.value} but none applicable "
                f"as of {context.activity_date.isoformat()}"
                if has
                else f"ftp_watts never provided for {discipline.value}"
            )
            self.log[context.activity_date] = {
                "has": has,
                "resolved": None,
                "age": None,
                "reason": reason,
            }
            return NotComputed(reason=reason)

        age = benchmark_age(
            activity_date=context.activity_date,
            measured_on=resolved.measured_on,
            window_days=context.settings.benchmark_staleness_days,
        )
        self.log[context.activity_date] = {
            "has": has,
            "resolved": (resolved.value, resolved.measured_on, resolved.note),
            "age": (age.age_days, age.window_days, age.is_stale),
            "reason": None,
        }
        return Computed(
            result=LoadResult(
                calculator_id=self.calculator_id,
                display_name=self.display_name,
                value=resolved.value,
                basis=(
                    f"ftp={resolved.value} "
                    f"measured_on={resolved.measured_on.isoformat()} "
                    f"note={resolved.note} stale={age.is_stale} age={age.age_days} "
                    f"window={age.window_days}"
                ),
                non_selected=(),
                flags=(),
                inputs_used=(),
                notes=(),
            )
        )


# --- the test itself ---------------------------------------------------------


def test_date_scoped_selection_end_to_end_across_a_hardware_change(
    tmp_path: Path,
) -> None:
    """Two RUN documents each resolve the running FTP entry current at their
    own date (mid -> the pre-Stryd 262W entry, late -> the post-Stryd 285W
    entry -- Req 3.1, 3.2), a third RUN document predating both entries
    resolves nothing while presence stays true and no prompt occurs (Req 3.3,
    3.5, 8.3), and a RIDE document with zero cycling entries on file resolves
    nothing for a reason distinguishable from the predating RUN document's
    (Req 3.5, 8.4). A second, forced ``recompute=True`` pass over the same
    data root reproduces every resolution and every staleness verdict exactly
    (Req 3.8, 4.3) and leaves every file byte-identical.
    """
    data_root = _build_data_root(
        tmp_path,
        {
            "predating.fit": _dated_run_fit_bytes(7001, _PREDATING_OFFSET),
            "mid.fit": _dated_run_fit_bytes(7002, _MID_OFFSET),
            "late.fit": _dated_run_fit_bytes(7003, _LATE_OFFSET),
            "ride-never.fit": builder.ride_fit_bytes(),
        },
    )
    _build_profile_with_run_ftp_history(data_root)

    predating = _doc_on(data_root, _PREDATING_DATE)
    mid = _doc_on(data_root, _MID_DATE)
    late = _doc_on(data_root, _LATE_DATE)
    ride = next(p for p in (data_root / WORKOUTS_DIR).glob("*.md") if "ride" in p.name)
    ride_date = date.fromisoformat(ride.name[:10])
    for other in (_PREDATING_DATE, _MID_DATE, _LATE_DATE):
        assert ride_date != other, "the ride document must have its own distinct date"

    settings_text = (
        "[load]\n"
        f'default_calculator = "stub-e2e-threshold-resolving"\n'
        f"benchmark_staleness_days = {_STALENESS_WINDOW_DAYS}\n"
    )
    (data_root / "fitdocs.toml").write_text(settings_text, encoding="utf-8")

    calc1 = _ThresholdResolvingCalculator()
    registry.register(calc1)
    try:
        report1 = apply_load(data_root, session=_RaisingSession())
    finally:
        registry.unregister(calc1.calculator_id)

    predating_rel = _rel(data_root, predating)
    mid_rel = _rel(data_root, mid)
    late_rel = _rel(data_root, late)
    ride_rel = _rel(data_root, ride)

    # --- report-level classification ---------------------------------------
    assert _docs_of(report1.computed) == {mid_rel, late_rel}
    assert _docs_of(report1.skipped) == {predating_rel, ride_rel}
    assert report1.failures == ()
    assert report1.unsupported == ()

    # --- the two skip reasons are distinct and each is independently
    # reachable: the predating RUN document really has an entry on file
    # (`has_benchmark` true), the ride document really has none -----------
    predating_log = calc1.log[_PREDATING_DATE]
    ride_log = calc1.log[ride_date]
    assert predating_log["has"] is True
    assert predating_log["resolved"] is None
    assert ride_log["has"] is False
    assert ride_log["resolved"] is None

    predating_reason = _reason_for(report1.skipped, predating_rel)
    ride_reason = _reason_for(report1.skipped, ride_rel)
    assert predating_reason != ride_reason
    assert "on file" in predating_reason and "none applicable" in predating_reason
    assert "never provided" in ride_reason

    # --- per-document resolved values, measurement dates and staleness -----
    mid_log = calc1.log[_MID_DATE]
    late_log = calc1.log[_LATE_DATE]
    assert mid_log["resolved"] == (_OLD_FTP_VALUE, _OLD_FTP_MEASURED_ON, _OLD_FTP_NOTE)
    assert late_log["resolved"] == (_NEW_FTP_VALUE, _NEW_FTP_MEASURED_ON, _NEW_FTP_NOTE)
    mid_age_days, mid_window, mid_stale = mid_log["age"]  # type: ignore[misc]
    late_age_days, late_window, late_stale = late_log["age"]  # type: ignore[misc]
    assert (mid_age_days, mid_window, mid_stale) == (91, _STALENESS_WINDOW_DAYS, True)
    assert (late_age_days, late_window, late_stale) == (
        79,
        _STALENESS_WINDOW_DAYS,
        False,
    )

    # --- no prompt occurred anywhere in this pass: a prompt attempt would
    # land in report1.failures via the engine's per-document exception
    # guard, which the report-level assertions above (report1.computed,
    # report1.skipped and report1.failures == ()) already reject ------------

    snapshot_after_pass1 = _snapshot(data_root)

    # --- a second, forced pass: recompute=True makes every document's
    # `compute` genuinely re-run (not merely restored from a preserved
    # payload), so identical output below is real determinism, not an
    # idempotence no-op ------------------------------------------------------
    calc2 = _ThresholdResolvingCalculator()
    registry.register(calc2)
    try:
        report2 = apply_load(data_root, session=_RaisingSession(), recompute=True)
    finally:
        registry.unregister(calc2.calculator_id)

    assert _docs_of(report2.computed) == {mid_rel, late_rel}
    assert _docs_of(report2.skipped) == {predating_rel, ride_rel}
    assert calc2.log == calc1.log

    snapshot_after_pass2 = _snapshot(data_root)
    assert snapshot_after_pass2 == snapshot_after_pass1
