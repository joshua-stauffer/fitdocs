"""Integration tests for the load pass engine (task 3.3, ``LoadEngine``).

These exercise :func:`fitdocs.load.engine.apply_load` over *real* temporary data
roots built with the workout-docs pipeline (``fitdocs.sync.sync`` renders the
documents, regions, frontmatter, and archives), so the engine is proven against
the exact document shapes it must edit in production -- not hand-mocked strings.

Coverage maps onto ``requirements.md`` 1.6, 3.1, 3.3-3.5, 7.4-7.7, 8.3-8.5, 8.7,
9.1, 9.3 and the design's ``apply_load`` flow: compute, idempotency,
unsupported, non-interactive skip, restore-after-regen, recompute,
foreign-content protection, per-document failure isolation, propagating
configuration errors, and ``--calculator`` selection.

fitdocs ships no calculator (Amendment 2), so these tests drive the pass with
``ComputingCalculator`` (:mod:`tests.load.conftest`, task 1.1) -- the published-
contract stub that declares one required field (``level``, 1-10) and reaches
``Computed`` once it is present and confirmed (``points = level * 10``, zone
label ``"Zone {level}"``). Every test that needs it registered requests both
``isolated_registry`` (so no other built-in or leaked stub competes for the
RUN modality) and ``computing_calculator`` from the shared conftest. Prompts
are driven by a scripted ``InteractionSession`` (per-kind FIFO queues; a
queued ``None`` declines) or the real ``NonInteractiveSession``.
"""

from __future__ import annotations

import inspect
from collections.abc import Sequence
from datetime import date, timedelta, timezone
from pathlib import Path

import pytest
import yaml

import fitdocs.load.engine as load_engine
from fitdocs import Modality, Sport, contract
from fitdocs.athlete import AthleteFileError, load_athlete_inputs
from fitdocs.benchmarks import BenchmarkKind
from fitdocs.layout import SETTINGS_FILE, WORKOUTS_DIR
from fitdocs.load import registry
from fitdocs.load.docedit import (
    RegionState,
    classify_load_region,
    read_frontmatter_load,
    replace_load_region,
    strip_frontmatter_load,
)
from fitdocs.load.engine import DocLoadEntry, LoadReport, apply_load
from fitdocs.load.profile import (
    PROFILE_FILENAME,
    ProfileError,
    load_profile,
    save_profile,
)
from fitdocs.load.prompts import NonInteractiveSession
from fitdocs.load.registry import UnknownCalculatorError
from fitdocs.load.settings import LoadSettingsError
from fitdocs.load.types import (
    AthleteField,
    BenchmarkRef,
    Computed,
    InteractionSession,
    LoadContext,
    LoadOutcome,
    LoadResult,
    NotComputed,
)
from fitdocs.render.charts.map import TileRef
from fitdocs.settings import load_settings_document
from fitdocs.sync import sync
from tests.fixtures import builder
from tests.load.conftest import (
    COMPUTING_FIELD,
    ComputingCalculator,
    DecliningCalculator,
)
from tests.load.test_render import (
    _V1_UNSUPPORTED_LINE,
    _V1_WITHDRAWN_COMPUTED_LINE,
)

# PINNED timezone (never the system zone) so document stems are byte-stable.
_TZ = timezone(timedelta(hours=-6))


# --- scripted interaction session -------------------------------------------


class ScriptedSession:
    """An :class:`InteractionSession` double answering from per-kind FIFO queues.

    Each primitive pops the next answer from its own queue (a queued ``None``
    simulates a decline); an empty queue raises so an over-asking, mis-wired
    flow fails loudly rather than silently reading ``None``.
    """

    def __init__(
        self,
        *,
        confirms: Sequence[bool | None] = (),
        ints: Sequence[int | None] = (),
        floats: Sequence[float | None] = (),
        chooses: Sequence[int | None] = (),
    ) -> None:
        self._confirms = list(confirms)
        self._ints = list(ints)
        self._floats = list(floats)
        self._chooses = list(chooses)
        self.informs: list[str] = []
        self.confirm_defaults: list[tuple[str, bool]] = []
        """Every ``confirm`` call's ``(question, default)`` pair, in order --
        lets a test pin the ``default`` a specific question was asked with
        (Req 3.9), without disturbing the FIFO ``_pop`` semantics below."""

    @staticmethod
    def _pop(queue: list[object], kind: str) -> object:
        if not queue:
            raise AssertionError(f"ScriptedSession: no more {kind} answers queued")
        return queue.pop(0)

    def confirm(self, question: str, *, default: bool = True) -> bool | None:
        self.confirm_defaults.append((question, default))
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
        answer = self._pop(self._floats, "ask_float")  # type: ignore[arg-type]
        assert answer is None or isinstance(answer, (int, float))
        return None if answer is None else float(answer)

    def choose(
        self,
        question: str,
        options: Sequence[str],
        *,
        default_index: int | None = None,
    ) -> int | None:
        answer = self._pop(self._chooses, "choose")  # type: ignore[arg-type]
        assert answer is None or isinstance(answer, int)
        return answer

    def inform(self, message: str) -> None:
        self.informs.append(message)


_: InteractionSession = ScriptedSession()


class _RecordingSession:
    """An :class:`InteractionSession` recording every prompt it is asked (kind
    plus question text) and answering ``None`` to each -- never blocks, never
    fabricates consent. Finding 1 of the 4.1 remediation round: the
    discriminating assertion is that NO prompt was ever issued, not merely
    that the final report looks right, so this session's ``prompts`` log is
    the primary evidence a mutation reddens against.
    """

    def __init__(self) -> None:
        self.prompts: list[str] = []

    def confirm(self, question: str, *, default: bool = True) -> bool | None:
        self.prompts.append(f"confirm:{question}")
        return None

    def ask_int(
        self,
        question: str,
        *,
        minimum: int | None = None,
        maximum: int | None = None,
        default: int | None = None,
    ) -> int | None:
        self.prompts.append(f"ask_int:{question}")
        return None

    def ask_float(
        self,
        question: str,
        *,
        minimum: float | None = None,
        maximum: float | None = None,
        default: float | None = None,
    ) -> float | None:
        self.prompts.append(f"ask_float:{question}")
        return None

    def choose(
        self,
        question: str,
        options: Sequence[str],
        *,
        default_index: int | None = None,
    ) -> int | None:
        self.prompts.append(f"choose:{question}")
        return None

    def inform(self, message: str) -> None:
        pass


_PROBE_FIELD = AthleteField(
    key="probe-level",
    label="Probe level",
    kind="int",
    minimum=1,
    maximum=10,
    help_text="Finding 1 probe field: only reachable if the engine's support "
    "check is deleted or reordered after field collection.",
)


class _UnguardedProbeCalculator:
    """Declares RUN only, and -- unlike every stub in ``tests.load.conftest``
    -- does NOT re-check ``activity.modality`` inside its own ``compute``.

    Every conftest stub (``ComputingCalculator``, ``ScopedFieldCalculator``,
    ``HintedCalculator``) opens ``compute`` with a modality self-guard, so
    driving the pass with any of them can never tell apart "the engine's own
    support check ran" from "the calculator's defence-in-depth caught it
    instead" -- both look identical from the outside (report + document
    state). This stub removes that shadow: if ``compute`` is ever reached for
    a non-RUN activity, or if field collection ever runs before the engine
    decides the activity is unsupported, the only thing that could have let
    that happen is a defect in engine.py's own gate (Req 1.14, 3.1, 7.7,
    10.5).
    """

    calculator_id = "stub-unguarded-probe"
    display_name = "Stub Unguarded Probe Calculator"
    supported_modalities = frozenset({Modality.RUN})

    def required_athlete_fields(self) -> tuple[AthleteField, ...]:
        return (_PROBE_FIELD,)

    def compute(
        self,
        activity: object,
        metrics: object,
        profile: object,
        session: object,
        context: object,
    ) -> LoadOutcome:
        raise AssertionError(
            "compute() was reached for a modality this calculator never "
            "declared -- the engine's support check (Req 1.14) failed to "
            "gate it before field collection"
        )


# A full compute script for a placeholder RUN doc with an EMPTY profile:
# collect ``level`` (the stub's one required field), then confirm the result.
def _compute_run_session(*, level: int = 7, confirm: bool = True) -> ScriptedSession:
    return ScriptedSession(ints=[level], confirms=[confirm])


# When the profile ALREADY carries ``level`` (e.g. recompute after an initial
# compute), only the compute confirmation runs -- no field collection.
def _recompute_run_session(*, confirm: bool = True) -> ScriptedSession:
    return ScriptedSession(confirms=[confirm])


# --- data-root construction (real workout-docs pipeline) --------------------


class _ServingTiles:
    """The always-supplied basemap-tile source these setup syncs inject (task 6.1).

    ``tiles`` is now a required engine argument; the load engine only cares about
    the load region, so this inert source just serves deterministic PNG bytes for
    any ref (the GPS-bearing run gains a Map section it never inspects; the no-GPS
    ride plans no route). Stateless -> one shared instance is safe.
    """

    attribution = "© OpenStreetMap contributors"

    def resolve(self, refs: Sequence[TileRef]) -> dict[TileRef, bytes]:
        return {ref: b"\x89PNG\r\n\x1a\n" for ref in refs}


