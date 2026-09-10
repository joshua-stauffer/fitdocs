"""Feature-level end-to-end proof that a prompt answer can score an activity
older than the date the answer was given (task 7.4, Amendment 4).

Drives the **real** sync pipeline (:func:`fitdocs.sync.sync`), an *absent*
``athlete.toml``, the real ``athlete.toml`` write path
(:meth:`~fitdocs.load.profile.AthleteProfile.with_benchmark` +
:func:`~fitdocs.load.profile.save_profile`, reached here only indirectly --
every entry in this module is written by the prompt flow itself, never by
this file calling ``with_benchmark`` directly), and the registered built-in
:class:`~fitdocs.load.threshold.calculator.ThresholdCalculator` through
:func:`~fitdocs.load.engine.apply_load` -- no stub calculator, no stub
profile, no hand-built ``Activity``, no hand-typed TOML.

Every scenario below scripts a single :class:`InteractionSession` double
(``ScriptedSession``, copied from ``tests/load/test_engine.py``'s double of
the same name and shape) and runs the pass with an explicit ``today`` well
after the fixture's own activity date(s) -- the pass's one clock read,
injected so this module reads no real clock either. The threshold
calculator's seven declared fields (``required_athlete_fields()``, module
docstring order) are all benchmark fields, so every accepted answer in this
module is a candidate for the retroactive-application question (Req
3.7-3.9): none is a flat field, so ``collect_missing_fields`` never takes the
no-question branch for a reason unrelated to the date comparison this module
exists to prove.

Every ``apply_load`` call's report asserts ``failures == ()`` first --
tasks.md's own recorded lesson from task 7.3: the engine's per-document
``except Exception`` swallows a double's own ``AssertionError`` into
``report.failures``, so an assertion inside ``ScriptedSession`` or
``_RaisingSession`` that never fires would otherwise report a *skipped* or
*computed* document instead of the double's actual complaint.
"""

from __future__ import annotations

import tomllib
from collections.abc import Sequence
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

from fitdocs import Sport
from fitdocs.athlete import load_athlete_inputs
from fitdocs.benchmarks import Benchmark, BenchmarkKind
from fitdocs.layout import WORKOUTS_DIR
from fitdocs.load.engine import DocLoadEntry, LoadReport, apply_load
from fitdocs.load.profile import AthleteProfile, load_profile
from fitdocs.load.prompts import _retroactive_question
from fitdocs.load.types import InteractionSession
from fitdocs.model import FIT_EPOCH
from fitdocs.sync import sync
from tests.fixtures import builder

# PINNED timezone (never the system zone) so document stems are byte-stable,
# matching the convention ``tests/load/threshold/test_feature_e2e.py`` and
# ``tests/load/test_benchmark_selection_e2e.py`` already use.
_TZ = timezone(timedelta(hours=-6))

# Long enough (601 s) to clear the shared 60 s default minimum duration with
# margin, so every channel is sufficient and the run genuinely computes.
_RECORD_COUNT = 601
_SPEED_MPS = 3.0

_TODAY = date(2027, 1, 4)
"""The injected pass date. Deliberately NOT the real calendar date on the day
this module was written (2026-09-10): while the two coincided, an engine that
ignored ``today=`` and read the clock produced identical results here, so the
injection was pinned only by ``tests/load/test_engine.py``."""
"""The pass date every scenario injects as ``apply_load``'s ``today`` -- the
date every accepted answer is recorded as measured on."""

_ACTIVITY_DATE = date(2026, 6, 1)
"""The single document's own recorded local calendar date in scenarios 1 and
2 -- strictly earlier than ``_TODAY``, the condition Req 3.7 requires for the
retroactive question to fire at all."""

_EARLIER_DATE = date(2026, 5, 1)
"""The earlier of the two documents in scenario 3 -- also strictly earlier
than ``_ACTIVITY_DATE``, so the two documents are unambiguously ordered and
the engine's sorted-stem scan visits ``_EARLIER_DATE`` first."""


