"""Regression + per-document isolation guards for plugin-api (task 4.2).

This suite pins two of the four guards task 4.2 owns; the other two -- the
public-surface inclusion check and the offline/dependency-footprint guard --
live in :mod:`tests.test_public_api` and :mod:`tests.test_determinism`
respectively, alongside the neighbouring properties they extend.

* **No-plugin regression (Req 1.7, 7.3, 7.4).** The golden document suite and
  :mod:`tests.test_determinism` already prove byte-identical output with
  nothing installed or configured. What is added here is the plugin layer's
  half of that guarantee made explicit: calling
  :func:`fitdocs.plugins.discover` with nothing installed or configured is
  provably a no-op on the registry -- the exact same built-in objects, in the
  exact same order, are registered before and after -- and a real load pass
  over a mixed RUN/RIDE data root produces the identical outcomes it produced
  before this feature existed.
* **Per-document plugin-failure channel (Req 3.7).** A *registered* plugin
  calculator whose ``compute()`` raises must be handled through the load
  engine's EXISTING per-document failure channel (``fitdocs.load.engine
  .apply_load``'s per-document ``except Exception``, unchanged by this
  feature): only that document is reported failed, and every other document
  in the same pass is processed normally. This mirrors
  ``tests/load/test_engine.py::test_missing_archive_is_a_failure_and_pass_continues``,
  the existing pattern for exactly this isolation property, substituting a
  raising plugin calculator for a missing archive as the fault.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import timedelta, timezone
from pathlib import Path

import pytest

from fitdocs import plugins
from fitdocs.athlete import load_athlete_inputs
from fitdocs.layout import WORKOUTS_DIR
from fitdocs.load import registry
from fitdocs.load.docedit import RegionState, classify_load_region
from fitdocs.load.engine import DocLoadEntry, apply_load
from fitdocs.load.prompts import NonInteractiveSession
from fitdocs.load.types import (
    AthleteField,
    InteractionSession,
    LoadContext,
    LoadOutcome,
    ProfileView,
)
from fitdocs.metrics.types import DerivedMetrics
from fitdocs.model import Activity, Modality
from fitdocs.render.charts.map import TileRef
from fitdocs.sync import sync
from tests.fixtures import builder

# PINNED timezone (never the system zone) so document stems are byte-stable,
# matching the convention in tests/load/test_engine.py.
_TZ = timezone(timedelta(hours=-6))


class _ServingTiles:
    """An inert basemap-tile source: deterministic bytes for any ref, no I/O.

    The load engine only cares about the load region, so this stand-in keeps
    the (required) tile argument satisfied without touching the network or
    the filesystem cache -- mirrors the equivalent fixture in
    ``tests/load/test_engine.py``.
    """

    attribution = "© OpenStreetMap contributors"

    def resolve(self, refs: Sequence[TileRef]) -> dict[TileRef, bytes]:
        return {ref: b"\x89PNG\r\n\x1a\n" for ref in refs}


_TILES = _ServingTiles()


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


def _doc(data_root: Path, needle: str) -> Path:
    """The single workout document whose filename contains ``needle``."""
    return next(p for p in (data_root / WORKOUTS_DIR).glob("*.md") if needle in p.name)


def _rel(data_root: Path, doc: Path) -> str:
    return doc.relative_to(data_root).as_posix()


def _docs_of(entries: tuple[DocLoadEntry, ...]) -> set[str]:
    return {entry.doc for entry in entries}


# --- 1. no-plugin regression (Req 1.7, 7.3, 7.4) -----------------------------


def test_discover_with_nothing_configured_registers_nothing(
    tmp_path: Path,
) -> None:
    """``discover()`` with nothing installed/configured is a registry no-op.

    This spec ships no built-in calculator (Req 13.2): before AND after the
    call, the registry is empty -- proving the plugin layer costs nothing
    when unused, rather than merely happening to leave the same *set of ids*
    (Req 1.7, 7.3, 7.4)."""
    data_root = tmp_path / "data"
    data_root.mkdir()

    before = registry.available()
    assert before == ()

    report = plugins.discover(data_root, plugins.DEFAULT_PLUGIN_SETTINGS)

    after = registry.available()
    assert after == before == ()
    assert report.errors == ()
    assert report.calculators == ()


def test_discover_with_nothing_configured_leaves_run_selection_unchanged(
    tmp_path: Path,
) -> None:
    """Automatic calculator selection for RUN documents is unaffected by a
    no-op discovery call -- no calculator supports it, both before and after
    (Req 1.7, 7.4, 13.2)."""
    data_root = tmp_path / "data"
    data_root.mkdir()

    before = registry.for_modality(Modality.RUN)
    plugins.discover(data_root, plugins.DEFAULT_PLUGIN_SETTINGS)
    after = registry.for_modality(Modality.RUN)

    assert after == before == ()


def test_discover_then_apply_load_leaves_outcomes_unchanged(
    tmp_path: Path,
) -> None:
    """A load pass over identical inputs is byte-identical whether or not a
    (no-op) discovery call preceded it: with no calculator registered
    (Req 13.2), both a RUN document and a RIDE document get the honest
    unsupported state, with no failures either way (Req 1.7, 7.3, 7.4).

    Two SEPARATE data roots are used -- one where ``apply_load`` runs alone
    (the pre-plugin-api shape) and one where ``discover()`` runs first,
    exactly as the CLI now runs it -- so the comparison is genuinely between
    "discovery happened" and "it didn't," not just a document compared to
    itself.
    """
    without_discovery = _build_data_root(
        tmp_path / "without_discovery",
        {"run.fit": builder.run_fit_bytes(), "ride.fit": builder.ride_fit_bytes()},
    )
    with_discovery = _build_data_root(
        tmp_path / "with_discovery",
        {"run.fit": builder.run_fit_bytes(), "ride.fit": builder.ride_fit_bytes()},
    )

    baseline_report = apply_load(without_discovery, session=NonInteractiveSession())

    # Discovery runs exactly as the CLI runs it: before any engine call.
    plugins.discover(with_discovery, plugins.DEFAULT_PLUGIN_SETTINGS)
    discovered_report = apply_load(with_discovery, session=NonInteractiveSession())

    assert baseline_report.failures == () and discovered_report.failures == ()
    run = _doc(without_discovery, "run")
    ride = _doc(without_discovery, "ride")
    assert _rel(without_discovery, run) in _docs_of(baseline_report.unsupported)
    assert _rel(without_discovery, ride) in _docs_of(baseline_report.unsupported)

    # Same categorization on the discovery-preceded root.
    run_d = _doc(with_discovery, "run")
    ride_d = _doc(with_discovery, "ride")
    assert _rel(with_discovery, run_d) in _docs_of(discovered_report.unsupported)
    assert _rel(with_discovery, ride_d) in _docs_of(discovered_report.unsupported)

    # The written documents are byte-identical between the two roots: a no-op
    # discovery call changed nothing about what the load pass wrote.
    assert run.read_bytes() == run_d.read_bytes()
    assert ride.read_bytes() == ride_d.read_bytes()

    classification = classify_load_region(ride.read_text(encoding="utf-8"))
    state, payload = classification.state, classification.payload
    assert state is RegionState.UNSUPPORTED
    assert payload is not None and payload.sport == "Ride"

    run_classification = classify_load_region(run.read_text(encoding="utf-8"))
    run_state, run_payload = run_classification.state, run_classification.payload
    assert run_state is RegionState.UNSUPPORTED
    assert run_payload is not None and run_payload.sport == "Run"


# --- 2. per-document plugin-failure channel (Req 3.7) ------------------------


class _RaisingRideCalculator:
    """A registered plugin calculator whose ``compute()`` always raises.

    Declares support for RIDE, a modality no built-in calculator covers, so
    registering it is what makes a RIDE document reach ``compute()`` at all in
    this pass -- without it, RIDE would simply be reported unsupported and
    ``compute()`` would never run.
    """

    calculator_id: str = "regression-raiser"
    display_name: str = "Regression Raiser"
    supported_modalities: frozenset[Modality] = frozenset({Modality.BIKE})

    def required_athlete_fields(self) -> tuple[AthleteField, ...]:
        return ()

    def compute(
        self,
        activity: Activity,
        metrics: DerivedMetrics,
        profile: ProfileView,
        session: InteractionSession,
        context: LoadContext,
    ) -> LoadOutcome:
        raise RuntimeError("boom: this plugin always fails")


def test_a_raising_plugin_calculator_fails_only_its_own_document(
    tmp_path: Path,
) -> None:
    """A REGISTERED plugin calculator whose ``compute()`` raises is reported
    through the EXISTING per-document failure channel: only its own document
    is reported failed with the reason, and every other document in the same
    pass is processed normally (Req 3.7).

    Mirrors ``test_missing_archive_is_a_failure_and_pass_continues`` in
    ``tests/load/test_engine.py`` -- the established pattern for exactly this
    isolation property -- substituting a raising plugin calculator for a
    missing archive as the fault. Without ``apply_load``'s per-document
    ``except Exception``, this raise would propagate out of the whole pass and
    the run document would never be processed -- which is what the final
    assertion below rules out.
    """
    calculator = _RaisingRideCalculator()
    # Sanity: the plugin genuinely raises when invoked (not vacuous). The
    # engine never actually calls compute() with placeholder Nones -- this is
    # a direct probe of the calculator alone, so the arguments are untyped.
    with pytest.raises(RuntimeError, match="boom"):
        calculator.compute(None, None, None, NonInteractiveSession(), None)  # type: ignore[arg-type]

    registry.register(calculator)
    try:
        data_root = _build_data_root(
            tmp_path,
            {"run.fit": builder.run_fit_bytes(), "ride.fit": builder.ride_fit_bytes()},
        )
        run = _doc(data_root, "run")
        ride = _doc(data_root, "ride")
        ride_before = ride.read_bytes()

        report = apply_load(data_root, session=NonInteractiveSession())

        failed_docs = _docs_of(report.failures)
        assert _rel(data_root, ride) in failed_docs
        detail = next(
            entry.detail
            for entry in report.failures
            if entry.doc == _rel(data_root, ride)
        )
        assert "boom" in detail
        assert ride.read_bytes() == ride_before  # a failure never mutates its doc

        # The pass kept going: the OTHER document was still processed normally
        # (no calculator supports running, so it receives the honest
        # unsupported state) rather than the whole run aborting.
        assert _rel(data_root, run) in _docs_of(report.unsupported)
        assert len(report.failures) == 1
    finally:
        # This calculator was registered directly, not through discover(), so
        # the autouse plugins.reset() fixture does not know about it.
        registry.unregister(calculator.calculator_id)


def test_plugins_module_prose_never_asserts_a_bundled_calculator_ships() -> None:
    """``plugins.py``'s own docstrings agree with Req 13.2: no calculator ships.

    ``test_fresh_interpreter_reports_the_registry_empty`` (tests/load/
    test_packaging.py) already pins the *behaviour*. What went stale is the
    prose above it: ``PluginReport.calculators`` documented the tuple as "in
    registration order (built-ins first)" and ``discover()`` stated that
    "built-ins are already registered by the time this runs ... so they always
    occupy the first registry slots". Both survived the deletion of the only
    built-in fitdocs ever shipped, and both are on the *published plugin
    surface* -- a plugin author reading them infers that bundled calculators
    exist and outrank theirs, which is the mental model Req 13.2 removed.

    Prose is not covered by any behavioural test, which is exactly why a false
    claim can outlive the behaviour it describes. This is the cheapest guard
    that closes the gap: the withdrawn claims cannot be restored verbatim.

    The ``BuiltIn`` *origin* is deliberately not forbidden. Origin is assigned
    by discovery channel, so a calculator registered outside the plugin
    channels legitimately carries it; only the claim that one ships is wrong.
    """
    source = Path(plugins.__file__).read_text(encoding="utf-8")

    # Positive control: without it, a rename of the module under test would
    # leave this asserting emptiness against an empty string forever.
    assert "class PluginReport" in source, "not reading fitdocs/plugins.py"

    forbidden = [
        "built-ins first",
        "occupy the first registry slots",
        "Built-ins are already registered",
        "built-ins are registered regardless",
    ]
    found = [phrase for phrase in forbidden if phrase in source]
    assert not found, (
        f"fitdocs/plugins.py claims a bundled calculator ships: {found}. "
        "fitdocs registers no calculator on import (Req 13.2); see "
        "fitdocs/load/__init__.py's own docstring."
    )