_TILES: _ServingTiles = _ServingTiles()


# A minimal, deterministic Hike fixture (Sport.HIKE, Modality.OTHER via
# ``fitdocs.ingest.sport.detect_sport``'s ``"hiking"`` mapping) -- the 4.1
# remediation round's finding 2 needs a real document
# :class:`~tests.load.conftest.DecliningCalculator` actually *supports* (it
# narrows only ``Sport.ROWING`` out of ``Modality.OTHER``).
# ``builder.hike_fit_bytes`` decodes and syncs through the identical real
# pipeline as run/ride.


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
    """The single workout document whose filename contains ``needle``."""
    return next(p for p in (data_root / WORKOUTS_DIR).glob("*.md") if needle in p.name)


def _rel(data_root: Path, doc: Path) -> str:
    return doc.relative_to(data_root).as_posix()


def _snapshot(data_root: Path) -> dict[str, bytes]:
    """Byte snapshot of every file under ``data_root`` (for no-write assertions)."""
    return {
        p.relative_to(data_root).as_posix(): p.read_bytes()
        for p in sorted(data_root.rglob("*"))
        if p.is_file()
    }


def _sources_last(doc: Path) -> str:
    """The document's current (last) ``sources`` archive ref."""
    block = doc.read_text(encoding="utf-8").split("---\n", 2)[1]
    parsed = yaml.safe_load(block)
    assert isinstance(parsed, dict)
    sources = parsed["sources"]
    assert isinstance(sources, list) and sources
    return str(sources[-1])


def _docs_of(entries: tuple[DocLoadEntry, ...]) -> set[str]:
    return {entry.doc for entry in entries}


# --- compute (Req 3.1-3.3, 9.1) ---------------------------------------------


def test_compute_fills_region_frontmatter_and_creates_profile(
    isolated_registry: None,
    computing_calculator: ComputingCalculator,
    tmp_path: Path,
) -> None:
    """A placeholder RUN doc + scripted session yields a computed load region,
    the three frontmatter keys, and a persisted profile with the stub's field.

    Mutation caught: if the engine skipped field collection, forgot to write the
    frontmatter keys, or mis-scored the result, the assertions below break."""
    data_root = _build_data_root(tmp_path, {"run.fit": builder.run_fit_bytes()})
    run = _doc(data_root, "run")

    report = apply_load(data_root, session=_compute_run_session(level=7))

    assert isinstance(report, LoadReport)
    # the run doc is reported computed by the stub-computing calculator
    assert _docs_of(report.computed) == {_rel(data_root, run)}
    assert report.computed[0].detail == computing_calculator.calculator_id
    assert report.restored == () and report.skipped == () and report.failures == ()

    # the load region now classifies as COMPUTED (payload present)
    text = run.read_text(encoding="utf-8")
    classification = classify_load_region(text)
    state, payload = classification.state, classification.payload
    assert state is RegionState.COMPUTED
    assert payload is not None and payload.result is not None
    assert payload.result.value == 70.0  # level 7 * 10

    # the three managed frontmatter keys are present and correct
    fm = read_frontmatter_load(text)
    assert fm["load_value"] == 70
    assert fm["load_methodology"] == computing_calculator.calculator_id

    # athlete.toml was created with the answered input, round-tripping through
    # the profile store's own reader.
    assert (data_root / PROFILE_FILENAME).is_file()
    profile = load_profile(data_root)
    assert profile.get_number(COMPUTING_FIELD.key) == 7


# --- idempotency (design: a repeated identical pass performs no writes) ------


def test_second_identical_pass_writes_nothing(
    isolated_registry: None,
    computing_calculator: ComputingCalculator,
    tmp_path: Path,
) -> None:
    """After a compute, a second pass (fresh session) changes no bytes and reports
    an empty computed/restored -- restore finds no drift on a stable computed doc.

    Mutation caught: if restore always rewrote the frontmatter or compute
    re-ran, the byte snapshot would differ and ``computed``/``restored`` fill."""
    data_root = _build_data_root(tmp_path, {"run.fit": builder.run_fit_bytes()})
    apply_load(data_root, session=_compute_run_session())
    before = _snapshot(data_root)

    report = apply_load(data_root, session=NonInteractiveSession())

    assert _snapshot(data_root) == before  # not one byte changed
    assert report.computed == ()
    assert report.restored == ()


def test_first_pass_actually_computed_before_the_second_writes_nothing(
    isolated_registry: None,
    computing_calculator: ComputingCalculator,
    tmp_path: Path,
) -> None:
    """The *first* pass must itself have computed the run -- otherwise a second
    pass writing nothing is trivially true of a classifier that never computes
    anything at all (task 4.1 remediation: HEAD's counterpart asserted only the
    second pass, and survives total classifier sabotage).

    Mutation caught: stubbing ``classify_load_region`` to always report
    ``FOREIGN`` (so nothing is ever computed and nothing ever restored) leaves
    the *second*-pass assertions in ``test_second_identical_pass_writes_nothing``
    green, because an all-``skipped`` pass also writes nothing on repeat -- but
    reddens this one, since the first pass never reaches ``report.computed``.
    """
    data_root = _build_data_root(tmp_path, {"run.fit": builder.run_fit_bytes()})
    run = _doc(data_root, "run")

    first = apply_load(data_root, session=_compute_run_session(level=7))

    assert _docs_of(first.computed) == {_rel(data_root, run)}
    assert classify_load_region(run.read_text(encoding="utf-8")).state is (
        RegionState.COMPUTED
    )


# --- unsupported state (Req 7.7) --------------------------------------------


def test_ride_gets_honest_unsupported_state_even_non_interactive(
    isolated_registry: None,
    computing_calculator: ComputingCalculator,
    tmp_path: Path,
) -> None:
    """A RIDE doc's load region gets the honest unsupported state (no numbers),
    written without any prompt -- so it works under ``NonInteractiveSession``.
    ``computing_calculator`` is registered but declares RUN only, so it never
    even reaches field collection for this activity.

    Mutation caught: if the engine prompted for a sport no calculator supports,
    the non-interactive session would leave it a placeholder instead."""
    data_root = _build_data_root(tmp_path, {"ride.fit": builder.ride_fit_bytes()})
    ride = _doc(data_root, "ride")

    report = apply_load(data_root, session=NonInteractiveSession())

    assert _docs_of(report.unsupported) == {_rel(data_root, ride)}
    text = ride.read_text(encoding="utf-8")
    classification = classify_load_region(text)
    state, payload = classification.state, classification.payload
    assert state is RegionState.UNSUPPORTED
    assert payload is not None and payload.sport == "Ride"
    # honest absence: no load frontmatter keys were written
    assert read_frontmatter_load(text) == {}


# --- non-interactive skip (Req 3.5, 9.1) ------------------------------------


def test_non_interactive_skips_run_but_still_marks_ride_unsupported(
    isolated_registry: None,
    computing_calculator: ComputingCalculator,
    tmp_path: Path,
) -> None:
    """Non-interactively, a placeholder RUN doc is skipped with a reason and left
    byte-identical, while a RIDE doc in the same pass still receives its
    unsupported state -- the two honest outcomes coexist (Req 3.5, 7.7).

    Mutation caught: if a non-interactive run were computed (fabricated inputs)
    the run doc would change; if the pass aborted on the run's skip, the ride
    would never be marked."""
    data_root = _build_data_root(
        tmp_path,
        {"run.fit": builder.run_fit_bytes(), "ride.fit": builder.ride_fit_bytes()},
    )
    run = _doc(data_root, "run")
    ride = _doc(data_root, "ride")
    run_before = run.read_bytes()

    report = apply_load(data_root, session=NonInteractiveSession())

    assert _rel(data_root, run) in _docs_of(report.skipped)
    assert run.read_bytes() == run_before  # skipped doc untouched
    assert _rel(data_root, ride) in _docs_of(report.unsupported)
    assert classify_load_region(ride.read_text(encoding="utf-8")).state is (
        RegionState.UNSUPPORTED
    )
    # nothing was answered, so no profile file was created
    assert not (data_root / PROFILE_FILENAME).exists()


# --- restore after regen (Req 7.4) ------------------------------------------


def test_restore_readds_frontmatter_without_prompting(
    isolated_registry: None,
    computing_calculator: ComputingCalculator,
    tmp_path: Path,
) -> None:
    """A COMPUTED doc whose load frontmatter keys were reset (a regen) has them
    restored from the preserved payload -- without recomputation or prompting --
    and the load region is left byte-identical (Req 7.4).

    Mutation caught: if restore recomputed, a NonInteractiveSession would leave
    the keys absent; if it rewrote the region, the region bytes would differ."""
    data_root = _build_data_root(tmp_path, {"run.fit": builder.run_fit_bytes()})
    run = _doc(data_root, "run")
    apply_load(data_root, session=_compute_run_session(level=7))

    # Simulate a regen: strip the managed frontmatter keys, keep the region.
    computed_text = run.read_text(encoding="utf-8")
    region_before = classify_load_region(computed_text).payload
    run.write_text(strip_frontmatter_load(computed_text), encoding="utf-8")
    assert read_frontmatter_load(run.read_text(encoding="utf-8")) == {}

    report = apply_load(data_root, session=NonInteractiveSession())

    assert _docs_of(report.restored) == {_rel(data_root, run)}
    assert report.computed == ()
    restored_text = run.read_text(encoding="utf-8")
    fm = read_frontmatter_load(restored_text)
    assert fm["load_value"] == 70
    # the preserved region content is unchanged by a restore
    assert classify_load_region(restored_text).payload == region_before


