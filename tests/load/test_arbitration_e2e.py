"""End-to-end proof of the arbitration and prompting boundaries (task 6.1).

Every scenario below drives :func:`fitdocs.load.engine.apply_load` over a real
temporary data root built through the actual sync pipeline (never a hand-mocked
string), and asserts on the returned :class:`~fitdocs.load.engine.LoadReport`
bucket and on a recording :class:`~fitdocs.load.types.InteractionSession`'s own
prompt log -- never on printed output (the task's own Observable) -- per the
requirements this module pins: 1.12, 1.14, 3.1, 10.2, 10.4, 10.5, 14.5, 14.6.

Deliberately its own module (task 6.1's boundary), disjoint from
``test_engine.py`` (which already proves many of these clauses for the tasks
that introduced them) and from tasks 6.2/6.3's modules. None of the scenarios
here reuse ``test_engine.py``'s own test functions -- each is independently
constructed so this module's mutation evidence stands on its own.

Several stub calculators below deliberately do **not** self-guard their own
modality inside ``compute`` (unlike every stub in ``tests/load/conftest.py``
except ``DecliningCalculator``) -- Implementation Notes from task 4.1's review
record that a self-guarding stub's ``compute`` shadows the engine's own gate,
so deleting the gate changes nothing observable. Where this module's point is
specifically "the engine's own gate fired", the stub instead raises if
``compute`` is ever reached for an activity it should never have been handed,
turning a silently-passing mutation into a per-document failure.
"""

from __future__ import annotations

import tomllib
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from datetime import timedelta, timezone
from pathlib import Path

import pytest
import yaml

from fitdocs import Modality, Sport
from fitdocs.athlete import load_athlete_inputs
from fitdocs.docio import read_frontmatter
from fitdocs.layout import SETTINGS_FILE, WORKOUTS_DIR
from fitdocs.load import THRESHOLD_CALCULATOR, registry
from fitdocs.load import engine as load_engine
from fitdocs.load.engine import DocLoadEntry, apply_load
from fitdocs.load.profile import PROFILE_FILENAME
from fitdocs.load.registry import UnknownCalculatorError
from fitdocs.load.settings import LoadSettingsError
from fitdocs.load.types import (
    AthleteField,
    Computed,
    LoadContext,
    LoadOutcome,
    LoadResult,
    NotComputed,
)
from fitdocs.render.charts.map import TileRef
from fitdocs.sync import sync
from tests.fixtures import builder
from tests.load.conftest import (
    HINTED_FIELD,
    DecliningCalculator,
    HintedCalculator,
)

_TZ = timezone(timedelta(hours=-6))


@contextmanager
def _threshold_built_in_excluded() -> Iterator[None]:
    """Temporarily excludes ``THRESHOLD_CALCULATOR`` from the registry so a
    stub can be the sole supporter of a modality it also declares, then
    restores exactly what this excluded -- never more.

    A bare ``registry.unregister(...)`` / ``finally: registry.register(...)``
    pair *installs* the built-in on exit regardless of whether it was there
    on entry: if the product ever fails to register it (e.g. task 4.1's
    ``register(THRESHOLD_CALCULATOR)`` call is missing or broken), this
    unconditional restore silently repairs that defect for the rest of the
    test session, masking it from every test that runs afterward
    (REMEDIATION ROUND 1 finding 5). Checking presence first and restoring
    only when this context actually removed it closes that gap: with the
    product registration missing, entry finds nothing to remove, so exit
    installs nothing either, and the defect stays visible to every test that
    depends on the built-in being registered.
    """
    was_registered = THRESHOLD_CALCULATOR.calculator_id in {
        c.calculator_id for c in registry.available()
    }
    if was_registered:
        registry.unregister(THRESHOLD_CALCULATOR.calculator_id)
    try:
        yield
    finally:
        if was_registered:
            registry.register(THRESHOLD_CALCULATOR)


# --- shared scaffolding ------------------------------------------------------


class _ServingTiles:
    """Inert basemap-tile source: the engine only cares about the load region."""

    attribution = "© OpenStreetMap contributors"

    def resolve(self, refs: Sequence[TileRef]) -> dict[TileRef, bytes]:
        return {ref: b"\x89PNG\r\n\x1a\n" for ref in refs}


_TILES: _ServingTiles = _ServingTiles()


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


def _doc(data_root: Path, needle: str) -> Path:
    return next(p for p in (data_root / WORKOUTS_DIR).glob("*.md") if needle in p.name)


def _rel(data_root: Path, doc: Path) -> str:
    return doc.relative_to(data_root).as_posix()


def _docs_of(entries: tuple[DocLoadEntry, ...]) -> set[str]:
    return {entry.doc for entry in entries}


def _write_load_settings(data_root: Path, toml_text: str) -> None:
    (data_root / SETTINGS_FILE).write_text(toml_text, encoding="utf-8")


def _snapshot(data_root: Path) -> dict[str, bytes]:
    return {
        p.relative_to(data_root).as_posix(): p.read_bytes()
        for p in sorted(data_root.rglob("*"))
        if p.is_file()
    }


