"""Feature-level end-to-end validation for training-load (task 5.1).

This is the differentiating feature's integration net: it exercises the *whole*
load layer over temporary data roots built with the **real** workout-docs
pipeline (:func:`fitdocs.sync.sync` renders documents, region markers,
frontmatter, and archives), proving that the engine, a calculator, the profile
store, the renderer, the doc editor, and the CLI integrate against the exact
document shapes fitdocs produces in the field -- not hand-mocked strings.

fitdocs ships no calculator (Amendment 2), so this suite drives the pass with
``ComputingCalculator`` (:mod:`tests.load.conftest`, task 1.1) -- the
published-contract stub -- registered per-test via the shared
``isolated_registry`` + ``computing_calculator`` fixtures. Unlike the
per-module suites (``test_engine`` isolates orchestration; ``test_prompts``
isolates the dialog), this suite spans multiple modules per scenario.

It also drives the **real** ``fitdocs.sync.regen`` (not a simulated frontmatter
strip) to prove restore-after-regen, and guards the profile seam (Req 2.5): a
profile written by the store loads through the read-only athlete-inputs reader
with byte-identical thresholds while a methodology-scoped table and
``profile_version`` are safely ignored.

These tests exercise ALREADY-IMPLEMENTED code (tasks 3.3 engine, 4.1 CLI, and
the calculator/store beneath them), so they must PASS as written; a failing
scenario would surface a real cross-module integration defect, not a RED phase.
The whole suite runs fully offline (asserted by construction in the final test).

Covered acceptance criteria: 2.5, 3.1, 3.5, 7.2, 7.4, 7.5, 7.6, 7.7,
8.1, 8.2, 8.5, 8.6, 8.7, 9.1, 9.3. (The interval-scoring vector this module
previously reproduced exercised withdrawn Requirement 6 -- the withdrawn
methodology's interval load computation -- and is not carried forward; per
tasks.md's Coverage Notes, withdrawn requirements are intentionally
uncovered.)
"""

from __future__ import annotations

import re
import tomllib
from collections.abc import Sequence
from datetime import timedelta, timezone
from pathlib import Path

import pytest
import yaml
from typer.testing import CliRunner

from fitdocs import ZoneSpec, cli
from fitdocs.athlete import ATHLETE_SCHEMA_VERSION, load_athlete_inputs
from fitdocs.cli import app
from fitdocs.contract import NOTES_REGION
from fitdocs.docmerge import extract_regions, region_block
from fitdocs.layout import WORKOUTS_DIR
from fitdocs.load.docedit import (
    RegionState,
    classify_load_region,
    read_frontmatter_load,
    replace_load_region,
)
from fitdocs.load.engine import DocLoadEntry, LoadReport, apply_load
from fitdocs.load.profile import (
    PROFILE_FILENAME,
    AthleteProfile,
    load_profile,
    save_profile,
)
from fitdocs.load.prompts import NonInteractiveSession
from fitdocs.load.types import AthleteField, InteractionSession
from fitdocs.sync import regen, sync
from tests.fixtures import builder
from tests.load.conftest import COMPUTING_FIELD, SCOPED_FIELD, ComputingCalculator

runner = CliRunner()

# PINNED timezone (never the system zone) so document stems are byte-stable.
_TZ = timezone(timedelta(hours=-6))


# --- scripted interaction session -------------------------------------------