# --- recompute (Req 8.3) ----------------------------------------------------


def test_recompute_replaces_result_with_fresh_confirmation(
    isolated_registry: None,
    computing_calculator: ComputingCalculator,
    tmp_path: Path,
) -> None:
    """``recompute=True`` re-confirms from scratch and replaces a COMPUTED result
    with a fresh one derived from the profile at recompute time (Req 8.3).

    Mutation caught: if recompute honored the no-overwrite rule, the result
    would stay level 3 / 30 instead of the newly confirmed level 5 / 50; if
    recompute skipped re-confirmation, ``_recompute_run_session`` (which queues
    exactly one confirm answer) would raise on the missing answer."""
    data_root = _build_data_root(tmp_path, {"run.fit": builder.run_fit_bytes()})
    run = _doc(data_root, "run")
    apply_load(data_root, session=_compute_run_session(level=3))
    assert read_frontmatter_load(run.read_text(encoding="utf-8"))["load_value"] == 30

    # Simulate the athlete's stub level rising between passes -- ``level`` is
    # already present in the profile, so recompute only re-runs the confirm
    # dialog, never field collection, and picks up the new persisted value.
    profile = load_profile(data_root)
    save_profile(data_root, profile.with_value(COMPUTING_FIELD, 5))

    report = apply_load(data_root, session=_recompute_run_session(), recompute=True)

    assert _docs_of(report.computed) == {_rel(data_root, run)}
    fm = read_frontmatter_load(run.read_text(encoding="utf-8"))
    assert fm["load_value"] == 50  # level 5 * 10


# --- foreign-content protection (Req 7.6) -----------------------------------


def test_foreign_region_untouched_without_recompute_then_overwritten(
    isolated_registry: None,
    computing_calculator: ComputingCalculator,
    tmp_path: Path,
) -> None:
    """Hand-edited (foreign) load-region content is left byte-identical and
    reported skipped without recompute; ``recompute=True`` overwrites it (7.6).

    Mutation caught: if the engine failed to recognize foreign content it would
    clobber the user's edit on an ordinary pass."""
    data_root = _build_data_root(tmp_path, {"run.fit": builder.run_fit_bytes()})
    run = _doc(data_root, "run")
    foreign = replace_load_region(
        run.read_text(encoding="utf-8"), "My own hand-written training notes."
    )
    run.write_text(foreign, encoding="utf-8")
    assert classify_load_region(foreign).state is RegionState.FOREIGN

    # Without recompute: untouched, reported skipped.
    report = apply_load(data_root, session=NonInteractiveSession())
    assert _rel(data_root, run) in _docs_of(report.skipped)
    assert run.read_text(encoding="utf-8") == foreign

    # With recompute: the foreign content is overwritten by a fresh compute.
    report2 = apply_load(data_root, session=_compute_run_session(), recompute=True)
    assert _docs_of(report2.computed) == {_rel(data_root, run)}
    assert classify_load_region(run.read_text(encoding="utf-8")).state is (
        RegionState.COMPUTED
    )


# --- prior-format (SUPERSEDED) protection (Req 11.2, 11.3, 13.4) ------------


def test_superseded_computed_result_is_skipped_byte_identical_not_erased(
    isolated_registry: None,
    computing_calculator: ComputingCalculator,
    tmp_path: Path,
) -> None:
    """A recorded prior-format ``computed`` result is a result to protect: an
    ordinary pass without ``--recompute`` must leave the document byte-identical
    and report it skipped -- never fall into the compute path and overwrite the
    recorded result with a fresh ``unsupported`` payload (Req 11.2, 11.3, 13.4).

    This is the task 2.3 remediation's data-loss regression test: at HEAD (before
    ``SUPERSEDED`` existed as a reachable state) the equivalent foreign-shaped
    content classified ``FOREIGN`` and hit this same protective branch. Making
    ``SUPERSEDED`` reachable without extending the branch's guard re-routed it
    into the compute path instead, where ``_write_unsupported`` silently erased
    the recorded v1 result.

    Mutation caught: removing the ``RegionState.SUPERSEDED`` arm from the guard
    at ``engine.py``'s skip branch reddens this test -- the document's bytes
    change and the entry moves from ``report.skipped`` to ``report.unsupported``.
    """
    data_root = _build_data_root(tmp_path, {"run.fit": builder.run_fit_bytes()})
    run = _doc(data_root, "run")
    superseded = replace_load_region(
        run.read_text(encoding="utf-8"), _V1_WITHDRAWN_COMPUTED_LINE
    )
    run.write_text(superseded, encoding="utf-8")
    assert classify_load_region(superseded).state is RegionState.SUPERSEDED
    before = run.read_bytes()

    # A session that *can* answer/confirm a fresh compute -- so that if the
    # guard were missing, the compute path would actually succeed and clobber
    # the document, rather than being masked by a coincidental non-interactive
    # skip. This is what makes the mutation below observable.
    report = apply_load(data_root, session=_compute_run_session())

    assert run.read_bytes() == before  # not one byte changed -- the v1 result survives
    rel = _rel(data_root, run)
    # Req 11.2 residue (task 4.1): the document lands in *none* of computed,
    # restored, or unsupported -- not only "not unsupported/computed". A
    # mutation appending a stamp-derived entry to ``buckets.restored`` while
    # writing no bytes would satisfy every assertion above but is caught here.
    assert rel in _docs_of(report.skipped)
    assert rel not in _docs_of(report.unsupported)
    assert rel not in _docs_of(report.computed)
    assert rel not in _docs_of(report.restored)
    # The skip reason names the recorded format version and the stamp's
    # methodology -- and the stamp's calculator_id reaches only this field.
    skip_entry = next(entry for entry in report.skipped if entry.doc == rel)
    assert "format version 1" in skip_entry.detail  # exact token, not bare digit
    assert "withdrawn-v1" in skip_entry.detail  # calculator_id, message-only
    for entry in report.computed + report.restored + report.unsupported:
        assert entry.doc != rel
        assert "withdrawn-v1" not in entry.detail


def test_recompute_over_superseded_region_replaces_it_with_current_format(
    isolated_registry: None,
    computing_calculator: ComputingCalculator,
    tmp_path: Path,
) -> None:
    """``--recompute`` over a document carrying a prior-format (v1, from the
    withdrawn calculator) result must NOT be treated as a result to protect:
    it recomputes from the archived source and replaces the section with a
    result in the current format (Req 11.4), applying the ordinary arbitration
    and unsupported-state rules exactly as it would for a placeholder document
    (Req 13.5).

    4.1 remediation round finding: every existing ``recompute=True`` test
    (``test_recompute_replaces_result_with_fresh_confirmation``,
    ``test_foreign_region_untouched_without_recompute_then_overwritten``, and
    the two e2e recompute tests) drives a COMPUTED or FOREIGN region -- none
    drives a SUPERSEDED one, so the guard's ``not recompute`` half was never
    proven live.

    Mutation caught: changing the guard at ``engine.py:374`` from
    ``if not recompute and state is RegionState.SUPERSEDED:`` to
    ``if state is RegionState.SUPERSEDED:`` leaves the full suite green
    (the ``not recompute`` path stays untested) -- under that mutation this
    document is skipped byte-identical even with ``--recompute``, never
    reaching the compute path at all."""
    data_root = _build_data_root(tmp_path, {"run.fit": builder.run_fit_bytes()})
    run = _doc(data_root, "run")
    superseded = replace_load_region(
        run.read_text(encoding="utf-8"), _V1_WITHDRAWN_COMPUTED_LINE
    )
    run.write_text(superseded, encoding="utf-8")
    assert classify_load_region(superseded).state is RegionState.SUPERSEDED

    report = apply_load(data_root, session=_compute_run_session(), recompute=True)

    rel = _rel(data_root, run)
    assert rel in _docs_of(report.computed)
    assert rel not in _docs_of(report.skipped)
    assert rel not in _docs_of(report.unsupported)
    assert rel not in _docs_of(report.restored)

    after = run.read_text(encoding="utf-8")
    assert classify_load_region(after).state is RegionState.COMPUTED
    assert "withdrawn-v1" not in after