# A generic sport-labelled synthetic .fit fixture, via the shared
# ``builder.small_sport_fit_bytes`` -- so a Rowing/Hike document decodes and
# syncs through the identical real pipeline. ``builder`` ships no dedicated
# rowing fixture of its own.


def _rowing_fit_bytes(serial: int = 3001) -> bytes:
    return builder.small_sport_fit_bytes(serial, "rowing")


def _hike_fit_bytes(serial: int = 3002) -> bytes:
    return builder.small_sport_fit_bytes(serial, "hiking")


def _walk_fit_bytes(serial: int = 3003) -> bytes:
    return builder.small_sport_fit_bytes(serial, "walking")


# A recording InteractionSession: never blocks (queues answer everything with a
# fixed reply), and logs every prompt kind+question plus every inform() call in
# call order -- the primary evidence for "prompt count asserted on the session".
class _RecordingSession:
    def __init__(
        self,
        *,
        int_answer: int | None = 1,
        float_answer: float | None = 1.0,
        confirm_answer: bool | None = True,
    ) -> None:
        self.prompts: list[str] = []
        self.informs: list[str] = []
        self._int_answer = int_answer
        self._float_answer = float_answer
        self._confirm_answer = confirm_answer

    def confirm(self, question: str, *, default: bool = True) -> bool | None:
        self.prompts.append(f"confirm:{question}")
        return self._confirm_answer

    def ask_int(
        self,
        question: str,
        *,
        minimum: int | None = None,
        maximum: int | None = None,
        default: int | None = None,
    ) -> int | None:
        self.prompts.append(f"ask_int:{question}")
        return self._int_answer

    def ask_float(
        self,
        question: str,
        *,
        minimum: float | None = None,
        maximum: float | None = None,
        default: float | None = None,
    ) -> float | None:
        self.prompts.append(f"ask_float:{question}")
        return self._float_answer

    def choose(
        self,
        question: str,
        options: object,
        *,
        default_index: int | None = None,
    ) -> int | None:
        self.prompts.append(f"choose:{question}")
        return None

    def inform(self, message: str) -> None:
        self.informs.append(message)


class _ScriptedSession:
    """A FIFO-queue :class:`InteractionSession` that raises on over-asking, so
    an unexpected extra prompt (e.g. a second document re-asking a field
    already persisted, or a supposedly-gated document prompting at all) fails
    loudly rather than silently returning a fabricated answer.
    """

    def __init__(
        self,
        *,
        confirms: list[bool | None] | None = None,
        floats: list[float | None] | None = None,
        ints: list[int | None] | None = None,
    ) -> None:
        self._confirms = list(confirms or [])
        self._floats = list(floats or [])
        self._ints = list(ints or [])
        self.prompts: list[str] = []
        self.informs: list[str] = []

    def _pop(self, queue: list[object], kind: str) -> object:
        if not queue:
            raise AssertionError(f"unexpected extra {kind} prompt")
        return queue.pop(0)

    def confirm(self, question: str, *, default: bool = True) -> bool | None:
        self.prompts.append(f"confirm:{question}")
        answer = self._pop(self._confirms, "confirm")  # type: ignore[arg-type]
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
        self.prompts.append(f"ask_int:{question}")
        answer = self._pop(self._ints, "ask_int")  # type: ignore[arg-type]
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
        self.prompts.append(f"ask_float:{question}")
        answer = self._pop(self._floats, "ask_float")  # type: ignore[arg-type]
        assert answer is None or isinstance(answer, (int, float))
        return None if answer is None else float(answer)

    def choose(
        self,
        question: str,
        options: object,
        *,
        default_index: int | None = None,
    ) -> int | None:
        raise AssertionError("choose() not expected in this scenario")

    def inform(self, message: str) -> None:
        self.informs.append(message)


# --- Bullet 1: configured default that does not support the sport ----------
# a second registered calculator that DOES support it must never be invoked.


class _RunOnlyDefaultCalculator:
    """Declares RUN only; unconditionally computes when asked (no self-guard),
    so a mutation deleting the engine's support check would let this stub's
    ``compute`` run for a non-RUN activity too -- reddening this test rather
    than being shadowed by a self-guard."""

    calculator_id = "stub-e2e-run-only-default"
    display_name = "Stub E2E Run-Only Default"
    supported_modalities = frozenset({Modality.RUN})

    def required_athlete_fields(self) -> tuple[AthleteField, ...]:
        return ()

    def compute(
        self,
        activity: object,
        metrics: object,
        profile: object,
        session: object,
        context: LoadContext,
    ) -> LoadOutcome:
        return Computed(
            result=LoadResult(
                calculator_id=self.calculator_id,
                display_name=self.display_name,
                value=1.0,
                basis="stub e2e run-only basis",
                non_selected=(),
                flags=(),
                inputs_used=(),
                notes=(),
            )
        )