class ScriptedSession:
    """An :class:`InteractionSession` double answering from per-kind FIFO queues.

    Each primitive pops the next answer from its own queue (a queued ``None``
    simulates a decline); an empty queue raises so an over-asking, mis-wired flow
    fails loudly rather than silently reading ``None``. This is the same double
    the per-module suites use, kept local so this file is self-contained.
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
    """Full compute script for a placeholder RUN doc with an EMPTY profile:
    collect ``level`` (the stub's one required field), then confirm the result.
    """
    return ScriptedSession(ints=[level], confirms=[confirm])


def _recompute_run_session(*, confirm: bool = True) -> ScriptedSession:
    """When the profile ALREADY carries ``level``, only the confirm dialog runs."""
    return ScriptedSession(confirms=[confirm])


# --- data-root construction (real workout-docs pipeline) --------------------


class _ServingTiles:
    """The always-supplied basemap-tile source these setup runs inject (task 6.1).

    ``tiles`` is a required engine argument now; this inert source serves
    deterministic PNG bytes for any ref, leaving the load-region and regen
    frontmatter-reset assertions untouched. Stateless -> one shared instance is
    safe across the setup ``sync`` and the real ``regen``.
    """

    attribution = "© OpenStreetMap contributors"

    def resolve(self, refs: Sequence[object]) -> dict[object, bytes]:
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


def _load_region(text: str) -> str:
    """The document's reserved ``load`` region inner content (byte-exact)."""
    return extract_regions(text)["load"]


def _docs_of(entries: tuple[DocLoadEntry, ...]) -> set[str]:
    return {entry.doc for entry in entries}


# --- Scenario 1: interactive compute, the headline path (3.1, 7.2, 8.2, 2.1) -


def test_interactive_compute_fills_doc_creates_profile_and_scores_result(
    isolated_registry: None,
    computing_calculator: ComputingCalculator,
    tmp_path: Path,
) -> None:
    """A real-pipeline RUN doc + a scripted interactive session yields the whole
    computed outcome: a COMPUTED load region whose payload parses, the three
    managed frontmatter keys, and an ``athlete.toml`` CREATED with the answered
    input (Req 3.1, 7.2, 8.2, 2.1).

    This is the feature's headline path: prompt -> persist -> compute -> render
    -> frontmatter, proven against a genuinely rendered document."""
    data_root = _build_data_root(tmp_path, {"run.fit": builder.run_fit_bytes()})
    run = _doc(data_root, "run")

    report = apply_load(data_root, session=_compute_run_session(level=7))

    assert isinstance(report, LoadReport)
    assert _docs_of(report.computed) == {_rel(data_root, run)}
    assert report.computed[0].detail == computing_calculator.calculator_id
    assert report.restored == () and report.skipped == () and report.failures == ()

    # The load region now classifies COMPUTED and its payload round-trips.
    text = run.read_text(encoding="utf-8")
    classification = classify_load_region(text)
    state, payload = classification.state, classification.payload
    assert state is RegionState.COMPUTED
    assert payload is not None and payload.result is not None
    assert payload.result.value == 70.0  # level 7 * 10

    # Region-only diagnostics -- absent from frontmatter -- survive the real
    # pass and land in the written document's payload (Req 7.1, 7.3): the
    # basis line, the non-selected entry's honest ``None`` value, and every
    # quality-flag verdict the stub raised.
    assert payload.result.basis == "stub computing basis (level 7)"
    non_selected = payload.result.non_selected
    assert len(non_selected) == 1
    assert non_selected[0].key == "stub-alt"
    assert non_selected[0].value is None
    flag_verdicts = {flag.key: flag.verdict for flag in payload.result.flags}
    assert flag_verdicts == {
        "stub-detected": "detected",
        "stub-not-detected": "not-detected",
        "stub-not-assessed": "not-assessed",
    }

    # The three managed frontmatter keys are present and correct (Req 7.2).
    fm = read_frontmatter_load(text)
    assert fm["load_value"] == 70
    assert fm["load_methodology"] == computing_calculator.calculator_id

    # athlete.toml was CREATED (Req 2.1) with the answered input.
    profile_path = data_root / PROFILE_FILENAME
    assert profile_path.is_file()
    stored = tomllib.loads(profile_path.read_text(encoding="utf-8"))
    assert stored[COMPUTING_FIELD.key] == 7 and isinstance(
        stored[COMPUTING_FIELD.key], int
    )
    assert stored["profile_version"] == ATHLETE_SCHEMA_VERSION

    # And it round-trips through the profile store's own reader.
    assert load_profile(data_root).get_number(COMPUTING_FIELD.key) == 7


# --- Scenario 3: idempotency (a repeated identical pass writes nothing) ------


def test_second_identical_pass_writes_no_bytes(
    isolated_registry: None,
    computing_calculator: ComputingCalculator,
    tmp_path: Path,
) -> None:
    """After a compute, a second (non-interactive) pass changes not one byte and
    reports empty computed/restored -- restore finds no drift on a stable doc.

    Mutation caught: if restore always rewrote frontmatter, or compute re-ran on
    an already-computed region, the byte snapshot would differ. The first
    pass's own outcome is asserted too (task 4.1 remediation): otherwise a
    classifier that never computes anything would trivially pass "the second
    pass writes nothing"."""
    data_root = _build_data_root(tmp_path, {"run.fit": builder.run_fit_bytes()})
    run = _doc(data_root, "run")

    first = apply_load(data_root, session=_compute_run_session())

    assert _docs_of(first.computed) == {_rel(data_root, run)}
    assert classify_load_region(run.read_text(encoding="utf-8")).state is (
        RegionState.COMPUTED
    )
    before = _snapshot(data_root)

    report = apply_load(data_root, session=NonInteractiveSession())

    assert _snapshot(data_root) == before  # not one byte changed
    assert report.computed == ()
    assert report.restored == ()


# --- Scenario 4: unsupported non-interactive (7.7, 3.5) ---------------------


def test_ride_gets_honest_unsupported_state_non_interactively(
    isolated_registry: None,
    computing_calculator: ComputingCalculator,
    tmp_path: Path,
) -> None:
    """A RIDE doc receives the honest unsupported state -- a human line naming the
    sport with NO digits -- written without any prompt, so it works under
    ``NonInteractiveSession`` (Req 7.7, 3.5).

    Mutation caught: if the engine prompted for a sport no calculator supports,
    the non-interactive session would leave it a placeholder."""
    data_root = _build_data_root(tmp_path, {"ride.fit": builder.ride_fit_bytes()})
    ride = _doc(data_root, "ride")

    report = apply_load(data_root, session=NonInteractiveSession())

    assert _docs_of(report.unsupported) == {_rel(data_root, ride)}
    text = ride.read_text(encoding="utf-8")
    classification = classify_load_region(text)
    state, payload = classification.state, classification.payload
    assert state is RegionState.UNSUPPORTED
    assert payload is not None and payload.sport == "Ride"
    # The visible (non-payload) line names the sport and carries no numbers.
    human = "\n".join(
        line
        for line in _load_region(text).splitlines()
        if not line.lstrip().startswith("<!-- fitdocs-load")
    )
    assert "Ride" in human
    assert not any(ch.isdigit() for ch in human)
    # Honest absence: no load frontmatter keys were written.
    assert read_frontmatter_load(text) == {}


# --- Scenario 5: non-interactive skip coexists with unsupported (3.5, 9.1) ---


def test_non_interactive_skips_run_but_marks_ride_unsupported(
    isolated_registry: None,
    computing_calculator: ComputingCalculator,
    tmp_path: Path,
) -> None:
    """Non-interactively, a placeholder RUN doc is skipped with a reason and left
    byte-identical (never computed from fabricated inputs), while a RIDE doc in
    the same pass still receives its unsupported state -- the two honest outcomes
    coexist and the pass never aborts on the skip (Req 3.5, 9.1, 7.7)."""
    data_root = _build_data_root(
        tmp_path,
        {"run.fit": builder.run_fit_bytes(), "ride.fit": builder.ride_fit_bytes()},
    )
    run = _doc(data_root, "run")
    ride = _doc(data_root, "ride")
    run_before = run.read_bytes()

    report = apply_load(data_root, session=NonInteractiveSession())

    assert _rel(data_root, run) in _docs_of(report.skipped)
    assert run.read_bytes() == run_before  # a skipped doc is untouched
    assert _rel(data_root, ride) in _docs_of(report.unsupported)
    assert classify_load_region(ride.read_text(encoding="utf-8")).state is (
        RegionState.UNSUPPORTED
    )
    # Nothing was answered, so no profile file was created (Req 9.1).
    assert not (data_root / PROFILE_FILENAME).exists()


# --- Scenario 6: restore after the REAL regen (7.4) -------------------------


def test_real_regen_resets_frontmatter_then_restore_readds_it(
    isolated_registry: None,
    computing_calculator: ComputingCalculator,
    tmp_path: Path,
) -> None:
    """Drive the genuine ``fitdocs.sync.regen``: regeneration resets the load
    frontmatter to generated values while preserving the load region verbatim,
    then a non-interactive load pass restores the frontmatter FROM the payload
    without recomputation and without prompting -- region bytes unchanged (7.4).

    This proves the restore integration against the real region-preservation
    mechanics rather than a hand-simulated frontmatter strip. Mutation caught: if
    regen leaked the load keys through, or restore recomputed/rewrote the region,
    the assertions below break."""
    data_root = _build_data_root(tmp_path, {"run.fit": builder.run_fit_bytes()})
    run = _doc(data_root, "run")
    apply_load(data_root, session=_compute_run_session(level=7))
    computed_region = _load_region(run.read_text(encoding="utf-8"))
    computed_payload = classify_load_region(run.read_text(encoding="utf-8")).payload

    # The REAL regeneration: re-render from the archive, preserving regions but
    # resetting frontmatter to generated values (the load keys are owned by this
    # feature and re-derived, so regen drops them).
    regen(data_root, athlete=load_athlete_inputs(data_root), tz=_TZ, tiles=_TILES)
    run = _doc(data_root, "run")  # same identity -> same document
    regen_text = run.read_text(encoding="utf-8")
    assert read_frontmatter_load(regen_text) == {}  # frontmatter reset by regen
    assert classify_load_region(regen_text).state is RegionState.COMPUTED
    assert _load_region(regen_text) == computed_region  # region preserved verbatim

    # A prompt-free pass restores the frontmatter from the preserved payload.
    report = apply_load(data_root, session=NonInteractiveSession())

    assert _docs_of(report.restored) == {_rel(data_root, run)}
    assert report.computed == ()
    restored_text = run.read_text(encoding="utf-8")
    fm = read_frontmatter_load(restored_text)
    assert fm["load_value"] == 70
    # Restore touches only frontmatter: the region content is byte-identical.
    assert _load_region(restored_text) == computed_region
    assert classify_load_region(restored_text).payload == computed_payload


# --- Scenario 7: recompute replaces the result with fresh confirmation (8.3) -


def test_recompute_replaces_result_with_fresh_confirmation(
    isolated_registry: None,
    computing_calculator: ComputingCalculator,
    tmp_path: Path,
) -> None:
    """``recompute=True`` re-confirms from scratch and replaces a COMPUTED result
    with a fresh one derived from the profile at recompute time (Req 8.3).

    Mutation caught: if recompute honored the no-overwrite rule, the result would
    stay level 3 / 30 instead of the newly confirmed level 5 / 50; if recompute
    skipped re-confirmation, ``_recompute_run_session`` (which queues exactly
    one confirm answer) would raise on the missing answer."""
    data_root = _build_data_root(tmp_path, {"run.fit": builder.run_fit_bytes()})
    run = _doc(data_root, "run")
    apply_load(data_root, session=_compute_run_session(level=3))
    assert read_frontmatter_load(run.read_text(encoding="utf-8"))["load_value"] == 30

    # Simulate the athlete's stub level rising between passes -- ``level`` is
    # already present in the profile, so recompute only re-runs the confirm
    # dialog and picks up the new persisted value.
    profile = load_profile(data_root)
    save_profile(data_root, profile.with_value(COMPUTING_FIELD, 5))
    report = apply_load(data_root, session=_recompute_run_session(), recompute=True)

    assert _docs_of(report.computed) == {_rel(data_root, run)}
    fm = read_frontmatter_load(run.read_text(encoding="utf-8"))
    assert fm["load_value"] == 50  # level 5 * 10


# --- Scenario 8: foreign-content protection (7.6) ---------------------------


def test_foreign_region_untouched_without_recompute_then_overwritten(
    isolated_registry: None,
    computing_calculator: ComputingCalculator,
    tmp_path: Path,
) -> None:
    """Hand-edited (foreign) load-region content is left byte-identical and
    reported skipped on an ordinary pass; ``recompute=True`` overwrites it (7.6).

    Mutation caught: if the engine failed to recognize foreign content, it would
    clobber the user's own edit on a routine pass."""
    data_root = _build_data_root(tmp_path, {"run.fit": builder.run_fit_bytes()})
    run = _doc(data_root, "run")
    foreign = replace_load_region(
        run.read_text(encoding="utf-8"), "My own hand-written training notes."
    )
    run.write_text(foreign, encoding="utf-8")
    assert classify_load_region(foreign).state is RegionState.FOREIGN

    # Without recompute: untouched and reported skipped.
    report = apply_load(data_root, session=NonInteractiveSession())
    assert _rel(data_root, run) in _docs_of(report.skipped)
    assert run.read_text(encoding="utf-8") == foreign

    # With recompute: the foreign content is overwritten by a fresh compute.
    report2 = apply_load(data_root, session=_compute_run_session(), recompute=True)
    assert _docs_of(report2.computed) == {_rel(data_root, run)}
    assert classify_load_region(run.read_text(encoding="utf-8")).state is (
        RegionState.COMPUTED
    )


# --- Scenario 9: missing archive -> failure, other docs still process (9.3) --


def test_missing_archive_fails_that_doc_while_others_process(
    isolated_registry: None,
    computing_calculator: ComputingCalculator,
    tmp_path: Path,
) -> None:
    """A document whose archived source is missing becomes a failure entry (its
    bytes untouched), and OTHER documents in the same pass still process -- the
    pass never aborts (Req 8.5, 9.3).

    Mutation caught: if a missing archive raised out of the pass, the ride would
    never be marked unsupported and no failure would be recorded."""
    data_root = _build_data_root(
        tmp_path,
        {"run.fit": builder.run_fit_bytes(), "ride.fit": builder.ride_fit_bytes()},
    )
    run = _doc(data_root, "run")
    ride = _doc(data_root, "ride")
    run_before = run.read_bytes()
    # Delete the run's archived source so its load pass cannot resolve it.
    data_root.joinpath(*_sources_last(run).split("/")).unlink()

    report = apply_load(data_root, session=NonInteractiveSession())

    assert _rel(data_root, run) in _docs_of(report.failures)
    assert run.read_bytes() == run_before  # a failure never mutates its doc
    # The pass kept going: the ride still received its unsupported state.
    assert _rel(data_root, ride) in _docs_of(report.unsupported)


# --- Scenario 10: profile seam guard (2.5) ----------------------------------


# A shared top-level field workout-docs' read-only reader knows about, built
# only from the published contract (mirrors what a real calculator would
# declare) -- not scoped, so it collides with no calculator's own table.
_MAX_HR = AthleteField(
    key="max_hr_bpm",
    label="Tested max HR",
    kind="int",
    minimum=120,
    maximum=220,
)


def test_store_written_profile_reads_back_identically_through_reader(
    tmp_path: Path,
) -> None:
    """A profile written by the load store loads through the existing read-only
    athlete-inputs reader without raising and yields byte-identical thresholds --
    int ``max_hr_bpm``/``resting_hr_bpm``, float ``ftp_watts``, and the zone spec
    -- while a methodology-scoped table and ``profile_version`` are safely
    ignored (Req 2.5).

    This is the shared-file contract between training-load (writer) and
    workout-docs (reader): if the store broke the int-serialization seam or lost
    an unmanaged key, the reader would raise or read a different threshold."""
    data_root = tmp_path / "data"
    data_root.mkdir()
    # Shared workout-docs keys start present (as a user/prior file would have),
    # then the store adds its managed fields through the validated write path:
    # one shared top-level field, and one methodology-scoped field (Req 2.7).
    base = AthleteProfile(
        data={
            "resting_hr_bpm": 45,
            "ftp_watts": 250.0,
            "hr_zones": [120.0, 140.0, 160.0, 180.0],
        }
    )
    profile = base.with_value(_MAX_HR, 190).with_value(SCOPED_FIELD, 42)
    save_profile(data_root, profile)

    # The read-only reader accepts the store's file (no raise) ...
    inputs = load_athlete_inputs(data_root)
    assert inputs is not None
    # ... and yields the SAME thresholds with the SAME types.
    assert inputs.max_hr_bpm == 190 and type(inputs.max_hr_bpm) is int
    assert inputs.resting_hr_bpm == 45 and type(inputs.resting_hr_bpm) is int
    assert inputs.ftp_watts == 250.0 and type(inputs.ftp_watts) is float
    assert inputs.hr_zones == ZoneSpec(dividers=(120.0, 140.0, 160.0, 180.0))

    # The scoped table and profile_version were ignored by the reader but
    # preserved for the store, which re-reads them from its own file.
    reloaded = load_profile(data_root)
    assert reloaded.get_number(SCOPED_FIELD.key) == 42
    assert reloaded.get_number("max_hr_bpm") == 190
    stored = tomllib.loads((data_root / PROFILE_FILENAME).read_text(encoding="utf-8"))
    assert stored["profile_version"] == ATHLETE_SCHEMA_VERSION
    assert stored["stub-scoped"] == {"custom_threshold": 42}


# --- Scenario 11: CLI end-to-end (8.1, 8.6) ---------------------------------


def test_cli_load_computes_run_and_reports_summary(
    isolated_registry: None,
    computing_calculator: ComputingCalculator,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``fitdocs load`` over a prepared data root computes the run through a
    scripted (interactive) session, prints the five-row summary table, and exits
    0 -- the standalone command wired to the same engine (Req 8.2, 8.6)."""
    data_root = _build_data_root(tmp_path, {"run.fit": builder.run_fit_bytes()})
    run = _doc(data_root, "run")
    monkeypatch.setattr(
        cli, "_build_session", lambda **_: _compute_run_session(level=7)
    )

    result = runner.invoke(app, ["load", "--out", str(data_root)])

    assert result.exit_code == 0
    for label in ("Computed", "Restored", "Unsupported", "Skipped", "Failed"):
        assert label in result.output
    assert computing_calculator.calculator_id in result.output
    fm = read_frontmatter_load(run.read_text(encoding="utf-8"))
    assert fm["load_value"] == 70
    assert fm["load_methodology"] == computing_calculator.calculator_id
    assert (data_root / PROFILE_FILENAME).is_file()


def _table_count(output: str, label: str) -> int:
    """The integer count printed on the summary table's ``label`` row.

    Tolerant of the rich table's box-drawing borders and column padding: it
    matches ``label`` followed (across the cell border) by the row's digits.
    """
    match = re.search(rf"{re.escape(label)}\s*\S\s*(\d+)", output)
    assert match is not None, f"{label!r} row not found in:\n{output}"
    return int(match.group(1))


def test_cli_sync_printed_summary_matches_load_report_buckets(
    isolated_registry: None,
    computing_calculator: ComputingCalculator,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Task 6.3 bullet 2: ``fitdocs sync`` writes documents and runs the load
    pass afterward; the printed summary's five row counts match the actual
    :class:`LoadReport` buckets the pass produced (Req 8.1, 8.2, 8.6).

    ``cli._run_load_pass`` is spied (not replaced) so the real report used to
    print the table is captured independently of the table-printing code --
    a swapped or miscounted row in ``_report_load`` reddens this test without
    needing a second, hand-maintained expectation of the counts."""
    source = tmp_path / "src"
    data_root = tmp_path / "data"
    source.mkdir()
    data_root.mkdir()
    (source / "run.fit").write_bytes(builder.run_fit_bytes())
    (source / "ride.fit").write_bytes(builder.ride_fit_bytes())
    monkeypatch.setattr(
        cli, "_build_session", lambda **_: _compute_run_session(level=7)
    )
    real_run_load_pass = cli._run_load_pass
    captured: list[LoadReport] = []

    def _spy(*args: object, **kwargs: object) -> LoadReport:
        report = real_run_load_pass(*args, **kwargs)  # type: ignore[arg-type]
        captured.append(report)
        return report

    monkeypatch.setattr(cli, "_run_load_pass", _spy)

    result = runner.invoke(app, ["sync", str(source), "--out", str(data_root)])

    assert result.exit_code == 0
    assert len(captured) == 1
    report = captured[0]
    # Without this, the comparison below is self-referential about *content*:
    # an all-zero report matches an all-zero table, so a sync that discovered
    # no documents at all would pass. This pins the "sync writes documents and
    # runs the pass" half of the bullet inside this test rather than leaving it
    # to siblings.
    assert report.computed and report.unsupported
    for label, expected in (
        ("Computed", len(report.computed)),
        ("Restored", len(report.restored)),
        ("Unsupported", len(report.unsupported)),
        ("Skipped", len(report.skipped)),
        ("Failed", len(report.failures)),
    ):
        assert _table_count(result.output, label) == expected


def test_report_load_prints_each_bucket_count_distinctly(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Task 6.3 bullet 2 remediation: ``cli._report_load`` prints each of the
    five buckets' own count, not a swapped neighbor's (Req 8.6).

    The fixture's five bucket sizes (1, 2, 3, 4, 5) are pairwise distinct, so a
    row-swap mutation between *any* two buckets -- including two buckets that
    both happen to be nonzero, or two that are both non-nonzero -- changes at
    least one printed count and reddens this test. A fixture with any two
    buckets tied at the same size would leave a swap between exactly those two
    invisible; that failure mode is why the end-to-end sync test above (which
    ties three buckets at 0 and two at 1) could not carry this assertion
    alone."""
    report = LoadReport(
        computed=(DocLoadEntry(doc="a.md", detail="load ok"),),
        restored=(
            DocLoadEntry(doc="b.md", detail="load ok"),
            DocLoadEntry(doc="c.md", detail="load ok"),
        ),
        unsupported=(
            DocLoadEntry(doc="d.md", detail="no calculator"),
            DocLoadEntry(doc="e.md", detail="no calculator"),
            DocLoadEntry(doc="f.md", detail="no calculator"),
        ),
        skipped=(
            DocLoadEntry(doc="g.md", detail="missing inputs"),
            DocLoadEntry(doc="h.md", detail="missing inputs"),
            DocLoadEntry(doc="i.md", detail="missing inputs"),
            DocLoadEntry(doc="j.md", detail="missing inputs"),
        ),
        failures=(
            DocLoadEntry(doc="k.md", detail="bad archive"),
            DocLoadEntry(doc="l.md", detail="bad archive"),
            DocLoadEntry(doc="m.md", detail="bad archive"),
            DocLoadEntry(doc="n.md", detail="bad archive"),
            DocLoadEntry(doc="o.md", detail="bad archive"),
        ),
    )

    cli._report_load(report)

    out = capsys.readouterr().out
    for label, expected in (
        ("Computed", 1),
        ("Restored", 2),
        ("Unsupported", 3),
        ("Skipped", 4),
        ("Failed", 5),
    ):
        assert _table_count(out, label) == expected


def test_cli_sync_runs_load_pass_marking_rowing_unsupported(tmp_path: Path) -> None:
    """``fitdocs sync`` runs the load pass after writing documents: a synced
    rowing document ends up with the unsupported load state and the load
    summary prints (Req 8.1, 8.6) -- proving the sync-integrated pass over
    freshly written documents.

    Rowing, not ride, is the sport used here: ``threshold-load``'s built-in
    now supports RIDE (Req 1.1, 2.1), where -- with no athlete benchmarks on
    file -- it would report ``skipped`` for missing inputs rather than
    ``unsupported``. Rowing is outside every registered calculator's declared
    support, so the honest-unsupported claim this test names stays true.
    """
    source = tmp_path / "src"
    data_root = tmp_path / "data"
    source.mkdir()
    data_root.mkdir()
    (source / "row.fit").write_bytes(builder.small_sport_fit_bytes(3103, "rowing"))

    result = runner.invoke(app, ["sync", str(source), "--out", str(data_root)])

    assert result.exit_code == 0
    assert "Unsupported" in result.output
    row = _doc(data_root, "row")
    assert classify_load_region(row.read_text(encoding="utf-8")).state is (
        RegionState.UNSUPPORTED
    )


# --- Scenario 12: offline by construction (8.7) -----------------------------


def test_load_layer_imports_no_network_libraries() -> None:
    """The load pass operates fully offline (Req 8.7). Asserted by construction:
    no module under ``fitdocs.load`` imports a networking library, so a pass can
    only ever read the data root's documents, archives, and profile.

    Scanning the package source is the durable guard -- a new import of any
    network client anywhere in the load layer would fail this test."""
    import fitdocs.load  # noqa: PLC0415 -- inspecting the real installed package

    assert fitdocs.load.__file__ is not None
    package_dir = Path(fitdocs.load.__file__).parent
    forbidden = (
        "socket",
        "ssl",
        "http",
        "urllib",
        "urllib3",
        "requests",
        "httpx",
        "aiohttp",
        "ftplib",
        "smtplib",
        "websocket",
        "websockets",
        "asyncio",
    )
    pattern = re.compile(
        rf"^\s*(?:import|from)\s+({'|'.join(re.escape(m) for m in forbidden)})\b",
        re.MULTILINE,
    )
    offenders: list[str] = []
    for py in sorted(package_dir.rglob("*.py")):
        for match in pattern.finditer(py.read_text(encoding="utf-8")):
            offenders.append(f"{py.name}: {match.group(1)}")
    assert offenders == [], f"load layer imports networking modules: {offenders}"


# --- Scenario 13: a computing pass leaves the notes region untouched (7.1) --


def _write_notes(doc: Path, text: str) -> None:
    """Overwrite ``doc``'s user-owned ``notes`` region, verbatim, via the public
    region grammar (:func:`region_block`/:func:`extract_regions` are each
    other's inverse, so the old block's exact text is reconstructible and safe
    to substring-replace)."""
    markdown = doc.read_text(encoding="utf-8")
    old_notes = extract_regions(markdown)[NOTES_REGION]
    old_block = region_block(NOTES_REGION, old_notes)
    assert old_block in markdown
    new_block = region_block(NOTES_REGION, text)
    doc.write_text(markdown.replace(old_block, new_block, 1), encoding="utf-8")


def test_compute_preserves_the_notes_region_byte_for_byte(
    isolated_registry: None,
    computing_calculator: ComputingCalculator,
    tmp_path: Path,
) -> None:
    """A computing pass writes only the ``load`` region: the user-owned ``notes``
    region survives byte-for-byte, and the load region genuinely changes (Req
    7.1). No fixture anywhere else in this module puts user content in a
    non-load region and runs ``apply_load`` over it, leaving 7.1's "without
    altering any other section or user-editable region" clause -- claimed by
    task 2.1, whose boundary is the renderer, not the surgery in
    ``docedit.replace_load_region`` -- unpinned at the integration level.

    Mutation caught: an engine that re-rendered the whole document from the
    archived source instead of surgically replacing only the ``load`` region
    (via ``replace_load_region``) would reset this hand-written notes content
    back to the freshly rendered placeholder, while the load region and
    frontmatter would still look correct -- the exact defect this test exists
    to catch."""
    data_root = _build_data_root(tmp_path, {"run.fit": builder.run_fit_bytes()})
    run = _doc(data_root, "run")

    distinctive_notes = "Felt strong on the last mile -- new shoes, negative split."
    _write_notes(run, distinctive_notes)
    before = run.read_text(encoding="utf-8")
    before_regions = extract_regions(before)
    # Reachability: the scenario is only meaningful if notes actually hold
    # content before the pass -- an empty notes region would make the
    # preservation assertion below vacuous (empty == empty).
    assert before_regions["notes"] == distinctive_notes
    assert before_regions["notes"] != ""
    # Falsity in the starting state for the load half: the pass has not run
    # yet, so the load region does not yet hold the final computed content.
    assert classify_load_region(before).state is not RegionState.COMPUTED

    report = apply_load(data_root, session=_compute_run_session(level=7))

    assert _docs_of(report.computed) == {_rel(data_root, run)}
    after = run.read_text(encoding="utf-8")
    after_regions = extract_regions(after)

    # The non-load, user-editable region survives byte-for-byte (Req 7.1).
    assert after_regions["notes"] == before_regions["notes"]
    # The load region genuinely changed -- a no-op pass would otherwise
    # satisfy this test just as well as a correct surgical one.
    assert after_regions["load"] != before_regions["load"]
    assert classify_load_region(after).state is RegionState.COMPUTED