def test_superseded_unsupported_stamp_still_refills_and_is_then_byte_stable(
    isolated_registry: None,
    computing_calculator: ComputingCalculator,
    tmp_path: Path,
) -> None:
    """The mirror case: a recorded prior-format ``unsupported`` stamp records no
    result to protect (Req 7.7), so it must still rejoin the compute path and be
    refilled -- distinguishing it end to end from the ``computed`` row above,
    which the Finding-1 guard must not have collaterally protected.

    One refill write on the first pass (fresh, current-format ``unsupported``
    content), then byte-stable from the second pass onward (Req 8.3's repeated-
    identical-pass guarantee).
    """
    data_root = _build_data_root(tmp_path, {"ride.fit": builder.ride_fit_bytes()})
    ride = _doc(data_root, "ride")
    superseded_unsupported = replace_load_region(
        ride.read_text(encoding="utf-8"), _V1_UNSUPPORTED_LINE
    )
    ride.write_text(superseded_unsupported, encoding="utf-8")
    assert classify_load_region(superseded_unsupported).state is RegionState.UNSUPPORTED

    report = apply_load(data_root, session=NonInteractiveSession())

    assert _rel(data_root, ride) in _docs_of(report.unsupported)
    assert ride.read_bytes() != superseded_unsupported.encode("utf-8")
    assert classify_load_region(ride.read_text(encoding="utf-8")).state is (
        RegionState.UNSUPPORTED
    )
    refilled = ride.read_bytes()

    report2 = apply_load(data_root, session=NonInteractiveSession())

    assert ride.read_bytes() == refilled  # byte-stable from the second pass onward
    assert _rel(data_root, ride) not in _docs_of(report2.unsupported)
    assert _rel(data_root, ride) not in _docs_of(report2.skipped)


# --- failure isolation (Req 8.5, 9.3) ---------------------------------------


def test_missing_archive_is_a_failure_and_pass_continues(
    isolated_registry: None,
    computing_calculator: ComputingCalculator,
    tmp_path: Path,
) -> None:
    """A doc whose archived source is missing becomes a failure entry (doc left
    byte-identical), and OTHER documents in the same pass are still processed --
    the pass never aborts (Req 8.5, 9.3).

    Mutation caught: if the missing archive raised out of the pass, the ride
    would never be marked unsupported and no failure would be recorded."""
    data_root = _build_data_root(
        tmp_path,
        {"run.fit": builder.run_fit_bytes(), "ride.fit": builder.ride_fit_bytes()},
    )
    run = _doc(data_root, "run")
    ride = _doc(data_root, "ride")
    run_before = run.read_bytes()
    # Delete the run's archived source so its load pass cannot resolve it.
    archive = data_root.joinpath(*_sources_last(run).split("/"))
    archive.unlink()

    report = apply_load(data_root, session=NonInteractiveSession())

    assert _rel(data_root, run) in _docs_of(report.failures)
    assert run.read_bytes() == run_before  # a failure never mutates its doc
    # the pass kept going: the ride still received its unsupported state
    assert _rel(data_root, ride) in _docs_of(report.unsupported)


# --- configuration errors (propagate, not per-doc failures) -----------------


def test_malformed_athlete_toml_propagates_as_config_error(tmp_path: Path) -> None:
    """A malformed ``athlete.toml`` aborts the pass with ``AthleteFileError`` --
    it is a configuration error, never swallowed as a per-document failure.

    Mutation caught: if the engine caught config errors per-doc, this would
    return a report with a failure entry instead of raising."""
    data_root = _build_data_root(tmp_path, {"run.fit": builder.run_fit_bytes()})
    (data_root / PROFILE_FILENAME).write_text("not = = valid toml", encoding="utf-8")

    with pytest.raises(AthleteFileError):
        apply_load(data_root, session=NonInteractiveSession())


def test_unknown_calculator_id_propagates(tmp_path: Path) -> None:
    """An unknown ``--calculator`` id aborts with ``UnknownCalculatorError``."""
    data_root = _build_data_root(tmp_path, {"run.fit": builder.run_fit_bytes()})

    with pytest.raises(UnknownCalculatorError):
        apply_load(data_root, session=NonInteractiveSession(), calculator_id="nope")


def test_invalid_profile_value_propagates_as_config_error(
    isolated_registry: None,
    computing_calculator: ComputingCalculator,
    tmp_path: Path,
) -> None:
    """A profile value that is present but non-numeric at an accessed key raises
    ``ProfileError`` out of the pass (config error, not a per-doc failure)."""
    data_root = _build_data_root(tmp_path, {"run.fit": builder.run_fit_bytes()})
    # A non-numeric value for the stub's required field is read via get_number
    # inside compute() -> raises. Hand-write a profile the calculator will
    # choke on at get_number time.
    (data_root / PROFILE_FILENAME).write_text(
        f'{COMPUTING_FIELD.key} = "not-a-number"\n', encoding="utf-8"
    )

    with pytest.raises(ProfileError):
        apply_load(data_root, session=NonInteractiveSession())


# --- --calculator selection (Req 8.4) ---------------------------------------


def test_forced_calculator_computes_a_run(
    isolated_registry: None,
    computing_calculator: ComputingCalculator,
    tmp_path: Path,
) -> None:
    """Forcing ``calculator_id`` uses only that calculator and computes a run."""
    data_root = _build_data_root(tmp_path, {"run.fit": builder.run_fit_bytes()})
    run = _doc(data_root, "run")

    report = apply_load(
        data_root,
        session=_compute_run_session(),
        calculator_id=computing_calculator.calculator_id,
    )

    assert _docs_of(report.computed) == {_rel(data_root, run)}
    assert report.computed[0].detail == computing_calculator.calculator_id


def test_forced_calculator_on_ride_yields_unsupported(
    isolated_registry: None,
    computing_calculator: ComputingCalculator,
    tmp_path: Path,
) -> None:
    """Forcing a running-only calculator on a RIDE yields the unsupported state --
    a forced calculator still declines a sport it does not support (Req 1.3, 8.4).

    Mutation caught: if a forced ``--calculator`` bypassed the modality filter,
    the ride would be prompted for (and skipped) rather than marked unsupported."""
    data_root = _build_data_root(tmp_path, {"ride.fit": builder.ride_fit_bytes()})
    ride = _doc(data_root, "ride")

    report = apply_load(
        data_root,
        session=NonInteractiveSession(),
        calculator_id=computing_calculator.calculator_id,
    )

    assert _docs_of(report.unsupported) == {_rel(data_root, ride)}
    assert classify_load_region(ride.read_text(encoding="utf-8")).state is (
        RegionState.UNSUPPORTED
    )


def test_support_check_gates_field_collection_before_declaring_unsupported(
    isolated_registry: None,
    tmp_path: Path,
) -> None:
    """The engine's own support check between arbitration and field collection
    (engine.py:488-490, Req 1.14, 3.1, 7.7, 10.5) -- not any calculator's own
    defence-in-depth -- is what keeps an unsupported document out of the
    prompt flow, and it runs BEFORE ``collect_missing_fields``, never after.

    Uses ``_UnguardedProbeCalculator``, registered as the configured
    ``[load] default_calculator`` and forced via ``calculator_id`` too so
    arbitration's forced branch selects it (sport-blind, per Req 10.5)
    regardless of coverage: unlike every stub in ``tests.load.conftest``, it
    does not re-check ``activity.modality`` inside ``compute``, so nothing
    else in this test stands between a RIDE document and a prompt for its one
    required field, ``probe-level``.

    Mutation caught: deleting the support check at engine.py:488-490, or
    moving it to run after ``collect_missing_fields`` (492-502), both let this
    RIDE document reach field collection -- ``session.prompts`` records an
    ``ask_int:...probe-level...`` entry and this test fails under either
    mutation. Verified by hand against both mutations (see the round-1
    remediation status report's EVIDENCE section)."""
    calc = _UnguardedProbeCalculator()
    registry.register(calc)
    try:
        data_root = _build_data_root(tmp_path, {"ride.fit": builder.ride_fit_bytes()})
        ride = _doc(data_root, "ride")
        session = _RecordingSession()

        report = apply_load(
            data_root, session=session, calculator_id=calc.calculator_id
        )

        rel = _rel(data_root, ride)
        assert session.prompts == []  # (a) no prompt was ever issued
        assert rel in _docs_of(report.unsupported)  # (b) honest unsupported state
        assert rel not in _docs_of(report.skipped)  # (c) never a MissingInputs skip
    finally:
        registry.unregister(calc.calculator_id)


def test_calculator_declining_at_compute_reaches_unsupported_not_skipped(
    isolated_registry: None,
    declining_calculator: DecliningCalculator,
    tmp_path: Path,
) -> None:
    """An arbitrated calculator that answers ``supports`` truthfully can still
    decline the specific activity from its own ``compute`` (Req 1.3, 10.5) --
    that outcome must reach ``report.unsupported`` with the honest unsupported
    region written, never be silently rerouted into ``report.skipped``
    (engine.py:522-528).

    Drives a Hike document (``Modality.OTHER``, and specifically NOT the one
    sport ``DecliningCalculator.supports`` narrows out -- ``Sport.ROWING``),
    forced so arbitration's sport-blind forced branch selects it. The support
    check then passes (Hike is not Rowing), so ``compute`` is actually called
    -- and it unconditionally declines every sport, landing here via the
    ``Unsupported()`` branch rather than the earlier support-check branch.

    Mutation caught: replacing ``_write_unsupported(...)`` at engine.py:
    522-528 with ``buckets.skipped.append(...)`` reroutes this document into
    ``report.skipped`` instead of ``report.unsupported`` -- this test fails
    under that mutation."""
    data_root = _build_data_root(tmp_path, {"hike.fit": builder.hike_fit_bytes()})
    hike = _doc(data_root, "hike")

    report = apply_load(
        data_root,
        session=NonInteractiveSession(),
        calculator_id=declining_calculator.calculator_id,
    )

    rel = _rel(data_root, hike)
    assert rel in _docs_of(report.unsupported)
    assert rel not in _docs_of(report.skipped)
    assert classify_load_region(hike.read_text(encoding="utf-8")).state is (
        RegionState.UNSUPPORTED
    )