class _RowCoveringCalculator:
    """Declares and supports Rowing -- registered alongside the configured RUN
    -only default so a substitution bug (falling back to whichever registered
    calculator WOULD cover the activity) has something to wrongly compute
    with. Its ``compute`` raises if ever invoked."""

    calculator_id = "stub-e2e-row-covering"
    display_name = "Stub E2E Row Covering"
    supported_modalities = frozenset({Modality.OTHER})

    def required_athlete_fields(self) -> tuple[AthleteField, ...]:
        return ()

    def compute(
        self,
        activity: object,
        metrics: object,
        profile: object,
        session: object,
        context: LoadContext,
    ) -> LoadOutcome:
        raise AssertionError(
            "stub-e2e-row-covering must never be invoked: the configured "
            "default must not be silently substituted (Req 10.5)"
        )


def test_configured_default_that_does_not_support_the_sport_is_never_substituted(
    tmp_path: Path,
) -> None:
    """A configured default (RUN-only) applied to a Rowing document writes the
    honest unsupported state; the second registered calculator that DOES
    cover Rowing is never invoked (Req 10.5).

    Mutation caught: the engine's support-check guard at the arbitrated
    :class:`~fitdocs.load.arbitrate.Selected` calculator (engine.py) being
    replaced by a fallback search over the registry would either compute the
    document with ``stub-e2e-row-covering``'s id or raise its
    ``AssertionError`` -- either way this test reddens.
    """
    default = _RunOnlyDefaultCalculator()
    covering = _RowCoveringCalculator()
    registry.register(default)
    registry.register(covering)
    try:
        data_root = _build_data_root(tmp_path, {"row.fit": _rowing_fit_bytes()})
        row = _doc(data_root, "row")
        before = row.read_bytes()
        _write_load_settings(
            data_root, f'[load]\ndefault_calculator = "{default.calculator_id}"\n'
        )

        report = apply_load(data_root, session=_RecordingSession())

        rel = _rel(data_root, row)
        assert rel in _docs_of(report.unsupported)
        assert report.computed == ()
        assert report.failures == ()
        assert row.read_bytes() != before  # the honest state IS written
    finally:
        registry.unregister(default.calculator_id)
        registry.unregister(covering.calculator_id)


# --- Bullet 2: activity-scoped suppression, not a blanket one ---------------

_E2E_LEVEL_FIELD = AthleteField(
    key="e2e-run-level",
    label="E2E run level",
    kind="int",
    minimum=1,
    maximum=10,
    help_text="Bullet-2 field: only reachable for a RUN activity.",
)


class _UnguardedRunOnlyCalculator:
    """Declares RUN only, requires one field, and does not *decline* inside
    ``compute`` the way the shared stubs do -- it **raises** instead. A
    declining self-guard shadows the engine's gate (deleting the gate then
    changes nothing); a raising one surfaces it, so reaching ``compute`` for a
    non-RUN activity becomes a loud defect distinct from "the engine wrote the
    honest state anyway"."""

    calculator_id = "stub-e2e-unguarded-run"
    display_name = "Stub E2E Unguarded Run"
    supported_modalities = frozenset({Modality.RUN})

    def required_athlete_fields(self) -> tuple[AthleteField, ...]:
        return (_E2E_LEVEL_FIELD,)

    def compute(
        self,
        activity: object,
        metrics: object,
        profile: object,
        session: object,
        context: LoadContext,
    ) -> LoadOutcome:
        modality = getattr(activity, "modality", None)
        if modality is not Modality.RUN:
            raise AssertionError(
                "compute() reached for a non-RUN activity -- the engine's "
                "support check (Req 1.14, 3.1) failed to gate it"
            )
        return Computed(
            result=LoadResult(
                calculator_id=self.calculator_id,
                display_name=self.display_name,
                value=1.0,
                basis="stub e2e unguarded-run basis",
                non_selected=(),
                flags=(),
                inputs_used=(),
                notes=(),
            )
        )


