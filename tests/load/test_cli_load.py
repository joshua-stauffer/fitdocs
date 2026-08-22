"""CLI end-to-end tests: the ``fitdocs load`` command and sync/regen wiring.

These drive the installable entry point through :class:`typer.testing.CliRunner`
over real temporary data roots (built with the workout-docs pipeline via
:func:`fitdocs.sync.sync`), locking the observable contract of task 4.1:

* ``fitdocs load [--out PATH] [--recompute] [--calculator ID] [--no-prompt]``
  runs the load pass and prints a summary table -- computed / restored /
  unsupported / skipped (with reasons) / failed -- with exit codes matching
  sync: ``0`` success (including an all-skipped pass), ``1`` any failure,
  ``2`` a configuration error (unresolvable data root, malformed profile,
  unknown calculator id) (Req 8.2, 8.6).
* ``fitdocs sync`` runs the load pass after writing documents (honoring
  ``--no-prompt``); ``fitdocs regen`` runs it prompt-free so restoration
  happens without user interaction (Req 8.1, 3.5, 7.4).
* The session factory ``_build_session`` picks the interactive session only on
  a real terminal with prompting enabled (Req 3.5).

Under ``CliRunner`` stdin is not a TTY, so the default session is
``NonInteractiveSession`` -- ideal for the unsupported / skip / restore / exit
paths. The interactive compute-through-CLI path is exercised by monkeypatching
``fitdocs.cli._build_session`` to a scripted session (queued answers).

fitdocs ships no calculator (Amendment 2), so the compute-through-CLI tests
drive the pass with ``ComputingCalculator`` (:mod:`tests.load.conftest`, task
1.1), registered per-test via the shared ``isolated_registry`` +
``computing_calculator`` fixtures.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import timedelta, timezone
from pathlib import Path

import pytest
from typer.testing import CliRunner

from fitdocs import Modality, cli
from fitdocs.athlete import load_athlete_inputs
from fitdocs.cli import _build_session, app
from fitdocs.layout import WORKOUTS_DIR
from fitdocs.load import engine as load_engine
from fitdocs.load import registry as load_registry
from fitdocs.load.docedit import (
    RegionState,
    classify_load_region,
    read_frontmatter_load,
    strip_frontmatter_load,
)
from fitdocs.load.profile import PROFILE_FILENAME, load_profile, save_profile
from fitdocs.load.prompts import NonInteractiveSession, RichInteractionSession
from fitdocs.load.types import (
    Activity,
    AthleteField,
    Computed,
    DerivedMetrics,
    InteractionSession,
    LoadContext,
    LoadOutcome,
    LoadResult,
    ProfileView,
)
from fitdocs.sync import sync
from tests.fixtures import builder
from tests.load.conftest import (
    COMPUTING_FIELD,
    ComputingCalculator,
    ScopedFieldCalculator,
)

runner = CliRunner()

# PINNED timezone (never the system zone) so document stems are byte-stable.
_TZ = timezone(timedelta(hours=-6))


class _ServingTiles:
    """The always-supplied basemap-tile source the setup sync injects (task 6.1).

    ``tiles`` is a required engine argument now; this inert source serves
    deterministic PNG bytes for any ref so the load-region assertions are
    unaffected. Stateless -> one shared instance is safe.
    """

    attribution = "© OpenStreetMap contributors"

    def resolve(self, refs: Sequence[object]) -> dict[object, bytes]:
        return {ref: b"\x89PNG\r\n\x1a\n" for ref in refs}


_TILES: _ServingTiles = _ServingTiles()


@pytest.fixture(autouse=True)
def _offline_tiles(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep every CLI ``sync``/``regen`` network-free (task 6.1 test guard).

    The CLI now builds a real ``TileStore`` from the data root's defaulted
    settings; for a GPS-bearing fixture with the default provider enabled that
    would fetch basemap tiles on a cold cache. Patching the module fetch seam to
    return deterministic bytes makes tile resolution succeed offline, so no test
    here performs real network access.
    """
    monkeypatch.setattr(
        "fitdocs.tiles._default_fetch", lambda _url: b"\x89PNG\r\n\x1a\n"
    )