# --- arbitration replaces the candidate loop (Req 1.6, 10.1-10.4) -----------


class _AltRunCalculator:
    """A second RUN-supporting calculator local to this module -- so an
    ambiguity (two supporters, no configured default) is reachable through the
    real pass without a shipped calculator (Req 10.2)."""

    calculator_id = "stub-alt-run"
    display_name = "Stub Alt Run Calculator"
    supported_modalities = frozenset({Modality.RUN})

    def required_athlete_fields(self) -> tuple[AthleteField, ...]:
        return ()

    def compute(
        self,
        activity: object,
        metrics: object,
        profile: object,
        session: object,
        context: object,
    ) -> LoadOutcome:
        raise AssertionError("stub-alt-run must never be invoked by these tests")


class _NonCoveringForcedCalculator:
    """Declares ``Modality.OTHER`` only -- so :func:`~fitdocs.load.types.
    supports_activity` answers ``False`` for a RUN activity -- yet is reachable
    as an arbitration :class:`~fitdocs.load.arbitrate.Selected` for one anyway
    by forcing its id (mirrors how a stale ``--calculator``/configured default
    reaches the engine's own support check un-narrowed by sport, per Req
    10.5's module docstring). Its own ``compute`` also raises, so even a
    defect that let arbitration itself narrow a forced id by sport would
    still be caught here rather than masked by a coincidental Computed."""

    calculator_id = "stub-non-covering-forced"
    display_name = "Stub Non-Covering Forced Calculator"
    supported_modalities = frozenset({Modality.OTHER})

    def required_athlete_fields(self) -> tuple[AthleteField, ...]:
        return ()

    def compute(
        self,
        activity: object,
        metrics: object,
        profile: object,
        session: object,
        context: object,
    ) -> LoadOutcome:
        raise AssertionError(
            "stub-non-covering-forced must never be invoked -- it fails "
            "supports_activity and must reach _write_unsupported, not compute"
        )


def _write_load_settings(data_root: Path, toml_text: str) -> None:
    (data_root / SETTINGS_FILE).write_text(toml_text, encoding="utf-8")


def test_two_supporters_with_no_default_are_skipped_ambiguous(
    isolated_registry: None,
    computing_calculator: ComputingCalculator,
    tmp_path: Path,
) -> None:
    """Two registered calculators support the same modality and no default is
    configured: the document is skipped -- never computed by whichever
    registered first -- with a reason naming both candidates and directing the
    user to configure a default (Req 10.1, 10.2).

    Mutation caught: a candidate loop that fell back to "first supporter wins"
    would compute the document with one of the two ids instead of skipping it.
    """
    alt = _AltRunCalculator()
    registry.register(alt)
    try:
        data_root = _build_data_root(tmp_path, {"run.fit": builder.run_fit_bytes()})
        run = _doc(data_root, "run")
        before = run.read_bytes()

        report = apply_load(data_root, session=NonInteractiveSession())

        rel = _rel(data_root, run)
        assert rel in _docs_of(report.skipped)
        assert rel not in _docs_of(report.computed)
        assert rel not in _docs_of(report.unsupported)
        skip_entry = next(entry for entry in report.skipped if entry.doc == rel)
        assert computing_calculator.calculator_id in skip_entry.detail
        assert alt.calculator_id in skip_entry.detail
        assert "default_calculator" in skip_entry.detail
        assert run.read_bytes() == before
    finally:
        registry.unregister(alt.calculator_id)


def test_configured_default_settles_an_otherwise_ambiguous_choice(
    isolated_registry: None,
    computing_calculator: ComputingCalculator,
    tmp_path: Path,
) -> None:
    """A ``[load] default_calculator`` configured in ``fitdocs.toml`` resolves
    what would otherwise be an ambiguity between two supporters, and the pass
    reads that table itself -- no ``default_calculator`` parameter exists on
    ``apply_load`` (Amendment 3, Req 14.4)."""
    alt = _AltRunCalculator()
    registry.register(alt)
    try:
        data_root = _build_data_root(tmp_path, {"run.fit": builder.run_fit_bytes()})
        run = _doc(data_root, "run")
        _write_load_settings(
            data_root,
            f'[load]\ndefault_calculator = "{computing_calculator.calculator_id}"\n',
        )

        report = apply_load(data_root, session=_compute_run_session(level=4))

        assert _docs_of(report.computed) == {_rel(data_root, run)}
        assert report.computed[0].detail == computing_calculator.calculator_id
    finally:
        registry.unregister(alt.calculator_id)


def test_forced_calculator_that_does_not_support_activity_is_never_substituted(
    isolated_registry: None,
    tmp_path: Path,
) -> None:
    """The engine's support check (engine.py:488-490) must never fall back to
    a different registered calculator that WOULD have supported the activity
    -- it must write the honest unsupported state for the arbitrated
    (forced) calculator itself (Req 10.5): "the CLI shall not silently
    substitute a different calculator that would have supported it."

    Two calculators are registered: ``stub-non-covering-forced`` (declares
    ``Modality.OTHER``, so it fails ``supports_activity`` for a RUN activity)
    is forced via ``--calculator``, and ``stub-alt-run`` (declares
    ``Modality.RUN``, so it WOULD support the same activity) sits registered
    alongside it, unused, with a ``compute`` that raises if ever invoked.

    Mutation caught: replacing the guard at engine.py:488-490 with a fallback
    that searches the registry for another supporter and calls its `compute`
    instead of `_write_unsupported` leaves the full suite green -- every
    existing two-calculator test registers two calculators that BOTH support
    the activity, so the substitutable state (one forced supporter that
    fails, one silent alternative that would succeed) is never reached. Under
    that mutation this test either computes the document with
    ``stub-alt-run``'s id (instead of landing in ``report.unsupported``) or
    raises the alternate's ``AssertionError`` when its ``compute`` is
    (wrongly) invoked."""
    non_covering = _NonCoveringForcedCalculator()
    covering = _AltRunCalculator()
    registry.register(non_covering)
    registry.register(covering)
    try:
        data_root = _build_data_root(tmp_path, {"run.fit": builder.run_fit_bytes()})
        run = _doc(data_root, "run")
        before = run.read_bytes()

        report = apply_load(
            data_root,
            session=NonInteractiveSession(),
            calculator_id=non_covering.calculator_id,
        )

        rel = _rel(data_root, run)
        assert rel in _docs_of(report.unsupported)
        assert report.computed == ()
        assert rel not in _docs_of(report.computed)
        assert run.read_bytes() != before
        assert classify_load_region(run.read_text(encoding="utf-8")).state is (
            RegionState.UNSUPPORTED
        )
    finally:
        registry.unregister(non_covering.calculator_id)
        registry.unregister(covering.calculator_id)


def test_unregistered_configured_default_aborts_before_any_write(
    isolated_registry: None,
    computing_calculator: ComputingCalculator,
    tmp_path: Path,
) -> None:
    """An unregistered ``[load] default_calculator`` aborts with
    ``UnknownCalculatorError`` before any document is read or written (Req 10.4).
    """
    data_root = _build_data_root(tmp_path, {"run.fit": builder.run_fit_bytes()})
    run = _doc(data_root, "run")
    before = run.read_bytes()
    _write_load_settings(data_root, '[load]\ndefault_calculator = "does-not-exist"\n')

    with pytest.raises(UnknownCalculatorError):
        apply_load(data_root, session=NonInteractiveSession())

    assert run.read_bytes() == before


def test_unregistered_configured_default_aborts_up_front_with_no_documents(
    tmp_path: Path,
) -> None:
    """The discriminating case for "validated up front, before the document
    scan" (Req 10.4, design.md ~660): a data root with an EMPTY ``workouts/``
    (no document ever reaches the compute path, where ``arbitrate``'s
    forced/configured branches would also raise the same
    ``UnknownCalculatorError`` -- just lazily, at the first such document).

    Mutation caught: deleting the ``validate_configured(...)`` call at
    engine.py:272-276 leaves nothing to raise here -- ``_discover_workout_docs``
    finds no documents, the per-document loop body never runs, and the pass
    would return an all-empty ``LoadReport`` instead of raising. Neither
    ``test_unknown_calculator_id_propagates`` nor
    ``test_unregistered_configured_default_aborts_before_any_write`` (both
    drive a data root with a real RUN document, so a lazy per-document check
    would ALSO raise there) can tell the two validation timings apart -- this
    one can, because it removes the compute path's own chance to raise the
    same error."""
    data_root = tmp_path / "data"
    data_root.mkdir()
    _write_load_settings(data_root, '[load]\ndefault_calculator = "does-not-exist"\n')

    with pytest.raises(UnknownCalculatorError):
        apply_load(data_root, session=NonInteractiveSession())