def test_configured_default_prompts_only_for_the_activity_it_covers(
    tmp_path: Path,
) -> None:
    """A configured RUN-only default and a fully interactive session: a Ride
    document, driven ALONE against its own fresh data root and profile,
    writes the honest unsupported state with **zero** prompts whatsoever
    (asserted on its own recording session) -- never as skipped for missing
    inputs. The same calculator, driven against a Run document in a SEPARATE
    fresh data root and profile, DOES collect its declared field, proving the
    suppression above is scoped to the activity rather than a blanket "never
    prompt" (Req 1.14, 3.1).

    The two documents are deliberately driven through independent
    ``apply_load`` calls (each its own data root, profile, and session)
    rather than one pass over a shared root: the calculator's single
    declared field has one key, so a shared profile would let a field
    collected under Run persist and mask a spurious Ride-triggered
    collection of the SAME field -- the resulting per-pass prompt count would
    stay unchanged (1) whether or not the Ride document ever reached field
    collection at all, regardless of which document happened to be
    processed first. Isolating the two documents into independent passes
    removes that masking: the Ride assertion (``session.prompts == []``) can
    only pass if field collection for Ride never fires, no matter what any
    other document does.

    Mutation caught: moving the engine's support-check guard (engine.py:488)
    to run after ``collect_missing_fields`` (immediately before
    ``context = LoadContext(...)`` at engine.py:503) lets field collection
    run for the Ride document's own isolated, fresh-profile pass -- with no
    persisted answer available to short-circuit it, ``collect_missing_fields``
    must actually call ``session.ask_int`` to obtain one, so
    ``ride_session.prompts == []`` fails outright.
    """
    calc = _UnguardedRunOnlyCalculator()
    registry.register(calc)
    try:
        ride_base = tmp_path / "ride-only"
        ride_base.mkdir()
        ride_root = _build_data_root(ride_base, {"ride.fit": builder.ride_fit_bytes()})
        ride = _doc(ride_root, "ride")
        _write_load_settings(
            ride_root, f'[load]\ndefault_calculator = "{calc.calculator_id}"\n'
        )
        ride_session = _RecordingSession(int_answer=5, confirm_answer=True)

        ride_report = apply_load(ride_root, session=ride_session)

        ride_rel = _rel(ride_root, ride)
        assert ride_rel in _docs_of(ride_report.unsupported)
        assert ride_rel not in _docs_of(ride_report.skipped)
        assert ride_report.computed == ()
        assert ride_report.failures == ()
        assert ride_session.prompts == []

        run_base = tmp_path / "run-only"
        run_base.mkdir()
        run_root = _build_data_root(run_base, {"run.fit": builder.run_fit_bytes()})
        run = _doc(run_root, "run")
        _write_load_settings(
            run_root, f'[load]\ndefault_calculator = "{calc.calculator_id}"\n'
        )
        run_session = _RecordingSession(int_answer=5, confirm_answer=True)

        run_report = apply_load(run_root, session=run_session)

        run_rel = _rel(run_root, run)
        assert run_rel in _docs_of(run_report.computed)
        assert run_report.failures == ()
        ask_int_prompts = [p for p in run_session.prompts if p.startswith("ask_int:")]
        assert len(ask_int_prompts) == 1
        assert _E2E_LEVEL_FIELD.label in ask_int_prompts[0]
    finally:
        registry.unregister(calc.calculator_id)


# --- Bullet 3: sport-granular decline inside a declared modality ------------


class _CountingDecliningCalculator(DecliningCalculator):
    """:class:`DecliningCalculator` (Req 1.14, 10.5's fixture: declares the
    broad ``Modality.OTHER``, narrows ``supports`` to refuse ``Sport.ROWING``
    only) wrapped to COUNT ``compute`` invocations.

    ``DecliningCalculator.compute`` unconditionally returns ``Unsupported``
    regardless of sport, so the *report bucket* alone cannot tell apart "the
    engine's ``supports_activity`` gate caught Rowing before ``compute`` was
    ever called" from "the gate is gone and ``compute`` declined it anyway" --
    both land the document in ``report.unsupported`` with zero prompts (no
    fields are declared either way). ``compute_calls`` is what makes the two
    distinguishable: it must stay ``0`` for a sport the calculator's own
    ``supports`` refuses.
    """

    def __init__(self) -> None:
        self.compute_calls = 0

    def compute(
        self,
        activity: object,
        metrics: object,
        profile: object,
        session: object,
        context: LoadContext,
    ) -> LoadOutcome:
        self.compute_calls += 1
        return super().compute(activity, metrics, profile, session, context)  # type: ignore[arg-type]


def test_supports_question_narrows_a_declared_modality_by_sport(
    tmp_path: Path,
) -> None:
    """``DecliningCalculator`` declares the broad ``Modality.OTHER`` but
    narrows ``supports`` to refuse ``Sport.ROWING`` specifically. Configured
    as the default (so arbitration returns it unconditionally, sport-blind,
    per Req 10.3/10.5) and applied to a Rowing document: the engine's own
    support check must catch what arbitration's forced/configured branch
    deliberately does not -- no prompt, honest unsupported state, and
    ``compute`` never invoked at all (Req 1.14).

    Mutation caught: deleting (or reordering after field collection) the
    engine's ``supports_activity`` gate at the arbitrated calculator would let
    ``compute`` be reached for Rowing -- ``compute_calls`` becomes ``1``
    instead of ``0`` even though the *report bucket* is unchanged (this
    stub's ``compute`` unconditionally declines regardless of sport, as
    documented defence-in-depth), which is exactly why the bucket alone
    cannot discriminate this clause and the call count is asserted directly.
    """
    calc = _CountingDecliningCalculator()
    registry.register(calc)
    try:
        data_root = _build_data_root(tmp_path, {"row.fit": _rowing_fit_bytes()})
        row = _doc(data_root, "row")
        _write_load_settings(
            data_root, f'[load]\ndefault_calculator = "{calc.calculator_id}"\n'
        )
        session = _RecordingSession()

        report = apply_load(data_root, session=session)

        rel = _rel(data_root, row)
        assert rel in _docs_of(report.unsupported)
        assert rel not in _docs_of(report.skipped)
        assert session.prompts == []
        assert calc.compute_calls == 0
    finally:
        registry.unregister(calc.calculator_id)