# --- scripted interaction session (drives the interactive CLI compute path) --


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

    @staticmethod
    def _pop(queue: list[object], kind: str) -> object:
        if not queue:
            raise AssertionError(f"ScriptedSession: no more {kind} answers queued")
        return queue.pop(0)

    def confirm(self, question: str, *, default: bool = True) -> bool | None:
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


def _compute_run_session(*, level: int = 7, confirm: bool = True) -> ScriptedSession:
    """A full compute script for a placeholder RUN doc with an EMPTY profile:
    collect ``level`` (the stub's one required field), then confirm the result.
    """
    return ScriptedSession(ints=[level], confirms=[confirm])


def _recompute_run_session(*, confirm: bool = True) -> ScriptedSession:
    """When the profile ALREADY carries ``level``, only the confirm dialog runs."""
    return ScriptedSession(confirms=[confirm])


# --- data-root construction (real workout-docs pipeline) --------------------


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


def _table_count(output: str, label: str) -> int:
    """The integer count printed on the summary table's ``label`` row.

    Tolerant of the rich table's box-drawing borders and column padding: it
    matches ``label`` followed (across the cell border) by the row's digits.
    Duplicated from ``tests/load/test_feature_e2e.py`` consistently with this
    module's existing helper duplication (``_build_data_root``, ``_doc``,
    ``_compute_run_session``, ``_sources_last``).
    """
    match = re.search(rf"{re.escape(label)}\s*\S\s*(\d+)", output)
    assert match is not None, f"{label!r} row not found in:\n{output}"
    return int(match.group(1))


def _sources_last(doc: Path) -> str:
    """The document's current (last) ``sources`` archive ref."""
    import yaml

    block = doc.read_text(encoding="utf-8").split("---\n", 2)[1]
    parsed = yaml.safe_load(block)
    assert isinstance(parsed, dict)
    sources = parsed["sources"]
    assert isinstance(sources, list) and sources
    return str(sources[-1])


# --- help / smoke -----------------------------------------------------------


def test_load_help_documents_all_four_flags() -> None:
    """``load --help`` documents --out, --recompute, --calculator, --no-prompt."""
    result = runner.invoke(app, ["load", "--help"])
    assert result.exit_code == 0
    for flag in ("--out", "--recompute", "--calculator", "--no-prompt"):
        assert flag in result.stdout


def test_root_help_lists_load_command() -> None:
    """The top-level help lists the new ``load`` command alongside sync/regen."""
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "load" in result.stdout


# --- fitdocs load: summary + exit 0 (all-skipped/unsupported is success) -----


def test_load_prints_summary_and_exits_zero(tmp_path: Path) -> None:
    """Over a prepared data root with nothing registered, ``load`` prints the
    five-row summary table; both the run and the ride doc receive the honest
    unsupported state (Req 13.2, 13.6), and the pass exits 0 (all-unsupported
    is success; Req 8.6)."""
    data_root = _build_data_root(
        tmp_path,
        {"run.fit": builder.run_fit_bytes(), "ride.fit": builder.ride_fit_bytes()},
    )
    run = _doc(data_root, "run")
    ride = _doc(data_root, "ride")

    result = runner.invoke(app, ["load", "--out", str(data_root)])

    assert result.exit_code == 0
    # The summary table carries every category label.
    for label in ("Computed", "Restored", "Unsupported", "Skipped", "Failed"):
        assert label in result.output
    # Both docs received the honest unsupported state (no numbers).
    assert classify_load_region(ride.read_text(encoding="utf-8")).state is (
        RegionState.UNSUPPORTED
    )
    assert classify_load_region(run.read_text(encoding="utf-8")).state is (
        RegionState.UNSUPPORTED
    )
    assert read_frontmatter_load(run.read_text(encoding="utf-8")) == {}