def test_malformed_load_table_aborts_before_any_write(
    isolated_registry: None,
    computing_calculator: ComputingCalculator,
    tmp_path: Path,
) -> None:
    """A malformed ``[load]`` table (Req 14.6) aborts through the configuration-
    error envelope before any document is read or written."""
    data_root = _build_data_root(tmp_path, {"run.fit": builder.run_fit_bytes()})
    run = _doc(data_root, "run")
    before = run.read_bytes()
    _write_load_settings(data_root, "[load]\ndefault_calculator = 123\n")

    with pytest.raises(LoadSettingsError):
        apply_load(data_root, session=NonInteractiveSession())

    assert run.read_bytes() == before


def test_malformed_load_table_aborts_up_front_with_no_documents(
    tmp_path: Path,
) -> None:
    """The discriminating case for "the ``[load]`` table is validated before
    any document is read" (Req 14.6): a data root with an EMPTY ``workouts/``
    (no document ever reaches the compute path, where a lazy per-document
    fallback to :data:`~fitdocs.load.settings.DEFAULT_LOAD_SETTINGS` would
    otherwise re-raise the same ``LoadSettingsError`` -- just lazily, at the
    first such document).

    Mirrors ``test_unregistered_configured_default_aborts_up_front_with_no_documents``
    (engine.py:272-276), which solved the identical problem for Req 10.4 by
    removing the compute path's own chance to raise.

    Mutation caught: catching ``LoadSettingsError`` at engine.py:269-271,
    falling back to ``DEFAULT_LOAD_SETTINGS``, and re-raising it only inside
    the per-document loop leaves nothing to raise here -- the pass would
    complete with an all-empty ``LoadReport`` instead of raising.
    ``test_malformed_load_table_aborts_before_any_write`` (which drives a data
    root with a real RUN document) cannot tell the two abort timings apart,
    because a lazy per-document check would ALSO raise there; this one can."""
    data_root = tmp_path / "data"
    data_root.mkdir()
    (data_root / WORKOUTS_DIR).mkdir()
    _write_load_settings(data_root, "[load]\ndefault_calculator = 123\n")

    with pytest.raises(LoadSettingsError):
        apply_load(data_root, session=NonInteractiveSession())


# --- the [load] table is read exactly once per invocation (Req 14.4) --------


def test_load_settings_document_is_read_exactly_once_per_invocation(
    tmp_path: Path,
) -> None:
    """The ``[load]`` table is read *exactly once* for the whole pass (Amendment
    3, Req 14.4, engine.py:267-271) -- never once per document. Drives TWO
    documents so a per-document re-read (2 reads) is distinguishable from a
    single up-front read (1 read); a single-document data root cannot tell the
    two apart.

    Mutation caught: threading ``settings=load_load_settings(
    load_settings_document(data_root), load_settings_file)`` into
    ``_process_document`` at engine.py:291 (instead of the already-resolved
    ``settings`` held from the up-front read) re-reads the table once per
    document -- the count becomes 2 under this mutation."""
    data_root = _build_data_root(
        tmp_path,
        {"run.fit": builder.run_fit_bytes(), "ride.fit": builder.ride_fit_bytes()},
    )
    calls: list[Path] = []
    # Taken from the defining module rather than from ``load_engine``'s binding
    # of it: ``load_settings_document`` belongs to ``fitdocs.settings`` and the
    # engine merely imports it, so reading it back off ``load_engine`` is an
    # implicit re-export that ``mypy --strict`` rejects. It is the same function
    # object either way, and this is only the wrapped original. What must target
    # the engine's own namespace is the ``setattr`` below -- patching *that*
    # binding is the point of the test -- and that is unchanged.
    original = load_settings_document

    def _counting_wrapper(root: Path) -> object:
        calls.append(root)
        return original(root)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(load_engine, "load_settings_document", _counting_wrapper)
        apply_load(data_root, session=NonInteractiveSession())

    assert len(calls) == 1


# --- LoadContext: resolved settings + the document's own date (1.12-1.14) ---


class _ContextEchoCalculator:
    """A RUN-supporting calculator that echoes its :class:`LoadContext` into
    the result's ``basis`` -- the only way a black-box pass-level test can
    observe what the engine actually built and handed to ``compute``."""

    calculator_id = "stub-context-echo"
    display_name = "Stub Context Echo Calculator"
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
        default = context.settings.default_calculator
        staleness = context.settings.benchmark_staleness_days
        basis = f"date={context.activity_date} default={default} staleness={staleness}"
        return Computed(
            result=LoadResult(
                calculator_id=self.calculator_id,
                display_name=self.display_name,
                value=1.0,
                basis=basis,
                non_selected=(),
                flags=(),
                inputs_used=(),
                notes=(),
            )
        )


def test_context_carries_resolved_settings_and_the_documents_own_date(
    isolated_registry: None,
    tmp_path: Path,
) -> None:
    """The context built for ``compute`` carries the pass's resolved ``[load]``
    settings and the document's own recorded date, read through
    ``contract.document_date`` -- never a clock (Req 1.12, 14.5)."""
    echo = _ContextEchoCalculator()
    registry.register(echo)
    try:
        data_root = _build_data_root(tmp_path, {"run.fit": builder.run_fit_bytes()})
        run = _doc(data_root, "run")
        block = run.read_text(encoding="utf-8").split("---\n", 2)[1]
        recorded_date = yaml.safe_load(block)["date"]
        _write_load_settings(
            data_root, f'[load]\ndefault_calculator = "{echo.calculator_id}"\n'
        )

        report = apply_load(data_root, session=NonInteractiveSession())

        assert _docs_of(report.computed) == {_rel(data_root, run)}
        payload = classify_load_region(run.read_text(encoding="utf-8")).payload
        assert payload is not None and payload.result is not None
        assert f"date={recorded_date}" in payload.result.basis
        assert f"default={echo.calculator_id}" in payload.result.basis
    finally:
        registry.unregister(echo.calculator_id)


def test_context_date_is_absent_for_an_undated_document(
    isolated_registry: None,
    tmp_path: Path,
) -> None:
    """An undated document binds an absent date on the context -- never today's
    date substituted (steering: absent data is ``None``, never a fabricated
    default)."""
    echo = _ContextEchoCalculator()
    registry.register(echo)
    try:
        data_root = _build_data_root(tmp_path, {"run.fit": builder.run_fit_bytes()})
        run = _doc(data_root, "run")
        lines = run.read_text(encoding="utf-8").split("\n")
        undated = [line for line in lines if not line.startswith("date:")]
        undated_text = "\n".join(undated)
        run.write_text(undated_text, encoding="utf-8")

        # Precondition (task 5.2 Gap 2): the rewritten document genuinely has no
        # parseable date -- through the same contract accessor the engine itself
        # uses, never an inline key read -- so a false PASS below (e.g. a stub
        # never invoked, or a document that still carries a date) is ruled out.
        assert contract.document_date(contract.parse_frontmatter(undated_text)) is None

        _write_load_settings(
            data_root, f'[load]\ndefault_calculator = "{echo.calculator_id}"\n'
        )

        report = apply_load(data_root, session=NonInteractiveSession())

        # Precondition continued: the document actually reached `compute` (the
        # stub really ran) rather than being skipped/failed for an unrelated
        # reason, which would make the basis assertion below vacuous.
        assert _docs_of(report.computed) == {_rel(data_root, run)}
        payload = classify_load_region(run.read_text(encoding="utf-8")).payload
        assert payload is not None and payload.result is not None
        assert "date=None" in payload.result.basis
    finally:
        registry.unregister(echo.calculator_id)


def test_context_carries_the_configured_staleness_window(
    isolated_registry: None,
    tmp_path: Path,
) -> None:
    """A configured ``benchmark_staleness_days`` reaches the calculator on the
    context's resolved settings -- this spec's own ``[load]`` field (task 2.2),
    distinct from ``training-load``'s ``default_calculator``.

    Pins **Req 7.3** (the staleness window reaches a calculator through the
    per-pass context's resolved settings, never through the profile view) and
    design's ``LoadEngineWiring``. It deliberately pins none of Req 2.9, 5.5 or
    8.2: this stub declares no athlete fields, so no prompt path runs; the
    ``[load]`` table here is *valid*, so no abort path runs; and it never writes
    ``athlete.toml``. Those three are covered elsewhere -- see the sweep in
    task 5.2's review.

    30 is deliberately not the default (``DEFAULT_LOAD_SETTINGS.
    benchmark_staleness_days == 84``, ``tests/load/test_settings.py:81``), so
    observing 30 distinguishes "the configured value arrived" from "some value
    arrived": dropping only this field from the projection makes the context
    echo 84 and reddens the assertion below as the suite's sole failure.

    The assertion anchors the END of the basis rather than matching a
    substring. ``staleness=`` is the trailing field, so a bare
    ``"staleness=30" in basis`` is a prefix match that a window of 300 also
    satisfies -- measured: multiplying the projected window by 10 left the
    whole suite green."""
    echo = _ContextEchoCalculator()
    registry.register(echo)
    try:
        data_root = _build_data_root(tmp_path, {"run.fit": builder.run_fit_bytes()})
        run = _doc(data_root, "run")
        _write_load_settings(
            data_root,
            f'[load]\ndefault_calculator = "{echo.calculator_id}"\n'
            "benchmark_staleness_days = 30\n",
        )

        report = apply_load(data_root, session=NonInteractiveSession())

        assert _docs_of(report.computed) == {_rel(data_root, run)}
        payload = classify_load_region(run.read_text(encoding="utf-8")).payload
        assert payload is not None and payload.result is not None
        assert payload.result.basis.endswith("staleness=30")
    finally:
        registry.unregister(echo.calculator_id)