# --- Bullet 4: two broad-modality supporters, narrowed by sport -------------


class _BroadModalityHikeOnly:
    """Declares ``Modality.OTHER``; ``supports`` narrows to Hike only."""

    calculator_id = "stub-e2e-broad-hike"
    display_name = "Stub E2E Broad Hike-Only"
    supported_modalities = frozenset({Modality.OTHER})

    def required_athlete_fields(self) -> tuple[AthleteField, ...]:
        return ()

    def supports(self, activity: object) -> bool:
        modality = getattr(activity, "modality", None)
        sport = getattr(activity, "sport", None)
        return modality in self.supported_modalities and sport is Sport.HIKE

    def compute(
        self,
        activity: object,
        metrics: object,
        profile: object,
        session: object,
        context: LoadContext,
    ) -> LoadOutcome:
        sport = getattr(activity, "sport", None)
        if sport is not Sport.HIKE:
            raise AssertionError(
                "stub-e2e-broad-hike computed a non-Hike activity -- "
                "arbitration's narrowing (Req 10.2) failed"
            )
        return Computed(
            result=LoadResult(
                calculator_id=self.calculator_id,
                display_name=self.display_name,
                value=1.0,
                basis="stub e2e broad-hike basis",
                non_selected=(),
                flags=(),
                inputs_used=(),
                notes=(),
            )
        )


class _BroadModalityWalkOnly:
    """Declares ``Modality.OTHER``; ``supports`` narrows to Walk only. Its
    ``compute`` raises unconditionally: it must never be selected in either
    scenario this pair drives (Rowing: neither supports; Hike: only the other
    one supports)."""

    calculator_id = "stub-e2e-broad-walk"
    display_name = "Stub E2E Broad Walk-Only"
    supported_modalities = frozenset({Modality.OTHER})

    def required_athlete_fields(self) -> tuple[AthleteField, ...]:
        return ()

    def supports(self, activity: object) -> bool:
        modality = getattr(activity, "modality", None)
        sport = getattr(activity, "sport", None)
        return modality in self.supported_modalities and sport is Sport.WALK

    def compute(
        self,
        activity: object,
        metrics: object,
        profile: object,
        session: object,
        context: LoadContext,
    ) -> LoadOutcome:
        raise AssertionError("stub-e2e-broad-walk must never be invoked")


def test_two_broad_supporters_neither_covering_the_sport_is_unsupported_not_ambiguous(
    tmp_path: Path,
) -> None:
    """Two calculators declare the same broad modality; neither supports
    Rowing (one narrows to Hike, the other to Walk). No default is
    configured: the document is reported **unsupported**, not skipped as an
    ambiguity, and the written state names no candidate to configure (Req
    10.2, design re-validation 2026-07-25).

    Mutation caught: narrowing the no-default arbitration branch only by
    modality (dropping the support-question filter) would see two OTHER
    -declaring candidates and resolve this as ``Ambiguous`` instead --
    landing the document in ``report.skipped`` with a "configure a default"
    reason rather than in ``report.unsupported``.
    """
    hike_only = _BroadModalityHikeOnly()
    walk_only = _BroadModalityWalkOnly()
    registry.register(hike_only)
    registry.register(walk_only)
    try:
        data_root = _build_data_root(tmp_path, {"row.fit": _rowing_fit_bytes()})
        row = _doc(data_root, "row")

        report = apply_load(data_root, session=_RecordingSession())

        rel = _rel(data_root, row)
        assert rel in _docs_of(report.unsupported)
        assert rel not in _docs_of(report.skipped)
        assert report.failures == ()
        entry = next(e for e in report.unsupported if e.doc == rel)
        assert "configure" not in entry.detail
        assert "default_calculator" not in entry.detail
    finally:
        registry.unregister(hike_only.calculator_id)
        registry.unregister(walk_only.calculator_id)


def test_two_broad_supporters_exactly_one_covering_computes_with_no_configuration(
    tmp_path: Path,
) -> None:
    """The same pair, over a Hike document: exactly one of the two (the
    Hike-only supporter) covers it, so arbitration's no-default branch
    resolves the narrowed candidate set to a single :class:`Selected` -- the
    document computes with **no** configured default at all (Req 10.2).

    Mutation caught: dropping the support-question narrowing would see both
    OTHER-declaring candidates as equally eligible and report this
    document skipped as ``Ambiguous`` instead of computed; a candidate-order
    fallback ("first one found") could instead compute it with
    ``stub-e2e-broad-walk``'s id, which its own ``compute`` refuses by
    raising.

    ``threshold-load`` ships a built-in that also supports Hike (Req 2.1), so
    the registry now genuinely holds a THIRD candidate that would make this
    scenario ambiguous. This test's subject is arbitration's narrowing among
    exactly these two stubs, not the built-in's own arbitration behavior (that
    is ``threshold-load``'s own concern), so the built-in is unregistered for
    the scope of this test and restored afterward regardless of outcome.
    """
    hike_only = _BroadModalityHikeOnly()
    walk_only = _BroadModalityWalkOnly()
    with _threshold_built_in_excluded():
        registry.register(hike_only)
        registry.register(walk_only)
        try:
            data_root = _build_data_root(tmp_path, {"hike.fit": _hike_fit_bytes()})
            hike = _doc(data_root, "hike")

            report = apply_load(data_root, session=_RecordingSession())

            rel = _rel(data_root, hike)
            assert rel in _docs_of(report.computed)
            assert report.computed[0].detail == hike_only.calculator_id
            assert report.failures == ()
            assert report.skipped == ()
            assert report.unsupported == ()
        finally:
            registry.unregister(hike_only.calculator_id)
            registry.unregister(walk_only.calculator_id)