class _ServingTiles:
    """The always-supplied basemap-tile source these setup runs inject."""

    attribution = "© OpenStreetMap contributors"

    def resolve(self, refs: Sequence[object]) -> dict[object, bytes]:
        return {ref: b"\x89PNG\r\n\x1a\n" for ref in refs}


_TILES: _ServingTiles = _ServingTiles()


# --- fixture builders (self-contained; this file borrows no helper from a
# sibling test module, per the task's boundary) --------------------------


def _timestamp_offset_for(day: date) -> int:
    """A FIT-epoch offset (seconds from ``builder.FIT_TIMESTAMP_BASE``) that
    places a noon-local (``_TZ``) record on ``day``'s own calendar date once
    synced with ``tz=_TZ``. Computed from real datetime arithmetic (via
    :data:`~fitdocs.model.FIT_EPOCH`, the same conversion ``fit_datetime``
    applies) rather than a hand-derived day-count."""
    base_instant = FIT_EPOCH + timedelta(seconds=builder.FIT_TIMESTAMP_BASE)
    target_instant = datetime.combine(day, time(12, 0), tzinfo=_TZ)
    offset = (target_instant - base_instant).total_seconds()
    assert offset.is_integer()
    return int(offset)


def _run_fit_bytes(serial: int, day: date) -> bytes:
    """A long, fully-covered running fixture dated ``day`` -- continuous
    distance, heart rate and power, so every one of the threshold
    calculator's three channels is sufficient and the document computes."""
    base = builder.FIT_TIMESTAMP_BASE + _timestamp_offset_for(day)
    mesgs: list[builder.Mesg] = [
        builder._file_id(serial),
        builder._device_info(serial, "SyntheticPromptDateWatch"),
        {"mesg_num": builder._MESG_SPORT, "sport": "running", "sub_sport": "generic"},
    ]
    for i in range(_RECORD_COUNT):
        mesgs.append(
            {
                "mesg_num": builder._MESG_RECORD,
                "timestamp": base + i,
                "distance": _SPEED_MPS * i,
                "heart_rate": 140 + (i % 5),
                "power": 250,
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
            "avg_power": 250,
            "max_power": 250,
        }
    )
    mesgs.append(builder._activity(_RECORD_COUNT - 1, float(_RECORD_COUNT - 1)))
    return builder.encode(mesgs)


def _build_data_root(tmp_path: Path, fixtures: dict[str, bytes]) -> Path:
    """Render ``fixtures`` into a temp data root via the real sync pipeline,
    with no ``athlete.toml`` written -- every scenario starts from an
    *absent* profile, per the task's boundary."""
    src = tmp_path / "src"
    data_root = tmp_path / "data"
    data_root.mkdir(parents=True)
    for name, data in fixtures.items():
        path = src / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    sync(src, data_root, athlete=load_athlete_inputs(data_root), tz=_TZ, tiles=_TILES)
    return data_root


def _doc_on(data_root: Path, day: date) -> Path:
    """Locate the one workout document recorded on ``day`` (dates are unique
    across this module's fixtures, so a filename-prefix match is
    unambiguous)."""
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


def _snapshot(data_root: Path) -> dict[str, bytes]:
    return {
        p.relative_to(data_root).as_posix(): p.read_bytes()
        for p in sorted(data_root.rglob("*"))
        if p.is_file()
    }


def _entry_for(
    profile: AthleteProfile, kind: BenchmarkKind, *, discipline: Sport | None
) -> Benchmark:
    matches = [
        entry
        for entry in profile.benchmarks.entries
        if entry.kind is kind and entry.discipline == discipline
    ]
    assert len(matches) == 1, (
        f"expected exactly one {kind!r}/{discipline!r} entry, found {matches}"
    )
    return matches[0]


# --- the scripted session double (copied, minimally adapted, from
# tests/load/test_engine.py's ScriptedSession of the same name and shape) --