def test_load_second_identical_run_writes_nothing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Task 6.3 bullet 1: with nothing registered, ``fitdocs load`` over several
    documents leaves every one honestly unsupported and exits 0; an identical
    second run then performs literally zero atomic writes (Req 8.1, 8.2, 8.6,
    13.2, 13.6).

    The first pass's own effect is asserted first (task 6.2's remediation): the
    post-condition under test -- ``PLACEHOLDER`` -> ``UNSUPPORTED`` -- is
    checked FALSE before the pass runs, so a classifier that never does
    anything cannot make this test pass by accident. The "no writes" half is
    then measured directly by counting calls to the engine's own atomic-write
    seam during the second invocation, rather than only comparing bytes (an
    unconditional re-write of byte-identical content would survive a byte
    snapshot but not a call count)."""
    data_root = _build_data_root(
        tmp_path,
        {"run.fit": builder.run_fit_bytes(), "ride.fit": builder.ride_fit_bytes()},
    )
    run = _doc(data_root, "run")
    ride = _doc(data_root, "ride")
    assert classify_load_region(run.read_text(encoding="utf-8")).state is (
        RegionState.PLACEHOLDER
    )
    assert classify_load_region(ride.read_text(encoding="utf-8")).state is (
        RegionState.PLACEHOLDER
    )

    first = runner.invoke(app, ["load", "--out", str(data_root)])

    assert first.exit_code == 0
    # A count, not a substring: the row label "Unsupported" is printed on every
    # pass regardless of the report, so only the printed count distinguishes an
    # honest tally from an under-reported one (Req 8.6, 13.6).
    assert _table_count(first.output, "Unsupported") == 2
    assert classify_load_region(run.read_text(encoding="utf-8")).state is (
        RegionState.UNSUPPORTED
    )
    assert classify_load_region(ride.read_text(encoding="utf-8")).state is (
        RegionState.UNSUPPORTED
    )

    write_calls: list[Path] = []
    monkeypatch.setattr(
        load_engine, "_atomic_write", lambda doc, new: write_calls.append(doc)
    )

    second = runner.invoke(app, ["load", "--out", str(data_root)])

    assert second.exit_code == 0
    assert write_calls == []


def test_load_calculator_flag_overrides_configured_default(
    isolated_registry: None,
    computing_calculator: ComputingCalculator,
    scoped_field_calculator: ScopedFieldCalculator,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Task 6.3 bullet 3: with two registered RUN supporters and a configured
    default naming the OTHER one, ``--calculator`` on the command line wins
    (Req 10.3).

    ``default_calculator`` is set to ``stub-scoped`` -- the calculator that
    would be selected were the flag absent -- so the override is provable
    rather than merely consistent with either outcome: ``ScopedFieldCalculator``
    prompts for a *float* field the scripted session never queues, so a
    mis-wired precedence (default winning) would either compute the wrong
    result or raise on the missing answer."""
    data_root = _build_data_root(tmp_path, {"run.fit": builder.run_fit_bytes()})
    run = _doc(data_root, "run")
    (data_root / "fitdocs.toml").write_text(
        '[load]\ndefault_calculator = "stub-scoped"\n', encoding="utf-8"
    )
    monkeypatch.setattr(
        cli, "_build_session", lambda **_: _compute_run_session(level=7)
    )

    result = runner.invoke(
        app,
        [
            "load",
            "--out",
            str(data_root),
            "--calculator",
            computing_calculator.calculator_id,
        ],
    )

    assert result.exit_code == 0
    fm = read_frontmatter_load(run.read_text(encoding="utf-8"))
    assert fm["load_methodology"] == computing_calculator.calculator_id
    assert fm["load_methodology"] != scoped_field_calculator.calculator_id
    assert fm["load_value"] == 70  # ComputingCalculator: level 7 * 10


def test_load_ambiguous_default_names_both_candidates_and_the_setting(
    isolated_registry: None,
    computing_calculator: ComputingCalculator,
    scoped_field_calculator: ScopedFieldCalculator,
    tmp_path: Path,
) -> None:
    """Task 6.3 bullet 4: two registered supporters and no configured default
    -- the run succeeds, the document is unchanged, and the printed reason
    names both identifiers and the setting to configure, so the ambiguity is
    actionable (Req 10.2).

    Both stubs declare ``Modality.RUN`` and neither narrows ``supports`` away
    from it, so a run document is genuinely ambiguous between them -- an
    unforced, unconfigured pass over it must not silently pick either."""
    data_root = _build_data_root(tmp_path, {"run.fit": builder.run_fit_bytes()})
    run = _doc(data_root, "run")
    before = run.read_bytes()

    result = runner.invoke(app, ["load", "--out", str(data_root)])

    assert result.exit_code == 0
    assert run.read_bytes() == before  # the ambiguous document is untouched
    # Discriminates from the zero-count "Skipped" label (which prints
    # regardless of outcome): the doc's own name appears under the skipped
    # detail block, naming the reason beneath it.
    assert run.name in result.output
    assert computing_calculator.calculator_id in result.output
    assert scoped_field_calculator.calculator_id in result.output
    assert "default_calculator" in result.output
    assert "fitdocs.toml" in result.output