# --- Bullet 5: the per-activity context (settings + activity date) ---------


class _ContextRecordingCalculator:
    """Echoes the :class:`LoadContext` it was handed into the result's
    ``basis`` -- and refuses (``NotComputed``) rather than substituting
    today's date when the context carries none, so this stub proves both
    halves of Req 1.12 at once: the settings projection AND the
    decline-rather-than-substitute date rule."""

    calculator_id = "stub-e2e-context"
    display_name = "Stub E2E Context Recorder"
    supported_modalities = frozenset({Modality.RUN})

    def required_athlete_fields(self) -> tuple[AthleteField, ...]:
        return ()

    def compute(
        self,
        activity: object,
        metrics: object,
        profile: object,
        session: object,
        context: LoadContext,
    ) -> LoadOutcome:
        if context.activity_date is None:
            return NotComputed(
                reason="no recorded activity date on the context; refusing "
                "to substitute today's date"
            )
        return Computed(
            result=LoadResult(
                calculator_id=self.calculator_id,
                display_name=self.display_name,
                value=1.0,
                basis=(
                    f"activity_date={context.activity_date} "
                    f"default_calculator={context.settings.default_calculator}"
                ),
                non_selected=(),
                flags=(),
                inputs_used=(),
                notes=(),
            )
        )


def test_context_echoes_configured_settings_and_the_documents_own_date(
    tmp_path: Path,
) -> None:
    """The context handed to ``compute`` carries the DATA ROOT's configured
    ``[load]`` projection (not the module default) and the document's own
    recorded date (Req 1.12, 14.5)."""
    calc = _ContextRecordingCalculator()
    registry.register(calc)
    try:
        data_root = _build_data_root(tmp_path, {"run.fit": builder.run_fit_bytes()})
        run = _doc(data_root, "run")
        block = run.read_text(encoding="utf-8").split("---\n", 2)[1]
        recorded_date = yaml.safe_load(block)["date"]
        _write_load_settings(
            data_root, f'[load]\ndefault_calculator = "{calc.calculator_id}"\n'
        )

        report = apply_load(data_root, session=_RecordingSession())

        rel = _rel(data_root, run)
        assert rel in _docs_of(report.computed)
        entry = next(e for e in report.computed if e.doc == rel)
        assert entry.detail == calc.calculator_id
        text = run.read_text(encoding="utf-8")
        assert f"activity_date={recorded_date}" in text
        assert f"default_calculator={calc.calculator_id}" in text
    finally:
        registry.unregister(calc.calculator_id)


def test_context_date_absent_for_undated_document_declines_rather_than_substitutes(
    tmp_path: Path,
) -> None:
    """An undated document binds an absent ``activity_date`` on the context --
    the calculator declines (``NotComputed``) rather than the pass
    substituting today's date (Req 1.12; steering: absent data is ``None``,
    never a fabricated default).

    Mutation caught: substituting ``date.today()`` when the frontmatter
    carries no ``date`` key would make this stub compute instead of decline,
    moving the document into ``report.computed`` instead of
    ``report.skipped``.
    """
    calc = _ContextRecordingCalculator()
    registry.register(calc)
    try:
        data_root = _build_data_root(tmp_path, {"run.fit": builder.run_fit_bytes()})
        run = _doc(data_root, "run")
        lines = run.read_text(encoding="utf-8").split("\n")
        undated = [line for line in lines if not line.startswith("date:")]
        run.write_text("\n".join(undated), encoding="utf-8")
        _write_load_settings(
            data_root, f'[load]\ndefault_calculator = "{calc.calculator_id}"\n'
        )

        report = apply_load(data_root, session=_RecordingSession())

        rel = _rel(data_root, run)
        assert rel in _docs_of(report.skipped)
        assert rel not in _docs_of(report.computed)
        skip_entry = next(e for e in report.skipped if e.doc == rel)
        assert "date" in skip_entry.detail
    finally:
        registry.unregister(calc.calculator_id)


# --- Bullet 6: unregistered configured default aborts up front -------------