# --- atomicity guard (task 6.4, Req 7.2, 10.6, 11.5): the cross-spec ---------
# document-contract change (task 2.4's rename) stays coherent from the
# document's *own* frontmatter, built by a genuine current-format load pass --
# never a hand-built or legacy-shaped dict, per task 2.4's own review note
# (post-rename, ``strip_frontmatter_load`` no longer strips ``load_points`` /
# ``load_zone``, so a legacy payload put through ``--recompute`` would leave
# stale unmanaged keys behind and a guard built on one would contradict
# itself).


def test_unmanaged_keys_is_empty_after_a_genuine_current_format_load_pass(
    isolated_registry: None,
    computing_calculator: ComputingCalculator,
    tmp_path: Path,
) -> None:
    """A document that has had a *real* load pass -- run through the stub
    calculator that exercises the full result vocabulary (non-selected values
    and quality flags included) -- reports no unmanaged frontmatter key.

    Unlike ``tests/test_contract.py::test_unmanaged_keys_is_empty_after_a_
    training_load_pass``, which hand-builds ``{key: "x" for key in
    contract.LOAD_KEYS}``, this drives the actual pipeline: sync renders the
    placeholder, ``apply_load`` computes and writes real load frontmatter, and
    the *whole* frontmatter block (not just the three load keys) is parsed and
    checked. This is what actually exercises the atomicity between task 2.4's
    key rename and the document-format version bump -- a mismatch between them
    would report ``load_value``/``load_methodology``/``load_basis`` (or their
    withdrawn predecessors ``load_points``/``load_zone``) as unmanaged.

    Mutation caught: removing any one of ``LOAD_KEYS`` from ``MANAGED_KEYS``
    (simulating the rename landing out of step with the managed-key set)
    reddens this test with the offending key named -- proven by hand against
    ``contract.MANAGED_KEYS = contract.MANAGED_KEYS - {"load_basis"}`` before
    writing this test.
    """
    data_root = _build_data_root(tmp_path, {"run.fit": builder.run_fit_bytes()})
    run = _doc(data_root, "run")

    report = apply_load(data_root, session=_compute_run_session(level=4))
    assert _docs_of(report.computed) == {_rel(data_root, run)}

    text = run.read_text(encoding="utf-8")
    frontmatter = contract.parse_frontmatter(text)
    assert frontmatter is not None
    # the result vocabulary's diagnostics are real (non_selected + all three
    # flag verdicts), proving this frontmatter came from a genuinely computed,
    # non-trivial result -- not a `Computed` outcome carrying nothing to leak.
    payload = classify_load_region(text).payload
    assert payload is not None and payload.result is not None
    assert payload.result.non_selected and payload.result.flags

    assert contract.unmanaged_keys(frontmatter) == ()
    assert set(contract.LOAD_KEYS) <= set(frontmatter)


# --- task 4.2: apply_load's injectable `today` threads to `on=` ------------

_BENCH_PROBE_FIELD = AthleteField(
    key="benchmarks.run.ftp_watts",
    label="Stub benchmark FTP",
    kind="float",
    minimum=50.0,
    maximum=600.0,
    help_text="Engine-level probe for the injectable `today` -> `on` thread.",
    benchmark=BenchmarkRef(kind=BenchmarkKind.FTP_WATTS, discipline=Sport.RUN),
)


class _BenchmarkProbeCalculator:
    """Declares one benchmark field and never computes -- exists only to
    drive :func:`collect_missing_fields` through a real ``apply_load`` pass
    so the engine's ``today`` -> ``on`` thread (task 4.2) is proven
    end-to-end, not merely at the unit level in ``test_prompts.py``.
    """

    calculator_id = "stub-benchmark-probe"
    display_name = "Stub Benchmark Probe Calculator"
    supported_modalities = frozenset({Modality.RUN})

    def required_athlete_fields(self) -> tuple[AthleteField, ...]:
        return (_BENCH_PROBE_FIELD,)

    def compute(
        self,
        activity: object,
        metrics: object,
        profile: object,
        session: InteractionSession,
        context: LoadContext,
    ) -> LoadOutcome:
        return NotComputed(reason="probe calculator never computes")


def test_apply_load_stamps_an_accepted_benchmark_with_the_injected_today(
    isolated_registry: None,
    tmp_path: Path,
) -> None:
    """Passing an explicit ``today=`` to ``apply_load`` (task 4.2's injectable
    seam) is the date a benchmark answer accepted during that pass is
    persisted under -- not the real system date, which is never touched here.

    Mutation caught: threading a hardcoded date, or ``date.today()``
    unconditionally, instead of the injected ``today`` into
    ``collect_missing_fields``'s ``on=`` would stamp the entry under a date
    other than ``stamped`` (chosen far from any plausible real "today" in this
    suite's lifetime), reddening the ``measured_on`` assertion below.
    """
    calc = _BenchmarkProbeCalculator()
    registry.register(calc)
    try:
        data_root = _build_data_root(tmp_path, {"run.fit": builder.run_fit_bytes()})
        session = ScriptedSession(floats=[275.0])
        stamped = date(2019, 4, 4)

        report = apply_load(
            data_root,
            session=session,
            calculator_id=calc.calculator_id,
            today=stamped,
        )

        # The document (2021) is dated after the injected pass date, so the
        # retroactive question must not fire -- asserted directly, not only
        # through the empty confirm queue raising into report.failures.
        assert report.failures == ()
        assert session.confirm_defaults == []

        profile = load_profile(data_root)
        entry = profile.benchmark(
            BenchmarkKind.FTP_WATTS, discipline=Sport.RUN, on=stamped
        )
        assert entry is not None
        assert entry.value == 275.0
        assert entry.measured_on == stamped
    finally:
        registry.unregister(calc.calculator_id)


def test_apply_load_defaults_today_to_the_real_calendar_date(
    isolated_registry: None,
    tmp_path: Path,
) -> None:
    """Omitting ``today`` resolves it via ``date.today()`` (task 4.2's
    ``today = today or date.today()``) -- the pass's one permitted clock read.

    The fixture document's own recorded date (derived from
    ``builder.run_fit_bytes()``'s fixed FIT timestamp) is 2021, always earlier
    than the real calendar date this test runs under -- so the retroactive
    question (Req 3.7-3.9) now fires, and a queued ``confirm`` answer is
    required (task 7.3; previously this probe never reached the question).

    Mutation caught: deleting the ``or date.today()`` fallback (leaving
    ``today`` as ``None``) breaks ``with_benchmark(measured_on=today)``'s type
    at runtime; a mutant that instead hardcodes a fixed fallback date
    reddens this assertion against the real calendar date captured just
    before the call.
    """
    calc = _BenchmarkProbeCalculator()
    registry.register(calc)
    try:
        data_root = _build_data_root(tmp_path, {"run.fit": builder.run_fit_bytes()})
        doc = _doc(data_root, "run")
        frontmatter = contract.parse_frontmatter(doc.read_text(encoding="utf-8"))
        activity_date = contract.document_date(frontmatter)
        assert activity_date is not None
        session = ScriptedSession(floats=[310.0], confirms=[True])
        before = date.today()
        assert activity_date < before  # precondition: the question must fire

        apply_load(data_root, session=session, calculator_id=calc.calculator_id)

        after = date.today()
        profile = load_profile(data_root)
        entry = profile.benchmark(
            BenchmarkKind.FTP_WATTS, discipline=Sport.RUN, on=after
        )
        assert entry is not None
        assert entry.value == 310.0
        assert before <= entry.measured_on <= after
        assert entry.applies_from == activity_date
        # Req 3.9: the retroactive question defaults to True. This probe
        # asks exactly one confirm (no hint), so the single recorded entry
        # is unambiguously the retroactive question.
        assert len(session.confirm_defaults) == 1
        retro_question, retro_default = session.confirm_defaults[0]
        assert "Recorded as measured on" in retro_question
        assert retro_default is True
    finally:
        registry.unregister(calc.calculator_id)


def test_apply_load_retroactive_question_false_persists_with_no_applies_from(
    isolated_registry: None,
    tmp_path: Path,
) -> None:
    """Engine-level False-branch: a declined-retroactive (``False``) answer
    persists ``measured_on=today`` with no ``applies_from``."""
    calc = _BenchmarkProbeCalculator()
    registry.register(calc)
    try:
        data_root = _build_data_root(tmp_path, {"run.fit": builder.run_fit_bytes()})
        doc = _doc(data_root, "run")
        frontmatter = contract.parse_frontmatter(doc.read_text(encoding="utf-8"))
        activity_date = contract.document_date(frontmatter)
        assert activity_date is not None
        stamped = date(2030, 1, 1)  # after the fixture's ~2021 activity date
        assert activity_date < stamped
        session = ScriptedSession(floats=[311.0], confirms=[False])

        apply_load(
            data_root,
            session=session,
            calculator_id=calc.calculator_id,
            today=stamped,
        )

        profile = load_profile(data_root)
        entry = profile.benchmark(
            BenchmarkKind.FTP_WATTS, discipline=Sport.RUN, on=stamped
        )
        assert entry is not None
        assert entry.value == 311.0
        assert entry.measured_on == stamped
        assert entry.applies_from is None
    finally:
        registry.unregister(calc.calculator_id)