def test_load_prints_skipped_reason_for_missing_required_input(
    isolated_registry: None,
    computing_calculator: ComputingCalculator,
    tmp_path: Path,
) -> None:
    """A run doc with no ``athlete.toml`` (so the stub's one required field is
    absent) is skipped with a reason -- the CLI's only coverage of the
    skipped-with-reasons detail (Req 8.6)."""
    data_root = _build_data_root(tmp_path, {"run.fit": builder.run_fit_bytes()})
    run = _doc(data_root, "run")

    result = runner.invoke(app, ["load", "--out", str(data_root)])

    assert result.exit_code == 0
    assert run.name in result.output
    assert "missing required inputs" in result.output
    assert COMPUTING_FIELD.label in result.output


# --- fitdocs load: interactive compute via a monkeypatched session -----------


def test_load_computes_run_with_scripted_session(
    isolated_registry: None,
    computing_calculator: ComputingCalculator,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Monkeypatching the session factory to a scripted (interactive) session
    lets ``load`` compute the run doc: the frontmatter load keys appear, the
    summary reports it computed by the stub calculator, and the pass exits 0
    (Req 3.1-3.3)."""
    data_root = _build_data_root(tmp_path, {"run.fit": builder.run_fit_bytes()})
    run = _doc(data_root, "run")
    monkeypatch.setattr(
        cli, "_build_session", lambda **_: _compute_run_session(level=7)
    )

    result = runner.invoke(app, ["load", "--out", str(data_root)])

    assert result.exit_code == 0
    assert "Computed" in result.output
    assert computing_calculator.calculator_id in result.output
    fm = read_frontmatter_load(run.read_text(encoding="utf-8"))
    assert fm["load_value"] == 70  # level 7 * 10
    assert fm["load_methodology"] == computing_calculator.calculator_id
    # The answered inputs were persisted so subsequent runs never re-ask.
    assert (data_root / PROFILE_FILENAME).is_file()


def test_no_prompt_flag_is_forwarded_to_the_session_builder_on_the_load_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``--no-prompt`` is forwarded through ``_build_session`` exactly on the
    ``load`` command's own path (Req 3.5). Spied rather than asserted on
    output, since ``CliRunner``'s stdin is never a TTY -- the *value*
    forwarded is what distinguishes the two, not the resulting session
    class."""
    data_root = _build_data_root(tmp_path, {"run.fit": builder.run_fit_bytes()})
    calls: list[bool] = []
    original = cli._build_session

    def _spy(*, no_prompt: bool) -> InteractionSession:
        calls.append(no_prompt)
        return original(no_prompt=no_prompt)

    monkeypatch.setattr(cli, "_build_session", _spy)

    result = runner.invoke(app, ["load", "--out", str(data_root), "--no-prompt"])
    assert result.exit_code == 0
    assert calls == [True]

    calls.clear()
    result = runner.invoke(app, ["load", "--out", str(data_root)])
    assert result.exit_code == 0
    assert calls == [False]


# --- fitdocs load: recompute replaces the result (Req 8.3) -------------------


def test_load_recompute_replaces_result(
    isolated_registry: None,
    computing_calculator: ComputingCalculator,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``--recompute`` re-confirms from scratch and replaces a computed result
    with a fresh one derived from the profile at recompute time (Req 8.3, 8.6)."""
    data_root = _build_data_root(tmp_path, {"run.fit": builder.run_fit_bytes()})
    run = _doc(data_root, "run")
    monkeypatch.setattr(
        cli, "_build_session", lambda **_: _compute_run_session(level=3)
    )
    first = runner.invoke(app, ["load", "--out", str(data_root)])
    assert first.exit_code == 0
    assert read_frontmatter_load(run.read_text(encoding="utf-8"))["load_value"] == 30

    # Simulate the athlete's stub level rising between passes -- ``level`` is
    # already present in the profile, so recompute only re-runs the confirm
    # dialog and picks up the new persisted value.
    profile = load_profile(data_root)
    save_profile(data_root, profile.with_value(COMPUTING_FIELD, 5))
    monkeypatch.setattr(cli, "_build_session", lambda **_: _recompute_run_session())
    result = runner.invoke(app, ["load", "--out", str(data_root), "--recompute"])

    assert result.exit_code == 0
    fm = read_frontmatter_load(run.read_text(encoding="utf-8"))
    assert fm["load_value"] == 50  # level 5 * 10


# --- fitdocs load --calculator (Req 8.4) ------------------------------------


class _FieldFreeCalculator:
    """A second RUN calculator, distinctly identified and requiring no athlete
    input, so a forced ``--calculator`` naming it reaches ``Computed`` under
    ``CliRunner``'s non-interactive session.

    Its purpose is to make ``--calculator`` *observable*. Every stub in
    ``tests.load.conftest`` declares a required field, so forcing one of those
    under a non-interactive pass lands in ``MissingInputs`` and prints no
    ``[<calculator-id>]`` detail -- precisely the outcome that cannot
    discriminate a threaded flag from an ignored one.

    Raises rather than self-guarding when handed a non-RUN activity: a stub that
    quietly returns ``Unsupported`` for a modality the engine's own prefilter
    should already have excluded shadows the engine's behaviour, so a mutation
    there would pass silently (``tasks.md`` Implementation Notes, task 4.1).
    """

    calculator_id = "stub-field-free"
    display_name = "Stub Field-Free Calculator"
    supported_modalities = frozenset({Modality.RUN})

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
        if activity.modality not in self.supported_modalities:
            raise AssertionError(
                f"{self.calculator_id} was handed {activity.modality!r}, which "
                "the registry's modality prefilter should have excluded"
            )
        return Computed(
            result=LoadResult(
                calculator_id=self.calculator_id,
                display_name=self.display_name,
                value=42.0,
                basis="stub field-free basis",
                non_selected=(),
                flags=(),
                inputs_used=(),
                notes=(),
            )
        )


def test_load_calculator_forces_that_calculator_and_rides_stay_unsupported(
    isolated_registry: None,
    computing_calculator: ComputingCalculator,
    tmp_path: Path,
) -> None:
    """A forced ``--calculator`` uses only that calculator, and a ride neither
    can score becomes the honest unsupported state (Req 8.4, 1.3).

    **Two** calculators are registered, both declaring RUN, because with one the
    8.4 half is unobservable: arbitration selects the same calculator whether
    ``--calculator`` was threaded, ignored, or never parsed, so the assertions
    hold identically under a broken flag. (Measured: hardcoding
    ``calculator_id=None`` in ``cli.py``'s load command left the previous,
    single-calculator version of this test green.)

    With two supporters and no configured ``default_calculator`` the run is an
    unresolved ambiguity (Req 10.2) and computes for neither -- so the
    ``[stub-field-free]`` detail appears if and only if the flag actually
    reached arbitration. That is what makes the docstring's 8.4 claim true of
    the assertions rather than only of the prose.

    The ride carries the 1.3 half: both calculators declare RUN only, so the
    registry's modality prefilter leaves it with no supporter at all.
    """
    data_root = _build_data_root(
        tmp_path,
        {"run.fit": builder.run_fit_bytes(), "ride.fit": builder.ride_fit_bytes()},
    )
    load_registry.register(_FieldFreeCalculator())
    run = _doc(data_root, "run")
    ride = _doc(data_root, "ride")

    # Precondition, asserted rather than assumed: both are registered and both
    # declare RUN, so the run really is contested and the forced choice is a
    # choice rather than the only option.
    registered = {c.calculator_id for c in load_registry.available()}
    assert registered == {computing_calculator.calculator_id, "stub-field-free"}

    result = runner.invoke(
        app,
        ["load", "--out", str(data_root), "--calculator", "stub-field-free"],
    )

    assert result.exit_code == 0
    # Which calculator ran -- the assertion the single-calculator version could
    # not make. Dies if --calculator stops reaching arbitration.
    assert "[stub-field-free]" in result.output
    assert computing_calculator.calculator_id not in result.output
    assert classify_load_region(run.read_text(encoding="utf-8")).state is (
        RegionState.COMPUTED
    )

    assert "Unsupported" in result.output
    assert classify_load_region(ride.read_text(encoding="utf-8")).state is (
        RegionState.UNSUPPORTED
    )


# --- fitdocs load: exit 1 on a per-document failure (Req 8.5) ----------------


def test_load_reports_failure_and_exits_one(tmp_path: Path) -> None:
    """A doc whose archived source is missing becomes a failure entry and makes
    the command exit 1 (a load failure is non-zero like a file failure)."""
    data_root = _build_data_root(tmp_path, {"run.fit": builder.run_fit_bytes()})
    run = _doc(data_root, "run")
    archive = data_root.joinpath(*_sources_last(run).split("/"))
    archive.unlink()

    result = runner.invoke(app, ["load", "--out", str(data_root)])

    assert result.exit_code == 1
    assert "Failed" in result.output
    assert run.name in result.output


# --- fitdocs load: configuration errors -> exit 2, distinct reasons ----------


def test_load_bad_out_path_exits_two(tmp_path: Path) -> None:
    """A nonexistent ``--out`` is an unresolvable data root -> exit 2 (Req 2.2)."""
    missing = tmp_path / "nope"
    result = runner.invoke(app, ["load", "--out", str(missing)])
    assert result.exit_code == 2
    assert "--out" in result.output


def test_load_unknown_calculator_exits_two(tmp_path: Path) -> None:
    """An unknown ``--calculator`` id is a configuration error -> exit 2."""
    data_root = _build_data_root(tmp_path, {"run.fit": builder.run_fit_bytes()})
    result = runner.invoke(
        app, ["load", "--out", str(data_root), "--calculator", "nope"]
    )
    assert result.exit_code == 2
    assert "nope" in result.output


# --- plugin-api wiring: discovery runs before the engine (task 3.1) ---------
#
# ``fitdocs load`` loads the plugin settings and runs discovery once, after the
# data root is resolved and before ``apply_load`` is ever called (Req 1.2), so
# a plugin-provided calculator id can be selected by ``--calculator`` (Req 1.5)
# and an unknown id's error message lists plugin ids alongside built-in ones
# (Req 1.6).

_PLUGIN_CALCULATOR_SOURCE = """\
from fitdocs import Modality
from fitdocs.load import Unsupported, register


class _PluginCalculator:
    calculator_id = "plugin-calc"
    display_name = "Plugin Calculator"
    supported_modalities = frozenset({Modality.RUN})

    def required_athlete_fields(self):
        return ()

    def compute(self, activity, metrics, profile, session, context):
        return Unsupported(reason="plugin calculator never computes")


register(_PluginCalculator())
"""


def _configure_local_plugin(data_root: Path) -> None:
    plugins_dir = data_root / "plugins"
    plugins_dir.mkdir()
    (plugins_dir / "plugin_calc.py").write_text(
        _PLUGIN_CALCULATOR_SOURCE, encoding="utf-8"
    )
    (data_root / "fitdocs.toml").write_text(
        '[plugins]\npath = "plugins"\n', encoding="utf-8"
    )


def test_load_calculator_resolves_a_plugin_provided_id(tmp_path: Path) -> None:
    """Discovery runs before the engine call, so ``--calculator`` can name a
    plugin-provided id and have it resolve (Req 1.4, 1.5)."""
    data_root = _build_data_root(tmp_path, {"run.fit": builder.run_fit_bytes()})
    _configure_local_plugin(data_root)

    result = runner.invoke(
        app, ["load", "--out", str(data_root), "--calculator", "plugin-calc"]
    )

    # A resolved plugin id yields exit 0 with the plugin's own (unsupported)
    # outcome; an unresolved id would instead exit 2 (UnknownCalculatorError).
    assert result.exit_code == 0
    assert "Unsupported" in result.output


def test_load_unknown_calculator_lists_plugin_ids_alongside_builtins(
    tmp_path: Path,
) -> None:
    """An unknown ``--calculator`` id's error lists plugin ids too (Req 1.6)."""
    data_root = _build_data_root(tmp_path, {"run.fit": builder.run_fit_bytes()})
    _configure_local_plugin(data_root)

    result = runner.invoke(
        app, ["load", "--out", str(data_root), "--calculator", "nope"]
    )

    assert result.exit_code == 2
    assert "nope" in result.output
    assert "plugin-calc" in result.output


def test_load_malformed_athlete_toml_exits_two(tmp_path: Path) -> None:
    """A malformed ``athlete.toml`` is a configuration error -> exit 2 (Req 2.4)."""
    data_root = _build_data_root(tmp_path, {"run.fit": builder.run_fit_bytes()})
    (data_root / PROFILE_FILENAME).write_text(
        "ftp_watts = 'not a number'\n", encoding="utf-8"
    )
    result = runner.invoke(app, ["load", "--out", str(data_root)])
    assert result.exit_code == 2
    assert PROFILE_FILENAME in result.output


# --- session factory selection (Req 3.5) ------------------------------------


class _FakeStdin:
    """A minimal stdin double whose ``isatty`` reports a fixed value."""

    def __init__(self, *, tty: bool) -> None:
        self._tty = tty

    def isatty(self) -> bool:
        return self._tty


def test_build_session_interactive_only_on_tty_with_prompting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``_build_session`` returns the rich session only on a TTY with prompting
    enabled; ``--no-prompt`` or a non-TTY forces the non-interactive session."""
    monkeypatch.setattr(cli.sys, "stdin", _FakeStdin(tty=True))
    assert isinstance(_build_session(no_prompt=False), RichInteractionSession)
    # Prompting disabled wins even on a real terminal.
    assert isinstance(_build_session(no_prompt=True), NonInteractiveSession)
    # No terminal -> never interactive.
    monkeypatch.setattr(cli.sys, "stdin", _FakeStdin(tty=False))
    assert isinstance(_build_session(no_prompt=False), NonInteractiveSession)


# --- sync wiring: the load pass runs after syncing (Req 8.1) -----------------


def test_sync_runs_load_pass_marking_ride_unsupported(tmp_path: Path) -> None:
    """``fitdocs sync`` runs the load pass after writing docs: a synced ride doc
    ends up with the unsupported load state and the load summary prints (Req 8.1)."""
    source = tmp_path / "src"
    data_root = tmp_path / "data"
    data_root.mkdir()
    source.mkdir()
    (source / "ride.fit").write_bytes(builder.ride_fit_bytes())

    result = runner.invoke(app, ["sync", str(source), "--out", str(data_root)])

    assert result.exit_code == 0
    # The load summary printed (distinct from the sync summary's rows).
    assert "Unsupported" in result.output
    ride = _doc(data_root, "ride")
    assert classify_load_region(ride.read_text(encoding="utf-8")).state is (
        RegionState.UNSUPPORTED
    )


def test_sync_no_prompt_skips_run_cleanly(
    isolated_registry: None,
    computing_calculator: ComputingCalculator,
    tmp_path: Path,
) -> None:
    """``fitdocs sync --no-prompt`` keeps a run doc skipped cleanly (no prompt,
    exit 0) while still writing the document (Req 3.5, 8.1)."""
    source = tmp_path / "src"
    data_root = tmp_path / "data"
    data_root.mkdir()
    source.mkdir()
    (source / "run.fit").write_bytes(builder.run_fit_bytes())

    result = runner.invoke(
        app, ["sync", str(source), "--out", str(data_root), "--no-prompt"]
    )

    assert result.exit_code == 0
    run = _doc(data_root, "run")
    # No load frontmatter keys: the run was skipped, not computed.
    assert read_frontmatter_load(run.read_text(encoding="utf-8")) == {}
    # Discriminates from the zero-count "Skipped" table label (which appears
    # regardless of outcome): the doc's name and its missing-input reason
    # appear under the Skipped detail block (Req 8.6).
    assert run.name in result.output
    assert "missing required inputs" in result.output


# --- regen wiring: prompt-free restore (Req 7.4, 3.5) -----------------------


def test_regen_restores_load_frontmatter_without_prompting(
    isolated_registry: None,
    computing_calculator: ComputingCalculator,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A previously computed doc whose load frontmatter was reset (a regen) has
    its load keys restored by ``fitdocs regen`` -- prompt-free (Req 7.4, 3.5)."""
    data_root = _build_data_root(tmp_path, {"run.fit": builder.run_fit_bytes()})
    run = _doc(data_root, "run")
    # Compute it once via a scripted (interactive) session.
    monkeypatch.setattr(
        cli, "_build_session", lambda **_: _compute_run_session(level=7)
    )
    computed = runner.invoke(app, ["load", "--out", str(data_root)])
    assert computed.exit_code == 0
    assert read_frontmatter_load(run.read_text(encoding="utf-8"))["load_value"] == 70

    # Simulate the regen reset: strip the managed frontmatter keys, keep region.
    run.write_text(
        strip_frontmatter_load(run.read_text(encoding="utf-8")), encoding="utf-8"
    )
    assert read_frontmatter_load(run.read_text(encoding="utf-8")) == {}

    # regen must NOT be interactive; restore this deterministically. If regen
    # prompted, this scripted session (no queued answers) would raise on pop.
    result = runner.invoke(app, ["regen", "--out", str(data_root)])

    assert result.exit_code == 0
    assert "Restored" in result.output
    fm = read_frontmatter_load(run.read_text(encoding="utf-8"))
    assert fm["load_value"] == 70


# --- regen wiring: the load pass respects the version gate (Req 5.5, 5.8) ---


def _set_doc_version_line(text: str, replacement: str) -> str:
    """Replace the ``doc_version: N`` frontmatter line with an arbitrary line.

    Mirrors ``tests/test_sync.py``'s helper of the same name -- duplicated
    rather than imported so this end-to-end module stays independent of the
    unit-test module's internals.
    """
    lines = text.splitlines(keepends=True)
    out = []
    for line in lines:
        if line.lstrip().startswith("doc_version:"):
            if replacement:
                out.append(replacement + "\n")
            continue
        out.append(line)
    return "".join(out)


def test_regen_load_pass_leaves_newer_document_and_its_load_region_untouched(
    tmp_path: Path,
) -> None:
    """``fitdocs regen``'s document rewrite already refuses a newer ``doc_version``
    (task 5.1); the training-load pass that runs afterward must refuse it too
    (Req 5.5, 5.8) -- through the real CLI, not just the engine functions.

    Reproduction (task 7.2, found during 7.1 review): a freshly-synced ride
    document (never run through the load pass, so its ``load`` region is still
    a PLACEHOLDER) is stamped as written by a newer fitdocs, then ``fitdocs
    regen`` is run. Ride is a modality no registered calculator supports, so
    the training-load pass's compute path -- reached for any placeholder
    region regardless of ``--recompute`` -- writes the honest "unsupported"
    load-region content even non-interactively. Before the fix this happened
    even though the ``doc_version`` gate is meant to leave the WHOLE document,
    including its regions, untouched; the document-rewrite gate above it
    correctly left the frontmatter/body/regions untouched and warned, which is
    exactly what made this a training-load-pass-only defect.
    """
    data_root = _build_data_root(tmp_path, {"ride.fit": builder.ride_fit_bytes()})
    ride = _doc(data_root, "ride")
    original = ride.read_text(encoding="utf-8")
    assert classify_load_region(original).state is RegionState.PLACEHOLDER

    # Simulate the document being written by a NEWER fitdocs.
    newer = _set_doc_version_line(original, "doc_version: 999")
    ride.write_text(newer, encoding="utf-8")

    result = runner.invoke(app, ["regen", "--out", str(data_root)])

    assert result.exit_code == 0
    assert "999" in result.output
    # The document -- frontmatter, body, AND the load region the training-load
    # pass fills -- is left byte-identical. The load pass must not have
    # computed the honest "unsupported" state (or anything else) into it.
    assert ride.read_text(encoding="utf-8") == newer