def test_unregistered_configured_default_aborts_naming_value_source_and_registered(
    tmp_path: Path,
) -> None:
    """An unregistered ``[load] default_calculator`` aborts through the
    configuration-error envelope, naming the offending value, its source
    (the settings file), and the registered identifiers (Req 10.4), and
    leaves the data root's document untouched.

    This scenario's data root owns a real document, so -- like the malformed
    ``[load]`` table case below -- it proves the message-content and
    no-document-writes claims but cannot on its own discriminate an up-front
    abort from a lazy per-document one; ``test_engine.py``'s
    ``test_unregistered_configured_default_aborts_up_front_with_no_documents``
    already carries that "up front" timing claim for Req 10.4.
    """
    calc = _RunOnlyDefaultCalculator()
    registry.register(calc)
    try:
        data_root = _build_data_root(tmp_path, {"run.fit": builder.run_fit_bytes()})
        run = _doc(data_root, "run")
        before = run.read_bytes()
        settings_file = data_root / SETTINGS_FILE
        _write_load_settings(
            data_root, '[load]\ndefault_calculator = "not-a-real-calculator"\n'
        )

        with pytest.raises(UnknownCalculatorError) as exc_info:
            apply_load(data_root, session=_RecordingSession())

        body = str(exc_info.value).replace(str(settings_file), "<settings-file>")
        assert "not-a-real-calculator" in body
        assert "[load] default_calculator" in body
        assert "<settings-file>" in body
        assert calc.calculator_id in body
        assert run.read_bytes() == before
    finally:
        registry.unregister(calc.calculator_id)


# --- Bullet 7: a malformed [load] table aborts the same way -----------------


def test_malformed_load_table_error_names_the_source_with_no_document_writes(
    tmp_path: Path,
) -> None:
    """A malformed ``[load]`` table (a non-string ``default_calculator``)
    aborts through the configuration-error envelope, naming the offending
    field and the settings file as its source, and leaves every document in
    the data root byte-for-byte unchanged (Req 14.6).

    This scenario alone -- a data root that owns real documents -- cannot
    tell apart an up-front abort (before ``_discover_workout_docs`` is even
    iterated) from a *lazy* per-document abort (config resolved lazily
    inside ``_process_document``, after ``doc.read_text(...)``): both raise
    before any document is *written*, and a read that never mutates the
    document leaves the snapshot equal either way. The "before any document
    is read" half of Req 14.6 is exercised discriminatingly, instead, by
    ``test_malformed_load_table_aborts_up_front_with_no_documents`` below,
    whose data root has no documents at all for a lazy per-document check to
    raise on.
    """
    data_root = _build_data_root(
        tmp_path,
        {"run.fit": builder.run_fit_bytes(), "ride.fit": builder.ride_fit_bytes()},
    )
    _write_load_settings(data_root, "[load]\ndefault_calculator = 999\n")
    snapshot_before = _snapshot(data_root)

    with pytest.raises(LoadSettingsError) as exc_info:
        apply_load(data_root, session=_RecordingSession())

    settings_file = data_root / SETTINGS_FILE
    body = str(exc_info.value).replace(str(settings_file), "<settings-file>")
    assert "default_calculator" in body
    assert "<settings-file>" in body
    # nothing in the data root changed -- no document was written, and the
    # (already-malformed) settings file itself is untouched.
    assert _snapshot(data_root) == snapshot_before


def test_malformed_load_table_aborts_up_front_with_no_documents(
    tmp_path: Path,
) -> None:
    """The discriminating case for "the ``[load]`` table is validated before
    any document is read or written" (Req 14.6): a data root whose
    ``workouts/`` directory exists but is EMPTY, so no document ever reaches
    a compute path at all -- a *lazy* per-document resolution of
    ``load_load_settings``/``validate_configured`` (deferred until inside
    ``_process_document``, after ``doc.read_text(...)``) would have nothing
    to raise on, and the pass would complete with an all-empty
    :class:`LoadReport` instead of raising ``LoadSettingsError``.

    Mutation caught: moving the ``[load]`` table resolution and
    ``validate_configured`` call from ``apply_load``'s up-front block
    (engine.py:269-276) into ``_process_document`` (after
    ``doc.read_text(...)``) leaves this empty-``workouts/`` data root with no
    document to raise the error from -- ``pytest.raises(LoadSettingsError)``
    fails outright.
    """
    data_root = tmp_path / "data"
    data_root.mkdir()
    (data_root / WORKOUTS_DIR).mkdir()
    _write_load_settings(data_root, "[load]\ndefault_calculator = 999\n")

    with pytest.raises(LoadSettingsError):
        apply_load(data_root, session=_RecordingSession())