class ScriptedSession:
    """An :class:`InteractionSession` double answering from per-kind FIFO
    queues. Each primitive pops the next answer from its own queue; an empty
    queue raises so an over-asking, mis-wired flow fails loudly rather than
    silently reading ``None``."""

    def __init__(
        self,
        *,
        confirms: Sequence[bool | None] = (),
        ints: Sequence[int | None] = (),
        floats: Sequence[float | None] = (),
    ) -> None:
        self._confirms = list(confirms)
        self._ints = list(ints)
        self._floats = list(floats)
        self.informs: list[str] = []
        self.confirm_defaults: list[tuple[str, bool]] = []
        """Every ``confirm`` call's ``(question, default)`` pair, in order --
        lets a test pin the exact question text and the ``default`` a
        specific question was asked with (Req 3.9)."""

    @staticmethod
    def _pop(queue: list[object], kind: str) -> object:
        if not queue:
            raise AssertionError(f"ScriptedSession: no more {kind} answers queued")
        return queue.pop(0)

    def confirm(self, question: str, *, default: bool = True) -> bool | None:
        self.confirm_defaults.append((question, default))
        answer = self._pop(self._confirms, "confirm")
        assert answer is None or isinstance(answer, bool)
        return answer

    def ask_int(
        self,
        question: str,
        *,
        minimum: int | None = None,
        maximum: int | None = None,
        default: int | None = None,
    ) -> int | None:
        answer = self._pop(self._ints, "ask_int")
        assert answer is None or isinstance(answer, int)
        return answer

    def ask_float(
        self,
        question: str,
        *,
        minimum: float | None = None,
        maximum: float | None = None,
        default: float | None = None,
    ) -> float | None:
        answer = self._pop(self._floats, "ask_float")
        assert answer is None or isinstance(answer, (int, float))
        return None if answer is None else float(answer)

    def choose(
        self,
        question: str,
        options: Sequence[str],
        *,
        default_index: int | None = None,
    ) -> int | None:
        raise AssertionError("ScriptedSession: this module never asks a choice")

    def inform(self, message: str) -> None:
        self.informs.append(message)


_: InteractionSession = ScriptedSession()


class _RaisingSession:
    """An :class:`InteractionSession` that fails loudly on any prompt at all
    -- proves a pass genuinely asks nothing, rather than merely inferring it
    from an empty queue that a mis-wired flow could also exhaust silently."""

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
        options: Sequence[str],
        *,
        default_index: int | None = None,
    ) -> int | None:
        raise AssertionError(f"unexpected choose prompt: {question!r}")

    def inform(self, message: str) -> None:
        return None


_: InteractionSession = _RaisingSession()


# The seven declared fields' answers, in ``ATHLETE_FIELDS`` declaration order
# (run FTP, ride FTP, run LTHR, ride LTHR, run pace, max HR, resting HR):
# pairwise-distinct so a mis-routed value (e.g. the pace answer landing under
# ride LTHR) is visible rather than accidentally matching a neighbor.
_INTS: tuple[int, ...] = (251, 213, 161, 157, 183, 47)
_FLOATS: tuple[float, ...] = (245.0,)


def _all_yes_session() -> ScriptedSession:
    return ScriptedSession(ints=list(_INTS), floats=list(_FLOATS), confirms=[True] * 7)


def _all_no_session() -> ScriptedSession:
    return ScriptedSession(ints=list(_INTS), floats=list(_FLOATS), confirms=[False] * 7)


# ---------------------------------------------------------------------------
# Scenario 1: yes to every retroactive question -- the document computes,
# and every entry is dated and applied retroactively (Req 3.7, 3.9, 9.1;
# athlete-benchmarks 3.10, 6.2, 6.10)
# ---------------------------------------------------------------------------