def test_apply_load_retroactive_question_none_persists_nothing(
    isolated_registry: None,
    tmp_path: Path,
) -> None:
    """Engine-level None-branch: a declined/skipped retroactive question
    persists nothing at all -- ``athlete.toml`` is not even written."""
    calc = _BenchmarkProbeCalculator()
    registry.register(calc)
    try:
        data_root = _build_data_root(tmp_path, {"run.fit": builder.run_fit_bytes()})
        doc = _doc(data_root, "run")
        frontmatter = contract.parse_frontmatter(doc.read_text(encoding="utf-8"))
        activity_date = contract.document_date(frontmatter)
        assert activity_date is not None
        stamped = date(2030, 1, 1)
        assert activity_date < stamped
        session = ScriptedSession(floats=[312.0], confirms=[None])

        report = apply_load(
            data_root,
            session=session,
            calculator_id=calc.calculator_id,
            today=stamped,
        )

        # Reachability: the question was asked (and skipped) and the pass
        # recorded no failure -- an engine that never asks also writes no
        # profile, so the absent-file assertion alone cannot tell them apart.
        assert report.failures == ()
        assert len(session.confirm_defaults) == 1
        assert not (data_root / PROFILE_FILENAME).exists()
    finally:
        registry.unregister(calc.calculator_id)


def test_apply_load_today_parameter_is_keyword_only_and_typed() -> None:
    """Pins ``apply_load``'s ``today: date | None = None`` shape (design's
    ``LoadEngineWiring`` Service Interface) -- a declared type alone is
    pinned by nothing unless a test reads it (task 4.1's rejection)."""
    params = inspect.signature(apply_load).parameters
    today_param = params["today"]
    assert today_param.kind is inspect.Parameter.KEYWORD_ONLY
    assert today_param.default is None
    assert today_param.annotation == "date | None"


# --- task 2.4: LoadPassPreservation -- engine-level, all three load paths
# leave a hand-tagged page's effort lines byte-identical (Req 4.3) ----------
#
# A "synced page tagged by hand" is a real, rendered workout document (the
# real sync pipeline, not a hand-mocked string) into which the four
# effort-tag user lines are inserted, verbatim, exactly the way a person
# editing the file would -- never through any fitdocs write path. These
# tests drive that page through each of the engine's three distinct load
# branches (restore / compute / recompute, ``fitdocs/load/engine.py``'s
# ``_process_document``) and prove that every effort line survives
# byte-identically, in the same relative order, and that the unmanaged-key
# reader (``contract.unmanaged_keys``, the effort-tag exemption) still
# reports nothing for the page afterward.

_TAG_LINES: tuple[str, ...] = (
    "effort: race",
    # Trailing whitespace, deliberately: a byte-identity assertion that only
    # checks a line's stripped/semantic value would not notice it silently
    # dropped -- proven against a `line.rstrip()` mutation applied to
    # `kept` in both `apply_frontmatter_load` and `strip_frontmatter_load`.
    "effort_distance_m: 42195  ",
    "effort_time_s: 10800",
    'effort_event: "[[Boston Marathon 2024]]"',
)
"""The four effort-tag user lines, in a fixed relative order, exactly as the
task's Observable names the ``effort_event`` line."""


def _tag_by_hand(text: str) -> str:
    """Insert the four effort-tag user lines just before the closing
    frontmatter fence -- simulating a page a person tagged by hand, never a
    line any fitdocs write path produces."""
    first_idx = text.index("---\n")
    second_idx = text.index("---\n", first_idx + len("---\n"))
    return text[:second_idx] + "\n".join(_TAG_LINES) + "\n" + text[second_idx:]


def _assert_effort_lines_preserved_and_ordered(text: str) -> None:
    """Every effort-tag line is present verbatim and in the fixture's
    relative order -- a swap of any two would fail this."""
    lines = text.split("\n")
    indices = [lines.index(line) for line in _TAG_LINES]
    assert indices == sorted(indices), f"effort lines out of relative order: {indices}"


def _assert_unmanaged_keys_empty_for(text: str) -> None:
    frontmatter = contract.parse_frontmatter(text)
    assert frontmatter is not None
    assert contract.unmanaged_keys(frontmatter) == ()


def test_restore_path_preserves_hand_tagged_effort_lines(
    isolated_registry: None,
    computing_calculator: ComputingCalculator,
    tmp_path: Path,
) -> None:
    """A synced page already carrying a computed load payload in the region,
    tagged by hand afterward, runs the restore path (no recompute, no
    prompting): every effort-tag line is byte-identical and in the same
    relative order afterward, and the unmanaged-key reader still reports
    nothing for the page (Req 4.3).

    Mutation caught: if the restore branch's ``apply_frontmatter_load`` call
    ever classified an effort-tag line as managed (this task's named
    mutation), the line would be stripped out of ``kept`` and this
    assertion would raise ``ValueError`` looking it up in the rewritten
    file instead of finding it in place.
    """
    data_root = _build_data_root(tmp_path, {"run.fit": builder.run_fit_bytes()})
    run = _doc(data_root, "run")
    apply_load(data_root, session=_compute_run_session(level=7))
    assert classify_load_region(run.read_text(encoding="utf-8")).state is (
        RegionState.COMPUTED
    )

    run.write_text(_tag_by_hand(run.read_text(encoding="utf-8")), encoding="utf-8")

    report = apply_load(data_root, session=NonInteractiveSession())

    assert _docs_of(report.restored) == {_rel(data_root, run)}
    result_text = run.read_text(encoding="utf-8")
    _assert_effort_lines_preserved_and_ordered(result_text)
    _assert_unmanaged_keys_empty_for(result_text)


def test_compute_path_preserves_hand_tagged_effort_lines(
    isolated_registry: None,
    computing_calculator: ComputingCalculator,
    tmp_path: Path,
) -> None:
    """A synced page still holding the placeholder region, tagged by hand,
    runs the compute path (the stub calculator fills the region and the
    frontmatter for the first time): every effort-tag line is byte-identical
    and in the same relative order afterward, and the unmanaged-key reader
    still reports nothing for the page (Req 4.3).

    Mutation caught: same as the restore test above -- the compute branch's
    ``apply_frontmatter_load`` call is the same function under the same
    named mutation.
    """
    data_root = _build_data_root(tmp_path, {"run.fit": builder.run_fit_bytes()})
    run = _doc(data_root, "run")
    assert classify_load_region(run.read_text(encoding="utf-8")).state is (
        RegionState.PLACEHOLDER
    )

    run.write_text(_tag_by_hand(run.read_text(encoding="utf-8")), encoding="utf-8")

    report = apply_load(data_root, session=_compute_run_session(level=6))

    assert _docs_of(report.computed) == {_rel(data_root, run)}
    result_text = run.read_text(encoding="utf-8")
    _assert_effort_lines_preserved_and_ordered(result_text)
    _assert_unmanaged_keys_empty_for(result_text)


def test_recompute_path_preserves_hand_tagged_effort_lines(
    isolated_registry: None,
    computing_calculator: ComputingCalculator,
    tmp_path: Path,
) -> None:
    """A synced page computed once, then tagged by hand, then recomputed
    (``recompute=True`` strips the managed keys and re-confirms from
    scratch, Req 8.3): the effort-tag lines -- including the exact
    ``effort_event: "[[Boston Marathon 2024]]"`` line the task's Observable
    names -- are byte-identical and in the same relative order in the
    written file afterward, and the unmanaged-key reader still reports
    nothing (Req 4.3).

    Mutation caught: the recompute branch strips first (``strip_frontmatter_
    load``) and then upserts fresh keys after a real ``replace_load_region``
    (``apply_frontmatter_load`` again) -- both calls go through the same
    ``_is_managed_line`` this task's named mutation corrupts, so an
    effort-tag line dropped by either call reddens the same lookup-by-value
    assertion below.
    """
    data_root = _build_data_root(tmp_path, {"run.fit": builder.run_fit_bytes()})
    run = _doc(data_root, "run")
    apply_load(data_root, session=_compute_run_session(level=3))

    run.write_text(_tag_by_hand(run.read_text(encoding="utf-8")), encoding="utf-8")

    report = apply_load(data_root, session=_recompute_run_session(), recompute=True)

    assert _docs_of(report.computed) == {_rel(data_root, run)}
    result_text = run.read_text(encoding="utf-8")
    # the task's Observable: this exact line, unchanged, in the written file.
    assert 'effort_event: "[[Boston Marathon 2024]]"' in result_text
    _assert_effort_lines_preserved_and_ordered(result_text)
    _assert_unmanaged_keys_empty_for(result_text)