def test_malformed_load_table_aborts_before_any_document_is_read(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Req 14.6's literal clause: the abort happens before *any document is
    read*, not merely before the per-document loop.

    The empty-``workouts/`` test above is weaker than the requirement it
    names. ``_discover_workout_docs`` calls ``_read_frontmatter`` on every
    candidate ``workouts/*.md`` to decide which are fitdocs documents -- so
    with a data root that owns documents, moving ``apply_load``'s settings
    resolution and ``validate_configured`` to sit *after*
    ``_discover_workout_docs(data_root)`` still raises, still writes nothing,
    still leaves the byte snapshot equal, and still aborts before the loop --
    while every document has already been read. The whole suite stayed green
    under exactly that move. A plausible "skip the settings read when there are
    no documents" optimisation lands precisely there.

    So this instruments the read itself rather than an outcome, which is the
    only observable that distinguishes the two orderings.
    """
    data_root = _build_data_root(
        tmp_path,
        {"run.fit": builder.run_fit_bytes(), "ride.fit": builder.ride_fit_bytes()},
    )

    reads: list[str] = []
    # Taken from the defining module: the engine imports this under a private
    # alias (``from fitdocs.docio import read_frontmatter as _read_frontmatter``),
    # so reading it back off the engine is an implicit re-export that
    # ``mypy --strict`` rejects. Same function object. The ``setattr`` below
    # still targets the engine's own binding, which is what discovery calls.
    original = read_frontmatter

    def _recording_read_frontmatter(path: Path) -> dict[str, object] | None:
        reads.append(path.name)
        return original(path)

    monkeypatch.setattr(load_engine, "_read_frontmatter", _recording_read_frontmatter)

    # Reachability control, run first: with a WELL-FORMED table the pass reaches
    # discovery and the spy observes real reads. Without this, the zero-count
    # assertion below is satisfied just as well by a spy patched onto the wrong
    # name or a seam the engine no longer uses -- it would pass having observed
    # nothing, and go on passing after the ordering regressed.
    _write_load_settings(data_root, "[load]\n")
    apply_load(data_root, session=_RecordingSession())
    assert reads, "the spy observed no reads even on a well-formed pass"

    reads.clear()
    _write_load_settings(data_root, "[load]\ndefault_calculator = 999\n")

    with pytest.raises(LoadSettingsError):
        apply_load(data_root, session=_RecordingSession())

    assert reads == [], (
        f"the [load] table was validated only after documents had been read: {reads}"
    )


# --- Bullet 8: a scoped field + confirmation hint across two documents ------


def test_hinted_scoped_field_is_asked_once_hint_echoed_second_doc_not_reasked(
    tmp_path: Path,
) -> None:
    """``HintedCalculator`` declares one methodology-scoped field with a
    per-field confirmation hint. Registered as the sole RUN supporter over
    TWO run documents in one pass: the field is asked exactly once, its hint
    is echoed via ``inform`` before the answer is persisted, the persisted
    value lands under the calculator's OWN scoped TOML table, and the second
    document computes without re-asking (Req 2.7, 3.3, 3.6).

    Mutation caught: dropping "ask once" (Req 3.3) would try to pop a second
    ``ask_float`` answer with none queued, raising
    ``AssertionError: unexpected extra ask_float prompt`` and moving the
    second document into ``report.failures`` instead of ``report.computed``.

    ``threshold-load`` ships a built-in that also supports RUN (Req 2.1), so
    -- with no configured default -- these RUN documents would otherwise be
    genuinely ambiguous between it and ``HintedCalculator``. This test's
    subject is the ask-once/hint/persistence mechanism, not arbitration
    itself, so the built-in is unregistered for the scope of this test (to
    keep ``HintedCalculator`` the sole RUN supporter, as the docstring above
    states) and restored afterward regardless of outcome.
    """
    calc = HintedCalculator()
    with _threshold_built_in_excluded():
        registry.register(calc)
        try:
            data_root = _build_data_root(
                tmp_path,
                {
                    "run-a.fit": builder.run_fit_bytes(),
                    "run-b.fit": builder.small_sport_fit_bytes(
                        4001, "running", timestamp_offset=3600 * 5
                    ),
                },
            )
            run_docs = sorted(
                p for p in (data_root / WORKOUTS_DIR).glob("*.md") if "-run-" in p.name
            )
            assert len(run_docs) == 2  # both fixtures rendered as distinct RUN docs
            # one float answer only: the first-processed doc's field collection
            # asks once; the hint-confirmation and each doc's own
            # compute-confirmation are separate `confirm` calls (first doc:
            # hint-confirm + compute-confirm; second doc: compute-confirm only --
            # its field is already persisted).
            session = _ScriptedSession(
                floats=[42.5],
                confirms=[True, True, True],
            )

            report = apply_load(data_root, session=session)

            expected_docs = {_rel(data_root, p) for p in run_docs}
            assert expected_docs <= _docs_of(report.computed)
            assert report.failures == ()

            ask_float_prompts = [
                p for p in session.prompts if p.startswith("ask_float:")
            ]
            assert len(ask_float_prompts) == 1  # asked exactly once (Req 3.3)

            assert any(
                "noted for confirmation echo" in message for message in session.informs
            )

            profile_toml = tomllib.loads(
                (data_root / PROFILE_FILENAME).read_text(encoding="utf-8")
            )
            table_name, field_name = HINTED_FIELD.key.split(".")
            assert table_name in profile_toml
            assert profile_toml[table_name][field_name] == pytest.approx(42.5)
        finally:
            registry.unregister(calc.calculator_id)