def test_yes_to_everything_scores_the_activity_and_dates_the_entries(
    tmp_path: Path,
) -> None:
    data_root = _build_data_root(
        tmp_path, {"run.fit": _run_fit_bytes(7501, _ACTIVITY_DATE)}
    )
    run = _doc_on(data_root, _ACTIVITY_DATE)
    session = _all_yes_session()

    report = apply_load(data_root, session=session, today=_TODAY)

    assert isinstance(report, LoadReport)
    assert report.failures == ()
    assert _docs_of(report.computed) == {_rel(data_root, run)}
    assert _rel(data_root, run) not in _docs_of(report.skipped)

    # Exactly seven retroactive questions -- one per declared benchmark
    # field, no more (a flat field would add an eighth ask with no
    # matching confirm; there is none to declare) and no fewer (a field
    # silently skipping the question would leave it under seven).
    assert len(session.confirm_defaults) == 7
    for question, default in session.confirm_defaults:
        assert default is True
        assert _TODAY.isoformat() in question
        assert _ACTIVITY_DATE.isoformat() in question
    # The exact shipped text, for at least one question.
    assert session.confirm_defaults[0][0] == _retroactive_question(
        _TODAY, _ACTIVITY_DATE
    )

    toml_path = data_root / "athlete.toml"
    assert toml_path.is_file()

    profile = load_profile(data_root)
    assert len(profile.benchmarks.entries) == 7
    checks = (
        (BenchmarkKind.FTP_WATTS, Sport.RUN, 251),
        (BenchmarkKind.FTP_WATTS, Sport.RIDE, 213),
        (BenchmarkKind.LTHR_BPM, Sport.RUN, 161),
        (BenchmarkKind.LTHR_BPM, Sport.RIDE, 157),
        (BenchmarkKind.THRESHOLD_PACE_S_PER_KM, Sport.RUN, 245.0),
        (BenchmarkKind.MAX_HR_BPM, None, 183),
        (BenchmarkKind.RESTING_HR_BPM, None, 47),
    )
    values_seen: set[float] = set()
    for kind, discipline, value in checks:
        entry = _entry_for(profile, kind, discipline=discipline)
        assert entry.value == value
        assert entry.measured_on == _TODAY
        assert entry.applies_from == _ACTIVITY_DATE
        values_seen.add(entry.value)
    # Guards the fixture's own literals, not production routing: a mis-routed
    # answer *permutes* the values (the per-entry ``entry.value == value``
    # assertion above is what catches it), whereas a duplicated literal in
    # ``checks`` would silently weaken that assertion -- this keeps the seven
    # answers pairwise-distinct.
    assert len(values_seen) == 7

    # Plain TOML keys -- ``tomllib`` decodes them as bare ``datetime.date``
    # values, and a hand edit sees exactly that, no fitdocs-specific type.
    raw = tomllib.loads(toml_path.read_text(encoding="utf-8"))
    raw_entries = raw["benchmarks"]["run"]["ftp_watts"]
    assert len(raw_entries) == 1
    assert isinstance(raw_entries[0]["measured_on"], date)
    assert isinstance(raw_entries[0]["applies_from"], date)
    assert raw_entries[0]["measured_on"] == _TODAY
    assert raw_entries[0]["applies_from"] == _ACTIVITY_DATE

    # Reachability of the retro path through the real store: the activity's
    # own date resolves (tier 2, athlete-benchmarks 3.10); the day before it
    # does not, even though the same entry is on file (has_benchmark True).
    resolved = profile.benchmark(
        BenchmarkKind.FTP_WATTS, discipline=Sport.RUN, on=_ACTIVITY_DATE
    )
    assert resolved is not None
    assert resolved.value == 251
    assert (
        profile.benchmark(
            BenchmarkKind.FTP_WATTS,
            discipline=Sport.RUN,
            on=_ACTIVITY_DATE - timedelta(days=1),
        )
        is None
    )
    assert profile.has_benchmark(BenchmarkKind.FTP_WATTS, discipline=Sport.RUN) is True


# ---------------------------------------------------------------------------
# Scenario 2 (control): no to every retroactive question -- the document is
# not computed, and no entry carries an applies-from date
# ---------------------------------------------------------------------------


