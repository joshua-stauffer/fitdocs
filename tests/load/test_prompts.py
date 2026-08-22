"""Tests for the generic prompt flow and interaction sessions (task 1.5, Req 3.1-3.6).

``collect_missing_fields`` is calculator-agnostic: it walks the declared
:class:`AthleteField`s, prompts only for the ones absent from the profile
(asked once, Req 3.3), lets the *session* own the re-ask-on-invalid loop (Req
3.2), persists each accepted answer immediately (Req 3.3), and leaves declined
or non-interactive fields uncomputed without substituting anything (Req 3.4,
3.5). An optional per-field confirm hint echoes derived context and lets the
user re-enter (Req 3.6).

The flow is driven here by a scripted test-double session with queued answers
(never a real TTY); the two shipped sessions -- :class:`RichInteractionSession`
(input source injected) and :class:`NonInteractiveSession` -- are exercised
directly.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable, Sequence
from datetime import date
from io import StringIO

from rich.console import Console

from fitdocs import Sport
from fitdocs.benchmarks import BenchmarkKind
from fitdocs.load.profile import AthleteProfile
from fitdocs.load.prompts import (
    NonInteractiveSession,
    RichInteractionSession,
    collect_missing_fields,
)
from fitdocs.load.types import AthleteField, BenchmarkRef, InteractionSession

_ON: date = date(2024, 3, 1)
"""A fixed date stood in for the pass's "today" wherever a test does not
care about the exact value -- distinct from every ``measured_on`` fixture
date used below so a benchmark test can tell the two apart (Req 6.2)."""

# --- field declarations used to drive the flow -----------------------------
MAX_HR = AthleteField(
    key="max_hr_bpm",
    label="Tested max HR",
    kind="int",
    minimum=120,
    maximum=220,
    help_text="the highest HR you have recorded in a maximal effort",
)
HPL = AthleteField(
    key="acme.threshold",
    label="Acme performance threshold",
    kind="int",
    minimum=1,
    maximum=69,
    help_text="tested performance level from the acme assessment",
)
FTP = AthleteField(
    key="ftp_watts",
    label="FTP",
    kind="float",
    minimum=50,
    maximum=600,
    help_text="functional threshold power in watts",
)
FTP_BENCH = AthleteField(
    key="benchmarks.run.ftp_watts",
    label="Running FTP",
    kind="float",
    minimum=50,
    maximum=600,
    help_text="functional threshold power in watts, running-specific",
    benchmark=BenchmarkRef(kind=BenchmarkKind.FTP_WATTS, discipline=Sport.RUN),
)
FTP_RIDE_BENCH = AthleteField(
    key="benchmarks.ride.ftp_watts",
    label="Cycling FTP",
    kind="float",
    minimum=50,
    maximum=600,
    help_text="functional threshold power in watts, cycling-specific",
    # Same *quantity* as FTP_BENCH, deliberately different *scope* -- the two
    # fields exist to prove the routing reads BOTH ref.kind and
    # ref.discipline, not just one (Finding 1, round 2).
    benchmark=BenchmarkRef(kind=BenchmarkKind.FTP_WATTS, discipline=Sport.RIDE),
)
MAX_HR_BENCH = AthleteField(
    key="benchmarks.athlete.max_hr_bpm",
    label="Max HR",
    kind="int",
    minimum=120,
    maximum=220,
    help_text="the highest HR you have recorded in a maximal effort",
    # Athlete-wide scope (discipline=None) and a different quantity than
    # FTP_WATTS -- exercises the ATHLETE_SCOPED half of BenchmarkRef through
    # the prompt flow, which no test previously did (Finding 1, round 2).
    benchmark=BenchmarkRef(kind=BenchmarkKind.MAX_HR_BPM, discipline=None),
)


# --- scripted test-double session ------------------------------------------
class ScriptedSession:
    """An :class:`InteractionSession` with queued answers, recording activity.

    Each ask/confirm/choose pops the next queued answer for that primitive and
    records the exact question text; ``inform`` records the message. A queued
    ``None`` models a decline / non-interactive answer.
    """

    def __init__(
        self,
        *,
        ints: Sequence[int | None] = (),
        floats: Sequence[float | None] = (),
        confirms: Sequence[bool | None] = (),
        choices: Sequence[int | None] = (),
    ) -> None:
        self.ints: deque[int | None] = deque(ints)
        self.floats: deque[float | None] = deque(floats)
        self.confirms: deque[bool | None] = deque(confirms)
        self.choices: deque[int | None] = deque(choices)
        self.asked: list[str] = []
        self.informed: list[str] = []

    def confirm(self, question: str, *, default: bool = True) -> bool | None:
        self.asked.append(question)
        return self.confirms.popleft()

    def ask_int(
        self,
        question: str,
        *,
        minimum: int | None = None,
        maximum: int | None = None,
        default: int | None = None,
    ) -> int | None:
        self.asked.append(question)
        return self.ints.popleft()

    def ask_float(
        self,
        question: str,
        *,
        minimum: float | None = None,
        maximum: float | None = None,
        default: float | None = None,
    ) -> float | None:
        self.asked.append(question)
        return self.floats.popleft()

    def choose(
        self,
        question: str,
        options: Sequence[str],
        *,
        default_index: int | None = None,
    ) -> int | None:
        self.asked.append(question)
        return self.choices.popleft()

    def inform(self, message: str) -> None:
        self.informed.append(message)


def _recording_persist() -> tuple[
    list[AthleteProfile], Callable[[AthleteProfile], None]
]:
    saved: list[AthleteProfile] = []

    def persist(profile: AthleteProfile) -> None:
        saved.append(profile)

    return saved, persist


def _queued_input(answers: Sequence[str]) -> Callable[[str], str]:
    pending = deque(answers)

    def _input(prompt: str) -> str:
        return pending.popleft()

    return _input


def _race_times_hint(value: float) -> str:
    """Stub confirm-hint (not a real derived lookup table)."""
    return f"race-times-for-{int(value)}"


# --- collect_missing_fields: valid -> immediate persist (3.3) --------------
def test_valid_answer_persists_immediately_and_is_returned() -> None:
    profile = AthleteProfile(data={})
    session = ScriptedSession(ints=[200])
    saved, persist = _recording_persist()

    updated, missing = collect_missing_fields(
        [MAX_HR], profile, session, persist, on=_ON
    )

    assert missing == ()
    assert updated.get_number("max_hr_bpm") == 200
    # persisted exactly once, with the accepted value already in the document
    assert len(saved) == 1
    assert saved[0].get_number("max_hr_bpm") == 200
    # the prompt presented the field's meaning and valid range (3.2)
    assert len(session.asked) == 1
    question = session.asked[0]
    assert "Tested max HR" in question
    assert "highest HR" in question
    assert "120" in question and "220" in question


# --- collect_missing_fields: already-present field skipped (3.3) -----------
def test_present_field_is_not_prompted() -> None:
    profile = AthleteProfile(data={"max_hr_bpm": 195})
    session = ScriptedSession()
    saved, persist = _recording_persist()

    updated, missing = collect_missing_fields(
        [MAX_HR], profile, session, persist, on=_ON
    )

    assert missing == ()
    assert session.asked == []  # never asked
    assert saved == []  # nothing re-persisted
    assert updated.get_number("max_hr_bpm") == 195


# --- collect_missing_fields: declined (3.4) --------------------------------
def test_declined_field_stays_missing_and_is_not_persisted() -> None:
    profile = AthleteProfile(data={})
    session = ScriptedSession(ints=[None])  # None == declined
    saved, persist = _recording_persist()

    updated, missing = collect_missing_fields(
        [MAX_HR], profile, session, persist, on=_ON
    )

    assert missing == (MAX_HR,)
    assert saved == []  # not persisted -- no substitution (3.4)
    assert updated.get_number("max_hr_bpm") is None  # profile unchanged
    assert updated.data == {}


# --- collect_missing_fields: non-interactive (3.5) -------------------------
def test_non_interactive_session_leaves_all_fields_missing() -> None:
    profile = AthleteProfile(data={})
    session = NonInteractiveSession()
    saved, persist = _recording_persist()

    updated, missing = collect_missing_fields(
        [MAX_HR, HPL], profile, session, persist, on=_ON
    )

    assert missing == (MAX_HR, HPL)  # every missing field returned
    assert saved == []  # never persisted, never blocked
    assert updated.data == {}


# --- collect_missing_fields: hint echoed + re-enter (3.6) ------------------
def test_hint_is_echoed_and_user_may_re_enter() -> None:
    profile = AthleteProfile(data={})
    # V1 then confirm=False (re-ask), V2 then confirm=True (accept)
    session = ScriptedSession(ints=[40, 55], confirms=[False, True])
    saved, persist = _recording_persist()

    updated, missing = collect_missing_fields(
        [HPL],
        profile,
        session,
        persist,
        hints={"acme.threshold": _race_times_hint},
        on=_ON,
    )

    assert missing == ()
    # the hint text for BOTH entries was echoed via inform (3.6)
    assert "race-times-for-40" in session.informed
    assert "race-times-for-55" in session.informed
    # the re-ask happened: HPL was asked twice
    assert session.asked.count(session.asked[0]) == 2
    # the final persisted value is V2, not V1
    assert updated.get_number("acme.threshold") == 55
    assert saved[-1].get_number("acme.threshold") == 55


def test_hint_confirm_decline_leaves_field_missing() -> None:
    profile = AthleteProfile(data={})
    session = ScriptedSession(ints=[40], confirms=[None])  # confirm None == decline
    saved, persist = _recording_persist()

    updated, missing = collect_missing_fields(
        [HPL],
        profile,
        session,
        persist,
        hints={"acme.threshold": _race_times_hint},
        on=_ON,
    )

    assert missing == (HPL,)
    assert saved == []
    assert updated.get_number("acme.threshold") is None


# --- collect_missing_fields: multiple fields threaded ----------------------
def test_multiple_missing_fields_threaded_and_each_persisted() -> None:
    profile = AthleteProfile(data={})
    session = ScriptedSession(ints=[200, 42])
    saved, persist = _recording_persist()

    updated, missing = collect_missing_fields(
        [MAX_HR, HPL], profile, session, persist, on=_ON
    )

    assert missing == ()
    # persisted once per accepted answer (3.3)
    assert len(saved) == 2
    # first persist has only the first field ...
    assert saved[0].get_number("max_hr_bpm") == 200
    assert saved[0].get_number("acme.threshold") is None
    # ... the second (threaded forward) has both
    assert saved[1].get_number("max_hr_bpm") == 200
    assert saved[1].get_number("acme.threshold") == 42
    assert updated.get_number("max_hr_bpm") == 200
    assert updated.get_number("acme.threshold") == 42


def test_float_field_uses_ask_float() -> None:
    profile = AthleteProfile(data={})
    session = ScriptedSession(floats=[250.0])
    saved, persist = _recording_persist()

    updated, missing = collect_missing_fields([FTP], profile, session, persist, on=_ON)

    assert missing == ()
    assert updated.get_number("ftp_watts") == 250.0
    assert saved[-1].get_number("ftp_watts") == 250.0


# --- RichInteractionSession: ask_int re-ask on invalid then valid ----------
def test_rich_ask_int_reasks_on_unparseable_and_out_of_range() -> None:
    console = Console(file=StringIO(), width=200)
    # "abc" (unparseable) -> "300" (out of range 120-220) -> "200" (valid)
    session = RichInteractionSession(
        console=console, input_fn=_queued_input(["abc", "300", "200"])
    )

    value = session.ask_int("Tested max HR (120-220)", minimum=120, maximum=220)

    assert value == 200
    output = console.file.getvalue()  # type: ignore[union-attr]
    # the range/help was shown (on the initial prompt and on re-ask)
    assert "120" in output and "220" in output


def test_rich_ask_int_skip_keyword_returns_none() -> None:
    console = Console(file=StringIO(), width=200)
    session = RichInteractionSession(console=console, input_fn=_queued_input(["s"]))
    assert session.ask_int("Tested max HR", minimum=120, maximum=220) is None

    session2 = RichInteractionSession(
        console=Console(file=StringIO(), width=200),
        input_fn=_queued_input(["skip"]),
    )
    assert session2.ask_int("Tested max HR", minimum=120, maximum=220) is None


def test_rich_ask_float_reasks_then_valid_and_skips() -> None:
    console = Console(file=StringIO(), width=200)
    # "abc" -> "700" (out of range) -> "250.5" (valid)
    session = RichInteractionSession(
        console=console, input_fn=_queued_input(["abc", "700", "250.5"])
    )
    value = session.ask_float("FTP (50-600)", minimum=50.0, maximum=600.0)
    assert value == 250.5
    output = console.file.getvalue()  # type: ignore[union-attr]
    assert "50" in output and "600" in output

    skip_session = RichInteractionSession(
        console=Console(file=StringIO(), width=200),
        input_fn=_queued_input(["skip"]),
    )
    assert skip_session.ask_float("FTP", minimum=50.0, maximum=600.0) is None


def test_rich_confirm_yes_no_default_and_skip() -> None:
    yes = RichInteractionSession(
        console=Console(file=StringIO(), width=200),
        input_fn=_queued_input(["y"]),
    )
    assert yes.confirm("OK?") is True

    no = RichInteractionSession(
        console=Console(file=StringIO(), width=200),
        input_fn=_queued_input(["n"]),
    )
    assert no.confirm("OK?") is False

    empty_default = RichInteractionSession(
        console=Console(file=StringIO(), width=200),
        input_fn=_queued_input([""]),
    )
    assert empty_default.confirm("OK?", default=True) is True
    empty_default_false = RichInteractionSession(
        console=Console(file=StringIO(), width=200),
        input_fn=_queued_input([""]),
    )
    assert empty_default_false.confirm("OK?", default=False) is False

    skip = RichInteractionSession(
        console=Console(file=StringIO(), width=200),
        input_fn=_queued_input(["s"]),
    )
    assert skip.confirm("OK?") is None


def test_rich_confirm_reasks_on_garbage() -> None:
    session = RichInteractionSession(
        console=Console(file=StringIO(), width=200),
        input_fn=_queued_input(["maybe", "yes"]),
    )
    assert session.confirm("OK?") is True


def test_rich_choose_valid_index_and_skip() -> None:
    console = Console(file=StringIO(), width=200)
    session = RichInteractionSession(console=console, input_fn=_queued_input(["2"]))
    # "2" (1-based) -> index 1 (0-based)
    assert session.choose("Pick one", ["Zone 1", "Zone 2", "Zone 3"]) == 1
    output = console.file.getvalue()  # type: ignore[union-attr]
    assert "Zone 2" in output  # options were listed

    skip = RichInteractionSession(
        console=Console(file=StringIO(), width=200),
        input_fn=_queued_input(["skip"]),
    )
    assert skip.choose("Pick one", ["a", "b"]) is None


def test_rich_choose_reasks_on_out_of_range() -> None:
    session = RichInteractionSession(
        console=Console(file=StringIO(), width=200),
        input_fn=_queued_input(["9", "0", "1"]),
    )
    assert session.choose("Pick one", ["a", "b", "c"]) == 0


def test_rich_inform_writes_to_console() -> None:
    console = Console(file=StringIO(), width=200)
    session = RichInteractionSession(console=console)
    session.inform("race-times-for-42")
    assert "race-times-for-42" in console.file.getvalue()  # type: ignore[union-attr]


# --- NonInteractiveSession: every primitive returns None -------------------
def test_non_interactive_session_returns_none_and_informs_silently() -> None:
    session = NonInteractiveSession()
    assert session.ask_int("HR", minimum=120, maximum=220) is None
    assert session.ask_float("FTP", minimum=50.0, maximum=600.0) is None
    assert session.confirm("OK?") is None
    assert session.choose("Pick", ["a", "b"]) is None
    # inform is a no-op and never raises / never blocks
    assert session.inform("anything") is None


# --- both sessions structurally satisfy InteractionSession -----------------
def test_sessions_conform_to_interaction_session_protocol() -> None:
    rich: InteractionSession = RichInteractionSession(
        console=Console(file=StringIO(), width=200)
    )
    non_interactive: InteractionSession = NonInteractiveSession()
    assert rich is not None
    assert non_interactive is not None


# --- collect_missing_fields: benchmark field routing (task 4.2, Req 8.*) ---
# A declared benchmark field's "already have it" check is `has_benchmark`
# (undated), and an accepted answer is written via `with_benchmark(measured_on
# =on)` -- both distinct from a flat field's `get_number`/`with_value` path,
# exercised above and left unchanged by every test in this section.


class _RecordingNonInteractiveSession(NonInteractiveSession):
    """The real, shipped :class:`NonInteractiveSession` behavior (every
    primitive still returns ``None``), plus a call counter -- so a test can
    assert the flow actually *reached* the session, distinguishing "declined
    because non-interactive" from "never asked because already present"
    (fixture-discrimination hazard 3: a zero call count is what both produce).
    """

    def __init__(self) -> None:
        self.ask_float_calls = 0

    def ask_float(
        self,
        question: str,
        *,
        minimum: float | None = None,
        maximum: float | None = None,
        default: float | None = None,
    ) -> float | None:
        self.ask_float_calls += 1
        return super().ask_float(
            question, minimum=minimum, maximum=maximum, default=default
        )


def test_benchmark_with_nothing_on_file_prompted_once_and_persisted_with_on() -> None:
    """Req 8.1, 8.2, 8.7: a declared benchmark field with no entry on file is
    prompted exactly once, and an accepted answer is persisted immediately as
    a dated measurement stamped with the ``on`` the caller supplied -- not
    "today" in the real, un-injected sense, and not any other fixture date.

    Two declared fields are routed here, deliberately differing in BOTH
    quantity and scope -- ``FTP_BENCH`` (FTP_WATTS, discipline-scoped to Run)
    and ``MAX_HR_BENCH`` (MAX_HR_BPM, athlete-wide / discipline=None). Each
    entry is asserted to land under its OWN declared kind and scope, which a
    routing that ignores ``ref.kind`` or ``ref.discipline`` (hardcoding one
    quantity/scope for every field) cannot satisfy for both simultaneously
    (Finding 1, round 2). Both hardcodes redden this test, and both do so from
    the *presence check* at ``prompts.py:111`` -- the write is never reached,
    so neither mutation exercises ``with_benchmark``'s guard: hardcoding
    ``ref.kind`` to ``BenchmarkKind.FTP_WATTS`` makes MAX_HR_BENCH query a
    discipline-scoped kind with ``discipline=None``, and hardcoding
    ``discipline=ref.discipline`` to ``Sport.RUN`` makes it query an
    athlete-wide kind with a discipline; ``AthleteProfile.has_benchmark``
    rejects each as a scope mismatch.

    Those two kills therefore rest on a scope *guard*, not on an assertion
    about where the entry landed. The write site is pinned separately and by
    assertion: mis-routing only the ``with_benchmark`` call, to a legal
    kind/scope pair that trips no guard, reddens ``hr_entry is not None``
    below as a sole failure.
    """
    profile = AthleteProfile(data={})
    session = ScriptedSession(floats=[275.0], ints=[190])
    saved, persist = _recording_persist()
    stamped = date(2025, 5, 20)  # distinct from `_ON` and every other fixture date

    updated, missing = collect_missing_fields(
        [FTP_BENCH, MAX_HR_BENCH], profile, session, persist, on=stamped
    )

    assert missing == ()
    assert len(session.asked) == 2  # each asked exactly once (8.2)
    assert len(saved) == 2  # persisted immediately, once per field (8.7)

    entry = updated.benchmark(BenchmarkKind.FTP_WATTS, discipline=Sport.RUN, on=stamped)
    assert entry is not None
    assert entry.value == 275.0
    assert entry.measured_on == stamped  # stamped with the provided date, not today's

    saved_entry = saved[-1].benchmark(
        BenchmarkKind.FTP_WATTS, discipline=Sport.RUN, on=stamped
    )
    assert saved_entry is not None and saved_entry.measured_on == stamped

    hr_entry = updated.benchmark(BenchmarkKind.MAX_HR_BPM, discipline=None, on=stamped)
    assert hr_entry is not None
    assert hr_entry.value == 190
    assert hr_entry.measured_on == stamped


def test_benchmark_field_and_flat_field_share_one_declaration_list() -> None:
    """Req 8.1: a benchmark field is declared and collected through the exact
    same ``fields`` sequence and per-kind ``ask_int``/``ask_float`` routing as
    a flat field -- no separate mechanism.
    """
    profile = AthleteProfile(data={})
    session = ScriptedSession(ints=[200], floats=[275.0])
    saved, persist = _recording_persist()
    on = date(2023, 11, 2)

    updated, missing = collect_missing_fields(
        [MAX_HR, FTP_BENCH], profile, session, persist, on=on
    )

    assert missing == ()
    assert len(session.asked) == 2
    assert updated.get_number("max_hr_bpm") == 200
    entry = updated.benchmark(BenchmarkKind.FTP_WATTS, discipline=Sport.RUN, on=on)
    assert entry is not None and entry.value == 275.0


def test_benchmark_on_file_is_not_reprompted_even_when_on_predates_every_entry() -> (
    None
):
    """Req 8.3, 8.4 (prompt-suppression half only -- the reporting half of 8.4
    is task 6.1's, asserted at the report level): a benchmark on file is never
    re-asked, even when the pass's ``on`` predates every recorded
    ``measured_on`` -- i.e. even when :meth:`AthleteProfile.benchmark` (the
    *dated* lookup) would return ``None`` for that same ``on``.

    Fixture-discrimination hazard 2: the on-file entry's ``measured_on`` is
    deliberately AFTER ``on`` passed here, so ``has_benchmark`` (True, undated)
    and ``benchmark(..., on=on)`` (None, dated) genuinely disagree. A fixture
    where the entry predates ``on`` would leave both predicates true and hide
    a swap of ``has_benchmark`` for ``benchmark(..., on=on)`` in the "already
    have it" check.

    Mutation verified by hand: replacing this module's
    ``profile.has_benchmark(ref.kind, discipline=ref.discipline)`` with
    ``profile.benchmark(ref.kind, discipline=ref.discipline, on=on) is not
    None`` reddens this test as the suite's sole failure (2006/2007, measured
    with ``__pycache__`` cleared).

    Deliberately not describing *how* it reds. Under the fixture as it stands
    the observable is ``IndexError: pop from an empty deque`` -- the
    wrongly-unsuppressed field consumes a queued answer and a later field
    starves -- rather than the ``assert len(session.asked) == 1`` below. Which
    of the two fires depends on how many answers this test happens to queue,
    and that changed once already when ``FTP_RIDE_BENCH`` was added here. An
    earlier version of this docstring named a mechanism that its own test had
    since invalidated; the durable claim is the sole failure, not the route.

    Also routes ``FTP_RIDE_BENCH`` -- same quantity (FTP_WATTS) as the
    on-file entry but a DIFFERENT scope (Ride, not Run) -- alongside
    ``FTP_BENCH`` in the same pass, to prove an on-file entry for one scope
    does NOT suppress the prompt for another scope of the same quantity
    (Req 8.2/8.3's "of that quantity and scope" clause; Finding 1, round 2).
    A ``discipline=ref.discipline`` hardcode (e.g. to ``Sport.RUN``) would
    make the "already have it" check for FTP_RIDE_BENCH consult the Run entry
    instead of Ride, wrongly skip the prompt, and file the accepted answer
    (were one ever accepted) under the wrong scope.
    """
    on = date(2020, 1, 1)
    entry_date = date(2026, 6, 1)  # strictly AFTER `on` -- see hazard note above
    assert entry_date > on
    base = AthleteProfile(data={}).with_benchmark(
        BenchmarkKind.FTP_WATTS,
        discipline=Sport.RUN,
        value=300.0,
        measured_on=entry_date,
    )
    # Precondition sanity: the dated lookup for `on` really is None, while the
    # undated presence check really is True -- the two predicates disagree.
    assert base.benchmark(BenchmarkKind.FTP_WATTS, discipline=Sport.RUN, on=on) is None
    assert base.has_benchmark(BenchmarkKind.FTP_WATTS, discipline=Sport.RUN) is True
    # Precondition sanity: nothing on file yet for the Ride scope.
    assert base.has_benchmark(BenchmarkKind.FTP_WATTS, discipline=Sport.RIDE) is False

    session = ScriptedSession(floats=[310.0])  # only FTP_RIDE_BENCH may be asked
    saved, persist = _recording_persist()

    updated, missing = collect_missing_fields(
        [FTP_BENCH, FTP_RIDE_BENCH], base, session, persist, on=on
    )

    assert missing == ()  # FTP_BENCH not reported still-missing (8.3, 8.4 prompt half)
    assert len(session.asked) == 1  # only FTP_RIDE_BENCH was prompted
    assert len(saved) == 1  # only FTP_RIDE_BENCH's accepted answer was persisted

    ride_entry = updated.benchmark(
        BenchmarkKind.FTP_WATTS, discipline=Sport.RIDE, on=on
    )
    assert ride_entry is not None
    assert ride_entry.value == 310.0
    # The Run entry is untouched by the Ride field's acceptance.
    run_entry = updated.benchmark(BenchmarkKind.FTP_WATTS, discipline=Sport.RUN, on=on)
    assert run_entry is None  # dated lookup for `on`, which predates it -- unchanged
    assert updated.has_benchmark(BenchmarkKind.FTP_WATTS, discipline=Sport.RUN) is True


def test_declined_benchmark_answer_persists_nothing_and_leaves_profile_untouched() -> (
    None
):
    """Req 8.5: a declined benchmark answer persists nothing and the field is
    reported still-missing -- asserted before AND after (hazard 3: an
    unchanged-after-only check proves nothing if the profile started that
    way, which it always does for "nothing on file").
    """
    profile = AthleteProfile(data={})
    assert profile.has_benchmark(BenchmarkKind.FTP_WATTS, discipline=Sport.RUN) is False
    session = ScriptedSession(floats=[None])  # None == declined
    saved, persist = _recording_persist()

    updated, missing = collect_missing_fields(
        [FTP_BENCH], profile, session, persist, on=_ON
    )

    assert missing == (FTP_BENCH,)
    assert saved == []  # not persisted
    assert updated.has_benchmark(BenchmarkKind.FTP_WATTS, discipline=Sport.RUN) is False
    assert updated.data == {}  # untouched


def test_non_interactive_session_prompts_nothing_for_a_benchmark_field() -> None:
    """Req 8.6: a non-interactive session never blocks and persists nothing
    for a benchmark field, but the field IS reached -- ``ask_float_calls == 1``
    proves the session was actually consulted (hazard 3), ruling out the
    "skipped because already present" confound (profile starts empty here).
    """
    profile = AthleteProfile(data={})
    session = _RecordingNonInteractiveSession()
    saved, persist = _recording_persist()

    updated, missing = collect_missing_fields(
        [FTP_BENCH], profile, session, persist, on=_ON
    )

    assert session.ask_float_calls == 1  # the session WAS reached
    assert missing == (FTP_BENCH,)
    assert saved == []
    assert updated.data == {}


def test_collect_missing_fields_on_is_keyword_only() -> None:
    """Pins the ``on`` parameter's shape (design's ``PromptFlowIntegration``
    Service Interface) -- a declared type/kind is pinned by nothing unless a
    test reads it (task 4.1's rejection)."""
    import inspect

    params = inspect.signature(collect_missing_fields).parameters
    on_param = params["on"]
    assert on_param.kind is inspect.Parameter.KEYWORD_ONLY
    assert on_param.default is inspect.Parameter.empty  # required, no default
    assert on_param.annotation == "date"