def test_no_to_everything_leaves_the_activity_uncomputed_and_undated(
    tmp_path: Path,
) -> None:
    data_root = _build_data_root(
        tmp_path, {"run.fit": _run_fit_bytes(7502, _ACTIVITY_DATE)}
    )
    run = _doc_on(data_root, _ACTIVITY_DATE)
    session = _all_no_session()

    report = apply_load(data_root, session=session, today=_TODAY)

    assert isinstance(report, LoadReport)
    assert report.failures == ()
    assert _rel(data_root, run) in _docs_of(report.skipped)
    assert _rel(data_root, run) not in _docs_of(report.computed)
    # Bucket only -- the calculator's not-computed reason text is
    # `2026-08-27-not-applicable-has-no-readers`'s territory, not this one's.

    assert len(session.confirm_defaults) == 7
    for _, default in session.confirm_defaults:
        assert default is True

    profile = load_profile(data_root)
    assert len(profile.benchmarks.entries) == 7
    checks = (
        (BenchmarkKind.FTP_WATTS, Sport.RUN),
        (BenchmarkKind.FTP_WATTS, Sport.RIDE),
        (BenchmarkKind.LTHR_BPM, Sport.RUN),
        (BenchmarkKind.LTHR_BPM, Sport.RIDE),
        (BenchmarkKind.THRESHOLD_PACE_S_PER_KM, Sport.RUN),
        (BenchmarkKind.MAX_HR_BPM, None),
        (BenchmarkKind.RESTING_HR_BPM, None),
    )
    for kind, discipline in checks:
        entry = _entry_for(profile, kind, discipline=discipline)
        assert entry.measured_on == _TODAY
        assert entry.applies_from is None

    assert (
        profile.benchmark(
            BenchmarkKind.FTP_WATTS, discipline=Sport.RUN, on=_ACTIVITY_DATE
        )
        is None
    )
    assert profile.has_benchmark(BenchmarkKind.FTP_WATTS, discipline=Sport.RUN) is True


# ---------------------------------------------------------------------------
# Scenario 3: two documents of the same sport on different dates, both
# before today -- the question fires while the earlier one is processed, a
# single yes per field covers both, and a second identical pass asks and
# writes nothing (asked once, Req 3.3)
# ---------------------------------------------------------------------------


def test_two_documents_ask_once_while_processing_the_earlier_one(
    tmp_path: Path,
) -> None:
    data_root = _build_data_root(
        tmp_path,
        {
            "run-early.fit": _run_fit_bytes(7503, _EARLIER_DATE),
            "run-late.fit": _run_fit_bytes(7504, _ACTIVITY_DATE),
        },
    )
    early = _doc_on(data_root, _EARLIER_DATE)
    late = _doc_on(data_root, _ACTIVITY_DATE)
    session = _all_yes_session()

    first = apply_load(data_root, session=session, today=_TODAY)

    assert first.failures == ()
    assert _docs_of(first.computed) == {
        _rel(data_root, early),
        _rel(data_root, late),
    }

    # Asked once, not twice: exactly seven confirms for the whole pass, all
    # naming the EARLIER document's date -- the engine visits sorted stems,
    # so the earlier document is the one that actually triggers each
    # question; by the time the later one is processed every field is
    # already present and the presence check (undated) skips the prompt.
    assert len(session.confirm_defaults) == 7
    for question, default in session.confirm_defaults:
        assert default is True
        assert _TODAY.isoformat() in question
        assert _EARLIER_DATE.isoformat() in question
        assert _ACTIVITY_DATE.isoformat() not in question

    snapshot_after_first = _snapshot(data_root)
    # Non-triviality anchor for the byte comparison below: the snapshot must
    # cover the written profile and both documents, or equality proves nothing.
    assert "athlete.toml" in snapshot_after_first
    assert len(snapshot_after_first) >= 3

    # A second, identical pass with a session that raises on ANY prompt:
    # nothing is asked, nothing is computed anew, and not one byte moves.
    raising_session = _RaisingSession()
    second = apply_load(data_root, session=raising_session, today=_TODAY)

    assert second.failures == ()
    assert second.computed == ()
    assert second.restored == ()
    assert _snapshot(data_root) == snapshot_after_first
